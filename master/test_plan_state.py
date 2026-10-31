"""플랜 상태 전이(`#826` T2) 계약 테스트 — [중요] **규칙에 어긋난 전이를 거절하는가.**

실행: python3 master/test_plan_state.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB    # noqa: E402
from master import plan_state as PS    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _plan(*rows) -> PB.Plan:
    return PB.Plan(1, [PB.Task(tid, state, "목표", deps=list(deps), evidence=ev)
                       for tid, state, deps, ev in rows])


def _err(fn) -> str:
    try:
        fn()
    except PS.TransitionError as e:
        return str(e)
    return ""


BASE = _plan(("T1", "대기", (), ""), ("T2", "대기", ("T1",), ""), ("T3", "대기", ("T1", "T2"), ""))


def test_normal_path():
    p = PS.transition(BASE, "T1", "작업중")
    p = PS.transition(p, "T1", "완료", note="abc1234 · 검사 OK")
    check("완료로 간다", p.task("T1").state == "완료")
    check("근거가 칸에 들어간다", p.task("T1").evidence == "abc1234 · 검사 OK")
    p = PS.transition(p, "T2", "작업중")
    check("선행이 끝나면 다음 태스크를 시작한다", p.task("T2").state == "작업중")
    check("원본은 그대로", BASE.task("T1").state == "대기" and BASE.task("T1").evidence == "")


def test_done_needs_evidence():
    p = PS.transition(BASE, "T1", "작업중")
    for note in ("", "   "):
        check(f"근거 없는 완료 거절 ({note!r})",
              "근거" in _err(lambda n=note: PS.transition(p, "T1", "완료", note=n)))


def test_block_and_skip_need_reason():
    p = PS.transition(BASE, "T1", "작업중")
    check("사유 없는 차단 거절", "사유" in _err(lambda: PS.transition(p, "T1", "차단")))
    check("사유 없는 해당없음 거절", "사유" in _err(lambda: PS.transition(BASE, "T1", "해당없음")))
    b = PS.transition(p, "T1", "차단", note="큐 서비스 응답 없음")
    check("사유 있는 차단은 된다", b.task("T1").evidence == "큐 서비스 응답 없음")
    r = PS.transition(b, "T1", "작업중")
    check("재개하면 지난 사유를 지운다", r.task("T1").state == "작업중" and r.task("T1").evidence == "")


def test_disallowed_transitions():
    done = PS.transition(PS.transition(BASE, "T1", "작업중"), "T1", "완료", note="근거")
    for to in ("대기", "작업중", "차단", "해당없음"):
        check(f"완료 → {to} 거절", "허용되지 않는다" in _err(lambda t=to: PS.transition(done, "T1", t, note="x")))
    check("대기 → 완료(작업 없이) 거절",
          "허용되지 않는다" in _err(lambda: PS.transition(BASE, "T1", "완료", note="근거")))
    skip = PS.transition(BASE, "T1", "해당없음", note="kind=code")
    check("해당없음 → 작업중 거절",
          "허용되지 않는다" in _err(lambda: PS.transition(skip, "T1", "작업중")))
    check("같은 상태로의 전이도 거절",
          "허용되지 않는다" in _err(lambda: PS.transition(BASE, "T1", "대기")))


def test_unknown_inputs():
    check("없는 태스크 거절", "없는 태스크" in _err(lambda: PS.transition(BASE, "T9", "작업중")))
    check("모르는 상태 거절", "모르는 상태" in _err(lambda: PS.transition(BASE, "T1", "진행")))


def test_deps_gate():
    check("선행이 대기면 작업중 거절",
          "T1" in _err(lambda: PS.transition(BASE, "T2", "작업중")))
    p = PS.transition(BASE, "T1", "해당없음", note="이번 범위 아님")
    check("선행이 해당없음이면 시작할 수 있다",
          PS.transition(p, "T2", "작업중").task("T2").state == "작업중")
    msg = _err(lambda: PS.transition(p, "T3", "작업중"))
    check("끝나지 않은 선행만 이름을 댄다", "T2" in msg and "T1" not in msg, msg)


def test_violations_reads_hand_edits():
    clean = _plan(("T1", "완료", (), "abc"), ("T2", "작업중", ("T1",), ""))
    check("깨끗한 플랜은 위반 0", PS.violations(clean) == [], str(PS.violations(clean)))
    dirty = _plan(("T1", "완료", (), ""), ("T2", "차단", (), " "),
                  ("T3", "작업중", ("T4",), ""), ("T4", "대기", (), ""))
    v = PS.violations(dirty)
    check("근거 빈 완료를 잡는다", any(x.startswith("T1:") for x in v), str(v))
    check("사유 빈 차단을 잡는다", any(x.startswith("T2:") for x in v), str(v))
    check("선행 미완료 작업중을 잡는다", any(x.startswith("T3:") and "T4" in x for x in v), str(v))
    check("대기는 위반이 아니다", not any(x.startswith("T4:") for x in v), str(v))


def test_roundtrip_through_body():
    body = "## 스펙\n\n요구\n"
    body = PB.append(body, BASE.tasks)
    plan = PS.transition(PB.parse(body), "T1", "작업중")
    body2 = PB.replace(body, plan.tasks)
    check("전이 결과가 본문으로 왕복한다", PB.parse(body2).task("T1").state == "작업중")
    check("본문 앞부분은 그대로", body2.startswith("## 스펙\n\n요구\n"))


def test_error_is_a_plan_error():
    check("TransitionError 는 PlanError 계열 — 호출자가 한 번에 잡는다",
          issubclass(PS.TransitionError, PB.PlanError))


def main() -> int:
    for fn in (test_normal_path,
               test_done_needs_evidence,
               test_block_and_skip_need_reason,
               test_disallowed_transitions,
               test_unknown_inputs,
               test_deps_gate,
               test_violations_reads_hand_edits,
               test_roundtrip_through_body,
               test_error_is_a_plan_error):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_state: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
