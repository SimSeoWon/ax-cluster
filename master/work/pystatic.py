"""`kind: code` ⑦ 통합 검사의 정적 검사 셋 — pyflakes · import (`#804`) · mypy (`#815`). 마스터 전용, 토큰 0.

`followup.code_build_fn` 이 공식 통합 검사·회귀 검사 옆에서 부른다. 이번 라운드가 바꾼 `.py`
(`base_ref..HEAD`, 지운 파일 제외)만 본다.

    pyflakes   막는 것: 문법 오류 · `undefined name` (UndefinedName·UndefinedExport)
               그 밖(미사용 import·변수, 자리표시자 없는 f-string, 재정의 …)은 비차단 노트
    import     파일마다 별도 프로세스 — 프로젝트 python · `-I -B` · 임시 HOME · 트리 루트와
               그 파일의 디렉토리를 sys.path 에 둔다(배달된 독립 스크립트 `hooks/*.py` 가
               형제 `hook_paths` 를 최상위로 import 한다 — 실측 2026-10-11)
    mypy       막는 것: `[call-arg]` 하나 (사용자 결정 `#815`) — 그 밖 코드는 전부 비차단 노트
               (실측: 마스터 209 모듈 309건 중 call-arg 만 진짜 결함, attr-defined·union-attr 76/76 오탐)

[중요] **base 에 이미 있던 결함은 이번 라운드 탓이 아니다** — pyflakes 는 `(파일, 종류, 문구)`
개수를 `git show <base>:<path>` 와 비교하고(줄 번호는 밀리므로 쓰지 않는다), import 는 base 트리
(`git archive`)에서도 실패하면 「기존」으로 적는다. mypy 는 base 트리에서 같은 파일을 다시 돌려
`(파일, 코드, 문구)` 개수로 비교한다. 실측 동기: `master/webui/app.py` 의 기존
`undefined name` 6건(`#812`) — 그 파일을 건드린 조각이 덮어쓰면 안 된다.
[중요] **확인 불가는 통과가 아니다** — pyflakes 가 돌지 못하면(미설치·크래시) `setup_error` 로
실패한다. import 의 「환경」(트리 밖 서드파티가 해석기에 없음)만 차단하지 않고 따로 센다.
"""
from __future__ import annotations

import io
import json
import keyword
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter
from pathlib import Path

PYFLAKES_TIMEOUT = 300
MYPY_TIMEOUT = 600          # 한 번 실행 — 실측 저장소 전체 48초, base 판이 한 번 더 돈다
BLOCKING_MYPY = ("call-arg",)
IMPORT_TIMEOUT = 30
BLOCKING_FLAKES = ("UndefinedName", "UndefinedExport")
_DONE = "@@AX_PYFLAKES_DONE"
_MARK = "@@AX_IMPORT "

# pyflakes 를 라이브러리로 부르되 **별도 프로세스**에서 — 종류(클래스 이름)를 문구 파싱 없이 받는다.
_FLAKES_SRC = r'''
import json, sys
from pyflakes import api, reporter as _r
class R(_r.Reporter):
    def __init__(self):
        pass
    def _emit(self, **d):
        sys.stdout.write(json.dumps(d, ensure_ascii=False) + "\n")
    def unexpectedError(self, filename, msg):
        self._emit(file=filename, cls="UnexpectedError", line=0, msg=str(msg))
    def syntaxError(self, filename, msg, lineno, offset, text):
        self._emit(file=filename, cls="SyntaxError", line=lineno or 0, msg=str(msg))
    def flake(self, m):
        self._emit(file=m.filename, cls=type(m).__name__, line=m.lineno,
                   msg=m.message % m.message_args)
rep = R()
for f in sys.argv[1:]:
    api.checkPath(f, rep)
sys.stdout.write("@@AX_PYFLAKES_DONE\n")
'''

# import 하나 — 결과는 표식 줄 하나로. 모듈이 남긴 스레드에 묶이지 않게 `os._exit`.
_IMPORT_SRC = r'''
import importlib, json, os, sys, traceback
root, d, mod = sys.argv[1:4]
sys.path.insert(0, root)
if d not in sys.path:
    sys.path.append(d)
try:
    importlib.import_module(mod)
    r = {"ok": True}
except BaseException as e:
    r = {"ok": False, "type": type(e).__name__, "msg": str(e)[:500],
         "name": getattr(e, "name", None) if isinstance(e, ImportError) else None,
         "tb": traceback.format_exc()[-1500:]}
sys.stdout.write("\n@@AX_IMPORT " + json.dumps(r, ensure_ascii=False) + "\n")
sys.stdout.flush()
os._exit(0)
'''


class StaticSetupError(RuntimeError):
    """검사 자체를 돌리지 못했다 — 「결함 0」으로 접지 않는다."""


def _default_run(argv, cwd, t, env=None):
    return subprocess.run(argv, cwd=cwd, capture_output=True, timeout=t, env=env)


def _txt(b) -> str:
    return b if isinstance(b, str) else (b or b"").decode("utf-8", "replace")


def py_files(tree, files) -> list:
    """바뀐 경로 중 HEAD 트리에 **있는** `.py` (지운 파일은 볼 것이 없다)."""
    root = Path(tree)
    return [f for f in files if f.endswith(".py") and (root / f).is_file()]


def import_targets(files) -> tuple:
    """`(대상 [(경로, 모듈 이름)], 제외 [사유])`. `tests/` 아래 · `test_*.py` · `__main__.py` 제외,
    패키지의 `__init__.py` 는 그 패키지 import 다. 식별자가 아닌 경로는 모듈 이름이 없다 — 사유를 남긴다."""
    out, skipped = [], []
    for f in files:
        p = Path(f)
        if "tests" in p.parts[:-1] or p.name.startswith("test_") or p.name == "__main__.py":
            continue
        parts = list(p.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts or not all(x.isidentifier() and not keyword.iskeyword(x) for x in parts):
            skipped.append(f"{f}: 모듈 이름으로 import 할 수 없는 경로 — 검사 안 함")
            continue
        out.append((f, ".".join(parts)))
    return out, skipped


# ─────────────────────────────────────────────────────────────
# pyflakes
# ─────────────────────────────────────────────────────────────

def _flakes(root: Path, files, *, python: str, run) -> list:
    """`[{file, cls, line, msg}]`. 돌지 못하면 `StaticSetupError`."""
    if not files:
        return []
    argv = [python, "-I", "-B", "-c", _FLAKES_SRC, *files]
    try:
        r = run(argv, str(root), PYFLAKES_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise StaticSetupError(f"pyflakes 타임아웃 {PYFLAKES_TIMEOUT}초") from None
    except OSError as e:
        raise StaticSetupError(f"pyflakes 실행 실패 — {e}") from None
    so, se = _txt(r.stdout), _txt(r.stderr)
    if r.returncode != 0 or _DONE not in so:
        raise StaticSetupError(f"pyflakes 를 돌리지 못했다 (rc={r.returncode}) — "
                               + (se.strip().splitlines() or ["출력 없음"])[-1][:300])
    found = []
    for ln in so.splitlines():
        if ln.startswith("{"):
            try:
                found.append(json.loads(ln))
            except ValueError:
                raise StaticSetupError(f"pyflakes 출력을 읽지 못했다: {ln[:200]}") from None
    return found


def _blocking(f: dict) -> bool:
    return f.get("cls") in ("SyntaxError", "UnexpectedError") or f.get("cls") in BLOCKING_FLAKES


def _key(f: dict) -> tuple:
    return (f.get("file"), f.get("cls"), f.get("msg"))


def _fmt(f: dict) -> str:
    return f"{f.get('file')}:{f.get('line')}: {f.get('msg')}"


def _git_bytes(root: Path, *args) -> tuple:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return p.returncode, p.stdout, _txt(p.stderr)


def _base_present(root: Path, base_ref: str, files) -> set:
    rc, out, err = _git_bytes(root, "ls-tree", "-r", "--name-only", base_ref, "--", *files)
    if rc != 0:
        raise StaticSetupError(f"`git ls-tree {base_ref}` 실패 — base 를 모른다: {err[:200]}")
    return {ln.strip() for ln in _txt(out).splitlines() if ln.strip()}


def pyflakes_check(tree, base_ref: str, files, *, python: str = "", runner=None,
                   logf=lambda s, m: None) -> dict:
    """바뀐 `.py` 의 pyflakes. 결과 `{ok, files, blocking, preexisting, notes, setup_error, summary}`."""
    root = Path(tree)
    run = runner or _default_run
    py = (python or "").strip() or sys.executable
    targets = py_files(root, files)
    res = {"ok": False, "files": len(targets), "blocking": [], "preexisting": [], "notes": [],
           "setup_error": "", "seconds": 0.0}
    t0 = time.monotonic()
    logf("check", f"pyflakes 시작 — 바뀐 .py {len(targets)}건")
    tmp = None
    try:
        head = _flakes(root, targets, python=py, run=run)
        hb = [f for f in head if _blocking(f)]
        base_cnt = Counter()
        if hb:
            # base 판을 같은 상대 경로로 펼쳐 같은 검사를 한 번 더 — 같은 (파일·종류·문구) 개수만큼은 기존이다
            need = sorted({f["file"] for f in hb})
            present = _base_present(root, base_ref, need)
            tmp = Path(tempfile.mkdtemp(prefix="ax-pyflakes-base-"))
            got = []
            for p in need:
                if p not in present:
                    continue                        # base 에 없던 파일 — 전부 새것이다
                rc, out, err = _git_bytes(root, "show", f"{base_ref}:{p}")
                if rc != 0:
                    raise StaticSetupError(f"`git show {base_ref}:{p}` 실패: {err[:200]}")
                (tmp / p).parent.mkdir(parents=True, exist_ok=True)
                (tmp / p).write_bytes(out)
                got.append(p)
            base_cnt = Counter(_key(f) for f in _flakes(tmp, got, python=py, run=run) if _blocking(f))
        for f in head:
            if not _blocking(f):
                res["notes"].append(_fmt(f))
            elif base_cnt[_key(f)] > 0:
                base_cnt[_key(f)] -= 1
                res["preexisting"].append(_fmt(f))
            else:
                res["blocking"].append(_fmt(f))
        res["ok"] = not res["blocking"]
    except StaticSetupError as e:
        res["setup_error"] = str(e)
        logf("check", f"[중요] pyflakes 확인 불가 — 통과가 아니다: {e}")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    res["seconds"] = round(time.monotonic() - t0, 1)
    for b in res["blocking"]:
        logf("check", f"pyflakes 차단: {b}")
    res["summary"] = ("확인 불가 — " + res["setup_error"] if res["setup_error"] else
                      f"차단 {len(res['blocking'])} · 기존 {len(res['preexisting'])} · "
                      f"노트 {len(res['notes'])} (파일 {res['files']})")
    logf("check", f"pyflakes 끝 — {res['summary']} ({res['seconds']}초)")
    return res


# ─────────────────────────────────────────────────────────────
# import
# ─────────────────────────────────────────────────────────────

def _import_one(root: Path, path: str, mod: str, *, python: str, home: Path, run) -> dict:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
           "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "XDG_CACHE_HOME": str(home / ".cache"), "XDG_DATA_HOME": str(home / ".local/share"),
           "TMPDIR": str(home / "tmp"), "PYTHONIOENCODING": "utf-8"}
    (home / "tmp").mkdir(exist_ok=True)
    d = str((root / path).parent)
    argv = [python, "-I", "-B", "-c", _IMPORT_SRC, str(root), d, mod]
    try:
        r = run(argv, str(home), IMPORT_TIMEOUT, env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "type": "Timeout", "msg": f"import 타임아웃 {IMPORT_TIMEOUT}초", "name": None}
    except OSError as e:
        raise StaticSetupError(f"import 검사 해석기 실행 실패 — {e}") from None
    so = _txt(r.stdout)
    for ln in reversed(so.splitlines()):
        if ln.startswith(_MARK):
            try:
                return json.loads(ln[len(_MARK):])
            except ValueError:
                break
    tail = (_txt(r.stderr).strip().splitlines() or so.strip().splitlines() or ["출력 없음"])[-1]
    return {"ok": False, "type": "NoResult", "msg": f"결과 없이 끝났다 (rc={r.returncode}) — {tail[:300]}",
            "name": None}


def _in_tree(root: Path, path: str, name: str) -> bool:
    top = (name or "").split(".")[0]
    if not top:
        return True
    d = (root / path).parent
    return any(p.exists() for p in (root / top, root / f"{top}.py", d / top, d / f"{top}.py"))


def _environment(root: Path, path: str, r: dict) -> bool:
    """트리 밖 이름이 해석기에 없다 — 서드파티 의존성. 이번 라운드 결함으로 판정하지 않는다."""
    return (r.get("type") in ("ModuleNotFoundError", "ImportError") and bool(r.get("name"))
            and not _in_tree(root, path, r["name"]))


def _base_tree(root: Path, base_ref: str, dest: Path) -> None:
    rc, out, err = _git_bytes(root, "archive", "--format=tar", base_ref)
    if rc != 0:
        raise StaticSetupError(f"`git archive {base_ref}` 실패 — base 를 모른다: {err[:200]}")
    with tarfile.open(fileobj=io.BytesIO(out)) as tf:
        tf.extractall(dest)


def import_check(tree, base_ref: str, files, *, python: str = "", runner=None,
                 logf=lambda s, m: None) -> dict:
    """바뀐 모듈마다 import. 결과 `{ok, checked, blocking, preexisting, environment, skipped, summary}`."""
    # [주의] 절대 경로로 — 자식은 임시 HOME 에서 돌아 상대 경로(`.`)가 엉뚱한 곳을 가리킨다
    #        (실측 2026-10-11: 저장소에서 `.` 로 부르자 `No module named 'master'` 4건 오탐)
    root = Path(tree).resolve()
    run = runner or _default_run
    py = (python or "").strip() or sys.executable
    targets, skipped = import_targets(py_files(root, files))
    res = {"ok": False, "checked": len(targets), "blocking": [], "preexisting": [],
           "environment": [], "skipped": skipped, "setup_error": "", "seconds": 0.0}
    t0 = time.monotonic()
    logf("check", f"import 검사 시작 — 모듈 {len(targets)}건 · 해석기 {py}")
    home = Path(tempfile.mkdtemp(prefix="ax-import-home-"))
    base = None
    try:
        failed = []
        for path, mod in targets:
            r = _import_one(root, path, mod, python=py, home=home, run=run)
            if r.get("ok"):
                continue
            line = f"{path} ({mod}): {r.get('type')}: {r.get('msg')}"
            if _environment(root, path, r):
                res["environment"].append(line + " — 환경(트리 밖 의존성), 검사 안 함")
            else:
                failed.append((path, mod, line))
        if failed:
            base = Path(tempfile.mkdtemp(prefix="ax-import-base-"))
            _base_tree(root, base_ref, base)
            for path, mod, line in failed:
                if (base / path).is_file() and not _import_one(base, path, mod, python=py,
                                                               home=home, run=run).get("ok"):
                    res["preexisting"].append(line + " — base 에서도 실패")
                else:
                    res["blocking"].append(line)
        res["ok"] = not res["blocking"]
    except StaticSetupError as e:
        res["setup_error"] = str(e)
        logf("check", f"[중요] import 검사 확인 불가 — 통과가 아니다: {e}")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        if base:
            shutil.rmtree(base, ignore_errors=True)
    res["seconds"] = round(time.monotonic() - t0, 1)
    for b in res["blocking"]:
        logf("check", f"import 차단: {b}")
    res["summary"] = ("확인 불가 — " + res["setup_error"] if res["setup_error"] else
                      f"차단 {len(res['blocking'])} · 기존 {len(res['preexisting'])} · "
                      f"환경 {len(res['environment'])} (모듈 {res['checked']})")
    logf("check", f"import 검사 끝 — {res['summary']} ({res['seconds']}초)")
    return res


# ─────────────────────────────────────────────────────────────
# mypy (`#815`)
# ─────────────────────────────────────────────────────────────

_re_mypy = re.compile(r"^(?P<file>[^\n:]+):(?P<line>\d+)(?::\d+)?: (?P<sev>error|warning|note): "
                      r"(?P<msg>.*?)(?:  \[(?P<code>[a-z0-9-]+)\])?$")


def parse_mypy(text: str) -> list:
    """`[{file, line, code, msg}]` — `error` 줄만. `note`(정의 위치·안내 링크)는 앞 줄의 덧붙임이라 버린다."""
    found = []
    for ln in (text or "").splitlines():
        m = _re_mypy.match(ln.rstrip("\r"))
        if not m or m["sev"] != "error":
            continue
        found.append({"file": m["file"].replace("\\", "/"), "line": int(m["line"]),
                      "code": m["code"] or "", "msg": m["msg"]})
    return found


def _mypy(root: Path, files, *, python: str, target: str, cache: Path, run) -> tuple:
    """`(오류 [{file, line, code, msg}], 문법 오류로 뺀 파일 [경로])`. 돌지 못하면 `StaticSetupError`.

    [주의] mypy 는 문법 오류를 만나면 rc 2 로 **그 하나만** 내고 멈춘다(실측 1.11.2) — 그 파일을
    빼고 다시 돈다. 문법 오류 판정은 pyflakes 몫이다.
    """
    left, syntax = list(files), []
    while left:
        argv = [python, "-I", "-m", "mypy", "--python-executable", target,
                "--explicit-package-bases", "--follow-imports=silent", "--no-error-summary",
                "--show-error-codes", "--hide-error-context", "--no-color-output",
                "--cache-dir", str(cache), *left]
        try:
            r = run(argv, str(root), MYPY_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise StaticSetupError(f"mypy 타임아웃 {MYPY_TIMEOUT}초") from None
        except OSError as e:
            raise StaticSetupError(f"mypy 실행 실패 — {e}") from None
        so, se = _txt(r.stdout), _txt(r.stderr)
        errs = parse_mypy(so)
        tail = ((se + "\n" + so).strip().splitlines() or ["출력 없음"])[-1][:300]
        if r.returncode == 2:
            bad = {e["file"] for e in errs if e["code"] == "syntax"} & set(left)
            if not errs or not bad or any(e["code"] != "syntax" for e in errs):
                raise StaticSetupError(f"mypy 를 돌리지 못했다 (rc=2) — {tail}")
            syntax += sorted(bad)
            left = [f for f in left if f not in bad]
            continue
        if r.returncode == 1 and not errs:
            raise StaticSetupError(f"mypy 가 rc=1 인데 오류 줄을 읽지 못했다 — {tail}")
        if r.returncode not in (0, 1):
            raise StaticSetupError(f"mypy 를 돌리지 못했다 (rc={r.returncode}) — {tail}")
        want = set(left)
        return [e for e in errs if e["file"] in want], syntax
    return [], syntax


def _mkey(e: dict) -> tuple:
    return (e.get("file"), e.get("code"), e.get("msg"))


def _mfmt(e: dict) -> str:
    return f"{e.get('file')}:{e.get('line')}: {e.get('msg')}  [{e.get('code')}]"


def mypy_check(tree, base_ref: str, files, *, python: str = "", target_python: str = "",
               runner=None, logf=lambda s, m: None) -> dict:
    """바뀐 `.py` 의 mypy. 결과 `{ok, files, blocking, preexisting, notes, codes, syntax_skipped,
    setup_error, seconds, summary}`.

    `python` = mypy 를 돌리는 해석기(마스터, 기본 `sys.executable`) · `target_python` = 타입을 볼
    대상 해석기(`--python-executable`, 기본 `python`). 막는 것은 `BLOCKING_MYPY` 뿐이다.
    """
    root = Path(tree).resolve()
    run = runner or _default_run
    py = (python or "").strip() or sys.executable
    tgt = (target_python or "").strip() or py
    targets = py_files(root, files)
    res = {"ok": False, "files": len(targets), "blocking": [], "preexisting": [], "notes": [],
           "codes": {}, "syntax_skipped": [], "setup_error": "", "seconds": 0.0}
    t0 = time.monotonic()
    logf("check", f"mypy 시작 — 바뀐 .py {len(targets)}건 · 차단 코드 {', '.join(BLOCKING_MYPY)}")
    # [주의] 캐시는 트리 밖 임시 — 검사 트리에 `.mypy_cache` 를 남기지 않는다
    tmp = Path(tempfile.mkdtemp(prefix="ax-mypy-"))
    try:
        head, res["syntax_skipped"] = _mypy(root, targets, python=py, target=tgt,
                                            cache=tmp / "cache-head", run=run)
        hb = [e for e in head if e["code"] in BLOCKING_MYPY]
        base_cnt = Counter()
        if hb:
            # base 트리 전체를 펼쳐 같은 파일을 한 번 더 — 같은 (파일·코드·문구) 개수만큼은 기존이다
            base = tmp / "base"
            base.mkdir()
            _base_tree(root, base_ref, base)
            got = [f for f in targets if (base / f).is_file()]
            berr, _ = _mypy(base, got, python=py, target=tgt, cache=tmp / "cache-base", run=run)
            base_cnt = Counter(_mkey(e) for e in berr if e["code"] in BLOCKING_MYPY)
        for e in head:
            res["codes"][e["code"] or "?"] = res["codes"].get(e["code"] or "?", 0) + 1
            if e["code"] not in BLOCKING_MYPY:
                res["notes"].append(_mfmt(e))
            elif base_cnt[_mkey(e)] > 0:
                base_cnt[_mkey(e)] -= 1
                res["preexisting"].append(_mfmt(e))
            else:
                res["blocking"].append(_mfmt(e))
        res["ok"] = not res["blocking"]
    except StaticSetupError as e:
        res["setup_error"] = str(e)
        logf("check", f"[중요] mypy 확인 불가 — 통과가 아니다: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res["seconds"] = round(time.monotonic() - t0, 1)
    for b in res["blocking"]:
        logf("check", f"mypy 차단: {b}")
    if res["syntax_skipped"]:
        logf("check", f"mypy 문법 오류로 제외(판정은 pyflakes): {', '.join(res['syntax_skipped'])}")
    res["summary"] = ("확인 불가 — " + res["setup_error"] if res["setup_error"] else
                      f"차단 {len(res['blocking'])} · 기존 {len(res['preexisting'])} · "
                      f"노트 {len(res['notes'])} (파일 {res['files']})")
    logf("check", f"mypy 끝 — {res['summary']} ({res['seconds']}초)")
    return res


def run_static(tree, base_ref: str, files, *, python: str = "", flakes_python: str = "",
               runner=None, logf=lambda s, m: None) -> dict:
    """셋 다 — `{"pyflakes": …, "imports": …, "mypy": …}`. pyflakes·mypy 는 마스터 해석기
    (`flakes_python`, 기본 `sys.executable`)로 돌고, import 와 mypy 의 `--python-executable` 은
    **프로젝트** 해석기(`python`)다."""
    return {"pyflakes": pyflakes_check(tree, base_ref, files, python=flakes_python,
                                       runner=runner, logf=logf),
            "imports": import_check(tree, base_ref, files, python=python, runner=runner, logf=logf),
            "mypy": mypy_check(tree, base_ref, files, python=flakes_python, target_python=python,
                               runner=runner, logf=logf)}
