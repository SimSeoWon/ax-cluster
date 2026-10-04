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

from .. import gitea_group
from ..context_search.paths import ProjectPaths, resolve
from ..projects.config import ConfigError, Registry, normalize_project_id
from .spool import Event, Spool

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
    mirror_note: str = ""       # 미러를 되돌렸으면 무엇을 버렸는지 (`#376` ⑷)
    synth_written: int = 0
    synth_lost: int = 0         # [중요] 문서가 안 생긴 그룹 수 = 그 커밋의 영구 유실
    synth_note: str = ""
    lost_groups: list[str] = field(default_factory=list)
    canary_write_failed: int = 0   # [주의] 카나리 기록 자체가 실패한 횟수 (조용히 넘기지 않는다)
    review_written: str = ""       # 자동 코드리뷰 리포트 경로 (소 3.3.5)
    review_note: str = ""          # 리뷰 스킵/실패 사유
    review_serial: str = ""        # 리뷰 번호 (`#627` — R35). 요약 줄에 싣는다
    review_queued: str = ""        # 리뷰 큐에 등재한 커밋 (`#635`)
    # ── 분석 커서 (`#278` — 커밋 하나씩) ──
    cursor_from: str = ""          # 이 회차가 시작한 커서 (config.yaml 의 analyzed_commit)
    cursor_note: str = ""          # 커서를 어디서 얻었는지 (이행: 워터마크 폴백)
    cursor_to: str = ""            # 이 회차가 적어 둔 커서. 비면 **한 커밋도 못 끝냈다**
    commits_total: int = 0         # 커서 → 현재 커밋 사이의 커밋 수
    commits_done: int = 0          # 문서까지 끝나 커서를 전진시킨 커밋 수
    commits_nonsource: int = 0     # 소스 밖 변경만 있어 합성 없이 전진시킨 커밋 수
    nonsource_notes: list = field(default_factory=list)
    halted: str = ""               # [중요] 걷기를 멈춘 사유. 멈췄으면 커서는 그 앞에 있다
    retry_skipped: int = 0         # 재시도에서 **이미 이 커밋으로 스탬프된** 그룹의 파일 수

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
        if self.mirror_note:
            # [중요] 되돌린 것은 **반드시 보인다** — 조용한 파괴적 명령을 만들지 않는다
            parts.append(self.mirror_note)
        if self.review_written:
            # 번호가 저널에 남아야 「이 커밋 = R35」를 찾는다 (`#627`). 없으면 없다고 찍는다
            parts.append("리뷰 1" + (f" ({self.review_serial})" if self.review_serial
                                     else " (번호 없음 — 목록 조회 때 붙는다)"))
        if self.review_queued:
            # [중요] **색인은 리뷰 등재로 위임한다** (`#635`) — 여기서 기다리지 않는다.
            #    이 줄이 없으면 「리뷰가 어디로 갔나」가 저널에서 사라진다.
            parts.append(f"리뷰 등재로 위임 {self.review_queued[:8]}")
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
        if self.retry_skipped:
            parts.append(f"재시도 생략 {self.retry_skipped}")
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
        # [중요] **멈춘 사유와 합성 사유를 저널 줄에 싣는다** — `summary` 에만 있으면 서비스 로그에
        #    안 나온다. 실측 2026-09-13 NS: 사흘간 「합성 0건」만 찍혔고 「위 사유 참조」가 가리키는
        #    줄이 없었다(사유는 `SynthError` 였고 커서가 한 커밋에 갇혀 있었다).
        if self.synth_note and not self.synth_written:
            bits.append(f"합성 사유: {self.synth_note[:160]}")
        if self.halted:
            bits.append(f"[중요] 멈춤: {self.halted}")
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


# [중요] **판정은 `master/gitea_group` 하나다** (`#336` ②). 이 함수가 원래 여기 있었고
#    `twin_base`·`ontology/drift` 는 무조건 `sg` 로 감싸 서비스 컨텍스트에서 죽었다. 같은 판정을
#    세 벌 두면 조용히 어긋난다 — 그래서 정본을 옮기고 여기서는 부른다.
def _git(repo: Path, *args: str, group: bool | None = None) -> tuple[int, str]:
    """git 실행. 필요할 때만 `sg gitea` 로 감싼다 (`gitea_group.wrap`)."""
    cmd = gitea_group.wrap(["git", "-C", str(repo), *args], force=group)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=GIT_TIMEOUT)
    return p.returncode, (p.stdout + p.stderr).strip()


# [중요] 카나리 기록기는 `master/canary.py` 로 옮겼다 (소 3.5.6 · `#182`).
#    이유는 층이다 — `context_search/rebuild` 도 찍어야 하는데 그쪽이 `events` 를 부르면
#    **층 역전**이다. [주의] 이 이름으로 부르던 곳(테스트 포함)이 그대로 돌도록 재수출한다.
from ..canary import (  # noqa: E402,F401
    KIND_CONTEXT_MD_LOST, KIND_DOMAIN_INDEX_GAP, append_canary,
)


def _recover_mirror(repo: Path, run) -> str:
    """더러워진 미러를 원격 상태로 되돌린다 — **되돌렸으면 사유 문자열**, 아니면 빈 문자열.

    🔴 [중요] **조건을 재고 건다** (`#376` ⑷). 되돌리는 것은 `reset --hard` 라 파괴적이다:

        미러에만 있는 커밋 0 · 워킹트리가 더럽다   → 되돌린다 (파생물이므로 잃을 것이 없다)
        미러에만 있는 커밋 ≥ 1                    → **되돌리지 않는다.** 알아야 할 사고다
        워킹트리가 깨끗하다                        → 할 일이 없다 (실패 사유가 다른 것이다)

    [중요] **무엇을 버렸는지 센다** — 조용히 지우면 다음 사람이 무슨 일이 있었는지 모른다.
    [주의] `git clean` 은 하지 않는다 — 추적 안 되는 파일까지 지우는 것은 이 사고를 푸는 데
    필요하지 않았고(실측: 그 파일들은 들어오는 커밋의 것이라 reset 이 흡수했다) 범위가 넓다.
    """
    rc, dirty = run(repo, "status", "--porcelain")
    if rc != 0 or not dirty.strip():
        return ""
    rc2, cnt = run(repo, "rev-list", "--count", "FETCH_HEAD..HEAD")
    ahead = int(cnt.strip()) if rc2 == 0 and cnt.strip().isdigit() else -1
    if ahead != 0:
        return ""                       # 모르거나(-1) 앞서 있으면 손대지 않는다
    lines = [ln for ln in dirty.splitlines() if ln.strip()]
    rc3, out3 = run(repo, "reset", "--hard", "FETCH_HEAD")
    if rc3 != 0:
        return f"[주의] 미러 복구 실패 — {out3[:200]}"
    return (f"[중요] 반쯤 적용된 미러를 되돌렸다 (`#376`) — 버린 워킹트리 변경 {len(lines)}건 "
            f"(미러에만 있는 커밋 0 을 확인하고 실행): " + ", ".join(x.strip()[:40] for x in lines[:3]))


def _ff_reason(repo: Path, out: str, run) -> str:
    """fast-forward 가 깨진 사유를 **관측으로** 가른다 (`#376` ⑶).

    갈라졌다고 말하려면 근거가 둘 중 하나여야 한다 — 미러에만 있는 커밋이 세어지거나,
    git 자신이 그렇게 말했거나(`Not possible to fast-forward`). 둘 다 아니면 **단정하지 않고**
    원문을 낸다(LFS smudge 실패가 그 자리였다).
    """
    rc, cnt = run(repo, "rev-list", "--count", "FETCH_HEAD..HEAD")
    n = int(cnt.strip()) if rc == 0 and cnt.strip().isdigit() else -1
    if n > 0:
        return f"미러가 갈라졌다 (미러에만 {n}커밋): {out[:300]}"
    if "Not possible to fast-forward" in out or "diverged" in out:
        return f"미러가 갈라졌다: {out[:300]}"
    return f"[주의] 갈라진 것이 아니다 (미러에만 있는 커밋 {max(n, 0)}건) — 원문: {out[:400]}"


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


def _unstamped_files(paths: ProjectPaths, changed: list[str], commit: str) -> list[str]:
    """이 커밋으로 **아직 스탬프되지 않은** 그룹의 파일만 남긴다 (`#280` 재시도 낭비 차단).

    [중요] 판정은 문서 프론트매터의 `source_commit` 이다 — 사용자가 설계한 그 값. 같은 커밋을
    다시 걸을 때(앞 회차에서 일부 그룹이 게이트에 막혀 커서가 안 올라간 경우) 이미 끝난 그룹을
    다시 합성하면 그만큼이 순전히 낭비다.
    [주의] **커밋이 다르면 반드시 다시 만든다** — 그것이 최신화의 본체다.
    """
    from ..context_synth import md as md_mod, synth as cs

    keep: list[str] = []
    for key, files in cs.group(changed).items():
        doc = cs.doc_path(paths, key)
        try:
            if doc.is_file() and md_mod.read_source_commit(
                    doc.read_text(encoding="utf-8", errors="replace")) == commit:
                continue                                  # 이 커밋으로 이미 끝났다
        except OSError:
            pass
        keep.extend(files)
    return keep


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


def _source_only(files: list[str], paths: "ProjectPaths | None" = None) -> list[str]:
    """소스 디렉토리 밖은 버린다 (사용자 지시 2026-08-23 · §5.2-E).

    [중요] **판정식을 새로 만들지 않는다** — `class_graph.list_source_files` 와 같은 두 겹
    (`Source/` 접두 + 파서 확장자)이다. `config.yaml` 의 `include` 글롭으로 따로 짜면 매처가
    둘이 되고, 그 둘은 언젠가 갈라진다(원전 대조에서 반복 확인된 부류).
    """
    from ..context_search.paths import DEFAULT_SCOPE
    from ..graph import parse

    # 판정은 `SourceScope.contains` 한 자리다 (`#693`) — 기본 경계는 종전과 같다
    scope = paths.scope if paths is not None else DEFAULT_SCOPE
    return [f for f in files if scope.contains(f, parse.PARSE_EXTS)]


def _sync_submodules(paths: ProjectPaths, run) -> str:
    """선언된 서브모듈을 미러 HEAD 가 가리키는 커밋으로 맞춘다 (`#693`). 빈 문자열이면 정상.

    [중요] **한 단계만** — `--recursive` 를 붙이지 않는다. 서브모듈 안의 서브모듈(`ggml`)은 경계
    밖이고, 받으면 클론만 무거워진다. 서브모듈을 선언하지 않은 프로젝트는 git 을 부르지 않는다.
    """
    subs = paths.scope.submodules
    if not subs:
        return ""
    rc, out = run(paths.repo, "submodule", "update", "--init", "--", *subs)
    return "" if rc == 0 else f"submodule update 실패 (rc={rc}): {out[:200]}"


def _expand_gitlinks(paths: ProjectPaths, prev: str, cur: str, touched: list, run) -> tuple:
    """diff 에 **서브모듈 경로 자체**가 나오면 그 안의 변경 파일로 펼친다 (`#693`).

    [중요] 루트 diff 는 포인터가 바뀐 것만 안다(`vendor/kimodo.cpp` 한 줄). 펼치지 않으면
    원본을 따라간 커밋(kimodo `#694`)이 **소스 밖 변경으로 접혀** 문서가 영영 안 갱신된다.
    돌려주는 것: `(펼친 목록, 사유)` — 사유가 있으면 펼치지 못한 것이다(조용히 버리지 않는다).
    """
    subs = set(paths.scope.submodules)
    out, why = [], []
    for f in touched:
        if f not in subs:
            out.append(f)
            continue
        olds = []
        for rev in (prev, cur):
            if rev == EMPTY_TREE:
                olds.append("")
                continue
            rc, o = run(paths.repo, "rev-parse", f"{rev}:{f}")
            olds.append(o.strip() if rc == 0 else "")
        old, new = olds
        if not new:
            why.append(f"{f}: {cur[:8]} 에 서브모듈 포인터가 없다(삭제?)")
            continue
        sub = paths.repo / f
        args = (["diff", "--name-only", old, new] if old
                else ["ls-tree", "-r", "--name-only", new])
        rc, o = run(sub, *args)
        if rc != 0:
            why.append(f"{f}: {old[:8] or '(처음)'}..{new[:8]} 펼치기 실패 — {o[:120]}")
            continue
        out.extend(f"{f}/{x.strip()}" for x in o.splitlines() if x.strip())
    return out, " · ".join(why)


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
    # [중요] **보류·포기를 로그에 싣는다** (`#377`). 거부된 그룹은 다음 실행이 다시 시도하고,
    #    상한을 넘으면 자동 재시도를 멈추는데 — **그 사실이 안 보이면 조용히 죽은 것과 같다.**
    from ..context_synth import pending as _pending
    _p = _pending.summary(paths)
    if _p:
        r.synth_note += " · " + _p
    if st.lost:
        # [중요] 어느 그룹이 유실됐는지 남긴다 — 숫자만으로는 다시 찾을 수 없다.
        for g in st.results:
            if g.lost:
                r.lost_groups.append(f"{g.key}: {g.reason[:120]}")
                # [중요] 저널만으로는 반복을 못 본다 — 누적한다 (소 3.5.6).
                if not append_canary(paths, kind="context-md-lost",
                                     detail=f"{g.key}: {g.reason}", commit=r.to_commit):
                    r.canary_write_failed += 1


def _enqueue_review(paths: ProjectPaths, changed: list[str], r: "ProjectResult",
                    *, commit: str = "", enqueue=None) -> None:
    """리뷰를 **큐에 등재만** 한다 (`#635` · 설계안 `docs/17-review-queue.md` §3.2).

    [중요] **색인은 여기서 LLM 을 기다리지 않는다.** 등재는 파일 쓰기 한 번이고, 리뷰는
    별도 유닛(`ax-review-queue`)이 소비한다. 종전에는 `REVIEW_TIMEOUT = 240` 초가 이
    경로 안에 있었다(결함 ⓑ).

    ## [중요] 이 함수가 닫는 결함 둘 — 종전 호출부가 갖고 있던 것

        ⓒ 형식 위반 파일이 재리뷰를 영구 차단했다. 가드가 *"파일이 있으면 스킵"* 이었는데
          `format_ok=False` 여도 파일은 써지고 `rv.written` 이 세팅된다. 소비자는 0건으로
          읽는데 다시 만들 길이 없었다.
        ⓓ `todo`(미스탬프 파일)가 비면 리뷰가 아예 안 돌았고, 재시도 회차에는 커밋 전체가
          아닌 **부분 파일 목록**만 봤다. → 호출부가 `if todo:` 밖으로 나오고 `changed` 를 넘긴다.

    [중요] **커밋당 리뷰는 한 번이다** (실측 2026-09-13 NS: 같은 커밋 리뷰 150개). 그 보장은
    이제 파일 존재가 아니라 **큐의 커밋 키**가 한다 — `enqueue` 가 `pending`/`running`/`done`
    인 같은 키를 다시 넣지 않는다.

    [주의] **이미 리뷰 파일이 있는 커밋**(큐 도입 전에 인라인으로 만들어진 것)은 그 파일의
    형식을 보고 가른다 — 정상이면 등재하지 않고, **형식 위반이면 등재한다**. 후자가 곧 ⓒ 다.
    """
    # 색인 전용(`#693`)은 **자동 리뷰를 쌓지 않는다** — 사용자 결정 범위가 「색인까지」이고,
    #    리뷰 경로는 UE 전제(`Source/`·`.h/.cpp/.cs`)에 레드마인 이슈까지 낸다.
    #    [주의] 호출부가 아니라 여기서 막는다 — 호출부 형태는 결함 ⓓ 의 회귀 테스트가 고정한다.
    from ..projects import profile as _pf
    if _pf.is_index_only(getattr(paths, "name", "")):
        r.review_note = "색인 전용 프로젝트 — 자동 리뷰를 쌓지 않는다 (#693)"
        return

    from ..context_synth import review_gen as rg
    from ..context_synth import review_queue as rq

    changed = rg.review_source_files(paths, changed)
    if not changed:
        r.review_note = "리뷰 등재 생략: 소스 변경 없음"
        return

    c = commit or r.to_commit
    if not c:
        r.review_note = "리뷰 등재 생략: 커밋이 없다"
        return

    # [주의] 큐 도입 전 인라인 경로가 남긴 리뷰 — 형식이 정상이면 다시 만들지 않는다.
    #    형식 위반이면 등재한다(소비자 기준 0건인 채로 굳는 것이 ⓒ 였다).
    prior = sorted((Path(paths.root) / rg.REVIEWS_DIRNAME).glob(f"*/*_{c[:8]}.md"))
    if prior:
        try:
            ok = rg.format_ok(prior[0].read_text(encoding="utf-8"))
        except OSError:
            ok = False
        if ok:
            r.review_note = f"리뷰 등재 생략: 정상 리뷰가 이미 있다 ({prior[0].name})"
            return
        r.review_note = f"[중요] 기존 리뷰가 형식 위반 — 다시 등재한다 ({prior[0].name})"

    fn = enqueue or rq.enqueue
    try:
        item = fn(paths.root, kind="commit", key=c, files=list(changed or []))
    except Exception as e:                              # noqa: BLE001
        # [중요] 등재 실패는 리뷰 유실이다 — 워터마크가 이 뒤에서 전진한다.
        r.review_note = f"[중요] 리뷰 등재 실패: {type(e).__name__}: {e}"
        if not append_canary(paths, kind="review-lost",
                             detail=r.review_note, commit=r.to_commit):
            r.canary_write_failed += 1
        return
    r.review_queued = c
    note = f"리뷰 큐 등재 {c[:8]} (파일 {len(changed or [])}건 · {item.get('state')})"
    r.review_note = (r.review_note + " · " + note) if r.review_note else note


def _auto_review(paths: ProjectPaths, changed: list[str], r: "ProjectResult",
                 *, commit: str = "", review_run=None) -> None:
    """[폐기 예정] 인라인 자동 코드리뷰 — `#635` 로 큐 위임(`_enqueue_review`)으로 바뀌었다.

    [주의] **호출부는 없다.** 큐 소비자(`#636`)가 서는 동안 되돌릴 자리로만 남겨 둔다.
    이 경로의 결함 넷(ⓐ 영구 유실 · ⓑ 색인이 240초 대기 · ⓒ 형식 위반이 재리뷰 차단 ·
    ⓓ `todo` 가 비면 안 돎)은 `docs/17-review-queue.md` §2 에 있다.
    """
    from ..context_synth import review_gen as rg
    c = commit or r.to_commit
    done = sorted((Path(paths.root) / rg.REVIEWS_DIRNAME).glob(f"*/*_{c[:8]}.md")) if c else []
    if done:
        r.review_note = f"리뷰 스킵: 이 커밋의 리뷰가 이미 있다 ({done[0].name})"
        return
    fn = review_run or rg.review_commit
    try:
        rv = fn(paths, c, changed)
    except Exception as e:                              # noqa: BLE001
        r.review_note = f"[중요] 리뷰 생성 예외: {type(e).__name__}: {e}"
        if not append_canary(paths, kind="review-lost",
                             detail=r.review_note, commit=r.to_commit):
            r.canary_write_failed += 1
        return
    if rv.written:
        r.review_written = rv.written
        r.review_serial = getattr(rv, "serial", "") or ""
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
                  synth_run=None, review_run=None, enqueue_review=None) -> ProjectResult:
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
    # 🔴 [중요] **타입과 무관하게 마운트된 것만 갱신한다** (사용자 2026-09-28 — *"마운트 된것만
    #    검색하고 갱신한다"*). `#693` 초판이 색인 전용을 여기서 예외로 뺐다가 되돌렸다 —
    #    NS 가 마운트된 채로 kimodo 를 합성했다. 새 프로젝트는 **마운트를 옮기고** 돌린다.
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
        # 🔴 [중요] **반쯤 적용된 미러를 되돌린다** (`#376` ⑷, 사용자 승인 2026-09-07).
        #    실측 2026-09-06: pull 이 체크아웃 도중 LFS 에서 죽어 워킹트리에 삭제 2건·수정 6건이
        #    남았고, 그 상태로는 다음 실행도 같은 자리에서 실패했다 — **사람이 `reset --hard`
        #    로 풀어야 했다.**
        #    [중요] **파괴적 명령이라 조건을 재고 건다** — 미러에만 있는 커밋이 **0** 일 때만.
        #    미러는 파생물이고 push 가 센티넬로 막혀 있어 그 값은 정상적으로 0 이다. 0 이 아니면
        #    그것은 **알아야 할 사고**이므로 되돌리지 않고 사유를 낸다.
        recovered = _recover_mirror(paths.repo, run)
        if recovered:
            r.mirror_note = recovered
            rc, out = run(paths.repo, "merge", "--ff-only", "FETCH_HEAD")
    if rc != 0 and "Already up to date" not in out:
        # 🔴 [중요] **사유를 라벨로 덮지 않는다** (`#376` ⑶). 종전에는 무조건
        #    *"미러가 갈라졌다"* 로 적었는데, 2026-09-06 의 실패는 **갈라짐이 아니라 LFS
        #    smudge 실패**였다(`origin/main..HEAD` 0건). 그 라벨을 믿고 조사하면 엉뚱한
        #    곳을 판다 — 라벨은 **재서** 붙이고, 못 재면 원문만 낸다.
        r.error = f"fast-forward 실패 — {_ff_reason(paths.repo, out, run)}"
        return r

    rc, out = run(paths.repo, "rev-parse", "HEAD")
    r.to_commit = out.strip() if rc == 0 else ""
    sub_err = _sync_submodules(paths, run)
    if sub_err:
        r.error = sub_err
        return r

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
                          "--", *paths.scope.roots)
            if rc != 0:
                r.halted = f"{c[:8]} diff 실패 — 커서를 전진시키지 않는다: {out[:120]}"
                break
            touched = [x.strip() for x in out.splitlines() if x.strip()]
            if paths.scope.submodules:
                touched, why = _expand_gitlinks(paths, prev, c, touched, run)
                if why:
                    # [중요] 커서를 전진시키지 않는다 — 전진하면 그 포인터 변경의 문서가 영영 안 생긴다
                    r.halted = f"{c[:8]} 서브모듈 펼치기 실패 — 커서를 전진시키지 않는다: {why}"
                    break
            changed = _source_only(touched, paths)
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
            # [중요] **재시도에서 이미 이 커밋으로 스탬프된 그룹은 다시 만들지 않는다.**
            #    커밋 단위 트랜잭션이라 한 그룹이 실패하면 커서가 안 올라가고 다음 회차가 같은
            #    커밋을 다시 걷는데, 종전 구현은 **성공한 그룹까지 매번 다시 합성**했다
            #    (실측 2026-08-23 NS: 회차마다 20여 건이 헛일 · `.43` 이 계속 돌았다).
            #    판정 근거는 사용자가 설계한 그 값이다 — 문서에 찍힌 `source_commit`.
            todo = _unstamped_files(paths, changed, c)
            if len(todo) != len(changed):
                r.retry_skipped += len(changed) - len(todo)
            if todo:
                _synthesize(paths, todo, r, commit=c, synth_run=synth_run)
            # ④ 자동 코드리뷰 — **큐에 등재만 한다** (`#635`).
            #    🔴 [중요] `if todo:` **밖**이고 `changed` 를 넘긴다 — 둘 다 결함 ⓓ 였다.
            #      ⑴ 합성이 이미 끝난 커밋(`todo` 가 빈 재시도 회차)은 종전에 리뷰가 아예
            #         호출되지 않았다 → 합성 성공 + 리뷰 실패 커밋은 영구 유실이었다.
            #      ⑵ 종전엔 `todo`(미스탬프분)를 넘겨 재시도 회차에 **부분 파일 목록**만 봤다.
            #         리뷰 대상은 커밋 전체다.
            #    [주의] 합성 게이트(`synthesize`) 아래 두지 않는다 — 등재는 LLM 을 쓰지 않으므로
            #      노드가 죽어도 할 수 있고, 오히려 그때 쌓아 둬야 나중에 소비된다.
            _enqueue_review(paths, changed, r, commit=c, enqueue=enqueue_review)
            # [중요] **그 커밋의 문서가 실제로 생겼는지 본다.** 합성 실패·게이트 거부를
            #    「완료」로 세면 커서가 그 위를 넘어가고, 그 커밋의 변경은 영구 유실이다
            #    (원전이 가진 구멍 — `process_commit` 은 예외를 안 던지고 호출부가 그대로
            #    `save_state` 를 부른다. 우리는 멈춘다).
            # [중요] **지금 클론에 남은 파일만 센다** — 원전 `_group_files` 가 `exists()` 로
            #    거르는 것과 같고, `synth.run` 도 같은 식으로 거른다(`synth.py:461`). 안 거르면
            #    **뒤 커밋이 지운 그룹**의 문서를 영원히 요구해 커서가 그 커밋에 갇힌다
            #    (실측 2026-09-13 NS: `0b33810` 이 만든 `NSCombatCharacterBase` 를 `4773dce` 가
            #    지웠고, 사흘간 10분마다 같은 커밋을 다시 걸었다).
            from ..context_synth import synth as _cs
            alive = [f for f in changed if (paths.repo / f).is_file()]
            # [DOC] `#375` — **존재 ≠ 그 커밋을 반영함.** 손으로 만든 문서(스탬프 -1)·레거시 문서·
            #    부분 실패가 남긴 옛 문서도 파일은 있다. 파일 존재만 보면 그 위로 커서가 넘어가
            #    가드가 지키려던 「영구 유실 방지」가 뚫린다. 판정은 `_unstamped_files` 와 **같은
            #    값** — 문서 프론트매터의 `source_commit` 이 이 커밋 `c` 인가 — 를 쓴다.
            # [DOC] 범위는 이 커서 판정 하나다. `synth_complete`(워터마크)는 건드리지 않는다.
            # [DOC] [주의] 합성이 「내용이 같아 다시 쓰지 않는」 경로로 성공 그룹의 스탬프를 안
            #    올리는 경우가 있으면 커서가 영원히 멈춘다. 그 경로를 확인하고, 있으면 **고치지 말고**
            #    결과 노트로 보고한다(범위 밖 파일 — 사용자 규칙).
            #    확인 결과(이 조각): `synthesize_group` 은 게이트를 통과하면 언제나
            #    `md.finalize(commit=c)` → `stamp` → `write_text` 를 거치고, `_synthesize` 는
            #    `skip_existing` 을 넘기지 않는다 — 「같은 내용이라 안 쓴다」 경로는 없다.
            missing = list(_cs.group(_unstamped_files(paths, alive, c)))
            if missing:
                r.halted = (f"{c[:8]} 의 그룹 {len(missing)}개가 이 커밋으로 스탬프된 문서 "
                            f"없음 — 커서를 전진시키지 않는다(다음 회차가 이 커밋을 다시 한다)")
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


def _note_dispatch_triggers(batch, reg) -> int:
    """골조 push(`task/<work>/base`)를 봤으면 **파견 트리거만** 남긴다 (`#340` 갈래 ⓑ).

    [중요] **게이트보다 먼저 불려야 한다.** 게이트는 `claim_batch` 로 이벤트를 claim 하고
    `done()` 으로 버린 뒤 `return` 하므로, 이 호출이 게이트 뒤에 있으면 **영원히 안 불린다** —
    그리고 골조 push 는 **정의상 항상 진행 중 work 이 있을 때** 일어난다(`#317` ① 순서:
    0 등재 → 1 브랜치 → 2 골조 push). 실측 2026-08-31 23:08:24: 그 이벤트 1건이 그대로
    버려졌고, `[dispatch]` 줄이 하나도 없어 사람이 영원히 기다렸다.

    [중요] **`batch.events` 를 보지 않고 배치 디렉토리를 직접 읽는다.** `coalesce()` 가
    `project_id` 당 **최신 하나만** 남기므로, 골조 push 뒤에 같은 프로젝트의 다른 push 가
    한 배치에 들어오면 골조 이벤트가 **조용히 사라진다.** 색인은 state-based 라 그래도
    되지만(미러 HEAD 를 대조한다) 파견의 트리거는 그 이벤트 하나뿐이라 안 된다.

    [주의] 여기서 파견하지 않는다 — 파견은 분 단위이고 이 소비자는 oneshot 이다.
    """
    import json as _json

    from ..work.autodispatch import note_trigger, work_id_from_ref
    n = 0
    try:
        files = sorted(f for f in batch.dir.iterdir() if f.is_file())
    except OSError as e:
        print(f"[dispatch-trigger] [주의] 배치를 못 읽었다 — {type(e).__name__}: {e}")
        return 0
    for f in files:
        try:
            d = _json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue                      # 거부 처리는 `_read_batch` 몫이다
        if not isinstance(d, dict):
            continue
        wid = work_id_from_ref(str(d.get("ref") or ""))
        if not wid:
            continue
        pid = str(d.get("project_id") or "")
        name = reg.find_by_project_id(pid) if pid else ""
        if not name:
            # 조용히 넘기지 않는다 — 골조 push 를 봤는데 프로젝트를 못 풀면 파견이 영구 정지다.
            print(f"[dispatch-trigger] [중요] 골조 push 인데 프로젝트를 못 찾았다 — "
                  f"project_id={pid!r} · work={wid}")
            continue
        try:
            path = note_trigger(wid, name, str(d.get("ref") or ""))
        except OSError as e:
            print(f"[dispatch-trigger] [중요] 트리거를 못 썼다 — {type(e).__name__}: {e}")
            continue
        print(f"[dispatch-trigger] 골조 push 감지 — {name}/{wid} → {path}")
        n += 1
    return n


def consume_once(spool: Spool | None = None, *, registry: Registry | None = None,
                 reindex=None, git=None, progress=None) -> RunResult:
    """스풀을 한 번 비운다. **다른 소비자가 돌고 있으면 즉시 물러난다** (flock)."""
    sp = spool or Spool()
    res = RunResult()
    if not sp.acquire():
        res.note = "다른 소비자가 돌고 있다 — 물러난다"
        return res

    try:
        return _consume_locked(sp, res, registry=registry, reindex=reindex,
                               git=git, progress=progress)
    finally:
        sp.release()


def _consume_locked(sp, res, *, registry=None, reindex=None, git=None,
                    progress=None) -> RunResult:
    """단일 소비자 락 안에서 고아 배치부터 복구한다 (`#714`)."""
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
    if g.degraded:
        res.note = (res.note + " · " if res.note else "") + g.degraded

    for batch in sp.iter_all_pending(is_registered=known):
        # 고아에도 같은 검증·게이트·트리거 경로를 적용한다. 신규 claim은 복구 뒤다.
        _note_dispatch_triggers(batch, reg)
        res.coalesced += batch.coalesced_away
        res.rejected += batch.rejected
        res.blocked_recursion += batch.skipped_index_output
        res.claimed += (len(batch.events) + batch.coalesced_away + batch.rejected
                        + batch.skipped_index_output)
        if g.paused:
            res.paused = g.line()
            res.deferred += len(batch.events)
        else:
            for ev in batch.events:
                if progress:
                    progress(f"{ev.project_id} {ev.old[:8]}→{ev.new[:8]}")
                result = process_event(ev, registry=reg, reindex=reindex, git=git)
                res.results.append(result)
                if not result.ok:
                    # 배치 전체를 남겨 다음 기동에서 다시 시도한다 (at-least-once).
                    return res
        sp.done(batch)
    if g.paused:
        return res
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
    if not res.results:
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
