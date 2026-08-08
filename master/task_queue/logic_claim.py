"""task_queue logic 분리 (2026-07-18) — claim/lease/directive/quota 클러스터 (facade = logic.py).
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from .models import (
    _VALID_DIRECTIVES, _VERIFY_BACKPRESSURE_SEC, normalize_capabilities
)
from .persistence import (
    TaskIndex, _tq_log, _now_iso, _git_commit_tasks
)
from .logic_persist import _save_task


def _stalled_submitted_in_work(idx: TaskIndex, work_id: str) -> Optional[str]:
    """work 내에 submitted 상태로 _VERIFY_BACKPRESSURE_SEC 초 이상 머물러 있는 task 가
    있으면 그 task_id 반환. 없으면 None.

    backpressure 의도 — 단일 워커도 통제 안 되는 verify 정체 상황에서 신규 claim 까지
    뽑아가면 같은 work 의 task 가 줄줄이 submitted 으로만 쌓이고 사용자가 silent
    누적을 알아차리는 시점이 늦어짐. claim 거부로 워커가 idle 하면 운영자가 즉시
    인지 → master_orchestrator 측 verify 문제(머지 충돌 / repo 상태 등) 를 빨리 잡을 수 있음.
    verify 가 자연 회복 또는 사용자 fix 로 풀리면 워커가 다음 poll 사이클에서 자동 재개."""
    now = datetime.now(timezone.utc).astimezone()
    for tid, t in idx.tasks.items():
        if t.get("work_id") != work_id:
            continue
        if t.get("status") != "submitted":
            continue
        # Plan v5 C.3 — push 모드 submitted 는 검증 워커가 처리(서버 verify-loop 아님). 상용 모델
        # 검증은 180s 초과가 정상이라 backpressure 로 같은 work 의 write claim 을 막으면 안 됨.
        # push 정체 가시성은 reclaim 의 verify lease 회수 + backlog 카나리가 담당.
        if t.get("distribution_mode") == "push":
            continue
        sub = t.get("submitted_at")
        if not sub:
            continue
        try:
            sub_dt = datetime.fromisoformat(sub)
            if (now - sub_dt).total_seconds() > _VERIFY_BACKPRESSURE_SEC:
                return tid
        except Exception:
            continue
    return None


# Plan v5 C.3 — 검증 워커 lease 만료 윈도우 (write lease 와 동일 기본값). reclaim 이 stale
# verify lease 를 회수하지만, claim 후보 필터에서도 active 검증자 점유 task 는 제외해 reclaim
# 사이클 사이의 이중 배정을 막는다.
_VERIFY_LEASE_SEC = 1200


def _is_verify_lease_active(t: dict) -> bool:
    """submitted task 에 현재 살아있는 검증 워커 lease 가 걸려있으면 True.
    verifier_id 가 있고 verify_heartbeat 가 _VERIFY_LEASE_SEC 내면 active."""
    if not t.get("verifier_id"):
        return False
    hb = t.get("verify_heartbeat") or t.get("verify_claimed_at")
    if not hb:
        return False
    try:
        hb_dt = datetime.fromisoformat(hb)
        return (datetime.now(timezone.utc).astimezone() - hb_dt).total_seconds() <= _VERIFY_LEASE_SEC
    except Exception:
        return False


def _worker_meets_requires(t: dict, caps: set) -> bool:
    """PLAN §5.2-C — task 의 `requires` 를 워커의 `capabilities` 가 전부 덮는가.

    **fail-closed**: 워커가 신고하지 않은 능력은 없는 것으로 본다. 능력을 아예 안 신고한
    구 워커(빈 집합)는 `requires` 가 빈 task 만 집는다 — 즉 오늘 동작 그대로다.
    마스터 워커가 `requires: ue5` 잡을 집어가는 것을 막는 것이 이 함수의 존재 이유다.
    """
    need = t.get("requires") or []
    return set(need) <= caps


def _claim_verify_job(idx: TaskIndex, worker_id: str, caps: Optional[set] = None) -> Optional[dict]:
    """Plan v5 C.3 — 검증 워커가 집을 verify job 선택 (lock 보유 가정).

    후보 = submitted && distribution_mode==push && active 검증 lease 없음. **write job 보다
    나중**(사용자 2026-07-05 — 작업 우선순위 1, 검증 우선순위 2: 워커가 작성을 먼저 소진하고
    없을 때 검증). **작성자≠검증자 무조건 제외 완화**(옛 2026-06-15 하드 제외 supersede) —
    다른 워커의 attempt 를 **우선**하되, 없으면(워커 1대 등) **자기 것도 검증**. 작성=무료 로컬
    LLM·검증=상용 모델(`verifier_model`)이라 같은 워커가 자기 것을 검증해도 모델 수준 독립
    검증이 유지된다(모토 불변). 선택 시 verifier lease 부여 + verifier_epoch 단조 증가(fencing).

    PLAN §5.2-C — **verify 도 `requires` 로 거른다.** 검증 워커는 판정을 내리려면 그 task 의
    브랜치·diff 를 손에 쥐어야 하고, 그건 파일을 소유한 작업장뿐이다(§2.1 — 파일은 윈도우를
    떠나지 않는다). 걸러내지 않으면 마스터가 UE5 task 의 verify lease 를 점유한 채 아무것도
    못 하고 lease 만 태운다. 걸러서 검증자가 없으면 backlog 카나리가 **시끄럽게** 알린다 —
    조용한 오배정보다 낫다.
    """
    caps = caps or set()
    cands = []
    for t in idx.tasks.values():
        if t.get("status") != "submitted":
            continue
        if t.get("distribution_mode") != "push":
            continue  # pull 모드 submitted 는 서버 verify-loop 가 처리(공존)
        if _is_verify_lease_active(t):
            continue  # 다른 검증 워커가 이미 점유
        if not _worker_meets_requires(t, caps):
            continue  # 능력 미달 — 이 워커는 이 task 의 파일을 못 만진다
        cands.append(t)
    if not cands:
        return None
    # 다른 워커 attempt 우선(N-워커 교차검증 유지) → 없으면 자기 것도(1대 fallback).
    others = [t for t in cands if t.get("worker_id") != worker_id]
    pool = others if others else cands
    pool.sort(key=lambda t: (
        int(t.get("hierarchy_level", 0)),
        -int(t.get("priority", 0)),
        t.get("submitted_at", ""),
    ))
    chosen = pool[0]
    chosen["verifier_id"] = worker_id
    chosen["verifier_epoch"] = int(chosen.get("verifier_epoch", 0)) + 1
    chosen["verify_claimed_at"] = _now_iso()
    chosen["verify_heartbeat"] = _now_iso()
    _save_task(idx, chosen["task_id"])
    _tq_log(f"[claim-verify] {chosen['task_id']} → {worker_id} "
            f"(author={chosen.get('worker_id')}, verify_epoch={chosen['verifier_epoch']})", idx.root)
    _git_commit_tasks(idx.root, f"[claim-verify] {chosen['task_id']} → {worker_id}",
                      [idx.task_paths[chosen["task_id"]]])
    out = dict(chosen)
    out["job_kind"] = "verify"
    return out


def claim_task(idx: TaskIndex, worker_id: str, verify_capable: bool = False,
               capabilities: Optional[list] = None) -> Optional[dict]:
    caps = set(normalize_capabilities(capabilities))
    with idx.lock:
        # Plan v5 C.3 — verify-capable 워커 접촉 기록 (backlog 카나리 liveness 입력).
        if verify_capable:
            idx.verify_capable_seen[worker_id] = _now_iso()
        idx.worker_last_seen[worker_id] = _now_iso()
        # PLAN §5.2-C — 최근 신고 능력 기록 (관측용. /admin/workers 가 노출).
        idx.worker_capabilities[worker_id] = sorted(caps)
        # Plan v5 C.3 — **write(코드 생성) 우선순위 1, verify 우선순위 2** (사용자 2026-07-05,
        # 옛 verify-우선 supersede). 워커는 작성 태스크를 먼저 소진하고, 더 없으면 검증을 집는다
        # ("일단 모두 작업 처리 → 그다음 모두 검증"). 워커 1대여도 작성 소진 후 자기 것 검증 가능
        # (_claim_verify_job 이 author 무조건 제외 완화 — 다른 워커 우선·없으면 self).
        # failed 도 dependents 차단 X — 영원 block 방지 (worker 가 이미 못 한 task 의 종속자도 시도 가능)
        completed = {tid for tid, t in idx.tasks.items()
                     if t.get("status") in ("verified", "cancelled", "failed")}
        # pending + needs_revision (re-attempt) 둘 다 후보
        candidates = [t for t in idx.tasks.values() if t.get("status") in ("pending", "needs_revision")]
        candidates.sort(key=lambda t: (
            int(t.get("hierarchy_level", 0)),
            -int(t.get("priority", 0)),
            t.get("created", ""),
        ))
        chosen = None
        skipped_quota_block = 0
        skipped_capability = 0
        for t in candidates:
            deps = t.get("depends_on") or []
            if not all(d in completed for d in deps):
                continue
            # PLAN §5.2-C — 능력 미달이면 이 워커의 후보가 아니다(다른 워커용으로 남겨둔다).
            # quota 차단과 달리 시간이 지나도 풀리지 않는다 — 능력은 기계의 속성이다.
            if not _worker_meets_requires(t, caps):
                skipped_capability += 1
                continue
            # Phase 3 lite — anti-affinity: 이 워커가 quota 신고한 task 는 5h 동안 skip
            if _is_worker_quota_blocked(t, worker_id):
                skipped_quota_block += 1
                continue
            chosen = t
            break
        if chosen is None:
            # write 없음 → verify 우선순위 2 (verify_capable 워커만; 빈 verifier_model = write 전용)
            if verify_capable:
                vjob = _claim_verify_job(idx, worker_id, caps)
                if vjob is not None:
                    return vjob
            if skipped_capability > 0:
                _tq_log(f"[claim] {worker_id} 능력 미달로 {skipped_capability}건 skip "
                        f"(보유={','.join(sorted(caps)) or '-'}) — 능력 보유 워커 대기", idx.root)
            if skipped_quota_block > 0:
                _tq_log(f"[claim] {worker_id} quota-blocked task {skipped_quota_block}건 skip — 다른 워커 대기", idx.root)
            return None
        # verify backpressure — 같은 work 의 verify 가 정체돼 있으면 claim 거부
        # (silent submitted 누적 차단). work 단위라 다른 work 는 영향 받지 않음.
        stalled = _stalled_submitted_in_work(idx, chosen.get("work_id", ""))
        if stalled:
            _tq_log(f"[claim] 거부 (verify 정체) — work={chosen.get('work_id')} "
                    f"stalled_task={stalled} ≥ {_VERIFY_BACKPRESSURE_SEC}s submitted, "
                    f"worker={worker_id} idle 유지 (verify 회복까지 대기)", idx.root)
            return None
        chosen["status"] = "claimed"
        chosen["worker_id"] = worker_id
        chosen["claimed_at"] = _now_iso()
        chosen["last_heartbeat"] = _now_iso()
        chosen["attempt_count"] = int(chosen.get("attempt_count", 0)) + 1
        # Plan v5 C.2 — fencing: 매 (재)배정마다 epoch 단조 증가 + 현재 assignee 기록.
        # reclaim 후 새 워커 claim 시 epoch 가 올라가, 이전 워커(zombie)의 submit 은 stale.
        chosen["epoch"] = int(chosen.get("epoch", 0)) + 1
        chosen["assignee"] = worker_id
        idx.worker_last_seen[worker_id] = _now_iso()
        _save_task(idx, chosen["task_id"])
        _tq_log(f"[claim] {chosen['task_id']} → {worker_id} (attempt={chosen['attempt_count']}, epoch={chosen['epoch']})", idx.root)
        _git_commit_tasks(idx.root, f"[claim] {chosen['task_id']} → {worker_id}",
                          [idx.task_paths[chosen["task_id"]]])
        out = dict(chosen)
        out["job_kind"] = "write"   # Plan v5 C.3 — 워커가 write/verify 분기
        return out


def _take_worker_directives(idx: TaskIndex, worker_id: str) -> list[str]:
    """워커 directive 큐 drain (lock 보유 가정). fire-once 의미."""
    queue = idx.worker_directives.get(worker_id) or []
    if queue:
        idx.worker_directives[worker_id] = []
    return list(queue)


def push_worker_directive(idx: TaskIndex, worker_id: str, directive: str) -> dict:
    """관리자 → 워커 directive 큐에 추가. 대상 워커가 미존재여도 큐만 만들어둠
    (워커가 다음 heartbeat/poll 에 자연스럽게 take)."""
    if directive not in _VALID_DIRECTIVES:
        return {"ok": False, "error": f"invalid directive: {directive} (allowed: {','.join(_VALID_DIRECTIVES)})"}
    if not worker_id:
        return {"ok": False, "error": "worker_id required"}
    with idx.lock:
        q = idx.worker_directives.setdefault(worker_id, [])
        q.append(directive)
        _tq_log(f"[directive] push {worker_id} ← {directive} (queue={q})", idx.root)
        return {"ok": True, "worker_id": worker_id, "directive": directive, "queue_len": len(q)}


def heartbeat(idx: TaskIndex, task_id: str, worker_id: str) -> dict:
    with idx.lock:
        t = idx.tasks.get(task_id)
        if not t:
            return {"ok": False, "code": 404, "error": "task not found"}
        # write lease (claimed) 또는 Plan v5 C.3 verify lease (submitted + verifier_id) 둘 다 수용.
        is_write_lease = (t.get("worker_id") == worker_id and t.get("status") == "claimed")
        is_verify_lease = (t.get("verifier_id") == worker_id and t.get("status") == "submitted")
        if not (is_write_lease or is_verify_lease):
            return {"ok": False, "code": 410, "error": "lease lost"}
        if is_verify_lease:
            t["verify_heartbeat"] = _now_iso()
        else:
            t["last_heartbeat"] = _now_iso()
        idx.worker_last_seen[worker_id] = _now_iso()
        # heartbeat 는 git commit 안 함 (잦음). 메모리 + 파일만
        _save_task(idx, task_id)
        directives = _take_worker_directives(idx, worker_id)
        if directives:
            _tq_log(f"[directive] take {worker_id} → {directives} (via heartbeat task={task_id})", idx.root)
        return {"ok": True, "directives": directives}


def poll_worker(idx: TaskIndex, worker_id: str) -> dict:
    """idle 워커가 directive 만 가져갈 때 사용. claim 시도 직전 호출."""
    if not worker_id:
        return {"ok": False, "error": "worker_id required"}
    with idx.lock:
        idx.worker_last_seen[worker_id] = _now_iso()
        directives = _take_worker_directives(idx, worker_id)
        if directives:
            _tq_log(f"[directive] take {worker_id} → {directives} (via poll)", idx.root)
        return {"ok": True, "directives": directives}


# ─────────────────────────────────────────
# Phase 3 lite — quota_exhausted handling + anti-affinity
# ─────────────────────────────────────────

# 워커가 quota 신고한 task 를 같은 워커가 다시 잡지 않도록 차단하는 시간 (초)
_QUOTA_BLOCK_WINDOW_SEC = 5 * 3600


def _is_worker_quota_blocked(t: dict, worker_id: str) -> bool:
    """task 가 이 worker_id 에 의해 quota_exhausted 로 신고된 후 5h 안이면 True.
    quota_blocked_workers: {worker_id: until_iso}"""
    blocks = t.get("quota_blocked_workers") or {}
    until_iso = blocks.get(worker_id)
    if not until_iso:
        return False
    try:
        until_dt = datetime.fromisoformat(until_iso)
        return datetime.now(timezone.utc).astimezone() < until_dt
    except Exception:
        return False


def _mark_worker_quota_blocked(t: dict, worker_id: str):
    """task 의 quota_blocked_workers 에 worker_id 등록 (만료 시각 = 지금 + 5h)."""
    blocks = t.get("quota_blocked_workers") or {}
    until = datetime.now(timezone.utc).astimezone() + timedelta(seconds=_QUOTA_BLOCK_WINDOW_SEC)
    blocks[worker_id] = until.isoformat(timespec='seconds')
    t["quota_blocked_workers"] = blocks
