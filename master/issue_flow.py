"""일감 단위 작업 흐름 — `#879` (부모 `#826` Phase D).

    start(issue_id)                  플랜 판정 → 로컬 `issue/<N>` 브랜치 → 시작 리비전을 Redmine 에
    finish(issue_id, confirm=False)  범위 보고 → (승인 시) main 적용·push → 브랜치 삭제 →
                                     범위 리뷰 등재(`kind=range`) → Redmine 에 리뷰 요청 노트

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
`main` 을 `--ff-only` 로 맞춘다 → `branch -d`(병합 확인 삭제) → 리뷰 등재 → 노트. push 가 거절되면
로컬은 그대로다(잃는 것 없음, 강제 push 없음). 사용자 결정(2026-11-03): main 적용 뒤 로컬 브랜치 삭제.
[주의] push 뒤 단계(로컬 맞춤·삭제·등재·노트)가 실패해도 **되돌리지 않는다** — 이미 원격 정본이
바뀌었다. 무엇이 됐고 무엇이 안 됐는지를 `done`/`why` 로 돌려준다.
[주의] **로그는 둘이다** — 호출자에게 돌려주는 `log` 목록과 `<AXCluster 트윈>/issue_flow.jsonl`
(한 줄 = 단계 하나). 파일 기록 실패는 흐름을 바꾸지 않는다(stderr 경고).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAIN = "main"
REMOTE = "origin"
BRANCH_PREFIX = "issue/"
EVENTS_NAME = "issue_flow.jsonl"
START_NOTE = "작업 시작 리비전: `{rev}` · 브랜치 `{branch}`"


class IssueFlowError(RuntimeError):
    """흐름이 계약에 어긋나 멈췄다 — 사유 문장을 담는다."""


def branch_name(issue_id) -> str:
    return f"{BRANCH_PREFIX}{int(issue_id)}"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def _git_ok(repo: Path, *args: str) -> str:
    rc, out = _git(repo, *args)
    if rc != 0:
        raise IssueFlowError(f"git {' '.join(args)} 실패(rc={rc}): {out}")
    return out


def default_events_path() -> Path:
    from master import plan_events as PE
    return PE.default_path().parent / EVENTS_NAME


class _Log:
    """단계 로그 — 목록 + jsonl + (선택) 호출자 logf."""

    def __init__(self, op: str, issue_id, *, events_path=None, logf=None):
        self.op, self.issue_id, self.lines = op, issue_id, []
        self.events_path, self.logf = events_path, logf

    def __call__(self, step: str, msg: str, **extra) -> None:
        line = f"[issue_flow] #{self.issue_id} {self.op}.{step}: {msg}"
        self.lines.append(line)
        if self.logf:
            self.logf(line)
        path = self.events_path
        if path is None:
            return
        rec = {"at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "op": self.op, "issue_id": self.issue_id, "step": step, "msg": msg, **extra}
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[issue_flow] [주의] 이벤트 기록 실패 {path}: {e}", file=sys.stderr)


def _refuse(log: _Log, step: str, why: str, **extra) -> dict:
    log(step, f"거절 — {why}")
    return {"ok": False, "issue_id": log.issue_id, "step": step, "why": why,
            "log": log.lines, **extra}


def _default_getter(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)


def _default_noter(issue_id, *, notes: str, status_name: str = "") -> str:
    from master import redmine
    return redmine.update_issue(issue_id, notes=notes, status_name=status_name)


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


def start(issue_id, *, repo=None, getter=None, noter=None, events_path=None,
          logf=None, fetch: bool = True) -> dict:
    """일감 작업을 시작한다 — 플랜 강제 → 로컬 브랜치 → 시작 리비전 Redmine 기록.

    이미 `issue/<N>` 에 서 있으면 새로 만들지 않고 그 시작점(`main` 과의 merge-base)을 돌려준다.
    """
    from master import plan_start as ST
    repo = Path(repo or REPO)
    injected = getter is not None or noter is not None
    log = _Log("start", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    getter = getter or _default_getter
    noter = noter or _default_noter
    branch = branch_name(issue_id)

    # ① 플랜 강제
    verdict = ST.start_issue(issue_id, getter=getter)
    if "error" in verdict:
        return _refuse(log, "plan", f"이슈를 읽지 못했다 — {verdict['error']}")
    if not verdict.get("ok"):
        return _refuse(log, "plan", f"플랜 판정 {verdict.get('verdict')} — {verdict.get('next_action', '')}",
                       verdict=verdict.get("verdict"))
    log("plan", f"판정 {verdict.get('verdict')} · 태스크 {', '.join(verdict.get('tasks') or []) or '-'}")

    # ② 이미 시작했나
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    exists = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0
    if exists:
        if cur != branch:
            return _refuse(log, "branch", f"{branch} 가 이미 있는데 지금 브랜치는 {cur} 다 — "
                                          "그 브랜치로 옮겨 이어 가거나 정리 여부를 사람이 정한다")
        rev = _git_ok(repo, "merge-base", MAIN, branch)
        log("branch", f"이미 {branch} 에 있다 — 시작 리비전 {rev[:12]} (새 기록 없음)")
        return {"ok": True, "issue_id": issue_id, "already": True, "branch": branch,
                "start_rev": rev, "log": log.lines}

    # ③ 기준 상태 — 깨끗한 main = origin/main
    if cur != MAIN:
        return _refuse(log, "base", f"지금 브랜치가 {cur} 다 — {MAIN} 에서 시작한다")
    rc, dirty = _git(repo, "status", "--porcelain")
    if rc != 0:
        return _refuse(log, "base", f"git status 실패: {dirty}")
    if dirty:
        n = len(dirty.splitlines())
        return _refuse(log, "base", f"작업 트리가 깨끗하지 않다({n}건) — 커밋·정리는 사람이 정한다",
                       dirty=dirty.splitlines()[:20])
    if fetch:
        rc, out = _git(repo, "fetch", "--quiet", REMOTE, MAIN)
        if rc != 0:
            return _refuse(log, "fetch", f"{REMOTE} fetch 실패: {out}")
        log("fetch", f"{REMOTE}/{MAIN} fetch")
    head = _git_ok(repo, "rev-parse", "HEAD")
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
    got = getter(issue_id)
    status = "진행" if isinstance(got, dict) and got.get("status") == "신규" else ""
    note = START_NOTE.format(rev=head, branch=branch)
    res = str(noter(issue_id, notes=note, status_name=status))
    if res.startswith("[주의]"):
        back = [_git(repo, "switch", MAIN), _git(repo, "branch", "-d", branch)]
        undone = all(rc == 0 for rc, _ in back)
        log("redmine", f"기록 실패 — {res} · 브랜치 되돌림 {'완료' if undone else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "redmine",
                "why": f"Redmine 기록 실패: {res}", "branch_rolled_back": undone,
                "log": log.lines}
    log("redmine", f"시작 리비전 기록 {head[:12]}" + (f" · 상태 {status}" if status else ""))
    return {"ok": True, "issue_id": issue_id, "already": False, "branch": branch,
            "start_rev": head, "redmine": res, "log": log.lines}


REVIEW_PRIORITY = 10            # 사람이 요청한 리뷰 — 자동 등재(0)보다 먼저 (`#638` 규약)
FINISH_NOTE = ("리뷰 요청: `{base}..{end}` (커밋 {n}건) · main 적용 `{end12}` · 브랜치 `{branch}` 삭제{deleted}\n"
               "{commits}\n리뷰 큐 등재: `range:{base12}..{end12}` ({state}) — 리뷰가 끝나면 이 일감에 노트로 남는다")


def _default_review_root() -> Path:
    from master.context_search.paths import resolve
    return Path(resolve("AXCluster").root)


def _default_enqueue(root, **kw) -> dict:
    from master.context_synth import review_queue as rq
    return rq.enqueue(root, **kw)


def _span(repo: Path, branch: str) -> tuple[str, str, list]:
    base = _git_ok(repo, "merge-base", MAIN, branch)
    end = _git_ok(repo, "rev-parse", branch)
    out = _git_ok(repo, "log", "--reverse", "--format=%H %s", f"{base}..{end}")
    return base, end, [ln for ln in out.splitlines() if ln.strip()]


def finish(issue_id, *, confirm: bool = False, repo=None, noter=None, enqueue=None,
           review_root=None, events_path=None, logf=None, fetch: bool = True) -> dict:
    """일감 작업을 마친다. `confirm=False` 면 보고만 한다(쓰기 0)."""
    repo = Path(repo or REPO)
    injected = noter is not None or enqueue is not None
    log = _Log("finish", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    noter = noter or _default_noter
    enqueue = enqueue or _default_enqueue
    branch = branch_name(issue_id)

    # ① 위치·상태
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    if cur != branch:
        return _refuse(log, "branch", f"지금 브랜치가 {cur} 다 — {branch} 에서 마친다")
    rc, dirty = _git(repo, "status", "--porcelain")
    if rc != 0 or dirty:
        return _refuse(log, "tree", f"작업 트리가 깨끗하지 않다 — 커밋·정리는 사람이 정한다",
                       dirty=(dirty or "").splitlines()[:20])
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
    files = _git_ok(repo, "diff", "--name-only", base, end).splitlines()
    summary = {"issue_id": issue_id, "branch": branch, "base": base, "end": end,
               "commits": commits, "files": len(files)}
    log("span", f"범위 {base[:12]}..{end[:12]} · 커밋 {len(commits)}건 · 파일 {len(files)}")

    if not confirm:
        log("preview", "confirm=False — 아무것도 바꾸지 않았다")
        return {"ok": True, "confirmed": False, **summary,
                "next": f"승인하면 finish({issue_id}, confirm=True) — push {REMOTE} {branch}:{MAIN} · "
                        f"로컬 {MAIN} ff · {branch} 삭제 · 범위 리뷰 등재 · Redmine 노트",
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
    # ③ 로컬 main 맞추기 → 브랜치 삭제
    deleted = False
    for args, label in ((("switch", MAIN), "switch"), (("merge", "--ff-only", end), "ff")):
        rc, out = _git(repo, *args)
        if rc != 0:
            problems.append(f"{label}: {out[-200:]}")
            log(label, f"실패 — {out[-200:]}")
            break
        done.append(label)
        log(label, f"{' '.join(args)}")
    else:
        rc, out = _git(repo, "branch", "-d", branch)
        if rc == 0:
            deleted = True
            done.append("delete_branch")
            log("delete_branch", f"{branch} 삭제(main 에서 도달 가능)")
        else:
            problems.append(f"branch -d: {out[-200:]}")
            log("delete_branch", f"실패 — {out[-200:]}")

    # ④ 범위 리뷰 등재
    state = "등재 실패"
    try:
        root = review_root or _default_review_root()
        item = enqueue(root, kind="range", key=f"{base}..{end}", files=files,
                       requester=f"issue_flow#{issue_id}", priority=REVIEW_PRIORITY,
                       meta={"issue_id": int(issue_id), "base": base, "end": end})
        state = item.get("state", "?")
        done.append("enqueue")
        log("enqueue", f"range:{base[:8]}..{end[:8]} {state}")
    except Exception as e:                              # noqa: BLE001
        problems.append(f"리뷰 등재: {type(e).__name__}: {e}")
        log("enqueue", f"실패 — {type(e).__name__}: {e}")

    # ⑤ Redmine
    lines = "\n".join(f"- `{c[:12]}` {c[41:]}" for c in commits)
    note = FINISH_NOTE.format(base=base, end=end, n=len(commits), end12=end[:12], branch=branch,
                              deleted="" if deleted else " 실패", commits=lines,
                              base12=base[:12], state=state)
    res = str(noter(issue_id, notes=note))
    if res.startswith("[주의]"):
        problems.append(f"Redmine: {res}")
        log("redmine", f"기록 실패 — {res}")
    else:
        done.append("redmine")
        log("redmine", "리뷰 요청 노트")
    return {"ok": not problems, "confirmed": True, **summary, "done": done,
            "why": " · ".join(problems), "log": log.lines}
