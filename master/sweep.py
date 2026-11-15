"""전수 검사 실행기 (`#965`) — `master/test_*.py` 전부를 병렬 프로세스로 돌리고 합계를 낸다.

    .venv/bin/python -m master.sweep [--jobs N] [--timeout S] [--only 이름...]

종전 `CLAUDE.md` bash 반복문과 **같은 판정**을 한다:

- 판정은 **종료코드**다 — rc≠0 이면 수치가 무엇이든 실패 파일이다(크래시는 수치를 안 찍는다).
- 수치는 형식 A(`N/M 통과`, 마지막 것) → 없으면 형식 B(`통과 N` · `실패 M`)로 읽는다.
- 그 둘로 못 읽는 파일 중 unittest(`Ran N tests` + `OK`)는 형식 C 로 따로 센다 —
  종전 반복문은 이것을 세지 않았으므로 합계를 **A·B 기준**과 **C** 로 나눠 보인다(옛 수치와 대조 가능).
- 셋 다 못 읽으면 「수치 못 읽음」으로 이름을 남긴다.

병렬 개수는 `tests/test-parallel.json` `sweep_jobs`(환경변수 `AX_TEST_JOBS` 가 덮어쓴다, 1 = 순차) —
`--jobs` 가 있으면 그것이 이긴다. 자식은 `-B` 로 돈다(병렬 `__pycache__` 쓰기 경합 방지).
종료 코드: 0 전부 통과 · 1 실패 파일 있음 · 2 사용법.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from master.integration_checks import parallel_jobs  # noqa: E402

DEFAULT_TIMEOUT = 900
SLOWEST = 10
_RE_A = re.compile(r"([0-9]+)/([0-9]+) 통과")
_RE_B_PASS = re.compile(r"통과 ([0-9]+)")
_RE_B_FAIL = re.compile(r"실패 ([0-9]+)")
_RE_C_RAN = re.compile(r"^Ran ([0-9]+) tests? in", re.M)
# `#970` D13 — unittest 의 `OK (expected failures=1, unexpected successes=1)` 처럼 공백이 든 이름도 받는다
_RE_C_OK = re.compile(r"^OK(?: \((?:[a-z_ ]+=[0-9]+(?:, )?)+\))?\s*$", re.M)


def _text(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v or ""


def parse_counts(out: str) -> dict:
    """출력에서 수치를 읽는다 — `{format, passed, total}`; 못 읽으면 format 이 None."""
    a = _RE_A.findall(out)
    if a:
        p, t = a[-1]
        return {"format": "A", "passed": int(p), "total": int(t)}
    bp = _RE_B_PASS.findall(out)
    if bp:
        bf = _RE_B_FAIL.findall(out)
        p = int(bp[-1])
        f = int(bf[-1]) if bf else 0
        return {"format": "B", "passed": p, "total": p + f}
    ran = _RE_C_RAN.findall(out)
    if ran:
        n = int(ran[-1])
        return {"format": "C", "passed": n if _RE_C_OK.search(out) else 0, "total": n}
    return {"format": None, "passed": 0, "total": 0}


def discover(root: Path, only=()) -> list[Path]:
    files = sorted((root / "master").glob("test_*.py"))
    if only:
        names = {n if n.startswith("test_") else f"test_{n}" for n in only}
        names = {n[:-3] if n.endswith(".py") else n for n in names}
        files = [f for f in files if f.stem in names]
    return files


def run_file(path: Path, root: Path, *, python: str, timeout: float, runner=None) -> dict:
    run = runner or subprocess.run
    rel = str(path.relative_to(root))
    t0 = time.monotonic()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = run([python, "-B", str(path)], cwd=str(root), capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=timeout, env=env)
        out, rc = (proc.stdout or "") + "\n" + (proc.stderr or ""), proc.returncode
        reason = "" if rc == 0 else f"rc={rc}"
    except subprocess.TimeoutExpired as e:
        out = _text(e.stdout) + "\n" + _text(e.stderr)     # `#970` D13 — 시간 초과 출력은 bytes 일 수 있다
        rc, reason = None, f"타임아웃 {timeout:g}초"
    except OSError as e:
        out, rc, reason = "", None, f"실행 실패: {type(e).__name__}"
    counts = parse_counts(out)
    return {"path": rel, "rc": rc, "ok": rc == 0, "reason": reason,
            "seconds": time.monotonic() - t0, "tail": out[-3000:], **counts}


def sweep(root: Path = ROOT, *, jobs: int = 1, python: str = "", timeout: float = DEFAULT_TIMEOUT,
          only=(), runner=None, log=None) -> dict:
    log = log or (lambda m: print(m, flush=True))
    files = discover(root, only)
    python = python or sys.executable
    t0 = time.monotonic()
    log(f"[sweep] {len(files)}파일 · 병렬 {jobs} · 파일당 제한 {timeout:g}초")
    results = []
    with ThreadPoolExecutor(max_workers=max(1, jobs), thread_name_prefix="ax-sweep") as pool:
        futures = [pool.submit(run_file, f, root, python=python, timeout=timeout, runner=runner)
                   for f in files]
        for fut in futures:
            r = fut.result()
            results.append(r)
            if not r["ok"]:
                log(f"[sweep] [중요] 실패 {r['path']} — {r['reason']}")
    by_fmt = {"A": [0, 0], "B": [0, 0], "C": [0, 0]}
    unread = []
    for r in results:
        if r["format"] is None:
            unread.append(r["path"])
            continue
        by_fmt[r["format"]][0] += r["passed"]
        by_fmt[r["format"]][1] += r["total"]
    failed = [r for r in results if not r["ok"]]
    ab_pass = by_fmt["A"][0] + by_fmt["B"][0]
    ab_total = by_fmt["A"][1] + by_fmt["B"][1]
    summary = {"files": len(results), "jobs": jobs, "seconds": time.monotonic() - t0,
               "ab_passed": ab_pass, "ab_total": ab_total,
               "c_passed": by_fmt["C"][0], "c_total": by_fmt["C"][1],
               "failed": [r["path"] for r in failed], "unread": unread,
               "slowest": [(r["path"], round(r["seconds"], 1))
                           for r in sorted(results, key=lambda r: -r["seconds"])[:SLOWEST]],
               "results": results}
    if unread:
        log(f"[sweep] [주의] 수치 못 읽음 {len(unread)}파일: {', '.join(unread)}")
    log("[sweep] 가장 느린 파일: " + " · ".join(f"{p} {s}초" for p, s in summary["slowest"]))
    log(f"SWEEP {len(results)}파일 · {ab_pass}/{ab_total} 통과(형식 A·B) · unittest {by_fmt['C'][0]}/"
        f"{by_fmt['C'][1]} · 실패 파일 {len(failed)}개 · {summary['seconds']:.1f}초")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m master.sweep", description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=0, help="병렬 개수(주면 설정·환경변수보다 우선)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="파일당 제한(초)")
    ap.add_argument("--only", nargs="*", default=(), help="이 파일만 (test_ 접두어 생략 가능)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if args.jobs < 0 or args.timeout <= 0:
        print("[sweep] --jobs 는 0 이상, --timeout 은 양수", file=sys.stderr)
        return 2
    if args.jobs:
        jobs, source = args.jobs, "--jobs"
    else:
        setting = parallel_jobs("sweep_jobs", ROOT)
        if setting["reason"]:
            print(f"[sweep] {setting['reason']}", flush=True)
        jobs, source = setting["jobs"], setting["source"]
    print(f"[sweep] 병렬 개수 출처: {source}", flush=True)
    summary = sweep(ROOT, jobs=jobs, timeout=args.timeout, only=args.only)
    for r in summary["results"]:
        if not r["ok"]:
            print(f"\n----- {r['path']} ({r['reason']}) 꼬리 -----\n{r['tail'][-1500:]}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
