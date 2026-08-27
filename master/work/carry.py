"""매니페스트 git-carried 배달 (#185, M5 판정 — 사용자 확정 2026-08-17).

원전(C.2)은 서버가 `.claude/tasks/<id>/context.md` 를 base 에 commit 해서 실어 보냈다 —
작업장은 체크아웃/fetch 만 하면 디스크에 있고 검색을 안 한다. 우리는 scp 로 밀어 넣고
있었는데, 그 선택의 근거(*"마스터는 push 할 수 없다"*)가 Flow Y(2026-08-14)로 소멸했고,
M6 폴링 데몬 확장은 pull 만 할 수 있어 scp 토폴로지에서 죽는다 → 원전 방식으로 되돌린다.
대조표: `reports/19-m5-version-judgments.md` §1.

우리 매체는 **durable `task/<task_id>`** 다 (§8.4: 마스터의 쓰기 표면 = attempt/*·task/*,
매니페스트는 마스터 소관). 등록 시 매니페스트를 durable 에 commit·push 하고, 파견은
워커에게 fetch + `git show` 로 **자기 클론에서 꺼내게** 한다 — scp 0, 이력은 git 에 영구.

[중요] 검증은 blob sha 로 한다: publish 가 만든 blob 의 sha 를 워커가 materialize 후
`git hash-object` 로 되찍어 대조한다 — scp 시절의 sha256 되읽기와 같은 자리, 같은 이유.
[중요] `add -f` — `.ax/` 가 gitignore/exclude 대상이라 -f 없이는 스테이징이 안 된다
(원전이 실 저장소에서 물린 함정, 2026-06-14 — 소 2.3.2 에서 이식된 그 교훈).
[주의] 부활 조건 (판정 기록): 히스토리에 남는 `.ax/tasks/*.md` 가 사람의 작업(SourceTree
가독성 등)을 실제로 방해한다고 사용자가 판단하면 scp(`runner.deliver_manifest`)로 복귀 —
그 함수는 그래서 지우지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import branch_names
from .attempt import WRITE_REMOTE, AttemptError, GitError, _git
from .runner import DispatchError

MANIFEST_REL_FMT = ".ax/tasks/{task_id}/context.md"
# 워커 쪽 임시 ref — 브랜치를 만들지 않고 fetch 결과만 담는다
_CARRY_REF_FMT = "refs/ax/carry/{task_id}"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class CarryError(Exception):
    pass


def manifest_rel(task_id: str) -> str:
    return MANIFEST_REL_FMT.format(task_id=task_id)


@dataclass
class Published:
    task_id: str = ""
    durable: str = ""
    head: str = ""               # durable 의 새 tip (스킵이면 기존 tip)
    blob: str = ""               # [중요] 매니페스트 blob sha — materialize 대조의 기준
    created: bool = False        # durable 브랜치를 이번에 만들었나
    skipped: str = ""            # 커밋하지 않은 사유 (내용 동일 등 — 오류 아님)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.blob) and not self.error


def _remote_tip(repo: Path, remote: str, branch: str) -> str:
    out = _git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
    for ln in out.splitlines():
        parts = ln.split()
        if parts:
            return parts[0]
    return ""


def publish(paths, work_id: str, task_id: str, body: str, *, base_commit: str,
            remote: str = WRITE_REMOTE, logf=None) -> Published:
    """매니페스트를 조각 durable `task/<work_id>/<task_id>` 에 commit·push 한다.

    [중요] `work_id` 가 앞에 붙은 것은 `#319`(계층형) 때문이다 — 조각은 작업 브랜치에서
    갈라지고, `base_commit` 은 그 **작업 브랜치 tip** 이다(옛 값: 트윈 커밋).

    멱등이다: durable tip 에 같은 내용이 이미 있으면 커밋 없이 그 blob 을 돌려준다 —
    파견 루프가 매번 불러도 refresh 로 내용이 바뀐 때만 커밋이 생긴다.
    """
    log = logf or (lambda m: None)
    p = Published(task_id=task_id)
    try:
        p.durable = branch_names.durable_branch(work_id, task_id)
    except branch_names.BranchNameError as e:
        p.error = str(e)
        return p
    if not (body or "").strip():
        p.error = "매니페스트 본문이 비었다 — 빈 것을 실어 보내지 않는다"
        return p

    repo = Path(paths.repo)
    rel = manifest_rel(task_id)
    wt_path = Path(paths.root) / f"ax-carry-{task_id}"
    try:
        tip = _remote_tip(repo, remote, p.durable)
        if tip:
            # 원격 tip 위에 얹는다 — 로컬에 그 커밋이 있어야 worktree 를 세울 수 있다
            _git(repo, "fetch", remote, f"+refs/heads/{p.durable}:refs/ax/carry-base/{task_id}")
            base = tip
        else:
            base = (base_commit or "").strip()
            if not base:
                p.error = ("기준 커밋이 비었고 durable 도 없다 — 어디에 얹을지 모른 채 "
                           "커밋하지 않는다")
                return p
            p.created = True

        _git(repo, "worktree", "add", "--detach", "--force", str(wt_path), base)
        try:
            f = wt_path / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body, encoding="utf-8")
            _git(wt_path, "add", "-f", rel)
            if not _git(wt_path, "status", "--porcelain").strip():
                p.skipped = "내용이 durable tip 과 같다 — 커밋 없음"
                p.head = base
            else:
                # 원전 커밋 메시지 그대로 (cluster_coordinator.py:157)
                _git(wt_path, "commit", "-q", "-m",
                     f"skeleton context manifest for {task_id}")
                p.head = _git(wt_path, "rev-parse", "HEAD")
                _git(wt_path, "push", remote, f"HEAD:refs/heads/{p.durable}")
            p.blob = _git(wt_path, "rev-parse", f"HEAD:{rel}")
        finally:
            _git(repo, "worktree", "remove", "--force", str(wt_path))
    except (GitError, AttemptError, OSError) as e:
        p.error = f"{type(e).__name__}: {e}"
        return p
    log(f"[carry] {task_id} → {p.durable} "
        + (f"커밋 {p.head[:8]}" if not p.skipped else p.skipped)
        + (" (브랜치 신설)" if p.created else ""))
    return p


def materialize_command(facts, work_id: str, task_id: str) -> str:
    """워커에서 도는 한 줄 — fetch → `git show` 로 자기 클론에서 매니페스트를 꺼내
    `./.ax/work/<task>/manifest.md` 에 놓고, **blob sha 를 마지막 줄로 찍는다.**

    [중요] 경로·소비 형식은 scp 시절과 동일하다 — 워커 프롬프트(`Read ./{work}/{task}/…`)를
    안 바꾼다. 바뀌는 것은 **운송 수단**뿐이다.
    [주의] sha 만 stdout 을 건넌다(ASCII) — CP949 콘솔 함정이 성립하지 않는다. 본문 바이트는
    git → 로컬 리다이렉트로만 흐른다.
    """
    from ..client import bundle
    durable = branch_names.durable_branch(work_id, task_id)
    ref = _CARRY_REF_FMT.format(task_id=task_id)
    rel = manifest_rel(task_id)
    dst_dir = f"{bundle.WORK_REL}/{task_id}"
    dst = f"{dst_dir}/manifest.md"
    if facts.windows:
        dd = dst_dir.replace("/", "\\")
        d = dst.replace("/", "\\")
        return (f'cd /d "{facts.path}" && '
                f'git fetch origin "+refs/heads/{durable}:{ref}" && '
                f'(if not exist "{dd}" mkdir "{dd}") && '
                f'git --no-pager show "{ref}:{rel}" > "{d}" && '
                f'git hash-object "{d}"')
    return (f'cd "{facts.path}" && '
            f'git fetch origin "+refs/heads/{durable}:{ref}" && '
            f'mkdir -p "{dst_dir}" && '
            f'git --no-pager show "{ref}:{rel}" > "{dst}" && '
            f'git hash-object "{dst}"')


def materialize(facts, work_id: str, task_id: str, *, expect_blob: str, runner_=None,
                timeout: int = 120) -> str:
    """워커 클론에 매니페스트를 실체화하고 **blob sha 를 대조한다.** 불일치·실패 = 예외.

    반환: 확인된 blob sha. `runner_(facts, cmd, timeout) -> (rc, stdout)` 주입은 테스트 자리.
    """
    if not (expect_blob or "").strip():
        raise CarryError(f"{task_id}: 기대 blob 이 비었다 — publish 결과 없이 실체화하지 않는다")
    cmd = materialize_command(facts, work_id, task_id)
    if runner_ is not None:
        rc, out = runner_(facts, cmd, timeout)
    else:
        from ..client import bundle
        rc, out = bundle._ssh(facts.host, facts.user, cmd, timeout=timeout)
    if rc != 0:
        raise CarryError(f"{facts.host}: 매니페스트 실체화 실패 (rc={rc}) — "
                         f"{(out or '').strip()[-200:]}")
    # [주의] fetch 진행 메시지가 stderr 로 섞여 온다 (ssh 는 두 스트림을 합친다) —
    #    마지막 줄이 아니라 **뒤에서부터 sha 모양인 줄**을 찾는다.
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    got = next((ln for ln in reversed(lines) if _SHA_RE.fullmatch(ln)), "")
    if not got:
        raise CarryError(f"{facts.host}: blob sha 를 못 읽었다 — 꼬리: "
                         f"{' | '.join(lines[-3:])[:160]!r}")
    if got != expect_blob.strip():
        raise CarryError(f"{facts.host}: [중요] 매니페스트가 다르다 — "
                         f"기대 {expect_blob[:12]} 실측 {got[:12]} (전송을 신뢰하지 않는다)")
    return got


def deliverer(paths, work_id: str, *, logf=None):
    """파견 루프용 배달 함수 — `deliver(facts, task_id, text)` 모양 (scp 자리의 대체).

    [중요] `work_id` 는 **만들 때 묶는다** (`#319`) — 한 번의 파견은 한 work 안이고, 배달
    함수의 인자 모양(`facts, task_id, text`)은 두 호출자가 공유하므로 안 바꾼다.

    refresh 로 본문이 바뀌었으면 publish 가 새 커밋을 만들고(멱등), 실체화가 blob 대조까지
    한다. 실패는 예외로 — **조용한 scp 폴백은 없다** (있으면 실전이 어느 경로로 돌았는지
    아무도 모르게 된다).
    """
    def _deliver(facts, task_id: str, text: str, *, runner_=None) -> str:
        from . import twin_base
        base = ""
        try:
            base = twin_base.resolve(paths, work_id).commit or ""
        except Exception:                                # noqa: BLE001
            base = ""
        if not base:
            # [중요] `#319` — 작업 브랜치가 없으면 조각을 어디에 얹을지 모른다. 종전에는
            #    트윈 커밋으로 조용히 접혔고, 그래서 조각들이 각자 main 에서 났다.
            raise DispatchError(
                f"{task_id}: 작업 브랜치 tip 을 못 구했다 — 조각을 얹을 자리가 없다. "
                f"`task/{work_id}/base` 가 원격에 있는지 확인할 것 (`#319`)")
        pub = publish(paths, work_id, task_id, text, base_commit=base, logf=logf)
        if not pub.ok:
            raise DispatchError(f"{task_id}: git-carried publish 실패 — {pub.error}")
        return materialize(facts, work_id, task_id, expect_blob=pub.blob, runner_=runner_)
    return _deliver
