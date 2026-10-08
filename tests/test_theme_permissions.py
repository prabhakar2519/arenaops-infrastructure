from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ThemePermissionTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory) / 'sit'
        scripts = root / 'scripts'; scripts.mkdir(parents=True)
        shutil.copy2(ROOT / 'scripts/normalize-theme-permissions.sh', scripts)
        shutil.copytree(ROOT / 'keycloak/themes', root / 'keycloak/themes')
        shutil.copy2(ROOT / 'keycloak/theme-assets.txt', root / 'keycloak/theme-assets.txt')
        themes = root / 'keycloak/themes'
        for path in [themes, *themes.rglob('*')]:
            path.chmod(0o700 if path.is_dir() else 0o600)
        secret = root / 'keycloak/realm/runtime-secret.env'
        secret.parent.mkdir(); secret.parent.chmod(0o700); secret.write_text('private fixture'); secret.chmod(0o600)
        return root, themes, secret

    def run_helper(self, root):
        return subprocess.run(['bash', str(root / 'scripts/normalize-theme-permissions.sh')],
                              capture_output=True, text=True)

    def test_normalization_is_idempotent_preserves_content_and_secret_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, themes, secret = self.fixture(directory)
            before = {str(p.relative_to(themes)): p.read_bytes() for p in themes.rglob('*') if p.is_file()}
            for _ in range(2):
                result = self.run_helper(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                for path in [themes, *themes.rglob('*')]:
                    self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)
                self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
                self.assertEqual(secret.parent.stat().st_mode & 0o777, 0o700)  # no parent chmod
                self.assertEqual(before, {str(p.relative_to(themes)): p.read_bytes() for p in themes.rglob('*') if p.is_file()})

    def test_missing_assets_symlinks_and_unlisted_files_fail_before_chmod(self):
        for fault in ('missing', 'symlink', 'unlisted'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root, themes, secret = self.fixture(directory)
                if fault == 'missing': (themes / 'arena-login/login/login.ftl').unlink()
                elif fault == 'symlink': (themes / 'outside-link').symlink_to(secret)
                else: (themes / 'unexpected-secret.env').write_text('private fixture')
                self.assertNotEqual(self.run_helper(root).returncode, 0)
                self.assertEqual(themes.stat().st_mode & 0o777, 0o700)
                self.assertEqual(secret.stat().st_mode & 0o777, 0o600)

    def test_asset_manifest_matches_repository_theme_tree(self):
        listed = set((ROOT / 'keycloak/theme-assets.txt').read_text().splitlines())
        actual = {str(path.relative_to(ROOT / 'keycloak/themes')) for path in (ROOT / 'keycloak/themes').rglob('*') if path.is_file()}
        self.assertEqual(listed, actual)

    def test_apply_checks_runtime_user_before_realm_bootstrap(self):
        script = (ROOT / 'scripts/apply-infrastructure.sh').read_text()
        self.assertLess(script.index('normalize-theme-permissions.sh'), script.index('compose up'))
        self.assertLess(script.index('compose exec -T keycloak'), script.index('bootstrap-keycloak.sh'))
        self.assertIn('test -r /opt/keycloak/themes/arena-login/login/theme.properties', script)
        self.assertIn('test -r /opt/keycloak/themes/arena-login/login/login.ftl', script)
        self.assertNotIn('--user root', script)
        self.assertIn('umask 077', script)
        self.assertIn('compose up -d --no-deps --force-recreate --wait --wait-timeout 360 keycloak', script)


if __name__ == '__main__':
    unittest.main()
