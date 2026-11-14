"""커밋 제목 범위 파서(`#946` T1) — 순수 함수 검사, 네트워크·git 0.

실행: .venv/bin/python -B master/test_commit_scope.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import commit_scope as CS     # noqa: E402
from master import plan_metrics as PM     # noqa: E402
from master.commit_scope import Scope     # noqa: E402


def one(subject: str) -> list[tuple]:
    return [(s.issue_id, s.tasks, s.form) for s in CS.parse(subject)]


class TestCommitScope(unittest.TestCase):
    def test_single_task(self):
        self.assertEqual(one("feat(#946 T1): 파서 추가"), [(946, ("T1",), "scope")])

    def test_issue_only_scope(self):
        self.assertEqual(one("fix(#946): 고침"), [(946, (), "scope")])

    def test_multiple_tasks_variants(self):
        for s in ("fix(#946 T1,T2): x", "fix(#946 T1, T2): x", "fix(#946 T1 T2): x",
                  "fix(#946 T1·T2): x"):
            self.assertEqual(one(s), [(946, ("T1", "T2"), "scope")], s)

    def test_task_dedupe_and_normalise(self):
        self.assertEqual(one("fix(#946 T01, T1, T2): x"), [(946, ("T1", "T2"), "scope")])

    def test_multiple_issues(self):
        self.assertEqual(one("fix(#861 T2, #857 T7): x"),
                         [(861, ("T2",), "scope"), (857, ("T7",), "scope")])
        self.assertEqual(one("fix(#861 T2 T3, #857): x"),
                         [(861, ("T2", "T3"), "scope"), (857, (), "scope")])

    def test_same_issue_twice_merges(self):
        self.assertEqual(one("fix(#946 T1, #946 T3): x"), [(946, ("T1", "T3"), "scope")])

    def test_issue_prefix_boundary(self):
        # `#86` 은 `#861` 의 일부로 잡히지 않는다 — 숫자 전체가 하나의 번호다.
        self.assertEqual(one("fix(#861 T2): x"), [(861, ("T2",), "scope")])
        self.assertNotIn(86, [s.issue_id for s in CS.parse("fix(#861 T2): x")])

    def test_task_word_boundary(self):
        self.assertEqual(one("fix(#946 TT1 T1x T3): x"), [(946, ("T3",), "scope")])

    def test_hyphen_type_and_bang(self):
        self.assertEqual(one("chore-deps(#12 T4): x"), [(12, ("T4",), "scope")])
        self.assertEqual(one("feat(#12 T4)!: x"), [(12, ("T4",), "scope")])

    def test_legacy_tail(self):
        self.assertEqual(one("feat: 제목 (#368)"), [(368, (), "legacy")])
        self.assertEqual(one("docs: record relay quota validation and live observations (#368)"),
                         [(368, (), "legacy")])
        # 범위 칸에 일감 번호가 없으면 끝 괄호를 본다.
        self.assertEqual(one("feat(webui): 화면 (#368)"), [(368, (), "legacy")])

    def test_legacy_tail_must_be_single_issue_at_end(self):
        self.assertEqual(one("feat: 제목 (#826 · #852)"), [])
        self.assertEqual(one("feat: 제목 (#368) 뒤에 더"), [])
        self.assertEqual(one("feat: 후속 #368 정리"), [])

    def test_no_scope(self):
        self.assertEqual(one("docs: hand off issue 368 completion and deployment checkpoint"), [])
        self.assertEqual(one("feat(webui): 화면"), [])
        self.assertEqual(one(""), [])
        self.assertEqual(one("그냥 고침 (#368)"), [])        # 종류 접두가 없다

    def test_uppercase_and_garbage(self):
        self.assertEqual(one("FEAT(#946 T1): x"), [])
        self.assertEqual(one("Feat: x (#946)"), [])
        self.assertEqual(one("(#946 T1): x"), [])
        self.assertEqual(one("feat (#946 T1): x"), [])
        self.assertEqual(one("feat(#abc T1): x"), [])

    def test_merge_subjects(self):
        self.assertEqual(one("Merge branch 'issue/946'"), [])
        self.assertEqual(one("Merge pull request #12 from x/y"), [])
        self.assertEqual(one("Revert \"feat(#946 T1): x\""), [])

    def test_message_helpers(self):
        msg = "\n\n  feat(#946 T2): 수집  \n\n본문에 fix(#1 T9) 가 있어도 안 본다\n"
        self.assertEqual(CS.subject_of(msg), "feat(#946 T2): 수집")
        self.assertEqual(CS.parse_message(msg), [Scope(946, ("T2",), "scope")])
        self.assertEqual(CS.subject_of(""), "")
        self.assertEqual(CS.parse_message(None), [])

    def test_plan_metrics_shares_regex(self):
        self.assertIs(PM.WORK_SCOPE_RE, CS.SCOPE_RE)

    def test_plan_metrics_issue_commits_unchanged(self):
        def git(_args):
            rows = [("a" * 40, "fix(#861 T2, #857 T7): x"), ("b" * 40, "feat: 후속 #861 메모"),
                    ("c" * 40, "feat: 제목 (#861)"), ("d" * 40, "fix(#8610 T1): x")]
            return "".join(f"\x1e{h}\x1f{b}\x1fmaster/x.py\n" for h, b in rows)
        got = {c["hash"][0]: (c["primary"], c["work"]) for c in PM.issue_commits(861, git=git)}
        self.assertEqual(got, {"a": (True, True), "b": (True, False), "c": (True, False)})


if __name__ == "__main__":
    unittest.main()
