"""벡터 색인 — 마운트된 프로젝트 기준 (PLAN §5.2-E, §5.5.2).

AgentTest `double_buffered_index.py` 이식. **구조는 유지하고 경로 해석만 뒤집었다:**

    AgentTest:  DoubleBufferedIndex(claude_dir)   ← 기동 시 고정, 클로저에 캡처 (§5.5.1)
    여기:       ContextIndex(paths)               ← `paths.resolve()` 가 매번 해석

🔴 **더블 버퍼를 유지하는 이유** (§5.4.6): 검색은 항상 Live 컬렉션에서 즉시 답하고, 갱신은
Work 컬렉션에서 진행한 뒤 원자적으로 교체한다. 재색인 중에도 검색이 막히지 않는다.
이벤트 큐 소비자가 재색인을 도는 동안 작업장이 검색을 계속 쓸 수 있어야 하므로 필수다.

🔴 **컬렉션 이름은 고정(`context_a`/`context_b`)이지만 프로젝트끼리 섞이지 않는다** —
`vector_db` 디렉토리가 프로젝트별로 갈리기 때문이다. §5.5.1 이 "컬렉션명에 프로젝트 식별자가
없다" 고 지적한 문제가 **경로 분기로 해소된다.**
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from . import embedding, generation
from .documents import Document, iter_documents
from .paths import ProjectPaths

LIVE_A = "context_a"
LIVE_B = "context_b"
# 코사인 — 원본과 동일. 바꾸면 기존 색인과 점수가 어긋난다.
_METADATA = {"hnsw:space": "cosine"}

# 한 번에 upsert 할 문서 수. 너무 크면 임베딩 배치가 메모리를 먹고, 너무 작으면 느리다.
BATCH = 128



@dataclass
class IndexStats:
    project: str
    documents: int
    live: str
    elapsed_sec: float = 0.0

    def summary(self) -> str:
        return (f"{self.project}: {self.documents}건 색인 "
                f"(live={self.live}, {self.elapsed_sec:.1f}s)")


class ContextIndex:
    """한 프로젝트의 벡터 색인. **경로는 생성자에서 받는다 — 전역이 없다.**"""

    def __init__(self, paths: ProjectPaths, *, gen: str | None = None):
        import chromadb  # 무거우므로 지연 import — 경로 해석만 하는 호출자를 막지 않는다

        self.paths = paths
        self.model_mismatch = ""
        paths.ensure_derived()
        self._client = chromadb.PersistentClient(path=str(paths.vector_db))
        # 🔴 **다국어 임베딩.** 영어 전용 모델에서는 한글 질의가 두 채널 모두 실패했다 —
        # 근거와 실측은 `embedding.py` 독스트링. 별도 모델 서버는 여전히 필요 없다(ONNX).
        self._embed_model = embedding.model_name()
        self._embed = embedding.build(self._embed_model)
        self._a = self._collection(LIVE_A)
        self._b = self._collection(LIVE_B)
        self._swap = threading.Lock()
        # 세대 포인터는 BM25 와 **공유한다** — 이유는 `generation.py` 참조.
        # 마커가 없으면 문서가 많은 쪽으로 자가 복구한다 (추측하지 않는다).
        self._live_name = gen or generation.read(paths.root) or (
            generation.B if self._b.count() > self._a.count() else generation.A
        )
        self._live, self._work = ((self._a, self._b)
                                  if self._live_name == generation.A else (self._b, self._a))

    def _collection(self, name: str):
        """컬렉션을 얻는다. **임베딩 모델이 바뀌었으면 비우고 다시 만든다.**

        🔴 chromadb 는 기존 컬렉션의 임베딩 함수 교체를 **거부한다** — 옳은 동작이다.
        차원이 같아도(둘 다 384) 벡터 공간이 다르면 비교가 무의미하다.

        그래서 우리가 처리한다:

        - 벡터는 **파생 자산**이다(`data-schema.md`) — 재색인으로 복구된다
        - 낡은 모델의 벡터를 남겨 두는 쪽이 **더 나쁘다**: 색인은 정상으로 보이고 결과만
          틀린다. 우리가 반복해 온 실패 모양이다

        비운 뒤 **무엇을 왜 비웠는지** `model_mismatch` 에 남긴다. 비운 직후엔 0건이므로
        호출자는 반드시 재색인해야 한다 — 그 사실도 같이 적는다.
        """
        meta = {**_METADATA, "embed_model": self._embed_model}
        try:
            return self._client.get_or_create_collection(
                name=name, metadata=meta, embedding_function=self._embed
            )
        except ValueError as e:
            if "mbedding function" not in str(e):
                raise
            try:
                had = self._client.get_collection(name=name).count()
            except Exception:                       # noqa: BLE001
                had = 0
            self._client.delete_collection(name=name)
            self.model_mismatch = (
                f"🔴 임베딩 모델이 바뀌어 `{name}` 을 비웠다 ({had}건) → {self._embed_model}. "
                f"벡터는 파생 자산이라 재구축된다 — 재색인해야 검색이 정상화된다"
            )
            return self._client.create_collection(
                name=name, metadata=meta, embedding_function=self._embed
            )

    # ── 조회 ──────────────────────────────────────────
    @property
    def live_name(self) -> str:
        return self._live_name

    def count(self) -> int:
        return self._live.count()

    def search(self, query: str, limit: int = 8) -> list[dict]:
        """Live 컬렉션에서 검색한다. **갱신 중에도 막히지 않는다.**"""
        if not query.strip():
            return []
        with self._swap:
            coll = self._live
        n = min(max(1, limit), max(1, coll.count()))
        if coll.count() == 0:
            return []
        res = coll.query(query_texts=[query], n_results=n)
        out = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, fid in enumerate(ids):
            out.append({
                "file_id": fid,
                "score": 1.0 - float(dists[i]) if i < len(dists) else None,  # cosine → 유사도
                "meta": metas[i] if i < len(metas) else {},
                "excerpt": (docs[i] or "")[:400] if i < len(docs) else "",
            })
        return out

    # ── 갱신 ──────────────────────────────────────────
    def rebuild(self, *, progress=None, swap: bool = True) -> IndexStats:
        """Work 컬렉션에 전체 재색인. **검색은 내내 Live 에서 열려 있다.**

        `swap=False` 는 두 채널을 함께 뒤집는 경우(`rebuild.py`)에 쓴다 — 벡터만 먼저
        뒤집으면 BM25 와 세대가 어긋난다.
        """
        import time

        t0 = time.monotonic()
        work = self._work
        # 원본과 달리 delete 대신 컬렉션을 비운다 — 이름을 유지해야 스왑이 단순하다.
        existing = work.get(include=[])["ids"]
        if existing:
            work.delete(ids=existing)

        batch: list[Document] = []
        total = 0

        def flush():
            nonlocal batch, total
            if not batch:
                return
            work.upsert(
                ids=[d.file_id for d in batch],
                documents=[d.embed_text for d in batch],
                metadatas=[d.meta for d in batch],
            )
            total += len(batch)
            if progress:
                progress(total)
            batch = []

        for doc in iter_documents(self.paths.context):
            batch.append(doc)
            if len(batch) >= BATCH:
                flush()
        flush()

        if swap:
            self._swap_live()
        return IndexStats(project=self.paths.name, documents=total,
                          live=self._live_name, elapsed_sec=time.monotonic() - t0)

    def upsert(self, file_ids: list[str]) -> int:
        """증분 갱신 — **Live 에 직접 쓴다.**

        전체 재색인과 달리 스왑하지 않는다. 소수 문서 갱신에 컬렉션을 통째로 바꾸는 것은
        낭비이고, 검색이 잠깐 새 문서와 옛 문서를 섞어 보는 것은 허용 범위다
        (워터마크가 커밋 해시라 결국 수렴한다 — §5.5.3-c).
        """
        ctx = self.paths.context
        docs = []
        for fid in file_ids:
            p = ctx / fid
            if not p.is_file():
                continue
            from .documents import is_excluded, load
            if is_excluded(fid):
                continue
            d = load(p, ctx)
            if d.search_text:
                docs.append(d)
        if not docs:
            return 0
        with self._swap:
            coll = self._live
        coll.upsert(ids=[d.file_id for d in docs],
                    documents=[d.embed_text for d in docs],
                    metadatas=[d.meta for d in docs])
        return len(docs)

    @property
    def work_name(self) -> str:
        return generation.other(self._live_name)

    def _swap_live(self) -> None:
        with self._swap:
            self._live, self._work = self._work, self._live
            self._live_name = generation.other(self._live_name)
        # 🔴 스왑 **후에** 쓴다 — 먼저 쓰고 죽으면 마커가 빈 세대를 가리킨다.
        generation.write(self.paths.root, self._live_name)


def open_index(name: str = "", *, registry=None, gen: str | None = None) -> ContextIndex:
    """마운트된(또는 지정한) 프로젝트의 색인을 연다.

    🔴 경로를 **매 호출 해석**한다 — 마운트가 바뀌면 다음 호출이 새 프로젝트를 연다.
    """
    from .paths import resolve

    return ContextIndex(resolve(name, registry=registry), gen=gen)
