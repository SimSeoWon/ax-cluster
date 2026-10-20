"""#837 요청 연결/동시성/원본 누적/검색 결과 계측 회귀 검사."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.context_search import search_log as log
from master.context_search.search import ContextSearch, Hit


class RagTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = SimpleNamespace(root=Path(self.tmp.name), name="demo")

    def test_context_children_and_concurrent_requests(self):
        async def run():
            async def one(origin):
                with log.search_context(task_type="user_task", user_request=origin,
                                        user_request_source="captured") as ctx:
                    await asyncio.sleep(0)
                    with log.search_context(caller="child"):
                        first = log.log_search(self.paths, query="child one")
                    second = log.log_search(self.paths, query="child two")
                    return ctx["request_id"], first, second
            return await asyncio.gather(one("원문 A"), one("원문 B"))
        results = asyncio.run(run())
        self.assertNotEqual(results[0][0], results[1][0])
        for request_id, first, second in results:
            self.assertEqual(first["request_id"], request_id)
            self.assertEqual(second["request_id"], request_id)
        self.assertEqual(log.current_context(), {})
        entries = log.list_entries(self.paths)["items"]
        self.assertEqual(len(entries), 4)
        self.assertEqual({r["user_request"] for r in entries}, {"원문 A", "원문 B"})

    def test_archive_survives_recent_rotation_and_exact_snapshot(self):
        hit = Hit("a.md", "vector+bm25", rrf_score=.01234567891,
                  similarity=.987654321, excerpt="원본 본문", vector_rank=1,
                  bm25_rank=2, bm25_score=7.12345678)
        with patch.object(log, "SEARCH_LOG_MAX_ENTRIES", 1):
            first = log.log_search(self.paths, query="first", hits=[hit])
            log.log_search(self.paths, query="second")
        self.assertEqual(len(log.read_entries(self.paths)), 1)
        self.assertEqual(log.list_entries(self.paths)["total"], 2)
        record = log.get_entry(self.paths, first["search_id"])
        self.assertEqual(record["result_snapshot"][0]["similarity"], .987654321)
        self.assertEqual(record["result_snapshot"][0]["excerpt"], "원본 본문")
        self.assertTrue(record["user_request_missing"])
        self.assertEqual(record["user_request_source"], "missing")

    def test_filters_and_dict_results(self):
        with log.search_context(task_type="automatic_review", user_request=None):
            a = log.log_search(self.paths, query="검증", error="failure")
        with log.search_context(task_type="user_task", user_request="사용자 원문"):
            log.log_search(self.paths, query="식별자", hits=[{
                "file_id": "x", "bm25_rank": 1, "bm25_score": 2.5,
                "excerpt": "body", "source": "bm25"}])
        self.assertEqual(log.list_entries(self.paths, status="missing_origin")["total"], 1)
        self.assertEqual(log.list_entries(self.paths, status="error")["items"][0]["search_id"], a["search_id"])
        self.assertEqual(log.list_entries(self.paths, query="사용자 원문")["total"], 1)
        self.assertEqual(log.list_entries(self.paths, task_type="automatic_review")["total"], 1)

    def _searcher(self):
        searcher = ContextSearch.__new__(ContextSearch)
        searcher.paths = self.paths
        searcher.vector = SimpleNamespace(live_name="a", search=lambda *a, **kw: [])
        searcher.bm25 = SimpleNamespace(search=lambda *a, **kw: [])
        return searcher

    def test_central_success_empty_error_and_suppression(self):
        searcher = self._searcher()
        def vector(query, **kwargs):
            self.assertTrue(log.logging_suppressed())
            return [{"file_id": "a", "score": .9, "excerpt": "exact"}]
        searcher.vector.search = vector
        expansion = SimpleNamespace(query="[CodeSymbol] appended")
        with patch("master.context_search.expand.expand_for", return_value=expansion):
            self.assertEqual(searcher.search("사용자 질의")[0].file_id, "a")
        rec = log.list_entries(self.paths)["items"][0]
        self.assertEqual(rec["query"], "사용자 질의")
        self.assertEqual(rec["query_expanded"], expansion.query)
        self.assertEqual(rec["query_used"], "CodeSymbol")
        self.assertEqual(rec["status"], "success")
        self.assertEqual(len(log.list_entries(self.paths)["items"]), 1)
        self.assertEqual(searcher.search(""), [])
        with patch("master.context_search.expand.expand_for", side_effect=RuntimeError("broken")):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                searcher.search("failure")
        records = log.list_entries(self.paths)["items"]
        self.assertEqual({r["status"] for r in records}, {"success", "empty", "error"})
        self.assertFalse(log.logging_suppressed())


if __name__ == "__main__":
    unittest.main()
