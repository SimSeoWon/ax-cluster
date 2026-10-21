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

    def test_range_options_and_selection_survive_plan_and_draft(self):
        artifact = self.artifact()
        artifact['selection'] = {'included': [{'id': 'readme', 'reason': 'registry-changed'}],
                                 'excluded': [], 'content_source': 'current-working-tree'}
        with patch('master.doc_sync.__main__.collect', return_value=artifact) as collect_mock:
            rc, output, error = self.run_cli('plan', '--since', 'start', '--until', 'end',
                                             '--id', 'readme')
        self.assertEqual((rc, error), (0, ''))
        self.assertEqual(json.loads(output)['selection'], artifact['selection'])
        self.assertEqual(collect_mock.call_args.kwargs,
                         dict(ids=['readme'], since='start', until='end'))
        destination = self.root / 'selected.json'
        from master.doc_sync.draft import generate as actual_generate
        def generate(plan, **kwargs):
            return actual_generate(plan, generator=lambda *args: json.dumps({
                'decision': 'unchanged', 'reason': '현재 내용이 근거와 일치', 'citations': []}))
        with patch('master.doc_sync.__main__.collect', return_value=artifact), \
                patch('master.context_search.paths.resolve_mounted_only',
                      return_value=SimpleNamespace(usage_log=self.root / 'usage.jsonl')), \
                patch('master.doc_sync.draft.generate', side_effect=generate):
            rc, output, _ = self.run_cli('draft', '--since', 'start', '--project', 'T',
                                          '--out', str(destination))
        self.assertEqual(rc, 0)
        saved = json.loads(destination.read_text())
        self.assertEqual(saved['selection'], artifact['selection'])
        self.assertEqual(json.loads(output)['selection'], artifact['selection'])
        self.assertEqual(saved['documents'][0]['decision'], 'unchanged')

    def test_until_requires_since_before_model_call(self):
        with patch('master.doc_sync.draft.generate') as generate:
            rc, _, error = self.run_cli('draft', '--until', 'HEAD', '--project', 'T',
                                          '--out', str(self.root / 'never.json'))
        self.assertEqual(rc, 1)
        self.assertIn('since', error)
        generate.assert_not_called()

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

    def test_draft_passes_claude_lane(self):
        output_path = self.root / "proposal-claude.json"
        with patch("master.context_search.paths.resolve_mounted_only", return_value=SimpleNamespace(
                usage_log=self.root / "usage.jsonl")), \
                patch("master.doc_sync.draft.generate", return_value=self.artifact()) as generate:
            rc, _, error = self.run_cli("draft", "--project", "T", "--lane", "claude",
                                        "--out", str(output_path))
        self.assertEqual((rc, error), (0, ""))
        self.assertEqual(generate.call_args.kwargs["lane"], "claude")

    def test_draft_parse_failure_saves_raw_response(self):
        from master.doc_sync import DocSyncError
        output_path = self.root / "proposal-bad.json"
        failure = DocSyncError("LLM 응답은 JSON 객체여야 한다")
        failure.raw_response = "not json"
        with patch("master.context_search.paths.resolve_mounted_only", return_value=SimpleNamespace(
                usage_log=self.root / "usage.jsonl")), \
                patch("master.doc_sync.draft.generate", side_effect=failure):
            rc, _, error = self.run_cli("draft", "--project", "T", "--out", str(output_path))
        self.assertEqual(rc, 1)
        self.assertFalse(output_path.exists())
        raw = Path(f"{output_path}.raw.txt")
        self.assertEqual(raw.read_text(), "not json")
        self.assertIn("응답 원문 저장", error)

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
