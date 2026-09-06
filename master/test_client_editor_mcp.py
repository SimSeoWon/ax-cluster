"""요청자 에디터(Unreal MCP) 접근 판정 (`#374`) — 훅 `editor_mcp.py`.

검증하는 것:

    ① 옵트인 게이트 — `.mcp.json` 에 `unreal-mcp` 가 없으면 **아무 말도 하지 않는다**
    ② 포트를 상수로 박지 않는다 — `.mcp.json` 의 url 이 정본이다
    ③ 🔴 판정표 6분기 — 특히 `stale`(포트 열림인데 이 세션은 못 붙음)
    ④ 세션 시작 스냅샷이 **그 세션 것만** 쓰인다 (남의 세션을 빌려 쓰면 조용히 틀린다)
    ⑤ 매 턴 같은 말을 하지 않는다 — 판정이 바뀐 턴에만 낸다
    ⑥ 🔴 **막지 않는다** — 어떤 분기도 예외를 던지지 않고, 캐시가 깨져도 고지는 산다
    ⑦ PowerShell `ToString('o')` 소수점 7자리 파싱

`python3 master/test_client_editor_mcp.py`  (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

# [중요] **배달 표면에 `__pycache__` 를 만들지 않는다** — `bundle.workshop_files` 가
#    `hooks/` 를 rglob 로 쓸어 담아서, 남기면 `.pyc` 가 요청자 기계로 배달된다
#    (실측 2026-09-06: `test_client_bundle` 이 그 바이트를 읽다 UnicodeDecodeError 로 죽었다).
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "client" / "workshop" / "hooks"))

import editor_mcp as EM                                                        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, got: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


class Listener:
    """진짜 소켓을 연다 — 「포트 열림」은 흉내가 아니라 실물로 잰다."""

    def __init__(self, respond: bytes | None = None, port: int = 0):
        self.respond = respond
        self.stopped = False
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        # [중요] accept 에 블록된 스레드가 있으면 `close()` 가 실제로 닫지 않는다 —
        #    실측 2026-09-06: 5회 중 2회 「에디터를 껐다」가 안 잡혔다(포트가 계속 열려 보였다).
        self.sock.settimeout(0.2)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.stopped:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                if self.respond is None:
                    continue
                try:
                    conn.recv(65536)
                    conn.sendall(self.respond)
                except OSError:
                    pass

    def close(self):
        self.stopped = True
        self.thread.join(timeout=1.0)      # 스레드가 나간 뒤에 닫는다
        self.sock.close()


def _proj(tmp: Path, port: int | None) -> Path:
    """`.mcp.json` 을 갖춘 체크아웃 흉내."""
    servers = {"ax-client": {"command": "py"}}
    if port is not None:
        servers["unreal-mcp"] = {"type": "http", "url": f"http://127.0.0.1:{port}/mcp"}
    (tmp / ".mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return tmp


def _payload(cwd: Path, event: str, sid: str = "s1") -> dict:
    return {"cwd": str(cwd), "hook_event_name": event, "session_id": sid,
            "transcript_path": str(cwd / "transcript.jsonl")}


# ── ① 옵트인 ────────────────────────────────────────────────────────────
def test_optin_gate():
    print("① 옵트인 게이트")
    with tempfile.TemporaryDirectory() as d:
        cwd = _proj(Path(d), None)
        check("[중요] `unreal-mcp` 항목이 없으면 endpoint 가 None", EM.endpoint(cwd) is None)
        check("[중요] 그 프로젝트에서는 한 줄도 내지 않는다",
              EM.notice(_payload(cwd, "SessionStart")) is None)
    with tempfile.TemporaryDirectory() as d:
        cwd = Path(d)
        check("`.mcp.json` 자체가 없어도 조용하다", EM.endpoint(cwd) is None)


# ── ② 포트는 파일에서 온다 ──────────────────────────────────────────────
def test_port_comes_from_file():
    print("② 포트를 상수로 박지 않는다")
    with tempfile.TemporaryDirectory() as d:
        cwd = _proj(Path(d), 8123)
        check("url 의 포트를 그대로 읽는다", EM.endpoint(cwd) == ("127.0.0.1", 8123, "/mcp"),
              str(EM.endpoint(cwd)))
        (cwd / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"unreal-mcp": {"url": "http://127.0.0.1/mcp"}}}),
            encoding="utf-8")
        check("포트 생략이면 스킴 기본값", EM.endpoint(cwd) == ("127.0.0.1", 80, "/mcp"),
              str(EM.endpoint(cwd)))


# ── ③ 판정표 ────────────────────────────────────────────────────────────
def test_verdict_table():
    print("③ 판정 6분기")
    check("포트 닫힘 → off", EM.verdict(False, False) == "off")
    check("살아 있고 세션 시작에도 → ok", EM.verdict(True, True) == "ok")
    check("🔴 살아 있는데 세션 시작엔 아니었다 → stale", EM.verdict(True, False) == "stale")
    check("세션 시작엔 있었는데 지금 닫힘 → gone", EM.verdict(False, True) == "gone")
    check("MCP 응답이 아니다 → not_mcp", EM.verdict(None, True) == "not_mcp")
    check("모르면 단정하지 않는다 → unknown", EM.verdict(True, None) == "unknown")
    # [중요] 처방이 바뀌었다 — 세션 재시작이 아니라 `/mcp reconnect` 가 먼저다 (2026-09-06)
    check("stale 문구가 **재연결 명령**을 말한다", EM.RECONNECT in EM.line("stale", "h", 1))
    check("세션 재시작은 **차선**으로만 나온다", "그래도 도구가 안 보이면" in EM.line("stale", "h", 1))
    check("gone 문구가 리빌드 흐름을 말한다 — 켜는 것만으로는 안 붙는다",
          EM.RECONNECT in EM.line("gone", "h", 1) and "에디터만 켜면 붙지 않는다" in EM.line("gone", "h", 1))
    check("off 문구가 **임의 기동 금지**를 말한다", "임의로 켜지 않는다" in EM.line("off", "h", 1))


# ── ④⑤ 스냅샷과 소음 ───────────────────────────────────────────────────
def test_snapshot_and_noise():
    print("④⑤ 스냅샷 · 매 턴 반복 금지")
    lis = Listener(respond=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                           b'Content-Length: 29\r\n\r\n{"jsonrpc":"2.0","result":{}}')
    try:
        with tempfile.TemporaryDirectory() as d:
            cwd = _proj(Path(d), lis.port)
            first = EM.notice(_payload(cwd, "SessionStart"))
            check("세션 시작에 한 줄 — 붙음", first is not None and "붙음" in first, str(first))
            snap = EM.read_snapshot(cwd, "s1")
            check("스냅샷에 `at_start=True` 가 적힌다", bool(snap and snap["at_start"]), str(snap))
            check("[중요] 다음 턴엔 침묵한다 (판정이 그대로다)",
                  EM.notice(_payload(cwd, "UserPromptSubmit")) is None)

            lis.close()                                    # 에디터를 끈 것과 같다
            time.sleep(0.05)
            gone = EM.notice(_payload(cwd, "UserPromptSubmit"))
            check("🔴 상태가 바뀐 턴에는 말한다 — gone",
                  gone is not None and "꺼졌다" in gone, str(gone))
            check("그 다음 턴은 다시 침묵",
                  EM.notice(_payload(cwd, "UserPromptSubmit")) is None)

            check("[중요] 남의 세션 스냅샷을 빌려 쓰지 않는다",
                  EM.read_snapshot(cwd, "다른세션") is None)
    finally:
        lis.close()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_stale_is_the_trap():
    print("③ 🔴 실물 — 세션 시작 뒤에 에디터가 뜬 경우 (어제 그 사고)")
    port = _free_port()
    with tempfile.TemporaryDirectory() as d:
        cwd = _proj(Path(d), port)
        start = EM.notice(_payload(cwd, "SessionStart"))    # 그때는 꺼져 있었다
        check("세션 시작 고지는 꺼짐", start is not None and "꺼짐" in start, str(start))

        # 사람이 에디터를 켰다 — **세션 시작 뒤에**
        lis = Listener(respond=b'HTTP/1.1 200 OK\r\n\r\n{"jsonrpc":"2.0"}', port=port)
        try:
            got = EM.notice(_payload(cwd, "UserPromptSubmit"))
            check("🔴 이 세션은 못 붙었다고 말한다",
                  got is not None and "이 세션은 못 붙었다" in got, str(got))
            check("🔴 그리고 **재연결 명령**을 준다 (세션 재시작은 차선)",
                  got is not None and EM.RECONNECT in got, str(got))
        finally:
            lis.close()


# ── ⑥ 막지 않는다 ──────────────────────────────────────────────────────
def test_never_blocks():
    print("⑥ 어떤 경우에도 세션을 막지 않는다")
    with tempfile.TemporaryDirectory() as d:
        cwd = _proj(Path(d), 1)                            # 확실히 닫힌 포트
        out = EM.notice(_payload(cwd, "SessionStart"))
        check("포트가 닫혀도 예외 없이 한 줄", out is not None and "꺼짐" in out, str(out))
        (cwd / ".ax").mkdir(exist_ok=True)
        (cwd / ".ax" / "editor_mcp.json").write_text("{깨진 json", encoding="utf-8")
        check("[중요] 캐시가 깨져도 고지는 산다",
              EM.notice(_payload(cwd, "UserPromptSubmit")) is not None)
        (cwd / ".mcp.json").write_text("{깨진", encoding="utf-8")
        check("`.mcp.json` 이 깨졌으면 조용하다 (남의 파일을 판정하지 않는다)",
              EM.notice(_payload(cwd, "SessionStart")) is None)


# ── ⑦ 폴백 파싱 ────────────────────────────────────────────────────────
def test_ps_time_parsing():
    print("⑦ PowerShell 시각 파싱")
    from datetime import datetime, timezone
    want = datetime(2026, 9, 5, 14, 39, tzinfo=timezone.utc).timestamp()
    got = EM.parse_ps_time("2026-09-05T14:39:00.1234567Z")
    check("소수점 7자리를 읽는다", got is not None and abs(got - want) < 1, f"{got} vs {want}")
    check("빈 출력은 None (에디터가 없다)", EM.parse_ps_time("") is None)
    check("쓰레기는 None", EM.parse_ps_time("Get-Process : ...") is None)


def main() -> int:
    for fn in (test_optin_gate, test_port_comes_from_file, test_verdict_table,
               test_snapshot_and_noise, test_stale_is_the_trap, test_never_blocks,
               test_ps_time_parsing):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_editor_mcp: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
