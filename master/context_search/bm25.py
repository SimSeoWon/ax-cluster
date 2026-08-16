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

from .. import sqlite_util

# 원본과 동일. 바꾸면 기존 색인과 순위가 어긋난다.
TAGS_BOOST = 3.0
CATEGORY_BOOST = 1.5
RELATED_CLASSES_BOOST = 2.5  # 식별자 정확 매칭 — tags 다음으로 강한 신호
BODY_BOOST = 1.0

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[가-힣]+")

# 사전 토큰화된 공백 구분 스트림을 받는다. tokenchars '_' 로 `class_name` 식별자 보존.
_FTS5_TOKENIZE = "unicode61 remove_diacritics 0 tokenchars '_'"

# [중요] **한글 전용 보조 테이블의 토크나이저.** SQLite 내장 `trigram` — 3자 창으로 쪼개므로
# 조사·어미가 붙어도 부분 문자열이 걸린다. 실측(SQLite 3.37.2):
#
#   trigram    MATCH '시스템' → 1건   ← 「시스템을 관리하는」 안에서 잡힌다
#   unicode61  MATCH '시스템' → 0건   ← 형태소 분석이 없어 못 잡는다
#
# **전체를 trigram 으로 바꾸지 않는 이유**: 식별자(`GlobalEventSystem`)도 3자 창으로
# 쪼개지면 정확 매칭의 이점이 사라지고 IDF 통계가 흔들려 **지금 잘 되는 영문이 나빠진다.**
# 그래서 테이블을 나누고 질의 언어로 고른다.
_FTS5_TOKENIZE_KR = "trigram"

# trigram 은 3자 미만을 매칭할 수 없다 — 그런 토큰은 이 채널에서 버린다(단어 테이블이 받는다).
KR_MIN_LEN = 3
_HANGUL_RE = re.compile(r"[가-힣]")

# [중요] **한글 질의 라우팅은 기본 꺼져 있다** (`AX_BM25_KR=1` 로 켠다).
#
# 표(색인)는 만든다 — trigram 이 **단독으로는 확실히 맞다**(실측: 질의 「전역 이벤트 시스템」에
# 대해 `GlobalEventSystem.md` 를 1위로. 단어 테이블은 3위).
#
# 그런데 **끝단 검색 품질은 나아지지 않았다.** 세 가지를 시도했다 — ⑴ 부족할 때만 채우기
# (효과 0: 단어 테이블이 limit 을 채워 trigram 이 조회조차 안 됨) ⑵ 순위 교차(더 나빠짐)
# ⑶ 한글 질의는 trigram 단독(그래도 안 나아짐).
#
# **원인은 BM25 가 아니라 RRF 융합에 있다.** RRF 는 두 채널이 **동의**하면 순위를 올리는데,
# 한글 질의에서 벡터 채널이 UI 문서 쪽으로 쏠려 있어 **상관된 오답이 서로를 밀어 올린다.**
# 정답은 BM25 단독이라 단일 채널로 남아 밀려난다.
#
# [중요] **그래서 더 손대지 않는다.** 질의 3개를 눈으로 보며 고르는 것은 측정이 아니다 —
# 세 번 고쳤고 한 번은 오히려 나빠졌다. **정답 집합(ground truth)을 만든 뒤에** 켤 것.
# 그때 검증할 가설: *"한글 질의에서는 벡터 채널을 낮추거나 끈다"*(원본도 `search_domain_norms`
# 에서 채널을 언어·신뢰도로 게이팅한다).
KR_ROUTING = __import__("os").environ.get("AX_BM25_KR", "") == "1"


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
    # [중요] `search_text` 를 쓴다 — 본문 없는 스텁도 색인한다 (`documents.py` 참조).
    body = " ".join(tokenize(doc.search_text))
    return tags, cat, rc, body


def _table(gen: str) -> str:
    return f"bm25_{gen}"


def _kr_table(gen: str) -> str:
    """한글 보조 테이블 (trigram)."""
    return f"bm25kr_{gen}"


def has_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(text or ""))


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
        # [중요] 프로세스 간 안전 (소 3.5.3). `bm25.db` 는 **두 프로세스**가 연다 —
        #    색인기(master.events.consumer, 쓰기)와 서비스(master.projects, 읽기).
        #    아래 `self._lock` 은 프로세스 **안**만 막는다. 2026-08-14 에 형제 모듈
        #    (`graph/db.py`·`graph/dependency.py`)에는 있고 여기만 빠져 있던 것이 발견됐다.
        sqlite_util.apply(self._conn)
        # 첫 검색 콜드미스(~200ms) 회피. 원본과 같은 값.
        self._conn.execute("PRAGMA mmap_size = 67108864")   # 64MB OS-level mmap
        self._conn.execute("PRAGMA cache_size = -8000")     # 8MB SQLite 캐시
        self._conn.execute("PRAGMA temp_store = MEMORY")
        for g in (generation.A, generation.B):
            self._create(g)
        self._conn.commit()
        self._gen = gen or generation.read(paths.root) or self._probe()

    def _create(self, gen: str) -> None:
        for table, tk in ((_table(gen), _FTS5_TOKENIZE), (_kr_table(gen), _FTS5_TOKENIZE_KR)):
            self._conn.execute(
                f"""CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING fts5(
                    file_id UNINDEXED,
                    tags,
                    category,
                    related_classes,
                    body,
                    tokenize = "{tk}"
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

        word = self._match(_table(self._gen), tokens, limit)
        if not KR_ROUTING:
            return word
        kr_tokens = [t for t in tokens if len(t) >= KR_MIN_LEN] if has_hangul(query) else []
        if not kr_tokens:
            return word

        # [중요] 한글 질의는 **두 테이블을 교차로 섞는다** (2026-08-08 실측으로 고친 지점).
        #
        # 처음엔 "단어 테이블이 부족할 때만 trigram 으로 채운다" 로 만들었는데 **효과가 0
        # 이었다** — 단어 테이블이 `limit` 을 채워 버려 trigram 이 조회조차 안 됐다.
        # 문제는 결과가 *부족한* 게 아니라 *틀린* 것이었다.
        #
        # 실측(질의 「전역 이벤트 시스템」):
        #   단어 테이블   : WNDUITopMenuBase · ModularStage · **GlobalEventSystem(3위)**
        #   trigram 테이블: **GlobalEventSystem(1위)** · WidgetEventTags · WNDUIHUD
        #
        # trigram 이 정답을 1위로 올린다. 그래서 **경쟁시킨다.**
        #
        # 점수로 섞지 않는 이유는 그대로다 — 토크나이저가 달라 `bm25()` 값이 **비교 불가**다.
        # 대신 **순위를 번갈아 놓는다.** RRF 는 순위만 쓰므로(`search.py`) 이것이 그대로
        # 반영되고, **RRF 는 여전히 2채널**이라 융합 로직·`RRF_K` 를 건드리지 않는다.
        kr = self._match(_kr_table(self._gen), kr_tokens, limit)
        if not kr:
            return word

        # **한글 어절이 절반을 넘으면 trigram 테이블을 쓴다.** 섞지 않는다.
        #
        # 섞어 봤고(순위 교차) **더 나빠졌다** — 실측 2026-08-08. 이유는 RRF 쪽에 있다:
        # 두 채널이 **동의**하면 순위가 오르는데, 한글 질의에서 벡터 채널이 UI 문서 쪽으로
        # 쏠려 있어 **상관된 오답이 서로를 밀어 올린다.** BM25 를 반쯤 섞으면 정답이
        # 단일 채널로 남아 오히려 밀려난다.
        #
        # 그래서 한글 질의에서는 **BM25 채널의 의견을 하나로** 준다 — trigram 쪽이 그 질의에
        # 더 맞는 도구다(실측: 「전역 이벤트 시스템」에 대해 `GlobalEventSystem.md` 를 1위로).
        # 영문·혼합 질의는 단어 테이블 그대로다.
        #
        # [주의] **이 규칙은 질의 3개로 정했다.** 표본이 얇다 — `search_log.jsonl` 이 쌓이면
        # 실제 질의 분포로 다시 재야 한다(원본의 `language_gap_report` 가 그 용도다).
        return kr if len(kr_tokens) * 2 > len(tokens) else word

    def _match(self, table: str, tokens: list[str], limit: int) -> list[tuple[str, float]]:
        """한 테이블에 MATCH. 토큰을 따옴표로 감싼다 — FTS5 예약어(AND/OR/NOT/NEAR) 충돌 방지."""
        match = " OR ".join(f'"{t}"' for t in tokens)
        try:
            with self._lock:
                rows = self._conn.execute(
                    f"""SELECT file_id,
                               -bm25({table}, 0.0, {TAGS_BOOST}, {CATEGORY_BOOST},
                                     {RELATED_CLASSES_BOOST}, {BODY_BOOST}) AS score
                        FROM {table}
                        WHERE {table} MATCH ?
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
            self._conn.execute(f"DELETE FROM {_kr_table(gen)}")
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
        """두 테이블에 **같은 내용**을 넣는다 — 토크나이저만 다르다.

        저장 텍스트는 사전 토큰화된 공백 구분 스트림 그대로다. trigram 쪽에도 그게 좋다 —
        공백이 토큰 경계를 유지하므로 **인접한 다른 토큰에 걸친 가짜 trigram** 이 생기지 않는다.
        """
        for table in (_table(gen), _kr_table(gen)):
            self._conn.executemany(
                f"INSERT INTO {table} (file_id, tags, category, related_classes, body) "
                f"VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def upsert(self, docs: list[Document]) -> int:
        """증분 갱신 — Live 세대에 직접 쓴다(벡터 쪽 `upsert()` 와 같은 판단)."""
        if self._conn is None or not docs:
            return 0
        with self._lock:
            for d in docs:
                for t in (_table(self._gen), _kr_table(self._gen)):
                    self._conn.execute(f"DELETE FROM {t} WHERE file_id = ?", (d.file_id,))
            self._insert(self._gen, [(d.file_id, *_fields(d)) for d in docs])
            self._conn.commit()
        return len(docs)

    def remove(self, file_ids: list[str]) -> int:
        if self._conn is None or not file_ids:
            return 0
        with self._lock:
            cur = self._conn.executemany(
                f"DELETE FROM {_table(self._gen)} WHERE file_id = ?", [(f,) for f in file_ids]
            )
            self._conn.executemany(
                f"DELETE FROM {_kr_table(self._gen)} WHERE file_id = ?", [(f,) for f in file_ids]
            )
            self._conn.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    # ── [중요] 0건 진단 (소 3.5.8 — 원전 `[BM25 0건 진단]` 카나리 이식) ──────
    #
    # [주의] **원전처럼 로그를 찍지 않는다.** 이 저장소의 모듈은 **사실을 반환하고 호출자가
    # 찍는다**(테스트 가능하고 전역 상태가 없다). 원전의 카나리는 `watch.exe` 의 상주 콘솔에
    # 묶인 방식이었다 — 기제를 옮기고 형태는 우리 것으로 둔다.
    #
    # [중요] **왜 이것이 필요한가.** *"검색이 비었다"* 는 사용자가 보고하는 **증상**이고 원인은
    # 여럿이다(색인이 빔 · 토큰이 하나도 안 맞음 · 한국어 어절 분해 실패 · 세대가 어긋남).
    # 리포트 13 §19.1 에서 *"도메인이 비어있어"* 라는 보고를 받고 처음부터 재야 했던 자리다 —
    # 그때 이 함수가 있었으면 한 번에 답했다.

    def stats(self) -> dict:
        """색인의 현재 상태. 기동 시 한 줄 찍기(원전 `[BM25 startup]`)의 재료."""
        return {"generation": self.gen, "documents": self.count()}

    def diagnose(self, query: str, limit: int = 10) -> dict:
        """검색이 0건일 때 **왜**를 돌려준다. 결과가 있어도 부를 수 있다(진단 전용).

        `unmatched` 가 곧 원인이다 — 어느 토큰도 안 맞으면 질의가 색인 어휘와 겹치지 않는다.
        """
        terms = tokenize(query)
        hits = self.search(query, limit=limit)
        per: dict = {}
        with self._lock:
            for t in terms:
                try:
                    row = self._conn.execute(
                        f"SELECT COUNT(*) FROM {_table(self._gen)} WHERE {_table(self._gen)} MATCH ?",
                        (f'"{t}"',)).fetchone()
                    per[t] = int(row[0]) if row else 0
                except Exception:                       # noqa: BLE001 — 진단이 죽으면 안 된다
                    per[t] = -1                         # -1 = 세어 보지 못했다
        unmatched = [t for t, n in per.items() if n == 0]
        return {
            "query": query,
            "results": len(hits),
            "documents": self.count(),
            "generation": self.gen,
            "terms": terms,
            "term_hits": per,
            "unmatched": unmatched,
            "has_hangul": has_hangul(query),
            # [중요] 사유를 문장으로 — 사람이 읽는 자리다.
            "reason": (
                "색인이 비어 있다" if self.count() == 0 else
                "토큰이 하나도 색인 어휘와 맞지 않는다" if terms and len(unmatched) == len(terms) else
                "질의에서 토큰이 나오지 않았다" if not terms else
                "일부 토큰만 맞는다 (질의를 좁히거나 클래스명을 함께 넣어 볼 것)"
                if unmatched and hits == [] else
                "결과가 있다"),
        }

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
