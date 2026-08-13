"""BM25 0건 진단 (소 3.5.8) — 🔴 *"검색이 비었다"* 는 증상이고 원인은 여럿이다.

원전 카나리 `[BM25 0건 진단]` 이식. ⚠️ **원전처럼 로그를 찍지 않는다** — 이 저장소의 모듈은
사실을 반환하고 호출자가 찍는다(테스트 가능·전역 상태 없음). 원전 카나리는 `watch.exe` 의 상주
콘솔에 묶인 방식이었다. **기제를 옮기고 형태는 우리 것으로 둔다.**

🔴 이것이 필요한 근거는 실제 사건이다 — 리포트 13 §19.1 에서 *"도메인이 비어있어"* 라는 보고를
받고 처음부터 재야 했다. 그때 이 함수가 있었으면 한 번에 답했다.

`.venv/bin/python master/test_bm25_diagnose.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search import bm25 as B                      # noqa: E402
from master.context_search.paths import ProjectPaths             # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _idx(td: str):
    return B.Bm25Index(ProjectPaths(name="probe", root=Path(td)))


def _doc(fid: str, body: str, tags=(), classes=()):
    """`Document(file_id, body, meta, fm)` — 실제 필드에 맞춘다."""
    fm = {"tags": list(tags), "related_classes": list(classes), "category": ""}
    return B.Document(file_id=fid, body=body, meta=dict(fm), fm=dict(fm))


def test_empty_index():
    with tempfile.TemporaryDirectory() as td:
        idx = _idx(td)
        st = idx.stats()
        check("stats 가 값을 준다 (메서드가 아니라 수)", st["documents"] == 0, str(st))
        check("stats 에 세대가 있다", bool(st["generation"]), str(st))
        d = idx.diagnose("아무거나")
        check("🔴 빈 색인을 그렇게 말한다", d["reason"] == "색인이 비어 있다", d["reason"])
        check("결과 0", d["results"] == 0)


def test_unmatched_terms_are_the_cause():
    with tempfile.TemporaryDirectory() as td:
        idx = _idx(td)
        idx.upsert([_doc("a.md", "미션 태스크 실행기", classes=["UMissionTaskExecutor"])])
        d = idx.diagnose("존재하지않는단어xyzq")
        check("🔴 아무 토큰도 안 맞으면 그렇게 말한다",
              d["reason"] == "토큰이 하나도 색인 어휘와 맞지 않는다", d["reason"])
        check("unmatched 에 그 토큰이 다 들어간다",
              set(d["unmatched"]) == set(d["terms"]), str(d))
        check("term_hits 가 토큰별 건수를 준다", all(v == 0 for v in d["term_hits"].values()),
              str(d["term_hits"]))


def test_hit_case_reports_results():
    with tempfile.TemporaryDirectory() as td:
        idx = _idx(td)
        idx.upsert([_doc("a.md", "미션 태스크 실행기", classes=["UMissionTaskExecutor"])])
        d = idx.diagnose("미션")
        check("맞으면 결과가 있다고 말한다", d["reason"] == "결과가 있다", d["reason"])
        check("결과 수가 실린다", d["results"] >= 1, str(d["results"]))
        check("unmatched 가 비어 있다", d["unmatched"] == [], str(d["unmatched"]))


def test_hangul_flag_and_no_terms():
    with tempfile.TemporaryDirectory() as td:
        idx = _idx(td)
        idx.upsert([_doc("a.md", "hello world")])
        check("한글 여부를 알려준다 (토크나이저 약점 자리)", B.has_hangul("미션") is True)
        check("영문은 False", idx.diagnose("hello")["has_hangul"] is False)
        d = idx.diagnose("!!!")
        check("토큰이 안 나오면 그렇게 말한다",
              d["reason"] in ("질의에서 토큰이 나오지 않았다", "색인이 비어 있다"), d["reason"])


def test_diagnose_never_raises():
    """🔴 진단이 죽으면 안 된다 — 세어 보지 못한 토큰은 -1 로 표시한다."""
    with tempfile.TemporaryDirectory() as td:
        idx = _idx(td)
        idx.upsert([_doc("a.md", "x")])
        try:
            d = idx.diagnose('"unbalanced AND ( quote')
            check("깨진 질의에도 예외가 없다", isinstance(d, dict), str(type(d)))
            check("세지 못한 토큰은 -1", all(isinstance(v, int) for v in d["term_hits"].values()))
        except Exception as e:                          # noqa: BLE001
            check("깨진 질의에도 예외가 없다", False, f"{type(e).__name__}: {e}")


def main() -> int:
    for fn in (test_empty_index, test_unmatched_terms_are_the_cause,
               test_hit_case_reports_results, test_hangul_flag_and_no_terms,
               test_diagnose_never_raises):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_bm25_diagnose: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
