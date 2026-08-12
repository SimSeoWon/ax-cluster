"""층1 — 결정적 자기검증 (중 2.1).

🔴 지키는 계약은 넷이다:

    ① **휘발 태그는 잡고 보존 태그는 건드리지 않는다** — 태그가 두 종류라는 게 실제 계약이다
    ② 🔴 **`[FEEDBACK]` 이 소스에 남으면 위반** — 원전에서 검증이 무한 실패한 그 자리다
    ③ **동결은 추가 허용 · 변경/삭제 위반 · 본문 채움 통과**
    ④ 🔴 **fail-closed** — 안 돌린 것도, 기준 원본이 없는 것도 통과가 아니다

`.venv/bin/python master/test_layer1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import infer as INF        # noqa: E402
from master.work import layer1 as L1        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


HDR = """#pragma once
UCLASS()
class MODULARSTAGE_API UFoo : public UObject
{
\tGENERATED_BODY()
public:
\tvirtual void SetData(const FMissionTaskInfo& InTaskInfo) override;
\tint32 GetStep() const;
};
"""
H, C = "Source/A/Foo.h", "Source/A/Foo.cpp"


# ── ① 휘발 태그 vs 보존 태그 ────────────────────────────────────────────────────

def test_volatile_tags_are_caught() -> None:
    for tag in ("[PSEUDO]", "[PSEUDO:2]", "[IMPL]"):
        r = L1.check({C: f"void UFoo::F()\n{{\n\t// {tag} 나중에 채운다\n}}\n"})
        check(f"{tag} 를 잡는다", not r.ok, r.summary)
        check(f"{tag} 를 사유에 적는다", any(tag.split(':')[0] in p for p in r.problems),
              str(r.problems))


def test_permanent_tags_and_plain_comments_pass() -> None:
    """🔴 `[DOC]`·`[STATE]`·`[BIND]`·`[REPLICATED]` 와 무태그 주석은 **남아 있어야 정상**이다."""
    body = ("// [DOC] 무엇을 하는가\n// [STATE] 상태 설명\n// [BIND] 바인딩\n"
            "// [REPLICATED] 복제됨\n// 그냥 주석\nvoid UFoo::F() {}\n")
    r = L1.check({C: body})
    check("보존 태그는 통과", r.ok, r.summary)


def test_feedback_left_in_source_is_a_violation() -> None:
    """🔴 원전: *"모든 주석 보존"* 지시가 `[FEEDBACK]` 삭제를 막아 **검증이 무한 실패**했다."""
    r = L1.check({C: "// [FEEDBACK] 빌드가 깨졌다\nvoid UFoo::F() {}\n"})
    check("[FEEDBACK] 잔재는 위반", not r.ok, r.summary)
    check("사유가 FEEDBACK 을 지목", any("FEEDBACK" in p for p in r.problems), str(r.problems))


def test_fence_residue_is_a_violation() -> None:
    r = L1.check({C: "```cpp\nvoid UFoo::F() {}\n```\n"})
    check("펜스 잔재는 위반", not r.ok, r.summary)


# ── ③ 동결 ──────────────────────────────────────────────────────────────────────

def test_freeze_semantics() -> None:
    add = HDR.replace("\tint32 GetStep() const;", "\tint32 GetStep() const;\n\tvoid New();")
    chg = HDR.replace("SetData(const FMissionTaskInfo& InTaskInfo)",
                      "SetData(FMissionTaskInfo In)")
    dele = HDR.replace("\tint32 GetStep() const;\n", "")
    fill = HDR.replace("\tint32 GetStep() const;", "\tint32 GetStep() const { return 0; }")
    for name, new, want in [("추가는 허용", add, True), ("시그니처 변경은 위반", chg, False),
                            ("선언 삭제는 위반", dele, False), ("본문 채움은 허용", fill, True)]:
        r = L1.check({H: new}, baseline=lambda p: HDR)
        check(name, r.ok is want, r.summary)


def test_cpp_is_not_a_freeze_target() -> None:
    """동결은 **선언**의 문제다 — `.cpp` 본문이 바뀌는 것은 정상 작업이다."""
    r = L1.check({C: "void UFoo::Other() {}\n"}, baseline=lambda p: "void UFoo::F() {}\n")
    check(".cpp 는 동결 대상이 아니다", r.ok, r.summary)


def test_new_file_has_nothing_to_freeze() -> None:
    r = L1.check({H: HDR}, baseline=lambda p: None)
    check("신규 파일은 통과", r.ok, r.summary)
    check("동결 미검사로 센다", r.skipped == [H], str(r.skipped))


# ── ④ fail-closed ───────────────────────────────────────────────────────────────

def test_fail_closed_directions() -> None:
    empty = L1.check({})
    check("빈 입력은 통과가 아니다", not empty.ok, empty.summary)

    unchecked = L1.Layer1()
    check("안 돌린 것은 통과가 아니다", not unchecked.ok, unchecked.summary)
    check("미확인이라고 적는다", "미확인" in unchecked.summary, unchecked.summary)

    no_base = L1.check({H: HDR})
    check("기준 원본 없이도 잔재는 본다", no_base.checked)
    check("동결은 미검사라고 적는다", "미검사" in no_base.summary, no_base.summary)


# ── 🔴 배선 — 응답 수락 경로 (소 2.1.3) ─────────────────────────────────────────

def test_residue_response_is_rejected_at_acceptance_not_at_apply() -> None:
    """🔴 잔재가 있는 응답이 *"통과"* 로 스풀에 들어가면 왕복이 하나 더 든다."""
    want = [H, C]
    good = f"=== FILE: {H} ===\n{HDR}=== FILE: {C} ===\nvoid UFoo::F() {{}}\n"
    ok = INF.judge("RESPONSE: 2\nRESULT: DONE", good, want=want)
    check("정상 응답은 통과", ok.ok, ok.summary)

    bad = f"=== FILE: {H} ===\n{HDR}=== FILE: {C} ===\n// [PSEUDO] 나중에\n"
    r = INF.judge("RESPONSE: 2\nRESULT: DONE", bad, want=want)
    check("🔴 잔재가 있으면 수락 단계에서 막는다", not r.ok, r.summary)
    check("치명 메모로 남는다", any("휘발 태그" in n for n in r.fatal), str(r.notes))

    fb = f"=== FILE: {H} ===\n{HDR}=== FILE: {C} ===\n// [FEEDBACK] 남았다\n"
    r2 = INF.judge("RESPONSE: 2\nRESULT: DONE", fb, want=want)
    check("[FEEDBACK] 잔재도 수락 단계에서 막는다", not r2.ok, r2.summary)


def test_integrate_still_runs_layer1_as_the_last_line() -> None:
    """🔴 두 곳 다 둔다 — 스풀을 손질하거나 재사용하는 경로에서 ①이 우회된다."""
    from master.work import integrate as ITG
    r = ITG.layer1({C: "// [IMPL] 미완\n"}, baseline=None)
    check("통합자 쪽도 같은 검사", not r.ok, r.summary)
    check("같은 구현을 쓴다", ITG.Layer1 is L1.Layer1)


def main() -> int:
    for fn in (test_volatile_tags_are_caught, test_permanent_tags_and_plain_comments_pass,
               test_feedback_left_in_source_is_a_violation, test_fence_residue_is_a_violation,
               test_freeze_semantics, test_cpp_is_not_a_freeze_target,
               test_new_file_has_nothing_to_freeze, test_fail_closed_directions,
               test_residue_response_is_rejected_at_acceptance_not_at_apply,
               test_integrate_still_runs_layer1_as_the_last_line):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_layer1: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
