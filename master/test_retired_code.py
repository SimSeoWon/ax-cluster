"""#234의 폐기 코드 부활·잔여 import와 현행 기능 과잉 철거를 막는다.

실행: .venv/bin/python -B master/test_retired_code.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from client.runtime import client_mcp  # noqa: E402
from master.context_search import context_audit  # noqa: E402
from master.webui import routes  # noqa: E402
from master.work import coordinator, review  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name} — {detail}")


def test_retired_entrypoints_are_gone() -> None:
    for rel in ("master/work/selftest.py", "master/test_selftest.py",
                "master/context_search/vector_fallback.py"):
        check(f"폐기 파일이 없다: {rel}", not (ROOT / rel).exists())
    for module, names in (
        (coordinator, ("assign_attempt", "push_attempt", "verify_and_merge",
                       "cleanup_attempts", "fake_workshop", "run_round")),
        (context_audit, ("archive_root", "plan_archive", "apply_archive", "format_archive_plan")),
        (routes, ("api_rebuild", "api_refuse_mutation")),
        (client_mcp, ("tool_get_object_spec", "tool_get_action_spec")),
    ):
        check(f"폐기 진입점이 없다: {module.__name__}",
              not any(hasattr(module, name) for name in names))


def test_no_retired_imports_in_production() -> None:
    hits = []
    for base in (ROOT / "master", ROOT / "client"):
        for path in base.rglob("*.py"):
            if path.name.startswith("test_") or "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    prefix = node.module or ""
                    names = [prefix, *(f"{prefix}.{alias.name}" for alias in node.names)]
                elif (isinstance(node, ast.Call) and node.args
                      and isinstance(node.args[0], ast.Constant)
                      and isinstance(node.args[0].value, str)):
                    function = node.func
                    if ((isinstance(function, ast.Name) and function.id == "__import__")
                        or (isinstance(function, ast.Attribute) and function.attr == "import_module")):
                        names = [node.args[0].value]
                if any(name.split(".")[-1] in {"selftest", "vector_fallback"} for name in names):
                    hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    check("프로덕션에 폐기 모듈 import가 없다", not hits, str(hits))


def test_current_entrypoints_remain() -> None:
    check("현행 큐 조회 fetch_work가 남는다", callable(review.fetch_work))
    check("공용 Git 헬퍼가 남는다", all(callable(getattr(coordinator, name, None))
          for name in ("GitError", "_git_cmd", "_git", "_git_rc", "_noop_log")))
    check("문서 진단·복구가 남는다", all(callable(getattr(context_audit, name, None))
          for name in ("audit", "plan_repair", "apply_repair", "post_unwrap_diagnosis")))
    tools = {tool["name"] for tool in client_mcp.TOOLS}
    check("MCP의 실제 스펙 조회 도구가 남는다", {"get_object_spec", "get_action_spec"} <= tools)


if __name__ == "__main__":
    for fn in (test_retired_entrypoints_are_gone, test_no_retired_imports_in_production,
               test_current_entrypoints_remain):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_retired_code: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
