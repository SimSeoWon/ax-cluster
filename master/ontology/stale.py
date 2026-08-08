"""stale 판정 — 어느 도메인을 재합성해야 하는가 (소 1.3.8). **LLM 0.**

원본: `watcher/ontology_refresh.compute_stale_domains` (Phase η.8).

## 원리 — 리비전 워터마크 두 개를 비교한다

    stored  = `class_ontology.source_commit`  ← **합성 시점**에 찍은 스냅샷
    latest  = 그 클래스의 컨텍스트 MD `source_commit`  ← **커밋 시점**에 갱신

하나라도 다르면 그 도메인은 stale 이다. 우리 `context_synth` 가 문서를 만들 때 `latest` 를
찍고(실측 확인), 재합성이 `stored` 를 `latest` 로 다시 찍으면 **자동으로 settle** 된다.

## 🔴 이 설계가 대체한 것 — dirty 플래그

Phase η.8 이 `domain_dirty` 테이블을 **없앴다.** 플래그는 누가 세우고 누가 지우는지가
갈려 있어 *"세워졌는데 안 지워짐"*·*"count=0 오인 폭주"* 가 났다. 워터마크는 **상태가
아니라 사실의 비교**라 그 실패 모드가 구조적으로 없다 — 재시작해도 같은 답이 나온다.

## 🔴 `-1` 규약이 첫 배포 폭주를 막는다

값을 못 가져오면 양쪽 다 `-1` 이다. `-1 == -1` 이므로 **not stale** — 레거시 문서나
커밋이 아직 없는 상태에서 전체 재합성이 터지지 않는다. 실제 커밋이 올라와 문서가
재생성될 때 비로소 실 리비전을 얻고, 그때만 stale 이 된다.

**commit-hash 축 밖의 변경**(도메인 MD 편집·신규 도메인)은 여기서 안 잡힌다 —
eventually-consistent 다. 다음 코드 변경 사이클이나 강제 재합성이 반영한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..context_search.paths import ProjectPaths
from ..context_synth import md as md_mod
from . import yaml_io

MISSING = "-1"


def context_doc_for(paths: ProjectPaths, source_file: str) -> Path:
    """소스 파일 → 그 파일의 컨텍스트 MD. **합성기의 그룹 규칙과 같아야 한다**
    (`parent/stem`) — 다르면 워터마크를 영영 못 찾아 전부 stale 로 보인다."""
    p = Path(source_file)
    return paths.context / f"{p.parent / p.stem}.md"


def latest_commit(paths: ProjectPaths, source_file: str) -> str:
    """그 소스의 컨텍스트 MD 에 찍힌 리비전. 없으면 `-1`."""
    if not source_file:
        return MISSING
    doc = context_doc_for(paths, source_file)
    try:
        return md_mod.read_source_commit(doc.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return MISSING


@dataclass
class DomainStale:
    domain: str
    changed: int = 0
    total: int = 0
    members: list = field(default_factory=list)     # (클래스, stored, latest) — 바뀐 것만

    @property
    def stale(self) -> bool:
        return self.changed > 0

    @property
    def reason(self) -> str:
        return f"stale={self.changed}/{self.total}"


def _members(paths: ProjectPaths, domain: str) -> dict:
    """도메인 멤버 → `{클래스: 소스파일}`.

    두 곳을 합친다 — **manifest 가 가리키는 object yaml**(우리 정본)과 **`class_ontology`
    분류 행**. 원본도 "MD 선언 ∪ 분류됨" 으로 합집합을 쓴다: 한쪽에만 있는 멤버를 놓치면
    그 클래스의 변경이 영영 stale 을 못 만든다.
    """
    out: dict = {}
    root = paths.ontology / "domains" / domain
    manifest = yaml_io.read(root / "domain.yaml") or {}
    for rel in manifest.get("objects") or []:
        obj = yaml_io.read(root / str(rel)) or {}
        name = obj.get("name")
        if name:
            out[name] = obj.get("file") or ""
    try:
        from ..graph import db as gdb
        if gdb.exists(paths):
            conn = gdb.connect(paths)
            try:
                rows = conn.execute(
                    "SELECT o.class_name, c.file FROM class_ontology o "
                    "LEFT JOIN classes c ON c.name = o.class_name "
                    "WHERE o.ontology_domain = ?", (domain,)).fetchall()
            finally:
                conn.close()
            for r in rows:
                out.setdefault(r["class_name"], r["file"] or "")
    except Exception:                                   # noqa: BLE001
        pass
    return out


def _stored(paths: ProjectPaths, domain: str, names: list) -> dict:
    """클래스별 `class_ontology.source_commit`. 없으면 `-1`."""
    out = {n: MISSING for n in names}
    try:
        from ..graph import db as gdb
        if not gdb.exists(paths) or not names:
            return out
        conn = gdb.connect(paths)
        try:
            marks = ",".join("?" * len(names))
            for r in conn.execute(
                    f"SELECT class_name, source_commit FROM class_ontology "
                    f"WHERE class_name IN ({marks})", tuple(names)):
                out[r["class_name"]] = r["source_commit"] or MISSING
        finally:
            conn.close()
    except Exception:                                   # noqa: BLE001
        pass
    return out


def active_domains(paths: ProjectPaths) -> list:
    """`status: active` 인 도메인. manifest 에 status 가 없으면 **active 로 본다** —
    받아온 스냅샷이 그 키를 안 쓴다(실측). draft 를 걸러내는 것이 목적이지 없는 키로
    전부 제외하는 것이 아니다."""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        m = yaml_io.read(d / "domain.yaml") or {}
        if str(m.get("status", "active")).lower() == "active":
            out.append(d.name)
    return out


def compute(paths: ProjectPaths, domains: list | None = None) -> list:
    """재합성이 필요한 도메인들. **stale 인 것만** 돌려준다."""
    out = []
    for domain in (domains if domains is not None else active_domains(paths)):
        members = _members(paths, domain)
        if not members:
            continue
        stored = _stored(paths, domain, list(members))
        st = DomainStale(domain=domain, total=len(members))
        for name, src in sorted(members.items()):
            s, l = stored.get(name, MISSING), latest_commit(paths, src)
            if s != l:
                st.changed += 1
                st.members.append((name, s, l))
        if st.stale:
            out.append(st)
    return out


def summary(results: list) -> str:
    if not results:
        return "stale 도메인 없음 — 재합성할 것이 없다"
    return " · ".join(f"{r.domain}({r.reason})" for r in results)
