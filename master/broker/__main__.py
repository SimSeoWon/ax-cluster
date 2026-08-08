"""브로커 진입점 — `python -m master.broker`.

포트 8102 (`ss -tln` 으로 비어 있음 확인, 2026-08-08). task_queue(8101) 와 같은 대역이다.
🔴 task_queue 와 마찬가지로 **인증 계층이 없다.** LAN 한정 개방으로만 방어한다 —
`ufw allow from 192.168.0.0/24 to any port 8102`. `Anywhere` 로 넓히지 말 것.
"""
from __future__ import annotations

import os

import uvicorn

from .server import create_app


def main() -> None:
    host = os.environ.get("AX_BROKER_HOST", "0.0.0.0")
    port = int(os.environ.get("AX_BROKER_PORT", "8102"))
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
