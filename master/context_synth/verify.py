"""컨텍스트 문서 사실 검증 — **결정적 게이트** (LLM 판단을 쓰지 않는다).

[중요] **왜 있나 — 실측된 실패다.** 우리 35B 로 `WNDMontageManager` 문서를 만들었더니
**주석 처리된 구조체·함수를 살아 있는 기능처럼 요약**했다. 특이한 것은 같은 응답의
「개선 필요 사항」 절에서는 *"주석으로 처리되어 살아 있는 기능이 아닙니다"* 라고 정확히
짚었다는 점이다 — **모델이 사실을 모르는 게 아니라 절마다 다르게 쓴다.**

그러면 검증을 모델에게 맡길 이유가 없다. 설계 규칙이 이미 답을 갖고 있다:

> **결정적 게이트(테스트·타입체커·린터)가 LLM 판단보다 우선한다.**

그래서 이 모듈은 **소스를 직접 읽어** 판정한다:

1. C++ 주석을 벗겨 **살아 있는 본문**을 만든다 (문자열 리터럴을 주석으로 오인하지 않는다)
2. **주석 안에만 등장하는 식별자** 집합을 만든다
3. 문서가 그중 하나를 언급하면 **위반** — 없는 기능을 있다고 안내하는 문서다

엔진 클래스(`AActor`·`UAnimMontage`)에 오탐이 나지 않는 이유: 그것들은 **소스 본문에
아예 없거나 살아 있는 코드에 있다.** "주석에만 있는 것" 이라는 조건이 그 둘을 자동으로
가른다 — 클래스 그래프에 없다는 이유로 거부하면 엔진 클래스가 전부 걸린다.

[중요] **중 1.3 에서 재사용한다.** 인수인계 문서가 `methods` 테이블의 존재 이유를 *"온톨로지
추출의 오탐 교차검증"* 이라고 적어 뒀다 — 온톨로지 합성도 같은 환각 위험을 갖는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 3자 이상만 본다. 짧은 토큰(`id`·`b`)은 우연 일치가 많아 게이트를 시끄럽게 만든다.
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")

# 검사에서 뺄 것 — 언어 키워드·UE 매크로처럼 어디에나 있는 토큰.
_NOISE = {
    "class", "struct", "public", "private", "protected", "virtual", "override", "const",
    "static", "inline", "template", "typename", "namespace", "return", "void", "bool",
    "int", "float", "double", "char", "enum", "union", "using", "typedef", "friend",
    "explicit", "operator", "sizeof", "nullptr", "true", "false", "this", "new", "delete",
    "include", "pragma", "once", "define", "ifdef", "ifndef", "endif", "else", "elif",
    "UCLASS", "USTRUCT", "UENUM", "UINTERFACE", "UPROPERTY", "UFUNCTION", "UMETA",
    "GENERATED_BODY", "GENERATED_USTRUCT_BODY", "FORCEINLINE", "UPARAM", "UDELEGATE",
    "TODO", "FIXME", "NOTE", "http", "https", "www",
}


def strip_comments(src: str) -> tuple[str, str]:
    """C++ 소스 → (살아 있는 본문, 주석만 모은 본문).

    문자열·문자 리터럴 안의 `//`·`/*` 는 주석으로 보지 않는다. 이걸 틀리면 **살아 있는
    코드가 주석으로 분류돼 오탐 위반**이 난다 — 게이트가 정상 문서를 거부하는 쪽이
    통과시키는 쪽보다 더 나쁘다(작업이 멈춘다).
    """
    live: list[str] = []
    dead: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            quote = c
            live.append(c)
            i += 1
            while i < n:
                if src[i] == "\\":
                    live.append(src[i:i + 2])
                    i += 2
                    continue
                live.append(src[i])
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n:
            if src[i + 1] == "/":
                j = src.find("\n", i)
                j = n if j == -1 else j
                dead.append(src[i + 2:j])
                live.append("\n")
                i = j
                continue
            if src[i + 1] == "*":
                j = src.find("*/", i + 2)
                j = n if j == -1 else j + 2
                dead.append(src[i + 2:max(i + 2, j - 2)])
                live.append("\n")
                i = j
                continue
        live.append(c)
        i += 1
    return "".join(live), "\n".join(dead)


def identifiers(text: str) -> set[str]:
    return {m for m in _IDENT_RE.findall(text or "") if m not in _NOISE}


def comment_only(src: str) -> set[str]:
    """주석 안에만 등장하는 식별자. **이것이 게이트의 판정 근거다.**"""
    live, dead = strip_comments(src)
    return identifiers(dead) - identifiers(live)


# 문서에서 사실 주장이 실리는 절. 「개선 필요 사항」은 **제외한다** — 거기서 "이건 주석
# 처리됐다" 고 말하는 것은 정확한 서술이므로 위반이 아니다.
_SUMMARY_RE = re.compile(r"^##\s*요약\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
_RELATED_RE = re.compile(r"^related_classes:\s*$(.*?)(?=^\w|\n---)", re.MULTILINE | re.DOTALL)


def claimed(doc: str) -> set[str]:
    """문서가 **사실로 주장한** 식별자 — 요약 본문 + `related_classes` 키."""
    out: set[str] = set()
    m = _SUMMARY_RE.search(doc or "")
    if m:
        out |= identifiers(m.group(1))
    m = _RELATED_RE.search(doc or "")
    if m:
        for line in m.group(1).splitlines():
            key = re.match(r"\s*-\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
            if key:
                out.add(key.group(1))
    return out


@dataclass
class Report:
    """검증 결과. **`ok` 가 아니면 저장하지 않는다** (σ.7-B 와 같은 처리)."""

    ok: bool = True
    ghosts: list[str] = field(default_factory=list)     # 주석에만 있는데 주장한 것
    declared: list[str] = field(default_factory=list)   # 실측 선언 클래스
    mentioned_declared: bool = True                     # 실측 클래스를 하나라도 언급했나

    @property
    def reason(self) -> str:
        parts = []
        if self.ghosts:
            parts.append("[중요] 주석에만 있는 식별자를 살아 있는 것처럼 서술: "
                         + ", ".join(self.ghosts[:6]))
        if not self.mentioned_declared:
            parts.append("[중요] 실측 선언 클래스를 하나도 언급하지 않았다 (다른 파일을 서술?): "
                         + ", ".join(self.declared[:6]))
        return " · ".join(parts)


def verify(doc: str, *, sources: dict[str, str], declared: list[str] | None = None) -> Report:
    """문서 vs 소스 실측. `sources` 는 `{경로: 원문}`, `declared` 는 tree-sitter 실측 클래스.

    `declared` 를 주면 "실측 클래스를 하나도 안 쓴 문서" 도 잡는다 — 그룹을 잘못 묶었거나
    모델이 다른 파일을 서술한 경우다. `declared` 가 비면 그 검사는 건너뛴다(파서가 없거나
    클래스가 없는 파일은 정상이다).
    """
    ghost_pool: set[str] = set()
    for src in sources.values():
        ghost_pool |= comment_only(src)
    said = claimed(doc)
    ghosts = sorted(said & ghost_pool)

    mentioned = True
    if declared:
        mentioned = bool(said & set(declared))

    return Report(ok=(not ghosts and mentioned), ghosts=ghosts,
                  declared=list(declared or []), mentioned_declared=mentioned)
