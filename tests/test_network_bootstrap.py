import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NetworkBootstrapTests(unittest.TestCase):
    def harness(self, directory):
        root = Path(directory)
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        docker = bin_dir / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
state_file = Path(os.environ['MOCK_NETWORK_STATE'])
state = json.loads(state_file.read_text()) if state_file.exists() else []
a = sys.argv[1:]
with open(os.environ['MOCK_DOCKER_LOG'], 'a') as log:
    log.write(json.dumps(a) + '\\n')
if a[:2] == ['network', 'inspect']:
    sys.exit(0 if a[2] in state else 1)
if a[:2] == ['network', 'create']:
    if os.environ.get('MOCK_CREATE_MODE') != 'failure':
        state.append(a[-1]); state_file.write_text(json.dumps(state))
    sys.exit(1 if os.environ.get('MOCK_CREATE_MODE') in ('failure', 'race') else 0)
if a == ['compose', 'version']:
    sys.exit(0)
if a and a[0] == 'compose':
    if 'exec' in a and os.environ.get('MOCK_RUNTIME_THEME_UNREADABLE') == 'yes':
        sys.exit(12)
    required = ['arenaops-sit', 'arenaops-prod'] if 'arenaops-edge' in a else [os.environ['MOCK_SELECTED_NETWORK']]
    if not all(network in state for network in required):
        print('Compose ran before external networks existed', file=sys.stderr); sys.exit(10)
    sys.exit(0)
sys.exit(11)
''')
        docker.chmod(0o755)
        return dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'],
                    MOCK_NETWORK_STATE=str(root / 'networks.json'), MOCK_DOCKER_LOG=str(root / 'commands.jsonl'))

    def commands(self, env):
        return [json.loads(line) for line in Path(env['MOCK_DOCKER_LOG']).read_text().splitlines()]

    def test_selected_then_shared_networks_are_idempotent(self):
        for environment in ('sit', 'prod'):
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as directory:
                env = self.harness(directory)
                helper = ['bash', str(ROOT / 'scripts/ensure-networks.sh')]
                subprocess.run(helper + [environment], env=env, check=True, capture_output=True)
                self.assertEqual(json.loads(Path(env['MOCK_NETWORK_STATE']).read_text()), ['arenaops-' + environment])
                for target in (environment, 'edge', 'edge'):
                    subprocess.run(helper + [target], env=env, check=True, capture_output=True)
                commands = self.commands(env)
                creates = [command[-1] for command in commands if command[:2] == ['network', 'create']]
                self.assertEqual(set(creates), {'arenaops-sit', 'arenaops-prod'})
                self.assertEqual(len(creates), 2)
                self.assertFalse(any(command[:2] in (['network', 'rm'], ['network', 'prune']) for command in commands))

    def test_fresh_vps_preparation_creates_only_selected_network(self):
        for environment in ('sit', 'prod'):
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as directory:
                env = self.harness(directory)
                # Exercise real preparation without writing /opt on the test host.
                install = Path(directory) / 'bin/install'
                install.write_text('#!/bin/sh\nexit 0\n'); install.chmod(0o755)
                for _ in range(2):
                    subprocess.run(['bash', str(ROOT / 'scripts/prepare-vps.sh'), environment],
                                   env=env, check=True, capture_output=True)
                self.assertEqual(json.loads(Path(env['MOCK_NETWORK_STATE']).read_text()), ['arenaops-' + environment])
                creates = [command for command in self.commands(env) if command[:2] == ['network', 'create']]
                self.assertEqual(len(creates), 1)

    def test_creation_failure_aborts_and_concurrent_creation_is_verified(self):
        for mode, success in [('failure', False), ('race', True)]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                env = self.harness(directory)
                env['MOCK_CREATE_MODE'] = mode
                result = subprocess.run(['bash', str(ROOT / 'scripts/ensure-networks.sh'), 'sit'],
                                        env=env, capture_output=True)
                self.assertEqual(result.returncode == 0, success)
                self.assertEqual(self.commands(env)[-1], ['network', 'inspect', 'arenaops-sit'])

    def test_fresh_apply_bootstraps_before_every_compose_and_starts_edge_last(self):
        for environment in ('sit', 'prod'):
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as directory:
                env = self.harness(directory)
                root = Path(directory) / environment
                scripts = root / 'scripts'; scripts.mkdir(parents=True)
                docker = root / 'docker'; docker.mkdir()
                edge = root / 'edge'; (edge / 'docker').mkdir(parents=True)
                for name in ('apply-infrastructure.sh', 'ensure-networks.sh', 'normalize-theme-permissions.sh'):
                    shutil.copy2(ROOT / 'scripts' / name, scripts / name)
                shutil.copytree(ROOT / 'keycloak/themes', root / 'keycloak/themes')
                shutil.copy2(ROOT / 'keycloak/theme-assets.txt', root / 'keycloak/theme-assets.txt')
                text = (ROOT / 'scripts/apply-edge.sh').read_text().replace('edge_dir=/opt/arenaops/edge', 'edge_dir="' + str(edge) + '"')
                (scripts / 'apply-edge.sh').write_text(text); (scripts / 'apply-edge.sh').chmod(0o755)
                # Stub credential loading, not the deployment ordering or network helper.
                (scripts / 'common.sh').write_text('''root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
load_environment() {
  export ARENA_ENV="$MOCK_ENVIRONMENT" ARENAOPS_TARGET="$root_dir" CADDY_BIND_IP=127.0.0.1
}
compose() { docker compose -p "arenaops-$ARENA_ENV" "$@"; }
''')
                (scripts / 'bootstrap-keycloak.sh').write_text('#!/bin/sh\nexit 0\n')
                (scripts / 'bootstrap-keycloak.sh').chmod(0o755)
                for name in ('Caddyfile', 'docker-compose.edge.yaml'):
                    (docker / name).write_text('test fixture\n')
                env.update(MOCK_ENVIRONMENT=environment, MOCK_SELECTED_NETWORK='arenaops-' + environment)
                for _ in range(2):
                    subprocess.run(['bash', str(scripts / 'apply-infrastructure.sh')], env=env, check=True, capture_output=True)
                commands = self.commands(env)
                creates = [command for command in commands if command[:2] == ['network', 'create']]
                self.assertEqual(len(creates), 2)
                infra_up = next(i for i, command in enumerate(commands) if 'up' in command and 'arenaops-' + environment in command)
                edge_up = next(i for i, command in enumerate(commands) if 'up' in command and 'arenaops-edge' in command)
                self.assertLess(infra_up, edge_up)
                marker = root / 'state' / (environment + '-infrastructure-applied')
                self.assertTrue(marker.exists())
                marker.unlink()
                env['MOCK_RUNTIME_THEME_UNREADABLE'] = 'yes'
                failed = subprocess.run(['bash', str(scripts / 'apply-infrastructure.sh')], env=env, capture_output=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertFalse(marker.exists())

    def test_workflow_preparation_precedes_remote_apply(self):
        text = (ROOT / 'scripts/deploy-from-actions.sh').read_text()
        self.assertLess(text.index('prepare-vps.sh'), text.index('remote-apply.sh'))
        self.assertIn('ensure-networks.sh', (ROOT / 'scripts/prepare-vps.sh').read_text())
        self.assertIn('Bootstrap VPS networks', (ROOT / '.github/workflows/infrastructure.yaml').read_text())


if __name__ == '__main__':
    unittest.main()
