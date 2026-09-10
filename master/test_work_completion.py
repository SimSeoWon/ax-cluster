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


if __name__ == "__main__":
    unittest.main()
