"""마스터측 attempt 계층 — **Flow Y 배선** (소 1.2.2 · `#123`).

    ① 마스터 (.57)   소스 조립 · 추론 라우팅 · [중요] **커밋**   ← 이 파일
    ② 작업장 (윈도우) pull → UE 빌드/RunTests → 보고. 판단 안 함 · stateless
    노드 (BC-250)    추론만 — 텍스트 in/out

[중요] **왜 이 파일이 생겼나.** `coordinator.py` 는 원전 2-tier 를 그대로 들고 있었지만
**실 파이프라인이 그것을 한 번도 부르지 않았다**(리포트 16 §2 실측: `import` 하는 곳은
`test_coordinator.py` 와 `selftest.py` 둘뿐). 이식은 끝나 있었고 **배선이 없었다.**

## [중요] 성공·실패 무관 push — `#115` 와 §8.4 의 모순이 여기서 풀린다

`integrate.py` 머리말은 *"실패는 커밋하지 않는다"* 라고 적고 그 근거로
*"쓰는 주체가 하나가 되면 **실패 attempt 를 남길 브랜치가 없다**"* 를 들었다. [중요] **그 전제가
사라졌다** — attempt 계층이 돌아왔으므로 실패를 담을 ephemeral 브랜치가 **있다.**
따라서 `docs/8-git-authority.md` §8.4 *"실패도 커밋한다"* 가 맞고, 원전이 그랬듯

    성공 → attempt push → 검증 → [중요] **통과분만** durable(`task/<id>`) 로 merge
    실패 → attempt push → 사유와 함께 `[FEEDBACK]` → 같은 durable 에서 재시도

durable 은 여전히 **단일 writer** 다. 잃는 것이 없다 — ephemeral 은 더러워져도 되는 자리다.

[주의] **`integrate.py` 를 지우지 않는다.** §8.4 규약대로 두 토폴로지를 나란히 두고 **측정으로**
고른다. 이 파일은 그것을 대체하는 것이 아니라 **옆에 선다**.

## [중요] 정본 트리는 건드리지 않는다

작업 트리는 `<프로젝트>/ax-wt-<work_id>` — 정본 클론 **옆**이지 안이 아니다(`integrate.py` 가
작업장에 세운 것과 같은 규약). 정본은 계속 `main` 에 앉아 있어야 한다. 색인기의
`merge --ff-only` 가 *"마스터는 이 클론에 커밋하지 않는다"* 를 전제로 하고, 그 전제가 깨지면
**미러가 갈라졌다**는 오진이 뜬다.

## [중요] push 표면이 `origin` 이 아니다

정본의 `origin` push 는 봉인돼 있다(`DISABLED://…-PLAN.md-2.1`). Flow Y 를 위해 별도 표면
`gitea-write`(Gitea SSH, 워커 `.43` 이 쓰는 것과 같은 경로)를 열었고, 봉인이 막아 주던 것은
클론의 `pre-push` 훅이 대신한다 — `attempt/*`·`task/*` 밖의 ref 와 **삭제 전부**를 거부한다.
[중요] 서버측 브랜치 보호로는 못 한다: 네 대가 **같은 Gitea 계정 `Sim`** 으로 인증해서 Gitea 가
기계를 구분할 수 없다(리포트 16 §5 실측).

## [주의] 색인기는 깨어나지만 재색인하지 않는다 (실측)

`events/post_receive_hook.py` 는 **ref 를 안 가리고** 전부 스풀에 넣는다. 그러나
`consumer.process_event` 는 `ev.ref` 를 보지 않고 정본에서 `merge --ff-only FETCH_HEAD` 를
하는데, 그 for-merge 항목은 **현재 브랜치(`main`)의 업스트림**뿐이다 → attempt push 는
`from == to` 가 되어 **재색인을 건너뛴다.** 리포트 14 §17 이 이미 잰 경로다
(*"push 3회 → 15회 깨어나 14회 건너뜀"*). 비용은 깨어남과 fetch 한 번이고, 파이프라인이
도는 동안은 색인 게이트(소 3.5.1)가 `in_progress` 를 보고 **멈춰 있다.**
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import coordinator as C
# [중요] `_git` 을 재사용한다 — 커밋 신원(`cluster@local`)·타임아웃·예외 형태가 이식본과
#    **한 글자도 갈리면 안 된다.** 여기서 따로 만들면 조용히 갈라진다.
from .coordinator import GitError, _git
from .branch_names import durable_branch

WORKTREE_PREFIX = "ax-wt"
WRITE_REMOTE = "gitea-write"

# [중요] 훅의 **원본은 저장소 안**이다. `.git/hooks/` 는 어느 저장소도 추적하지 않으므로 거기만
#    고치면 클론을 다시 만들 때 가드가 조용히 사라진다 — `events/post_receive_hook.py` 가 같은
#    규약을 같은 이유로 못박아 뒀다.
HOOK_SOURCE = Path(__file__).resolve().parent / "pre_push_hook.sh"
HOOK_NAME = "pre-push"


class AttemptError(RuntimeError):
    """attempt 를 올릴 수 없다. [중요] **모르는 채로 push 하지 않는다.**"""


@dataclass
class AttemptTree:
    """마스터 소유 작업 트리. [중요] **사람의 트리에 같은 논리를 적용하지 말 것.**"""

    path: Path
    base: str = ""
    created: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def tree_path(paths, work_id: str) -> Path:
    """정본 **옆**. 안에 두면 색인 대상과 겹치고 `add -A` 가 그것을 삼킨다."""
    return Path(paths.root) / f"{WORKTREE_PREFIX}-{work_id}"


def ensure_attempt_tree(paths, work_id: str, *, at_commit: str) -> AttemptTree:
    """`at_commit` 에 선 트리를 보장한다. 있으면 **그 커밋으로 되맞춘다.**

    [중요] `at_commit` 을 모르면 만들지 않는다 — 어느 시점에 적용하는지 모르면 적용해선 안 된다
    (`integrate.ensure_worktree` 와 같은 판단).
    """
    base = (at_commit or "").strip()
    if not base:
        raise AttemptError("기준 커밋이 비었다 — 어디에 적용할지 모른 채로 트리를 세우지 않는다")

    repo = Path(paths.repo)
    if not repo.is_dir():
        raise AttemptError(f"정본 클론이 없다: {repo}")

    wt = AttemptTree(path=tree_path(paths, work_id), base=base)
    if not wt.path.exists():
        _git(repo, "worktree", "add", "--detach", "--force", str(wt.path), base)
        wt.created = True
    else:
        # 재사용 — 기준으로 되맞춘다. [중요] 이 트리가 **파이프라인 소유**라서만 안전하다.
        _git(wt.path, "checkout", "--detach", "--force", base)

    # [중요] 추적되지 않은 잔재를 확인한다. `push_attempt` 가 `add -A` 를 하므로(원전 그대로)
    #    남아 있으면 **이번 조각과 무관한 것이 커밋에 실린다.** 지우지 않고 **거부**한다 —
    #    무엇이 남았는지 모르는 채 지우는 쪽이 더 위험하다.
    out = _git(wt.path, "status", "--porcelain")
    stray = [ln[3:] for ln in out.splitlines() if ln.startswith("??")]
    if stray:
        wt.error = ("[중요] 추적되지 않은 잔재가 있다 — 지우지 않고 멈춘다 "
                    f"({len(stray)}건: {', '.join(stray[:5])}"
                    f"{' …' if len(stray) > 5 else ''})")
        return wt

    head = _git(wt.path, "rev-parse", "HEAD")
    if not (head.startswith(base) or base.startswith(head[:len(base)])):
        wt.error = f"HEAD 가 기준과 다르다 — 기대 {base[:12]} 실측 {head[:12]}"
    return wt


def apply_responses(responses):
    """응답들을 트리에 쓰는 `work_fn` 을 만든다 — `coordinator.push_attempt` 의 주입 자리.

    [중요] **원전이 만든 그 seam 을 그대로 쓴다.** 드라이런은 `fake_workshop`, 실전은 이것 —
    같은 2-tier 경로를 타므로 *"드라이런에서만 되는" 코드가 생기지 않는다.*

    `Response.files` 는 `{경로: 완성 본문}` 이다(부분 diff 가 아니다) — 그대로 쓴다.
    [주의] `target_rel` 인자는 원전 서명 때문에 받지만 여기서는 쓰지 않는다. 파일 목록은
    응답이 들고 있고, 그것이 **여러 개**다.
    """
    def _fn(repo: Path, target_rel: str) -> None:
        for res in responses:
            for rel, body in (res.files or {}).items():
                rel = rel.replace("\\", "/").lstrip("/")
                if ".." in rel.split("/"):
                    raise AttemptError(f"경로가 트리를 벗어난다: {rel!r}")
                p = Path(repo) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")
                # [중요] 되읽어 확인한다. 원전이 해시 대조를 둔 자리와 같은 목적 —
                #    쓴 줄 알았는데 안 쓰인 것이 이 저장소가 반복해 물린 유형이다.
                if p.read_text(encoding="utf-8") != body:
                    raise AttemptError(f"쓴 내용이 다시 읽히지 않는다: {rel}")
    return _fn


@dataclass
class Pushed:
    """한 태스크의 attempt 결과."""

    task_id: str = ""
    workshop: str = ""
    attempt: str = ""
    durable: str = ""
    head: str = ""
    files: list = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.head) and not self.error

    def summary(self) -> str:
        if self.error:
            return f"{self.task_id}: [중요] {self.error}"
        return (f"{self.task_id}: attempt {self.attempt} ← {self.head[:8]} "
                f"· 파일 {len(self.files)}")


def push_attempt_for(paths, *, work_id: str, task_id: str, workshop: str, ts: str,
                     responses, base_commit: str, message: str = "",
                     remote: str = WRITE_REMOTE, logf=C._noop_log) -> Pushed:
    """[중요] **성공·실패 무관** — 받은 응답을 attempt 브랜치에 올린다.

    이 함수는 **판정하지 않는다.** 판정(층1·층2·빌드)은 durable merge 앞에 서고, 여기서
    막으면 §8.4 *"실패도 커밋한다"* 가 다시 깨진다 — 실패의 증거가 어디에도 안 남는다.
    """
    p = Pushed(task_id=task_id, workshop=workshop, durable=durable_branch(work_id, task_id))
    p.files = sorted({f for r in responses for f in (r.files or {})})
    if not p.files:
        p.error = "올릴 파일이 없다 — 응답이 비었다"
        return p

    wt = ensure_attempt_tree(paths, work_id, at_commit=base_commit)
    if not wt.ok:
        p.error = wt.error
        return p

    a = C.assign_attempt(work_id, task_id, workshop, ts)
    p.attempt, p.durable = a["attempt"], a["durable"]
    logf("assign", f"{task_id} → {workshop}, attempt={p.attempt}")

    msg = message or f"{task_id}: 마스터 적용 (검증 전 — ephemeral)"
    try:
        p.head = C.push_attempt(wt.path, p.attempt, base_commit,
                                apply_responses(responses), "",
                                message=msg, remote=remote, logf=logf)
    except GitError as e:
        # [주의] 변경이 없으면 commit 이 rc=1 이다. 그건 **작업이 아무것도 안 했다는 사실**이므로
        #    삼키지 않되, 진짜 git 사고와 갈라야 한다.
        #
        # [중요] **문구로 가르지 않는다.** 이 기계는 `ko_KR.UTF-8` 이라 git 이 한국어로 말한다 —
        #    `"nothing to commit"` 대조는 여기서 **조용히 빗나간다**(실측: 이 테스트가 잡았다).
        #    대신 **트리 상태로** 판정한다: 스테이징 후에도 변경이 0이면 그것이 곧 그 사실이다.
        #    [주의] `integrate.py` 는 아직 문구 대조를 쓴다 — 거기는 git 이 영어인 윈도우 작업장에서
        #    도는 코드라 지금은 맞지만, 마스터로 옮겨오면 같은 자리에서 깨진다.
        try:
            dirty = _git(wt.path, "status", "--porcelain")
        except GitError:
            dirty = "?"                      # 상태조차 못 읽으면 사실 주장을 하지 않는다
        p.error = ("커밋할 변경이 없다 — 응답이 기존 파일과 같다" if dirty == ""
                   else f"attempt push 실패: {e}")
    return p


# ── 소 1.2.4 (`#125`) 원격 정리 — [중요] **도달 가능한 것만** ──────────────────────
#
# 사용자 결정 2026-08-14. 기준은 `work/cleanup.py` 가 로컬 브랜치에 쓰는 것과 **같은 것 하나**:
# *"그 팁이 `<remote>/<기본브랜치>` 에서 도달 가능한가"* = 정말 병합됐다 = 지워도 잃는 것이 없다.
#
# [중요] **이 기준을 고른 근거는 실측이다** (리포트 16 §9): 원격 attempt 4건이 **전부 main 에서 도달
# 불가**였고 응답 스풀에는 그중 어느 것도 없었다. 원전대로 work 종료 시 `delete=True` 를 돌렸다면
# **실패 시도 3건의 유일한 사본이 사라졌다.** [주의] 단서 — 그 셋은 스풀 설계(소 1.3.2) *이전*의
# 산물이다. 이후 작업은 스풀이 응답을 들고 있어 조건이 다르다. 그래도 기준은 이쪽이 안전하다:
# **병합되면 자동으로 지울 수 있게 되므로** 영구 누적이 아니다.
#
# [주의] **범위는 ephemeral 뿐이다 — durable(`task/*`)은 원전대로 보존한다.** 세어서 보고만 한다.
# durable 을 없애는 것은 그것을 만든 주체(요청자)와 사람의 판단이다(§8.4).

@dataclass
class RemoteCleanup:
    """원격 정리 계획. [중요] **지울 것과 남길 것을 둘 다 들고 있다** (`cleanup.py` 와 같은 형태)."""

    delete: list = field(default_factory=list)          # [(ref, tip)]
    keep: list = field(default_factory=list)            # [(ref, 사유)]
    durable: list = field(default_factory=list)         # [(ref, tip)] — [중요] 세기만 한다
    deleted: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def summary(self) -> str:
        return (f"ephemeral 삭제 대상 {len(self.delete)} · 보존 {len(self.keep)} · "
                f"durable {len(self.durable)}건(건드리지 않음)"
                + (f" · 실제 삭제 {len(self.deleted)}" if self.deleted else "")
                + (f" · [중요] 오류 {len(self.errors)}" if self.errors else ""))


def plan_remote_cleanup(paths, task_id: str = "", *, work_id: str = "",
                        remote: str = WRITE_REMOTE,
                        base_branch: str = "main") -> RemoteCleanup:
    """무엇을 지울 수 있는지 **계획만** 낸다. [중요] 지우지 않는다.

    범위는 좁은 것부터 넓은 것까지 셋이다 (`#319` 계층형):

        work_id + task_id   그 조각만            attempt/<W>/<T>/*  ·  task/<W>/<T>
        work_id 만          그 작업 전부          attempt/<W>/*      ·  task/<W>/*  (base 포함)
        둘 다 없음          전부                  attempt/*          ·  task/*

    [중요] **`task_id` 만 주는 옛 호출도 받는다** — 옛 한 칸짜리 durable(`task/<task_id>`)이
    origin 에 실재하고(사용자 결정: 읽기만 호환), 그것을 못 보면 정리에서 조용히 빠진다.
    [주의] git 의 ls-remote 패턴은 `/` 를 넘는다(실측 2026-08-27) — `task/*` 하나가 평평한
    옛 이름과 계층형을 **둘 다** 잡는다. 훅의 POSIX `case` 와 같은 성질이다.

    [주의] 인자 `base_branch` 는 **기본 브랜치(main)** 이지 작업 브랜치가 아니다 —
    `branch_names.base_branch()` 와 이름이 겹친다. 여기서 안 고치는 이유는 키워드로 부르는
    호출자가 있어서다. 고칠 때는 호출자를 같이 본다.
    """
    repo = Path(paths.repo)
    plan = RemoteCleanup()

    # [중요] tracking ref 를 최신으로 만든다. 낡은 것으로 재면 병합된 것을 미병합으로 본다 —
    #    그 방향은 안전하지만(보존) 계획이 조용히 쓸모없어진다.
    try:
        _git(repo, "fetch", "--quiet", "--prune", remote)
    except GitError as e:
        plan.errors.append(f"fetch 실패 — 낡은 tracking 으로 판정하지 않는다: {e}")
        return plan

    tracking = f"refs/remotes/{remote}/{base_branch}"
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", tracking)
    except GitError:
        plan.errors.append(f"{tracking} 이 없다 — 도달 여부를 잴 수 없으므로 아무것도 지우지 않는다")
        return plan

    if work_id and task_id:
        pats = [f"refs/heads/attempt/{work_id}/{task_id}/*",
                f"refs/heads/task/{work_id}/{task_id}"]
    elif work_id:
        pats = [f"refs/heads/attempt/{work_id}/*", f"refs/heads/task/{work_id}/*"]
    elif task_id:
        # 옛 평평한 이름 + 계층형 어디에 있든 그 조각을 잡는다 (읽기 호환)
        pats = [f"refs/heads/attempt/{task_id}/*", f"refs/heads/attempt/*/{task_id}/*",
                f"refs/heads/task/{task_id}", f"refs/heads/task/*/{task_id}"]
    else:
        pats = ["refs/heads/attempt/*", "refs/heads/task/*"]
    try:
        out = _git(repo, "ls-remote", "--heads", remote, *pats)
    except GitError as e:
        plan.errors.append(f"원격 목록 실패: {e}")
        return plan

    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2 or "refs/heads/" not in parts[1]:
            continue
        tip, ref = parts[0], parts[1].split("refs/heads/", 1)[1]

        if ref.startswith("task/"):
            plan.durable.append((ref, tip))          # [중요] 원전대로 보존 — 세기만 한다
            continue

        # [중요] `--is-ancestor` 의 **종료코드로 판정하지 않는다.** 그러면 "미병합(rc=1)" 과
        #    "판정 실패(rc≠0,1)" 를 우리 예외 문구를 문자열 대조해서 갈라야 하고, 그 방식은
        #    이 세션에 이미 한 번 조용히 빗나갔다(git 이 `ko_KR` 로 말하는 자리).
        #    대신 **값으로** 판정한다: merge-base(tip, main) == tip ⇔ tip 이 main 에 있다.
        try:
            base = _git(repo, "merge-base", tip, tracking)
        except GitError as e:
            plan.keep.append((ref, f"도달 여부를 확인하지 못했다 ({e})"))
            continue
        if base and base.strip() == tip:
            plan.delete.append((ref, tip))
        else:
            plan.keep.append((ref, f"{remote}/{base_branch} 에 병합되지 않았다 — 증거일 수 있다"))

    return plan


def apply_remote_cleanup(paths, plan: RemoteCleanup, *,
                         remote: str = WRITE_REMOTE, logf=C._noop_log) -> RemoteCleanup:
    """계획의 삭제분을 실제로 지운다. [중요] **계획이 고른 것만** 건드린다.

    [주의] 마지막 방어선은 이 함수가 아니라 클론의 `pre-push` 훅이다 — 같은 도달 기준을 훅이
    **한 번 더** 판정하므로, 이 함수에 결함이 생겨도 미병합 증거는 지워지지 않는다.
    [중요] 이 함수는 파이프라인·운영 명령의 자리다. **대화형 세션에서 사람이 부르지 않는다**
    (`CLAUDE.md`: 브랜치 삭제는 승인이 있어도 사람 세션이 하지 않는다).
    """
    repo = Path(paths.repo)
    for ref, tip in plan.delete:
        try:
            _git(repo, "push", "--quiet", remote, "--delete", ref)
            plan.deleted.append(ref)
            logf("cleanup", f"{ref} 제거 (tip={tip[:8]}, 병합 확인됨)")
        except GitError as e:
            plan.errors.append(f"{ref} 삭제 실패: {e}")
    return plan


# ── 가드 설치·검증 — [중요] **가드는 자기가 설치돼 있는지 말할 수 있어야 한다** ─────

def hook_target(paths) -> Path:
    """정본 클론의 훅 경로. [중요] 워크트리가 아니라 **클론**의 `.git/hooks/` 다 —
    `git worktree` 는 훅을 공유하므로 한 곳에 두면 작업 트리의 push 에도 걸린다."""
    return Path(paths.repo) / ".git" / "hooks" / HOOK_NAME


def hook_status(paths) -> dict:
    """설치돼 있나 · 원본과 같나 · 실행 가능한가. **추측하지 않고 읽어서** 답한다."""
    t = hook_target(paths)
    if not t.exists():
        return {"installed": False, "current": False, "executable": False,
                "reason": f"없다: {t}"}
    try:
        same = t.read_bytes() == HOOK_SOURCE.read_bytes()
    except OSError as e:
        return {"installed": True, "current": False, "executable": False,
                "reason": f"읽지 못했다: {e}"}
    import os
    ex = os.access(t, os.X_OK)
    return {"installed": True, "current": same, "executable": ex,
            "reason": ("정상" if same and ex else
                       ("실행 권한이 없다" if same else "[중요] 원본과 다르다 — 손으로 고쳤나?"))}


def install_hook(paths) -> dict:
    """원본을 정본 클론에 설치한다. **덮어쓴다** — 원본이 SSOT 이므로 그것이 맞다."""
    t = hook_target(paths)
    if not HOOK_SOURCE.is_file():
        raise AttemptError(f"훅 원본이 없다: {HOOK_SOURCE}")
    t.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOOK_SOURCE, t)
    t.chmod(0o755)
    st = hook_status(paths)
    if not (st["installed"] and st["current"] and st["executable"]):
        raise AttemptError(f"설치했는데 검증이 실패했다: {st['reason']}")
    return st


def merge_verified(paths, *, work_id: str, task_id: str, attempt: str,
                   submit_epoch: int, current_epoch: int,
                   remote: str = WRITE_REMOTE, logf=C._noop_log) -> dict:
    """검증을 통과한 attempt 만 durable 로 올린다 — [중요] epoch 게이트가 먼저 판정한다.

    [주의] **빌드 판정은 이 함수의 몫이 아니다.** 호출자가 작업장(`.2`)의 판정을 받아 통과했을
    때만 부른다 — 리눅스가 강제한 유일한 변경(빌드 스텝의 원격 위임, 소 1.3.1)이 그 자리다.
    """
    wt = tree_path(paths, work_id)
    if not wt.is_dir():
        raise AttemptError(f"작업 트리가 없다: {wt}")
    return C.verify_and_merge(wt, attempt, durable_branch(work_id, task_id),
                              submit_epoch=submit_epoch, current_epoch=current_epoch,
                              remote=remote, logf=logf)


# ── CLI — [중요] 정리는 **계획이 기본**이다 (`cleanup.py` 와 같은 규약) ─────────────

def main(argv: list[str] | None = None) -> int:
    from ..context_search.paths import resolve

    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "status"

    if cmd in ("-h", "--help", "help"):
        print("사용법: python -m master.work.attempt status|install-hook|plan|apply [프로젝트]")
        print("  status        가드가 설치돼 있는지 · 원본과 같은지 읽어서 보고")
        print("  install-hook  훅 원본을 정본 클론에 설치 (원본이 SSOT — 덮어쓴다)")
        print("  plan          [중요] 원격 정리 계획만 낸다 (기본)")
        print("  apply         계획의 삭제분을 실제로 지운다 — [중요] 대화형 세션에서 부르지 말 것")
        return 0

    project = args[1] if len(args) > 1 else ""
    paths = resolve(project)

    if cmd == "status":
        st = hook_status(paths)
        mark = "[완료]" if st["current"] and st["executable"] else "[중요]"
        print(f"{mark} pre-push 가드: {st['reason']}")
        print(f"   원본  {HOOK_SOURCE}")
        print(f"   설치  {hook_target(paths)}")
        return 0 if st["current"] and st["executable"] else 1

    if cmd == "install-hook":
        st = install_hook(paths)
        print(f"[완료] 설치 완료 — {hook_target(paths)} ({st['reason']})")
        return 0

    if cmd in ("plan", "apply"):
        plan = plan_remote_cleanup(paths)
        print(plan.summary())
        for ref, tip in plan.delete:
            print(f"  삭제 대상  {ref}  {tip[:8]}")
        for ref, why in plan.keep:
            print(f"  보존       {ref}\n               → {why}")
        for ref, tip in plan.durable:
            print(f"  durable    {ref}  {tip[:8]}  (원전대로 보존)")
        for e in plan.errors:
            print(f"  [중요] {e}")
        if cmd == "apply":
            if not plan.delete:
                print("지울 것이 없다 — 아무것도 하지 않았다.")
                return 0
            apply_remote_cleanup(paths, plan,
                                 logf=lambda s, m: print(f"  [{s}] {m}"))
            print(plan.summary())
        return 1 if plan.errors else 0

    print(f"모르는 명령: {cmd} (--help 참조)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
