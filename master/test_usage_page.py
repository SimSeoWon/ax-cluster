"""[DOC] 화면 조각 검사 골조. 주입 보고서만 사용하며 집계 조각을 구현하지 않는다."""
import unittest

from master.webui import usage_page


def _report(**changes):
    report = {
        "period": "daily",
        "start": "2026-09-01",
        "end": "2026-09-03",
        "project": "AXCluster",
        "family": "",
        "source": "dispatch",
        "timezone": "Asia/Seoul",
        "generated_at": "2026-09-04T12:00:00+09:00",
        "projects": ["AXCluster", "Game"],
        "warnings": ["측정 토큰은 input/cache/output을 중복 없이 합산한다."],
        "totals": {
            "calls": 3, "measured_calls": 2, "unmeasured_calls": 1,
            "failed_calls": 1, "tokens": 42, "input_tokens": 20,
            "output_tokens": 17, "cache_read": 5, "cache_create": 0,
            "reasoning_tokens": 3, "issues": 1, "unlinked_calls": 1,
        },
        "buckets": [
            {"date": "2026-09-01", "family": "claude", "calls": 2,
             "measured_calls": 2, "unmeasured_calls": 0, "failed_calls": 1,
             "tokens": 42},
            {"date": "2026-09-02", "family": "gemini", "calls": 1,
             "measured_calls": 0, "unmeasured_calls": 1, "failed_calls": 0,
             "tokens": None},
        ],
        "models": [
            {"family": "claude", "model": "claude-sonnet-4-5", "calls": 2,
             "measured_calls": 2, "unmeasured_calls": 0, "failed_calls": 1,
             "tokens": 42},
            {"family": "gemini", "model": "gemini-2.5-pro", "calls": 1,
             "measured_calls": 0, "unmeasured_calls": 1, "failed_calls": 0,
             "tokens": None},
        ],
        "issues": [
            {"issue_id": 716, "title": "사용량 화면", "project": "AXCluster",
             "work_ids": ["usage-page"], "families": ["claude", "gemini"],
             "calls": 2, "measured_calls": 1, "unmeasured_calls": 1,
             "failed_calls": 1, "tokens": 42,
             "last_at": "2026-09-02T09:30:00+09:00"},
        ],
    }
    report.update(changes)
    return report


def _text(report):
    rendered = usage_page.render(report)
    assert isinstance(rendered, bytes)
    return rendered.decode("utf-8")


class UsagePageTests(unittest.TestCase):
    def test_filters_chart_models_and_issue_links(self):
        body = _text(_report())

        self.assertIn('lang="ko"', body)
        for label in ("일간", "주간", "월간", "프로젝트", "모델", "작업 실행", "대화 세션"):
            self.assertIn(label, body)
        for value in ("daily", "weekly", "monthly", "dispatch", "session"):
            self.assertIn(value, body)
        self.assertIn("/usage", body)
        self.assertTrue("<svg" in body or "<canvas" in body)
        self.assertIn("그래프 대체 표", body)
        self.assertIn("2026-09-01", body)
        self.assertIn("claude-sonnet-4-5", body)
        self.assertIn("gemini-2.5-pro", body)
        self.assertIn("http://192.168.0.57:8080/issues/716", body)
        self.assertIn("사용량 화면", body)
        self.assertIn("측정 토큰", body)
        self.assertNotIn("usage-page", body)  # 내부 work id는 화면 정보가 아니다.

    def test_zero_unmeasured_and_empty_data(self):
        zero = _report(
            totals={"calls": 2, "measured_calls": 1, "unmeasured_calls": 1,
                    "failed_calls": 0, "tokens": 0, "input_tokens": 0,
                    "output_tokens": 0, "cache_read": 0, "cache_create": 0,
                    "reasoning_tokens": 0, "issues": 0, "unlinked_calls": 1},
            buckets=[],
            models=[{"family": "local", "model": "qwen", "calls": 1,
                     "measured_calls": 1, "unmeasured_calls": 0,
                     "failed_calls": 0, "tokens": 0},
                    {"family": "unknown", "model": "모델 미상", "calls": 1,
                     "measured_calls": 0, "unmeasured_calls": 1,
                     "failed_calls": 0, "tokens": None}],
            issues=[],
        )
        body = _text(zero)
        self.assertIn(">0<", body)
        self.assertIn("미계측", body)
        self.assertIn("부분", body)
        self.assertIn("미연결", body)
        self.assertIn("기록 없음", body)
        self.assertIn("합산", body)

        empty = _report(
            source="session", project="", projects=[], warnings=[],
            totals={"calls": 0, "measured_calls": 0, "unmeasured_calls": 0,
                    "failed_calls": 0, "tokens": None, "input_tokens": 0,
                    "output_tokens": 0, "cache_read": 0, "cache_create": 0,
                    "reasoning_tokens": 0, "issues": 0, "unlinked_calls": 0},
            buckets=[], models=[], issues=[],
        )
        empty_body = _text(empty)
        self.assertIn("기록 없음", empty_body)
        self.assertIn("일감", empty_body)
        self.assertIn("연결", empty_body)

    def test_untrusted_strings_are_escaped(self):
        attack = '<script>alert("x")</script>'
        report = _report(
            project=attack,
            projects=[attack],
            warnings=[attack + "</script>"],
            models=[{"family": "unknown", "model": attack, "calls": 1,
                     "measured_calls": 1, "unmeasured_calls": 0,
                     "failed_calls": 0, "tokens": 1}],
            issues=[{"issue_id": 7, "title": attack, "project": attack,
                     "work_ids": [], "families": ["unknown"], "calls": 1,
                     "measured_calls": 1, "unmeasured_calls": 0,
                     "failed_calls": 0, "tokens": 1, "last_at": attack}],
        )
        body = _text(report)
        self.assertNotIn(attack, body)
        self.assertNotIn("</script></script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertIn("&quot;x&quot;", body)

        seen = {}

        def loader(**kwargs):
            seen.update(kwargs)
            return report

        status, raw = usage_page.page({"project": attack, "period": "daily"}, loader=loader)
        self.assertEqual(200, status)
        self.assertNotIn(attack, raw.decode("utf-8"))
        self.assertEqual(attack, seen["project"])

    def test_loader_parameters_and_safe_errors(self):
        seen = {}

        def loader(**kwargs):
            seen.update(kwargs)
            return _report(**kwargs)

        query = {"project": "AXCluster", "period": "weekly", "start": "2026-08-01",
                 "end": "2026-09-01", "family": "codex", "source": "session",
                 "projects_root": "/tmp/secret", "extra": "ignored"}
        status, raw = usage_page.page(query, loader=loader)
        self.assertEqual(200, status)
        self.assertIsInstance(raw, bytes)
        self.assertEqual(
            {"project": "AXCluster", "period": "weekly", "start": "2026-08-01",
             "end": "2026-09-01", "family": "codex", "source": "session"},
            seen,
        )

        def invalid(**_kwargs):
            raise ValueError("bad <period>")

        status, raw = usage_page.page({"period": "bad"}, loader=invalid)
        text = raw.decode("utf-8")
        self.assertEqual(400, status)
        self.assertIn("잘못", text)
        self.assertNotIn("bad <period>", text)

        secret = "/home/sim/private/token.json"

        def unreadable(**_kwargs):
            raise OSError(secret)

        status, raw = usage_page.page({}, loader=unreadable)
        text = raw.decode("utf-8")
        self.assertEqual(503, status)
        self.assertIn("사용량", text)
        self.assertNotIn(secret, text)
        self.assertNotIn("OSError", text)


if __name__ == "__main__":
    unittest.main()
