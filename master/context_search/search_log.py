"""RAG 요청 추적 (#837).

모든 검색은 분류와 원문 출처를 기록한다. 날짜별 search_logs/*.jsonl은 누적
관측 원본이며 삭제 회전하지 않는다. search_log.jsonl은 기존 분석기용 최근 캐시다.
사용자 원문은 확보된 값만 기록하며 검색 질의로 대체하지 않는다.
"""
from __future__ import annotations

import json
import re
import threading
import fcntl
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4
from datetime import datetime
from pathlib import Path

SEARCH_LOG_MAX_ENTRIES = 2000          # 원전 상수 그대로

_HANGUL_RE = re.compile(r"[가-힣]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# 원전 Phase η.12.16 — 같은 파일에 동시 append 하면 줄이 겹칠 수 있다. `ax-projects` 도
# uvicorn **단일 프로세스**이므로 프로세스 내 락으로 충분하다(워커를 늘리면 무효 — 늘리지 않는다).
_lock = threading.Lock()


_context = ContextVar("rag_search_context", default=None)
_suppressed = ContextVar("rag_search_suppressed", default=False)


def current_context() -> dict:
    return dict(_context.get() or {})


@contextmanager
def search_context(**metadata):
    """원문/작업 분류를 하위 검색에 전달하고 종료 후 원래 컨텍스트를 복구한다."""
    context = current_context()
    context.update(metadata)
    context["request_id"] = context.get("request_id") or uuid4().hex
    token = _context.set(context)
    try:
        yield context
    finally:
        _context.reset(token)


@contextmanager
def suppress_logging():
    """융합 검색 안의 벡터 호출을 중복 기록하지 않는다."""
    token = _suppressed.set(True)
    try:
        yield
    finally:
        _suppressed.reset(token)


def logging_suppressed() -> bool:
    return _suppressed.get()


def _field(hit, key, default=None):
    return hit.get(key, default) if isinstance(hit, dict) else getattr(hit, key, default)


def _snapshot(hits):
    out = []
    for rank, hit in enumerate(hits, 1):
        out.append({
            "rank": rank, "file_id": _field(hit, "file_id"),
            "source": _field(hit, "source", "vector"),
            "rrf_score": _field(hit, "rrf_score"),
            "similarity": _field(hit, "similarity", _field(hit, "score")),
            "bm25_score": _field(hit, "bm25_score"),
            "vector_rank": _field(hit, "vector_rank"),
            "bm25_rank": _field(hit, "bm25_rank"),
            "excerpt": _field(hit, "excerpt", ""),
            "meta": _field(hit, "meta", {}),
        })
    return out


def detect_lang(query: str) -> str:
    """질의 언어를 휴리스틱으로 분류한다 — `ko`/`en`/`mixed`/`other`. **원전 그대로.**

    5배 우세 규칙까지 원전과 같다. 바꾸면 언어별 갭 리포트가 과거 데이터와 비교 불가해진다.
    """
    if not query:
        return "other"
    ko = len(_HANGUL_RE.findall(query))
    en = len(_LATIN_RE.findall(query))
    if ko == 0 and en == 0:
        return "other"
    if ko > 0 and en == 0:
        return "ko"
    if en > 0 and ko == 0:
        return "en"
    if ko >= en * 5:
        return "ko"
    if en >= ko * 5:
        return "en"
    return "mixed"


def build_result_details(hits) -> list[dict]:
    """채널별 rank·score 추출. [중요] `Hit` **필드**를 읽는다 (`to_dict()` 는 셋을 버린다).

    원전과 같은 키 이름을 쓴다 — `vec_rank`·`bm25_rank` 는 분석기가 그 이름으로 읽는다.
    [주의] **0 도 의미 있는 값**(1위)이라 `None` 비교로 가른다. truthy 검사로 바꾸면 1위가 사라진다.
    """
    details = []
    for h in hits or []:
        d = {
            "file": _field(h, "file_id", None),
            "source": _field(h, "source", None),
            "rrf_score": round(_field(h, "rrf_score", 0.0) or 0.0, 6),
        }
        if _field(h, "vector_rank", None) is not None:
            d["vec_rank"] = _field(h, "vector_rank")
        if _field(h, "bm25_rank", None) is not None:
            d["bm25_rank"] = _field(h, "bm25_rank")
        if _field(h, "similarity", 0):
            d["similarity"] = round(_field(h, "similarity"), 4)
        if _field(h, "bm25_score", None) is not None:
            d["bm25_score"] = round(_field(h, "bm25_score"), 4)
        details.append(d)
    return details


def log_path_for(paths) -> Path:
    """`<프로젝트 데이터>/search_log.jsonl`. §5.5 — 프로젝트 안에 두지 않는다.

    정본은 `ProjectPaths.search_log` 다(데이터 위치는 그 클래스가 소유한다). 여기서 `root`
    로 조립하는 경로는 **그 속성이 없는 호출자**(테스트 대역)를 위한 폴백이다 — 두 곳이
    갈리지 않게 **속성이 있으면 그것을 쓴다.**
    """
    p = getattr(paths, "search_log", None)
    return Path(p) if p is not None else Path(paths.root) / "search_log.jsonl"


def log_search(paths, *, query: str | None = None, hits=None,
               caller: str | None = None, session_id: str | None = None,
               work_id: str | None = None, query_expanded: str | None = None,
               query_used: str | None = None, duration_ms: float | None = None,
               generation: str | None = None, error: str | None = None,
               **metadata) -> dict:
    """날짜별 원본과 기존 최근 로그에 기록한다. 실패는 반환값으로 관측한다."""
    hits = list(hits or [])
    if query is None and not hits and error is None:
        return {"ok": False, "reason": "질의도 결과도 없다 — 기록할 것이 없다", "written": False}
    context = current_context()
    context.update(metadata)
    now = datetime.now().astimezone()
    origin = context.get("user_request")
    missing = origin is None or origin == ""
    payload = {
        **context,
        "schema_version": 2, "ts": now.isoformat(),
        "project": getattr(paths, "name", ""),
        "request_id": context.get("request_id") or uuid4().hex,
        "search_id": uuid4().hex,
        "task_type": context.get("task_type") or "unclassified",
        "user_request": origin,
        "user_request_missing": missing,
        "user_request_source": "missing" if missing else context.get("user_request_source", "provided"),
        "query": query, "lang": detect_lang(query or ""),
        "query_expanded": query_expanded if query_expanded is not None else query,
        "query_used": query_used if query_used is not None else query,
        "results": [_field(h, "file_id") for h in hits],
        "result_details": build_result_details(hits),
        "result_snapshot": _snapshot(hits),
        "status": "error" if error is not None else ("success" if hits else "empty"),
        "error": error, "duration_ms": duration_ms, "generation": generation,
    }
    if len(hits) < 2:
        payload["zero_hit"] = len(hits) == 0
    for key, value in (("caller", caller), ("session_id", session_id), ("work_id", work_id)):
        if value is not None:
            payload[key] = value
    p = log_path_for(paths)
    archive = p.parent / "search_logs" / f"{now.date().isoformat()}.jsonl"
    try:
        line = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"직렬화 실패: {exc}", "written": False}
    written = False
    try:
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            # CLI와 서비스 사이에도 원본 append 및 최근 캐시 회전을 직렬화한다.
            with (p.parent / ".search-log.lock").open("a") as lockfile:
                fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
                archive.parent.mkdir(parents=True, exist_ok=True)
                with archive.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
                written = True
                with p.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
                rot = rotate(p)
                if not rot["ok"]:
                    return {"ok": False, "written": True, "reason": rot["reason"],
                            "search_id": payload["search_id"]}
    except OSError as exc:
        return {"ok": False, "reason": f"기록 실패: {exc}", "written": written,
                "search_id": payload["search_id"]}
    return {"ok": True, "written": True, "path": str(archive),
            "search_id": payload["search_id"], "request_id": payload["request_id"],
            "rotated": rot.get("removed", 0)}


def rotate(p: Path) -> dict:
    """최대 건수를 넘으면 오래된 것을 버린다 (원전 `_rotate_search_log`).

    [주의] 원전과 같이 **뒤쪽을 남긴다**(최신 우선). 회전 실패도 조용히 넘기지 않고 값으로 돌린다.
    """
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return {"ok": False, "reason": f"읽기 실패: {e}", "removed": 0}
    if len(lines) <= SEARCH_LOG_MAX_ENTRIES:
        return {"ok": True, "removed": 0}
    kept = lines[-SEARCH_LOG_MAX_ENTRIES:]
    try:
        p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "reason": f"쓰기 실패: {e}", "removed": 0}
    return {"ok": True, "removed": len(lines) - len(kept)}


def read_entries(paths, *, limit: int = 0) -> list[dict]:
    """기록을 읽어 온다 (분석기 `#161` 의 입력). [중요] **깨진 줄은 건너뛰고 세지 않는다.**

    한 줄이 깨졌다고 전체 분석을 포기하면 관측이 사라진다 — 그건 로그의 목적에 반한다.
    `limit` 을 주면 **최신** 그만큼만.
    """
    p = log_path_for(paths)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out[-limit:] if limit else out


def _all_entries(paths):
    """누적 원본과 도입 전 최근 로그를 합치되 신규 search_id 중복을 제거한다."""
    p = log_path_for(paths)
    files = [p] + sorted((p.parent / "search_logs").glob("????-??-??.jsonl"))
    seen = set()
    entries = []
    for file in files:
        if not file.is_file():
            continue
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            key = rec.get("search_id")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            entries.append(rec)
    return entries


def list_entries(paths, *, task_type='', query='', request_id='', status='',
                 date_from='', date_to='', offset=0, limit=50):
    """웹UI 조회. status=missing_origin은 실제 원문 미수집 요청만 고른다."""
    entries = []
    needle = query.casefold()
    for rec in _all_entries(paths):
        if task_type and rec.get("task_type", "unclassified") != task_type:
            continue
        if request_id and rec.get("request_id") != request_id:
            continue
        if status == "missing_origin":
            if not rec.get("user_request_missing", not rec.get("user_request")):
                continue
        elif status and rec.get("status") != status:
            continue
        day = rec.get("ts", "")[:10]
        if date_from and day < date_from or date_to and day > date_to:
            continue
        if needle and not any(needle in str(rec.get(key) or '').casefold()
                              for key in ("query", "query_expanded", "query_used", "user_request")):
            continue
        entries.append(rec)
    entries.sort(key=lambda rec: (rec.get("ts", ""), rec.get("search_id", "")), reverse=True)
    offset = max(0, int(offset))
    limit = min(200, max(1, int(limit)))
    return {"items": entries[offset:offset + limit], "total": len(entries),
            "offset": offset, "limit": limit}


def get_entry(paths, search_id):
    return next((rec for rec in _all_entries(paths) if rec.get("search_id") == search_id), None)
