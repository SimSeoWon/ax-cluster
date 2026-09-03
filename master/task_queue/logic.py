import json
import shutil
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from .models import (
    _VALID_DIRECTIVES, _VERIFY_BACKPRESSURE_SEC, _VERIFY_RESULT_TO_STATUS,
    _KNOWN_CAPABILITIES, normalize_capabilities
)
from .persistence import (
    TaskIndex, _tasks_dir, _archive_dir, _tq_log, _now_iso, _gen_task_id,
    _slugify, _gen_work_id, _build_md, _atomic_write, _read_md,
    _git, _git_commit_tasks
)


# 책임 단위 분리 (2026-07-18) — facade re-export 로 기존 `from logic import ...` /
# `logic.X` 경로 보존 (watcher/context.py 패턴).
from .logic_persist import (  # noqa: F401  (re-export)
    _save_work, _save_task, _update_index_md, update_work_meta, _count_terminal_in_work,
)
from .logic_claim import (  # noqa: F401  (re-export)
    _VERIFY_LEASE_SEC, _QUOTA_BLOCK_WINDOW_SEC,
    _stalled_submitted_in_work, _is_verify_lease_active, _claim_verify_job,
    _worker_meets_requires,
    claim_task, _take_worker_directives, push_worker_directive,
    heartbeat, poll_worker, _is_worker_quota_blocked, _mark_worker_quota_blocked,
)
from .logic_lifecycle import (  # noqa: F401  (re-export)
    _is_stale_epoch, submit_result, submit_fail, verify_task, reverify_task, cancel_task,
)
from .logic_cleanup import (  # noqa: F401  (re-export)
    _read_redmine_config, _redmine_post_issue, _try_create_review_issue_async,
    _auto_cleanup_work_async,
)


# ─────────────────────────────────────────
# 핵심 로직 (모두 동기. RLock 으로 직렬화)
# ─────────────────────────────────────────

# merge_status 가 이 집합에 들어가면 "이미 종결된 work" 로 간주 — 중복 판정에서 제외.
_TERMINAL_MERGE_STATUSES = {"merged", "rejected", "cancelled"}


def _norm_repo(p: str) -> str:
    """target_repo 비교용 정규화 — 슬래시 통일 + 대소문자 무시 (Windows)."""
    return (p or "").replace("\\", "/").rstrip("/").lower()


def find_active_duplicates(idx: TaskIndex, *, slug: str, target_repo: str) -> list[dict]:
    """동일 slug + target_repo 의 active (미머지) work 목록.
    slug 는 _slugify 결과 기준 — 이 함수에 들어오기 전 호출자가 정규화해야 한다."""
    if not slug:
        return []
    norm_repo = _norm_repo(target_repo)
    out: list[dict] = []
    with idx.lock:
        for w in idx.works.values():
            wid = w.get("work_id", "")
            # work_id 는 "<YYYYMMDD_HHMM>_<slug>" — 뒷 토큰을 slug 로 사용
            parts = wid.split("_", 2)
            wid_slug = parts[2] if len(parts) >= 3 else ""
            if wid_slug != slug:
                continue
            if _norm_repo(w.get("target_repo", "")) != norm_repo:
                continue
            if (w.get("merge_status") or "in_progress") in _TERMINAL_MERGE_STATUSES:
                continue
            out.append({
                "work_id": wid,
                "title": w.get("title", ""),
                "target_branch": w.get("target_branch"),
                "merge_status": w.get("merge_status"),
                "redmine_issue_id": w.get("redmine_issue_id"),
                "total": w.get("total", 0),
                "verified": w.get("verified", 0),
                "created": w.get("created"),
            })
    return out


def register_work(idx: TaskIndex, *, title: str, target_repo: str,
                  project: str = "",
                  reference_repo: str = "", target_branch: str = "",
                  branch_isolation: bool = True, created_branch_at: str = "",
                  original_request: str = "", decomposition: str = "",
                  max_extensions_per_work: int = 5, slug: str = "",
                  review_scheduled: str = "",
                  distribution_mode: str = "pull",
                  force_duplicate: bool = False) -> dict:
    work_slug = slug or _slugify(title)
    if not force_duplicate:
        dups = find_active_duplicates(idx, slug=work_slug, target_repo=target_repo)
        if dups:
            _tq_log(f"[work-register] reject duplicate slug={work_slug} active={len(dups)}", idx.root)
            return {
                "ok": False,
                "reason": "duplicate",
                "slug": work_slug,
                "duplicates": dups,
            }
    with idx.lock:
        work_id = _gen_work_id(work_slug)
        td = _tasks_dir(idx.root) / work_id
        td.mkdir(parents=True, exist_ok=True)
        meta = {
            "work_id": work_id,
            "title": title,
            "project": project or None,     # [중요] 귀속 스탬프 (#210) — None = 옛 등록
            "target_repo": target_repo,
            "reference_repo": reference_repo,
            "target_branch": target_branch or None,
            "branch_isolation": branch_isolation,
            "created_branch_at": created_branch_at or None,
            "merge_status": "in_progress",
            "review_scheduled": review_scheduled or None,
            "review_decision": {"decided_at": None, "decided_by": None,
                                "result": None, "notes": None},
            "total": 0,
            "verified": 0,
            "extensions_used": 0,
            "max_extensions_per_work": max_extensions_per_work,
            # Plan v5 C.6 — pull(기본)/push 모드 per-work 스탬프. 플래그 flip 은 신규 work 만,
            # in-flight 는 시작 모드로 완주(가역·안전). 워커/verifier 는 이 값(또는 task 의 복사본)으로 분기.
            "distribution_mode": distribution_mode if distribution_mode in ("pull", "push") else "pull",
            "created": _now_iso(),
        }
        body_parts = ["", "## Original Request", "", original_request or "(none)", ""]
        if decomposition:
            body_parts += ["## Decomposition", "", decomposition, ""]
        body_parts += ["## Subtasks", "", "(registration in progress)", ""]
        body = "\n".join(body_parts)
        path = td / "_request.md"
        _atomic_write(path, _build_md(meta, body))
        idx.works[work_id] = meta
        idx.work_paths[work_id] = path
        _tq_log(f"[work-register] {work_id} title={title}", idx.root)
        _git_commit_tasks(idx.root, f"[work-register] {work_id}: {title}", [path])
        _update_index_md(idx)
        result = dict(meta)
        result["ok"] = True
        return result


def register_task(idx: TaskIndex, *, work_id: str, type: str, task_data: dict,
                  base_commit: str = "", target_file: str = "",
                  header_file: str = "", depends_on: Optional[list] = None,
                  hierarchy_level: int = 0, priority: int = 0,
                  stem: str = "", origin: str = "master",
                  parent_attempt: Optional[str] = None,
                  requires: Optional[list] = None) -> dict:
    if work_id not in idx.works:
        return {"ok": False, "error": f"unknown work_id: {work_id}"}
    # PLAN §5.2-C — 능력 태그는 **등록 시점에** 검증한다. 미지의 태그를 통과시키면 어떤 워커도
    # 만족시킬 수 없는 task 가 조용히 pending 에 쌓인다(claim 쪽은 fail-closed 라 영원히 skip).
    req_caps = normalize_capabilities(requires)
    unknown = [c for c in req_caps if c not in _KNOWN_CAPABILITIES]
    if unknown:
        return {"ok": False,
                "error": f"unknown requires: {','.join(unknown)} "
                         f"(allowed: {','.join(_KNOWN_CAPABILITIES)})"}
    with idx.lock:
        task_id = _gen_task_id()
        meta = {
            "task_id": task_id,
            "work_id": work_id,
            "type": type,
            "status": "pending",
            "base_commit": base_commit,
            "target_file": target_file,
            "header_file": header_file,
            "depends_on": depends_on or [],
            # PLAN §5.2-C — 능력 요구. 빈 리스트면 아무 워커나 집을 수 있다(기존 동작).
            "requires": req_caps,
            "hierarchy_level": hierarchy_level,
            "priority": priority,
            "worker_id": None,
            "last_heartbeat": None,
            "claimed_at": None,
            "submitted_at": None,
            "verified_at": None,
            "attempt_count": 0,
            "reclaim_count": 0,
            # Plan v5 C.2 — fencing token: (재)배정마다 단조 증가. assignee=현재 배정 워커.
            # submit/notify 게이트가 stale epoch(zombie assignee) 를 거부하는 권위 기준.
            "epoch": 0,
            "assignee": None,
            # Plan v5 C.3 — 검증 워커 lease (write lease 와 직교; submitted task 를 다른 워커가
            # 검증하는 동안 점유). verifier_epoch 는 verify notify fencing(zombie 검증자 verdict 거부).
            "verifier_id": None,
            "verifier_epoch": 0,
            "verify_claimed_at": None,
            "verify_heartbeat": None,
            # Plan v5 C.6 — work 의 모드를 task 로 복사 → claim 응답으로 워커에 전파(워커가 분기).
            "distribution_mode": idx.works[work_id].get("distribution_mode", "pull"),
            "origin": origin,
            "parent_attempt": parent_attempt,
            "created": _now_iso(),
        }
        body = "\n## task_data\n```json\n" + json.dumps(task_data, ensure_ascii=False, indent=2) + "\n```\n"
        fname = f"{task_id}_{_slugify(stem) if stem else 'task'}.md"
        path = _tasks_dir(idx.root) / work_id / fname
        _atomic_write(path, _build_md(meta, body))
        idx.tasks[task_id] = meta
        idx.task_paths[task_id] = path
        # [중요] claim 응답으로 워커에 전달하려면 **메모리에도** 들고 있어야 한다. 본문에만 쓰면
        #    재기동 전까지 아무도 못 읽는다(`rebuild()` 가 본문에서 되읽는 것과 짝이다).
        idx.task_data[task_id] = dict(task_data or {})
        wmeta = idx.works[work_id]
        wmeta["total"] = int(wmeta.get("total", 0)) + 1
        _save_work(idx, work_id)
        _tq_log(f"[register] {task_id} work={work_id} type={type} target={target_file} "
                f"level={hierarchy_level} requires={','.join(req_caps) or '-'}", idx.root)
        _git_commit_tasks(idx.root,
                          f"[task-register] {task_id} → {work_id}: {stem or 'task'}",
                          [path, idx.work_paths[work_id]])
        return {"ok": True, "task_id": task_id, "meta": dict(meta)}


def admin_reset(idx: TaskIndex, purge: bool = False, cleanup_branches: bool = False) -> dict:
    """모든 work·task 를 비운다 (테스트용).

    purge=False (기본): work 폴더들을 `_archive/_purge_<timestamp>/` 로 이동, 인덱스 파일 삭제.
    purge=True: work 폴더들을 완전 삭제, 인덱스 파일 삭제.
    [중요] cleanup_branches 는 **마스터에서 지원하지 않는다** (2026-08-08 이식 시 결정).
    AgentTest 에서는 root == UE5 프로젝트 루트라 상태와 코드가 같은 저장소였고 거기서
    `worker/*` 브랜치를 지우는 게 맞았다. 마스터의 root 는 **큐 상태 저장소**(ax-state)이고
    UE5 저장소가 아니라, 그대로 두면 지울 브랜치를 못 찾고 **조용히 성공한 척**한다.
    브랜치 정리는 저장소를 소유한 쪽(윈도우 작업장)의 일이다 (PLAN.md §2.1).
    → **아무것도 건드리기 전에** 거부한다. (원본 구현은 AgentTest 쪽에 그대로 있다.)

    in-memory 인덱스는 항상 비우고 _git_commit 으로 audit 흔적 남김.
    """
    if cleanup_branches:
        return {
            "ok": False,
            "error": "cleanup_branches_not_supported_on_master",
            "detail": ("브랜치 정리는 UE5 저장소를 소유한 윈도우 작업장의 일이다. "
                       "마스터의 root 는 큐 상태 저장소라 대상 브랜치가 존재하지 않는다 "
                       "(PLAN.md §2.1). --cleanup-branches 없이 다시 실행하라."),
        }
    with idx.lock:
        td = _tasks_dir(idx.root)
        if not td.exists():
            return {"ok": True, "message": "no tasks dir", "moved": 0}

        work_dirs = [d for d in td.iterdir() if d.is_dir() and not d.name.startswith("_")]
        index_md = td / "_index.md"
        review_queue_md = td / "_review_queue.md"

        moved_works: list[str] = []
        archive_target: Optional[Path] = None

        if purge:
            for d in work_dirs:
                shutil.rmtree(d, ignore_errors=True)
                moved_works.append(d.name)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_target = _archive_dir(idx.root) / f"_purge_{ts}"
            archive_target.mkdir(parents=True, exist_ok=True)
            for d in work_dirs:
                try:
                    shutil.move(str(d), str(archive_target / d.name))
                    moved_works.append(d.name)
                except Exception as e:
                    _tq_log(f"[reset] move 실패 {d.name}: {e}", idx.root)

        for f in (index_md, review_queue_md):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

        # in-memory 비우기
        idx.tasks.clear()
        idx.task_paths.clear()
        idx.works.clear()
        idx.work_paths.clear()

        action = "purge" if purge else "archive"
        _tq_log(f"[admin-reset] {action} works={len(moved_works)} → {archive_target or '(deleted)'}", idx.root)
        # audit commit
        try:
            paths_for_commit = [td] if td.exists() else []
            _git_commit_tasks(idx.root, f"[admin-reset] {action} {len(moved_works)} works", paths_for_commit)
        except Exception:
            pass

        branch_result: Optional[dict] = None
        result = {
            "ok": True,
            "action": action,
            "moved_count": len(moved_works),
            "moved": moved_works,
            "archive": str(archive_target) if archive_target else None,
        }
        if branch_result is not None:
            result["branches"] = branch_result
        return result


# ─────────────────────────────────────────
# Phase 2 — work meta patch / summary / auto-cleanup / Redmine
# ─────────────────────────────────────────

def get_work_summary(idx: TaskIndex, work_id: str) -> dict:
    """work 1건의 task 상태 요약 + 종결 플래그.

    Phase 2 초기엔 `all_verified` (전 task 가 verified) 만 cleanup 진입 조건이었으나
    failed/cancelled 가 섞이면 stuck — 2026-05-10 ModularStage 사고 후 `all_done`
    (terminal == total) 도 함께 노출. cleanup 은 all_done 만으로도 진입 가능.
    """
    with idx.lock:
        wmeta = idx.works.get(work_id)
        if not wmeta:
            return {"ok": False, "error": f"work not found: {work_id}"}
        tasks = [t for t in idx.tasks.values() if t.get("work_id") == work_id]
        by_status: dict[str, int] = {}
        for t in tasks:
            s = t.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        total = int(wmeta.get("total", 0)) or len(tasks)
        verified = int(wmeta.get("verified", 0))
        terminal = sum(by_status.get(s, 0) for s in ("verified", "cancelled", "failed"))
        all_verified = (verified == total and total > 0 and verified == terminal)
        all_done = (terminal == total and total > 0)
        return {
            "ok": True, "work_id": work_id,
            "merge_status": wmeta.get("merge_status"),
            "target_branch": wmeta.get("target_branch"),
            "total": total, "verified": verified, "terminal": terminal,
            "by_status": by_status,
            "all_verified": all_verified,  # 전부 verified (실패 0)
            "all_done": all_done,            # 전부 종결 (failed/cancelled 포함)
        }


def recover_stuck_works(idx: TaskIndex) -> list[str]:
    """daemon --serve 부팅 시 1회 — 기존 stuck work 자동 복구.

    배경: 이전 버전 verify_task 가 `verified == total` 조건만 보다보니 failed 가
    섞이면 in_progress 상태로 영구 stuck. 새 버전은 terminal 카운트로 트리거하므로
    daemon 재기동만으로 자동 회복 가능.

    동작:
      - in_progress 인 work 들을 스캔
      - 각 work 의 terminal task 수가 total 과 같으면 → ready_for_review 로 flip
        + auto_cleanup 트리거
      - 아직 진행 중인 work (pending/claimed/submitted 가 남음) 는 손대지 않음

    반환: 복구된 work_id 목록.
    """
    recovered: list[str] = []
    with idx.lock:
        for wid, wmeta in list(idx.works.items()):
            if wmeta.get("merge_status") != "in_progress":
                continue
            total = int(wmeta.get("total", 0))
            if total <= 0:
                continue
            terminal = _count_terminal_in_work(idx, wid)
            if terminal < total:
                continue
            wmeta["merge_status"] = "ready_for_review"
            verified = int(wmeta.get("verified", 0))
            failed = total - verified
            _tq_log(f"[boot-recover] {wid} stuck work 복구 → ready_for_review "
                    f"(total={total}, verified={verified}, failed/cancelled={failed})", idx.root)
            _save_work(idx, wid)
            recovered.append(wid)
    # auto_cleanup 은 lock 밖에서 비동기로 (각 work 의 git 작업이 시간 걸림)
    for wid in recovered:
        _auto_cleanup_work_async(idx, wid)
    return recovered


# ─────────────────────────────────────────
# Phase 3 lite — rebase-pending (drift 0 보장)
# ─────────────────────────────────────────

def rebase_pending_tasks_in_work(idx: TaskIndex, work_id: str,
                                  new_base_commit: str) -> dict:
    """work 내 pending/needs_revision task 들의 base_commit 을 일괄 갱신.

    매 task verify-merge 직후 master_orchestrator 가 호출 — 다음 task 가 stale base
    위에서 시작해 머지 충돌·시그니처 silent 손실 일으키는 문제 차단.
    """
    if not new_base_commit or len(new_base_commit) < 7:
        return {"ok": False, "error": f"invalid base_commit: {new_base_commit!r}"}
    with idx.lock:
        if work_id not in idx.works:
            return {"ok": False, "error": f"work not found: {work_id}"}
        rebased: list[str] = []
        for tid, t in idx.tasks.items():
            if t.get("work_id") != work_id:
                continue
            if t.get("status") not in ("pending", "needs_revision"):
                continue
            old = t.get("base_commit", "")
            if old == new_base_commit:
                continue  # 이미 최신
            t["base_commit"] = new_base_commit
            _save_task(idx, tid)
            rebased.append(tid)
        if rebased:
            _tq_log(f"[rebase] {work_id}: {len(rebased)}개 task base_commit ← {new_base_commit[:8]}",
                    idx.root)
            paths = [idx.task_paths[tid] for tid in rebased if tid in idx.task_paths]
            _git_commit_tasks(idx.root,
                              f"[rebase] {work_id}: {len(rebased)} pending tasks → {new_base_commit[:8]}",
                              paths)
        return {"ok": True, "work_id": work_id, "rebased_count": len(rebased),
                "rebased_tasks": rebased, "new_base_commit": new_base_commit}
