"""요청자 에디터(Unreal MCP) 접근 판정 (`#374`) — 훅 `editor_mcp.py`.

검증하는 것:

    ① 옵트인 게이트 — `.mcp.json` 에 `unreal-mcp` 가 없으면 **아무 말도 하지 않는다**
    ② 포트를 상수로 박지 않는다 — `.mcp.json` 의 url 이 정본이다
    ③ 🔴 판정표 6분기 — 특히 `stale`(포트 열림인데 이 세션은 못 붙음)
    ④ 세션 시작 스냅샷이 **그 세션 것만** 쓰인다 (남의 세션을 빌려 쓰면 조용히 틀린다)
    ⑤ 매 턴 같은 말을 하지 않는다 — 판정이 바뀐 턴에만 낸다
    ⑥ 🔴 **막지 않는다** — 어떤 분기도 예외를 던지지 않고, 캐시가 깨져도 고지는 산다
    ⑦ PowerShell `ToString('o')` 소수점 7자리 파싱
    ⑧ 🔴 **리빌드 경로** — 붙어 있던 연결은 껐다 켜도 **스스로 회복한다**(실측 75초)
    ⑨ 실증 로그 — **조용한 세션 시작도 남는다**(그게 「훅이 돌았다」의 증거다) · 바뀐 턴만 · 상한

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
    check("문구는 **사람에게 요청**하는 형태다 (슬래시 명령은 세션이 못 친다)",
          "요청한다" in EM.line("stale", "h", 1) and "요청" in EM.line("off", "h", 1))
    check("stale 문구가 **재연결 명령**을 말한다", EM.RECONNECT in EM.line("stale", "h", 1))
    check("세션 재시작은 **차선**으로만 나온다", "그래도 도구가 안 보이면" in EM.line("stale", "h", 1))
    # 🔴 실측이 뒤집은 자리 — 붙어 있던 연결은 껐다 켜면 스스로 회복한다(75초 중단에도)
    check("🔴 gone 은 **재연결을 요구하지 않는다** — 다시 켜기만 하면 된다",
          EM.RECONNECT not in EM.line("gone", "h", 1)
          and "다시 켜기만 하면 된다" in EM.line("gone", "h", 1))
    check("stale 만이 재연결이 필요한 경우다 (세션 시작에 서버가 없었다)",
          EM.RECONNECT in EM.line("stale", "h", 1) and "몇 초 만에 포기" in EM.line("stale", "h", 1))
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
            # [중요] 정상은 조용하다 (사용자 결정 2026-09-06) — 그래도 스냅샷은 남아야 한다
            check("🔴 붙어 있으면 **아무 말도 하지 않는다**", first is None, str(first))
            snap = EM.read_snapshot(cwd, "s1")
            check("스냅샷에 `at_start=True` 가 적힌다", bool(snap and snap["at_start"]), str(snap))
            check("[중요] 다음 턴엔 침묵한다 (판정이 그대로다)",
                  EM.notice(_payload(cwd, "UserPromptSubmit")) is None)

            lis.close()                                    # 에디터를 끈 것과 같다
            time.sleep(0.05)
            gone = EM.notice(_payload(cwd, "UserPromptSubmit"))
            check("🔴 상태가 바뀐 턴에는 말한다 — gone",
                  gone is not None and "꺼졌다" in gone, str(gone))
            # [중요] 다음 턴의 판정은 `off` 지만 사람에게는 **같은 사실**이다 — 부류로 묶는다
            check("그 다음 턴은 다시 침묵 (gone 과 off 는 같은 부류)",
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


# ── ⑧ 리빌드 경로 ──────────────────────────────────────────────────────
def test_rebuild_cycle_recovers_by_itself():
    """🔴 리빌드는 **사람이 할 일이 없다** — 붙어 있던 연결은 스스로 회복한다.

    실측 2026-09-06 (가짜 MCP 서버, `claude` 2.1.263):

        세션 시작에 붙어 있었다  3초 중단 ✅ · **75초 중단 ✅** (재연결 명령 없이 새 프로세스에)
        세션 시작에 없었다      2초 ✅ · 10 · 20 · 55 · 170초 ❌ 도구없음

    [주의] 한때 이 테스트는 **반대**를 요구했다 — 「다시 켜도 안 붙는다」고 단정하고
    `gone` 뒤에 `at_start` 를 내렸다(`4dfd75b`). 재고 나서 되돌렸다.
    """
    print("⑧ 🔴 리빌드 — 껐다 켜면 스스로 회복한다 (사람이 할 일 없음)")
    port = _free_port()
    body = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 29\r\n\r\n{"jsonrpc":"2.0","result":{}}'
    with tempfile.TemporaryDirectory() as d:
        cwd = _proj(Path(d), port)
        lis = Listener(respond=body, port=port)
        try:
            check("세션 시작엔 붙어 있었다 (조용하다)",
                  EM.notice(_payload(cwd, "SessionStart")) is None)
        finally:
            lis.close()                                    # ← 빌드하려고 에디터를 닫았다
        gone = EM.notice(_payload(cwd, "UserPromptSubmit"))
        check("꺼진 것은 말한다 — 지금은 호출이 실패하니까",
              gone is not None and "꺼졌다" in gone, str(gone))
        check("🔴 다만 **재연결을 요구하지 않는다** (다시 켜기만 하면 된다)",
              gone is not None and EM.RECONNECT not in gone, str(gone))

        lis2 = Listener(respond=body, port=port)           # ← 빌드 끝, 다시 켰다
        try:
            back = EM.notice(_payload(cwd, "UserPromptSubmit"))
            check("🔴 다시 켜면 **붙은 것으로 본다** (못 붙었다고 하지 않는다)",
                  back is None or "못 붙었다" not in back, str(back))
            check("🔴 복구를 **말한다** — 직전에 「호출이 실패한다」고 알렸으니까",
                  back is not None and "다시 붙었다" in back, str(back))
            check("사람이 한 일이 없다는 것까지 적는다",
                  back is not None and "사람이 한 일은 없다" in back, str(back))
            check("그 다음 턴은 침묵", EM.notice(_payload(cwd, "UserPromptSubmit")) is None)
        finally:
            lis2.close()


# ── ⑨ 실증 로그 ────────────────────────────────────────────────────────
def _log_rows(cwd: Path):
    f = cwd.joinpath(*EM.LOG_REL)
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if f.is_file() else []


def test_log_makes_the_live_run_checkable():
    """스냅샷은 **최신 상태 한 건**이라 전이가 안 남는다 — 실증은 이력이 있어야 한다."""
    print("⑨ 실증 로그")
    port = _free_port()
    body = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 29\r\n\r\n{"jsonrpc":"2.0","result":{}}'
    with tempfile.TemporaryDirectory() as d:
        cwd = _proj(Path(d), port)
        lis = Listener(respond=body, port=port)
        try:
            check("붙어 있으면 세션 시작이 조용하다",
                  EM.notice(_payload(cwd, "SessionStart")) is None)
            rows = _log_rows(cwd)
            check("🔴 [중요] **조용해도 로그에는 남는다** — 그게 「훅이 돌았다」의 증거다",
                  len(rows) == 1 and rows[0]["code"] == "ok" and rows[0]["spoke"] is False,
                  str(rows))
            check("어디를 쟀는지 남는다", rows[0]["where"].endswith(str(port)), str(rows[0]))
            EM.notice(_payload(cwd, "UserPromptSubmit"))
            check("판정이 그대로인 턴은 **안 남는다** (매 턴 적으면 그 자체가 소음)",
                  len(_log_rows(cwd)) == 1, str(_log_rows(cwd)))
        finally:
            lis.close()
        EM.notice(_payload(cwd, "UserPromptSubmit"))          # 에디터를 껐다
        rows = _log_rows(cwd)
        check("바뀐 턴은 남고 **직전 부류**도 함께 남는다",
              len(rows) == 2 and rows[1]["code"] == "gone" and rows[1]["prev"] == "up", str(rows))

        for _ in range(EM.LOG_MAX + 5):                        # 상한 — 사람 기계를 키우지 않는다
            EM.log_event(cwd, {"event": "x", "session": "s", "code": "off", "spoke": False})
        check(f"최근 {EM.LOG_MAX}줄만 남는다", len(_log_rows(cwd)) == EM.LOG_MAX,
              str(len(_log_rows(cwd))))


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


# ── ⑩ 훅 배치에서 하위 폴더 세션 (`#901`) ─────────────────────────────
def test_subfolder_session_via_hook_placement():
    """🔴 위 검사들은 `notice()` 에 `cwd` 를 직접 넣는다 — **훅 배치 경로는 안 잰다.**

    실제 훅은 `<체크아웃>/.claude/hooks/pending_works.py` 이고 루트는 그 자리가 안다
    (`hook_paths.checkout_root`). 세션이 하위 폴더에서 열리면 payload `cwd` 는 루트가 아니다 —
    그 값을 그대로 넘기면 `.mcp.json` 을 못 찾아 **옵트인 꺼짐으로 침묵**했다
    (드라이런 재현 2026-11-07, `#899`). 그래서 이 검사는 진짜 배치에서 서브프로세스로 돈다.
    """
    import shutil
    import subprocess
    print("⑩ 훅 배치 — 하위 폴더에서 연 세션도 에디터를 판정한다 (#901)")
    hooks = Path(__file__).resolve().parent / "client" / "workshop" / "hooks"
    with tempfile.TemporaryDirectory() as d:
        root = _proj(Path(d), 1)                          # 확실히 닫힌 포트 → 「꺼짐」
        dst = root / ".claude" / "hooks"
        dst.mkdir(parents=True)
        for name in ("pending_works.py", "editor_mcp.py", "hook_paths.py"):
            shutil.copy2(hooks / name, dst / name)
        sub = root / "Source" / "Sub"
        sub.mkdir(parents=True)
        for label, cwd in (("루트", root), ("하위 폴더", sub)):
            payload = json.dumps(_payload(cwd, "SessionStart", sid=f"s-{label}"))
            p = subprocess.run([sys.executable, "-B", str(dst / "pending_works.py")],
                               input=payload, capture_output=True, text=True,
                               encoding="utf-8", cwd=str(cwd), timeout=60)
            check(f"{label} 세션 — 「꺼짐」을 고지한다", "[에디터 MCP] 꺼짐" in p.stdout,
                  p.stdout[-300:] + p.stderr[-300:])
        rows = _log_rows(root)
        check("🔴 두 세션 모두 **루트의** 실증 로그에 남는다",
              sorted(r["session"] for r in rows) == ["s-루트", "s-하위 폴더"[:8]], str(rows))
        check("하위 폴더에 `.ax/` 를 만들지 않는다 (스냅샷·로그는 루트 것이다)",
              not (sub / ".ax").exists())


def main() -> int:
    for fn in (test_optin_gate, test_port_comes_from_file, test_verdict_table,
               test_snapshot_and_noise, test_stale_is_the_trap,
               test_rebuild_cycle_recovers_by_itself, test_log_makes_the_live_run_checkable,
               test_never_blocks,
               test_ps_time_parsing,
               test_subfolder_session_via_hook_placement):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_editor_mcp: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
