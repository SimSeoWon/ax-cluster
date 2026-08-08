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
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
