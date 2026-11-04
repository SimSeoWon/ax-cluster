"""색인기의 커밋 리뷰 등재를 일감 마감 추적에 잇는다 (`#884` T2).

사용자 결정(2026-11-04): 작업 세션이 `issue/<N>` 을 `main` 에 머지·push 하고 그 브랜치의 커밋 해시를
`issue_track.register` 로 등록하면, 그 해시들의 커밋 리뷰는 **우선순위 10**(사람 요청과 같다 ·
자동 등재 기본은 0)으로 앞당겨지고 시간 상한은 없다. 이 모듈은 그 연결만 맡는다 —
`issue_track` 이 리뷰 큐를 import 하지 않도록 둘 사이에 선다.

    on_enqueued(root, sha, item)   색인기가 등재한 직후(새 항목이든, 이미 있던 항목이든)
    on_skipped(root, sha, why)     색인기가 그 커밋을 등재하지 않기로 한 자리마다
    link_round(root, N)            등록 직후(T5) — 등록 **전에** 색인기가 이미 넣은 항목을 줍는다

## 큐 상태 → 해시 상태

    pending · running · failed   우선순위 10 으로 올리고 meta(issue_id·issue_round) → `queued`
    done                         `done` (리뷰 번호는 `fix_index.serial_for_commit` — 없으면 빈 값)
    abandoned                    `abandoned` (사유는 항목의 last_why)

[주의] `enqueue` 는 `abandoned`·`failed` 를 새 `pending` 으로 다시 넣으므로 `on_enqueued` 가
`abandoned` 를 보는 일은 사실상 없다 — `link_round` 가 줍는 옛 항목에서만 나온다.

## 건너뜀 → 해시 상태

    색인 전용 · 소스 변경 없음 · 머지(소스 없음) · 소스 밖 변경   → `skipped` (why = 색인기 사유)
    🔴 정상 리뷰가 이미 있다(`reviewed=True`)                   → `done`

마지막 갈래를 `skipped` 가 아니라 `done` 으로 적는 이유: 그 커밋은 **리뷰가 실제로 있다** —
큐 도입 전 인라인 경로가 만든 정상 리뷰다. `skipped` 는 「리뷰 대상이 아니었다」라서 T3 진행
노트·T4 종합 리뷰가 그 리뷰를 없는 것으로 읽는다. 판정은 문자열 대조가 아니라 호출부가 넘기는
`reviewed=True` 로 한다(사유 문구가 바뀌어도 갈래가 안 바뀐다). 리뷰 번호는 `fix_index` 에서 찾고,
아직 훑지 않아 없으면 빈 값 + why 에 파일 이름(색인기 사유)이 남는다.

## [중요] 색인을 깨지 않는다

연결은 색인의 **부수 작업**이다. 여기서 나는 예외는 전부 잡아 `[issue_link]` 한 줄로 찍고 돌아간다
— 색인기 커서 전진·합성·등재를 막지 않는다. 추적 파일이 깨졌으면(`IssueTrackError`) `[중요]` 로
크게 찍는다(그 파일은 `issue_track` 이 덮지 않으므로 사람이 볼 때까지 연결이 멈춘다).
추적 파일이 아예 없으면(등록된 일감이 없다) 잠금 파일도 만들지 않고 바로 돌아간다.
[주의] 추적에 없는 해시는 아무것도 바꾸지 않는다 — 우선순위 0 그대로다.
"""
from __future__ import annotations

from . import issue_track as it
from . import review_queue as rq

PRIORITY = 10          # 사용자 결정 2026-11-04 — 사람 요청(`#638`)과 같은 값
_QUEUED = ("pending", "running", "failed")
_TERMINAL = ("done", "abandoned")


def _say(logf):
    return logf if logf else print


def _fail(logf, op: str, sha: str, e: Exception) -> dict:
    log = _say(logf)
    if isinstance(e, it.IssueTrackError):
        log(f"[issue_link] [중요] {op} {str(sha)[:12]} — 일감 마감 추적 기록을 믿을 수 없다, "
            f"연결을 건너뛴다(색인은 계속): {e}")
        return {"ok": False, "reason": "track_corrupt", "why": str(e)}
    log(f"[issue_link] [주의] {op} {str(sha)[:12]} — 연결 실패, 건너뛴다(색인은 계속): "
        f"{type(e).__name__}: {e}")
    return {"ok": False, "reason": "error", "why": f"{type(e).__name__}: {e}"}


def _owner(root, sha: str):
    """(일감 번호, 라운드 번호, 해시 상태) 또는 None — `issue_of_hash` 와 같은 규칙
    (열린 라운드 중 가장 최근 등록)에 라운드 번호를 더한 것. 추적 파일이 없으면 바로 None."""
    if not sha or not it.state_path(root).exists():
        return None
    s = it._norm_sha(sha)
    best = None
    for r in it.open_rounds(root):
        h = it._find_hash(r, s)
        if h is not None:
            best = (r["issue_id"], r["round"], h["state"])
    return best


def _serial(root, sha: str) -> str:
    try:
        from . import fix_index as _fx
        return _fx.serial_for_commit(root, sha) or ""
    except Exception:                                   # noqa: BLE001 — 번호는 보조 정보다
        return ""


def _apply(root, n: int, rnum: int, sha: str, item: dict, logf) -> dict:
    """큐 항목 하나의 상태를 추적 기록에 옮긴다. 호출부가 예외를 잡는다."""
    log = _say(logf)
    state = item.get("state")
    out = {"ok": True, "linked": True, "issue_id": n, "round": rnum, "item_state": state}
    if state in _QUEUED:
        got = rq.set_priority(root, item.get("id") or rq._item_id("commit", sha), PRIORITY,
                              meta={"issue_id": n, "issue_round": rnum}, logf=log)
        out["priority"] = got.get("priority")
        res = it.set_hash(root, n, sha, state="queued", round=rnum, logf=log)
    elif state == "done":
        res = it.set_hash(root, n, sha, state="done", serial=_serial(root, sha), round=rnum, logf=log)
    elif state == "abandoned":
        res = it.set_hash(root, n, sha, state="abandoned", why=str(item.get("last_why") or "")[:200],
                          round=rnum, logf=log)
    else:
        log(f"[issue_link] [주의] #{n} {sha[:12]} — 모르는 큐 상태 {state!r}, 그대로 둔다")
        return {**out, "ok": False, "reason": "unknown_item_state"}
    out["hash_state"] = (res.get("hash") or {}).get("state") or res.get("state")
    if not res.get("ok"):
        out.update(ok=False, reason=res.get("reason"), why=res.get("why"))
    return out


def on_enqueued(root, sha, item, *, logf=None) -> dict:
    """색인기가 `commit:<sha>` 를 등재한 직후. 추적에 없는 해시면 `linked=False` 로 아무것도 안 한다."""
    try:
        own = _owner(root, sha)
        if own is None:
            return {"ok": True, "linked": False}
        n, rnum, _ = own
        return _apply(root, n, rnum, it._norm_sha(sha), item or {}, logf)
    except Exception as e:                              # noqa: BLE001 — 색인을 깨지 않는다
        return _fail(logf, "on_enqueued", sha, e)


def on_skipped(root, sha, why, *, reviewed: bool = False, logf=None) -> dict:
    """색인기가 그 커밋을 등재하지 않은 자리. `reviewed=True` 는 「정상 리뷰가 이미 있다」 —
    `done` 으로 적는다(근거는 모듈 머리말). 그 밖은 `skipped`."""
    try:
        own = _owner(root, sha)
        if own is None:
            return {"ok": True, "linked": False}
        n, rnum, _ = own
        s = it._norm_sha(sha)
        log = _say(logf)
        if reviewed:
            res = it.set_hash(root, n, s, state="done", serial=_serial(root, s), why=str(why or ""),
                              round=rnum, logf=log)
        else:
            res = it.set_hash(root, n, s, state="skipped", why=str(why or ""), round=rnum, logf=log)
        out = {"ok": bool(res.get("ok")), "linked": True, "issue_id": n, "round": rnum,
               "hash_state": (res.get("hash") or {}).get("state") or res.get("state")}
        if not res.get("ok"):
            out.update(reason=res.get("reason"), why=res.get("why"))
        return out
    except Exception as e:                              # noqa: BLE001 — 색인을 깨지 않는다
        return _fail(logf, "on_skipped", sha, e)


def link_round(root, issue_id, *, logf=None) -> dict:
    """최신 라운드의 `waiting` 해시 중 큐에 `commit:<sha>` 항목이 있는 것을 `on_enqueued` 와 같이 잇는다.

    T5 가 `register` 직후 부른다 — 등록 전에 색인기가 이미 등재한 해시를 줍는다. 큐 항목이 없는
    해시는 그대로 둔다(색인기가 아직 안 걸었다 — 걸 때 `on_enqueued`/`on_skipped` 가 잇는다).
    반환: `{"ok", "issue_id", "round", "linked": [...], "untouched": [...], "errors": [...]}`.
    """
    log = _say(logf)
    try:
        n = int(issue_id)
        rnd = it.current(root, n)
        if rnd is None:
            log(f"[issue_link] #{n} link_round — 등록된 라운드가 없다")
            return {"ok": False, "issue_id": n, "reason": "not_registered"}
        by_key = {}
        for x in rq.items(root):
            if x.get("kind") == "commit":
                by_key[str(x.get("key") or "").lower()] = x
        linked, untouched, errors = [], [], []
        for h in rnd["hashes"]:
            if h["state"] != "waiting":
                continue
            item = by_key.get(h["sha"])
            if item is None:
                untouched.append(h["sha"])
                continue
            try:
                res = _apply(root, n, rnd["round"], h["sha"], item, logf)
            except Exception as e:                      # noqa: BLE001
                res = _fail(logf, "link_round", h["sha"], e)
            (linked if res.get("ok") else errors).append({"sha": h["sha"], **res})
        log(f"[issue_link] #{n} 라운드 {rnd['round']} 연결 — 이음 {len(linked)} · "
            f"큐에 없음 {len(untouched)} · 실패 {len(errors)}")
        return {"ok": not errors, "issue_id": n, "round": rnd["round"], "linked": linked,
                "untouched": untouched, "errors": errors}
    except Exception as e:                              # noqa: BLE001
        return _fail(logf, "link_round", f"#{issue_id}", e)
