"""claimer 상주 등록 — **`.2` schtasks 와 `.43` cron 이 한 선언에서 나온다** (`#255`).

## 왜 선언이 필요한가

`#229` 미결 3 이 *"감시자(schtasks/cron) 등록을 사람이 하나, 배달이 하나"* 로 **질문 상태**로
남아 있었고, 두 기계의 등록 방식은 **문서에만** 있었다(`win-worker-2.md` § AxClaimer ·
`bc250-1.md` § AX claimer). 문서만 있으면 새 기계에서 재현되지 않는다.

## 실측 — 지금 두 기계의 실물 (2026-08-22)

    .2   schtasks `\\AxClaimer` · 5분 · 실행 계정 `DESKTOP-HV0I6DL\\janus`
         `"…\\Python310\\pythonw.exe" "E:\\trunk\\ModularStage\\.ax\\lib\\axmaster\\work\\claimer.py"
          --types=build,code`
         [주의] 마지막 결과 `0x800710e0` = *"운영자 또는 관리자가 요청을 거부"* — **로그온 세션
         전용**이라 세션이 없으면 이 값이 정상이다(CLAUDE.md 가 그렇게 적어 뒀다).
         지금 `claimer.lock` 도 pythonw 프로세스도 없다 = **상주 없음**이고 그것이 설계다
    .43  cron `*/5 * * * *` + `PATH=` 줄 · `cd <체크아웃> && /usr/bin/python3
         .ax/lib/axmaster/work/claimer.py --types=code`
         [주의] 상주 중(pid 실측). 헤드리스라 세션 제약이 없다

## [중요] 유형(`--types`)은 능력에서 나온다 — 표로 들지 않는다

`.2` 는 `build,code`(UE5 있음), `.43` 은 `code`(UE5 없음). 그 판정은 **probe 실측**(`ue5`)이고,
`#204` 가 그렇게 정했다. 선언에 하드코딩하면 새 기계에서 틀린다.

## [중요] 켜는 것과 만드는 것을 가른다 (`#251` 실측)

잠금은 **체크아웃 단위**(`<체크아웃>/.ax/claimer.lock`)인데 그 근거는 **큐**다
(*"겹치면 같은 큐를 두 입이 빤다"*). 프로젝트가 둘이면 각자 잠금을 얻고 같은 큐를 빨며,
claim 에 프로젝트 축이 없어(`#248`) 서로의 태스크를 집는다.

    → **한 기계에 두 번째 프로젝트의 상주는 `#248` 뒤에 켠다.**
      `plan_lines()` 가 그 사실을 찍고, `commands()` 는 만들어도 실행기가 게이트를 본다.
"""
from __future__ import annotations

import shlex

TASK_NAME = "AxClaimer"          # `.2` 의 실물 이름 — 바꾸면 기존 등록과 둘이 된다
INTERVAL_MIN = 5                 # 감시자 주기. 잠금 싱글턴이 겹침을 흡수한다
CLAIMER_REL = ".ax/lib/axmaster/work/claimer.py"
RESTART_FILE = "claimer.restart"    # claimer.RESTART_FILE 과 같은 값 (배달물은 마스터를 import 하지 않는다)


def types_for(facts) -> str:
    """이 기계가 집을 유형. [중요] **probe 실측(`ue5`)에서 나온다** — 표로 들지 않는다."""
    return "build,code" if getattr(facts, "ue5", "") else "code"


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
    """등록 명령 `(라벨, 명령)`. **여기가 계약이다** — 두 기계의 모양이 여기서만 갈린다."""
    types = types_for(facts)
    if facts.windows:
        py = python_path or python_for(facts)
        script = f'{facts.path}\\{CLAIMER_REL.replace("/", chr(92))}'
        # [중요] **`/tr` 은 전체를 한 인자로 받고, 안쪽 인용은 `\"` 로 이스케이프한다.**
        #    실측 2026-08-22: 그냥 `"py" "script" --types=…` 로 주니 cmd 가 두 번째 토큰을
        #    schtasks 의 옵션으로 읽어 *"잘못된 인수/옵션 - 'E:\…\claimer.py'"* 로 거부했다.
        #    임시 작업(`AxProbeQuote`)으로 이 형태를 확인한 뒤 기존 `AxClaimer` 의 Task_To_Run
        #    과 **글자까지 대조**했다 — 같았다. (임시 작업은 지웠다)
        run = f'\\"{py}\\" \\"{script}\\" --types={types}'
        name = task_name(project)
        # [주의] `/f` 로 덮어쓴다 — 멱등이어야 한다(감시자 등록을 두 벌 만들면 겹쳐 돈다).
        #    `/it` = 대화형 전용. 세션 없을 때 `0x800710e0` 이 나는 것이 **정상**이고,
        #    그것이 이 기계의 설계다(사람 PC 에 백그라운드 상주를 심지 않는다).
        return [("register",
                 f'schtasks /create /f /tn {name} /sc minute /mo {INTERVAL_MIN} '
                 f'/it /rl LIMITED /tr "{run}"')]
    q = shlex.quote
    line = (f"*/{INTERVAL_MIN} * * * * cd {q(facts.path)} && {python_for(facts)} "
            f"{CLAIMER_REL} --types={types} >/dev/null 2>&1")
    # [중요] **PATH 줄을 지키고 우리 줄만 갈아끼운다** — 실측: `.43` crontab 첫 줄이
    #    `PATH=/home/sim/.local/bin:…` 이고, 그것이 없으면 claimer 가 도구를 못 찾는다.
    #    [주의] `crontab -l | grep -v` 로 통째로 다시 쓰면 그 줄을 날린다.
    marker = f"cd {facts.path} &&"
    return [("register",
             "( crontab -l 2>/dev/null | grep -vF " + q(marker)
             + "; echo " + q(line) + " ) | crontab -")]


def plan_lines(project: str, facts, *, mounted: str = "") -> list:
    """`plan` 이 찍을 줄. [중요] **게이트를 함께 찍는다** — 지금 켜면 안 되는 경우가 있다."""
    out = [f"   ⟳ {facts.host}: claimer 상주 등록 — "
           + (f"schtasks `{task_name(project)}`" if facts.windows else "cron")
           + f" {INTERVAL_MIN}분 · --types={types_for(facts)}"]
    if facts.windows:
        out.append("     [주의] 로그온 세션 전용 — 세션이 없으면 `0x800710e0`(요청 거부)이 "
                   "정상이다. 사람 PC 에 백그라운드 상주를 심지 않는다")
    if mounted and project != mounted:
        out.append(f"     [중요] **지금 켜지 않는다** — 마운트는 {mounted} 이고 claim 에 "
                   f"프로젝트 축이 없다(#248). 두 상주가 같은 큐를 빨면 남의 태스크를 집는다")
    return out


def blocked_reason(project: str, mounted: str) -> str:
    """켜면 안 되는 사유. 빈 문자열이면 켜도 된다 (`#251` 실측 근거)."""
    if mounted and project != mounted:
        return (f"마운트되지 않은 프로젝트({project} ≠ {mounted})의 상주는 `#248`(큐가 project 로 "
                f"거른다) 뒤에 켠다 — 잠금은 체크아웃 단위지만 큐는 공유다")
    return ""


# ── 배달 뒤 갱신 (`#277`) ──────────────────────────────────────────────────────

CLAIMER_REL_WIN = CLAIMER_REL.replace("/", chr(92))
PROBE_KEYS = ("running", "stale", "busy", "restart_pending", "pid", "started",
              "alive_age", "boot_mtime", "code_mtime", "locked", "no_stamp")


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
        return f'cd /d "{facts.path}" && "{py}" "{facts.path}\\{CLAIMER_REL_WIN}" --probe'
    return (f"cd {shlex.quote(facts.path)} && {python_for(facts)} "
            f"{shlex.quote(CLAIMER_REL)} --probe")


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
    """갱신해야 하나. [중요] **`stale` 하나만 본다** — `running=0` 은 갱신 대상이 아니다
    (감시자가 다음 주기에 새 코드로 띄운다). 상태를 못 읽었으면 **건드리지 않는다.**"""
    if not state or "stale" not in state:
        return False
    return bool(state.get("stale"))


def refresh_commands(facts, *, force: bool = False, pid: int = 0) -> list:
    """갱신 명령 `(라벨, 명령)`. **깃발이 먼저, 강제 종료는 폴백이다.**

    [중요] 완료 조건 3(*"재기동이 진행 중 작업을 죽이지 않는다"*)을 지키는 방법이 깃발이다 —
    claimer 가 **다음 claim 전에** 그것을 보고 물러나므로 처리 중 태스크를 버리지 않는다.
    [주의] 그런데 **옛 코드는 깃발을 모른다**(이번 사고의 상주가 그랬다). 그래서 폴백이 필요하고,
    폴백은 `force=True` 로만 나간다 — 호출자가 `busy=0` 을 확인한 뒤에만 켠다.
    """
    flag = f"{facts.path}\\.ax\\{RESTART_FILE}" if facts.windows \
        else f"{facts.path}/.ax/{RESTART_FILE}"
    out = [("flag", f'echo 1 > "{flag}"' if facts.windows
            else f"echo 1 > {shlex.quote(flag)}")]
    if force:
        # [주의] 강제 종료는 **깃발을 모르는 옛 코드**를 위한 것이다. 감시자가 되살린다.
        # [중요] **pid 로만 죽인다.** 이름/패턴으로 죽이면(`taskkill /im pythonw.exe`,
        #    `pkill -f claimer.py`) **다른 프로젝트의 상주까지 죽는다** — 한 기계에 여럿을
        #    허용한 것(`#250`)이 이 갱신 절차 때문에 깨지면 안 된다. pid 는 probe 가 준다.
        if pid > 0:
            out.append(("kill", f"taskkill /f /pid {pid}" if facts.windows
                        else f"kill {pid}"))
        else:
            out.append(("kill", "(pid 를 모른다 — 강제 종료를 건너뛴다. "
                                "이름으로 죽이면 남의 프로젝트 상주까지 죽는다)"))
    return out


def clear_flag_commands(facts) -> list:
    """깃발 제거 — **놓은 쪽이 치운다.** 강제 종료 뒤에 부른다."""
    flag = f"{facts.path}\\.ax\\{RESTART_FILE}" if facts.windows \
        else f"{facts.path}/.ax/{RESTART_FILE}"
    return [("clear", f'del /q "{flag}" 2>nul' if facts.windows
             else f"rm -f {shlex.quote(flag)}")]


def refresh_plan_lines(facts, state: dict) -> list:
    """`plan` 이 찍을 줄 — [중요] **무엇을 근거로 갱신하는지 함께 찍는다.**"""
    if not state or "stale" not in state:
        return [f"   ? {facts.host}: 상주 상태를 읽지 못했다 — **건드리지 않는다** "
                f"(모르는 것을 고치면 진행 중 작업을 죽인다)"]
    if not state.get("running"):
        return [f"   · {facts.host}: 상주 없음 — 갱신 대상이 아니다 "
                f"(감시자가 다음 주기에 새 코드로 띄운다)"]
    if not state.get("stale"):
        return [f"   [완료] {facts.host}: 도는 것이 지금 코드다 "
                f"(부팅 mtime {state.get('boot_mtime')} ≥ 코드 {state.get('code_mtime')})"]
    busy = " · **처리 중** — 태스크가 끝난 뒤 물러난다" if state.get("busy") else ""
    if state.get("no_stamp"):
        # [중요] 가장 위험한 상태다 — 깃발을 모르고, 거절을 태스크로 읽는다(이번 사고의 상주)
        return [f"   ⟳ {facts.host}: **`#277` 이전 코드가 돌고 있다** (잠금은 쥐었는데 부팅 "
                f"스탬프가 없다) → 깃발은 무시될 것이므로 **pid 로 강제 종료**한다{busy}"]
    return [f"   ⟳ {facts.host}: **옛 코드로 돌고 있다** "
            f"(부팅 {state.get('boot_mtime')} < 코드 {state.get('code_mtime')}) → 갱신 깃발{busy}"]
