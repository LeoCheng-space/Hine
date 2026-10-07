"""Behavioral safety checks; no Docker daemon or product substitutes required."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

SOURCE = Path(__file__).resolve().parents[2]


class OperationsSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / "infra", self.root / "infra")
        shutil.copyfile(SOURCE / ".env.example", self.root / ".env.example")
        shutil.copyfile(SOURCE / "docker-compose.yml", self.root / "docker-compose.yml")

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, name, *args, overrides=None):
        environment = os.environ.copy()
        for key in ("HINE_ENV", "HINE_SECRET_DIR", "WEB_ROOT", "HINE_DOMAIN"):
            environment.pop(key, None)
        environment.update(overrides or {})
        return subprocess.run(["sh", str(self.root / "infra/scripts" / name), *args],
                              cwd=self.root, env=environment, text=True, capture_output=True, check=False)

    def test_init_generates_private_distinct_credentials_and_preserves_reruns(self):
        result = self.run_script("init-dev.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        directory = self.root / ".secrets"
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        names = ("postgres_password", "redis_password", "api_internal_token", "realtime_internal_token")
        before = {name: (directory / name).read_bytes() for name in names}
        self.assertEqual(len(set(before.values())), 4)
        for name, value in before.items():
            self.assertRegex(value.decode().strip(), r"^[0-9a-f]{64}$")
            self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), 0o600)
            self.assertNotIn(value.decode().strip(), result.stdout + result.stderr)
        self.assertEqual((directory / "redis_url").read_text().strip(),
                         "redis://:" + before["redis_password"].decode().strip() + "@redis:6379/0")
        second = self.run_script("init-dev.sh")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(before, {name: (directory / name).read_bytes() for name in names})

    def test_generated_environment_ids_match_the_secret_owner_for_capless_runtime(self):
        result = self.run_script("init-dev.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        environment = dict(line.split("=", 1) for line in (self.root / ".env").read_text().splitlines()
                           if line and not line.startswith("#") and "=" in line)
        for name in ("redis_url", "api_internal_token", "realtime_internal_token"):
            secret = (self.root / ".secrets" / name).stat()
            self.assertEqual(int(environment["HINE_RUNTIME_UID"]), secret.st_uid)
            self.assertEqual(int(environment["HINE_RUNTIME_GID"]), secret.st_gid)

    def test_rerun_preserves_existing_environment_including_explicit_runtime_ids(self):
        original = b"HINE_ENV=production\nHINE_RUNTIME_UID=1234\nHINE_RUNTIME_GID=4321\n"
        (self.root / ".env").write_bytes(original)
        result = self.run_script("init-dev.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / ".env").read_bytes(), original)

    def test_init_rejects_symlink_without_changing_target(self):
        external = self.root / "private-target"
        external.write_text("unchanged")
        (self.root / ".secrets").mkdir(mode=0o700)
        (self.root / ".secrets/postgres_password").symlink_to(external)
        result = self.run_script("init-dev.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(external.read_text(), "unchanged")

    def test_init_rejects_symlinked_environment_file(self):
        external = self.root / "env-target"
        external.write_text("unchanged")
        (self.root / ".env").symlink_to(external)
        self.assertNotEqual(self.run_script("init-dev.sh").returncode, 0)
        self.assertEqual(external.read_text(), "unchanged")
    def test_ambiguous_database_targets_fail_before_changing_existing_credentials(self):
        directory = self.root / ".secrets"
        directory.mkdir(mode=0o700)
        password = directory / "postgres_password"
        password.write_bytes(b"a" * 64 + b"\n")
        password.chmod(0o640)
        before = password.read_bytes(), password.stat().st_mode
        for content in (
            "POSTGRES_DB=hine\nPOSTGRES_DB=other\n",
            "NOTE='example\nPOSTGRES_DB=other\n'\n",
            "NOTE: 'example\nPOSTGRES_DB=other\n'\n",
            "POSTGRES_USER=${UNCONFIRMED_TARGET}\n",
        ):
            with self.subTest(content=content):
                (self.root / ".env").write_text(content)
                result = self.run_script("init-dev.sh")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((password.read_bytes(), password.stat().st_mode), before)
                self.assertFalse((directory / "database_url").exists())
                self.assertFalse((directory / "jwt_signing_key").exists())

    def test_explicit_empty_database_environment_does_not_use_dotenv_target(self):
        (self.root / ".env").write_text("POSTGRES_DB=other\nPOSTGRES_USER=hine\n")
        result = self.run_script("init-dev.sh", overrides={"POSTGRES_DB": "", "POSTGRES_USER": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        target = urlsplit((self.root / ".secrets/database_url").read_text().strip())
        self.assertEqual((target.username, target.path), ("hine", "/hine"))

    def test_literal_quoted_database_target_and_environment_override_stay_consistent(self):
        (self.root / ".env").write_text("POSTGRES_DB='stored'\nPOSTGRES_USER=\"stored_user\"\n")
        result = self.run_script("init-dev.sh", overrides={"POSTGRES_DB": "explicit", "POSTGRES_USER": "explicit_user"})
        self.assertEqual(result.returncode, 0, result.stderr)
        target = urlsplit((self.root / ".secrets/database_url").read_text().strip())
        self.assertEqual((target.username, target.path), ("explicit_user", "/explicit"))


    def test_restore_requires_destructive_flag_before_any_docker_call(self):
        result = self.run_script("restore-postgres.sh", "missing.dump")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--confirm-destructive", result.stderr)

    def test_restore_rejects_missing_archive_even_with_confirmation(self):
        result = self.run_script("restore-postgres.sh", "--confirm-destructive", "missing.dump")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive", result.stderr.lower())

    def test_backup_does_not_overwrite_existing_output(self):
        output = self.root / "important.dump"
        output.write_text("keep")
        result = self.run_script("backup-postgres.sh", str(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(), "keep")

    def test_down_rejects_volume_flags_before_production_prerequisites(self):
        for flag in ("-v", "-v=true", "-vt10", "--volumes", "--volumes=true", "--volume"):
            with self.subTest(flag=flag):
                result = self.run_script("stack.sh", "down", flag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe down argument", result.stderr)

    def test_down_allowlist_accepts_safe_timeouts_and_service_names(self):
        for arguments in (
            ("--timeout", "10", "caddy", "api", "realtime"),
            ("--timeout=10", "--remove-orphans"),
            ("-t10", "postgres", "redis"),
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    ["sh", "-ec", '. "$1"; shift; validate_down_arguments "$@"',
                     str(self.root / "infra/scripts/stack.sh"), str(self.root / "infra/scripts/common.sh"), *arguments],
                    cwd=self.root, text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def production_recovery_environment(self):
        self.assertEqual(self.run_script("init-dev.sh").returncode, 0)
        return {
            "HINE_ENV": "production",
            "COMPOSE_PROJECT_NAME": "hine-recovery-target",
            "HINE_SECRET_DIR": str(self.root / ".secrets"),
            "WEB_ROOT": str(self.root / "missing-frontend-release"),
            "HINE_DOMAIN": "hine.run.place",
            "ACME_EMAIL": "operator@example.org",
        }

    def test_production_recovery_configuration_allows_absent_frontend(self):
        environment = os.environ.copy()
        environment.update(self.production_recovery_environment())
        result = subprocess.run(
            ["sh", "-ec", '. "$1"; configure_stack production',
             str(self.root / "infra/scripts/stack.sh"), str(self.root / "infra/scripts/common.sh")],
            cwd=self.root, env=environment, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_launch_preflight_still_refuses_absent_frontend_before_docker(self):
        result = self.run_script("preflight.sh", "--local", overrides=self.production_recovery_environment())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WEB_ROOT must contain", result.stderr)



if __name__ == "__main__":
    unittest.main()
