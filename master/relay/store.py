"""작업 세션 저장소 (`#942` T2) — 일감 번호별 로그·상태·보관.

    <root>/sessions/<N>/log.jsonl     세션 로그 — 순번 붙은 추가 전용 기록 (미러링 대상 = 공유 메모리)
    <root>/sessions/<N>/state.json    에이전트별 세션 ID · 마지막으로 본 순번 · 현재 에이전트
    <root>/sessions/<N>/debug.log     디버그 로그 — 실행 명령·종료 코드·오류 출력·해석 실패 (사람이 읽는다)
    <root>/archive/<N>-<시각>/         마무리된 세션 — 디렉터리째 옮긴다
    <root>/relay.log                  세션이 없을 때의 디버그 로그

[중요] **로그에 쓰는 것은 이 모듈뿐이다** — 에이전트는 읽기만 한다. 순번은 파일 잠금 안에서 매긴다.
[중요] **못 읽는 상태 파일은 덮어쓰지 않는다** — `StoreError` 로 멈춘다(`issue_lock` 과 같은 원칙).
보관은 옮기기다 — 지우지 않는다. 같은 일감을 다시 열면 빈 세션에서 시작한다.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = 1
AGENTS = ("claude", "codex", "agy")
LOG_NAME = "log.jsonl"
STATE_NAME = "state.json"
DEBUG_NAME = "debug.log"
ROOT_DEBUG = "relay.log"
_LOCK = ".lock"
_SEQ = ".seq"


class StoreError(RuntimeError):
    """세션 파일을 믿을 수 없다 — 사유 문장을 담는다. 파일은 건드리지 않았다."""


def default_root() -> Path:
    env = os.environ.get("AX_RELAY_ROOT", "").strip()
    return Path(env) if env else Path.home() / "ax-state" / "relay"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _iid(issue_id) -> int:
    try:
        n = int(issue_id)
    except (TypeError, ValueError):
        raise StoreError(f"일감 번호가 정수가 아니다: {issue_id!r}") from None
    if n <= 0:
        raise StoreError(f"일감 번호는 양수여야 한다: {issue_id!r}")
    return n


def session_dir(root, issue_id) -> Path:
    return Path(root) / "sessions" / str(_iid(issue_id))


def log_path(root, issue_id) -> Path:
    return session_dir(root, issue_id) / LOG_NAME


def debug_path(root, issue_id=None) -> Path:
    return (session_dir(root, issue_id) / DEBUG_NAME) if issue_id else Path(root) / ROOT_DEBUG


def debug(root, issue_id, where: str, msg: str) -> str:
    """디버그 로그에 한 줄. 세션 디렉터리가 없으면 루트 로그에 쓴다. 쓰기 실패는 삼키지 않고 올린다."""
    line = f"{_now()} [{where}] {msg}"
    p = debug_path(root, issue_id)
    if issue_id and not p.parent.is_dir():
        p = debug_path(root, None)
        line = f"{_now()} [{where}] (#{issue_id}) {msg}"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(line.replace("\r", "\\r") + "\n")
    return line


@contextmanager
def _locked(d: Path):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / _LOCK, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _empty_state(issue_id: int) -> dict:
    return {"schema": SCHEMA, "issue": issue_id, "created": _now(), "current": "",
            "agents": {a: {"session": "", "seen": 0, "turns": 0} for a in AGENTS}}


def _load_state(d: Path, issue_id: int) -> dict:
    p = d / STATE_NAME
    if not p.exists():
        return _empty_state(issue_id)
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise StoreError(f"세션 상태를 읽지 못했다 ({p}: {e}) — 덮어쓰지 않았다") from None
    if not isinstance(st, dict) or st.get("schema") != SCHEMA or not isinstance(st.get("agents"), dict):
        raise StoreError(f"세션 상태 형식이 다르다 ({p}) — 덮어쓰지 않았다")
    for a in AGENTS:
        st["agents"].setdefault(a, {"session": "", "seen": 0, "turns": 0})
    return st


def _save_state(d: Path, st: dict) -> None:
    tmp = d / (STATE_NAME + ".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, d / STATE_NAME)


def exists(root, issue_id) -> bool:
    return (session_dir(root, issue_id) / STATE_NAME).exists()


def open_session(root, issue_id) -> dict:
    """세션을 만들거나 이어 간다. 돌려주는 값: `{"issue", "created", "resumed", "state", "log", "debug"}`."""
    n = _iid(issue_id)
    d = session_dir(root, n)
    with _locked(d):
        resumed = (d / STATE_NAME).exists()
        st = _load_state(d, n)
        if not resumed:
            _save_state(d, st)
    debug(root, n, "store.open", f"세션 {'이어감' if resumed else '생성'} — {d}")
    if not resumed:
        append(root, n, kind="session", text=f"작업 세션 #{n} 시작")
    return {"issue": n, "created": st["created"], "resumed": resumed, "state": st,
            "log": str(d / LOG_NAME), "debug": str(d / DEBUG_NAME)}


def state(root, issue_id) -> dict:
    n = _iid(issue_id)
    d = session_dir(root, n)
    if not (d / STATE_NAME).exists():
        raise StoreError(f"작업 세션 #{n} 이 없다 ({d})")
    with _locked(d):
        return _load_state(d, n)


def update_agent(root, issue_id, agent: str, **fields) -> dict:
    """에이전트 상태·한도 관측을 고친다. `current=True` 면 현재 에이전트로 둔다."""
    if agent not in AGENTS:
        raise StoreError(f"모르는 에이전트: {agent!r}")
    n = _iid(issue_id)
    d = session_dir(root, n)
    make_current = bool(fields.pop("current", False))
    bad = set(fields) - {"session", "seen", "turns", "quota", "quota_warning"}
    if bad:
        raise StoreError(f"모르는 필드: {sorted(bad)}")
    with _locked(d):
        if not (d / STATE_NAME).exists():
            raise StoreError(f"작업 세션 #{n} 이 없다 ({d})")
        st = _load_state(d, n)
        before = dict(st["agents"][agent])
        if fields.get("session") == "":
            fields.update(quota={}, quota_warning={})
        st["agents"][agent].update(fields)
        if make_current:
            st["current"] = agent
        _save_state(d, st)
    if before.get("session") != st["agents"][agent]["session"]:
        debug(root, n, "store.agent", f"{agent} 세션 ID {before.get('session') or '(없음)'} → "
                                      f"{st['agents'][agent]['session'] or '(없음)'}")
    return st


def append(root, issue_id, *, kind: str, agent: str = "", text: str = "", data=None) -> dict:
    """세션 로그에 한 줄을 더하고 그 기록(순번 포함)을 돌려준다."""
    n = _iid(issue_id)
    d = session_dir(root, n)
    with _locked(d):
        sp = d / _SEQ
        try:
            seq = int(sp.read_text()) if sp.exists() else 0
        except (OSError, ValueError) as e:
            raise StoreError(f"순번 파일을 읽지 못했다 ({sp}: {e}) — 덮어쓰지 않았다") from None
        rec = {"seq": seq + 1, "ts": _now(), "issue": n, "agent": agent, "kind": kind, "text": text}
        if data is not None:
            rec["data"] = data
        with open(d / LOG_NAME, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
        sp.write_text(str(seq + 1))
    return rec


def last_seq(root, issue_id) -> int:
    sp = session_dir(root, issue_id) / _SEQ
    try:
        return int(sp.read_text()) if sp.exists() else 0
    except (OSError, ValueError) as e:
        raise StoreError(f"순번 파일을 읽지 못했다 ({sp}: {e})") from None


def read(root, issue_id, *, after: int = 0) -> list:
    """`after` 보다 큰 순번의 기록. 못 읽는 줄은 버리지 않고 `kind="unreadable"` 로 돌려준다."""
    p = log_path(root, issue_id)
    out = []
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as fh:
        for i, ln in enumerate(fh, 1):
            ln = ln.rstrip("\n")
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except ValueError:
                rec = {"seq": 0, "kind": "unreadable", "text": ln, "line": i}
            if rec.get("seq", 0) > after or rec.get("kind") == "unreadable":
                out.append(rec)
    return out


def sessions(root) -> list:
    """열려 있는(보관 안 된) 세션의 일감 번호."""
    d = Path(root) / "sessions"
    if not d.is_dir():
        return []
    return sorted(int(p.name) for p in d.iterdir() if p.name.isdigit() and (p / STATE_NAME).exists())


def archive(root, issue_id, *, why: str = "") -> dict:
    """세션을 보관소로 옮긴다 — 에이전트 세션 ID 도 함께 떠나므로 다음 세션은 빈 상태다."""
    n = _iid(issue_id)
    d = session_dir(root, n)
    if not (d / STATE_NAME).exists():
        raise StoreError(f"작업 세션 #{n} 이 없다 ({d})")
    append(root, n, kind="session", text=f"작업 세션 #{n} 보관" + (f" — {why}" if why else ""))
    debug(root, n, "store.archive", f"보관 시작 — 사유: {why or '(없음)'}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = Path(root) / "archive" / f"{n}-{stamp}"
    k = 1
    while dest.exists():
        k += 1
        dest = Path(root) / "archive" / f"{n}-{stamp}-{k}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(d, dest)
    debug(root, None, "store.archive", f"#{n} → {dest}")
    return {"issue": n, "dest": str(dest)}
