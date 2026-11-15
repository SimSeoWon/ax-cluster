"""분류 문서 로더(`#960` T1) 계약 테스트 — 분류·단계는 **문서 머리말**에서 오고, 깨진 문서는 전체 거절.

실행: .venv/bin/python master/test_interview_categories.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import interview_categories as IC    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _doc(root: Path, name: str, fm: str, body: str = "# 안내\n\n본문\n") -> None:
    (root / f"category-{name}.md").write_text(f"---\n{fm}\n---\n\n{body}", encoding="utf-8")


def _rejects(root: Path, needle: str) -> bool:
    try:
        IC.load(root)
    except IC.CategoryError as e:
        return needle in str(e)
    return False


def test_real_docs():
    cats = IC.load()
    check("실제 분류 3종", sorted(cats) == ["bug", "feature", "modify"], str(sorted(cats)))
    check("버그는 재현 포함", cats["bug"].applies("reproduce"))
    check("신규·수정은 재현 없음", not cats["feature"].applies("reproduce") and not cats["modify"].applies("reproduce"))
    check("as_dict 의 skipped", cats["feature"].as_dict()["skipped"] == ["reproduce"], str(cats["feature"].as_dict()))
    check("label 이 있다", all(c.label for c in cats.values()))


def test_order_is_fixed_not_doc_order():
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        _doc(r, "x", "name: x\nlabel: 엑스\nsteps: [impact, specify, investigate]")
        check("순서는 고정 순서로 정렬", IC.load(r)["x"].steps == ("investigate", "specify", "impact"))


def test_adding_a_doc_adds_a_category():
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        _doc(r, "bug", "name: bug\nlabel: 버그\nsteps: [specify]")
        check("하나", list(IC.load(r)) == ["bug"])
        _doc(r, "port", "name: port\nlabel: 이식\nsteps: [investigate, specify, impact]")
        check("문서만 더하면 분류가 는다", sorted(IC.load(r)) == ["bug", "port"])


def test_broken_rejects_all():
    cases = [
        ("yaml", "name: x\nlabel: [깨짐\nsteps: [specify]", "YAML"),
        ("name-mismatch", "name: other\nlabel: 엑스\nsteps: [specify]", "파일 이름"),
        ("no-label", "name: no-label\nsteps: [specify]", "label"),
        ("bad-step", "name: bad-step\nlabel: 엑스\nsteps: [specify, guess]", "모르는 단계"),
        ("classify", "name: classify\nlabel: 엑스\nsteps: [classify, specify]", "모르는 단계"),
        ("dup", "name: dup\nlabel: 엑스\nsteps: [specify, specify]", "중복"),
        ("no-spec", "name: no-spec\nlabel: 엑스\nsteps: [investigate]", "필수 단계"),
        ("extra", "name: extra\nlabel: 엑스\nsteps: [specify]\nmode: fast", "모르는 머리말 키"),
    ]
    for name, fm, needle in cases:
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            _doc(r, "good", "name: good\nlabel: 정상\nsteps: [specify]")
            _doc(r, name, fm)
            check(f"깨진 문서({name}) → 전체 거절", _rejects(r, needle))
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        _doc(r, "empty", "name: empty\nlabel: 엑스\nsteps: [specify]", body="")
        check("본문 빈 문서 거절", _rejects(r, "본문"))
        (r / "category-nofm.md").write_text("# 머리말 없음\n", encoding="utf-8")
        check("머리말 없음 거절", _rejects(r, "머리말 없음"))
    with tempfile.TemporaryDirectory() as t:
        check("문서 0개 거절", _rejects(Path(t), "분류 문서가 없다"))


def test_get_unknown():
    try:
        IC.get("nope")
        ok = False
    except IC.CategoryError as e:
        ok = "모르는 분류" in str(e)
    check("모르는 분류 거절", ok)


def test_no_newline_after_frontmatter_969():
    """`#969` 14 (R397-5 · R389-1) — 닫는 `---` 뒤에 개행이 없어도 CategoryError(본문 빔)로 끝난다."""
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        (r / "category-nonl.md").write_text("---\nname: nonl\nlabel: 엑스\nsteps: [specify]\n---", encoding="utf-8")
        try:
            IC.load(r)
            got = "예외 없음"
        except IC.CategoryError as e:
            got = f"CategoryError: {e}"
        except Exception as e:                               # noqa: BLE001
            got = f"{type(e).__name__}: {e}"
        check("14 개행 없음 → CategoryError(본문)", got.startswith("CategoryError") and "본문" in got, got)


def main() -> int:
    for fn in (test_real_docs, test_order_is_fixed_not_doc_order, test_adding_a_doc_adds_a_category,
               test_broken_rejects_all, test_get_unknown, test_no_newline_after_frontmatter_969):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_interview_categories: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
