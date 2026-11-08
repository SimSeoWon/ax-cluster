"""검사 파일 직접 실행 규약 (`#921`) — `master/test_*.py` 는 `python master/test_x.py` 로 돌아야 한다.

    .venv/bin/python master/test_test_runnable.py

[중요] 왜: 저장소의 전수 실행 루프(`CLAUDE.md` Tests)와 공식 통합(`checks.json`)은 검사 파일을 **직접**
실행한다. 모듈 수준에서 `master…` 를 import 하는데 그 앞에 `sys.path.insert` 가 없으면 직접 실행이
`ModuleNotFoundError` 로 죽는다 — 2026-11-08 #820 `test_scope_check.py` 가 「7/7」로 보고됐지만 직접
실행 rc=1 이었다(`-m unittest` 로만 통과). 정적으로 본다(AST · 실행 없음).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _imports_master(node) -> bool:
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] == "master" for a in node.names)
    if isinstance(node, ast.ImportFrom):
        return not node.level and (node.module or "").split(".")[0] == "master"
    return False


def _inserts_path(node, src: str) -> bool:
    seg = ast.get_source_segment(src, node) or ""
    return "sys.path.insert" in seg or "sys.path[:0]" in seg


def violation(src: str) -> str:
    """위반이면 사유, 아니면 빈 문자열. 모듈 수준 문장만 본다(함수 안 import 는 그때 경로가 이미 있다)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"구문 오류 {e.lineno}행"
    for node in tree.body:
        if _inserts_path(node, src):
            return ""
        if _imports_master(node):
            return f"{node.lineno}행 master import 앞에 sys.path.insert 가 없다"
    return ""


def test_samples() -> None:
    good = "import sys\nfrom pathlib import Path\nsys.path.insert(0, 'x')\nfrom master import a\n"
    bad = "import unittest\nfrom master.work.scope_check import x\n"
    late = "from master import a\nimport sys\nsys.path.insert(0, 'x')\n"
    inner = "import sys\ndef f():\n    from master import a\n"
    check("표본 — 앞에 sys.path.insert → 통과", violation(good) == "")
    check("표본 — 없음 → 위반", "2행" in violation(bad), violation(bad))
    check("표본 — 뒤에 있음 → 위반", "1행" in violation(late), violation(late))
    check("표본 — 함수 안 import 만 → 통과", violation(inner) == "")


def test_repo() -> None:
    files = sorted((ROOT / "master").glob("test_*.py"))
    bad = [(f.name, why) for f in files if (why := violation(f.read_text(encoding="utf-8")))]
    check(f"master/test_*.py {len(files)}개 전부 직접 실행 가능", not bad, str(bad[:10]))


def main() -> int:
    test_samples()
    test_repo()
    print(f"{'OK' if not FAIL else 'FAIL'} test_test_runnable: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
