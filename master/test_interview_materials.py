"""착수 전 인터뷰 재료 수집(`#960` T4) 계약 테스트 — 출처 하나가 실패해도 나머지를 주고, 실패는 말한다.

실행: .venv/bin/python master/test_interview_materials.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import interview_materials as IM    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


ISSUE = {"id": 960, "subject": "[AX] 버그 — 착수 전 인터뷰 절차", "fixed_version": "마일스톤 8 - 버그/개선",
         "status": "진행", "description": "본문", "journals": [{"created_on": "t0", "user": "u", "notes": "노트"}]}


def _boom(*_a):
    raise RuntimeError("검색 서비스 없음")


def test_collect_all_sources():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        (root / "a.md").write_text("관련 #960 기록\n무관 #9600\n", encoding="utf-8")
        (root / "b.md").write_text("다른 #961\n", encoding="utf-8")
        qs = []
        out = IM.collect(ISSUE, project="ax-cluster",
                         rag=lambda q: qs.append(q) or {"ok": True, "hits": [{"path": "x"}], "request_id": "r1"},
                         ontology=lambda q: {"ok": False, "domains": [], "summary": "모름"},
                         recent=lambda p: {"issues": [{"id": 1, "subject": "s", "fixed_version": "v",
                                                       "updated_on": "t", "extra": 1}]},
                         reports_root=root)
    check("질의는 머리표를 걷은 제목", qs == ["착수 전 인터뷰 절차"], str(qs))
    check("일감 원문(본문·노트·마일스톤)", out["issue"]["fixed_version"] == "마일스톤 8 - 버그/개선"
          and out["issue"]["journals"][0]["notes"] == "노트")
    check("RAG", out["rag"]["hits"] == [{"path": "x"}] and out["rag"]["request_id"] == "r1")
    check("온톨로지 모름(ok:false)은 실패가 아니다", out["ontology"]["summary"] == "모름" and "ontology" not in out["errors"])
    check("보고서는 #960 만(#9600·#961 제외)", [r["path"] for r in out["reports"]] == [str(root / "a.md")]
          and out["reports"][0]["lines"] == ["관련 #960 기록"], str(out["reports"]))
    check("최근 완료 일감", out["recent_closed"] == [{"id": 1, "subject": "s", "fixed_version": "v", "updated_on": "t"}])
    check("실패 없음", out["errors"] == {})
    check("수집 로그 줄", any("재료 수집 #960" in x for x in out["log"]))


def test_one_source_fails_others_stay():
    out = IM.collect(ISSUE, rag=_boom, ontology=lambda q: {"ok": False, "error": "트윈 없음"},
                     recent=lambda p: {"error": "레드마인 503"}, reports_root=Path("/nonexistent-dir-960"))
    check("RAG 실패 → errors 에 사유", out["rag"] is None and "검색 서비스 없음" in out["errors"]["rag"])
    check("온톨로지 error → errors", out["ontology"] is None and out["errors"]["ontology"] == "트윈 없음")
    check("최근 일감 error → errors", out["recent_closed"] is None and "503" in out["errors"]["recent_closed"])
    check("일감 원문은 남는다", out["issue"]["subject"] == ISSUE["subject"])
    check("보고서 폴더 없음 → 빈 목록", out["reports"] == [])
    check("실패가 로그에 찍힌다", sum("실패" in x for x in out["log"]) >= 3, str(out["log"]))


def main() -> int:
    for fn in (test_collect_all_sources, test_one_source_fails_others_stay):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_interview_materials: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
