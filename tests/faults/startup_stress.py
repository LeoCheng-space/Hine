#!/usr/bin/env python3
"""Issue #26 reproduction: repeatedly start and stop the owned native product stack used by the fault drill
and browser acceptance (PostgreSQL 17, Redis, API, BA, Caddy) and record every startup failure.

Only fixed failure codes and the drill's fixed-category child-exit diagnostic are reported; never logs.
Run on a disposable runner only. Exit 0 when every start succeeded, 1 when any start failed, 2 on bad input.
"""
import argparse
import asyncio
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_drill():
    spec = importlib.util.spec_from_file_location("hine_product_fault_drill", ROOT / "tests/faults/product_fault_drill.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def run(args):
    drill = load_drill()
    evidence = {"environment": {}, "provenance": {}}
    await drill.prerequisites(args, evidence)
    deadline = time.monotonic() + args.minutes * 60
    attempts, failures, durations = 0, [], []
    while time.monotonic() < deadline and attempts < args.max_attempts:
        attempts += 1
        started = time.monotonic()
        try:
            async with asyncio.timeout(120):
                async with drill.Components(args):
                    pass
            durations.append(time.monotonic() - started)
        except drill.DrillFailure as failure:
            failures.append({"attempt": attempts, "failure_code": str(failure), "diagnostic": failure.diagnostic})
        except TimeoutError:
            failures.append({"attempt": attempts, "failure_code": "STARTUP_OR_CLEANUP_TIMEOUT", "diagnostic": None})
        except Exception as failure:  # noqa: BLE001 - class name only; the message may carry private values.
            failures.append({"attempt": attempts, "failure_code": "UNEXPECTED", "failure_type": type(failure).__name__, "diagnostic": None})
    durations.sort()
    return {
        "attempts": attempts,
        "successes": attempts - len(failures),
        "failures": failures,
        "failure_codes": dict(Counter(item["failure_code"] for item in failures)),
        "child_exit_categories": dict(Counter((item["diagnostic"] or {}).get("category") for item in failures if item["diagnostic"])),
        "start_stop_seconds_p50": round(durations[len(durations) // 2], 2) if durations else None,
        "tools": evidence["environment"].get("tools", evidence["environment"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("--postgres-bin", "--redis-server", "--caddy", "--python", "--output"):
        parser.add_argument(name, required=True)
    parser.add_argument("--minutes", type=float, default=20)
    parser.add_argument("--max-attempts", type=int, default=1000)
    args = parser.parse_args()
    args.web_root = None
    output = Path(args.output)
    if output.exists():
        print("STARTUP_STRESS_OUTPUT_EXISTS", file=sys.stderr)
        return 2
    report = asyncio.run(run(args))
    output.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps({key: report[key] for key in ("attempts", "successes", "failure_codes", "child_exit_categories")}))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
