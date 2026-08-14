"""유휴 배치 — 자리(소 3.4.4 · `#192`) + 첫 배치(소 3.4.2 · `#161`).

검증하는 것:

    ① 시간 게이트 조건 다섯 — 각각이 **단독으로** 막는다 (원전 순서 그대로)
    ② 🔴 안 도는 이유가 **항상 있다** (고장과 구별되려면)
    ③ 마커 — 쓰고 읽고, 최소 간격이 실제로 막는다
    ④ 🔴 마커는 **성공했을 때만** 쓴다 (실패하면 다음 회차에 다시 온다)
    ⑤ 🔴 `force` 는 시각·요일·간격·입력최소치를 넘지만 **활성 플래그·일시 중지 게이트는 못 넘는다**
    ⑥ 배치 하나가 죽어도 나머지가 돌고, **조용히 넘어가지 않는다**
    ⑦ 분석기 — 표본이 얇으면 🔴 **판단을 보류**한다 (오판이 무판정보다 비싸다)
    ⑧ 분석기 — 채널 필드가 있으면 RRF 시뮬레이션이 실제로 돈다

`.venv/bin/python master/test_batch.py`
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.batch import gates, run as R                          # noqa: E402
from master.context_search import search_log_analyzer as A        # noqa: E402

PASS = FAIL = 0

# 일요일 23시 — `RAG_ANALYSIS` 게이트가 통과하는 시점
SUNDAY_23 = datetime(2026, 8, 16, 23, 30)


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


@dataclass
class Paths:
    root: Path
    name: str = "T"

    @property
    def search_log(self) -> Path:
        return self.root / "search_log.jsonl"

    @property
    def config(self) -> Path:
        return self.root / "config.yaml"


def _paths(tmp) -> Paths:
    p = Paths(root=Path(tmp) / "proj")
    p.root.mkdir(parents=True, exist_ok=True)
    return p


# ── ①② 게이트 ───────────────────────────────────────────────────────────────

def test_each_condition_blocks_alone():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        S = gates.RAG_ANALYSIS

        v = gates.should_run(S, {}, p.root, input_count=50, now=SUNDAY_23)
        check("① 전부 충족하면 돈다", v.run, v.reason)

        v = gates.should_run(S, {"batch": {"rag_analysis": False}}, p.root,
                             input_count=50, now=SUNDAY_23)
        check("① 활성 조건이 단독으로 막는다", not v.run and "꺼져" in v.reason, v.reason)

        v = gates.should_run(S, {}, p.root, input_count=3, now=SUNDAY_23)
        check("① 입력 최소치가 단독으로 막는다", not v.run and "입력 부족" in v.reason, v.reason)

        v = gates.should_run(S, {}, p.root, input_count=50,
                             now=SUNDAY_23.replace(hour=9))
        check("① 시각이 단독으로 막는다", not v.run and "시각 미달" in v.reason, v.reason)

        v = gates.should_run(S, {}, p.root, input_count=50,
                             now=SUNDAY_23 - timedelta(days=2))   # 금요일
        check("① 요일이 단독으로 막는다", not v.run and "요일 불일치" in v.reason, v.reason)

        # ② 어떤 판정이든 이유가 비지 않는다
        for kwargs in ({"input_count": 50}, {"input_count": 0}):
            v = gates.should_run(S, {}, p.root, now=SUNDAY_23, **kwargs)
            check("② 이유가 항상 있다", bool(v.reason.strip()), repr(v.reason))


def test_config_overrides_use_origin_key_names():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        cfg = {"batch": {"rag_analysis_hour": 1, "rag_analysis_schedule": "daily",
                         "rag_analysis_min_entries": 2}}
        v = gates.should_run(gates.RAG_ANALYSIS, cfg, p.root, input_count=3,
                            now=SUNDAY_23.replace(hour=2))
        check("① config 로 시각·스케줄·최소치를 덮는다", v.run, v.reason)


def test_marker_gap_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        m = gates.write_marker(p.root, "rag_analysis", now=SUNDAY_23)
        check("③ 마커를 썼다", m["ok"], str(m))
        back = gates.read_marker(p.root, "rag_analysis")
        check("③ 마커를 읽는다", back is not None and back.hour == 23, str(back))

        # ⚠️ 같은 일요일 안에 머물러야 한다 — 자정을 넘기면 **요일·시각 게이트가 먼저**
        #    막아 간격 게이트를 재지 못한다(원전 순서상 정상 동작이고, 첫 판이 거기 걸렸다).
        v = gates.should_run(gates.RAG_ANALYSIS, {}, p.root, input_count=50,
                             now=SUNDAY_23 + timedelta(minutes=20))
        check("③ 🔴 최소 간격이 막는다", not v.run and "간격 미달" in v.reason, v.reason)

        v = gates.should_run(gates.RAG_ANALYSIS, {}, p.root, input_count=50,
                             now=SUNDAY_23 + timedelta(days=7))
        check("③ 간격이 지나면 다시 돈다", v.run, v.reason)


def test_broken_marker_is_treated_as_absent():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        mp = gates.marker_path(p.root, "rag_analysis")
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text("깨진 타임스탬프", encoding="utf-8")
        check("③ 깨진 마커는 없는 것으로 본다 (한 번 더 도는 쪽이 안전)",
              gates.read_marker(p.root, "rag_analysis") is None)


# ── ④⑤⑥ 구동 ────────────────────────────────────────────────────────────────

def _fake_batch(*, ok=True, boom=False, key="rag_analysis"):
    def execute(paths):
        if boom:
            raise RuntimeError("배치가 터졌다")
        return {"ok": ok, "reason": "" if ok else "내부 실패", "entries": 7}
    return R.BatchDef(schedule=gates.Schedule(key=key, hour=0, schedule="daily",
                                              min_entries=1),
                      label="가짜", count_input=lambda p: 5, execute=execute)


def test_marker_only_on_success():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        orig = R.BATCHES
        try:
            R.BATCHES = [_fake_batch(ok=False)]
            out = R.run(p, {}, now=SUNDAY_23)
            check("④ 실패는 error 로 보고된다", bool(out[0].error), str(out[0].result))
            check("④ 🔴 실패하면 마커를 쓰지 않는다",
                  gates.read_marker(p.root, "rag_analysis") is None)

            R.BATCHES = [_fake_batch(ok=True)]
            out = R.run(p, {}, now=SUNDAY_23)
            check("④ 성공하면 돌았다고 보고", out[0].ran and out[0].ok, str(out[0].error))
            check("④ 성공 시 마커를 쓴다",
                  gates.read_marker(p.root, "rag_analysis") is not None)
        finally:
            R.BATCHES = orig


def test_exception_is_not_swallowed():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        orig = R.BATCHES
        try:
            R.BATCHES = [_fake_batch(boom=True), _fake_batch(ok=True, key="other")]
            out = R.run(p, {}, now=SUNDAY_23)
            check("⑥ 죽은 배치가 error 로 남는다",
                  "터졌다" in (out[0].error or ""), out[0].error)
            check("⑥ 나머지는 돌았다", out[1].ran, str(out[1].error))
        finally:
            R.BATCHES = orig


def test_force_skips_time_gate_only():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        orig = R.BATCHES
        try:
            # 시각을 못 넘기는 게이트
            b = _fake_batch(ok=True)
            b = R.BatchDef(schedule=gates.Schedule(key="rag_analysis", hour=23,
                                                   schedule="weekly", day="sunday",
                                                   min_entries=1),
                           label=b.label, count_input=b.count_input, execute=b.execute)
            R.BATCHES = [b]
            out = R.run(p, {}, now=SUNDAY_23.replace(hour=5))
            check("⑤ 시각 미달이면 안 돈다", not out[0].ran, out[0].verdict)
            out = R.run(p, {}, now=SUNDAY_23.replace(hour=5), force=True)
            check("⑤ force 면 시간 게이트를 넘는다", out[0].ran, out[0].verdict)
            check("⑤ force 를 이유에 남긴다", "force" in out[0].verdict, out[0].verdict)

            # 🔴 force 도 활성 플래그는 못 넘는다 — 운영자가 끈 것을 되살리지 않는다
            out = R.run(p, {"batch": {"rag_analysis": False}},
                        now=SUNDAY_23.replace(hour=5), force=True)
            check("⑤ 🔴 force 가 활성 플래그를 넘지 못한다", not out[0].ran, out[0].verdict)
            check("⑤ 그 사실을 이유에 적는다", "force 무시됨" in out[0].verdict,
                  out[0].verdict)
        finally:
            R.BATCHES = orig


def test_plan_has_no_side_effects():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        orig = R.BATCHES
        try:
            R.BATCHES = [_fake_batch(ok=True)]
            out = R.plan(p, {}, now=SUNDAY_23)
            check("plan 은 돌 것을 알려 준다", out[0].result.get("would_run") is True,
                  str(out[0].result))
            check("🔴 plan 은 마커를 쓰지 않는다",
                  gates.read_marker(p.root, "rag_analysis") is None)
        finally:
            R.BATCHES = orig


# ── ⑦⑧ 분석기 ───────────────────────────────────────────────────────────────

def _write_log(p: Paths, entries: list) -> None:
    p.search_log.parent.mkdir(parents=True, exist_ok=True)
    p.search_log.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
                            + "\n", encoding="utf-8")


def _entry(query, lang, files, *, both=True, zero=False):
    details = []
    for i, f in enumerate(files, start=1):
        d = {"file": f, "source": "vector+bm25" if both else "vector",
             "rrf_score": 0.03, "vec_rank": i}
        if both:
            d["bm25_rank"] = i
        details.append(d)
    e = {"ts": "2026-08-14T23:00:00", "results": files, "query": query, "lang": lang,
         "result_details": details}
    if zero:
        e["zero_hit"] = True
    return e


def test_thin_sample_withholds_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        _write_log(p, [_entry("MissionTask", "en", ["Source/A.md"])])
        res = A.run_for_project(p)
        check("⑦ 리포트가 생성됐다", res["ok"], str(res))
        body = (Path(p.root) / "analysis" / A.CHANNEL_REPORT).read_text(encoding="utf-8")
        check("⑦ 🔴 표본 부족을 명시한다", "표본" in body and "판단 보류" in body,
              body[:200])
        check("⑦ 수치는 그대로 낸다 (참고용)", "채널 기여도" in body, body[:200])


def test_rrf_simulation_runs_with_channel_fields():
    entries = [_entry(f"Q{i}", "en", [f"Source/{i}_a.md", f"Source/{i}_b.md"])
               for i in range(A.MIN_TOTAL_SAMPLE + 2)]
    rrf = A.rrf_simulate(entries)
    check("⑧ RRF 시뮬레이션이 엔트리를 봤다",
          rrf["entries_analyzed"] == len(entries), str(rrf["entries_analyzed"]))
    check("⑧ k 별 결과가 있다", set(rrf["by_k"]) == {40, 60, 80}, str(rrf["by_k"]))
    check("⑧ k=60 은 자기 자신과 overlap 1.0",
          rrf["by_k"][60]["avg_overlap_with_k60"] == 1.0, str(rrf["by_k"][60]))


def test_channel_fields_absent_means_empty_rrf():
    """🔴 `to_dict()` 로 로그를 적었다면 이 자리가 통째로 빈다 — 그 사실을 고정한다."""
    entries = [{"ts": "2026-08-14T23:00:00", "query": "x", "lang": "en",
                "result_details": [{"file": "a.md", "source": "vector+bm25"}]}]
    rrf = A.rrf_simulate(entries)
    check("⑧ 채널 필드가 없으면 overlap 이 비거나 0 이다",
          rrf["by_k"][40]["avg_overlap_with_k60"] in (None, 1.0), str(rrf["by_k"][40]))


def test_thesaurus_candidates_need_repetition():
    base = {"ts": "2026-08-14T23:00:00", "lang": "ko", "zero_hit": True,
            "result_details": []}
    once = [dict(base, query="미션연출")]
    twice = [dict(base, query="미션연출"), dict(base, query="미션연출")]
    check("⑦ 1회는 후보가 아니다",
          A.thesaurus_alias_candidates(once)["candidates"] == [])
    check("⑦ 반복되면 후보다 (검색 습관)",
          A.thesaurus_alias_candidates(twice)["candidates"] == [("미션연출", 2)])
    # 영문 0건은 제외한다 (별칭 갭 신호가 약하다 — 원전 판단)
    en = [dict(base, query="MissionTask", lang="en"),
          dict(base, query="MissionTask", lang="en")]
    check("⑦ 영문 0건은 후보에서 제외",
          A.thesaurus_alias_candidates(en)["candidates"] == [])


def main() -> int:
    for fn in (test_each_condition_blocks_alone, test_config_overrides_use_origin_key_names,
               test_marker_gap_blocks, test_broken_marker_is_treated_as_absent,
               test_marker_only_on_success, test_exception_is_not_swallowed,
               test_force_skips_time_gate_only, test_plan_has_no_side_effects,
               test_thin_sample_withholds_verdict, test_rrf_simulation_runs_with_channel_fields,
               test_channel_fields_absent_means_empty_rrf,
               test_thesaurus_candidates_need_repetition):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_batch: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
