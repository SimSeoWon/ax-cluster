"""리더 검수 이식(`#135`) 계약 테스트 — [중요] **사람의 트리를 건드리지 않는가**가 핵심이다.

원전 `review_work_impl` 은 `git stash push -u` → `checkout main` → … → `stash pop` 을 하고
pop 실패는 **로그만** 남긴다. 우리에게 그 자리는 사람이 편집 중인 트리이고, 실측 2026-08-16 에
`.33` 에는 커밋 안 된 `.uasset` 이 실제로 있었다. [중요] **그래서 이 파일의 첫 번째 단정은
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
from master.work.branch_names import durable_branch as _dur   # noqa: E402

# [중요] `#319` — 조각 durable 은 `task/<work_id>/<task_id>` 다. 이 파일의 work 는 전부 `w1`
#    이므로 얇은 래퍼로 감아 호출부를 그대로 둔다(브랜치 계층이 바뀐 것이지 검사 의도가
#    바뀐 것이 아니다).
WORK = "w1"


def durable_branch(tid: str) -> str:
    return _dur(WORK, tid)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


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

    # 사람의 트리 상태 — main 위 + [중요] 미커밋 작업 (되살릴 수 없는 것을 흉내낸다)
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


# ── [중요] 사람의 트리 미접촉 ─────────────────────────────────────

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
        check("[중요] 미커밋 파일이 그대로 있다", live.exists(),
              "사람이 편집 중이던 파일이 사라졌다 — stash 를 옮겼다는 뜻")
        check("[중요] 미커밋 파일의 내용이 그대로다",
              live.exists() and live.read_text(encoding="utf-8") == before_body)
        check("[중요] 브랜치가 안 바뀌었다", g(repo, "branch", "--show-current").strip() == before_branch,
              f"{before_branch} → {g(repo, 'branch', '--show-current').strip()}")
        check("[중요] HEAD 가 안 움직였다", g(repo, "rev-parse", "HEAD").strip() == before_head)
        check("[중요] 워킹트리 상태가 그대로다", g(repo, "status", "--porcelain") == before_status)
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
        check("[중요] 검수 트리가 정리됐다", not Path(r.tree).exists(), r.tree)
        check("빌드는 주입 안 하면 skip", r.build_skipped and r.gate_passed)
        # [중요] 어디에도 push 하지 않았다 — 원격 main 이 그대로다
        remote_main = g(repo, "ls-remote", "origin", "refs/heads/main")
        base = g(repo, "rev-parse", "origin/main").strip()
        check("[중요] 원격 main 이 안 움직였다 (시뮬레이션이다)", base in remote_main, remote_main)
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
        check("[중요] 빌드 실패 시 Redmine 본문을 만들어 둔다 (직접 쓰지 않는다)",
              "리뷰 단계 빌드 실패" in r.redmine_note, r.redmine_note[:80])
        check("사람 트리는 여전히 무사하다", (repo / "Content" / "BP_Live.uasset").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 통합 실패 경로 — [중요] 통째 중단 ─────────────────────────────

def test_conflict_aborts_whole():
    root, repo, work, tasks = fixture(conflict=True)
    try:
        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks)
        check("충돌이면 ok=False", not r.ok)
        check("충돌로 표시된다", r.conflicts, str(r.error)[:120])
        check("[중요] 어느 브랜치에서 충돌했는지 말한다", durable_branch("t2") in (r.error or ""),
              r.error[:160])
        check("[중요] 부분 머지가 남지 않는다 (검수 트리 폐기)", not Path(r.tree).exists())
        check("사람 트리는 무사하다", (repo / "Content" / "BP_Live.uasset").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_missing_durable_stops():
    """[중요] verified 인데 durable 이 없으면 **넘어가지 않는다** — 빠진 채 성공으로 보이면 안 된다."""
    root, repo, work, tasks = fixture(missing_durable=True)
    try:
        r = R.review_work(repo, work_id="w1", work=work, tasks=tasks)
        check("durable 부재면 중단한다", not r.ok)
        check("어느 durable 인지 말한다", durable_branch("t2") in (r.error or ""), r.error[:160])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 정리 계획 — [중요] 지우지 않는다 ──────────────────────────────

def test_cleanup_plan_splits_by_reachability():
    root, repo, work, tasks = fixture()
    try:
        plan = R.plan_branch_cleanup(repo, tasks=tasks, work_id=WORK, target_branch="feature/w1")
        refs_keep = {ref for ref, _ in plan.keep}
        check("[중요] main 미도달 브랜치는 보존된다 (증거)",
              {durable_branch("t1"), durable_branch("t2"), "feature/w1"} <= refs_keep,
              str(refs_keep))
        check("지울 것이 없다", not plan.delete, str(plan.delete))
        check("보존 이유를 말한다", all("병합되지 않았다" in why for _, why in plan.keep))

        # main 에 병합하면 도달 가능해진다 → 그때는 지워도 된다
        g(repo, "checkout", "main")
        g(repo, "merge", "--no-ff", "-m", "merge", f"origin/{durable_branch('t1')}")
        g(repo, "push", "origin", "main")
        g(repo, "fetch", "origin")
        plan2 = R.plan_branch_cleanup(repo, tasks=tasks, work_id=WORK, target_branch="")
        check("병합된 durable 은 삭제 후보가 된다",
              durable_branch("t1") in {ref for ref, _ in plan2.delete}, str(plan2.delete))
        check("아직 미병합인 것은 여전히 보존", durable_branch("t2") in {r for r, _ in plan2.keep})
        cmds = plan2.commands()
        check("[중요] 계획은 **명령 문자열**만 낸다", all(c.startswith("git push origin --delete") for c in cmds),
              str(cmds))
        check("계획이 실제로 지우지는 않았다",
              durable_branch("t1") in g(repo, "ls-remote", "--heads", "origin"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cleanup_plan_fails_closed():
    """판정을 못 하면 **보존** 쪽으로 기운다."""
    root, repo, work, tasks = fixture()
    try:
        plan = R.plan_branch_cleanup(repo, tasks=tasks, work_id=WORK, target_branch="feature/w1",
                                     base_branch="존재하지-않는-브랜치")
        check("기준을 못 잡으면 오류로 남긴다", bool(plan.errors), str(plan.errors))
        check("[중요] 그때는 아무것도 삭제 후보가 아니다", not plan.delete)
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


def test_manifest_only_durable_is_not_merged():
    """[중요] `#319` ⓐ — 매니페스트만 든 조각 durable 은 머지하지 않는다 (사용자 결정 2026-08-27).

    실측 2026-08-27: 통합자가 코드를 **작업 브랜치**에 올리므로 조각 durable 에는
    `.ax/tasks/<T>/context.md` 하나만 남는다. 그것을 머지하면 인프라 파일이 게임 `main` 에
    박힌다 — NS 첫 완주의 미결과 같은 자리다.
    """
    root, repo, work, tasks = fixture()
    try:
        # t2 의 durable 을 **매니페스트 전용**으로 다시 만든다 (소스 변경 0)
        g(repo, "push", "origin", "--delete", durable_branch("t2"))
        g(repo, "checkout", "feature/w1")
        g(repo, "checkout", "-B", durable_branch("t2"))
        write(repo / ".ax" / "tasks" / "t2" / "context.md", "# 매니페스트\n")
        # [주의] `-A` 를 쓰면 픽스처의 **미커밋** Content/BP_Live.uasset 까지 담겨
        #    이 durable 이 `.ax/` 밖을 건드린 것이 된다 — 경로를 집어서 담는다.
        g(repo, "add", "-f", ".ax"); g(repo, "commit", "-m", "manifest only")
        g(repo, "push", "-f", "origin", durable_branch("t2"))
        g(repo, "checkout", "main")
        g(repo, "fetch", "origin")

        tree = root / "wt"
        g(repo, "worktree", "add", "--detach", str(tree), "origin/main")
        integ = R.integrate_durables(tree, work_id=WORK, target_branch="feature/w1",
                                     tasks=tasks, merge_label="[t]")
        check("통합 성공", integ.ok, integ.error)
        check("[중요] 소스를 든 t1 은 머지한다", durable_branch("t1") in integ.merged,
              str(integ.merged))
        check("[중요] 매니페스트 전용 t2 는 머지하지 않는다",
              durable_branch("t2") not in integ.merged, str(integ.merged))
        check("[중요] 안 했다고 **말한다** (빠뜨린 것과 구분된다)",
              durable_branch("t2") in integ.ax_only, str(integ.ax_only))
        got = g(tree, "ls-tree", "-r", "--name-only", "HEAD")
        check("[중요] 트리에 `.ax/` 가 없다 — 게임 main 에 인프라 파일을 넣지 않는다",
              ".ax/" not in got, got[:200])
        check("t1 의 소스는 들어왔다", "a.txt" in got, got[:200])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_missing_target_branch():
    # [중요] `#319` — 이름은 이제 **work_id 에서 유도**된다. 그래서 "없다" 는 work_id 까지
    #    없을 때만 성립한다. 유도가 되면 시작하고, 뒤에서 실물이 없어 실패한다(그건 다른 사유다).
    r = R.review_work(Path("/tmp"), work_id="", work={}, tasks=[])
    check("[중요] work_id 도 target_branch 도 없으면 시작도 안 한다",
          not r.ok and "작업 브랜치를 정할 수 없다" in r.error, r.error)
    check("  이름 규약을 사유에 적는다", "task/<work_id>/base" in r.error, r.error)
    check("[중요] work_id 만 있어도 유도한다 (저장값 없이)",
          R.work_base_branch("w9") == "task/w9/base")
    check("[중요] 저장된 target_branch 가 이긴다 (옛 work 호환)",
          R.work_base_branch("w9", {"target_branch": "feature/x"}) == "feature/x")


# ── 반려 ──────────────────────────────────────────────────────

class FakeApi:
    """큐 호출을 기록만 한다. [중요] 실 큐를 띄우지 않고 **계약**을 잰다."""

    def __init__(self, fail: bool = False):
        self.calls: list = []
        self.fail = fail

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if self.fail:
            raise RuntimeError("큐 무응답")
        return {"ok": True}


def test_reject_patches_and_keeps_branches():
    root, repo, work, tasks = fixture()
    try:
        work = dict(work, merge_status="ready_for_review", redmine_issue_id="42")
        api = FakeApi()
        d = R.reject_work(repo, work_id="w1", work=work, tasks=tasks,
                          reviewer="사람", reason="설계가 다르다", api=api)
        check("반려가 성공한다", d.ok, d.error)
        check("큐에 rejected 를 PATCH 한다",
              any(m == "PATCH" and p.get("merge_status") == "rejected" for m, _, p in api.calls),
              str(api.calls))
        check("결정에 검토자·사유가 실린다",
              any((p or {}).get("review_decision", {}).get("decided_by") == "사람"
                  and (p or {}).get("review_decision", {}).get("notes") == "설계가 다르다"
                  for _, _, p in api.calls))
        check("[중요] 원격 브랜치가 그대로 있다 (지우지 않았다)",
              durable_branch("t1") in g(repo, "ls-remote", "--heads", "origin")
              and durable_branch("t2") in g(repo, "ls-remote", "--heads", "origin"))
        check("[중요] 반려된 work 는 전부 보존된다 (main 도달 불가라 구조적으로)",
              not d.cleanup.delete and len(d.cleanup.keep) >= 3, str(d.cleanup.delete))
        check("Redmine 본문을 만들어 둔다 (직접 쓰지 않는다)", "[반려]" in d.redmine_note)
        check("반려 본문이 보존을 말한다", "보존" in d.redmine_note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_reject_idempotent_and_guarded():
    root, repo, work, tasks = fixture()
    try:
        d = R.reject_work(repo, work_id="w1", work=dict(work, merge_status="rejected"),
                          tasks=tasks, api=FakeApi())
        check("이미 반려면 no-op", d.ok and d.noop)
        d2 = R.reject_work(repo, work_id="w1", work=dict(work, merge_status="merged"),
                           tasks=tasks, api=FakeApi())
        check("[중요] 이미 머지된 work 는 반려 불가", not d2.ok and "merged" in d2.error)
        api = FakeApi(fail=True)
        d3 = R.reject_work(repo, work_id="w1", work=dict(work, merge_status="in_progress"),
                           tasks=tasks, api=api)
        check("[중요] 큐 갱신 실패를 조용히 넘기지 않는다", not d3.ok and "수동 갱신" in d3.error,
              d3.error)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 승인 — [중요] 기본값이 push 를 막는다 ─────────────────────────

def test_finalize_default_does_not_push():
    root, repo, work, tasks = fixture()
    try:
        before = g(repo, "ls-remote", "origin", "refs/heads/main")
        api = FakeApi()
        d = R.finalize_work(repo, work_id="w1", work=dict(work, merge_status="ready_for_review"),
                            tasks=tasks, reviewer="사람", api=api)
        check("confirm 없이도 통합은 된다", d.ok, d.error)
        check("[중요] push 하지 않았다", not d.pushed)
        check("[중요] 원격 main 이 그대로다", g(repo, "ls-remote", "origin", "refs/heads/main") == before)
        check("[중요] 큐 상태도 안 바꿨다 (아직 머지가 아니다)",
              not any(m == "PATCH" for m, _, _ in api.calls), str(api.calls))
        check("사람이 실행할 push 명령을 준다",
              any("push origin HEAD:main" in c for c in d.commands), str(d.commands))
        check("[중요] 통합 결과를 담은 트리를 남긴다 (명령의 대상)", Path(d.tree).exists(), d.tree)
        check("사람 트리는 무사하다", (repo / "Content" / "BP_Live.uasset").exists())
        shutil.rmtree(d.tree, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_confirm_pushes_and_then_cleanup_is_possible():
    root, repo, work, tasks = fixture()
    try:
        before = g(repo, "rev-parse", "origin/main").strip()
        live_before = (repo / "Content" / "BP_Live.uasset").read_text(encoding="utf-8")
        api = FakeApi()
        d = R.finalize_work(repo, work_id="w1",
                            # 분산 work 은 등재 때 Redmine 이슈를 갖는다 — ② 기재 경로를 태운다
                            work=dict(work, merge_status="ready_for_review",
                                      redmine_issue_id="226"),
                            tasks=tasks, reviewer="사람", confirm=True, api=api)
        check("승인하면 성공한다", d.ok, d.error)
        check("[중요] push 했다", d.pushed)
        g(repo, "fetch", "origin")
        check("[중요] 원격 main 이 실제로 움직였다",
              g(repo, "rev-parse", "origin/main").strip() != before)
        check("durable 둘이 통합됐다", len(d.merged_durables) == 2, str(d.merged_durables))
        check("큐에 merged 를 PATCH 한다",
              any(m == "PATCH" and (p or {}).get("merge_status") == "merged"
                  for m, _, p in api.calls))
        check("[중요] 머지 뒤에는 durable 이 삭제 후보가 된다 (도달 가능해졌다)",
              {durable_branch("t1"), durable_branch("t2")} <= {r for r, _ in d.cleanup.delete},
              str(d.cleanup.delete))
        # [중요] **계약이 바뀌었다** (사용자 결정 2026-08-21 — 원전 `finalize_work` 6단계 동등).
        #    2026-08-16 의 *"브랜치 삭제는 사람"* 을 뒤집었고, 안전 근거는 **가드가 둘**이다:
        #    ① `plan.delete` 는 도달 가능분만 ② 그 위에서 pre-push 훅(`#125`)이 같은 판정을
        #    한 번 더 한다. 그래서 여기서 재는 것은 「안 지웠나」가 아니라 **「도달 가능한
        #    것만 지웠나」**다.
        heads = g(repo, "ls-remote", "--heads", "origin")
        check("[중요] 도달 가능해진 durable 을 실제로 지웠다",
              durable_branch("t1") not in heads and durable_branch("t2") not in heads, heads)
        check("삭제 목록이 결과에 남는다 (안 보이는 산출물은 없는 것으로 읽힌다)",
              {durable_branch("t1"), durable_branch("t2")} <= set(d.deleted_branches),
              str(d.deleted_branches))
        check("[중요] 성공한 삭제를 명령으로 또 주지 않는다 (혼선 금지)",
              not any("--delete" in c for c in d.commands), str(d.commands))
        check("머지 커밋을 알아 둔다 (원전이 이슈에 적는 값)",
              len(d.merge_commit) == 40, d.merge_commit)
        check("[중요] Redmine 기재를 대행 경로로 보낸다 (키는 이 기계에 없다)",
              any(m == "POST" and p2 == "/api/v1/redmine/note" for m, p2, _ in api.calls),
              str([(m, p2) for m, p2, _ in api.calls]))
        note = next((p or {}) for m, p2, p in api.calls
                    if m == "POST" and p2 == "/api/v1/redmine/note")
        check("[주의] 상태는 「해결」이다 — 「완료」로 닫는 것은 사람이다",
              note.get("status_name") == "해결", str(note.get("status_name")))
        check("노트에 머지 커밋이 실린다", d.merge_commit in (note.get("notes") or ""))
        check("[중요] 사람의 미커밋 작업이 그대로다",
              (repo / "Content" / "BP_Live.uasset").read_text(encoding="utf-8") == live_before)
        check("[중요] 사람의 브랜치도 그대로 main 이다 (로컬은 pull 하면 된다)",
              g(repo, "branch", "--show-current").strip() == "main")
        check("push 했으면 트리를 정리한다", not Path(d.tree).exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_six_step_edges():
    """원전 6단계 동등의 **가장자리** (사용자 결정 2026-08-21).

    재는 것 셋:
      ① `confirm=False` 는 **아무것도 하지 않는다** — 지우지도, 기재하지도 않는다(fail-closed)
      ② Redmine 이슈가 없는 work 은 기재를 **건너뛰고도 성공**이다 (없는 곳에 쓰지 않는다)
      ③ [중요] 기재가 실패해도 **머지·정리는 유지**된다 — 되돌리면 잃는 것이 더 크다
    """
    # ① confirm=False
    root, repo, work, tasks = fixture()
    try:
        api = FakeApi()
        d = R.finalize_work(repo, work_id="w1",
                            work=dict(work, merge_status="ready_for_review",
                                      redmine_issue_id="226"),
                            tasks=tasks, reviewer="사람", confirm=False, api=api)
        check("[중요] confirm=False 는 push 하지 않는다", not d.pushed)
        check("[중요] confirm=False 는 브랜치를 지우지 않는다", d.deleted_branches == [],
              str(d.deleted_branches))
        check("[중요] confirm=False 는 Redmine 에 쓰지 않는다",
              not d.redmine_posted and not any(p2 == "/api/v1/redmine/note"
                                              for _m, p2, _p in api.calls))
        check("대신 사람이 실행할 push 명령을 준다",
              any("push" in c and "HEAD:main" in c for c in d.commands), str(d.commands))
        check("통합 트리는 남긴다 (그 안에 결과가 있다)", Path(d.tree).exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ② 이슈 없는 work
    root, repo, work, tasks = fixture()
    try:
        api = FakeApi()
        d = R.finalize_work(repo, work_id="w1", work=dict(work, merge_status="ready_for_review"),
                            tasks=tasks, confirm=True, api=api)
        check("이슈가 없으면 기재를 건너뛴다", not d.redmine_posted)
        check("[중요] 그래도 성공이다 — 없는 곳에 쓰지 않는 것은 실패가 아니다", d.ok, d.error)
        check("머지·정리는 그대로 됐다", d.pushed and len(d.deleted_branches) >= 2,
              f"{d.pushed} {d.deleted_branches}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ③ 기재 실패
    root, repo, work, tasks = fixture()
    try:
        class Boom(FakeApi):
            def __call__(self, method, path, payload=None):
                if path == "/api/v1/redmine/note":
                    raise RuntimeError("redmine down")
                return super().__call__(method, path, payload)
        api = Boom()
        d = R.finalize_work(repo, work_id="w1",
                            work=dict(work, merge_status="ready_for_review",
                                      redmine_issue_id="226"),
                            tasks=tasks, confirm=True, api=api)
        check("[중요] 기재 실패가 머지를 되돌리지 않는다", d.pushed and d.ok, d.error)
        check("[중요] 정리도 유지된다", len(d.deleted_branches) >= 2, str(d.deleted_branches))
        check("기재만 안 된 것으로 남는다", not d.redmine_posted)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_status_gate():
    root, repo, work, tasks = fixture()
    try:
        d = R.finalize_work(repo, work_id="w1", work=dict(work, merge_status="merged"),
                            tasks=tasks, api=FakeApi())
        check("이미 머지면 no-op", d.ok and d.noop)
        for bad in ("rejected", "cancelled", "build_failed"):
            db = R.finalize_work(repo, work_id="w1", work=dict(work, merge_status=bad),
                                 tasks=tasks, api=FakeApi())
            check(f"[중요] {bad} 상태는 승인 불가", not db.ok and bad in db.error, db.error)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_conflict_leaves_nothing():
    root, repo, work, tasks = fixture(conflict=True)
    try:
        before = g(repo, "ls-remote", "origin", "refs/heads/main")
        d = R.finalize_work(repo, work_id="w1", work=dict(work, merge_status="ready_for_review"),
                            tasks=tasks, confirm=True, api=FakeApi())
        check("충돌이면 실패한다", not d.ok)
        check("[중요] 원격 main 은 그대로다 (통째 중단)",
              g(repo, "ls-remote", "origin", "refs/heads/main") == before)
        check("[중요] 부분 머지 트리를 남기지 않는다", not Path(d.tree).exists())
        check("사람 트리는 무사하다", (repo / "Content" / "BP_Live.uasset").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)



# ── 🔴 정본 ⑺ — 라운드 종결: 작업 브랜치 전진 (사용자 확정 2026-09-04) ────────────────

class _Build:
    def __init__(self, passed=True):
        self.passed = passed

    def summary(self):
        return "BUILD OK" if self.passed else "BUILD FAILED"


def test_advance_bases_on_the_work_branch_not_main():
    """🔴 **`review_work` 와 기준이 다르다.** 그쪽은 `origin/main` 에 트리를 세우고(시뮬레이션),
    여기는 **`origin/<작업 브랜치>`** 에 세운다 — 전진분 위에 얹는 것이기 때문이다.

    실측 2026-09-04: 코드가 `main` 기준이라 정본과 갈려 있었다(사용자 지적).
    """
    root, repo, work, tasks = fixture()
    try:
        before = g(repo, "rev-parse", "origin/feature/w1").strip()
        a = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                           build_fn=lambda t: _Build(True))
        check("[중요] 기준이 작업 브랜치다", a.target_branch == "feature/w1", a.target_branch)
        check("  전진 전 tip 을 그 브랜치에서 읽는다", a.before == before, f"{a.before} vs {before}")
        check("  트리 이름이 review 와 갈린다", "ax-advance-w1" in a.tree, a.tree)
        check("  조각 둘을 머지했다", len(a.merged) == 2, str(a.merged))
        check("  tip 이 움직였다", a.head and a.head != a.before, f"{a.before}→{a.head}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_advance_does_not_push_without_confirm():
    """[중요] **`confirm=False` 가 기본이다** (`finalize_work` 와 같은 규약).

    [주의] 전진을 잘못 push 하면 **다음 라운드 조각이 그 위에서 갈라진다** — 되돌리려면
    사람이 브랜치를 되감아야 한다. 그래서 게이트가 필수다.
    """
    root, repo, work, tasks = fixture()
    try:
        before = g(repo, "rev-parse", "origin/feature/w1").strip()
        a = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                           build_fn=lambda t: _Build(True))
        check("[중요] push 하지 않았다", not a.pushed, a.summary)
        after = g(repo, "rev-parse", "origin/feature/w1").strip()
        check("  원격 브랜치가 그대로다", after == before, f"{before}→{after}")
        check("  머지·빌드까지는 됐다고 말한다", a.ok, a.summary)
        check("  실행할 명령을 돌려준다", any("push" in c for c in a.commands), str(a.commands))
        check("  트리를 남긴다 (사람이 그 안에서 본다)", Path(a.tree).exists(), a.tree)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_advance_pushes_on_confirm():
    root, repo, work, tasks = fixture()
    try:
        a = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                           build_fn=lambda t: _Build(True), confirm=True)
        check("[중요] 승인하면 전진한다", a.pushed and a.ok, a.summary)
        after = g(repo, "rev-parse", "origin/feature/w1").strip()
        check("  원격 브랜치가 전진했다", after == a.head, f"{after} vs {a.head}")
        check("  main 은 만지지 않는다",
              g(repo, "rev-parse", "origin/main").strip() != a.head, "main 이 움직였다")
        check("  push 했으면 트리를 지운다", not Path(a.tree).exists(), a.tree)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_advance_refuses_when_build_failed_or_unmeasured():
    """[중요] **확인 못 한 것은 통과가 아니다** — `build_fn` 미주입도 거절한다."""
    root, repo, work, tasks = fixture()
    try:
        a = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                           build_fn=lambda t: _Build(False), confirm=True)
        check("[중요] 빌드 실패면 전진하지 않는다", not a.pushed, a.summary)
        check("  사유를 말한다", "빌드가 통과하지 않았다" in (a.error or ""), a.error)
        b = R.advance_work(repo, work_id="w1", work=work, tasks=tasks, confirm=True)
        check("[중요] 빌드 미측정도 전진하지 않는다", not b.pushed, b.summary)
        check("  None 과 False 를 구분한다", b.build_passed is None, str(b.build_passed))
        check("  미확인이라고 말한다", "확인 못 한" in (b.error or "") or "미확인" in b.build_note,
              f"{b.error} / {b.build_note}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_advance_asks_the_canonical_question():
    """🔴 정본이 요구하는 물음 — *"버그가 있는가, 아니면 구조를 수정해야 하는가?"*"""
    root, repo, work, tasks = fixture()
    try:
        ok = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                            build_fn=lambda t: _Build(True))
        check("[중요] 버그·구조를 묻는다",
              "버그" in ok.question and "구조" in ok.question, ok.question)
        bad = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                             build_fn=lambda t: _Build(False))
        check("  빌드가 깨지면 다음 라운드를 안내한다",
              "다음 라운드" in bad.question, bad.question)
        none = R.advance_work(repo, work_id="w1", work=work, tasks=tasks)
        check("  미측정은 「재지 못했다」로 말한다", "재지 못했다" in none.question, none.question)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_advance_stops_whole_on_conflict():
    """[주의] 부분 머지를 남기지 않는다 — 그 상태로 빌드하면 무엇이 문제인지 알 수 없다."""
    root, repo, work, tasks = fixture(conflict=True)
    try:
        before = g(repo, "rev-parse", "origin/feature/w1").strip()
        a = R.advance_work(repo, work_id="w1", work=work, tasks=tasks,
                           build_fn=lambda t: _Build(True), confirm=True)
        check("[중요] 통째 중단한다", not a.ok and not a.pushed, a.summary)
        check("  충돌을 표시한다", a.conflicts, str(a.conflicts))
        check("  원격은 그대로다",
              g(repo, "rev-parse", "origin/feature/w1").strip() == before, "브랜치가 움직였다")
    finally:
        shutil.rmtree(root, ignore_errors=True)

def main() -> int:
    for fn in (test_advance_bases_on_the_work_branch_not_main,
               test_advance_does_not_push_without_confirm,
               test_advance_pushes_on_confirm,
               test_advance_refuses_when_build_failed_or_unmeasured,
               test_advance_asks_the_canonical_question,
               test_advance_stops_whole_on_conflict,
               test_order_and_split, test_missing_target_branch,
               test_manifest_only_durable_is_not_merged,
               test_human_tree_untouched, test_review_integrates_and_cleans_up,
               test_build_fn_injected, test_conflict_aborts_whole,
               test_missing_durable_stops, test_cleanup_plan_splits_by_reachability,
               test_cleanup_plan_fails_closed,
               test_reject_patches_and_keeps_branches, test_reject_idempotent_and_guarded,
               test_finalize_default_does_not_push,
               test_finalize_confirm_pushes_and_then_cleanup_is_possible,
               test_finalize_status_gate,
               test_finalize_six_step_edges, test_finalize_conflict_leaves_nothing):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_review: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
