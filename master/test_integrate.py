"""통합자 (중 1.4).

🔴 지키는 계약은 다섯이다:

    ① **격리** — 적용 트리는 체크아웃의 형제다(안에 두면 git 이 자기 트리를 삼킨다)
    ② **기준이 섞이거나 없으면 적용하지 않는다** — 낡은 응답은 남의 실패로 빌드를 깬다
    ③ **싼 검사가 먼저** — 층1 이 막으면 적용도 빌드도 하지 않는다
    ④ 🔴 **실패는 커밋하지 않는다** — 되돌리고 `[FEEDBACK]` 을 남긴다 (소 1.4.4)
    ⑤ **push 는 ff-only** — 거부되면 force 하지 않고 사람에게 넘긴다

`.venv/bin/python master/test_integrate.py`
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import infer as INF        # noqa: E402
from master.work import integrate as I      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


HDR = """#pragma once
UCLASS()
class MODULARSTAGE_API UFoo : public UObject
{
\tGENERATED_BODY()
public:
\tvirtual void SetData(const FMissionTaskInfo& InTaskInfo) override;
\tint32 GetStep() const;
};
"""
CPP = "#include \"Foo.h\"\nvoid UFoo::SetData(const FMissionTaskInfo& In) {}\n"
H, C = "Source/A/Foo.h", "Source/A/Foo.cpp"


@dataclass
class FakeFacts:
    host: str = "w1"
    user: str = "u"
    path: str = r"E:\trunk\ModularStage"
    role: str = "worker"
    os: str = "windows"
    ue5: str = r"C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
    checkout_ok: bool = True

    @property
    def windows(self) -> bool:
        return self.os == "windows"


class Build:
    """`BuildResult` 대역."""

    def __init__(self, passed=True, seconds=42.0, tail="error C2065: 'None'"):
        self.passed, self.seconds, self.tail = passed, seconds, tail

    def summary(self):
        return "BUILD OK(42s)" if self.passed else "BUILD FAILED"


class Git:
    """원격 git 대역. 부른 명령을 순서대로 기록하고, 규칙대로 답한다."""

    def __init__(self, *, head="aaaa111", dirty="", worktree_exists=False,
                 push_rc=0, commit_rc=0):
        self.calls: list = []
        self.head, self.dirty = head, dirty
        self.worktree_exists = worktree_exists
        self.push_rc, self.commit_rc = push_rc, commit_rc
        self.commits = 0

    def __call__(self, facts, cmd):
        self.calls.append(cmd)
        if "worktree list" in cmd:
            return 0, (r"worktree E:/trunk/ax-wt-W1" if self.worktree_exists else
                       r"worktree E:/trunk/ModularStage")
        if "status --porcelain" in cmd:
            return 0, self.dirty
        if "rev-parse HEAD" in cmd:
            return 0, self.head
        if cmd.split("git -C")[-1].strip().startswith('"') and " commit " in cmd:
            pass
        if " commit " in cmd:
            if self.commit_rc:
                return self.commit_rc, "nothing to commit, working tree clean"
            self.commits += 1
            self.head = f"bbbb{self.commits:03d}"
            return 0, ""
        if " push " in cmd:
            return self.push_rc, ("" if not self.push_rc else
                                  "! [rejected] main -> main (non-fast-forward)")
        return 0, ""

    def ran(self, needle: str) -> bool:
        return any(needle in c for c in self.calls)


def tmp_paths():
    root = Path(tempfile.mkdtemp(prefix="axitg"))

    class P:
        name = "ModularStage"

        @property
        def responses(self):
            return root / "responses"

        @property
        def config(self):
            return root / "config.yaml"

        @property
        def repo(self):
            return root / "repo"
    return P(), root


def resp(task_id, files, base="aaaa111", order=1, epoch=7):
    r = INF.Response(task_id=task_id, status="DONE", files=dict(files),
                     want=sorted(files), base_commit=base, epoch=epoch)
    return r


def spool_two(paths, *, bases=("aaaa111", "aaaa111")):
    INF.spool(paths, resp("t1", {H: HDR, C: CPP}, base=bases[0]), work_id="W1", order=1)
    INF.spool(paths, resp("t2", {"Source/B/Bar.h": HDR}, base=bases[1]), work_id="W1", order=2)


# ── ① 격리 ──────────────────────────────────────────────────────────────────────

def test_worktree_is_a_sibling_not_a_child() -> None:
    """🔴 체크아웃 *안*에 두면 git 이 자기 트리를 삼킨다."""
    w = I.worktree_path(FakeFacts(), "W1")
    check("형제 디렉토리", w == r"E:\trunk\ax-wt-W1", w)
    check("체크아웃 안이 아니다", not w.startswith(r"E:\trunk\ModularStage"), w)

    lin = FakeFacts(os="linux", path="/home/sim/trunk/ModularStage")
    check("리눅스 경로", I.worktree_path(lin, "W1") == "/home/sim/trunk/ax-wt-W1",
          I.worktree_path(lin, "W1"))
    check("이름을 안전하게 만든다", "/" not in I.worktree_path(lin, "a/b").rsplit("/", 1)[-1])
    try:
        I.worktree_path(FakeFacts(), "")
        check("🔴 빈 work_id 는 예외", False, "통과해버렸다")
    except I.IntegrateError:
        check("빈 work_id 는 예외", True)


def test_worktree_is_detached_and_verified() -> None:
    g = Git(head="aaaa111")
    wt = I.ensure_worktree(FakeFacts(), "W1", at_commit="aaaa111", runner_=g)
    check("세웠다", wt.ok, wt.error)
    check("fetch 를 먼저 한다", g.ran("fetch --prune origin"))
    check("🔴 detached 로 만든다", g.ran("worktree add --detach"), str(g.calls))
    check("만들었다고 표시", wt.created)

    # 🔴 "맞췄다" 는 보고를 믿지 않는다 — HEAD 를 되읽어 대조한다
    bad = I.ensure_worktree(FakeFacts(), "W1", at_commit="deadbee", runner_=Git(head="aaaa111"))
    check("HEAD 가 다르면 막는다", not bad.ok, bad.error)
    check("사유가 대조 실패를 말한다", "기대" in bad.error, bad.error)


def test_dirty_reuse_is_reverted_first() -> None:
    """앞 실행이 남긴 적용물 위에 또 쓰면 무엇이 이번 변경인지 알 수 없다."""
    g = Git(worktree_exists=True, dirty=" M Source/A/Foo.h")
    wt = I.ensure_worktree(FakeFacts(), "W1", at_commit="aaaa111", runner_=g)
    check("재사용", wt.ok and not wt.created, wt.error)
    check("되돌린 뒤 쓴다", g.ran("checkout -- ."), str(g.calls))
    check("기준으로 맞춘다", g.ran("checkout --detach --force aaaa111"))


def test_no_fetch_no_worktree() -> None:
    class NoFetch(Git):
        def __call__(self, facts, cmd):
            if "fetch" in cmd:
                return 1, "fatal: unable to access"
            return super().__call__(facts, cmd)

    wt = I.ensure_worktree(FakeFacts(), "W1", at_commit="aaaa111", runner_=NoFetch())
    check("🔴 fetch 실패면 만들지 않는다", not wt.ok, wt.error)


# ── ② 기준 커밋 ─────────────────────────────────────────────────────────────────

def test_mixed_or_missing_base_refuses() -> None:
    check("한 기준이면 통과", I.one_base([resp("a", {H: HDR}), resp("b", {H: HDR})]) == "aaaa111")
    try:
        I.one_base([resp("a", {H: HDR}, base="aaaa111"), resp("b", {H: HDR}, base="ffff999")])
        check("🔴 기준이 섞이면 예외", False, "통과해버렸다")
    except I.IntegrateError as e:
        check("기준이 섞이면 예외", "섞여" in str(e), str(e))
    try:
        I.one_base([resp("a", {H: HDR}, base="")])
        check("🔴 기준이 없으면 예외", False, "통과해버렸다")
    except I.IntegrateError as e:
        check("기준이 없으면 예외", "비었다" in str(e), str(e))


def test_handoff_takes_only_passing_responses_in_order() -> None:
    paths, root = tmp_paths()
    try:
        spool_two(paths)
        bad = INF.Response(task_id="t3", status="BLOCKED", want=[H], base_commit="aaaa111")
        INF.spool(paths, bad, work_id="W1", order=3)
        got = I.load_handoff(paths, "W1")
        check("통과분만", [r.task_id for r in got] == ["t1", "t2"], str([r.task_id for r in got]))
        check("epoch 이 살아 온다", got[0].epoch == 7, str(got[0].epoch))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── ③ 층1 이 먼저 ───────────────────────────────────────────────────────────────

def test_layer1_blocks_before_any_write_or_build() -> None:
    """🔴 무료 검사가 비싼 빌드 앞에 있다 — 막히면 **적용도 빌드도 하지 않는다.**"""
    g = Git()
    built = []
    wrote = []
    r = resp("t1", {H: HDR.replace("\tint32 GetStep() const;", "\t// [PSEUDO] 나중에")})
    a = I.apply_one(FakeFacts(), r, tree=r"E:\trunk\ax-wt-W1", project="ModularStage",
                    baseline=lambda p: HDR,
                    builder=lambda *args, **kw: built.append(1) or Build(),
                    writer=lambda f, p, t: wrote.append(p), runner_=g)
    check("층1 에서 막혔다", not a.ok, a.summary)
    check("🔴 파일을 쓰지 않았다", not wrote, str(wrote))
    check("🔴 빌드를 부르지 않았다", not built)
    check("커밋도 없다", not g.ran(" commit "))


def test_layer1_without_baseline_is_not_a_pass() -> None:
    """🔴 fail-closed — 기준 원본이 없으면 동결을 **확인하지 못한 것**이고, 그렇게 적는다."""
    L = I.layer1({H: HDR})
    check("검사는 돌았다", L.checked)
    check("미검사를 말한다", "미검사" in L.summary, L.summary)
    check("동결 못 본 파일을 센다", L.skipped == [H], str(L.skipped))


def test_freeze_semantics() -> None:
    add = HDR.replace("\tint32 GetStep() const;", "\tint32 GetStep() const;\n\tvoid New();")
    chg = HDR.replace("SetData(const FMissionTaskInfo& InTaskInfo)", "SetData(FMissionTaskInfo In)")
    dele = HDR.replace("\tint32 GetStep() const;\n", "")
    fill = HDR.replace("\tint32 GetStep() const;", "\tint32 GetStep() const { return 0; }")
    for name, new, want_ok in [("추가는 허용", add, True), ("시그니처 변경은 위반", chg, False),
                               ("선언 삭제는 위반", dele, False), ("본문 채움은 허용", fill, True)]:
        L = I.layer1({H: new}, baseline=lambda p: HDR)
        check(name, L.ok is want_ok, L.summary)
    # 🔴 `.cpp` 는 동결 대상이 아니다 — 동결은 **선언**의 문제다
    L = I.layer1({C: "void UFoo::Other() {}\n"}, baseline=lambda p: CPP)
    check(".cpp 는 동결 대상이 아니다", L.ok, L.summary)


# ── ④ 🔴 실패는 커밋하지 않는다 ────────────────────────────────────────────────

def test_build_failure_reverts_and_does_not_commit() -> None:
    g = Git()
    r = resp("t1", {H: HDR, C: CPP})
    a = I.apply_one(FakeFacts(), r, tree=r"E:\trunk\ax-wt-W1", project="ModularStage",
                    baseline=lambda p: HDR if p == H else CPP,
                    builder=lambda *args, **kw: Build(passed=False),
                    writer=lambda *x: None, runner_=g)
    check("실패", not a.ok, a.summary)
    check("🔴 커밋하지 않았다", not g.ran(" commit "), str(g.calls))
    check("되돌렸다", a.reverted and g.ran("checkout -- "), str(g.calls))
    check("🔴 reset --hard 를 쓰지 않았다", not g.ran("reset --hard"))
    check("🔴 git clean 을 쓰지 않았다", not g.ran("clean"))
    # 되돌리기 범위는 **이번 조각의 파일**뿐이다
    rev = [c for c in g.calls if "checkout -- " in c][0]
    check("범위가 이번 파일뿐", H in rev and C in rev and "." not in rev.split("checkout -- ")[1][:2],
          rev)


def test_feedback_block_is_not_source_and_carries_the_raw_verdict() -> None:
    a = I.Applied(task_id="t1", files=[H])
    a.l1 = I.layer1({H: "// [PSEUDO] x"}, baseline=lambda p: None)
    a.build = Build(passed=False)
    fb = I.feedback_block(a)
    check("[FEEDBACK] 로 시작", fb.startswith(I.FEEDBACK_BEGIN), fb[:40])
    check("층1 사유를 담는다", "PSEUDO" in fb)
    check("빌드 원문 꼬리를 담는다", "C2065" in fb, fb[-200:])
    check("요약하지 말라는 규약을 지킨다", "원문이 근거다" in fb)
    check("되돌렸다고 말한다", "커밋하지 않았다" in fb)


def test_build_pass_commits() -> None:
    g = Git()
    r = resp("t1", {H: HDR})
    a = I.apply_one(FakeFacts(), r, tree=r"E:\trunk\ax-wt-W1", project="ModularStage",
                    baseline=lambda p: HDR, builder=lambda *args, **kw: Build(),
                    writer=lambda *x: None, runner_=g)
    check("통과", a.ok, a.summary)
    check("커밋했다", g.ran(" commit "), str(g.calls))
    check("커밋 sha 를 들고 온다", a.commit.startswith("bbbb"), a.commit)
    check("add 범위가 파일 단위", g.ran(f'add -- "{H}"'), str(g.calls))


def test_no_change_is_not_a_silent_pass() -> None:
    g = Git(commit_rc=1)
    a = I.apply_one(FakeFacts(), resp("t1", {H: HDR}), tree="T", project="ModularStage",
                    baseline=lambda p: HDR, builder=lambda *args, **kw: Build(),
                    writer=lambda *x: None, runner_=g)
    check("변경 없음을 말한다", not a.ok and "변경이 없다" in a.error, a.summary)


def test_missing_engine_blocks_instead_of_passing() -> None:
    """⚠️ 확인 불가는 통과가 아니다."""
    a = I.apply_one(FakeFacts(ue5=""), resp("t1", {H: HDR}), tree="T", project="ModularStage",
                    baseline=lambda p: HDR, builder=lambda *args, **kw: Build(),
                    writer=lambda *x: None, runner_=Git())
    check("엔진 없으면 막는다", not a.ok and "Build.bat" in a.error, a.summary)


# ── ⑤ 순차 · 중단 · push ────────────────────────────────────────────────────────

def _run(paths, *, git=None, builds=None, durable="task/w1", push=True, stop=True, submits=None):
    g = git or Git()
    seq = list(builds or [Build(), Build()])

    def builder(*args, **kw):
        return seq.pop(0) if seq else Build()

    def api(method, path, payload=None, **kw):
        if submits is not None:
            submits.append((path.rsplit("/", 1)[-1], path.split("/")[-2], payload))
        return {"ok": True}

    itg = I.run(paths, FakeFacts(), "W1", durable=durable, stop_on_fail=stop,
                baseline=lambda p: HDR, builder=builder, writer=lambda *x: None,
                runner_=g, push=push, api=api)
    return itg, g


def test_sequential_and_stops_at_first_failure() -> None:
    paths, root = tmp_paths()
    try:
        spool_two(paths)
        subs = []
        itg, g = _run(paths, builds=[Build(passed=False), Build()], submits=subs)
        check("조각 2개를 다뤘다", len(itg.applied) == 2, itg.summary())
        check("첫 조각 실패", not itg.applied[0].ok)
        check("🔴 둘째는 적용조차 안 했다", itg.applied[1].skipped, itg.applied[1].summary)
        check("사유가 선행 실패", "선행" in itg.applied[1].skipped, itg.applied[1].skipped)
        check("push 하지 않았다", not itg.pushed)
        check("실패는 큐에 되돌린다",
              any(k == "submit-fail" for k, _, _ in subs), str(subs))
        check("🔴 통과한 게 없으니 submit 도 없다",
              not any(k == "submit" for k, _, _ in subs), str(subs))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_partial_pass_keeps_the_increment() -> None:
    """🔴 이 마일스톤의 값 — 조각 2가 깨져도 **조각 1은 컴파일되는 상태로 남는다.**"""
    paths, root = tmp_paths()
    try:
        spool_two(paths)
        itg, g = _run(paths, builds=[Build(), Build(passed=False)], stop=True)
        check("첫 조각은 커밋됐다", itg.applied[0].ok, itg.applied[0].summary)
        check("둘째는 실패", not itg.applied[1].ok)
        check("통과분이 있다", len(itg.passed) == 1, itg.summary())
        # ⚠️ 실패가 하나라도 있으면 `ok` 는 아니다 — 그래도 증분은 남는다
        check("전체는 ok 가 아니다", not itg.ok)
        check("🔴 통과분은 push 한다", itg.pushed, itg.summary())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_push_is_ff_only_and_refusal_is_not_forced() -> None:
    paths, root = tmp_paths()
    try:
        spool_two(paths)
        itg, g = _run(paths, git=Git(push_rc=1))
        push = [c for c in g.calls if " push " in c][0]
        check("ff-only 형태", "HEAD:refs/heads/task/w1" in push, push)
        check("🔴 force 를 쓰지 않는다", "--force" not in push and "-f " not in push, push)
        check("거부를 말한다", "push 거부" in itg.note, itg.note)
        check("커밋이 남아 있다고 말한다", "잃지 않았다" in itg.note, itg.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_durable_means_local_only_and_says_so() -> None:
    paths, root = tmp_paths()
    try:
        spool_two(paths)
        itg, g = _run(paths, durable="")
        check("커밋은 했다", len(itg.passed) == 2, itg.summary())
        check("push 는 안 했다", not itg.pushed and not g.ran(" push "))
        check("로컬까지만이라고 말한다", "로컬 커밋까지만" in itg.note, itg.note)
        check("요청자가 만들어야 한다고 말한다", "요청자" in itg.note, itg.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_submit_carries_epoch_and_build_evidence() -> None:
    """🔴 제출은 통합자만 한다 (소 1.4.3) — 근거는 빌드를 통과한 커밋이다."""
    paths, root = tmp_paths()
    try:
        spool_two(paths)
        subs = []
        itg, g = _run(paths, submits=subs)
        ok = [(tid, p) for k, tid, p in subs if k == "submit"]
        check("통과분마다 제출", len(ok) == 2, str(subs))
        _, payload = ok[0]
        check("durable 브랜치를 싣는다", payload["branch"] == "task/w1", str(payload))
        check("커밋을 싣는다", payload["head_commit"].startswith("bbbb"), str(payload))
        check("🔴 epoch 을 싣는다 (fencing)", payload["epoch"] == 7, str(payload))
        check("빌드 판정을 근거로 싣는다", "BUILD OK" in payload["self_check"]["build"],
              str(payload["self_check"]))
        check("통합자가 했다고 적는다", payload["self_check"]["by"] == "integrator")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_spool_is_an_error_not_an_empty_run() -> None:
    paths, root = tmp_paths()
    try:
        try:
            I.load_handoff(paths, "nope")
            check("🔴 스풀 없으면 예외", False, "통과해버렸다")
        except I.IntegrateError as e:
            check("스풀 없으면 예외", "스풀이 없다" in str(e), str(e))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (test_worktree_is_a_sibling_not_a_child,
               test_worktree_is_detached_and_verified,
               test_dirty_reuse_is_reverted_first, test_no_fetch_no_worktree,
               test_mixed_or_missing_base_refuses,
               test_handoff_takes_only_passing_responses_in_order,
               test_layer1_blocks_before_any_write_or_build,
               test_layer1_without_baseline_is_not_a_pass, test_freeze_semantics,
               test_build_failure_reverts_and_does_not_commit,
               test_feedback_block_is_not_source_and_carries_the_raw_verdict,
               test_build_pass_commits, test_no_change_is_not_a_silent_pass,
               test_missing_engine_blocks_instead_of_passing,
               test_sequential_and_stops_at_first_failure,
               test_partial_pass_keeps_the_increment,
               test_push_is_ff_only_and_refusal_is_not_forced,
               test_no_durable_means_local_only_and_says_so,
               test_submit_carries_epoch_and_build_evidence,
               test_no_spool_is_an_error_not_an_empty_run):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_integrate: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
