"""명시 통합 검사 어댑터 회귀 — 실제 자식 프로세스와 임시 저장소만 사용한다."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.integration_checks import CheckConfigError, load_checks, run_check


class IntegrationChecksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ax-integration-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "root"
        (self.root / "master").mkdir(parents=True)
        self.manifest = self.root / "checks.json"

    def entry(self, code="print('CHECKS 3')\n", **overrides):
        path = self.root / "master/test_fixture.py"
        path.write_text(code, encoding="utf-8")
        return dict(path="master/test_fixture.py", count_pattern=r"^CHECKS (?P<count>[0-9]+)$",
                    **overrides)

    def load(self, value):
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        return load_checks(self.manifest, self.root)

    def test_manifest_validates_and_defaults(self):
        entry = self.entry()
        loaded = self.load([entry])
        self.assertEqual(loaded, [dict(entry, timeout=120)])

    def test_manifest_invalid_values(self):
        entry = self.entry()
        for value in ([], {}, None, [None], [entry, entry],
                      [dict(entry, path="../out.py")], [dict(entry, path="/outside.py")],
                      [dict(entry, path="master/test_missing.py")],
                      [dict(entry, path="master/../master/test_fixture.py")],
                      [dict(entry, path="master/test_fixture.py", typo=True)],
                      [dict(entry, count_pattern="[")], [dict(entry, count_pattern="CHECKS (.+)")],
                      [dict(entry, timeout=0)], [dict(entry, timeout=-1)],
                      [dict(entry, timeout=True)], [dict(entry, timeout=float("inf"))],
                      [dict(entry, timeout="120")], [dict(entry, failed_count_pattern="bad")]):
            with self.subTest(value=value), self.assertRaises(CheckConfigError):
                self.load(value)
        self.manifest.write_text("{", encoding="utf-8")
        with self.assertRaises(CheckConfigError):
            load_checks(self.manifest, self.root)

    def test_symlink_escape_is_rejected(self):
        outside = self.base / "outside.py"
        outside.write_text("print('CHECKS 3')\n", encoding="utf-8")
        path = self.root / "master/test_outside.py"
        path.symlink_to(outside)
        with self.assertRaises(CheckConfigError):
            self.load([dict(path="master/test_outside.py", count_pattern=r"(?P<count>[0-9]+)")])

    def test_success_and_last_summary(self):
        entry = self.entry("print('CHECKS 1')\nprint('CHECKS 7')\n")
        result = run_check(self.root, entry)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["count"], 7)
        self.assertEqual(result["rc"], 0)

    def test_stderr_summary(self):
        entry = self.entry("import sys\nprint('CHECKS 2', file=sys.stderr)\n")
        result = run_check(self.root, entry)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["count"], 2)

    def test_exit_failure_even_with_positive_evidence(self):
        result = run_check(self.root, self.entry("print('CHECKS 3')\nraise SystemExit(1)\n"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["rc"], 1)
        self.assertIn("CHECKS 3", result["stdout"])

    def test_missing_zero_and_invalid_counts(self):
        for code, pattern in (("pass\n", r"^CHECKS (?P<count>[0-9]+)$"),
                              ("print('CHECKS 0')\n", r"^CHECKS (?P<count>[0-9]+)$"),
                              ("print('CHECKS -1')\n", r"^CHECKS (?P<count>.+)$"),
                              ("print('CHECKS bad')\n", r"^CHECKS (?P<count>.+)$")):
            with self.subTest(code=code):
                entry = self.entry(code)
                entry["count_pattern"] = pattern
                self.assertFalse(run_check(self.root, entry)["ok"])

    def test_total_and_failed_groups(self):
        for summary, expected in (("3/3 failed=0", True), ("2/3 failed=0", False),
                                  ("3/3 failed=1", False)):
            entry = self.entry(f"print({summary!r})\n")
            entry["count_pattern"] = r"^(?P<count>[0-9]+)/(?P<total>[0-9]+) failed=(?P<failed>[0-9]+)$"
            with self.subTest(summary=summary):
                self.assertEqual(run_check(self.root, entry)["ok"], expected)

    def test_explicit_failure_summary_required(self):
        for summary, expected in (("FAILURES 0", True), ("FAILURES 1", False), ("", False)):
            entry = self.entry(f"print('CHECKS 3')\nprint({summary!r})\n",
                               failed_count_pattern=r"^FAILURES (?P<count>[0-9]+)$")
            with self.subTest(summary=summary):
                self.assertEqual(run_check(self.root, entry)["ok"], expected)

    def test_timeout_and_os_error_fail_closed(self):
        result = run_check(self.root, self.entry("import time\ntime.sleep(2)\n", timeout=0.1))
        self.assertFalse(result["ok"])
        self.assertIn("타임아웃", result["reason"])
        result = run_check(self.root, self.entry(), python=str(self.base / "no-python"))
        self.assertFalse(result["ok"])
        self.assertIn("실행 실패", result["reason"])

    def test_unittest_real_execution(self):
        entry = self.entry("import unittest\nclass Example(unittest.TestCase):\n"
                           "    def test_real(self): self.assertEqual(2+2, 4)\n"
                           "if __name__ == '__main__': unittest.main()\n")
        entry["count_pattern"] = r"^Ran (?P<count>[0-9]+) tests? in [0-9.]+s"
        result = run_check(self.root, entry)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["count"], 1)

    def test_unittest_all_skipped_is_not_execution(self):
        entry = self.entry("import unittest\nclass Example(unittest.TestCase):\n"
                           "    @unittest.skip('fixture')\n"
                           "    def test_skip(self): pass\n"
                           "if __name__ == '__main__': unittest.main()\n")
        entry["count_pattern"] = r"^Ran (?P<count>[0-9]+) tests? in [0-9.]+s"
        result = run_check(self.root, entry)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["count"], 0)

    def test_unittest_failed_or_incomplete_signal(self):
        for status in ("FAILED (failures=1)", ""):
            entry = self.entry(f"print('Ran 3 tests in 0.001s')\nprint({status!r})\n")
            entry["count_pattern"] = r"^Ran (?P<count>[0-9]+) tests? in [0-9.]+s"
            with self.subTest(status=status):
                self.assertFalse(run_check(self.root, entry)["ok"])

    def test_child_environment_and_cwd_are_isolated(self):
        code = ("import os, sys\nfrom pathlib import Path\n"
                f"assert Path.cwd() == Path({str(self.root)!r})\n"
                "assert sys.dont_write_bytecode\n"
                "assert os.environ['AX_PROJECTS_ROOT'] != 'production-projects'\n"
                "assert os.environ['AX_GITEA_REPO_ROOT'] != 'production-gitea'\n"
                "assert Path(os.environ['AX_PROJECTS_ROOT']).is_dir()\n"
                "assert Path(os.environ['AX_GITEA_REPO_ROOT']).is_dir()\n"
                "assert os.environ['AX_CHECK_LEAK'] == 'parent'\n"
                "os.environ['AX_CHECK_LEAK'] = 'child'\nprint('CHECKS 1')\n")
        with patch.dict(os.environ, AX_PROJECTS_ROOT="production-projects",
                        AX_GITEA_REPO_ROOT="production-gitea", AX_CHECK_LEAK="parent"):
            entry = self.entry(code)
            for _ in range(2):
                result = run_check(self.root, entry)
                self.assertTrue(result["ok"], result)
                self.assertEqual(os.environ["AX_CHECK_LEAK"], "parent")
            self.assertEqual(os.environ["AX_PROJECTS_ROOT"], "production-projects")
        self.assertEqual(list(self.root.rglob("__pycache__")), [])

    def test_runner_contract_and_revalidation(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, "CHECKS 1\n", "")
        result = run_check(self.root, self.entry(), runner=runner)
        self.assertTrue(result["ok"])
        argv, kwargs = calls[0]
        self.assertEqual(argv[:2], [sys.executable, "-B"])
        self.assertEqual(kwargs["cwd"], str(self.root))
        self.assertIs(kwargs["shell"], False)
        result = run_check(self.root, dict(path="../bad.py"), runner=runner)
        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
