"""8103 공개 `/api/v1` 의 게시판 쓰기 라우트가 **걷혔다** (`#812`, 사용자 결정 2026-10-11).

검증하는 것 — ASGI 앱을 프로세스 안에서 불러 실제 응답을 본다(라이브 조회 0):

    ① 걷은 여섯 요청(도메인 생성 · chat · update · activate · delete_domain · chat 비우기 DELETE)이
       **405 「no such write route」** 다 — 종전 500 NameError 가 아니다
    ② `board.*` 쓰기 함수 자체가 **없다** (코드째 걷었다 — 되살아나면 여기서 잡힌다)
    ③ 읽기 POST(`/api/v1/search/combined` · `/api/v1/search/vector`)는 그대로 200 이다
    ④ 게시판 읽기 GET(`/api/v1/domains`)도 그대로 200 이다
    ⑤ `/` 원전 화면에서 걷힌 쓰기 버튼·채팅 칸이 CSS 로 숨고 안내가 붙되, 읽기 UI 는 남는다

`.venv/bin/python -B master/test_webui_write_routes.py`
"""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# 통합 검사는 스크립트로 단독 실행한다(`tests/integration/checks.json`) — 저장소 루트를 경로에 둔다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.webui import app, board, routes  # noqa: E402

REMOVED = (
    ("POST", "/api/v1/domains", {"topic": "전투"}),
    ("POST", "/api/v1/domains/%EC%A0%84%ED%88%AC/chat", {"message": "질문"}),
    ("POST", "/api/v1/domains/%EC%A0%84%ED%88%AC/update", {"content": "x"}),
    ("POST", "/api/v1/domains/%EC%A0%84%ED%88%AC/activate", {"content": "x"}),
    ("POST", "/api/v1/ontology/delete_domain", {"domain_name": "전투"}),
    ("DELETE", "/api/v1/domains/%EC%A0%84%ED%88%AC/chat", None),
)
BOARD_WRITES = ("create_domain", "chat", "update_domain", "activate_domain",
                "delete_domain", "clear_chat")


def _request(webui, method, path, payload=None):
    messages = []
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(webui({"type": "http", "method": method, "path": path,
                       "query_string": b""}, receive, send))
    start, out = messages
    return start["status"], json.loads(out["body"].decode("utf-8"))


class RemovedWriteRoutesTests(unittest.TestCase):
    def setUp(self):
        self.paths = SimpleNamespace(root=Path("/nonexistent-ax-test"), name="T")
        self.webui = app.WebUI(lambda: self.paths)

    def test_board_write_functions_are_gone(self):
        for name in BOARD_WRITES:
            self.assertFalse(hasattr(board, name), name)

    def test_removed_routes_are_405(self):
        for method, path, payload in REMOVED:
            with self.subTest(method=method, path=path):
                st, got = _request(self.webui, method, path, payload)
                self.assertEqual(st, 405, got)
                self.assertEqual(got.get("error"), "no such write route")
                self.assertEqual(got.get("path"), path)

    def test_old_write_constants_are_gone(self):
        """상수만 되살려 공개 접두어에 쓰기가 다시 붙는 일을 막는다 — 되살리려면 토큰 뒤에."""
        for name in ("_W_CREATE", "_W_CHAT", "_W_UPDATE", "_W_ACTIVATE", "_W_DELETE_DOMAIN"):
            self.assertFalse(hasattr(app, name), name)
        self.assertFalse(hasattr(app.WebUI, "_write"))

    def test_read_posts_still_work(self):
        calls = []

        def fake_search(paths, query, n=5):
            calls.append(("search", query, n))
            return {"results": [{"file": "a.md"}], "query": query}

        def fake_documents(paths, n=5):
            calls.append(("documents", n))
            return {"results": []}

        with patch.object(routes, "api_search", fake_search), \
                patch.object(routes, "api_documents", fake_documents):
            for path in sorted(app.READ_POST):
                with self.subTest(path=path):
                    st, got = _request(self.webui, "POST", path,
                                       {"query": "전투", "n_results": 3})
                    self.assertEqual(st, 200, got)
                    self.assertEqual(got["query"], "전투")
            st, got = _request(self.webui, "POST", "/api/v1/search/combined",
                               {"query": " ", "n_results": 7})
            self.assertEqual(st, 200, got)
        self.assertEqual(calls, [("search", "전투", 3), ("search", "전투", 3),
                                 ("documents", 7)])

    def test_board_read_get_still_works(self):
        with patch.object(board, "list_board", lambda paths: {"domains": []}):
            st, got = _request(self.webui, "GET", "/api/v1/domains")
        self.assertEqual(st, 200)
        self.assertEqual(got, {"domains": []})


class RetiredControlsHiddenTests(unittest.TestCase):
    """`/` 원전 화면의 걷힌 쓰기 버튼을 서빙 시점에 숨긴다 (`#812`) — 원전 바이트는 그대로."""

    def setUp(self):
        self.paths = SimpleNamespace(root=Path("/nonexistent-ax-test"), name="T")
        self.webui = app.WebUI(lambda: self.paths)

    def _served(self):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        asyncio.run(self.webui({"type": "http", "method": "GET", "path": "/",
                                "query_string": b""}, receive, send))
        start, out = messages
        self.assertEqual(start["status"], 200)
        return out["body"].decode("utf-8")

    def test_each_retired_control_is_hidden(self):
        text = self._served()
        head = text[:text.lower().index("</head>")]
        rule = ",".join(routes.RETIRED_WRITE_SELECTORS) + "{display:none!important}"
        self.assertIn(rule, head)
        self.assertEqual(routes.RETIRED_WRITE_SELECTORS, (
            'button[onclick="toggleNewDomain()"]', "#newDomainForm",
            "#domainDetail .delete-btn", "#domainDetail .domain-chat-panel"))
        # 선택자가 가리키는 원전 요소가 실제로 응답에 있다 (원전이 바뀌면 여기서 드러난다).
        # Send/Apply/Activate/Clear·입력창·기록은 모두 채팅 칸 안에 있다 — 칸째 숨는다
        self.assertIn('onclick="toggleNewDomain()"', text)
        self.assertIn('id="newDomainForm"', text)
        self.assertIn('class="delete-btn" onclick="deleteDomain()"', text)
        panel = text.index('<div class="domain-chat-panel">')
        panel_end = text.index('<script>', panel)
        for marker in ('id="chatMessages"', 'class="chat-input-area"', 'id="chatSendBtn"',
                       'class="apply-btn"', 'id="activateBtn"', 'class="clear-btn"'):
            with self.subTest(marker=marker):
                self.assertTrue(panel < text.index(marker) < panel_end, marker)
        self.assertIn("#domainDetail .domain-layout{grid-template-columns:1fr!important}", head)

    def test_notice_is_shown(self):
        text = self._served()
        self.assertIn("도메인 문서 편집·채팅은 2026-10-11 제거됨 (#812)", text)
        self.assertIn('#domainListView::before{content:"', text)

    def test_read_ui_is_not_hidden(self):
        text = self._served()
        for marker in ('id="searchQuery"', 'id="docList"', 'id="tagCloud"', 'id="domainList"',
                       'id="domainFilter"', 'id="domainContent"', 'id="domainSources"',
                       'class="domain-doc-panel"', 'data-tab="domains"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        joined = " ".join(routes.RETIRED_WRITE_SELECTORS)
        for read in ("#domainList", "#domainContent", "#domainSources", "#searchQuery",
                     ".domain-doc-panel", ".tab-content", "#domainDetail{", "#tab-domains"):
            self.assertNotIn(read, joined)
        # 읽기 응답에 채팅 기록이 실리지 않는다 — 원전 JS 는 `data.chat_history || []` 로 견딘다
        self.assertIn("(data.chat_history || [])", text)

    def test_original_bytes_untouched(self):
        from master.webui.web_ui_original import WEB_UI_HTML
        self.assertNotIn("#812", WEB_UI_HTML)
        self.assertNotIn("display:none!important", WEB_UI_HTML)


if __name__ == "__main__":
    unittest.main()
