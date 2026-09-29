from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover prior immutable attempt artifacts for one stable daily run id.")
    ap.add_argument("run_id")
    ap.add_argument("--runs-dir", default="research/runs")
    args = ap.parse_args()

    root = Path(args.runs_dir)
    matches = sorted(path for path in root.rglob("*.json") if args.run_id in path.name or args.run_id in path.as_posix())
    attempts: dict[str, list[str]] = {}
    for path in matches:
        name = path.name
        marker = f"{args.run_id}-attempt-"
        if marker in name:
            suffix = name.split(marker, 1)[1]
            attempt_id = marker + suffix.split(".", 1)[0]
        else:
            attempt_id = "legacy-or-unscoped"
        attempts.setdefault(attempt_id, []).append(path.as_posix())
    result = {
        "run_id": args.run_id,
        "prior_artifact_count": len(matches),
        "attempts": [{"attempt_id": key, "artifacts": value} for key, value in sorted(attempts.items())],
        "rule": "Never overwrite a prior terminal attempt. Create a new attempt_id and link/supersede it in the new run record.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
