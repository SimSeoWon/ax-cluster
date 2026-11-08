"""#830 model policy regression: injected metadata/processes; no paid calls."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master import agy_models as A


class ModelPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ax-agy-policy-test-")
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state.json"
        self.now = 1000.0
        self.calls = []
        self.catalog_calls = []
        self.answers = []
        self.labels = {
            A.DEFAULT_MODEL: "Gemini 3.8 Flash (Medium)",
            "gemini-3.8-flash-low": "Gemini 3.8 Flash (Low)",
            "gemini-4-argon-low": "Gemini 4 Argon (Low)",
            "claude-opus-5-5-medium": "Claude Opus 5.5 (Medium)",
            "gpt-oss-120b-medium": "GPT OSS 120B (Medium)",
        }

    def catalog(self, exe, timeout):
        self.catalog_calls.append((exe, timeout))
        return "\n".join(f"{key}\t{value}" for key, value in self.labels.items())

    def command(self, selected, log):
        return ["fake-agy", "--model", selected, "--log-file", log, "-p", "BRIEF"]

    def runner(self, cmd, *, timeout):
        self.calls.append((cmd, timeout))
        selected = cmd[cmd.index("--model") + 1]
        spec = self.answers.pop(0) if self.answers else {}
        label = spec.get("label", self.labels[selected])
        if label is not None:
            Path(cmd[cmd.index("--log-file") + 1]).write_text(
                f'Propagating selected model override to backend: label="{label}"\n'
                + spec.get("log", ""), encoding="utf-8")
        body = {"status": spec.get("status", "SUCCESS"), "response": "OK",
                "usage": {"input_tokens": 3, "output_tokens": 1}}
        if "error" in spec:
            body["error"] = spec["error"]
        if "model" in spec:
            body["model"] = spec["model"]
        raw = json.dumps(body)
        return (None if spec.get("rc", 0) else raw,
                spec.get("why", ""), spec.get("rc", 0), raw)

    def run_model(self, **kw):
        return A.execute("fake-agy", self.command, self.runner, timeout=20,
                         state_path=self.state, catalog_runner=self.catalog,
                         clock=lambda: self.now, **kw)

    def test_default_explicit_and_request_local_log(self):
        with patch.dict(os.environ, {"AGY_MODEL": "gemini-4-argon-high"}):
            first = self.run_model()
            second = self.run_model()
        self.assertEqual((first.requested_model, first.actual_model, first.model_source),
                         (A.DEFAULT_MODEL, A.DEFAULT_MODEL, "log"))
        self.assertFalse(first.why)
        self.assertFalse(second.why)
        self.assertEqual(len(self.calls), 2)
        self.assertNotEqual(self.calls[0][0][4], self.calls[1][0][4])
        self.assertEqual(len(self.catalog_calls), 1)

    def test_catalog_expiry_and_executable_identity(self):
        self.run_model()
        self.now += A.CATALOG_TTL
        self.run_model()
        self.assertEqual(len(self.catalog_calls), 2)
        A.execute("other-agy", self.command, self.runner, timeout=20,
                  state_path=self.state, catalog_runner=self.catalog, clock=lambda: self.now)
        self.assertEqual(len(self.catalog_calls), 3)

    def test_alias_missing_and_non_gemini_are_blocked_before_generation(self):
        for model in ("Gemini 3.8 Flash (Medium)", "gemini-3.6-flash-high",
                      "claude-opus-5-5-medium", "gpt-oss-120b-medium"):
            with self.subTest(model=model):
                result = self.run_model(model=model)
                self.assertTrue(result.why)
        self.assertEqual(self.calls, [])

    def test_argon_requires_both_manual_flags_and_no_fallback(self):
        for kw in ({"model": "gemini-4-argon-low"}, {"allow_argon": True,
                   "fallback_models": ("gemini-4-argon-low",)},
                   {"model": "gemini-4-argon-low", "allow_argon": True,
                    "fallback_models": (A.DEFAULT_MODEL,)}):
            self.assertTrue(self.run_model(**kw).why)
        self.assertEqual(self.calls, [])
        result = self.run_model(model="gemini-4-argon-low", allow_argon=True)
        self.assertFalse(result.why)
        self.assertEqual(result.actual_model, "gemini-4-argon-low")

    def test_cooldown_note_and_read(self):
        """`#920` — 한도 응답을 남기고 읽는다. 리셋 문구가 없으면 기본 쿨다운."""
        self.assertEqual(A.cooldown_left("gemini-4-argon-medium", state_path=self.state, clock=lambda: self.now), 0)
        A.note_limit("gemini-4-argon-medium", "429 quota exceeded", state_path=self.state, clock=lambda: self.now)
        left = A.cooldown_left("gemini-4-argon-medium", state_path=self.state, clock=lambda: self.now)
        self.assertGreater(left, 0)
        self.assertEqual(A.cooldown_left(A.DEFAULT_MODEL, state_path=self.state, clock=lambda: self.now), 0)

    def test_catalog_argon_label_blocked_before_generation(self):
        self.labels[A.DEFAULT_MODEL] = "Gemini 4 Argon (Medium)"
        self.assertTrue(self.run_model().why)
        self.assertEqual(self.calls, [])

    def test_actual_model_mismatch_rejects_output_without_fallback(self):
        self.answers = [{"label": "Gemini 4 Argon (Medium)"}]
        result = self.run_model(fallback_models=("gemini-3.8-flash-low",))
        self.assertIn("mismatch", result.why)
        self.assertEqual(result.actual_model, "gemini-4-argon-medium")
        self.assertEqual(len(self.calls), 1)

    def test_mismatch_with_quota_cannot_fallback_or_poison_requested_model(self):
        self.answers = [{"label": "Gemini 4 Argon (Medium)", "rc": 3,
                         "why": "RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 150h"}]
        result = self.run_model(fallback_models=("gemini-3.8-flash-low",))
        self.assertIn("mismatch", result.why)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn(A.DEFAULT_MODEL, json.loads(self.state.read_text()).get("cooldowns", {}))

    def test_cooldown_is_visible_to_another_process(self):
        self.answers = [{"rc": 3, "why": "RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your subscription to increase your limits."}]
        self.run_model()
        code = '''import sys
from master import agy_models as A
def forbidden(*a, **kw):
    raise AssertionError("generation or catalog must not run during persistent cooldown")
r = A.execute("fake-agy", forbidden, forbidden, timeout=5,
              state_path=sys.argv[1], catalog_runner=forbidden, clock=lambda: 1001.0)
assert "cooldown" in r.why, r
'''
        proc = subprocess.run([sys.executable, "-B", "-c", code, str(self.state)],
                              cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_total_timeout_includes_metadata(self):
        ticks = [100.0]
        def slow_catalog(*args):
            ticks[0] += 21
            return self.catalog(*args)
        with patch.object(A.time, "monotonic", side_effect=lambda: ticks[0]):
            result = A.execute("fake-agy", self.command, self.runner, timeout=20,
                               state_path=self.state, catalog_runner=slow_catalog,
                               clock=lambda: self.now)
        self.assertIn("timeout", result.why)
        self.assertEqual(self.calls, [])

    def test_envelope_model_has_evidence_and_unknown_is_not_invented(self):
        self.answers = [{"label": None, "model": A.DEFAULT_MODEL}, {"label": None}]
        self.assertEqual(self.run_model().model_source, "envelope")
        result = self.run_model()
        self.assertEqual((result.actual_model, result.model_source), ("", ""))

    def test_unknown_actual_model_rejects_output_without_cooldown_or_fallback(self):
        # 사용자 결정(#830): 실제 모델을 증명하지 못하면 출력이 있어도 실패다.
        self.answers = [{"label": None, "log": "RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 2h\n"}]
        result = self.run_model(fallback_models=("gemini-3.8-flash-low",))
        self.assertIn("실제 모델 미상", result.why)
        self.assertIsNone(result.raw)
        self.assertEqual((result.actual_model, result.model_source), ("", ""))
        self.assertEqual(len(result.attempts), 1)
        attempt = result.attempts[0]
        self.assertEqual(attempt["requested_model"], A.DEFAULT_MODEL)
        self.assertIn("실제 모델 미상", attempt["why"])
        self.assertTrue(attempt["raw"])          # 계측(토큰)은 보존한다
        self.assertEqual(len(self.calls), 1)     # 폴백 없음
        state = json.loads(self.state.read_text())
        self.assertNotIn(A.DEFAULT_MODEL, state.get("cooldowns", {}))
        self.assertFalse(self.run_model().why)   # 다음 호출을 막지 않는다
        self.assertEqual(len(self.calls), 2)

    def test_quota_survives_call_and_expires_at_reported_reset(self):
        self.answers = [{"rc": 3, "why": "rc=3: RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 2m 5s"}]
        result = self.run_model()
        self.assertTrue(result.why)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["cooldowns"][A.DEFAULT_MODEL], self.now + 125)
        self.assertIn("cooldown", self.run_model().why)
        self.assertEqual(len(self.calls), 1)
        self.now += 125
        self.assertFalse(self.run_model().why)
        self.assertEqual(len(self.calls), 2)

    def test_default_no_fallback_and_approved_fallback_preserves_attempts(self):
        self.answers = [{"rc": 3, "why": "RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your subscription to increase your limits."}]
        self.assertTrue(self.run_model().why)
        result = self.run_model(fallback_models=("gemini-3.8-flash-low",))
        self.assertFalse(result.why)
        self.assertEqual(result.requested_model, "gemini-3.8-flash-low")
        self.assertEqual(len(result.attempts), 2)
        self.assertIn("skipped", result.attempts[0])
        self.assertEqual(len(self.calls), 2)

    def test_nonquota_failure_does_not_poison_model_availability(self):
        self.answers = [{"rc": 1, "why": "connection closed"}]
        self.assertTrue(self.run_model().why)
        self.assertFalse(self.run_model().why)
        self.assertEqual(len(self.calls), 2)

    def test_metadata_failure_prevents_generation(self):
        self.catalog = lambda *_: "not a model catalog"
        self.assertTrue(self.run_model().why)
        self.assertEqual(self.calls, [])

    # 🔴 `#845` — agy CLI 정상 로그 줄(실측 2026-10-30)은 한도가 아니다
    ROUTINE_LOG = (
        "I1030 18:19:20.896604     236 quota_manager.go:36] doRefreshQuota: skipped (not logged in)\n"
        "I1030 18:19:20.909156       1 server_oauth.go:224] applyAuthResult: email=x, authMethod=consumer, quotaProject=\n"
        "W1018 00:26:24.627900     429 cache.go:163] Failed to refresh cache in background: admin controls not applicable\n")

    def test_routine_log_lines_are_not_a_limit(self):
        self.assertFalse(A._limited(self.ROUTINE_LOG))
        self.assertFalse(A._limited("타임아웃 236.48초\n" + self.ROUTINE_LOG))

    def test_timeout_with_routine_log_does_not_cool_down(self):
        """#845 실측 — 타임아웃이 정상 로그의 quota 로 600초 쿨다운이 됐고, 재시도 둘이 즉시 소진됐다."""
        self.answers = [{"rc": 1, "why": "타임아웃 236.48초", "log": self.ROUTINE_LOG}]
        self.assertTrue(self.run_model().why)
        self.assertNotIn(A.DEFAULT_MODEL, json.loads(self.state.read_text()).get("cooldowns", {}))
        self.assertFalse(self.run_model().why)
        self.assertEqual(len(self.calls), 2)

    def test_real_exhaustion_line_cools_down_until_reported_reset(self):
        line = ("E1018 03:15:04.005814     548 errorreport.go:224] generating and executing: "
                "RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your "
                "subscription to increase your limits. Resets in 150h53m7s.\n")
        self.assertTrue(A._limited(line))
        self.answers = [{"rc": 1, "why": "agy failed rc=1", "log": self.ROUTINE_LOG + line}]
        self.assertTrue(self.run_model().why)
        until = json.loads(self.state.read_text())["cooldowns"][A.DEFAULT_MODEL]
        self.assertEqual(until, self.now + 150 * 3600 + 53 * 60 + 7)

    def test_reset_units_and_bounded_unknown(self):
        self.assertEqual(A.reset_deadline("Resets in ~150h", 10), 540010)
        self.assertEqual(A.reset_deadline("Resets in 1h 20m 3s", 10), 4813)
        self.assertEqual(A.reset_deadline("quota unknown", 10), 10 + A.COOLDOWN_SECONDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
