"""Completion signals: MCP envelope, terminal states, deduplication and error visibility."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "client/workshop/hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import work_completion as W
import pending_works as P
from master.work import followup as F

IMPERATIVES = ("하세요", "하라", "해 주세요", "해주세요", "말고", "보고한다", "묻지", "넘겨라")


class Prep:
    """`prepare_round` 대역 — 부른 횟수를 센다. 실제 잠금·기록·렌더는 진짜 `followup` 이 한다."""

    def __init__(self, state="at_gate"):
        self.calls, self.state = 0, state

    def __call__(self, repo, work_id, **kw):
        self.calls += 1
        return F.Followup(work_id=work_id, state=self.state, round=kw.get("expect_round") or 1,
                          merge_status="ready_for_review", project="AXCluster", title="제목",
                          redmine_issue_id=55, kind="code", tree=f"/x/ax-advance-{work_id}",
                          target_branch=f"task/{work_id}/base", before="a" * 40, head="b" * 40,
                          merged=[f"task/{work_id}/r1/p1"], build_passed=True,
                          build_note="통합 TESTS OK (3) · 회귀 1/1",
                          question=F.R.Advance(build_passed=True).question,
                          checks={"passed": 2, "failed": 0, "items": [
                              {"name": "통합 검사", "ok": True, "summary": "TESTS OK (3)"},
                              {"name": "회귀 master/test_x.py", "ok": True, "summary": "ok"}]},
                          reason="fake")


class FollowupStub:
    """배달된 `axmaster.work.followup` 자리 — 진짜 모듈에 상태 디렉토리·대역만 꽂는다."""

    def __init__(self, sd, prep, notes=None):
        self.sd, self.prep, self.notes = sd, prep, notes if notes is not None else []
        self.render = F.render

    def _note(self, api, **kw):
        self.notes.append(kw)
        return {"ok": True}

    def prepare_once(self, repo, wid, rnd, **kw):
        return F.prepare_once(repo, wid, rnd, state=self.sd, prepare=self.prep,
                              note=self._note, **kw)

    def recorded_for(self, repo, wid, rnd=None):
        return F.recorded_for(repo, wid, rnd, state=self.sd)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ax-completion-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def detail(self, status="ready_for_review", failed=False, round_no=1):
        return {"work": {"work_id": "W", "round": round_no, "merge_status": status},
                "tasks": [{"round": round_no, "status": "failed" if failed else "verified",
                           "last_feedback": "OAuth expired"}]}

    def test_actual_mcp_envelope(self):
        payload = {"ok": True, "work_id": "W", "round": 1}
        for v in (payload, {"content": [{"type": "text", "text": json.dumps(payload)}]},
                  [{"type": "text", "text": json.dumps(payload)}]):
            self.assertEqual(W.result_object(v), payload)
        self.assertFalse(W.result_object({"isError": True, "content": [payload]}))
        self.assertFalse(W.result_object("not JSON"))

    def test_completion_after_wait_and_duplicate(self):
        states = iter([self.detail("in_progress"), self.detail()])
        msg = W.wait_for_work(self.root, "S", "W", 1, lambda _: next(states), sleep=lambda _: None)
        self.assertIn("ready_for_review", msg)
        self.assertEqual(W.wait_for_work(self.root, "S", "W", 1,
                                         lambda _: self.fail("duplicate queried server")), "")
        events = [json.loads(x)["event"] for x in
                  (self.root / ".ax/work_completion.jsonl").read_text().splitlines()]
        # [중요] 중복 호출도 **한 줄 남긴다** — 조용히 넘기면 「안 돌았다」와 구분이 안 된다
        self.assertEqual(events, ["watch_started", "state_observed", "state_observed",
                                  "signal_emitted", "already_noticed"])

    def test_failed_piece_is_in_signal(self):
        msg = W.wait_for_work(self.root, "S", "W", 1, lambda _: self.detail(failed=True))
        self.assertIn("OAuth expired", msg)

    def test_rejected_round_emits_terminal_notice(self):
        msg = W.wait_for_work(self.root, "S", "W", 1,
                              lambda _: self.detail("rejected", failed=True))
        self.assertIn("rejected", msg)
        self.assertIn("통합·전진 대기 대상이 아닙니다", msg)
        self.assertTrue(W.already_noticed(self.root, "S", "W", 1))

    def test_notification_failure_is_visible_without_cancelling_success(self):
        detail = self.detail()
        detail["work"].update(notification_error="Redmine unavailable", termination_required=True)
        msg = W.wait_for_work(self.root, "S", "W", 1, lambda _: detail)
        self.assertIn("ready_for_review", msg)
        self.assertIn("Redmine unavailable", msg)
        self.assertIn("사람 판단", msg)
        self.assertIn("Redmine unavailable", P._line(detail["work"], detail))

    def test_failure_before_round_completion_uses_queue_fields(self):
        detail = self.detail("in_progress", failed=True)
        detail["tasks"] = [
            {"task_id": "broken", "round": 1, "status": "failed",
             "fail_reason": "BLOCKED", "fail_detail": "Access denied reading SKILL.md"},
            {"task_id": "busy", "round": 1, "status": "claimed"},
        ]
        msg = W.wait_for_work(self.root, "S", "W", 1, lambda _: detail)
        self.assertIn("Access denied reading SKILL.md", msg)
        self.assertIn("in_progress", msg)
        self.assertFalse(W.already_noticed(self.root, "S", "W", 1))
        self.assertEqual(W.pending_failure_watch(self.root, "S")["work_id"], "W")
        self.assertFalse(W.pending_failure_watch(self.root, "other"))
        self.assertIn("Access denied reading SKILL.md", P._line(detail["work"], detail))

    def test_revision_signal_does_not_suppress_completion(self):
        revision = self.detail("in_progress")
        revision["tasks"][0].update(status="needs_revision", attempt_count=1)
        first = W.wait_for_work(self.root, "S", "W", 1, lambda _: revision)
        self.assertIn("실패 후 재시도 대기", first)
        self.assertIn("OAuth expired", first)
        states = iter([revision, self.detail()])
        final = W.wait_for_work(self.root, "S", "W", 1, lambda _: next(states), sleep=lambda _: None)
        self.assertIn("ready_for_review", final)
        self.assertTrue(W.already_noticed(self.root, "S", "W", 1))
        self.assertFalse(W.pending_failure_watch(self.root, "S"))

    def test_next_tool_call_resumes_after_failure(self):
        detail = self.detail("in_progress", failed=True)
        W.wait_for_work(self.root, "S", "W", 1, lambda _: detail)
        class Client:
            HTTP_TIMEOUT = 0
            def queue_api(self, cwd):
                return None
            def tool_get_work(self, api, wid):
                return self_detail
        self_detail = self.detail()
        old_load, old_stdin = P._load_client, sys.stdin
        P._load_client = lambda _: Client()
        sys.stdin = io.StringIO(json.dumps({"cwd": str(self.root), "session_id": "S",
                                            "tool_name": "Bash", "tool_response": "reading status"}))
        try:
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(W.main(), 2)
            self.assertIn("ready_for_review", output.getvalue())
        finally:
            P._load_client, sys.stdin = old_load, old_stdin

    def test_every_invocation_leaves_a_line(self):
        """🔴 **침묵을 만들지 않는다** — 「훅이 안 붙었다」와 「이 호출은 대상이 아니었다」가
        로그에서 갈려야 한다. 파견 트리거가 그 침묵으로 이틀을 태웠다(2026-08-29~31).
        """
        base = {"cwd": str(self.root), "session_id": "S", "tool_name": "Bash"}
        def run(resp):
            sys.stdin = io.StringIO(json.dumps({**base, "tool_response": resp}))
            try:
                return W.main()
            finally:
                sys.stdin = sys.__stdin__
        self.assertEqual(run({"ok": False}), 0)                     # 등록이 아니다
        self.assertEqual(run({"ok": True, "work_id": "W"}), 0)      # round 가 없다
        events = [json.loads(x)["event"] for x in
                  (self.root / ".ax/work_completion.jsonl").read_text().splitlines()]
        self.assertEqual(events, ["not_a_registration", "bad_round"])

    def test_lock_and_duplicate_are_logged_not_silent(self):
        W.wait_for_work(self.root, "S", "W", 1, lambda _: self.detail())
        W.wait_for_work(self.root, "S", "W", 1, lambda _: self.fail("서버를 또 물었다"))
        events = [json.loads(x)["event"] for x in
                  (self.root / ".ax/work_completion.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1], "already_noticed")

    def test_signal_carries_facts_only(self):
        """🔴 명령형을 실으면 깨어난 세션이 **주입으로 거부한다** (실측 2026-09-10, 리포트 60).

        [중요] 이 못은 문구가 다시 명령형으로 돌아가는 것을 막는다. 「그래서 무엇을 하나」는
        `ax-request` 스킬의 자리이고, 훅은 **사실만** 싣는다.
        """
        for failed in (False, True):
            msg = W.wait_for_work(self.root, f"S{failed}", "W", 1,
                                  lambda _: self.detail(failed=failed))
            for imperative in ("하세요", "하라", "말고", "보고한다", "묻지"):
                self.assertNotIn(imperative, msg, f"명령형이 실렸다: {imperative!r} in {msg!r}")
            self.assertIn("W", msg)
            self.assertIn("ready_for_review", msg)

    def test_other_session_receives_its_own_signal(self):
        for session in ("S1", "S2"):
            self.assertTrue(W.wait_for_work(self.root, session, "W", 1, lambda _: self.detail()))

    def test_wrong_round_is_not_completion(self):
        with self.assertRaises(RuntimeError):
            W.wait_for_work(self.root, "S", "W", 1, lambda _: self.detail(round_no=2))
        self.assertFalse(W.already_noticed(self.root, "S", "W", 1))

    def test_timeout_and_network_error_are_not_completion(self):
        with self.assertRaises(TimeoutError):
            W.wait_for_work(self.root, "S", "W", 1, lambda _: self.detail(), timeout=0)
        def bad(_):
            raise OSError("offline")
        with self.assertRaises(OSError):
            W.wait_for_work(self.root, "S", "W", 1, bad)
        self.assertFalse(W.already_noticed(self.root, "S", "W", 1))

    def test_pending_notice_survives_the_async_path(self):
        """🔴 [중요] **`pending_works` 의 매 턴 고지를 이 훅이 대체하지 않는다.**

        새 경로(asyncRewake)는 격리 실측만 통과했고 **라이브에서 한 번도 안 돌았다.** 그래서
        두 겹을 함께 둔다 — 종전 안전망을 미실측 경로와 맞바꾸지 않는다. 이 못은 「완료 훅을
        만들었으니 세션 시작 고지는 접어도 된다」로 다시 미끄러지는 것을 막는다.
        """
        detail = self.detail()
        class Client:
            def queue_api(self, cwd):
                return lambda *args: {}
            def tool_list_works(self, api):
                return {"works": [detail["work"]]}
            def tool_get_work(self, api, wid):
                return detail
        old_load, old_editor, old_stdin = P._load_client, P._editor_notice, sys.stdin
        P._load_client, P._editor_notice = lambda _: Client(), lambda _: None
        try:
            def run(session):
                sys.stdin = io.StringIO(json.dumps({"cwd": str(self.root), "session_id": session}))
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    P.main()
                return out.getvalue()
            first = run("S")
            self.assertIn("ax-advance", first)      # ⑺ 절차가 살아 있다
            self.assertEqual(run("S"), first)       # 매 턴 반복한다 — 억제하지 않는다
            # 완료 훅이 신호를 낸 뒤에도 세션 시작 고지는 그대로다
            W.wait_for_work(self.root, "S2", "W", 1, lambda _: detail)
            self.assertEqual(run("S2"), first)
        finally:
            P._load_client, P._editor_notice, sys.stdin = old_load, old_editor, old_stdin


class FollowupHookTests(unittest.TestCase):
    """`#798` ⓒ — terminal 을 본 훅이 같은 `prepare_once` 를 부르고 그 사실을 고지에 싣는다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ax-fu-hook-")
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.sd = Path(self.temp.name) / "state"

    def tearDown(self):
        self.temp.cleanup()

    def detail(self, status="ready_for_review", failed=False):
        return {"work": {"work_id": "W", "round": 1, "merge_status": status,
                         "redmine_issue_id": 55},
                "tasks": [{"round": 1, "status": "failed" if failed else "verified",
                           "task_id": "p1", "last_feedback": "x"}]}

    def events(self):
        return [json.loads(x)["event"] for x in
                (self.root / ".ax/work_completion.jsonl").read_text().splitlines()]

    def run_hook(self, stub, detail=None, budget=7200, **kw):
        detail = detail or self.detail()
        on_t = lambda work, left: W.prepare_followup(self.root, "S", work, 1, None, stub,
                                                     budget=min(budget, left), **kw)
        return W.wait_for_work(self.root, "S", "W", 1, lambda _: detail, on_terminal=on_t)

    def test_terminal_prepares_and_message_has_facts(self):
        prep = Prep()
        stub = FollowupStub(self.sd, prep)
        msg = self.run_hook(stub)
        self.assertEqual(prep.calls, 1)
        for want in ("[분산 작업 결과] W", "[⑦ 준비 결과] W", "at_gate", "승인 대기",
                     "/x/ax-advance-W", "bbbbbbbbbbbb", "항목 통과 2", "실패 0",
                     "게이트 물음(원문 인용)", "Redmine #55", "완료 훅"):
            self.assertIn(want, msg)
        for bad in IMPERATIVES:
            self.assertNotIn(bad, msg)
        ev = self.events()
        self.assertIn("prepare_started", ev)
        self.assertIn("prepare_done", ev)
        self.assertIn("followup_line", ev)
        self.assertEqual(ev[-1], "signal_emitted")
        self.assertEqual(len(stub.notes), 1)               # ⓐ 노트도 한 번

    def test_already_prepared_by_timer_is_reused_not_rerun(self):
        prep = Prep()
        F.prepare_once(self.root, "W", 1, state=self.sd, prepare=prep, origin="timer",
                       note=lambda api, **kw: {"ok": True})
        msg = self.run_hook(FollowupStub(self.sd, prep))
        self.assertEqual(prep.calls, 1)                    # 다시 돌리지 않았다
        self.assertIn("[⑦ 준비 결과] W", msg)
        self.assertIn("타이머(scan)", msg)
        self.assertIn("prepare_reused", self.events())

    def test_lock_held_waits_for_record_and_reports_it(self):
        prep = Prep()
        lock = F.round_key_path(self.sd, self.root, "W", 1).with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("timer pid=1")                     # 타이머가 지금 준비 중
        def timer_finishes(_):
            # 대기 중 타이머가 끝나 기록을 남긴다
            lock.unlink(missing_ok=True)
            F.prepare_once(self.root, "W", 1, state=self.sd, prepare=prep, origin="timer")
        on_t = lambda work, left: W.prepare_followup(self.root, "S", work, 1, None,
                                                     FollowupStub(self.sd, prep), budget=7200,
                                                     sleep=timer_finishes)
        msg = W.wait_for_work(self.root, "S", "W", 1, lambda _: self.detail(), on_terminal=on_t)
        self.assertEqual(prep.calls, 1)                    # 훅은 돌리지 않았다
        self.assertIn("[⑦ 준비 결과] W", msg)
        self.assertIn("타이머(scan)", msg)
        ev = self.events()
        self.assertIn("prepare_waiting", ev)
        self.assertIn("prepare_reused", ev)

    def test_lock_held_until_budget_ends_is_reported_as_fact(self):
        lock = F.round_key_path(self.sd, self.root, "W", 1).with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("timer pid=1")
        t = [0.0]
        def clock():
            return t[0]
        def sleep(_):
            t[0] += 1000
            lock.touch()
        out = W.prepare_followup(self.root, "S", self.detail()["work"], 1, None,
                                 FollowupStub(self.sd, Prep()), budget=2000, sleep=sleep,
                                 clock=clock)
        self.assertIn("준비 결과 기록 없음", out)
        self.assertIn("prepare_pending", self.events())

    def test_short_budget_defers_to_timer(self):
        prep = Prep()
        msg = self.run_hook(FollowupStub(self.sd, prep), budget=10)
        self.assertEqual(prep.calls, 0)
        self.assertIn("타이머(scan) 대상", msg)
        self.assertIn("prepare_deferred", self.events())

    def test_prepare_error_keeps_completion_notice(self):
        class Broken(FollowupStub):
            def prepare_once(self, *a, **k):
                raise OSError("disk full")
        msg = self.run_hook(Broken(self.sd, Prep()))
        self.assertIn("ready_for_review", msg)
        self.assertIn("[⑦ 준비 오류] W", msg)
        self.assertIn("disk full", msg)
        self.assertIn("prepare_error", self.events())
        self.assertTrue(W.already_noticed(self.root, "S", "W", 1))
        # on_terminal 자체가 터져도 같다
        msg2 = W.wait_for_work(self.root, "S2", "W", 1, lambda _: self.detail(),
                               on_terminal=lambda w, b: 1 / 0)
        self.assertIn("ready_for_review", msg2)
        self.assertIn("ZeroDivisionError", msg2)

    def test_failure_wake_and_merged_do_not_prepare(self):
        prep = Prep()
        stub = FollowupStub(self.sd, prep)
        self.run_hook(stub, detail=self.detail("in_progress", failed=True))
        self.assertEqual(prep.calls, 0)                    # 실패 깨우기는 terminal 이 아니다
        out = W.prepare_followup(self.root, "S", {"work_id": "W", "merge_status": "merged"}, 1,
                                 None, stub, budget=7200)
        self.assertEqual((out, prep.calls), ("", 0))

    def test_rejected_round_records_stopped(self):
        prep = Prep(state="stopped")
        msg = self.run_hook(FollowupStub(self.sd, prep), detail=self.detail("rejected"))
        self.assertIn("상태 stopped", msg)
        self.assertEqual(prep.calls, 1)

    def test_main_end_to_end_wakes_with_prepared_facts(self):
        prep = Prep()
        detail = self.detail()
        class Client:
            HTTP_TIMEOUT = 0
            def queue_api(self, cwd):
                return None
            def tool_get_work(self, api, wid):
                return detail
        old = P._load_client, W._load_followup, sys.stdin
        P._load_client = lambda _: Client()
        W._load_followup = lambda _: FollowupStub(self.sd, prep)
        sys.stdin = io.StringIO(json.dumps({
            "cwd": str(self.root), "session_id": "S", "tool_name": "mcp__ax-client__register_work",
            "tool_response": {"ok": True, "work_id": "W", "round": 1}}))
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(W.main(), 2)
        finally:
            P._load_client, W._load_followup, sys.stdin = old
        self.assertIn("[⑦ 준비 결과] W", err.getvalue())
        self.assertEqual(prep.calls, 1)
        self.assertEqual(self.events()[-1], "exit")

    def test_pending_works_shows_timer_prepared_round(self):
        """ⓑ 세션 시작·매 턴 고지가 타이머가 준비한 결과를 사실로 싣는다."""
        F.prepare_once(self.root, "W", 1, state=self.sd, prepare=Prep(), origin="timer",
                       note=lambda api, **kw: {"ok": True})
        detail = self.detail()
        detail["work"]["title"] = "제목"
        class Client:
            def queue_api(self, cwd):
                return lambda *args: {}
            def tool_list_works(self, api):
                return {"works": [detail["work"]]}
            def tool_get_work(self, api, wid):
                return detail
        old = P._load_client, P._editor_notice, P._load_followup, sys.stdin
        P._load_client, P._editor_notice = lambda _: Client(), lambda _: None
        P._load_followup = lambda: FollowupStub(self.sd, Prep())
        try:
            sys.stdin = io.StringIO(json.dumps({"cwd": str(self.root), "session_id": "S"}))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                P.main()
            text = out.getvalue()
            for want in ("[⑦ 준비 결과] W", "승인 대기", "/x/ax-advance-W", "타이머(scan)",
                         "Redmine 노트: 기재됨", "게이트 물음(원문 인용)"):
                self.assertIn(want, text)
            block = P._followup_block(self.root, detail["work"], detail)
            for bad in IMPERATIVES:
                self.assertNotIn(bad, block)
            # 기록이 없는 work 는 「없음」을 사실로 말한다
            none = P._followup_block(self.root, {"work_id": "Z"}, {"work": {"round": 1}})
            self.assertIn("준비 기록 없음", none)
            P._load_followup = lambda: (_ for _ in ()).throw(ImportError("no axmaster"))
            self.assertIn("조회 불가", P._followup_block(self.root, detail["work"], detail))
        finally:
            P._load_client, P._editor_notice, P._load_followup, sys.stdin = old


if __name__ == "__main__":
    unittest.main()
