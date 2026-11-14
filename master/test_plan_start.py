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


ALL_KEYS = [k for k, _ in ST.SPEC_SECTIONS]
SPEC_DOC = Path(__file__).resolve().parent.parent / "docs" / "issue-spec.md"


def _doc_example() -> str:
    text = SPEC_DOC.read_text(encoding="utf-8")
    a = text.index("<!-- issue-spec-example:begin -->")
    b = text.index("<!-- issue-spec-example:end -->")
    return text[a:b]


def test_spec_missing_template_example():
    """#911 — 템플릿 문서의 예시 본문은 누락 0 이어야 한다(문서와 검출 규칙이 한 쌍)."""
    ex = _doc_example()
    check("템플릿 예시 본문 → 누락 없음", ST.spec_missing(ex) == [], str(ST.spec_missing(ex)))
    for key, _ in ST.SPEC_SECTIONS:
        check(f"템플릿 문서 §2 표에 `{key}` 가 있다", f"`{key}`" in SPEC_DOC.read_text(encoding="utf-8"))


def test_spec_missing_reports_absent_sections():
    check("빈 본문 → 전부 누락", ST.spec_missing("") == ALL_KEYS, str(ST.spec_missing("")))
    check("종전 최소 스펙 → 전부 누락", ST.spec_missing(SPEC) == ALL_KEYS, str(ST.spec_missing(SPEC)))
    body = "## 배경\r\n설명\r\n### 범위와 비범위\r\n- a\r\n## 완료 조건\r\nrc 0\r\n"
    check("일부만 있으면 빠진 키만 (CRLF·제목 수준 무관)",
          ST.spec_missing(body) == ["triage", "observe", "open"], str(ST.spec_missing(body)))
    check("본문 줄의 열쇠말은 세지 않는다 — 제목 줄만",
          ST.spec_missing("문제 분류 관측 범위 완료 조건 열린 결정\n") == ALL_KEYS)
    check("영문 열쇠말은 대소문자 무관", "observe" not in ST.spec_missing("## You See\nx\n"))


def test_spec_missing_ignores_plan_area():
    plan = PB.append(SPEC, [PB.Task("T1", "대기", "목표")])
    fake = plan.replace("<!-- ax:plan:end -->", "## 문제 분류 관측 범위 완료 조건 열린 결정\n<!-- ax:plan:end -->")
    check("플랜 영역 안의 제목은 세지 않는다", ST.spec_missing(fake) == ALL_KEYS, str(ST.spec_missing(fake)))


def test_spec_missing_is_warning_only():
    """[중요] 경고만 — 판정은 스펙 항목 유무와 무관하다(사용자 결정 2026-11-14)."""
    full = _doc_example()
    for body in (SPEC, full):
        check(f"판정 불변 — plan_needed ({len(ST.spec_missing(body))}개 누락)",
              ST.assess(body).verdict == "plan_needed")
    rows = (("T1", "대기", (), ""),)
    check("누락이 있어도 next 는 ok", ST.assess(_body(*rows)).ok)
    got = {"id": 1, "subject": "s", "description": _body(*rows)}
    out = ST.start_issue(1, getter=lambda iid: got)
    check("start_issue 응답에 spec_missing 이 실린다",
          out.get("spec_missing") == ALL_KEYS and out["ok"], str(out))
    check("as_dict 키는 그대로 + spec_missing 하나만 더한다",
          set(out) == {"verdict", "ok", "tasks", "detail", "next_action", "issue_id", "subject", "spec_missing"},
          str(sorted(out)))


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
               test_assess_never_writes,
               test_spec_missing_template_example,
               test_spec_missing_reports_absent_sections,
               test_spec_missing_ignores_plan_area,
               test_spec_missing_is_warning_only):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_start: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
