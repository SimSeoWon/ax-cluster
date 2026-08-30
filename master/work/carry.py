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


def _guard_or_reason(paths) -> str:
    """쓰기 가드가 서 있나. 서 있으면 `""`, 아니면 **막을 사유**를 돌려준다 (`#329`).

    [중요] **「낡았다」는 막지 않는다** — 그건 우리 가드가 맞고 지금 막고 있다는 뜻이다.
    막는 것은 **없거나 우리 것이 아닐 때**뿐이다. 그 구분이 `#329` 의 요지다.
    [주의] 확인 자체가 실패하면(예외) **막는다** — 미확인은 통과가 아니다.
    """
    try:
        from .attempt import hook_status, STATE_MISSING, STATE_FOREIGN
        st = hook_status(paths)
    except Exception as e:                                   # noqa: BLE001
        return (f"[중요] 쓰기 가드를 확인하지 못했다 ({type(e).__name__}: {e}) — "
                f"미확인은 통과가 아니다. push 하지 않는다 (`#329`)")
    if st.get("state") in (STATE_MISSING, STATE_FOREIGN):
        return (f"[중요] 쓰기 가드가 서 있지 않다 — {st.get('reason')} "
                f"· 복구: `python -m master.work.attempt install-hook <프로젝트>` (`#125`·`#329`)")
    return ""


def _has_commit(repo, sha: str) -> bool:
    """이 저장소가 그 커밋 객체를 갖고 있나. [중요] **없으면 `worktree add` 가 죽는다.**"""
    if not (sha or "").strip():
        return False
    try:
        _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


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

    # [중요] **push 직전에 쓰기 가드를 확인한다** (`#329`, 사용자 결정 2026-08-28).
    #    여기가 마스터가 `gitea-write` 로 실제로 미는 자리다 — **가드가 필요한 바로 그 순간**에
    #    재는 것이 가장 강하다. 실측 2026-08-28: `git lfs install` 이 NS 클론의 훅을 덮어
    #    가드가 통째로 사라졌는데 **아무 표면도 그것을 말하지 않았다**(`#125` 가 막던 셋 —
    #    `task/*` 밖 push · main 이동 · 미병합 삭제 — 이 그동안 무방비였다).
    # [주의] **fail-closed 다 — 없으면 막는다.** 파이프라인이 멈추는 것이 무방비로 미는 것보다
    #    낫다. 사유가 `install-hook` 을 가리키므로 사람이 한 줄로 복구한다.
    guard = _guard_or_reason(paths)
    if guard:
        p.error = guard
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
            # [중요] **base 커밋도 fetch 한다** (`#341`, 실측 2026-08-30). durable 경로는 위에서
            #    fetch 하는데 이 갈래는 안 했다 — `#319` 로 base 브랜치가 도입될 때 durable 쪽만
            #    넣고 여기를 빠뜨렸다. **첫 조각은 durable 이 아직 없어 반드시 이리 온다.**
            #    미러에 그 커밋이 없으면 바로 아래 `worktree add` 가 죽는다:
            #        fatal: 잘못된 레퍼런스: 953587343eda…
            #    [주의] `twin_base.resolve()` 는 **bare 를 직접 읽어** exists=True 를 냈는데,
            #    carry 는 **미러의 로컬 객체**를 쓴다. 둘이 보는 곳이 달라서 「있다고 했는데
            #    없다」가 됐다 — 첫 실전 파견이 여기서 죽었다.
            if not _has_commit(repo, base):
                # [주의] **이미 로컬에 있으면 건드리지 않는다** — fetch 실패를 치명으로 보면
                #    원격이 없는 테스트·오프라인 경로가 죽는다. 없을 때만 가져온다.
                _base_br = branch_names.base_branch(work_id)
                try:
                    _git(repo, "fetch", remote,
                         f"+refs/heads/{_base_br}:refs/ax/carry-base/{task_id}")
                except GitError as e:
                    p.error = (f"기준 커밋 {base[:8]} 이 로컬에 없고 base 브랜치도 못 가져왔다 "
                               f"— {_base_br}: {str(e)[:160]}")
                    return p
                if not _has_commit(repo, base):
                    p.error = (f"base 브랜치를 가져왔는데도 기준 커밋 {base[:8]} 이 없다 "
                               f"— {_base_br} tip 과 어긋난다")
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
