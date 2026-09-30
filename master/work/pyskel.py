"""`.py` 골조의 **동결 · 스텁 잔존 · 구문** — 층1 의 Python 판 (`#695` P3).

## 왜 따로 있나

`skeleton.frozen_decls` 는 **헤더의 선언 줄**을 키로 쓴다(원전 `worker/validator._frozen_decls`).
Python 에는 헤더가 없고 선언과 정의가 한 몸이라 그 방식이 성립하지 않는다 — 실측 2026-09-30:
`is_header(".py")` 가 False 라 시그니처 변경·`def` 삭제가 **둘 다 층1 을 통과했다**.
그래서 AST 로 잰다. **LLM 0 · 표준 라이브러리만.**

## 무엇을 보나

    동결       모듈 최상위 함수·클래스, 클래스의 메서드 — **이름 + 인자 + 반환 표기**가 키다.
               추가는 허용, **변경·삭제는 위반**이다 (C++ 판과 같은 계약, 소 2.1.1)
    스텁 잔존  골조에서 `# [PSEUDO]` 가 들어 있던 함수가 구현 뒤에도 본문이
               `raise NotImplementedError` / `...` 뿐이면 **안 채운 것**이다
               [중요] 마커 주석만 지우고 스텁을 남기는 구멍을 막는다 — 마커 검사는 주석만 본다
    구문       구현본이 파싱되지 않으면 위반이다 (C++ 는 조각 빌드가 잡지만 Python 판에는 그 자리가 없다)

[주의] **본문 모양을 골조 단계에서 보지 않는다** — 그건 2026-09-03 에 걷은 계층이다. 여기는
**구현 뒤**(층1)이고, 원전 `validator.py` 도 이 자리에서 *"빈 함수 본문·미구현은 reject"* 한다.
"""
from __future__ import annotations

import ast
import re

_PSEUDO_LINE = re.compile(r"^[ \t]*#[ \t]*\[PSEUDO(?::\d+)?\]")


def _sig(qual: str, node) -> str:
    """함수 키 — `def 수식명(인자) -> 반환`. 기본값·주석까지 `ast.unparse` 그대로 비교한다."""
    ret = f" -> {ast.unparse(node.returns)}" if getattr(node, "returns", None) else ""
    pre = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{pre}{qual}({ast.unparse(node.args)}){ret}"


def _walk(tree):
    """`(수식명, 노드)` — 최상위 함수·클래스와 클래스 안의 메서드. 중첩 함수는 본문이다."""
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n.name, n
        elif isinstance(n, ast.ClassDef):
            yield n.name, n
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{n.name}.{m.name}", m


def parse(text: str):
    """파싱. 실패하면 `(None, "파일:행: 사유")` — 호출자가 위반으로 적는다."""
    try:
        return ast.parse(text or ""), ""
    except SyntaxError as e:
        return None, f"{e.lineno}: {e.msg}"


def frozen(text: str) -> set:
    """동결 키 집합. 파싱이 안 되면 빈 집합 — [주의] 호출자는 `parse` 로 먼저 가른다."""
    tree, _ = parse(text)
    if tree is None:
        return set()
    out = set()
    for q, n in _walk(tree):
        if isinstance(n, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in n.bases)
            out.add(f"class {q}({bases})")
        else:
            out.add(_sig(q, n))
    return out


def violation(original: str, new: str) -> str:
    """동결 위반 문장. 없으면 빈 값. **추가는 허용, 변경·삭제는 위반.**"""
    tree, why = parse(new)
    if tree is None:
        return f"구문 오류 — {why}"
    gone = frozen(original) - frozen(new)
    if not gone:
        return ""
    return "동결 인터페이스 변경/삭제: " + "; ".join(sorted(gone)[:3]) + \
        (f" 외 {len(gone) - 3}" if len(gone) > 3 else "")


def _is_stub(node) -> bool:
    """본문이 (docstring +) `raise NotImplementedError[...]` 또는 `...` 뿐인가."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None),
                                                            ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1:
        return False
    s = body[0]
    if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis:
        return True
    if isinstance(s, ast.Raise) and s.exc is not None:
        e = s.exc.func if isinstance(s.exc, ast.Call) else s.exc
        return isinstance(e, ast.Name) and e.id == "NotImplementedError"
    return False


def pseudo_functions(text: str) -> set:
    """골조에서 `# [PSEUDO]` 줄을 **몸 안에** 가진 함수의 수식명."""
    tree, _ = parse(text)
    if tree is None:
        return set()
    lines = (text or "").splitlines()
    out = set()
    for q, n in _walk(tree):
        if isinstance(n, ast.ClassDef):
            continue
        seg = lines[n.lineno - 1:(n.end_lineno or n.lineno)]
        if any(_PSEUDO_LINE.match(ln) for ln in seg):
            out.add(q)
    return out


def unfilled(original: str, new: str) -> list:
    """골조에서 채우라던 함수 중 **아직 스텁인 것**의 수식명."""
    want = pseudo_functions(original)
    if not want:
        return []
    tree, _ = parse(new)
    if tree is None:
        return []                    # 구문 오류는 `violation` 이 말한다
    return sorted(q for q, n in _walk(tree)
                  if q in want and not isinstance(n, ast.ClassDef) and _is_stub(n))
