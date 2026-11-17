"""일감 스냅샷 — 기록 **그 시점**에 그 일감이 무엇을 요구했나 (`#979` T1).

사용자 요지(2026-11-17): 작업을 Redmine 일감으로 진행하니 원문이 「N번 진행하자」뿐이면 검색 로그·작업 기록만으로는
그 순간 무엇을 요청했는지 알 수 없다. 그래서 검색 로그(`_search_links`)와 `log_history` 가 일감 번호와 함께 **그 시점의**
제목 · 「문제·맥락」 요약 · 작업중 태스크를 남긴다. 나중에 일감 본문·플랜이 바뀌어도 기록은 당시 값을 들고 있다.

    snapshot(issue_id, *, fetch=None, now=None) -> dict

        {"issue_id": 211, "status": "ok", "fetched_at": "...+09:00",
         "subject": "...", "context": "…(200자)", "tasks": [{"id": "T2", "goal": "...", "state": "작업중"}],
         "tasks_note": ""}

    status   ok · 조회 실패(fetch_failed) — 실패해도 예외를 올리지 않는다(검색·기록을 막지 않는다).
    tasks    「작업중」 태스크 전부. 없으면 [] 이고 tasks_note 가 사유(플랜 없음 · 작업중 태스크 없음 · 플랜 형식 오류).
    context  스펙 영역의 「문제…」 절 첫 문단 · 스펙이 없으면 본문(플랜 영역 뺀) 첫 문단 — 200자.

[중요] 원문 속 숫자로 일감을 추정하지 않는다(`#855`) — 번호는 부르는 쪽이 준다(직접 지정 · 일감 잠금).
[중요] 읽기 공개 API 로 2초 제한(`#855` 화면과 같은 길) — API 키 조회(`docker exec`)를 타지 않는다.
       같은 일감은 60초 동안 재사용한다(검색마다 Redmine 을 두드리지 않는다). 실패는 캐시하지 않는다.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from datetime import datetime

TIMEOUT = 2.0
TTL = 60.0
CONTEXT_MAX = 200

OK = "ok"
FETCH_FAILED = "fetch_failed"
ACTIVE_STATE = "작업중"

_cache: dict = {}
_lock = threading.Lock()
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(.*?)\s*$")


def _fetch_public(issue_id: int) -> dict:
    """읽기 공개 API — 제목·본문. 실패는 예외로 올린다(`snapshot` 이 받아 상태로 바꾼다)."""
    from master.redmine import base_url
    with urllib.request.urlopen(f"{base_url()}/issues/{int(issue_id)}.json", timeout=TIMEOUT) as resp:
        iss = json.load(resp)["issue"]
    return {"subject": iss.get("subject") or "", "description": iss.get("description") or ""}


def _paragraphs(text: str):
    para: list[str] = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if not line.strip() or _HEADING_RE.match(line) and line.lstrip().startswith("#"):
            if para:
                yield " ".join(s.strip() for s in para)
                para = []
            continue
        para.append(line)
    if para:
        yield " ".join(s.strip() for s in para)


def _problem_section(spec: str) -> str:
    """스펙의 「문제…」 머리 아래 글. 그런 머리가 없으면 스펙 전체."""
    lines = (spec or "").replace("\r\n", "\n").split("\n")
    start = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line) if line.lstrip().startswith("#") else None
        if m is None:
            continue
        if start is not None:
            return "\n".join(lines[start:i])
        if m.group(1).startswith("문제"):
            start = i + 1
    return "\n".join(lines[start:]) if start is not None else spec or ""


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= CONTEXT_MAX else text[:CONTEXT_MAX - 1] + "…"


def context_of(description: str) -> str:
    """「문제·맥락」 첫 문단(200자). 스펙 영역이 없으면 본문(플랜 영역 뺀) 첫 문단."""
    from master import spec_block
    from master.context_synth.issue_context import split_spec
    try:
        spec = spec_block.parse(description or "")
    except Exception:                                       # noqa: BLE001 — 형식 오류면 본문으로
        spec = None
    if spec:
        text = _problem_section(spec)
    else:
        try:
            text = split_spec(description or "")
        except Exception:                                   # noqa: BLE001
            text = description or ""
    return _clip(next(_paragraphs(text), ""))


def tasks_of(description: str) -> tuple[list, str]:
    """(작업중 태스크 목록, 비었을 때 사유)."""
    from master import plan_block
    try:
        plan = plan_block.parse(description or "")
    except plan_block.PlanError as e:
        return [], f"플랜 형식 오류 — {e}"
    if plan is None:
        return [], "플랜 없음"
    active = [{"id": t.id, "goal": t.goal, "state": t.state}
              for t in plan.tasks if t.state == ACTIVE_STATE]
    return active, ("" if active else "작업중 태스크 없음")


def snapshot(issue_id, *, fetch=None, now=None) -> dict:
    """그 시점 일감 스냅샷. 예외를 올리지 않는다. `fetch`·`now` 는 검사 대역 자리."""
    n = int(issue_id)
    clock = now or time.monotonic
    t = clock()
    with _lock:
        hit = _cache.get(n)
        if hit and t - hit[0] < TTL:
            return dict(hit[1])
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        got = (fetch or _fetch_public)(n)
        desc = str(got.get("description") or "")
        tasks, note = tasks_of(desc)
        snap = {"issue_id": n, "status": OK, "fetched_at": stamp,
                "subject": str(got.get("subject") or ""), "context": context_of(desc),
                "tasks": tasks, "tasks_note": note}
    except Exception as e:                                  # noqa: BLE001 — 기록은 막지 않는다
        return {"issue_id": n, "status": FETCH_FAILED, "fetched_at": stamp,
                "why": f"{type(e).__name__}: {str(e)[:120]}"}
    with _lock:
        _cache[n] = (t, snap)
    return dict(snap)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def task_line(snap: dict) -> str:
    """한 줄 요약 — 화면·frontmatter 용. 예) `T2 실제 소스와 대조한 … (작업중)`."""
    if not snap or snap.get("status") != OK:
        return ""
    tasks = snap.get("tasks") or []
    if not tasks:
        return snap.get("tasks_note") or ""
    return " · ".join(f"{x['id']} {x.get('goal') or ''}".strip() for x in tasks)
