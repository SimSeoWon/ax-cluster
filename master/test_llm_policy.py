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


    def test_excluded_clouds_840_2(self):
        """#840 ② — 앞 재시도에서 형식·사실에 진 클라우드는 빼고, 그 자리는 「건너뜀」(quota 아님)."""
        self.assertEqual(P.next_lane([], excluded=["agy"]), "codex")
        self.assertIsNone(P.next_lane([], excluded=["agy", "codex"], local_model="local"),
                          "둘 다 졌으면 claude·로컬을 열지 않는다")
        self.assertFalse(P.eligible("claude", [{"lane": "codex", "kind": "quota"}], excluded=["agy"]),
                         "진 것은 quota 가 아니다 — claude 조건 불충족")
        self.assertEqual(P.next_lane([], excluded=["codex"]), "agy")
        self.assertIsNone(P.next_lane([{"lane": "agy", "kind": "quota"}], excluded=["codex"],
                                      local_model="local"))
        self.assertEqual(P.next_lane([{"lane": "agy", "kind": "quota"}, {"lane": "codex", "kind": "quota"}],
                                     excluded=["claude"], local_model="local"), None,
                         "claude 가 졌고 둘이 quota 여도 로컬은 세 클라우드 quota 조건")

    def test_lane_failure_tag_roundtrip(self):
        f = P.add_lane_failure([], "agy", "facts")
        f = P.add_lane_failure(f, "codex:gpt-5", "format")
        f = P.add_lane_failure(f, "agy", "format")            # 같은 클라우드는 한 번
        f = P.add_lane_failure(f, "qwen2.5-coder:14b", "facts")  # 로컬은 나르지 않는다
        f = P.add_lane_failure(f, "claude", "quota")          # 형식·사실만
        tag = P.format_lane_failures(f)
        self.assertEqual(tag, "[lane-fail:agy:facts,codex:format]")
        self.assertEqual(P.parse_lane_failures(f"[fp:abc] [kind:code] {tag} 층2 이 막았다"), f)
        self.assertEqual(P.parse_lane_failures("표지 없음"), [])
        self.assertEqual(P.parse_lane_failures("[lane-fail:evil:facts,agy:quota,codex:facts]"),
                         [{"lane": "codex", "kind": "facts"}])
        self.assertEqual(P.format_lane_failures([]), "")

if __name__ == "__main__":
    unittest.main()
