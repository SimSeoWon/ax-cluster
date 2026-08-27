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
    """`ProjectPaths` 대역 — 스풀만 쓴다."""
    root = Path(tempfile.mkdtemp(prefix="axinfer"))

    class P:
        name = "T"

        @property
        def responses(self):
            return root / "responses"
    return P(), root


# ── ② 대상 파일은 매니페스트에서 ────────────────────────────────────────────────

def test_target_files_come_from_the_manifest() -> None:
    got = I.target_files_from(MANIFEST)
    check("대상 파일 2개", got == WANT, str(got))
    # [중요] 다른 절의 백틱 낱말을 파일로 오인하면 판정 기준이 오염된다
    check("다른 절을 안 먹는다", "NotAFile.h" not in got, str(got))
    check("빈 매니페스트는 빈 목록", I.target_files_from("") == [])


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

    def writer(facts, rel, content, base="home"):
        delivered[rel] = content
        return rel

    def fake_runner(facts, task_id, timeout):
        return 0, json.dumps({"result": "RESPONSE: 2\nRESULT: DONE",
                              "total_cost_usd": 0.0123})

    def reader(facts, abs_path):
        check("응답을 체크아웃 안에서 읽는다", abs_path.startswith("/checkout"), abs_path)
        return GOOD_RESPONSE

    r = I.infer_task(f, "t1", MANIFEST, runner_=fake_runner, writer=writer, reader=reader)
    check("통과", r.ok, r.summary)
    check("매니페스트를 배달했다", any("t1" in k and "manifest" in k for k in delivered),
          str(list(delivered)))
    check("계측을 들고 온다", abs(r.cost_usd - 0.0123) < 1e-9, str(r.usage))
    check("워커를 기록한다", r.worker == "w1", r.worker)


def test_ssh_failure_does_not_pass_a_done() -> None:
    f = FakeFacts()

    def fake_runner(facts, task_id, timeout):
        return 1, "RESPONSE: 2\nRESULT: DONE"

    r = I.infer_task(f, "t1", MANIFEST, runner_=fake_runner,
                     writer=lambda *a, **k: "ok", reader=lambda *a: GOOD_RESPONSE)
    check("rc≠0 이면 DONE 을 접지 않는다", not r.ok, r.summary)
    check("rc 를 사유에 적는다", "rc=1" in r.reason, r.reason)


def test_unreadable_response_is_not_absent() -> None:
    """[중요] '못 읽었다' 를 '없다' 로 접으면 조용히 틀린다 (`_remote_read` 가 배운 것)."""
    from master.client import bundle
    f = FakeFacts()

    def boom(facts, abs_path):
        raise bundle.BundleError("scp 거부")

    r = I.infer_task(f, "t1", MANIFEST, runner_=lambda *a: (0, "RESULT: DONE"),
                     writer=lambda *a, **k: "ok", reader=boom)
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
        self.beats = 0

    def __call__(self, method, path, payload=None, *, timeout=20):
        if path.endswith("/claim"):
            return self.tasks.pop(0) if self.tasks else None
        if path.endswith("/heartbeat"):
            self.beats += 1
            return {"ok": True}
        if path.endswith("/submit-fail"):
            self.failed.append((path.split("/")[-2], (payload or {}).get("reason", "")))
            return {"ok": True}
        raise AssertionError(f"예상 밖 호출: {method} {path}")


def _run(paths, q, *, tasks_manifest=MANIFEST, response=GOOD_RESPONSE, workers=1,
         limit=4, parallel=False, stdout="RESULT: DONE"):
    facts = [FakeFacts(host=f"w{i+1}") for i in range(workers)]

    def fake_manifest(p, task_id):
        return tasks_manifest

    def fake_refresh(body, p, task_id, resolver=None):
        return body

    saved = (R._manifest_for, R.refresh_base)
    R._manifest_for, R.refresh_base = fake_manifest, fake_refresh
    try:
        return I.run_many(paths, limit=limit, facts=facts, api=q, clean=lambda f: Clean(),
                          parallel=parallel, work_id="W1",
                          runner_=lambda f, t, to: (0, stdout),
                          writer=lambda *a, **k: "ok", reader=lambda *a: response)
    finally:
        R._manifest_for, R.refresh_base = saved


def test_run_many_takes_several_and_orders_them() -> None:
    paths, root = tmp_paths()
    try:
        q = FakeQueue([{"task_id": "t1", "epoch": 1}, {"task_id": "t2", "epoch": 1}])
        hand = _run(paths, q)
        check("두 건을 파견했다", len(hand.items) == 2, str(hand.items))
        check("둘 다 통과", len(hand.ordered()) == 2, hand.summary())
        ids = [r.task_id for r in hand.ordered()]
        check("적용 순서는 파견 순서", ids == ["t1", "t2"], str(ids))
        check("큐가 비면 멈춘다", not q.tasks)
        check("제출하지 않는다 — 통합자의 일이다", not q.failed, str(q.failed))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dependents_of_a_failure_are_not_dispatched() -> None:
    """[중요] 큐는 `failed` 를 의존 해소로 센다(*영원 block 방지*) — 마스터가 막는다."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([{"task_id": "X.d1", "epoch": 1},
                       {"task_id": "X.d2", "epoch": 1, "depends_on": ["X.d1"]}])
        # 응답을 비워 첫 건을 실패시킨다
        hand = _run(paths, q, response="")
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
        q = FakeQueue([{"task_id": "t1"}])
        facts = [FakeFacts(host="r1", role="requester")]
        hand = I.run_many(paths, facts=facts, api=q, clean=lambda f: Clean(),
                          work_id="W1", runner_=lambda *a: (0, "RESULT: DONE"),
                          writer=lambda *a, **k: "ok", reader=lambda *a: GOOD_RESPONSE)
        check("파견 0건", not hand.items, str(hand.items))
        check("태스크가 큐에 남아 있다", len(q.tasks) == 1, str(q.tasks))
        check("왜 못 했는지 말한다", "워커가 없어" in hand.note, hand.note)
        check("요청자를 제외한 사유를 적는다", "requester" in hand.note, hand.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_serial_is_the_default_and_says_so() -> None:
    """[중요] 병렬은 기본값이 아니다 (실측: 12% 빠르고 90% 비쌌다)."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([{"task_id": "t1"}, {"task_id": "t2"}])
        hand = _run(paths, q, workers=2)
        check("직렬임을 말한다", "직렬" in hand.note, hand.note)
        check("실측 근거를 적는다", "90%" in hand.note, hand.note)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_parallel_uses_both_workers() -> None:
    paths, root = tmp_paths()
    try:
        q = FakeQueue([{"task_id": "t1"}, {"task_id": "t2"}])
        hand = _run(paths, q, workers=2, parallel=True)
        used = {r.worker for _, r in hand.items}
        check("두 워커가 다 일했다", used == {"w1", "w2"}, str(used))
        check("둘 다 통과", len(hand.ordered()) == 2, hand.summary())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_limit_is_respected() -> None:
    paths, root = tmp_paths()
    try:
        q = FakeQueue([{"task_id": f"t{i}"} for i in range(5)])
        hand = _run(paths, q, limit=2)
        check("상한을 지킨다", len(hand.items) == 2, str(len(hand.items)))
        check("나머지는 큐에 남는다", len(q.tasks) == 3, str(len(q.tasks)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_handoff_states_that_nobody_applies_yet() -> None:
    """[주의] 없는 것을 있는 척하지 않는다 — 통합자(중 1.4)는 아직 비어 있다."""
    paths, root = tmp_paths()
    try:
        q = FakeQueue([{"task_id": "t1"}])
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

        q = FakeQueue([{"task_id": "t1"}])
        facts = [FakeFacts()]

        class FakeBase:
            commit = "abc1234"

        import master.work.twin_base as tb
        saved = (R._manifest_for, R.refresh_base, tb.resolve)
        R._manifest_for = lambda p, t: MANIFEST
        R.refresh_base = lambda b, p, t, resolver=None: b
        tb.resolve = lambda p, t: FakeBase()
        try:
            hand = I.run_many(paths, facts=facts, api=q, clean=lambda f: Clean(),
                              work_id="W1", runner_=counting_runner,
                              writer=lambda *a, **k: "ok", reader=lambda *a: GOOD_RESPONSE)
        finally:
            R._manifest_for, R.refresh_base, tb.resolve = saved
        check("워커를 부르지 않았다", not calls, str(calls))
        check("그래도 인계에 들어간다", len(hand.ordered()) == 1, hand.summary())
        check("재사용 표시가 보인다", hand.ordered()[0].reused, hand.ordered()[0].summary)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (test_target_files_come_from_the_manifest,
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
               test_dependents_of_a_failure_are_not_dispatched,
               test_no_worker_means_no_claim,
               test_serial_is_the_default_and_says_so,
               test_parallel_uses_both_workers, test_limit_is_respected,
               test_handoff_states_that_nobody_applies_yet,
               test_reuse_avoids_paying_twice):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_infer: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
