"""플랜 도구(`#826` T5) 계약 테스트 — [중요] **상태는 transition 으로만 바뀌는가,
쓰기 실패를 성공으로 보고하지 않는가.**

실 Redmine 을 두드리지 않는다 — getter/updater 주입.
실행: python3 master/test_plan_tools.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB    # noqa: E402
from master import plan_tools as PT    # noqa: E402
from master import plan_start as ST    # noqa: E402
from master import issue_lock as IL    # noqa: E402

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


def test_set_reports_spec_missing():
    """#939 — 플랜 등록 응답에 스펙 누락 경고를 싣는다. 등록은 막지 않는다."""
    keys = [k for k, _ in ST.SPEC_SECTIONS]
    iss = FakeIssue(SPEC)
    out = PT.set_plan(939, _tasks(), "등록", getter=iss.get, updater=iss.update)
    check("스펙 항목이 없어도 등록은 된다", out["ok"] and PB.parse(iss.body) is not None, str(out))
    check("빠진 항목 전부를 경고로 싣는다", out.get("spec_missing") == keys, str(out.get("spec_missing")))
    full = "".join(f"## {h}\n내용\n" for h in ("문제·맥락", "초반 분류", "관측 결과", "범위·비범위",
                                                  "완료 조건", "열린 결정"))
    iss = FakeIssue(full)
    out = PT.set_plan(939, _tasks(), "등록", getter=iss.get, updater=iss.update)
    check("6항목 본문 → 빈 목록", out.get("spec_missing") == [], str(out.get("spec_missing")))
    out = PT.set_plan(939, _tasks() + [{"id": "T3", "goal": "더"}], "갱신", getter=iss.get, updater=iss.update)
    check("갱신(플랜 영역 있음)에서도 플랜 안은 세지 않는다", out.get("spec_missing") == [], str(out))


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


def test_set_steps_v2():
    iss = FakeIssue(SPEC)
    tasks = [{"id": "T1", "goal": "클래스 추가", "steps": [4]},
             {"id": "T2", "goal": "어셋", "steps": "6·2", "deps": ["T1"]}]
    PT.set_plan(1, tasks, "단계 선언", getter=iss.get, updater=iss.update)
    plan = PB.parse(iss.body)
    check("단계 선언이 v2 로 들어간다", plan.version == 2 and plan.task("T1").steps == [4]
          and plan.task("T2").steps == [2, 6], str(plan))
    check("범위 밖 단계 거절", bool(_err(lambda: PT.set_plan(
        1, [{"id": "T1", "goal": "x", "steps": [8]}], "x", getter=iss.get, updater=iss.update))))


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


# #905 의 실제 완료 근거(2026-11-08 Redmine 원문) — #908 의 계기
EV905 = {
    "T1": "구현 편집 완료: /home/sim/ax-issues/905의 master/issue_flow.py 및 신규 master/issue_worktree.py. "
          "start·재개·보류·취소가 운영 main을 유지하고 영속 /home/sim/ax-issues/N 경로를 사용하도록 변경. "
          "사용자 지시로 검사·테스트·코드 실행 미실시, 미커밋·미배포.",
    "T2": "master/issue_flow.py finish 편집 완료. 운영 main과 일감 worktree 분리, push→운영 main FF→일감 경로 "
          "detach 보존→branch -d→기존 마감 기록 순서. 사용자 지시로 검사·테스트 미실시, 미커밋·미배포.",
    "T3": "구현·안내·기록 편집 완료. 격리 작업본의 변경 7파일: issue_flow.py, 인수인계서, 리포트141. "
          "검사·테스트·실증 미실행, 미커밋·미배포·미설치·미재기동.",
    "T4": "커밋 6a0a2013f39e1cdfff806906026b59a450a381af를 main에 push·운영 main FF 반영. 드라이런·검사·테스트 미실행.",
}


def test_evidence_warning_judgement():
    """#908 — 판정 함수. 경고만 하므로 오탐보다 놓침이 문제다: #905 넷은 전부 걸려야 한다."""
    for tid, ev in EV905.items():
        check(f"#905 {tid} 원문 → 경고", PT.evidence_warning(ev).startswith("[주의]"), ev[:40])
    check("미실시 어휘는 그 구절을 사유에 싣는다", "미실시" in PT.evidence_warning(EV905["T1"]))
    for ev in ("커밋 abc1234 · test 3/3 rc0 · 커밋·push·마감 미실행(승인 대기)",
               "test 12/12 · 재기동 미승인·미실행",
               "test 5/5 · 언리얼 드라이런은 미실행",
               "test 19/19 · 임시 Git 조건은 운영 실증으로 주장하지 않는다"):
        check(f"검사가 아닌 것의 미실행은 경고 안 함 ({ev[-14:]})", PT.evidence_warning(ev) == "",
              PT.evidence_warning(ev))
    for ev in ("커밋 6e46635 — test_plan_start 44/44 rc0",
               "abc1234 push",
               "test_x 12/12 통과",
               "공식 통합 Ran 199 OK",
               "reports/189 작성 · 실물 확인",
               "드라이런 쓰기 0 · 응답 확인"):
        check(f"표지 있는 근거 → 경고 없음 ({ev[:20]})", PT.evidence_warning(ev) == "", PT.evidence_warning(ev))
    check("「검사를 실행하지 않았다」도 잡는다", PT.evidence_warning("abc1234 · 검사는 실행하지 않았다").startswith("[주의]"))
    # #961 — 해시·검사 수치가 있어도 명시된 「검사 실행 안 함」을 놓치지 않는다.
    for ev in ("검사 실행 안 함", "커밋 abc1234 · 검사 실행 안 함",
               "test 3/3 rc0 · 검사 실행 안 함"):
        check(f"검사 실행 안 함 → 미실행 경고 ({ev})",
              "검사 실행 안 함」" in PT.evidence_warning(ev), PT.evidence_warning(ev))
    check("검사 결과 뒤 커밋 안 함은 미실행으로 보지 않는다",
          PT.evidence_warning("검사 3/3 rc0 · 커밋 안 함") == "")
    for ev in ("T1 완료: 인터페이스 설계 확정", "구현 완료", ""):
        check(f"표지 없음 → 경고 ({ev or '빈 문자열'})",
              "표지가 없다" in PT.evidence_warning(ev), PT.evidence_warning(ev))


def test_transition_evidence_warning_is_warning_only():
    """#908 — [중요] 경고만: 전이·본문은 경고 유무와 무관하고, 노트와 응답에만 실린다."""
    iss = FakeIssue(SPEC)
    PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update)
    PT.transition(1, "T1", "작업중", getter=iss.get, updater=iss.update)
    out = PT.transition(1, "T1", "완료", EV905["T1"], getter=iss.get, updater=iss.update)
    t1 = PB.parse(iss.body).task("T1")
    check("빈약한 근거도 완료로 전이된다", out["ok"] and t1.state == "완료", str(out))
    check("근거 칸은 원문 그대로(경고를 섞지 않는다)", t1.evidence == EV905["T1"].strip(), t1.evidence)
    check("응답에 evidence_warning", out.get("evidence_warning", "").startswith("[주의]"), str(out))
    check("Redmine 노트 끝에 경고 줄", iss.writes[-1][1].rstrip().endswith("(#908)"), iss.writes[-1][1])
    PT.transition(1, "T2", "작업중", getter=iss.get, updater=iss.update)
    out = PT.transition(1, "T2", "완료", "커밋 6e46635 · test 3/3 rc0", getter=iss.get, updater=iss.update)
    check("좋은 근거 → 응답에 키 없음", "evidence_warning" not in out, str(out))
    check("좋은 근거 → 노트에 경고 없음", "#908" not in iss.writes[-1][1], iss.writes[-1][1])
    iss = FakeIssue(SPEC)
    PT.set_plan(2, _tasks(), "등록", getter=iss.get, updater=iss.update)
    out = PT.transition(2, "T1", "해당없음", "범위 밖", getter=iss.get, updater=iss.update)
    check("완료가 아닌 전이는 판정하지 않는다", "evidence_warning" not in out, str(out))


def test_transition_not_run_phrase():
    """#961 — 재현 입력이 기존 경고 응답·노트로 연결되고 근거 원문은 보존된다."""
    iss = FakeIssue(SPEC)
    PT.set_plan(1, _tasks(), "등록", getter=iss.get, updater=iss.update)
    PT.transition(1, "T1", "작업중", getter=iss.get, updater=iss.update)
    note = "커밋 abc1234 · 검사 실행 안 함"
    out = PT.transition(1, "T1", "완료", note, getter=iss.get, updater=iss.update)
    task = PB.parse(iss.body).task("T1")
    warning = out.get("evidence_warning", "")
    check("재현 입력 → 기존 미실행 경고 응답", "검사 실행 안 함」" in warning, str(out))
    check("재현 입력 → 노트에 동일 경고", bool(warning) and iss.writes[-1][1].endswith(warning))
    check("재현 입력 → 완료 유지", out["ok"] and task.state == "완료")
    check("재현 입력 → 근거 원문 보존", task.evidence == note, task.evidence)


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


def test_transition_lock_gate():
    """`#883` — 다른 일감이 활성이면 작업중 전이를 거절한다(lock_root 는 늘 임시)."""
    with tempfile.TemporaryDirectory() as d:
        lk = Path(d)
        iss = FakeIssue(SPEC)
        PT.set_plan(5, _tasks(), "등록", getter=iss.get, updater=iss.update)
        IL.acquire(lk, 9, branch="issue/9", start_rev="r")
        n = len(iss.writes)
        msg = _err(lambda: PT.transition(5, "T1", "작업중", getter=iss.get, updater=iss.update, lock_root=lk))
        check("잠금 — 비보유 일감 작업중 거절 · 보유자 이름", "#9" in msg and "하나씩" in msg, msg)
        check("잠금 — 거절 뒤 쓰기 없음", len(iss.writes) == n)
        check("잠금 — 작업중 아닌 전이는 막지 않는다(해당없음)", PT.transition(
            5, "T2", "해당없음", "안 함", getter=iss.get, updater=iss.update, lock_root=lk)["ok"])
        # 보유자 자신은 된다
        own = FakeIssue(SPEC)
        PT.set_plan(9, _tasks(), "등록", getter=own.get, updater=own.update)
        out = PT.transition(9, "T1", "작업중", getter=own.get, updater=own.update, lock_root=lk)
        check("잠금 — 보유 일감은 허용 · 알림 없음", out["ok"] and "lock_note" not in out, str(out))
        # 보류 중 일감: 누가 활성이면 거절, 비어 있으면 허용 + 알림
        IL.pause(lk, 9)
        IL.acquire(lk, 5, branch="issue/5", start_rev="r")
        p9 = FakeIssue(SPEC)
        PT.set_plan(9, _tasks(), "등록", getter=p9.get, updater=p9.update)
        msg = _err(lambda: PT.transition(9, "T1", "작업중", getter=p9.get, updater=p9.update, lock_root=lk))
        check("잠금 — 보류 일감도 다른 활성 있으면 거절", "#5" in msg and "보류 중인" in msg, msg)
        IL.release(lk, 5, op="cancel")
        out = PT.transition(9, "T1", "작업중", getter=p9.get, updater=p9.update, lock_root=lk)
        check("잠금 — 빈 자리면 보류 일감 허용 · issue_start 안내", out["ok"]
              and "issue_start" in out.get("lock_note", ""), str(out))
        # 주입 + lock_root 없음 → 검사 건너뜀(운영 잠금 안 읽음)
        IL.acquire(lk, 77, branch="issue/77", start_rev="r")
        orig = IL.default_root
        IL.default_root = lambda *a, **k: (_ for _ in ()).throw(AssertionError("운영 잠금을 읽었다"))
        try:
            f = FakeIssue(SPEC)
            PT.set_plan(6, _tasks(), "등록", getter=f.get, updater=f.update)
            out = PT.transition(6, "T1", "작업중", getter=f.get, updater=f.update)
        finally:
            IL.default_root = orig
        check("잠금 — 주입 대역 + lock_root 없음 → 건너뜀", out["ok"], str(out))
        # 깨진 잠금 → 전송 실패로 거절
        IL.state_path(lk).write_text("{깨짐")
        try:
            PT.transition(6, "T2", "작업중", getter=f.get, updater=f.update, lock_root=lk)
            e = None
        except PB.PlanError as x:
            e = x
        check("잠금 — 못 읽으면 PlanTransportError", isinstance(e, PT.PlanTransportError), repr(e))


def main() -> int:
    for fn in (test_evidence_warning_judgement,
               test_transition_evidence_warning_is_warning_only,
               test_transition_not_run_phrase,
               test_set_reports_spec_missing,
               test_set_creates_plan,
               test_set_keeps_states_and_evidence,
               test_set_steps_v2,
               test_set_refuses_state_and_bad_input,
               test_set_cannot_drop_started_task,
               test_transition_writes_and_reports_next,
               test_transition_refusals_do_not_write,
               test_write_failure_is_not_success,
               test_read_failure,
               test_start_adds_steps,
               test_transition_lock_gate):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_tools: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
