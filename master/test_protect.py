"""보호 표식 일괄 (레드마인 #24 후속).

🔴 지키는 계약: **`verified_by_user` 와 섞지 않는다.** 뜻이 다르고, 섞으면 둘 다 못 쓴다.

    verified_by_user   사람이 이 항목을 **검수했다**            한 건씩
    protected          이 내용을 **재생성으로 대체하지 않는다**   출처가 근거 · 일괄

`.venv/bin/python master/test_protect.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths          # noqa: E402
from master.ontology import edit as E, package as pkg, yaml_io  # noqa: E402

PASS = FAIL = 0
WHY = "받아온 스냅샷 — 재생산 불가"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _seed(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="T", root=root)
    pkg.write(p, "D",
              objects=[{"name": "AMonster", "layer": 1, "file": "m.h"}],
              actions=[{"name": "Spawn", "layer": 2, "description": "스냅샷 설명"},
                       {"name": "Kill", "layer": 2, "description": "스냅샷 설명2"}])
    return p


def test_plan_then_apply() -> None:
    """🔴 일괄이라 더 위험하다 — 기본은 계획만 (`sync`·`cleanup` 과 같은 규칙)."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        plan = E.protect_all(p, reason=WHY)
        check("계획은 세운다", len(plan.changed) == 3, str(plan.summary))
        check("🔴 계획은 아무것도 안 쓴다", not E.protected_items(p), str(E.protected_items(p)))
        check("계획이라고 말한다", plan.summary.startswith("계획"), plan.summary)

        done = E.protect_all(p, reason=WHY, apply=True)
        check("적용하면 표시된다", len(E.protected_items(p)) == 3, str(done.summary))
        again = E.protect_all(p, reason=WHY, apply=True)
        check("멱등하다 (이미 표시된 것은 안 센다)", again.already == 3 and not again.changed,
              again.summary)


def test_reason_is_required() -> None:
    """🔴 *왜* 보호하는지 없으면 다음 사람이 풀어도 되는지 판단할 수 없다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        try:
            E.protect_all(p, apply=True)
            check("🔴 사유 없이는 못 건다", False, "사유 없이 통과했다")
        except E.EditError as e:
            check("🔴 사유 없이는 못 건다", "사유" in str(e), str(e)[:50])
        # 푸는 데는 사유가 필요 없다 — 되돌리기를 막으면 안 된다
        E.protect_all(p, reason=WHY, apply=True)
        off = E.protect_all(p, on=False, apply=True)
        check("풀 때는 사유가 필요 없다", not E.protected_items(p), off.summary)


def test_not_the_same_as_verified() -> None:
    """🔴 이것이 이 기능의 존재 이유다 — 신호를 오염시키지 않는다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        E.protect_all(p, reason=WHY, apply=True)
        item = yaml_io.read(E.find_item(p, "D", "actions", "Spawn"))
        check("보호 표식이 붙는다", item.get(E.PROTECT_FIELD) is True, str(item))
        # 🔴 247건에 "사람이 검수했다" 를 찍으면 진짜 검수한 것을 구분할 수 없게 된다
        check("🔴 verified_by_user 는 건드리지 않는다",
              item.get(E.LOCK_FIELD) is not True, str(item))
        check("검수 잠금 목록은 비어 있다", E.locked_items(p) == [], str(E.locked_items(p)))
        check("사유가 파일에 남는다", WHY in str(item.get(E.PROTECT_WHY)), str(item))


def test_protection_survives_resynthesis() -> None:
    """🔴 효과는 검수 잠금과 같아야 한다 — 재합성이 덮지 않는다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        E.protect_all(p, reason=WHY, apply=True)
        pkg.write(p, "D", actions=[{"name": "Spawn", "layer": 2, "description": "합성이 새로 쓴 것"},
                                   {"name": "새것", "layer": 2, "description": "추가분"}])
        got = yaml_io.read(E.find_item(p, "D", "actions", "Spawn"))
        check("🔴 보호된 것은 안 덮인다", got["description"] == "스냅샷 설명", str(got))
        check("🔴 보호된 것은 안 지워진다 (prune 대상 밖)",
              E.find_item(p, "D", "actions", "Kill") is not None)
        check("새 항목은 그대로 들어온다", E.find_item(p, "D", "actions", "새것") is not None)


def test_selective() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        E.protect_all(p, kinds=("actions",), reason=WHY, apply=True)
        kinds = {r["kind"] for r in E.protected_items(p)}
        check("kind 를 고를 수 있다", kinds == {"actions"}, str(kinds))
        check("objects 는 안 걸렸다", E.find_item(p, "D", "objects", "AMonster") is not None
              and not (yaml_io.read(E.find_item(p, "D", "objects", "AMonster")) or {}).get(E.PROTECT_FIELD))


def main() -> int:
    for fn in (test_plan_then_apply, test_reason_is_required, test_not_the_same_as_verified,
               test_protection_survives_resynthesis, test_selective):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_protect: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
