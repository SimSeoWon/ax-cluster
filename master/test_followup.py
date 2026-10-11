"""`work/followup.py` 계약 테스트 (`#798`) — ⑦ 준비 한 입구.

[중요] 첫 단정은 **「`advance_work` 에 confirm=True 가 절대 가지 않는다」**다. 이 입구는
사람 게이트 **앞**에서 멈추는 자리이고, 그 계약이 깨지면 승인 없는 전진이 된다.
큐·전진·검사는 전부 주입한 대역이다 — 네트워크·실제 큐를 쓰지 않는다. 회귀 판정만은
임시 git 저장소와 임시 스크립트로 **실제로** 돌린다(주입만으로는 계약만 잰다).

실행: .venv/bin/python master/test_followup.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import followup as F       # noqa: E402
from master.work import review as R         # noqa: E402

PASS = FAIL = 0


def check(name: str, cond, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── 대역 ────────────────────────────────────────────────────────────────────

def _fetch(work: dict, tasks: list):
    def f(work_id, *, api=None):
        return dict(work), [dict(t) for t in tasks]
    return f


class AdvanceSpy:
    """`advance_work` 대역 — 받은 인자를 전부 기록한다."""

    def __init__(self, *, error: str = "", build_passed=True):
        self.calls = []
        self.error, self.build_passed = error, build_passed

    def __call__(self, repo, **kw):
        self.calls.append(kw)
        a = R.Advance(work_id=kw["work_id"], target_branch="task/w1/base",
                      before="a" * 40, head="b" * 40, tree=f"/x/ax-advance-{kw['work_id']}",
                      merged=["task/w1/r1/t1"], commands=["git push …"])
        if self.error:
            a.error = self.error
            return a
        a.build_passed, a.build_note = self.build_passed, "통합 TESTS OK (3) · 회귀 1/1"
        a.ok = True
        return a


def _bfn(tree):
    return {"ok": True, "passed": True, "summary": "fake"}


WORK_READY = {"work_id": "w1", "merge_status": "ready_for_review", "round": 1, "project": "AXCluster"}
TASKS_DONE = [{"task_id": "t1", "status": "verified", "round": 1},
              {"task_id": "t2", "status": "verified", "round": 1}]


# ── 상태 갈래 ───────────────────────────────────────────────────────────────

def test_running_has_no_side_effects():
    spy = AdvanceSpy()
    w = dict(WORK_READY, merge_status="in_progress")
    fu = F.prepare_round(Path("/nonexistent"), "w1", fetch=_fetch(w, [
        {"task_id": "t1", "status": "verified", "round": 1},
        {"task_id": "t2", "status": "claimed", "round": 1}]), advance=spy, build_fn=_bfn)
    check("도는 중 → running", fu.state == "running", fu.state)
    check("도는 중 → advance 안 부름", not spy.calls)
    check("도는 중 → 조각 수를 센다", fu.counts == {"verified": 1, "claimed": 1}, str(fu.counts))
    check("도는 중 → 로그가 남는다", any("[fetch]" in ln for ln in fu.log), str(fu.log))


def test_ready_calls_advance_with_confirm_false():
    spy = AdvanceSpy()
    fu = F.prepare_round(Path("/r"), "w1", api="API", fetch=_fetch(WORK_READY, TASKS_DONE),
                         advance=spy, build_fn=_bfn)
    check("ready → at_gate", fu.state == "at_gate", f"{fu.state} {fu.reason}")
    check("ready → advance 한 번", len(spy.calls) == 1, str(len(spy.calls)))
    kw = spy.calls[0] if spy.calls else {}
    check("[중요] confirm=False", kw.get("confirm") is False, str(kw.get("confirm")))
    check("keep_tree=True", kw.get("keep_tree") is True)
    # `#798` — 검사 결과 원본을 붙잡으려 감싼다. 호출하면 원래 build_fn 의 결과가 그대로 나온다
    bf = kw.get("build_fn")
    check("build_fn 이 감싸여 그대로 돈다", callable(bf) and bf("/t") == _bfn("/t"), str(bf))
    check("api 를 넘긴다", kw.get("api") == "API")
    check("트리·HEAD 를 돌려준다", fu.tree.endswith("ax-advance-w1") and fu.head == "b" * 40)
    check("빌드 판정을 싣는다", fu.build_passed is True)
    check("사람에게 물을 문장이 있다", "구조" in fu.question, fu.question)
    check("push 안 함", fu.pushed is False)
    check("게이트 로그가 남는다", any("[gate]" in ln for ln in fu.log), str(fu.log))
    d = fu.to_dict()
    check("to_dict 는 JSON 직렬화된다", isinstance(__import__("json").dumps(d, ensure_ascii=False), str))


def test_rejected_and_cancelled_stop():
    for st in ("rejected", "cancelled", "merged"):
        spy = AdvanceSpy()
        w = dict(WORK_READY, merge_status=st, terminal_reason="조각 실행 실패")
        fu = F.prepare_round(Path("/r"), "w1", fetch=_fetch(w, TASKS_DONE), advance=spy,
                             build_fn=_bfn)
        check(f"{st} → stopped", fu.state == "stopped", fu.state)
        check(f"{st} → advance 안 부름", not spy.calls)


def test_failed_task_stops():
    spy = AdvanceSpy()
    tasks = [{"task_id": "t1", "status": "verified", "round": 1},
             {"task_id": "t2", "status": "failed", "round": 1, "failure": "층1 차단"}]
    fu = F.prepare_round(Path("/r"), "w1", fetch=_fetch(WORK_READY, tasks), advance=spy,
                         build_fn=_bfn)
    check("실패 조각 → stopped", fu.state == "stopped", fu.state)
    check("실패 조각 → advance 안 부름", not spy.calls)
    check("실패 사실을 싣는다", fu.failed_tasks and fu.failed_tasks[0]["reason"] == "층1 차단",
          str(fu.failed_tasks))


def test_previous_round_failure_does_not_block():
    """지난 라운드 실패 조각은 이번 라운드 판정에 끼지 않는다 (`advance_work` 와 같은 거르기)."""
    spy = AdvanceSpy()
    w = dict(WORK_READY, round=2)
    tasks = [{"task_id": "t0", "status": "failed", "round": 1},
             {"task_id": "t1", "status": "verified", "round": 2}]
    fu = F.prepare_round(Path("/r"), "w1", fetch=_fetch(w, tasks), advance=spy, build_fn=_bfn)
    check("지난 라운드 실패는 무시 → at_gate", fu.state == "at_gate", f"{fu.state} {fu.reason}")


def test_ready_but_unfinished_is_error():
    spy = AdvanceSpy()
    tasks = [{"task_id": "t1", "status": "verified", "round": 1},
             {"task_id": "t2", "status": "pending", "round": 1}]
    fu = F.prepare_round(Path("/r"), "w1", fetch=_fetch(WORK_READY, tasks), advance=spy,
                         build_fn=_bfn)
    check("ready 인데 미종결 → error (모순)", fu.state == "error", fu.state)
    check("모순 → advance 안 부름", not spy.calls)


def test_index_only_refused_before_tree():
    spy = AdvanceSpy()
    fu = F.prepare_round(Path("/r"), "w1", kind="index_only", fetch=_fetch(WORK_READY, TASKS_DONE),
                         advance=spy)
    check("index_only → error", fu.state == "error", fu.state)
    check("index_only 사유", "index_only" in fu.reason, fu.reason)
    check("index_only → 트리를 세우지 않는다", not spy.calls)


def test_unknown_kind_refused():
    spy = AdvanceSpy()
    d = Path(tempfile.mkdtemp(prefix="fu-kind-"))
    try:
        fu = F.prepare_round(d, "w1", fetch=_fetch(dict(WORK_READY, project=""), TASKS_DONE),
                             advance=spy)
        check("타입 미상 → error", fu.state == "error", fu.state)
        check("타입 미상 → unreal 로 추정하지 않는다", not spy.calls)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_unreal_without_engine_refused():
    """unreal 은 `build_local.local_build_fn` 에 맡긴다 — 엔진을 못 찾으면 그쪽이 만들 때 죽는다."""
    spy = AdvanceSpy()
    d = Path(tempfile.mkdtemp(prefix="fu-ue-"))
    try:
        fu = F.prepare_round(d, "w1", kind="unreal", fetch=_fetch(WORK_READY, TASKS_DONE),
                             advance=spy)
        check("unreal 엔진 없음 → error", fu.state == "error", fu.state)
        check("unreal 사유는 build_local 의 것", "Build.bat" in fu.reason, fu.reason)
        check("unreal 엔진 없음 → 트리 안 세움", not spy.calls)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_advance_error_reported():
    spy = AdvanceSpy(error="durable 머지 충돌")
    fu = F.prepare_round(Path("/r"), "w1", fetch=_fetch(WORK_READY, TASKS_DONE), advance=spy,
                         build_fn=_bfn)
    check("advance 실패 → error", fu.state == "error" and "충돌" in fu.reason, fu.reason)
    check("advance 실패 → 물음 없음", fu.question == "")


def test_fetch_failure_reported():
    def boom(work_id, *, api=None):
        raise RuntimeError("queue down")
    fu = F.prepare_round(Path("/r"), "w1", fetch=boom, advance=AdvanceSpy(), build_fn=_bfn)
    check("큐 조회 실패 → error", fu.state == "error" and "queue down" in fu.reason, fu.reason)


def test_source_never_passes_confirm_true():
    """[중요] 코드에 `confirm=True` 가 **없다** — 인자로도 열지 않는다."""
    src = (Path(F.__file__)).read_text(encoding="utf-8")
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    check("[중요] confirm=True 문자열이 실코드에 없다", "confirm=True" not in code.replace(
        "confirm=True 를 넘기지 않는다", ""))
    check("advance 호출은 confirm=False 고정", "confirm=False, keep_tree=True" in src)
    import inspect
    check("prepare_round 에 confirm 인자가 없다",
          "confirm" not in inspect.signature(F.prepare_round).parameters)


# ── code 판 build_fn ────────────────────────────────────────────────────────

def _git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def _repo_with_change() -> Path:
    """base 커밋 → master/foo.py 수정 커밋. master/test_foo.py 는 base 에 있다."""
    d = Path(tempfile.mkdtemp(prefix="fu-code-"))
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "master").mkdir()
    (d / "tests" / "integration").mkdir(parents=True)
    (d / "tests" / "integration" / "checks.json").write_text(
        '[{"path": "master/test_bar.py", "count_pattern": "x", "timeout": 1}]', encoding="utf-8")
    (d / "master" / "foo.py").write_text("X = 1\n", encoding="utf-8")
    (d / "master" / "bar.py").write_text("Y = 1\n", encoding="utf-8")
    (d / "master" / "test_foo.py").write_text(
        "print('OK test_foo: 3/3 통과')\n", encoding="utf-8")
    (d / "master" / "test_bar.py").write_text("print('1/1 통과')\n", encoding="utf-8")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    _git(d, "branch", "basebr")
    (d / "master" / "foo.py").write_text("X = 2\n", encoding="utf-8")
    (d / "master" / "bar.py").write_text("Y = 2\n", encoding="utf-8")
    (d / "master" / "nomatch.py").write_text("Z = 1\n", encoding="utf-8")
    (d / "README.md").write_text("x\n", encoding="utf-8")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "change")
    return d


class _Proc:
    def __init__(self, out, rc=0):
        self.stdout, self.stderr, self.returncode = out, "", rc


UNITTEST_OK = "test_01 ... ok\n\n----\nRan 3 tests in 0.5s\n\nOK\n"
UNITTEST_ZERO = "\n----\nRan 0 tests in 0.0s\n\nOK\n"


def test_regression_mapping():
    d = _repo_with_change()
    try:
        files = F.changed_files(d, "basebr")
        check("바뀐 파일을 읽는다", set(files) == {"master/foo.py", "master/bar.py",
                                                "master/nomatch.py", "README.md"}, str(files))
        targets, notes = F.regression_targets(d, files)
        check("foo.py → master/test_foo.py", targets == ["master/test_foo.py"], str(targets))
        check("공식 목록에 있는 것은 빼고 사유", any("공식 통합 목록" in n for n in notes), str(notes))
        check("대응 없음도 남긴다", any("nomatch.py" in n for n in notes), str(notes))
        check("비 .py 는 대상 아님", not any("README" in n for n in notes))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_code_build_fn_pass_and_fail():
    d = _repo_with_change()
    try:
        argv_seen = []

        def runner(argv, cwd, t):
            argv_seen.append(argv)
            return _Proc(UNITTEST_OK)
        lines = []
        fn = F.code_build_fn(base_ref="basebr", runner=runner,
                             regression_fn=lambda tree, p: {"path": p, "ok": True, "reason": "ok"},
                             logf=lambda s, m: lines.append(m))
        res = fn(d)
        ok, note = R.build_verdict(res)
        check("통합+회귀 통과 → build_verdict 통과", ok is True, note)
        check("공식 명령 그대로 (-f -v)", argv_seen and argv_seen[0][-6:] == [
            "-s", "tests/integration", "-p", "test_axcluster.py", "-f", "-v"], str(argv_seen))
        check("회귀 1건이 돌았다", [r["path"] for r in res["regressions"]] == ["master/test_foo.py"])
        check("검사 로그가 남는다", any("통합 검사 시작" in m for m in lines)
              and any("회귀 master/test_foo.py" in m for m in lines), str(lines))

        fn2 = F.code_build_fn(base_ref="basebr", runner=runner,
                              regression_fn=lambda tree, p: {"path": p, "ok": False, "reason": "rc=1"})
        ok2, note2 = R.build_verdict(fn2(d))
        check("[중요] 회귀 실패 → 통과 아님", ok2 is False, note2)

        fn3 = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: _Proc(UNITTEST_ZERO),
                              regression_fn=lambda tree, p: {"path": p, "ok": True, "reason": "ok"})
        ok3, _ = R.build_verdict(fn3(d))
        check("[중요] 통합 0건 실행 → 통과 아님", ok3 is False)

        fn4 = F.code_build_fn(base_ref="no-such-ref", runner=runner,
                              regression_fn=lambda tree, p: {"path": p, "ok": True, "reason": "ok"})
        ok4, _ = R.build_verdict(fn4(d))
        check("[중요] 바뀐 파일을 못 읽으면 통과 아님", ok4 is False)

        fn5 = F.code_build_fn(base_ref="basebr", start_dir="nope", runner=runner)
        ok5, _ = R.build_verdict(fn5(d))
        check("통합 검사 디렉토리 없음 → 통과 아님", ok5 is False)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_regression_real_subprocess():
    """회귀 판정은 `integration_checks.run_check` 를 실제로 거친다 — 형식 A·B·무수치·rc≠0."""
    d = _repo_with_change()
    try:
        r = F.run_regression(d, "master/test_foo.py")
        check("형식 A `N/M 통과` → 통과", r["ok"] and r["count"] == 3, str(r))
        (d / "master" / "test_b.py").write_text("print('통과 4 · 실패 0')\n", encoding="utf-8")
        r = F.run_regression(d, "master/test_b.py")
        check("형식 B `통과 N · 실패 M` → 통과", r["ok"] and r["count"] == 4, str(r))
        (d / "master" / "test_c.py").write_text("print('hello')\n", encoding="utf-8")
        r = F.run_regression(d, "master/test_c.py")
        check("[중요] 수치 없음 → 통과 아님", not r["ok"] and "읽지 못했다" in r["reason"], str(r))
        (d / "master" / "test_e.py").write_text("import sys\nprint('2/2 통과')\nsys.exit(1)\n",
                                                 encoding="utf-8")
        r = F.run_regression(d, "master/test_e.py")
        check("[중요] rc≠0 → 통과 아님", not r["ok"] and "exit 1" in r["reason"], str(r))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_build_fn_for_code_defaults_to_official_manifest():
    d = _repo_with_change()
    try:
        fn = F.build_fn_for("code", repo=d, base_ref="origin/task/w1/base")
        check("checks.json 이 있으면 공식 명령", "-s tests/integration -p test_axcluster.py -f -v"
              in fn.command, fn.command)
        try:
            F.build_fn_for("code", repo=Path("/nonexistent-x"), base_ref="x")
            check("검사 위치 미상 → 거절", False)
        except F.FollowupError:
            check("검사 위치 미상 → 거절", True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 멱등 · 잠금 · scan ─────────────────────────────────────────────────────

class PrepareSpy:
    """`prepare_round` 대역 — 부른 (work_id, expect_round) 를 기록하고 정해진 state 를 돌려준다."""

    def __init__(self, state="at_gate"):
        self.calls, self.state = [], state

    def __call__(self, repo, work_id, **kw):
        self.calls.append((work_id, kw.get("expect_round"), kw.get("project")))
        return F.Followup(work_id=work_id, state=self.state, round=kw.get("expect_round") or 1,
                          reason="fake", tree=f"/x/ax-advance-{work_id}", head="c" * 40)


def _works(*rows):
    return lambda api, project: [dict(r) for r in rows]


def test_scan_baseline_then_only_new_terminal_rounds():
    sd = Path(tempfile.mkdtemp(prefix="fu-state-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-repo-"))
    try:
        spy, lines = PrepareSpy(), []
        logf = lambda s, m: lines.append(f"[{s}] {m}")
        old = {"work_id": "old", "merge_status": "ready_for_review", "round": 1}
        # ① 첫 주기 = 기준선: 이미 종결된 라운드는 준비하지 않는다
        r = F.scan(repo, project="P", state=sd, list_works=_works(old),
                   once=lambda *a, **k: F.prepare_once(*a, prepare=spy, **k), logf=logf)
        check("첫 주기는 기준선", r["baseline"] is True and not spy.calls, str(r))
        check("기준선 키를 로그로 남긴다", any("기준선 old r1" in ln for ln in lines), str(lines))
        # ② 다음 주기: 새로 끝난 라운드만, 도는 것·마감은 빼고
        rows = (old,
                {"work_id": "new", "merge_status": "ready_for_review", "round": 1},
                {"work_id": "run", "merge_status": "in_progress", "round": 1},
                {"work_id": "rej", "merge_status": "rejected", "round": 2})
        lines.clear()
        r = F.scan(repo, project="P", state=sd, list_works=_works(*rows),
                   once=lambda *a, **k: F.prepare_once(*a, prepare=spy, **k), logf=logf)
        got = sorted((c[0], c[1]) for c in spy.calls)
        check("종결·미준비 라운드만 준비 (new·rej)", got == [("new", 1), ("rej", 2)], str(got))
        check("기준선 라운드는 건너뛴다", r["skipped"].get("old/r1") == "baseline", str(r["skipped"]))
        check("도는 work 는 running 사유", r["skipped"].get("run/r1", "").startswith("running"),
              str(r["skipped"]))
        check("프로젝트가 준비로 간다", all(c[2] == "P" for c in spy.calls), str(spy.calls))
        check("tick 한 줄이 남는다", sum("tick P" in ln for ln in lines) == 1, str(lines))
        # ③ 둘째 주기: 아무것도 다시 돌리지 않는다
        n = len(spy.calls)
        lines.clear()
        r = F.scan(repo, project="P", state=sd, list_works=_works(*rows),
                   once=lambda *a, **k: F.prepare_once(*a, prepare=spy, **k), logf=logf)
        check("[중요] 둘째 주기는 재준비 없음", len(spy.calls) == n, str(spy.calls))
        check("이미 준비 사유", r["skipped"].get("new/r1") == "already_prepared", str(r["skipped"]))
        check("반려는 already_stopped 가 아니라 기록대로",
              r["skipped"].get("rej/r2") == "already_prepared", str(r["skipped"]))
        check("할 일이 없어도 tick 한 줄", sum("tick P" in ln for ln in lines) == 1, str(lines))
        # ④ 개선요청으로 라운드가 오르면 새 키 → 다시 준비
        rows2 = ({"work_id": "new", "merge_status": "ready_for_review", "round": 2},)
        F.scan(repo, project="P", state=sd, list_works=_works(*rows2),
               once=lambda *a, **k: F.prepare_once(*a, prepare=spy, **k), logf=logf)
        check("[중요] round+1 은 준비된다", spy.calls[-1][:2] == ("new", 2), str(spy.calls[-1]))
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_prepare_once_lock_contention_and_stale():
    sd = Path(tempfile.mkdtemp(prefix="fu-lock-"))
    try:
        spy, lines = PrepareSpy(), []
        logf = lambda s, m: lines.append(m)
        path = F.round_key_path(sd, "/r", "w9", 1)
        lock = path.with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("otherhost pid=1")                 # 살아 있는 잠금(방금 만든 mtime)
        r = F.prepare_once("/r", "w9", 1, state=sd, prepare=spy, logf=logf)
        check("[중요] 잠금 경합 → locked 로 건너뜀", r["skip"] == "locked" and not spy.calls, str(r))
        check("경합도 로그를 남긴다", any("잡고 있다" in ln for ln in lines), str(lines))
        import os
        os.utime(lock, (time.time() - 300, time.time() - 300))   # 하트비트 끊긴 지 300초
        r = F.prepare_once("/r", "w9", 1, state=sd, prepare=spy, logf=logf)
        check("죽은 잠금은 지우고 진행", r["action"] == "prepared" and len(spy.calls) == 1, str(r))
        check("죽은 잠금 사유를 로그로", any("죽은 잠금" in ln and "otherhost" in ln for ln in lines),
              str(lines))
        check("끝나면 잠금을 푼다", not lock.exists())
        r = F.prepare_once("/r", "w9", 1, state=sd, prepare=spy, logf=logf)
        check("재호출 → already_prepared", r["skip"] == "already_prepared" and len(spy.calls) == 1)
        r = F.prepare_once("/r", "w9", 1, state=sd, prepare=spy, force=True, logf=logf)
        check("--force 는 다시 준비", r["action"] == "prepared" and len(spy.calls) == 2)
    finally:
        shutil.rmtree(sd, ignore_errors=True)


def test_prepare_once_records_only_final_states():
    sd = Path(tempfile.mkdtemp(prefix="fu-rec-"))
    try:
        run = PrepareSpy(state="running")
        F.prepare_once("/r", "a", 1, state=sd, prepare=run)
        F.prepare_once("/r", "a", 1, state=sd, prepare=run)
        check("running 은 기록 안 함 → 매 주기 다시 본다", len(run.calls) == 2)
        stale = PrepareSpy(state="stale_round")
        F.prepare_once("/r", "b", 1, state=sd, prepare=stale)
        F.prepare_once("/r", "b", 1, state=sd, prepare=stale)
        check("stale_round 도 기록 안 함", len(stale.calls) == 2)
        err = PrepareSpy(state="error")
        F.prepare_once("/r", "c", 1, state=sd, prepare=err)
        r = F.prepare_once("/r", "c", 1, state=sd, prepare=err)
        check("error 는 기록 → 매분 재시도 안 함", len(err.calls) == 1 and r["skip"] == "previous_error",
              str(r))
        jl = (sd / "followup.jsonl").read_text(encoding="utf-8")
        check("jsonl 에 시작·끝이 남는다", "prepare_started" in jl and "prepare_done" in jl)
    finally:
        shutil.rmtree(sd, ignore_errors=True)


def test_prepare_round_stale_round():
    spy = AdvanceSpy()
    fu = F.prepare_round(Path("/r"), "w1", expect_round=2, fetch=_fetch(WORK_READY, TASKS_DONE),
                         advance=spy, build_fn=_bfn)
    check("기대 라운드 불일치 → stale_round · 부작용 없음", fu.state == "stale_round" and not spy.calls,
          fu.state)


def test_scan_refuses_without_project_and_logs():
    sd = Path(tempfile.mkdtemp(prefix="fu-np-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-np-repo-"))
    try:
        lines = []
        import os
        old = os.environ.pop("AX_PROJECTS_ROOT", None)
        os.environ["AX_PROJECTS_ROOT"] = str(repo)          # 마운트 없는 빈 레지스트리
        try:
            r = F.scan(repo, state=sd, list_works=_works(), logf=lambda s, m: lines.append(m))
        finally:
            if old is None:
                os.environ.pop("AX_PROJECTS_ROOT", None)
            else:
                os.environ["AX_PROJECTS_ROOT"] = old
        check("프로젝트 없음 → 거절", r["ok"] is False and r["reason"] == "no_project", str(r))
        check("거절도 한 줄 남긴다", any("프로젝트를 정할 수 없다" in ln for ln in lines), str(lines))
        lines.clear()

        def boom(api, project):
            raise RuntimeError("queue down")
        r = F.scan(repo, project="P", state=sd, list_works=boom, logf=lambda s, m: lines.append(m))
        check("목록 실패도 tick 로그", r["ok"] is False and any("목록 조회 실패" in ln for ln in lines))
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


# ── `#798` ⓐⓑⓒ — 사실 렌더 · Redmine 노트 · 기록 조회 ───────────────────────────────

IMPERATIVES = ("하세요", "하라", "해 주세요", "해주세요", "말고", "보고한다", "묻지", "넘겨라",
               "확인할 것")


def _sample_facts() -> dict:
    fu = F.Followup(work_id="w798", state="at_gate", merge_status="ready_for_review", round=2,
                    project="AXCluster", title="⑦ 자동 준비", redmine_issue_id=798, kind="code",
                    kind_source="프로필", tree="/home/sim/ax-advance-w798",
                    target_branch="task/w798/base", before="1" * 40, head="2" * 40,
                    merged=["task/w798/r2/a", "task/w798/r2/b"], conflicts=False,
                    build_passed=True, build_note="통합 TESTS OK (12) · 회귀 1/1",
                    question=R.Advance(build_passed=True).question,
                    checks=F.check_counts({"integration": {"passed": True, "summary": "TESTS OK (12)"},
                                           "regressions": [{"path": "master/test_followup.py",
                                                            "ok": True, "reason": "88건 통과"}]}))
    return dict(fu.facts(), origin="timer", at=1760140800.0)


def test_render_facts_only():
    txt = F.render(_sample_facts())
    for want in ("w798", "라운드 2", "at_gate", "승인 대기", "/home/sim/ax-advance-w798",
                 "222222222222", "충돌 없음", "항목 통과 2", "실패 0", "Redmine #798",
                 "게이트 물음(원문 인용)", "타이머(scan)", "task/w798/base"):
        check(f"렌더에 사실 `{want}`", want in txt, txt)
    for bad in IMPERATIVES:
        check(f"[중요] 렌더에 명령형 `{bad}` 없음", bad not in txt, txt)
    # 멈춤·오류도 사실만
    for st, reason in (("stopped", "이번 라운드 조각 1건이 실패·취소다 — 머지하지 않았다"),
                       ("error", "타입을 정할 수 없다(`비어 있음`) — `--kind`(unreal/code/index_only) "
                                 "인자도 배달 설정 `kind` 도 없다. 추정하지 않는다")):
        t2 = F.render({"work_id": "w", "round": 1, "state": st, "reason": reason})
        check(f"{st} 렌더에 사유", reason in t2, t2)
        for bad in IMPERATIVES:
            check(f"[중요] {st} 렌더에 명령형 `{bad}` 없음", bad not in t2, t2)


class NoteSpy:
    def __init__(self, ok=True, raise_=None):
        self.calls, self.ok, self.raise_ = [], ok, raise_

    def __call__(self, api, **kw):
        self.calls.append(kw)
        if self.raise_:
            raise self.raise_
        return {"ok": self.ok, "result": "갱신" if self.ok else "[주의] 실패"}


class IssueSpy(PrepareSpy):
    def __call__(self, repo, work_id, **kw):
        fu = super().__call__(repo, work_id, **kw)
        fu.redmine_issue_id, fu.project = 798, "AXCluster"
        return fu


def test_note_once_per_round():
    sd = Path(tempfile.mkdtemp(prefix="fu-note-"))
    try:
        note, prep = NoteSpy(), IssueSpy()
        r1 = F.prepare_once("/r", "w1", 1, state=sd, prepare=prep, note=note, origin="timer")
        r2 = F.prepare_once("/r", "w1", 1, state=sd, prepare=prep, note=note, origin="hook")
        check("[중요] (work, 라운드) 당 노트 한 번", len(note.calls) == 1, str(note.calls))
        c = note.calls[0] if note.calls else {}
        check("노트는 work 의 이슈·프로젝트로", c.get("issue_id") == 798 and c.get("project") == "AXCluster"
              and c.get("work_id") == "w1", str(c))
        check("노트 본문은 render 사실", "[⑦ 준비 결과] w1" in c.get("text", "") and "Redmine #798" in c.get("text", ""))
        for bad in IMPERATIVES:
            check(f"노트에 명령형 `{bad}` 없음", bad not in c.get("text", ""))
        check("기록에 노트 결과", (r1.get("facts") or {}).get("note", {}).get("ok") is True, str(r1))
        check("재호출은 기록을 돌려준다(facts 포함)",
              r2["skip"] == "already_prepared" and r2["facts"]["state"] == "at_gate"
              and r2["facts"]["note"]["ok"] is True and r2["facts"]["origin"] == "timer", str(r2))
        F.prepare_once("/r", "w1", 2, state=sd, prepare=prep, note=note)
        check("라운드가 오르면 새 노트", len(note.calls) == 2)
        # 실패 노트 — 기록되고 재시도하지 않는다
        bad = NoteSpy(raise_=OSError("queue down"))
        F.prepare_once("/r", "w2", 1, state=sd, prepare=IssueSpy(state="error"), note=bad)
        F.prepare_once("/r", "w2", 1, state=sd, prepare=IssueSpy(state="error"), note=bad)
        rec = F.recorded_for("/r", "w2", 1, state=sd)
        check("노트 실패가 기록에 남는다", rec.get("note", {}).get("ok") is False
              and "queue down" in rec["note"].get("error", ""), str(rec))
        check("실패 노트도 한 번만 시도", len(bad.calls) == 1)
        # 이슈 없는 work → 노트 없음 + 사유
        F.prepare_once("/r", "w3", 1, state=sd, prepare=PrepareSpy(state="stopped"), note=note)
        check("이슈 없으면 노트 안 부름", len(note.calls) == 2)
        jl = (sd / "followup.jsonl").read_text(encoding="utf-8")
        for ev in ("note_posted", "note_failed", "note_skipped", "prepare_reused"):
            check(f"jsonl 사건 `{ev}`", f'"{ev}"' in jl)
        # running 은 기록이 없으니 노트도 없다
        F.prepare_once("/r", "w4", 1, state=sd, prepare=IssueSpy(state="running"), note=note)
        check("running 은 노트 없음", len(note.calls) == 2)
    finally:
        shutil.rmtree(sd, ignore_errors=True)


def test_post_note_uses_queue_route():
    calls = []
    def api(method, path, payload=None):
        calls.append((method, path, payload))
        return {"ok": True, "result": "ok"}
    got = F.post_note(api, issue_id=7, text="t", project="P", work_id="w")
    check("요청자 redmine_note 와 같은 큐 라우트",
          calls == [("POST", "/api/v1/redmine/note",
                     {"issue_id": 7, "notes": "t", "project": "P", "work_id": "w"})], str(calls))
    check("응답 그대로", got.get("ok") is True)


def test_recorded_for_lookup():
    sd = Path(tempfile.mkdtemp(prefix="fu-recf-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-recf-repo-"))
    try:
        F.prepare_once(repo, "w5", 1, state=sd, prepare=PrepareSpy(state="stopped"))
        F.prepare_once(repo, "w5", 2, state=sd, prepare=PrepareSpy(state="at_gate"))
        check("라운드 지정 조회", F.recorded_for(repo, "w5", 1, state=sd).get("state") == "stopped")
        latest = F.recorded_for(repo, "w5", state=sd)
        check("라운드 없으면 가장 높은 라운드", latest.get("round") == 2 and latest.get("state") == "at_gate",
              str(latest))
        check("다른 체크아웃은 안 맞는다", F.recorded_for("/elsewhere", "w5", state=sd) == {})
        check("없는 work 는 빈 값", F.recorded_for(repo, "nope", 1, state=sd) == {})
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_check_counts_and_capture():
    c = F.check_counts({"integration": {"passed": True, "summary": "TESTS OK (3)"},
                        "regressions": [{"path": "a", "ok": True}, {"path": "b", "ok": False,
                                                                     "reason": "rc=1"}]})
    check("code 판 항목 수", c["passed"] == 2 and c["failed"] == 1 and len(c["items"]) == 3, str(c))
    u = F.check_counts({"passed": False, "summary": "UE5 FAILED"})
    check("unreal 판 1항목", u["passed"] == 0 and u["failed"] == 1, str(u))
    check("결과 없음은 빈 값(0 실패로 접지 않는다)", F.check_counts(None) == {})

    class CallingAdvance(AdvanceSpy):
        def __call__(self, repo, **kw):
            res = kw["build_fn"]("/tree")
            a = super().__call__(repo, **kw)
            a.build_passed, a.build_note = R.build_verdict(res)
            return a
    def bfn(tree):
        return {"ok": False, "passed": False, "summary": "s",
                "integration": {"passed": True, "summary": "TESTS OK (4)"},
                "regressions": [{"path": "master/test_x.py", "ok": False, "reason": "rc=1"}]}
    fu = F.prepare_round(Path("/r"), "w1", fetch=_fetch(dict(WORK_READY, redmine_issue_id=12,
                                                             title="T"), TASKS_DONE),
                         advance=CallingAdvance(), build_fn=bfn)
    check("prepare_round 가 검사 항목 수를 잡는다",
          fu.checks.get("passed") == 1 and fu.checks.get("failed") == 1, str(fu.checks))
    check("work 의 이슈·제목·프로젝트를 싣는다",
          fu.redmine_issue_id == 12 and fu.title == "T" and fu.project == "AXCluster")


def test_resolve_kind_from_delivered_config():
    repo = Path(tempfile.mkdtemp(prefix="fu-kind-"))
    try:
        (repo / ".ax").mkdir()
        (repo / ".ax/config.json").write_text('{"kind": "unreal"}', encoding="utf-8")
        check("배달 설정 kind 를 읽는다 (요청자 — 프로필 없음)",
              F.resolve_kind(repo, "", "") == ("unreal", ".ax/config.json kind"))
        (repo / ".ax/config.json").write_text('{"kind": "weird"}', encoding="utf-8")
        check("모르는 kind 는 쓰지 않는다", F.resolve_kind(repo, "", "") == ("", ""))
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_failure_tail_is_kept_and_rendered():
    """실측 2026-10-11 (#798 5a): 실패 판정만 남고 원문이 없어 원인을 못 봤다 — 꼬리를 남긴다."""
    d = _repo_with_change()
    try:
        err = ("test_06 ... ok\ntest_07_test_revise ... FAIL\n\n"
               "======================================================================\n"
               "FAIL: test_07_test_revise (test_axcluster.AXClusterChecks)\n"
               "Traceback (most recent call last):\n  File \"x.py\", line 9\n"
               "AssertionError: master/test_revise.py rc=1 · 통과 66 · 실패 1\n\n"
               "Ran 7 tests in 3.6s\n\nFAILED (failures=1)\n")

        class P:
            returncode, stdout, stderr = 1, "[AXCluster] master/x.py: 검사 3건 통과\n", err
        lines = []
        fn = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: P(),
                             regression_fn=lambda tree, p: {"path": p, "ok": False, "reason": "rc=1",
                                                            "tail": "Traceback\nValueError: boom"},
                             logf=lambda s, m: lines.append(m))
        res = fn(d)
        tail = res["integration"].get("tail") or ""
        check("🔴 통합 실패 꼬리가 결과에 남는다", "FAIL: test_07_test_revise" in tail
              and "AssertionError" in tail, tail)
        check("  꼬리는 FAIL 블록부터 (stdout 통과 줄이 아니다)", tail.startswith("FAIL:"), tail[:80])
        check("🔴 실패 꼬리가 로그에 찍힌다", any("실패 원문 꼬리" in m and "AssertionError" in m for m in lines))
        check("  회귀 실패 꼬리도 로그에", any("master/test_foo.py 실패 원문 꼬리" in m for m in lines))
        cc = F.check_counts(res)
        it = {i["name"]: i for i in cc["items"]}
        check("🔴 check_counts 가 꼬리를 싣는다", "AssertionError" in it["통합 검사"].get("tail", ""))
        check("  회귀 실패 꼬리도 싣는다", "ValueError: boom" in it["회귀 master/test_foo.py"].get("tail", ""))
        txt = F.render({"work_id": "w1", "round": 1, "state": "at_gate", "build_passed": False,
                        "checks": cc, "merged": ["x"]})
        check("🔴 렌더(노트·고지)에 꼬리가 보인다", "실패 원문 꼬리" in txt and "AssertionError" in txt, txt)

        class Ok:
            returncode, stdout, stderr = 0, "", "Ran 3 tests in 0.1s\n\nOK\n"
        res2 = F.code_build_fn(base_ref="basebr", runner=lambda a, c, t: Ok(),
                               regression_fn=lambda tree, p: {"path": p, "ok": True, "reason": "ok"})(d)
        check("  통과면 꼬리를 싣지 않는다", "tail" not in res2["integration"]
              and all("tail" not in i for i in F.check_counts(res2)["items"]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    for fn in (test_running_has_no_side_effects,
               test_ready_calls_advance_with_confirm_false,
               test_rejected_and_cancelled_stop,
               test_failed_task_stops,
               test_previous_round_failure_does_not_block,
               test_ready_but_unfinished_is_error,
               test_index_only_refused_before_tree,
               test_unknown_kind_refused,
               test_unreal_without_engine_refused,
               test_advance_error_reported,
               test_fetch_failure_reported,
               test_source_never_passes_confirm_true,
               test_regression_mapping,
               test_code_build_fn_pass_and_fail,
               test_run_regression_real_subprocess,
               test_build_fn_for_code_defaults_to_official_manifest,
               test_scan_baseline_then_only_new_terminal_rounds,
               test_prepare_once_lock_contention_and_stale,
               test_prepare_once_records_only_final_states,
               test_prepare_round_stale_round,
               test_scan_refuses_without_project_and_logs,
               test_render_facts_only,
               test_note_once_per_round,
               test_post_note_uses_queue_route,
               test_recorded_for_lookup,
               test_check_counts_and_capture,
               test_resolve_kind_from_delivered_config,
               test_failure_tail_is_kept_and_rendered):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_followup: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
