"""`#726` 지휘 세션 잇기 — 읽을 때 잇는다 (사용자 결정 2026-10-09 (가)).

🔴 이 파일이 못 박는 것:
  ⑴ codex `thread.started.thread_id` 가 meta·`Usage` 의 `session_id` 로 실린다
  ⑵ `usage.record` 가 그것을 파견 기록의 `session_id` 로 쓴다 — 없으면 칸이 없다
  ⑶ `[usage]` 줄은 종전 문구 뒤에 `비캐시 · 캐시(%)` 와 `세션 <8자>` 만 붙인다
  ⑷ rollout 지표는 `parse_codex` 와 같은 규칙(누적값이 바뀐 `token_count` 만)으로 센다
  ⑸ 사본이 없으면 `None`/「미수집」 — 0 이 아니다. 화면에 절대 경로가 없다

실 LLM·SSH·서비스 0. 임시 디렉토리만 쓴다. 실측 사본이 있으면 손 측정값(#766)과 대조하고,
없으면 건너뛴다고 찍는다. `.venv/bin/python master/test_conductor_metrics.py`
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.work import infer as I                       # noqa: E402
from master.work import session_usage as S               # noqa: E402
from master.work import usage as U                       # noqa: E402
from master.work.runner import _unwrap                   # noqa: E402
from master.work.usage_dashboard import build_report     # noqa: E402
from master.webui import usage_page as P                 # noqa: E402

SID = "01a11fa5-154c-7dd3-88f6-ad6c83738b0b"
CODEX_EVENTS = "\n".join([
    json.dumps({"type": "thread.started", "thread_id": SID}),
    json.dumps({"type": "turn.started"}),
    json.dumps({"type": "item.completed",
                "item": {"type": "agent_message", "text": "RESULT: DONE"}}),
    json.dumps({"type": "turn.completed",
                "usage": {"input_tokens": 870003, "cached_input_tokens": 797312,
                          "output_tokens": 5927, "reasoning_output_tokens": 100}}),
])


def _tc(total, inp, cached, out):
    return json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": {"total_tokens": total},
        "last_token_usage": {"input_tokens": inp, "cached_input_tokens": cached,
                             "output_tokens": out}}}})


def _tool(kind):
    return json.dumps({"type": "response_item", "payload": {"type": kind}})


ROLLOUT = [
    json.dumps({"type": "session_meta", "payload": {"id": SID}}),
    _tc(110, 100, 0, 10),
    _tc(110, 100, 0, 10),              # 같은 누적값 반복 — 세지 않는다
    _tool("function_call"),
    _tool("custom_tool_call"),
    _tool("function_call_output"),     # 도구 결과는 호출이 아니다
    json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": None}}),
    _tc(330, 200, 150, 20),
    _tool("local_shell_call"),
    _tc(630, 280, 250, 20),
    "not json",
]


class ThreadIdTests(unittest.TestCase):
    def test_parse_codex_jsonl_carries_session_id(self):
        text, meta = U.parse_codex_jsonl(CODEX_EVENTS)
        self.assertEqual(text, "RESULT: DONE")
        self.assertEqual(meta["session_id"], SID)
        # runner·wcommit 이 쓰는 같은 진입으로도 남는다(직접·세션1 모두 이 문자열을 푼다)
        _body, meta2 = _unwrap(CODEX_EVENTS)
        self.assertEqual(meta2.get("session_id"), SID)

    def test_absent_thread_started_means_no_key(self):
        _text, meta = U.parse_codex_jsonl(CODEX_EVENTS.split("\n", 1)[1])
        self.assertNotIn("session_id", meta)

    def test_thread_started_alone_is_not_a_codex_result(self):
        self.assertIsNone(U.parse_codex_jsonl(CODEX_EVENTS.split("\n", 1)[0]))

    def test_lane_usage_carries_session_id_through_envelope(self):
        u = U.usage_from_codex_events(CODEX_EVENTS)
        self.assertEqual(u.session_id, SID)
        meta = U.meta_from_usage(u)
        self.assertEqual(meta["session_id"], SID)
        _body, back = _unwrap(U.envelope("RESULT: DONE", meta))
        self.assertEqual(back["session_id"], SID)
        self.assertNotIn("session_id", U.meta_from_usage(U.Usage(lane="agy", input_tokens=1)))


class RecordTests(unittest.TestCase):
    def test_record_writes_session_id_only_when_present(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "usage_log.jsonl"
            _t, meta = U.parse_codex_jsonl(CODEX_EVENTS)
            a = U.record(log, meta, task_id="t1", worker="192.168.0.43", mode="codex")
            b = U.record(log, {"source": "agy", "usage": {"input_tokens": 3}}, task_id="t2")
            rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(a["session_id"], SID)
        self.assertEqual(rows[0]["session_id"], SID)
        self.assertNotIn("session_id", b)
        self.assertNotIn("session_id", rows[1])
        self.assertEqual(rows[0]["input_tokens"], 870003)     # 기존 칸은 그대로


class UsageLineTests(unittest.TestCase):
    def _rec(self, meta):
        return U.record("/dev/null/never", meta, task_id="t1", mode="codex")

    def test_codex_line_appends_split_and_session(self):
        _t, meta = U.parse_codex_jsonl(CODEX_EVENTS)
        rec = self._rec(meta)
        line = I.usage_line("t1", rec, "codex", meta)
        self.assertTrue(line.startswith("[usage] t1 lane=codex mode=codex 입력 870,003 · 출력 5,927 · 비용 미상"),
                        line)
        self.assertIn(" · 비캐시 72,691 · 캐시 797,312(91.6%)", line)
        self.assertTrue(line.endswith(" · 세션 01a11fa5"), line)

    def test_unknown_parts_are_not_appended(self):
        meta = {"source": "codex", "cost_unknown": True,
                "usage": {"input_tokens": 10, "output_tokens": 2}}   # 캐시 미상
        rec = self._rec(meta)
        line = I.usage_line("t1", rec, "codex", meta)
        self.assertNotIn("비캐시", line)
        self.assertNotIn("세션", line)
        self.assertEqual(line, "[usage] t1 lane=codex mode=codex 입력 10 · 출력 2 · 비용 미상")

    def test_claude_input_excludes_cache(self):
        meta = {"usage": {"input_tokens": 100, "output_tokens": 5,
                          "cache_read_input_tokens": 300, "cache_creation_input_tokens": 100},
                "total_cost_usd": 0.01}
        rec = U.record("/dev/null/never", meta, task_id="t1", mode="claude")
        line = I.usage_line("t1", rec, "claude", meta)
        self.assertIn(" · 비캐시 200 · 캐시 300(60.0%)", line)


class MetricsTests(unittest.TestCase):
    def test_metrics_on_synthetic_rollout(self):
        m = S.conductor_metrics(ROLLOUT)
        self.assertEqual(m, {"calls": 3, "first_input": 100, "last_input": 280,
                             "input_sum": 580, "uncached_sum": 180, "output_sum": 50,
                             "tool_calls": 3})
        # 호출 수는 parse_codex 와 같은 규칙이다
        self.assertEqual(len(S.parse_codex(ROLLOUT).records), m["calls"])

    def test_empty_rollout_is_none_not_zero(self):
        m = S.conductor_metrics([])
        self.assertEqual(m["calls"], 0)
        self.assertIsNone(m["first_input"])
        self.assertIsNone(m["last_input"])

    def test_find_rollout(self):
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            self.assertIsNone(S.find_rollout(SID, "AXCluster", "192.168.0.43", raw))
            d = raw / "AXCluster" / "192.168.0.43" / "codex" / "sessions" / "2026" / "10" / "09"
            d.mkdir(parents=True)
            f = d / f"rollout-2026-10-09T16-51-15-{SID}.jsonl"
            f.write_text("\n".join(ROLLOUT), encoding="utf-8")
            self.assertEqual(S.find_rollout(SID, "AXCluster", "192.168.0.43", raw), f)
            self.assertIsNone(S.find_rollout(SID, "AXCluster", "192.168.0.2", raw))
            for bad in ("*", "../x", "a/b", ""):
                self.assertIsNone(S.find_rollout(bad, "AXCluster", "192.168.0.43", raw), bad)
            self.assertIsNone(S.find_rollout(SID, "..", "192.168.0.43", raw))
            self.assertIsNone(S.find_rollout(SID, "AXCluster", "*", raw))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.projects_root = root / "projects"
        self.queue_root = root / "queue"
        self.session_store = root / "usage" / "sessions"
        self.raw = root / "usage" / "raw"
        self.projects_root.mkdir()
        (self.projects_root / "projects.yaml").write_text(
            "version: 1\nactive: Alpha\nprojects:\n  - Alpha\n", encoding="utf-8")
        (self.projects_root / "Alpha").mkdir()
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    def add(self, **kw):
        rec = {"ts": "2026-10-14 10:00:00", "work_id": "", "task_id": "", "worker": "",
               "mode": "", "rc": 0, "source": "dispatch", "model": "", "lane": "codex",
               "measured": True, "input_tokens": 0, "output_tokens": 0, "cache_read": 0,
               "cache_create": 0, "reasoning_tokens": 0, **kw}
        with (self.projects_root / "Alpha" / "usage_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def report(self, **kw):
        return build_report(projects_root=self.projects_root, queue_root=self.queue_root,
                            session_store=self.session_store, now=self.now, **kw)

    def test_split_values_and_totals_unchanged(self):
        self.add(lane="codex", input_tokens=1000, cache_read=900, output_tokens=10)
        self.add(lane="claude", model="claude-opus", input_tokens=50, cache_read=400,
                 cache_create=30, output_tokens=5)
        self.add(lane="codex", measured=False, input_tokens=0)
        r = self.report()
        t = r["totals"]
        self.assertEqual(t["input_uncached"], 100 + 80)
        self.assertEqual(t["input_cached"], 900 + 400)
        self.assertEqual(t["tokens"], (1000 + 10) + (50 + 5 + 400 + 30))    # 합계 정의 그대로
        rows = {m["family"]: m for m in r["models"]}
        self.assertEqual((rows["codex"]["input_uncached"], rows["codex"]["input_cached"]), (100, 900))
        self.assertEqual((rows["claude"]["input_uncached"], rows["claude"]["input_cached"]), (80, 400))
        self.assertEqual(r["conductor_sessions"], [])

    def test_conductor_metrics_and_not_collected(self):
        other = "01a11fa5-0000-7000-8000-000000000001"
        self.add(task_id="t1", worker="192.168.0.43", mode="codex", session_id=SID,
                 input_tokens=580, cache_read=400, output_tokens=50)
        self.add(task_id="t2", worker="192.168.0.2", mode="codex", session_id=other,
                 ts="2026-10-14 11:00:00", input_tokens=5, output_tokens=1)
        self.add(task_id="t3", worker="192.168.0.2", mode="codex", input_tokens=5)  # 옛 기록
        d = self.raw / "Alpha" / "192.168.0.43" / "codex" / "sessions" / "2026" / "10" / "14"
        d.mkdir(parents=True)
        (d / f"rollout-2026-10-14T10-00-00-{SID}.jsonl").write_text("\n".join(ROLLOUT),
                                                                     encoding="utf-8")
        r = self.report()
        rows = {x["task_id"]: x for x in r["conductor_sessions"]}
        self.assertEqual(set(rows), {"t1", "t2"})
        self.assertEqual(r["conductor_sessions"][0]["task_id"], "t2")      # 최근 순
        self.assertTrue(rows["t1"]["collected"])
        self.assertEqual(rows["t1"]["metrics"]["calls"], 3)
        self.assertEqual(rows["t1"]["metrics"]["uncached_sum"], 180)
        self.assertFalse(rows["t2"]["collected"])
        self.assertIsNone(rows["t2"]["metrics"])
        self.assertNotIn(str(self.raw), json.dumps(r, ensure_ascii=False))
        html = P.render(r).decode("utf-8")
        self.assertIn("지휘 세션", html)
        self.assertIn("미수집", html)
        self.assertIn("01a11fa5", html)
        self.assertNotIn(SID, html)                       # 앞 8자만
        self.assertNotIn(self.temp.name, html)            # 절대 경로 없음
        self.assertIn("비캐시 입력", html)
        self.assertIn("<b>190</b><span>비캐시 입력</span>", html)    # 180 + t2·t3 의 5·5

    def test_page_read_error_and_no_rows(self):
        report = {"source": "dispatch", "totals": {}, "conductor_sessions": [
            {"at": "x", "task_id": "t", "worker": "w", "mode": "codex", "session_id": SID,
             "collected": False, "read_error": True, "metrics": None}]}
        html = P.render(report).decode("utf-8")
        self.assertIn("읽기 실패", html)
        self.assertIn("<b>—</b><span>비캐시 입력</span>", html)          # 모르면 0 이 아니다
        empty = P.render({"source": "dispatch", "totals": {}}).decode("utf-8")
        self.assertIn("세션 id 가 있는 작업 실행 기록 없음", empty)
        self.assertNotIn("지휘 세션</h2>", P.render({"source": "session", "totals": {}}).decode("utf-8"))


# 실측 사본(#766 손 측정) — 있으면 대조하고 없으면 건너뛴다
REAL = Path.home() / "ax-state" / "usage" / "raw" / "AXCluster"
EXPECT = {  # host: (calls, first, last, input_sum, uncached_sum, tool_calls)
    "192.168.0.43": (22, 17818, 59112, 870003, 72691, 21),
    "192.168.0.2": (25, 22166, 80365, 1584132, 71428, 24),
    "192.168.0.33": (49, 18961, 89456, 3174684, 85532, 48),
}


class RealFixtureTests(unittest.TestCase):
    def test_hand_measured_numbers(self):
        for host, want in EXPECT.items():
            hits = sorted((REAL / host / "codex" / "sessions" / "2026" / "10" / "09")
                          .glob("rollout-2026-10-09T16-51-1*.jsonl")) if REAL.is_dir() else []
            if not hits:
                print(f"  [건너뜀] 실측 사본 없음 — {host}")
                continue
            sid = hits[0].name[-len(SID) - len(".jsonl"):-len(".jsonl")]
            self.assertEqual(S.find_rollout(sid, "AXCluster", host, REAL.parent), hits[0])
            with hits[0].open(encoding="utf-8") as fh:
                m = S.conductor_metrics(fh)
            got = (m["calls"], m["first_input"], m["last_input"], m["input_sum"],
                   m["uncached_sum"], m["tool_calls"])
            print(f"  [실측] {host} {got}")
            self.assertEqual(got, want, host)


if __name__ == "__main__":
    unittest.main(verbosity=1)
