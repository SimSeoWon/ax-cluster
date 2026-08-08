"""BM25 키워드 채널 — SQLite FTS5 (AgentTest `bm25_index.py` 이식).

벡터 검색의 약점을 메우는 채널이다. **정확한 식별자**(`UWNDUIViewManager`)와
**한국어 어절**은 임베딩이 뭉개는데, BM25 는 그대로 잡는다. 둘을 RRF 로 섞는다(`search.py`).

**원본에서 그대로 가져온 것 — 건드리면 점수가 어긋난다:**

- `_TOKEN_RE` — 코드 식별자와 한글을 토큰으로 나눈다
- 필드 가중치 (tags 3.0 / related_classes 2.5 / category 1.5 / body 1.0)
- `unicode61 remove_diacritics 0 tokenchars '_'` — `_` 를 토큰 문자로 살려 `class_name` 보존
- 사전 토큰화 후 공백으로 이어 붙여 저장하는 방식 (FTS5 토크나이저를 사실상 공백 분할로 씀)

**바꾼 것:**

- 구 4컬럼 스키마 마이그레이션을 뺐다 — 이 저장소에는 마이그레이션할 옛 DB가 없다.
  없는 과거를 위한 코드는 검증할 수도 없다.
- 테이블을 **세대별로 둘(`bm25_a`/`bm25_b`)** 로 나눴다. 원본은 제자리에서 지우고 다시
  채우는데(`clear()` → `build()`), 프로세스가 갈린 여기서는 그 사이 검색이 **반쯤 지어진
  색인**을 보게 된다. 세대를 나누면 재색인 내내 옛 세대가 온전히 살아 있다 (`generation.py`).
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from . import generation
from .documents import Document, iter_documents
from .paths import ProjectPaths

# 원본과 동일. 바꾸면 기존 색인과 순위가 어긋난다.
TAGS_BOOST = 3.0
CATEGORY_BOOST = 1.5
RELATED_CLASSES_BOOST = 2.5  # 식별자 정확 매칭 — tags 다음으로 강한 신호
BODY_BOOST = 1.0

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[가-힣]+")

# 사전 토큰화된 공백 구분 스트림을 받는다. tokenchars '_' 로 `class_name` 식별자 보존.
_FTS5_TOKENIZE = "unicode61 remove_diacritics 0 tokenchars '_'"


def tokenize(text: str) -> list[str]:
    """코드 식별자(영문/숫자/언더스코어)와 한국어 어절을 토큰으로 분리. **원본 그대로.**"""
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _fts5_available() -> bool:
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
            return True
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return False


FTS5_AVAILABLE = _fts5_available()


def class_names(related_classes) -> list[str]:
    """`related_classes` 에서 **클래스명만** 뽑는다.

    값(파일 경로)은 쓰지 않는다 — 디렉토리 토큰이 섞여 색인을 오염시킨다. 원본과 같다.
    """
    rc = related_classes
    if not rc:
        return []
    if isinstance(rc, dict):
        names = list(rc.keys())
        for v in rc.values():
            if isinstance(v, dict):
                names.extend(v.keys())
        return [str(n) for n in names if n]
    if isinstance(rc, list):
        return [str(n) for n in rc if n]
    if isinstance(rc, str):
        return [rc]
    return []


def _fields(doc: Document) -> tuple[str, str, str, str]:
    """문서 → (tags, category, related_classes, body) 의 사전 토큰화 텍스트."""
    fm = doc.fm
    tags = " ".join(tokenize(" ".join(fm.get("tags") or [])))
    cat = " ".join(tokenize(str(fm.get("category") or "")))
    rc = " ".join(tokenize(" ".join(class_names(fm.get("related_classes")))))
    # 🔴 `search_text` 를 쓴다 — 본문 없는 스텁도 색인한다 (`documents.py` 참조).
    body = " ".join(tokenize(doc.search_text))
    return tags, cat, rc, body


def _table(gen: str) -> str:
    return f"bm25_{gen}"


class Bm25Index:
    """한 프로젝트의 BM25 색인. 세대 포인터는 벡터 색인과 **공유한다**."""

    def __init__(self, paths: ProjectPaths, *, gen: str | None = None):
        self.paths = paths
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        if not FTS5_AVAILABLE:
            # 조용히 빈 채널로 떨어진다 — 검색은 벡터만으로도 답을 낸다.
            self._gen = generation.A
            return
        paths.bm25_db.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False — FastAPI 워커 스레드에서 검색을 부른다.
        self._conn = sqlite3.connect(str(paths.bm25_db), check_same_thread=False)
        # 첫 검색 콜드미스(~200ms) 회피. 원본과 같은 값.
        self._conn.execute("PRAGMA mmap_size = 67108864")   # 64MB OS-level mmap
        self._conn.execute("PRAGMA cache_size = -8000")     # 8MB SQLite 캐시
        self._conn.execute("PRAGMA temp_store = MEMORY")
        for g in (generation.A, generation.B):
            self._create(g)
        self._conn.commit()
        self._gen = gen or generation.read(paths.root) or self._probe()

    def _create(self, gen: str) -> None:
        self._conn.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS {_table(gen)} USING fts5(
                file_id UNINDEXED,
                tags,
                category,
                related_classes,
                body,
                tokenize = "{_FTS5_TOKENIZE}"
            )"""
        )

    def _probe(self) -> str:
        """마커 유실 — 실제로 문서가 많은 세대를 고른다. 둘 다 비었으면 `a`."""
        return generation.B if self._count(generation.B) > self._count(generation.A) else generation.A

    # ── 조회 ──────────────────────────────────────────
    @property
    def gen(self) -> str:
        return self._gen

    def _count(self, gen: str) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            return int(self._conn.execute(f"SELECT COUNT(*) FROM {_table(gen)}").fetchone()[0])

    def count(self) -> int:
        return self._count(self._gen)

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """FTS5 MATCH + 컬럼 가중치. `(file_id, score)` 내림차순.

        FTS5 의 `bm25()` 는 **음수**를 돌려준다(작을수록 좋은 매칭). 부호를 뒤집어
        "큰 값 = 좋은 매칭" 으로 맞춘다 — 원본과 같은 관행이고, RRF 가 순위만 쓰므로
        절대값은 중요하지 않지만 **정렬 방향이 뒤집히면 조용히 최악의 결과를 준다.**
        """
        if self._conn is None:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        # 토큰을 따옴표로 감싼다 — FTS5 예약어(AND/OR/NOT/NEAR) 충돌 방지.
        match = " OR ".join(f'"{t}"' for t in tokens)
        try:
            with self._lock:
                rows = self._conn.execute(
                    f"""SELECT file_id,
                               -bm25({_table(self._gen)}, 0.0, {TAGS_BOOST}, {CATEGORY_BOOST},
                                     {RELATED_CLASSES_BOOST}, {BODY_BOOST}) AS score
                        FROM {_table(self._gen)}
                        WHERE {_table(self._gen)} MATCH ?
                        ORDER BY score DESC
                        LIMIT ?""",
                    (match, limit),
                ).fetchall()
            return [(r[0], float(r[1])) for r in rows]
        except sqlite3.OperationalError:
            return []

    # ── 갱신 ──────────────────────────────────────────
    def rebuild_into(self, gen: str, *, progress=None) -> int:
        """`gen` 세대를 통째로 다시 채운다. **Live 세대는 건드리지 않는다.**"""
        if self._conn is None:
            return 0
        total = 0
        with self._lock:
            self._conn.execute(f"DELETE FROM {_table(gen)}")
            rows = []
            for doc in iter_documents(self.paths.context):
                rows.append((doc.file_id, *_fields(doc)))
                if len(rows) >= 500:
                    self._insert(gen, rows)
                    total += len(rows)
                    rows = []
                    if progress:
                        progress(total)
            if rows:
                self._insert(gen, rows)
                total += len(rows)
            self._conn.commit()
        if progress:
            progress(total)
        return total

    def _insert(self, gen: str, rows: list[tuple]) -> None:
        self._conn.executemany(
            f"INSERT INTO {_table(gen)} (file_id, tags, category, related_classes, body) "
            f"VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    def upsert(self, docs: list[Document]) -> int:
        """증분 갱신 — Live 세대에 직접 쓴다(벡터 쪽 `upsert()` 와 같은 판단)."""
        if self._conn is None or not docs:
            return 0
        t = _table(self._gen)
        with self._lock:
            for d in docs:
                self._conn.execute(f"DELETE FROM {t} WHERE file_id = ?", (d.file_id,))
            self._insert(self._gen, [(d.file_id, *_fields(d)) for d in docs])
            self._conn.commit()
        return len(docs)

    def remove(self, file_ids: list[str]) -> int:
        if self._conn is None or not file_ids:
            return 0
        t = _table(self._gen)
        with self._lock:
            cur = self._conn.executemany(
                f"DELETE FROM {t} WHERE file_id = ?", [(f,) for f in file_ids]
            )
            self._conn.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def use_generation(self, gen: str) -> None:
        """세대 전환 — **마커는 쓰지 않는다.** 두 채널을 함께 뒤집는 쪽(`rebuild.py`)의 몫이다."""
        with self._lock:
            self._gen = gen

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None
