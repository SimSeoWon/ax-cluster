"""RAG 요청 원문·검색 질의·당시 반환 결과의 읽기 전용 화면 (#837).

프로젝트 해석은 호출자가 담당한다. 이 모듈은 전달받은 paths만 조회하며,
파일 경로를 사용자 입력에서 만들거나 현재 문서를 다시 읽지 않는다.
"""
from __future__ import annotations

import html
from datetime import date
from urllib.parse import urlencode

from ..status import _CSS
from .nav import SIDE_CSS, nav_html

_FIELDS = ("project", "start", "end", "query", "task_type", "status", "request_id", "search_id", "offset", "limit")
_CSS_EXTRA = """
.filters{display:flex;flex-wrap:wrap;gap:.7rem;margin:1rem 0;padding:1rem;background:var(--card);border:1px solid var(--line);border-radius:10px}
.filters label{display:flex;flex-direction:column;font-size:.8rem;gap:.25rem}
input,select,button{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:.35rem}
.note{padding:.7rem;border:1px solid var(--line);border-radius:8px;margin:.7rem 0;color:var(--dim)}
.wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.85rem}th,td{padding:.5rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
td.query{min-width:15rem;white-space:pre-wrap}.group{border:1px solid var(--line);border-radius:10px;padding:1rem;margin:1rem 0;background:var(--card)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem;border:1px solid var(--line);border-radius:6px;padding:.7rem;background:var(--bg)}
.meta{font-size:.8rem;color:var(--dim);overflow-wrap:anywhere}.results td{overflow-wrap:anywhere;max-width:35rem}.results pre{min-width:15rem;margin:0}
.pager{display:flex;gap:1rem;margin:1rem 0}details{margin:.7rem 0}summary{cursor:pointer;color:var(--accent)}
"""


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _link(filters, **changes):
    values = {key: value for key, value in filters.items() if key in _FIELDS and value != ""}
    values.update(changes)
    return "/rag-logs?" + urlencode(values)


def _shell(body):
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>RAG 검색 로그</title><style>{_CSS}{SIDE_CSS}{_CSS_EXTRA}</style></head>'
            f'<body><div class="shell">{nav_html("/rag-logs")}<main><h1>RAG 검색 로그</h1>'
            f'{body}</main></div></body></html>').encode("utf-8")


def _options(options, selected):
    return "".join(f'<option value="{_e(value)}"{" selected" if value == selected else ""}>{_e(label)}</option>'
                   for value, label in options)


def _form(filters, projects):
    current = str(filters.get("project", ""))
    names = list(dict.fromkeys([current] + list(projects or [])))
    out = ['<form class="filters" method="get" action="/rag-logs">']
    out.append('<label>프로젝트<select name="project">' + _options([(p, p or "현재 마운트") for p in names], current) + '</select></label>')
    for key, label, kind in (("start", "시작일 (로그 기록일 기준)", "date"), ("end", "종료일 (로그 기록일 기준)", "date"),
                             ("query", "검색어·원문", "search"), ("task_type", "작업 분류", "text"),
                             ("request_id", "요청 ID", "text")):
        out.append(f'<label>{label}<input type="{kind}" name="{key}" value="{_e(filters.get(key, ""))}"></label>')
    out.append('<label>상태<select name="status">' + _options(
        [("", "전체"), ("success", "결과 있음"), ("empty", "결과 없음"), ("error", "검색 오류"), ("missing_origin", "사용자 원문 미수집")],
        filters.get("status", "")) + '</select></label>')
    out.append('<button type="submit">조회</button></form>')
    out.append('<p class="meta">날짜는 저장 시각에 기록된 시간대의 날짜를 기준으로 조회합니다. 현재 서버 기록은 KST(+09:00)입니다.</p>')
    return "".join(out)


def _results(entry):
    snapshot = entry.get("result_snapshot")
    if not isinstance(snapshot, list):
        snapshot = entry.get("result_details") or []
        note = '<p class="note">이전 형식 로그: 당시 반환 본문 전체는 미수집입니다. 보관된 결과 식별자·점수만 표시합니다.</p>'
    else:
        note = '<p class="meta">검색 당시 저장한 반환 결과입니다. 현재 문서를 다시 검색하거나 읽지 않습니다.</p>'
    out = [note, '<div class="wrap"><table class="results"><thead><tr><th>순위</th><th>문서</th><th>채널·점수</th><th>당시 본문</th></tr></thead><tbody>']
    for index, row in enumerate(snapshot, 1):
        if not isinstance(row, dict):
            continue
        scores = " · ".join(f"{key}: {_e(row[key])}" for key in
                            ("score", "rrf_score", "similarity", "bm25_score", "vector_rank", "bm25_rank") if row.get(key) is not None)
        channel = row.get("channel", row.get("source", ""))
        excerpt = row.get("excerpt", row.get("content_preview", row.get("body", "")))
        out.append(f'<tr><td>{_e(row.get("rank", index))}</td><td>{_e(row.get("file", row.get("file_id", "")))}</td>'
                   f'<td>{_e(channel)}<br>{scores}</td><td><pre>{_e(excerpt)}</pre></td></tr>')
    if not snapshot:
        out.append('<tr><td colspan="4">저장된 결과 없음</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)


def render(report) -> bytes:
    filters = report.get("filters", {})
    out = [_form(filters, report.get("projects", [])),
           '<p class="note">원문 → LLM 검색 질의 → 처리된 질의 → 반환 결과를 연결합니다. '
           '결과가 있다는 사실은 정답 적중률을 뜻하지 않습니다. 자동 작업과 원문 미수집을 구분합니다.</p>']
    if report.get("message"):
        out.append(f'<p class="note">{_e(report["message"])}</p>')
    items = report.get("items", [])
    out.append(f'<p class="meta">조건에 맞는 검색 {int(report.get("total", 0))}건 · 이번 화면 {len(items)}건</p>')
    groups = {}
    for entry in items:
        groups.setdefault(str(entry.get("request_id") or entry.get("search_id") or "이전 로그"), []).append(entry)
    display_groups = [(request_id, entries, False) for request_id, entries in groups.items()]
    selected = report.get("selected_entry")
    if selected:
        display_groups.insert(0, (str(selected.get("request_id") or selected.get("search_id")), [selected], True))
    for request_id, entries, separate_selection in display_groups:
        out.append(f'<section class="group"><h2>요청 {_e(request_id)}</h2>')
        if separate_selection:
            out.append('<p class="note">선택한 검색 상세 · 아래 관련 검색 목록의 현재 페이지에 포함되지 않은 기록입니다. 목록 건수에는 추가하지 않습니다.</p>')
        out.append(f'<a href="{_e(_link(filters, request_id=request_id, search_id="", offset=0))}">이 요청의 검색 모아 보기</a>')
        origins = list(dict.fromkeys(str(e.get("user_request")) for e in entries if e.get("user_request") is not None))
        if origins:
            for origin in origins:
                out.append('<h3>사용자 명령 원문</h3><pre>' + _e(origin) + '</pre>')
        else:
            automatic = all(str(e.get("task_type", "")).startswith("auto")
                            or e.get("task_type") in ("internal_collection", "context_synthesis") for e in entries)
            out.append('<p class="note">' + ("자동 작업 · 사용자 명령 원문 없음" if automatic else "사용자 명령 원문 미수집") + '</p>')
        for entry in entries:
            search_id = str(entry.get("search_id") or "")
            out.append('<details' + (' open' if filters.get("search_id") == search_id else '') + '><summary>'
                       + _e(entry.get("ts", "")) + ' · ' + _e(entry.get("task_type", "미분류"))
                       + ' · ' + _e(entry.get("status", "이전 로그")) + ' · ' + _e(entry.get("query", "")) + '</summary>')
            out.append('<p class="meta">검색 ID: ' + _e(search_id or "미수집")
                       + ' · 호출: ' + _e(entry.get("caller", "")) + ' · 원문 출처: ' + _e(entry.get("user_request_source", "미수집"))
                       + ' · 소요(ms): ' + _e(entry.get("duration_ms", "미수집")) + '</p>')
            for key, label in (("query", "LLM이 서버에 요청한 질의"), ("query_expanded", "시소러스 확장 질의"), ("query_used", "실제 검색 질의")):
                value = entry.get("llm_query", entry.get("query", "미수집")) if key == "query" else entry.get(key, "미수집")
                out.append(f'<h3>{label}</h3><pre>{_e(value)}</pre>')
            if entry.get("status") == "error":
                out.append('<p class="note">검색 실패 · 상세 오류는 서버 로그에서 확인하세요.</p>')
            out.append(_results(entry))
            if search_id:
                out.append(f'<p><a href="{_e(_link(filters, search_id=search_id))}">이 검색 상세 링크</a></p>')
            out.append('</details>')
        out.append('</section>')
    if not items and not selected:
        out.append('<p class="note">조건에 맞는 로그가 없습니다.</p>')
    offset, limit = int(report.get("offset", 0)), int(report.get("limit", 50))
    out.append('<div class="pager">')
    if offset:
        out.append(f'<a href="{_e(_link(filters, offset=max(0, offset-limit), search_id=""))}">이전</a>')
    if offset + len(items) < int(report.get("total", 0)):
        out.append(f'<a href="{_e(_link(filters, offset=offset+limit, search_id=""))}">다음</a>')
    out.append('</div>')
    return _shell("".join(out))


def page(paths, filters, *, projects=None, loader=None, detail_loader=None):
    """외부에서 등록·마운트 경계를 확인한 paths만 전달한다."""
    filters = {key: str(filters[key]) for key in _FIELDS if key in filters}
    filters["project"] = str(getattr(paths, "name", filters.get("project", "")))
    try:
        offset, limit = int(filters.get("offset", "0")), int(filters.get("limit", "50"))
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("invalid pagination")
        for key in ("start", "end"):
            if filters.get(key):
                date.fromisoformat(filters[key])
        if filters.get("start") and filters.get("end") and filters["start"] > filters["end"]:
            raise ValueError("invalid range")
        if loader is None or detail_loader is None:
            from ..context_search import search_log
            loader = loader or search_log.list_entries
            detail_loader = detail_loader or search_log.get_entry
        if filters.get("search_id"):
            selected = detail_loader(paths, filters["search_id"])
            if selected is None:
                return 404, _shell('<p class="note">검색 기록이 없습니다.</p>')
            if selected.get("request_id"):
                filters["request_id"] = str(selected["request_id"])
                # 상세는 같은 요청에 연결된 검색들을 보여 준다.
                for key in ("query", "status", "task_type", "start", "end"):
                    filters.pop(key, None)
                offset = 0
        report = loader(paths, task_type=filters.get("task_type", ""), query=filters.get("query", ""),
                        request_id=filters.get("request_id", ""), status=filters.get("status", ""),
                        date_from=filters.get("start", ""), date_to=filters.get("end", ""), offset=offset, limit=limit)
        if filters.get("search_id") and not selected.get("request_id"):
            report = {"items": [selected], "total": 1, "offset": 0, "limit": limit}
        elif filters.get("search_id") and not any(
                entry.get("search_id") == selected.get("search_id") for entry in report.get("items", [])):
            report = {**report, "selected_entry": selected}
        return 200, render({**report, "filters": filters, "projects": projects or [filters["project"]]})
    except ValueError:
        return 400, _shell('<p class="note">조회 조건을 확인하세요.</p>')
    except Exception:  # 서버 경로·예외 문자열을 브라우저에 노출하지 않는다.
        return 503, _shell('<p class="note">RAG 로그를 읽을 수 없습니다.</p>')
