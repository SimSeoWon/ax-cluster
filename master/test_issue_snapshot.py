"""#979 T1 — 일감 스냅샷: 제목·「문제·맥락」·작업중 태스크·실패·캐시."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import issue_snapshot as S

PLAN = """## 플랜

<!-- ax:plan:begin v=3 autonomy=0.5 -->
| ID | 상태 | 목표 | 대상 | 단계 | 선행 | 검증 | 근거 |
|---|---|---|---|---|---|---|---|
| T1 | 완료 | 후보 동결 | a | — | — | 검사 | 커밋 abc |
| T2 | 작업중 | 정답 확정 | b | — | T1 | 확인 | |
| T3 | 작업중 | 벤치 보강 | c | — | T1 | rc0 | |
| T4 | 대기 | 보고 | d | — | T2 | 보고 | |
<!-- ax:plan:end -->
"""

SPEC = """등록자 본문 첫 줄.

## 확정 스펙 (착수 전 인터뷰)

<!-- ax:spec:begin v=1 -->
## 문제·맥락
원문이 「N번 진행하자」뿐이라
그 순간 요구를 알 수 없다.

둘째 문단은 싣지 않는다.

## 초반 분류
기존 기능 수정.
<!-- ax:spec:end -->
"""


def fetcher(desc, subject="[AX] 제목", calls=None):
    def f(n):
        if calls is not None:
            calls.append(n)
        return {"subject": subject, "description": desc}
    return f


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        S.clear_cache()
        self.addCleanup(S.clear_cache)

    def test_ok_with_spec_and_active_tasks(self):
        snap = S.snapshot(211, fetch=fetcher(SPEC + "\n" + PLAN))
        self.assertEqual(snap["status"], S.OK)
        self.assertEqual(snap["issue_id"], 211)
        self.assertEqual(snap["subject"], "[AX] 제목")
        self.assertEqual(snap["context"], "원문이 「N번 진행하자」뿐이라 그 순간 요구를 알 수 없다.")
        self.assertEqual([t["id"] for t in snap["tasks"]], ["T2", "T3"])
        self.assertEqual(snap["tasks"][0], {"id": "T2", "goal": "정답 확정", "state": "작업중"})
        self.assertEqual(snap["tasks_note"], "")
        self.assertTrue(snap["fetched_at"])
        self.assertEqual(S.task_line(snap), "T2 정답 확정 · T3 벤치 보강")

    def test_no_spec_uses_body_first_paragraph_and_clips(self):
        body = "## 배경\n" + "가" * 300 + "\n\n둘째\n\n" + PLAN
        snap = S.snapshot(5, fetch=fetcher(body))
        self.assertEqual(len(snap["context"]), S.CONTEXT_MAX)
        self.assertTrue(snap["context"].endswith("…"))

    def test_no_plan_and_no_active(self):
        snap = S.snapshot(6, fetch=fetcher("본문만"))
        self.assertEqual((snap["tasks"], snap["tasks_note"]), ([], "플랜 없음"))
        self.assertEqual(snap["context"], "본문만")
        self.assertEqual(S.task_line(snap), "플랜 없음")
        idle = PLAN.replace("| 작업중 |", "| 대기 |")
        snap = S.snapshot(7, fetch=fetcher(idle))
        self.assertEqual(snap["tasks_note"], "작업중 태스크 없음")

    def test_broken_plan_is_noted_not_raised(self):
        broken = "본문\n<!-- ax:plan:begin v=2 -->\n| 깨진 |\n"
        snap = S.snapshot(8, fetch=fetcher(broken))
        self.assertEqual(snap["status"], S.OK)
        self.assertTrue(snap["tasks_note"].startswith("플랜 형식 오류"))

    def test_fetch_failure_is_status_and_not_cached(self):
        calls = []
        def boom(n):
            calls.append(n)
            raise TimeoutError("timed out")
        snap = S.snapshot(9, fetch=boom)
        self.assertEqual(snap["status"], S.FETCH_FAILED)
        self.assertIn("TimeoutError", snap["why"])
        self.assertNotIn("subject", snap)
        self.assertEqual(S.task_line(snap), "")
        S.snapshot(9, fetch=boom)
        self.assertEqual(calls, [9, 9])

    def test_cache_reuses_within_ttl_and_refetches_after(self):
        calls, t = [], [100.0]
        f = fetcher(PLAN, calls=calls)
        a = S.snapshot(10, fetch=f, now=lambda: t[0])
        t[0] += S.TTL - 1
        b = S.snapshot(10, fetch=f, now=lambda: t[0])
        self.assertEqual(calls, [10])
        self.assertEqual(a, b)
        b["subject"] = "바꿈"
        self.assertNotEqual(S.snapshot(10, fetch=f, now=lambda: t[0])["subject"], "바꿈")
        t[0] += 2
        S.snapshot(10, fetch=f, now=lambda: t[0])
        self.assertEqual(calls, [10, 10])

    def test_default_fetch_uses_public_read_with_timeout(self):
        import inspect
        src = inspect.getsource(S._fetch_public)
        self.assertIn("timeout=TIMEOUT", src)
        self.assertNotIn("api_key", src)
        self.assertEqual(S.TIMEOUT, 2.0)


if __name__ == "__main__":
    unittest.main()
