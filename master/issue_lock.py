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
from uuid import uuid4

SCHEMA = 1
STATE_NAME = "issue_lock.json"
LOCK_NAME = ".issue_lock.lock"
HISTORY_CAP = 50
RELEASE_OPS = ("complete", "cancel", "finish")
NODE_RUNNING, NODE_REVIEW, NODE_REWORK = "running", "review", "rework"


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
    nodes = data.get("node_assignments", {})
    if not isinstance(nodes, dict):
        raise _bad(p, "node_assignments 가 사전이 아니다")
    running = set()
    for k, rec in nodes.items():
        _check_rec(p, rec, f"node_assignments[{k}]")
        worker = rec.get("worker")
        if (str(rec["issue_id"]) != k or rec["issue_id"] <= 0
                or type(rec.get("root_id")) is not int or rec["root_id"] <= 0
                or not isinstance(worker, str) or not worker.strip()
                or not isinstance(rec.get("assignment_id"), str) or not rec["assignment_id"]
                or rec.get("state") not in (NODE_RUNNING, NODE_REVIEW, NODE_REWORK)
                or k in paused or (active and rec["issue_id"] == active["issue_id"])):
            raise _bad(p, f"node_assignments[{k}] 기록이 잘못됐거나 단독 잠금과 겹친다")
        if rec["state"] == NODE_RUNNING:
            key = worker.casefold()
            if key in running:
                raise _bad(p, f"워커 {worker} 에 실행 중인 노드가 둘 이상이다")
            running.add(key)
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


@contextmanager
def node_guard(root, issue_id: int):
    """같은 티켓의 배정 변경과 외부 쓰기를 직렬화한다. 전역 상태 잠금보다 먼저 잡는다."""
    if type(issue_id) is not int or issue_id <= 0:
        raise ValueError("양의 정수 노드 일감 번호가 필요하다")
    directory = Path(root) / ".node_locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / str(issue_id)).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


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
    return bool(a and a["issue_id"] == n) or str(n) in data["paused"] or str(n) in data.get("node_assignments", {})


def node_assignments(root) -> dict[int, dict]:
    """분산 배정 상태의 스냅샷. 단독 잠금과 같은 파일을 대조한다."""
    if not state_path(root).exists():
        return {}
    with _locked(root):
        return {int(k): dict(v) for k, v in _load(root).get("node_assignments", {}).items()}


def snapshot(root) -> tuple[dict | None, dict[int, dict], dict[int, dict]]:
    """원자 교체되는 잠금 장부를 한 번 읽는다. 드라이런에서는 파일과 flock을 만들지 않는다."""
    data = _load(root)
    return (data["active"], {int(k): rec for k, rec in data["paused"].items()},
            {int(k): rec for k, rec in data.get("node_assignments", {}).items()})


# ── 변경 ────────────────────────────────────────────────────────────────────

def acquire(root, issue_id, *, branch: str, start_rev: str, by: str = "", why: str = "",
            logf=None) -> dict:
    """N 을 활성으로 — 빈 자리 · 같은 N 활성(`already`) · N 보류 중 빈 자리(`resumed`)면 ok.

    다른 일감이 활성이면 `reason="busy"` 로 거절한다. 다른 일감의 **보류**는 막지 않는다.
    """
    n = int(issue_id)
    with _locked(root):
        data = _load(root)
        if str(n) in data.get("node_assignments", {}):
            return _refuse(logf, n, "acquire", "node_assigned", f"#{n} 는 분산 노드 배정으로 관리 중이다")
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


def note_author(root, issue_id, family: str, *, client: str = "", logf=None) -> dict:
    """활성 N 의 기록에 작성 계열을 더한다(`#920`) — 중복 없이 순서대로. 활성이 N 이 아니면 거절.

    교대가 있으면 계열이 여럿 쌓인다. 보류 기록에도 그대로 남아 재개 뒤까지 이어진다.
    """
    n = int(issue_id)
    with _locked(root):
        data = _load(root)
        a = data["active"]
        if not a or a["issue_id"] != n:
            return _refuse(logf, n, "author", "not_active", f"#{n} 는 활성 일감이 아니다")
        authors = list(a.get("authors") or [])
        if family not in authors:
            authors.append(family)
        a["authors"] = authors
        a["updated"] = _now()
        _record(data, "author", n, client or "unknown", f"작성 계열 {family}")
        _save(root, data)
        line = _emit(logf, n, "author", f"작성 계열 {family} (client={client or '없음'}) · 누적 {authors}")
    return {"ok": True, "issue_id": n, "authors": authors, "log": [line]}


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


def reserve_node(root, issue_id: int, *, root_id: int, worker: str, logf=None) -> dict:
    """마스터가 발주 조건을 확인한 노드를 예약한다. 발주·SSH 호출은 이 함수 밖에서 한다."""
    if (type(issue_id) is not int or type(root_id) is not int or min(issue_id, root_id) <= 0
            or issue_id == root_id or not isinstance(worker, str) or not worker.strip()):
        return _refuse(logf, issue_id, "reserve_node", "invalid", "노드 번호·Root 번호·워커가 필요하다")
    worker = worker.strip()
    with node_guard(root, issue_id), _locked(root):
        data = _load(root)
        active = data["active"]
        key = str(issue_id)
        nodes = data.setdefault("node_assignments", {})
        if (active and active["issue_id"] == issue_id) or key in data["paused"]:
            return _refuse(logf, issue_id, "reserve_node", "local_tracked", "단독 잠금에 이미 등록됐다")
        prev = nodes.get(key)
        if prev and (prev["state"] != NODE_REWORK or prev["root_id"] != root_id):
            return _refuse(logf, issue_id, "reserve_node", "node_busy", "이미 배정됐거나 검수 대기 중이다")
        for rec in nodes.values():
            if rec["state"] == NODE_RUNNING and rec["worker"].casefold() == worker.casefold():
                return _refuse(logf, issue_id, "reserve_node", "worker_busy", f"{worker} 는 이미 실행 중이다",
                               holder=rec["issue_id"])
        rec = {"issue_id": issue_id, "root_id": root_id, "worker": worker, "assignment_id": uuid4().hex,
               "state": NODE_RUNNING, "updated": _now()}
        nodes[key] = rec
        _record(data, "reserve_node", issue_id, worker, rec["assignment_id"])
        _save(root, data)
    return {"ok": True, "record": dict(rec), "log": [_emit(logf, issue_id, "reserve_node", worker)]}


def advance_node_assignment(root, issue_id: int, *, assignment_id: str, to: str, by: str, why: str,
                            logf=None) -> dict:
    """마스터가 확인한 종료 → 검수, 또는 승인된 재작업·마감 결과를 기록한다."""
    if type(issue_id) is not int or issue_id <= 0:
        return _refuse(logf, issue_id, "advance_node", "invalid", "노드 번호가 필요하다")
    with node_guard(root, issue_id):
        return _advance_node_assignment(root, issue_id, assignment_id=assignment_id, to=to,
                                        by=by, why=why, logf=logf)


def _advance_node_assignment(root, issue_id: int, *, assignment_id: str, to: str, by: str, why: str,
                             logf=None) -> dict:
    """호출자는 해당 티켓의 node_guard를 유지한다."""
    required = {NODE_REVIEW: NODE_RUNNING, NODE_REWORK: NODE_REVIEW, "finished": NODE_REVIEW}
    if to not in required or not assignment_id or not by.strip() or not why.strip():
        return _refuse(logf, issue_id, "advance_node", "invalid", "배정 번호·허용 전이·주체·근거가 필요하다")
    with _locked(root):
        data = _load(root)
        nodes = data.get("node_assignments", {})
        key = str(issue_id)
        rec = nodes.get(key)
        if rec is None or rec["assignment_id"] != assignment_id:
            return _refuse(logf, issue_id, "advance_node", "stale_assignment", "현재 배정 번호와 다르다")
        if rec["state"] != required[to]:
            return _refuse(logf, issue_id, "advance_node", "invalid_state", f"현재 상태 {rec['state']}")
        updated = {**rec, "state": to, "updated": _now()}
        if to == "finished":
            del nodes[key]
        else:
            nodes[key] = updated
        _record(data, f"node_{to}", issue_id, by, why)
        _save(root, data)
    return {"ok": True, "record": updated, "log": [_emit(logf, issue_id, "advance_node", to)]}
