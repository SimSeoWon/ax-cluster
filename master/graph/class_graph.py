"""클래스 상속 그래프 — 풀 스캔·증분·질의 (소 1.1.3).

원본: `AgentTest/watcher/class_graph.py`. 저장 형태(`classes` + `methods`)와 질의
(recursive CTE) 는 그대로다.

[중요] **바꾼 것 세 개.**

⑴ **색인 대상은 `repo/Source/**` 뿐이다** (§5.2-E). 원본은 `git ls-files` 로 저장소 전체를
   훑었다. 우리는 `-- Source` 로 한정한다 — `Content/`(uasset, 워킹트리의 93%)를 파싱할
   이유가 없고, 색인기·소스 diff 도 같은 경계를 쓴다(`SOURCE_SUBDIR`).

⑵ **조용히 죽지 않는다.** 원본 `build_full` 은 tree-sitter 가 없거나 `git ls-files` 가
   실패하면 로그 한 줄 남기고 `return` 한다. 그러면 **"클래스가 없다" 와 "파서/깃이
   실패했다" 가 구분되지 않는다.** 여기서는 둘 다 예외다 — 색인기가 40초를 태워 빈
   그래프를 만들고 성공으로 보고하는 일을 막는다.

⑶ **dict 호환 API 를 옮기지 않았다.** 원본에는 `load_graph`/`save_graph`/`find_*(graph, ...)`
   의 dict 판이 SQLite 판과 나란히 있다 — 스모크 테스트와 외부 코드 호환을 위한 것이고,
   우리에겐 그 호환 대상이 없다. 필요해지면 그때 SQLite 판 위에 얹는다.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import source_text
from ..context_search.paths import ProjectPaths, SOURCE_SUBDIR
from . import db, parse

GIT_TIMEOUT = 60


class GraphError(RuntimeError):
    """그래프를 만들 수 없다. [중요] 삼키면 빈 그래프가 정상처럼 보인다."""


@dataclass
class BuildStats:
    """무엇을 얼마나 넣었는지. **분모를 같이 들고 다닌다.**

    [중요] `parsed` 와 `classes` 를 구분한다. `name` 이 PK 라 같은 클래스명이 여러 파일에
    나오면 `INSERT OR REPLACE` 로 **덮인다** — 파싱 건수를 그대로 "클래스 수" 라고 부르면
    DB 실제 건수보다 크게 보고된다(ModularStage 실측: 파싱 1,847 vs DB 1,806).
    그 차이 자체가 신호다 — 이름이 겹치는 클래스는 온톨로지에서 어느 쪽에 귀속할지
    모호해진다. 그래서 버리지 않고 `duplicate_names` 로 남긴다.
    """

    files: int = 0
    parsed: int = 0                # 파싱해 넣으려 한 건수 (덮어쓰기 포함)
    classes: int = 0              # 커밋 후 DB 실제 건수
    methods: int = 0
    dropped_rows: int = 0
    elapsed_ms: int = 0
    encodings: source_text.EncodingTally = field(default_factory=source_text.EncodingTally)

    @property
    def duplicate_names(self) -> int:
        """여러 파일에 같은 이름으로 나타나 덮인 건수."""
        return max(0, self.parsed - self.classes)

    @property
    def summary(self) -> str:
        s = (f"파일 {self.files} · 클래스 {self.classes} · 메서드 {self.methods} "
             f"· {self.elapsed_ms}ms")
        if self.duplicate_names:
            s += f" · [중요] 이름 중복 {self.duplicate_names}"
        if self.dropped_rows:
            s += f" (지운 행 {self.dropped_rows})"
        return f"{s} · {self.encodings.summary}"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, timeout=GIT_TIMEOUT)
    return p.returncode, (p.stdout or p.stderr).strip()


def list_source_files(paths: ProjectPaths, *, git=None) -> list[str]:
    """색인 대상 C++ 파일 — `repo/` 기준 상대 경로. **`Source/` 하위만** (§5.2-E).

    [중요] `git ls-files` 가 실패하면 예외다. 빈 리스트를 돌려주면 "소스가 없는 저장소" 와
    구분이 안 되고, 그 상태로 `build_full` 이 그래프를 0건으로 덮어쓴다.
    """
    run = git or _git
    if not paths.repo.is_dir():
        raise GraphError(f"소스 클론이 없다: {paths.repo}")
    rc, out = run(paths.repo, "ls-files", "--", SOURCE_SUBDIR)
    if rc != 0:
        raise GraphError(f"git ls-files 실패 (rc={rc}): {out[:200]}")
    # [중요] 경계를 **두 겹**으로 둔다. pathspec 하나에만 의존하면 §5.2-E 가 호출 방식에
    # 딸려 다니게 된다 — 인자를 한 번 잘못 넘기면 `Content/`(워킹트리의 93%)가 조용히
    # 들어온다. 접두 검사는 공짜다. (토큰 인증도 같은 이유로 ufw 와 두 겹이다)
    prefix = f"{SOURCE_SUBDIR}/"
    return [
        f for f in (line.strip().replace("\\", "/") for line in out.splitlines())
        if f.startswith(prefix) and Path(f).suffix.lower() in parse.PARSE_EXTS
    ]


def _entries_for(rel: str, paths: ProjectPaths,
                 tally: source_text.EncodingTally | None = None) -> dict[str, dict]:
    """한 파일 → `{클래스명: 정보}`. `file` 은 `repo/` 기준 상대 경로로 저장한다."""
    entries: dict[str, dict] = {}
    classes, decoded = parse.parse_file(paths.repo / rel)
    if tally is not None:
        tally.add(decoded)
    for c in classes:
        entries[c["name"]] = {
            "parent": c["parents"][0] if c["parents"] else "",
            "parents": c["parents"],
            "file": rel,
            "line": c["line"],
            "prefix": c["prefix"],
            "kind": c["kind"],
            "methods": c.get("methods", []),
        }
    return entries


def _upsert(conn, name: str, info: dict) -> int:
    conn.execute(
        "INSERT OR REPLACE INTO classes "
        "(name, parent, parents_json, file, line, prefix, kind) VALUES (?,?,?,?,?,?,?)",
        (name, info["parent"], json.dumps(info["parents"], ensure_ascii=False),
         info["file"], int(info["line"]), info["prefix"], info["kind"]),
    )
    for m in info.get("methods", []):
        conn.execute(
            "INSERT OR REPLACE INTO methods (class_name, method_name, file, line) "
            "VALUES (?,?,?,?)",
            (name, m["name"], info["file"], int(m.get("line", 0))),
        )
    return len(info.get("methods", []))


def build_full(paths: ProjectPaths, *, git=None, progress=None) -> BuildStats:
    """풀 스캔 → DB 전체 교체.

    `data-schema.md` 가 이 DB 의 복구 절차를 *"파일 삭제 → 재기동 시 풀 스캔"* 이라고
    적어 둔 그 풀 스캔이다. **한 트랜잭션**에서 지우고 다시 넣으므로, 중간에 실패하면
    이전 그래프가 그대로 남는다(세대 포인터와 같은 원칙 — 실패가 자산을 깨지 않는다).
    """
    parse.require()
    t0 = time.monotonic()
    files = list_source_files(paths, git=git)
    if not files:
        raise GraphError(
            f"`{SOURCE_SUBDIR}/` 에 C++ 파일이 없다 — 클론이 비었거나 경계가 틀렸다. "
            "빈 그래프로 덮지 않고 멈춘다."
        )
    stats = BuildStats(files=len(files))
    conn = db.connect(paths)
    try:
        with db.lock():
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM classes")       # methods 는 CASCADE 로 함께 지워진다
                for i, rel in enumerate(files, 1):
                    entries = _entries_for(rel, paths, stats.encodings)
                    for name, info in entries.items():
                        stats.methods += _upsert(conn, name, info)
                        stats.parsed += 1
                    if progress and i % 200 == 0:
                        progress(f"  {i}/{len(files)} — 클래스 {stats.parsed}")
                # 커밋 전에 실제 건수를 읽는다 — 파싱 건수와 다를 수 있다(위 docstring).
                stats.classes = int(conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0])
                stats.methods = int(conn.execute("SELECT COUNT(*) FROM methods").fetchone()[0])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
    stats.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return stats


def update_incremental(paths: ProjectPaths, changed: list[str]) -> BuildStats:
    """변경 파일만 갱신. 삭제된 파일은 **존재 여부로 스스로 감지**한다.

    `changed` 는 `repo/` 기준 상대 경로다(색인기가 `git diff --name-only ... -- Source`
    로 얻는 것과 같은 형태). 파싱 대상 확장자가 아니면 통째로 무시한다 — 빈 통계를
    돌려주므로 호출자가 "아무것도 안 했다" 를 볼 수 있다.
    """
    parse.require()
    relevant = [f for f in changed if Path(f).suffix.lower() in parse.PARSE_EXTS]
    stats = BuildStats(files=len(relevant))
    if not relevant:
        return stats
    t0 = time.monotonic()
    alive = [f for f in relevant if (paths.repo / f).is_file()]
    conn = db.connect(paths)
    try:
        with db.lock():
            conn.execute("BEGIN")
            try:
                # 변경·삭제 파일에 속했던 기존 행을 먼저 지운다 — 파일에서 사라진 클래스가
                # 유령으로 남는 것을 막는다.
                marks = ",".join("?" * len(relevant))
                cur = conn.execute(f"DELETE FROM classes WHERE file IN ({marks})",
                                   tuple(f.replace("\\", "/") for f in relevant))
                stats.dropped_rows = cur.rowcount or 0
                for rel in alive:
                    for name, info in _entries_for(rel, paths, stats.encodings).items():
                        stats.methods += _upsert(conn, name, info)
                        stats.parsed += 1
                stats.classes = stats.parsed   # 증분은 전체 건수가 아니라 넣은 건수를 센다
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
    stats.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return stats


# ── 질의 ──────────────────────────────────────────────────────────
# 모두 SQLite 직접 질의다. 자손은 `parent` 컬럼의 recursive CTE, 조상은 다중 상속을 살리기
# 위해 `parents_json` 을 펼친다 — 원본의 비대칭을 그대로 유지한다(자손 탐색에서 다중 상속의
# 두 번째 부모까지 타면 UE 인터페이스 때문에 결과가 폭발한다).

def find_subclasses(paths: ProjectPaths, parent: str, max_depth: int = -1) -> list[str]:
    if not db.exists(paths):
        return []
    conn = db.connect(paths)
    try:
        if max_depth <= 0:
            sql = """WITH RECURSIVE subs(name, depth) AS (
                       SELECT name, 1 FROM classes WHERE parent = ?
                       UNION
                       SELECT c.name, s.depth + 1 FROM classes c JOIN subs s ON c.parent = s.name)
                     SELECT DISTINCT name FROM subs ORDER BY depth, name"""
            args: tuple = (parent,)
        else:
            sql = """WITH RECURSIVE subs(name, depth) AS (
                       SELECT name, 1 FROM classes WHERE parent = ?
                       UNION
                       SELECT c.name, s.depth + 1 FROM classes c JOIN subs s ON c.parent = s.name
                       WHERE s.depth < ?)
                     SELECT DISTINCT name FROM subs ORDER BY depth, name"""
            args = (parent, max_depth)
        return [r["name"] for r in conn.execute(sql, args)]
    finally:
        conn.close()


def find_ancestors(paths: ProjectPaths, class_name: str, max_depth: int = -1) -> list[str]:
    if not db.exists(paths):
        return []
    conn = db.connect(paths)
    try:
        result: list[str] = []
        visited: set[str] = set()
        frontier = [class_name]
        depth = 0
        while frontier:
            depth += 1
            if max_depth > 0 and depth > max_depth:
                break
            marks = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"SELECT parents_json FROM classes WHERE name IN ({marks})", tuple(frontier)
            ).fetchall()
            nxt: list[str] = []
            for row in rows:
                try:
                    parents = json.loads(row["parents_json"]) or []
                except (TypeError, ValueError):
                    parents = []
                for p in parents:
                    if p and p not in visited:
                        visited.add(p)
                        result.append(p)
                        nxt.append(p)
            frontier = nxt
        return result
    finally:
        conn.close()


def find_siblings(paths: ProjectPaths, class_name: str) -> list[str]:
    """상속 목록이 **완전히 같은** 다른 클래스. 부분 일치는 형제로 보지 않는다."""
    if not db.exists(paths):
        return []
    conn = db.connect(paths)
    try:
        row = conn.execute("SELECT parents_json FROM classes WHERE name = ?",
                           (class_name,)).fetchone()
        if not row:
            return []
        try:
            if not json.loads(row["parents_json"] or "[]"):
                return []
        except (TypeError, ValueError):
            return []
        return [r["name"] for r in conn.execute(
            "SELECT name FROM classes WHERE parents_json = ? AND name != ? ORDER BY name",
            (row["parents_json"], class_name))]
    finally:
        conn.close()


def methods_ready(paths: ProjectPaths) -> bool:
    """`methods` 에 한 건이라도 있는지.

    [중요] **`method_belongs_to_class` 를 부르기 전에 반드시 이걸 통과시켜야 한다.** 테이블이
    비었을 때 곧이곧대로 물으면 **전부 "없다"** 가 나와, 오탐 교차검증이 오히려 전수
    거짓양성을 만든다. 원본이 같은 이유로 이 게이트를 두었다.
    """
    if not db.exists(paths):
        return False
    conn = db.connect(paths)
    try:
        return conn.execute("SELECT 1 FROM methods LIMIT 1").fetchone() is not None
    finally:
        conn.close()


def method_belongs_to_class(paths: ProjectPaths, class_name: str, method_name: str,
                            *, include_ancestors: bool = True) -> bool:
    """그 클래스(또는 조상)가 헤더에서 그 메서드를 실제로 선언했는지. 이름 레벨 매칭.

    `include_ancestors` 기본 True — 부모가 선언하고 자식이 override 없이 쓰는 것이 UE 에서
    흔한 패턴이라, 그걸 부정하면 정당한 귀속까지 오탐으로 잡는다.
    """
    if not class_name or not method_name or not db.exists(paths):
        return False
    conn = db.connect(paths)
    try:
        hit = conn.execute(
            "SELECT 1 FROM methods WHERE class_name = ? AND method_name = ? LIMIT 1",
            (class_name, method_name)).fetchone() is not None
    finally:
        conn.close()
    if hit or not include_ancestors:
        return hit
    ancestors = find_ancestors(paths, class_name)
    if not ancestors:
        return False
    conn = db.connect(paths)
    try:
        marks = ",".join("?" * len(ancestors))
        return conn.execute(
            f"SELECT 1 FROM methods WHERE method_name = ? AND class_name IN ({marks}) LIMIT 1",
            (method_name, *ancestors)).fetchone() is not None
    finally:
        conn.close()
