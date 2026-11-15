"""공용 일감 테스트 픽스처(`#963` T9) 자체 검사 — 픽스처가 **실제 흐름**으로 상태를 만드는가.

실행: .venv/bin/python master/test_testkit_issue.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB            # noqa: E402
from master import plan_proposal as PP         # noqa: E402
from master import plan_start as ST            # noqa: E402
from master import spec_block as SB            # noqa: E402
from master import testkit_issue as TK         # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


TASKS = [{"id": "T1", "goal": "읽기"}, {"id": "T2", "goal": "쓰기", "deps": ["T1"]}]


def test_spec_body():
    b = TK.spec_body()
    check("스펙 영역이 있다", SB.exists(b))
    check("판정은 plan_needed", ST.assess(b).verdict == "plan_needed", ST.assess(b).verdict)


def test_issue_with_plan_goes_through_the_flow():
    iss = TK.issue_with_plan(TASKS, checklist=["제안 없는 등록 거절"], autonomy=0.25)
    plan = TK.plan_of(iss)
    check("플랜 등록", [t.id for t in plan.tasks] == ["T1", "T2"])
    check("체크리스트·자율성이 제안대로", [c.item for c in plan.checklist] == ["제안 없는 등록 거절"]
          and plan.checklist[0].state == "미확인" and plan.autonomy == 0.25, str(plan))
    check("제안 노트가 남았다", PP.latest(iss.journals)["tasks"][1]["deps"] == ["T1"])
    check("등록 노트에 동의가 실렸다", "사용자 동의: 동의" in iss.notes[-1], iss.notes[-1])
    check("노트 순서 제안 → 등록", iss.notes[0].startswith(PP.MARK) and "플랜 등록" in iss.notes[1])
    check("CRLF 본문", "\n" not in iss.body.replace("\r\n", ""))
    check("판정은 next", ST.assess(iss.body).verdict == "next")


def test_register_edit_needs_new_proposal_each_time():
    iss = TK.issue_with_plan(TASKS)
    out = TK.register(iss, 1, TASKS + [{"id": "T3", "goal": "더"}], "T3 추가")
    check("편집도 제안 → 등록", out["added"] == ["T3"] and len(PP.proposals(iss.journals)) == 2, str(out))


def test_answer_simulates_write_failure():
    iss = TK.FakeIssue(TK.spec_body(), answer="[주의] 실패")
    try:
        TK.propose(iss, 1, TASKS)
        ok = False
    except PB.PlanError as e:
        ok = "[주의] 실패" in str(e)
    check("쓰기 실패 흉내", ok and iss.journals == [] and iss.writes, str(iss.writes))


def main() -> int:
    for fn in (test_spec_body, test_issue_with_plan_goes_through_the_flow,
               test_register_edit_needs_new_proposal_each_time, test_answer_simulates_write_failure):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_testkit_issue: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
