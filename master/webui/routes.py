"""온톨로지 뷰어 + Context Server 웹 UI — 🔴 **원전 그대로 복각** (사용자 지시 2026-08-13).

> *"그대로 복각하라고"* / *"웹UX 모두 다 날라갔잖아 뭐한거야?"*

원전(`~/AgentTest/mcp/context_search/`)에 **3,700줄**짜리 웹 UI 가 있었는데 내가 읽지 않고
229줄짜리 접이식 목록을 새로 만들었다. 그것이 이 파일이 존재하는 이유다.

## 🔴 방향 — 프론트엔드를 고치지 않고 **백엔드를 맞춘다**

    static/ontology/domain.html   1,056줄   그대로
    static/ontology/app.css         839줄   그대로
    static/ontology/tree_nav.js     159줄   그대로
    static/ontology/index.html      171줄   그대로
    static/ontology/task.html       129줄   그대로
    vendor/cytoscape.min.js                 그대로 (🔴 CDN 금지 — 저장소에 담는다)
    web_ui_original.py              664줄   그대로 (상태카드 + 탭 4개)

원전 프론트엔드가 부르는 엔드포인트 **21개**를 우리 데이터로 채운다. 응답 **모양**이 조금이라도
다르면 화면이 그대로 못 돌기 때문에, 로더는 원전 `ontology_route_loaders.py` 를 경로만 바꿔
이식했다(`loaders.py`).

## 🔴 우리 데이터가 원전과 같은 구조였다

    domains/<도메인>/domain.yaml + L{1,2,3}/{objects,actions,invariants}/*.yaml

우리 트윈이 원전 스냅샷을 이어받았으므로 레이아웃이 같다. 그래서 로더가 거의 그대로 돌았다.

## ⚠️ 원전과 **다를 수밖에 없는 것** — 여기 다 적는다

    ① VSCode 열기      원전은 서버가 파일을 소유해서 됐다. 🔴 우리 마스터는 파일을 소유하지
                       않는다(§2.1) → 버튼은 두되 **경로 복사**로 동작하고 그 이유를 화면에 적는다
    ② history          원전엔 `history/` 기록이 있었다. 우리에겐 없다 → 빈 목록(화면이 알아서 숨긴다)
    ③ 태스크 템플릿    원전 `task.yaml` 템플릿 CRUD. 우리에겐 없다 → 빈 목록
    ④ 인덱스 rebuild   원전은 서버가 색인을 들고 있었다. 우리는 **별도 프로세스**(`ax-indexer`)라
                       웹에서 부르지 않는다 → 명령을 안내한다(🔴 웹이 재색인을 트리거하지 않는다)
    ⑤ 도메인 생성/채팅 원전은 LLM 으로 도메인 패키지를 만들었다. 🔴 우리 저장소는 온톨로지 편집을
                       **대화형 + 편집이 곧 잠금**으로 못박고 자동 승급을 영구 비활성했다 →
                       **읽기 전용**이고, 화면이 그 이유를 말한다

⚠️ ①~⑤ 는 **내 판단으로 뺀 것이 아니다** — 우리 아키텍처에서 물리적으로 다른 것과, 저장소가
이미 내려 둔 결정이다. 각각을 화면에 **적어서** 사람이 "왜 없지?" 를 묻지 않게 한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import loaders

STATIC = Path(__file__).parent / "static" / "ontology"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")

# 🔴 원전과 다른 점을 화면이 스스로 말하게 하는 문구 (위 § ①~⑤)
NOTES = {
    "vscode": "🔴 마스터는 파일을 소유하지 않는다(§2.1) — 경로를 복사해 작업 머신에서 연다",
    "history": "우리 트윈에는 항목별 history 기록이 아직 없다",
    "tasks": "태스크 템플릿은 이 저장소에 아직 없다",
    "rebuild": ("🔴 재색인은 웹에서 하지 않는다 — 색인기는 별도 프로세스다(`ax-indexer`). "
                "마스터에서: `python -m master.context_search.rebuild`"),
    "mutation": ("🔴 읽기 전용이다. 온톨로지 편집은 **대화형 + 편집이 곧 잠금**으로 정해져 있고 "
                 "자동 승급은 영구 비활성이다 — 웹 버튼이 트윈을 쓰지 않는다. "
                 "편집은 `python -m master.ontology` 와 MCP 도구로 한다"),
}


# ── 파일 서빙 ────────────────────────────────────────────────────────────────────

def read_static(name: str) -> tuple:
    """`(바이트, content-type)`. 🔴 이름만 받는다 — 경로를 조립하지 않는다."""
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    if not parts or not all(_SAFE.match(p) for p in parts):
        return None, b""
    p = STATIC.joinpath(*parts)
    try:
        p = p.resolve()
        p.relative_to(STATIC.resolve())          # 🔴 순회 이중 방어
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


# 🔴 원전 헤더의 상호 링크 자리에 **클러스터 상태**를 끼운다 (사용자 지시 2026-08-13:
#    *"복각한 페이지에서 연결하고 View를 제거해"*).
#
#    원전은 `/` 에 `Ontology Viewer →`, `/ontology` 에 `← Context Search` 를 두는 방식으로
#    화면을 서로 잇는다. **그 자리를 그대로 쓴다** — 새 내비게이션을 발명하지 않는다.
#
#    ⚠️ 원전 파일(`web_ui_original.py`·`*.html`)은 **바이트 그대로 둔다.** 링크는 **서빙 시점에
#    주입**한다 — 그래야 원전과의 diff 가 이 함수 하나에만 남고, 다음 사람이 "원전이 이랬나?"
#    를 헷갈리지 않는다.
_CLUSTER_LINK = (
    '<a href="/cluster" style="font-size:0.7em;font-weight:500;color:#d7ba7d;'
    'background:#252526;border:1px solid #d7ba7d;border-radius:6px;padding:6px 14px;'
    'text-decoration:none;margin-right:8px;">클러스터 상태 →</a>')
_CLUSTER_LINK_SMALL = (
    '<a href="/cluster" class="back" style="margin:0;color:#d7ba7d;">/ 클러스터 상태</a>')


def context_server_html() -> bytes:
    """원전 `web_ui.py` 의 HTML. 🔴 파일은 손대지 않고 **링크만 주입**한다."""
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
    """클러스터 상태 화면. 🔴 **`/cluster` 한 자리**로 옮겼다 — `/view` 는 없앴다.

    ⚠️ 스냅샷이라 낡을 수 있다 — 나이를 배너로 박는 판단은 그대로 유지한다.
    """
    from ..viewer import STALE_SEC, _age, inject, stale_banner
    p = paths.root / "cluster.html"
    if not p.is_file():
        return 503, ("<p>🔴 클러스터 상태 화면이 아직 만들어지지 않았다.</p>"
                     "<p>마스터에서: <code>python -m master.status html</code></p>"
                     '<p><a href="/">← Context Search</a></p>').encode("utf-8")
    body = p.read_text(encoding="utf-8", errors="replace")
    sec, _ = _age(p)
    if sec is not None and sec > STALE_SEC:
        body = inject(body, stale_banner(sec, "python -m master.status html"))
    # 🔴 원전 화면으로 돌아가는 링크 — 고아 페이지로 두지 않는다
    body = inject(body, (
        '<div style="margin:-1.5rem -1.5rem 1rem;padding:.5rem .9rem;'
        'border-bottom:1px solid #2f2f2c;font:13px/1.6 -apple-system,sans-serif">'
        '<a href="/" style="color:#4ec9b0;text-decoration:none">← Context Search</a>'
        '<span style="opacity:.4"> · </span>'
        '<a href="/ontology" style="color:#4ec9b0;text-decoration:none">Ontology Viewer</a>'
        '</div>'))
    return 200, body.encode("utf-8")


# ── API — 온톨로지 (읽기 전용) ───────────────────────────────────────────────────
#
# ⚠️ 2026-08-13: `cluster_page` 를 다시 쓰다가 이 아래를 **잘라먹어** `/api/v1/tags` 가 500 이
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
    # ⚠️ 원전엔 있고 우리에겐 없다 — **빈 목록 + 사유**. 없는 것을 있는 척하지 않는다
    return {"class": cls, "source": "all", "count": 0, "records": [],
            "note": NOTES["history"]}


def api_tasks() -> dict:
    return {"status": "ok", "count": 0, "templates": [], "note": NOTES["tasks"]}


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
    """색인 상태. 🔴 **필드명은 원전 프론트엔드가 읽는 그대로다** — `indexed_documents`.

    ⚠️ 실측 2026-08-13: 내가 `documents` 로 냈더니 화면이 **DOCUMENTS 0** 을 보였다(문서는
    1,055개 있었다). 프론트엔드를 그대로 쓰는 복각이므로 **모양을 맞추는 쪽이 우리다.**
    """
    out = {"indexed_documents": _doc_count(paths), "generation": "", "updating": False}
    try:
        from ..context_search.generation import current
        out["generation"] = current(paths)
    except Exception:                                        # noqa: BLE001
        pass
    return out


def api_tags(root: Path, paths=None) -> dict:
    """🔴 태그 클라우드.

    ⚠️ **모양이 계약이다**: 원전 `renderTagCloud` 는 `tags.tags` 를 **`{태그: 개수}` 객체**로
    받고 `Object.entries(...)` 로 돈다. 배열로 주면 화면이 빈 채로 뜬다(실측). 배지는 `total_tags`.

    출처는 둘 — 도메인 manifest 의 `tags`(온톨로지) + 오브젝트 `aliases`(시소러스의 한국어 말).
    """
    counts: dict = {}
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
    return {"tags": counts, "total_tags": len(counts)}


def api_search(paths, query: str, limit: int = 5) -> dict:
    """융합 검색(벡터+BM25). 🔴 우리 `ContextSearch` 를 그대로 쓴다."""
    try:
        from ..context_search import ContextSearch
        hits = ContextSearch(paths).search(query, limit=max(1, min(50, limit)))
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "results": []}
    return {"query": query, "count": len(hits),
            "results": [{"file": h.file_id, "score": round(h.rrf_score, 4),
                         "source": h.source, "category": (h.meta or {}).get("category", ""),
                         "tags": (h.meta or {}).get("tags", []),
                         "body": h.excerpt} for h in hits]}


def api_rebuild() -> dict:
    # 🔴 웹이 재색인을 트리거하지 않는다 (머리말 § ④)
    return {"status": "refused", "note": NOTES["rebuild"]}


def api_refuse_mutation() -> dict:
    return {"status": "refused", "note": NOTES["mutation"]}
