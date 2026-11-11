"""일감 마감 추적 — 끝낸 일감의 커밋 해시 묶음과 그 리뷰 진행(`#884` T1).

사용자 결정(2026-11-04): 작업 세션은 `issue/<N>` 을 `main` 에 머지·push 한 뒤 **그 브랜치의 커밋
해시 목록 + 레드마인 일감 번호** 를 인프라에 등록하고, 잠금을 풀고 곧바로 다음으로 간다. 그 뒤는
인프라 몫이다 — 이 모듈은 그 **기록 하나만** 맡는다(배선은 T2~T5):

    T2  색인기의 커밋 리뷰를 우선순위 10 으로 · 일감에 연결         → issue_of_hash
    T3  커밋 리뷰가 끝날 때마다(done/abandoned) 짧은 진행 노트       → set_hash · mark_hash_noted
        색인기가 끝내 안 넣은 해시(소스 변경 없음·리뷰 이미 있음)는
        워터마크가 지나가면 `skipped`
    T4  모든 해시가 종결(done/abandoned/skipped)이면 종합 범위 리뷰 1회 → all_hashes_terminal · set_summary
    T5  issue_review_status · 종합 리뷰 판정(#889 뒤 완료 관문은 안 읽는다) → current

    register(root, N, project=, base=, end=, hashes=)   새 라운드(해시 전부 `waiting`)
    current(root, N) / open_rounds(root) / issue_of_hash(root, sha)
    set_hash(root, N, sha, state=…) / mark_hash_noted(root, N, sha)
    set_hash_missing(root, N, sha, why=…) / clear_hash_missing(root, N, sha)
    set_summary(root, N, state=…)
    all_hashes_terminal(round) / pending_hashes(round)   순수 함수

상태 파일은 `<트윈 루트>/issue_track.json`(schema 1) — 프로젝트 트윈마다 하나다(AXCluster 와
`.33` 요청자의 언리얼 프로젝트가 같은 흐름을 쓴다).

## 라운드 — 한 일감은 여러 번 끝날 수 있다

취소 뒤 재개·후속 작업으로 같은 일감을 다시 마감할 수 있다. 그래서 `records[str(N)]` 는 **라운드
목록**이고 마지막이 현재다. 라운드마다 `round`(1부터 단조 증가) 번호가 붙고, 옛 라운드는
`ROUND_CAP` 개까지 남긴다. 최신 라운드와 `base..end` 가 같으면 새 라운드를 만들지 않는다
(`already`) — 같은 마감을 두 번 등록해도 무해하다. 범위는 같은데 해시 집합이 다르면
`hashes_mismatch` 로 거절한다(히스토리가 다시 쓰였다 — 사람이 볼 일이다).
[주의] 새 라운드가 와도 옛 라운드의 진행은 지우지 않는다 — 종합 리뷰가 아직 안 끝난 옛 라운드도
`open_rounds` 에 나온다. 변경 API 는 `round=` 를 받아 옛 라운드를 지목할 수 있고, 생략하면 최신이다.

## 해시 상태 전이 (코드가 집행한다)

    waiting → queued · done · abandoned · skipped
    queued  → queued(serial 갱신) · done · abandoned
    종결(done·abandoned·skipped) → 같은 상태만(`already`, 변경 없음), 다른 상태는 거절

`queued → skipped` 는 거절한다 — `skipped` 는 「색인기가 끝내 넣지 않았다」는 뜻이라 이미 큐에
들어간 해시에는 성립하지 않는다(큐에서 사라졌다면 `abandoned` 다).

## 종합 리뷰 상태

    waiting · queued · running · done · failed · abandoned
    queued·running·done 은 모든 해시가 종결된 뒤에만 — 순서를 코드가 강제한다
    done·abandoned 는 종결 — 다른 상태로 되돌리지 않는다(같은 상태는 `already`)

[중요] **못 읽는 상태 파일은 덮어쓰지 않는다** — 깨졌거나 형식이 다르면 `IssueTrackError` 로 멈춘다
(`issue_lock`·`fix_index` 와 같은 원칙). 조용히 비우면 진행 중인 마감 추적이 사라진다.
[중요] 모든 변경은 `.issue_track.lock` flock 안에서 읽고 쓰며, 쓰기는 임시 파일 + `os.replace` 다.
[주의] 이 모듈은 git·네트워크·Redmine·리뷰 큐를 건드리지 않는다. 변경은 라운드의 `history`
(최근 `HISTORY_CAP` 건)에 쌓이고 `logf` 와 반환 `log` 로 한 줄씩 찍힌다.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
STATE_NAME = "issue_track.json"
LOCK_NAME = ".issue_track.lock"
ROUND_CAP = 10
HISTORY_CAP = 30

HASH_STATES = ("waiting", "queued", "done", "abandoned", "skipped")
HASH_TERMINAL = ("done", "abandoned", "skipped")
HASH_NEXT = {
    "waiting": ("queued", "done", "abandoned", "skipped"),
    "queued": ("queued", "done", "abandoned"),
}
SUMMARY_STATES = ("waiting", "queued", "running", "done", "failed", "abandoned")
SUMMARY_CLOSED = ("done", "abandoned")
SUMMARY_NEEDS_TERMINAL = ("queued", "running", "done")

_SHA = re.compile(r"^[0-9a-f]{40}$")


class IssueTrackError(RuntimeError):
    """상태 파일을 믿을 수 없다 — 사유 문장을 담는다. 파일은 건드리지 않았다."""


def state_path(root) -> Path:
    return Path(root) / STATE_NAME


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _empty() -> dict:
    return {"schema": SCHEMA, "records": {}}


def _bad(p: Path, why: str) -> IssueTrackError:
    return IssueTrackError(f"일감 마감 추적 상태를 믿을 수 없다 ({p}: {why}) — 덮어쓰지 않았다, 사람이 확인한다")


def _check_round(p: Path, key: str, rnd) -> None:
    where = f"records[{key}]"
    if not isinstance(rnd, dict) or rnd.get("issue_id") != int(key) or not isinstance(rnd.get("round"), int):
        raise _bad(p, f"{where} 라운드 형식이 아니다")
    hs = rnd.get("hashes")
    if not isinstance(hs, list) or not hs:
        raise _bad(p, f"{where} hashes 가 비었거나 목록이 아니다")
    for h in hs:
        if not isinstance(h, dict) or not isinstance(h.get("sha"), str) or h.get("state") not in HASH_STATES:
            raise _bad(p, f"{where} 해시 기록 형식이 아니다")
        missing = h.get("mirror_missing")
        if missing is not None and (not isinstance(missing, dict)
                                    or not isinstance(missing.get("why"), str)
                                    or type(missing.get("noted")) is not bool
                                    or not isinstance(missing.get("detected_at"), str)):
            raise _bad(p, f"{where} 미러 부재 기록 형식이 아니다")
    s = rnd.get("summary")
    if not isinstance(s, dict) or s.get("state") not in SUMMARY_STATES:
        raise _bad(p, f"{where} summary 형식이 아니다")
    if not isinstance(rnd.get("history"), list):
        raise _bad(p, f"{where} history 가 목록이 아니다")


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
    recs = data.get("records")
    if not isinstance(recs, dict):
        raise _bad(p, "records 가 사전이 아니다")
    for k, rounds in recs.items():
        if not k.isdigit() or not isinstance(rounds, list) or not rounds:
            raise _bad(p, f"records[{k}] 가 라운드 목록이 아니다")
        for rnd in rounds:
            _check_round(p, k, rnd)
    return data


def _save(root, data: dict) -> None:
    p = state_path(root)
    tmp = p.with_name(f"{STATE_NAME}.{os.getpid()}.{threading.get_ident()}.tmp")
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
    line = f"[issue_track] #{issue_id} {op}: {msg}"
    if logf:
        logf(line)
    return line


def _refuse(logf, issue_id, op: str, reason: str, why: str, **extra) -> dict:
    line = _emit(logf, issue_id, op, f"거절({reason}) — {why}")
    return {"ok": False, "issue_id": issue_id, "reason": reason, "why": why, "log": [line], **extra}


def _hist(rnd: dict, op: str, msg: str) -> None:
    h = rnd["history"]
    h.append({"at": _now(), "op": op, "msg": msg})
    if len(h) > HISTORY_CAP:
        del h[:len(h) - HISTORY_CAP]


def _copy(rnd: dict) -> dict:
    return json.loads(json.dumps(rnd))


def norm_sha(s) -> str:
    """해시 정규화 — 앞뒤 공백 제거·소문자. 추적 기록의 해시는 늘 이 꼴이다."""
    return str(s or "").strip().lower()


# #917(R240-1·2): 다른 모듈이 부르는 공개 이름. 밑줄 이름은 모듈 안 호출부를 위한 별칭으로 남긴다.
_norm_sha = norm_sha


def _pick_round(data: dict, n: int, rnum):
    """(라운드, 거절 사유|None). rnum 이 None 이면 최신."""
    rounds = data["records"].get(str(n))
    if not rounds:
        return None, ("not_registered", f"#{n} 는 등록된 마감 라운드가 없다")
    if rnum is None:
        return rounds[-1], None
    for r in rounds:
        if r["round"] == int(rnum):
            return r, None
    return None, ("no_round", f"#{n} 에 라운드 {rnum} 가 없다(남은 라운드 {[r['round'] for r in rounds]})")


def find_hash(rnd: dict, sha: str):
    """라운드에서 해시 항목(정규화된 sha 로 찾는다) 또는 None."""
    for h in rnd["hashes"]:
        if h["sha"] == sha:
            return h
    return None


_find_hash = find_hash   # #917 별칭


# ── 순수 판정 ────────────────────────────────────────────────────────────────

def all_hashes_terminal(rnd: dict) -> bool:
    """라운드의 해시가 전부 done/abandoned/skipped 면 True — T4 가 종합 리뷰를 걸 조건."""
    hs = (rnd or {}).get("hashes") or []
    return bool(hs) and all(h.get("state") in HASH_TERMINAL for h in hs)


def pending_hashes(rnd: dict) -> list:
    """아직 종결되지 않은(waiting·queued) 해시 sha 목록 — 등록 순서."""
    return [h["sha"] for h in (rnd or {}).get("hashes") or [] if h.get("state") not in HASH_TERMINAL]


# ── 조회 ────────────────────────────────────────────────────────────────────

def current(root, issue_id) -> dict | None:
    """최신 라운드(사본) 또는 None."""
    with _locked(root):
        rounds = _load(root)["records"].get(str(int(issue_id)))
    return _copy(rounds[-1]) if rounds else None


def rounds(root, issue_id) -> list:
    """일감의 라운드 전부(사본, 오래된 것부터)."""
    with _locked(root):
        rs = _load(root)["records"].get(str(int(issue_id))) or []
    return [_copy(r) for r in rs]


def open_rounds(root) -> list:
    """종합 리뷰가 done/abandoned 가 아닌 라운드 전부(사본) — 등록 시각 순. T3/T4 가 훑는다."""
    with _locked(root):
        data = _load(root)
    out = [_copy(r) for rs in data["records"].values() for r in rs
           if r["summary"]["state"] not in SUMMARY_CLOSED]
    out.sort(key=lambda r: (r.get("registered_at", ""), r["issue_id"], r["round"]))
    return out


def issue_of_hash(root, sha) -> int | None:
    """열린 라운드 중 sha 를 담은 **가장 최근에 등록된** 라운드의 일감 번호 — 없으면 None.

    닫힌(종합 리뷰 done/abandoned) 라운드는 보지 않는다. T2 가 우선순위·연결에 쓴다.
    """
    s = _norm_sha(sha)
    best = None
    for r in open_rounds(root):
        if any(h["sha"] == s for h in r["hashes"]):
            best = r  # open_rounds 는 등록 순 — 마지막이 최신
    return best["issue_id"] if best else None


def authors_of_hash(root, sha) -> tuple | None:
    """sha 를 담은 열린 라운드의 작성 계열(`#920`). 그런 라운드가 없으면 None — 빈 튜플과 구분한다."""
    s = _norm_sha(sha)
    best = None
    for r in open_rounds(root):
        if any(h["sha"] == s for h in r["hashes"]):
            best = r
    return tuple(best.get("authors") or ()) if best else None


# ── 변경 ────────────────────────────────────────────────────────────────────

def register(root, issue_id, *, project: str, base: str, end: str, hashes, by: str = "",
             logf=None, authors=()) -> dict:
    """마감 등록 — 새 라운드(해시 전부 `waiting`). 최신 라운드와 base..end·해시가 같으면 `already`.

    거절 사유: bad_issue · bad_project · bad_sha(base/end/hashes) · no_hashes · hashes_mismatch.
    해시는 소문자 40자리만 받고, 중복은 첫 위치만 남긴다.
    """
    try:
        n = int(issue_id)
        if n <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _refuse(logf, issue_id, "register", "bad_issue", f"일감 번호가 아니다 — {issue_id!r}")
    if not str(project or "").strip():
        return _refuse(logf, n, "register", "bad_project", "project 가 비었다")
    b, e = _norm_sha(base), _norm_sha(end)
    for name, v in (("base", b), ("end", e)):
        if not _SHA.match(v):
            return _refuse(logf, n, "register", "bad_sha", f"{name} 가 40자리 해시가 아니다 — {v!r}")
    if isinstance(hashes, str) or not hashes:
        return _refuse(logf, n, "register", "no_hashes", "해시 목록이 비었다")
    shas: list[str] = []
    for h in hashes:
        v = _norm_sha(h)
        if not _SHA.match(v):
            return _refuse(logf, n, "register", "bad_sha", f"해시가 40자리가 아니다 — {v!r}")
        if v not in shas:
            shas.append(v)
    with _locked(root):
        data = _load(root)
        rs = data["records"].setdefault(str(n), [])
        last = rs[-1] if rs else None
        if last and last["base"] == b and last["end"] == e:
            if [h["sha"] for h in last["hashes"]] == shas:
                line = _emit(logf, n, "register", f"이미 등록 — 라운드 {last['round']} · {b[:12]}..{e[:12]}")
                return {"ok": True, "issue_id": n, "already": True, "round": last["round"],
                        "record": _copy(last), "log": [line]}
            return _refuse(logf, n, "register", "hashes_mismatch",
                           f"같은 범위 {b[:12]}..{e[:12]} 인데 해시 목록이 다르다"
                           f"(기존 {len(last['hashes'])}개 · 새 {len(shas)}개) — 히스토리가 바뀌었는지 사람이 확인한다",
                           round=last["round"])
        now = _now()
        rnum = (last["round"] + 1) if last else 1
        rnd = {"issue_id": n, "round": rnum, "project": str(project), "base": b, "end": e,
               "registered_at": now, "by": by, "authors": [str(x) for x in authors or ()],
               "hashes": [{"sha": s, "state": "waiting", "serial": "", "findings": None, "why": "",
                           "noted": False, "updated": now} for s in shas],
               "summary": {"state": "waiting", "item_id": "", "serial": "", "noted": False, "updated": now},
               "history": []}
        msg = f"라운드 {rnum} 등록 — {project} · {b[:12]}..{e[:12]} · 해시 {len(shas)}개"
        _hist(rnd, "register", msg + (f" · by {by}" if by else ""))
        rs.append(rnd)
        dropped = len(rs) - ROUND_CAP
        if dropped > 0:
            del rs[:dropped]
            msg += f" · 옛 라운드 {dropped}개 정리"
        _save(root, data)
        line = _emit(logf, n, "register", msg)
    return {"ok": True, "issue_id": n, "round": rnum, "record": _copy(rnd), "log": [line]}


def set_hash(root, issue_id, sha, *, state: str, serial: str = "", findings=None, why: str = "",
             round=None, logf=None) -> dict:   # noqa: A002 — 라운드 번호
    """해시 하나의 상태를 옮긴다 — 전이 규칙은 모듈 머리말.

    거절 사유: bad_state · not_registered · no_round · unknown_sha · bad_transition.
    종결 상태에서 같은 상태로 다시 오면 변경 없이 `already`.
    """
    n = int(issue_id)
    s = _norm_sha(sha)
    if state not in HASH_STATES or state == "waiting":
        return _refuse(logf, n, "set_hash", "bad_state",
                       f"상태는 {'/'.join(HASH_STATES[1:])} 중 하나다 — {state!r}")
    with _locked(root):
        data = _load(root)
        rnd, err = _pick_round(data, n, round)
        if err:
            return _refuse(logf, n, "set_hash", *err)
        h = _find_hash(rnd, s)
        if h is None:
            return _refuse(logf, n, "set_hash", "unknown_sha",
                           f"라운드 {rnd['round']} 에 {s[:12]} 가 없다", round=rnd["round"])
        cur = h["state"]
        if cur in HASH_TERMINAL:
            if cur == state:
                line = _emit(logf, n, "set_hash", f"{s[:12]} 이미 {cur}")
                return {"ok": True, "issue_id": n, "round": rnd["round"], "already": True,
                        "hash": dict(h), "log": [line]}
            return _refuse(logf, n, "set_hash", "bad_transition",
                           f"{s[:12]} 는 이미 종결({cur}) — {state} 로 옮기지 않는다",
                           round=rnd["round"], state=cur)
        if state not in HASH_NEXT[cur]:
            return _refuse(logf, n, "set_hash", "bad_transition",
                           f"{s[:12]} {cur} → {state} 는 허용되지 않는다(허용 {'/'.join(HASH_NEXT[cur])})",
                           round=rnd["round"], state=cur)
        h.update({"state": state, "updated": _now()})
        if serial:
            h["serial"] = str(serial)
        if findings is not None:
            h["findings"] = int(findings)
        if why:
            h["why"] = str(why)
        left = len(pending_hashes(rnd))
        msg = (f"{s[:12]} {cur}→{state}" + (f" · {h['serial']}" if h["serial"] else "")
               + (f" · 지적 {h['findings']}" if h["findings"] is not None else "")
               + (f" · {why}" if why else "") + f" · 남은 해시 {left}")
        _hist(rnd, "set_hash", msg)
        _save(root, data)
        line = _emit(logf, n, "set_hash", msg)
    return {"ok": True, "issue_id": n, "round": rnd["round"], "hash": dict(h),
            "all_terminal": left == 0, "log": [line]}


def mark_hash_noted(root, issue_id, sha, noted: bool = True, *, round=None, logf=None) -> dict:  # noqa: A002
    """해시의 진행 노트 게시 여부 — True 는 종결된 해시에만(아니면 `not_terminal`)."""
    n = int(issue_id)
    s = _norm_sha(sha)
    with _locked(root):
        data = _load(root)
        rnd, err = _pick_round(data, n, round)
        if err:
            return _refuse(logf, n, "noted", *err)
        h = _find_hash(rnd, s)
        if h is None:
            return _refuse(logf, n, "noted", "unknown_sha", f"라운드 {rnd['round']} 에 {s[:12]} 가 없다",
                           round=rnd["round"])
        if noted and h["state"] not in HASH_TERMINAL:
            return _refuse(logf, n, "noted", "not_terminal",
                           f"{s[:12]} 는 아직 {h['state']} — 종결 전에는 노트 표시를 하지 않는다",
                           round=rnd["round"], state=h["state"])
        h["noted"] = bool(noted)
        _hist(rnd, "noted", f"{s[:12]} noted={bool(noted)}")
        _save(root, data)
        line = _emit(logf, n, "noted", f"{s[:12]} noted={bool(noted)}")
    return {"ok": True, "issue_id": n, "round": rnd["round"], "hash": dict(h), "log": [line]}


def set_hash_missing(root, issue_id, sha, why: str, *, noted=None, round=None, logf=None) -> dict:  # noqa: A002
    """#932 미러 부재 사유와 별도 알림 표시. 해시 상태·종결 노트 표시는 바꾸지 않는다.

    같은 사유를 다시 기록해도 이미 성공한 알림 표시는 보존한다. Git/기한 판정과 노트 전송은
    호출부 몫이며, 노트 성공 뒤 noted=True를 남기는 사이의 프로세스 종료는 원자적이지 않다.
    """
    n, s = int(issue_id), _norm_sha(sha)
    if not isinstance(why, str) or not why.strip() or (noted is not None and type(noted) is not bool):
        return _refuse(logf, n, "missing", "bad_notice", "부재 사유와 올바른 알림 표시가 필요하다")
    with _locked(root):
        data = _load(root)
        rnd, err = _pick_round(data, n, round)
        if err:
            return _refuse(logf, n, "missing", *err)
        h = _find_hash(rnd, s)
        if h is None:
            return _refuse(logf, n, "missing", "unknown_sha", f"라운드 {rnd['round']} 에 {s[:12]} 가 없다")
        if h["state"] in HASH_TERMINAL:
            return _refuse(logf, n, "missing", "terminal", f"{s[:12]} 는 이미 종결({h['state']})")
        old = h.get("mirror_missing") or {}
        notice = dict(old) if old else {"detected_at": _now(), "noted": False}
        notice.pop("recovered_at", None)
        notice["why"] = why.strip()
        if noted is not None:
            notice["noted"] = noted
            if noted:
                notice.setdefault("noted_at", _now())
            else:
                notice.pop("noted_at", None)
        if notice == old:
            return {"ok": True, "issue_id": n, "round": rnd["round"], "already": True,
                    "hash": dict(h), "log": []}
        h["mirror_missing"] = notice
        msg = f"{s[:12]} 미러 부재 · noted={notice['noted']} · {notice['why']}"
        _hist(rnd, "missing", msg)
        _save(root, data)
        line = _emit(logf, n, "missing", msg)
    return {"ok": True, "issue_id": n, "round": rnd["round"], "hash": dict(h), "log": [line]}


def clear_hash_missing(root, issue_id, sha, *, round=None, logf=None) -> dict:  # noqa: A002
    """#932 실제 미러 도착을 복구로 기록한다. 이전 부재·알림 이력과 해시 상태는 보존한다."""
    n, s = int(issue_id), _norm_sha(sha)
    with _locked(root):
        data = _load(root)
        rnd, err = _pick_round(data, n, round)
        if err:
            return _refuse(logf, n, "missing_clear", *err)
        h = _find_hash(rnd, s)
        if h is None:
            return _refuse(logf, n, "missing_clear", "unknown_sha", f"라운드 {rnd['round']} 에 {s[:12]} 가 없다")
        notice = h.get("mirror_missing")
        if not notice or notice.get("recovered_at"):
            return {"ok": True, "issue_id": n, "round": rnd["round"], "already": True,
                    "hash": dict(h), "log": []}
        notice["recovered_at"] = _now()
        msg = f"{s[:12]} 미러 도착 확인 · 부재 대기 복구(상태 {h['state']} 유지)"
        _hist(rnd, "missing_clear", msg)
        _save(root, data)
        line = _emit(logf, n, "missing_clear", msg)
    return {"ok": True, "issue_id": n, "round": rnd["round"], "hash": dict(h), "log": [line]}


def set_summary(root, issue_id, *, state: str, item_id: str = "", serial: str = "", noted=None,
                round=None, logf=None) -> dict:   # noqa: A002
    """종합 리뷰 상태 — 규칙은 모듈 머리말.

    거절 사유: bad_state · not_registered · no_round · hashes_pending · closed.
    """
    n = int(issue_id)
    if state not in SUMMARY_STATES:
        return _refuse(logf, n, "summary", "bad_state", f"상태는 {'/'.join(SUMMARY_STATES)} 중 하나다 — {state!r}")
    with _locked(root):
        data = _load(root)
        rnd, err = _pick_round(data, n, round)
        if err:
            return _refuse(logf, n, "summary", *err)
        sm = rnd["summary"]
        cur = sm["state"]
        if cur in SUMMARY_CLOSED and state != cur:
            return _refuse(logf, n, "summary", "closed",
                           f"라운드 {rnd['round']} 종합 리뷰는 이미 {cur} — {state} 로 옮기지 않는다",
                           round=rnd["round"], state=cur)
        if state in SUMMARY_NEEDS_TERMINAL and not all_hashes_terminal(rnd):
            left = pending_hashes(rnd)
            return _refuse(logf, n, "summary", "hashes_pending",
                           f"종결 안 된 해시 {len(left)}개 — {', '.join(x[:12] for x in left[:5])}",
                           round=rnd["round"], pending=left)
        already = (cur == state and not item_id and not serial and noted is None)
        if already:
            line = _emit(logf, n, "summary", f"라운드 {rnd['round']} 이미 {cur}")
            return {"ok": True, "issue_id": n, "round": rnd["round"], "already": True,
                    "summary": dict(sm), "log": [line]}
        sm.update({"state": state, "updated": _now()})
        if item_id:
            sm["item_id"] = str(item_id)
        if serial:
            sm["serial"] = str(serial)
        if noted is not None:
            sm["noted"] = bool(noted)
        msg = (f"라운드 {rnd['round']} 종합 {cur}→{state}" + (f" · {sm['item_id']}" if sm["item_id"] else "")
               + (f" · {sm['serial']}" if sm["serial"] else "") + (f" · noted={sm['noted']}" if noted is not None else ""))
        _hist(rnd, "summary", msg)
        _save(root, data)
        line = _emit(logf, n, "summary", msg)
    return {"ok": True, "issue_id": n, "round": rnd["round"], "summary": dict(sm), "log": [line]}
