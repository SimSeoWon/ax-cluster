"""#211 T3 — KR 벤치: 주석 규칙 · 정답표 호환 · 유형별 지표 · 평가 로그 분리 · 색인 사본."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import bench_kr
from master.context_search import search_log
from master.context_search.paths import ProjectPaths

HEADER = "# query\texpected(|구분)\ttier(natural|structural)\tsource\tconfirmed(y/n)"


class CommentRuleTests(unittest.TestCase):
    def test_hash_space_or_alone_is_comment(self):
        for ln in (HEADER, "#", "#\tx", "#  메모"):
            self.assertTrue(bench_kr.is_comment(ln), ln)

    def test_issue_number_query_is_data(self):
        for ln in ("#837 RAG 검색 로그", "#a", "질의 # 안"):
            self.assertFalse(bench_kr.is_comment(ln), ln)


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, rel, lines):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_legacy_five_columns_from_twin_default(self):
        self.write("analysis/kr_ground_truth.tsv", [
            HEADER, "미션 완료\ta.md|b.md\tnatural\tlog:1\ty",
            "미확정\tc.md\tnatural\tlog:2\tn", "빈 기대\t\tnatural\tlog:3\ty",
            "짧은 행\ta.md"])
        rows = bench_kr.load_ground_truth(SimpleNamespace(root=self.root))
        self.assertEqual(rows, [{"query": "미션 완료", "expected": ["a.md", "b.md"],
                                 "tier": "natural", "source": "log:1"}])

    def test_seven_columns_and_hash_query_via_gt(self):
        p = self.write("x/gt.tsv", [
            HEADER + "\tcandidate_id\trequest_id",
            "#837 RAG 검색 로그 웹UI\twebui/rag_logs.md\tnatural\tlog:f\ty\tQ01\tr1",
            "한글 질의\tz.md\tnatural\tlog:g\ty\tQ02\tr2"])
        rows = bench_kr.load_ground_truth(gt=str(p))
        self.assertEqual([r["id"] for r in rows], ["Q01", "Q02"])
        self.assertEqual(rows[0]["query"], "#837 RAG 검색 로그 웹UI")
        self.assertEqual(rows[0]["request_id"], "r1")

    def test_repo_ground_truth_loads_all_thirty(self):
        p = Path(__file__).resolve().parents[1] / "reports" / "203-211-ground-truth.tsv"
        if not p.is_file():
            self.skipTest("정답표 없음")
        rows = bench_kr.load_ground_truth(gt=str(p))
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({r["id"] for r in rows}), 30)
        self.assertIn("Q01", {r["id"] for r in rows})


class MetricTests(unittest.TestCase):
    def test_lang_type(self):
        self.assertEqual(bench_kr.lang_type("일감 생명주기 잠금"), "hangul_only")
        self.assertEqual(bench_kr.lang_type("issue_lock 잠금"), "mixed")
        self.assertEqual(bench_kr.lang_type("issue_lock flow"), "other")

    def test_rank_and_metrics(self):
        self.assertEqual(bench_kr.rank_of(["x", "b", "a"], ["a", "b"]), 2)
        self.assertEqual(bench_kr.rank_of(["x"], ["a"]), 0)
        m = bench_kr.metrics([1, 3, 0, 6])
        self.assertEqual((m["hit@1"], m["hit@5"], m["n"]), (0.25, 0.5, 4))
        self.assertAlmostEqual(m["MRR"], (1 + 1 / 3 + 1 / 6) / 4)
        self.assertEqual(bench_kr.metrics([])["n"], 0)


class FakeSearcher:
    """실 검색 경로처럼 끝에 `log_search` 를 부른다 — 억제가 실제로 막는지 본다."""

    def __init__(self, paths):
        self.paths = paths
        self.closed = False
        self.bm25 = SimpleNamespace(search=lambda q, limit: [("bm.md", 1.0), ("a.md", .5)])

    def search(self, q, limit):
        files = ["v.md", "a.md"] if "식별" in q or "_" in q else ["v.md", "x.md", "y.md", "a.md"]
        search_log.log_search(self.paths, query=q, hits=[{"file_id": f} for f in files])
        return [SimpleNamespace(file_id=f) for f in files]

    def close(self):
        self.closed = True


class RunVariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = SimpleNamespace(root=Path(self.tmp.name), name="demo",
                                     ontology=Path(self.tmp.name) / "ontology")
        self.rows = [{"id": "Q1", "query": "한글 전용 질의", "expected": ["a.md"]},
                     {"id": "Q2", "query": "식별 issue_lock 질의", "expected": ["a.md"]}]

    def test_variants_split_by_lang_and_write_no_log(self):
        from master.context_search import bm25 as B
        before = B.KR_ROUTING
        made = []
        def factory(p):
            made.append(FakeSearcher(p))
            return made[-1]
        res = bench_kr.run_all(self.paths, self.rows, searcher_factory=factory)
        self.assertEqual(list(res), ["baseline", "kr_on", "gated", "kr+gated"])
        self.assertEqual([p["rank"] for p in res["baseline"]["per_query"]], [4, 2])
        self.assertEqual([p["rank"] for p in res["gated"]["per_query"]], [2, 2])
        self.assertEqual(res["gated"]["by_lang"]["hangul_only"]["n"], 1)
        self.assertEqual(res["gated"]["by_lang"]["mixed"]["MRR"], 0.5)
        self.assertEqual(B.KR_ROUTING, before)
        self.assertTrue(all(s.closed for s in made))
        self.assertFalse(search_log.logging_suppressed())
        self.assertEqual(list(self.paths.root.rglob("*.jsonl")), [])

    def test_log_written_outside_suppression_only(self):
        r = search_log.log_search(self.paths, query="밖", hits=[{"file_id": "a"}])
        self.assertTrue(r["written"])
        with search_log.suppress_logging():
            r2 = search_log.log_search(self.paths, query="안", hits=[{"file_id": "a"}])
        self.assertEqual((r2["ok"], r2["written"], r2.get("suppressed")), (True, False, True))
        entries = search_log.list_entries(self.paths)["items"]
        self.assertEqual([e["query"] for e in entries], ["밖"])


class SnapshotTests(unittest.TestCase):
    def test_copies_derived_and_leaves_source_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "twin"
            (src / "vector_db" / "seg").mkdir(parents=True)
            (src / "vector_db" / "chroma.sqlite3").write_bytes(b"v")
            (src / "ontology" / "domains").mkdir(parents=True)
            (src / "context").mkdir()
            (src / "context" / "a.md").write_text("문서", encoding="utf-8")
            (src / "index_live.json").write_text(json.dumps({"live": "b"}), encoding="utf-8")
            with sqlite3.connect(src / "bm25.db") as c:
                c.execute("CREATE TABLE t(x)")
                c.execute("INSERT INTO t VALUES (1)")
            c.close()
            before = {p: p.stat().st_mtime_ns for p in src.rglob("*")}
            paths = ProjectPaths(name="demo", root=src)
            snap, info = bench_kr.snapshot_paths(paths, Path(t) / "copy")
            self.assertEqual(snap.root, Path(t) / "copy")
            self.assertEqual(snap.name, "demo")
            self.assertEqual(info["generation"], "b")
            self.assertTrue((snap.vector_db / "chroma.sqlite3").is_file())
            with sqlite3.connect(snap.bm25_db) as c:
                self.assertEqual(c.execute("SELECT x FROM t").fetchall(), [(1,)])
            c.close()
            self.assertTrue((snap.context / "a.md").is_file())
            self.assertNotEqual(snap.search_log.parent, src)
            self.assertEqual({p: p.stat().st_mtime_ns for p in src.rglob("*")}, before)


if __name__ == "__main__":
    unittest.main()
