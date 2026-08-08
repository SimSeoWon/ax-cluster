"""능력 기반 라우팅(`requires` / `capabilities`) 계약 테스트 — PLAN §5.2-C.

핵심은 **능력을 신고하지 않은 워커에게 `requires` 잡이 절대 새지 않는다**는 것.
(마스터 워커가 UE5 잡을 집어가면 파일이 없는 기계에서 빌드가 도는 셈이 된다.)

실행: .venv/bin/python master/test_capability_routing.py
      — task_queue 가 pydantic 을 쓰므로 시스템 python3 가 아니라 **venv** 로 돌린다.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue.logic import (  # noqa: E402
    register_work, register_task, claim_task, _worker_meets_requires,
)
from master.task_queue.models import normalize_capabilities  # noqa: E402
from master.task_queue.persistence import TaskIndex  # noqa: E402


# ── 하네스 ────────────────────────────────────────────────────

def _idx() -> TaskIndex:
    """임시 root 의 빈 큐. git 미초기화라 audit commit 은 silent skip 된다."""
    root = Path(tempfile.mkdtemp(prefix="ax-caproute-"))
    idx = TaskIndex(root)
    r = register_work(idx, title="t", target_repo="/tmp/repo")
    assert r.get("ok"), r
    idx._test_work_id = r["work_id"]
    return idx


def _add(idx: TaskIndex, requires=None, priority: int = 0, stem: str = "s") -> dict:
    return register_task(idx, work_id=idx._test_work_id, type="write",
                         task_data={}, stem=stem, priority=priority,
                         requires=requires)


# ── 등록 시점 검증 ────────────────────────────────────────────

def test_unknown_requires_is_rejected_at_register():
    """🔴 오타를 통과시키면 아무도 못 집는 task 가 조용히 굶는다."""
    r = _add(_idx(), requires=["ue-5"])
    assert not r.get("ok")
    assert "unknown requires" in r.get("error", "")


def test_requires_is_normalized():
    idx = _idx()
    r = _add(idx, requires=["  UE5 ", "ue5", "Windows"])
    assert r["ok"]
    assert idx.tasks[r["task_id"]]["requires"] == ["ue5", "windows"]


def test_no_requires_defaults_to_empty():
    idx = _idx()
    r = _add(idx)
    assert idx.tasks[r["task_id"]]["requires"] == []


# ── 🔴 fail-closed 라우팅 ─────────────────────────────────────

def test_capability_less_worker_cannot_claim_ue5_task():
    """이 테스트가 이 기능의 존재 이유다 — 마스터 워커의 UE5 잡 탈취 차단."""
    idx = _idx()
    _add(idx, requires=["ue5"])
    assert claim_task(idx, "master-worker") is None


def test_old_worker_unchanged_on_plain_tasks():
    """능력 인자를 아예 안 보내는 구 워커는 requires 없는 task 를 그대로 집는다(하위호환)."""
    idx = _idx()
    _add(idx)
    t = claim_task(idx, "old-worker")
    assert t is not None and t["job_kind"] == "write"


def test_ue5_worker_claims_ue5_task():
    idx = _idx()
    r = _add(idx, requires=["ue5"])
    t = claim_task(idx, "win-pc-1", capabilities=["ue5"])
    assert t is not None and t["task_id"] == r["task_id"]


def test_partial_capability_is_not_enough():
    """부분집합 매칭 — 하나라도 모자라면 못 집는다."""
    idx = _idx()
    _add(idx, requires=["ue5", "windows"])
    assert claim_task(idx, "half", capabilities=["ue5"]) is None
    assert claim_task(idx, "full", capabilities=["ue5", "windows"]) is not None


def test_extra_capability_is_harmless():
    idx = _idx()
    _add(idx)
    assert claim_task(idx, "win-pc-1", capabilities=["ue5", "windows"]) is not None


def test_skip_does_not_stop_the_scan():
    """능력 미달 task 는 **건너뛰고 계속** 봐야 한다 — 큐 앞을 막으면 안 된다.

    우선순위가 높은 UE5 잡이 먼저 오지만, 능력 없는 워커는 그 뒤의 일반 잡을 집어야 한다."""
    idx = _idx()
    _add(idx, requires=["ue5"], priority=10, stem="ue5-job")
    plain = _add(idx, priority=1, stem="plain-job")
    t = claim_task(idx, "master-worker")
    assert t is not None and t["task_id"] == plain["task_id"]


def test_ue5_task_stays_claimable_by_the_right_worker():
    """능력 미달 워커가 지나간 뒤에도 task 는 pending 그대로여야 한다(소비되지 않음)."""
    idx = _idx()
    r = _add(idx, requires=["ue5"])
    claim_task(idx, "master-worker")
    assert idx.tasks[r["task_id"]]["status"] == "pending"
    assert claim_task(idx, "win-pc-1", capabilities=["ue5"]) is not None


# ── verify 잡도 같은 규칙 ─────────────────────────────────────

def _make_submitted(idx: TaskIndex, requires=None) -> str:
    r = _add(idx, requires=requires)
    t = idx.tasks[r["task_id"]]
    t["status"] = "submitted"
    t["distribution_mode"] = "push"
    t["worker_id"] = "someone-else"
    t["submitted_at"] = "2026-08-08T09:00:00+09:00"
    return r["task_id"]


def test_verify_job_is_capability_gated():
    """검증자도 diff 를 쥐려면 파일 소유 기계여야 한다(§2.1)."""
    idx = _idx()
    _make_submitted(idx, requires=["ue5"])
    assert claim_task(idx, "master-worker", verify_capable=True) is None


def test_verify_job_goes_to_capable_worker():
    idx = _idx()
    tid = _make_submitted(idx, requires=["ue5"])
    t = claim_task(idx, "win-pc-1", verify_capable=True, capabilities=["ue5"])
    assert t is not None and t["job_kind"] == "verify" and t["task_id"] == tid


def test_plain_verify_job_still_open_to_all():
    idx = _idx()
    _make_submitted(idx)
    t = claim_task(idx, "master-worker", verify_capable=True)
    assert t is not None and t["job_kind"] == "verify"


# ── 관측 ──────────────────────────────────────────────────────

def test_worker_capabilities_are_recorded():
    """"왜 아무도 이 잡을 안 집나" 진단의 첫 단서."""
    idx = _idx()
    claim_task(idx, "win-pc-1", capabilities=["UE5"])
    assert idx.worker_capabilities["win-pc-1"] == ["ue5"]


# ── 단위 ──────────────────────────────────────────────────────

def test_subset_helper():
    assert _worker_meets_requires({}, set())
    assert _worker_meets_requires({"requires": []}, set())
    assert not _worker_meets_requires({"requires": ["ue5"]}, set())
    assert _worker_meets_requires({"requires": ["ue5"]}, {"ue5", "windows"})


def test_normalize():
    assert normalize_capabilities(None) == []
    assert normalize_capabilities([" UE5", "ue5", "", "  "]) == ["ue5"]


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
