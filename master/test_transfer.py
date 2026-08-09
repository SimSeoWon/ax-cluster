"""상태 익스포트/임포트 (소 2.4.3).

🔴 지키는 계약: **임포트는 덮어쓰기가 아니라 병합이다.** 우리 트리는 받은 스냅샷과 갈라져
있고(보호 표식 240건·별칭), 통째로 덮으면 그게 사라진다 — 재합성 경계에서 이미 겪은 문제다.

`.venv/bin/python master/test_transfer.py`
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths      # noqa: E402
from master import transfer as T                           # noqa: E402
from master.ontology import package as pkg, yaml_io        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _seed(root: Path, *, protect=True) -> ProjectPaths:
    p = ProjectPaths(name="T", root=root)
    pkg.write(p, "D", objects=[{"name": "UFoo", "layer": 1, "file": "Source/Foo.h"}],
              actions=[{"name": "Act", "layer": 2, "description": "설명"}])
    (root / "context").mkdir(parents=True, exist_ok=True)
    (root / "context" / "a.md").write_text("문서", encoding="utf-8")
    if protect:
        f = next((p.ontology / "domains" / "D").rglob("UFoo.yaml"))
        it = yaml_io.read(f)
        it.update({"protected": True, "protected_at": "c0ffee", "protected_reason": "스냅샷",
                   "aliases": ["푸"]})
        yaml_io.write(f, it)
    return p


def test_two_variants() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        out = Path(t) / "out"
        full, compat = T.export(p, out, variant="full"), T.export(p, out, variant="compat")
        with zipfile.ZipFile(full.path) as z:
            nf = z.namelist()
        with zipfile.ZipFile(compat.path) as z:
            nc = z.namelist()
            body = z.read("ontology_domains/L1/objects/UFoo.yaml"
                          if "ontology_domains/L1/objects/UFoo.yaml" in nc
                          else "ontology_domains/D/L1/objects/UFoo.yaml").decode()
        check("둘 다 README 를 동봉한다", "README.md" in nf and "README.md" in nc)
        check("둘 다 매니페스트가 있다", T.MANIFEST_NAME in nf and T.MANIFEST_NAME in nc)
        # 🔴 호환본은 우리 필드를 뺀다 — 원본이 모르는 키다
        check("🔴 compat 에 protected 가 없다", "protected" not in body, body[:120])
        # ⚠️ aliases 는 원본의 필드다 — 빼면 안 된다
        check("⚠️ compat 도 aliases 는 남긴다", "aliases" in body, body[:160])
        check("제거 수를 센다", compat.stripped == 3, str(compat.stripped))


def test_import_is_a_merge() -> None:
    """🔴 이것이 이 모듈의 존재 이유다."""
    with tempfile.TemporaryDirectory() as t:
        src = _seed(Path(t) / "src", protect=False)          # 상대가 보낸 것 (표식 없음)
        z = T.export(src, Path(t) / "out", variant="compat").path

        dst = _seed(Path(t) / "dst", protect=True)           # 우리 (표식 있음)
        plan = T.import_(dst, z)
        check("계획이 이월 대상을 센다", len(plan.carried) == 1, str(plan.carried))
        check("🔴 계획은 아무것도 안 쓴다", not plan.applied)

        done = T.import_(dst, z, apply=True, backup_dir=Path(t) / "bk")
        it = yaml_io.read(next((dst.ontology / "domains" / "D").rglob("UFoo.yaml")))
        check("🔴 보호 표식이 살아남는다", it.get("protected") is True, str(it))
        check("🔴 기준 커밋도 살아남는다", it.get("protected_at") == "c0ffee", str(it))
        check("🔴 별칭도 살아남는다", it.get("aliases") == ["푸"], str(it))
        check("들어온 내용은 반영된다", it.get("file") == "Source/Foo.h", str(it))
        check("백업을 남긴다", done.backup and Path(done.backup).is_dir(), done.backup)
        check("재색인이 필요하다고 말한다", any("rebuild" in n for n in done.notes), str(done.notes))


def test_incoming_wins_when_present() -> None:
    """들어온 쪽에 값이 있으면 그쪽을 존중한다 — 이월은 **빈 자리만** 채운다."""
    with tempfile.TemporaryDirectory() as t:
        src = _seed(Path(t) / "src", protect=True)
        z = T.export(src, Path(t) / "out", variant="full").path
        dst = _seed(Path(t) / "dst", protect=True)
        f = next((dst.ontology / "domains" / "D").rglob("UFoo.yaml"))
        it = yaml_io.read(f); it["aliases"] = ["우리것"]; yaml_io.write(f, it)
        T.import_(dst, z, apply=True, backup_dir=Path(t) / "bk")
        got = yaml_io.read(f).get("aliases")
        check("들어온 값이 이긴다", got == ["푸"], str(got))


def test_never_deletes_ours() -> None:
    """🔴 zip 에 없는 우리 항목을 지우지 않는다 — 안 보낸 건지 지운 건지 모른다."""
    with tempfile.TemporaryDirectory() as t:
        src = _seed(Path(t) / "src", protect=False)
        z = T.export(src, Path(t) / "out", variant="compat").path
        dst = _seed(Path(t) / "dst")
        extra = dst.ontology / "domains" / "D" / "L1" / "objects" / "UOnlyHere.yaml"
        yaml_io.write(extra, {"name": "UOnlyHere", "layer": 1})
        plan = T.import_(dst, z, apply=True, backup_dir=Path(t) / "bk")
        check("🔴 우리 것을 지우지 않는다", extra.is_file())
        check("세어서 보고한다", any("UOnlyHere" in x for x in plan.removed_here),
              str(plan.removed_here))
        check("요약에 남긴다", "남겨 둔다" in plan.summary, plan.summary)


def test_guards() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        try:
            T.export(p, Path(t) / "o", variant="bogus")
            check("variant 검사", False)
        except ValueError:
            check("variant 검사", True)
        try:
            T.import_(p, Path(t) / "없는.zip")
            check("없는 zip 은 예외", False)
        except RuntimeError as e:
            check("없는 zip 은 예외", "zip 이 없다" in str(e), str(e)[:40])


def main() -> int:
    for fn in (test_two_variants, test_import_is_a_merge, test_incoming_wins_when_present,
               test_never_deletes_ours, test_guards):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_transfer: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
