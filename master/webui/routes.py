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
from __future__ import annotations

import json
import re
from pathlib import Path

from ..context_search import documents
from . import loaders

STATIC = Path(__file__).parent / "static" / "ontology"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")

# [중요] 원전과 다른 점을 화면이 스스로 말하게 하는 문구 (위 § ①~⑤)
NOTES = {
    "vscode": "[중요] 마스터는 파일을 소유하지 않는다(§2.1) — 경로를 복사해 작업 머신에서 연다",
    "history": "우리 트윈에는 항목별 history 기록이 아직 없다",
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


# [중요] 원전 헤더의 상호 링크 자리에 **클러스터 상태**를 끼운다 (사용자 지시 2026-08-13:
#    *"복각한 페이지에서 연결하고 View를 제거해"*).
#
#    원전은 `/` 에 `Ontology Viewer →`, `/ontology` 에 `← Context Search` 를 두는 방식으로
#    화면을 서로 잇는다. **그 자리를 그대로 쓴다** — 새 내비게이션을 발명하지 않는다.
#
#    [주의] 원전 파일(`web_ui_original.py`·`*.html`)은 **바이트 그대로 둔다.** 링크는 **서빙 시점에
#    주입**한다 — 그래야 원전과의 diff 가 이 함수 하나에만 남고, 다음 사람이 "원전이 이랬나?"
#    를 헷갈리지 않는다.
_CLUSTER_LINK = (
    '<a href="/cluster" style="font-size:0.7em;font-weight:500;color:#d7ba7d;'
    'background:#252526;border:1px solid #d7ba7d;border-radius:6px;padding:6px 14px;'
    'text-decoration:none;margin-right:8px;">클러스터 상태 →</a>')
_CLUSTER_LINK_SMALL = (
    '<a href="/cluster" class="back" style="margin:0;color:#d7ba7d;">/ 클러스터 상태</a>')


def context_server_html() -> bytes:
    """원전 `web_ui.py` 의 HTML. [중요] 파일은 손대지 않고 **링크만 주입**한다."""
    from .web_ui_original import WEB_UI_HTML
    anchor = '<a href="/ontology"'
    html_text = WEB_UI_HTML
    if anchor in html_text:
        html_text = html_text.replace(anchor, _CLUSTER_LINK + anchor, 1)
    return html_text.encode("utf-8")


def inject_cluster_link(body: bytes) -> bytes:
    """`/ontology` 페이지들의 `Context Search` 링크 옆에 클러스터 상태를 끼운다."""
    text = body.decode("utf-8", "replace")
    anchor = '<a href="/" class="back"'
    if anchor in text:
        text = text.replace(anchor, _CLUSTER_LINK_SMALL + anchor)
    else:
        anchor2 = '<a href="/" style="font-size:13px'
        if anchor2 in text:
            text = text.replace(
                anchor2,
                '<a href="/cluster" style="font-size:13px;color:#d7ba7d;background:#252526;'
                'border:1px solid #d7ba7d;border-radius:6px;padding:6px 14px;'
                'text-decoration:none;white-space:nowrap;margin-right:8px;">클러스터 상태</a>'
                + anchor2, 1)
    return text.encode("utf-8")


def cluster_page(paths) -> tuple:
    """클러스터 상태 화면. [중요] **`/cluster` 한 자리**로 옮겼다 — `/view` 는 없앴다.

    [주의] 스냅샷이라 낡을 수 있다 — 나이를 배너로 박는 판단은 그대로 유지한다.
    """
    from ..viewer import STALE_SEC, _age, inject, stale_banner
    p = paths.root / "cluster.html"
    if not p.is_file():
        return 503, ("<p>[중요] 클러스터 상태 화면이 아직 만들어지지 않았다.</p>"
                     "<p>마스터에서: <code>python -m master.status html</code></p>"
                     '<p><a href="/">← Context Search</a></p>').encode("utf-8")
    body = p.read_text(encoding="utf-8", errors="replace")
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
    # work 중심 층 (#222) — 화면의 주어를 등록 단위로 올린다. 실시간 층 **아래**에 둔다:
    #    「지금 무엇이 도는가」가 먼저고, 「내 작업이 어디까지 왔나」가 그 다음이다.
    #    실시간 층을 못 읽었으면(토큰·큐 장애) work 도 재료가 없으므로 그리지 않는다.
    if not got.get("error"):
        # 회수된 워커 로그를 함께 넘긴다 (#220 ③-B) — [중요] **로컬 사본만 읽는다.**
        #    서빙 순간의 scp 는 15초 자동 리로드와 만나 120초 가드를 깬다. 회수는
        #    ax-status.timer(5분)의 SSH 순간에만 한다 (`master.work.logs`).
        stored, host_logs = {}, {}
        try:
            from ..work import logs as _logs
            ids = [str(t.get("task_id") or "") for t in (got.get("tasks") or [])
                   if isinstance(t, dict)]
            stored = _logs.read_stored(paths, ids)
            host_logs = _logs.read_host_logs(paths)
        except Exception:                                    # noqa: BLE001
            stored, host_logs = {}, {}   # 로그는 부가 정보 — 없다고 화면을 죽이지 않는다
        live += _status.work_section(got.get("works"), got.get("tasks"), logs=stored)
        live += _status.daemon_log_section(host_logs)
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
    # [중요] 원전 화면으로 돌아가는 링크 — 고아 페이지로 두지 않는다.
    #    색은 **원전 헤더와 같은 `#4ec9b0`**, 경계선은 `status.py` 의 `--line`(#30363d) 이다.
    #    [주의] 전에는 경계선을 `#2f2f2c` 로 박아 뒀는데, 그건 내가 만든 옛 팔레트의 값이었다 —
    #    화면 색을 원전에 맞추면서 **여기 하드코딩도 같이 옮겨야** 한다(사용자 지적 2026-08-13).
    body = inject(body, (
        '<div style="margin:-1.5rem -1.5rem 1rem;padding:.5rem .9rem;'
        'border-bottom:1px solid #30363d;font:13px/1.6 -apple-system,sans-serif">'
        '<a href="/" style="color:#4ec9b0;text-decoration:none">← Context Search</a>'
        '<span style="opacity:.4"> · </span>'
        '<a href="/ontology" style="color:#4ec9b0;text-decoration:none">Ontology Viewer</a>'
        '</div>'))
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


def api_history(cls: str) -> dict:
    # [주의] 원전엔 있고 우리에겐 없다 — **빈 목록 + 사유**. 없는 것을 있는 척하지 않는다
    return {"class": cls, "source": "all", "count": 0, "records": [],
            "note": NOTES["history"]}


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
    try:
        from ..context_search.documents import iter_documents
        md = sum(1 for _ in iter_documents(paths.context))
    except Exception:                                        # noqa: BLE001
        md = _doc_count(paths)          # 최후 폴백 — 그러면 판정이 헐거워진다
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
    try:
        from ..context_search.generation import current
        out["generation"] = current(paths)
    except Exception:                                        # noqa: BLE001
        pass
    return out


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


def api_search(paths, query: str, limit: int = 5) -> dict:
    """융합 검색(벡터+BM25). [중요] 우리 `ContextSearch` 를 그대로 쓴다.

    [중요] **여기도 기록한다** (소 3.4.5). 원전은 MCP(`search_tools.py`)와 **HTTP
    (`search_routes.py`) 양쪽**에서 `_log_search` 를 부른다 — 한쪽만 심으면 로그가 표면에
    따라 편향되고, 채널 튜닝의 근거가 조용히 반쪽이 된다. [주의] 실제로 처음엔 MCP 만 심었고
    재기동을 검증하려다 이 자리를 발견했다.

    [주의] `caller="web_ui"` 는 **원전 vocabulary 에 없는 값**이다. 원전 HTTP 라우트는 caller 를
    **클라이언트가 신고**하는데(`req.caller`, 기본 None) 우리 webui 는 in-process 호출이라
    신고할 주체가 없다. 표면을 못 가르면 이 필드의 존재 의미가 없으므로 값을 준다.
    """
    try:
        from ..context_search import ContextSearch
        hits = ContextSearch(paths).search(query, limit=max(1, min(50, limit)))
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "results": []}
    # [중요] 검색 뒤에 기록한다 — 실패하면 기록할 것이 없고, 기록은 검색을 막지 않는다.
    from ..context_search import search_log
    search_log.log_search(paths, query=query, hits=hits, caller="web_ui")
    return {"query": query, "count": len(hits),
            "results": [{"file": h.file_id, "score": round(h.rrf_score, 4),
                         "source": h.source, "category": (h.meta or {}).get("category", ""),
                         "tags": (h.meta or {}).get("tags", []),
                         "body": h.excerpt} for h in hits]}


def api_rebuild() -> dict:
    # [중요] 웹이 재색인을 트리거하지 않는다 (머리말 § ④)
    return {"status": "refused", "note": NOTES["rebuild"]}


def api_refuse_mutation() -> dict:
    return {"status": "refused", "note": NOTES["mutation"]}
