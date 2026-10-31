"""Redmine 이슈 본문 안의 **플랜 영역** 읽기/쓰기 — `#826` T1.

플랜은 이슈 본문 안 태그 사이에 둔다 (사용자 결정 2026-10-31):

    <!-- ax:plan:begin v=1 -->
    | ID | 상태 | 목표 | 대상 | 선행 | 검증 | 근거 |
    |---|---|---|---|---|---|---|
    | T1 | 대기 | ... | ... | — | ... | |
    <!-- ax:plan:end -->

[중요] **이 모듈은 태그 사이만 다룬다.** 영역 밖 본문은 바이트 그대로 돌려준다 — 사람이 고친
스펙·제목을 플랜 갱신이 덮으면 안 된다. Redmine 이 본문을 CRLF 로 저장하므로 영역 안에 새로
쓰는 줄도 본문의 줄바꿈 방식을 따른다.

[중요] **형식이 어긋나면 고쳐 읽지 않고 거절한다** (`PlanError`). 태그가 둘이거나, 칸 수가
다르거나, 모르는 상태 값이면 추측으로 이어 가지 않는다 — 사람이 본문을 직접 고친 흔적일 수
있고, 잘못 읽은 플랜으로 다음 태스크를 고르는 것이 더 비싸다.

상태 전이 규칙(근거 없는 완료 거절 등)은 여기 없다 — T2 의 몫이다. 이 모듈은 형식만 판정한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FORMAT_VERSION = 1
BEGIN_RE = re.compile(r"<!-- ax:plan:begin v=(\d+) -->")
END_TAG = "<!-- ax:plan:end -->"
COLUMNS = ("ID", "상태", "목표", "대상", "선행", "검증", "근거")
STATES = ("대기", "작업중", "완료", "차단", "해당없음")
NO_DEPS = "—"


class PlanError(ValueError):
    """플랜 영역의 형식이 어긋났다 — 사유 문장을 담는다."""


@dataclass
class Task:
    id: str
    state: str
    goal: str
    target: str = ""
    deps: list[str] = field(default_factory=list)
    check: str = ""
    evidence: str = ""


@dataclass
class Plan:
    version: int
    tasks: list[Task]

    def task(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)


def _region(body: str) -> tuple[int, int, int] | None:
    """(영역 안 시작, 영역 안 끝, 형식 버전). 태그가 없으면 None."""
    begins = list(BEGIN_RE.finditer(body))
    ends = [m.start() for m in re.finditer(re.escape(END_TAG), body)]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise PlanError(f"플랜 태그가 한 쌍이 아니다 — 시작 {len(begins)}개 · 끝 {len(ends)}개")
    begin = begins[0]
    if ends[0] < begin.end():
        raise PlanError("플랜 끝 태그가 시작 태그보다 앞에 있다")
    return begin.end(), ends[0], int(begin.group(1))


def _cells(line: str) -> list[str]:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        raise PlanError(f"표 줄이 아니다: {line.strip()[:80]!r}")
    parts = re.split(r"(?<!\\)\|", s[1:-1])
    return [p.strip().replace("\\|", "|") for p in parts]


def _cell(text: str) -> str:
    if "\n" in text or "\r" in text:
        raise PlanError(f"칸에 줄바꿈을 넣을 수 없다: {text[:80]!r}")
    return text.replace("|", "\\|")


def _deps(text: str) -> list[str]:
    if text in ("", NO_DEPS):
        return []
    return [d.strip() for d in re.split(r"[·,]", text) if d.strip()]


def parse(body: str) -> Plan | None:
    """본문에서 플랜을 읽는다. 플랜 영역이 없으면 None, 형식이 어긋나면 `PlanError`."""
    region = _region(body or "")
    if region is None:
        return None
    start, end, version = region
    if version != FORMAT_VERSION:
        raise PlanError(f"모르는 플랜 형식 버전 v={version} (이 코드는 v={FORMAT_VERSION})")
    lines = [ln for ln in body[start:end].splitlines() if ln.strip()]
    if len(lines) < 2:
        raise PlanError("플랜 표에 머리줄과 구분줄이 없다")
    if tuple(_cells(lines[0])) != COLUMNS:
        raise PlanError(f"플랜 표 머리줄이 다르다: {_cells(lines[0])}")
    if not all(re.fullmatch(r":?-{3,}:?", c) for c in _cells(lines[1])):
        raise PlanError("플랜 표 구분줄이 아니다")
    tasks: list[Task] = []
    for ln in lines[2:]:
        c = _cells(ln)
        if len(c) != len(COLUMNS):
            raise PlanError(f"칸 수가 {len(c)}개다 (필요 {len(COLUMNS)}): {ln.strip()[:80]!r}")
        tid, state, goal, target, deps, check, evidence = c
        if not tid:
            raise PlanError(f"ID 가 비었다: {ln.strip()[:80]!r}")
        if state not in STATES:
            raise PlanError(f"{tid}: 모르는 상태 {state!r} (허용 {', '.join(STATES)})")
        if any(t.id == tid for t in tasks):
            raise PlanError(f"ID 가 겹친다: {tid}")
        tasks.append(Task(tid, state, goal, target, _deps(deps), check, evidence))
    known = {t.id for t in tasks}
    for t in tasks:
        missing = [d for d in t.deps if d not in known]
        if missing:
            raise PlanError(f"{t.id}: 없는 선행 태스크 {', '.join(missing)}")
    return Plan(version, tasks)


def render(tasks: list[Task]) -> str:
    """태그 사이에 들어갈 표(LF). 앞뒤 줄바꿈 포함."""
    rows = ["| " + " | ".join(COLUMNS) + " |",
            "|" + "---|" * len(COLUMNS)]
    for t in tasks:
        if t.state not in STATES:
            raise PlanError(f"{t.id}: 모르는 상태 {t.state!r}")
        cells = (t.id, t.state, t.goal, t.target,
                 "·".join(t.deps) if t.deps else NO_DEPS, t.check, t.evidence)
        rows.append("|" + "".join(f" {_cell(x)} |" if x else " |" for x in cells))
    return "\n" + "\n".join(rows) + "\n"


def replace(body: str, tasks: list[Task]) -> str:
    """플랜 영역 안만 `tasks` 로 바꾼 본문. 영역 밖은 바이트 그대로다.

    영역이 없으면 `PlanError` — 처음 만드는 것은 `append` 다. 둘을 나눈 이유: 갱신하려던
    본문에 영역이 없는 것은 대개 엉뚱한 일감을 집은 것이라 조용히 새로 만들면 안 된다.
    """
    region = _region(body or "")
    if region is None:
        raise PlanError("플랜 영역이 없다 — 새로 만들려면 append")
    start, end, version = region
    if version != FORMAT_VERSION:
        raise PlanError(f"모르는 플랜 형식 버전 v={version} (이 코드는 v={FORMAT_VERSION})")
    inner = render(tasks)
    if "\r\n" in body:
        inner = inner.replace("\n", "\r\n")
    return body[:start] + inner + body[end:]


def append(body: str, tasks: list[Task], *, heading: str = "## 플랜") -> str:
    """플랜 영역이 없는 본문 끝에 제목과 영역을 붙인다. 이미 있으면 `PlanError`."""
    if _region(body or "") is not None:
        raise PlanError("플랜 영역이 이미 있다 — 갱신은 replace")
    nl = "\r\n" if "\r\n" in (body or "") else "\n"
    block = (f"{heading}\n\n<!-- ax:plan:begin v={FORMAT_VERSION} -->"
             + render(tasks) + END_TAG + "\n").replace("\n", nl)
    base = (body or "").rstrip("\r\n")
    return (base + nl + nl if base else "") + block
