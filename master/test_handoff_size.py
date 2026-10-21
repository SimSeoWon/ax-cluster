"""인수인계서 길이 가드 (`#842`) — `docs/orchestrator-handoff.md` 는 한 벌로 덮어쓴다.

2026-10-21 에 2,506줄(338KB)까지 쌓여 한 번에 읽히지 않았다. 원인은 세션마다 새 체크포인트를
위에 쓰고 직전 것을 「이전 체크포인트」로 내려 남긴 것이고, 「한 벌만 유지」(`docs/15` §15.3)는
문장뿐이라 아무도 막지 않았다. 그래서 코드가 막는다.

재는 것:
  ① 줄 수가 상한 이하
  ② 「이전 체크포인트」 항목이 없다 — 쌓는 갱신의 흔적
  ③ `AGENTS.md` 가 가리키는 「바로 다음 작업」 절이 있다
  ④ 가드가 실제로 잡는다 — 옮겨 둔 옛 원문(history)을 넣으면 실패한다

`.venv/bin/python master/test_handoff_size.py` (venv 없이 `python3` 도 된다)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs" / "orchestrator-handoff.md"
HISTORY = ROOT / "docs" / "orchestrator-handoff-history.md"
MAX_LINES = 150
STACKED = re.compile(r"^\s*-\s*\*\*이전 체크포인트", re.M)
NEXT_STEP = re.compile(r"^#{2,3}\s*바로 다음 작업", re.M)

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


def problems(text: str) -> list[str]:
    out = []
    n = text.count("\n") + (0 if text.endswith("\n") else 1)
    if n > MAX_LINES:
        out.append(f"{n}줄 > 상한 {MAX_LINES} — 덮어써서 줄이고 지난 내용은 reports/·Redmine 노트로")
    k = len(STACKED.findall(text))
    if k:
        out.append(f"「이전 체크포인트」 {k}개 — 쌓지 말고 덮어쓴다")
    if not NEXT_STEP.search(text):
        out.append("「바로 다음 작업」 절 없음 — AGENTS.md 가 이 절을 가리킨다")
    return out


def test_current_handoff() -> None:
    p = problems(HANDOFF.read_text(encoding="utf-8"))
    check("현재 인수인계서가 상한·형식을 지킨다", not p, " · ".join(p))


def test_guard_catches_stacked_history() -> None:
    if not HISTORY.exists():
        check("옛 원문이 있다(가드 실측용)", False, str(HISTORY))
        return
    p = problems(HISTORY.read_text(encoding="utf-8"))
    check("🔴 옛 원문(2,506줄)은 줄 수로 걸린다", any("상한" in x for x in p), " · ".join(p))
    check("🔴 옛 원문은 「이전 체크포인트」로 걸린다", any("이전 체크포인트" in x for x in p), " · ".join(p))


def test_small_cases() -> None:
    ok = "# 현재 AX 작업 인수인계\n\n## 바로 다음 작업\n\n1. 대조\n"
    check("짧은 정상본 → 통과", not problems(ok), " · ".join(problems(ok)))
    check("「바로 다음 작업」 빠짐 → 걸린다", problems("# 현재\n\n## 상태\n"))
    check("쌓인 항목 한 개 → 걸린다", problems(ok + "\n- **이전 체크포인트: 어제**\n"))
    check("상한 초과 → 걸린다", problems(ok + "x\n" * MAX_LINES))


def main() -> int:
    test_current_handoff()
    test_guard_catches_stacked_history()
    test_small_cases()
    print(f"{'OK' if not FAIL else 'FAIL'} test_handoff_size: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
