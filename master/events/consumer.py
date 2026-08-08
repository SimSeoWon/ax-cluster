"""스풀 소비자 — 푸시 이벤트를 받아 트윈을 따라잡힌다 (PLAN §5.4.5-a, §5.2-E).

    작업장 push → Gitea 훅 → ~/ax-spool/incoming → **여기** → 미러 갱신 · 재색인

🔴 **폴링 데몬이 아니다** (§5.4). 한 번 돌고 끝나는 명령이고, `systemd` **path 유닛**(inotify)이
스풀에 파일이 생길 때 깨운다. 30초마다 깨어나 아무것도 안 하는 프로세스를 두지 않는다.

🔴 **`gitea` 그룹이 필요하다.** bare 저장소(`/var/lib/gitea/...`)를 읽어야 `git fetch` 가 된다.
실측(2026-08-08): 그룹이 없으면 git 이 *"does not appear to be a git repository"* 라고 하는데
**실제 원인은 권한**이다 — 메시지가 원인을 감춘다. 유닛에 `SupplementaryGroups=gitea` 를 둔다.

---

## ⚠️ 지금 이 소비자가 **하지 못하는 것** — 감추지 않고 적는다

색인 대상은 **컨텍스트 MD**(`<Project>/context/`)이지 소스가 아니다(§5.2-E).
그리고 그 MD 는 **소스 저장소에 없다** — 마스터 로컬이고, AgentTest 의 합성기가 만든
`--export-state` 산출물을 들여온 것이다(`config.yaml: source: infra_state_*.zip`).

**그 합성기(`watcher/` 21,171줄 중 컨텍스트·온톨로지 합성부)는 아직 이식되지 않았다.**

따라서 지금은:

| 푸시가 바꾸는 것 | 소비자가 하는 일 |
|---|---|
| `repo/` 의 소스 | ✅ 미러를 fast-forward · 변경 파일 목록 산출 · 워터마크 전진 |
| `context/` 의 MD | ❌ **아무것도 안 바뀐다** — 합성기가 없다 |

그래서 **소스만 바뀐 푸시는 재색인을 건너뛴다.** 40초를 태워 같은 961건을 다시 넣을 이유가
없기 때문이다. 대신 `skipped` 사유를 결과에 남긴다 — "색인이 최신" 과 "색인기가 반쪽" 은
다른 상태이고, 조용히 같아 보이면 안 된다.

컨텍스트가 **실제로** 바뀌면(재수출·수동 편집·나중에 합성기가 이식되면) 다이제스트가 달라져
자동으로 재색인한다. 그때 코드를 고칠 필요가 없도록 지금 그렇게 짜 둔다.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..context_search.paths import ProjectPaths, resolve
from ..projects.config import ConfigError, Registry, normalize_project_id
from .spool import Batch, Event, Spool

DIGEST_FILE = "context_digest.json"
GIT_TIMEOUT = 300


@dataclass
class ProjectResult:
    project_id: str
    project: str = ""
    from_commit: str = ""
    to_commit: str = ""
    source_changed: int = 0
    reindexed: bool = False
    docs: int = 0
    skipped: str = ""          # 재색인을 건너뛴 사유. 비어 있으면 안 건너뛴 것
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def line(self) -> str:
        if self.error:
            return f"  ❌ {self.project_id}: {self.error}"
        bits = [f"{self.from_commit[:8] or '?'}→{self.to_commit[:8] or '?'}"]
        if self.source_changed:
            bits.append(f"소스 {self.source_changed}건")
        if self.reindexed:
            bits.append(f"재색인 {self.docs}건")
        elif self.skipped:
            bits.append(f"재색인 건너뜀 ({self.skipped})")
        return f"  ✅ {self.project_id}: " + " · ".join(bits)


@dataclass
class RunResult:
    results: list[ProjectResult] = field(default_factory=list)
    claimed: int = 0
    coalesced: int = 0
    rejected: int = 0
    blocked_recursion: int = 0
    note: str = ""

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def summary(self) -> str:
        if self.note:
            return self.note
        return (f"이벤트 {self.claimed}건 → 프로젝트 {len(self.results)}개 "
                f"(합침 {self.coalesced}, 거부 {self.rejected})")


def _has_gitea_group() -> bool:
    """이 프로세스가 이미 `gitea` 그룹을 갖고 있나.

    서비스로 돌 때는 `SupplementaryGroups=gitea` 라 갖고 있고, 사람이 셸에서 돌릴 때는
    **세션이 그룹 추가 이전에 시작됐으면 없다**(실측 2026-08-08: DB 에는 있는데 프로세스에는
    없었다). 있으면 감싸지 않는다 — `sg` 는 호출마다 저널에 그룹 전환 두 줄을 남겨
    **정작 읽어야 할 소비자 출력을 덮는다.**
    """
    import grp
    try:
        return grp.getgrnam("gitea").gr_gid in os.getgroups()
    except KeyError:
        return False


def _git(repo: Path, *args: str, group: bool | None = None) -> tuple[int, str]:
    """git 실행. 필요할 때만 `sg gitea` 로 감싼다."""
    cmd = ["git", "-C", str(repo), *args]
    need = (not _has_gitea_group()) if group is None else group
    if need:
        inner = " ".join(_shquote(c) for c in cmd)
        cmd = ["sg", "gitea", "-c", inner]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=GIT_TIMEOUT)
    return p.returncode, (p.stdout + p.stderr).strip()


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def context_digest(paths: ProjectPaths) -> str:
    """`context/` 의 상태 지문. **내용이 바뀌었는지만** 알면 되므로 크기·mtime 으로 충분하다.

    1,055개 파일을 매번 해싱하는 것보다 싸고, 놓치는 경우(같은 크기·같은 mtime 으로 내용만
    다른 편집)는 실질적으로 없다. 정확도가 더 필요해지면 여기만 바꾸면 된다.
    """
    ctx = paths.context
    if not ctx.is_dir():
        return ""
    h = hashlib.sha256()
    for p in sorted(ctx.rglob("*.md")):
        try:
            st = p.stat()
        except OSError:
            continue
        h.update(f"{p.relative_to(ctx).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n"
                 .encode("utf-8"))
    return h.hexdigest()[:16]


def _digest_path(paths: ProjectPaths) -> Path:
    return paths.root / DIGEST_FILE


def read_digest(paths: ProjectPaths) -> str:
    try:
        return json.loads(_digest_path(paths).read_text(encoding="utf-8"))["digest"]
    except Exception:                                  # noqa: BLE001
        return ""


def write_digest(paths: ProjectPaths, digest: str) -> None:
    p = _digest_path(paths)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"digest": digest}), encoding="utf-8")
    tmp.replace(p)


def _update_watermark(paths: ProjectPaths, commit: str) -> None:
    """`config.yaml` 의 `index.last_indexed_commit` 을 전진시킨다.

    YAML 을 통째로 다시 쓰지 않고 **그 줄만** 바꾼다 — 사용자가 손으로 넣은 주석·순서를
    라이브러리가 재직렬화하면서 뭉개는 것을 막는다.
    """
    import re

    cfg = paths.config
    text = cfg.read_text(encoding="utf-8")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    text2 = re.sub(r"(^\s*last_indexed_commit:\s*).*$", rf"\g<1>{commit}",
                   text, count=1, flags=re.MULTILINE)
    text2 = re.sub(r"(^\s*last_indexed_at:\s*).*$", rf"\g<1>'{stamp}'",
                   text2, count=1, flags=re.MULTILINE)
    if text2 == text:
        return
    tmp = cfg.with_suffix(".tmp")
    tmp.write_text(text2, encoding="utf-8")
    tmp.replace(cfg)


def process_event(ev: Event, *, registry: Registry | None = None,
                  reindex=None, git=None) -> ProjectResult:
    """이벤트 하나(=프로젝트 하나)를 처리한다."""
    r = ProjectResult(project_id=ev.project_id)
    reg = registry or Registry.load()
    run = git or _git

    try:
        name = reg.find_by_project_id(ev.project_id)
        if not name:
            r.error = f"등록되지 않은 project_id (§5.5.4-④)"
            return r
        paths = resolve(name, registry=reg)
        r.project = name
    except ConfigError as e:
        r.error = str(e)
        return r

    if not paths.repo.is_dir():
        r.error = f"소스 클론이 없다: {paths.repo}"
        return r

    rc, out = run(paths.repo, "rev-parse", "HEAD")
    r.from_commit = out.strip() if rc == 0 else ""

    rc, out = run(paths.repo, "fetch", "--prune")
    if rc != 0:
        r.error = f"fetch 실패: {out[:200]}"
        return r

    # 🔴 `reset --hard` 가 아니라 `merge --ff-only` 다. 마스터는 이 클론에 커밋하지 않으므로
    #    항상 fast-forward 여야 하고, **아니라면 그건 알아야 할 사고**다. 조용히 덮어쓰지 않는다.
    rc, out = run(paths.repo, "merge", "--ff-only", "FETCH_HEAD")
    if rc != 0 and "Already up to date" not in out:
        r.error = f"fast-forward 실패 — 미러가 갈라졌다: {out[:200]}"
        return r

    rc, out = run(paths.repo, "rev-parse", "HEAD")
    r.to_commit = out.strip() if rc == 0 else ""

    if r.from_commit and r.to_commit and r.from_commit != r.to_commit:
        rc, out = run(paths.repo, "diff", "--name-only",
                      r.from_commit, r.to_commit, "--", "Source")
        if rc == 0:
            r.source_changed = len([x for x in out.splitlines() if x.strip()])

    # ── 재색인은 컨텍스트가 실제로 바뀐 경우에만 ──────────────
    now_digest = context_digest(paths)
    if not now_digest:
        r.skipped = "context/ 가 없다"
    elif now_digest == read_digest(paths):
        # 🔴 여기가 §문서에 적은 그 지점이다 — 소스는 바뀌었는데 MD 는 안 바뀐다.
        r.skipped = ("컨텍스트 MD 변화 없음"
                     + (" — MD 합성기 미이식이라 소스 변경이 색인에 반영되지 않는다"
                        if r.source_changed else ""))
    else:
        do = reindex or _default_reindex
        try:
            r.docs = do(paths)
            r.reindexed = True
            write_digest(paths, now_digest)
        except Exception as e:                         # noqa: BLE001
            r.error = f"재색인 실패: {type(e).__name__}: {e}"
            return r

    if r.to_commit:
        _update_watermark(paths, r.to_commit)
    return r


def _default_reindex(paths: ProjectPaths) -> int:
    from ..context_search.rebuild import rebuild_all
    return rebuild_all(paths).vector_docs


def consume_once(spool: Spool | None = None, *, registry: Registry | None = None,
                 reindex=None, git=None, progress=None) -> RunResult:
    """스풀을 한 번 비운다. **다른 소비자가 돌고 있으면 즉시 물러난다** (flock)."""
    sp = spool or Spool()
    res = RunResult()
    if not sp.acquire():
        res.note = "다른 소비자가 돌고 있다 — 물러난다"
        return res

    reg = registry or Registry.load()

    def known(pid: str) -> bool:
        return bool(reg.find_by_project_id(pid))

    batch: Batch = sp.claim_batch(is_registered=known)
    res.coalesced = batch.coalesced_away
    res.rejected = batch.rejected
    # 재귀 차단은 **스풀이 claim 단계에서** 이미 한다 — 여기서 다시 세지 않고 그 수를 받는다.
    res.blocked_recursion = batch.skipped_index_output
    res.claimed = (len(batch.events) + res.coalesced + res.rejected
                   + res.blocked_recursion)

    for ev in batch.events:
        if progress:
            progress(f"{ev.project_id} {ev.old[:8]}→{ev.new[:8]}")
        res.results.append(process_event(ev, registry=reg, reindex=reindex, git=git))

    sp.done(batch)
    return res


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="이벤트 스풀 소비 (한 번 돌고 끝난다)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    r = consume_once(progress=None if args.quiet else (lambda m: print(f"  · {m}")))
    print(r.summary())
    for x in r.results:
        print(x.line())
    if r.blocked_recursion:
        print(f"  (색인기 자신의 커밋 {r.blocked_recursion}건 차단 — 재귀 방지)")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
