"""스풀 소비자 — 푸시 이벤트를 받아 트윈을 따라잡힌다 (PLAN §5.4.5-a, §5.2-E).

    작업장 push → Gitea 훅 → ~/ax-spool/incoming → **여기** → 미러 갱신 · 재색인

[중요] **폴링 데몬이 아니다** (§5.4). 한 번 돌고 끝나는 명령이고, `systemd` **path 유닛**(inotify)이
스풀에 파일이 생길 때 깨운다. 30초마다 깨어나 아무것도 안 하는 프로세스를 두지 않는다.

[중요] **`gitea` 그룹이 필요하다.** bare 저장소(`/var/lib/gitea/...`)를 읽어야 `git fetch` 가 된다.
실측(2026-08-08): 그룹이 없으면 git 이 *"does not appear to be a git repository"* 라고 하는데
**실제 원인은 권한**이다 — 메시지가 원인을 감춘다. 유닛에 `SupplementaryGroups=gitea` 를 둔다.

---

## [주의] 지금 이 소비자가 **하지 못하는 것** — 감추지 않고 적는다

색인 대상은 **컨텍스트 MD**(`<Project>/context/`)이지 소스가 아니다(§5.2-E).
그리고 그 MD 는 **소스 저장소에 없다** — 마스터 로컬이고, AgentTest 의 합성기가 만든
`--export-state` 산출물을 들여온 것이다(`config.yaml: source: infra_state_*.zip`).

**그 합성기(`watcher/` 21,171줄 중 컨텍스트·온톨로지 합성부)는 아직 이식되지 않았다.**

따라서 지금은:

| 푸시가 바꾸는 것 | 소비자가 하는 일 |
|---|---|
| `repo/` 의 소스 | [완료] 미러를 fast-forward · 변경 파일 목록 산출 · 워터마크 전진 |
| `context/` 의 MD | [실패] **아무것도 안 바뀐다** — 합성기가 없다 |

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

from ..context_search.paths import SOURCE_SUBDIR, ProjectPaths, resolve
from ..projects.config import ConfigError, Registry, normalize_project_id
from .spool import Batch, Event, Spool

DIGEST_FILE = "context_digest.json"
# git 의 **빈 트리** 오브젝트 — 모든 저장소에서 같은 값이다. 첫 커밋의 diff 기준으로 쓴다
# (저장 해시가 없으면 「이력 처음부터 하나씩」이 기본 동작이므로 그 시작점이 필요하다).
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
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
    synth_lost: int = 0         # [중요] 문서가 안 생긴 그룹 수 = 그 커밋의 영구 유실
    synth_note: str = ""
    lost_groups: list[str] = field(default_factory=list)
    canary_write_failed: int = 0   # [주의] 카나리 기록 자체가 실패한 횟수 (조용히 넘기지 않는다)
    review_written: str = ""       # 자동 코드리뷰 리포트 경로 (소 3.3.5)
    review_note: str = ""          # 리뷰 스킵/실패 사유
    # ── 분석 커서 (`#278` — 커밋 하나씩) ──
    cursor_from: str = ""          # 이 회차가 시작한 커서 (config.yaml 의 analyzed_commit)
    cursor_note: str = ""          # 커서를 어디서 얻었는지 (이행: 워터마크 폴백)
    cursor_to: str = ""            # 이 회차가 적어 둔 커서. 비면 **한 커밋도 못 끝냈다**
    commits_total: int = 0         # 커서 → 현재 커밋 사이의 커밋 수
    commits_done: int = 0          # 문서까지 끝나 커서를 전진시킨 커밋 수
    commits_nonsource: int = 0     # 소스 밖 변경만 있어 합성 없이 전진시킨 커밋 수
    nonsource_notes: list = field(default_factory=list)
    halted: str = ""               # [중요] 걷기를 멈춘 사유. 멈췄으면 커서는 그 앞에 있다

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
        if self.review_written:
            parts.append("리뷰 1")
        if self.synth_note:
            parts.append(f"합성 {self.synth_written}" +
                         (f" [중요]유실 {self.synth_lost}" if self.synth_lost else ""))
        if self.reindexed:
            parts.append(f"색인 {self.docs}")
        if self.commits_total:
            parts.append(f"커밋 {self.commits_done}/{self.commits_total}"
                         + (f"(소스밖 {self.commits_nonsource})" if self.commits_nonsource else ""))
        if self.cursor_to:
            parts.append(f"커서 {self.cursor_to[:8]}")
        if self.cursor_note:
            parts.append(f"[주의] {self.cursor_note[:70]}")
        if self.halted:
            parts.append(f"[중요] 멈춤({self.halted[:60]})")
        if self.skipped:
            parts.append(f"건너뜀({self.skipped[:40]})")
        if self.error:
            parts.append(f"[중요] {self.error[:60]}")
        return " · ".join(parts)

    def line(self) -> str:
        if self.error:
            return f"  [실패] {self.project_id}: {self.error}"
        bits = [f"{self.from_commit[:8] or '?'}→{self.to_commit[:8] or '?'}"]
        if self.source_changed:
            bits.append(f"소스 {self.source_changed}건")
        if self.graph_notes:
            bits.append("그래프 " + "·".join(self.graph_notes))
        if self.synth_note:
            bits.append(f"합성 {self.synth_written}건"
                        + (f" [중요]유실 {self.synth_lost}" if self.synth_lost else ""))
        if self.reindexed:
            bits.append(f"재색인 {self.docs}건")
        elif self.skipped:
            bits.append(f"재색인 건너뜀 ({self.skipped})")
        return f"  [완료] {self.project_id}: " + " · ".join(bits)


@dataclass
class RunResult:
    results: list[ProjectResult] = field(default_factory=list)
    claimed: int = 0
    coalesced: int = 0
    rejected: int = 0
    blocked_recursion: int = 0
    note: str = ""
    paused: str = ""          # [중요] 게이트가 멈췄으면 그 사유 (소 3.5.1)
    polled: int = 0           # 이벤트 0건일 때 상태 대조만 돌린 프로젝트 수
    # [중요] 마운트 밖이라 **의도적으로** 안 돈 프로젝트 (`#246` ③) — 고장과 설계를 가른다
    unmounted: list = field(default_factory=list)
    poll_skipped: int = 0     # project_id 를 못 읽어 폴하지 못한 프로젝트 수
    deferred: int = 0         # 멈춰서 넘긴 이벤트 수 (유실 아님 — state-based 라 누적분이 다음에 잡힌다)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def summary(self) -> str:
        if self.note:
            return self.note
        _unm = (f" · 마운트 밖 {len(self.unmounted)}개 건너뜀"
                f"({', '.join(self.unmounted[:3])})" if self.unmounted else "")
        return (f"이벤트 {self.claimed}건 → 프로젝트 {len(self.results)}개{_unm} "
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


# [중요] 카나리 기록기는 `master/canary.py` 로 옮겼다 (소 3.5.6 · `#182`).
#    이유는 층이다 — `context_search/rebuild` 도 찍어야 하는데 그쪽이 `events` 를 부르면
#    **층 역전**이다. [주의] 이 이름으로 부르던 곳(테스트 포함)이 그대로 돌도록 재수출한다.
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


def has_context_md(paths: ProjectPaths) -> bool:
    """`context/` 에 MD 가 **한 건이라도** 있는가 (`#244`).

    [중요] `context_digest()` 와 다르다 — 그쪽은 *변화*를 보는 지문이라 **빈 디렉토리에도 해시를
    돌려준다.** 「색인할 것이 있는가」는 개수 문제다.
    [주의] 하위 디렉토리를 센다 — 실물이 `context/Source/…` 에 있어 `context/*.md` 로 세면 0 이다.
    """
    ctx = paths.context
    if not ctx.is_dir():
        return False
    return any(True for _ in ctx.rglob("*.md"))


def synth_complete(paths: ProjectPaths, *, git=None) -> tuple:
    """합성이 **끝났는가** — 문서 없는 그룹이 0 인가 (`#274`). `(끝났나, 사유)`.

    [중요] `has_context_md()`(=`#244`, 0건 가드)는 **부분 완료를 막지 못한다.** 실측 2026-08-22:
    NS 가 42그룹 중 13건인 상태에서 워터마크가 찍혀 온보딩이 *"전부 초기화됐다"* 고 거짓 보고했다.
    워터마크는 *"이 커밋까지 트윈에 반영됐다"* 는 주장이므로, 미합성 그룹이 남아 있으면 거짓이다.

    [주의] 판정 불가는 **막는 쪽**으로 접는다(fail-closed) — 세지 못하는데 전진시키면 그 커밋의
    변경이 영구 유실된다.

    [중요] **`git` 주입 자리를 통과시킨다** — `process_event` 가 받은 러너를 그대로 써야 한다.
    처음에 `cg` 를 직접 불러 실제 git 을 타서, 주입으로 도는 테스트가 깨졌다(저장소 관례를
    어긴 것이고, 그 관례가 있는 이유가 정확히 이것이다).
    """
    try:
        from ..context_synth import synth
        from ..graph import class_graph as cg
        groups = synth.group(cg.list_source_files(paths, git=git))
    except Exception as e:                                   # noqa: BLE001
        return False, f"그룹을 세지 못했다: {type(e).__name__}: {e}"
    if not groups:
        return False, "합성할 그룹이 없다"
    missing = sum(1 for k in groups if not synth.doc_path(paths, k).is_file())
    if missing:
        return False, f"{len(groups) - missing}/{len(groups)} 그룹 — {missing}개 미합성"
    return True, f"{len(groups)}/{len(groups)} 그룹"


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


def _note(r: "ProjectResult", why: str) -> None:
    """건너뜀 사유를 **쌓는다.** 대입하면 앞 단계의 판정을 지운다."""
    r.skipped = (r.skipped + " · " + why) if r.skipped else why


def _update_cursor(paths: ProjectPaths, commit: str) -> bool:
    """`config.yaml` 의 `index.analyzed_commit` 을 이 커밋으로 적는다 (`#280`).

    [중요] **커밋 하나가 끝날 때마다** 부른다. 원전(`watcher/watch.py`)은 루프가 끝난 뒤
    `save_state` 를 한 번 부르고, 그래서 중간에 죽으면 배치를 **처음부터** 다시 한다 —
    그 재실행이 LLM 비용이다(사용자 요구가 원전보다 엄격한 자리).

    [주의] **키가 없는 구 config 도 있다** — 그때는 `index:` 아래에 새로 넣는다. 조용히 아무
    것도 안 하면 커서가 영원히 비어 판정이 계속 「미확인」에 머문다.
    """
    import re

    cfg = paths.config
    text = cfg.read_text(encoding="utf-8")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    text2 = re.sub(r"(^\s*analyzed_commit:\s*).*$", rf"\g<1>{commit}",
                   text, count=1, flags=re.MULTILINE)
    if text2 != text:
        text2 = re.sub(r"(^\s*analyzed_at:\s*).*$", rf"\g<1>'{stamp}'",
                       text2, count=1, flags=re.MULTILINE)
    else:
        m = re.search(r"^index:[ \t]*$", text, flags=re.MULTILINE)
        if not m:
            return False                        # `index:` 절이 없다 — 호출자가 알아야 한다
        head, tail = text[:m.end()], text[m.end():]
        text2 = f"{head}\n  analyzed_commit: {commit}\n  analyzed_at: '{stamp}'{tail}"
    tmp = cfg.with_suffix(".tmp")
    tmp.write_text(text2, encoding="utf-8")
    tmp.replace(cfg)
    return True


def _commits_between(repo: Path, old: str, new: str, run) -> tuple:
    """`old..new` 커밋 해시를 **오래된 순**으로. 반환 `(목록, 오류사유)`.

    원전 `watcher/git_ops.get_commits_between` 과 같은 계약이다(그쪽도 `reverse()` 한다).
    [주의] 실패를 빈 목록으로 접지 않는다 — 「걸을 커밋이 없다」와 구분되지 않는다.
    """
    rng = f"{old}..{new}" if old else new
    rc, out = run(repo, "log", "--format=%H", rng)
    if rc != 0:
        return [], f"git log {rng[:20]} 실패 (rc={rc}): {out[:200]}"
    hs = [x.strip() for x in out.splitlines() if x.strip()]
    hs.reverse()
    return hs, ""


def _source_only(files: list[str]) -> list[str]:
    """소스 디렉토리 밖은 버린다 (사용자 지시 2026-08-23 · §5.2-E).

    [중요] **판정식을 새로 만들지 않는다** — `class_graph.list_source_files` 와 같은 두 겹
    (`Source/` 접두 + 파서 확장자)이다. `config.yaml` 의 `include` 글롭으로 따로 짜면 매처가
    둘이 되고, 그 둘은 언젠가 갈라진다(원전 대조에서 반복 확인된 부류).
    """
    from ..context_search.paths import SOURCE_SUBDIR
    from ..graph import parse

    prefix = f"{SOURCE_SUBDIR}/"
    return [f for f in files
            if f.startswith(prefix) and Path(f).suffix.lower() in parse.PARSE_EXTS]


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
            r.graph_notes.append(f"[중요] {label} 실패: {type(e).__name__}: {e}")


def _synthesize(paths: ProjectPaths, changed: list[str], r: "ProjectResult",
                *, commit: str = "", synth_run=None) -> None:
    """컨텍스트 MD 합성 (중 1.2). **여기가 트윈을 자라게 한다.**

    [중요] 실패·거부를 **삼키지 않는다.** 원본이 판별 기준을 적어 뒀다 — *"skip 후 워터마크가
    전진하느냐"*. 이 함수 뒤에서 워터마크가 전진하므로, 여기서 문서를 못 만들면 그 커밋의
    변경은 **영구 유실**이다. 그래서 사유를 `ProjectResult` 에 실어 로그로 내보낸다.
    """
    from ..context_synth import synth as cs
    fn = synth_run or cs.run
    try:
        # [중요] 스탬프는 **지금 걷고 있는 커밋**이다 — `to_commit`(HEAD)을 넘기면 아직
        #    분석하지 않은 커밋을 근거로 적는 것이고, 그것이 거짓 신선도다(`#280`).
        #    실측: 회귀 칸 [12-4] 가 이 자리를 잡았다.
        st = fn(paths, changed=changed, commit=(commit or r.to_commit))
    except cs.SynthError as e:
        r.synth_note = f"합성 건너뜀: {e}"
        return
    except Exception as e:                              # noqa: BLE001
        r.synth_note = f"[중요] 합성 실패: {type(e).__name__}: {e}"
        return
    r.synth_written = st.written
    r.synth_lost = st.lost
    r.synth_note = st.summary
    if st.lost:
        # [중요] 어느 그룹이 유실됐는지 남긴다 — 숫자만으로는 다시 찾을 수 없다.
        for g in st.results:
            if g.lost:
                r.lost_groups.append(f"{g.key}: {g.reason[:120]}")
                # [중요] 저널만으로는 반복을 못 본다 — 누적한다 (소 3.5.6).
                if not append_canary(paths, kind="context-md-lost",
                                     detail=f"{g.key}: {g.reason}", commit=r.to_commit):
                    r.canary_write_failed += 1


def _auto_review(paths: ProjectPaths, changed: list[str], r: "ProjectResult",
                 *, commit: str = "", review_run=None) -> None:
    """자동 코드리뷰 생산자 (소 3.3.5 · `#205`) — 유저 커밋의 변경분을 리뷰해 되먹임의
    원료(`reviews/<작성자>/`)를 만든다.

    [중요] fail-soft 지만 조용하지 않다 — 이 함수 뒤에서 워터마크가 전진하므로 여기서 리뷰를
    못 만들면 **그 커밋의 리뷰는 다시 생기지 않는다**. 합성 유실과 같은 기준으로 카나리에
    누적한다(kind=review-lost). 스킵(trivial·작성자 제외)은 유실이 아니라 설계다 — 카나리 없음.
    """
    from ..context_synth import review_gen as rg
    fn = review_run or rg.review_commit
    try:
        rv = fn(paths, (commit or r.to_commit), changed)
    except Exception as e:                              # noqa: BLE001
        r.review_note = f"[중요] 리뷰 생성 예외: {type(e).__name__}: {e}"
        if not append_canary(paths, kind="review-lost",
                             detail=r.review_note, commit=r.to_commit):
            r.canary_write_failed += 1
        return
    if rv.written:
        r.review_written = rv.written
        if not getattr(rv, "format_ok", True):
            # [중요] 저장은 됐지만 소비자는 0건으로 읽는다 — 되먹임 기준 유실이다
            r.review_note = "[중요] 리뷰 형식 위반 — 소비자 파서 기준 이슈 0건 (사람만 읽을 수 있다)"
            if not append_canary(paths, kind="review-format-invalid",
                                 detail=Path(rv.written).name, commit=r.to_commit):
                r.canary_write_failed += 1
    elif rv.skipped:
        r.review_note = f"리뷰 스킵: {rv.skipped}"
    elif rv.error:
        r.review_note = f"[중요] 리뷰 유실: {rv.error}"
        if not append_canary(paths, kind="review-lost",
                             detail=rv.error, commit=r.to_commit):
            r.canary_write_failed += 1


def process_event(ev: Event, *, registry: Registry | None = None,
                  reindex=None, git=None, synthesize: bool = True,
                  synth_run=None, review_run=None) -> ProjectResult:
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

    # [중요] **마운트되지 않은 프로젝트는 여기서 멈춘다** (`#242`). git 을 부르기 **전에** 막아야
    #    한다 — fetch·그래프·합성이 마운트 밖 프로젝트에 돌면 그것이 곧 비용이고, 워터마크까지
    #    찍히면 상태가 오염된다(실측 2026-08-22: 등록만 된 NS 를 색인하고 워터마크를 찍어
    #    온보딩 판정이 *"전부 초기화됐다"* 고 거짓 보고했다).
    # [중요] **`active` 가 비어도 막는다** — fail-closed. 2026-08-21 에 만든 게이트가 바로 그
    #    구멍(빈 active 면 통과)을 가졌다. 「모르면 통과」는 게이트가 아니다.
    # [주의] 건너뜀은 **에러가 아니다** — 유닛을 빨갛게 만들지 않고 사유만 남긴다.
    mounted = (reg.active or "").strip()
    if name != mounted:
        r.skipped = (f"마운트되지 않았다 (활성: {mounted or '(없음)'}) — "
                     f"git 을 부르지 않고 건너뛴다 (§5.5.2 단일 마운트)")
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

    # [중요] `reset --hard` 가 아니라 `merge --ff-only` 다. 마스터는 이 클론에 커밋하지 않으므로
    #    항상 fast-forward 여야 하고, **아니라면 그건 알아야 할 사고**다. 조용히 덮어쓰지 않는다.
    rc, out = run(paths.repo, "merge", "--ff-only", "FETCH_HEAD")
    if rc != 0 and "Already up to date" not in out:
        r.error = f"fast-forward 실패 — 미러가 갈라졌다: {out[:200]}"
        return r

    rc, out = run(paths.repo, "rev-parse", "HEAD")
    r.to_commit = out.strip() if rc == 0 else ""

    # ── [중요] 여기가 트윈이 자라는 지점이다 (중 1.1 · 중 1.2) ──────────
    #
    # 원본 `watch.py` 의 커밋 처리 순서를 그대로 따른다:
    #   ① 컨텍스트 MD 합성 (LLM) — `source_commit` 을 스탬프한다
    #   ② 관계 그래프 증분 (LLM 0) — 커밋 즉시
    #   ③ 색인 (아래) — ①이 문서를 바꿨을 때만 돈다
    #
    # 순서가 뒤집히면 안 된다: ①이 그래프를 **근거로** 읽으므로 그래프가 먼저면 좋지만,
    # 원본은 MD 를 먼저 만든다(그래야 `source_commit` 워터마크가 stale 판정의 기준이 된다).
    # 우리는 **그래프를 먼저** 돌린다 — LLM 0 이라 싸고, 합성이 최신 그래프를 근거로 쓴다.
    #
    # ── [중요] 커밋을 **하나씩** 걷는다 (`#278`·`#280`, 사용자 지시 2026-08-23) ────
    #
    # 기준은 `config.yaml` 의 **분석 커서**다 — 클론의 fetch 전 HEAD 가 아니다. 그 둘은
    # 갈라진다: 클론은 매 회차 ff 로 전진하는데 커서는 *문서가 끝난* 커밋에서만 전진하므로,
    # HEAD 를 기준으로 삼으면 **끝나지 않은 커밋의 변경이 다음 회차 diff 에서 사라진다.**
    # 원전도 `get_commits_between(last_hash, actual)` 로 커밋을 하나씩 걷는다 — 우리 이식이
    # 그 루프를 HEAD diff 하나로 뭉갠 것이 누락이었다(`#279`).
    from ..projects.config import ProjectConfig
    try:
        _cfg = ProjectConfig.load(paths.config)
    except Exception as e:                                  # noqa: BLE001
        r.error = f"config 를 읽지 못했다: {type(e).__name__}: {e}"
        return r
    cursor = (_cfg.analyzed_commit or "").strip()
    if not cursor and (_cfg.last_indexed_commit or "").strip():
        # [중요] **이행 폴백 — 값을 지어내는 것이 아니다.** `last_indexed_commit` 은 `#244`·`#274`
        #    게이트가 *"전 그룹 합성이 끝났다"* 를 확인했을 때만 찍힌 값이라, 커서가 뜻하는
        #    *"여기까지 문서가 끝났다"* 와 **같은 주장**이다. 이미 번 값을 새 키로 옮기는 것과
        #    없는 근거를 만드는 것은 다르다 — 후자는 `#275` 가 거부한 그것이다.
        #    [주의] 폴백을 **말한다.** 조용히 쓰면 다음 세션이 커서가 원래 있었다고 읽는다.
        cursor = (_cfg.last_indexed_commit or "").strip()
        r.cursor_note = (f"커서가 비어 워터마크({cursor[:8]})를 출발점으로 삼았다 — "
                         "같은 주장이다(#274 게이트가 확인하고 찍은 값). 이번 회차가 커서를 적는다")
    r.cursor_from = cursor

    if not cursor:
        # [중요] **커서가 없다는 것도 「다르다」다** (사용자 정정 2026-08-23): *"마지막 컨텍스트
        #    문서 분석한 해시값을 저장하고 다르면 깃에 헤더까지 하나씩 분석하고 문서를 만들면서
        #    해시값 맞추는 게 기본 동작"*. 그래서 **이력 처음부터** 걷는다 — 첫 커밋의 diff
        #    기준은 빈 트리다.
        #    [주의] 종전 구현은 여기서 멈추고 *"최초 합성은 온보딩 일"* 이라고 보고했다. 그것은
        #    지시에 없던 **내 판단**이었다. M2 금기(일괄 재생성)와도 다른 문제다 — 금기는 *이미
        #    있는 문서*를 한꺼번에 다시 만드는 것이고, 여기서 걷는 것은 그 커밋이 실제로 만진
        #    파일뿐이다.
        r.skipped = "저장된 해시가 없다 — 이력 처음부터 하나씩 분석한다"
    if cursor and cursor == r.to_commit:
        r.skipped = f"최신 — 커서가 현재 커밋과 같다 ({cursor[:8]})"
    else:
        commits, err = _commits_between(paths.repo, cursor, r.to_commit, run)
        if err:
            r.error = err
            return r
        r.commits_total = len(commits)
        if not commits:
            # [주의] 커서가 이 이력의 조상이 아니다 — 되감김·강제 푸시·잘못 적힌 값.
            #    조용히 「최신」으로 접으면 그 프로젝트는 영원히 안 자란다.
            _note(r, (f"커서 {cursor[:8] or '(없음)'} → {r.to_commit[:8]} 사이에 커밋이 "
                      "없다 — 커서가 이 이력의 조상이 아니다(되감김/강제 푸시?). 사람이 봐야 한다"))
        # 첫 커밋의 기준 — 커서가 없으면 **빈 트리**(그래야 그 커밋의 파일이 전부 들어온다)
        prev = cursor or EMPTY_TREE
        for c in commits:
            # [중요] 경계는 **두 겹**이다 — pathspec 으로 좁히고(`class_graph` 관례),
            #    `_source_only` 가 확장자로 한 번 더 자른다. 한 겹이면 인자를 한 번 잘못
            #    넘길 때 `Content/`(워킹트리의 93%)가 조용히 들어온다.
            rc, out = run(paths.repo, "diff", "--name-only", prev, c,
                          "--", SOURCE_SUBDIR)
            if rc != 0:
                r.halted = f"{c[:8]} diff 실패 — 커서를 전진시키지 않는다: {out[:120]}"
                break
            touched = [x.strip() for x in out.splitlines() if x.strip()]
            changed = _source_only(touched)
            if not changed:
                # 사용자 지시: **분석 대상이 소스 디렉토리 밖이면 스킵한다.**
                # [중요] 그때 **커서는 전진시킨다** — 안 그러면 매 회차가 같은 커밋을 다시
                #    걷는다(사용자 확인 2026-08-23: *"안 그럼 무한히 재시도할테니"*).
                if not _update_cursor(paths, c):
                    r.halted = f"{c[:8]} 커서 기록 실패 — config 에 `index:` 절이 없다"
                    break
                r.cursor_to, prev = c, c
                r.commits_nonsource += 1
                r.nonsource_notes.append(f"{c[:8]}: 소스 밖 변경만 — 합성 없음")
                continue
            r.source_changed += len(changed)
            _update_graphs(paths, changed, r)
            if not synthesize:
                # [중요] 합성이 꺼졌으면 **커서를 전진시키지 않는다.** 그래프는 풀 스캔으로
                #    복구되는 파생 자산이지만 문서는 아니다 — 전진시키면 그 커밋의 문서가
                #    영구히 안 만들어진다.
                r.halted = "합성이 꺼져 있다 — 그래프만 갱신하고 커서는 그대로 둔다"
                break
            _synthesize(paths, changed, r, commit=c, synth_run=synth_run)
            # ④ 자동 코드리뷰 (소 3.3.5) — 합성과 같은 게이트(synthesize) 아래 둔다:
            #    노드가 죽어 합성을 껐다면 리뷰도 돌 수 없는 상태다.
            _auto_review(paths, changed, r, commit=c, review_run=review_run)
            # [중요] **그 커밋의 문서가 실제로 생겼는지 본다.** 합성 실패·게이트 거부를
            #    「완료」로 세면 커서가 그 위를 넘어가고, 그 커밋의 변경은 영구 유실이다
            #    (원전이 가진 구멍 — `process_commit` 은 예외를 안 던지고 호출부가 그대로
            #    `save_state` 를 부른다. 우리는 멈춘다).
            from ..context_synth import synth as _cs
            missing = [k for k in _cs.group(changed)
                       if not _cs.doc_path(paths, k).is_file()]
            if missing:
                r.halted = (f"{c[:8]} 의 그룹 {len(missing)}개가 문서 없음 — 커서를 "
                            f"전진시키지 않는다(다음 회차가 이 커밋을 다시 한다)")
                break
            if not _update_cursor(paths, c):
                r.halted = f"{c[:8]} 커서 기록 실패 — config 에 `index:` 절이 없다"
                break
            r.cursor_to, prev = c, c
            r.commits_done += 1

    # ── 재색인은 컨텍스트가 실제로 바뀐 경우에만 ──────────────
    #
    # [중요] 사유를 **덮지 않고 쌓는다.** 걷기 단계가 이미 사유를 남겼을 수 있는데(커서가
    #    최신 · 커서 없음 · 조상 아님) 여기서 대입하면 그 판정이 사라진다 — 판정을 했는데
    #    안 보이면 「안 한 것」과 구분되지 않는다(이 저장소에서 반복 확인된 부류).
    now_digest = context_digest(paths)
    if not now_digest:
        _note(r, "context/ 가 없다")
    elif now_digest == read_digest(paths):
        _note(r, "컨텍스트 MD 변화 없음"
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

    # [중요] **워터마크는 색인할 것이 있었을 때만 찍는다** (`#244`). 종전에는 `to_commit` 만
    #    참이면 찍어서 **컨텍스트 MD 0건에도 찍혔다** — 실측: ServerTest 가 MD 0건인데
    #    `last_indexed_commit` 이 HEAD 였고, 2026-08-22 NS 온보딩에서도 표본 2건으로 워터마크가
    #    찍혀 온보딩 판정이 *"전부 초기화됐다"* 고 **거짓 보고**했다.
    #    [주의] 거짓 신선도는 합성을 **영원히 건너뛰게** 만든다 — 다음 이벤트가 그 커밋을
    #    기준으로 diff 하므로 변경분이 사라진다.
    # [주의] **`context_digest()` 로 판정하면 안 된다** — 빈 디렉토리도 해시(빈 문자열의
    #    sha256)를 돌려주므로 참이 된다. 실측 2026-08-22: 그렇게 짰다가 회귀 칸에 잡혔다.
    #    조건은 *"MD 가 한 건이라도 있는가"* 다(`#244` 완료 조건 그대로).
    if r.to_commit:
        ok_synth, why = synth_complete(paths, git=run)
        if ok_synth:
            _update_watermark(paths, r.to_commit)
        else:
            # 조용히 넘기지 않는다 — 「안 찍었다」와 「찍었다」는 다른 상태다.
            _note(r, f"워터마크 미기입 — 합성이 안 끝났다({why}). "
                     f"기준을 전진시키면 남은 그룹의 변경이 유실된다")
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

    # ── [중요] 색인 일시 중지 게이트 (소 3.5.1 — 원전 watch_state 이식) ──────
    #
    # 진행 중 분산 작업이 있으면 **fetch·색인을 하지 않는다.** 원전 근거: *"feature 브랜치
    # 작업 중 main 인덱싱 무의미 + 워커들과 git lock 경쟁 방지"*.
    #
    # [주의] 스풀은 **비운다**(claim 하고 처리를 건너뛴다). 남기면 `ax-indexer.path` 가 조건이 계속
    # 참이라 재트리거를 반복할 수 있다. [중요] **비워도 유실이 아니다** — 이 소비자는 state-based 라
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
    # [중요] **이벤트가 없어도 한 바퀴 돈다** (소 3.5.1 과 짝).
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
        # [주의] 못 읽는 프로젝트는 조용히 건너뛰지 않고 **세어서** 결과에 남긴다.
        # [중요] **마운트된 것만 돈다** (`#242`). 종전에는 `reg.names` 전부를 돌아, 등록만 된
        #    프로젝트도 5분마다 fetch·대조 대상이 됐다(실측 2026-08-22: `프로젝트 2개`).
        #    관문(`process_event`)이 다시 막지만 여기서 애초에 만들지 않는 것이 싸다.
        ids = []
        _mounted = (reg.active or "").strip()
        # [중요] **비마운트 프로젝트를 「건너뜀」으로 남긴다** (`#246` 완료 조건 ③).
        #    실측 2026-08-23: 마운트 왕복 뒤 로그에 마운트된 것만 나오고 나머지는 **아예
        #    언급이 없었다** — 부재는 기록이 아니다. 「NS 는 왜 안 도나」를 로그로 답할 수
        #    없으면 운영자는 고장과 설계를 구분하지 못한다.
        res.unmounted = [n for n in reg.names if n != _mounted]
        for _name in ([_mounted] if _mounted and _mounted in reg.names else []):
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
        # [중요] 종료코드 4 = 게이트에 걸림. **고장이 아니다** — 유닛이 `SuccessExitStatus=4` 로 받는다
        #    (상태 화면의 종료코드 3 과 같은 패턴: *"늘 빨간 유닛은 유닛이 아니다"*).
        print(f"{r.paused} · 이벤트 {r.deferred}건 넘김 (유실 아님 — 다음 회차에 누적분으로 잡힌다)")
        return 4
    print(r.summary())
    for x in r.results:
        print(x.line())
        # [중요] 유실은 목록으로 남긴다 — 워터마크가 이미 전진했으므로 다시 찾을 수 없다.
        for g in x.lost_groups:
            print(f"      [중요] {g}")
    if r.blocked_recursion:
        print(f"  (색인기 자신의 커밋 {r.blocked_recursion}건 차단 — 재귀 방지)")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
