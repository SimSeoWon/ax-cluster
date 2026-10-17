"""`/distribute` ② register — `stage_register` 가 `register_work` 를 **실제 시그니처로** 부른다.

[중요] `#815` ② (mypy `[call-arg]`). `53fc90f`(`#348`) 가 `register_work` 의 `searcher` 를
지웠는데 `stage_register` 는 계속 `searcher=` 를 넘겨, CLI `register` 가 **늘 TypeError** 였다.
이 경로를 덮는 테스트가 없어 보이지 않았다.

`python3 master/test_distribute.py`
"""
from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_signature_has_no_searcher() -> None:
    """[중요] 지운 매개변수가 입구에 남아 있지 않다."""
    from master.work import distribute
    params = inspect.signature(distribute.stage_register).parameters
    check("[중요] stage_register 에 searcher 가 없다", "searcher" not in params, str(list(params)))


def test_register_call_binds_real_signature() -> None:
    """[중요] 넘기는 인자가 **실물** `register_work` 시그니처에 묶인다 — 망·트윈 없이."""
    from master.work import decompose, distribute, register

    real = register.register_work
    sig = inspect.signature(real)
    seen: dict = {}

    def fake_load_plan(paths, slug):
        pieces = [decompose.Piece(stem="a", classes=["AFoo"], files=["Source/Foo.h"])]
        return pieces, {"instruction": "고친다", "requires": []}

    def fake_register_work(*args, **kwargs):
        try:
            sig.bind(*args, **kwargs)
            seen["bound"] = True
        except TypeError as e:
            seen["error"] = str(e)
            raise
        seen["kwargs"] = kwargs
        # [주의] 실물 `Registered` 를 돌려준다 — stage_register 가 읽는 표면이 그대로다
        return register.Registered(work_id="w-test", tasks=[
            register.TaskResult(stem="a", task_id="t-1"),
            register.TaskResult(stem="b", error="거절됨")])

    orig_load, orig_reg = distribute.load_plan, register.register_work
    distribute.load_plan, register.register_work = fake_load_plan, fake_register_work
    st = None
    try:
        st = distribute.stage_register(types.SimpleNamespace(root=Path("/nonexistent")),
                                       slug="s", title="제목", target_repo="o/r")
    except Exception as e:   # TypeError(#815 ②) · AttributeError(manifest_degraded 잔재)
        check("[중요] 예외 없이 돈다", False, f"{type(e).__name__}: {e}")
    finally:
        distribute.load_plan, register.register_work = orig_load, orig_reg

    check("[중요] 실물 시그니처에 묶인다", seen.get("bound") is True, seen.get("error", ""))
    check("searcher 를 넘기지 않는다", "searcher" not in seen.get("kwargs", {}),
          str(seen.get("kwargs")))
    check("Staged 를 돌려준다", isinstance(st, distribute.Staged), repr(st))
    if isinstance(st, distribute.Staged):
        check("register 단계다", st.stage == "register", st.stage)
        check("work_id 를 실어 낸다", st.detail.get("work_id") == "w-test", str(st.detail))
        check("성공 조각 줄을 그린다", "  OK a → t-1" in st.text, st.text)
        check("실패 조각 줄을 그린다", "  FAIL b → 거절됨" in st.text, st.text)
        check("[중요] 실패 조각이 있으면 ok 가 아니다", st.ok is False, str(st.ok))
        check("[주의] 게이트 미확인을 적는다", "골조 빌드를 확인하지 않았다" in st.text, st.text)


if __name__ == "__main__":
    for fn in (test_signature_has_no_searcher, test_register_call_binds_real_signature):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_distribute: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
