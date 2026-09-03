"""본문 작성 레인 (`#346`).

[중요] 지키는 계약은 넷이다:

    ① **순서** — `agy` → 로컬. `claude` 는 기본 체인에 **없다** (사용자 지시 2026-09-04)
    ② **fail-forward** — 한 레인이 죽으면 다음으로 넘어간다 (429 하나로 라운드가 죽던 것)
    ③ **써 넣기 실패는 성공이 아니다** — 텍스트를 받은 것과 워커 디스크에 올라간 것은 다르다
    ④ **레인 규약을 두 벌 두지 않는다** — `ontology/synth.generate` 를 그대로 쓴다

`.venv/bin/python master/test_lanes.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import lanes as LN      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


H = "Source/NS/Interaction/NSInteractorComponent.h"
C = "Source/NS/Interaction/NSInteractorComponent.cpp"
SKEL = {H: "// [DOC] 인터랙터\nclass UNSInteractorComponent { void Use(); };\n",
        C: "// [PSEUDO] Use 본문\nvoid UNSInteractorComponent::Use() {}\n"}


class FakeFacts:
    host, user, path, windows = "w1", "u", "/trunk/NS", False


def both(marker: str = "") -> str:
    """두 파일을 규약대로 낸 응답."""
    return (f"=== FILE: {H} ===\n// [DOC] 인터랙터\nclass X {{}};\n\n"
            f"=== FILE: {C} ===\n{marker}// [DOC] 인터랙터\nvoid X::Use() {{ Do(); }}\n")


# ── ① 순서 ──────────────────────────────────────────────────────────────────────

def test_default_order_is_agy_then_local_and_claude_is_absent() -> None:
    """🔴 **사용자 지시 2026-09-04**: *"agy, 그다음 로컬로 배선하고, 클로드는 나중에 사용해"*.

    [중요] `claude` 를 뺀 것은 품질 판정이 아니다 — 한도가 **공용 자원**이라 먼저 쓰면 라운드
    전체가 그 한도에 묶인다. 실측 00:16: `429 session limit` 하나로 4조각 중 3이 동시에 죽었다.
    """
    check("[중요] 첫 레인이 agy", LN.DEFAULT_LANES[0] == "agy", str(LN.DEFAULT_LANES))
    check("  둘째가 로컬 모델", ":" in LN.DEFAULT_LANES[1] and "claude" not in LN.DEFAULT_LANES[1],
          str(LN.DEFAULT_LANES))
    check("[중요] claude 는 기본 체인에 없다",
          not any(l.startswith("claude") for l in LN.DEFAULT_LANES), str(LN.DEFAULT_LANES))


def test_prompt_names_every_file() -> None:
    """[주의] 실측: 지시에 파일 목록이 없으면 로컬 모델이 `.h` 를 빼먹는다 (`.2` 파일 1/2)."""
    p = LN.build_prompt(SKEL)
    check("두 파일이 프롬프트에 있다", H in p and C in p)
    check("[중요] 목록을 명시한다", "Files to implement:" in p, p[:120])
    check("마커 삭제를 지시한다", "DELETE that marker line" in p)
    check("동결 계약을 지시한다", "frozen contract" in p)
    try:
        LN.build_prompt({})
        check("빈 골조를 거부한다", False, "예외가 안 났다")
    except LN.LaneError:
        check("빈 골조를 거부한다", True)


# ── ② fail-forward ──────────────────────────────────────────────────────────────

def test_chain_moves_on_when_a_lane_fails() -> None:
    """🔴 **이 배선의 목적이다.** 종전에는 레인이 하나뿐이라 그 하나가 죽으면 조각이 죽었다."""
    seen, wrote = [], {}

    def gen(prompt, lane):
        seen.append(lane)
        if lane == "agy":
            raise RuntimeError("429 You've hit your session limit")
        return both()

    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=gen,
                              writer=lambda f, rel, body, base="": wrote.setdefault(rel, body))
    check("[중요] 다음 레인으로 넘어간다", got is not None and got.lane == LN.DEFAULT_LANES[1],
          str([t.summary for t in tried]))
    check("  순서대로 시도했다", seen == list(LN.DEFAULT_LANES), str(seen))
    check("  실패 사유를 남긴다", "session limit" in (tried[0].reason or ""), tried[0].reason)
    check("  두 파일을 워커에 썼다", set(wrote) == {H, C}, str(sorted(wrote)))


def test_all_lanes_failing_is_blocked_not_silent() -> None:
    def boom(prompt, lane):
        raise RuntimeError("nope")
    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=boom, writer=lambda *a, **k: None)
    check("[중요] 성공으로 접지 않는다", got is None)
    check("  시도를 전부 기록한다", len(tried) == len(LN.DEFAULT_LANES), str(len(tried)))


def test_missing_file_is_not_success() -> None:
    """[주의] 한 파일만 오면 `wcommit` 이 「빠진 파일」로 막는다 — 레인에서 먼저 잡는다."""
    def half(prompt, lane):
        return f"=== FILE: {C} ===\nvoid X::Use() {{ Do(); }}\n"
    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=half, writer=lambda *a, **k: None)
    check("[중요] 부분 응답을 통과시키지 않는다", got is None)
    check("  빠진 파일을 지목한다", tried[0].missing == [H], str(tried[0].missing))


# ── ③ 써 넣기 실패는 성공이 아니다 ──────────────────────────────────────────────

def test_write_failure_falls_through() -> None:
    """[중요] 텍스트를 받은 것과 **워커 디스크에 올라간 것**은 다르다."""
    def gen(prompt, lane):
        return both()

    def bad_writer(f, rel, body, base=""):
        raise OSError("scp 실패")

    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=gen, writer=bad_writer)
    check("[중요] 성공이 아니다", got is None)
    check("  사유가 써 넣기를 지목한다",
          any("써 넣지 못했다" in (t.reason or "") for t in tried),
          str([t.reason for t in tried]))


# ── ④ 파싱 — 펜스·잡음 ─────────────────────────────────────────────────────────

def test_markdown_fence_is_stripped() -> None:
    """[주의] 로컬 14b 의 **알려진 결함**이다 (`skeleton.py` 머리말) — 층1 도 잡지만 먼저 걷는다."""
    out = (f"=== FILE: {H} ===\n```cpp\nclass X {{}};\n```\n\n"
           f"=== FILE: {C} ===\n```cpp\nvoid X::Use() {{ Do(); }}\n```\n")
    got, miss = LN.parse_blocks(out, [H, C])
    check("두 파일을 읽었다", set(got) == {H, C}, str(sorted(got)))
    check("[중요] 백틱이 남지 않는다", not any("```" in v for v in got.values()),
          str(got.get(H, ""))[:80])
    check("빠진 것 없다", not miss)


def test_unknown_paths_are_ignored() -> None:
    """모델이 안 시킨 파일을 내면 **버린다** — 조각의 파일 집합 밖은 남의 것이다."""
    out = both() + f"\n=== FILE: Source/NS/Other.cpp ===\nvoid Other() {{}}\n"
    got, miss = LN.parse_blocks(out, [H, C])
    check("[중요] 목록 밖 파일은 안 받는다", set(got) == {H, C}, str(sorted(got)))
    check("빠진 것 없다", not miss)


def main() -> int:
    for fn in (test_default_order_is_agy_then_local_and_claude_is_absent,
               test_prompt_names_every_file,
               test_chain_moves_on_when_a_lane_fails,
               test_all_lanes_failing_is_blocked_not_silent,
               test_missing_file_is_not_success,
               test_write_failure_falls_through,
               test_markdown_fence_is_stripped,
               test_unknown_paths_are_ignored):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_lanes: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
