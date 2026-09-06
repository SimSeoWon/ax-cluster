"""요청자 에디터(Unreal MCP) 접근 가능 여부 — 세션 시작에 **사실만** 낸다 (`#374`).

## 왜 필요한가 (실측 2026-09-05)

`.33` 세션이 한참 작업한 뒤에야 *"세션 시작할 때부터 unreal-mcp 연결이 실패한 상태였다"* 를
알았다. 아무도 안 알려 줬기 때문이다. 원전에도 이 점검은 **사람이 읽는 런북**으로만 있었다
(`docs/runbook.md` §12) — 그 절차를 관측값으로 바꾼 것이지 새 계층이 아니다.

## 🔴 함정 — 「포트 열림」은 「이 세션이 붙었다」가 아니다

MCP 는 **세션 시작에 한 번만** 붙고 자동 재시도가 없다(원전 런북 §12-5 도 같은 말로 끝난다:
*"이후에도 도구가 안 보이면 Claude Code 세션 재시작"*). 그래서 판정은 둘을 **모두** 본다 —
지금 살아 있나, 그리고 **세션이 시작될 때** 살아 있었나.

[중요] 다만 처방은 원전보다 가볍다 — **세션을 다시 열 필요는 없고 `/mcp reconnect` 면 된다**
(아래 `RECONNECT`, 실측 2026-09-06). 리빌드마다 에디터를 닫아야 하므로 이 구분이 크다.

    off        포트 닫힘                         에디터가 안 떠 있다
    ok         지금 살아 있고 세션 시작에도 살아 있었다   붙었을 것이다
    stale      🔴 지금 살아 있는데 세션 시작엔 아니었다   이 세션은 못 붙었다 — `/mcp reconnect`
    gone       세션 시작엔 살아 있었는데 지금 닫혔다     도구는 목록에 남고 호출만 실패한다
    not_mcp    포트는 열렸는데 MCP 응답이 아니다        남이 그 포트를 잡고 있다
    unknown    열렸지만 세션 시작 기록이 없다          단정하지 않는다

## [중요] 「세션 시작에 살아 있었나」는 **우리가 그때 재서** 안다

이슈가 제안한 원안은 「에디터 프로세스 기동 시각 vs 세션 시작 시각」인데, 이 훅은 **세션 시작에
직접 돌므로** 그 시각을 추정할 필요가 없다 — 그때 재서 스냅샷에 적어 두면 된다. 프로세스 시각
비교는 **스냅샷이 없을 때만** 쓰는 폴백으로 남긴다(배달 직후처럼 세션 시작을 못 본 경우).

## [중요] 막지 않는다 · 자동으로 켜지 않는다

에디터가 필요 없는 작업이 대부분이다(2026-09-05 실증 3라운드 전부). 그래서 **고지만** 한다.
기동은 사람의 결정이고, 원격 기동은 설계하지 않는다 — `win-main-33.md`: *"Unreal MCP 의 수명은
에디터의 수명 → 대화형 세션이 소유한다. 원격 절차를 설계하지 마라 — 그런 것은 없다"*.

## [중요] 정상은 조용하다 — 위험한 것만 말한다 (사용자 결정 2026-09-06)

`붙음`(ok)이면 **아무 말도 하지 않는다.** 이 파일의 이웃(`pending_works.py`)이 이미 그 규약이고
(*"세션마다 「없음」을 찍는 것은 소음이다"*), 「붙음」에서만 그것을 어기고 있었다.
[주의] 조용해도 **스냅샷은 남긴다** — 뒤 턴의 판정 근거가 그것이다.

## [주의] 매 턴 같은 말을 하지 않는다

`pending_works.py` 는 `SessionStart` 와 `UserPromptSubmit` 양쪽에 등록돼 있다. 세션 시작에 한 번,
그 뒤로는 **판정이 바뀐 턴에만** 낸다(`#364` 의 교훈 — 닿아야 하지만 반복은 소음).

## 🔴 [중요] 리빌드가 이 기능의 기본 경로다

C++ 을 고치면 **에디터를 닫고 → 빌드하고 → 다시 켠다.** 그때 이 세션의 연결은 **죽고 돌아오지
않는다.** 그래서 `gone` 을 한 번 본 세션은 그 뒤로 `ok` 가 될 수 없다(스냅샷의 `at_start` 를
내린다) — 다시 켠 뒤의 정답은 `stale` 이고, 처방은 **사람에게 `/mcp reconnect` 를 요청**하는 것이다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

SERVER_NAME = "unreal-mcp"                 # `.mcp.json` 의 항목 이름 = 옵트인 스위치
SNAPSHOT_REL = (".ax", "editor_mcp.json")  # `.ax/` 는 커밋되지 않는다 (spec.GITIGNORE_BODY)
SNAPSHOT_MAX = 4                           # 한 체크아웃에 동시에 열린 세션 — 오래된 것부터 버린다
TCP_TIMEOUT = 0.6                          # 루프백이라 거절은 즉시다 — 매 턴 도는 값
MCP_TIMEOUT = 1.5                          # handshake 는 **세션 시작 1회**만
PS_TIMEOUT = 4.0

PREFIX = "[에디터 MCP]"

# [중요] **세션을 다시 열 필요는 없다** — `claude` 에 재연결 명령이 있다 (실측 2026-09-06,
#    2.1.263 바이너리 문자열: `/mcp reconnect <서버>` · `/mcp reconnect all` ·
#    *"isn't a recognized /mcp action. Try reconnect, enable, or disable"*).
#    [주의] 이것이 실제 운영을 가른다 — **C++ 을 고쳐 리빌드할 때마다 에디터를 닫으므로**
#    (사용자 지적 2026-09-06) 연결은 하루에도 여러 번 끊긴다. 그때마다 세션을 새로 여는 것은
#    맥락을 버리는 일이고, 재연결은 한 줄이다.
RECONNECT = "/mcp reconnect unreal-mcp"
# [중요] **그 명령은 사람이 친다** — 슬래시 명령은 세션이 실행할 수 없다. 그래서 문구는
#    전부 「사람에게 요청한다」로 쓴다(사용자 지시 2026-09-06: *"사람은 자리에 앉아있는거니까
#    대신 요청하면 될듯해 — 에디터를 켜달라거나 MCP를 다시 시작해달라거나"*).

# 원전 런북 §12-5 의 그 본문 — 포트를 잡은 것이 **정말 MCP 서버인지** 가른다
_INIT_BODY = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "ax-editor-probe", "version": "0"}},
}


# ── 관측 ────────────────────────────────────────────────────────────────
def endpoint(cwd: Path):
    """`.mcp.json` 의 `unreal-mcp` → `(host, port, path)`. 없으면 `None` = **기능이 꺼진 것**.

    [중요] 여기가 옵트인 게이트다 — 항목이 없는 프로젝트(비-UE5)에서는 **아무 말도 하지 않는다**.
    포트를 상수로 박지 않는 이유도 같다: 정본은 `claude` 가 실제로 읽는 그 파일이다.
    """
    try:
        data = json.loads((cwd / ".mcp.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ent = (data.get("mcpServers") or {}).get(SERVER_NAME)
    url = str((ent or {}).get("url") or "")
    if not url:
        return None
    u = urlsplit(url)
    if not u.hostname:
        return None
    port = u.port or (443 if u.scheme == "https" else 80)
    return (u.hostname, int(port), u.path or "/mcp")


def tcp_open(host: str, port: int, timeout: float = TCP_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def mcp_alive(host: str, port: int, path: str, timeout: float = MCP_TIMEOUT):
    """`initialize` 한 번. `True` = MCP 서버 · `None` = 열렸지만 MCP 응답이 아니다.

    [주의] **세션 시작에만 부른다** — handshake 마다 서버 쪽 세션이 생길 수 있어서, 매 턴
    두드리면 에디터에 찌꺼기를 쌓는다. 매 턴 판정은 TCP 열림만으로 충분하다.

    🔴 [중요] **본문을 읽지 않는다.** streamable-http 의 응답은 `text/event-stream` 일 수
    있고, 그때 `read()` 는 서버가 끊을 때까지 **블록한다** — 실측(2026-09-06, 테스트가 잡았다)
    으로 그 대기가 타임아웃이 되면 판정이 `not_mcp` 로 뒤집혔다. 상태줄과 Content-Type 이면
    「MCP 가 응답했다」는 판정에 충분하다.

    [중요] **모호하면 `True` 쪽으로 접는다.** 오탐의 값이 다르기 때문이다 —
    틀린 「붙음」은 도구 호출이 실패하며 그 자리에서 드러나지만, 틀린 「못 붙었다」는
    **사람에게 헛되이 세션 재시작을 시킨다.** 그래서 타임아웃·비HTTP 응답은 살아 있음으로 본다.
    """
    req = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=json.dumps(_INIT_BODY).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            ok = r.status == 200 and ("json" in ctype or "event-stream" in ctype)
    except urllib.error.HTTPError as e:
        # HTTP 로 **거절**했다 = 뭔가 다른 서버다 (405/404/400…)
        return None if e.code not in (200, 202) else True
    except Exception:                                       # noqa: BLE001
        return True                    # 타임아웃·리셋 — 단정하지 않는다 (위 [중요])
    return True if ok else None


def session_started(data: dict):
    """세션 시작 시각(epoch). 트랜스크립트 파일의 생성 시각이 그것이다 — 없으면 `None`."""
    tp = str(data.get("transcript_path") or "")
    if not tp:
        return None
    try:
        return Path(tp).stat().st_ctime
    except OSError:
        return None


def listener_started(port: int):
    """그 포트를 잡은 프로세스의 기동 시각(epoch). **윈도우 전용 폴백** — 없으면 `None`.

    [주의] 스냅샷이 없을 때만 부른다. `powershell` 기동은 수백 ms 라 매 턴 낼 값이 아니다.
    """
    if os.name != "nt":
        return None
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return None
    cmd = (f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
           f"-ErrorAction SilentlyContinue | Select-Object -First 1; "
           f"if ($c) {{ (Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue)"
           f".StartTime.ToUniversalTime().ToString('o') }}")
    try:
        out = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", cmd],
                             capture_output=True, text=True, timeout=PS_TIMEOUT).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_ps_time(out)


def parse_ps_time(out: str):
    """`ToString('o')` 출력 → epoch. [주의] 소수점 7자리는 `fromisoformat` 이 못 읽는다."""
    from datetime import datetime
    s = (out or "").strip().splitlines()[-1].strip() if (out or "").strip() else ""
    if not s:
        return None
    s = re.sub(r"\.(\d{6})\d+", r".\1", s).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


# ── 스냅샷 — 「세션 시작에 살아 있었나」를 그때 적어 둔다 ────────────────
def _snap_file(cwd: Path) -> Path:
    return cwd.joinpath(*SNAPSHOT_REL)


def read_snapshot(cwd: Path, session_id: str):
    """이 세션의 기록. **다른 세션의 것을 빌려 쓰지 않는다** — 그러면 조용히 틀린다."""
    if not session_id:
        return None
    try:
        data = json.loads(_snap_file(cwd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    got = (data.get("sessions") or {}).get(session_id)
    return got if isinstance(got, dict) else None


def write_snapshot(cwd: Path, session_id: str, entry: dict) -> None:
    """[주의] 실패해도 삼킨다 — 고지가 캐시 때문에 죽으면 본말이 뒤집힌다."""
    if not session_id:
        return
    path = _snap_file(cwd)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sessions = data.get("sessions")
        if not isinstance(sessions, dict):
            sessions = {}
    except (OSError, ValueError):
        sessions = {}
    sessions[session_id] = {**entry, "ts": time.time()}
    if len(sessions) > SNAPSHOT_MAX:                        # 오래된 세션부터 버린다
        for k, _ in sorted(sessions.items(), key=lambda kv: kv[1].get("ts") or 0)[:-SNAPSHOT_MAX]:
            sessions.pop(k, None)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sessions": sessions}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError:
        pass


# ── 판정 — 순수 함수 (`.venv` 없이 테스트된다) ──────────────────────────
def verdict(live, at_start) -> str:
    """`live` 지금(True/False/None=MCP 아님) · `at_start` 세션 시작에(True/False/None=모름)."""
    if live is None:
        return "not_mcp"
    if not live:
        return "gone" if at_start else "off"
    if at_start is None:
        return "unknown"
    return "ok" if at_start else "stale"


# [중요] **중복 판정은 「부류」로 한다** — `gone`(방금 꺼졌다)과 `off`(꺼져 있다)는 사람에게
#    같은 사실이다. 코드로 비교하면 에디터를 닫은 다음 턴에 **같은 말을 두 번** 하게 된다
#    (실측 2026-09-06: 테스트가 잡았다). 문구는 정확한 것을 내고, **말할지 말지는 부류로** 정한다.
CLASS = {"ok": "up", "off": "down", "gone": "down",
         "stale": "detached", "not_mcp": "not_mcp", "unknown": "unknown"}


def line(code: str, host: str, port: int) -> str:
    where = f"{host}:{port}"
    if code == "ok":
        return (f"{PREFIX} 붙음 — 에디터가 세션 시작 전부터 떠 있다 ({where}). "
                f"애셋·블루프린트 작업 가능.")
    if code == "off":
        return (f"{PREFIX} 꺼짐 — 에디터가 안 떠 있다 ({where}). 소스·빌드·로그 작업은 영향 "
                f"없다. 애셋·BP·입력 매핑을 건드려야 하면 **사람에게 「에디터를 켜 주세요」**라고 "
                f"요청하고(임의로 켜지 않는다), 켜진 뒤 **「`{RECONNECT}` 를 실행해 주세요」**까지 "
                f"함께 부탁한다.")
    if code == "stale":
        return (f"{PREFIX} 🔴 열렸지만 **이 세션은 못 붙었다** — 에디터가 세션 시작 뒤에 떴거나 "
                f"중간에 다시 떴다 "
                f"({where}). MCP 는 세션 시작에 한 번만 붙고 **자동 재시도가 없다**. "
                f"애셋·BP 작업이 필요하면 **사람에게 「`{RECONNECT}` 를 실행해 주세요」**라고 "
                f"요청한다 — 그래도 도구가 안 보이면 그때 세션을 다시 열어 달라고 부탁한다.")
    if code == "gone":
        return (f"{PREFIX} 에디터가 꺼졌다 — 세션 시작엔 떠 있었다 ({where}). `unreal-mcp` 도구는 "
                f"목록에 남아 있어도 **호출은 실패한다**. 리빌드로 다시 켠 뒤에는 사람에게 "
                f"**「`{RECONNECT}` 를 실행해 주세요」**라고 요청한다 — **에디터만 켜면 붙지 "
                f"않는다.**")
    if code == "not_mcp":
        return (f"{PREFIX} [주의] 포트는 열렸는데 MCP 응답이 아니다 ({where}) — 다른 프로세스가 "
                f"그 포트를 잡고 있을 수 있다. 원전 런북 §12 순서로 확인할 것.")
    return (f"{PREFIX} 열려 있다 ({where}) — 다만 **이 세션이 붙었는지는 모른다**(세션 시작 "
            f"기록이 없다). 애셋·BP 작업 전에 `mcp__unreal-mcp__*` 도구가 이 세션에 있는지 "
            f"확인하고, 없으면 사람에게 `{RECONNECT}` 실행을 요청한다.")


# ── 훅에서 부르는 자리 ──────────────────────────────────────────────────
def notice(data: dict):
    """훅 페이로드 → 낼 한 줄(없으면 `None`). 판정이 바뀌지 않은 턴에는 `None` 이다."""
    cwd = Path(str(data.get("cwd") or "."))
    ep = endpoint(cwd)
    if ep is None:
        return None                       # 옵트인 꺼짐 — 이 프로젝트엔 에디터 MCP 가 없다
    host, port, path = ep
    sid = str(data.get("session_id") or "")
    at_startup = str(data.get("hook_event_name") or "") == "SessionStart"

    live = tcp_open(host, port)
    if live and at_startup:
        live = mcp_alive(host, port, path)          # True | None

    if at_startup:
        # 지금이 곧 세션 시작이다 — 추정할 것이 없다
        code = verdict(live, live is True)
        write_snapshot(cwd, sid, {"at_start": live is True, "last": CLASS[code]})
        # [중요] **정상은 조용하다** (사용자 결정 2026-09-06). 이 파일의 원래 규약이 그것이고
        #    (`pending_works.py`: *"세션마다 「없음」을 찍는 것은 소음이다"*), 「붙음」에서만
        #    그 규약을 어기고 있었다. 위험한 넷만 말한다 — **스냅샷은 그대로 남긴다**(조용해도
        #    뒤 턴의 판정 근거는 있어야 한다).
        return None if code == "ok" else line(code, host, port)

    snap = read_snapshot(cwd, sid)
    if snap is not None:
        at_start = bool(snap.get("at_start"))
    elif live:
        # 폴백 — 세션 시작을 못 본 경우에만 프로세스 시각을 비교한다 (이슈 `#374` 원안)
        started, s0 = listener_started(port), session_started(data)
        at_start = (started < s0) if (started and s0) else None
    else:
        at_start = None

    code = verdict(live, at_start)
    if snap is not None and snap.get("last") == CLASS[code]:
        return None                       # 매 턴 같은 **부류**를 두 번 말하지 않는다

    # 🔴 [중요] **에디터가 한 번 꺼지면 이 세션의 연결은 죽는다** — 다시 켜도 안 돌아온다.
    #    그래서 `gone` 을 본 순간 `at_start` 를 내린다. 안 그러면 리빌드 흐름
    #    (`ok → gone → 다시 켬`)이 **다시 `ok`** 로 판정돼 **「붙음」이라고 거짓말한다.**
    #    그것이 이 기능이 가장 자주 만나는 경로다(사용자 지적 2026-09-06: *"코드 변경해서
    #    재빌드 할때 연결 끊어질꺼 아니야"*). 다시 켠 뒤의 정답은 `stale` — `/mcp reconnect`.
    at_start = False if code == "gone" else at_start
    write_snapshot(cwd, sid, {"at_start": at_start, "last": CLASS[code]})
    return line(code, host, port)


def main() -> int:
    """훅으로도, 사람이 부르는 점검으로도 돈다.

    stdin 에 훅 페이로드가 있으면 그 계약대로, 없으면 **지금 서버가 살아 있는지**만 낸다.
    [중요] 후자는 「이 세션이 붙었는지」를 말하지 못한다 — 그 판정은 세션 시작에만 성립한다.
    """
    payload = {}
    if not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            payload = {}
    if payload.get("hook_event_name"):
        out = notice(payload)
        if out:
            print(out)
        return 0

    cwd = Path(str(payload.get("cwd") or os.getcwd()))
    ep = endpoint(cwd)
    if ep is None:
        print(f"{PREFIX} `.mcp.json` 에 `{SERVER_NAME}` 항목이 없다 — 이 프로젝트는 "
              f"에디터 MCP 를 쓰지 않는다.")
        return 0
    host, port, path = ep
    live = mcp_alive(host, port, path) if tcp_open(host, port) else False
    print(line(verdict(live, None if live else False), host, port))
    print("  [중요] 이것은 **서버**의 상태다. 이 세션이 붙었는지는 세션 시작에 정해졌고, "
          "결정적 확인은 `mcp__unreal-mcp__*` 도구가 이 세션에 있는지다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
