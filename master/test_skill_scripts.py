"""스킬 정적 스크립트(`scripts/conductor.py`) 계약 (`#969` 16 — R251-6·7 · R252-5·9).

결과는 언제나 JSON 한 줄이다 — 정본 함수가 예외를 던져도 `{"ok": false, "error": …}` 와 rc 1.

    .venv/bin/python master/test_skill_scripts.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.work import conductor as C          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _load(skill: str):
    path = ROOT / "master" / "skills" / skill / "scripts" / "conductor.py"
    spec = importlib.util.spec_from_file_location(f"conductor_{skill.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(mod, argv) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mod.main(argv)
    return rc, out.getvalue()


def test_exception_is_one_json_line() -> None:
    saved = (C.snapshot, C.record_master, C.set_worker, C.set_work_worker_mode)

    def boom(*a, **k):
        raise OSError("상태 파일을 못 읽었다")
    try:
        C.snapshot = C.record_master = C.set_worker = C.set_work_worker_mode = boom
        cases = (("ax-handoff", ["snapshot"]),
                 ("ax-handoff", ["record-master", "claude", "--why", "w"]),
                 ("ax-mode", ["snapshot"]),
                 ("ax-mode", ["set-worker", "lane", "--why", "w"]))
        for skill, argv in cases:
            try:
                rc, text = _run(_load(skill), argv)
                lines = [ln for ln in text.splitlines() if ln.strip()]
                data = json.loads(lines[-1]) if lines else {}
                got = (rc, len(lines), data.get("ok"), "상태 파일" in str(data.get("error")))
            except Exception as e:                       # noqa: BLE001
                got = f"{type(e).__name__}: {e}"
            check(f"16 {skill} {argv[0]} 예외 → JSON 한 줄 · ok false · rc 1", got == (1, 1, False, True), str(got))
    finally:
        C.snapshot, C.record_master, C.set_worker, C.set_work_worker_mode = saved


def main() -> int:
    test_exception_is_one_json_line()
    print(f"{'OK' if not FAIL else 'FAIL'} test_skill_scripts: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
