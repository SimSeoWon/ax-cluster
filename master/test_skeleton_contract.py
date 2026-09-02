"""골조 태그 계약 게이트 — `[DOC]` 보존 · `[PSEUDO]` 는 빈 자리 (실측 2026-09-03).

## 무엇이 났나

`.33` 골조가 **본문까지 다 써 놓고** 그 위에 `[PSEUDO]` 를 붙였다(13/13 실코드). 결과:

    · 워커는 채울 게 없다
    · `[PSEUDO]` 를 지우면 설명이 사라지고, 안 지우면 **층1 이 막는다**
    · 실제로 층1 이 막았다 — 워커 한 대의 추론값을 통째로 버린 뒤에 드러났다

[중요] 그때 `[DOC]` 은 **헤더에 있었다** — 즉 종전 검사(`_has_doc`)만으로는 게이트가 돌았어도
통과했다. 이 파일이 고정하는 것은 **양방향**이다:

    ① 본문이 실린 `[PSEUDO]` 를 **막는다**
    ② [중요] **정상 골조는 통과한다** — 프롬프트 규칙 2가 요구하는 placeholder `return` 을
       위반으로 세면 정상 파이프라인이 전부 죽는다. 그쪽이 더 비싼 실패다

`python3 master/test_skeleton_contract.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import skeleton_gate as G                        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── 정상 골조 — 프롬프트 규칙 2 그대로 ───────────────────────────────────────
GOOD_H = """// [DOC] 상호작용 대상 컴포넌트. 서브시스템이 중앙에서 판정하므로 틱이 없다.
#pragma once
UCLASS()
class UNSInteractableComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    // [DOC] 이 대상이 지금 상호작용 가능한가. 거리는 서브시스템이 이미 걸렀다.
    bool CanBeInteractedBy(const UNSInteractorComponent* Interactor) const;
    // [STATE] 하이라이트를 붙일 컴포넌트. 비면 오너 루트로 대체한다.
    UPROPERTY(EditAnywhere) USceneComponent* HighlightTarget;
};
"""

GOOD_CPP = """#include "NSInteractableComponent.h"

void UNSInteractableComponent::BeginPlay()
{
    // [DOC] 시작 상태는 항상 Idle 이고, 서브시스템 등록은 EndPlay 의 해제와 짝이다.
    // [PSEUDO] 여기를 채워라
}

bool UNSInteractableComponent::CanBeInteractedBy(const UNSInteractorComponent* Interactor) const
{
    // [DOC] 비활성·파괴 중이면 false. 거리 판정은 하지 않는다 (서브시스템 소관).
    // [PSEUDO] 여기를 채워라
    return false;
}

FVector UNSInteractableComponent::GetFocusLocation() const
{
    // [DOC] 하이라이트 대상의 월드 위치. 없으면 오너 루트.
    // [PSEUDO] 여기를 채워라
    return {};
}

void UNSInteractableComponent::EndPlay(EEndPlayReason::Type EndPlayReason)
{
    // [DOC] 서브시스템에서 등록 해제한다.
    // [PSEUDO] 여기를 채워라

    Super::EndPlay(EndPlayReason);
}

void UNSInteractableComponent::TickComponent(float DT, ELevelTick T, FActorComponentTickFunction* F)
{
    // [DOC] 여기서는 아무것도 하지 않는다 — 판정은 서브시스템이 중앙에서 한다.
    // [PSEUDO] 여기를 채워라
    Super::TickComponent(DT, T, F);
}
"""

# ── 실측 2026-09-03 의 모양 — 본문이 이미 실렸다 ─────────────────────────────
BAD_CPP = """#include "NSInteractionSubsystem.h"

void UNSInteractionSubsystem::RegisterInteractable(UNSInteractableComponent* Interactable)
{
    // [PSEUDO] Interactables 에 중복 없이 추가한다. 파괴된 엔트리 청소는 여기서 하지 않는다 —
    // Tick 쪽에서 TWeakObjectPtr::Get() 이 IsValid 로 걸러낸다.
    if (Interactable)
    {
        Interactables.AddUnique(Interactable);
    }
}

void UNSInteractionSubsystem::UnregisterInteractable(UNSInteractableComponent* Interactable)
{
    // [PSEUDO] 레지스트리에서 제거한다.
    Interactables.RemoveSingleSwap(Interactable);
}
"""


def test_good_skeleton_passes():
    """[중요] **이쪽이 더 중요하다** — 오탐이면 파이프라인이 전부 죽는다."""
    why = G.check_tags({"X.h": GOOD_H, "X.cpp": GOOD_CPP})
    check("[중요] **정상 골조는 통과한다**", why == "", why[:160])
    check("  placeholder `return false;` 를 본문으로 세지 않는다",
          not any("return false" in h for h in G.pseudo_with_code({"X.cpp": GOOD_CPP})),
          str(G.pseudo_with_code({"X.cpp": GOOD_CPP})))
    check("  `return {};` 도 마찬가지", not G.pseudo_with_code({"X.cpp": GOOD_CPP}),
          str(G.pseudo_with_code({"X.cpp": GOOD_CPP})))
    check("  void 함수의 주석 단독도 통과", not G.pseudo_with_code(
        {"V.cpp": "void A::B()\n{\n    // [PSEUDO] 여기를 채워라\n}\n"}))
    # 🔴 실측 2026-09-03 — 이것을 빠뜨려 **정상 골조 2건을 막았다**
    check("[중요] **`Super::` 호출은 본문이 아니다** (UE5 가 요구하는 뼈대)",
          not G.pseudo_with_code({"E.cpp": "void A::EndPlay(T R)\n{\n"
                                           "    // [PSEUDO] 여기를 채워라\n\n"
                                           "    Super::EndPlay(R);\n}\n"}),
          str(G.pseudo_with_code({"E.cpp": "void A::EndPlay(T R)\n{\n"
                                           "    // [PSEUDO] 여기를 채워라\n\n"
                                           "    Super::EndPlay(R);\n}\n"})))
    check("  `return Super::…;` 도 통과",
          not G.pseudo_with_code({"R.cpp": "bool A::B()\n{\n"
                                           "    // [PSEUDO] 채워라\n    return Super::B();\n}\n"}))
    check("[중요] **`Super::` 뒤에 실코드가 오면 여전히 잡는다**",
          len(G.pseudo_with_code({"X.cpp": "void A::EndPlay(T R)\n{\n"
                                           "    // [PSEUDO] 채워라\n    Super::EndPlay(R);\n"
                                           "    DoRealWork();\n}\n"})) == 1)


def test_body_already_written_is_blocked():
    hits = G.pseudo_with_code({"S.cpp": BAD_CPP})
    check("[중요] 본문이 실린 `[PSEUDO]` 를 잡는다", len(hits) == 2, str(hits))
    why = G.check_tags({"S.cpp": BAD_CPP, "S.h": "// [DOC] 서브시스템\n"})
    check("  게이트가 막는다", "이미 본문이 있다" in why, why[:120])
    check("[중요] **사유가 무엇을 고쳐야 하는지 말한다**",
          "[DOC]" in why and "비워" in why, why[:200])
    check("  자리를 찍는다 (파일:줄)", "S.cpp:" in why, why[-120:])


def test_doc_zero_is_blocked_first():
    """[주의] 순서가 계약이다 — 계약이 아예 없는 것이 더 근본적이다."""
    why = G.check_tags({"X.cpp": "void A::B()\n{\n    // [PSEUDO] 채워라\n}\n"})
    check("`[DOC]` 0개를 먼저 막는다", "`[DOC]` 0개" in why, why[:120])
    check("  그때는 본문 사유를 내지 않는다", "이미 본문이 있다" not in why, why[:120])


def test_doc_in_header_is_not_enough():
    """🔴 [중요] **실측이 정확히 이 모양이었다** — `[DOC]` 은 헤더에 있었다.

    종전 검사(`_has_doc`)만으로는 게이트가 돌았어도 통과했다. 그것이 이 테스트의 존재 이유다.
    """
    files = {"S.h": "// [DOC] 서브시스템 계약\n", "S.cpp": BAD_CPP}
    check("종전 검사는 통과한다 (그래서 못 잡았다)", G._has_doc(files))
    check("[중요] **새 검사가 잡는다**", "이미 본문이 있다" in G.check_tags(files),
          G.check_tags(files)[:120])


def test_pseudo_depth_and_edges():
    check("`[PSEUDO:2]` 도 같은 규칙",
          len(G.pseudo_with_code({"D.cpp": "void A::B()\n{\n    // [PSEUDO:2] 채워라\n"
                                           "    DoIt();\n}\n"})) == 1)
    check("연속 마커 사이는 빈 것으로 본다",
          not G.pseudo_with_code({"C.cpp": "void A::B()\n{\n    // [PSEUDO] 하나\n"
                                           "    // [PSEUDO] 둘\n}\n"}))
    check("보존 태그는 본문이 아니다",
          not G.pseudo_with_code({"K.cpp": "void A::B()\n{\n    // [PSEUDO] 채워라\n"
                                           "    // [STATE] 설명\n    // [BIND] 바인딩\n}\n"}))
    check("전처리기도 본문이 아니다",
          not G.pseudo_with_code({"P.cpp": "void A::B()\n{\n    // [PSEUDO] 채워라\n"
                                           "#if WITH_EDITOR\n#endif\n}\n"}))
    check("빈 입력은 조용히 빈 목록", G.pseudo_with_code({}) == [])
    check("[주의] 파일이 없으면 사유를 낸다 (통과가 아니다)",
          "잴 것이 없다" in G.check_tags({}), G.check_tags({}))


def main() -> int:
    for fn in (test_good_skeleton_passes, test_body_already_written_is_blocked,
               test_doc_zero_is_blocked_first, test_doc_in_header_is_not_enough,
               test_pseudo_depth_and_edges):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_skeleton_contract: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
