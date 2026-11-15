"""master.sweep 회귀 (`#965`) — 수치 형식 A·B·C · rc 판정 · 병렬 · 타임아웃 · CLI 설정 출처.

실제 자식 프로세스는 임시 디렉터리의 가짜 검사 파일로만 돌린다(실 저장소 전수를 돌리지 않는다).
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import testkit_tmp  # noqa: E402 — `#970` D14: 만든 임시 디렉터리를 끝날 때 지운다
testkit_tmp.track()
from master import sweep as S  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_parse_counts() -> None:
    c = S.parse_counts("x\n3/4 통과\n...\n10/10 통과\n")
    check("형식 A 는 마지막 것", c == {"format": "A", "passed": 10, "total": 10}, str(c))
    c = S.parse_counts("통과 5\n통과 7 · 실패 2\n")
    check("형식 B 통과+실패", c == {"format": "B", "passed": 7, "total": 9}, str(c))
    c = S.parse_counts("통과 4\n")
    check("형식 B 실패 없음", c == {"format": "B", "passed": 4, "total": 4}, str(c))
    c = S.parse_counts("A 가 B 보다 먼저: 통과 1\n2/3 통과\n")
    check("A 가 있으면 A", c["format"] == "A" and c["total"] == 3, str(c))
    c = S.parse_counts("....\nRan 12 tests in 0.5s\n\nOK (skipped=1)\n")
    check("형식 C unittest OK", c == {"format": "C", "passed": 12, "total": 12}, str(c))
    c = S.parse_counts("Ran 3 tests in 0.1s\n\nFAILED (failures=1)\n")
    check("형식 C FAILED 는 통과 0", c == {"format": "C", "passed": 0, "total": 3}, str(c))
    c = S.parse_counts("아무 수치 없음\n")
    check("못 읽으면 format None", c["format"] is None, str(c))


def _fixture(files: dict) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ax-sweep-test-"))
    (root / "master").mkdir()
    for name, code in files.items():
        (root / "master" / name).write_text(code, encoding="utf-8")
    return root


def test_sweep_real_children() -> None:
    root = _fixture({
        "test_a.py": "print('5/5 통과')\n",
        "test_b.py": "print('통과 3 · 실패 0')\n",
        "test_c.py": "import unittest\nclass T(unittest.TestCase):\n    def test_x(self): pass\n"
                     "unittest.main()\n",
        "test_crash.py": "print('9/9 통과')\nraise SystemExit(3)\n",
        "test_none.py": "print('hello')\n",
        "helper.py": "raise SystemExit(1)\n",
    })
    logs = []
    s = S.sweep(root, jobs=3, python=sys.executable, timeout=60, log=logs.append)
    check("test_*.py 만 대상", s["files"] == 5, str(s["files"]))
    check("A·B 합계(크래시 파일 수치도 종전처럼 더함)",
          (s["ab_passed"], s["ab_total"]) == (17, 17), str((s["ab_passed"], s["ab_total"])))
    check("unittest 는 따로", (s["c_passed"], s["c_total"]) == (1, 1), str((s["c_passed"], s["c_total"])))
    check("rc≠0 은 수치가 있어도 실패", s["failed"] == ["master/test_crash.py"], str(s["failed"]))
    check("수치 못 읽음 목록", s["unread"] == ["master/test_none.py"], str(s["unread"]))
    check("SWEEP 요약 줄", any(m.startswith("SWEEP 5파일 · 17/17 통과(형식 A·B) · unittest 1/1 · 실패 파일 1개")
                               for m in logs), "\n".join(logs))
    check("실패 로그 줄", any("[중요] 실패 master/test_crash.py — rc=3" in m for m in logs), "\n".join(logs))
    check("시작 로그에 병렬 개수", any(m.startswith("[sweep] 5파일 · 병렬 3") for m in logs), logs[0])
    only = S.sweep(root, jobs=1, python=sys.executable, timeout=60, only=["a", "test_b.py"],
                   log=lambda m: None)
    check("--only 는 접두어·확장자 생략 가능", only["files"] == 2 and not only["failed"], str(only["files"]))


def test_parallel_is_actually_parallel() -> None:
    root = _fixture({f"test_s{i}.py": "import time\ntime.sleep(1)\nprint('1/1 통과')\n" for i in range(4)})
    t0 = time.monotonic()
    s = S.sweep(root, jobs=4, python=sys.executable, timeout=60, log=lambda m: None)
    took = time.monotonic() - t0
    check("4파일 1초씩 · 병렬 4 는 순차(4초)보다 확실히 짧다", took < 3.0 and s["ab_passed"] == 4, f"{took:.1f}s")


def test_timeout_and_child_env() -> None:
    root = _fixture({
        "test_slow.py": "import time\ntime.sleep(5)\nprint('1/1 통과')\n",
        "test_env.py": "import os, sys\nassert os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'\n"
                       "assert sys.flags.dont_write_bytecode\nprint('1/1 통과')\n",
    })
    s = S.sweep(root, jobs=2, python=sys.executable, timeout=1, log=lambda m: None)
    slow = next(r for r in s["results"] if r["path"].endswith("test_slow.py"))
    check("타임아웃은 실패 · 사유", not slow["ok"] and slow["reason"].startswith("타임아웃"), str(slow["reason"]))
    env = next(r for r in s["results"] if r["path"].endswith("test_env.py"))
    check("자식은 -B · PYTHONDONTWRITEBYTECODE", env["ok"], env["tail"][-300:])
    check("__pycache__ 를 만들지 않는다", not list(root.rglob("__pycache__")))


def test_unittest_ok_variants_and_timeout_bytes_970() -> None:
    """`#970` D13 (R422-3·4 · R416-1·2) — `OK (expected failures=N)` 도 읽고, 시간 초과의 bytes 출력도 버리지 않는다."""
    c = S.parse_counts("Ran 4 tests in 0.2s\n\nOK (skipped=1, expected failures=1)\n")
    check("D13 expected failures 가 있어도 통과로 읽는다", c == {"format": "C", "passed": 4, "total": 4}, str(c))
    c = S.parse_counts("Ran 2 tests in 0.2s\n\nOK (unexpected successes=1)\n")
    check("D13 unexpected successes 도 읽는다", c["passed"] == 2, str(c))

    def runner(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1, output=b"3/9 \xed\x86\xb5\xea\xb3\xbc\n", stderr=b"boom\n")
    r = S.run_file(Path(__file__), Path(__file__).resolve().parents[1], python=sys.executable, timeout=1,
                   runner=runner)
    check("D13 시간 초과의 bytes 출력이 꼬리에 남는다", "boom" in r["tail"] and "통과" in r["tail"], r["tail"])


def test_cli_setting_source() -> None:
    """CLI 는 실제 저장소 설정을 읽는다 — `--only` 로 이 파일 하나(재귀 방지: 가벼운 대상)만."""
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, AX_TEST_JOBS="2")
    p = subprocess.run([sys.executable, "-B", "-m", "master.sweep", "--only", "test_verdict"],
                       cwd=str(repo), capture_output=True, text=True, env=env, timeout=120)
    check("CLI rc0", p.returncode == 0, p.stdout[-500:] + p.stderr[-500:])
    check("환경변수 출처를 찍는다", "병렬 개수 출처: env AX_TEST_JOBS" in p.stdout, p.stdout[-500:])
    check("병렬 2", "병렬 2" in p.stdout, p.stdout[-500:])
    env["AX_TEST_JOBS"] = "zero"
    p = subprocess.run([sys.executable, "-B", "-m", "master.sweep", "--only", "test_verdict"],
                       cwd=str(repo), capture_output=True, text=True, env=env, timeout=120)
    check("잘못된 값은 사유를 찍고 순차", "양의 정수가 아니다" in p.stdout and "병렬 1" in p.stdout,
          p.stdout[-500:])
    p = subprocess.run([sys.executable, "-B", "-m", "master.sweep", "--jobs", "-1"],
                       cwd=str(repo), capture_output=True, text=True, timeout=60)
    check("--jobs 음수는 rc2", p.returncode == 2, str(p.returncode))


def main() -> int:
    for t in (test_parse_counts, test_sweep_real_children, test_parallel_is_actually_parallel,
              test_timeout_and_child_env, test_unittest_ok_variants_and_timeout_bytes_970, test_cli_setting_source):
        t()
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
