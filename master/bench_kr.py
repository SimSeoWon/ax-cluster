"""한글 검색 정답 집합 벤치 (#211) — KR 라우팅·채널 게이팅 판정의 측정 도구.

[중요] **정답 집합 없이 검색을 손대지 않는다** (M2 규칙, bm25.py 실측 교훈 — "질의 3개를
눈으로 보는 것은 측정이 아니다"). 이 벤치가 그 정답 집합 위에서 네 변형을 잰다:

    baseline   현행 (KR 라우팅 꺼짐 · 2채널 RRF)
    kr_on      AX_BM25_KR 켬 (한글 과반 질의는 trigram 테이블)
    gated      한글 전용 질의는 벡터 채널 게이팅 (BM25 단독) — bm25.py 에 기록된 가설
    kr+gated   둘 다

정답 집합: `<트윈>/analysis/kr_ground_truth.tsv` (query / expected / tier / source / confirmed)
    natural    실사용 로그에서 온 질의 — 기대 문서는 **사람 확정**(confirmed=y)만 채점
    structural 별칭(사람 등록)·판별력 있는 한글 태그(≤5문서)에서 유도

지표: hit@1 · hit@5 · MRR (기대 문서 중 하나라도 잡히면 hit).

실행: AX_PROJECTS_ROOT=… .venv/bin/python master/bench_kr.py [--tier natural|structural]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HANGUL_RE = re.compile(r"[가-힣]")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def load_ground_truth(paths) -> list:
    p = Path(paths.root) / "analysis" / "kr_ground_truth.tsv"
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) < 5 or parts[4].strip() != "y" or not parts[1].strip():
            continue
        rows.append({"query": parts[0], "expected": [e for e in parts[1].split("|") if e],
                     "tier": parts[2], "source": parts[3]})
    return rows


def hangul_only(query: str) -> bool:
    """식별자 토큰이 없고 한글이 있는 질의 — 게이팅 대상 (bm25.py 가설의 범위)."""
    return bool(_HANGUL_RE.search(query)) and not _IDENT_RE.search(query)


def run_variant(paths, rows, *, kr: bool, gated: bool) -> dict:
    from master.context_search import bm25 as B
    from master.context_search.search import ContextSearch, focus, fuse
    from master.context_search.expand import expand_for

    old = B.KR_ROUTING
    B.KR_ROUTING = kr
    try:
        s = ContextSearch(paths)
        hit1 = hit5 = 0
        mrr = 0.0
        for r in rows:
            q0 = r["query"]
            ex = expand_for(paths, q0)
            q = focus(ex.query)
            if gated and hangul_only(q0):
                pairs = s.bm25.search(q, limit=15)
                files = [f for f, _ in pairs]
            else:
                files = [h.file_id for h in s.search(q0, limit=15)]
            rank = next((i + 1 for i, f in enumerate(files) if f in r["expected"]), 0)
            if rank == 1:
                hit1 += 1
            if 1 <= rank <= 5:
                hit5 += 1
            if rank:
                mrr += 1.0 / rank
        n = len(rows) or 1
        return {"hit@1": hit1 / n, "hit@5": hit5 / n, "MRR": mrr / n, "n": len(rows)}
    finally:
        B.KR_ROUTING = old


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="", choices=["", "natural", "structural"])
    args = ap.parse_args(argv)

    from master.context_search.paths import resolve
    paths = resolve("")
    rows = load_ground_truth(paths)
    if args.tier:
        rows = [r for r in rows if r["tier"] == args.tier]
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    print(f"정답 집합: {len(rows)}건 (확정분만) · 계층 {tiers}")
    if len([r for r in rows if r['tier'] == 'natural']) < 30:
        print("[주의] 자연 계층 표본이 30건 미만 — KR 라우팅 최종 판정은 보류가 규칙이다"
              " (구조 계층은 방향 신호로만 읽는다)")

    variants = [("baseline", False, False), ("kr_on", True, False),
                ("gated", False, True), ("kr+gated", True, True)]
    print(f"{'변형':<10} {'hit@1':>7} {'hit@5':>7} {'MRR':>7}   n")
    for name, kr, gated in variants:
        m = run_variant(paths, rows, kr=kr, gated=gated)
        print(f"{name:<10} {m['hit@1']:>7.3f} {m['hit@5']:>7.3f} {m['MRR']:>7.3f}   {m['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
