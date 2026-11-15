"""플랜 제안 → 동의 → 등록(`#963` T2) 계약 테스트 — [중요] **제안하지 않은 표는 등록되지 않는가.**

실행: .venv/bin/python master/test_plan_proposal.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB            # noqa: E402
from master import plan_proposal as PP         # noqa: E402
from master import plan_tools as PT            # noqa: E402
from master import testkit_issue as TK         # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


TASKS = [{"id": "T1", "goal": "읽기", "target": "a.py", "check": "단위"},
         {"id": "T2", "goal": "쓰기", "deps": "T1", "check": "왕복"}]


def _err(fn) -> str:
    try:
        fn()
    except PB.PlanError as e:
        return str(e)
    return ""


def _set(iss, tasks=TASKS, answer="동의"):
    return PT.set_plan(1, tasks, "등록", user_answer=answer, getter=iss.get, updater=iss.update)


def test_propose_records_note():
    iss = TK.FakeIssue(TK.spec_body())
    out = TK.propose(iss, 1, TASKS, checklist=["제안 없는 등록 거절", {"item": "마감 경로 멈춤"}])
    check("응답", out["ok"] and out["tasks"] == ["T1", "T2"] and out["checklist"] == ["C1", "C2"]
          and out["autonomy"] == 0.5, str(out))
    note = iss.notes[-1]
    check("표지·요약", note.startswith(PP.MARK) and "태스크 2 · 체크리스트 2 · 자율성 0.5" in note, note[:120])
    prop = PP.latest(iss.journals)
    check("JSON 왕복 — 선행 문자열도 목록으로", prop["tasks"][1]["deps"] == ["T1"]
          and prop["checklist"][1] == {"id": "C2", "item": "마감 경로 멈춤"}, str(prop))
    check("본문은 안 바꾼다(제안은 노트뿐)", PB.parse(iss.body) is None)


def test_propose_refusals():
    bare = TK.FakeIssue(TK.BARE)
    check("스펙 영역 없음 거절", "스펙 영역이 없다" in _err(lambda: TK.propose(bare, 1, TASKS)))
    iss = TK.FakeIssue(TK.spec_body())
    check("why 빈칸 거절", "why" in _err(lambda: PP.propose(1, TASKS, [], " ", getter=iss.get, noter=iss.note)))
    check("상태 실음 거절", "전이 도구로만" in _err(lambda: TK.propose(iss, 1, [{"id": "T1", "goal": "g", "state": "완료"}])))
    check("없는 선행 거절(형식 판정)", "선행" in _err(lambda: TK.propose(iss, 1, [{"id": "T1", "goal": "g", "deps": ["T9"]}])))
    check("빈 체크리스트 항목 거절", "비었다" in _err(lambda: TK.propose(iss, 1, TASKS, checklist=["  "])))
    check("자율성 범위 밖 거절", "autonomy" in _err(lambda: TK.propose(iss, 1, TASKS, autonomy=2)))
    check("거절은 노트를 안 쓴다", iss.journals == [])


def test_set_requires_proposal_and_consent():
    iss = TK.FakeIssue(TK.spec_body())
    check("제안 없음 거절", "플랜 제안이 없다" in _err(lambda: _set(iss)))
    TK.propose(iss, 1, TASKS, checklist=["c"])
    check("사용자 답 빈칸 거절", "사용자 답이 비었다" in _err(lambda: _set(iss, answer=" ")))
    other = TASKS[:1]
    check("제안과 다른 목록 거절", "최신 제안과 다른 목록" in _err(lambda: _set(iss, tasks=other)))
    changed = [dict(TASKS[0], goal="읽기(바꿈)"), TASKS[1]]
    msg = _err(lambda: _set(iss, tasks=changed))
    check("내용이 다른 태스크를 짚는다", "처음 다른 태스크 T1" in msg, msg)
    check("거절은 본문을 안 바꾼다", PB.parse(iss.body) is None)
    out = _set(iss)
    plan = PB.parse(iss.body)
    check("제안대로 등록", out["ok"] and out["created"] and plan.version == 3
          and [c.item for c in plan.checklist] == ["c"] and plan.autonomy == 0.5, str(plan))
    check("노트에 동의 원문", "사용자 동의: 동의" in iss.notes[-1])


def test_latest_proposal_wins():
    iss = TK.FakeIssue(TK.spec_body())
    TK.propose(iss, 1, TASKS)
    TK.propose(iss, 1, TASKS[:1], checklist=["두 번째"], autonomy=0.8)
    check("옛 제안 목록은 거절", "최신 제안과 다른 목록" in _err(lambda: _set(iss)))
    _set(iss, tasks=TASKS[:1])
    plan = PB.parse(iss.body)
    check("최신 제안 기준 등록", [t.id for t in plan.tasks] == ["T1"] and plan.autonomy == 0.8
          and plan.checklist[0].item == "두 번째", str(plan))


def test_edit_after_flow_needs_new_proposal_and_keeps_states():
    iss = TK.issue_with_plan(TASKS, checklist=["c1"])
    PT.transition(1, "T1", "작업중", getter=iss.get, updater=iss.update)
    more = TASKS + [{"id": "T3", "goal": "더"}]
    check("제안 흐름 일감의 편집도 제안 필요", "최신 제안과 다른 목록" in _err(lambda: _set(iss, tasks=more)))
    TK.register(iss, 1, more, checklist=["c1", "c2"])
    plan = PB.parse(iss.body)
    check("편집 뒤 상태 보존", plan.task("T1").state == "작업중" and plan.task("T3").state == "대기")
    check("체크리스트 갱신(C2 추가 · C1 유지)", [(c.id, c.state) for c in plan.checklist]
          == [("C1", "미확인"), ("C2", "미확인")], str(plan.checklist))


def test_legacy_plan_edit_unchanged():
    legacy = TK.FakeIssue(PB.append(TK.BARE, [PB.Task("T1", "대기", "옛 목표")]))
    out = PT.set_plan(1, [{"id": "T1", "goal": "옛 목표(고침)"}], "옛 편집", getter=legacy.get, updater=legacy.update)
    plan = PB.parse(legacy.body)
    check("제안 노트 없는 옛 플랜 편집은 지금처럼", out["ok"] and plan.version == 2 and plan.task("T1").goal
          == "옛 목표(고침)", str(out))


def test_broken_latest_proposal():
    iss = TK.FakeIssue(TK.spec_body(), notes=[PP.MARK + "\n깨진 제안\n```json\n{oops\n```"])
    check("깨진 최신 제안 거절", "JSON 이 깨졌다" in _err(lambda: _set(iss)))


def main() -> int:
    for fn in (test_propose_records_note, test_propose_refusals, test_set_requires_proposal_and_consent,
               test_latest_proposal_wins, test_edit_after_flow_needs_new_proposal_and_keeps_states,
               test_legacy_plan_edit_unchanged, test_broken_latest_proposal):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_proposal: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
