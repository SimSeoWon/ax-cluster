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
                     review_decision: Optional[dict] = None) -> dict:
    """work 메타 부분 갱신. 명시된 필드만 patch. PATCH /api/v1/works/{work_id} 의 코어."""
    with idx.lock:
        wmeta = idx.works.get(work_id)
        if not wmeta:
            return {"ok": False, "error": f"work not found: {work_id}"}
        changed: list[str] = []
        if merge_status is not None and merge_status != wmeta.get("merge_status"):
            wmeta["merge_status"] = merge_status
            changed.append(f"merge_status={merge_status}")
        if redmine_issue_id is not None and redmine_issue_id != wmeta.get("redmine_issue_id"):
            wmeta["redmine_issue_id"] = redmine_issue_id
            changed.append(f"redmine_issue_id={redmine_issue_id}")
        if review_decision is not None:
            wmeta["review_decision"] = review_decision
            changed.append("review_decision")
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
