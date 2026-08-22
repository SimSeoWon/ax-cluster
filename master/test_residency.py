"""claimer 상주 등록 (`#255`) — **두 기계가 한 선언에서 나온다.**

[중요] **실물과 대조해 만들었다** (2026-08-22). 문서만 보고 짜면 틀린다 — 실제로 두 번 틀렸다:

    ⓐ `pythonw` 가 **PATH 에 없다** (`where pythonw` 빈 값 · 실물은 `%LOCALAPPDATA%` 아래)
    ⓑ `schtasks /tr` 은 전체를 한 인자로 받고 **안쪽 인용을 `\\"` 로 이스케이프**해야 한다.
      그냥 주니 cmd 가 두 번째 토큰을 옵션으로 읽어 *"잘못된 인수/옵션"* 으로 거부했다

그리고 임시 작업(`AxProbeQuote`)으로 형태를 확인한 뒤 기존 `AxClaimer` 의 Task_To_Run 과
**글자까지 대조**했다 — 같았다.

`python3 master/test_residency.py`
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client.init import residency as R                              # noqa: E402
from master.client.bundle import HostFacts                           # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _f(*, windows, ue5="", path="/p/M"):
    return HostFacts(host="h", user="u", path=path, driven="ssh", role="worker",
                     os="windows" if windows else "linux", ue5=ue5, checkout_ok=True)


def test_types_from_probe() -> None:
    """[중요] 유형은 **probe 실측(`ue5`)** 에서 나온다 — 표로 들지 않는다."""
    check("UE5 있으면 build,code", R.types_for(_f(windows=True, ue5="x")) == "build,code")
    check("없으면 code", R.types_for(_f(windows=False)) == "code")


def test_task_name_per_project() -> None:
    """[중요] 한 기계에 둘이 설치될 수 있다(`#250`) → 이름이 갈려야 한다."""
    check("ModularStage 는 기존 이름 유지", R.task_name("ModularStage") == "AxClaimer")
    check("다른 프로젝트는 접미", R.task_name("NS") == "AxClaimer_NS")
    check("[중요] 두 이름이 다르다", R.task_name("NS") != R.task_name("ModularStage"))


def test_windows_command_shape() -> None:
    """실물과 같은 형태여야 한다 — 인용이 이 함수의 핵심이다."""
    c = dict(R.commands("ModularStage", _f(windows=True, ue5="x", path=r"E:\t\M"),
                        python_path=r"C:\Py\pythonw.exe"))["register"]
    check("schtasks /create /f (멱등)", "/create /f" in c, c)
    check("5분 주기", "/sc minute /mo 5" in c, c)
    check("[주의] 대화형 전용(/it) — 사람 PC 에 백그라운드 상주를 심지 않는다", "/it" in c, c)
    check("권한 상승 없음(/rl LIMITED)", "/rl LIMITED" in c, c)
    check("[중요] 안쪽 인용을 이스케이프한다", '\\"C:\\Py\\pythonw.exe\\"' in c, c)
    check("스크립트도 이스케이프", "claimer.py" in c and c.count('\\"') == 4, c)
    check("유형이 붙는다", "--types=build,code" in c, c)
    check("pythonw 를 쓴다 (콘솔 창 없음)", "pythonw" in c, c)


def test_linux_command_preserves_path_line() -> None:
    """[중요] **PATH 줄을 지키고 우리 줄만 갈아끼운다** — 실측: `.43` crontab 첫 줄이 PATH= 다."""
    c = dict(R.commands("ModularStage", _f(windows=False, path="/home/sim/trunk/M")))["register"]
    check("crontab -l 을 읽어서 다시 쓴다", "crontab -l" in c and "| crontab -" in c, c)
    check("[중요] 우리 줄만 제외한다 (grep -vF 마커)", "grep -vF" in c, c)
    check("[주의] 통째로 지우지 않는다", "crontab -r" not in c, c)
    check("마커가 체크아웃 경로다", "/home/sim/trunk/M &&" in c, c)
    check("5분 주기", "*/5 * * * *" in c, c)
    check("출력을 버린다 (감시자 로그 폭증 방지)", ">/dev/null 2>&1" in c, c)


def test_gate_before_second_project() -> None:
    """[중요] **`#248` 전에는 두 번째 프로젝트의 상주를 켜지 않는다** (`#251` 실측 근거)."""
    check("마운트와 같으면 막지 않는다", R.blocked_reason("M", "M") == "")
    why = R.blocked_reason("NS", "ModularStage")
    check("[중요] 다르면 막는다", bool(why), why)
    check("사유가 #248 을 가리킨다", "#248" in why, why)
    check("잠금은 체크아웃·큐는 공유라는 근거를 든다", "큐는 공유" in why, why)

    lines = R.plan_lines("NS", _f(windows=False), mounted="ModularStage")
    check("계획에 그 사유가 찍힌다", any("지금 켜지 않는다" in l for l in lines), str(lines))
    ok = R.plan_lines("ModularStage", _f(windows=False), mounted="ModularStage")
    check("같은 프로젝트면 그 줄이 없다", not any("지금 켜지 않는다" in l for l in ok), str(ok))


def test_python_probe() -> None:
    """[중요] 경로를 **박지 않고 잰다** — `Python310` 같은 버전 디렉토리가 들어간다."""
    check("PATH 먼저 본다", R.PYTHONW_PROBE.startswith("where pythonw"))
    check("LOCALAPPDATA 후보를 훑는다", "%LOCALAPPDATA%" in R.PYTHONW_PROBE)
    check("버전을 와일드카드로", "Python3*" in R.PYTHONW_PROBE)
    out = ("C:\\Users\\janus\\AppData\\Local\\Programs\\Python\\Python310\\pythonw.exe\n" * 2)
    check("출력에서 한 줄을 고른다",
          R.parse_python_probe(out).endswith("pythonw.exe"), R.parse_python_probe(out))
    check("[주의] 못 찾으면 빈 문자열 (추측하지 않는다)",
          R.parse_python_probe("INFO: 파일을 찾을 수 없습니다") == "")


if __name__ == "__main__":
    for fn in (test_types_from_probe, test_task_name_per_project, test_windows_command_shape,
               test_linux_command_preserves_path_line, test_gate_before_second_project,
               test_python_probe):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_residency: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
