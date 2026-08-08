"""`#include` 의존 그래프 (소 1.1.5).

원본: `AgentTest/watcher/dependency.py`. LLM 을 쓰지 않는다 — 정규식 하나와 `git ls-files`
뿐이라 커밋 즉시 돌 수 있다.

🔴 **알고 써야 하는 근사 — `included_by` 는 경로가 아니라 파일명으로 역산한다.**

`#include "Foo.h"` 의 경로는 UBT 가 모듈별 include 디렉토리로 해석한다. 그 정보 없이는
정확히 어느 `Foo.h` 인지 알 수 없어서, 원본은 **basename 이 같으면 전부 연결**한다.
같은 이름 헤더가 두 모듈에 있으면 **없는 간선이 생긴다.**

실측(ModularStage, 2026-08-08): 소스 1,662개 중 **basename 이 겹치는 헤더 9종**(각 2개).
작지만 0 이 아니다 — 그래서 버리지 않고 `BuildStats.ambiguous_basenames` 로 **보고한다.**
소비자(영향도 질의)는 이 숫자를 보고 결과를 의심할 수 있어야 한다.

🔴 **바꾼 것 넷.**

⑴ **위치** `<Name>/dependency_graph.db` · **`Source/` 한정** (§5.2-E) — 원본은 저장소 전체를
   훑었다. 경계는 pathspec + 접두 **두 겹**이다(`class_graph` 와 같은 이유).
⑵ **fail-closed** — git 실패·소스 0건은 예외다. 원본은 빈 dict 를 돌려줘서 "의존이 없다" 와
   "스캔이 실패했다" 가 구분되지 않았다.
⑶ **질의를 SQL 로 한다.** 원본 `get_dependents`/`get_dependencies` 는 **매 호출마다 그래프
   전체를 dict 로 적재**하고 파이썬에서 순회한다. `get_dependencies` 는 의존마다 전체 키를
   다시 훑어 **O(N·M)** 이다. 여기서는 `dst_base` 컬럼에 인덱스를 걸어 한 번의 인덱스 질의로
   끝낸다 — 의미는 같고(같은 basename 매칭) 전체 적재가 없다.
⑷ **마이그레이션(레거시 JSON) 미이식** — 우리는 DB 를 처음부터 만든다.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .. import source_text
from ..context_search.paths import ProjectPaths, SOURCE_SUBDIR
from .class_graph import GraphError, _git

_INCLUDE_RE = re.compile(r'#include\s+"([^"]+)"')

# 원본과 같은 집합을 유지한다. `.cs`(UBT Build.cs)·`.py` 는 `#include` 가 없어 간선 0 으로
# 남지만, `files` 에 등록해 두면 "추적 대상인데 의존이 없다" 와 "추적조차 안 한다" 가
# 구분된다 — 영향도 질의에서 그 구분이 필요하다.
TARGET_EXTS = {".cpp", ".h", ".hpp", ".inl", ".cs", ".py"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    name TEXT PRIMARY KEY               -- repo/ 기준 상대 경로 (`Source/...`)
);
CREATE TABLE IF NOT EXISTS includes (
    src_file TEXT NOT NULL,             -- 포함하는 쪽 (경로)
    dst_file TEXT NOT NULL,             -- `#include "..."` 원문 그대로
    dst_base TEXT NOT NULL,             -- dst_file 의 basename. 🔴 역방향 질의의 실제 키다
    PRIMARY KEY (src_file, dst_file)
);
CREATE INDEX IF NOT EXISTS idx_includes_src  ON includes(src_file);
CREATE INDEX IF NOT EXISTS idx_includes_base ON includes(dst_base);
"""

_LOCK = threading.RLock()


@dataclass
class BuildStats:
    files: int = 0
    edges: int = 0
    dropped_edges: int = 0
    elapsed_ms: int = 0
    ambiguous_basenames: int = 0     # 🔴 위 docstring — 근사가 틀릴 수 있는 범위

    @property
    def summary(self) -> str:
        s = f"파일 {self.files} · 간선 {self.edges} · {self.elapsed_ms}ms"
        if self.ambiguous_basenames:
            s += f" · ⚠️ 이름 겹치는 헤더 {self.ambiguous_basenames}종 (역방향 근사)"
        if self.dropped_edges:
            s += f" (지운 간선 {self.dropped_edges})"
        return s


def _base(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def connect(paths: ProjectPaths) -> sqlite3.Connection:
    paths.dependency_graph_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(paths.dependency_graph_db), check_same_thread=False,
                           isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")     # 색인기와 검색기가 별개 프로세스다
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        conn.executescript(SCHEMA)
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def exists(paths: ProjectPaths) -> bool:
    return paths.dependency_graph_db.is_file()


def counts(paths: ProjectPaths) -> dict[str, int]:
    if not exists(paths):
        return {"files": 0, "includes": 0}
    conn = connect(paths)
    try:
        return {t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
                for t in ("files", "includes")}
    finally:
        conn.close()


def parse_includes(file_path: Path) -> list[str]:
    """`#include "..."` 만 뽑는다. `<...>` 는 엔진/표준 헤더라 트윈 밖이다.

    include 경로는 ASCII 라 인코딩에 무관하지만, 읽기는 공용 경로를 쓴다 —
    CP949 파일에서 `UnicodeDecodeError` 로 파일 전체를 놓치는 일이 없게 한다.
    """
    d = source_text.read(file_path)
    if d is None:
        return []
    return [inc.replace("\\", "/") for inc in _INCLUDE_RE.findall(d.text)]


def list_source_files(paths: ProjectPaths, *, git=None) -> list[str]:
    """추적 대상 — `repo/Source/**` 의 `TARGET_EXTS`. 경계는 두 겹이다 (§5.2-E)."""
    run = git or _git
    if not paths.repo.is_dir():
        raise GraphError(f"소스 클론이 없다: {paths.repo}")
    rc, out = run(paths.repo, "ls-files", "--", SOURCE_SUBDIR)
    if rc != 0:
        raise GraphError(f"git ls-files 실패 (rc={rc}): {out[:200]}")
    prefix = f"{SOURCE_SUBDIR}/"
    return [f for f in (ln.strip().replace("\\", "/") for ln in out.splitlines())
            if f.startswith(prefix) and Path(f).suffix.lower() in TARGET_EXTS]


def _count_ambiguous(files: list[str]) -> int:
    """basename 이 둘 이상인 것의 종류 수. 역방향 간선이 틀릴 수 있는 범위다."""
    seen: dict[str, int] = {}
    for f in files:
        if Path(f).suffix.lower() in {".h", ".hpp", ".inl"}:
            seen[_base(f)] = seen.get(_base(f), 0) + 1
    return sum(1 for n in seen.values() if n > 1)


def build_full(paths: ProjectPaths, *, git=None, progress=None) -> BuildStats:
    """풀 스캔 → 전체 교체. 한 트랜잭션이라 실패하면 이전 그래프가 남는다."""
    t0 = time.monotonic()
    files = list_source_files(paths, git=git)
    if not files:
        raise GraphError(
            f"`{SOURCE_SUBDIR}/` 에 추적 대상 파일이 없다 — 클론이 비었거나 경계가 틀렸다. "
            "빈 그래프로 덮지 않고 멈춘다."
        )
    stats = BuildStats(files=len(files), ambiguous_basenames=_count_ambiguous(files))
    conn = connect(paths)
    try:
        with _LOCK:
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM includes")
                conn.execute("DELETE FROM files")
                for i, rel in enumerate(files, 1):
                    conn.execute("INSERT OR IGNORE INTO files (name) VALUES (?)", (rel,))
                    for inc in parse_includes(paths.repo / rel):
                        conn.execute(
                            "INSERT OR IGNORE INTO includes (src_file, dst_file, dst_base) "
                            "VALUES (?,?,?)", (rel, inc, _base(inc)))
                    if progress and i % 400 == 0:
                        progress(f"  {i}/{len(files)}")
                stats.edges = int(conn.execute("SELECT COUNT(*) FROM includes").fetchone()[0])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
    stats.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return stats


def update_incremental(paths: ProjectPaths, changed: list[str]) -> BuildStats:
    """변경 파일의 간선만 다시 만든다. 사라진 파일은 `files` 에서도 뺀다."""
    relevant = [f.replace("\\", "/") for f in changed
                if Path(f).suffix.lower() in TARGET_EXTS]
    stats = BuildStats(files=len(relevant))
    if not relevant:
        return stats
    t0 = time.monotonic()
    conn = connect(paths)
    try:
        with _LOCK:
            conn.execute("BEGIN")
            try:
                for rel in relevant:
                    cur = conn.execute("DELETE FROM includes WHERE src_file = ?", (rel,))
                    stats.dropped_edges += cur.rowcount or 0
                    if (paths.repo / rel).is_file():
                        conn.execute("INSERT OR IGNORE INTO files (name) VALUES (?)", (rel,))
                        for inc in parse_includes(paths.repo / rel):
                            conn.execute(
                                "INSERT OR IGNORE INTO includes (src_file, dst_file, dst_base) "
                                "VALUES (?,?,?)", (rel, inc, _base(inc)))
                            stats.edges += 1
                    else:
                        conn.execute("DELETE FROM files WHERE name = ?", (rel,))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
    stats.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return stats


# ── 질의 ──────────────────────────────────────────────────────────
# 전체 적재 없이 인덱스 질의로 한 단계씩 넓힌다. `depth` 는 원본과 같은 의미다 —
# `depth=1` 이면 직접 관계만, `depth=2` 면 한 다리 건너까지.

def dependents(paths: ProjectPaths, file_path: str, depth: int = 2) -> list[str]:
    """이 파일을 `#include` 하는 쪽 (역방향). 🔴 basename 매칭 근사다 — 위 docstring."""
    if not exists(paths):
        return []
    conn = connect(paths)
    try:
        result: list[str] = []
        visited = {file_path.replace("\\", "/")}
        frontier = [file_path.replace("\\", "/")]
        for _ in range(max(0, depth)):
            if not frontier:
                break
            marks = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"SELECT DISTINCT src_file FROM includes WHERE dst_base IN ({marks})",
                tuple(_base(f) for f in frontier)).fetchall()
            nxt = [r["src_file"] for r in rows if r["src_file"] not in visited]
            visited.update(nxt)
            result.extend(nxt)
            frontier = nxt
        return result
    finally:
        conn.close()


def dependencies(paths: ProjectPaths, file_path: str, depth: int = 2) -> list[str]:
    """이 파일이 `#include` 하는 쪽 (정방향). 추적 대상 안에 있는 것만 돌려준다 —
    엔진 헤더는 `files` 에 없으므로 자연히 빠진다."""
    if not exists(paths):
        return []
    conn = connect(paths)
    try:
        result: list[str] = []
        visited = {file_path.replace("\\", "/")}
        frontier = [file_path.replace("\\", "/")]
        for _ in range(max(0, depth)):
            if not frontier:
                break
            marks = ",".join("?" * len(frontier))
            # dst_file 은 include 원문이라 경로가 부분적이다 → basename 으로 실제 파일에 붙인다.
            rows = conn.execute(
                f"""SELECT DISTINCT f.name FROM includes i
                    JOIN files f ON f.name = i.dst_file
                                 OR f.name LIKE '%/' || i.dst_base
                    WHERE i.src_file IN ({marks})""", tuple(frontier)).fetchall()
            nxt = [r["name"] for r in rows if r["name"] not in visited]
            visited.update(nxt)
            result.extend(nxt)
            frontier = nxt
        return result
    finally:
        conn.close()
