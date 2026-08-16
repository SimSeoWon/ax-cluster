"""컨텍스트 MD 진단 (소 3.4.1 · `#160`) — 원전 `context_audit.py` 이식분.

검증하는 것:

    ① 8분류가 각각 잡힌다
    ② [중요] **분류 순서** — `orphan_stem` 이 내용 분류보다 **먼저**다
       (실측으로 값이 증명됐다: 순서를 바꾸면 재생성할 소스가 없는 108건이 재생성 대상이 된다)
    ③ `dir_named` 가 내용 분류보다 먼저다
    ④ `## 코멘트` 이후는 평가에서 뺀다 (사람이 쓴 것 — 원전 판단)
    ⑤ [중요] 복구는 **걷어내서 나아지는 것만** — 아니면 거부한다
    ⑥ [중요] `apply_repair` 는 **계획이 고른 것 밖을 건드리지 않는다**
    ⑦ [중요] `dir_named`·`orphan_stem` 은 **옮기지 않는다** (복구 후보에 아예 안 들어간다)
    ⑧ 읽기 실패를 **세어서 돌려준다** (원전은 로그 한 줄만 남겼다)
    ⑨ 아카이브 — [중요] 목적지가 `context/` **밖**이고, 계획이 기본이고, **덮어쓰지 않는다**
    ⑩ σ.9.0 4분기 — [중요] 신호원이 **git 커밋 시각**이다(`mtime` 이면 갓 클론한 미러에서 전부 오판)

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
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


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
    """[중요] 실측이 증명한 순서 — 소스 없는 빈 문서는 `shell_only` 가 아니라 `orphan_stem` 이다."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/Zombie.md", "---\ntags: []\n---\n")      # 빈 본문 + 소스 없음
        r = fx.run()
        check("② [중요] orphan_stem 으로 잡힌다", r["categories"]["orphan_stem"] == ["Source/Zombie.md"],
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

    [중요] 이 엄격함이 실측에서 값을 냈다: 좀비 11건을 찾았고, 전수 확인 결과 **prefix 형태로도
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
        check("⑥ [중요] 거부된 파일은 안 건드렸다",
              (fx.context / "Source/Bad.md").read_text(encoding="utf-8") == before_bad)
        check("⑥ 고친 파일이 valid 가 됐다",
              CA.classify((fx.context / "Source/Good.md").read_text(encoding="utf-8")) == "valid")


def test_human_call_categories_are_never_repair_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/Zombie.md", VALID)                       # 소스 없음 → orphan_stem
        r = fx.run()
        plan = CA.plan_repair(fx.context, r)
        check("⑦ [중요] orphan_stem 은 복구 후보가 아니다", plan["fixable"] == [], str(plan))
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
    """[중요] 이 기능의 핵심 — 목적지가 `context/` **안**이면 색인 범위를 벗어나지 못한다.

    우리 코퍼스가 실제로 그 상태였다(`context/_archive/project_alpha_md/`), 그래서 이 세션에
    같은 신호가 셋 나왔다(검색 1위 · 도메인 빈도 · orphan 101건).
    """
    with tempfile.TemporaryDirectory() as tmp:
        fx = ArchFx(Path(tmp))
        root = CA.archive_root(fx, "orphan_stem", "2026-08-14")
        check("⑨ [중요] 목적지가 context 밖이다",
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
        check("⑨ [중요] 계획 단계에선 원본이 그대로 있다", (fx.context / "Source/Zombie.md").exists())

        applied = CA.apply_archive(fx, plan)
        check("⑨ 옮겼다", len(applied["moved"]) == 1 and not applied["failed"], str(applied))
        check("⑨ 원본이 사라졌다", not (fx.context / "Source/Zombie.md").exists())
        check("⑨ 목적지에 있다", Path(plan["moves"][0][1]).exists(), plan["moves"][0][1])
        check("⑨ [중요] 경로가 이름에 보존된다 (되돌릴 수 있다)",
              Path(plan["moves"][0][1]).name == "Source__Zombie.md",
              Path(plan["moves"][0][1]).name)
        check("⑨ 살아 있는 문서는 안 건드렸다", (fx.context / "Source/Live.md").exists())

        # 옮긴 뒤 다시 감사하면 사라져 있다
        r2 = fx.run()
        check("⑨ 재감사에서 orphan 이 0 이다", r2["categories"]["orphan_stem"] == [],
              str(r2["categories"]))


def test_archive_never_overwrites():
    """[중요] 아카이브는 증거다 — 덮어쓰면 증거가 사라진다."""
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
        check("⑨ [중요] 목적지가 있으면 거부한다", plan2["moves"] == [], str(plan2["moves"]))
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
        check("⑨ [중요] dir_named 는 고르지 않으면 안 옮긴다", plan["moves"] == [], str(plan["moves"]))
        plan2 = CA.plan_archive(fx, r, kinds=("dir_named",), day="d")
        check("⑨ 명시하면 계획에 든다", len(plan2["moves"]) == 1, str(plan2["moves"]))
        plan3 = CA.plan_archive(fx, r, kinds=("valid",), day="d")
        check("⑨ 아카이브 대상이 아닌 종류는 거부", plan3["moves"] == [] and plan3["refused"],
              str(plan3))


# ── ⑩ σ.9.0 빈 문서 4분기 ────────────────────────────────────────────────────

SHELL = "---\ntags: []\nrelated_classes:\n  - UThing: Source/Thing.h\n---\n"


def _git(cwd: Path, *args, env_extra=None):
    import os
    import subprocess
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)


def test_signal_is_git_time_not_mtime():
    """[중요] 원전은 `mtime` 을 쓰는데 우리 미러는 mtime 이 전부 전개 시각이다 (실측).

    실측 2026-08-15: 소스 400개 mtime 이 **전부 한 날짜**였고, 그래서 첫 판이 39건 **전부**
    `recent_but_empty` 로 나왔다 — 결함이 아니라 계측 오류였다. git 커밋 시각으로 바꾸니
    14 / 25 로 갈렸다. 이 테스트가 그 신호원을 고정한다.
    """
    from datetime import datetime, timedelta
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _git(fx.repo, "init", "-q")
        fx.src("Source/Thing.h")
        _git(fx.repo, "add", "-A")
        # [중요] 커밋은 **오래 전**으로 박고, 파일 mtime 은 **지금**이다 (클론 상황의 재현)
        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%S")
        _git(fx.repo, "commit", "-q", "-m", "old", "--date", old,
             env_extra={"GIT_COMMITTER_DATE": old})

        ts = CA.source_changed_at(fx.repo, "Source/Thing.h")
        mtime = (fx.repo / "Source/Thing.h").stat().st_mtime
        check("⑩ [중요] git 시각을 쓴다 (mtime 이 아니다)", ts is not None and ts < mtime - 86400,
              f"git={ts} mtime={mtime}")

        fx.md("Source/Thing.md", SHELL)
        r = fx.run()
        check("⑩ shell_only 로 잡혔다", r["categories"]["shell_only"] == ["Source/Thing.md"],
              str(r["categories"]))
        d = CA.post_unwrap_diagnosis(fx.context, fx.repo, recent_days=30, audit_result=r)
        check("⑩ [중요] 오래된 소스는 old_inactive 다 (mtime 이면 recent 로 오판)",
              len(d["categories"]["old_inactive"]) == 1
              and not d["categories"]["recent_but_empty"], str(d["categories"]))
        check("⑩ 분기 판정이 D-a", d["branch_decision"] == "D-a", d["branch_decision"])


def test_recent_source_empty_doc_is_a_defect():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _git(fx.repo, "init", "-q")
        fx.src("Source/Thing.h")
        _git(fx.repo, "add", "-A")
        _git(fx.repo, "commit", "-q", "-m", "now")        # 지금 커밋
        fx.md("Source/Thing.md", SHELL)
        d = CA.post_unwrap_diagnosis(fx.context, fx.repo, recent_days=30)
        check("⑩ [중요] 최근 소스 + 빈 문서 = 결함(recent_but_empty)",
              len(d["categories"]["recent_but_empty"]) == 1, str(d["categories"]))
        check("⑩ 분기 판정이 D-b", d["branch_decision"] == "D-b", d["branch_decision"])
        check("⑩ 며칠 전인지 싣는다",
              d["categories"]["recent_but_empty"][0]["info"].get("age_days") is not None,
              str(d["categories"]["recent_but_empty"][0]))


def test_link_present_but_file_missing_is_orphan_md():
    """[중요] 링크가 있는데 파일이 없으면 좀비 — 링크 자체가 없는 것과 **다르다**."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.md("Source/Thing.md", SHELL)                   # related_classes 는 있고 소스는 없다
        r = CA.audit(fx.context, fx.repo)
        # 소스가 없으니 감사에선 orphan_stem 이다 — 4분기는 shell_only 대상이므로 직접 넣는다
        d = CA.post_unwrap_diagnosis(fx.context, fx.repo,
                                     audit_result={"categories": {"shell_only": ["Source/Thing.md"]}})
        check("⑩ 링크 있음 + 파일 없음 → orphan_md",
              len(d["categories"]["orphan_md"]) == 1, str(d["categories"]))
        check("⑩ 분기 판정이 D-c", d["branch_decision"] == "D-c", d["branch_decision"])

        fx.md("Source/NoLink.md", "---\ntags: []\n---\n")
        d2 = CA.post_unwrap_diagnosis(fx.context, fx.repo,
                                      audit_result={"categories": {"shell_only": ["Source/NoLink.md"]}})
        check("⑩ 링크 없음 → no_source_link",
              len(d2["categories"]["no_source_link"]) == 1, str(d2["categories"]))


def test_frontmatter_link_beats_stem_fallback():
    """[주의] 폴백이 앞서면 **문서가 스스로 밝힌 근거**보다 우리 추측이 앞선다 (원전 순서)."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        cands = CA.extract_source_candidates(SHELL, fx.context / "Source/Thing.md", fx.context)
        check("⑩ frontmatter 링크가 먼저다", cands[0] == "Source/Thing.h", str(cands[:3]))
        check("⑩ 폴백도 뒤에 붙는다", any(c.endswith(".cpp") for c in cands), str(cands[:6]))


def main() -> int:
    for fn in (test_classify_each_category, test_comment_section_is_excluded,
               test_orphan_beats_content_classification, test_dir_named_beats_everything,
               test_domains_dir_is_out_of_scope, test_prefix_form_is_not_a_match,
               test_repair_only_when_it_improves,
               test_human_call_categories_are_never_repair_candidates,
               test_unreadable_is_counted, test_missing_context_dir_is_a_fact,
               test_archive_destination_is_outside_context, test_archive_plan_then_apply,
               test_archive_never_overwrites, test_archive_kinds_are_opt_in,
               test_signal_is_git_time_not_mtime, test_recent_source_empty_doc_is_a_defect,
               test_link_present_but_file_missing_is_orphan_md,
               test_frontmatter_link_beats_stem_fallback):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_context_audit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
