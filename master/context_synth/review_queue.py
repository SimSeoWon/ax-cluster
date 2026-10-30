"""리뷰 큐 — 리뷰를 색인 스레드에서 떼어 낸다 (`#634` · 설계안 `docs/17-review-queue.md`).

사용자 확정 2026-09-19: *"단일 쓰레드에서 컨텍스트 생성과 리뷰를 동시에 하다 보니 리뷰의
퀄리티가 떨어진다"* · *"원자 단위는 커밋"*.

## [중요] 이 모듈이 닫는 것 — 색인 인라인 리뷰의 결함 넷

    ⓐ 리뷰 실패 = 영구 유실 (뒤에서 워터마크가 전진한다)
    ⓑ 색인이 상용 콜 240초를 기다린다
    ⓒ 형식 위반 파일이 재리뷰를 영구 차단 — 가드가 **파일 존재**로 판정했다
    ⓓ `todo` 가 비면 리뷰가 아예 안 돈다 + 재시도 회차엔 부분 파일 목록만 본다

핵심은 **판정 근거를 파일 존재에서 상태로 옮기는 것**이다. ⓒⓓ 가 거기서 닫힌다.

## [중요] 재시도 상한은 새 정책이 아니다 — 원전 값 + `revise.py` 의 기존 갈래

    ENV(실행파일 없음·PATH)      1 즉시 중단   `work/revise.py` ENV_MARKERS
    결정적(diff 못 읽음)          1 즉시 중단   `#615` 의 여섯 번째 갈래
    QUOTA(429·session limit)    카운트 미소비 · 지연 후 재큐
    일시적(응답 없음·타임아웃)     3            원전 `verifier.py:55` _DEFAULT_MAX_ATTEMPTS
    형식 위반(format_ok=False)    3            원전의 revise 정책

🔴 실측이 이 배분을 받친다 — 카나리 `review-lost` 31행 중 **27건이 ENV, 3건이 결정적**이었다.
갈래 구분이 없어 결정적 실패를 계속 재시도한 결과다. 이 설계면 4행으로 줄었다.

[주의] **큐를 `reviews/` 안에 두지 않는다** — `plan_archive` 가 그 디렉토리를 `_archive/` 로
옮긴다(`fix_index` 가 번호를 경로 아닌 커밋에 묶은 것과 같은 이유).
[주의] 쓰는 쪽이 여럿이다(색인기·큐 소비자·8101) — 쓰기는 전부 `review_queue/.lock` 을 잡는다.
[중요] **깨진 큐를 빈 것으로 덮지 않는다** — 덮으면 대기 중인 항목이 조용히 사라진다.
못 읽으면 `ReviewQueueError` 로 멈춘다 (`fix_index` 와 같은 규약).

🔴 [중요] **주인 없는 `running` 은 회수한다** (`#749`, 사용자 결정 2026-10-05). 소비자가 끝나지
   못하면(systemd `TimeoutStartSec` · 재부팅 · OOM) 항목이 `running` 으로 남고, `claim` 은 `pending`
   만 집으므로 그 커밋 리뷰가 **조용히 영구 누락**됐다(실측 `075bbba2`, 15:45 시간 제한 종료).
   판정은 시간(리스)이 아니라 **사실**로 한다 — 소비자는 실행 내내 `.consumer.lock` 을 잡고,
   그 잠금을 얻은 소비자가 보는 `running` 은 살아 있는 주인이 없다(죽은 프로세스의 `flock` 은
   커널이 놓는다 — 이벤트 스풀 `consumer.lock` 과 같은 규약). 회수는 일시적 실패 한 번으로 센다 —
   매번 시간 제한에 걸리는 항목이 무한히 돌지 않고 상한(3)에서 `abandoned` 로 멈춘다.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

QUEUE_DIRNAME = "review_queue"
QUEUE_NAME = "queue.json"
SCHEMA = 1

STATES = ("pending", "running", "done", "failed", "abandoned")
KINDS = ("commit", "scope")

# ── 실패 갈래와 상한 ─────────────────────────────────────────────────────────
#
# [중요] 마커는 `work/revise.py` 에서 가져온다 — **같은 판정을 두 벌 두지 않는다.**
# 거기 주석이 근거를 갖고 있다(ENV: *"재시도는 토큰만 쓴다 — 첫 번째에 멈춘다"* ·
# QUOTA: *"한도가 공용 자원이라 조각을 죽이지 않는다"*).
ENV = "env"
DETERMINISTIC = "deterministic"
QUOTA = "quota"
TRANSIENT = "transient"
FORMAT = "format"

MAX_ATTEMPTS = {
    ENV: 1,             # 재시도는 토큰만 쓴다
    DETERMINISTIC: 1,   # 몇 번을 돌려도 같다
    TRANSIENT: 3,       # 원전 _DEFAULT_MAX_ATTEMPTS
    FORMAT: 3,
    # QUOTA 는 여기 없다 — 시도 횟수를 소비하지 않는다 (아래 `is_quota`)
}

# 결정적 실패 — 재시도가 의미 없는 사유. 실측 3건이 전부 이 문구였다.
DETERMINISTIC_MARKERS = (
    "diff 를 읽지 못했다",
    "diff를 읽지 못했다",
    "커밋을 찾지 못했다",
    "unknown revision",
    "bad object",
)


class ReviewQueueError(RuntimeError):
    """사람에게 보고하고 멈출 사유. [중요] 깨진 큐를 덮지 않는다."""


def classify(why: str) -> str:
    """실패 사유 문자열을 갈래로 가른다.

    [중요] **ENV·QUOTA 판정은 `work/revise.py` 의 마커를 그대로 쓴다.** 같은 판정을 두 벌
    두면 한쪽만 고쳐져 갈라진다(`#285` 가 「응답 없음」으로 PATH 를 감춘 것과 같은 병).
    """
    from ..work import revise as _rv
    text = why or ""
    low = text.lower()
    if any(m.lower() in low for m in _rv.QUOTA_MARKERS):
        return QUOTA
    # 🔴 `#847` — agy 쿨다운(`agy_models`: 「<모델>: model cooldown Ns」)은 호출 **전에** 막힌 것이고
    #    쿨다운은 실제 소진에서만 걸린다(`#845`). 공용 마커에 넣으면 레인·작업 조각 동작이 바뀌어
    #    (사용자 결정 (가)) 리뷰 큐에만 둔다 — 아래 `실행파일 없음` 과 같은 로컬 규칙이다.
    if "model cooldown" in low:
        return QUOTA
    if any(m.lower() in low for m in _rv.ENV_MARKERS):
        return ENV
    # PATH·실행파일 부재는 `#285` 가 남긴 우리 쪽 문구다 — 환경 실패다.
    if "실행파일 없음" in text or "PATH 미등록" in text:
        return ENV
    if any(m in text for m in DETERMINISTIC_MARKERS):
        return DETERMINISTIC
    return TRANSIENT


def is_quota(kind: str) -> bool:
    """한도 소진은 시도 횟수를 **소비하지 않는다** — 지연 후 재큐."""
    return kind == QUOTA


def cap(kind: str) -> int:
    return MAX_ATTEMPTS.get(kind, MAX_ATTEMPTS[TRANSIENT])


# ── 저장 ────────────────────────────────────────────────────────────────────

def queue_dir(root) -> Path:
    return Path(root) / QUEUE_DIRNAME


def queue_path(root) -> Path:
    return queue_dir(root) / QUEUE_NAME


@contextmanager
def _locked(root):
    d = queue_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read(root) -> dict:
    """[중요] 없으면 빈 큐, **깨졌으면 예외.** 덮으면 대기 항목이 조용히 사라진다."""
    f = queue_path(root)
    if not f.is_file():
        return {"schema": SCHEMA, "items": []}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ReviewQueueError(
            f"리뷰 큐를 읽지 못했다 ({type(e).__name__}) — 빈 것으로 덮지 않는다: {f}") from e
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ReviewQueueError(f"리뷰 큐 형식이 아니다 — 덮지 않는다: {f}")
    return data


def _write(root, data: dict) -> None:
    """원자적 교체 — 쓰다 죽어도 반쪽 파일이 남지 않는다."""
    f = queue_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


@contextmanager
def consumer_lock(root):
    """소비자 단일 실행 잠금(비차단). 얻으면 True, 다른 소비자가 돌고 있으면 False 를 내준다.

    [주의] 쓰기 잠금(`.lock`)과 다르다 — 그것은 한 번의 읽고-쓰기만 감싸고, 이것은 소비자
    **실행 전체**를 감싼다. 프로세스가 죽으면 커널이 놓으므로 스테일 잠금이 남지 않는다.
    """
    d = queue_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(d / ".consumer.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


ORPHAN_WHY = "소비자가 끝나지 못했다 — 주인 없는 running 회수 (시간 제한·재부팅 등)"


def reclaim_orphans(root, *, logf=None) -> list:
    """주인 없는 `running` 을 일시적 실패 한 번으로 돌린다. 반환: 회수한 항목들.

    [중요] **`consumer_lock` 을 쥔 소비자만 부른다** — 그래야 `running` 의 주인이 없다는 것이
    사실이 된다. 판정·상한은 `finish` 의 것을 그대로 쓴다(같은 판정을 두 벌 두지 않는다).
    """
    log = logf or (lambda m: None)
    orphans = [it["id"] for it in items(root, state="running")]
    out = []
    for iid in orphans:
        it = finish(root, iid, ok=False, why=ORPHAN_WHY, logf=log)
        log(f"[리뷰큐] 회수 {it['key'][:12]} running → {it['state']} "
            f"(시도 {it.get('attempts')}/{cap(it.get('last_kind') or TRANSIENT)})")
        out.append(it)
    return out


def _item_id(kind: str, key: str) -> str:
    return f"{kind}:{key}"


# ── 공개 API ────────────────────────────────────────────────────────────────

def enqueue(root, *, kind: str = "commit", key: str = "", files=None,
            requester: str = "", priority: int = 0, logf=None) -> dict:
    """항목을 등재한다. **이미 있으면 그대로 둔다**(커밋당 리뷰 한 번).

    `kind="commit"` 이면 `key` 는 커밋 해시, `kind="scope"` 면 대상(디렉토리·도메인)이다.
    `priority` 가 크면 먼저 꺼낸다 — 사람 요청(`#638`)이 자동 등재보다 앞선다.

    [중요] **등재는 파일 쓰기 한 번이다** — 색인 경로에서 불려도 LLM 을 기다리지 않는다(ⓑ).
    [중요] 종결된 항목(`done`)이 있으면 다시 넣지 않는다. 그러나 `abandoned`·`failed` 는
    **다시 넣을 수 있다** — 사람이 요청 창구로 부르는 복구 경로가 그것이다(`#638`).
    """
    log = logf or (lambda m: None)
    if kind not in KINDS:
        raise ReviewQueueError(f"알 수 없는 kind: {kind}")
    if not key:
        raise ReviewQueueError("key 가 비었다")
    iid = _item_id(kind, key)
    with _locked(root):
        data = _read(root)
        for it in data["items"]:
            if it.get("id") == iid and it.get("state") in ("pending", "running", "done"):
                log(f"[리뷰큐] 등재 생략 {iid} — 이미 {it.get('state')}")
                return it
        # 재등재: 종전 실패 항목은 자리를 비켜 준다
        data["items"] = [it for it in data["items"] if it.get("id") != iid]
        item = {
            "id": iid, "kind": kind, "key": key,
            "files": list(files or []),
            "state": "pending", "attempts": 0,
            "requester": requester, "priority": int(priority),
            "created_at": _now(), "updated_at": _now(),
            "last_kind": "", "last_why": "", "history": [],
        }
        data["items"].append(item)
        _write(root, data)
    log(f"[리뷰큐] 등재 {kind}={key[:12]} 파일 {len(item['files'])}건"
        + (f" 요청자={requester}" if requester else ""))
    return item


def claim(root, *, logf=None) -> dict | None:
    """`pending` 하나를 `running` 으로 바꿔 돌려준다. 없으면 `None`.

    우선순위 → 등재 순. [중요] **잠금 안에서 상태를 바꾼다** — 두 소비자가 같은 항목을
    집으면 리뷰가 두 번 난다(2026-09-13 NS 에서 같은 커밋 리뷰 150개가 났던 사고의 결).
    """
    log = logf or (lambda m: None)
    with _locked(root):
        data = _read(root)
        cands = [it for it in data["items"] if it.get("state") == "pending"]
        if not cands:
            return None
        cands.sort(key=lambda it: (-int(it.get("priority") or 0), it.get("created_at") or ""))
        it = cands[0]
        it["state"] = "running"
        it["attempts"] = int(it.get("attempts") or 0) + 1
        it["updated_at"] = _now()
        _write(root, data)
    limit = cap(it.get("last_kind") or TRANSIENT)
    log(f"[리뷰큐] 꺼냄 {it['kind']}={it['key'][:12]} 시도 {it['attempts']}/{limit}")
    return it


def finish(root, item_id: str, *, ok: bool, why: str = "", note: str = "",
           logf=None) -> dict:
    """한 회차의 결과를 적는다.

    성공이면 `done`. 실패면 **갈래를 가려** 상한과 비교한다:

        QUOTA        시도 횟수를 되돌리고 `pending` 으로 — 한도는 공용 자원이다
        상한 도달     `abandoned` — 사람에게 넘긴다 (요청 창구가 복구 경로)
        그 외        `pending` 으로 되돌려 다음 회차가 집는다
    """
    log = logf or (lambda m: None)
    with _locked(root):
        data = _read(root)
        it = next((x for x in data["items"] if x.get("id") == item_id), None)
        if it is None:
            raise ReviewQueueError(f"큐에 없는 항목: {item_id}")
        it["updated_at"] = _now()
        if ok:
            it["state"] = "done"
            it["last_kind"] = ""
            it["last_why"] = ""
            it["history"].append({"at": _now(), "result": "done", "note": note})
            _write(root, data)
            log(f"[리뷰큐] 완료 {it['kind']}={it['key'][:12]}" + (f" — {note}" if note else ""))
            return it

        k = classify(why)
        it["last_kind"] = k
        it["last_why"] = why
        it["history"].append({"at": _now(), "result": "failed", "kind": k, "why": why})
        if is_quota(k):
            # [중요] 횟수를 되돌린다 — 한도 소진은 이 항목의 잘못이 아니다.
            it["attempts"] = max(0, int(it.get("attempts") or 1) - 1)
            it["state"] = "pending"
            _write(root, data)
            log(f"[리뷰큐] 한도 — {it['key'][:12]} 시도 미소비 · 재큐 ({why[:60]})")
            return it
        limit = cap(k)
        if int(it.get("attempts") or 0) >= limit:
            it["state"] = "abandoned"
            _write(root, data)
            log(f"[리뷰큐] 포기 {it['key'][:12]} 갈래={k} 상한 {limit} 초과 — {why[:70]}")
            return it
        it["state"] = "pending"
        _write(root, data)
    log(f"[리뷰큐] 실패 {it['key'][:12]} 시도 {it['attempts']}/{limit} 갈래={k} — {why[:70]}")
    return it


def counts(root) -> dict:
    """상태별 건수. 읽기만 한다."""
    data = _read(root)
    out = {s: 0 for s in STATES}
    for it in data["items"]:
        s = it.get("state")
        if s in out:
            out[s] += 1
    return out


def items(root, *, state: str = "") -> list:
    data = _read(root)
    return [it for it in data["items"] if not state or it.get("state") == state]
