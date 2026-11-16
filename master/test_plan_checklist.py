"""마감 체크리스트 판정(`#963` T4) 순수 계약 — 미확인 목록 · 옛 플랜 통과 · 읽기 실패 미통과.

실행: .venv/bin/python master/test_plan_checklist.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB            # noqa: E402
from master import plan_checklist as PC        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _body(*states):
    cl = [PB.IssuePlanCheck(f"C{i}", st, f"항목{i}", "근거" if st != "미확인" else "") for i, st in enumerate(states, 1)]
    return PB.append("## 스펙\n\n본문\n", [PB.IssuePlanTask("T1", "대기", "목표")], checklist=cl, autonomy=0.5)


def main() -> int:
    v = PC.judge(_body("미확인", "충족", "미확인"))
    check("미확인 목록", not v.ok and [p["id"] for p in v.pending] == ["C1", "C3"]
          and v.counts == {"미확인": 2, "충족": 1, "제외": 0}, str(v))
    check("사람에게 묻는 문장", "사용자에게 항목별로 묻는다" in v.why and "C1, C3" in v.why)
    check("모두 표시 → 통과", PC.judge(_body("충족", "제외")).ok)
    check("옛 플랜 → 통과", PC.judge(PB.append("본문\n", [PB.IssuePlanTask("T1", "대기", "x")])).ok)
    check("플랜 없음 → 통과", PC.judge("본문만").ok)
    check("깨진 플랜 → 미통과", not PC.judge("<!-- ax:plan:begin v=3 -->\n").ok)
    check("읽기 오류 → 미통과", not PC.check(1, lambda i: {"error": "HTTP 500"}).ok)
    check("읽기 예외 → 미통과", not PC.check(1, lambda i: 1 / 0).ok)
    check("as_dict 통과는 pending 없음", "pending" not in PC.judge(_body("충족")).as_dict())
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_checklist: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
