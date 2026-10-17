"""#823: 임시 main과 가짜 판정기로 수집/전달 계약을 검증한다. 실 LLM 호출 없음."""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.context_synth import dismissal_candidates as D, fix_index as F
from master.batch import gates, run as B


class CandidatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "twin"
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "a.py").write_text("def f():\n    return 1\n")
        self.git("add", "a.py")
        self.git("commit", "-m", "fixture")
        review = self.root / "reviews" / "Tester" / "_archive" / "2026-W01" / "a.md"
        review.parent.mkdir(parents=True)
        review.write_text("# review\n- 커밋: `" + "a" * 40 + "`\n- 작성자: Tester\n"
                          "### a.py\n## 1. 변경분 코딩 컨벤션\n"
                          "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n"
                          "| a.py | 타입 | 타입 표기 없음 | 1 | low |\n")
        plan = self.root / "plans" / "Tester" / "2026-W01" / "a.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("---\ntype: improvement_plan\ntarget_file: a.py\nstatus: pending\n---\n타입 권고\n")
        F.sweep(self.root)
        self.paths = SimpleNamespace(root=self.root, repo=self.repo,
                                     usage_log=self.root / "usage.jsonl")
        self.index = F.index_path(self.root).read_bytes()
        self.plan = plan
        self.plan_before = plan.read_bytes()
        self.calls = []

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def chat(self, prompt):
        self.calls.append(prompt)
        data = json.loads(prompt.split("DATA_JSON\n", 1)[1])
        # #825: 소스는 싣지 않는다 — 대상 경로와 고정 SHA 만 준다
        self.assertNotIn("source", data)
        self.assertEqual(data["item"]["file"], "a.py")
        self.assertIn(D.main_sha(self.repo), prompt)
        self.assertNotIn("return 1", prompt)
        return json.dumps({"verdict": "candidate", "reason": "타입 표기 권고",
                           "evidence": [{"file": "a.py", "line": 1, "text": "def f():"}]})

    def collect(self, **kwargs):
        return D.collect(self.paths, chat=self.chat,
                         now=datetime(2026, 10, 17, 10), **kwargs)

    def test_archived_review_old_plan_and_state_unchanged(self):
        (self.repo / "a.py").write_text("UNCOMMITTED\n")
        got = self.collect()
        self.assertTrue(got["complete"])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(F.index_path(self.root).read_bytes(), self.index)
        self.assertEqual(self.plan.read_bytes(), self.plan_before)
        self.assertEqual((self.repo / "a.py").read_text(), "UNCOMMITTED\n")
        self.collect()
        self.assertEqual(len(self.calls), 2)
        with patch.object(D, "collect", side_effect=AssertionError("목록 수집 금지")):
            public = F.list_docs(self.root, do_sweep=False)
            private = F.list_docs(self.root, do_sweep=False, candidate_details=True)
        self.assertEqual(public["dismissal_candidates"]["count"], 2)
        self.assertNotIn("타입 표기 권고", json.dumps(public, ensure_ascii=False))
        self.assertIn("타입 표기 권고", json.dumps(private, ensure_ascii=False))
        F.set_status(self.root, "P1", "dismissed", by="human")
        self.assertEqual(D.read_results(self.root)["count"], 1)

    def test_main_change_stale_and_new_collection(self):
        self.collect()
        (self.repo / "a.py").write_text("def f():\n    return 2\n")
        self.git("add", "a.py")
        self.git("commit", "-m", "new main")
        self.assertTrue(all(r["stale"] for r in D.read_results(self.root)["candidates"]))
        self.collect()
        self.assertFalse(any(r["stale"] for r in D.read_results(self.root)["candidates"]))
        self.assertEqual(len(self.calls), 4)

    def test_invalid_evidence_is_unjudged(self):
        def bad(_):
            return json.dumps({"verdict": "candidate", "reason": "wrong",
                               "evidence": [{"file": "a.py", "line": 99, "text": "x"}]})
        got = D.collect(self.paths, chat=bad)
        self.assertEqual(len(got["unjudged"]), 2)
        self.assertEqual(D.read_results(self.root)["count"], 0)

    def test_resolved_is_listed_separately_with_checked_evidence(self):
        good = {"verdict": "resolved", "reason": "이미 수정됨",
                "evidence": [{"file": "a.py", "line": 2, "text": "    return 1"}]}
        D.collect(self.paths, chat=lambda _: json.dumps(good))
        got = D.read_results(self.root, details=True)
        self.assertEqual((got["count"], got["resolved_count"]), (0, 2))
        self.assertTrue(all(r["verdict"] == "resolved" and r["reason"] == "이미 수정됨"
                            for r in got["candidates"]))
        from master.webui import fixes_page
        from master.test_fixes_surface import FakeRegistry
        _, body = fixes_page.render("T", registry=FakeRegistry({"T": self.root}, "T"))
        self.assertIn("주말 기각 후보 0건 · 이미 해소 후보 2건", body)
        self.assertNotIn("이미 수정됨", body)
        D._path(self.root).unlink()
        bad = {**good, "evidence": [{"file": "a.py", "line": 2, "text": "    return 9"}]}
        got = D.collect(self.paths, chat=lambda _: json.dumps(bad))
        self.assertEqual(len(got["unjudged"]), 2)
        self.assertEqual(D.read_results(self.root)["resolved_count"], 0)

    def test_unjudged_reason_is_kept_but_not_listed(self):
        got = D.collect(self.paths, chat=lambda _: json.dumps(
            {"verdict": "unjudged", "reason": "이미 수정됨", "evidence": []}))
        self.assertEqual(got["unjudged"], [])
        entries = json.loads(D._path(self.root).read_text())["entries"]
        self.assertTrue(all(e["reason"] == "이미 수정됨" for e in entries.values()))
        self.assertEqual(D.read_results(self.root)["count"], 0)

    def test_malformed_or_resolved_response_is_not_candidate(self):
        for answer in (None, "garbage", '{"verdict":"applied"}', '[]'):
            with self.subTest(answer=answer):
                D._path(self.root).unlink(missing_ok=True)
                got = D.collect(self.paths, chat=lambda _: answer)
                self.assertEqual(len(got["unjudged"]), 2)
                self.assertEqual(D.read_results(self.root)["count"], 0)

    def test_prompt_carries_no_source_regardless_of_size(self):
        # #825: 에이전트가 작업 디렉터리에서 직접 읽는다. 상용 판정엔 크기 한도도 없다(2026-10-17).
        big = "def f():\n" + "    x = '" + "가" * 30000 + "'\n    return 1\n"
        (self.repo / "a.py").write_text(big)
        self.git("add", "a.py")
        self.git("commit", "-m", "big")
        seen = []

        def judge(prompt):
            seen.append(prompt)
            return json.dumps({"verdict": "candidate", "reason": "r",
                               "evidence": [{"file": "a.py", "line": 1, "text": "def f():"}]})
        got = D.collect(self.paths, chat=judge)
        self.assertTrue(got["complete"])
        self.assertEqual(got["unjudged"], [])
        self.assertEqual(len(seen), 2)
        self.assertTrue(all("가" * 100 not in p and len(p) < 5000 for p in seen),
                        [len(p) for p in seen])
        self.assertEqual(D.read_results(self.root)["count"], 2)

    def test_real_chain_gets_pinned_worktree_at_main(self):
        sha = D.main_sha(self.repo)
        seen = []

        def fake_chat(prompt, *, workdir=None, **_):
            wd = Path(workdir)
            head = subprocess.run(["git", "-C", str(wd), "rev-parse", "HEAD"], check=True,
                                  capture_output=True, text=True).stdout.strip()
            seen.append((wd, head, (wd / "a.py").read_text(), wd.is_relative_to(self.repo)))
            return json.dumps({"verdict": "candidate", "reason": "r",
                               "evidence": [{"file": "a.py", "line": 1, "text": "def f():"}]})
        (self.repo / "a.py").write_text("UNCOMMITTED\n")
        with patch("master.context_synth.review_gen.commercial_chat", fake_chat):
            got = D.collect(self.paths, now=datetime(2026, 10, 17, 10))
        self.assertEqual(got["unjudged"], [])
        self.assertEqual(len(seen), 2)
        self.assertEqual(len({w for w, *_ in seen}), 1, "수집 한 번에 트리 하나")
        wd, head, text, inside = seen[0]
        self.assertEqual(head, sha)
        self.assertEqual(text, "def f():\n    return 1\n")
        self.assertFalse(inside, "트리는 저장소 밖에 있다")
        self.assertFalse(wd.exists(), "수집 뒤 트리를 지운다")
        listed = self.git("worktree", "list", "--porcelain")
        self.assertNotIn(str(wd), listed)
        self.assertEqual((self.repo / "a.py").read_text(), "UNCOMMITTED\n")

    def test_real_chain_worktree_failure_is_unjudged(self):
        calls = []
        with patch("master.context_synth.pinned_tree.pinned_worktree",
                   side_effect=RuntimeError("x")) as pw, \
                patch("master.context_synth.review_gen.commercial_chat",
                      lambda *a, **k: calls.append(1)):
            got = D.collect(self.paths, now=datetime(2026, 10, 17, 10))
        self.assertEqual(len(got["unjudged"]), 2)
        self.assertEqual(calls, [])
        self.assertEqual(pw.call_count, 1, "같은 수집에서 재시도하지 않는다")

    def test_incomplete_run_resumes_next_weekend_not_same_weekend(self):
        runs = []

        def execute(_):
            runs.append(1)
            return {"ok": True, "complete": False}

        fake = B.BatchDef(gates.DISMISSAL_CANDIDATES, "test", lambda _: 1,
                          execute, gates.should_run_dismissal_candidates)
        with patch.object(B, "BATCHES", [fake]):
            first_run = B.run(self.paths, {}, now=datetime(2026, 10, 17, 10))
            # 미완료여도 주간 마커는 남는다 — 같은 주말에 매시 재실행하지 않는다(#823).
            self.assertIsNotNone(gates.read_marker(self.root, "dismissal_candidates"))
            self.assertTrue(first_run[0].ran)
            self.assertIn("다음 주말", first_run[0].verdict)
            B.run(self.paths, {}, now=datetime(2026, 10, 17, 11))
            B.run(self.paths, {}, now=datetime(2026, 10, 18, 10))
            self.assertEqual(len(runs), 1)
            B.run(self.paths, {}, now=datetime(2026, 10, 24, 10))
            self.assertEqual(len(runs), 2)

    def test_public_list_only_displays_summary(self):
        from master.webui import fixes_page
        from master.test_fixes_surface import FakeRegistry
        self.collect()
        reg = FakeRegistry({"T": self.root}, "T")
        status, body = fixes_page.render("T", registry=reg)
        self.assertEqual(status, 200)
        self.assertIn("주말 기각 후보 2건", body)
        self.assertNotIn("타입 표기 권고", body)
        self.assertNotIn("a.py", body)

    def test_weekend_gate_independent_and_failure_preserves_list(self):
        s = gates.DISMISSAL_CANDIDATES
        sat = datetime(2026, 10, 17, 10)
        self.assertTrue(gates.should_run_dismissal_candidates(s, {}, self.root, input_count=2, now=sat).run)
        self.assertFalse(gates.should_run_dismissal_candidates(s, {}, self.root, input_count=2,
                                                            now=datetime(2026, 10, 16, 10)).run)
        gates.write_marker(self.root, s.key, now=sat)
        self.assertFalse(gates.should_run_dismissal_candidates(s, {}, self.root, input_count=2, now=sat).run)
        self.assertTrue(any(b.schedule.key == s.key for b in B.BATCHES))
        D._path(self.root).write_text("broken")
        got = F.list_docs(self.root, do_sweep=False)
        self.assertEqual(len(got["docs"]), 2)
        self.assertIn("error", got["dismissal_candidates"])


if __name__ == "__main__":
    unittest.main()
