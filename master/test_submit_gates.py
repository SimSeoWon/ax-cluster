"""`#318` — submit/submit-fail 의 **두 게이트**: epoch 펜싱 + 고지자 신원.

## [중요] 왜 이 파일이 있나

종전에는 `submit_result` 가 epoch 만 보고 **신원을 안 봤고**, `submit_fail` 은 **아무것도 안
봤다.** 그래서 두 가지가 가능했다:

    ① 워커 토큰만 있으면 **남의 태스크에 submit** 할 수 있다 (epoch 만 맞으면)
    ② 만기돼 회수당한 워커가 뒤늦게 「실패했다」고 고지하면 **재할당된 태스크가 실패로 뒤집힌다**

②의 방향이 특히 나쁘다 — **zombie 가 살아 있는 작업을 죽인다.** submit 은 fencing 하면서
fail 은 안 하는 비대칭이었다.

[중요] 신원 대조 대신 구조에 기댄 근거가 코드 주석에 있었다 — *"2-tier 구조가 push 충돌은
이미 차단"*. 그 전제는 **프로젝트 1개·워커 1대**일 때만 성립했다(`#251` 이 잠금에서 발견한
것과 같은 부류: 근거와 범위가 어긋난 채 N=1 이 가려 왔다).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue.logic import claim_task, register_task, register_work   # noqa: E402
from master.task_queue.logic_lifecycle import submit_fail, submit_result       # noqa: E402
from master.task_queue.persistence import TaskIndex                            # noqa: E402

A, B = "w-.2", "w-.43"
_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail
    if ok:
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _claimed(worker: str = A) -> tuple:
    """work + task 하나를 만들고 `worker` 가 claim 한 상태로 돌려준다."""
    root = Path(tempfile.mkdtemp(prefix="ax-318-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="t", target_repo="/tmp/repo")
    register_task(idx, work_id=w["work_id"], type="build", task_data={}, stem="b")
    t = claim_task(idx, worker, capabilities=["ue5"], types=["build"])
    return idx, t["task_id"], int(t.get("epoch", 1))


def _ok_submit(idx, tid, epoch, worker):
    return submit_result(idx, tid, branch="br", head_commit="abc",
                         self_check={"build": {"ok": True}}, epoch=epoch, worker_id=worker)


def test_submit_identity() -> None:
    print("\n[1] submit — 고지자 신원 (완료 조건 1)")
    idx, tid, ep = _claimed()
    r = _ok_submit(idx, tid, ep, B)
    check("[중요] 남의 태스크에 submit 하면 거부한다", not r.get("ok") and r.get("identity"), str(r))
    check("  사유를 돌려준다 (조용한 실패가 아니다)", "소유자" in (r.get("error") or ""), str(r))
    check("  상태를 안 바꾼다", idx.tasks[tid]["status"] == "claimed", idx.tasks[tid]["status"])

    r2 = submit_result(idx, tid, branch="br", head_commit="abc",
                       self_check={}, epoch=ep)          # worker_id 미전송
    check("[중요] worker_id 를 안 보내면 거부한다 (미확인은 통과가 아니다)",
          not r2.get("ok") and r2.get("identity"), str(r2))

    r3 = _ok_submit(idx, tid, ep, A)
    check("소유자가 보내면 통과한다", r3.get("ok"), str(r3))
    check("  상태가 submitted", idx.tasks[tid]["status"] == "submitted")


def test_submit_fail_gates() -> None:
    print("\n[2] submit-fail — **같은 두 게이트** (완료 조건 2)")
    idx, tid, ep = _claimed()
    r = submit_fail(idx, tid, "build-setup", "엔진 못 찾음", epoch=ep, worker_id=B)
    check("[중요] 남이 실패를 고지하면 거부한다", not r.get("ok") and r.get("identity"), str(r))
    check("  태스크를 죽이지 않았다", idx.tasks[tid]["status"] == "claimed",
          idx.tasks[tid]["status"])

    r2 = submit_fail(idx, tid, "build-setup", "x", epoch=ep - 1, worker_id=A)
    check("[중요] stale epoch 의 실패 고지를 거부한다 (종전에는 게이트가 아예 없었다)",
          not r2.get("ok") and r2.get("stale"), str(r2))
    check("  태스크를 죽이지 않았다", idx.tasks[tid]["status"] == "claimed")

    r3 = submit_fail(idx, tid, "build-setup", "엔진 못 찾음", epoch=ep, worker_id=A)
    check("소유자가 현재 epoch 로 보내면 통과한다", r3.get("ok"), str(r3))
    check("  상태가 failed", idx.tasks[tid]["status"] == "failed")


def test_zombie_after_reassignment() -> None:
    """[중요] 완료 조건 8 — 재파견 뒤 **옛 대상의 submit 과 fail 이 둘 다** 거부되나."""
    print("\n[3] 재파견 뒤 zombie — submit **과** fail 둘 다 (완료 조건 8)")
    idx, tid, ep_a = _claimed(A)

    # 회수(reclaim 이 하는 것과 같은 형태) → 다른 워커가 다시 집는다
    t = idx.tasks[tid]
    t["status"], t["worker_id"], t["last_heartbeat"] = "pending", None, None
    t2 = claim_task(idx, B, capabilities=["ue5"], types=["build"])
    ep_b = int(t2.get("epoch", 0))
    check("재claim 이 epoch 를 올린다 (펜싱 전제)", ep_b > ep_a, f"{ep_a} → {ep_b}")
    check("재claim 이 소유자를 갱신한다", idx.tasks[tid]["worker_id"] == B,
          str(idx.tasks[tid].get("worker_id")))

    z1 = _ok_submit(idx, tid, ep_a, A)
    check("[중요] zombie 의 submit 이 거부된다", not z1.get("ok"), str(z1))
    z2 = submit_fail(idx, tid, "죽었다고 고지", "", epoch=ep_a, worker_id=A)
    check("[중요] zombie 의 **fail** 도 거부된다 — 살아 있는 작업을 못 죽인다",
          not z2.get("ok"), str(z2))
    check("  태스크는 여전히 claimed (B 가 일하는 중)",
          idx.tasks[tid]["status"] == "claimed", idx.tasks[tid]["status"])

    ok = _ok_submit(idx, tid, ep_b, B)
    check("현재 소유자 B 는 통과한다", ok.get("ok"), str(ok))


def test_quota_release_also_gated() -> None:
    print("\n[4] quota_exhausted 되돌리기도 같은 게이트를 지난다")
    idx, tid, ep = _claimed()
    r = submit_fail(idx, tid, "quota_exhausted", "", epoch=ep, worker_id=B)
    check("[중요] 남이 quota 로 되돌릴 수 없다", not r.get("ok") and r.get("identity"), str(r))
    check("  pending 으로 안 떨어졌다", idx.tasks[tid]["status"] == "claimed")
    r2 = submit_fail(idx, tid, "quota_exhausted", "", epoch=ep, worker_id=A)
    check("소유자는 되돌릴 수 있다", r2.get("ok") and r2.get("released"), str(r2))
    check("  pending 으로 돌아갔다", idx.tasks[tid]["status"] == "pending")


def test_waiting_is_visible() -> None:
    """[중요] 완료 조건 5 — 회수돼 `pending` 으로 돌아온 태스크가 **보여야** 한다.

    push 모델에서는 회수돼도 **집을 주체가 없다**(pull 이면 다른 워커가 집었다). 마스터가
    파견 루프를 다시 돌리는 것이 곧 재파견이고, 상주가 철거된 지금(`#320`) 그 루프는 사람이
    시작한다. 그래서 「기다리는 것이 있다」가 안 보이면 **조용히 멈춘다.**
    """
    print("\n[5] 회수된 태스크의 가시성 (완료 조건 5)")
    from master.work import runner as RN
    rows = [
        {"task_id": "aaaa1111", "status": "pending", "reclaim_count": 2, "stem": "A"},
        {"task_id": "bbbb2222", "status": "pending", "reclaim_count": 0, "stem": "B"},
        {"task_id": "cccc3333", "status": "stuck", "reclaim_count": 4, "stem": "C"},
        {"task_id": "dddd4444", "status": "claimed", "reclaim_count": 9, "stem": "D"},
    ]
    w = RN.waiting_summary("NS", api=lambda m, p, b=None: rows)
    check("pending 을 센다", w["pending"] == 2, str(w))
    check("[주의] stuck 을 pending 과 섞지 않는다", w["stuck"] == 1, str(w))
    check("[중요] 회수된 것을 따로 센다", w["reclaimed"] == 2, str(w))
    check("  claimed 는 대기가 아니다 (세지 않는다)",
          all("dddd4444" not in ln for ln in w["lines"]), str(w["lines"]))
    check("  회수 횟수를 줄에 적는다", any("회수 2회" in ln for ln in w["lines"]), str(w["lines"]))

    def _boom(m, p, b=None):
        raise RuntimeError("큐가 안 뜬다")
    w2 = RN.waiting_summary("NS", api=_boom)
    check("[중요] 못 읽으면 0 이 아니라 **사유**를 남긴다 (없다는 뜻이 아니다)",
          any("읽지 못했다" in ln for ln in w2["lines"]), str(w2))


def main() -> int:
    for fn in (test_submit_identity, test_submit_fail_gates,
               test_zombie_after_reassignment, test_quota_release_also_gated,
               test_waiting_is_visible):
        fn()
    total = 26
    print(f"\n{'OK' if not _fail else '[실패]'} test_submit_gates: {total - _fail}/{total} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
