"""7단계 해당 판정(`#826` T4) 계약 테스트 — [중요] **code 에 에디터 단계를 내보내지 않는가,
모르는 타입을 unreal 로 읽지 않는가.**

실행: python3 master/test_plan_steps.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_steps as PS    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _by_no(steps):
    return {s.no: s for s in steps}


def test_order_is_826():
    names = [s.name for s in PS.steps_for_kind("code")]
    check("7단계 순서가 #826 과 같다",
          names == ["버전 동기화·상태 확인", "프리 에디터 작업", "소스 작업", "프로젝트 제네레이트",
                    "소스코드 빌드", "에디터 작업", "작업 상태 확인·인수인계 기록"], str(names))
    check("[중요] 버전 동기화가 프리 에디터보다 먼저", names.index("버전 동기화·상태 확인")
          < names.index("프리 에디터 작업"))


def test_code_table():
    s = _by_no(PS.steps_for_kind("code"))
    check("code 는 1·3·5·7 실행", all(s[n].applies == PS.RUN for n in (1, 3, 5, 7)))
    check("code 는 2·4·6 해당없음", all(s[n].applies == PS.SKIP for n in (2, 4, 6)))
    check("해당없음에는 사유가 있다", all(s[n].reason.strip() for n in (2, 4, 6)))
    check("code 의 빌드는 정적·통합 검사로 대신한다는 사유", "통합 검사" in s[5].reason, s[5].reason)


def test_unreal_table():
    s = _by_no(PS.steps_for_kind("unreal"))
    check("unreal 은 1·3·5·7 실행", all(s[n].applies == PS.RUN for n in (1, 3, 5, 7)))
    check("unreal 은 2·6 조건부", all(s[n].applies == PS.COND for n in (2, 6)))
    check("[중요] unreal 4단계(제네레이트)는 해당없음 — #857 T1 실측", s[4].applies == PS.SKIP
          and "T1" in s[4].reason and "IDE" in s[4].reason, s[4].reason)
    check("프리 에디터 조건에 승인 뒤 제거가 있다", "승인" in s[2].reason, s[2].reason)
    check("에디터 조건에 MCP 확인이 있다", "MCP" in s[6].reason, s[6].reason)
    check("해당없음은 4단계 하나뿐", [n for n, x in s.items() if x.applies == PS.SKIP] == [4])


def test_refuses_unknown_and_index_only():
    for kind in ("", "  ", "ue5", None):
        try:
            PS.steps_for_kind(kind)
            ok = False
        except PS.StepError as e:
            ok = "unreal 로 읽지 않는다" in str(e)
        check(f"모르는 kind {kind!r} 거절", ok)
    try:
        PS.steps_for_kind("index_only")
        ok = False
    except PS.StepError as e:
        ok = "분산 작업을 받지 않는다" in str(e)
    check("index_only 거절", ok)


def test_project_uses_profile_kind():
    seen = []
    steps = PS.steps_for_project("AXCluster", kind_of=lambda p: seen.append(p) or "code")
    check("프로필 kind 를 그 프로젝트로 묻는다", seen == ["AXCluster"], str(seen))
    check("그 kind 의 표를 돌려준다", _by_no(steps)[6].applies == PS.SKIP)


def test_every_kind_in_profile_is_decided():
    from master.projects import profile
    for kind in profile.KINDS:
        try:
            PS.steps_for_kind(kind)
            decided = True
        except PS.StepError:
            decided = kind == "index_only"
        check(f"프로필 KINDS 의 {kind} 는 판정되거나 의도적으로 거절된다", decided)


def test_task_declares_conditional_steps():
    s = _by_no(PS.steps_for_task("unreal", [6]))
    check("선언한 조건부 단계는 실행", s[6].applies == PS.RUN and "선언" in s[6].reason, s[6].reason)
    check("선언 안 한 조건부는 해당없음 + 조건을 사유로",
          s[2].applies == PS.SKIP and "조건" in s[2].reason, s[2].reason)
    check("늘 하는 단계는 그대로 실행", all(s[n].applies == PS.RUN for n in (1, 3, 5, 7)))
    check("[중요] 판정 뒤에는 조건부가 남지 않는다",
          not any(x.applies == PS.COND for x in s.values()))
    s = _by_no(PS.steps_for_task("unreal", []))
    check("아무것도 선언 안 하면 2·4·6 해당없음", all(s[n].applies == PS.SKIP for n in (2, 4, 6)))
    check("4단계 사유는 선언 여부가 아니라 실측", "T1" in s[4].reason, s[4].reason)
    s = _by_no(PS.steps_for_task("unreal", [6, 2, 2]))
    check("중복·순서와 무관", s[2].applies == PS.RUN and s[6].applies == PS.RUN and s[4].applies == PS.SKIP)
    s = _by_no(PS.steps_for_task("code", []))
    check("code 는 선언 없이 종전 표 그대로", s[4].applies == PS.SKIP and s[5].applies == PS.RUN)


def test_task_declaring_non_conditional_is_refused():
    for kind, steps in (("code", [4]), ("code", [6]), ("unreal", [5]), ("unreal", [1, 6]),
                        ("unreal", [4])):
        try:
            PS.steps_for_task(kind, steps)
            ok = False
        except PS.StepError as e:
            ok = "조건부가 아닌" in str(e)
        check(f"[중요] {kind} 에 {steps} 선언 → 거절", ok)
    try:
        PS.steps_for_task("", [4])
        ok = False
    except PS.StepError:
        ok = True
    check("모르는 kind 는 선언과 무관하게 거절", ok)


def main() -> int:
    for fn in (test_order_is_826,
               test_code_table,
               test_unreal_table,
               test_refuses_unknown_and_index_only,
               test_project_uses_profile_kind,
               test_every_kind_in_profile_is_decided,
               test_task_declares_conditional_steps,
               test_task_declaring_non_conditional_is_refused):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_steps: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
