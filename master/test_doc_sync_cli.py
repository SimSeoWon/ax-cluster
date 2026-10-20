"""등록 문서 CLI의 읽기·수정안 저장·명시 적용 연결 검사 (#838)."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.doc_sync import digest
from master.doc_sync.__main__ import main
from master.doc_sync.registry import collect


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "README.md").write_text("old\n", encoding="utf-8")
        (self.root / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.registry = self.root / "registry.json"
        self.registry.write_text(json.dumps({"version": 1, "documents": [
            {"id": "readme", "path": "README.md", "role": "overview", "protected": False,
             "instructions": "근거만 사용", "evidence": ["source.py"]}]}), encoding="utf-8")
        self.args = ["--root", str(self.root), "--registry", str(self.registry)]

    def run_cli(self, command, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([command, *self.args, *args])
        return rc, stdout.getvalue(), stderr.getvalue()

    def artifact(self):
        plan = collect(self.root, self.registry)
        doc = plan["documents"][0]
        doc.update(decision="update", after="new\n", after_sha256=digest("new\n"),
                   reason="현재 소스 반영", citations=["source.py:1"], diff="old -> new")
        return plan

    def test_plan_is_read_only_and_summarizes_registered_targets(self):
        before = sorted(p.name for p in self.root.iterdir())
        rc, output, error = self.run_cli("plan")
        self.assertEqual((rc, error), (0, ""))
        data = json.loads(output)
        self.assertEqual(data["documents"][0]["id"], "readme")
        self.assertNotIn("before", data["documents"][0])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)

    def test_draft_saves_artifact_but_does_not_apply(self):
        output_path = self.root / "proposal.json"
        with patch("master.context_search.paths.resolve_mounted_only", return_value=SimpleNamespace(
                usage_log=self.root / "usage.jsonl")), \
                patch("master.doc_sync.draft.generate", return_value=self.artifact()) as generate:
            rc, output, error = self.run_cli("draft", "--project", "T", "--out", str(output_path))
        self.assertEqual((rc, error), (0, ""))
        self.assertTrue(json.loads(output)["ok"])
        self.assertEqual(generate.call_args.kwargs["lane"], "codex")
        self.assertEqual(json.loads(output_path.read_text())["documents"][0]["after"], "new\n")
        self.assertEqual((self.root / "README.md").read_text(), "old\n")

    def test_apply_requires_explicit_ids_and_is_repeatable(self):
        output_path = self.root / "proposal.json"
        output_path.write_text(json.dumps(self.artifact()), encoding="utf-8")
        rc, output, _ = self.run_cli("apply", "--artifact", str(output_path))
        self.assertEqual(rc, 0)
        self.assertFalse(json.loads(output)["confirm"])
        self.assertEqual((self.root / "README.md").read_text(), "old\n")
        rc, output, _ = self.run_cli("apply", "--artifact", str(output_path), "--confirm", "--approve", "readme")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(output)["changed"], ["readme"])
        rc, output, _ = self.run_cli("apply", "--artifact", str(output_path), "--confirm", "--approve", "readme")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(output)["unchanged"], ["readme"])

    def test_existing_output_is_refused_before_model_call(self):
        output_path = self.root / "README.md"
        with patch("master.context_search.paths.resolve_mounted_only", return_value=SimpleNamespace(
                usage_log=self.root / "usage.jsonl")), patch("master.doc_sync.draft.generate") as generate:
            rc, _, error = self.run_cli("draft", "--project", "T", "--out", str(output_path))
        self.assertEqual(rc, 1)
        self.assertIn("출력", error)
        generate.assert_not_called()

    def test_invalid_artifact_does_not_write(self):
        plan = copy.deepcopy(self.artifact())
        plan["documents"][0]["after_sha256"] = "bad"
        output_path = self.root / "proposal.json"
        output_path.write_text(json.dumps(plan))
        rc, _, error = self.run_cli("apply", "--artifact", str(output_path), "--confirm", "--approve", "readme")
        self.assertEqual(rc, 1)
        self.assertIn("해시", error)
        self.assertEqual((self.root / "README.md").read_text(), "old\n")


if __name__ == "__main__":
    unittest.main()
