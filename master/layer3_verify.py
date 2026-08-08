"""층3 검증의 판정 계약 — fail-closed (PLAN §4.3, §5.5.4-⑥-③).

층3 은 **UE5 가 실제로 빌드되고 테스트가 도는가**다. 층2(§9.4.4)가 LLM 판정의 계약이라면
이쪽은 **엔진 로그의 계약**이다. 형태는 같다 — 정확한 신호만 믿고, 없으면 막는다.

🔴 **판정 신호는 이 둘뿐이다** (실측 2026-08-08, `.2` 에서 SSH·세션 0 구동):

    LogAutomationController: Display: Test Completed. Result={Success|Fail} Name={..} Path={..}
    LogAutomationCommandLine: Display: **** TEST COMPLETE. EXIT CODE: N ****

🔴 **틀린 신호 두 개 — 실측으로 걸렀다:**

1. **SSH 종료 코드를 쓰지 마라.** 에디터가 `EXIT CODE: 0` 인 실행에서도 `ssh` 는 **1** 을
   반환했다(두 번 다). 감싼 배치의 `%ERRORLEVEL%` 도 기록되지 않았다 — 래퍼 문제가 아니라
   원격 프로세스 종료와 SSH 채널 종료가 어긋나는 것이다.
2. **`Error` 문자열을 쓰지 마라.** **전부 통과한 실행에 `LogAutomationTest: Error` 가
   15줄** 있었다. 실패를 일부러 유발하는 부정 경로 검사들이 그렇게 남긴다.
   `grep -i error` 게이트는 **통과한 빌드를 실패로 판정한다.**

통과 조건은 네 가지가 **전부** 참일 때뿐이다:
  ① 완료 마커가 있다   ② `EXIT CODE: 0`   ③ `Result={Fail}` 이 0건   ④ `Success` 가 1건 이상

④ 는 **이중 방어**다. 실측(2026-08-08 `.2`)에서 매치가 없는 필터를 주면 UE 5.8 은
`EXIT CODE: -1` 을 내므로 ② 가 먼저 잡는다 — 즉 지금 엔진에서는 ④ 없이도 막힌다.
그래도 남겨 두는 이유는 **판정을 엔진의 종료 코드 관례에 의존시키지 않기 위해서**다.
아무것도 검증하지 않은 실행을 통과로 세면 게이트가 조용히 무의미해지는데, 그 방어가
엔진 버전이 바뀌면 사라지는 것이면 방어가 아니다.

⚠️ 이 모듈의 초안은 "매치가 없어도 exit 0" 이라고 적었다 — **실측으로 틀린 것이 확인돼
고쳤다.** 추측으로 쓴 근거는 실행해 보기 전까지 근거가 아니다.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Sequence

# `Test Completed. Result={Success} Name={Unique} Path={System.Core.Algo.Unique}`
_RESULT = re.compile(
    r"Test Completed\.\s*Result=\{(?P<result>[^}]*)\}"
    r"(?:\s*Name=\{(?P<name>[^}]*)\})?"
    r"(?:\s*Path=\{(?P<path>[^}]*)\})?"
)
# `**** TEST COMPLETE. EXIT CODE: 0 ****`
_COMPLETE = re.compile(r"TEST COMPLETE\.\s*EXIT CODE:\s*(?P<code>-?\d+)")

SUCCESS = "Success"
FAIL = "Fail"

DEFAULT_TIMEOUT = 3600  # 층3 은 길다. 셰이더/DDC 가 차가우면 수십 분이 정상이다.

Runner = Callable[[Sequence[str], int], subprocess.CompletedProcess]


def _run(cmd: Sequence[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd), capture_output=True, text=True, timeout=timeout, check=False
    )


@dataclass
class TestOutcome:
    result: str
    name: str = ""
    path: str = ""

    @property
    def ok(self) -> bool:
        return self.result == SUCCESS


@dataclass
class Layer3Result:
    """층3 판정. `passed` 만 보고 분기하면 된다 — fail-closed 가 이미 반영돼 있다."""

    passed: bool
    failure: str | None                       # None = 테스트가 실제로 돌고 판정이 났다
    exit_code: int | None = None
    tests: list[TestOutcome] = field(default_factory=list)
    raw_tail: str = ""                        # 진단용 — 로그 끝부분

    @property
    def success_count(self) -> int:
        return sum(1 for t in self.tests if t.result == SUCCESS)

    @property
    def fail_count(self) -> int:
        return sum(1 for t in self.tests if t.result == FAIL)

    @property
    def other(self) -> list[TestOutcome]:
        """`Success`/`Fail` 이 아닌 결과(NotRun·Skipped 등). 막지는 않되 보이게 남긴다."""
        return [t for t in self.tests if t.result not in (SUCCESS, FAIL)]

    def failures(self) -> list[TestOutcome]:
        return [t for t in self.tests if t.result == FAIL]

    def summary(self) -> str:
        if self.passed:
            s = f"PASS({self.success_count}건)"
            if self.other:
                s += f" +기타 {len(self.other)}건"
            return s
        if self.failure:
            return f"BLOCKED(계약 위반: {self.failure})"
        return f"FAIL({self.fail_count}/{len(self.tests)}건)"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failure": self.failure,
            "exit_code": self.exit_code,
            "summary": self.summary(),
            "success": self.success_count,
            "fail": self.fail_count,
            "other": [{"result": t.result, "path": t.path} for t in self.other],
            "failed_tests": [{"name": t.name, "path": t.path} for t in self.failures()],
            "raw_tail": self.raw_tail,
        }


def parse_automation_log(text: str, *, tail_lines: int = 15) -> Layer3Result:
    """엔진 로그에서 층3 판정을 뽑는다. **순수 함수 — 프로세스를 띄우지 않는다.**

    🔴 `Error` 문자열도 SSH 종료 코드도 보지 않는다. 위 모듈 독스트링 참조.
    """
    text = text or ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    tail = "\n".join(lines[-tail_lines:])

    tests = [
        TestOutcome(
            result=(m.group("result") or "").strip(),
            name=(m.group("name") or "").strip(),
            path=(m.group("path") or "").strip(),
        )
        for m in _RESULT.finditer(text)
    ]

    # ① 완료 마커 — 없으면 로그가 잘렸거나 프로세스가 죽었다는 뜻이다.
    completes = _COMPLETE.findall(text)
    if not completes:
        return Layer3Result(
            passed=False,
            failure=(
                "완료 마커('TEST COMPLETE. EXIT CODE:')가 없다. "
                "로그가 잘렸거나 에디터가 비정상 종료했다 — 통과로 취급하지 않는다."
            ),
            tests=tests,
            raw_tail=tail,
        )
    # 여러 번 나오면 마지막 것을 쓴다(재시도·중첩 실행).
    exit_code = int(completes[-1])

    def blocked(reason: str) -> Layer3Result:
        return Layer3Result(
            passed=False, failure=reason, exit_code=exit_code, tests=tests, raw_tail=tail
        )

    # ② 종료 코드
    if exit_code != 0:
        return blocked(f"에디터가 0 이 아닌 코드로 끝났다: EXIT CODE {exit_code}.")

    fails = [t for t in tests if t.result == FAIL]
    succ = [t for t in tests if t.result == SUCCESS]

    # ③ 실패한 테스트 — 계약 위반이 아니라 **정상적인 불합격**이므로 failure=None 이다.
    if fails:
        return Layer3Result(
            passed=False, failure=None, exit_code=exit_code, tests=tests, raw_tail=tail
        )

    # ④ 아무것도 돌지 않았으면 통과가 아니다.
    if not succ:
        return blocked(
            f"성공한 테스트가 0건이다(전체 {len(tests)}건). "
            "필터가 아무것도 매치하지 않았거나 전부 실행되지 않았다 — "
            "검증하지 않은 실행을 통과로 세지 않는다."
        )

    return Layer3Result(
        passed=True, failure=None, exit_code=exit_code, tests=tests, raw_tail=tail
    )


def build_command(editor_cmd: str, uproject: str, test_filter: str) -> str:
    """원격에서 실행할 명령 문자열. `-nullrhi` 가 세션 0 구동의 핵심이다."""
    return (
        f'"{editor_cmd}" "{uproject}" '
        f'-ExecCmds="Automation RunTests {test_filter}; Quit" '
        "-unattended -nopause -nosplash -nullrhi -stdout -NoLogTimes"
    )


def run_tests_on_workshop(
    host: str,
    user: str,
    editor_cmd: str,
    uproject: str,
    test_filter: str,
    *,
    runner: Runner = _run,
    timeout: int = DEFAULT_TIMEOUT,
) -> Layer3Result:
    """워크숍에서 층3 을 돌리고 판정한다.

    🔴 **`runner` 의 반환 코드를 보지 않는다.** 판정은 오직 stdout 파싱이다 —
    에디터가 성공해도 `ssh` 가 1 을 내는 것이 실측으로 확인됐다(모듈 독스트링).
    """
    cmd = [
        "ssh", "-o", "BatchMode=yes", f"{user}@{host}",
        build_command(editor_cmd, uproject, test_filter),
    ]
    try:
        proc = runner(cmd, timeout)
    except subprocess.TimeoutExpired:
        return Layer3Result(
            passed=False,
            failure=f"{timeout}초 안에 끝나지 않았다 — 확인 실패이므로 막는다.",
        )
    except OSError as e:
        return Layer3Result(passed=False, failure=f"SSH 실행 실패: {e} — 막는다.")

    # stderr 도 합쳐서 본다. 엔진이 어디로 쓰든 마커만 찾으면 된다.
    return parse_automation_log((proc.stdout or "") + "\n" + (proc.stderr or ""))
