"""σ 감사 스캐너 (소 4.2.1) — [중요] **판정을 내리지 않는다는 것**을 못박는다.

원전이 6건 중 **4건을 「정상 fallback 이라 유지」**로 판정했다. 그래서 이 스캐너의 계약은
*"silent fallback 인데 **의도가 적혀 있지 않다**"* 를 찾는 것까지다 — 의도가 적혀 있으면 설계다.

[주의] 이 파일이 지키는 것은 **좁히는 조건 셋**이다. 첫 이식에서 그것들을 빠뜨려 114건이 나왔고
(원전은 6건) 그건 노이즈였다:
  ① 넓은 핸들러만 (`except Exception`/bare) — 좁은 예외는 의도적이다
  ② 예외를 **값으로 돌려주면** 조용하지 않다 (`return _fail(e)` — 우리 MCP 도구 24개가 그 형태)
  ③ 의도는 **핸들러 블록의 주석**에서도 찾는다 (독스트링만 보면 주석이 소실된다)

`.venv/bin/python master/test_sigma_audit.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import sigma_audit as S      # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _scan(src: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.py"
        p.write_text(src, encoding="utf-8")
        found, err = S.scan_file(p, rel="m.py")
        return found, err


def test_catches_broad_silent():
    f, _ = _scan("def g():\n    try:\n        x()\n    except Exception:\n        pass\n")
    check("넓은 핸들러 + pass 를 잡는다", len(f) == 1, str(f))
    if f:
        check("swallow 를 적는다", f[0].swallow == "pass", f[0].swallow)
        check("의도 없음으로 표시", not f[0].intent_documented)


def test_narrow_exception_is_not_flagged():
    """[중요] ① 좁은 예외는 의도적이다."""
    for exc in ("ValueError", "OSError", "(TypeError, ValueError)", "sqlite3.OperationalError"):
        f, _ = _scan(f"def g():\n    try:\n        x()\n    except {exc}:\n        pass\n")
        check(f"except {exc} 는 안 잡는다", len(f) == 0, str(f))
    f, _ = _scan("def g():\n    try:\n        x()\n    except:\n        pass\n")
    check("bare except 는 잡는다", len(f) == 1, str(f))


def test_returning_exception_is_loud():
    """[중요] ② 예외를 값으로 돌려주면 조용하지 않다."""
    f, _ = _scan("def g():\n    try:\n        x()\n    except Exception as e:\n        return _fail(e)\n")
    check("예외를 돌려주면 안 잡는다", len(f) == 0, str(f))
    f, _ = _scan("def g():\n    try:\n        x()\n    except Exception as e:\n        return ''\n")
    check("바인딩만 하고 안 쓰면 잡는다", len(f) == 1, str(f))


def test_logging_is_loud():
    for body in ("log('x')", "print('x')", "raise", "out.append('x')"):
        f, _ = _scan(f"def g():\n    try:\n        x()\n    except Exception:\n        {body}\n")
        check(f"{body} 는 조용하지 않다", len(f) == 0, str(f))


def test_intent_in_handler_comment():
    """[중요] ③ 의도는 핸들러 **주석**에서도 찾는다."""
    src = ("def g():\n    try:\n        x()\n    except Exception:\n"
           "        # 못 읽으면 빈 값이 맞다 — 폴백이 정상 동작이다\n        pass\n")
    f, _ = _scan(src)
    check("주석의 의도를 읽는다", len(f) == 1 and f[0].intent_documented, str(f))
    src2 = ("def g():\n    '''폴백은 의도된 것이다.'''\n    try:\n        x()\n"
            "    except Exception:\n        pass\n")
    f2, _ = _scan(src2)
    check("독스트링의 의도도 읽는다", len(f2) == 1 and f2[0].intent_documented, str(f2))


def test_report_only_surfaces_undocumented():
    src = ("def a():\n    try:\n        x()\n    except Exception:\n        pass\n\n"
           "def b():\n    try:\n        x()\n    except Exception:\n"
           "        # 폴백이 정상이다\n        pass\n")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "m.py").write_text(src, encoding="utf-8")
        r = S.scan(Path(td))
        check("전체는 2건", len(r.findings) == 2, str(len(r.findings)))
        check("[중요] 사람이 볼 것은 1건", len(r.undocumented) == 1, str(len(r.undocumented)))
        check("요약에 두 수가 다 있다", "2건" in r.summary() and "1건" in r.summary(), r.summary())


def test_tests_are_skipped():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "test_x.py").write_text(
            "def g():\n    try:\n        x()\n    except Exception:\n        pass\n", encoding="utf-8")
        r = S.scan(Path(td))
        check("테스트 파일은 훑지 않는다", len(r.findings) == 0 and r.scanned == 0, r.summary())


def test_syntax_error_is_reported_not_swallowed():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "bad.py").write_text("def (\n", encoding="utf-8")
        r = S.scan(Path(td))
        check("[주의] 파싱 실패를 삼키지 않고 보고한다", len(r.parse_failed) == 1, str(r.parse_failed))
        check("요약에도 실린다", "파싱 실패" in r.summary(), r.summary())


def main() -> int:
    for fn in (test_catches_broad_silent, test_narrow_exception_is_not_flagged,
               test_returning_exception_is_loud, test_logging_is_loud,
               test_intent_in_handler_comment, test_report_only_surfaces_undocumented,
               test_tests_are_skipped, test_syntax_error_is_reported_not_swallowed):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_sigma_audit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
