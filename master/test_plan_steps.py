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
    check("unreal 은 2·4·6 조건부", all(s[n].applies == PS.COND for n in (2, 4, 6)))
    check("프리 에디터 조건에 승인 뒤 제거가 있다", "승인" in s[2].reason, s[2].reason)
    check("에디터 조건에 MCP 확인이 있다", "MCP" in s[6].reason, s[6].reason)
    check("해당없음은 하나도 없다", not any(x.applies == PS.SKIP for x in s.values()))


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


def main() -> int:
    for fn in (test_order_is_826,
               test_code_table,
               test_unreal_table,
               test_refuses_unknown_and_index_only,
               test_project_uses_profile_kind,
               test_every_kind_in_profile_is_decided):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_steps: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
