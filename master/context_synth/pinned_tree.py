"""고정 SHA 의 읽기용 분리 worktree (`#825`).

상용 CLI(codex·agy·claude)는 파일을 읽는 에이전트다 — 소스를 프롬프트에 싣지 않고 이 트리를
작업 디렉터리로 준다. 원전 `master_orchestrator/common.py:418` `call_cli_llm(prompt, cwd=...)` 은
저장소 경로를 그대로 줬다. 여기는 더 좁다 — **저장소 밖 임시 디렉터리의 detached worktree** 라
판정 중에 `main` 이 움직여도 읽는 내용이 SHA 에 고정된다.

[주의] 쓰기를 막지는 못한다(agy 는 강제 수단이 없다). 판정 근거는 본 저장소의 `git show sha:file`
과 대조하므로 결과를 오염시키지 못하지만, 쓰기는 **로그로 드러낸다** — 나올 때 `status --porcelain`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


def _log(msg: str, logf=None) -> None:
    if logf is not None:
        try:
            logf(msg)
            return
        except Exception:                                    # noqa: BLE001
            pass
    print(f"[pinned_tree] {msg}", file=sys.stderr, flush=True)


def _git(*args, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def check_writes(tree, *, logf=None) -> list[str]:
    """트리의 변경(`status --porcelain` 줄)을 돌려준다. 있으면 경고 한 줄을 남긴다.

    [주의] 상태를 못 읽으면 그것도 경고로 남기고 `["?? (status 실패)"]` 를 돌려준다 — 「깨끗하다」로
    접지 않는다.
    """
    try:
        p = _git("-C", str(tree), "status", "--porcelain")
    except (OSError, subprocess.SubprocessError) as e:
        _log(f"[경고] 고정 트리 상태 확인 실패 {tree} — {type(e).__name__}", logf)
        return ["?? (status 실패)"]
    if p.returncode:
        _log(f"[경고] 고정 트리 상태 확인 실패 {tree} — rc={p.returncode}", logf)
        return ["?? (status 실패)"]
    dirty = [x for x in p.stdout.splitlines() if x.strip()]
    if dirty:
        _log(f"[경고] 고정 트리에 쓰기 {len(dirty)}건 {tree} — 판정 근거는 본 저장소와 대조한다", logf)
    return dirty


@contextmanager
def pinned_worktree(repo, sha: str, *, logf=None, writes: list | None = None):
    """`repo` 의 `sha` 를 저장소 밖 임시 디렉터리에 detached worktree 로 만들어 그 `Path` 를 준다.

    나올 때 **항상** `worktree remove --force` + `worktree prune` 을 하고 임시 디렉터리를 지운다.
    그 직전에 `check_writes` 로 쓰기를 검사하고, `writes` 리스트를 주면 그 줄들을 덧붙인다.
    생성 실패는 `RuntimeError` 다.
    """
    base = Path(tempfile.mkdtemp(prefix="ax-pinned-"))
    tree = base / "tree"
    try:
        p = _git("-C", str(repo), "worktree", "add", "--detach", str(tree), sha)
    except (OSError, subprocess.SubprocessError) as e:
        shutil.rmtree(base, ignore_errors=True)
        _log(f"고정 트리 생성 실패 {sha[:12]} — {type(e).__name__}", logf)
        raise RuntimeError("고정 worktree 를 만들지 못했다") from e
    if p.returncode:
        shutil.rmtree(base, ignore_errors=True)
        _log(f"고정 트리 생성 실패 {sha[:12]} — rc={p.returncode}: "
             f"{(p.stderr or '').strip()[:200]}", logf)
        raise RuntimeError("고정 worktree 를 만들지 못했다")
    _log(f"고정 트리 생성 {tree} @ {sha[:12]}", logf)
    try:
        yield tree
    finally:
        dirty = check_writes(tree, logf=logf)
        if writes is not None:
            writes.extend(dirty)
        try:
            r = _git("-C", str(repo), "worktree", "remove", "--force", str(tree))
            if r.returncode:
                _log(f"[경고] 고정 트리 제거 실패 {tree} — rc={r.returncode}: "
                     f"{(r.stderr or '').strip()[:200]}", logf)
        except (OSError, subprocess.SubprocessError) as e:
            _log(f"[경고] 고정 트리 정리 실패 {tree} — {type(e).__name__}", logf)
        # 제거가 실패했어도 디렉터리를 지운 뒤 prune 이 남은 등록을 걷는다
        shutil.rmtree(base, ignore_errors=True)
        try:
            _git("-C", str(repo), "worktree", "prune")
        except (OSError, subprocess.SubprocessError) as e:
            _log(f"[경고] worktree prune 실패 — {type(e).__name__}", logf)
        _log(f"고정 트리 제거 {tree}", logf)
