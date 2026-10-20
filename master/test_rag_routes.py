"""#837 ASGI 로그 페이지·API, 등록경계와 공개 응답 검사."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.webui import app


def request(web, path, query=b"", method="GET"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(web({"type": "http", "path": path, "method": method, "query_string": query}, receive, send))
    return messages[0]["status"], messages[1]["body"]


class RAGRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = SimpleNamespace(name="Test", root=root, search_log=root / "search_log.jsonl")
        self.web = app.WebUI(lambda: self.paths)
        self.entry = {"search_id": "s1", "request_id": "r1", "ts": "2026-10-18T10:00:00+00:00",
                      "task_type": "user_task", "user_request": "<script>사용자 원문</script>",
                      "llm_query": "LLM 실제 입력", "query": "검색 입력", "query_expanded": "확장 입력",
                      "query_used": "실제 사용", "status": "success",
                      "result_snapshot": [{"rank": 1, "file_id": "old.md", "excerpt": "당시 본문",
                                           "meta": {"path": "/private/server/source"}}]}
        self.paths.search_log.write_text(json.dumps(self.entry, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_entry_page_and_api(self):
        with patch("master.projects.config.Registry.load", side_effect=OSError("config unavailable")):
            status, body = request(self.web, "/rag-logs")
            self.assertEqual(status, 200)
            self.assertIn("&lt;script&gt;사용자 원문&lt;/script&gt;", body.decode())
            self.assertIn("LLM 실제 입력", body.decode())
            self.assertIn("당시 본문", body.decode())
            self.assertNotIn(b"/private/server", body)
            status, body = request(self.web, "/api/v1/rag-logs", b"request_id=r1")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["items"][0]["user_request"], self.entry["user_request"])
            self.assertNotIn(b"/private/server", body)
            status, body = request(self.web, "/api/v1/rag-logs", b"search_id=s1")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["item"]["search_id"], "s1")

    def test_registered_project_selection_does_not_mount(self):
        other = SimpleNamespace(name="Other", root=Path(self.tmp.name), search_log=Path(self.tmp.name) / "absent.jsonl")
        reg = SimpleNamespace(names=["Test", "Other"])
        with patch("master.projects.config.Registry.load", return_value=reg), \
                patch("master.context_search.paths.resolve", return_value=other) as resolve:
            status, body = request(self.web, "/api/v1/rag-logs", b"project=Other")
        self.assertEqual(status, 200)
        resolve.assert_called_once_with("Other", registry=reg)
        self.assertEqual(json.loads(body)["total"], 0)

    def test_unknown_or_traversing_project_rejected(self):
        reg = SimpleNamespace(names=["Test"])
        with patch("master.projects.config.Registry.load", return_value=reg), \
                patch("master.context_search.paths.resolve") as resolve:
            for query in (b"project=Unknown", b"project=..%2Fprivate"):
                status, _ = request(self.web, "/rag-logs", query)
                self.assertEqual(status, 400)
            resolve.assert_not_called()

    def test_invalid_filters_missing_detail_and_non_get(self):
        with patch("master.projects.config.Registry.load", side_effect=OSError()):
            for query in (b"start=broken", b"offset=-1", b"limit=1000", b"start=2026-10-20&end=2026-10-01"):
                self.assertEqual(request(self.web, "/api/v1/rag-logs", query)[0], 400)
            self.assertEqual(request(self.web, "/api/v1/rag-logs", b"search_id=..%2Fprivate")[0], 404)
        for path in ("/rag-logs", "/rag-logs/", "/api/v1/rag-logs"):
            self.assertEqual(request(self.web, path, method="POST")[0], 405)

    def test_public_projection_drops_absolute_metadata_and_errors(self):
        entry = dict(self.entry, status="error", error="/private/key", root="/private/root",
                     result_snapshot=[{"file_id": "/private/file", "meta": {"path": "/private/meta"}, "excerpt": "응답"}])
        public = app._public_rag_entry(entry)
        self.assertNotIn("/private", json.dumps(public))
        self.assertEqual(public["result_snapshot"][0]["excerpt"], "응답")


if __name__ == "__main__":
    unittest.main()
