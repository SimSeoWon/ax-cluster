"""`#392` ② — 진행 중 work 의 지휘자 스탬프를 큐 PATCH 로 바꾼다 (큐 쪽 계약).

[DOC] 대상: `task_queue/logic_persist.update_work_meta(worker_mode=)` · `models.WorkPatchReq.worker_mode` ·
      `server.patch_work_ep` 의 전달과 거절 모양. 임시 `TaskIndex` 만 쓴다(실 큐·HTTP 없음).
      출력 형식은 저장소 관례 `통과 N · 실패 M` + rc(실패 있으면 1).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.task_queue.persistence import TaskIndex                    # noqa: E402
from master.task_queue.logic import register_work                      # noqa: E402
from master.task_queue.logic_persist import update_work_meta           # noqa: E402

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


# [PSEUDO] #392: [1] codex 로 등재한 work 에 update_work_meta(worker_mode="claude") → ok · 레코드가 claude · changed 에 "worker_mode=codex→claude" 가 있다.
# [PSEUDO] #392: [2] 같은 값 재요청 → ok · changed 비어 있음(저장·커밋 없음).
# [PSEUDO] #392: [3] worker_mode="typo" 와 "  " → ok False · reason invalid_worker_mode · 레코드 그대로.
# [PSEUDO] #392: [4] merge_status 를 merged / rejected / cancelled 로 둔 각각에서 다른 모드 요청 → reason terminal_work · 레코드 그대로 · 같은 요청에 실은 다른 필드(예: dispatch_note)도 저장되지 않는다.
# [PSEUDO] #392: [5] worker_mode=None(생략) → 기존 스탬프 유지 · 다른 필드 patch 는 종전대로.
# [PSEUDO] #392: [6] WorkPatchReq(worker_mode="lane") 이 필드를 보존하고, 생략하면 None 이다.
# [PSEUDO] #392: [7] 서버 라우트: fastapi TestClient 없이 검증할 수 있으면 server.patch_work_ep 소스에 worker_mode=req.worker_mode 전달이 있는지와 reason 있는 실패를 404 로 바꾸지 않는지를 확인한다(실 HTTP 금지 — 기존 테스트가 라우트를 어떻게 잡는지 따른다).

print()
print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
