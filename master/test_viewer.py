"""읽기 전용 화면 서빙 + 자격증명 분리 (중 3.2 후속).

[중요] 지키는 계약은 다섯이다:

    ① **경로는 화이트리스트다** — 클라이언트가 준 문자열로 파일을 열지 않는다
    ② [중요] **뷰는 공개, API 는 잠김** — 공개는 뷰 경로에만 적용된다.
       잠근 모드(`AX_VIEW_REQUIRE_TOKEN=1`)에서는 자격증명이 **양방향으로** 갈린다
    ③ **읽기 전용** — GET/HEAD 만. 요청이 수집을 유발하지 않는다
    ④ **낡은 것을 최신처럼 보이게 두지 않는다** — 나이를 배너로 박는다
    ⑤ **한 포트·한 유닛** — 라우터가 갈라 주고 서비스를 늘리지 않는다

`.venv/bin/python master/test_viewer.py`
"""
from __future__ import annotations

import asyncio
import base64
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import auth as A          # noqa: E402
from master import viewer as V        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def call(app, path="/view/", method="GET", headers=None) -> tuple:
    """ASGI 앱을 한 번 부른다. `(status, 헤더dict, 본문str)`."""
    scope = {"type": "http", "method": method, "path": path,
             "headers": [(k.lower().encode(), v.encode())
                         for k, v in (headers or {}).items()]}
    out = {"status": 0, "headers": {}, "body": b""}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = {k.decode().lower(): v.decode() for k, v in msg["headers"]}
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(app(scope, receive, send))
    return out["status"], out["headers"], out["body"].decode("utf-8", "replace")


def tmp_root(*, cluster_age=0.0, with_domains=True):
    d = Path(tempfile.mkdtemp(prefix="axview"))
    (d / "cluster.html").write_text(
        "<!doctype html><html lang=ko><head></head><body><h1>상태</h1></body></html>",
        encoding="utf-8")
    if with_domains:
        (d / "domains.html").write_text("<html><body>도메인</body></html>", encoding="utf-8")
    if cluster_age:
        old = time.time() - cluster_age
        import os
        os.utime(d / "cluster.html", (old, old))
    return d


# ── ① 경로 화이트리스트 ─────────────────────────────────────────────────────────

def test_path_is_whitelisted_not_joined() -> None:
    """[중요] 순회를 막는 가장 확실한 방법은 **경로를 받지 않는 것**이다."""
    root = Path("/tmp")
    for bad in ("../../etc/passwd", "..%2fetc", "cluster.html/../../x", "secret.html",
                "", "cluster.HTML"):
        check(f"거부: {bad!r}", V.page_path(root, bad) is None, bad)
    check("허용: cluster.html", V.page_path(root, "cluster.html") == root / "cluster.html")


def test_unknown_view_is_404_and_traversal_never_reads() -> None:
    d = tmp_root()
    try:
        app = V.ViewApp(lambda: d)
        st, _, _ = call(app, "/view/../../etc/passwd")
        check("순회는 404", st == 404, str(st))
        st, _, body = call(app, "/view/nope.html")
        check("모르는 이름은 404", st == 404, str(st))
        check("무엇이 있는지 흘리지 않는다", "cluster" not in body, body[:80])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── ③ 읽기 전용 ─────────────────────────────────────────────────────────────────

def test_read_only_methods() -> None:
    d = tmp_root()
    try:
        app = V.ViewApp(lambda: d)
        for m in ("POST", "PUT", "DELETE", "PATCH"):
            st, _, body = call(app, "/view/cluster.html", method=m)
            check(f"{m} 는 405", st == 405, str(st))
            check(f"{m} 사유가 읽기 전용", "read-only" in body, body[:60])
        st, _, _ = call(app, "/view/cluster.html", method="GET")
        check("GET 은 200", st == 200, str(st))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_serving_never_regenerates() -> None:
    """[중요] 새로고침이 BC-250 에 SSH 폴링을 걸면 주기 가드를 만든 이유가 사라진다."""
    src = Path(V.__file__).read_text(encoding="utf-8")
    for bad in ("status.collect", "subprocess", "_ssh(", "os.system"):
        check(f"[중요] `{bad}` 를 부르지 않는다", bad not in src, bad)


def test_no_store_so_refresh_shows_latest() -> None:
    d = tmp_root()
    try:
        _, h, _ = call(V.ViewApp(lambda: d), "/view/cluster.html")
        check("캐시하지 않는다", "no-store" in h.get("cache-control", ""),
              h.get("cache-control", ""))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── ④ 낡음을 숨기지 않는다 ──────────────────────────────────────────────────────

def test_stale_snapshot_gets_a_banner() -> None:
    d = tmp_root(cluster_age=3600)
    try:
        st, _, body = call(V.ViewApp(lambda: d), "/view/cluster.html")
        check("여전히 200", st == 200, str(st))
        check("배너가 박힌다", "지금 상태가 아니다" in body, body[:200])
        check("만드는 명령을 알려준다", "master.status html" in body)
        # [중요] `<body>` 바로 뒤여야 한다 — 앞에 붙으면 문서가 깨진다
        check("body 안쪽에 넣는다", body.index("<body>") < body.index("지금 상태가"))
        check("원래 내용이 남아 있다", "<h1>상태</h1>" in body)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_fresh_snapshot_has_no_banner() -> None:
    d = tmp_root()
    try:
        _, _, body = call(V.ViewApp(lambda: d), "/view/cluster.html")
        check("새 것엔 배너 없음", "지금 상태가 아니다" not in body)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing_page_says_how_to_make_it() -> None:
    d = tmp_root(with_domains=False)
    try:
        st, _, body = call(V.ViewApp(lambda: d), "/view/domains.html")
        check("없으면 503", st == 503, str(st))
        check("만드는 명령을 알려준다", "master.ontology view" in body, body[:150])
        _, _, idx = call(V.ViewApp(lambda: d), "/view/")
        check("목록에도 없다고 적는다", "아직 만들어지지 않았다" in idx)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_index_shows_age_and_marks_stale() -> None:
    d = tmp_root(cluster_age=7200)
    try:
        _, _, idx = call(V.ViewApp(lambda: d), "/view/")
        check("나이를 보인다", "시간 전" in idx or "분 전" in idx, idx[:200])
        check("낡은 것에 표시", "[주의]" in idx)
        check("읽기 전용임을 적는다", "읽기 전용" in idx)
        # [주의] 로그인을 뺀 뒤(사용자 결정 2026-08-13) 문구가 바뀌었다 — **인증이 없다는 사실**과
        #    같은 포트의 API 는 잠겨 있다는 것을 화면이 말해야 한다
        check("인증이 없다고 적는다", "인증이 없다" in idx, idx[-300:])
        check("API 는 잠겨 있다고 적는다", "잠겨" in idx, idx[-300:])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── ② [중요] 자격증명 분리 ──────────────────────────────────────────────────────────

def _basic(tok: str) -> str:
    return "Basic " + base64.b64encode(f"ax:{tok}".encode()).decode()


def test_view_token_and_api_token_do_not_cross() -> None:
    """[중요] 브라우저가 쥔 자격으로 MCP 를 부를 수 없어야 한다 — 분리한 이유가 그것이다."""
    api, view = "A" * 40, "V" * 40
    seen: list = []

    async def inner(scope, receive, send):
        seen.append(scope.get("path"))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = A.BearerAuthMiddleware(inner, api, view_prefix="/view", view_token=view)

    st, h, _ = call(app, "/view/", headers={"Authorization": _basic(view)})
    check("뷰토큰+Basic → 화면 열림", st == 200, str(st))
    st, _, _ = call(app, "/view/", headers={"Authorization": f"Bearer {view}"})
    check("뷰토큰+Bearer 도 허용", st == 200, str(st))

    st, _, _ = call(app, "/view/", headers={"Authorization": f"Bearer {api}"})
    check("[중요] API 토큰으로 화면 못 본다", st == 401, str(st))
    st, _, _ = call(app, "/view/", headers={"Authorization": _basic(api)})
    check("[중요] API 토큰 Basic 도 막힌다", st == 401, str(st))

    st, _, _ = call(app, "/mcp", headers={"Authorization": f"Bearer {view}"})
    check("[중요] 뷰 토큰으로 MCP 못 부른다", st == 401, str(st))
    st, _, _ = call(app, "/mcp", headers={"Authorization": _basic(view)})
    check("[중요] 뷰 토큰 Basic 으로도 못 부른다", st == 401, str(st))
    st, _, _ = call(app, "/mcp", headers={"Authorization": f"Bearer {api}"})
    check("API 토큰은 MCP 통과", st == 200, str(st))


def test_view_is_public_by_default() -> None:
    """[중요] 사용자 결정 2026-08-13: *"그냥 있는거 보여주는 뷰어를 원하는거라니까."*

    이 경로는 조작이 불가능하다(GET/HEAD · 화이트리스트 · 수집 유발 없음). 규칙의 글자를
    지키려고 **쓰이지 않는 화면**을 만드는 것이 더 나쁘다. 남는 방어는 ufw LAN 한정이다.
    """
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = A.BearerAuthMiddleware(inner, "A" * 40, view_prefix="/view", view_public=True)
    st, _, _ = call(app, "/view/")
    check("[중요] 인증 없이 화면이 열린다", st == 200, str(st))
    st, _, _ = call(app, "/view/cluster.html")
    check("페이지도 열린다", st == 200, str(st))
    # [중요] 그래도 **API 는 잠겨 있다** — 공개는 뷰 경로에만 적용된다
    st, _, _ = call(app, "/mcp")
    check("[중요] MCP 는 여전히 401", st == 401, str(st))
    st, _, _ = call(app, "/mcp", headers={"Authorization": "Bearer " + "A" * 40})
    check("API 토큰으로만 MCP", st == 200, str(st))


def test_browser_gets_a_basic_challenge_api_gets_bearer() -> None:
    """브라우저가 로그인 창을 띄우려면 **Basic** 도전이 와야 한다."""
    app = A.BearerAuthMiddleware(lambda *a: None, "A" * 40,
                                 view_prefix="/view", view_token="V" * 40)
    _, h, _ = call(app, "/view/")
    check("뷰는 Basic 도전", "Basic" in h.get("www-authenticate", ""),
          h.get("www-authenticate", ""))
    _, h, _ = call(app, "/mcp")
    check("API 는 Bearer 도전", h.get("www-authenticate", "").startswith("Bearer"),
          h.get("www-authenticate", ""))


def test_no_view_token_closes_the_view_but_not_the_service() -> None:
    """[주의] 화면 하나 때문에 큐·MCP 가 못 뜨는 것은 과하다 — fail-closed 의 방향을 고른다."""
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = A.BearerAuthMiddleware(inner, "A" * 40, view_prefix="/view", view_token=None)
    st, _, body = call(app, "/view/", headers={"Authorization": _basic("V" * 40)})
    check("[중요] 뷰 토큰이 없으면 화면은 닫힌다", st == 401, str(st))
    check("사유를 말한다", "not configured" in body, body)
    st, _, _ = call(app, "/mcp", headers={"Authorization": "Bearer " + "A" * 40})
    check("그래도 MCP 는 뜬다", st == 200, str(st))


def test_view_token_uses_the_same_strength_rules() -> None:
    """읽기 전용이라고 느슨하게 두지 않는다."""
    d = Path(tempfile.mkdtemp(prefix="axtok"))
    try:
        p = d / "view-token"
        p.write_text("short\n", encoding="utf-8")
        p.chmod(0o600)
        try:
            A.load_view_token(p)
            check("[중요] 짧은 토큰 거부", False, "통과해버렸다")
        except A.AuthError as e:
            check("짧은 토큰 거부", "너무 짧다" in str(e), str(e))
        p.write_text("V" * 40, encoding="utf-8")
        p.chmod(0o644)
        try:
            A.load_view_token(p)
            check("[중요] 열린 권한 거부", False, "통과해버렸다")
        except A.AuthError as e:
            check("열린 권한 거부", "권한" in str(e), str(e))
        check("없으면 None (예외 아님)", A.load_view_token(d / "nope") is None)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── ⑤ 한 포트 ───────────────────────────────────────────────────────────────────

def test_root_redirects_so_the_port_alone_works() -> None:
    """[중요] 실측 2026-08-13: 사용자가 `…:8103/` 를 열자 `{"error":"unauthorized"}` 를 받았다.

    주소에 `/view/` 를 붙여야 하는 것은 사람이 외워야 하는 마찰이고, 마찰은 화면을 안 보게 만든다.
    """
    async def mcp(scope, receive, send):
        raise AssertionError("루트를 MCP 로 넘기면 안 된다")

    r = V.Router(mcp, lambda *a: None, prefix="/view")
    st, h, _ = call(r, "/")
    check("루트는 302", st == 302, str(st))
    check("화면으로 보낸다", h.get("location") == "/view/", h.get("location", ""))
    st, _, _ = call(r, "/favicon.ico")
    check("파비콘은 204 (401 로 콘솔을 더럽히지 않는다)", st == 204, str(st))


def test_opening_root_does_not_open_the_api() -> None:
    """[중요] 라우터가 직접 처리하고 **뒤로 넘기지 않으므로** MCP 가 인증 없이 노출되지 않는다."""
    from master.auth import OPEN_PATHS
    reached: list = []

    async def mcp(scope, receive, send):
        reached.append(scope.get("path"))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"SECRET"})

    router = V.Router(mcp, lambda *a: None, prefix="/view")
    app = A.BearerAuthMiddleware(router, "A" * 40,
                                open_paths=OPEN_PATHS | {"/", V.FAVICON},
                                view_prefix="/view", view_public=True)
    st, _, body = call(app, "/")
    check("루트는 302", st == 302, str(st))
    check("[중요] MCP 에 닿지 않았다", not reached, str(reached))
    check("본문이 새지 않았다", "SECRET" not in body)
    st, _, _ = call(app, "/mcp")
    check("[중요] MCP 는 여전히 401", st == 401, str(st))


def test_old_view_paths_redirect_to_cluster() -> None:
    """[주의] `/view` 는 없앴다 (사용자 지시 2026-08-13) — 북마크를 404 로 만들지 않고 **보낸다.**"""
    hits: list = []

    def mk(tag):
        async def app(scope, receive, send):
            hits.append(tag)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        return app

    r = V.Router(mk("mcp"), mk("view"), prefix="/view", webui=mk("webui"))
    for p in ("/view", "/view/", "/view/cluster.html", "/view/domains.html"):
        st, h, _ = call(r, p)
        check(f"{p} → 302", st == 302, str(st))
        check(f"{p} → /cluster", h.get("location") == "/cluster", h.get("location", ""))
    check("[중요] 뷰 앱을 부르지 않는다", "view" not in hits, str(hits))

    # [중요] 새 주소는 webui 가 가져간다 — 목록은 `webui.app` 이 소유한다(단일 지점)
    hits.clear()
    call(r, "/cluster")
    call(r, "/ontology")
    call(r, "/api/v1/tags")
    call(r, "/mcp")
    check("웹UI 경로는 webui 로", hits[:3] == ["webui"] * 3, str(hits))
    check("MCP 는 그대로", hits[-1] == "mcp", str(hits))


def test_route_list_has_a_single_owner() -> None:
    """[중요] 라우트를 추가할 때 세 곳을 맞춰야 해서 두 번 틀렸다 — 목록은 한 곳이 소유한다."""
    from master.webui.app import PREFIXES
    check("Router 가 그 상수를 쓴다", V.Router.WEBUI_PREFIXES is PREFIXES,
          str(V.Router.WEBUI_PREFIXES))
    check("/cluster 가 목록에 있다", "/cluster" in PREFIXES, str(PREFIXES))


def main() -> int:
    for fn in (test_path_is_whitelisted_not_joined,
               test_unknown_view_is_404_and_traversal_never_reads,
               test_read_only_methods, test_serving_never_regenerates,
               test_no_store_so_refresh_shows_latest,
               test_stale_snapshot_gets_a_banner, test_fresh_snapshot_has_no_banner,
               test_missing_page_says_how_to_make_it,
               test_index_shows_age_and_marks_stale,
               test_view_is_public_by_default,
               test_view_token_and_api_token_do_not_cross,
               test_browser_gets_a_basic_challenge_api_gets_bearer,
               test_no_view_token_closes_the_view_but_not_the_service,
               test_view_token_uses_the_same_strength_rules,
               test_root_redirects_so_the_port_alone_works,
               test_opening_root_does_not_open_the_api,
               test_old_view_paths_redirect_to_cluster,
               test_route_list_has_a_single_owner):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_viewer: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
