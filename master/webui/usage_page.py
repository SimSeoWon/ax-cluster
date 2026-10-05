"""/usage LLM 작업·토큰 시각화 화면 골조.

[DOC] build_report(JSON 계약은 master/work/usage_dashboard.py의 모듈 설명에 동결됨)을
소비한다. 집계 구현은 다른 조각 소유. 이 파일과 master/test_usage_page.py만 변경한다.
참조: master/webui/fixes_page.py, nav.py, master/status.py. 기존 어두운 색·좌측 메뉴 사용.
불필요한 lambda 대신 이름 있는 함수. 외부 CDN/새 의존성 금지.

UI 계약:
- 한국어 신규 페이지 /usage, 일간/주간/월간 전환, 프로젝트·기간·모델 계열 필터,
  작업 실행 기록/대화 세션 기록 선택. 숫자·날짜만 표시, 비용·대화·내부 경로 없음.
- 모델 계열 Claude/Codex/Gemini/로컬 LLM/미상. 실제 model별 요약 표와 기간별 토큰
  SVG 또는 canvas 그래프. 계열 색 구분·축·범례·값 확인·그래프 대체 표 제공.
- 레드마인 일감 표: 번호 링크 http://192.168.0.57:8080/issues/<양의정수>, 큐 제목,
  프로젝트, 참여 모델 계열, 호출·실패·미계측 건수, 측정 토큰, 최근 작업 시각.
- tokens=None은 '미계측', 실제 0은 '0'. 부분 미계측 건수와 미연결 호출을 명시한다.
  Gemini 기록 없음은 '기록 없음'. 작업/세션 합산하지 않고, 세션의 일감 미연결을 설명.
- 사용자/로그 문자열 HTML escape. 임베드 JSON의 </script> 등 안전 처리. 경고·에러도
  escape. 실제 예외/절대 경로는 사용자에게 보내지 않는다. 작은 화면에서 표 스크롤.
- render(report)는 완전한 HTML bytes. page(query)는 (HTTP 상태,HTML bytes).
  query는 project/period/start/end/family/source만 읽는다. loader=None이면 build_report,
  주입 loader는 동일 키워드 입력->dict 계약. ValueError는 400, 읽기 예외는 고정 안내 503.
  렌더러는 로그/파일/네트워크를 직접 읽지 않는다. 필터 GET /usage 링크·form으로 동작.
- 그래프·표에 input/cache/reasoning의 중복 합산 방지와 측정 토큰 합계임을 간단히 설명.

- [중요] 모델 계열별 토큰 비율 도넛 (사용자 결정 2026-10-04): 화면의 기간·프로젝트 필터를 따르되
  **언제나 source=all(모두 보기)로 센다** — 작업 실행 기록과 대화 세션 기록을 섞어 같은 호출을 두 번
  세지 않기 위해서다. 계열 필터는 따르지 않는다(비율 그림이 한 조각이 되기 때문 — family=""). 화면이
  이미 all·전체 계열이면 같은 보고서를 다시 쓴다. render(report, pie_report=None) 의 두 번째 인자로
  받고, page() 는 pie_loader(기본: loader 가 없을 때만 build_report)로 한 번 더 부른다. 주입 loader
  만 준 기존 호출은 두 번째 조회를 하지 않는다(그때 도넛은 「자료 없음」). 두 번째 조회가 실패해도
  화면은 200 이고 도넛 자리에 고정 안내만 둔다.

검사: python -B -m unittest master.test_usage_page -v. 주입 보고서로 검증, 라이브 조회 0.
"""
from __future__ import annotations

import html
import sys
from urllib.parse import urlencode

from ..status import _CSS
from .nav import SIDE_CSS, nav_html


_FAMILIES = ("claude", "codex", "gemini", "local", "unknown")
_FAMILY_LABEL = {
    "claude": "Claude", "codex": "Codex", "gemini": "Gemini",
    "local": "로컬 LLM", "unknown": "미상",
}
_FAMILY_COLOR = {
    "claude": "#d2a8ff", "codex": "#58a6ff", "gemini": "#3fb950",
    "local": "#e3b341", "unknown": "#8b949e",
}
_PERIOD_LABEL = {"daily": "일간", "weekly": "주간", "monthly": "월간"}
_SOURCE_LABEL = {"dispatch": "작업 실행 기록", "session": "대화 세션 기록", "all": "모두 보기"}

_EXTRA = """
.filters{display:flex;gap:.7rem;flex-wrap:wrap;align-items:end;margin:1rem 0;
 border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.8rem}
.filters label{display:flex;flex-direction:column;gap:.25rem;color:var(--dim);font-size:.76rem}
.filters input,.filters select,.filters button{font:inherit;color:var(--fg);background:var(--bg);
 border:1px solid var(--line);border-radius:6px;padding:.35rem .45rem}
.filters button{cursor:pointer;background:var(--card);color:var(--accent)}
.periods{display:flex;gap:.35rem}.periods a{border:1px solid var(--line);border-radius:999px;
 color:var(--dim);text-decoration:none;padding:.25rem .65rem;font-size:.8rem}
.periods a.on{color:var(--accent);border-color:var(--accent)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.6rem;margin:1rem 0}
.stat{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.65rem .8rem}
.stat b{display:block;font-size:1.25rem;font-variant-numeric:tabular-nums}.stat span{color:var(--dim);font-size:.76rem}
.note,.warning{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;
 background:var(--card);padding:.65rem .8rem;margin:.7rem 0;font-size:.84rem}
.warning{border-left-color:var(--warning)}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table.usage{border-collapse:collapse;width:100%;font-size:.82rem}
table.usage th,table.usage td{padding:.42rem .55rem;border-bottom:1px solid var(--line);
 text-align:left;white-space:nowrap;vertical-align:top}
table.usage th{color:var(--dim);font-size:.74rem}table.usage tr:last-child td{border-bottom:0}
.num{text-align:right!important;font-variant-numeric:tabular-nums}.dim{color:var(--dim)}
.families{display:flex;gap:.75rem;flex-wrap:wrap;margin:.5rem 0;font-size:.8rem;color:var(--dim)}
.swatch{display:inline-block;width:.7rem;height:.7rem;border-radius:2px;margin-right:.25rem}
.chart{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.5rem}
.chart svg{display:block;min-width:620px;width:100%;height:260px}.chart text{fill:var(--dim);font-size:11px}
.chart .axis{stroke:var(--line);stroke-width:1}.chart .grid{stroke:var(--line);stroke-width:.5}
.pie{display:flex;gap:1.2rem;flex-wrap:wrap;align-items:center;border:1px solid var(--line);
 border-radius:10px;background:var(--card);padding:.8rem}
.pie svg{width:180px;height:180px;flex:none}.pie svg text{fill:var(--fg);font-size:13px}
.pie svg .sub{fill:var(--dim);font-size:10px}.pie table.usage{width:auto;flex:1;min-width:260px}
.issue a{color:var(--accent);text-decoration:none}.issue a:hover{text-decoration:underline}
@media(max-width:760px){.filters{align-items:stretch}.filters label{min-width:45%}}
"""


def _int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _token(value) -> str:
    return "미계측" if value is None else f"{_int(value):,}"


def _family(value) -> str:
    value = str(value or "unknown").lower()
    return value if value in _FAMILIES else "unknown"


def _label(value) -> str:
    return _FAMILY_LABEL[_family(value)]


def _options(values, selected, labels=None) -> str:
    out = []
    for value in values:
        label = (labels or {}).get(value, value)
        sel = " selected" if value == selected else ""
        out.append(f'<option value="{html.escape(value, quote=True)}"{sel}>{html.escape(label)}</option>')
    return "".join(out)


def _period_links(report: dict) -> str:
    current = str(report.get("period") or "daily")
    base = {key: str(report.get(key) or "") for key in ("project", "start", "end", "family", "source")}
    links = []
    for period, label in _PERIOD_LABEL.items():
        query = urlencode({**base, "period": period})
        on = " on" if period == current else ""
        links.append(f'<a class="{on.strip()}" href="/usage?{html.escape(query, quote=True)}">{label}</a>')
    return '<div class="periods" aria-label="집계 기간">' + "".join(links) + "</div>"


def _filters(report: dict) -> str:
    projects = [str(p) for p in (report.get("projects") or [])]
    project_values = [""] + projects
    project_labels = {"": "전체 프로젝트", **{p: p for p in projects}}
    return f"""<form class="filters" method="get" action="/usage">
<label>프로젝트<select name="project">{_options(project_values, str(report.get('project') or ''), project_labels)}</select></label>
<label>시작일<input type="date" name="start" value="{html.escape(str(report.get('start') or ''), quote=True)}"></label>
<label>종료일<input type="date" name="end" value="{html.escape(str(report.get('end') or ''), quote=True)}"></label>
<label>모델 계열<select name="family">{_options([''] + list(_FAMILIES), str(report.get('family') or ''), {'': '전체 계열', **_FAMILY_LABEL})}</select></label>
<label>기록<select name="source">{_options(list(_SOURCE_LABEL), str(report.get('source') or 'dispatch'), _SOURCE_LABEL)}</select></label>
<input type="hidden" name="period" value="{html.escape(str(report.get('period') or 'daily'), quote=True)}">
<button type="submit">적용</button></form>"""


def _legend() -> str:
    return '<div class="families" aria-label="모델 계열 범례">' + "".join(
        f'<span><i class="swatch" style="background:{_FAMILY_COLOR[k]}"></i>{_FAMILY_LABEL[k]}</span>'
        for k in _FAMILIES) + "</div>"


def _chart(report: dict) -> str:
    buckets = report.get("buckets") or []
    dates = sorted({str(b.get("date") or "") for b in buckets if b.get("date")})
    values = {(str(b.get("date") or ""), _family(b.get("family"))):
              (None if b.get("tokens") is None else _int(b.get("tokens"))) for b in buckets}
    maximum = max((v for v in values.values() if v is not None), default=0)
    width, height, left, top, bottom = max(620, 90 + len(dates) * 70), 260, 60, 20, 48
    plot_h = height - top - bottom
    scale_max = maximum or 1
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="기간별 측정 토큰 그래프">']
    for step in range(5):
        y = top + plot_h * step / 4
        val = round(scale_max * (4 - step) / 4)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width-10}" y2="{y:.1f}"/><text x="4" y="{y+4:.1f}">{val:,}</text>')
    parts.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}"/>')
    group_w = (width - left - 15) / max(1, len(dates))
    bar_w = max(2, min(10, (group_w - 8) / len(_FAMILIES)))
    for di, date in enumerate(dates):
        gx = left + di * group_w + 4
        for fi, family in enumerate(_FAMILIES):
            value = values.get((date, family))
            if value is None:
                continue
            bar_h = (value / scale_max) * plot_h
            x, y = gx + fi * bar_w, top + plot_h - bar_h
            title = html.escape(f"{date} · {_FAMILY_LABEL[family]} · {value:,} 토큰")
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(1, bar_w-1):.1f}" height="{bar_h:.1f}" fill="{_FAMILY_COLOR[family]}"><title>{title}</title></rect>')
        parts.append(f'<text x="{gx:.1f}" y="{height-25}">{html.escape(date)}</text>')
    parts.append("</svg>")
    if not dates:
        parts.append('<div class="note">선택한 조건에 기간별 기록이 없다.</div>')
    return '<div class="chart">' + "".join(parts) + "</div>"


def _family_tokens(report) -> dict:
    """보고서의 models 에서 계열별 측정 토큰. 미계측(None)은 0 으로 세지 않고 빠진다."""
    out: dict[str, int] = {}
    for m in (report or {}).get("models") or []:
        if not isinstance(m, dict) or m.get("tokens") is None:
            continue
        family = _family(m.get("family"))
        out[family] = out.get(family, 0) + _int(m.get("tokens"))
    return out


_PIE_TITLE = "모델 계열별 토큰 비율 — 모두 보기 기준"
_PIE_NOTE = ("이 그림은 화면의 기간·프로젝트 필터를 따르되, 선택한 기록·계열과 무관하게 언제나 "
             "모두 보기(Claude·Codex는 대화 세션 기록, 그 밖은 작업 실행 기록)로 센다 — 같은 호출을 두 번 세지 않는다.")


def _pct(value: int, total: int) -> str:
    share = value / total * 100
    return "&lt;0.1%" if 0 < share < 0.05 else f"{share:.1f}%"    # 0이 아닌데 0.0%로 읽히지 않게


def _pie(pie_report) -> str:
    """계열별 측정 토큰 도넛(인라인 SVG) + 백분율·토큰 범례 표. 자료가 없으면 빈 상태."""
    note = f'<div class="sub">{html.escape(_PIE_NOTE)}</div>'
    if pie_report is None:
        return note + '<div class="note">모두 보기 기준 비율 자료를 읽지 못했다.</div>'
    tokens = _family_tokens(pie_report)
    total = sum(tokens.values())
    if total <= 0:
        return note + '<div class="note">선택한 조건에 측정 토큰 기록이 없어 비율을 그리지 않는다.</div>'
    rows = [(f, tokens[f]) for f in _FAMILIES if tokens.get(f, 0) > 0]
    size, r, width = 180, 70, 26
    circ = 2 * 3.141592653589793 * r
    gap = 2.0 if len(rows) > 1 else 0.0            # 조각 사이 2px 표면 틈 (한 계열이면 온전한 원)
    parts = [f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="{html.escape(_PIE_TITLE, quote=True)}">',
             f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="var(--line)" stroke-width="{width}"/>']
    offset = 0.0
    for family, value in rows:
        share = value / total
        length = max(0.5, share * circ - gap)
        title = f"{_FAMILY_LABEL[family]} · {_pct(value, total)} · {value:,} 토큰"   # 고정 라벨·숫자뿐
        parts.append(
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{_FAMILY_COLOR[family]}" '
            f'stroke-width="{width}" stroke-dasharray="{length:.2f} {circ:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {size/2} {size/2})">'
            f'<title>{title}</title></circle>')
        offset += share * circ
    parts.append(f'<text x="{size/2}" y="{size/2}" text-anchor="middle">{total:,}</text>'
                 f'<text class="sub" x="{size/2}" y="{size/2 + 15}" text-anchor="middle">측정 토큰</text></svg>')
    legend = "".join(
        f'<tr><td><i class="swatch" style="background:{_FAMILY_COLOR[f]}"></i>{_FAMILY_LABEL[f]}</td>'
        f'<td class="num">{_pct(v, total)}</td><td class="num">{v:,}</td></tr>' for f, v in rows)
    table = ('<table class="usage"><caption>도넛 대체 표</caption><tr><th>계열</th><th>비율</th>'
             f'<th>측정 토큰</th></tr>{legend}</table>')
    return note + '<div class="pie">' + "".join(parts) + table + "</div>"


def _bucket_table(report: dict) -> str:
    rows = []
    for b in report.get("buckets") or []:
        rows.append(f"<tr><td>{html.escape(str(b.get('date') or ''))}</td><td>{_label(b.get('family'))}</td>"
                    f"<td class=\"num\">{_int(b.get('calls'))}</td><td class=\"num\">{_int(b.get('failed_calls'))}</td>"
                    f"<td class=\"num\">{_int(b.get('unmeasured_calls'))}</td><td class=\"num\">{_token(b.get('tokens'))}</td></tr>")
    if not rows:
        rows.append('<tr><td colspan="6" class="dim">기록 없음</td></tr>')
    return '<div class="wrap"><table class="usage"><caption>그래프 대체 표</caption><tr><th>기간 시작</th><th>계열</th><th>호출</th><th>실패</th><th>미계측</th><th>측정 토큰</th></tr>' + "".join(rows) + "</table></div>"


def _model_table(report: dict) -> str:
    models = report.get("models") or []
    rows = []
    for m in models:
        rows.append(f"<tr><td>{_label(m.get('family'))}</td><td>{html.escape(str(m.get('model') or '모델 미상'))}</td>"
                    f"<td class=\"num\">{_int(m.get('calls'))}</td><td class=\"num\">{_int(m.get('measured_calls'))}</td>"
                    f"<td class=\"num\">{_int(m.get('unmeasured_calls'))}</td><td class=\"num\">{_int(m.get('failed_calls'))}</td>"
                    f"<td class=\"num\">{_token(m.get('tokens'))}</td></tr>")
    if not rows:
        rows.append('<tr><td colspan="7" class="dim">기록 없음</td></tr>')
    if models and not any(_family(m.get("family")) == "gemini" for m in models):
        rows.append('<tr><td>Gemini</td><td colspan="6" class="dim">기록 없음</td></tr>')
    return '<div class="wrap"><table class="usage"><tr><th>계열</th><th>실제 모델</th><th>호출</th><th>측정</th><th>미계측</th><th>실패</th><th>측정 토큰</th></tr>' + "".join(rows) + "</table></div>"


def _issue_table(report: dict) -> str:
    rows = []
    for issue in report.get("issues") or []:
        issue_id = _int(issue.get("issue_id"))
        number = (f'<a href="http://192.168.0.57:8080/issues/{issue_id}">#{issue_id}</a>'
                  if issue_id > 0 else '<span class="dim">미연결</span>')
        families = ", ".join(_label(v) for v in (issue.get("families") or [])) or "—"
        rows.append(f'<tr><td class="issue">{number}</td><td>{html.escape(str(issue.get("title") or ""))}</td>'
                    f'<td>{html.escape(str(issue.get("project") or ""))}</td><td>{html.escape(families)}</td>'
                    f'<td class="num">{_int(issue.get("calls"))}</td><td class="num">{_int(issue.get("failed_calls"))}</td>'
                    f'<td class="num">{_int(issue.get("unmeasured_calls"))}</td><td class="num">{_token(issue.get("tokens"))}</td>'
                    f'<td>{html.escape(str(issue.get("last_at") or ""))}</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="9" class="dim">연결된 레드마인 일감 기록 없음</td></tr>')
    return '<div class="wrap"><table class="usage"><tr><th>번호</th><th>큐 제목</th><th>프로젝트</th><th>참여 모델 계열</th><th>호출</th><th>실패</th><th>미계측</th><th>측정 토큰</th><th>최근 작업 시각</th></tr>' + "".join(rows) + "</table></div>"


def _reusable_for_pie(report: dict) -> bool:
    return str(report.get("source") or "") == "all" and not str(report.get("family") or "")


def render(report: dict, pie_report: dict | None = None) -> bytes:
    # [DOC] 공용 nav.nav_html('/usage')와 SIDE_CSS 사용. 보고서의 숫자와 큐 제목만 표시.
    #    pie_report 가 없고 report 자체가 모두 보기·전체 계열이면 그것으로 도넛을 그린다.
    if pie_report is None and _reusable_for_pie(report):
        pie_report = report
    totals = report.get("totals") or {}
    warnings = "".join(f'<div class="warning">{html.escape(str(w))}</div>'
                       for w in (report.get("warnings") or []))
    source = str(report.get("source") or "dispatch")
    session_note = ('<div class="note">작업 실행 기록과 대화 세션 기록은 서로 겹칠 수 있어 합산하지 않는다. '
                    '대화 세션은 작업 디렉토리로 프로젝트를 판정하며, 판정되지 않은 세션은 미분류로 모인다. 일감에는 연결되지 않는다.</div>' if source == "session"
                    else '<div class="note">모두 보기는 Claude·Codex를 대화 세션 기록에서, 그 밖의 계열을 작업 실행 기록에서 센다 — '
                    '같은 호출을 두 번 세지 않는다. 일감별 표는 작업 실행 기록에서 본다.</div>' if source == "all"
                    else '<div class="note">작업 실행 기록과 대화 세션 기록은 서로 겹칠 수 있어 합산하지 않는다.</div>')
    body = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AX 클러스터 — LLM 사용량</title>
<style>{_CSS}{SIDE_CSS}{_EXTRA}</style></head><body><div class="shell">{nav_html('/usage')}<main>
<h1>LLM 사용량</h1><div class="sub">작업과 토큰을 기간·프로젝트·모델 계열별로 본다</div>
{_period_links(report)}{_filters(report)}{warnings}{session_note}
<div class="stats"><div class="stat"><b>{_int(totals.get('calls')):,}</b><span>호출</span></div>
<div class="stat"><b>{_int(totals.get('failed_calls')):,}</b><span>실패</span></div>
<div class="stat"><b>{_int(totals.get('unmeasured_calls')):,}</b><span>미계측 호출</span></div>
<div class="stat"><b>{_token(totals.get('tokens'))}</b><span>측정 토큰</span></div>
<div class="stat"><b>{_int(totals.get('issues')):,}</b><span>연결 일감</span></div>
<div class="stat"><b>{_int(totals.get('unlinked_calls')):,}</b><span>미연결 호출</span></div></div>
<div class="note">토큰은 측정된 호출만 합산하며 부분 미계측 건수는 따로 표시한다. Claude 입력에는 캐시 읽기·생성을 더하고, Codex의 캐시 입력은 다시 더하지 않는다. reasoning은 output의 부분집합이므로 중복 합산하지 않는다. <b>미계측</b>은 실제 0과 다르다.</div>
<h2>{html.escape(_PIE_TITLE)}</h2>{_pie(pie_report)}
<h2>기간별 측정 토큰</h2>{_legend()}{_chart(report)}{_bucket_table(report)}
<h2>실제 모델별 요약</h2>{_model_table(report)}
<h2>레드마인 일감별 작업</h2><div class="sub">제목은 작업 큐에 저장된 제목이다.</div>{_issue_table(report)}
</main></div></body></html>"""
    return body.encode("utf-8")


def page(query=None, *, loader=None, pie_loader=None) -> tuple:
    # [DOC] build_report와 동결 키워드로 연결. ValueError/IO 오류를 안전한 HTTP 안내로 변환.
    #    [중요] 도넛용 두 번째 조회(source=all·family="")는 pie_loader 로 한다. 기본은 loader 가
    #    없을 때만 build_report — 주입 loader 의 호출 계약(한 번, 같은 키워드)을 바꾸지 않는다.
    if loader is None:
        from ..work.usage_dashboard import build_report
        loader = build_report
        if pie_loader is None:
            pie_loader = build_report
    query = query or {}

    def one(key: str) -> str:
        value = query.get(key, "") if hasattr(query, "get") else ""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        return str(value or "")

    params = {key: one(key) for key in ("project", "period", "start", "end", "family", "source")}
    params["period"] = params["period"] or "daily"
    params["source"] = params["source"] or "dispatch"
    try:
        report = loader(**params)
    except ValueError:
        return 400, _error_page("필터 값이 올바르지 않다. 날짜와 선택 항목을 확인한다.")
    except Exception:  # noqa: BLE001 - 저장소/로그 읽기 실패를 사용자에게 노출하지 않는다.
        return 503, _error_page("사용량 기록을 읽지 못했다. 잠시 뒤 다시 시도한다.")
    pie_report = None
    if isinstance(report, dict) and _reusable_for_pie(report):
        pie_report = report                      # 이미 모두 보기 — 다시 세지 않는다
    elif pie_loader is not None:
        try:
            pie_report = pie_loader(**{**params, "source": "all", "family": ""})
        except Exception as exc:  # noqa: BLE001 - 도넛 실패가 화면을 막지 않는다. 안내는 고정 문구다.
            print(f"[usage-page] 모두 보기 비율 조회 실패: {type(exc).__name__}", file=sys.stderr)
            pie_report = None
    return 200, render(report, pie_report)


def _error_page(message: str) -> bytes:
    body = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AX 클러스터 — LLM 사용량</title>
<style>{_CSS}{SIDE_CSS}{_EXTRA}</style></head><body><div class="shell">{nav_html('/usage')}
<main><h1>LLM 사용량</h1><div class="warning">{html.escape(message)}</div></main></div></body></html>"""
    return body.encode("utf-8")
