"""파견 계측 (`#387`) — 성공·실패 × 레인·지휘자 네 갈래에서 계측이 살아남는가.

🔴 이 파일이 못 박는 것은 셋이다:
  ⑴ **실패해도 계측이 남는다** — 실패한 실행도 토큰은 태웠다(사용자 지적 2026-09-08)
  ⑵ **레인과 지휘자가 같은 모양으로 남는다** — 형태가 둘이면 A/B 비교가 성립하지 않는다
  ⑶ **미상과 0 이 구분된다** — codex 는 토큰은 주고 USD 는 안 준다
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.work import usage as U
from master.work import wcommit
from master.work.runner import _unwrap, Outcome

CLAUDE_META = {"usage": {"input_tokens": 1200, "output_tokens": 800,
                         "cache_read_input_tokens": 5000,
                         "cache_creation_input_tokens": 300},
               "total_cost_usd": 0.0412}
CODEX_STDOUT = "\n".join([
    json.dumps({"type": "item.completed",
                "item": {"type": "agent_message", "text": "RESULT: DONE"}}),
    json.dumps({"type": "turn.completed",
                "usage": {"input_tokens": 9000, "output_tokens": 1500,
                          "cached_input_tokens": 40, "cache_write_input_tokens": 7,
                          "reasoning_output_tokens": 640}}),
])


class Envelope(unittest.TestCase):
    """레인 봉투가 지휘자 출력과 **같은 경로**로 풀리는가."""

    def test_lane_envelope_round_trips_through_unwrap(self):
        u = U.Usage(lane="agy", input_tokens=700, output_tokens=400, total_tokens=1100)
        env = U.envelope("RESULT: DONE (lane=agy)", U.meta_from_usage(u))
        body, meta = _unwrap(env)
        self.assertEqual(body, "RESULT: DONE (lane=agy)")
        self.assertEqual(meta["source"], "agy")
        self.assertEqual(meta["usage"]["input_tokens"], 700)
        # 레인은 USD 를 모른다 — 0 으로 접지 않는다
        self.assertTrue(meta["cost_unknown"])
        self.assertFalse(Outcome(usage=meta).cost_known)

    def test_claude_and_codex_land_in_the_same_shape(self):
        for raw, src, known in ((json.dumps({"result": "x", **CLAUDE_META}), None, True),
                                (CODEX_STDOUT, "codex", False)):
            _body, meta = _unwrap(raw)
            self.assertTrue(meta.get("usage"), raw[:40])
            self.assertEqual(Outcome(usage=meta).cost_known, known)
            if src:
                self.assertEqual(meta["source"], src)

    def test_unknown_values_never_become_zero(self):
        """🔴 `None` 을 0 으로 적으면 「안 썼다」가 된다 — 키 자체를 만들지 않는다."""
        meta = U.meta_from_usage(U.Usage(lane="agy", note="형식 불명"))
        self.assertNotIn("usage", meta)
        self.assertTrue(meta["cost_unknown"])
        self.assertEqual(U.meta_from_usage(None), {})


class CycleCarriesUsage(unittest.TestCase):
    """`wcommit._cycle` 이 `out` 을 버리지 않는가 — 이 일감의 증상 자체."""

    def _run(self, rc, out):
        c = wcommit.Committed(task_id="t", want=["a.cpp"])
        facts = type("F", (), {"windows": False, "path": "/ws", "host": "h"})()
        def llm(*_a, **_k):
            return rc, out
        def read(*_a, **_k):
            return "body"
        wcommit._cycle(facts, "t", c, "base", llm, lambda *a, **k: "", read, None, None)
        return c

    def test_success_keeps_usage(self):
        c = self._run(0, json.dumps({"result": "RESULT: DONE", **CLAUDE_META}))
        self.assertEqual(c.usage["usage"]["input_tokens"], 1200)
        self.assertGreaterEqual(c.seconds, 0.0)

    def test_failure_keeps_usage_too(self):
        """🔴 실패한 실행도 토큰은 태웠다 — 여기가 버려지던 자리다."""
        c = self._run(1, CODEX_STDOUT)
        self.assertEqual(c.usage["usage"]["input_tokens"], 9000)
        self.assertTrue(c.usage["cost_unknown"])

    def test_failure_reason_shows_body_not_envelope(self):
        """봉투 JSON 을 사유로 보이면 사람이 못 읽는다."""
        c = self._run(1, json.dumps({"result": "RESULT: BLOCKED - lanes failed",
                                     "cost_unknown": True}))
        self.assertIn("RESULT: BLOCKED - lanes failed", c.reason)
        self.assertNotIn('{"result"', c.reason)

    def test_unparseable_output_is_not_a_failure(self):
        """계측이 없는 것과 작업이 실패한 것은 다르다."""
        c = self._run(1, "그냥 산문")
        self.assertEqual(c.usage, {})
        self.assertIn("그냥 산문", c.reason)


class CodexErrors(unittest.TestCase):
    def test_errors_survive_without_body_and_do_not_invent_usage(self):
        message = "You've hit your usage limit. Try again later."
        raw = json.dumps({"type": "error", "message": message})
        body, meta = _unwrap(raw)
        self.assertEqual(body, "")
        self.assertEqual(meta["errors"], [message])
        self.assertNotIn("usage", meta)
        self.assertTrue(meta["cost_unknown"])

    def test_last_body_usage_and_distinct_errors_are_preserved(self):
        message = "You've hit your usage limit."
        events = [CODEX_STDOUT,
                  json.dumps({"type": "error", "message": message}),
                  json.dumps({"type": "turn.failed", "error": {"message": message}}),
                  json.dumps({"type": "error", "message": "another error"})]
        body, meta = _unwrap("\n".join(events))
        self.assertEqual(body, "RESULT: DONE")
        self.assertEqual(meta["usage"]["input_tokens"], 9000)
        self.assertEqual(meta["errors"], [message, "another error"])

    def test_malformed_events_do_not_hide_following_error(self):
        events = ['{"broken"', '{}',
                  json.dumps({"type": "item.completed", "item": "bad"}),
                  json.dumps({"type": "turn.failed", "error": []}),
                  json.dumps({"type": "error", "message": 5}),
                  json.dumps({"type": "turn.failed", "error": {"message": "usage limit"}})]
        self.assertEqual(_unwrap("\n".join(events))[1]["errors"], ["usage limit"])

    def test_long_error_is_retained_in_failure_notes(self):
        message = "x" * 500 + " usage limit " + "y" * 500
        out = CODEX_STDOUT + "\n" + json.dumps({"type": "error", "message": message})
        c = CycleCarriesUsage()._run(1, out)
        self.assertTrue(any(message in note for note in c.notes))


class LogAndSummary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ax-usage-")
        self.log = Path(self.tmp.name) / "usage_log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_records_both_outcomes_and_separates_unknown_cost(self):
        U.record(self.log, CLAUDE_META, lane="claude", task_id="t1", work_id="w",
                 worker=".2", mode="claude", rc=0, seconds=47.2)
        U.record(self.log, _unwrap(CODEX_STDOUT)[1], task_id="t2", work_id="w",
                 worker=".43", mode="codex", rc=1, seconds=85.0)
        s = U.summarize(self.log, days=1)
        self.assertEqual(s["calls"], 2)
        self.assertEqual(s["failed_calls"], 1)          # ⑴ 실패도 세어진다
        self.assertEqual(s["input_tokens"], 10200)      # 토큰은 미상 여부와 무관
        self.assertEqual(s["reasoning_tokens"], 640)
        # ⑶ 아는 비용만 더하고, 모르는 호출 수를 따로 낸다
        self.assertAlmostEqual(s["cost_usd"], 0.0412, places=4)
        self.assertEqual(s["cost_unknown_calls"], 1)
        self.assertEqual(s["by_mode"]["codex"]["cost_usd"], 0.0)
        self.assertEqual(s["by_mode"]["codex"]["cost_unknown_calls"], 1)

    def test_zero_cost_is_not_unknown_cost(self):
        """🔴 아는 0 과 모르는 0 을 섞지 않는다."""
        U.record(self.log, {"usage": {"input_tokens": 1}, "total_cost_usd": 0.0}, lane="x")
        s = U.summarize(self.log, days=1)
        self.assertEqual(s["cost_unknown_calls"], 0)
        self.assertEqual(s["cost_usd"], 0.0)

    def test_unmeasured_call_is_counted(self):
        U.record(self.log, {}, lane="?", mode="lane")
        s = U.summarize(self.log, days=1)
        self.assertEqual(s["unmeasured_calls"], 1)
        self.assertEqual(s["cost_unknown_calls"], 1)

    def test_summary_spans_several_twins(self):
        other = Path(self.tmp.name) / "other.jsonl"
        U.record(self.log, CLAUDE_META, lane="claude")
        U.record(other, CLAUDE_META, lane="claude")
        s = U.summarize([self.log, other], days=1)
        self.assertEqual(s["calls"], 2)
        self.assertEqual(s["files"], 2)

    def test_logging_failure_never_raises(self):
        """계측이 파이프라인을 죽이지 않는다 — 다만 사유는 돌려준다."""
        blocker = Path(self.tmp.name) / "blocker"
        blocker.write_text("파일이다 — 디렉토리가 될 수 없다", encoding="utf-8")
        rec = U.record(blocker / "sub" / "usage_log.jsonl", CLAUDE_META)
        self.assertIn("error", rec)
        self.assertEqual(rec["input_tokens"], 1200)     # 레코드 자체는 온전하다

    def test_broken_line_is_skipped_not_counted(self):
        U.record(self.log, CLAUDE_META, lane="claude")
        with self.log.open("a", encoding="utf-8") as f:
            f.write("깨진 줄\n")
        self.assertEqual(U.summarize(self.log, days=1)["calls"], 1)

    def test_missing_file_is_empty_not_an_error(self):
        s = U.summarize(Path(self.tmp.name) / "absent.jsonl", days=1)
        self.assertEqual((s["calls"], s["files"]), (0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=1)
