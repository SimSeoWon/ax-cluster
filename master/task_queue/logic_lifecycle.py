"""task_queue logic 분리 (2026-07-18) — submit/verify/cancel 라이프사이클 (facade = logic.py).

verify_task/submit_fail 종결 시 logic_cleanup 의 auto-cleanup 클러스터를 호출한다
(단방향 — cleanup 은 lifecycle 을 역참조하지 않음).
"""
import json
from typing import Optional
from .models import (
    _VERIFY_RESULT_TO_STATUS
)
from .persistence import (
    TaskIndex, _tq_log, _now_iso, _read_md, _git_commit_tasks
)
from .logic_persist import (
    _save_task, _save_work, _update_index_md, _count_terminal_in_work
)
from .logic_claim import _mark_worker_quota_blocked
from .logic_cleanup import _auto_cleanup_work_async


def _is_stale_epoch(submit_epoch: Optional[int], current_epoch: int) -> bool:
    """Plan v5 C.2 fencing 판정 (순수) — submit 의 epoch 이 현재보다 낮으면 stale(zombie).

    submit_epoch is None → 구 워커(epoch 미전송) 하위호환, 게이트 통과(거부 안 함).
    """
    if submit_epoch is None:
        return False
    return int(submit_epoch) < int(current_epoch)


def _identity_gate(t: dict, worker_id: Optional[str], what: str) -> Optional[dict]:
    """고지자가 **그 태스크의 현재 소유자**인가 (`#318` 완료 조건 1·2).

    [중요] 종전에는 이 판정이 아예 없었고, 코드 주석이 근거를 밝혔다 —
    *"notify 게이트의 권위 판정 (2-tier 구조가 push 충돌은 이미 차단)"*. **구조에 기댄** 것이고,
    그 전제는 프로젝트 1개·워커 1대일 때만 성립했다(`#251` 이 잠금에서 발견한 것과 같은 부류).

    [중요] **미확인은 통과가 아니다** — `worker_id` 를 안 보내면 거부한다. 실측 2026-08-27:
    큐의 submit 표면을 두드리는 주체는 **전부 이 저장소의 마스터 코드**다(워커에 배달되는
    `ax-work` 스킬은 *"마스터: 마커를 읽어 큐에 submit"* 이라고 적혀 있고, 상주 claimer 는
    `#320` 으로 철거됐다). 그래서 하위호환 예외를 둘 이유가 없다.

    [주의] 사유를 **돌려준다** — 조용한 실패를 만들지 않는다(이 저장소 관례).
    """
    owner = (t.get("worker_id") or "").strip()
    got = (worker_id or "").strip()
    if not got:
        return {"ok": False, "code": 409, "identity": True,
                "error": (f"{what}: worker_id 가 없다 — 고지자를 확인할 수 없다. "
                          f"미확인은 통과가 아니다 (`#318`)")}
    if owner and got != owner:
        return {"ok": False, "code": 409, "identity": True,
                "error": (f"{what}: 고지자 {got!r} 가 소유자 {owner!r} 가 아니다 — "
                          f"거부한다 (`#318`)")}
    return None


def submit_result(idx: TaskIndex, task_id: str, *,
                  branch: str, head_commit: str, self_check: dict,
                  escalation_questions: Optional[list] = None,
                  metrics: Optional[dict] = None,
                  epoch: Optional[int] = None,
                  worker_id: Optional[str] = None) -> dict:
    with idx.lock:
        t = idx.tasks.get(task_id)
        if not t:
            return {"ok": False, "error": "task not found"}
        # Plan v5 C.2 — fencing 게이트: 재배정으로 epoch 가 올라간 뒤 들어온 이전 워커(zombie)
        # 의 submit 거부. notify 게이트의 권위 판정 (2-tier 구조가 push 충돌은 이미 차단).
        if _is_stale_epoch(epoch, int(t.get("epoch", 0))):
            _tq_log(f"[submit] 거부 — {task_id} stale epoch {epoch} < 현재 {t.get('epoch')} "
                    f"(재배정됨; zombie assignee submit)", idx.root)
            return {"ok": False, "code": 409, "stale": True,
                    "error": f"stale epoch {epoch} < current {t.get('epoch')} (reassigned)"}
        bad = _identity_gate(t, worker_id, "submit")
        if bad:
            _tq_log(f"[submit] 거부 — {task_id} {bad['error']}", idx.root)
            return bad
        if t.get("status") != "claimed":
            return {"ok": False, "error": f"not in claimed state (current={t.get('status')})"}
        t["status"] = "submitted"
        t["submitted_at"] = _now_iso()
        # Plan v5 C.6 — 제출한 실제 브랜치명을 메타에 저장. push 의 ephemeral(attempt/<…>/<ts>)은
        # verifier 가 재구성 불가(ts 모름)라 이 값으로 머지 대상을 찾는다. (pull 은 worker/<id>/<task>.)
        t["submitted_branch"] = branch
        path = idx.task_paths[task_id]
        _, body = _read_md(path)
        body += "\n## self_check\n```json\n" + json.dumps(self_check, ensure_ascii=False, indent=2) + "\n```\n"
        body += f"\n## submit_meta\nbranch: {branch}\nhead_commit: {head_commit}\nat: {_now_iso()}\n"
        if escalation_questions:
            body += "\n## escalation_questions\n" + "\n".join(f"- {q}" for q in escalation_questions) + "\n"
        if metrics:
            body += "\n## metrics\n```json\n" + json.dumps(metrics, ensure_ascii=False, indent=2) + "\n```\n"
        _save_task(idx, task_id, body_override=body)
        _tq_log(f"[submit] {task_id} branch={branch} head={head_commit[:8]}", idx.root)
        _git_commit_tasks(idx.root, f"[submit] {task_id}: branch={branch}", [path])
        return {"ok": True}


def submit_fail(idx: TaskIndex, task_id: str, reason: str, detail: str = "", *,
                epoch: Optional[int] = None, worker_id: Optional[str] = None) -> dict:
    """실패 고지. [중요] **submit 과 같은 두 게이트를 건다** (`#318` 완료 조건 2).

    [중요] 종전에는 이 경로에 **epoch 게이트조차 없었다.** 만기돼 회수당한 워커가 뒤늦게
    「실패했다」고 고지하면 **재할당된 태스크가 실패로 뒤집혔다** — submit 은 fencing 하면서
    fail 은 안 하는 비대칭이었고, 방향이 나빴다: zombie 가 **살아 있는 작업을 죽인다.**
    """
    with idx.lock:
        t = idx.tasks.get(task_id)
        if not t:
            return {"ok": False, "error": "task not found"}
        if _is_stale_epoch(epoch, int(t.get("epoch", 0))):
            _tq_log(f"[submit-fail] 거부 — {task_id} stale epoch {epoch} < 현재 "
                    f"{t.get('epoch')} (재배정됨; zombie 가 살아 있는 작업을 죽이려 했다)", idx.root)
            return {"ok": False, "code": 409, "stale": True,
                    "error": f"stale epoch {epoch} < current {t.get('epoch')} (reassigned)"}
        bad = _identity_gate(t, worker_id, "submit-fail")
        if bad:
            _tq_log(f"[submit-fail] 거부 — {task_id} {bad['error']}", idx.root)
            return bad
        if t.get("status") not in ("claimed", "submitted"):
            return {"ok": False, "error": f"not in claim/submit state (current={t.get('status')})"}
        # Phase 3 lite — quota_exhausted 는 task 결과물이 아닌 워커 환경 문제이므로
        # task 를 죽이지 않고 pending 으로 되돌려 다른 워커가 잡게 함. 같은 워커는
        # 5h 동안 이 task 재할당 차단 (quota_blocked_workers).
        if reason == "quota_exhausted":
            worker_id = t.get("worker_id") or ""
            if worker_id:
                _mark_worker_quota_blocked(t, worker_id)
            t["status"] = "pending"
            t["worker_id"] = None
            t["claimed_at"] = None
            t["last_heartbeat"] = None
            path = idx.task_paths[task_id]
            _, body = _read_md(path)
            body += (f"\n## quota_release\nreason: {reason}\ndetail: {detail}\n"
                     f"by_worker: {worker_id}\nat: {_now_iso()}\n"
                     f"note: task → pending (다른 워커가 claim 가능). 이 워커는 5h 차단.\n")
            _save_task(idx, task_id, body_override=body)
            _tq_log(f"[quota-release] {task_id} ← {worker_id} (5h anti-affinity)", idx.root)
            _git_commit_tasks(idx.root, f"[quota-release] {task_id} from {worker_id}", [path])
            return {"ok": True, "released": True}
        # 일반 실패 — 기존 동작
        t["status"] = "failed"
        # 근거를 **본문뿐 아니라 레코드에도** 남긴다 (#222) — 본문에만 있으면 API·화면이
        # 「실패했다」까지만 알고 「왜」를 모른다. 본문은 감사 기록으로 그대로 유지한다.
        t["fail_reason"] = str(reason)[:120]
        t["fail_detail"] = str(detail)[:600]
        t["failed_at"] = _now_iso()
        path = idx.task_paths[task_id]
        _, body = _read_md(path)
        body += f"\n## fail\nreason: {reason}\ndetail: {detail}\nat: {_now_iso()}\n"
        _save_task(idx, task_id, body_override=body)
        _tq_log(f"[submit-fail] {task_id} reason={reason}", idx.root)
        _git_commit_tasks(idx.root, f"[submit-fail] {task_id}: {reason}", [path])
        # Phase 2 보강 — submit_fail 도 terminal 트리거 검사. failed task 가 마지막 상태
        # 라면 work 의 cleanup 진입.
        wid = t.get("work_id")
        if wid in idx.works:
            wmeta = idx.works[wid]
            terminal = _count_terminal_in_work(idx, wid)
            total = int(wmeta.get("total", 0))
            if terminal >= total and total > 0 and wmeta.get("merge_status") == "in_progress":
                wmeta["merge_status"] = "ready_for_review"
                v = int(wmeta.get("verified", 0))
                f = total - v
                _tq_log(f"[work-ready] {wid} all tasks done (post-fail) → ready_for_review "
                        f"(verified={v}, failed/cancelled={f})", idx.root)
                _save_work(idx, wid)
                _auto_cleanup_work_async(idx, wid)
        return {"ok": True}


def verify_task(idx: TaskIndex, task_id: str, passed: bool = True,
                 feedback: str = "", result: str = "",
                 new_base_commit: str = "", verify_epoch: Optional[int] = None) -> dict:
    """검증 결과 기록.

    인자:
      result: "pass" | "revise" | "reject" | "superseded" 명시 (없으면 passed=bool 로 fallback)
      passed: 하위 호환 — result 가 비면 True=pass, False=reject 로 매핑
      feedback: revise/reject 시 워커가 다음 시도에 참고할 텍스트
      new_base_commit: revise 시 워커 브랜치에 feedback 주석 박은 새 HEAD — 다음 claim 이 이 commit 에서 체크아웃
      verify_epoch: Plan v5 C.3 — 검증 워커 verdict 의 verify lease epoch. 현재보다 낮으면
                    stale(zombie 검증자) → verdict 거부. None(서버 verify-loop)은 fencing skip.
    """
    if result:
        if result not in _VERIFY_RESULT_TO_STATUS:
            return {"ok": False, "error": f"invalid result: {result} (allowed: {list(_VERIFY_RESULT_TO_STATUS)})"}
        new_status = _VERIFY_RESULT_TO_STATUS[result]
    else:
        new_status = "verified" if passed else "failed"
        result = "pass" if passed else "reject"

    with idx.lock:
        t = idx.tasks.get(task_id)
        if not t:
            return {"ok": False, "error": "task not found"}
        if t.get("status") != "submitted":
            return {"ok": False, "error": f"not in submitted state (current={t.get('status')})"}
        # Plan v5 C.3 — verify notify fencing: 재배정으로 verifier_epoch 가 올라간 뒤 들어온
        # 이전 검증 워커(zombie)의 verdict 거부. durable 권위 보존(stale verdict 가 다음 라운드
        # durable 을 덮어쓰는 것 차단). None 이면 서버 verify-loop(pull) — fencing skip.
        if _is_stale_epoch(verify_epoch, int(t.get("verifier_epoch", 0))):
            _tq_log(f"[verify] 거부 — {task_id} stale verify_epoch {verify_epoch} < "
                    f"현재 {t.get('verifier_epoch')} (재배정됨; zombie 검증자 verdict)", idx.root)
            return {"ok": False, "code": 409, "stale": True,
                    "error": f"stale verify_epoch {verify_epoch} < current {t.get('verifier_epoch')}"}
        t["status"] = new_status
        t["verified_at"] = _now_iso()
        # verdict 확정 — verify lease 해제 (verifier_epoch 는 단조 유지)
        t["verifier_id"] = None
        t["verify_claimed_at"] = None
        t["verify_heartbeat"] = None
        # 판정 근거를 레코드에도 (#222) — 화면이 「왜 그 상태인가」를 답할 수 있어야 한다.
        #    revise 의 last_result 와 달리 **모든** 판정에 남는다.
        t["verdict"] = result
        if feedback:
            t["verdict_feedback"] = str(feedback)[:600]
        if new_status == "failed":
            t.setdefault("fail_reason", f"verify:{result}")
            if feedback:
                t.setdefault("fail_detail", str(feedback)[:600])
        # revise 시 feedback 을 frontmatter 에 저장 — claim_task 가 다음 시도에 워커에게 전달
        if new_status == "needs_revision":
            t["last_feedback"] = feedback
            t["last_result"] = result
            if new_base_commit:
                # 워커 브랜치에 feedback 주석이 박힌 새 commit — 재시도는 여기서 출발
                t["base_commit"] = new_base_commit
                _tq_log(f"[verify-revise] {task_id} base_commit → {new_base_commit[:8]} (worker branch HEAD with embedded feedback)", idx.root)
        path = idx.task_paths[task_id]
        _, body = _read_md(path)
        body += f"\n## verify\nresult: {result}\nstatus: {new_status}\nat: {_now_iso()}\n"
        if feedback:
            body += f"\n## feedback\n{feedback}\n"
        _save_task(idx, task_id, body_override=body)
        wid = t.get("work_id")
        paths = [path]
        triggered_auto_cleanup = False
        if new_status in ("verified", "failed", "cancelled") and wid in idx.works:
            wmeta = idx.works[wid]
            if new_status == "verified":
                wmeta["verified"] = int(wmeta.get("verified", 0)) + 1
            # Phase 2 보강 (2026-05-10) — terminal 카운트로 트리거.
            # 이전엔 verified >= total 조건이 failed 무시 → 영구 stuck.
            terminal = _count_terminal_in_work(idx, wid)
            total = int(wmeta.get("total", 0))
            if terminal >= total and total > 0 and wmeta.get("merge_status") == "in_progress":
                wmeta["merge_status"] = "ready_for_review"
                triggered_auto_cleanup = True
                v = int(wmeta.get("verified", 0))
                f = total - v
                if f > 0:
                    _tq_log(f"[work-ready] {wid} all tasks done → ready_for_review (verified={v}, failed/cancelled={f})", idx.root)
                else:
                    _tq_log(f"[work-ready] {wid} all tasks verified → ready_for_review", idx.root)
            _save_work(idx, wid)
            paths.append(idx.work_paths[wid])
        _tq_log(f"[verify] {task_id} → {new_status} (result={result})", idx.root)
        _git_commit_tasks(idx.root, f"[verify] {task_id}: {result}", paths)
        _update_index_md(idx)
        # 마지막 task verified — 서버측 자동 정리 + Redmine 이슈 생성 (백그라운드)
        if triggered_auto_cleanup:
            _auto_cleanup_work_async(idx, wid)
        return {"ok": True, "status": new_status, "result": result}


def reverify_task(idx: TaskIndex, task_id: str) -> dict:
    """failed task 를 submitted 로 flip — verify-loop 가 다음 사이클에 재검증.

    용도: verifier 가 false-positive (ex: target_file 만 diff 해서 header-only 변경
    무시) 로 reject 한 task 를 새 verifier 로직으로 다시 평가. 워커 브랜치는 origin
    에 그대로 남아있어 재검증 가능.
    """
    with idx.lock:
        t = idx.tasks.get(task_id)
        if not t:
            return {"ok": False, "error": f"task not found: {task_id}"}
        if t.get("status") != "failed":
            return {"ok": False, "error": f"not failed (current={t.get('status')})"}
        t["status"] = "submitted"
        # work 의 verified 카운트 보정 — failed 였으니 늘리지 않았었음. 그대로 유지.
        # 단 work 가 이미 ready_for_review 로 flip 됐다면 다시 in_progress 로 돌림
        wid = t.get("work_id")
        if wid in idx.works:
            wmeta = idx.works[wid]
            if wmeta.get("merge_status") == "ready_for_review":
                wmeta["merge_status"] = "in_progress"
                _save_work(idx, wid)
                _tq_log(f"[reverify] {wid} merge_status ready_for_review → in_progress (재검증 진행)", idx.root)
        path = idx.task_paths[task_id]
        _, body = _read_md(path)
        body += f"\n## reverify\nat: {_now_iso()}\nnote: failed → submitted, verify-loop 재검증 대상\n"
        _save_task(idx, task_id, body_override=body)
        _tq_log(f"[reverify] {task_id} failed → submitted", idx.root)
        _git_commit_tasks(idx.root, f"[reverify] {task_id} → submitted",
                          [path] + ([idx.work_paths[wid]] if wid in idx.works else []))
        return {"ok": True, "task_id": task_id, "status": "submitted"}


def cancel_task(idx: TaskIndex, task_id: str) -> dict:
    with idx.lock:
        t = idx.tasks.get(task_id)
        if not t:
            return {"ok": False, "error": "task not found"}
        t["status"] = "cancelled"
        _save_task(idx, task_id)
        path = idx.task_paths[task_id]
        _tq_log(f"[cancel] {task_id}", idx.root)
        _git_commit_tasks(idx.root, f"[cancel] {task_id}", [path])
        return {"ok": True}
