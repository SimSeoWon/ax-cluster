"""소스↔온톨로지 정합 — path_sync · declared (소 1.3.9).

지키는 계약: 🔴 **기계의 사실만 건드린다. 없는 것을 지우지 않는다. 잠금이 문서를 썩히지 않는다.**

`.venv/bin/python master/test_ontology_sync.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths          # noqa: E402
from master.ontology import package as pkg, sync as S, yaml_io  # noqa: E402

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
    pkg.write(p, "D", objects=[
        {"name": "AMonster", "layer": 1, "file": "Source/옛경로.h"},
        {"name": "AGhost", "layer": 2, "file": "Source/Ghost.h"},
    ])
    return p


FILES = {"AMonster": "Source/새경로.h", "AGhost": "Source/Ghost.h"}
METHODS = {"AMonster": ["Attack", "Die", "Step"], "AGhost": []}


def _item(p, name):
    from master.ontology.edit import find_item
    return yaml_io.read(find_item(p, "D", "objects", name))


def test_path_sync() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        st = S.sync_domain(p, "D", files=FILES, methods=METHODS)
        check("옮겨진 경로를 고친다", [x[0] for x in st.path_fixed] == ["AMonster"], str(st.path_fixed))
        check("옛 경로도 보고한다", st.path_fixed[0][1] == "Source/옛경로.h", str(st.path_fixed))
        check("파일에 반영된다", _item(p, "AMonster")["file"] == "Source/새경로.h")
        check("맞는 것은 건드리지 않는다", _item(p, "AGhost")["file"] == "Source/Ghost.h")

        # 두 번 돌려도 변화가 없어야 한다 (멱등)
        st2 = S.sync_domain(p, "D", files=FILES, methods=METHODS)
        check("멱등하다", not st2.path_fixed and not st2.declared_set, st2.summary)


def test_declared() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        S.sync_domain(p, "D", files=FILES, methods=METHODS)
        # 🔴 실측 근거: 규범만으론 CurrentStep(실제 Step) 같은 한 글자 차이가 남았다
        check("선언 메서드를 들여놓는다",
              _item(p, "AMonster")[S.DECLARED_FIELD] == ["Attack", "Die", "Step"],
              str(_item(p, "AMonster")))
        check("메서드가 없으면 필드를 만들지 않는다",
              S.DECLARED_FIELD not in _item(p, "AGhost"), str(_item(p, "AGhost")))

        many = {"AMonster": [f"M{i}" for i in range(S.MAX_DECLARED + 5)], "AGhost": []}
        st = S.sync_domain(p, "D", files=FILES, methods=many)
        # 🔴 잘랐으면 잘랐다고 말한다
        check("상한을 넘으면 자른다",
              len(_item(p, "AMonster")[S.DECLARED_FIELD]) == S.MAX_DECLARED)
        check("자른 사실을 보고한다", st.truncated == ["AMonster"] and "상한" in st.summary,
              st.summary)


def test_missing_is_reported_not_deleted() -> None:
    """🔴 그래프에 없다고 지우면, 그래프가 낡았을 때 문서가 사라진다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        st = S.sync_domain(p, "D", files={"AGhost": "Source/Ghost.h"}, methods={})
        check("없는 것을 보고한다", st.missing == ["AMonster"], str(st.missing))
        check("🔴 지우지 않는다", _item(p, "AMonster") is not None)
        check("남겨 뒀다고 요약에 적는다", "남겨 둠" in st.summary, st.summary)


def test_lock_does_not_rot_the_doc() -> None:
    """🔴 잠금이 지키는 것은 사람의 내용이지 '어느 파일에 있는가' 가 아니다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        from master.ontology import edit as E
        E.edit(p, "D", "objects", "AMonster", {"description": "사람이 쓴 설명"})
        S.sync_domain(p, "D", files=FILES, methods=METHODS)
        item = _item(p, "AMonster")
        check("🔴 잠겨 있어도 경로는 맞춘다", item["file"] == "Source/새경로.h", str(item))
        check("🔴 사람이 쓴 내용은 그대로", item["description"] == "사람이 쓴 설명", str(item))
        check("잠금도 그대로", item[E.LOCK_FIELD] is True, str(item))


def test_plan_only() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        st = S.sync_domain(p, "D", files=FILES, methods=METHODS, apply=False)
        check("계획은 세운다", len(st.path_fixed) == 1, str(st.path_fixed))
        # 🔴 apply=False 면 파일이 그대로여야 한다
        check("🔴 아무것도 쓰지 않는다", _item(p, "AMonster")["file"] == "Source/옛경로.h",
              str(_item(p, "AMonster")))


def test_no_graph() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        st = S.sync_domain(p, "D")
        check("🔴 그래프가 없으면 0을 성공으로 보고하지 않는다",
              any("그래프가 없다" in n for n in st.notes), str(st.notes))
        check("아무것도 안 고친다", not st.path_fixed)


def main() -> int:
    for fn in (test_path_sync, test_declared, test_missing_is_reported_not_deleted,
               test_lock_does_not_rot_the_doc, test_plan_only, test_no_graph):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_ontology_sync: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
