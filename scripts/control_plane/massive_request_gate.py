from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config" / "massive-request-policy.json"
EPSILON = 0.05


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"expected_object:{path}")
    return obj


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    os.replace(tmp, path)


def _load_policy(path: Path) -> dict[str, Any]:
    obj = _read_json(path)
    required = {
        "covered_operation", "max_requests_per_window", "window_seconds",
        "minimum_interval_seconds", "halt_on_rate_limit_warning", "rate_limit_recovery",
    }
    missing = sorted(required - obj.keys())
    if missing:
        raise ValueError(f"policy_missing:{','.join(missing)}")
    if obj["covered_operation"] != "call_api":
        raise ValueError("policy_covered_operation_must_be_call_api")
    maximum = int(obj["max_requests_per_window"])
    window = float(obj["window_seconds"])
    interval = float(obj["minimum_interval_seconds"])
    if maximum < 1 or window <= 0 or interval < 0:
        raise ValueError("invalid_rate_policy_values")
    if interval + 1e-9 < window / maximum:
        raise ValueError("minimum_interval_too_small_for_window_cap")
    if obj["rate_limit_recovery"] != "NEW_ATTEMPT_REQUIRED":
        raise ValueError("unsupported_rate_limit_recovery")
    return {
        "covered_operation": "call_api",
        "max_requests_per_window": maximum,
        "window_seconds": window,
        "minimum_interval_seconds": interval,
        "halt_on_rate_limit_warning": bool(obj["halt_on_rate_limit_warning"]),
        "rate_limit_recovery": obj["rate_limit_recovery"],
    }


@contextmanager
def _locked(ledger_path: Path):
    lock = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    deadline = time.monotonic() + 10.0
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"request_gate_lock_timeout:{lock}")
            time.sleep(0.05)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _next_allowed(ledger: dict[str, Any], now: datetime) -> datetime:
    policy = ledger["policy"]
    starts = sorted(_parse(item["permit_issued_at"]) for item in ledger["requests"])
    target = now
    if starts:
        interval_target = starts[-1].timestamp() + float(policy["minimum_interval_seconds"])
        target = max(target, datetime.fromtimestamp(interval_target, timezone.utc))
    maximum = int(policy["max_requests_per_window"])
    if len(starts) >= maximum:
        window_target = starts[-maximum].timestamp() + float(policy["window_seconds"]) + EPSILON
        target = max(target, datetime.fromtimestamp(window_target, timezone.utc))
    return target


def audit_ledger(ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("status") == "SEALED":
        expected = ledger.get("content_digest")
        unsigned = dict(ledger)
        unsigned["content_digest"] = None
        actual = _digest(unsigned)
        if not expected or expected != actual:
            errors.append("ledger.content_digest_mismatch")
    policy = ledger["policy"]
    requests = ledger.get("requests", [])
    starts = [_parse(item["permit_issued_at"]) for item in requests]
    interval = float(policy["minimum_interval_seconds"])
    maximum = int(policy["max_requests_per_window"])
    window = float(policy["window_seconds"])
    for idx in range(1, len(starts)):
        gap = (starts[idx] - starts[idx - 1]).total_seconds()
        if gap + 1e-6 < interval:
            errors.append(f"request[{idx}].minimum_interval_violation:{gap:.3f}<{interval:.3f}")
    for idx, start in enumerate(starts):
        in_window = sum(1 for prior in starts[: idx + 1] if (start - prior).total_seconds() < window)
        if in_window > maximum:
            errors.append(f"request[{idx}].rolling_window_violation:{in_window}>{maximum}")
    for idx, item in enumerate(requests):
        if item.get("completed_at") is None or item.get("outcome") is None:
            errors.append(f"request[{idx}].incomplete")
        warning = (item.get("warning") or "").upper()
        if item.get("outcome") == "RATE_LIMIT" or "RATE_LIMIT" in warning:
            errors.append(f"request[{idx}].rate_limit_observed")
    if ledger.get("tainted"):
        errors.append("ledger.tainted")
    if ledger.get("halt_required"):
        errors.append("ledger.halt_required")
    return errors


def cmd_init(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    if ledger_path.exists():
        print(f"IMMUTABLE_CONFLICT:{ledger_path}")
        return 3
    policy_path = Path(args.policy)
    try:
        policy = _load_policy(policy_path)
        raw_policy = _read_json(policy_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"REQUEST_GATE_ERROR:{exc}")
        return 2
    ledger = {
        "schema_version": 1,
        "run_id": args.run_id,
        "attempt_id": args.attempt_id,
        "created_at": _iso(_utc_now()),
        "policy_path": policy_path.as_posix(),
        "policy_digest": _digest(raw_policy),
        "policy": policy,
        "status": "OPEN",
        "tainted": False,
        "halt_required": False,
        "requests": [],
        "sealed_at": None,
        "content_digest": None,
    }
    _write_json(ledger_path, ledger)
    print(json.dumps({"ledger": ledger_path.as_posix(), "policy": policy}, sort_keys=True))
    return 0


def _schedule(policy: dict[str, Any], count: int) -> list[float]:
    starts: list[float] = []
    for _ in range(count):
        target = 0.0 if not starts else starts[-1] + float(policy["minimum_interval_seconds"])
        maximum = int(policy["max_requests_per_window"])
        if len(starts) >= maximum:
            target = max(target, starts[-maximum] + float(policy["window_seconds"]) + EPSILON)
        starts.append(target)
    return starts


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        policy = _load_policy(Path(args.policy))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"REQUEST_GATE_ERROR:{exc}")
        return 2
    starts = _schedule(policy, args.request_count)
    result = {
        "request_count": args.request_count,
        "policy": policy,
        "minimum_start_span_seconds": 0.0 if not starts else round(starts[-1], 3),
        "scheduled_start_offsets_seconds": [round(value, 3) for value in starts],
    }
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_permit(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    try:
        params = json.loads(args.params_json)
        if not isinstance(params, dict):
            raise ValueError("params_json_must_be_object")
        with _locked(ledger_path):
            ledger = _read_json(ledger_path)
            if ledger.get("status") == "SEALED":
                print("REQUEST_GATE_SEALED")
                return 4
            if ledger.get("tainted") or ledger.get("halt_required") or ledger.get("status") == "TAINTED":
                print("REQUEST_GATE_TAINTED:NEW_ATTEMPT_REQUIRED")
                return 4
            if ledger.get("requests") and ledger["requests"][-1].get("completed_at") is None:
                print("REQUEST_GATE_OUTSTANDING_PERMIT:COMPLETE_PREVIOUS_REQUEST_FIRST")
                return 4
            target = _next_allowed(ledger, _utc_now())
            delay = (target - _utc_now()).total_seconds()
            if delay > 0:
                time.sleep(delay)
            issued = _utc_now()
            sequence = len(ledger["requests"]) + 1
            permit_id = f"req-{sequence:04d}-{uuid.uuid4().hex[:12]}"
            entry = {
                "sequence": sequence,
                "permit_id": permit_id,
                "operation": "call_api",
                "label": args.label,
                "endpoint_path": args.endpoint_path,
                "params_digest": _digest(params),
                "permit_issued_at": _iso(issued),
                "completed_at": None,
                "outcome": None,
                "warning": None,
                "request_id": None,
                "row_count": None,
                "pagination_terminal": None,
                "next_url_present": None,
            }
            ledger["requests"].append(entry)
            _write_json(ledger_path, ledger)
        print(json.dumps({"permit_id": permit_id, "permit_issued_at": entry["permit_issued_at"], "endpoint_path": args.endpoint_path}, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"REQUEST_GATE_ERROR:{exc}")
        return 2


def _bool_or_none(value: str | None) -> bool | None:
    if value is None or value.upper() == "UNKNOWN":
        return None
    if value.upper() == "TRUE":
        return True
    if value.upper() == "FALSE":
        return False
    raise ValueError(f"expected_TRUE_FALSE_UNKNOWN:{value}")


def cmd_complete(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    try:
        with _locked(ledger_path):
            ledger = _read_json(ledger_path)
            match = next((item for item in ledger["requests"] if item["permit_id"] == args.permit_id), None)
            if match is None:
                raise ValueError(f"unknown_permit:{args.permit_id}")
            if match.get("completed_at") is not None:
                raise ValueError(f"permit_already_completed:{args.permit_id}")
            warning = args.warning
            outcome = args.outcome
            rate_limited = outcome == "RATE_LIMIT" or (warning is not None and "RATE_LIMIT" in warning.upper())
            match["completed_at"] = _iso(_utc_now())
            match["outcome"] = "RATE_LIMIT" if rate_limited else outcome
            match["warning"] = warning
            match["request_id"] = args.request_id
            match["row_count"] = args.row_count
            match["pagination_terminal"] = _bool_or_none(args.pagination_terminal)
            match["next_url_present"] = _bool_or_none(args.next_url_present)
            if rate_limited and ledger["policy"]["halt_on_rate_limit_warning"]:
                ledger["tainted"] = True
                ledger["halt_required"] = True
                ledger["status"] = "TAINTED"
            _write_json(ledger_path, ledger)
        result = {"permit_id": args.permit_id, "outcome": match["outcome"], "ledger_status": ledger["status"], "halt_required": ledger["halt_required"]}
        print(json.dumps(result, sort_keys=True))
        return 4 if rate_limited else 0
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"REQUEST_GATE_ERROR:{exc}")
        return 2


def cmd_audit(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    try:
        with _locked(ledger_path):
            ledger = _read_json(ledger_path)
            errors = audit_ledger(ledger)
            if errors:
                print(json.dumps({"status": "FAIL", "errors": errors}, sort_keys=True))
                return 2
            if args.seal:
                ledger["status"] = "SEALED"
                ledger["sealed_at"] = _iso(_utc_now())
                unsigned = dict(ledger)
                unsigned["content_digest"] = None
                ledger["content_digest"] = _digest(unsigned)
                _write_json(ledger_path, ledger)
        print(json.dumps({"status": "PASS", "sealed": bool(args.seal), "request_count": len(ledger["requests"]), "content_digest": ledger.get("content_digest")}, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"REQUEST_GATE_ERROR:{exc}")
        return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic pacing/compliance gate for provider-facing Massive MCP call_api requests.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("--run-id", required=True)
    p.add_argument("--attempt-id", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--policy", default=str(DEFAULT_POLICY))
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan")
    p.add_argument("--request-count", type=int, required=True)
    p.add_argument("--policy", default=str(DEFAULT_POLICY))
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("permit")
    p.add_argument("--ledger", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--endpoint-path", required=True)
    p.add_argument("--params-json", default="{}")
    p.set_defaults(func=cmd_permit)

    p = sub.add_parser("complete")
    p.add_argument("--ledger", required=True)
    p.add_argument("--permit-id", required=True)
    p.add_argument("--outcome", choices=["SUCCESS", "RATE_LIMIT", "NOT_ENTITLED", "ERROR"], required=True)
    p.add_argument("--warning")
    p.add_argument("--request-id")
    p.add_argument("--row-count", type=int)
    p.add_argument("--pagination-terminal", choices=["TRUE", "FALSE", "UNKNOWN"])
    p.add_argument("--next-url-present", choices=["TRUE", "FALSE", "UNKNOWN"])
    p.set_defaults(func=cmd_complete)

    p = sub.add_parser("audit")
    p.add_argument("--ledger", required=True)
    p.add_argument("--seal", action="store_true")
    p.set_defaults(func=cmd_audit)

    args = ap.parse_args()
    if getattr(args, "request_count", 0) < 0:
        print("REQUEST_GATE_ERROR:request_count_must_be_nonnegative")
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
