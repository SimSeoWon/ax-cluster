"""
task_queue MCP 서버 (2026-05-02 재작성: SQLite → MD 폴더 저장)

작업 저장 구조:
  .claude/tasks/_index.md
  .claude/tasks/_review_queue.md
  .claude/tasks/<work_id>/_request.md
  .claude/tasks/<work_id>/<task_id>_<stem>.md
  .claude/tasks/_archive/<work_id>/

서버 동시성: 단일 프로세스 + threading.RLock (워커는 HTTP 만 사용해 외부 동시 쓰기 없음).
매 상태 전이마다 MD 갱신 + git add + commit (감사 로그). git 실패는 경고만, 동작 막지 않음.

3가지 실행 모드:
  task_queue.exe                                           MCP stdio (기본)
  task_queue.exe --serve <project_root> [port] [host]      HTTP 서버 모드 (워커 폴링)
  task_queue.exe --status <project_root>                   상태 출력
  task_queue.exe --list   <project_root> [status]          task 목록 출력
"""
import sys
import json
import threading
from pathlib import Path
from typing import Optional

from .models import (
    _VALID_DIRECTIVES, _VERIFY_RESULT_TO_STATUS, WorkRegisterReq, TaskRegisterReq,
    ClaimReq, HeartbeatReq, SubmitReq, SubmitFailReq, VerifyReq, AdminResetReq,
    WorkerPollReq, DirectiveReq, WorkPatchReq, AntiPatternNotifyReq, RedmineNoteReq
)
from .persistence import (
    TaskIndex, _project_root, _tasks_dir, _archive_dir, _log_dir, _tq_log,
    _bootstrap_log_rotation, _atomic_write, _read_md, _git_repo, _slugify
)
from .logic import (
    register_work, register_task, claim_task, heartbeat, poll_worker,
    submit_result, submit_fail, verify_task, cancel_task, admin_reset,
    push_worker_directive, update_work_meta, get_work_summary,
    rebase_pending_tasks_in_work, recover_stuck_works, reverify_task,
    find_active_duplicates,
)
from ..auth import BearerAuthMiddleware, auth_headers, load_token
from .reclaim import _verify_loop, _reclaim_loop



# ─────────────────────────────────────────
# HTTP 서버 (--serve)
# ─────────────────────────────────────────

def _run_http_server(root: Path, port: int, host: str, lease_seconds: int = 1200):
    from fastapi import FastAPI, HTTPException
    import uvicorn

    # 데몬 부팅 — 기존 동일-날짜 로그가 있으면 _N 접미사로 백업 후 새 파일 생성
    _bootstrap_log_rotation(root)

    app = FastAPI(title="task_queue")

    # 🔴 인증 (PLAN §9.5.6). 토큰이 없으면 여기서 예외가 나고 데몬이 뜨지 않는다.
    #    `/api/v1/health` 는 work/task 개수를 드러내므로 **인증 뒤에** 둔다.
    _auth_token = load_token()

    @app.get("/livez")
    def livez():
        """인증 없이 열린 유일한 경로. 살아 있다는 것 외에는 아무것도 알려주지 않는다."""
        return {"ok": True}

    idx = TaskIndex(root)
    idx.rebuild()
    _tq_log(f"[serve] starting on {host}:{port}, root={root}, indexed works={len(idx.works)} tasks={len(idx.tasks)}", root)

    # 부팅 시 stuck work 자동 복구 — 이전 버전이 failed task 때문에 ready_for_review 로
    # flip 못했던 work 들을 새 terminal-카운트 로직으로 회복. 1회성, lock 안에서 빠르게.
    recovered = recover_stuck_works(idx)
    if recovered:
        _tq_log(f"[boot-recover] {len(recovered)}개 stuck work 자동 복구 트리거: {recovered}", root)

    stop_event = threading.Event()
    reclaim_thread = threading.Thread(
        target=_reclaim_loop, args=(idx, lease_seconds, 30, stop_event), daemon=True
    )
    reclaim_thread.start()
    # 자동 verify 데몬 — submitted 가 쌓이면 30초마다 master_orch --verify-all 호출
    verify_thread = threading.Thread(
        target=_verify_loop, args=(idx, 30, stop_event), daemon=True
    )
    verify_thread.start()

    @app.get("/api/v1/health")
    def health():
        return {"ok": True, "service": "task_queue", "works": len(idx.works), "tasks": len(idx.tasks)}

    @app.post("/api/v1/works")
    def register_work_ep(req: WorkRegisterReq):
        return register_work(idx,
            title=req.title, target_repo=req.target_repo,
            reference_repo=req.reference_repo, target_branch=req.target_branch,
            branch_isolation=req.branch_isolation, created_branch_at=req.created_branch_at,
            original_request=req.original_request, decomposition=req.decomposition,
            max_extensions_per_work=req.max_extensions_per_work, slug=req.slug,
            review_scheduled=req.review_scheduled,
            distribution_mode=req.distribution_mode,
            force_duplicate=req.force_duplicate)

    @app.get("/api/v1/works/duplicates")
    def find_duplicates_ep(slug: str = "", title: str = "", target_repo: str = ""):
        """동일 slug + target_repo 의 active work 사전 조회 — /distribute Step 0.5 용.
        slug 가 비었으면 title 로부터 산출."""
        eff_slug = slug or _slugify(title)
        if not eff_slug or not target_repo:
            raise HTTPException(400, "slug (or title) and target_repo are required")
        dups = find_active_duplicates(idx, slug=eff_slug, target_repo=target_repo)
        return {"slug": eff_slug, "target_repo": target_repo, "duplicates": dups}

    @app.get("/api/v1/works")
    def list_works():
        return list(idx.works.values())

    @app.get("/api/v1/works/{work_id}")
    def get_work(work_id: str):
        w = idx.works.get(work_id)
        if not w:
            raise HTTPException(404, "work not found")
        tasks = [t for t in idx.tasks.values() if t.get("work_id") == work_id]
        return {"work": w, "tasks": tasks}

    @app.patch("/api/v1/works/{work_id}")
    def patch_work_ep(work_id: str, req: WorkPatchReq):
        r = update_work_meta(idx, work_id,
                             merge_status=req.merge_status,
                             redmine_issue_id=req.redmine_issue_id,
                             review_decision=req.review_decision)
        if not r.get("ok"):
            raise HTTPException(404, r.get("error", "patch failed"))
        return r

    @app.get("/api/v1/works/{work_id}/summary")
    def work_summary_ep(work_id: str):
        r = get_work_summary(idx, work_id)
        if not r.get("ok"):
            raise HTTPException(404, r.get("error", "summary failed"))
        return r

    @app.post("/api/v1/works/{work_id}/rebase-pending")
    def rebase_pending_ep(work_id: str, payload: dict):
        """매 verify-merge 후 master_orchestrator 가 호출.
        body: {"base_commit": "<hash>"} — pending/needs_revision task 들의 base 갱신."""
        new_base = (payload or {}).get("base_commit") or ""
        r = rebase_pending_tasks_in_work(idx, work_id, new_base)
        if not r.get("ok"):
            raise HTTPException(400, r.get("error", "rebase failed"))
        return r

    @app.post("/api/v1/tasks")
    def register_task_ep(req: TaskRegisterReq):
        result = register_task(idx,
            work_id=req.work_id, type=req.type, task_data=req.task_data,
            base_commit=req.base_commit, target_file=req.target_file,
            header_file=req.header_file, depends_on=req.depends_on,
            hierarchy_level=req.hierarchy_level, priority=req.priority,
            stem=req.stem, origin=req.origin, parent_attempt=req.parent_attempt,
            requires=req.requires)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "register failed"))
        return result

    @app.post("/api/v1/tasks/claim")
    def claim_ep(req: ClaimReq):
        t = claim_task(idx, req.worker_id, verify_capable=req.verify_capable,
                       capabilities=req.capabilities)
        if t is None:
            raise HTTPException(204, "no available task")
        return t

    @app.post("/api/v1/tasks/{task_id}/heartbeat")
    def heartbeat_ep(task_id: str, req: HeartbeatReq):
        r = heartbeat(idx, task_id, req.worker_id)
        if not r.get("ok"):
            raise HTTPException(r.get("code", 409), r.get("error", "heartbeat failed"))
        return r

    @app.post("/api/v1/tasks/{task_id}/submit")
    def submit_ep(task_id: str, req: SubmitReq):
        r = submit_result(idx, task_id,
            branch=req.branch, head_commit=req.head_commit,
            self_check=req.self_check, escalation_questions=req.escalation_questions,
            metrics=req.metrics, epoch=req.epoch)
        if not r.get("ok"):
            raise HTTPException(409, r.get("error"))
        return r

    @app.post("/api/v1/tasks/{task_id}/submit-fail")
    def submit_fail_ep(task_id: str, req: SubmitFailReq):
        r = submit_fail(idx, task_id, req.reason, req.detail)
        if not r.get("ok"):
            raise HTTPException(409, r.get("error"))
        return r

    @app.post("/api/v1/tasks/{task_id}/verify")
    def verify_ep(task_id: str, req: VerifyReq):
        r = verify_task(idx, task_id, passed=req.passed, feedback=req.feedback,
                        result=req.result, new_base_commit=req.new_base_commit,
                        verify_epoch=req.verify_epoch)
        if not r.get("ok"):
            raise HTTPException(409, r.get("error"))
        return r

    @app.get("/api/v1/tasks/{task_id}")
    def get_task_ep(task_id: str):
        t = idx.tasks.get(task_id)
        if not t:
            raise HTTPException(404, "task not found")
        return t

    @app.get("/api/v1/tasks")
    def list_tasks_ep(status: str = "", work_id: str = "", limit: int = 200):
        tasks = list(idx.tasks.values())
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if work_id:
            tasks = [t for t in tasks if t.get("work_id") == work_id]
        tasks.sort(key=lambda t: (t.get("work_id", ""), int(t.get("hierarchy_level", 0)), t.get("created", "")))
        return tasks[:limit]

    @app.get("/api/v1/status")
    def status_ep():
        out: dict[str, int] = {}
        for t in idx.tasks.values():
            s = t.get("status", "unknown")
            out[s] = out.get(s, 0) + 1
        return {"tasks_by_status": out, "works": len(idx.works), "tasks": len(idx.tasks)}

    @app.post("/api/v1/tasks/{task_id}/cancel")
    def cancel_ep(task_id: str):
        r = cancel_task(idx, task_id)
        if not r.get("ok"):
            raise HTTPException(404, r.get("error"))
        return r

    @app.post("/api/v1/tasks/{task_id}/reverify")
    def reverify_ep(task_id: str):
        """failed → submitted flip. verify-loop 가 다음 사이클에 재검증."""
        r = reverify_task(idx, task_id)
        if not r.get("ok"):
            raise HTTPException(409, r.get("error"))
        return r

    @app.post("/api/v1/admin/reset")
    def admin_reset_ep(req: AdminResetReq):
        return admin_reset(idx, purge=req.purge, cleanup_branches=req.cleanup_branches)

    @app.post("/api/v1/workers/{worker_id}/poll")
    def worker_poll_ep(worker_id: str, req: WorkerPollReq):
        # URL path 의 worker_id 가 권위 — body 의 worker_id 는 검증용
        if req.worker_id and req.worker_id != worker_id:
            raise HTTPException(400, "worker_id mismatch (path vs body)")
        r = poll_worker(idx, worker_id)
        if not r.get("ok"):
            raise HTTPException(400, r.get("error", "poll failed"))
        return r

    @app.post("/api/v1/admin/workers/{worker_id}/directive")
    def push_directive_ep(worker_id: str, req: DirectiveReq):
        r = push_worker_directive(idx, worker_id, req.directive)
        if not r.get("ok"):
            raise HTTPException(400, r.get("error", "directive failed"))
        return r

    @app.post("/api/v1/redmine/note")
    def redmine_note_ep(req: RedmineNoteReq):
        """🔴 검수 흐름의 Redmine 갱신을 **마스터가 대신** 한다.

        원전은 리더 PC 의 `config.json` 에 API 키를 두고 직접 쓴다. 우리 키는 마스터의
        컨테이너 DB 에만 있으므로(§10.1) 요청자는 본문만 만들고 이 자리를 부른다.
        🔴 **키 값은 응답·로그 어디에도 나가지 않는다** — 결과 문장만 돌려준다.
        """
        from ..redmine import update_issue
        result = update_issue(req.issue_id, notes=req.notes,
                              status_name=req.status_name, done_ratio=req.done_ratio)
        _tq_log(f"[redmine] #{req.issue_id} work={req.work_id or '-'} → {result}", root)
        # ⚠️ 실패해도 200 이다 — 검수 흐름을 막지 않는다. 🔴 다만 `ok` 로 **말은 한다**
        #    (조용한 실패 금지). 호출자가 사람에게 그대로 보여 준다.
        return {"ok": not result.startswith("⚠️"), "result": result,
                "issue_id": req.issue_id}

    @app.post("/api/v1/anti_patterns/notify")
    def anti_patterns_notify_ep(req: AntiPatternNotifyReq):
        """리더가 머지한 _distribute_failures.md 신규 엔트리 알림.

        finalize_work_impl 가 머지 commit 에서 .claude/recipes/_distribute_failures.md
        변경 감지 시 호출. 서버는 audit log + tasks 폴더의 누적 노트 파일에 한 줄 append.
        """
        from datetime import datetime as _dt
        ts = _dt.now().isoformat(timespec='seconds')
        titles_join = ", ".join(req.titles) if req.titles else "(헤더 없음)"
        _tq_log(f"[anti-pattern] work={req.work_id} commit={req.commit_sha[:8] if req.commit_sha else '-'} "
                f"titles={titles_join} summary={req.summary[:120]!r}", root)
        # audit log 파일에 한 줄 누적
        try:
            audit_fp = _tasks_dir(root) / "_anti_patterns_audit.md"
            header = ""
            if not audit_fp.exists():
                header = ("# Anti-Pattern Audit Log\n\n"
                         "리더가 review 단계에서 발견·수정 후 메인 머지한 분산 워커 함정 기록.\n"
                         "각 줄은 work_id, commit, 추가 엔트리 제목.\n\n")
            line = (f"- `{ts}` work=`{req.work_id}` commit=`{req.commit_sha[:8] if req.commit_sha else '-'}` "
                    f"entries={titles_join}"
                    + (f" — {req.summary}" if req.summary else "")
                    + "\n")
            with open(audit_fp, 'a', encoding='utf-8') as f:
                if header:
                    f.write(header)
                f.write(line)
        except Exception as e:
            _tq_log(f"[anti-pattern] audit log write 실패: {e}", root)
        return {"ok": True, "work_id": req.work_id, "logged_at": ts,
                "titles_count": len(req.titles)}

    @app.get("/api/v1/admin/workers")
    def list_workers_ep():
        with idx.lock:
            # 최근 접촉 워커 (last_seen / 큐 잔여) + 현재 lease 보유 워커
            seen_ids = set(idx.worker_last_seen.keys()) | set(idx.worker_directives.keys())
            for t in idx.tasks.values():
                wid = t.get("worker_id")
                if wid:
                    seen_ids.add(wid)
            rows = []
            for wid in sorted(seen_ids):
                active_tasks = [t["task_id"] for t in idx.tasks.values()
                                if t.get("worker_id") == wid and t.get("status") == "claimed"]
                rows.append({
                    "worker_id": wid,
                    "last_seen": idx.worker_last_seen.get(wid),
                    "directives_pending": list(idx.worker_directives.get(wid) or []),
                    "active_tasks": active_tasks,
                    # PLAN §5.2-C — 마지막 claim 때 신고한 능력. "왜 이 잡을 아무도 안 집나"
                    # 를 진단하는 첫 단서다 (능력 미달 skip 은 로그에만 남는다).
                    "capabilities": idx.worker_capabilities.get(wid, []),
                })
            return {"workers": rows, "count": len(rows)}

    print(f"task_queue serving at http://{host}:{port} (root={root})")
    try:
        # 🔴 라우트를 전부 등록한 **뒤** 감싼다.
        uvicorn.run(BearerAuthMiddleware(app, _auth_token),
                    host=host, port=port, log_level="info")
    finally:
        stop_event.set()


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def _cli_status(root: Path):
    idx = TaskIndex(root)
    idx.rebuild()
    print(f"Root: {root}")
    print(f"Works: {len(idx.works)}, Tasks: {len(idx.tasks)}")
    by_status: dict[str, int] = {}
    for t in idx.tasks.values():
        s = t.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    for s in ("pending", "claimed", "submitted", "verified", "failed",
              "awaiting_dependency", "cancelled", "stuck"):
        print(f"  {s:24s}: {by_status.get(s, 0)}")


def _cli_reset(root: Path, purge: bool = False, port: int = 8101, cleanup_branches: bool = False):
    """task_queue 비우기 + (선택) feature/worker 브랜치 삭제. 데몬 떠있으면 HTTP, 아니면 직접."""
    payload = {"purge": purge, "cleanup_branches": cleanup_branches}
    try:
        import urllib.request as _ur
        body = json.dumps(payload).encode("utf-8")
        req = _ur.Request(f"http://localhost:{port}/api/v1/admin/reset",
                          data=body, headers={"Content-Type": "application/json", **auth_headers()},
                          method="POST")
        with _ur.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"[via daemon @{port}] {json.dumps(result, ensure_ascii=False, indent=2)}")
            return
    except Exception:
        pass
    print(f"[direct] daemon not responding on :{port}, performing file ops directly")
    idx = TaskIndex(root)
    idx.rebuild()
    result = admin_reset(idx, purge=purge, cleanup_branches=cleanup_branches)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_reverify(root: Path, task_id: str, port: int = 8101):
    """failed → submitted flip. 데몬 떠있으면 HTTP, 아니면 직접 디스크."""
    try:
        import urllib.request as _ur
        body = json.dumps({}).encode("utf-8")
        req = _ur.Request(f"http://localhost:{port}/api/v1/tasks/{task_id}/reverify",
                          data=body, headers={"Content-Type": "application/json", **auth_headers()},
                          method="POST")
        with _ur.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"[via daemon @{port}] {json.dumps(result, ensure_ascii=False, indent=2)}")
            return
    except Exception:
        pass
    print(f"[direct] daemon not responding on :{port}, performing file ops directly")
    idx = TaskIndex(root)
    idx.rebuild()
    result = reverify_task(idx, task_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_send_directive(worker_id: str, directive: str, port: int = 8101):
    """관리자 → 데몬 → 워커 directive push. 데몬 떠있어야 함 (in-memory 큐)."""
    if directive not in _VALID_DIRECTIVES:
        print(f"invalid directive: {directive} (allowed: {','.join(_VALID_DIRECTIVES)})")
        sys.exit(2)
    try:
        import urllib.request as _ur
        body = json.dumps({"directive": directive}).encode("utf-8")
        req = _ur.Request(f"http://localhost:{port}/api/v1/admin/workers/{worker_id}/directive",
                          data=body, headers={"Content-Type": "application/json", **auth_headers()},
                          method="POST")
        with _ur.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"daemon not responding on :{port} or push failed: {e}")
        print("note: directive 큐는 in-memory 라 데몬 떠있어야 동작함")
        sys.exit(1)


def _cli_list_workers(port: int = 8101):
    try:
        import urllib.request as _ur
        _req = _ur.Request(f"http://localhost:{port}/api/v1/admin/workers",
                           headers=auth_headers())
        with _ur.urlopen(_req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        rows = result.get("workers") or []
        if not rows:
            print("(no known workers)")
            return
        print(f"{'worker_id':<32s} {'last_seen':<26s} {'active':<10s} pending")
        for r in rows:
            print(f"{r['worker_id']:<32s} {(r.get('last_seen') or '-'):<26s} "
                  f"{','.join(r.get('active_tasks') or []) or '-':<10s} "
                  f"{','.join(r.get('directives_pending') or []) or '-'}")
    except Exception as e:
        print(f"daemon not responding on :{port}: {e}")
        sys.exit(1)


def _cli_list(root: Path, status: str = ""):
    idx = TaskIndex(root)
    idx.rebuild()
    tasks = list(idx.tasks.values())
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if not tasks:
        print("(no tasks)")
        return
    tasks.sort(key=lambda t: (t.get("work_id", ""),
                              int(t.get("hierarchy_level", 0)),
                              t.get("created", "")))
    for t in tasks:
        target = t.get("target_file") or t.get("header_file") or "-"
        print(f"  {t.get('task_id','-'):10s} {t.get('status','-'):20s} "
              f"L{t.get('hierarchy_level',0)} work={t.get('work_id','-'):28s} "
              f"target={target}")


def main():
    args = sys.argv[1:]
    if not args:
        # MCP stdio 모드 — Claude Code 가 자식 프로세스로 spawn
        # 부팅 시 1회 rotate (기존 동일-날짜 로그를 _N 으로 백업)
        _bootstrap_log_rotation(_project_root())
        # cold boot 진단용 부팅 완료 로그
        _tq_log(f"[boot] stdio MCP ready (exe={sys.executable})", _project_root())
        # 지연 import — `mcp` 패키지는 stdio 모드에서만 필요하다. systemd 로 도는
        # 주 모드(--serve)가 MCP SDK 미설치로 기동 실패하지 않게 한다.
        from .mcp_server import run_stdio
        run_stdio()
        return
    cmd = args[0]
    if cmd == "--serve":
        if len(args) < 2:
            print("usage: task_queue --serve <project_root> [port=8101] [host=0.0.0.0]")
            sys.exit(1)
        root = Path(args[1]).resolve()
        port = int(args[2]) if len(args) > 2 else 8101
        host = args[3] if len(args) > 3 else "0.0.0.0"
        _run_http_server(root, port, host)
    elif cmd == "--status":
        if len(args) < 2:
            print("usage: task_queue --status <project_root>")
            sys.exit(1)
        _cli_status(Path(args[1]).resolve())
    elif cmd == "--list":
        if len(args) < 2:
            print("usage: task_queue --list <project_root> [status]")
            sys.exit(1)
        root = Path(args[1]).resolve()
        st = args[2] if len(args) > 2 else ""
        _cli_list(root, st)
    elif cmd == "--reset":
        if len(args) < 2:
            print("usage: task_queue --reset <project_root> [--purge] [--cleanup-branches] [--port <port>]")
            print("  기본: <project_root>/.claude/tasks/<work>/* 를 _archive/_purge_<ts>/ 로 이동")
            print("  --purge: archive 없이 완전 삭제")
            print("  --cleanup-branches: archive 대상 work 들의 feature 브랜치 + 모든 worker/* 브랜치 삭제 (로컬 + 원격)")
            print("  --port: 데몬이 8101 외 포트면 명시 (기본 8101)")
            sys.exit(1)
        root = Path(args[1]).resolve()
        purge = "--purge" in args[2:]
        cleanup_branches = "--cleanup-branches" in args[2:]
        port = 8101
        if "--port" in args[2:]:
            i = args.index("--port")
            if i + 1 < len(args):
                port = int(args[i + 1])
        _cli_reset(root, purge=purge, port=port, cleanup_branches=cleanup_branches)
    elif cmd == "--reverify":
        if len(args) < 3:
            print("usage: task_queue --reverify <project_root> <task_id> [--port <port>]")
            print("  failed task 를 submitted 로 flip — verify-loop 가 다음 사이클에 재검증.")
            print("  데몬이 떠있으면 HTTP, 아니면 디스크 직접 (이 경우 데몬 재기동 필요).")
            sys.exit(1)
        root = Path(args[1]).resolve()
        task_id = args[2]
        port = 8101
        if "--port" in args[3:]:
            i = args.index("--port")
            if i + 1 < len(args):
                port = int(args[i + 1])
        _cli_reverify(root, task_id, port=port)
    elif cmd == "--send-directive":
        if len(args) < 3:
            print("usage: task_queue --send-directive <worker_id> <directive> [--port <port>]")
            print(f"  directive: {' | '.join(_VALID_DIRECTIVES)}")
            sys.exit(1)
        worker_id = args[1]
        directive = args[2]
        port = 8101
        if "--port" in args[3:]:
            i = args.index("--port")
            if i + 1 < len(args):
                port = int(args[i + 1])
        _cli_send_directive(worker_id, directive, port=port)
    elif cmd == "--list-workers":
        port = 8101
        if "--port" in args[1:]:
            i = args.index("--port")
            if i + 1 < len(args):
                port = int(args[i + 1])
        _cli_list_workers(port=port)
    else:
        print(f"unknown command: {cmd}")
        print("commands: --serve, --status, --list, --reset, --reverify, --send-directive, --list-workers  (no args = MCP stdio)")
        sys.exit(1)


if __name__ == "__main__":
    main()
