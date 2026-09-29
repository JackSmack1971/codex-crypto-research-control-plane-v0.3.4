from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SUCCESS = "SUCCEEDED"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("probe_report")
    ap.add_argument("--matrix", default="config/daily-capabilities.json")
    ap.add_argument("--out")
    args = ap.parse_args()

    matrix = json.loads(Path(args.matrix).read_text(encoding="utf-8"))
    report = json.loads(Path(args.probe_report).read_text(encoding="utf-8"))
    policies = {item["capability_id"]: item for item in matrix["capabilities"]}
    observed = {item["capability_id"]: item for item in report["capabilities"]}

    core_failures: list[str] = []
    degradations: list[str] = []
    optional_unavailable: list[str] = []
    evaluated: list[dict] = []

    for capability_id, policy in policies.items():
        obs = observed.get(capability_id, {
            "capability_id": capability_id,
            "discovery_status": "UNKNOWN",
            "basic_snapshot_status": "UNKNOWN",
            "access_status": "NOT_PROBED",
            "evidence": ["missing_probe_result"],
        })
        usable = (
            obs.get("discovery_status") == "VERIFIED"
            and obs.get("basic_snapshot_status") == "INCLUDED"
            and obs.get("access_status") == SUCCESS
        )
        requirement = policy["requirement"]
        reason = None if usable else (
            f"{capability_id}:requirement={requirement}:discovery={obs.get('discovery_status')}:"
            f"snapshot={obs.get('basic_snapshot_status')}:access={obs.get('access_status')}"
        )
        if not usable and requirement == "CORE":
            core_failures.append(reason)
        elif not usable and requirement == "ENRICHMENT":
            degradations.append(reason)
        elif not usable:
            optional_unavailable.append(reason)
        evaluated.append({
            "capability_id": capability_id,
            "requirement": requirement,
            "usable": usable,
            "discovery_status": obs.get("discovery_status"),
            "basic_snapshot_status": obs.get("basic_snapshot_status"),
            "access_status": obs.get("access_status"),
        })

    status = "BLOCKED" if core_failures else ("DEGRADED" if degradations else "READY")
    result = {
        "run_id": report["run_id"],
        "attempt_id": report["attempt_id"],
        "status": status,
        "core_failures": core_failures,
        "degradations": degradations,
        "optional_unavailable": optional_unavailable,
        "evaluated_capabilities": evaluated,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            print(f"IMMUTABLE_CONFLICT:{out}")
            return 3
        out.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 2 if status == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
