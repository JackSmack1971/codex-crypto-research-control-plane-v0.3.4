from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True

from common import load_json

REQUIRED_CHECKS = (
    "chronology",
    "leakage",
    "multiple_testing",
    "uncertainty",
    "parameter_stability",
    "regime_dependence",
    "turnover",
    "cost_scenarios",
    "oos",
)


def evaluate(hypothesis: dict, validation: dict, audit: dict, data_quality: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    candidate_id = validation.get("candidate_id")
    if not candidate_id:
        reasons.append("validation.missing_candidate_id")

    hypothesis_id = hypothesis.get("hypothesis_id")
    if hypothesis.get("status") != "REGISTERED":
        reasons.append("hypothesis.not_preregistered")
    if not hypothesis.get("multiple_testing_family"):
        reasons.append("hypothesis.missing_multiple_testing_family")

    if data_quality.get("status") != "PASS":
        reasons.append(f"data_quality.{data_quality.get('status', 'MISSING')}")
    for key in ("run_id", "cutoff", "datasets", "findings"):
        if key not in data_quality or data_quality.get(key) is None:
            reasons.append(f"data_quality.missing:{key}")
    if not isinstance(data_quality.get("datasets"), list) or not data_quality.get("datasets"):
        reasons.append("data_quality.datasets_empty")

    if validation.get("validator") != "statistical-validator":
        reasons.append("validation.invalid_validator_identity")
    if validation.get("verdict") != "PROMOTE":
        reasons.append(f"validation.verdict.{validation.get('verdict', 'MISSING')}")
    if validation.get("hypothesis_id") != hypothesis_id:
        reasons.append("identity.validation_hypothesis_mismatch")
    if not validation.get("evidence"):
        reasons.append("validation.missing_evidence")

    checks = validation.get("checks") or {}
    for key in REQUIRED_CHECKS:
        if checks.get(key) is not True:
            reasons.append(f"validation.check_failed:{key}")

    if audit.get("auditor") != "methodology-auditor":
        reasons.append("audit.invalid_auditor_identity")
    if not isinstance(audit.get("reason_codes"), list):
        reasons.append("audit.invalid_reason_codes")
    if audit.get("status") != "PASS":
        reasons.append(f"audit.status.{audit.get('status', 'MISSING')}")
    if audit.get("subject_type") != "candidate":
        reasons.append("audit.subject_not_candidate")
    if candidate_id and audit.get("subject_id") != candidate_id:
        reasons.append("identity.audit_subject_mismatch")
    if candidate_id and audit.get("candidate_id") != candidate_id:
        reasons.append("identity.audit_candidate_mismatch")
    if audit.get("hypothesis_id") != hypothesis_id:
        reasons.append("identity.audit_hypothesis_mismatch")
    if not audit.get("evidence"):
        reasons.append("audit.missing_evidence")

    return (not reasons, reasons)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hypothesis", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--data-quality", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    hypothesis = load_json(args.hypothesis)
    validation = load_json(args.validation)
    audit = load_json(args.audit)
    dq = load_json(args.data_quality)
    ok, reasons = evaluate(hypothesis, validation, audit, dq)

    decision = {
        "candidate_id": validation.get("candidate_id", ""),
        "decision": "PROMOTED" if ok else "BLOCKED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reason_codes": reasons,
        "evidence": [args.hypothesis, args.validation, args.audit, args.data_quality],
    }
    if args.json:
        import json
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        print(decision["decision"])
        for reason in reasons:
            print(reason)
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
