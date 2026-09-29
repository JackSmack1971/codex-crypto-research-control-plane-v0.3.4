from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import canonical_bytes  # noqa: E402
from seal_acquisition import validate as validate_acquisition  # noqa: E402
from validate_artifact import validate as validate_schema  # noqa: E402

SCHEMA = ROOT / "schemas/live_replay_bundle.schema.json"
MATERIALIZED_SCHEMA = ROOT / "schemas/materialized_dataset.schema.json"
ROLES = {"crypto_universe", "crypto_cutoff", "crypto_history", "fx_history", "stock_history", "index_history"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected_object:{path}")
    return value


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_artifact_digest(path: Path) -> str:
    """Digest pipeline meaning while classifying emitted paths as environment provenance."""
    if path.name not in {"pipeline-result.json", "forecast-payload.json"}:
        return sha(path)
    obj = load(path)
    if path.name == "pipeline-result.json":
        obj["artifacts"] = {key: Path(value.replace("\\", "/")).name for key, value in obj["artifacts"].items()}
    else:
        obj["source_artifacts"] = [Path(value.replace("\\", "/")).name for value in obj["source_artifacts"]]
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def inside_repo(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if ROOT.resolve() not in resolved.parents or path.is_symlink() or resolved.is_symlink():
        raise ValueError(f"source_outside_repository_or_symlink:{path}")
    return resolved


def git_commit() -> str | None:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def export(args: argparse.Namespace) -> Path:
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(f"bundle_exists:{out}")
    manifest_path = inside_repo(args.manifest)
    manifest = load(manifest_path)
    errors = validate_acquisition(manifest)
    unsigned_manifest = dict(manifest); recorded_manifest_digest = unsigned_manifest.pop("content_digest", None)
    calculated_manifest_digest = "sha256:" + hashlib.sha256(canonical_bytes(unsigned_manifest)).hexdigest()
    if errors or manifest.get("status") not in {"COMPLETE", "DEGRADED"} or recorded_manifest_digest != calculated_manifest_digest:
        raise ValueError("ineligible_or_unsealed_acquisition:" + ";".join(errors))
    datasets: list[tuple[str, Path, Path, dict[str, Any]]] = []
    for item in manifest["datasets"]:
        if item.get("status") != "COMPLETE" or item.get("materialization_status") != "VERIFIED":
            continue
        role = item["dataset_id"]
        if role not in ROLES:
            continue
        data = inside_repo(ROOT / item["materialized_path"])
        meta = inside_repo(data.with_name(data.stem + ".meta.json"))
        metadata = load(meta)
        schema_errors = validate_schema(metadata, load(MATERIALIZED_SCHEMA))
        rows = sum(bool(line.strip()) for line in data.read_text(encoding="utf-8").splitlines())
        if schema_errors or sha(data) != item["materialized_digest"] or metadata["data_digest"] != sha(data) or rows != item["row_count"] or rows != metadata["row_count"]:
            raise ValueError(f"invalid_materialization:{role}:{';'.join(schema_errors)}")
        for key in ("run_id", "attempt_id", "research_cutoff"):
            if metadata[key] != manifest[key]:
                raise ValueError(f"materialization_identity_mismatch:{role}:{key}")
        datasets.append((role, data, meta, metadata))
    if not {"crypto_universe", "crypto_cutoff", "crypto_history"}.issubset({x[0] for x in datasets}):
        raise ValueError("missing_required_materialization")
    controls = {name: inside_repo(path) for name, path in (("data_quality", args.data_quality), ("capability_evaluation", args.capability_evaluation), ("model_config", args.config))}
    pipeline = inside_repo(args.pipeline_dir)
    result_path = inside_repo(pipeline / "pipeline-result.json")
    pipeline_result = load(result_path)
    if any(pipeline_result.get(k) != manifest[k] for k in ("run_id", "attempt_id", "research_cutoff")):
        raise ValueError("pipeline_identity_mismatch")
    forecast_created_at = load(inside_repo(pipeline / "forecast-payload.json")).get("created_at")
    if forecast_created_at != args.created_at:
        raise ValueError("pipeline_created_at_mismatch")
    expected = {p.name: semantic_artifact_digest(p) for p in sorted(pipeline.iterdir()) if p.is_file() and not p.is_symlink()}
    runtime = load(inside_repo(args.runtime)) if args.runtime else {"recorded": False}
    ledger_identity = ledger_digest = None
    ledger_status = "NOT_RECORDED"
    if args.request_ledger:
        ledger_path = inside_repo(args.request_ledger)
        ledger = load(ledger_path)
        ledger_identity, ledger_digest = ledger.get("ledger_id", ledger.get("attempt_id")), sha(ledger_path)
        ledger_status = "COMPLIANT" if ledger.get("sealed") is True and ledger.get("compliance_status") == "COMPLIANT" else "NOT_RECORDED"

    out.mkdir(parents=True)
    try:
        copied: list[Path] = []
        entries = []
        for role, data, meta, metadata in sorted(datasets):
            data_dst = out / "evidence/datasets" / f"{role}.jsonl"
            meta_dst = out / "evidence/datasets" / f"{role}.meta.json"
            data_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(data, data_dst); shutil.copyfile(meta, meta_dst)
            copied += [data_dst, meta_dst]
            entries.append({"role": role, "data_path": data_dst.relative_to(out).as_posix(), "metadata_path": meta_dst.relative_to(out).as_posix(), "data_digest": sha(data_dst), "metadata_digest": sha(meta_dst), "row_count": metadata["row_count"]})
        control_paths = {}
        for name, source in sorted(controls.items()):
            dst = out / "evidence/controls" / ("daily-model.json" if name == "model_config" else name.replace("_", "-") + ".json")
            dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dst); copied.append(dst)
            control_paths[name] = dst.relative_to(out).as_posix()
        inventory = [{"path": p.relative_to(out).as_posix(), "digest": sha(p), "size": p.stat().st_size} for p in sorted(copied)]
        bundle = {
            "bundle_schema_version": 1, "bundle_id": f"{manifest['attempt_id']}-live-capture-v1", "bundle_digest": "",
            "source_provenance": "LIVE_CAPTURE", "run_id": manifest["run_id"], "attempt_id": manifest["attempt_id"],
            "research_cutoff": manifest["research_cutoff"], "created_at": args.created_at,
            "source_control_plane": {"version": "live-replay-bundle-v1", "git_commit": git_commit()},
            "acquisition": {"acquisition_id": manifest["acquisition_id"], "manifest_digest": sha(manifest_path), "manifest_content_digest": manifest["content_digest"], "status": manifest["status"]},
            "source_live_request_compliance": {"status": ledger_status, "ledger_identity": ledger_identity, "ledger_digest": ledger_digest},
            "replay_provider_compliance": "NOT_TESTED", "datasets": entries, "controls": control_paths,
            "expected_pipeline_digests": expected, "source_pipeline_result_digest": semantic_artifact_digest(result_path), "source_runtime": runtime, "inventory": inventory,
        }
        unsigned = dict(bundle); unsigned.pop("bundle_digest")
        bundle["bundle_digest"] = "sha256:" + hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
        schema_errors = validate_schema(bundle, load(SCHEMA))
        if schema_errors:
            raise ValueError("bundle_schema_invalid:" + ";".join(schema_errors))
        (out / "bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Export sealed live evidence for provider-free deterministic replay.")
    ap.add_argument("--attempt-id", required=True); ap.add_argument("--manifest", type=Path); ap.add_argument("--pipeline-dir", type=Path)
    ap.add_argument("--data-quality", type=Path); ap.add_argument("--capability-evaluation", type=Path); ap.add_argument("--runtime", type=Path); ap.add_argument("--request-ledger", type=Path)
    ap.add_argument("--config", type=Path, default=ROOT / "config/daily-model.json"); ap.add_argument("--created-at", required=True); ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.manifest = args.manifest or ROOT / "research/acquisitions" / f"{args.attempt_id}.json"
    args.pipeline_dir = args.pipeline_dir or ROOT / "research/pipeline" / args.attempt_id
    args.data_quality = args.data_quality or ROOT / "research/runs" / f"{args.attempt_id}.data-quality.json"
    args.capability_evaluation = args.capability_evaluation or ROOT / "research/runs" / f"{args.attempt_id}.capability-evaluation.json"
    try:
        print(export(args)); return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"EXPORT_BLOCKED:{exc}"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
