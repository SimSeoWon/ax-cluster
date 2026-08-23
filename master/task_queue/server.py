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
    WorkerPollReq, DirectiveReq, WorkPatchReq, AntiPatternNotifyReq, RedmineNoteReq,
    RedmineIssueReq, RedmineLinkCommitReq,
    WriterSignalReq, HistoryReq, AliasReq, NotAClassReq, RecipeSearchReq
)
from . import tagging                      # 라우트별 태그 정책 (#257)
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

    # [중요] 인증 (PLAN §9.5.6). 토큰이 없으면 여기서 예외가 나고 데몬이 뜨지 않는다.
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
        # [중요] **비마운트 프로젝트의 work 는 등재되지 않는다** (§5.5.2 · `#257`).
        #    이 관문이 없던 동안 요청 표면이 열려 있었다 — 등재까지는 다 됐고 훅·색인에서만
        #    막혔다(그래서 「다 막힌다」는 서술이 거짓이었다).
        bad = _mount_gate(req.project, require=True)
        if bad:
            return bad
        return register_work(idx,
            title=req.title, target_repo=req.target_repo, project=req.project,
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
    def list_works(project: str = ""):
        """[중요] `project` 로 거른다 (`#257` · 정책 `TAG`) — 거부하지 않고 **걸러 준다.**

        [주의] 스탬프 없는 옛 work 는 어느 태그로도 빠지지 않는다 — 필터가 그것을 숨기면
        옛 work 가 조회에서 사라진다(같은 호환 규칙: `_paths_for`·claim 필터).
        """
        works = list(idx.works.values())
        want = (project or "").strip()
        if not want:
            return works
        return [w for w in works
                if not (w.get("project") or "").strip()
                or (w.get("project") or "").strip() == want]

    @app.get("/api/v1/works/{work_id}")
    def get_work(work_id: str):
        w = idx.works.get(work_id)
        if not w:
            raise HTTPException(404, "work not found")
        tasks = [t for t in idx.tasks.values() if t.get("work_id") == work_id]
        return {"work": w, "tasks": tasks}

    def _paths_for(work_meta=None, work_id: str = ""):
        """트윈 해석 — [중요] 활성이 아니라 **work 의 프로젝트 스탬프**로 푼다 (#210).

        원전 데몬은 프로젝트 안에 살아 귀속이 물리적이었다. 중앙 큐에서 활성으로 풀면
        미종결 work 를 둔 채 활성을 바꿨을 때 산출물이 다른 프로젝트 트윈에 착지한다.
        스탬프 없는 옛 work 는 활성으로 (호환).

        [중요] **여기는 `#243` 의 마운트 강제를 적용하지 않는다 — 의도된 예외다.** `#210` 이
        *"활성이 아니라 work 의 스탬프로 푼다"* 를 명시적으로 정했고, 그 이유가 정확히 이 함수의
        존재 이유다: 미종결 work 를 둔 채 활성을 바꿨을 때 산출물이 **원래 프로젝트로** 가야 한다.
        [주의] 요청 표면(`thesaurus/*`)과 다른 축이다 — 그쪽은 **요청자가 태그를 고른다**(우회 가능)
        이고, 이쪽은 **큐가 등록 시점에 스탬프한 값**이다. 전자만 강제한다.
        """
        from ..context_search.paths import resolve
        proj = ""
        if work_meta:
            proj = work_meta.get("project") or ""
        elif work_id:
            proj = (idx.works.get(work_id) or {}).get("project") or ""
        return resolve(proj or "")

    @app.patch("/api/v1/works/{work_id}")
    def patch_work_ep(work_id: str, req: WorkPatchReq):
        bad = _stamp_gate(req.project, work_id=work_id)
        if bad:
            return bad
        r = update_work_meta(idx, work_id,
                             merge_status=req.merge_status,
                             redmine_issue_id=req.redmine_issue_id,
                             review_decision=req.review_decision)
        if not r.get("ok"):
            raise HTTPException(404, r.get("error", "patch failed"))
        # 생산자③ (#207) — 종결(merged/rejected)의 사실 기록. [중요] fail-soft: 기록이
        # 죽어도 종결은 성립한다 — 다만 조용히 넘기지 않고 응답과 로그로 말한다.
        if req.merge_status in ("merged", "rejected") and \
                any(c.startswith("merge_status=") for c in r.get("changed", ())):
            try:
                from ..context_synth import history_gen as HG
                tasks = [t for t in idx.tasks.values() if t.get("work_id") == work_id]
                r["history_written"] = HG.record_work_terminal(
                    _paths_for(r.get("work")), r.get("work") or {}, tasks, req.merge_status)
                _tq_log(f"[history] {work_id} {req.merge_status} → "
                        f"{r['history_written']}", root)
            except Exception as e:                           # noqa: BLE001
                r["history_error"] = f"작업 기록 실패: {e}"
                _tq_log(f"[history] [주의] {work_id} 기록 실패: {e}", root)
        return r

    @app.post("/api/v1/history")
    def history_ep(req: HistoryReq):
        """작업 기록 (#207) — 요청자(`.33`) 세션의 비자명한 결정을 받는다.

        `signals` 와 같은 마스터 대행 구조·같은 requester 스코프. 파이프라인 종결 기록은
        위 PATCH 훅이 자동으로 하므로 이 자리는 **사람 주도 작업의 결정**만 온다.
        """
        from ..context_synth import history_gen as HG
        bad = _stamp_gate(req.project, work_id=req.work_id)
        if bad:
            return bad
        # [중요] work 가 없으면 스탬프가 없다 → **마운트를 강제한다**. 그러지 않으면 태그만으로
        #    남의 트윈에 기록이 쌓인다(`#243` 이 시소러스에서 막은 것과 같은 구멍).
        if not req.work_id:
            bad = _mount_gate(req.project, require=True)
            if bad:
                return bad
        try:
            content = HG.render(
                title=req.title, decision_type=req.decision_type,
                work_id=req.work_id, session_id=req.session_id,
                affected_classes=req.affected_classes,
                affected_domains=req.affected_domains, supersedes=req.supersedes,
                alternatives_considered=req.alternatives_considered,
                tags=req.tags, user_quote=req.user_quote, body=req.body)
            stored = HG.write(_paths_for(work_id=req.work_id), content, title=req.title)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:                               # noqa: BLE001
            _tq_log(f"[history] 저장 실패: {e}", root)
            return {"ok": False, "error": f"작업 기록 저장 실패: {e}"}
        _tq_log(f"[history] '{req.title[:60]}' type={req.decision_type} "
                f"work={req.work_id or '-'}", root)
        return {"ok": True, "stored_at": stored, "title": req.title}

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
        # [중요] **워커는 자기 프로젝트의 태스크만 집는다** (`#248`). 태그가 마운트와 다르면
        #    거부하고, 통과하면 그 프로젝트로 후보를 거른다 — 한 기계에 두 프로젝트의
        #    claimer 가 돌아도 남의 태스크를 집지 않는 근거가 여기다.
        # [주의] 태그를 안 보내는 기존 claimer 는 **마운트로 해석된다**(하위 호환) — 스탬프가
        #    없는 옛 work 는 계속 후보다(`_paths_for` 와 같은 호환 규칙).
        bad = _mount_gate(req.project, require=True)
        if bad:
            return bad
        eff_project = (req.project or "").strip() or getattr(_mount_gate, "last", "")
        t = claim_task(idx, req.worker_id, verify_capable=req.verify_capable,
                       capabilities=req.capabilities, types=req.types,
                       project=eff_project)
        if t is None:
            raise HTTPException(204, "no available task")
        return t

    @app.post("/api/v1/tasks/{task_id}/heartbeat")
    def heartbeat_ep(task_id: str, req: HeartbeatReq):
        r = heartbeat(idx, task_id, req.worker_id, note=req.note)
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
    def list_tasks_ep(status: str = "", work_id: str = "", limit: int = 200,
                      project: str = ""):
        tasks = list(idx.tasks.values())
        # [중요] 프로젝트 필터 (`#257` · 정책 `TAG`) — task 는 스탬프를 갖지 않으므로
        #    **그 task 가 속한 work 의 스탬프**로 판정한다. 스탬프 없는 옛 work 는 남긴다.
        want = (project or "").strip()
        if want:
            def _wp(t):
                return ((idx.works.get(t.get("work_id") or "") or {}).get("project") or "").strip()
            tasks = [t for t in tasks if not _wp(t) or _wp(t) == want]
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
        bad = _mount_gate(req.project, require=True)          # claim 과 같은 파견 축이다 (`#248`)
        if bad:
            return bad
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
        """[중요] 검수 흐름의 Redmine 갱신을 **마스터가 대신** 한다.

        원전은 리더 PC 의 `config.json` 에 API 키를 두고 직접 쓴다. 우리 키는 마스터의
        컨테이너 DB 에만 있으므로(§10.1) 요청자는 본문만 만들고 이 자리를 부른다.
        [중요] **키 값은 응답·로그 어디에도 나가지 않는다** — 결과 문장만 돌려준다.
        """
        from ..redmine import update_issue
        result = update_issue(req.issue_id, notes=req.notes,
                              status_name=req.status_name, done_ratio=req.done_ratio)
        _tq_log(f"[redmine] #{req.issue_id} work={req.work_id or '-'} → {result}", root)
        # [주의] 실패해도 200 이다 — 검수 흐름을 막지 않는다. [중요] 다만 `ok` 로 **말은 한다**
        #    (조용한 실패 금지). 호출자가 사람에게 그대로 보여 준다.
        return {"ok": not result.startswith("[주의]"), "result": result,
                "issue_id": req.issue_id}

    # ── Redmine 조회·생성·연결 (#226 위임 구멍 ①) ─────────────────────
    # [중요] **읽기를 8103 에 두지 않았다.** 그 포트의 `/api/v1/*` 는 무인증 공개라(실측
    #    2026-08-20: 토큰 없이 200) 일감 본문·검수 이력이 LAN 아무에게나 열린다. 원전은
    #    리더 PC 가 키를 갖고 직접 읽었고, 우리는 키가 마스터에만 있으니 대행이 그 자리다.
    # [주의] 실패해도 200 + `error` 문장이다 — `redmine/note` 와 같은 관례(조용한 실패 금지,
    #    다만 흐름을 막지 않는다). 호출자가 사람에게 사유를 그대로 보여 준다.

    @app.get("/api/v1/redmine/issues")
    def redmine_issues_ep(status: str = "open", tracker: str = "", fixed_version: str = "",
                          limit: int = 25, offset: int = 0,
                          sort: str = "updated_on:desc", project: str = ""):
        """이슈 목록 (원전 `list_issues`). 기본 `status=open` — 우리 규약에서 「해결」도 열린 것.

        [중요] **읽기도 프로젝트 축을 받는다** (`#293`). 안 주면 AX 인프라 프로젝트를 본다 —
        읽기는 오염이 아니므로 폴백해도 되지만, **무엇을 봤는지 응답에 적는다.**
        """
        from ..redmine import AX_PROJECT_ID, list_issues, project_of
        target = project_of(project) if (project or "").strip() else AX_PROJECT_ID
        if (project or "").strip() and not target:
            return {"error": f"`{project}` 의 config.yaml 에 `redmine.project` 가 없다"}
        out = list_issues(status=status, tracker=tracker, fixed_version=fixed_version,
                          limit=limit, offset=offset, sort=sort, project=target)
        if isinstance(out, dict):
            out["redmine_project"] = target      # 무엇을 봤는지 말한다
        return out

    @app.get("/api/v1/redmine/meta")
    def redmine_meta_ep():
        """상태·트래커·우선순위·버전 카탈로그 (원전 `list_statuses`+`list_trackers` 를 한 번에)."""
        from ..redmine import meta
        return meta()

    @app.get("/api/v1/redmine/issue/{issue_id}")
    def redmine_issue_ep(issue_id: int):
        """이슈 1건 + 노트 이력 (원전 `get_issue`). 없는 번호는 `error` 로 **말한다**."""
        from ..redmine import get_issue
        return get_issue(issue_id)

    @app.post("/api/v1/redmine/issue")
    def redmine_create_issue_ep(req: RedmineIssueReq):
        """이슈 생성 대행 (원전 `create_issue`).

        [중요] **등재 대상은 요청의 프로젝트 태그가 정한다** (`#293`, 사용자 지적 2026-08-24).
        종전 주석은 *"프로젝트는 고정 — 새 프로젝트를 만들지 않는다"* 였는데, 사용자가 정한 것은
        「**AX 인프라 이슈**를 게임 프로젝트와 분리하지 않는다」이고(2026-08-09) 「레드마인
        프로젝트는 하나다」가 아니었다. 게임 프로젝트가 늘면 그 일감의 자리도 늘어난다.
        [주의] **폴백하지 않는다** — `config.yaml` 에 `redmine.project` 가 없으면 거부한다.
        조용히 남의 프로젝트에 쓰면 그것이 오염이다(`#257` 과 같은 판단).
        """
        from ..redmine import create_issue, project_of
        target = project_of(req.project or "")
        if not target:
            return {"error": f"`{req.project or '(태그 없음)'}` 의 config.yaml 에 "
                             "`redmine.project` 가 없다 — 폴백하지 않는다"}
        r = create_issue(req.subject, req.description, tracker_name=req.tracker_name,
                         priority_name=req.priority_name, project=target)
        _tq_log(f"[redmine] 이슈 생성 project={target} → {r}", root)
        return r

    @app.post("/api/v1/redmine/link-commit")
    def redmine_link_commit_ep(req: RedmineLinkCommitReq):
        """커밋 해시 연결 (원전 `link_commit` — 같은 노트 문구 형식)."""
        from ..redmine import link_commit
        result = link_commit(req.issue_id, req.commit_hash, req.message)
        _tq_log(f"[redmine] #{req.issue_id} 커밋 연결 {req.commit_hash[:12]} → {result}", root)
        return {"ok": not result.startswith("[주의]"), "result": result,
                "issue_id": req.issue_id}

    @app.post("/api/v1/signals")
    def writer_signal_ep(req: WriterSignalReq):
        """code-writer 신호 적재 (#206) — 요청자(`.33`) 직접 작업의 과정 휴리스틱을 받는다.

        신호 파일은 마스터의 트윈 디렉토리(`recipes/_signals.jsonl`)에 있으므로 마스터가
        대행한다 (`redmine/note` 와 같은 구조·같은 requester 스코프). 파이프라인 쪽 신호는
        통합자가 직접 적재하므로 이 자리를 지나지 않는다.
        """
        from ..context_synth import signals as SG
        bad = _stamp_gate(req.project, work_id=req.work_id)
        if bad:
            return bad
        if not req.work_id:                     # 스탬프가 없으면 마운트를 강제한다 (위와 같은 규칙)
            bad = _mount_gate(req.project, require=True)
            if bad:
                return bad
        try:
            record = SG.make_record(
                intent=req.intent, queries=req.queries, files_read=req.files_read,
                files_modified=req.files_modified, iterations=req.iterations,
                feedback_notes=req.feedback_notes,
                rejected_approaches=req.rejected_approaches,
                error_recoveries=req.error_recoveries,
                session_id=req.session_id, work_id=req.work_id, source="requester")
            stored = SG.append_signal(_paths_for(work_id=req.work_id), record)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:                               # noqa: BLE001
            # [중요] 조용한 실패 금지 — 신호는 한 번 놓치면 그 작업의 패턴은 다시 안 온다
            _tq_log(f"[signal] 저장 실패: {e}", root)
            return {"ok": False, "error": f"신호 저장 실패: {e}"}
        _tq_log(f"[signal] intent='{record['intent'][:60]}' work={req.work_id or '-'} "
                f"read={len(record['files_read'])} modified={len(record['files_modified'])} "
                f"errors={len(record['error_recoveries'])}", root)
        return {"ok": True, "stored_at": stored, "intent": record["intent"]}

    def _mount_gate(project: str, *, require: bool = False):
        """`MOUNT` 정책 표면의 관문 — 태그가 마운트와 다르면 **거부 응답**을 돌려준다.

        [중요] 경로를 풀지 않는다 — 트윈을 만지지 않는 표면(`claim`·`poll`·`works` 등재)도
        같은 판정을 써야 하므로, 판정과 경로 해석을 갈랐다. 통과면 `None`.
        [주의] 통과하면 해석된 마운트 이름을 `_mount_gate.last` 에 남긴다 — 태그를 안 보낸
        요청의 유효 프로젝트가 그 값이다(레지스트리를 두 번 읽지 않는다).
        [주의] 실측 2026-08-22 — 이 관문이 없어 **요청 표면이 열려 있었다**: 비마운트 프로젝트로
        work 를 등재하고 태스크를 넣을 수 있었다(막힌 것은 훅·색인 쪽뿐이었다).
        """
        from ..context_search.paths import resolve_mounted_only
        from ..projects.config import ConfigError
        if require and not (project or "").strip():
            # [중요] 태그 없음도 거절이다 (사용자 2026-08-22) — 마운트로 「가정」하는 순간
            #    판정 근거 없는 요청이 마운트 트윈에 쌓인다.
            try:
                mounted = resolve_mounted_only("").name
            except ConfigError:
                mounted = ""
            return tagging.reject_untagged(mounted)
        try:
            _mount_gate.last = resolve_mounted_only(project or "").name
            return None
        except ConfigError as e:
            _mount_gate.last = ""
            return tagging.reject(str(e), project=(project or "").strip())

    def _stamp_gate(project: str, work_id: str = "", work_meta=None):
        """`STAMP` 정책 표면의 대조 — 태그가 그 work 의 스탬프와 다르면 거부.

        [중요] **마운트와 비교하지 않는다** (`#210`) — 미종결 work 를 둔 채 활성을 바꿔도
        그 work 의 요청은 계속 처리돼야 한다. 통과면 `None`.
        """
        stamped = ""
        if work_meta:
            stamped = work_meta.get("project") or ""
        elif work_id:
            stamped = (idx.works.get(work_id) or {}).get("project") or ""
        why = tagging.check_stamp(project or "", stamped)
        if why:
            return {"ok": False, "status": "project_mismatch", "reason": why,
                    "project": (project or "").strip(), "work_project": stamped}
        return None

    def _mounted_paths(project: str):
        """요청의 태그를 **마운트와 대조**해 푼다 (`#243`). 거부는 예외로 올린다.

        [중요] **거부 형태는 200 + `ok:false` + 사유**다 (§12.5-c 확정). 409 를 쓰지 않는 이유는
        실측이다 — `ax-client` 는 [미연결] 시 지난 스냅샷으로 폴백하도록 되어 있어 **거절을
        장애로 오인해 낡은 결과를 돌려준다.** 그리고 500 은 더 나쁘다: 사유가 없다.
        [주의] 실측 2026-08-22 — 배선 전에는 `resolve(req.project or "")` 가 태그를 검사 없이
        따라, `project=NS`(비마운트) 요청이 `thesaurus.register` 까지 진입해 `open()` 에서
        **500** 으로 죽었다. 막은 것은 우리 코드가 아니라 systemd 샌드박스였다 —
        **의도된 방어가 아니다.**
        """
        from ..context_search.paths import resolve_mounted_only
        return resolve_mounted_only(project or "")

    @app.post("/api/v1/thesaurus/alias")
    def thesaurus_alias_ep(req: AliasReq):
        """사용자가 확인해 준 별칭을 등록한다 — 요청자(`.33`) 대행 (2026-08-20).

        [중요] **판정을 여기서 다시 하지 않는다.** 범용어 가드(#213)는
        `thesaurus.register` 안에 있고, 두 벌이 되면 다음에 갈라진다 —
        `redmine/note`·`signals` 와 같은 얇은 대행이다.
        [주의] 거부도 **200 + ok:false** 로 말한다. 조용히 무시하면 사용자는 등록된 줄 안다.
        """
        from ..context_search import thesaurus as th
        from ..projects.config import ConfigError
        bad = _mount_gate(req.project, require=True)     # 태그 없음도 거절 (사용자 2026-08-22)
        if bad:
            _tq_log(f"[thesaurus] 거부 — {bad['status']}", root)
            return {**bad, "class": req.class_name, "term": req.term}
        try:
            paths = _mounted_paths(req.project)
        except ConfigError as e:
            _tq_log(f"[thesaurus] 거부 — {e}", root)
            return {"ok": False, "status": "not_mounted", "reason": str(e),
                    "class": req.class_name, "term": req.term, "project": req.project}
        status = th.register(paths, req.class_name, req.term)
        ok = status.startswith("added") or status == "noop"
        _tq_log(f"[thesaurus] alias {req.class_name} ← '{req.term}' "
                f"→ {status.split(':')[0]} ({paths.name})", root)
        return {"ok": ok, "status": status, "class": req.class_name,
                "term": req.term, "project": paths.name}

    @app.post("/api/v1/thesaurus/not-a-class")
    def thesaurus_not_a_class_ep(req: NotAClassReq):
        """`그건 클래스가 아니다` 를 기억한다 — 다음부터 묻지 않는다."""
        from ..context_search import thesaurus as th
        from ..projects.config import ConfigError
        bad = _mount_gate(req.project, require=True)     # 태그 없음도 거절 (사용자 2026-08-22)
        if bad:
            _tq_log(f"[thesaurus] 거부 — {bad['status']}", root)
            return {**bad, "term": req.term}
        try:
            paths = _mounted_paths(req.project)
        except ConfigError as e:
            _tq_log(f"[thesaurus] 거부 — {e}", root)
            return {"ok": False, "status": "not_mounted", "reason": str(e),
                    "term": req.term, "project": req.project}
        status = th.ignore(paths, req.term)
        _tq_log(f"[thesaurus] not-a-class '{req.term}' → {status} ({paths.name})", root)
        return {"ok": status != "not_found", "status": status,
                "term": req.term, "project": paths.name}

    @app.post("/api/v1/recipes/search")
    def recipes_ep(req: RecipeSearchReq):
        """합성된 레시피 검색 — 요청자(`.33`) 대행 (`#267`).

        [중요] **경로 권위는 마스터다.** 레시피는 마스터 트윈(`<프로젝트>/recipes/`)에 있고
        요청자 기계엔 그 디렉토리가 없다 — `signals`·`history` 와 같은 대행 구조다.
        [주의] 읽기인데 마운트를 대조하는 이유: **답의 정확성이 프로젝트에 달렸다.** 남의
        프로젝트 레시피를 돌려주면 빈 결과보다 나쁘다.
        [중요] **읽기인데 POST 인 이유는 질의가 한글이기 때문이다** (사용자 지적 2026-08-23).
        URL 에 넣으면 퍼센트 인코딩으로 저널이 못 읽게 되고 손으로 curl 하면 깨진다 —
        이 저장소 관례도 이미 본문이다(`POST /api/v1/search/combined`).
        """
        from ..context_synth import recipes_read as RR
        from ..projects.config import ConfigError
        try:
            paths = _mounted_paths(req.project)
        except ConfigError as e:
            _tq_log(f"[recipes] 거부 — {e}", root)
            return {"ok": False, "status": "not_mounted", "reason": str(e),
                    "project": req.project}
        out = RR.find(paths, req.query, req.n)
        _tq_log(f"[recipes] '{req.query[:40]}' → {len(out.get('matches') or [])}건 "
                f"(총 {out.get('total_recipes')}) ({paths.name})", root)
        return {**out, "project": paths.name}

    @app.get("/api/v1/anti_patterns")
    def anti_patterns_ep(project: str = ""):
        """안티패턴 카탈로그 — *"이 프로젝트에서 거절당한 접근"* (`#267`).

        [중요] `exists=False` 로 **「없음」을 명시**한다 — 빈 값만 돌려주면 부르는 쪽이
        고장과 구분할 수 없다(원전 규약 그대로).
        """
        from ..context_synth import recipes_read as RR
        from ..projects.config import ConfigError
        try:
            paths = _mounted_paths(project)
        except ConfigError as e:
            _tq_log(f"[anti-pattern] 거부 — {e}", root)
            return {"ok": False, "status": "not_mounted", "reason": str(e),
                    "project": project}
        out = RR.anti_patterns(paths)
        _tq_log(f"[anti-pattern] 카탈로그 조회 exists={out.get('exists')} ({paths.name})", root)
        return {**out, "project": paths.name}

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
        # [중요] 라우트를 전부 등록한 **뒤** 감싼다.
        # 역할 스코프 토큰 (소 3.8.2) — requester 토큰 파일이 있으면 그 스코프의 경로가
        # 열린다. 없으면 닫힌 것이다(fail-closed) — 서비스는 그대로 뜬다(뷰 토큰과 같은 결).
        from ..auth import REQUESTER_SCOPE, WORKER_SCOPE, load_role_token
        _scoped = []
        for _role, _scope in (("requester", REQUESTER_SCOPE), ("worker", WORKER_SCOPE)):
            _tok = load_role_token(_role)
            if _tok:
                _scoped.append((_tok, _scope))
        uvicorn.run(BearerAuthMiddleware(app, _auth_token, scoped=tuple(_scoped)),
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
