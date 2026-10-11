"""라운드 종결 뒤 ⑦ 준비를 **한 입구**로 묶는다 — Claude·Codex 요청자 세션 공용 (`#798`).

## 왜 있나

분산 work 의 조각이 전부 끝나면(`merge_status` 가 `ready_for_review` · `rejected` · `cancelled`)
요청자 세션은 ⑦ 준비를 해야 한다: 큐에서 work 를 다시 읽고 → 이번 라운드 서브 브랜치를
격리 트리에 모아 → 타입별 통합 검사를 **한 번** 돌리고 → 「버그냐 구조 수정이냐」 사람 게이트에서
**멈춘다.** 종전에는 그 순서를 모델이 기억해야 했고, Codex 세션이 완료 고지를 보고 그냥 멈췄다.
[중요] 필수 과정은 절차서가 아니라 파이썬이 강제한다 — 그래서 여기 한 함수다.

## [중요] 이것은 통합자가 아니다

이 모듈을 부르는 것은 둘이다 — **요청자 세션**(CLI) 과 **`ax-followup.timer`**(1분, `--scan`).
마스터에서는 훅을 쓰지 않는다(사용자 결정 2026-10-11, `#798`) — 수신은 타이머 하나다.
하는 일은 `review.advance_work(confirm=False, keep_tree=True)` 까지이고, 그 뒤(전진·finalize)는
사람의 답이 트리거다. 삭제된 「통합자」는 서버가 durable 에 **머지**했다 — 이 모듈은 격리
worktree 에서 검사만 하고 사람 게이트에서 멈추며, `master/test_no_integrator.py` 가 그 부활을 막는다.

    confirm=True 를 넘기지 않는다 · push 하지 않는다 · `main` 을 만지지 않는다

## 타입별 통합 검사 (`build_fn(tree) -> dict` — `review.build_verdict` 가 읽는 계약)

    unreal       `build_local.local_build_fn` 에 그대로 맡긴다 (다시 만들지 않는다)
    code         공식 통합 검사 + 이번 라운드가 건드린 파일의 회귀 검사 (`code_build_fn`)
    index_only   거절 — 분산 작업을 받지 않는 타입이다

원전 대조 (`~/AgentTest/mcp/master_orchestrator/executor_integration_build.py:17` 읽음,
2026-10-11): 원전 `integration_build_impl` 은 ① UE 빌드 → ② **빌드가 통과하면** 그 work 에 묶인
테스트 필터(`collect_work_test_filters`)를 돌리고 → `gate_passed = build_passed and tests_passed`.
[중요] **「통합 검사 + 이 work 에 해당하는 테스트, 둘 다 통과해야 게이트 통과」를 따른다.**
따르지 않는 셋: 원전은 서버 저장소에서 `checkout` 하고(우리는 격리 worktree — `review.py` 머리말),
`auto_flip` 으로 큐 상태·Redmine 을 직접 쓰고(여기는 큐에 쓰지 않는다), 테스트 인프라 미가용을
fail-open 으로 넘긴다(code 판은 **fail-closed** — 못 돌린 것은 통과가 아니다).

## 대기 입구 — 「준비」와 「묻기」는 다른 자리다 (`#798` ①, 사용자 결정 2026-10-11)

마스터에서는 훅을 쓰지 않는다. **준비는 타이머**(`--scan`)가 하고, **세션에 알리는 것은
`--wait`** 다: 등재 응답(`register_work_tool` 의 `wait`)이 이 명령을 싣고, 세션이 그것을
등재 직후 백그라운드로 돌려 두면 이번 라운드의 준비 결과(at_gate·stopped·error)·work 종결·
타임아웃에서 결과 블록(`render` 와 같은 문구)을 찍고 끝난다 — 그 종료가 세션을 깨운다.
`--wait` 는 순수 읽기다(준비·전진·상태 기록 없음).

`.venv/bin/python -m master.work.followup <work_id> [--repo PATH] [--python PY]`
`.venv/bin/python -m master.work.followup --scan --project AXCluster --repo PATH`   (타이머)
`.venv/bin/python -m master.work.followup <work_id> --wait --repo PATH [--interval S] [--timeout S]`
    종료 코드: 0 at_gate · 3 stopped/error/terminal_*/merged · 4 timeout · 2 사용법
"""
from __future__ import annotations

import json
import re as _re_mod
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import coordinator as C
from . import review as R
from .build_local import BuildSetupError, parse_unittest

# ── 상태 이름 — 큐의 값 그대로 (`task_queue/logic_lifecycle.py`) ────────────────────────
READY = "ready_for_review"
STOP_STATES = ("rejected", "cancelled", "merged")
TASK_TERMINAL = ("verified", "failed", "cancelled")
TASK_BAD = ("failed", "cancelled")
KINDS = ("unreal", "code", "index_only")

# ── code 판 공식 통합 검사 (AXCluster `CLAUDE.md` § Tests 의 명령 그대로) ───────────────
OFFICIAL_START_DIR = "tests/integration"
OFFICIAL_PATTERN = "test_axcluster.py"
OFFICIAL_MANIFEST = "tests/integration/checks.json"
REGRESSION_TIMEOUT = 180            # checks.json 의 항목별 값과 같다

# 회귀 스크립트의 「몇 건 통과」 형식 — 이 저장소에 실재하는 셋 (CLAUDE.md 「세는 법」·checks.json).
# [주의] 어느 것도 못 읽으면 **통과가 아니다** — 수치 없이 rc 0 만 보고 통과로 접지 않는다.
REGRESSION_PATTERNS = (
    {"count_pattern": r"(?m)(?P<count>\d+)/(?P<total>\d+) 통과\s*$"},
    {"count_pattern": r"(?m)^통과 (?P<count>\d+) · 실패 (?P<failed>\d+)\s*$"},
    {"count_pattern": r"(?ms)^Ran (?P<count>\d+) tests? in [^\n]+\n\nOK(?: \(skipped=(?P<skipped>\d+)\))?\s*$"},
)


class FollowupError(RuntimeError):
    """⑦ 준비를 **시작조차** 할 수 없다 (타입 미상·검사 설정 없음 등). 조용히 넘기지 않는다."""


# ─────────────────────────────────────────────────────────────
# 로그 — `logf(stage, msg)` 관용구 (`review`·`coordinator` 와 같다) + 결과에도 남긴다
# ─────────────────────────────────────────────────────────────

class _Log:
    """호출자의 `logf` 로 넘기면서 줄을 모은다. [중요] 로그만 남기면 아무도 안 본다 —
    결과(JSON)에도 실어 세션이 그대로 보고할 수 있게 한다."""

    def __init__(self, sink=None):
        self.sink = sink or C._noop_log
        self.lines: list = []

    def __call__(self, stage: str, msg: str) -> None:
        self.lines.append(f"{datetime.now().strftime('%H:%M:%S')} [{stage}] {msg}")
        self.sink(stage, msg)


def stderr_log(stage: str, msg: str) -> None:
    """CLI 기본 로그. **stdout 은 결과 JSON 전용**이라 stderr 로 찍는다."""
    print(f"[followup] {datetime.now().strftime('%H:%M:%S')} [{stage}] {msg}",
          file=sys.stderr, flush=True)


# ─────────────────────────────────────────────────────────────
# code 판 build_fn
# ─────────────────────────────────────────────────────────────

def changed_files(tree, base_ref: str) -> list:
    """`base_ref..HEAD` 에서 바뀐 경로. 실패하면 예외 — **모르는 것을 「없음」으로 접지 않는다.**"""
    rc, out = C._git_rc(Path(tree), "diff", "--name-only", f"{base_ref}", "HEAD")
    if rc != 0:
        raise FollowupError(f"`git diff {base_ref} HEAD` 실패 — 바뀐 파일을 모른다: {out[:200]}")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def regression_targets(tree, files) -> tuple:
    """바뀐 파일 → 돌릴 회귀 검사 `(targets, notes)`.

    대응 규칙 (AXCluster 관례 `master/test_<stem>.py`):

        master/test_*.py 자체가 바뀌었다     → 그 파일
        그 밖의 `<경로>/<stem>.py`          → `master/test_<stem>.py` 가 트리에 **있으면** 그 파일
        `__init__.py` · `tests/` 아래 · 비 .py  → 대상 아님

    [주의] 공식 목록(`checks.json`)에 이미 있는 파일은 빼고 사유를 남긴다 — 통합 검사가 이미
    돌린다. 대응 테스트가 없는 파일도 **조용히 지나가지 않는다** — `notes` 에 「대응 없음」을 남긴다.
    """
    root = Path(tree)
    official = set()
    man = root / OFFICIAL_MANIFEST
    if man.is_file():
        try:
            official = {str(e.get("path")) for e in json.loads(man.read_text(encoding="utf-8"))
                        if isinstance(e, dict)}
        except (OSError, ValueError):
            official = set()
    targets, notes = [], []
    for f in files:
        p = Path(f)
        if p.suffix != ".py" or p.name == "__init__.py" or (p.parts and p.parts[0] == "tests"):
            continue
        if len(p.parts) == 2 and p.parts[0] == "master" and p.name.startswith("test_"):
            cand = f
        else:
            cand = f"master/test_{p.stem}.py"
        if not (root / cand).is_file():
            notes.append(f"{f}: 대응 회귀 검사 없음 ({cand})")
            continue
        if cand in official:
            notes.append(f"{f}: {cand} 는 공식 통합 목록에 있다 — 거기서 돈다")
            continue
        if cand not in targets:
            targets.append(cand)
    return targets, notes


def _memo_runner(run):
    """한 번만 실제로 돌리고 같은 결과를 재사용한다 — 형식 셋을 차례로 대조하려고 세 번 돌리지 않는다."""
    cache = {}

    def _r(argv, **kw):
        key = tuple(argv)
        if key not in cache:
            cache[key] = run(argv, **kw)
        return cache[key]
    return _r


def run_regression(tree, path: str, *, python: str = "", runner=None) -> dict:
    """회귀 스크립트 하나. 격리·판정은 `integration_checks.run_check` 를 **그대로 쓴다** —
    공식 목록과 같은 기준(별도 프로세스·임시 프로젝트 루트·0건 실행은 실패)이다."""
    from .. import integration_checks as IC                        # noqa: PLC0415 (마스터 전용)
    run = _memo_runner(runner or subprocess.run)
    last = None
    for pat in REGRESSION_PATTERNS:
        entry = {"path": path, "timeout": REGRESSION_TIMEOUT, **pat}
        r = IC.run_check(Path(tree), entry, python=python or sys.executable, runner=run)
        if r["ok"]:
            return {"path": path, "ok": True, "count": r["count"], "reason": r["reason"]}
        last = r
        # rc≠0·타임아웃·설정 오류는 형식 문제가 아니다 — 다음 형식을 대 볼 이유가 없다
        if not r["reason"].startswith("실행 건수 증거가 없거나"):
            break
    reason = last["reason"] if last else "실행하지 못했다"
    if last and last["reason"].startswith("실행 건수 증거가 없거나"):
        reason = "통과 수치를 어떤 형식으로도 읽지 못했다 — 통과가 아니다"
    tail = ((last or {}).get("stdout", "") + "\n" + (last or {}).get("stderr", ""))[-1500:]
    return {"path": path, "ok": False, "count": (last or {}).get("count", 0),
            "reason": reason, "tail": tail}


TAIL_LINES = 30
_re_fail = _re_mod.compile(r"^(FAIL|ERROR): ", _re_mod.M)


def _fail_tail(stderr: str, stdout: str, lines: int = TAIL_LINES) -> str:
    """실패 원문 꼬리 — **첫 FAIL/ERROR 블록부터** stderr 를, 없으면 stderr·stdout 의 끝을 준다."""
    se = (stderr or "").strip()
    m = _re_fail.search(se)
    body = se[m.start():] if m else se
    got = body.splitlines()[:lines] if m else body.splitlines()[-lines:]
    if not got:
        got = (stdout or "").strip().splitlines()[-lines:]
    return "\n".join(got)


def code_build_fn(*, base_ref: str, start_dir: str = OFFICIAL_START_DIR,
                  pattern: str = OFFICIAL_PATTERN, python: str = "", timeout: int = 1800,
                  regressions: bool = True, runner=None, regression_fn=None,
                  logf=C._noop_log):
    """`kind: code` 의 ⑦ 통합 검사 `build_fn(tree) -> dict`.

    ① 공식 통합 검사 — `python -B -m unittest discover -s <start_dir> -p <pattern> -f -v`
       (판정은 `build_local.parse_unittest` 그대로: `Ran N`(N≥1) · `OK` · rc 0)
    ② 회귀 검사 — `base_ref..HEAD` 가 건드린 파일마다 `regression_targets` 규칙으로 고른 스크립트

    [중요] 통과 = ① 통과 **그리고** ② 전부 통과. 원전 `integration_build_impl` 의
    `gate_passed = build_passed and tests_passed` 와 같은 결이다. ② 대상이 0건이면 실패가 아니라
    「대상 없음」으로 적는다 — ① 은 언제나 1건 이상이어야 한다.
    [주의] `base_ref` 는 전진 전 작업 브랜치(`<remote>/<target>`)다 — 이번 라운드의 변경만 본다.
    """
    if not (base_ref or "").strip():
        raise BuildSetupError("base_ref 가 비었다 — 이번 라운드가 무엇을 바꿨는지 모른다")
    if not (start_dir or "").strip() or not (pattern or "").strip():
        raise BuildSetupError("start_dir·pattern 이 비었다 — 무엇을 돌릴지 모른다. "
                              "[중요] 확인 불가는 통과가 아니다")
    exe = (python or "").strip() or sys.executable
    run = runner or (lambda argv, cwd, t: subprocess.run(argv, cwd=cwd, capture_output=True,
                                                         timeout=t))
    reg = regression_fn or (lambda tree, path: run_regression(tree, path, python=exe))

    def _fn(tree) -> dict:
        root = Path(tree)
        out = {"ok": False, "passed": False, "integration": {}, "regressions": [],
               "regression_notes": [], "failure": None}
        # ── ① 공식 통합 검사 ──
        if not (root / start_dir).is_dir():
            out.update(failure=f"검사 트리에 {start_dir} 이 없다: {tree}",
                       summary="BLOCKED(통합 검사 디렉토리 없음)")
            logf("check", out["failure"])
            return out
        argv = [exe, "-B", "-m", "unittest", "discover", "-s", start_dir, "-p", pattern, "-f", "-v"]
        logf("check", f"통합 검사 시작 — {' '.join(argv[1:])}")
        t0 = time.monotonic()
        try:
            r = run(argv, str(root), timeout)
            so = r.stdout if isinstance(r.stdout, str) else (r.stdout or b"").decode("utf-8", "replace")
            se = r.stderr if isinstance(r.stderr, str) else (r.stderr or b"").decode("utf-8", "replace")
            integ = parse_unittest(se + "\n" + so, r.returncode)
            if integ.get("passed") is not True:
                # 🔴 실측 2026-10-11 (#798 5a): 실패 판정만 남고 원문이 어디에도 없어 재현 못 한
                #    실패를 설명할 수 없었다. unittest 의 FAIL/ERROR·traceback 은 stderr 에 있고
                #    `raw_tail` 은 stdout 꼬리라 그것을 놓친다 — stderr 꼬리를 따로 붙잡는다.
                integ["tail"] = _fail_tail(se, so)
        except subprocess.TimeoutExpired:
            integ = {"ok": False, "passed": False, "failure": f"타임아웃 {timeout}초",
                     "summary": "BLOCKED(타임아웃)"}
        except OSError as e:
            integ = {"ok": False, "passed": False, "failure": f"실행 실패 — {e}",
                     "summary": "BLOCKED(실행 실패)"}
        integ["seconds"] = round(time.monotonic() - t0, 1)
        out["integration"] = integ
        logf("check", f"통합 검사 {integ.get('summary')} ({integ['seconds']}초)")
        if integ.get("tail"):
            logf("check", "통합 검사 실패 원문 꼬리 ↓\n" + integ["tail"])

        # ── ② 회귀 검사 — 통합 검사 결과와 무관하게 돌린다(사람이 볼 근거를 한 번에) ──
        reg_ok = True
        if regressions:
            try:
                files = changed_files(root, base_ref)
                targets, notes = regression_targets(root, files)
            except FollowupError as e:
                targets, notes, reg_ok = [], [str(e)], False
                logf("check", f"[중요] {e}")
            out["regression_notes"] = notes
            logf("check", f"회귀 대상 {len(targets)}건 (바뀐 경로 기준) — {', '.join(targets) or '없음'}")
            for path in targets:
                rr = reg(root, path)
                out["regressions"].append(rr)
                reg_ok = reg_ok and bool(rr.get("ok"))
                logf("check", f"회귀 {path}: {'통과' if rr.get('ok') else '실패'} — {rr.get('reason')}")
                if not rr.get("ok") and rr.get("tail"):
                    logf("check", f"회귀 {path} 실패 원문 꼬리 ↓\n" + rr["tail"])

        passed = integ.get("passed") is True and reg_ok
        nreg = len(out["regressions"])
        bad = [r["path"] for r in out["regressions"] if not r.get("ok")]
        out["ok"] = out["passed"] = passed
        out["summary"] = (f"통합 {integ.get('summary')} · 회귀 {nreg - len(bad)}/{nreg}"
                          + (f" (실패: {', '.join(bad)})" if bad else "")
                          + ("" if reg_ok or bad else " · 회귀 대상 판정 실패"))
        if not passed:
            out["failure"] = integ.get("failure") or ("회귀 검사 실패" if bad else
                                                       "통합 검사 실패" if not integ.get("passed")
                                                       else "회귀 대상 판정 실패")
        return out

    _fn.command = f"{exe} -B -m unittest discover -s {start_dir} -p {pattern} -f -v"
    return _fn


# ─────────────────────────────────────────────────────────────
# 타입 판정 · build_fn 선택
# ─────────────────────────────────────────────────────────────

def _read_ax_config(repo) -> dict:
    p = Path(repo) / ".ax" / "config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def resolve_kind(repo, project: str, kind: str = "") -> tuple:
    """`(kind, 출처)`. 순서: 호출자 지정 → 마스터 프로필(`profile.kind_of`) →
    배달 설정에 `tests` 가 있으면 code(`ax-advance` §3 규칙). [중요] **unreal 을 추정하지 않는다** —
    `.uproject` 유무로 타입을 정하지 않는다(distribute 스킬). 못 정하면 빈 값 → 호출자가 거절한다."""
    if kind:
        return kind, "인자"
    if project:
        # [주의] 요청자 배달본(`axmaster`)에는 `projects` 가 없다 — ImportError 는 정상 경로다
        try:
            from ..projects import profile as _pf                  # noqa: PLC0415 (마스터 전용)
        except ImportError:
            _pf = None
        if _pf is not None:
            try:
                k = _pf.kind_of(project)
                if k:
                    return k, "프로필"
            except Exception:                                      # noqa: BLE001
                pass
    cfg = _read_ax_config(repo)
    # 배달 설정의 `kind` 는 마스터 프로필 값을 그대로 실은 것이다(`bundle.config_for`) — 추정이 아니다
    if str(cfg.get("kind") or "") in KINDS:
        return str(cfg["kind"]), ".ax/config.json kind"
    if isinstance(cfg.get("tests"), dict):
        return "code", ".ax/config.json tests"
    return "", ""


def build_fn_for(kind: str, *, repo, project: str = "", base_ref: str = "",
                 start_dir: str = "", pattern: str = "", python: str = "",
                 ue5_cmd: str = "", logf=C._noop_log):
    """타입별 `build_fn`. [중요] **만들 때 실패하면 예외** — 트리를 세우기 전에 드러낸다."""
    cfg = _read_ax_config(repo)
    if kind == "index_only":
        raise FollowupError("색인 전용 프로젝트다 (`kind: index_only`) — 분산 작업·통합 검사가 없다")
    if kind == "unreal":
        from .build_local import local_build_fn                    # noqa: PLC0415
        return local_build_fn(project=project or str(cfg.get("project") or ""),
                              ue5_cmd=ue5_cmd or str((cfg.get("backends") or {}).get("ue5_cmd") or ""))
    if kind == "code":
        tests = cfg.get("tests") if isinstance(cfg.get("tests"), dict) else {}
        if start_dir and pattern:
            sd, pt = start_dir, pattern
        elif (Path(repo) / OFFICIAL_MANIFEST).is_file():
            sd, pt = OFFICIAL_START_DIR, OFFICIAL_PATTERN          # AXCluster 공식 목록
        elif tests.get("start_dir") and tests.get("pattern"):
            sd, pt = str(tests["start_dir"]), str(tests["pattern"])
        else:
            raise FollowupError("code 프로젝트인데 통합 검사 위치를 모른다 — "
                                "`--start-dir`·`--pattern` 인자도 배달 설정 `tests` 도 없다")
        py = python or str((cfg.get("backends") or {}).get("python") or "")
        return code_build_fn(base_ref=base_ref, start_dir=sd, pattern=pt, python=py, logf=logf)
    raise FollowupError(f"타입을 정할 수 없다(`{kind or '비어 있음'}`) — `--kind`"
                        f"({'/'.join(KINDS)}) 인자도 배달 설정 `kind` 도 없다. 추정하지 않는다")


# ─────────────────────────────────────────────────────────────
# 입구
# ─────────────────────────────────────────────────────────────

@dataclass
class Followup:
    """⑦ 준비 결과. `state` 는 넷 중 하나다:

        running   아직 도는 조각이 있다 — 아무것도 안 했다
        stopped   반려·취소·실패·마감 — 사실만 내고 멈췄다 (머지·검사 안 함)
        at_gate   머지·통합 검사까지 했고 **사람 게이트에서 멈췄다** (push 없음)
        error     준비를 못 했다 (타입·검사 설정·머지 충돌 등) — 사유를 보고한다
        stale_round  부른 쪽이 기대한 라운드와 큐의 라운드가 다르다 — 아무것도 안 했다
    """
    work_id: str = ""
    state: str = ""
    merge_status: str = ""
    round: int = 0
    project: str = ""
    title: str = ""
    redmine_issue_id: int | None = None
    kind: str = ""
    kind_source: str = ""
    counts: dict = field(default_factory=dict)
    failed_tasks: list = field(default_factory=list)
    reason: str = ""
    tree: str = ""
    target_branch: str = ""
    before: str = ""
    head: str = ""
    merged: list = field(default_factory=list)
    conflicts: bool = False
    build_passed: bool | None = None
    build_note: str = ""
    question: str = ""
    checks: dict = field(default_factory=dict)     # `check_counts` — 통과·실패 항목 수
    commands: list = field(default_factory=list)
    pushed: bool = False
    log: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def facts(self) -> dict:
        """기록·고지용 사실. 로그는 끝 20줄만 싣는다 (상태 파일을 키우지 않는다)."""
        d = self.to_dict()
        d["log"] = list(self.log[-20:])
        return d


def check_counts(res) -> dict:
    """`build_fn` 결과 → `{passed, failed, items:[{name, ok, summary}]}`.

    code 판(`code_build_fn`)은 통합 검사 1건 + 회귀 n건, 그 밖(unreal 등)은 결과 1건이다.
    [중요] 결과를 못 받았으면(예외·미실행) 빈 dict — 「0 실패」로 접지 않는다.
    """
    if res is None:
        return {}
    items = []
    if isinstance(res, dict) and "integration" in res:
        integ = res.get("integration") or {}
        items.append({"name": "통합 검사", "ok": integ.get("passed") is True,
                      "summary": str(integ.get("summary") or integ.get("failure") or "")[:200],
                      **({"tail": str(integ["tail"])[-3000:]} if integ.get("tail") else {})})
        for r in res.get("regressions") or []:
            items.append({"name": f"회귀 {r.get('path')}", "ok": r.get("ok") is True,
                          "summary": str(r.get("reason") or "")[:200],
                          **({"tail": str(r["tail"])[-3000:]} if not r.get("ok") and r.get("tail")
                             else {})})
    else:
        ok, note = R.build_verdict(res)
        items.append({"name": "빌드", "ok": ok, "summary": note[:200]})
    passed = sum(1 for i in items if i["ok"])
    return {"passed": passed, "failed": len(items) - passed, "items": items}

def _round_tasks(work: dict, tasks) -> list:
    """`advance_work` 와 **같은** 라운드 거르기 — 스탬프 없는 옛 레코드는 거르지 않는다."""
    cur = int((work or {}).get("round", 1) or 1)
    tasks = list(tasks or [])
    if any(int(t.get("round") or 0) > 0 for t in tasks):
        tasks = [t for t in tasks if int(t.get("round") or 0) in (0, cur)]
    return tasks


def _failed_of(rtasks) -> list:
    """실패·취소 조각의 사실 — `prepare_round` 와 `wait_for_gate` 가 같은 모양으로 쓴다."""
    return [{"task_id": t.get("task_id") or t.get("id"), "status": t.get("status"),
             "reason": str(t.get("failure") or t.get("error") or t.get("reason") or "")[:300]}
            for t in rtasks or () if t.get("status") in TASK_BAD]


def prepare_round(repo, work_id: str, *, api=None, kind: str | None = None, project: str = "",
                  build_fn=None, start_dir: str = "", pattern: str = "", python: str = "",
                  ue5_cmd: str = "", remote: str = R.DEFAULT_REMOTE,
                  expect_round: int | None = None,
                  fetch=None, advance=None, logf=None) -> Followup:
    """라운드 종결 뒤 ⑦ 준비. 요청자 세션(CLI) 또는 `ax-followup.timer` 가 부른다 — 큐 서버는 부르지 않는다.

    [중요] `advance_work` 에는 **언제나 `confirm=False`** 다(인자로 열지 않는다). 그래서 이
    함수는 push 하지 않고 `main` 을 만지지 않는다. 사람의 답 뒤의 전진은 `ax-advance` §5 의
    별도 호출이다. `fetch`·`advance` 는 테스트 주입 자리다.
    """
    log = _Log(logf)
    fu = Followup(work_id=work_id)

    def _done(state: str, reason: str = "") -> Followup:
        fu.state, fu.reason = state, reason or fu.reason
        log("followup", f"멈춤 — state={state}" + (f" · {fu.reason}" if fu.reason else ""))
        fu.log = list(log.lines)
        return fu

    # ── ① 큐에서 다시 읽는다 ──
    try:
        work, tasks = (fetch or R.fetch_work)(work_id, api=api)
    except Exception as e:                                         # noqa: BLE001
        return _done("error", f"큐 조회 실패 — {type(e).__name__}: {e}")
    if not work:
        return _done("error", f"큐에 work {work_id} 가 없다")
    fu.merge_status = str(work.get("merge_status") or "")
    fu.round = int(work.get("round", 1) or 1)
    fu.project = str(project or work.get("project") or "")
    fu.title = str(work.get("title") or "")
    try:
        fu.redmine_issue_id = int(work.get("redmine_issue_id")) if work.get("redmine_issue_id") else None
    except (TypeError, ValueError):
        fu.redmine_issue_id = None
    rtasks = _round_tasks(work, tasks)
    counts: dict = {}
    for t in rtasks:
        s = str(t.get("status") or "?")
        counts[s] = counts.get(s, 0) + 1
    fu.counts = counts
    fu.failed_tasks = _failed_of(rtasks)
    terminal = sum(n for s, n in counts.items() if s in TASK_TERMINAL)
    log("fetch", f"work {work_id} merge_status={fu.merge_status} · 라운드 {fu.round} · "
                 f"조각 {terminal}/{len(rtasks)} 종결 · {counts}")

    # ── ② 상태로 갈래를 정한다 — 사실만, 부작용 없음 ──
    if expect_round is not None and fu.round != int(expect_round):
        # [중요] 목록을 읽은 뒤 개선요청으로 라운드가 넘어갔다 — 옛 라운드 키로 새 라운드를 돌리지 않는다
        return _done("stale_round", f"요청한 라운드 {expect_round} ≠ 큐의 라운드 {fu.round} — 다음 주기에 다시 본다")
    if fu.merge_status in STOP_STATES:
        return _done("stopped", f"work 가 `{fu.merge_status}` 다 — ⑦ 준비를 하지 않는다"
                     + (f" (사유: {work.get('terminal_reason')})" if work.get("terminal_reason") else ""))
    if fu.failed_tasks:
        return _done("stopped", f"이번 라운드 조각 {len(fu.failed_tasks)}건이 실패·취소다 — "
                                "머지하지 않았다")
    if fu.merge_status != READY:
        return _done("running", f"아직 `{fu.merge_status or '?'}` — 조각 {terminal}/{len(rtasks)} 종결. "
                                "끝나면 다음 호출·주기에 다시 본다")
    if not rtasks or terminal < len(rtasks):
        # [주의] 큐는 ready 인데 조각이 덜 끝났다 — 모순을 통과로 접지 않는다
        return _done("error", f"`{READY}` 인데 조각 {terminal}/{len(rtasks)} 만 종결 — 큐 상태가 모순이다")

    # ── ③ 타입 → build_fn (트리를 세우기 **전에** 실패를 드러낸다) ──
    project = project or str(work.get("project") or "")
    fu.target_branch = R.work_base_branch(work_id, work)
    if build_fn is None:
        fu.kind, fu.kind_source = resolve_kind(repo, project, kind or "")
        log("kind", f"타입 {fu.kind or '미상'} (출처: {fu.kind_source or '없음'}) · 프로젝트 {project or '?'}")
        try:
            build_fn = build_fn_for(fu.kind, repo=repo, project=project,
                                    base_ref=f"{remote}/{fu.target_branch}",
                                    start_dir=start_dir, pattern=pattern, python=python,
                                    ue5_cmd=ue5_cmd, logf=log)
        except (FollowupError, BuildSetupError) as e:
            return _done("error", str(e))
    else:
        fu.kind, fu.kind_source = (kind or ""), "build_fn 주입"
        log("kind", "build_fn 을 호출자가 주입했다")

    # ── ④ 머지 + 통합 검사 — [중요] confirm=False 고정 · 트리 보존 ──
    # 검사 결과 원본을 붙잡아 통과·실패 항목 수를 낸다 (`Advance` 는 요약 문장만 돌려준다)
    _inner, _seen = build_fn, {}

    def build_fn(tree, _inner=_inner):                              # noqa: F811
        _seen["res"] = _inner(tree)
        return _seen["res"]
    if hasattr(_inner, "command"):
        build_fn.command = _inner.command
    log("advance", f"시작 — {remote}/{fu.target_branch} 위에 라운드 {fu.round} 조각 {len(rtasks)}건 "
                   f"(confirm=False · keep_tree=True)")
    a = (advance or R.advance_work)(Path(repo), work_id=work_id, work=work, tasks=tasks,
                                    build_fn=build_fn, confirm=False, keep_tree=True,
                                    remote=remote, api=api, logf=log)
    fu.tree, fu.before, fu.head = a.tree, a.before, a.head
    fu.merged, fu.conflicts, fu.pushed = list(a.merged), bool(a.conflicts), bool(a.pushed)
    fu.build_passed, fu.build_note = a.build_passed, a.build_note
    fu.checks = check_counts(_seen.get("res")) if "res" in _seen else {}
    fu.commands = list(a.commands)
    if a.pushed:
        # 있어서는 안 된다 — confirm=False 를 넘겼다. 보이게 남긴다
        log("advance", "[중요] confirm=False 인데 push 됐다고 보고됐다 — 계약 위반, 사람이 확인할 것")
    if a.error:
        return _done("error", f"⑦ 준비 실패 — {a.error}")
    log("build", f"통합 검사 build_passed={a.build_passed} — {a.build_note[:200]}")
    fu.question = a.question
    log("gate", f"사람 게이트에서 멈춘다 — 트리 {a.tree} · HEAD {a.head[:12]} · push 안 함")
    return _done("at_gate", a.summary)




# ─────────────────────────────────────────────────────────────
# 멱등 · 동시성 — 타이머(1분)와 사람의 CLI 호출이 **같은 핵심**을 부른다
# ─────────────────────────────────────────────────────────────
#
# 키는 `(정본 경로, work_id, 라운드)` 다. 라운드가 오르면(개선요청) 새 키라 다시 준비된다.
#
# [중요] 상태 자리 = `~/.cache/ax-followup/` (환경변수 `AX_FOLLOWUP_STATE_DIR` 로 바꾼다).
#    체크아웃 안(`<repo>/.ax/`)에 두지 않는 이유:
#      ① 요청자 체크아웃은 **사람의 트리**일 수 있다(`.33`) — 거기에 매분 쓰는 파일을 두지 않는다
#      ② 이 상태는 **기계(호스트)의 것**이다 — 세션과 무관하고 정본 경로를 키에 이미 싣는다
#      ③ 재부팅을 넘어야 한다 — `~/.cache/ax-dispatch/hold.json` 과 같은 자리·같은 이유
#    [주의] 지우면 「이미 준비함」 기억이 사라져 **다시 준비한다**(트리 재생성·재검사) — 잃는 것은 시간뿐이다.
#
# 잠금: `O_CREAT|O_EXCL` 파일 + 하트비트 `touch` + mtime 90초 초과면 죽은 잠금으로 보고
# **사유를 남기고** 지운다. 준비(통합 검사)는 한 호출이 몇 분 막히므로 하트비트를 스레드가 친다.

STATE_ENV = "AX_FOLLOWUP_STATE_DIR"
LOCK_STALE = 90                     # 초
HEARTBEAT = 20                      # 초 — LOCK_STALE 보다 충분히 짧게
RECORDED = {"at_gate": "prepared", "stopped": "stopped", "error": "error"}


def state_dir(override=None) -> Path:
    import os
    if override:
        return Path(override)
    env = os.environ.get(STATE_ENV, "").strip()
    return Path(env) if env else Path.home() / ".cache" / "ax-followup"


def round_key_path(sdir, repo, work_id: str, round_no: int) -> Path:
    import hashlib
    key = json.dumps([str(Path(repo).resolve()), work_id, int(round_no)], ensure_ascii=True)
    return Path(sdir) / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def read_state(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(path: Path, value: dict) -> None:
    """원자적으로 쓴다 (임시 파일 → replace)."""
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def journal(sdir, event: str, **fields) -> None:
    """`<state>/followup.jsonl` 한 줄 (이벤트 · 시각 · 필드)."""
    try:
        d = Path(sdir)
        d.mkdir(parents=True, exist_ok=True)
        row = dict(at=time.time(), event=event, **fields)
        with (d / "followup.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass                         # 기록 실패가 준비를 막지 않는다 — stderr 로그는 남는다


class RoundLock:
    """`(repo, work_id, round)` 하나의 잠금. `acquire()` 가 False 면 누가 잡고 있다."""

    def __init__(self, path: Path, *, stale: int = LOCK_STALE, heartbeat: int = HEARTBEAT,
                 logf=C._noop_log, now=time.time):
        self.path, self.stale, self.heartbeat = Path(path), stale, heartbeat
        self.logf, self.now = logf, now
        self._stop = None
        self._thread = None
        self.held = False

    def acquire(self) -> bool:
        import os
        import socket
        import threading
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.path.exists():
                age = self.now() - self.path.stat().st_mtime
                if age > self.stale:
                    who = self.path.read_text(encoding="utf-8", errors="replace")[:120]
                    self.path.unlink(missing_ok=True)
                    self.logf("lock", f"[주의] 죽은 잠금을 지운다 — 하트비트 {age:.0f}초 끊김 "
                                      f"(> {self.stale}초) · 보유자 {who or '?'} · {self.path.name}")
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        os.write(fd, f"{socket.gethostname()} pid={os.getpid()}".encode())
        os.close(fd)
        self.held = True
        self._stop = threading.Event()

        def _beat():
            while not self._stop.wait(self.heartbeat):
                try:
                    self.path.touch()
                except OSError:
                    pass
        self._thread = threading.Thread(target=_beat, name="followup-heartbeat", daemon=True)
        self._thread.start()
        return True

    def release(self) -> None:
        if self._stop:
            self._stop.set()
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False


NOTE_ROUTE = "/api/v1/redmine/note"     # `client_mcp.tool_redmine_note` 와 같은 큐 대행 자리
STATE_LABEL = {
    "at_gate": "⑦ 준비됨 · 사람 승인 대기 (전진·push 없음)",
    "stopped": "멈춤 — ⑦ 준비 대상 아님",
    "error": "⑦ 준비 실패",
    "running": "진행 중 — 준비 전",
    "stale_round": "라운드 불일치 — 준비 안 함",
    "baseline": "기준선 — followup 설치 전에 종결된 라운드, 준비 안 함",
}
ORIGIN_LABEL = {"hook": "완료 훅", "timer": "타이머(scan)", "cli": "CLI"}   # hook 은 일반 라벨만 — 마스터에 훅 배선 없음


def post_note(api, *, issue_id: int, text: str, project: str = "", work_id: str = "") -> dict:
    """Redmine 노트 — 요청자 MCP `redmine_note` 와 **같은 큐 대행 라우트**다(새 인증 경로 없음).

    [중요] 키는 마스터 컨테이너에만 있고 요청자는 본문만 보낸다. 태그(`project`)는 라우트
    정책이 TAG 라 싣는다(`task_queue/tagging.py`) — 요청자 `queue_api` 는 비어 있으면 채우고,
    마스터 `runner._api` 경로를 위해 여기서도 work 의 프로젝트를 싣는다.
    서버는 실패해도 200 + `ok:false` 다 — 호출자가 `ok` 를 본다.
    """
    payload = {"issue_id": int(issue_id), "notes": text}
    if project:
        payload["project"] = project
    if work_id:
        payload["work_id"] = work_id
    return api("POST", NOTE_ROUTE, payload) or {}


def render(facts: dict, *, origin: str = "", at: float | None = None) -> str:
    """⑦ 준비 결과 → **사실만** 담은 여러 줄 (CLI 출력 · Redmine 노트 공용).

    🔴 [중요] 명령형을 쓰지 않는다 — 자동 경로로 모델에게 닿는 글에 명령형이 있으면 주입으로
    거부된다(실측 2026-09-10, 리포트 60). 「그래서 무엇을 하나」는 `distribute`·`ax-advance`
    스킬의 몫이다. 사람에게 묻는 물음은 `Advance.question`
    **원문을 인용**으로만 싣는다.
    """
    f = dict(facts or {})
    st = str(f.get("state") or f.get("event") or "")
    wid = f.get("work_id") or "(id 없음)"
    out = [f"[⑦ 준비 결과] {wid} · 라운드 {f.get('round')} · 상태 {st} — "
           f"{STATE_LABEL.get(st, st or '미상')}"]
    if f.get("title"):
        out.append(f"  제목: {f['title']}")
    meta = [x for x in (f"프로젝트 {f['project']}" if f.get("project") else "",
                        f"타입 {f['kind']}" if f.get("kind") else "",
                        f"큐 상태 {f['merge_status']}" if f.get("merge_status") else "") if x]
    if meta:
        out.append("  " + " · ".join(meta))
    if f.get("tree"):
        out.append(f"  트리: {f['tree']}")
    if f.get("target_branch") or f.get("head"):
        out.append(f"  작업 브랜치 {f.get('target_branch') or '?'} · 전진 전 "
                   f"{str(f.get('before') or '?')[:12]} · 트리 HEAD {str(f.get('head') or '?')[:12]}")
    if st == "at_gate" or f.get("merged"):
        out.append(f"  머지한 조각 {len(f.get('merged') or [])}건 · 충돌 "
                   f"{'있음' if f.get('conflicts') else '없음'}")
    checks = f.get("checks") or {}
    bp = f.get("build_passed")
    verdict = "통과" if bp is True else "실패" if bp is False else "미측정"
    if checks:
        out.append(f"  통합 검사 {verdict} · 항목 통과 {checks.get('passed', 0)} · "
                   f"실패 {checks.get('failed', 0)}")
        for it in checks.get("items") or []:
            out.append(f"    · {it.get('name')}: {'통과' if it.get('ok') else '실패'}"
                       + (f" — {it['summary']}" if it.get("summary") else ""))
            if it.get("tail") and not it.get("ok"):
                out.append("      실패 원문 꼬리:")
                out.extend("        " + ln for ln in str(it["tail"]).splitlines()[-TAIL_LINES:])
    elif st == "at_gate":
        out.append(f"  통합 검사 {verdict} — {f.get('build_note') or '요약 없음'}")
    if f.get("failed_tasks"):
        for t in f["failed_tasks"]:
            out.append(f"  조각 {t.get('status')} {t.get('task_id')}: {t.get('reason') or '사유 없음'}")
    if f.get("reason") and st != "at_gate":
        out.append(f"  사유: {str(f['reason'])[:500]}")
    if f.get("question"):
        out.append(f"  게이트 물음(원문 인용): 「{f['question']}」")
    if f.get("pushed"):
        out.append("  [중요] push 됨으로 보고됨 — confirm=False 계약과 어긋난 기록")
    if f.get("redmine_issue_id"):
        out.append(f"  Redmine #{f['redmine_issue_id']}")
    note = f.get("note") or {}
    if note:
        out.append(f"  Redmine 노트: {'기재됨' if note.get('ok') else '기재 실패 — ' + str(note.get('error') or note.get('result') or '')[:200]}")
    src = ORIGIN_LABEL.get(origin or f.get("origin") or "", origin or f.get("origin") or "")
    when = at if at is not None else f.get("at")
    tail = [x for x in (f"준비 주체 {src}" if src else "",
                        f"기록 시각 {datetime.fromtimestamp(float(when)).strftime('%Y-%m-%d %H:%M:%S')}"
                        if when else "") if x]
    if tail:
        out.append("  " + " · ".join(tail))
    return "\n".join(out)


def recorded_for(repo, work_id: str, round_no: int | None = None, *, state=None) -> dict:
    """기록된 준비 결과 하나 (없으면 빈 dict). 라운드를 모르면 그 work 의 **가장 높은 라운드**.

    [주의] 키는 `(정본 경로, work_id, 라운드)` 해시라 라운드 없이는 파일명을 못 만든다 —
    그때만 상태 디렉토리를 훑어 기록 안의 `work_id`·`repo` 로 맞춘다.
    """
    sdir = state_dir(state)
    if round_no is not None:
        rec = read_state(round_key_path(sdir, repo, work_id, int(round_no)))
        return _with_facts(rec)
    want = str(Path(repo).resolve())
    best: dict = {}
    for p in Path(sdir).glob("*.json") if Path(sdir).is_dir() else ():
        rec = read_state(p)
        if rec.get("work_id") != work_id:
            continue
        try:
            if str(Path(str(rec.get("repo") or "")).resolve()) != want:
                continue
        except OSError:
            continue
        if not best or int(rec.get("round") or 0) > int(best.get("round") or 0):
            best = rec
    return _with_facts(best)


def _with_facts(rec: dict) -> dict:
    """옛 기록(사실 묶음 없음)도 같은 모양으로 읽히게 한다."""
    if not rec:
        return {}
    facts = dict(rec.get("facts") or {})
    for k in ("work_id", "round", "state", "reason", "tree", "head", "build_passed"):
        facts.setdefault(k, rec.get(k))
    if not facts.get("state"):
        facts["state"] = rec.get("event", "")
    for k in ("note", "origin", "at"):
        if rec.get(k) is not None:
            facts[k] = rec[k]
    return facts


def _post_note_once(sdir, path: Path, rec: dict, fu, api, note, log) -> dict:
    """기록 직후 한 번 — 결과를 기록에 남긴다. 기록이 있으면 다음 호출은 여기 오지 않는다(키당 1회)."""
    wid, rnd = rec["work_id"], rec["round"]
    if not fu.redmine_issue_id:
        log("note", f"{wid} r{rnd} Redmine 이슈 번호가 work 에 없다 — 노트 없음")
        journal(sdir, "note_skipped", work_id=wid, round=rnd, reason="no_issue")
        return {"ok": False, "skipped": "no_issue"}
    if note is None and api is None:
        log("note", f"{wid} r{rnd} 큐 호출자가 없다 — Redmine #{fu.redmine_issue_id} 노트 못 남김")
        journal(sdir, "note_skipped", work_id=wid, round=rnd, reason="no_api",
                issue=fu.redmine_issue_id)
        return {"ok": False, "skipped": "no_api"}
    text = render(_with_facts(rec))
    try:
        got = (note or post_note)(api, issue_id=fu.redmine_issue_id, text=text,
                                  project=fu.project, work_id=wid) or {}
        ok = got.get("ok") is not False
        res = {"ok": ok, "at": time.time(), "issue": fu.redmine_issue_id,
               "result": str(got.get("result") or "")[:300]}
    except Exception as e:                                         # noqa: BLE001
        res = {"ok": False, "at": time.time(), "issue": fu.redmine_issue_id,
               "error": f"{type(e).__name__}: {e}"[:300]}
    if res["ok"]:
        log("note", f"{wid} r{rnd} Redmine #{fu.redmine_issue_id} 노트 기재 ({len(text)}자)")
        journal(sdir, "note_posted", work_id=wid, round=rnd, issue=fu.redmine_issue_id,
                chars=len(text))
    else:
        log("note", f"[중요] {wid} r{rnd} Redmine #{fu.redmine_issue_id} 노트 실패 — "
                    f"{res.get('error') or res.get('result')}")
        journal(sdir, "note_failed", work_id=wid, round=rnd, issue=fu.redmine_issue_id,
                error=res.get("error") or res.get("result"))
    return res


def prepare_once(repo, work_id: str, round_no: int | None = None, *, state=None,
                 force: bool = False, api=None, fetch=None, prepare=None, note=None,
                 origin: str = "cli", logf=None, **kw) -> dict:
    """멱등 입구 — 타이머·사람이 **이것을** 부른다. `{work_id, round, action, skip, result, facts}`.

    action: `prepared`(준비를 돌렸다 — 결과 state 는 result 에) · `skipped`(사유는 skip)
    skip:   `already_prepared` · `already_stopped` · `previous_error` · `baseline` · `locked` ·
            `round_unknown`
    [중요] 기록하는 것은 at_gate·stopped·error 셋뿐이다. running·stale_round 는 기록하지 않는다 —
    다음 주기에 다시 본다. error 도 기록한다: 머지 충돌·검사 설정 결손은 1분 뒤에 저절로 낫지
    않고, 매분 트리를 다시 세우고 검사를 다시 돌리면 그 자체가 해다. 재시도는 `--force`.
    [중요] 기록한 직후 **그 work 의 Redmine 이슈에 노트를 한 번** 남긴다(`#798` ⓐ). 기록이
    잠금 안에서 먼저 생기므로 같은 키로 두 번 오지 않는다. 노트 실패는 기록에 남고 재시도하지 않는다.
    `facts` 는 이번에 만든 결과든 기록이든 `render()` 가 읽는 같은 모양이다.
    """
    log = logf or C._noop_log
    sdir = state_dir(state)
    if round_no is None:
        try:
            work, _ = (fetch or R.fetch_work)(work_id, api=api)
            round_no = int((work or {}).get("round", 1) or 1)
        except Exception as e:                                     # noqa: BLE001
            log("once", f"{work_id} 라운드를 못 읽었다 — {type(e).__name__}: {e}")
            return {"work_id": work_id, "round": None, "action": "skipped",
                    "skip": "round_unknown", "reason": str(e)}
    out = {"work_id": work_id, "round": int(round_no), "action": "skipped", "skip": ""}
    path = round_key_path(sdir, repo, work_id, round_no)
    lock = RoundLock(path.with_suffix(".lock"), logf=log)
    if not lock.acquire():
        log("once", f"{work_id} r{round_no} 건너뜀 — 다른 준비가 잡고 있다(잠금 {lock.path.name})")
        journal(sdir, "lock_held", work_id=work_id, round=round_no, lock=str(lock.path),
                origin=origin)
        out["skip"] = "locked"
        return out
    try:
        # [중요] 기록 확인은 **잠금 안에서** 한다 — 잠금 밖에서 보면 둘이 동시에 「안 함」을 본다
        prev = read_state(path)
        if prev and not force:
            ev = prev.get("event", "")
            out["skip"] = {"prepared": "already_prepared", "stopped": "already_stopped",
                           "error": "previous_error", "baseline": "baseline"}.get(ev, ev)
            out["recorded"] = prev
            out["facts"] = _with_facts(prev)
            log("once", f"{work_id} r{round_no} 건너뜀 — {out['skip']} "
                        f"(기록 {prev.get('state', ev)} · {prev.get('reason', '')[:120]})"
                        + (" · 다시 하려면 --force" if ev in ("error", "baseline") else ""))
            journal(sdir, "prepare_reused", work_id=work_id, round=round_no, skip=out["skip"],
                    origin=origin)
            return out
        if prev and force:
            log("once", f"{work_id} r{round_no} --force — 기록 `{prev.get('event')}` 을 무시하고 다시 준비한다")
        journal(sdir, "prepare_started", work_id=work_id, round=round_no, force=force, origin=origin)
        log("once", f"{work_id} r{round_no} 준비 시작 (주체 {origin})")
        fu = (prepare or prepare_round)(repo, work_id, api=api, expect_round=int(round_no),
                                        fetch=fetch, logf=log, **kw)
        out["action"], out["result"] = "prepared", fu.to_dict()
        out["facts"] = dict(fu.facts(), origin=origin, at=time.time())
        ev = RECORDED.get(fu.state)
        if ev:
            rec = {"event": ev, "state": fu.state, "at": out["facts"]["at"],
                   "work_id": work_id, "round": int(round_no), "repo": str(repo),
                   "reason": fu.reason, "tree": fu.tree, "head": fu.head,
                   "build_passed": fu.build_passed, "origin": origin, "facts": fu.facts()}
            write_state(path, rec)
            rec["note"] = _post_note_once(sdir, path, rec, fu, api, note, log)
            write_state(path, rec)
            out["facts"]["note"] = rec["note"]
        journal(sdir, "prepare_done", work_id=work_id, round=round_no, state=fu.state,
                recorded=ev or "", reason=fu.reason[:300], tree=fu.tree,
                build_passed=fu.build_passed, origin=origin)
        return out
    finally:
        lock.release()


# ─────────────────────────────────────────────────────────────
# scan — 타이머가 60초마다 부른다
# ─────────────────────────────────────────────────────────────

TERMINAL_WORK = (READY, "rejected", "cancelled")


def resolve_project(repo, project: str = "") -> tuple:
    """`(project, 출처)`. 지정 → 요청자 배달 설정 `.ax/config.json` → 마스터 마운트. 없으면 빈 값."""
    if project:
        return project, "인자"
    p = str(_read_ax_config(repo).get("project") or "").strip()
    if p:
        return p, ".ax/config.json"
    try:
        from ..projects.config import Registry                     # noqa: PLC0415 (마스터 전용)
    except ImportError:                                            # 요청자 배달본엔 없다
        return "", ""
    try:
        a = (Registry.load().active or "").strip()
        if a:
            return a, "마운트"
    except Exception:                                              # noqa: BLE001
        pass
    return "", ""


def list_open_works(api, project: str) -> list:
    """큐의 work 목록(그 프로젝트) — `client_mcp.tool_list_works` 와 같은 라우트. `merged` 는 뺀다."""
    from urllib.parse import quote
    got = api("GET", f"/api/v1/works?project={quote(project)}")
    works = got if isinstance(got, list) else ((got or {}).get("works") or [])
    return [w for w in works if w.get("merge_status") != "merged"]


def scan(repo, *, project: str = "", api=None, state=None, list_works=None, once=None,
         logf=None, **kw) -> dict:
    """한 주기. [중요] **할 일이 없어도 한 줄을 남긴다** — 「타이머가 죽었다」와 구분되어야 한다.

    최초 주기(그 프로젝트의 기준선이 없을 때)는 **기준선만 긋는다**: 지금 이미 종결된 라운드를
    `baseline` 으로 적고 **준비하지 않는다.** 이 기능이 생기기 전에 끝난(대개 이미 전진했거나
    사람이 다룬) 라운드마다 트리를 세우고 검사를 돌리지 않기 위해서다. 적은 키는 하나하나
    로그에 남고, 다시 하려면 `<work_id> --force` 다.
    """
    log = logf or C._noop_log
    sdir = state_dir(state)
    proj, src = resolve_project(repo, project)
    if not proj:
        log("scan", "[중요] 프로젝트를 정할 수 없다 — `--project` 인자·배달 설정·마운트 모두 비었다. 멈춘다")
        journal(sdir, "scan_refused", reason="no_project")
        return {"ok": False, "reason": "no_project"}
    try:
        works = (list_works or list_open_works)(api, proj)
    except Exception as e:                                         # noqa: BLE001
        log("scan", f"[중요] tick {proj}: 큐 목록 조회 실패 — {type(e).__name__}: {e}")
        journal(sdir, "scan_error", project=proj, error=str(e)[:300])
        return {"ok": False, "reason": f"list_failed: {e}"}

    base_mark = Path(sdir) / f"baseline-{hashlib_name(repo, proj)}.json"
    first = not base_mark.exists()
    summary = {"ok": True, "project": proj, "project_source": src, "works": len(works),
               "baseline": first, "prepared": [], "skipped": {}}
    for w in works:
        wid = str(w.get("work_id") or "")
        st = str(w.get("merge_status") or "")
        rnd = int(w.get("round", 1) or 1)
        if not wid:
            continue
        if st not in TERMINAL_WORK:
            summary["skipped"][f"{wid}/r{rnd}"] = f"running({st or '?'})"
            continue
        if first:
            p = round_key_path(sdir, repo, wid, rnd)
            if not p.exists():
                write_state(p, {"event": "baseline", "state": st, "at": time.time(),
                                "work_id": wid, "round": rnd, "repo": str(repo),
                                "reason": "followup 설치 전에 이미 종결된 라운드 — 준비하지 않았다"})
                log("scan", f"기준선 {wid} r{rnd} ({st}) — 준비하지 않는다 (--force 로 따로 돌릴 수 있다)")
            summary["skipped"][f"{wid}/r{rnd}"] = "baseline"
            continue
        r = (once or prepare_once)(repo, wid, rnd, state=sdir, api=api, logf=log,
                                  project=proj, origin="timer", **kw)
        if r.get("action") == "prepared":
            summary["prepared"].append({"work_id": wid, "round": rnd,
                                        "state": (r.get("result") or {}).get("state")})
        else:
            summary["skipped"][f"{wid}/r{rnd}"] = r.get("skip") or "?"
    if first:
        write_state(base_mark, {"at": time.time(), "project": proj, "repo": str(repo)})
    skip_txt = ", ".join(f"{k}={v}" for k, v in summary["skipped"].items()) or "없음"
    prep_txt = ", ".join(f"{p['work_id']}/r{p['round']}→{p['state']}" for p in summary["prepared"]) or "없음"
    log("scan", f"tick {proj}({src}) · work {len(works)}건"
                + (" · [기준선 주기]" if first else "")
                + f" · 준비 {prep_txt} · 건너뜀 {skip_txt}")
    journal(sdir, "scan_tick", project=proj, works=len(works), baseline=first,
            prepared=summary["prepared"], skipped=summary["skipped"])
    return summary


def hashlib_name(repo, project: str) -> str:
    import hashlib
    return hashlib.sha256(json.dumps([str(Path(repo).resolve()), project]).encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────
# wait — 등재한 세션이 백그라운드로 돌려 두는 **읽기 전용** 대기 (`#798` ①)
# ─────────────────────────────────────────────────────────────
#
# 타이머가 ⑦ 를 준비해도 **사용자에게 묻는 것**은 보장되지 않았다 — 실측 2026-10-11 에
# 물음이 사람에게 닿은 것은 세션이 우연히 journald 를 따라가고 있었기 때문이다.
# 그래서 등재와 대기를 한 입구로 묶는다: 등재 응답이 이 명령을 싣고, 세션이 그것을
# 백그라운드로 돌려 두면 **끝날 때 세션이 깨어난다.**
#
# [중요] 순수 읽기다 — 준비하지 않고(`prepare_once` 를 부르지 않는다) · 전진·확인을 부르지
# 않고 · 상태 파일·저널에 쓰지 않는다. 준비는 타이머의 몫이고 이 함수는 그 기록을 읽을 뿐이다.

WAIT_RECORDED = ("at_gate", "stopped", "error")     # `RECORDED` 의 결과 state — 이 셋이면 끝
WAIT_TERMINAL = ("rejected", "cancelled")
WAIT_EXIT = {"at_gate": 0, "stopped": 3, "error": 3, "terminal_rejected": 3,
             "terminal_cancelled": 3, "merged": 3, "timeout": 4}
WAIT_LABEL = {
    "merged": "work 가 이미 `merged` — 마감됨, ⑦ 대기 대상 아님",
    "terminal_rejected": "work 가 `rejected` — ⑦ 준비 대상 아님",
    "terminal_cancelled": "work 가 `cancelled` — ⑦ 준비 대상 아님",
    "timeout": "대기 시간 초과 — 준비 결과를 보지 못했다",
}


def _mmss(sec: float) -> str:
    s = max(0, int(round(sec)))
    return f"{s // 60:02d}:{s % 60:02d}"


def render_wait(res: dict) -> str:
    """`wait_for_gate` 결과 → 사실만 담은 블록. 준비 기록이 있으면 `render()` 를 **그대로**
    쓴다(Redmine 노트와 같은 문구). 🔴 명령형 없음 — 모듈 규칙(`render` 머리말)과 같다."""
    if res.get("text"):
        return str(res["text"])
    oc = str(res.get("outcome") or "")
    out = [f"[⑦ 대기 결과] {res.get('work_id') or '(id 없음)'} · 라운드 {res.get('round')} · "
           f"결과 {oc} — {WAIT_LABEL.get(oc, oc or '미상')}"]
    meta = [x for x in (f"큐 상태 {res['merge_status']}" if res.get("merge_status") else "",
                        f"조각 {res.get('verified', 0)}/{res.get('total', 0)} verified"
                        if res.get("total") is not None else "",
                        f"준비 기록 {res.get('record_state') or '없음'}") if x]
    out.append("  " + " · ".join(meta))
    for t in res.get("failed_tasks") or []:
        out.append(f"  조각 {t.get('status')} {t.get('task_id')}: {t.get('reason') or '사유 없음'}")
    if res.get("terminal_reason"):
        out.append(f"  사유: {str(res['terminal_reason'])[:500]}")
    if res.get("last_error"):
        out.append(f"  마지막 큐 조회 오류: {str(res['last_error'])[:300]}")
    out.append(f"  조회 {res.get('polls', 0)}회 · 경과 {_mmss(res.get('elapsed') or 0)}")
    return "\n".join(out)


def wait_for_gate(repo, work_id: str, *, api=None, state=None, interval: float = 30,
                  timeout: float = 5400, clock=time.monotonic, sleep=time.sleep,
                  logf=None) -> dict:
    """이번 라운드의 ⑦ 준비가 끝난 결과(또는 work 종결·타임아웃)까지 읽기만 하며 기다린다.

    매 조회: 큐의 work(`GET /api/v1/works/<id>`) → 그 work 의 **지금** 라운드 →
    `recorded_for(repo, work_id, 그 라운드)`. 라운드는 개선요청으로만 바뀌므로 매번 다시 읽는다.

        outcome   at_gate · stopped · error   그 라운드의 준비 기록 (facts · question · text=render)
                  terminal_rejected · terminal_cancelled   work 종결 (실패 조각 사유)
                  merged                      work 마감
                  timeout                     마지막으로 본 큐 상태·기록 · 마지막 조회 오류

    큐 조회 실패는 로그를 남기고 계속 조회한다 — 끝까지 실패하면 `timeout` + `last_error`.
    조회마다 한 줄(`[wait] … 남은 mm:ss`)을 남긴다 — 기다리는 동안에도 보여야 한다.
    """
    log = logf or C._noop_log
    if api is None:
        api = _resolve_api(repo)          # 못 정하면 FollowupError — 대기를 시작하지 않는다
    t0 = clock()
    deadline = t0 + float(timeout)
    res: dict = {"work_id": work_id, "round": None, "outcome": "", "merge_status": "",
                 "verified": 0, "total": None, "record_state": "", "failed_tasks": [],
                 "terminal_reason": "", "last_error": "", "polls": 0, "elapsed": 0.0,
                 "facts": {}, "question": "", "text": ""}

    def _finish(outcome: str) -> dict:
        res["outcome"] = outcome
        res["elapsed"] = round(clock() - t0, 1)
        res["exit_code"] = WAIT_EXIT.get(outcome, 3)
        log("wait", f"{work_id} r{res['round'] if res['round'] is not None else '?'} 끝 — "
                    f"{outcome} (조회 {res['polls']}회 · 경과 {_mmss(res['elapsed'])})")
        return res

    while True:
        res["polls"] += 1
        rec: dict = {}
        try:
            work, tasks = R.fetch_work(work_id, api=api)
            if not work:
                raise FollowupError(f"큐에 work {work_id} 가 없다")
            res["last_error"] = ""
            rnd = int(work.get("round", 1) or 1)
            res["round"] = rnd
            res["merge_status"] = str(work.get("merge_status") or "")
            rtasks = _round_tasks(work, tasks)
            res["total"] = len(rtasks)
            res["verified"] = sum(1 for t in rtasks if t.get("status") == "verified")
            rec = recorded_for(repo, work_id, rnd, state=state)
            res["record_state"] = str(rec.get("state") or "") if rec else ""
            remain = deadline - clock()
            log("wait", f"{work_id} r{rnd} · 큐 {res['merge_status'] or '?'} · 조각 "
                        f"{res['verified']}/{res['total']} · 준비 {res['record_state'] or '없음'} · "
                        f"남은 {_mmss(remain)}")
            if res["record_state"] in WAIT_RECORDED:
                res["facts"] = rec
                res["question"] = str(rec.get("question") or "")
                res["text"] = render(rec)
                return _finish(res["record_state"])
            if res["merge_status"] == "merged":
                return _finish("merged")
            if res["merge_status"] in WAIT_TERMINAL:
                res["failed_tasks"] = _failed_of(rtasks)
                res["terminal_reason"] = str(work.get("terminal_reason") or "")
                return _finish(f"terminal_{res['merge_status']}")
        except Exception as e:                                     # noqa: BLE001
            res["last_error"] = f"{type(e).__name__}: {e}"[:300]
            log("wait", f"[주의] {work_id} 큐 조회 실패 — {res['last_error']} · 계속 조회한다 · "
                        f"남은 {_mmss(deadline - clock())}")
        remain = deadline - clock()
        if remain <= 0:
            return _finish("timeout")
        sleep(min(float(interval), remain))


# ─────────────────────────────────────────────────────────────
# CLI — 어느 에이전트든, 타이머든 같은 한 줄로 부른다
# ─────────────────────────────────────────────────────────────

def _resolve_api(repo):
    """큐 호출 자리. 마스터는 `runner._api`(review 기본값), 요청자 배달본은 `queue_api(repo)`.
    [주의] 토큰은 여기서 읽지도 찍지도 않는다 — 각 경로가 알아서 든다."""
    try:
        from . import runner as _runner                            # noqa: F401, PLC0415
        return R._default_api
    except ImportError:
        pass
    try:
        from ..clientside.client_mcp import queue_api              # noqa: PLC0415 (배달본)
        return queue_api(Path(repo))
    except ImportError as e:
        raise FollowupError("큐 클라이언트가 없다 — 마스터에서 돌리거나 `api=` 를 주입하라") from e


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m master.work.followup",
                                 description="라운드 종결 뒤 ⑦ 준비 (confirm=False — push 없음)")
    ap.add_argument("work_id", nargs="?", default="")
    ap.add_argument("--scan", action="store_true", help="열린 work 를 훑어 종결·미준비 라운드만 준비한다")
    ap.add_argument("--force", action="store_true", help="이미 기록된 라운드도 다시 준비한다 (work_id 지정 때만)")
    ap.add_argument("--repo", default=".", help="정본 체크아웃 (기본: 현재 디렉토리)")
    ap.add_argument("--kind", choices=KINDS, default=None)
    ap.add_argument("--project", default="")
    ap.add_argument("--start-dir", default="")
    ap.add_argument("--pattern", default="")
    ap.add_argument("--python", default="")
    ap.add_argument("--ue5-cmd", default="")
    ap.add_argument("--remote", default=R.DEFAULT_REMOTE)
    ap.add_argument("--state-dir", default="")
    ap.add_argument("--wait", action="store_true",
                    help="준비하지 않고 이 work 의 지금 라운드 ⑦ 준비 결과까지 읽기만 하며 기다린다")
    ap.add_argument("--interval", type=float, default=30.0, help="--wait 조회 간격(초)")
    ap.add_argument("--timeout", type=float, default=5400.0, help="--wait 최대 대기(초)")
    ns = ap.parse_args(argv)
    if bool(ns.scan) == bool(ns.work_id):
        ap.error("`<work_id>` 와 `--scan` 중 하나만 준다")
    if ns.scan and ns.force:
        ap.error("--force 는 work_id 하나에만 쓴다 (scan 전체를 다시 돌리지 않는다)")
    if ns.wait and (ns.scan or ns.force):
        ap.error("--wait 는 work_id 하나에만 쓰고 --scan·--force 와 함께 쓰지 않는다 (읽기 전용)")
    if ns.wait and (ns.interval <= 0 or ns.timeout <= 0):
        ap.error("--interval·--timeout 은 0 보다 커야 한다")
    repo = Path(ns.repo).resolve()
    try:
        api = _resolve_api(repo)
    except FollowupError as e:
        stderr_log("followup", f"[중요] {e}")
        print(json.dumps({"state": "error", "reason": str(e)}, ensure_ascii=False, indent=2))
        return 1
    if ns.wait:
        # stdout 은 결과 블록 하나, 조회마다의 줄은 stderr. 종료 코드: 0 at_gate ·
        # 3 stopped/error/terminal_*/merged · 4 timeout · 2 사용법
        res = wait_for_gate(repo, ns.work_id, api=api, state=ns.state_dir or None,
                            interval=ns.interval, timeout=ns.timeout, logf=stderr_log)
        print(render_wait(res))
        return int(res.get("exit_code", 3))
    kw = dict(kind=ns.kind, start_dir=ns.start_dir, pattern=ns.pattern, python=ns.python,
              ue5_cmd=ns.ue5_cmd, remote=ns.remote)
    if ns.scan:
        res = scan(repo, project=ns.project, api=api, state=ns.state_dir or None,
                   logf=stderr_log, **kw)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0 if res.get("ok") else 1
    res = prepare_once(repo, ns.work_id, None, state=ns.state_dir or None, force=ns.force,
                       api=api, logf=stderr_log, project=ns.project, **kw)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    # 종료 코드: 준비를 못 했으면 1. running·stopped·at_gate·건너뜀은 정상 결과다
    st = (res.get("result") or {}).get("state")
    return 1 if (st == "error" or res.get("skip") == "round_unknown") else 0


if __name__ == "__main__":
    sys.exit(main())
