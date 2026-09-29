import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "control_plane" / "qualify_replay.py"
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


if __name__ == "__main__":
    unittest.main()
