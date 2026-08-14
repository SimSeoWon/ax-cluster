"""컨텍스트 MD 진단 (소 3.4.1 · `#160`) — 원전 `context_audit.py` 이식분.

검증하는 것:

    ① 8분류가 각각 잡힌다
    ② 🔴 **분류 순서** — `orphan_stem` 이 내용 분류보다 **먼저**다
       (실측으로 값이 증명됐다: 순서를 바꾸면 재생성할 소스가 없는 108건이 재생성 대상이 된다)
    ③ `dir_named` 가 내용 분류보다 먼저다
    ④ `## 코멘트` 이후는 평가에서 뺀다 (사람이 쓴 것 — 원전 판단)
    ⑤ 🔴 복구는 **걷어내서 나아지는 것만** — 아니면 거부한다
    ⑥ 🔴 `apply_repair` 는 **계획이 고른 것 밖을 건드리지 않는다**
    ⑦ 🔴 `dir_named`·`orphan_stem` 은 **옮기지 않는다** (복구 후보에 아예 안 들어간다)
    ⑧ 읽기 실패를 **세어서 돌려준다** (원전은 로그 한 줄만 남겼다)
    ⑨ 아카이브 — 🔴 목적지가 `context/` **밖**이고, 계획이 기본이고, **덮어쓰지 않는다**

`.venv/bin/python master/test_context_audit.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search import context_audit as CA          # noqa: E402

PASS = FAIL = 0

VALID = """---
tags: [a]
---

## 요약

이 클래스는 미션 실행기를 들고 있고 상태를 복제한다. 본문이 오십 자를 넘도록 충분히 길게 적는다.
"""


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


class Fx:
    """`context/` 와 `repo/` 를 실제 디렉토리로 만든다."""

    def __init__(self, tmp: Path):
        self.context = tmp / "context"
        self.repo = tmp / "repo"
        (self.context / "Source").mkdir(parents=True)
        (self.repo / "Source").mkdir(parents=True)

    def md(self, rel: str, body: str) -> Path:
        p = self.context / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def src(self, rel: str) -> Path:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("// src\n", encoding="utf-8")
        return p

    def run(self) -> dict:
        return CA.audit(self.context, self.repo)


# ── ① 분류 ───────────────────────────────────────────────────────────────────

def test_classify_each_category():
    cases = {
        "valid": VALID,
        "pence_wrapped": "```markdown\n---\ntags: []\n---\n\n## 요약\n" + "가" * 60 + "\n```",
        "natural_prefix": "네, 문서를 작성했습니다!\n\n---\ntags: []\n---\n\n## 요약\n" + "가" * 60,
        "shell_only": "---\ntags: []\n---\n",
        "empty_summary": "---\ntags: []\n---\n\n" + "가" * 60,
        "no_frontmatter": "그냥 본문만 있고 구분선이 없다 " + "가" * 60,
    }
    for want, content in cases.items():
        got = CA.classify(content)
        check(f"① classify → {want}", got == want, f"실측 {got}")
    check("① 빈 파일은 no_frontmatter", CA.classify("") == "no_frontmatter")


def test_comment_section_is_excluded():
    """④ `## 코멘트` 는 사람이 쓴 것 — 그것만으로 valid 가 되면 안 된다."""
    md = "---\ntags: []\n---\n\n## 코멘트\n" + "사람이 쓴 긴 메모 " * 20
    check("④ 코멘트만 있으면 shell_only", CA.classify(md) == "shell_only", CA.classify(md))


# ── ②③⑦ 순서 ────────────────────────────────────────────────────────────────

def test_orphan_beats_content_classification():
    """🔴 실측이 증명한 순서 — 소스 없는 빈 문서는 `shell_only` 가 아니라 `orphan_stem` 이다."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/Zombie.md", "---\ntags: []\n---\n")      # 빈 본문 + 소스 없음
        r = fx.run()
        check("② 🔴 orphan_stem 으로 잡힌다", r["categories"]["orphan_stem"] == ["Source/Zombie.md"],
              str(r["categories"]))
        check("② shell_only 로 잡히지 **않는다**", r["categories"]["shell_only"] == [],
              str(r["categories"]["shell_only"]))

        # 소스를 주면 같은 내용이 shell_only 가 된다
        fx.src("Source/Zombie.h")
        r = fx.run()
        check("② 소스가 있으면 shell_only 로 내려간다",
              r["categories"]["shell_only"] == ["Source/Zombie.md"], str(r["categories"]))


def test_dir_named_beats_everything():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/Mission.md", VALID)
        (fx.context / "Source" / "Mission").mkdir()            # 같은 이름의 디렉토리
        fx.src("Source/Mission.h")
        r = fx.run()
        check("③ dir_named 가 내용·소스 판정보다 먼저",
              r["categories"]["dir_named"] == ["Source/Mission.md"], str(r["categories"]))


def test_domains_dir_is_out_of_scope():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("_domains/Mission/objects.md", "---\n---\n")
        r = fx.run()
        check("도메인 패키지는 범위 밖", r["total"] == 0, str(r["categories"]))


def test_prefix_form_is_not_a_match():
    """원전은 **정확한 stem** 만 대응으로 본다 — `UISubsystem.md` ↔ `UUISubsystem.h` 는 아니다.

    🔴 이 엄격함이 실측에서 값을 냈다: 좀비 11건을 찾았고, 전수 확인 결과 **prefix 형태로도
    없었다.** 느슨하게 잡았으면 그 11건이 조용히 valid 로 넘어갔다.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/UISubsystem.md", VALID)
        fx.src("Source/UUISubsystem.h")                        # prefix 붙은 다른 파일
        r = fx.run()
        check("prefix 형태는 대응이 아니다",
              r["categories"]["orphan_stem"] == ["Source/UISubsystem.md"], str(r["categories"]))


# ── ⑤⑥⑦ 복구 ────────────────────────────────────────────────────────────────

def test_repair_only_when_it_improves():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        # 고칠 수 있는 것: 펜스를 걷으면 valid 가 된다
        fx.md("Source/Good.md", "```markdown\n" + VALID.strip() + "\n```")
        fx.src("Source/Good.h")
        # 고칠 수 없는 것: 펜스를 걷어도 껍데기다
        fx.md("Source/Bad.md", "```markdown\n---\ntags: []\n---\n```")
        fx.src("Source/Bad.h")

        r = fx.run()
        check("⑤ 둘 다 pence_wrapped 로 잡혔다",
              sorted(r["categories"]["pence_wrapped"]) == ["Source/Bad.md", "Source/Good.md"],
              str(r["categories"]["pence_wrapped"]))

        plan = CA.plan_repair(fx.context, r)
        fixable = [rel for rel, _, _ in plan["fixable"]]
        check("⑤ 나아지는 것만 후보다", fixable == ["Source/Good.md"], str(plan["fixable"]))
        check("⑤ 나머지는 사유와 함께 거부", any("Bad" in rel for rel, _ in plan["refused"]),
              str(plan["refused"]))

        before_bad = (fx.context / "Source/Bad.md").read_text(encoding="utf-8")
        applied = CA.apply_repair(fx.context, plan)
        check("⑥ 고친 것은 하나", len(applied["fixed"]) == 1, str(applied))
        check("⑥ 🔴 거부된 파일은 안 건드렸다",
              (fx.context / "Source/Bad.md").read_text(encoding="utf-8") == before_bad)
        check("⑥ 고친 파일이 valid 가 됐다",
              CA.classify((fx.context / "Source/Good.md").read_text(encoding="utf-8")) == "valid")


def test_human_call_categories_are_never_repair_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/Zombie.md", VALID)                       # 소스 없음 → orphan_stem
        r = fx.run()
        plan = CA.plan_repair(fx.context, r)
        check("⑦ 🔴 orphan_stem 은 복구 후보가 아니다", plan["fixable"] == [], str(plan))
        check("⑦ 그리고 파일이 그대로 있다", (fx.context / "Source/Zombie.md").exists())


# ── ⑧ 읽기 실패 ──────────────────────────────────────────────────────────────

def test_unreadable_is_counted():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        p = fx.md("Source/Locked.md", VALID)
        fx.src("Source/Locked.h")
        p.chmod(0o000)
        try:
            r = fx.run()
            check("⑧ 읽기 실패를 세어서 돌려준다", len(r["unreadable"]) == 1, str(r["unreadable"]))
            check("⑧ 분류에는 안 들어간다", r["total"] == 0, str(r["categories"]))
        finally:
            p.chmod(0o644)


def test_missing_context_dir_is_a_fact():
    with tempfile.TemporaryDirectory() as tmp:
        r = CA.audit(Path(tmp) / "nope", Path(tmp))
        check("컨텍스트 디렉토리가 없으면 사실로 보고", bool(r.get("error")), str(r))
        check("리포트도 그것을 말한다", "진단 불가" in CA.format_report(r), CA.format_report(r)[:60])


# ── ⑨ 아카이브 이동 (`#160` 2단계) ───────────────────────────────────────────

class ArchFx(Fx):
    """`paths` 흉내 — `root`/`context`/`repo` 만 있으면 된다."""

    def __init__(self, tmp: Path):
        self.root = tmp
        super().__init__(tmp)


def test_archive_destination_is_outside_context():
    """🔴 이 기능의 핵심 — 목적지가 `context/` **안**이면 색인 범위를 벗어나지 못한다.

    우리 코퍼스가 실제로 그 상태였다(`context/_archive/project_alpha_md/`), 그래서 이 세션에
    같은 신호가 셋 나왔다(검색 1위 · 도메인 빈도 · orphan 101건).
    """
    with tempfile.TemporaryDirectory() as tmp:
        fx = ArchFx(Path(tmp))
        root = CA.archive_root(fx, "orphan_stem", "2026-08-14")
        check("⑨ 🔴 목적지가 context 밖이다",
              not str(root).startswith(str(fx.context)), str(root))
        check("⑨ 종류·날짜로 갈린다",
              root.parent.name == "orphan_md" and root.name == "2026-08-14", str(root))


def test_archive_plan_then_apply():
    with tempfile.TemporaryDirectory() as tmp:
        fx = ArchFx(Path(tmp))
        fx.md("Source/Zombie.md", VALID)                 # 소스 없음 → orphan_stem
        fx.md("Source/Live.md", VALID)
        fx.src("Source/Live.h")
        r = fx.run()

        plan = CA.plan_archive(fx, r, kinds=("orphan_stem",), day="2026-08-14")
        check("⑨ 좀비만 계획에 든다", [m[0] for m in plan["moves"]] == ["Source/Zombie.md"],
              str(plan["moves"]))
        check("⑨ 🔴 계획 단계에선 원본이 그대로 있다", (fx.context / "Source/Zombie.md").exists())

        applied = CA.apply_archive(fx, plan)
        check("⑨ 옮겼다", len(applied["moved"]) == 1 and not applied["failed"], str(applied))
        check("⑨ 원본이 사라졌다", not (fx.context / "Source/Zombie.md").exists())
        check("⑨ 목적지에 있다", Path(plan["moves"][0][1]).exists(), plan["moves"][0][1])
        check("⑨ 🔴 경로가 이름에 보존된다 (되돌릴 수 있다)",
              Path(plan["moves"][0][1]).name == "Source__Zombie.md",
              Path(plan["moves"][0][1]).name)
        check("⑨ 살아 있는 문서는 안 건드렸다", (fx.context / "Source/Live.md").exists())

        # 옮긴 뒤 다시 감사하면 사라져 있다
        r2 = fx.run()
        check("⑨ 재감사에서 orphan 이 0 이다", r2["categories"]["orphan_stem"] == [],
              str(r2["categories"]))


def test_archive_never_overwrites():
    """🔴 아카이브는 증거다 — 덮어쓰면 증거가 사라진다."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = ArchFx(Path(tmp))
        fx.md("Source/Zombie.md", VALID)
        r = fx.run()
        plan = CA.plan_archive(fx, r, day="2026-08-14")
        CA.apply_archive(fx, plan)

        # 같은 이름이 다시 생긴 상황
        fx.md("Source/Zombie.md", VALID)
        r2 = fx.run()
        plan2 = CA.plan_archive(fx, r2, day="2026-08-14")
        check("⑨ 🔴 목적지가 있으면 거부한다", plan2["moves"] == [], str(plan2["moves"]))
        check("⑨ 사유를 남긴다", any("이미 있다" in why for _, why in plan2["refused"]),
              str(plan2["refused"]))


def test_archive_kinds_are_opt_in():
    with tempfile.TemporaryDirectory() as tmp:
        fx = ArchFx(Path(tmp))
        fx.md("Source/Mission.md", VALID)
        (fx.context / "Source" / "Mission").mkdir()
        fx.src("Source/Mission.h")
        r = fx.run()
        plan = CA.plan_archive(fx, r, kinds=("orphan_stem",), day="d")
        check("⑨ 🔴 dir_named 는 고르지 않으면 안 옮긴다", plan["moves"] == [], str(plan["moves"]))
        plan2 = CA.plan_archive(fx, r, kinds=("dir_named",), day="d")
        check("⑨ 명시하면 계획에 든다", len(plan2["moves"]) == 1, str(plan2["moves"]))
        plan3 = CA.plan_archive(fx, r, kinds=("valid",), day="d")
        check("⑨ 아카이브 대상이 아닌 종류는 거부", plan3["moves"] == [] and plan3["refused"],
              str(plan3))


def main() -> int:
    for fn in (test_classify_each_category, test_comment_section_is_excluded,
               test_orphan_beats_content_classification, test_dir_named_beats_everything,
               test_domains_dir_is_out_of_scope, test_prefix_form_is_not_a_match,
               test_repair_only_when_it_improves,
               test_human_call_categories_are_never_repair_candidates,
               test_unreadable_is_counted, test_missing_context_dir_is_a_fact,
               test_archive_destination_is_outside_context, test_archive_plan_then_apply,
               test_archive_never_overwrites, test_archive_kinds_are_opt_in):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_context_audit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
