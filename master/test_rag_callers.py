"""#837 내부 RAG의 분류·원문 연결과 독립 도메인 검색 로그."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.context_search import domain_index, search_log
from master.context_search.paths import ProjectPaths
from master.context_search.index import ContextIndex
from master.context_synth import synth
from master.work import norms
from master.work import register


class RagCallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = ProjectPaths(name="T", root=Path(self.tmp.name))

    def test_domain_result_keeps_request_and_original(self):
        manifest = self.paths.ontology / "domains" / "Worker" / "domain.yaml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("summary: 워커 지휘 규범\n", encoding="utf-8")
        with search_log.search_context(request_id="request-1", task_type="user_command",
                                       user_request="워커 검색을 확인해", user_request_source="captured"), \
                patch.object(domain_index, "_bm25_hits", return_value=[
                    ("Worker", 2.5), ("Lexical", 1.5)]), \
                patch.object(domain_index, "_vector_hits", return_value=[
                    ("Semantic", .95), ("Worker", .8), ("BelowThreshold", .1)]):
            hits = domain_index.search_norms(self.paths, "Worker", top_k=3, threshold=.7)
        self.assertEqual([hit["domain"] for hit in hits], ["Worker", "Semantic", "Lexical"])
        entry = search_log.list_entries(self.paths)["items"][0]
        self.assertEqual(entry["request_id"], "request-1")
        self.assertEqual(entry["user_request"], "워커 검색을 확인해")
        self.assertEqual(entry["results"], ["Worker", "Semantic", "Lexical"])
        self.assertEqual(entry["result_snapshot"][0]["excerpt"], "워커 지휘 규범")
        self.assertEqual(entry["result_details"][0]["bm25_score"], 2.5)
        expected = [(1, 0, "vector+bm25"), (0, None, "vector"), (None, 1, "bm25")]
        for hit, snapshot, detail, (vector_rank, bm25_rank, source) in zip(
                hits, entry["result_snapshot"], entry["result_details"], expected):
            with self.subTest(domain=hit["domain"]):
                self.assertEqual(hit.get("vector_rank"), vector_rank)
                self.assertEqual(hit.get("bm25_rank"), bm25_rank)
                self.assertEqual(snapshot["vector_rank"], vector_rank)
                self.assertEqual(snapshot["bm25_rank"], bm25_rank)
                for key, rank in (("vec_rank", vector_rank), ("bm25_rank", bm25_rank)):
                    if rank is None:
                        self.assertNotIn(key, detail)
                    else:
                        self.assertEqual(detail[key], rank)
                self.assertEqual(hit["source"], source)
                self.assertEqual(snapshot["source"], source)
                expected_rrf = round(sum(1 / (domain_index.RRF_K + rank)
                                         for rank in (vector_rank, bm25_rank)
                                         if rank is not None), 6)
                self.assertEqual(hit["rrf_score"], expected_rrf)
                self.assertEqual(snapshot["rrf_score"], expected_rrf)
                self.assertNotIn("_v", hit)
                self.assertNotIn("_b", hit)
                if vector_rank is None:
                    self.assertNotIn("vector_rank", hit)
                if bm25_rank is None:
                    self.assertNotIn("bm25_rank", hit)

    def test_domain_bm25_only_keeps_zero_rank_and_result_limit(self):
        with patch.object(domain_index, "_bm25_hits", return_value=[
                ("First", 2.5), ("Second", 1.5)]), \
                patch.object(domain_index, "_vector_hits", return_value=[]):
            hits = domain_index.search_norms(self.paths, "Worker", top_k=1)
        self.assertEqual([hit["domain"] for hit in hits], ["First"])
        self.assertEqual(hits[0]["bm25_rank"], 0)
        self.assertNotIn("vector_rank", hits[0])
        entry = search_log.list_entries(self.paths)["items"][0]
        self.assertEqual(entry["result_snapshot"][0]["bm25_rank"], 0)
        self.assertIsNone(entry["result_snapshot"][0]["vector_rank"])
        self.assertEqual(entry["result_details"][0]["bm25_rank"], 0)
        self.assertNotIn("vec_rank", entry["result_details"][0])

    def test_domain_without_bm25_still_rejects_vector_only_search(self):
        with patch.object(domain_index, "_bm25_hits", return_value=[]), \
                patch.object(domain_index, "_vector_hits", return_value=[
                    ("Semantic", .95)]) as vector:
            self.assertEqual(domain_index.search_norms(self.paths, "Worker"), [])
        vector.assert_not_called()
        entry = search_log.list_entries(self.paths)["items"][0]
        self.assertEqual(entry["status"], "empty")
        self.assertEqual(entry["result_snapshot"], [])

    def test_domain_empty_and_error_are_recorded_without_inventing_original(self):
        with patch.object(domain_index, "_bm25_hits", return_value=[]):
            self.assertEqual(domain_index.search_norms(self.paths, "아직없음"), [])
        with patch.object(domain_index, "_bm25_hits", side_effect=RuntimeError("broken")):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                domain_index.search_norms(self.paths, "실패")
        entries = search_log.read_entries(self.paths)
        self.assertEqual([entry["status"] for entry in entries], ["empty", "error"])
        self.assertTrue(all(entry["user_request_missing"] for entry in entries))
        self.assertEqual(entries[-1]["error"], "RuntimeError: broken")

    def test_synthesis_search_has_automatic_classification(self):
        seen = []

        def search(query, **kwargs):
            seen.append((query, search_log.current_context()))
            return [SimpleNamespace(file_id="Neighbor.md", excerpt="관련 문서")]

        hits = synth.collect_related(self.paths, "Target", ["Target.py"], "",
                                     searcher=SimpleNamespace(search=search))
        self.assertEqual(hits, [("Neighbor.md", "관련 문서")])
        self.assertEqual(seen[0][1]["task_type"], "context_synthesis")
        self.assertNotIn("user_request", seen[0][1])
        self.assertEqual(search_log.current_context(), {})

    def test_work_preparation_preserves_genuine_original(self):
        seen = []

        def search(paths, query, **kwargs):
            seen.append(search_log.current_context())
            return []

        with search_log.search_context(request_id="work-request", user_request="검색 개선해"):
            norms.attach(self.paths, classes=["Worker"], search=search)
        self.assertEqual(seen[0]["task_type"], "work_preparation")
        self.assertEqual(seen[0]["request_id"], "work-request")
        self.assertEqual(seen[0]["user_request"], "검색 개선해")

    def vector_index(self):
        index = object.__new__(ContextIndex)
        index.paths = self.paths
        index._live_name = "context_a"
        return index

    def test_direct_vector_records_snapshot_and_preserves_automatic_review(self):
        index = self.vector_index()
        hit = {"file_id": "Target.md", "score": .8, "excerpt": "결과 본문"}
        with search_log.search_context(task_type="automatic_review", request_id="review-1"), \
                patch.object(index, "_search_once", return_value=[hit]):
            self.assertEqual(index.search("Target"), [hit])
        entry = search_log.read_entries(self.paths)[-1]
        self.assertEqual(entry["task_type"], "automatic_review")
        self.assertEqual(entry["request_id"], "review-1")
        self.assertEqual(entry["caller"], "vector_direct")
        self.assertEqual(entry["result_snapshot"][0]["excerpt"], "결과 본문")

    def test_direct_vector_empty_error_and_suppression(self):
        index = self.vector_index()
        self.assertEqual(index.search(" "), [])
        with patch.object(index, "_search_once", side_effect=RuntimeError("broken")):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                index.search("Target")
        with search_log.suppress_logging(), \
                patch.object(index, "_search_once", return_value=[]):
            self.assertEqual(index.search("Target"), [])
        entries = search_log.read_entries(self.paths)
        self.assertEqual([entry["status"] for entry in entries], ["empty", "error"])

    def test_direct_vector_retry_logs_only_final_result(self):
        index = self.vector_index()
        with patch.object(index, "_search_once", side_effect=[
                RuntimeError("Nothing found on disk"), []]), \
                patch.object(index, "_reopen") as reopen:
            self.assertEqual(index.search("Target"), [])
        reopen.assert_called_once()
        entries = search_log.read_entries(self.paths)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "empty")

    def test_registration_passes_only_actual_original_and_links_generated_work(self):
        for original in ("사용자가 쓴 실제 요청", ""):
            seen = []

            def prepare(*args, **kwargs):
                seen.append(search_log.current_context())
                return {}

            def after(*args, **kwargs):
                seen.append(search_log.current_context())
                return "registered"

            with patch.object(register, "_check_targets"), \
                    patch.object(register, "_prepare_specs", side_effect=prepare), \
                    patch.object(register, "create_work", return_value="work-1"), \
                    patch.object(register, "_register_after_create", side_effect=after):
                result = register.register_work(
                    "제목으로 원문을 대체하지 않는다", [register.TaskSpec("Target")],
                    paths=self.paths, target_repo="repo", original_request=original,
                    poster=lambda *args: {}, profile_blockers=lambda name: [])
            self.assertEqual(result, "registered")
            self.assertEqual(seen[0]["user_request"], original or None)
            self.assertEqual(seen[0]["user_request_source"],
                             "provided" if original else "missing")
            self.assertEqual(seen[0]["request_id"], seen[1]["request_id"])
            self.assertEqual(seen[1]["work_id"], "work-1")
            self.assertEqual(search_log.current_context(), {})


if __name__ == "__main__":
    unittest.main()
