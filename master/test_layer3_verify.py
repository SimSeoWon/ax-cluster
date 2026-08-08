"""층3 게이트 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_layer3_verify.py

🔴 이 테스트가 지키는 불변식 (PLAN §5.5.4-⑥-③-1, 2026-08-08 실측에서 나온 것):
   1. **통과한 실행에도 `LogAutomationTest: Error` 가 있다** — Error 로 판정하면 안 된다
   2. **에디터가 0 이어도 `ssh` 는 1 을 낸다** — 프로세스 반환 코드로 판정하면 안 된다
   3. 완료 마커 없음 / exit != 0 / 성공 0건 → 전부 **fail-closed**
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.layer3_verify import (  # noqa: E402
    build_command,
    parse_automation_log,
    run_tests_on_workshop,
)

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


# ── 실측 로그를 그대로 옮긴 픽스처 (.2, 2026-08-08) ───────────────────────────
REAL_PASS = """LogAutomationTest: Error: Condition failed
LogAutomationTest: Error: Condition failed
LogAutomationTest: Error: Condition failed
LogAudio: Display: No default SoundConcurrencyObject specified (or failed to load).
LogAutomationController: Display: Test Completed. Result={Success} Name={CondensationGraph} Path={System.Core.Algo.CondensationGraph}
LogAutomationController: Display: Test Completed. Result={Success} Name={ReachabilityGraph} Path={System.Core.Algo.ReachabilityGraph}
LogAutomationController: Display: Test Completed. Result={Success} Name={TopologicalSort} Path={System.Core.Algo.TopologicalSort}
LogAutomationController: Display: Test Completed. Result={Success} Name={Unique} Path={System.Core.Algo.Unique}
LogAutomationController: Display: Test Completed. Result={Success} Name={UniqueBy} Path={System.Core.Algo.UniqueBy}
LogAutomationCommandLine: Display: **** TEST COMPLETE. EXIT CODE: 0 ****
"""

WITH_FAIL = """LogAutomationController: Display: Test Completed. Result={Success} Name={A} Path={X.A}
LogAutomationController: Display: Test Completed. Result={Fail} Name={B} Path={X.B}
LogAutomationCommandLine: Display: **** TEST COMPLETE. EXIT CODE: 0 ****
"""


def fake(stdout="", *, rc=0, stderr="", raises=None):
    def run(cmd, timeout):
        run.cmd = list(cmd)
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)

    run.cmd = []
    return run


def main() -> int:
    print("[1] 🔴 실측 통과 로그 — Error 15줄이 있어도 통과다")
    r = parse_automation_log(REAL_PASS)
    check("passed=True", r.passed, r.summary())
    check("계약 위반 없음", r.failure is None, str(r.failure))
    check("성공 5건", r.success_count == 5, str(r.success_count))
    check("실패 0건", r.fail_count == 0)
    check("exit_code 0", r.exit_code == 0, str(r.exit_code))
    check(
        "🔴 Error 줄이 판정에 영향을 주지 않았다",
        "LogAutomationTest: Error" in REAL_PASS and r.passed,
    )

    print("\n[2] 실패한 테스트가 있으면 막는다 — 계약 위반이 아니라 '불합격'")
    r = parse_automation_log(WITH_FAIL)
    check("passed=False", not r.passed)
    check("failure 는 None (계약은 지켜졌다)", r.failure is None, str(r.failure))
    check("실패 1건 집계", r.fail_count == 1)
    check("실패 목록에 경로", r.failures()[0].path == "X.B", str(r.failures()))
    check("summary 가 FAIL", r.summary().startswith("FAIL"), r.summary())

    print("\n[3] 🔴 fail-closed — 세 가지 계약 위반")
    r = parse_automation_log(
        "LogAutomationController: Display: Test Completed. Result={Success} Name={A} Path={X.A}\n"
    )
    check("완료 마커 없음 → 차단", not r.passed and r.failure, r.summary())
    check("  사유에 마커 언급", "TEST COMPLETE" in (r.failure or ""), str(r.failure))

    r = parse_automation_log(
        "Test Completed. Result={Success} Name={A} Path={X.A}\n"
        "**** TEST COMPLETE. EXIT CODE: 3 ****\n"
    )
    check("exit != 0 → 차단", not r.passed and r.failure, r.summary())
    check("  exit_code 보존", r.exit_code == 3, str(r.exit_code))

    r = parse_automation_log("**** TEST COMPLETE. EXIT CODE: 0 ****\n")
    check("성공 0건 → 차단", not r.passed and r.failure, r.summary())
    check("  '검증하지 않은 실행' 사유", "0건" in (r.failure or ""), str(r.failure))

    r = parse_automation_log(
        "Test Completed. Result={NotRun} Name={A} Path={X.A}\n"
        "**** TEST COMPLETE. EXIT CODE: 0 ****\n"
    )
    check("전부 NotRun → 차단(성공 0건)", not r.passed and r.failure, r.summary())

    # 실측(2026-08-08): 매치 없는 필터를 주면 UE 5.8 은 EXIT CODE -1 을 낸다.
    # ② 가 먼저 잡지만, ④ 가 없으면 엔진이 0 을 내도록 바뀌는 순간 방어가 사라진다.
    r = parse_automation_log("**** TEST COMPLETE. EXIT CODE: -1 ****\n")
    check("매치 없음(UE 5.8 실측 exit -1) → 차단", not r.passed and r.failure, r.summary())
    check("  음수 exit 파싱", r.exit_code == -1, str(r.exit_code))

    print("\n[4] Success/Fail 이 아닌 결과는 막지 않되 보이게 남긴다")
    r = parse_automation_log(
        "Test Completed. Result={Success} Name={A} Path={X.A}\n"
        "Test Completed. Result={Skipped} Name={B} Path={X.B}\n"
        "**** TEST COMPLETE. EXIT CODE: 0 ****\n"
    )
    check("passed=True", r.passed, r.summary())
    check("기타 1건 집계", len(r.other) == 1, str(r.other))
    check("summary 에 기타 노출", "기타" in r.summary(), r.summary())

    print("\n[5] 마커가 여러 번이면 마지막을 쓴다")
    r = parse_automation_log(
        "Test Completed. Result={Success} Name={A} Path={X.A}\n"
        "**** TEST COMPLETE. EXIT CODE: 5 ****\n"
        "Test Completed. Result={Success} Name={B} Path={X.B}\n"
        "**** TEST COMPLETE. EXIT CODE: 0 ****\n"
    )
    check("마지막 exit 0 을 채택", r.exit_code == 0 and r.passed, r.summary())

    print("\n[6] 빈 입력·쓰레기 입력")
    for label, txt in (("빈 문자열", ""), ("공백", "  \n\n"), ("무관한 로그", "hello\nworld\n")):
        r = parse_automation_log(txt)
        check(f"{label} → 차단", not r.passed and bool(r.failure))

    print("\n[7] 🔴 프로세스 반환 코드로 판정하지 않는다")
    # 실측: 에디터 EXIT CODE 0 인데 ssh 는 1 을 냈다.
    r = run_tests_on_workshop(
        "192.168.0.2", "janus", "C:/UE/UnrealEditor-Cmd.exe", "E:/p.uproject", "X",
        runner=fake(REAL_PASS, rc=1),
    )
    check("rc=1 이어도 로그가 통과면 통과", r.passed, r.summary())
    # 역방향도 막아야 한다 — rc=0 이라고 통과가 아니다.
    r = run_tests_on_workshop(
        "h", "u", "e", "p", "X", runner=fake("아무 마커 없음", rc=0)
    )
    check("rc=0 이어도 마커 없으면 차단", not r.passed and r.failure, r.summary())

    print("\n[8] stderr 로 나와도 잡는다")
    r = run_tests_on_workshop("h", "u", "e", "p", "X", runner=fake("", stderr=REAL_PASS))
    check("stderr 파싱", r.passed, r.summary())

    print("\n[9] 실행 실패는 차단")
    r = run_tests_on_workshop(
        "h", "u", "e", "p", "X", runner=fake(raises=subprocess.TimeoutExpired("ssh", 10))
    )
    check("타임아웃 → 차단", not r.passed and r.failure, r.summary())
    r = run_tests_on_workshop("h", "u", "e", "p", "X", runner=fake(raises=OSError("boom")))
    check("OSError → 차단", not r.passed and r.failure, r.summary())

    print("\n[10] 조립되는 명령 — 세션 0 구동 요건")
    cmd = build_command(
        r"C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
        r"E:\trunk\ModularStage\ModularStage.uproject",
        "System.Core.Algo",
    )
    check("🔴 -nullrhi (세션 0 의 핵심)", "-nullrhi" in cmd, cmd)
    check("-unattended", "-unattended" in cmd)
    check("-nopause (프롬프트로 매달리지 않는다)", "-nopause" in cmd)
    check("-stdout (로그를 받아야 판정한다)", "-stdout" in cmd)
    check("RunTests 필터 전달", "Automation RunTests System.Core.Algo" in cmd, cmd)
    check("Quit 로 끝난다", "; Quit" in cmd, cmd)
    check("경로가 원문 그대로", r"E:\trunk\ModularStage" in cmd, cmd)
    # 게이트가 저장소를 건드리면 안 된다.
    for verb in ("clean", "reset", "checkout", "push", "commit"):
        check(f"  `{verb}` 없음", verb not in cmd)

    print("\n[11] 빌드 판정 — 실측 로그 픽스처")
    from master.layer3_verify import (  # noqa: E402
        build_build_command,
        parse_build_log,
        run_build_on_workshop,
    )

    # 실측(.2, 2026-08-08) 성공 로그
    BUILD_OK = """Using 'git status' to determine working set for adaptive non-unity build.
UbaServer - Listening on 0.0.0.0:1345
Target is up to date
Output binary: C:\\Program Files\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor.exe

Result: Succeeded
Total execution time: 1.86 seconds
"""
    # 실측 실패 로그 (없는 타깃)
    BUILD_FAIL = """Location: C:\\Program Files\\UE_5.8\\Engine\\Intermediate\\Build\\BuildRules\\UE5Rules.dll

Result: Failed (RulesError)
Total execution time: 1.04 seconds
"""
    b = parse_build_log(BUILD_OK)
    check("성공 로그 → passed", b.passed, b.summary())
    check("  소요 시간 파싱", b.seconds == 1.86, str(b.seconds))
    check("  summary", b.summary().startswith("BUILD OK"), b.summary())

    b = parse_build_log(BUILD_FAIL)
    check("실패 로그 → 차단", not b.passed, b.summary())
    check("  failure=None (계약은 지켜졌다)", b.failure is None, str(b.failure))
    check("  사유 태그 보존", b.detail == "RulesError", b.detail)

    b = parse_build_log("아무 판정 줄 없음\n")
    check("판정 줄 없음 → 계약 위반", not b.passed and b.failure, b.summary())
    check("빈 입력 → 계약 위반", not parse_build_log("").passed)

    print("\n[12] 🔴 빌드도 반환 코드로 판정하지 않는다")
    # 실측: Build.bat 이 실패해도 ssh 는 0 을 낸다 — 이게 가장 위험한 방향이다.
    b = run_build_on_workshop("h", "u", "bb", "T", "p", runner=fake(BUILD_FAIL, rc=0))
    check("🔴 rc=0 이어도 로그가 Failed 면 차단", not b.passed, b.summary())
    b = run_build_on_workshop("h", "u", "bb", "T", "p", runner=fake(BUILD_OK, rc=9))
    check("rc=9 여도 로그가 Succeeded 면 통과", b.passed, b.summary())
    b = run_build_on_workshop(
        "h", "u", "bb", "T", "p", runner=fake(raises=subprocess.TimeoutExpired("ssh", 5))
    )
    check("타임아웃 → 차단", not b.passed and b.failure, b.summary())

    print("\n[13] 빌드 명령 형태 — Jenkins 등 외부 구동 표준")
    bc = build_build_command(
        r"C:\Program Files\UE_5.8\Engine\Build\BatchFiles\Build.bat",
        "ModularStageEditor",
        r"E:\trunk\ModularStage\ModularStage.uproject",
    )
    check("타깃·플랫폼·구성", "ModularStageEditor Win64 Development" in bc, bc)
    check("-Project 지정", '-Project="E:\\trunk\\ModularStage\\ModularStage.uproject"' in bc, bc)
    check("-WaitMutex (동시 실행 충돌 방지)", "-WaitMutex" in bc, bc)
    check("call 로 호출 (배치가 조기 종료되지 않게)", bc.startswith("call "), bc)
    for verb in ("clean", "reset", "checkout", "push"):
        check(f"  `{verb}` 없음", verb not in bc.lower())

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
