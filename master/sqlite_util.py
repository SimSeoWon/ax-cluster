"""SQLite 멀티프로세스 동시성 PRAGMA — 한 자리에 모은다.

원전 `common.apply_sqlite_concurrency_pragmas` 이식(2026-06-05 실측 근거).

🔴 **왜 필요한가.** 우리 DB 는 **두 프로세스**가 연다 — 색인기(`master.events.consumer`, 쓰기)와
서비스(`master.projects`, 읽기). 기본 `busy_timeout=0` 이면 동시 쓰기에서 즉시
`database is locked` 가 나고, 상위 `log(skip)` 이 그것을 삼키면 **그 사이클 변경이 영구 유실**된다
(원전 실측 2026-06-05 — 그 사고가 이 헬퍼를 만든 계기다).

🔴 **왜 한 자리에 모으나.** 값(10초)이 세 곳에 흩어져 있으면 어긋난다. 실제로 2026-08-14 에
`graph/db.py`·`graph/dependency.py` 는 걸어 뒀는데 **`context_search/bm25.py` 만 빠져 있는 것**이
발견됐다 — `graph/db.py` 스스로 *"프로세스 간에는 WAL + busy_timeout 이 담당한다"* 고 적어 두고도
형제 모듈에서 빠뜨렸다. 복제는 그렇게 어긋난다.

⚠️ **원전이 명시적으로 기각한 것도 옮긴다**: *"`locked` 명시 재시도 루프는 미채택 —
`busy_timeout` 이 SQLite 네이티브 블록-후-재시도이고 WAL 이 읽기↔쓰기 경합을 제거(writer↔writer
직렬화만 남고 증분 쓰기는 ms 단위)라 별도 루프는 redundant."* 재시도 루프를 새로 만들지 말 것.

⚠️ `*.db-wal` / `*.db-shm` 은 **삭제 금지**(실행 중 삭제 시 미체크포인트 쓰기 유실). 모든 프로세스
종료 후에는 안전하나, 보통 종료 시 체크포인트로 본 DB 에 흡수된다 — 원전 `runbook.md` §4.
"""
from __future__ import annotations

import sqlite3

BUSY_TIMEOUT_MS = 10_000        # 🔴 원전 실측값 `SQLITE_BUSY_TIMEOUT_MS`. 바꾸려면 근거를 남길 것.


def apply(conn: sqlite3.Connection, *, synchronous: str = "") -> sqlite3.Connection:
    """프로세스 간 안전 PRAGMA 를 건다. 같은 연결을 돌려주므로 이어서 쓸 수 있다.

    `synchronous` 를 주면 그 값도 건다(기본은 건드리지 않는다 — DB 별 판단이 다르다).
    """
    conn.execute("PRAGMA journal_mode = WAL")      # 🔴 읽기와 쓰기가 서로 막지 않게
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")   # 🔴 쓰는 중이면 기다린다
    if synchronous:
        conn.execute(f"PRAGMA synchronous = {synchronous}")
    return conn


def check(conn: sqlite3.Connection) -> dict:
    """지금 걸려 있는 값을 읽어 온다 — 테스트·진단용."""
    jm = conn.execute("PRAGMA journal_mode").fetchone()
    bt = conn.execute("PRAGMA busy_timeout").fetchone()
    return {"journal_mode": (jm[0] if jm else "").lower(),
            "busy_timeout": int(bt[0]) if bt else 0}
