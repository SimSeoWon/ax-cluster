"""읽기 전용 화면 서빙 — 🔴 **다른 머신에서 보려면 서빙해야 한다** (중 3.2 후속).

## 🔴 왜 로컬 파일로는 안 되나 (사용자 지적 2026-08-13)

> *"그럴꺼면 웹을 왜써? 작업 머신이나 다른 머신에서 상태를 보거나 … 다 먹통인거잖아."*

맞는 지적이다. **웹 UI 의 목적이 다른 머신에서 보는 것**인데 마스터의 로컬 파일로 만들면 그
요구를 정면으로 못 지킨다. xrdp·scp 는 웹이 아니다. 그리고 도메인 뷰어(소 2.4.2)도 같은 결함을
갖고 있었다 — **둘 다 먹통**이었다. 전임 와처는 포트를 열어 실제로 문서를 봤다.

내가 문서의 *"같은 표면을 쓴다"* 를 **"로컬 파일"** 로 읽은 것이 틀렸다. 그것은 **"두 화면이 한
표면을 공유한다"** 는 뜻이고, 경고는 *서비스 증식*에 대한 것이었다. 그래서:

    🔴 **새 포트·새 유닛·새 ufw 규칙 = 0.** 이미 열려 있고 이미 인증된 8103 에 붙인다.
       두 화면(`cluster.html`·`domains.html`)이 **같은 표면**에서 나온다.

## 🔴 자격증명을 분리했다 — 브라우저에 API 토큰을 주지 않는다

브라우저가 화면을 보려면 자격증명을 들고 있어야 하는데, 그것이 API 토큰이면 **그 브라우저는
MCP 도구를 호출할 자격**을 들고 있는 셈이다. 그래서 `auth.load_view_token()` — **다른 비밀**이고
이 경로에서만 통한다. 이 토큰으로는 큐도 브로커도 MCP 도구도 부를 수 없다.

브라우저는 `Bearer` 를 스스로 못 붙이므로 **Basic** 을 받는다(사용자명은 무시, 비밀번호가 토큰).

## 🔴 요청이 수집을 유발하지 않는다

새로고침 한 번이 BC-250 에 SSH 폴링을 걸면, 주기 가드(120초)를 만든 이유가 사라진다. 그래서
**여기서는 파일을 읽어 주기만** 한다 — 생성은 `python -m master.status html` 이 한다.

⚠️ 그 대가로 화면이 **낡을 수 있다.** 낡은 것을 최신처럼 보이게 두는 것이 최악이므로,
**나이를 계산해 배너로 박는다**(설정값보다 오래되면 눈에 띄게).

## 🔴 경로는 화이트리스트다

클라이언트가 준 문자열로 파일을 열지 않는다 — 이름 두 개만 받는다. 경로 순회(`../`)를 막는
가장 확실한 방법은 **애초에 경로를 받지 않는 것**이다.
"""
from __future__ import annotations

import html
import time
from pathlib import Path

PREFIX = "/view"
STALE_SEC = 900          # 🔴 이보다 오래된 스냅샷은 낡았다고 **화면에** 적는다
NO_STORE = b"no-store, must-revalidate"

# 🔴 화이트리스트. 값은 (파일명, 사람이 읽는 제목, 만드는 명령).
PAGES: dict = {
    "cluster.html": ("클러스터 상태", "python -m master.status html"),
    "domains.html": ("도메인 뷰어", "python -m master.ontology view"),
}


def page_path(root: Path, name: str) -> Path | None:
    """🔴 이름이 화이트리스트에 없으면 **경로를 만들지도 않는다.**"""
    if name not in PAGES:
        return None
    return root / name


def _age(p: Path) -> tuple:
    """`(초, 사람이 읽는 문구)`. 없으면 `(None, …)`."""
    try:
        sec = max(0.0, time.time() - p.stat().st_mtime)
    except OSError:
        return None, "없음"
    if sec < 90:
        return sec, f"{sec:.0f}초 전"
    if sec < 5400:
        return sec, f"{sec / 60:.0f}분 전"
    if sec < 172800:
        return sec, f"{sec / 3600:.1f}시간 전"
    return sec, f"{sec / 86400:.1f}일 전"


_BANNER_CSS = (
    "position:sticky;top:0;z-index:99;margin:-1.5rem -1.5rem 1rem;padding:.6rem .9rem;"
    "background:#d03b3b;color:#fff;font:600 14px/1.5 -apple-system,'Noto Sans KR',sans-serif")


def stale_banner(seconds: float, cmd: str) -> str:
    """🔴 낡은 것을 최신처럼 보이게 두지 않는다."""
    when = f"{seconds / 60:.0f}분" if seconds < 5400 else f"{seconds / 3600:.1f}시간"
    return (f'<div style="{_BANNER_CSS}">⚠️ 이 화면은 <b>{html.escape(when)} 전</b>에 수집된 '
            f'스냅샷이다 — 지금 상태가 아니다. 새로 만들려면 마스터에서 '
            f'<code>{html.escape(cmd)}</code></div>')


def inject(body: str, banner: str) -> str:
    """`<body>` 바로 뒤에 배너를 넣는다.

    ⚠️ 문자열 수술이지만, 대안(파일을 다시 렌더)은 **요청이 수집을 유발**하게 만든다.
    마커를 못 찾으면 앞에 붙인다 — 조용히 빠뜨리지 않는다.
    """
    if not banner:
        return body
    i = body.lower().find("<body>")
    if i < 0:
        return banner + body
    j = i + len("<body>")
    return body[:j] + banner + body[j:]


def index_html(root: Path) -> str:
    rows = []
    for name, (title, cmd) in PAGES.items():
        p = root / name
        sec, when = _age(p)
        if sec is None:
            rows.append(f'<li><b>{html.escape(title)}</b> — 🔴 아직 만들어지지 않았다. '
                        f'마스터에서 <code>{html.escape(cmd)}</code></li>')
            continue
        mark = "⚠️ " if sec > STALE_SEC else ""
        rows.append(f'<li><a href="{name}">{html.escape(title)}</a> — '
                    f'{mark}{html.escape(when)} 수집 · {p.stat().st_size:,} bytes</li>')
    return (
        "<!doctype html><html lang=ko><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<title>AX 클러스터 화면</title><style>"
        ":root{--bg:#fcfcfb;--fg:#0b0b0b;--dim:#52514e}"
        "@media(prefers-color-scheme:dark){:root{--bg:#1a1a19;--fg:#fff;--dim:#c3c2b7}}"
        "body{margin:0;padding:1.5rem;background:var(--bg);color:var(--fg);"
        "font:15px/1.7 -apple-system,'Noto Sans KR',Segoe UI,sans-serif}"
        "h1{font-size:1.3rem;margin:0 0 .8rem}a{color:inherit}"
        "li{margin:.35rem 0}code{font-family:ui-monospace,Menlo,monospace;font-size:.9em}"
        ".sub{color:var(--dim);font-size:.84rem;margin-top:1.2rem}"
        "</style></head><body><h1>AX 클러스터 화면</h1><ul>"
        + "".join(rows) +
        "</ul><div class=\"sub\">🔴 <b>읽기 전용이다.</b> 이 화면을 여는 것이 수집을 유발하지 "
        "않는다 — 새로고침이 BC-250 에 SSH 폴링을 걸면 주기 가드(120초)를 만든 이유가 사라진다. "
        "생성은 마스터에서 사람이 부를 때만 돈다.<br>"
        "🔴 이 자격증명은 <b>화면 전용</b>이다 — 큐·브로커·MCP 도구를 호출할 수 없다."
        "</div></body></html>")


def _respond(send, status: int, body: bytes, ctype: bytes = b"text/html; charset=utf-8"):
    async def go():
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", ctype),
                                (b"content-length", str(len(body)).encode()),
                                # 🔴 캐시하지 않는다 — 새로고침이 항상 최신 파일을 보여야 한다
                                (b"cache-control", NO_STORE)]})
        await send({"type": "http.response.body", "body": body})
    return go()


class ViewApp:
    """순수 ASGI. 🔴 새 의존성을 들이지 않는다 (미들웨어와 같은 방식)."""

    def __init__(self, root_fn, *, prefix: str = PREFIX, stale_sec: int = STALE_SEC):
        self._root_fn = root_fn        # 지연 해석 — 마운트 전환에 재기동이 필요 없다
        self.prefix = prefix
        self.stale_sec = stale_sec

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await _respond(send, 400, b"http only", b"text/plain")
        if scope.get("method", "GET").upper() not in ("GET", "HEAD"):
            # 🔴 읽기 전용이다 — 쓰기 메서드를 받지 않는다
            return await _respond(send, 405, b'{"error":"read-only"}',
                                  b"application/json")

        rest = scope.get("path", "")[len(self.prefix):].lstrip("/")
        try:
            root = Path(self._root_fn())
        except Exception as e:                                # noqa: BLE001
            return await _respond(send, 503, (
                f"<p>🔴 프로젝트를 해석하지 못했다: {html.escape(str(e))}</p>"
            ).encode())

        if not rest:
            return await _respond(send, 200, index_html(root).encode("utf-8"))

        p = page_path(root, rest)
        if p is None:
            # 🔴 화이트리스트 밖 — 경로를 만들지도 않았다
            return await _respond(send, 404, b'{"error":"no such view"}',
                                  b"application/json")
        title, cmd = PAGES[rest]
        if not p.is_file():
            return await _respond(send, 503, (
                f"<p>🔴 <b>{html.escape(title)}</b> 가 아직 만들어지지 않았다.</p>"
                f"<p>마스터에서: <code>{html.escape(cmd)}</code></p>"
            ).encode())

        body = p.read_text(encoding="utf-8", errors="replace")
        sec, _ = _age(p)
        if sec is not None and sec > self.stale_sec:
            body = inject(body, stale_banner(sec, cmd))
        return await _respond(send, 200, body.encode("utf-8"))


class Router:
    """경로로 갈라 준다 — 🔴 **한 포트, 한 유닛**. 서비스를 늘리지 않는다."""

    def __init__(self, default_app, view_app, *, prefix: str = PREFIX):
        self.default_app = default_app
        self.view_app = view_app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith(self.prefix):
            return await self.view_app(scope, receive, send)
        return await self.default_app(scope, receive, send)


def project_root() -> Path:
    """활성 프로젝트의 데이터 디렉토리. **매 요청 해석한다** (§5.5.2 와 같은 이유)."""
    from .context_search.paths import resolve
    return resolve("").root
