"""task_queue logic 분리 (2026-07-18) — 최저수준 영속 헬퍼 (공유 베이스, facade = logic.py).
"""
from typing import Optional
from .persistence import (
    TaskIndex, _tasks_dir, _tq_log, _now_iso, _build_md, _atomic_write, _read_md,
    _git_commit_tasks
)


def _save_work(idx: TaskIndex, work_id: str):
    path = idx.work_paths.get(work_id)
    if not path:
        return
    _, body = _read_md(path) if path.exists() else ({}, "")
    meta = idx.works[work_id]
    _atomic_write(path, _build_md(meta, body))


def _save_task(idx: TaskIndex, task_id: str, body_override: Optional[str] = None):
    path = idx.task_paths.get(task_id)
    if not path:
        return
    _, body = _read_md(path) if path.exists() else ({}, "")
    if body_override is not None:
        body = body_override
    meta = idx.tasks[task_id]
    _atomic_write(path, _build_md(meta, body))


def _update_index_md(idx: TaskIndex):
    """`.claude/tasks/_index.md` 갱신 — 활성 work 요약."""
    path = _tasks_dir(idx.root) / "_index.md"
    lines = ["# Task Queue Index", "",
             f"_Updated: {_now_iso()}_", "",
             "## Active Works", "",
             "| work_id | title | branch | total/verified | merge_status |",
             "|---|---|---|---|---|"]
    for wid, w in sorted(idx.works.items()):
        if w.get("merge_status") == "merged":
            continue
        lines.append(f"| {wid} | {w.get('title','-')} | {w.get('target_branch') or '-'} | "
                     f"{w.get('verified',0)}/{w.get('total',0)} | {w.get('merge_status','-')} |")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding='utf-8')


def update_work_meta(idx: TaskIndex, work_id: str, *,
                     merge_status: Optional[str] = None,
                     redmine_issue_id: Optional[int] = None,
                     review_decision: Optional[dict] = None,
                     target_branch: Optional[str] = None,
                     noticed_round: Optional[int] = None,
                     dispatch_note: Optional[str] = None,
                     dispatch_at: Optional[str] = None,
                     worker_mode: Optional[str] = None) -> dict:
    """work 메타 부분 갱신. 명시된 필드만 patch. PATCH /api/v1/works/{work_id} 의 코어."""
    # [DOC] #392 ② (사용자 결정 2026-10-05 · 2026-10-11 A안): `worker_mode` 는 진행 중 work 의
    #       지휘자 스탬프를 바꾸는 장애 대응 경로다. None 이면 손대지 않는다. 적용은 **다음 파견부터**
    #       (`autodispatch` 가 파견 시작 때 스탬프를 한 번 읽어 그 파견 전체에 고정한다 — #389 그대로).
    #       거절은 `{"ok": False, "reason": <코드>, "error": <문장>}` 이고 저장하지 않는다:
    #         invalid_worker_mode  `master.work.mode.MODES` 밖의 값 (strip 뒤 빈 값 포함)
    #         terminal_work        merge_status 가 merged · rejected · cancelled
    #       바뀌면 changed 에 `worker_mode=<이전 또는 None>→<새 값>` 한 항목을 넣는다 — 기존
    #       `[work-patch]` 로그·커밋 메시지가 그 문자열로 이전·새 값을 남긴다.
    normalized_worker_mode = None
    if worker_mode is not None:
        from ..work.mode import MODES
        normalized_worker_mode = worker_mode.strip()
        if normalized_worker_mode not in MODES:
            return {
                "ok": False,
                "reason": "invalid_worker_mode",
                "error": f"알 수 없는 worker_mode: {normalized_worker_mode!r}",
            }
    with idx.lock:
        wmeta = idx.works.get(work_id)
        if not wmeta:
            return {"ok": False, "error": f"work not found: {work_id}"}
        previous_worker_mode = wmeta.get("worker_mode")
        worker_mode_changed = (normalized_worker_mode is not None
                               and normalized_worker_mode != previous_worker_mode)
        if worker_mode_changed and wmeta.get("merge_status") in (
                "merged", "rejected", "cancelled"):
            return {
                "ok": False,
                "reason": "terminal_work",
                "error": f"종결된 work 의 worker_mode 는 바꿀 수 없습니다: {work_id}",
            }
        changed: list[str] = []
        if merge_status is not None and merge_status != wmeta.get("merge_status"):
            wmeta["merge_status"] = merge_status
            changed.append(f"merge_status={merge_status}")
        # [중요] 라운드 완료 노트의 **멱등 표시** — 같은 라운드를 두 번 적지 않기 위한 것.
        #    [주의] 이 함수는 **화이트리스트**다. 없는 키워드를 넘기면 `TypeError` 가 나고,
        #    실측 2026-09-05 00:06 에 그것으로 노트 기록 뒤 저장이 통째로 깨졌다
        #    (노트는 붙었는데 표시가 안 남아 재발동 시 두 번 붙는 상태였다).
        if noticed_round is not None and int(noticed_round) != int(wmeta.get("noticed_round", 0) or 0):
            wmeta["noticed_round"] = int(noticed_round)
            changed.append(f"noticed_round={noticed_round}")
        # 🔴 [중요] **「왜 안 걸렸나」를 큐가 말한다** (사용자 2026-09-05 · `.33` 보고).
        #    요청자에서 마스터로 가는 SSH 가 없어서, 파견이 안 돌면 `.33` 은 *"pending 인데
        #    아무도 안 집는다"* 까지만 알고 사유를 못 봤다 — 사람이 마스터에 물어야 했다.
        #    파견기가 매번 이 자리에 사유를 적으면 `get_work`·`list_works` 가 그대로 돌려준다.
        #    [주의] 값이 같으면 `changed` 가 비어 **아무것도 쓰지 않는다** — catchup 이 10분마다
        #    돌아도 커밋이 쌓이지 않는다.
        if dispatch_note is not None and str(dispatch_note) != str(wmeta.get("dispatch_note") or ""):
            wmeta["dispatch_note"] = str(dispatch_note)[:300]
            wmeta["dispatch_at"] = dispatch_at or _now_iso()
            changed.append("dispatch_note")
        if redmine_issue_id is not None and redmine_issue_id != wmeta.get("redmine_issue_id"):
            wmeta["redmine_issue_id"] = redmine_issue_id
            changed.append(f"redmine_issue_id={redmine_issue_id}")
        if review_decision is not None:
            wmeta["review_decision"] = review_decision
            changed.append("review_decision")
        # [중요] 작업 브랜치 이름은 **work_id 를 받은 뒤에야** 만들어진다 (`#319`) —
        #    `task/<work_id>/base`. 생성 POST 에는 실을 수 없으므로 등록이 곧바로 patch 한다.
        #    큐가 work 메타의 SSOT 이므로 유도값을 여기 적어 둔다 (표·조회가 그것을 읽는다).
        if target_branch is not None and target_branch != wmeta.get("target_branch"):
            wmeta["target_branch"] = target_branch
            changed.append(f"target_branch={target_branch}")
        if worker_mode_changed:
            wmeta["worker_mode"] = normalized_worker_mode
            changed.append(f"worker_mode={previous_worker_mode}→{normalized_worker_mode}")
        if not changed:
            return {"ok": True, "work_id": work_id, "changed": []}
        _save_work(idx, work_id)
        _tq_log(f"[work-patch] {work_id} ← {', '.join(changed)}", idx.root)
        _git_commit_tasks(idx.root, f"[work-patch] {work_id}: {', '.join(changed)}",
                          [idx.work_paths[work_id]])
        _update_index_md(idx)
        return {"ok": True, "work_id": work_id, "changed": changed, "work": dict(wmeta)}


def _count_terminal_in_work(idx: TaskIndex, work_id: str) -> int:
    """work 의 verified+failed+cancelled task 수. lock 보유 가정."""
    return sum(1 for t in idx.tasks.values()
               if t.get("work_id") == work_id
               and t.get("status") in ("verified", "failed", "cancelled"))


def completed_work_status(idx: TaskIndex, work_id: str) -> str:
    """Classify a completed round; no-work cancellations are successful skips (#701).

    [중요] 요청자 인계 취소(`requester_handoff`, `#757` · 사용자 결정 2026-10-09 ①)도
    `no_work` 처럼 라운드를 `cancelled` 로 만들지 않는다 — ⑦ 에서 사람이 채운다.
    """
    work = idx.works.get(work_id) or {}
    total = int(work.get("total") or 0)
    if total <= 0 or _count_terminal_in_work(idx, work_id) < total:
        return ""
    round_no = int(work.get("round") or 1)
    tasks = [task for task in idx.tasks.values() if task.get("work_id") == work_id
             and int(task.get("round") or 0) in (0, round_no)]
    if any(task.get("status") == "failed" for task in tasks):
        return "rejected"
    if any(task.get("status") == "cancelled" and not task.get("no_work")
           and not task.get("requester_handoff") for task in tasks):
        return "cancelled"
    return "ready_for_review"
