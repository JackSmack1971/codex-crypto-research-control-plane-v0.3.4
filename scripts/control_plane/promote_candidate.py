from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

from common import digest, load_json, write_new_json
from promotion_gate import evaluate


def missing_evidence_paths(report: dict, root: Path) -> list[str]:
    missing: list[str] = []
    for raw in report.get("evidence") or []:
        if not isinstance(raw, str) or not raw.strip():
            missing.append(str(raw))
            continue
        path_text = raw.split("#", 1)[0]
        path = (root / path_text).resolve() if not Path(path_text).is_absolute() else Path(path_text).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            missing.append(raw)
            continue
        if not path.is_file():
            missing.append(raw)
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hypothesis", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--data-quality", required=True)
    ap.add_argument("--out-dir", default="research/promotions")
    args = ap.parse_args()

    hypothesis = load_json(args.hypothesis)
    validation = load_json(args.validation)
    audit = load_json(args.audit)
    dq = load_json(args.data_quality)
    ok, reasons = evaluate(hypothesis, validation, audit, dq)
    root = Path.cwd().resolve()
    for label, report in (("validation", validation), ("audit", audit)):
        for evidence in missing_evidence_paths(report, root):
            reasons.append(f"{label}.missing_evidence_path:{evidence}")
    ok = not reasons
    if not ok:
        print("BLOCKED")
        for reason in reasons:
            print(reason)
        return 3

    candidate_id = validation["candidate_id"]
    record = {
        "candidate_id": candidate_id,
        "hypothesis_id": hypothesis["hypothesis_id"],
        "decision": "PROMOTED",
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "evidence": [args.hypothesis, args.validation, args.audit, args.data_quality],
    }
    record["content_digest"] = digest(record)
    out = Path(args.out_dir) / f"{candidate_id}.json"
    try:
        write_new_json(out, record)
    except FileExistsError:
        print(f"IMMUTABLE_CONFLICT:{out}")
        return 4
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
