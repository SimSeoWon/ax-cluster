"""작업장 상주 데몬 안전 가드 — 원전 `worker/safety.py`(81줄) 이식 (#204, #165 부활 조건 충족).

[중요] #165 가 "되살릴 조건 = 상주 데몬이 생길 때"로 잠들어 있었고, claimer(#204)가 정확히
그 조건이다. 세 가드 전부 원전 글자대로, 바뀐 것은 로그 함수 주입과 로그 경로뿐:

    crash handler     silent process death 잡기 — faulthandler(C 레벨) + excepthook(파이썬)
                      + atexit 마커. 로그 마지막 줄이 "boot …" 로 끝나면 비정상 종료
    sleep guard       OS sleep 차단 — sleep 이 들어가면 heartbeat 스레드도 얼어서
                      lease 만료 → reclaim → submit 거절 → 작업 통째 폐기 (원전 실측 서사)
    quick-edit guard  윈도우 콘솔 클릭 한 번이 프로세스 I/O 를 통째로 멈추는
                      selection mode 차단 — Enter/ESC 전까지 freeze (원전 실측 서사)

[주의] sleep/quick-edit 은 윈도우 전용 — 다른 OS 에선 조용히 "해당 없음" 을 **말하고** 넘어간다.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _default_log(msg: str) -> None:
    print(msg, flush=True)


def setup_crash_handler(log_dir: Path, log=_default_log):
    """크래시 진단 — silent process death 잡기. `<log_dir>/claimer_crash.log` 의 마지막 줄이
    "boot ..." 으로 끝나면 비정상 종료(crash·kill·power loss), "clean exit ..." 면 정상."""
    try:
        import atexit
        import faulthandler
        p = Path(log_dir) / "claimer_crash.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        _crash_log = open(p, "a", encoding="utf-8", buffering=1)
        _crash_log.write(f"\n=== boot {datetime.now().isoformat()} pid={os.getpid()} "
                         f"argv={sys.argv[1:]} ===\n")
        faulthandler.enable(file=_crash_log)

        def _excepthook(exc_type, exc_value, exc_tb):
            _crash_log.write(f"\n=== uncaught {datetime.now().isoformat()} ===\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=_crash_log)
            _crash_log.flush()
            try:
                log(f"[crash] uncaught {exc_type.__name__}: {exc_value}")
            except Exception:                                # noqa: BLE001 — 원전 그대로
                pass
        sys.excepthook = _excepthook

        def _exit_marker():
            _crash_log.write(f"=== clean exit {datetime.now().isoformat()} "
                             f"pid={os.getpid()} ===\n")
            _crash_log.flush()
        atexit.register(_exit_marker)
    except Exception as e:                                    # noqa: BLE001 — 원전 그대로
        log(f"[warn] crash handler 설치 실패: {e!r}")


def apply_sleep_guard(log=_default_log):
    """OS sleep 차단 — 모니터 sleep 은 막지 않음 (ES_DISPLAY_REQUIRED 미설정).
    프로세스 종료 시 자동 해제."""
    if os.name != "nt":
        log("[sleep-guard] 윈도우 아님 — 해당 없음")
        return
    try:
        import ctypes
        _ES_CONTINUOUS = 0x80000000
        _ES_SYSTEM_REQUIRED = 0x00000001
        if ctypes.windll.kernel32.SetThreadExecutionState(
                _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED):
            log("[sleep-guard] OS sleep 차단 활성 (ES_SYSTEM_REQUIRED | ES_CONTINUOUS)")
        else:
            log("[sleep-guard] SetThreadExecutionState 0 반환 — sleep 차단 비활성, 절전 위험")
    except Exception as e:                                    # noqa: BLE001 — 원전 그대로
        log(f"[sleep-guard] 활성화 실패: {e!r} — 절전 위험")


def apply_quick_edit_guard(log=_default_log):
    """Quick Edit Mode 비활성 — 콘솔 클릭이 프로세스 I/O 를 멈추는 selection mode 차단.
    데몬은 클릭 받을 일이 없어야 정상이므로 부팅 시 비활성."""
    if os.name != "nt":
        log("[quick-edit-guard] 윈도우 아님 — 해당 없음")
        return
    try:
        import ctypes
        _STD_INPUT_HANDLE = -10
        _ENABLE_EXTENDED_FLAGS = 0x0080
        _ENABLE_QUICK_EDIT_MODE = 0x0040
        _hStdin = ctypes.windll.kernel32.GetStdHandle(_STD_INPUT_HANDLE)
        _mode = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetConsoleMode(_hStdin, ctypes.byref(_mode)):
            # ENABLE_EXTENDED_FLAGS 를 세팅해야 ENABLE_QUICK_EDIT_MODE 변경이 적용됨
            new_mode = (_mode.value & ~_ENABLE_QUICK_EDIT_MODE) | _ENABLE_EXTENDED_FLAGS
            if ctypes.windll.kernel32.SetConsoleMode(_hStdin, new_mode):
                log("[quick-edit-guard] Quick Edit Mode 비활성 (콘솔 클릭 freeze 차단)")
            else:
                log("[quick-edit-guard] SetConsoleMode 실패 — 콘솔 클릭 시 freeze 위험")
        else:
            # 콘솔이 없는 환경 (서비스 모드, redirect 등) — 정상
            log("[quick-edit-guard] stdin 콘솔 아님 — 클릭 freeze 위험 없음")
    except Exception as e:                                    # noqa: BLE001 — 원전 그대로
        log(f"[quick-edit-guard] 활성화 실패: {e!r} — 콘솔 클릭 시 freeze 위험")


def apply_all(log_dir: Path, log=_default_log):
    """claimer 기동 시 한 번 — 셋 다 건다."""
    setup_crash_handler(log_dir, log)
    apply_sleep_guard(log)
    apply_quick_edit_guard(log)
