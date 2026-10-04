"""세션 원본 수집기 검사 — 임시 디렉토리 + 가짜 원격 목록·스트림. 실 SSH·실 저장소 0.

본다: ① 원본 바이트 그대로 복사·레이아웃 ② cwd → 등록 작업장 프로젝트 귀속(미일치 `_unassigned`,
활성 프로젝트로 떨어뜨리지 않음) ③ `.ax/work/<task>` → task_id·work_id ④ 크기+mtime 증분
⑤ 자란 파일은 통째 재복사 ⑥ 색인 필드 ⑦ 스냅샷(프로젝트 포함) ⑧ 원격 쓰기 경로 없음
⑨ 화면 열기 트리거의 간격·잠금·비차단.
"""
import hashlib
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.work import session_usage as su


def _claude_lines(cwd, mid="m1"):
    return [
        {"type": "user", "cwd": cwd, "sessionId": "s1", "message": {"content": "본문은 그대로"}},
        {"type": "assistant", "cwd": cwd, "sessionId": "s1", "timestamp": "2026-10-04T01:00:00Z",
         "message": {"id": mid, "model": "claude-opus-5-5",
                     "usage": {"input_tokens": 3, "output_tokens": 4,
                               "cache_read_input_tokens": 5, "cache_creation_input_tokens": 6}}},
    ]


def _codex_lines(cwd):
    return [
        {"type": "session_meta", "payload": {"id": "c1", "cwd": cwd}},
        {"type": "turn_context", "payload": {"model": "gpt-5-codex"}},
        {"type": "event_msg", "timestamp": "2026-10-04T01:00:00Z",
         "payload": {"type": "token_count", "info": {
             "total_token_usage": {"input_tokens": 10}, "last_token_usage": {
                 "input_tokens": 10, "output_tokens": 2, "cached_input_tokens": 4}}}},
    ]


def _blob(rows):
    return ("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)).encode("utf-8")


class FakeRemote:
    """원격 파일 표 — 목록과 tar 스트림을 흉내 낸다. 쓰기 메서드는 없다."""

    def __init__(self):
        self.files = {}          # (tool, origin) -> (bytes, mtime)
        self.fetched = []

    def put(self, tool, origin, data, mtime):
        self.files[(tool, origin)] = (data, mtime)

    def lister(self, host):
        return [(t, o, len(d), m) for (t, o), (d, m) in sorted(self.files.items())]

    def fetcher(self, host, tool, origins):
        self.fetched.append((host, tool, list(origins)))
        for o in origins:
            if (tool, o) in self.files:
                data, mtime = self.files[(tool, o)]
                yield o, io.BytesIO(data), mtime


SHOPS = {
    "192.168.0.33": [("C:\\trunk\\AXCluster", "AXCluster"),
                     ("C:\\Users\\USER\\Documents\\ModularStage", "ModularStage")],
    "192.168.0.43": [("/home/sim/trunk/NS", "NS")],
}


class CollectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.raw = self.root / "raw"
        self.store = self.root / "sessions"
        self.queue = self.root / "queue"
        task = self.queue / ".claude" / "tasks" / "20261004_work_x" / "abcd1234_piece.md"
        task.parent.mkdir(parents=True)
        task.write_text("---\ntask_id: abcd1234\nwork_id: 20261004_work_x\n---\n", encoding="utf-8")
        self.remote = FakeRemote()

    def run_collect(self, host="192.168.0.33"):
        return su.collect(host, raw_root=self.raw, store=self.store, queue_root=self.queue,
                          shops=SHOPS, lister=self.remote.lister, fetcher=self.remote.fetcher)

    def test_copy_attribution_index_and_snapshot(self):
        a = _blob(_claude_lines("c:\\Trunk\\AXCluster\\master"))       # 대소문자·하위 경로
        b = _blob(_codex_lines("C:\\Users\\USER\\Documents\\ModularStage\\.ax\\work\\abcd1234"))
        c = _blob(_codex_lines("D:\\elsewhere"))
        self.remote.put("claude", "projects/C--trunk-AXCluster/s1.jsonl", a, 1000)
        self.remote.put("codex", "sessions/2026/10/04/r-b.jsonl", b, 1001)
        self.remote.put("codex", "sessions/2026/10/04/r-c.jsonl", c, 1002)
        res = self.run_collect()
        self.assertEqual((res["claude"]["copied"], res["codex"]["copied"]), (1, 2))
        self.assertEqual(res["codex"]["bytes"], len(b) + len(c))
        pa = self.raw / "AXCluster/192.168.0.33/claude/projects/C--trunk-AXCluster/s1.jsonl"
        pb = self.raw / "ModularStage/192.168.0.33/codex/sessions/2026/10/04/r-b.jsonl"
        pc = self.raw / "_unassigned/192.168.0.33/codex/sessions/2026/10/04/r-c.jsonl"
        self.assertEqual(pa.read_bytes(), a)                         # 바이트 그대로(마스킹 없음)
        self.assertEqual(pb.read_bytes(), b)
        self.assertEqual(pc.read_bytes(), c)
        index = su.load_index(self.raw)
        eb = index[su._key("192.168.0.33", "codex", "sessions/2026/10/04/r-b.jsonl")]
        self.assertEqual((eb["project"], eb["task_id"], eb["work_id"]),
                         ("ModularStage", "abcd1234", "20261004_work_x"))
        self.assertEqual(eb["sha256"], hashlib.sha256(b).hexdigest())
        self.assertEqual((eb["size"], eb["mtime"]), (len(b), 1001))
        for key in ("host", "tool", "origin", "collected_at", "raw"):
            self.assertIn(key, eb)
        ec = index[su._key("192.168.0.33", "codex", "sessions/2026/10/04/r-c.jsonl")]
        self.assertIsNone(ec["project"])
        self.assertIsNone(ec["work_id"])
        snap = json.loads((self.store / "192.168.0.33/claude/"
                           "projects__C--trunk-AXCluster__s1.json").read_text(encoding="utf-8"))
        self.assertEqual(snap["project"], "AXCluster")
        self.assertEqual(snap["records"][0]["cache_create"], 6)
        self.assertFalse(list(self.raw.rglob("*.part")))
        self.assertFalse((self.raw / ".staging" / "192.168.0.33").exists())

    def test_incremental_skip_and_regrow(self):
        o = "sessions/2026/10/04/r.jsonl"
        self.remote.put("codex", o, _blob(_codex_lines("/nowhere")), 1000)
        self.run_collect("192.168.0.43")
        self.remote.fetched.clear()
        second = self.run_collect("192.168.0.43")
        self.assertEqual((second["codex"]["skipped"], second["codex"]["copied"]), (1, 0))
        self.assertEqual(self.remote.fetched, [])                    # 받을 것이 없으면 전송 0
        grown = _blob(_codex_lines("/nowhere") + _codex_lines("/nowhere"))
        self.remote.put("codex", o, grown, 1005)
        third = self.run_collect("192.168.0.43")
        self.assertEqual(third["codex"]["copied"], 1)
        self.assertEqual(self.remote.fetched, [("192.168.0.43", "codex", [o])])
        self.assertEqual((self.raw / "_unassigned/192.168.0.43/codex" / o).read_bytes(), grown)
        # 원격에서 사라져도(30일 정리) 사본과 색인은 남는다
        self.remote.files.clear()
        self.run_collect("192.168.0.43")
        self.assertTrue((self.raw / "_unassigned/192.168.0.43/codex" / o).is_file())
        self.assertIn(su._key("192.168.0.43", "codex", o), su.load_index(self.raw))

    def test_missing_local_copy_is_refetched_and_listing_errors_reported(self):
        o = "projects/-home-sim-trunk-NS/s.jsonl"
        self.remote.put("claude", o, _blob(_claude_lines("/home/sim/trunk/NS")), 7)
        self.run_collect("192.168.0.43")
        (self.raw / "NS/192.168.0.43/claude" / o).unlink()
        again = self.run_collect("192.168.0.43")
        self.assertEqual(again["claude"]["copied"], 1)

        def boom(host):
            raise RuntimeError("목록 rc=255: down")
        res = su.collect("192.168.0.2", raw_root=self.raw, store=self.store, shops=SHOPS,
                         lister=boom, fetcher=self.remote.fetcher)
        self.assertTrue(res["claude"]["error"] and res["codex"]["error"])

    def test_vanished_and_unsafe_names_counted_as_errors(self):
        self.remote.put("codex", "sessions/a.jsonl", b"{}\n", 1)
        self.remote.put("codex", "sessions/../evil.jsonl", b"{}\n", 1)

        def lossy(host, tool, origins):
            return iter(())                                           # 목록 뒤 사라졌다
        res = su.collect("192.168.0.43", raw_root=self.raw, store=self.store, shops=SHOPS,
                         lister=self.remote.lister, fetcher=lossy)
        self.assertEqual(res["codex"]["errors"], 2)
        self.assertFalse((self.root / "evil.jsonl").exists())

    def test_names_are_batched_under_stdin_budget(self):
        for i in range(100):
            self.remote.put("codex", f"sessions/2026/10/04/{'r' * 90}-{i:03d}.jsonl", b"{}\n", i)
        res = self.run_collect("192.168.0.43")
        self.assertEqual(res["codex"]["copied"], 100)
        self.assertGreaterEqual(len(self.remote.fetched), 2)
        for _, _, names in self.remote.fetched:
            self.assertLessEqual(sum(len(n.encode()) + 1 for n in names), su.STDIN_BUDGET)
        self.assertEqual(list(su.batches(["aaaa", "bbbb", "cc"], budget=10)),
                         [["aaaa", "bbbb"], ["cc"]])

    def test_attribute_rules(self):
        self.assertEqual(su.attribute("/home/sim/trunk/NS/.ax/work/ff00ee11/x", "192.168.0.43",
                                      SHOPS), ("NS", "ff00ee11"))
        self.assertEqual(su.attribute("/home/sim/trunk/NSX", "192.168.0.43", SHOPS), (None, None))
        self.assertEqual(su.attribute("/home/sim/trunk/ns", "192.168.0.43", SHOPS), (None, None))
        self.assertEqual(su.attribute("/home/sim/ax-cluster", "local", SHOPS), (None, None))
        self.assertEqual(su.attribute("", "192.168.0.33", SHOPS), (None, None))

    def test_master_checkout_maps_to_axcluster(self):
        # 사용자 결정 2026-10-04: 마스터 세션은 cwd 가 ~/ax-cluster 면 AXCluster
        home = str(Path.home())
        shop = Mock(path="/home/sim/trunk/AXCluster")
        reg = Mock(names=["AXCluster", "NS"])
        reg.config_of.side_effect = lambda n: Mock(
            workshops={"192.168.0.43": shop} if n == "AXCluster" else {})
        with patch("master.projects.config.Registry.load", return_value=reg):
            shops = su.workshop_paths()
        self.assertEqual(shops["local"], [(home + "/ax-cluster", "AXCluster")])
        self.assertEqual(su.attribute(home + "/ax-cluster/master", "local", shops),
                         ("AXCluster", None))
        self.assertEqual(su.attribute(home, "local", shops), (None, None))
        self.assertEqual(su.attribute(home + "/ax-cluster-old", "local", shops), (None, None))
        reg.names = ["NS"]
        with patch("master.projects.config.Registry.load", return_value=reg):
            self.assertNotIn("local", su.workshop_paths())

    def test_parse_listing_both_formats(self):
        text = ("claude\t12\t1791037097.5\tprojects/a/b.jsonl\r\n"
                "codex\t3\t1791037097\tsessions/2026/x.jsonl\n"
                "garbage line\n")
        self.assertEqual(su.parse_listing(text), [
            ("claude", "projects/a/b.jsonl", 12, 1791037097),
            ("codex", "sessions/2026/x.jsonl", 3, 1791037097)])

    def test_reparse_moves_on_registry_change(self):
        o = "sessions/r.jsonl"
        self.remote.put("codex", o, _blob(_codex_lines("/home/sim/trunk/New")), 1)
        self.run_collect("192.168.0.43")
        self.assertTrue((self.raw / "_unassigned/192.168.0.43/codex" / o).is_file())
        shops = {**SHOPS, "192.168.0.43": [("/home/sim/trunk/New", "New")]}
        out = su.reparse(raw_root=self.raw, store=self.store, queue_root=self.queue, shops=shops)
        self.assertEqual(out["moved"], 1)
        self.assertTrue((self.raw / "New/192.168.0.43/codex" / o).is_file())
        self.assertFalse((self.raw / "_unassigned/192.168.0.43/codex" / o).exists())

    def test_remote_commands_are_read_only(self):
        import inspect
        remote = su._PS_LIST + "\n" + su._SH_LIST + "\n" + inspect.getsource(su.fetch_remote)
        for bad in ("Remove-Item", "rm -", " del ", "Move-Item", " mv ", "Set-Content",
                    "Out-File", "New-Item", "tar -x", "-delete"):
            self.assertNotIn(bad, remote, bad)
        self.assertNotIn(">", su._PS_LIST + su._SH_LIST)          # 원격 리디렉션 없음
        self.assertIn("tar -cf - -C", remote)


class LockAndTriggerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raw = Path(tmp.name) / "raw"
        self.store = Path(tmp.name) / "sessions"

    def test_collect_all_lock_is_exclusive(self):
        fd = su._acquire(self.raw)
        try:
            with self.assertRaises(su.Busy):
                su.collect_all(["local"], raw_root=self.raw, store=self.store, shops={})
        finally:
            import os
            os.close(fd)

    def test_trigger_interval_busy_and_nonblocking(self):
        started = threading.Event()
        release = threading.Event()

        def slow(hosts, **kw):
            started.set()
            release.wait(5)
            return {}

        with patch.object(su, "collect_all", side_effect=slow) as run:
            self.assertEqual(su.refresh_in_background(raw_root=self.raw, store=self.store,
                                                      min_interval=0), "started")
            self.assertTrue(started.wait(5))                 # 배경에서 돌고, 호출은 이미 돌아왔다
            self.assertEqual(su.refresh_in_background(raw_root=self.raw, store=self.store,
                                                      min_interval=0), "busy")
            release.set()
            for _ in range(100):
                if not su._BG_LOCK.locked():
                    break
                threading.Event().wait(0.05)
            self.assertFalse(su._BG_LOCK.locked())
            self.assertEqual(su.refresh_in_background(raw_root=self.raw, store=self.store,
                                                      min_interval=300), "interval")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0], ["local", *su.HOSTS])

    def test_trigger_never_raises(self):
        with patch.object(su, "collect_all", side_effect=RuntimeError("x")):
            self.assertEqual(su.refresh_in_background(raw_root=self.raw, store=self.store,
                                                      min_interval=0, _thread=False), "started")
        self.assertFalse(su._BG_LOCK.locked())
        with patch.object(Path, "mkdir", side_effect=OSError("ro")):
            self.assertEqual(su.refresh_in_background(raw_root=self.raw / "new", store=self.store,
                                                      min_interval=0), "error")
        self.assertFalse(su._BG_LOCK.locked())


if __name__ == "__main__":
    unittest.main()
