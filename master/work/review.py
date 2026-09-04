"""리더 검수 흐름 이식 — `/review-work` (중 2.1 · `#135`).

원전 = `mcp/master_orchestrator/executor_review_finalize.py` 623줄
(`review_work_impl` · `reject_work_impl` · `finalize_work_impl` +
`_integrate_push_durables`(C.7) + `_cleanup_all_work_branches`).

## [중요] 리더가 없다 — 요청자 `.33` 이 그 자리다 (사용자 2026-08-16)

> *"이제 리더[TD, 팀장등]이 없으니 작업 요청자 [.33] 가 진행하면 될 거 같아."*

[주의] 이것은 **새 판단이 아니라 이미 우리 코드에 적혀 있던 것의 확인**이다 —
`pre_push_hook.sh` 의 거부 메시지가 *"main 을 옮기는 것은 사람의 자리다 — 요청자(.33)에서
한다"* 라고 못박아 뒀다. `.33` 은 UE5 를 갖고 있어 검증 빌드가 가장 빠르고(스킬 `ax-request`
§7), 사람이 거기 앉아 있다. 원전의 「리더(TD·팀장)」 자리가 그대로 옮겨온다.

## [중요] 원전의 `stash` + `checkout main` 을 **옮기지 않는다** — 사람의 트리이기 때문이다

원전 `review_work_impl` 은 서버 저장소에서 이렇게 한다:

    git stash push -u -m server-pre-review-<id>  →  checkout main  →  …  →  stash pop
    (pop 이 실패하면 **로그만 남긴다** — `executor_review_finalize.py:191`)

원전에서는 그 트리가 **서버의 것**이라 잃을 것이 없었다. [중요] 우리에게 그 자리는 **사람이
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
    main 머지 · push                                 [중요] 승인 후 실행 (커밋·푸시 규칙)
    브랜치 삭제                                      [중요] **하지 않는다 — 명령만 적어 준다**

마지막 줄이 원전과 다른 자리다. 원전 `_cleanup_all_work_branches` 는 finalize/reject 때
work 관련 **모든** 원격 브랜치를 지운다. 우리는 둘 때문에 그러지 않는다:

    ① 하드룰   대화형 세션은 브랜치 삭제를 **승인이 있어도** 하지 않는다 (명령만 적어 준다)
    ② `#125`   삭제 기준은 **도달 가능성**이다 (사용자 결정 2026-08-14). 실측이 그것을
               골라 줬다 — 원격 attempt 4건이 전부 `main` 미도달이었고, 원전대로 일괄
               삭제했으면 **실패 시도 3건의 유일한 사본**이 사라졌다 (리포트 16 §9)

그래서 `plan_branch_cleanup()` 은 **계획만** 낸다 — 무엇이 도달 가능하고(지워도 안전),
무엇이 증거인지 갈라서 보여 준다.

## [주의] 빌드는 주입한다 — 이 모듈은 UE5 를 모른다

`review_work(build_fn=…)` 의 `build_fn(worktree_path) -> dict` 자리에 `.33` 로컬 빌드가
꽂힌다(사용자 결정 2026-08-16: *".33 로컬 (원전 그대로)"* — 마스터에 UE5 가 없어 `.2` 로
위임하던 것은 **리눅스가 강제한 것**이고 `.33` 에는 해당이 없다). 판정 계약은 이미
`layer3_verify` 가 갖고 있다 — [중요] **SSH 종료 코드는 양방향으로 틀리므로 로그를 파싱한다.**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import coordinator as C
from .coordinator import GitError, _git, _git_rc
from .branch_names import (
    BranchNameError, base_branch as _base_branch, durable_branch, attempt_glob,
)


def work_base_branch(work_id: str, work: dict | None = None) -> str:
    """이 work 의 작업 브랜치 이름 (`#319`).

    [중요] **저장된 `target_branch` 가 이긴다** — 옛 work(그 값이 `main` 이나 `feature/…`)도
    그대로 돌아야 한다. 없으면 **work_id 에서 유도**한다: 이름의 SSOT 는 큐가 발급한 id 이므로
    유도는 지어내는 것이 아니다(`#197` 이 값을 치른 구분).
    [주의] 못 만들면 **빈 문자열** — 호출자가 사유를 붙여 거절한다(예외로 새지 않는다).
    """
    stored = ((work or {}).get("target_branch") or "").strip()
    if stored:
        return stored
    try:
        return _base_branch(work_id)
    except BranchNameError:
        return ""

REVIEW_TREE_PREFIX = "ax-review"
DEFAULT_REMOTE = "origin"
BASE_BRANCH = "main"


class ReviewError(RuntimeError):
    """검수를 진행할 수 없다. [중요] **모르는 채로 머지하지 않는다.**"""


# ─────────────────────────────────────────────────────────────
# C.7 리더 통합 머지 — [중요] 머지만 한다. push 없음
# ─────────────────────────────────────────────────────────────

@dataclass
class Integration:
    """`{ok, merged, skipped, conflict_branch, missing_durable, error}` 의 형태 있는 판."""
    ok: bool = False
    merged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    # [중요] `#319` ⓐ — **매니페스트만 든 조각 durable 은 머지하지 않는다.** 여기 이름이 남는다:
    #    "안 머지했다" 와 "빠뜨렸다" 는 다르고, 그 차이가 안 보이면 나중에 구분할 수 없다.
    ax_only: list = field(default_factory=list)
    conflict: bool = False
    conflict_branch: str = ""
    missing_durable: str = ""
    error: str = ""


def order_verified(tasks) -> list:
    """통합 순서 — [중요] **claim 과 같은 순서**여야 의존이 지켜진다 (원전 그대로).

    `hierarchy_level` 오름 → `priority` **내림** → `created` 오름.
    """
    return sorted(tasks, key=lambda t: (int(t.get("hierarchy_level", 0) or 0),
                                        -int(t.get("priority", 0) or 0),
                                        str(t.get("created", "") or "")))


def split_push_tasks(tasks) -> tuple:
    """push 모드 task 를 `(verified, skipped)` 로 가른다.

    [주의] **verified 만 통합한다** — 원전 C.7 의 핵심이다. 실패·미완료를 섞으면 「검증된 것만
    durable 에 올린다」는 2-tier 의 전제가 무너진다.
    """
    push = [t for t in tasks or [] if t.get("distribution_mode") == "push"]
    verified = order_verified([t for t in push if t.get("status") == "verified"])
    skipped = [{"task_id": t.get("task_id"), "status": t.get("status")}
               for t in push if t.get("status") != "verified"]
    return verified, skipped


def integrate_durables(repo: Path, *, work_id: str, target_branch: str, tasks,
                       merge_label: str, remote: str = DEFAULT_REMOTE,
                       logf=C._noop_log) -> Integration:
    """Plan v5 C.7 — 작업 브랜치(골조·코드) + **소스를 든** 조각 durable 을 현재 브랜치에 머지한다.

    [중요] **`#319` ⓐ — 매니페스트 전용 조각 durable 은 머지하지 않는다** (사용자 결정
    2026-08-27). 통합자가 코드를 작업 브랜치에 올리므로 조각 durable 에는 `.ax/tasks/<T>/
    context.md` 만 남고, 그것을 머지하면 **인프라 파일이 게임 `main` 에 박힌다.** 판정은
    이름이 아니라 **내용**이다 — `.ax/` 밖을 건드리는 조각은 머지한다(attempt 경로가 그렇다).

    [중요] `#319` 이후 계층은 3단이다:

        attempt/<W>/<T>/<작업장>/<ts>   시도
          └ task/<W>/<T>                조각 durable — 검증 통과분이 여기 merge 된다
             └ task/<W>/base            작업 브랜치 — 골조가 실물로 있고 조각들이 여기서 갈라졌다
                └ main                  사람이 옮긴다 (요청자 `.33`)

    그래서 **작업 브랜치를 먼저 머지한다** — 조각들의 공통 조상이라 대개 fast-forward 로
    흡수되지만, 골조만 있고 조각이 하나도 없는 work 에서도 골조가 살아남아야 한다.

    [중요] **호출 전제**: 호출자가 통합 대상 브랜치를 **이미 체크아웃**해 뒀다 (원전과 같다).
    [중요] **push 하지 않는다** — 머지 정합성만 본다. 어디에 올릴지는 호출자(review=시뮬레이션
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
    ax_only: list = []
    for t in verified:
        tid = t.get("task_id")
        dur = durable_branch(work_id, tid, int(t.get("round") or 0))
        # [중요] verified 인데 durable 이 없다 = 이상(검증 워커의 merge 누락) → 통째 중단.
        #    [주의] 여기서 넘어가면 **검증됐다고 기록된 것이 빠진 채** 통합이 성공으로 보인다.
        rc, ls = _git_rc(repo, "ls-remote", "--heads", remote, dur)
        if rc != 0 or not ls.strip():
            return Integration(merged=merged, skipped=skipped, missing_durable=dur,
                               error=f"verified task {tid} 의 durable `{dur}` 가 {remote} 에 없다 — 통째 중단")
        rc, out = _git_rc(repo, "fetch", remote, dur)
        if rc != 0:
            return Integration(merged=merged, skipped=skipped, missing_durable=dur,
                               error=f"durable fetch 실패: {dur} — {out[:200]}")
        # [중요] **`#319` ⓐ (사용자 결정 2026-08-27) — 매니페스트 전용 조각은 머지하지 않는다.**
        #    실측 2026-08-27: 통합자가 코드를 **작업 브랜치**에 올리므로 조각 durable 에는
        #    `.ax/tasks/<T>/context.md` **하나만** 남고, 그것은 작업 브랜치에서 도달 불가한
        #    형제 분기다. 그대로 머지하면 **인프라 파일이 게임 `main` 에 들어간다.**
        #    [주의] 그렇다고 무조건 건너뛰지는 않는다 — attempt 경로(`attempt.merge_verified`)는
        #    조각 durable 에 **소스**를 올린다. 그것을 건너뛰면 검증된 코드가 조용히 사라진다.
        #    그래서 판정은 「이 조각이 `.ax/` 밖을 건드리나」다.
        outside = _touches_outside_ax(repo, f"{remote}/{target_branch}", f"{remote}/{dur}")
        if not outside:
            ax_only.append(dur)
            logf("integrate", f"durable {dur} — 매니페스트 전용이라 머지하지 않는다 (#319 ⓐ)")
            continue
        rc, out = _git_rc(repo, "merge", "--no-ff", f"{remote}/{dur}", "-m", f"{lab}: {dur}")
        if rc != 0:
            _git_rc(repo, "merge", "--abort")
            return Integration(merged=merged, skipped=skipped, conflict=True, conflict_branch=dur,
                               error=f"durable `{dur}` 머지 충돌 — 통째 중단: {out[:200]}")
        merged.append(dur)
        logf("integrate", f"durable {dur} 머지 (`.ax/` 밖 변경 {len(outside)}건)")

    # [중요] **마지막 가드 — 어느 경로로 새든 여기서 잡는다** (`#319` ⓐ).
    #    위 판정을 우회해 `.ax/` 가 트리에 들어왔다면 그것은 계약 위반이다. 조용히 넘기면
    #    `main` 에 인프라 파일이 박히고, 그건 사람이 손으로 걷어내야 한다.
    stray = _ax_paths_in_tree(repo)
    if stray:
        return Integration(merged=merged, skipped=skipped, ax_only=ax_only,
                           error=("[중요] 통합 트리에 `.ax/` 파일이 들어왔다 — 게임 `main` 에 "
                                  "인프라 파일을 넣지 않는다(`#319` ⓐ). 통째 중단: "
                                  + ", ".join(stray[:5])))
    return Integration(ok=True, merged=merged, skipped=skipped, ax_only=ax_only)


def _touches_outside_ax(repo: Path, base_ref: str, dur_ref: str) -> list:
    """`base_ref` 대비 `dur_ref` 가 **`.ax/` 밖**에서 바꾼 파일. 못 재면 **[]가 아니라 전부**.

    [중요] fail-closed 의 방향이 여기서는 **머지 쪽**이다 — 못 쟀는데 건너뛰면 검증된 코드가
    조용히 사라진다. 그 반대(불필요한 머지)는 아래 `_ax_paths_in_tree` 가드가 잡는다.
    """
    rc, out = _git_rc(repo, "diff", "--name-only", f"{base_ref}...{dur_ref}")
    if rc != 0:
        return ["(diff 실패 — 머지 쪽으로 접는다)"]
    return [ln.strip() for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith(".ax/")]


def _ax_paths_in_tree(repo: Path) -> list:
    """통합 트리(HEAD)에 남아 있는 `.ax/` 추적 파일. 없으면 `[]`."""
    rc, out = _git_rc(repo, "ls-tree", "-r", "--name-only", "HEAD", ".ax")
    if rc != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


# ─────────────────────────────────────────────────────────────
# 정리 — [중요] **계획만 낸다.** 지우는 것은 사람의 자리다
# ─────────────────────────────────────────────────────────────

@dataclass
class CleanupPlan:
    """`delete` 는 *"지워도 잃는 것이 없다"* 로 판정된 것뿐이다."""
    delete: list = field(default_factory=list)      # (ref, tip) — base 에서 도달 가능
    keep: list = field(default_factory=list)        # (ref, 이유) — [중요] 증거
    errors: list = field(default_factory=list)

    def commands(self, remote: str = DEFAULT_REMOTE) -> list:
        """사람이 그대로 붙여 넣을 명령. [중요] **우리가 실행하지 않는다.**"""
        return [f"git push {remote} --delete {ref}" for ref, _ in self.delete]

    def summary(self) -> str:
        return (f"정리 계획 — 지워도 되는 것 {len(self.delete)}건 · "
                f"[중요] 보존(증거) {len(self.keep)}건" +
                (f" · 오류 {len(self.errors)}건" if self.errors else ""))


def apply_branch_cleanup(repo: Path, plan: "CleanupPlan", *, remote: str = DEFAULT_REMOTE,
                         logf=C._noop_log) -> tuple:
    """[중요] **`plan.delete` 만** 지운다 — 그건 *"base 에서 도달 가능"* 으로 판정된 것뿐이다.

    사용자 결정 2026-08-21: 원전 `finalize_work` 6단계 동등으로 올린다(③ 원격 브랜치 정리).
    2026-08-16 의 *"브랜치 삭제는 사람"* 을 뒤집는 것이고, 뒤집어도 안전한 근거는 **가드가
    둘**이라는 점이다 — 이 함수는 `plan.delete`(도달 가능분)만 받고, 그 위에서 pre-push 훅
    (`#125`)이 **같은 판정을 한 번 더** 한다. 훅이 거부하면 그건 우리 판정이 틀렸다는 뜻이므로
    **밀어붙이지 않는다**(`--no-verify` 금지).

    [주의] **실패는 머지를 되돌리지 않는다** — 머지는 이미 끝났고 브랜치가 남는 것은 잡음일
    뿐이다. 사유를 돌려주고 사람이 본다. 반환: `(deleted, failed)`.
    """
    deleted, failed = [], []
    for ref, tip in (plan.delete if plan else []):
        rc, out = _git_rc(repo, "push", remote, "--delete", ref)
        if rc == 0:
            deleted.append(ref)
            logf("cleanup", f"삭제 {ref} ({tip[:8]})")
        else:
            failed.append((ref, out.strip()[:160]))
            logf("cleanup", f"[주의] 삭제 실패 {ref} — {out.strip()[:120]}")
    return deleted, failed


def plan_branch_cleanup(repo: Path, *, tasks, work_id: str = "", target_branch: str = "",
                        remote: str = DEFAULT_REMOTE, base_branch: str = BASE_BRANCH,
                        logf=C._noop_log) -> CleanupPlan:
    """원전 `_cleanup_all_work_branches` 이식 — [중요] **지우지 않고 가른다.**

    원전은 리더가 적용·폐기할 때 work 관련 **모든** 원격 브랜치를 지운다(브랜치 증식 차단).
    우리는 기준이 다르다 — **`<remote>/<base>` 에서 도달 가능한 것만** 지울 수 있다
    (`#125` 사용자 결정 2026-08-14). 도달 불가면 그 커밋이 **거기에만 있을 수 있다.**

    [주의] 판정을 못 하면(tracking ref 없음·git 실패) **보존 쪽으로 기운다** — `pre_push_hook.sh`
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
        rc, out = _git_rc(repo, "ls-remote", "--heads", remote,
                          attempt_glob(work_id, tid) if work_id else f"refs/heads/attempt/*/{tid}/*")
        if rc == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                    refs.append((parts[1][len("refs/heads/"):], parts[0]))
        rc, out = _git_rc(repo, "ls-remote", "--heads", remote,
                          durable_branch(work_id, tid) if work_id else f"refs/heads/task/*/{tid}")
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
            plan.keep.append((ref, f"[중요] {remote}/{base_branch} 에 병합되지 않았다 — 증거일 수 있다"))
    logf("cleanup", plan.summary())
    return plan


# ─────────────────────────────────────────────────────────────
# 검수 — [중요] 사람의 트리를 건드리지 않는다
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
    # [중요] `#319` ⓐ — 머지 **안 한** 매니페스트 전용 조각. "안 했다"와 "빠뜨렸다"는 다르다
    ax_only: list = field(default_factory=list)
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
    redmine_note: str = ""      # [중요] 마스터 경유로 보낼 본문. 여기서 직접 쓰지 않는다
    error: str = ""


def review_work(repo: Path, *, work_id: str, work: dict, tasks,
                build_fn=None, remote: str = DEFAULT_REMOTE,
                base_branch: str = BASE_BRANCH, keep_tree: bool = False,
                logf=C._noop_log) -> ReviewResult:
    """시뮬레이션 통합 + (주입된) 빌드 + 요약. [중요] **어디에도 push 하지 않는다.**

    `work` / `tasks` 는 호출자가 큐(`GET /api/v1/works/<id>`)에서 읽어 넘긴다 — 이 모듈이
    HTTP 를 알면 테스트가 큐를 띄워야 한다.

    [중요] **사람의 트리 미접촉**: 통합은 `<정본 옆>/ax-review-<work_id>` worktree 에서 돈다.
    원전처럼 `stash` + `checkout main` 을 하지 않는다 (모듈 머리말의 반사실 실측).
    """
    r = ReviewResult(work_id=work_id)
    # [중요] `#319` — 저장된 값이 이기고, 없으면 **work_id 에서 유도**한다.
    #    이름의 SSOT 는 큐가 발급한 work_id 이므로 유도는 지어내는 것이 아니다.
    target = work_base_branch(work_id, work)
    if not target:
        r.error = ("작업 브랜치를 정할 수 없다 — work_id 도 target_branch 도 쓸 수 없다 "
                   "(`#319`: 이름은 `task/<work_id>/base`)")
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
        # [중요] 기준은 **원격 main** 이다. 로컬 main 은 사람이 어디에 두었는지 모른다.
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
            integ = integrate_durables(tree, work_id=work_id, target_branch=target, tasks=tasks,
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
        r.ax_only = integ.ax_only
        r.skipped = integ.skipped
        r.conflicts = integ.conflict
        if not integ.ok:
            r.error = integ.error
            return r

        # 요약 — [중요] 비교 대상은 **원격** base 다
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
            # 원전 7) — 빌드 실패면 Redmine 코멘트. [중요] **키가 여기 없다**(우리 키는 디스크에
            # 없고 컨테이너 DB 에 있다) → 본문만 만들어 돌려주고 **마스터 경유**로 보낸다
            # (사용자 결정 2026-08-16).
            r.redmine_note = (
                f"[리뷰 단계 빌드 실패] 요청자가 시뮬레이션 통합 + 빌드 시도\n"
                f"- 검수 트리: {tree.name} (시뮬레이션 — {base_branch} 미변경)\n"
                f"- 통합된 durable {len(r.merged_durables)}건"
                + (f" · [주의] 매니페스트 전용이라 **머지하지 않은 것** "
                   f"{len(r.ax_only)}건 (`#319` ⓐ — 게임 `main` 에 `.ax/` 를 넣지 않는다)"
                   if r.ax_only else "") + "\n"
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


# ─────────────────────────────────────────────────────────────
# 반려 · 승인 — [중요] 큐 호출은 **주입 가능한 한 자리**로 모은다
# ─────────────────────────────────────────────────────────────

def _default_api(method: str, path: str, payload=None):
    """큐 호출. [중요] `runner._api` 를 **재사용한다** — 토큰·타임아웃·오류 형태를 따로 만들면
    조용히 갈라진다(`coordinator._git_cmd` 를 공유하는 것과 같은 이유).

    [주의] **요청자(`.33`)에는 이 경로가 없다** — 배달되는 것은 이 모듈의 의존 폐포뿐이고
    큐 토큰은 그 기계에 두지 않는다(`client/bundle.py`: *"토큰은 이 번들에 넣지 않는다"*).
    거기서는 호출자가 `api=` 를 주입한다(MCP 도구가 토큰을 갖고 있다). [중요] 그래서 여기서
    맨 `ImportError` 를 내지 않고 **무엇을 해야 하는지** 말한다.
    """
    try:
        from . import runner
    except ImportError as e:
        raise ReviewError(
            "이 머신에는 큐 클라이언트가 없다 — `api=` 를 주입하라 "
            "(요청자에는 토큰을 두지 않는다: client/bundle.py)") from e
    return runner._api(method, path, payload)


def fetch_work(work_id: str, *, api=None) -> tuple:
    """큐에서 `(work, tasks)`. [중요] 이 모듈에서 HTTP 를 아는 유일한 자리다."""
    resp = (api or _default_api)("GET", f"/api/v1/works/{work_id}") or {}
    return (resp.get("work") or {}), (resp.get("tasks") or [])


def _decision(result: str, reviewer: str, notes: str = "") -> dict:
    from datetime import datetime, timezone
    return {"decided_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "decided_by": reviewer or None, "result": result, "notes": notes or None}


@dataclass
class Decision:
    ok: bool = False
    work_id: str = ""
    merge_status: str = ""
    noop: bool = False
    pushed: bool = False
    merged_durables: list = field(default_factory=list)
    # [중요] `#319` ⓐ — 머지 **안 한** 매니페스트 전용 조각. "안 했다"와 "빠뜨렸다"는 다르다
    ax_only: list = field(default_factory=list)
    tree: str = ""
    cleanup: object = None          # CleanupPlan — [중요] 계획일 뿐이다
    commands: list = field(default_factory=list)
    redmine_note: str = ""
    redmine_issue_id: str = ""
    queue_patched: bool = False
    # 원전 6단계 동등 (사용자 결정 2026-08-21) — ② Redmine 기재 · ③ 브랜치 정리 실행
    merge_commit: str = ""          # main 에 올라간 머지 커밋 (원전이 이슈에 적는 그 값)
    redmine_posted: bool = False    # 노트 전송 성공 (마스터 대행 경유)
    deleted_branches: list = field(default_factory=list)
    cleanup_failed: list = field(default_factory=list)   # (ref, 사유) — 실패해도 머지는 끝났다
    error: str = ""


def reject_work(repo: Path, *, work_id: str, work: dict, tasks, reviewer: str = "",
                reason: str = "", api=None, remote: str = DEFAULT_REMOTE,
                base_branch: str = BASE_BRANCH, logf=C._noop_log) -> Decision:
    """원전 `reject_work_impl` 이식 — 상태·통지 마무리. [중요] **브랜치를 지우지 않는다.**

    원전은 push work 반려 시 관련 원격 브랜치를 **전부** 지운다(증식 차단). 우리는 계획만
    낸다 — 하드룰 + `#125`. [주의] 반려된 work 의 durable 은 `main` 에 도달할 리 없으므로
    실질적으로 **전부 보존**된다. 그것이 의도다: 실패한 시도도 조사 자산이다(§8.4 누적 모델).
    """
    d = Decision(work_id=work_id)
    cur = (work or {}).get("merge_status")
    d.redmine_issue_id = str((work or {}).get("redmine_issue_id") or "")
    if cur == "rejected":
        d.ok, d.noop, d.merge_status = True, True, "rejected"
        return d
    if cur == "merged":
        d.error = "이미 merged 된 work — 반려할 수 없다"
        return d

    try:
        (api or _default_api)("PATCH", f"/api/v1/works/{work_id}",
                              {"merge_status": "rejected",
                               "review_decision": _decision("rejected", reviewer, reason)})
        d.queue_patched = True
    except Exception as e:                                  # noqa: BLE001
        # [중요] 조용히 넘기지 않는다 — 큐 상태가 안 바뀌면 이 work 는 계속 열려 있다
        d.error = f"큐 상태 갱신 실패 (수동 갱신 필요): {type(e).__name__}: {e}"
        logf("reject", d.error)

    d.merge_status = "rejected"
    d.cleanup = plan_branch_cleanup(repo, tasks=tasks, work_id=work_id,
                                    target_branch=work_base_branch(work_id, work),
                                    remote=remote, base_branch=base_branch, logf=logf)
    d.commands = d.cleanup.commands(remote)
    d.redmine_note = (
        f"[반려] 검토자={reviewer or '(미지정)'}\n\n"
        f"사유: {reason or '(미입력)'}\n\n"
        f"- [중요] 브랜치는 **보존**된다 — 실패한 시도도 조사 자산이다(누적 모델). "
        f"재작업은 같은 durable 위에 `[FEEDBACK]` 을 얹어 이어 간다\n"
        f"- 영구 종결은 사람이 판단한다")
    d.ok = not d.error
    return d


def finalize_work(repo: Path, *, work_id: str, work: dict, tasks, reviewer: str = "",
                  confirm: bool = False, api=None, remote: str = DEFAULT_REMOTE,
                  base_branch: str = BASE_BRANCH, logf=C._noop_log) -> Decision:
    """원전 `finalize_work_impl` 이식 — 승인 → 통합 → `main` 반영.

    [중요] **`confirm=False` 가 기본이다** (fail-closed). 그때는 검수 트리에서 통합만 하고
    **push 하지 않으며**, 사람이 그대로 실행할 명령을 돌려준다. 사용자 결정(2026-08-16):
    *"머지·push 는 승인 후 자동, 브랜치 삭제는 사람"*. 승인은 대화에서 일어나므로 코드의
    기본값은 **안 하는 쪽**이어야 한다.

    [중요] **사람의 트리에서 `checkout main` 을 하지 않는다** — 원전은 그렇게 하지만 그 자리는
    우리에겐 사람의 워킹트리다(모듈 머리말). 대신 `<정본 옆>` worktree 를 `<remote>/<base>`
    에 세워 통합하고 **`HEAD:<base>` 로 push** 한다. [주의] 그래서 사람의 로컬 `main` 은 그대로다 —
    끝난 뒤 `git pull` 하면 된다. 그 편이 안전하다.
    """
    d = Decision(work_id=work_id)
    status = (work or {}).get("merge_status")
    target = work_base_branch(work_id, work)
    d.redmine_issue_id = str((work or {}).get("redmine_issue_id") or "")
    if status == "merged":
        d.ok, d.noop, d.merge_status = True, True, "merged"
        return d
    if status not in ("ready_for_review", "in_progress"):
        d.error = (f"merge_status={status!r} — ready_for_review / in_progress 만 승인할 수 있다 "
                   f"(원전과 같은 게이트)")
        return d
    if not target:
        d.error = ("작업 브랜치를 정할 수 없다 — work_id 도 target_branch 도 쓸 수 없다 "
                   "(`#319`: 이름은 `task/<work_id>/base`)")
        return d

    is_push = (work or {}).get("distribution_mode") == "push"
    tree = review_tree_path(repo, work_id)
    d.tree = str(tree)
    try:
        rc, out = _git_rc(repo, "fetch", remote, base_branch)
        if rc != 0:
            d.error = f"{remote}/{base_branch} fetch 실패: {out[:200]}"
            return d
        if tree.exists():
            _git_rc(repo, "worktree", "remove", "--force", str(tree))
        rc, out = _git_rc(repo, "worktree", "add", "--detach", "--force",
                          str(tree), f"{remote}/{base_branch}")
        if rc != 0:
            d.error = f"통합 worktree 생성 실패: {out[:200]}"
            return d

        label = f"Merge work {work_id}: {(work or {}).get('title', target)}"
        if reviewer:
            label += f" (Reviewed-by: {reviewer})"
        if is_push:
            integ = integrate_durables(tree, work_id=work_id, target_branch=target, tasks=tasks,
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
                                        error=f"머지 충돌 — 수동 해결 필요: {out[:300]}")
                else:
                    integ = Integration(ok=True, merged=[target])
        d.merged_durables = integ.merged
        d.ax_only = integ.ax_only
        if not integ.ok:
            d.error = integ.error
            _git_rc(repo, "worktree", "remove", "--force", str(tree))   # 부분 머지 폐기
            _git_rc(repo, "worktree", "prune")
            return d

        push_cmd = f"git -C {tree} push {remote} HEAD:{base_branch}"
        if confirm:
            rc, out = _git_rc(tree, "push", remote, f"HEAD:{base_branch}")
            if rc != 0:
                # [중요] 되돌리지 않는다 — 커밋은 이 트리에 그대로 있고 잃은 것이 없다.
                #    `--force` 로 밀지 않는다(하드룰). 사람이 판단한다.
                d.error = (f"{base_branch} push 거부됨 — 통합은 `{tree}` 에 그대로 있다. "
                           f"밀어내지 않는다: {out[:200]}")
                d.commands = [push_cmd]
                return d
            d.pushed = True
            rc2, head = _git_rc(tree, "rev-parse", "HEAD")
            d.merge_commit = (head or "").strip() if rc2 == 0 else ""
            logf("finalize", f"{remote}/{base_branch} 갱신 (durable {len(d.merged_durables)}건)"
                             + (f" · {d.merge_commit[:8]}" if d.merge_commit else ""))
        else:
            d.commands = [push_cmd]
            logf("finalize", "confirm=False — 통합만 하고 멈춘다 (트리 보존)")

        if d.pushed:
            try:
                (api or _default_api)("PATCH", f"/api/v1/works/{work_id}",
                                      {"merge_status": "merged",
                                       "review_decision": _decision("approved", reviewer)})
                d.queue_patched = True
            except Exception as e:                          # noqa: BLE001
                d.error = f"머지는 됐고 큐 상태 갱신만 실패했다 (수동 갱신 필요): {e}"
                logf("finalize", d.error)
            d.merge_status = "merged"
            _git_rc(repo, "fetch", remote, base_branch)      # 정리 판정의 입력을 새로 읽는다
            d.cleanup = plan_branch_cleanup(repo, tasks=tasks, work_id=work_id,
                                            target_branch=target,
                                            remote=remote, base_branch=base_branch, logf=logf)
            # ── ③ 정리 실행 (원전 6단계 ③ · 사용자 결정 2026-08-21) ──────────
            # [중요] 머지가 끝난 **뒤**라 도달 가능 판정이 이제 참이다. 순서를 바꾸면
            #    (정리를 머지 전에 하면) 같은 ref 가 「미병합」으로 보여 아무것도 안 지워진다.
            d.deleted_branches, d.cleanup_failed = apply_branch_cleanup(
                repo, d.cleanup, remote=remote, logf=logf)
            # 못 지운 것만 사람 몫으로 남긴다 — 지운 것을 명령으로 또 주면 혼선이다
            d.commands += [f"git push {remote} --delete {ref}" for ref, _ in d.cleanup_failed]
            kept = len(d.cleanup.keep)
            d.redmine_note = (
                f"분산 작업 완료 — {base_branch} 머지 완료\n\n"
                f"- work_id: {work_id}\n"
                f"- 통합: 작업 브랜치 `{target}` + 소스를 든 durable "
                f"{len(d.merged_durables)}건 (no-ff)"
                + (f" · 매니페스트 전용 {len(d.ax_only)}건은 **머지하지 않았다** "
                   f"(`#319` ⓐ)" if d.ax_only else "") + "\n"
                f"- 검토자: {reviewer or '(미지정)'}\n"
                + (f"- 커밋 연결: `{d.merge_commit}`\n" if d.merge_commit else "")
                + f"- 브랜치 정리: 삭제 {len(d.deleted_branches)}건"
                + (f" · [주의] 실패 {len(d.cleanup_failed)}건(사람 확인)" if d.cleanup_failed else "")
                + (f" · [중요] 보존 {kept}건 — 미병합은 증거다" if kept else ""))
            # ── ② Redmine 기재 (원전 6단계 ② — 상태·머지 커밋) ──────────────
            # [중요] **키는 이 코드가 도는 기계에 없다** — 이 모듈은 `.33` 에도 배달된다.
            #    그래서 마스터 대행(`/api/v1/redmine/note`)을 지나간다. 값이 아니라 본문만 만든다.
            # 🔴 [중요] **여기서 닫는다 — 상태는 「완료」다** (사용자 2026-09-04:
            #    *"레드마인 닫고 메인에 머지해야지"*). 마감은 분산 작업의 끝이고, `main` 머지가
            #    이미 일어난 자리다.
            #    [주의] 종전 규약은 *"「해결」까지만 — 닫는 것은 사람"* 이었다. 그 규약이
            #    지키려던 것은 **사람이 판단한다**인데, `finalize_work(confirm=True)` 자체가
            #    사람의 승인 발화로만 도는 자리다. 자동으로 닫히는 것이 아니다.
            if d.redmine_issue_id:
                try:
                    (api or _default_api)("POST", "/api/v1/redmine/note",
                                          {"issue_id": int(d.redmine_issue_id),
                                           "notes": d.redmine_note,
                                           "status_name": "완료",
                                           "work_id": work_id})
                    d.redmine_posted = True
                except Exception as e:                      # noqa: BLE001
                    # 머지·정리는 끝났다 — 기재 실패는 조용히 넘기지 않고 사유만 싣는다
                    logf("finalize", f"[주의] Redmine 기재 실패 — {type(e).__name__}: {e}")
        d.ok = not d.error
        return d
    except GitError as e:
        d.error = f"git 오류: {e}"
        return d
    finally:
        # [중요] push 했으면 트리를 지운다. **안 했으면 남긴다** — 그 안에 통합 결과가 있고,
        #    사람이 `commands` 를 그대로 실행할 대상이 그 트리다.
        if d.pushed and tree.exists():
            _git_rc(repo, "worktree", "remove", "--force", str(tree))
            _git_rc(repo, "worktree", "prune")


# ── 🔴 정본 ⑺ — **라운드 종결: 작업 브랜치를 한 칸 전진시킨다** (사용자 확정 2026-09-04) ──
#
# ## [중요] `main` 반영과 다른 단계다 — 오늘 그 둘을 섞어 오지시를 냈다
#
#     ② main 반영 판단   `review_work` + `finalize_work`   ← 작업 **전체**가 끝났을 때
#     ③ 라운드 종결      **여기**                          ← 매 라운드
#
# 사용자 서술: *"서브 브랜치들을 처음 등록된 분산 작업용 메인 브랜치에 머지하고 테스트하고
# 리뷰한뒤 버그가 있는가, 아니면 구조를 수정해야 하는가? 등을 확인하고 물어본뒤 분산 작업용
# 메인 브랜치에 커밋해 한단계 전진시키는거야."* · *"분산 작업 브랜치를 전진시킨게 재사용하기
# 위함이고. 전진한 메인 작업 브랜치를 기준으로 서브 작업이 있다면 해당 기점을 기준으로
# 서브 태스크용 브랜치를 추가할 생각이었어."*
#
# ## [중요] 원전에 없다 — **사용자 설계**다 (확인 2026-09-04)
#
# 원전 스킬 전수(13종)에 `review-work` 는 있고 라운드 루프는 없다. 원전 모델은
# 「조각 검증 → 서버가 feature 에 머지 → 리더가 feature→main」로 **한 번** 끝난다.
# 그러니 이것은 이식 누락이 아니라 원전보다 한 겹 더 있는 구조다. 만들기 전 셋을 답했다:
#
#     ① 원전에 있나       없다 (스킬 전수 확인)
#     ② 이미 잡는 게 있나  `integrate_durables`(머지만·push 0)와 `finalize_work`(confirm 게이트)
#                        가 재료다 — **조립이 없었을 뿐** 새로 만들지 않는다
#     ③ 오탐이면 뭐가 죽나 전진을 잘못 push 하면 다음 라운드 조각이 그 위에서 갈라진다.
#                        되돌리려면 사람이 브랜치를 되감아야 한다 → **`confirm` 게이트 필수**
#
# ## [중요] 기준이 `main` 이 아니라 **작업 브랜치**다
#
# `review_work` 는 `origin/main` 에 트리를 세운다(시뮬레이션이라 그게 맞다). 여기는
# **`origin/<작업 브랜치>`** 에 세운다 — 전진분 위에 얹는 것이므로.

ADVANCE_TREE_PREFIX = "ax-advance"


def advance_tree_path(repo: Path, work_id: str) -> Path:
    """정본 **옆**. `review_work` 트리와도 이름이 갈린다 — 둘이 동시에 있어도 안 부딪힌다."""
    return Path(repo).parent / f"{ADVANCE_TREE_PREFIX}-{work_id}"


@dataclass
class Advance:
    """라운드 종결 결과. [중요] **모르는 것을 통과로 접지 않는다.**"""
    ok: bool = False
    work_id: str = ""
    target_branch: str = ""          # 전진시킬 작업 브랜치
    before: str = ""                 # 전진 전 tip
    head: str = ""                   # 머지 뒤 트리의 HEAD
    pushed: bool = False
    merged: list = field(default_factory=list)
    ax_only: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: bool = False
    build_passed: bool | None = None   # [중요] `None` = **안 쟀다**. False 와 다르다
    build_note: str = ""
    tree: str = ""
    commands: list = field(default_factory=list)
    notes: list = field(default_factory=list)   # 레드마인 기재 등 부수 기록
    error: str = ""

    @property
    def summary(self) -> str:
        # [중요] 기재 실패 같은 **비치명 결손을 요약에 싣는다** — 성공 문장만 보면 사람이
        #    「다 됐다」로 읽는다(실측 2026-09-05: 전진은 됐고 레드마인만 비었다).
        tail = "".join(f" · {n}" for n in self.notes if n.startswith("[중요]"))
        if self.error:
            return f"[중요] {self.error}"
        b = ("[완료] 빌드 통과" if self.build_passed
             else "[중요] 빌드 실패" if self.build_passed is False
             else "[주의] 빌드 미확인")
        s = (f"조각 {len(self.merged)}개 머지 · {b} · "
             f"{self.target_branch} {self.before[:8]}→{self.head[:8]}")
        return (s + (" · **push 됨(전진)**" if self.pushed else " · push 안 함(승인 대기)")
                + tail)

    @property
    def question(self) -> str:
        """[중요] 사람에게 물을 문장. 정본이 요구하는 그 물음이다."""
        if self.build_passed is False:
            return ("빌드가 깨졌다 — **버그인가, 구조를 고쳐야 하는가?** "
                    "버그면 이 트리에서 고쳐 커밋하고, 구조 문제면 전진을 보류하고 "
                    "`.h`/`.cpp` 에 지시 주석을 남겨 다음 라운드를 등재한다.")
        if self.build_passed is None:
            return ("빌드를 **재지 못했다** — 확인 못 한 것은 통과가 아니다. "
                    "빌드를 돌린 뒤에 전진을 판단한다.")
        return ("빌드는 통과했다 — **코드에 버그가 없는가, 구조를 고쳐야 하지 않는가?** "
                "이상 없으면 승인해 전진시키고, 고칠 것이 있으면 위와 같이 다음 라운드로 넘긴다.")


def advance_work(repo: Path, *, work_id: str, work: dict, tasks, build_fn=None,
                 confirm: bool = False, remote: str = DEFAULT_REMOTE,
                 keep_tree: bool = False, api=None, decision_note: str = "",
                 logf=C._noop_log) -> Advance:
    """서브 브랜치를 **작업 브랜치에** 모아 세우고, 승인되면 그 브랜치를 전진시킨다.

    [중요] **`confirm=False` 가 기본이다** (fail-closed · `finalize_work` 와 같은 규약).
    그때는 머지·빌드만 하고 **push 하지 않으며**, 트리를 남기고 실행할 명령을 돌려준다 —
    사람이 `question` 에 답한 뒤에야 전진한다.

    [중요] **사람의 워킹트리를 건드리지 않는다** — `<정본 옆>/ax-advance-<work_id>` 에서 돈다.
    `main` 은 **만지지 않는다**: 그것은 작업 전체가 끝난 뒤 `finalize_work` 의 몫이다.
    """
    a = Advance(work_id=work_id)
    # 🔴 [중요] **이번 라운드 조각만 머지한다** (사용자 2026-09-04: *"이미 전진했는데 그냥 다
    #    머지하는게 말이 안되는거니까"*). 지난 라운드 조각은 그때 전진에서 이미 작업 브랜치로
    #    들어갔다 — 목록에 끼면 `.33` 이 「이번에 만든 것」을 못 가려낸다.
    #    [주의] 라운드 스탬프가 없는 옛 레코드는 **거르지 않는다** — 스탬프 없음을 0으로 읽어
    #    통째로 빼면 머지할 것이 사라진다.
    cur_round = int((work or {}).get("round", 1) or 1)
    stamped = [t for t in (tasks or []) if int(t.get("round") or 0) > 0]
    if stamped:
        tasks = [t for t in (tasks or []) if int(t.get("round") or 0) in (0, cur_round)]
        logf("advance", f"라운드 {cur_round} 조각 {len(tasks)}건만 머지한다 "
                        f"(지난 라운드분은 이미 작업 브랜치에 있다)")
    target = work_base_branch(work_id, work)
    if not target:
        a.error = ("작업 브랜치를 정할 수 없다 — work_id 도 target_branch 도 쓸 수 없다 "
                   "(`#319`: 이름은 `task/<work_id>/base`)")
        return a
    a.target_branch = target

    tree = advance_tree_path(repo, work_id)
    a.tree = str(tree)
    try:
        # ── ① 기준은 **작업 브랜치**다 (`review_work` 는 여기가 main 이다 — 다른 단계다) ──
        rc, out = _git_rc(repo, "fetch", remote, target)
        if rc != 0:
            a.error = f"{remote}/{target} fetch 실패: {out[:200]}"
            return a
        rc, before = _git_rc(repo, "rev-parse", f"{remote}/{target}")
        if rc != 0:
            a.error = f"{remote}/{target} tip 을 못 읽었다: {before[:200]}"
            return a
        a.before = before.strip()

        if tree.exists():
            _git_rc(repo, "worktree", "remove", "--force", str(tree))
        rc, out = _git_rc(repo, "worktree", "add", "--detach", "--force",
                          str(tree), f"{remote}/{target}")
        if rc != 0:
            a.error = f"전진 worktree 생성 실패: {out[:200]}"
            return a
        logf("advance", f"worktree {tree.name} = {remote}/{target} @ {a.before[:8]} "
                        f"(사람 트리 미접촉 · main 미접촉)")

        # ── ② 서브 브랜치 전부 머지 — [중요] 충돌이면 **통째 중단** ──────────────────
        integ = integrate_durables(tree, work_id=work_id, target_branch=target, tasks=tasks,
                                   merge_label=f"[ADVANCE] {work_id}", remote=remote, logf=logf)
        a.merged, a.ax_only, a.skipped = integ.merged, integ.ax_only, integ.skipped
        a.conflicts = integ.conflict
        if not integ.ok:
            a.error = integ.error
            return a
        rc, head = _git_rc(tree, "rev-parse", "HEAD")
        a.head = head.strip() if rc == 0 else ""
        if a.head and a.head == a.before:
            # [주의] 머지했는데 tip 이 안 움직였다 = 전진할 것이 없다. 성공으로 접지 않는다
            a.error = "머지 뒤에도 tip 이 그대로다 — 전진할 것이 없다 (조각이 이미 반영됐나)"
            return a

        # ── ③ 통합 빌드 — [중요] **한 번**. 조각별로 나눠 보지 않는다 ────────────────
        if build_fn is None:
            a.build_note = ("[주의] 빌드를 돌리지 않았다 (`build_fn` 미주입) — "
                            "**확인 못 한 것은 통과가 아니다**")
            logf("advance", a.build_note)
        else:
            try:
                res = build_fn(tree)
                a.build_passed = bool(getattr(res, "passed", res))
                a.build_note = getattr(res, "summary", lambda: str(res))() \
                    if callable(getattr(res, "summary", None)) else str(res)
            except Exception as e:                           # noqa: BLE001
                a.build_note = f"빌드 호출이 실패했다 — {type(e).__name__}: {e}"
                logf("advance", f"[중요] {a.build_note}")
            logf("advance", f"빌드 {a.build_passed} — {a.build_note[:160]}")

        # ── ④ 전진 — [중요] **승인 없이는 push 하지 않는다** ─────────────────────────
        a.commands = [f"git -C {tree} log --oneline {a.before[:8]}..HEAD",
                      f"git -C {tree} push {remote} HEAD:refs/heads/{target}"]
        if not confirm:
            a.ok = True                  # 머지·빌드까지는 됐다. 전진만 안 한 것이다
            logf("advance", "confirm=False — 전진하지 않았다 (사람의 답이 트리거다)")
            return a
        if a.build_passed is not True:
            a.error = ("빌드가 통과하지 않았다 — 전진하지 않는다. "
                       "[중요] 확인 못 한 것도 통과가 아니다")
            return a
        rc, out = _git_rc(tree, "push", remote, f"HEAD:refs/heads/{target}")
        if rc != 0:
            a.error = (f"push 거부됨 — {out.strip()[:200]}. 커밋은 트리에 남아 있다 "
                       f"(잃지 않았다). **force 하지 않는다** — 사람이 판단한다")
            return a
        a.pushed, a.ok = True, True
        logf("advance", f"[완료] {target} 전진 — {a.before[:8]} → {a.head[:8]}")

        # 🔴 **전진과 그 자리의 결정을 레드마인에 남긴다** (사용자 2026-09-04:
        #    *"추가 개선 요청했을때 레드마인에 내용이 기입되어야 할 꺼같은데 … 타이밍이
        #    안맞고"*). 이슈는 **등재 때** 이미 만들어져 있고, 여기서 노트를 붙인다.
        #
        # [중요] `decision_note` 는 **사람의 답**이다 — 「버그냐 구조냐」·「추가 개선인가
        #    마감인가」를 묻고 받은 내용을 호출자(`ax-advance`)가 그대로 실어 준다.
        #    비어 있으면 전진 사실만 적는다. **추측해서 채우지 않는다.**
        # [주의] 기재 실패가 전진을 되돌리지 않는다 — push 는 이미 끝났다. 사유만 남긴다.
        issue_id = (work or {}).get("redmine_issue_id")
        if issue_id:
            note = "\n".join([
                f"라운드 {cur_round} 전진 — `{target}` {a.before[:8]} → {a.head[:8]}",
                "",
                f"- 머지한 서브 브랜치: {len(a.merged)}건"
                + (f" ({', '.join(a.merged[:8])})" if a.merged else ""),
                f"- 통합 빌드: {a.build_note or '(미기록)'}",
            ] + (["", "## 이 자리에서 사람이 정한 것", "", decision_note]
                 if decision_note else
                 ["", "[주의] 사람의 판단이 기록되지 않았다 — "
                  "「버그냐 구조냐 · 추가 개선인가 마감인가」를 묻고 그 답을 실어야 한다"]))
            try:
                (api or _default_api)("POST", "/api/v1/redmine/note",
                                      {"issue_id": int(issue_id), "notes": note,
                                       "work_id": work_id})
                a.notes.append(f"레드마인 #{issue_id} 에 전진 기록")
            except Exception as e:                           # noqa: BLE001
                # [중요] **결과에도 싣는다** — 로그로만 남기면 아무도 안 본다. 실측
                #    2026-09-05: 호출자가 `api=` 를 안 넘겨 기재가 조용히 실패했고, 전진은
                #    성공으로 보여서 라운드 기록이 통째로 비었다(사람은 다음 라운드에서야 안다).
                why = (f"[중요] 레드마인 #{issue_id} 기재 실패 — {type(e).__name__}: {e}"
                       + ("  · `api=queue_api()` 를 넘겼는지 확인하라"
                          if api is None else ""))
                a.notes.append(why)
                logf("advance", why)
        else:
            why = "[중요] 이 work 에 레드마인 이슈 id 가 없다 — 전진을 기록하지 못했다"
            a.notes.append(why)
            logf("advance", why)
    finally:
        # [중요] push 했으면 트리를 지운다. **안 했으면 남긴다** — 사람이 그 안에서 보고 고친다
        if a.pushed and not keep_tree and tree.exists():
            _git_rc(repo, "worktree", "remove", "--force", str(tree))
            _git_rc(repo, "worktree", "prune")
    return a
