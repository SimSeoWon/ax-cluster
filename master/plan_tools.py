"""플랜 도구의 본체 — `#826` T5. MCP(`projects/mcp_server.py`)는 이 함수들을 부르기만 한다.

    start(issue_id)                      시작 판정(T3) + 7단계 표(T4). 읽기만 한다
    set_plan(issue_id, tasks, why)       플랜 등록·태스크 추가·편집. **상태·근거는 못 바꾼다**
    transition(issue_id, task_id, to, note)   상태 전이(T2) — 상태를 바꾸는 유일한 쓰기

[중요] **상태는 `transition` 으로만 바뀐다.** `set_plan` 이 상태·근거를 받으면 T2 의 규칙
(근거 없는 완료 거절 등)을 옆문으로 우회할 수 있다. 그래서 `set_plan` 의 새 태스크는 늘
「대기」로 들어가고, 기존 태스크의 상태·근거는 본문 값을 그대로 쓴다. 이미 시작된 태스크는
목록에서 빼지 못한다.
[중요] **쓰기는 Redmine 의 그 이슈 본문 하나다** — 플랜 영역 밖은 `plan_block` 이 보존하고,
왜 바꿨는지는 같은 갱신의 노트로 남긴다. `update_issue` 가 `[주의]` 로 답하면 성공이 아니다.
[주의] 읽고-고치고-쓰는 사이에 사람이 본문을 고치면 그 수정은 덮인다(Redmine 이슈 API 에
조건부 갱신이 없다). 같은 일감을 두 세션이 동시에 마킹하지 않는 것이 전제다.
"""
from __future__ import annotations

from master import plan_block as PB
from master import plan_start as ST
from master import plan_state as PS
from master import plan_steps as STEPS


class PlanToolError(PB.PlanError):
    """도구 입력이 계약에 어긋났다 — 사유 문장을 담는다."""


def _deps_of(raw) -> list[str]:
    if raw in (None, "", PB.NO_DEPS):
        return []
    if isinstance(raw, str):
        return PB._deps(raw)
    return [str(d).strip() for d in raw if str(d).strip()]


def _steps_of(raw) -> list[int]:
    """「단계」 선언 — 목록(`[2, 6]`) 또는 「2·6」. 1~7 밖이면 `plan_block` 이 거절한다."""
    if raw in (None, "", PB.NO_DEPS, []):
        return []
    if isinstance(raw, (str, int)):
        return PB._steps(str(raw))
    return PB._steps("·".join(str(x) for x in raw))


def _default_getter(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)


def _default_updater(issue_id, *, description: str, notes: str) -> str:
    from master import redmine
    return redmine.update_issue(issue_id, description=description, notes=notes)


def _read(issue_id, getter) -> str:
    got = getter(issue_id)
    if not isinstance(got, dict) or got.get("error"):
        reason = got.get("error") if isinstance(got, dict) else "응답 형식이 아니다"
        raise PlanToolError(f"#{issue_id} 를 읽지 못했다 — {reason}")
    return got.get("description") or ""


def _write(issue_id, body: str, notes: str, updater) -> str:
    out = updater(issue_id, description=body, notes=notes)
    if str(out).startswith("[주의]"):
        raise PlanToolError(str(out))
    return str(out)


def start(issue_id, *, project: str = "", getter=None, kind_of=None, active=None) -> dict:
    """시작 판정과 그 프로젝트의 7단계 표. `project` 를 비우면 마운트된 프로젝트다."""
    out = ST.start_issue(issue_id, getter=getter or _default_getter)
    if "error" in out:
        return {"ok": False, **out}
    if not project:
        if active is None:
            from master.projects.config import Registry
            active = lambda: Registry.load().active          # noqa: E731
        project = active() or ""
    out["project"] = project
    try:
        out["steps"] = [s.__dict__ for s in STEPS.steps_for_project(project, kind_of=kind_of)]
    except STEPS.StepError as e:
        out["steps"], out["steps_error"] = [], str(e)
    return out


def set_plan(issue_id, tasks: list, why: str, *, getter=None, updater=None) -> dict:
    """플랜을 만들거나 태스크를 추가·편집한다. `tasks` 는 **원하는 전체 목록**(표 순서)이다.

    각 항목: `id`·`goal` 필수, `target`·`deps`(목록 또는 「T1·T2」)·`check`·`steps`(조건부 단계 선언,
    목록 또는 「2·6」 — v2) 선택.
    `state`·`evidence` 를 실으면 거절한다 — 상태는 `transition` 으로만 바뀐다.
    """
    if not (why or "").strip():
        raise PlanToolError("why 가 비었다 — 플랜을 왜 바꾸는지 노트로 남긴다")
    if not isinstance(tasks, list) or not tasks:
        raise PlanToolError("tasks 가 비었다")
    body = _read(issue_id, getter or _default_getter)
    current = PB.parse(body)
    old = {t.id: t for t in (current.tasks if current else [])}
    new_tasks: list[PB.Task] = []
    for raw in tasks:
        if not isinstance(raw, dict):
            raise PlanToolError(f"태스크 항목이 객체가 아니다: {raw!r}")
        banned = [k for k in ("state", "evidence") if k in raw]
        if banned:
            raise PlanToolError(f"{raw.get('id', '?')}: {', '.join(banned)} 는 set_plan 으로 못 바꾼다 "
                                "— 상태는 plan_transition 으로만")
        tid, goal = str(raw.get("id") or "").strip(), str(raw.get("goal") or "").strip()
        if not tid or not goal:
            raise PlanToolError(f"id·goal 은 필수다: {raw!r}")
        prev = old.get(tid)
        new_tasks.append(PB.Task(tid, prev.state if prev else PS.WAITING, goal,
                                 str(raw.get("target") or "").strip(), _deps_of(raw.get("deps")),
                                 str(raw.get("check") or "").strip(),
                                 prev.evidence if prev else "", _steps_of(raw.get("steps"))))
    kept = {t.id for t in new_tasks}
    dropped = [t for t in old.values() if t.id not in kept]
    started = [t.id for t in dropped if t.state != PS.WAITING]
    if started:
        raise PlanToolError(f"시작된 태스크는 목록에서 뺄 수 없다: {', '.join(started)}")
    new_body = PB.replace(body, new_tasks) if current else PB.append(body, new_tasks)
    plan = PB.parse(new_body)                      # 선행·ID 중복 등은 여기서 거절된다
    bad = PS.violations(plan)
    if bad:
        raise PlanToolError("규칙 위반이 생긴다 — " + " · ".join(bad))
    added = [t.id for t in new_tasks if t.id not in old]
    summary = (f"플랜 {'갱신' if current else '등록'} — 추가 {', '.join(added) or '없음'}"
               f" · 제거 {', '.join(t.id for t in dropped) or '없음'}\n사유: {why.strip()}")
    result = _write(issue_id, new_body, summary, updater or _default_updater)
    return {"ok": True, "issue_id": issue_id, "created": current is None, "added": added,
            "removed": [t.id for t in dropped], "tasks": [t.id for t in plan.tasks],
            "redmine": result}


def transition(issue_id, task_id: str, to: str, note: str = "", *, getter=None,
               updater=None) -> dict:
    """태스크 하나의 상태를 바꾸고 같은 갱신에 노트를 남긴다."""
    body = _read(issue_id, getter or _default_getter)
    plan = PB.parse(body)
    if plan is None:
        raise PlanToolError(f"#{issue_id} 에 플랜 영역이 없다 — 먼저 plan_set 으로 등록한다")
    before = plan.task(task_id).state if plan.task(task_id) else ""
    plan = PS.transition(plan, task_id, to, note=note)
    new_body = PB.replace(body, plan.tasks)
    line = f"플랜 {task_id}: {before} → {to}" + (f" — {note.strip()}" if (note or "").strip() else "")
    result = _write(issue_id, new_body, line, updater or _default_updater)
    nxt = ST.assess(new_body)
    return {"ok": True, "issue_id": issue_id, "task": task_id, "from": before, "to": to,
            "next": nxt.as_dict(), "redmine": result}
