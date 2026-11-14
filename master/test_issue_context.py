"""리뷰용 일감·태스크 컨텍스트 수집(`#946` T2) — 가짜 추적·가짜 Redmine 으로만 돈다(네트워크 0).

실행: .venv/bin/python -B master/test_issue_context.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import issue_context as IC     # noqa: E402

SHA = "a" * 40
PLAN = """\
<!-- ax:plan:begin v=2 -->
| ID | 상태 | 목표 | 대상 | 단계 | 선행 | 검증 | 근거 |
|---|---|---|---|---|---|---|---|
| T1 | 완료 | 제목 범위 파서 | master/commit_scope.py | — | — | test_commit_scope 통과 | abc1234 |
| T2 | 작업중 | 일감 컨텍스트 수집 | master/context_synth/issue_context.py | — | T1 | test_issue_context 통과 | |
| T3 | 대기 | 프롬프트 주입 | master/context_synth/review_gen.py | — | T2 | 리뷰 로그 | |
<!-- ax:plan:end -->"""
DESC = "## 배경\n자동 리뷰가 일감을 모른다.\n\n## 플랜\n\n" + PLAN + "\n\n## 메모\n끝."


def issue(desc=DESC, subject="리뷰에 일감 컨텍스트"):
    return {"id": 946, "subject": subject, "description": desc}


class Fakes:
    def __init__(self, tracked=None, got=None, raise_get=None, raise_track=None):
        self.tracked, self.got, self.raise_get, self.raise_track = tracked, got, raise_get, raise_track
        self.logs: list[str] = []
        self.gets: list[int] = []

    def track(self, root, sha):
        if self.raise_track:
            raise self.raise_track
        return self.tracked

    def get_issue(self, n):
        self.gets.append(n)
        if self.raise_get:
            raise self.raise_get
        return self.got if self.got is not None else issue()

    def run(self, message="", sha=SHA, root="/twin", **kw):
        return IC.collect(sha=sha, message=message, root=root, get_issue=self.get_issue,
                          track=self.track, logf=self.logs.append, **kw)


class TestResolve(unittest.TestCase):
    def test_track_hit(self):
        f = Fakes(tracked=946)
        ctx = f.run("feat(#946 T2): 수집")
        self.assertEqual((ctx.issue_id, ctx.source, ctx.status), (946, "track", IC.OK))
        self.assertEqual([t.id for t in ctx.tasks], ["T2"])
        self.assertEqual([t.id for t in ctx.others], ["T1", "T3"])
        self.assertEqual(len(f.logs), 1)
        self.assertTrue(f.logs[0].startswith("[리뷰 컨텍스트] #946 T2 — ok (track)"), f.logs)

    def test_track_hit_without_scope_message(self):
        f = Fakes(tracked=946)
        ctx = f.run("wip")
        self.assertEqual((ctx.source, ctx.requested, ctx.status), ("track", (), IC.OK))
        self.assertIn("태스크를 밝히지 않은", ctx.why)

    def test_message_only(self):
        f = Fakes(tracked=None)
        ctx = f.run("fix(#946 T1, T2): 둘")
        self.assertEqual((ctx.issue_id, ctx.source), (946, "message"))
        self.assertEqual([t.id for t in ctx.tasks], ["T1", "T2"])

    def test_message_legacy_tail(self):
        ctx = Fakes().run("feat: 제목 (#946)")
        self.assertEqual((ctx.issue_id, ctx.source, ctx.requested), (946, "message", ()))

    def test_no_root_skips_track(self):
        f = Fakes(raise_track=AssertionError("부르면 안 된다"))
        ctx = f.run("feat(#946 T1): x", root=None)
        self.assertEqual(ctx.source, "message")

    def test_track_error_falls_back_to_message(self):
        f = Fakes(raise_track=RuntimeError("깨진 상태"))
        ctx = f.run("feat(#946 T1): x")
        self.assertEqual((ctx.source, ctx.status), ("message", IC.OK))
        self.assertTrue(any("추적 조회 실패" in m for m in f.logs))

    def test_disagreement_prefers_track(self):
        f = Fakes(tracked=946)
        ctx = f.run("feat(#861 T2): 다른 일감")
        self.assertEqual((ctx.issue_id, ctx.source, ctx.requested), (946, "track", ()))
        self.assertEqual(ctx.other_issues, (861,))
        self.assertEqual(f.gets, [946])
        self.assertTrue(any("어긋난다" in m and "#861" in m for m in f.logs), f.logs)

    def test_multi_issue_message_with_track_picks_matching(self):
        f = Fakes(tracked=946)
        ctx = f.run("fix(#861 T2, #946 T3): x")
        self.assertEqual(ctx.requested, ("T3",))
        self.assertEqual(ctx.other_issues, (861,))
        self.assertFalse(any("어긋난다" in m for m in f.logs))

    def test_nothing_resolved(self):
        f = Fakes(tracked=None)
        ctx = f.run("docs: 메모")
        self.assertEqual((ctx.issue_id, ctx.status), (None, IC.NO_ISSUE))
        self.assertEqual(f.gets, [])
        self.assertEqual(len(f.logs), 1)
        self.assertIn("[리뷰 컨텍스트] #? —", f.logs[0])
        self.assertEqual(IC.commit_section(ctx, "docs: 메모"), "")
        self.assertEqual(IC.draft_section(ctx, "docs: 메모"), "")
        self.assertEqual(IC.range_section(ctx, []), "")

    def test_given_issue(self):
        ctx = Fakes(raise_track=AssertionError("x")).run("feat(#946 T3): x", issue_id=946)
        self.assertEqual((ctx.source, ctx.requested), ("given", ("T3",)))


class TestFailSoft(unittest.TestCase):
    def test_redmine_raises(self):
        f = Fakes(tracked=946, raise_get=OSError("연결 거부"))
        ctx = f.run("feat(#946 T1): x")
        self.assertEqual(ctx.status, IC.REDMINE_ERROR)
        self.assertIn("연결 거부", ctx.why)
        self.assertEqual(IC.commit_section(ctx, "x"), "")
        self.assertIn("redmine_error", f.logs[-1])

    def test_redmine_error_dict(self):
        ctx = Fakes(got={"error": "#946 없음 (404)"}).run("feat(#946 T1): x")
        self.assertEqual(ctx.status, IC.REDMINE_ERROR)
        self.assertIn("404", ctx.why)

    def test_issue_without_plan(self):
        ctx = Fakes(got=issue(desc="스펙만 있다")).run("feat(#946 T1): x")
        self.assertEqual(ctx.status, IC.NO_PLAN)
        self.assertEqual(ctx.spec, "스펙만 있다")
        sec = IC.commit_section(ctx, "feat(#946 T1): x")
        self.assertIn("스펙만 있다", sec)
        self.assertEqual(IC.draft_section(ctx, "feat(#946 T1): x"), "")

    def test_broken_plan(self):
        bad = "스펙\n<!-- ax:plan:begin v=2 -->\n| 엉망 |\n<!-- ax:plan:end -->"
        ctx = Fakes(got=issue(desc=bad)).run("feat(#946 T1): x")
        self.assertEqual(ctx.status, IC.PLAN_ERROR)
        self.assertIn("스펙", ctx.spec)

    def test_task_not_in_plan(self):
        f = Fakes()
        ctx = f.run("feat(#946 T2, T9): x")
        self.assertEqual(ctx.status, IC.TASK_MISSING)
        self.assertEqual(ctx.missing, ("T9",))
        self.assertEqual([t.id for t in ctx.tasks], ["T2"])
        self.assertIn("T9", IC.commit_section(ctx, "feat(#946 T2, T9): x"))
        self.assertIn("task_missing", f.logs[-1])

    def test_never_raises_on_bad_logf_free_inputs(self):
        ctx = IC.collect(sha="", message=None, root=None, get_issue=lambda n: None,
                         track=lambda r, s: None)
        self.assertEqual(ctx.status, IC.NO_ISSUE)
        ctx = IC.collect(message="feat(#946 T1): x", get_issue=lambda n: "이상한 응답")
        self.assertEqual(ctx.status, IC.REDMINE_ERROR)


class TestRender(unittest.TestCase):
    MSG = "feat(#946 T2): 수집\n\n본문 설명 줄"

    def setUp(self):
        self.ctx = Fakes(tracked=946).run(self.MSG)

    def test_spec_excludes_plan(self):
        self.assertIn("자동 리뷰가 일감을 모른다", self.ctx.spec)
        self.assertIn("## 메모\n끝.", self.ctx.spec)
        self.assertNotIn("ax:plan", self.ctx.spec)
        self.assertNotIn("## 플랜", self.ctx.spec)
        self.assertNotIn("| T1 |", self.ctx.spec)

    def test_commit_section(self):
        s = IC.commit_section(self.ctx, self.MSG)
        for part in ("작성자가 밝힌 의도", "검증된 사실이 아니다", "#946 리뷰에 일감 컨텍스트",
                     "본문 설명 줄", "자동 리뷰가 일감을 모른다", "T2 [작업중] 목표: 일감 컨텍스트 수집",
                     "대상: master/context_synth/issue_context.py", "검증: test_issue_context 통과",
                     "- T1 [완료] 제목 범위 파서", "- T3 [대기] 프롬프트 주입"):
            self.assertIn(part, s)
        self.assertNotIn("대상: master/commit_scope.py", s)    # 나머지 태스크는 한 줄만

    def test_draft_section_short(self):
        s = IC.draft_section(self.ctx, self.MSG)
        self.assertIn("커밋: feat(#946 T2): 수집", s)
        self.assertIn("T2 [작업중] 목표: 일감 컨텍스트 수집", s)
        self.assertNotIn("자동 리뷰가 일감을 모른다", s)       # 스펙 없음
        self.assertNotIn("본문 설명 줄", s)                     # 메시지 본문 없음
        self.assertNotIn("T1", s.replace("feat(#946 T2)", ""))  # 다른 태스크 없음

    def test_range_section(self):
        commits = [("1234567890abcdef" + "0" * 24, "feat(#946 T1): 파서"),
                   {"hash": "fedcba0987654321" + "0" * 24, "message": "fix(#946 T1,T2): 둘\n\n본문"},
                   {"sha": "abcabcabca" + "0" * 30, "subject": "docs: 메모 (#946)"}]
        s = IC.range_section(self.ctx, commits)
        self.assertIn("자동 리뷰가 일감을 모른다", s)
        for tid in ("T1", "T2", "T3"):
            self.assertIn(f"- {tid} [", s)
        self.assertIn("- 1234567890 [T1] feat(#946 T1): 파서", s)
        self.assertIn("- fedcba0987 [T1,T2] fix(#946 T1,T2): 둘", s)
        self.assertIn("- abcabcabca [—] docs: 메모 (#946)", s)
        self.assertIn("작성자가 밝힌 의도", s)


if __name__ == "__main__":
    unittest.main()
