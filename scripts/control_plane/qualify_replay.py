from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_artifact import validate as validate_schema  # noqa: E402

FIXTURE_SCHEMA = ROOT / "schemas" / "replay_fixture.schema.json"
BUNDLE_SCHEMA = ROOT / "schemas" / "live_replay_bundle.schema.json"
MATERIALIZED_SCHEMA = ROOT / "schemas" / "materialized_dataset.schema.json"
DQ_SCHEMA = ROOT / "schemas" / "data_quality_report.schema.json"
CAPS_SCHEMA = ROOT / "schemas" / "capability_evaluation.schema.json"
PIPELINE_SCHEMA = ROOT / "schemas" / "daily_pipeline_result.schema.json"
RESULT_SCHEMA = ROOT / "schemas" / "replay_qualification.schema.json"
DEFAULT_FIXTURE = ROOT / "fixtures" / "replay" / "daily-v1" / "fixture.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_artifact_digest(path: Path) -> str:
    if path.name not in {"pipeline-result.json", "forecast-payload.json"}:
        return _digest(path)
    obj = _load(path)
    if path.name == "pipeline-result.json":
        obj["artifacts"] = {key: Path(value.replace("\\", "/")).name for key, value in obj["artifacts"].items()}
    else:
        obj["source_artifacts"] = [Path(value.replace("\\", "/")).name for value in obj["source_artifacts"]]
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolve(base: Path, value: str) -> Path:
    path = (base / value).resolve()
    if base.resolve() not in path.parents:
        raise ValueError(f"fixture_path_escape:{value}")
    return path


def _schema_check(path: Path, schema_path: Path) -> None:
    errors = validate_schema(_load(path), _load(schema_path))
    if errors:
        raise ValueError(f"schema_invalid:{path.name}:" + ";".join(errors))


def _bundle_digest(obj: dict[str, Any]) -> str:
    unsigned = dict(obj)
    unsigned.pop("bundle_digest", None)
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _verify_bundle(path: Path) -> tuple[dict[str, Any], Path]:
    manifest = path / "bundle.json" if path.is_dir() else path
    _schema_check(manifest, BUNDLE_SCHEMA)
    bundle = _load(manifest)
    if bundle["source_provenance"] != "LIVE_CAPTURE":
        raise ValueError("live_bundle_provenance_mismatch")
    if _bundle_digest(bundle) != bundle["bundle_digest"]:
        raise ValueError("bundle_digest_mismatch")
    base = manifest.parent
    declared = set()
    for entry in bundle["inventory"]:
        item = _resolve(base, entry["path"])
        declared.add(entry["path"])
        if item.is_symlink() or not item.is_file() or _digest(item) != entry["digest"] or item.stat().st_size != entry["size"]:
            raise ValueError(f"bundle_inventory_mismatch:{entry['path']}")
    referenced = {value for value in bundle["controls"].values()}
    referenced.update(value for dataset in bundle["datasets"] for value in (dataset["data_path"], dataset["metadata_path"]))
    if referenced != declared:
        raise ValueError("bundle_inventory_reference_mismatch")
    return bundle, base


def _validate_dataset(base: Path, entry: dict[str, Any], fixture: dict[str, Any]) -> tuple[Path, dict[str, str]]:
    data = _resolve(base, entry["data_path"])
    meta_path = _resolve(base, entry["metadata_path"])
    if _digest(data) != entry["data_digest"]:
        raise ValueError(f"fixture_digest_mismatch:{entry['role']}:data")
    if _digest(meta_path) != entry["metadata_digest"]:
        raise ValueError(f"fixture_digest_mismatch:{entry['role']}:metadata")
    _schema_check(meta_path, MATERIALIZED_SCHEMA)
    meta = _load(meta_path)
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != entry["row_count"] or len(rows) != meta["row_count"]:
        raise ValueError(f"fixture_row_count_mismatch:{entry['role']}")
    if meta["data_digest"] != entry["data_digest"]:
        raise ValueError(f"materialized_digest_mismatch:{entry['role']}")
    if Path(meta["data_path"]).name != data.name:
        raise ValueError(f"materialized_path_mismatch:{entry['role']}")
    for field in ("run_id", "attempt_id", "research_cutoff"):
        if meta[field] != fixture[field]:
            raise ValueError(f"fixture_identity_mismatch:{entry['role']}:{field}")
    keys: set[tuple[str, ...]] = set()
    cutoff = datetime.fromisoformat(fixture["research_cutoff"].replace("Z", "+00:00"))
    for index, row in enumerate(rows):
        key = tuple(str(row.get(field, "")) for field in meta["key_fields"])
        if meta["key_fields"] and ("" in key or key in keys):
            raise ValueError(f"fixture_unique_key_violation:{entry['role']}:{index}")
        keys.add(key)
        timestamp = row.get("t", row.get("t_2"))
        if timestamp is not None and datetime.fromtimestamp(float(timestamp) / 1000, cutoff.tzinfo) > cutoff:
            raise ValueError(f"fixture_cutoff_violation:{entry['role']}:{index}")
    return data, {"data": entry["data_digest"], "metadata": entry["metadata_digest"]}


def _source_identity() -> dict[str, Any]:
    paths = [ROOT / "scripts" / "control_plane" / "qualify_replay.py", ROOT / "scripts" / "pipeline" / "run_daily_pipeline.py", ROOT / "config" / "daily-model.json"]
    identity: dict[str, Any] = {"files": {path.relative_to(ROOT).as_posix(): _digest(path) for path in paths}}
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    identity["git_commit"] = proc.stdout.strip() if proc.returncode == 0 else None
    return identity


def qualify(fixture_path: Path, output: Path, live_bundle: bool = False) -> int:
    stages: list[dict[str, str]] = []
    artifact_digests: dict[str, str] = {}
    fixture_digests: dict[str, Any] = {}
    status = "BLOCKED"
    fixture: dict[str, Any] = {}
    limitation = "Provider access, authentication, entitlement, requests, and replay request compliance were NOT tested; replay made zero live provider requests."
    try:
        if live_bundle:
            fixture, base = _verify_bundle(fixture_path)
            stages.append({"stage": "live_bundle_schema_digest_inventory", "outcome": "PASS"})
            fixture = dict(fixture)
            fixture["data_quality"] = fixture["controls"]["data_quality"]
            fixture["capability_evaluation"] = fixture["controls"]["capability_evaluation"]
            fixture["provenance"] = "LIVE_CAPTURE"
            fixture["fixture_id"] = fixture["bundle_id"]
            fixture["fixture_version"] = fixture["bundle_schema_version"]
        else:
            _schema_check(fixture_path, FIXTURE_SCHEMA)
            fixture = _load(fixture_path)
            base = fixture_path.parent
            stages.append({"stage": "fixture_schema", "outcome": "PASS"})
        paths: dict[str, Path] = {}
        fixture_digests["manifest"] = fixture["bundle_digest"] if live_bundle else _digest(fixture_path)
        for entry in fixture["datasets"]:
            paths[entry["role"]], fixture_digests[entry["role"]] = _validate_dataset(base, entry, fixture)
        stages.append({"stage": "materialization_integrity_unique_keys_cutoff", "outcome": "PASS"})
        dq = _resolve(base, fixture["data_quality"])
        caps = _resolve(base, fixture["capability_evaluation"])
        _schema_check(dq, DQ_SCHEMA)
        _schema_check(caps, CAPS_SCHEMA)
        fixture_digests["data_quality"] = _digest(dq)
        fixture_digests["capability_evaluation"] = _digest(caps)
        stages.append({"stage": "data_quality_and_replay_capability_contracts", "outcome": "PASS"})
        with tempfile.TemporaryDirectory(prefix="offline-replay-") as td:
            out_dir = Path(td) / "pipeline"
            cmd = [sys.executable, "-B", str(ROOT / "scripts" / "pipeline" / "run_daily_pipeline.py"),
                   "--run-id", fixture["run_id"], "--attempt-id", fixture["attempt_id"],
                   "--research-cutoff", fixture["research_cutoff"], "--crypto-universe", str(paths["crypto_universe"]),
                   "--crypto-cutoff", str(paths["crypto_cutoff"]), "--crypto-history", str(paths["crypto_history"]),
                   "--data-quality", str(dq), "--capability-evaluation", str(caps), "--config", str(_resolve(base, fixture["controls"]["model_config"]) if live_bundle else ROOT / "config" / "daily-model.json"),
                   "--created-at", fixture["created_at"], "--out-dir", "pipeline"]
            for role, flag in (("fx_history", "--fx-history"), ("stock_history", "--stock-history"), ("index_history", "--index-history")):
                if role in paths:
                    cmd.extend([flag, str(paths[role])])
            proc = subprocess.run(cmd, cwd=td, text=True, capture_output=True, check=False)
            if proc.returncode:
                raise ValueError(f"pipeline_failed:{proc.stdout.strip()}:{proc.stderr.strip()}")
            produced = out_dir / fixture["attempt_id"]
            result = produced / "pipeline-result.json"
            _schema_check(result, PIPELINE_SCHEMA)
            for path in sorted(produced.iterdir()):
                artifact_digests[path.name] = _semantic_artifact_digest(path) if live_bundle else _digest(path)
            if artifact_digests != fixture["expected_pipeline_digests"]:
                raise ValueError("pipeline_output_digest_mismatch")
        stages.append({"stage": "deterministic_daily_pipeline_and_schema", "outcome": "PASS"})
        stages.append({"stage": "research_risk_and_pre_freeze_payload", "outcome": "PASS"})
        status = "LIVE_CAPTURE_REPLAY_MATCH" if live_bundle else "PASS"
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        stages.append({"stage": "qualification", "outcome": "BLOCKED", "detail": str(exc)})
        if live_bundle and str(exc) == "pipeline_output_digest_mismatch":
            status = "LIVE_CAPTURE_REPLAY_MISMATCH"

    result_obj = {
        "qualification_mode": "LIVE_CAPTURE_REPLAY" if live_bundle else "OFFLINE_REPLAY", "status": status,
        "fixture": {"id": fixture.get("fixture_id", fixture_path.name), "version": fixture.get("fixture_version"), "provenance": fixture.get("provenance", "UNKNOWN")},
        "fixture_digests": fixture_digests, "control_plane_source": _source_identity(),
        "python_runtime": {"executable": sys.executable, "version": platform.python_version(), "implementation": platform.python_implementation(), "platform": platform.platform()},
        "stages": stages, "artifact_digests": artifact_digests,
        "bundle_identity": fixture.get("bundle_id"), "bundle_digest": fixture.get("bundle_digest"),
        "source_run_id": fixture.get("run_id"), "source_attempt_id": fixture.get("attempt_id"),
        "source_artifact_digest": fixture.get("source_pipeline_result_digest"), "replay_artifact_digest": artifact_digests.get("pipeline-result.json"),
        "artifact_comparisons": {name: ("MATCH" if artifact_digests.get(name) == expected else "MISMATCH") for name, expected in fixture.get("expected_pipeline_digests", {}).items()},
        "live_provider_qualified": False, "live_daily_run_pass": False,
        "provider_access_in_replay": "NOT_TESTED", "provider_authentication_in_replay": "NOT_TESTED", "provider_entitlement_in_replay": "NOT_TESTED", "replay_provider_compliance": "NOT_TESTED", "live_provider_requests_in_replay": 0,
        "provider_checks": {key: "NOT_TESTED" for key in ("massive_mcp_visibility", "authentication", "entitlement", "effective_capability_probe", "live_request_ledger", "live_acquisition")},
        "limitations": [limitation] + ([] if live_bundle else ["Synthetic fixed vectors cannot support claims about real market behavior."]),
    }
    schema_errors = validate_schema(result_obj, _load(RESULT_SCHEMA))
    if schema_errors:
        print("RESULT_SCHEMA_INVALID:" + ";".join(schema_errors))
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result_obj, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"{status}:{output}")
    return 0 if status in {"PASS", "LIVE_CAPTURE_REPLAY_MATCH"} else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify the deterministic post-acquisition workflow from a governed offline fixture; never performs provider calls.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    source.add_argument("--bundle", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "research" / "qualifications" / "offline-replay.json")
    args = parser.parse_args()
    return qualify((args.bundle or args.fixture).resolve(), args.out.resolve(), args.bundle is not None)


if __name__ == "__main__":
    raise SystemExit(main())
