"""`task_data` 가 등재 → claim 응답 → **재기동** 을 넘어 살아남는지 — 원전 능력 이식 (`#141`).

[중요] **왜 이 파일이 생겼나.** 원전은 이 자리에 주석을 박아 뒀다 —
*"task_data 는 free-form dict → 확실히 저장·**claim 응답에 전달**(top-level 은 모델이 drop)"*
(`mcp/master_orchestrator/cluster_selftest.py:223`). 워커가 `force_backend` 를 읽는 경로가 그것이다.
실측 2026-08-16: **우리 큐는 claim 응답에 `task_data` 를 아예 싣지 않았다.** MD 본문의 json
블록에만 쓰고 메모리에는 들지 않아, 워커가 볼 방법이 없었다 — 셀프테스트의 라운드트립 단정이
잡았다(유닛 55개는 전부 통과한 채였다: **주입은 계약을 재고 실물을 재지 않는다**).

[주의] **재기동 복원을 반드시 잰다.** 등재 직후만 재면 「메모리에만 있고 재기동하면 사라지는」
상태를 통과시킨다 — 그러면 큐를 한 번 내렸다 올린 순간 워커가 조용히 다른 백엔드를 쓴다.

실행: .venv/bin/python master/test_task_data.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue.logic import (  # noqa: E402
    register_work, register_task, claim_task,
)
from master.task_queue.persistence import (  # noqa: E402
    TaskIndex, parse_task_data, parse_fail_reason,
)


# ── 하네스 ────────────────────────────────────────────────────

def _idx() -> tuple:
    root = Path(tempfile.mkdtemp(prefix="ax-taskdata-"))
    idx = TaskIndex(root)
    r = register_work(idx, title="t", target_repo="/tmp/repo")
    assert r.get("ok"), r
    return idx, root, r["work_id"]


# ── 본문 파서 ─────────────────────────────────────────────────

def test_parse_task_data_roundtrip():
    body = ('\n## task_data\n```json\n'
            '{\n  "stem": "probe_0",\n  "classes": ["A", "B"],\n'
            '  "force_backend": "local_llm"\n}\n```\n')
    got = parse_task_data(body)
    assert got.get("force_backend") == "local_llm", got
    assert got.get("classes") == ["A", "B"], got


def test_parse_task_data_absent_and_broken():
    assert parse_task_data("") == {}
    assert parse_task_data("본문만 있고 블록은 없다") == {}
    assert parse_task_data("## task_data\n```json\n{깨진\n```\n") == {}
    # dict 아닌 최상위 값은 받지 않는다 — 워커가 `.get()` 하다 죽는다
    assert parse_task_data('## task_data\n```json\n[1, 2]\n```\n') == {}
    assert parse_task_data('## task_data\n```json\n') == {}


# ── 등재 → claim ──────────────────────────────────────────────

def test_claim_carries_task_data():
    """[중요] 이것이 없으면 `force_backend` 이식은 죽은 이식이다."""
    idx, _root, wid = _idx()
    register_task(idx, work_id=wid, type="write", stem="p0",
                  task_data={"stem": "p0", "force_backend": "local_llm"})
    job = claim_task(idx, worker_id="w1")
    assert job is not None, "claim 이 아무것도 안 줬다"
    assert "task_data" in job, f"claim 응답에 task_data 가 없다: {sorted(job)}"
    assert job["task_data"].get("force_backend") == "local_llm", job["task_data"]


def test_claim_without_task_data_is_empty_dict():
    """[주의] `None` 이 아니라 빈 dict — 워커가 `.get()` 을 바로 부를 수 있어야 한다."""
    idx, _root, wid = _idx()
    register_task(idx, work_id=wid, type="write", stem="p0", task_data={})
    job = claim_task(idx, worker_id="w1")
    assert job is not None
    assert job.get("task_data") == {}, job.get("task_data")


# ── [중요] 재기동 복원 ────────────────────────────────────────────

def test_survives_restart():
    """[중요] 큐를 내렸다 올려도 워커가 같은 값을 받아야 한다 (본문에서 되읽는다)."""
    idx, root, wid = _idx()
    register_task(idx, work_id=wid, type="write", stem="p0",
                  task_data={"stem": "p0", "force_backend": "agy",
                             "constraints": {"no_business_logic": False}})
    fresh = TaskIndex(root)          # ← 재기동 상당
    fresh.rebuild()
    job = claim_task(fresh, worker_id="w1")
    assert job is not None, "재기동 후 claim 이 아무것도 안 줬다"
    assert job["task_data"].get("force_backend") == "agy", job.get("task_data")
    # 중첩 dict 도 살아남는다 — 우리 제한적 YAML 파서로는 못 하는 일이라 본문에 두는 이유다
    assert job["task_data"].get("constraints") == {"no_business_logic": False}, job["task_data"]


def test_claim_does_not_erase_body():
    """[주의] claim 이 MD 를 다시 쓴다 — 그때 본문의 json 블록을 지우면 재기동 후 사라진다."""
    idx, root, wid = _idx()
    r = register_task(idx, work_id=wid, type="write", stem="p0",
                      task_data={"force_backend": "local_llm"})
    tid = r["task_id"]
    claim_task(idx, worker_id="w1")                      # ← 여기서 _save_task 가 돈다
    text = idx.task_paths[tid].read_text(encoding="utf-8")
    assert "## task_data" in text, "claim 이 본문을 지웠다"
    assert parse_task_data(text).get("force_backend") == "local_llm"
    fresh = TaskIndex(root)
    fresh.rebuild()
    assert fresh.task_data.get(tid, {}).get("force_backend") == "local_llm", fresh.task_data


# ── 실패 근거 (#222) — 「왜 그 상태인가」가 API·화면까지 닿아야 한다 ──

def test_parse_fail_reason_from_body():
    body = ("\n## verify\nresult: pass\n"
            "\n## fail\nreason: build-setup\ndetail: UE5 Build.bat 을 찾지 못했다\n"
            "at: 2026-08-19T10:00:00+09:00\n")
    got = parse_fail_reason(body)
    assert got["fail_reason"] == "build-setup"
    assert "찾지 못했다" in got["fail_detail"]
    assert got["failed_at"].startswith("2026-08-19")
    assert parse_fail_reason("") == {} and parse_fail_reason("실패 없음") == {}


def test_parse_fail_reason_takes_the_last_failure():
    """같은 태스크가 두 번 실패했으면 **마지막**이 현재 상태다."""
    body = ("\n## fail\nreason: 첫번째\ndetail: a\n"
            "\n## fail\nreason: 두번째\ndetail: b\n")
    assert parse_fail_reason(body)["fail_reason"] == "두번째"


def test_submit_fail_records_reason_in_record_and_survives_restart():
    from master.task_queue.logic_lifecycle import submit_fail
    idx, root, wid = _idx()
    register_task(idx, work_id=wid, type="build", task_data={}, stem="b")
    t = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    tid = t["task_id"]
    assert submit_fail(idx, tid, "build-setup", "엔진을 못 찾았다").get("ok")
    rec = idx.tasks[tid]
    assert rec["status"] == "failed"
    assert rec["fail_reason"] == "build-setup" and "못 찾았다" in rec["fail_detail"]
    # 재기동 — 근거가 본문에서 되읽혀야 한다 (2026-08-19 이전 실패도 이 경로로 살아난다)
    again = TaskIndex(root)
    again.rebuild()
    assert again.tasks[tid]["fail_reason"] == "build-setup"
    assert "못 찾았다" in again.tasks[tid]["fail_detail"]


def test_verify_reject_records_verdict():
    from master.task_queue.logic_lifecycle import verify_task
    idx, root, wid = _idx()
    register_task(idx, work_id=wid, type="build", task_data={}, stem="b")
    t = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    tid = t["task_id"]
    from master.task_queue.logic_lifecycle import submit_result
    assert submit_result(idx, tid, branch="", head_commit="abc",
                         self_check={"build": {"ok": True}}).get("ok")
    assert verify_task(idx, tid, result="reject", feedback="환각 2건").get("ok")
    rec = idx.tasks[tid]
    assert rec["status"] == "failed" and rec["verdict"] == "reject"
    assert rec["fail_reason"] == "verify:reject" and "환각" in rec["fail_detail"]


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
