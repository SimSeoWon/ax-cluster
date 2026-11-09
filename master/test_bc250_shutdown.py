"""master.test_bc250_shutdown — BC-250 전원 종료 계약 및 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from unittest.mock import MagicMock, patch

from master.infra.bc250_shutdown import (
    ALLOWED_TARGETS,
    DEFAULT_TARGET,
    FORBIDDEN_TARGETS,
    PreflightCheckError,
    ShutdownError,
    TargetRefusalError,
    check_broker_inflight,
    check_queue,
    check_remote_processes,
    execute_shutdown,
    main,
    run_preflight_checks,
    shutdown,
    validate_target,
    verify_shutdown,
)


class TestTargetContract(unittest.TestCase):
    """비접촉 계약 검증: 오직 .43만 허용되며, .2, .33, .57 및 기타 노드는 거절된다."""

    def test_allowed_targets(self):
        for target in ("192.168.0.43", "bc250-1", "bc250", "43", ".43", None):
            self.assertEqual(validate_target(target), DEFAULT_TARGET)

    def test_forbidden_targets(self):
        for target in FORBIDDEN_TARGETS:
            with self.subTest(target=target):
                with self.assertRaises(TargetRefusalError):
                    validate_target(target)

    def test_arbitrary_unauthorized_target(self):
        for target in ("192.168.0.99", "random-host", "10.0.0.1"):
            with self.subTest(target=target):
                with self.assertRaises(TargetRefusalError):
                    validate_target(target)


class TestPreflightChecks(unittest.TestCase):
    """사전 점검 로직 검증: 큐 활성 작업, 브로커 inflight, 원격 프로세스 검출."""

    def test_check_queue_blocks_active_tasks(self):
        status_data = {
            "tasks": [
                {"task_id": "t1", "status": "claimed", "worker_id": "192.168.0.43"},
            ],
            "works": [],
        }
        with self.assertRaises(PreflightCheckError) as ctx:
            check_queue(status_data)
        self.assertIn("활성 태스크 1건 존재", str(ctx.exception))

    def test_check_queue_passes_closed_tasks(self):
        status_data = {
            "tasks": [
                {"task_id": "t1", "status": "verified", "worker_id": "192.168.0.43"},
                {"task_id": "t2", "status": "cancelled", "assignee": "192.168.0.43"},
                {"task_id": "t3", "status": "claimed", "worker_id": "192.168.0.2"},  # .2는 .43이 아님
            ],
            "works": [],
        }
        res = check_queue(status_data)
        self.assertTrue(any(".43 대상 활성 태스크 0건" in r for r in res))

    def test_check_broker_inflight_blocks_busy(self):
        status_data = {
            "endpoints": [
                {"name": "bc250", "host": "192.168.0.43:11434", "inflight": 2},
                {"name": "rtx3060", "host": "192.168.0.2:11434", "inflight": 0},
            ]
        }
        with self.assertRaises(PreflightCheckError) as ctx:
            check_broker_inflight(status_data)
        self.assertIn("inflight 작업 진행 중", str(ctx.exception))

    def test_check_broker_inflight_passes_idle(self):
        status_data = {
            "endpoints": [
                {"name": "bc250", "host": "192.168.0.43:11434", "inflight": 0},
                {"name": "rtx3060", "host": "192.168.0.2:11434", "inflight": 5},
            ]
        }
        res = check_broker_inflight(status_data)
        self.assertTrue(any("BC-250 엔드포인트 inflight 0건" in r for r in res))

    def test_check_remote_processes_detects_worker(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "1234 python3 /home/sim/worker.py\n"
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(PreflightCheckError) as ctx:
            check_remote_processes("192.168.0.43", runner=runner)
        self.assertIn("작업 프로세스 1건 실행 중", str(ctx.exception))

    def test_check_remote_processes_clean(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "9999 bash\n"  # 셸 세션만 있는 경우 제외
        runner = MagicMock(return_value=mock_proc)

        res = check_remote_processes("192.168.0.43", runner=runner)
        self.assertTrue(any("잔여 작업 프로세스 0건" in r for r in res))


class TestExecutionAndVerify(unittest.TestCase):
    """전원 종료 및 단절 검증 로직 테스트."""

    def test_dry_run_does_not_execute(self):
        runner = MagicMock()
        res = execute_shutdown("192.168.0.43", dry_run=True, runner=runner)
        self.assertTrue(res["dry_run"])
        runner.assert_not_called()
        self.assertIn("sudo -n systemctl poweroff", res["command"])

    def test_execute_calls_poweroff(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        runner = MagicMock(return_value=mock_proc)

        res = execute_shutdown("192.168.0.43", dry_run=False, runner=runner)
        self.assertTrue(res["ok"])
        runner.assert_called_once()
        called_cmd = runner.call_args[0][0]
        self.assertIn("sudo -n systemctl poweroff", called_cmd)

    def test_verify_shutdown_detects_disconnect(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 255  # Connection closed
        runner = MagicMock(return_value=mock_proc)

        verified = verify_shutdown("192.168.0.43", timeout=5, interval=0.1, runner=runner)
        self.assertTrue(verified)

    def test_verify_shutdown_times_out(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0  # 여전히 연결됨
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(ShutdownError):
            verify_shutdown("192.168.0.43", timeout=1, interval=0.1, runner=runner)


class TestCli(unittest.TestCase):
    """CLI 반환 코드 검증."""

    def test_cli_target_refusal(self):
        rc = main(["--target", "192.168.0.2"])
        self.assertEqual(rc, 3)

    def test_cli_dry_run_success(self):
        dummy_status = {
            "tasks": [],
            "works": [],
            "endpoints": [{"name": "bc250", "host": "192.168.0.43:11434", "inflight": 0}],
        }
        with patch("master.infra.bc250_shutdown.check_queue", return_value=["ok"]), \
             patch("master.infra.bc250_shutdown.check_broker_inflight", return_value=["ok"]), \
             patch("master.infra.bc250_shutdown.check_remote_processes", return_value=["ok"]):
            rc = main(["--dry-run"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
