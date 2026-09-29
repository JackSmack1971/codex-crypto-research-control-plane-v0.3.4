from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
from common import digest, load_json, parse_timestamp, require_fields, write_new_json

REQUIRED = [
    "acquisition_id", "run_id", "attempt_id", "created_at", "research_cutoff", "source",
    "server_url", "status", "datasets", "errors", "limitations",
]
DATASET_REQUIRED = [
    "dataset_id", "capability_id", "requirement", "market", "purpose", "method", "endpoint_path", "params",
    "retrieved_at", "retrieval_time_source", "as_of", "discovery_status", "basic_snapshot_status",
    "access_status", "pagination_complete", "row_count", "materialization_status", "status",
]
VALID_OVERALL = {"COMPLETE", "DEGRADED", "PARTIAL", "BLOCKED"}
VALID_DATASET = {"COMPLETE", "PARTIAL", "ACCESS_DENIED", "ERROR", "UNAVAILABLE", "SKIPPED"}
VALID_REQUIREMENT = {"CORE", "ENRICHMENT", "EVENT_OPTIONAL"}


def _parse_as_of(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: invalid as_of value")
    value = value.strip()
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        return parse_timestamp(value, label)
    except ValueError as exc:
        raise ValueError(f"{label}: invalid date/date-time: {value!r}") from exc


def _complete_dataset_errors(dataset: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if dataset.get("status") != "COMPLETE":
        errors.append(f"{label}.not_complete")
    if dataset.get("discovery_status") != "VERIFIED":
        errors.append(f"{label}.discovery_not_VERIFIED")
    if dataset.get("basic_snapshot_status") != "INCLUDED":
        errors.append(f"{label}.basic_snapshot_not_INCLUDED")
    if dataset.get("access_status") != "SUCCEEDED":
        errors.append(f"{label}.access_not_SUCCEEDED")
    if dataset.get("pagination_complete") is not True:
        errors.append(f"{label}.pagination_incomplete")
    if dataset.get("materialization_status") != "VERIFIED":
        errors.append(f"{label}.materialization_not_VERIFIED")
    if dataset.get("materialized_row_count") != dataset.get("row_count"):
        errors.append(f"{label}.materialized_row_count_mismatch")
    digest_value = dataset.get("materialized_digest")
    if not isinstance(digest_value, str) or not digest_value.startswith("sha256:"):
        errors.append(f"{label}.materialized_digest_missing")
    if not dataset.get("materialized_path"):
        errors.append(f"{label}.materialized_path_missing")
    if dataset.get("retrieval_time_source") == "APPROXIMATE":
        errors.append(f"{label}.retrieval_time_approximate")
    return errors


def validate(obj: dict[str, Any]) -> list[str]:
    errors = require_fields(obj, REQUIRED, "acquisition")
    if obj.get("source") != "massive_mcp":
        errors.append("acquisition.source_must_be_massive_mcp")
    if obj.get("server_url") != "https://mcp.massive.com/":
        errors.append("acquisition.server_url_must_be_official_massive_mcp")
    if obj.get("status") not in VALID_OVERALL:
        errors.append("acquisition.invalid_status")
    if not isinstance(obj.get("errors"), list):
        errors.append("acquisition.errors_must_be_list")
    if not isinstance(obj.get("limitations"), list):
        errors.append("acquisition.limitations_must_be_list")

    datasets = obj.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        errors.append("acquisition.datasets_must_be_nonempty_list")
        return errors

    try:
        created_at = parse_timestamp(obj.get("created_at", ""), "acquisition.created_at")
        cutoff = parse_timestamp(obj.get("research_cutoff", ""), "acquisition.research_cutoff")
    except ValueError as exc:
        errors.append(str(exc))
        created_at = cutoff = None

    seen: set[str] = set()
    for idx, dataset in enumerate(datasets):
        label = f"dataset[{idx}]"
        if not isinstance(dataset, dict):
            errors.append(f"{label}.must_be_object")
            continue
        errors.extend(require_fields(dataset, DATASET_REQUIRED, label))
        dataset_id = dataset.get("dataset_id")
        if dataset_id in seen:
            errors.append(f"{label}.duplicate_dataset_id:{dataset_id}")
        elif isinstance(dataset_id, str):
            seen.add(dataset_id)
        if dataset.get("requirement") not in VALID_REQUIREMENT:
            errors.append(f"{label}.invalid_requirement")
        if dataset.get("method") != "GET":
            errors.append(f"{label}.method_must_be_GET")
        path = dataset.get("endpoint_path")
        if not isinstance(path, str) or not path.startswith("/"):
            errors.append(f"{label}.endpoint_path_must_start_with_slash")
        if not isinstance(dataset.get("params"), dict):
            errors.append(f"{label}.params_must_be_object")
        if dataset.get("basic_snapshot_status") not in {"INCLUDED", "UNKNOWN"}:
            errors.append(f"{label}.invalid_basic_snapshot_status")
        if dataset.get("discovery_status") not in {"VERIFIED", "UNKNOWN"}:
            errors.append(f"{label}.invalid_discovery_status")
        if dataset.get("access_status") not in {"SUCCEEDED", "NOT_ENTITLED", "UNAVAILABLE", "ERROR"}:
            errors.append(f"{label}.invalid_access_status")
        if not isinstance(dataset.get("pagination_complete"), bool):
            errors.append(f"{label}.pagination_complete_must_be_boolean")
        if not isinstance(dataset.get("row_count"), int) or dataset.get("row_count", -1) < 0:
            errors.append(f"{label}.row_count_must_be_nonnegative_integer")
        if dataset.get("status") not in VALID_DATASET:
            errors.append(f"{label}.invalid_status")
        try:
            retrieved_at = parse_timestamp(dataset.get("retrieved_at", ""), f"{label}.retrieved_at")
            if created_at is not None and retrieved_at > created_at:
                errors.append(f"{label}.retrieved_after_manifest_created")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            as_of = _parse_as_of(dataset.get("as_of"), f"{label}.as_of")
            if cutoff is not None and as_of > cutoff:
                errors.append(f"{label}.as_of_after_research_cutoff")
        except ValueError as exc:
            errors.append(str(exc))

    overall = obj.get("status")
    if overall in {"COMPLETE", "DEGRADED"}:
        for idx, dataset in enumerate(datasets):
            if not isinstance(dataset, dict):
                continue
            requirement = dataset.get("requirement")
            label = f"dataset[{idx}]"
            if requirement == "CORE":
                errors.extend(_complete_dataset_errors(dataset, label))
            elif overall == "COMPLETE" and requirement == "ENRICHMENT":
                errors.extend(_complete_dataset_errors(dataset, label))
        if obj.get("errors"):
            errors.append(f"acquisition.{overall}_cannot_have_errors")
    if overall == "COMPLETE":
        for idx, dataset in enumerate(datasets):
            if isinstance(dataset, dict) and dataset.get("requirement") == "ENRICHMENT" and dataset.get("status") != "COMPLETE":
                errors.append(f"dataset[{idx}].enrichment_not_complete_in_COMPLETE_acquisition")
    if overall == "DEGRADED":
        has_degradation = any(
            isinstance(dataset, dict)
            and dataset.get("requirement") == "ENRICHMENT"
            and dataset.get("status") != "COMPLETE"
            for dataset in datasets
        ) or bool(obj.get("limitations"))
        if not has_degradation:
            errors.append("acquisition.DEGRADED_without_recorded_degradation")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--out-dir", default="research/acquisitions")
    args = ap.parse_args()

    obj = load_json(args.payload)
    errors = validate(obj)
    if errors:
        print("\n".join(errors))
        return 2

    obj["content_digest"] = digest(obj)
    out = Path(args.out_dir) / f"{obj['acquisition_id']}.json"
    try:
        write_new_json(out, obj)
    except FileExistsError:
        print(f"IMMUTABLE_CONFLICT:{out}")
        return 3
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
