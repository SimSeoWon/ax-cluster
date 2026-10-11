"""#701: failed rounds terminate; notification failures preserve successful evidence.

Temporary persisted queue + synchronous fake notification, no network/SSH/real Codex.
"""
import sys
import tempfile
import unittest
import copy
from datetime import datetime, timezone
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
        # `#780` 즉시 통보 — 네트워크 없이 동기로 돌리고 노트·저널을 모은다.
        self.piece_notes, self.log = [], []
        self.note_result = True
        orig_log = C._tq_log
        for p in (patch.object(C.threading, "Thread", ImmediateThread),
                  patch.object(C, "_read_redmine_config", lambda *a:
                               {"url": "http://fake", "api_key": "fake", "project": "ns"}),
                  patch.object(C, "_redmine_add_note", self._fake_note),
                  patch.object(C, "_redmine_post_issue", self._no_new_issue),
                  patch.object(C, "_tq_log", lambda m, r: (self.log.append(m), orig_log(m, r)))):
            p.start()
            self.addCleanup(p.stop)
        self.wid = Q.register_work(self.idx, title="test", target_repo="/tmp/repo",
                                  project="NS", target_branch="task/test/base")["work_id"]

    def _fake_note(self, cfg, issue_id, notes, *a):
        if isinstance(self.note_result, Exception):
            raise self.note_result
        self.piece_notes.append((issue_id, notes))
        return self.note_result

    def _no_new_issue(self, *a, **kw):
        raise AssertionError("즉시 통보가 이슈를 새로 만들면 안 된다")

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

    def test_quota_failure_persists_reason_without_terminating_and_reassigns(self):
        self.tasks(1)
        task = self.claim()
        tid = task["task_id"]
        detail = "[fp:abcdefabcdef] [kind:quota] usage limit " + "x" * 900
        before = datetime.now(timezone.utc)
        result = L.submit_fail(self.idx, tid, "quota_exhausted", detail,
                               worker_id="192.168.0.2", epoch=task["epoch"])
        after = datetime.now(timezone.utc)
        self.assertTrue(result["released"])
        rec = self.idx.tasks[tid]
        self.assertEqual(rec["status"], "pending")
        self.assertEqual(rec["release_reason"], "quota_exhausted")
        self.assertEqual(rec["release_detail"], detail[:600])
        self.assertNotIn("fail_reason", rec)
        self.assertNotIn("fail_detail", rec)
        self.assertTrue(rec["release_detail"].startswith("[fp:abcdefabcdef] [kind:quota]"))
        self.assertNotIn("failed_at", rec)
        self.assertIsNone(rec["worker_id"])
        self.assertEqual(self.work["merge_status"], "in_progress")
        self.assertEqual(completed_work_status(self.idx, self.wid), "")
        until = datetime.fromisoformat(rec["quota_blocked_workers"]["192.168.0.2"])
        self.assertGreaterEqual((until - before).total_seconds(), 5 * 3600 - 1)
        self.assertLessEqual((until - after).total_seconds(), 5 * 3600)
        rebuilt = TaskIndex(self.idx.root)
        rebuilt.rebuild()
        self.assertEqual(rebuilt.tasks[tid]["status"], "pending")
        self.assertEqual(rebuilt.tasks[tid]["release_detail"], detail[:600])
        self.assertEqual(rebuilt.tasks[tid]["release_reason"], "quota_exhausted")
        self.assertEqual(rebuilt.tasks[tid]["quota_blocked_workers"], rec["quota_blocked_workers"])
        self.assertFalse(self.claim())
        reassigned = Q.claim_task(self.idx, "192.168.0.43", capabilities=["ue5"], types=["code"])
        self.assertEqual(reassigned["task_id"], tid)
        self.assertEqual(reassigned["worker_id"], "192.168.0.43")
        self.assertEqual(reassigned["epoch"], task["epoch"] + 1)
        self.assertEqual(reassigned["release_detail"], detail[:600])

    def test_quota_release_does_not_leak_into_later_failure(self):
        # 한도 반납 → 다른 워커 재할당 → 검증 reject: 최종 실패는 옛 한도 사유로 읽히지 않는다.
        from master.work import workmodel as WM
        self.tasks(1)
        task = self.claim()
        tid = task["task_id"]
        L.submit_fail(self.idx, tid, "quota_exhausted", "[kind:quota] usage limit",
                      worker_id="192.168.0.2", epoch=task["epoch"])
        Q.claim_task(self.idx, "192.168.0.43", capabilities=["ue5"], types=["code"])
        self.idx.tasks[tid]["status"] = "submitted"
        L.verify_task(self.idx, tid, result="reject", feedback="layer2 reject: invented enum")
        rec = self.idx.tasks[tid]
        self.assertEqual(rec["status"], "failed")
        self.assertEqual(rec["fail_reason"], "verify:reject")
        self.assertEqual(rec["fail_detail"], "layer2 reject: invented enum")
        self.assertNotEqual(WM.Task(rec).classify()[0], WM.QUOTA)

    def test_quota_stale_and_identity_rejections_preserve_record(self):
        self.tasks(1)
        task = self.claim()
        tid = task["task_id"]
        self.idx.tasks[tid]["fail_reason"] = "previous reason"
        self.idx.tasks[tid]["fail_detail"] = "previous detail"
        original = copy.deepcopy(self.idx.tasks[tid])
        for epoch, worker, key in ((task["epoch"] - 1, "192.168.0.2", "stale"),
                                   (task["epoch"], "192.168.0.43", "identity")):
            with self.subTest(gate=key):
                result = L.submit_fail(self.idx, tid, "quota_exhausted", "new detail",
                                       epoch=epoch, worker_id=worker)
                self.assertFalse(result["ok"])
                self.assertTrue(result[key])
                self.assertEqual(self.idx.tasks[tid], original)
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

    # ── `#780` 「즉시 통보, 나머지 계속」 ─────────────────────────────────────────
    def piece_log(self):
        return [m for m in self.log if m.startswith("[piece-fail]")]

    def test_780_terminal_failure_with_others_running_notes_once(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(3)
        t = self.claim()
        self.assertTrue(self.fail(t)["ok"])
        tid = t["task_id"]
        rec = self.idx.tasks[tid]
        self.assertEqual(rec["status"], "failed")
        self.assertEqual(self.work["merge_status"], "in_progress")   # 나머지는 계속
        self.assertEqual(len(self.piece_notes), 1)
        issue, note = self.piece_notes[0]
        self.assertEqual(issue, 123)
        for want in (tid, rec["target_file"], "execution failed: actual detail",
                     "terminal failed", "2건은 계속 진행 중", "라운드 공지는"):
            self.assertIn(want, note)
        self.assertNotIn("하세요", note)                                # 명령형 없음
        self.assertTrue(any(f"task={tid}" in m and rec["target_file"] in m
                            and self.wid in m and "actual detail" in m
                            for m in self.piece_log()))
        self.assertTrue(rec["fail_notice_at"])
        self.assertEqual(rec["fail_notice_error"], "")
        self.assertEqual(rec["fail_notice_issue"], 123)
        self.assertNotIn("fail_notice_pending", rec)
        self.assertNotIn("notification_error", self.work)              # 라운드 계약 불변
        # 다른 조각은 멈추지 않았다 — 여전히 집을 수 있다
        self.assertEqual({x["status"] for k, x in self.idx.tasks.items() if k != tid},
                         {"pending"})
        # 중복 없음 — 직접 재호출 · 재검증 뒤 다시 실패
        self.assertFalse(C._notify_piece_failed_async(self.idx, tid))
        self.assertTrue(L.reverify_task(self.idx, tid)["ok"])
        self.assertTrue(L.verify_task(self.idx, tid, result="reject", feedback="again")["ok"])
        self.assertEqual(len(self.piece_notes), 1)
        rebuilt = TaskIndex(self.idx.root)
        rebuilt.rebuild()
        self.assertTrue(rebuilt.tasks[tid]["fail_notice_at"])

    def test_skeleton_failure_waits_for_round_notice_and_preserves_remaining_success(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(3)
        skeleton, running = self.claim(), self.claim()
        tid = skeleton["task_id"]
        result = L.submit_fail(self.idx, tid, "BLOCKED",
                               "[kind:skeleton] 층1 동결 위반 — 골조 변경 필요",
                               worker_id="192.168.0.2", epoch=skeleton["epoch"])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(self.idx.tasks[tid]["status"], "failed")
        self.assertEqual(self.work["merge_status"], "in_progress")
        self.assertEqual(self.piece_notes, [])
        self.assertNotIn("fail_notice_at", self.idx.tasks[tid])
        self.assertFalse(C._notify_piece_failed_async(self.idx, tid))
        self.assertEqual({t["status"] for k, t in self.idx.tasks.items() if k != tid},
                         {"pending", "claimed"})
        self.finish(running)
        self.assertEqual(self.work["merge_status"], "in_progress")
        remaining = self.claim()
        self.assertTrue(remaining)
        self.finish(remaining)
        self.assertEqual(self.work["merge_status"], "rejected")
        self.assertEqual(self.work["verified"], 2)
        self.assertEqual(self.piece_notes, [])
        notes = self.notify()
        self.assertEqual(len(notes), 1)
        self.assertIn("골조 변경 필요", notes[0])
        self.assertIn("골조 수정 후 재작업 필요", notes[0])
        self.assertIn("성공 조각의 커밋 증거", notes[0])
        for task in (running, remaining):
            self.assertEqual(self.idx.tasks[task["task_id"]]["submitted_branch"], "attempt/preserved")
            self.assertIn(task["task_id"], notes[0])
            self.assertIn("head_commit: abc1234", self.idx.task_paths[task["task_id"]].read_text())

    def test_780_verify_reject_with_others_running_notes(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(2)
        t = self.claim()
        self.assertTrue(L.submit_result(self.idx, t["task_id"], branch="attempt/x",
                                        head_commit="abc1234", self_check={},
                                        worker_id="192.168.0.2", epoch=t["epoch"])["ok"])
        self.assertTrue(L.verify_task(self.idx, t["task_id"], result="reject",
                                      feedback="layer2 grounding_incomplete")["ok"])
        self.assertEqual(len(self.piece_notes), 1)
        self.assertIn("verify:reject: layer2 grounding_incomplete", self.piece_notes[0][1])

    def test_780_retryable_failures_do_not_notify(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(2)
        t = self.claim()
        self.assertTrue(self.fail(t, result="revise")["revised"])
        t = self.claim()
        self.assertTrue(L.submit_fail(self.idx, t["task_id"], "quota_exhausted", "429",
                                      worker_id="192.168.0.2", epoch=t["epoch"])["released"])
        self.assertEqual(self.piece_notes, [])
        self.assertEqual(self.piece_log(), [])
        self.assertTrue(all("fail_notice_at" not in x for x in self.idx.tasks.values()))

    def test_780_last_piece_failure_leaves_it_to_round_notice(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(2)
        self.finish(self.claim())
        t = self.claim()
        self.assertTrue(self.fail(t)["ok"])
        self.assertEqual(self.work["merge_status"], "rejected")
        self.assertEqual(self.piece_notes, [])
        self.assertTrue(any("생략" in m for m in self.piece_log()))
        self.assertNotIn("fail_notice_at", self.idx.tasks[t["task_id"]])

    def test_780_redmine_error_keeps_transition(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(3)
        self.note_result = OSError("connection refused")
        t1 = self.claim()
        self.assertEqual(self.fail(t1), {"ok": True})
        r1 = self.idx.tasks[t1["task_id"]]
        self.assertEqual(r1["status"], "failed")
        self.assertIn("예외", r1["fail_notice_error"])
        self.note_result = False
        t2 = self.claim()
        self.assertEqual(self.fail(t2), {"ok": True})
        r2 = self.idx.tasks[t2["task_id"]]
        self.assertEqual(r2["status"], "failed")
        self.assertIn("노트 실패", r2["fail_notice_error"])
        self.assertEqual(self.work["merge_status"], "in_progress")
        self.assertNotIn("termination_required", self.work)
        # 실패도 기록이 남았으므로 재전송하지 않는다 (t2 의 실패 시도 1건만 있다)
        self.assertEqual(len(self.piece_notes), 1)
        self.note_result = True
        self.assertFalse(C._notify_piece_failed_async(self.idx, t1["task_id"]))
        self.assertFalse(C._notify_piece_failed_async(self.idx, t2["task_id"]))
        self.assertEqual(len(self.piece_notes), 1)

    def test_780_preparation_error_keeps_transition(self):
        self.work["redmine_issue_id"] = 123
        self.tasks(2)
        t = self.claim()
        with patch.object(C, "_notify_piece_failed", side_effect=RuntimeError("boom")):
            self.assertEqual(self.fail(t), {"ok": True})
        self.assertEqual(self.idx.tasks[t["task_id"]]["status"], "failed")
        self.assertTrue(any("준비 예외" in m for m in self.piece_log()))

    def test_780_without_registration_issue_creates_nothing(self):
        self.tasks(2)
        t = self.claim()
        self.assertTrue(self.fail(t)["ok"])                           # _no_new_issue 가 지킨다
        self.assertEqual(self.piece_notes, [])
        self.assertIn("등재 이슈 없음", self.idx.tasks[t["task_id"]]["fail_notice_error"])

    def test_stale_round_callback_is_ignored(self):
        self.work["round"] = 2
        C._record_notification_outcome(self.idx, self.wid, 1, error="old notice")
        self.assertNotIn("notification_error", self.work)


if __name__ == "__main__":
    unittest.main()
