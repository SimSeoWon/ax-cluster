"""도메인 뷰어 (소 2.4.2).

🔴 지키는 계약: **자립형** · **매니페스트를 믿지 않고 파일을 훑는다** · **결손을 첫 화면에.**
숫자를 예쁘게 보여주는 것보다 *판단에 필요한 것*을 보이게 하는 게 이 뷰어의 값이다.

`.venv/bin/python master/test_view.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths      # noqa: E402
from master.ontology import package as pkg, view as V, yaml_io  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _seed(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="T", root=root)
    pkg.write(p, "D", objects=[{"name": "UFoo", "layer": 1, "file": "Source/Foo.h"}],
              invariants=[{"name": "Rule", "layer": 2, "text": "규칙 본문"}])
    return p


def test_self_contained() -> None:
    """🔴 CDN 을 물면 인터넷 없는 자리에서 빈 화면이 된다 — 이 클러스터는 LAN 이 전제다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        h = V.render(p, V.collect(p))
        for bad in ("http://", "https://", "<script src", "<link "):
            check(f"🔴 외부 자원 없음: {bad!r}", bad not in h)
        check("CSS 가 인라인", "<style>" in h)
        check("JS 가 인라인", "<script>" in h and "src=" not in h.split("<script>")[1][:80])
        check("한국어 문서로 선언", 'lang=ko' in h and "charset=utf-8" in h)


def test_reads_files_not_manifest() -> None:
    """🔴 이게 실제로 결함을 잡았다 — 스냅샷에 manifest 에 없는 object yaml 이 있었다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        d = p.ontology / "domains" / "D"
        yaml_io.write(d / "L3/objects/UOrphan.yaml", {"name": "UOrphan", "layer": 3})
        doms = V.collect(p)
        names = {i.name for i in doms[0].items}
        check("🔴 목록에 없어도 읽는다", "UOrphan" in names, str(names))
        check("🔴 고아라고 표시한다", any("UOrphan" in o for o in doms[0].orphans),
              str(doms[0].orphans))
        h = V.render(p, doms)
        # 🔴 색인·sync 는 manifest 를 근거로 삼으므로 이건 검색에서 빠져 있다
        check("첫 화면에 경고한다", "manifest 에 없는 항목 파일" in h, h[:600])
        check("무엇이 문제인지 말한다", "검색에도 동기화에도 빠져" in h)


def test_boundary_warning() -> None:
    """경계가 없으면 합성이 다른 도메인의 클래스를 끌어온다(실측 7개 중 6개)."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        h = V.render(p, V.collect(p))
        check("🔴 경계 없음을 첫 화면에", "도메인 경계 절이 없는 도메인" in h, h[:500])
        check("왜 문제인지 적는다", "다른 도메인의 클래스를 끌어올" in h)

        d = p.ontology / "domains" / "D"
        man = yaml_io.read(d / "domain.yaml"); man["boundary"] = "여기까지가 이 도메인"
        yaml_io.write(d / "domain.yaml", man)
        h2 = V.render(p, V.collect(p))
        check("있으면 경고하지 않는다", "경계 절이 없는" not in h2)
        check("있다고 표시한다", "경계 있음" in h2)


def test_shows_provenance() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        f = next((p.ontology / "domains" / "D").rglob("Rule.yaml"))
        it = yaml_io.read(f)
        it.update({"protected": True, "protected_at": "abc12345" * 5,
                   "protected_reason": "스냅샷"})
        yaml_io.write(f, it)
        h = V.render(p, V.collect(p))
        check("🔒 보호를 보여준다", "🔒 보호" in h, h[-400:])
        # 🔴 드리프트를 보려면 **언제 기준인지**가 있어야 한다
        check("🔴 기준 커밋을 보여준다", "abc12345" in h)
        check("본문도 보여준다", "규칙 본문" in h)


def test_write_is_read_only_for_ontology() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        before = {f: f.stat().st_mtime_ns for f in (p.ontology).rglob("*.yaml")}
        out, n = V.write(p)
        check("파일을 쓴다", out.is_file() and n > 0, str(out))
        after = {f: f.stat().st_mtime_ns for f in (p.ontology).rglob("*.yaml")}
        check("🔴 온톨로지는 안 건드린다", before == after)
        try:
            V.write(ProjectPaths(name="X", root=Path(t) / "none"))
            check("도메인이 없으면 예외", False, "조용히 빈 파일을 만들었다")
        except RuntimeError as e:
            check("도메인이 없으면 예외", "볼 것이 없다" in str(e), str(e)[:50])


def main() -> int:
    for fn in (test_self_contained, test_reads_files_not_manifest, test_boundary_warning,
               test_shows_provenance, test_write_is_read_only_for_ontology):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_view: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
