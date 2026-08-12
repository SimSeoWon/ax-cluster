"""프로젝트 MCP 서버 진입점 — `python -m master.projects`.

포트 8103 (`ss -tln` 으로 비어 있음 확인, 2026-08-08). 8101·8102 와 같은 대역이다.
🔴 인증 계층이 없다 — LAN 한정 개방으로만 방어한다:
   `ufw allow from 192.168.0.0/24 to any port 8103`. `Anywhere` 로 넓히지 말 것.

DNS 리바인딩 보호는 **켜 둔다.** 방화벽이 막는 것은 LAN 밖 접근이고, 이 보호가 막는 것은
LAN 안의 브라우저가 악성 페이지에 속아 이 포트를 찌르는 경로다 — 서로 다른 위협이다.
⚠️ SDK 의 `allowed_hosts` 는 와일드카드 `*` 를 지원하지 않는다. 정확 일치 또는 `host:*`
(포트 와일드카드) 뿐이다 — `["*"]` 를 넣으면 전부 거부된다(2026-08-08 실측).
"""
from __future__ import annotations

import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from ..auth import BearerAuthMiddleware, load_token, load_view_token
from ..viewer import PREFIX as VIEW_PREFIX
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
    auth_token = load_token()   # 🔴 없으면 여기서 예외 — 인증 없이 뜨지 않는다
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
    # 🔴 **읽기 전용 화면을 같은 포트에 붙인다** (중 3.2 후속, 사용자 지적 2026-08-13).
    #    웹 UI 의 목적이 *다른 머신에서 보는 것*이라 서빙하지 않으면 요구를 못 지킨다.
    #    새 포트·유닛·ufw 규칙 0 — 이미 열려 있고 이미 인증된 이 포트를 쓴다.
    #    🔴 자격증명은 **분리**한다: 뷰 토큰으로는 MCP 도구를 부를 수 없다(`auth.py` § 참조).
    #    ⚠️ 뷰 토큰이 없으면 화면만 안 열린다 — 큐·MCP 는 그대로 뜬다(fail-closed 의 방향).
    view_token = load_view_token()
    served = Router(app, ViewApp(project_root), prefix=VIEW_PREFIX)
    if view_token:
        print(f"[view] {VIEW_PREFIX}/ 열림 — Basic 인증(비밀번호 = 뷰 토큰)")
    else:
        print(f"[view] {VIEW_PREFIX}/ 🔴 닫힘 — 뷰 토큰이 없다: "
              f"python -m master.auth init-view")

    # 🔴 DNS 리바인딩 보호와 **별개**다. 그쪽은 브라우저가 속아서 찌르는 경로를 막고,
    #    이쪽은 아무나 찌르는 것을 막는다 — 서로 다른 위협이라 둘 다 필요하다.
    uvicorn.run(BearerAuthMiddleware(served, auth_token,
                                     view_prefix=VIEW_PREFIX, view_token=view_token),
                host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
