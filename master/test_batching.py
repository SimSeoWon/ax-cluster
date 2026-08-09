"""태스크 묶기 (레드마인 #65).

🔴 지키는 계약은 **비용**이 아니라 **충돌 방지**다 — 사용자: *"클래스 별로 분리하는건
분산 작업시 충돌을 방지하기 위해서인데"*. 묶어서 싸지는 것은 그 계약을 깨지 않는 선에서만
가치가 있다.

`.venv/bin/python master/test_batching.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import batching as B      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def test_header_and_impl_stay_together() -> None:
    """🔴 선언과 정의가 다른 워커로 가면 어긋난 채 각자 push 된다."""
    us = B.units([("UFoo", "Source/A/Foo.h"), ("UFoo", "Source/A/Foo.cpp"),
                  ("UBar", "Source/B/Bar.h")])
    check("stem 으로 한 몸이 된다", len(us) == 2, [u.key for u in us])
    foo = next(u for u in us if u.key.endswith("Foo"))
    check("헤더와 구현이 같은 단위", sorted(foo.files) == ["Source/A/Foo.cpp", "Source/A/Foo.h"],
          str(foo.files))


def test_ue_public_private_pair() -> None:
    """🔴 UE 모듈은 선언·구현을 `Public/`↔`Private/` 로 가른다 — 그래도 한 몸이다.

    실측 2026-08-10: 이 프로젝트에 50건. 원전(AgentTest)은 같은 폴더만 봐서 *"헤더 전용"*
    으로 오판하고 **워커 태스크를 통째로 누락**했다(2026-06-07 prod 발견).
    """
    us = B.units([("UBeacon", "ModularStageEditor/Public/BeaconDetails.h"),
                  ("UBeacon", "ModularStageEditor/Private/BeaconDetails.cpp")])
    check("Public/Private 짝은 한 단위", len(us) == 1, [u.key for u in us])
    check("열쇠에서 Public/Private 가 빠진다", us[0].key == "ModularStageEditor/BeaconDetails",
          us[0].key)


def test_same_name_in_other_module_splits() -> None:
    """🔴 다른 모듈의 동명 파일은 **갈라야 한다** — 실측 9건이 포팅 원본↔대상이다.

    묶으면 워커에게 *"이 둘은 한 몸이니 같이 고쳐라"* 가 되는데, 포팅 원본은 읽기 전용이다.
    """
    us = B.units([("UHex", "ModularStage/UI/HexGrid/Alpha_HexagonTileItem.h"),
                  ("UHex", "ModularStage/UI/HexGrid/Alpha_HexagonTileItem.cpp"),
                  ("UHex", "Project_Alpha/UI/Components/Hexagon/Alpha_HexagonTileItem.h"),
                  ("UHex", "Project_Alpha/UI/Components/Hexagon/Alpha_HexagonTileItem.cpp")])
    check("모듈이 다르면 갈라진다", len(us) == 2, [u.key for u in us])
    check("각 단위는 자기 모듈의 짝만 갖는다",
          all(len(u.files) == 2 and len({f.split("/")[0] for f in u.files}) == 1 for u in us),
          str([u.files for u in us]))
    check("두 단위가 파일을 공유하지 않는다",
          not (set(us[0].files) & set(us[1].files)))


def test_same_file_classes_never_split() -> None:
    """🔴 한 파일의 클래스들이 갈라지면 두 워커가 같은 파일을 고친다."""
    items = [("UA", "Source/X.h"), ("UB", "Source/X.h"), ("UC", "Source/Y.h")]
    groups = B.plan(items, size=1)          # 가장 잘게 쪼개도
    check("같은 파일은 한 묶음", B.check_disjoint(groups) == [], str(B.check_disjoint(groups)))
    x = [g for g in groups if any("Source/X.h" in u.files for u in g)]
    check("X.h 묶음은 하나뿐", len(x) == 1, str(len(x)))
    check("그 안에 두 클래스가 다 있다",
          sorted(x[0][0].classes) == ["UA", "UB"], str(x[0][0].classes))


def test_disjoint_is_the_invariant() -> None:
    """🔴 불변식이 깨지면 호출자가 파견하지 않아야 한다 — 그래서 검사가 따로 있다."""
    ok = B.plan([("UA", "Source/A.h"), ("UB", "Source/B.h"), ("UC", "Source/C.h")], size=2)
    check("정상이면 위반 0", B.check_disjoint(ok) == [])
    check("요약이 안전하다고 말한다", "겹침 없음" in B.summary(ok), B.summary(ok))

    # 손으로 잘못 만든 묶음 — 검사가 잡아야 한다
    bad = [[B.Unit(key="a", files=["Source/Same.h"])],
           [B.Unit(key="b", files=["Source/Same.h"])]]
    v = B.check_disjoint(bad)
    check("🔴 파일 중복을 잡는다", len(v) == 1 and "Same.h" in v[0], str(v))
    check("요약이 위험을 드러낸다", "🔴" in B.summary(bad), B.summary(bad))


def test_pack_size() -> None:
    us = B.units([(f"U{i}", f"Source/F{i}.h") for i in range(9)])
    g = B.pack(us, size=4)
    check("4개씩 묶는다", [len(x) for x in g] == [4, 4, 1], str([len(x) for x in g]))
    # 🔴 실측된 점은 4 하나뿐이다 — 기본값이 그것이어야 한다
    check("🔴 기본 크기는 실측값 4", B.DEFAULT_SIZE == 4, str(B.DEFAULT_SIZE))
    check("단위를 쪼개지 않는다", all(isinstance(u, B.Unit) for x in g for u in x))
    try:
        B.pack(us, size=0)
        check("size 0 은 거부", False)
    except ValueError:
        check("size 0 은 거부", True)


def test_no_file_no_problem() -> None:
    """파일을 모르는 클래스도 버리지 않는다 — 클래스명을 열쇠로 쓴다."""
    us = B.units([("UOrphan", ""), ("UFoo", "Source/Foo.h")])
    check("파일 없는 것도 단위가 된다", len(us) == 2, [u.key for u in us])
    check("빈 항목은 버린다", len(B.units([("", ""), ("UA", "Source/A.h")])) == 1)


def main() -> int:
    for fn in (test_header_and_impl_stay_together, test_ue_public_private_pair,
               test_same_name_in_other_module_splits, test_same_file_classes_never_split,
               test_disjoint_is_the_invariant, test_pack_size, test_no_file_no_problem):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_batching: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
