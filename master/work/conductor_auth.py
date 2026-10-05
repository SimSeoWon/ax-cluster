"""워커 홈에 Claude 인증 상태를 24시간 보관한다. 자격 정보는 읽거나 저장하지 않는다."""
from __future__ import annotations

import json
import math
import ntpath
import shlex
import threading
import time

TTL = 24 * 60 * 60
CACHE_REL = ".cache/ax-dispatch/claude-auth.json"
AUTH_FAILED = "Claude 인증 실패: 워커에서 claude auth login 후 강제 재검사 필요"
REASONS = {
    "": "",
    "auth": AUTH_FAILED,
    "exit": "Claude 인증 상태 조회 명령 실패: 워커 CLI와 인증 상태 확인 필요",
    "json": "Claude 인증 상태 조회 응답이 올바른 JSON이 아니다",
    "probe": "Claude 인증 상태 조회 실패: 연결 또는 시간 제한 확인 필요",
}
_locks = {}
_guard = threading.Lock()
_revoked = set()


def _key(facts):
    return facts.host, facts.user, facts.home


def _lock(facts):
    with _guard:
        return _locks.setdefault(_key(facts), threading.Lock())


def cache_path(facts):
    return (ntpath.join(facts.home, CACHE_REL.replace("/", "\\")) if facts.windows
            else f"{facts.home}/{CACHE_REL}")


def _result(facts, stamp, ok, code, *, cached=False):
    return {"schema": 1, "kind": "claude", "host": facts.host, "user": facts.user,
            "home": facts.home, "checked_at": stamp, "ok": ok,
            "failure_type": code, "reason": REASONS[code], "cached": cached}


def _load(raw, facts, stamp):
    try:
        record = json.loads(raw)
        at = record.get("checked_at")
        code = record.get("failure_type")
        if (record.get("schema") != 1 or record.get("kind") != "claude" or
                (record.get("host"), record.get("user"), record.get("home")) != _key(facts) or
                type(record.get("ok")) is not bool or type(at) not in (int, float) or
                not math.isfinite(at) or not 0 <= stamp - at < TTL or
                code not in REASONS or record["ok"] != (code == "")):
            return None
        return _result(facts, at, record["ok"], code, cached=True)
    except (ValueError, AttributeError, TypeError):
        return None


def _save(facts, result, write):
    try:
        # Persist only normalized fields; never CLI stdout, exception text, mail or token.
        record = {k: v for k, v in result.items() if k != "cached"}
        write(facts, CACHE_REL, json.dumps(record, ensure_ascii=False) + "\n", base="home")
        _revoked.discard(_key(facts))
        return result
    except Exception:
        _revoked.add(_key(facts))
        return {**result, "ok": False, "failure_type": "storage",
                "reason": "Claude 인증 검사 기록 저장 실패: 워커 연결과 홈 쓰기 권한 확인 필요"}


def check_claude_auth(facts, *, reader=None, writer=None, shell_probe=None,
                      now=None, force=False):
    """이전 검사 후 24시간 미만이면 성공/실패를 재사용한다. force는 재로그인 후 재검사다."""
    from ..client import bundle
    read = reader or bundle._remote_read
    write = writer or bundle._remote_write
    shell = shell_probe or bundle._ssh
    with _lock(facts):
        stamp = time.time() if now is None else now() if callable(now) else now
        if not facts.home or not facts.path:
            return {"ok": False, "checked_at": stamp, "cached": False,
                    "failure_type": "probe", "reason": "Claude 인증 검사에 워커 홈과 체크아웃 경로가 필요하다"}
        if not force and _key(facts) not in _revoked:
            try:
                cached = _load(read(facts, cache_path(facts)), facts, stamp)
            except Exception:
                return {"ok": False, "checked_at": stamp, "cached": False,
                        "failure_type": "storage", "reason": "Claude 인증 검사 기록 읽기 실패: 워커 연결 확인 필요"}
            if cached is not None:
                return cached
        if facts.windows:
            if any(c in facts.path for c in '\"&|<>^%\r\n'):
                return {"ok": False, "checked_at": stamp, "cached": False,
                        "failure_type": "probe", "reason": "Claude 인증 검사 체크아웃 경로가 안전하지 않다"}
            command = f'cd /d "{facts.path}" && claude auth status 2>&1'
        else:
            command = f"cd {shlex.quote(facts.path)} && claude auth status 2>&1"
        try:
            rc, out = shell(facts.host, facts.user, command, timeout=30)
            try:
                data = json.loads(out)
            except (ValueError, TypeError):
                data = None
            if rc == 0 and isinstance(data, dict) and data.get("loggedIn") is True:
                code = ""
            elif isinstance(data, dict) and data.get("loggedIn") is False:
                code = "auth"
            elif rc != 0:
                code = "exit"
            else:
                code = "json"
        except Exception:
            code = "probe"
        return _save(facts, _result(facts, stamp, code == "", code), write)


def invalidate_claude_auth(facts, *, writer=None, now=None):
    """실행 중 인증 실패를 실패 기록으로 바꾼다. 원문 오류는 받지 않는다."""
    from ..client import bundle
    with _lock(facts):
        stamp = time.time() if now is None else now() if callable(now) else now
        _revoked.add(_key(facts))
        return _save(facts, _result(facts, stamp, False, "auth"), writer or bundle._remote_write)
