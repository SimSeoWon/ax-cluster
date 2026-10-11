"""`work/pystatic.py` 계약 테스트 (`#804`) — ⑦ code 판 정적 검사 pyflakes · import.

[중요] 임시 git 저장소에서 **실제로** 돈다 — `git show <base>`·`git archive`·별도 프로세스 import
를 대역 없이 밟는다(주입만으로는 계약만 잰다). pyflakes 미설치는 시스템 `python3`(pyflakes 없음)로 잰다.

실행: .venv/bin/python -B master/test_pystatic.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import followup as F       # noqa: E402
from master.work import pystatic as PS      # noqa: E402
from master.work import review as R         # noqa: E402

PASS = FAIL = 0


def check(name: str, cond, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def _write(d: Path, files: dict) -> None:
    for rel, body in files.items():
        p = d / rel
        if body is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _repo(base: dict, head: dict) -> Path:
    """base 커밋(브랜치 `basebr`) → head 커밋. `None` 값은 head 에서 지운다."""
    d = Path(tempfile.mkdtemp(prefix="ps-"))
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    _write(d, {"pkg/__init__.py": "", "README.md": "x\n", **base})
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    _git(d, "branch", "basebr")
    _write(d, head)
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "head")
    return d


def _run(d: Path, **kw) -> dict:
    files = F.changed_files(d, "basebr")
    return PS.run_static(d, "basebr", files, **kw)


def test_pyflakes_blocking_and_baseline():
    d = _repo({"pkg/old.py": "def f():\n    return missing_a\n",
               "pkg/twice.py": "def f():\n    return gone\n"},
              {"pkg/old.py": "# 줄이 밀린다\n\n\ndef f():\n    return missing_a\n\nX = 1\n",
               "pkg/twice.py": "def f():\n    return gone\n\n\ndef g():\n    return gone\n",
               "pkg/new.py": "import os\n\n\ndef h():\n    v = 1\n    return f'x' + undefined_b\n",
               "pkg/broken.py": "def (:\n"})
    try:
        lines = []
        r = PS.pyflakes_check(d, "basebr", F.changed_files(d, "basebr"),
                              logf=lambda s, m: lines.append(m))
        blk = "\n".join(r["blocking"])
        check("새 undefined name → 차단", "pkg/new.py" in blk and "undefined_b" in blk, blk)
        check("문법 오류 → 차단", "pkg/broken.py" in blk, blk)
        check("[중요] base 에 있던 undefined name 은 차단 아님 (줄이 밀려도)",
              "missing_a" not in blk and any("missing_a" in x for x in r["preexisting"]), str(r))
        check("같은 이름이 하나 더 생기면 그 하나만 차단 (개수 비교)",
              sum("gone" in x for x in r["blocking"]) == 1
              and sum("gone" in x for x in r["preexisting"]) == 1, str(r))
        notes = "\n".join(r["notes"])
        check("미사용 import·변수·f-string 은 비차단 노트",
              "'os' imported but unused" in notes and "never used" in notes
              and "placeholders" in notes, notes)
        check("차단이 있으면 ok=False", r["ok"] is False and not r["setup_error"])
        check("로그: 시작·끝·차단 줄", any(m.startswith("pyflakes 시작") for m in lines)
              and any(m.startswith("pyflakes 끝") and "차단 3" in m for m in lines)
              and any(m.startswith("pyflakes 차단:") for m in lines), str(lines))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_pyflakes_clean_and_deleted():
    d = _repo({"pkg/gone.py": "def f():\n    return nope\n"},
              {"pkg/gone.py": None, "pkg/ok.py": "import os\nX = os.sep\n"})
    try:
        r = PS.pyflakes_check(d, "basebr", F.changed_files(d, "basebr"))
        check("지운 파일은 보지 않고 깨끗하면 통과", r["ok"] is True and r["files"] == 1
              and not r["blocking"], str(r))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_pyflakes_unavailable_is_loud_failure():
    d = _repo({}, {"pkg/a.py": "X = 1\n"})
    try:
        files = F.changed_files(d, "basebr")
        # pyflakes 없는 해석기가 내는 그대로 — 실물(`/usr/bin/python3`, 마스터 실측 미설치)이
        # 있으면 그것도 잰다. 다른 기계에서 이 검사가 돌아도 판정이 같게 대역을 함께 둔다.
        class NoMod:
            returncode, stdout = 1, ""
            stderr = "ModuleNotFoundError: No module named 'pyflakes'\n"
        lines = []
        r = PS.pyflakes_check(d, "basebr", files, runner=lambda a, c, t, env=None: NoMod(),
                              logf=lambda s, m: lines.append(m))
        check("[중요] pyflakes 없음 → 확인 불가 = 실패", r["ok"] is False
              and "pyflakes" in r["setup_error"] and "확인 불가" in r["summary"], str(r))
        check("  로그가 [중요] 로 크게 남는다", any("[중요] pyflakes 확인 불가" in m for m in lines))
        sys_py = "/usr/bin/python3"
        if Path(sys_py).is_file() and subprocess.run([sys_py, "-c", "import pyflakes"],
                                                      capture_output=True).returncode != 0:
            rr = PS.pyflakes_check(d, "basebr", files, python=sys_py)
            check("[중요] 실물 — pyflakes 없는 python3 → 실패",
                  rr["ok"] is False and "No module named 'pyflakes'" in rr["setup_error"], str(rr))
        r2 = PS.pyflakes_check(d, "basebr", files, python="/nonexistent/python")
        check("[중요] 해석기 없음 → 실패", r2["ok"] is False and "실행 실패" in r2["setup_error"], str(r2))

        class Crash:
            returncode, stdout, stderr = 0, "", "Segmentation fault"
        r3 = PS.pyflakes_check(d, "basebr", files, runner=lambda a, c, t, env=None: Crash())
        check("[중요] 완료 표식 없음(크래시) → 실패", r3["ok"] is False and r3["setup_error"], str(r3))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_import_rules():
    real_home = os.path.expanduser("~")
    d = _repo({"pkg/old_bad.py": "raise RuntimeError('base 에서도 죽는다')\n",
               "pkg/was_ok.py": "X = 1\n"},
              {"pkg/old_bad.py": "Y = 2\nraise RuntimeError('여전히 죽는다')\n",
               "pkg/was_ok.py": "X = 1\nraise ValueError('이번 라운드가 깼다')\n",
               "pkg/new_bad.py": "from pkg import nothere_mod\n",
               "pkg/sub/__init__.py": "import pkg.sub.missing_in_tree\n",
               "pkg/third.py": "import torch_not_installed_xyz\n",
               "pkg/home.py": (f"import os\nassert os.environ['HOME'] != {real_home!r}\n"
                               "assert 'PYTHONPATH' not in os.environ\n"),
               "pkg/hooks/hook_paths.py": "P = 1\n",
               "pkg/hooks/on_stop.py": "import hook_paths\nX = hook_paths.P\n",
               "pkg/test_x.py": "raise SystemExit('test 는 import 하지 않는다')\n",
               "tests/integration/helper.py": "raise SystemExit('tests/ 는 import 하지 않는다')\n",
               "pkg/__main__.py": "raise SystemExit('__main__ 은 import 하지 않는다')\n",
               "my-tool/run.py": "X = 1\n"})
    try:
        lines = []
        r = PS.import_check(d, "basebr", F.changed_files(d, "basebr"),
                            logf=lambda s, m: lines.append(m))
        blk = "\n".join(r["blocking"])
        check("base 에서 되던 것이 깨지면 차단", "pkg/was_ok.py" in blk, blk)
        check("새 파일의 트리 안 이름 import 실패 → 차단", "pkg/new_bad.py" in blk, blk)
        check("패키지 __init__ 도 import 하고 트리 안 누락은 차단", "pkg/sub/__init__.py" in blk, blk)
        check("[중요] base 에서도 실패 → 기존(차단 아님)", "old_bad" not in blk
              and any("pkg/old_bad.py" in x for x in r["preexisting"]), str(r))
        check("트리 밖 서드파티 누락 → 환경, 차단 아님", "third" not in blk
              and any("torch_not_installed_xyz" in x for x in r["environment"]), str(r))
        check("격리 HOME · PYTHONPATH 없음", "home.py" not in blk, blk)
        check("hooks 형제 import 는 디렉토리를 sys.path 에 두어 통과", "on_stop" not in blk, blk)
        check("tests/·test_*·__main__ 은 import 대상이 아님",
              not any(x in blk for x in ("test_x", "helper", "__main__")), blk)
        check("식별자 아닌 경로는 사유를 남기고 건너뛴다",
              any("my-tool/run.py" in x for x in r["skipped"]), str(r["skipped"]))
        check("차단 수가 정확하다", len(r["blocking"]) == 3 and r["ok"] is False, str(r["blocking"]))
        check("로그: 시작·끝·차단", any(m.startswith("import 검사 시작") for m in lines)
              and any(m.startswith("import 검사 끝") and "차단 3" in m and "환경 1" in m for m in lines)
              and any(m.startswith("import 차단:") for m in lines), str(lines))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_import_clean_passes():
    d = _repo({}, {"pkg/a.py": "import json\nX = json.dumps(1)\n"})
    try:
        r = PS.import_check(d, "basebr", F.changed_files(d, "basebr"))
        check("깨끗한 모듈은 통과", r["ok"] is True and r["checked"] == 1, str(r))
        cwd = os.getcwd()
        try:
            os.chdir(d)
            rr = PS.import_check(Path("."), "basebr", F.changed_files(d, "basebr"))
        finally:
            os.chdir(cwd)
        check("상대 경로 트리(`.`)로 불러도 통과 — 실측 오탐 회귀", rr["ok"] is True, str(rr))
        r2 = PS.import_check(d, "basebr", F.changed_files(d, "basebr"), python="/nonexistent/py")
        check("[중요] import 해석기 없음 → 확인 불가 = 실패", r2["ok"] is False and r2["setup_error"],
              str(r2))
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Ok:
    stdout, stderr, returncode = "", "test_a ... ok\n\n----\nRan 2 tests in 0.1s\n\nOK\n", 0


def test_code_build_fn_wiring():
    d = _repo({}, {"tests/integration/test_axcluster.py": "", "pkg/a.py": "def f():\n    return nope\n"})
    try:
        lines = []
        res = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: _Ok(),
                              logf=lambda s, m: lines.append(m))(d)
        ok, note = R.build_verdict(res)
        check("[중요] 정적 차단 → ⑦ 통과 아님", ok is False and "정적 실패" in note, note)
        check("  실패 사유가 정적 검사", "정적 검사 실패" in (res.get("failure") or ""), str(res.get("failure")))
        cc = F.check_counts(res)
        it = {i["name"]: i for i in cc["items"]}
        check("check_counts 에 정적 항목 둘", "정적 pyflakes" in it and "정적 import" in it, str(it))
        check("  pyflakes 항목 실패 + 차단 사유를 꼬리로", it["정적 pyflakes"]["ok"] is False
              and "undefined name 'nope'" in it["정적 pyflakes"].get("tail", ""), str(it))
        check("  import 항목은 통과", it["정적 import"]["ok"] is True)
        txt = F.render({"work_id": "w1", "round": 1, "state": "at_gate", "build_passed": False,
                        "checks": cc, "merged": ["x"]})
        check("렌더(⑦ 고지·노트)에 막힌 사유가 보인다", "undefined name 'nope'" in txt, txt)
        check("로그에 정적 검사 줄", any("pyflakes 차단" in m for m in lines))

        _write(d, {"pkg/a.py": "def f():\n    return 1\n"})
        _git(d, "commit", "-qam", "fix")
        res2 = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: _Ok())(d)
        check("고치면 통과", R.build_verdict(res2)[0] is True, str(res2.get("summary")))

        bad = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: _Ok(),
                              static_fn=lambda t, f, lf: PS.run_static(t, "basebr", f,
                                                                       flakes_python="/nonexistent/python"))(d)
        check("[중요] pyflakes 확인 불가 → ⑦ 통과 아님", R.build_verdict(bad)[0] is False,
              str(bad.get("summary")))

        def boom(t, f, lf):
            raise RuntimeError("x")
        bad2 = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: _Ok(), static_fn=boom)(d)
        check("[중요] 정적 검사 예외 → 통과 아님", R.build_verdict(bad2)[0] is False)
        bad3 = F.code_build_fn(base_ref="no-such-ref", runner=lambda a, c, t: _Ok())(d)
        check("[중요] 바뀐 파일 모름 → 정적도 확인 불가", (bad3["static"]["pyflakes"].get("ok") is False
                                                  and R.build_verdict(bad3)[0] is False))
        off = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: _Ok(), static=False)(d)
        check("static=False 면 정적 항목 없음", off["static"] == {}
              and not any(i["name"].startswith("정적") for i in F.check_counts(off)["items"]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    for fn in (test_pyflakes_blocking_and_baseline,
               test_pyflakes_clean_and_deleted,
               test_pyflakes_unavailable_is_loud_failure,
               test_import_rules,
               test_import_clean_passes,
               test_code_build_fn_wiring):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_pystatic: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
