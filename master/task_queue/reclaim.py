import sys
import time
import threading
import subprocess
from datetime import datetime, timezone, timedelta
from .models import _VERIFY_BACKPRESSURE_SEC
from .persistence import TaskIndex, _tq_log, _git_commit_tasks
from .logic import _save_task

# Plan v5 C.3 — 검증자 0대 backlog 카나리의 liveness 윈도우. 워커가 poll/claim 마다
# verify_capable 신고하므로 이 시간 내 접촉이 없으면 verify-capable 워커가 없는 것으로 간주.
_VERIFY_CAPABLE_RECENT_SEC = 300

# ─────────────────────────────────────────
# Reclaim background thread
# ─────────────────────────────────────────

def _verify_loop(idx: TaskIndex, interval: int, stop_event: threading.Event):
    """주기적 자동 verify — submitted 가 있으면 master_orchestrator.exe --verify-all 호출.

    워커가 task 처리 후 submit → 즉시 또는 다음 interval 에 서버가 검증·머지 → deps 풀려
    다음 worker 가 종속 task claim 가능. 사용자 수동 개입 없이 흐름 자동화.

    가시성 (보수성 보강):
    - stuck alert: submitted 가 임계 시간 (_VERIFY_BACKPRESSURE_SEC) 넘으면 task 별 1회 [ALERT].
      master_orchestrator 가 무한 retry 만 하고 침묵하던 사각지대 차단 — 운영자 즉시 인지.
    - work progress: 작업 상태 변화 시마다 work 단위 한 줄 요약 (verified=N/M submitted=K ...).
      4-5대 동시 운영 시에도 큐 흐름이 보임. 변화 없으면 silent.
    """
    master_orch = idx.root / ".claude" / "mcp" / "master_orchestrator.exe"
    if not master_orch.exists():
        _tq_log(f"[verify-loop] master_orchestrator.exe 없음 ({master_orch}) — 자동 verify 비활성", idx.root)
        return
    _tq_log(f"[verify-loop] 시작 (interval={interval}s, master_orch={master_orch.name})", idx.root)
    in_flight = False
    alerted_stuck: set[str] = set()    # task_id 기준 — 임계 첫 도달 시 1회 alert, 해소 후 재정체 시 다시 alert
    verify_backlog_alerted = False     # Plan v5 C.3 — 검증자 0대 backlog 카나리 1회/조건
    last_progress_snapshot = ""        # work 진척 요약 — 변경 시에만 로그
    while not stop_event.wait(interval):
        if in_flight:
            continue  # 이전 verify 진행 중 — 다음 사이클 대기
        try:
            # Plan v5 C.3 — push 모드 submitted 는 검증 워커가 처리. 서버 verify-loop 는 pull
            # 모드 submitted 만 --verify-all 로 검증(공존). push 정체는 아래 backlog 카나리로 가시화.
            with idx.lock:
                pull_submitted = sum(1 for t in idx.tasks.values()
                                     if t.get("status") == "submitted"
                                     and t.get("distribution_mode") != "push")
            if pull_submitted > 0:
                _tq_log(f"[verify-loop] pull submitted={pull_submitted} 감지, --verify-all 호출", idx.root)
                in_flight = True
                t0 = time.time()
                r = subprocess.run(
                    [str(master_orch), "--verify-all", str(idx.root)],
                    capture_output=True, text=True,
                    encoding='utf-8', errors='replace',
                    stdin=subprocess.DEVNULL, timeout=600,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,
                )
                dur = time.time() - t0
                if r.returncode == 0:
                    _tq_log(f"[verify-loop] 완료 duration={dur:.1f}s", idx.root)
                else:
                    _tq_log(f"[verify-loop] master_orch rc={r.returncode} stderr={r.stderr[:200]}", idx.root)
                in_flight = False

            # 사이클 끝마다 — verify 진행 여부 무관하게 — stuck alert + work progress 점검
            with idx.lock:
                now = datetime.now(timezone.utc).astimezone()
                stuck_tasks: list[tuple[str, int]] = []
                for tid, t in idx.tasks.items():
                    if t.get("status") != "submitted":
                        continue
                    sub = t.get("submitted_at")
                    if not sub:
                        continue
                    try:
                        sub_dt = datetime.fromisoformat(sub)
                        elapsed = int((now - sub_dt).total_seconds())
                        if elapsed > _VERIFY_BACKPRESSURE_SEC:
                            stuck_tasks.append((tid, elapsed))
                    except Exception:
                        continue
                # 신규 stuck 만 alert — 같은 task 반복 알림 방지
                for tid, elapsed in stuck_tasks:
                    if tid not in alerted_stuck:
                        _tq_log(f"[ALERT] verify 정체 — task={tid} submitted {elapsed}s 경과 "
                                f"(임계 {_VERIFY_BACKPRESSURE_SEC}s). master/repo 상태 점검 필요. "
                                f"backpressure 로 같은 work 의 워커 idle 유지 중", idx.root)
                        alerted_stuck.add(tid)
                # 해소된 task 는 알림 set 에서 제거 (회복 후 재정체 시 다시 알림 가능)
                still_stuck_ids = {tid for tid, _ in stuck_tasks}
                alerted_stuck &= still_stuck_ids

                # Plan v5 C.3 — 검증자 0대 backlog 카나리 (liveness, safety 와 별개 트랙).
                # push submitted 가 쌓이는데 최근 verify-capable 워커 접촉이 없으면 → 검증 영영
                # 정체(주말 무인 silent failure). 작성워커 verify fallback 은 모토 위반이라 금지 —
                # 큐 상태 가시화만 (analytics/supervisor 아님, 기존 사실의 로그 1줄).
                push_submitted = sum(1 for t in idx.tasks.values()
                                     if t.get("status") == "submitted"
                                     and t.get("distribution_mode") == "push")
                recent_verifier = False
                for seen in idx.verify_capable_seen.values():
                    try:
                        if (now - datetime.fromisoformat(seen)).total_seconds() <= _VERIFY_CAPABLE_RECENT_SEC:
                            recent_verifier = True
                            break
                    except Exception:
                        continue
                if push_submitted > 0 and not recent_verifier:
                    if not verify_backlog_alerted:
                        _tq_log(f"[ALERT] 검증자 0대 — push submitted {push_submitted}건이 검증 대기 중인데 "
                                f"최근 {_VERIFY_CAPABLE_RECENT_SEC}s 내 verify-capable 워커 접촉 없음. "
                                f"상용 모델 워커(verifier_model 설정) 기동·quota 확인 필요. "
                                f"(작성워커 verify fallback 안 함 — 모토)", idx.root)
                        verify_backlog_alerted = True
                else:
                    verify_backlog_alerted = False

                # work 단위 progress 요약 — 변경 시에만 출력
                progress: dict[str, dict[str, int]] = {}
                for t in idx.tasks.values():
                    wid = t.get("work_id") or ""
                    if not wid:
                        continue
                    p = progress.setdefault(wid, {"verified": 0, "submitted": 0,
                                                   "claimed": 0, "pending": 0,
                                                   "needs_revision": 0, "failed": 0,
                                                   "stuck": 0, "total": 0})
                    st = t.get("status", "pending")
                    p["total"] += 1
                    if st in p:
                        p[st] += 1
                # 활성 work 만 (모두 verified/failed/cancelled 인 work 는 잠잠)
                active_lines = []
                for wid, p in sorted(progress.items()):
                    terminal = p["verified"] + p["failed"]
                    if terminal >= p["total"]:
                        continue
                    active_lines.append(
                        f"work={wid} verified={p['verified']}/{p['total']} "
                        f"submitted={p['submitted']} claimed={p['claimed']} "
                        f"pending={p['pending']} revision={p['needs_revision']} "
                        f"stuck={p['stuck']} failed={p['failed']}"
                    )
                snapshot = "|".join(active_lines)
                if snapshot != last_progress_snapshot:
                    for line in active_lines:
                        _tq_log(f"[progress] {line}", idx.root)
                    last_progress_snapshot = snapshot
        except subprocess.TimeoutExpired:
            _tq_log(f"[verify-loop] timeout 600s (verify 가 너무 느림)", idx.root)
            in_flight = False
        except Exception as e:
            _tq_log(f"[verify-loop] 예외: {e}", idx.root)
            in_flight = False


def _reclaim_loop(idx: TaskIndex, lease_seconds: int, interval: int, stop_event: threading.Event):
    while not stop_event.wait(interval):
        try:
            cutoff = datetime.now(timezone.utc).astimezone() - timedelta(seconds=lease_seconds)
            with idx.lock:
                to_reclaim = []
                verify_to_reclaim = []
                for tid, t in idx.tasks.items():
                    # Plan v5 C.3 — verify lease 회수: submitted + verifier_id 인데 verify_heartbeat
                    # 가 stale 이면 검증 워커 죽음 → verifier_id 클리어해 다른 검증 워커가 재claim.
                    # verifier_epoch 는 단조 유지(이전 검증자 zombie verdict fencing). status 는
                    # submitted 유지(write 경로 아님).
                    if t.get("status") == "submitted" and t.get("verifier_id"):
                        vhb = t.get("verify_heartbeat") or t.get("verify_claimed_at")
                        if vhb:
                            try:
                                if datetime.fromisoformat(vhb) < cutoff:
                                    verify_to_reclaim.append(tid)
                            except ValueError:
                                # [중요] 타임스탬프가 깨졌다 — 이번 회차에 회수하지 않는다(다음에 재시도).
                                # [주의] **영구히 깨져 있으면 그 task 는 영원히 회수되지 않는다.** 우리가
                                # ISO 로만 쓰므로 확률은 낮지만, 넓은 `except Exception` 이었을 때는
                                # 그 사실이 보이지도 않았다(σ.2 감사 2026-08-14). 좁혀서 의도를 구조로 만든다.
                                pass
                        continue
                    if t.get("status") != "claimed":
                        continue
                    hb = t.get("last_heartbeat")
                    if not hb:
                        continue
                    try:
                        if datetime.fromisoformat(hb) < cutoff:
                            to_reclaim.append(tid)
                    except ValueError:
                        continue          # 위와 같다 — 깨진 타임스탬프는 이번 회차만 건너뛴다

                for tid in verify_to_reclaim:
                    t = idx.tasks.get(tid)
                    if not t or t.get("status") != "submitted" or not t.get("verifier_id"):
                        continue
                    prev = t.get("verifier_id")
                    t["verifier_id"] = None
                    t["verify_claimed_at"] = None
                    t["verify_heartbeat"] = None
                    _save_task(idx, tid)
                    _tq_log(f"[reclaim-verify] {tid} prev_verifier={prev} lease 만료 → verify 재배정 대기 "
                            f"(verify_epoch={t.get('verifier_epoch')} 유지)", idx.root)
                    _git_commit_tasks(idx.root, f"[reclaim-verify] {tid}: verify lease timeout",
                                      [idx.task_paths[tid]])
                for tid in to_reclaim:
                    t = idx.tasks.get(tid)
                    if not t or t.get("status") != "claimed":
                        continue
                    prev = t.get("worker_id")
                    t["reclaim_count"] = int(t.get("reclaim_count", 0)) + 1
                    if t["reclaim_count"] > 3:
                        t["status"] = "stuck"
                    else:
                        t["status"] = "pending"
                        t["worker_id"] = None
                        t["last_heartbeat"] = None
                    _save_task(idx, tid)
                    _tq_log(f"[reclaim] {tid} prev_worker={prev} count={t['reclaim_count']} → {t['status']}", idx.root)
                    _git_commit_tasks(idx.root, f"[reclaim] {tid}: timeout", [idx.task_paths[tid]])
        except Exception as e:
            _tq_log(f"[reclaim-loop] error: {e}", idx.root)
