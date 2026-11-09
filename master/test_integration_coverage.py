"""master.test_integration_coverage — 공식 통합 검사(checks.json) 등록 누락 방지 검사 (`#929`).

`master/test_*.py` 중 공식 통합 검사(`tests/integration/checks.json`)에 등록되지 않은 파일이 있으면 실패한다.
고의로 제외할 파일은 `EXCLUDED_FROM_INTEGRATION`에 명시해야 한다.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# 공식 통합 검사(독립 프로세스 실행)에서 제외된 기존 테스트 파일 목록 (사유: DB/Docker 의존, 임시 픽스처 등)
EXCLUDED_FROM_INTEGRATION = {
    "master/test_agy_trace.py",
    "master/test_home_guides.py",
    "master/test_issue_flow.py",
    "master/test_issue_infra.py",
    "master/test_issue_link.py",
    "master/test_issue_lock.py",
    "master/test_issue_progress.py",
    "master/test_issue_review.py",
    "master/test_issue_track.py",
    "master/test_notice_recovery.py",
    "master/test_nowork.py",
    "master/test_ontology.py",
    "master/test_ontology_proxy.py",
    "master/test_ontology_python.py",
    "master/test_plan_block.py",
    "master/test_plan_build.py",
    "master/test_plan_start.py",
    "master/test_plan_state.py",
    "master/test_plan_steps.py",
    "master/test_plan_tools.py",
    "master/test_redmine_completion_gate.py",
    "master/test_review_range.py",
    "master/test_rounds.py",
    "master/test_sandbox.py",
    "master/test_setup_host.py",
    "master/test_task_submission.py",
}


class TestIntegrationCoverage(unittest.TestCase):
    """checks.json 커버리지 검증."""

    def test_all_master_tests_registered_or_excluded(self):
        checks_file = _REPO / "tests" / "integration" / "checks.json"
        self.assertTrue(checks_file.is_file(), f"checks.json 파일 부재: {checks_file}")

        checks = json.loads(checks_file.read_text(encoding="utf-8"))
        registered_paths = {c["path"] for c in checks}

        master_tests = {
            f"master/{p.name}"
            for p in (_REPO / "master").glob("test_*.py")
            if p.is_file()
        }

        unaccounted = master_tests - registered_paths - EXCLUDED_FROM_INTEGRATION
        self.assertEqual(
            unaccounted,
            set(),
            f"공식 통합 검사(checks.json) 또는 제외 목록에 등록되지 않은 테스트 {len(unaccounted)}건 발견: {sorted(unaccounted)}. "
            f"신규 테스트는 checks.json에 등록하거나 제외 목록에 사유와 함께 추가해야 합니다.",
        )

    def test_bc250_shutdown_is_registered(self):
        checks_file = _REPO / "tests" / "integration" / "checks.json"
        checks = json.loads(checks_file.read_text(encoding="utf-8"))
        registered_paths = {c["path"] for c in checks}
        self.assertIn("master/test_bc250_shutdown.py", registered_paths)


if __name__ == "__main__":
    unittest.main()
