"""온톨로지 뷰어 + Context Server 웹 UI — [중요] **원전 그대로 복각** (사용자 지시 2026-08-13).

> *"그대로 복각하라고"* / *"웹UX 모두 다 날라갔잖아 뭐한거야?"*

원전(`~/AgentTest/mcp/context_search/`)에 **3,700줄**짜리 웹 UI 가 있었는데 내가 읽지 않고
229줄짜리 접이식 목록을 새로 만들었다. 그것이 이 파일이 존재하는 이유다.

## [중요] 방향 — 프론트엔드를 고치지 않고 **백엔드를 맞춘다**

    static/ontology/domain.html   1,056줄   그대로
    static/ontology/app.css         839줄   그대로
    static/ontology/tree_nav.js     159줄   그대로
    static/ontology/index.html      171줄   그대로
    static/ontology/task.html       129줄   그대로
    vendor/cytoscape.min.js                 그대로 ([중요] CDN 금지 — 저장소에 담는다)
    web_ui_original.py              664줄   그대로 (상태카드 + 탭 4개)

원전 프론트엔드가 부르는 엔드포인트 **21개**를 우리 데이터로 채운다. 응답 **모양**이 조금이라도
다르면 화면이 그대로 못 돌기 때문에, 로더는 원전 `ontology_route_loaders.py` 를 경로만 바꿔
이식했다(`loaders.py`).

## [중요] 우리 데이터가 원전과 같은 구조였다

    domains/<도메인>/domain.yaml + L{1,2,3}/{objects,actions,invariants}/*.yaml

우리 트윈이 원전 스냅샷을 이어받았으므로 레이아웃이 같다. 그래서 로더가 거의 그대로 돌았다.

## [주의] 원전과 **다를 수밖에 없는 것** — 여기 다 적는다

    ① VSCode 열기      원전은 서버가 파일을 소유해서 됐다. [중요] 우리 마스터는 파일을 소유하지
                       않는다(§2.1) → 버튼은 두되 **경로 복사**로 동작하고 그 이유를 화면에 적는다
    ② history          원전엔 `history/` 기록이 있었다. 우리에겐 없다 → 빈 목록(화면이 알아서 숨긴다)
    ③ 태스크 템플릿    원전 `task.yaml` 템플릿 CRUD. 우리에겐 없다 → 빈 목록
    ④ 인덱스 rebuild   원전은 서버가 색인을 들고 있었다. 우리는 **별도 프로세스**(`ax-indexer`)라
                       웹에서 부르지 않는다 → 명령을 안내한다([중요] 웹이 재색인을 트리거하지 않는다)
    ⑤ 도메인 생성/채팅 원전은 LLM 으로 도메인 패키지를 만들었다. [중요] 우리 저장소는 온톨로지 편집을
                       **대화형 + 편집이 곧 잠금**으로 못박고 자동 승급을 영구 비활성했다 →
                       **읽기 전용**이고, 화면이 그 이유를 말한다

[주의] ①~⑤ 는 **내 판단으로 뺀 것이 아니다** — 우리 아키텍처에서 물리적으로 다른 것과, 저장소가
이미 내려 둔 결정이다. 각각을 화면에 **적어서** 사람이 "왜 없지?" 를 묻지 않게 한다.
"""
# [DOC] import 는 이 모듈이 실제로 쓰는 이름만 둔다 (#815 pyflakes 정리).
from __future__ import annotations

import re
from pathlib import Path

from ..context_search import documents
from . import loaders

STATIC = Path(__file__).parent / "static" / "ontology"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")

# [중요] 원전과 다른 점을 화면이 스스로 말하게 하는 문구 (위 § ①~⑤)
NOTES = {
    "vscode": "[중요] 마스터는 파일을 소유하지 않는다(§2.1) — 경로를 복사해 작업 머신에서 연다",
    # [주의] 이 문구는 **기록이 0건일 때만** 나간다 (`#307`) — 종전에는 하드코딩된 빈 응답에
    #    항상 붙어 있어서, 기록이 생긴 뒤에도 화면이 「없다」고 말했다
    "history": "이 트윈에 아직 작업 기록(history)이 없다",
    "tasks": "태스크 템플릿은 이 저장소에 아직 없다",
    "rebuild": ("[중요] 재색인은 웹에서 하지 않는다 — 색인기는 별도 프로세스다(`ax-indexer`). "
                "마스터에서: `python -m master.context_search.rebuild`"),
    "mutation": ("[중요] 읽기 전용이다. 온톨로지 편집은 **대화형 + 편집이 곧 잠금**으로 정해져 있고 "
                 "자동 승급은 영구 비활성이다 — 웹 버튼이 트윈을 쓰지 않는다. "
                 "편집은 `python -m master.ontology` 와 MCP 도구로 한다"),
}


# ── 파일 서빙 ────────────────────────────────────────────────────────────────────

def read_static(name: str) -> tuple:
    """`(바이트, content-type)`. [중요] 이름만 받는다 — 경로를 조립하지 않는다."""
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    if not parts or not all(_SAFE.match(p) for p in parts):
        return None, b""
    p = STATIC.joinpath(*parts)
    try:
        p = p.resolve()
        p.relative_to(STATIC.resolve())          # [중요] 순회 이중 방어
    except (ValueError, OSError):
        return None, b""
    if not p.is_file():
        return None, b""
    ctype = {".css": b"text/css; charset=utf-8",
             ".js": b"application/javascript; charset=utf-8",
             ".html": b"text/html; charset=utf-8"}.get(p.suffix.lower(),
                                                       b"application/octet-stream")
    return p.read_bytes(), ctype


def page(name: str) -> bytes:
    """`domain.html` 등 원전 페이지를 그대로 낸다."""
    body, _ = read_static(name)
    return body or b"<p>page missing</p>"


# 🔴 [중요] 좌측 목록은 **모든 화면에 한 벌** (사용자 결정 2026-10-04, 「a-1」) — 정본은
#    `nav.py` 다. 종전에는 화면마다 링크 버튼을 따로 끼웠고(`온보딩 →`·`클러스터 상태 →`·
#    `리뷰·플랜 →`), 새 화면(`/usage`)이 생길 때마다 **원전 화면에만 입구가 빠졌다.**
#
#    [주의] 원전 파일(`web_ui_original.py`·`static/*.html`)은 **바이트 그대로 둔다** (2026-08-13
#    규약). 목록은 **서빙 시점에 감싸서** 넣는다 — 원전과의 diff 는 이 함수들에만 남는다.
#    원전 바이트에 들어 있는 상호 링크(`Ontology Viewer →`·`← Context Search`·`← 도메인 목록`)는
#    원전의 것이라 그대로 둔다.
#
#    원전 팔레트에는 `--line`·`--card`·`--fg` 가 없다 → **목록 안에서만** 정의한다.
#    값은 `status._CSS` 의 `:root` 와 같다(같은 다크 팔레트 — 화면마다 색이 달라 보이지 않게).
_SIDE_VARS = (".side{--line:#30363d;--card:#161b22;--fg:#e6edf3;--dim:#8b949e;"
              "--accent:#58a6ff}"
              # 원전 `app.css` 의 `a:hover{text-decoration:underline}` 가 목록까지 번진다
              ".side a:hover{text-decoration:none}")
# 컨텍스트 검색(`/`) — 원전 `.container` 가 자기 여백(24px)을 들고 있으므로 간격은 그것에 맡긴다.
_CONTEXT_SHELL_CSS = ".ax-shell{gap:0;padding:16px 16px 0}"
# 🔴 온톨로지 — `.board-shell`·`.layout` 이 `height:100vh` 의 전면 레이아웃이다. 바깥 여백을
#    두면 그만큼 세로 스크롤이 생기므로 **여백 0** 으로 붙이고, 목록 쪽에만 띄움을 준다.
_ONTOLOGY_SHELL_CSS = (".ax-shell{gap:0;padding:0}"
                       ".ax-shell>.side{margin:12px;top:12px}")


def wrap_side_nav(text: str, current: str, extra_css: str = "") -> str:
    """완성된 HTML 문서의 본문을 `<div class="shell">목록<main>…</main></div>` 로 감싼다.

    [주의] 표지(`</head>`·`<body>`·`</body>`)를 못 찾으면 앞뒤에 붙인다 — 조용히 빠뜨리지 않는다.
    """
    from .nav import SIDE_CSS, nav_html
    style = "<style>" + _SIDE_VARS + SIDE_CSS + extra_css + "</style>"
    end_head = re.search(r"</head>", text, re.IGNORECASE)
    i = end_head.start() if end_head else -1
    text = text[:i] + style + text[i:] if i >= 0 else style + text
    head = f'<div class="shell ax-shell">{nav_html(current)}<main>'
    m = re.search(r"<body[^>]*>", text, re.IGNORECASE)
    text = text[:m.end()] + head + text[m.end():] if m else head + text
    j = text.lower().rfind("</body>")
    tail = "</main></div>"
    return text[:j] + tail + text[j:] if j >= 0 else text + tail


# [중요] `#812` (2026-10-11) — 게시판 쓰기·채팅을 **코드째 걷었다**(`board.py`·`app.py` 405).
#    원전 화면의 쓰기 버튼은 그대로 두면 **조용히 성공처럼 보인다**(Apply 는 브라우저 textarea
#    만 바꾸고, Activate 는 실패 분기가 없고, Clear 는 응답을 안 보고 화면을 비운다). 원전 바이트는
#    그대로 두고(`OriginalsUntouchedTests`) **서빙 시점에 CSS 로 숨긴다**. JS 가 인라인
#    `style.display` 를 바꾸므로 `!important` 로 이긴다. 채팅은 없어졌으므로 상세의 채팅 칸은
#    **통째로** 숨긴다. 읽기(도메인 목록·문서·소스 문서·검색·다른 탭)는 숨기지 않는다.
RETIRED_WRITE_SELECTORS = (
    'button[onclick="toggleNewDomain()"]',   # + New Domain
    "#newDomainForm",                        # 생성 폼(Create → createDomain)
    "#domainDetail .delete-btn",             # Delete → deleteDomain
    "#domainDetail .domain-chat-panel",      # 채팅 칸 전체 — 기록·입력·Send/Apply/Activate/Clear
)
RETIRED_WRITE_NOTICE = "도메인 문서 편집·채팅은 2026-10-11 제거됨 (#812)"
_RETIRED_WRITE_CSS = (
    ",".join(RETIRED_WRITE_SELECTORS) + "{display:none!important}"
    # 상세는 문서 칸 하나만 남으므로 두 칸 격자를 한 칸으로 편다
    + "#domainDetail .domain-layout{grid-template-columns:1fr!important}"
    + f'#domainListView::before{{content:"{RETIRED_WRITE_NOTICE}";display:block;'
    "color:#8b949e;font-size:.85rem;margin:0 0 8px}"
)


def context_server_html() -> bytes:
    """원전 `web_ui.py` 의 HTML. [중요] 파일은 손대지 않고 **좌측 목록으로 감싼다**."""
    from .web_ui_original import WEB_UI_HTML
    # 실제 입력값을 trim된 검색 질의와 별도로 보존한다. 원전 자산 파일은 변경하지 않는다.
    body = WEB_UI_HTML.replace(
        "const body = { query, n_results: n };",
        "const body = { query, n_results: n, task_type: 'user_search', caller: 'web_ui', "
        "user_request: document.getElementById('searchQuery').value, "
        "user_request_source: 'captured_web_input' };")
    return wrap_side_nav(body, "/",
                         _CONTEXT_SHELL_CSS + _RETIRED_WRITE_CSS).encode("utf-8")


def inject_cluster_link(body: bytes) -> bytes:
    """`/ontology` 페이지들(목록·도메인 상세·태스크)을 좌측 목록으로 감싼다.

    [주의] 이름은 옛 동작(링크 주입)의 것이다 — 호출자(`app.py`)를 바꾸지 않으려고 남겼다.
    세 화면 모두 목록에서는 `/ontology` 한 항목이 켜진다.
    """
    text = body.decode("utf-8", "replace")
    return wrap_side_nav(text, "/ontology", _ONTOLOGY_SHELL_CSS).encode("utf-8")


def cluster_page(paths) -> tuple:
    """클러스터 상태 화면. [중요] **`/cluster` 한 자리**로 옮겼다 — `/view` 는 없앴다.

    [주의] 스냅샷이라 낡을 수 있다 — 나이를 배너로 박는 판단은 그대로 유지한다.
    """
    from ..viewer import STALE_SEC, _age, inject, stale_banner
    p = paths.root / "cluster.html"
    if not p.is_file():
        from ..status import _CSS
        miss = ("<!doctype html><html lang=ko><head><meta charset=utf-8>"
                "<title>AX 클러스터 상태</title><style>" + _CSS + "</style></head><body>"
                "<p>[중요] 클러스터 상태 화면이 아직 만들어지지 않았다.</p>"
                "<p>마스터에서: <code>python -m master.status html</code></p>"
                "</body></html>")
        return 503, wrap_side_nav(miss, "/cluster").encode("utf-8")
    body = p.read_text(encoding="utf-8", errors="replace")
    # [주의] 좌측 목록도 **서빙 시점에 감싼다** (맨 끝 `wrap_side_nav`).
    #    [중요] `cluster.html` 은 파일로도 열리는 자립형 HTML 이라(`status.write`·`deliver`)
    #    절대 경로 링크를 본문에 박으면 `file://` 로 열었을 때 죽는다 — `test_status` 의
    #    *"외부 자원 0"* 계약이 그것을 잡는다. 그래서 `status.render` 가 아니라 여기서 넣는다.
    sec, _ = _age(p)
    if sec is not None and sec > STALE_SEC:
        body = inject(body, stale_banner(sec, "python -m master.status html"))

    # [중요] 실시간 작업 층 (#216) — **서빙 순간** 큐(8101)·브로커(8102)를 로컬 HTTP 로 읽어
    #    스냅샷의 LIVE_MARK 자리에 꽂는다. SSH 는 타지 않는다(120초 가드의 취지 그대로) —
    #    신선해지는 것은 마스터 자신의 상태뿐이고, 하드웨어 층은 여전히 스냅샷이다.
    #    토큰은 서버 측에서만 쓴다 — 브라우저에 절대 내려보내지 않는다.
    from .. import status as _status
    from datetime import datetime as _dt
    got = _status.fetch_live()
    live = _status.live_section(got.get("queue"), got.get("tasks"), got.get("endpoints"),
                                error=got.get("error", ""),
                                at=_dt.now().strftime("%H:%M:%S"),
                                recent=got.get("recent"),
                                activity=_status.read_activity(paths.root))
    from .orchestration import section as orchestration_section
    live = orchestration_section() + live
    # work 중심 층 (#222) — 화면의 주어를 등록 단위로 올린다. 실시간 층 **아래**에 둔다:
    #    「지금 무엇이 도는가」가 먼저고, 「내 작업이 어디까지 왔나」가 그 다음이다.
    #    실시간 층을 못 읽었으면(토큰·큐 장애) work 도 재료가 없으므로 그리지 않는다.
    if not got.get("error"):
        # 파견 기록을 함께 넘긴다 (`#323`) — [중요] **로컬 스풀만 읽는다. SSH 0.**
        #    종전에는 워커의 claimer 로그를 5분 주기 SSH 로 걷어 왔는데, 그 상주가 `#320`
        #    으로 철거돼 **결과가 정해진 SSH** 가 됐다. 재료는 파견이 이미 스풀에 쓰고 있다.
        stored = {}
        try:
            from ..work import logs as _logs
            ids = [str(t.get("task_id") or "") for t in (got.get("tasks") or [])
                   if isinstance(t, dict)]
            stored = _logs.read_runs(paths, ids)
        except Exception:                                    # noqa: BLE001
            stored = {}                  # 기록은 부가 정보 — 없다고 화면을 죽이지 않는다
        live += _status.work_section(got.get("works"), got.get("tasks"), logs=stored)
    # 자동 갱신 (사용자: "매번 F5 누르기 불편") — 탭이 보일 때만 15초마다 리로드.
    #    페이지 전체가 가벼운 정적 서빙이라 부분 갱신 API 를 새로 여는 것보다 싸고,
    #    토큰 없는 공개 API 를 만들지 않아도 된다.
    live += ('<script>setInterval(function(){if(document.visibilityState==="visible")'
             'location.reload();},15000);</script>'
             '<div class="sub" style="margin:.2rem 0 0">15초마다 자동 갱신 '
             '(탭이 보일 때만) — 실시간 층 기준. 하드웨어 스냅샷은 별도 주기</div>')
    if _status.LIVE_MARK in body:
        body = body.replace(_status.LIVE_MARK, live, 1)
    else:
        body = inject(body, live)      # 옛 스냅샷(마커 없음) 폴백
    # 🔴 좌측 목록 (사용자 결정 2026-10-04) — 종전의 상단 링크 줄(`← Context Search ·
    #    Ontology Viewer`)과 부제 줄의 `온보딩 →`·`리뷰·플랜 →` 은 목록이 대신한다.
    #    [주의] **맨 마지막에** 감싼다 — 위의 `inject` 가 `<body>` 바로 뒤를 표지로 쓰므로,
    #    먼저 감싸면 배너가 목록 바깥으로 나간다.
    body = wrap_side_nav(body, "/cluster")
    return 200, body.encode("utf-8")


# ── API — 온톨로지 (읽기 전용) ───────────────────────────────────────────────────
#
# [주의] 2026-08-13: `cluster_page` 를 다시 쓰다가 이 아래를 **잘라먹어** `/api/v1/tags` 가 500 이
#    됐다. 파일 꼬리를 교체할 때는 남는 부분을 먼저 확인할 것 — 실측으로 물린 자리다.

def api_domains(root: Path) -> dict:
    return {"domains": loaders.list_domains(root)}


def api_domain(root: Path, name: str):
    got = loaders.load_domain_package(root, name)
    if got is None:
        return None
    got.update(loaders.domain_link_info(root, name))
    return got


def api_object(root: Path, domain: str, cls: str):
    return loaders.load_object(root, domain, cls)


def api_action(root: Path, domain: str, action: str):
    return loaders.load_action(root, domain, action)


def api_history(paths, cls: str, *, limit: int = 3) -> dict:
    """클래스 → 최근 작업 narrative (`#307`). 프론트 계약: `records[].{source,date,
    decision_type,summary_head,path}`.

    [중요] **종전에는 하드코딩된 빈 목록이었다** — 사유가 *"우리 트윈에는 항목별 history 기록이
    아직 없다"* 였고 2026-08-24 부터 그 문장이 **거짓**이 됐다. `#295`(색인 실패를 정상으로
    보여준 자리)와 같은 부류이고 방향만 반대다: 있는 것을 없다고 말했다.

    🔴 [중요] **이 포트는 무인증 공개다** (실측 2026-08-24: 토큰 없이 `/api/v1/*` 200 — 루프백과
    LAN 주소 둘 다). 그래서 여기서 내보내는 것을 **의도적으로 줄였다**:

        내보낸다      date · decision_type · source · 파일명 · 제목에서 뽑은 한 줄
        안 내보낸다   `user_quote`(사람의 발화 원문) · 본문 · 절대경로

    사유: 저장소가 같은 판단을 이미 한 자리가 있다 — 레드마인 **읽기**를 8103 에 두지 않고
    8101 로 보낸 것(*"일감 본문·검수 이력이 LAN 아무에게나 열린다"*). 전문 조회는 토큰이 걸린
    8101 의 `find_history`(`#306`)가 맡는다. **화면은 돌고, 사람의 말은 안 나간다.**
    [주의] 이 절충은 판정이고 뒤집을 수 있다 — 뒤집으려면 이 주석과 함께 고칠 것.
    """
    from ..context_synth import history_harvest as HH
    try:
        cdir, gdir = HH.project_history_dirs(paths)
        recs = HH.walk_histories(cdir, gdir)
    except Exception as e:                                   # noqa: BLE001
        # [중요] **빈 목록으로 위장하지 않는다** (`#285` 축) — 못 읽은 것과 없는 것은 다르다
        return {"class": cls, "source": "all", "count": 0, "records": [],
                "error": f"history 를 읽지 못했다 — {type(e).__name__}: {e}"}
    matched = HH.filter_for_classes(recs, {cls}, limit=max(1, int(limit)))
    out = {"class": cls, "source": "all", "count": len(matched),
           "records": [{"source": r.source, "date": r.date,
                        "decision_type": r.decision_type,
                        # [주의] `summary` 는 user_quote 를 담을 수 있다 — 제목을 쓴다
                        "summary_head": (r.title or "")[:160],
                        "path": Path(r.path).name} for r in matched]}
    if not matched:
        # [중요] 사유는 **없을 때만** 붙인다 — 있는데도 「없다」고 적으면 화면이 거짓말을 한다
        out["note"] = (NOTES["history"] if not recs else
                       f"이 트윈에 기록 {len(recs)}건이 있지만 `{cls}` 를 다룬 것은 없다")
    return out


def api_tasks(paths=None) -> dict:
    """등록된 태스크 템플릿 목록. [완료] **더 이상 빈 목록이 아니다** (소 2.2.2 · `#140`).

    [중요] **검색이 아니라 디렉토리 스캔이다** — 태스크 템플릿은 도메인 검색 채널에 인덱싱하지
    않는다(채널 분리 불변식). 섞으면 도메인 문서와 경합해 한쪽이 묻힌다(원전, 사용자 지적).
    """
    if paths is None:
        return {"status": "ok", "count": 0, "templates": [], "note": NOTES["tasks"]}
    from ..ontology import tasks as _t
    got = _t.listing(paths.ontology)
    if not got.get("count"):
        got["note"] = NOTES["tasks"]
    return got


def api_task(paths, task_type: str):
    """템플릿 하나. 없으면 `None` (호출자가 404 로 만든다).

    [주의] **404 는 두 가지다** — *"라우트 미등록"* 과 *"자원 없음"*. 여기서 `None` 은 뒤쪽이고,
    본문에 그 사실을 적는다(리포트 14 §의 오탐 두 번이 이 구분에서 나왔다).
    """
    from ..ontology import tasks as _t
    got = _t.get(paths.ontology, task_type)
    return None if got.get("status") != "ok" else got


# ── API — Context Server 탭 ──────────────────────────────────────────────────────

def _doc_count(paths) -> int:
    try:
        return len(list(paths.context.glob("**/*.md"))) if paths.context.is_dir() else 0
    except OSError:
        return 0


def api_health(root: Path, paths) -> dict:
    from ..graph import db as gdb
    return {"status": "ok", "project_root": str(root), "updating": False,
            "indexed_documents": _doc_count(paths), "graph": gdb.exists(paths)}


def api_index_status(paths) -> dict:
    """색인 상태. [중요] **필드명은 원전 프론트엔드가 읽는 그대로다** — `indexed_documents`.

    [주의] 실측 2026-08-13: 내가 `documents` 로 냈더니 화면이 **DOCUMENTS 0** 을 보였다(문서는
    1,055개 있었다). 프론트엔드를 그대로 쓰는 복각이므로 **모양을 맞추는 쪽이 우리다.**

    ## [중요] 필드 다섯이 빠져 있었다 — 이식 드리프트 복구 (`#295`)

    원전 `search_routes.py:409` 는 `status`·`context_md_files`·`bm25_documents`·
    `needs_rebuild`·`vector_available`·`bm25_available` 을 함께 낸다. 그리고 **`indexed_documents`
    는 벡터 색인의 실측**(`_index.live.count()`)이지 파일 개수가 아니다.

    [중요] 우리 종전 구현은 `_doc_count`(=`context/**/*.md` **파일 수**)를 `indexed_documents`
    로 냈다. 그러면 **색인이 실패해도 화면은 정상으로 보인다** — 파일은 그대로 있으니까.
    원전이 `needs_rebuild = count != md_count` 를 둔 이유가 정확히 그것이다(원전 주석:
    *"과거 len(tag_cache) 는 draft·빈 문서를 안 걸러 벡터보다 많아 needs_rebuild 가 상시
    true 였음"* — 그쪽도 같은 자리에서 한 번 틀렸다).

    [주의] 못 읽는 항목은 **`None`** 으로 두고 `available` 을 False 로 낸다 — 0 으로 두면
    「비었다」와 「못 읽었다」가 섞인다(이 세션에서 반복 확인된 부류).
    """
    # [중요] **분모는 「색인 가능한」 문서다** — 파일 개수가 아니다. 원전이 같은 자리에서 한 번
    #    틀렸고 주석으로 남겼다(*"과거 len(tag_cache) 는 draft·빈 문서를 안 걸러 벡터보다 많아
    #    needs_rebuild 가 상시 true 였음"*). 우리 정본은 `documents.iter_documents` 다 — 색인이
    #    실제로 넣는 그 목록이라, 그것으로 세지 않으면 판정이 영구히 「재색인 필요」가 된다.
    fallback = ""
    try:
        from ..context_search.documents import iter_documents
        md = sum(1 for _ in iter_documents(paths.context))
    except Exception as e:                                   # noqa: BLE001
        # [중요] 폴백을 쓰면 **판정이 헐거워진다** — 파일 개수로 세므로 `needs_rebuild` 가
        #    과대 판정된다. 주석에 그렇게 적어 두고 **말하지 않으면** 화면을 보는 사람이
        #    「왜 재색인 필요라고 나오나」를 못 되짚는다 (`#296`).
        md = _doc_count(paths)
        fallback = f"색인 대상 목록을 못 읽어 파일 개수로 셌다: {type(e).__name__}"
    vec = bm25 = None
    try:
        from ..context_search.index import open_index
        vec = int(open_index(paths.name).count())
    except Exception:                                        # noqa: BLE001
        pass
    try:
        from ..context_search.bm25 import Bm25Index
        bm25 = int(Bm25Index(paths).count())
    except Exception:                                        # noqa: BLE001
        pass
    out = {
        # [중요] 화면이 읽는 이름 — 벡터 색인 실측이다. 못 읽으면 0 이 아니라 그 사실을
        #    `vector_available: False` 로 말한다.
        "indexed_documents": vec if vec is not None else 0,
        "context_md_files": md,
        "bm25_documents": bm25 if bm25 is not None else 0,
        # [중요] **불일치를 드러내는 것이 이 API 의 값이다.** 못 읽었으면 「필요 없다」고 하지
        #    않는다 — 모르는 것을 괜찮다고 말하지 않는다.
        "needs_rebuild": (vec != md) if vec is not None else True,
        "vector_available": vec is not None,
        "bm25_available": bool(bm25),
        "status": ("정상" if (vec is not None and vec == md)
                   else "재색인 필요" if vec is not None else "색인을 읽지 못했다"),
        "generation": "",
        "updating": False,
    }
    if fallback:
        out["note"] = fallback
    # [중요] **없는 함수를 부르고 있었다** (`#301` 검증에서 잡혔다). 종전 코드는
    #    `from ..context_search.generation import current` 였고 그 이름은 **존재하지 않는다** —
    #    `except: pass` 가 그것을 가려 `generation` 이 **영구히 빈 문자열**이었다. 사유를
    #    남기게 고친 직후 `note: "세대를 못 읽었다: ImportError"` 로 드러났다.
    #    실제 API 는 `generation.read(root)` 다(`a`/`b` 세대 포인터 · PLAN §5.4.6).
    try:
        from ..context_search import generation as _gen
        out["generation"] = _gen.read(paths.root) or ""
    except Exception as e:                                   # noqa: BLE001
        out["note"] = ((out.get("note", "") + " · ") if out.get("note") else "") + \
            f"세대를 못 읽었다: {type(e).__name__}: {e}"
    return out


def api_documents(paths, limit: int = 100) -> dict:
    """**빈 질의 = 문서 목록** (`#378`). 원전 화면 `loadDocs` 가 그 계약으로 서 있다.

    원전 서버는 이것을 *공백 임베딩의 최근접 이웃*으로 흉내낸다(`search_routes.py:66`,
    Chroma 에 `query_texts=[" "]`). 우리 검색은 융합(벡터+BM25)이라 공백이면 **0건**이 나온다 —
    같은 계약을 **결정적으로** 세운다. 화면이 읽는 필드는 넷뿐이다(`file`·`tags`·`category`·
    `content_preview`), 그래서 순위가 아니라 **목록**이면 충분하다.

    [중요] 파서는 `api_tags` 와 **같은 것**을 쓴다 — `documents.parse_frontmatter`.
    화면과 색인이 다른 태그를 보면 안 된다.
    [주의] 스코프는 호출자가 준 `paths` 다 — 웹 UI 는 **매 요청 마운트를 다시 푼다**.
    """
    ctx = paths.context
    out = []
    if ctx.is_dir():
        for md in sorted(ctx.rglob("*.md")):
            rel = md.relative_to(ctx).as_posix()
            if documents.is_excluded(rel):
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta = documents.parse_frontmatter(text) or {}
            out.append({
                "file": rel,
                "similarity": None,          # 목록이다 — 순위가 아니다
                "category": str(meta.get("category") or ""),
                "tags": [str(t) for t in (meta.get("tags") or [])],
                "related_classes": meta.get("related_classes") or {},
                "content_preview": text[:500],
            })
            if len(out) >= max(1, int(limit)):
                break
    return {"query": "", "count": len(out), "results": out,
            "note": "빈 질의 — 문서 목록을 낸다 (`#378`)"}


def api_tags(root: Path, paths=None) -> dict:
    """[중요] 태그 클라우드.

    [주의] **모양이 계약이다**: 원전 `renderTagCloud` 는 `tags.tags` 를 **`{태그: 개수}` 객체**로
    받고 `Object.entries(...)` 로 돈다. 배열로 주면 화면이 빈 채로 뜬다(실측). 배지는 `total_tags`.

    ## [중요] 출처의 정본은 **컨텍스트 문서**다 — 이식 드리프트 복구 (`#288`)

    원전 `search_routes.py:400 api_list_tags` 는 `_index.tag_cache` 를 돈다. 그 캐시는
    `double_buffered_index._build_tag_cache` 가 **`context/` 의 모든 MD 프론트매터**에서
    만든 것이다(`_domains/*.md` 만 제외). 우리 이식은 그 축을 빼먹고 **도메인만** 셌다.

    실측 2026-08-23: NS 가 컨텍스트 문서 42건에 한글 태그를 갖고 있는데 도메인이 0개라
    화면이 **완전히 비어 있었다.** ModularStage 는 도메인이 많아 채워져 보였으므로 이
    차이가 드러나지 않았다 — **N=1 이 설계를 검증하지 않는다**(`#231` 과 같은 부류).

    [주의] 도메인 manifest·`aliases` 집계는 **뺀 것이 아니라 더한 것**이다. 우리 확장이고
    (시소러스의 한국어 말) 지우면 ModularStage 화면이 후퇴한다. 원전 축을 정본으로 두고
    우리 축을 합친다.
    """
    counts: dict = {}

    # ① 원전 정본 — 컨텍스트 문서의 프론트매터 태그
    # [중요] 파서는 **재사용한다** — `documents.parse_frontmatter` 가 색인이 쓰는 그 파서다.
    #    여기서 새로 정규식을 쓰면 화면과 색인이 다른 태그를 보게 된다.
    ctx = (paths.context if paths is not None else root / "context")
    if ctx.is_dir():
        for md in sorted(ctx.rglob("*.md")):
            rel = md.relative_to(ctx).as_posix()
            if documents.is_excluded(rel):
                continue
            try:
                meta = documents.parse_frontmatter(md.read_text(encoding="utf-8",
                                                               errors="replace"))
            except OSError:
                continue
            for t in (meta.get("tags") or []):
                counts[str(t)] = counts.get(str(t), 0) + 1

    # ② 우리 확장 — 도메인 manifest 의 `tags` + 오브젝트 `aliases`
    for d in loaders.list_domains(root):
        for t in d.get("tags") or []:
            counts[str(t)] = counts.get(str(t), 0) + 1
    for pkg in sorted((root / "ontology" / "domains").glob("*")):
        if not pkg.is_dir():
            continue
        for y in loaders._glob_object_yamls(pkg):
            data = loaders.parse_domain_yaml(y) or {}
            for a in (data.get("aliases") or []):
                counts[str(a)] = counts.get(str(a), 0) + 1

    # 원전과 같이 **많이 쓰인 순**으로 준다 (`sorted_tags` — 화면이 크기를 그 순서로 준다)
    ordered = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return {"tags": ordered, "total_tags": len(ordered)}


def _tag_list(v) -> list:
    """태그를 **배열**로 (`#380`). 화면이 `(r.tags || []).map(...)` 을 부른다.

    🔴 [중요] **벡터 저장소 메타는 태그를 콤마 문자열로 갖는다** — 리스트를 못 넣기 때문이다.
    원전은 내보낼 때 쪼갠다(`search_routes.py:91` `[t for t in meta.get("tags","").split(",") if t]`).
    우리는 그 한 줄을 안 옮겨 **원문 문자열을 그대로 흘렸고**, 화면에서 `.map is not a function`
    으로 죽었다(사용자 실측 2026-09-06: 문서를 클릭하면 *"Search failed"*).
    [주의] 이미 리스트인 경로(`api_documents` 는 프론트매터에서 바로 읽는다)도 있으므로 둘 다 받는다.
    """
    if isinstance(v, (list, tuple)):
        return [str(t) for t in v if str(t).strip()]
    return [t.strip() for t in str(v or "").split(",") if t.strip()]


def _related_classes(paths, file_id: str):
    """컨텍스트 문서 프론트매터의 `related_classes` (`#381`).

    [주의] **색인 메타에는 없다** — 실측(2026-09-06) 메타 키는 `category·content_hash·file_id·
    has_body·path·tags` 뿐이다. 원전은 Chroma 메타에 JSON 으로 넣어 뒀지만 우리 색인은 그러지
    않으므로 **디스크의 프론트매터**에서 읽는다(반환 행 ≤50개라 비싸지 않다).
    """
    try:
        text = (paths.context / file_id).read_text(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        return {}                       # 보강이 검색을 죽이지 않는다 (위 `_included_by` 와 같은 이유)
    return (documents.parse_frontmatter(text) or {}).get("related_classes") or {}


def _included_by(paths, file_id: str, cap: int = 5) -> list:
    """이 문서가 서술하는 소스를 `#include` 하는 쪽 (`#381`).

    원전은 `search_routes.py:312` 에서 `dependency_graph.db` 를 직접 열어 역방향 맵을 만든다.
    [중요] **우리는 그 판정을 다시 적지 않는다** — `graph.dependency.dependents` 가 같은 일을
    하고(basename 매칭까지 같다), 판정이 두 벌이면 언젠가 한쪽만 고쳐진다.
    [주의] 검색 행은 **문서**(`…/Foo.md`)이고 그래프는 **소스**(`…/Foo.h|.cpp`)다 — stem 으로 잇는다.
    """
    # [중요] **보강이 검색을 죽이지 않는다** — 이것은 화면의 한 줄이고, 없으면 그 줄만 안 뜬다.
    #    (테스트가 잡았다: 그래프 경로가 없는 `paths` 에서 `AttributeError` 로 결과 전체가 죽었다.)
    try:
        from ..graph import dependency as dep
        if not dep.exists(paths):
            return []                   # 그래프가 없으면 빈 배열 — 화면은 그 줄을 안 그린다
        stem = Path(file_id).stem
        out: list = []
        for ext in (".h", ".cpp"):
            for f in dep.dependents(paths, stem + ext, depth=1):
                if f not in out and Path(f).stem != stem:
                    out.append(f)
        return sorted(out)[:cap]
    except Exception:                                        # noqa: BLE001
        return []


def _search_row(paths, h) -> dict:
    """검색 결과 행 — **원전 스키마** (`#381`).

    [중요] `similarity` 는 **지어내지 않는다.** `Hit.similarity` 가 진짜 벡터 유사도이고
    BM25 단독이면 `0.0` 이다 — 그때는 `None` 으로 낸다. 화면은 `similarity != null && > 0` 일
    때만 퍼센트를 쓰고 아니면 `source` 를 보이므로(`vector+bm25` 등) 그 폴백이 정답이다.
    [주의] 우리 `rrf_score` 는 융합 순위 점수라 **유사도가 아니다** — 그것을 `similarity` 로
    내보내면 화면이 「1.6%」를 보여 준다. 별도 키(`score`)로 남긴다.
    [주의] `co_changed` 는 **원전 서버에도 없다**(화면만 읽는다) — 만들지 않는다.
    """
    meta = h.meta or {}
    return {
        "file": h.file_id,
        "similarity": round(h.similarity, 4) if h.similarity else None,
        "category": meta.get("category", ""),
        "tags": _tag_list(meta.get("tags")),
        "related_classes": _related_classes(paths, h.file_id),
        "content_hash": meta.get("content_hash", ""),
        "content_preview": h.excerpt,
        "included_by": _included_by(paths, h.file_id),
        # 우리 확장 — 융합 순위와 채널 (원전에도 `source`·`bm25_score` 가 있다)
        "source": h.source,
        "score": round(h.rrf_score, 4),
        "bm25_score": round(h.bm25_score, 4) if h.bm25_score else 0.0,
        "body": h.excerpt,               # [주의] 하위호환 — 우리 소비자가 이 이름을 쓴다
    }


def api_search(paths, query: str, limit: int = 5, *, trace=None) -> dict:
    """융합 검색(벡터+BM25). [중요] 우리 `ContextSearch` 를 그대로 쓴다.

    [중요] **여기도 기록한다** (소 3.4.5). 원전은 MCP(`search_tools.py`)와 **HTTP
    (`search_routes.py`) 양쪽**에서 `_log_search` 를 부른다 — 한쪽만 심으면 로그가 표면에
    따라 편향되고, 채널 튜닝의 근거가 조용히 반쪽이 된다. [주의] 실제로 처음엔 MCP 만 심었고
    재기동을 검증하려다 이 자리를 발견했다.

    [주의] `caller="web_ui"` 는 **원전 vocabulary 에 없는 값**이다. 원전 HTTP 라우트는 caller 를
    **클라이언트가 신고**하는데(`req.caller`, 기본 None) 우리 webui 는 in-process 호출이라
    신고할 주체가 없다. 표면을 못 가르면 이 필드의 존재 의미가 없으므로 값을 준다.
    """
    from ..context_search import search_log
    context = dict(trace or {})
    context.setdefault("caller", "web_ui")
    context.setdefault("task_type", "unclassified")
    with search_log.search_context(**context):
        return _api_search(paths, query, limit)


def _api_search(paths, query: str, limit: int) -> dict:
    from ..context_search import search_log
    searcher = None
    try:
        from ..context_search import ContextSearch
        searcher = ContextSearch(paths)
        hits = searcher.search(query, limit=max(1, min(50, limit)))
    except Exception as e:                                   # noqa: BLE001
        logged = (getattr(searcher, "last_log_result", None) if searcher is not None else None)
        if logged is None:
            logged = search_log.log_search(paths, query=query, error=f"{type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}", "results": [],
                "logged": logged.get("ok", False), "search_id": logged.get("search_id"),
                "request_id": logged.get("request_id")}
    logged = getattr(searcher, "last_log_result", {})
    return {"query": query, "count": len(hits),
            "results": [_search_row(paths, h) for h in hits],
            "logged": logged.get("ok", False), "search_id": logged.get("search_id"),
            "request_id": logged.get("request_id"),
            **({"log_error": "검색 로그 기록 실패"} if not logged.get("ok") else {})}


def api_context_doc(paths, file: str) -> tuple:
    """컨텍스트 문서 **전문** — 검색 결과의 「전문 보기」 (사용자 요청 2026-09-29 · 공개로 결정).

    [중요] 이 포트는 **인증이 없다**(ufw LAN 한정 한 겹). 그래서 공개로 붙이되 좁힌다:
      · 트윈의 `context/` 아래 `.md` 만 — 절대경로·`..`·역슬래시는 거절, 실경로로 한 번 더 대조
      · 응답에 **절대경로를 싣지 않는다** (`api_history` 가 지키는 것과 같은 판단)
      · 마운트된 프로젝트만 — 호출자가 넘기는 `paths` 가 곧 마운트다(검색과 같은 규칙)
    [주의] 같은 부류의 전문이 이미 이 포트에 있다 — 도메인 게시판의 `_domains/*.md`. 검색 결과도
    400자 발췌를 이미 낸다. 그래서 **컨텍스트 문서는 민감 본문(히스토리 인용·절대경로)과 다른 부류**로
    봤고, 그 판단은 사용자가 했다.
    돌려주는 것: `(status, dict)` — 거절은 400/404 + 사유.
    """
    f = str(file or "").strip()
    if (not f or not f.endswith(".md") or f.startswith("/") or "\\" in f
            or ".." in Path(f).parts or ":" in f):
        return 400, {"error": "file 은 context/ 기준 상대 경로의 .md 여야 한다", "file": f}
    base = paths.context.resolve()
    target = (paths.context / f).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return 400, {"error": "context/ 밖이다", "file": f}
    if not target.is_file():
        return 404, {"error": "그 문서가 없다", "file": f}
    text = target.read_text(encoding="utf-8", errors="replace")
    front, body = "", text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front = text[3:end].strip("\n")
            body = text[end + 4:].lstrip("\n")
    return 200, {"file": f, "project": getattr(paths, "name", ""), "frontmatter": front,
                 "body": body, "chars": len(text)}


def api_rebuild() -> dict:
    # [중요] 웹이 재색인을 트리거하지 않는다 (머리말 § ④)
    return {"status": "refused", "note": NOTES["rebuild"]}


def api_refuse_mutation() -> dict:
    return {"status": "refused", "note": NOTES["mutation"]}
