"""자동 파견의 판정 — `needs_integration` (신설 2026-09-02).

[중요] **이 모듈에 테스트가 하나도 없었다.** 2026-08-29~31 이틀을 태운 곳이고(파견이 걸렸는지
찍지 않아 침묵이 배선 사망과 구별되지 않았다), 정본 ⑸ 로 `submitted` 의 **뜻이 바뀌는**
자리라 판정을 고정한다.

여기서 지키는 계약:

    ① `submitted` = **워커가 커밋했다** → 통합이 아니라 **⑺ 사람 승인 대기**
    ② [중요] **사유 문구가 거짓말을 하지 않는다** — 종전 문구는 통합이 손댄 적 없는데
       *"이미 통합이 손을 댔다"* 였다. 그 종류의 오문구가 이틀을 태웠다
    ③ 보류·pending·응답 결손은 각각 **다른 사유**로 멈춘다 (뭉치면 원인이 흐려진다)

`python3 master/test_autodispatch.py`
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import autodispatch as A                        # noqa: E402

PASS = FAIL = 0
WORK = "20260902_0035_ns_1_ea254ff3"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class _Paths:
    def __init__(self, root: Path):
        self.name = "T"
        self.root = root
        self.responses = root / "responses"


def _api(tasks, *, merge_status="in_progress"):
    def call(method, path, payload=None, *, timeout=20):
        if path.endswith(f"/works/{WORK}"):
            return {"work": {"merge_status": merge_status}, "tasks": tasks}
        raise AssertionError(f"예상 밖 호출: {method} {path}")
    return call


def _spool(paths: _Paths, work_id: str, statuses):
    """스풀에 응답 레코드를 놓는다 — `needs_integration` 이 실물로 센다."""
    from master.work.infer import spool_dir
    d = spool_dir(paths, work_id)
    d.mkdir(parents=True, exist_ok=True)
    for i, st in enumerate(statuses):
        (d / f"t{i}.json").write_text(
            json.dumps({"task_id": f"t{i}", "status": st}, ensure_ascii=False),
            encoding="utf-8")


def _no_hold():
    orig = A.hold_active
    A.hold_active = lambda: (False, "")
    return orig


def test_submitted_means_worker_committed():
    """🔴 정본 ⑸ — `submitted` 는 **워커가 커밋한 것**이고 다음은 ⑺ 사람 승인이다."""
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            tasks = [{"task_id": "t0", "status": "submitted"},
                     {"task_id": "t1", "status": "submitted"}]
            need, why = A.needs_integration(p, WORK, api=_api(tasks))
            check("통합을 자동으로 걸지 않는다", not need, why)
            check("[중요] **사유가 ⑺ 사람 승인을 가리킨다**", "사람 승인" in why, why)
            check("[중요] **「통합이 손을 댔다」로 거짓말하지 않는다**",
                  "통합이 손을 댔다" not in why, why)
            check("  몇 건인지 센다", "2/2" in why, why)
    finally:
        A.hold_active = orig


def test_failed_is_its_own_reason():
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            tasks = [{"task_id": "t0", "status": "failed"}]
            need, why = A.needs_integration(p, WORK, api=_api(tasks))
            check("실패는 멈춘다", not need, why)
            check("[중요] 실패와 완료를 **다른 사유**로 구분한다",
                  "실패" in why and "사람 승인" not in why, why)
    finally:
        A.hold_active = orig


def test_pending_blocks_first():
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            tasks = [{"task_id": "t0", "status": "pending"},
                     {"task_id": "t1", "status": "claimed"}]
            need, why = A.needs_integration(p, WORK, api=_api(tasks))
            check("pending 이 있으면 파견이 먼저다", not need and "pending" in why, why)
    finally:
        A.hold_active = orig


def test_claimed_with_full_spool_integrates():
    """[주의] 옛 경로(⑸ 전)도 여전히 성립해야 한다 — `claimed` + 스풀 전량."""
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            tasks = [{"task_id": "t0", "status": "claimed"},
                     {"task_id": "t1", "status": "claimed"}]
            _spool(p, WORK, ["DONE", "DONE"])
            need, why = A.needs_integration(p, WORK, api=_api(tasks))
            check("응답이 조각 수만큼 오면 통합한다", need, why)
            check("  통과 수를 문장에 싣는다", "통과 2" in why, why)
    finally:
        A.hold_active = orig


def test_partial_spool_waits():
    """[중요] `pending 0` 은 「추론 완료」가 아니다 (실측 2026-09-01 01:03)."""
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            tasks = [{"task_id": "t0", "status": "claimed"},
                     {"task_id": "t1", "status": "claimed"}]
            _spool(p, WORK, ["DONE"])          # 1/2 만 왔다
            need, why = A.needs_integration(p, WORK, api=_api(tasks))
            check("[중요] 덜 끝났으면 기다린다 (전량 재적용 방지)",
                  not need and "1/2" in why, why)
    finally:
        A.hold_active = orig


def test_all_failed_spool_has_nothing_to_apply():
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            tasks = [{"task_id": "t0", "status": "claimed"}]
            _spool(p, WORK, ["BLOCKED"])
            need, why = A.needs_integration(p, WORK, api=_api(tasks))
            check("[중요] 실패 응답을 「완료」로 세지 않는다",
                  not need and "통과한 응답이 0건" in why, why)
    finally:
        A.hold_active = orig


def test_hold_blocks_integration_too():
    """[중요] 세션 한도 보류는 통합에도 걸린다 — 층2 도 같은 `claude` 를 쓴다."""
    orig = A.hold_active
    A.hold_active = lambda: (True, "세션 한도 — 03:40 까지 보류")
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            need, why = A.needs_integration(p, WORK, api=_api([]))
            check("보류면 멈춘다", not need and "보류" in why, why)
    finally:
        A.hold_active = orig


def test_merge_status_gate():
    orig = _no_hold()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = _Paths(Path(td))
            need, why = A.needs_integration(
                p, WORK, api=_api([{"task_id": "t0", "status": "claimed"}],
                                  merge_status="ready_for_review"))
            check("이미 검수 대기면 통합하지 않는다",
                  not need and "merge_status" in why, why)
    finally:
        A.hold_active = orig


def main() -> int:
    for fn in (test_submitted_means_worker_committed, test_failed_is_its_own_reason,
               test_pending_blocks_first, test_claimed_with_full_spool_integrates,
               test_partial_spool_waits, test_all_failed_spool_has_nothing_to_apply,
               test_hold_blocks_integration_too, test_merge_status_gate):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_autodispatch: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
