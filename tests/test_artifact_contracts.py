import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "control_plane"


def run_script(name, *args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, args)],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def assert_schema_shape(testcase, obj, schema_name):
    schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    testcase.assertTrue(set(schema.get("required", [])).issubset(obj), obj)
    testcase.assertTrue(set(obj).issubset(schema.get("properties", {})), obj)


def write_freeze_evidence(root: Path, run_id: str, attempt_id: str) -> tuple[Path, Path]:
    ledger = root / "request-ledger.json"
    init = run_script(
        "massive_request_gate.py", "init", "--run-id", run_id, "--attempt-id", attempt_id,
        "--ledger", ledger, cwd=ROOT,
    )
    if init.returncode != 0:
        raise AssertionError(init.stdout + init.stderr)
    permit = run_script(
        "massive_request_gate.py", "permit", "--ledger", ledger, "--label", "fixture",
        "--endpoint-path", "/v2/aggs/grouped/locale/global/market/crypto/2026-09-28",
        "--params-json", "{}", cwd=ROOT,
    )
    if permit.returncode != 0:
        raise AssertionError(permit.stdout + permit.stderr)
    permit_id = json.loads(permit.stdout)["permit_id"]
    complete = run_script(
        "massive_request_gate.py", "complete", "--ledger", ledger, "--permit-id", permit_id,
        "--outcome", "SUCCESS", "--row-count", "1", "--pagination-terminal", "TRUE",
        "--next-url-present", "FALSE", cwd=ROOT,
    )
    if complete.returncode != 0:
        raise AssertionError(complete.stdout + complete.stderr)
    sealed = run_script("massive_request_gate.py", "audit", "--ledger", ledger, "--seal", cwd=ROOT)
    if sealed.returncode != 0:
        raise AssertionError(sealed.stdout + sealed.stderr)
    audit = root / "audit.json"
    audit.write_text(json.dumps({
        "subject_type": "daily_run",
        "subject_id": run_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "auditor": "methodology-auditor",
        "status": "PASS",
        "reason_codes": [],
        "evidence": ["fixture"],
    }), encoding="utf-8")
    return ledger, audit


class ArtifactContractTests(unittest.TestCase):
    def test_registered_hypothesis_matches_persisted_schema_shape_and_is_immutable(self):
        payload = json.loads((ROOT / "examples" / "hypothesis.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "hypothesis.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            out_dir = td / "registry"
            first = run_script("register_hypothesis.py", src, "--out-dir", out_dir, cwd=ROOT)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            stored_path = out_dir / f"{payload['hypothesis_id']}.json"
            before = stored_path.read_bytes()
            stored = json.loads(before)
            self.assertIn("content_digest", stored)
            assert_schema_shape(self, stored, "hypothesis.schema.json")
            second = run_script("register_hypothesis.py", src, "--out-dir", out_dir, cwd=ROOT)
            self.assertEqual(3, second.returncode, second.stdout + second.stderr)
            self.assertEqual(before, stored_path.read_bytes())

    def test_frozen_forecast_matches_persisted_schema_shape_and_rejects_rewrite(self):
        payload = json.loads((ROOT / "examples" / "forecast.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "forecast.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            out_dir = td / "forecasts"
            ledger, audit = write_freeze_evidence(td, payload["run_id"], "attempt-fixture")
            args = (src, "--request-ledger", ledger, "--methodology-audit", audit, "--out-dir", out_dir)
            first = run_script("freeze_forecast.py", *args, cwd=ROOT)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            stored_path = out_dir / f"{payload['forecast_id']}.json"
            before = stored_path.read_bytes()
            stored = json.loads(before)
            self.assertIn("content_digest", stored)
            assert_schema_shape(self, stored, "forecast_record.schema.json")
            second = run_script("freeze_forecast.py", *args, cwd=ROOT)
            self.assertEqual(3, second.returncode, second.stdout + second.stderr)
            self.assertEqual(before, stored_path.read_bytes())

    def test_forecast_rejects_cutoff_after_creation(self):
        payload = json.loads((ROOT / "examples" / "forecast.example.json").read_text(encoding="utf-8"))
        payload["research_cutoff"] = "2026-09-29T00:00:00Z"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "forecast.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            ledger, audit = write_freeze_evidence(td, payload["run_id"], "attempt-fixture")
            proc = run_script(
                "freeze_forecast.py", src, "--request-ledger", ledger, "--methodology-audit", audit,
                "--out-dir", td / "forecasts", cwd=ROOT,
            )
            self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("research_cutoff_after_created_at", proc.stdout)

    def test_forecast_rejects_tainted_request_ledger(self):
        payload = json.loads((ROOT / "examples" / "forecast.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "forecast.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            ledger = td / "request-ledger.json"
            init = run_script("massive_request_gate.py", "init", "--run-id", payload["run_id"], "--attempt-id", "attempt-tainted", "--ledger", ledger, cwd=ROOT)
            self.assertEqual(0, init.returncode, init.stdout + init.stderr)
            permit = run_script("massive_request_gate.py", "permit", "--ledger", ledger, "--label", "fixture", "--endpoint-path", "/v2/test", cwd=ROOT)
            self.assertEqual(0, permit.returncode, permit.stdout + permit.stderr)
            permit_id = json.loads(permit.stdout)["permit_id"]
            complete = run_script("massive_request_gate.py", "complete", "--ledger", ledger, "--permit-id", permit_id, "--outcome", "RATE_LIMIT", cwd=ROOT)
            self.assertEqual(4, complete.returncode, complete.stdout + complete.stderr)
            audit = td / "audit.json"
            audit.write_text(json.dumps({"subject_type": "daily_run", "subject_id": payload["run_id"], "run_id": payload["run_id"], "attempt_id": "attempt-tainted", "auditor": "methodology-auditor", "status": "PASS", "reason_codes": [], "evidence": ["fixture"]}), encoding="utf-8")
            proc = run_script("freeze_forecast.py", src, "--request-ledger", ledger, "--methodology-audit", audit, "--out-dir", td / "forecasts", cwd=ROOT)
            self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("request_ledger", proc.stdout)

    def test_promotion_record_matches_schema_shape_and_is_immutable(self):
        h = {"hypothesis_id": "h1", "status": "REGISTERED", "multiple_testing_family": "fam"}
        v = {
            "candidate_id": "c1",
            "hypothesis_id": "h1",
            "validator": "statistical-validator",
            "verdict": "PROMOTE",
            "checks": {key: True for key in (
                "chronology", "leakage", "multiple_testing", "uncertainty",
                "parameter_stability", "regime_dependence", "turnover", "cost_scenarios", "oos"
            )},
            "evidence": ["validation-details.json"],
        }
        a = {
            "subject_type": "candidate",
            "subject_id": "c1",
            "candidate_id": "c1",
            "hypothesis_id": "h1",
            "auditor": "methodology-auditor",
            "status": "PASS",
            "reason_codes": [],
            "evidence": ["audit-details.json"],
        }
        dq = {
            "run_id": "r1",
            "status": "PASS",
            "cutoff": "2026-09-28T23:00:00Z",
            "datasets": ["crypto_grouped"],
            "findings": [],
        }
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            paths = {}
            for name, obj in (("h", h), ("v", v), ("a", a), ("dq", dq)):
                p = td / f"{name}.json"
                p.write_text(json.dumps(obj), encoding="utf-8")
                paths[name] = p
            (td / "validation-details.json").write_text("{}", encoding="utf-8")
            (td / "audit-details.json").write_text("{}", encoding="utf-8")
            out_dir = td / "promotions"
            args = (
                "--hypothesis", paths["h"], "--validation", paths["v"],
                "--audit", paths["a"], "--data-quality", paths["dq"],
                "--out-dir", out_dir,
            )
            first = run_script("promote_candidate.py", *args, cwd=td)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            stored_path = out_dir / "c1.json"
            before = stored_path.read_bytes()
            stored = json.loads(before)
            assert_schema_shape(self, stored, "promotion_decision.schema.json")
            second = run_script("promote_candidate.py", *args, cwd=td)
            self.assertEqual(4, second.returncode, second.stdout + second.stderr)
            self.assertEqual(before, stored_path.read_bytes())

    def test_massive_acquisition_is_validated_sealed_and_immutable(self):
        payload = json.loads((ROOT / "examples" / "acquisition.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "acquisition.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            out_dir = td / "acquisitions"
            first = run_script("seal_acquisition.py", src, "--out-dir", out_dir, cwd=ROOT)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            stored_path = out_dir / f"{payload['acquisition_id']}.json"
            before = stored_path.read_bytes()
            stored = json.loads(before)
            self.assertIn("content_digest", stored)
            assert_schema_shape(self, stored, "massive_acquisition_manifest.schema.json")
            second = run_script("seal_acquisition.py", src, "--out-dir", out_dir, cwd=ROOT)
            self.assertEqual(3, second.returncode, second.stdout + second.stderr)
            self.assertEqual(before, stored_path.read_bytes())

    def test_complete_acquisition_rejects_unknown_basic_capability(self):
        payload = json.loads((ROOT / "examples" / "acquisition.example.json").read_text(encoding="utf-8"))
        payload["datasets"][0]["basic_snapshot_status"] = "UNKNOWN"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "acquisition.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            proc = run_script("seal_acquisition.py", src, "--out-dir", td / "acquisitions", cwd=ROOT)
            self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("basic_snapshot_not_INCLUDED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
