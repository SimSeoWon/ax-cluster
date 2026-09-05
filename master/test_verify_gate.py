"""사실 게이트 오탐 (`#270`) — **실측 사례 그대로** 재는 회귀 칸.

[중요] NS 온보딩 최초 합성에서 **4그룹 중 3이 거부**됐고(통과 25%) 그중 **둘이 오탐**이었다.
근거를 파일·행으로 확인했다:

    "All"       NS.h:1 `// Copyright Epic Games, Inc. All Rights Reserved.`   ← 저작권 헤더
                [중요] 그런데 NS.h:8 `DECLARE_LOG_CATEGORY_EXTERN(LogNS, Log, All)` 로 **코드에도
                있다** — 그래도 잡혔다. 원인은 `verify()` 가 파일별 `comment_only` 를 **합집합**만
                해서, *같은 그룹의 다른 파일에서 살아 있는* 식별자를 유령으로 센 것이다
    "GameMode"  NSGameMode.h:10 `*  Simple GameMode for a third person game`  ← 설명 주석
                실제 클래스는 `ANSGameMode` — 문서가 접두를 떼고 쓰는 것이 자연스럽다
    "StateTree" CombatAIController.h:12 실제 심볼은 `UStateTreeAIComponent`

[주의] **셋 중 하나는 진짜 위반이다** — `ACombatAIController` 미언급. 그것은 계속 거부돼야 한다.

`python3 master/test_verify_gate.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import verify as V                        # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


LIC = "// Copyright Epic Games, Inc. All Rights Reserved.\n"

NS_H = LIC + '''
#pragma once
#include "CoreMinimal.h"

/** Main log category used across the project */
DECLARE_LOG_CATEGORY_EXTERN(LogNS, Log, All);
'''
NS_CPP = LIC + '''
#include "NS.h"
IMPLEMENT_PRIMARY_GAME_MODULE( FDefaultGameModuleImpl, NS, "NS" );
DEFINE_LOG_CATEGORY(LogNS)
'''

GM_H = LIC + '''
#pragma once
#include "GameFramework/GameModeBase.h"

/**
 *  Simple GameMode for a third person game
 */
UCLASS(abstract)
class ANSGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    ANSGameMode();
};
'''

AI_H = LIC + '''
#pragma once
class UStateTreeAIComponent;

/**  A basic AI Controller capable of running StateTree  */
UCLASS(abstract)
class ACombatAIController : public AAIController
{
    GENERATED_BODY()
};
'''


def _doc(summary, related="LogNS: Source/NS/NS.h"):
    return ("---\ntags: [x]\ncategory: a/b/c\nrelated_classes:\n  - " + related
            + "\n---\n\n## 요약\n" + summary + "\n\n## 개선 필요 사항\n없음\n")


# ── 오탐 둘은 통과해야 한다 ────────────────────────────────────────

def test_license_header_not_identifier() -> None:
    """[중요] 저작권 머리말의 낱말은 식별자가 아니다."""
    only = V.comment_only(NS_CPP)
    for w in ("All", "Copyright", "Epic", "Games", "Reserved", "Rights"):
        check(f"저작권 낱말이 유령 풀에 없다: {w}", w not in only, str(sorted(only)))
    # [중요] 산문 낱말은 **모양 규칙**으로 아예 후보가 아니다 (`#270`) — `Main`·`category` 는
    #    식별자가 아니다. 그래서 저작권 제외와 무관하게 유령 풀에 안 들어간다.
    check("산문 낱말은 후보가 아니다", not (V.identifiers("Main category project the used")),
          str(V.identifiers("Main category project")))
    check("[주의] All 도 모양 규칙에서 빠진다 (대문자 1개)",
          not V._SHAPED_RE.search("All"))


def test_cross_file_live_wins() -> None:
    """[중요] 그룹의 다른 파일에서 살아 있으면 유령이 아니다 — 이것이 실제 원인이었다.

    [주의] 실측 사례의 `All` 은 이제 **모양 규칙**에서도 빠지지만, 교차 파일 문제는 **식별자
    모양 이름에서도 그대로** 난다 — 헤더에 선언된 클래스를 `.cpp` 가 주석으로만 언급하는 것이
    흔하다. 그래서 모양 있는 이름으로 잰다.
    """
    H = LIC + "class UWidgetHost { void Attach(); };\n"
    C = LIC + "// UWidgetHost 는 여기서 붙인다\n#include \"H.h\"\nvoid f() {}\n"
    check("전제: .cpp 만 보면 유령이다", "UWidgetHost" in V.comment_only(C))
    check("전제: .h 에서는 살아 있다",
          "UWidgetHost" in V.identifiers(V.strip_comments(H)[0]))
    r = V.verify(_doc("UWidgetHost 는 위젯을 붙인다.", related="UWidgetHost: H.h"),
                 sources={"H.h": H, "C.cpp": C}, declared=["UWidgetHost"])
    check("[중요] 그룹 전체로 보면 통과", r.ok, str(r.ghosts))
    # 대조군 — .cpp 만 주면 (그룹이 아니면) 그대로 잡힌다
    r2 = V.verify(_doc("UWidgetHost 는 위젯을 붙인다.", related="UWidgetHost: H.h"),
                  sources={"C.cpp": C})
    check("(대조군) .cpp 단독이면 잡힌다", not r2.ok and "UWidgetHost" in r2.ghosts, str(r2.ghosts))
    # 실측 사례도 통과한다
    r3 = V.verify(_doc("NS 모듈은 All 수준의 로그 카테고리 LogNS 를 선언한다."),
                  sources={"NS.h": NS_H, "NS.cpp": NS_CPP})
    check("[중요] 실측 오탐 1 (All) 통과", r3.ok, str(r3.ghosts))


def test_ue_prefix_substring() -> None:
    """[중요] 문서가 UE 접두를 떼고 쓰는 것은 위반이 아니다."""
    r = V.verify(_doc("GameMode 는 3인칭 게임의 기본 규칙을 정한다.",
                      related="ANSGameMode: Source/NS/NSGameMode.h"),
                 sources={"NSGameMode.h": GM_H}, declared=["ANSGameMode"])
    check("[중요] 오탐 2 (GameMode ← ANSGameMode) 통과", r.ok, str(r.ghosts))
    r2 = V.verify(_doc("ACombatAIController 는 StateTree 를 구동하는 AI 컨트롤러다.",
                       related="ACombatAIController: .../CombatAIController.h"),
                  sources={"CombatAIController.h": AI_H}, declared=["ACombatAIController"])
    check("StateTree ← UStateTreeAIComponent 통과", r2.ok, str(r2.ghosts))


# ── 진짜 위반은 계속 잡혀야 한다 ───────────────────────────────────

def test_real_violation_still_caught() -> None:
    """[중요] **완료 조건 3** — 오탐을 고치려고 구멍을 내지 않았음을 보인다."""
    # [주의] `related_classes` 키도 「언급」으로 세므로, 미언급을 재려면 거기에도 없어야 한다
    r = V.verify(_doc("이 파일은 로그 카테고리를 선언한다.", related="LogNS: x.h"),
                 sources={"CombatAIController.h": AI_H}, declared=["ACombatAIController"])
    check("[중요] 실측 클래스 미언급은 계속 거부", not r.ok and not r.mentioned_declared,
          r.reason)

    # 2026-08-12 의 「없는 enum 멤버」 부류 — 지어낸 이름은 어떤 live 의 부분열도 아니다
    SRC = LIC + '''
enum class EMode : uint8 { Idle, Run };
// enum class EOld : uint8 { Legacy };
class UThing { void Go(); };
'''
    # [중요] **이 게이트의 범위를 정확히 적어 둔다** (2026-08-22 에 내가 오해했다):
    #    `ghosts` 는 **주석에 있는 이름**만 잡는다. 아무 데도 없는 이름을 지어내면 이 검사로는
    #    안 잡힌다 — 그것은 grounding(프롬프트에 선언부를 주는 것)의 몫이다(실측 2026-08-12:
    #    선언부가 없으면 5개 후보 중 4가 없는 enum 멤버를 놓쳤고, 주면 전부 잡았다).
    #    이 칸은 그 경계를 **문서화**한다 — 감추면 다음 사람이 또 오해한다.
    r2 = V.verify(_doc("UThing 은 EMode::Invented 로 상태를 바꾼다.",
                       related="UThing: T.h"), sources={"T.h": SRC}, declared=["UThing"])
    check("[주의] 아무 데도 없는 이름은 이 검사의 범위 밖이다 (grounding 몫)",
          r2.ok and not r2.ghosts, f"ok={r2.ok} ghosts={r2.ghosts}")
    r3 = V.verify(_doc("UThing 은 EOld 를 쓴다.", related="UThing: T.h"),
                  sources={"T.h": SRC}, declared=["UThing"])
    check("[중요] 주석 처리된 enum 을 살아 있다고 하면 잡힌다",
          not r3.ok and "EOld" in r3.ghosts, f"ok={r3.ok} ghosts={r3.ghosts}")

    # [중요] **부분열 완화가 유령을 통과시키지 않는다** — 주석의 `EOld` 는 어떤 live 의
    #    부분열도 아니므로 그대로 잡힌다(위 r3). 완화가 먹는 것은 *live 의 부분열*뿐이다.
    check("[중요] 완화 뒤에도 주석 유령이 잡힌다 (게이트가 죽지 않았다)",
          not r3.ok and "EOld" in r3.ghosts, f"ok={r3.ok} ghosts={r3.ghosts}")
    # live 의 부분열은 통과 — 그것이 이번 완화의 전부다
    r5 = V.verify(_doc("UThing 은 Mode 상태를 관리한다.", related="UThing: T.h"),
                  sources={"T.h": SRC}, declared=["UThing"])
    check("live(EMode) 의 부분열 Mode 는 통과", r5.ok, str(r5.ghosts))


def test_mention_uses_unfiltered_set() -> None:
    """[중요] **언급 판정은 `#270` 필터 전 집합으로 한다** (`#286`, 실측 2026-08-23).

    `#270` 이 유령 판정을 위해 「live 의 부분열」을 뺐는데, 같은 집합을 언급 판정이 쓰면서
    **정반대로 작동했다**: UE 접두를 뗀 `PlatformingGameMode` 가 `APlatformingGameMode` 의
    부분열이라 빠지고, 그래서 *"하나도 언급하지 않았다"* 로 거부됐다.
    NS 라이브에서 3그룹이 이것 때문에 5분마다 무한 재시도했다.
    """
    print("\n[언급] 접두를 떼도 언급으로 센다 (#286)")
    SRC = ("class APlatformingGameMode : public AGameModeBase {\n"
           "  void BeginPlay();\n};\n")
    srcs = {"PlatformingGameMode.h": SRC}
    decl = ["APlatformingGameMode"]

    r_pre = V.verify(_doc("APlatformingGameMode 는 AGameModeBase 를 상속한다."),
                     sources=srcs, declared=decl)
    check("접두를 붙여 쓰면 통과 (종전에도 통과)", r_pre.ok, r_pre.reason)

    r_bare = V.verify(_doc("PlatformingGameMode 는 GameModeBase 를 상속한다."),
                      sources=srcs, declared=decl)
    check("[중요] 접두를 떼도 통과한다 (UE 규약 — #270 이 자연스럽다고 적어 둔 표기)",
          r_bare.ok and r_bare.mentioned_declared, r_bare.reason)

    # [중요] **게이트를 무디게 만들지 않았다** — 아래 둘은 여전히 막힌다
    r_other = V.verify(_doc("ACombatEnemy 는 적 AI 를 담당한다."),
                       sources=srcs, declared=decl)
    check("[중요] 다른 파일을 서술하면 여전히 막는다",
          not r_other.ok and not r_other.mentioned_declared, r_other.reason)

    r_made = V.verify(_doc("APlatformingHoverBoard 가 부양을 처리한다."),
                      sources=srcs, declared=decl)
    check("[중요] 지어낸 이름도 여전히 막는다 (부분열이 아니다)",
          not r_made.ok, r_made.reason)

    # [주의] 역방향은 언급이 **아니다** — 선언이 문서 낱말의 부분열인 경우
    #    (`Mode` 만 쓰고 `APlatformingGameMode` 를 가리킨다고 볼 수 없다)
    r_rev = V.verify(_doc("APlatformingGameModeExtendedHelper 를 쓴다."),
                     sources=srcs, declared=decl)
    check("선언이 문서 낱말의 부분열인 것은 언급으로 세지 않는다",
          not r_rev.mentioned_declared, r_rev.reason)


def test_korean_particles_do_not_hide_identifiers() -> None:
    """[중요] **`\\b` 는 한글 앞에서 경계가 아니다** (`#287`, 실측 2026-08-23).

    파이썬 `re` 의 `\\b` 는 `\\w`↔non-`\\w` 경계인데 한글이 `\\w` 에 포함된다. 그래서
    `ANSCharacter는` 이 한 낱말이 되어 식별자가 **통째로 안 잡혔다.** 이 프로젝트의 컨텍스트
    문서는 한국어이므로, 게이트가 반쯤 눈을 감고 있었던 것이다 — NS 3그룹이 그 때문에
    5분마다 무한 재시도했다.
    """
    print("\n[한글] 조사가 붙어도 식별자를 본다 (#287)")
    check("조사 `는` 이 붙어도 잡는다",
          V.identifiers("ANSCharacter는 상속한다") == {"ANSCharacter"},
          str(V.identifiers("ANSCharacter는 상속한다")))
    check("조사 `를` 도, 두 개가 한 줄에 있어도",
          V.identifiers("ANSCharacter는 ACharacter를 상속") == {"ANSCharacter", "ACharacter"},
          str(V.identifiers("ANSCharacter는 ACharacter를 상속")))
    check("백틱·괄호도 경계다",
          "ACharacter" in V.identifiers("`ACharacter`를 (UObject)와"),
          str(V.identifiers("`ACharacter`를 (UObject)와")))
    # [중요] **경계 판정을 무디게 만들지 않았다** — 부분 매치는 여전히 안 된다
    check("[중요] 식별자 안쪽의 부분열은 잡지 않는다",
          V.identifiers("FooBarBaz") == {"FooBarBaz"}, str(V.identifiers("FooBarBaz")))
    check("소문자 낱말은 여전히 제외 (모양 규칙)",
          V.identifiers("abc는 소문자") == set(), str(V.identifiers("abc는 소문자")))

    # 실전 형태 — 조사 붙은 선언 클래스가 언급으로 세어진다
    SRC = "class APlatformingGameMode : public AGameModeBase {\n  void BeginPlay();\n};\n"
    r = V.verify(_doc("APlatformingGameMode는 AGameModeBase를 상속한다."),
                 sources={"G.h": SRC}, declared=["APlatformingGameMode"])
    check("[중요] 조사 붙은 선언 클래스를 언급으로 센다 (NS 3그룹이 여기서 막혔다)",
          r.ok and r.mentioned_declared, r.reason)


def test_project_symbols_are_not_ghosts() -> None:
    """🔴 **파일 경계를 넘는 정상 참조를 유령으로 잡지 않는다** (`#367`, 2026-09-06).

    실측: `NSPropsBase` 주석의 *"서브클래스(예: ANSLootableChest)"* 가 거부됐는데 그 클래스는
    `NSLootableChest.h:27` 에 **실재**한다. 색인기는 **변경된 파일만** 합성에 넘기므로 그룹이
    반쪽인 경우도 있고(그건 `synth.complete_group` 이 채운다), 다른 파일의 선언은 그래도 남는다.

    [중요] **게이트를 무디게 하는 것이 아니다** — 판정 근거를 프로젝트 범위로 넓히는 것이다.
    아래 세 번째 검사가 그 계약이다: **주석에만 있고 프로젝트에도 없으면 그대로 잡힌다.**
    """
    src = {"A.h": "// UNSGhostOnly 는 주석에만 있다\n// ANSLootableChest 는 다른 파일에 있다\n"
                  "class ANSPropsBase { void Run(); };\n"}
    doc = "## 요약\n\nANSPropsBase 는 ANSLootableChest 를 서브클래스로 갖는다\n\n## 끝\n"
    before = V.verify(doc, sources=src, declared=["ANSPropsBase"])
    check("[주의] 종전에는 다른 파일의 실재 클래스가 유령이었다",
          not before.ok and "ANSLootableChest" in before.ghosts, str(before.ghosts))
    after = V.verify(doc, sources=src, declared=["ANSPropsBase"],
                     known={"ANSLootableChest", "ANSPropsBase"})
    check("🔴 프로젝트에 실재하면 유령이 아니다", after.ok, str(after.ghosts))

    ghost_doc = "## 요약\n\nANSPropsBase 는 UNSGhostOnly 를 쓴다\n\n## 끝\n"
    still = V.verify(ghost_doc, sources=src, declared=["ANSPropsBase"],
                     known={"ANSLootableChest", "ANSPropsBase"})
    check("[중요] **주석에만 있고 프로젝트에도 없으면 그대로 잡는다** (무뎌지지 않았다)",
          not still.ok and "UNSGhostOnly" in still.ghosts, str(still.ghosts))
    check("  근거가 없으면(known 없음) 종전 판정 그대로 — 조용히 통과시키지 않는다",
          not V.verify(doc, sources=src, declared=["ANSPropsBase"], known=set()).ok)


if __name__ == "__main__":
    for fn in (test_license_header_not_identifier, test_cross_file_live_wins,
               test_ue_prefix_substring, test_real_violation_still_caught,
               test_mention_uses_unfiltered_set,
               test_korean_particles_do_not_hide_identifiers,
               test_project_symbols_are_not_ghosts):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_verify_gate: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
