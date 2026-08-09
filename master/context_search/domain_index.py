"""도메인(온톨로지) 색인 — 소 2.1.1 · 2.1.2 · 2.1.3.

원본: `AgentTest/mcp/context_search/domain_index.py` (829줄) 중 색인·검색부.

## 왜 별도 DB·별도 컬렉션인가

컨텍스트 MD 색인(961건)과 **파일도 컬렉션도 분리**한다. 도메인 문서는 한 건이 도메인 전체를
아우르는 **광범위 신호**라, 같은 표에 넣으면 일반 검색에서 늘 상위에 끼어들어 파일 단위 결과를
밀어낸다. 원본이 같은 이유로 분리했고(*"별도 DB / 별도 컬렉션 — 일반 인덱스는 영향 받지 않음"*),
그래서 이 모듈이 실패해도 **기존 검색은 멀쩡하다.**

## 🔴 증분이 아니라 전체 재빌드다

도메인은 수십 개 규모다. 증분 갱신 기계를 만드는 비용이 전체 재빌드보다 비싸고, 부분 갱신은
**낡은 행이 조용히 남는** 실패 모드를 만든다. FTS5 는 DELETE 로 공간을 회수하지 않으므로
**파일째 지우고 새로 만든다**(원본과 같다).

## 🔴 노이즈 3중 차단 (소 2.1.2) — 빼면 조용히 나빠진다

원본이 회사 환경에서 검증한 것: **벡터 단독은 무관한 질의에도 약한 hit 를 낸다.** 그대로 두면
*"모든 검색에 도메인이 끼어드는"* 상태가 된다. 그래서 `search_norms` 는:

1. **BM25 가 0건이면 빈 결과** — 도메인은 광범위 신호라 **정확 매칭이 있어야** 의미가 있다
2. **벡터 단독 매칭은 유사도 임계 이상만** 인정
3. **개수 상한**(기본 2) — 규범은 곁들이는 것이지 결과 목록이 아니다

## 이식하며 바꾼 것

- **파싱은 `ontology.yaml_io` 를 쓴다.** 원본은 자체 부분 파서를 또 만들었지만, 우리는
  **쓰는 쪽과 읽는 쪽이 같은 모듈**이라 왕복이 보장된다(중 1.3 에서 그렇게 지었다)
- **임베딩은 우리 다국어 모델**(`embedding.py`)을 쓴다. chroma 기본 임베딩을 쓰면 컨텍스트
  색인과 **벡터 공간이 달라** 같은 질의가 두 채널에서 다르게 동작한다
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ..ontology import yaml_io
from . import bm25, embedding
from .paths import ProjectPaths

COLLECTION = "ontology_domains"
TABLE = "domains"
RRF_K = 60                      # 컨텍스트 검색과 같은 값 — 손대면 순위가 드리프트한다
DEFAULT_TOP_K = 2
SIMILARITY_THRESHOLD = 0.2
PREVIEW = 500

# 필드 가중치 — 원본 값 그대로. 🔴 **바꾸면 순위가 드리프트한다** (보고서 08 §14.4).
WEIGHTS = (3.0, 1.5, 2.5, 1.0)          # tags · category · related_classes · body


class DomainIndexError(RuntimeError):
    """색인을 만들 수 없다. 🔴 빈 색인을 성공으로 보고하지 않는다."""


@dataclass
class SyncStats:
    synced: int = 0
    skipped: int = 0
    bm25_count: int = 0
    vector_count: int = 0
    domains: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    skipped_unchanged: bool = False

    @property
    def summary(self) -> str:
        head = "도메인" if not self.skipped_unchanged else "도메인(유지)"
        s = f"{head} {self.synced} · BM25 {self.bm25_count} · 벡터 {self.vector_count}"
        if self.skipped:
            s += f" · 🔴 건너뜀 {self.skipped}"
        if self.notes:
            s += " · " + " / ".join(self.notes[:2])
        return s


# ── 페이로드 ────────────────────────────────────────────────────

def manifests(paths: ProjectPaths) -> list:
    """색인 대상 — 패키지의 `domain.yaml` **만**.

    🔴 항목 yaml(objects/actions/invariants)은 **직접 색인하지 않는다.** 검색 진입점은
    도메인 하나당 하나여야 한다(원본 결정). 항목 본문은 아래에서 manifest 페이로드에 **녹인다.**
    """
    root = paths.ontology / "domains"
    if not root.is_dir():
        return []
    return [d / "domain.yaml" for d in sorted(root.iterdir())
            if d.is_dir() and (d / "domain.yaml").is_file()]


def payload(manifest: Path) -> dict | None:
    """`domain.yaml` → 색인 페이로드. 읽을 수 없거나 도메인명이 없으면 `None`."""
    data = yaml_io.read(manifest)
    if not isinstance(data, dict):
        return None
    domain = str(data.get("domain") or "").strip()
    if not domain:
        return None

    pkg = manifest.parent
    tags = [str(t) for t in (data.get("tags") or []) if t]
    if domain not in tags:
        tags.append(domain)     # 도메인명 자체도 태그 채널에 — 이름으로 부를 때 매칭된다

    # 🔴 **오브젝트에 등록된 별칭을 tags 채널(가중치 3.0)로 올린다** (중 1.4.5).
    #
    # 실측 2026-08-09: 도메인 태그는 전체 118토큰 중 **한글이 4개(3%)** 뿐인데, 같은 도메인의
    # 본문에는 한글이 887~1,740자씩 있다. 즉 **한글 질의는 최고 가중치 채널을 통째로 놓치고**
    # `body`(1.0)에만 걸리는데, 길이 정규화가 내용 많은 도메인을 오히려 깎는다
    # (「미션 태스크 실행」에서 MissionEditor 0.4883 vs MissionRuntime 0.4778).
    #
    # 별칭은 사람이 등록한 한글 표현이다(`thesaurus.register`). 그것을 이 채널에 얹는 것이
    # **가중치를 만지지 않고 한글 질의를 살리는 유일하게 안전한 수단**이다 — 순위 튜닝은
    # 정답 집합이 생기기 전에는 하지 않기로 이미 정했다(리포트 10 §9.2).
    seen = {t.casefold() for t in tags}
    for o in data.get("objects") or []:
        if not isinstance(o, str):
            continue
        item = yaml_io.read(pkg / o)
        if not isinstance(item, dict):
            continue
        for a in item.get("aliases") or []:
            a = str(a).strip()
            if a and a.casefold() not in seen:
                seen.add(a.casefold())
                tags.append(a)

    # objects 는 경로 리스트다(패키지 구조) — stem 이 클래스명이다.
    related: list = []
    for o in data.get("objects") or []:
        if isinstance(o, str):
            stem = o.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if stem:
                related.append(stem)
        elif isinstance(o, dict) and o.get("name"):
            related.append(str(o["name"]))

    body: list = []
    for key in ("summary", "user_intent_notes"):
        if data.get(key):
            body.append(str(data[key]))
    for key in ("core_responsibilities", "invariants"):
        body += [str(x) for x in (data.get(key) or []) if x]

    # 🔴 항목 본문을 녹인다 — 이게 없으면 액션·invariant 로는 도메인이 검색되지 않는다.
    for key in ("actions", "invariants_files"):
        for rel in data.get(key) or []:
            item = yaml_io.read(pkg / str(rel))
            if not isinstance(item, dict):
                continue
            for f in ("name", "description", "text", "evidence"):
                if item.get(f):
                    body.append(str(item[f]))
            for step in item.get("flow") or []:
                if isinstance(step, dict):
                    body.append(" ".join(str(step.get(k) or "")
                                         for k in ("actor", "operation", "target")))
            for f in ("triggers_events", "subscribed_to", "objects_affected"):
                body += [str(x) for x in (item.get(f) or []) if x]

    return {
        "file_id": domain,
        "domain": domain,
        "tags": tags,
        "category": "domain",
        "related_classes": related,
        "body": "\n".join(x for x in body if x),
        "collaborates_with": [str(c) for c in (data.get("collaborates_with") or []) if c],
        "tier": data.get("tier"),
        "path": str(manifest),
    }


# ── fingerprint (소 2.1.3) ──────────────────────────────────────

def fingerprint(paths: ProjectPaths) -> str:
    """색인 입력의 지문 — `(경로, mtime, 크기)` 의 해시.

    🔴 **manifest 만이 아니라 항목 파일도 센다.** 액션 본문이 페이로드에 녹아 들어가므로
    manifest 가 그대로여도 항목이 바뀌면 색인은 낡는다.
    """
    import hashlib
    h = hashlib.sha1()
    root = paths.ontology / "domains"
    if root.is_dir():
        for p in sorted(root.rglob("*.yaml")):
            try:
                st = p.stat()
            except OSError:
                continue
            h.update(f"{p.relative_to(root)}|{int(st.st_mtime)}|{st.st_size}\n".encode())
    return h.hexdigest()[:16]


def _stamp_path(paths: ProjectPaths) -> Path:
    return paths.root / "domain_index.json"


def _read_stamp(paths: ProjectPaths) -> dict:
    try:
        d = json.loads(_stamp_path(paths).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def stored_fingerprint(paths: ProjectPaths) -> str:
    return str(_read_stamp(paths).get("fingerprint", ""))


def _write_stamp(paths: ProjectPaths, fp: str, stats: SyncStats) -> None:
    _stamp_path(paths).write_text(json.dumps(
        {"fingerprint": fp, "domains": stats.domains, "bm25": stats.bm25_count,
         "vector": stats.vector_count}, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 색인 (소 2.1.1) ─────────────────────────────────────────────

def _build_bm25(paths: ProjectPaths, payloads: list) -> int:
    """FTS5 표를 **파일째 새로** 만든다. DELETE 는 공간을 회수하지 않는다."""
    if not bm25.FTS5_AVAILABLE:
        raise DomainIndexError("sqlite3 에 FTS5 가 없다 — BM25 채널을 만들 수 없다")
    db = paths.bm25_domains_db
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE {TABLE} USING fts5("
            f"file_id UNINDEXED, tags, category, related_classes, body, "
            f"tokenize=\"unicode61 remove_diacritics 0 tokenchars '_'\")")
        conn.executemany(
            f"INSERT INTO {TABLE}(file_id, tags, category, related_classes, body) "
            f"VALUES (?,?,?,?,?)",
            [(p["file_id"],
              " ".join(bm25.tokenize(" ".join(p["tags"]))),
              " ".join(bm25.tokenize(p["category"])),
              " ".join(bm25.tokenize(" ".join(p["related_classes"]))),
              " ".join(bm25.tokenize(p["body"]))) for p in payloads])
        conn.commit()
        return conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    finally:
        conn.close()


def _build_vector(paths: ProjectPaths, payloads: list, stats: SyncStats) -> int:
    """별도 컬렉션을 지우고 다시 만든다. **컨텍스트 색인은 건드리지 않는다.**"""
    try:
        import chromadb
    except ImportError:
        stats.notes.append("chromadb 없음 — 벡터 채널 건너뜀")
        return 0
    paths.ensure_derived()
    client = chromadb.PersistentClient(path=str(paths.vector_db))
    model = embedding.model_name()
    try:
        client.delete_collection(COLLECTION)
    except Exception:                                   # noqa: BLE001
        pass
    col = client.create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine", "embed_model": model},
        embedding_function=embedding.build(model))
    col.add(ids=[p["file_id"] for p in payloads],
            documents=[p["body"] for p in payloads],
            metadatas=[{"domain": p["domain"],
                        "tier": p["tier"] if p["tier"] is not None else -1,
                        "tags": ",".join(p["tags"]),
                        "related_classes": ",".join(p["related_classes"]),
                        "collaborates_with": json.dumps(p["collaborates_with"],
                                                        ensure_ascii=False),
                        "path": p["path"]} for p in payloads])
    return col.count()


def sync(paths: ProjectPaths, *, force: bool = False, progress=None) -> SyncStats:
    """도메인 색인 전체 재빌드. `force=False` 면 지문이 같을 때 건너뛴다.

    🔴 **대상이 0이면 예외다.** 빈 색인을 조용히 만들면 "검색이 안 되는" 상태가 정상처럼
    보인다 — 우리가 반복해 온 실패 모양이다.
    """
    files = manifests(paths)
    if not files:
        raise DomainIndexError(
            f"색인할 도메인 패키지가 없다 — {paths.ontology / 'domains'} 를 확인하라. "
            f"빈 색인을 성공으로 보고하지 않는다")

    fp = fingerprint(paths)
    stats = SyncStats()
    if not force and fp and fp == stored_fingerprint(paths):
        # 🔴 건너뛸 때 **0 을 보고하지 않는다.** 살아 있는 색인 건수를 그대로 들고 나온다 —
        # "0건" 은 "색인이 비었다" 로 읽히고, 그건 우리가 고치려던 바로 그 오해다.
        prev = _read_stamp(paths)
        stats.notes.append(f"변화 없음 (지문 {fp}) — 건너뜀")
        stats.domains = prev.get("domains") or [p.parent.name for p in files]
        stats.synced = len(stats.domains)
        stats.bm25_count = int(prev.get("bm25") or 0)
        stats.vector_count = int(prev.get("vector") or 0)
        stats.skipped_unchanged = True
        return stats

    payloads: list = []
    for m in files:
        pl = payload(m)
        if pl is None or not pl["body"]:
            stats.skipped += 1
            stats.notes.append(f"{m.parent.name}: 본문이 비어 색인 제외")
            continue
        payloads.append(pl)
        if progress:
            progress(f"  {pl['domain']}: 본문 {len(pl['body'])}자 · 클래스 {len(pl['related_classes'])}")
    if not payloads:
        raise DomainIndexError("페이로드가 하나도 안 나왔다 — 도메인 manifest 를 확인하라")

    stats.synced = len(payloads)
    stats.domains = [p["domain"] for p in payloads]
    stats.bm25_count = _build_bm25(paths, payloads)
    stats.vector_count = _build_vector(paths, payloads, stats)
    _write_stamp(paths, fp, stats)
    return stats


# ── 검색 (소 2.1.2) ─────────────────────────────────────────────

def _bm25_hits(paths: ProjectPaths, query: str, limit: int) -> list:
    db = paths.bm25_domains_db
    if not db.is_file():
        return []
    tokens = bm25.tokenize(query)
    if not tokens:
        return []
    expr = " OR ".join(f'"{t}"' for t in tokens)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT file_id, bm25({TABLE}, 0.0, {WEIGHTS[0]}, {WEIGHTS[1]}, "
            f"{WEIGHTS[2]}, {WEIGHTS[3]}) AS s FROM {TABLE} "
            f"WHERE {TABLE} MATCH ? ORDER BY s LIMIT ?", (expr, limit)).fetchall()
        return [(r[0], round(-float(r[1]), 4)) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _vector_hits(paths: ProjectPaths, query: str, limit: int) -> list:
    try:
        import chromadb
    except ImportError:
        return []
    if not paths.vector_db.is_dir():
        return []
    try:
        client = chromadb.PersistentClient(path=str(paths.vector_db))
        model = embedding.model_name()
        col = client.get_collection(name=COLLECTION,
                                    embedding_function=embedding.build(model))
        r = col.query(query_texts=[query], n_results=limit)
        ids = (r.get("ids") or [[]])[0]
        dists = (r.get("distances") or [[]])[0]
        return [(i, round(1.0 - float(d), 4)) for i, d in zip(ids, dists)]
    except Exception:                                   # noqa: BLE001
        return []


def search_norms(paths: ProjectPaths, query: str, *, top_k: int = DEFAULT_TOP_K,
                 threshold: float = SIMILARITY_THRESHOLD) -> list:
    """질의 → 관련 도메인 규범. 🔴 **노이즈 3중 차단**(모듈 독스트링 참조).

    반환 항목에는 `path` 가 있다 — 호출자가 필요할 때 본문을 직접 읽으라는 뜻이고,
    그게 *문서는 지도지 정답이 아니다* 원칙에 맞는 형태다.
    """
    pool = max(top_k * 3, 5)
    hits = _bm25_hits(paths, query, pool)
    # ① 🔴 BM25 0건이면 끝. 도메인은 광범위 신호라 정확 매칭이 있어야 의미가 있다.
    if not hits:
        return []

    merged: dict = {}
    for rank, (fid, score) in enumerate(hits):
        merged[fid] = {"domain": fid, "bm25_score": score, "similarity": 0.0,
                       "_b": rank}
    for rank, (fid, sim) in enumerate(_vector_hits(paths, query, pool)):
        if fid in merged:
            merged[fid]["similarity"] = sim
            merged[fid]["_v"] = rank
        elif sim >= threshold:
            # ② 벡터 단독은 임계 이상만
            merged[fid] = {"domain": fid, "bm25_score": 0.0, "similarity": sim, "_v": rank}

    out: list = []
    for e in merged.values():
        rrf = 0.0
        for key in ("_v", "_b"):
            if key in e:
                rrf += 1.0 / (RRF_K + e[key])
        e["rrf_score"] = round(rrf, 6)
        e["source"] = ("vector+bm25" if "_v" in e and "_b" in e
                       else "bm25" if "_b" in e else "vector")
        e.pop("_v", None)
        e.pop("_b", None)
        man = paths.ontology / "domains" / e["domain"] / "domain.yaml"
        e["path"] = str(man)
        data = yaml_io.read(man) if man.is_file() else None
        if isinstance(data, dict):
            e["tier"] = data.get("tier")
            e["collaborates_with"] = data.get("collaborates_with") or []
            e["preview"] = str(data.get("summary") or "")[:PREVIEW]
        out.append(e)
    out.sort(key=lambda x: -x["rrf_score"])
    # ③ 개수 상한 — 규범은 곁들이는 것이지 결과 목록이 아니다
    return out[:top_k]
