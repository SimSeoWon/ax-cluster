"""드리프트 감사 (소 2.4.1).

🔴 지키는 계약은 **좁히기**다. "기준 커밋이 다르다" 로 깃발을 꽂으면 커밋 하나에 240건이
한꺼번에 뜨고 아무도 안 본다 — 경보가 많으면 경보가 아니다.

`.venv/bin/python master/test_drift.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths        # noqa: E402
from master.ontology import drift as DR, edit as E, package as pkg  # noqa: E402

PASS = FAIL = 0
OLD, NEW = "a" * 40, "b" * 40


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _seed(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="T", root=root)
    pkg.write(p, "D", objects=[{"name": "AMonster", "layer": 1, "file": "Source/M.h"}],
              actions=[{"name": "Spawn", "layer": 2, "description": "x"}])
    return p


def _audit(p, *, head=NEW, changed=(), ghosts=(), missing=(), at=OLD):
    """의존을 전부 주입한다 — git 도 그래프도 부르지 않는다."""
    import types
    orig_changed, orig_sync, orig_vf, orig_commit = (
        DR._changed_between, None, None, None)
    from master.ontology import sync as osync, verify_facts as vf
    from master.work import twin_base
    orig_sync, orig_vf, orig_commit = osync.sync_domain, vf.verify_domain, twin_base.twin_commit
    DR._changed_between = lambda paths, o, n: list(changed)
    osync.sync_domain = lambda paths, dom, **kw: types.SimpleNamespace(
        path_fixed=[], missing=list(missing), declared_set=[], summary="")
    vf.verify_domain = lambda paths, dom: types.SimpleNamespace(
        findings=list(ghosts), checked=1, skipped_reason="")
    twin_base.twin_commit = lambda paths: head
    orig_items = E.protected_items
    E.protected_items = lambda paths, dom="": [
        {"domain": "D", "kind": "actions", "name": "Spawn", "at": at, "reason": "r", "path": "x"}]
    try:
        return DR.audit(p)
    finally:
        DR._changed_between, osync.sync_domain = orig_changed, orig_sync
        vf.verify_domain, twin_base.twin_commit = orig_vf, orig_commit
        E.protected_items = orig_items


def test_narrowing_is_the_contract() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))

        same = _audit(p, head=OLD, at=OLD)
        check("기준이 같으면 조용하다", not same.suspects, same.render()[:120])

        # 🔴 커밋은 달라졌지만 **이 도메인 파일은 안 바뀌었다** → 깃발을 꽂지 않는다
        other = _audit(p, changed=["Docs/README.md", "ModularStage.uproject"])
        check("🔴 무관한 파일 변경은 무시한다", not other.suspects,
              str([d.line for d in other.domains]))

        # 🔴 이 도메인이 근거로 삼은 파일이 바뀌었다 → 의심
        mine = _audit(p, changed=["Source/M.h"])
        check("🔴 근거 파일이 바뀌면 잡는다", len(mine.suspects) == 1, str(mine.suspects))
        check("무엇이 바뀌었는지 말한다", "M.h" in mine.suspects[0].line, mine.suspects[0].line)
        check("기준 커밋을 밝힌다", OLD[:8] in mine.suspects[0].line, mine.suspects[0].line)


def test_other_checks_flag_regardless() -> None:
    """사실 게이트·사라진 클래스는 **커밋과 무관하게** 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        g = _audit(p, head=OLD, at=OLD, ghosts=["ghost_method: X::Y"])
        check("유령은 기준이 같아도 잡는다", len(g.suspects) == 1, str(g.suspects))
        check("유령 수를 적는다", "유령 1" in g.suspects[0].line, g.suspects[0].line)

        m = _audit(p, head=OLD, at=OLD, missing=["AGone"])
        check("사라진 클래스도 잡는다", len(m.suspects) == 1 and m.suspects[0].missing == ["AGone"])


def test_report_says_what_it_cannot_do() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = _audit(_seed(Path(t)), changed=["Source/M.h"]).render()
        # 🔴 감사가 지운다고 오해하면 사람이 확인을 안 한다
        check("🔴 지우지 않는다고 못박는다", "감사는 지우지 않는다" in r, r[-300:])
        check("무엇으로 고치는지 알려준다", "remove(force)" in r and "refresh" in r)
        # 🔴 못 잡는 것을 밝힌다 — 설계 규칙 서술은 자동 검증이 안 된다
        check("🔴 한계를 밝힌다", "자동으로 못 잡는다" in r, r[-300:])
        check("의심 수를 머리에 적는다", "의심 1" in r, r[:120])


def test_read_only() -> None:
    src = (Path(__file__).resolve().parent / "ontology" / "drift.py").read_text("utf-8")
    for banned in ("yaml_io.write", ".write_text(", ".unlink(", "apply=True"):
        check(f"🔴 {banned} 없음", banned not in src)


def main() -> int:
    for fn in (test_narrowing_is_the_contract, test_other_checks_flag_regardless,
               test_report_says_what_it_cannot_do, test_read_only):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_drift: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
