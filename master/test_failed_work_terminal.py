"""#701: failed rounds terminate; notification failures preserve successful evidence.

Temporary persisted queue + synchronous fake notification, no network/SSH/real Codex.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.task_queue import logic as Q, logic_cleanup as C, logic_lifecycle as L
from master.task_queue.logic_persist import _save_work, completed_work_status
from master.task_queue.persistence import TaskIndex


class ImmediateThread:
    def __init__(self, target, **kw):
        self.target = target

    def start(self):
        self.target()


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ax-701-")
        self.addCleanup(self.temp.cleanup)
        self.idx = TaskIndex(Path(self.temp.name))
        # Never race the registration notifier against the fake review notifier.
        self.registration = patch.object(Q, "_create_work_issue_async", lambda *a: None)
        self.registration.start()
        self.addCleanup(self.registration.stop)
        self.cleanup = patch.object(L, "_auto_cleanup_work_async", lambda *a: None)
        self.cleanup.start()
        self.addCleanup(self.cleanup.stop)
        self.wid = Q.register_work(self.idx, title="test", target_repo="/tmp/repo",
                                  project="NS", target_branch="task/test/base")["work_id"]

    def tasks(self, n):
        return [Q.register_task(self.idx, work_id=self.wid, type="code", task_data={},
                               target_file=f"Source/F{i}.cpp", stem=f"f{i}")["task_id"]
                for i in range(n)]

    @property
    def work(self):
        return self.idx.works[self.wid]

    def claim(self):
        return Q.claim_task(self.idx, "192.168.0.2", capabilities=["ue5"], types=["code"])

    def fail(self, t, **kw):
        return L.submit_fail(self.idx, t["task_id"], "execution failed", "actual detail",
                             worker_id="192.168.0.2", epoch=t["epoch"], **kw)

    def finish(self, t):
        self.assertTrue(L.submit_result(self.idx, t["task_id"], branch="attempt/preserved",
                                       head_commit="abc1234", self_check={},
                                       worker_id="192.168.0.2", epoch=t["epoch"])["ok"])
        self.assertTrue(L.verify_task(self.idx, t["task_id"], passed=True, result="pass")["ok"])

    def notify(self, *, config=None, note=True):
        self.work["redmine_issue_id"] = 123
        notes = []
        with patch.object(C.threading, "Thread", ImmediateThread), \
                patch.object(C, "_read_redmine_config", lambda *a: config if config is not None
                             else {"url": "http://fake", "api_key": "fake", "project": "ns"}), \
                patch.object(C, "_redmine_add_note", lambda *a:
                             notes.append(a[-1]) or note):
            C._try_create_review_issue_async(self.idx, self.wid)
        return notes

    def test_mixed_round_ends_only_when_all_terminal_and_preserves_success(self):
        self.tasks(2)
        first = self.claim()
        self.finish(first)
        self.assertEqual(self.work["merge_status"], "in_progress")
        self.assertTrue(self.fail(self.claim())["ok"])
        self.assertEqual(self.work["merge_status"], "rejected")
        self.assertEqual(self.work["verified"], 1)
        self.assertEqual(self.work["total"], 2)
        self.assertEqual(self.idx.tasks[first["task_id"]]["submitted_branch"], "attempt/preserved")
        self.assertTrue(self.work["terminal_at"])
        rebuilt = TaskIndex(self.idx.root)
        rebuilt.rebuild()
        self.assertEqual(rebuilt.works[self.wid]["merge_status"], "rejected")

    def test_cancel_is_terminal_but_no_work_is_success(self):
        tid, = self.tasks(1)
        L.cancel_task(self.idx, tid, reason="human cancellation")
        self.assertEqual(self.work["merge_status"], "cancelled")

    def test_no_work_waits_for_review(self):
        tid, = self.tasks(1)
        L.cancel_task(self.idx, tid, reason="already complete", no_work=True)
        self.assertEqual(self.work["merge_status"], "ready_for_review")

    def test_revise_is_not_terminal(self):
        self.tasks(1)
        self.fail(self.claim(), result="revise")
        self.assertEqual(self.work["merge_status"], "in_progress")
        self.assertEqual(completed_work_status(self.idx, self.wid), "")

    def test_stale_failure_cannot_kill_new_attempt(self):
        self.tasks(1)
        t = self.claim()
        result = L.submit_fail(self.idx, t["task_id"], "old failure", epoch=t["epoch"] - 1,
                               worker_id="192.168.0.2")
        self.assertTrue(result["stale"])
        self.assertEqual(self.work["merge_status"], "in_progress")

    def test_boot_recovers_old_failed_ready_without_reopening_terminal(self):
        self.tasks(1)
        self.fail(self.claim())
        self.work["merge_status"] = "ready_for_review"
        with patch.object(Q, "_auto_cleanup_work_async", lambda *a: None):
            self.assertEqual(Q.recover_stuck_works(self.idx), [self.wid])
            self.assertEqual(Q.recover_stuck_works(self.idx), [])
        self.assertEqual(self.work["merge_status"], "rejected")

    def test_old_round_failure_does_not_poison_current_success(self):
        self.tasks(1)
        self.fail(self.claim())
        self.work.update(round=2, merge_status="in_progress")
        self.tasks(1)
        self.finish(self.claim())
        self.assertEqual(self.work["merge_status"], "ready_for_review")

    def test_notice_failure_preserves_success_and_persists_human_warning(self):
        self.tasks(1)
        self.finish(self.claim())
        self.notify(note=False)
        self.assertEqual(self.work["merge_status"], "ready_for_review")
        self.assertTrue(self.work["termination_required"])
        self.assertIn("실패", self.work["notification_error"])
        rebuilt = TaskIndex(self.idx.root)
        rebuilt.rebuild()
        self.assertTrue(rebuilt.works[self.wid]["termination_required"])
        self.notify()
        self.assertFalse(self.work["termination_required"])
        self.assertEqual(self.work["notification_error"], "")
        self.assertEqual(self.notify(), [])  # successful notice deduplicated

    def test_missing_notification_configuration_is_visible(self):
        self.tasks(1)
        self.finish(self.claim())
        self.notify(config={})
        self.assertIn("설정 누락", self.work["notification_error"])
        self.assertTrue(self.work["termination_required"])

    def test_failed_notice_describes_terminal_not_advance(self):
        self.tasks(1)
        self.fail(self.claim())
        notes = self.notify()
        self.assertEqual(len(notes), 1)
        self.assertIn("rejected", notes[0])
        self.assertIn("actual detail", notes[0])
        self.assertIn("통합·전진 대기 대상이 아니다", notes[0])
        self.assertNotIn("ax-advance", notes[0])
        self.assertEqual(self.work["noticed_status"], "rejected")

    def test_stale_round_callback_is_ignored(self):
        self.work["round"] = 2
        C._record_notification_outcome(self.idx, self.wid, 1, error="old notice")
        self.assertNotIn("notification_error", self.work)


if __name__ == "__main__":
    unittest.main()
