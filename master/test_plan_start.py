"""「일감 시작」 진입점(`#826` T3) 계약 테스트 — [중요] **플랜이 없으면 구현으로 넘어가지 않는가.**

실행: python3 master/test_plan_start.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB    # noqa: E402
from master import plan_start as ST    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


SPEC = "## 스펙\n\n요구와 완료 조건\n"


def _body(*rows, spec=SPEC) -> str:
    return PB.append(spec, [PB.Task(tid, st, "목표", deps=list(deps), evidence=ev)
                            for tid, st, deps, ev in rows])


def _v(body: str) -> ST.StartVerdict:
    return ST.assess(body)


def test_no_plan_is_not_ok():
    v = _v(SPEC)
    check("플랜 없음 → plan_needed", v.verdict == "plan_needed", v.verdict)
    check("[중요] plan_needed 는 ok 가 아니다", not v.ok)
    check("다음 행동이 「구현하지 않는다」", "구현하지 않는다" in v.next_action)


def test_no_spec():
    for body in ("", "   \n", _body(("T1", "대기", (), ""), spec="")):
        v = _v(body)
        check(f"스펙 없음 → no_spec ({body[:20]!r})", v.verdict == "no_spec" and not v.ok, v.verdict)


def test_invalid_plan():
    bad = SPEC + "<!-- ax:plan:begin v=1 -->\n| 엉망 |\n<!-- ax:plan:end -->\n"
    v = _v(bad)
    check("형식 오류 → plan_invalid", v.verdict == "plan_invalid" and not v.ok, v.verdict)
    check("사유를 담는다", bool(v.detail), str(v.detail))
    check("태그 짝이 깨져도 plan_invalid",
          _v(SPEC + "<!-- ax:plan:end -->\n").verdict == "plan_invalid")


def test_violations():
    v = _v(_body(("T1", "완료", (), "")))
    check("근거 빈 완료 → plan_violations", v.verdict == "plan_violations" and not v.ok, v.verdict)
    check("위반 문장을 담는다", any("T1" in d for d in v.detail), str(v.detail))


def test_resume_first():
    v = _v(_body(("T1", "완료", (), "abc"), ("T2", "작업중", ("T1",), ""), ("T3", "대기", (), "")))
    check("작업중이 있으면 resume", v.verdict == "resume" and v.ok and v.tasks == ["T2"], str(v))


def test_next_picks_first_startable():
    v = _v(_body(("T1", "완료", (), "abc"), ("T2", "대기", ("T3",), ""),
                 ("T3", "대기", ("T1",), "")))
    check("선행이 안 끝난 T2 를 건너뛰고 T3", v.verdict == "next" and v.tasks == ["T3"], str(v))
    v = _v(_body(("T1", "대기", (), ""), ("T2", "대기", (), "")))
    check("표 순서대로 첫 태스크", v.tasks == ["T1"], str(v))


def test_blocked():
    v = _v(_body(("T1", "차단", (), "큐 응답 없음"), ("T2", "대기", ("T1",), "")))
    check("시작할 것이 없으면 blocked", v.verdict == "blocked" and not v.ok, v.verdict)
    check("차단 사유를 보인다", any("큐 응답 없음" in d for d in v.detail), str(v.detail))
    check("선행 대기를 보인다", any(d.startswith("T2:") and "T1" in d for d in v.detail), str(v.detail))


def test_plan_done():
    v = _v(_body(("T1", "완료", (), "abc"), ("T2", "해당없음", (), "kind=code")))
    check("전부 끝 → plan_done", v.verdict == "plan_done" and not v.ok, v.verdict)
    check("일감 완료는 따로 판단한다고 말한다", "따로" in v.next_action)


def test_start_issue_reads_and_reports():
    got = {"id": 826, "subject": "제목", "description": _body(("T1", "대기", (), ""))}
    out = ST.start_issue(826, getter=lambda iid: got)
    check("이슈를 읽어 판정한다", out["verdict"] == "next" and out["ok"] and out["tasks"] == ["T1"], str(out))
    check("번호·제목을 싣는다", out["issue_id"] == 826 and out["subject"] == "제목")
    check("다음 행동 문장이 있다", bool(out["next_action"]))
    for bad in ({"error": "#9 없음 (404)"}, None, []):
        out = ST.start_issue(9, getter=lambda iid, b=bad: b)
        check(f"읽기 실패 {bad!r} 는 판정이 아니라 오류", "error" in out and "verdict" not in out, str(out))


def test_assess_never_writes():
    body = _body(("T1", "대기", (), ""))
    before = body
    ST.assess(body)
    check("판정은 본문을 바꾸지 않는다", body == before)


def main() -> int:
    for fn in (test_no_plan_is_not_ok,
               test_no_spec,
               test_invalid_plan,
               test_violations,
               test_resume_first,
               test_next_picks_first_startable,
               test_blocked,
               test_plan_done,
               test_start_issue_reads_and_reports,
               test_assess_never_writes):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_start: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
