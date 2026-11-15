"""testkit_tmp 회귀 (`#970` D14) — 검사가 만든 임시 디렉터리는 프로세스가 끝날 때(예외 포함) 지워진다.

    .venv/bin/python master/test_testkit_tmp.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


CHILD = """
import sys, tempfile
sys.path.insert(0, {root!r})
from master import testkit_tmp
testkit_tmp.track()
testkit_tmp.track()
a = tempfile.mkdtemp(prefix="ax-970-kit-")
with tempfile.TemporaryDirectory(prefix="ax-970-kit-td-") as t:
    pass
print(a, flush=True)
if {boom}:
    raise RuntimeError("단정 실패 흉내")
"""


def _run(boom: bool) -> tuple:
    p = subprocess.run([sys.executable, "-B", "-c", CHILD.format(root=str(ROOT), boom=boom)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, (p.stdout.strip().splitlines() or [""])[0]


def test_cleans_on_normal_exit() -> None:
    rc, path = _run(False)
    check("정상 종료 → 만든 디렉터리가 없다", rc == 0 and path and not Path(path).exists(), f"rc={rc} {path}")


def test_cleans_on_exception() -> None:
    rc, path = _run(True)
    check("예외로 끝나도 → 만든 디렉터리가 없다", rc != 0 and path and not Path(path).exists(), f"rc={rc} {path}")


def test_tracked_files_use_it() -> None:
    """플래그된 검사 파일은 모두 track() 을 부른다 — 빠지면 다시 쌓인다."""
    names = ["client_bundle", "context_synth", "followup", "pystatic", "redmine_completion_gate", "rounds",
             "service_freshness", "signals", "skill_conventions", "sweep", "task_submission"]
    missing = [n for n in names if "testkit_tmp.track()" not in (ROOT / "master" / f"test_{n}.py").read_text(encoding="utf-8")]
    check("D14 대상 검사 파일이 모두 track() 을 부른다", not missing, str(missing))


def main() -> int:
    for fn in (test_cleans_on_normal_exit, test_cleans_on_exception, test_tracked_files_use_it):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_testkit_tmp: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
