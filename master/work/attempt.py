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


# [중요] **마스터측 attempt 배선이 여기 있었다 — `#327` 로 걷어냈다** (2026-08-28).
#    `AttemptTree` · `tree_path` · `ensure_attempt_tree` · `apply_responses` · `Pushed` ·
#    `push_attempt_for` — 「커밋 후 검증」 계층의 마스터 쪽 절반이다.
#
# [중요] **걷은 근거는 측정이다.** `#317` 미결 ⑦ 이 *"통합자 커밋 전 검증 → 워커 커밋 후 검증"*
#    을 물었고, 재 보니 **이 배선은 한 번도 안 돌았다** — 프로덕션 호출자 0 · bare 에 attempt
#    브랜치 0. `master/README.md` 도 이미 *"실 파이프라인이 한 번도 부르지 않았다"* 고 적어 뒀다.
#    사용자 결정 2026-08-28: **검증 → 통과분만 커밋**이 정본이고, 이 층은 걷는다.
#
# [주의] **`coordinator.py` 의 2-tier 원전 이식은 남겼다** — `selftest` 드라이런이 그것을
#    운송 수단 삼아 매니페스트 왕복·`[PSEUDO]` 제거·좀비 epoch 거부를 증명한다(살아 있는
#    소비자다). **소비자 0 인 것만 걷는 것**이 이번 절단면이다(사용자 결정).
#
# [주의] 워크트리 헬퍼는 `integrate.py` 가 **자기 것을 따로 갖고 있다**(`worktree_path`) —
#    여기 것이 사라져도 통합자는 영향이 없다. 되살릴 조건은 `#327` 노트, 원형은 git 이력에.

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


# [중요] **가드 고유 표식** (`#329`) — 「우리 것이 아니다」와 「낡았다」를 가르는 근거다.
#    둘 다 있어야 우리 훅으로 본다: 하나는 **판정 분기**(`case` 패턴), 하나는 **거절 메시지**라
#    성격이 달라 한쪽만 우연히 겹칠 일이 없다.
# [주의] **원본에서 이 문자열이 사라지면 판정이 조용히 무너진다** — `test_attempt` 가
#    원본에 표식이 있는지 먼저 잰다(조건 4). 표식을 바꾸면 그 검사가 **먼저** 죽는다.
GUARD_MARKS = ("refs/heads/attempt/", "pre-push 거부")

# 상태 넷 — [중요] **「낡았다」와 「우리 것이 아니다」는 값이 다르다.**
#    전자는 *"지금 막고 있다, 사본이 낡았을 뿐"*, 후자는 **"지금 아무것도 안 막고 있다"**.
STATE_MISSING = "missing"     # 파일이 없다
STATE_FOREIGN = "foreign"     # [중요] 우리 가드가 아니다 (예: `git lfs install` 이 덮었다)
STATE_STALE = "stale"         # 우리 것이지만 원본과 다르다
STATE_OK = "ok"


def hook_status(paths) -> dict:
    """설치돼 있나 · **우리 것인가** · 원본과 같나 · 실행 가능한가.

    [중요] `#329` — 종전에는 「우리 것이 아니다」를 **「원본과 다르다」로 뭉갰다.** 실측
    2026-08-28: `git lfs install` 이 NS 클론의 훅을 덮어 가드가 **통째로 사라져 있었는데**,
    주석 표기만 옛 판이던 ModularStage 와 **같은 문구**를 받았다. 하나는 지금 막고 있고 다른
    하나는 **아무것도 안 막고 있는데** 같은 말을 하면 사람이 뒤를 안 본다 — 실제로 안 봤다.
    """
    t = hook_target(paths)
    if not t.exists():
        return {"installed": False, "ours": False, "current": False, "executable": False,
                "state": STATE_MISSING, "reason": f"없다: {t}"}
    try:
        raw = t.read_bytes()
        text = raw.decode("utf-8", "replace")
    except OSError as e:
        return {"installed": True, "ours": False, "current": False, "executable": False,
                "state": STATE_MISSING, "reason": f"읽지 못했다: {e}"}
    ours = all(m in text for m in GUARD_MARKS)
    same = raw == HOOK_SOURCE.read_bytes()
    import os
    ex = os.access(t, os.X_OK)
    if not ours:
        # [중요] **가장 위험한 상태다** — 파일은 있는데 우리 가드가 아니다. 사유가 그것을
        #    말해야 사람이 `install-hook` 을 부른다.
        head = text.strip().splitlines()[1:2]
        return {"installed": True, "ours": False, "current": False, "executable": ex,
                "state": STATE_FOREIGN,
                "reason": ("[중요] **우리 가드가 아니다** — 다른 훅이 덮었다"
                           + (f" (첫 줄: {head[0].strip()[:60]})" if head else "")
                           + ". `install-hook` 으로 다시 세울 것 — 지금은 아무것도 안 막는다")}
    if not same:
        return {"installed": True, "ours": True, "current": False, "executable": ex,
                "state": STATE_STALE,
                "reason": "[주의] 우리 가드이지만 **원본과 다르다** (낡은 사본이거나 손으로 "
                          "고쳤다) — 막고는 있다. `install-hook` 으로 맞출 것"}
    return {"installed": True, "ours": True, "current": True, "executable": ex,
            "state": STATE_OK if ex else STATE_STALE,
            "reason": "정상" if ex else "실행 권한이 없다"}


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


# [중요] **`merge_verified` 가 여기 있었다 — `#327` 로 걷어냈다.** 검증 통과분을 durable 로
#    올리는 함수였고, `master/README.md` 가 *"부르는 파이프라인 호출자는 아직 없다"* 고
#    적어 둔 채 끝까지 없었다.


# ─────────────────────────────────────────────────────────────────────────────
# 공유 git/가드 유틸 — [중요] **`carry.py` 에서 옮겨 왔다** (매니페스트 철거, 2026-09-02).
#
# `#327` 이 정한 규칙을 그대로 따른다: *"유틸이 여러 곳에 쓰이면 옮길지 남길지 판정하고 근거를
# 적는다."* 이 셋은 매니페스트와 무관한 순수 git/가드 조회이고, 소비자가 `carry` 밖에 있다
# (`subbranch`·`cleanup`). 가드의 집이 이 파일이므로(`hook_status`) 여기가 자리다.
# ─────────────────────────────────────────────────────────────────────────────


def remote_tip(repo, remote: str, branch: str) -> str:
    """그 원격 브랜치의 tip. 없으면 `""`."""
    out = _git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
    for ln in out.splitlines():
        parts = ln.split()
        if parts:
            return parts[0]
    return ""


def has_commit(repo, sha: str) -> bool:
    """이 저장소가 그 커밋 객체를 갖고 있나. [중요] **없으면 `worktree add`·push 가 죽는다.**"""
    if not (sha or "").strip():
        return False
    try:
        _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


def guard_or_reason(paths) -> str:
    """쓰기 가드가 서 있나. 서 있으면 `""`, 아니면 **막을 사유**를 돌려준다 (`#329`).

    [중요] **「낡았다」는 막지 않는다** — 그건 우리 가드가 맞고 지금 막고 있다는 뜻이다.
    막는 것은 **없거나 우리 것이 아닐 때**뿐이다. 그 구분이 `#329` 의 요지다.
    [주의] 확인 자체가 실패하면(예외) **막는다** — 미확인은 통과가 아니다.
    """
    try:
        st = hook_status(paths)
    except Exception as e:                                   # noqa: BLE001
        return (f"[중요] 쓰기 가드를 확인하지 못했다 ({type(e).__name__}: {e}) — "
                f"미확인은 통과가 아니다. push 하지 않는다 (`#329`)")
    if st.get("state") in (STATE_MISSING, STATE_FOREIGN):
        return (f"[중요] 쓰기 가드가 서 있지 않다 — {st.get('reason')} "
                f"· 복구: `python -m master.work.attempt install-hook <프로젝트>` (`#125`·`#329`)")
    return ""

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
