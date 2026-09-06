"""거부된 합성의 보류·재시도 (`#377` ⓑ).

검증하는 것:

    ① 거부를 적고, 다음 실행이 **다시 끌어온다** (변경이 없어도)
    ② 성공하면 **지운다** — 목록이 낫는 것을 보여 준다
    ③ 🔴 **무한 재시도가 아니다** — 상한을 넘으면 `given_up`, 자동 재시도에서 빠진다
       (리포트 51: 같은 커밋을 하루 종일 다시 걷던 그 사고를 만들지 않는다)
    ④ [중요] 포기해도 **목록에는 남는다** — 조용히 사라지지 않는다
    ⑤ 한 실행이 끌어오는 수에 **상한**이 있다 (배치가 부풀지 않게)
    ⑥ 저장 위치가 `context/` **밖**이다 — 안에 두면 색인·태그가 문서로 센다
    ⑦ 요약 한 줄이 **보류/포기를 갈라** 말한다

`python3 master/test_pending.py`  (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.dont_write_bytecode = True

from master.context_synth import pending as P                               # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, got: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


def paths_in(tmp: Path):
    class P_:
        name = "T"
    P_.root = tmp
    P_.context = tmp / "context"
    P_.context.mkdir(parents=True, exist_ok=True)
    return P_()


def test_record_and_retry() -> None:
    print("①② 적고 · 끌어오고 · 성공하면 지운다")
    tmp = Path(tempfile.mkdtemp(prefix="ax-pending-"))
    try:
        p = paths_in(tmp)
        check("처음엔 비어 있다 (조용하다)", P.load(p) == {} and P.summary(p) == "")
        P.record(p, "Source/NS/Foo", ["Source/NS/Foo.h", "Source/NS/Foo.cpp"],
                 "사실 게이트 거부 — 주석에만 있는 식별자")
        got = P.load(p)["Source/NS/Foo"]
        check("사유·파일·시도횟수가 남는다",
              got["attempts"] == 1 and len(got["files"]) == 2 and "사실 게이트" in got["reason"],
              str(got))
        check("다음 실행이 끌어온다", [k for k, _f in P.due(p)] == ["Source/NS/Foo"])
        check("[중요] 성공하면 지운다", P.clear(p, "Source/NS/Foo") and P.load(p) == {})
        check("  없는 것을 지우면 False", P.clear(p, "없음") is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_not_an_infinite_loop() -> None:
    """🔴 리포트 51 의 그 사고 — 같은 실패를 하루 종일 반복하지 않는다."""
    print("③④ 상한을 넘으면 자동 재시도를 멈춘다")
    tmp = Path(tempfile.mkdtemp(prefix="ax-pending-"))
    try:
        p = paths_in(tmp)
        for i in range(P.MAX_ATTEMPTS):
            P.record(p, "Source/NS/Bad", ["Source/NS/Bad.h"], "사실 게이트 거부")
            still = [k for k, _f in P.due(p)]
            if i < P.MAX_ATTEMPTS - 1:
                check(f"  {i+1}회차 — 아직 재시도 대상", still == ["Source/NS/Bad"], str(still))
        check(f"🔴 {P.MAX_ATTEMPTS}회 뒤에는 자동 재시도에서 빠진다", P.due(p) == [], str(P.due(p)))
        check("[중요] 그래도 목록에는 남는다 — 조용히 사라지지 않는다",
              P.given_up(p) == ["Source/NS/Bad"], str(P.given_up(p)))
        check("  요약이 **사람이 봐야 한다**고 말한다",
              "포기 1건" in P.summary(p) and "사람이 봐야" in P.summary(p), P.summary(p))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cap_and_location() -> None:
    print("⑤⑥⑦ 상한 · 저장 위치 · 요약")
    tmp = Path(tempfile.mkdtemp(prefix="ax-pending-"))
    try:
        p = paths_in(tmp)
        for i in range(P.RETRY_CAP + 5):
            P.record(p, f"Source/NS/G{i:02d}", [f"Source/NS/G{i:02d}.h"], "거부")
        check("한 실행이 끌어오는 수에 상한", len(P.due(p)) == P.RETRY_CAP, str(len(P.due(p))))
        check("  상한을 인자로 줄일 수 있다", len(P.due(p, cap=3)) == 3)

        f = tmp / P.FILE
        check("[중요] 저장 파일이 `context/` 밖이다 (안에 두면 문서로 센다)",
              f.is_file() and "context" not in f.relative_to(tmp).parts, str(f))
        s = P.summary(p)
        check("⑦ 요약이 보류 수를 말한다", "보류" in s, s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    for fn in (test_record_and_retry, test_not_an_infinite_loop, test_cap_and_location):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_pending: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
