"""#855 T1 — 검색 로그의 일감 연결은 관측값만 남긴다(지어내지 않는다).

    .venv/bin/python -B master/test_rag_issue_link.py
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import interview_materials as IM                      # noqa: E402
from master.context_search import search_log as log              # noqa: E402
from master.projects import mcp_server as M                      # noqa: E402


class IssueLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = SimpleNamespace(root=Path(self.tmp.name), name="demo")

    def _lock(self, record):
        return patch.multiple("master.issue_lock", current=lambda root: record)

    def _resolve(self):
        return patch("master.context_search.paths.resolve", lambda name="": self.paths)

    def test_links_provided_lock_none_and_purpose(self):
        with self._resolve(), self._lock({"issue_id": 855, "state": "active"}):
            self.assertEqual(M._search_links(0), {"issue_id": 855, "issue_id_source": "issue_lock"})
            self.assertEqual(M._search_links(971, "원인 위치"),
                             {"issue_id": 971, "issue_id_source": "provided", "purpose": "원인 위치"})
        with self._resolve(), self._lock(None):
            self.assertEqual(M._search_links(0), {}, "잠금이 없으면 지어내지 않는다")
            self.assertEqual(M._search_links("abc"), {}, "숫자가 아니면 버린다")
            self.assertEqual(M._search_links(0, "  "), {}, "빈 목적은 키를 넣지 않는다")

        def boom(root):
            raise RuntimeError("잠금 파일 깨짐")
        with self._resolve(), patch("master.issue_lock.current", boom):
            self.assertEqual(M._search_links(0), {}, "잠금 조회 실패는 연결 없음 — 검색을 막지 않는다")

    def test_tool_records_link_and_keeps_origin(self):
        seen = []

        def fake_search(query, limit):
            seen.append(log.log_search(self.paths, query=query, hits=[{"file_id": "a.md", "excerpt": "x"}]))
            return "{}"
        with self._resolve(), self._lock({"issue_id": 855}), patch.object(M, "_search_context", fake_search):
            M.search_context_tool("질의", task_type="user_command", user_request="855번 진행해",
                                  purpose="로그 필드 위치")
            M.search_context_tool("둘째", task_type="user_command", user_request="원문", issue_id=12)
        with self._resolve(), self._lock(None), patch.object(M, "_search_context", fake_search):
            M.search_context_tool("셋째", task_type="user_command", user_request="그냥 검색")
        rows = {r["query"]: r for r in log.list_entries(self.paths)["items"]}
        self.assertEqual((rows["질의"]["issue_id"], rows["질의"]["issue_id_source"], rows["질의"]["purpose"]),
                         (855, "issue_lock", "로그 필드 위치"))
        self.assertEqual(rows["질의"]["user_request"], "855번 진행해", "원문 불변")
        self.assertEqual((rows["둘째"]["issue_id"], rows["둘째"]["issue_id_source"]), (12, "provided"))
        self.assertNotIn("issue_id", rows["셋째"])
        self.assertNotIn("purpose", rows["셋째"])
        self.assertEqual(log.list_entries(self.paths, issue_id=855)["total"], 1)
        self.assertEqual(log.list_entries(self.paths, issue_id=12)["total"], 1)
        self.assertEqual(log.list_entries(self.paths)["total"], 3)
        self.assertEqual(log.current_context(), {}, "컨텍스트가 새지 않는다")

    def test_interview_materials_stamp_its_issue(self):
        seen = []

        def fake_search(query, limit):
            seen.append(log.current_context())
            return '{"hits": [], "request_id": "r"}'
        issue = {"id": 973, "subject": "[AX] 무엇", "description": ""}
        with self._resolve(), self._lock({"issue_id": 855}), patch.object(M, "_search_context", fake_search):
            IM.collect(issue, ontology=lambda q: {}, recent=lambda p: {"issues": []},
                       reports_root=Path(self.tmp.name))
        self.assertEqual((seen[0]["issue_id"], seen[0]["issue_id_source"]), (973, "interview"),
                         "재료 검색은 잠금이 아니라 그 일감 번호")
        self.assertEqual(seen[0]["task_type"], "interview_materials")


if __name__ == "__main__":
    unittest.main()
