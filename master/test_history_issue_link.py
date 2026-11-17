"""#979 T4 — log_history 의 일감 연결: 서버 라우트 · frontmatter 왕복 · find_history 필터 · 클라 인자.

실제 8101 앱(TestClient, 소켓 없음)에 임시 트윈을 마운트로 보이게 하고, 일감 잠금·스냅샷은 대역이다
(실 Redmine 을 두드리지 않는다).

    .venv/bin/python -B master/test_history_issue_link.py
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.context_search.paths import ProjectPaths            # noqa: E402
from master.context_synth import history_gen as HG             # noqa: E402
from master.context_synth import history_harvest as HH         # noqa: E402

_TOKEN = "master-" + "m" * 40
SNAP = {"issue_id": 211, "status": "ok", "fetched_at": "2026-11-17T21:00:00+09:00",
        "subject": '[AX] 한글 "정답" 집합', "context": "원문이 「N번 진행하자」뿐이라\n알 수 없다",
        "tasks": [{"id": "T2", "goal": "정답 확정", "state": "작업중"}], "tasks_note": ""}


def _queue_client(root: Path):
    from fastapi.testclient import TestClient
    from master.task_queue import server as SV
    from master.task_queue.persistence import TaskIndex
    idx = TaskIndex(root)
    with patch.object(SV, "TaskIndex", return_value=idx), \
            patch.object(SV, "_bootstrap_log_rotation"), \
            patch.object(SV, "recover_stuck_works", return_value=[]), \
            patch.object(SV, "load_token", return_value=_TOKEN), \
            patch("master.auth.load_role_token", return_value=""), \
            patch("threading.Thread.start"), patch("uvicorn.run") as run:
        SV._run_http_server(root, 0, "127.0.0.1")
    return TestClient(run.call_args.args[0])


class FrontmatterTests(unittest.TestCase):
    def test_issue_fields_round_trip_through_mini_parser(self):
        text = HG.render(title="결정", issue_id=211, issue_id_source="issue_lock", issue_snapshot=SNAP)
        fm = HH._parse_simple_frontmatter(text.split("---")[1])
        self.assertEqual(fm["issue_id"], "211")
        self.assertEqual(fm["issue_id_source"], "issue_lock")
        self.assertEqual(fm["issue_subject"], "[AX] 한글 '정답' 집합", "큰따옴표는 바꾼다")
        self.assertEqual(fm["issue_context"], "원문이 「N번 진행하자」뿐이라 알 수 없다", "줄바꿈은 한 줄로")
        self.assertEqual(fm["issue_tasks"], ["T2 정답 확정"])
        self.assertEqual(fm["issue_status"], "ok")
        self.assertEqual(fm["decision_type"], "feature", "뒤 필드가 밀리지 않는다")

    def test_failed_and_unlinked(self):
        bad = {"issue_id": 7, "status": "fetch_failed", "fetched_at": "t", "why": "TimeoutError: x"}
        fm = HH._parse_simple_frontmatter(
            HG.render(title="t", issue_id=7, issue_id_source="provided", issue_snapshot=bad).split("---")[1])
        self.assertEqual((fm["issue_id"], fm["issue_status"], fm["issue_why"]), ("7", "fetch_failed", "TimeoutError: x"))
        self.assertNotIn("issue_subject", fm)
        fm = HH._parse_simple_frontmatter(HG.render(title="t").split("---")[1])
        self.assertIsNone(fm["issue_id"], "연결 없음은 null")
        self.assertNotIn("issue_status", fm)
        fm = HH._parse_simple_frontmatter(HG.render(title="t", issue_id="abc").split("---")[1])
        self.assertIsNone(fm["issue_id"], "숫자가 아니면 연결 없음")


class SearchTests(unittest.TestCase):
    def test_issue_filter_row_and_old_records(self):
        with tempfile.TemporaryDirectory() as t:
            p = ProjectPaths(name="T", root=Path(t))
            HG.write(p, HG.render(title="옛 기록", body="# 옛 기록\n본문"), title="옛 기록")
            HG.write(p, HG.render(title="일감 기록", issue_id=211, issue_id_source="issue_lock",
                                  issue_snapshot=SNAP, body="# 일감 기록\n본문"), title="일감 기록")
            allr = HH.search(p)
            self.assertEqual(allr["count"], 2)
            got = HH.search(p, issue_id=211)
            self.assertEqual([r["title"] for r in got["records"]], ["일감 기록"])
            row = got["records"][0]
            self.assertEqual(row["issue_id"], 211)
            self.assertEqual(row["issue"]["tasks"], ["T2 정답 확정"])
            self.assertEqual(row["issue"]["source"], "issue_lock")
            self.assertEqual(HH.search(p, issue_id=999)["count"], 0)
            old = next(r for r in allr["records"] if r["title"] == "옛 기록")
            self.assertEqual((old["issue_id"], old["issue"]), (None, {}), "옛 기록은 연결 없음 그대로")
            self.assertEqual(HH.search(p, query="정답 확정")["count"], 1, "당시 태스크로도 찾는다")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.twin = ProjectPaths(name="T", root=Path(self.tmp.name) / "twin")
        self.twin.root.mkdir()
        self.client = _queue_client(Path(self.tmp.name) / "queue")
        self.hdr = {"Authorization": "Bearer " + _TOKEN}
        for target in ("master.context_search.paths.resolve", "master.context_search.paths.resolve_mounted_only"):
            p = patch(target, lambda name="", **_k: self.twin)
            p.start()
            self.addCleanup(p.stop)

    def post(self, **extra):
        return self.client.post("/api/v1/history", headers=self.hdr,
                                json={"project": "T", "title": "결정 기록", **extra}).json()

    def test_lock_observed_and_snapshot_written(self):
        calls = []
        with patch("master.issue_lock.current", lambda root: {"issue_id": 211}), \
                patch("master.issue_snapshot.snapshot", lambda n: calls.append(n) or dict(SNAP)):
            r = self.post()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["issue_id"], r["issue_id_source"], r["issue_status"]), (211, "issue_lock", "ok"))
        self.assertEqual(calls, [211])
        rec = HH.search(self.twin, issue_id=211)["records"]
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["issue"]["subject"], "[AX] 한글 '정답' 집합")

    def test_given_number_wins_and_fetch_failure_still_records(self):
        def boom(n):
            raise RuntimeError("redmine down")
        with patch("master.issue_lock.current", lambda root: {"issue_id": 211}), \
                patch("master.issue_snapshot.snapshot", boom):
            r = self.post(issue_id=979)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["issue_id"], r["issue_id_source"], r["issue_status"]), (979, "provided", "fetch_failed"))
        rec = HH.search(self.twin, issue_id=979)["records"][0]
        self.assertEqual(rec["issue"]["status"], "fetch_failed")
        self.assertIn("RuntimeError", rec["issue"]["why"])

    def test_no_lock_means_no_link_and_no_fetch(self):
        calls = []
        def broken_lock(root):
            raise OSError("잠금 파일 깨짐")
        for lock in (lambda root: None, broken_lock):
            with patch("master.issue_lock.current", lock), \
                    patch("master.issue_snapshot.snapshot", lambda n: calls.append(n)):
                r = self.post()
            self.assertTrue(r["ok"], r)
            self.assertIsNone(r["issue_id"])
        self.assertEqual(calls, [])

    def test_search_route_filters_by_issue(self):
        with patch("master.issue_lock.current", lambda root: {"issue_id": 211}), \
                patch("master.issue_snapshot.snapshot", lambda n: dict(SNAP)):
            self.post()
        with patch("master.issue_lock.current", lambda root: None):
            self.post(title="다른 기록")
        r = self.client.post("/api/v1/history/search", headers=self.hdr,
                             json={"project": "T", "issue_id": 211}).json()
        self.assertTrue(r["ok"], r)
        self.assertEqual([x["title"] for x in r["records"]], ["결정 기록"])


class ClientToolTests(unittest.TestCase):
    def test_issue_id_sent_only_when_positive(self):
        from client.runtime import client_mcp as cm
        calls = []
        def api(m, path, payload=None):
            calls.append((path, payload))
            return {"ok": True}
        cm.dispatch_tool("log_history", {"title": "t", "issue_id": 979}, api=api)
        cm.dispatch_tool("log_history", {"title": "t", "issue_id": "abc"}, api=api)
        cm.dispatch_tool("find_history", {"issue_id": 211}, api=api)
        cm.dispatch_tool("find_history", {"issue_id": 0}, api=api)
        self.assertEqual(calls[0][1]["issue_id"], 979)
        self.assertNotIn("issue_id", calls[1][1])
        self.assertEqual(calls[2], ("/api/v1/history/search", {"issue_id": 211}))
        self.assertNotIn("issue_id", calls[3][1])
        names = {t["name"]: t for t in cm.TOOLS}
        for n in ("log_history", "find_history"):
            self.assertIn("issue_id", names[n]["inputSchema"]["properties"], n)


if __name__ == "__main__":
    unittest.main()
