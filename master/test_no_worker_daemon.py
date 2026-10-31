"""🔴 워커 상주 데몬이 되살아나면 여기서 막는다 (사용자 결정 2026-10-31, `#860`·`#861`).

워커·요청자에 상주 데몬은 없다 — 서버(.57)가 SSH 로 총괄한다. `#320`(08-27)이 걷은 상주를
`#404`(09-12)가 build 전용으로 되살렸고, 2026-10-31 `#857` T4 가 그 복원을 「기존 자산」으로
다시 써서 되돌아갔다. 메모리·문서는 무시하면 그만이므로 **기계가 막는다**
(`test_no_integrator.py` 와 같은 방식).

계약:

    ① 지운 모듈 넷(`work/worker_daemon.py`·`work/ax_safety.py`·`work/buildjob.py`·
       `test_worker_daemon.py`)이 저장소에 **없다**
    ② 어느 역할의 페이로드에도 그 모듈이 **없다** (배달 표 `PAYLOAD_BY_ROLE`)
    ③ 프로덕션 코드(`master/`·`client/`)가 그 모듈을 **import 하지 않는다**
    ④ 이미 배달된 사본을 지우는 선언(`spec.DEPRECATED_PAYLOAD`)이 **살아 있다**

[주의] 이름을 **설명 주석**으로 인용하는 것은 막지 않는다 — 지운 이유를 남기는 것이 필요하다.

`.venv/bin/python -B master/test_no_worker_daemon.py`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 저장소 루트
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0
GONE_FILES = ("master/work/worker_daemon.py", "master/work/ax_safety.py",
              "master/work/buildjob.py", "master/test_worker_daemon.py")
GONE_MODULES = ("worker_daemon", "ax_safety", "buildjob")
GONE_PAYLOAD = ("work/worker_daemon.py", "work/ax_safety.py", "work/buildjob.py")
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+[\w.]*\s+import\s+.*\b(?P<a>" + "|".join(GONE_MODULES) + r")\b"
    r"|from\s+[\w.]*\b(?P<b>" + "|".join(GONE_MODULES) + r")\b\s+import"
    r"|import\s+[\w.]*\b(?P<c>" + "|".join(GONE_MODULES) + r")\b)")
_DYNAMIC_RE = re.compile(r"""import_module\(\s*['"][\w.]*(""" + "|".join(GONE_MODULES)
                         + r""")['"]""")


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _prod_py():
    for base in (ROOT / "master", ROOT / "client"):
        for p in sorted(base.rglob("*.py")):
            if p.name.startswith("test_") or "__pycache__" in p.parts:
                continue
            yield p


def test_files_are_gone() -> None:
    for rel in GONE_FILES:
        check(f"[중요] 지운 파일이 없다: {rel}", not (ROOT / rel).exists())


def test_no_payload_entry() -> None:
    from master.client import bundle
    for role, pairs in bundle.PAYLOAD_BY_ROLE.items():
        hits = [f"{d}<-{s}" for d, s in pairs
                if any(d.endswith(g) or s.endswith(g) for g in GONE_PAYLOAD)]
        check(f"[중요] {role} 페이로드에 데몬 폐포가 없다", not hits, ", ".join(hits))


def test_no_import_in_production() -> None:
    hits = []
    for p in _prod_py():
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = ln.split("#")[0]
            if _IMPORT_RE.search(code) or _DYNAMIC_RE.search(code):
                hits.append(f"{p.relative_to(ROOT)}:{i}")
    check("[중요] 프로덕션 코드가 지운 모듈을 import 하지 않는다", not hits, " · ".join(hits[:6]))


def test_regex_catches_revival() -> None:
    """가드가 실제로 무는지 — 막아야 할 모양을 가드 정규식에 직접 넣어 본다."""
    for bad in ("from master.work import buildjob, infer",
                "from master.work.worker_daemon import main",
                "    from . import ax_safety",
                "import master.work.buildjob as bj",
                "from axmaster.work.worker_daemon import main as _pkg_main"):
        check(f"가드가 잡는다: {bad.strip()}", bool(_IMPORT_RE.search(bad)))
    for ok in ("from master.client import bundle",
               "def ensure_worker_daemon(project):",
               'DEPRECATED_PAYLOAD = ("work/worker_daemon.py",)'):
        check(f"가드가 오탐하지 않는다: {ok}", not _IMPORT_RE.search(ok))


def test_retired_payload_stays_declared() -> None:
    from master.client import bundle, spec
    want = {"work/worker_daemon.py", "work/ax_safety.py"}
    check("[중요] 폐기 페이로드 선언이 살아 있다 (이미 배달된 사본을 지운다)",
          want <= set(spec.DEPRECATED_PAYLOAD), str(spec.DEPRECATED_PAYLOAD))
    for role in bundle.PAYLOAD_BY_ROLE:
        check(f"{role} 기계에서 지울 목록에 둘 다 든다",
              want <= set(bundle.retired_payload_for(role)),
              str(bundle.retired_payload_for(role)))


if __name__ == "__main__":
    for fn in (test_files_are_gone, test_no_payload_entry, test_no_import_in_production,
               test_regex_catches_revival, test_retired_payload_stays_declared):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_no_worker_daemon: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
