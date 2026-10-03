"""`related_classes` 정규화 (`#382`) — 합성 산출물을 스키마 형태로 맞춘다.

검증하는 것:

    ① 🔴 **이름을 지어내지 않는다** — 클래스 그래프가 못 풀면 그 줄을 그대로 두고 **센다**
    ② 경로만 있는 줄 → `ClassName: path` (이름은 **그래프에서만**)
    ③ `<ClassName>: path` → 꺾쇠만 벗긴다 (이름은 이미 있다 — 형식 문제다)
    ④ 정상 줄·프론트매터 밖·본문은 **건드리지 않는다**
    ⑤ 못 푸는 부류를 **사유로 낸다** (`?` · `경로: 설명문` · 그래프에 없는 경로)
    ⑥ 보수(`repair`)는 **계획이 기본**이고 `--confirm` 이 쓴다

`python3 master/test_related.py`  (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.dont_write_bytecode = True

from master.context_synth import related as RL                              # noqa: E402

PASS = FAIL = 0
MAP = {"Source/NS/Interaction/NSInteractableComponent.h": "UNSInteractableComponent",
       "Source/NS/NSCharacter.h": "ANSCharacter"}


def check(name: str, cond: bool, got: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


def doc(items: str, body: str = "본문이다.\n") -> str:
    return ("---\ntags: [A, B]\ncategory: C/D\nrelated_classes:\n"
            f"{items}---\n\n{body}")


def test_names_come_from_the_graph_only() -> None:
    print("①② 이름은 그래프에서만 온다")
    t = doc("  - Source/NS/Interaction/NSInteractableComponent.h\n")
    new, fixed, unres = RL.normalize(t, MAP)
    check("경로만 있는 줄을 매핑형으로", "- UNSInteractableComponent: Source/NS/Interaction/"
          "NSInteractableComponent.h" in new, new[:200])
    check("  고친 줄 수를 센다", fixed == 1, str(fixed))

    # 🔴 stem 으로 지어내지 않는다 — 실제 클래스는 `U` 접두가 붙는다
    check("[중요] stem(`NSInteractableComponent`)을 쓰지 않았다",
          "- NSInteractableComponent:" not in new, new[:200])

    t2 = doc("  - Source/NS/Unknown/NotInGraph.h\n")
    new2, fixed2, unres2 = RL.normalize(t2, MAP)
    check("🔴 그래프가 못 풀면 **그대로 둔다**", new2 == t2 and fixed2 == 0)
    check("  그리고 센다 (조용히 버리지 않는다)",
          unres2 == ["Source/NS/Unknown/NotInGraph.h"], str(unres2))


def test_angle_brackets_are_a_format_problem() -> None:
    print("③ `<이름>: 경로` — 이름은 이미 있다")
    t = doc("  - <ACombatAIController>: Source/NS/Variant_Combat/AI/CombatAIController.h\n")
    new, fixed, _u = RL.normalize(t, MAP)
    check("꺾쇠만 벗긴다", "- ACombatAIController: Source/NS/Variant_Combat/AI/"
          "CombatAIController.h" in new, new[:220])
    check("  그래프에 없어도 고친다 (이름을 모델이 이미 줬다)", fixed == 1, str(fixed))

    t2 = doc("  - <AAIController>: ?\n")
    new2, fixed2, unres2 = RL.normalize(t2, MAP)
    check("[주의] 경로가 `?` 면 고치지 않는다 — 내용 문제다", fixed2 == 0 and new2 == t2)
    check("  사유에 실린다", unres2 and "?" in unres2[0], str(unres2))


def test_untouched_surfaces() -> None:
    print("④ 건드리지 않는 자리")
    ok_line = "  - ANSCharacter: Source/NS/NSCharacter.h\n"
    t = doc(ok_line)
    new, fixed, _u = RL.normalize(t, MAP)
    check("정상 줄은 그대로", new == t and fixed == 0)

    body = "본문에도 - Source/NS/Interaction/NSInteractableComponent.h 가 있다.\n"
    t2 = doc(ok_line, body=body)
    new2, _f, _u2 = RL.normalize(t2, MAP)
    check("[중요] 본문은 안 건드린다", body in new2 and new2 == t2, new2[-120:])

    check("프론트매터가 없으면 그대로", RL.normalize("본문뿐", MAP) == ("본문뿐", 0, []))
    check("그래프가 비면 아무것도 안 한다 (지어낼 재료가 없다)",
          RL.normalize(doc("  - Source/NS/NSCharacter.h\n"), {})[1] == 0)


def test_junk_is_reported_not_invented() -> None:
    print("⑤ 못 푸는 부류를 사유로 낸다")
    t = doc("  - ?\n  - Source/NS/NS.h: NS (이 파일 자체가 정의하는 것)\n")
    _new, fixed, unres = RL.normalize(t, MAP)
    check("`?` 도 `경로: 설명문` 도 안 고친다", fixed == 0, str(fixed))
    check("  둘 다 사유에 실린다", len(unres) == 2, str(unres))


def test_repair_plans_before_writing() -> None:
    print("⑥ 보수는 계획이 기본")
    tmp = Path(tempfile.mkdtemp(prefix="ax-related-"))
    try:
        ctx = tmp / "context" / "Source" / "NS"
        ctx.mkdir(parents=True)
        f = ctx / "NSCharacter.md"
        f.write_text(doc("  - Source/NS/NSCharacter.h\n"), encoding="utf-8")

        class P:
            name = "T"
        P.root, P.context = tmp, tmp / "context"
        paths = P()
        RL.file_to_class = lambda _p: MAP                    # 그래프 대신 고정 매핑
        RL.class_to_file = lambda _p: {}                     # `#712` 이름→경로 갈래도 고정 (빈 그래프)

        plan = RL.repair(paths)
        check("계획은 쓰지 않는다", plan["files"] == 1 and not plan["applied"]
              and "Source/NS/NSCharacter.h" in f.read_text(encoding="utf-8"), str(plan))
        done = RL.repair(paths, confirm=True)
        check("`--confirm` 이 쓴다", done["applied"] and "- ANSCharacter: Source/NS/NSCharacter.h"
              in f.read_text(encoding="utf-8"), f.read_text(encoding="utf-8")[:160])
        check("[중요] 멱등 — 두 번째는 고칠 것이 없다", RL.repair(paths, confirm=True)["fixed"] == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unknown_filled_only_by_exact_name() -> None:
    print("⑦ 🔴 `이름: ?` — 그래프에 **정확히 있는 이름만** 채운다 (#712)")
    names = {"TaskIndex": "master/task_queue/logic.py",
             "master.verdict.Verdict": "master/verdict.py"}
    src = doc("  - TaskIndex: ?\n  - Verdict: ?\n  - _tq_log: ?\n  - <TaskIndex>: ?\n")
    out, fixed, unres = RL.normalize(src, {}, names)
    check("정확히 있는 이름은 경로로", "- TaskIndex: master/task_queue/logic.py" in out, out)
    check("꺾쇠 변형도 같은 규칙", out.count("TaskIndex: master/task_queue/logic.py") == 2, out)
    check("[중요] 겹쳐서 모듈명이 붙은 짧은 이름은 **고르지 않는다**", "- Verdict: ?" in out, out)
    check("그래프에 없는 이름(함수)은 그대로", "- _tq_log: ?" in out, out)
    check("고친 줄 수", fixed == 2, str(fixed))
    out2, fixed2, _ = RL.normalize(src, {})
    check("names 를 안 주면 종전 그대로 (호환)", fixed2 == 0 and "- TaskIndex: ?" in out2, str(fixed2))


def main() -> int:
    for fn in (test_names_come_from_the_graph_only, test_angle_brackets_are_a_format_problem,
               test_untouched_surfaces, test_junk_is_reported_not_invented,
               test_repair_plans_before_writing, test_unknown_filled_only_by_exact_name):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_related: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
