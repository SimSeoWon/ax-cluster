"""MCP 서버 모듈 회귀 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_mcp_servers.py

🔴 **이 테스트가 존재하는 이유.** 2026-08-08 까지 `task_queue/mcp_server.py` 가
`mcp.server.fastmcp` 를 import 하고 있었는데 설치본은 `mcp` 2.0.0 이라 그 경로가 없다.
stdio 모드가 **import 단계에서 죽어 있었는데도 아무도 몰랐다** — HTTP `--serve` 는 이 모듈을
지연 import 하고, 어떤 테스트도 이 모듈을 건드리지 않았기 때문이다.

그래서 여기서 검사하는 것은 로직이 아니라 **모듈이 import 되고 도구가 실제로 등록되는가**다.
SDK 를 올리거나 도구를 추가할 때 이 테스트가 먼저 깨져야 한다.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# 실제 상태 저장소를 건드리지 않는다.
_TMP = Path(tempfile.mkdtemp(prefix="ax-mcp-test-"))
os.environ["AX_TASK_QUEUE_ROOT"] = str(_TMP / "state")
os.environ["AX_GITEA_REPO_ROOT"] = str(_TMP / "gitea")
os.environ["AX_PROJECTS_ROOT"] = str(_TMP / "projects")

_passed = 0
_failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {label}")
    else:
        _failed += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def tool_names(server) -> list[str]:
    """MCPServer.list_tools() 는 코루틴이다 (2.0.0)."""
    return [t.name for t in asyncio.run(server.list_tools())]


print("\n[1] mcp SDK — 고수준 API 경로")
try:
    from mcp.server import MCPServer
    check("mcp.server.MCPServer 가 있다", True)
except ImportError as e:  # pragma: no cover - 환경 문제
    check("mcp.server.MCPServer 가 있다", False, str(e))
    sys.exit(1)

# 옛 경로를 쓰면 안 된다는 것을 명시적으로 남긴다.
try:
    import mcp.server.fastmcp  # noqa: F401
    _has_fastmcp = True
except ImportError:
    _has_fastmcp = False
check("설치본에 mcp.server.fastmcp 는 없다 (있다면 SDK 가 바뀐 것)", not _has_fastmcp)


print("\n[2] task_queue — stdio MCP 서버")
from master.task_queue import mcp_server as tq  # noqa: E402

check("모듈 import", True)
check("MCPServer 인스턴스", type(tq.mcp).__name__ == "MCPServer", type(tq.mcp).__name__)
_tq = tool_names(tq.mcp)
check("도구 6종 등록", len(_tq) == 6, f"실제 {len(_tq)}종: {_tq}")
for name in ("register_work_tool", "register_task_tool", "claim_task_tool",
             "list_tasks_tool", "list_works_tool", "status_summary_tool"):
    check(f"  {name}", name in _tq)
check("run_stdio 가 호출 가능", callable(tq.run_stdio))


print("\n[3] projects — 프로젝트 레지스트리 MCP 서버")
from master.projects import mcp_server as pj  # noqa: E402

check("모듈 import", True)
check("MCPServer 인스턴스", type(pj.mcp).__name__ == "MCPServer", type(pj.mcp).__name__)
_pj = tool_names(pj.mcp)
check("도구 29종 등록", len(_pj) == 29, f"실제 {len(_pj)}종: {_pj}")
# 🔴 **감사 창구 둘** (소 3.4.1·3.4.2, 2026-08-14) — 원전은 감사를 **요청 시** 부르는 도구로
#   뒀다(`audit_context_md` · `analyze_search_log`). 유휴 배치가 아니다.
for _t in ("audit_context_tool", "analyze_search_log_tool"):
    check(f"  🔴 감사 창구: {_t}", _t in _pj, str(_pj))
# 🔴 **버전 핸드셰이크** (소 3.1.8, κ.9 계약 표면) — 이것이 없으면 소비자가 어느 마스터와
#   말하는지 확인할 방법이 없다(원전이 get_server_version 을 만든 계기와 같은 상태).
check("  🔴 버전 핸드셰이크: get_master_version_tool", "get_master_version_tool" in _pj, str(_pj))
# 🔴 개수만 세면 다음에 또 깨진다 — **요청자가 실제로 부를 것**이 있는지 이름으로 본다.
#   `.33` 은 이것들이 없으면 개념을 추가·수정·제거할 수단이 아예 없다(2026-08-09 실측:
#   어휘(별칭)만 다룰 수 있고 개념은 마스터 CLI 에만 있었다).
for _t in ("create_domain_tool", "edit_ontology_item_tool", "remove_ontology_item_tool",
           "lock_ontology_item_tool", "list_locked_tool", "unassigned_classes_tool",
           "sync_ontology_tool", "protect_ontology_tool", "list_protected_tool", "drift_audit_tool", "infer_domain_tool"):
    check(f"  🔴 요청자 창구: {_t}", _t in _pj, str(_pj))
for name in ("register_project_tool", "set_active_tool",
             "list_projects_tool", "check_registry_tool",
             # 워크숍 (§5.5.4)
             "set_workshop_tool", "remove_workshop_tool", "list_workshops_tool",
             "check_workshops_clean_tool",
             # 워크플로우 (§4.7) — 작업장이 부르는 두 창구
             "register_work_tool", "get_manifest", "get_code"):
    check(f"  {name}", name in _pj)


print("\n[4] 두 서버가 같은 SDK 경로를 쓴다")
check("같은 MCPServer 클래스", type(tq.mcp) is type(pj.mcp))


print("\n[5] 스키마가 생성된다 — 까다로운 인자 포함")
_schemas = {t.name: t.input_schema for t in asyncio.run(tq.mcp.list_tools())}
_rt = _schemas["register_task_tool"]
check("register_task_tool 필수 인자", _rt.get("required") == ["work_id", "type", "task_data"],
      str(_rt.get("required")))
for arg in ("task_data", "depends_on", "requires"):
    check(f"  {arg} 스키마 생성됨", arg in _rt.get("properties", {}))


print("\n" + "=" * 46)
print(f"통과 {_passed} · 실패 {_failed}")
print("=" * 46)
sys.exit(1 if _failed else 0)
