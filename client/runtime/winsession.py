"""Windows 세션 0 판정 (`#832`) — 표준 라이브러리만 쓴다. 리눅스·Windows 어디서든 임포트된다.

🔴 Windows OpenSSH 는 명령을 **SessionId 0**(`NT AUTHORITY\\NETWORK` 로그온)에서 돌린다(실측 2026-10-18).
사용자 대화형 자격이 필요한 도구(agy 로그인 · codex 샌드박스)는 거기서 **늦고 엉뚱한 오류**로 죽는다 —
agy 는 *"You are not logged into Antigravity"* 를 내고 우리 코드는 60초 뒤 「실제 모델 미상」으로 보고했다.
몇 달째 되풀이됐으므로 절차서가 아니라 **코드가 막는다**: 세션 0 이면 고정 사유로 즉시 거절한다.

[중요] 배달본은 `.ax/lib/axmaster/clientside/winsession.py`, 저장소는 `client/runtime/winsession.py` 다.
부르는 쪽은 **경로로** 로드한다(`session1_conductor` 가 `work/usage.py` 를 로드하는 방식).
[주의] 판정은 예외를 던지지 않는다 — 못 재면 `None`(세션 0 아님)이다. 리눅스는 늘 `None` 이다.
"""
from __future__ import annotations

import sys

REFUSAL = ("세션 0(SSH·비대화형)에서는 실행하지 않는다 — 세션 1 런처(schtasks /IT) 또는 "
           "그 PC 의 대화형 세션에서 실행 (#832)")


def session_id() -> int | None:
    """현재 프로세스의 Windows SessionId. Windows 가 아니거나 못 재면 `None`."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        sid = wintypes.DWORD()
        if not k32.ProcessIdToSessionId(k32.GetCurrentProcessId(), ctypes.byref(sid)):
            return None
        return int(sid.value)
    except Exception:                                            # noqa: BLE001
        return None


def is_session0() -> bool:
    """Windows 이고 SessionId 가 0 일 때만 True."""
    return sys.platform == "win32" and session_id() == 0


def refuse_reason() -> str:
    """세션 0 이면 고정 사유 + 측정한 SessionId, 아니면 `""`."""
    if not is_session0():
        return ""
    return f"{REFUSAL} · SessionId={session_id()}"
