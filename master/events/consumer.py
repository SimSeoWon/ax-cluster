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
    # ── 트윈 성장 (중 1.1 · 중 1.2) ──
    graph_notes: list[str] = field(default_factory=list)
    synth_written: int = 0
    synth_lost: int = 0         # 🔴 문서가 안 생긴 그룹 수 = 그 커밋의 영구 유실
    synth_note: str = ""
    lost_groups: list[str] = field(default_factory=list)
    canary_write_failed: int = 0   # ⚠️ 카나리 기록 자체가 실패한 횟수 (조용히 넘기지 않는다)

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def summary(self) -> str:
        parts = [f"{self.project or self.project_id}"]
        if self.source_changed:
            parts.append(f"소스 {self.source_changed}")
        if self.graph_notes:
            parts.append("그래프 " + "·".join(self.graph_notes))
        if self.synth_note:
            parts.append(f"합성 {self.synth_written}" +
                         (f" 🔴유실 {self.synth_lost}" if self.synth_lost else ""))
        if self.reindexed:
            parts.append(f"색인 {self.docs}")
        if self.skipped:
            parts.append(f"건너뜀({self.skipped[:40]})")
        if self.error:
            parts.append(f"🔴 {self.error[:60]}")
        return " · ".join(parts)

    def line(self) -> str:
        if self.error:
            return f"  ❌ {self.project_id}: {self.error}"
        bits = [f"{self.from_commit[:8] or '?'}→{self.to_commit[:8] or '?'}"]
        if self.source_changed:
            bits.append(f"소스 {self.source_changed}건")
        if self.graph_notes:
            bits.append("그래프 " + "·".join(self.graph_notes))
        if self.synth_note:
            bits.append(f"합성 {self.synth_written}건"
                        + (f" 🔴유실 {self.synth_lost}" if self.synth_lost else ""))
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
    paused: str = ""          # 🔴 게이트가 멈췄으면 그 사유 (소 3.5.1)
    polled: int = 0           # 이벤트 0건일 때 상태 대조만 돌린 프로젝트 수
    poll_skipped: int = 0     # project_id 를 못 읽어 폴하지 못한 프로젝트 수
    deferred: int = 0         # 멈춰서 넘긴 이벤트 수 (유실 아님 — state-based 라 누적분이 다음에 잡힌다)

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


# 🔴 카나리 기록기는 `master/canary.py` 로 옮겼다 (소 3.5.6 · `#182`).
#    이유는 층이다 — `context_search/rebuild` 도 찍어야 하는데 그쪽이 `events` 를 부르면
#    **층 역전**이다. ⚠️ 이 이름으로 부르던 곳(테스트 포함)이 그대로 돌도록 재수출한다.
from ..canary import (  # noqa: E402,F401
    KIND_CONTEXT_MD_LOST, KIND_DOMAIN_INDEX_GAP, append_canary,
)


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


def _update_graphs(paths: ProjectPaths, changed: list[str], r: "ProjectResult") -> None:
    """관계 그래프 증분 (중 1.1). **LLM 0 이라 커밋 즉시 돈다.**

    실패해도 배치를 세우지 않는다 — 그래프는 `python -m master.graph build` 로 언제든
    풀 스캔 복구되는 파생 자산이다(`data-schema.md`). 다만 **사유는 남긴다.**
    """
    from ..graph import class_graph as cg, dependency as dep
    for label, fn in (("상속", cg.update_incremental), ("의존", dep.update_incremental)):
        try:
            st = fn(paths, changed)
            r.graph_notes.append(f"{label} {st.classes if label == '상속' else st.edges}")
        except Exception as e:                          # noqa: BLE001
            r.graph_notes.append(f"🔴 {label} 실패: {type(e).__name__}: {e}")


def _synthesize(paths: ProjectPaths, changed: list[str], r: "ProjectResult",
                *, synth_run=None) -> None:
    """컨텍스트 MD 합성 (중 1.2). **여기가 트윈을 자라게 한다.**

    🔴 실패·거부를 **삼키지 않는다.** 원본이 판별 기준을 적어 뒀다 — *"skip 후 워터마크가
    전진하느냐"*. 이 함수 뒤에서 워터마크가 전진하므로, 여기서 문서를 못 만들면 그 커밋의
    변경은 **영구 유실**이다. 그래서 사유를 `ProjectResult` 에 실어 로그로 내보낸다.
    """
    from ..context_synth import synth as cs
    fn = synth_run or cs.run
    try:
        st = fn(paths, changed=changed, commit=r.to_commit)
    except cs.SynthError as e:
        r.synth_note = f"합성 건너뜀: {e}"
        return
    except Exception as e:                              # noqa: BLE001
        r.synth_note = f"🔴 합성 실패: {type(e).__name__}: {e}"
        return
    r.synth_written = st.written
    r.synth_lost = st.lost
    r.synth_note = st.summary
    if st.lost:
        # 🔴 어느 그룹이 유실됐는지 남긴다 — 숫자만으로는 다시 찾을 수 없다.
        for g in st.results:
            if g.lost:
                r.lost_groups.append(f"{g.key}: {g.reason[:120]}")
                # 🔴 저널만으로는 반복을 못 본다 — 누적한다 (소 3.5.6).
                if not append_canary(paths, kind="context-md-lost",
                                     detail=f"{g.key}: {g.reason}", commit=r.to_commit):
                    r.canary_write_failed += 1


def process_event(ev: Event, *, registry: Registry | None = None,
                  reindex=None, git=None, synthesize: bool = True,
                  synth_run=None) -> ProjectResult:
    """이벤트 하나(=프로젝트 하나)를 처리한다.

    `synthesize=False` 로 합성을 끌 수 있다 — 노드가 죽었거나 품질을 재보는 중일 때.
    끄면 관계 그래프만 갱신되고 색인은 컨텍스트가 안 바뀌므로 돌지 않는다.
    """
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

    changed: list[str] = []
    if r.from_commit and r.to_commit and r.from_commit != r.to_commit:
        rc, out = run(paths.repo, "diff", "--name-only",
                      r.from_commit, r.to_commit, "--", "Source")
        if rc == 0:
            changed = [x.strip() for x in out.splitlines() if x.strip()]
            r.source_changed = len(changed)

    # ── 🔴 여기가 트윈이 자라는 지점이다 (중 1.1 · 중 1.2) ──────────
    #
    # 원본 `watch.py` 의 커밋 처리 순서를 그대로 따른다:
    #   ① 컨텍스트 MD 합성 (LLM) — `source_commit` 을 스탬프한다
    #   ② 관계 그래프 증분 (LLM 0) — 커밋 즉시
    #   ③ 색인 (아래) — ①이 문서를 바꿨을 때만 돈다
    #
    # 순서가 뒤집히면 안 된다: ①이 그래프를 **근거로** 읽으므로 그래프가 먼저면 좋지만,
    # 원본은 MD 를 먼저 만든다(그래야 `source_commit` 워터마크가 stale 판정의 기준이 된다).
    # 우리는 **그래프를 먼저** 돌린다 — LLM 0 이라 싸고, 합성이 최신 그래프를 근거로 쓴다.
    if changed:
        _update_graphs(paths, changed, r)
        if synthesize:
            _synthesize(paths, changed, r, synth_run=synth_run)

    # ── 재색인은 컨텍스트가 실제로 바뀐 경우에만 ──────────────
    now_digest = context_digest(paths)
    if not now_digest:
        r.skipped = "context/ 가 없다"
    elif now_digest == read_digest(paths):
        r.skipped = ("컨텍스트 MD 변화 없음"
                     + (" — 합성이 문서를 바꾸지 않았다 (게이트 거부/실패는 위 사유 참조)"
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

    # ── 🔴 색인 일시 중지 게이트 (소 3.5.1 — 원전 watch_state 이식) ──────
    #
    # 진행 중 분산 작업이 있으면 **fetch·색인을 하지 않는다.** 원전 근거: *"feature 브랜치
    # 작업 중 main 인덱싱 무의미 + 워커들과 git lock 경쟁 방지"*.
    #
    # ⚠️ 스풀은 **비운다**(claim 하고 처리를 건너뛴다). 남기면 `ax-indexer.path` 가 조건이 계속
    # 참이라 재트리거를 반복할 수 있다. 🔴 **비워도 유실이 아니다** — 이 소비자는 state-based 라
    # 이벤트는 깨우는 신호일 뿐이고, 미러가 뒤에 남으면 **다음 번에 누적분이 한꺼번에** 잡힌다.
    # 그 *"다음 번"* 을 만드는 것이 `ax-indexer.timer` 다(게이트만 두고 타이머를 안 두면 깨울
    # 주체가 없다 — 리포트 13 §19.3 이 상태 화면에서 똑같이 물린 자리).
    from .gate import check as _gate_check
    g = _gate_check(spool_root=sp.root if hasattr(sp, "root") else None)
    if g.paused:
        batch = sp.claim_batch(is_registered=known)
        res.paused = g.line()
        res.deferred = len(batch.events)
        res.claimed = res.deferred + batch.coalesced_away + batch.rejected + batch.skipped_index_output
        sp.done(batch)
        return res
    if g.degraded:
        res.note = (res.note + " · " if res.note else "") + g.degraded

    batch: Batch = sp.claim_batch(is_registered=known)
    res.coalesced = batch.coalesced_away
    res.rejected = batch.rejected
    # 🔴 **이벤트가 없어도 한 바퀴 돈다** (소 3.5.1 과 짝).
    #
    # 이 소비자는 state-based 다 — 무엇을 색인할지는 이벤트 내용이 아니라 **미러 HEAD 대조**가
    # 정한다. 그런데 원래 구현은 `for ev in batch.events` 안에서만 일해서, 이벤트가 0건이면
    # fetch 조차 하지 않았다. 그러면 게이트가 멈춘 동안 넘긴 분을 **따라잡을 방법이 없다**
    # (실측 2026-08-14: 게이트가 이벤트를 넘긴 뒤 재실행이 `이벤트 0건 → 프로젝트 0개` 였다 —
    # 내 *"유실 아님"* 주장이 그 자리에서 틀렸다).
    #
    # → 스풀이 비었으면 **등록된 프로젝트마다 합성 이벤트 한 건**으로 상태 대조를 돌린다.
    #   미러 fetch 는 로컬 bare 라 ms 단위이므로 매 기동에 돌려도 싸다. 이렇게 두면
    #   `ax-indexer.timer` 가 별도 모드 없이 그대로 따라잡기 역할을 한다.
    if not batch.events:
        # project_id 는 각 프로젝트의 `config.yaml` 이 SSOT 다(`track.project_id`).
        # ⚠️ 못 읽는 프로젝트는 조용히 건너뛰지 않고 **세어서** 결과에 남긴다.
        ids = []
        for _name in reg.names:
            try:
                pid = (reg.config_of(_name).project_id or "").strip()
            except Exception:                               # noqa: BLE001
                pid = ""
            if pid:
                ids.append(pid)
            else:
                res.poll_skipped += 1
        synth = [Event(project_id=pid) for pid in ids]
        res.polled = len(synth)
        for ev in synth:
            res.results.append(process_event(ev, registry=reg, reindex=reindex, git=git))
        sp.done(batch)
        return res
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
    if r.paused:
        # 🔴 종료코드 4 = 게이트에 걸림. **고장이 아니다** — 유닛이 `SuccessExitStatus=4` 로 받는다
        #    (상태 화면의 종료코드 3 과 같은 패턴: *"늘 빨간 유닛은 유닛이 아니다"*).
        print(f"{r.paused} · 이벤트 {r.deferred}건 넘김 (유실 아님 — 다음 회차에 누적분으로 잡힌다)")
        return 4
    print(r.summary())
    for x in r.results:
        print(x.line())
        # 🔴 유실은 목록으로 남긴다 — 워터마크가 이미 전진했으므로 다시 찾을 수 없다.
        for g in x.lost_groups:
            print(f"      🔴 {g}")
    if r.blocked_recursion:
        print(f"  (색인기 자신의 커밋 {r.blocked_recursion}건 차단 — 재귀 방지)")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
