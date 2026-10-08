#!/usr/bin/env python3
"""One environment mapping; parse dotenv as data, never execute it."""
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys

REQUIRED = ('ARENA_DB_NAME', 'ARENA_DB_USERNAME', 'ARENA_DB_PASSWORD',
            'KC_ADMIN_USERNAME', 'KC_ADMIN_PASSWORD', 'KC_BFF_CLIENT_SECRET',
            'INITIAL_ADMIN_USERNAME', 'INITIAL_ADMIN_EMAIL', 'INITIAL_ADMIN_PASSWORD')
class ConfigError(ValueError):
    pass

ENVIRONMENTS = {
    'dev': ('arena-dev', 'localhost', '9091'),
    'sit': ('arena-sit', 'sit.arenaops.in', '19091'),
    'prod': ('arena', 'arenaops.in', '29091'),
}

def load_config(filename):
    path = Path(filename)
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ConfigError('Runtime env file must exist and have mode 0600')
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise ConfigError('Invalid env file entry')
        # Workflow writes JSON double-quoted strings with dotenv dollars escaped.
        if value.startswith('"'):
            value = json.loads(value).replace('$$', '$')
        elif value.startswith("'"):
            if not value.endswith("'"):
                raise ConfigError('Invalid quoted env value')
            value = value[1:-1].replace("\\'", "'")
        if any(c in value for c in '\r\n\x00'):
            raise ConfigError('Env values must be single line')
        if key in values:
            raise ConfigError('Duplicate env key: ' + key)
        values[key] = value
    allowed = set(REQUIRED) | {'ARENA_ENV', 'CADDY_BIND_IP'}
    if set(values) - allowed:
        raise ConfigError('Unknown env keys: ' + ', '.join(sorted(set(values) - allowed)))
    environment = values.get('ARENA_ENV')
    if environment not in ENVIRONMENTS:
        raise ConfigError('ARENA_ENV must be dev, sit or prod')
    for key in REQUIRED:
        if not values.get(key) or not values[key].strip():
            raise ConfigError(key + ' is required')
    if values['INITIAL_ADMIN_USERNAME'].casefold() == values['KC_ADMIN_USERNAME'].casefold():
        raise ConfigError('Initial application admin and master administrator must have distinct usernames')
    if not re.fullmatch(r'[A-Za-z0-9._@+-]+', values['INITIAL_ADMIN_USERNAME']):
        raise ConfigError('Invalid initial admin username')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', values['INITIAL_ADMIN_EMAIL']):
        raise ConfigError('Invalid initial admin email')
    if values['INITIAL_ADMIN_PASSWORD'].lower() in ('admin', 'password'):
        raise ConfigError('Default initial admin passwords are forbidden')
    if environment != 'dev':
        if values['KC_ADMIN_USERNAME'].lower() == 'admin' and values['KC_ADMIN_PASSWORD'].lower() == 'admin':
            raise ConfigError('Remote admin/admin credentials are forbidden')
        if not values.get('CADDY_BIND_IP'):
            raise ConfigError('CADDY_BIND_IP is required for remote environments')
        ipaddress.IPv4Address(values['CADDY_BIND_IP'])
    realm, domain, port = ENVIRONMENTS[environment]
    values.update(KC_REALM=realm, ARENAOPS_DOMAIN=domain,
                  COMPOSE_PROJECT_NAME='arenaops-' + environment,
                  ARENAOPS_NETWORK='arenaops-' + environment,
                  KC_LOCAL_PORT=port, KC_BASE_URL='http://127.0.0.1:' + port + '/auth',
                  KC_PUBLIC_URL=('http://localhost:' + port if environment == 'dev' else 'https://' + domain) + '/auth',
                  ARENAOPS_TARGET='/opt/arenaops/' + environment)
    return values

if __name__ == '__main__':
    try:
        config = load_config(sys.argv[1])
        for key, value in config.items():
            print('export ' + key + '=' + shlex.quote(value))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Cannot parse runtime env file', file=sys.stderr)
        sys.exit(1)
