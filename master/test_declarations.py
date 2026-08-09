"""생성 프롬프트의 선언부 (레드마인 #26).

🔴 지키는 계약: **못 실은 것을 조용히 빼지 않는다.** 말없이 생략하면 모델이 *"선언부에
없으니 지어내도 되겠다"* 로 읽어, 고치려던 실패가 그대로 돌아온다.

`.venv/bin/python master/test_declarations.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import declarations as D            # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def test_render_states_the_rule() -> None:
    d = D.Declarations(blocks=[("UFoo", "Source/Foo.h", "class UFoo { int32 Step; };")])
    r = d.render()
    # 🔴 실측된 실패는 한 글자 차이였다(CurrentStep vs Step) — 베끼라고 명시해야 한다
    check("정확히 베끼라고 말한다", "COPY THESE NAMES EXACTLY" in r, r[:80])
    check("🔴 없으면 지어내지 말라고 말한다", "do NOT invent" in r, r[:200])
    check("헤더 경로를 밝힌다", "Source/Foo.h" in r)
    check("본문이 실린다", "int32 Step" in r)


def test_missing_is_never_silent() -> None:
    """🔴 이것이 이 모듈의 핵심 계약이다."""
    d = D.Declarations(blocks=[("UFoo", "f.h", "x")], missing=["UBar", "UBaz"])
    r = d.render()
    check("🔴 못 찾은 것을 본문에 적는다", "NOT AVAILABLE" in r and "UBar" in r, r[-200:])
    check("요약에도 뜬다", "헤더 없음 2" in d.summary, d.summary)

    t = D.Declarations(blocks=[("UFoo", "f.h", "x")], truncated=["UFoo"])
    check("잘린 것도 적는다", "TRUNCATED" in t.render() and "UFoo" in t.render())
    o = D.Declarations(blocks=[("UFoo", "f.h", "x")], dropped=["UQux"])
    check("예산에 못 실은 것도 적는다", "OMITTED" in o.render() and "UQux" in o.render())

    # 아무것도 못 실었으면 그 사실만이라도 남아야 한다
    only = D.Declarations(missing=["UBar"])
    check("🔴 전부 못 찾아도 침묵하지 않는다", "UBar" in only.render(), only.render()[:120])
    check("아무 정보도 없으면 빈 문자열", D.Declarations().render() == "")


def test_budget() -> None:
    """예산은 실측 근거다 — 프롬프트 2,824tok · 여유 5,368tok (리포트 11 §14)."""
    check("클래스당 상한", D.PER_CLASS == 1500, str(D.PER_CLASS))
    check("전체 상한이 여유 안", D.TOTAL == 6000 and D.TOTAL / 2.85 < 5368, str(D.TOTAL))
    check("클래스당 ≤ 전체", D.PER_CLASS <= D.TOTAL)


def test_read_only() -> None:
    """🔴 프롬프트를 만드는 모듈이 파일을 쓰면 안 된다."""
    src = (Path(__file__).resolve().parent / "work" / "declarations.py").read_text("utf-8")
    for banned in (".write_text(", ".unlink(", "yaml_io.write", "mkdir("):
        check(f"🔴 {banned} 없음", banned not in src)


def test_prompt_places_it_last() -> None:
    """🔴 베낄 텍스트가 지시에서 멀수록 모델은 기억에서 꺼낸다."""
    import importlib
    G = importlib.import_module("master.work.generate")   # 함수가 모듈을 가린다
    p = G.build_prompt(manifest_body="MANIFEST-BODY", instruction="DO-THIS",
                       target_file="a.h", declarations="DECL-BLOCK")
    check("선언부가 매니페스트보다 뒤", p.index("DECL-BLOCK") > p.index("MANIFEST-BODY"), "순서")
    check("🔴 선언부가 TASK 앞", p.index("DECL-BLOCK") < p.index("DO-THIS"), "순서")
    check("안 주면 안 넣는다",
          "DECL" not in G.build_prompt(manifest_body="M", instruction="T"))


def main() -> int:
    for fn in (test_render_states_the_rule, test_missing_is_never_silent, test_budget,
               test_read_only, test_prompt_places_it_last):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_declarations: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
