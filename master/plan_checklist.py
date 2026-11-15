"""마감 체크리스트 판정 — `#963` T4.

사용자 결정(2026-11-15, #963 스펙 영역): 플랜에서 구성한 **개발 완료 체크리스트**에 「미확인」 항목이 남아
있으면 마감(`issue_finish`)은 목록을 보이고 **멈춰 사람에게 묻는다** — 근거 보강 · 이번 범위 제외 · 작업 계속.
사용자의 답은 `plan_transition(C<n>, 충족|제외, …)` 으로 기록되고, 그 뒤 마감을 다시 부르면 진행된다.

두 마감 경로가 이 함수 하나를 부른다 — 마스터 `issue_flow.finish`(AXCluster) · `.33` 의 `issue_infra.infra_finish`.

- 체크리스트가 없는 플랜(옛 v1·v2, 비범위: 소급)은 지금처럼 통과한다.
- 본문을 읽지 못하거나 플랜 형식이 깨졌으면 **확인하지 못한 채 마감하지 않는다**(fail-closed).
- 근거의 진위·질은 보지 않는다 — 상태가 「미확인」인지만 본다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from master import plan_block as PB
from master import plan_state as PS

ASK = ("사용자에게 항목별로 묻는다 — 근거 보강(plan_transition C<n> 충족 + 근거) · 이번 범위 제외"
       "(plan_transition C<n> 제외 + 사유 + user_answer) · 작업 계속. 기록한 뒤 마감을 다시 부른다")


@dataclass
class Verdict:
    ok: bool
    why: str = ""
    pending: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {"ok": self.ok, "counts": self.counts}
        if not self.ok:
            out.update({"why": self.why, "pending": self.pending})
        return out


def judge(body: str) -> Verdict:
    """본문 하나로 판정한다(순수 함수)."""
    try:
        plan = PB.parse(body or "")
    except PB.PlanError as e:
        return Verdict(False, f"플랜 형식이 깨져 체크리스트를 확인하지 못했다 — {e}")
    if plan is None or not plan.checklist:
        return Verdict(True)
    counts = {s: sum(1 for c in plan.checklist if c.state == s) for s in PB.CHECK_STATES}
    pending = [{"id": c.id, "item": c.item} for c in plan.checklist if c.state == PS.UNCHECKED]
    if pending:
        ids = ", ".join(p["id"] for p in pending)
        return Verdict(False, f"개발 완료 체크리스트 미확인 {len(pending)}개({ids}) — {ASK}", pending, counts)
    return Verdict(True, counts=counts)


def check(issue_id, getter) -> Verdict:
    """Redmine 일감을 읽어 판정한다. 읽기 실패는 미통과다."""
    try:
        got = getter(issue_id)
    except Exception as e:                               # noqa: BLE001
        return Verdict(False, f"일감을 읽지 못해 체크리스트를 확인하지 못했다 — {type(e).__name__}: {e}")
    if not isinstance(got, dict) or got.get("error"):
        reason = got.get("error") if isinstance(got, dict) else "응답 형식이 아니다"
        return Verdict(False, f"일감을 읽지 못해 체크리스트를 확인하지 못했다 — {reason}")
    return judge(got.get("description") or "")


def default_getter(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)
