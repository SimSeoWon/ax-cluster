"""`#392` ② — 「이 work 만」 지휘자 변경 표면 (`conductor.set_work_worker_mode` · MCP 도구 · 잠금 판정).

[DOC] 대상: `work/conductor.set_work_worker_mode` · `work/autodispatch.dispatch_locked` ·
      `projects/mcp_server.set_worker_mode_tool(work_id=)`. 큐는 주입한 api 대역, 잠금 디렉토리는
      임시 경로(`autodispatch.LOCK_DIR` 를 바꿔 끼우고 되돌린다), 준비 검사는 주입 — 실 SSH·실 큐 금지.
      출력 형식은 저장소 관례 `통과 N · 실패 M` + rc.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.work import autodispatch as AD                             # noqa: E402
from master.work import conductor as WC                                # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {name}")
    else:
        FAIL += 1
        print(f"  [중요] 실패: {name}" + (f" — {got}" if got else ""))


import fcntl
import io
import json
import os
import tempfile
from contextlib import redirect_stderr
from unittest.mock import patch
from master.projects import mcp_server as MS


with tempfile.TemporaryDirectory() as directory, patch.object(AD, "LOCK_DIR", Path(directory)):
    lock_path = Path(directory) / "w.lock"
    check("잠금 없음", AD.dispatch_locked("w") is False)
    check("판정이 파일을 만들지 않음", not lock_path.exists())
    lock_path.touch()
    check("빈 잠금 파일", AD.dispatch_locked("w") is False)
    fd = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check("다른 fd가 보유한 잠금", AD.dispatch_locked("w") is True)
        other = os.open(lock_path, os.O_RDWR)
        try:
            try:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                check("판정 뒤 기존 잠금 유지", True)
            else:
                check("판정 뒤 기존 잠금 유지", False)
                fcntl.flock(other, fcntl.LOCK_UN)
        finally:
            os.close(other)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    check("해제 뒤 잠금 없음", AD.dispatch_locked("w") is False)
    with patch.object(AD.os, "open", side_effect=OSError("denied")):
        check("열기 실패는 거절", AD.dispatch_locked("w") is True)


def _api_stub(calls, work=None, result=None):
    def call(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return {"work": work} if work is not None else {}
        return result if result is not None else {"ok": True}
    return call


work = {"worker_mode": "codex", "project": "AXCluster"}
calls = []
stderr = io.StringIO()
with redirect_stderr(stderr):
    got = WC.set_work_worker_mode("w", "claude", "복구", "tester",
                                  api=_api_stub(calls, work), readiness={"ok": True},
                                  locked=lambda wid: False)
check("work 모드 변경 반환", got == {"ok": True, "work_id": "w", "previous": "codex",
      "mode": "claude", "applies": "next_dispatch", "readiness": {"ok": True}}, got)
check("큐 경로와 PATCH 본문", calls == [
    ("GET", "/api/v1/works/w", None),
    ("PATCH", "/api/v1/works/w", {"project": "AXCluster", "worker_mode": "claude"})], calls)
check("성공 로그", "[work-mode] w codex→claude" in stderr.getvalue()
      and "다음 파견부터" in stderr.getvalue())

for name, overrides, missing, result, expected, patch_expected in [
    ("파견 중", {"locked": lambda wid: True}, False, None, "파견", False),
    ("빈 사유", {"why": " "}, False, None, "사유", False),
    ("모르는 모드", {"selected": "unknown"}, False, None, "모르는", False),
    ("빈 work_id", {"work_id": " "}, False, None, "work_id", False),
    ("준비 실패", {"readiness": {"ok": False, "reason": "not_ready"}}, False, None, "not_ready", False),
    ("work 없음", {}, True, None, "work", False),
    ("큐 변경 거절", {}, False, {"ok": False, "reason": "terminal_work"}, "terminal_work", True),
    ("큐 error 전달", {}, False, {"ok": False, "error": "denied"}, "denied", True),
    ("work_id 타입", {"work_id": 1}, False, None, "문자열", False),
    ("모드 타입", {"selected": 1}, False, None, "문자열", False),
    ("기록자 타입", {"by": 1}, False, None, "문자열", False),
]:
    calls = []
    kwargs = {"work_id": "w", "selected": "claude", "why": "복구", "by": "tester",
              "api": _api_stub(calls, None if missing else work, result),
              "readiness": {"ok": True}, "locked": lambda wid: False}
    kwargs.update(overrides)
    try:
        WC.set_work_worker_mode(**kwargs)
    except ValueError as exc:
        check(name, expected in str(exc), str(exc))
    else:
        check(name, False, "ValueError 없음")
    check(name + " PATCH 여부", any(c[0] == "PATCH" for c in calls) == patch_expected, calls)

with patch.object(WC, "worker_mode_readiness", return_value={"ok": True}) as ready:
    with redirect_stderr(io.StringIO()):
        WC.set_work_worker_mode("w", "claude", "복구", api=_api_stub([], work),
                                locked=lambda wid: False)
    check("work 프로젝트 준비 검사", ready.call_args.args == ("claude", "AXCluster"))

with patch.object(WC, "set_work_worker_mode", return_value={"ok": True}) as local, \
        patch.object(WC, "set_worker", return_value={"ok": True}) as global_mode:
    check("MCP work 반환", json.loads(MS.set_worker_mode_tool("claude", "복구", "tester", " w "))["ok"])
    check("MCP work 분기", local.call_args.args == ("w", "claude", "복구", "tester")
          and not global_mode.called)
    MS.set_worker_mode_tool("codex", "기본", "tester")
    check("MCP 전역 분기", global_mode.call_args.args == ("codex",)
          and global_mode.call_args.kwargs == {"why": "기본", "by": "tester"}
          and local.call_count == 1)
with patch.object(WC, "set_work_worker_mode", side_effect=ValueError("terminal_work")):
    got = json.loads(MS.set_worker_mode_tool("claude", "복구", work_id="w"))
    check("MCP ValueError JSON", got.get("ok") is False and got.get("reason") == "terminal_work"
          and got.get("modes") == ["lane", "claude", "codex"], got)

print()
print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
