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

**v3** (`#963` T1) — 시작 표지에 플랜 전체 속성을 싣고, 태스크 표 아래에 **개발 완료 체크리스트** 표를 둔다:

    <!-- ax:plan:begin v=3 autonomy=0.5 -->
    | ID | 상태 | 목표 | 대상 | 단계 | 선행 | 검증 | 근거 |
    |---|---|---|---|---|---|---|---|
    | T1 | 대기 | ... | ... | — | — | ... | |

    | ID | 상태 | 항목 | 근거 |
    |---|---|---|---|
    | C1 | 미확인 | 제안 없는 plan_set 거절 | |
    <!-- ax:plan:end -->

- `autonomy` 는 0~1(사용자 결정 2026-11-15: 기본 0.5 · 값↔세밀도 대응은 `#948`). 표지에 없으면 0.5 로 읽는다.
- 체크리스트 ID 는 `C<숫자>`, 상태는 미확인·충족·제외. 태스크 ID 는 `C<숫자>` 꼴을 쓸 수 없다(전이 도구가
  같은 ID 공간을 쓰기 때문).
- [중요] **v1·v2 본문은 바이트 그대로** — 체크리스트나 자율성 값을 처음 실을 때만 v3 으로 올린다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FORMAT_VERSION = 2                     # 새 플랜의 기본 — 체크리스트·자율성이 실리면 v3
BEGIN_RE = re.compile(r"<!-- ax:plan:begin v=(\d+)((?: [a-z_]+=[^\s>]+)*) -->")
END_TAG = "<!-- ax:plan:end -->"
COLUMNS_V1 = ("ID", "상태", "목표", "대상", "선행", "검증", "근거")
COLUMNS = ("ID", "상태", "목표", "대상", "단계", "선행", "검증", "근거")
COLUMNS_BY_VERSION = {1: COLUMNS_V1, 2: COLUMNS, 3: COLUMNS}
CHECK_COLUMNS = ("ID", "상태", "항목", "근거")
CHECK_STATES = ("미확인", "충족", "제외")
CHECK_ID = re.compile(r"^C\d+$")
DEFAULT_AUTONOMY = 0.5
ATTRS = ("autonomy",)
STEP_NUMBERS = range(1, 8)
STATES = ("대기", "작업중", "완료", "차단", "해당없음")
NO_DEPS = "—"


class PlanError(ValueError):
    """플랜 영역의 형식이 어긋났다 — 사유 문장을 담는다."""


@dataclass
class IssuePlanTask:
    id: str
    state: str
    goal: str
    target: str = ""
    deps: list[str] = field(default_factory=list)
    check: str = ""
    evidence: str = ""
    steps: list[int] = field(default_factory=list)     # v2 「단계」 — 맨 뒤라 위치 인자 호환


@dataclass
class IssuePlanCheck:
    """개발 완료 체크리스트 한 줄 (v3)."""
    id: str
    state: str
    item: str
    evidence: str = ""


@dataclass
class IssuePlan:
    version: int
    tasks: list[IssuePlanTask]
    checklist: list[IssuePlanCheck] = field(default_factory=list)
    autonomy_raw: float | None = None          # 표지에 적힌 값 — 없으면 None

    @property
    def autonomy(self) -> float:
        return DEFAULT_AUTONOMY if self.autonomy_raw is None else self.autonomy_raw

    def task(self, task_id: str) -> IssuePlanTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def check(self, check_id: str) -> IssuePlanCheck | None:
        return next((c for c in self.checklist if c.id == check_id), None)


def autonomy_value(raw) -> float:
    """0~1 실수로 읽는다. 아니면 `PlanError`."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise PlanError(f"autonomy 는 0~1 숫자다: {raw!r}") from None
    if not (0.0 <= v <= 1.0) or v != v:
        raise PlanError(f"autonomy 는 0~1 숫자다: {raw!r}")
    return v


def _attrs(text: str, version: int) -> dict:
    out = {}
    for kv in (text or "").split():
        k, _, v = kv.partition("=")
        if k not in ATTRS:
            raise PlanError(f"모르는 플랜 표지 속성 {k!r} (허용 {', '.join(ATTRS)})")
        out[k] = v
    if out and version < 3:
        raise PlanError(f"표지 속성은 v3 부터다 — v={version}")
    return out


def _region(body: str) -> tuple[int, int, int, int] | None:
    """(시작 태그 시작, 영역 안 시작, 영역 안 끝, 형식 버전). 태그가 없으면 None. 속성은 `_attrs`."""
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


def parse(body: str) -> IssuePlan | None:
    """본문에서 플랜을 읽는다. 플랜 영역이 없으면 None, 형식이 어긋나면 `PlanError`."""
    region = _region(body or "")
    if region is None:
        return None
    tag, start, end, version = region
    columns = _check_version(version)
    attrs = _attrs(BEGIN_RE.match(body, tag).group(2), version)
    lines = [ln for ln in body[start:end].splitlines() if ln.strip()]
    check_lines: list[str] = []
    if version >= 3:
        head = next((i for i, ln in enumerate(lines) if i > 0 and ln.strip().startswith("|")
                     and tuple(_cells(ln)) == CHECK_COLUMNS), None)
        if head is not None:
            lines, check_lines = lines[:head], lines[head:]
    if len(lines) < 2:
        raise PlanError("플랜 표에 머리줄과 구분줄이 없다")
    if tuple(_cells(lines[0])) != columns:
        raise PlanError(f"플랜 표 머리줄이 다르다: {_cells(lines[0])}")
    if not all(re.fullmatch(r":?-{3,}:?", c) for c in _cells(lines[1])):
        raise PlanError("플랜 표 구분줄이 아니다")
    tasks: list[IssuePlanTask] = []
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
        if CHECK_ID.match(tid):
            raise PlanError(f"{tid}: C<숫자> 는 체크리스트 ID 다 — 태스크 ID 로 쓸 수 없다")
        tasks.append(IssuePlanTask(tid, state, goal, target, _deps(deps), check, evidence,
                          _steps(steps)))
    known = {t.id for t in tasks}
    for t in tasks:
        missing = [d for d in t.deps if d not in known]
        if missing:
            raise PlanError(f"{t.id}: 없는 선행 태스크 {', '.join(missing)}")
    checklist = _parse_checklist(check_lines)
    autonomy = autonomy_value(attrs["autonomy"]) if "autonomy" in attrs else None
    return IssuePlan(version, tasks, checklist, autonomy)


def _parse_checklist(lines: list[str]) -> list[IssuePlanCheck]:
    if not lines:
        return []
    if len(lines) < 2 or not all(re.fullmatch(r":?-{3,}:?", c) for c in _cells(lines[1])):
        raise PlanError("체크리스트 표 구분줄이 아니다")
    out: list[IssuePlanCheck] = []
    for ln in lines[2:]:
        c = _cells(ln)
        if len(c) != len(CHECK_COLUMNS):
            raise PlanError(f"체크리스트 칸 수가 {len(c)}개다 (필요 {len(CHECK_COLUMNS)}): {ln.strip()[:80]!r}")
        cid, state, item, evidence = c
        if not CHECK_ID.match(cid):
            raise PlanError(f"체크리스트 ID 는 C<숫자>다: {cid!r}")
        if state not in CHECK_STATES:
            raise PlanError(f"{cid}: 모르는 체크리스트 상태 {state!r} (허용 {', '.join(CHECK_STATES)})")
        if not item:
            raise PlanError(f"{cid}: 항목이 비었다")
        if any(x.id == cid for x in out):
            raise PlanError(f"체크리스트 ID 가 겹친다: {cid}")
        out.append(IssuePlanCheck(cid, state, item, evidence))
    return out


def _needed_version(tasks: list[IssuePlanTask], current: int, checklist=(), autonomy=None) -> int:
    """단계를 선언한 태스크가 있으면 v2 이상, 체크리스트·자율성이 있으면 v3. 아니면 지금 버전을 지킨다."""
    if checklist or autonomy is not None:
        return max(current, 3)
    return max(current, 2) if any(t.steps for t in tasks) else current


def _begin(version: int, autonomy: float | None) -> str:
    attr = f" autonomy={autonomy:g}" if autonomy is not None else ""
    return f"<!-- ax:plan:begin v={version}{attr} -->"


def render_checklist(checklist: list[IssuePlanCheck]) -> str:
    """체크리스트 표(LF, 앞에 빈 줄). 비면 ""."""
    if not checklist:
        return ""
    rows = ["| " + " | ".join(CHECK_COLUMNS) + " |", "|" + "---|" * len(CHECK_COLUMNS)]
    seen = set()
    for c in checklist:
        if not CHECK_ID.match(c.id) or c.id in seen:
            raise PlanError(f"체크리스트 ID 는 겹치지 않는 C<숫자>다: {c.id!r}")
        if c.state not in CHECK_STATES:
            raise PlanError(f"{c.id}: 모르는 체크리스트 상태 {c.state!r}")
        if not c.item.strip():
            raise PlanError(f"{c.id}: 항목이 비었다")
        seen.add(c.id)
        rows.append("|" + "".join(f" {_cell(x)} |" if x else " |" for x in (c.id, c.state, c.item, c.evidence)))
    return "\n" + "\n".join(rows) + "\n"


def render(tasks: list[IssuePlanTask], *, version: int = FORMAT_VERSION) -> str:
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
        if CHECK_ID.match(t.id):
            raise PlanError(f"{t.id}: C<숫자> 는 체크리스트 ID 다 — 태스크 ID 로 쓸 수 없다")
        if version == 1 and t.steps:
            raise PlanError(f"{t.id}: v1 표에는 단계 칸이 없다")
        deps = "·".join(t.deps) if t.deps else NO_DEPS
        steps = "·".join(str(s) for s in sorted(set(t.steps))) if t.steps else NO_DEPS
        cells = ((t.id, t.state, t.goal, t.target, deps, t.check, t.evidence) if version == 1
                 else (t.id, t.state, t.goal, t.target, steps, deps, t.check, t.evidence))
        rows.append("|" + "".join(f" {_cell(x)} |" if x else " |" for x in cells))
    return "\n" + "\n".join(rows) + "\n"


_KEEP = object()


def replace(body: str, tasks: list[IssuePlanTask], *, checklist=_KEEP, autonomy=_KEEP) -> str:
    """플랜 영역 안만 `tasks` 로 바꾼 본문. 영역 밖은 바이트 그대로다.

    `checklist`·`autonomy` 를 주지 않으면 지금 값을 그대로 둔다(v3). 주면 바꾼다.

    영역이 없으면 `PlanError` — 처음 만드는 것은 `append` 다. 둘을 나눈 이유: 갱신하려던
    본문에 영역이 없는 것은 대개 엉뚱한 일감을 집은 것이라 조용히 새로 만들면 안 된다.
    """
    region = _region(body or "")
    if region is None:
        raise PlanError("플랜 영역이 없다 — 새로 만들려면 append")
    tag, start, end, version = region
    _check_version(version)
    current = parse(body)
    checklist = current.checklist if checklist is _KEEP else list(checklist or [])
    autonomy = current.autonomy_raw if autonomy is _KEEP else (
        None if autonomy is None else autonomy_value(autonomy))
    out_version = _needed_version(tasks, version, checklist, autonomy)
    inner = render(tasks, version=out_version) + render_checklist(checklist)
    if "\r\n" in body:
        inner = inner.replace("\n", "\r\n")
    same = out_version == version and autonomy == current.autonomy_raw
    begin = body[tag:start] if same else _begin(out_version, autonomy)
    return body[:tag] + begin + inner + body[end:]


def append(body: str, tasks: list[IssuePlanTask], *, heading: str = "## 플랜", checklist=(), autonomy=None) -> str:
    """플랜 영역이 없는 본문 끝에 제목과 영역을 붙인다. 이미 있으면 `PlanError`."""
    if _region(body or "") is not None:
        raise PlanError("플랜 영역이 이미 있다 — 갱신은 replace")
    checklist = list(checklist or [])
    autonomy = None if autonomy is None else autonomy_value(autonomy)
    version = _needed_version(tasks, FORMAT_VERSION, checklist, autonomy)
    nl = "\r\n" if "\r\n" in (body or "") else "\n"
    block = (f"{heading}\n\n{_begin(version, autonomy)}"
             + render(tasks, version=version) + render_checklist(checklist) + END_TAG + "\n").replace("\n", nl)
    base = (body or "").rstrip("\r\n")
    return (base + nl + nl if base else "") + block
