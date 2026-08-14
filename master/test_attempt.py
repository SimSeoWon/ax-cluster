"""마스터측 attempt 계층 (Flow Y 배선) — 🔴 **실제 git 저장소·실제 worktree 로** 돌린다.

리포트 13 §14 · 14 §의 같은 교훈: **주입은 계약을 재고 실물을 재지 않는다.** 그래서 git 을
흉내내지 않는다 — `tmp` 에 bare origin + 정본 클론을 만들고 실제 `git worktree` 를 세운다.

검증하는 것:

    ① 🔴 **실패 응답도 attempt 에 올라간다** (성공·실패 무관 — §8.4)
    ② 🔴 정본 트리는 **안 움직인다** (색인기의 `merge --ff-only` 전제)
    ③ 작업 트리는 정본 **옆**이지 안이 아니다
    ④ 🔴 추적되지 않은 잔재가 있으면 **거부**한다 (`add -A` 가 삼키는 것을 막는다)
    ⑤ 경로 탈출(`..`)은 예외
    ⑥ 통과분은 durable 을 만든다 · ⑦ stale epoch 은 durable 을 안 움직인다
    ⑧ 같은 내용 재제출은 *"커밋할 변경이 없다"* 라는 **사실**로 보고된다

`.venv/bin/python master/test_attempt.py`
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import attempt as A                              # noqa: E402
from master.work.branch_names import durable_branch               # noqa: E402

PASS = FAIL = 0
WORK = "w1"
TASK = "t7"
SHOP = "HV0I6DL"
REL = "Source/ModularStage/Mission/MissionTask_Probe.cpp"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _run(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={r.returncode}: {r.stderr}")
    return (r.stdout or "").strip()


@dataclass
class Res:
    """`infer.Response` 중 이 계층이 실제로 읽는 것만."""

    task_id: str = TASK
    files: dict = field(default_factory=dict)
    base_commit: str = ""


@dataclass
class Paths:
    """`ProjectPaths` 중 이 계층이 읽는 것만 — `root` 와 `repo`."""

    root: Path

    @property
    def repo(self) -> Path:
        return self.root / "repo"


class Fixture:
    """bare origin + 정본 클론. 실제 git 이다."""

    def __init__(self, tmp: Path):
        self.origin = tmp / "origin.git"
        self.paths = Paths(root=tmp / "proj")
        self.paths.root.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)],
                       check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.paths.repo)],
                       check=True)
        p = self.paths.repo / REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("// base\n", encoding="utf-8")
        _run(self.paths.repo, "add", "-A")
        _run(self.paths.repo, "commit", "-q", "-m", "base")
        _run(self.paths.repo, "push", "-q", "origin", "main")
        self.base = _run(self.paths.repo, "rev-parse", "HEAD")


def _fx(tmp):
    return Fixture(Path(tmp))


# ── ①②③ 성공·실패 무관 push · 정본 불변 · 트리 위치 ───────────────────────────

def test_failed_response_is_pushed_anyway():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        head_before = _run(fx.paths.repo, "rev-parse", "HEAD")

        # 🔴 "실패한" 응답 — 이 계층은 판정하지 않는다. 그대로 올라가야 한다.
        res = Res(files={REL: "// 컴파일 안 되는 것\n#error broken\n"})
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[res], base_commit=fx.base,
                               remote="origin")
        check("① 실패 응답도 attempt 에 올라간다", p.ok, p.error)

        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("① attempt 가 원격에 있다", f"refs/heads/{p.attempt}" in refs, refs)
        check("① durable 은 아직 없다", durable_branch(TASK) not in refs, refs)

        body = _run(fx.paths.repo, "show", f"origin/{p.attempt}:{REL}")
        check("① 올라간 것이 그 본문이다", "#error broken" in body, body[:60])

        head_after = _run(fx.paths.repo, "rev-parse", "HEAD")
        check("② 정본 HEAD 가 안 움직였다", head_before == head_after,
              f"{head_before[:8]} → {head_after[:8]}")
        check("② 정본 트리가 청결하다", _run(fx.paths.repo, "status", "--porcelain") == "")

        wt = A.tree_path(fx.paths, WORK)
        check("③ 작업 트리는 정본 옆이다", wt.parent == fx.paths.root, str(wt))
        check("③ 작업 트리가 정본 안이 아니다",
              not str(wt).startswith(str(fx.paths.repo) + "/"), str(wt))


# ── ④ 잔재는 삼키지 않고 거부한다 ─────────────────────────────────────────────

def test_stray_untracked_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        A.ensure_attempt_tree(fx.paths, WORK, at_commit=fx.base)
        stray = A.tree_path(fx.paths, WORK) / "leftover.txt"
        stray.write_text("이전 라운드의 잔재\n", encoding="utf-8")

        wt = A.ensure_attempt_tree(fx.paths, WORK, at_commit=fx.base)
        check("④ 잔재가 있으면 거부한다", not wt.ok, "통과해 버렸다")
        check("④ 거부 사유에 파일명이 있다", "leftover.txt" in wt.error, wt.error)
        check("④ 🔴 잔재를 지우지 않았다", stray.exists(), "지워 버렸다")

        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={REL: "// x\n"})],
                               base_commit=fx.base, remote="origin")
        check("④ push 도 그 자리에서 멈춘다", not p.ok and "잔재" in p.error, p.error)


# ── ⑤ 경로 탈출 ───────────────────────────────────────────────────────────────

def test_path_escape_raises():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        fn = A.apply_responses([Res(files={"../../etc/evil": "x"})])
        try:
            fn(A.tree_path(fx.paths, WORK), "")
            check("⑤ 경로 탈출은 예외다", False, "예외가 안 났다")
        except A.AttemptError:
            check("⑤ 경로 탈출은 예외다", True)


def test_empty_response_is_a_fact():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={})],
                               base_commit=fx.base, remote="origin")
        check("⑤ 빈 응답은 사실로 보고된다", not p.ok and "비었다" in p.error, p.error)


# ── ⑥⑦ durable 은 검증 통과분만 · epoch 게이트 ────────────────────────────────

def test_verified_creates_durable():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={REL: "// 통과분\n"})],
                               base_commit=fx.base, remote="origin")
        check("⑥ attempt 선행", p.ok, p.error)

        r = A.merge_verified(fx.paths, work_id=WORK, task_id=TASK, attempt=p.attempt,
                             submit_epoch=1, current_epoch=1, remote="origin")
        check("⑥ merge 됐다", r.get("merged"), str(r))
        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("⑥ durable 이 생겼다", f"refs/heads/{durable_branch(TASK)}" in refs, refs)


def test_stale_epoch_leaves_durable_alone():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={REL: "// 좀비\n"})],
                               base_commit=fx.base, remote="origin")
        r = A.merge_verified(fx.paths, work_id=WORK, task_id=TASK, attempt=p.attempt,
                             submit_epoch=1, current_epoch=2, remote="origin")
        check("⑦ stale epoch 은 거부된다", not r.get("merged"), str(r))
        check("⑦ 사유가 epoch 이다", "stale_epoch" in r.get("reason", ""), str(r))
        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("⑦ 🔴 durable 이 안 생겼다 (부작용 0)",
              durable_branch(TASK) not in refs, refs)


# ── ⑧ 변경 없음은 사실이다 ────────────────────────────────────────────────────

def test_no_change_is_reported_as_fact():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={REL: "// base\n"})],
                               base_commit=fx.base, remote="origin")
        check("⑧ 같은 내용은 사실로 보고된다",
              not p.ok and "변경이 없다" in p.error, p.error)


# ── 소 1.2.4 원격 정리 — 🔴 도달 가능한 것만 (사용자 결정 2026-08-14) ──────────

def test_cleanup_keeps_unmerged_evidence():
    """🔴 이 저장소가 실제로 물릴 뻔한 것: attempt 가 **미병합인 채** 쌓인 상태."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={REL: "// 실패한 시도\n"})],
                               base_commit=fx.base, remote="origin")
        check("정리: attempt 선행", p.ok, p.error)

        plan = A.plan_remote_cleanup(fx.paths, remote="origin")
        check("🔴 미병합 attempt 는 삭제 대상이 아니다", not plan.delete,
              str(plan.delete))
        check("보존 목록에 들어간다", any(p.attempt == r for r, _ in plan.keep),
              str(plan.keep))
        check("사유가 「병합되지 않았다」 다",
              any("병합되지 않았다" in why for _, why in plan.keep), str(plan.keep))

        # 실제로 지우려 해도 대상이 없으므로 아무것도 안 지운다
        A.apply_remote_cleanup(fx.paths, plan, remote="origin")
        check("🔴 아무것도 지우지 않았다", not plan.deleted, str(plan.deleted))
        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("attempt 가 원격에 살아 있다", p.attempt in refs, refs)


def test_cleanup_deletes_merged_attempt():
    """병합되면 지울 수 있게 된다 — 영구 누적이 아니라는 성질."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        p = A.push_attempt_for(fx.paths, work_id=WORK, task_id=TASK, workshop=SHOP,
                               ts="t1", responses=[Res(files={REL: "// 통과분\n"})],
                               base_commit=fx.base, remote="origin")
        A.merge_verified(fx.paths, work_id=WORK, task_id=TASK, attempt=p.attempt,
                         submit_epoch=1, current_epoch=1, remote="origin")
        # durable 을 main 으로 올린다 — 요청자·사람이 하는 그 단계
        _run(fx.paths.repo, "push", "-q", "origin",
             f"{durable_branch(TASK)}:main")

        plan = A.plan_remote_cleanup(fx.paths, remote="origin")
        check("🔴 병합된 attempt 는 삭제 대상이다",
              any(p.attempt == r for r, _ in plan.delete), str(plan.delete))
        check("⚠️ durable 은 삭제 대상이 아니다 (원전대로 보존)",
              not any(r.startswith("task/") for r, _ in plan.delete), str(plan.delete))
        check("durable 은 세어서 보고된다",
              any(r == durable_branch(TASK) for r, _ in plan.durable), str(plan.durable))

        A.apply_remote_cleanup(fx.paths, plan, remote="origin")
        check("실제로 지워졌다", p.attempt in plan.deleted, str(plan.deleted))
        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("attempt 가 원격에서 사라졌다", p.attempt not in refs, refs)
        check("🔴 durable 은 살아 있다", durable_branch(TASK) in refs, refs)


def test_cleanup_without_tracking_deletes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        plan = A.plan_remote_cleanup(fx.paths, remote="origin", base_branch="nosuchbranch")
        check("🔴 기준 브랜치가 없으면 아무것도 안 지운다", not plan.delete, str(plan.delete))
        check("오류로 보고한다", bool(plan.errors), str(plan.errors))


# ── 가드 자체 — 🔴 **원본은 저장소 안이고, 설치 여부를 스스로 말한다** ──────────

def test_hook_source_is_in_repo_and_installs():
    """🔴 `.git/hooks/` 는 추적되지 않는다 — 원본이 저장소에 없으면 클론을 다시 만들 때
    가드가 **조용히 사라진다.** 그것이 가드에는 최악의 실패다."""
    check("훅 원본이 저장소 안에 있다", A.HOOK_SOURCE.is_file(), str(A.HOOK_SOURCE))

    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        st = A.hook_status(fx.paths)
        check("설치 전에는 없다고 말한다", not st["installed"], st["reason"])

        st = A.install_hook(fx.paths)
        check("설치 후 원본과 같다", st["current"], st["reason"])
        check("실행 가능하다", st["executable"], st["reason"])

        # 손으로 고친 경우를 잡아내나
        A.hook_target(fx.paths).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        st = A.hook_status(fx.paths)
        check("🔴 손으로 고친 것을 잡아낸다", not st["current"], st["reason"])


def main() -> int:
    for fn in (test_hook_source_is_in_repo_and_installs,
               test_failed_response_is_pushed_anyway, test_stray_untracked_is_refused,
               test_path_escape_raises, test_empty_response_is_a_fact,
               test_verified_creates_durable, test_stale_epoch_leaves_durable_alone,
               test_no_change_is_reported_as_fact,
               test_cleanup_keeps_unmerged_evidence, test_cleanup_deletes_merged_attempt,
               test_cleanup_without_tracking_deletes_nothing):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_attempt: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
