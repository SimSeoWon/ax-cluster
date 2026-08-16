"""`task_data` 가 등재 → claim 응답 → **재기동** 을 넘어 살아남는지 — 원전 능력 이식 (`#141`).

🔴 **왜 이 파일이 생겼나.** 원전은 이 자리에 주석을 박아 뒀다 —
*"task_data 는 free-form dict → 확실히 저장·**claim 응답에 전달**(top-level 은 모델이 drop)"*
(`mcp/master_orchestrator/cluster_selftest.py:223`). 워커가 `force_backend` 를 읽는 경로가 그것이다.
실측 2026-08-16: **우리 큐는 claim 응답에 `task_data` 를 아예 싣지 않았다.** MD 본문의 json
블록에만 쓰고 메모리에는 들지 않아, 워커가 볼 방법이 없었다 — 셀프테스트의 라운드트립 단정이
잡았다(유닛 55개는 전부 통과한 채였다: **주입은 계약을 재고 실물을 재지 않는다**).

⚠️ **재기동 복원을 반드시 잰다.** 등재 직후만 재면 「메모리에만 있고 재기동하면 사라지는」
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
from master.task_queue.persistence import TaskIndex, parse_task_data  # noqa: E402


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
    """🔴 이것이 없으면 `force_backend` 이식은 죽은 이식이다."""
    idx, _root, wid = _idx()
    register_task(idx, work_id=wid, type="write", stem="p0",
                  task_data={"stem": "p0", "force_backend": "local_llm"})
    job = claim_task(idx, worker_id="w1")
    assert job is not None, "claim 이 아무것도 안 줬다"
    assert "task_data" in job, f"claim 응답에 task_data 가 없다: {sorted(job)}"
    assert job["task_data"].get("force_backend") == "local_llm", job["task_data"]


def test_claim_without_task_data_is_empty_dict():
    """⚠️ `None` 이 아니라 빈 dict — 워커가 `.get()` 을 바로 부를 수 있어야 한다."""
    idx, _root, wid = _idx()
    register_task(idx, work_id=wid, type="write", stem="p0", task_data={})
    job = claim_task(idx, worker_id="w1")
    assert job is not None
    assert job.get("task_data") == {}, job.get("task_data")


# ── 🔴 재기동 복원 ────────────────────────────────────────────

def test_survives_restart():
    """🔴 큐를 내렸다 올려도 워커가 같은 값을 받아야 한다 (본문에서 되읽는다)."""
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
    """⚠️ claim 이 MD 를 다시 쓴다 — 그때 본문의 json 블록을 지우면 재기동 후 사라진다."""
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
