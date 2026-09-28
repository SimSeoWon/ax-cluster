"""프로젝트 프로필 — **사람만 아는 것**을 받아 적립하고, 없으면 등재를 거절한다 (`#650`).

검증하는 것:

    ① 두 부류를 안 섞는다 — `measure()`(A) 의 값은 **저장되지 않는다**
    ② 필수 칸 판정 — 빈 프로필은 `missing` 이 전부이고, `game` 이면 `genre` 도 필수다
    ③ 🔴 **집행** — `blockers` 가 비지 않으면 `register_work` 가 **거절**한다
    ④ `blockers` ≠ `missing` — `engine_decided: false` 는 기록된 답이지만 등재는 막힌다
    ⑤ 검증은 fail-closed — 모르는 칸·모르는 용도·한 단어 서술은 **거절**한다
    ⑥ 부분 저장을 허용한다 (받은 것을 버리면 사람이 같은 말을 두 번 한다)
    ⑦ `{PROJECT_LINE}` 이음매 — 프로필이 비면 「비어 있다」고 말하고, 차면 그 문장이 들어간다
    ⑧ 🔴 **온보딩 판정기가 이 단계를 본다** — 선언(`spec.SERVER_STEPS`)과 판정기가 같이 있다

`.venv/bin/python master/test_project_profile.py`
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
# [중요] 테스트가 스스로 환경을 세운다 — `test_client_bundle.py` 와 같은 이유다.
os.environ.setdefault("AX_PROJECTS_ROOT", str(_REPO))

from master.client import spec                                       # noqa: E402
from master.projects import onboard, profile as PF                   # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, got: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


class _Tmp:
    """프로필 적립처를 임시 디렉토리로 돌린다 — **저장소의 진짜 정본을 건드리지 않는다.**"""

    def __init__(self, tmp: Path):
        self.tmp, self._orig = tmp, PF.profile_dir

    def __enter__(self):
        PF.profile_dir = lambda: self.tmp
        return self

    def __exit__(self, *a):
        PF.profile_dir = self._orig


def test_two_kinds_are_not_mixed(tmp):
    print("\n① 측정(A)은 결정(B) 자리에 적립되지 않는다")
    with _Tmp(tmp):
        m = PF.measure("NS")
        check("measure 는 소스 트리를 잰다 (EngineAssociation)", "engine_association" in m, str(m)[:120])
        check("[중요] 측정값은 저장되지 않는다 — 프로필은 비어 있다", PF.load("NS") == {}, str(PF.load("NS")))
        check("  그래서 측정만으로는 `missing` 이 줄지 않는다", set(PF.REQUIRED) <= set(PF.missing("NS")))


def test_required_fields(tmp):
    print("\n② 필수 칸 · `game` 이면 장르도 필수")
    with _Tmp(tmp):
        check("빈 프로필은 필수 칸 전부가 미수집", set(PF.missing("NS")) == set(PF.REQUIRED))
        PF.save("NS", kind="unreal", engine_decided=True, engine="Unreal Engine", engine_version="5.8",
                language="C++", purpose="game", overview="이 프로젝트는 " + "가" * 50)
        check("[중요] purpose=game 이면 genre 가 남는다", PF.missing("NS") == ["genre"], str(PF.missing("NS")))
        PF.save("NS", genre="액션")
        check("  genre 를 채우면 미수집이 없다", PF.missing("NS") == [], str(PF.missing("NS")))


def test_blockers_are_not_missing(tmp):
    print("\n④ `blockers` 는 `missing` 과 다르다")
    with _Tmp(tmp):
        PF.save("NS", kind="unreal", engine_decided=False, engine="미정", engine_version="미정",
                language="C++", purpose="rnd", overview="엔진을 아직 고르는 중인 " + "탐색" * 20)
        check("[중요] 답을 다 받았으므로 미수집은 없다", PF.missing("NS") == [], str(PF.missing("NS")))
        check("🔴 그래도 등재는 막힌다 (engine_decided=false)",
              any("확정" in b for b in PF.blockers("NS")), str(PF.blockers("NS")))


def test_validation_is_fail_closed(tmp):
    print("\n⑤ 검증은 fail-closed — 조용히 무시하지 않는다")
    with _Tmp(tmp):
        for name, kw in (("모르는 칸", {"engin": "x"}),
                         ("모르는 용도", {"purpose": "mmo"}),
                         ("한 단어 서술", {"overview": "게임"}),
                         ("engine_decided 가 문자열", {"engine_decided": "yes"})):
            try:
                PF.save("NS", **kw)
                check(f"{name} 은 거절된다", False, "예외가 안 났다")
            except ValueError:
                check(f"{name} 은 거절된다", True)


def test_partial_save(tmp):
    print("\n⑥ 부분 저장을 허용한다")
    with _Tmp(tmp):
        PF.save("NS", engine="Unreal Engine")
        got = PF.save("NS", language="C++")
        check("먼저 준 값이 남아 있다", PF.load("NS").get("engine") == "Unreal Engine")
        check("[중요] 미완은 미완이라고 계속 말한다", got["missing"], str(got["missing"]))


def test_project_line_seam(tmp):
    print("\n⑦ `{PROJECT_LINE}` 이음매")
    with _Tmp(tmp):
        empty = PF.project_line("NS")
        check("[중요] 비면 「비어 있다」고 말하고 지어내지 않는다", "비어 있다" in empty, empty[:80])
        check("  채우는 길을 가리킨다", "set_project_profile" in empty)
        PF.save("NS", kind="unreal", engine_decided=True, engine="Unreal Engine", engine_version="5.8",
                language="C++ 중심", purpose="game", genre="소울라이크",
                overview="근접 전투의 방어 판정을 " + "다루는 " * 12)
        line = PF.project_line("NS")
        check("차면 사람이 준 문장이 들어간다", "소울라이크" in line and "방어 판정" in line, line[:120])
        check("[주의] 엔진·버전도 사람의 답에서 온다", "Unreal Engine 5.8" in line, line[:80])


def test_onboarding_sees_it(tmp):
    print("\n⑧ 🔴 선언과 판정기가 같이 있다")
    keys = [s.key for s in spec.SERVER_STEPS]
    check("[중요] 단계가 선언돼 있다", "profile" in keys, str(keys))
    check("  `conventions` 보다 앞이다 (그 단계가 놓는 본문을 이 값이 채운다)",
          keys.index("profile") < keys.index("conventions"), str(keys))
    check("[중요] 판정기가 붙어 있다 — 선언만 있으면 영원히 「미확인」이다",
          "profile" in onboard.PROBES)


def test_register_refuses(tmp):
    print("\n③ 🔴 집행 — 프로필이 없으면 등재를 거절한다")
    from master.work.register import RegisterError, register_work

    class _Paths:
        name = "NS"

    with _Tmp(tmp):
        try:
            register_work("제목", [object()], paths=_Paths(), target_repo="x")
            check("등재가 거절된다", False, "예외가 안 났다")
        except RegisterError as e:
            check("등재가 거절된다", True)
            check("  사유에 미수집 칸이 실린다", "프로필" in str(e), str(e)[:140])
            check("[중요] 추측 금지를 명시한다", "추측" in str(e), str(e)[-160:])
        PF.save("NS", kind="unreal", engine_decided=True, engine="Unreal Engine", engine_version="5.8",
                language="C++", purpose="tool", overview="사내 툴이다 " + "설명 " * 20)
        check("  프로필이 차면 이 게이트는 통과한다 (다음 검증으로 넘어간다)",
              PF.blockers("NS") == [], str(PF.blockers("NS")))


def test_index_only_kind(tmp):
    print("\n⑨ 🔴 `kind` — index_only 는 색인까지만 (`#693`)")
    with _Tmp(tmp):
        check("kind 가 없으면 미수집에 kind 가 있다", "kind" in PF.missing("K"), str(PF.missing("K")))
        check("  kind 가 없으면 kind_of 는 빈 값 (unreal 로 읽지 않는다)", PF.kind_of("K") == "")
        try:
            PF.save("K", kind="python")
            check("모르는 kind 는 거절한다", False, "예외가 안 났다")
        except ValueError as e:
            check("모르는 kind 는 거절한다", "kind" in str(e), str(e))
        PF.save("K", kind="index_only", language="Python · C++ 서브모듈", purpose="tool",
                overview="텍스트로 애니메이션 모션을 만드는 WebUI 래퍼다 " + "설명 " * 10)
        check("[중요] index_only 는 엔진 세 칸을 요구하지 않는다", PF.missing("K") == [],
              str(PF.missing("K")))
        check("🔴 그래도 등재는 막힌다 (분산 작업 없음)",
              any("index_only" in b for b in PF.blockers("K")), str(PF.blockers("K")))
        check("  is_index_only", PF.is_index_only("K"))
        check("  project_line 이 엔진을 지어내지 않는다",
              "색인 전용" in PF.project_line("K") and "None" not in PF.project_line("K"),
              PF.project_line("K")[:120])
        PF.save("U", kind="unreal", language="C++", purpose="tool",
                overview="엔진 칸을 아직 안 채운 언리얼 프로젝트 " + "설명 " * 10)
        check("unreal 은 엔진 세 칸이 여전히 필수",
              set(PF.ENGINE_FIELDS) <= set(PF.missing("U")), str(PF.missing("U")))


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        for fn in (test_two_kinds_are_not_mixed, test_required_fields,
                   test_blockers_are_not_missing, test_validation_is_fail_closed,
                   test_partial_save, test_project_line_seam,
                   test_onboarding_sees_it, test_register_refuses,
                   test_index_only_kind):
            sub = Path(d) / fn.__name__
            sub.mkdir()
            fn(sub)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_project_profile: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
