"""미배정 클래스 노출 (소 1.3.6).

지키는 계약: 🔴 **노출만 한다(자동 편입 0). 그리고 안 보여준 것을 세어서 말한다.**
실측 1,806 중 1,695 가 미배정이라, *무엇을 숨겼는지* 말하지 않는 보고는 거짓이 된다.

`.venv/bin/python master/test_unassigned.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths      # noqa: E402
from master.ontology import unassigned as U                # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def test_no_graph_is_not_success() -> None:
    """🔴 그래프가 없으면 '미배정 0' 이 아니라 **모른다** 다."""
    with tempfile.TemporaryDirectory() as t:
        rep = U.scan(ProjectPaths(name="T", root=Path(t)))
        check("총 클래스 0", rep.total_classes == 0)
        check("🔴 0을 성공으로 보고하지 않는다",
              any("그래프가 없다" in n for n in rep.notes), str(rep.notes))
        check("무엇을 해야 하는지 말한다",
              any("master.graph build" in n for n in rep.notes), str(rep.notes))


def _report(**kw) -> U.Report:
    r = U.Report(total_classes=kw.get("total", 100), assigned=kw.get("assigned", 10))
    r.adjacent = [U.Adjacent(name=f"A{i}", domain="D", why="자식(구현체)", via="M")
                  for i in range(kw.get("adj", 3))]
    r.isolated_total = kw.get("iso_total", 50)
    r.isolated = [(f"I{i}", 90 - i) for i in range(kw.get("iso_sample", 5))]
    return r


def test_counts_are_honest() -> None:
    r = _report(total=1806, assigned=111, adj=266, iso_total=1429, iso_sample=8)
    check("미배정 = 총수 − 배정", r.unassigned_total == 1695, str(r.unassigned_total))
    s = r.summary
    check("요약에 분모가 다 있다",
          all(x in s for x in ("1806", "111", "1695", "266", "1429")), s)

    out = r.render(limit=5)
    # 🔴 잘랐으면 잘랐다고 쓴다 — 안 그러면 "이게 전부" 로 읽힌다
    check("🔴 인접을 자르면 남은 수를 적는다", "외 261건" in out, out[:300])
    check("🔴 고립 총수를 숨기지 않는다", "1429건" in out, out[:400])
    check("표본이 규모 순이다", out.index("I0") < out.index("I1"))
    # 🔴 이 모듈의 존재 이유
    check("🔴 자동 편입 안 한다고 못박는다", "자동 편입은 하지 않는다" in out)


def test_adjacent_carries_reason() -> None:
    """🔴 근거 없는 후보는 판단할 수 없다 — `collect.propose` 와 같은 규칙."""
    a = U.Adjacent(name="AFoo", domain="MissionRuntime", why="자식(구현체)", via="UBar")
    check("어디에 붙을지 말한다", "MissionRuntime" in a.line, a.line)
    check("왜인지 말한다", "자식" in a.line, a.line)
    check("무엇을 통해서인지 말한다", "UBar 경유" in a.line, a.line)
    check("경유가 없으면 괄호가 깨지지 않는다",
          U.Adjacent("A", "D", "#include 이웃").line.endswith(")"),
          U.Adjacent("A", "D", "#include 이웃").line)


def test_isolated_is_a_signal_not_noise() -> None:
    """🔴 고립분을 숨기면 *도메인이 모자라다* 는 신호가 사라진다."""
    r = _report(total=1806, assigned=111, adj=0, iso_total=1429, iso_sample=3)
    out = r.render()
    check("인접이 없어도 그렇게 쓴다", "붙을 자리가 보이는 것 — 없다" in out, out[:200])
    check("고립은 여전히 보고한다", "1429건" in out, out[:300])


def test_read_only() -> None:
    """🔴 이 모듈은 아무것도 쓰지 않는다."""
    src = (Path(__file__).resolve().parent / "ontology" / "unassigned.py").read_text("utf-8")
    for banned in ("yaml_io.write", ".write_text(", ".unlink(", "mkdir("):
        check(f"🔴 {banned} 를 쓰지 않는다", banned not in src)


def main() -> int:
    for fn in (test_no_graph_is_not_success, test_counts_are_honest,
               test_adjacent_carries_reason, test_isolated_is_a_signal_not_noise,
               test_read_only):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_unassigned: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
