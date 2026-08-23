"""도메인 게시판 mutation (원전 복각 · 사용자 결정 2026-08-13).

[중요] 지키는 계약은 다섯이다:

    ① **게시판은 `_domains/*.md` 다** — 온톨로지 YAML 을 건드리지 않는다(두 층을 헷갈리면 안 된다)
    ② **경로 이탈을 막는다** — 다만 [중요] **한글 이름은 허용**한다(원전이 그랬다)
    ③ `_` 로 시작하는 관리 문서(`_overview`·`_unassigned`)는 **손대지 않는다**
    ④ [중요] **삭제는 아카이브다** — 웹 버튼 한 번으로 사람이 쓴 문서를 잃지 않는다
    ⑤ **원자적 쓰기** — 색인기(inotify)가 반쯤 쓰인 문서를 집어가면 안 된다

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


def test_management_docs_are_never_written() -> None:
    paths, root = tmp_paths()
    try:
        before = (paths.context / "_domains" / "_overview.md").read_text(encoding="utf-8")
        for fn in (lambda: B.update_domain(paths, "_overview", "덮어쓴다"),
                   lambda: B.activate_domain(paths, "_overview", "덮어쓴다"),
                   lambda: B.delete_domain(paths, "_overview")):
            try:
                fn()
                check("[중요] 관리 문서를 건드렸다", False, "통과해버렸다")
            except B.BoardError:
                check("관리 문서는 거부", True)
        after = (paths.context / "_domains" / "_overview.md").read_text(encoding="utf-8")
        check("내용이 그대로", before == after)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 갱신 · 활성화 ───────────────────────────────────────────────────────────────

def test_update_refuses_empty() -> None:
    paths, root = tmp_paths()
    try:
        try:
            B.update_domain(paths, "시험도메인", "   ")
            check("[중요] 빈 내용으로 덮었다", False, "통과해버렸다")
        except B.BoardError as e:
            check("빈 내용은 거부", "빈 내용" in str(e), str(e))
        got = B.update_domain(paths, "시험도메인", DRAFT + "\n추가됨\n")
        check("갱신은 된다", got["status"] == "updated")
        check("내용이 반영", "추가됨" in
              (paths.context / "_domains" / "시험도메인.md").read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_activate_flips_status_and_inherits_tags() -> None:
    """[중요] 원전과 같은 동작 — draft→active + 소스 문서 태그 상속."""
    paths, root = tmp_paths()
    try:
        got = B.activate_domain(paths, "시험도메인", DRAFT)
        check("활성화됨", got["status"] == "activated", str(got))
        text = (paths.context / "_domains" / "시험도메인.md").read_text(encoding="utf-8")
        check("status 가 active", "status: active" in text)
        check("draft 가 남지 않음", "status: draft" not in text)
        # 소스의 tags [mission, snapshot, UI] 를 상속
        for t in ("mission", "snapshot", "UI"):
            check(f"태그 상속: {t}", t in text, text[:120])
        # [중요] 색인은 우리가 하지 않는다 — 색인기에 맡긴다
        check("색인을 직접 하지 않는다", got["indexed"] is False)
        check("누가 색인하는지 말한다", "ax-indexer" in got["note"], got["note"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── ④ 삭제는 아카이브 ───────────────────────────────────────────────────────────

def test_delete_archives_instead_of_removing() -> None:
    """[중요] 웹 버튼 한 번으로 사람이 쓴 문서를 잃지 않는다 (원전은 지웠다)."""
    paths, root = tmp_paths()
    try:
        B.save_chat(paths, "시험도메인", [{"role": "user", "content": "x"}])
        got = B.delete_domain(paths, "시험도메인")
        check("아카이브됨", got["status"] == "archived", str(got))
        check("원본이 없다", not (paths.context / "_domains" / "시험도메인.md").exists())
        arch = list((paths.context / "_domains" / "_archive").glob("시험도메인.*.md"))
        check("아카이브에 있다", len(arch) == 1, str(arch))
        check("내용이 살아 있다", "시험용 초안" in arch[0].read_text(encoding="utf-8"))
        check("채팅도 지워진다", B.load_chat(paths, "시험도메인") == [])
        check("되돌릴 수 있다고 말한다", "되돌릴 수 있다" in got["note"], got["note"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── ⑤ 원자적 쓰기 ──────────────────────────────────────────────────────────────

def test_writes_are_atomic() -> None:
    """색인기(inotify)가 반쯤 쓰인 문서를 집어가면 안 된다."""
    src = Path(B.__file__).read_text(encoding="utf-8")
    check("tmp → replace 를 쓴다", "tmp.replace(p)" in src)
    check("[중요] 직접 write_text 로 본문을 쓰지 않는다",
          "p.write_text(content" not in src and "md_path(paths, name).write_text" not in src)


def test_chat_history_round_trip() -> None:
    paths, root = tmp_paths()
    try:
        B.save_chat(paths, "시험도메인", [{"role": "user", "content": "안녕"}])
        got = B.load_chat(paths, "시험도메인")
        check("히스토리 왕복", got and got[0]["content"] == "안녕", str(got))
        B.clear_chat(paths, "시험도메인")
        check("초기화", B.load_chat(paths, "시험도메인") == [])
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


def test_create_without_llm_says_so() -> None:
    """[주의] LLM 없이 만들어졌다는 사실을 숨기지 않는다."""
    paths, root = tmp_paths()
    saved = B.call_llm
    try:
        B.call_llm = lambda *a, **k: None
        got = B.create_domain(paths, "테스트 주제")
        check("초안은 만들어진다", got["status"] == "created", str(got))
        check("[중요] LLM 실패를 말한다", "LLM" in (got.get("note") or ""), str(got.get("note")))
        p = paths.context / "_domains" / f"{got['domain_name']}.md"
        check("파일이 있다", p.is_file(), str(p))
        check("draft 로 만든다", "status: draft" in p.read_text(encoding="utf-8"))
    finally:
        B.call_llm = saved
        shutil.rmtree(root, ignore_errors=True)


def test_create_refuses_empty_topic() -> None:
    paths, root = tmp_paths()
    try:
        try:
            B.create_domain(paths, "  ")
            check("[중요] 빈 주제를 통과시켰다", False)
        except B.BoardError as e:
            check("빈 주제는 거부", "topic" in str(e), str(e))
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


def main() -> int:
    for fn in (test_board_lists_md_not_ontology, test_detail_carries_source_contents,
               test_korean_names_allowed_traversal_blocked,
               test_management_docs_are_never_written, test_update_refuses_empty,
               test_activate_flips_status_and_inherits_tags,
               test_delete_archives_instead_of_removing, test_writes_are_atomic,
               test_chat_history_round_trip, test_frontmatter_parses_our_format,
               test_create_without_llm_says_so, test_create_refuses_empty_topic,
               test_tag_cloud_counts_context_documents):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_board: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
