"""온톨로지 항목 편집 + 검수 잠금 (소 1.3.2 · 1.3.7).

지키는 계약: 🔴 **사람이 손댄 것은 재합성이 덮지 않는다. 그리고 손대지 않은 것을 만들지도
않는다.** 잠금 보존은 `package` 가 이미 하고 있었지만 **거는 경로가 없어 死코드였다** —
여기가 그 절반이다.

`.venv/bin/python master/test_ontology_edit.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths      # noqa: E402
from master.ontology import edit as E, package as pkg, yaml_io  # noqa: E402

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
    pkg.write(p, "D",
              objects=[{"name": "AMonster", "layer": 1, "file": "m.h"}],
              actions=[{"name": "Spawn", "layer": 2, "description": "합성이 쓴 설명"}])
    return p


def test_edit_locks() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        r = E.edit(p, "D", "actions", "Spawn", {"description": "사람이 고친 설명"})
        check("값이 바뀐다", r.changed == ["description"], str(r.changed))
        check("🔴 편집은 곧 잠금이다", r.locked, r.summary)
        f = E.find_item(p, "D", "actions", "Spawn")
        item = yaml_io.read(f)
        check("파일에 반영된다", item["description"] == "사람이 고친 설명", str(item))
        check("잠금 표식이 파일에 있다", item.get(E.LOCK_FIELD) is True, str(item))

        # 🔴 값이 같으면 changed 에 넣지 않는다 — "바꿨다" 는 보고가 거짓이면 안 된다
        r2 = E.edit(p, "D", "actions", "Spawn", {"description": "사람이 고친 설명"})
        check("같은 값은 변경으로 세지 않는다", r2.changed == [], str(r2.changed))
        check("이미 잠겨 있었음을 안다", r2.was_locked, r2.summary)


def test_immutable_fields() -> None:
    """🔴 `name`·`layer` 는 파일 경로의 근거다 — 패치로 바꾸면 파일과 내용이 어긋난다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        r = E.edit(p, "D", "objects", "AMonster",
                   {"name": "ADragon", "layer": 3, "file": "d.h"})
        check("🔴 name/layer 는 무시한다", sorted(r.ignored) == ["layer", "name"], str(r.ignored))
        # 🔴 조용히 무시하면 호출자가 바뀐 줄 안다 — 보고해야 한다
        check("무시했다고 보고한다", "무시" in r.summary, r.summary)
        check("나머지는 적용한다", r.changed == ["file"], str(r.changed))
        item = yaml_io.read(E.find_item(p, "D", "objects", "AMonster"))
        check("이름이 그대로다", item["name"] == "AMonster", str(item))
        check("계층이 그대로다", item["layer"] == 1, str(item))

        # 잠금은 lock 인자로만 — 두 경로를 두지 않는다
        r2 = E.edit(p, "D", "objects", "AMonster", {E.LOCK_FIELD: False})
        check("🔴 patch 로 잠금을 못 바꾼다", E.LOCK_FIELD in r2.ignored and r2.locked, str(r2.ignored))


def test_never_creates() -> None:
    """🔴 없는 항목을 편집하면 **만들지 않고 예외** — 오타가 유령 항목을 낳으면 안 된다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        try:
            E.edit(p, "D", "actions", "없는것", {"description": "x"})
            check("🔴 없는 항목은 만들지 않는다", False, "조용히 만들었다")
        except E.EditError as e:
            check("🔴 없는 항목은 만들지 않는다", "찾지 못했다" in str(e), str(e)[:60])
        check("파일이 생기지 않았다", E.find_item(p, "D", "actions", "없는것") is None)

        try:
            E.edit(p, "D", "objectz", "AMonster", {})
            check("잘못된 kind 는 예외", False)
        except E.EditError:
            check("잘못된 kind 는 예외", True)


def test_lock_survives_resynthesis() -> None:
    """🔴 이것이 전부다 — 잠근 것을 재합성이 덮지 않는가."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        E.edit(p, "D", "actions", "Spawn", {"description": "사람이 검수한 설명"})

        # 합성기가 같은 이름으로 다른 내용을 들고 다시 온다
        pkg.write(p, "D", actions=[{"name": "Spawn", "layer": 2,
                                    "description": "LLM 이 새로 쓴 설명"}])
        item = yaml_io.read(E.find_item(p, "D", "actions", "Spawn"))
        check("🔴 재합성이 잠긴 항목을 덮지 않는다",
              item["description"] == "사람이 검수한 설명", str(item))

        # 잠기지 않은 것은 갱신돼야 한다 — 잠금이 전부를 얼리면 안 된다
        pkg.write(p, "D", objects=[{"name": "AMonster", "layer": 1, "file": "새.h"}])
        obj = yaml_io.read(E.find_item(p, "D", "objects", "AMonster"))
        check("잠기지 않은 것은 갱신된다", obj["file"] == "새.h", str(obj))


def test_unlock() -> None:
    """🔴 잘못 건 잠금이 영구가 되면 그 항목은 영영 낡는다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        E.edit(p, "D", "actions", "Spawn", {"description": "사람 것"})
        r = E.set_lock(p, "D", "actions", "Spawn", locked=False)
        check("잠금을 풀 수 있다", not r.locked, r.summary)
        # 🔴 푸는 것의 결과를 말해 준다
        check("풀면 덮인다고 경고한다", "덮을 수 있다" in r.note, r.note)

        pkg.write(p, "D", actions=[{"name": "Spawn", "layer": 2, "description": "합성 것"}])
        item = yaml_io.read(E.find_item(p, "D", "actions", "Spawn"))
        check("풀린 뒤엔 재합성이 덮는다", item["description"] == "합성 것", str(item))


def test_visibility() -> None:
    """🔴 무엇을 잠갔는지 볼 수 없으면 사람이 잊는다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        check("처음엔 잠긴 것이 없다", E.locked_items(p) == [])
        E.edit(p, "D", "actions", "Spawn", {"description": "x"})
        got = E.locked_items(p)
        check("잠근 것이 목록에 뜬다", len(got) == 1 and got[0]["name"] == "Spawn", str(got))
        check("어디 있는지도 준다", got and got[0]["kind"] == "actions" and got[0]["layer"] == "L2",
              str(got))


def main() -> int:
    for fn in (test_edit_locks, test_immutable_fields, test_never_creates,
               test_lock_survives_resynthesis, test_unlock, test_visibility):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_ontology_edit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
