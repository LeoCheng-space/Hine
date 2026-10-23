"""Acceptance runners must not fail on startup windows of the real tools they launch."""
import asyncio
import importlib.util
import ssl
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import aiohttp
from aiohttp.abc import AbstractResolver

SOURCE = Path(__file__).resolve().parents[2]
# TLS alert record: handshake failure with alert description internal_error (80), as Caddy
# answers while its listener is up but the internal-CA leaf certificate is still being issued.
INTERNAL_ERROR_ALERT = bytes.fromhex("15030300020250")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, SOURCE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DevToolsPortTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runner = load("browser_acceptance_under_test", "tests/browser/browser_acceptance.py")
        self.temp = tempfile.TemporaryDirectory(prefix="hine-devtools-port-")
        self.port_file = Path(self.temp.name) / "DevToolsActivePort"

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def child(self, script):
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", script, str(self.port_file))
        self.addAsyncCleanup(self.reap, process)
        return process

    @staticmethod
    async def reap(process):
        if process.returncode is None:
            process.kill()
        await process.wait()

    async def test_port_file_created_before_its_content_is_written(self):
        # Chrome creat()s DevToolsActivePort with O_TRUNC and writes it afterwards.
        child = await self.child(
            "import sys,time\nopen(sys.argv[1],'w').close()\ntime.sleep(0.2)\n"
            "open(sys.argv[1],'w').write('41579\\n/devtools/browser/x')\ntime.sleep(30)\n")
        async with asyncio.timeout(10):
            self.assertEqual(await self.runner.devtools_port(self.port_file, child), 41579)

    async def test_browser_exiting_before_publishing_a_port_is_reported(self):
        child = await self.child("raise SystemExit(3)")
        async with asyncio.timeout(10):
            self.assertIsNone(await self.runner.devtools_port(self.port_file, child))


class PinnedToolchainTests(unittest.TestCase):
    # The browser gate attests the exact Playwright it runs, taken from the same file CI installs, so an
    # update PR (e.g. Dependabot) is exercised with its new version instead of being refused before any browser runs.
    def setUp(self):
        self.runner = load("browser_acceptance_under_test", "tests/browser/browser_acceptance.py")
        self.temp = tempfile.TemporaryDirectory(prefix="hine-pin-")
        self.addCleanup(self.temp.cleanup)
        self.requirements = Path(self.temp.name) / "requirements.txt"

    def test_exact_pin_is_the_required_version(self):
        self.requirements.write_text("# browser gate\nplaywright==1.64.0\n")
        self.assertEqual(self.runner.pinned_version("playwright", self.requirements), "1.64.0")

    def test_missing_or_non_exact_pin_is_a_prerequisite_failure(self):
        for contents in ("", "aiohttp==3.14.4\n", "playwright>=1.63\n", "playwright\n"):
            with self.subTest(contents=contents):
                self.requirements.write_text(contents)
                with self.assertRaises(self.runner.PrerequisiteFailure):
                    self.runner.pinned_version("playwright", self.requirements)

    def test_the_shipped_requirements_pin_playwright(self):
        pinned = self.runner.pinned_version("playwright", SOURCE / "tests/browser/requirements.txt")
        self.assertRegex(pinned, r"^[0-9]+\.[0-9]+\.[0-9]+$")


def self_signed(directory, name):
    cert, key = directory / f"{name}.pem", directory / f"{name}.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                    "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
    return cert, key


class VerifiedTlsStatusTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hine-tls-ready-")
        directory = Path(cls.temp.name)
        cls.cert, key = self_signed(directory, "server")
        cls.untrusted, _ = self_signed(directory, "other")
        cls.server_tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        cls.server_tls.load_cert_chain(cls.cert, key)
        cls.drill = load("product_fault_drill_under_test", "tests/faults/product_fault_drill.py")
        # The drill imports aiohttp only after its prerequisites are attested.
        cls.drill.aiohttp = aiohttp

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    async def asyncSetUp(self):
        self.connections = 0
        self.caddy = SimpleNamespace(returncode=None)

    async def serve(self, alerts_before_ready, exit_after_alert=False):
        async def handle(reader, writer):
            self.connections += 1
            try:
                if self.connections <= alerts_before_ready:
                    await reader.read(4096)  # ClientHello
                    writer.write(INTERNAL_ERROR_ALERT)
                    await writer.drain()
                    if exit_after_alert:
                        self.caddy.returncode = 1
                    return
                await writer.start_tls(self.server_tls)
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
                await writer.drain()
            except (ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self.addAsyncCleanup(self.stop, server)
        return f"https://localhost:{server.sockets[0].getsockname()[1]}/"

    @staticmethod
    async def stop(server):
        server.close()
        await server.wait_closed()

    def client(self, cafile):
        connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=str(cafile)), force_close=True,
                                         resolver=StaticResolver())
        return aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5))

    async def test_leaf_certificate_still_being_issued_is_waited_for(self):
        url = await self.serve(alerts_before_ready=2)
        async with self.client(self.cert) as http, asyncio.timeout(10):
            self.assertEqual(await self.drill.verified_tls_status(http, url, self.caddy), 200)
        self.assertEqual(self.connections, 3)

    async def test_untrusted_certificate_is_not_retried(self):
        url = await self.serve(alerts_before_ready=0)
        async with self.client(self.untrusted) as http, asyncio.timeout(10):
            with self.assertRaises(aiohttp.ClientConnectorCertificateError):
                await self.drill.verified_tls_status(http, url, self.caddy)
        self.assertEqual(self.connections, 1)

    async def test_caddy_exiting_while_waiting_is_reported(self):
        url = await self.serve(alerts_before_ready=1000, exit_after_alert=True)
        async with self.client(self.cert) as http, asyncio.timeout(10):
            with self.assertRaises(self.drill.DrillFailure) as raised:
                await self.drill.verified_tls_status(http, url, self.caddy)
        self.assertEqual(str(raised.exception), "OWNED_CADDY_EXITED")
        self.assertEqual(self.connections, 1)


class StaticResolver(AbstractResolver):
    """Resolve the certificate's host name to the loopback test server only."""

    async def resolve(self, host, port=0, family=0):
        return [{"hostname": host, "host": "127.0.0.1", "port": port, "family": 2, "proto": 0, "flags": 0}]

    async def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
