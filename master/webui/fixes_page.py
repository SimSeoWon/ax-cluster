"""리뷰·플랜 목록 화면 (`/reviews`, `#629`) — 번호 · 종류 · 날짜 · 작성자 · 항목 수 · 결정 상태.

사용자 요청 2026-09-16: *"코드 작업을 메인 브랜치에 커밋하면 자동으로 리뷰를 작성하는데, 이걸
보여주는 웹UX와 [이때 각 리뷰나 플랜 문서마다 인덱스나 시리얼 넘버가 있고]"*

[중요] **요약만 그린다** (사용자 결정 2026-09-16). 8103 은 무인증이다 — 본문·지적 설명·소스
경로는 `fix_index.list_docs` 가 애초에 내지 않고, 이 화면은 그 요약만 쓴다. 본문은 `.33` 이
번호로 8101(토큰)에서 받는다.
[주의] **예외 문자열을 화면에 싣지 않는다** — `str(OSError)` 에 절대 경로가 들어 있다
(`orchestration.py` 머리말과 같은 이유). 사유는 고정 문구, 실제 예외는 로그(stderr → 저널)다.
"""
from __future__ import annotations

import html
import sys

from ..status import _CSS

_EXTRA = """
.nav{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0 1.2rem}
.nav a{border:1px solid var(--line);border-radius:999px;padding:.35rem .85rem;
 font-size:.82rem;text-decoration:none;background:var(--card);color:var(--fg)}
.nav a.on{border-color:var(--accent);color:var(--accent)}
.tabs{display:flex;gap:.4rem;flex-wrap:wrap;margin:0 0 1rem}
.tabs a{font-size:.8rem;padding:.2rem .7rem;border-radius:6px;border:1px solid var(--line);
 color:var(--dim);text-decoration:none}
.tabs a.on{color:var(--fg);border-color:var(--accent)}
.stats{display:flex;gap:.7rem;flex-wrap:wrap;margin:.2rem 0 1rem}
.stat{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.55rem .85rem;
 min-width:7.5rem}
.stat b{display:block;font-size:1.25rem;font-variant-numeric:tabular-nums}
.stat span{color:var(--dim);font-size:.78rem}
.note{border:1px solid var(--line);border-left:4px solid var(--accent);background:var(--card);
 border-radius:8px;padding:.7rem .9rem;margin:.9rem 0;font-size:.88rem}
.note code{color:var(--accent)}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table.fx{border-collapse:collapse;width:100%;font-size:.84rem}
table.fx th,table.fx td{padding:.42rem .6rem;border-bottom:1px solid var(--line);text-align:left;
 white-space:nowrap}
table.fx th{color:var(--dim);font-weight:600;font-size:.76rem}
table.fx tr:last-child td{border-bottom:0}
.serial{font-family:ui-monospace,Menlo,monospace;font-weight:650;color:var(--accent)}
.mono{font-family:ui-monospace,Menlo,monospace;color:var(--dim)}
.num{font-variant-numeric:tabular-nums;text-align:right}
.sev-high{color:var(--danger,#f85149);font-weight:650}
.sev-mid{color:var(--warning)}
.zero{color:var(--dim)}
.chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:0 .45rem;
 margin-right:.25rem;font-size:.74rem}
.chip.open{color:var(--dim)}
.chip.applied{border-color:var(--accent);color:var(--accent)}
.chip.dismissed,.chip.stale{color:var(--dim);text-decoration:line-through}
.chip.failed{border-color:var(--warning);color:var(--warning)}
.chip.accepted{color:var(--fg)}
.missing{color:var(--dim);font-style:italic}
.empty{color:var(--dim);padding:.8rem}
"""

STATE_LABEL = {"open": "미결", "accepted": "적용 예정", "applied": "적용됨",
               "dismissed": "기각", "stale": "해당 없음", "failed": "실패"}
_STATE_ORDER = ("open", "accepted", "applied", "failed", "stale", "dismissed")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _chips(states: dict) -> str:
    out = []
    for k in _STATE_ORDER:
        n = (states or {}).get(k)
        if n:
            out.append(f'<span class="chip {k}">{STATE_LABEL[k]} {n}</span>')
    return "".join(out) or '<span class="zero">—</span>'


def _sev(n: int, cls: str) -> str:
    return f'<td class="num {cls if n else "zero"}">{n}</td>'


def _review_rows(docs: list) -> str:
    rows = []
    for d in docs:
        sev = d.get("severity") or {}
        miss = ' <span class="missing">(파일 없음)</span>' if d.get("missing") else ""
        rows.append(
            f'<tr><td class="serial">{html.escape(d["serial"])}</td>'
            f'<td>{html.escape(d.get("created") or "")}</td>'
            f'<td>{html.escape(d.get("author") or "")}</td>'
            f'<td class="mono">{html.escape(d.get("commit") or "")}</td>'
            f'<td class="num">{int(d.get("files") or 0)}</td>'
            f'<td class="num">{int(d.get("items") or 0)}</td>'
            + _sev(int(sev.get("high") or 0), "sev-high")
            + _sev(int(sev.get("mid") or 0), "sev-mid")
            + _sev(int(sev.get("low") or 0), "")
            + f'<td>{_chips(d.get("states"))}{miss}</td></tr>')
    if not rows:
        return '<tr><td colspan="10" class="empty">자동 리뷰가 아직 없다</td></tr>'
    return "".join(rows)


def _plan_rows(docs: list) -> str:
    rows = []
    for d in docs:
        rid = str(d.get("redmine_issue_id") or "")
        miss = ' <span class="missing">(파일 없음)</span>' if d.get("missing") else ""
        rows.append(
            f'<tr><td class="serial">{html.escape(d["serial"])}</td>'
            f'<td>{html.escape(d.get("week") or "")}</td>'
            f'<td>{html.escape(d.get("author") or "")}</td>'
            f'<td>{html.escape(d.get("category") or "")}</td>'
            f'<td>{html.escape(d.get("severity_label") or "")}</td>'
            f'<td class="mono">{html.escape(d.get("plan_status") or "")}</td>'
            f'<td class="mono">{"#" + html.escape(rid) if rid else "—"}</td>'
            f'<td>{_chips(d.get("states"))}{miss}</td></tr>')
    if not rows:
        return '<tr><td colspan="8" class="empty">주간 플랜이 아직 없다 — 주말 배치가 만든다</td></tr>'
    return "".join(rows)


def _shell(body: str, *, title: str = "리뷰·플랜") -> str:
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AX 클러스터 — {html.escape(title)}</title><style>{_CSS}{_EXTRA}</style></head><body>
<h1>리뷰·플랜 — 번호로 부르는 수정 항목</h1>
<div class="sub">메인 커밋마다 자동 리뷰 · 주말마다 주간 플랜 · 번호를 골라 .33 에서 검토한다</div>
<div class="nav">
  <a href="/onboarding">온보딩 →</a>
  <a href="/cluster">클러스터 상태 →</a>
  <a class="on" href="/reviews">리뷰·플랜</a>
  <a href="/ontology">온톨로지 뷰어 →</a>
  <a href="/">컨텍스트 검색 →</a>
</div>
{body}
</body></html>"""


def render(project: str = "", *, registry=None, list_docs=None) -> tuple:
    """(상태코드, HTML). `registry`/`list_docs` 주입은 테스트 자리."""
    try:
        from ..context_search.paths import resolve
        from ..projects.config import Registry
        reg = registry or Registry.load()
        names = list(reg.names)
        name = project if project in names else (reg.active or (names[0] if names else ""))
        paths = resolve(name, registry=reg)
    except Exception as e:                                   # noqa: BLE001
        _log(f"[fix] 웹 목록 — 프로젝트 해석 실패: {type(e).__name__}: {e}")
        return 503, _shell('<div class="note">프로젝트를 해석하지 못했다 — 마스터 로그를 본다.</div>')

    if list_docs is None:
        from ..context_synth.fix_index import list_docs
    try:
        got = list_docs(paths.root)
    except Exception as e:                                   # noqa: BLE001
        _log(f"[fix] [중요] 웹 목록 실패 ({paths.name}): {type(e).__name__}: {e}")
        return 500, _shell('<div class="note">목록을 읽지 못했다 — 마스터 로그를 본다.</div>')
    swept = got.get("swept") or {}
    if swept.get("assigned"):
        _log(f"[fix] 웹 목록이 번호를 붙였다 ({paths.name}): {', '.join(swept['assigned'])}")

    docs = got.get("docs") or []
    reviews = [d for d in docs if d.get("kind") == "review"]
    plans = [d for d in docs if d.get("kind") == "plan"]
    open_items = sum(int((d.get("states") or {}).get("open") or 0) for d in docs)
    applied = sum(int((d.get("states") or {}).get("applied") or 0) for d in docs)

    tabs = "".join(
        f'<a class="{"on" if n == paths.name else ""}" href="/reviews?project={html.escape(n)}">'
        f'{html.escape(n)}</a>' for n in names)
    body = f"""<div class="tabs">{tabs}</div>
<div class="stats">
  <div class="stat"><b>{len(reviews)}</b><span>자동 리뷰</span></div>
  <div class="stat"><b>{len(plans)}</b><span>주간 플랜</span></div>
  <div class="stat"><b>{open_items}</b><span>미결 항목</span></div>
  <div class="stat"><b>{applied}</b><span>적용됨</span></div>
</div>
<div class="note">.33 에서 번호로 부른다 — <code>R12 검토해볼까?</code> · <code>P3 수정해볼까?</code>.
본문과 수정 행은 토큰이 필요한 자리에서만 내려간다. 리뷰 항목은 <code>R12-3</code> 처럼 행 번호까지 붙는다.</div>
<h2>자동 리뷰</h2>
<div class="wrap"><table class="fx">
<tr><th>번호</th><th>생성</th><th>작성자</th><th>커밋</th><th>파일</th><th>항목</th>
<th>high</th><th>mid</th><th>low</th><th>결정</th></tr>
{_review_rows(reviews)}
</table></div>
<h2>주간 플랜</h2>
<div class="wrap"><table class="fx">
<tr><th>번호</th><th>주차</th><th>작성자</th><th>분류</th><th>심각도</th><th>플랜 상태</th>
<th>레드마인</th><th>결정</th></tr>
{_plan_rows(plans)}
</table></div>"""
    return 200, _shell(body)


def page(project: str = "") -> tuple:
    st, text = render(project)
    return st, text.encode("utf-8")
