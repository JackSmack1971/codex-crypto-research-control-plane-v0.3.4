from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FILES = [
    "config/daily-capabilities.json",
    "config/daily-model.json",
    "config/massive-request-policy.json",
    "config/python-runtime-policy.json",
    "scripts/control_plane/bootstrap.ps1",
    "scripts/control_plane/run_python.ps1",
    "scripts/control_plane/bootstrap.sh",
    "scripts/control_plane/run_python.sh",
    "scripts/control_plane/run_tests.py",
    "scripts/control_plane/materialize_mcp_dataset.py",
    "scripts/control_plane/massive_request_gate.py",
    "scripts/control_plane/evaluate_capabilities.py",
    "scripts/control_plane/validate_artifact.py",
    "scripts/pipeline/run_daily_pipeline.py",
    "scripts/control_plane/seal_acquisition.py",
    "scripts/control_plane/freeze_forecast.py",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--attempt-id", required=True)
    ap.add_argument("--research-cutoff", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict] = []
    if sys.version_info < (3, 11):
        errors.append(f"python_too_old:{sys.version.split()[0]}")
    checks.append({"check": "python_runtime", "status": "PASS" if not errors else "FAIL", "detail": sys.executable})

    for rel in REQUIRED_FILES:
        exists = (ROOT / rel).is_file()
        checks.append({"check": f"required_file:{rel}", "status": "PASS" if exists else "FAIL"})
        if not exists:
            errors.append(f"missing:{rel}")

    for rel in ("research/acquisitions", "research/data", "research/pipeline", "research/runs", "research/forecasts"):
        path = ROOT / rel
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / f".preflight-{os.getpid()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append({"check": f"writable:{rel}", "status": "PASS"})
        except OSError as exc:
            errors.append(f"not_writable:{rel}:{exc}")
            checks.append({"check": f"writable:{rel}", "status": "FAIL", "detail": str(exc)})

    git = shutil.which("git")
    if git and (ROOT / ".git").exists():
        try:
            head = subprocess.run(
                [git, "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
            ).stdout.strip()
        except subprocess.CalledProcessError as exc:
            head = None
            warnings.append(f"git_head_unavailable:{exc.returncode}")
        checks.append({"check": "git_checkout", "status": "PASS", "detail": git, "head": head})
    else:
        warnings.append("git_checkout_unavailable:git verification is optional for execution but must be reported")
        checks.append({"check": "git_checkout", "status": "WARN"})

    manifest = ROOT / "CONTROL_PLANE_MANIFEST.json"
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else None
    manifest_digest = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None
    checks.append({
        "check": "source_identity",
        "status": "PASS" if version and manifest_digest else "WARN",
        "version": version,
        "control_plane_manifest_digest": manifest_digest,
    })

    try:
        policy = json.loads((ROOT / "config" / "massive-request-policy.json").read_text(encoding="utf-8"))
        maximum = int(policy["max_requests_per_window"])
        window = float(policy["window_seconds"])
        interval = float(policy["minimum_interval_seconds"])
        if maximum < 1 or window <= 0 or interval + 1e-9 < window / maximum:
            raise ValueError("unsafe pacing values")
        checks.append({
            "check": "massive_request_policy",
            "status": "PASS",
            "detail": f"{maximum} call_api requests/{window:g}s; minimum interval {interval:g}s",
        })
    except Exception as exc:
        errors.append(f"massive_request_policy_invalid:{exc}")
        checks.append({"check": "massive_request_policy", "status": "FAIL", "detail": str(exc)})

    try:
        runtime_policy = json.loads((ROOT / "config" / "python-runtime-policy.json").read_text(encoding="utf-8"))
        if runtime_policy.get("minimum_version") != "3.11":
            raise ValueError("minimum_version_must_be_3.11")
        if runtime_policy.get("allow_repo_local_uv_provision") is not True:
            raise ValueError("repo_local_uv_provision_must_be_enabled")
        if runtime_policy.get("auto_install_scope") != "REPO_LOCAL_ONLY":
            raise ValueError("auto_install_scope_must_be_repo_local_only")
        checks.append({"check": "python_runtime_policy", "status": "PASS", "detail": "Python >=3.11; discovery hardened; bounded repo-local uv provisioning enabled"})
    except Exception as exc:
        errors.append(f"python_runtime_policy_invalid:{exc}")
        checks.append({"check": "python_runtime_policy", "status": "FAIL", "detail": str(exc)})

    prior = sorted((ROOT / "research" / "runs").rglob(f"*{args.run_id}*.json"))
    if prior:
        warnings.append(f"prior_run_artifacts:{len(prior)}:create_new_attempt_do_not_overwrite")
    checks.append({"check": "prior_run_discovery", "status": "WARN" if prior else "PASS", "count": len(prior)})
    warnings.append("massive_effective_access_probe_required:local preflight cannot prove MCP entitlement")

    result = {
        "run_id": args.run_id,
        "attempt_id": args.attempt_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "research_cutoff": args.research_cutoff,
        "status": "BLOCKED" if errors else "READY",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
