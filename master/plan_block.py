"""Redmine 이슈 본문 안의 **플랜 영역** 읽기/쓰기 — `#826` T1.

플랜은 이슈 본문 안 태그 사이에 둔다 (사용자 결정 2026-10-31):

    <!-- ax:plan:begin v=2 -->
    | ID | 상태 | 목표 | 대상 | 단계 | 선행 | 검증 | 근거 |
    |---|---|---|---|---|---|---|---|
    | T1 | 대기 | ... | ... | 2·6 | — | ... | |
    <!-- ax:plan:end -->

「단계」 칸(v2, `#857`)은 태스크가 **조건부 단계 중 무엇을 하는지** 선언한다 — 7단계 번호를
`·` 로 잇고, 없으면 `—`. 판정은 `plan_steps` 몫이고 여기서는 1~7 숫자인지만 본다.
[중요] **v1 본문도 그대로 읽고 그대로 쓴다** — 단계를 선언한 태스크가 생길 때만 v2 로 올린다.

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

FORMAT_VERSION = 2
BEGIN_RE = re.compile(r"<!-- ax:plan:begin v=(\d+) -->")
END_TAG = "<!-- ax:plan:end -->"
COLUMNS_V1 = ("ID", "상태", "목표", "대상", "선행", "검증", "근거")
COLUMNS = ("ID", "상태", "목표", "대상", "단계", "선행", "검증", "근거")
COLUMNS_BY_VERSION = {1: COLUMNS_V1, 2: COLUMNS}
STEP_NUMBERS = range(1, 8)
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
    steps: list[int] = field(default_factory=list)     # v2 「단계」 — 맨 뒤라 위치 인자 호환


@dataclass
class Plan:
    version: int
    tasks: list[Task]

    def task(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)


def _region(body: str) -> tuple[int, int, int, int] | None:
    """(시작 태그 시작, 영역 안 시작, 영역 안 끝, 형식 버전). 태그가 없으면 None."""
    begins = list(BEGIN_RE.finditer(body))
    ends = [m.start() for m in re.finditer(re.escape(END_TAG), body)]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise PlanError(f"플랜 태그가 한 쌍이 아니다 — 시작 {len(begins)}개 · 끝 {len(ends)}개")
    begin = begins[0]
    if ends[0] < begin.end():
        raise PlanError("플랜 끝 태그가 시작 태그보다 앞에 있다")
    return begin.start(), begin.end(), ends[0], int(begin.group(1))


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


def _steps(text: str) -> list[int]:
    if text in ("", NO_DEPS):
        return []
    out = []
    for part in re.split(r"[·,]", text):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or int(part) not in STEP_NUMBERS:
            raise PlanError(f"단계는 1~7 숫자다: {text!r}")
        if int(part) not in out:
            out.append(int(part))
    return sorted(out)


def _check_version(version: int) -> tuple:
    if version not in COLUMNS_BY_VERSION:
        raise PlanError(f"모르는 플랜 형식 버전 v={version} "
                        f"(이 코드는 v{'·v'.join(map(str, COLUMNS_BY_VERSION))})")
    return COLUMNS_BY_VERSION[version]


def parse(body: str) -> Plan | None:
    """본문에서 플랜을 읽는다. 플랜 영역이 없으면 None, 형식이 어긋나면 `PlanError`."""
    region = _region(body or "")
    if region is None:
        return None
    _tag, start, end, version = region
    columns = _check_version(version)
    lines = [ln for ln in body[start:end].splitlines() if ln.strip()]
    if len(lines) < 2:
        raise PlanError("플랜 표에 머리줄과 구분줄이 없다")
    if tuple(_cells(lines[0])) != columns:
        raise PlanError(f"플랜 표 머리줄이 다르다: {_cells(lines[0])}")
    if not all(re.fullmatch(r":?-{3,}:?", c) for c in _cells(lines[1])):
        raise PlanError("플랜 표 구분줄이 아니다")
    tasks: list[Task] = []
    for ln in lines[2:]:
        c = _cells(ln)
        if len(c) != len(columns):
            raise PlanError(f"칸 수가 {len(c)}개다 (필요 {len(columns)}): {ln.strip()[:80]!r}")
        if version == 1:
            tid, state, goal, target, deps, check, evidence = c
            steps = ""
        else:
            tid, state, goal, target, steps, deps, check, evidence = c
        if not tid:
            raise PlanError(f"ID 가 비었다: {ln.strip()[:80]!r}")
        if state not in STATES:
            raise PlanError(f"{tid}: 모르는 상태 {state!r} (허용 {', '.join(STATES)})")
        if any(t.id == tid for t in tasks):
            raise PlanError(f"ID 가 겹친다: {tid}")
        tasks.append(Task(tid, state, goal, target, _deps(deps), check, evidence,
                          _steps(steps)))
    known = {t.id for t in tasks}
    for t in tasks:
        missing = [d for d in t.deps if d not in known]
        if missing:
            raise PlanError(f"{t.id}: 없는 선행 태스크 {', '.join(missing)}")
    return Plan(version, tasks)


def _needed_version(tasks: list[Task], current: int) -> int:
    """단계를 선언한 태스크가 있으면 v2 이상. 없으면 지금 버전을 지킨다(v1 본문 바이트 보존)."""
    return max(current, 2) if any(t.steps for t in tasks) else current


def render(tasks: list[Task], *, version: int = FORMAT_VERSION) -> str:
    """태그 사이에 들어갈 표(LF). 앞뒤 줄바꿈 포함."""
    columns = _check_version(version)
    rows = ["| " + " | ".join(columns) + " |",
            "|" + "---|" * len(columns)]
    for t in tasks:
        if t.state not in STATES:
            raise PlanError(f"{t.id}: 모르는 상태 {t.state!r}")
        bad = [s for s in t.steps if s not in STEP_NUMBERS]
        if bad:
            raise PlanError(f"{t.id}: 단계는 1~7 숫자다: {bad}")
        if version == 1 and t.steps:
            raise PlanError(f"{t.id}: v1 표에는 단계 칸이 없다")
        deps = "·".join(t.deps) if t.deps else NO_DEPS
        steps = "·".join(str(s) for s in sorted(set(t.steps))) if t.steps else NO_DEPS
        cells = ((t.id, t.state, t.goal, t.target, deps, t.check, t.evidence) if version == 1
                 else (t.id, t.state, t.goal, t.target, steps, deps, t.check, t.evidence))
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
    tag, start, end, version = region
    _check_version(version)
    out_version = _needed_version(tasks, version)
    inner = render(tasks, version=out_version)
    if "\r\n" in body:
        inner = inner.replace("\n", "\r\n")
    begin = f"<!-- ax:plan:begin v={out_version} -->" if out_version != version else body[tag:start]
    return body[:tag] + begin + inner + body[end:]


def append(body: str, tasks: list[Task], *, heading: str = "## 플랜") -> str:
    """플랜 영역이 없는 본문 끝에 제목과 영역을 붙인다. 이미 있으면 `PlanError`."""
    if _region(body or "") is not None:
        raise PlanError("플랜 영역이 이미 있다 — 갱신은 replace")
    nl = "\r\n" if "\r\n" in (body or "") else "\n"
    block = (f"{heading}\n\n<!-- ax:plan:begin v={FORMAT_VERSION} -->"
             + render(tasks) + END_TAG + "\n").replace("\n", nl)
    base = (body or "").rstrip("\r\n")
    return (base + nl + nl if base else "") + block
