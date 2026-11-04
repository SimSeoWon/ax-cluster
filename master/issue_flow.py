"""일감 단위 작업 흐름 — `#879` (부모 `#826` Phase D).

    start(issue_id)                  플랜 판정 → 로컬 `issue/<N>` 브랜치 → 시작 리비전을 Redmine 에
    finish(issue_id, confirm=False)  범위 보고 → (승인 시) main 적용·push → 브랜치 삭제 →
                                     범위 리뷰 등재(`kind=range`) → Redmine 에 리뷰 요청 노트
    pause(issue_id)                  잠금 보류 → main 으로 → Redmine 「보류」 노트 (브랜치 유지)
    cancel(issue_id, confirm=False)  미리보기(쓰기 0) → (승인 시) 잠금 해제 · 「취소」 노트 ·
                                     `delete_branch=True` 일 때만 브랜치 삭제

`#883` 일감 하나씩: 활성 일감이 있으면 다른 일감의 `start` 는 거절한다(`master/issue_lock.py`).
보류된 일감은 `start` 를 다시 부르면 재개된다(브랜치로 옮기고 「재개」 노트). 잠금은 `finish` 뒤에도
남는다 — Redmine 「완료」 때 푼다(T4).
[중요] **잠금 위치(`lock_root`)** — 넘기면 그것을 쓴다. 안 넘기면 **아무것도 주입하지 않은 운영
호출만** AXCluster 트윈(`issue_lock.default_root()`)을 쓴다. getter·noter·enqueue 를 주입한 호출
(테스트 대역)이 `lock_root` 를 안 주면 **잠금을 쓰지 않는다**(`start`·`finish` 는 `[주의] 잠금 미사용`
로그만 남기고 이전처럼 돈다 · `pause`·`cancel` 은 잠금이 본체라 거절). `_resolve_events` 와 같은
원칙 — 대역 실행이 운영 상태를 건드리지 않게.

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
        except (OSError, TypeError, ValueError) as e:
            # `#881` R218-3 — 직렬화 불가 값(TypeError·ValueError)도 흐름을 바꾸지 않는다
            print(f"[issue_flow] [주의] 이벤트 기록 실패 {path}: {type(e).__name__}: {e}", file=sys.stderr)


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


def _call_redmine(fn, *a, **kw) -> str:
    """Redmine 호출 — 예외도 `[주의]` 문장으로 바꾼다(`#881` R216-4·R218-2·R216-5).

    `update_issue` 는 실패를 문장으로 돌려주지만 대역·네트워크 계층은 예외를 던질 수 있다. 예외가
    새면 `start` 는 방금 만든 브랜치를 되돌리지 못하고, `finish` 는 push 뒤 결과를 못 돌려준다.
    """
    try:
        return str(fn(*a, **kw))
    except Exception as e:                              # noqa: BLE001
        return f"[주의] Redmine 호출 예외 {type(e).__name__}: {e}"


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


_NO_LOCK = object()          # 주입 실행 + lock_root 없음 → 잠금 미사용


def _resolve_lock(lock_root, injected: bool):
    """잠금 위치. 주입 실행이 `lock_root` 를 안 주면 `_NO_LOCK`(운영 트윈을 건드리지 않는다).

    운영 호출에서 위치를 못 풀면 예외가 그대로 올라간다 — 호출자가 `lock` 단계 거절로 바꾼다
    (잠금을 못 읽은 채 시작하면 두 일감이 동시에 열린다 — fail-closed).
    """
    if lock_root is not None:
        return Path(lock_root)
    if injected:
        return _NO_LOCK
    from master import issue_lock as IL
    return IL.default_root()


def _lock_state(IL, root, n: int) -> tuple[dict | None, dict]:
    """(활성 기록 | None, N 의 보류 기록 | {})."""
    active = IL.current(root)
    rec = IL.paused(root).get(n) or {}
    return active, rec


def _busy_why(active: dict) -> str:
    h = active["issue_id"]
    return (f"#{h} 작업이 진행 중이다({active.get('branch')}) — 일감은 하나씩 한다. "
            f"#{h} 를 완료하거나, 보류(issue_pause) 또는 취소(issue_cancel)한 뒤 시작한다")


def _lock_logf(log: "_Log"):
    """`issue_lock` 의 줄을 같은 단계 로그(`lock`)로 흘린다."""
    return lambda line: log("lock", line)


def _clean(repo: Path) -> tuple[bool, list]:
    rc, dirty = _git(repo, "status", "--porcelain")
    if rc != 0:
        return False, [f"git status 실패: {dirty}"]
    return not dirty, dirty.splitlines()[:20]


def _branch_exists(repo: Path, branch: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0


RESUME_NOTE = "재개: 브랜치 `{branch}` (시작 리비전 `{rev}`) — 보류에서 이어서 작업한다"
PAUSE_NOTE = "보류: 브랜치 `{branch}` 유지 (끝 `{end}`), 재개는 issue_start — 잠금을 풀었다"


def start(issue_id, *, repo=None, getter=None, noter=None, events_path=None,
          logf=None, fetch: bool = True, lock_root=None) -> dict:
    """일감 작업을 시작한다 — 플랜 강제 → 잠금 확인 → 로컬 브랜치 → 시작 리비전 Redmine 기록.

    이미 `issue/<N>` 에 서 있으면 새로 만들지 않고 그 시작점(`main` 과의 merge-base)을 돌려준다
    (잠금에 없던 옛 브랜치도 이때 잠금에 올린다). N 이 보류 중이고 깨끗한 `main` 에 서 있으면
    `issue/<N>` 으로 옮기고 잠금을 재개한 뒤 「재개」 노트를 남긴다(`resumed: True`).
    """
    from master import issue_lock as IL
    from master import plan_start as ST
    repo = Path(repo or REPO)
    injected = getter is not None or noter is not None
    log = _Log("start", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    getter = getter or _default_getter
    noter = noter or _default_noter
    branch = branch_name(issue_id)
    n = int(issue_id)
    llog = _lock_logf(log)

    # ① 플랜 강제
    try:
        verdict = ST.start_issue(issue_id, getter=getter)
    except Exception as e:                              # noqa: BLE001
        return _refuse(log, "plan", f"이슈를 읽지 못했다 — 예외 {type(e).__name__}: {e}")
    if "error" in verdict:
        return _refuse(log, "plan", f"이슈를 읽지 못했다 — {verdict['error']}")
    if not verdict.get("ok"):
        return _refuse(log, "plan", f"플랜 판정 {verdict.get('verdict')} — {verdict.get('next_action', '')}",
                       verdict=verdict.get("verdict"))
    log("plan", f"판정 {verdict.get('verdict')} · 태스크 {', '.join(verdict.get('tasks') or []) or '-'}")

    # ①-1 잠금 — 다른 일감이 활성이면 아무것도 바꾸지 않고 거절 (`#883`)
    try:
        lroot = _resolve_lock(lock_root, injected)
        if lroot is _NO_LOCK:
            active, prec = None, {}
            log("lock", "[주의] 잠금 미사용 — 대역 주입 실행에 lock_root 가 없다")
        else:
            active, prec = _lock_state(IL, lroot, n)
    except Exception as e:                              # noqa: BLE001 — IssueLockError·경로 해석
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")
    if active and active["issue_id"] != n:
        return _refuse(log, "lock", _busy_why(active), holder=active["issue_id"])
    if lroot is not _NO_LOCK:
        log("lock", f"#{n} 이미 활성" if active else (f"빈 자리 · #{n} 보류 중" if prec else "빈 자리"))

    def _acquire(start_rev: str, why: str) -> dict:
        if lroot is _NO_LOCK:
            return {"ok": True, "skipped": True}
        try:
            return IL.acquire(lroot, n, branch=branch, start_rev=start_rev, by="issue_flow.start",
                              why=why, logf=llog)
        except Exception as e:                          # noqa: BLE001
            return {"ok": False, "reason": "error", "why": f"{type(e).__name__}: {e}"}

    def _lock_kind(res: dict) -> str:
        if res.get("skipped"):
            return "none"
        return "already" if res.get("already") else ("resumed" if res.get("resumed") else "acquired")

    # ② 이미 시작했나
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
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
            kind = _lock_kind(got)
            log("branch", f"이미 {branch} 에 있다 — 시작 리비전 {rev[:12]} (새 기록 없음 · 잠금 {kind})")
            return {"ok": True, "issue_id": issue_id, "already": True, "branch": branch,
                    "start_rev": rev, "lock": kind, "log": log.lines}
        if not prec:
            return _refuse(log, "branch", f"{branch} 가 이미 있는데 지금 브랜치는 {cur} 다 — "
                                          "그 브랜치로 옮겨 이어 가거나 정리 여부를 사람이 정한다")
        return _resume(issue_id, repo=repo, cur=cur, branch=branch, prec=prec, noter=noter,
                       acquire=_acquire, lroot=lroot, log=log, llog=llog)

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
    try:
        got = getter(issue_id)
    except Exception:                                   # noqa: BLE001 — 상태 판정용 읽기일 뿐이다
        got = None
    status = "진행" if isinstance(got, dict) and got.get("status") == "신규" else ""
    note = START_NOTE.format(rev=head, branch=branch)
    res = _call_redmine(noter, issue_id, notes=note, status_name=status)
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
            "start_rev": head, "redmine": res, "lock": _lock_kind(got), "log": log.lines}


def _resume(issue_id, *, repo: Path, cur: str, branch: str, prec: dict, noter, acquire,
            lroot, log: _Log, llog) -> dict:
    """보류 중인 N 을 재개 — 깨끗한 main → `switch issue/N` → 잠금 재개 → 「재개」 노트.

    노트가 실패하면 main 으로 되돌아가고 잠금을 다시 보류로 둔다(undo).
    """
    from master import issue_lock as IL
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
    rev = prec.get("start_rev") or ""
    got = acquire(rev, "보류 재개")
    if not got.get("ok"):
        rc2, out2 = _git(repo, "switch", MAIN)
        log("lock", f"재개 실패 — {got.get('why')} · {MAIN} 복귀 {'완료' if rc2 == 0 else '실패: ' + out2}")
        return {"ok": False, "issue_id": issue_id, "step": "lock", "why": got.get("why", "잠금 실패"),
                "holder": got.get("holder"), "switched_back": rc2 == 0, "log": log.lines}
    rec = got.get("record") or {}
    rev = rec.get("start_rev") or rev
    note = RESUME_NOTE.format(branch=branch, rev=rev)
    res = _call_redmine(noter, issue_id, notes=note)
    if res.startswith("[주의]"):
        rc2, out2 = _git(repo, "switch", MAIN)
        try:
            back = IL.pause(lroot, n, by="issue_flow.start", why="재개 노트 실패 — 되돌림", logf=llog)
            relocked = bool(back.get("ok"))
        except Exception as e:                          # noqa: BLE001
            relocked = False
            log("lock", f"보류 되돌림 예외 — {type(e).__name__}: {e}")
        log("redmine", f"재개 노트 실패 — {res} · {MAIN} 복귀 {'완료' if rc2 == 0 else '실패: ' + out2}"
                       f" · 잠금 보류 복원 {'완료' if relocked else '실패'}")
        return {"ok": False, "issue_id": issue_id, "step": "redmine",
                "why": f"Redmine 재개 노트 실패: {res} — 재개를 되돌렸다"
                       f"({MAIN} 복귀 {'완료' if rc2 == 0 else '실패'} · 보류 복원 {'완료' if relocked else '실패'})",
                "switched_back": rc2 == 0, "relocked": relocked, "log": log.lines}
    log("redmine", f"재개 노트 · 시작 리비전 {str(rev)[:12]}")
    return {"ok": True, "issue_id": issue_id, "already": False, "resumed": True, "branch": branch,
            "start_rev": rev, "redmine": res, "lock": "resumed", "log": log.lines}


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
           review_root=None, events_path=None, logf=None, fetch: bool = True,
           lock_root=None) -> dict:
    """일감 작업을 마친다. `confirm=False` 면 보고만 한다(쓰기 0).

    `#883`: N 이 보류 중이면(먼저 재개) · 다른 일감이 활성이면 거절한다. 잠금에 없는 N(`#883` 이전
    시작)은 `[주의]` 로그만 남기고 진행한다. **잠금은 여기서 풀지 않는다** — Redmine 「완료」 때(T4).
    """
    from master import issue_lock as IL
    repo = Path(repo or REPO)
    injected = noter is not None or enqueue is not None
    log = _Log("finish", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    noter = noter or _default_noter
    enqueue = enqueue or _default_enqueue
    branch = branch_name(issue_id)
    n = int(issue_id)

    # ⓪ 잠금
    try:
        lroot = _resolve_lock(lock_root, injected)
        if lroot is _NO_LOCK:
            log("lock", "[주의] 잠금 미사용 — 대역 주입 실행에 lock_root 가 없다")
        else:
            active, prec = _lock_state(IL, lroot, n)
            if prec:
                return _refuse(log, "lock", f"#{n} 는 보류 중이다 — issue_start 로 재개한 뒤 마친다")
            if active and active["issue_id"] != n:
                return _refuse(log, "lock", f"#{active['issue_id']} 가 활성이다({active.get('branch')}) — "
                                            f"#{n} 는 잠금에 없다, 일감은 하나씩 마친다",
                               holder=active["issue_id"])
            if active:
                log("lock", f"#{n} 활성 — 잠금은 Redmine 완료 때 푼다(여기서 유지)")
            else:
                log("lock", f"[주의] 잠금 기록 없음 — #{n} 는 #883 이전 시작으로 보고 진행한다")
    except Exception as e:                              # noqa: BLE001
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")

    # ① 위치·상태
    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    if cur != branch:
        return _refuse(log, "branch", f"지금 브랜치가 {cur} 다 — {branch} 에서 마친다")
    rc, dirty = _git(repo, "status", "--porcelain")
    if rc != 0 or dirty:
        return _refuse(log, "tree", "작업 트리가 깨끗하지 않다 — 커밋·정리는 사람이 정한다",
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
    try:
        files = _git_ok(repo, "diff", "--name-only", base, end).splitlines()
    except IssueFlowError as e:
        return _refuse(log, "span", str(e))
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
    res = _call_redmine(noter, issue_id, notes=note)
    if res.startswith("[주의]"):
        problems.append(f"Redmine: {res}")
        log("redmine", f"기록 실패 — {res}")
    else:
        done.append("redmine")
        log("redmine", "리뷰 요청 노트")
    return {"ok": not problems, "confirmed": True, **summary, "done": done,
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


def pause(issue_id, *, repo=None, noter=None, lock_root=None, events_path=None, logf=None) -> dict:
    """활성 일감을 보류한다 — `issue/<N>` 의 깨끗한 트리 → 잠금 보류 → `main` 으로 → 「보류」 노트.

    브랜치는 남는다. 재개는 `start(N)` 이다. [중요] dirty 면 거절한다 — 미커밋 변경이 `main` 으로
    따라간다. `main` 전환이 실패하면 잠금을 다시 활성으로 되돌린다. 노트만 실패하면 보류 상태는
    유지하고(잠금이 정본) `ok: False` 로 알린다.
    """
    from master import issue_lock as IL
    repo = Path(repo or REPO)
    injected = noter is not None
    log = _Log("pause", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    noter = noter or _default_noter
    branch = branch_name(issue_id)
    n = int(issue_id)
    llog = _lock_logf(log)
    lroot, refused = _lock_required(lock_root, injected, log)
    if refused:
        return refused

    rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return _refuse(log, "repo", f"저장소를 못 읽었다: {cur}")
    if cur != branch:
        return _refuse(log, "branch", f"지금 브랜치가 {cur} 다 — {branch} 에서 보류한다")
    ok, lines = _clean(repo)
    if not ok:
        return _refuse(log, "tree", f"작업 트리가 깨끗하지 않다({len(lines)}건) — 미커밋 변경이 {MAIN} 으로 "
                                    "따라간다, 커밋·정리는 사람이 정한다", dirty=lines)
    end = _git(repo, "rev-parse", "HEAD")[1]
    try:
        got = IL.pause(lroot, n, by="issue_flow.pause", why="보류 요청", logf=llog)
    except Exception as e:                              # noqa: BLE001
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")
    if not got.get("ok"):
        return _refuse(log, "lock", got.get("why", "잠금 보류 실패"), holder=got.get("holder"))
    rec = got.get("record") or {}

    rc, out = _git(repo, "switch", MAIN)
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
    log("switch", f"{branch} → {MAIN} · {branch} 유지 @ {end[:12]}")

    res = _call_redmine(noter, issue_id, notes=PAUSE_NOTE.format(branch=branch, end=end))
    base = {"issue_id": issue_id, "paused": True, "branch": branch, "end": end,
            "start_rev": rec.get("start_rev")}
    if res.startswith("[주의]"):
        log("redmine", f"보류 노트 실패 — {res} · 보류 상태는 유지(잠금이 정본)")
        return {"ok": False, **base, "step": "redmine",
                "why": f"Redmine 보류 노트 실패: {res} — 보류(잠금 해제·{MAIN} 전환)는 이미 됐고 유지한다, "
                       "노트는 사람이 남긴다", "log": log.lines}
    log("redmine", "보류 노트")
    return {"ok": True, **base, "redmine": res, "log": log.lines}


CANCEL_NOTE = "취소: 잠금 해제 · 브랜치 `{branch}` {fate}\n{commits}"


def cancel(issue_id, *, confirm: bool = False, delete_branch: bool = False, repo=None, noter=None,
           lock_root=None, events_path=None, logf=None) -> dict:
    """일감을 취소한다. `confirm=False`(기본)는 미리보기만 한다(쓰기 0).

    승인 시: `issue/<N>` 에 서 있으면 깨끗한지 보고 `main` 으로 → 잠금 해제(`op=cancel`) → 「취소」 노트
    → `delete_branch=True` **일 때만** `branch -D`. [중요] 노트가 실패하면 브랜치를 지우지 않는다 —
    지울 커밋 목록이 어디에도 안 남는다. 잠금에 없는 N 은 브랜치가 있을 때만 받는다(옛 브랜치 정리).
    """
    from master import issue_lock as IL
    repo = Path(repo or REPO)
    injected = noter is not None
    log = _Log("cancel", issue_id, events_path=_resolve_events(events_path, injected), logf=logf)
    noter = noter or _default_noter
    branch = branch_name(issue_id)
    n = int(issue_id)
    llog = _lock_logf(log)
    lroot, refused = _lock_required(lock_root, injected, log)
    if refused:
        return refused

    try:
        active, prec = _lock_state(IL, lroot, n)
    except Exception as e:                              # noqa: BLE001
        return _refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}")
    lock_state = "active" if active and active["issue_id"] == n else ("paused" if prec else "absent")
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
                        + ("잠금 해제(cancel) · " if lock_state != "absent" else "")
                        + f"Redmine 취소 노트 · {fate}"
                        + ("" if delete_branch else " (삭제는 delete_branch=True 일 때만)"),
                "log": log.lines}

    done: list[str] = []
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
    if lock_state != "absent":
        try:
            got = IL.release(lroot, n, op="cancel", by="issue_flow.cancel", why="취소 요청", logf=llog)
        except Exception as e:                          # noqa: BLE001
            got = {"ok": False, "why": f"{type(e).__name__}: {e}"}
        if not got.get("ok"):
            log("lock", f"해제 실패 — {got.get('why')}")
            return {"ok": False, "confirmed": True, **summary, "step": "lock",
                    "why": f"잠금 해제 실패: {got.get('why')}", "done": done, "log": log.lines}
        done.append("release")
    else:
        log("lock", "[주의] 잠금 기록 없음 — 해제할 것 없음")

    will_delete = bool(delete_branch and exists)
    fate = "삭제(branch -D)" if will_delete else "유지"
    lines_ = "\n".join(f"- `{c[:12]}` {c[41:]}" + (" (로컬에만)" if c[:40] in local_only else "")
                       for c in commits) or "- (main 밖 커밋 없음)"
    res = _call_redmine(noter, issue_id, notes=CANCEL_NOTE.format(branch=branch, fate=fate, commits=lines_))
    if res.startswith("[주의]"):
        log("redmine", f"취소 노트 실패 — {res}" + (" · 브랜치 삭제 안 함" if will_delete else ""))
        return {"ok": False, "confirmed": True, **summary, "step": "redmine",
                "why": f"Redmine 취소 노트 실패: {res} — 잠금 해제는 됐다"
                       + (f", 커밋 목록이 기록되지 않아 {branch} 는 지우지 않았다" if will_delete else ""),
                "branch_deleted": False, "done": done, "log": log.lines}
    done.append("redmine")
    log("redmine", f"취소 노트 · 브랜치 {fate}")

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
