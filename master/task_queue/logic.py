import json
import os
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
    _read_redmine_config, _redmine_post_issue, _redmine_add_note,
    _try_create_review_issue_async, create_work_issue_async as _create_work_issue_async,
    _auto_cleanup_work_async,
)


# ─────────────────────────────────────────
# 핵심 로직 (모두 동기. RLock 으로 직렬화)
# ─────────────────────────────────────────

# merge_status 가 이 집합에 들어가면 "이미 종결된 work" 로 간주 — 중복 판정에서 제외.
_TERMINAL_MERGE_STATUSES = {"merged", "rejected", "cancelled"}


class _NotLiveQueue(Exception):
    """테스트용 임시 큐 루트 — 파견 신호를 쓰지 않는다는 표시(제어 흐름 전용)."""


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
            # 🔴 분산 작업은 **여러 라운드**를 돈다 (사용자 2026-09-04). 조각·브랜치 이름이
            #    이 번호를 달고, 공지·전진은 **그 라운드 것만** 본다.
            "round": 1,
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
        # 🔴 **레드마인 이슈는 등재 때 만든다** (사용자 2026-09-04: *"완료시 만들지말고 작업
        #    등재할때 만들라고"*). 라운드 완료·전진·추가 개선·마감이 그 이슈에 노트로 쌓인다.
        #    [주의] 비동기이고 실패해도 등재를 막지 않는다 — 큐가 정본이다.
        _create_work_issue_async(idx, work_id)
        _git_commit_tasks(idx.root, f"[work-register] {work_id}: {title}", [path])
        _update_index_md(idx)
        result = dict(meta)
        result["ok"] = True
        return result


def reopen_work(idx: TaskIndex, *, work_id: str, expected_round: int = 0) -> dict:
    """🔴 **개선요청 — 끝난 라운드의 work 을 다음 라운드로 연다** (사용자 결정 2026-09-05).

    사용자: *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로 말이야"* ·
    *"라운드는 처음 작업 요청할 때는 1이고 … 머지하고 개선 요청을 받은 경우 +1 이 되서
    2 라운드 시작"*.

        등록      round = 1 고정                     `register_work`
        개선요청   round = 현재 + 1                   **여기**
        마감      main 머지 · 큐 merged · 이슈 완료   `review.finalize_work`

    [중요] **`expected_round` 는 명령이 아니라 확인이다.** 값은 이미 정해져 있고(현재+1),
    요청자가 실어 보내는 것은 *"내가 아는 라운드가 이거다"* 라는 대조다. 어긋나면 **거절**한다 —
    맞추지 않는다. 그래야 요청자와 큐가 서로 다른 라운드를 보고 있는 상태가 드러난다.

    [주의] **전진(⑺)이 실제로 있었는지는 보지 않는다** (사용자 2026-09-05:
    *"그건 모두 .33 메인 컴퓨터에서 처리되겠지. 마스터가 왜 신경써"*). 마스터가 판정하는 것은
    **자기가 가진 큐 상태**까지다 — `ready_for_review` 는 조각이 다 끝났다는 큐 자신의 사실이고,
    그 다음 판단은 요청자 몫이다. 여기에 「머지했나」 게이트를 더하면 원전에 없는 계층이 된다.
    """
    if work_id not in idx.works:
        return {"ok": False, "reason": "unknown_work", "error": f"unknown work_id: {work_id}"}
    with idx.lock:
        w = idx.works[work_id]
        cur = int(w.get("round", 1) or 1)
        st = str(w.get("merge_status") or "")
        nxt = cur + 1
        if st != "ready_for_review":
            # [중요] **열어 놓고 조각 등재가 실패한 경우의 재시도를 막지 않는다.** 승격은
            #    조각보다 앞이라, 그 사이에서 죽으면 work 이 `in_progress` · 라운드는 이미
            #    올라간 상태로 남는다. 그때 다시 거절하면 그 work 은 개선요청으로 되살릴 길이
            #    없어진다(마감밖에 안 남는다). **그 라운드 조각이 0건일 때만** 재시도로 본다 —
            #    관측 가능한 조건이고, 도는 중인 라운드에 조각을 밀어 넣는 길은 열리지 않는다.
            n_cur = sum(1 for t in idx.tasks.values()
                        if t.get("work_id") == work_id and int(t.get("round") or 0) == cur)
            if st == "in_progress" and int(expected_round or 0) == cur and n_cur == 0:
                return {"ok": True, "work_id": work_id, "round": cur, "previous_round": cur,
                        "reopened": False,
                        "note": (f"이미 라운드 {cur} 로 열려 있고 그 라운드 조각이 0건이다 — "
                                 f"승격 뒤 등재가 실패한 재시도로 본다"),
                        "target_branch": w.get("target_branch") or "",
                        "redmine_issue_id": w.get("redmine_issue_id") or "",
                        "title": w.get("title") or ""}
            why = ("라운드가 아직 도는 중이다 — 조각이 전부 끝나면 `ready_for_review` 가 된다"
                   if st in ("in_progress", "") else "종결된 work 이다 — 마감된 것은 다시 열지 않는다")
            return {"ok": False, "reason": "not_reopenable",
                    "error": (f"work {work_id} 는 merge_status={st!r} · 라운드 {cur} 다 — "
                              f"개선요청을 받을 수 있는 상태가 아니다. {why}"),
                    "round": cur, "merge_status": st}
        if not int(expected_round or 0):
            return {"ok": False, "reason": "round_required",
                    "error": (f"라운드 값이 없다 — 개선요청은 몇 라운드를 여는지 실어야 한다. "
                              f"work {work_id} 의 다음 라운드는 {nxt} 다"),
                    "round": cur, "next_round": nxt}
        if int(expected_round) != nxt:
            return {"ok": False, "reason": "round_mismatch",
                    "error": (f"라운드가 어긋난다 — 받은 값 {int(expected_round)}, "
                              f"큐가 아는 다음 라운드 {nxt} (현재 {cur}). "
                              f"맞추지 않고 거절한다 — 서로 다른 라운드를 보고 있다는 뜻이다"),
                    "round": cur, "next_round": nxt}
        w["merge_status"] = "in_progress"
        w["round"] = nxt
        # [중요] **이슈 id 는 그대로 둔다** — work 하나에 이슈 하나이고, 라운드는 그 이슈의
        #    노트로 쌓인다 (사용자 2026-09-04). 여기서 버리면 라운드마다 새 이슈가 난다.
        _save_work(idx, work_id)
        _tq_log(f"[work-reopen] {work_id} ready_for_review → in_progress · "
                f"라운드 {cur} → {nxt} (개선요청)"
                + (f" (이슈 #{w['redmine_issue_id']})" if w.get("redmine_issue_id") else ""),
                idx.root)
        return {"ok": True, "work_id": work_id, "round": nxt, "previous_round": cur,
                "reopened": True,
                "target_branch": w.get("target_branch") or "",
                "redmine_issue_id": w.get("redmine_issue_id") or "",
                "title": w.get("title") or ""}


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
        # 🔴 [중요] **라운드 승격은 여기서 하지 않는다 — 개선요청이 명시로 한다**
        #    (사용자 결정 2026-09-05: *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로"*).
        #
        # 종전에는 이 자리에서 `ready_for_review` 를 보고 **조각 등재의 부수효과로** work 을
        # 다시 열고 `round` 를 올렸다. 그래서 등재가 「최초냐 N회차 개선요청이냐」를 **상태로
        # 추론**했고, 상태가 예상 밖이면 조용히 틀렸다:
        #
        #     in_progress 인 work 에 등재   승격 없음 → 새 조각이 **지난 라운드 번호**로 찍혀
        #                                   같은 `r<N>` 브랜치 이름에 섞인다
        #     merged·cancelled 인 work      등재는 성공하고 조각은 pending 에 박힌 뒤,
        #                                   파견 게이트가 영원히 거절한다 (조용한 교착)
        #
        # 이제 승격은 `reopen_work()` **하나뿐**이고(요청자의 개선요청이 부른다), 여기는
        # **거절만 한다.** 라운드는 추론 결과가 아니라 호출이 정한 값이다.
        _w = idx.works[work_id]
        _st = str(_w.get("merge_status") or "")
        _cur = int(_w.get("round", 1) or 1)
        if _st == "ready_for_review":
            return {"ok": False, "reason": "round_closed",
                    "error": (f"work {work_id} 는 라운드 {_cur} 가 끝난 상태다"
                              f"(ready_for_review) — 조각을 더하려면 **개선요청이 먼저다**: "
                              f"`POST /work/improve` (round={_cur + 1})")}
        if _st not in ("in_progress", ""):
            return {"ok": False, "reason": "work_closed",
                    "error": (f"work {work_id} 는 merge_status={_st!r} 다 — 종결된 work 에는 "
                              f"조각을 등재하지 않는다(파견 게이트가 영원히 거절한다)")}
        task_id = _gen_task_id()
        meta = {
            "task_id": task_id,
            "work_id": work_id,
            # [중요] 등재 시점의 라운드를 **조각에 새긴다** — 브랜치 이름과 머지 대상 판정이
            #    이 값에서 나온다. 나중에 work 의 라운드가 올라가도 이 조각은 안 따라간다.
            "round": int(idx.works[work_id].get("round", 1)),
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
        # 🔴 [중요] **등재도 파견 트리거다** (사용자 2026-09-05).
        #
        # 종전 트리거는 **골조 push 하나뿐**이었다. 그래서 요청자가 push 를 먼저 하고 등재를
        # 뒤에 하면(라운드 2 실측 2026-09-05: push 01:35:01 → 등재 01:35:53) 그 push 는
        # *"진행 중인 work 만 민다"* 로 거절되고, 등재 뒤에는 새 push 가 없어 **트리거가 다시
        # 안 울린다.** 그날 조각 3건이 catchup 타이머(10분)를 기다렸고, `.33` 은 그 4분 동안
        # *"아무도 안 집는다"* 만 보고 있었다.
        #
        # [주의] 여기서 **파견하지 않는다** — 신호만 쓴다(`note_trigger` 규약). 골조가 아직
        # 안 올라왔으면 파견 쪽이 *"base 가 원격에 없다"* 로 거절하고 그 사유를 work 에 적는다.
        # 조각 N건이면 같은 파일에 N번 쓰지만 이름이 `<work_id>.json` 이라 합쳐진다.
        try:
            # 🔴 [중요] **라이브 큐일 때만 신호를 쓴다** (실측 2026-09-05 — 이걸 안 갈라서
            #    사고가 났다). 테스트는 임시 루트로 `TaskIndex` 를 만드는데, 신호 경로는
            #    `~/ax-spool/dispatch` 상수라 **테스트가 라이브 스풀에 썼다.** 가짜 work_id
            #    트리거가 파견 유닛을 15초에 다섯 번 깨워 `start-limit-hit` 으로 `.service` 와
            #    `.path` 를 둘 다 죽였고, 그 복구(`reset-failed`)는 NOPASSWD 밖이라 사람 몫이 됐다.
            #    `#345`(테스트가 라이브 큐에 결합)와 **같은 뿌리**다 — 실행 경로가 파일 밖에 있다.
            from pathlib import Path as _P                    # noqa: PLC0415
            _live = _P(os.environ.get("AX_TASK_QUEUE_ROOT") or (_P.home() / "ax-state"))
            if _P(idx.root).resolve() != _live.resolve():
                raise _NotLiveQueue(f"임시 큐 루트({idx.root}) — 신호를 쓰지 않는다")
            from ..work.autodispatch import note_trigger      # noqa: PLC0415
            note_trigger(work_id, str(idx.works[work_id].get("project") or ""),
                         ref="register")
        except _NotLiveQueue:
            pass                                              # 테스트 경로 — 조용히 넘긴다
        except Exception as e:                                # noqa: BLE001
            _tq_log(f"[register] [주의] {task_id} 파견 트리거를 못 남겼다 — "
                    f"{type(e).__name__}: {e} (catchup 이 최대 10분 뒤 집는다)", idx.root)
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
