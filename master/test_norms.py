"""소 2.3.1 도메인 규범 번들 — 관련성 필터 · 예산 · [중요] 결손 명시.

**LLM 도 임베딩도 부르지 않는다.** 검색은 주입한다 — 여기서 지켜야 하는 계약은 검색 품질이
아니라 *"관련된 것만, 예산 안에서, 빈 것은 비었다고 말한다"* 이다.

`python3 master/test_norms.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths        # noqa: E402
from master.ontology import yaml_io                          # noqa: E402
from master.work import norms, skeleton                      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _project(tmp: Path) -> ProjectPaths:
    paths = ProjectPaths(name="T", root=tmp)
    d = paths.ontology / "domains" / "MissionRuntime"
    yaml_io.write(d / "domain.yaml", {
        "domain": "MissionRuntime", "tier": 3,
        "summary": "미션 실행을 관리한다. " + "가" * 400,     # [중요] 상한 확인용으로 길게
        "actions": ["L3/actions/RunTask.yaml", "L3/actions/UnrelatedUi.yaml"],
        "invariants_files": [f"L3/invariants/Inv{i}.yaml" for i in range(9)],
    })
    yaml_io.write(d / "L3/actions/RunTask.yaml", {
        "name": "RunTask", "description": "태스크를 실행한다",
        "implementation": {"primary": "UMissionTaskExecutor::Run"},
        "objects_affected": ["UMissionTaskExecutor"],
    })
    yaml_io.write(d / "L3/actions/UnrelatedUi.yaml", {
        "name": "UnrelatedUi", "description": "UI 만 만진다",
        "implementation": {"primary": "UWidgetThing::Show"},
        "objects_affected": ["UWidgetThing"],
    })
    for i in range(9):
        yaml_io.write(d / f"L3/invariants/Inv{i}.yaml", {
            "name": f"Inv{i}", "text": f"규칙 {i} 는 항상 참이다. " + "나" * 300,
            "evidence": f"X.cpp:{i}",
        })
    return paths


def _hit(domain="MissionRuntime"):
    return [{"domain": domain, "source": "bm25", "rrf_score": 0.03}]


def test_relevance() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        b = norms.attach(paths, classes=["UMissionTaskExecutor"],
                         search=lambda *a, **k: _hit())
        check("도메인이 실린다", len(b.domains) == 1, str(b.degraded))
        acts = [a["name"] for a in b.domains[0].actions]
        # [중요] 목표 ②는 "관련된 것만" 이다
        check("[중요] 대상 클래스와 얽힌 액션만", acts == ["RunTask"], str(acts))

        b2 = norms.attach(paths, classes=[], stem="미션",
                          search=lambda *a, **k: _hit())
        acts2 = [a["name"] for a in b2.domains[0].actions]
        check("대상이 없으면 전부 관련으로 본다", set(acts2) == {"RunTask", "UnrelatedUi"}, str(acts2))


def test_budget() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        b = norms.attach(paths, classes=["UMissionTaskExecutor"],
                         search=lambda *a, **k: _hit())
        d = b.domains[0]
        check("summary 를 자른다", len(d.summary) <= norms.SUMMARY_CHARS + 1, str(len(d.summary)))
        check("invariant 본문을 자른다",
              all(len(i["text"]) <= norms.INVARIANT_CHARS + 1 for i in d.invariants))
        check("invariant 개수 상한", len(d.invariants) == norms.MAX_INVARIANTS,
              str(len(d.invariants)))
        # [중요] 잘랐으면 잘랐다고 말한다
        check("[중요] 뺀 개수를 센다", d.dropped_invariants == 3, str(d.dropped_invariants))
        text = "\n".join(b.render())
        check("[중요] 뺀 사실이 본문에 보인다", "예산으로 제외" in text and "직접 읽을 것" in text)


def test_degraded_is_visible() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))

        b = norms.attach(paths, classes=[], stem="")
        check("질의를 못 만들면 사유가 남는다",
              not b.ok and "질의를 만들 수 없" in " ".join(b.degraded), str(b.degraded))

        b = norms.attach(paths, classes=["UFoo"], search=lambda *a, **k: [])
        check("0건이어도 실패가 아니다 (노이즈 차단일 수 있다)",
              not b.ok and "노이즈 차단" in " ".join(b.degraded), str(b.degraded))
        text = "\n".join(b.render())
        check("[중요] 비면 '규범 grounding 없이 진행된다' 를 본문에 쓴다",
              "규범 grounding 없이" in text, text[:80])

        def boom(*a, **k):
            raise RuntimeError("색인 없음")
        b = norms.attach(paths, classes=["UFoo"], search=boom)
        check("검색이 터져도 예외를 올리지 않는다", not b.ok)
        check("터진 사유를 적는다", "규범 검색 실패" in " ".join(b.degraded), str(b.degraded))


def test_skeleton_wiring() -> None:
    """[중요] 규범의 소비처는 **골조 프롬프트**다 (매니페스트 철거 2026-09-02).

    종전에는 `manifest.build` 가 규범 절을 본문에 넣는지를 쟀다. 그 문서가 없어졌으므로
    같은 계약을 실제 소비처에서 잰다 — `skeleton.build_prompt` 가 규범을 싣는가.
    """
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        bundle = norms.attach(paths, classes=["UMissionTaskExecutor"],
                              search=lambda *a, **k: _hit())
        lines = bundle.render()
        check("규범 줄이 나온다", bool(lines), str(lines)[:120])
        body = "\n".join(lines)
        check("규범 본문이 들어간다", "지켜야 할 규칙" in body, body[:160])
        d, inv, act = bundle.counts
        check("도메인 수를 센다", d == 1, str(d))
        # [중요] 예산이 도메인당 `MAX_INVARIANTS` 로 잘린다 — 그 상한이 계약이다
        check("항목 수가 예산 상한에서 잘린다", inv == norms.MAX_INVARIANTS, str(inv))
        # [중요] '_미구현_' 은 이제 나오면 안 된다 (소 2.3.1 완료)
        check("[중요] '_미구현_' 자리표시자가 사라졌다", "_미구현" not in body)

        spec = skeleton.SkeletonSpec(stem="X", classes=["UMissionTaskExecutor"],
                                     instruction="만들어라",
                                     files=["Source/X.h", "Source/X.cpp"])
        prompt = skeleton.build_prompt(
            spec, norms="=== DOMAIN NORMS ===\n" + body + "\n=== END DOMAIN NORMS ===")
        check("[중요] **골조 프롬프트가 규범을 싣는다**",
              "DOMAIN NORMS" in prompt and "지켜야 할 규칙" in prompt, prompt[:200])

        empty = norms.NormBundle(degraded=["없음"])
        check("규범이 비면 degraded 로 표시", not empty.ok, str(empty.degraded))
        check("[중요] 왜 비었는지를 돌려준다 (조용히 빈 값 아님)",
              bool(empty.degraded), str(empty.degraded))


def main() -> int:
    for fn in (test_relevance, test_budget, test_degraded_is_visible, test_skeleton_wiring):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_norms: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
