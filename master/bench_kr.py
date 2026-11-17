"""한글 검색 정답 집합 벤치 (#211) — KR 라우팅·채널 게이팅 판정의 측정 도구.

[중요] **정답 집합 없이 검색을 손대지 않는다** (M2 규칙, bm25.py 실측 교훈 — "질의 3개를
눈으로 보는 것은 측정이 아니다"). 이 벤치가 그 정답 집합 위에서 네 변형을 잰다:

    baseline   현행 (KR 라우팅 꺼짐 · 2채널 RRF, limit 15 · 채널 풀 45)
    kr_on      AX_BM25_KR 켬 (한글 과반 질의는 trigram 테이블)
    gated      한글 전용 질의는 벡터 채널 게이팅 (BM25 단독, limit 15) — bm25.py 에 기록된 가설
    kr+gated   둘 다

정답 집합: 기본 `<트윈>/analysis/kr_ground_truth.tsv`, `--gt <경로>` 로 바꾼다.
    열: query / expected(|구분) / tier / source / confirmed(y/n) [/ candidate_id / request_id]
    natural    실사용 로그에서 온 질의 — 기대 문서는 **사람 확정**(confirmed=y)만 채점
    structural 별칭(사람 등록)·판별력 있는 한글 태그(≤5문서)에서 유도
    [주의] 주석은 `#` 다음이 공백(또는 줄 끝)인 줄만이다 — `#837 …` 처럼 일감 번호로 시작하는
    실사용 질의를 버리지 않는다(`#211` T3, 종전 `startswith("#")` 가 Q01 을 조용히 뺐다).

지표: hit@1 · hit@5 · MRR (기대 문서 중 하나라도 잡히면 hit). 질의 유형별로 따로 낸다:
    hangul_only  한글이 있고 식별자 토큰이 없다 — 게이팅 대상(bm25.py 가설의 범위)
    mixed        한글 + 식별자
    other        한글 없음

[중요] **운영 자료에 쓰지 않는다** (`#211` T3):
    · 측정은 `vector_db`·`bm25.db`·세대 마커·온톨로지의 **임시 사본**에서 한다 — 색인기가 도중에
      돌아도 결과가 흔들리지 않고, `Bm25Index` 생성자의 `CREATE … IF NOT EXISTS`·commit 도 사본에 간다.
    · 검색은 전부 `search_log.suppress_logging()` 안에서 한다 — 평가 검색이 실사용 로그 분모에
      섞이지 않는다(사본의 로그 경로까지 이중으로 막는다).

실행: AX_PROJECTS_ROOT=… .venv/bin/python master/bench_kr.py [--gt TSV] [--tier natural|structural] [--json]
"""
from __future__ import annotations

import dataclasses
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HANGUL_RE = re.compile(r"[가-힣]")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

GT_REL = Path("analysis") / "kr_ground_truth.tsv"
VARIANTS = (("baseline", False, False), ("kr_on", True, False),
            ("gated", False, True), ("kr+gated", True, True))
LIMIT = 15
LANG_TYPES = ("hangul_only", "mixed", "other")


def is_comment(line: str) -> bool:
    """`#` 다음이 공백이거나 줄 끝인 줄만 주석이다 — `#837 질의` 는 데이터다."""
    return line.startswith("#") and (len(line) == 1 or line[1].isspace())


def gt_path(paths=None, gt=None) -> Path:
    if gt:
        return Path(gt)
    return Path(paths.root) / GT_REL


def load_ground_truth(paths=None, *, gt=None) -> list:
    """확정(confirmed=y)이고 기대 문서가 있는 행만. 6·7 열(candidate_id·request_id)은 있으면 싣는다."""
    rows = []
    for ln in gt_path(paths, gt).read_text(encoding="utf-8").splitlines():
        if not ln.strip() or is_comment(ln):
            continue
        parts = ln.split("\t")
        if len(parts) < 5 or parts[4].strip() != "y" or not parts[1].strip():
            continue
        row = {"query": parts[0], "expected": [e for e in parts[1].split("|") if e],
               "tier": parts[2], "source": parts[3]}
        if len(parts) > 5 and parts[5].strip():
            row["id"] = parts[5].strip()
        if len(parts) > 6 and parts[6].strip():
            row["request_id"] = parts[6].strip()
        rows.append(row)
    return rows


def hangul_only(query: str) -> bool:
    """식별자 토큰이 없고 한글이 있는 질의 — 게이팅 대상 (bm25.py 가설의 범위)."""
    return bool(_HANGUL_RE.search(query)) and not _IDENT_RE.search(query)


def lang_type(query: str) -> str:
    if hangul_only(query):
        return "hangul_only"
    return "mixed" if _HANGUL_RE.search(query) else "other"


def rank_of(files, expected) -> int:
    """기대 문서 중 처음 잡힌 순위(1부터). 없으면 0."""
    return next((i + 1 for i, f in enumerate(files) if f in expected), 0)


def metrics(ranks) -> dict:
    ranks = list(ranks)
    n = len(ranks)
    d = n or 1
    return {"hit@1": sum(1 for r in ranks if r == 1) / d,
            "hit@5": sum(1 for r in ranks if 1 <= r <= 5) / d,
            "MRR": sum(1.0 / r for r in ranks if r) / d, "n": n}


# ── 색인 사본 ────────────────────────────────────────────────────────────────────

def snapshot_paths(paths, dest: Path) -> tuple:
    """검색이 읽는 파생물을 `dest` 로 복사한 `ProjectPaths` 와 그 기록을 돌려준다.

    `bm25.db` 는 sqlite backup API(쓰기 중에도 일관된 한 시점), `vector_db` 는 디렉터리 복사다.
    `context/` 는 읽기만 하므로 심볼릭 링크로 둔다. 원본에는 아무것도 쓰지 않는다.
    """
    from master.context_search import generation
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(paths.root)
    if Path(paths.vector_db).is_dir():
        shutil.copytree(paths.vector_db, dest / Path(paths.vector_db).name)
    if Path(paths.bm25_db).is_file():
        with closing(sqlite3.connect(f"file:{paths.bm25_db}?mode=ro", uri=True)) as s_conn, \
                closing(sqlite3.connect(str(dest / Path(paths.bm25_db).name))) as d_conn:
            s_conn.backup(d_conn)
    marker = generation.marker_path(src)
    if marker.is_file():
        shutil.copy2(marker, generation.marker_path(dest))
    if Path(paths.ontology).is_dir():
        shutil.copytree(paths.ontology, dest / Path(paths.ontology).name)
    if Path(paths.context).is_dir():
        (dest / Path(paths.context).name).symlink_to(Path(paths.context).resolve())
    snap = dataclasses.replace(paths, root=dest) if dataclasses.is_dataclass(paths) else paths
    info = {"source_root": str(src), "copied_at": datetime.now().astimezone().isoformat(),
            "generation": generation.read(dest)}
    return snap, info


# ── 측정 ────────────────────────────────────────────────────────────────────────

def run_variant(paths, rows, *, kr: bool, gated: bool, searcher_factory=None) -> dict:
    """한 변형의 지표와 질의별 순위. 검색은 전부 `suppress_logging` 안이다."""
    from master.context_search import bm25 as B
    from master.context_search import search_log
    from master.context_search.search import ContextSearch, focus
    from master.context_search.expand import expand_for

    factory = searcher_factory or ContextSearch
    old = B.KR_ROUTING
    B.KR_ROUTING = kr
    s = None
    try:
        with search_log.suppress_logging():
            s = factory(paths)
            per = []
            for r in rows:
                q0 = r["query"]
                if gated and hangul_only(q0):
                    q = focus(expand_for(paths, q0).query)
                    files = [f for f, _ in s.bm25.search(q, limit=LIMIT)]
                else:
                    files = [h.file_id for h in s.search(q0, limit=LIMIT)]
                per.append({"id": r.get("id", ""), "lang": lang_type(q0),
                            "rank": rank_of(files, r["expected"]), "top5": files[:5]})
        out = metrics(p["rank"] for p in per)
        out["by_lang"] = {t: metrics(p["rank"] for p in per if p["lang"] == t)
                          for t in LANG_TYPES}
        out["per_query"] = per
        return out
    finally:
        B.KR_ROUTING = old
        close = getattr(s, "close", None)
        if callable(close):
            close()


def run_all(paths, rows, *, searcher_factory=None) -> dict:
    return {name: run_variant(paths, rows, kr=kr, gated=gated,
                              searcher_factory=searcher_factory)
            for name, kr, gated in VARIANTS}


def _fmt(m) -> str:
    return f"{m['hit@1']:>7.3f} {m['hit@5']:>7.3f} {m['MRR']:>7.3f}   {m['n']}"


def report_text(rows, results, info) -> str:
    tiers, langs = {}, {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
        t = lang_type(r["query"])
        langs[t] = langs.get(t, 0) + 1
    out = [f"정답 집합: {len(rows)}건 (확정분만) · 계층 {tiers} · 유형 {langs}",
           f"색인 사본: 세대 {info.get('generation')} · 원본 {info.get('source_root')} · "
           f"복사 {info.get('copied_at')}"]
    if tiers.get("natural", 0) < 30:
        out.append("[주의] 자연 계층 표본이 30건 미만 — KR 라우팅 최종 판정은 보류가 규칙이다"
                   " (구조 계층은 방향 신호로만 읽는다)")
    out.append(f"{'변형':<10} {'유형':<12} {'hit@1':>7} {'hit@5':>7} {'MRR':>7}   n")
    for name, m in results.items():
        out.append(f"{name:<10} {'전체':<12} {_fmt(m)}")
        for t in LANG_TYPES:
            if m["by_lang"][t]["n"]:
                out.append(f"{'':<10} {t:<12} {_fmt(m['by_lang'][t])}")
    out.append("질의별 순위 (0 = 상위 15 밖)")
    names = list(results)
    out.append(f"{'id':<6} {'유형':<12} " + " ".join(f"{n:>9}" for n in names))
    for i, r in enumerate(rows):
        ranks = [results[n]["per_query"][i]["rank"] for n in names]
        out.append(f"{r.get('id', str(i + 1)):<6} {lang_type(r['query']):<12} "
                   + " ".join(f"{x:>9}" for x in ranks))
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="", help="정답 TSV 경로 (기본: <트윈>/analysis/kr_ground_truth.tsv)")
    ap.add_argument("--tier", default="", choices=["", "natural", "structural"])
    ap.add_argument("--json", action="store_true", help="지표·질의별 순위를 JSON 으로")
    args = ap.parse_args(argv)

    from master.context_search.paths import resolve
    paths = resolve("")
    rows = load_ground_truth(paths, gt=args.gt or None)
    if args.tier:
        rows = [r for r in rows if r["tier"] == args.tier]
    with tempfile.TemporaryDirectory(prefix="bench_kr-") as tmp:
        snap, info = snapshot_paths(paths, Path(tmp) / "twin")
        info["ground_truth"] = str(gt_path(paths, args.gt or None))
        results = run_all(snap, rows)
    if args.json:
        print(json.dumps({"snapshot": info, "rows": rows, "results": results},
                         ensure_ascii=False, indent=1))
    else:
        print(report_text(rows, results, info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
