"""검색 로그 분석 — 원전 `mcp/context_search/search_log_analyzer.py`(696줄) 이식
(소 3.4.2 · `#161`, 2026-08-14). Phase α — RAG 채널 분석·튜닝.

`search_log.jsonl` 누적분을 읽어 여섯을 잰다:

    1. 채널 기여도      vector / bm25 / vector+bm25 별 source 분포
    2. 언어별 갭        ko / en / mixed / other 별 채널 hit 비율
    3. BM25 0건 진단    0건 쿼리의 형태 (single-CamelCase · korean-only …)
    4. 시소러스 후보    [중요] **반복되는 0건 한국어 검색어** (원전 η.12.5)
    5. 도메인 빈도      결과 경로 첫 디렉토리 기준
    6. RRF k 튜닝       k=40/60/80 시뮬레이션 — 우리 `RRF_K=60` 이 맞는지

[중요] **stdlib 만 쓴다 — 외부 의존 0, LLM 0.** 원전이 이 자리에 값을 매긴 이유가 그것이다:
*"분석기는 stdlib 전용·LLM 0 이라 토큰 비용이 없다 — 배치 비용은 로그 1패스뿐."*

## [중요] 왜 이것이 「자동 판정」을 스스로 내리나

원전 주석 그대로: *"자동 배치는 사람이 실시간으로 「해석 가이드」를 읽지 않으므로, 각 섹션이
스스로 결론(verdict)을 내려야 한다."* 그래서 사람용 해석 가이드와 **별개로** 임계값 대비
결론을 붙인다. [중요] 그리고 **표본이 얇으면 결론 대신 「판단 보류」** 를 낸다 — 희소한 초기
데이터에서 오판하지 않기 위해서다(`MIN_TOTAL_SAMPLE`).

[주의] 우리에게 이 가드가 특히 중요하다: 로그를 **오늘 심었으므로**(소 3.4.5) 당장은 표본이
한 자릿수다. 첫 리포트는 *"판단 보류"* 로 나오는 것이 **정상이고 옳다.**

## 원전과 다르게 둔 것 셋

**① 입출력 경로.** 원전은 `<프로젝트>/.claude/…` 지만 §5.5 가 *"데이터를 프로젝트 밖으로"* 로
확정했다 → 입력 `ProjectPaths.search_log`, 출력 `<프로젝트 데이터>/analysis/`.

**② `tag` 채널이 우리에겐 없다.** 원전 융합은 vector+bm25+**tag** 3채널이고 우리는 2채널이다
(`search.fuse`). 관련 집계(`has_tag`)는 **지우지 않고 남긴다** — 늘 0으로 나오고, 그 0이
*"우리는 2채널이다"* 를 리포트에서 말해 준다. 지우면 나중에 tag 를 붙일 때 이 자리를 다시
찾아야 한다.

**③ 함수 정의 순서.** 원전은 `fmt_thesaurus_candidates` 를 쓰는 곳보다 **뒤에** 정의해 뒀다
(파이썬은 호출 시점에 해석하므로 동작한다). 여기서는 쓰는 순서대로 놓았다 — 동작은 같다.

[중요] **임계값·판정 문구는 바꾸지 않았다.** 바꾸면 과거 리포트와 비교가 안 된다
(`detect_lang` 의 5배 규칙을 그대로 둔 것과 같은 이유).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

# ─────────────────────────────────────────────────────────────
# 자동 판정 임계값 — [중요] **원전 값 그대로.** 운영 데이터로 보정될 수 있게 모듈 상수로 둔다
# (원전 주석: *"config 표면화는 과설계라 보류"*).
# ─────────────────────────────────────────────────────────────

MIN_TOTAL_SAMPLE = 30      # 전체 엔트리 최소치 — 이보다 적으면 verdict 를 「판단 보류」로 강등
MIN_LANG_SAMPLE = 10       # 언어 버킷별 최소치

LANG_GAP_PCT_THRESHOLD = 15.0     # ko 의 bm25_zero_% 가 en 대비 이 %p 이상이면 한국어 갭 의심
BM25_REDUNDANT_RATIO = 0.90       # bm25 hit 중 vec 동의 비율이 이 이상이면 단독 가치 낮음
RRF_TOP1_CHANGE_THRESHOLD = 20.0  # top-1 변경률이 이 % 이상인 k 가 있으면 튜닝 ROI 있음
RRF_OVERLAP_STABLE = 0.95         # top-5 overlap 이 이 이상이면 k=60 과 사실상 동일

CHANNEL_REPORT = "rag_channel_report.md"
LANGUAGE_REPORT = "language_gap_report.md"


def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """ISO 8601 파싱 — 여러 포맷을 허용한다. 못 읽으면 `None`(버리지 않고 무시)."""
    if not ts:
        return None
    s = ts.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def load_entries(log_path: Path, since: Optional[datetime] = None,
                 until: Optional[datetime] = None) -> Iterator[dict]:
    """JSONL 한 줄씩 — `since <= ts < until`. [중요] 깨진 줄은 건너뛴다(분석을 포기하지 않는다)."""
    log_path = Path(log_path)
    if not log_path.exists():
        return
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            ts = parse_ts(entry.get("ts")) if entry.get("ts") else None
            if since is not None and ts is not None and ts < since:
                continue
            if until is not None and ts is not None and ts >= until:
                continue
            yield entry


# ─────────────────────────────────────────────────────────────
# 분석 — [중요] 전부 순수 함수다. 입력이 같으면 출력이 같다
# ─────────────────────────────────────────────────────────────

def channel_breakdown(entries: list) -> dict:
    src_counter: Counter = Counter()
    total_entries = 0
    total_results = 0
    for entry in entries:
        total_entries += 1
        for r in entry.get("result_details", []) or []:
            total_results += 1
            src_counter[r.get("source", "unknown")] += 1
    return {"total_entries": total_entries, "total_results": total_results,
            "by_source": dict(src_counter.most_common())}


def language_gap(entries: list) -> dict:
    """언어별 채널 hit. [주의] `has_tag` 는 우리에게 늘 0 이다 (2채널) — 남겨 둔 이유는 머리말 ②."""
    table: dict = defaultdict(
        lambda: {"total": 0, "has_vec": 0, "has_bm25": 0, "has_both": 0,
                 "has_tag": 0, "bm25_zero": 0}
    )
    for entry in entries:
        row = table[entry.get("lang", "unknown")]
        row["total"] += 1
        sources = [r.get("source", "") for r in (entry.get("result_details", []) or [])]
        any_vec = any("vector" in s for s in sources)
        any_bm25 = any("bm25" in s for s in sources)
        any_tag = any(s == "tag" or "+tag" in s for s in sources)
        if any_vec:
            row["has_vec"] += 1
        if any_bm25:
            row["has_bm25"] += 1
        if any_vec and any_bm25:
            row["has_both"] += 1
        if any_tag:
            row["has_tag"] += 1
        if not any_bm25:
            row["bm25_zero"] += 1
    return dict(table)


_IDENT_RE = re.compile(r"[A-Z][A-Za-z0-9_]+")
_HANGUL_RE = re.compile(r"[가-힣]+")
# UE 타입 prefix (U=UObject · A=AActor · F=struct · E=enum · T=template · I=interface · S=Slate)
_UE_PREFIX_RE = re.compile(r"\b[UAFETIS][A-Z][A-Za-z0-9_]+")


def has_ue_prefix(query: str) -> bool:
    """쿼리에 UE 타입 prefix 형태 식별자가 있나.

    BM25 0건 진단의 보조 — prefix 없는 bare CamelCase(`MissionSubsystem`)는 인덱스의
    prefix 형(`UMissionSubsystem`)과 안 맞는 **갭 후보**다. `UISubsystem` 처럼 이미 prefix
    가 있는 형태와 구분한다.
    """
    return bool(_UE_PREFIX_RE.search(query))


def query_shape(query: str) -> str:
    if not query:
        return "empty"
    has_ident = bool(_IDENT_RE.search(query))
    has_hangul = bool(_HANGUL_RE.search(query))
    is_short = len(query.split()) <= 2
    if has_ident and not has_hangul and is_short:
        return "single-CamelCase"
    if has_ident and has_hangul:
        return "ident+korean-mixed"
    if has_hangul and not has_ident:
        return "korean-only"
    if has_ident and not has_hangul:
        return "ident-only-multi"
    return "other"


def bm25_zero_patterns(entries: list) -> dict:
    patterns: Counter = Counter()
    samples: dict = defaultdict(list)
    total_zero = 0
    ident_zero = 0
    ident_no_prefix = 0
    for entry in entries:
        details = entry.get("result_details", []) or []
        if details and any("bm25" in r.get("source", "") for r in details):
            continue
        total_zero += 1
        q = entry.get("query", "") or ""
        shape = query_shape(q)
        patterns[shape] += 1
        if len(samples[shape]) < 5:
            samples[shape].append(q[:80])
        if shape in ("single-CamelCase", "ident-only-multi", "ident+korean-mixed"):
            ident_zero += 1
            if not has_ue_prefix(q):
                ident_no_prefix += 1
    return {"total_bm25_zero": total_zero, "by_shape": dict(patterns.most_common()),
            "samples": dict(samples), "ident_zero": ident_zero,
            "ident_no_ue_prefix": ident_no_prefix}


def thesaurus_alias_candidates(entries: list, min_count: int = 2, top_n: int = 20) -> dict:
    """[중요] **반복되는 0건 한국어 검색어** → 시소러스 별칭 후보 (원전 η.12.5).

    전 채널이 0건인 한국어 쿼리는 *"그 개념을 가리키는 영문 클래스명 별칭이 시소러스에
    없다"* 는 신호일 확률이 높다. 영문 쿼리는 보통 클래스명 그대로라 신호가 약해 **제외**한다.
    같은 검색어가 반복되면(`min_count`) 우연이 아니라 **검색 습관**으로 본다.

    [중요] **후보 나열까지만 — 자동 반영은 없다.** 원전의 *"제안형 원칙"* 이고 우리 온톨로지
    규약(*"자동 승급 폐기 · 사람이 시켜야 부른다"*)과 같은 결이다.
    """
    counter: Counter = Counter()
    total_zero = 0
    total_ko_zero = 0
    for entry in entries:
        if not entry.get("zero_hit"):
            continue
        total_zero += 1
        q = (entry.get("query") or "").strip()
        if not q or entry.get("lang") != "ko":
            continue
        total_ko_zero += 1
        counter[q] += 1
    candidates = [(q, n) for q, n in counter.most_common(top_n) if n >= min_count]
    return {"total_zero_hit": total_zero, "total_ko_zero_hit": total_ko_zero,
            "candidates": candidates}


def domain_frequency(entries: list, top_n: int = 15) -> dict:
    """결과 경로의 **첫 디렉토리** 기준 빈도. 로그에 도메인 필드가 없어도 된다."""
    counter: Counter = Counter()
    for entry in entries:
        for r in entry.get("result_details", []) or []:
            f = (r.get("file", "") or "").replace("\\", "/")
            head = f.split("/", 1)[0] if "/" in f else f
            if head:
                counter[head] += 1
    return {"top": counter.most_common(top_n), "unique_domains": len(counter)}


def rrf_simulate(entries: list, k_values=(40, 60, 80), top_n: int = 5) -> dict:
    """`vec_rank`/`bm25_rank` 로 RRF 를 재계산해 k 별 top-N 안정성을 비교한다.

    [중요] **이것이 `result_details` 의 채널 필드를 요구하는 자리다.** `Hit.to_dict()` 로 로그를
    적었다면 여기가 통째로 빈다(소 3.4.5 머리말의 함정).
    """
    base_k = 60
    overlap_stats: dict = {k: [] for k in k_values}
    top1_change: dict = {k: 0 for k in k_values}
    n_entries = 0
    for entry in entries:
        details = entry.get("result_details", []) or []
        if not details:
            continue
        n_entries += 1

        def scored_for(k):
            out = []
            for r in details:
                score = 0.0
                if isinstance(r.get("vec_rank"), int):
                    score += 1.0 / (k + r["vec_rank"])
                if isinstance(r.get("bm25_rank"), int):
                    score += 1.0 / (k + r["bm25_rank"])
                out.append((r.get("file", ""), score))
            out.sort(key=lambda x: x[1], reverse=True)
            return [f for f, _ in out[:top_n]]

        base_top = scored_for(base_k)
        for k in k_values:
            top_k_files = scored_for(k)
            if base_top:
                overlap = len(set(top_k_files) & set(base_top)) / len(base_top)
                overlap_stats[k].append(overlap)
            if base_top and top_k_files and base_top[0] != top_k_files[0]:
                top1_change[k] += 1

    result = {"entries_analyzed": n_entries, "by_k": {}}
    for k in k_values:
        if not overlap_stats[k]:
            result["by_k"][k] = {"avg_overlap_with_k60": None, "top1_change_pct": 0.0}
            continue
        avg_overlap = sum(overlap_stats[k]) / len(overlap_stats[k])
        change_pct = (top1_change[k] / n_entries * 100) if n_entries else 0.0
        result["by_k"][k] = {"avg_overlap_with_k60": round(avg_overlap, 3),
                             "top1_change_pct": round(change_pct, 1)}
    return result


# ─────────────────────────────────────────────────────────────
# 자동 판정 — [중요] 문구·임계값 원전 그대로 (바꾸면 과거 리포트와 비교 불가)
# ─────────────────────────────────────────────────────────────

def verdict_channel(channel: dict, language: dict) -> str:
    has_bm25 = sum(row.get("has_bm25", 0) for row in language.values())
    has_both = sum(row.get("has_both", 0) for row in language.values())
    if has_bm25 == 0:
        return "BM25 hit 0 — 인덱스/토큰화 점검 필요 (BM25 채널이 거의 작동 안 함)"
    ratio = has_both / has_bm25
    if ratio >= BM25_REDUNDANT_RATIO:
        return (f"BM25 hit 의 {ratio*100:.0f}% 가 벡터와 중복 (≥{BM25_REDUNDANT_RATIO*100:.0f}%) "
                "→ BM25 단독 채널 가치 낮음 (RRF 효과 제한적)")
    return (f"BM25 hit 의 {ratio*100:.0f}% 만 벡터와 중복 "
            "→ 두 채널이 서로 다른 결과 보완 (RRF 효과 유효)")


def verdict_language(language: dict) -> str:
    ko = language.get("ko")
    en = language.get("en")
    if not ko or not en:
        return "ko/en 버킷 부족 — 언어 갭 비교 보류"
    if ko["total"] < MIN_LANG_SAMPLE or en["total"] < MIN_LANG_SAMPLE:
        return (f"표본 부족 (ko {ko['total']}/en {en['total']}, 최소 {MIN_LANG_SAMPLE}) "
                "— 언어 갭 판단 보류")
    ko_zero = ko["bm25_zero"] / ko["total"] * 100
    en_zero = en["bm25_zero"] / en["total"] * 100
    gap = ko_zero - en_zero
    if gap >= LANG_GAP_PCT_THRESHOLD:
        # [중요] 처방이 원전과 다르다 (#194 머지 지점 1, 2026-08-17). 원전은 "다국어 임베딩
        #    검토"를 권했지만 우리는 이미 다국어 모델이다(embedding.py) — 우리 지렛대는
        #    ① 태그·별칭 커버리지 (실측 4~7% 에서 멈춰 있다) ② KR 라우팅(정답 집합을 만든
        #    뒤에만 — bm25.py 의 실측 판정). 같은 신호, 우리 층에 맞는 답.
        return (f"ko bm25_zero {ko_zero:.0f}% vs en {en_zero:.0f}% (갭 {gap:.0f}%p "
                f"≥ {LANG_GAP_PCT_THRESHOLD:.0f}%p) → 한국어 갭 의심. 처방: 한글 태그·별칭 "
                f"커버리지 확대(현 4~7%), KR 라우팅은 정답 집합 이후 (다국어 임베딩은 이미 있음)")
    return (f"ko bm25_zero {ko_zero:.0f}% vs en {en_zero:.0f}% (갭 {gap:.0f}%p) "
            "→ 한국어 갭 임계 미만, 현 임베딩 유지 근거")


def verdict_rrf(rrf: dict) -> str:
    by_k = rrf.get("by_k", {})
    if not by_k:
        return "RRF 데이터 없음 — 판단 보류"
    max_change = 0.0
    max_change_k = None
    for k, row in by_k.items():
        c = row.get("top1_change_pct", 0.0) or 0.0
        if c > max_change:
            max_change, max_change_k = c, k
    if max_change >= RRF_TOP1_CHANGE_THRESHOLD:
        return (f"k={max_change_k} 에서 top-1 변경률 {max_change:.0f}% "
                f"(≥ {RRF_TOP1_CHANGE_THRESHOLD:.0f}%) → k 튜닝 ROI 있음, 재평가 권고")
    return (f"최대 top-1 변경률 {max_change:.0f}% (< {RRF_TOP1_CHANGE_THRESHOLD:.0f}%) "
            "→ k 변화 영향 미미, 현 k=60 유지")


def verdict_zero_patterns(zero: dict) -> str:
    ident_zero = zero.get("ident_zero", 0)
    no_prefix = zero.get("ident_no_ue_prefix", 0)
    if ident_zero == 0:
        return "ident 포함 0건 쿼리 없음 — prefix-gap 진단 불가"
    pct = no_prefix / ident_zero * 100
    return (f"ident 포함 0건 {ident_zero}건 중 {no_prefix}건({pct:.0f}%) 이 UE prefix 없음 "
            "→ prefix-gap 후보 (검색 시 U/A/F 접두 누락 가능성)")


def verdict_thesaurus_candidates(result: dict) -> str:
    candidates = result.get("candidates", [])
    if not candidates:
        return "반복 0건 한국어 검색어 없음 — 시소러스 갭 후보 없음"
    top_q, top_n = candidates[0]
    return (f"0건 반복 검색어 {len(candidates)}건 발견 (최다: `{top_q}` {top_n}회) "
            "— 별칭 등록 검토 권장 (자동 반영 아님, 사람 확인 필요)")


def _verdict_line(text: str, sample_ok: bool) -> list:
    """[중요] 표본이 얇으면 **결론을 내지 않는다.** 오판이 무판정보다 비싸다."""
    if not sample_ok:
        return ["**자동 판정**: 표본 부족 — 판단 보류", ""]
    return [f"**자동 판정**: {text}", ""]


# ─────────────────────────────────────────────────────────────
# 리포트 포매팅
# ─────────────────────────────────────────────────────────────

def fmt_summary(entries: list, label: str = "") -> list:
    out = []
    if label:
        out += [f"## {label}", ""]
    out.append(f"- 총 엔트리: **{len(entries)}**")
    if entries:
        out.append(f"- 기간: {entries[0].get('ts', '?')} ~ {entries[-1].get('ts', '?')}")
        lang_counter: Counter = Counter()
        for e in entries:
            lang_counter[e.get("lang", "unknown")] += 1
        out.append("- 언어 분포: "
                   + ", ".join(f"{lang} {n}" for lang, n in lang_counter.most_common()))
    out.append("")
    return out


def fmt_channel(result: dict) -> list:
    out = ["### 채널 기여도 (source 별)", ""]
    out += [f"전체 결과 row 수: **{result['total_results']}** ({result['total_entries']} 엔트리)",
            "", "| source | 건수 | 비율 |", "|--------|------|------|"]
    total = result["total_results"] or 1
    for src, n in result["by_source"].items():
        out.append(f"| `{src}` | {n} | {n / total * 100:.1f}% |")
    out.append("")
    return out


def fmt_language(result: dict) -> list:
    out = ["### 언어별 채널 hit 분포", "",
           "| lang | total | vec_hit | bm25_hit | both | tag | bm25_zero | bm25_zero_% |",
           "|------|-------|---------|----------|------|-----|-----------|-------------|"]
    for lang in sorted(result.keys()):
        row = result[lang]
        total = row["total"] or 1
        out.append(f"| {lang} | {row['total']} | {row['has_vec']} | {row['has_bm25']} | "
                   f"{row['has_both']} | {row['has_tag']} | {row['bm25_zero']} | "
                   f"{row['bm25_zero'] / total * 100:.1f}% |")
    out += ["", "**해석 가이드**:",
            "- `bm25_zero_%` 가 ko 에서 en 대비 현저히 높으면 → 한국어 토큰화/인덱싱 갭",
            "- `has_both` 가 낮으면 → 두 채널이 서로 다른 결과를 찾고 있다 (RRF 효과 큼)",
            "- `has_vec` ≈ `has_both` 면 → BM25 가 거의 항상 벡터에 동의 → 단독 가치 낮음",
            "- [주의] `tag` 는 우리에게 **늘 0** 이다 — 융합이 2채널이다 (원전은 3채널)", ""]
    return out


def fmt_zero_patterns(result: dict) -> list:
    out = ["### BM25 0건 진단 패턴", ""]
    total = result["total_bm25_zero"]
    out += [f"BM25 hit 0건 엔트리: **{total}건**", ""]
    if total == 0:
        return out + ["(0건 케이스 없음)", ""]
    out += ["| 쿼리 형태 | 건수 | 비율 | 샘플 |", "|----------|------|------|------|"]
    for shape, n in result["by_shape"].items():
        sample = "; ".join(result["samples"].get(shape, [])[:3]).replace("|", "\\|")
        out.append(f"| `{shape}` | {n} | {n / total * 100:.1f}% | {sample} |")
    out.append("")
    ident_zero = result.get("ident_zero", 0)
    if ident_zero:
        out += [f"- ident 포함 0건 쿼리 {ident_zero}건 중 "
                f"**{result.get('ident_no_ue_prefix', 0)}건** 이 UE 타입 prefix 없음 "
                "(prefix-gap 후보)", ""]
    out += ["**해석 가이드**:",
            "- `single-CamelCase` 가 많으면 → UE prefix gap (`UISubsystem` vs 인덱스 `UUISubsystem`)",
            "- `ident+korean-mixed` 가 많으면 → 다중 토큰에서 어느 토큰도 안 잡힘 (인덱싱 누락)",
            "- `korean-only` 가 많으면 → 한국어 어절 매칭 자체가 약함 — 처방은 한글 태그·별칭 "
            "커버리지 (다국어 임베딩은 이미 있음, #194 지점 1)",
            "- [주의] 로그의 질의는 `focus()` **이전 원문**이다 (실측) — `[대괄호]` 질의는 "
            "실제 검색 때 괄호 안만 남는다. 대괄호 질의의 형태 통계는 그만큼 보수적으로 읽는다 "
            "(#194 지점 2)", ""]
    return out


def fmt_thesaurus_candidates(result: dict) -> list:
    out = ["### 시소러스 별칭 후보 (0건 검색어)", ""]
    out += [f"결과 0건 엔트리: **{result['total_zero_hit']}건** "
            f"(한국어 쿼리: {result['total_ko_zero_hit']}건)", ""]
    candidates = result.get("candidates", [])
    if not candidates:
        return out + ["(반복 0건 한국어 검색어 없음 — 후보 없음)", ""]
    out += ["| 검색어 | 0건 반복 횟수 |", "|--------|--------------|"]
    for q, n in candidates:
        out.append(f"| `{q.replace('|', chr(92) + '|')}` | {n} |")
    out += ["", "**해석 가이드**: 반복되는 0건 한국어 검색어는 클래스 별칭 등록 후보다. "
            "대상 클래스가 확인되면 사람이 `add_alias_tool(클래스, 표현)` 로 등록한다 — "
            "[중요] 여기 나열은 **후보 제안일 뿐 자동 반영되지 않는다.**", ""]
    return out


def fmt_domain(result: dict) -> list:
    out = ["### 도메인별 검색 빈도 (결과 경로 첫 디렉토리)", "",
           f"- 고유 도메인 수: {result['unique_domains']}", "",
           "| 도메인 | 결과 등장 수 |", "|--------|-------------|"]
    for name, n in result["top"]:
        out.append(f"| `{name}` | {n} |")
    out.append("")
    return out


def fmt_rrf(result: dict) -> list:
    out = ["### RRF k 튜닝 비교", "", f"분석한 엔트리: {result['entries_analyzed']}", "",
           "| k | top-5 overlap with k=60 | top-1 변경률 |",
           "|---|------------------------|--------------|"]
    for k, row in result["by_k"].items():
        ov = row.get("avg_overlap_with_k60")
        out.append(f"| {k} | {f'{ov:.3f}' if ov is not None else '—'} | "
                   f"{row['top1_change_pct']}% |")
    out += ["", "**해석 가이드**:",
            f"- overlap 이 {RRF_OVERLAP_STABLE}+ 면 → k 변화 영향 미미. 현 k=60 유지",
            f"- top-1 변경률 {RRF_TOP1_CHANGE_THRESHOLD:.0f}%+ 면 → k 튜닝 ROI 있음", ""]
    return out


# ─────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────

def _analyze_window(entries: list, label: str = "") -> list:
    sample_ok = len(entries) >= MIN_TOTAL_SAMPLE
    channel = channel_breakdown(entries)
    language = language_gap(entries)
    zero = bm25_zero_patterns(entries)
    thesaurus = thesaurus_alias_candidates(entries)
    domain = domain_frequency(entries)
    rrf = rrf_simulate(entries)

    out = fmt_summary(entries, label=label)
    if not sample_ok:
        out += [f"> [주의] 표본 {len(entries)}건 < 최소 {MIN_TOTAL_SAMPLE}건 — "
                "자동 판정은 보류 처리됐다 (수치는 참고용)", ""]
    out += fmt_channel(channel)
    out += _verdict_line(verdict_channel(channel, language), sample_ok)
    out += fmt_language(language)
    out += _verdict_line(verdict_language(language), sample_ok)
    out += fmt_zero_patterns(zero)
    out += _verdict_line(verdict_zero_patterns(zero), sample_ok)
    out += fmt_thesaurus_candidates(thesaurus)
    out += _verdict_line(verdict_thesaurus_candidates(thesaurus), sample_ok)
    out += fmt_domain(domain)
    out += fmt_rrf(rrf)
    out += _verdict_line(verdict_rrf(rrf), sample_ok)
    return out


def analyze(log_path, since: str = "", until: str = "", compare_at: str = "") -> str:
    """분석 리포트 문자열 (사람이 부르는 진입점). `compare_at` 을 주면 Pre/Post 두 창으로."""
    log_path = Path(log_path)
    if not log_path.exists():
        return f"# 분석 불가\n\n로그 파일 없음: `{log_path}`"

    s = parse_ts(since) if since else None
    u = parse_ts(until) if until else None
    p = parse_ts(compare_at) if compare_at else None

    report = ["# 검색 로그 분석 리포트", "", f"- 로그: `{log_path}`"]
    for label, v in (("since", s), ("until", u), ("compare-at", p)):
        if v:
            report.append(f"- {label}: {v.isoformat()}")
    report.append("")

    if p is None:
        report += _analyze_window(list(load_entries(log_path, since=s, until=u)))
    else:
        report += ["---", "## Pre (변경 이전)", ""]
        report += _analyze_window(list(load_entries(log_path, since=s, until=p)),
                                  label=f"기간: ~ {p.isoformat()}")
        report += ["---", "## Post (변경 이후)", ""]
        report += _analyze_window(list(load_entries(log_path, since=p, until=u)),
                                  label=f"기간: {p.isoformat()} ~")
    return "\n".join(report)


def _report_header(title: str, log_path, entries: list) -> list:
    out = [f"# {title}", "", f"- 로그: `{log_path}`",
           "- 생성: 자동 배치 (Phase α — RAG 채널 분석·튜닝)",
           f"- 엔트리: {len(entries)}건"]
    if len(entries) < MIN_TOTAL_SAMPLE:
        out.append(f"> [주의] 표본 {len(entries)}건 < 최소 {MIN_TOTAL_SAMPLE}건 — "
                   "자동 판정 보류 (수치는 참고용)")
    out.append("")
    return out


def generate_reports(log_path, out_dir, since: str = "", until: str = "") -> dict:
    """[중요] **배치 진입점** — 두 리포트 파일을 `out_dir` 에 쓴다 (원전 부록 B 구조).

        rag_channel_report.md    요약 + 채널 기여도 + RRF k 튜닝 + 도메인 빈도
        language_gap_report.md   요약 + 언어별 갭 + BM25 0건 진단 + 시소러스 별칭 후보

    반환 `{ok, entries, files, reason}` — [중요] **예외를 올리지 않고 값으로 말한다**(배치 안전).
    """
    log_path = Path(log_path)
    out_dir = Path(out_dir)
    if not log_path.exists():
        return {"ok": False, "entries": 0, "files": [], "reason": f"로그 없음: {log_path}"}

    s = parse_ts(since) if since else None
    u = parse_ts(until) if until else None
    entries = list(load_entries(log_path, since=s, until=u))
    sample_ok = len(entries) >= MIN_TOTAL_SAMPLE

    channel = channel_breakdown(entries)
    language = language_gap(entries)
    zero = bm25_zero_patterns(entries)
    thesaurus = thesaurus_alias_candidates(entries)
    domain = domain_frequency(entries)
    rrf = rrf_simulate(entries)

    ch = _report_header("RAG 채널 분석 리포트", log_path, entries)
    ch += fmt_channel(channel)
    ch += _verdict_line(verdict_channel(channel, language), sample_ok)
    ch += fmt_rrf(rrf)
    ch += _verdict_line(verdict_rrf(rrf), sample_ok)
    ch += fmt_domain(domain)

    lg = _report_header("RAG 언어별 갭 리포트", log_path, entries)
    lg += fmt_language(language)
    lg += _verdict_line(verdict_language(language), sample_ok)
    lg += fmt_zero_patterns(zero)
    lg += _verdict_line(verdict_zero_patterns(zero), sample_ok)
    lg += fmt_thesaurus_candidates(thesaurus)
    lg += _verdict_line(verdict_thesaurus_candidates(thesaurus), sample_ok)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        ch_path = out_dir / CHANNEL_REPORT
        lg_path = out_dir / LANGUAGE_REPORT
        ch_path.write_text("\n".join(ch) + "\n", encoding="utf-8")
        lg_path.write_text("\n".join(lg) + "\n", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "entries": len(entries), "files": [],
                "reason": f"리포트 쓰기 실패: {e}"}
    return {"ok": True, "entries": len(entries),
            "files": [str(ch_path), str(lg_path)], "reason": ""}


def run_for_project(paths, *, since: str = "", until: str = "") -> dict:
    """우리 경로 규약으로 부르는 얇은 래퍼 (원전 `watcher/rag_report.run_rag_analysis` 자리).

    입력 `ProjectPaths.search_log` · 출력 `<프로젝트 데이터>/analysis/` — §5.5.
    """
    return generate_reports(paths.search_log, Path(paths.root) / "analysis",
                            since=since, until=until)
