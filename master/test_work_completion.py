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
import work_completion as W
import pending_works as P


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


class CliWaitTests(unittest.TestCase):
    """`#799` — 훅이 없을 때(Codex)·2시간을 넘길 때 대기하는 쪽이 큐를 직접 본다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ax-cliwait-")
        self.root = Path(self.temp.name)
        self.now = [0.0]

    def tearDown(self):
        self.temp.cleanup()

    def clock(self):
        return self.now[0]

    def sleep(self, s):
        self.sleep_calls.append(s)
        self.now[0] += s

    def detail(self, status="in_progress", round_no=1, task_status="claimed"):
        return {"work": {"work_id": "W", "round": round_no, "merge_status": status,
                         "title": "제목"},
                "tasks": [{"task_id": "T1", "round": round_no, "status": task_status,
                           "last_feedback": "빌드 오류"},
                          {"task_id": "OLD", "round": round_no - 1, "status": "failed"}]}

    def run_wait(self, states, **kw):
        self.sleep_calls = []
        seq = iter(states)
        calls = []
        def get(wid):
            calls.append(wid)
            got = next(seq)
            if isinstance(got, Exception):
                raise got
            return got
        err = io.StringIO()
        code, text = W.cli_wait(self.root, "W", get, clock=self.clock, sleep=self.sleep,
                                err=err, **kw)
        return code, text, err.getvalue().splitlines(), calls

    def test_ready_exits_zero_with_facts_and_poll_lines(self):
        code, text, lines, calls = self.run_wait(
            [self.detail(), self.detail(), self.detail("ready_for_review", task_status="verified")],
            round_no=1)
        self.assertEqual(code, 0)
        self.assertIn("[분산 작업 결과] W · 라운드 1 · ready_for_review", text)
        self.assertEqual(len(lines), 3)                      # 조회마다 한 줄
        self.assertTrue(all(x.startswith("[wait] W r1 · 큐 ") and " · 남은 " in x for x in lines))
        self.assertIn("조각 claimed 1", lines[0])            # 지난 라운드 조각은 안 센다
        self.assertEqual(self.sleep_calls, [60, 60])        # 기본 1분 간격
        for imperative in ("하세요", "하라", "말고", "묻지"):
            self.assertNotIn(imperative, text)

    def test_default_interval_is_one_minute(self):
        self.assertEqual(W.CLI_INTERVAL, 60)
        self.assertGreaterEqual(W.CLI_TIMEOUT, 86400)

    def test_timeout_exits_four_and_is_not_completion(self):
        code, text, lines, calls = self.run_wait([self.detail()] * 10, round_no=1,
                                                 timeout=150, interval=60)
        self.assertEqual(code, 4)
        self.assertIn("완료로 처리하지 않았습니다", text)
        self.assertIn("in_progress", text)
        self.assertEqual(len(calls), 4)                      # 0·60·120·150(상한 시각)
        self.assertEqual(self.sleep_calls, [60, 60, 30])

    def test_query_error_is_logged_and_retried(self):
        code, text, lines, _ = self.run_wait(
            [OSError("offline"), self.detail("ready_for_review", task_status="verified")],
            round_no=1)
        self.assertEqual(code, 0)
        self.assertIn("조회 오류 OSError: offline", lines[0])
        code, text, lines, _ = self.run_wait([OSError("offline")] * 3, round_no=1,
                                             timeout=100, interval=60)
        self.assertEqual(code, 4)
        self.assertIn("마지막 조회 오류: OSError: offline", text)

    def test_current_round_lookup_when_round_omitted(self):
        code, text, lines, _ = self.run_wait(
            [self.detail(round_no=3), self.detail("ready_for_review", 3, "verified")])
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("[wait] W r3 · "))
        self.assertIn("라운드 3", text)

    def test_invalid_initial_round_is_retried_without_fixing_round(self):
        for invalid in (None, 0, -1, "invalid"):
            with self.subTest(round=invalid):
                self.now[0] = 0
                bad = self.detail()
                if invalid is None:
                    del bad["work"]["round"]
                else:
                    bad["work"]["round"] = invalid
                code, text, lines, calls = self.run_wait(
                    [bad, self.detail("ready_for_review", 3, "verified")])
                self.assertEqual(code, 0)
                self.assertIn("라운드 3", text)
                self.assertIn("r? · 조회 오류", lines[0])
                self.assertTrue(lines[1].startswith("[wait] W r3 · "))
                self.assertEqual(calls, ["W", "W"])
                self.assertEqual(self.sleep_calls, [60])

    def test_invalid_round_until_timeout_does_not_become_mismatch(self):
        for invalid in (None, 0, -1, "invalid"):
            with self.subTest(round=invalid):
                self.now[0] = 0
                bad = self.detail()
                if invalid is None:
                    del bad["work"]["round"]
                else:
                    bad["work"]["round"] = invalid
                code, text, lines, calls = self.run_wait(
                    [bad] * 3, timeout=100, interval=60)
                self.assertEqual(code, 4)
                self.assertIn("라운드 ?", text)
                self.assertIn("마지막 조회 오류", text)
                self.assertTrue(all("r? · 조회 오류" in line for line in lines))
                self.assertEqual(calls, ["W"] * 3)
                self.assertEqual(self.sleep_calls, [60, 40])

    def test_first_valid_round_stays_fixed_when_round_omitted(self):
        code, text, _, calls = self.run_wait(
            [self.detail(round_no=3), self.detail("ready_for_review", 4, "verified")])
        self.assertEqual(code, 3)
        self.assertIn("요청 라운드 3", text)
        self.assertIn("큐 라운드 4", text)
        self.assertEqual(calls, ["W", "W"])

    def test_round_mismatch_is_not_completion(self):
        code, text, _, _ = self.run_wait([self.detail("ready_for_review", round_no=2)], round_no=1)
        self.assertEqual(code, 3)
        self.assertIn("완료로 처리하지 않았습니다", text)

    def test_other_terminal_and_failure_exit_three(self):
        for status in ("merged", "cancelled", "rejected"):
            code, text, _, _ = self.run_wait([self.detail(status)], round_no=1)
            self.assertEqual(code, 3, status)
            self.assertIn(status, text)
        code, text, _, _ = self.run_wait([self.detail(task_status="failed")], round_no=1)
        self.assertEqual(code, 3)
        self.assertIn("빌드 오류", text)
        # --skip-failures 는 실패를 찍고 종결까지 기다린다
        code, text, lines, _ = self.run_wait(
            [self.detail(task_status="failed"), self.detail("ready_for_review", task_status="verified")],
            round_no=1, skip_failures=True)
        self.assertEqual(code, 0)
        self.assertTrue(any("실패 조각 1건" in x for x in lines))

    def test_read_only_and_independent_of_hook_dedupe(self):
        """큐에 쓰지 않고, 훅의 고지·잠금 파일을 쓰지도 읽지도 않는다 — 신호를 서로 안 지운다."""
        ready = self.detail("ready_for_review", task_status="verified")
        # 훅이 같은 work·라운드를 이미 고지한 뒤에도 CLI 는 결과를 낸다
        W.wait_for_work(self.root, "S", "W", 1, lambda _: ready)
        before = sorted(p.name for p in (self.root / ".ax/work-notices").iterdir())
        code, text, _, _ = self.run_wait([ready], round_no=1)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in (self.root / ".ax/work-notices").iterdir()), before)
        # CLI 가 먼저 돌아도 훅의 고지는 억제되지 않는다
        other = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.root, saved = other, self.root
        self.run_wait([ready], round_no=1)
        self.assertFalse((other / ".ax/work-notices").exists())
        self.assertIn("ready_for_review", W.wait_for_work(other, "S", "W", 1, lambda _: ready))
        events = [json.loads(x) for x in (other / ".ax/work_completion.jsonl").read_text().splitlines()]
        self.assertEqual({e["session"] for e in events if e["event"].startswith("cli_")}, {"cli-wait"})
        self.root = saved

    def test_log_write_failure_does_not_stop_wait(self):
        (self.root / ".ax").write_text("not a dir")          # .ax 쓰기가 실패하는 자리
        code, _, _, _ = self.run_wait([self.detail("ready_for_review", task_status="verified")],
                                      round_no=1)
        self.assertEqual(code, 0)

    def test_cli_main_uses_hook_client_and_exit_codes(self):
        got_api = []
        class Client:
            HTTP_TIMEOUT = 0
            def queue_api(self, cwd):
                got_api.append(cwd)
                return "API"
            def tool_get_work(self, api, wid):
                assert api == "API" and wid == "W"
                return {"work": {"work_id": "W", "round": 2, "merge_status": "ready_for_review"},
                        "tasks": []}
        old_load = P._load_client
        P._load_client = lambda _: Client()
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out, \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                code = W.cli_main(["--wait", "W", "--root", str(self.root)])
            self.assertEqual(code, 0)
            self.assertIn("ready_for_review", out.getvalue())
            self.assertIn("[wait] W r2", err.getvalue())
            self.assertEqual(got_api, [self.root])
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(W.cli_main(["--wait", "W", "--interval", "0",
                                             "--root", str(self.root)]), 2)
                self.assertEqual(W.cli_main(["--round", "1"]), 2)   # --wait 없음
        finally:
            P._load_client = old_load

    def test_cli_main_setup_failure_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(W.cli_main(["--wait", "W", "--root", str(self.root)]), 2)
        self.assertIn("연결 준비 실패", err.getvalue())

    def test_script_without_args_stays_hook_mode(self):
        """인자 없이 불리면 종전 훅 경로(stdin) 그대로다 — 등록 명령은 인자를 싣지 않는다."""
        import subprocess
        script = Path(W.__file__)
        r = subprocess.run([sys.executable, "-B", str(script)], input=json.dumps(
            {"cwd": str(self.root), "session_id": "S", "tool_name": "Bash",
             "tool_response": {"ok": False}}), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        events = [json.loads(x)["event"] for x in
                  (self.root / ".ax/work_completion.jsonl").read_text().splitlines()]
        self.assertEqual(events, ["not_a_registration"])


if __name__ == "__main__":
    unittest.main()
