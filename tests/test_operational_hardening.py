import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "scripts" / "control_plane"
PIPELINE = ROOT / "scripts" / "pipeline"


def run(path, *args, cwd=ROOT):
    return subprocess.run([sys.executable, str(path), *map(str, args)], cwd=cwd, text=True, capture_output=True)


def write_materialized(root: Path, attempt: str, dataset_id: str, rows: list[dict], market="Crypto") -> Path:
    out = root / attempt
    out.mkdir(parents=True, exist_ok=True)
    data = out / f"{dataset_id}.jsonl"
    body = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    body_bytes = body.encode("utf-8")
    data.write_bytes(body_bytes)
    digest = "sha256:" + hashlib.sha256(body_bytes).hexdigest()
    meta = {
        "dataset_id": dataset_id,
        "run_id": "2026-09-28-eod",
        "attempt_id": attempt,
        "market": market,
        "endpoint_path": "/test",
        "params": {},
        "requirement": "CORE",
        "research_cutoff": "2026-09-28T23:59:59Z",
        "retrieved_at": "2026-09-29T00:00:01Z",
        "as_of": "2026-09-28",
        "row_count": len(rows),
        "sort_fields": [],
        "key_fields": [],
        "data_path": data.as_posix(),
        "data_digest": digest,
        "source_chunks": [],
        "materialization_status": "VERIFIED",
    }
    (out / f"{dataset_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return data


class OperationalHardeningTests(unittest.TestCase):


    def test_windows_bootstrap_policy_has_bounded_repo_local_repair_and_diagnostics(self):
        policy = json.loads((ROOT / "config" / "python-runtime-policy.json").read_text(encoding="utf-8"))
        self.assertEqual("3.11", policy["minimum_version"])
        self.assertEqual("3.12", policy["preferred_provision_version"])
        self.assertTrue(policy["allow_windows_registry_scan"])
        self.assertTrue(policy["allow_uv_managed_scan"])
        self.assertTrue(policy["allow_repo_local_uv_provision"])
        self.assertEqual("REPO_LOCAL_ONLY", policy["auto_install_scope"])
        bootstrap = (CONTROL / "bootstrap.ps1").read_text(encoding="utf-8")
        resolver = (CONTROL / "run_python.ps1").read_text(encoding="utf-8")
        self.assertIn("bootstrap.json", bootstrap)
        self.assertIn("python-runtime.json", bootstrap)
        self.assertIn("-AllowProvision", bootstrap)
        self.assertIn("Get-RegistryPythonCandidates", resolver)
        self.assertIn("Get-UvManagedCandidates", resolver)
        self.assertIn("Get-PathPythonCandidates", resolver)
        self.assertIn("uv_python_install", resolver)
        self.assertIn("--install-dir", resolver)
        self.assertIn("--no-bin", resolver)
        self.assertIn("probes = @($Diagnostics)", resolver)

    def test_skill_paths_are_project_root_relative_and_daily_workflow_is_bundled(self):
        for skill_md in (ROOT / ".agents" / "skills").glob("*/SKILL.md"):
            text = skill_md.read_text(encoding="utf-8")
            self.assertIn("Repository path contract:", text, skill_md.as_posix())
            self.assertNotIn("../../../", text, skill_md.as_posix())
        bundled = ROOT / ".agents" / "skills" / "daily-research-run" / "references" / "daily-goal.md"
        self.assertTrue(bundled.is_file())
        self.assertEqual((ROOT / "workflows" / "daily-goal.md").read_bytes(), bundled.read_bytes())

    def test_python_runtime_schema_accepts_ready_and_blocked_evidence(self):
        schema = ROOT / "schemas" / "python_runtime.schema.json"
        ready = {
            "status": "READY",
            "mode": "native",
            "source": "windows_registry",
            "executable": "C:/Python312/python.exe",
            "resolved_executable": "C:/Python312/python.exe",
            "prefix": [],
            "version": "3.12.7",
            "checked_at": "2026-09-29T12:00:00Z",
            "provisioned_repo_runtime": False,
            "provisioning": [],
            "probes": [{"source":"windows_registry","candidate":"C:/Python312/python.exe","status":"READY","detail":"version=3.12.7"}],
        }
        blocked = {
            "status": "BLOCKED",
            "reason": "NO_WORKING_PYTHON_3_11_PLUS",
            "checked_at": "2026-09-29T12:00:00Z",
            "minimum_version": "3.11",
            "repo_local_provision_allowed": True,
            "provisioning_attempted": True,
            "provisioning": [{"status":"FAILED","method":"uv_python_install"}],
            "probes": [{"source":"path_enumeration","candidate":"python.exe","status":"FAILED","detail":"permission denied"}],
            "remediation": ["repair runtime"],
        }
        with tempfile.TemporaryDirectory() as td:
            for name, obj in (("ready", ready), ("blocked", blocked)):
                path = Path(td) / f"{name}.json"
                path.write_text(json.dumps(obj), encoding="utf-8")
                proc = run(CONTROL / "validate_artifact.py", path, schema)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_windows_workflow_forbids_bare_python_after_runtime_binding(self):
        workflow = (ROOT / "workflows" / "daily-goal.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("bootstrap.ps1", workflow)
        self.assertIn("run_python.ps1", workflow)
        self.assertIn("Do not revert to bare `python`", workflow)
        self.assertIn("make **zero Massive provider calls**", agents)
        self.assertIn("bounded self-repair", agents)
        self.assertIn(".runtime/python", agents)

    def test_request_gate_plan_enforces_five_per_minute(self):
        proc = run(CONTROL / "massive_request_gate.py", "plan", "--request-count", "25")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        starts = result["scheduled_start_offsets_seconds"]
        self.assertEqual(25, len(starts))
        self.assertGreaterEqual(result["minimum_start_span_seconds"], 288.0)
        for idx in range(1, len(starts)):
            self.assertGreaterEqual(starts[idx] - starts[idx - 1] + 1e-9, 12.0)
        for idx, start in enumerate(starts):
            in_window = sum(1 for prior in starts[: idx + 1] if start - prior < 60.0)
            self.assertLessEqual(in_window, 5)

    def test_request_gate_rate_limit_taints_and_refuses_next_permit(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.json"
            init = run(CONTROL / "massive_request_gate.py", "init", "--run-id", "r", "--attempt-id", "a", "--ledger", ledger)
            self.assertEqual(0, init.returncode, init.stdout + init.stderr)
            permit = run(CONTROL / "massive_request_gate.py", "permit", "--ledger", ledger, "--label", "history", "--endpoint-path", "/v2/aggs/test", "--params-json", "{}")
            self.assertEqual(0, permit.returncode, permit.stdout + permit.stderr)
            permit_id = json.loads(permit.stdout)["permit_id"]
            done = run(CONTROL / "massive_request_gate.py", "complete", "--ledger", ledger, "--permit-id", permit_id, "--outcome", "RATE_LIMIT", "--warning", "Warning [RATE_LIMIT]")
            self.assertEqual(4, done.returncode)
            obj = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual("TAINTED", obj["status"])
            self.assertTrue(obj["halt_required"])
            refused = run(CONTROL / "massive_request_gate.py", "permit", "--ledger", ledger, "--label", "history2", "--endpoint-path", "/v2/aggs/test2", "--params-json", "{}")
            self.assertEqual(4, refused.returncode)
            self.assertIn("NEW_ATTEMPT_REQUIRED", refused.stdout)
            audit = run(CONTROL / "massive_request_gate.py", "audit", "--ledger", ledger, "--seal")
            self.assertEqual(2, audit.returncode)

    def test_request_gate_requires_serial_completion_and_seals_clean_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ledger = td / "ledger.json"
            self.assertEqual(0, run(CONTROL / "massive_request_gate.py", "init", "--run-id", "r", "--attempt-id", "a", "--ledger", ledger).returncode)
            permit = run(CONTROL / "massive_request_gate.py", "permit", "--ledger", ledger, "--label", "probe", "--endpoint-path", "/v3/reference/tickers", "--params-json", "{}")
            self.assertEqual(0, permit.returncode, permit.stdout + permit.stderr)
            refused = run(CONTROL / "massive_request_gate.py", "permit", "--ledger", ledger, "--label", "probe2", "--endpoint-path", "/v3/reference/tickers", "--params-json", "{}")
            self.assertEqual(4, refused.returncode)
            self.assertIn("OUTSTANDING_PERMIT", refused.stdout)
            permit_id = json.loads(permit.stdout)["permit_id"]
            complete = run(CONTROL / "massive_request_gate.py", "complete", "--ledger", ledger, "--permit-id", permit_id, "--outcome", "SUCCESS", "--row-count", "1", "--pagination-terminal", "TRUE", "--next-url-present", "FALSE")
            self.assertEqual(0, complete.returncode, complete.stdout + complete.stderr)
            seal = run(CONTROL / "massive_request_gate.py", "audit", "--ledger", ledger, "--seal")
            self.assertEqual(0, seal.returncode, seal.stdout + seal.stderr)
            sealed = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual("SEALED", sealed["status"])
            self.assertTrue(sealed["content_digest"].startswith("sha256:"))
            validate = run(CONTROL / "validate_artifact.py", ledger, ROOT / "schemas" / "massive_request_ledger.schema.json")
            self.assertEqual(0, validate.returncode, validate.stdout + validate.stderr)

    def test_capability_evaluation_degrades_for_stock_index_denial(self):
        matrix = json.loads((ROOT / "config" / "daily-capabilities.json").read_text(encoding="utf-8"))
        caps = []
        for item in matrix["capabilities"]:
            access = "SUCCEEDED"
            if item["capability_id"] in {"stock_macro_proxies", "index_macro_proxies"}:
                access = "NOT_ENTITLED"
            caps.append({
                "capability_id": item["capability_id"],
                "discovery_status": "VERIFIED",
                "basic_snapshot_status": "INCLUDED",
                "access_status": access,
                "endpoint_path": "/test",
                "probe_params": {},
                "probed_at": "2026-09-29T00:00:00Z",
                "evidence": ["test"],
            })
        report = {
            "run_id": "2026-09-28-eod",
            "attempt_id": "a1",
            "created_at": "2026-09-29T00:00:00Z",
            "research_cutoff": "2026-09-28T23:59:59Z",
            "capabilities": caps,
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "probe.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            proc = run(CONTROL / "evaluate_capabilities.py", path)
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual("DEGRADED", result["status"])
            self.assertFalse(result["core_failures"])
            self.assertEqual(2, len(result["degradations"]))

    def test_capability_evaluation_blocks_for_core_denial(self):
        matrix = json.loads((ROOT / "config" / "daily-capabilities.json").read_text(encoding="utf-8"))
        caps = []
        for item in matrix["capabilities"]:
            caps.append({
                "capability_id": item["capability_id"],
                "discovery_status": "VERIFIED",
                "basic_snapshot_status": "INCLUDED",
                "access_status": "NOT_ENTITLED" if item["capability_id"] == "crypto_history" else "SUCCEEDED",
                "endpoint_path": "/test",
                "probe_params": {},
                "probed_at": "2026-09-29T00:00:00Z",
                "evidence": ["test"],
            })
        report = {"run_id": "r", "attempt_id": "a", "created_at": "2026-09-29T00:00:00Z", "research_cutoff": "2026-09-28T23:59:59Z", "capabilities": caps}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "probe.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            proc = run(CONTROL / "evaluate_capabilities.py", path)
            self.assertEqual(2, proc.returncode)
            self.assertEqual("BLOCKED", json.loads(proc.stdout)["status"])

    def test_materializer_verifies_count_digest_and_immutability(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            c1 = td / "one.csv"
            c2 = td / "two.csv"
            c1.write_text("ticker,t,c\nX:BTCUSD,1,10\n", encoding="utf-8")
            c2.write_text("ticker,t,c\nX:ETHUSD,1,20\n", encoding="utf-8")
            out = td / "data"
            args = [c1, c2, "--dataset-id", "crypto", "--run-id", "r", "--attempt-id", "a", "--market", "Crypto", "--endpoint-path", "/test", "--params-json", "{}", "--requirement", "CORE", "--research-cutoff", "2026-09-28T23:59:59Z", "--retrieved-at", "2026-09-29T00:00:01Z", "--as-of", "2026-09-28", "--expected-rows", "2", "--sort-fields", "ticker,t", "--key-fields", "ticker,t", "--out-dir", out]
            first = run(CONTROL / "materialize_mcp_dataset.py", *args)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            result = json.loads(first.stdout)
            self.assertEqual(2, result["row_count"])
            meta = Path(result["metadata"])
            self.assertTrue(meta.exists())
            second = run(CONTROL / "materialize_mcp_dataset.py", *args)
            self.assertEqual(3, second.returncode)

    def test_materializer_rejects_truncated_chunk(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            chunk = td / "bad.csv"
            chunk.write_text("ticker,t,c\nX:BTCUSD,1,[truncated: 9 more chars]\n", encoding="utf-8")
            proc = run(CONTROL / "materialize_mcp_dataset.py", chunk, "--dataset-id", "crypto", "--run-id", "r", "--attempt-id", "a", "--market", "Crypto", "--endpoint-path", "/test", "--params-json", "{}", "--requirement", "CORE", "--research-cutoff", "2026-09-28T23:59:59Z", "--retrieved-at", "2026-09-29T00:00:01Z", "--as-of", "2026-09-28", "--expected-rows", "1", "--out-dir", td / "out")
            self.assertEqual(2, proc.returncode)
            self.assertIn("truncation_marker", proc.stdout)

    def test_degraded_acquisition_allows_denied_enrichment_but_complete_core(self):
        payload = json.loads((ROOT / "examples" / "acquisition.example.json").read_text(encoding="utf-8"))
        payload["status"] = "DEGRADED"
        payload["limitations"] = ["stock_macro_proxies:not_entitled"]
        payload["datasets"].append({
            "dataset_id": "stock_macro",
            "capability_id": "stock_macro_proxies",
            "requirement": "ENRICHMENT",
            "market": "Stocks",
            "purpose": "macro",
            "method": "GET",
            "endpoint_path": "/v2/aggs/grouped/locale/us/market/stocks/2026-09-28",
            "params": {},
            "retrieved_at": "2026-09-29T00:03:00Z",
            "retrieval_time_source": "CLIENT_CAPTURED",
            "as_of": "2026-09-28",
            "discovery_status": "VERIFIED",
            "basic_snapshot_status": "INCLUDED",
            "access_status": "NOT_ENTITLED",
            "pagination_complete": True,
            "row_count": 0,
            "workspace_table": None,
            "request_ids": [],
            "materialization_status": "NOT_REQUIRED",
            "materialized_path": None,
            "materialized_digest": None,
            "materialized_row_count": None,
            "status": "ACCESS_DENIED",
            "notes": ["provider denial"],
        })
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "payload.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            proc = run(CONTROL / "seal_acquisition.py", src, "--out-dir", td / "out")
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_validate_artifact_enforces_additional_properties(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            artifact = json.loads((ROOT / "examples" / "data-quality.example.json").read_text(encoding="utf-8"))
            artifact["unexpected"] = True
            src = td / "dq.json"
            src.write_text(json.dumps(artifact), encoding="utf-8")
            proc = run(CONTROL / "validate_artifact.py", src, ROOT / "schemas" / "data_quality_report.schema.json")
            self.assertEqual(1, proc.returncode)
            self.assertIn("additionalProperty:unexpected", proc.stdout)

    def test_deterministic_pipeline_runs_with_verified_crypto_core_and_degraded_macro(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            attempt = "2026-09-28-eod-attempt-test"
            tickers = ["X:BTCUSD", "X:ETHUSD", "X:SOLUSD", "X:XRPUSD", "X:LTCUSD", "X:ADAUSD"]
            universe = [{"ticker": t, "active": True} for t in tickers]
            cutoff = []
            history = []
            start = datetime(2026, 7, 26, tzinfo=timezone.utc)
            for j, ticker in enumerate(tickers):
                base = 100 + j * 20
                for i in range(65):
                    price = base * (1 + 0.002 * (j + 1) * i)
                    ts = int((start + timedelta(days=i)).timestamp() * 1000)
                    history.append({"ticker": ticker, "t": ts, "o": price * 0.997, "h": price * 1.01, "l": price * 0.99, "c": price, "v": 100000 + 1000 * j, "vw": price * 0.999, "n": 1000 + i})
                last = history[-1]
                cutoff.append({"T": ticker, "t_2": last["t"], "o": last["o"], "h": last["h"], "l": last["l"], "c": last["c"], "v": last["v"], "vw": last["vw"], "n": last["n"]})
            data_root = td / "data"
            p_universe = write_materialized(data_root, attempt, "crypto_universe", universe)
            p_cutoff = write_materialized(data_root, attempt, "crypto_grouped_cutoff", cutoff)
            p_history = write_materialized(data_root, attempt, "crypto_history", history)
            dq = td / "dq.json"
            dq.write_text(json.dumps({"run_id": "2026-09-28-eod", "status": "PASS", "cutoff": "2026-09-28T23:59:59Z", "datasets": ["crypto_universe", "crypto_grouped_cutoff", "crypto_history"], "findings": []}), encoding="utf-8")
            caps = td / "caps.json"
            caps.write_text(json.dumps({"run_id": "2026-09-28-eod", "attempt_id": attempt, "status": "DEGRADED", "core_failures": [], "degradations": ["stock_macro_proxies:NOT_ENTITLED", "index_macro_proxies:NOT_ENTITLED"], "optional_unavailable": [], "evaluated_capabilities": []}), encoding="utf-8")
            out = td / "pipeline"
            proc = run(PIPELINE / "run_daily_pipeline.py", "--run-id", "2026-09-28-eod", "--attempt-id", attempt, "--research-cutoff", "2026-09-28T23:59:59Z", "--crypto-universe", p_universe, "--crypto-cutoff", p_cutoff, "--crypto-history", p_history, "--data-quality", dq, "--capability-evaluation", caps, "--config", ROOT / "config" / "daily-model.json", "--out-dir", out)
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            result = json.loads((out / attempt / "pipeline-result.json").read_text(encoding="utf-8"))
            self.assertEqual("DEGRADED", result["status"])
            self.assertEqual(6, result["history_qualified_assets"])
            self.assertIn(result["market_state"], {"RISK_ON", "TRANSITION", "RISK_OFF"})
            self.assertTrue((out / attempt / "forecast-payload.json").exists())


if __name__ == "__main__":
    unittest.main()
