"""웹 UI ASGI 앱 — 🔴 원전 프론트엔드를 그대로 태우는 라우터 (사용자 지시 2026-08-13).

## 🔴 왜 순수 ASGI 인가

원전은 FastAPI 였다. 우리는 8103 에 **MCP 앱과 한 프로세스로** 얹으므로(포트를 늘리지 않는다)
프레임워크를 하나 더 들이지 않고 `viewer.py` 와 같은 방식(순수 ASGI)으로 쓴다 — 그쪽 미들웨어·
라우터가 이미 그 규약이다.

## 경로

    /                       원전 Context Server (상태카드 + 탭 4개)
    /ontology               원전 도메인 목록 (트리 네비)
    /ontology/domain/{name} 원전 도메인 상세 (3분할 + Cytoscape 그래프)
    /ontology/task/{type}   원전 태스크 템플릿 상세
    /ontology-static/*      app.css · tree_nav.js · vendor/cytoscape.min.js
    /api/v1/...             원전 프론트엔드가 부르는 21개 (`routes.py`)

🔴 **쓰기 메서드는 전부 거부한다** — 사유를 JSON 으로 돌려주고 화면이 그것을 보여준다.
우리 온톨로지 편집 규칙(대화형 + 편집이 곧 잠금)과 충돌하지 않게.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, unquote

from . import routes

JSON = b"application/json; charset=utf-8"
HTML = b"text/html; charset=utf-8"
NO_STORE = b"no-store, must-revalidate"

_DOMAIN_PAGE = re.compile(r"^/ontology/domain/(.+)$")
_TASK_PAGE = re.compile(r"^/ontology/task/(.+)$")
_API_DOMAIN = re.compile(r"^/api/v1/ontology/domain/(.+)$")
_API_OBJECT = re.compile(r"^/api/v1/ontology/object/([^/]+)/(.+)$")
_API_ACTION = re.compile(r"^/api/v1/ontology/action/([^/]+)/(.+)$")
_API_HISTORY = re.compile(r"^/api/v1/ontology/history/(.+)$")
_API_TASK = re.compile(r"^/api/v1/ontology/task/(.+)$")
_API_BOARD_ONE = re.compile(r"^/api/v1/domains/(.+)$")


async def _send(send, status: int, body: bytes, ctype: bytes = JSON) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype),
                            (b"content-length", str(len(body)).encode()),
                            (b"cache-control", NO_STORE)]})
    await send({"type": "http.response.body", "body": body})


def _j(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class WebUI:
    """원전 웹 UI. `paths_fn()` 이 활성 프로젝트를 매 요청 해석한다 (§5.5.2 와 같은 이유)."""

    def __init__(self, paths_fn):
        self._paths_fn = paths_fn

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await _send(send, 400, b'{"error":"http only"}')
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        # 🔴 쓰기는 전부 거부 — 사유를 돌려준다(화면이 그것을 보여준다)
        if method not in ("GET", "HEAD"):
            return await _send(send, 200, _j(routes.api_refuse_mutation()))

        try:
            paths = self._paths_fn()
            root = paths.root
        except Exception as e:                               # noqa: BLE001
            return await _send(send, 503, _j({"error": f"프로젝트 해석 실패: {e}"}))

        # ── 정적 자산 ──
        if path.startswith("/ontology-static/"):
            body, ctype = routes.read_static(path[len("/ontology-static/"):])
            if body is None:
                return await _send(send, 404, b'{"error":"not found"}')
            return await _send(send, 200, body, ctype)

        # ── 페이지 (원전 HTML 그대로) ──
        if path in ("/", ""):
            return await _send(send, 200, routes.context_server_html(), HTML)
        if path in ("/ontology", "/ontology/"):
            return await _send(send, 200, routes.page("index.html"), HTML)
        if _DOMAIN_PAGE.match(path):
            return await _send(send, 200, routes.page("domain.html"), HTML)
        if _TASK_PAGE.match(path):
            return await _send(send, 200, routes.page("task.html"), HTML)

        # ── API: 온톨로지 ──
        if path == "/api/v1/ontology/domains":
            return await _send(send, 200, _j(routes.api_domains(root)))
        m = _API_DOMAIN.match(path)
        if m:
            got = routes.api_domain(root, unquote(m.group(1)))
            if got is None:
                return await _send(send, 404, _j({"detail": "도메인 부재"}))
            return await _send(send, 200, _j(got))
        m = _API_OBJECT.match(path)
        if m:
            got = routes.api_object(root, unquote(m.group(1)), unquote(m.group(2)))
            if got is None:
                return await _send(send, 404, _j({"detail": "오브젝트 부재"}))
            return await _send(send, 200, _j(got))
        m = _API_ACTION.match(path)
        if m:
            got = routes.api_action(root, unquote(m.group(1)), unquote(m.group(2)))
            if got is None:
                return await _send(send, 404, _j({"detail": "액션 부재"}))
            return await _send(send, 200, _j(got))
        m = _API_HISTORY.match(path)
        if m:
            return await _send(send, 200, _j(routes.api_history(unquote(m.group(1)))))
        if path == "/api/v1/ontology/tasks":
            return await _send(send, 200, _j(routes.api_tasks()))
        if _API_TASK.match(path):
            return await _send(send, 404, _j({"detail": routes.NOTES["tasks"]}))

        # ── API: Context Server 탭 ──
        if path == "/api/v1/health":
            return await _send(send, 200, _j(routes.api_health(root, paths)))
        if path == "/api/v1/index/status":
            return await _send(send, 200, _j(routes.api_index_status(paths)))
        if path == "/api/v1/tags":
            return await _send(send, 200, _j(routes.api_tags(root, paths)))
        if path in ("/api/v1/search/combined", "/api/v1/search/vector"):
            # ⚠️ 원전은 POST 였다. GET 도 받는다 — 쓰기가 아니므로(§ 위 GET 만 통과 규칙과 충돌 X)
            q = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
            query = (q.get("query") or q.get("q") or [""])[0]
            try:
                n = int((q.get("n") or ["5"])[0])
            except ValueError:
                n = 5
            if not query.strip():
                return await _send(send, 200, _j({"results": [], "count": 0,
                                                  "note": "query 가 비었다"}))
            return await _send(send, 200, _j(routes.api_search(paths, query, n)))
        if path == "/api/v1/domains":
            return await _send(send, 200, _j(routes.api_board_domains(root)))
        m = _API_BOARD_ONE.match(path)
        if m:
            got = routes.api_domain(root, unquote(m.group(1)).split("/")[0])
            if got is None:
                return await _send(send, 404, _j({"detail": "도메인 부재"}))
            return await _send(send, 200, _j(got))

        return await _send(send, 404, _j({"error": "no such route", "path": path}))
