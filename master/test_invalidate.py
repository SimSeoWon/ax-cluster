"""부분 무효화 테스트 — 소 3.2.2. pytest 없이 실행한다.

    .venv/bin/python master/test_invalidate.py

원본: `AgentTest/tests/test_eta_7_partial.py` 16건. 그 파일이 고정한 계약을 능력 단위로
맞췄고, **우리에게만 있는 것 둘**을 추가했다 — 잠금·보호 항목 보존, 그리고
`prune=False` 가 manifest 를 잃지 않는 것.

🔴 **여기서 고정하는 진짜 계약은 「보존」이다.** 무효화가 과하면 LLM 을 더 쓰고 끝나지만,
보존이 깨지면 사람이 검수한 것과 받아온 스냅샷이 **조용히 사라진다.**
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths        # noqa: E402
from master.ontology import (domain_md as dmd, invalidate as inv,            # noqa: E402
                             package as pkg, yaml_io as y)

PASS = FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def _paths(tmp: Path, name: str = "M") -> ProjectPaths:
    return ProjectPaths(name=name, root=tmp / name)


def _domain_md(paths: ProjectPaths, domain: str, body: str = "# D\n\n## 시스템 개요\n\n내용\n"):
    d = dmd.domains_dir(paths)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{domain}.md").write_text(body, encoding="utf-8")


def _item(paths: ProjectPaths, domain: str, kind: str, name: str, text: str, layer: str = "L3",
          extra: dict | None = None):
    """항목 yaml 하나를 직접 쓴다 (합성기를 안 태우고 무효화 판정만 재려는 것)."""
    p = paths.ontology / "domains" / domain / layer / kind / f"{name}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "description": text}
    data.update(extra or {})
    y.write(p, data)
    return p


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-inval-"))
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp: Path) -> int:
    print("\n[1] 도메인 MD content-hash")
    P = _paths(tmp)
    _domain_md(P, "D")
    h1 = inv.domain_md_hash(P, "D")
    check("해시가 나온다 (md5 앞 16자)", len(h1) == 16, h1)
    check("같은 내용은 같은 해시", inv.domain_md_hash(P, "D") == h1)
    _domain_md(P, "D", "# D\n\n## 시스템 개요\n\n바뀐 내용\n")
    check("🔴 내용이 바뀌면 해시가 바뀐다", inv.domain_md_hash(P, "D") != h1)
    check("MD 가 없으면 빈 문자열", inv.domain_md_hash(P, "없는도메인") == "")

    print("\n[2] manifest md_hash 읽기")
    check("manifest 가 없으면 None", inv.manifest_md_hash(P, "D") is None)
    root = P.ontology / "domains" / "D"
    root.mkdir(parents=True, exist_ok=True)
    y.write(root / pkg.MANIFEST, {"domain": "D", "tier": 3})
    check("키가 없어도 None (레거시)", inv.manifest_md_hash(P, "D") is None)
    y.write(root / pkg.MANIFEST, {"domain": "D", "md_hash": "abc123"})
    check("있으면 그 값", inv.manifest_md_hash(P, "D") == "abc123")

    print("\n[3] 🔴 package.write 가 md_hash 를 찍는다 (없으면 영원히 full 폴백)")
    P2 = _paths(tmp, "M2")
    _domain_md(P2, "D")
    pkg.write(P2, "D", objects=[{"name": "UFoo", "layer": 3, "file": "Foo.h"}])
    man = y.read(P2.ontology / "domains" / "D" / pkg.MANIFEST) or {}
    check("manifest 에 md_hash 가 있다", man.get("md_hash") == inv.domain_md_hash(P2, "D"), str(man.get("md_hash")))
    P3 = _paths(tmp, "M3")
    pkg.write(P3, "D", objects=[{"name": "UFoo", "layer": 3, "file": "Foo.h"}])
    man3 = y.read(P3.ontology / "domains" / "D" / pkg.MANIFEST) or {}
    check("🔴 MD 가 없으면 빈 md_hash 키를 만들지 않는다", "md_hash" not in man3, str(man3))

    print("\n[4] 무효화 범위 — 언급된 것만, 애매하면 무효화")
    P4 = _paths(tmp, "M4")
    _domain_md(P4, "D")
    # 멤버 두 개를 manifest 로 선언한다 (collect.members_of 가 읽는 자리)
    pkg.write(P4, "D", objects=[{"name": "UFoo", "layer": 3, "file": "Foo.h"},
                                {"name": "UBar", "layer": 3, "file": "Bar.h"}])
    a_hit = _item(P4, "D", "actions", "TouchesFoo", "UFoo 가 무언가를 한다")
    a_miss = _item(P4, "D", "actions", "TouchesBar", "UBar 만 나온다")
    i_hit = _item(P4, "D", "invariants", "FooAlwaysValid", "UFoo 와 UBar 가 함께 나온다")
    r = inv.determine_invalidation(P4, "D", {"UFoo"})
    check("변경 클래스를 언급한 action 이 무효화", a_hit in r.actions, str(r.actions))
    check("🔴 언급 없는 action 은 보존", a_miss not in r.actions and r.preserved_actions == 1, r.summary)
    check("invariant 도 같은 규칙", i_hit in r.invariants, str(r.invariants))
    check("🔴 응집 — 같이 언급된 멤버가 scope 에 들어온다", r.scope_classes == {"UFoo", "UBar"}, str(r.scope_classes))
    check("objects 는 변경 클래스 자신", r.objects == {"UFoo"}, str(r.objects))
    r2 = inv.determine_invalidation(P4, "D", {"UQux"})       # 멤버도 아니고 언급도 없다
    check("무관한 클래스는 아무것도 무효화하지 않는다", r2.empty, r2.summary)
    check("그때 scope 는 변경 클래스 그대로", r2.scope_classes == {"UQux"}, str(r2.scope_classes))

    print("\n[5] 🔴 잠금·보호 항목은 무효화하지 않는다 (원전에 없는 우리 개념)")
    lock = _item(P4, "D", "actions", "LockedFoo", "UFoo 를 언급하지만 사람이 검수했다",
                 extra={"verified_by_user": True})
    prot = _item(P4, "D", "invariants", "SnapshotFoo", "UFoo 를 언급하는 받아온 스냅샷",
                 extra={"protected": True})
    r3 = inv.determine_invalidation(P4, "D", {"UFoo"})
    check("검수 잠금은 무효화 목록에 없다", lock not in r3.actions, str(r3.actions))
    check("보호(스냅샷)도 없다", prot not in r3.invariants, str(r3.invariants))
    check("잠금 수를 센다", r3.locked_kept == 2, r3.summary)
    check("보존 수에도 반영된다", r3.preserved_actions >= 1 and r3.preserved_invariants >= 1, r3.summary)

    print("\n[6] 못 읽는 yaml 은 무효화 쪽으로 (보수적)")
    P5 = _paths(tmp, "M5")
    _domain_md(P5, "D")
    pkg.write(P5, "D", objects=[{"name": "UFoo", "layer": 3, "file": "Foo.h"}])
    bad = P5.ontology / "domains" / "D" / "L3" / "actions" / "Broken.yaml"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"name: Broken\n")
    bad.chmod(0o000)
    try:
        r4 = inv.determine_invalidation(P5, "D", {"UFoo"})
        readable = bad.read_text(encoding="utf-8", errors="replace") is not None
    except OSError:
        readable = False
    if readable:
        print("     ⚠️ root 로 도는 환경이라 권한 실패를 못 만든다 — 이 항목만 건너뛴다")
    else:
        check("🔴 읽기 실패는 무효화한다", bad in r4.actions, str(r4.actions))
        check("그 수를 따로 센다", r4.unreadable == 1, r4.summary)
    bad.chmod(0o644)

    print("\n[7] full 폴백 판정 (원전 decision 3)")
    P6 = _paths(tmp, "M6")
    _domain_md(P6, "D")
    r6root = P6.ontology / "domains" / "D"
    r6root.mkdir(parents=True, exist_ok=True)
    y.write(r6root / pkg.MANIFEST, {"domain": "D"})
    check("md_hash 부재 → full", inv.plan_domain_refresh(P6, "D").full)
    check("사유를 남긴다", "부재" in inv.plan_domain_refresh(P6, "D").reason)
    y.write(r6root / pkg.MANIFEST, {"domain": "D", "md_hash": "지난번해시"})
    p = inv.plan_domain_refresh(P6, "D")
    check("md_hash 불일치(도메인 뜻 변경) → full", p.full, p.summary)
    check("그 사유도 남긴다", "MD 변경" in p.reason, p.reason)
    y.write(r6root / pkg.MANIFEST, {"domain": "D", "md_hash": inv.domain_md_hash(P6, "D")})
    p2 = inv.plan_domain_refresh(P6, "D")
    check("🔴 일치하면 full 이 아니다", not p2.full, p2.summary)
    check("변경 클래스가 0 이면 빈 집합 (full 과 다르다)", p2.changed == set(), str(p2.changed))

    print("\n[8] 🔴 prune=False 가 manifest 를 잃지 않는다 (부분 갱신의 전제)")
    P7 = _paths(tmp, "M7")
    _domain_md(P7, "D")
    pkg.write(P7, "D",
              actions=[{"name": "Keep", "layer": 3}, {"name": "Redo", "layer": 3}],
              invariants=[{"name": "Inv1", "layer": 3}])
    root7 = P7.ontology / "domains" / "D"
    before = set((y.read(root7 / pkg.MANIFEST) or {}).get("actions") or [])
    check("두 액션이 manifest 에 있다", len(before) == 2, str(before))
    pkg.write(P7, "D", actions=[{"name": "Redo", "layer": 3, "description": "다시 만든 것"}],
              prune=False)
    man7 = y.read(root7 / pkg.MANIFEST) or {}
    check("🔴 안 들어온 항목의 경로가 manifest 에 남는다",
          set(man7.get("actions") or []) == before, str(man7.get("actions")))
    check("파일도 그대로 있다", (root7 / "L3" / "actions" / "Keep.yaml").is_file())
    check("다시 만든 것은 갱신됐다",
          (y.read(root7 / "L3" / "actions" / "Redo.yaml") or {}).get("description") == "다시 만든 것")
    check("건드리지 않은 종류(invariants)도 유지",
          (man7.get("invariants_files") or []) == ["L3/invariants/Inv1.yaml"], str(man7))
    pkg.write(P7, "D", actions=[{"name": "Redo", "layer": 3}])     # 기본값 prune=True
    man8 = y.read(root7 / pkg.MANIFEST) or {}
    check("반대로 prune=True 는 정리한다", set(man8.get("actions") or []) == {"L3/actions/Redo.yaml"},
          str(man8.get("actions")))
    check("그 파일도 지워졌다", not (root7 / "L3" / "actions" / "Keep.yaml").is_file())

    print("\n[9] 🔴 무효화 파일 삭제는 쓰기 직전에만 (실패해도 파괴하지 않는다)")
    from master.ontology import synth as sy
    P8 = _paths(tmp, "M8")
    _domain_md(P8, "D")
    pkg.write(P8, "D", objects=[{"name": "UFoo", "layer": 3, "file": "Foo.h"}])
    victim = _item(P8, "D", "actions", "TouchesFoo", "UFoo 가 무언가를 한다")
    r9 = inv.determine_invalidation(P8, "D", {"UFoo"})
    check("삭제 전에는 파일이 있다", victim.is_file())
    n = sy._delete_invalidated(r9)
    check("무효화분을 지운다", n == 1 and not victim.is_file(), str(n))
    check("이미 없는 것을 또 지워도 죽지 않는다", sy._delete_invalidated(r9) == 0)

    print("\n[10] 🔴 LLM 없이 partial 분기가 도는지 (합성기 배선)")
    # LLM 을 부르지 않게 조각을 0개로 만드는 경로 — 소스 발췌가 없는 프로젝트다.
    P9 = _paths(tmp, "M9")
    _domain_md(P9, "D")
    pkg.write(P9, "D", objects=[{"name": "UFoo", "layer": 3, "file": "Foo.h"}])
    res = sy.refresh_domain(P9, "D", changed_classes={"UFoo"}, dry_run=True)
    check("scope 를 못 만들어도 예외를 던지지 않는다", isinstance(res, sy.DomainResult))
    check("사유가 남는다", bool(res.reasons), str(res.reasons))
    check("🔴 멤버와 겹치면 partial 로 붙는다", res.partial and res.invalidation is not None,
          f"partial={res.partial} reasons={res.reasons}")
    res2 = sy.refresh_domain(P9, "D", changed_classes={"없는클래스"}, dry_run=True)
    check("🔴 scope 가 멤버와 안 겹치면 partial 을 포기하고 full 로 간다",
          not res2.partial and any("full" in x for x in res2.reasons), str(res2.reasons))

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
