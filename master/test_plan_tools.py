"""플랜 도구(`#826` T5) 계약 테스트 — [중요] **상태는 transition 으로만 바뀌는가,
쓰기 실패를 성공으로 보고하지 않는가.**

실 Redmine 을 두드리지 않는다 — getter/updater 주입.
실행: python3 master/test_plan_tools.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB    # noqa: E402
from master import plan_tools as PT    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class FakeIssue:
    """Redmine 이슈 하나 — 본문을 CRLF 로 저장한다(실측과 같다)."""

    def __init__(self, body: str, answer: str = ""):
        self.body = body.replace("\n", "\r\n")
        self.writes: list = []
        self.answer = answer

    def get(self, iid):
        return {"id": iid, "subject": "제목", "description": self.body}

    def update(self, iid, *, description, notes):
        self.writes.append((description, notes))
        if self.answer:
            return self.answer
        self.body = description
        return f"레드마인 #{iid} 갱신 (notes, description)"


SPEC = "## 스펙\n\n요구와 완료 조건\n"


def _err(fn) -> str:
    try:
        fn()
    except PB.PlanError as e:
        return str(e)
    return ""


def _tasks():
    return [{"id": "T1", "goal": "읽기", "target": "a.py", "check": "단위"},
            {"id": "T2", "goal": "쓰기", "deps": ["T1"], "check": "왕복"}]


def test_set_creates_plan():
    iss = FakeIssue(SPEC)
    out = PT.set_plan(852, _tasks(), "파일럿 플랜", getter=iss.get, updater=iss.update)
    check("등록 성공", out["ok"] and out["created"] and out["added"] == ["T1", "T2"], str(out))
    plan = PB.parse(iss.body)
    check("새 태스크는 대기", all(t.state == "대기" for t in plan.tasks))
    check("스펙은 그대로 앞에 남는다", iss.body.startswith(SPEC.replace("\n", "\r\n").rstrip("\r\n")))
    check("노트에 사유가 남는다", "파일럿 플랜" in iss.writes[-1][1], iss.writes[-1][1])
    check("CRLF 본문에 LF 단독 줄을 섞지 않는다", "\n" not in iss.body.replace("\r\n", ""))


def test_set_keeps_states_and_evidence():
    iss = FakeIssue(SPEC)
    PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update)
    PT.transition(1, "T1", "작업중", getter=iss.get, updater=iss.update)
    PT.transition(1, "T1", "완료", "abc123", getter=iss.get, updater=iss.update)
    edited = _tasks() + [{"id": "T3", "goal": "새 일", "deps": "T1·T2"}]
    edited[0]["goal"] = "읽기(고친 목표)"
    out = PT.set_plan(1, edited, "T3 추가", getter=iss.get, updater=iss.update)
    plan = PB.parse(iss.body)
    check("추가만 보고한다", out["added"] == ["T3"] and not out["removed"], str(out))
    check("완료 상태·근거를 유지한다",
          plan.task("T1").state == "완료" and plan.task("T1").evidence == "abc123", str(plan.task("T1")))
    check("목표 편집은 반영된다", plan.task("T1").goal == "읽기(고친 목표)")
    check("문자열 선행도 읽는다", plan.task("T3").deps == ["T1", "T2"])


def test_set_refuses_state_and_bad_input():
    iss = FakeIssue(SPEC)
    for bad in ([{"id": "T1", "goal": "x", "state": "완료"}],
                [{"id": "T1", "goal": "x", "evidence": "abc"}]):
        check(f"{list(bad[0])[-1]} 를 실으면 거절",
              "plan_transition" in _err(lambda b=bad: PT.set_plan(1, b, "x", getter=iss.get,
                                                                   updater=iss.update)))
    check("why 없으면 거절", "why" in _err(lambda: PT.set_plan(1, _tasks(), " ", getter=iss.get,
                                                                updater=iss.update)))
    check("빈 목록 거절", "비었다" in _err(lambda: PT.set_plan(1, [], "x", getter=iss.get,
                                                           updater=iss.update)))
    check("goal 없는 항목 거절", "필수" in _err(lambda: PT.set_plan(1, [{"id": "T1"}], "x",
                                                                getter=iss.get, updater=iss.update)))
    check("없는 선행 거절", "선행" in _err(lambda: PT.set_plan(
        1, [{"id": "T1", "goal": "x", "deps": ["T9"]}], "x", getter=iss.get, updater=iss.update)))
    check("거절된 호출은 아무것도 쓰지 않는다", iss.writes == [], str(iss.writes))


def test_set_cannot_drop_started_task():
    iss = FakeIssue(SPEC)
    PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update)
    PT.transition(1, "T1", "작업중", getter=iss.get, updater=iss.update)
    n = len(iss.writes)
    check("작업중 태스크 제거 거절", "T1" in _err(lambda: PT.set_plan(
        1, [_tasks()[1] | {"deps": []}], "정리", getter=iss.get, updater=iss.update)))
    check("거절 뒤 쓰기 없음", len(iss.writes) == n)
    out = PT.set_plan(1, [_tasks()[0]], "T2 빼기", getter=iss.get, updater=iss.update)
    check("대기 태스크는 뺄 수 있다", out["removed"] == ["T2"], str(out))


def test_transition_writes_and_reports_next():
    iss = FakeIssue(SPEC)
    PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update)
    out = PT.transition(1, "T1", "작업중", getter=iss.get, updater=iss.update)
    check("전이 결과", out["from"] == "대기" and out["to"] == "작업중", str(out))
    check("다음 판정은 resume T1", out["next"]["verdict"] == "resume" and out["next"]["tasks"] == ["T1"])
    out = PT.transition(1, "T1", "완료", "abc · 검사 OK", getter=iss.get, updater=iss.update)
    check("노트에 전이와 근거가 남는다", "T1: 작업중 → 완료" in iss.writes[-1][1]
          and "abc" in iss.writes[-1][1], iss.writes[-1][1])
    check("다음 판정은 next T2", out["next"]["verdict"] == "next" and out["next"]["tasks"] == ["T2"])


def test_transition_refusals_do_not_write():
    iss = FakeIssue(SPEC)
    check("플랜 없는 일감 거절", "plan_set" in _err(lambda: PT.transition(1, "T1", "작업중",
                                                                     getter=iss.get, updater=iss.update)))
    PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update)
    n = len(iss.writes)
    check("근거 없는 완료 거절(T2 규칙 그대로)", bool(_err(lambda: PT.transition(
        1, "T1", "완료", getter=iss.get, updater=iss.update))))
    check("선행 미완료 착수 거절", "T1" in _err(lambda: PT.transition(
        1, "T2", "작업중", getter=iss.get, updater=iss.update)))
    check("거절 뒤 쓰기 없음", len(iss.writes) == n)


def test_write_failure_is_not_success():
    iss = FakeIssue(SPEC, answer="[주의] 레드마인 #1 갱신 실패 — HTTP 422")
    msg = _err(lambda: PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update))
    check("[주의] 응답은 실패로 올린다", "HTTP 422" in msg, msg)


def test_read_failure():
    msg = _err(lambda: PT.set_plan(9, _tasks(), "x", getter=lambda i: {"error": "#9 없음 (404)"},
                                   updater=lambda *a, **k: "x"))
    check("읽기 실패는 사유와 함께 거절", "404" in msg, msg)


def test_start_adds_steps():
    iss = FakeIssue(SPEC)
    out = PT.start(1, getter=iss.get, kind_of=lambda p: "code", active=lambda: "AXCluster")
    check("판정 plan_needed", out["verdict"] == "plan_needed" and not out["ok"], str(out))
    check("마운트 프로젝트를 쓴다", out["project"] == "AXCluster")
    check("7단계 표를 싣는다", len(out["steps"]) == 7 and out["steps"][1]["applies"] == "해당없음")
    out = PT.start(1, getter=iss.get, kind_of=lambda p: "", active=lambda: "X")
    check("모르는 kind 는 steps_error 로 말한다", out["steps"] == [] and "unreal" in out["steps_error"])
    out = PT.start(1, getter=lambda i: {"error": "없음"}, kind_of=lambda p: "code", active=lambda: "A")
    check("읽기 실패는 ok false", out["ok"] is False and "error" in out, str(out))


def main() -> int:
    for fn in (test_set_creates_plan,
               test_set_keeps_states_and_evidence,
               test_set_refuses_state_and_bad_input,
               test_set_cannot_drop_started_task,
               test_transition_writes_and_reports_next,
               test_transition_refusals_do_not_write,
               test_write_failure_is_not_success,
               test_read_failure,
               test_start_adds_steps):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_tools: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
