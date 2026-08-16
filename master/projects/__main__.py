"""프로젝트 MCP 서버 진입점 — `python -m master.projects`.

포트 8103 (`ss -tln` 으로 비어 있음 확인, 2026-08-08). 8101·8102 와 같은 대역이다.
[중요] 인증 계층이 없다 — LAN 한정 개방으로만 방어한다:
   `ufw allow from 192.168.0.0/24 to any port 8103`. `Anywhere` 로 넓히지 말 것.

DNS 리바인딩 보호는 **켜 둔다.** 방화벽이 막는 것은 LAN 밖 접근이고, 이 보호가 막는 것은
LAN 안의 브라우저가 악성 페이지에 속아 이 포트를 찌르는 경로다 — 서로 다른 위협이다.
[주의] SDK 의 `allowed_hosts` 는 와일드카드 `*` 를 지원하지 않는다. 정확 일치 또는 `host:*`
(포트 와일드카드) 뿐이다 — `["*"]` 를 넣으면 전부 거부된다(2026-08-08 실측).
"""
from __future__ import annotations

import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from ..auth import OPEN_PATHS, BearerAuthMiddleware, load_token, load_view_token
from ..viewer import FAVICON, PREFIX as VIEW_PREFIX
from ..viewer import Router, ViewApp, project_root
from .mcp_server import mcp

# LAN IP 는 CLAUDE.md 기준. 추가가 필요하면 AX_PROJECTS_ALLOWED_HOSTS 에 콤마로 나열한다.
_DEFAULT_HOSTS = ["127.0.0.1", "localhost", "192.168.0.57", "sim-desktop"]


def allowed_hosts() -> list[str]:
    extra = [
        h.strip()
        for h in os.environ.get("AX_PROJECTS_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    ]
    hosts: list[str] = []
    for h in _DEFAULT_HOSTS + extra:
        hosts += [h, f"{h}:*"]
    return hosts


def main() -> None:
    host = os.environ.get("AX_PROJECTS_HOST", "0.0.0.0")
    port = int(os.environ.get("AX_PROJECTS_PORT", "8103"))
    hosts = allowed_hosts()
    auth_token = load_token()   # [중요] 없으면 여기서 예외 — 인증 없이 뜨지 않는다
    app = mcp.streamable_http_app(
        host=host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            # Origin 은 브라우저만 붙인다. 목록이 비면 Origin 이 있는 요청이 전부 막힌다.
            allowed_origins=[f"http://{h}" for h in hosts]
            + [f"https://{h}" for h in hosts],
        ),
    )
    # [중요] **읽기 전용 화면을 같은 포트에 붙인다** (중 3.2 후속, 사용자 지적 2026-08-13).
    #    웹 UI 의 목적이 *다른 머신에서 보는 것*이라 서빙하지 않으면 요구를 못 지킨다.
    #    새 포트·유닛·ufw 규칙 0 — 이미 열려 있고 이미 인증된 이 포트를 쓴다.
    #    [중요] 자격증명은 **분리**한다: 뷰 토큰으로는 MCP 도구를 부를 수 없다(`auth.py` § 참조).
    #    [주의] 뷰 토큰이 없으면 화면만 안 열린다 — 큐·MCP 는 그대로 뜬다(fail-closed 의 방향).
    # [중요] **뷰는 인증 없이 열린다** (사용자 결정 2026-08-13: *"그냥 있는거 보여주는 뷰어"*).
    #    근거는 `auth.BearerAuthMiddleware.__init__` 의 § 에 있다 — 이 경로는 조작이 불가능하고,
    #    쓰이지 않는 화면을 만드는 것이 더 나쁘다. 남는 방어는 **ufw LAN 한정** 한 층이다.
    require = os.environ.get("AX_VIEW_REQUIRE_TOKEN", "").strip() in ("1", "true", "yes")
    view_token = load_view_token() if require else None
    # [중요] **원전 웹 UI 복각** (사용자 지시 2026-08-13) — `/` `/ontology*` `/api/v1/*`.
    #    `/view/` 는 스냅샷 화면(중 3.2)이라 그대로 둔다: 둘은 다른 것이다.
    from ..webui.app import PREFIXES as WEB_PREFIXES
    from ..webui.app import WebUI
    from ..context_search.paths import resolve as _resolve
    web = WebUI(lambda: _resolve(""))
    served = Router(app, ViewApp(project_root), prefix=VIEW_PREFIX, webui=web)
    if not require:
        print(f"[view] {VIEW_PREFIX}/ 공개 — 인증 없음 (LAN 한정 · 읽기 전용)")
    elif view_token:
        print(f"[view] {VIEW_PREFIX}/ 잠김 — Basic 인증(비밀번호 = 뷰 토큰)")
    else:
        print(f"[view] {VIEW_PREFIX}/ [중요] 닫힘 — AX_VIEW_REQUIRE_TOKEN 인데 뷰 토큰이 없다: "
              f"python -m master.auth init-view")

    # [중요] DNS 리바인딩 보호와 **별개**다. 그쪽은 브라우저가 속아서 찌르는 경로를 막고,
    #    이쪽은 아무나 찌르는 것을 막는다 — 서로 다른 위협이라 둘 다 필요하다.
    # [중요] 루트와 파비콘을 인증에서 연다 — 라우터가 **직접 처리하고 뒤로 넘기지 않으므로**
    #    MCP 앱에 인증 없이 도달하는 경로가 생기지 않는다(리다이렉트와 빈 응답뿐이다).
    uvicorn.run(BearerAuthMiddleware(served, auth_token,
                                     # [중요] 원전 UI 경로는 공개(읽기 전용) — `/mcp` 는 잠김
                                     open_paths=OPEN_PATHS | {"/", FAVICON},
                                     # [중요] 목록을 여기 다시 적지 않는다 — `webui.app` 이 소유한다.
                                     #    `/cluster` 를 빼먹어 401, 그 다음 라우터에서 또 빠져
                                     #    404 가 났다(실측). 단일 지점이 그 부류를 없앤다.
                                     #    `/view` 는 옛 주소(→ `/cluster` 302)라 함께 열어 둔다.
                                     public_prefixes=WEB_PREFIXES + ("/view",),
                                     view_prefix=VIEW_PREFIX, view_token=view_token,
                                     view_public=not require),
                host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
