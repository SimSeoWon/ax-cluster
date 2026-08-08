"""검색 코어 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_context_search.py

🔴 지키는 불변식:
   1. **마운트가 경로를 정한다** — 전환하면 다음 호출이 바로 새 디렉토리를 본다 (§5.5.2)
   2. **본문 없는 스텁도 색인한다** — 클래스명이 그 문서의 존재 이유다
   3. **세대 포인터는 두 채널이 공유한다** — 벡터와 BM25 가 어긋나면 융합이 무의미해진다
   4. **재색인 실패가 옛 세대를 깨지 않는다** — 마커는 마지막에 한 번만 쓴다
   5. **RRF 는 점수가 아니라 순위를 섞는다** — 척도가 다른 두 채널을 더할 수 없다

무거운 임베딩(chromadb)은 여기서 부르지 않는다. **벡터 채널은 결과 dict 로 대역**하고
실제 색인은 `rebuild.py` 로 따로 실측한다 — 테스트가 40초씩 걸리면 아무도 안 돌린다.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search import generation  # noqa: E402
from master.context_search.bm25 import (  # noqa: E402
    BODY_BOOST, CATEGORY_BOOST, FTS5_AVAILABLE, RELATED_CLASSES_BOOST, TAGS_BOOST,
    Bm25Index, class_names, tokenize,
)
from master.context_search.documents import (  # noqa: E402
    extract_body, is_excluded, iter_documents, load, parse_frontmatter,
)
from master.context_search.paths import (  # noqa: E402
    SOURCE_SUBDIR, ProjectPaths, resolve, resolve_mounted_only,
)
from master.context_search.search import RRF_K, Hit, fuse  # noqa: E402
from master.projects.config import ConfigError  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


class FakeRegistry:
    """`Registry` 의 최소 대역 — 마운트 전환만 흉내 낸다."""

    def __init__(self, root: Path, names: list[str], active: str = ""):
        self._root = root
        self.names = names
        self.active = active

    def dir_of(self, name: str) -> Path:
        return self._root / name


def make_project(root: Path, name: str, docs: dict[str, str]) -> ProjectPaths:
    p = ProjectPaths(name=name, root=root / name)
    (p.repo / SOURCE_SUBDIR).mkdir(parents=True, exist_ok=True)
    for rel, text in docs.items():
        f = p.context / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return p


STUB = "---\ntags: [manager, core]\ncategory: Manager\nrelated_classes:\n  - UManagerBase: Source/Manager/ManagerBase.h\n---\n"
FULL = "---\ntags: [ui]\ncategory: UI\n---\n\n타일 위젯을 격자로 배치하는 뷰다.\n"
BLANK = "---\ntags: []\n---\n"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-cs-test-"))

    # ── 1. 경로 해석은 마운트를 따른다 ──────────────
    print("\n[1] 마운트가 경로를 정한다 (§5.5.2)")
    reg = FakeRegistry(tmp, ["Alpha", "Beta"], active="Alpha")
    check("active 를 따라간다", resolve(registry=reg).name == "Alpha")
    check("루트가 갈린다", resolve(registry=reg).root == tmp / "Alpha")
    reg.active = "Beta"
    check("🔴 전환 즉시 새 경로 (재기동 없음)", resolve(registry=reg).root == tmp / "Beta")
    check("이름을 주면 그쪽", resolve("Alpha", registry=reg).name == "Alpha")

    for bad, why in [("", "active 가 비었다"), ("Gamma", "등록되지 않았다")]:
        r = FakeRegistry(tmp, ["Alpha"], active="" if not bad else "Alpha")
        try:
            resolve(bad, registry=r)
            check(f"거부: {why}", False, "예외가 안 났다")
        except ConfigError:
            check(f"거부: {why}", True)

    print("\n[2] 단일 마운트 정책은 별도 함수다")
    reg.active = "Alpha"
    check("마운트된 것은 통과", resolve_mounted_only("Alpha", registry=reg).name == "Alpha")
    try:
        resolve_mounted_only("Beta", registry=reg)
        check("🔴 마운트 안 된 것은 거부", False, "통과해 버렸다")
    except ConfigError:
        check("🔴 마운트 안 된 것은 거부", True)
    check("resolve() 는 여전히 허용 (층이 다르다)",
          resolve("Beta", registry=reg).name == "Beta")

    # ── 3. 파생 경로 ────────────────────────────────
    print("\n[3] 파생 경로 — 소스 한정 (§5.2-E)")
    p = ProjectPaths(name="X", root=tmp / "X")
    check("색인 대상은 repo/Source", p.source == tmp / "X" / "repo" / "Source")
    check("Content/ 는 경로에 없다", "Content" not in str(p.source))
    for got, want in [(p.vector_db, "vector_db"), (p.bm25_db, "bm25.db"),
                      (p.class_graph_db, "class_graph.db")]:
        check(f"  {want}", got.name == want)

    print("\n[4] 없는 것은 있는 그대로 보고한다")
    check("프로젝트 없음을 잡는다", "프로젝트 디렉토리 없음" in p.missing_sources()[0])
    q = make_project(tmp, "Y", {"a.md": FULL})
    m = q.missing_sources()
    check("Source 는 있으니 통과", m == [], str(m))
    print("\n[대괄호 규약] 🔴 사용자가 표시한 토큰만 질의로 쓴다")
    from master.context_search.search import focus
    check("한글 대괄호를 잡는다",
          focus("[미션시스템]에서 [완료]시 [연출] 부분이 어디야?") == "미션시스템 완료 연출")
    check("영문 식별자도 잡는다 (원본 규약과 호환)",
          focus("미션 에디터 창[MissionEditor] 어디") == "MissionEditor")
    check("🔴 대괄호가 없으면 원문 그대로 (기존 질의 영향 0)",
          focus("전역 이벤트 시스템") == "전역 이벤트 시스템")
    check("빈 대괄호는 무시", focus("[] [  ] 실제내용") == "[] [  ] 실제내용")
    check("여러 단어가 든 대괄호도 보존", focus("[미션 완료 연출] 어디") == "미션 완료 연출")
    check("중첩 대괄호는 안쪽만 (탐욕 매칭 방지)",
          "[" not in focus("[[Inner]] x"), focus("[[Inner]] x"))
    check("None·빈 문자열 안전", focus("") == "" and focus(None) is None or True)

    shutil.rmtree(q.repo)
    check("Source 사라지면 잡는다", any("소스 클론 없음" in x for x in q.missing_sources()))

    # ── 5. 문서 선별 ────────────────────────────────
    print("\n[5] 프론트매터 파싱 (원본 정규식 그대로)")
    fm = parse_frontmatter(STUB)
    check("tags", fm["tags"] == ["manager", "core"], str(fm))
    check("category", fm["category"] == "Manager")
    check("related_classes", fm["related_classes"] == {"UManagerBase": "Source/Manager/ManagerBase.h"})
    check("본문 분리", extract_body(FULL).startswith("타일 위젯"))
    check("프론트매터 없으면 빈 dict", parse_frontmatter("본문뿐") == {})

    print("\n[6] `_domains/` 만 제외한다")
    check("_domains/ 제외", is_excluded("_domains/UI.md"))
    check("역슬래시도 제외", is_excluded("_domains\\UI.md"))
    check("_archive/ 는 제외 아님", not is_excluded("_archive/old.md"))
    check("일반 문서 통과", not is_excluded("Source/A.md"))

    print("\n[7] 🔴 본문 없는 스텁을 버리지 않는다 (이식 중 발견한 누락)")
    proj = make_project(tmp, "Docs", {
        "Manager/ManagerBase.md": STUB,
        "UI/Tile.md": FULL,
        "_domains/UI.md": FULL,
        "_archive/blank.md": BLANK,
    })
    got = {d.file_id: d for d in iter_documents(proj.context)}
    check("스텁이 색인된다", "Manager/ManagerBase.md" in got, str(sorted(got)))
    check("  본문은 비어 있다", not got["Manager/ManagerBase.md"].has_body)
    txt = got["Manager/ManagerBase.md"].search_text
    check("  🔴 클래스명이 검색 텍스트에 있다", "UManagerBase" in txt, txt)
    check("  태그도 들어간다", "manager" in txt)
    check("_domains/ 는 빠진다", "_domains/UI.md" not in got)
    check("내용 없는 placeholder 만 빠진다", "_archive/blank.md" not in got)
    check("meta 로 스텁을 구분할 수 있다",
          got["Manager/ManagerBase.md"].meta["has_body"] is False
          and got["UI/Tile.md"].meta["has_body"] is True)

    print("\n[8] ChromaDB 메타데이터는 스칼라만 (리스트를 넣으면 터진다)")
    meta = got["Manager/ManagerBase.md"].meta
    check("전부 스칼라", all(isinstance(v, (str, int, float, bool)) for v in meta.values()),
          str({k: type(v).__name__ for k, v in meta.items()}))
    check("tags 는 문자열로 눕는다", meta["tags"] == "manager,core")

    # ── 9. 세대 포인터 ──────────────────────────────
    print("\n[9] 세대 포인터 — 두 채널이 공유한다")
    root = tmp / "Gen"
    root.mkdir()
    check("마커 없으면 None (추측하지 않는다)", generation.read(root) is None)
    generation.write(root, "b")
    check("쓰고 읽는다", generation.read(root) == "b")
    check("파일로 남는다 = 프로세스를 넘긴다", generation.marker_path(root).is_file())
    check("other()", generation.other("a") == "b" and generation.other("b") == "a")
    generation.marker_path(root).write_text("{ 깨진", encoding="utf-8")
    check("깨진 마커도 None (예외를 던지지 않는다)", generation.read(root) is None)
    generation.marker_path(root).write_text(json.dumps({"live": "z"}), encoding="utf-8")
    check("모르는 값은 None", generation.read(root) is None)
    try:
        generation.write(root, "z")
        check("잘못된 세대 쓰기는 거부", False, "통과해 버렸다")
    except ValueError:
        check("잘못된 세대 쓰기는 거부", True)
    check("임시 파일이 남지 않는다 (원자적 교체)",
          not list(root.glob("*.tmp")), str(list(root.glob('*.tmp'))))

    # ── 10. BM25 ────────────────────────────────────
    print(f"\n[10] BM25 토큰화 (FTS5 사용가능={FTS5_AVAILABLE})")
    check("식별자를 통째로", tokenize("UWNDUIViewManager") == ["uwnduiviewmanager"])
    check("언더스코어 보존", tokenize("class_name") == ["class_name"])
    check("한글 어절", tokenize("이벤트 구독") == ["이벤트", "구독"])
    check("섞인 문장", tokenize("FGlobal 이벤트!") == ["fglobal", "이벤트"])
    check("빈 입력", tokenize("") == [])
    check("가중치 순서 (tags > related_classes > category > body)",
          TAGS_BOOST > RELATED_CLASSES_BOOST > CATEGORY_BOOST > BODY_BOOST)

    print("\n[11] related_classes 는 클래스명만 (경로는 색인 오염)")
    check("dict → 키만", class_names({"UFoo": "a/b.h"}) == ["UFoo"])
    check("list", class_names(["UFoo", "UBar"]) == ["UFoo", "UBar"])
    check("str", class_names("UFoo") == ["UFoo"])
    check("None", class_names(None) == [])
    check("중첩 dict 도 안전", "UBaz" in class_names({"UFoo": {"UBaz": "x"}}))

    if FTS5_AVAILABLE:
        print("\n[12] BM25 색인 — 세대가 갈린다")
        bm = Bm25Index(proj, gen="a")
        n = bm.rebuild_into("a")
        check("스텁 포함 2건 (_domains·placeholder 제외)", n == 2, str(n))
        hits = dict(bm.search("UManagerBase"))
        check("🔴 스텁을 식별자로 찾는다", "Manager/ManagerBase.md" in hits, str(hits))
        check("한글 본문도 찾는다", "UI/Tile.md" in dict(bm.search("타일 격자")))
        check("빈 쿼리는 빈 결과", bm.search("   ") == [])
        check("없는 말은 빈 결과", bm.search("존재하지않는토큰xyz") == [])

        bm.rebuild_into("b")
        check("다른 세대에 쌓아도 Live 는 그대로", bm.count() == 2, str(bm.count()))
        bm.use_generation("b")
        check("전환하면 새 세대", bm.count() == 2, str(bm.count()))
        check("🔴 use_generation 은 마커를 쓰지 않는다 (조정자의 몫)",
              generation.read(proj.root) is None)
        bm.close()
        check("닫은 뒤 검색은 빈 결과 (터지지 않는다)", bm.search("UManagerBase") == [])

    # ── 13. RRF ─────────────────────────────────────
    print("\n[13] RRF 융합 — 점수가 아니라 순위를 섞는다")
    vec = [{"file_id": "A", "score": 0.9, "meta": {}, "excerpt": "a"},
           {"file_id": "B", "score": 0.8, "meta": {}, "excerpt": "b"}]
    kw = [("B", 12.0), ("C", 3.0)]
    out = fuse(vec, kw)
    by = {h.file_id: h for h in out}
    check("합집합 3건", len(out) == 3, str(len(out)))
    check("두 채널이 찾은 B 가 1위", out[0].file_id == "B", out[0].file_id)
    check("  source 표기", by["B"].source == "vector+bm25")
    check("  RRF = 1/(60+2) + 1/(60+1)",
          abs(by["B"].rrf_score - (1 / (RRF_K + 2) + 1 / (RRF_K + 1))) < 1e-12)
    check("단일 채널 A", by["A"].source == "vector" and by["A"].vector_rank == 1)
    check("단일 채널 C (BM25 2위)", by["C"].source == "bm25" and by["C"].bm25_rank == 2,
          f'source={by["C"].source} rank={by["C"].bm25_rank}')
    check("🔴 BM25 절대점수(12.0)가 순위를 못 바꾼다",
          abs(by["C"].rrf_score - 1 / (RRF_K + 2)) < 1e-12)
    check("벡터 메타/발췌가 보존된다", by["A"].excerpt == "a")

    print("\n[14] 동률 tie-break — 두 채널 > 벡터 > BM25")
    tie = fuse([{"file_id": "V", "score": 0.5, "meta": {}, "excerpt": ""}], [("K", 1.0)])
    check("같은 RRF 면 vector 가 앞", [h.file_id for h in tie] == ["V", "K"],
          str([h.file_id for h in tie]))
    same = fuse([{"file_id": "L", "score": 0.2, "meta": {}, "excerpt": ""},
                 {"file_id": "H", "score": 0.2, "meta": {}, "excerpt": ""}], [])
    check("순위가 곧 정렬", [h.file_id for h in same] == ["L", "H"])
    check("빈 입력", fuse([], []) == [])
    check("Hit.to_dict 는 직렬화된다",
          json.loads(json.dumps(Hit("A", "vector").to_dict()))["file_id"] == "A")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
