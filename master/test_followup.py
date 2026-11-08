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
from unittest.mock import patch

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


def test_regression_selection_rules():
    """`#815` ⑤ — 같은 이름 + 직접 import + 경로 언급. 전이 import 는 고르지 않는다."""
    d = Path(tempfile.mkdtemp(prefix="fu-sel-"))
    try:
        (d / "master" / "work").mkdir(parents=True)
        (d / "tests" / "integration").mkdir(parents=True)
        (d / F.OFFICIAL_MANIFEST).write_text('[{"path": "master/test_official.py"}]', encoding="utf-8")
        files = {
            "master/work/target.py": "X = 1\n",
            "master/work/middle.py": "from master.work import target\n",
            "master/test_target.py": "pass\n",
            "master/test_plain.py": "import master.work.target\n",
            "master/test_multi.py": "from master.work import (\n    other,\n    target,\n)\n",
            "master/test_alias.py": "from master.work import target as T\n",
            "master/test_fromname.py": "from master.work.target import X\n",
            "master/test_path.py": "SRC = 'master/work/target.py'\n",
            "master/test_subpath.py": "# work/target.py 를 배달한다\n",
            "master/test_transitive.py": "from master.work import middle\n",
            "master/test_lookalike.py": "from master.work import targets\nP = 'work/target.pyc_x'\n"
                                        "Q = 'test_target.py'\n",
            "master/test_official.py": "import master.work.target\n",
            "master/test_ontology.py": "import master.work.target\n",
            "master/test_broken.py": "def (:\nfrom master.work import (\n  target,\n)\n",
        }
        for rel, text in files.items():
            (d / rel).write_text(text, encoding="utf-8")
        lines = []
        targets, notes = F.regression_targets(d, ["master/work/target.py", "master/nomatch.py"],
                                              logf=lambda s, m: lines.append(m))
        check("같은 이름이 맨 앞", targets[:1] == ["master/test_target.py"], str(targets))
        want = {"master/test_plain.py", "master/test_multi.py", "master/test_alias.py",
                "master/test_fromname.py", "master/test_path.py", "master/test_subpath.py",
                "master/test_broken.py"}
        check("import(평범·괄호 여러 줄·별칭·from 모듈)·경로 언급을 고른다",
              want <= set(targets), str(targets))
        check("나머지는 정렬", targets[1:] == sorted(targets[1:]), str(targets))
        check("[중요] 전이 import 는 고르지 않는다", "master/test_transitive.py" not in targets)
        check("닮은 이름(targets·.pyc_x·test_target.py)은 아님", "master/test_lookalike.py" not in targets)
        check("공식 목록은 빼고 사유", "master/test_official.py" not in targets
              and any("test_official.py 는 공식 통합 목록" in n for n in notes), str(notes))
        check("중복 없음", len(targets) == len(set(targets)))
        check("마스터 환경 검사는 빼고 사유", "master/test_ontology.py" not in targets
              and any("test_ontology.py — 마스터 환경 검사 — 검사 트리에서 돌지 않는다, 마스터 전수가 돈다"
                      in n for n in notes), str(notes))
        check("이유별 건수 노트", any(n.startswith("master/work/target.py: 회귀 8건 — 같은 이름 1 · "
                                              "import 5 · 경로 2 (공식 목록 제외 1) (마스터 환경 제외 1)")
                                       for n in notes),
              str(notes))
        check("구문 해석 실패는 정규식 대체 + 노트", any("구문 해석 실패" in n and "test_broken.py" in n
                                               for n in notes), str(notes))
        check("대응 없음 노트", any(n.startswith("master/nomatch.py: 대응 회귀 검사 없음") for n in notes))
        check("파일마다 로그 한 줄(선택·이유)", any(m.startswith("회귀 선택 master/work/target.py:")
                                              and "test_plain.py(import)" in m
                                              and "test_path.py(경로)" in m
                                              and "마스터 환경 제외 master/test_ontology.py" in m
                                              for m in lines)
              and any(m == "회귀 선택 master/nomatch.py: 없음" for m in lines), str(lines))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_regression_selection_real_repo():
    """실물 — `work/review.py` 를 고치면 배달 import 를 잡는 `test_client_bundle.py` 가 돈다
    (⑦ 이 같은 이름만 돌려 놓친 사례)."""
    repo = Path(__file__).resolve().parent.parent
    # #815 ⑥ 뒤 두 검사 모두 공식 통합 목록에 들어갔다 — 선택은 되지만 「공식 목록 제외」로
    # notes 에 남아야 한다(조용히 사라지면 안 된다). 경로 언급 선택 규칙 자체는
    # 임시 트리 고정물 test_regression_selection_rules 가 맡는다.
    targets, notes = F.regression_targets(repo, ["master/work/review.py"])
    excl = [n for n in notes if "는 공식 통합 목록에 있다" in n]
    check("실물: review.py → test_client_bundle.py 공식 목록 제외 기록",
          "master/work/review.py: master/test_client_bundle.py 는 공식 통합 목록에 있다 — 거기서 돈다"
          in notes and "master/test_client_bundle.py" not in targets, str(notes))
    check("실물: 같은 이름 test_review.py 가 맨 앞에 제외 기록",
          excl[:1] == ["master/work/review.py: master/test_review.py 는 공식 통합 목록에 있다 — 거기서 돈다"]
          and "master/test_review.py" not in targets, str(notes))
    check("실물: 건수 줄에 공식 목록 제외가 실린다",
          any(n.startswith("master/work/review.py: 회귀 ") and "공식 목록 제외" in n for n in notes),
          str(notes))


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
        # 실패 노트 — 기록에 남고, `#903`(사용자 결정 A) 부터 다음 호출이 **노트만** 다시 보낸다
        bad = NoteSpy(raise_=OSError("queue down"))
        err_prep = IssueSpy(state="error")
        F.prepare_once("/r", "w2", 1, state=sd, prepare=err_prep, note=bad)
        F.prepare_once("/r", "w2", 1, state=sd, prepare=err_prep, note=bad)
        rec = F.recorded_for("/r", "w2", 1, state=sd)
        check("노트 실패가 기록에 남는다", rec.get("note", {}).get("ok") is False
              and "queue down" in rec["note"].get("error", ""), str(rec))
        check("#903 실패 노트는 다음 호출에 재시도된다(준비는 다시 안 한다)",
              len(bad.calls) == 2 and len(err_prep.calls) == 1, f"{len(bad.calls)} {err_prep.calls}")
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


class _Stop(BaseException):
    """프로세스 중단 모사 — `_post_note_once` 의 `except Exception` 을 지나친다."""


def test_note_retry_after_interruption_903():
    """`#903` — 기록 뒤·노트 전/후에 프로세스가 죽어도 다음 주기가 노트를 보낸다(중복 쪽)."""
    for label, sent_before_stop in (("전송 전 중단", False), ("전송 후 저장 전 중단", True)):
        sd = Path(tempfile.mkdtemp(prefix="fu-note903-"))
        try:
            prep, calls = IssueSpy(), []

            def dying(api, **kw):
                if sent_before_stop:
                    calls.append(kw)
                raise _Stop()
            try:
                F.prepare_once("/r", "w", 1, state=sd, prepare=prep, note=dying)
            except _Stop:
                pass
            rec = F.recorded_for("/r", "w", 1, state=sd)
            check(f"{label}: 기록에 노트 대기 표시가 남는다",
                  (rec.get("note") or {}).get("pending") is True, str(rec.get("note")))
            ok = NoteSpy()
            r = F.prepare_once("/r", "w", 1, state=sd, prepare=prep, note=ok)
            check(f"{label}: 다음 호출이 노트를 1회 보낸다 · 준비는 다시 안 한다",
                  len(ok.calls) == 1 and len(prep.calls) == 1 and r.get("skip") == "already_prepared",
                  f"{len(ok.calls)} {prep.calls} {r.get('skip')}")
            rec = F.recorded_for("/r", "w", 1, state=sd)
            check(f"{label}: 기록이 성공으로 바뀐다", (rec.get("note") or {}).get("ok") is True
                  and not (rec.get("note") or {}).get("pending"), str(rec.get("note")))
            F.prepare_once("/r", "w", 1, state=sd, prepare=prep, note=ok)
            check(f"{label}: 그다음 호출은 보내지 않는다", len(ok.calls) == 1)
            text = ok.calls[0].get("text", "") if ok.calls else ""
            check(f"{label}: 노트 본문에 대기·실패 줄이 없다",
                  "기재 실패" not in text and "pending" not in text, text[-300:])
        finally:
            shutil.rmtree(sd, ignore_errors=True)


def test_note_retry_limit_903():
    """`#903` — 실패는 다음 호출마다 재시도, **총 5회** 뒤 멈추고 [중요] 를 한 번 남긴다."""
    sd = Path(tempfile.mkdtemp(prefix="fu-note903-"))
    try:
        bad, prep, lines = NoteSpy(ok=False), IssueSpy(), []
        logf = lambda s, m: lines.append(f"[{s}] {m}")
        for _ in range(8):
            F.prepare_once("/r", "w", 1, state=sd, prepare=prep, note=bad, logf=logf)
        check("총 5회까지만 보낸다", len(bad.calls) == getattr(F, "NOTE_MAX_ATTEMPTS", None) == 5,
              f"{len(bad.calls)} {getattr(F, 'NOTE_MAX_ATTEMPTS', None)}")
        check("준비는 한 번", len(prep.calls) == 1, str(prep.calls))
        rec = F.recorded_for("/r", "w", 1, state=sd)
        n = rec.get("note") or {}
        check("기록: 시도 5 · 멈춤 표시", n.get("attempts") == 5 and n.get("gave_up") is True, str(n))
        gave = [x for x in lines if "[중요]" in x and "멈춘다" in x]
        check("[중요] 멈춤 로그는 한 번", len(gave) == 1, str(gave))
        jl = (sd / "followup.jsonl").read_text(encoding="utf-8")
        check("jsonl 사건 note_retry · note_gave_up", '"note_retry"' in jl and '"note_gave_up"' in jl)
        ok = NoteSpy()
        F.prepare_once("/r", "w", 1, state=sd, prepare=prep, note=ok, force=True)
        check("--force 는 다시 준비하고 노트를 보낸다", len(ok.calls) == 1 and len(prep.calls) == 2,
              f"{len(ok.calls)} {prep.calls}")
    finally:
        shutil.rmtree(sd, ignore_errors=True)


def test_note_retry_never_touches_old_records_903():
    """`#903` — 운영의 baseline·옛 기록(노트 필드 없음)·이슈 없음(skipped)은 재시도 대상이 아니다."""
    sd = Path(tempfile.mkdtemp(prefix="fu-note903-"))
    try:
        note = NoteSpy()
        for wid, rec in (("base", {"event": "baseline", "state": "ready_for_review"}),
                         ("old", {"event": "prepared", "state": "at_gate"})):
            F.write_state(F.round_key_path(F.state_dir(sd), "/r", wid, 1),
                          dict(rec, work_id=wid, round=1, repo="/r", at=0.0))
            F.prepare_once("/r", wid, 1, state=sd, prepare=IssueSpy(), note=note)
        F.prepare_once("/r", "noissue", 1, state=sd, prepare=PrepareSpy(state="stopped"), note=note)
        F.prepare_once("/r", "noissue", 1, state=sd, prepare=PrepareSpy(state="stopped"), note=note)
        check("🔴 baseline·옛 기록·이슈 없음은 노트를 보내지 않는다", note.calls == [], str(note.calls))
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


# ── wait — 읽기 전용 대기 (`#798` ①) ───────────────────────────────────────

class FakeClock:
    """주입 시계 — `sleep` 이 시간을 앞으로 민다. 실제로 자지 않는다."""

    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def _queue(seq):
    """조회마다 다음 응답 — 함수면 호출(예외 주입), 마지막 값은 반복한다."""
    calls = []

    def api(method, path, payload=None):
        calls.append((method, path))
        item = seq[min(len(calls) - 1, len(seq) - 1)]
        if callable(item):
            return item()
        return item
    api.calls = calls
    return api


def _resp(status="in_progress", rnd=1, tasks=None, **extra):
    w = {"work_id": "ww", "merge_status": status, "round": rnd, "project": "AXCluster", **extra}
    return {"work": w, "tasks": tasks if tasks is not None else [
        {"task_id": "t1", "status": "verified", "round": rnd},
        {"task_id": "t2", "status": "claimed", "round": rnd}]}


def _listing(d: Path) -> dict:
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in d.rglob("*")} if d.exists() else {}


def test_wait_at_gate_after_polls():
    sd = Path(tempfile.mkdtemp(prefix="fu-wait-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait-repo-"))
    try:
        fc, lines = FakeClock(), []
        polls = {"n": 0}

        def third():
            # 세 번째 조회 직전에 타이머가 준비를 끝냈다 — 기록을 심는다(대기 쪽은 쓰지 않는다)
            def spy(repo_, wid, **kw):
                fu = PrepareSpy(state="at_gate")(repo_, wid, **kw)
                fu.question = "버그 수정인가, 구조 수정인가?"
                return fu
            F.prepare_once(repo, "ww", 1, state=sd, prepare=spy, note=lambda *a, **k: {"ok": True})
            return _resp("ready_for_review", tasks=TASKS_DONE)
        api = _queue([_resp(), _resp(), third])
        before = _listing(sd)
        res = F.wait_for_gate(repo, "ww", api=api, state=sd, interval=30, timeout=600,
                              clock=fc.clock, sleep=fc.sleep, logf=lambda s, m: lines.append((s, m)))
        check("wait: 세 번째 조회에서 at_gate", res["outcome"] == "at_gate" and res["polls"] == 3, str(res))
        check("wait: at_gate → 종료 코드 0", res["exit_code"] == 0)
        check("wait: 큐 라우트 그대로", api.calls[0] == ("GET", "/api/v1/works/ww"), str(api.calls))
        rec = F.recorded_for(repo, "ww", 1, state=sd)
        check("[중요] wait: 텍스트는 render(기록) 그대로 (노트와 같은 문구)", res["text"] == F.render(rec))
        check("wait: 사실·게이트 물음을 싣는다", res["facts"].get("state") == "at_gate"
              and res["question"] == "버그 수정인가, 구조 수정인가?" and "게이트 물음(원문 인용)" in F.render_wait(res), str(res)[:300])
        check("wait: 진짜로 자지 않고 간격만큼 민다", fc.slept == [30, 30], str(fc.slept))
        wl = [m for s, m in lines if s == "wait"]
        check("wait: 조회마다 카운트다운 한 줄", sum(1 for m in wl if " · 남은 " in m) == 3, str(wl))
        check("wait: 줄 모양", any(m.startswith("ww r1 · 큐 in_progress · 조각 1/2 · 준비 없음 · 남은 10:00")
                                   for m in wl), str(wl))
        check("wait: 다음 줄은 남은 시간이 준다", any("남은 09:30" in m for m in wl), str(wl))
        for bad in ("하세요", "하라", "해라", "실행하", "묻지 말"):
            check(f"wait: 렌더에 명령형 `{bad}` 없음", bad not in F.render_wait(res))
        # 쓰지 않는다 — 이미 있는 기록을 두고 다시 기다려도 디렉토리가 그대로다
        before = _listing(sd)
        F.wait_for_gate(repo, "ww", api=_queue([_resp("ready_for_review", tasks=TASKS_DONE)]),
                        state=sd, clock=fc.clock, sleep=fc.sleep)
        check("[중요] wait 는 상태 파일·저널을 쓰지 않는다", _listing(sd) == before)
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_terminal_merged_and_records():
    sd = Path(tempfile.mkdtemp(prefix="fu-wait2-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait2-repo-"))
    try:
        fc = FakeClock()
        before = _listing(sd)
        for st in ("rejected", "cancelled"):
            tasks = [{"task_id": "t1", "status": "failed", "round": 1, "failure": "층1 위반"},
                     {"task_id": "t2", "status": "verified", "round": 1}]
            res = F.wait_for_gate(repo, "ww", api=_queue([_resp(st, tasks=tasks, terminal_reason="반려")]),
                                  state=sd, clock=fc.clock, sleep=fc.sleep)
            check(f"wait: {st} → terminal_{st}", res["outcome"] == f"terminal_{st}", str(res))
            check(f"wait: terminal_{st} → 종료 코드 3", res["exit_code"] == 3)
            check(f"wait: {st} 실패 조각 사유", res["failed_tasks"][0]["reason"] == "층1 위반"
                  and "층1 위반" in F.render_wait(res) and "반려" in F.render_wait(res))
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp("merged")]), state=sd,
                              clock=fc.clock, sleep=fc.sleep)
        check("wait: merged", res["outcome"] == "merged" and res["polls"] == 1)
        check("[중요] wait: 종결 경로도 아무것도 쓰지 않는다", _listing(sd) == before)
        for st, code in (("stopped", 3), ("error", 3)):
            F.prepare_once(repo, "w-" + st, 1, state=sd, prepare=PrepareSpy(state=st))
            api = _queue([_resp("ready_for_review", tasks=TASKS_DONE)])
            res = F.wait_for_gate(repo, "w-" + st, api=api, state=sd, clock=fc.clock, sleep=fc.sleep)
            check(f"wait: {st} 기록 → outcome {st} · 코드 {code}",
                  res["outcome"] == st and res["exit_code"] == code, str(res)[:200])
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_timeout_and_queue_errors():
    sd = Path(tempfile.mkdtemp(prefix="fu-wait3-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait3-repo-"))
    try:
        fc, lines = FakeClock(), []
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp()]), state=sd, interval=30, timeout=100,
                              clock=fc.clock, sleep=fc.sleep, logf=lambda s, m: lines.append(m))
        check("wait: timeout", res["outcome"] == "timeout" and res["exit_code"] == 4, str(res))
        check("wait: 마지막 간격은 남은 만큼만 잔다", fc.slept == [30, 30, 30, 10], str(fc.slept))
        check("wait: timeout 에 마지막 큐 상태", res["merge_status"] == "in_progress"
              and "in_progress" in F.render_wait(res) and "준비 기록 없음" in F.render_wait(res))

        def boom():
            raise OSError("connection refused")
        fc = FakeClock()
        lines.clear()
        res = F.wait_for_gate(repo, "ww", api=_queue([boom, boom, _resp("merged")]), state=sd,
                              interval=5, timeout=100, clock=fc.clock, sleep=fc.sleep,
                              logf=lambda s, m: lines.append(m))
        check("wait: 큐 오류 뒤 회복", res["outcome"] == "merged" and res["polls"] == 3
              and res["last_error"] == "", str(res))
        check("wait: 큐 오류도 줄을 남긴다", sum(1 for m in lines if "큐 조회 실패" in m) == 2, str(lines))
        fc = FakeClock()
        res = F.wait_for_gate(repo, "ww", api=_queue([boom]), state=sd, interval=10, timeout=25,
                              clock=fc.clock, sleep=fc.sleep)
        check("wait: 끝까지 실패 → timeout + last_error", res["outcome"] == "timeout"
              and "connection refused" in res["last_error"]
              and "connection refused" in F.render_wait(res), str(res))
        fc = FakeClock()
        res = F.wait_for_gate(repo, "ww", api=_queue([{}]), state=sd, interval=10, timeout=15,
                              clock=fc.clock, sleep=fc.sleep)
        check("wait: 큐에 work 없음은 오류로 계속 조회", res["outcome"] == "timeout"
              and "없다" in res["last_error"], str(res))
        check("[중요] wait: 오류·타임아웃도 아무것도 쓰지 않는다", _listing(sd) == {})
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_uses_current_round():
    sd = Path(tempfile.mkdtemp(prefix="fu-wait4-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait4-repo-"))
    try:
        # 라운드 1 은 이미 at_gate 로 기록됐다 — 개선요청으로 라운드 2 가 열렸으면 그것을 기다린다
        F.prepare_once(repo, "ww", 1, state=sd, prepare=PrepareSpy(state="at_gate"))
        fc, lines = FakeClock(), []
        r2_tasks = [{"task_id": "t9", "status": "claimed", "round": 2},
                    {"task_id": "t1", "status": "verified", "round": 1}]

        def r2_done():
            F.prepare_once(repo, "ww", 2, state=sd, prepare=PrepareSpy(state="stopped"))
            return _resp("rejected", rnd=2, tasks=r2_tasks)
        api = _queue([_resp("in_progress", rnd=2, tasks=r2_tasks), r2_done])
        res = F.wait_for_gate(repo, "ww", api=api, state=sd, interval=30, timeout=300,
                              clock=fc.clock, sleep=fc.sleep, logf=lambda s, m: lines.append(m))
        check("[중요] wait: 옛 라운드의 at_gate 로 끝나지 않는다",
              res["polls"] == 2 and res["round"] == 2, str(res)[:300])
        check("wait: 라운드 2 의 기록(stopped)이 종결보다 앞선다", res["outcome"] == "stopped", res["outcome"])
        check("wait: 라운드 조각만 센다", any(m.startswith("ww r2 · 큐 in_progress · 조각 0/1") for m in lines),
              str(lines))
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_task_reason_key_mapping():
    """큐가 실제로 쓰는 사유 키 (`logic_lifecycle.py`) — 옛 키는 폴백 (`#798` 후속)."""
    from master.work import workmodel as WM
    check("[중요] 공개 이름 재수출 — task_reason·REASON_KEYS 는 workmodel 정본",
          F.task_reason is WM.task_reason and F.REASON_KEYS is WM.REASON_KEYS
          and F.LEGACY_REASON_KEYS is WM.LEGACY_REASON_KEYS and F.BLOCK_STATES == ("needs_revision", "failed"))
    rt = F.task_reason
    check("failed: fail_reason + fail_detail",
          rt({"status": "failed", "fail_reason": "layer1", "fail_detail": "동결 위반 x"})
          == "layer1 — 동결 위반 x")
    check("failed: verify:<result> 만 있어도", rt({"status": "failed", "fail_reason": "verify:reject"})
          == "verify:reject")
    check("cancelled: cancel_reason", rt({"status": "cancelled", "cancel_reason": "골조 결함",
                                          "last_feedback": "층1"}) == "골조 결함")
    check("needs_revision: last_feedback", rt({"status": "needs_revision", "last_feedback": "층1 위반 1"})
          == "층1 위반 1")
    check("옛 키 폴백 (failure)", rt({"status": "failed", "failure": "옛 사유"}) == "옛 사유")
    check("옛 키 폴백 (error)", rt({"status": "cancelled", "error": "e"}) == "e")
    check("큐 키가 옛 키보다 앞선다", rt({"status": "failed", "fail_reason": "새", "failure": "옛"}) == "새")
    check("사유 없으면 빈 문자열", rt({"status": "failed"}) == "")
    check("300자로 자른다", len(rt({"status": "needs_revision", "last_feedback": "x" * 900})) == 300)
    got = F._failed_of([
        {"task_id": "a", "status": "failed", "fail_reason": "r", "fail_detail": "d", "worker_id": "w1",
         "attempt_count": 2},
        {"task_id": "b", "status": "cancelled", "cancel_reason": "c", "assignee": "192.168.0.2",
         "attempt_count": 1},
        {"task_id": "c", "status": "needs_revision", "last_feedback": "f"},
        {"task_id": "d", "status": "verified"}])
    check("_failed_of: 기본은 failed·cancelled 만", [t["task_id"] for t in got] == ["a", "b"], str(got))
    check("_failed_of: 상태·워커·시도·사유", got[0] == {"task_id": "a", "status": "failed", "reason": "r — d",
                                                   "worker": "w1", "attempt_count": 2}, str(got[0]))
    check("_failed_of: worker_id 없으면 assignee", got[1].get("worker") == "192.168.0.2"
          and got[1]["reason"] == "c", str(got[1]))
    blk = F._failed_of([{"task_id": "c", "status": "needs_revision", "last_feedback": "f"},
                        {"task_id": "a", "status": "failed"},
                        {"task_id": "b", "status": "cancelled"}], F.BLOCK_STATES)
    check("_failed_of(BLOCK_STATES): needs_revision·failed", [t["task_id"] for t in blk] == ["c", "a"], str(blk))
    txt = F.render({"state": "stopped", "work_id": "w", "round": 1, "failed_tasks": got})
    check("render: 진짜 사유가 노트에 실린다", "r — d" in txt and "사유 없음" not in txt
          and "워커 w1" in txt and "시도 2" in txt, txt)


def test_wait_blocked_needs_revision():
    """조회 도중 needs_revision → 첫 막힘에서 blocked · 코드 3 · last_feedback 사유 (사용자 결정 2026-10-11)."""
    sd = Path(tempfile.mkdtemp(prefix="fu-wait6-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait6-repo-"))
    try:
        fc = FakeClock()
        lines = []
        before = _listing(sd)
        claimed = [{"task_id": "t1", "status": "claimed", "round": 1, "assignee": "192.168.0.2"},
                   {"task_id": "t2", "status": "claimed", "round": 1, "assignee": "192.168.0.43"}]
        revised = [{"task_id": "t1", "status": "needs_revision", "round": 1, "assignee": "192.168.0.2",
                    "worker_id": None, "attempt_count": 1, "last_feedback": "층1 위반 1: 동결 위반"},
                   {"task_id": "t2", "status": "claimed", "round": 1, "assignee": "192.168.0.43"}]
        api = _queue([_resp(tasks=claimed), _resp(tasks=revised)])
        res = F.wait_for_gate(repo, "ww", api=api, state=sd, interval=30, timeout=600,
                              clock=fc.clock, sleep=fc.sleep, logf=lambda s, m: lines.append(m))
        check("[중요] wait: needs_revision → blocked", res["outcome"] == "blocked" and res["polls"] == 2, str(res))
        check("wait: blocked → 종료 코드 3", res["exit_code"] == 3 and F.WAIT_EXIT["blocked"] == 3)
        bt = res["blocked_tasks"]
        check("wait: 막힌 조각 사실", len(bt) == 1 and bt[0]["task_id"] == "t1"
              and bt[0]["status"] == "needs_revision" and bt[0]["worker"] == "192.168.0.2"
              and bt[0]["attempt_count"] == 1 and bt[0]["reason"] == "층1 위반 1: 동결 위반", str(bt))
        txt = F.render_wait(res)
        check("render_wait: blocked 블록", txt.startswith("[⑦ 대기 결과] ww · 라운드 1 · 결과 blocked"), txt)
        cap = F.REVISE_MAX_ATTEMPTS
        check("render_wait: 조각 줄에 워커·시도·사유",
              f"조각 needs_revision t1 · 워커 192.168.0.2 · 시도 1/{cap}: 층1 위반 1: 동결 위반" in txt, txt)
        check("render_wait: 재시도 후보로 남아 있다는 사실", "needs_revision 1건은 큐의 자동 재시도 후보" in txt
              and f"상한 {cap}회" in txt, txt)
        check("render_wait: 사유 없음 아님", "사유 없음" not in txt, txt)
        for bad in ("하세요", "하라", "해라", "실행하"):
            check(f"render_wait blocked: 명령형 `{bad}` 없음", bad not in txt)
        check("wait: 막힘 수가 조회 줄에 (0 이면 없음)",
              any("조각 0/2 · 준비 없음" in m for m in lines)
              and any("조각 0/2 · 막힘 1 · 준비 없음" in m for m in lines), str(lines))
        check("wait: 막힘 사유 로그 줄", any("막힘 — needs_revision t1" in m for m in lines), str(lines))
        # `#363` — 4상태·종류·권고와 다른 조각의 상태
        check("[중요] wait blocked: workmodel 판정 (첫 동결 위반 1건은 code → retry)",
              bt[0].get("kind") == "code" and bt[0].get("action") == "retry"
              and bt[0].get("state") == "실패" and bt[0].get("retryable") is True, str(bt))
        check("render_wait: 상태·종류·권고 줄",
              f"상태 실패·재시도 예정 (시도 1/{cap}) · 종류 code · 권고 retry — " in txt, txt)
        check("[중요] wait blocked: 다른 조각 상태가 실린다",
              res["other_tasks"] == [{"task_id": "t2", "status": "claimed", "state": "작업중",
                                      "worker": "192.168.0.43"}], str(res["other_tasks"]))
        check("render_wait: 다른 조각 요약·목록",
              "이번 라운드 다른 조각 — 작업중 1 · 성공 0 · 대기 0" in txt
              and "· t2 작업중(claimed) · 워커 192.168.0.43" in txt, txt)
        check("wait: 다른 조각 로그 줄", any("다른 조각 — 작업중 1 · 성공 0 · 대기 0" in m for m in lines),
              str(lines))
        check("wait: 막힘 로그에 종류·권고", any("종류 code · 권고 retry" in m for m in lines), str(lines))
        check("wait: 큐에는 GET 만", all(c[0] == "GET" for c in api.calls), str(api.calls))
        check("[중요] wait: blocked 도 아무것도 쓰지 않는다", _listing(sd) == before)
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_blocked_skeleton_two_frozen():
    """같은 라운드 두 조각이 동시에 동결 위반 → skeleton · notify_human (`#363` 사용자 결정 2026-10-11).
    사유 원문은 실측 #734(2026-10-11 12:26) 의 `last_feedback` 그대로."""
    sd = Path(tempfile.mkdtemp(prefix="fu-wait8-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait8-repo-"))
    try:
        fc = FakeClock()
        fb1 = ("[fp:f703f2c105b0] [중요] 층1 — 층1 이 막았다 — 커밋하지 않는다 — 층1 위반 1: "
               "master/projects/mcp_server.py: 동결 위반 — 동결 인터페이스 변경/삭제: def get_code(...)")
        fb2 = ("[fp:73785f4413c3] [중요] 층1 — 층1 이 막았다 — 커밋하지 않는다 — 층1 위반 1: "
               "master/work/generate.py: 동결 위반 — 동결 인터페이스 변경/삭제: class Dispatch()")
        tasks = [{"task_id": "d389e08f", "status": "needs_revision", "round": 1, "assignee": "192.168.0.2",
                  "attempt_count": 1, "last_feedback": fb1},
                 {"task_id": "ca8e428c", "status": "needs_revision", "round": 1, "assignee": "192.168.0.43",
                  "attempt_count": 1, "last_feedback": fb2},
                 {"task_id": "t3", "status": "pending", "round": 1}]
        final_tasks = [dict(t, status="failed", fail_detail=t.get("last_feedback"), fail_reason="BLOCKED")
                       if t["status"] == "needs_revision" else dict(t, status="verified") for t in tasks]
        gate = {"state": "at_gate", "work_id": "ww", "round": 1, "rework": True,
                "tree": "/integrated", "head": "a" * 40, "build_passed": False}
        with patch.object(F, "recorded_for", side_effect=[{}, {}, gate]):
            res = F.wait_for_gate(repo, "ww", api=_queue([_resp(tasks=tasks),
                                  _resp(tasks=final_tasks, merge_status="rejected")]), state=sd,
                                  clock=fc.clock, sleep=fc.sleep)
        bt = res["work_summary"]["rework_tasks"]
        check("[중요] wait: 동결 위반 2건 동시 → 둘 다 skeleton · notify_human",
              [b.get("task_id") for b in bt] == ["d389e08f", "ca8e428c"], str(bt))
        txt = F.render_wait(res)
        check("render_wait: 골조 결함 근거 (사실만)",
              "골조 재작업 필요" in txt and "동결 위반" in txt, txt)
        check("render_wait: 다른 대기조각도 완료+통합준비뒤 고지", "성공 조각 t3" in txt and res["polls"] == 3, txt)
        for bad in ("하세요", "하라", "해라", "실행하"):
            check(f"render_wait skeleton: 명령형 `{bad}` 없음", bad not in txt)
        check("wait skeleton: 통합본 사람게이트 코드0", res["outcome"] == "at_gate" and res["exit_code"] == 0)
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_skeleton_deferred_until_other_tasks_finish():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        before = _listing(root)
        skeleton = {"task_id": "a", "status": "failed", "round": 1,
                    "fail_detail": "[kind:skeleton] 동결 위반"}
        working = {"task_id": "b", "status": "claimed", "round": 1, "worker_id": "worker"}
        pending = {"task_id": "c", "status": "pending", "round": 1}
        done_b, done_c = dict(working, status="verified"), dict(pending, status="verified")
        fc = FakeClock()
        responses = [_resp(tasks=[skeleton, working, pending]),
                     _resp(tasks=[skeleton, done_b, dict(pending, status="claimed")]),
                     _resp(tasks=[skeleton, done_b, done_c], merge_status="rejected")]
        old = {"state": "stopped", "work_id": "ww", "round": 1, "reason": "옛 실패 기록"}
        gate = {"state": "at_gate", "work_id": "ww", "round": 1, "rework": True,
                "tree": "/integrated", "head": "a" * 40, "build_passed": False}
        with patch.object(F, "recorded_for", side_effect=[{}, {}, old, gate]):
            res = F.wait_for_gate(root / "repo", "ww", api=_queue(responses), state=root / "state",
                                  clock=fc.clock, sleep=fc.sleep)
        txt = F.render_wait(res)
        check("골조실패 즉시대기종료 않고 나머지종결+통합준비까지조회", res["polls"] == 4 and res["outcome"] == "at_gate")
        check("최종 종결에 골조 재작업 필요", res["work_summary"]["rework_required"] and "골조 재작업 필요" in txt, txt)
        check("최종 성공조각 결과 모두 보존", "성공 조각 b" in txt and "성공 조각 c" in txt, txt)
        check("전체보류/취소/재할당제어 없음", "work 파견 보류" not in txt and _listing(root) == before)
        original = "[준비 기록 원문] 예전 stopped 기록"
        recorded = dict(res, text=original, outcome="stopped")
        txt = F.render_wait(recorded)
        check("과거준비기록원문보존+최신골조재작업덧붙임", txt.startswith(original + "\n\n[최신 큐 상태]")
              and "골조 재작업 필요" in txt and "성공 조각 b" in txt)
        active = dict(recorded, work_summary=F.WM.Work.from_record(
            {"round": 1}, [skeleton, working, pending]).execution_summary())
        check("과거기록에 실행중이면 종결거짓고지안함", F.render_wait(active) == original)


def test_prepare_rework_merges_and_reports_second_skeleton():
    w = dict(WORK_READY, merge_status="rejected")
    tasks = [{"task_id": "t1", "status": "verified", "round": 1},
             {"task_id": "t2", "status": "failed", "round": 1, "target_file": "master/x.py",
              "fail_detail": "[kind:skeleton] 동결 위반 — 선언 삭제"}]
    spy = AdvanceSpy(build_passed=False)
    def advance(repo, **kw):
        a = spy(repo, **kw)
        a.rework_evidence = [{"task_id": "t1", "branch": "task/w1/r1/t1", "head": "c" * 40,
                              "source": "durable", "verified": True}]
        a.missing_results = [{"task_id": "t2", "status": "failed", "reason": "커밋 없음"}]
        return a
    fu = F.prepare_round("/r", "w1", fetch=_fetch(w, tasks), advance=advance, build_fn=_bfn)
    check("골조종결은 rejected여도 통합사람게이트", fu.state == "at_gate" and fu.rework, fu.reason)
    kw = spy.calls[0] if spy.calls else {}
    check("재작업통합도 confirmFalse/keepTreeTrue", kw.get("rework") is True
          and kw.get("confirm") is False and kw.get("keep_tree") is True)
    p = fu.next_skeleton
    check("2차골조는 통합본HEAD/tree기준", p.get("next_round") == 2 and p.get("integrated_head") == fu.head
          and p.get("integrated_tree") == fu.tree)
    check("2차골조 사유/대상/성공재사용 구조화", p.get("repairs", [{}])[0].get("targets") == ["master/x.py"]
          and p.get("successful_tasks") == ["t1"])
    txt = F.render(fu.facts())
    check("고지에 통합증거와누락결과명시", "통합 결과 t1" in txt and "결과 없음 t2" in txt
          and "다음 골조 준비" in txt and "성공 결과 재사용: t1" in txt, txt)
    check("자동생성/파견/전진안함", "코드 생성·다음 라운드 등재는 아직 없음" in txt and not fu.pushed)
    check("빌드실패도전체취소또는통합본수정2라운드선택고지", fu.build_passed is False
          and "완전히 취소" in fu.question and "라운드 2" in fu.question
          and "cancel_work" in txt and "fix_and_next_round" in txt
          and p["decision_options"]["fix_and_next_round"]["requires_confirmation"])
    spy = AdvanceSpy()
    active = [tasks[1], dict(tasks[0], status="claimed")]
    fu = F.prepare_round("/r", "w1", fetch=_fetch(dict(w, merge_status="in_progress"), active),
                         advance=spy, build_fn=_bfn)
    check("골조실패라도 다른실행중이면 통합안함", fu.state == "running" and not spy.calls)
    spy = AdvanceSpy()
    fu = F.prepare_round("/r", "w1", fetch=_fetch(dict(w, merge_status="cancelled"), tasks),
                         advance=spy, build_fn=_bfn)
    check("명시work취소는골조있어도통합안함", fu.state == "stopped" and not spy.calls)
    fu = F.prepare_round("/r", "w1", fetch=_fetch(dict(w, merge_status="cancelled"), active),
                         advance=spy, build_fn=_bfn)
    check("명시취소는골조와실행중조각보다우선", fu.state == "stopped" and not spy.calls)
    fu = F.prepare_round("/r", "w1", fetch=_fetch(dict(w, merge_status="in_progress"), tasks),
                         advance=spy, build_fn=_bfn)
    check("골조완료도큐rejected종결전통합안함", fu.state == "running" and not spy.calls)


def test_rework_reopens_stopped_history_once_and_scan():
    w = dict(WORK_READY, merge_status="rejected")
    tasks = [{"task_id": "t1", "status": "verified", "round": 1},
             {"task_id": "t2", "status": "failed", "round": 1, "fail_detail": "[kind:skeleton] 동결 위반"}]
    with tempfile.TemporaryDirectory() as td:
        state, repo = Path(td) / "state", Path(td) / "repo"
        path = F.round_key_path(state, repo, "w1", 1)
        old = {"event": "stopped", "state": "stopped", "work_id": "w1", "round": 1,
               "repo": str(repo.resolve()), "reason": "옛 사유 없음 기록"}
        F.write_state(path, old)
        old_bytes = path.read_bytes()
        spy = AdvanceSpy()
        kwargs = {"state": state, "fetch": _fetch(w, tasks), "advance": spy, "build_fn": _bfn}
        out = F.prepare_once(repo, "w1", 1, **kwargs)
        check("최신골조확정때만stopped재준비", out["action"] == "prepared" and out["result"]["rework"])
        check("옛stopped원문이력보존", (state / "history" / path.name).read_bytes() == old_bytes)
        again = F.prepare_once(repo, "w1", 1, **kwargs)
        check("재작업준비도라운드멱등", again["skip"] == "already_prepared" and len(spy.calls) == 1)
        rec = dict(old, event="error", state="error")
        F.write_state(path, rec)
        again = F.prepare_once(repo, "w1", 1, **kwargs)
        check("재작업준비오류는자동재시도안함", again["skip"] == "previous_error" and len(spy.calls) == 1)
        F.write_state(path, old)
        ordinary = [tasks[0], dict(tasks[1], fail_detail="[kind:code] 일반 코드 실패")]
        again = F.prepare_once(repo, "w1", 1, state=state, fetch=_fetch(w, ordinary),
                               advance=spy, build_fn=_bfn)
        check("일반실패stopped는재개안함", again["skip"] == "already_stopped" and len(spy.calls) == 1)
        again = F.prepare_once(repo, "w1", 1, state=state, fetch=_fetch(dict(w, round=2), tasks),
                               advance=spy, build_fn=_bfn)
        check("다른라운드는옛stopped재준비안함", again["skip"] == "already_stopped")
        F.scan(repo, project="P", state=state, list_works=_works())
        def once(*args, **kw):
            return F.prepare_once(*args, fetch=_fetch(w, tasks), advance=spy, build_fn=_bfn, **kw)
        out = F.scan(repo, project="P", state=state, list_works=_works(w), once=once)
        check("timer scan도골조rejected를준비게이트연결", out["prepared"] == [{"work_id": "w1", "round": 1, "state": "at_gate"}])



def test_wait_blocked_failed_and_precedence():
    sd = Path(tempfile.mkdtemp(prefix="fu-wait7-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait7-repo-"))
    try:
        fc = FakeClock()
        failed = [{"task_id": "t1", "status": "failed", "round": 1, "worker_id": "janus",
                   "attempt_count": 3, "fail_reason": "verify:reject", "fail_detail": "층2 차단"},
                  {"task_id": "t2", "status": "verified", "round": 1}]
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp(tasks=failed)]), state=sd,
                              clock=fc.clock, sleep=fc.sleep)
        check("wait: failed → blocked", res["outcome"] == "blocked" and res["exit_code"] == 3, str(res))
        bt = res["blocked_tasks"][0]
        check("wait: failed 사유 = fail_reason — fail_detail", bt["reason"] == "verify:reject — 층2 차단"
              and bt["worker"] == "janus" and "max_attempts" not in bt, str(bt))
        txt = F.render_wait(res)
        check("render_wait: failed 줄", "조각 failed t1 · 워커 janus · 시도 3: verify:reject — 층2 차단" in txt
              and "재시도 후보" not in txt, txt)
        check("wait blocked: 상한 도달 failed → cap · notify_human",
              bt.get("kind") == "cap" and bt.get("action") == "notify_human"
              and bt.get("retryable") is False, str(bt))
        check("render_wait: 성공 조각도 다른 조각으로 보인다",
              "이번 라운드 다른 조각 — 작업중 0 · 성공 1 · 대기 0" in txt and "· t2 성공(verified)" in txt, txt)
        # 지난 라운드의 막힘은 이번 라운드를 막지 않는다
        old = [{"task_id": "t0", "status": "failed", "round": 1, "fail_reason": "x"},
               {"task_id": "t1", "status": "claimed", "round": 2}]
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp(rnd=2, tasks=old)]), state=sd, interval=10,
                              timeout=15, clock=fc.clock, sleep=fc.sleep)
        check("wait: 지난 라운드 failed 는 막힘이 아니다", res["outcome"] == "timeout", res["outcome"])
        # 그 라운드의 준비 기록이 있으면 기록이 앞선다
        F.prepare_once(repo, "w-rec", 1, state=sd, prepare=PrepareSpy(state="at_gate"))
        stale = [{"task_id": "t1", "status": "needs_revision", "round": 1, "last_feedback": "옛 피드백"}]
        res = F.wait_for_gate(repo, "w-rec", api=_queue([_resp("ready_for_review", tasks=stale)]),
                              state=sd, clock=fc.clock, sleep=fc.sleep)
        check("[중요] wait: 준비 기록(at_gate)이 needs_revision 보다 앞선다",
              res["outcome"] == "at_gate" and res["exit_code"] == 0, res["outcome"])
        # work 종결(cancelled)은 막힘보다 앞서고, 취소 사유는 cancel_reason 으로 보인다
        canc = [{"task_id": "t1", "status": "cancelled", "round": 1, "attempt_count": 1,
                 "assignee": "192.168.0.43", "last_feedback": "층1", "cancel_reason": "골조 설계 결함"},
                {"task_id": "t2", "status": "needs_revision", "round": 1, "last_feedback": "층1"}]
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp("cancelled", tasks=canc, terminal_reason="조각 취소")]),
                              state=sd, clock=fc.clock, sleep=fc.sleep)
        txt = F.render_wait(res)
        check("wait: cancelled work 는 terminal_cancelled", res["outcome"] == "terminal_cancelled", res["outcome"])
        check("[중요] render_wait: 취소 사유가 cancel_reason 으로", "조각 cancelled t1 · 워커 192.168.0.43 · "
              "시도 1: 골조 설계 결함" in txt and "사유 없음" not in txt, txt)
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_baseline_ends_first_poll():
    """기준선 기록은 준비되지 않는다 — 첫 조회에서 `baseline` 으로 끝난다 (`#798`)."""
    sd = Path(tempfile.mkdtemp(prefix="fu-wait-bl-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait-bl-repo-"))
    try:
        # scan 첫 실행이 쓰는 모양 그대로 심는다
        F.scan(repo, project="P", state=sd,
               list_works=_works({"work_id": "ww", "merge_status": "ready_for_review", "round": 1}))
        path = F.round_key_path(sd, repo, "ww", 1)
        check("baseline: scan 이 기준선을 썼다", F.read_state(path).get("event") == "baseline",
              str(F.read_state(path)))
        check("baseline: _with_facts 가 event 를 싣는다",
              F.recorded_for(repo, "ww", 1, state=sd).get("event") == "baseline")
        fc, lines = FakeClock(), []
        before = _listing(sd)
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp("ready_for_review", tasks=TASKS_DONE)]),
                              state=sd, interval=30, timeout=600, clock=fc.clock, sleep=fc.sleep,
                              logf=lambda s_, m: lines.append((s_, m)))
        check("[중요] baseline: 첫 조회에서 끝난다", res["outcome"] == "baseline" and res["polls"] == 1, str(res)[:300])
        check("baseline: 종료 코드 3", res["exit_code"] == 3 and F.WAIT_EXIT["baseline"] == 3)
        check("baseline: 자지 않는다", fc.slept == [], str(fc.slept))
        check("baseline: 기록 상태·사실", res["record_state"] == "baseline"
              and res["facts"].get("event") == "baseline", str(res)[:300])
        wl = [m for s_, m in lines if s_ == "wait"]
        check("baseline: 조회 한 줄 + 끝 한 줄", len(wl) == 2 and " · 남은 " in wl[0]
              and "끝 — baseline" in wl[1], str(wl))
        txt = F.render_wait(res)
        check("baseline: 렌더에 라벨", F.WAIT_LABEL["baseline"] in txt and "다시 하려면 --force" in txt, txt)
        for bad in ("하세요", "하라", "해라", "실행하", "묻지 말"):
            check(f"baseline: 렌더에 명령형 `{bad}` 없음", bad not in txt)
        check("[중요] baseline: wait 는 쓰지 않는다", _listing(sd) == before)
        # --force 준비가 같은 파일을 at_gate 로 덮으면 그 결과를 본다
        F.write_state(path, {"event": "prepared", "state": "at_gate", "at": 1.0, "work_id": "ww",
                             "round": 1, "repo": str(repo.resolve()), "reason": "준비됨"})
        res = F.wait_for_gate(repo, "ww", api=_queue([_resp("ready_for_review", tasks=TASKS_DONE)]),
                              state=sd, clock=fc.clock, sleep=fc.sleep)
        check("baseline: --force 로 덮인 뒤엔 at_gate · 코드 0",
              res["outcome"] == "at_gate" and res["exit_code"] == 0, str(res)[:300])
    finally:
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_wait_cli_exit_codes():
    import contextlib
    import io
    sd = Path(tempfile.mkdtemp(prefix="fu-wait5-"))
    repo = Path(tempfile.mkdtemp(prefix="fu-wait5-repo-"))
    orig_resolve, orig_wait = F._resolve_api, F.wait_for_gate
    try:
        F._resolve_api = lambda r: _queue([_resp("merged")])
        for oc, code in (("at_gate", 0), ("stopped", 3), ("error", 3), ("blocked", 3), ("terminal_rejected", 3),
                         ("terminal_cancelled", 3), ("merged", 3), ("baseline", 3), ("timeout", 4)):
            got = {}

            def fake_wait(repo_, wid, **kw):
                got.update(kw, wid=wid)
                return {"work_id": wid, "round": 1, "outcome": oc, "exit_code": F.WAIT_EXIT[oc],
                        "text": f"BLOCK {oc}" if oc in ("at_gate", "stopped", "error") else ""}
            F.wait_for_gate = fake_wait
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = F.main(["ww", "--wait", "--repo", str(repo), "--interval", "2", "--timeout", "9",
                             "--state-dir", str(sd)])
            check(f"CLI --wait {oc} → 종료 코드 {code}", rc == code, f"rc={rc}")
            check(f"CLI --wait {oc} stdout 은 결과 블록", buf.getvalue().strip().startswith(
                "BLOCK" if oc in ("at_gate", "stopped", "error") else "[⑦ 대기 결과]"), buf.getvalue())
        check("CLI --wait 인자 전달", got.get("interval") == 2.0 and got.get("timeout") == 9.0
              and got.get("wid") == "ww", str(got))
        for bad in (["--scan", "--wait"], ["ww", "--wait", "--force"], ["ww", "--wait", "--interval", "0"]):
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    F.main(bad)
                    code = 0
                except SystemExit as e:
                    code = e.code
            check(f"CLI 사용법 오류 {bad} → 2", code == 2, f"code={code}")
    finally:
        F._resolve_api, F.wait_for_gate = orig_resolve, orig_wait
        shutil.rmtree(sd, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def test_register_tool_carries_wait_command():
    """등재 응답이 대기 명령을 싣는다 — 등재와 대기를 한 입구로 (`#798` ①)."""
    import json as _json
    try:
        from master.projects import mcp_server as pj
    except ImportError as e:                       # mcp SDK 가 없는 환경 — 실패로 남긴다
        check("register_work_tool import", False, str(e))
        return
    from types import SimpleNamespace
    orig = (pj.register_work, pj.resolve)
    try:
        pj.resolve = lambda project: None
        pj.register_work = lambda *a, **k: SimpleNamespace(
            ok=True, work_id="20261011_x_work_1", tasks=[], summary=lambda: "s")
        got = _json.loads(pj.register_work_tool("T", "repo", "[]"))
        # 자리는 서버가 도는 체크아웃(`pj._CODE_ROOT`) — 마스터에서는 `/home/sim/ax-cluster`,
        # 격리 worktree 에서는 그 worktree 다. `AX_PROJECTS_ROOT` 는 받은 값(없으면 체크아웃).
        import shlex
        code = Path(__file__).resolve().parents[1]
        check("서버 체크아웃 = 이 테스트의 체크아웃", pj._CODE_ROOT == code, str(pj._CODE_ROOT))
        try:
            proot = str(pj.projects_root())
        except pj.ConfigError:
            proot = str(code)
        want = (f"AX_PROJECTS_ROOT={shlex.quote(proot)} "
                f"{shlex.quote(str(code / '.venv' / 'bin' / 'python'))} "
                f"-m master.work.followup 20261011_x_work_1 --wait --repo {shlex.quote(str(code))}")
        check("[중요] 등재 응답에 wait 명령", got.get("wait") == want, str(got.get("wait")))
        note = got.get("wait_note") or ""
        check("등재 응답에 wait_note (사실)", "at_gate" in note and "읽기" in note, note)
        for bad in ("하세요", "하라", "해라", "실행하"):
            check(f"wait_note 에 명령형 `{bad}` 없음", bad not in note, note)
        check("다른 필드는 그대로", set(got) == {"ok", "work_id", "summary", "tasks", "wait", "wait_note"},
              str(sorted(got)))
        pj.register_work = lambda *a, **k: SimpleNamespace(
            ok=False, work_id="", tasks=[], summary=lambda: "s")
        got = _json.loads(pj.register_work_tool("T", "repo", "[]"))
        check("등재 실패면 wait 없음", "wait" not in got, str(got))
    finally:
        pj.register_work, pj.resolve = orig


def test_scope_report_rendered_at_gate():
    facts = {
        "work_id": "w820",
        "round": 1,
        "state": "at_gate",
        "merged": ["task_a"],
        "scope_report": {
            "out_of_scope_count": 2,
            "by_kind": {"other": 1, "import": 1, "comment": 0},
            "render_line": "범위 밖 변경 덩어리 2건 (other 1 · import 1)",
        },
    }
    txt = F.render(facts)
    check("render: 범위 밖 변경 덩어리 고지 포함", "범위 밖 변경 덩어리 2건 (other 1 · import 1)" in txt, txt)

    facts_clean = {
        "work_id": "w820",
        "round": 1,
        "state": "at_gate",
        "merged": ["task_a"],
        "scope_report": {},
    }
    txt_clean = F.render(facts_clean)
    check("render: 범위 이탈 없으면 줄 없음", "범위 밖 변경" not in txt_clean, txt_clean)


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
               test_regression_selection_rules,
               test_regression_selection_real_repo,
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
               test_note_retry_after_interruption_903,
               test_note_retry_limit_903,
               test_note_retry_never_touches_old_records_903,
               test_post_note_uses_queue_route,
               test_recorded_for_lookup,
               test_check_counts_and_capture,
               test_resolve_kind_from_delivered_config,
               test_failure_tail_is_kept_and_rendered,
               test_wait_at_gate_after_polls,
               test_wait_terminal_merged_and_records,
               test_wait_timeout_and_queue_errors,
               test_wait_uses_current_round,
               test_task_reason_key_mapping,
               test_wait_blocked_needs_revision,
               test_wait_blocked_failed_and_precedence,
               test_wait_blocked_skeleton_two_frozen,
               test_wait_skeleton_deferred_until_other_tasks_finish,
               test_prepare_rework_merges_and_reports_second_skeleton,
               test_rework_reopens_stopped_history_once_and_scan,
               test_wait_baseline_ends_first_poll,
               test_wait_cli_exit_codes,
               test_register_tool_carries_wait_command,
               test_scope_report_rendered_at_gate):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_followup: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
