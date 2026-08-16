"""층3 검증의 판정 계약 — fail-closed (PLAN §4.3, §5.5.4-⑥-③).

층3 은 **UE5 가 실제로 빌드되고 테스트가 도는가**다. 층2(§9.4.4)가 LLM 판정의 계약이라면
이쪽은 **엔진 로그의 계약**이다. 형태는 같다 — 정확한 신호만 믿고, 없으면 막는다.

[중요] **판정 신호는 이 둘뿐이다** (실측 2026-08-08, `.2` 에서 SSH·세션 0 구동):

    LogAutomationController: Display: Test Completed. Result={Success|Fail} Name={..} Path={..}
    LogAutomationCommandLine: Display: **** TEST COMPLETE. EXIT CODE: N ****

[중요] **틀린 신호 두 개 — 실측으로 걸렀다:**

1. **SSH 종료 코드를 쓰지 마라. 양방향으로 틀린다** (실측 2026-08-08):

   | 실행 | 실제 결과 | `ssh` 종료 코드 |
   |---|---|---|
   | `UnrealEditor-Cmd` (테스트 통과) | 성공 (`EXIT CODE: 0`) | **1** ← 거짓 실패 |
   | `Build.bat` (성공) | `Result: Succeeded` | 0 |
   | `Build.bat` (**실패**) | `Result: Failed (RulesError)` | **0** ← **거짓 성공** |

   마지막 줄이 위험한 쪽이다 — **실패한 빌드를 통과시킨다.** 감싼 배치의 `%ERRORLEVEL%` 는
   빌드에서는 맞았지만(0 vs 8) 에디터 실행에서는 **기록조차 되지 않았다.**
   래퍼로도 메울 수 없으니 **로그를 파싱하는 것 외에 방법이 없다.**
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

[주의] 이 모듈의 초안은 "매치가 없어도 exit 0" 이라고 적었다 — **실측으로 틀린 것이 확인돼
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


def _run(cmd, timeout: int) -> subprocess.CompletedProcess:
    """원격 명령 실행. [중요] **바이트로 받아 우리 디코더로 푼다.**

    [주의] 실측 2026-08-11(골조 게이트 첫 실전 구동에서 터졌다): `text=True` 는 strict UTF-8 이라
    **한국어 윈도우의 UBT 출력에서 `UnicodeDecodeError` 로 죽는다** — 링커가 CP949 로
    *"라이브러리 … 만들고 있습니다"* 를 뱉는다. 판정 문자열(`Result:`)은 ASCII 라 살아 있는데
    **디코딩이 먼저 죽어서 판정 자체에 도달하지 못했다.**

    [중요] `errors="replace"` 로 때우지 않는다 — 그러면 빌드 실패 사유의 한국어가 깨져 **사람이
    로그를 못 읽는다.** 소스 44%가 CP949 라 이미 만들어 둔 `source_text.decode`(UTF-8 → CP949
    → replace)를 그대로 쓴다.
    """
    # [중요] 문자열 명령은 **셸이 그대로 파싱**하게 한다. 첫 로컬 실 구동(.33, #197)에서
    #    리스트로 감싼 `cmd /c "call \"...\""` 가 list2cmdline 의 `\"` 이스케이프로 뭉개져
    #    Build.bat 이 실행조차 안 됐다 — cmd 는 백슬래시 이스케이프를 모른다. SSH 경로가
    #    멀쩡했던 이유도 같다: 원격 셸이 문자열을 그대로 파싱한다. 로컬도 같게 맞춘다.
    if isinstance(cmd, str):
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout, check=False)
    else:
        p = subprocess.run(list(cmd), capture_output=True, timeout=timeout, check=False)
    from .source_text import decode
    return subprocess.CompletedProcess(
        p.args, p.returncode,
        decode(p.stdout or b"").text, decode(p.stderr or b"").text,
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

    [중요] `Error` 문자열도 SSH 종료 코드도 보지 않는다. 위 모듈 독스트링 참조.
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


# ─────────────────────────────────────────
# 빌드 (UnrealBuildTool / Build.bat)
# ─────────────────────────────────────────

# `Result: Succeeded` / `Result: Failed (RulesError)`
_BUILD_RESULT = re.compile(r"^\s*Result:\s*(?P<result>Succeeded|Failed)(?:\s*\((?P<why>[^)]*)\))?",
                           re.MULTILINE)
_BUILD_TIME = re.compile(r"Total execution time:\s*(?P<sec>[\d.]+)\s*seconds")


@dataclass
class BuildResult:
    """빌드 판정. 테스트와 같은 계약 — 정확한 신호만 믿고, 없으면 막는다."""

    passed: bool
    failure: str | None          # None = UBT 가 실제로 판정을 냈다
    result: str = ""             # "Succeeded" | "Failed" | ""
    detail: str = ""             # 실패 사유 태그 (예: RulesError)
    seconds: float | None = None
    raw_tail: str = ""

    def summary(self) -> str:
        if self.passed:
            s = "BUILD OK"
            return f"{s}({self.seconds:.1f}s)" if self.seconds is not None else s
        if self.failure:
            return f"BLOCKED(계약 위반: {self.failure})"
        return f"BUILD FAILED({self.detail})" if self.detail else "BUILD FAILED"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failure": self.failure,
            "result": self.result,
            "detail": self.detail,
            "seconds": self.seconds,
            "summary": self.summary(),
            "raw_tail": self.raw_tail,
        }


def parse_build_log(text: str, *, tail_lines: int = 15) -> BuildResult:
    """UBT 로그에서 빌드 판정을 뽑는다. **순수 함수.**

    [중요] 프로세스 반환 코드를 보지 않는다 — `Build.bat` 이 실패해도 `ssh` 는 0 을 낸다(실측).
    """
    text = text or ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    tail = "\n".join(lines[-tail_lines:])

    t = _BUILD_TIME.search(text)
    seconds = float(t.group("sec")) if t else None

    matches = list(_BUILD_RESULT.finditer(text))
    if not matches:
        return BuildResult(
            passed=False,
            failure=(
                "판정 줄('Result: Succeeded|Failed')이 없다. "
                "UBT 가 시작조차 못 했거나 로그가 잘렸다 — 통과로 취급하지 않는다."
            ),
            seconds=seconds,
            raw_tail=tail,
        )
    m = matches[-1]  # 여러 번이면 마지막
    result = m.group("result")
    why = (m.group("why") or "").strip()

    if result == "Succeeded":
        return BuildResult(passed=True, failure=None, result=result, seconds=seconds, raw_tail=tail)
    # 빌드가 실제로 실패한 것은 계약 위반이 아니다 → failure=None
    return BuildResult(
        passed=False, failure=None, result=result, detail=why, seconds=seconds, raw_tail=tail
    )


def build_build_command(build_bat: str, target: str, uproject: str,
                        *, platform: str = "Win64", config: str = "Development") -> str:
    """Jenkins 등 외부 구동이 쓰는 표준 UBT 호출 형태."""
    return (
        f'call "{build_bat}" {target} {platform} {config} '
        f'-Project="{uproject}" -WaitMutex'
    )


def run_build_on_workshop(
    host: str,
    user: str,
    build_bat: str,
    target: str,
    uproject: str,
    *,
    platform: str = "Win64",
    config: str = "Development",
    runner: Runner = _run,
    timeout: int = DEFAULT_TIMEOUT,
) -> BuildResult:
    """워크숍에서 빌드를 돌리고 판정한다. **반환 코드를 보지 않는다.**"""
    cmd = [
        "ssh", "-o", "BatchMode=yes", f"{user}@{host}",
        build_build_command(build_bat, target, uproject, platform=platform, config=config),
    ]
    try:
        proc = runner(cmd, timeout)
    except subprocess.TimeoutExpired:
        return BuildResult(
            passed=False, failure=f"{timeout}초 안에 끝나지 않았다 — 확인 실패이므로 막는다."
        )
    except OSError as e:
        return BuildResult(passed=False, failure=f"SSH 실행 실패: {e} — 막는다.")
    return parse_build_log((proc.stdout or "") + "\n" + (proc.stderr or ""))


def run_build_local(
    build_bat: str,
    target: str,
    uproject: str,
    *,
    platform: str = "Win64",
    config: str = "Development",
    runner: Runner = _run,
    timeout: int = DEFAULT_TIMEOUT,
) -> BuildResult:
    """**이 기계에서** 빌드를 돌리고 판정한다 (중 2.1 `#135` — 요청자 `.33` 의 검수 빌드).

    [중요] **같은 명령·같은 파서, 전송만 다르다.** `run_build_on_workshop` 과 이 함수는
    `build_build_command` 와 `parse_build_log` 를 **공유한다** — 여기서 명령을 다시 조립하거나
    판정을 다시 쓰면 두 경로가 조용히 갈라진다(`coordinator._git_cmd` 를 공유하는 것과 같은 결).

    [주의] **왜 로컬 판이 필요한가**: 마스터에는 UE5 가 없어 `.2` 로 위임하지만, 요청자 `.33` 은
    자기 검수 worktree 를 **자기 디스크에** 갖고 있다. 거기서 SSH 로 자기 자신에게 붙을 이유가
    없다(사용자 결정 2026-08-16: *".33 로컬 (원전 그대로)"*).

    [중요] **반환 코드를 보지 않는 것도 같다** — `Build.bat` 은 실패해도 0 을 낸 실측이 있다.
    """
    # [중요] 리스트로 감싸지 않는다 — #197 첫 실 구동이 잡은 결함(따옴표 뭉개짐, `_run` 참조)
    cmd = build_build_command(build_bat, target, uproject,
                              platform=platform, config=config)
    try:
        proc = runner(cmd, timeout)
    except subprocess.TimeoutExpired:
        return BuildResult(
            passed=False, failure=f"{timeout}초 안에 끝나지 않았다 — 확인 실패이므로 막는다."
        )
    except OSError as e:
        return BuildResult(passed=False, failure=f"빌드 실행 실패: {e} — 막는다.")
    return parse_build_log((proc.stdout or "") + "\n" + (proc.stderr or ""))


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

    [중요] **`runner` 의 반환 코드를 보지 않는다.** 판정은 오직 stdout 파싱이다 —
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
