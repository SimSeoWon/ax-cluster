"""`client/runtime/winsession.py` 검사 (`#832`) — Windows 세션 0 판정.

리눅스에서 Windows 를 흉내 낸다: `sys.platform` 을 바꾸고 `ctypes.windll` 에 가짜 kernel32 를 꽂는다.
[중요] 판정은 **예외를 던지지 않는다** — 못 재면 `None`(세션 0 아님)이다.
"""
from __future__ import annotations

import ctypes
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "client" / "runtime" / "winsession.py"

PASS = FAIL = 0
PLATFORM, HAD_WINDLL = sys.platform, hasattr(ctypes, "windll")


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label} — {detail}")


def load():
    spec = importlib.util.spec_from_file_location("ax_test_winsession", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeK32:
    """`ProcessIdToSessionId` 가 `sid` 를 써 넣는다. `ok=False` 면 0(실패) 반환, `boom` 이면 예외."""

    def __init__(self, sid=0, ok=True, boom=None):
        self.sid, self.ok, self.boom, self.calls = sid, ok, boom, []

    def GetCurrentProcessId(self):
        return 4242

    def ProcessIdToSessionId(self, pid, ref):
        self.calls.append(pid)
        if self.boom:
            raise self.boom
        if not self.ok:
            return 0
        ref._obj.value = self.sid
        return 1


class Win:
    """`sys.platform = "win32"` + `ctypes.windll.kernel32 = k32` 를 잠시 꽂는다."""

    def __init__(self, k32=None, windll_missing=False):
        self.k32, self.missing = k32, windll_missing

    def __enter__(self):
        self.plat, self.had = sys.platform, hasattr(ctypes, "windll")
        self.old = getattr(ctypes, "windll", None)
        sys.platform = "win32"
        if self.missing:
            if self.had:
                delattr(ctypes, "windll")
        else:
            ctypes.windll = type("W", (), {"kernel32": self.k32})()
        return self

    def __exit__(self, *exc):
        sys.platform = self.plat
        if self.had:
            ctypes.windll = self.old
        elif hasattr(ctypes, "windll"):
            delattr(ctypes, "windll")
        return False


def main() -> int:
    W = load()
    print("\n[1] 리눅스(실제 플랫폼)")
    check("임포트된다 · REFUSAL 은 고정 문구(#832)", "#832" in W.REFUSAL and "세션 0" in W.REFUSAL)
    if sys.platform != "win32":
        check("non-Windows → session_id None", W.session_id() is None)
        check("non-Windows → is_session0 False", W.is_session0() is False)
        check("non-Windows → refuse_reason 빈 문자열", W.refuse_reason() == "")

    print("\n[2] Windows 흉내 — SessionId 0 (SSH)")
    k = FakeK32(sid=0)
    with Win(k):
        check("session_id 0", W.session_id() == 0)
        check("[중요] is_session0 True", W.is_session0() is True)
        r = W.refuse_reason()
        check("[중요] 사유 = 고정 문구 + 측정 SessionId", r.startswith(W.REFUSAL) and "SessionId=0" in r, r)
    check("현재 PID 로 물었다", k.calls and k.calls[0] == 4242, str(k.calls))

    print("\n[3] Windows 흉내 — SessionId 18 (대화형, .33 실측값)")
    with Win(FakeK32(sid=18)):
        check("session_id 18", W.session_id() == 18)
        check("is_session0 False", W.is_session0() is False)
        check("refuse_reason 빈 문자열", W.refuse_reason() == "")

    print("\n[4] Windows 흉내 — 못 재면 None (예외를 던지지 않는다)")
    with Win(FakeK32(ok=False)):
        check("API 가 0 을 돌려주면 None", W.session_id() is None)
        check("  → 세션 0 아님", W.is_session0() is False and W.refuse_reason() == "")
    with Win(FakeK32(boom=OSError("access denied"))):
        try:
            got = W.session_id()
            check("API 예외 → None", got is None, str(got))
        except Exception as e:                                   # noqa: BLE001
            check("API 예외 → None", False, f"예외가 샜다: {e!r}")
        check("  → is_session0 False", W.is_session0() is False)
    with Win(windll_missing=True):
        try:
            check("windll 이 없으면 None", W.session_id() is None)
        except Exception as e:                                   # noqa: BLE001
            check("windll 이 없으면 None", False, f"예외가 샜다: {e!r}")

    print("\n[5] 🔴 리눅스는 영향 없음 — windll 을 건드리지 않는다 (.43·마스터)")
    for plat in ("linux", "darwin"):
        k = FakeK32(sid=0)
        real = sys.platform
        had, old = hasattr(ctypes, "windll"), getattr(ctypes, "windll", None)
        ctypes.windll = type("W", (), {"kernel32": k})()     # 세션 0 을 말하는 가짜가 꽂혀 있어도
        sys.platform = plat
        try:
            check(f"{plat}: session_id None", W.session_id() is None)
            check(f"{plat}: is_session0 False · 사유 없음", W.is_session0() is False and W.refuse_reason() == "")
            check(f"[중요] {plat}: kernel32 를 부르지 않았다", k.calls == [], str(k.calls))
        finally:
            sys.platform = real
            if had:
                ctypes.windll = old
            else:
                delattr(ctypes, "windll")

    print("\n[6] 원상 복구")
    check("sys.platform 복구", sys.platform == PLATFORM, sys.platform)
    check("ctypes.windll 복구", hasattr(ctypes, "windll") == HAD_WINDLL)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_winsession: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
