"""질의 → 도메인 결정적 추론 (소 2.2.2).

🔴 지키는 계약: **모르면 비운다.** 산문에서 도메인 이름을 닮은 말을 찾아 추측하면
*"결정적"* 이라는 이 함수의 유일한 값어치가 사라진다 — 그 일은 `search_norms` 가 하고,
그쪽은 노이즈 3중 차단을 갖고 있다.

`.venv/bin/python master/test_infer.py`
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths      # noqa: E402
from master.context_search import infer as I               # noqa: E402
from master.ontology import package as pkg                 # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _seed(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="T", root=root)
    pkg.write(p, "Runtime", objects=[{"name": "UTaskExec", "layer": 1, "file": "a.h"},
                                     {"name": "UTaskBase", "layer": 1, "file": "b.h"}])
    pkg.write(p, "Editor", objects=[{"name": "UTaskEditor", "layer": 1, "file": "c.h"}])
    return p


@dataclass
class Exp:
    added: list = field(default_factory=list)


def test_direct_identifier() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        r = I.infer(p, "UTaskExec 를 고쳐줘")
        check("소속을 짚는다", r.domains == ["Runtime"], str(r.domains))
        check("🔴 근거를 댄다", r.evidence[0].line.startswith("UTaskExec → Runtime"), r.summary)
        check("어떻게 알았는지도", "질의에 직접" in r.evidence[0].line, r.evidence[0].line)


def test_never_guesses() -> None:
    """🔴 이것이 이 모듈의 존재 이유다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        r = I.infer(p, "런타임 쪽 어딘가를 고쳐줘")     # 'Runtime' 을 닮았지만 클래스가 없다
        check("🔴 닮은 말로 추측하지 않는다", not r.ok, str(r.domains))
        check("모른다고 말한다", "추론 불가" in r.summary, r.summary)

        r2 = I.infer(p, "UNothing 수정")
        check("클래스처럼 생겼지만 소속 없음을 보고", r2.unknown == ["UNothing"], str(r2.unknown))
        check("그래도 도메인은 안 만든다", not r2.ok)
        check("빈 질의는 빈 결과", not I.infer(p, "").ok)


def test_alias_path() -> None:
    """한글 질의는 식별자를 안 쓴다 — 별칭이 실질 경로다."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        r = I.infer(p, "태스크 실행 흐름", expansion=Exp(added=[("태스크 실행", "UTaskExec")]))
        check("별칭으로 짚는다", r.domains == ["Runtime"], str(r.domains))
        check("🔴 별칭이 근거에 남는다", "별칭: 태스크 실행" in r.evidence[0].line,
              r.evidence[0].line)


def test_multiple_domains_ranked() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        r = I.infer(p, "UTaskExec UTaskBase UTaskEditor 정리")
        # Runtime 이 2건, Editor 가 1건 → 근거 많은 쪽이 먼저
        check("근거 수로 정렬한다", r.domains == ["Runtime", "Editor"], str(r.domains))
        check("근거를 다 들고 있다", len(r.evidence) == 3, str(len(r.evidence)))


def test_membership_source() -> None:
    """🔴 출처는 패키지 yaml 이다 — `class_ontology` 표는 비어 있다(실측)."""
    with tempfile.TemporaryDirectory() as t:
        p = _seed(Path(t))
        m = I.membership(p)
        check("패키지에서 읽는다", m.get("UTaskExec") == "Runtime" and m.get("UTaskEditor") == "Editor",
              str(m))
        src = (Path(__file__).resolve().parent / "context_search" / "infer.py").read_text("utf-8")
        check("🔴 죽은 DB 표를 근거로 쓰지 않는다", "class_ontology" not in src.split('"""')[2],
              "본문에서 class_ontology 를 읽는다")
        check("패키지가 없으면 그렇게 말한다",
              "근거가 없다" in I.infer(ProjectPaths(name="X", root=Path(t) / "none"), "U").summary)


def main() -> int:
    for fn in (test_direct_identifier, test_never_guesses, test_alias_path,
               test_multiple_domains_ranked, test_membership_source):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_infer: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
