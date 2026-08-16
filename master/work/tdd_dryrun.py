"""TDD 드라이런 하니스 — 원전 `tdd_dryrun.py` 459줄 이식 (소 2.4.1 · `#145`).

사용자(원전) 발화가 이 모듈의 존재 이유다: *"분산작업에서 TDD를 바로 적용하기엔 깃과 레드마인
등 여러곳에 흔적을 남겨서, **서버 기준 경량화된 1차 테스트**를 하고 싶다."*
→ **분산 파이프라인(브랜치·레드마인·큐) 밖에서** TDD 기제를 검증·튜닝하는 자리다.

    ① 템플릿의 contracts 를 읽는다                     ← 없으면 **시작하지 않는다**
    ② 임시 worktree (흔적 0 — push·레드마인·큐 미접촉)
    ③ [에이전트] 계약을 검증하는 테스트를 쓴다
    ④ 시나리오별 구현 — `compliant` / `violating`
    ⑤ 계약 루브릭 + (옵션) 실 빌드·RunTests
    ⑥ 🔴 **red-green 판정** — 위반은 잡히고(red) 준수는 통과(green) 하는가

## 🔴 이 모듈의 값은 ⑥ 에 있다 — 실측으로 얻은 교훈 넷이 거기 박혀 있다

    ① fail-open 을 통과로 세지 않는다   인프라 미가용(`ok=False`)은 **판정 불가**다.
                                       원전 실측: 크래시가 fail-open 으로 green 이 됐다
    ② 루브릭이 테스트를 가리지 않게      루브릭(LLM)만 보면 약한 생성 테스트가 숨는다 →
                                       둘이 어긋나면 **problem 으로 표면화**한다
    ③ 빌드 실패를 조용히 넘기지 않는다   컴파일이 안 되면 red-green 은 **미검증**이다.
                                       루브릭 폴백이 거짓 클로저를 보고하지 않게 말한다
    ④ 준수 실패의 두 원인을 가른다       위반이 정상 포착되는데 준수만 실패하면 계약이
                                       과엄격한 게 아니라 **샘플 자체 결함**일 수 있다(LLM 변동성)

## ⚠️ 지금 입력이 없다 — 그래서 이식이 먼저다

드라이런은 `contracts` 가 등록된 **태스크 템플릿**을 소비한다(`ontology/tasks.py` · `#139`).
등록은 **사람의 자리**라 아직 0건이다. 🔴 그래도 옮기는 이유는 마일스톤 최우선 규칙이다 —
*"원전에 있는 장치는 재지 않고 옮긴다. 검증은 이식 후에 한다."* 템플릿 하나가 등록되는 순간
이 하니스가 곧바로 쓰인다.

## ⚠️ 우리와 다른 것 — 전부 주입이다

원전은 `claude -p` spawn·UE 빌드·루브릭을 모듈 안에서 직접 부른다. 우리는 **주입**한다
(`spawn` / `rubric` / `build` / `tests`) — 이 저장소가 모든 게이트에서 쓰는 그 seam 이고,
그래야 판정 로직을 실 LLM·실 UE 없이 잰다. 🔴 다만 *"주입은 계약을 재고 실물을 재지 않는다"* —
실 구동은 템플릿이 생긴 뒤 별도로 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 🔴 필터 이름 규약 — 원전 그대로. 드라이런 테스트가 실 automation 필터와 섞이지 않게 접두어를 준다.
FILTER_PREFIX = "TDDDryRun"
SCENARIOS = ("compliant", "violating")


def contracts_text(contracts) -> str:
    """계약 3종을 프롬프트용 텍스트로. 비어 있으면 그렇게 적는다 — 조용히 빈칸을 주지 않는다."""
    c = contracts or {}
    out = []
    for key, label in (("preconditions", "선행"), ("postconditions", "후행"),
                       ("acceptance", "인수")):
        items = c.get(key) or []
        out.append(f"- {label}({key}): " + ("; ".join(str(i) for i in items) if items else "(없음)"))
    return "\n".join(out)


def refs_text(example) -> str:
    """참조 경로. 🔴 **코드를 싣지 않고 경로를 준다** — 원전 규약(example=참조 경로)이다.

    이유: 코드를 프롬프트에 박으면 그 사본이 곧 낡는다(stale). 에이전트가 **읽게** 한다.
    """
    e = example or {}
    refs = e.get("refs") or []
    head = f"- 예제 인스턴스: {e.get('instance') or '(없음)'}"
    if not refs:
        return head + "\n- 참조 경로: (없음) — 🔴 이 상태면 에이전트가 API 를 지어낼 수 있다"
    return head + "\n" + "\n".join(f"- {r}" for r in refs)


def test_gen_prompt(task_type: str, data: dict) -> str:
    """테스트 작성 프롬프트.

    🔴 **「UE 자동화 테스트 규약」 절을 반드시 싣는다** — 원전이 이것 없이 돌렸다가 생성 테스트가
    두 번 연속 컴파일에 실패했다(`TestEqual` 설명 인자 `TEXT()` 누락 · 포인터 const 불일치).
    그때 red-green 은 **미검증인 채로 루브릭 폴백이 클로저를 보고**했다. 프롬프트 한 절이
    그 사고를 막는다(예방), 판정부의 build_ok 표면화는 같은 것을 드러낸다(자기보고) — 상보다.
    """
    return (
        f"당신은 UE5 프로젝트의 테스트 작성 에이전트입니다. 작업 유형 템플릿 `{task_type}` 의 "
        "계약(contracts)을 검증하는 **FAutomationTest .cpp** 1개를 작성하세요.\n\n"
        f"## 계약\n{contracts_text(data.get('contracts'))}\n\n"
        "## 참조 클래스 (실제 API — 🔴 반드시 Read 로 시그니처를 확인하고 쓸 것. 환각 금지)\n"
        f"{refs_text(data.get('example'))}\n\n"
        "## 지시\n"
        "1. 위 참조 경로의 헤더를 Read 해 실제 함수·프로퍼티 시그니처를 확인한다.\n"
        "2. `IMPLEMENT_SIMPLE_AUTOMATION_TEST` + ProductFilter flags(헤드리스 `-nullrhi` 호환)로 "
        "각 선행/후행/인수를 TestTrue/TestEqual 단언으로 매핑한다. 검증 불가 항목은 `// TODO` 로 "
        "**정직하게** 남긴다.\n"
        f"3. 테스트 필터 이름은 `{FILTER_PREFIX}.{task_type}` 으로 한다.\n"
        "4. 프로젝트의 기존 `*Test.cpp` 위치 관례를 따라 새 파일로 쓴다.\n\n"
        "## 🔴 UE 자동화 테스트 규약 (컴파일 필수 — 위반하면 빌드가 깨진다)\n"
        "- **단언 설명 인자는 반드시 `TEXT(\"...\")` 로 감싼다.** TestTrue/TestEqual 의 첫 인자는 "
        "`const TCHAR*` 라 좁은 문자열(`const char[]`)은 변환되지 않아 컴파일이 실패한다.\n"
        "- **포인터·구조체를 TestEqual 로 비교할 땐 양쪽 타입과 const 를 맞춘다.** 예: "
        "`GetScriptStruct()` 는 `const UScriptStruct*` 이므로 `StaticStruct()`(`UScriptStruct*`)는 "
        "`(const UScriptStruct*)` 로 캐스트한다 — 안 그러면 ValueType 추론이 모호해 빌드가 깨진다. "
        "모호하면 `GetName()` 문자열 비교나 포인터 `==` + TestTrue 로 우회한다.\n"
        "읽어서 확인한 API 만 쓴다. 컴파일되지 않는 코드는 쓰지 않는다."
    )


def impl_prompt(task_type: str, data: dict, scenario: str, spec: str = "") -> str:
    """구현 프롬프트. `spec` 이 있으면 합성 샘플 대신 **그 미션**을 구현한다(더 현실적인 드라이런)."""
    structure = data.get("structure") or []
    struct_txt = "\n".join(
        f"  - {s.get('role')}: {s.get('class_pattern') or s.get('symbol_pattern', '')} "
        f"(base={s.get('base', '')})" for s in structure) or "  (없음)"
    subject = "아래 **사용자 서술 미션**을" if spec else "이 작업 유형의 신규 1건을"
    if scenario == "compliant":
        goal = f"{subject} 계약을 **모두 만족**하게 구현하라. 위 테스트가 green 이어야 한다."
    else:
        goal = (f"{subject} 구현하되 계약 중 **후행/인수 하나를 의도적으로 위반**하라 "
                "(예: 권한 가드 누락, null 체크 누락). 위 테스트가 그것을 red 로 잡아야 한다. "
                "🔴 단 **컴파일은 되어야 한다** — 안 되면 red-green 을 못 잰다.")
    spec_block = f"## 구현할 미션 (사용자 서술)\n{spec}\n\n" if spec else ""
    return (
        f"당신은 분산 워커를 흉내내는 구현 에이전트입니다. 작업 유형 `{task_type}` 의 신규 1건을 "
        "구현하세요. **드라이런이라 이 변경은 머지되지 않습니다.**\n\n"
        f"## 시나리오: {scenario}\n{goal}\n\n{spec_block}"
        f"## 계약\n{contracts_text(data.get('contracts'))}\n\n"
        f"## 구조(역할)\n{struct_txt}\n\n"
        f"## 참조 (실제 API — Read 로 확인)\n{refs_text(data.get('example'))}\n\n"
        "구조·규약을 따라 구현한다. 읽어서 확인한 API 만 쓴다."
        + ("\n🔴 서술 미션의 범위를 벗어나지 말 것 — 명시된 동작만 구현한다." if spec else "")
    )


# ─────────────────────────────────────────────────────────────
# 🔴 판정 — 이 모듈의 값이 여기 있다
# ─────────────────────────────────────────────────────────────

def ue_view(result: dict, with_ue_test: bool) -> tuple:
    """`(ran, passed)` — `ran` 은 *"실제 테스트가 **판정 가능하게** 돌았나"* 다.

    🔴 **`ok=False` 는 fail-open(인프라 미가용)이라 결과를 믿지 않는다** — `ran=False` 로 본다.
    원전 실측(2026-06-12): 위반 구현이 **에디터를 크래시**시켰는데 *"리포트 부재 + exit=3"* 가
    fail-open 으로 처리돼 **green 으로 삼켜졌다.** 그 뒤 원전은 *"리포트가 없는데 종료코드가
    비정상이면 크래시 = red"* 로 고쳤고, 여기서는 그 신호를 `ok=True/tests_passed=False` 로 받는다.
    """
    ut = result.get("ue_test") or {}
    if with_ue_test and ut.get("build_ok") and ut.get("ok") is True:
        return True, bool(ut.get("tests_passed"))
    return False, None


def compute_verdict(scenario_results, with_ue_test: bool) -> dict:
    """red-green 이 닫혔는가 — 위반은 잡히고(caught) 준수는 통과(passed)하는가.

    🔴 실제 테스트가 판정 가능하게 돌았으면 그 결과를 **루브릭과 대조**해 어긋남을 problem 으로
    표면화한다. 루브릭(LLM)만 보면 약한 생성 테스트가 가려져 **거짓 클로저**가 보고된다.
    """
    by = {r.get("scenario"): r for r in (scenario_results or [])}

    def caught(r):
        if not r or not r.get("impl_ok"):
            return None
        ran, ue_pass = ue_view(r, with_ue_test)
        if ran and not ue_pass:
            return True                      # 실제 테스트가 잡았다
        if r.get("rubric_issues"):
            return True                      # 루브릭이 잡았다
        return False

    def passed(r):
        if not r or not r.get("impl_ok"):
            return None
        if r.get("rubric_issues"):
            return False
        ran, ue_pass = ue_view(r, with_ue_test)
        if ran and not ue_pass:
            return False
        return True

    viol, comp = by.get("violating"), by.get("compliant")
    viol_caught, comp_passed = caught(viol), passed(comp)
    problems: list = []

    if viol is not None and viol_caught is False:
        problems.append("위반 시나리오를 루브릭·테스트가 못 잡았다 — 계약/테스트가 너무 느슨하다")
    if comp is not None and comp_passed is False:
        if viol_caught:
            # 🔴 위반은 정상 포착되는데 준수만 실패 = 계약 과엄격보다 **샘플 자체 결함**이 흔하다
            #    (원전 실측: 준수 구현이 위젯을 stub 으로 남긴 LLM 변동성 결함이었다).
            problems.append("준수 시나리오는 실패했는데 위반은 정상 포착됐다 — 준수 샘플 자체의 "
                            "결함일 수 있다(LLM 변동성). 로그로 결함 위치를 확인하고 재시도할 것. "
                            "반복되면 그때 계약·테스트가 과엄격한지 본다")
        else:
            problems.append("준수 시나리오가 실패로 처리됐다 — 계약/테스트가 과엄격이거나 거짓양성이다")

    if with_ue_test:
        for sc, r in (("violating", viol), ("compliant", comp)):
            if not r or not r.get("impl_ok"):
                continue
            ut = r.get("ue_test") or {}
            if ut.get("build_ok") is False:
                # 🔴 컴파일이 안 되면 red-green 은 **미검증**이다. 루브릭 폴백이 이것을 조용히
                #    가리면 거짓 클로저가 나간다(원전이 그렇게 한 번 속았다).
                problems.append(f"[{sc}] UE 빌드 실패 — 테스트가 컴파일되지 않아 실제 red-green 이 "
                                "미검증이다(루브릭으로만 판정). 빌드 로그를 볼 것")
                continue
            ran, ue_pass = ue_view(r, with_ue_test)
            if not ran:
                continue
            rubric_flag = bool(r.get("rubric_issues"))
            if rubric_flag and ue_pass:
                problems.append(f"[{sc}] 루브릭은 계약 위반을 지적했는데 실제 RunTests 는 통과했다 "
                                "— 생성 테스트가 그 계약을 런타임에서 검증하지 못한다(테스트 보강). "
                                "실제 테스트로는 클로저가 닫히지 않았다")
            elif (not rubric_flag) and (not ue_pass):
                problems.append(f"[{sc}] 루브릭은 위반 없음으로 봤는데 실제 RunTests 는 실패했다 "
                                "— 루브릭이 놓친 실패를 테스트가 잡았다(루브릭 신호 보완)")

    return {"red_green_closed": bool(viol_caught) and bool(comp_passed),
            "violating_caught": viol_caught, "compliant_passed": comp_passed,
            "problems": problems}


# ─────────────────────────────────────────────────────────────
# 오케스트레이션 — 🔴 실행 주체는 전부 주입이다
# ─────────────────────────────────────────────────────────────

@dataclass
class DryRun:
    task_type: str = ""
    ok: bool = False
    with_ue_test: bool = False
    scenarios: list = field(default_factory=list)
    verdict: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    error: str = ""


def run(task_type: str, *, template: dict, spawn, rubric=None, build=None, tests=None,
        spec: str = "", with_ue_test: bool = False, logf=None) -> DryRun:
    """드라이런 한 바퀴. 🔴 **계약이 없으면 시작하지 않는다.**

    `spawn(prompt, label) -> dict`  에이전트 한 번 (`{ok, detail}`)
    `rubric(scenario) -> list`      계약 루브릭 위반 목록 (없으면 건너뛴다)
    `build(scenario) -> dict`       `{build_ok, ok, tests_passed}` — 층3 계약과 같은 모양
    """
    log = logf or (lambda stage, msg: None)
    r = DryRun(task_type=task_type, with_ue_test=with_ue_test)
    data = template or {}
    if not (data.get("contracts") or {}):
        # ⚠️ 원전과 같다 — 계약이 없으면 잴 것이 없다. **조용히 통과시키지 않는다.**
        r.error = (f"템플릿 `{task_type}` 에 contracts 가 없다 — 드라이런은 계약을 재는 것이라 "
                   "시작하지 않는다. 먼저 계약을 등록할 것")
        return r

    gen = spawn(test_gen_prompt(task_type, data), "test-gen")
    r.steps.append({"step": "test-gen", **(gen or {})})
    if not (gen or {}).get("ok"):
        r.error = f"테스트 생성 실패: {(gen or {}).get('detail', '')[:200]}"
        return r
    log("dryrun", "테스트 생성 완료")

    for sc in SCENARIOS:
        impl = spawn(impl_prompt(task_type, data, sc, spec), f"impl-{sc}")
        entry = {"scenario": sc, "impl_ok": bool((impl or {}).get("ok"))}
        r.steps.append({"step": f"impl-{sc}", **(impl or {})})
        if entry["impl_ok"]:
            if rubric is not None:
                entry["rubric_issues"] = list(rubric(sc) or [])
            if with_ue_test and build is not None:
                entry["ue_test"] = dict(build(sc) or {})
        r.scenarios.append(entry)
        log("dryrun", f"{sc} — impl_ok={entry['impl_ok']}")

    r.verdict = compute_verdict(r.scenarios, with_ue_test)
    # 🔴 `ok` 는 *"하니스가 완주했다"* 이지 *"red-green 이 닫혔다"* 가 아니다 — 둘을 섞으면
    #    problem 이 있는 런이 성공으로 보인다.
    r.ok = all(s["impl_ok"] for s in r.scenarios)
    return r
