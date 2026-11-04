"""일감 범위 리뷰 상태 — 레드마인 「완료」 게이트가 읽는 기계 판정 (`#883` T3).

`issue_flow.finish(confirm=True)` 가 범위 리뷰를 큐에 넣는다(`kind=range`, `meta.issue_id`).
이 모듈은 그 일감의 범위 리뷰가 **끝났는지**, 끝났다면 **결정되지 않은 HIGH 지적이 남았는지**를
한 dict 로 돌려준다. 판정만 한다 — 큐·색인 상태를 바꾸지 않는다.

[중요] 별도 모듈로 둔 이유: 리뷰 큐(`review_queue`)와 수정 항목 색인(`fix_index`)을 **함께** 읽는
첫 자리다. `fix_index` 는 지금 큐를 모르고(번호·결정만 안다), 큐도 색인을 모른다 — 둘 중 하나에
넣으면 그 모듈이 다른 쪽에 의존하게 된다.

## 큐 상태 → `review`

    항목 없음                              none      — 완료 막힘 (리뷰가 등재되지 않았다)
    pending · running                      pending   — 완료 막힘 (재시도 대기·WAIT 미러 미도착 포함)
    failed  (현재 `finish` 는 쓰지 않는다)   failed    — 완료 막힘 · 종결 실패로 본다
    abandoned (상한 도달)                  abandoned — 완료 막힘 · 사람이 재등재해야 한다
    done                                   done      — 아래 항목 판정으로 넘어간다

한 일감에 범위 항목이 여럿이면(재시작·여러 번 finish) **`created_at` 이 가장 늦은 것**을 본다.
모든 id 는 `items` 에 싣는다.

## 항목 상태 → 막힘 (severity == "high" 인 항목만)

    open      막힘 — 아무도 결정하지 않았다
    accepted  막힘 — 「고치기로」 했을 뿐 아직 고치지 않았다(applied 까지)
    failed    막힘 — 수정 시도가 실패했다
    applied · dismissed(사유 필수) · stale   막지 않는다

`severity` 는 `review_collector._normalize_severity` 가 이미 `high`/`mid`/`low` 로 정규화한다
(원문 `높음`·`상`·`High` → `high`). mid·low 는 막지 않는다 — `open_other` 로 건수만 알린다.

[중요] **fail-closed 둘**: done 인데 번호를 못 찾았고 「스킵」 완료도 아니면 막는다(항목을
확인할 수 없다). 번호는 있는데 리뷰 파일이 사라졌어도(`missing`) 막는다.
[주의] 번호를 최신으로 하려고 `fix_index.sweep` 을 부른다 — 기존 `get_doc`·`run_range` 와 같은
방식이다. sweep 은 멱등이고 잠금을 잡으며, **새 리뷰 파일이 있을 때만** 색인에 번호를 쓴다.
"""
from __future__ import annotations

from pathlib import Path

from . import fix_index as fx
from . import review_queue as rq

BLOCKING_FIX_STATES = ("open", "accepted", "failed")
_PENDING = ("pending", "running")
_SKIP_PREFIX = "스킵"


def _range_items(root, issue_id: int) -> list:
    out = []
    for n, it in enumerate(rq.items(root)):
        if it.get("kind") != "range":
            continue
        meta = it.get("meta") or {}
        if str(meta.get("issue_id") or "") == str(issue_id):
            out.append((it.get("created_at") or "", n, it))
    out.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in out]


def _last_note(item: dict) -> str:
    for h in reversed(item.get("history") or []):
        if h.get("result") == "done":
            return h.get("note") or ""
    return ""


def issue_review_status(root, issue_id, *, logf=None) -> dict:
    """일감 `issue_id` 의 범위 리뷰 상태와 완료 가능 여부.

    반환:
        {"issue_id": int, "review": none|pending|failed|abandoned|done,
         "item_id": str, "items": [모든 범위 항목 id (오래된 것 먼저)], "latest_of": int,
         "queue_state": str, "attempts": int, "last_why": str,
         "serial": "R12" | "", "blocking": [{id, file, line, summary, severity, state}],
         "open_other": int, "ok_to_complete": bool, "why": str}
    """
    log = logf or (lambda m: None)
    root = Path(root)
    iid = int(issue_id)
    out = {"issue_id": iid, "review": "none", "item_id": "", "items": [], "latest_of": 0,
           "queue_state": "", "attempts": 0, "last_why": "", "serial": "",
           "blocking": [], "open_other": 0, "ok_to_complete": False, "why": ""}

    cands = _range_items(root, iid)
    out["items"] = [it["id"] for it in cands]
    out["latest_of"] = len(cands)
    if not cands:
        out["why"] = (f"#{iid} 의 범위 리뷰가 큐에 없다 — `issue_flow.finish(confirm=True)` 로 "
                      f"등재된 적이 없다. 등재 뒤 리뷰가 끝나야 완료할 수 있다")
        log(f"[issue-review] #{iid} 판정 none — 범위 항목 0 · 완료 막힘")
        return out
    it = cands[-1]
    multi = f" (범위 항목 {len(cands)}개 중 최신)" if len(cands) > 1 else ""
    st = it.get("state") or ""
    meta = it.get("meta") or {}
    out.update(item_id=it["id"], queue_state=st, attempts=int(it.get("attempts") or 0),
               last_why=it.get("last_why") or "")
    rng = f"{(meta.get('base') or '')[:8]}..{(meta.get('end') or '')[:8]}"

    if st in _PENDING:
        out["review"] = "pending"
        extra = f" · 직전 실패({it.get('last_kind')}): {out['last_why'][:80]}" if out["last_why"] else ""
        out["why"] = (f"#{iid} 범위 리뷰 {rng}{multi} 가 아직 끝나지 않았다 ({st}, 시도 "
                      f"{out['attempts']}){extra} — 리뷰 큐가 끝낼 때까지 기다린다")
        log(f"[issue-review] #{iid} 판정 pending — {it['id']} {st}{multi} · 완료 막힘")
        return out
    if st in ("failed", "abandoned"):
        out["review"] = st
        out["why"] = (f"#{iid} 범위 리뷰 {rng}{multi} 가 실패로 끝났다 ({st}, 시도 {out['attempts']}"
                      f" · {out['last_why'][:120]}) — 원인을 확인한 뒤 같은 범위를 다시 등재한다"
                      f"(review_queue.enqueue kind=range 는 실패 항목을 재등재할 수 있다)")
        log(f"[issue-review] #{iid} 판정 {st} — {it['id']}{multi} · 완료 막힘")
        return out
    if st != "done":
        out["review"] = "failed"
        out["why"] = f"#{iid} 범위 리뷰 항목 상태를 알 수 없다 ({st!r}) — 큐를 직접 확인한다"
        log(f"[issue-review] [주의] #{iid} 알 수 없는 큐 상태 {st!r} — 완료 막힘")
        return out

    out["review"] = "done"
    base, end = meta.get("base", ""), meta.get("end", "")
    fx.sweep(root, logf=log)
    serial = fx.serial_for_range(root, base, end) or (meta.get("serial") or "")
    out["serial"] = serial
    if not serial:
        note = _last_note(it)
        if note.startswith(_SKIP_PREFIX):
            out["ok_to_complete"] = True
            out["why"] = (f"#{iid} 범위 리뷰 {rng}{multi} 는 리뷰 없이 끝났다({note}) — "
                          f"지적이 없으므로 완료할 수 있다")
            log(f"[issue-review] #{iid} 판정 done(스킵) — 완료 가능")
        else:
            out["why"] = (f"#{iid} 범위 리뷰 {rng}{multi} 는 완료로 적혔지만 리뷰 번호를 찾지 못했다"
                          f" — 항목을 확인할 수 없어 막는다. reviews/_range 와 색인을 확인한다")
            log(f"[issue-review] [주의] #{iid} done 이지만 번호 없음 — 완료 막힘")
        return out

    doc = fx.get_doc(root, serial)
    if not doc.get("ok") or doc.get("missing"):
        out["why"] = (f"#{iid} 범위 리뷰 {serial}{multi} 의 문서를 읽지 못했다"
                      f"({doc.get('reason') or 'missing'}) — 항목을 확인할 수 없어 막는다")
        log(f"[issue-review] [주의] #{iid} {serial} 문서 없음 — 완료 막힘")
        return out
    blocking, other = [], 0
    for item in doc.get("items_detail") or []:
        state = (item.get("status") or {}).get("state", "open")
        if item.get("severity") == "high":
            if state in BLOCKING_FIX_STATES:
                blocking.append({"id": item["id"], "file": item.get("file", ""),
                                 "line": item.get("line", ""),
                                 "summary": (item.get("description") or "")[:200],
                                 "severity": "high", "state": state})
        elif state == "open":
            other += 1
    out["blocking"], out["open_other"] = blocking, other
    if blocking:
        ids = ", ".join(b["id"] for b in blocking)
        out["why"] = (f"#{iid} 범위 리뷰 {serial}{multi} 에 결정되지 않은 HIGH 지적 {len(blocking)}건: "
                      f"{ids} — 고쳐서 applied 로 기록하거나, 고치지 않을 것이면 사유와 함께 "
                      f"update_fix_status(state=dismissed, note=사유) 로 기각한다"
                      f" (accepted 는 고친 뒤 applied 가 될 때까지 막는다)")
        log(f"[issue-review] #{iid} 판정 done {serial} — HIGH 미결 {len(blocking)}건({ids}) · 완료 막힘")
    else:
        out["ok_to_complete"] = True
        out["why"] = (f"#{iid} 범위 리뷰 {serial}{multi} 완료 · 결정되지 않은 HIGH 지적 없음"
                      + (f" (mid·low 미결 {other}건은 막지 않는다)" if other else ""))
        log(f"[issue-review] #{iid} 판정 done {serial} — HIGH 미결 0 · 완료 가능")
    return out
