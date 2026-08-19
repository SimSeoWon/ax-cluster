"""`thesaurus.register` 범용어 가드 테스트 (사용자 지시 2026-08-17).

핵심 계약: **범용 표현은 별칭이 되지 못한다** — 별칭은 질의에 클래스명을 덧붙여
확장하므로, '완료' 같은 말이 등록되면 그 단어가 든 모든 질의가 한 클래스로 쏠린다.

문턱값의 근거는 실측이다(리포트 20 예정): 961문서 코퍼스에서 기존 별칭 11건의 정확 구
DF 최고가 1.9%('미션 태스크'), 범용어 최저가 3.3%('연출') — 2.5% 가 그 사이를 가른다.
여기서는 그 측정을 `df_fn` 으로 주입해 계약만 잰다 (실 BM25 를 두드리지 않는다).

실행: .venv/bin/python master/test_thesaurus_guard.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from master.context_search.paths import ProjectPaths            # noqa: E402
from master.context_search import thesaurus as th               # noqa: E402


def _paths(tmp: str) -> ProjectPaths:
    return ProjectPaths(name="T", root=Path(tmp))


def _yaml_target(paths: ProjectPaths, cls: str) -> Path:
    d = paths.ontology / "domains" / "D" / "L1" / "objects"
    d.mkdir(parents=True)
    f = d / f"{cls}.yaml"
    f.write_text(f"name: {cls}\n", encoding="utf-8")
    return f


# ── 거부 경로 — 파일이 하나도 없어도 가드가 먼저 선다 ──────────────

def test_short_term_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        st = th.register(_paths(tmp), "UFoo", "완료", df_fn=lambda t: (0, 961))
        assert st.startswith("rejected_short"), st
        assert "쏠린다" in st          # 사유가 문장으로 담긴다 — 조용한 실패 금지


def test_short_counts_without_spaces():
    # '미 션' 처럼 공백으로 부풀린 짧은 표현도 걸린다
    with tempfile.TemporaryDirectory() as tmp:
        st = th.register(_paths(tmp), "UFoo", "미 션", df_fn=lambda t: (0, 961))
        assert st.startswith("rejected_short"), st


def test_generic_term_rejected_by_df():
    with tempfile.TemporaryDirectory() as tmp:
        # '인터페이스' — 4자 이상이라 ①은 통과하지만 실측 DF 10% 급이라 ②에 걸린다
        st = th.register(_paths(tmp), "UFoo", "인터페이스", df_fn=lambda t: (96, 961))
        assert st.startswith("rejected_generic"), st
        assert "96/961" in st          # 측정값이 사유에 그대로 남는다


def test_threshold_boundary_is_strict_greater():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        # 정확히 2.5% (24/960) 는 통과 — 초과만 거부
        st = th.register(p, "UFoo", "판별 표현", df_fn=lambda t: (24, 960))
        assert not st.startswith("rejected"), st


# ── 통과 경로 ────────────────────────────────────────────────

def test_discriminative_term_added_to_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        f = _yaml_target(p, "UFoo")
        st = th.register(p, "UFoo", "미션 흐름", df_fn=lambda t: (5, 961))
        assert st == "added", st
        assert "미션 흐름" in f.read_text(encoding="utf-8")


def test_unmeasured_says_so_instead_of_pretending():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        _yaml_target(p, "UFoo")
        st = th.register(p, "UFoo", "미션 흐름", df_fn=lambda t: (None, 0))
        assert st == "added_unmeasured", st


def test_side_fallback_keeps_guard_and_label():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        # 온톨로지 yaml 도 클래스 그래프도 없다 → 폴백 경로. 가드 라벨은 유지된다
        st = th.register(p, "UFoo", "미션 흐름", df_fn=lambda t: (5, 961))
        assert st == "added_side", st
        st2 = th.register(p, "UBar", "태스크 흐름", df_fn=lambda t: (None, 0))
        assert st2 == "added_side_unmeasured", st2


def test_noop_still_works_after_guard():
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        _yaml_target(p, "UFoo")
        ok = lambda t: (0, 961)                          # noqa: E731
        assert th.register(p, "UFoo", "미션 흐름", df_fn=ok) == "added"
        assert th.register(p, "UFoo", "미션 흐름", df_fn=ok) == "noop"


def test_queue_route_does_not_bypass_the_guard():
    """[중요] 요청자 대행 라우트(2026-08-20)가 가드를 우회하지 않는가.

    가드는 `thesaurus.register` **안**에 있다. 라우트가 판정을 다시 하면 두 벌이 되고
    문턱값이 바뀔 때 갈라진다 — 그래서 라우트는 얇아야 하고, 문턱 상수가 거기 있으면
    그것이 곧 복제의 증거다.
    """
    src = (Path(__file__).resolve().parent / "task_queue" / "server.py").read_text(encoding="utf-8")
    seg = src[src.index('@app.post("/api/v1/thesaurus/alias")'):]
    seg = seg[:seg.index('@app.post("/api/v1/anti_patterns/notify")')]
    assert "th.register(" in seg, "라우트가 register 를 타지 않는다"
    assert "th.ignore(" in seg, "not-a-class 가 ignore 를 타지 않는다"
    for dup in ("GUARD_MIN_CHARS", "GUARD_DF_RATIO", "0.025"):
        assert dup not in seg, f"라우트에 가드 문턱이 복제돼 있다: {dup}"
    assert "rejected" in seg or 'status.startswith("added")' in seg, \
        "거부 상태를 그대로 말하지 않는다"
    # [중요] 8103 이 아니라 큐(8101)에 둔 이유를 코드가 스스로 적어 두는가 — 다음 세션이
    #   "읽기가 8103 인데 왜 쓰기는 8101 이냐" 를 다시 파헤치지 않게.
    models = (Path(__file__).resolve().parent / "task_queue" / "models.py").read_text(encoding="utf-8")
    assert "무인증" in models, "무인증 공개(8103) 근거가 적혀 있지 않다"


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
