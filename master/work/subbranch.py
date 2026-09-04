"""정본 ⑷ — 조각마다 **작업 브랜치에서 갈라진 서브 브랜치**를 만든다 (사용자 확정 2026-09-02).

사용자 서술 7단계 ④: *"마스터 서버는 이 작업 브랜치에 있는 골조 파일을 기준으로 서브 태스크를
만들고, **작업 브랜치에서 갈라진 각각의 서브 브랜치를 만들고** 워커들에게 브랜치와 작업할
클래스를 전달해"*.

## [중요] 원전 인용 — 이름을 배정하는 것은 서버다

    mcp/master_orchestrator/cluster_coordinator.py:11
      "push 모델상 **서버가 브랜치명을 배정**하므로 워커는 받은 이름을 쓸 뿐(구성 안 함)."
    cluster_coordinator.assign()  →  {"durable": durable_branch(task_id), ...}

즉 워커가 이름을 짓지 않는다. 우리도 같다 — 이름은 `branch_names.durable_branch(work, task)`
로 결정되고(계층형은 `#319`), 이 모듈이 그 ref 를 **base 커밋 위에** 만들어 둔다.

## [중요] 커밋을 만들지 않는다 — ref 만 세운다

`carry.publish` 는 매니페스트 본문을 커밋해야 했으므로 worktree 를 세웠다. 여기는 **얹을
내용이 없다**: 서브 브랜치의 첫 상태는 정의상 **골조 그대로**다. 그래서

    git push <remote> <base_commit>:refs/heads/task/<work>/<task>

한 번으로 끝난다 — worktree 도, 체크아웃도, 로컬 브랜치도 만들지 않는다. 로컬에 base 커밋이
있어야 push 할 수 있으므로 없으면 base 브랜치에서 fetch 한다(`#341` 과 같은 자리 · 같은 이유).

## [중요] 멱등이다 — 이미 있으면 만들지 않는다

파견 루프가 매번 불러도 안전해야 한다. 원격에 그 ref 가 이미 있으면 **손대지 않고** 그 tip 을
돌려준다. [주의] **덮어쓰지 않는 것이 계약이다** — 워커가 이미 커밋해 둔 것을 base 로 되돌리면
검증된 작업이 조용히 사라진다. 그래서 `--force` 를 쓰지 않고, 불일치는 사유로 보고한다.

## [주의] 실패는 고치지 않고 사유를 돌려준다

쓰기 가드(`#329`)가 없으면 **막는다** — fail-closed. 파이프라인이 멈추는 것이 무방비로 미는
것보다 낫다. 사유가 복구 명령을 가리키므로 사람이 한 줄로 되살린다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import branch_names
from .attempt import WRITE_REMOTE, GitError, _git
from .attempt import guard_or_reason as _guard_or_reason, has_commit as _has_commit, remote_tip as _remote_tip


@dataclass
class Created:
    task_id: str = ""
    branch: str = ""
    tip: str = ""                # 그 ref 가 가리키는 커밋 (신설이면 base_commit)
    created: bool = False        # 이번 호출이 만들었나
    existed: bool = False        # 이미 있어서 손대지 않았나
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.branch) and bool(self.tip) and not self.error


def _ensure_base_locally(repo: Path, work_id: str, base: str, remote: str) -> str:
    """base 커밋이 로컬에 없으면 작업 브랜치에서 가져온다. 실패 사유를 돌려준다(`""`=성공).

    [중요] `#341` 이 물린 자리와 같다 — `twin_base.resolve()` 는 bare 를 직접 읽어 「있다」고
    하는데 여기는 **미러의 로컬 객체**를 쓴다. 둘이 보는 곳이 달라 「있다고 했는데 없다」가 된다.
    """
    if _has_commit(repo, base):
        return ""
    base_br = branch_names.base_branch(work_id)
    try:
        _git(repo, "fetch", remote, f"+refs/heads/{base_br}:refs/ax/subbranch-base/{work_id}")
    except GitError as e:
        return (f"기준 커밋 {base[:8]} 이 로컬에 없고 작업 브랜치도 못 가져왔다 "
                f"— {base_br}: {str(e)[:160]}")
    if not _has_commit(repo, base):
        return (f"작업 브랜치를 가져왔는데도 기준 커밋 {base[:8]} 이 없다 "
                f"— {base_br} tip 과 어긋난다")
    return ""


def create(paths, work_id: str, task_id: str, *, base_commit: str,
           remote: str = WRITE_REMOTE, logf=None, round_no: int = 0) -> Created:
    """조각의 서브 브랜치를 base 커밋 위에 세운다. **멱등 · 덮어쓰지 않음.**

    [중요] `round_no` 가 있으면 이름에 들어간다 — `task/<work>/r<N>/<task>`. 라운드가
    바뀌면 이름이 갈리므로 이미 전진한 라운드의 조각과 섞이지 않는다.
    """
    log = logf or (lambda m: None)
    c = Created(task_id=task_id)
    try:
        c.branch = branch_names.durable_branch(work_id, task_id, round_no)
    except branch_names.BranchNameError as e:
        c.error = str(e)
        return c

    base = (base_commit or "").strip()
    if not base:
        c.error = "기준 커밋이 비었다 — 어디서 갈라야 할지 모른 채 브랜치를 만들지 않는다"
        return c

    repo = Path(paths.repo)
    try:
        tip = _remote_tip(repo, remote, c.branch)
        if tip:
            # [중요] 이미 있다 — 손대지 않는다. 워커의 커밋이 여기 실려 있을 수 있다.
            c.tip, c.existed = tip, True
            log(f"[subbranch] {task_id} → {c.branch} 이미 있다 (tip={tip[:8]})")
            return c

        # [주의] **push 직전에 쓰기 가드를 확인한다** (`#329`) — 여기가 실제로 미는 자리다.
        guard = _guard_or_reason(paths)
        if guard:
            c.error = guard
            return c

        why = _ensure_base_locally(repo, work_id, base, remote)
        if why:
            c.error = why
            return c

        _git(repo, "push", remote, f"{base}:refs/heads/{c.branch}")
        c.tip, c.created = base, True
    except GitError as e:
        c.error = f"{type(e).__name__}: {e}"
        return c

    log(f"[subbranch] {task_id} → {c.branch} 신설 (base={base[:8]})")
    return c


def create_all(paths, work_id: str, task_ids, *, base_commit: str,
               remote: str = WRITE_REMOTE, logf=None) -> list:
    """조각 전부. [중요] **하나가 실패해도 나머지를 시도한다** — 결과 목록으로 보고한다.

    [주의] 여기서 멈추면 「어느 조각이 왜 안 됐나」를 사람이 로그에서 뒤져야 한다. 전수를
    돌려주고 **판정은 호출자**가 한다(파견은 ok 인 것만 보낸다).
    """
    return [create(paths, work_id, t, base_commit=base_commit, remote=remote, logf=logf)
            for t in task_ids]
