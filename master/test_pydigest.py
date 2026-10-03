"""파이썬 요약본·합성 토큰 기록 테스트 (`#711`·`#713`). pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_pydigest.py

[중요] 지키는 불변식:
   1. **「왜」를 남긴다** — 시그니처·독스트링·본문 안 주석은 남고, 본문 로직만 `...` 로 덜린다
   2. **파싱이 안 되면 `None`** — 호출자가 종전(앞에서 자르기)으로 돌아간다. 지어내지 않는다
   3. **비UE 에만** — UE 프로젝트의 프롬프트는 바뀌지 않는다(사용자 결정 2026-10-03)
   4. **짧으면 그대로** — 상한 안의 소스는 요약하지 않는다
   5. **사용량은 노드가 준 것만** — 값이 없으면 키를 비운다(0 을 지어내지 않는다)
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_synth import pydigest, synth                 # noqa: E402
import importlib                                                  # noqa: E402

# [주의] `master.work` 는 같은 이름의 **함수** `generate` 를 내보낸다 — 모듈을 직접 잡는다
generate = importlib.import_module("master.work.generate")

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


SRC = '''"""모듈 독스트링 — 왜 있나."""
import os

LIMIT = 5   # 상수는 남는다


@decorated
def alpha(x: int) -> int:
    """alpha 의 이유 — #404."""
    # 본문 안 주석도 남는다
    y = x + 1
    z = y * 2
    return z


def beta():
    def inner():
        return SECRET_INNER
    return inner()


class Gamma:
    """클래스 설명."""
    attr = 3

    def method(self):
        return BODY_ONLY_NAME
'''


class _Paths:
    def __init__(self, name: str):
        self.name = name


def main() -> int:
    print("[1] 요약본 — 「왜」를 남기고 본문 로직을 덜어 낸다")
    d = pydigest.digest(SRC)
    t = d.text if d else ""
    check("파싱된다", d is not None)
    check("모듈 독스트링·import·상수가 남는다",
          "모듈 독스트링" in t and "import os" in t and "LIMIT = 5" in t)
    check("데코레이터·시그니처가 남는다", "@decorated" in t and "def alpha(x: int) -> int:" in t)
    check("🔴 함수 독스트링이 남는다 (이 저장소의 「왜」가 여기 있다)", "alpha 의 이유 — #404." in t)
    check("🔴 본문 안 주석 줄도 남는다", "# 본문 안 주석도 남는다" in t)
    check("본문 로직은 덜린다", "y = x + 1" not in t and "return z" not in t, t)
    check("중첩 함수는 바깥 본문과 함께 덜린다", "SECRET_INNER" not in t and "def inner" not in t, t)
    check("클래스 독스트링·속성은 남고 메서드 본문은 덜린다",
          "클래스 설명." in t and "attr = 3" in t and "def method(self):" in t
          and "BODY_ONLY_NAME" not in t, t)
    check("덜어 낸 자리마다 `...` 한 줄", t.count(pydigest.ELIDED) == 3, str(t.count("...")))
    check("세는 값이 맞다 — 함수 3개(alpha·beta·method)", d is not None and d.functions == 3,
          str(d and d.functions))
    check("요약이 원본보다 짧다", d is not None and len(t) < len(SRC))

    print("[2] 파싱 실패는 None — 호출자가 종전 동작으로")
    check("문법 오류면 None", pydigest.digest("def broken(:\n    pass\n") is None)

    print("[3] 프롬프트 본문 선택 — 비UE·긴 .py 에만")
    long_src = SRC + ("\n# 채움 — 상한을 넘기려고 넣은 주석 줄\n" * 400)
    bodies = {"m/a.py": long_src}
    orig = synth._index_only
    try:
        synth._index_only = lambda paths: True
        out, note = synth._prompt_bodies(_Paths("code"), bodies, 4000)
        check("비UE·상한 초과 → 요약본", out["m/a.py"] != long_src and "요약본" in note, note)
        check("[중요] 원본 dict 는 건드리지 않는다 (사실 게이트가 원본으로 대조한다)",
              bodies["m/a.py"] == long_src)
        out2, note2 = synth._prompt_bodies(_Paths("code"), {"m/a.py": SRC}, 4000)
        check("상한 안이면 그대로", out2["m/a.py"] == SRC and note2 == "")
        out3, note3 = synth._prompt_bodies(_Paths("code"), {"m/a.h": "x" * 5000}, 4000)
        check(".py 가 아니면 그대로", out3["m/a.h"] == "x" * 5000)
        out4, note4 = synth._prompt_bodies(_Paths("code"), {"m/a.py": "def (\n" * 900}, 4000)
        check("파싱 실패는 그대로 두고 사유를 남긴다", "파싱 실패" in note4, note4)
        synth._index_only = lambda paths: False
        out5, note5 = synth._prompt_bodies(_Paths("ue"), bodies, 4000)
        check("🔴 UE 프로젝트는 종전 그대로 (사용자 결정)", out5["m/a.py"] == long_src and note5 == "")
    finally:
        synth._index_only = orig

    print("[4] call_broker 사용량 — 노드가 준 것만")
    real = generate.urllib.request.urlopen

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(payload):
        return lambda req, timeout=0: _Resp(json.dumps(payload).encode())

    try:
        generate.urllib.request.urlopen = fake({"response": "ok", "prompt_eval_count": 12,
                                                 "eval_count": 7, "total_duration": 3_500_000_000})
        u: dict = {}
        r = generate.call_broker("p", model="m", token="t", usage=u)
        check("응답 본문은 그대로", r == "ok")
        check("입력·출력·시간이 채워진다", u == {"in": 12, "out": 7, "ms": 3500}, str(u))
        generate.urllib.request.urlopen = fake({"response": "ok"})
        u2: dict = {}
        generate.call_broker("p", model="m", token="t", usage=u2)
        check("[중요] 노드가 안 주면 비운다 (0 을 지어내지 않는다)", u2 == {}, str(u2))
        check("usage 를 안 주는 기존 호출은 그대로", generate.call_broker("p", model="m", token="t") == "ok")
    finally:
        generate.urllib.request.urlopen = real

    print("[5] 합계 — 배치 요약에 토큰이 나온다")
    st = synth.Stats(groups=2, written=2, tokens_in=10, tokens_out=4, digested=1)
    check("요약 줄에 토큰과 요약본 수", "토큰 입력 10 · 출력 4" in st.summary and "요약본 1" in st.summary,
          st.summary)

    print(f"\n{'=' * 46}\n통과 {PASS} · 실패 {FAIL}\n{'=' * 46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
