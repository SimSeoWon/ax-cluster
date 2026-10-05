"""[DOC] 집계 조각의 결정적 검사 골조. 임시 숫자 로그·큐 일감만 사용, 실 LLM/Redmine 0.
공개 API 동결. 아래 사례는 실제 fixture와 기대 수치로 검사, 구현을 그대로 복제하지 않는다.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import sys

# 통합 검사는 스크립트로 단독 실행한다(`tests/integration/checks.json`) — 저장소 루트를 경로에 둔다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.work.usage_dashboard import build_report


class UsageDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.projects_root = root / "projects"
        self.queue_root = root / "queue"
        self.session_store = root / "sessions"
        self.projects_root.mkdir()
        (self.projects_root / "projects.yaml").write_text(
            "version: 1\nactive: Alpha\nprojects:\n  - Alpha\n  - Beta\n",
            encoding="utf-8",
        )
        for name in ("Alpha", "Beta"):
            (self.projects_root / name).mkdir()
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    def report(self, **kwargs):
        return build_report(
            projects_root=self.projects_root, queue_root=self.queue_root,
            session_store=self.session_store, now=self.now, **kwargs,
        )

    def add_call(self, project, ts, *, work_id="", model="claude-sonnet-4-5",
                 lane="claude", source="dispatch", measured=True, rc=0,
                 input_tokens=1, output_tokens=2, cache_read=0,
                 cache_create=0, reasoning_tokens=0, mode=""):
        record = {
            "ts": ts, "work_id": work_id, "task_id": "", "worker": "",
            "mode": mode, "rc": rc, "source": source, "model": model,
            "lane": lane, "measured": measured,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_read": cache_read, "cache_create": cache_create,
            "reasoning_tokens": reasoning_tokens,
        }
        with (self.projects_root / project / "usage_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def add_work(self, work_id, project, issue_id, title, *, archived=False):
        parent = self.queue_root / ".claude" / "tasks"
        if archived:
            parent /= "_archive"
        path = parent / work_id / "_request.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            f"work_id: {work_id}\nproject: {project}\n"
            f"title: {title}\nredmine_issue_id: {issue_id}\n"
            "---\n",
            encoding="utf-8",
        )

    def add_session(self, host, tool, records, *, project=None, name="sample"):
        path = self.session_store / host / tool / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "host": host, "tool": tool, "session_id": name,
            "origin": f"{name}.jsonl", "collected_at": "2026-10-15T00:00:00",
            "project": project, "records": records,
        }), encoding="utf-8")

    def test_calendar_buckets_and_timezone(self):
        self.add_call("Alpha", "2026-10-03T14:59:00Z", input_tokens=1, output_tokens=0)
        self.add_call("Alpha", "2026-10-03T15:01:00Z", input_tokens=2, output_tokens=0)
        self.add_call("Alpha", "2026-10-04 23:59:00", input_tokens=3, output_tokens=0)
        self.add_call("Alpha", "2026-10-05T00:00:00+09:00", input_tokens=4, output_tokens=0)
        self.add_call("Alpha", "2026-09-30T14:59:00Z", input_tokens=5, output_tokens=0)
        daily = self.report(start="2026-10-04", end="2026-10-05")
        self.assertEqual(daily["timezone"], "Asia/Seoul")
        self.assertEqual(daily["totals"]["calls"], 3)
        self.assertEqual(daily["totals"]["tokens"], 9)
        self.assertEqual(
            {(b["date"], b["calls"]) for b in daily["buckets"]},
            {("2026-10-04", 2), ("2026-10-05", 1)},
        )
        weekly = self.report(period="weekly", start="2026-10-01", end="2026-10-05")
        self.assertEqual(
            {(b["date"], b["calls"]) for b in weekly["buckets"]},
            {("2026-09-28", 3), ("2026-10-05", 1)},
        )
        monthly = self.report(period="monthly", start="2026-09-30", end="2026-10-05")
        self.assertEqual(
            {(b["date"], b["calls"]) for b in monthly["buckets"]},
            {("2026-09-01", 1), ("2026-10-01", 4)},
        )

    def test_issue_linkage_and_filters(self):
        self.add_work("active-alpha", "Alpha", 101, "Alpha queue title")
        self.add_work("archived-beta", "Beta", 202, "Beta archived title", archived=True)
        self.add_call("Alpha", "2026-10-10 10:00:00", work_id="active-alpha",
                      model="claude-sonnet-4-5", lane="claude", input_tokens=4)
        self.add_call("Beta", "2026-10-11 10:00:00", work_id="archived-beta",
                      model="gpt-5-codex", lane="codex", input_tokens=5)
        self.add_call("Alpha", "2026-10-12 10:00:00", work_id="missing",
                      model="claude-sonnet-4-5", lane="claude", input_tokens=6)
        all_data = self.report(start="2026-10-10", end="2026-10-12")
        self.assertEqual(all_data["totals"]["calls"], 3)
        self.assertEqual(all_data["totals"]["issues"], 2)
        self.assertEqual(all_data["totals"]["unlinked_calls"], 1)
        issues = {row["issue_id"]: row for row in all_data["issues"]}
        self.assertEqual(set(issues), {101, 202})
        self.assertEqual((issues[101]["title"], issues[101]["project"],
                          issues[101]["work_ids"]),
                         ("Alpha queue title", "Alpha", ["active-alpha"]))
        self.assertEqual((issues[202]["title"], issues[202]["project"]),
                         ("Beta archived title", "Beta"))
        filtered = self.report(project="Alpha", family="claude",
                               start="2026-10-10", end="2026-10-11")
        self.assertEqual(filtered["totals"]["calls"], 1)
        self.assertEqual(filtered["totals"]["tokens"], 6)
        self.assertEqual([r["issue_id"] for r in filtered["issues"]], [101])
        self.assertEqual(filtered["totals"]["unlinked_calls"], 0)
        self.assertEqual(sum(r["tokens"] for r in filtered["models"]), 6)
        self.assertEqual(sum(r["tokens"] for r in filtered["buckets"]), 6)

    def test_token_accounting_and_unmeasured(self):
        self.add_call("Alpha", "2026-10-10 10:00:00", model="claude-sonnet-4-5",
                      lane="claude", input_tokens=10, output_tokens=20,
                      cache_read=30, cache_create=40, reasoning_tokens=5)
        self.add_call("Alpha", "2026-10-10 11:00:00", model="gpt-5-codex",
                      lane="codex", input_tokens=100, output_tokens=50,
                      cache_read=60, reasoning_tokens=10, rc=1)
        self.add_call("Alpha", "2026-10-10 12:00:00", model="local-model",
                      lane="local:local-model", input_tokens=0, output_tokens=0)
        self.add_call("Alpha", "2026-10-10 13:00:00", model="",
                      lane="agy", measured=False, input_tokens=0, output_tokens=0)
        data = self.report(start="2026-10-10", end="2026-10-10")
        totals = data["totals"]
        self.assertEqual((totals["calls"], totals["measured_calls"],
                          totals["unmeasured_calls"], totals["failed_calls"]),
                         (4, 3, 1, 1))
        self.assertEqual((totals["input_tokens"], totals["output_tokens"],
                          totals["cache_read"], totals["cache_create"],
                          totals["reasoning_tokens"], totals["tokens"]),
                         (110, 70, 90, 40, 15, 250))
        self.assertEqual(sum(r["tokens"] or 0 for r in data["models"]), 250)
        self.assertEqual(sum(r["tokens"] or 0 for r in data["buckets"]), 250)
        # #728: 모델 키가 없는 agy 는 gemini 계열 · 'Antigravity(모델 미상)' 표기 (사용자 2026-10-04)
        self.assertTrue(any(r["model"] == "Antigravity(모델 미상)" for r in data["models"]))
        zero = self.report(family="local", start="2026-10-10", end="2026-10-10")
        self.assertEqual(zero["totals"]["tokens"], 0)
        gemini = self.report(family="gemini", start="2026-10-10", end="2026-10-10")
        self.assertEqual(gemini["totals"]["calls"], 1)
        self.assertIsNone(gemini["totals"]["tokens"])
        self.assertIsNone(gemini["models"][0]["tokens"])
        unknown = self.report(family="unknown", start="2026-10-10", end="2026-10-10")
        self.assertEqual(unknown["totals"]["calls"], 0)

    def test_agy_lane_is_gemini(self):
        # #728: agy 실측 행(모델 키 없음) · 모델이 생긴 행 · 브로커 행이 서로 갈린다.
        self.add_call("Alpha", "2026-10-10 10:00:00", model="", lane="agy",
                      input_tokens=4869, output_tokens=26, cache_read=8136, reasoning_tokens=25)
        self.add_call("Alpha", "2026-10-10 11:00:00", model="gemini-2.5-pro", lane="agy",
                      input_tokens=10, output_tokens=5)
        self.add_call("Alpha", "2026-10-10 12:00:00", model="gemma4:e4b",
                      lane="local:gemma4:e4b", input_tokens=7, output_tokens=3)
        data = self.report(start="2026-10-10", end="2026-10-10")
        rows = {(r["family"], r["model"]): r for r in data["models"]}
        self.assertEqual(set(rows), {("gemini", "Antigravity(모델 미상)"),
                                     ("gemini", "gemini-2.5-pro"), ("local", "gemma4:e4b")})
        # agy 의 total_tokens 는 input+output(캐시 제외) — 실측 4869+26=4895
        self.assertEqual(rows[("gemini", "Antigravity(모델 미상)")]["tokens"], 4895)
        only = self.report(family="gemini", start="2026-10-10", end="2026-10-10")
        self.assertEqual((only["totals"]["calls"], only["totals"]["tokens"]), (2, 4910))

    def test_conductor_mode_fills_family_when_model_and_lane_empty(self):
        # 2026-10-04 실측: claude 지휘자 레코드는 model·lane 이 비어 unknown 으로 샜다.
        self.add_call("Alpha", "2026-10-10 10:00:00", model="", lane="", mode="claude",
                      input_tokens=14, output_tokens=2652,
                      cache_read=310548, cache_create=42710, rc=1)
        self.add_call("Alpha", "2026-10-10 11:00:00", model="", lane="", mode="codex",
                      input_tokens=100, output_tokens=50, cache_read=60)
        self.add_call("Alpha", "2026-10-10 12:00:00", model="", lane="", mode="lane",
                      input_tokens=7, output_tokens=3, cache_read=1000)
        # 명시 증거(lane·model)가 mode 를 이긴다.
        self.add_call("Alpha", "2026-10-10 13:00:00", model="", lane="local:gemma4:e4b",
                      mode="claude", input_tokens=5, output_tokens=5, cache_read=900)
        self.add_call("Alpha", "2026-10-10 14:00:00", model="gpt-5-codex", lane="",
                      mode="claude", input_tokens=1, output_tokens=1, cache_read=800)
        data = self.report(start="2026-10-10", end="2026-10-10")
        rows = {(r["family"], r["model"]): r for r in data["models"]}
        self.assertEqual(set(rows), {("claude", "모델 미상"), ("codex", "모델 미상"),
                                     ("codex", "gpt-5-codex"), ("unknown", "모델 미상"),
                                     ("local", "gemma4:e4b")})
        claude = rows[("claude", "모델 미상")]
        self.assertEqual((claude["calls"], claude["failed_calls"], claude["tokens"]),
                         (1, 1, 14 + 2652 + 310548 + 42710))
        self.assertEqual(rows[("codex", "모델 미상")]["tokens"], 150)
        self.assertEqual(rows[("unknown", "모델 미상")]["tokens"], 10)
        self.assertEqual(rows[("local", "gemma4:e4b")]["tokens"], 10)
        self.assertEqual(rows[("codex", "gpt-5-codex")]["tokens"], 2)
        only_claude = self.report(family="claude", start="2026-10-10", end="2026-10-10")
        self.assertEqual(only_claude["totals"]["calls"], 1)
        self.assertEqual(only_claude["totals"]["tokens"], 355924)
        self.assertEqual(sum(r["tokens"] or 0 for r in data["buckets"]),
                         data["totals"]["tokens"])

    def test_session_source_is_separate(self):
        self.add_call("Alpha", "2026-10-10 10:00:00", input_tokens=999)
        self.add_session("local", "claude", [{
            "ts": "2026-10-10T01:00:00Z", "model": "claude-sonnet-4-5",
            "input": 2, "output": 3, "cache_read": 4,
            "cache_create": 5, "reasoning": 1,
        }])
        session = self.report(source="session", start="2026-10-10", end="2026-10-10")
        self.assertEqual(session["totals"]["calls"], 1)
        self.assertEqual(session["totals"]["tokens"], 14)
        self.assertEqual(session["issues"], [])
        self.assertEqual(session["totals"]["issues"], 0)
        self.assertEqual(session["totals"]["unlinked_calls"], 0)
        dispatch = self.report(source="dispatch", start="2026-10-10", end="2026-10-10")
        self.assertEqual(dispatch["totals"]["calls"], 1)
        self.assertEqual(dispatch["totals"]["tokens"], 1001)
        restricted = self.report(source="session", project="Alpha",
                                 start="2026-10-10", end="2026-10-10")
        self.assertEqual(restricted["totals"]["calls"], 0)
        self.assertEqual(restricted["issues"], [])
        self.assertTrue(restricted["warnings"])

    def test_session_project_filter_uses_snapshot_project(self):
        codex = {"ts": "2026-10-10T01:00:00Z", "model": "gpt-5-codex",
                 "input": 10, "output": 5, "cache_read": 8, "reasoning": 2}
        self.add_session("192.168.0.2", "codex", [codex], project="Alpha", name="a")
        self.add_session("192.168.0.2", "codex", [codex], project="Beta", name="b")
        self.add_session("local", "codex", [codex], name="unassigned")
        self.add_call("Alpha", "2026-10-10 10:00:00", input_tokens=999)
        every = self.report(source="session", start="2026-10-10", end="2026-10-10")
        self.assertEqual(every["totals"]["calls"], 3)
        self.assertEqual(every["totals"]["tokens"], 45)          # Codex 입력은 캐시 포함
        alpha = self.report(source="session", project="Alpha",
                            start="2026-10-10", end="2026-10-10")
        self.assertEqual(alpha["totals"]["calls"], 1)
        self.assertEqual(alpha["totals"]["tokens"], 15)
        self.assertEqual(alpha["issues"], [])
        self.assertEqual(alpha["models"][0]["family"], "codex")
        dispatch = self.report(source="dispatch", project="Alpha",
                               start="2026-10-10", end="2026-10-10")
        self.assertEqual(dispatch["totals"]["tokens"], 1001)       # 두 소스는 합산하지 않는다

    def test_all_source_takes_one_origin_per_family(self):
        # 사용자 결정 2026-10-04: 모두 보기 = claude·codex 는 세션, 그 밖은 작업 실행 기록
        codex = {"ts": "2026-10-10T01:00:00Z", "model": "gpt-5-codex", "input": 10, "output": 5}
        claude = {"ts": "2026-10-10T01:00:00Z", "model": "claude-sonnet-4-5",
                  "input": 1, "output": 1, "cache_read": 1, "cache_create": 1}
        self.add_session("192.168.0.2", "codex", [codex], project="Alpha", name="a")
        self.add_session("local", "claude", [claude], name="unassigned")
        self.add_work("w1", "Alpha", 7, "일감")
        self.add_call("Alpha", "2026-10-10 10:00:00", work_id="w1", input_tokens=999)  # claude 파견 — 세션과 겹친다
        self.add_call("Alpha", "2026-10-10 10:00:00", work_id="w1", model="", lane="codex",
                      input_tokens=888)                                              # codex 파견 — 겹친다
        self.add_call("Alpha", "2026-10-10 10:00:00", work_id="w1", model="", lane="agy",
                      input_tokens=30, output_tokens=0)
        self.add_call("Beta", "2026-10-10 10:00:00", model="", lane="local:gemma4:e4b",
                      input_tokens=20, output_tokens=0)
        every = self.report(source="all", start="2026-10-10", end="2026-10-10")
        self.assertEqual(every["source"], "all")
        self.assertEqual(every["totals"]["calls"], 4)
        self.assertEqual(every["totals"]["tokens"], 15 + 4 + 30 + 20)   # 999·888 은 세지 않는다
        self.assertEqual(sorted({m["family"] for m in every["models"]}),
                         ["claude", "codex", "gemini", "local"])
        self.assertEqual(every["issues"], [])
        self.assertTrue(any("모두 보기" in w for w in every["warnings"]))
        alpha = self.report(source="all", project="Alpha", start="2026-10-10", end="2026-10-10")
        self.assertEqual(alpha["totals"]["tokens"], 15 + 30)           # 미분류 세션·Beta 제외
        only = self.report(source="all", family="codex", start="2026-10-10", end="2026-10-10")
        self.assertEqual(only["totals"]["tokens"], 15)

    def test_agy_session_is_gemini_and_all_keeps_dispatch(self):
        # #748: agy 세션 스냅샷은 gemini · 합계는 #728 계약대로 입력+출력(캐시 제외)
        #       모두 보기에서 gemini 는 여전히 작업 실행 기록이 맡는다(헤드리스 agy 는 양쪽에 남는다)
        agy = {"ts": "2026-10-10T01:00:00Z", "model": "Gemini 3.6 Flash (High)",
               "input": 5083, "output": 194, "cache_read": 16284}
        self.add_session("local", "agy", [agy, {**agy, "model": ""}], project="Alpha", name="g")
        self.add_call("Alpha", "2026-10-10 10:00:00", model="", lane="agy",
                      input_tokens=30, output_tokens=0)
        session = self.report(source="session", start="2026-10-10", end="2026-10-10")
        self.assertEqual(session["totals"]["invalid_records"], 0)
        rows = {(r["family"], r["model"]): r for r in session["models"]}
        self.assertEqual(set(rows), {("gemini", "Gemini 3.6 Flash (High)"),
                                     ("gemini", "Antigravity(모델 미상)")})
        self.assertEqual(session["totals"]["tokens"], 2 * (5083 + 194))
        every = self.report(source="all", start="2026-10-10", end="2026-10-10")
        self.assertEqual((every["totals"]["calls"], every["totals"]["tokens"]), (1, 30))

    def test_request_read_errors_and_invalid_records_are_separate(self):
        self.add_work("work-1", "Alpha", 716, "사용량 검사")
        self.add_call("Alpha", "2026-10-10T10:00:00Z", work_id="work-1")
        secret = "SECRET-TOKEN-DO-NOT-SHOW"
        detail = f"{secret} {self.queue_root}"
        cases = ((PermissionError(detail), "read_errors", "invalid_records"),
                 (ValueError(detail), "invalid_records", "read_errors"),
                 (TypeError(detail), "invalid_records", "read_errors"))
        for error, counted, other in cases:
            with self.subTest(error=type(error).__name__):
                with patch("master.work.usage_dashboard._read_md", side_effect=error):
                    data = self.report(start="2026-10-10", end="2026-10-10")
                self.assertEqual(data["totals"][counted], 1)
                self.assertEqual(data["totals"][other], 0)
                self.assertEqual(data["totals"]["calls"], 1)
                self.assertEqual(data["totals"]["unlinked_calls"], 1)
                self.assertIn("일감 연결 자료 중 읽지 못한 항목이 있습니다.", data["warnings"])
                visible = json.dumps(data, ensure_ascii=False)
                self.assertNotIn(secret, visible)
                self.assertNotIn(str(self.queue_root), visible)

    def test_validation_and_malformed_records(self):
        invalid = (
            {"start": "2026-02-30"}, {"end": "yesterday"},
            {"start": "2026-10-11", "end": "2026-10-10"},
            {"start": "2025-01-01", "end": "2026-10-10"},
            {"period": "hourly"}, {"family": "other"},
            {"source": "both"}, {"project": "Unregistered"},
        )
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.report(**options)
        secret = "SECRET-TOKEN-DO-NOT-SHOW"
        path = self.projects_root / "Alpha" / "usage_log.jsonl"
        path.write_text(
            "{" + secret + "\n"
            + json.dumps({"ts": "invalid", "lane": "claude", "measured": True,
                          "input_tokens": 3, "output_tokens": 2, "secret": secret}) + "\n"
            + json.dumps({"ts": "2026-10-10 10:00:00", "lane": "claude",
                          "model": "claude-sonnet-4-5", "measured": True,
                          "input_tokens": 2, "output_tokens": 3, "rc": 0}) + "\n",
            encoding="utf-8",
        )
        data = self.report(start="2026-10-10", end="2026-10-10")
        self.assertEqual(data["totals"]["calls"], 1)
        self.assertEqual(data["totals"]["tokens"], 5)
        self.assertGreaterEqual(data["totals"]["invalid_records"], 2)
        self.assertTrue(data["warnings"])
        visible = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(secret, visible)
        self.assertNotIn(str(self.projects_root), visible)


if __name__ == "__main__":
    unittest.main()
