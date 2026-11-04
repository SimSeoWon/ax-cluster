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
[중요] **규칙 거절은 `plan_events` 에 한 줄씩 남긴다** (`#864` T1) — 노트는 성공만 남기므로 거절은
여기서만 보인다. 예외는 **그대로 다시 올린다.** Redmine 읽기·쓰기 실패(`PlanTransportError`)는
규칙 거절이 아니라서 남기지 않는다. 기본 경로(실 Redmine getter)일 때만 기록하고, getter 를
주입한 호출(테스트 대역)은 `events_path` 를 줄 때만 기록한다 — 대역 실행이 운영 기록을 오염시키지
않게.
[중요] **`#883` 일감 하나씩 — 「작업중」 전이는 일감 잠금(`issue_lock`)을 본다.** 다른 일감이 활성이면
거절한다(같은 `_rejections` 경로, 보유 일감 번호를 사유에 싣는다). 아무도 활성이 아니면 보류 중인
일감도 허용하되 「재개는 issue_start」 를 결과에 알린다. 잠금 위치는 `lock_root` → 없으면 운영 호출만
AXCluster 트윈(`issue_lock.default_root()`); getter·updater 를 주입하고 `lock_root` 를 안 주면 **검사를
건너뛴다**(대역이 운영 상태를 읽지 않게). [주의] `redmine.get_issue` 응답에 프로젝트가 없어
AXCluster 일감만 고르지 못한다 — **모든 일감의 「작업중」 전이에 적용한다.**
"""
from __future__ import annotations

from contextlib import contextmanager

from master import plan_block as PB
from master import plan_events as PE
from master import plan_start as ST
from master import plan_state as PS
from master import plan_steps as STEPS


class PlanToolError(PB.PlanError):
    """도구 입력이 계약에 어긋났다 — 사유 문장을 담는다."""


class PlanTransportError(PlanToolError):
    """Redmine 읽기·쓰기 실패 — 규칙 거절이 아니다(거절 기록에 남기지 않는다)."""


@contextmanager
def _rejections(op: str, issue_id, *, enabled: bool, events_path=None, caller: str = "",
                ctx: dict | None = None):
    """규칙 거절(`PlanError` 계열, 전송 실패 제외)을 기록하고 **그대로** 다시 올린다.

    `ctx` 는 블록 안에서 채워지는 값(task_id·from·to·note·tasks)이다 — 거절 시점의 값을 쓴다.
    """
    ctx = ctx if ctx is not None else {}
    try:
        yield ctx
    except PB.PlanError as e:
        if enabled and not isinstance(e, PlanTransportError):
            PE.record(op, issue_id, e, path=events_path, caller=caller,
                      task_id=ctx.get("task_id", ""), from_state=ctx.get("from", ""),
                      to=ctx.get("to", ""), note=ctx.get("note", ""), tasks=ctx.get("tasks"))
        raise


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
        raise PlanTransportError(f"#{issue_id} 를 읽지 못했다 — {reason}")
    return got.get("description") or ""


def _write(issue_id, body: str, notes: str, updater) -> str:
    out = updater(issue_id, description=body, notes=notes)
    if str(out).startswith("[주의]"):
        raise PlanTransportError(str(out))
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


def set_plan(issue_id, tasks: list, why: str, *, getter=None, updater=None,
             events_path=None, caller: str = "") -> dict:
    """플랜을 만들거나 태스크를 추가·편집한다. `tasks` 는 **원하는 전체 목록**(표 순서)이다.

    각 항목: `id`·`goal` 필수, `target`·`deps`(목록 또는 「T1·T2」)·`check`·`steps`(조건부 단계 선언,
    목록 또는 「2·6」 — v2) 선택.
    `state`·`evidence` 를 실으면 거절한다 — 상태는 `transition` 으로만 바뀐다.
    """
    ids = [str(t.get("id", "")) if isinstance(t, dict) else "?" for t in tasks] \
        if isinstance(tasks, list) else []
    with _rejections("set", issue_id, enabled=events_path is not None or getter is None,
                     events_path=events_path, caller=caller, ctx={"tasks": ids}):
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


def _lock_gate(issue_id, lock_root) -> str:
    """「작업중」 전이의 잠금 검사(`#883`). 거절이면 `PlanToolError`, 아니면 알릴 문장(없으면 "")."""
    from master import issue_lock as IL
    try:
        root = lock_root if lock_root is not None else IL.default_root()
        active = IL.current(root)
        paused = IL.paused(root)
    except Exception as e:                              # noqa: BLE001 — IssueLockError·경로 해석
        raise PlanTransportError(f"일감 잠금 상태를 못 읽었다 — {type(e).__name__}: {e}") from e
    n = int(issue_id)
    if active and active["issue_id"] != n:
        h = active["issue_id"]
        state = "보류 중인 " if n in paused else ""
        raise PlanToolError(f"#{h} 작업이 진행 중이다({active.get('branch')}) — {state}#{n} 의 태스크를 "
                            f"작업중으로 옮기지 않는다, 일감은 하나씩 한다. #{h} 를 완료·보류(issue_pause)·"
                            "취소(issue_cancel)한 뒤 진행한다")
    if n in paused:
        return f"#{n} 는 보류 중이다 — 작업 재개(브랜치·잠금)는 issue_start 가 한다"
    return ""


def transition(issue_id, task_id: str, to: str, note: str = "", *, getter=None,
               updater=None, events_path=None, caller: str = "", lock_root=None) -> dict:
    """태스크 하나의 상태를 바꾸고 같은 갱신에 노트를 남긴다.

    「작업중」 으로 갈 때는 일감 잠금을 본다(`#883` — 모듈 설명).
    """
    ctx = {"task_id": task_id, "to": to, "note": note or ""}
    injected = getter is not None or updater is not None
    lock_note = ""
    with _rejections("transition", issue_id, enabled=events_path is not None or getter is None,
                     events_path=events_path, caller=caller, ctx=ctx):
        if to == PS.WORKING and (lock_root is not None or not injected):
            lock_note = _lock_gate(issue_id, lock_root)
        body = _read(issue_id, getter or _default_getter)
        plan = PB.parse(body)
        if plan is None:
            raise PlanToolError(f"#{issue_id} 에 플랜 영역이 없다 — 먼저 plan_set 으로 등록한다")
        before = plan.task(task_id).state if plan.task(task_id) else ""
        ctx["from"] = before
        plan = PS.transition(plan, task_id, to, note=note)
        new_body = PB.replace(body, plan.tasks)
        line = f"플랜 {task_id}: {before} → {to}" + (f" — {note.strip()}" if (note or "").strip() else "")
        result = _write(issue_id, new_body, line, updater or _default_updater)
    nxt = ST.assess(new_body)
    out = {"ok": True, "issue_id": issue_id, "task": task_id, "from": before, "to": to,
           "next": nxt.as_dict(), "redmine": result}
    if lock_note:
        out["lock_note"] = lock_note
    return out
