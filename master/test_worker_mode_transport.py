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


if __name__ == "__main__":
    unittest.main()
