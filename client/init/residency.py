"""AX 원격 등록 — 상주 작업 데몬은 금지, 로그인 런처와 옛 등록 해제만 유지한다.

사용자 2026-10-31 (#860 · #861): 서버가 SSH로 작업을 총괄한다. 데몬 생성·기동·갱신
명령은 더 이상 만들지 않는다. AxConductor는 Windows 로그인 세션을 빌리는 별도 런처다.
옛 AxWorker 이름·cron 표식은 이미 배달된 등록을 찾아 제거하기 위한 계약으로 남긴다.
"""

from __future__ import annotations

import base64
import re
import shlex
from dataclasses import dataclass

TASK_NAME = "AxWorker"           # 철회된 상주의 옛 작업 이름 — 남은 등록을 찾아 해제하는 데만 쓴다 (#861)
INTERVAL_MIN = 5                 # 감시자 주기. 잠금 싱글턴이 겹침을 흡수한다
# [주의] 데몬 파일 경로·재기동 깃발 상수는 지웠다 (#861, 2026-10-31) — 데몬 모듈이 저장소에서
#    삭제됐다. 옛 등록 해제는 **프로젝트 이름과 무관하게** `AxWorker*`·`AxClaimer*` 작업과
#    `worker_daemon`·`claimer` cron 줄을 찾는다 (#861 T5 — 현재 프로젝트명만 보면 다른 이름의
#    잔재를 놓친다).


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
    """옛 상주 작업 이름(프로젝트별). 등록은 더 이상 하지 않는다 — 배달이 남은 등록을 이 이름으로
    찾아 해제하고 check 가 잔재를 잡는다 (#861). 옛 `AxClaimer`(#320 철거)·`AxWorker`(#404 철회)는
    기록이다.
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
    """옛 체크아웃별 cron 표식(기록·호환용). 잔재 판정·해제는 `CRON_PATTERNS` 를 쓴다 (#861 T5)."""
    return f"cd {facts.path} &&"


LEGACY_TASK_PREFIXES = ("AxWorker", "AxClaimer")   # 철회된 상주의 옛 작업 이름 접두 — 프로젝트명 무관 (#861 T5)
PROTECTED_TASK_PREFIXES = ("AxConductor", "AX_Ollama")  # 절대 건드리지 않는다 — 로그인 런처·추론 상주
CRON_PATTERNS = ("worker_daemon", "claimer")       # 옛 cron 줄을 찾는 고정 문자열 — 경로·프로젝트 무관
TASKS_MARK = "AX_RESIDENCY_TASKS="
ABSENT_MARK = "AX_RESIDENCY_PRESENT=0"
ERROR_MARK = "AX_RESIDENCY_ERROR="
_SAFE_TASK = re.compile(r"^\\?(?:[A-Za-z0-9_.-]+\\)*[A-Za-z0-9_.-]+$")


def encoded_powershell(script: str) -> str:
    """PowerShell 스크립트를 `-EncodedCommand`(UTF-16LE base64)로 싼다.

    [중요] OpenSSH → cmd.exe → powershell 세 겹 인용을 아예 피한다 — `|`·`%`·`^`·따옴표가
    cmd 에 닿지 않는다. 덤으로 이 프로세스의 명령줄에 검색 문자열이 평문으로 남지 않아
    프로세스 조회가 자기 자신을 잡지 않는다.
    """
    b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"powershell -NoProfile -NonInteractive -EncodedCommand {b64}"


def _task_leaf(name: str) -> str:
    return name.rsplit("\\", 1)[-1]


def is_legacy_task(name: str) -> bool:
    """옛 상주 작업 이름인가. 보호 접두(`AxConductor*`·`AX_Ollama*`)는 늘 거짓이다."""
    leaf = _task_leaf(name).lower()
    if any(leaf.startswith(p.lower()) for p in PROTECTED_TASK_PREFIXES):
        return False
    return any(leaf.startswith(p.lower()) for p in LEGACY_TASK_PREFIXES)


def _registration_ps_script() -> str:
    likes = " -or ".join(f"$_.TaskName -like '{p}*'" for p in LEGACY_TASK_PREFIXES)
    return (
        "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
        "try { $n=@(Get-ScheduledTask -ErrorAction Stop | "
        f"Where-Object {{ {likes} }} | "
        "ForEach-Object { $_.TaskPath + $_.TaskName }); "
        f"if($n.Count -gt 0){{ '{TASKS_MARK}' + ($n -join ';') }} else {{ '{ABSENT_MARK}' }} }} "
        f"catch {{ Write-Output ('{ERROR_MARK}' + $_.Exception.Message); exit 1 }}"
    )


def registration_query_command(project: str = "", facts=None) -> str:
    """옛 상주 등록 조회 — **프로젝트 이름과 무관하게** 남은 것을 전부 찾는다 (#861 T5).

    Windows: `AxWorker*`·`AxClaimer*` 예약 작업 전부 → `AX_RESIDENCY_TASKS=<경로1>;<경로2>` 또는
    `AX_RESIDENCY_PRESENT=0`, 오류는 `AX_RESIDENCY_ERROR=` + exit 1.
    Linux: crontab 전체(`worker_daemon`·`claimer` 줄을 판정 쪽에서 찾는다).
    `project` 인자는 호출 호환용이다.
    """
    if facts is not None and facts.windows:
        return encoded_powershell(_registration_ps_script())
    return "LC_ALL=C crontab -l 2>&1"


def _cron_hits(text: str) -> list:
    return [ln.strip() for ln in (text or "").splitlines()
            if ln.strip() and any(p in ln for p in CRON_PATTERNS)]


def registration_status(rc: int, out: str, facts) -> dict:
    """`{"known", "present", "names"}`. 관측 불가를 부재로 접지 않는다.

    Windows 는 표식 줄만 읽는다(`#< CLIXML` 등 잡음은 무시). 표식이 정확히 하나 있어야 known 이다.
    """
    text = (out or "").strip()
    if facts.windows:
        lines = [x.strip() for x in text.splitlines()]
        marks = [x for x in lines if x.startswith(("AX_RESIDENCY_", ))]
        if rc == 0 and len(marks) == 1:
            m = marks[0]
            if m == ABSENT_MARK:
                return {"known": True, "present": False, "names": []}
            if m.startswith(TASKS_MARK):
                names = [n.strip() for n in m[len(TASKS_MARK):].split(";") if n.strip()]
                bad = [n for n in names if not _SAFE_TASK.match(n) or not is_legacy_task(n)]
                if names and not bad:
                    return {"known": True, "present": True, "names": names}
                return {"known": False, "present": None, "names": [],
                        "error": f"상주 등록 조회 결과를 해석하지 못했다: {m[:160]}"}
    elif rc == 0:
        hits = _cron_hits(text)
        return {"known": True, "present": bool(hits), "names": hits}
    elif rc == 1 and text.lower().startswith("no crontab for "):
        return {"known": True, "present": False, "names": []}
    return {"known": False, "present": None, "names": [],
            "error": f"상주 등록 조회 실패 rc={rc}: {text[:160] or '(응답 없음)'}"}


def registration_present(rc: int, out: str, facts) -> bool:
    """호환용 존재 조회. 실패를 다루는 호출자는 registration_status를 사용한다."""
    return registration_status(rc, out, facts).get("present") is True


def unregister_commands(project: str, facts, names=()) -> list:
    """상주 **해제** 명령 `(라벨, 명령)` (`#311` · `#861` T5).

    Windows: 조회가 찾은 **이름마다** `schtasks /delete` — 프로젝트 이름과 무관하다.
    `names` 를 안 주면 옛 프로젝트별 이름 하나(호환). 보호 접두·이상한 이름은 명령을 내지 않는다.
    Linux: `worker_daemon`·`claimer` 줄만 뺀다 — `PATH=` 등 다른 줄은 보존한다.
    [주의] crontab 읽기가 실패하면 쓰지 않는다 — 빈 crontab 으로 덮지 않는다.
    """
    if facts.windows:
        want = list(names) or [task_name(project)]
        return [(f"unregister {n}", f'schtasks /delete /f /tn "{n}"')
                for n in want if _SAFE_TASK.match(n) and is_legacy_task(n)]
    pats = " ".join(f"-e {shlex.quote(p)}" for p in CRON_PATTERNS)
    return [("unregister",
             'c=$(crontab -l) || exit 1; '
             f'printf \'%s\\n\' "$c" | grep -vF {pats} | crontab -')]


# ── 실행 중인 데몬 프로세스 (#861 T5) — 조회만, 종료하지 않는다 ─────────────────
PROCS_MARK = "AX_DAEMON_PROCS="
PROCS_DONE = "AX_DAEMON_DONE"
PROCS_ERROR = "AX_DAEMON_ERROR="


def daemon_process_query_command(facts) -> str:
    """`worker_daemon`·`claimer` 가 명령줄에 든 프로세스 pid. 끝 표식이 없으면 조회 실패다."""
    if facts.windows:
        script = (
            "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
            "try { $p=@(Get-CimInstance Win32_Process -ErrorAction Stop | "
            "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'worker_daemon|claimer' } | "
            "ForEach-Object { $_.ProcessId }); "
            f"'{PROCS_MARK}' + ($p -join ','); '{PROCS_DONE}' }} "
            f"catch {{ Write-Output ('{PROCS_ERROR}' + $_.Exception.Message); exit 1 }}"
        )
        return encoded_powershell(script)
    # [중요] `[w]orker_daemon` — 이 명령을 실은 셸의 명령줄 자체는 정규식에 걸리지 않는다
    return ("p=$(pgrep -d, -f '[w]orker_daemon|[c]laimer'); rc=$?; "
            f"if [ $rc -gt 1 ]; then echo {PROCS_ERROR}pgrep_rc=$rc; exit 1; fi; "
            f'echo "{PROCS_MARK}$p"; echo {PROCS_DONE}')


def daemon_process_status(rc: int, out: str) -> dict:
    """`{"known", "pids", "error"}`. 끝 표식·pid 표식이 없거나 rc≠0 이면 조회 실패다."""
    lines = [x.strip() for x in (out or "").splitlines()]
    procs = [x for x in lines if x.startswith(PROCS_MARK)]
    if rc != 0 or PROCS_DONE not in lines or len(procs) != 1:
        return {"known": False, "pids": [],
                "error": f"데몬 프로세스 조회 실패 rc={rc}: {(out or '').strip()[:160] or '(응답 없음)'}"}
    pids = [p.strip() for p in procs[0][len(PROCS_MARK):].split(",") if p.strip()]
    if not all(p.isdigit() for p in pids):
        return {"known": False, "pids": [], "error": f"데몬 프로세스 조회 결과 해석 실패: {procs[0][:160]}"}
    return {"known": True, "pids": pids, "error": ""}


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

def console_python(path: str) -> str:
    """`pythonw.exe` → `python.exe`. [중요] 출력이 필요한 호출에는 콘솔판을 쓴다."""
    p = (path or "").strip()
    if p.lower().endswith("pythonw.exe"):
        return p[: -len("pythonw.exe")] + "python.exe"
    if p.lower() == "pythonw":
        return "python"
    return p


def needs_refresh(state: dict) -> bool:
    """옛 데몬 상태가 남아 있어도 재기동·갱신 대상으로 삼지 않는다."""
    return False


def refresh_commands(facts, *, force: bool = False, pid: int = 0) -> list:
    """데몬 갱신을 위한 깃발·종료·재기동 명령을 생성하지 않는다."""
    return []


def refresh_plan_lines(facts, state: dict) -> list:
    """옛 호출자에게도 폐기 정책을 안내한다."""
    return [f"   · {facts.host}: {DECOMMISSIONED_REASON}"]
