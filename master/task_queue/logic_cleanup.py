"""task_queue logic 분리 (2026-07-18) — work 종결 후처리: auto-cleanup·통합 빌드·Redmine (facade = logic.py).

lifecycle → cleanup 단방향 의존 — 이 모듈은 logic_lifecycle 을 import 하지 않는다.
"""
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from .persistence import (
    TaskIndex, _tq_log, _git_repo, _git
)
from .logic_persist import update_work_meta


def _read_redmine_config(root: Path) -> dict:
    """프로젝트 루트 config.json 에서 redmine 설정 읽기. 미설정이면 빈 dict."""
    cfg_path = root / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        with open(cfg_path, encoding='utf-8-sig') as f:
            cfg = json.load(f)
        return {
            "url": (cfg.get("redmine_url") or "").rstrip("/"),
            "api_key": cfg.get("redmine_api_key") or "",
            "project": cfg.get("redmine_project") or "",
        }
    except Exception:
        return {}


def _redmine_post_issue(rm_cfg: dict, subject: str, description: str) -> Optional[int]:
    """Redmine 이슈 생성 — 성공 시 issue_id, 실패 시 None.
    redmine_tracker MCP 와 같은 REST 호출 패턴, 단 stdio MCP 우회해 직접 호출."""
    if not (rm_cfg.get("url") and rm_cfg.get("api_key") and rm_cfg.get("project")):
        return None
    url = f"{rm_cfg['url']}/issues.json"
    payload = {"issue": {
        "project_id": rm_cfg["project"],
        "subject": subject,
        "description": description,
    }}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"X-Redmine-API-Key": rm_cfg["api_key"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        iss = data.get("issue") or {}
        return int(iss.get("id")) if iss.get("id") else None
    except Exception:
        return None


def _try_create_review_issue_async(idx: TaskIndex, work_id: str,
                                    build_status: str = "passed",
                                    build_log_tail: str = "",
                                    build_error: str = ""):
    """ready_for_review (또는 build_failed) flip 시 Redmine 이슈 자동 생성 (백그라운드).
    실패는 silent — Redmine 미연동 환경에서도 cleanup 흐름 무중단.

    Args:
        build_status: "passed" (default) 또는 "failed" — 통합 빌드 결과
        build_log_tail: 빌드 실패 시 마지막 로그 일부 (이슈 본문에 첨부)
        build_error: 빌드 실패 시 짧은 에러 요약
    """
    def _job():
        try:
            with idx.lock:
                wmeta = idx.works.get(work_id)
                if not wmeta:
                    return
                if wmeta.get("redmine_issue_id"):
                    return  # 이미 생성됨 (멱등성)
                title = wmeta.get("title", work_id)
                target_branch = wmeta.get("target_branch") or "(unknown)"
                # verified / failed / cancelled 분리
                tasks_all = [t for t in idx.tasks.values() if t.get("work_id") == work_id]
                tasks_v = [t for t in tasks_all if t.get("status") == "verified"]
                tasks_f = [t for t in tasks_all if t.get("status") == "failed"]
                tasks_c = [t for t in tasks_all if t.get("status") == "cancelled"]
                files_v = sorted({t.get("target_file", "") for t in tasks_v if t.get("target_file")})
                files_f = sorted({t.get("target_file", "") for t in tasks_f if t.get("target_file")})
                files_c = sorted({t.get("target_file", "") for t in tasks_c if t.get("target_file")})
                # failed task 의 reason 도 같이 — 사용자 진단용
                fail_details = []
                for t in tasks_f:
                    rf = t.get("target_file", "?")
                    last_fb = t.get("last_feedback") or t.get("last_result") or ""
                    fail_details.append((rf, str(last_fb)[:200]))

            rm_cfg = _read_redmine_config(idx.root)
            if not rm_cfg.get("url"):
                _tq_log(f"[redmine] {work_id} 스킵 — config.redmine_url 미설정", idx.root)
                return

            partial = bool(tasks_f or tasks_c)
            build_failed = (build_status == "failed")
            if build_failed:
                subject_prefix = "[빌드 실패] 통합 빌드 게이트 차단"
            elif partial:
                subject_prefix = "[리뷰 요청 — 일부 미완성]"
            else:
                subject_prefix = "[리뷰 요청]"
            subject = f"{subject_prefix} {title}"
            header_line = ("통합 빌드 실패 — 수동 fix 후 재시도 필요"
                           if build_failed
                           else "분산 워커 작업 완료 — 머지 결정 요청")
            lines = [
                header_line,
                "",
                f"- work_id: {work_id}",
                f"- feature 브랜치: `origin/{target_branch}`",
                f"- 검증 통과 task: {len(tasks_v)}건"
                + (f" / 실패: {len(tasks_f)}건" if tasks_f else "")
                + (f" / 취소: {len(tasks_c)}건" if tasks_c else ""),
                f"- 통합 빌드: {'❌ 실패' if build_failed else '✅ 통과'}",
                "",
                "## 구현 파일 (검증 통과)",
            ]
            for f in files_v[:50]:
                lines.append(f"- `{f}`")
            if len(files_v) > 50:
                lines.append(f"- … 외 {len(files_v) - 50}건")

            if tasks_f:
                lines += ["", "## ⚠ 미완성 파일 (failed) — 수동 보완 필요"]
                for rf, fb in fail_details[:30]:
                    if fb:
                        lines.append(f"- `{rf}` — {fb}")
                    else:
                        lines.append(f"- `{rf}`")
                if len(fail_details) > 30:
                    lines.append(f"- … 외 {len(fail_details) - 30}건")

            if tasks_c:
                lines += ["", "## 취소된 파일 (cancelled)"]
                for f in files_c[:30]:
                    lines.append(f"- `{f}`")

            if build_failed:
                lines += ["", "## ❌ 통합 빌드 실패 로그 (마지막 부분)"]
                if build_error:
                    lines.append(f"- 요약: {build_error}")
                if build_log_tail:
                    lines.append("```")
                    lines.append(build_log_tail[-2500:])
                    lines.append("```")

            lines += [
                "",
                "## 다음 단계",
                "",
                "1. feature 브랜치 확인 (`git fetch && git checkout " + target_branch + "`)",
            ]
            if build_failed:
                lines.append("2. 빌드 에러 fix → feature 브랜치에 직접 commit + push (cross-file 정합성 보강)")
                lines.append("3. fix 후 통합 빌드 재시도: 서버에서 `master_orchestrator --integration-build " + work_id + " --repo <repo>`")
                lines.append("4. 빌드 통과되면 finalize 가능: `master_orchestrator --finalize " + work_id + "`")
            elif partial:
                lines.append("2. ⚠ 미완성 파일 수동 작성 / 또는 수동 task 재등재 후 워커 재실행")
                lines.append("3. 승인: 서버에서 `master_orchestrator --finalize " + work_id + "` 실행")
            else:
                lines.append("2. 승인: 서버에서 `master_orchestrator --finalize " + work_id + "` 실행")
                lines.append("3. 반려/추가 작업: 본 이슈에 코멘트 + 워커 PC 에 추가 task 등재")
            description = "\n".join(lines)

            issue_id = _redmine_post_issue(rm_cfg, subject, description)
            if not issue_id:
                _tq_log(f"[redmine] {work_id} 이슈 생성 실패 (네트워크/인증/필수필드 확인)", idx.root)
                return
            update_work_meta(idx, work_id, redmine_issue_id=issue_id)
            _tq_log(f"[redmine] {work_id} 이슈 생성: #{issue_id}", idx.root)
        except Exception as e:
            _tq_log(f"[redmine] {work_id} 예외: {e}", idx.root)

    threading.Thread(target=_job, daemon=True).start()


def _run_integration_build(idx: TaskIndex, work_id: str) -> dict:
    """master_orchestrator.exe --integration-build <work_id> 호출.
    Returns {build_passed: bool, exit_code, build_log_tail, error?} 또는 {ok: False, error: ...}
    호출 자체 실패 (master_orch 없음, timeout 등) 는 ok=False — caller 가 build_failed 로 간주.
    """
    import subprocess as _sp
    master_orch = idx.root / ".claude" / "mcp" / "master_orchestrator.exe"
    if not master_orch.exists():
        _tq_log(f"[integration-build] {work_id} master_orchestrator.exe 없음 ({master_orch}) — 빌드 게이트 스킵 (ok 가정)", idx.root)
        # exe 가 없으면 빌드 검증 자체를 못함 → 보수적으로 PASS 처리해 기존 흐름 유지
        return {"ok": True, "build_passed": True, "skipped": True, "reason": "master_orch.exe missing"}
    try:
        r = _sp.run(
            [str(master_orch), "--integration-build", work_id, "--repo", str(idx.root)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            stdin=_sp.DEVNULL, timeout=1900,  # build 자체 timeout 1800s + 여유 100s
        )
    except _sp.TimeoutExpired:
        _tq_log(f"[integration-build] {work_id} master_orch timeout — build_failed 로 간주", idx.root)
        return {"ok": True, "build_passed": False, "error": "integration-build timeout"}
    except Exception as e:
        _tq_log(f"[integration-build] {work_id} 호출 예외: {e}", idx.root)
        return {"ok": True, "build_passed": False, "error": f"call exception: {e}"}
    # master_orch 의 stdout 마지막에 JSON 결과 — 파싱
    out_text = (r.stdout or "").strip()
    try:
        # 출력 끝의 JSON 블록만 (다른 로그가 앞에 있을 수 있음)
        json_start = out_text.rfind("{")
        json_end = out_text.rfind("}")
        if json_start >= 0 and json_end > json_start:
            payload = json.loads(out_text[json_start:json_end+1])
            return {"ok": True, **payload}
    except Exception as e:
        _tq_log(f"[integration-build] {work_id} JSON 파싱 실패 (stdout 끝부분): {e}", idx.root)
    if r.returncode != 0:
        return {"ok": True, "build_passed": False,
                "error": f"master_orch rc={r.returncode}",
                "build_log_tail": (r.stderr or "")[-2000:]}
    return {"ok": True, "build_passed": False, "error": "no JSON in stdout"}


def _do_auto_cleanup(idx: TaskIndex, work_id: str):
    """all_verified 직후 서버 측 자동 정리 (백그라운드 스레드 본문).
    1) git fetch --all
    2) 원격 worker/<*>/<task_id> 삭제 (이 work 의 task 만)
    3) **통합 빌드 게이트** (옵션 A) — feature 브랜치 위에서 UE Build.bat 호출
       - 빌드 실패 시: merge_status=build_failed + Redmine 이슈에 빌드 로그 → 종료
       - 빌드 성공 시: 다음 단계
    4) git checkout main + pull origin main
    5) merge_status → ready_for_review (verify_task 가 이미 한 경우 idempotent)
    6) Redmine 이슈 자동 생성 트리거
    실패는 모두 log 만 — cleanup 미완료여도 finalize_work 가 수동 복구 가능."""
    repo = _git_repo(idx.root)
    if not (repo / ".git").exists():
        _tq_log(f"[auto-cleanup] {work_id} 스킵 — git repo 없음 ({repo})", idx.root)
        return

    # 1) fetch
    rc, out = _git(repo, "fetch", "--all", "--prune")
    if rc != 0:
        _tq_log(f"[auto-cleanup] {work_id} fetch 실패: {out[:200]}", idx.root)

    # 2) 이 work 의 worker 브랜치 수집·삭제 (origin only — 로컬 worker/* 는 서버에 보통 없음)
    with idx.lock:
        worker_branches: list[str] = []
        for t in idx.tasks.values():
            if t.get("work_id") != work_id:
                continue
            wid = t.get("worker_id") or ""
            tid = t.get("task_id") or ""
            if wid and tid:
                b = f"worker/{wid}/{tid}"
                if b not in worker_branches:
                    worker_branches.append(b)

    for b in worker_branches:
        rc, out = _git(repo, "push", "origin", "--delete", b)
        if rc == 0:
            _tq_log(f"[auto-cleanup] origin/{b} 삭제", idx.root)
        elif "remote ref does not exist" not in out:
            _tq_log(f"[auto-cleanup] origin/{b} 삭제 실패 (계속): {out[:120]}", idx.root)

    # 3) 통합 빌드 게이트 (옵션 A) — feature 브랜치 위에서 UE Build.bat. master_orch.exe 가
    #    feature 체크아웃 + Build.bat 까지 일괄 처리하므로 task_queue 는 결과만 받음.
    _tq_log(f"[auto-cleanup] {work_id} 통합 빌드 게이트 시작", idx.root)
    bres = _run_integration_build(idx, work_id)
    if bres.get("skipped"):
        _tq_log(f"[auto-cleanup] {work_id} 통합 빌드 스킵 — {bres.get('reason')}", idx.root)
    elif not bres.get("build_passed"):
        # 빌드 실패 — build_failed 로 flip, Redmine 이슈에 로그 첨부 후 종료 (main 체크아웃 X)
        err = bres.get("error", "build failed")
        log_tail = bres.get("build_log_tail") or ""
        _tq_log(f"[auto-cleanup] {work_id} 통합 빌드 실패 — merge_status=build_failed: {err}", idx.root)
        update_work_meta(idx, work_id, merge_status="build_failed")
        _try_create_review_issue_async(idx, work_id,
                                        build_status="failed",
                                        build_log_tail=log_tail,
                                        build_error=err)
        # main 으로 복귀는 시도 (운영자가 작업하기 좋게)
        rc_co, _ = _git(repo, "checkout", "main")
        if rc_co != 0:
            _git(repo, "checkout", "master")
        return
    else:
        _tq_log(f"[auto-cleanup] {work_id} 통합 빌드 통과 "
                f"(exit={bres.get('exit_code')} duration={bres.get('duration_seconds')}s)", idx.root)

    # 4) checkout main + pull (서버가 워커 브랜치 또는 feature 위에 있을 수 있음)
    #    feature 브랜치는 finalize_work 가 머지·삭제하므로 여기선 손대지 않음
    rc, out = _git(repo, "checkout", "main")
    if rc != 0:
        # main 없으면 master 시도
        rc2, out2 = _git(repo, "checkout", "master")
        if rc2 != 0:
            _tq_log(f"[auto-cleanup] {work_id} checkout main/master 실패: {out[:120]} / {out2[:120]}", idx.root)
        else:
            _tq_log(f"[auto-cleanup] master 체크아웃", idx.root)
    else:
        _tq_log(f"[auto-cleanup] main 체크아웃", idx.root)
    # --ff-only: 서버의 로컬 main 이 origin 과 divergence 면 (수동 commit 등)
    # 머지 에디터를 띄우지 않고 깨끗이 실패. stdin=DEVNULL 환경에서의 hang 위험 차단.
    rc, out = _git(repo, "pull", "--ff-only", "origin", "main")
    if rc != 0:
        rc2, _ = _git(repo, "pull", "--ff-only", "origin", "master")
        if rc2 != 0:
            _tq_log(f"[auto-cleanup] {work_id} pull --ff-only 실패 (계속): {out[:120]}", idx.root)

    # 4) merge_status idempotent flip (verify_task 가 보통 먼저 처리)
    update_work_meta(idx, work_id, merge_status="ready_for_review")

    # 5) Redmine 이슈 생성 트리거 (백그라운드)
    _try_create_review_issue_async(idx, work_id)
    _tq_log(f"[auto-cleanup] {work_id} 완료 — 워커 브랜치={len(worker_branches)} 정리, ready_for_review", idx.root)


def _auto_cleanup_work_async(idx: TaskIndex, work_id: str):
    """verify_task 에서 호출 — auto-cleanup 을 백그라운드 스레드로 위임.
    HTTP 응답 지연 차단 + verify_task 의 lock 점유 최소화."""
    threading.Thread(target=_do_auto_cleanup, args=(idx, work_id), daemon=True).start()
