"""영구 유실 카나리 누적 (소 3.5.6) — 🔴 **반복은 누적된 것을 봐야 보인다.**

원전 지침: *"카나리가 **반복**되면 근본 원인(LLM 쿼터·타임아웃 등)을 먼저 해결할 것 —
재touch/rebuild 는 증상 복구일 뿐."* 저널에 한 줄 찍는 것만으로는 그 지침을 따를 수 없다.

⚠️ **판별 기준은 원전 그대로**: *"skip 후 워터마크가 전진하느냐."* 전진하지 않는 실패는 다음
회차에 self-heal 되므로 카나리로 만들지 않는다 — 원전은 except ~33개 중 **딱 2개만** 승격했다
(*"self-heal 되는 걸 카나리로 만들면 노이즈"*).

🔴 **우리는 원전의 두 번째 kind(`vector-index-gap`)를 이식하지 않았다** — 재색인 실패 시
`return r` 로 워터마크를 전진시키지 않고, 우리는 커밋 워터마크만이 아니라 **컨텍스트 digest** 로도
판정하므로 다음 회차에 재시도된다. 즉 우리에겐 그 자리가 **영구 유실이 아니다.**

`.venv/bin/python master/test_canary.py`
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.events.consumer import append_canary      # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


class FakePaths:
    def __init__(self, root: Path):
        self.canary = root / "canary" / "permanent_loss.jsonl"


def test_appends_and_accumulates():
    with tempfile.TemporaryDirectory() as td:
        p = FakePaths(Path(td))
        check("첫 기록 성공", append_canary(p, kind="context-md-lost", detail="A", commit="aaa"))
        check("디렉토리를 만든다", p.canary.parent.is_dir())
        check("두 번째도 성공", append_canary(p, kind="context-md-lost", detail="B", commit="bbb"))
        lines = [l for l in p.canary.read_text(encoding="utf-8").splitlines() if l.strip()]
        check("🔴 누적된다 (덮어쓰지 않는다)", len(lines) == 2, str(len(lines)))
        recs = [json.loads(l) for l in lines]
        check("kind 가 실린다", all(r["kind"] == "context-md-lost" for r in recs))
        check("detail 이 실린다", [r["detail"] for r in recs] == ["A", "B"])
        check("commit 이 실린다", [r["commit"] for r in recs] == ["aaa", "bbb"])
        check("시각이 실린다", all(r.get("at") for r in recs))


def test_korean_survives():
    with tempfile.TemporaryDirectory() as td:
        p = FakePaths(Path(td))
        append_canary(p, kind="context-md-lost", detail="한글 사유 — em-dash 포함")
        raw = p.canary.read_text(encoding="utf-8")
        check("한글이 이스케이프 없이 남는다", "한글 사유" in raw, raw[:80])


def test_detail_is_bounded():
    with tempfile.TemporaryDirectory() as td:
        p = FakePaths(Path(td))
        append_canary(p, kind="k", detail="x" * 5000)
        rec = json.loads(p.canary.read_text(encoding="utf-8").splitlines()[0])
        check("detail 길이가 제한된다", len(rec["detail"]) == 500, str(len(rec["detail"])))


def test_write_failure_does_not_raise():
    """🔴 카나리를 쓰다 색인을 죽이면 본말전도다 — 예외 대신 False."""
    class Bad:
        canary = Path("/proc/nonexistent-ax/permanent_loss.jsonl")
    try:
        ok = append_canary(Bad(), kind="k", detail="d")
        check("기록 실패는 예외가 아니라 False", ok is False, str(ok))
    except Exception as e:                              # noqa: BLE001
        check("기록 실패는 예외가 아니라 False", False, f"{type(e).__name__}: {e}")


# ── 소 3.5.6 두 번째 승격 자리 (`#182`) — 도메인 색인 갭 ─────────

def test_domain_index_failure_is_promoted():
    """🔴 **삼킨 실패가 조용하지 않은가.**

    `rebuild_all` 은 도메인 색인 실패를 `note` 로 바꾸고 정상 반환한다(fail-soft — 도메인
    색인이 죽어도 컨텍스트 검색은 멀쩡하므로 그건 옳다). 문제는 그 성공 반환 때문에 호출자가
    **워터마크를 전진**시키고, 재색인은 컨텍스트 MD 가 바뀔 때만 돌아 **다음 회차가 안 온다**는
    것이다. 원전 승격 기준에 정확히 걸린다.
    """
    import json as _json
    import tempfile
    from master.context_search import rebuild as R

    class FakeVec:
        work_name, live_name = "b", "a"
        def __init__(self, paths): pass
        def rebuild(self, swap=False):
            class S: documents = 3
            return S()

    class FakeBm:
        def __init__(self, paths, gen=""): pass
        def rebuild_into(self, work): return 5
        def close(self): pass

    class FakeGen:
        @staticmethod
        def write(root, work): pass

    class Boom(Exception):
        pass

    class FakeDomain:
        DomainIndexError = Boom
        @staticmethod
        def sync(paths, progress=None):
            raise Boom("컬렉션을 못 열었다")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)

        class P:
            name = "T"
            canary = root / "_silent_failure" / "permanent_loss.jsonl"
            def __init__(self): self.root = root
            def missing_sources(self): return []

        paths = P()
        old = (R.ContextIndex, R.Bm25Index, R.generation, R.domain_index)
        R.ContextIndex, R.Bm25Index, R.generation, R.domain_index = (
            FakeVec, FakeBm, FakeGen, FakeDomain)
        try:
            st = R.rebuild_all(paths)
        finally:
            R.ContextIndex, R.Bm25Index, R.generation, R.domain_index = old

        # 🔴 fail-soft 는 그대로 — 바꾸는 것은 "조용히" 뿐이다
        check("도메인 색인이 죽어도 재구축은 성공으로 끝난다 (fail-soft 유지)",
              st.vector_docs == 3 and st.bm25_docs == 5, str(st))
        check("사유를 note 로 들고 나온다", "도메인 색인" in (st.domain_note or ""), st.domain_note)
        check("🔴 그리고 **조용하지 않다** — 카나리가 찍힌다", paths.canary.exists(),
              "카나리 파일이 없다 — 삼킨 실패가 아무 흔적도 안 남겼다")
        if paths.canary.exists():
            rec = _json.loads(paths.canary.read_text(encoding="utf-8").splitlines()[-1])
            check("kind 가 domain-index-gap", rec["kind"] == "domain-index-gap", str(rec))
            check("사유가 실린다", "컬렉션을 못 열었다" in rec["detail"], str(rec))


def test_kinds_are_named_constants():
    """⚠️ 문자열을 호출부마다 손으로 적으면 오타가 조용히 새 kind 를 만든다."""
    from master import canary as C
    check("두 kind 가 상수로 있다",
          C.KIND_CONTEXT_MD_LOST == "context-md-lost"
          and C.KIND_DOMAIN_INDEX_GAP == "domain-index-gap")
    from master.events import consumer as CO
    check("🔴 옛 이름으로도 그대로 부를 수 있다 (재수출)",
          CO.append_canary is C.append_canary)


def main() -> int:
    for fn in (test_appends_and_accumulates, test_korean_survives,
               test_detail_is_bounded, test_write_failure_does_not_raise,
               test_domain_index_failure_is_promoted, test_kinds_are_named_constants):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_canary: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
