"""#840 quota 전용 생성 사슬. 실제 CLI·브로커 호출 없이 실행한다."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.work import llm_policy as P


class PolicyTests(unittest.TestCase):
    def test_successive_quota_opens_claude_then_local(self):
        attempts = []
        seen = []
        for _ in range(4):
            lane = P.next_lane(attempts, local_model="gemma4:e4b")
            seen.append(lane)
            attempts.append({"lane": lane, "kind": "quota"})
        self.assertEqual(seen, ["agy", "codex", "claude", "gemma4:e4b"])
        self.assertIsNone(P.next_lane(attempts, local_model="gemma4:e4b"))

    def test_general_or_gate_failure_keeps_last_two_closed(self):
        for failure in ("error", "format", "facts"):
            with self.subTest(failure=failure):
                attempts = [{"lane": "agy", "kind": failure}]
                self.assertEqual(P.next_lane(attempts, local_model="local"), "codex")
                attempts.append({"lane": "codex", "kind": "quota"})
                self.assertIsNone(P.next_lane(attempts, local_model="local"))
                self.assertFalse(P.eligible("claude", attempts))
                self.assertFalse(P.eligible("local", attempts))

    def test_write_and_success_stop_every_further_call(self):
        for kind in ("write", "success"):
            self.assertIsNone(P.next_lane([{"lane": "agy", "kind": kind}], local_model="local"))

    def test_cloud_only_and_direct_local_do_not_bypass_policy(self):
        attempts = [{"lane": n, "kind": "quota"} for n in P.CLOUD_LANES]
        self.assertIsNone(P.next_lane(attempts, local_model="local", allow_local=False))
        self.assertFalse(P.eligible("local", []))
        self.assertFalse(P.eligible("claude", []))
        self.assertFalse(P.eligible("codex", []))

    def test_only_error_channel_with_positive_exhaustion_evidence_is_quota(self):
        for text in ("429 Too many requests, retry later", "quota exhausted", "quota exceeded",
                     "You've hit your session limit", "usage limit reached", "RESOURCE_EXHAUSTED"):
            self.assertEqual(P.classify_failure(text), "quota", text)
        for text in ("unknown quota field", "quota parser unavailable", "line 429 invalid",
                     "HTTP 503 capacity unavailable", "OAuth expired", "timeout"):
            self.assertEqual(P.classify_failure(text), "error", text)
        for kind in ("facts", "format", "write"):
            self.assertEqual(P.classify_failure("quota exhausted", kind=kind), kind)


if __name__ == "__main__":
    unittest.main()
