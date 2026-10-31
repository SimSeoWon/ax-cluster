"""AX 원격 등록 — 상주 작업 데몬은 금지, 로그인 런처와 옛 등록 해제만 유지한다.

사용자 2026-10-31 (#860 · #861): 서버가 SSH로 작업을 총괄한다. 데몬 생성·기동·갱신
명령은 더 이상 만들지 않는다. AxConductor는 Windows 로그인 세션을 빌리는 별도 런처다.
옛 AxWorker 이름·cron 표식은 이미 배달된 등록을 찾아 제거하기 위한 계약으로 남긴다.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

TASK_NAME = "AxWorker"           # 🔴 개명 (`#405`) — 근거는 아래 「개명」 절
INTERVAL_MIN = 5                 # 감시자 주기. 잠금 싱글턴이 겹침을 흡수한다
DAEMON_REL = ".ax/lib/axmaster/work/worker_daemon.py"
RESTART_FILE = "worker_daemon.restart"   # 데몬의 같은 상수와 짝 (배달물은 마스터를 import 하지 않는다)


def types_for(facts) -> str:
    """이 기계가 집을 유형. [중요] **probe 실측(`ue5`)에서 나온다** — 표로 들지 않는다.

    🔴 [중요] **`code` 를 더는 신고하지 않는다** (`#404`, 2026-09-12). 데몬의 추론 경로는
    폐기된 `carry`/`manifest` 운송 규약 위에 있어서 들어냈고, 지금 추론 파견은 마스터
    push(`work/infer.py`)가 맡는다. 그런데 종전 값은 UE5 없는 기계에 `code` 를 신고했다 —
    그러면 데몬이 **마스터가 맡아야 할 태스크를 집어서 `unsupported-type` 으로 튕긴다.**
    실측으로 잡았다: `.43` 에 걸린 cron 이 `--types=code` 였다(2026-09-12 첫 실물 등록).

    [주의] 그래서 **UE5 가 없으면 집을 것이 없다** — 빈 문자열을 돌려주고, 호출자
    (`blocked_reason`)가 「지금 켜지 않는다」로 막는다. 조용히 헛도는 상주를 만들지 않는다.
    """
    return "build" if getattr(facts, "ue5", "") else ""


def task_name(project: str) -> str:
    """[중요] **프로젝트마다 다른 이름**이어야 한다 — 한 기계에 둘이 설치될 수 있으므로
    (`#250` 허용). `.2` 의 기존 등록은 `AxClaimer` 이고 그것이 ModularStage 몫이다.
    """
    return TASK_NAME if project == "ModularStage" else f"{TASK_NAME}_{project}"


def python_for(facts) -> str:
    """상주를 띄울 인터프리터. 윈도우는 **`pythonw.exe`** 다 — 콘솔 창을 띄우지 않는다."""
    return "pythonw" if facts.windows else "/usr/bin/python3"


# [중요] 윈도우 `pythonw` 는 **PATH 에 없다** (실측 2026-08-22: `.2` 에서 `where pythonw` 가
#    빈 값이고 실물은 `%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe` 였다).
#    기존 schtasks 등록도 절대경로를 쓴다. 그래서 **경로를 선언에 박지 않고 잰다** —
#    버전 디렉토리(`Python310`)가 들어가므로 박으면 다음 업그레이드에 조용히 깨진다.
# [중요] 윈도우 `pythonw` 는 **PATH 에 없다** (실측 2026-08-22: `.2` 에서 `where pythonw` 가
#    빈 값이고 실물은 `%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe` 였다).
#    기존 schtasks 등록도 절대경로를 쓴다. 그래서 **경로를 선언에 박지 않고 잰다** —
#    버전 디렉토리(`Python310`)가 들어가므로 박으면 다음 업그레이드에 조용히 깨진다.
# [주의] `for /f` 로 짜려다 인용이 세 겹(bash → ssh → cmd)이라 깨졌다. **후보를 나열해 존재만
#    확인**하는 편이 읽히고 안 깨진다 — 출력 줄에서 `pythonw.exe` 로 끝나는 것을 고른다.
PYTHONW_PROBE = (
    "where pythonw 2>nul"
    ' & for /d %D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do'
    ' @if exist "%D\pythonw.exe" echo %D\pythonw.exe'
)


def parse_python_probe(out: str) -> str:
    """프로브 출력에서 경로 한 줄. 못 찾으면 빈 문자열 — **추측하지 않는다.**"""
    for line in (out or "").splitlines():
        s = line.strip().strip('"')
        if s.lower().endswith("pythonw.exe"):
            return s
    return ""


def commands(project: str, facts, *, python_path: str = "") -> list:
    """폐기된 데몬 등록 API — 모든 OS·프로젝트에서 생성 명령을 내지 않는다."""
    return []


def ensure_commands(project: str, facts) -> list:
    """폐기된 데몬 기동 API — schtasks /run·nohup을 만들지 않는다."""
    return []


CONDUCTOR_TASK = "AxConductor"
CONDUCTOR_REL = ".ax/lib/axmaster/clientside/session1_conductor.py"


def conductor_task_name(project: str) -> str:
    return CONDUCTOR_TASK if project == "ModularStage" else f"{CONDUCTOR_TASK}_{project}"


def conductor_register_commands(project: str, facts, *, python_path: str = "") -> list:
    """세션 1 지휘자 런처를 `/IT` 작업으로 등록 (`#401`). **윈도우 전용.**

    🔴 [중요] **`/it` 가 이 등록의 전부다** — 그것이 프로세스를 세션 1 에 만들고, 거기서는
    codex 샌드박스 자식이 산다(실측 2026-09-12: 세션 0 `0xC0000142` / 세션 1 `exit_code 0`).
    [주의] 리눅스는 이 문제가 없다 — SSH 로 그냥 돌린다. 그래서 빈 목록을 돌려준다.
    [주의] `/sc once` 다 — 주기 실행이 아니라 **마스터가 `/run` 으로 부를 때만** 돈다.
    """
    if not facts.windows:
        return []
    py = python_path or python_for(facts)
    script = f'{facts.path}\\{CONDUCTOR_REL.replace("/", chr(92))}'
    run = f'\\"{py}\\" \\"{script}\\"'
    return [("conductor-register",
             f'schtasks /create /f /tn {conductor_task_name(project)} '
             f'/sc once /st 23:59 /it /rl LIMITED /tr "{run}"')]


def crash_dialog_commands(facts) -> list:
    """🔴 **크래시 대화상자를 끈다** (`#401`, 실측 2026-09-12). **Windows 전용.**

    세션 1 은 데스크톱이 있어서 크래시가 **모달 대화상자**로 뜬다 — 그러면 프로세스가
    **무한 대기**한다. 세션 0 에서는 데스크톱이 없어 조용히 죽던 것이 여기서는 매달린다.
    실물: `dotnet`(UBT) 둘이 CPU 0 으로 남아 **사람이 창을 닫아 줘야** 풀렸다.

    [중요] **세션 1 로 옮긴 것의 부작용이라 같이 배선한다** — 안 하면 새 워커에서 그대로
    재현된다(이 저장소가 「문서에만 있으면 재현되지 않는다」로 여러 번 겪은 부류다).
    [주의] `HKCU` 다 — 사용자 범위라 **관리자 권한이 필요 없고** 되돌리기 쉽다.
    되돌리려면 값을 0 으로 두거나 지운다.
    """
    if not facts.windows:
        return []
    return [("crash-dialog-off",
             'reg add "HKCU\\Software\\Microsoft\\Windows\\Windows Error Reporting" '
             '/v DontShowUI /t REG_DWORD /d 1 /f')]


def conductor_run_command(project: str, facts) -> str:
    """등록된 런처를 **지금 한 번** 돌린다. 윈도우 전용."""
    return f"schtasks /run /tn {conductor_task_name(project)}"


def cron_marker(facts) -> str:
    """`.43` 류의 crontab 에서 **우리 줄을 찾는 표식**. [중요] 등록과 해제가 같은 값을 써야
    한다 — 두 벌로 쓰면 해제가 남의 줄을 지우거나 우리 줄을 못 지운다."""
    return f"cd {facts.path} &&"


def registration_query_command(project: str, facts) -> str:
    """조회 성공·명시적 부재·조회 실패를 구분할 수 있는 관측 명령."""
    if facts.windows:
        name = task_name(project).replace("'", "''")
        return (
            'powershell -NoProfile -Command "$ErrorActionPreference=\'Stop\'; '
            "try { $found=@(Get-ScheduledTask -ErrorAction Stop | "
            f"Where-Object {{ $_.TaskName -eq '{name}' }}); "
            "if($found.Count -gt 0){'AX_RESIDENCY_PRESENT=1'}"
            "else{'AX_RESIDENCY_PRESENT=0'} } "
            "catch { Write-Output ('AX_RESIDENCY_ERROR='+$_.Exception.Message); exit 1 }\""
        )
    return "LC_ALL=C crontab -l 2>&1"


def registration_status(rc: int, out: str, facts) -> dict:
    """관측 불가를 부재로 접지 않는다. 존재는 옛 작업 이름/cron 표식으로만 판정."""
    text = (out or "").strip()
    if facts.windows:
        if rc == 0 and text in ("AX_RESIDENCY_PRESENT=0", "AX_RESIDENCY_PRESENT=1"):
            return {"known": True, "present": text.endswith("=1")}
    elif rc == 0:
        return {"known": True, "present": cron_marker(facts) in text}
    elif rc == 1 and text.lower().startswith("no crontab for "):
        return {"known": True, "present": False}
    return {"known": False, "present": None,
            "error": f"상주 등록 조회 실패 rc={rc}: {text[:160] or '(응답 없음)'}"}


def registration_present(rc: int, out: str, facts) -> bool:
    """호환용 존재 조회. 실패를 다루는 호출자는 registration_status를 사용한다."""
    return registration_status(rc, out, facts).get("present") is True


def unregister_commands(project: str, facts) -> list:
    """상주 **해제** 명령 `(라벨, 명령)` (`#311`).

    [중요] **ⓐ 결정의 짝이다** — 「상주는 마운트를 따른다」면 옮기는 일이 늘 둘이다: 새 것을
    켜고 **이전 것을 멈춘다**. 켜는 쪽만 코드에 있으면 멈추는 쪽은 매번 손으로 쓰이고, 그러면
    작업 이름·표식이 등록과 갈린다(실측 2026-08-25: 손으로 쓴 뒤 이 함수를 만들었다).
    [주의] crontab 은 **우리 줄만** 뺀다 — 통째로 다시 쓰면 `PATH=` 줄이 날아가고 claimer 가
    도구를 못 찾는다(`commands()` 의 같은 주의).
    """
    if facts.windows:
        return [("unregister", f"schtasks /delete /f /tn {task_name(project)}")]
    q = shlex.quote
    return [("unregister",
             "( crontab -l 2>/dev/null | grep -vF " + q(cron_marker(facts)) + " ) | crontab -")]


def plan_lines(project: str, facts, *, mounted: str = "") -> list:
    """새 데몬 등록 계획 대신 정책과 유지할 로그인 런처를 명시한다."""
    decision = desired_state(project, mounted, facts)
    out = [f"   · {facts.host}: {decision.reason}"]
    if facts.windows and getattr(facts, "role", "worker") == "worker":
        out.append(f"   → {facts.host}: 로그인 런처 {conductor_task_name(project)} 유지 "
                   "(서버 SSH 요청 시 실행)")
    return out


# [중요] **이 사유가 정본이다** (`#311`, 사용자 결정 ⓐ 2026-08-25). `plan_lines` 도 이 함수를
#    쓰고, `projects/onboard.py` 와 `docs/14-onboarding-runbook.md` §14.2-4 는 이 함수를
#    **가리킨다**. 종전에는 같은 규칙이 **네 곳**에 각자 적혀 있었고 넷 다 낡은 전제였다:
#    *"claim 에 프로젝트 축이 없다(#248)"* — 축은 **있다**(`#248` 닫힘 · `ClaimReq.project` ·
#    `claimer.py` 가 `#258` 로 태그를 붙인다).
@dataclass(frozen=True)
class ResidencyDecision:
    """상주의 원하는 상태. plan·deliver·check가 이 값 하나를 소비한다."""

    required: bool
    reason: str = ""


DECOMMISSIONED_REASON = "워커·요청자 상주 데몬은 폐기됐다 — 서버가 SSH로 총괄한다 (#861)"


def desired_state(project: str, mounted: str, facts=None, *, daemon_available: bool = True,
                  index_only: bool = False, code: bool = False) -> ResidencyDecision:
    """타입·능력·마운트와 무관하게 AX 작업 데몬은 요구하지 않는다.

    기존 인자는 호출 호환을 위해 남긴다. Windows 지휘자 런처는 별도 등록 계약이다.
    """
    return ResidencyDecision(False, DECOMMISSIONED_REASON)


def blocked_reason(project: str, mounted: str, facts=None) -> str:
    """상주 금지 사유. 과거의 마운트별 허용 판정으로 돌아가지 않는다."""
    return desired_state(project, mounted, facts).reason


# ── 배달 뒤 갱신 (`#277`) ──────────────────────────────────────────────────────

DAEMON_REL_WIN = DAEMON_REL.replace("/", chr(92))
PROBE_KEYS = ("running", "stale", "busy", "restart_pending", "pid", "started",
              "alive_age", "boot_mtime", "code_mtime", "locked", "no_stamp", "hung")


def console_python(path: str) -> str:
    """`pythonw.exe` → `python.exe`. [중요] 출력이 필요한 호출에는 콘솔판을 쓴다."""
    p = (path or "").strip()
    if p.lower().endswith("pythonw.exe"):
        return p[: -len("pythonw.exe")] + "python.exe"
    if p.lower() == "pythonw":
        return "python"
    return p


def probe_command(facts, *, python_path: str = "") -> str:
    """상주 상태를 묻는 원격 명령 한 줄.

    [중요] **판정 로직을 명령줄에 짜지 않는다** — `claimer.py --probe` 안(파이썬)에 있다.
    이유 둘: ⓐ bash→ssh→cmd 삼중 인용에서 `for /f`·PowerShell 한 줄이 깨진 실측이 있다
    (위 `PYTHONW_PROBE` 주석) ⓑ 같은 코드가 두 OS 에서 돌아 **로컬 유닛으로 잴 수 있다**.
    """
    if facts.windows:
        # [중요] **인터프리터를 박지 않는다** — 실측 2026-08-22: `.2` 에서 `where pythonw` 가
        #    빈 값이었다(실물은 `%LOCALAPPDATA%\Programs\Python\Python310\`). `python` 도
        #    PATH 에 있다고 가정하면 안 된다. 호출자가 `PYTHONW_PROBE` 로 잰 값을 넘긴다.
        # [중요] **probe 는 `pythonw` 로 돌리면 안 된다 — 콘솔이 없어 stdout 이 사라진다.**
        #    상주는 콘솔 창을 띄우지 않으려고 `pythonw` 를 쓰지만, 관측은 출력이 목적이다.
        py = console_python(python_path or python_for(facts))
        return f'cd /d "{facts.path}" && "{py}" "{facts.path}\\{DAEMON_REL_WIN}" --probe'
    return (f"cd {shlex.quote(facts.path)} && {python_for(facts)} "
            f"{shlex.quote(DAEMON_REL)} --probe")


def parse_probe(out: str) -> dict:
    """`key=value` 줄을 읽는다. [주의] 못 읽은 키는 **없는 것으로 두지 않는다** — 호출자가
    「모른다」와 「거짓」을 구분해야 한다(모르면 갱신을 강행하지 않는다)."""
    got = {}
    for line in (out or "").splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() in PROBE_KEYS:
            try:
                got[k.strip()] = int(v.strip())
            except ValueError:
                continue
    return got


def needs_refresh(state: dict) -> bool:
    """옛 데몬 상태가 남아 있어도 재기동·갱신 대상으로 삼지 않는다."""
    return False


def refresh_commands(facts, *, force: bool = False, pid: int = 0) -> list:
    """데몬 갱신을 위한 깃발·종료·재기동 명령을 생성하지 않는다."""
    return []


def clear_flag_commands(facts) -> list:
    """깃발 제거 — **놓은 쪽이 치운다.** 강제 종료 뒤에 부른다."""
    flag = f"{facts.path}\\.ax\\{RESTART_FILE}" if facts.windows \
        else f"{facts.path}/.ax/{RESTART_FILE}"
    return [("clear", f'del /q "{flag}" 2>nul' if facts.windows
             else f"rm -f {shlex.quote(flag)}")]


def refresh_plan_lines(facts, state: dict) -> list:
    """옛 호출자에게도 폐기 정책을 안내한다."""
    return [f"   · {facts.host}: {DECOMMISSIONED_REASON}"]
