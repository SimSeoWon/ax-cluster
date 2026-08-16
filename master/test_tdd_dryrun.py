"""TDD 드라이런 판정(`#145`) 계약 테스트 — 🔴 **거짓 클로저를 보고하지 않는가.**

이 모듈의 값은 red-green 판정에 있고, 그 판정은 원전이 **실측으로 네 번 데어** 얻은 것이다.
그래서 여기서 재는 것은 «닫혔다» 가 아니라 **«닫히지 않았는데 닫혔다고 하지 않는가»** 다:

    ① fail-open 을 통과로 세지 않는다      크래시가 green 으로 삼켜진 사고
    ② 루브릭이 약한 테스트를 가리지 않는다  둘이 어긋나면 problem 으로 표면화
    ③ 빌드 실패를 조용히 넘기지 않는다      컴파일 안 되면 red-green 은 **미검증**
    ④ 준수 실패의 두 원인을 가른다          과엄격 vs 샘플 자체 결함(LLM 변동성)

실행: python3 master/test_tdd_dryrun.py   (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import tdd_dryrun as D      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def sc(scenario, *, impl_ok=True, rubric=None, build_ok=None, ok=None, tests_passed=None):
    e = {"scenario": scenario, "impl_ok": impl_ok}
    if rubric is not None:
        e["rubric_issues"] = rubric
    if build_ok is not None or ok is not None or tests_passed is not None:
        e["ue_test"] = {"build_ok": build_ok, "ok": ok, "tests_passed": tests_passed}
    return e


TEMPLATE = {"contracts": {"postconditions": ["Complete() 는 한 번"]},
            "example": {"instance": "X", "refs": ["A/X.h"]},
            "structure": [{"role": "실행자", "class_pattern": "*Executor", "base": "UObject"}]}


# ── 기본 클로저 ───────────────────────────────────────────────

def test_closes_when_rubric_only():
    v = D.compute_verdict([sc("violating", rubric=["위반 1"]), sc("compliant", rubric=[])], False)
    check("위반 잡히고 준수 통과 → 닫힌다", v["red_green_closed"] is True, str(v))
    check("problem 없음", v["problems"] == [], str(v["problems"]))


def test_loose_contract_is_named():
    v = D.compute_verdict([sc("violating", rubric=[]), sc("compliant", rubric=[])], False)
    check("위반을 못 잡으면 안 닫힌다", v["red_green_closed"] is False)
    check("🔴 느슨하다고 말한다", any("느슨" in p for p in v["problems"]), str(v["problems"]))


# ── ① fail-open 을 통과로 세지 않는다 ─────────────────────────

def test_fail_open_is_not_a_pass():
    """🔴 원전 실측: 크래시가 *"리포트 부재 + exit≠0"* 로 fail-open 되어 **green 으로 삼켜졌다.**"""
    ran, passed = D.ue_view({"ue_test": {"build_ok": True, "ok": False, "tests_passed": True}}, True)
    check("ok=False 는 판정 불가로 본다 (ran=False)", ran is False and passed is None,
          f"{ran} {passed}")
    ran2, _ = D.ue_view({"ue_test": {"build_ok": True, "ok": True, "tests_passed": False}}, True)
    check("ok=True 여야 판정 가능", ran2 is True)
    ran3, _ = D.ue_view({"ue_test": {"build_ok": True, "ok": True}}, False)
    check("with_ue_test=False 면 애초에 판정 안 한다", ran3 is False)
    # 🔴 인프라 미가용인데 루브릭이 위반을 못 봤다 → **잡힌 것이 아니다**
    v = D.compute_verdict([sc("violating", rubric=[], build_ok=True, ok=False, tests_passed=True),
                           sc("compliant", rubric=[], build_ok=True, ok=False, tests_passed=True)],
                          True)
    check("🔴 fail-open 상태에서 위반이 잡혔다고 하지 않는다",
          v["violating_caught"] is False, str(v))
    check("그래서 닫히지 않는다", v["red_green_closed"] is False, str(v))


# ── ② 루브릭이 테스트를 가리지 않는다 ─────────────────────────

def test_rubric_and_test_disagreement_is_surfaced():
    v = D.compute_verdict([sc("violating", rubric=["위반"], build_ok=True, ok=True, tests_passed=True),
                           sc("compliant", rubric=[], build_ok=True, ok=True, tests_passed=True)],
                          True)
    check("🔴 루브릭은 잡았는데 실제 테스트는 green → 말한다",
          any("런타임에서 검증하지 못한다" in p for p in v["problems"]), str(v["problems"]))
    check("그래도 caught 자체는 True (루브릭이 잡았다)", v["violating_caught"] is True)

    v2 = D.compute_verdict([sc("violating", rubric=[], build_ok=True, ok=True, tests_passed=False),
                            sc("compliant", rubric=[], build_ok=True, ok=True, tests_passed=True)],
                           True)
    check("🔴 루브릭은 놓쳤는데 실제 테스트가 잡음 → 말한다",
          any("루브릭이 놓친" in p for p in v2["problems"]), str(v2["problems"]))
    check("실제 테스트가 잡았으므로 caught", v2["violating_caught"] is True)
    check("그리고 닫힌다", v2["red_green_closed"] is True, str(v2))


# ── ③ 빌드 실패를 조용히 넘기지 않는다 ────────────────────────

def test_build_failure_is_not_hidden_by_rubric():
    """🔴 컴파일이 안 되면 red-green 은 **미검증**이다 — 루브릭 폴백이 가리면 거짓 클로저다."""
    v = D.compute_verdict([sc("violating", rubric=["위반"], build_ok=False),
                           sc("compliant", rubric=[], build_ok=False)], True)
    check("🔴 빌드 실패를 problem 으로 말한다",
          sum("UE 빌드 실패" in p for p in v["problems"]) == 2, str(v["problems"]))
    check("미검증이라고 적는다", any("미검증" in p for p in v["problems"]))
    # ⚠️ 루브릭만으로는 닫힌 것처럼 보이지만 problem 이 그 사실을 들고 나온다
    check("루브릭 판정 자체는 유지된다", v["violating_caught"] is True and v["compliant_passed"] is True)


# ── ④ 준수 실패의 두 원인 ─────────────────────────────────────

def test_compliant_failure_reasons_are_split():
    both = D.compute_verdict([sc("violating", rubric=["위반"]), sc("compliant", rubric=["오탐?"])],
                             False)
    check("🔴 위반은 잡히고 준수만 실패 → **샘플 결함 가능**이라고 말한다",
          any("샘플 자체의 결함" in p for p in both["problems"]), str(both["problems"]))
    check("재시도를 권한다", any("재시도" in p for p in both["problems"]))

    neither = D.compute_verdict([sc("violating", rubric=[]), sc("compliant", rubric=["오탐"])], False)
    check("🔴 위반도 못 잡았으면 **과엄격/거짓양성** 쪽으로 말한다",
          any("과엄격" in p for p in neither["problems"]), str(neither["problems"]))


def test_impl_failure_is_unknown_not_false():
    v = D.compute_verdict([sc("violating", impl_ok=False), sc("compliant", impl_ok=False)], False)
    check("구현 자체가 실패하면 판정은 None (모른다)",
          v["violating_caught"] is None and v["compliant_passed"] is None, str(v))
    check("모르는 것을 닫혔다고 하지 않는다", v["red_green_closed"] is False)
    check("없는 시나리오도 None", D.compute_verdict([], False)["violating_caught"] is None)


# ── 프롬프트 — 컴파일 규약이 실려야 한다 ──────────────────────

def test_prompts_carry_the_compile_rules():
    p = D.test_gen_prompt("MissionTaskAddition", TEMPLATE)
    check("🔴 TEXT() 규약이 실린다", 'TEXT("...")' in p, p[:0])
    check("🔴 포인터 const 일치 규약이 실린다", "const" in p and "ValueType" in p)
    check("필터 이름 규약", "TDDDryRun.MissionTaskAddition" in p)
    check("🔴 참조는 경로로 준다 (코드 사본이 아니다)", "A/X.h" in p and "Read" in p)
    check("계약이 실린다", "Complete() 는 한 번" in p)

    iv = D.impl_prompt("T", TEMPLATE, "violating")
    check("위반 시나리오는 **컴파일은 되어야** 한다고 못박는다", "컴파일은 되어야" in iv)
    ic = D.impl_prompt("T", TEMPLATE, "compliant", spec="보스 레이드 태스크")
    check("서술 미션이 실린다", "보스 레이드 태스크" in ic)
    check("범위를 벗어나지 말라고 한다", "범위를 벗어나지" in ic)
    check("구조 역할이 실린다", "*Executor" in ic)


def test_refs_absence_is_loud():
    check("🔴 참조가 없으면 그 위험을 적는다",
          "지어낼 수 있다" in D.refs_text({"instance": "X"}), D.refs_text({"instance": "X"}))
    check("계약이 비면 (없음) 으로 적는다", "(없음)" in D.contracts_text({}))


# ── 오케스트레이션 ────────────────────────────────────────────

def test_no_contracts_does_not_start():
    r = D.run("T", template={"contracts": {}}, spawn=lambda p, l: {"ok": True})
    check("🔴 계약이 없으면 시작하지 않는다", not r.ok and "contracts" in r.error, r.error)
    check("이유를 말한다", "계약을 등록" in r.error, r.error)


def test_run_wires_scenarios():
    seen = []

    def spawn(prompt, label):
        seen.append(label)
        return {"ok": True, "detail": ""}

    r = D.run("T", template=TEMPLATE, spawn=spawn,
              rubric=lambda s: ["위반"] if s == "violating" else [],
              with_ue_test=False)
    check("테스트 생성 → 두 시나리오 순으로 부른다",
          seen == ["test-gen", "impl-compliant", "impl-violating"], str(seen))
    check("완주하면 ok", r.ok is True)
    check("판정이 닫힌다", r.verdict["red_green_closed"] is True, str(r.verdict))
    check("단계 로그가 남는다", len(r.steps) == 3, str(len(r.steps)))

    bad = D.run("T", template=TEMPLATE, spawn=lambda p, l: {"ok": l == "test-gen"})
    check("🔴 구현이 실패하면 ok 가 아니다", bad.ok is False)
    check("그때도 판정은 나온다 (모른다로)", bad.verdict["violating_caught"] is None, str(bad.verdict))

    gen_fail = D.run("T", template=TEMPLATE, spawn=lambda p, l: {"ok": False, "detail": "쿼터"})
    check("테스트 생성 실패면 시나리오로 안 넘어간다",
          not gen_fail.ok and "테스트 생성 실패" in gen_fail.error, gen_fail.error)


def main() -> int:
    for fn in (test_closes_when_rubric_only, test_loose_contract_is_named,
               test_fail_open_is_not_a_pass, test_rubric_and_test_disagreement_is_surfaced,
               test_build_failure_is_not_hidden_by_rubric,
               test_compliant_failure_reasons_are_split, test_impl_failure_is_unknown_not_false,
               test_prompts_carry_the_compile_rules, test_refs_absence_is_loud,
               test_no_contracts_does_not_start, test_run_wires_scenarios):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_tdd_dryrun: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
