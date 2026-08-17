"""`census.py` 계약 테스트 (#177/#178).

핵심 계약: ① 경계 보정 — `http_server.py` 는 `server.py` 의 인용이 아니다 (`/` 뒤는 인정,
`_` 뒤는 거부) ② 제외 디렉토리가 리포트 14 §1 과 같다 ③ 필독 4종은 항상 따로 보인다.

실행: python3 master/test_census.py  (순수 stdlib)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from master import census as C                                  # noqa: E402


# ── ① 경계 보정 ────────────────────────────────────────────────

def test_boundary_underscore_rejected():
    assert C.count_citation("우리는 http_server.py 를 쓴다", "server.py") == 0


def test_boundary_slash_and_start_accepted():
    corpus = "mcp/context_search/server.py 참조\nserver.py 도 참조"
    assert C.count_citation(corpus, "server.py") == 2


def test_boundary_backtick_and_paren():
    assert C.count_citation("(`logic.py`) 그리고 [logic.py]", "logic.py") == 2


def test_regex_metachar_in_name_is_escaped():
    # basename 의 `.` 이 정규식 임의 문자가 되면 `logicXpy` 도 잡힌다 — escape 계약
    assert C.count_citation("logicXpy", "logic.py") == 0


# ── ② 수집 규칙 ────────────────────────────────────────────────

def test_origin_excludes_report14_dirs_and_exts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a").mkdir()
        (root / "a" / "keep.py").write_text("x", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "skip.py").write_text("x", encoding="utf-8")
        (root / "plan_archive").mkdir()
        (root / "plan_archive" / "skip.md").write_text("x", encoding="utf-8")
        (root / "a" / "skip.ts").write_text("x", encoding="utf-8")   # 확장자 제외
        names = [p.name for p in C.origin_files(root)]
        assert names == ["keep.py"], names


def test_corpus_excludes_twin_and_git():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "a.md").write_text("코퍼스에 든다", encoding="utf-8")
        (root / "ModularStage").mkdir()
        (root / "ModularStage" / "b.md").write_text("트윈은 제외", encoding="utf-8")
        got = C.corpus_text(root, extra=())
        assert "코퍼스에 든다" in got and "트윈은 제외" not in got


# ── ③ census 결과 모양 ─────────────────────────────────────────

def test_run_census_partitions_and_must_reads():
    with tempfile.TemporaryDirectory() as o, tempfile.TemporaryDirectory() as r:
        origin, repo = Path(o), Path(r)
        (origin / "cited.py").write_text("1\n2\n3", encoding="utf-8")
        (origin / "orphan.py").write_text("1\n2", encoding="utf-8")
        (repo / "doc.md").write_text("우리는 cited.py 를 이식했다", encoding="utf-8")
        got = C.run_census(origin=origin, repo=repo, extra=())
        assert [x["file"] for x in got["cited"]] == ["cited.py"]
        assert [x["file"] for x in got["uncited"]] == ["orphan.py"]
        assert got["uncited"][0]["lines"] == 2
        assert set(got["must_reads"]) == set(C.MUST_READS)   # 항상 4종 전부 보고


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 통과")
    sys.exit(1 if failed else 0)
