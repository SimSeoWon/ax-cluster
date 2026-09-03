"""분해 (중 1.2).

[중요] 지키는 계약은 둘이다 — **동시에 돌 것들은 파일이 겹치지 않는다**(그렇지 않으면 두 워커가
같은 파일을 고친다), 그리고 **의존이 먼저 적용된다**(아니면 선언이 없어 컴파일이 깨진다).

`.venv/bin/python master/test_decompose.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import decompose as D      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class FakeDeps:
    """`#include` 그래프 대역. `{파일: [그 파일이 무는 것]}`.

    [중요] `exists` 도 흉내낸다 — 실제 코드가 *"그래프가 아예 없다"* 와 *"조회가 실패했다"* 를
    구분하기 때문이다. 대역이 그 구분을 안 가지면 테스트가 실제를 안 재는 셈이다.
    """

    def __init__(self, edges: dict, boom: bool = False, built: bool = True):
        self.edges, self.boom, self.built = edges, boom, built

    def exists(self, paths):
        return self.built

    def dependencies(self, paths, f, depth=1):
        if self.boom:
            raise RuntimeError("그래프 없음")
        return list(self.edges.get(f, []))


def with_deps(monkey: FakeDeps):
    """`_order_by_includes` 가 쓰는 모듈을 갈아 끼운다."""
    import master.graph.dependency as real
    saved = (real.dependencies, real.exists)
    real.dependencies, real.exists = monkey.dependencies, monkey.exists
    return real, saved


def test_pieces_inherit_file_indivisibility() -> None:
    """[중요] 파일 불가분은 `batching` 이 이미 보장한다 — 여기서 다시 깨면 안 된다."""
    ps = D.pieces_from([("UFoo", "M/A/Foo.h"), ("UFoo", "M/A/Foo.cpp"),
                        ("UBar", "M/B/Bar.h")])
    check("조각 2개", len(ps) == 2, str([p.stem for p in ps]))
    foo = next(p for p in ps if p.stem.endswith("Foo"))
    check("`.h`/`.cpp` 가 한 조각", sorted(foo.files) == ["M/A/Foo.cpp", "M/A/Foo.h"],
          str(foo.files))


def test_dependency_comes_first() -> None:
    """[중요] A 가 B 를 include 하면 **B 가 먼저** — 아니면 선언이 없어 깨진다."""
    real, saved = with_deps(FakeDeps({"M/A/A.h": ["M/B/B.h"]}))
    try:
        p = D.plan(None, [("UA", "M/A/A.h"), ("UB", "M/B/B.h")])
    finally:
        real.dependencies, real.exists = saved
    names = [x.stem for x in p.ordered()]
    check("의존 대상이 앞", names.index("M/B/B") < names.index("M/A/A"), str(names))
    check("순환 없음", not p.cycles, str(p.cycles))
    check("계획이 안전", p.ok, p.preview())


def test_chain_of_three() -> None:
    real, saved = with_deps(FakeDeps({"M/A.h": ["M/B.h"], "M/B.h": ["M/C.h"]}))
    try:
        p = D.plan(None, [("UA", "M/A.h"), ("UB", "M/B.h"), ("UC", "M/C.h")])
    finally:
        real.dependencies, real.exists = saved
    names = [x.stem for x in p.ordered()]
    check("C → B → A 순", names == ["M/C", "M/B", "M/A"], str(names))


def test_cycle_is_reported_not_blocked() -> None:
    """[주의] 순환은 **막지 않는다** — include 역추적이 basename 근사라 가짜일 수 있다.

    *정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다* (사실 게이트에서 내린 판단).
    """
    real, saved = with_deps(FakeDeps({"M/A.h": ["M/B.h"], "M/B.h": ["M/A.h"]}))
    try:
        p = D.plan(None, [("UA", "M/A.h"), ("UB", "M/B.h")])
    finally:
        real.dependencies, real.exists = saved
    check("순환을 보고한다", len(p.cycles) == 1, str(p.cycles))
    check("[중요] 그래도 막지 않는다", p.ok, p.preview())
    check("미리보기가 순환을 드러낸다", "순환 의존" in p.preview(), p.preview())
    check("가짜일 수 있다고 말한다", "근사" in p.preview())


def test_graph_failure_is_stated_not_swallowed() -> None:
    """[주의] *순서를 못 정한 것*과 *순서가 없는 것*은 다르다."""
    real, saved = with_deps(FakeDeps({}, boom=True))
    try:
        p = D.plan(None, [("UA", "M/A.h"), ("UB", "M/B.h")])
    finally:
        real.dependencies, real.exists = saved
    check("[중요] 사유를 남긴다 (조회 실패를 '의존 없음' 으로 뭉개지 않는다)",
          any("조회 실패" in n or "순서를 못 정했다" in n for n in p.notes), str(p.notes))
    check("그래도 조각은 나온다", len(p.pieces) == 2)


def test_no_graph_at_all_is_a_different_message() -> None:
    """[중요] *그래프가 없다* 와 *조회가 실패했다* 는 다른 사실이다 — 조치도 다르다."""
    real, saved = with_deps(FakeDeps({}, built=False))
    try:
        p = D.plan(None, [("UA", "M/A.h")])
    finally:
        real.dependencies, real.exists = saved
    check("[중요] 그래프 미구축을 말한다", any("그래프가 없다" in n for n in p.notes), str(p.notes))
    check("조치를 알려준다", any("master.graph build" in n for n in p.notes), str(p.notes))


def test_ungraphed_files_are_flagged_not_dropped() -> None:
    """신규 파일은 그래프에 없다 — 정상이지만 **말은 한다.**"""
    real, saved = with_deps(FakeDeps({"M/A.h": ["M/B.h"]}))
    try:
        p = D.plan(None, [("UA", "M/A.h"), ("UB", "M/B.h"), ("UNew", "M/New.h")])
    finally:
        real.dependencies, real.exists = saved
    check("그래프에 없는 것을 센다", "M/New.h" in p.ungraphed, str(p.ungraphed))
    check("버리지는 않는다", len(p.pieces) == 3, str([x.stem for x in p.pieces]))
    check("미리보기가 말한다", "그래프에 없는 파일" in p.preview())


def test_depth_split_is_sequential_not_concurrent() -> None:
    """[중요] **뎁스는 같은 파일이라도 충돌이 아니다** — `depends_on` 으로 줄을 서기 때문이다."""
    skel = ("// [PSEUDO:1] 기반\n// [PSEUDO:2] 중간\n// [PSEUDO:3] 통합")
    real, saved = with_deps(FakeDeps({}))
    try:
        p = D.plan(None, [("UA", "M/A.h"), ("UA", "M/A.cpp")], skeletons={"M/A": skel})
    finally:
        real.dependencies, real.exists = saved
    check("뎁스만큼 조각", len(p.pieces) == 3, str([x.stem for x in p.pieces]))
    check("뎁스가 1,2,3", [x.depth for x in p.ordered()] == [1, 2, 3],
          str([x.depth for x in p.ordered()]))
    check("앞 뎁스에 의존", p.ordered()[1].depends_on == ["M/A.d1"],
          str(p.ordered()[1].depends_on))
    check("첫 뎁스는 의존 없음", p.ordered()[0].depends_on == [])
    # [중요] 핵심 — 같은 파일을 셋이 나눠 갖지만 **위반이 아니다**
    check("[중요] 같은 파일이어도 위반 아님", p.ok, str(p.violations()))
    check("물결이 셋으로 갈린다", len(p.waves()) == 3, str([len(w) for w in p.waves()]))
    check("메모에 뎁스 분할", any("뎁스 분할" in n for n in p.notes), str(p.notes))


def test_plain_pseudo_is_one_task() -> None:
    """번호 없는 `[PSEUDO]` 는 나누지 않는다 (하위 호환)."""
    real, saved = with_deps(FakeDeps({}))
    try:
        p = D.plan(None, [("UA", "M/A.h")], skeletons={"M/A": "// [PSEUDO] 한 번에"})
    finally:
        real.dependencies, real.exists = saved
    check("한 조각 그대로", len(p.pieces) == 1 and p.pieces[0].depth == 0)


def test_concurrent_overlap_is_caught() -> None:
    """[중요] 같은 물결에서 파일이 겹치면 **파견하면 안 된다.**"""
    p = D.Plan(pieces=[D.Piece(stem="X", files=["M/Same.h"], order=0),
                       D.Piece(stem="Y", files=["M/Same.h"], order=0)])
    v = p.violations()
    check("겹침을 잡는다", len(v) == 1 and "Same.h" in v[0], str(v))
    check("[중요] 안전하지 않다", not p.ok)
    check("미리보기가 경고한다", "파견하면 안 된다" in p.preview(), p.preview())


def test_to_specs_refuses_broken_plans() -> None:
    """[중요] 불변식이 깨진 계획으로 태스크를 만들지 않는다."""
    from master.work.register import RegisterError
    bad = D.Plan(pieces=[D.Piece(stem="X", files=["M/S.h"], order=0),
                         D.Piece(stem="Y", files=["M/S.h"], order=0)])
    try:
        D.to_specs(bad)
        check("[중요] 깨진 계획은 거부", False)
    except RegisterError as e:
        check("[중요] 깨진 계획은 거부", "파견하지 않는다" in str(e), str(e))

    good = D.Plan(pieces=[D.Piece(stem="M/C", files=["M/C.h"], order=0),
                          D.Piece(stem="M/A", files=["M/A.h"], order=1)])
    specs = D.to_specs(good, instruction="만든다", requires=["ue5"])
    check("순서대로 만든다", [s.stem for s in specs] == ["M/C", "M/A"],
          str([s.stem for s in specs]))
    # [중요] 먼저 적용될 것이 먼저 나가야 한다
    check("우선순위가 순서를 따른다", specs[0].priority > specs[1].priority,
          f"{specs[0].priority} vs {specs[1].priority}")
    check("지시·능력을 넘긴다", specs[0].instruction == "만든다" and specs[0].requires == ["ue5"])
    check("파일을 넘긴다", specs[0].target_files == ["M/C.h"], str(specs[0].target_files))


def test_empty_is_stated() -> None:
    p = D.plan(None, [])
    check("빈 것을 말한다", any("조각이 없다" in n for n in p.notes), str(p.notes))


# ── 🔴 정본 ⑷ — 조각의 짝 채우기 (사용자 결정 ⓐ 2026-09-03) ────────────────────────

class _FakeMirror:
    """골조 커밋의 `main...<base>` diff 대역. **실 git 을 두드리지 않는다.**"""

    def __init__(self, changed: list):
        self.changed = list(changed)
        self.calls: list = []

    def ensure_commit(self, paths, commit, **kw):
        self.calls.append(("ensure", commit))

    def mirror_git(self, paths, *args, **kw):
        self.calls.append(("git",) + args)
        return "\n".join(self.changed) + "\n"


def _with_mirror(changed):
    """`decompose.complete_pairs` 가 쓰는 두 함수를 갈아 끼운다."""
    from master.work import declarations as DE
    fake = _FakeMirror(changed)
    saved = (DE.ensure_commit, DE._mirror_git)
    DE.ensure_commit, DE._mirror_git = fake.ensure_commit, fake.mirror_git
    return fake, saved


def _restore(saved):
    from master.work import declarations as DE
    DE.ensure_commit, DE._mirror_git = saved


SKEL = ["Source/NS/Interaction/NSInteractable.h",
        "Source/NS/Interaction/NSInteractable.cpp",
        "Source/NS/Interaction/NSInteractableComponent.h",
        "Source/NS/Interaction/NSInteractableComponent.cpp"]


def test_header_only_piece_gets_its_cpp() -> None:
    """🔴 **이것이 없어서 라운드 하나가 4/4 죽었다** (실측 2026-09-03 23:12~23:16).

    등재가 `.h` 만 실어 보냈고, 워커는 골조의 `[PSEUDO]` 가 있는 `.cpp` 를 고쳤다. 커밋은
    `want` 만 스테이징하므로 `.h` 는 무변경 → `"no changes added to commit"` → rc=1 →
    BLOCKED. **실제 산출물이 통째로 버려졌다.**
    """
    fake, saved = _with_mirror(SKEL)
    try:
        want, added, why = D.complete_pairs(None, "deadbee",
                                            ["Source/NS/Interaction/NSInteractable.h"])
        check("[중요] `.cpp` 를 채운다",
              "Source/NS/Interaction/NSInteractable.cpp" in want, str(want))
        check("무엇을 붙였는지 돌려준다",
              added == ["Source/NS/Interaction/NSInteractable.cpp"], str(added))
        check("원래 것을 잃지 않는다",
              "Source/NS/Interaction/NSInteractable.h" in want, str(want))
        check("사유 없음(성공)", not why, why)
    finally:
        _restore(saved)


def test_cpp_only_piece_gets_its_header() -> None:
    """반대 방향도 같다 — 선언만 고치는 조각이면 헤더가 없으면 커밋이 빈다."""
    fake, saved = _with_mirror(SKEL)
    try:
        want, added, _ = D.complete_pairs(None, "deadbee",
                                          ["Source/NS/Interaction/NSInteractable.cpp"])
        check("`.h` 를 채운다", "Source/NS/Interaction/NSInteractable.h" in want, str(want))
        check("한 짝만 붙인다", len(added) == 1, str(added))
    finally:
        _restore(saved)


def test_only_files_the_skeleton_touched_are_paired() -> None:
    """[주의] **아무 짝이나 끌어오지 않는다.** 실측 2026-08-10: 다른 모듈·같은 이름 9건은
    **갈라야** 한다 — 골조 diff 안으로 한정하면 그 위험이 사라진다."""
    fake, saved = _with_mirror(["Source/NS/Interaction/NSInteractable.h"])   # `.cpp` 없음
    try:
        want, added, why = D.complete_pairs(None, "deadbee",
                                            ["Source/NS/Interaction/NSInteractable.h"])
        check("[중요] 골조에 없는 짝은 안 붙인다", not added, str(added))
        check("want 를 망가뜨리지 않는다", want == ["Source/NS/Interaction/NSInteractable.h"],
              str(want))
        check("조용히 넘기지 않는다 (사유 없음이 정상)", why == "", why)
    finally:
        _restore(saved)


def test_public_private_split_is_paired() -> None:
    """UE 는 선언을 `Public/`, 정의를 `Private/` 에 두는 배치가 흔하다 (실측 50쌍)."""
    fake, saved = _with_mirror(["Source/M/Public/Foo.h", "Source/M/Private/Foo.cpp"])
    try:
        want, added, _ = D.complete_pairs(None, "deadbee", ["Source/M/Public/Foo.h"])
        check("[중요] Public↔Private 을 넘어 짝을 찾는다",
              "Source/M/Private/Foo.cpp" in want, str(want))
    finally:
        _restore(saved)


def test_missing_commit_says_why_and_does_not_break_dispatch() -> None:
    """[주의] 짝을 못 채운 것과 조각이 틀린 것은 다르다 — 사유를 돌려주고 파견은 막지 않는다."""
    want, added, why = D.complete_pairs(None, "", ["Source/A/B.h"])
    check("want 를 그대로 돌려준다", want == ["Source/A/B.h"], str(want))
    check("사유를 말한다", "기준 커밋" in why, why)


def main() -> int:
    for fn in (test_pieces_inherit_file_indivisibility, test_dependency_comes_first,
               test_chain_of_three, test_cycle_is_reported_not_blocked,
               test_graph_failure_is_stated_not_swallowed,
               test_no_graph_at_all_is_a_different_message,
               test_ungraphed_files_are_flagged_not_dropped,
               test_depth_split_is_sequential_not_concurrent,
               test_plain_pseudo_is_one_task, test_concurrent_overlap_is_caught,
               test_to_specs_refuses_broken_plans, test_empty_is_stated,
               test_header_only_piece_gets_its_cpp,
               test_cpp_only_piece_gets_its_header,
               test_only_files_the_skeleton_touched_are_paired,
               test_public_private_split_is_paired,
               test_missing_commit_says_why_and_does_not_break_dispatch):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_decompose: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
