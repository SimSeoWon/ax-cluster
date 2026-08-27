"""골조 + 인터페이스 동결 (중 1.1).

[중요] 지키는 계약은 **동결**이다 — 원전이 *"이건 강제"* 라고 못박은 것(사용자 2026-06-21).
클래스 단위 분할은 파일 충돌만 막고, 인터페이스 충돌은 이 동결만이 막는다.

`.venv/bin/python master/test_skeleton.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import skeleton as S      # noqa: E402

PASS = FAIL = 0

HEADER = """// [DOC] 미션 태스크 실행기 — 상태 기계는 Step 으로만 전진한다
#pragma once
#include "CoreMinimal.h"
#include "MissionTaskExecutor.generated.h"

UCLASS(BlueprintType)
class MISSIONRUNTIME_API UMissionTaskExecutor : public UActorComponent
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable)
    void StartTask(int32 InStep);

    virtual void TickComponent(float DeltaTime) override;

    // [STATE] 현재 진행 단계. 0 은 미시작이다
    UPROPERTY(VisibleAnywhere)
    int32 Step = 0;

    int32 GetStep() const { return Step; }
};
"""


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_frozen_decls_picks_the_contract() -> None:
    """동결 대상은 매크로·class 선언·함수 시그니처다."""
    d = S.frozen_decls(HEADER)
    joined = " || ".join(sorted(d))
    check("UCLASS 를 잡는다", any(x.startswith("UCLASS") for x in d), joined)
    # [중요] 키는 `GENERATED_BODY()` — 그 줄엔 `;` 도 `{` 도 없으니 괄호가 남는 것이 정상이다
    check("GENERATED_BODY 를 잡는다", any(x.startswith("GENERATED_BODY") for x in d), joined)
    check("class 선언을 잡는다", any(x.startswith("class MISSIONRUNTIME_API") for x in d), joined)
    check("함수 시그니처를 잡는다", any("StartTask" in x for x in d), joined)
    check("override 시그니처도 잡는다", any("TickComponent" in x for x in d), joined)
    # [중요] 태그는 계약이 아니다 — 주석을 지우고 뽑으므로 섞이면 안 된다
    check("[중요] 주석·태그가 키에 안 섞인다",
          not any("[DOC]" in x or "[STATE]" in x for x in d), joined)


def test_filling_a_body_is_not_a_violation() -> None:
    """[중요] 인라인 `[PSEUDO]` 본문을 채우는 것은 정상이다 — `;` → `{…}` 가 키를 안 깬다."""
    skel = "void UFoo::Bar(int32 X);"
    impl = "void UFoo::Bar(int32 X)\n{\n    Step = X;\n}"
    check("본문 채움은 위반 아님", S.violation(skel, impl) == "", S.violation(skel, impl))


def test_adding_is_allowed_changing_is_not() -> None:
    """[중요] 방향이 핵심이다 — 추가는 허용, 변경·삭제는 위반(`original ⊆ new`)."""
    added = HEADER.replace("    int32 GetStep() const { return Step; }",
                           "    int32 GetStep() const { return Step; }\n"
                           "    void Helper(float Dt);")
    check("멤버 추가는 허용", S.violation(HEADER, added) == "", S.violation(HEADER, added))

    changed = HEADER.replace("void StartTask(int32 InStep);", "void StartTask(float InStep);")
    v = S.violation(HEADER, changed)
    check("[중요] 시그니처 변경은 위반", "StartTask" in v, v)

    removed = HEADER.replace("    virtual void TickComponent(float DeltaTime) override;\n", "")
    v2 = S.violation(HEADER, removed)
    check("[중요] 선언 삭제는 위반", "TickComponent" in v2, v2)


def test_ue_declaration_macro_families() -> None:
    """[중요] 원전 목록의 구멍 — 실측(헤더 857개)으로 메운 것들."""
    # [중요] 매크로는 **줄 머리**에 있어야 잡힌다 — 실제 코드의 모양 그대로 쓴다
    #    (`WidgetEventTags.h` 는 namespace 를 열고 다음 줄에 탭 들여쓴 매크로를 둔다).
    #    한 줄에 `namespace T { MACRO(...); }` 로 몰아 쓰면 안 잡히는데, 그건 실재하지 않는 모양이고
    #    줄 단위 스캔의 알려진 한계다.
    text = ("GENERATED_USTRUCT_BODY()\n"
            "DECLARE_LOG_CATEGORY_EXTERN(LogMS, Log, All);\n"
            "DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnX, int32, V);\n"
            "namespace T\n{\n\tUE_DECLARE_GAMEPLAY_TAG_EXTERN(TAG_A);\n}\n")
    d = S.frozen_decls(text)
    for want in ("GENERATED_USTRUCT_BODY", "DECLARE_LOG_CATEGORY_EXTERN",
                 "DECLARE_DYNAMIC_MULTICAST_DELEGATE", "UE_DECLARE_GAMEPLAY_TAG_EXTERN"):
        check(f"{want} 를 잡는다", any(x.startswith(want) for x in d), str(sorted(d)))


def test_inline_log_is_not_frozen() -> None:
    """[중요] 대문자 매크로를 통째로 받으면 안 된다 — `UE_LOG` 가 헤더 인라인 본문에 23회 있었다.

    동결하면 워커가 로그 문구만 고쳐도 위반이 뜬다. *정상 작업을 막는 게이트가 통과시키는
    게이트보다 나쁘다.*
    """
    before = 'void Log() const { UE_LOG(LogMS, Log, TEXT("before")); }'
    after = 'void Log() const { UE_LOG(LogMS, Log, TEXT("after")); }'
    d = S.frozen_decls(before)
    check("UE_LOG 은 동결 대상이 아니다", not any("UE_LOG" in x for x in d), str(sorted(d)))
    check("[중요] 로그 문구만 바꾸면 위반이 아니다", S.violation(before, after) == "",
          S.violation(before, after))


def test_statement_is_not_a_signature() -> None:
    """`return Foo();` 가 선언으로 오인되면 본문을 쓸 때마다 위반이 뜬다."""
    body = "int32 UFoo::Bar()\n{\n    return Baz();\n    if (Check()) { Other(); }\n}"
    d = S.frozen_decls(body)
    check("본문 문장은 동결 대상이 아니다",
          not any("return" in x or x.startswith("if") for x in d), str(sorted(d)))


def test_depths_and_pseudo() -> None:
    """`[PSEUDO:N]` 은 파일 내 순차 분할(소 1.2.4), 번호 없으면 단일 태스크."""
    plain = "// [PSEUDO] 로드한다\n// [PSEUDO] 갱신한다"
    check("번호 없으면 뎁스 없음", S.depths(plain) == [], str(S.depths(plain)))
    check("PSEUDO 개수를 센다", S.pseudo_count(plain) == 2, str(S.pseudo_count(plain)))
    deep = "// [PSEUDO:1] 기반\n// [PSEUDO:2] 중간\n// [PSEUDO:1] 기반 더\n// [PSEUDO:3] 통합"
    check("뎁스를 정렬해 모은다", S.depths(deep) == [1, 2, 3], str(S.depths(deep)))


def test_parse_files_rejects_unrequested_paths() -> None:
    """[중요] 요청하지 않은 경로를 받으면 `check_disjoint` 의 전제가 깨진다 — 버린다."""
    raw = ("=== FILE: Source/A/Foo.h ===\n#pragma once\nclass AFoo {};\n"
           "=== FILE: Source/A/Bonus.h ===\nclass ABonus {};\n")
    files, notes = S.parse_files(raw, want=["Source/A/Foo.h"])
    check("요청한 것만 받는다", list(files) == ["Source/A/Foo.h"], str(list(files)))
    check("버린 것을 말한다", any("Bonus" in n for n in notes), str(notes))


def test_parse_files_reports_missing_and_fence() -> None:
    raw = ("=== FILE: Source/A/Foo.h ===\nclass AFoo {};\n"
           "=== FILE: Source/A/Foo.cpp ===\n```cpp\nvoid X(){}\n```\n")
    files, notes = S.parse_files(raw, want=["Source/A/Foo.h", "Source/A/Foo.cpp",
                                           "Source/A/Bar.h"])
    check("빠진 파일을 말한다", any("Bar.h" in n for n in notes), str(notes))
    # [중요] 중간 펜스는 모델이 설명을 섞었다는 뜻이다 — 조용히 지우지 않고 보고한다
    check("[중요] 남은 펜스를 보고한다", any("펜스" in n for n in notes), str(notes))

    single = "#pragma once\nclass AFoo {};"
    f2, n2 = S.parse_files(single, want=["Source/A/Foo.h"])
    check("대상 하나면 마커 없어도 받는다", f2.get("Source/A/Foo.h", "").startswith("#pragma"))
    check("관대하게 받은 것을 말한다", any("마커 없음" in n for n in n2), str(n2))

    try:
        S.parse_files("아무 말", want=["a.h", "b.h"])
        check("[중요] 마커 없이 여러 파일은 거부", False)
    except S.SkeletonError:
        check("[중요] 마커 없이 여러 파일은 거부", True)


def test_skeleton_is_fail_closed() -> None:
    """[중요] `[PSEUDO]` 0개거나 동결 0개면 골조가 아니다."""
    good = S.Skeleton(stem="Foo", files={"a.h": HEADER + "\n// [PSEUDO] 채운다"},
                      frozen=S.frozen_decls(HEADER), pseudo=1)
    check("정상 골조는 ok", good.ok, good.summary)

    done = S.Skeleton(stem="Foo", files={"a.h": HEADER}, frozen=S.frozen_decls(HEADER),
                      pseudo=0)
    check("[중요] PSEUDO 0 은 골조가 아니다", not done.ok, done.summary)

    naked = S.Skeleton(stem="Foo", files={"a.h": "// [PSEUDO] 뭔가"}, frozen=set(), pseudo=1)
    check("[중요] 동결 0 은 골조가 아니다", not naked.ok, naked.summary)
    check("요약이 위험을 드러낸다", "[중요]" in naked.summary, naked.summary)


def test_contracts_text_carries_the_tag_rules() -> None:
    """계약 텍스트가 워커가 읽는 유일한 규칙이다 — 태그 두 종류가 여기 있어야 한다."""
    sk = S.Skeleton(stem="Foo", files={"a.h": HEADER}, frozen=S.frozen_decls(HEADER), pseudo=1)
    c = sk.contracts()
    check("동결 선언이 실린다", "GENERATED_BODY" in c)
    check("추가는 허용이라고 말한다", "Adding new" in c, c[:200])
    for tag in ("[PSEUDO]", "[DOC]", "[BIND]"):
        check(f"태그 규칙에 {tag}", tag in c)
    check("빈 동결이면 계약도 빈다", S.Skeleton(stem="x").contracts() == "")


def test_header_is_the_source_of_freeze() -> None:
    """[중요] 동결의 원천은 헤더다 — `.cpp` 의 인라인 정의는 계약이 아니다."""
    sk = S.Skeleton(stem="Foo", files={"Source/A/Foo.h": HEADER,
                                       "Source/A/Foo.cpp": "void UMissionTaskExecutor::Extra(){}"})
    check("헤더만 골라낸다", "GENERATED_BODY" in sk.header_text)
    check("cpp 는 안 섞인다", "Extra" not in sk.header_text)
    check("헤더 판정", S.is_header("a/b/Foo.h") and not S.is_header("a/b/Foo.cpp"))


def test_prompt_grounds_and_states_porting_rules() -> None:
    spec = S.SkeletonSpec(stem="Foo", files=["Source/A/Foo.h", "Source/A/Foo.cpp"],
                          classes=["UFoo"], instruction="미션 태스크 실행기를 만든다")
    p = S.build_prompt(spec, declarations="=== DECLARATIONS ===\nint32 Step;",
                       norms="=== DOMAIN NORMS ===\ninvariant X")
    check("요청 파일을 순서대로 싣는다", p.index("Source/A/Foo.h") < p.index("Source/A/Foo.cpp"))
    # [중요] 베껴야 할 텍스트가 지시에서 멀면 모델은 기억에서 꺼낸다 (#26 실측)
    check("[중요] 선언부가 규범보다 지시에 가깝다",
          p.index("DECLARATIONS") > p.index("DOMAIN NORMS"))
    check("선언부가 TASK 바로 앞", p.index("DECLARATIONS") < p.index("TASK:"))
    check("본문 금지를 지시한다", "[PSEUDO]" in p and "Do NOT write real logic" in p)
    check("getter/setter 주석 금지", "getters/setters" in p)

    port = S.SkeletonSpec(stem="Foo", files=["Source/A/Foo.h"], classes=["UFoo"],
                          instruction="포팅한다", source_files=["// 옛 구현"])
    pp = S.build_prompt(port)
    check("[중요] 포팅 원본은 정답이 아니라고 말한다", "NOT the answer" in pp)
    check("[중요] 원본 편집 금지를 말한다", "never edit it" in pp)


def test_spec_validation() -> None:
    for bad, why in ((S.SkeletonSpec(stem="", files=["a.h"], instruction="x"), "stem"),
                     (S.SkeletonSpec(stem="F", files=[], instruction="x"), "파일"),
                     (S.SkeletonSpec(stem="F", files=["a.h"], instruction=""), "지시")):
        try:
            bad.validate()
            check(f"[중요] {why} 없으면 거부", False)
        except S.SkeletonError:
            check(f"[중요] {why} 없으면 거부", True)
    ok = S.SkeletonSpec(stem="F", files=["Source/A/F.h", "Source/A/F.cpp"], instruction="x")
    ok.validate()
    check("헤더만 골라낸다", ok.headers == ["Source/A/F.h"], str(ok.headers))


def test_register_wiring() -> None:
    """소 1.1.4 — 등록부가 빈 골조를 채운다. [중요] **큐를 만지기 전에** 끝낸다."""
    from master.work import register as R

    made = S.Skeleton(stem="Foo", files={"Source/A/Foo.h": HEADER + "\n// [PSEUDO] x"},
                      frozen=S.frozen_decls(HEADER), pseudo=1, depth_set=[1, 2])
    calls: list = []

    def fake(paths, spec):
        calls.append(spec.stem)
        return made

    posted: list = []

    def poster(url, payload):
        posted.append((url, payload))
        return {"work_id": "w1", "task_id": f"t{len(posted)}"}

    # ① instruction 이 있고 골조가 없으면 생성한다
    spec = R.TaskSpec(stem="Foo", classes=["UFoo"], target_files=["Source/A/Foo.h"],
                      instruction="미션 실행기를 만든다")
    got = R._fill_skeletons([spec], paths=None, make_skeleton=fake)
    check("생성했다고 보고한다", got == ["Foo"], str(got))
    check("골조가 텍스트로 실린다", "=== FILE: Source/A/Foo.h ===" in spec.skeleton)
    check("[중요] 동결 계약도 같이 채운다", "FROZEN INTERFACE" in spec.contracts)
    check("뎁스를 넘긴다", spec.depth_set == [1, 2], str(spec.depth_set))

    # ② 이미 골조가 있으면 손대지 않는다 (하위 호환)
    calls.clear()
    kept = R.TaskSpec(stem="Bar", classes=["UBar"], target_files=["b.h"],
                      skeleton="사람이 쓴 골조", instruction="무시돼야 한다")
    R._fill_skeletons([kept], paths=None, make_skeleton=fake)
    check("[중요] 사람이 쓴 골조가 이긴다", kept.skeleton == "사람이 쓴 골조")
    check("생성기를 부르지 않는다", calls == [], str(calls))

    # ③ 골조도 instruction 도 없으면 그냥 넘어간다 — 골조 없는 등록은 정상 경로다
    plain = R.TaskSpec(stem="Baz", classes=["UBaz"], target_files=["c.h"])
    check("둘 다 없으면 건너뛴다", R._fill_skeletons([plain], paths=None,
                                                     make_skeleton=fake) == [])
    check("골조는 여전히 빈다", plain.skeleton == "")

    # ④ [중요] 골조가 아니면 등록하지 않는다 — 큐에 아무것도 안 들어가야 한다
    bad = S.Skeleton(stem="Bad", files={"c.h": "완성된 파일"}, frozen=set(), pseudo=0)
    posted.clear()
    try:
        R.register_work("제목", [R.TaskSpec(stem="Bad", classes=["UBad"],
                                            target_files=["c.h"], instruction="만든다")],
                        paths=None, target_repo="r", poster=poster,
                        make_skeleton=lambda p, s: bad)
        check("[중요] 골조 아닌 것은 거부", False)
    except R.RegisterError as e:
        check("[중요] 골조 아닌 것은 거부", "골조 생성 실패" in str(e), str(e))
    check("[중요] 큐를 만지지 않았다", posted == [], str(posted))


def test_gate_mode_is_uht_by_default() -> None:
    """[중요] `#317` 미결 ② — 골조 게이트의 기본은 **UHT** 다 (구현·실측 2026-08-28).

    골조 단계에 풀 빌드는 성립하지 않는다 — 골조가 헤더 계약이면 정의 없는 `UFUNCTION`
    하나로 `LNK2019` 가 나고, 그건 *골조가 깨진 것*이 아니라 *미완성인 것*이다.
    """
    from master.work import skeleton_gate as G
    from master import layer3_verify as L

    seen = {}

    def fake_build(host, user, bb, target, up, **kw):
        seen["fn"] = "full"
        return L.BuildResult(passed=True, failure=None, result="Succeeded")

    sk = S.Skeleton(stem="P", files={"a.h": "x"}, frozen={"k"}, pseudo=1)

    class F:
        host, user, ue5, windows = "h", "u", r"C:\UE\Engine\Binaries\Win64\UnrealEditor-Cmd.exe", True

    # 기본 모드가 uht 인지 — 주입 없이 부르면 `run_uht_on_workshop` 이 골라져야 한다
    import inspect
    src = inspect.getsource(G.run)
    check("[중요] 기본값이 MODE_UHT 다", "mode: str = MODE_UHT" in src, src[:200])
    check("  uht 면 run_uht_on_workshop 을 고른다",
          "run_uht_on_workshop if mode == MODE_UHT" in src, src[:400])
    check("  full 이면 옛 경로가 남아 있다 (되돌릴 자리)",
          "run_build_on_workshop" in src and G.MODE_FULL == "full")

    # 모르는 모드는 조용히 넘기지 않는다
    try:
        G.run(F(), sk, tree="T", project="P", mode="maybe")
        check("모르는 모드 거부", False, "통과해 버렸다")
    except ValueError as e:
        check("모르는 모드 거부", "uht|full" in str(e), str(e))

    # 판정 결과에 무엇으로 쟀는지 남는다 — 「안 돌린 것 ≠ 통과」와 같은 결
    g = G.run(F(), sk, tree="T", project="P", writer=lambda *a, **k: None,
              builder=fake_build, mode=G.MODE_FULL)
    check("[주의] 무엇으로 쟀는지 결과에 남는다", g.mode == "full", str(g.mode))


def test_uht_command_shape() -> None:
    """[주의] 중첩 인용 — `-Target="…"` 안에 `-Project="…"` 가 들어간다 (실측으로 고른 형태)."""
    from master import layer3_verify as L
    cmd = L.build_uht_command(r"C:\UE\Build.bat", "NSEditor", r"E:\t\NS.uproject")
    check("UHT 모드를 쓴다", "-Mode=UnrealHeaderTool" in cmd, cmd)
    check("타깃·플랫폼·구성이 -Target 안에 있다",
          '-Target="NSEditor Win64 Development' in cmd, cmd)
    check("[주의] uproject 가 안쪽 따옴표로 감싸인다 (공백 있는 경로 대비)",
          '-Project="E:\\t\\NS.uproject"' in cmd, cmd)
    check("[중요] 풀 빌드 명령과 다르다", cmd != L.build_build_command(
        r"C:\UE\Build.bat", "NSEditor", r"E:\t\NS.uproject"))


def main() -> int:
    for fn in (test_gate_mode_is_uht_by_default, test_uht_command_shape,
               test_frozen_decls_picks_the_contract, test_ue_declaration_macro_families,
               test_inline_log_is_not_frozen, test_filling_a_body_is_not_a_violation,
               test_adding_is_allowed_changing_is_not, test_statement_is_not_a_signature,
               test_depths_and_pseudo, test_parse_files_rejects_unrequested_paths,
               test_parse_files_reports_missing_and_fence, test_skeleton_is_fail_closed,
               test_contracts_text_carries_the_tag_rules, test_header_is_the_source_of_freeze,
               test_prompt_grounds_and_states_porting_rules, test_spec_validation,
               test_register_wiring):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_skeleton: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
