"""Deployment helper behavior: strict configuration parsing, pre-check decisions and credential initialization."""
import importlib.util
import json
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SOURCE / "infra/scripts" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load("deploy-config.py")
checks = load("deploy-checks.py")

VALID = (
    "# comment\n"
    "HINE_DOMAIN=hine.example.org\n"
    "ACME_EMAIL=ops@example.org\n"
    "HINE_EXPECTED_IP=34.80.10.20\n"
    "GCS_BUCKET=\n"
)


class DeployConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "deploy.env"

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, text, kind="deploy"):
        self.path.write_text(text)
        return dict(config.parse(kind, self.path))

    def test_valid_file_fills_default_subnets_and_derives_trusted_proxies(self):
        values = self.parse(VALID)
        self.assertEqual(values["HINE_EDGE_SUBNET"], "172.30.1.0/24")
        self.assertEqual(values["HINE_BACKEND_SUBNET"], "172.30.2.0/24")
        self.assertEqual(values["TRUSTED_PROXY_NETWORKS"], "172.30.1.0/24,172.30.2.0/24")
        self.assertNotIn("GCS_BUCKET", values)

    def test_rejections_name_the_problem(self):
        cases = {
            VALID + "SHELL=1\n": "不允許的欄位",
            VALID + "HINE_DOMAIN=other.example.org\n": "重複",
            VALID.replace("ops@example.org", "ops@example.org;rm"): "不允許的字元",
            VALID.replace("ops@example.org", "'ops@example.org'"): "不允許的字元",
            VALID.replace("ops@example.org", "$EMAIL"): "不允許的字元",
            VALID.replace("HINE_DOMAIN=hine.example.org\n", ""): "HINE_DOMAIN",
            VALID.replace("34.80.10.20", "10.0.0.5"): "HINE_EXPECTED_IP",
            VALID + "HINE_EDGE_SUBNET=172.30.0.0/16\nHINE_BACKEND_SUBNET=172.30.2.0/24\n": "重疊",
            VALID + "HINE_EDGE_SUBNET=8.8.8.0/24\n": "私有",
            VALID + "GCS_CREDENTIALS_FILE=relative/key.json\n": "絕對路徑",
            VALID.replace("hine.example.org", "https://hine.example.org"): "HINE_DOMAIN",
            "export " + VALID: "KEY=VALUE",
        }
        for text, fragment in cases.items():
            with self.subTest(fragment=fragment, text=text):
                with self.assertRaises(config.ConfigError) as caught:
                    self.parse(text)
                self.assertIn(fragment, str(caught.exception))

    def test_active_file_requires_the_release_path_of_its_commit(self):
        active = (
            "HINE_ACTIVE_COMMIT=0123456789ab\n"
            "WEB_ROOT=/srv/hine/releases/0123456789ab/web\n"
            "COMPOSE_PROJECT_NAME=hine-production\n"
            "HINE_SECRET_DIR=/srv/hine/secrets\n"
            "HINE_EDGE_SUBNET=172.30.1.0/24\n"
            "HINE_BACKEND_SUBNET=172.30.2.0/24\n"
            "HINE_RUNTIME_UID=1000\n"
            "HINE_RUNTIME_GID=1000\n"
            "HINE_DEPLOYED_AT=20261017T120000Z\n"
        )
        self.assertEqual(self.parse(active, "active")["WEB_ROOT"], "/srv/hine/releases/0123456789ab/web")
        with self.assertRaises(config.ConfigError):
            self.parse(active.replace("/0123456789ab/web", "/ffffffffffff/web"), "active")

    def test_command_line_reports_errors_without_traceback(self):
        self.path.write_text("NOPE=1\n")
        result = subprocess.run(["python3", str(SOURCE / "infra/scripts/deploy-config.py"), "deploy", str(self.path)],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("deploy-config: ", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


def network(name, subnet, project=None, role=None):
    labels = {}
    if project:
        labels = {"com.docker.compose.project": project, "com.docker.compose.network": role}
    return {"Name": name, "Labels": labels, "IPAM": {"Config": [{"Subnet": subnet}] if subnet else []}}


class DeployChecksTests(unittest.TestCase):
    EDGE, BACKEND = "172.30.1.0/24", "172.30.2.0/24"

    def conflicts(self, *networks):
        return checks.subnet_conflicts(list(networks), "hine-production", self.EDGE, self.BACKEND)

    def test_existing_networks_of_this_deployment_with_same_cidrs_are_ignored(self):
        self.assertEqual(self.conflicts(network("hine-production_edge", self.EDGE, "hine-production", "edge"),
                                        network("hine-production_backend", self.BACKEND, "hine-production", "backend"),
                                        network("bridge", "172.17.0.0/16")), [])

    def test_own_network_with_a_different_cidr_requires_manual_recreation(self):
        problems = self.conflicts(network("hine-production_edge", "172.31.9.0/24", "hine-production", "edge"))
        self.assertEqual(len(problems), 1)
        self.assertIn("hine-production_edge", problems[0])
        self.assertIn("手動移除", problems[0])

    def test_other_overlapping_networks_are_named_and_ipv6_is_ignored(self):
        problems = self.conflicts(network("hine-dev_edge", "172.30.0.0/16", "hine-dev", "edge"),
                                  network("v6only", "fd00:1::/64"))
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("hine-dev_edge" in problem for problem in problems))

    def test_dns_must_exactly_match_expected_ipv4_without_aaaa(self):
        answers = "34.80.10.20 STREAM hine.example.org\n34.80.10.20 DGRAM\n"
        self.assertIsNone(checks.dns_mismatch(answers, "34.80.10.20"))
        self.assertIn("不一致", checks.dns_mismatch(answers + "2001:db8::1 STREAM\n", "34.80.10.20"))
        self.assertIn("不一致", checks.dns_mismatch(answers, "34.80.10.21"))
        self.assertIn("沒有任何", checks.dns_mismatch("", "34.80.10.20"))

    def test_subnets_command_reads_docker_inspect_json(self):
        payload = json.dumps([network("x", "172.30.2.0/25")])
        result = subprocess.run(["python3", str(SOURCE / "infra/scripts/deploy-checks.py"), "subnets",
                                 "hine-production", self.EDGE, self.BACKEND],
                                input=payload, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 3)
        self.assertIn("x", result.stdout)


class InitSecretsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / "infra", self.root / "infra", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(SOURCE / ".env.example", self.root / ".env.example")

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args):
        return subprocess.run(["sh", str(self.root / "infra/scripts/init-secrets.sh"), *args],
                              cwd=self.root, text=True, capture_output=True, check=False)

    def test_absolute_directory_gets_seven_private_files_and_reruns_keep_them(self):
        directory = self.root / "production-secrets"
        result = self.run_script(str(directory), "hine", "hine")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = sorted(path.name for path in directory.iterdir())
        self.assertEqual(names, sorted(["postgres_password", "redis_password", "redis_url", "api_internal_token",
                                        "realtime_internal_token", "database_url", "jwt_signing_key"]))
        before = {name: (directory / name).read_bytes() for name in names}
        for name in names:
            self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(self.run_script(str(directory), "hine", "hine").returncode, 0)
        self.assertEqual(before, {name: (directory / name).read_bytes() for name in names})
        self.assertFalse((self.root / ".secrets").exists())

    def test_relative_directory_is_refused(self):
        result = self.run_script("relative", "hine", "hine")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)
        self.assertFalse((self.root / "relative").exists())

    def test_init_env_creates_once_with_runtime_ids(self):
        script = self.root / "infra/scripts/init-env.sh"
        self.assertEqual(subprocess.run(["sh", str(script), "123", "456"], check=False).returncode, 0)
        text = (self.root / ".env").read_text()
        self.assertIn("HINE_RUNTIME_UID=123\n", text)
        self.assertIn("HINE_RUNTIME_GID=456\n", text)
        self.assertEqual(stat.S_IMODE((self.root / ".env").stat().st_mode), 0o600)
        self.assertEqual(subprocess.run(["sh", str(script), "1", "2"], check=False).returncode, 0)
        self.assertEqual((self.root / ".env").read_text(), text)
        self.assertNotEqual(subprocess.run(["sh", str(script), "1", ""], capture_output=True, check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
