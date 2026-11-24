"""#839 — 운영 스냅샷: 결정성·페이지 넘김·민감 정보 제외·아이디어 버킷·못 닿음·쓰기 범위."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import ops_snapshot as O

NOW = datetime(2026, 11, 24, 23, 40, 0, tzinfo=timezone(timedelta(hours=9)))
HEAD = "0123456789abcdef0123456789abcdef01234567"
M8 = {"id": 23, "name": "마일스톤 8 — 개선·확장"}
BUG = {"id": 24, "name": "마일스톤 8 - 버그/개선"}
IDEA = {"id": 18, "name": "아이디어 — 추후 검토 수집"}


def issue(n, version=None, **extra):
    d = {"id": n, "subject": f"[AX] 일감 {n}", "status": {"id": 1, "name": "신규"},
         "priority": {"id": 2, "name": "보통"}, "done_ratio": 10,
         "updated_on": "2026-11-24T14:30:00Z",
         "description": "본문 비밀 /home/sim/secret.txt", "author": {"id": 1, "name": "x"}}
    if version:
        d["fixed_version"] = version
    d.update(extra)
    return d


def pager(issues, *, total=None, limit=O.PAGE_LIMIT, calls=None):
    total = len(issues) if total is None else total

    def fetch(project, offset):
        if calls is not None:
            calls.append((project, offset))
        return {"issues": issues[offset:offset + limit], "total_count": total,
                "offset": offset, "limit": limit}
    return fetch


def runner(fail_units=(), head=HEAD, dirty=""):
    def run(argv):
        if argv[0] == "git":
            if "rev-parse" in argv:
                return 0, head
            return 0, dirty
        unit = argv[2]
        if unit in fail_units:
            return 1, "Failed to connect to bus: /run/user/1000/bus token=abc"
        return 0, ("LoadState=loaded\nActiveState=active\nSubState=running\n"
                   "ExecMainStartTimestamp=Mon 2026-11-24 10:00:00 KST")
    return run


def workers_ok(project, head):
    return [{"host": "192.168.0.43", "role": "worker", "commit": head[:12], "verdict": "same",
             "behind": 0, "note": "마스터 HEAD 와 같다", "error": ""},
            {"host": "192.168.0.2", "role": "worker", "commit": "aaaaaaaaaaaa", "verdict": "drifted",
             "behind": 3, "note": "aaaaaaa — HEAD 보다 3 커밋 뒤 (재배달 필요)", "error": ""}]


def workers_one_down(project, head):
    rows = workers_ok(project, head)
    rows[1] = {"host": "192.168.0.2", "role": "worker", "commit": "", "verdict": "", "behind": None,
               "note": "", "error": O._reason("BundleError: 192.168.0.2: C:\\trunk\\AXCluster\\.ax\\config.json 읽기 실패")}
    return rows


def mounted():
    return {"project": "AXCluster", "redmine": "ax-cluster"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.log = []

    def tearDown(self):
        self._tmp.cleanup()

    def go(self, *, fetch=None, run=None, workers=workers_ok, only="", project=""):
        return O.run(self.root, project=project, only=only, now=NOW,
                     fetch_page=fetch or pager([issue(3, M8), issue(1, BUG)]),
                     runner=run or runner(), workers=workers, mounted=mounted,
                     log=self.log.append, redmine_base="http://192.168.0.57:8080")

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")


class TestDeterminism(Base):
    def test_same_inputs_same_bytes(self):
        self.assertEqual(self.go(), 0)
        a = (self.read(O.REDMINE_FILE), self.read(O.OPS_FILE))
        self.assertEqual(self.go(), 0)
        b = (self.read(O.REDMINE_FILE), self.read(O.OPS_FILE))
        self.assertEqual(a, b)
        for text in a:
            self.assertIn("2026-11-24T23:40:00+09:00", text)
            self.assertIn(HEAD[:12], text)
            self.assertIn("python -m master.ops_snapshot", text)
            self.assertIn("라이브가 아니다", text)
            self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))

    def test_ordering(self):
        self.go(fetch=pager([issue(5, M8), issue(9, M8), issue(7), issue(2, BUG)]))
        t = self.read(O.REDMINE_FILE)
        self.assertLess(t.index("| 9 |"), t.index("| 5 |"))          # 일감은 id 내림차순
        self.assertLess(t.index("## 마일스톤 8 - 버그"), t.index("## 마일스톤 8 — 개선"))  # 버전 이름순
        self.assertLess(t.index("## 마일스톤 8 — 개선"), t.index(f"## {O.NO_VERSION}"))  # 버전 없음은 끝
        self.assertIn("| 2026-11-24 |", t)                             # 14:30Z → KST 23:30 같은 날


class TestPagination(Base):
    def test_two_pages_assembled(self):
        calls = []
        issues = [issue(n, M8) for n in range(150, 0, -1)]
        self.assertEqual(self.go(fetch=pager(issues, calls=calls)), 0)
        self.assertEqual([c[1] for c in calls], [0, 100])
        self.assertTrue(all(c[0] == "ax-cluster" for c in calls))
        t = self.read(O.REDMINE_FILE)
        self.assertIn("받은 열린 일감: 150건 · total_count 150", t)
        self.assertNotIn("[주의]", t)
        self.assertIn("| 1 |", t)
        self.assertIn("| 150 |", t)
        self.assertIn("열린 150건 (total_count 150)", "\n".join(self.log))

    def test_total_mismatch_visible(self):
        issues = [issue(n, M8) for n in range(120, 0, -1)]
        self.go(fetch=pager(issues, total=125))
        t = self.read(O.REDMINE_FILE)
        self.assertIn("total_count 125", t)
        self.assertIn("받은 120 ≠ total_count 125", t)

    def test_project_override(self):
        calls = []
        self.go(fetch=pager([issue(1)], calls=calls), project="ns")
        self.assertEqual(calls[0][0], "ns")
        self.assertIn("project_id=ns", self.read(O.REDMINE_FILE))


class TestSensitive(Base):
    def test_no_body_notes_mail_paths_or_secrets(self):
        bad = issue(7, M8, subject="경로 /home/sim/ax-cluster/x.py 와 C:\\Users\\janus\\a 그리고 a.b@example.com",
                    journals=[{"notes": "노트 내용 비밀"}],
                    assigned_to={"id": 2, "name": "x", "mail": "who@example.com"})
        rows = [{"host": "192.168.0.2", "role": "worker", "commit": "", "verdict": "", "behind": None,
                 "note": "", "error": O._reason("config 를 읽지 못했다(빈 응답): C:\\trunk\\AXCluster\\.ax\\config.json")},
                {"host": "192.168.0.43", "role": "worker", "commit": HEAD[:12], "verdict": "unknown",
                 "behind": None, "note": O._reason("api_key=SECRETVALUE token: abc /home/sim/.ax/x"), "error": ""}]
        self.go(fetch=pager([bad]), run=runner(fail_units=("ax-broker",)),
                workers=lambda p, h: rows)
        for rel in (O.REDMINE_FILE, O.OPS_FILE):
            t = self.read(rel)
            for leak in ("/home/", "C:\\", "본문 비밀", "노트 내용", "@example.com", "SECRETVALUE",
                         "token=abc", "token: abc", "/run/user"):
                self.assertNotIn(leak, t, f"{rel}: {leak}")
        self.assertIn("| 7 |", self.read(O.REDMINE_FILE))

    def test_scrub_keeps_relative_and_routes(self):
        self.assertEqual(O.scrub("master/client/bundle.py · /api/v1"), "master/client/bundle.py · /api/v1")
        self.assertEqual(O.scrub("a|b"), "a\\|b")


class TestIdeaBucket(Base):
    def test_count_only(self):
        self.go(fetch=pager([issue(30, IDEA), issue(31, IDEA), issue(3, M8)]))
        t = self.read(O.REDMINE_FILE)
        self.assertIn("아이디어 — 추후 검토 수집: 2건", t)
        self.assertNotIn("| 30 |", t)
        self.assertNotIn("| 31 |", t)
        self.assertNotIn("## 아이디어", t)
        self.assertIn("| 3 |", t)
        self.assertIn("아이디어 2", "\n".join(self.log))


class TestUnreached(Base):
    def test_redmine_failure(self):
        def boom(project, offset):
            raise OSError("[Errno 111] Connection refused /home/sim/x")
        rc = self.go(fetch=boom, only="redmine")
        self.assertEqual(rc, 1)
        t = self.read(O.REDMINE_FILE)
        self.assertIn("닿지 않았다: OSError", t)
        self.assertNotIn("| # |", t)
        self.assertNotIn("/home/", t)

    def test_service_and_worker_down(self):
        rc = self.go(run=runner(fail_units=("ax-broker",)), workers=workers_one_down, only="ops")
        self.assertEqual(rc, 1)
        t = self.read(O.OPS_FILE)
        self.assertIn("| ax-broker | 닿지 않았다:", t)
        self.assertIn("| ax-projects | active | running |", t)
        self.assertIn("| 192.168.0.2 | worker | 닿지 않았다:", t)
        self.assertIn("| 192.168.0.43 | worker | " + HEAD[:12] + " | same | 0 |", t)
        log = "\n".join(self.log)
        self.assertIn("[ops_snapshot] service ax-broker: 닿지 않았다", log)
        self.assertIn("[ops_snapshot] worker 192.168.0.2: 닿지 않았다", log)

    def test_all_reached_rc0(self):
        self.assertEqual(self.go(only="ops"), 0)
        t = self.read(O.OPS_FILE)
        self.assertNotIn("닿지 않았다", t)
        self.assertIn("| 192.168.0.2 | worker | aaaaaaaaaaaa | drifted | 3 |", t)
        self.assertIn("| 작업트리 | clean |", t)
        log = "\n".join(self.log)
        self.assertIn("[ops_snapshot] service ax-projects: active", log)
        self.assertIn("[ops_snapshot] worker 192.168.0.2: drifted", log)
        self.assertIn("[ops_snapshot] 썼다: docs/snapshots/ops-state.md", log)

    def test_mount_unreadable(self):
        rc = O.run(self.root, only="ops", now=NOW, runner=runner(), workers=workers_ok,
                   mounted=lambda: {"project": "", "redmine": "", "error": "ConfigError: 없다"},
                   log=self.log.append)
        self.assertEqual(rc, 1)
        self.assertIn("닿지 않았다: ConfigError", self.read(O.OPS_FILE))

    def test_head_unreadable(self):
        rc = self.go(run=runner(head="fatal: not a git repository"), only="ops")
        self.assertEqual(rc, 1)
        self.assertIn("마스터 HEAD: 닿지 않았다", self.read(O.OPS_FILE))

    def test_dirty_and_unit_missing(self):
        def run(argv):
            if argv[0] == "git":
                return (0, HEAD) if "rev-parse" in argv else (0, " M x")
            return 0, "LoadState=not-found\nActiveState=inactive\nSubState=dead\nExecMainStartTimestamp="
        self.assertEqual(self.go(run=run, only="ops"), 1)
        t = self.read(O.OPS_FILE)
        self.assertIn("| 작업트리 | dirty |", t)
        self.assertIn("유닛이 없다", t)


class TestDefaultWorkers(unittest.TestCase):
    """기본 `_workers` — 전체 probe 없이 HostFacts 를 만들어 `delivered_stamp`·`compare_version` 을 쓴다."""

    def test_uses_bundle_compare_without_probe(self):
        from unittest import mock
        from master.client import bundle
        seen = []

        def stamp(f):
            seen.append((f.host, f.windows))
            if f.host == "192.168.0.33":
                raise bundle.BundleError("192.168.0.33: C:\\trunk\\AXCluster\\.ax\\config.json 읽기 실패")
            if f.host == "192.168.0.2":
                return {"error": "config 를 읽지 못했다(빈 응답): C:\\trunk\\AXCluster\\.ax\\config.json"}
            return {"commit": HEAD, "commit_short": HEAD[:7]}

        ws = [("192.168.0.43", "sim", "/home/sim/trunk/AXCluster", "ssh", "worker", ""),
              ("192.168.0.2", "janus", "C:\\trunk\\AXCluster", "ssh", "worker", ""),
              ("192.168.0.33", "user", "C:\\trunk\\AXCluster", "ssh", "worker", ""),
              ("192.168.0.9", "", "", "ssh", "worker", "")]
        with mock.patch.object(bundle, "workshops", return_value=ws), \
                mock.patch.object(bundle, "probe", side_effect=AssertionError("probe 금지")), \
                mock.patch.object(bundle, "delivered_stamp", side_effect=stamp), \
                mock.patch.object(bundle, "compare_version",
                                  return_value={"ok": True, "verdict": "same", "behind": 0,
                                                "reason": "마스터 HEAD 와 같다"}) as cmp:
            rows = O._workers("AXCluster", HEAD)
        self.assertEqual(seen, [("192.168.0.43", False), ("192.168.0.2", True), ("192.168.0.33", True)])
        self.assertEqual(cmp.call_args.kwargs["head"], HEAD)
        by = {r["host"]: r for r in rows}
        self.assertEqual((by["192.168.0.43"]["verdict"], by["192.168.0.43"]["commit"]), ("same", HEAD[:12]))
        for h in ("192.168.0.2", "192.168.0.33", "192.168.0.9"):
            self.assertTrue(by[h]["error"], h)
            self.assertNotIn("C:\\", by[h]["error"])


class TestWriteScope(Base):
    def test_only_snapshot_files(self):
        (self.root / "keep.txt").write_text("x", encoding="utf-8")
        self.go()
        files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(files, ["docs/snapshots/ops-state.md", "docs/snapshots/redmine-open.md", "keep.txt"])

    def test_only_redmine_writes_one(self):
        self.go(only="redmine")
        files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(files, ["docs/snapshots/redmine-open.md"])

    def test_usage_error_rc2(self):
        with self.assertRaises(SystemExit) as cm:
            O.main(["--only", "bogus"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
