"""골조 휴리스틱 — 대화형 수집 (소 1.1.6).

🔴 지키는 계약: **사람이 답한 것만 적립된다.** 모델의 제안을 적립하면 다음 골조가 자기 말을
근거로 같은 선택을 반복한다 — 온톨로지 자동 승급을 껐던 것과 같은 이유.

`.venv/bin/python master/test_heuristics.py`
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import heuristics as H      # noqa: E402
from master.work import skeleton as S        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


@dataclass
class P:
    root: Path


def test_questions_are_parsed_loosely() -> None:
    """형식을 조금 어겨도 질문을 잃지 않는다 — 잃는 것이 더 나쁘다."""
    raw = ("=== FILE: a.h ===\nclass A {};\n"
           "=== QUESTIONS ===\n"
           "- Should snapshots be a component or a subsystem?\n"
           "* Is tick needed? vs event-driven\n"
           "1. Should we cap the stack size?\n"
           "=== END QUESTIONS ===")
    qs = H.parse_questions(raw)
    check("셋 다 읽는다", len(qs) == 3, str([q.topic for q in qs]))
    check("불릿·번호를 뗀다", qs[0].topic.startswith("Should snapshots"), qs[0].topic)
    check("선택지를 살린다", qs[1].options and "event-driven" in qs[1].options[-1],
          str(qs[1].options))


def test_no_block_means_no_questions() -> None:
    """🔴 블록이 없으면 **지어내지 않는다.**"""
    check("빈 목록", H.parse_questions("=== FILE: a.h ===\nclass A {};") == [])
    check("빈 입력도 안전", H.parse_questions("") == [])


def test_questions_never_leak_into_files() -> None:
    """🔴 질문이 파일 본문에 섞이면 그대로 워커에게 배달된다."""
    raw = ("=== FILE: Source/A.h ===\nclass A {};\n"
           "=== QUESTIONS ===\n- Should A be final?\n")
    files, _notes = S.parse_files(raw, want=["Source/A.h"])
    body = files["Source/A.h"]
    check("파일에 질문이 안 섞인다", "QUESTIONS" not in body and "final?" not in body, body)
    check("본문은 살아 있다", "class A" in body, body)


def test_only_human_answers_are_stored() -> None:
    """🔴 적립되는 것은 사람의 답이다 — 주제·결정이 없으면 거부."""
    with tempfile.TemporaryDirectory() as d:
        paths = P(root=Path(d))
        check("처음엔 비어 있다", H.load(paths) == [])
        for bad in (H.Heuristic(topic="", decision="X"),
                    H.Heuristic(topic="T", decision="")):
            try:
                H.add(paths, bad)
                check("🔴 빈 휴리스틱은 거부", False)
            except ValueError:
                check("🔴 빈 휴리스틱은 거부", True)

        H.add(paths, H.Heuristic(topic="스냅샷은 컴포넌트인가 서브시스템인가",
                                 decision="컴포넌트", why="액터 수명에 묶여야 한다",
                                 at="b1ba6af0"))
        got = H.load(paths)
        check("적립된다", len(got) == 1, str(got))
        check("결정을 읽는다", got[0].decision == "컴포넌트", got[0].decision)
        check("이유를 읽는다", "액터 수명" in got[0].why, got[0].why)
        check("기준 커밋을 읽는다", got[0].at.startswith("b1ba6af"), got[0].at)
        check("사람이 답한 것만이라고 파일에 적는다",
              "사람이 답한 것만" in H.path_for(paths).read_text(encoding="utf-8"))


def test_second_answer_appends_not_overwrites() -> None:
    """🔴 판단이 바뀐 것도 기록이다 — 옛 결정을 조용히 지우지 않는다."""
    with tempfile.TemporaryDirectory() as d:
        paths = P(root=Path(d))
        H.add(paths, H.Heuristic(topic="틱", decision="쓴다"))
        H.add(paths, H.Heuristic(topic="틱", decision="안 쓴다", why="이벤트로 바꿨다"))
        got = H.load(paths)
        check("둘 다 남는다", len(got) == 2, str([(g.topic, g.decision) for g in got]))
        check("나중 것이 뒤에", got[-1].decision == "안 쓴다", got[-1].decision)


def test_render_prefers_recent_and_says_what_it_cut() -> None:
    """🔴 잘랐으면 잘랐다고 적는다 — 조용히 빼면 '그런 결정은 없다' 로 읽힌다."""
    items = [H.Heuristic(topic=f"T{i}", decision="D" * 200) for i in range(10)]
    text = H.render(items, budget=600)
    check("최근 것이 실린다", "T9" in text, text[:200])
    check("오래된 것은 잘린다", "T0" not in text)
    check("🔴 잘랐다고 말한다", "omitted for budget" in text, text[-200:])
    check("여전히 유효하다고 말한다", "still stand" in text)
    check("사람의 결정이라고 못박는다", "human decisions, not suggestions" in text)
    check("빈 목록은 빈 문자열", H.render([]) == "")


def test_prompt_puts_heuristics_first() -> None:
    """🔴 이미 내려진 사람의 결정이라 다른 재료보다 위다."""
    spec = S.SkeletonSpec(stem="F", files=["a.h"], classes=["UF"], instruction="만든다")
    p = S.build_prompt(spec, heuristics_text="=== HEURISTICS ===\nX",
                       norms="=== DOMAIN NORMS ===\nY",
                       declarations="=== DECLARATIONS ===\nZ")
    check("휴리스틱이 규범보다 앞", p.index("HEURISTICS") < p.index("DOMAIN NORMS"))
    check("규범이 선언부보다 앞", p.index("DOMAIN NORMS") < p.index("DECLARATIONS"))
    # 🔴 질문을 요구하되, 그것 때문에 파일을 바꾸지는 말라고 해야 한다
    check("질문 블록을 요구한다", "=== QUESTIONS ===" in p)
    check("🔴 주인이 정한다고 못박는다", "the owner decides" in p, "")


def main() -> int:
    for fn in (test_questions_are_parsed_loosely, test_no_block_means_no_questions,
               test_questions_never_leak_into_files, test_only_human_answers_are_stored,
               test_second_answer_appends_not_overwrites,
               test_render_prefers_recent_and_says_what_it_cut,
               test_prompt_puts_heuristics_first):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_heuristics: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
