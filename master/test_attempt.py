"""마스터측 attempt 계층 (Flow Y 배선) — [중요] **실제 git 저장소·실제 worktree 로** 돌린다.

리포트 13 §14 · 14 §의 같은 교훈: **주입은 계약을 재고 실물을 재지 않는다.** 그래서 git 을
흉내내지 않는다 — `tmp` 에 bare origin + 정본 클론을 만들고 실제 `git worktree` 를 세운다.

검증하는 것:

    ① [중요] **실패 응답도 attempt 에 올라간다** (성공·실패 무관 — §8.4)
    ② [중요] 정본 트리는 **안 움직인다** (색인기의 `merge --ff-only` 전제)
    ③ 작업 트리는 정본 **옆**이지 안이 아니다
    ④ [중요] 추적되지 않은 잔재가 있으면 **거부**한다 (`add -A` 가 삼키는 것을 막는다)
    ⑤ 경로 탈출(`..`)은 예외
    ⑥ 통과분은 durable 을 만든다 · ⑦ stale epoch 은 durable 을 안 움직인다
    ⑧ 같은 내용 재제출은 *"커밋할 변경이 없다"* 라는 **사실**로 보고된다

`.venv/bin/python master/test_attempt.py`
"""
from __future__ import annotations

import subprocess
import sys
import pathlib
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
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


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

# [중요] **`push_attempt_for`·`merge_verified`·`apply_responses` 검사 7개가 여기 있었다 —
#    `#327` 로 그 주제가 사라져 같이 걷었다** (2026-08-28). 대상이 없는 것을 재는 검사는
#    남기지 않는다(`#323` 에서 같은 판단을 했다).
#    걷은 검사: 실패도 push 된다 · 미추적 잔재 거부 · 경로 탈출 거부 · 빈 응답도 사실이다 ·
#    검증분이 durable 을 만든다 · stale epoch 이 durable 을 안 건드린다 · 무변경도 사실이다.
#    [주의] **그중 「경로 탈출 거부」는 성질이 다르다** — 보안 성격이라 통합자 경로에도 같은
#    방어가 있어야 한다. `integrate.apply_one` → `skeleton_gate.place` 가 해시 대조까지 하는
#    자리이고, `test_integrate` 가 그것을 잰다.

def test_dead_wiring_stays_dead():
    """[중요] `#327` — 걷어낸 배선이 되살아나지 않는지 **이름으로** 잰다.

    `#323` 의 `test_no_ssh_surface_left` 와 같은 자리다: 지운 경로가 조용히 돌아오면
    「안 도는 지도」가 다시 생긴다.
    """
    for gone in ("push_attempt_for", "merge_verified", "apply_responses",
                 "ensure_attempt_tree", "tree_path", "AttemptTree", "Pushed"):
        check(f"attempt.{gone} 가 없다", not hasattr(A, gone), "되살아났다")
    from master.work import coordinator as _C
    check("coordinator.run_round 가 없다", not hasattr(_C, "run_round"), "되살아났다")
    # [주의] **남아야 하는 것도 같이 잰다** — 과잉 철거를 잡는다
    for live in ("plan_remote_cleanup", "apply_remote_cleanup",
                 "hook_target", "hook_status", "install_hook", "WRITE_REMOTE"):
        check(f"attempt.{live} 는 산다", hasattr(A, live), "같이 걷혔다")
    for live in ("assign_attempt", "push_attempt", "verify_and_merge", "cleanup_attempts"):
        check(f"coordinator.{live} 는 산다 (selftest 드라이런이 쓴다)",
              hasattr(_C, live), "같이 걷혔다")


def _make_attempt(fx, *, task_id=TASK, ts="t1", body="// 시도\n") -> str:
    """attempt 브랜치 하나를 **직접 git 으로** 만든다 (`#327` 이후).

    [중요] 종전에는 `push_attempt_for` 로 만들었는데 그 배선이 걷혔다. 정리(`plan_remote_cleanup`)
    는 **살아 있고**, 그것이 재는 것은 *"attempt 브랜치가 원격에 있을 때 무엇을 지울 수 있나"*
    이지 *"그 브랜치를 누가 만들었나"* 가 아니다 — 그래서 만드는 쪽만 갈아 끼운다.
    """
    from master.work.branch_names import attempt_branch
    br = attempt_branch(WORK, task_id, SHOP, ts)
    repo = fx.paths.repo
    _run(repo, "checkout", "-q", "-B", br, fx.base)
    f = pathlib.Path(repo) / REL
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    _run(repo, "add", "-A", REL)
    _run(repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", br)
    _run(repo, "push", "-q", "origin", br)
    _run(repo, "checkout", "-q", "main")
    return br


def test_cleanup_keeps_unmerged_evidence():
    """[중요] 이 저장소가 실제로 물릴 뻔한 것: attempt 가 **미병합인 채** 쌓인 상태."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        att = _make_attempt(fx, body="// 실패한 시도\n")

        plan = A.plan_remote_cleanup(fx.paths, remote="origin")
        check("[중요] 미병합 attempt 는 삭제 대상이 아니다", not plan.delete,
              str(plan.delete))
        check("보존 목록에 들어간다", any(att == r for r, _ in plan.keep),
              str(plan.keep))
        check("사유가 「병합되지 않았다」 다",
              any("병합되지 않았다" in why for _, why in plan.keep), str(plan.keep))

        # 실제로 지우려 해도 대상이 없으므로 아무것도 안 지운다
        A.apply_remote_cleanup(fx.paths, plan, remote="origin")
        check("[중요] 아무것도 지우지 않았다", not plan.deleted, str(plan.deleted))
        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("attempt 가 원격에 살아 있다", att in refs, refs)


def test_cleanup_deletes_merged_attempt():
    """병합되면 지울 수 있게 된다 — 영구 누적이 아니라는 성질."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        att = _make_attempt(fx, body="// 통과분\n")
        # 통과분을 durable 로 올린다 — 종전엔 `merge_verified` 가 했고, 지금은 통합자가
        # 작업 브랜치로 올린다(`#319` ⓐ). 여기서는 **정리가 볼 상태**만 만들면 된다.
        dur = durable_branch(WORK, TASK)
        _run(fx.paths.repo, "push", "-q", "origin", f"{att}:{dur}")
        _run(fx.paths.repo, "push", "-q", "origin", f"{att}:main")

        plan = A.plan_remote_cleanup(fx.paths, remote="origin")
        check("[중요] 병합된 attempt 는 삭제 대상이다",
              any(att == r for r, _ in plan.delete), str(plan.delete))
        check("[주의] durable 은 삭제 대상이 아니다 (원전대로 보존)",
              not any(r.startswith("task/") for r, _ in plan.delete), str(plan.delete))
        check("durable 은 세어서 보고된다",
              any(r == durable_branch(WORK, TASK) for r, _ in plan.durable), str(plan.durable))

        A.apply_remote_cleanup(fx.paths, plan, remote="origin")
        check("실제로 지워졌다", att in plan.deleted, str(plan.deleted))
        refs = _run(fx.paths.repo, "ls-remote", "--heads", "origin")
        check("attempt 가 원격에서 사라졌다", att not in refs, refs)
        check("[중요] durable 은 살아 있다", durable_branch(WORK, TASK) in refs, refs)


def test_cleanup_without_tracking_deletes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        plan = A.plan_remote_cleanup(fx.paths, remote="origin", base_branch="nosuchbranch")
        check("[중요] 기준 브랜치가 없으면 아무것도 안 지운다", not plan.delete, str(plan.delete))
        check("오류로 보고한다", bool(plan.errors), str(plan.errors))


# ── 가드 자체 — [중요] **원본은 저장소 안이고, 설치 여부를 스스로 말한다** ──────────

def test_hook_source_is_in_repo_and_installs():
    """[중요] `.git/hooks/` 는 추적되지 않는다 — 원본이 저장소에 없으면 클론을 다시 만들 때
    가드가 **조용히 사라진다.** 그것이 가드에는 최악의 실패다."""
    check("훅 원본이 저장소 안에 있다", A.HOOK_SOURCE.is_file(), str(A.HOOK_SOURCE))

    with tempfile.TemporaryDirectory() as tmp:
        fx = _fx(tmp)
        st = A.hook_status(fx.paths)
        check("설치 전에는 없다고 말한다", not st["installed"], st["reason"])

        st = A.install_hook(fx.paths)
        check("설치 후 원본과 같다", st["current"], st["reason"])
        check("실행 가능하다", st["executable"], st["reason"])

        # [중요] **git-lfs 훅과 공존해야 한다** (실측 2026-08-28) — `git lfs install` 이
        #    `pre-push` 를 자기 것으로 덮어 **NS 클론의 가드가 통째로 사라져 있었다.**
        #    반대로 우리가 그냥 덮으면 LFS 저장소의 `.uasset` push 가 깨진다.
        src = A.HOOK_SOURCE.read_text(encoding="utf-8")
        check("[중요] LFS 에 위임하는 절이 있다", "git lfs pre-push" in src)
        check("  stdin 을 버퍼에 담아 **두 번** 먹인다 (ref 목록은 한 번 읽으면 사라진다)",
              src.count('printf \'%s\\n\' "$_refs"') >= 2, src[:200])
        check("  [주의] 가드가 먼저다 (거부할 push 에 LFS 업로드 비용을 안 치른다)",
              src.index("_guard") < src.index("git lfs pre-push"))

        # ── `#329` 상태 넷을 가른다 ───────────────────────────────────
        # [중요] **원본에 표식이 있어야 판정이 성립한다** (완료 조건 4). 표식을 바꾸면
        #    이 검사가 **먼저** 죽어야 한다 — 안 그러면 판정이 조용히 무너진다.
        for m in A.GUARD_MARKS:
            check(f"원본에 가드 표식이 있다: {m!r}", m in src, "표식이 사라졌다")

        # ① 우리 것이 아니다 — LFS 훅이 덮은 그 모양 (실측 2026-08-28)
        A.hook_target(fx.paths).write_text('#!/bin/sh\ngit lfs pre-push "$@"\n',
                                           encoding="utf-8")
        st = A.hook_status(fx.paths)
        check("[중요] 남의 훅이 덮은 것을 **foreign** 으로 잡는다",
              st["state"] == A.STATE_FOREIGN and not st["ours"], str(st))
        check("  사유가 「우리 가드가 아니다」라고 말한다",
              "우리 가드가 아니다" in st["reason"], st["reason"])
        check("  [중요] 「지금은 아무것도 안 막는다」를 말한다",
              "아무것도 안 막는다" in st["reason"], st["reason"])

        # ② 낡았다 — 우리 것이지만 원본과 다르다
        A.install_hook(fx.paths)
        A.hook_target(fx.paths).write_text(src + "\n# 낡은 사본\n", encoding="utf-8")
        st = A.hook_status(fx.paths)
        check("[중요] 낡은 사본은 **stale** 로 가른다 (foreign 이 아니다)",
              st["state"] == A.STATE_STALE and st["ours"], str(st))
        check("  [주의] 「막고는 있다」를 말한다", "막고는 있다" in st["reason"], st["reason"])

        # ③ 없다
        A.hook_target(fx.paths).unlink()
        st = A.hook_status(fx.paths)
        check("없으면 **missing**", st["state"] == A.STATE_MISSING, str(st))

        # [중요] **두 상태가 섞이지 않는다** — 이것이 `#329` 의 요지다.
        #    종전에는 ①과 ②가 같은 문구(*"원본과 다르다 — 손으로 고쳤나?"*)를 받았고,
        #    그래서 NS 의 무방비가 조용히 지나갔다.


def main() -> int:
    for fn in (test_hook_source_is_in_repo_and_installs, test_dead_wiring_stays_dead,
               test_cleanup_keeps_unmerged_evidence, test_cleanup_deletes_merged_attempt,
               test_cleanup_without_tracking_deletes_nothing):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_attempt: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
