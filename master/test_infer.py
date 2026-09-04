"""추론 파견 (중 1.3).

[중요] 지키는 계약은 넷이다:

    ① 판정은 **fail-closed** — 마커·응답파일 둘 다 맞아야 통과다
    ② 대상 파일은 **매니페스트에서** 읽는다 (워커가 본 것과 같은 문서)
    ③ 같은 추론을 **두 번 사지 않는다** — 스풀에 같은 기준 커밋의 통과분이 있으면 재사용
    ④ **실패한 선행의 후속은 파견하지 않는다** — 큐는 `failed` 를 의존 해소로 세므로 (실측)

`.venv/bin/python master/test_infer.py`
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import infer as I      # noqa: E402
from master.work import runner as R     # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


WANT = ["Source/A/Foo.h", "Source/A/Foo.cpp"]
GOOD_RESPONSE = ("=== FILE: Source/A/Foo.h ===\n#pragma once\nclass A {};\n"
                 "=== FILE: Source/A/Foo.cpp ===\n#include \"Foo.h\"\n")
def _t(task_id, **kw):
    """가짜 claim 레코드. [중요] **대상 파일이 레코드에 있다** (2026-09-01) — 파견은 이제
    매니페스트를 읽지 않고 큐 레코드에서 목록을 만들며, 그 하나가 워커 지시와 판정에 같이 쓰인다.
    """
    d = {"task_id": task_id, "target_file": "Source/A/Foo.cpp",
         "header_file": "Source/A/Foo.h"}
    d.update(kw)
    return d


MANIFEST = """# 컨텍스트 매니페스트 — `t1`

## 기준 (커밋·브랜치)

- 커밋 `abc1234`

## 대상 클래스

- `UFoo`

## 대상 파일 — [중요] **이 목록 밖은 건드리지 않는다**

- `Source/A/Foo.h`
- `Source/A/Foo.cpp`

[중요] **한 태스크의 파일은 한 워커가 통째로 맡는다.**

## 계약 (동결 — 바꾸지 말 것)

- `NotAFile.h` 는 계약 절의 낱말이다
"""


@dataclass
class FakeFacts:
    """`HostFacts` 대역 — 파견 판정이 보는 것만."""
    host: str = "w1"
    user: str = "u"
    path: str = "/checkout"
    driven: str = "ssh"
    role: str = "worker"
    os: str = "linux"
    claude: str = "/usr/bin/claude"
    checkout_ok: bool = True
    capabilities: list = field(default_factory=list)
    # [주의] `#321` — 파견 판정이 보는 축이 하나 늘었다 (`role` = 자격, `dispatch` = 가용성).
    dispatch: str = ""

    @property
    def dispatchable(self) -> bool:
        if self.role != "worker":
            return False
        return True if not self.dispatch else (self.dispatch == "always")

    @property
    def windows(self) -> bool:
        return self.os == "windows"


class Clean:
    ok = True
    reason = ""


def tmp_paths():
    """`ProjectPaths` 대역 — 스풀과 (⑷ 용) `repo` 만 쓴다."""
    root = Path(tempfile.mkdtemp(prefix="axinfer"))

    class P:
        name = "T"
        repo = root / "repo"

        @property
        def responses(self):
            return root / "responses"
    return P(), root


# ── 정본 ⑸ 주입 대역 ─────────────────────────────────────────────────────────
# [중요] **실물 증명은 `test_wcommit.py`(실 git)가 한다.** 여기서 잴 것은 큐 오케스트레이션 —
#    누구를 몇 건 집나 · 순서 · 재사용 · 실패 후속 차단 · **커밋이 생기면 제출하나**.

SUB_TIP = "1" * 40          # 서브 브랜치가 선 커밋 (= 골조 커밋)
WORKER_HEAD = "2" * 40      # 워커가 만든 커밋


def _fake_subbranch(monkey=True):
    """⑷ 를 주입으로 세운다 — 실 git 없이 「브랜치가 있다」를 만든다."""
    from master.work import subbranch as SB

    def create(paths, work_id, task_id, *, base_commit, remote="", logf=None, round_no=0):
        # [중요] 이름에 라운드가 들어간다 (`task/<work>/r<N>/<task>`) — 대역도 실물과 같은
        #    규약을 써야 「어느 라운드 브랜치에 커밋했나」를 테스트가 잴 수 있다.
        return SB.Created(task_id=task_id,
                          branch=SB.branch_names.durable_branch(work_id, task_id, round_no),
                          tip=base_commit, created=True)
    orig = SB.create
    SB.create = create
    return SB, orig


def _fake_shell(bodies):
    """checkout·commit 명령을 흉내낸다. `bodies` 가 비면 커밋이 안 생긴 것으로 본다."""
    def ssh(facts, cmd, timeout):
        if "checkout -q -B" in cmd:
            return 0, SUB_TIP
        if "git commit" in cmd:
            return (0, WORKER_HEAD) if bodies else (1, "nothing to commit")
        return 0, ""
    return ssh


def test_no_target_list_is_blocked_not_passed() -> None:
    """[중요] 무엇을 받아야 하는지 모르면 무엇을 받아도 통과시킬 수 없다."""
    r = I.judge("RESULT: DONE", GOOD_RESPONSE, want=[])
    check("목록 없으면 BLOCKED", not r.ok and r.status == R.BLOCKED, r.summary)
    check("사유가 목록 부재를 말한다", "대상 파일 목록" in r.reason, r.reason)


# ── ① fail-closed 판정 ─────────────────────────────────────────────────────────

def test_marker_and_file_must_both_hold() -> None:
    ok = I.judge("RESPONSE: 2\nRESULT: DONE", GOOD_RESPONSE, want=WANT)
    check("둘 다 맞으면 통과", ok.ok, ok.summary)
    check("본문을 들고 온다", set(ok.files) == set(WANT), str(list(ok.files)))

    no_marker = I.judge("두 파일 다 작성했습니다!", GOOD_RESPONSE, want=WANT)
    check("마커 없으면 BLOCKED", not no_marker.ok, no_marker.summary)

    no_file = I.judge("RESPONSE: 2\nRESULT: DONE", "", want=WANT)
    check("응답 파일 없으면 BLOCKED", not no_file.ok, no_file.summary)
    check("사유가 응답 파일을 지목한다", I.RESPONSE_NAME in no_file.reason, no_file.reason)


def test_missing_file_is_not_partial_success() -> None:
    r = I.judge("RESPONSE: 1\nRESULT: DONE",
                "=== FILE: Source/A/Foo.h ===\nx\n", want=WANT)
    check("하나 빠지면 BLOCKED", not r.ok, r.summary)
    check("무엇이 빠졌는지 말한다", r.missing == ["Source/A/Foo.cpp"], str(r.missing))


def test_out_of_scope_path_blocks() -> None:
    """[중요] 목록 밖 파일을 낸 것은 **분해 계획 밖을 고치려 한 것**이다 — 조용히 버리지 않는다."""
    r = I.judge("RESULT: DONE", GOOD_RESPONSE + "=== FILE: Source/Evil.h ===\nx\n", want=WANT)
    check("목록 밖이면 BLOCKED", not r.ok, r.summary)
    check("버린 사실이 치명 메모로 남는다",
          any("요청하지 않은 경로" in n for n in r.fatal), str(r.notes))


def test_fence_residue_blocks() -> None:
    r = I.judge("RESULT: DONE",
                "=== FILE: Source/A/Foo.h ===\n```cpp\nx\n```\n"
                "=== FILE: Source/A/Foo.cpp ===\ny\n", want=WANT)
    check("펜스 잔재는 BLOCKED", not r.ok, r.summary)


def test_blocked_reason_survives() -> None:
    """[중요] 비대칭은 의도다 — 안전한 판정 쪽(BLOCKED)에만 관대하다."""
    r = I.judge("RESULT: BLOCKED — Source/ 가 더럽다", "", want=WANT)
    check("사유를 살린다", "더럽다" in r.reason, r.reason)
    loose_done = I.judge("RESULT: DONE — 다 했어요", GOOD_RESPONSE, want=WANT)
    check("DONE 에는 관대하지 않다", not loose_done.ok, loose_done.summary)


def test_marker_does_not_demand_branch_or_commit() -> None:
    """[중요] 추론 파견에는 ATTEMPT/HEAD 가 **없는 것이 정상**이다 — 사유가 거짓이면 안 된다."""
    r = I.judge("RESPONSE: 2\nRESULT: DONE", GOOD_RESPONSE, want=WANT)
    check("ATTEMPT 를 요구하지 않는다", r.ok, r.summary)
    check("사유에 ATTEMPT 가 안 나온다", "ATTEMPT" not in r.reason, r.reason)


def test_markers_inside_the_response_file_are_stripped_and_reported() -> None:
    """[중요] 실전 첫 구동에서 나온 결함 (2026-08-12) — 안 떼면 `.cpp` 끝에 `RESULT: DONE` 이 박힌다."""
    polluted = GOOD_RESPONSE + "RESPONSE: 2\nRESULT: DONE\n"
    r = I.judge("RESPONSE: 2\nRESULT: DONE", polluted, want=WANT)
    check("그래도 통과시킨다 (본문은 옳다)", r.ok, r.summary)
    check("마커가 본문에 안 남았다",
          not any("RESULT: DONE" in v for v in r.files.values()),
          str([v[-30:] for v in r.files.values()]))
    check("뗀 사실을 [주의] 로 말한다",
          any("판정 마커" in n for n in r.notes), str(r.notes))

    clean, n = I.strip_trailing_markers(polluted)
    check("두 줄을 뗐다", n == 2, str(n))
    # [주의] 중간의 같은 글자는 건드리지 않는다
    mid = "=== FILE: Source/A/Foo.h ===\n// RESULT: DONE 은 주석이다\nx\n"
    _, n2 = I.strip_trailing_markers(mid)
    check("중간은 안 건드린다", n2 == 0, str(n2))


def test_eof_newline_is_normalized_to_one() -> None:
    """[중요] 실측 2026-08-12 — `parse_files` 의 strip 이 끝 개행을 지워 EOF 잡음 diff 를 만들었다.

    `Source/ModularStage` 160개 실측: 개행 하나 110 · 없음 36 · 빈 줄 14 → 하나로 맞춘다.
    """
    r = I.judge("RESULT: DONE", GOOD_RESPONSE, want=WANT)
    for k, v in r.files.items():
        check(f"{k}: 개행 하나로 끝난다", v.endswith("\n") and not v.endswith("\n\n"), repr(v[-6:]))


def test_count_mismatch_is_warned_not_failed() -> None:
    r = I.judge("RESPONSE: 5\nRESULT: DONE", GOOD_RESPONSE, want=WANT)
    check("신고 수가 틀려도 통과", r.ok, r.summary)
    check("어긋남을 [주의] 로 남긴다", any(n.startswith("[주의]") for n in r.notes), str(r.notes))


# ── 파견 한 건 — 배달·되읽기·계측 ──────────────────────────────────────────────

def test_infer_task_delivers_reads_and_judges() -> None:
    f = FakeFacts()
    delivered: dict = {}

    def writer(facts, rel, content, base="home"):     # 불리면 그 자체가 실패다
        delivered[rel] = content
        return rel

    def fake_runner(facts, task_id, timeout):
        return 0, json.dumps({"result": "RESPONSE: 2\nRESULT: DONE",
                              "total_cost_usd": 0.0123})

    def reader(facts, abs_path):
        check("응답을 체크아웃 안에서 읽는다", abs_path.startswith("/checkout"), abs_path)
        return GOOD_RESPONSE

    r = I.infer_task(f, "t1", want=WANT, runner_=fake_runner, reader=reader)
    check("통과", r.ok, r.summary)
    # [중요] **아무것도 배달하지 않는다** (매니페스트 철거 2026-09-02) — 지시서는 골조 주석이다
    check("[중요] 배달이 없다", not delivered, str(list(delivered)))
    check("계측을 들고 온다", abs(r.cost_usd - 0.0123) < 1e-9, str(r.usage))
    check("워커를 기록한다", r.worker == "w1", r.worker)


def test_ssh_failure_does_not_pass_a_done() -> None:
    f = FakeFacts()

    def fake_runner(facts, task_id, timeout):
        return 1, "RESPONSE: 2\nRESULT: DONE"

    r = I.infer_task(f, "t1", want=WANT, runner_=fake_runner, reader=lambda *a: GOOD_RESPONSE)
    check("rc≠0 이면 DONE 을 접지 않는다", not r.ok, r.summary)
    check("rc 를 사유에 적는다", "rc=1" in r.reason, r.reason)


def test_unreadable_response_is_not_absent() -> None:
    """[중요] '못 읽었다' 를 '없다' 로 접으면 조용히 틀린다 (`_remote_read` 가 배운 것)."""
    from master.client import bundle
    f = FakeFacts()

    def boom(facts, abs_path):
        raise bundle.BundleError("scp 거부")

    r = I.infer_task(f, "t1", want=WANT, runner_=lambda *a: (0, "RESULT: DONE"), reader=boom)
    check("읽기 실패는 BLOCKED", not r.ok, r.summary)
    check("읽기 실패를 사유에 적는다", "읽기 실패" in r.reason, r.reason)


def test_windows_response_path_uses_backslash() -> None:
    w = FakeFacts(os="windows", path=r"E:\trunk\ModularStage")
    p = I.response_path(w, "t9")
    check("윈도우 경로는 역슬래시", p == r"E:\trunk\ModularStage\.ax\work\t9\response.txt", p)
    check("리눅스 경로는 슬래시",
          I.response_path(FakeFacts(), "t9") == "/checkout/.ax/work/t9/response.txt")


def test_instruction_is_ascii_and_names_the_skill() -> None:
    """[중요] 명령줄에 한글을 실으면 워커 콘솔에서 깨진다 (두 번 물린 함정)."""
    cmd = I.infer_command(FakeFacts(), "t1")
    check("ASCII 만", all(ord(c) < 128 for c in cmd), repr([c for c in cmd if ord(c) >= 128]))
    check("ax-infer 를 지목한다", "ax-infer" in cmd, cmd[:80])
    check("ax-work 가 아님을 못박는다", "not ax-work" in cmd)
    check("계측을 켠다", "--output-format json" in cmd)


# ── ③ 스풀 — 돈을 낸 출력이다 ──────────────────────────────────────────────────

def test_spool_round_trip() -> None:
    paths, root = tmp_paths()
    try:
        r = I.judge("RESULT: DONE", GOOD_RESPONSE, want=WANT)
        r.task_id, r.worker, r.base_commit = "t1", "w1", "abc1234"
        p = I.spool(paths, r, work_id="W1", order=3)
        check("스풀 파일이 생긴다", Path(p).is_file(), p)
        back = I.unspool(paths, "t1", "W1")
        check("본문이 살아 돌아온다", back.files == r.files, str(list(back.files)))
        check("기준 커밋이 남는다", back.base_commit == "abc1234", back.base_commit)
        check("재사용 표시가 붙는다", back.reused)
        check("없는 것은 None", I.unspool(paths, "nope", "W1") is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_failure_is_spooled_too() -> None:
    """[중요] 실패도 남긴다 — 무엇을 시도했는지가 사라지면 피드백의 근거가 없다."""
    paths, root = tmp_paths()
    try:
        r = I.judge("RESULT: BLOCKED — 계약 모순", "", want=WANT)
        r.task_id = "t2"
        I.spool(paths, r, work_id="W1", order=1)
        back = I.unspool(paths, "t2", "W1")
        check("실패가 스풀에 있다", back is not None and back.status == R.BLOCKED)
        check("사유가 남는다", "계약 모순" in back.reason, back.reason)
        check("실패는 재사용 대상이 아니다",
              I.reusable(paths, "t2", base_commit="", work_id="W1") is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_same_base_commit_is_reused_other_is_not() -> None:
    paths, root = tmp_paths()
    try:
        r = I.judge("RESULT: DONE", GOOD_RESPONSE, want=WANT)
        r.task_id, r.base_commit = "t1", "abc1234"
        I.spool(paths, r, work_id="W1", order=1)
        same = I.reusable(paths, "t1", base_commit="abc1234", work_id="W1")
        check("같은 기준이면 재사용", same is not None and same.ok)
        moved = I.reusable(paths, "t1", base_commit="deadbee", work_id="W1")
        # [주의] 트윈이 움직였으면 근거가 달라졌다 — 낡은 응답은 남의 실패로 빌드를 깬다
        check("기준이 다르면 재사용 안 함", moved is None)
        check("기준 미상이면 재사용 안 함",
              I.reusable(paths, "t1", base_commit="", work_id="W1") is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 다건 파견 + ④ 선행 실패 차단 ───────────────────────────────────────────────

class FakeQueue:
    """큐 대역. `tasks` 를 순서대로 내주고 submit-fail 을 기록한다."""

    def __init__(self, tasks: list):
        self.tasks = list(tasks)
        self.failed: list = []
        self.submitted: list = []      # 🔴 정본 ⑸ — 커밋이 생기면 여기 쌓인다
        self.verified: list = []       # 🔴 정본 ⑹ — 판정이 나야 `.33` 공지가 나간다
        self.cancelled: list = []      # 🔴 「할 일 없음」 종결 (claim 앞에서 걷어낸 것)
        self.claims = 0                # claim 호출 횟수
        # 🔴 [중요] **실제로 워커에 건네진 조각**. ⓐ(claim 뒤 판정)와 ⓑ(claim 앞 판정)를
        #    가르는 것은 이것 하나다 — 폴백이 뒤에서 같은 결과를 내므로 `cancelled` 만
        #    보면 두 설계가 구분되지 않는다(실측: 사전 훑기를 꺼도 테스트가 통과했다).
        self.handed: list = []
        self.beats = 0

    def __call__(self, method, path, payload=None, *, timeout=20):
        if method == "GET" and "/works/" in path:
            # [중요] 사전 훑기(`prescreen_nowork`)가 읽는 표면이다 — 없으면 훑기가
            #    조용히 생략되고 **claim 앞에서 걷는지**를 잴 수 없다.
            return {"work": {"work_id": path.rsplit("/", 1)[-1]},
                    "tasks": [{**t, "status": "pending"} for t in self.tasks]}
        if path.endswith("/cancel"):
            tid = path.split("/")[-2]
            self.cancelled.append((tid, dict(payload or {})))
            self.tasks = [t for t in self.tasks if t.get("task_id") != tid]
            return {"ok": True}
        if path.endswith("/claim"):
            self.claims += 1
            if not self.tasks:
                return None
            t = self.tasks.pop(0)
            self.handed.append(t.get("task_id"))
            return t
        if path.endswith("/heartbeat"):
            self.beats += 1
            return {"ok": True}
        if path.endswith("/submit-fail"):
            self.failed.append((path.split("/")[-2], (payload or {}).get("reason", "")))
            return {"ok": True}
        if path.endswith("/submit"):
            self.submitted.append(dict(payload or {}))
            return {"ok": True}
        if path.endswith("/verify"):
            self.verified.append((path.split("/")[-2], dict(payload or {})))
            return {"ok": True}
        raise AssertionError(f"예상 밖 호출: {method} {path}")


def _counting_runner(stdout, calls):
    """워커 호출을 센다 — [중요] **ⓐ 는 「부르지 않았다」를 재는 것**이라 세지 않으면 못 잰다."""
    def call(f, t, to):
        if calls is not None:
            calls.append((getattr(f, "host", "?"), t))
        return (0, stdout)
    return call


def _run(paths, q, *, body="void X::Go() { Do(); }\n", workers=1,
         limit=4, parallel=True, stdout="RESULT: DONE", runner_calls=None):
    """정본 ⑸ 로 한 바퀴 — 워커가 본문을 쓰고 마스터가 커밋한다.

    `body` 가 비면 **본문이 안 채워진 것**이라 커밋이 생기지 않는다(fail-closed).
    """
    facts = [FakeFacts(host=f"w{i+1}") for i in range(workers)]
    SB, orig = _fake_subbranch()
    import master.work.twin_base as TB
    saved_bl, saved_tb = TB.local_baseline, TB.resolve

    class _Base:
        commit = SUB_TIP

    TB.local_baseline = lambda p, b: None      # 동결 원본 없음 → 층1 이 미검사로 기록
    TB.resolve = lambda p, w: _Base()          # 작업 브랜치 tip (골조 커밋)
    try:
        return I.run_many(paths, limit=limit, facts=facts, api=q, clean=lambda f: Clean(),
                          parallel=parallel, work_id="W1",
                          runner_=_counting_runner(stdout, runner_calls),
                          ssh=_fake_shell(body),
                          reader=lambda f, p: body)
    finally:
        SB.create = orig
        TB.local_baseline, TB.resolve = saved_bl, saved_tb


def test_run_many_takes_several_and_orders_them() -> None:
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1", epoch=1), _t("t2", epoch=1)])
        hand = _run(paths, q)
        check("두 건을 파견했다", len(hand.items) == 2, str(hand.items))
        check("둘 다 통과", len(hand.ordered()) == 2, hand.summary())
        ids = [r.task_id for r in hand.ordered()]
        check("적용 순서는 파견 순서", ids == ["t1", "t2"], str(ids))
        check("큐가 비면 멈춘다", not q.tasks)
        # 🔴 정본 ⑸ — **커밋이 생긴 시점이 태스크가 끝난 시점**이므로 여기서 제출한다
        #    (원전 `... commit·push → submit_result → 다시 claim`). 종전에는 통합자에 뒀고,
        #    그래서 리스가 붙잡힌 채 만료돼 **같은 추론을 다시 사는** 자리가 됐다.
        check("[중요] **커밋이 생기면 제출한다**", len(q.submitted) == 2, str(q.submitted))
        check("  브랜치와 커밋을 실어 보낸다",
              all(p.get("branch", "").startswith("task/W1/") and p.get("head_commit")
                  for p in q.submitted), str(q.submitted))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_committed_piece_is_verified_so_the_requester_gets_told() -> None:
    """🔴 정본 ⑹ — **조각이 다 끝나면 `.33` 에 완료를 공지한다.** 그 공지의 방아쇠가 여기다.

    큐는 `terminal = verified + failed + cancelled` 가 `total` 에 닿을 때만 work 을
    `ready_for_review` 로 뒤집고, 그 flip 에 Redmine [리뷰 요청] 이슈 생성이 달려 있다
    (`task_queue/logic_cleanup.py`). 즉 **submit 만 하면 공지는 영원히 안 나간다.**

    [중요] 실측 2026-09-03 22:30 — 조각 4/4 가 커밋에 성공했는데 전부 `submitted` 로 남아
    terminal 0/4, `[work-ready]` 0건, Redmine 0건, `.33` 은 끝난 줄 몰랐다. 당시 판정은
    「통합자」 안에 있었고 통합은 사람 승인 대기였으므로 **승인하라는 공지가 통합 뒤에 나오는
    교착**이었다. 통합자는 지웠다(통합은 `.33` 의 자리다) — 조각의 끝은 워커 커밋이다.
    """
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1", epoch=1), _t("t2", epoch=1)])
        _run(paths, q)
        check("[중요] **커밋한 조각마다 판정이 나간다**", len(q.verified) == 2, str(q.verified))
        check("  제출한 것과 같은 태스크다",
              sorted(t for t, _ in q.verified) == sorted(
                  ["t1", "t2"]), str(q.verified))
        check("  pass 로 확정한다",
              all(p.get("result") == "pass" and p.get("passed") is True
                  for _, p in q.verified), str(q.verified))
        check("  판정 근거를 싣는다", all(p.get("feedback") for _, p in q.verified),
              str(q.verified))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dependents_of_a_failure_are_not_dispatched() -> None:
    """[중요] 큐는 `failed` 를 의존 해소로 센다(*영원 block 방지*) — 마스터가 막는다."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("X.d1", epoch=1),
                       _t("X.d2", epoch=1, depends_on=["X.d1"])])
        # 응답을 비워 첫 건을 실패시킨다
        hand = _run(paths, q, body="")
        check("첫 건 실패", hand.items and not hand.items[0][1].ok, hand.summary())
        check("후속은 파견하지 않았다", len(hand.skipped) == 1, str(hand.skipped))
        check("사유가 선행 실패를 말한다",
              hand.skipped and "X.d1" in hand.skipped[0][1], str(hand.skipped))
        check("후속을 큐에 반납했다", ("X.d2", "선행 실패") in q.failed, str(q.failed))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_worker_means_no_claim() -> None:
    """[중요] 집어놓고 못 돌리는 것이 가장 나쁘다 — claim 조차 하지 않는다."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1")])
        facts = [FakeFacts(host="r1", role="requester")]
        hand = I.run_many(paths, facts=facts, api=q, clean=lambda f: Clean(),
                          work_id="W1", runner_=lambda *a: (0, "RESULT: DONE"), reader=lambda *a: GOOD_RESPONSE)
        check("파견 0건", not hand.items, str(hand.items))
        check("태스크가 큐에 남아 있다", len(q.tasks) == 1, str(q.tasks))
        check("왜 못 했는지 말한다", "워커가 없어" in hand.note, hand.note)
        check("요청자를 제외한 사유를 적는다", "requester" in hand.note, hand.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_parallel_is_the_default() -> None:
    """🔴 [중요] **병렬이 기본값이다** (사용자 확정 2026-09-03).

    정본 ⑸: *"워커들은 각각 지정된 서브 브랜치에 커밋하고 작업을 마치고 다음 작업을 요청"* —
    **클래스 단위로 쪼개는 목적이 병렬**이다(`#343`). 종전 기본값은 `False` 였고 근거가
    *"2대는 12% 빠르고 90% 비쌌다"* 였는데, **그 비용을 감수할지는 사용자가 정한다.**
    """
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1"), _t("t2")])
        hand = _run(paths, q, workers=2)          # parallel 을 주지 않는다 = 기본값
        check("[중요] **기본값이 병렬이라 직렬 문구가 없다**", "직렬" not in hand.note, hand.note)
        check("  두 건 다 돌았다", len(hand.items) == 2, str(hand.items))
        # [중요] 워커가 1대면 「병렬로 켰다」와 「병렬로 돌았다」가 다르다 — 그것을 말해야 한다
        q1 = FakeQueue([_t("s1")])
        h1 = _run(paths, q1, workers=1)
        check("[중요] **워커 1대면 실제로는 직렬임을 말한다**",
              "1대" in h1.note and "직렬" in h1.note, h1.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_serial_only_when_asked() -> None:
    """[주의] 끄는 것은 **호출자의 명시**다 — 기본값으로 조용히 직렬이 되지 않는다."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1"), _t("t2")])
        hand = _run(paths, q, workers=2, parallel=False)
        check("직렬임을 말한다", "직렬" in hand.note, hand.note)
        check("  누가 껐는지 말한다", "명시" in hand.note, hand.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_parallel_uses_both_workers() -> None:
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1"), _t("t2")])
        hand = _run(paths, q, workers=2, parallel=True)
        used = {r.worker for _, r in hand.items}
        check("두 워커가 다 일했다", used == {"w1", "w2"}, str(used))
        check("둘 다 통과", len(hand.ordered()) == 2, hand.summary())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_limit_is_respected() -> None:
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t(f"t{i}") for i in range(5)])
        hand = _run(paths, q, limit=2)
        check("상한을 지킨다", len(hand.items) == 2, str(len(hand.items)))
        check("나머지는 큐에 남는다", len(q.tasks) == 3, str(len(q.tasks)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_handoff_states_that_nobody_applies_yet() -> None:
    """[주의] 없는 것을 있는 척하지 않는다 — 통합자(중 1.4)는 아직 비어 있다."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([_t("t1")])
        s = _run(paths, q).summary()
        check("적용이 안 됐음을 말한다", "적용은 아직" in s, s[-200:])
        check("리스 만료를 말한다", "리스" in s, s[-200:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_reuse_avoids_paying_twice() -> None:
    """[중요] 재확보는 정상 흐름이다(제출은 통합자가 한다) — 그때 추론을 다시 사지 않는다."""
    paths, root = tmp_paths()
    try:
        pre = I.judge("RESULT: DONE", GOOD_RESPONSE, want=WANT)
        pre.task_id, pre.worker, pre.base_commit = "t1", "w1", "abc1234"
        I.spool(paths, pre, work_id="W1", order=1)

        calls: list = []

        def counting_runner(f, t, to):
            calls.append(t)
            return 0, "RESULT: DONE"

        q = FakeQueue([_t("t1")])
        facts = [FakeFacts()]

        class FakeBase:
            commit = "abc1234"

        import master.work.twin_base as tb
        saved = tb.resolve
        tb.resolve = lambda p, t: FakeBase()
        try:
            hand = I.run_many(paths, facts=facts, api=q, clean=lambda f: Clean(),
                              work_id="W1", runner_=counting_runner,
                              reader=lambda *a: GOOD_RESPONSE)
        finally:
            tb.resolve = saved
        check("워커를 부르지 않았다", not calls, str(calls))
        check("그래도 인계에 들어간다", len(hand.ordered()) == 1, hand.summary())
        check("재사용 표시가 보인다", hand.ordered()[0].reused, hand.ordered()[0].summary)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 🔴 ⓐ 할 일이 없는 조각은 파견하지 않는다 (원전 「등재 skip」 이식) ─────────────────

def test_piece_without_pseudo_is_not_dispatched_at_all() -> None:
    """🔴 **추론을 사기 전에 막는다** (사용자 결정 ⓐ 2026-09-03).

    `skeleton.py` 머리말: *"`[PSEUDO]` 가 하나도 없으면 그것은 완성된 파일이지 골조가 아니다.
    **원전은 그 경우 워커 태스크 등재를 skip 한다**"*.

    실측 2026-09-03: `NSInteractionPromptWidget`(골조에 *"이 클래스에는 C++ 로직을 추가하지
    않는다"* · `[PSEUDO]` 0개)이 **두 라운드 연속** 파견돼 조각당 $0.66~$1.08 을 태우고
    실패로 기록됐다.

    🔴 [중요] **판정이 claim 앞으로 옮겼다** (사용자 결정 ⓑ, 2026-09-04). 종전에는 claim
    **뒤에** 판정하고 `submit(worker_id="(none)")` 로 종결했는데, `#318` 신원 게이트가 409 로
    막아 조각이 `claimed` 에 갇혔다(실측 21:32, `terminal 2/4` 교착 · 공지 0건).
    """
    from master.work import decompose as DC
    paths, root = tmp_paths()
    saved = DC.pseudo_in_skeleton
    calls: list = []
    DC.pseudo_in_skeleton = lambda p, c, f: (0, "")       # 골조에 마커 0
    try:
        q = FakeQueue([_t("t1", epoch=1)])
        _run(paths, q, runner_calls=calls)
        check("[중요] **워커를 부르지 않는다**", not calls, str(calls))
        check("🔴 **집지도 않는다** — 걷어낸 뒤 claim 은 빈손이다",
              q.handed == [], str(q.handed))
        check("조각을 종결한다 (cancel)", len(q.cancelled) == 1, str(q.cancelled))
        check("  「할 일 없음」으로 적힌다 — 실패도 취소도 아니다",
              all(p.get("no_work") is True for _, p in q.cancelled), str(q.cancelled))
        check("  사유가 마커를 지목한다",
              any("PSEUDO" in (p.get("reason") or "") for _, p in q.cancelled),
              str(q.cancelled))
        check("[중요] 소유권 게이트를 건드리지 않는다 (submit/verify 0)",
              not q.submitted and not q.verified,
              f"submit={q.submitted} verify={q.verified}")
    finally:
        DC.pseudo_in_skeleton = saved
        shutil.rmtree(root, ignore_errors=True)


def test_nowork_is_screened_before_the_claim_not_after() -> None:
    """🔴 **claim 앞이어야 한다** — 그것이 ⓐ 와 ⓑ 를 가르는 전부다 (실측 2026-09-04 21:32).

    claim 뒤에 종결하면 `#318` 이 *"고지자 '(none)' 가 소유자 '192.168.0.2' 가 아니다"* 로
    409 를 낸다. 소유자가 있는 조각을 소유자 아닌 이름으로 끝낼 방법은 없고, 파견도 안 한
    조각을 워커 이름으로 제출하는 것은 사실도 아니다.
    """
    from master.work import decompose as DC
    paths, root = tmp_paths()
    saved = DC.pseudo_in_skeleton
    # 조각 둘 중 하나만 마커가 없다 — 걷힌 것과 파견된 것이 갈리는지 본다
    DC.pseudo_in_skeleton = lambda p, c, f: (0, "") if "Bar" in " ".join(f) else (3, "")
    calls: list = []
    try:
        q = FakeQueue([_t("t1", epoch=1),
                       _t("t2", epoch=1, target_file="Source/A/Bar.cpp",
                          header_file="Source/A/Bar.h")])
        _run(paths, q, runner_calls=calls)
        check("걷힌 것은 하나다", [t for t, _ in q.cancelled] == ["t2"], str(q.cancelled))
        check("[중요] 남은 조각은 정상 파견된다", len(calls) == 1, str(calls))
        check("🔴 **걷힌 조각은 워커에 건네지지 않는다** (claim 앞에서 걷었다)",
              q.handed == ["t1"], str(q.handed))
    finally:
        DC.pseudo_in_skeleton = saved
        shutil.rmtree(root, ignore_errors=True)


def test_prescreen_failure_does_not_block_dispatch() -> None:
    """[주의] **fail-open 이다** — 훑기가 죽어도 파견은 돈다. 조용히도 아니다(로그에 남는다)."""
    from master.work import decompose as DC
    paths, root = tmp_paths()
    saved = DC.pseudo_in_skeleton

    def boom(*a, **k):
        raise RuntimeError("골조 저장소를 못 읽었다")

    DC.pseudo_in_skeleton = boom
    calls: list = []
    try:
        q = FakeQueue([_t("t1", epoch=1)])
        _run(paths, q, runner_calls=calls)
        check("[중요] 계수가 터져도 파견한다", len(calls) == 1, str(calls))
        check("  걷어내지 않았다", not q.cancelled, str(q.cancelled))
    finally:
        DC.pseudo_in_skeleton = saved
        shutil.rmtree(root, ignore_errors=True)


def test_unreadable_skeleton_still_dispatches() -> None:
    """[주의] `-1` 은 「마커가 없다」가 아니라 **「못 셌다」**다 — 접으면 정상 조각이 안 나간다."""
    from master.work import decompose as DC
    paths, root = tmp_paths()
    saved = DC.pseudo_in_skeleton
    calls: list = []
    DC.pseudo_in_skeleton = lambda p, c, f: (-1, "골조를 못 읽었다")
    try:
        q = FakeQueue([_t("t1", epoch=1)])
        _run(paths, q, runner_calls=calls)
        check("[중요] 못 셌으면 파견한다", len(calls) == 1, str(calls))
    finally:
        DC.pseudo_in_skeleton = saved
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (
               test_no_target_list_is_blocked_not_passed,
               test_marker_and_file_must_both_hold,
               test_missing_file_is_not_partial_success,
               test_out_of_scope_path_blocks, test_fence_residue_blocks,
               test_blocked_reason_survives,
               test_marker_does_not_demand_branch_or_commit,
               test_markers_inside_the_response_file_are_stripped_and_reported,
               test_eof_newline_is_normalized_to_one,
               test_count_mismatch_is_warned_not_failed,
               test_infer_task_delivers_reads_and_judges,
               test_ssh_failure_does_not_pass_a_done,
               test_unreadable_response_is_not_absent,
               test_windows_response_path_uses_backslash,
               test_instruction_is_ascii_and_names_the_skill,
               test_spool_round_trip, test_failure_is_spooled_too,
               test_same_base_commit_is_reused_other_is_not,
               test_run_many_takes_several_and_orders_them,
               test_committed_piece_is_verified_so_the_requester_gets_told,
               test_piece_without_pseudo_is_not_dispatched_at_all,
               test_nowork_is_screened_before_the_claim_not_after,
               test_prescreen_failure_does_not_block_dispatch,
               test_unreadable_skeleton_still_dispatches,
               test_dependents_of_a_failure_are_not_dispatched,
               test_no_worker_means_no_claim,
               test_parallel_is_the_default, test_serial_only_when_asked,
               test_parallel_uses_both_workers, test_limit_is_respected,
               test_handoff_states_that_nobody_applies_yet,
               test_reuse_avoids_paying_twice):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_infer: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
