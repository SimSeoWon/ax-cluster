"""시소러스 질의 확장 (소 2.2.1).

🔴 지키는 계약 둘: **원본을 지우지 않는다** · **조용히 바꾸지 않는다.**
확장이 틀렸을 때 원래 질의가 남아 있어야 0건으로 떨어지지 않고, 무엇을 붙였는지 보이지
않으면 사람이 색인이나 가중치를 의심한다 — 원인은 여기인데.

`.venv/bin/python master/test_expand.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search import expand as X       # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


@dataclass
class A:
    term: str
    class_name: str


def _al(*pairs):
    return {t.casefold(): A(t, c) for t, c in pairs}


def test_particles() -> None:
    """🔴 한국어엔 조사가 붙는다 — 토큰 일치로는 못 잡는다."""
    al = _al(("몬스터", "AMonster"))
    e = X.expand("몬스터를 스폰한다", al)
    check("🔴 조사가 붙어도 찾는다", e.changed and "AMonster" in e.query, e.query)
    check("🔴 원본을 지우지 않는다", "몬스터를 스폰한다" in e.query, e.query)
    check("무엇을 왜 붙였는지 말한다", "몬스터→AMonster" in e.note, e.note)
    check("안 걸리면 그대로", not X.expand("전혀 다른 말", al).changed)


def test_short_terms_are_dangerous() -> None:
    """🔴 한 글자 별칭은 어디에나 들어간다 — 부분 문자열 매칭의 대가다."""
    al = _al(("적", "AEnemy"), ("몬스터", "AMonster"))
    e = X.expand("목적지 설정", al)          # 「적」이 「목적지」에 들어 있다
    check("🔴 짧은 별칭은 확장하지 않는다", not e.changed, e.query)
    check("건너뛴 것을 기록한다", "적" in e.skipped_short, str(e.skipped_short))


def test_cap_and_specificity() -> None:
    al = _al(*[(f"말{i}", f"UClass{i}") for i in range(10)])
    q = " ".join(f"말{i}" for i in range(10))
    e = X.expand(q, al)
    # 🔴 확장은 거들 뿐 — 질의를 대체하지 않는다
    check("🔴 개수 상한이 있다", len(e.added) == X.MAX_EXPAND, str(len(e.added)))
    check("생략한 수를 적는다", e.capped == 4 and "생략" in e.note, e.note)

    # 긴 별칭이 더 구체적이다
    al2 = _al(("태스크", "UTask"), ("미션 태스크", "UMissionTask"))
    e2 = X.expand("미션 태스크 실행", al2)
    check("🔴 구체적인 것이 먼저다", e2.added[0][1] == "UMissionTask", str(e2.added))


def test_no_duplicate_noise() -> None:
    al = _al(("몬스터", "AMonster"))
    e = X.expand("AMonster 를 고친다 몬스터", al)
    check("🔴 이미 질의에 있는 식별자는 안 붙인다", not e.changed, e.query)

    al2 = _al(("몬스터", "AMonster"), ("몹", "AMonster"))
    e2 = X.expand("몬스터 몹", al2)
    check("같은 클래스는 한 번만", e2.query.count("AMonster") == 1, e2.query)


def test_never_breaks_search() -> None:
    """🔴 확장 실패가 검색을 막으면 안 된다."""
    check("별칭이 없으면 원본", X.expand("질의", {}).query == "질의")
    check("빈 질의는 빈 채로", X.expand("", _al(("a", "B"))).query == "")
    bad = X.expand("몬스터", {"몬스터": A("몬스터", "")})     # class 가 빈 별칭
    check("클래스가 없는 별칭은 무시", not bad.changed, bad.query)

    class Boom:
        def __getattr__(self, k):
            raise RuntimeError("boom")
    got = X.expand_for(Boom(), "몬스터")        # paths 가 이상해도
    check("🔴 예외가 검색을 막지 않는다", got.query == "몬스터", got.query)


def main() -> int:
    for fn in (test_particles, test_short_terms_are_dangerous, test_cap_and_specificity,
               test_no_duplicate_noise, test_never_breaks_search):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_expand: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
