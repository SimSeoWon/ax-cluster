"""도메인 생성 — 씨앗 MD (소 1.3.1).

지키는 계약: [중요] **덮지 않는다 · 이름을 고쳐 주지 않는다 · 멤버십을 추측하지 않는다.**

`.venv/bin/python master/test_ontology_create.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths          # noqa: E402
from master.ontology import create as C, domain_md            # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_name_rules() -> None:
    """[중요] 규칙은 원전과 같다 — 경로 위험문자만 거부, 한글 허용 (#194 지점 5, 사용자 ⓐ).

    이 자리에 있던 「비ASCII 거부」는 허위 인용("원본이 거부한다") 위의 검사였다 — 원전
    실물(domain.py:546)은 한글을 통과시킨다. 조용한 정규화 금지는 그대로다.
    """
    check("PascalCase 통과", C.validate_name("MissionRuntime") == "MissionRuntime")
    check("[중요] 한글 도메인명 통과 (원전 규칙 · 사용자 결정 ⓐ)",
          C.validate_name("미션런타임") == "미션런타임")
    for bad, why in (("", "빈 이름"), ("미션/런타임", "경로 구분자"), ("a b", "공백"),
                     ('x"y', "따옴표"), ("t:t", "콜론")):
        try:
            C.validate_name(bad)
            check(f"[중요] {why} 거부", False, f"{bad!r} 를 받았다")
        except C.CreateError as e:
            check(f"[중요] {why} 거부", True, str(e)[:40])
    try:
        C.validate_name("미션")
    except C.CreateError as e:
        # [중요] 거부만 하지 말고 어디에 넣으라고 알려준다
        check("한글은 어디에 넣을지 알려준다", "별칭" in str(e) and "태그" in str(e), str(e)[:80])


def test_creates_seed() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = ProjectPaths(name="T", root=Path(t))
        r = C.create(p, "Inventory", tags=["인벤토리", "UI"], summary="아이템 보관")
        f = C.md_path(p, "Inventory")
        check("파일이 생긴다", f.is_file(), str(f))
        txt = f.read_text(encoding="utf-8")
        check("[중요] draft 로 시작한다", "status: draft" in txt, txt[:120])
        check("태그가 들어간다", "인벤토리" in txt, txt[:120])
        check("개요가 들어간다", "아이템 보관" in txt)
        # [중요] 실측: 7개 중 6개에 이 절이 없어서 합성이 남의 클래스를 끌어왔다
        check("[중요] 도메인 경계 절을 만든다", "## 도메인 경계" in txt)
        check("경계를 왜 채워야 하는지 적는다", "끌어온다" in txt, txt[:400])
        check("태그가 없으면 그렇게 알려준다",
              any("한글 태그" in n for n in C.create(p, "Bare").notes))

        # [중요] 우리 파서와 왕복돼야 한다 — 안 그러면 만든 문서를 합성이 못 읽는다
        doc = domain_md.parse_text(f.read_text(encoding="utf-8"), domain="Inventory")
        check("[중요] 파서가 개요를 읽는다", "아이템 보관" in (doc.summary or ""), str(doc.summary)[:60])
        # [중요] 씨앗의 절 이름이 파서의 정규 매핑과 어긋나면 만든 문서를 합성이 못 읽는다
        check("[중요] missing 에 경계가 없다 (자리를 만들었다)",
              "boundary" not in (getattr(doc, "missing", []) or []), str(getattr(doc, "missing", None)))


def test_never_overwrites() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = ProjectPaths(name="T", root=Path(t))
        C.create(p, "Inventory")
        C.md_path(p, "Inventory").write_text("사람이 쓴 내용\n", encoding="utf-8")
        try:
            C.create(p, "Inventory")
            check("[중요] 이미 있으면 덮지 않는다", False, "덮었다")
        except C.CreateError as e:
            check("[중요] 이미 있으면 덮지 않는다", "덮지 않는다" in str(e), str(e)[:60])
        check("내용이 그대로다",
              C.md_path(p, "Inventory").read_text(encoding="utf-8") == "사람이 쓴 내용\n")


def test_parent() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = ProjectPaths(name="T", root=Path(t))
        try:
            C.create(p, "Child", parent="없는상위")
            check("비ASCII 상위는 거부", False)
        except C.CreateError:
            check("비ASCII 상위는 거부", True)
        try:
            C.create(p, "Child", parent="Missing")
            check("[중요] 없는 상위는 거부", False, "조용히 받았다")
        except C.CreateError as e:
            check("[중요] 없는 상위는 거부", "먼저 만들어라" in str(e), str(e)[:60])

        C.create(p, "Parent")
        r = C.create(p, "Child", parent="Parent")
        txt = C.md_path(p, "Child").read_text(encoding="utf-8")
        check("frontmatter 에 상위가 남는다", "parent_domain: Parent" in txt, txt[:160])
        # 패키지가 아직 없으니 계층 연결은 보류돼야 한다 — 실패가 아니라 상태다
        check("패키지 없으면 연결 보류를 알린다",
              (not r.linked) and any("보류" in n for n in r.notes), r.summary)


def main() -> int:
    for fn in (test_name_rules, test_creates_seed, test_never_overwrites, test_parent):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_ontology_create: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
