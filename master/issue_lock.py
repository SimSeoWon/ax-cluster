"""일감 하나씩 — 작업 잠금 상태(`#883` T1).

    acquire(root, N, branch=…, start_rev=…)   빈 자리면 N 을 활성으로 · 같은 N 이면 이어감
    pause(root, N)                             활성 N 을 보류로 옮기고 자리를 비운다
    release(root, N, op="complete"|"cancel"|"finish")   활성·보류에서 N 을 지운다
        finish — `issue_flow.finish` 가 main 적용·마감 추적 등록 뒤 푼다(`#884` T5, 사용자 결정
                 2026-11-04 「잠금은 마감 때 푼다 — 세션은 곧바로 다음으로 간다」)
    current(root) / is_tracked(root, N)        조회

사용자 결정(2026-11-04): 일감 작업을 시작하면 그 일감이 **완료·보류·취소** 되기 전에는 다른 일감을
시작하지 않는다. **보류는 잠금을 푼다**(브랜치는 남는다) — 다시 이어가는 것은 같은 일감을 다시
시작(`acquire`)하는 것이다. 그래서 상태는 **활성 한 칸(`active`)과 보류 목록(`paused`)** 이다.

[중요] **못 읽는 상태 파일은 덮어쓰지 않는다** — 깨졌거나 형식이 다르면 `IssueLockError` 로 멈춘다
(`fix_index` 와 같은 원칙). 조용히 비우면 잠금이 사라져 두 일감이 동시에 열린다.
[중요] **모든 변경은 파일 잠금(`.issue_lock.lock` flock) 안에서 읽고 쓴다** — 쓰기는 임시 파일 +
`os.replace` 로 원자적이다. 동시에 두 `acquire` 가 와도 이기는 쪽은 하나다.
[주의] 이 모듈은 네트워크·Redmine·git 을 부르지 않는다 — 배선은 `issue_flow`(T2)·`redmine`(T4) 몫이다.
모든 변경은 `history`(최근 `HISTORY_CAP` 건)에 쌓이고 `logf` 로 한 줄씩 찍힌다.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = 1
STATE_NAME = "issue_lock.json"
LOCK_NAME = ".issue_lock.lock"
HISTORY_CAP = 50
RELEASE_OPS = ("complete", "cancel", "finish")


class IssueLockError(RuntimeError):
    """상태 파일을 믿을 수 없다 — 사유 문장을 담는다. 파일은 건드리지 않았다."""


def default_root(project: str = "AXCluster") -> Path:
    from master.context_search.paths import resolve
    return Path(resolve(project).root)


def state_path(root) -> Path:
    return Path(root) / STATE_NAME


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empty() -> dict:
    return {"schema": SCHEMA, "active": None, "paused": {}, "history": []}


def _bad(p: Path, why: str) -> IssueLockError:
    return IssueLockError(f"일감 잠금 상태를 믿을 수 없다 ({p}: {why}) — 덮어쓰지 않았다, 사람이 확인한다")


def _check_rec(p: Path, rec, where: str) -> None:
    if not isinstance(rec, dict) or not isinstance(rec.get("issue_id"), int):
        raise _bad(p, f"{where} 기록 형식이 아니다")


def _load(root) -> dict:
    p = state_path(root)
    if not p.exists():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise _bad(p, f"읽기 실패 {type(e).__name__}") from e
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise _bad(p, f"알 수 없는 형식(schema={data.get('schema') if isinstance(data, dict) else '?'})")
    active, paused, hist = data.get("active"), data.get("paused"), data.get("history")
    if active is not None:
        _check_rec(p, active, "active")
    if not isinstance(paused, dict):
        raise _bad(p, "paused 가 사전이 아니다")
    for k, rec in paused.items():
        _check_rec(p, rec, f"paused[{k}]")
        if str(rec["issue_id"]) != k:
            raise _bad(p, f"paused[{k}] 의 issue_id 가 {rec['issue_id']} 다")
    if not isinstance(hist, list):
        raise _bad(p, "history 가 목록이 아니다")
    if active is not None and str(active["issue_id"]) in paused:
        raise _bad(p, f"#{active['issue_id']} 가 활성과 보류에 동시에 있다")
    return data


def _save(root, data: dict) -> None:
    p = state_path(root)
    tmp = p.with_name(f"{STATE_NAME}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


@contextmanager
def _locked(root):
    d = Path(root)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / LOCK_NAME, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _emit(logf, issue_id, op: str, msg: str) -> str:
    line = f"[issue_lock] #{issue_id} {op}: {msg}"
    if logf:
        logf(line)
    return line


def _record(data: dict, op: str, issue_id: int, by: str, why: str) -> None:
    hist = data["history"]
    hist.append({"at": _now(), "op": op, "issue_id": issue_id, "by": by, "why": why})
    if len(hist) > HISTORY_CAP:
        del hist[:len(hist) - HISTORY_CAP]


def _refuse(logf, issue_id, op: str, reason: str, why: str, **extra) -> dict:
    line = _emit(logf, issue_id, op, f"거절({reason}) — {why}")
    return {"ok": False, "issue_id": issue_id, "reason": reason, "why": why, "log": [line], **extra}


# ── 조회 ────────────────────────────────────────────────────────────────────

def current(root) -> dict | None:
    """활성 기록(사본) 또는 None."""
    with _locked(root):
        a = _load(root)["active"]
    return dict(a) if a else None


def paused(root) -> dict:
    """보류 기록 `{issue_id(int): 기록}`."""
    with _locked(root):
        p = _load(root)["paused"]
    return {int(k): dict(v) for k, v in p.items()}


def is_tracked(root, issue_id) -> bool:
    """활성이거나 보류에 있으면 True — 「완료」 관문이 손 닫기를 막을지 정하는 데 쓴다(`#889` — 작업 중이면 막음)."""
    n = int(issue_id)
    with _locked(root):
        data = _load(root)
    a = data["active"]
    return bool(a and a["issue_id"] == n) or str(n) in data["paused"]


# ── 변경 ────────────────────────────────────────────────────────────────────

def acquire(root, issue_id, *, branch: str, start_rev: str, by: str = "", why: str = "",
            logf=None) -> dict:
    """N 을 활성으로 — 빈 자리 · 같은 N 활성(`already`) · N 보류 중 빈 자리(`resumed`)면 ok.

    다른 일감이 활성이면 `reason="busy"` 로 거절한다. 다른 일감의 **보류**는 막지 않는다.
    """
    n = int(issue_id)
    with _locked(root):
        data = _load(root)
        a = data["active"]
        if a and a["issue_id"] == n:
            line = _emit(logf, n, "acquire", f"이미 활성 — {a.get('branch')} · 시작 {str(a.get('start_rev'))[:12]}")
            return {"ok": True, "issue_id": n, "already": True, "record": dict(a), "log": [line]}
        if a:
            h = a["issue_id"]
            return _refuse(logf, n, "acquire", "busy",
                           f"#{h} 작업이 진행 중이다({a.get('branch')}) — 일감은 하나씩 한다. "
                           f"#{h} 를 완료하거나, 보류(pause) 또는 취소(cancel)한 뒤 시작한다",
                           holder=h, state="active")
        now = _now()
        prev = data["paused"].pop(str(n), None)
        if prev:
            rec = {**prev, "state": "active", "updated": now}
            rec.pop("paused_at", None)
            rec.setdefault("branch", branch)
            rec.setdefault("start_rev", start_rev)
            op, msg = "resume", f"보류에서 재개 — {rec.get('branch')} · 시작 {str(rec.get('start_rev'))[:12]}"
        else:
            rec = {"issue_id": n, "state": "active", "branch": branch, "start_rev": start_rev,
                   "since": now, "updated": now}
            op, msg = "acquire", f"활성 — {branch} · 시작 {str(start_rev)[:12]}"
        data["active"] = rec
        _record(data, op, n, by, why)
        _save(root, data)
        line = _emit(logf, n, op, msg)
    out = {"ok": True, "issue_id": n, "record": dict(rec), "log": [line]}
    if prev:
        out["resumed"] = True
    return out


def pause(root, issue_id, *, by: str = "", why: str = "", logf=None) -> dict:
    """활성 N 을 보류로 옮기고 활성 자리를 비운다 — 활성이 N 이 아니면 거절."""
    n = int(issue_id)
    with _locked(root):
        data = _load(root)
        a = data["active"]
        if not a or a["issue_id"] != n:
            holder = a["issue_id"] if a else None
            state = "paused" if str(n) in data["paused"] else "absent"
            return _refuse(logf, n, "pause", "not_active",
                           f"#{n} 는 활성 일감이 아니다(지금 활성 {'#' + str(holder) if holder else '없음'}"
                           f" · #{n} 상태 {state})", holder=holder, state=state)
        now = _now()
        rec = {**a, "state": "paused", "paused_at": now, "updated": now}
        data["paused"][str(n)] = rec
        data["active"] = None
        _record(data, "pause", n, by, why)
        _save(root, data)
        line = _emit(logf, n, "pause", f"보류 — 잠금 해제 · 브랜치 {rec.get('branch')} 유지")
    return {"ok": True, "issue_id": n, "record": dict(rec), "log": [line]}


def release(root, issue_id, *, op: str, by: str = "", why: str = "", logf=None) -> dict:
    """완료·취소 — 활성 또는 보류에서 N 을 지운다. 어디에도 없으면 거절."""
    n = int(issue_id)
    if op not in RELEASE_OPS:
        return _refuse(logf, n, "release", "bad_op", f"op 는 {'/'.join(RELEASE_OPS)} 중 하나다 — {op!r}")
    with _locked(root):
        data = _load(root)
        a = data["active"]
        if a and a["issue_id"] == n:
            rec, was = a, "active"
            data["active"] = None
        elif str(n) in data["paused"]:
            rec, was = data["paused"].pop(str(n)), "paused"
        else:
            return _refuse(logf, n, op, "not_tracked", f"#{n} 는 활성·보류 어디에도 없다", state="absent")
        _record(data, op, n, by, why)
        _save(root, data)
        line = _emit(logf, n, op, f"해제({was}→없음) — 브랜치 {rec.get('branch')}")
    return {"ok": True, "issue_id": n, "op": op, "was": was, "record": dict(rec), "log": [line]}
