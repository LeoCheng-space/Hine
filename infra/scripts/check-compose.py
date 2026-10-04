#!/usr/bin/env python3
"""Reject production providers that violate the private single-instance topology."""
import json
import sys
from pathlib import Path


def validate(config):
    services = config.get("services", {})
    for name in ("api", "realtime", "postgres", "redis", "caddy"):
        if name not in services:
            raise ValueError(f"missing actual service: {name}")
    if config.get("networks", {}).get("backend", {}).get("internal") is not True:
        raise ValueError("backend network must be internal")
    for name, service in services.items():
        if service.get("network_mode") or service.get("privileged"):
            raise ValueError(f"{name}: host/shared networking or privileged mode is forbidden")
        if service.get("ports") and name != "caddy":
            raise ValueError(f"{name}: only caddy may publish ports in production")
        if service.get("deploy", {}).get("replicas", 1) != 1 or service.get("scale", 1) != 1:
            raise ValueError(f"{name}: this handoff requires one instance")
        networks = set(service.get("networks", {}))
        if name in ("postgres", "redis", "realtime") and networks != {"backend"}:
            raise ValueError(f"{name}: must join only the private backend network")
        if name in ("api", "caddy") and "backend" not in networks:
            raise ValueError(f"{name}: private backend network missing")
    ports = services["caddy"].get("ports", [])
    observed = {(str(port.get("published")), int(port.get("target", 0)), port.get("protocol", "tcp"))
                for port in ports}
    if observed != {("80", 80, "tcp"), ("443", 443, "tcp")} or len(ports) != 2:
        raise ValueError("caddy must publish only TCP80 and TCP443 to the same target ports")
    api = services["api"]
    if not api.get("image") and not api.get("build"):
        raise ValueError("api provider must supply its real image or build")
    health = api.get("healthcheck", {})
    if health.get("disable") or not health.get("test") or health["test"][0] == "NONE":
        raise ValueError("api provider must include an actual readiness healthcheck")


def main():
    if len(sys.argv) != 2:
        raise ValueError("usage: check-compose.py RESOLVED_COMPOSE_JSON")
    config = json.loads(Path(sys.argv[1]).read_text())
    validate(config)
    api = config["services"]["api"]
    if api.get("build"):
        build = api["build"]
        context = Path(build["context"])
        dockerfile = Path(build.get("dockerfile", "Dockerfile"))
        if not dockerfile.is_absolute():
            dockerfile = context / dockerfile
        if not context.is_dir() or not dockerfile.is_file():
            raise ValueError("api provider build context/Dockerfile is not locally available")
    # A named image's existence is checked by preflight.sh via docker image inspect;
    # do not pull an arbitrary tag or invent a BB implementation here.
    print("Production topology validated; runtime/public checks are separate.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"preflight: {error}", file=sys.stderr)
        sys.exit(1)
