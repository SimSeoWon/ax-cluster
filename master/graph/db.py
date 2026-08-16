"""클래스 그래프 SQLite 코어 — 스키마·연결 (소 1.1.2, 소 1.1.4).

원본: `AgentTest/watcher/class_graph_db.py`.

[중요] **바꾼 것 세 개.**

⑴ **위치** — 원본은 `<UE프로젝트>/.claude/vector_db/class_graph.db` 였다. 여기는
   `<Name>/class_graph.db` 다(`paths.class_graph_db`). 이유는 §5.5.2 — 경로가 상수가 아니라
   함수이고, 프로젝트 디렉토리가 갈리므로 프로젝트끼리 섞이지 않는다.

⑵ **마이그레이션 없음** — 원본에는 ① `.claude/class_graph.json` 레거시 import ②
   `class_ontology` 의 `ALTER TABLE`(ontology_layer·verified_by_layer·source_commit) 이 있다.
   둘 다 **기존 배포본을 올려붙이기 위한 것**이고 우리는 DB 를 처음부터 만든다. 대신
   **스키마를 처음부터 완성형으로 둔다** — `domains`·`class_ontology` 까지 만들어 두면
   중 1.3(온톨로지 합성)·소 2.2.2(질의→도메인 추론)가 나중에 스키마를 고칠 필요가 없다.
   빈 `class_ontology` 는 원본의 구 DB 호환 경로와 같은 결과(빈 추론)를 낸다.

⑶ **동시성 PRAGMA 를 명시한다** — 원본은 `common.apply_sqlite_concurrency_pragmas` 에
   위임했다. [중요] 여기서 이게 더 중요하다: 색인기(`ax-indexer.service`)와 검색기가 **별개
   프로세스**라 같은 파일을 동시에 연다. 세대 포인터를 메모리에만 두어 새 프로세스가
   `count()==0` 을 본 사고(→ `context_search/generation.py`)와 같은 계열의 함정이다.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .. import sqlite_util
from ..context_search.paths import ProjectPaths

# 스키마는 완성형이다 — 위 ⑵ 참조. `IF NOT EXISTS` 라 멱등이다.
SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
    name         TEXT PRIMARY KEY,
    parent       TEXT NOT NULL DEFAULT '',   -- parents[0]. recursive CTE 가 이 컬럼을 탄다
    parents_json TEXT NOT NULL DEFAULT '[]', -- 다중 상속 전체
    file         TEXT NOT NULL DEFAULT '',   -- repo/ 기준 상대 경로 (`Source/...`)
    line         INTEGER NOT NULL DEFAULT 0,
    prefix       TEXT NOT NULL DEFAULT '',
    kind         TEXT NOT NULL DEFAULT 'class'
);
CREATE INDEX IF NOT EXISTS idx_classes_parent ON classes(parent);
CREATE INDEX IF NOT EXISTS idx_classes_file   ON classes(file);

-- 소 1.1.4 — 메서드 소유권. SSOT 는 헤더 선언이다. 온톨로지 추출의 **오탐 교차검증용**
-- 이고, 오버로드는 이름 레벨로만 구분한다.
CREATE TABLE IF NOT EXISTS methods (
    class_name  TEXT NOT NULL,
    method_name TEXT NOT NULL,
    file        TEXT NOT NULL DEFAULT '',
    line        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (class_name, method_name),
    FOREIGN KEY (class_name) REFERENCES classes(name) ON DELETE CASCADE
);

-- 여기부터는 중 1.3(온톨로지)이 채운다. 지금은 비어 있고, 비어 있어도 검색은 돈다.
CREATE TABLE IF NOT EXISTS domains (
    name        TEXT PRIMARY KEY,
    tier        INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS class_ontology (
    class_name        TEXT PRIMARY KEY,
    ontology_kind     TEXT,                               -- Object/Function/null
    ontology_tier     INTEGER,                            -- 1~4/null
    ontology_domain   TEXT,                               -- domains.name (nullable)
    confidence        REAL NOT NULL DEFAULT 0.0,
    verified_by_user  INTEGER NOT NULL DEFAULT 0,
    rationale         TEXT NOT NULL DEFAULT '',
    classified_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ontology_layer    INTEGER,                            -- L1/L2/L3 (소 1.3.5 가 추정)
    verified_by_layer INTEGER NOT NULL DEFAULT 0,         -- layer 잠금 (tier 검수와 직교)
    source_commit     TEXT,                               -- [중요] stale 판정의 한쪽 (소 1.3.8)
    FOREIGN KEY (class_name)      REFERENCES classes(name) ON DELETE CASCADE,
    FOREIGN KEY (ontology_domain) REFERENCES domains(name) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_class_ontology_domain ON class_ontology(ontology_domain);
CREATE INDEX IF NOT EXISTS idx_class_ontology_tier   ON class_ontology(ontology_tier);
CREATE INDEX IF NOT EXISTS idx_class_ontology_kind   ON class_ontology(ontology_kind);
CREATE INDEX IF NOT EXISTS idx_class_ontology_layer  ON class_ontology(ontology_layer);
"""

# 같은 프로세스 안의 쓰기 직렬화. 프로세스 간에는 아래 WAL + busy_timeout 이 담당한다.
_LOCK = threading.RLock()


def lock() -> threading.RLock:
    return _LOCK


def connect(paths: ProjectPaths) -> sqlite3.Connection:
    """연결 + 스키마 보장. **멱등**이라 아무 때나 불러도 된다."""
    paths.class_graph_db.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False — FastAPI 워커 스레드에서도 읽는다.
    # isolation_level=None — 트랜잭션 경계를 우리가 BEGIN/COMMIT 으로 명시한다.
    conn = sqlite3.connect(str(paths.class_graph_db), check_same_thread=False,
                           isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")      # methods/class_ontology 의 CASCADE 를 위해
    # [중요] 값은 `master/sqlite_util.py` 가 단일 소유 — 세 곳에 흩어져 있다가
    #    bm25 에서만 빠진 것이 2026-08-14 에 발견됐다.
    sqlite_util.apply(conn, synchronous="NORMAL")
    try:
        conn.executescript(SCHEMA)
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def exists(paths: ProjectPaths) -> bool:
    """DB 파일이 있는지. **내용은 보지 않는다** — `count` 와 구분한다."""
    return paths.class_graph_db.is_file()


def counts(paths: ProjectPaths) -> dict[str, int]:
    """테이블별 건수. `data-schema.md` 기준 이 DB 는 **삭제하면 풀 스캔으로 되살아난다** —
    그래서 여기서 하는 보고는 "복구가 필요한가" 가 아니라 "지금 몇 건인가" 다.
    """
    if not exists(paths):
        return {"classes": 0, "methods": 0, "domains": 0, "class_ontology": 0}
    conn = connect(paths)
    try:
        return {
            t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
            for t in ("classes", "methods", "domains", "class_ontology")
        }
    finally:
        conn.close()
