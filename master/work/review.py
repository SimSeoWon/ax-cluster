"""리더 검수 흐름 이식 — `/review-work` (중 2.1 · `#135`).

원전 = `mcp/master_orchestrator/executor_review_finalize.py` 623줄
(`review_work_impl` · `reject_work_impl` · `finalize_work_impl` +
`_integrate_push_durables`(C.7) + `_cleanup_all_work_branches`).

## 🔴 리더가 없다 — 요청자 `.33` 이 그 자리다 (사용자 2026-08-16)

> *"이제 리더[TD, 팀장등]이 없으니 작업 요청자 [.33] 가 진행하면 될 거 같아."*

⚠️ 이것은 **새 판단이 아니라 이미 우리 코드에 적혀 있던 것의 확인**이다 —
`pre_push_hook.sh` 의 거부 메시지가 *"main 을 옮기는 것은 사람의 자리다 — 요청자(.33)에서
한다"* 라고 못박아 뒀다. `.33` 은 UE5 를 갖고 있어 검증 빌드가 가장 빠르고(스킬 `ax-request`
§7), 사람이 거기 앉아 있다. 원전의 「리더(TD·팀장)」 자리가 그대로 옮겨온다.

## 🔴 원전의 `stash` + `checkout main` 을 **옮기지 않는다** — 사람의 트리이기 때문이다

원전 `review_work_impl` 은 서버 저장소에서 이렇게 한다:

    git stash push -u -m server-pre-review-<id>  →  checkout main  →  …  →  stash pop
    (pop 이 실패하면 **로그만 남긴다** — `executor_review_finalize.py:191`)

원전에서는 그 트리가 **서버의 것**이라 잃을 것이 없었다. 🔴 우리에게 그 자리는 **사람이
편집 중인 트리**다. 반사실 실측(2026-08-16): 그 순간 `.33` 에는

    M Content/Blueprints/BP_MissionPrefab_C_0/BP_MissionPrefab_C_0.uasset

가 **커밋되지 않은 채** 있었다. 그대로 옮겼으면 사람의 미커밋 **바이너리** 에셋이 stash 로
들어갔고, pop 이 실패해도 **로그 한 줄**로 끝났을 것이다. `.uasset` 은 되살릴 수 없다.

→ 그래서 **worktree 를 쓴다.** 이것은 「안 옮기는 판단」이 아니라 **옮기되 우리 규약을
끼워 넣는 판단**이다(리포트 17 §4 의 `protected` 와 같은 결). 기제(시뮬레이션 머지 →
빌드 → 요약 → 상태 flip)는 원전 그대로다. 우리 `CLAUDE.md`·`ax-request` §7 이 이미
*"메인 워킹트리에서 브랜치를 갈아타지 않는다"* 로 같은 것을 요구하고 있었다.

## 자동화 경계 (사용자 2026-08-16)

    시뮬레이션 머지 · 빌드 · 요약 · 큐 상태 flip     자동
    main 머지 · push                                 🔴 승인 후 실행 (커밋·푸시 규칙)
    브랜치 삭제                                      🔴 **하지 않는다 — 명령만 적어 준다**

마지막 줄이 원전과 다른 자리다. 원전 `_cleanup_all_work_branches` 는 finalize/reject 때
work 관련 **모든** 원격 브랜치를 지운다. 우리는 둘 때문에 그러지 않는다:

    ① 하드룰   대화형 세션은 브랜치 삭제를 **승인이 있어도** 하지 않는다 (명령만 적어 준다)
    ② `#125`   삭제 기준은 **도달 가능성**이다 (사용자 결정 2026-08-14). 실측이 그것을
               골라 줬다 — 원격 attempt 4건이 전부 `main` 미도달이었고, 원전대로 일괄
               삭제했으면 **실패 시도 3건의 유일한 사본**이 사라졌다 (리포트 16 §9)

그래서 `plan_branch_cleanup()` 은 **계획만** 낸다 — 무엇이 도달 가능하고(지워도 안전),
무엇이 증거인지 갈라서 보여 준다.

## ⚠️ 빌드는 주입한다 — 이 모듈은 UE5 를 모른다

`review_work(build_fn=…)` 의 `build_fn(worktree_path) -> dict` 자리에 `.33` 로컬 빌드가
꽂힌다(사용자 결정 2026-08-16: *".33 로컬 (원전 그대로)"* — 마스터에 UE5 가 없어 `.2` 로
위임하던 것은 **리눅스가 강제한 것**이고 `.33` 에는 해당이 없다). 판정 계약은 이미
`layer3_verify` 가 갖고 있다 — 🔴 **SSH 종료 코드는 양방향으로 틀리므로 로그를 파싱한다.**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import coordinator as C
from .coordinator import GitError, _git, _git_rc
from .branch_names import durable_branch, attempt_glob

REVIEW_TREE_PREFIX = "ax-review"
DEFAULT_REMOTE = "origin"
BASE_BRANCH = "main"


class ReviewError(RuntimeError):
    """검수를 진행할 수 없다. 🔴 **모르는 채로 머지하지 않는다.**"""


# ─────────────────────────────────────────────────────────────
# C.7 리더 통합 머지 — 🔴 머지만 한다. push 없음
# ─────────────────────────────────────────────────────────────

@dataclass
class Integration:
    """`{ok, merged, skipped, conflict_branch, missing_durable, error}` 의 형태 있는 판."""
    ok: bool = False
    merged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflict: bool = False
    conflict_branch: str = ""
    missing_durable: str = ""
    error: str = ""


def order_verified(tasks) -> list:
    """통합 순서 — 🔴 **claim 과 같은 순서**여야 의존이 지켜진다 (원전 그대로).

    `hierarchy_level` 오름 → `priority` **내림** → `created` 오름.
    """
    return sorted(tasks, key=lambda t: (int(t.get("hierarchy_level", 0) or 0),
                                        -int(t.get("priority", 0) or 0),
                                        str(t.get("created", "") or "")))


def split_push_tasks(tasks) -> tuple:
    """push 모드 task 를 `(verified, skipped)` 로 가른다.

    ⚠️ **verified 만 통합한다** — 원전 C.7 의 핵심이다. 실패·미완료를 섞으면 「검증된 것만
    durable 에 올린다」는 2-tier 의 전제가 무너진다.
    """
    push = [t for t in tasks or [] if t.get("distribution_mode") == "push"]
    verified = order_verified([t for t in push if t.get("status") == "verified"])
    skipped = [{"task_id": t.get("task_id"), "status": t.get("status")}
               for t in push if t.get("status") != "verified"]
    return verified, skipped


def integrate_durables(repo: Path, *, target_branch: str, tasks, merge_label: str,
                       remote: str = DEFAULT_REMOTE, logf=C._noop_log) -> Integration:
    """Plan v5 C.7 — feature(골조·글루) + **verified** task durable 을 현재 브랜치에 머지한다.

    🔴 **호출 전제**: 호출자가 통합 대상 브랜치를 **이미 체크아웃**해 뒀다 (원전과 같다).
    🔴 **push 하지 않는다** — 머지 정합성만 본다. 어디에 올릴지는 호출자(review=시뮬레이션
    브랜치 폐기 / finalize=main)가 정한다.

    충돌·이상 시 **진행 중 머지를 abort 하고 통째 중단**한다(사용자 2026-06-16, 원전).
    부분 머지 잔재를 정리할 책임은 호출자에게 있다 — review 는 트리를 버리면 되고 finalize
    는 되돌려야 한다.
    """
    lab = merge_label or "[integrate]"
    # 1) feature 먼저 — durable 이 없는 완전구현 클래스는 feature 에만 있다 (원전 주석).
    rc, out = _git_rc(repo, "fetch", remote, target_branch)
    if rc != 0:
        return Integration(error=f"feature fetch 실패: {target_branch} — {out[:200]}")
    rc, out = _git_rc(repo, "merge", "--no-ff", f"{remote}/{target_branch}",
                      "-m", f"{lab}: feature {target_branch} (골조/글루)")
    if rc != 0:
        _git_rc(repo, "merge", "--abort")
        return Integration(conflict=True, conflict_branch=target_branch,
                           error=f"feature({target_branch}) 머지 충돌 — 통째 중단: {out[:200]}")
    logf("integrate", f"feature {target_branch} 머지")

    verified, skipped = split_push_tasks(tasks)
    merged: list = []
    for t in verified:
        tid = t.get("task_id")
        dur = durable_branch(tid)
        # 🔴 verified 인데 durable 이 없다 = 이상(검증 워커의 merge 누락) → 통째 중단.
        #    ⚠️ 여기서 넘어가면 **검증됐다고 기록된 것이 빠진 채** 통합이 성공으로 보인다.
        rc, ls = _git_rc(repo, "ls-remote", "--heads", remote, dur)
        if rc != 0 or not ls.strip():
            return Integration(merged=merged, skipped=skipped, missing_durable=dur,
                               error=f"verified task {tid} 의 durable `{dur}` 가 {remote} 에 없다 — 통째 중단")
        rc, out = _git_rc(repo, "fetch", remote, dur)
        if rc != 0:
            return Integration(merged=merged, skipped=skipped, missing_durable=dur,
                               error=f"durable fetch 실패: {dur} — {out[:200]}")
        rc, out = _git_rc(repo, "merge", "--no-ff", f"{remote}/{dur}", "-m", f"{lab}: {dur}")
        if rc != 0:
            _git_rc(repo, "merge", "--abort")
            return Integration(merged=merged, skipped=skipped, conflict=True, conflict_branch=dur,
                               error=f"durable `{dur}` 머지 충돌 — 통째 중단: {out[:200]}")
        merged.append(dur)
        logf("integrate", f"durable {dur} 머지")
    return Integration(ok=True, merged=merged, skipped=skipped)


# ─────────────────────────────────────────────────────────────
# 정리 — 🔴 **계획만 낸다.** 지우는 것은 사람의 자리다
# ─────────────────────────────────────────────────────────────

@dataclass
class CleanupPlan:
    """`delete` 는 *"지워도 잃는 것이 없다"* 로 판정된 것뿐이다."""
    delete: list = field(default_factory=list)      # (ref, tip) — base 에서 도달 가능
    keep: list = field(default_factory=list)        # (ref, 이유) — 🔴 증거
    errors: list = field(default_factory=list)

    def commands(self, remote: str = DEFAULT_REMOTE) -> list:
        """사람이 그대로 붙여 넣을 명령. 🔴 **우리가 실행하지 않는다.**"""
        return [f"git push {remote} --delete {ref}" for ref, _ in self.delete]

    def summary(self) -> str:
        return (f"정리 계획 — 지워도 되는 것 {len(self.delete)}건 · "
                f"🔴 보존(증거) {len(self.keep)}건" +
                (f" · 오류 {len(self.errors)}건" if self.errors else ""))


def plan_branch_cleanup(repo: Path, *, tasks, target_branch: str = "",
                        remote: str = DEFAULT_REMOTE, base_branch: str = BASE_BRANCH,
                        logf=C._noop_log) -> CleanupPlan:
    """원전 `_cleanup_all_work_branches` 이식 — 🔴 **지우지 않고 가른다.**

    원전은 리더가 적용·폐기할 때 work 관련 **모든** 원격 브랜치를 지운다(브랜치 증식 차단).
    우리는 기준이 다르다 — **`<remote>/<base>` 에서 도달 가능한 것만** 지울 수 있다
    (`#125` 사용자 결정 2026-08-14). 도달 불가면 그 커밋이 **거기에만 있을 수 있다.**

    ⚠️ 판정을 못 하면(tracking ref 없음·git 실패) **보존 쪽으로 기운다** — `pre_push_hook.sh`
    와 같은 방향의 fail-closed 다. 실행 자체를 안 하므로 여기서는 더 안전하다.
    """
    plan = CleanupPlan()
    tracking = f"refs/remotes/{remote}/{base_branch}"
    rc, _ = _git_rc(repo, "rev-parse", "--verify", "--quiet", tracking)
    if rc != 0:
        plan.errors.append(f"{tracking} 가 없어 도달 여부를 못 잰다 — 먼저 `git fetch {remote}`")

    refs: list = []
    for t in tasks or []:
        tid = t.get("task_id")
        if not tid:
            continue
        rc, out = _git_rc(repo, "ls-remote", "--heads", remote, attempt_glob(tid))
        if rc == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                    refs.append((parts[1][len("refs/heads/"):], parts[0]))
        rc, out = _git_rc(repo, "ls-remote", "--heads", remote, durable_branch(tid))
        if rc == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 2:
                    refs.append((parts[1][len("refs/heads/"):], parts[0]))
    if target_branch:
        rc, out = _git_rc(repo, "ls-remote", "--heads", remote, target_branch)
        if rc == 0 and out.strip():
            parts = out.split()
            if len(parts) >= 2:
                refs.append((parts[1][len("refs/heads/"):], parts[0]))

    for ref, tip in refs:
        if plan.errors:                       # 판정 자체가 불가 — 전부 보존
            plan.keep.append((ref, "도달 여부를 못 쟀다 (fail-closed: 보존)"))
            continue
        rc, _ = _git_rc(repo, "merge-base", "--is-ancestor", tip, tracking)
        if rc == 0:
            plan.delete.append((ref, tip))
        else:
            plan.keep.append((ref, f"🔴 {remote}/{base_branch} 에 병합되지 않았다 — 증거일 수 있다"))
    logf("cleanup", plan.summary())
    return plan


# ─────────────────────────────────────────────────────────────
# 검수 — 🔴 사람의 트리를 건드리지 않는다
# ─────────────────────────────────────────────────────────────

def review_tree_path(repo: Path, work_id: str) -> Path:
    """정본 **옆**. 안에 두면 `add -A` 와 색인 대상이 그것을 삼킨다(`attempt.py` 와 같은 규약)."""
    return Path(repo).parent / f"{REVIEW_TREE_PREFIX}-{work_id}"


@dataclass
class ReviewResult:
    ok: bool = False
    work_id: str = ""
    title: str = ""
    target_branch: str = ""
    redmine_issue_id: str = ""
    tree: str = ""
    merged_durables: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: bool = False
    build_passed: bool = True
    build_skipped: bool = True
    build_detail: dict = field(default_factory=dict)
    gate_passed: bool = False
    diff_summary: str = ""
    recent_commits: str = ""
    files_changed: list = field(default_factory=list)
    status_flipped: bool = False
    redmine_note: str = ""      # 🔴 마스터 경유로 보낼 본문. 여기서 직접 쓰지 않는다
    error: str = ""


def review_work(repo: Path, *, work_id: str, work: dict, tasks,
                build_fn=None, remote: str = DEFAULT_REMOTE,
                base_branch: str = BASE_BRANCH, keep_tree: bool = False,
                logf=C._noop_log) -> ReviewResult:
    """시뮬레이션 통합 + (주입된) 빌드 + 요약. 🔴 **어디에도 push 하지 않는다.**

    `work` / `tasks` 는 호출자가 큐(`GET /api/v1/works/<id>`)에서 읽어 넘긴다 — 이 모듈이
    HTTP 를 알면 테스트가 큐를 띄워야 한다.

    🔴 **사람의 트리 미접촉**: 통합은 `<정본 옆>/ax-review-<work_id>` worktree 에서 돈다.
    원전처럼 `stash` + `checkout main` 을 하지 않는다 (모듈 머리말의 반사실 실측).
    """
    r = ReviewResult(work_id=work_id)
    target = (work or {}).get("target_branch") or ""
    if not target:
        r.error = "target_branch 가 없다 — branch_isolation=False work 인가?"
        return r
    r.target_branch = target
    r.title = (work or {}).get("title") or work_id
    r.redmine_issue_id = str((work or {}).get("redmine_issue_id") or "")
    is_push = (work or {}).get("distribution_mode") == "push"

    tree = review_tree_path(repo, work_id)
    r.tree = str(tree)
    try:
        rc, out = _git_rc(repo, "fetch", remote, base_branch)
        if rc != 0:
            r.error = f"{remote}/{base_branch} fetch 실패: {out[:200]}"
            return r
        # 🔴 기준은 **원격 main** 이다. 로컬 main 은 사람이 어디에 두었는지 모른다.
        if tree.exists():
            _git_rc(repo, "worktree", "remove", "--force", str(tree))
        rc, out = _git_rc(repo, "worktree", "add", "--detach", "--force",
                          str(tree), f"{remote}/{base_branch}")
        if rc != 0:
            r.error = f"검수 worktree 생성 실패: {out[:200]}"
            return r
        logf("review", f"worktree {tree.name} = {remote}/{base_branch} (사람 트리 미접촉)")

        label = f"[REVIEW SIM] {work_id}: {r.title}"
        if is_push:
            integ = integrate_durables(tree, target_branch=target, tasks=tasks,
                                       merge_label=label, remote=remote, logf=logf)
        else:
            rc, out = _git_rc(tree, "fetch", remote, target)
            if rc != 0:
                integ = Integration(error=f"feature fetch 실패: {out[:200]}")
            else:
                rc, out = _git_rc(tree, "merge", "--no-ff", f"{remote}/{target}", "-m", label)
                if rc != 0:
                    _git_rc(tree, "merge", "--abort")
                    integ = Integration(conflict=True, conflict_branch=target,
                                        error=f"머지 충돌 — {base_branch} 와 충돌: {out[:300]}")
                else:
                    integ = Integration(ok=True, merged=[target])
        r.merged_durables = integ.merged
        r.skipped = integ.skipped
        r.conflicts = integ.conflict
        if not integ.ok:
            r.error = integ.error
            return r

        # 요약 — 🔴 비교 대상은 **원격** base 다
        r.diff_summary = _git(tree, "diff", f"{remote}/{base_branch}", "HEAD", "--stat",
                              check=False)[-3000:]
        r.recent_commits = _git(tree, "log", f"{remote}/{base_branch}..HEAD", "--oneline", "-20",
                                check=False)[-2000:]
        names = _git(tree, "diff", f"{remote}/{base_branch}", "HEAD", "--name-only", check=False)
        r.files_changed = [ln.strip() for ln in names.splitlines() if ln.strip()]

        if build_fn is not None:
            r.build_skipped = False
            logf("review", "빌드 호출 — 검수 트리 위")
            bres = build_fn(tree) or {}
            r.build_detail = dict(bres)
            r.build_passed = bool(bres.get("ok"))
            logf("review", f"빌드 결과 build_passed={r.build_passed}")
        r.gate_passed = r.build_passed
        r.ok = True

        if not r.build_skipped and not r.gate_passed:
            # 원전 7) — 빌드 실패면 Redmine 코멘트. 🔴 **키가 여기 없다**(우리 키는 디스크에
            # 없고 컨테이너 DB 에 있다) → 본문만 만들어 돌려주고 **마스터 경유**로 보낸다
            # (사용자 결정 2026-08-16).
            r.redmine_note = (
                f"[리뷰 단계 빌드 실패] 요청자가 시뮬레이션 통합 + 빌드 시도\n"
                f"- 검수 트리: {tree.name} (시뮬레이션 — {base_branch} 미변경)\n"
                f"- 통합된 durable {len(r.merged_durables)}건\n"
                f"- 상세: {str(r.build_detail)[:1500]}")
        return r
    except GitError as e:
        r.error = f"git 오류: {e}"
        return r
    finally:
        if not keep_tree and tree.exists():
            _git_rc(repo, "worktree", "remove", "--force", str(tree))
            _git_rc(repo, "worktree", "prune")
            logf("review", f"검수 트리 제거 {tree.name}")
