"""task_queue MCP stdio 모드 — Claude Code 가 자식 프로세스로 spawn 할 때만 쓴다.

⚠️ 이 모듈은 `mcp` 패키지를 요구한다. 마스터의 주 실행 모드는 systemd 로 도는
HTTP 서버(`--serve`)이고 그쪽은 MCP SDK 가 필요 없으므로, `server.py` 는 이 모듈을
**지연 import** 한다 (PLAN.md §9.5).

🔴 설치본은 `mcp` 2.0.0 이라 `mcp.server.fastmcp` 가 **없다.** 고수준 API 는
`mcp.server.MCPServer` — `master/projects/mcp_server.py` 와 같은 경로를 쓴다.
2026-08-08 까지 이 파일이 옛 경로를 참조해 stdio 모드가 import 단계에서 죽어 있었다
(HTTP `--serve` 는 지연 import 덕에 영향 없었다).
"""
import json
from typing import Optional

from mcp.server import MCPServer

from .persistence import TaskIndex, _project_root
from .logic import claim_task, register_task, register_work

mcp = MCPServer(
    name="task-queue",
    instructions=(
        "AX 클러스터의 작업 큐. work 를 등록하고 그 아래 task 를 등재하며, "
        "워커가 능력(capabilities)에 맞는 task 를 atomic 하게 claim 한다. "
        "모든 상태 전이는 ~/ax-state 에 감사 커밋으로 남는다."
    ),
)


def run_stdio():
    """MCP stdio 서버 기동. `server.main()` 이 무인자 호출 시 여기로 들어온다."""
    mcp.run(transport="stdio")


# ─────────────────────────────────────────
# MCP stdio
# ─────────────────────────────────────────

_mcp_idx: Optional[TaskIndex] = None


def _ensure_mcp_idx() -> TaskIndex:
    global _mcp_idx
    if _mcp_idx is None:
        _mcp_idx = TaskIndex(_project_root())
        _mcp_idx.rebuild()
    return _mcp_idx


@mcp.tool()
def register_work_tool(title: str, target_repo: str,
                        reference_repo: str = "", target_branch: str = "",
                        branch_isolation: bool = True,
                        original_request: str = "", decomposition: str = "",
                        max_extensions_per_work: int = 5, slug: str = "") -> str:
    """work 1건 등록. 인터랙티브 수집 직후 호출."""
    return json.dumps(register_work(_ensure_mcp_idx(),
        title=title, target_repo=target_repo, reference_repo=reference_repo,
        target_branch=target_branch, branch_isolation=branch_isolation,
        original_request=original_request, decomposition=decomposition,
        max_extensions_per_work=max_extensions_per_work, slug=slug),
        ensure_ascii=False)


@mcp.tool()
def register_task_tool(work_id: str, type: str, task_data: dict,
                        base_commit: str = "", target_file: str = "",
                        header_file: str = "", depends_on: Optional[list] = None,
                        hierarchy_level: int = 0, priority: int = 0,
                        stem: str = "", origin: str = "master",
                        parent_attempt: Optional[str] = None,
                        requires: Optional[list] = None) -> str:
    """task 등재. master_orchestrator 또는 검증 에이전트 호출용.

    requires: 실행에 필요한 능력 태그(예 ["ue5"]). 빈값이면 아무 워커나 집는다 (PLAN §5.2-C)."""
    return json.dumps(register_task(_ensure_mcp_idx(),
        work_id=work_id, type=type, task_data=task_data,
        base_commit=base_commit, target_file=target_file, header_file=header_file,
        depends_on=depends_on, hierarchy_level=hierarchy_level,
        priority=priority, stem=stem, origin=origin,
        parent_attempt=parent_attempt, requires=requires), ensure_ascii=False)


@mcp.tool()
def claim_task_tool(worker_id: str, capabilities: Optional[list] = None) -> str:
    """다음 가능 task atomic claim. 없으면 null.

    capabilities: 이 워커의 보유 능력(예 ["ue5"]). **미신고 = 능력 없음** — `requires` 가
    붙은 task 는 집지 못한다 (PLAN §5.2-C)."""
    t = claim_task(_ensure_mcp_idx(), worker_id, capabilities=capabilities)
    return json.dumps(t, ensure_ascii=False) if t else "null"


@mcp.tool()
def list_tasks_tool(status: str = "", work_id: str = "", limit: int = 200) -> str:
    idx = _ensure_mcp_idx()
    tasks = list(idx.tasks.values())
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if work_id:
        tasks = [t for t in tasks if t.get("work_id") == work_id]
    return json.dumps(tasks[:limit], ensure_ascii=False)


@mcp.tool()
def list_works_tool() -> str:
    idx = _ensure_mcp_idx()
    return json.dumps(list(idx.works.values()), ensure_ascii=False)


@mcp.tool()
def status_summary_tool() -> str:
    idx = _ensure_mcp_idx()
    out: dict[str, int] = {}
    for t in idx.tasks.values():
        out[t.get("status", "unknown")] = out.get(t.get("status", "unknown"), 0) + 1
    return json.dumps({"tasks_by_status": out,
                       "works": len(idx.works), "tasks": len(idx.tasks)},
                      ensure_ascii=False)


