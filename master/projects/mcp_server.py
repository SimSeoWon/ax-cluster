"""프로젝트 등록·전환 MCP 서버 — 대화형으로 처리하기 위해 외부로 노출한다 (PLAN §5.5).

노출 도구 2종:
  · register_project — 디지털 트윈을 생성할 프로젝트를 등록한다(설정 파일 생성부터)
  · set_active       — 가리키는 프로젝트를 바꾼다

읽기용 2종(부수):
  · list_projects · check_registry

🔴 `task_queue`(8101)·브로커(8102) 와 마찬가지로 **인증 계층이 없다.**
LAN 한정 개방으로만 방어한다 — `ufw allow from 192.168.0.0/24 to any port 8103`.
`Anywhere` 로 넓히지 말 것.

⚠️ 설치된 SDK 는 `mcp` 2.0.0 이라 `mcp.server.fastmcp` 가 **없다**
(`task_queue/mcp_server.py` 는 아직 그 경로를 쓰고 있어 stdio 모드가 깨져 있다).
2.0.0 의 고수준 API 는 `mcp.server.MCPServer` 다.
"""
from __future__ import annotations

import json

from mcp.server import MCPServer

from .config import ConfigError
from .logic import (
    list_projects,
    list_workshops,
    register_project,
    remove_workshop,
    set_active,
    set_workshop,
)
from .config import Registry

mcp = MCPServer(
    name="ax-projects",
    instructions=(
        "AX 클러스터 마스터가 보유한 디지털 트윈 디렉토리를 관리한다. "
        "프로젝트를 등록하면 그 디렉토리에 컨텍스트 문서와 온톨로지가 쌓이고, "
        "가리키는 프로젝트(active)는 한 번에 하나뿐이다."
    ),
)


def _fail(e: Exception) -> str:
    return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def register_project_tool(
    name: str,
    project_id: str,
    bare_path: str = "",
    clone_url: str = "",
    branch: str = "main",
    engine: str = "",
) -> str:
    """디지털 트윈을 생성할 프로젝트를 등록한다.

    설정 파일(config.yaml) 생성부터 시작해 디렉토리·루트 목록·gitignore·원본 잠금까지
    한 번에 처리한다. 소스 클론과 최초 색인은 포함하지 않는다.

    name: 디렉토리명이 된다(예: ModularStage).
    project_id: Gitea 저장소 식별자 '<owner>/<repo>'. 별칭을 지어내지 말 것 —
                훅 이벤트가 이 값으로 온다.
    """
    try:
        return json.dumps(
            register_project(
                name, project_id, bare_path=bare_path, clone_url=clone_url,
                branch=branch, engine=engine,
            ),
            ensure_ascii=False,
        )
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def set_active_tool(name: str) -> str:
    """가리키는 프로젝트를 바꾼다. 디렉토리는 전부 남고 마운트 대상만 바뀐다."""
    try:
        return json.dumps(set_active(name), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def list_projects_tool() -> str:
    """등록된 프로젝트와 각각의 갱신 워터마크, 지금 가리키는 것을 돌려준다."""
    try:
        return json.dumps(list_projects(), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def set_workshop_tool(
    name: str,
    host: str,
    driven: str = "interactive",
    path: str = "",
    user: str = "",
    note: str = "",
) -> str:
    """작업장 한 대의 UE5 체크아웃 위치를 등록·갱신한다 (PLAN §5.5.4).

    마스터는 이 경로를 **읽지도 쓰지도 않는다** — 어디로 작업을 보낼지 정하는
    라우팅 정보다.

    host:   작업장 IP 또는 호스트명 (예: 192.168.0.2).
    driven: 'ssh' = 마스터가 밀어넣을 수 있다 / 'interactive' = 사람이 앉아서 한다.
            'ssh' 를 고르면 path 와 user 가 반드시 있어야 한다.
    path:   그 머신의 프로젝트 경로. 윈도우는 역슬래시 그대로 (예: E:\\trunk\\ModularStage).
    """
    try:
        return json.dumps(
            set_workshop(name, host, driven=driven, path=path, user=user, note=note),
            ensure_ascii=False,
        )
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def remove_workshop_tool(name: str, host: str) -> str:
    """워크숍 등록을 해제한다. 원격 디렉토리는 건드리지 않는다."""
    try:
        return json.dumps(remove_workshop(name, host), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def list_workshops_tool(name: str = "") -> str:
    """이 프로젝트를 체크아웃해 둔 작업장들을 돌려준다.

    name 을 비우면 지금 가리키는 프로젝트를 본다. `drivable_hosts` 는 마스터가
    SSH 로 작업을 밀어넣을 수 있는 머신 목록이다.
    """
    try:
        return json.dumps(list_workshops(name), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def check_registry_tool() -> str:
    """3자 일치 검사 — 루트 목록 ↔ 디렉토리 ↔ 각 config.yaml 의 name."""
    try:
        reg = Registry.load()
        problems = reg.check()
        return json.dumps(
            {"ok": not problems, "active": reg.active, "problems": problems},
            ensure_ascii=False,
        )
    except (ConfigError, OSError) as e:
        return _fail(e)
