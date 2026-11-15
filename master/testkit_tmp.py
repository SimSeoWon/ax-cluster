"""검사 프로세스의 임시 디렉터리 정리 (`#970` D14).

`tempfile.mkdtemp()` 로 만든 디렉터리를 검사들이 지우지 않아 `/tmp` 에 `ax-*` 가 4194개 쌓였다(실측
2026-11-15). 검사 파일 맨 위에서 `track()` 을 한 번 부르면, 이 프로세스에서 만든 mkdtemp 디렉터리를
**프로세스가 끝날 때**(단정 실패·예외로 끝나도) 지운다. 검사 도중에는 지우지 않으므로 검사의 동작은
바뀌지 않는다. `TemporaryDirectory` 는 스스로 지우므로 두 번 지워도 무해하다(`ignore_errors`).

    from master import testkit_tmp   # noqa: E402
    testkit_tmp.track()
"""
from __future__ import annotations

import atexit
import shutil
import tempfile

_MADE: list = []
_REAL = tempfile.mkdtemp
_ON = False


def _mkdtemp(*args, **kwargs):
    path = _REAL(*args, **kwargs)
    _MADE.append(path)
    return path


def cleanup() -> int:
    """만든 디렉터리를 지우고 지운 수를 돌려준다(없어진 것도 센다)."""
    n = 0
    while _MADE:
        shutil.rmtree(_MADE.pop(), ignore_errors=True)
        n += 1
    return n


def track() -> None:
    """이 프로세스의 mkdtemp 를 기록하고 끝날 때 지운다. 여러 번 불러도 한 번만 건다."""
    global _ON
    if _ON:
        return
    _ON = True
    tempfile.mkdtemp = _mkdtemp
    atexit.register(cleanup)
