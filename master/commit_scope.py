"""커밋 제목의 **일감·태스크 범위** 읽기 — `#946` T1. 순수 함수, LLM 0, 표준 라이브러리만.

규약(사용자 결정 2026-11-14, `docs/orchestrator-rules.md` §1.9):

    종류(#N T#): 제목            feat(#946 T1): 파서 추가
    종류(#N T#,T#): 제목         fix(#946 T1,T2): …   (`T1, T2` · `T1 T2` 도 받는다)
    종류(#N T#, #M T#): 제목     fix(#861 T2, #857 T7): …   (일감 여럿)

옛 꼴 `종류: 제목 (#368)` — 제목 끝 괄호에 일감 번호 **하나만** 있는 것 — 은 일감만 풀고
태스크는 비운다(`form="legacy"`). 종류 접두가 없거나 꼴이 다르면 아무것도 돌려주지 않는다.

[주의] **게이트가 아니다** — 규약을 어긴 커밋을 막지 않는다(사용자 결정: 규약 기록 + 리뷰 로그만).
이 모듈은 읽기만 하고, 못 읽으면 빈 목록이다.
[중요] `SCOPE_RE` 는 `plan_metrics.WORK_SCOPE_RE` 와 **같은 객체**다 — 작업 커밋 판정과 리뷰
컨텍스트가 서로 다른 정규식으로 갈라지지 않게 여기 하나만 둔다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 제목 맨 앞 `종류(…)` — 괄호 안이 범위 칸이다. 종류는 소문자·하이픈만(`FEAT(…)` 은 아니다).
SCOPE_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*\(([^)]*)\)")
# 옛 꼴: `종류[(범위)][!]: 제목 (#N)` — 끝 괄호에 일감 하나만.
TYPE_PREFIX_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*(?:\([^)]*\))?!?:\s")
LEGACY_TAIL_RE = re.compile(r"\(#(\d+)\)\s*$")
ISSUE_RE = re.compile(r"#(\d+)(?!\d)")
TASK_RE = re.compile(r"(?<![A-Za-z0-9])T(\d+)(?![A-Za-z0-9])")

FORM_SCOPE = "scope"
FORM_LEGACY = "legacy"


@dataclass(frozen=True)
class Scope:
    issue_id: int
    tasks: tuple[str, ...] = ()
    form: str = FORM_SCOPE          # "scope" | "legacy"


def subject_of(message: str) -> str:
    """전체 커밋 메시지에서 제목 줄(첫 비지 않은 줄, 앞뒤 공백 제거)."""
    for line in (message or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _scope_items(inner: str) -> list[Scope]:
    """범위 칸 안의 `#N T# …` 묶음 — 일감 번호 사이 구간의 태스크가 그 일감 것이다."""
    marks = list(ISSUE_RE.finditer(inner))
    merged: dict[int, list[str]] = {}
    for i, m in enumerate(marks):
        seg = inner[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(inner)]
        tasks = merged.setdefault(int(m.group(1)), [])
        for t in TASK_RE.finditer(seg):
            tid = f"T{int(t.group(1))}"
            if tid not in tasks:
                tasks.append(tid)
    return [Scope(n, tuple(ts), FORM_SCOPE) for n, ts in merged.items()]


def parse(subject: str) -> list[Scope]:
    """제목 한 줄 → 일감별 범위 목록(등장 순, 같은 일감은 태스크를 합친다). 못 읽으면 []."""
    s = (subject or "").strip()
    m = SCOPE_RE.match(s)
    if m:
        items = _scope_items(m.group(1))
        if items:
            return items
    # 범위 칸이 없거나 일감 번호가 없으면(`feat(webui): …`) 옛 꼴 끝 괄호를 본다.
    if TYPE_PREFIX_RE.match(s):
        t = LEGACY_TAIL_RE.search(s)
        if t:
            return [Scope(int(t.group(1)), (), FORM_LEGACY)]
    return []


def parse_message(message: str) -> list[Scope]:
    """전체 메시지의 제목 줄을 `parse` 한다 — 본문은 보지 않는다."""
    return parse(subject_of(message))
