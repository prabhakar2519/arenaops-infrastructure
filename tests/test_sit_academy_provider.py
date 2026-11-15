"""Verify that the staff provider opt-in only applies to SIT."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class SitAcademyProviderTests(unittest.TestCase):
    def selection(self, environment, installed):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/common.sh', root / 'scripts/common.sh')
            if installed:
                provider = root / 'keycloak/providers/academy-keycloak-provider.jar'
                provider.parent.mkdir(parents=True)
                provider.touch()
            script = 'source "$1/scripts/common.sh"; docker() { printf "%s\\n" "$@"; }; ARENA_ENV="$2"; COMPOSE_PROJECT_NAME=test; compose config'
            return subprocess.run(['bash', '-c', script, '_', str(root), environment], check=True, capture_output=True, text=True).stdout
    def test_sit_with_provider_includes_override(self):
        self.assertIn('docker-compose.sit-academy.yaml', self.selection('sit', True))
    def test_sit_without_provider_preserves_base_configuration(self):
        self.assertNotIn('docker-compose.sit-academy.yaml', self.selection('sit', False))
    def test_prod_and_dev_never_include_override(self):
        for environment in ('prod', 'dev'):
            with self.subTest(environment=environment):
                self.assertNotIn('docker-compose.sit-academy.yaml', self.selection(environment, True))
    def test_override_is_readonly_and_has_no_credentials(self):
        override = (ROOT / 'docker/docker-compose.sit-academy.yaml').read_text()
        self.assertIn('ARENA_ACADEMY_REALM: arena-sit', override)
        self.assertIn('read_only: true', override)
        self.assertIn('create_host_path: false', override)
        self.assertNotIn('SMTP_PASSWORD', override)
