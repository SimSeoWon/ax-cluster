"""[DOC] 라우트 조각 검사 골조. ASGI 호출, usage_page/build_report 주입으로 라이브 조회 0.
허용 파일은 master/webui/app.py와 이 파일. 기존 __call__ 등 선언은 동결.
"""
import asyncio
import builtins
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import sys
from pathlib import Path

# 통합 검사는 스크립트로 단독 실행한다(`tests/integration/checks.json`) — 저장소 루트를 경로에 둔다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.webui import app, fixes_page, onboarding, usage_page
from master.work import usage_dashboard


def _request(webui, path, query=b"", method="GET"):
    messages = []

    async def receive():
        raise AssertionError("usage GET must not read the request body")

    async def send(message):
        messages.append(message)

    asyncio.run(webui({"type": "http", "method": method, "path": path,
                      "query_string": query}, receive, send))
    start, body = messages
    return start["status"], dict(start["headers"]), body["body"]


class UsageRouteTests(unittest.TestCase):
    def test_page_and_api_get_routes(self):
        paths = Mock(side_effect=AssertionError("usage must not resolve mounted paths"))
        webui = app.WebUI(paths)
        report = {"totals": {"calls": 2, "tokens": None}, "warnings": ["기록 없음"]}
        with patch.object(usage_page, "page", return_value=(202, b"usage HTML")) as page:
            for path in ("/usage", "/usage/"):
                with self.subTest(path=path):
                    status, headers, body = _request(webui, path)
                    self.assertEqual(status, 202)
                    self.assertEqual(body, b"usage HTML")
                    self.assertEqual(headers[b"content-type"], app.HTML)
                    self.assertEqual(headers[b"cache-control"], app.NO_STORE)
                    page.assert_called_with({})
        with patch.object(usage_dashboard, "build_report", return_value=report) as build:
            status, headers, body = _request(webui, "/api/v1/usage")
            self.assertEqual(status, 200)
            self.assertEqual(headers[b"content-type"], app.JSON)
            self.assertEqual(json.loads(body), report)
            build.assert_called_once_with()
        self.assertIn("/usage", app.PREFIXES)
        self.assertIn("/api/v1", app.PREFIXES)
        paths.assert_not_called()

    def test_filter_forwarding_and_read_only(self):
        paths = Mock(side_effect=AssertionError("usage must not resolve mounted paths"))
        webui = app.WebUI(paths)
        query = (b"project=AXCluster&project=other&period=weekly&start=2026-09-01"
                 b"&end=2026-09-30&family=codex&source=session"
                 b"&projects_root=/secret&queue_root=/secret&session_store=/secret"
                 b"&now=unsafe&unknown=ignored")
        expected = {"project": "AXCluster", "period": "weekly", "start": "2026-09-01",
                    "end": "2026-09-30", "family": "codex", "source": "session"}
        with patch.object(usage_page, "page", return_value=(200, b"page")) as page, \
                patch.object(usage_dashboard, "build_report", return_value={}) as build:
            for path in ("/usage", "/usage/"):
                self.assertEqual(_request(webui, path, query)[0], 200)
                page.assert_called_with(expected)
            self.assertEqual(_request(webui, "/api/v1/usage", query)[0], 200)
            build.assert_called_once_with(**expected)
            _request(webui, "/usage", b"project=&family=&family=claude")
            page.assert_called_with({"project": "", "family": ""})
            _request(webui, "/api/v1/usage", b"project=&family=&family=claude")
            build.assert_called_with(project="", family="")
            page.reset_mock()
            build.reset_mock()
            for path in ("/usage", "/usage/", "/api/v1/usage"):
                for method in ("POST", "DELETE", "HEAD"):
                    with self.subTest(path=path, method=method):
                        status, headers, body = _request(webui, path, query, method)
                        self.assertEqual(status, 405)
                        self.assertEqual(headers[b"content-type"], app.JSON)
                        self.assertIn("error", json.loads(body))
            page.assert_not_called()
            build.assert_not_called()
        paths.assert_not_called()

    def test_invalid_filters_and_safe_failure(self):
        paths = Mock(side_effect=AssertionError("usage must not resolve mounted paths"))
        webui = app.WebUI(paths)
        secret = "/private/usage.jsonl token=secret-value"
        targets = (("/usage", usage_page, "page"),
                   ("/usage/", usage_page, "page"),
                   ("/api/v1/usage", usage_dashboard, "build_report"))
        for page_status in (400, 503):
            with self.subTest(page_status=page_status), \
                    patch.object(usage_page, "page", return_value=(page_status, b"safe HTML")):
                status, headers, body = _request(webui, "/usage")
                self.assertEqual((status, body), (page_status, b"safe HTML"))
                self.assertEqual(headers[b"content-type"], app.HTML)
        for path, module, name in targets:
            for error, expected_status, message in (
                    (ValueError(secret), 400, "invalid usage filters"),
                    (OSError(secret), 503, "usage unavailable")):
                with self.subTest(path=path, error=type(error).__name__), \
                        patch.object(module, name, side_effect=error):
                    status, headers, body = _request(webui, path)
                    self.assertEqual(status, expected_status)
                    self.assertEqual(headers[b"content-type"], app.JSON)
                    self.assertEqual(json.loads(body), {"error": message})
                    self.assertNotIn(secret.encode(), body)
        original_import = builtins.__import__

        def fail_usage_import(name, globals=None, locals=None, fromlist=(), level=0):
            if ("usage_page" in (fromlist or ())
                    or "usage_dashboard" in (fromlist or ())
                    or name.endswith(".usage_dashboard")
                    or name.endswith(".usage_page")):
                raise ImportError(secret)
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fail_usage_import):
            for path, _, _ in targets:
                with self.subTest(path=path, error="import"):
                    status, headers, body = _request(webui, path)
                    self.assertEqual(status, 503)
                    self.assertEqual(headers[b"content-type"], app.JSON)
                    self.assertEqual(json.loads(body), {"error": "usage unavailable"})
                    self.assertNotIn(secret.encode(), body)
        paths.assert_not_called()

    def test_existing_routes_still_work(self):
        paths = Mock(return_value=SimpleNamespace(root="unused"))
        webui = app.WebUI(paths)
        with patch.object(fixes_page, "page", return_value=(207, b"reviews")) as reviews, \
                patch.object(onboarding, "page", return_value=b"onboarding") as onboard, \
                patch.object(usage_page, "page", side_effect=AssertionError("wrong route")), \
                patch.object(usage_dashboard, "build_report",
                             side_effect=AssertionError("wrong route")):
            for path in ("/reviews", "/reviews/"):
                status, headers, body = _request(webui, path, b"project=AXCluster")
                self.assertEqual((status, body), (207, b"reviews"))
                self.assertEqual(headers[b"content-type"], app.HTML)
                reviews.assert_called_with("AXCluster")
            for path in ("/onboarding", "/onboarding/", "/onboarding.html"):
                status, headers, body = _request(webui, path)
                self.assertEqual((status, body), (200, b"onboarding"))
                self.assertEqual(headers[b"content-type"], app.HTML)
            self.assertEqual(onboard.call_count, 3)
        self.assertEqual(paths.call_count, 5)


if __name__ == "__main__":
    unittest.main()
