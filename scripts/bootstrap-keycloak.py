#!/usr/bin/env python3
"""Bootstrap without putting credentials/tokens in process arguments or logs."""
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import sys

ROLE_NAMES = {'manage-users', 'view-users', 'view-realm'}

def bootstrap(template_path):
    for key in ('KC_REALM', 'KC_BASE_URL', 'KC_ADMIN_USERNAME', 'KC_ADMIN_PASSWORD', 'KC_BFF_CLIENT_SECRET'):
        if not os.environ.get(key):
            raise RuntimeError(key + ' is required')
    base = os.environ['KC_BASE_URL'].rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise RuntimeError('Invalid KC_BASE_URL')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', 'keycloak'):
        raise RuntimeError('Plain HTTP bootstrap must use a local/private Keycloak endpoint')
    realm = os.environ['KC_REALM']
    if realm not in ('arena-dev', 'arena-sit', 'arena'):
        raise RuntimeError('Unsupported KC_REALM')
    data = json.loads(Path(template_path).read_text())
    if data.get('realm') != realm:
        raise RuntimeError('Realm template does not match KC_REALM')
    clients = [c for c in data['clients'] if c['clientId'] == 'arena-bff']
    if len(clients) != 1:
        raise RuntimeError('Expected exactly one arena-bff client')
    clients[0]['secret'] = os.environ['KC_BFF_CLIENT_SECRET']
    # Secure files are always cleaned, including HTTP/JSON errors.
    os.umask(0o077)
    temp_base = '/dev/shm' if Path('/dev/shm').is_dir() else None
    with tempfile.TemporaryDirectory(prefix='arenaops-bootstrap-', dir=temp_base) as directory:
        temporary_realm = Path(directory) / 'realm.json'
        temporary_realm.write_text(json.dumps(data))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token = None

        def request(path, method='GET', body=None, form=False, allowed=()):
            headers = {}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            if body is not None:
                headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
            req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
            try:
                with opener.open(req, timeout=10) as response:
                    content = response.read()
                    return response.status, json.loads(content) if content else None
            except urllib.error.HTTPError as exc:
                if exc.code in allowed:
                    return exc.code, None
                raise RuntimeError('Keycloak request failed: HTTP ' + str(exc.code)) from None
            except urllib.error.URLError:
                raise RuntimeError('Keycloak endpoint is unavailable') from None

        for attempt in range(60):
            try:
                request('/realms/master/.well-known/openid-configuration')
                break
            except RuntimeError:
                if attempt == 59:
                    raise RuntimeError('Keycloak did not become ready') from None
                time.sleep(5)
        form = urllib.parse.urlencode(dict(client_id='admin-cli', username=os.environ['KC_ADMIN_USERNAME'],
                                          password=os.environ['KC_ADMIN_PASSWORD'], grant_type='password')).encode()
        _, auth = request('/realms/master/protocol/openid-connect/token', 'POST', form, True)
        token = auth.get('access_token')
        if not token:
            raise RuntimeError('Missing admin access token')
        admin = '/admin/realms/' + realm
        status, _ = request(admin, allowed=(404,))
        if status == 404:
            request('/admin/realms', 'POST', temporary_realm.read_bytes())
            print('Created ' + realm)
        else:
            print(realm + ' already exists; configuration and client secret preserved')

        def client_id(name):
            _, found = request(admin + '/clients?clientId=' + name)
            exact = [c for c in found if c.get('clientId') == name]
            if len(exact) != 1 or not exact[0].get('id'):
                raise RuntimeError('Required client missing: ' + name)
            return exact[0]['id']

        bff = client_id('arena-bff')
        management = client_id('realm-management')
        _, service_user = request(admin + '/clients/' + bff + '/service-account-user')
        if not service_user.get('id'):
            raise RuntimeError('Missing BFF service account')
        _, available_roles = request(admin + '/clients/' + management + '/roles')
        roles = [r for r in available_roles if r['name'] in ROLE_NAMES]
        if {r['name'] for r in roles} != ROLE_NAMES:
            raise RuntimeError('Required management roles are missing')
        role_path = admin + '/users/' + service_user['id'] + '/role-mappings/clients/' + management
        _, assigned = request(role_path)
        missing = [r for r in roles if r['id'] not in {a['id'] for a in assigned}]
        if missing:
            request(role_path, 'POST', json.dumps(missing).encode())
        print('BFF service-account roles configured')

if __name__ == '__main__':
    try:
        bootstrap(sys.argv[1])
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # HTTP bodies and JSON parser diagnostics can contain sensitive values.
        print('Keycloak bootstrap failed; check configuration and internal availability', file=sys.stderr)
        sys.exit(1)
