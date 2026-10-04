"""[DOC] 화면 조각 검사 골조. 주입 보고서만 사용하며 집계 조각을 구현하지 않는다."""
import unittest

import sys
from pathlib import Path

# 통합 검사는 스크립트로 단독 실행한다(`tests/integration/checks.json`) — 저장소 루트를 경로에 둔다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
        self.assertIn("올바르지", text)
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



def _models(*rows):
    return [{"family": f, "model": m, "calls": 1, "measured_calls": 1, "unmeasured_calls": 0,
             "failed_calls": 0, "tokens": t} for f, m, t in rows]


class UsagePieTests(unittest.TestCase):
    """모델 계열별 토큰 비율 도넛 — 언제나 모두 보기 기준 (사용자 결정 2026-10-04)."""

    def test_slices_percent_and_tokens(self):
        pie = _report(source="all", models=_models(("claude", "a", 300), ("claude", "b", 100),
                                                   ("codex", "c", 600), ("gemini", "g", None)))
        body = _text(pie)                               # all·전체 계열이면 같은 보고서를 다시 쓴다
        self.assertIn("모델 계열별 토큰 비율 — 모두 보기 기준", body)
        self.assertIn("도넛 대체 표", body)
        self.assertIn(">40.0%<", body)                  # claude 400/1000
        self.assertIn(">60.0%<", body)
        self.assertIn(">400<", body)
        self.assertIn(">1,000<", body)
        self.assertIn("#d2a8ff", body)                  # 기존 계열 색 그대로
        self.assertEqual(body.count("stroke-dasharray"), 2)   # 미계측 gemini 는 조각이 없다

    def test_single_family_full_circle_and_empty(self):
        one = _text(_report(source="all", models=_models(("codex", "c", 5))))
        self.assertIn(">100.0%<", one)
        self.assertIn('stroke-dasharray="439.82 439.82"', one)   # 틈 없이 온전한 원(2πr, r=70)
        for models in ([], _models(("claude", "a", None)), _models(("claude", "a", 0))):
            body = _text(_report(source="all", models=models))
            self.assertIn("측정 토큰 기록이 없어", body)
            self.assertNotIn("stroke-dasharray", body)
        body = _text(_report())                         # dispatch 보고서만 주면 자료 없음
        self.assertIn("비율 자료를 읽지 못했다", body)

    def test_page_reloads_with_source_all_and_reuses_when_already_all(self):
        calls = []

        def loader(**kwargs):
            calls.append(("main", kwargs))
            return _report(**kwargs)

        def pie_loader(**kwargs):
            calls.append(("pie", kwargs))
            return _report(**kwargs, models=_models(("local", "qwen", 9)))

        query = {"project": "AXCluster", "period": "weekly", "start": "2026-08-01",
                 "end": "2026-09-01", "family": "codex", "source": "session"}
        status, raw = usage_page.page(query, loader=loader, pie_loader=pie_loader)
        self.assertEqual(200, status)
        self.assertEqual([c[0] for c in calls], ["main", "pie"])
        self.assertEqual(calls[1][1], {**query, "source": "all", "family": ""})
        self.assertIn(">100.0%<", raw.decode("utf-8"))
        calls.clear()
        usage_page.page({**query, "source": "all", "family": ""}, loader=loader,
                        pie_loader=pie_loader)
        self.assertEqual([c[0] for c in calls], ["main"])          # 이미 모두 보기 — 재사용

        def broken(**_kwargs):
            raise OSError("/home/sim/secret")
        status, raw = usage_page.page(query, loader=loader, pie_loader=broken)
        text = raw.decode("utf-8")
        self.assertEqual(200, status)                   # 도넛 실패는 화면을 막지 않는다
        self.assertIn("비율 자료를 읽지 못했다", text)
        self.assertNotIn("/home/sim/secret", text)

    def test_pie_strings_escaped(self):
        attack = '<script>alert("x")</script>'
        pie = _report(source="all", models=_models((attack, attack, 3)))
        body = _text(pie)
        self.assertNotIn(attack, body)
        self.assertIn(">100.0%<", body)                 # 모르는 계열은 미상으로 접힌다
        self.assertIn("미상", body)

if __name__ == "__main__":
    unittest.main()
