"""「일감 시작」 진입점 — `#826` T3.

일감을 시작하라는 요청을 받으면 **구현보다 먼저** 이 판정을 부른다. 판정만 하고 아무것도
쓰지 않는다 — 상태를 바꾸는 것은 `plan_state.transition` 의 몫이다.

    no_spec         본문에 스펙이 없다                       → 스펙부터 사람과 쓴다
    plan_needed     플랜 영역이 없다                         → RAG·현재 소스 대조 뒤 사용자와 플랜을 쓴다
    plan_invalid    플랜 형식이 어긋났다(PlanError)           → 본문을 사람과 고친다
    plan_violations 형식은 맞지만 상태 규칙을 어겼다           → 위반을 사람과 고친다
    resume          작업중 태스크가 있다                     → 그 태스크부터 재개(실제 상태 재대조)
    next            시작할 수 있는 대기 태스크가 있다          → 그 태스크를 작업중으로
    blocked         남은 태스크가 차단·선행 대기뿐이다         → 사유를 보고하고 멈춘다
    plan_done       모든 태스크가 완료·해당없음이다            → 일감 완료 여부는 스펙·승인 규칙으로 따로

[중요] **`plan_needed` 에서 구현으로 넘어가지 않는다** (#826 §2). 이 함수가 길을 막는 것이
아니라 호출자(스킬·세션)가 `ok` 가 아닌 판정에서 멈추는 것이 계약이다 — 그래서 판정마다
`ok` 와 다음 행동 문장을 함께 돌려준다.
[주의] `resume` 은 플랜 기록만 본 것이다. 재개 전에 실제 코드·리비전과 대조하는 것은 호출자 몫이다.

`spec_missing` (`#911`) — 스펙 템플릿(`docs/issue-spec.md`)의 여섯 항목 중 본문 제목 줄에 없는 것의
키 목록. [중요] **경고만 한다** — 판정(`verdict`·`ok`)을 바꾸지 않는다(사용자 결정 2026-11-14).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from master import plan_block as PB
from master import plan_state as PS

NEXT_ACTION = {
    "no_spec": "스펙(무엇을 개발할지·완료 조건)을 사용자와 먼저 쓴다",
    "plan_needed": "구현하지 않는다 — RAG 와 현재 소스를 대조한 뒤 사용자와 플랜을 작성해 이 일감의 플랜 영역에 등록한다",
    "plan_invalid": "플랜 형식 오류를 사용자에게 보이고 본문을 함께 고친다",
    "plan_violations": "상태 규칙 위반을 사용자에게 보이고 함께 고친다",
    "resume": "작업중 태스크를 실제 코드·리비전 상태와 대조한 뒤 이어서 한다",
    "next": "이 태스크를 작업중으로 바꾸고 시작한다",
    "blocked": "차단 사유와 대기 중인 선행을 사용자에게 보고하고 멈춘다",
    "plan_done": "모든 태스크가 끝났다 — 일감 완료는 스펙·완료 조건과 승인 규칙으로 따로 판단한다",
}
OK_VERDICTS = ("resume", "next")

# 스펙 템플릿 여섯 항목(docs/issue-spec.md §2) — (키, 제목 열쇠말). 제목 줄에 열쇠말 하나가 들어 있으면 있다고 본다.
SPEC_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("problem", ("문제", "배경", "맥락")),
    ("triage", ("분류", "트리아지")),
    ("observe", ("관측", "you see", "사용 예")),
    ("scope", ("범위", "파급")),
    ("done", ("완료 조건", "완료 기준", "증명")),
    ("open", ("열린 결정", "열린 질문", "미정")),
)


@dataclass
class StartVerdict:
    verdict: str
    detail: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict in OK_VERDICTS

    @property
    def next_action(self) -> str:
        return NEXT_ACTION[self.verdict]

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "ok": self.ok, "tasks": self.tasks,
                "detail": self.detail, "next_action": self.next_action}


def spec_missing(body: str) -> list[str]:
    """스펙 템플릿 항목 중 본문(플랜 영역 밖) 제목 줄에 없는 것의 키 — 경고용, 판정과 무관."""
    heads = [ln.lstrip().lstrip("#").strip().lower()
             for ln in _outside_plan(body or "").splitlines() if ln.lstrip().startswith("#")]
    return [key for key, words in SPEC_SECTIONS
            if not any(w in h for h in heads for w in words)]


def _outside_plan(body: str) -> str:
    m = PB.BEGIN_RE.search(body)
    end = body.find(PB.END_TAG)
    if m and end > m.end():
        return body[:m.start()] + body[end + len(PB.END_TAG):]
    return body


def assess(body: str) -> StartVerdict:
    """이슈 본문 하나로 시작 판정을 낸다(순수 함수)."""
    body = body or ""
    try:
        plan = PB.parse(body)
    except PB.PlanError as e:
        return StartVerdict("plan_invalid", [str(e)])
    # 제목 줄만 있는 본문(`## 플랜` 등)은 스펙이 아니다
    if not any(ln.strip() and not ln.lstrip().startswith("#")
               for ln in _outside_plan(body).splitlines()):
        return StartVerdict("no_spec")
    if plan is None:
        return StartVerdict("plan_needed")
    bad = PS.violations(plan)
    if bad:
        return StartVerdict("plan_violations", bad)
    working = [t.id for t in plan.tasks if t.state == PS.WORKING]
    if working:
        return StartVerdict("resume", tasks=working)
    for t in plan.tasks:
        if t.state == PS.WAITING:
            try:
                PS.transition(plan, t.id, PS.WORKING)
            except PS.TransitionError:
                continue
            return StartVerdict("next", tasks=[t.id])
    open_ = [t for t in plan.tasks if t.state not in PS.SETTLED]
    if not open_:
        return StartVerdict("plan_done")
    detail = []
    for t in open_:
        if t.state == PS.BLOCKED:
            detail.append(f"{t.id}: 차단 — {t.evidence}")
        else:
            pending = [d for d in t.deps if plan.task(d).state not in PS.SETTLED]
            detail.append(f"{t.id}: 선행 대기 — {', '.join(pending)}")
    return StartVerdict("blocked", detail, [t.id for t in open_])


def start_issue(issue_id, *, getter=None) -> dict:
    """Redmine 이슈를 읽어 시작 판정을 낸다. 읽기 실패는 판정이 아니라 오류로 돌려준다."""
    if getter is None:
        from master import redmine
        getter = redmine.get_issue
    got = getter(issue_id)
    if not isinstance(got, dict) or got.get("error"):
        return {"error": (got or {}).get("error", "이슈를 읽지 못했다") if isinstance(got, dict)
                else "이슈를 읽지 못했다", "issue_id": issue_id}
    body = got.get("description") or ""
    out = assess(body).as_dict()
    out["spec_missing"] = spec_missing(body)
    out.update({"issue_id": got.get("id", issue_id), "subject": got.get("subject", "")})
    return out
