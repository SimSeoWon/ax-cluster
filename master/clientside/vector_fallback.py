"""클라이언트 벡터 폴백 — 원전 `mcp/context_search/client_index.py` 이식
(소 3.4.3 · `#162`, 2026-08-15).

마스터가 응답한 검색 결과를 로컬 ChromaDB 에 적재해, 마스터에 닿지 못할 때 **의미 검색**을
유지한다. 온톨로지 정형 KV 캐시(`ontology_cache.py`)와 **책임·디렉토리를 분리**한다 —
성격이 임베딩 vs KV 다(원전 판단).

## [중요] 핵심은 「해시가 같으면 임베딩을 다시 만들지 않는다」

    content_hash   서버가 컨텍스트 생성 시 박아 준 것을 **우선** 쓴다
                   없으면 본문의 로컬 해시로 폴백 (16자)
    같으면 skip    → 반복 검색의 임베딩 비용이 **0** 이다

이 skip 이 없으면 폴백 캐시가 매 검색마다 임베딩을 다시 만들어, 마스터가 멈춘 상황에서
클라이언트가 **더 느려진다.** 원전이 이 자리에 해시를 둔 이유다.

## [중요] 원전과 다르게 둔 것 — 임베더는 **우리 것**을 쓴다

원전은 Chroma **기본 임베딩 함수**(내장 `ONNXMiniLM_L6_V2` = `all-MiniLM-L6-v2`)를 쓴다.
[중요] **우리 `context_search/embedding.py` 가 이미 그 모델을 기각해 뒀고 근거도 적혀 있다**:

> *"기본값이던 chromadb 내장 `ONNXMiniLM_L6_V2`(= `all-MiniLM-L6-v2`)는 **영어 전용**이다 …
> 영어 전용 모델에서는 **한글 질의가 두 채널 모두 실패했다**"*

그대로 옮기면 **폴백이 한글 질의에 무력해진다** — 마스터가 멈춰서 폴백으로 내려간 그 순간에.
그래서 기제는 옮기고 **구성요소는 우리 것**(`paraphrase-multilingual-MiniLM-L12-v2`, 384차원이라
저장 증가 0)을 쓴다. [주의] 이것은 정합 작업(`#194`)이 아니라 **이식이 성립하기 위한 조건**이다 —
σ.9.0 의 `mtime` 을 git 시각으로 바꾼 것과 같은 부류다.

[주의] **마스터 색인과 유사도를 직접 비교하지 말 것.** 같은 모델이라 결과가 일관되긴 하지만, 이
캐시는 **서버가 준 결과의 사본**이고 코퍼스 전체가 아니다 — 폴백은 *"가진 것 중에서 가장
가까운 것"* 이지 *"코퍼스에서 가장 가까운 것"* 이 아니다. `source` 필드가 그것을 표시한다.

## 정책

- 전역 없음 — `VectorFallback(cache_dir)` 로 받는다(`ontology_cache.py` 와 같은 이유)
- 초기화 실패는 **한 번만** 시도하고 폴백 비활성 (원전 그대로)
- 실패를 값으로 돌린다 — fail-open 이되 조용하지 않다 (중 4.2 σ 기준)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

COLLECTION = "context_client_cache"
CACHE_DIRNAME = "vector_db_client"
PREVIEW_CHARS = 300


def content_hash(content: str) -> str:
    """서버가 해시를 안 줄 때만 쓰는 폴백. 원전과 같은 길이(16자)를 유지한다."""
    return hashlib.md5((content or "").encode("utf-8")).hexdigest()[:16]


class VectorFallback:
    """클라이언트측 의미 검색 캐시."""

    def __init__(self, cache_dir, *, embed_model: str | None = None):
        self.dir = Path(cache_dir) / CACHE_DIRNAME
        self._coll = None
        self._tried = False
        self.error = ""
        self._embed_model = embed_model

    # ── 연결 ────────────────────────────────────────────────────────────────
    def _collection(self):
        if self._coll is not None or self._tried:
            return self._coll
        self._tried = True
        try:
            import chromadb                      # 무겁다 — 지연 import (우리 index.py 와 같은 규약)

            from ..context_search import embedding

            self.dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.dir))
            model = self._embed_model or embedding.model_name()
            self._embed_model = model
            self._coll = client.get_or_create_collection(
                name=COLLECTION,
                embedding_function=embedding.build(model),
                metadata={"description": "마스터 응답의 클라이언트측 사본 (폴백 전용)"},
            )
        except Exception as e:                    # noqa: BLE001 — 폴백이 호출자를 막지 않는다
            self.error = f"초기화 실패 — 폴백 비활성: {type(e).__name__}: {e}"
            self._coll = None
        return self._coll

    @property
    def available(self) -> bool:
        return self._collection() is not None

    def count(self) -> int:
        coll = self._collection()
        if coll is None:
            return 0
        try:
            return int(coll.count())
        except Exception:                          # noqa: BLE001
            return 0

    # ── 적재 ────────────────────────────────────────────────────────────────
    def upsert(self, results: list) -> dict:
        """마스터 검색 결과를 적재한다. [중요] **해시가 같으면 건너뛴다.**

        기대 형태(원전과 같다): `{file, content_preview, content_hash?, category?, tags?,
        related_classes?}`. `file` 이나 본문이 없으면 그 항목은 **버린다** — 무엇을 적재했는지
        모르는 채로 넣으면 폴백이 쓰레기를 내민다.
        """
        coll = self._collection()
        if coll is None:
            return {"upserted": 0, "skipped": 0, "dropped": 0,
                    "reason": self.error or "캐시 없음"}

        cands, dropped = [], 0
        for r in results or []:
            fid = (r.get("file") or "").strip()
            body = r.get("content_preview") or ""
            if not fid or not body:
                dropped += 1
                continue
            related = r.get("related_classes") or {}
            cands.append({
                "id": fid,
                "doc": body,
                "meta": {
                    "category": r.get("category", "") or "",
                    # [주의] Chroma 메타데이터는 스칼라만 받는다 — 목록·매핑을 문자열로 접는다
                    "tags": ",".join(r.get("tags") or []),
                    "related_classes_json": (json.dumps(related, ensure_ascii=False)
                                             if related else ""),
                    "content_hash": r.get("content_hash") or content_hash(body),
                    "source": "remote_cache",
                },
            })
        if not cands:
            return {"upserted": 0, "skipped": 0, "dropped": dropped,
                    "reason": "적재할 후보가 없다"}

        existing: dict = {}
        try:
            got = coll.get(ids=[c["id"] for c in cands], include=["metadatas"])
            metas = got.get("metadatas") or []
            for i, eid in enumerate(got.get("ids") or []):
                m = metas[i] if i < len(metas) else {}
                if m:
                    existing[eid] = m.get("content_hash", "")
        except Exception as e:                     # noqa: BLE001
            # [중요] 비교를 못 하면 **전부 적재**한다 — 원전과 같은 방향(폴백이 비는 쪽이 더 나쁘다)
            self.error = f"기존 해시 조회 실패 — 전체 적재로 진행: {e}"

        todo = [c for c in cands if existing.get(c["id"]) != c["meta"]["content_hash"]]
        skipped = len(cands) - len(todo)
        if not todo:
            return {"upserted": 0, "skipped": skipped, "dropped": dropped,
                    "reason": "전부 변경 없음 — 임베딩 비용 0"}
        try:
            coll.upsert(ids=[c["id"] for c in todo],
                        documents=[c["doc"] for c in todo],
                        metadatas=[c["meta"] for c in todo])
        except Exception as e:                     # noqa: BLE001
            return {"upserted": 0, "skipped": skipped, "dropped": dropped,
                    "reason": f"적재 실패: {e}"}
        return {"upserted": len(todo), "skipped": skipped, "dropped": dropped, "reason": ""}

    # ── 검색 ────────────────────────────────────────────────────────────────
    def search(self, query: str, *, limit: int = 5, category: str = "") -> list:
        """로컬 사본에서 의미 검색. [중요] 결과에 `source` 를 박아 **폴백임을 표시한다.**

        표시가 없으면 소비자가 *"코퍼스에서 가장 가까운 것"* 으로 오해한다 — 이것은
        **가진 것 중에서** 가장 가까운 것이다.
        """
        coll = self._collection()
        if coll is None or not (query or "").strip():
            return []
        try:
            where = {"category": {"$eq": category}} if category else None
            res = coll.query(query_texts=[query], n_results=max(1, limit), where=where)
        except Exception as e:                     # noqa: BLE001
            self.error = f"검색 실패: {e}"
            return []

        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        out = []
        for i, fid in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            raw = meta.get("related_classes_json", "")
            try:
                related = json.loads(raw) if raw else {}
            except ValueError:
                related = {}
            dist = dists[i] if i < len(dists) else 0
            out.append({
                "file": fid,
                # 원전과 같은 변환. [중요] 음수가 나오지 않게 자른다(거리 > 1 인 경우가 있다)
                "similarity": max(0.0, 1.0 - float(dist or 0)),
                "category": meta.get("category", ""),
                "tags": [t for t in (meta.get("tags", "") or "").split(",") if t],
                "related_classes": related,
                "content_preview": (docs[i][:PREVIEW_CHARS] if i < len(docs) else ""),
                "source": "client_cache_vector",
            })
        return out

    def stats(self) -> dict:
        return {"available": self.available, "count": self.count(),
                "dir": str(self.dir), "embed_model": self._embed_model,
                "error": self.error}
