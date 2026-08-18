"""#223 파이프라인 단계 스텝퍼 계약.

핵심 계약:
① [중요] **큐가 기록하는 단계만 그린다** — 서술상 12단계지만 태스크 레코드가 증거를 갖는 것은
   여섯이다. 마스터 측(분해·collect·층1·적용·커밋)은 그리지 않고, 안 그린다는 사실을 화면에 적는다
② 추정하지 않는다 — 근거 필드가 없으면 `pending` (「아마 지났을 것」을 done 으로 만들지 않는다)
③ 착수 실패(build-setup·infer-setup)는 **제출에 이르지 못한** 실패다 — 실행에서 끊긴다
④ 색만으로 의미를 전달하지 않는다 — 라벨 + `<title>` + 실패는 X 표식

실행: python3 master/test_stepper.py  (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from master import status as S                                  # noqa: E402


def _states(task, work=None) -> dict:
    return {label: state for label, state, _ in S.stage_steps(task, work)}


# ── ② 근거가 있는 것만 done ─────────────────────────────────────

def test_pending_task_only_registration_done():
    got = _states({"created": "2026-08-19T01:00:00+09:00", "status": "pending"})
    assert got["등록"] == "done"
    assert got["배정"] == "current"          # 아직 아무도 안 집었다 = 배정 중
    assert got["실행"] == "pending" and got["제출"] == "pending"
    assert got["판정"] == "pending" and got["종결"] == "pending"


def test_claimed_task_is_running():
    got = _states({"created": "c", "status": "claimed", "claimed_at": "2026-08-19T01:10:55+09:00",
                   "note": "UE5 빌드 중"}, {"merge_status": "in_progress"})
    assert got["배정"] == "done" and got["실행"] == "current"
    assert got["제출"] == "pending" and got["판정"] == "pending"


def test_submitted_task_awaits_verdict():
    got = _states({"created": "c", "status": "submitted", "claimed_at": "a",
                   "submitted_at": "2026-08-19T01:13:05+09:00"},
                  {"merge_status": "in_progress"})
    assert got["실행"] == "done" and got["제출"] == "done"
    assert got["판정"] == "current" and got["종결"] == "pending"


def test_verified_and_merged_is_all_done():
    got = _states({"created": "c", "status": "verified", "claimed_at": "a",
                   "submitted_at": "b", "verified_at": "d", "verdict": "pass"},
                  {"merge_status": "merged"})
    assert all(v == "done" for v in got.values()), got


# ── ③ 실패의 위치 ──────────────────────────────────────────────

def test_setup_failure_breaks_at_execution_not_verdict():
    """착수 실패는 제출에 이르지 못한 실패다 — 판정 단계까지 실패로 칠하면 거짓말이 된다."""
    got = _states({"created": "c", "status": "failed", "claimed_at": "a",
                   "fail_reason": "build-setup"}, {"merge_status": "cancelled"})
    assert got["실행"] == "failed" and got["제출"] == "failed"
    assert got["판정"] == "failed" and got["종결"] == "failed"


def test_verdict_rejection_keeps_execution_done():
    """빌드는 돌았고 판정에서 막힌 경우 — 실행·제출은 done 이다."""
    got = _states({"created": "c", "status": "failed", "claimed_at": "a",
                   "submitted_at": "b", "verified_at": "d", "verdict": "reject"},
                  {"merge_status": "rejected"})
    assert got["실행"] == "done" and got["제출"] == "done"
    assert got["판정"] == "failed" and got["종결"] == "failed"


def test_never_claimed_failure_marks_assignment_failed():
    got = _states({"created": "c", "status": "failed"}, {})
    assert got["배정"] == "failed" and got["실행"] == "pending"


# ── ④ 렌더 — 색 외 신호 ────────────────────────────────────────

def test_svg_is_self_contained_and_labels_states():
    steps = S.stage_steps({"created": "c", "status": "claimed", "claimed_at": "a",
                           "note_at": "2026-08-19T01:10:56+09:00"},
                          {"merge_status": "in_progress"})
    out = S.stepper_svg(steps)
    assert out.startswith("<svg") and out.endswith("</svg>")
    assert "http" not in out and "<script" not in out      # 자립형 — 외부 참조 금지
    for label in S.PIPE_STAGES:
        assert f">{label}</text>" in out, label
    assert "<title>실행: current" in out                    # 상태를 글자로도 말한다
    assert 'role="img"' in out and 'aria-label' in out


def test_svg_marks_failure_with_shape_not_only_color():
    steps = S.stage_steps({"created": "c", "status": "failed", "claimed_at": "a"}, {})
    out = S.stepper_svg(steps)
    assert "<path d=" in out                                # X 표식
    assert "var(--critical)" in out


def test_svg_escapes_and_empty_is_empty():
    assert S.stepper_svg([]) == ""
    out = S.stepper_svg([("<b>", "done", "2026-08-19T01:00:00+09:00")])
    assert "&lt;b&gt;" in out and "<b>" not in out


def test_work_section_embeds_stepper_and_caption():
    works = [{"work_id": "W", "merge_status": "in_progress", "total": 1,
              "created": "2026-08-19T01:10:52+09:00"}]
    tasks = [{"task_id": "420a5c1e", "work_id": "W", "status": "claimed", "type": "build",
              "created": "c", "claimed_at": "2026-08-19T01:10:55+09:00"}]
    out = S.work_section(works, tasks)
    assert "<svg" in out and "420a5c1e" in out
    assert "큐가 기록하는 여섯" in out                        # 안 그리는 것을 적는다
    assert "분해·collect·층1·적용·커밋" in out


def test_work_section_caps_steppers_per_work():
    works = [{"work_id": "W", "merge_status": "in_progress", "total": 9}]
    tasks = [{"task_id": f"t{i}", "work_id": "W", "status": "pending", "created": "c"}
             for i in range(9)]
    out = S.work_section(works, tasks)
    assert len(re.findall(r"<svg", out)) == S.STEPPER_MAX


def test_closed_work_draws_one_stepper_only():
    works = [{"work_id": "W", "merge_status": "merged", "total": 3}]
    tasks = [{"task_id": f"t{i}", "work_id": "W", "status": "verified", "created": "c",
              "claimed_at": "a", "submitted_at": "b", "verified_at": "d"} for i in range(3)]
    out = S.work_section(works, tasks)
    assert len(re.findall(r"<svg", out)) == 1


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 통과")
    sys.exit(1 if failed else 0)
