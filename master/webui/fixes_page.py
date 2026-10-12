"""리뷰·플랜 게시판 (`/reviews` 목록 · `/reviews/<번호>` 상세, `#629`).

사용자 요청 2026-09-16:
    *"코드 작업을 메인 브랜치에 커밋하면 자동으로 리뷰를 작성하는데, 이걸 보여주는 웹UX와 [이때 각
    리뷰나 플랜 문서마다 인덱스나 시리얼 넘버가 있고]"*
    *"웹 화면에서 게시판처럼 클릭하면 상세 페이지가 떠지면 좋겠다고"* ·
    *"클릭하면 해당 시리얼넘버[R32]를 캡처해서 클로드에 붙여넣을 수 있다던지"*

    목록   번호·날짜·작성자·항목 수·심각도·결정 상태 — 번호를 누르면 상세, [복사]는 `R32 검토해볼까?`
    상세   복사 상자(요청 문구·번호) · 항목 표 + 결정 · 리뷰·플랜 원문 전체

[중요] **상세는 LAN 공개다 — 사용자 결정 2026-09-16.** 처음엔 「요약만」(본문은 8101 토큰 경로로만)
이었고, 상세 페이지를 요청하며 공개 범위를 다시 물었을 때 사용자가 **LAN 공개(클릭하면 바로)** 를
골랐다. 8103 은 인증이 없고 남은 방어는 ufw LAN 한 겹이다(`machines/sim-desktop.md`).
[주의] 목록은 여전히 요약만 싣는다 — 본문은 번호를 눌러 들어간 자리에서만 나온다.
[주의] **예외 문자열을 화면에 싣지 않는다** — `str(OSError)` 에 절대 경로가 들어 있다
(`orchestration.py` 머리말과 같은 이유). 사유는 고정 문구, 실제 예외는 로그(stderr → 저널)다.
[주의] **복사는 `navigator.clipboard` 만으로는 안 된다** — `http://192.168.0.57` 은 보안 문맥이
아니라 그 API 가 막힌다. `execCommand('copy')` 로 떨어지고, 그것도 안 되면 버튼이 직접 선택하라고 말한다.
"""
from __future__ import annotations

import html
import re
import sys
from urllib.parse import quote

from ..status import _CSS
from .nav import SIDE_CSS, nav_html

_EXTRA = """
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
 white-space:nowrap;vertical-align:top}
table.fx th{color:var(--dim);font-weight:600;font-size:.76rem}
table.fx tr:last-child td{border-bottom:0}
table.fx tr.row:hover td{background:rgba(88,166,255,.06)}
table.fx td.wide{white-space:normal;min-width:16rem}
.serial a{font-family:ui-monospace,Menlo,monospace;font-weight:650;color:var(--accent);
 text-decoration:none}
.serial a:hover{text-decoration:underline}
.mono{font-family:ui-monospace,Menlo,monospace;color:var(--dim)}
.num{font-variant-numeric:tabular-nums;text-align:right}
.sev-high{color:var(--danger,#f85149);font-weight:650}
.sev-mid{color:var(--warning)}
.zero{color:var(--dim)}
.chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:0 .45rem;
 margin-right:.25rem;font-size:.74rem;white-space:nowrap}
.chip.open{color:var(--dim)}
.chip.applied{border-color:var(--accent);color:var(--accent)}
.chip.dismissed,.chip.stale{color:var(--dim);text-decoration:line-through}
.chip.failed{border-color:var(--warning);color:var(--warning)}
.chip.accepted{color:var(--fg)}
.missing{color:var(--dim);font-style:italic}
.empty{color:var(--dim);padding:.8rem}
button.cp{font:inherit;font-size:.74rem;padding:.12rem .55rem;border-radius:6px;cursor:pointer;
 border:1px solid var(--line);background:transparent;color:var(--dim)}
button.cp:hover{color:var(--accent);border-color:var(--accent)}
.copybox{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;border:1px solid var(--accent);
 border-radius:10px;background:var(--card);padding:.75rem .9rem;margin:.4rem 0 1rem}
.copybox .phrase{font-family:ui-monospace,Menlo,monospace;font-size:1.15rem;font-weight:650;
 color:var(--accent);user-select:all;padding:.15rem .5rem;border:1px dashed var(--line);border-radius:6px}
.copybox button.cp{font-size:.82rem;padding:.3rem .8rem;color:var(--fg)}
.copybox .hint{color:var(--dim);font-size:.8rem;flex-basis:100%}
.meta{color:var(--dim);font-size:.85rem;margin:.2rem 0 .6rem}
.meta b{color:var(--fg);font-weight:600}
.decision{font-size:.78rem;color:var(--dim);margin-top:.2rem;white-space:normal}
.back{font-size:.82rem;color:var(--dim);text-decoration:none}
details.src{margin:1rem 0}
details.src summary{cursor:pointer;color:var(--dim);font-size:.85rem}
.doc{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.4rem 1rem 1rem;
 margin-top:.5rem;font-size:.88rem;line-height:1.55}
.doc h2,.doc h3,.doc h4,.doc h5{margin:1rem 0 .4rem}
.doc h3{font-size:1rem;color:var(--accent)}
.doc h4,.doc h5{font-size:.9rem}
.doc code{color:var(--accent)}
.doc pre.fm{color:var(--dim);font-size:.8rem;white-space:pre-wrap}
.doc .wrap{margin:.3rem 0 .6rem}
.doc .mod{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:10px;
 background:var(--bg);margin:1rem 0;padding:.2rem .9rem .7rem;min-width:0;max-width:100%}
.doc .mod-head{display:flex;flex-wrap:wrap;gap:.3rem .8rem;align-items:baseline;
 border-bottom:1px solid var(--line);padding:.55rem 0 .45rem;margin-bottom:.3rem}
.doc .mod-name{font-family:ui-monospace,Menlo,monospace;font-size:1.08rem;font-weight:700;
 color:var(--fg);overflow-wrap:anywhere;min-width:0}
.doc .mod-count{font-size:.78rem;color:var(--dim);font-variant-numeric:tabular-nums}
.doc .mod-count b{color:var(--fg);font-weight:650}
.doc .mod h4.sub{font-size:.84rem;font-weight:600;color:var(--dim);margin:.8rem 0 .3rem}
"""

_COPY_JS = """<script>
function axFallbackCopy(t){var a=document.createElement('textarea');a.value=t;
a.setAttribute('readonly','');a.style.position='fixed';a.style.opacity='0';
document.body.appendChild(a);a.select();var ok=false;
try{ok=document.execCommand('copy');}catch(e){ok=false;}document.body.removeChild(a);return ok;}
function axCopy(btn){var t=btn.getAttribute('data-copy');var label=btn.textContent;
function done(ok){btn.textContent=ok?'복사됨 ✓':'복사 실패 — 직접 선택';
setTimeout(function(){btn.textContent=label;},1600);}
if(navigator.clipboard&&window.isSecureContext){
navigator.clipboard.writeText(t).then(function(){done(true);},function(){done(axFallbackCopy(t));});
}else{done(axFallbackCopy(t));}}
</script>"""

STATE_LABEL = {"open": "미결", "accepted": "적용 예정", "applied": "적용됨",
               "dismissed": "기각", "stale": "해당 없음", "failed": "실패"}
_STATE_ORDER = ("open", "accepted", "applied", "failed", "stale", "dismissed")
_SEV_LABEL = {"high": "높음", "mid": "중간", "low": "낮음"}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def ask_phrase(serial: str) -> str:
    """`.33` 에 붙여넣을 요청 문구 — `ax-fix` 스킬의 발동 문구와 같은 모양이다."""
    return f"{serial} 검토해볼까?"


def _copy_btn(text: str, label: str = "복사") -> str:
    return (f'<button class="cp" type="button" data-copy="{html.escape(text, quote=True)}" '
            f'onclick="axCopy(this)">{html.escape(label)}</button>')


def _detail_href(serial: str, project: str) -> str:
    return f"/reviews/{quote(serial)}?project={quote(project)}"


def _chips(states: dict) -> str:
    out = []
    for k in _STATE_ORDER:
        n = (states or {}).get(k)
        if n:
            out.append(f'<span class="chip {k}">{STATE_LABEL[k]} {n}</span>')
    return "".join(out) or '<span class="zero">—</span>'


def _sev(n: int, cls: str) -> str:
    return f'<td class="num {cls if n else "zero"}">{n}</td>'


def _serial_cell(d: dict, project: str) -> str:
    s = d["serial"]
    return (f'<td class="serial"><a href="{_detail_href(s, project)}">{html.escape(s)}</a></td>')


def _review_rows(docs: list, project: str) -> str:
    rows = []
    for d in docs:
        sev = d.get("severity") or {}
        miss = ' <span class="missing">(파일 없음)</span>' if d.get("missing") else ""
        rows.append(
            '<tr class="row">' + _serial_cell(d, project)
            + f'<td>{html.escape(d.get("created") or "")}</td>'
            f'<td>{html.escape(d.get("author") or "")}</td>'
            f'<td class="mono">{html.escape(d.get("commit") or "")}</td>'
            f'<td class="num">{int(d.get("files") or 0)}</td>'
            f'<td class="num">{int(d.get("items") or 0)}</td>'
            + _sev(int(sev.get("high") or 0), "sev-high")
            + _sev(int(sev.get("mid") or 0), "sev-mid")
            + _sev(int(sev.get("low") or 0), "")
            + f'<td>{_chips(d.get("states"))}{miss}</td>'
            f'<td>{_copy_btn(ask_phrase(d["serial"]))}</td></tr>')
    if not rows:
        return '<tr><td colspan="11" class="empty">자동 리뷰가 아직 없다</td></tr>'
    return "".join(rows)


def _plan_rows(docs: list, project: str) -> str:
    rows = []
    for d in docs:
        rid = str(d.get("redmine_issue_id") or "")
        miss = ' <span class="missing">(파일 없음)</span>' if d.get("missing") else ""
        rows.append(
            '<tr class="row">' + _serial_cell(d, project)
            + f'<td>{html.escape(d.get("week") or "")}</td>'
            f'<td>{html.escape(d.get("author") or "")}</td>'
            f'<td>{html.escape(d.get("category") or "")}</td>'
            f'<td>{html.escape(d.get("severity_label") or "")}</td>'
            f'<td class="mono">{html.escape(d.get("plan_status") or "")}</td>'
            f'<td class="mono">{"#" + html.escape(rid) if rid else "—"}</td>'
            f'<td>{_chips(d.get("states"))}{miss}</td>'
            f'<td>{_copy_btn(ask_phrase(d["serial"]))}</td></tr>')
    if not rows:
        return '<tr><td colspan="9" class="empty">주간 플랜이 아직 없다 — 주말 배치가 만든다</td></tr>'
    return "".join(rows)


def _shell(body: str, *, title: str = "리뷰·플랜", heading: str = "리뷰·플랜 — 번호로 부르는 수정 항목",
           sub: str = "로컬 초고를 Antigravity가 퇴고한 자동 리뷰 · 주말 플랜 · 번호로 적용 여부 검토") -> str:
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AX 클러스터 — {html.escape(title)}</title><style>{_CSS}{_EXTRA}{SIDE_CSS}</style>{_COPY_JS}</head><body>
<!-- 좌측 목록은 공용(nav.py) — 종전의 화면별 .nav 줄을 대신한다 (사용자 결정 2026-10-04) -->
<div class="shell">{nav_html("/reviews")}<main>
<h1>{html.escape(heading)}</h1>
<div class="sub" style="margin-bottom:1.2rem">{html.escape(sub)}</div>
{body}
</main></div>
</body></html>"""


def _resolve(project: str, registry):
    from ..context_search.paths import resolve
    from ..projects.config import Registry
    reg = registry or Registry.load()
    names = list(reg.names)
    name = project if project in names else (reg.active or (names[0] if names else ""))
    return reg, names, resolve(name, registry=reg)


# ── 목록 ─────────────────────────────────────────────────────────────────────

def render(project: str = "", *, registry=None, list_docs=None) -> tuple:
    """(상태코드, HTML). `registry`/`list_docs` 주입은 테스트 자리."""
    try:
        reg, names, paths = _resolve(project, registry)
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
    candidates = got.get("dismissal_candidates") or {}
    candidate_note = ""
    if candidates.get("error"):
        candidate_note = '<div class="note">기각 후보 수집 결과를 읽지 못했다.</div>'
    elif candidates.get("count"):
        stale = sum(bool(c.get("stale")) for c in candidates.get("candidates", []))
        candidate_note = (f'<div class="note">주말 기각 후보 {int(candidates["count"])}건'
                          f' · 재확인 필요 {stale}건 · 기준 '
                          f'{html.escape(str(candidates.get("main_sha") or "")[:12])}'
                          f' · {html.escape(str(candidates.get("collected_at") or ""))}'
                          ' · 상태는 변경되지 않았다. 근거는 요청자 목록 조회로 확인한다.</div>')
    reviews = [d for d in docs if d.get("kind") == "review"]
    plans = [d for d in docs if d.get("kind") == "plan"]
    open_items = sum(int((d.get("states") or {}).get("open") or 0) for d in docs)
    applied = sum(int((d.get("states") or {}).get("applied") or 0) for d in docs)

    tabs = "".join(
        f'<a class="{"on" if n == paths.name else ""}" href="/reviews?project={quote(n)}">'
        f'{html.escape(n)}</a>' for n in names)
    body = f"""<div class="tabs">{tabs}</div>
<div class="stats">
  <div class="stat"><b>{len(reviews)}</b><span>자동 리뷰</span></div>
  <div class="stat"><b>{len(plans)}</b><span>주간 플랜</span></div>
  <div class="stat"><b>{open_items}</b><span>미결 항목</span></div>
  <div class="stat"><b>{applied}</b><span>적용됨</span></div>
</div>
{candidate_note}
<div class="note">자동 리뷰는 <b>로컬 1차 초고 → Antigravity 2차 퇴고</b>를 거친 최종본이다.
번호를 누르면 상세가 열린다. <b>[복사]</b>는 <code>R12 검토해볼까?</code>를 복사하며,
.33 의 <code>ax-fix</code>는 새 리뷰를 만들지 않고 지금 main 기준의 적용 여부를 검토한다.</div>
<h2>자동 리뷰</h2>
<div class="wrap"><table class="fx">
<tr><th>번호</th><th>생성</th><th>작성자</th><th>커밋</th><th>파일</th><th>항목</th>
<th>high</th><th>mid</th><th>low</th><th>결정</th><th></th></tr>
{_review_rows(reviews, paths.name)}
</table></div>
<h2>주간 플랜</h2>
<div class="wrap"><table class="fx">
<tr><th>번호</th><th>주차</th><th>작성자</th><th>분류</th><th>심각도</th><th>플랜 상태</th>
<th>레드마인</th><th>결정</th><th></th></tr>
{_plan_rows(plans, paths.name)}
</table></div>"""
    return 200, _shell(body)


def page(project: str = "") -> tuple:
    st, text = render(project)
    return st, text.encode("utf-8")


# ── 상세 ─────────────────────────────────────────────────────────────────────

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_HEAD = re.compile(r"^(#{1,4})\s+(.*)$")


def _inline(text: str) -> str:
    s = html.escape(text or "")
    s = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", s)
    return _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", s)


def render_markdown(text: str, *, sub_heads: bool = False) -> str:
    """리뷰·플랜 MD 를 읽기 좋게 — 제목 · 표 · 목록 · 문단 · 인라인 코드만. [중요] 전부 이스케이프한다.

    `sub_heads=True` 는 리뷰 모듈 카드 안쪽 자리다 — `#` 개수와 무관하게 제목을 모두
    `<h4 class="sub">` 로 낮춰, 모듈 머리보다 작게 보이게 한다. 기본값은 종전 그대로다."""
    lines = (text or "").splitlines()
    out, para, i = [], [], 0
    if lines and lines[0].strip() == "---":
        end = next((k for k in range(1, len(lines)) if lines[k].strip() == "---"), None)
        if end:
            out.append('<pre class="fm">' + html.escape("\n".join(lines[1:end])) + "</pre>")
            i = end + 1

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                head, body = rows[0], rows[1:]
                t = ('<div class="wrap"><table class="fx"><tr>'
                     + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr>")
                t += "".join("<tr>" + "".join(f'<td class="wide">{_inline(c)}</td>' for c in r)
                             + "</tr>" for r in body)
                if not body:
                    t += f'<tr><td colspan="{len(head)}" class="empty">없음</td></tr>'
                out.append(t + "</table></div>")
            continue
        m = _HEAD.match(s)
        if m:
            flush()
            if sub_heads:
                out.append(f'<h4 class="sub">{_inline(m.group(2))}</h4>')
            else:
                lvl = min(len(m.group(1)) + 1, 5)
                out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
        elif s.startswith(("- ", "* ")):
            flush()
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append("<li>" + _inline(lines[i].strip()[2:]) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif not s:
            flush()
        else:
            para.append(s)
        i += 1
    flush()
    return "\n".join(out)


_MOD = re.compile(r"^###\s+(.*)$")


def _table_counts(lines: list) -> dict:
    """모듈 절 안의 컨벤션·안전성 표 데이터 행 수 — 머리 행·구분 행은 빼고 센다.

    표를 헤더 칸으로 알아본다(`review_gen` 계약: 컨벤션은 `위반 내용`, 안전성은 `위험도`).
    알아본 표만 키가 생긴다 — 둘 다 없으면 빈 dict 이고 머리에 개수를 싣지 않는다."""
    counts, kind, i = {}, None, 0
    while i < len(lines):
        s = lines[i].strip()
        if not s.startswith("|"):
            kind = None
            i += 1
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if kind is None:
            kind = ("conv" if "위반 내용" in cells else "safety" if "위험도" in cells else "other")
            if kind != "other":
                counts.setdefault(kind, 0)
        elif kind != "other" and not all(set(c) <= set("-: ") for c in cells):
            counts[kind] += 1
        i += 1
    return counts


def _mod_count_html(counts: dict) -> str:
    bits = [f"{label} <b>{counts[k]}</b>" for k, label in (("conv", "컨벤션"), ("safety", "안전성"))
            if k in counts]
    return f'<span class="mod-count">{" · ".join(bits)}</span>' if bits else ""


def render_review(text: str, serial: str = "") -> str:
    """자동 리뷰 원문 — `### <모듈>` 절마다 테두리 카드로 나눈다 (모듈 경계가 안 보이던 문제).

    첫 `###` 앞(제목·메타 목록)은 `render_markdown` 그대로다. 카드 안의 `## N.` 제목은
    `<h4 class="sub">` 로 낮춘다. `###` 가 하나도 없으면 로그 한 줄을 남기고 평문 렌더링으로 떨어진다."""
    lines = (text or "").splitlines()
    starts = [k for k, ln in enumerate(lines) if _MOD.match(ln.strip())]
    if not starts:
        _log(f"[fix] 웹 상세 — 리뷰 원문에 모듈 절(###) 없음 {serial}")
        return render_markdown(text)
    out = []
    pre = "\n".join(lines[:starts[0]])
    if pre.strip():
        out.append(render_markdown(pre))
    for n, k in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        name = _MOD.match(lines[k].strip()).group(1)
        inner = lines[k + 1:end]
        out.append('<section class="mod"><div class="mod-head">'
                   f'<span class="mod-name">{_inline(name)}</span>{_mod_count_html(_table_counts(inner))}'
                   f'</div>{render_markdown(chr(10).join(inner), sub_heads=True)}</section>')
    return "\n".join(out)


def _decision(st: dict) -> str:
    st = st or {}
    state = st.get("state") or "open"
    bits = []
    if st.get("by"):
        bits.append(html.escape(st["by"]))
    if st.get("at"):
        bits.append(html.escape(st["at"].replace("T", " ")))
    if st.get("branch"):
        bits.append(f'<span class="mono">{html.escape(st["branch"])}</span>')
    if st.get("commit"):
        bits.append(f'<span class="mono">{html.escape(st["commit"][:12])}</span>')
    extra = (" · ".join(bits))
    note = f"<br>{html.escape(st['note'])}" if st.get("note") else ""
    return (f'<span class="chip {state}">{STATE_LABEL.get(state, html.escape(state))}</span>'
            + (f'<div class="decision">{extra}{note}</div>' if (extra or note) else ""))


def _item_rows(items: list) -> str:
    if not items:
        return '<tr><td colspan="6" class="empty">수정 항목 없음 — 이 리뷰는 지적한 행이 없다</td></tr>'
    rows = []
    for it in items:
        sev = it.get("severity") or ""
        rows.append(
            f'<tr class="row"><td class="serial"><span class="mono">{html.escape(it["id"])}</span> '
            f'{_copy_btn(it["id"], "복사")}</td>'
            f'<td class="sev-{html.escape(sev)}">{html.escape(_SEV_LABEL.get(sev, sev))}</td>'
            f'<td class="mono">{html.escape(it.get("file") or "")}:{html.escape(str(it.get("line") or ""))}</td>'
            f'<td class="wide">{_inline(it.get("description") or "")}</td>'
            f'<td class="wide">{_inline(it.get("recommendation") or "") or "<span class=zero>—</span>"}</td>'
            f'<td>{_decision(it.get("status"))}</td></tr>')
    return "".join(rows)


def render_detail(serial: str, project: str = "", *, registry=None, get_doc=None) -> tuple:
    """(상태코드, HTML). `registry`/`get_doc` 주입은 테스트 자리."""
    try:
        reg, names, paths = _resolve(project, registry)
    except Exception as e:                                   # noqa: BLE001
        _log(f"[fix] 웹 상세 — 프로젝트 해석 실패: {type(e).__name__}: {e}")
        return 503, _shell('<div class="note">프로젝트를 해석하지 못했다 — 마스터 로그를 본다.</div>')
    if get_doc is None:
        from ..context_synth.fix_index import get_doc
    try:
        d = get_doc(paths.root, serial)
    except Exception as e:                                   # noqa: BLE001
        _log(f"[fix] [중요] 웹 상세 실패 {serial!r} ({paths.name}): {type(e).__name__}: {e}")
        return 500, _shell('<div class="note">문서를 읽지 못했다 — 마스터 로그를 본다.</div>')
    back = f'<a class="back" href="/reviews?project={quote(paths.name)}">← {html.escape(paths.name)} 목록</a>'
    if not d.get("ok"):
        return 404, _shell(f'{back}<div class="note">{html.escape(d.get("reason") or "없는 번호다")}</div>')

    s = d["serial"]
    kind = d.get("kind")
    phrase = ask_phrase(s)
    copybox = (f'<div class="copybox"><span class="phrase">{html.escape(phrase)}</span>'
               f'{_copy_btn(phrase, "요청 문구 복사")}{_copy_btn(s, "번호만 복사")}'
               '<span class="hint">.33 의 claude 에 붙여넣으면 <code>ax-fix</code> 가 받아, 지금 main '
               '기준으로 합당한지 분석하고 적용할지 묻는다.</span></div>')
    if kind == "review":
        heading = f"{s} — 자동 리뷰"
        meta = (f'<div class="meta">커밋 <b class="mono">{html.escape(d.get("commit") or "")}</b> · '
                f'<b>{html.escape(d.get("author") or "")}</b> · {html.escape(d.get("created") or "")} · '
                f'파일 {int(d.get("files") or 0)}개 · 프로젝트 {html.escape(paths.name)}</div>')
        sev = d.get("severity") or {}
        stats = (f'<div class="stats"><div class="stat"><b>{int(d.get("items") or 0)}</b><span>수정 항목</span></div>'
                 f'<div class="stat"><b class="sev-high">{int(sev.get("high") or 0)}</b><span>높음</span></div>'
                 f'<div class="stat"><b class="sev-mid">{int(sev.get("mid") or 0)}</b><span>중간</span></div>'
                 f'<div class="stat"><b>{int(sev.get("low") or 0)}</b><span>낮음</span></div>'
                 f'<div class="stat"><span>결정</span><div>{_chips(d.get("states"))}</div></div></div>')
        table = ('<h2>수정 항목</h2><div class="wrap"><table class="fx">'
                 '<tr><th>항목</th><th>심각도</th><th>파일:라인</th><th>지적</th><th>권장 수정</th>'
                 '<th>결정</th></tr>' + _item_rows(d.get("items_detail") or []) + "</table></div>")
    else:
        heading = f"{s} — 주간 플랜"
        rid = str(d.get("redmine_issue_id") or "")
        meta = (f'<div class="meta">주차 <b>{html.escape(d.get("week") or "")}</b> · '
                f'<b>{html.escape(d.get("author") or "")}</b> · 분류 {html.escape(d.get("category") or "")} · '
                f'심각도 {html.escape(d.get("severity_label") or "")} · 플랜 상태 '
                f'<span class="mono">{html.escape(d.get("plan_status") or "")}</span>'
                + (f' · 레드마인 #{html.escape(rid)}' if rid else "")
                + f' · 프로젝트 {html.escape(paths.name)}</div>')
        stats = ""
        srcs = "".join(f"<li class=mono>{html.escape(str(x))}</li>" for x in d.get("source_reviews") or [])
        table = ('<h2>대상과 결정</h2><div class="wrap"><table class="fx">'
                 '<tr><th>대상 파일</th><th>원본 리뷰</th><th>결정</th></tr>'
                 f'<tr><td class="wide mono">{html.escape(d.get("target_file") or "")}</td>'
                 f'<td class="wide"><ul style="margin:0;padding-left:1rem">{srcs}</ul></td>'
                 f'<td>{_decision(d.get("status"))}</td></tr></table></div>')
    missing = ('<div class="note">원본 파일이 없다 — 아카이브 보관 기간이 지났을 수 있다. '
               '번호와 결정 기록은 남아 있다.</div>') if d.get("missing") else ""
    body_md = d.get("body") or ""
    rendered = render_review(body_md, s) if kind == "review" else render_markdown(body_md)
    source = (f'<details class="src" open><summary>원문 전체</summary>'
              f'<div class="doc">{rendered}</div></details>'
              if d.get("body") else "")
    body = back + meta + copybox + missing + stats + table + source
    return 200, _shell(body, title=s, heading=heading,
                       sub="번호를 복사해 .33 에서 부른다 · 적용 여부는 사람이 정한다")


def page_detail(serial: str, project: str = "") -> tuple:
    st, text = render_detail(serial, project)
    return st, text.encode("utf-8")
