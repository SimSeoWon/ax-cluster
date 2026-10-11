"""도메인 게시판 — **읽기 전용** (쓰기는 `#812` 2026-10-11 에 걷었다).

[중요] 지키는 계약은 넷이다:

    ① **게시판은 `_domains/*.md` 다** — 온톨로지 YAML 이 아니다(두 층을 헷갈리면 안 된다)
    ② **경로 이탈을 막는다** — 다만 [중요] **한글 이름은 허용**한다(원전이 그랬다)
    ③ `_` 로 시작하는 관리 문서(`_overview`·`_unassigned`)는 목록·상세에 **내지 않는다**
    ④ 🔴 **쓰기·채팅 코드는 없다**(`#812`) — 상세는 `chat_history` 를 싣지 않고, 읽기는 아무것도 쓰지 않는다

`.venv/bin/python master/test_board.py`
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.webui import board as B      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


DRAFT = """---
tags: []
category: 도메인/시험
type: domain
status: draft
source_documents:
  - Source/A/Foo.md
created: 2026-08-13
---

## 시스템 개요

시험용 초안이다.
"""

SRC = """---
tags: [mission, snapshot, UI]
category: 코드/Foo
---

## 요약

소스 문서다.
"""


def tmp_paths(*, with_src=True):
    root = Path(tempfile.mkdtemp(prefix="axboard"))
    ctx = root / "context"
    (ctx / "_domains").mkdir(parents=True)
    (ctx / "_domains" / "시험도메인.md").write_text(DRAFT, encoding="utf-8")
    # [중요] 관리 문서 — 게시판에 나오지도, 수정되지도 않아야 한다
    (ctx / "_domains" / "_overview.md").write_text("---\ntype: index\n---\n관리 문서\n",
                                                   encoding="utf-8")
    if with_src:
        (ctx / "Source" / "A").mkdir(parents=True)
        (ctx / "Source" / "A" / "Foo.md").write_text(SRC, encoding="utf-8")

    class P:
        name = "T"
    P.root = root
    P.context = ctx
    return P(), root


# ── ① 게시판은 MD 문서다 ────────────────────────────────────────────────────────

def test_board_lists_md_not_ontology() -> None:
    paths, root = tmp_paths()
    try:
        got = B.list_board(paths)
        names = [d["name"] for d in got["domains"]]
        check("초안이 보인다", names == ["시험도메인"], str(names))
        check("[중요] 관리 문서(`_`)는 안 보인다", "_overview" not in names, str(names))
        check("draft 로 센다", got["counts"]["draft"] == 1, str(got["counts"]))
        d = got["domains"][0]
        check("소스 문서 목록", d["source_documents"] == ["Source/A/Foo.md"],
              str(d["source_documents"]))
        check("개요를 요약으로", "시험용 초안" in d["summary"], d["summary"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_detail_carries_source_contents() -> None:
    paths, root = tmp_paths()
    try:
        got = B.get_board_domain(paths, "시험도메인")
        check("상세가 온다", got is not None)
        check("소스 본문을 싣는다", "소스 문서다" in got["source_documents"][0]["content"])
        check("없는 소스는 그렇게 말한다",
              B.get_board_domain(tmp_paths(with_src=False)[0],
                                 "시험도메인")["source_documents"][0]["content"]
              == "(파일 없음)")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── ②③ 이름 · 경로 안전 ────────────────────────────────────────────────────────

def test_korean_names_allowed_traversal_blocked() -> None:
    """[중요] 원전은 한글 파일명을 그대로 썼다 — 내가 좁혔다가 이름이 `domain` 이 됐다(실측)."""
    paths, root = tmp_paths()
    try:
        check("한글 이름 허용", B.md_path(paths, "미션 스냅샷").name == "미션 스냅샷.md")
        for bad in ("../etc/passwd", "a/b", "a\\b", "..", ".hidden", "_overview",
                    "끝점.", " 앞공백", "긴이름" * 40):
            try:
                B.md_path(paths, bad)
                check(f"[중요] 거부해야 함: {bad!r}", False, "통과해버렸다")
            except B.BoardError:
                check(f"거부: {bad!r}", True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 쓰기는 걷혔다 (`#812`) ────────────────────────────────────────────────────────

RETIRED = ("create_domain", "chat", "update_domain", "activate_domain", "delete_domain",
           "clear_chat", "save_chat", "load_chat", "chat_dir", "call_llm", "related_docs",
           "_atomic_write", "CHAT_DIR")


def test_writes_are_retired() -> None:
    """🔴 `#812` (사용자 결정 2026-10-11) — 게시판 쓰기·채팅 코드가 되살아나지 않는다."""
    for name in RETIRED:
        check(f"[중요] `board.{name}` 이 없다", not hasattr(B, name), "되살아났다")
    src = Path(B.__file__).read_text(encoding="utf-8")
    for needle in ("write_text(", ".replace(p)", "unlink(", "mkdir("):
        check(f"board.py 에 쓰기 호출 `{needle}` 이 없다", needle not in src)


def test_detail_has_no_chat_and_reads_do_not_write() -> None:
    """상세는 `chat_history` 를 싣지 않고, 읽기가 디렉토리(`.chat`)를 만들지 않는다."""
    paths, root = tmp_paths()
    try:
        d = paths.context / "_domains"
        before = sorted(p.name for p in d.rglob("*"))
        got = B.get_board_domain(paths, "시험도메인")
        B.list_board(paths)
        check("chat_history 키가 없다", "chat_history" not in got, str(sorted(got)))
        check("응답 키는 넷", sorted(got) == ["content", "name", "source_documents", "status"],
              str(sorted(got)))
        check("[중요] 읽기가 파일·디렉토리를 만들지 않는다",
              sorted(p.name for p in d.rglob("*")) == before)
        try:
            B.get_board_domain(paths, "_overview")
            check("[중요] 관리 문서를 상세로 냈다", False, "통과해버렸다")
        except B.BoardError:
            check("관리 문서 상세는 거부", True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_frontmatter_parses_our_format() -> None:
    meta = B.parse_front(SRC)
    check("인라인 리스트", meta.get("tags") == ["mission", "snapshot", "UI"], str(meta))
    meta2 = B.parse_front(DRAFT)
    check("블록 리스트", meta2.get("source_documents") == ["Source/A/Foo.md"], str(meta2))
    check("빈 리스트", meta2.get("tags") == [], str(meta2.get("tags")))
    check("status", meta2.get("status") == "draft")
    check("frontmatter 없으면 빈 dict", B.parse_front("본문만") == {})


def test_tag_cloud_counts_context_documents() -> None:
    """[중요] **태그 클라우드의 정본은 컨텍스트 문서다** (`#288`, 이식 드리프트 복구).

    원전 `search_routes.py:400` 은 `_index.tag_cache` 를 돌고, 그 캐시는
    `_build_tag_cache` 가 **`context/` 의 모든 MD 프론트매터**에서 만든다(`_domains/` 제외).
    우리 이식은 그 축을 빼먹고 **도메인만** 셌다 — 실측 2026-08-23: NS 는 컨텍스트 문서 42건에
    한글 태그가 있는데 도메인이 0개라 화면이 **완전히 비어 있었다.** ModularStage 는 도메인이
    많아 채워져 보였으므로 드러나지 않았다(**N=1 이 설계를 검증하지 않는다**).
    """
    from master.context_search.paths import ProjectPaths
    from master.webui import routes as R

    print("\n[태그] 컨텍스트 문서의 프론트매터를 센다 (#288)")
    tmp = Path(tempfile.mkdtemp(prefix="ax-tags-"))
    p = ProjectPaths(name="T", root=tmp / "T")
    (p.context / "Source" / "NS").mkdir(parents=True)
    (p.context / "Source" / "NS" / "A.md").write_text(
        "---\ntags: [캐릭터, 점프, Character]\n---\n본문", encoding="utf-8")
    (p.context / "Source" / "NS" / "B.md").write_text(
        "---\ntags: [캐릭터, 게임모드]\n---\n본문", encoding="utf-8")
    # [중요] `_domains/*.md` 는 제외한다 — 원전과 같은 규칙(별도 진입점)
    (p.context / "_domains").mkdir(parents=True)
    (p.context / "_domains" / "D.md").write_text(
        "---\ntags: [도메인문서는_안_센다]\n---\n본문", encoding="utf-8")

    r = R.api_tags(p.root, p)
    check("컨텍스트 문서 태그를 센다 (도메인 0개여도)", r["total_tags"] == 4,
          f"{r['total_tags']} {r['tags']}")
    check("[중요] 한글 태그가 들어간다 (문서가 한국어다)",
          r["tags"].get("캐릭터") == 2 and "게임모드" in r["tags"], str(r["tags"]))
    check("[중요] `_domains/` 는 제외한다 (원전 규칙)",
          "도메인문서는_안_센다" not in r["tags"], str(r["tags"]))
    check("많이 쓰인 순으로 준다 (화면이 크기를 그 순서로 정한다)",
          list(r["tags"])[0] == "캐릭터", str(list(r["tags"])[:3]))
    # [주의] 모양이 계약이다 — 원전 renderTagCloud 는 `{태그: 개수}` 객체를 Object.entries 로 돈다
    check("[주의] 배열이 아니라 객체다 (배열이면 화면이 빈 채로 뜬다)",
          isinstance(r["tags"], dict), type(r["tags"]).__name__)
    shutil.rmtree(tmp, ignore_errors=True)


def test_index_status_reveals_mismatch() -> None:
    """[중요] **색인 상태는 불일치를 드러내야 한다** (`#295`, 이식 드리프트 복구).

    원전 `search_routes.py:409` 는 `status`·`context_md_files`·`bm25_documents`·
    `needs_rebuild`·`vector_available`·`bm25_available` 을 함께 낸다. 우리는 그 다섯이 없었고,
    더 나쁘게 **`indexed_documents` 에 파일 개수를 냈다** — 그러면 색인이 실패해도 화면은
    정상으로 보인다(파일은 그대로 있으니까).

    [주의] **분모는 「색인 가능한」 문서다** — 파일 개수로 세면 판정이 영구히 「재색인 필요」가
    된다. 원전이 같은 자리에서 한 번 틀리고 주석으로 남겼고, 나도 이 커밋에서 처음 그렇게 짜
    ModularStage 를 961/1055 로 읽었다(실제로는 961/961 이 맞다 — 제외 규칙·빈 문서).
    """
    from master.context_search.paths import ProjectPaths
    from master.webui import routes as R

    print("\n[색인] 상태가 불일치를 드러낸다 (#295)")
    tmp = Path(tempfile.mkdtemp(prefix="ax-idxst-"))
    p = ProjectPaths(name="T", root=tmp / "T")
    (p.context / "Source").mkdir(parents=True)
    (p.context / "Source" / "A.md").write_text("---\ntags: [a]\n---\n본문", encoding="utf-8")
    # [중요] 제외·빈 문서는 분모에서 빠진다 — 색인이 넣지 않는 것을 분모에 넣으면 판정이 거짓이 된다
    (p.context / "_domains").mkdir(parents=True)
    (p.context / "_domains" / "D.md").write_text("---\ntags: [d]\n---\n본문", encoding="utf-8")
    (p.context / "Source" / "empty.md").write_text("", encoding="utf-8")

    d = R.api_index_status(p)
    for k in ("status", "indexed_documents", "context_md_files", "bm25_documents",
              "needs_rebuild", "vector_available", "bm25_available"):
        check(f"필드 `{k}` 가 있다 (원전 계약)", k in d, str(sorted(d)))
    check("[중요] 분모는 색인 가능한 문서 1건 (`_domains`·빈 문서 제외)",
          d["context_md_files"] == 1, f"{d['context_md_files']} {d}")
    # 색인이 없는 프로젝트 — [중요] **「모른다」를 「괜찮다」로 접지 않는다**
    check("[중요] 색인을 못 읽으면 재색인 필요로 답한다", d["needs_rebuild"] is True, str(d))
    check("  그리고 그 사실을 말한다 (0 으로 뭉개지 않는다)",
          d["vector_available"] is False and "읽지 못했다" in d["status"], str(d))
    shutil.rmtree(tmp, ignore_errors=True)


# ── ④ 빈 질의 = 문서 목록 (`#378`) ──────────────────────────────────────────────

def test_blank_query_lists_documents() -> None:
    """🔴 원전 화면은 **문서 목록을 빈 질의로** 가져온다 (`loadDocs`).

    우리 포팅이 서버에 *"query 가 비었다"* 거절을 넣어 **모든 프로젝트에서 목록이 처음부터
    비어 있었다** — 에러가 아니라 빈 목록이라 아무도 몰랐다(실측 2026-09-06).
    [주의] 같은 규칙이 **클라이언트에는 남는다** — MCP 도구의 빈 질의는 호출자 실수다.
    """
    print("\n[④] 빈 질의는 목록이다 (`#378`)")
    from master.webui import routes as R
    paths, root = tmp_paths()
    try:
        got = R.api_documents(paths, 100)
        files = [r["file"] for r in got["results"]]
        check("소스 문서가 목록에 나온다", "Source/A/Foo.md" in files, str(files))
        check("[중요] 게시판(`_domains/*.md`)은 문서 목록이 아니다",
              not any(f.startswith("_domains/") for f in files), str(files))
        r0 = got["results"][0]
        check("화면이 읽는 필드 넷이 있다 (file·tags·category·content_preview)",
              all(k in r0 for k in ("file", "tags", "category", "content_preview")), str(r0.keys()))
        check("태그는 프론트매터에서 온다", isinstance(r0["tags"], list) and r0["tags"], str(r0["tags"]))
        check("limit 이 듣는다", R.api_documents(paths, 1)["count"] == 1)
        check("문서가 없으면 빈 목록 (예외가 아니다)",
              R.api_documents(tmp_paths(with_src=False)[0], 10)["count"] == 0)

        # 🔴 [중요] **태그는 언제나 배열이다** (`#380`). 벡터 저장소 메타는 콤마 문자열로 갖는데
        #    원전은 내보낼 때 쪼갠다 — 그 한 줄을 안 옮겨 화면이 `.map is not a function` 으로
        #    죽었다(사용자 실측: 문서를 클릭하면 *"Search failed"*).
        check("문자열 메타를 배열로 쪼갠다", R._tag_list("A,B, C") == ["A", "B", "C"],
              str(R._tag_list("A,B, C")))
        check("이미 배열이면 그대로", R._tag_list(["A", "B"]) == ["A", "B"])
        check("빈 값은 빈 배열 (None 도)", R._tag_list(None) == [] and R._tag_list("") == [])
        check("[주의] 빈 조각은 버린다 — 화면에 빈 태그 칩이 생긴다",
              R._tag_list("A,,B,") == ["A", "B"], str(R._tag_list("A,,B,")))
    finally:
        shutil.rmtree(root, ignore_errors=True)



# ── ⑤ 검색 결과 행이 원전 스키마다 (`#381`) ─────────────────────────────────────

class _FakeHit:
    def __init__(self, **kw):
        self.file_id = kw.get("file_id", "Source/A/Foo.md")
        self.source = kw.get("source", "vector")
        self.rrf_score = kw.get("rrf_score", 0.0164)
        self.similarity = kw.get("similarity", 0.6089)
        self.bm25_score = kw.get("bm25_score", 0.0)
        self.meta = kw.get("meta", {"category": "C/D", "tags": "A,B",
                                    "content_hash": "deadbeef"})
        self.excerpt = kw.get("excerpt", "본문 발췌")


def test_search_row_matches_origin_schema() -> None:
    """🔴 원전 결과 행 키를 갖는다 (`#381`). 프론트엔드를 그대로 쓰므로 **모양을 맞추는 쪽이 우리**다.

    [중요] `similarity` 를 **지어내지 않는다** — BM25 단독(0.0)이면 `None` 이고, 화면은 그때
    `source` 를 보인다. 우리 `rrf_score` 는 융합 순위라 유사도가 아니다(넣으면 「1.6%」가 뜬다).
    """
    print("\n[⑤] 검색 행이 원전 스키마다 (`#381`)")
    from master.webui import routes as R
    paths, root = tmp_paths()
    try:
        row = R._search_row(paths, _FakeHit())
        for k in ("file", "similarity", "category", "tags", "related_classes",
                  "content_hash", "content_preview"):
            check(f"원전 키 `{k}` 가 있다", k in row, str(sorted(row)))
        check("  tags 는 배열", row["tags"] == ["A", "B"], str(row["tags"]))
        check("  similarity 는 **진짜 벡터 유사도**", row["similarity"] == 0.6089, str(row["similarity"]))
        check("🔴 BM25 단독이면 similarity 는 None (화면이 source 로 폴백)",
              R._search_row(paths, _FakeHit(similarity=0.0))["similarity"] is None)
        check("  [주의] 융합 점수를 similarity 로 내보내지 않는다 — 별도 키 `score`",
              row["score"] == 0.0164 and row["similarity"] != row["score"], str(row))
        check("  하위호환 `body` 도 남는다 (우리 소비자가 쓴다)", row["body"] == "본문 발췌")
        check("  그래프가 없으면 included_by 는 빈 배열", row["included_by"] == [],
              str(row["included_by"]))
        check("[주의] `co_changed` 는 만들지 않는다 — **원전 서버에도 없다**(화면만 읽는다)",
              "co_changed" not in row, str(sorted(row)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (test_board_lists_md_not_ontology, test_detail_carries_source_contents,
               test_korean_names_allowed_traversal_blocked, test_blank_query_lists_documents,
               test_search_row_matches_origin_schema,
               test_writes_are_retired, test_detail_has_no_chat_and_reads_do_not_write,
               test_frontmatter_parses_our_format,
               test_tag_cloud_counts_context_documents,
               test_index_status_reveals_mismatch):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_board: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
