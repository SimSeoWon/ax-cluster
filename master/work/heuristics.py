"""골조 휴리스틱 — **대화형으로 모은 사람의 판단** (소 1.1.6, 사용자 지시 2026-08-11).

> *"사용자가 명령을 내렸고 컴퓨터 앞에 있으니 분산 작업에 대한 골조를 생성할 때 애매한
> 것이나 더 좋은 구조등에 대한 내용을 대화형으로 주고 받으면서 휴리스틱을 수집해"*

## [중요] 골조도 전자동이 아니다 — 온톨로지와 같은 원칙

마일스톤 2 의 목표 ①이 이미 못박아 뒀다: 온톨로지는 *"사용자의 수동 명령과 대화형으로
휴리스틱이 포함된"* 것이고 **자동 승급은 영구 비활성**이다. 골조도 같다 — 오히려 더하다.
골조는 **모든 병렬 조각의 계약**이라, 애매한 선택을 모델이 조용히 하면 그 선택이 N개 조각에
박힌다. 그리고 그때는 이미 늦다.

    옛 흐름   요청 → 골조 → (모델이 알아서 정함) → 파견
    새 흐름   요청 → 골조 + **질문** → [중요] 사람이 답함 → 휴리스틱 적립 → 파견
                                              ↘ 다음 골조 프롬프트에 실린다

## [중요] 모델의 질문은 휴리스틱이 아니다 — 사람의 답이 휴리스틱이다

자동 승급을 껐던 이유와 같다. 모델이 *"이렇게 하는 게 좋겠습니다"* 라고 한 것을 그대로
적립하면, 다음 골조는 **자기가 한 말을 근거로** 같은 선택을 반복한다 — 근거 없는 확신이
쌓인다. 적립되는 것은 **사람이 답한 것뿐**이다.

## 두 개의 되먹임 고리 — 짝이다

    소 2.3.4  실패 카탈로그   층3 빌드 실패 → 다음 프롬프트   **기계가 모은다**
    소 1.1.6  휴리스틱        사람의 판단 → 다음 프롬프트     [중요] **사람이 답한 것만**

원전은 앞쪽만 있었다(`.claude/recipes/_distribute_failures.md`). 뒤쪽이 없으면 *"컴파일은
되지만 구조가 나쁜"* 선택은 영원히 교정되지 않는다 — 빌드가 통과하니 카탈로그에 안 남는다.

## [중요] 범위가 없으면 오염이다 (사용자 지적 2026-08-11)

> *"저 질문들은 답변하면 모든 분산 작업에 적용되는거야?"*

처음 구현이 그랬다 — **답을 전부 한 파일에 쌓고 모든 골조 프롬프트에 실었다.** 그러면
*"이 스냅샷은 컴포넌트로 한다"* 가 **관계없는 다음 작업에도** 실린다. 명백히 틀렸다.

    project      "액터 수명에 묶이는 상태는 컴포넌트로 둔다"   → 앞으로 계속 적용
    domain:<D>   "MissionRuntime 에서는 …"                   → 그 도메인 작업에만
    once         "이번 스냅샷은 컴포넌트로"                    → [중요] **적립하지 않는다**

우리 온톨로지가 이미 **도메인별 규범**과 전역을 갈라 뒀고, 원전도 작업유형 템플릿(`task.yaml`)과
전역 실패 카탈로그를 갈라 뒀다. 그 구분을 여기서 뭉개면 프롬프트가 **남의 작업의 결정**으로
채워진다 — grounding 이 아니라 노이즈다.

[중요] **범위도 사람이 정한다.** 모델이 *"이건 전역 규약입니다"* 라고 판단하게 두면, 적립 자체를
사람에게 맡긴 이유가 사라진다.

## 저장 형태 — 사람이 읽는 마크다운

YAML 도 JSON 도 아니다. 이건 **사람이 답한 문장**이고, 사람이 다시 읽고 고칠 것이다.
`ontology/domains/**` 의 `protected_reason` 이 문장인 것과 같은 이유다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

FILE_NAME = "skeleton-heuristics.md"
BUDGET = 3000           # 프롬프트에 실을 상한 (선언부·규범을 밀어내면 안 된다)
MAX_QUESTIONS = 6       # [중요] 사람에게 한 번에 물을 수 있는 양에는 한계가 있다

# [중요] **마지막** 블록을 잡는다. 지시가 *"파일 다음에"* 라고 못박으므로 질문은 뒤에 온다 —
# 모델이 본문 중간에 같은 낱말을 흘려도(실측: 한 번 그랬다) 앞의 파일들을 잃지 않는다.
# 줄 머리로 앵커해서 코드 안의 문자열과도 안 헷갈린다.
_Q_BLOCK = re.compile(r"^===\s*QUESTIONS\s*===(.*?)(?:^===\s*END QUESTIONS\s*===|\Z)",
                      re.DOTALL | re.IGNORECASE | re.MULTILINE)


def _last_q_start(raw: str) -> int:
    """마지막 `=== QUESTIONS ===` 의 시작 위치. 없으면 -1."""
    last = -1
    for m in re.finditer(r"^===\s*QUESTIONS\s*===", raw or "", re.MULTILINE | re.IGNORECASE):
        last = m.start()
    return last
_ENTRY = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class Question:
    """골조가 애매하다고 말한 지점. [중요] **이것 자체는 휴리스틱이 아니다.**"""

    topic: str
    text: str = ""
    options: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = f"{self.topic}"
        if self.options:
            s += " — " + " / ".join(self.options[:3])
        return s


SCOPE_PROJECT = "project"
SCOPE_ONCE = "once"          # [중요] 적립하지 않는다 — 이번 골조에만 쓰고 버린다
DOMAIN_PREFIX = "domain:"


@dataclass
class Heuristic:
    """사람이 답한 것. **이것만 적립된다.**

    [중요] `scope` 가 핵심이다 — 없으면 이번 작업의 결정이 다음 작업을 오염시킨다(사용자 지적).
    """

    topic: str
    decision: str
    why: str = ""
    at: str = ""                        # 트윈 기준 커밋 (언제의 판단인지)
    scope: str = SCOPE_PROJECT          # project · domain:<D> · once

    @property
    def domain(self) -> str:
        return self.scope[len(DOMAIN_PREFIX):] if self.scope.startswith(DOMAIN_PREFIX) else ""

    @property
    def storable(self) -> bool:
        """[중요] `once` 는 적립하지 않는다 — 이번 골조에만 쓰고 버린다."""
        return self.scope != SCOPE_ONCE

    def applies_to(self, domains) -> bool:
        """이 작업에 실어야 하나."""
        if self.scope == SCOPE_PROJECT:
            return True
        d = self.domain
        return bool(d) and d in set(domains or ())

    def render(self) -> str:
        out = [f"## {self.topic}", "", f"**범위**: {self.scope}", f"**결정**: {self.decision}"]
        if self.why:
            out.append(f"**이유**: {self.why}")
        if self.at:
            out.append(f"_기준 {self.at[:8]}_")
        return "\n".join(out) + "\n"


def path_for(paths: ProjectPaths):
    return paths.root / FILE_NAME


def parse_questions(raw: str, *, limit: int = MAX_QUESTIONS) -> list:
    """골조 응답에서 `=== QUESTIONS ===` 블록을 읽는다. **없으면 빈 목록.**

    형식은 느슨하게 받는다 — 모델이 형식을 조금 어겨도 질문을 잃는 것보다 낫다. 다만
    **블록 자체가 없으면 지어내지 않는다.**
    """
    i = _last_q_start(raw or "")
    if i < 0:
        return []
    m = _Q_BLOCK.search(raw, i)
    if not m:
        return []
    out: list = []
    for line in m.group(1).splitlines():
        t = line.strip().lstrip("-*0123456789. ").strip()
        if not t or t.startswith("==="):
            continue
        opts: list = []
        topic = t
        if "?" in t:
            head, _, tail = t.partition("?")
            topic = head.strip() + "?"
            # `A / B` 또는 `A vs B` 형태의 선택지를 살린다
            opts = [x.strip() for x in re.split(r"\s+(?:vs|/|또는)\s+", tail) if x.strip()]
        out.append(Question(topic=topic, text=t, options=opts))
        if len(out) >= limit:
            break
    return out


def load(paths: ProjectPaths) -> list:
    """적립된 휴리스틱. **없으면 빈 목록** — 파일이 없는 것은 정상이다."""
    p = path_for(paths)
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8")
    out: list = []
    marks = list(_ENTRY.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        dec = why = at = scope = ""
        for line in body.splitlines():
            t = line.strip()
            if t.startswith("**결정**:"):
                dec = t.split(":", 1)[1].strip()
            elif t.startswith("**이유**:"):
                why = t.split(":", 1)[1].strip()
            elif t.startswith("_기준 "):
                at = t.strip("_ ").replace("기준 ", "")
            elif t.startswith("**범위**:"):
                scope = t.split(":", 1)[1].strip()
        if dec:
            out.append(Heuristic(topic=m.group(1).strip(), decision=dec, why=why, at=at,
                                 scope=scope or SCOPE_PROJECT))
    return out


def add(paths: ProjectPaths, h: Heuristic) -> str:
    """휴리스틱 하나를 적립한다. [중요] **덮지 않고 이어 쓴다.**

    같은 주제가 이미 있으면 **새 항목으로 덧붙인다** — 판단이 바뀐 것도 기록이고, 옛 결정을
    조용히 지우면 *왜 바뀌었는지*가 사라진다(`supersedes` 를 사람이 문장으로 쓰면 된다).
    """
    if not (h.topic or "").strip() or not (h.decision or "").strip():
        raise ValueError("주제와 결정이 있어야 적립한다 — 빈 휴리스틱은 다음 골조를 흐린다")
    if not h.storable:
        # [중요] `once` 는 이번 골조에만 쓰고 버린다 — 적립하면 남의 작업을 오염시킨다
        raise ValueError("scope=once 는 적립하지 않는다 — 이번 골조에만 쓰고 버린다")
    p = path_for(paths)
    head = ("# 골조 휴리스틱\n\n"
            "[중요] **사람이 답한 것만 여기 쌓인다** — 모델이 제안한 것은 적립되지 않는다"
            "(자동 승급을 껐던 것과 같은 이유). 골조 생성 프롬프트에 실린다.\n\n"
            "손으로 고쳐도 된다. 형식: `## 주제` + `**결정**:` + `**이유**:`\n\n---\n\n")
    if not p.is_file():
        p.write_text(head + h.render(), encoding="utf-8")
    else:
        with p.open("a", encoding="utf-8") as f:
            f.write("\n" + h.render())
    return str(p)


def render(items: list, *, budget: int = BUDGET, domains=None, extra=None) -> str:
    """프롬프트에 실을 블록. **최근 것이 우선**이고 예산에서 잘린다.

    [중요] `domains` 로 **거른다** — `project` 범위는 늘 싣고, `domain:<D>` 는 이 작업이 그
    도메인일 때만 싣는다. 안 거르면 남의 작업의 결정이 프롬프트를 채운다(사용자 지적).
    `extra` 는 이번 작업 한정(`once`) 답변 — 적립되지 않지만 이번 골조에는 실린다.
    """
    items = [h for h in (items or []) if h.applies_to(domains)] + list(extra or [])
    if not items:
        return ""
    out = ["=== HEURISTICS — decisions this project's owner already made ===",
           "[중요] These are human decisions, not suggestions. Follow them unless the task "
           "explicitly says otherwise.", ""]
    used = 0
    kept = 0
    for h in reversed(items):                 # 최근 것부터
        block = h.render()
        if used + len(block) > budget:
            break
        out.append(block)
        used += len(block)
        kept += 1
    if kept < len(items):
        # [중요] 잘랐으면 잘랐다고 적는다 — 조용히 빼면 모델이 "그런 결정은 없다" 로 읽는다
        out.append(f"[중요] {len(items) - kept} older decision(s) omitted for budget — "
                   f"they still stand.")
    out.append("=== END HEURISTICS ===")
    return "\n".join(out)
