"""본문 작성 레인 (`#346`).

[중요] 지키는 계약은 넷이다:

    ① **순서** — agy → codex → claude → local, 제한 레인은 quota 조건을 만족해야 한다
    ② **실패 분류** — 모델 본문·형식 실패는 quota 증거가 아니다
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

def test_default_order_is_quota_aware_cloud_first() -> None:
    """#840의 현재 순서를 검사한다. 실제 호출 허용은 별도 시나리오가 검사한다."""
    check("첫 레인이 agy", LN.DEFAULT_LANES[0] == "agy", str(LN.DEFAULT_LANES))
    check("둘째가 codex", LN.DEFAULT_LANES[1] == "codex",
          str(LN.DEFAULT_LANES))
    check("  마지막이 로컬 모델 — 상용이 다 막혔을 때 남는 자리",
          ":" in LN.DEFAULT_LANES[-1] and "claude" not in LN.DEFAULT_LANES[-1],
          str(LN.DEFAULT_LANES))
    check("claude는 세번째 quota 전용 레인",
          LN.DEFAULT_LANES[2] == "claude", str(LN.DEFAULT_LANES))


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

    # [주의] **순서에 묶지 않는다** — 종전엔 `if lane == "agy"` 로 첫 레인을 이름으로 박아 둬서,
    #    2026-09-06 에 순서가 `codex → agy` 로 바뀌자 의도와 무관하게 깨졌다. 이 테스트가 재는
    #    것은 「첫 레인이 죽으면 다음으로 간다」이지 **누가 첫 레인인가**가 아니다.
    def gen(prompt, lane):
        seen.append(lane)
        if lane == LN.DEFAULT_LANES[0]:
            raise RuntimeError("429 You've hit your session limit")
        return both()

    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=gen,
                              writer=lambda f, rel, body, base="": wrote.setdefault(rel, body))
    check("[중요] 다음 레인으로 넘어간다", got is not None and got.lane == LN.DEFAULT_LANES[1],
          str([t.summary for t in tried]))
    # [주의] **성공하면 거기서 멈춘다** — 뒤 레인까지 다 부르지 않는다(폴백이지 병렬이 아니다)
    check("  순서대로 시도하고 성공에서 멈춘다", seen == list(LN.DEFAULT_LANES[:2]), str(seen))
    check("  실패 사유를 남긴다", "session limit" in (tried[0].reason or ""), tried[0].reason)
    check("  두 파일을 워커에 썼다", set(wrote) == {H, C}, str(sorted(wrote)))


def test_all_lanes_failing_is_blocked_not_silent() -> None:
    def boom(prompt, lane):
        raise RuntimeError("nope")
    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=boom, writer=lambda *a, **k: None)
    check("[중요] 성공으로 접지 않는다", got is None)
    check("일반 실패 뒤 Claude와 local을 부르지 않는다", len(tried) == 2, str(len(tried)))


def test_missing_file_is_not_success() -> None:
    """[주의] 한 파일만 오면 `wcommit` 이 「빠진 파일」로 막는다 — 레인에서 먼저 잡는다."""
    def half(prompt, lane):
        return f"=== FILE: {C} ===\nvoid X::Use() {{ Do(); }}\n"
    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=half, writer=lambda *a, **k: None)
    check("[중요] 부분 응답을 통과시키지 않는다", got is None)
    check("  빠진 파일을 지목한다", tried[0].missing == [H], str(tried[0].missing))


# ── ③ 써 넣기 실패는 성공이 아니다 ──────────────────────────────────────────────

def test_write_failure_stops_chain() -> None:
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
    check("쓰기 실패 뒤 다른 모델을 호출하지 않는다", len(tried) == 1, str(len(tried)))


def test_quota_only_fallback_and_local_provenance() -> None:
    for failure, expected in (("quota", list(LN.DEFAULT_LANES)),
                              ("format", ["agy", "codex"]),
                              ("mixed", ["agy", "codex"])):
        seen = []
        def gen(prompt, lane):
            seen.append(lane)
            if lane == LN.DEFAULT_LANES[-1]:
                return both()
            if failure == "format":
                return "usage limit reached"  # model text is not quota evidence
            if failure == "mixed" and lane == "codex":
                raise RuntimeError("transport failed")
            raise RuntimeError("usage limit reached")
        got, tried = LN.run_chain(FakeFacts(), SKEL, generator=gen,
                                 writer=lambda *a, **kw: None)
        check(f"{failure} 호출 순서", seen == expected, str(seen))
        if failure == "quota":
            check("local 성공은 재검증 표지", got is not None and got.needs_revalidation)
            check("local 출처에 세 cloud quota 보존", got is not None and
                  [a["kind"] for a in got.provenance] == ["quota"] * 3 + ["success"])
        else:
            check(f"{failure} 실패는 local 성공 아님", got is None)
            check(f"{failure} 명시 실패종류 유지", tried[-1].failure_kind ==
                  ("format" if failure == "format" else "error"))
    seen = []
    got, tried = LN.run_chain(FakeFacts(), SKEL, lanes=("qwen2.5-coder:14b",),
                             generator=lambda *a: seen.append(a) or both(),
                             writer=lambda *a, **kw: None)
    check("local 단일 override로 quota 우회 불가", not seen and got is None and not tried)


def test_excluded_clouds_are_not_called_840_2() -> None:
    """#840 ② — 진 클라우드는 부르지 않고, 남은 클라우드가 없으면 로컬로 가지 않는다."""
    seen = []
    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=lambda p, lane: seen.append(lane) or both(),
                             writer=lambda *a, **kw: None, excluded=["agy"])
    check("agy 제외 → codex 가 쓴다", got is not None and got.lane == "codex" and seen == ["codex"], str(seen))
    check("  codex 성공은 재검증 표지 아님", got is not None and not got.needs_revalidation)
    seen.clear()
    got, tried = LN.run_chain(FakeFacts(), SKEL, generator=lambda p, lane: seen.append(lane) or both(),
                             writer=lambda *a, **kw: None, excluded=["agy", "codex"])
    check("agy·codex 제외 → 아무도 안 부른다(claude·로컬 닫힘)", got is None and not seen and not tried,
          str(seen))


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


def test_python_pieces_get_the_python_instruction():
    """🔴 `#695` P4 — `.py` 조각은 Python 판 지시문, 섞이면 거절."""
    py = LN.build_prompt({"webui/a.py": "# [DOC] x\ndef f():\n    # [PSEUDO] y\n    raise NotImplementedError\n"})
    check("`.py` 조각은 Python 지시문", py.startswith(LN.INSTRUCTION_PY), py[:60])
    check("  UE 문구가 섞이지 않는다", "UE5" not in py.split("Files to implement")[0])
    for rule in ("raise NotImplementedError", "frozen contract", "Do NOT start servers",
                 "third-party imports"):
        check(f"  층1 이 재는 계약 · 금지를 말한다: {rule}", rule in LN.INSTRUCTION_PY)
    ue = LN.build_prompt({"Source/A/Foo.h": "x", "Source/A/Foo.cpp": "y"})
    check("[중요] UE 조각은 종전 지시문 그대로", ue.startswith(LN.INSTRUCTION))
    try:
        LN.build_prompt({"webui/a.py": "x", "src/b.cpp": "y"})
        check("🔴 섞인 조각은 거절한다", False, "예외가 안 났다")
    except LN.LaneError as e:
        check("🔴 섞인 조각은 거절한다", "섞였다" in str(e), str(e))


def main() -> int:
    for fn in (test_default_order_is_quota_aware_cloud_first,
               test_quota_only_fallback_and_local_provenance,
               test_excluded_clouds_are_not_called_840_2,
               test_prompt_names_every_file,
               test_chain_moves_on_when_a_lane_fails,
               test_all_lanes_failing_is_blocked_not_silent,
               test_missing_file_is_not_success,
               test_write_failure_stops_chain,
               test_markdown_fence_is_stripped,
               test_unknown_paths_are_ignored,
               test_python_pieces_get_the_python_instruction):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_lanes: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
