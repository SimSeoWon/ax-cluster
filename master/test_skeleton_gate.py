"""골조 빌드 게이트 (소 1.1.5).

[중요] 지키는 계약은 **fail-closed** 다 — *"확인하지 못했다"* 를 *"괜찮다"* 로 바꾸면 이 게이트는
없는 것과 같다. 원전은 빌드를 등재 *뒤*에 두었다가 깨진 골조가 `origin` 에 박혔다.

`.venv/bin/python master/test_skeleton_gate.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.layer3_verify import BuildResult      # noqa: E402
from master.work import skeleton as S             # noqa: E402
from master.work import skeleton_gate as G        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


@dataclass
class Facts:
    host: str = "192.168.0.2"
    user: str = "janus"
    windows: bool = True
    path: str = r"E:\trunk\ModularStage"
    home: str = r"C:\Users\janus"
    ue5: str = r"C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"


def good_skeleton() -> S.Skeleton:
    head = ("#pragma once\nUCLASS()\nclass FOO_API UFoo : public UObject\n{\n"
            "    GENERATED_BODY()\npublic:\n    void Go();\n};\n")
    return S.Skeleton(stem="Foo",
                      files={"Source/A/Foo.h": "// [DOC] 왜 이렇게 생겼나\n" + head,
                             "Source/A/Foo.cpp": "// [DOC] 무엇을 왜\n// [PSEUDO] 구현한다"},
                      frozen=S.frozen_decls(head), pseudo=1)


def test_build_bat_is_derived_not_guessed() -> None:
    """[중요] 실측: 이 기계의 엔진은 `C:\\Program Files\\UE_5.8` — `Epic Games` 하위가 아니다.

    경로를 짐작했다가 실제로 틀렸다(1차 측정이 `NO_BUILD_BAT` 으로 끝났다). `probe` 가
    찾아 둔 값에서 되짚는다.
    """
    bb = G._build_bat_from(Facts())
    check("Build.bat 을 유도한다",
          bb == r"C:\Program Files\UE_5.8\Engine\Build\BatchFiles\Build.bat", bb)
    check("엔진을 모르면 빈 문자열", G._build_bat_from(Facts(ue5="")) == "")
    check("모양이 다르면 빈 문자열", G._build_bat_from(Facts(ue5=r"C:\weird\thing.exe")) == "")


def test_target_name() -> None:
    check("에디터 타깃을 만든다", G.target_name("ModularStage") == "ModularStageEditor")
    check("이미 붙어 있으면 그대로", G.target_name("ModularStageEditor") == "ModularStageEditor")
    try:
        G.target_name("")
        check("[중요] 빈 프로젝트는 거부", False)
    except ValueError:
        check("[중요] 빈 프로젝트는 거부", True)


def test_place_writes_into_the_isolated_tree() -> None:
    """[중요] 사람·워커의 트리가 아니라 **격리 트리**에 쓴다."""
    wrote: list = []
    got = G.place(Facts(), r"E:\trunk\ms-wt-1",
                  {"Source/A/Foo.h": "h", "Source/A/Foo.cpp": "c"},
                  writer=lambda f, p, t: wrote.append((p, t)))
    check("경로를 윈도우로 잇는다",
          got == [r"E:\trunk\ms-wt-1\Source\A\Foo.cpp", r"E:\trunk\ms-wt-1\Source\A\Foo.h"],
          str(got))
    check("체크아웃 경로를 안 쓴다", all("ModularStage\\Source" not in p for p, _ in wrote))
    check("내용을 그대로 넘긴다", sorted(t for _, t in wrote) == ["c", "h"])
    try:
        G.place(Facts(), "", {"a.h": "x"}, writer=lambda *a: None)
        check("[중요] 트리 경로가 비면 거부", False)
    except ValueError:
        check("[중요] 트리 경로가 비면 거부", True)


def test_gate_blocks_before_building_when_not_a_skeleton() -> None:
    """[중요] 골조가 아니면 빌드할 이유도 없다 — 싼 검사를 먼저."""
    built: list = []
    bad = S.Skeleton(stem="Bad", files={"a.h": "완성된 파일"}, frozen=set(), pseudo=0)
    g = G.run(Facts(), bad, tree=r"E:\wt", project="ModularStage",
              writer=lambda *a: None, builder=lambda *a, **k: built.append(1))
    check("[중요] 통과가 아니다", not g.ok, g.summary)
    check("빌드를 부르지 않았다", built == [], str(built))
    check("사유를 말한다", "골조가 아니다" in g.error, g.error)

    empty = S.Skeleton(stem="Empty")
    g2 = G.run(Facts(), empty, tree=r"E:\wt", project="ModularStage",
               writer=lambda *a: None, builder=lambda *a, **k: built.append(1))
    check("[중요] 파일이 없으면 막는다", not g2.ok and "세울 것이 없다" in g2.error, g2.error)


def test_gate_is_fail_closed_on_every_uncertainty() -> None:
    """[중요] *"확인하지 못했다"* 는 통과가 아니다."""
    sk = good_skeleton()

    # ① 배치 실패
    def boom(*a):
        raise RuntimeError("scp 해시 불일치")
    g = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage", writer=boom,
              builder=lambda *a, **k: BuildResult(passed=True, failure=None, result="Succeeded"))
    check("[중요] 배치 실패는 막는다", not g.ok and "배치 실패" in g.error, g.error)
    check("배치 실패면 빌드 안 함", not g.checked)

    # ② 엔진을 못 찾음
    g2 = G.run(Facts(ue5=""), sk, tree=r"E:\wt", project="ModularStage",
               writer=lambda *a: None,
               builder=lambda *a, **k: BuildResult(passed=True, failure=None))
    check("[중요] 엔진 미발견은 막는다", not g2.ok and "Build.bat" in g2.error, g2.error)

    # ③ UBT 가 판정을 못 냈다 (SSH 실패·타임아웃) — layer3 계약이 failure 로 준다
    g3 = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage", writer=lambda *a: None,
               builder=lambda *a, **k: BuildResult(passed=False, failure="3600초 안에 안 끝났다"))
    check("[중요] 판정 없음은 막는다", not g3.ok, g3.summary)
    check("돌리긴 했다고 기록", g3.checked)

    # ④ 빌드 실패
    g4 = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage", writer=lambda *a: None,
               builder=lambda *a, **k: BuildResult(passed=False, failure=None,
                                                   result="Failed", detail="CompileError"))
    check("[중요] 빌드 실패는 막는다", not g4.ok, g4.summary)
    check("요약이 사유를 보인다", "FAILED" in g4.summary or "CompileError" in g4.summary,
          g4.summary)


def test_gate_passes_only_on_a_real_verdict() -> None:
    seen: dict = {}

    def builder(host, user, bb, target, up, **kw):
        seen.update(host=host, target=target, uproject=up, build_bat=bb)
        return BuildResult(passed=True, failure=None, result="Succeeded", seconds=812.4)

    g = G.run(Facts(), good_skeleton(), tree=r"E:\trunk\ms-wt-7", project="ModularStage",
              writer=lambda *a: None, builder=builder)
    check("[완료] 통과", g.ok, g.summary)
    check("에디터 타깃을 짓는다", seen["target"] == "ModularStageEditor", str(seen))
    check("[중요] uproject 도 격리 트리 것", seen["uproject"] == r"E:\trunk\ms-wt-7\ModularStage.uproject",
          seen["uproject"])
    check("유도한 Build.bat 을 쓴다", seen["build_bat"].endswith(r"\Build.bat"), seen["build_bat"])
    check("소요를 기록한다", g.seconds == 812.4, str(g.seconds))
    check("파일 수를 요약에", "파일 2" in g.summary, g.summary)


def test_not_run_is_not_a_pass() -> None:
    """[주의] **게이트를 안 붙인 것**과 **게이트가 통과한 것**은 다르다."""
    g = G.GateResult(stem="Foo")
    check("[중요] 안 돌렸으면 통과 아님", not g.ok)
    check("요약이 '미확인' 이라고 말한다", "미확인" in g.summary, g.summary)


def main() -> int:
    for fn in (test_build_bat_is_derived_not_guessed, test_target_name,
               test_place_writes_into_the_isolated_tree,
               test_gate_blocks_before_building_when_not_a_skeleton,
               test_gate_is_fail_closed_on_every_uncertainty,
               test_gate_passes_only_on_a_real_verdict, test_not_run_is_not_a_pass):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_skeleton_gate: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
