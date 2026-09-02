"""검색 로그 기록기 (소 3.4.5 · `#193`) — 원전 `cs_common._log_search` 이식분.

검증하는 것:

    ① 언어 휴리스틱 — 원전 5배 규칙까지 같다 (바꾸면 과거 리포트와 비교 불가)
    ② [중요] `result_details` 가 **채널 필드를 잃지 않는다** (`to_dict()` 로 적으면 전부 빈다)
    ③ [중요] `zero_hit` 은 **2건 미만일 때만** 나온다 (원전 η.12.5 의 입력 신호)
    ④ [중요] 기록 실패가 **조용하지 않다** — 값으로 돌아온다 (원전은 `except: pass`)
    ⑤ 회전 — 최대 건수를 넘으면 **최신**을 남긴다
    ⑥ 깨진 줄이 있어도 나머지를 읽는다
    ⑦ 위치가 프로젝트 **밖**이다 (§5.5)
    ⑧ [중요] 표면 census — MCP·웹UI **양쪽**이 기록하고, 기계 생성 질의는 기록하지 않는다

`.venv/bin/python master/test_search_log.py`
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search import search_log as SL              # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


@dataclass
class Hit:
    """`context_search.search.Hit` 중 기록기가 읽는 필드만."""

    file_id: str = "a.md"
    source: str = "vector+bm25"
    rrf_score: float = 0.03
    similarity: float = 0.87
    bm25_score: float = 4.2
    vector_rank: int | None = 1
    bm25_rank: int | None = 2

    def to_dict(self) -> dict:                      # 일부러 채널 필드를 버린다 (실물과 같게)
        return {"file_id": self.file_id, "source": self.source}


@dataclass
class Paths:
    root: Path


def _paths(tmp) -> Paths:
    return Paths(root=Path(tmp) / "proj")


# ── ① 언어 휴리스틱 ───────────────────────────────────────────────────────────

def test_detect_lang():
    cases = {
        "": "other", "123 !!": "other",
        "미션 시스템": "ko", "MissionTask": "en",
        "미션 MissionTask 연출": "mixed",
        # 5배 규칙 — 한글 10자 vs 영문 1자
        "미션시스템완료연출확인A": "ko",
    }
    for q, want in cases.items():
        got = SL.detect_lang(q)
        check(f"① lang({q!r}) == {want}", got == want, f"실측 {got}")


# ── ② 채널 필드 보존 ──────────────────────────────────────────────────────────

def test_result_details_keeps_channel_fields():
    d = SL.build_result_details([Hit()])[0]
    check("② vec_rank 가 남는다", d.get("vec_rank") == 1, str(d))
    check("② bm25_rank 가 남는다", d.get("bm25_rank") == 2, str(d))
    check("② bm25_score 가 남는다", d.get("bm25_score") == 4.2, str(d))
    check("② similarity 가 남는다", d.get("similarity") == 0.87, str(d))
    check("② rrf_score 가 남는다", d.get("rrf_score") == 0.03, str(d))

    # [중요] 0 은 의미 있는 값(1위)이다 — truthy 검사로 바꾸면 사라진다
    d0 = SL.build_result_details([Hit(vector_rank=0, bm25_rank=0)])[0]
    check("② [중요] rank 0 이 사라지지 않는다",
          d0.get("vec_rank") == 0 and d0.get("bm25_rank") == 0, str(d0))

    # 채널 하나만 잡힌 경우
    d1 = SL.build_result_details([Hit(source="bm25", vector_rank=None, similarity=0.0)])[0]
    check("② 벡터에 없으면 vec_rank 를 안 적는다", "vec_rank" not in d1, str(d1))
    check("② similarity 0 은 적지 않는다 (원전과 같다)", "similarity" not in d1, str(d1))


# ── ③④⑦ 기록 ────────────────────────────────────────────────────────────────

def test_log_writes_schema():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        r = SL.log_search(p, query="미션 시스템", hits=[Hit(), Hit(file_id="b.md")],
                          caller="mcp_direct")
        check("③ 기록됐다", r.get("ok"), str(r))

        lp = SL.log_path_for(p)
        check("⑦ 위치가 프로젝트 데이터 밑이다", lp.name == "search_log.jsonl", str(lp))
        rec = json.loads(lp.read_text(encoding="utf-8").strip())
        check("③ results 가 파일 목록이다", rec["results"] == ["a.md", "b.md"], str(rec))
        check("③ lang 이 붙는다", rec["lang"] == "ko", str(rec))
        check("③ caller 가 붙는다", rec["caller"] == "mcp_direct", str(rec))
        check("③ [중요] 2건이면 zero_hit 이 없다", "zero_hit" not in rec, str(rec))
        check("③ result_details 가 실렸다", len(rec["result_details"]) == 2, str(rec))


def test_zero_hit_only_below_two():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        SL.log_search(p, query="없는것")
        SL.log_search(p, query="하나만", hits=[Hit()])
        recs = SL.read_entries(p)
        check("③ 0건은 zero_hit=True", recs[0].get("zero_hit") is True, str(recs[0]))
        check("③ 1건은 zero_hit=False", recs[1].get("zero_hit") is False, str(recs[1]))


def test_nothing_to_log_is_a_fact():
    with tempfile.TemporaryDirectory() as tmp:
        r = SL.log_search(_paths(tmp))
        check("③ 질의도 결과도 없으면 사실로 보고", not r["ok"] and "기록할 것이 없다" in r["reason"],
              str(r))


def test_write_failure_is_not_silent():
    """[중요] 원전은 `except Exception: pass` 다 — 우리는 값으로 돌린다."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        # 로그 경로 자리에 **디렉토리**를 놓아 쓰기를 실패시킨다
        lp = SL.log_path_for(p)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.mkdir()
        r = SL.log_search(p, query="x", hits=[Hit()])
        check("④ [중요] 실패가 조용하지 않다", not r["ok"] and bool(r.get("reason")), str(r))
        check("④ 예외를 올리지 않았다 (fail-open)", r.get("written") is False, str(r))


# ── ⑤⑥ 회전·복원력 ───────────────────────────────────────────────────────────

def test_rotation_keeps_newest():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        lp = SL.log_path_for(p)
        lp.parent.mkdir(parents=True, exist_ok=True)
        n = SL.SEARCH_LOG_MAX_ENTRIES + 5
        lp.write_text("\n".join(json.dumps({"i": i}) for i in range(n)) + "\n",
                      encoding="utf-8")
        r = SL.rotate(lp)
        check("⑤ 회전이 일어났다", r["ok"] and r["removed"] == 5, str(r))
        recs = SL.read_entries(p)
        check("⑤ 건수가 상한이다", len(recs) == SL.SEARCH_LOG_MAX_ENTRIES, str(len(recs)))
        check("⑤ [중요] 최신을 남겼다", recs[-1]["i"] == n - 1 and recs[0]["i"] == 5,
              f"{recs[0]}…{recs[-1]}")


def test_broken_line_does_not_kill_the_read():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        lp = SL.log_path_for(p)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text('{"i":1}\n깨진 줄 {{{\n\n{"i":2}\n', encoding="utf-8")
        recs = SL.read_entries(p)
        check("⑥ 깨진 줄을 건너뛰고 나머지를 읽는다",
              [r["i"] for r in recs] == [1, 2], str(recs))


def test_both_surfaces_are_instrumented():
    """[중요] 표면 census 를 고정한다 — 원전은 MCP·HTTP **양쪽**에서 기록한다.

    처음엔 MCP 한 곳만 심었고 재기동 검증 중에 `api_search` 를 발견했다. 배선이 조용히
    빠지면 로그가 표면에 따라 **편향**되고, 그건 값이 없는 것보다 나쁘다(틀린 근거가 된다).
    [주의] 소스 검사다 — 실행 경로가 아니라 **배선의 존재**를 잰다.
    """
    root = Path(__file__).resolve().parent
    want = {
        "projects/mcp_server.py": "mcp_direct",
        "webui/routes.py": "web_ui",
    }
    for rel, caller in want.items():
        src = (root / rel).read_text(encoding="utf-8")
        check(f"⑧ {rel} 이 기록한다", "search_log.log_search(" in src, "호출이 없다")
        check(f"⑧ {rel} 의 caller={caller}", f'caller="{caller}"' in src, "caller 가 다르다")

    # [중요] 기계 생성 질의는 기록하지 않는다 — 섞이면 분포가 오염된다
    for rel in ("context_synth/synth.py", "webui/board.py", "work/subbranch.py"):
        src = (root / rel).read_text(encoding="utf-8")
        check(f"⑧ {rel} 은 기록하지 않는다", "search_log.log_search(" not in src,
              "기계 생성 질의가 로그에 섞인다")


def main() -> int:
    for fn in (test_detect_lang, test_result_details_keeps_channel_fields,
               test_log_writes_schema, test_zero_hit_only_below_two,
               test_nothing_to_log_is_a_fact, test_write_failure_is_not_silent,
               test_rotation_keeps_newest, test_broken_line_does_not_kill_the_read,
               test_both_surfaces_are_instrumented):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_search_log: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
