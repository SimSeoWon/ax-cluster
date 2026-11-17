"""#980 — 검색 유용성 유추: 연결 해석 · 판정 규칙 · --apply · (LLM 0 · 네트워크 0 · 실 git 아님)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import search_usefulness as SU      # noqa: E402


def fake_git(commits: dict, log: str = ""):
    """commits: sha → 바뀐 파일 목록. log 는 `git log --grep` 결과."""
    calls = []

    def git(repo, *args):
        calls.append(args)
        if args[0] == "show":
            return "\n".join(commits.get(args[-1], []))
        if args[0] == "log":
            return log
        return ""
    git.calls = calls
    return git


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.ctx = base / "twin" / "context"
        for doc in ("master/a.md", "master/b.md", "master/c.md", "master/test_a.md", "client/x/b.md"):
            (self.ctx / doc).parent.mkdir(parents=True, exist_ok=True)
            (self.ctx / doc).write_text("문서", encoding="utf-8")
        self.reports = base / "repo" / "reports"
        self.reports.mkdir(parents=True)
        self.twin = base / "twin"
        p = patch("master.context_synth.issue_track.rounds", lambda root, n: self.track.get(n, []))
        p.start()
        self.addCleanup(p.stop)
        self.track = {}


class LinkTests(unittest.TestCase):
    def test_observed_candidate_multiple_none(self):
        obs = SU.link_of([{"issue_id": 211, "issue_id_source": "issue_lock", "user_request": "응!"}])
        self.assertEqual((obs.issue_id, obs.kind, obs.source), (211, SU.OBSERVED, "issue_lock"))
        cand = SU.link_of([{"user_request": "#864 진행해"}, {"user_request": "864번 다시"}])
        self.assertEqual((cand.issue_id, cand.kind, cand.source), (864, SU.CANDIDATE, "원문 번호 후보"))
        many = SU.link_of([{"user_request": "936번 진행해 그리고 2026 계획"}])
        self.assertIsNone(many.issue_id)
        self.assertIn("여럿", many.why)
        self.assertIsNone(SU.link_of([{"user_request": "단독으로 진행해줘"}]).issue_id)
        two = SU.link_of([{"issue_id": 1}, {"issue_id": 2}])
        self.assertIsNone(two.issue_id, "한 요청에 관측 일감이 둘이면 연결하지 않는다")
        self.assertEqual(SU.link_of([{"issue_id": 7, "user_request": "999번"}]).kind, SU.OBSERVED,
                         "관측이 원문 번호보다 먼저")

    def test_group_requests(self):
        g = SU.group_requests([{"request_id": "r1", "task_type": "user_command"},
                               {"request_id": "r1", "task_type": "user_command"},
                               {"request_id": "r2", "task_type": "context_synthesis"},
                               {"search_id": "s3", "task_type": "user_command"}])
        self.assertEqual({k: len(v) for k, v in g.items()}, {"r1": 2, "s3": 1})


class EvidenceTests(Fixture):
    def test_issue_track_first_then_message_and_tests_excluded(self):
        self.track = {211: [{"hashes": [{"sha": "aaaa111"}, {"sha": "bbbb222"}]}]}
        git = fake_git({"aaaa111": ["master/a.py", "master/test_a.py", "docs/x.md"],
                        "bbbb222": ["master/b.py", "master/gone.py"]}, log="cccc333\n")
        ev = SU.evidence(211, twin_root=self.twin, context_root=self.ctx, reports_root=self.reports, git=git)
        self.assertEqual(ev.commit_source, "issue_track")
        self.assertEqual(sorted(ev.commit_docs), ["master/a.md", "master/b.md"],
                         "테스트·문서·색인에 없는 파일은 빠진다")
        self.assertIn("커밋 aaaa111: master/a.py", ev.commit_docs["master/a.md"])
        self.assertFalse(any(c[0] == "log" for c in git.calls), "추적이 있으면 메시지로 찾지 않는다")

        git = fake_git({"cccc333": ["master/c.py"]}, log="cccc333\n")
        ev = SU.evidence(864, twin_root=self.twin, context_root=self.ctx, reports_root=self.reports, git=git)
        self.assertEqual((ev.commit_source, sorted(ev.commit_docs)), ("message", ["master/c.md"]))
        grep = next(c for c in git.calls if c[0] == "log")
        self.assertIn("--grep=#864([^0-9]|$)", grep, "#8640 같은 다른 번호를 잡지 않는다")

    def test_reports_own_file_whole_others_only_mention_lines(self):
        (self.reports / "203-211-eval.md").write_text(
            "# 203\n표 줄 master/a.py\n그리고 b.py 도\n", encoding="utf-8")
        (self.reports / "150-other.md").write_text(
            "무관 master/c.py\n#211 관련 줄 master/b.py\n#2110 다른 일감 master/c.py\n", encoding="utf-8")
        ev = SU.evidence(211, twin_root=self.twin, context_root=self.ctx, reports_root=self.reports,
                         git=fake_git({}))
        self.assertEqual(sorted(ev.report_docs), ["master/a.md", "master/b.md"])
        self.assertIn("reports/150-other.md:2", ev.report_docs["master/b.md"])
        self.assertNotIn("master/c.md", ev.report_docs, "남의 리포트는 #211 언급 줄만 본다")
        self.assertEqual(ev.reports, ["reports/150-other.md", "reports/203-211-eval.md"])
        self.assertEqual(ev.commit_source, "")

    def test_bare_name_maps_only_when_unique(self):
        (self.reports / "9-211.md").write_text("b.py 와 a.py\n", encoding="utf-8")
        ev = SU.evidence(211, twin_root=self.twin, context_root=self.ctx, reports_root=self.reports,
                         git=fake_git({}))
        self.assertEqual(sorted(ev.report_docs), ["master/a.md"], "b.md 는 둘이라 고르지 않는다")


if __name__ == "__main__":
    unittest.main()
