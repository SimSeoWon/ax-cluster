"""Verify explicit modes survive requester → HTTP route → reopen payload."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client.runtime import client_mcp as C
from master.projects import register_route as HTTP
from master.work import register as R


class TransportTests(unittest.TestCase):
    def test_requester_sends_mode_on_both_calls(self):
        for fn, extra in ((C.tool_register_work, {"title": "x"}),
                          (C.tool_improve_work, {"work_id": "W", "round": 2})):
            with patch.object(C, "projects_write_api") as api:
                fn(None, dict(extra, specs=[{"stem": "X"}], worker_mode="codex"))
                self.assertEqual(api.return_value.call_args.args[2]["worker_mode"], "codex")

    def test_http_route_forwards_mode(self):
        result = SimpleNamespace(ok=True, work_id="W", round=2, tasks=[], summary=lambda: "ok")
        with patch("master.context_search.paths.resolve"), patch.object(R, "improve_work", return_value=result) as fn:
            got = HTTP._run({"project": "NS", "work_id": "W", "round": 2,
                             "worker_mode": "claude", "specs": [{"stem": "X"}]}, improve=True)
            self.assertTrue(got["ok"])
            self.assertEqual(fn.call_args.kwargs["worker_mode"], "claude")

    def test_reopen_request_carries_mode(self):
        sent = []
        def post(url, body):
            sent.append((url, body))
            return {"ok": True, "round": 2}
        with patch.object(R, "_prepare_specs", return_value={}), patch.object(
                R, "_register_after_create", return_value=SimpleNamespace(round=0)):
            R.improve_work("W", [R.TaskSpec(stem="X")], round=2, worker_mode="codex",
                           paths=SimpleNamespace(name="NS"), poster=post)
        self.assertTrue(sent[0][0].endswith("/reopen"))
        self.assertEqual(sent[0][1]["worker_mode"], "codex")


class WaitFieldTests(unittest.TestCase):
    """`#799` — 등재·개선요청 성공 응답에 이 체크아웃의 대기 명령이 실린다."""

    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory(prefix="ax-waitfield-")
        self.root = Path(self.temp.name)
        (self.root / ".claude/hooks").mkdir(parents=True)
        (self.root / ".claude/hooks/work_completion.py").write_text("", encoding="utf-8")
        (self.root / ".ax").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def config(self, python, os_name="windows"):
        import json
        (self.root / ".ax/config.json").write_text(json.dumps(
            {"backends": {"python": python}, "this_host": {"os": os_name}}), encoding="utf-8")

    def call(self, fn, extra, reply):
        with patch.object(C, "projects_write_api") as api:
            api.return_value.return_value = reply
            return fn(None, dict(extra, specs=[{"stem": "X"}]), root=self.root)

    def test_register_and_improve_carry_wait(self):
        self.config(r"C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe")
        got = self.call(C.tool_register_work, {"title": "x"}, {"ok": True, "work_id": "W1", "round": 1})
        py = "C:/Users/USER/AppData/Local/Programs/Python/Python312/python.exe"
        self.assertEqual(got["wait"], f"{py} .claude/hooks/work_completion.py --wait W1 --round 1")
        self.assertEqual(got["wait_argv"], [py, ".claude/hooks/work_completion.py", "--wait", "W1",
                                            "--round", "1"])
        self.assertIn("1분마다", got["wait_note"])
        self.assertNotIn("wait_error", got)
        got = self.call(C.tool_improve_work, {"work_id": "W1", "round": 3},
                        {"ok": True, "work_id": "W1", "round": 3})
        self.assertTrue(got["wait"].endswith("--wait W1 --round 3"))

    def test_space_in_python_is_quoted(self):
        self.config(r"C:\Program Files\Python312\python.exe")
        got = self.call(C.tool_register_work, {"title": "x"}, {"ok": True, "work_id": "W", "round": 1})
        self.assertTrue(got["wait"].startswith('"C:/Program Files/Python312/python.exe" '))
        self.assertEqual(got["wait_argv"][0], "C:/Program Files/Python312/python.exe")

    def test_missing_python_falls_back_by_os(self):
        self.config(None)
        got = self.call(C.tool_register_work, {"title": "x"}, {"ok": True, "work_id": "W", "round": 1})
        self.assertTrue(got["wait"].startswith("py .claude/hooks/"))
        self.config(None, "linux")
        got = self.call(C.tool_register_work, {"title": "x"}, {"ok": True, "work_id": "W", "round": 1})
        self.assertTrue(got["wait"].startswith("python3 .claude/hooks/"))

    def test_unbuildable_command_reports_wait_error(self):
        (self.root / ".claude/hooks/work_completion.py").unlink()
        self.config("py")
        got = self.call(C.tool_register_work, {"title": "x"}, {"ok": True, "work_id": "W", "round": 1})
        self.assertNotIn("wait", got)
        self.assertIn("대기 스크립트가 없다", got["wait_error"])
        (self.root / ".claude/hooks/work_completion.py").write_text("", encoding="utf-8")
        (self.root / ".ax/config.json").unlink()
        got = self.call(C.tool_register_work, {"title": "x"}, {"ok": True, "work_id": "W", "round": 1})
        self.assertIn("미구성", got["wait_error"])

    def test_refusal_gets_no_wait(self):
        self.config("py")
        refused = {"ok": False, "reason": "not_mounted", "error": "x"}
        self.assertEqual(self.call(C.tool_register_work, {"title": "x"}, refused), refused)


if __name__ == "__main__":
    unittest.main()
