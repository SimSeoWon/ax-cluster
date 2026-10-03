"""파이썬 파싱 — `ast` (`#712`, 2026-10-03). 클래스 그래프·의존 그래프의 파이썬 갈래.

🔴 [중요] **원전에 없던 확장이다.** 원전 그래프는 C++(tree-sitter) 하나였다(`AgentTest` 에 `ast`
   사용 0). 순수 파이썬 프로젝트(ax-cluster 자신)를 등록하자 온보딩 `graph` 가 *"C++ 파일이 없다"*
   로 멈췄고, 합성 문서 89개 중 61개의 `related_classes` 가 전부 `?` 였다 — 경로를 풀 그래프가
   없어서다. 의존 그래프도 `.py` 를 추적 대상에 넣어 두고 `#include` 정규식만 돌려 간선이 0이었다.

[중요] **사용자 결정 2026-10-03**:
   - 클래스 이름이 여러 모듈에 겹치면 **겹치는 것만** 모듈명을 붙인다(`master.verdict.Verdict`).
     파이썬은 UE 와 달리 이름이 전역 유일하지 않다(실측: 테스트 제외 16개 — `Verdict` 4곳 등).
     짧은 이름으로는 **어느 쪽인지 고르지 않는다** — 문서의 「Verdict」 는 `?` 로 남는다
   - **테스트 파일(`test_*.py`)은 클래스 그래프에서 뺀다** — 보조 클래스(`P`·`_Paths`)는 잡음이고
     충돌의 대부분이다. import 의존은 테스트도 그대로 들어간다

**자기완결** — `parse.py` 와 같은 원칙으로 같은 패키지의 어떤 것도 import 하지 않는다.
"""
from __future__ import annotations

import ast
from pathlib import PurePosixPath

PY_EXTS = {".py"}


def is_test_file(rel: str) -> bool:
    return PurePosixPath(rel).name.startswith("test_")


def module_name(rel: str) -> str:
    """`master/work/usage.py` → `master.work.usage` · `pkg/__init__.py` → `pkg`."""
    p = PurePosixPath(rel.replace("\\", "/"))
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _base_name(node) -> str:
    """기반 클래스 식 → 이름 하나. `a.b.C` → `C` · `Generic[T]` → `Generic` · 모르면 ''."""
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def parse_source(text: str) -> list[dict]:
    """**모듈 최상위** 클래스 선언 → C++ 파서(`parse.parse_source`)와 같은 모양.

    `{name, parents, line, prefix, kind, methods: [{name, line}]}`. 중첩 클래스·함수 안 클래스는
    넣지 않는다 — 그래프 키는 모듈 수준 이름이다. 파싱이 안 되면 빈 리스트(호출자가 센다).
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out: list[dict] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        parents = [b for b in (_base_name(x) for x in node.bases) if b and b != "object"]
        methods = [{"name": m.name, "line": m.lineno} for m in node.body
                   if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        out.append({"name": node.name, "parents": parents, "line": node.lineno,
                    "prefix": "", "kind": "class", "methods": methods})
    return out


def _candidates(mod: str) -> list[str]:
    base = mod.replace(".", "/")
    return [f"{base}.py", f"{base}/__init__.py"] if base else []


def resolve_imports(rel: str, text: str, known: set) -> list[str]:
    """한 파일의 import → **저장소 안에 실재하는** 대상 파일 경로(`repo/` 기준). 외부 패키지는 버린다.

    `from .x import y` 는 `y` 가 하위 모듈일 수도 있어 둘 다 시도한다(`from . import synth`).
    `known` 은 저장소의 파일 집합이다 — 존재 여부로만 판정한다, 지어내지 않는다.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    pkg = module_name(rel)
    if not PurePosixPath(rel).name == "__init__.py":
        pkg = pkg.rpartition(".")[0]          # 모듈이면 그 패키지가 상대 import 의 기준이다
    found: list[str] = []

    def add(mod: str) -> None:
        for c in _candidates(mod):
            if c in known and c != rel and c not in found:
                found.append(c)
                return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = pkg.split(".") if pkg else []
                up = node.level - 1
                if up > len(parts):
                    continue
                anchor = ".".join(parts[:len(parts) - up] if up else parts)
                mod = ".".join(x for x in (anchor, node.module or "") if x)
            else:
                mod = node.module or ""
            add(mod)
            for a in node.names:
                if a.name != "*":
                    add(f"{mod}.{a.name}" if mod else a.name)
    return found


def disambiguate(entries: list[tuple[str, dict]]) -> tuple[list[tuple[str, dict]], list[str]]:
    """`(이름, 정보)` 목록에서 **파이썬 파일끼리 겹치는 이름만** 모듈명을 붙인다.

    반환: (고친 목록, 겹친 짧은 이름들). C++ 항목은 손대지 않는다 — UE 는 이름이 전역 유일하다는
    종전 전제(마지막 것이 이긴다)를 그대로 둔다.
    """
    py_count: dict[str, int] = {}
    for name, info in entries:
        if str(info.get("file", "")).endswith(".py"):
            py_count[name] = py_count.get(name, 0) + 1
    dup = sorted(n for n, c in py_count.items() if c > 1)
    dset = set(dup)
    out = []
    for name, info in entries:
        if name in dset and str(info.get("file", "")).endswith(".py"):
            name = f"{module_name(info['file'])}.{name}"
        out.append((name, info))
    return out, dup
