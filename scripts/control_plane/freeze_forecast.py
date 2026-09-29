from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from common import digest, load_json, parse_timestamp, require_fields, write_new_json
from massive_request_gate import audit_ledger

REQUIRED = [
    "forecast_id", "run_id", "created_at", "research_cutoff", "target_horizon",
    "universe", "predictions", "source_artifacts"
]


def validate_forecast(obj: dict) -> list[str]:
    errors = require_fields(obj, REQUIRED, "forecast")
    if not isinstance(obj.get("predictions"), list) or not obj.get("predictions"):
        errors.append("forecast.predictions_must_be_nonempty_list")
    if not isinstance(obj.get("source_artifacts"), list) or not obj.get("source_artifacts"):
        errors.append("forecast.source_artifacts_must_be_nonempty_list")
    try:
        created_at = parse_timestamp(obj.get("created_at", ""), "forecast.created_at")
        cutoff = parse_timestamp(obj.get("research_cutoff", ""), "forecast.research_cutoff")
        if cutoff > created_at:
            errors.append("forecast.research_cutoff_after_created_at")
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--request-ledger", required=True)
    ap.add_argument("--methodology-audit", required=True)
    ap.add_argument("--out-dir", default="research/forecasts")
    args = ap.parse_args()

    obj = load_json(args.payload)
    errors = validate_forecast(obj)
    ledger = load_json(args.request_ledger)
    ledger_errors = audit_ledger(ledger)
    if not ledger.get("requests"):
        ledger_errors.append("request_ledger_has_no_provider_calls")
    if ledger.get("status") != "SEALED":
        ledger_errors.append("request_ledger_not_sealed")
    if ledger.get("run_id") != obj.get("run_id"):
        ledger_errors.append("request_ledger_run_id_mismatch")

    audit = load_json(args.methodology_audit)
    if audit.get("subject_type") != "daily_run":
        errors.append("methodology_audit_subject_type_must_be_daily_run")
    if audit.get("status") != "PASS":
        errors.append(f"methodology_audit_not_PASS:{audit.get('status', 'MISSING')}")
    if audit.get("run_id") != obj.get("run_id"):
        errors.append("methodology_audit_run_id_mismatch")
    if audit.get("attempt_id") != ledger.get("attempt_id"):
        errors.append("methodology_audit_attempt_id_mismatch_or_missing")
    errors.extend(f"request_ledger:{item}" for item in ledger_errors)
    if errors:
        print("\n".join(errors))
        return 2

    for evidence_path in (args.request_ledger, args.methodology_audit):
        if evidence_path not in obj["source_artifacts"]:
            obj["source_artifacts"].append(evidence_path)

    obj["content_digest"] = digest(obj)
    out = Path(args.out_dir) / f"{obj['forecast_id']}.json"
    try:
        write_new_json(out, obj)
    except FileExistsError:
        print(f"IMMUTABLE_CONFLICT:{out}")
        return 3
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
