"""#855 T2 — RAG 평가 라벨: 원본 로그와 분리 · 직접 채택은 산출물 근거 · 집계는 행별 판정과 맞는다.

    .venv/bin/python -B master/test_rag_labels.py
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.context_search import rag_labels as L                 # noqa: E402
from master.context_search import search_log as log              # noqa: E402


class RagLabelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = SimpleNamespace(root=Path(self.tmp.name), name="demo")
        hit = {"file_id": "master/a.md", "excerpt": "x", "meta": {"content_hash": "h1"}}
        with log.search_context(task_type="user_command", user_request="855 진행해", issue_id=855,
                                issue_id_source="issue_lock") as ctx:
            self.s1 = log.log_search(self.paths, query="q1", hits=[hit])["search_id"]
            self.s2 = log.log_search(self.paths, query="q2", hits=[hit, {"file_id": "b.md"}])["search_id"]
            self.r1 = ctx["request_id"]
        with log.search_context(task_type="user_command", user_request="다른 요청") as ctx:
            self.s3 = log.log_search(self.paths, query="q3", hits=[hit])["search_id"]
            self.r2 = ctx["request_id"]
        self.log_before = (Path(self.tmp.name) / "search_logs").read_bytes() \
            if (Path(self.tmp.name) / "search_logs").is_file() else None

    def _logs(self):
        return sorted((p.name, p.read_bytes()) for p in Path(self.tmp.name).rglob("*.jsonl")
                      if "rag_labels" not in p.parts)

    def test_add_validates_and_keeps_log(self):
        before = self._logs()
        rec = L.add(self.paths, target="search", target_id=self.s1, evidence="있음", adoption="직접",
                    status="확정", basis=["커밋 853dbd3", "master/x.py:12"], reviewer="claude")
        self.assertEqual(rec["doc_hashes"], {"master/a.md": "h1"}, "판정 당시 문서 해시")
        self.assertEqual(rec["issue_ids"], [855])
        self.assertEqual(self._logs(), before, "원본 검색 로그는 바뀌지 않는다")
        for kw, why in (
                (dict(adoption="직접", basis=["같은 모듈이 나중에 수정됨"]), "산출물 근거 없는 직접"),
                (dict(adoption="직접", evidence="없음", basis=["853dbd3"]), "근거 없음인데 직접"),
                (dict(status="확정", reviewer="", basis=["x.py:1"]), "확정인데 검증자 없음"),
                (dict(status="확정", reviewer="r", basis=[]), "확정인데 근거 없음"),
                (dict(evidence="많음"), "모르는 값")):
            args = dict(target="search", target_id=self.s2, evidence="있음", adoption="간접",
                        status="후보", basis=[], reviewer="")
            args.update(kw)
            with self.assertRaises(L.LabelError, msg=why):
                L.add(self.paths, **args)
        with self.assertRaises(L.LabelError):
            L.add(self.paths, target="search", target_id="없는id", evidence="있음", adoption="간접")
        with self.assertRaises(L.LabelError):
            L.add(self.paths, target="request", target_id="없는요청", evidence="있음", adoption="간접")

    def test_latest_wins_and_summary_counts(self):
        L.add(self.paths, target="search", target_id=self.s1, evidence="일부", adoption="확인불가")
        L.add(self.paths, target="search", target_id=self.s1, evidence="있음", adoption="간접",
              status="확정", basis=["#855 노트"], reviewer="sim")
        L.add(self.paths, target="search", target_id=self.s3, evidence="없음", adoption="확인불가")
        L.add(self.paths, target="request", target_id=self.r1, evidence="있음", adoption="직접",
              basis=["#855 T1"], reviewer="claude")
        rep = L.summary(self.paths)
        self.assertEqual(rep["totals"], {"searches": 3, "requests": 2, "docs": 4})
        s = rep["counts"]["search"]
        self.assertEqual((s["labeled"], s["unlabeled"]), (2, 1))
        self.assertEqual(s["evidence"]["있음"], 1, "최신 판정만 센다")
        self.assertEqual(s["adoption"], {"직접": 0, "간접": 1, "확인불가": 1})
        self.assertEqual(rep["counts"]["request"]["adoption"]["직접"], 1)
        self.assertEqual(L.check(rep), [])
        only = L.summary(self.paths, issue_id=855)
        self.assertEqual(only["totals"]["searches"], 2, "관측 연결된 검색만")
        self.assertEqual(only["counts"]["search"]["labeled"], 1)
        self.assertEqual(L.check(only), [])

    def test_check_catches_mismatch(self):
        L.add(self.paths, target="search", target_id=self.s1, evidence="있음", adoption="간접")
        rep = L.summary(self.paths)
        bad = dict(rep, counts={**rep["counts"], "search": {**rep["counts"]["search"], "labeled": 2}})
        self.assertTrue(any("판정 수" in p for p in L.check(bad)))
        bad = dict(rep, counts={**rep["counts"], "search": {
            **rep["counts"]["search"], "adoption": {"직접": 1, "간접": 0, "확인불가": 0}}})
        self.assertTrue(any("adoption" in p for p in L.check(bad)))
        bad = dict(rep, totals={**rep["totals"], "searches": 9})
        self.assertTrue(any("분모" in p for p in L.check(bad)))
        # 「반환됐지만 채택 증거 없음」이 직접으로 집계된 행은 잡는다(파일을 손으로 고친 경우)
        row = dict(rep["rows"][0], adoption="직접", basis=["같은 파일이 수정됨"])
        bad = dict(rep, rows=[row], counts={**rep["counts"], "search": {
            **rep["counts"]["search"], "adoption": {"직접": 1, "간접": 0, "확인불가": 0}}})
        self.assertTrue(any("산출물 근거 없이" in p for p in L.check(bad)))

    def test_cli(self):
        with patch("master.context_search.paths.resolve", lambda name="": self.paths):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = L._main(["add", "--search", self.s1, "--evidence", "있음", "--adoption", "직접"])
            self.assertEqual(rc, 2, "산출물 근거 없는 직접은 CLI 도 거절")
            self.assertIn("거절", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L._main(["add", "--request", self.r2, "--evidence", "없음",
                                          "--adoption", "확인불가"]), 0)
                self.assertEqual(L._main(["summary"]), 0)
                self.assertEqual(L._main(["check"]), 0)
                self.assertEqual(L._main(["list", "--request", self.r2]), 0)

    def test_mcp_tools(self):
        import json
        from master.projects import mcp_server as M
        with patch("master.context_search.paths.resolve", lambda name="": self.paths):
            bad = json.loads(M.rag_label_tool("있음", "직접", search_id=self.s1, basis=["같은 모듈 수정"]))
            self.assertFalse(bad["ok"])
            self.assertIn("산출물 근거", bad["error"])
            both = json.loads(M.rag_label_tool("있음", "간접", search_id=self.s1, request_id=self.r1))
            self.assertFalse(both["ok"])
            ok = json.loads(M.rag_label_tool("있음", "직접", search_id=self.s1, status="확정",
                                             basis=["커밋 0ff78ea"], reviewer="claude"))
            self.assertTrue(ok["ok"], ok)
            got = json.loads(M.rag_labels_tool(issue_id=855))
            self.assertEqual(got["problems"], [])
            self.assertEqual(got["counts"]["search"]["labeled"], 1)
            self.assertEqual(got["totals"]["searches"], 2)
            one = json.loads(M.rag_labels_tool(request_id="없는요청"))
            self.assertEqual(one["rows"], [])


if __name__ == "__main__":
    unittest.main()
