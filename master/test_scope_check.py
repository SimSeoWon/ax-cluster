from __future__ import annotations

import unittest

from master.work.scope_check import (
    ScopeReport,
    check_scope,
    classify_hunk,
    find_pseudo_spans,
    parse_diff_hunks,
)

BASE_SOURCE = """\
import os

MAX_RETRY = 3


def helper(x: int) -> int:
    return x + 1


def target_work(a: int, b: int) -> int:
    # [PSEUDO] compute weighted sum
    pass


def untouched_after() -> str:
    return "ok"
"""


class TestScopeCheck(unittest.TestCase):
    def test_in_scope_change_inside_pseudo_function(self) -> None:
        spans = find_pseudo_spans(BASE_SOURCE)
        self.assertEqual(spans, [(10, 12)])

        diff = """\
--- a/sample.py
+++ b/sample.py
@@ -10,3 +10,3 @@
 def target_work(a: int, b: int) -> int:
-    # [PSEUDO] compute weighted sum
-    pass
+    return a * 2 + b
"""
        report = check_scope(BASE_SOURCE, diff, filename="sample.py")
        self.assertEqual(report.out_of_scope_count, 0)
        self.assertEqual(report.by_kind, {"other": 0, "import": 0, "comment": 0})
        self.assertEqual(report.details, [])
        self.assertEqual(report.render_line(), "")

    def test_out_of_scope_other_change(self) -> None:
        diff = """\
--- a/sample.py
+++ b/sample.py
@@ -3,1 +3,1 @@
-MAX_RETRY = 3
+MAX_RETRY = 10
@@ -6,2 +6,2 @@
 def helper(x: int) -> int:
-    return x + 1
+    return x + 2
"""
        report = check_scope(BASE_SOURCE, diff, filename="sample.py")
        self.assertEqual(report.out_of_scope_count, 2)
        self.assertEqual(report.by_kind["other"], 2)
        self.assertEqual(report.by_kind["import"], 0)
        self.assertEqual(report.by_kind["comment"], 0)
        self.assertEqual(len(report.details), 2)

    def test_import_addition_classified_as_import(self) -> None:
        diff = """\
--- a/sample.py
+++ b/sample.py
@@ -1,1 +1,3 @@
 import os
+import sys
+from pathlib import Path
"""
        report = check_scope(BASE_SOURCE, diff, filename="sample.py")
        self.assertEqual(report.out_of_scope_count, 1)
        self.assertEqual(report.by_kind["import"], 1)
        self.assertEqual(report.by_kind["other"], 0)
        self.assertEqual(report.by_kind["comment"], 0)

    def test_comment_addition_classified_as_comment(self) -> None:
        diff = """\
--- a/sample.py
+++ b/sample.py
@@ -15,2 +15,3 @@
 def untouched_after() -> str:
+    # Added explanatory note
     return "ok"
"""
        report = check_scope(BASE_SOURCE, diff, filename="sample.py")
        self.assertEqual(report.out_of_scope_count, 1)
        self.assertEqual(report.by_kind["comment"], 1)
        self.assertEqual(report.by_kind["other"], 0)
        self.assertEqual(report.by_kind["import"], 0)

    def test_top_level_pseudo_block_handling(self) -> None:
        top_level_source = """\
import os

# [PSEUDO] define registry table
REGISTRY = {
    "a": 1,
    "b": 2,
}

OTHER_CONST = 42
"""
        spans = find_pseudo_spans(top_level_source)
        self.assertEqual(spans, [(3, 7)])

        in_scope_diff = """\
@@ -3,5 +3,4 @@
-# [PSEUDO] define registry table
 REGISTRY = {
-    "a": 1,
+    "a": 10,
     "b": 2,
 }
"""
        report_ok = check_scope(top_level_source, in_scope_diff)
        self.assertEqual(report_ok.out_of_scope_count, 0)

        out_scope_diff = """\
@@ -9,1 +9,1 @@
-OTHER_CONST = 42
+OTHER_CONST = 99
"""
        report_out = check_scope(top_level_source, out_scope_diff)
        self.assertEqual(report_out.out_of_scope_count, 1)
        self.assertEqual(report_out.by_kind["other"], 1)

    def test_empty_diff_and_file_without_pseudo(self) -> None:
        empty_report = check_scope(BASE_SOURCE, "")
        self.assertEqual(empty_report.out_of_scope_count, 0)
        self.assertEqual(empty_report.render_line(), "")

        no_pseudo_source = """\
def foo() -> int:
    return 1
"""
        self.assertEqual(find_pseudo_spans(no_pseudo_source), [])
        diff = """\
@@ -1,2 +1,2 @@
 def foo() -> int:
-    return 1
+    return 2
"""
        report = check_scope(no_pseudo_source, diff)
        self.assertEqual(report.out_of_scope_count, 1)
        self.assertEqual(report.by_kind["other"], 1)

    def test_render_line_formatting(self) -> None:
        clean = ScopeReport()
        self.assertEqual(clean.render_line(), "")

        mixed = ScopeReport(
            out_of_scope_count=2,
            by_kind={"other": 1, "import": 1, "comment": 0},
            details=["sample.py:L3-3 (other)", "sample.py:L1-1 (import)"],
        )
        self.assertEqual(
            mixed.render_line(),
            "범위 밖 변경 덩어리 2건 (other 1 · import 1)",
        )

        all_kinds = ScopeReport(
            out_of_scope_count=4,
            by_kind={"other": 2, "import": 1, "comment": 1},
        )
        self.assertEqual(
            all_kinds.render_line(),
            "범위 밖 변경 덩어리 4건 (other 2 · import 1 · comment 1)",
        )


if __name__ == "__main__":
    unittest.main()
