"""검색 — 벡터 + BM25 를 RRF 로 융합 (AgentTest `cs_common.rrf_rank_and_sort` 이식).

**원본에서 그대로 가져온 것 — 바꾸면 순위가 드리프트한다:**

- `RRF_K = 60`
- source 조합별 tie-break 우선순위 (`_SOURCE_PRIORITY`)
- 정렬 키: RRF 내림차순 → source 우선순위 → similarity 내림차순

**1단계에서 뺀 것** (전부 온톨로지·부가 계층이라 §5.2-E ③ 의 분할선과 일치한다):

| 뺀 것 | 어디로 |
|---|---|
| 도메인 자동 추론 (`infer_domain_from_query`) | 2단계 — `class_ontology` 테이블이 있어야 한다 |
| 시소러스 쿼리 확장 (`_expand_query_with_thesaurus`) | 2단계 — 온톨로지 objects yaml 이 원천 |
| 규범 첨부 (`attach_norms`) | 2단계 |
| 검색 로그 (`_log_search`, caller/session_id/work_id) | §5.2-D 로 별도 판단 (감사 계층) |
| 원격 모드 (`_is_remote_mode`) | 불필요 — 여기가 서버다 |

🔴 **뺀 것들은 전부 "얹는" 기능이다.** 원본에서도 추론 실패 시 무필터로 폴백하므로
(`search_tools.py:290` 의 `except → skip`) **없어도 검색은 온전히 돈다.** 1단계를 먼저
세울 수 있는 근거가 이것이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bm25 import Bm25Index
from .index import ContextIndex
from .paths import ProjectPaths

RRF_K = 60

# RRF 동률일 때의 정렬 우선순위. 두 채널이 함께 찾은 문서가 앞선다.
_SOURCE_PRIORITY = {
    "vector+bm25": 0,
    "vector": 1,
    "bm25": 2,
}


@dataclass
class Hit:
    file_id: str
    source: str
    rrf_score: float = 0.0
    similarity: float = 0.0     # 벡터 유사도 (BM25 단독이면 0.0)
    bm25_score: float = 0.0
    vector_rank: int | None = None
    bm25_rank: int | None = None
    meta: dict = field(default_factory=dict)
    excerpt: str = ""

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "source": self.source,
            "rrf_score": round(self.rrf_score, 6),
            "similarity": round(self.similarity, 4),
            "meta": self.meta,
            "excerpt": self.excerpt,
        }


def fuse(vector_hits: list[dict], bm25_hits: list[tuple[str, float]]) -> list[Hit]:
    """두 채널의 **순위**를 RRF 로 합친다.

    🔴 점수가 아니라 **순위**를 쓴다. 코사인 유사도와 BM25 점수는 척도가 달라 직접 더할 수
    없다 — RRF 가 존재하는 이유가 그것이다. 채널 하나를 정규화해서 섞으려 들면 안 된다.
    """
    merged: dict[str, Hit] = {}

    for rank, h in enumerate(vector_hits, start=1):
        fid = h["file_id"]
        merged[fid] = Hit(
            file_id=fid, source="vector", vector_rank=rank,
            similarity=h.get("score") or 0.0,
            meta=h.get("meta") or {}, excerpt=h.get("excerpt") or "",
        )

    for rank, (fid, score) in enumerate(bm25_hits, start=1):
        hit = merged.get(fid)
        if hit is None:
            merged[fid] = Hit(file_id=fid, source="bm25", bm25_rank=rank, bm25_score=score)
        else:
            hit.source = "vector+bm25"
            hit.bm25_rank = rank
            hit.bm25_score = score

    for hit in merged.values():
        rrf = 0.0
        if hit.vector_rank is not None:
            rrf += 1.0 / (RRF_K + hit.vector_rank)
        if hit.bm25_rank is not None:
            rrf += 1.0 / (RRF_K + hit.bm25_rank)
        hit.rrf_score = rrf

    return sorted(
        merged.values(),
        key=lambda h: (-h.rrf_score, _SOURCE_PRIORITY.get(h.source, 9), -h.similarity),
    )


class ContextSearch:
    """한 프로젝트의 검색 진입점. **두 채널이 같은 세대를 본다** (`generation.py`)."""

    def __init__(self, paths: ProjectPaths):
        self.paths = paths
        self.vector = ContextIndex(paths)
        # 🔴 벡터가 해석한 세대를 BM25 에 넘긴다. 각자 마커를 읽게 두면 그 사이 재색인이
        # 끝났을 때 두 채널이 다른 세대를 잡는 창이 생긴다.
        self.bm25 = Bm25Index(paths, gen=self.vector.live_name)

    @property
    def generation(self) -> str:
        return self.vector.live_name

    def search(self, query: str, limit: int = 8, *, pool: int | None = None) -> list[Hit]:
        """융합 검색.

        `pool` 은 융합 **전** 각 채널에서 가져올 후보 수다. `limit` 과 같게 두면 한 채널에만
        잡힌 문서가 잘려 나가 융합의 의미가 줄어든다 — 기본값을 넉넉히(`limit*3`) 잡는다.
        """
        if not query.strip():
            return []
        n = pool or max(limit * 3, 10)
        vec = self.vector.search(query, limit=n)
        kw = self.bm25.search(query, limit=n)
        return fuse(vec, kw)[:limit]

    def close(self) -> None:
        self.bm25.close()


def open_search(name: str = "", *, registry=None) -> ContextSearch:
    """마운트된(또는 지정한) 프로젝트의 검색기를 연다. 경로는 **매 호출 해석**한다."""
    from .paths import resolve

    return ContextSearch(resolve(name, registry=registry))
