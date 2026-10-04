import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('config', ROOT / 'scripts/config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

class InfrastructureTests(unittest.TestCase):
    def runtime(self, directory, environment='sit', **overrides):
        values = {k: 'validation' for k in config.REQUIRED}
        values.update(ARENA_ENV=environment, CADDY_BIND_IP='127.0.0.1')
        values.update(overrides)
        path = Path(directory) / 'runtime.env'
        path.write_text(''.join(k + '=' + json.dumps(v.replace('$', '$$')) + '\n' for k, v in values.items()))
        path.chmod(0o600)
        return path

    def test_environment_mapping_and_compose_isolation(self):
        volumes = set()
        for environment, (realm, domain, port) in config.ENVIRONMENTS.items():
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as directory:
                values = config.load_config(self.runtime(directory, environment))
                self.assertEqual(values['KC_REALM'], realm)
                self.assertEqual(values['ARENAOPS_TARGET'], '/opt/arenaops/' + environment)
                env = dict(os.environ, **values)
                command = ['docker', 'compose', '--env-file', '/dev/null', '-p', values['COMPOSE_PROJECT_NAME'],
                           '-f', str(ROOT / 'docker/docker-compose.infra.yaml')]
                if environment == 'dev':
                    command += ['-f', str(ROOT / 'docker/docker-compose.dev.yaml')]
                result = subprocess.run(command + ['config', '--format', 'json'], env=env,
                                        check=True, capture_output=True, text=True)
                composed = json.loads(result.stdout)
                volume = composed['volumes']['postgres_data']['name']
                self.assertNotIn(volume, volumes)
                volumes.add(volume)
                self.assertEqual(composed['networks']['arenaops']['name'], 'arenaops-' + environment)
                self.assertTrue(composed['networks']['arenaops']['external'])
                services = composed['services']
                self.assertEqual(services['keycloak']['ports'][0]['host_ip'], '127.0.0.1')
                self.assertEqual(str(services['keycloak']['ports'][0]['published']), port)
                if environment != 'dev':
                    self.assertNotIn('ports', services['postgres'])
                self.assertEqual(set(services), {'postgres', 'keycloak'})
                for name, service in services.items():
                    self.assertEqual(service['container_name'], environment + '-' + name)
                    self.assertEqual(set(service['networks']), {'arenaops'})
                    self.assertIn(environment + '-' + name, service['networks']['arenaops']['aliases'])
                    self.assertIn('healthcheck', service)
                    self.assertEqual(service['restart'], 'unless-stopped')
                self.assertEqual(services['keycloak']['environment']['KC_BOOTSTRAP_ADMIN_PASSWORD'], 'validation')

    def test_shared_edge_networks_ports_and_persistent_volumes(self):
        result = subprocess.run(['docker', 'compose', '--env-file', '/dev/null', '-f',
            str(ROOT / 'docker/docker-compose.edge.yaml'), 'config', '--format', 'json'],
            env=dict(os.environ, CADDY_BIND_IP='127.0.0.1'), check=True, capture_output=True, text=True)
        composed = json.loads(result.stdout)
        self.assertEqual(composed['name'], 'arenaops-edge')
        self.assertEqual(set(composed['services']), {'caddy'})
        edge = composed['services']['caddy']
        self.assertEqual(edge['container_name'], 'arenaops-edge-caddy')
        self.assertEqual(set(edge['networks']), {'sit', 'prod'})
        self.assertEqual({str(p['published']) for p in edge['ports']}, {'80', '443'})
        for environment in ('sit', 'prod'):
            self.assertEqual(composed['networks'][environment]['name'], 'arenaops-' + environment)
            self.assertTrue(composed['networks'][environment]['external'])
        self.assertEqual(composed['volumes']['caddy_data']['name'], 'arenaops-edge-caddy-data')
        self.assertIn('flock 9', (ROOT / 'scripts/apply-edge.sh').read_text())
        self.assertIn('arenaops-shared-vps-infrastructure', (ROOT / '.github/workflows/infrastructure.yaml').read_text())

    def test_fail_fast_invalid_and_missing_configuration(self):
        for overrides in ({'ARENA_ENV': 'production'}, {'KC_BFF_CLIENT_SECRET': ''},
                          {'KC_ADMIN_USERNAME': 'admin', 'KC_ADMIN_PASSWORD': 'admin'}, {'CADDY_BIND_IP': ''}):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    config.load_config(self.runtime(directory, **overrides))
        with tempfile.TemporaryDirectory() as directory:
            path = self.runtime(directory)
            path.chmod(0o644)
            with self.assertRaises(ValueError): config.load_config(path)

    def test_secret_serialization(self):
        secret = '''dollar$quote"apostrophe'backslash\\backtick`$(command)# space'''
        with tempfile.TemporaryDirectory() as directory:
            values = config.load_config(self.runtime(directory, KC_BFF_CLIENT_SECRET=secret))
            self.assertEqual(values['KC_BFF_CLIENT_SECRET'], secret)
            env = dict(os.environ, **{k: 'validation' for k in config.REQUIRED})
            env.update(ARENA_ENV='sit', CADDY_BIND_IP='127.0.0.1', KC_BFF_CLIENT_SECRET=secret)
            path = Path(directory) / 'generated.env'
            subprocess.run(['python3', str(ROOT / 'scripts/write-runtime-env.py'), str(path)], env=env, check=True)
            self.assertEqual(config.load_config(path)['KC_BFF_CLIENT_SECRET'], secret)

    def test_realms_and_public_routes(self):
        for environment, (realm, domain, _) in config.ENVIRONMENTS.items():
            data = json.loads((ROOT / f'keycloak/realm/arena-realm.{environment}.template.json').read_text())
            self.assertEqual(data['realm'], realm)
            self.assertEqual(data['loginTheme'], 'arena-login')
            self.assertFalse(data['users'])
            clients = {c['clientId']: c for c in data['clients']}
            self.assertNotIn('secret', clients['arena-bff'])
            self.assertEqual(clients['arena-ui']['attributes']['pkce.code.challenge.method'], 'S256')
            if environment != 'dev':
                self.assertEqual(clients['arena-ui']['webOrigins'], ['https://' + domain])
                self.assertEqual(data['sslRequired'], 'external')
        caddy = (ROOT / 'docker/Caddyfile').read_text()
        self.assertIn('respond @private_auth 404', caddy)
        self.assertLess(caddy.index('respond @private_auth'), caddy.index('reverse_proxy sit-arena-ui'))
        for environment, realm in [('sit', 'arena-sit'), ('prod', 'arena')]:
            self.assertIn('/auth/realms/' + realm + '/*', caddy)
            for service, port in [('keycloak', 8080), ('arena-login', 7700), ('arena-ui', 80)]:
                self.assertIn(environment + '-' + service + ':' + str(port), caddy)
        self.assertNotIn('{$', caddy)
        self.assertNotIn('reverse_proxy keycloak', caddy) # Must always have a matcher.

    def test_workflow_is_manual_and_has_separate_targets(self):
        text = (ROOT / '.github/workflows/infrastructure.yaml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('\n  push:', text)
        self.assertIn("inputs.confirmation == 'APPLY'", text)
        self.assertIn('sit-infrastructure', text)
        self.assertIn('production-infrastructure', text)
        self.assertIn('/dev/shm/', (ROOT / 'scripts/deploy-from-actions.sh').read_text())
        self.assertIn('StrictHostKeyChecking=yes', (ROOT / 'scripts/deploy-from-actions.sh').read_text())

    def test_remote_failure_removes_runtime_secrets(self):
        before = set(Path('/dev/shm').glob('arenaops-infra.*'))
        with tempfile.TemporaryDirectory() as directory:
            body = self.runtime(directory).read_text()
            result = subprocess.run(['bash', str(ROOT / 'scripts/remote-apply.sh'), 'sit'],
                                    input=body, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Deployment environment mismatch', result.stderr)
            self.assertNotIn('validation', result.stdout + result.stderr)
        self.assertEqual(set(Path('/dev/shm').glob('arenaops-infra.*')), before)

    def test_bootstrap_create_preserve_roles_and_cleanup(self):
        state = {'exists': False, 'imports': 0, 'assigned': [], 'role_posts': 0}
        roles = [{'id': name, 'name': name} for name in ('manage-users', 'view-users', 'view-realm')]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, status, body=None):
                self.send_response(status); self.end_headers()
                if body is not None: self.wfile.write(json.dumps(body).encode())
            def do_GET(self):
                path = self.path
                if path.endswith('/.well-known/openid-configuration'): self.reply(200, {})
                elif path == '/auth/admin/realms/arena-sit': self.reply(200 if state['exists'] else 404, {})
                elif '/clients?clientId=' in path:
                    name = path.split('=')[-1]; self.reply(200, [{'clientId': name, 'id': name}])
                elif path.endswith('/service-account-user'): self.reply(200, {'id': 'service-user'})
                elif path.endswith('/roles'): self.reply(200, roles)
                elif '/role-mappings/' in path: self.reply(200, state['assigned'])
                else: self.reply(500)
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                if self.path.endswith('/token'): self.reply(401 if state.get('auth_fail') else 200, {'access_token': 'validation-token'})
                elif self.path == '/auth/admin/realms':
                    imported = json.loads(body)
                    state['secret'] = imported['clients'][0]['secret']
                    state['imports'] += 1; state['exists'] = True; self.reply(201)
                elif '/role-mappings/' in self.path:
                    state['assigned'] = json.loads(body); state['role_posts'] += 1; self.reply(204)
                else: self.reply(500)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        before = set(Path('/dev/shm').glob('arenaops-bootstrap-*'))
        try:
            env = dict(os.environ, KC_REALM='arena-sit', KC_BASE_URL=f'http://127.0.0.1:{server.server_port}/auth',
                       KC_ADMIN_USERNAME='validation', KC_ADMIN_PASSWORD='validation', KC_BFF_CLIENT_SECRET='validation-secret')
            command = ['bash', str(ROOT / 'scripts/bootstrap-keycloak.sh'), str(ROOT / 'keycloak/realm/arena-realm.sit.template.json')]
            for _ in range(2):
                result = subprocess.run(command, env=env, check=True, capture_output=True, text=True)
                self.assertNotIn('validation-secret', result.stdout + result.stderr)
            self.assertEqual(state['imports'], 1)
            self.assertEqual(state['role_posts'], 1)
            self.assertEqual(state['secret'], 'validation-secret')
            state['auth_fail'] = True
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('validation-secret', result.stdout + result.stderr)
            env['KC_REALM'] = 'arena'
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('validation-secret', result.stdout + result.stderr)
        finally:
            server.shutdown(); server.server_close(); thread.join()
        self.assertEqual(set(Path('/dev/shm').glob('arenaops-bootstrap-*')), before)

if __name__ == '__main__': unittest.main()
