"""웹 UI ASGI 앱 — [중요] 원전 프론트엔드를 그대로 태우는 라우터 (사용자 지시 2026-08-13).

## [중요] 왜 순수 ASGI 인가

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

[중요] **쓰기 메서드는 전부 거부한다** — 사유를 JSON 으로 돌려주고 화면이 그것을 보여준다.
우리 온톨로지 편집 규칙(대화형 + 편집이 곧 잠금)과 충돌하지 않게.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, unquote

from . import routes

# [중요] **이 앱이 처리하는 경로를 여기 한 번만 적는다** (실측 2026-08-13: 같은 실수를 두 번 했다).
#    라우트를 추가할 때 손대야 하는 곳이 셋(핸들러 · 라우터 분기 · 인증 공개 목록)이었고,
#    매번 하나를 빠뜨려 401/404 가 났다. **목록을 하나로 모으면 그 부류가 사라진다** —
#    `viewer.Router` 와 `projects/__main__` 이 이 상수를 import 해서 쓴다.
PREFIXES = ("/ontology", "/ontology-static", "/api/v1", "/cluster", "/onboarding",
            "/commit-flow", "/reviews", "/usage")
# 정확히 이 경로만(접두어가 아니라 완전 일치) 이 앱이 가져간다
EXACT = ("/", "", "/cluster.html")

JSON = b"application/json; charset=utf-8"
HTML = b"text/html; charset=utf-8"
NO_STORE = b"no-store, must-revalidate"

_DOMAIN_PAGE = re.compile(r"^/ontology/domain/(.+)$")
_TASK_PAGE = re.compile(r"^/ontology/task/(.+)$")
_REVIEW_DETAIL = re.compile(r"^/reviews/([^/]+)/?$")
_API_DOMAIN = re.compile(r"^/api/v1/ontology/domain/(.+)$")
_API_OBJECT = re.compile(r"^/api/v1/ontology/object/([^/]+)/(.+)$")
_API_ACTION = re.compile(r"^/api/v1/ontology/action/([^/]+)/(.+)$")
_API_HISTORY = re.compile(r"^/api/v1/ontology/history/(.+)$")
_API_TASK = re.compile(r"^/api/v1/ontology/task/(.+)$")
_API_BOARD_ONE = re.compile(r"^/api/v1/domains/(.+)$")

# [중요] POST 지만 **읽기**인 경로 — 원전 프론트엔드가 이렇게 부른다.
READ_POST = frozenset({"/api/v1/search/combined", "/api/v1/search/vector"})


def search_paths(mounted_paths, tag: str):
    """검색이 볼 프로젝트 — **마운트된 것뿐이다** (사용자 2026-09-28 — *"마운트 된것만 검색"*).

        태그 없음 · 태그 == 마운트  → 마운트
        그 밖의 태그                → `(None, 사유)` — **거절**

    [중요] 거절이 요점이다: 남의 프로젝트 결과를 돌려주는 것은 빈 결과보다 나쁘다
    (`tagging.py` 의 레시피 읽기가 `MOUNT` 인 것과 같은 판단). 종전에는 태그를 안 봐서
    다른 체크아웃도 늘 마운트를 검색했다.
    [주의] `#693` 초판은 색인 전용 태그를 마운트와 무관하게 받았다 — 규칙 위반이라 되돌렸다.
    돌려주는 것: `(paths, "")` 또는 `(None, 사유)`.
    """
    tag = (tag or "").strip()
    if not tag or tag == getattr(mounted_paths, "name", ""):
        return mounted_paths, ""
    return None, (f"not_mounted — `{tag}` 는 마운트되지 않았다(마운트: "
                  f"{getattr(mounted_paths, 'name', '') or '(없음)'}). 남의 프로젝트 결과로 "
                  "답하지 않는다")


async def _send(send, status: int, body: bytes, ctype: bytes = JSON) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype),
                            (b"content-length", str(len(body)).encode()),
                            (b"cache-control", NO_STORE)]})
    await send({"type": "http.response.body", "body": body})


def _j(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


async def _read_body(receive) -> bytes:
    """요청 본문. [주의] `more_body` 를 끝까지 읽는다 — 한 번만 받으면 큰 본문이 잘린다."""
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
        """[중요] 쓰기 — `(status, dict)` 또는 라우트 없으면 `None`. 원전 mutation 복각."""
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
                # 원전은 이 경로로 도메인을 지웠다. [중요] 우리는 `_archive/` 로 옮긴다(되돌리기 가능)
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
        # [DOC] LLM 사용량 조각: 이 파일과 master/test_usage_routes.py만 변경한다.
        # [DOC] /usage(/) -> usage_page.page(q:scalar dict), /api/v1/usage ->
        # [DOC] usage_dashboard.build_report(project,period,start,end,family,source 키워드).
        # [DOC] 기존 라우트·선언 유지. PREFIXES에 /usage 추가(상위 라우터/공개 목록 공유).
        # [DOC] 조회 전용 GET. 여섯 쿼리만 전달하며 서버 파일 경로 쿼리는 받지 않는다.
        # [DOC] ValueError400·예외 고정503, 예외 경로/비밀값 노출 금지. 불필요한 lambda 금지.
        if scope.get("type") != "http":
            return await _send(send, 400, b'{"error":"http only"}')
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        if path in ("/usage", "/usage/", "/api/v1/usage"):
            if method != "GET":
                return await _send(send, 405, _j({"error": "read-only method"}))
            try:
                query = parse_qs(
                    (scope.get("query_string") or b"").decode("utf-8", "replace"),
                    keep_blank_values=True)
                filters = {key: query[key][0]
                           for key in ("project", "period", "start", "end", "family", "source")
                           if key in query}
                if path == "/api/v1/usage":
                    from ..work import usage_dashboard
                    status, body, ctype = 200, _j(usage_dashboard.build_report(**filters)), JSON
                else:
                    from . import usage_page
                    status, body = usage_page.page(filters)
                    ctype = HTML
            except ValueError:
                return await _send(send, 400, _j({"error": "invalid usage filters"}))
            except Exception:                               # noqa: BLE001
                return await _send(send, 503, _j({"error": "usage unavailable"}))
            return await _send(send, status, body, ctype)

        # [중요] **읽기 POST 와 쓰기 POST 를 가른다** (실측 2026-08-13).
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
        # 🔴 온보딩 — **에이전트가 무엇인가** (사용자 요청 2026-09-05). 상태(`/cluster`)가
        #    *"지금 어떤가"* 라면 여기는 *"무엇인가"* 다. 생성물이 아니라 코드에서 바로 낸다 —
        #    스냅샷이 아니므로 낡을 자리가 없다.
        if path in ("/onboarding", "/onboarding/", "/onboarding.html"):
            from . import onboarding
            return await _send(send, 200, onboarding.page(), HTML)

        # 손 커밋 흐름 (`#633` 축) — 분산 작업(`/onboarding`)과 **다른 흐름**이다.
        if path in ("/commit-flow", "/commit-flow/"):
            from . import commit_flow
            return await _send(send, 200, commit_flow.page(), HTML)
        # 🔴 리뷰·플랜 목록 (`#629`, 사용자 요청 2026-09-16) — 번호로 부르는 수정 항목의 입구.
        #    [중요] 요약만 그린다 — 본문은 8101(토큰)이다. `?project=` 로 등록된 프로젝트를 고른다.
        if path in ("/reviews", "/reviews/"):
            from . import fixes_page
            qs = parse_qs((scope.get("query_string") or b"").decode("utf-8", "replace"))
            st, body = fixes_page.page((qs.get("project") or [""])[0])
            return await _send(send, st, body, HTML)
        #    상세 — 게시판처럼 번호를 누르면 뜬다 (사용자 요청 2026-09-16). [중요] **LAN 공개다** —
        #    본문이 실리지만 사용자가 공개 범위를 골랐다(`fixes_page` 머리말).
        m = _REVIEW_DETAIL.match(path)
        if m:
            from . import fixes_page
            qs = parse_qs((scope.get("query_string") or b"").decode("utf-8", "replace"))
            st, body = fixes_page.page_detail(unquote(m.group(1)), (qs.get("project") or [""])[0])
            return await _send(send, st, body, HTML)
        # [중요] 클러스터 상태 — `/view` 를 없애고 여기로 모았다 (사용자 지시)
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
            # [중요] `limit` 을 실제로 쓴다 (`#307`) — 프론트가 `?limit=3` 을 보내는데 종전
            #    시그니처엔 인자가 없어 **조용히 무시**됐다. 파싱 실패는 기본값으로 떨어진다
            _q = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
            try:
                lim = int((_q.get("limit") or ["3"])[0])
            except (TypeError, ValueError):
                lim = 3
            return await _send(send, 200,
                               _j(routes.api_history(paths, unquote(m.group(1)), limit=lim)))
        if path == "/api/v1/ontology/tasks":
            return await _send(send, 200, _j(routes.api_tasks(paths)))
        m = _API_TASK.match(path)
        if m:
            got = routes.api_task(paths, unquote(m.group(1)))
            if got is None:
                # [주의] 자원 부재이지 라우트 부재가 아니다 — 본문이 그것을 말한다
                return await _send(send, 404, _j({"detail": "그 이름의 태스크 템플릿이 없다",
                                                  "task_type": unquote(m.group(1))}))
            return await _send(send, 200, _j(got))

        # ── API: Context Server 탭 ──
        if path == "/api/v1/health":
            return await _send(send, 200, _j(routes.api_health(root, paths)))
        if path == "/api/v1/index/status":
            return await _send(send, 200, _j(routes.api_index_status(paths)))
        if path == "/api/v1/tags":
            return await _send(send, 200, _j(routes.api_tags(root, paths)))
        if path == "/api/v1/context/doc":
            # 검색 결과 「전문 보기」 — 마운트된 프로젝트의 context/*.md 만 (`routes.api_context_doc`)
            q = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
            status, got = routes.api_context_doc(paths, (q.get("file") or [""])[0])
            return await _send(send, status, _j(got))
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
            # 🔴 [중요] **개수 필드는 `n_results` 다** (`#378`). 원전 모델이 그렇고
            #    (`search_routes.py:32,51` `n_results: int = 5`) 원전 화면도 그것을 보낸다.
            #    우리는 **우리 클라이언트가 쓰는 `n` 만** 읽고 있었다 — 화면이 48을 보내도
            #    조용히 5로 떨어졌다. 둘 다 받는다: 원전 이름이 먼저, 우리 이름이 폴백.
            try:
                n = int(data.get("n_results") or data.get("n")
                        or (q.get("n_results") or q.get("n") or ["5"])[0])
            except (ValueError, TypeError):
                n = 5
            # 🔴 [중요] **빈 질의를 거절하지 않는다** (`#378`). 원전 서버는 질의를 검사하지 않고
            #    (`search_routes.py:66,132`), 원전 화면은 **문서 전체 목록을 빈 질의로** 가져온다
            #    (`loadDocs`: `query: ' '`, `n_results = indexed_documents`). 그 방어를 여기 넣은
            #    탓에 **모든 프로젝트에서 문서 목록이 처음부터 비어 있었다** — 에러가 아니라 빈
            #    목록이라 아무도 몰랐다.
            #    [주의] 같은 규칙이 **클라이언트에는 남는다**(`client_mcp.tool_search_context`).
            #    MCP 도구 호출의 빈 질의는 호출자 실수이고 **거기가 옳은 자리다** — 서버는
            #    원전 화면이라는 다른 호출자도 받는 자리라 규칙을 옮겨 심으면 안 됐다.
            # 🔴 프로젝트 태그 — 마운트와 다르면 거절한다 (남의 결과로 답하지 않는다)
            sp, why = search_paths(paths, str(data.get("project") or ""))
            if sp is None:
                # [주의] 200 + 사유 — `tagging` 의 「거부도 200 + ok:false 로 말한다」와 같은 결
                return await _send(send, 200, _j({"ok": False, "error": why, "results": []}))
            if not query.strip():
                # 원전 계약: 빈 질의는 **문서 목록**이다 (`loadDocs`). 아래 검색은 융합이라
                # 공백이면 0건이 나온다 — 계약을 지키려면 목록으로 답해야 한다.
                return await _send(send, 200, _j(routes.api_documents(sp, n)))
            return await _send(send, 200, _j(routes.api_search(sp, query, n)))
        # [중요] 게시판은 `_domains/*.md` 다 — 온톨로지 YAML 이 아니다(`board.py` 머리말)
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
