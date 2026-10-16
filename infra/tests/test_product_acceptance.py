"""Evidence must not claim execution or overwrite an operator's saved result."""
import contextlib
import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]


class ContainerAcceptanceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hine-acceptance-safety-")
        self.root = Path(self.temp.name)
        self.missing_client = self.root / "unavailable-client"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, output):
        return subprocess.run(
            [sys.executable, str(SOURCE / "infra/scripts/check-product.py"),
             "--docker", str(self.missing_client), "--output", str(output)],
            cwd=self.root, capture_output=True, text=True, timeout=20, check=False)

    def test_missing_daemon_client_publishes_private_unexercised_evidence(self):
        output = self.root / "new.json"
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 2)
        report = json.loads(output.read_text())
        self.assertEqual(report["status"], "NOT_EXERCISED")
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertNotIn(str(self.missing_client), output.read_text() + result.stdout + result.stderr)

    def test_existing_evidence_is_never_replaced_on_a_failed_run(self):
        output = self.root / "previous.json"
        original = b'{"saved_operator_result": "keep"}\n'
        output.write_bytes(original)
        output.chmod(0o640)
        before = output.stat()
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(output.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o640)

    def test_existing_evidence_symlink_cannot_overwrite_its_target(self):
        target = self.root / "operator-result.json"
        original = b'{"saved_operator_result": "keep"}\n'
        target.write_bytes(original)
        output = self.root / "new.json"
        output.symlink_to(target)
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(output.is_symlink())
        self.assertEqual(target.read_bytes(), original)

    def test_sigterm_reaps_its_blocked_child_and_publishes_private_failure(self):
        # This dependency only blocks; it never fabricates Docker/product output.
        entered = self.root / "child-pid"
        tool = self.root / "blocking-local-tool"
        tool.write_text(
            f"#!{sys.executable}\nimport os,time\nfrom pathlib import Path\n"
            f"Path({str(entered)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n")
        tool.chmod(0o700)
        output = self.root / "cancelled.json"
        process = subprocess.Popen(
            [sys.executable, str(SOURCE / "infra/scripts/check-product.py"),
             "--docker", str(tool), "--output", str(output)],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not entered.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(entered.exists(), "Runner did not enter its external command.")
            child_pid = int(entered.read_text())
            process.send_signal(signal.SIGTERM)
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, 1)
            report = json.loads(output.read_text())
            self.assertEqual(report["exit_code"], 1)
            self.assertNotEqual(report["status"], "passed")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

    def test_null_ipam_configs_do_not_mask_occupied_subnets(self):
        spec = importlib.util.spec_from_file_location(
            "container_acceptance", SOURCE / "infra/scripts/check-product.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        networks = [
            {"IPAM": {"Config": None}},
            {"IPAM": {"Config": [{"Subnet": "172.29.0.0/24"}]}},
        ]
        # Read-only Docker metadata seam; no product response or daemon success.
        with patch.object(runner, "run", side_effect=[b"none\nbridge\n", json.dumps(networks).encode()]):
            subnets = runner.isolated_subnets("docker", {})
        self.assertEqual(tuple(str(subnet) for subnet in subnets),
                         ("172.29.1.0/24", "172.29.2.0/24"))
