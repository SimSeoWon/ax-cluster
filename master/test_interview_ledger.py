"""대화 장부(`#1040`·`#1051`) 계약 테스트 — 실제 문답의 원문·세션과 LLM의 해석을 대조하고,
확정·후속 질문·중단을 구분하는지 확인한다.

임시 디렉토리만 쓴다 — 실 트윈 루트·Redmine 을 건드리지 않는다.
실행: .venv/bin/python master/test_interview_ledger.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import interview_ledger as L    # noqa: E402

PASS = FAIL = 0
ANS_2215 = "진행을 해야 고친 버그 실증 테스트를 하던지 뭘 하던지 하지 씨발 죄송하다 안했습니다 듣고 싶은게 아니라고"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def refused(fn, *a, **kw) -> str:
    try:
        fn(*a, **kw)
    except L.LedgerError as e:
        return str(e)
    return ""


def prompt(root, text):
    return L.record_prompt(root, text, session="codex", source="test")["id"]


def t_ask_rules(root):
    ok = L.ask(root, 7, "classify", "버그인가?", "버그", ["수정", "둘로"], 60, "재현 여부")
    check("질문 등록", ok["ok"] and ok["confidence"] == 60 and ok["alternatives"] == ["수정", "둘로"], str(ok))
    check("추천 누락 거절", "추천" in refused(L.ask, root, 7, "classify", "q", " ", [], 50, "g"))
    check("대안 4개 거절", "3개" in refused(L.ask, root, 7, "classify", "q", "r", ["a", "b", "c", "d"], 90))
    check("확신도 범위 거절", "0~100" in refused(L.ask, root, 7, "classify", "q", "r", [], 101))
    check("확신도 bool 거절", "0~100" in refused(L.ask, root, 7, "classify", "q", "r", [], True))
    check("낮은 확신도 빈 것 필수", "gaps" in refused(L.ask, root, 7, "classify", "q", "r", [], 30))
    check("모르는 단계 거절", "모르는 단계" in refused(L.ask, root, 7, "nope", "q", "r", [], 90))
    L.ask(root, 7, "classify", "다시 묻기", "버그", [], 80)
    qs = L.open_questions(root, 7)
    check("앞 질문은 대체된다", len(qs) == 1 and qs[0]["question"] == "다시 묻기", str(qs))


def t_no_question(root):
    answer = "1번"
    why = refused(L.assess_answer, root, 8, "classify", answer, prompt_id=prompt(root, answer),
                  action=L.CONFIRM, divergence=L.NONE, divergence_reason="추천 선택", option=1)
    check("질문 미등록 거절", "등록된 질문이 없다" in why, why)


def t_session_answers(root):
    for issue, text in ((1050, "응 신규 기능이야"), (1051, "1")):
        start = L.record_prompt(root, "P4 진행해", session="codex")["id"]
        question = L.ask(root, issue, "classify", "어느 분류로 진행할까요?", "신규 기능",
                         ["기존 기능 수정"], 90, prompt_id=start, require_prompt=True)
        other = L.record_prompt(root, text, session="claude")["id"]
        decision = dict(action=L.CONFIRM, divergence=L.NONE, divergence_reason="신규 기능 선택", option=1)
        why = refused(L.assess_answer, root, issue, "classify", text, prompt_id=other, **decision)
        check("다른 세션의 동일 원문 거절", "같은 세션" in why, why)
        current = L.record_prompt(root, text, session="codex")["id"]
        why = refused(L.assess_answer, root, issue, "classify", text + " ", prompt_id=current, **decision)
        check("호출 원문 불일치 거절", "원문" in why, why)
        got = L.assess_answer(root, issue, "classify", text, prompt_id=current, **decision)
        check("질문 맥락으로 내린 동의 판정을 기록", got["status"] == "answered"
              and got["user_answer"] == text and got["question_id"] == question["id"], str(got))
    why = refused(L.ask, root, 1050, "classify", "q", "r", confidence=90, require_prompt=True)
    check("질문 등록에 현재 턴 입력 ID를 요구", "prompt_id" in why, why)
    why = refused(L.ask, root, 1050, "classify", "q", "r", confidence=90, prompt_id=start)
    check("지나간 턴 입력 ID는 재사용할 수 없다", "현재 사용자 입력" in why, why)


def t_fabricated_answer(root):
    asked_by = prompt(root, "응")
    L.ask(root, 9, "classify", "q", "버그", ["수정"], 80, prompt_id=asked_by)
    decision = dict(action=L.CONFIRM, divergence=L.NONE, divergence_reason="추천 선택", option=1)
    why = refused(L.assess_answer, root, 9, "classify", "응", prompt_id=asked_by, **decision)
    check("질문 전 입력은 답변으로 쓸 수 없다", "답변보다 먼저 등록된 질문" in why, why)
    answer_id = prompt(root, "1번으로 가자")
    why = refused(L.assess_answer, root, 9, "classify", "1번으로 가자요", prompt_id=answer_id, **decision)
    check("원문이 다르면 거절", "원문" in why, why)


def t_unrelated_answer(root):
    """기준선 재현 R1 — #1037 22:15 답 원문은 승인으로 기록되지 않는다."""
    L.ask(root, 1037, "classify", "신규 기능으로 볼까?", "신규 기능", ["수정"], 60, "분류 근거",
          prompt_id=prompt(root, "1037 진행"))
    decision = dict(prompt_id=prompt(root, ANS_2215), action=L.FOLLOWUP, divergence=L.FLIP,
                    divergence_reason="분류 질문에 답하지 않고 다른 작업을 지시")
    got = L.assess_answer(root, 1037, "classify", ANS_2215, **decision)
    check("22:15 원문 → 후속 질문 필요, 원문 보존", got["ok"] and got["status"] == "followup_required"
          and got["user_answer"] == ANS_2215 and "60 → 0" in got["note_line"], str(got))
    why = refused(L.assess_answer, root, 1037, "classify", ANS_2215, **decision)
    check("후속 질문 필요로 기록한 답을 확정에 재사용할 수 없다", "등록된 질문이 없다" in why, why)


def t_choices_and_confidence(root):
    L.ask(root, 10, "specify", "이대로?", "확정", ["입력 장부 제외", "①④만"], 60, "범위",
          prompt_id=prompt(root, "이어서"))
    answer = "그대로 확정하자"
    got = L.assess_answer(root, 10, "specify", answer, prompt_id=prompt(root, answer), action=L.CONFIRM,
                          divergence=L.NONE, divergence_reason="공개된 추천 내용에 동의", option=1)
    check("추천 선택 → 확신도 상승 및 판단 근거", got["status"] == "answered" and got["pick"] == 1
          and "60 → 80" in got["note_line"] and "공개된 추천 내용에 동의" in got["note_line"], str(got))

    L.ask(root, 10, "impact", "어느 방안?", "등록 워커 전부", ["마스터만", "마스터와 .33"], 70,
          prompt_id=prompt(root, "범위 정하자"))
    answer = "마스터로만 가자"
    choice = dict(prompt_id=prompt(root, answer), action=L.CONFIRM, divergence_reason="대안의 마스터만 선택")
    why = refused(L.assess_answer, root, 10, "impact", answer, **choice, divergence=L.REVISE, option=4)
    check("등록된 보기를 벗어난 선택 번호 거절", "보기 범위" in why, why)
    why = refused(L.assess_answer, root, 10, "impact", answer, **choice, divergence=L.NONE, option=2)
    check("다른 보기에 어긋남 없음 → 거절", "차이를 기록" in why, why)
    got = L.assess_answer(root, 10, "impact", answer, **choice, divergence=L.REVISE, option=2)
    check("자연어 대안 선택은 확인 상태로 기록", got["status"] == "answered" and got["pick"] == 2
          and got["user_answer"] == answer and "70 → 35" in got["note_line"], str(got))

    L.ask(root, 10, "plan", "q", "r", [], 90, prompt_id=prompt(root, "플랜 보자"))
    answer = "그걸로 가자. 근데 로그도 남겨"
    decision = dict(prompt_id=prompt(root, answer), action=L.FOLLOWUP, divergence_reason="로그 요구 추가", option=1)
    why = refused(L.assess_answer, root, 10, "plan", answer, **decision, divergence="")
    check("등급 누락 거절", "divergence" in why, why)
    got = L.assess_answer(root, 10, "plan", answer, **decision, divergence=L.ADD)
    check("추천 + 보탬 → 후속 질문 필요 및 확신도 감소", got["status"] == "followup_required"
          and "90 → 80" in got["note_line"] and "보강" in got["note_line"], str(got))


def t_open_questions(root):
    L.ask(root, 11, "decision", "어떻게?", "A", [], 90)
    check("답 대기 질문", [q["issue_id"] for q in L.open_questions(root, 11)] == [11])
    L.record_prompt(root, "A로")
    check("입력이 들어오면 대기 아님", L.open_questions(root, 11) == [])


def t_gate_switch():
    class R:
        active = "AXCluster"

        def __init__(self, raw):
            self.raw = raw

        def config_of(self, _):
            return self

    check("관문 기본 꺼짐", L.gate_enabled(registry=R({})) is False)
    check("관문 enforce", L.gate_enabled(registry=R({"interview_gate": "enforce"})) is True)


def t_record_gate(root):
    """T3 — 실 `interview.record` 가 관문을 거친다(가짜 Redmine · 임시 장부)."""
    from master import interview as IV
    notes = []

    def getter(_):
        return {"description": "## 문제·맥락\n시험", "journals": [{"notes": n} for n in notes]}

    def noter(_, text):
        notes.append(text)
        return "ok"

    kw = dict(category="bug", getter=getter, noter=noter, ledger_root=root, gate=True)

    def refused_iv(*a, **k):
        try:
            IV.record(*a, **k)
        except IV.InterviewError as e:
            return str(e)
        return ""

    answer = "응"
    why = refused_iv(1037, "classify", "버그로 예측", answer, divergence=L.NONE,
                     divergence_reason="추천에 동의", **kw,
                     answer_context={"prompt_id": prompt(root, answer), "action": L.CONFIRM, "option": 1})
    check("[중요] 관문 켬 — 질문 없이 분류 기록 거절", "등록된 질문이 없다" in why and not notes, why)
    L.ask(root, 1037, "classify", "버그인가?", "버그", ["수정"], 60, "재현 여부",
          prompt_id=prompt(root, "1037 진행"))
    answer_id = prompt(root, ANS_2215)
    got = IV.record(1037, "classify", "버그로 예측", ANS_2215, divergence=L.FLIP, divergence_reason="딴 지시", **kw,
                    answer_context={"prompt_id": answer_id, "action": L.FOLLOWUP})
    check("[중요] 관문 켬 — 22:15 원문은 후속 질문 필요·노트 0", got["ok"]
          and got["status"] == "followup_required" and got["next"] == "classify" and got["written"] == []
          and got["user_answer"] == ANS_2215 and not notes, str(got))
    L.ask(root, 1037, "classify", "실증은 다음 단계에 넣고 지금은 버그로 분류할까요?", "버그", ["수정"],
          50, "재현 여부", prompt_id=answer_id)
    answer = "실증도 하고 버그로 가자"
    got = IV.record(1037, "classify", "버그로 예측", answer, divergence=L.NONE, **kw,
                    divergence_reason="분류 질문에서 버그를 선택",
                    answer_context={"prompt_id": prompt(root, answer), "action": L.CONFIRM, "option": 1})
    check("관문 켬 — 실제 답이면 기록 + 노트에 확신도", got["ok"] and "## 확신도" in notes[-1]
          and "50 → 70" in notes[-1] and answer in notes[-1], notes[-1][-120:])

    got = IV.record(1038, "classify", "버그", "응", category="bug", getter=getter, noter=noter, ledger_root=root)
    check("[중요] 가짜 getter + gate 미지정 → 관문 꺼짐(실 설정을 읽지 않는다)", got["ok"], str(got)[:200])


def t_set_plan_gate(root):
    """T3 — 실 `set_plan`(제안 흐름) 이 동의 답을 판정한다."""
    from master import plan_tools as PT
    from master import testkit_issue as TK
    tasks = [{"id": "T1", "goal": "g"}]
    iss = TK.FakeIssue(TK.spec_body())
    TK.propose(iss, 5, tasks)
    kw = dict(getter=iss.get, updater=iss.update, ledger_root=root, gate=True)
    answer = "1번으로 등록하자"
    try:
        PT.set_plan(5, tasks, "등록", user_answer=answer, divergence=L.NONE, divergence_reason="플랜 동의", **kw,
                    answer_context={"prompt_id": prompt(root, answer), "action": L.CONFIRM, "option": 1})
        why = ""
    except PT.PlanToolError as e:
        why = str(e)
    check("[중요] 플랜 등록 — 질문 없으면 거절", "등록된 질문이 없다" in why, why)
    L.ask(root, 5, "plan", "이 플랜 등록?", "등록", ["자율성 변경"], 80, prompt_id=prompt(root, "플랜 확인"))
    writes = len(iss.writes)
    answer = "검증도 같이 적어줘"
    answer_id = prompt(root, answer)
    got = PT.set_plan(5, tasks, "등록", user_answer=answer, divergence=L.ADD, divergence_reason="검증 계획 보강", **kw,
                      answer_context={"prompt_id": answer_id, "action": L.FOLLOWUP})
    check("플랜 보강 의견 — 후속 질문 필요, 본문과 노트 무변경", got["ok"] and got["status"] == "followup_required"
          and got["next"] == "plan" and len(iss.writes) == writes, str(got))
    L.ask(root, 5, "plan", "검증 내용을 함께 적은 플랜을 등록할까요?", "등록", [], 80, prompt_id=answer_id)
    answer = "그렇게 등록하자"
    got = PT.set_plan(5, tasks, "등록", user_answer=answer, divergence=L.NONE, divergence_reason="보강안 동의", **kw,
                      answer_context={"prompt_id": prompt(root, answer), "action": L.CONFIRM, "option": 1})
    check("플랜 등록 — 실제 동의면 통과 + 노트에 확신도", got["ok"] and "확신도: 확신도 80 → 100"
          in iss.writes[-1][1] and answer in iss.writes[-1][1], iss.writes[-1][1][-160:])


def t_failures(root):
    """T4 — 실패 장부와 plan_start 판정 갈림(00:35 재현)."""
    from master import plan_tools as PT
    skill = "master/skills/ax-wayfinder/SKILL.md"
    L.record_check(root, 1039, "integration", 1, paths=[skill], summary="test_skill_conventions 53/54")
    fails = L.open_failures(root, 1039)
    check("실패 장부 — 열린 실패 1", len(fails) == 1 and fails[0]["paths"] == [skill], str(fails))

    def verdict(changed, failures=None):
        out = {"verdict": "resume", "ok": True, "tasks": ["T4"], "detail": []}
        PT._apply_failures(out, 1039, "AXCluster", L.open_failures(root, 1039) if failures is None else failures,
                           changed)
        return out

    out = verdict([skill, "master/wayfinder_dispatch.py"])
    check("[중요] 00:35 — 실패 경로가 이번 일감 변경(커밋분 포함) 안 → resume 유지",
          out["verdict"] == "resume" and out["ok"] and "record_check" in out["detail"][-1], str(out))
    out = verdict(["master/wayfinder_dispatch.py"])
    check("[중요] 변경 밖 실패 → stop · ok False · §1.1 안내",
          out["verdict"] == "stop" and out["ok"] is False and "§1.1" in out["next_action"], str(out))
    out = PT._apply_failures(o := {"verdict": "resume", "ok": True}, 1039, "AXCluster", L.open_failures(root, 1039),
                             lambda *_: None) or o
    check("변경 목록 모름 → stop", out["verdict"] == "stop" and "모름" in out["detail"][0], str(out))
    L.record_check(root, 1039, "noroute", 2, summary="경로 없음")
    out = verdict([skill])
    check("경로 없는 실패 → stop", out["verdict"] == "stop", str(out))
    L.record_check(root, 1039, "integration", 0)
    L.record_check(root, 1039, "noroute", 0)
    check("rc 0 이 같은 검사의 실패를 닫는다", L.open_failures(root, 1039) == [])
    out = verdict([skill])
    check("열린 실패 없음 → 판정 그대로", out == {"verdict": "resume", "ok": True, "tasks": ["T4"], "detail": []},
          str(out))
    out = {"verdict": "plan_needed", "ok": False}
    PT._apply_failures(out, 1039, "AXCluster", [{"check": "x", "rc": 1, "paths": []}], [])
    check("resume·next 가 아니면 손대지 않는다", out == {"verdict": "plan_needed", "ok": False}, str(out))
    check("rc bool 거절", "정수" in refused(L.record_check, root, 1, "c", True))


def t_stop_check(root):
    """T5 — 멈춤 판정. 00:27 재현: resume 인데 사유 없이 끝내면 막는다."""
    res = {"verdict": "resume", "tasks": ["T3"]}
    got = L.stop_check(root, active_issue=1039, verdict=res, session="s")
    check("[중요] 00:27 — 잠금 활성 + resume + 사유 없음 → block", got["block"] and "resume" in got["reason"]
          and "T3" in got["reason"], str(got))
    check("[중요] 사유 문장에 명령형이 없다(사실만)", not any(w in got["reason"] for w in ("하라", "하세요", "해라", "할 것")),
          got["reason"])
    check("잠금 없음 → 통과", not L.stop_check(root, active_issue=None, verdict=res)["block"])
    for v in ("stop", "plan_needed", "interview_needed", "plan_done", "blocked"):
        check(f"판정 {v} → 통과", not L.stop_check(root, active_issue=1039, verdict={"verdict": v})["block"])
    check("판정 모름(None) → 통과(fail-open)", not L.stop_check(root, active_issue=1039, verdict=None)["block"])
    L.ask(root, 1039, "decision", "어느 쪽?", "A", ["B"], 80)
    got = L.stop_check(root, active_issue=1039, verdict=res, session="s")
    check("[중요] 답 대기 질문 있음 → 통과", not got["block"] and "답 대기" in got["reason"], str(got))
    L.record_prompt(root, "A로 해", session="s")
    check("답이 들어오면 다시 막는다", L.stop_check(root, active_issue=1039, verdict=res, session="s")["block"])
    L.record_prompt(root, "일단 토큰 없으니 인수인계 작성하고 마무리하자", session="s")
    got = L.stop_check(root, active_issue=1039, verdict=res, session="s")
    check("[중요] 사용자 멈춤 지시(15:37 원문) → 통과", not got["block"] and "멈춤 지시" in got["reason"], str(got))
    L.record_prompt(root, "계속", session="t")
    blocks = [L.stop_check(root, active_issue=1039, verdict=res, session="t")["block"] for _ in range(4)]
    check("연속 차단 상한 3 → 네 번째는 통과", blocks == [True, True, True, False], str(blocks))
    L.record_prompt(root, "계속", session="t")
    check("새 입력이면 차단 수 초기화", L.stop_check(root, active_issue=1039, verdict=res, session="t")["block"])


def main() -> int:
    for fn in (t_ask_rules, t_no_question, t_session_answers, t_fabricated_answer, t_unrelated_answer,
               t_choices_and_confidence, t_open_questions, t_record_gate, t_set_plan_gate, t_failures,
               t_stop_check):
        with tempfile.TemporaryDirectory(prefix="ax-ledger-") as d:
            try:
                fn(Path(d))
            except Exception as e:                       # noqa: BLE001
                check(f"{fn.__name__} 예외 없음", False, f"{type(e).__name__}: {e}")
    t_gate_switch()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_interview_ledger: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
