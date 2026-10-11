"""`#392` ② — 진행 중 work 의 지휘자 스탬프를 큐 PATCH 로 바꾼다 (큐 쪽 계약).

[DOC] 대상: `task_queue/logic_persist.update_work_meta(worker_mode=)` · `models.WorkPatchReq.worker_mode` ·
      `server.patch_work_ep` 의 전달과 거절 모양. 임시 `TaskIndex` 만 쓴다(실 큐·HTTP 없음).
      출력 형식은 저장소 관례 `통과 N · 실패 M` + rc(실패 있으면 1).
"""
import sys
import tempfile
import inspect
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.task_queue.persistence import TaskIndex                    # noqa: E402
from master.task_queue.logic import register_work                      # noqa: E402
from master.task_queue.logic_persist import update_work_meta           # noqa: E402
from master.task_queue.models import WorkPatchReq                      # noqa: E402
from master.task_queue.server import _run_http_server                  # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {name}")
    else:
        FAIL += 1
        print(f"  [중요] 실패: {name}" + (f" — {got}" if got else ""))


def _idx():
    return TaskIndex(Path(tempfile.mkdtemp(prefix="ax-wmode-patch-")))


print("[1] 진행 중 work 의 지휘자 스탬프 변경")
idx = _idx()
registered = register_work(idx, title="mode patch", target_repo="R", worker_mode="codex")
wid = registered["work_id"]
r = update_work_meta(idx, wid, worker_mode="claude")
check("변경 요청 성공", r.get("ok"), str(r))
check("레코드가 claude", idx.works[wid].get("worker_mode") == "claude",
      str(idx.works[wid].get("worker_mode")))
check("이전·새 모드가 changed 에 남는다",
      "worker_mode=codex→claude" in r.get("changed", ()), str(r.get("changed")))

same = update_work_meta(idx, wid, worker_mode="claude")
check("같은 값 재요청은 멱등", same.get("ok") and same.get("changed") == [], str(same))

print("[2] 잘못된 모드는 저장하지 않는다")
for invalid in ("typo", "  "):
    before = dict(idx.works[wid])
    rejected = update_work_meta(idx, wid, worker_mode=invalid)
    check(f"잘못된 모드 {invalid!r} 거절",
          not rejected.get("ok") and rejected.get("reason") == "invalid_worker_mode",
          str(rejected))
    check(f"잘못된 모드 {invalid!r} 에 레코드 불변", idx.works[wid] == before,
          str(idx.works[wid]))

print("[3] 종결 work 는 다른 필드까지 원자적으로 거절")
for terminal in ("merged", "rejected", "cancelled"):
    terminal_idx = _idx()
    terminal_work = register_work(
        terminal_idx, title=f"terminal {terminal}", target_repo="R", worker_mode="codex")
    terminal_id = terminal_work["work_id"]
    terminal_idx.works[terminal_id]["merge_status"] = terminal
    before = dict(terminal_idx.works[terminal_id])
    rejected = update_work_meta(
        terminal_idx, terminal_id, worker_mode="lane", dispatch_note="should-not-save")
    check(f"{terminal} work 모드 변경 거절",
          not rejected.get("ok") and rejected.get("reason") == "terminal_work",
          str(rejected))
    check(f"{terminal} work 전체 레코드 불변", terminal_idx.works[terminal_id] == before,
          str(terminal_idx.works[terminal_id]))

print("[4] worker_mode 생략과 요청 모델")
before_mode = idx.works[wid].get("worker_mode")
patched = update_work_meta(idx, wid, dispatch_note="still-running")
check("생략하면 기존 모드 유지", patched.get("ok") and
      idx.works[wid].get("worker_mode") == before_mode, str(patched))
check("다른 필드는 종전대로 patch", idx.works[wid].get("dispatch_note") == "still-running",
      str(idx.works[wid]))
check("WorkPatchReq 가 모드를 보존", WorkPatchReq(worker_mode="lane").worker_mode == "lane")
check("WorkPatchReq 생략값은 None", WorkPatchReq().worker_mode is None,
      repr(WorkPatchReq().worker_mode))

print("[5] 서버 라우트 전달·거절 계약")
server_source = inspect.getsource(_run_http_server)
check("서버가 worker_mode 를 코어에 전달",
      "worker_mode=req.worker_mode" in server_source)
check("reason 있는 코어 거절은 그대로 반환",
      'if not r.get("ok") and r.get("reason")' in server_source and
      "return r" in server_source)

print()
print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
