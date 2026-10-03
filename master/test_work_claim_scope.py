"""Push dispatch must never consume a different work (including verify fallback)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.task_queue.logic import register_work, register_task, claim_task
from master.task_queue.models import ClaimReq
from master.task_queue.persistence import TaskIndex


class WorkClaimScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ax-work-scope-")
        self.addCleanup(self.tmp.cleanup)
        self.idx = TaskIndex(Path(self.tmp.name))
        self.old = self.work("old")
        self.new = self.work("new")
        self.a = self.task(self.old, "old-piece", 10)
        self.b = self.task(self.new, "new-piece", 1)

    def work(self, title):
        result = register_work(self.idx, title=title, target_repo="/tmp/repo")
        self.assertTrue(result.get("ok"), result)
        wid = result["work_id"]
        self.idx.works[wid]["project"] = "P"
        return wid

    def task(self, wid, stem, priority):
        result = register_task(self.idx, work_id=wid, type="write",
                               task_data={}, stem=stem, priority=priority)
        self.assertTrue(result.get("ok"), result)
        return result["task_id"]

    def claim(self, **kw):
        return claim_task(self.idx, "worker", **kw)

    def test_scoped_claim_ignores_higher_priority_foreign_work(self):
        self.assertEqual(self.claim(work_id=self.new)["task_id"], self.b)
        self.assertEqual(self.idx.tasks[self.a]["status"], "pending")

    def test_retry_of_foreign_work_is_not_consumed(self):
        self.idx.tasks[self.a]["status"] = "needs_revision"
        self.assertEqual(self.claim(work_id=self.new)["task_id"], self.b)
        self.assertEqual(self.idx.tasks[self.a]["status"], "needs_revision")

    def test_empty_scope_does_not_fall_back_to_other_work(self):
        self.idx.tasks[self.b]["status"] = "verified"
        self.assertIsNone(self.claim(work_id=self.new))

    def test_unknown_work_does_not_fall_back(self):
        self.assertIsNone(self.claim(work_id="missing"))

    def test_terminal_work_cannot_be_claimed(self):
        for status in ("merged", "rejected", "cancelled"):
            with self.subTest(status=status):
                self.idx.works[self.new]["merge_status"] = status
                self.assertIsNone(self.claim(work_id=self.new))

    def test_project_filter_is_not_bypassed(self):
        self.assertIsNone(self.claim(work_id=self.new, project="other"))

    def test_unscoped_claim_remains_compatible(self):
        self.assertEqual(self.claim()["task_id"], self.a)

    def submitted(self, tid):
        self.idx.tasks[tid].update(status="submitted", distribution_mode="push",
                                   worker_id="author")

    def test_verify_fallback_cannot_escape_scope(self):
        self.submitted(self.a)
        self.idx.tasks[self.b]["status"] = "verified"
        self.assertIsNone(self.claim(work_id=self.new, verify_capable=True))
        self.assertIsNone(self.idx.tasks[self.a].get("verifier_id"))

    def test_scoped_verify_selects_only_own_work(self):
        self.submitted(self.a)
        self.submitted(self.b)
        result = self.claim(work_id=self.new, verify_capable=True)
        self.assertEqual((result["task_id"], result["job_kind"]), (self.b, "verify"))

    def test_verify_respects_project_filter(self):
        self.submitted(self.a)
        self.submitted(self.b)
        self.assertIsNone(self.claim(project="other", verify_capable=True))

    def test_request_model_keeps_optional_work_scope(self):
        self.assertEqual(ClaimReq(worker_id="worker").work_id, "")
        self.assertEqual(ClaimReq(worker_id="worker", work_id=self.new).work_id, self.new)


if __name__ == "__main__":
    unittest.main()
