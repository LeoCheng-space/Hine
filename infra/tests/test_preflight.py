"""Catch publicly published private ports and fake/incomplete provider artifacts."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_compose", Path(__file__).resolve().parents[1] / "scripts/check-compose.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ComposeIsolationTests(unittest.TestCase):
    def configuration(self):
        return {
            "services": {
                "postgres": {"image": "postgres:17-alpine", "networks": {"backend": {}}},
                "redis": {"image": "redis:7-alpine", "networks": {"backend": {}}},
                "api": {"image": "approved-api:release", "networks": {"backend": {}},
                        "healthcheck": {"test": ["CMD", "check-ready"]}},
                "realtime": {"build": {"context": "/release"}, "networks": {"backend": {}}},
                "caddy": {"networks": {"backend": {}, "edge": {}},
                          "ports": [{"published": "80", "target": 80}, {"published": "443", "target": 443}]},
            },
            "networks": {"backend": {"internal": True}, "edge": {}},
        }

    def test_private_stack_with_only_caddy_ports_is_accepted(self):
        module.validate(self.configuration())

    def test_loopback_database_publication_is_still_rejected_in_production(self):
        config = self.configuration()
        config["services"]["postgres"]["ports"] = [{"host_ip": "127.0.0.1", "published": "5432", "target": 5432}]
        with self.assertRaises(ValueError):
            module.validate(config)

    def test_host_network_cannot_bypass_port_validation(self):
        config = self.configuration()
        config["services"]["api"]["network_mode"] = "host"
        with self.assertRaises(ValueError):
            module.validate(config)

    def test_database_cannot_join_egress_network(self):
        config = self.configuration()
        config["services"]["redis"]["networks"]["edge"] = {}
        with self.assertRaises(ValueError):
            module.validate(config)

    def test_missing_api_artifact_fails_instead_of_skipping(self):
        config = self.configuration()
        del config["services"]["api"]["image"]
        with self.assertRaises(ValueError):
            module.validate(config)

    def test_missing_api_healthcheck_fails(self):
        config = self.configuration()
        del config["services"]["api"]["healthcheck"]
        with self.assertRaises(ValueError):
            module.validate(config)

    def test_private_network_must_be_internal(self):
        config = self.configuration()
        config["networks"]["backend"]["internal"] = False
        with self.assertRaises(ValueError):
            module.validate(config)


probe_spec = importlib.util.spec_from_file_location("probe_public", Path(__file__).resolve().parents[1] / "scripts/probe-public.py")
probe = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(probe)


class WebSocketProbeTests(unittest.TestCase):
    def test_rfc6455_accept_header_is_required_for_upgrade(self):
        probe.validate_upgrade(
            "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n",
            "dGhlIHNhbXBsZSBub25jZQ==")

    def test_ordinary_http101_without_valid_accept_is_not_a_pass(self):
        with self.assertRaises(ValueError):
            probe.validate_upgrade(
                "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Accept: invalid\r\n\r\n", "dGhlIHNhbXBsZSBub25jZQ==")

    def test_frontend200_cannot_be_mistaken_for_wss_upgrade(self):
        with self.assertRaises(ValueError):
            probe.validate_upgrade("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n",
                                   "dGhlIHNhbXBsZSBub25jZQ==")


if __name__ == "__main__":
    unittest.main()
