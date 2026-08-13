"""색인 일시 중지 게이트 (소 3.5.1) — 🔴 **`in_progress` 만 멈춘다.**

원전이 명시한 것: *"Phase 2 변경: `in_progress` 만 pause 조건. `ready_for_review` 는
auto_cleanup 이 이미 main 으로 복귀시킨 시점이라 watcher 재개해야 함."*
⚠️ 2026-08-14 에 내가 원전의 **cleanup 용 active 집합**을 pause 조건으로 잘못 옮겼다가
정독에서 정정했다. 그 정정을 여기서 **테스트로 못박는다.**

`.venv/bin/python master/test_gate.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.events import gate as G          # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def w(wid, status):
    return {"work_id": wid, "merge_status": status}


def test_only_in_progress_pauses():
    v = G.check(works=[w("a", "in_progress")])
    check("in_progress 는 멈춘다", v.paused and v.works == ("a",), str(v))

    for st in ("ready_for_review", "merged", "rejected", "cancelled", "", None):
        v = G.check(works=[w("a", st)])
        check(f"🔴 {st!r} 는 멈추지 않는다", not v.paused, str(v))


def test_mixed():
    v = G.check(works=[w("a", "merged"), w("b", "in_progress"), w("c", "ready_for_review")])
    check("섞여 있으면 in_progress 만 잡는다", v.paused and v.works == ("b",), str(v))
    v = G.check(works=[w("a", "merged"), w("c", "ready_for_review")])
    check("in_progress 가 없으면 진행", not v.paused, str(v))


def test_empty_and_case():
    check("work 0건이면 진행", not G.check(works=[]).paused)
    check("대소문자 무관", G.check(works=[w("a", "IN_PROGRESS")]).paused)


def test_unknown_state_does_not_pause_forever():
    """🔴 큐에도 디스크에도 못 물으면 **멈추지 않는다** — 항상 멈추는 게이트는 고장이다."""
    v = G.check(queue_url="http://127.0.0.1:1", spool_root=Path("/nonexistent-ax-spool"))
    check("근거가 없으면 진행한다", not v.paused, str(v))
    check("그 사실이 degraded 에 남는다", bool(v.degraded), v.degraded)
    check("source=none 으로 표시된다", v.source == "none", v.source)


def test_line_is_readable():
    v = G.check(works=[w("w1", "in_progress"), w("w2", "in_progress")])
    line = v.line()
    check("멈춤 줄에 건수가 있다", "2건" in line, line)
    check("멈춤 줄에 work_id 가 있다", "w1" in line, line)
    check("진행 줄은 멈춤이라 말하지 않는다",
          "중지" not in G.check(works=[]).line(), G.check(works=[]).line())


def main() -> int:
    for fn in (test_only_in_progress_pauses, test_mixed, test_empty_and_case,
               test_unknown_state_does_not_pause_forever, test_line_is_readable):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_gate: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
