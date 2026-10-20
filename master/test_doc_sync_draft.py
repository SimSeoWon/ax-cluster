"""문서 수정안의 근거 검증·원문 보존·CLI 계측 계약."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.doc_sync import DocSyncError, digest
from master.doc_sync.draft import generate


def plan():
    before = "old\r\n"
    return {"schema_version": 1, "root": "/example", "documents": [
        {"id": "readme", "path": "README.md", "target": "README.md",
         "before": before, "before_sha256": digest(before), "role": "overview",
         "protected": True, "instructions": "지침 보존",
         "evidence": [{"path": "src.py", "sha256": "example", "text": "a\nb\n"}]}]}


def response(**changes):
    return json.dumps({"decision": "update", "content": "new\n", "reason": "변경 근거",
                       "citations": ["src.py:2"], **changes})


class DraftTests(unittest.TestCase):
    def test_edits_assemble_full_content_in_order(self):
        data = {"decision": "update", "reason": "근거", "citations": ["src.py:1"],
                "edits": [{"before": "old", "after": "new"},
                          {"before": "new", "after": "final"}]}
        artifact = generate(plan(), generator=lambda *args: json.dumps(data))
        self.assertEqual(artifact["documents"][0]["after"], "final\r\n")

    def test_reject_ambiguous_or_mixed_edits(self):
        invalid = [[{"before": "", "after": "a"}],
                   [{"before": "missing", "after": "a"}],
                   [{"before": "old", "after": "old"}, {"before": "old", "after": "x"}]]
        for edits in invalid:
            value = {"decision": "update", "reason": "근거", "citations": ["src.py:1"],
                     "edits": edits}
            with self.subTest(edits=edits), self.assertRaises(DocSyncError):
                generate(plan(), generator=lambda *args: json.dumps(value))
        with self.assertRaises(DocSyncError):
            generate(plan(), generator=lambda *args: response(edits=[]))
        data = plan()
        data["documents"][0]["before"] = "old old"
        value = {"decision": "update", "reason": "근거", "citations": ["src.py:1"],
                 "edits": [{"before": "old", "after": "new"}]}
        with self.assertRaises(DocSyncError):
            generate(data, generator=lambda *args: json.dumps(value))

    def test_update_prompt_and_no_input_mutation(self):
        original = plan()
        saved = copy.deepcopy(original)
        seen = []

        def generator(prompt, lane, timeout):
            seen.append((prompt, lane, timeout))
            return response()

        result = generate(original, generator=generator)
        self.assertEqual(original, saved)
        self.assertEqual(result["documents"][0]["after"], "new\n")
        self.assertIn("-old", result["documents"][0]["diff"])
        self.assertIn("src.py:2 b", seen[0][0])
        self.assertIn("AX-ENTRY-MARK", seen[0][0])
        self.assertEqual(seen[0][1:], ("codex", 180))

    def test_unchanged_preserves_original_bytes(self):
        result = generate(plan(), generator=lambda *args: response(
            decision="unchanged", content="ignored", citations=[]))
        self.assertEqual(result["documents"][0]["after"], "old\r\n")
        self.assertEqual(result["documents"][0]["diff"], "")

    def test_reject_invalid_responses(self):
        values = ["not json", "[]", response(decision="write"), response(content=" "),
                  response(reason=""), response(citations=[]), response(citations=["src.py:3"]),
                  response(citations=["other.py:1"]), response(citations="src.py:1"),
                  response(content="\ud800")]
        for value in values:
            with self.subTest(value=value), self.assertRaises(DocSyncError):
                generate(plan(), generator=lambda *args: value)

    def test_multiple_documents_and_stop_on_failure(self):
        data = plan()
        data["documents"].append(copy.deepcopy(data["documents"][0]))
        generator = unittest.mock.Mock(side_effect=[response(), response(decision="unchanged")])
        self.assertEqual(len(generate(data, generator=generator)["documents"]), 2)
        generator = unittest.mock.Mock(side_effect=RuntimeError("fail"))
        with self.assertRaises(DocSyncError):
            generate(data, generator=generator)
        self.assertEqual(generator.call_count, 1)

    def test_real_usage_success_and_parse_failure_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "usage.jsonl"
            events = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 7}})
            with patch("master.doc_sync.draft.L2.call_codex_why",
                       return_value=(response(), events, "")) as call:
                generate(plan(), usage_log=logfile)
                self.assertEqual(call.call_count, 1)
                workdir = call.call_args.kwargs["workdir"]
                self.assertIn("ax-doc-sync-llm-", workdir)
                self.assertNotEqual(Path(workdir), Path.cwd())
            with patch("master.doc_sync.draft.L2.call_codex_why",
                       return_value=("bad json", events, "")):
                with self.assertRaises(DocSyncError):
                    generate(plan(), usage_log=logfile)
            records = [json.loads(line) for line in logfile.read_text().splitlines()]
            self.assertEqual([item["rc"] for item in records], [0, 1])
            self.assertTrue(all(item["source"] == "doc-sync" for item in records))
            self.assertEqual(records[1]["input_tokens"], 7)

    def test_usage_call_error_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "usage.jsonl"
            with patch("master.doc_sync.draft.L2.call_codex_why",
                       return_value=(None, "", "timeout")):
                with self.assertRaisesRegex(DocSyncError, "timeout"):
                    generate(plan(), usage_log=logfile)
            self.assertEqual(json.loads(logfile.read_text())["rc"], 1)

    def test_no_unmetered_real_call_or_lane_fallback(self):
        with patch("master.doc_sync.draft.L2.call_codex_why") as call:
            with self.assertRaises(DocSyncError):
                generate(plan())
            with self.assertRaises(DocSyncError):
                generate(plan(), lane="unknown", generator=lambda *args: response())
            with self.assertRaisesRegex(DocSyncError, "읽기 전용"):
                generate(plan(), lane="agy", generator=lambda *args: response())
            call.assert_not_called()

    def test_claude_lane_isolated_and_metered_once(self):
        from master.work import usage as U

        def fake(prompt, *, timeout, workdir):
            # 실제 call_claude_why 처럼 공용 진입으로만 사용량을 낸다
            U.emit_cli("claude", U.Usage(lane="claude", input_tokens=11, output_tokens=3,
                                         cache_read=2, cost_usd=0.5), rc=0, model="opus")
            return response(), ""

        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "usage.jsonl"
            with patch("master.doc_sync.draft.L2.call_codex_why") as codex, \
                    patch("master.doc_sync.draft.L2.call_claude_why", side_effect=fake) as call:
                artifact = generate(plan(), lane="claude", usage_log=logfile)
            codex.assert_not_called()
            self.assertEqual(call.call_count, 1)
            self.assertIn("ax-doc-sync-llm-", call.call_args.kwargs["workdir"])
            self.assertEqual(artifact["lane"], "claude")
            self.assertEqual(artifact["documents"][0]["decision"], "update")
            records = [json.loads(line) for line in logfile.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual((records[0]["lane"], records[0]["source"], records[0]["rc"]),
                             ("claude", "doc-sync", 0))
            self.assertEqual((records[0]["input_tokens"], records[0]["output_tokens"],
                              records[0]["cache_read"]), (11, 3, 2))
            self.assertEqual(records[0]["model"], "opus")

    def test_single_code_fence_unwrapped_only(self):
        fenced = "```json\n" + response() + "\n```\n"
        artifact = generate(plan(), generator=lambda *args: fenced)
        self.assertEqual(artifact["documents"][0]["after"], "new\n")
        for bad in ("설명\n```json\n" + response() + "\n```",
                    "```python\n" + response() + "\n```"):
            with self.assertRaisesRegex(DocSyncError, "JSON") as caught:
                generate(plan(), generator=lambda *args, text=bad: text)
            self.assertEqual(caught.exception.raw_response, bad)

    def test_claude_lane_failure_recorded_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "usage.jsonl"
            with patch("master.doc_sync.draft.L2.call_codex_why") as codex, \
                    patch("master.doc_sync.draft.L2.call_claude_why",
                          return_value=(None, "rc=1: limit")):
                with self.assertRaisesRegex(DocSyncError, "limit"):
                    generate(plan(), lane="claude", usage_log=logfile)
            codex.assert_not_called()
            record = json.loads(logfile.read_text())
            self.assertEqual((record["rc"], record["lane"], record["measured"]), (1, "claude", False))


if __name__ == "__main__":
    unittest.main()
