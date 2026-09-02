"""`#328` — 골조 **물음 → 사람의 답 → 적립 → 다음 프롬프트** 루프가 실제로 도나.

## [중요] 이 파일이 있는 이유

`heuristics.py` 는 설계·근거·범위 규약(`project`/`domain:<D>`/`once`)까지 다 갖춘 채
**한 번도 안 돌았다** (실측 2026-08-28):

    `register._fill_skeletons` 가 `built.questions` 를 **버렸다**  → 사람에게 닿을 길이 없다
    `H.add` 프로덕션 호출자 **0** · `<트윈>/skeleton-heuristics.md` **존재조차 안 함**

`#320`(상주)·`#327`(attempt)과 같은 부류 — **배선된 지도가 실물과 다르다.**
`~/CLAUDE.md` 의 *"모델의 제안을 답으로 적립하지 않는다"* 는 지켜진 것이 아니라 **그 자리가
비어 있었다.** 이 파일은 그 루프가 도는 것을 잰다.

## [중요] 방향이 반대다 — 그것이 규칙의 강제다

    나가는 것   `Registered.questions`  = **모델의 물음** (`Question`: topic·text·options)
    들어오는 것 `register_work(heuristics=…)` = **사람의 답** (`Heuristic`: topic·decision·scope)

타입이 갈라져 있고 `H.add` 가 `decision` 없는 것을 거부한다 — 모델의 물음은 구조적으로
적립될 수 없다.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths                     # noqa: E402
from master.work import heuristics as H                                  # noqa: E402
from master.work import register as REG                                  # noqa: E402
from master.work import skeleton as SK                                   # noqa: E402

_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail
    if ok:
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _paths(root: Path) -> ProjectPaths:
    return ProjectPaths(name="T", root=root)


def _poster(calls):
    def post(url, payload):
        calls.append((url, payload))
        if url.endswith("/works"):
            return {"work_id": "w1"}
        if "/works/" in url:
            return {"ok": True}
        return {"task_id": f"t{len(calls)}"}
    return post


def _fake_skeleton(questions=None):
    """`skeleton.build` 대역 — 물음을 낸다. 실제 LLM 을 안 태운다."""
    def build(paths, spec):
        s = SK.Skeleton(stem=spec.stem,
                        files={f"{spec.stem}.h": "// [PSEUDO:1] x\n"},
                        frozen={f"{spec.stem}::F"}, pseudo=1)
        s.questions = list(questions or [])
        s.notes.append(f"answers={len(spec.answers)}")
        return s
    return build


def test_questions_reach_the_result() -> None:
    """[중요] 완료 조건 1 — 종전에는 **버려졌다.**"""
    print("\n[1] 골조의 물음이 결과에 실린다 (완료 조건 1)")
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        q = H.Question(topic="스냅샷을 컴포넌트로?", options=["컴포넌트", "서브시스템"])
        calls: list = []
        got = REG.register_work("t", [REG.TaskSpec(stem="A", classes=["U"], instruction="만들어")],
                                paths=p, target_repo="r", poster=_poster(calls), make_skeleton=_fake_skeleton([q]))
        check("물음이 결과에 있다", got.questions and got.questions[0][0] == "A",
              str(got.questions))
        check("  요약이 크게 말한다", "물음 1건" in got.summary(), got.summary())
        check("  사람이 읽을 줄을 낸다",
              any("스냅샷을 컴포넌트로?" in ln for ln in got.question_lines()),
              str(got.question_lines()))
        check("[주의] 물음은 적립되지 않는다 (모델의 제안이다)",
              not H.path_for(p).exists(), "적립 파일이 생겼다")


def test_answers_accrue_with_scope() -> None:
    print("\n[2] 사람의 답이 적립된다 · scope 를 지킨다 (완료 조건 2·3)")
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        calls: list = []
        got = REG.register_work(
            "t", [REG.TaskSpec(stem="A", classes=["U"], instruction="만들어")],
            paths=p, target_repo="r", poster=_poster(calls),
            make_skeleton=_fake_skeleton(),
            heuristics=[
                {"topic": "상태 보관", "decision": "액터 수명에 묶이면 컴포넌트", "scope": "project"},
                {"topic": "미션 런타임", "decision": "틱 대신 이벤트", "scope": "domain:MissionRuntime"},
                {"topic": "이번 스냅샷", "decision": "컴포넌트로", "scope": "once"},
            ])
        items = H.load(p)
        topics = {h.topic for h in items}
        check("project 답이 적립된다", "상태 보관" in topics, str(topics))
        check("domain 답이 적립된다", "미션 런타임" in topics, str(topics))
        check("[중요] **once 는 적립되지 않는다**", "이번 스냅샷" not in topics, str(topics))
        check("  안 했다고 **말한다** (조용히 버리지 않는다)",
              any("once" in a for a in got.accrued), str(got.accrued))
        check("  요약에 적립 수가 드러난다", "휴리스틱 적립" in got.summary(), got.summary())


def test_once_reaches_this_skeleton_only() -> None:
    """[중요] `once` 는 적립 대신 **이번 골조 프롬프트**에 실린다."""
    print("\n[3] once 답이 이번 골조에 닿는다 (완료 조건 3)")
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        got = REG.register_work(
            "t", [REG.TaskSpec(stem="A", classes=["U"], instruction="만들어")],
            paths=p, target_repo="r", poster=_poster([]),
            make_skeleton=_fake_skeleton(),
            heuristics=[{"topic": "이번만", "decision": "컴포넌트로", "scope": "once"}])
        check("[중요] 골조가 그 답을 받았다 (SkeletonSpec.answers)",
              got.ok, got.summary())
        check("  적립 파일은 안 생긴다", not H.path_for(p).exists())


def test_accrual_is_before_skeleton() -> None:
    """[중요] 적립이 골조 생성보다 **먼저**여야 이번 프롬프트에 실린다."""
    print("\n[4] 순서 — 적립이 골조보다 먼저다")
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        seen: list = []

        def build(paths, spec):
            seen.append(len(H.load(paths)))          # 골조 만들 때 적립분이 보이나
            return SK.Skeleton(stem=spec.stem, files={"a.h": "// [PSEUDO:1]\n"},
                               frozen={"a::F"}, pseudo=1)

        REG.register_work("t", [REG.TaskSpec(stem="A", classes=["U"], instruction="x")],
                          paths=p, target_repo="r", poster=_poster([]),
                          make_skeleton=build,
                          heuristics=[{"topic": "T", "decision": "D", "scope": "project"}])
        check("[중요] 골조 생성 시점에 이미 적립돼 있다", seen == [1],
              f"{seen} — 0 이면 순서가 뒤집혀 이번 답이 이번 프롬프트에 안 실린다")


def test_bad_input_does_not_block_registration() -> None:
    print("\n[5] 적립 실패가 등록을 막지 않는다")
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        got = REG.register_work(
            "t", [REG.TaskSpec(stem="A", classes=["U"], instruction="x")],
            paths=p, target_repo="r", poster=_poster([]),
            make_skeleton=_fake_skeleton(),
            heuristics=[{"topic": "", "decision": ""}, "형식아님"])
        check("등록은 성공한다", got.ok, got.summary())
        check("[주의] 사유를 남긴다 (조용히 넘기지 않는다)",
              sum(1 for a in got.accrued if "[주의]" in a) == 2, str(got.accrued))


def test_accrued_reaches_the_next_prompt() -> None:
    """[중요] 완료 조건 6 의 왕복 — 적립분이 **다음 골조 프롬프트에 실제로** 들어가나.

    LLM 을 안 태우고 잰다: `H.render` 가 프롬프트에 실릴 블록을 만드는 자리이고,
    `applies_to` 가 도메인으로 거른다.
    """
    print("\n[6] 적립분이 다음 프롬프트에 실린다 · domain 이 걸러진다 (완료 조건 6)")
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        REG.register_work("t", [REG.TaskSpec(stem="A", classes=["U"], instruction="x")],
                          paths=p, target_repo="r", poster=_poster([]),
                          make_skeleton=_fake_skeleton(),
                          heuristics=[
                              {"topic": "전역", "decision": "컴포넌트로", "scope": "project"},
                              {"topic": "미션전용", "decision": "이벤트로",
                               "scope": "domain:MissionRuntime"},
                          ])
        items = H.load(p)
        check("적립분 2건이 읽힌다", len(items) == 2, str([h.topic for h in items]))

        # 이 작업이 MissionRuntime 이면 둘 다 실린다
        both = H.render(items, domains=["MissionRuntime"])
        check("[중요] 같은 도메인이면 둘 다 실린다",
              "전역" in both and "미션전용" in both, both[:200])

        # 다른 도메인이면 project 만 실린다
        only = H.render(items, domains=["UI"])
        check("[중요] **다른 도메인의 결정은 안 실린다**",
              "전역" in only and "미션전용" not in only, only[:200])

        # 도메인을 모르면 project 만
        none = H.render(items, domains=[])
        check("도메인 미상이면 project 만", "전역" in none and "미션전용" not in none, none[:200])

        check("  applies_to 가 같은 판정을 한다",
              [h.applies_to(["UI"]) for h in items] == [True, False],
              str([(h.topic, h.scope) for h in items]))


def main() -> int:
    for fn in (test_questions_reach_the_result, test_answers_accrue_with_scope,
               test_once_reaches_this_skeleton_only, test_accrual_is_before_skeleton,
               test_bad_input_does_not_block_registration,
               test_accrued_reaches_the_next_prompt):
        fn()
    total = 19
    print(f"\n{'OK' if not _fail else '[실패]'} test_heuristic_loop: {total - _fail}/{total} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
