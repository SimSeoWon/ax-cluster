"""일감 흐름의 인프라 쪽 — 플랜 판정·잠금·마감 추적·Redmine 노트 (`#884` T6). **git 은 만지지 않는다.**

같은 규칙을 두 표면이 쓴다 (사용자 결정 2026-11-04 — 마스터 세션과 `.33` 세션이 똑같이 동작한다):

    마스터 로컬   `ax-projects` MCP → `issue_flow.start/finish/pause/cancel`
                  git(브랜치·push·삭제)은 `issue_flow` 가 하고, 나머지는 이 모듈 함수를 부른다
    `.33` 요청자  `ax-client` → 8101 `POST /api/v1/issue/{start,finish,pause,cancel}` → `infra_*`
                  git 은 요청자가 자기 worktree 에서 하고(`ax-issue` 스킬), 인프라는 기록만 한다

    infra_start(project, N, branch=, start_rev=, check_only=False)
        플랜 판정 → 잠금 확인 → (check_only 면 여기서 끝 · 쓰기 0)
        → 이미 활성이면 기록 없음 · 보류면 재개(잠금 → 「재개」 노트) · 아니면 시작 노트 → 잠금
    infra_finish(project, N, base=, end=, hashes=, subjects=)
        잠금 보유 확인 → `issue_track.register` → `issue_link.link_round` →
        잠금 해제(op=finish, **등록 성공 시만**) → 「리뷰 요청」 노트(로컬 finish 와 같은 틀)
    infra_pause(project, N, end=)          잠금 보류 → 「보류」 노트
    infra_cancel(project, N, confirm=…)    미리보기(쓰기 0) → (승인 시) 잠금 해제 → 「취소」 노트

[중요] **위치는 프로젝트 트윈 루트다** — 잠금(`issue_lock.json`)·마감 추적(`issue_track.json`)·
흐름 로그(`issue_flow.jsonl`)가 `master.context_search.paths.resolve(project).root` 아래에 있다.
원격 호출은 프로젝트를 반드시 싣는다(서버가 마운트 관문을 먼저 건다). 마스터 로컬 흐름의 기본은
종전대로 AXCluster 다.
[중요] **`base..end`·해시 목록·push 여부는 요청자의 보고다** — 인프라는 형식(40자리 해시)과
일관성(`end` 가 마지막 해시 · `base` 가 목록 밖)만 검사하고, 받은 값을 노트·추적 기록에 그대로
남긴다. 그 커밋이 실제로 `main` 에 있는지는 색인기·리뷰 큐가 미러에서 다시 본다.
[주의] 이 모듈의 노트 문장은 사실만 싣는다 — 자동 경로 글에 명령형을 쓰지 않는다(`CLAUDE.md`).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

BRANCH_PREFIX = "issue/"
EVENTS_NAME = "issue_flow.jsonl"
START_NOTE = "작업 시작 리비전: `{rev}` · 브랜치 `{branch}`"
RESUME_NOTE = "재개: 브랜치 `{branch}` (시작 리비전 `{rev}`) — 보류에서 이어서 작업한다"
PAUSE_NOTE = "보류: 브랜치 `{branch}` 유지 (끝 `{end}`), 재개는 issue_start — 잠금을 풀었다"
CANCEL_NOTE = "취소: 잠금 해제 · 브랜치 `{branch}` {fate}\n{commits}"
FINISH_NOTE = ("리뷰 요청: `{base}..{end}` (커밋 {n}건) · main 적용 `{end12}` · 브랜치 `{branch}` 삭제{deleted}\n"
               "{commits}\n"
               "마감 추적: {track}\n"
               "일감 잠금: {lock}\n"
               "일감 상태: {state}")
# `#889` (사용자 결정 2026-11-06·11-07) — main 적용 = 「완료」. 마감 추적 등록이 성공해야 닫는다(잠금 해제와 같은 조건).
CLOSE_STATUS, CLOSE_RATIO = "완료", 100
STATE_CLOSE = "「완료」·100 — main 적용으로 마감(#889). 리뷰는 끝나는 대로 이 일감에 노트로만 붙는다"
STATE_OPEN = "열어 둔다 — 마감 추적 등록이 실패해 닫지 않았다(리뷰가 이어지지 않은 채 닫히지 않게)"
STATE_CLOSE_FAIL = "닫기 실패 — {why}. 사람이 확인한다(main 적용은 끝났다)"
TRACK_OK = ("라운드 {round} 에 해시 {n}개 등록{already} — 해시별 커밋 리뷰가 끝날 때마다 이 일감에 진행 노트가 "
            "남고, 모두 끝나면 `{base12}..{end12}` 종합 리뷰 1회의 결과가 노트로 남는다")
TRACK_FAIL = "등록 실패 — {why}. 해시별·종합 리뷰가 이 일감에 이어지지 않는다"
REMOTE_DELETED = " (요청자 작업 트리가 등록 뒤 정리)"   # 원격 finish — 브랜치 정리는 등록 뒤 요청자 몫

_SHA = re.compile(r"^[0-9a-f]{40}$")
NO_LOCK = object()          # 주입 실행 + lock_root 없음 → 잠금 미사용


def branch_name(issue_id) -> str:
    return f"{BRANCH_PREFIX}{int(issue_id)}"


def project_root(project: str) -> Path:
    """프로젝트 트윈 루트 — 잠금·마감 추적·흐름 로그의 자리."""
    from master.context_search.paths import resolve
    return Path(resolve(project).root)


# ── 로그·거절·Redmine 호출 ─────────────────────────────────────────────────────

class Log:
    """단계 로그 — 목록 + jsonl + (선택) 호출자 logf."""

    def __init__(self, op: str, issue_id, *, events_path=None, logf=None, tag: str = "issue_flow"):
        self.op, self.issue_id, self.lines = op, issue_id, []
        self.events_path, self.logf, self.tag = events_path, logf, tag

    def __call__(self, step: str, msg: str, **extra) -> None:
        line = f"[{self.tag}] #{self.issue_id} {self.op}.{step}: {msg}"
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
            print(f"[{self.tag}] [주의] 이벤트 기록 실패 {path}: {type(e).__name__}: {e}", file=sys.stderr)


def refuse(log: Log, step: str, why: str, **extra) -> dict:
    log(step, f"거절 — {why}")
    return {"ok": False, "issue_id": log.issue_id, "step": step, "why": why,
            "log": log.lines, **extra}


def default_getter(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)


def default_noter(issue_id, *, notes: str, status_name: str = "", done_ratio=None) -> str:
    from master import redmine
    return redmine.update_issue(issue_id, notes=notes, status_name=status_name, done_ratio=done_ratio)


def call_redmine(fn, *a, **kw) -> str:
    """Redmine 호출 — 예외도 `[주의]` 문장으로 바꾼다(`#881` R216-4·R218-2·R216-5)."""
    try:
        return str(fn(*a, **kw))
    except Exception as e:                              # noqa: BLE001
        return f"[주의] Redmine 호출 예외 {type(e).__name__}: {e}"


# ── 잠금 ──────────────────────────────────────────────────────────────────────

def resolve_lock(lock_root, injected: bool, project: str = ""):
    """잠금 위치. 주입 실행이 `lock_root` 를 안 주면 `NO_LOCK`(운영 트윈을 건드리지 않는다).

    운영 호출에서 위치를 못 풀면 예외가 그대로 올라간다 — 호출자가 `lock` 단계 거절로 바꾼다.
    `project` 를 비우면 AXCluster(마스터 로컬 흐름의 종전 기본값).
    """
    if lock_root is not None:
        return Path(lock_root)
    if injected:
        return NO_LOCK
    from master import issue_lock as IL
    return IL.default_root(project) if project else IL.default_root()


def lock_state(root, n: int) -> tuple[dict | None, dict]:
    """(활성 기록 | None, N 의 보류 기록 | {})."""
    from master import issue_lock as IL
    return IL.current(root), (IL.paused(root).get(n) or {})


def busy_why(active: dict) -> str:
    h = active["issue_id"]
    return (f"#{h} 작업이 진행 중이다({active.get('branch')}) — 일감은 하나씩 한다. "
            f"#{h} 를 완료하거나, 보류(issue_pause) 또는 취소(issue_cancel)한 뒤 시작한다")


def lock_logf(log: Log):
    """`issue_lock` 의 줄을 같은 단계 로그(`lock`)로 흘린다."""
    return lambda line: log("lock", line)


def acquire(lroot, n: int, *, branch: str, start_rev: str, why: str, by: str, log: Log) -> dict:
    """N 을 활성으로. `NO_LOCK` 이면 `skipped`. 예외는 `ok: False` 로 바꾼다."""
    from master import issue_lock as IL
    if lroot is NO_LOCK:
        return {"ok": True, "skipped": True}
    try:
        return IL.acquire(lroot, n, branch=branch, start_rev=start_rev, by=by, why=why,
                          logf=lock_logf(log))
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "reason": "error", "why": f"{type(e).__name__}: {e}"}


def lock_kind(res: dict) -> str:
    if res.get("skipped"):
        return "none"
    return "already" if res.get("already") else ("resumed" if res.get("resumed") else "acquired")


# ── 시작 ──────────────────────────────────────────────────────────────────────

def plan_gate(issue_id, *, getter, log: Log) -> tuple[dict | None, dict]:
    """플랜 강제 — `plan_start` 판정이 ok 가 아니면 거절. `(거절 | None, 판정)`."""
    from master import plan_start as ST
    try:
        verdict = ST.start_issue(issue_id, getter=getter)
    except Exception as e:                              # noqa: BLE001
        return refuse(log, "plan", f"이슈를 읽지 못했다 — 예외 {type(e).__name__}: {e}"), {}
    if "error" in verdict:
        return refuse(log, "plan", f"이슈를 읽지 못했다 — {verdict['error']}"), verdict
    if not verdict.get("ok"):
        return refuse(log, "plan", f"플랜 판정 {verdict.get('verdict')} — {verdict.get('next_action', '')}",
                      verdict=verdict.get("verdict")), verdict
    log("plan", f"판정 {verdict.get('verdict')} · 태스크 {', '.join(verdict.get('tasks') or []) or '-'}")
    return None, verdict


def lock_gate(lroot, n: int, *, log: Log) -> tuple[dict | None, dict | None, dict]:
    """시작 잠금 검사 — 다른 일감이 활성이면 거절. `(거절 | None, 활성, N 의 보류 기록)`."""
    try:
        if lroot is NO_LOCK:
            active, prec = None, {}
            log("lock", "[주의] 잠금 미사용 — 대역 주입 실행에 lock_root 가 없다")
        else:
            active, prec = lock_state(lroot, n)
    except Exception as e:                              # noqa: BLE001 — IssueLockError·경로 해석
        return refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}"), None, {}
    if active and active["issue_id"] != n:
        return refuse(log, "lock", busy_why(active), holder=active["issue_id"]), active, prec
    if lroot is not NO_LOCK:
        log("lock", f"#{n} 이미 활성" if active else (f"빈 자리 · #{n} 보류 중" if prec else "빈 자리"))
    return None, active, prec


def start_note(issue_id, *, branch: str, start_rev: str, getter, noter) -> tuple[str, str]:
    """시작 리비전 노트 — 신규 일감이면 상태를 「진행」으로. `(결과 문장, 바꾼 상태)`."""
    try:
        got = getter(issue_id)
    except Exception:                                   # noqa: BLE001 — 상태 판정용 읽기일 뿐이다
        got = None
    status = "진행" if isinstance(got, dict) and got.get("status") == "신규" else ""
    res = call_redmine(noter, issue_id, notes=START_NOTE.format(rev=start_rev, branch=branch),
                       status_name=status)
    return res, status


def resume_record(issue_id, *, lroot, branch: str, prec: dict, noter, log: Log, by: str) -> dict:
    """보류 재개의 기록 쪽 — 잠금 재개 → 「재개」 노트. 노트가 실패하면 잠금을 다시 보류로 둔다.

    돌려주는 `step`: 성공이면 없음 · `lock`(재개 실패) · `redmine`(노트 실패 — `relocked` 동반).
    git 되돌림(로컬의 main 복귀)은 호출자 몫이다.
    """
    from master import issue_lock as IL
    n = int(issue_id)
    rev = prec.get("start_rev") or ""
    got = acquire(lroot, n, branch=branch, start_rev=rev, why="보류 재개", by=by, log=log)
    if not got.get("ok"):
        return {"ok": False, "step": "lock", "why": got.get("why", "잠금 실패"), "holder": got.get("holder")}
    rec = got.get("record") or {}
    rev = rec.get("start_rev") or rev
    res = call_redmine(noter, issue_id, notes=RESUME_NOTE.format(branch=branch, rev=rev))
    if res.startswith("[주의]"):
        try:
            back = IL.pause(lroot, n, by=by, why="재개 노트 실패 — 되돌림", logf=lock_logf(log))
            relocked = bool(back.get("ok"))
        except Exception as e:                          # noqa: BLE001
            relocked = False
            log("lock", f"보류 되돌림 예외 — {type(e).__name__}: {e}")
        return {"ok": False, "step": "redmine", "res": res, "relocked": relocked, "start_rev": rev}
    return {"ok": True, "res": res, "start_rev": rev}


def _sha(v) -> str:
    return str(v or "").strip().lower()


def infra_start(project: str, issue_id, *, branch: str = "", start_rev: str = "", check_only: bool = False,
                getter=None, noter=None, lock_root=None, events_path=None, logf=None) -> dict:
    """요청자(`.33`)의 일감 시작 기록 — 브랜치·worktree 는 요청자가 이미 만들었다(또는 만들 참이다).

    `check_only=True` 는 플랜 판정과 잠금 상태만 돌려준다(쓰기 0) — 요청자는 이것이 ok 일 때
    worktree 를 만든다. 실제 기록 호출은 `branch == issue/<N>` 과 40자리 `start_rev` 를 싣는다.
    """
    log, lroot, refused = _remote_setup("start", project, issue_id, getter=getter, noter=noter,
                                        lock_root=lock_root, events_path=events_path, logf=logf)
    if refused:
        return refused
    getter = getter or default_getter
    noter = noter or default_noter
    n = int(issue_id)
    want = branch_name(n)
    bad, verdict = plan_gate(issue_id, getter=getter, log=log)
    if bad:
        return {**bad, "project": project}
    bad, active, prec = lock_gate(lroot, n, log=log)
    if bad:
        return {**bad, "project": project}
    state = "active" if active else ("paused" if prec else "free")
    base = {"issue_id": n, "project": project, "branch": want, "verdict": verdict.get("verdict"),
            "tasks": verdict.get("tasks") or [], "lock_state": state}
    if check_only:
        log("check", f"점검만 — 잠금 {state} · 쓰기 0")
        out = {"ok": True, "check_only": True, **base, "log": log.lines}
        if prec:
            out["paused"] = {"branch": prec.get("branch"), "start_rev": prec.get("start_rev")}
        if active:
            out["active"] = {"branch": active.get("branch"), "start_rev": active.get("start_rev")}
        return out
    if (branch or "").strip() != want:
        return refuse(log, "branch", f"브랜치는 {want} 다(받은 값 {branch!r})", project=project)
    rev = _sha(start_rev)
    if active:                                           # 같은 N 이 이미 활성 — 기록 없음
        have = str(active.get("start_rev") or "")
        log("lock", f"#{n} 이미 활성 — 새 기록 없음 · 시작 {have[:12]}")
        out = {"ok": True, "already": True, **base, "start_rev": have, "lock": "already", "log": log.lines}
        if rev and have and rev != have:
            out["warning"] = f"보고한 시작 리비전 {rev[:12]} 이 잠금 기록 {have[:12]} 과 다르다 — 잠금 기록을 유지했다"
            log("lock", f"[주의] {out['warning']}")
        return out
    if prec:                                             # 보류 재개 — 잠금 → 「재개」 노트
        got = resume_record(issue_id, lroot=lroot, branch=want, prec=prec, noter=noter, log=log,
                            by="issue_infra.start")
        if not got["ok"]:
            if got["step"] == "lock":
                return refuse(log, "lock", f"재개 실패 — {got['why']}", holder=got.get("holder"), project=project)
            log("redmine", f"재개 노트 실패 — {got['res']} · 잠금 보류 복원 {'완료' if got['relocked'] else '실패'}")
            return {"ok": False, **base, "step": "redmine",
                    "why": f"Redmine 재개 노트 실패: {got['res']} — 재개를 되돌렸다"
                           f"(보류 복원 {'완료' if got['relocked'] else '실패'})",
                    "relocked": got["relocked"], "log": log.lines}
        log("redmine", f"재개 노트 · 시작 리비전 {str(got['start_rev'])[:12]}")
        return {"ok": True, **base, "resumed": True, "start_rev": got["start_rev"], "redmine": got["res"],
                "lock": "resumed", "log": log.lines}
    if not _SHA.match(rev):
        return refuse(log, "rev", f"start_rev 가 40자리 해시가 아니다 — {start_rev!r}", project=project)
    res, status = start_note(issue_id, branch=want, start_rev=rev, getter=getter, noter=noter)
    if res.startswith("[주의]"):
        log("redmine", f"기록 실패 — {res}")
        return {"ok": False, **base, "step": "redmine", "why": f"Redmine 기록 실패: {res}",
                "log": log.lines}
    log("redmine", f"시작 리비전 기록 {rev[:12]}" + (f" · 상태 {status}" if status else ""))
    got = acquire(lroot, n, branch=want, start_rev=rev, why="요청자 시작", by="issue_infra.start", log=log)
    if not got.get("ok"):
        log("lock", f"잠금 실패 — {got.get('why')}")
        return {"ok": False, **base, "step": "lock",
                "why": f"잠금 실패: {got.get('why')} — [주의] Redmine 시작 노트는 이미 기록됐다({rev[:12]})",
                "holder": got.get("holder"), "redmine": res, "log": log.lines}
    return {"ok": True, "already": False, **base, "start_rev": rev, "redmine": res,
            "lock": lock_kind(got), "log": log.lines}


# ── 종료 ──────────────────────────────────────────────────────────────────────

def finish_lock_check(lroot, n: int, *, log: Log) -> tuple[dict | None, bool]:
    """종료 잠금 검사 — N 보류 중·다른 일감 활성이면 거절. `(거절 | None, 잠금 보유)`."""
    try:
        if lroot is NO_LOCK:
            log("lock", "[주의] 잠금 미사용 — 대역 주입 실행에 lock_root 가 없다")
            return None, False
        active, prec = lock_state(lroot, n)
        if prec:
            return refuse(log, "lock", f"#{n} 는 보류 중이다 — issue_start 로 재개한 뒤 마친다"), False
        if active and active["issue_id"] != n:
            return refuse(log, "lock", f"#{active['issue_id']} 가 활성이다({active.get('branch')}) — "
                                       f"#{n} 는 잠금에 없다, 일감은 하나씩 마친다",
                          holder=active["issue_id"]), False
        if active:
            log("lock", f"#{n} 활성 — 마감 추적 등록이 성공하면 이 단계 끝에서 푼다(op=finish)")
            return None, True
        log("lock", f"[주의] 잠금 기록 없음 — #{n} 는 #883 이전 시작으로 보고 진행한다")
        return None, False
    except Exception as e:                              # noqa: BLE001
        return refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}"), False


def default_register(root, issue_id, **kw) -> dict:
    from master.context_synth import issue_track as it
    return it.register(root, issue_id, **kw)


def default_link(root, issue_id, **kw) -> dict:
    from master.context_synth import issue_link as il
    return il.link_round(root, issue_id, **kw)


def finish_record(issue_id, *, project: str, track_root_fn, lroot, lock_held: bool, base: str, end: str,
                  commits: list, branch: str, deleted: str, register, link, noter, log: Log,
                  done: list, problems: list, by: str) -> dict:
    """종료의 기록 쪽 — 마감 추적 등록 → 리뷰 연결 → 잠금 해제(등록 성공 시만) → 「리뷰 요청」 노트 + 닫기.

    🔴 `#889` — 등록이 성공하면 같은 Redmine 갱신에서 「완료」·100 으로 닫는다(main 적용 = 마감). 등록이 실패하면
    열어 둔다. 닫기가 거절·실패하면(예: 잠금 해제 실패로 관문이 막음) 노트만 다시 보내 기록을 남기고
    `problems` 에 적는다 — push 는 되돌리지 않는다.

    `commits` 는 `"<40자리 sha> <제목>"` 줄 목록(순서대로). `track_root_fn()` 은 추적 루트를 돌려주거나
    예외를 던진다(등록 실패로 다룬다). `done`·`problems` 에 이어서 적는다.
    [중요] 등록이 실패하면 잠금을 풀지 않는다 — 리뷰가 어디에도 이어지지 않은 채 세션이 다음
    일감으로 가는 조용한 유실을 막는다. 노트·`why` 가 그 사실을 말한다.
    """
    from master import issue_lock as IL
    n = int(issue_id)
    hashes = [c[:40] for c in commits]
    registered, track_round, track_text, root = False, None, "", None
    try:
        root = track_root_fn()
        reg = register(root, n, project=project, base=base, end=end, hashes=hashes,
                       by=by, logf=lambda line: log("track", line))
        if not isinstance(reg, dict):
            raise RuntimeError(f"등록 반환 형식 오류: {reg!r}"[:200])
        if reg.get("ok"):
            registered, track_round = True, reg.get("round")
            done.append("register")
            log("register", f"라운드 {track_round} · 해시 {len(hashes)}개"
                            + (" (이미 등록)" if reg.get("already") else "") + f" · {root}")
            track_text = TRACK_OK.format(round=track_round, n=len(hashes),
                                         already=" (같은 범위가 이미 등록돼 있었다)" if reg.get("already") else "",
                                         base12=base[:12], end12=end[:12])
        else:
            why = f"{reg.get('reason', '?')}: {reg.get('why', '')}"
            problems.append(f"마감 추적 등록: {why}")
            log("register", f"거절 — {why}")
            track_text = TRACK_FAIL.format(why=why)
    except Exception as e:                              # noqa: BLE001 — IssueTrackError·경로 해석 포함
        why = f"{type(e).__name__}: {e}"
        problems.append(f"마감 추적 등록: {why}")
        log("register", f"실패 — {why}")
        track_text = TRACK_FAIL.format(why=why)

    if registered:                                      # 색인기가 이미 넣은 해시를 줍는다
        try:
            lk = link(root, n, logf=lambda line: log("link", line))
            if isinstance(lk, dict) and lk.get("ok"):
                done.append("link")
                log("link", f"이음 {len(lk.get('linked') or [])} · 큐에 없음 {len(lk.get('untouched') or [])}")
            else:
                why = (lk.get("why") or lk.get("reason") or lk.get("errors")) if isinstance(lk, dict) \
                    else f"반환 형식 오류 {lk!r}"
                problems.append(f"리뷰 연결: {str(why)[:200]}")
                log("link", f"[주의] 실패 — {str(why)[:200]} · 다음 동기화 회차가 다시 잇는다")
        except Exception as e:                          # noqa: BLE001
            problems.append(f"리뷰 연결: {type(e).__name__}: {e}")
            log("link", f"[주의] 예외 — {type(e).__name__}: {e} · 다음 동기화 회차가 다시 잇는다")

    if lroot is NO_LOCK:
        lock_text = "미사용(대역 실행)"
    elif not lock_held:
        lock_text = "기록 없음 — 해제할 것 없음(#883 이전 시작)"
        log("release", "잠금 기록 없음 — 해제할 것 없음")
    elif not registered:
        lock_text = "유지 — 마감 추적 등록이 실패해 풀지 않았다(리뷰가 이어지지 않은 채 다음으로 가지 않게)"
        log("release", "[중요] 등록 실패 — 잠금 유지")
    else:
        try:
            rel = IL.release(lroot, n, op="finish", by=by, why=f"마감 추적 라운드 {track_round} 등록",
                             logf=lock_logf(log))
        except Exception as e:                          # noqa: BLE001
            rel = {"ok": False, "why": f"{type(e).__name__}: {e}"}
        if rel.get("ok"):
            done.append("release")
            lock_text = "해제(finish) — 다음 일감을 시작할 수 있다"
            log("release", f"잠금 해제({rel.get('was', '?')}→없음)")
        else:
            problems.append(f"잠금 해제: {rel.get('why')}")
            lock_text = f"해제 실패 — {rel.get('why')}"
            log("release", f"실패 — {rel.get('why')}")

    lines = "\n".join(f"- `{c[:12]}` {c[41:]}" for c in commits)

    def _note(state: str) -> str:
        return FINISH_NOTE.format(base=base, end=end, n=len(commits), end12=end[:12], branch=branch,
                                  deleted=deleted, commits=lines, track=track_text, lock=lock_text, state=state)
    closed = False
    if registered:
        res = call_redmine(noter, issue_id, notes=_note(STATE_CLOSE),
                           status_name=CLOSE_STATUS, done_ratio=CLOSE_RATIO)
        if res.startswith("[주의]"):
            problems.append(f"Redmine 닫기: {res}")
            log("close", f"[주의] 「{CLOSE_STATUS}」 실패 — {res}")
            # 거절이면 노트도 안 붙었다 — 기록은 남긴다(노트만)
            res = call_redmine(noter, issue_id, notes=_note(STATE_CLOSE_FAIL.format(why=res[:300])))
        else:
            closed = True
            done.append("close")
            log("close", f"「{CLOSE_STATUS}」·{CLOSE_RATIO} — main 적용으로 마감(#889)")
    else:
        res = call_redmine(noter, issue_id, notes=_note(STATE_OPEN))
        log("close", "열어 둔다 — 마감 추적 등록 실패")
    if res.startswith("[주의]"):
        problems.append(f"Redmine: {res}")
        log("redmine", f"기록 실패 — {res}")
    else:
        done.append("redmine")
        log("redmine", "리뷰 요청 노트")
    return {"registered": registered, "round": track_round, "lock_released": "release" in done,
            "closed": closed, "redmine": res}


def infra_finish(project: str, issue_id, *, base: str, end: str, hashes, subjects=None, noter=None,
                 register=None, link=None, lock_root=None, events_path=None, logf=None) -> dict:
    """요청자의 일감 종료 기록 — 요청자가 `push origin issue/<N>:main` 을 마친 **뒤에** 부른다.

    `hashes` 는 `base..end` 의 커밋 해시(오래된 것부터), `subjects` 는 같은 순서의 제목(선택).
    인프라는 git 을 보지 않는다 — 형식·일관성만 검사하고 보고를 기록한다(모듈 머리말).
    """
    injected = any(x is not None for x in (noter, register, link))
    log, lroot, refused = _remote_setup("finish", project, issue_id, noter=noter, injected=injected,
                                        lock_root=lock_root, events_path=events_path, logf=logf)
    if refused:
        return refused
    n = int(issue_id)
    b, e = _sha(base), _sha(end)
    hs = [_sha(h) for h in (hashes or [])] if not isinstance(hashes, str) else []
    for name, v in (("base", b), ("end", e)):
        if not _SHA.match(v):
            return refuse(log, "span", f"{name} 가 40자리 해시가 아니다 — {v!r}", project=project)
    if not hs:
        return refuse(log, "span", "해시 목록이 비었다 — base..end 의 커밋 해시를 순서대로 싣는다", project=project)
    badh = [h for h in hs if not _SHA.match(h)]
    if badh:
        return refuse(log, "span", f"40자리가 아닌 해시 {len(badh)}개 — {badh[0]!r}", project=project)
    if hs[-1] != e:
        return refuse(log, "span", f"마지막 해시 {hs[-1][:12]} 가 end {e[:12]} 와 다르다", project=project)
    if b in hs:
        return refuse(log, "span", f"base {b[:12]} 가 해시 목록 안에 있다 — 범위는 base 를 빼고 센다",
                      project=project)
    subs = list(subjects or [])
    if subs and len(subs) != len(hs):
        return refuse(log, "span", f"subjects {len(subs)}개가 해시 {len(hs)}개와 다르다", project=project)
    commits = [f"{h} {str(subs[i]).splitlines()[0] if subs and str(subs[i]).strip() else ''}".rstrip()
               if subs else h for i, h in enumerate(hs)]
    bad, held = finish_lock_check(lroot, n, log=log)
    if bad:
        return {**bad, "project": project}
    branch = branch_name(n)
    log("span", f"요청자 보고 범위 {b[:12]}..{e[:12]} · 커밋 {len(hs)}건 (push 는 요청자가 했다고 보고)")
    done: list[str] = []
    problems: list[str] = []
    rootp = lroot if lroot is not NO_LOCK else None

    def track_root():
        if rootp is None:
            raise RuntimeError("대역 주입 실행에 lock_root 가 없다 — 운영 트윈을 건드리지 않는다")
        return rootp

    got = finish_record(issue_id, project=project, track_root_fn=track_root, lroot=lroot, lock_held=held,
                        base=b, end=e, commits=commits, branch=branch, deleted=REMOTE_DELETED,
                        register=register or default_register, link=link or default_link,
                        noter=noter or default_noter, log=log, done=done, problems=problems,
                        by="issue_infra.finish")
    return {"ok": not problems, "issue_id": n, "project": project, "branch": branch, "base": b, "end": e,
            "commits": commits, "done": done, **got, "why": " · ".join(problems), "log": log.lines}


# ── 보류·취소 ─────────────────────────────────────────────────────────────────

def pause_lock(lroot, n: int, *, log: Log, by: str) -> tuple[dict | None, dict]:
    """잠금 보류. `(거절 | None, 보류 기록)`."""
    from master import issue_lock as IL
    try:
        got = IL.pause(lroot, n, by=by, why="보류 요청", logf=lock_logf(log))
    except Exception as e:                              # noqa: BLE001
        return refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}"), {}
    if not got.get("ok"):
        return refuse(log, "lock", got.get("why", "잠금 보류 실패"), holder=got.get("holder")), {}
    return None, got.get("record") or {}


def pause_note(issue_id, *, branch: str, end: str, noter) -> str:
    return call_redmine(noter, issue_id, notes=PAUSE_NOTE.format(branch=branch, end=end))


def infra_pause(project: str, issue_id, *, end: str = "", noter=None, lock_root=None,
                events_path=None, logf=None) -> dict:
    """요청자의 보류 기록 — 잠금 보류 → 「보류」 노트. 브랜치·worktree 는 요청자 쪽에 그대로 남는다.

    노트만 실패하면 보류(잠금)는 유지하고 `ok: False` 로 알린다(잠금이 정본).
    """
    log, lroot, refused = _remote_setup("pause", project, issue_id, noter=noter, lock_root=lock_root,
                                        events_path=events_path, logf=logf, need_lock=True)
    if refused:
        return refused
    n = int(issue_id)
    branch = branch_name(n)
    e = _sha(end)
    if e and not _SHA.match(e):
        return refuse(log, "rev", f"end 가 40자리 해시가 아니다 — {end!r}", project=project)
    bad, rec = pause_lock(lroot, n, log=log, by="issue_infra.pause")
    if bad:
        return {**bad, "project": project}
    res = pause_note(issue_id, branch=branch, end=e or "?", noter=noter or default_noter)
    base = {"issue_id": n, "project": project, "paused": True, "branch": branch, "end": e,
            "start_rev": rec.get("start_rev")}
    if res.startswith("[주의]"):
        log("redmine", f"보류 노트 실패 — {res} · 보류 상태는 유지(잠금이 정본)")
        return {"ok": False, **base, "step": "redmine",
                "why": f"Redmine 보류 노트 실패: {res} — 보류(잠금 해제)는 이미 됐고 유지한다",
                "log": log.lines}
    log("redmine", "보류 노트")
    return {"ok": True, **base, "redmine": res, "log": log.lines}


def cancel_state(lroot, n: int) -> str:
    """`active` · `paused` · `absent` — 예외는 호출자가 거절로 바꾼다."""
    active, prec = lock_state(lroot, n)
    return "active" if active and active["issue_id"] == n else ("paused" if prec else "absent")


def cancel_record(issue_id, *, lroot, lock_state_: str, branch: str, commits: list, local_only: list,
                  will_delete: bool, noter, log: Log, done: list, by: str) -> dict:
    """취소의 기록 쪽 — 잠금 해제(op=cancel) → 「취소」 노트(커밋 목록 · 브랜치 운명).

    `{"ok", "step"?, "why"?, "res"?}`. 노트가 실패하면 호출자는 브랜치를 지우지 않는다 — 지울
    커밋 목록이 어디에도 안 남는다.
    """
    from master import issue_lock as IL
    n = int(issue_id)
    if lock_state_ != "absent":
        try:
            got = IL.release(lroot, n, op="cancel", by=by, why="취소 요청", logf=lock_logf(log))
        except Exception as e:                          # noqa: BLE001
            got = {"ok": False, "why": f"{type(e).__name__}: {e}"}
        if not got.get("ok"):
            log("lock", f"해제 실패 — {got.get('why')}")
            return {"ok": False, "step": "lock", "why": f"잠금 해제 실패: {got.get('why')}"}
        done.append("release")
    else:
        log("lock", "[주의] 잠금 기록 없음 — 해제할 것 없음")
    fate = "삭제(branch -D)" if will_delete else "유지"
    lines_ = "\n".join(f"- `{c[:12]}` {c[41:]}" + (" (로컬에만)" if c[:40] in local_only else "")
                       for c in commits) or "- (main 밖 커밋 없음)"
    res = call_redmine(noter, issue_id, notes=CANCEL_NOTE.format(branch=branch, fate=fate, commits=lines_))
    if res.startswith("[주의]"):
        log("redmine", f"취소 노트 실패 — {res}" + (" · 브랜치 삭제 안 함" if will_delete else ""))
        return {"ok": False, "step": "redmine", "res": res,
                "why": f"Redmine 취소 노트 실패: {res} — 잠금 해제는 됐다"
                       + (f", 커밋 목록이 기록되지 않아 {branch} 는 지우지 않았다" if will_delete else "")}
    done.append("redmine")
    log("redmine", f"취소 노트 · 브랜치 {fate}")
    return {"ok": True, "res": res}


def infra_cancel(project: str, issue_id, *, confirm: bool = False, delete_branch: bool = False,
                 branch_exists: bool = True, commits=None, local_only=None, noter=None, lock_root=None,
                 events_path=None, logf=None) -> dict:
    """요청자의 취소 기록. `confirm=False`(기본)는 잠금 상태와 요청자가 보낸 커밋 목록으로 미리보기만 한다.

    승인 시 잠금 해제 → 「취소」 노트. 브랜치·worktree 삭제는 요청자가 노트 성공(`ok`)을 본 뒤
    `delete_branch=True` 일 때만 한다 — 응답의 `branch_delete_allowed` 가 그 판정이다.
    `commits` 는 `"<sha> <제목>"` 줄(main 밖 커밋), `local_only` 는 원격에 없는 sha 목록.
    """
    log, lroot, refused = _remote_setup("cancel", project, issue_id, noter=noter, lock_root=lock_root,
                                        events_path=events_path, logf=logf, need_lock=True)
    if refused:
        return refused
    n = int(issue_id)
    branch = branch_name(n)
    try:
        state = cancel_state(lroot, n)
    except Exception as e:                              # noqa: BLE001
        return refuse(log, "lock", f"잠금 상태를 못 읽었다 — {type(e).__name__}: {e}", project=project)
    exists = bool(branch_exists)
    if state == "absent" and not exists:
        return refuse(log, "lock", f"#{n} 는 잠금에도 없고 {branch} 도 없다 — 취소할 것이 없다", project=project)
    cs = [str(c).strip() for c in (commits or []) if str(c).strip()]
    lo = [_sha(c)[:40] for c in (local_only or []) if str(c).strip()]
    log("state", f"잠금 {state} · 브랜치 {'있음(요청자 보고)' if exists else '없음'} · main 밖 커밋 {len(cs)}건"
                 f"(로컬에만 {len(lo)})")
    summary = {"issue_id": n, "project": project, "branch": branch, "lock_state": state,
               "branch_exists": exists, "commits": cs, "local_only": lo, "delete_branch": delete_branch}
    warning = (f"[중요] {branch} 의 커밋 {len(lo)}건은 요청자 저장소에만 있다(원격 없음) — 브랜치를 지우면 "
               "되살릴 수 없다") if lo else ""
    if not confirm:
        fate = f"{branch} 삭제" if delete_branch and exists else f"{branch} 유지"
        log("preview", "confirm=False — 아무것도 바꾸지 않았다")
        return {"ok": True, "confirmed": False, **summary, "warning": warning,
                "next": "승인 시 confirm=true 호출이 이어서 한다 — "
                        + ("잠금 해제(cancel) · " if state != "absent" else "")
                        + f"Redmine 취소 노트 · {fate}"
                        + ("" if delete_branch else " (삭제는 delete_branch=true 일 때만)"),
                "log": log.lines}
    done: list[str] = []
    will_delete = bool(delete_branch and exists)
    got = cancel_record(issue_id, lroot=lroot, lock_state_=state, branch=branch, commits=cs, local_only=lo,
                        will_delete=will_delete, noter=noter or default_noter, log=log, done=done,
                        by="issue_infra.cancel")
    if not got["ok"]:
        return {"ok": False, "confirmed": True, **summary, "step": got["step"], "why": got["why"],
                "branch_delete_allowed": False, "done": done, "log": log.lines}
    return {"ok": True, "confirmed": True, **summary, "branch_delete_allowed": will_delete, "done": done,
            "redmine": got["res"], "log": log.lines}


# ── 원격 공통 ─────────────────────────────────────────────────────────────────

def _remote_setup(op: str, project: str, issue_id, *, getter=None, noter=None, injected=None,
                  lock_root=None, events_path=None, logf=None, need_lock: bool = False):
    """원격 호출의 공통 준비 — `(Log, 잠금 루트, 거절 | None)`.

    [중요] 프로젝트가 비면 거절한다 — 원격 호출이 AXCluster 로 「가정」되면 남의 잠금을 건드린다.
    대역 주입 실행(getter·noter 등)이 `lock_root` 를 안 주면 잠금·추적을 쓰지 않는다(`NO_LOCK`) —
    pause·cancel 은 잠금이 본체라 거절한다. 흐름 로그는 `<프로젝트 트윈>/issue_flow.jsonl`.
    """
    if injected is None:
        injected = getter is not None or noter is not None
    try:
        n = int(issue_id)
        if n <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, None, {"ok": False, "issue_id": issue_id, "step": "input",
                            "why": f"일감 번호가 아니다 — {issue_id!r}", "log": []}
    proj = (project or "").strip()
    ev = events_path
    if ev is None and not injected and proj:
        try:
            ev = project_root(proj) / EVENTS_NAME
        except Exception as e:                          # noqa: BLE001
            print(f"[issue_infra] [주의] 이벤트 경로를 못 풀었다: {e}", file=sys.stderr)
    log = Log(op, n, events_path=ev, logf=logf, tag="issue_infra")
    if not proj:
        return log, None, refuse(log, "project", "project 가 비었다 — 원격 일감 흐름은 프로젝트를 싣는다")
    try:
        lroot = resolve_lock(lock_root, injected, proj)
    except Exception as e:                              # noqa: BLE001
        return log, None, refuse(log, "lock", f"잠금 위치를 못 풀었다 — {type(e).__name__}: {e}", project=proj)
    if need_lock and lroot is NO_LOCK:
        return log, None, refuse(log, "lock", "대역 주입 실행에 lock_root 가 없다 — 운영 잠금을 건드리지 않는다",
                                 project=proj)
    log("setup", f"프로젝트 {proj} · 잠금 {'미사용(대역)' if lroot is NO_LOCK else lroot}")
    return log, lroot, None
