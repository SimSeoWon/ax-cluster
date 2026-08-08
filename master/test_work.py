"""워크플로우 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_work.py

🔴 지키는 불변식 (PLAN §4.2, plan v5 C.1/C.2):
   1. **두 작업장이 같은 ref 에 push 하지 않는다** — zombie race 가 구조적으로 성립 불가
   2. **식별자를 조용히 정규화하지 않는다** — 이름이 곧 정체성이다
   3. **매니페스트는 1회 수집** — 작업장은 읽기만 한다
   4. **수집 결손을 숨기지 않는다** — grounding 없이 일하는 줄 알아야 한다
   5. **매니페스트 쓰기는 원자적** — 반쯤 쓰인 것을 읽으면 안 된다
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths  # noqa: E402
from master.work import branch_names as bn  # noqa: E402
from master.work import manifest as mf  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


class FakeSearch:
    def __init__(self, hits=(), exc=None):
        self._hits = list(hits)
        self._exc = exc
        self.calls = []

    def search(self, query, limit=8):
        self.calls.append((query, limit))
        if self._exc:
            raise self._exc
        return self._hits[:limit]


class FakeHit:
    def __init__(self, file_id, rrf=0.03, source="vector+bm25", excerpt="본문"):
        self.file_id, self.rrf_score, self.source, self.excerpt = file_id, rrf, source, excerpt


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-work-test-"))
    paths = ProjectPaths(name="TestProj", root=tmp / "TestProj")

    # ── 브랜치 규약 ─────────────────────────────────
    print("\n[1] 2-tier 규약")
    check("durable", bn.durable_branch("task_5") == "task/task_5")
    check("attempt", bn.attempt_branch("task_5", "HV0I6DL", "20260808_120000")
          == "attempt/task_5/HV0I6DL/20260808_120000")
    check("durable 판별", bn.is_durable("task/task_5") and not bn.is_durable("attempt/x/y/z"))
    check("attempt 판별", bn.is_attempt("attempt/x/y/z") and not bn.is_attempt("task/task_5"))
    check("glob", bn.attempt_glob("task_5") == "attempt/task_5/*")

    print("\n[2] 🔴 zombie race 가 구조적으로 성립하지 않는다")
    a = bn.attempt_branch("task_5", "HV0I6DL", "t1")     # 작업장 A
    b = bn.attempt_branch("task_5", "JFVS693", "t2")     # 재배정된 B
    check("서로 다른 ref", a != b, f"{a} vs {b}")
    check("둘 다 durable 이 아니다", not bn.is_durable(a) and not bn.is_durable(b))
    check("같은 작업장 재시도도 갈린다",
          bn.attempt_branch("task_5", "A", "t1") != bn.attempt_branch("task_5", "A", "t2"))
    check("같은 glob 으로 일괄 정리된다",
          bn.parse_attempt(a)["task_id"] == bn.parse_attempt(b)["task_id"] == "task_5")

    print("\n[3] 파싱 왕복")
    got = bn.parse_attempt(a)
    check("필드", got == {"task_id": "task_5", "workshop": "HV0I6DL", "ts": "t1"}, str(got))
    check("durable 파싱", bn.parse_durable("task/task_5") == "task_5")
    for bad in ("task/task_5", "attempt/a/b", "attempt/a/b/c/d", "", "쓰레기", None):
        check(f"  attempt 아님: {bad!r}", bn.parse_attempt(bad) is None)
    for bad in ("attempt/a/b/c", "task/a/b", "", None):
        check(f"  durable 아님: {bad!r}", bn.parse_durable(bad) is None)

    print("\n[4] 🔴 잘못된 식별자를 조용히 고치지 않는다")
    for bad, why in [("", "빈 값"), ("   ", "공백뿐"), ("a/b", "슬래시"),
                     ("a b", "공백"), ("a:b", "콜론"), ("한글", "비ASCII")]:
        try:
            bn.durable_branch(bad)
            check(f"  거부: {why}", False, "통과해 버렸다")
        except bn.BranchNameError:
            check(f"  거부: {why}", True)
    check("attempt 도 작업장명을 검사한다",
          _raises(lambda: bn.attempt_branch("t", "a/b", "ts"), bn.BranchNameError))
    check("attempt 도 ts 를 검사한다",
          _raises(lambda: bn.attempt_branch("t", "w", ""), bn.BranchNameError))
    check("앞뒤 공백은 다듬는다 (내용은 안 바꾼다)",
          bn.durable_branch("  task_5  ") == "task/task_5")

    # ── 매니페스트 ──────────────────────────────────
    print("\n[5] 매니페스트 조립")
    s = FakeSearch([FakeHit("A.md"), FakeHit("B.md", 0.02, "vector", "")])
    m = mf.build(paths, "task_1", classes=["UManagerBase"], stem="초기화",
                 contracts="Init() 동결", searcher=s, now=NOW)
    check("온전히 수집", m.ok and m.hits == 2, f"ok={m.ok} hits={m.hits}")
    check("클래스명이 질의 앞에 온다", s.calls[0][0].startswith("UManagerBase"), s.calls[0][0])
    check("stem 도 질의에 들어간다", "초기화" in s.calls[0][0])
    for want in ("task_1", "TestProj", "UManagerBase", "Init() 동결", "A.md", "B.md"):
        check(f"  본문에 {want}", want in m.body)
    check("발췌 없는 히트도 실린다", "B.md" in m.body)
    check("재검색 불필요를 명시", "재검색 불필요" in m.body)

    print("\n[6] 🔴 온톨로지가 없다는 사실을 숨기지 않는다")
    check("규범 섹션이 있다", "도메인 규범" in m.body)
    check("미구현이라 적혀 있다", "미구현" in m.body and "2단계" in m.body)

    print("\n[7] 🔴 수집 결손을 숨기지 않는다 (베스트에포트지만 조용하지 않다)")
    m2 = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch(exc=RuntimeError("죽음")),
                  now=NOW)
    check("검색 실패해도 매니페스트는 나온다", bool(m2.body))
    check("  ok=False", not m2.ok)
    check("  본문에 경고", "수집이 온전하지 않다" in m2.body and "RuntimeError" in m2.body)

    m3 = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch([]), now=NOW)
    check("결과 0건도 결손으로 표시", not m3.ok and "결과가 없다" in m3.body)

    m4 = mf.build(paths, "t", searcher=FakeSearch([FakeHit("X.md")]), now=NOW)
    check("질의를 못 만들면 검색하지 않는다", not m4.ok and "질의를 만들 수 없" in m4.body)

    m5 = mf.build(paths, "t", classes=["UFoo"], searcher=None, now=NOW)
    check("검색기 없음도 기록", not m5.ok and "검색기가 없다" in m5.body)

    print("\n[8] 히트 수 제한과 발췌 길이")
    many = FakeSearch([FakeHit(f"{i}.md", excerpt="가" * 500) for i in range(20)])
    m6 = mf.build(paths, "t", classes=["UFoo"], hits=3, searcher=many, now=NOW)
    check("limit 이 전달된다", many.calls[0][1] == 3, str(many.calls[0]))
    check("히트 수", m6.hits == 3)
    check("발췌가 잘린다", "…" in m6.body and "가" * 200 not in m6.body)

    print("\n[9] 저장 — 원자적, 파생물 위치")
    p = mf.write(paths, m)
    check("경로", p == paths.root / "manifests" / "task_1.md", str(p))
    check("트윈 파생물 아래", p.parent == paths.manifests)
    check("읽힌다", mf.read(paths, "task_1") == m.body)
    check("임시 파일이 안 남는다", not list(p.parent.glob("*.tmp")))
    check("없는 것은 None (빈 문자열과 구분)", mf.read(paths, "없는거") is None)
    p2 = mf.write(paths, mf.build(paths, "task_1", classes=["UBar"],
                                  searcher=FakeSearch([FakeHit("C.md")]), now=NOW))
    check("덮어쓰기", p2 == p and "C.md" in mf.read(paths, "task_1"))

    print("\n[10] 경로 안전")
    check("슬래시가 디렉토리를 벗어나지 못한다",
          mf.manifest_path(paths, "a/b").parent == paths.manifests,
          str(mf.manifest_path(paths, "a/b")))
    check("빈 task_id 거부", _raises(lambda: mf.manifest_path(paths, "  "), mf.ManifestError))

    print("\n[11] collect() — 검색기를 못 열어도 등록을 막지 않는다")
    broken = mf._BrokenSearcher(OSError("DB 없음"))
    m7 = mf.build(paths, "t9", classes=["UFoo"], searcher=broken, now=NOW)
    check("예외가 새어 나오지 않는다", not m7.ok)
    check("원인이 기록된다", "OSError" in m7.body and "DB 없음" in m7.body)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


def _raises(fn, exc) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


if __name__ == "__main__":
    sys.exit(main())
