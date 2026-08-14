"""온톨로지 일관성 감사 (소 3.1.5 · `#188`) — 원전 `ontology_pkg_audit.py` 이식분.

검증하는 것:

    ① 도메인 MD 검출 셋 — 중복 stem · `status:` 누락 · `_archive` 안 `status: active`
    ② `_` 로 시작하는 파일은 도메인이 아니다 (`_overview` 등 — 원전과 같은 제외)
    ③ 🔴 **read-only** — 감사가 파일을 고치지 않는다
    ④ 패키지 walk — objects/actions/invariants 카운트 + 레이어 분포
    ⑤ 🔴 `domain.yaml` 이 없는 디렉토리는 **세지 않되 보고한다**
       (원전은 조용히 건너뛴다 — 몇 개를 안 봤는지 모르면 「도메인 N개」가 전부인지 알 수 없다)
    ⑥ 갭은 「수치 0건」 신호일 뿐 — 🔴 자동으로 고치지 않는다(원인 둘이 같은 외양)
    ⑦ 읽기 실패를 세어서 돌려준다 (원전은 `except: continue`)
    ⑧ PyYAML 없이 frontmatter 를 읽는다 (감사가 파서에 의존하면 파서가 깨질 때 함께 눈을 감는다)

`.venv/bin/python master/test_pkg_audit.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology import pkg_audit as PA                      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def md(status: str = "active", extra: str = "") -> str:
    return f"---\ntype: domain\nstatus: {status}\n{extra}---\n\n## 요약\n본문\n"


class Fx:
    def __init__(self, tmp: Path):
        self.context = tmp / "context"
        self.ontology = tmp / "ontology"
        self.root = tmp
        (self.context / "_domains").mkdir(parents=True)
        (self.ontology / "domains").mkdir(parents=True)

    def domain_md(self, name: str, body: str, *, archived: bool = False) -> Path:
        d = self.context / "_domains" / ("_archive" if archived else "")
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text(body, encoding="utf-8")
        return p

    def pkg(self, name: str, *, manifest: bool = True, objects=(), actions=(), invariants=()):
        base = self.ontology / "domains" / name
        base.mkdir(parents=True, exist_ok=True)
        if manifest:
            (base / PA.MANIFEST).write_text("name: " + name + "\n", encoding="utf-8")
        for layer, n in objects:
            d = base / layer / "objects"
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                (d / f"o{i}.yaml").write_text("x: 1\n", encoding="utf-8")
        for layer, n in actions:
            d = base / layer / "actions"
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                (d / f"a{i}.yaml").write_text("x: 1\n", encoding="utf-8")
        for layer, n in invariants:
            d = base / layer / "invariants"
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                (d / f"i{i}.yaml").write_text("x: 1\n", encoding="utf-8")


# ── ①②③⑦⑧ 도메인 MD ─────────────────────────────────────────────────────────

def test_md_detects_three_gaps():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.domain_md("Good.md", md("active"))
        fx.domain_md("Dup.md", md("active"))
        fx.domain_md("Dup.md", md("archived"), archived=True)     # ① 중복 stem
        fx.domain_md("NoStatus.md", "---\ntype: domain\n---\n\n본문\n")   # ① status 누락
        fx.domain_md("StillActive.md", md("active"), archived=True)       # ① archive+active
        fx.domain_md("_overview.md", md("active"))                        # ② 제외 대상

        r = PA.audit_domain_md(fx.context)
        check("① 중복 stem 을 잡는다", r["duplicate_stems"] == ["Dup"], str(r["duplicate_stems"]))
        check("① status 누락을 잡는다", r["missing_status"] == ["NoStatus.md"],
              str(r["missing_status"]))
        # ⚠️ `Dup.md` 는 `status: archived` 라 잡히지 **않는다** — 중복 stem 이지만
        #    archive_active 는 아니다. 첫 판은 둘을 기대했고 그건 테스트가 틀린 것이었다.
        check("① 🔴 _archive 안 active 를 잡는다",
              r["archive_active"] == ["StillActive.md"], str(r["archive_active"]))
        check("② `_` 시작 파일은 도메인이 아니다", r["direct_count"] == 3,
              f"direct={r['direct_count']}")

        # ③ 감사가 아무것도 안 고쳤다
        check("③ 🔴 read-only — status 가 그대로다",
              "status: active" in (fx.context / "_domains" / "StillActive.md").read_text()
              if False else "status: active" in
              (fx.context / "_domains" / "_archive" / "StillActive.md").read_text(encoding="utf-8"))
        check("③ 파일이 안 지워졌다", (fx.context / "_domains" / "NoStatus.md").exists())


def test_md_no_gaps_is_quiet():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.domain_md("A.md", md("active"))
        fx.domain_md("B.md", md("archived"), archived=True)
        r = PA.audit_domain_md(fx.context)
        check("갭이 없으면 빈 목록이다 (노이즈를 만들지 않는다)", PA.md_gaps(r) == [],
              str(PA.md_gaps(r)))


def test_missing_dir_is_a_fact():
    with tempfile.TemporaryDirectory() as tmp:
        r = PA.audit_domain_md(Path(tmp) / "nope")
        check("디렉토리가 없으면 사실로 보고", bool(r.get("error")), str(r))
        check("갭 문장에도 나온다", any("없다" in g for g in PA.md_gaps(r)), str(PA.md_gaps(r)))


def test_unreadable_is_counted():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        p = fx.domain_md("Locked.md", md("active"))
        p.chmod(0o000)
        try:
            r = PA.audit_domain_md(fx.context)
            check("⑦ 읽기 실패를 세어서 돌려준다", len(r["unreadable"]) == 1, str(r["unreadable"]))
            check("⑦ 갭 문장에 나온다", any("읽지 못한" in g for g in PA.md_gaps(r)),
                  str(PA.md_gaps(r)))
        finally:
            p.chmod(0o644)


def test_frontmatter_without_yaml():
    """⑧ 감사가 파서에 의존하면 파서가 깨질 때 감사도 함께 눈을 감는다."""
    fm = PA._frontmatter("---\ntype: domain\nstatus: 'active'\ntags: [a, b]\n"
                         "source_documents:\n  - x.md\n---\n\n본문\n")
    check("⑧ 스칼라를 읽는다", fm.get("status") == "active", str(fm))
    check("⑧ 중첩 항목은 무시한다 (파서가 되지 않는다)", "- x.md" not in str(fm.values()), str(fm))
    check("⑧ frontmatter 가 없으면 빈 dict", PA._frontmatter("본문만") == {})


# ── ④⑤⑥ 패키지 ───────────────────────────────────────────────────────────────

def test_packages_count_and_layers():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.pkg("MissionRuntime", objects=[("L1", 1), ("L3", 10)],
               actions=[("L3", 12)], invariants=[("L3", 10)])
        r = PA.audit_packages(fx.ontology)
        d = r["domains"][0]
        check("④ objects 를 레이어 합산한다", d["objects"] == 11, str(d))
        check("④ actions·invariants 도", d["actions"] == 12 and d["invariants"] == 10, str(d))
        check("④ 레이어 분포를 낸다", d["layer_dist"] == {"L1": 1, "L3": 10},
              str(d["layer_dist"]))
        check("④ 합계가 맞는다", r["totals"]["objects"] == 11 and r["totals"]["domains"] == 1,
              str(r["totals"]))


def test_manifestless_dir_is_reported_not_counted():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.pkg("Real", objects=[("L1", 2)], actions=[("L1", 1)])
        fx.pkg("Legacy", manifest=False, objects=[("L1", 99)])
        r = PA.audit_packages(fx.ontology)
        check("⑤ manifest 없는 것은 세지 않는다", r["totals"]["domains"] == 1, str(r["totals"]))
        check("⑤ 🔴 그래도 보고한다", r["skipped"] == ["Legacy"], str(r["skipped"]))
        check("⑤ 그 안의 yaml 도 합계에 안 들어간다", r["totals"]["objects"] == 2,
              str(r["totals"]))


def test_zero_counts_are_gaps_not_fixes():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.pkg("Empty")                                  # objects 0 · actions 0
        r = PA.audit_packages(fx.ontology)
        check("⑥ objects=0 을 갭으로 낸다", any("objects=0" in g for g in r["gaps"]),
              str(r["gaps"]))
        check("⑥ actions=0 도", any("actions=0" in g for g in r["gaps"]), str(r["gaps"]))
        rep = PA.format_report({"direct_count": 0, "archive_count": 0, "duplicate_stems": [],
                                "missing_status": [], "archive_active": [], "unreadable": []}, r)
        check("⑥ 🔴 리포트가 「자동으로 고치지 않는다」를 말한다",
              "자동으로 고치지 않는다" in rep, rep[:120])
        check("⑥ 원인이 둘임을 말한다", "같은 외양" in rep, rep[:200])


def main() -> int:
    for fn in (test_md_detects_three_gaps, test_md_no_gaps_is_quiet, test_missing_dir_is_a_fact,
               test_unreadable_is_counted, test_frontmatter_without_yaml,
               test_packages_count_and_layers, test_manifestless_dir_is_reported_not_counted,
               test_zero_counts_are_gaps_not_fixes):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_pkg_audit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
