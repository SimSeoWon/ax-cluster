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
