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

# 🔴 **이 앱이 처리하는 경로를 여기 한 번만 적는다** (실측 2026-08-13: 같은 실수를 두 번 했다).
#    라우트를 추가할 때 손대야 하는 곳이 셋(핸들러 · 라우터 분기 · 인증 공개 목록)이었고,
#    매번 하나를 빠뜨려 401/404 가 났다. **목록을 하나로 모으면 그 부류가 사라진다** —
#    `viewer.Router` 와 `projects/__main__` 이 이 상수를 import 해서 쓴다.
PREFIXES = ("/ontology", "/ontology-static", "/api/v1", "/cluster")
# 정확히 이 경로만(접두어가 아니라 완전 일치) 이 앱이 가져간다
EXACT = ("/", "", "/cluster.html")

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

# 🔴 POST 지만 **읽기**인 경로 — 원전 프론트엔드가 이렇게 부른다.
READ_POST = frozenset({"/api/v1/search/combined", "/api/v1/search/vector"})

# 🔴 **쓰기 경로** (사용자 결정 2026-08-13: *"생성·삭제·채팅까지 원전대로 살려"*).
#    대상은 `context/_domains/*.md` — **사람이 읽고 쓰는 도메인 문서**다.
#    ⚠️ 온톨로지 YAML(`ontology/domains/…`)은 여기서 절대 건드리지 않는다 — 그쪽은 편집이 곧
#    잠금이고 대화형으로만 바뀐다. 두 층을 헷갈리지 말 것(`board.py` 머리말 참조).
_W_CREATE = "/api/v1/domains"
_W_CHAT = re.compile(r"^/api/v1/domains/([^/]+)/chat$")
_W_UPDATE = re.compile(r"^/api/v1/domains/([^/]+)/update$")
_W_ACTIVATE = re.compile(r"^/api/v1/domains/([^/]+)/activate$")
_W_DELETE_DOMAIN = "/api/v1/ontology/delete_domain"


async def _send(send, status: int, body: bytes, ctype: bytes = JSON) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype),
                            (b"content-length", str(len(body)).encode()),
                            (b"cache-control", NO_STORE)]})
    await send({"type": "http.response.body", "body": body})


def _j(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


async def _read_body(receive) -> bytes:
    """요청 본문. ⚠️ `more_body` 를 끝까지 읽는다 — 한 번만 받으면 큰 본문이 잘린다."""
    buf = b""
    while True:
        msg = await receive()
        if msg.get("type") != "http.request":
            break
        buf += msg.get("body", b"") or b""
        if not msg.get("more_body"):
            break
    return buf


class WebUI:
    """원전 웹 UI. `paths_fn()` 이 활성 프로젝트를 매 요청 해석한다 (§5.5.2 와 같은 이유)."""

    def __init__(self, paths_fn):
        self._paths_fn = paths_fn

    async def _write(self, scope, receive, method: str, path: str):
        """🔴 쓰기 — `(status, dict)` 또는 라우트 없으면 `None`. 원전 mutation 복각."""
        from . import board
        try:
            paths = self._paths_fn()
        except Exception as e:                               # noqa: BLE001
            return 503, {"error": f"프로젝트 해석 실패: {e}"}

        raw = await _read_body(receive)
        data: dict = {}
        if raw:
            try:
                data = json.loads(raw.decode("utf-8", "replace")) or {}
            except ValueError:
                data = {}

        try:
            if method == "POST" and path == _W_CREATE:
                return 200, board.create_domain(paths, str(data.get("topic") or ""))
            m = _W_CHAT.match(path)
            if m and method == "POST":
                return 200, board.chat(paths, unquote(m.group(1)),
                                       str(data.get("message") or ""))
            m = _W_UPDATE.match(path)
            if m and method == "POST":
                return 200, board.update_domain(paths, unquote(m.group(1)),
                                                str(data.get("content") or ""))
            m = _W_ACTIVATE.match(path)
            if m and method == "POST":
                return 200, board.activate_domain(paths, unquote(m.group(1)),
                                                  str(data.get("content") or ""))
            if method == "POST" and path == _W_DELETE_DOMAIN:
                # 원전은 이 경로로 도메인을 지웠다. 🔴 우리는 `_archive/` 로 옮긴다(되돌리기 가능)
                return 200, board.delete_domain(paths,
                                                str(data.get("domain_name")
                                                    or data.get("name") or ""))
            m = _W_CHAT.match(path)
            if m and method == "DELETE":
                return 200, board.clear_chat(paths, unquote(m.group(1)))
        except board.BoardError as e:
            return 400, {"error": str(e)}
        except Exception as e:                               # noqa: BLE001
            return 500, {"error": f"{type(e).__name__}: {e}"}
        return None

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await _send(send, 400, b'{"error":"http only"}')
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        # 🔴 **읽기 POST 와 쓰기 POST 를 가른다** (실측 2026-08-13).
        #    원전은 검색을 `POST /api/v1/search/*` 로 부른다 — HTTP 메서드만 보고 막으면
        #    **검색 탭이 통째로 죽는다**(내가 그렇게 만들어 놓고 확인해서 잡았다).
        #    기준은 메서드가 아니라 **무엇을 하는 경로인가** 다: 검색은 읽기다.
        if method not in ("GET", "HEAD"):
            if path in READ_POST:
                pass                                  # 읽기 POST — 아래에서 처리
            elif method in ("POST", "DELETE"):
                got = await self._write(scope, receive, method, path)
                if got is not None:
                    return await _send(send, got[0], _j(got[1]))
                return await _send(send, 405, _j({"error": "no such write route",
                                                  "path": path}))
            else:
                return await _send(send, 405, _j({"error": "read-only method"}))

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
            return await _send(send, 200,
                               routes.inject_cluster_link(routes.page("index.html")), HTML)
        if _DOMAIN_PAGE.match(path):
            return await _send(send, 200,
                               routes.inject_cluster_link(routes.page("domain.html")), HTML)
        if _TASK_PAGE.match(path):
            return await _send(send, 200,
                               routes.inject_cluster_link(routes.page("task.html")), HTML)
        # 🔴 클러스터 상태 — `/view` 를 없애고 여기로 모았다 (사용자 지시)
        if path in ("/cluster", "/cluster/", "/cluster.html"):
            st, body = routes.cluster_page(paths)
            return await _send(send, st, body, HTML)

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
        if path in READ_POST:
            # 원전은 **본문 JSON** 으로 보낸다(`{query, n, category, tags}`). 편의로 쿼리스트링도 받는다.
            body = await _read_body(receive)
            data = {}
            if body:
                try:
                    data = json.loads(body.decode("utf-8", "replace")) or {}
                except ValueError:
                    data = {}
            q = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
            query = str(data.get("query") or (q.get("query") or q.get("q") or [""])[0])
            try:
                n = int(data.get("n") or (q.get("n") or ["5"])[0])
            except (ValueError, TypeError):
                n = 5
            if not query.strip():
                return await _send(send, 200, _j({"results": [], "count": 0,
                                                  "note": "query 가 비었다"}))
            return await _send(send, 200, _j(routes.api_search(paths, query, n)))
        # 🔴 게시판은 `_domains/*.md` 다 — 온톨로지 YAML 이 아니다(`board.py` 머리말)
        from . import board
        if path == "/api/v1/domains":
            return await _send(send, 200, _j(board.list_board(paths)))
        m = _API_BOARD_ONE.match(path)
        if m:
            name = unquote(m.group(1)).split("/")[0]
            try:
                got = board.get_board_domain(paths, name)
            except board.BoardError as e:
                return await _send(send, 400, _j({"error": str(e)}))
            if got is None:
                return await _send(send, 404, _j({"error": "도메인 없음"}))
            return await _send(send, 200, _j(got))

        return await _send(send, 404, _j({"error": "no such route", "path": path}))
