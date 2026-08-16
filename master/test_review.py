"""리더 검수 이식(`#135`) 계약 테스트 — 🔴 **사람의 트리를 건드리지 않는가**가 핵심이다.

원전 `review_work_impl` 은 `git stash push -u` → `checkout main` → … → `stash pop` 을 하고
pop 실패는 **로그만** 남긴다. 우리에게 그 자리는 사람이 편집 중인 트리이고, 실측 2026-08-16 에
`.33` 에는 커밋 안 된 `.uasset` 이 실제로 있었다. 🔴 **그래서 이 파일의 첫 번째 단정은
「검수를 돌려도 미커밋 작업이 그대로 있는가」다** — 통합이 되는지보다 그쪽이 먼저다.

실행: .venv/bin/python master/test_review.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import review as R          # noqa: E402
from master.work.branch_names import durable_branch   # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def g(cwd, *args, check_rc: bool = True) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check_rc and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={r.returncode}: {r.stderr}")
    return (r.stdout or "") + (r.stderr or "")


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fixture(*, conflict: bool = False, missing_durable: bool = False):
    """bare 원격 + 사람의 클론. feature 하나 + durable 둘."""
    root = Path(tempfile.mkdtemp(prefix="ax-review-t-"))
    bare = root / "origin.git"
    g(root, "init", "--bare", "-b", "main", str(bare))
    repo = root / "repo"
    g(root, "clone", str(bare), str(repo))
    write(repo / "base.txt", "base\n")
    g(repo, "add", "-A"); g(repo, "commit", "-m", "base"); g(repo, "push", "origin", "main")

    # feature — 골조/글루 (durable 없는 완전구현이 사는 자리)
    g(repo, "checkout", "-b", "feature/w1")
    write(repo / "glue.txt", "glue\n")
    g(repo, "add", "-A"); g(repo, "commit", "-m", "glue"); g(repo, "push", "origin", "feature/w1")

    # durable 둘 — feature 위에서 각자 다른 파일
    for tid, fname in (("t1", "a.txt"), ("t2", "b.txt")):
        g(repo, "checkout", "feature/w1")
        g(repo, "checkout", "-b", durable_branch(tid))
        write(repo / fname, f"{tid}\n")
        if conflict and tid == "t2":
            write(repo / "a.txt", "t2 가 같은 파일을 다르게 쓴다\n")   # t1 과 충돌
        g(repo, "add", "-A"); g(repo, "commit", "-m", tid)
        g(repo, "push", "origin", durable_branch(tid))

    if missing_durable:
        g(repo, "push", "origin", "--delete", durable_branch("t2"))

    # 사람의 트리 상태 — main 위 + 🔴 미커밋 작업 (되살릴 수 없는 것을 흉내낸다)
    g(repo, "checkout", "main")
    write(repo / "Content" / "BP_Live.uasset", "사람이 편집 중인 바이너리\n")
    g(repo, "fetch", "origin")
    tasks = [{"task_id": "t1", "distribution_mode": "push", "status": "verified",
              "hierarchy_level": 0, "priority": 0, "created": "1"},
             {"task_id": "t2", "distribution_mode": "push", "status": "verified",
              "hierarchy_level": 0, "priority": 0, "created": "2"},
             {"task_id": "t3", "distribution_mode": "push", "status": "failed"}]
    work = {"target_branch": "feature/w1", "distribution_mode": "push", "title": "테스트 work"}
    return root, repo, work, tasks


# ── 🔴 사람의 트리 미접촉 ─────────────────────────────────────

def test_human_tree_untouched():
    root, repo, work, tasks = fixture()
    try:
        live = repo / "Content" / "BP_Live.uasset"
        before_head = g(repo, "rev-parse", "HEAD").strip()
        before_branch = g(repo, "branch", "--show-current").strip()
        before_body = live.read_text(encoding="utf-8")
        before_status = g(repo, "status", "--porcelain")

        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks)

        check("검수가 성공한다", r.ok, f"error={r.error}")
        check("🔴 미커밋 파일이 그대로 있다", live.exists(),
              "사람이 편집 중이던 파일이 사라졌다 — stash 를 옮겼다는 뜻")
        check("🔴 미커밋 파일의 내용이 그대로다",
              live.exists() and live.read_text(encoding="utf-8") == before_body)
        check("🔴 브랜치가 안 바뀌었다", g(repo, "branch", "--show-current").strip() == before_branch,
              f"{before_branch} → {g(repo, 'branch', '--show-current').strip()}")
        check("🔴 HEAD 가 안 움직였다", g(repo, "rev-parse", "HEAD").strip() == before_head)
        check("🔴 워킹트리 상태가 그대로다", g(repo, "status", "--porcelain") == before_status)
        check("stash 를 만들지 않았다", not g(repo, "stash", "list").strip(),
              g(repo, "stash", "list"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_review_integrates_and_cleans_up():
    root, repo, work, tasks = fixture()
    try:
        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks)
        check("durable 둘이 통합됐다", r.merged_durables == [durable_branch("t1"), durable_branch("t2")],
              str(r.merged_durables))
        check("verified 아닌 task 는 skip 으로 보고된다",
              [s["task_id"] for s in r.skipped] == ["t3"], str(r.skipped))
        check("변경 파일에 feature 글루와 durable 산출물이 모두 있다",
              {"glue.txt", "a.txt", "b.txt"} <= set(r.files_changed), str(r.files_changed))
        check("🔴 검수 트리가 정리됐다", not Path(r.tree).exists(), r.tree)
        check("빌드는 주입 안 하면 skip", r.build_skipped and r.gate_passed)
        # 🔴 어디에도 push 하지 않았다 — 원격 main 이 그대로다
        remote_main = g(repo, "ls-remote", "origin", "refs/heads/main")
        base = g(repo, "rev-parse", "origin/main").strip()
        check("🔴 원격 main 이 안 움직였다 (시뮬레이션이다)", base in remote_main, remote_main)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_build_fn_injected():
    root, repo, work, tasks = fixture()
    try:
        seen = {}

        def build(tree):
            seen["tree"] = Path(tree)
            seen["has_merge"] = (Path(tree) / "a.txt").exists() and (Path(tree) / "b.txt").exists()
            return {"ok": False, "detail": "컴파일 에러 3건"}

        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks, build_fn=build)
        check("빌드가 **통합된 트리 위에서** 불린다", seen.get("has_merge") is True)
        check("빌드 실패가 게이트를 막는다", not r.build_passed and not r.gate_passed)
        check("빌드를 돌렸으면 skip 이 아니다", not r.build_skipped)
        check("🔴 빌드 실패 시 Redmine 본문을 만들어 둔다 (직접 쓰지 않는다)",
              "리뷰 단계 빌드 실패" in r.redmine_note, r.redmine_note[:80])
        check("사람 트리는 여전히 무사하다", (repo / "Content" / "BP_Live.uasset").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 통합 실패 경로 — 🔴 통째 중단 ─────────────────────────────

def test_conflict_aborts_whole():
    root, repo, work, tasks = fixture(conflict=True)
    try:
        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks)
        check("충돌이면 ok=False", not r.ok)
        check("충돌로 표시된다", r.conflicts, str(r.error)[:120])
        check("🔴 어느 브랜치에서 충돌했는지 말한다", durable_branch("t2") in (r.error or ""),
              r.error[:160])
        check("🔴 부분 머지가 남지 않는다 (검수 트리 폐기)", not Path(r.tree).exists())
        check("사람 트리는 무사하다", (repo / "Content" / "BP_Live.uasset").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_missing_durable_stops():
    """🔴 verified 인데 durable 이 없으면 **넘어가지 않는다** — 빠진 채 성공으로 보이면 안 된다."""
    root, repo, work, tasks = fixture(missing_durable=True)
    try:
        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks)
        check("durable 부재면 중단한다", not r.ok)
        check("어느 durable 인지 말한다", durable_branch("t2") in (r.error or ""), r.error[:160])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 정리 계획 — 🔴 지우지 않는다 ──────────────────────────────

def test_cleanup_plan_splits_by_reachability():
    root, repo, work, tasks = fixture()
    try:
        plan = R.plan_branch_cleanup(repo, tasks=tasks, target_branch="feature/w1")
        refs_keep = {ref for ref, _ in plan.keep}
        check("🔴 main 미도달 브랜치는 보존된다 (증거)",
              {durable_branch("t1"), durable_branch("t2"), "feature/w1"} <= refs_keep,
              str(refs_keep))
        check("지울 것이 없다", not plan.delete, str(plan.delete))
        check("보존 이유를 말한다", all("병합되지 않았다" in why for _, why in plan.keep))

        # main 에 병합하면 도달 가능해진다 → 그때는 지워도 된다
        g(repo, "checkout", "main")
        g(repo, "merge", "--no-ff", "-m", "merge", f"origin/{durable_branch('t1')}")
        g(repo, "push", "origin", "main")
        g(repo, "fetch", "origin")
        plan2 = R.plan_branch_cleanup(repo, tasks=tasks, target_branch="")
        check("병합된 durable 은 삭제 후보가 된다",
              durable_branch("t1") in {ref for ref, _ in plan2.delete}, str(plan2.delete))
        check("아직 미병합인 것은 여전히 보존", durable_branch("t2") in {r for r, _ in plan2.keep})
        cmds = plan2.commands()
        check("🔴 계획은 **명령 문자열**만 낸다", all(c.startswith("git push origin --delete") for c in cmds),
              str(cmds))
        check("계획이 실제로 지우지는 않았다",
              durable_branch("t1") in g(repo, "ls-remote", "--heads", "origin"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cleanup_plan_fails_closed():
    """판정을 못 하면 **보존** 쪽으로 기운다."""
    root, repo, work, tasks = fixture()
    try:
        plan = R.plan_branch_cleanup(repo, tasks=tasks, target_branch="feature/w1",
                                     base_branch="존재하지-않는-브랜치")
        check("기준을 못 잡으면 오류로 남긴다", bool(plan.errors), str(plan.errors))
        check("🔴 그때는 아무것도 삭제 후보가 아니다", not plan.delete)
        check("전부 보존으로 분류된다", len(plan.keep) >= 3, str(len(plan.keep)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 순수 로직 ─────────────────────────────────────────────────

def test_order_and_split():
    ordered = R.order_verified([
        {"task_id": "c", "hierarchy_level": 1, "priority": 0, "created": "3"},
        {"task_id": "a", "hierarchy_level": 0, "priority": 5, "created": "2"},
        {"task_id": "b", "hierarchy_level": 0, "priority": 9, "created": "1"},
    ])
    check("계층 오름 → 우선순위 내림 → 생성 오름",
          [t["task_id"] for t in ordered] == ["b", "a", "c"], str([t["task_id"] for t in ordered]))
    v, s = R.split_push_tasks([
        {"task_id": "x", "distribution_mode": "push", "status": "verified"},
        {"task_id": "y", "distribution_mode": "push", "status": "failed"},
        {"task_id": "z", "distribution_mode": "pull", "status": "verified"},
    ])
    check("push 모드만 본다", [t["task_id"] for t in v] == ["x"] and
          [d["task_id"] for d in s] == ["y"], f"{v} {s}")
    check("빈 입력도 안전", R.split_push_tasks(None) == ([], []))


def test_missing_target_branch():
    r = R.review_work(Path("/tmp"), work_id="w", work={}, tasks=[])
    check("target_branch 없으면 시작도 안 한다", not r.ok and "target_branch" in r.error, r.error)


def main() -> int:
    for fn in (test_order_and_split, test_missing_target_branch,
               test_human_tree_untouched, test_review_integrates_and_cleans_up,
               test_build_fn_injected, test_conflict_aborts_whole,
               test_missing_durable_stops, test_cleanup_plan_splits_by_reachability,
               test_cleanup_plan_fails_closed):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_review: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
