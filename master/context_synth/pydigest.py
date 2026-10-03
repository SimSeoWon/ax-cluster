"""파이썬 소스의 **요약본** — 함수 본문을 빼고 구조·독스트링·주석을 남긴다 (`#711`, 2026-10-03).

🔴 [중요] **왜 있나.** 합성 프롬프트는 소스를 앞에서 `CONTENT_LIMIT`(4,000자) 만큼 자른다.
   ax-cluster(파이썬) 실측: 347개 중 **297개(85%)** 가 그 상한을 넘고 중앙값이 8,324자다 —
   모델이 파일의 절반도 못 보고, 이 저장소처럼 머리 주석이 길면 뒤쪽 정의는 아예 안 들어간다.
   그런데 이 저장소의 「왜」(사용자 결정·실측 근거)는 **독스트링과 주석**에 있다. 그래서
   자르는 대신 **본문 로직만 덜어 내고 나머지를 남긴다.**

[중요] **사용자 결정 2026-10-03**: 비UE 프로젝트에만 적용 · 조각 분할(map→reduce, 호출 4배)
   대신 이 방식 — LLM 호출 수는 그대로다. 대가는 **함수 본문 안 로직을 못 본다**는 것.

[주의] **프롬프트 전용이다.** 사실 게이트(`verify.verify`)는 여전히 **원본 전체**와 대조한다 —
   요약본으로 대조하면 본문에서만 쓰이는 실제 식별자가 「유령」으로 거부된다(`#367` 과 같은 함정).

남기는 것: 모듈 수준 코드 전부(상수·import·주석) · 데코레이터 · `def`/`class` 시그니처 ·
독스트링 · 함수 본문 안의 **주석 줄**. 덜어 내는 것: 함수 본문의 나머지 줄 — 연속 구간마다
`...` 한 줄로 바꾼다. 클래스 본문은 메서드 단위로 같은 규칙을 따른다(클래스 속성은 남는다).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass

ELIDED = "..."


@dataclass
class Digest:
    text: str
    original_chars: int
    functions: int = 0         # 본문을 덜어 낸 함수·메서드 수
    elided_lines: int = 0      # 덜어 낸 줄 수

    @property
    def summary(self) -> str:
        return (f"요약본 {self.original_chars}→{len(self.text)}자 · "
                f"함수 본문 {self.functions}개 · {self.elided_lines}줄 생략")


def _docstring_end(node) -> int:
    """함수 본문 첫 문장이 독스트링이면 그 끝 줄(1-based), 아니면 0."""
    body = getattr(node, "body", None) or []
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None),
                                                               ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[0].end_lineno or 0
    return 0


def _elidable_lines(tree: ast.AST) -> tuple[set[int], int]:
    """덜어 낼 줄 번호(1-based)와 대상 함수 수. **가장 바깥 함수**만 센다 — 중첩 함수는
    바깥 함수 본문에 속해 함께 덜린다."""
    out: set[int] = set()
    count = 0

    def visit(node, inside_func: bool) -> None:
        nonlocal count
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not inside_func:
                body = child.body
                if not body:
                    continue
                start = body[0].lineno
                doc_end = _docstring_end(child)
                if doc_end:
                    start = doc_end + 1
                end = child.end_lineno or body[-1].end_lineno or start - 1
                if start <= end:
                    out.update(range(start, end + 1))
                    count += 1
                # 중첩 함수는 이미 범위 안이다 — 내려가지 않는다
            else:
                visit(child, inside_func)

    visit(tree, False)
    return out, count


def digest(text: str) -> Digest | None:
    """요약본을 만든다. 파싱이 안 되면 `None` — 호출자가 종전(앞에서 자르기)으로 돌아간다."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    elide, funcs = _elidable_lines(tree)
    lines = text.splitlines()
    kept: list[str] = []
    dropped = 0
    in_gap = False
    for no, line in enumerate(lines, 1):
        if no in elide and not line.lstrip().startswith("#"):
            if line.strip():
                dropped += 1
            if not in_gap:
                indent = line[:len(line) - len(line.lstrip())] or "    "
                kept.append(f"{indent}{ELIDED}")
                in_gap = True
            continue
        in_gap = False
        kept.append(line)
    return Digest(text="\n".join(kept) + ("\n" if text.endswith("\n") else ""),
                  original_chars=len(text), functions=funcs, elided_lines=dropped)
