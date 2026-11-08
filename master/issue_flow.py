"""일감 단위 작업 흐름 — `#879` (부모 `#826` Phase D).

    start(issue_id)                  플랜 판정 → 로컬 `issue/<N>` 브랜치 → 시작 리비전을 Redmine 에
    finish(issue_id, confirm=False)  범위 보고 → (승인 시) main 적용·push → 브랜치 삭제 →
                                     마감 추적 등록(`issue_track.register` · 해시 전부) →
                                     `issue_link.link_round` → 잠금 해제(`op=finish`) →
                                     Redmine 에 리뷰 요청 노트
    pause(issue_id)                  잠금 보류 → main 으로 → Redmine 「보류」 노트 (브랜치 유지)
    cancel(issue_id, confirm=False)  미리보기(쓰기 0) → (승인 시) 잠금 해제 · 「취소」 노트 ·
                                     `delete_branch=True` 일 때만 브랜치 삭제

`#883` 일감 하나씩: 활성 일감이 있으면 다른 일감의 `start` 는 거절한다(`master/issue_lock.py`).
보류된 일감은 `start` 를 다시 부르면 재개된다(브랜치로 옮기고 「재개」 노트). `#884` T5: 잠금은
`finish` 가 **마감 추적 등록에 성공한 뒤** 푼다 — 세션은 곧바로 다음 일감으로 간다(사용자 결정
2026-11-04). 🔴 `#889` — 등록이 성공하면 같은 갱신에서 일감을 「완료」로 닫는다(main 적용 = 마감). 리뷰는 그 뒤
추적 기록(`issue_track`)을 따라 노트로만 붙는다.
[중요] **잠금 위치(`lock_root`)** — 넘기면 그것을 쓴다. 안 넘기면 **아무것도 주입하지 않은 운영
호출만** AXCluster 트윈(`issue_lock.default_root()`)을 쓴다. getter·noter·enqueue 를 주입한 호출
(테스트 대역)이 `lock_root` 를 안 주면 **잠금을 쓰지 않는다**(`start`·`finish` 는 `[주의] 잠금 미사용`
로그만 남기고 이전처럼 돈다 · `pause`·`cancel` 은 잠금이 본체라 거절). `_resolve_events` 와 같은
원칙 — 대역 실행이 운영 상태를 건드리지 않게.

🔴 `#906`: 기본 작업 저장소는 **이 모듈이 든 운영 저장소**(`REPO`)다. `#905` 가 그것을
`AXCluster/config.yaml` 의 `track.local_clone`(`AXCluster/repo`)으로 바꿨는데, 그 클론은 색인기의
**ff 전용 미러**다 — `events/consumer.py` 가 *"마스터는 이 클론에 커밋하지 않는다"* 를 전제로 매 회차
`merge --ff-only` 로 main 끝을 따라가고, `origin` push 는 `DISABLED://…`(PLAN §2.1)로, pre-push 훅은
main 을 막는다. 거기에 일감 브랜치를 세우자 ① 마감 push 가 rc128 로 죽었고(`#893`) ② 미러가 main 을
안 따라가며(현재 브랜치에 upstream 이 없어 `FETCH_HEAD` 가 전부 not-for-merge) ③ 미병합 커밋이
색인됐다. [중요] **봉인된 저장소는 코드가 거절한다** — `origin` 의 push URL 이 `DISABLED` 면 `start`·
`finish` 가 브랜치·push 전에 멈춘다(`_sealed`). 명시 `repo` 인자는 그대로 우선한다.
[주의] `#905` 의 원래 문제(운영 체크아웃에서 작업하면 oneshot 서비스가 미커밋 코드를 실행한다)는
이 복귀로 다시 열린다 — 별도 일감에서 사용자와 정한다.

사용자 결정(2026-11-03): *"작업을 위해 플랜 영역 생성을 강제하고, 작업 시작할 때 무조건 로컬
리비전을 생성한 뒤 레드마인에 깃 해시를 등록해."*

[중요] **플랜이 없으면 시작하지 않는다** — `plan_start` 판정이 `ok` 가 아니면 브랜치를 만들기
전에 거절한다. 절차서의 「플랜부터」를 코드가 집행하는 자리다(`enforce_process_in_python`).
[중요] **시작 기준은 `origin/main` 과 같은 깨끗한 `main` 이다** — dirty·다른 브랜치·원격과 어긋남은
전부 거절이고, 고치지 않고 사유를 돌려준다(실패는 보고하는 자리).
[중요] **Redmine 기록에 실패하면 방금 만든 브랜치를 되돌린다** — 기록 없는 시작은 나중에 범위를
잃는다. 되돌리는 브랜치는 `main` 과 같은 커밋이라 잃는 것이 없다.
[중요] **종료는 승인이 트리거다** — `confirm=False`(기본)는 범위·커밋 목록만 돌려주고 아무것도 안
바꾼다. 승인 시 순서: **원격 먼저**(`push origin issue/<N>:main`, fast-forward 만) → 성공해야 로컬
`main` 을 끝 커밋으로 바로 전환한다(사전에 ff 가능 검사) → `branch -d`(병합 확인 삭제) → 마감 추적 등록 → 연결 → 잠금 해제
→ 노트. push 가 거절되면
로컬은 그대로다(잃는 것 없음, 강제 push 없음). 사용자 결정(2026-11-03): main 적용 뒤 로컬 브랜치 삭제.
[주의] push 뒤 단계(로컬 맞춤·삭제·등록·해제·노트)가 실패해도 **되돌리지 않는다** — 이미 원격 정본이
바뀌었다. 무엇이 됐고 무엇이 안 됐는지를 `done`/`why` 로 돌려준다.
[중요] `#884` T6 — **git 이 아닌 부분(플랜 판정·잠금·마감 추적·Redmine 노트)은 `master/issue_infra.py`
가 본체다.** `.33` 요청자는 같은 함수를 8101 `/api/v1/issue/*` 로 부른다(git 은 요청자 worktree 몫).
이 모듈은 마스터 로컬 저장소의 git 단계와 그 함수들을 잇는 자리다.
[주의] **로그는 둘이다** — 호출자에게 돌려주는 `log` 목록과 `<AXCluster 트윈>/issue_flow.jsonl`
(한 줄 = 단계 하나). 파일 기록 실패는 흐름을 바꾸지 않는다(stderr 경고).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from master import issue_infra as INF

MAIN = "main"
REMOTE = "origin"
BRANCH_PREFIX = INF.BRANCH_PREFIX
EVENTS_NAME = INF.EVENTS_NAME
START_NOTE = INF.START_NOTE


class IssueFlowError(RuntimeError):
    """흐름이 계약에 어긋나 멈췄다 — 사유 문장을 담는다."""


REPO = Path(__file__).resolve().parent.parent


def default_repo() -> Path:
    """`#906`: 운영 저장소(`REPO`). 색인 미러(`track.local_clone`)는 작업 위치가 아니다 — 모듈 머리말."""
    return REPO


SEALED_PREFIX = "DISABLED"


def _sealed(repo: Path) -> str:
    """`origin` push 가 봉인된 저장소면 사유 문장, 아니면 빈 문자열 (`#906`).

    색인 미러는 `origin` push URL 을 `DISABLED://…` 로 봉인한다(PLAN §2.1). 그 위에 일감 브랜치를
    세우면 마감이 push 에서 죽고 색인기가 main 을 놓친다 — 시작 전에 막는다.
    """
    rc, url = _git(repo, "remote", "get-url", "--push", REMOTE)
    if rc == 0 and url.startswith(SEALED_PREFIX):
        return (f"{repo} 의 {REMOTE} push 가 봉인돼 있다({url[:60]}) — 색인 미러 같은 읽기 전용 "
                "클론에서는 일감을 시작·마감하지 않는다(#906). 운영 저장소에서 한다")
    return ""


branch_name = INF.branch_name


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """`(rc, 출력)`. **성공이면 stdout 만**, 실패면 stdout+stderr(사유)를 돌려준다 (`#881` R218-1).

    [중요] 성공해도 git 은 stderr 에 경고·안내를 쓴다(CRLF 경고·`switch` 안내 등). 합쳐 돌려주면
    해시(`rev-parse`·`merge-base`)가 오염되고 `status --porcelain` 이 깨끗한 트리를 dirty 로 읽는다.
    인코딩은 UTF-8 고정·`replace` — 로케일에 기대지 않는다(R216-3).
    """
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode == 0:
        return 0, (p.stdout or "").strip()
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def _git_ok(repo: Path, *args: str) -> str:
    rc, out = _git(repo, *args)
    if rc != 0:
        raise IssueFlowError(f"git {' '.join(args)} 실패(rc={rc}): {out}")
    return out


def default_events_path() -> Path:
    from master import plan_events as PE
    return PE.default_path().parent / EVENTS_NAME


# `#884` T6 — 기록 쪽(로그·거절·Redmine·잠금)은 `issue_infra` 가 본체다. `.33` 요청자의 8101 경로와
#    같은 함수를 쓰려고 옮겼다 — 아래 이름은 이 모듈의 종전 이름을 잇는 별칭이다.
_Log = INF.Log
_refuse = INF.refuse
_default_getter = INF.default_getter
_default_noter = INF.default_noter
_call_redmine = INF.call_redmine
_NO_LOCK = INF.NO_LOCK
_busy_why = INF.busy_why
_lock_logf = INF.lock_logf


def _resolve_events(events_path, injected: bool):
    """주입 실행(테스트 대역)은 `events_path` 를 줄 때만 기록한다 — 운영 기록 오염 방지."""
    if events_path is not None:
        return events_path
    if injected:
        return None
    try:
        return default_events_path()
    except Exception as e:                              # noqa: BLE001
        print(f"[issue_flow] [주의] 이벤트 경로를 못 풀었다: {e}", file=sys.stderr)
        return None


def _resolve_lock(lock_root, injected: bool):
    """잠금 위치 — `issue_infra.resolve_lock`(프로젝트 미지정 = AXCluster)."""
    return INF.resolve_lock(lock_root, injected)


def _clean(repo: Path) -> tuple[bool, list]:
    rc, dirty = _git(repo, "status", "--porcelain")
    if rc != 0:
        return False, [f"git status 실패: {dirty}"]
    return not dirty, dirty.splitlines()[:20]


def _branch_exists(repo: Path, branch: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0


# ── `#907` 마스터 작업 공간 — 일감 worktree ─────────────────────────────────────
WORKSPACE_PROJECT = "AXCluster"


def _workspace(repo, worktree_root, project: str = WORKSPACE_PROJECT) -> tuple:
    """`(운영 저장소, worktree 부모 | None, 거절 사유)` (`#907`).

    - `worktree_root` 를 넘기면 그것을 쓴다(테스트 대역 자리).
    - `repo` 만 넘기면 **종전 인플레이스**(그 저장소에서 브랜치 전환) — 수동·테스트 호출.
    - 둘 다 없으면 **운영 호출**: `<project>/config.yaml` 의 `master_workspace.issue_worktree_root`.
      🔴 `requester: master` 가 아니거나 `kind: unreal` 이거나 값이 없거나 색인 미러 안이면 **거절**한다
      — 게임·언리얼 프로젝트는 `.33` 이 자기 worktree 에서 작업하고(ax-issue), 값을 추정하면 마스터 경로를
      작업 위치로 오인한다.
    """
    if worktree_root is not None:
        return Path(repo) if repo is not None else default_repo(), Path(worktree_root), ""
    if repo is not None:
        return Path(repo), None, ""
    try:
        from master.context_search.paths import resolve
        from master.projects.config import ProjectConfig
        paths = resolve(project)
        cfg = ProjectConfig.load(paths.config)
    except Exception as e:                              # noqa: BLE001 — 설정 해석
        return default_repo(), None, f"{project} 설정을 못 읽었다 — {type(e).__name__}: {e}"
    if not cfg.requester_is_master:
        return default_repo(), None, (f"{project} 는 `requester: master` 가 아니다 — 이 흐름은 마스터가 요청자인 "
                                      "프로젝트(AXCluster) 전용이다. 게임 프로젝트 일감은 요청자 기계의 worktree 에서 "
                                      "한다(ax-client issue_* · ax-issue)")
    try:
        from master.projects import profile as PF
        kind = PF.kind_of(project)
    except Exception:                                   # noqa: BLE001 — 프로필 없음은 아래 판정에 맡긴다
        kind = ""
    if kind == "unreal":
        return default_repo(), None, f"{project} 는 kind=unreal 이다 — 언리얼 일감은 .33 에서 한다"
    root = cfg.master_issue_worktree_root
    if not root:
        return default_repo(), None, (f"{project}/config.yaml 에 master_workspace.issue_worktree_root 가 없다 — "
                                      "작업 위치를 추정하지 않는다(#907)")
    root_p = Path(root).resolve()
    mirror = Path(paths.repo).resolve()
    if root_p == mirror or mirror in root_p.parents:
        return default_repo(), None, f"issue_worktree_root {root} 가 색인 미러({mirror}) 안이다 — 작업 위치가 아니다"
    return default_repo(), Path(root), ""


def _wt_path(wt_root: Path, issue_id) -> Path:
    return Path(wt_root) / str(int(issue_id))


def _wt_branch(wt: Path) -> str:
    """worktree `wt` 의 현재 브랜치 — 없거나 git 이 아니면 빈 문자열."""
    if not (Path(wt) / ".git").exists():
        return ""
    rc, out = _git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    return out if rc == 0 else ""


def _wt_remove(repo: Path, wt: Path) -> tuple[int, str]:
    """깨끗한 worktree 제거(브랜치는 남는다). 강제하지 않는다 — 미커밋 변경이 있으면 git 이 거절한다."""
    rc, out = _git(repo, "worktree", "remove", str(wt))
    if rc == 0:
        _git(repo, "worktree", "prune")
    return rc, out


RESUME_NOTE = INF.RESUME_NOTE
PAUSE_NOTE = INF.PAUSE_NOTE


def start(issue_id, *, repo=None, getter=None, noter=None, events_path=None,
          logf=None, fetch: bool = True, lock_root=None, worktree_root=None,
          project: str = WORKSPACE_PROJECT) -> dict:
    """일감 작업을 시작한다 — 플랜 강제 → 잠금 확인 → 로컬 브랜치 → 시작 리비전 Redmine 기록.

    이미 `issue/<N>` 에 서 있으면 새로 만들지 않고 그 시작점(`main` 과의 merge-base)을 돌려준다
    (잠금에 없던 옛 브랜치도 이때 잠금에 올린다). N 이 보류 중이고 깨끗한 `main` 에 서 있으면
    `issue/<N>` 으로 옮기고 잠금을 재개한 뒤 「재개」 노트를 남긴다(`resumed: True`).
    플랜·잠금·노트는 `issue_infra` 의 공용 함수다(`.33` 요청자 경로와 같은 규칙).

    🔴 `#907` — 운영 호출(`repo`·`worktree_root` 미지정)은 운영 저장소를 **늘 main 으로 두고**
    `master_workspace.issue_worktree_root/<N>` 에 `issue/<N>` worktree 를 만든다. 응답 `repo` 가 그 worktree
    (편집·커밋 위치), `checkout` 이 운영 저장소다. 설정이 없거나 `requester: master` 가 아니면 거절한다.
    """
    repo, wt_root, ws_why = _workspace(repo, worktree_root, project)
    injected = getter is not None or noter is not None
    log = _Log("start", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    if ws_why:
        return _refuse(log, "workspace", ws_why)
    getter = getter or _default_getter
    noter = noter or _default_noter
    branch = branch_name(issue_id)
    n = int(issue_id)

    # ① 플랜 강제
    bad, _verdict = INF.plan_gate(issue_id, getter=getter, log=log)
    if bad:
        return bad

    # ①-1 잠금 — 다른 일감이 활성이면 아무것도 바꾸지 않고 거절 (`#883`)
    try:
        lroot = _resolve_lock(lock_root, injected)
    except Exception as e:                              # noqa: BLE001 — 경로 해석
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")
    bad, active, prec = INF.lock_gate(lroot, n, log=log)
    if bad:
        return bad

    def _acquire(start_rev: str, why: str) -> dict:
        return INF.acquire(lroot, n, branch=branch, start_rev=start_rev, why=why,
                           by="issue_flow.start", log=log)

    # ② 이미 시작했나
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    sealed = _sealed(repo)                               # `#906` — 색인 미러에 브랜치를 세우지 않는다
    if sealed:
        return _refuse(log, "repo", sealed)
    if wt_root is not None:
        return _start_wt(issue_id, repo=repo, wt=_wt_path(wt_root, issue_id), cur=cur, prec=prec,
                         getter=getter, noter=noter, lroot=lroot, log=log, fetch=fetch, acquire=_acquire)
    exists = _branch_exists(repo, branch)
    if prec and not exists:
        return _refuse(log, "lock", f"#{n} 는 보류 기록이 있는데 {branch} 가 없다 — "
                                    "issue_cancel 로 정리할지 사람이 정한다")
    if exists:
        if cur == branch:
            try:
                rev = _git_ok(repo, "merge-base", MAIN, branch)
            except IssueFlowError as e:                 # `#881` R216-6
                return _refuse(log, "branch", f"{branch} 의 시작 리비전을 못 구했다 — {e}")
            got = _acquire(rev, "이미 브랜치에 서 있음")
            if not got.get("ok"):
                return _refuse(log, "lock", got.get("why", "잠금 실패"), holder=got.get("holder"))
            kind = INF.lock_kind(got)
            log("branch", f"이미 {branch} 에 있다 — 시작 리비전 {rev[:12]} (새 기록 없음 · 잠금 {kind})")
            return {"ok": True, "issue_id": issue_id, "already": True, "branch": branch,
                    "start_rev": rev, "repo": str(repo), "lock": kind, "log": log.lines}
        if not prec:
            return _refuse(log, "branch", f"{branch} 가 이미 있는데 지금 브랜치는 {cur} 다 — "
                                          "그 브랜치로 옮겨 이어 가거나 정리 여부를 사람이 정한다")
        return _resume(issue_id, repo=repo, cur=cur, branch=branch, prec=prec, noter=noter,
                       lroot=lroot, log=log)

    # ③ 기준 상태 — 깨끗한 main = origin/main
    if cur != MAIN:
        return _refuse(log, "base", f"지금 브랜치가 {cur} 다 — {MAIN} 에서 시작한다")
    rc, dirty = _git(repo, "status", "--porcelain")
    if rc != 0:
        return _refuse(log, "base", f"git status 실패: {dirty}")
    if dirty:
        cnt = len(dirty.splitlines())
        return _refuse(log, "base", f"작업 트리가 깨끗하지 않다({cnt}건) — 커밋·정리는 사람이 정한다",
                       dirty=dirty.splitlines()[:20])
    if fetch:
        rc, out = _git(repo, "fetch", "--quiet", REMOTE, MAIN)
        if rc != 0:
            return _refuse(log, "fetch", f"{REMOTE} fetch 실패: {out}")
        log("fetch", f"{REMOTE}/{MAIN} fetch")
    rc, head = _git(repo, "rev-parse", "HEAD")
    if rc != 0:
        return _refuse(log, "base", f"HEAD 를 못 읽었다: {head}")
    rc, remote = _git(repo, "rev-parse", f"{REMOTE}/{MAIN}")
    if rc != 0:
        return _refuse(log, "base", f"{REMOTE}/{MAIN} 을 못 읽었다: {remote}")
    if head != remote:
        return _refuse(log, "base", f"{MAIN} {head[:12]} 이 {REMOTE}/{MAIN} {remote[:12]} 과 다르다 — "
                                    "동기화는 사람이 정한다", head=head, remote=remote)
    log("base", f"{MAIN}={REMOTE}/{MAIN}={head[:12]} · 깨끗함")

    # ④ 로컬 리비전(브랜치)
    rc, out = _git(repo, "switch", "-c", branch)
    if rc != 0:
        return _refuse(log, "branch", f"브랜치 생성 실패: {out}")
    log("branch", f"{branch} 생성 @ {head[:12]}")

    # ⑤ Redmine 기록 — 실패하면 브랜치를 되돌린다
    res, status = INF.start_note(issue_id, branch=branch, start_rev=head, getter=getter, noter=noter)
    if res.startswith("[주의]"):
        back = [_git(repo, "switch", MAIN), _git(repo, "branch", "-d", branch)]
        undone = all(rc == 0 for rc, _ in back)
        log("redmine", f"기록 실패 — {res} · 브랜치 되돌림 {'완료' if undone else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "redmine",
                "why": f"Redmine 기록 실패: {res}", "branch_rolled_back": undone,
                "log": log.lines}
    log("redmine", f"시작 리비전 기록 {head[:12]}" + (f" · 상태 {status}" if status else ""))

    # ⑥ 잠금 — 노트가 성공한 뒤에. 그 사이 다른 일감이 잡았으면(경합) 브랜치를 되돌린다
    got = _acquire(head, "새 브랜치")
    if not got.get("ok"):
        back = [_git(repo, "switch", MAIN), _git(repo, "branch", "-d", branch)]
        undone = all(rc == 0 for rc, _ in back)
        log("lock", f"잠금 실패 — {got.get('why')} · 브랜치 되돌림 {'완료' if undone else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "lock",
                "why": f"잠금 실패: {got.get('why')} — [주의] Redmine 시작 노트는 이미 기록됐다"
                       f"({head[:12]}), 브랜치는 {'되돌렸다' if undone else '되돌리지 못했다'}",
                "holder": got.get("holder"), "branch_rolled_back": undone, "redmine": res,
                "log": log.lines}
    return {"ok": True, "issue_id": issue_id, "already": False, "branch": branch,
            "start_rev": head, "repo": str(repo), "redmine": res, "lock": INF.lock_kind(got), "log": log.lines}


def _base_ok(repo: Path, cur: str, log: _Log, fetch: bool):
    """운영 저장소가 깨끗한 main = origin/main 인가 — `(head, 거절 dict | None)`."""
    if cur != MAIN:
        return "", _refuse(log, "base", f"운영 저장소가 {cur} 에 있다 — 운영 체크아웃은 늘 {MAIN} 이어야 한다(#907)")
    ok, lines = _clean(repo)
    if not ok:
        return "", _refuse(log, "base", f"운영 저장소가 깨끗하지 않다({len(lines)}건) — 커밋·정리는 사람이 정한다",
                           dirty=lines)
    if fetch:
        rc, out = _git(repo, "fetch", "--quiet", REMOTE, MAIN)
        if rc != 0:
            return "", _refuse(log, "fetch", f"{REMOTE} fetch 실패: {out}")
        log("fetch", f"{REMOTE}/{MAIN} fetch")
    rc, head = _git(repo, "rev-parse", "HEAD")
    rc2, remote = _git(repo, "rev-parse", f"{REMOTE}/{MAIN}")
    if rc != 0 or rc2 != 0:
        return "", _refuse(log, "base", f"HEAD·{REMOTE}/{MAIN} 을 못 읽었다: {head} {remote}")
    if head != remote:
        return "", _refuse(log, "base", f"{MAIN} {head[:12]} 이 {REMOTE}/{MAIN} {remote[:12]} 과 다르다 — "
                                        "동기화는 사람이 정한다", head=head, remote=remote)
    log("base", f"{MAIN}={REMOTE}/{MAIN}={head[:12]} · 깨끗함")
    return head, None


def _start_wt(issue_id, *, repo: Path, wt: Path, cur: str, prec, getter, noter, lroot, log: _Log,
              fetch: bool, acquire) -> dict:
    """`#907` worktree 방식 start — 운영 저장소는 main 그대로, `wt` 에 `issue/<N>`."""
    branch = branch_name(issue_id)
    exists = _branch_exists(repo, branch)
    out_base = {"issue_id": issue_id, "branch": branch, "repo": str(wt), "checkout": str(repo)}
    if exists and _wt_branch(wt) == branch:
        try:
            rev = _git_ok(repo, "merge-base", MAIN, branch)
        except IssueFlowError as e:
            return _refuse(log, "branch", f"{branch} 의 시작 리비전을 못 구했다 — {e}")
        got = acquire(rev, "이미 worktree 에 있음")
        if not got.get("ok"):
            return _refuse(log, "lock", got.get("why", "잠금 실패"), holder=got.get("holder"))
        log("branch", f"이미 {wt} 에 {branch} — 시작 리비전 {rev[:12]} (새 기록 없음)")
        return {"ok": True, **out_base, "already": True, "start_rev": rev, "lock": INF.lock_kind(got),
                "log": log.lines}
    if wt.exists():
        return _refuse(log, "worktree", f"{wt} 가 이미 있는데 {branch} worktree 가 아니다 — 정리는 사람이 정한다")
    if prec and not exists:
        return _refuse(log, "lock", f"#{int(issue_id)} 는 보류 기록이 있는데 {branch} 가 없다 — "
                                    "issue_cancel 로 정리할지 사람이 정한다")
    if exists and not prec:
        return _refuse(log, "branch", f"{branch} 가 이미 있다(worktree 없음·보류 기록 없음) — "
                                      "이어 갈지 정리할지 사람이 정한다")
    head, bad = _base_ok(repo, cur, log, fetch)
    if bad:
        return bad
    wt.parent.mkdir(parents=True, exist_ok=True)
    if exists:                                           # 보류 → 재개
        rc, out = _git(repo, "worktree", "add", str(wt), branch)
        if rc != 0:
            return _refuse(log, "worktree", f"worktree 추가 실패: {out}")
        log("worktree", f"{wt} ← {branch} (재개)")
        got = INF.resume_record(issue_id, lroot=lroot, branch=branch, prec=prec, noter=noter, log=log,
                                by="issue_flow.start")
        if not got["ok"]:
            rc2, _ = _wt_remove(repo, wt)
            log(got["step"], f"재개 실패 — {got.get('why') or got.get('res')} · worktree 제거 "
                             f"{'완료' if rc2 == 0 else '실패'}")
            return {"ok": False, "issue_id": issue_id, "step": got["step"],
                    "why": got.get("why") or f"Redmine 재개 노트 실패: {got.get('res')}",
                    "worktree_removed": rc2 == 0, "log": log.lines}
        log("redmine", f"재개 노트 · 시작 리비전 {str(got['start_rev'])[:12]}")
        return {"ok": True, **out_base, "already": False, "resumed": True, "start_rev": got["start_rev"],
                "redmine": got["res"], "lock": "resumed", "log": log.lines}

    rc, out = _git(repo, "worktree", "add", "-b", branch, str(wt), head)
    if rc != 0:
        return _refuse(log, "worktree", f"worktree·브랜치 생성 실패: {out}")
    log("worktree", f"{wt} ← {branch} 생성 @ {head[:12]} · 운영 저장소는 {MAIN} 유지")

    def _undo() -> bool:
        a, _ = _wt_remove(repo, wt)
        b, _ = _git(repo, "branch", "-d", branch)
        return a == 0 and b == 0
    res, status = INF.start_note(issue_id, branch=branch, start_rev=head, getter=getter, noter=noter)
    if res.startswith("[주의]"):
        undone = _undo()
        log("redmine", f"기록 실패 — {res} · worktree·브랜치 되돌림 {'완료' if undone else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "redmine", "why": f"Redmine 기록 실패: {res}",
                "branch_rolled_back": undone, "log": log.lines}
    log("redmine", f"시작 리비전 기록 {head[:12]}" + (f" · 상태 {status}" if status else ""))
    got = acquire(head, "새 worktree")
    if not got.get("ok"):
        undone = _undo()
        log("lock", f"잠금 실패 — {got.get('why')} · worktree·브랜치 되돌림 {'완료' if undone else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "lock",
                "why": f"잠금 실패: {got.get('why')} — [주의] Redmine 시작 노트는 이미 기록됐다({head[:12]})",
                "holder": got.get("holder"), "branch_rolled_back": undone, "redmine": res, "log": log.lines}
    return {"ok": True, **out_base, "already": False, "start_rev": head, "redmine": res,
            "lock": INF.lock_kind(got), "log": log.lines}


def _resume(issue_id, *, repo: Path, cur: str, branch: str, prec: dict, noter, lroot,
            log: _Log) -> dict:
    """보류 중인 N 을 재개 — 깨끗한 main → `switch issue/N` → 잠금 재개 → 「재개」 노트.

    기록 쪽(잠금 재개·노트·노트 실패 시 보류 복원)은 `issue_infra.resume_record` 다. 실패하면
    여기서 main 으로 되돌아간다(undo).
    """
    n = int(issue_id)
    if cur != MAIN:
        return _refuse(log, "base", f"#{n} 는 보류 중이다 — 재개는 {MAIN} 에서 한다(지금 {cur})")
    ok, lines = _clean(repo)
    if not ok:
        return _refuse(log, "base", f"작업 트리가 깨끗하지 않다({len(lines)}건) — 변경이 {branch} 로 "
                                    "따라간다, 커밋·정리는 사람이 정한다", dirty=lines)
    rc, out = _git(repo, "switch", branch)
    if rc != 0:
        return _refuse(log, "branch", f"{branch} 로 옮기지 못했다: {out}")
    log("branch", f"{MAIN} → {branch}")
    got = INF.resume_record(issue_id, lroot=lroot, branch=branch, prec=prec, noter=noter, log=log,
                            by="issue_flow.start")
    if not got["ok"]:
        rc2, out2 = _git(repo, "switch", MAIN)
        back = "완료" if rc2 == 0 else "실패: " + out2
        if got["step"] == "lock":
            log("lock", f"재개 실패 — {got.get('why')} · {MAIN} 복귀 {back}")
            return {"ok": False, "issue_id": issue_id, "step": "lock", "why": got.get("why", "잠금 실패"),
                    "holder": got.get("holder"), "switched_back": rc2 == 0, "log": log.lines}
        relocked = got["relocked"]
        res = got["res"]
        log("redmine", f"재개 노트 실패 — {res} · {MAIN} 복귀 {back}"
                       f" · 잠금 보류 복원 {'완료' if relocked else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "redmine",
                "why": f"Redmine 재개 노트 실패: {res} — 재개를 되돌렸다"
                       f"({MAIN} 복귀 {'완료' if rc2 == 0 else '실패'} · 보류 복원 {'완료' if relocked else '실패'})",
                "switched_back": rc2 == 0, "relocked": relocked, "log": log.lines}
    rev = got["start_rev"]
    log("redmine", f"재개 노트 · 시작 리비전 {str(rev)[:12]}")
    return {"ok": True, "issue_id": issue_id, "already": False, "resumed": True, "branch": branch,
            "start_rev": rev, "repo": str(repo), "redmine": got["res"], "lock": "resumed", "log": log.lines}


REVIEW_PRIORITY = 10            # 사람이 요청한 리뷰 — 자동 등재(0)보다 먼저 (`#638` 규약) · 값은
                                # 이제 `issue_link.PRIORITY` 가 해시·종합 리뷰에 건다(`#884`)
REVIEW_PROJECT = "AXCluster"    # 마스터 로컬 흐름의 마감 추적 트윈 — 이 흐름은 AXCluster 저장소용이다
FINISH_NOTE = INF.FINISH_NOTE
TRACK_OK = INF.TRACK_OK
TRACK_FAIL = INF.TRACK_FAIL


def _default_review_root(project: str = REVIEW_PROJECT) -> Path:
    from master.context_search.paths import resolve
    return Path(resolve(project).root)


_default_register = INF.default_register
_default_link = INF.default_link


def _span(repo: Path, branch: str) -> tuple[str, str, list]:
    base = _git_ok(repo, "merge-base", MAIN, branch)
    end = _git_ok(repo, "rev-parse", branch)
    out = _git_ok(repo, "log", "--reverse", "--format=%H %s", f"{base}..{end}")
    return base, end, [ln for ln in out.splitlines() if ln.strip()]


def finish(issue_id, *, confirm: bool = False, repo=None, noter=None, register=None, link=None,
           review_root=None, events_path=None, logf=None, fetch: bool = True,
           lock_root=None, project: str = REVIEW_PROJECT, worktree_root=None) -> dict:
    """일감 작업을 마친다. `confirm=False` 면 보고만 한다(쓰기 0).

    `#883`: N 이 보류 중이면(먼저 재개) · 다른 일감이 활성이면 거절한다. 잠금에 없는 N(`#883` 이전
    시작)은 `[주의]` 로그만 남기고 진행한다.

    `#884` T5 — 승인 시 push·로컬 맞춤·브랜치 삭제 뒤:
      ④ `issue_track.register(review_root, N, project=, base=, end=, hashes=<base..end 전체 sha, 순서대로>)`
         [중요] **범위 리뷰(`kind=range`)를 직접 등재하지 않는다** — 커밋 리뷰는 색인기가 해시마다
         걸고(우선순위 10 은 `issue_link` 가 올린다), 종합 리뷰는 해시가 모두 끝난 뒤 큐 소비자
         (`issue_progress.sync_issue_tracks`)가 건다.
      ⑤ `issue_link.link_round(review_root, N)` — 등록 **전에** 색인기가 이미 넣은 해시를 줍는다.
         실패해도 다음 동기화 회차가 같은 규칙(`issue_link.apply`)으로 잇는다 — `problems` 에만 적는다.
      ⑥ 잠금 해제(`op=finish`) — 🔴 **등록이 성공했을 때만**. 등록이 실패했는데 잠금을 풀면 그 일감의
         리뷰는 어디에도 이어지지 않은 채 세션이 다음으로 가 버린다(조용한 유실). 그래서 등록 실패면
         잠금을 남겨 두고 노트·`why` 가 그 사실을 말한다 — 사람이 재등록하거나 취소로 푼다.
      ⑦ 「리뷰 요청」 노트 — 등록 결과·잠금 결과를 사실로 적는다.

    주입: `register(root, N, **kw)`·`link(root, N, logf=)` 는 테스트 대역 자리다. 대역 주입 실행
    (noter·register·link 중 하나라도)이 `review_root` 를 안 주면 운영 트윈을 건드리지 않으려고 등록을
    하지 않는다(등록 실패로 다룬다 — 잠금도 남는다).

    🔴 `#907` worktree 방식(운영 호출): 운영 저장소는 깨끗한 main, `<root>/<N>` worktree 는 깨끗한
    `issue/<N>` 이어야 한다. push 뒤 운영 main 을 끝 커밋으로 fast-forward(= 서비스 코드 반영) →
    worktree 제거 → `branch -d`.
    """
    repo, wt_root, ws_why = _workspace(repo, worktree_root, project)
    injected = noter is not None or register is not None or link is not None
    log = _Log("finish", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    if ws_why:
        return _refuse(log, "workspace", ws_why)
    wt = _wt_path(wt_root, issue_id) if wt_root is not None else None
    noter = noter or _default_noter
    register = register or _default_register
    link = link or _default_link
    branch = branch_name(issue_id)
    n = int(issue_id)

    # ⓪ 잠금
    try:
        lroot = _resolve_lock(lock_root, injected)
    except Exception as e:                              # noqa: BLE001
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")
    bad, lock_held = INF.finish_lock_check(lroot, n, log=log)
    if bad:
        return bad

    # ① 위치·상태
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    sealed = _sealed(repo)                               # `#906` — 봉인된 push 를 시도하지 않는다
    if sealed:
        return _refuse(log, "repo", sealed)
    if wt is not None:
        if cur != MAIN:
            return _refuse(log, "branch", f"운영 저장소가 {cur} 에 있다 — 운영 체크아웃은 늘 {MAIN} 이어야 한다(#907)")
        if _wt_branch(wt) != branch:
            return _refuse(log, "worktree", f"{wt} 에 {branch} worktree 가 없다 — issue_start 로 시작·재개한 뒤 마친다")
        for where, label in ((repo, "운영 저장소"), (wt, "일감 worktree")):
            ok, lines = _clean(where)
            if not ok:
                return _refuse(log, "tree", f"{label}가 깨끗하지 않다 — 커밋·정리는 사람이 정한다", dirty=lines)
    else:
        if cur != branch:
            return _refuse(log, "branch", f"지금 브랜치가 {cur} 다 — {branch} 에서 마친다")
        rc, dirty = _git(repo, "status", "--porcelain")
        if rc != 0 or dirty:
            return _refuse(log, "tree", "작업 트리가 깨끗하지 않다 — 커밋·정리는 사람이 정한다",
                           dirty=(dirty or "").splitlines()[:20])
    # #896 방어: Git 버전에 따라 switch -C가 다른 worktree의 main 점유도 덮는다.
    # 같은 로컬 저장소의 등록 worktree만 확인하고 push 전에 거절한다.
    rc, worktrees = _git(repo, "worktree", "list", "--porcelain")
    if rc != 0:
        return _refuse(log, "worktree", f"worktree 목록 조회 실패: {worktrees}")
    for record in worktrees.split("\n\n"):
        fields = record.splitlines()
        if f"branch refs/heads/{MAIN}" not in fields:
            continue
        owner = next((line[len("worktree "):] for line in fields if line.startswith("worktree ")), "")
        if not owner:
            return _refuse(log, "worktree", f"{MAIN} 점유 worktree 경로를 읽지 못했다")
        if Path(owner).resolve() != repo.resolve():
            return _refuse(log, "worktree", f"다른 worktree가 {MAIN} 을 사용 중이다: {owner} — "
                                           "push·참조 변경 없이 중단한다")
    if fetch:
        rc, out = _git(repo, "fetch", "--quiet", REMOTE, MAIN)
        if rc != 0:
            return _refuse(log, "fetch", f"{REMOTE} fetch 실패: {out}")
        log("fetch", f"{REMOTE}/{MAIN} fetch")
    try:
        base, end, commits = _span(repo, branch)
        remote = _git_ok(repo, "rev-parse", f"{REMOTE}/{MAIN}")
        local_main = _git_ok(repo, "rev-parse", MAIN)
    except IssueFlowError as e:
        return _refuse(log, "span", str(e))
    if not commits:
        return _refuse(log, "span", f"{branch} 에 {MAIN} 이후 커밋이 없다 — 마칠 것이 없다")
    if local_main != remote:
        return _refuse(log, "base", f"로컬 {MAIN} {local_main[:12]} ≠ {REMOTE}/{MAIN} {remote[:12]} — "
                                    "동기화는 사람이 정한다")
    if _git(repo, "merge-base", "--is-ancestor", remote, end)[0] != 0:
        return _refuse(log, "base", f"{REMOTE}/{MAIN} {remote[:12]} 이 {branch} 의 조상이 아니다 — "
                                    "fast-forward 불가, rebase·머지는 사람이 정한다")
    try:
        files = _git_ok(repo, "diff", "--name-only", base, end).splitlines()
    except IssueFlowError as e:
        return _refuse(log, "span", str(e))
    summary = {"issue_id": issue_id, "branch": branch, "base": base, "end": end,
               "commits": commits, "files": len(files), "repo": str(wt or repo)}
    if wt is not None:
        summary["checkout"] = str(repo)
    log("span", f"범위 {base[:12]}..{end[:12]} · 커밋 {len(commits)}건 · 파일 {len(files)}")

    if not confirm:
        log("preview", "confirm=False — 아무것도 바꾸지 않았다")
        return {"ok": True, "confirmed": False, **summary,
                "next": f"승인하면 finish({issue_id}, confirm=True) — push {REMOTE} {branch}:{MAIN} · "
                        + (f"운영 {MAIN} fast-forward(서비스 코드 반영) · worktree {wt} 제거 · " if wt is not None
                           else f"끝 커밋으로 로컬 {MAIN} 전환(성공 시 참조 전진) · ")
                        + f"{branch} 삭제 · 마감 추적 등록(해시 {len(commits)}개) · "
                        f"색인기 리뷰 연결 · "
                        + ("잠금 해제(등록 성공 시) · " if lock_held else "")
                        + "Redmine 리뷰 요청 노트 + 「완료」·100(등록 성공 시 — #889) — 해시별 리뷰와 종합 리뷰는 "
                          "큐 소비자가 끝나는 대로 이 일감에 노트로만 남긴다",
                "log": log.lines}

    done: list[str] = []
    # ② 원격 먼저
    rc, out = _git(repo, "push", REMOTE, f"{branch}:{MAIN}")
    if rc != 0:
        log("push", f"거절 — 로컬은 그대로: {out[-300:]}")
        return {"ok": False, "confirmed": True, **summary, "step": "push",
                "why": f"push 실패(rc={rc}) — 강제 push 하지 않는다: {out[-500:]}", "done": done,
                "log": log.lines}
    done.append("push")
    log("push", f"{REMOTE}/{MAIN} ← {end[:12]}")

    problems: list[str] = []
    # ③ 끝 커밋의 main으로 전환 → 브랜치 삭제 (#896).
    # switch main → merge 는 잠깐 옛 main 파일을 깐다. -C는 끝 커밋으로 바로 전환하며,
    # 전환에 실패하면 main 참조도 바꾸지 않는다. ff 가능성은 위에서 이미 확인했다.
    deleted = False
    if wt is not None:
        # `#907` — 운영 main 을 앞으로(fast-forward만) → worktree 제거 → 브랜치 삭제
        rc, out = _git(repo, "merge", "--ff-only", end)
        if rc != 0:
            problems.append(f"운영 main ff: {out[-200:]}")
            log("ff", f"실패 — {out[-200:]}")
        else:
            done.append("ff")
            log("ff", f"운영 {MAIN} ← {end[:12]} (서비스 코드 반영)")
            rc, out = _wt_remove(repo, wt)
            if rc != 0:
                problems.append(f"worktree remove: {out[-200:]}")
                log("worktree", f"제거 실패 — {out[-200:]}")
            else:
                done.append("worktree_remove")
                log("worktree", f"{wt} 제거")
                rc, out = _git(repo, "branch", "-d", branch)
                if rc == 0:
                    deleted = True
                    done.append("delete_branch")
                    log("delete_branch", f"{branch} 삭제(main 에서 도달 가능)")
                else:
                    problems.append(f"branch -d: {out[-200:]}")
                    log("delete_branch", f"실패 — {out[-200:]}")
    else:
        rc, out = _git(repo, "switch", "-C", MAIN, end)
        if rc != 0:
            problems.append(f"switch: {out[-200:]}")
            log("switch", f"실패 — {out[-200:]}")
        else:
            done.append("switch")
            log("switch", f"switch -C {MAIN} {end}")
            rc, out = _git(repo, "branch", "-d", branch)
            if rc == 0:
                deleted = True
                done.append("delete_branch")
                log("delete_branch", f"{branch} 삭제(main 에서 도달 가능)")
            else:
                problems.append(f"branch -d: {out[-200:]}")
                log("delete_branch", f"실패 — {out[-200:]}")

    # ④~⑦ 마감 추적 등록 → 리뷰 연결 → 잠금 해제(등록 성공 시만) → 「리뷰 요청」 노트 — `issue_infra`
    def _track_root():
        if review_root is None and injected:
            raise IssueFlowError("대역 주입 실행에 review_root 가 없다 — 운영 트윈을 건드리지 않는다")
        return Path(review_root) if review_root is not None else _default_review_root(project)

    got = INF.finish_record(issue_id, project=project, track_root_fn=_track_root, lroot=lroot,
                            lock_held=lock_held, base=base, end=end, commits=commits, branch=branch,
                            deleted="" if deleted else " 실패", register=register, link=link,
                            noter=noter, log=log, done=done, problems=problems, by="issue_flow.finish")
    return {"ok": not problems, "confirmed": True, **summary, "done": done,
            "registered": got["registered"], "round": got["round"],
            "lock_released": got["lock_released"], "closed": got.get("closed", False),
            # `#921` — 마감 뒤 단계(신선도 판정·재기동·인수인계 확인·배달·기록)는 이 명령이 집행한다(§1.9)
            "next": f"AX_PROJECTS_ROOT={REPO} {REPO}/.venv/bin/python -m master.issue_wrapup {issue_id}",
            "why": " · ".join(problems), "log": log.lines}


# ── `#883` 보류·취소 ──────────────────────────────────────────────────────────

def _lock_required(lock_root, injected: bool, log: _Log):
    """pause·cancel 은 잠금이 본체다 — 위치가 없으면(`_NO_LOCK`·해석 실패) 거절 사유를 돌려준다."""
    try:
        root = _resolve_lock(lock_root, injected)
    except Exception as e:                              # noqa: BLE001
        return None, _refuse(log, "lock", f"잠금 위치를 못 풀었다 — {type(e).__name__}: {e}")
    if root is _NO_LOCK:
        return None, _refuse(log, "lock", "대역 주입 실행에 lock_root 가 없다 — 운영 잠금을 건드리지 않는다")
    return root, None


def pause(issue_id, *, repo=None, noter=None, lock_root=None, events_path=None, logf=None,
          worktree_root=None, project: str = WORKSPACE_PROJECT) -> dict:
    """활성 일감을 보류한다 — `issue/<N>` 의 깨끗한 트리 → 잠금 보류 → `main` 으로 → 「보류」 노트.

    브랜치는 남는다. 재개는 `start(N)` 이다. [중요] dirty 면 거절한다 — 미커밋 변경이 `main` 으로
    따라간다. `main` 전환이 실패하면 잠금을 다시 활성으로 되돌린다. 노트만 실패하면 보류 상태는
    유지하고(잠금이 정본) `ok: False` 로 알린다.

    `#907` worktree 방식: 깨끗한 `<root>/<N>` worktree 를 **제거**한다(브랜치 유지) — 운영 저장소는 손대지
    않는다. 재개(`start`)가 worktree 를 다시 만든다.
    """
    from master import issue_lock as IL
    repo, wt_root, ws_why = _workspace(repo, worktree_root, project)
    injected = noter is not None
    log = _Log("pause", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    if ws_why:
        return _refuse(log, "workspace", ws_why)
    wt = _wt_path(wt_root, issue_id) if wt_root is not None else None
    noter = noter or _default_noter
    branch = branch_name(issue_id)
    n = int(issue_id)
    llog = _lock_logf(log)
    lroot, refused = _lock_required(lock_root, injected, log)
    if refused:
        return refused

    work = wt if wt is not None else repo
    rc, cur = _git(work, "rev-parse", "--abbrev-ref", "HEAD") if (wt is None or _wt_branch(wt)) else (1, "")
    if rc != 0:
        if wt is not None:
            return _refuse(log, "worktree", f"{wt} 에 {branch} worktree 가 없다 — 보류할 작업이 없다")
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    if cur != branch:
        return _refuse(log, "branch", f"지금 브랜치가 {cur} 다 — {branch} 에서 보류한다")
    ok, lines = _clean(work)
    if not ok:
        return _refuse(log, "tree", f"작업 트리가 깨끗하지 않다({len(lines)}건) — "
                                    + ("worktree 를 지우면 미커밋 변경을 잃는다" if wt is not None
                                       else f"미커밋 변경이 {MAIN} 으로 따라간다")
                                    + ", 커밋·정리는 사람이 정한다", dirty=lines)
    end = _git(work, "rev-parse", "HEAD")[1]
    bad, rec = INF.pause_lock(lroot, n, log=log, by="issue_flow.pause")
    if bad:
        return bad

    rc, out = _wt_remove(repo, wt) if wt is not None else _git(repo, "switch", MAIN)
    if rc != 0:
        try:
            back = IL.acquire(lroot, n, branch=branch, start_rev=rec.get("start_rev") or "",
                              by="issue_flow.pause", why="main 전환 실패 — 되돌림", logf=llog)
            relocked = bool(back.get("ok"))
        except Exception as e:                          # noqa: BLE001
            relocked = False
            log("lock", f"활성 되돌림 예외 — {type(e).__name__}: {e}")
        log("switch", f"실패 — {out[-200:]} · 잠금 활성 복원 {'완료' if relocked else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "switch",
                "why": f"{MAIN} 으로 옮기지 못했다: {out[-300:]} — 보류를 되돌렸다"
                       f"(잠금 활성 복원 {'완료' if relocked else '실패'})",
                "relocked": relocked, "log": log.lines}
    log("switch", (f"worktree {wt} 제거" if wt is not None else f"{branch} → {MAIN}")
        + f" · {branch} 유지 @ {end[:12]}")

    res = INF.pause_note(issue_id, branch=branch, end=end, noter=noter)
    base = {"issue_id": issue_id, "paused": True, "branch": branch, "end": end,
            "start_rev": rec.get("start_rev")}
    if res.startswith("[주의]"):
        log("redmine", f"보류 노트 실패 — {res} · 보류 상태는 유지(잠금이 정본)")
        return {"ok": False, **base, "step": "redmine",
                "why": f"Redmine 보류 노트 실패: {res} — 보류(잠금 해제·{MAIN} 전환)는 이미 됐고 유지한다, "
                       "노트는 사람이 남긴다", "log": log.lines}
    log("redmine", "보류 노트")
    return {"ok": True, **base, "redmine": res, "log": log.lines}


CANCEL_NOTE = INF.CANCEL_NOTE


def cancel(issue_id, *, confirm: bool = False, delete_branch: bool = False, repo=None, noter=None,
           lock_root=None, events_path=None, logf=None, worktree_root=None,
           project: str = WORKSPACE_PROJECT) -> dict:
    """일감을 취소한다. `confirm=False`(기본)는 미리보기만 한다(쓰기 0).

    승인 시: `issue/<N>` 에 서 있으면 깨끗한지 보고 `main` 으로 → 잠금 해제(`op=cancel`) → 「취소」 노트
    → `delete_branch=True` **일 때만** `branch -D`. [중요] 노트가 실패하면 브랜치를 지우지 않는다 —
    지울 커밋 목록이 어디에도 안 남는다. 잠금에 없는 N 은 브랜치가 있을 때만 받는다(옛 브랜치 정리).
    `#907` worktree 방식: `<root>/<N>` worktree 가 있으면 깨끗한지 보고 **제거**한다(운영 저장소는 그대로).
    """
    repo, wt_root, ws_why = _workspace(repo, worktree_root, project)
    injected = noter is not None
    log = _Log("cancel", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    if ws_why:
        return _refuse(log, "workspace", ws_why)
    wt = _wt_path(wt_root, issue_id) if wt_root is not None else None
    wt_on = wt is not None and _wt_branch(wt) == branch_name(issue_id)
    noter = noter or _default_noter
    branch = branch_name(issue_id)
    n = int(issue_id)
    lroot, refused = _lock_required(lock_root, injected, log)
    if refused:
        return refused

    try:
        lock_state = INF.cancel_state(lroot, n)
    except Exception as e:                              # noqa: BLE001
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    exists = _branch_exists(repo, branch)
    if lock_state == "absent" and not exists:
        return _refuse(log, "lock", f"#{n} 는 잠금에도 없고 {branch} 도 없다 — 취소할 것이 없다")
    commits, local_only = [], []
    if exists:
        rc, out = _git(repo, "log", "--reverse", "--format=%H %s", f"{MAIN}..{branch}")
        if rc != 0:
            return _refuse(log, "span", f"{MAIN}..{branch} 커밋을 못 읽었다: {out}")
        commits = [ln for ln in out.splitlines() if ln.strip()]
        rc, out = _git(repo, "log", "--format=%H", f"{MAIN}..{branch}", "--not", "--remotes")
        local_only = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else [c[:40] for c in commits]
    log("state", f"잠금 {lock_state}{' (잠금 기록 없음 — 옛 브랜치)' if lock_state == 'absent' else ''} · "
                 f"브랜치 {'있음' if exists else '없음'} · 지금 {cur} · {MAIN} 밖 커밋 {len(commits)}건"
                 f"(로컬에만 {len(local_only)})")
    summary = {"issue_id": issue_id, "branch": branch, "lock_state": lock_state,
               "branch_exists": exists, "on_branch": cur == branch, "commits": commits,
               "local_only": local_only, "delete_branch": delete_branch}
    if wt is not None:
        summary["worktree"] = str(wt) if wt_on else ""
    warning = ""
    if local_only:
        warning = (f"[중요] {branch} 의 커밋 {len(local_only)}건은 이 저장소에만 있다(원격 없음) — "
                   "브랜치를 지우면 되살릴 수 없다")

    if not confirm:
        fate = (f"{branch} 삭제(branch -D)" if delete_branch and exists else f"{branch} 유지")
        log("preview", "confirm=False — 아무것도 바꾸지 않았다")
        return {"ok": True, "confirmed": False, **summary, "warning": warning,
                "next": f"승인하면 cancel({n}, confirm=True{', delete_branch=True' if delete_branch else ''}) — "
                        + (f"{MAIN} 으로 전환 · " if cur == branch else "")
                        + (f"worktree {wt} 제거 · " if wt_on else "")
                        + ("잠금 해제(cancel) · " if lock_state != "absent" else "")
                        + f"Redmine 취소 노트 · {fate}"
                        + ("" if delete_branch else " (삭제는 delete_branch=True 일 때만)"),
                "log": log.lines}

    done: list[str] = []
    if wt_on:
        ok, lines = _clean(wt)
        if not ok:
            return _refuse(log, "tree", f"일감 worktree 가 깨끗하지 않다({len(lines)}건) — 커밋·정리는 사람이 정한다",
                           dirty=lines, **summary)
        rc, out = _wt_remove(repo, wt)
        if rc != 0:
            return _refuse(log, "worktree", f"worktree 제거 실패: {out[-300:]}", **summary)
        done.append("worktree_remove")
        log("worktree", f"{wt} 제거")
    if cur == branch:
        ok, lines = _clean(repo)
        if not ok:
            return _refuse(log, "tree", f"작업 트리가 깨끗하지 않다({len(lines)}건) — 커밋·정리는 사람이 정한다",
                           dirty=lines, **summary)
        rc, out = _git(repo, "switch", MAIN)
        if rc != 0:
            return _refuse(log, "switch", f"{MAIN} 으로 옮기지 못했다: {out[-300:]}", **summary)
        done.append("switch")
        log("switch", f"{branch} → {MAIN}")
    will_delete = bool(delete_branch and exists)
    got = INF.cancel_record(issue_id, lroot=lroot, lock_state_=lock_state, branch=branch, commits=commits,
                            local_only=local_only, will_delete=will_delete, noter=noter, log=log,
                            done=done, by="issue_flow.cancel")
    if not got["ok"]:
        out = {"ok": False, "confirmed": True, **summary, "step": got["step"], "why": got["why"],
               "done": done, "log": log.lines}
        if got["step"] == "redmine":
            out["branch_deleted"] = False
        return out
    res = got["res"]

    deleted = False
    if will_delete:
        rc, out = _git(repo, "branch", "-D", branch)
        if rc != 0:
            log("delete_branch", f"실패 — {out[-200:]}")
            return {"ok": False, "confirmed": True, **summary, "step": "delete_branch",
                    "why": f"{branch} 삭제 실패(노트에는 삭제로 적혔다): {out[-300:]}",
                    "branch_deleted": False, "done": done, "log": log.lines}
        deleted = True
        done.append("delete_branch")
        log("delete_branch", f"{branch} 삭제 — 커밋 {len(commits)}건(로컬에만 {len(local_only)})은 노트에 남았다")
    elif exists:
        log("keep_branch", f"{branch} 유지")
    return {"ok": True, "confirmed": True, **summary, "branch_deleted": deleted, "done": done,
            "redmine": res, "log": log.lines}
