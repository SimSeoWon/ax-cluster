"""#837 실제 입력 캡처→클라이언트→HTTP→검색 로그→웹UI 연결 검사."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client.runtime import client_mcp as client
from master.context_search import search_log
from master.context_search.paths import ProjectPaths
from master.context_search.search import ContextSearch
from master.webui import app, routes


def request(web, path, method="GET", payload=None, query=b""):
    messages = []
    async def receive():
        return {"type": "http.request", "body": json.dumps(payload or {}).encode(), "more_body": False}
    async def send(message):
        messages.append(message)
    asyncio.run(web({"type": "http", "method": method, "path": path,
                     "query_string": query}, receive, send))
    return messages[0]["status"], messages[1]["body"]


class RequestFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = ProjectPaths("T", self.root / "twin")
        self.web = app.WebUI(lambda: self.paths)
        self.cache = SimpleNamespace(put=lambda *a: None, get_stale=lambda *a: None)
        self.searcher = ContextSearch.__new__(ContextSearch)
        self.searcher.paths = self.paths
        self.searcher.vector = SimpleNamespace(live_name="a", search=lambda *a, **kw: [
            {"file_id": "source.md", "score": .87, "excerpt": "검색 당시 본문 <tag>"}])
        self.searcher.bm25 = SimpleNamespace(search=lambda *a, **kw: [])
        self.original = "  워커의 설정을 확인해.\n원문 그대로 보관해!  "

    def papi(self, method, path, payload):
        with patch("master.context_search.ContextSearch", return_value=self.searcher), \
                patch.object(routes, "_related_classes", return_value=[]), \
                patch.object(routes, "_included_by", return_value=[]):
            status, body = request(self.web, path, method, payload)
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_captured_input_exact_and_multiple_searches_visible(self):
        captured = client.capture_rag_request(self.root, {
            "hook_event_name": "UserPromptSubmit", "prompt": self.original, "session_id": "session-A"})
        for query in ("워커 설정", "codex config"):
            result = client.dispatch_tool("search_context", {"query": query,
                "request_id": captured["request_id"]}, papi=self.papi, root=self.root, cache=self.cache)
            self.assertTrue(result["logged"])
        rows = search_log.list_entries(self.paths)["items"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["request_id"] for row in rows}, {captured["request_id"]})
        self.assertEqual({row["user_request"] for row in rows}, {self.original})
        self.assertEqual({row["user_request_source"] for row in rows}, {"captured_client_input"})
        self.assertEqual({row["caller"] for row in rows}, {"client_mcp"})
        self.assertEqual({row["task_type"] for row in rows}, {"user_command"})
        self.assertEqual(rows[0]["result_snapshot"][0]["excerpt"], "검색 당시 본문 <tag>")
        status, page = request(self.web, "/rag-logs", query=("request_id=" + captured["request_id"]).encode())
        self.assertEqual(status, 200)
        text = page.decode()
        self.assertIn(self.original, text)
        self.assertIn("워커 설정", text)
        self.assertIn("codex config", text)
        self.assertIn("검색 당시 본문 &lt;tag&gt;", text)

    def test_auto_missing_origin_and_error_are_recorded(self):
        result = client.tool_search_context(self.papi, "자동 리뷰 확인", task_type="automatic_review")
        row = search_log.get_entry(self.paths, result["search_id"])
        self.assertTrue(row["user_request_missing"])
        self.assertIsNone(row["user_request"])
        self.assertEqual(row["task_type"], "automatic_review")
        self.searcher.vector.search = lambda *a, **kw: []
        empty = client.tool_search_context(self.papi, "없는 자료")
        self.assertEqual(search_log.get_entry(self.paths, empty["search_id"])["status"], "empty")
        def fail(*args, **kwargs):
            raise RuntimeError("test backend failed")
        self.searcher.vector.search = fail
        failed = client.tool_search_context(self.papi, "실패 탐침")
        self.assertEqual(search_log.get_entry(self.paths, failed["search_id"])["status"], "error")

    def test_origin_not_guessed_and_other_request_not_used(self):
        self.assertIsNone(client.capture_rag_request(self.root, {"hook_event_name": "SessionStart"}))
        a = client.capture_rag_request(self.root, {"hook_event_name": "UserPromptSubmit", "prompt": "A"})
        client.capture_rag_request(self.root, {"hook_event_name": "UserPromptSubmit", "prompt": "B"})
        self.assertEqual(client.rag_request_context(self.root, a["request_id"])["user_request"], "A")
        self.assertEqual(client.rag_request_context(self.root, "../bad"), {})
        with self.assertRaises(client.ClientError):
            client.dispatch_tool("search_context", {"query": "q", "request_id": a["request_id"],
                "user_request": "고쳐쓴 A"}, papi=self.papi, root=self.root, cache=self.cache)

    def test_native_mcp_origin_and_initialization_failure(self):
        from master.projects import mcp_server as mcp
        with patch("master.context_search.paths.resolve", return_value=self.paths), \
                patch("master.context_search.search.open_search", return_value=self.searcher):
            result = json.loads(mcp.search_context_tool("worker settings", user_request=self.original,
                                                       task_type="user_command"))
        row = search_log.get_entry(self.paths, result["search_id"])
        self.assertEqual(row["llm_query"], "worker settings")
        self.assertEqual(row["user_request"], self.original)
        with patch("master.context_search.paths.resolve", return_value=self.paths), \
                patch("master.context_search.search.open_search", side_effect=RuntimeError("init")):
            failed = json.loads(mcp.search_context_tool("q", task_type="automatic_review"))
        self.assertFalse(failed["ok"])
        self.assertEqual(search_log.list_entries(self.paths, status="error")["total"], 1)

    def test_served_web_form_captures_raw_input(self):
        text = routes.context_server_html().decode()
        self.assertIn("user_request: document.getElementById('searchQuery').value", text)
        self.assertIn("captured_web_input", text)


if __name__ == "__main__":
    unittest.main()
