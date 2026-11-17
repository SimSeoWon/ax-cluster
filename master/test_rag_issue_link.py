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
        # `#979` — 일감 스냅샷은 실 Redmine 을 두드리지 않는다(대역). 스냅샷 자체 계약은 test_issue_snapshot.
        self.snapped = []
        snap = lambda n: (self.snapped.append(n) or {"issue_id": n, "status": "ok", "subject": f"제목{n}",
                                                     "context": "맥락", "tasks": [{"id": "T2", "goal": "목표",
                                                                                   "state": "작업중"}]})
        p = patch("master.issue_snapshot.snapshot", snap)
        p.start()
        self.addCleanup(p.stop)

    def _lock(self, record):
        return patch.multiple("master.issue_lock", current=lambda root: record)

    def _resolve(self):
        return patch("master.context_search.paths.resolve", lambda name="": self.paths)

    def test_links_provided_lock_none_and_purpose(self):
        with self._resolve(), self._lock({"issue_id": 855, "state": "active"}):
            got = M._search_links(0)
            self.assertEqual((got["issue_id"], got["issue_id_source"]), (855, "issue_lock"))
            self.assertEqual(got["issue_snapshot"]["subject"], "제목855")
            got = M._search_links(971, "원인 위치")
            self.assertEqual((got["issue_id"], got["issue_id_source"], got["purpose"]),
                             (971, "provided", "원인 위치"))
            self.assertEqual(got["issue_snapshot"]["tasks"][0]["id"], "T2")
        with self._resolve(), self._lock(None):
            self.assertEqual(M._search_links(0), {}, "잠금이 없으면 지어내지 않는다")
            self.assertEqual(M._search_links("abc"), {}, "숫자가 아니면 버린다")
            self.assertEqual(M._search_links(0, "  "), {}, "빈 목적은 키를 넣지 않는다")
        self.assertEqual(self.snapped, [855, 971], "연결이 없으면 스냅샷 조회도 없다")

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
        snap = rows["질의"]["issue_snapshot"]
        self.assertEqual((snap["issue_id"], snap["subject"], snap["tasks"][0]["id"]), (855, "제목855", "T2"),
                         "#979 — 그 시점 일감 요구가 로그에 남는다")
        self.assertNotIn("issue_snapshot", rows["셋째"])

    def test_snapshot_failure_does_not_block_search(self):
        def fake_search(query, limit):
            log.log_search(self.paths, query=query, hits=[{"file_id": "a.md", "excerpt": "x"}])
            return '{"hits": 1}'

        def boom(n):
            raise RuntimeError("스냅샷 모듈 고장")
        with self._resolve(), self._lock(None), patch.object(M, "_search_context", fake_search), \
                patch("master.issue_snapshot.snapshot", boom):
            out = M.search_context_tool("질의", task_type="user_command", user_request="979번 진행하자",
                                        issue_id=979)
        self.assertEqual(out, '{"hits": 1}', "검색 결과는 그대로")
        row = log.list_entries(self.paths)["items"][0]
        self.assertEqual((row["issue_id"], row["issue_snapshot"]["status"]), (979, "fetch_failed"))
        self.assertIn("RuntimeError", row["issue_snapshot"]["why"])

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
