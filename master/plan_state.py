"""플랜 태스크 **상태 전이 강제** — `#826` T2.

`plan_block` 이 형식을 판정한다면 이 모듈은 **의미**를 판정한다. 상태를 바꾸는 길은
`transition` 하나이고, 규칙에 어긋나면 고쳐 주지 않고 `TransitionError` 로 거절한다.

    대기   → 작업중 · 차단 · 해당없음
    작업중 → 완료 · 차단 · 대기
    차단   → 작업중 · 대기
    해당없음 → 대기
    완료   → (없음)

[중요] **근거 없는 완료, 사유 없는 차단·해당없음은 거절한다.** 근거·사유는 표의 「근거」 칸에
들어간다 — 칸이 하나라 같은 자리를 쓴다. 지난 사유의 이력은 Redmine 노트가 갖는다.
[중요] **선행 태스크가 완료·해당없음이 아니면 작업중으로 들어가지 않는다** — #826 의
「선행 조건 불충족 시 다음 단계로 자동 전진하지 않는다」를 태스크 단위로 집행한 것이다.
[주의] **완료는 되돌리지 않는다.** 잘못 마킹했으면 사람이 본문을 고친다 — 자동 경로가
완료를 풀 수 있으면 「검증 뒤 완료」가 의미를 잃는다.

`violations` 는 사람이 본문을 직접 고친 플랜이 이 규칙을 어겼는지 읽기만 한다(T3 이 쓴다).
"""
from __future__ import annotations

import copy

from master.plan_block import Plan, PlanError

WAITING, WORKING, DONE, BLOCKED, SKIPPED = "대기", "작업중", "완료", "차단", "해당없음"

ALLOWED = {
    WAITING: (WORKING, BLOCKED, SKIPPED),
    WORKING: (DONE, BLOCKED, WAITING),
    BLOCKED: (WORKING, WAITING),
    SKIPPED: (WAITING,),
    DONE: (),
}
NEEDS_NOTE = {DONE: "근거", BLOCKED: "사유", SKIPPED: "사유"}
SETTLED = (DONE, SKIPPED)


class TransitionError(PlanError):
    """상태 전이 규칙 위반 — 사유 문장을 담는다."""


def _unsettled_deps(plan: Plan, task_id: str) -> list[str]:
    t = plan.task(task_id)
    return [d for d in t.deps if (plan.task(d) is None or plan.task(d).state not in SETTLED)]


def transition(plan: Plan, task_id: str, to: str, *, note: str = "") -> Plan:
    """`task_id` 를 `to` 로 옮긴 **새** 플랜. 원본은 건드리지 않는다.

    `note` 는 완료면 근거, 차단·해당없음이면 사유다(필수). 작업중·대기로 갈 때는 선택이고,
    주지 않으면 근거 칸을 비운다 — 지난 차단 사유가 새 상태의 근거처럼 남지 않게.
    """
    t = plan.task(task_id)
    if t is None:
        raise TransitionError(f"없는 태스크: {task_id}")
    if to not in ALLOWED:
        raise TransitionError(f"{task_id}: 모르는 상태 {to!r}")
    if to not in ALLOWED[t.state]:
        allowed = ", ".join(ALLOWED[t.state]) or "없음"
        raise TransitionError(f"{task_id}: {t.state} → {to} 는 허용되지 않는다 (가능: {allowed})")
    note = (note or "").strip()
    if to in NEEDS_NOTE and not note:
        raise TransitionError(f"{task_id}: {to} 에는 {NEEDS_NOTE[to]}가 필요하다")
    if to == WORKING:
        pending = _unsettled_deps(plan, task_id)
        if pending:
            raise TransitionError(f"{task_id}: 선행 태스크가 끝나지 않았다 — {', '.join(pending)}")
    out = copy.deepcopy(plan)
    nt = out.task(task_id)
    nt.state, nt.evidence = to, note
    return out


def violations(plan: Plan) -> list[str]:
    """본문을 사람이 고친 플랜이 규칙을 어긴 곳. 비어 있으면 깨끗하다."""
    found = []
    for t in plan.tasks:
        if t.state in NEEDS_NOTE and not t.evidence.strip():
            found.append(f"{t.id}: {t.state}인데 {NEEDS_NOTE[t.state]}가 비었다")
        if t.state in (WORKING, DONE):
            pending = _unsettled_deps(plan, t.id)
            if pending:
                found.append(f"{t.id}: {t.state}인데 선행이 끝나지 않았다 — {', '.join(pending)}")
    return found
