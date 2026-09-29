import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "control_plane" / "qualify_replay.py"
EXPORTER = ROOT / "scripts" / "control_plane" / "export_live_replay_bundle.py"
FIXTURE = ROOT / "fixtures" / "replay" / "daily-v1"


def run_replay(fixture: Path, output: Path):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), "--fixture", str(fixture), "--out", str(output)], cwd=ROOT, text=True, capture_output=True)


class ReplayQualificationTests(unittest.TestCase):
    def test_replay_is_offline_explicit_and_cannot_masquerade_as_live(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
        imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        self.assertTrue(imports.isdisjoint({"socket", "urllib", "requests", "httpx"}))
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "qualification.json"
            proc = run_replay(FIXTURE / "fixture.json", output)
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("OFFLINE_REPLAY", result["qualification_mode"])
            self.assertEqual("SYNTHETIC", result["fixture"]["provenance"])
            self.assertFalse(result["live_provider_qualified"])
            self.assertFalse(result["live_daily_run_pass"])
            self.assertEqual({"NOT_TESTED"}, set(result["provider_checks"].values()))
            self.assertNotIn("content_digest", result)

    def test_data_digest_tampering_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            copied = Path(td) / "fixture"
            shutil.copytree(FIXTURE, copied)
            with (copied / "crypto_history.jsonl").open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            proc = run_replay(copied / "fixture.json", Path(td) / "result.json")
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("BLOCKED", proc.stdout)

    def test_row_count_tampering_blocks_even_with_updated_metadata_digest(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            copied = Path(td) / "fixture"
            shutil.copytree(FIXTURE, copied)
            meta_path = copied / "crypto_universe.meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["row_count"] += 1
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path = copied / "fixture.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["datasets"][0]["metadata_digest"] = "sha256:" + hashlib.sha256(meta_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            proc = run_replay(manifest_path, Path(td) / "result.json")
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("BLOCKED", proc.stdout)

    def test_fixed_fixture_pipeline_outputs_are_stable(self):
        with tempfile.TemporaryDirectory() as td:
            first, second = Path(td) / "first.json", Path(td) / "second.json"
            self.assertEqual(0, run_replay(FIXTURE / "fixture.json", first).returncode)
            self.assertEqual(0, run_replay(FIXTURE / "fixture.json", second).returncode)
            a, b = json.loads(first.read_text()), json.loads(second.read_text())
            self.assertEqual(a["artifact_digests"], b["artifact_digests"])
            self.assertEqual(a["artifact_digests"], json.loads((FIXTURE / "fixture.json").read_text())["expected_pipeline_digests"])


class LiveCaptureParityTests(unittest.TestCase):
    def _source(self, root: Path, sealed: bool = True, omit_history: bool = False):
        source = root / "source"
        shutil.copytree(FIXTURE, source)
        fixture = json.loads((source / "fixture.json").read_text())
        pipeline = root / "pipeline"
        cmd = [sys.executable, "-B", str(ROOT / "scripts/pipeline/run_daily_pipeline.py"), "--run-id", fixture["run_id"], "--attempt-id", fixture["attempt_id"], "--research-cutoff", fixture["research_cutoff"], "--crypto-universe", str(source / "crypto_universe.jsonl"), "--crypto-cutoff", str(source / "crypto_cutoff.jsonl"), "--crypto-history", str(source / "crypto_history.jsonl"), "--data-quality", str(source / "data-quality.json"), "--capability-evaluation", str(source / "capability-evaluation.json"), "--config", str(ROOT / "config/daily-model.json"), "--created-at", fixture["created_at"], "--out-dir", str(pipeline)]
        self.assertEqual(0, subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode)
        datasets = []
        for entry in fixture["datasets"]:
            if omit_history and entry["role"] == "crypto_history":
                continue
            datasets.append({"dataset_id": entry["role"], "capability_id": entry["role"], "requirement": "CORE", "market": "Crypto", "purpose": "test live capture", "method": "GET", "endpoint_path": "/v2/test", "params": {}, "retrieved_at": "2026-09-29T00:00:00Z", "retrieval_time_source": "CLIENT_CAPTURED", "as_of": "2026-09-28", "discovery_status": "VERIFIED", "basic_snapshot_status": "INCLUDED", "access_status": "SUCCEEDED", "pagination_complete": True, "row_count": entry["row_count"], "materialization_status": "VERIFIED", "materialized_path": (source / entry["data_path"]).relative_to(ROOT).as_posix(), "materialized_digest": entry["data_digest"], "materialized_row_count": entry["row_count"], "status": "COMPLETE"})
        manifest = {"acquisition_id": "test-acquisition", "run_id": fixture["run_id"], "attempt_id": fixture["attempt_id"], "created_at": "2026-09-29T00:05:00Z", "research_cutoff": fixture["research_cutoff"], "source": "massive_mcp", "server_url": "https://mcp.massive.com/", "status": "DEGRADED", "datasets": datasets, "errors": [], "limitations": ["test fixture omits enrichment"]}
        if sealed:
            manifest["content_digest"] = "sha256:" + hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        return fixture, source, pipeline / fixture["attempt_id"], manifest_path

    def _export(self, root: Path, sealed: bool = True, omit_history: bool = False):
        fixture, source, pipeline, manifest = self._source(root, sealed, omit_history)
        out = root / "bundle"
        proc = subprocess.run([sys.executable, "-B", str(EXPORTER), "--attempt-id", fixture["attempt_id"], "--manifest", str(manifest), "--pipeline-dir", str(pipeline), "--data-quality", str(source / "data-quality.json"), "--capability-evaluation", str(source / "capability-evaluation.json"), "--created-at", fixture["created_at"], "--out", str(out)], cwd=ROOT, text=True, capture_output=True)
        return proc, out

    def test_live_capture_exports_and_replays_with_zero_provider_calls(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            proc, bundle = self._export(Path(td))
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            result = Path(td) / "result.json"
            replay = subprocess.run([sys.executable, "-B", str(SCRIPT), "--bundle", str(bundle), "--out", str(result)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(0, replay.returncode, replay.stdout + replay.stderr)
            obj = json.loads(result.read_text())
            self.assertEqual("LIVE_CAPTURE_REPLAY", obj["qualification_mode"])
            self.assertEqual("LIVE_CAPTURE_REPLAY_MATCH", obj["status"])
            self.assertEqual(0, obj["live_provider_requests_in_replay"])
            self.assertFalse(obj["live_provider_qualified"])
            self.assertEqual({"MATCH"}, set(obj["artifact_comparisons"].values()))

    def test_export_rejects_unsealed_and_incomplete_sources(self):
        for sealed, omit in ((False, False), (True, True)):
            with self.subTest(sealed=sealed, omit=omit), tempfile.TemporaryDirectory(dir=ROOT) as td:
                proc, _ = self._export(Path(td), sealed, omit)
                self.assertNotEqual(0, proc.returncode)

    def test_inventory_dataset_and_expected_output_tampering_are_detected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            proc, bundle = self._export(Path(td)); self.assertEqual(0, proc.returncode, proc.stdout)
            (bundle / "evidence/datasets/crypto_history.jsonl").write_text("{}\n")
            replay = subprocess.run([sys.executable, "-B", str(SCRIPT), "--bundle", str(bundle), "--out", str(Path(td) / "bad.json")], cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(0, replay.returncode)
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            proc, bundle = self._export(Path(td)); self.assertEqual(0, proc.returncode, proc.stdout)
            manifest = json.loads((bundle / "bundle.json").read_text()); manifest["expected_pipeline_digests"]["factors.json"] = "sha256:" + "0" * 64
            unsigned = dict(manifest); unsigned.pop("bundle_digest")
            manifest["bundle_digest"] = "sha256:" + hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            (bundle / "bundle.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
            result = Path(td) / "mismatch.json"
            replay = subprocess.run([sys.executable, "-B", str(SCRIPT), "--bundle", str(bundle), "--out", str(result)], cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(0, replay.returncode)
            self.assertEqual("LIVE_CAPTURE_REPLAY_MISMATCH", json.loads(result.read_text())["status"])

    def test_export_rejects_source_outside_repository(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory(dir=ROOT) as td:
            fixture, source, pipeline, manifest = self._source(Path(td))
            external = Path(outside) / "dq.json"; shutil.copyfile(source / "data-quality.json", external)
            proc = subprocess.run([sys.executable, "-B", str(EXPORTER), "--attempt-id", fixture["attempt_id"], "--manifest", str(manifest), "--pipeline-dir", str(pipeline), "--data-quality", str(external), "--capability-evaluation", str(source / "capability-evaluation.json"), "--created-at", "2026-09-29T01:00:00Z", "--out", str(Path(td) / "bundle")], cwd=ROOT, capture_output=True)
            self.assertNotEqual(0, proc.returncode)


if __name__ == "__main__":
    unittest.main()
