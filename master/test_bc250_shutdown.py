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
    is_bc250_worker,
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

    def test_force_does_not_bypass_target_refusal(self):
        """--force 여도 대상 노드 거절은 절대 해제되지 않는다."""
        for forbidden in ("192.168.0.2", "192.168.0.33", "192.168.0.57", "unknown-node"):
            with self.subTest(target=forbidden):
                with self.assertRaises(TargetRefusalError):
                    shutdown(target=forbidden, force=True, dry_run=True)


class TestWorkerIdentification(unittest.TestCase):
    """작업자 식별자 (.43 / BC-250) 오탐 방지 테스트."""

    def test_is_bc250_worker_distinguishes_143_from_43(self):
        self.assertFalse(is_bc250_worker("worker-143"))
        self.assertFalse(is_bc250_worker("192.168.0.143"))
        self.assertFalse(is_bc250_worker("node143"))
        self.assertFalse(is_bc250_worker("430"))
        self.assertFalse(is_bc250_worker(None))
        self.assertFalse(is_bc250_worker(""))

        self.assertTrue(is_bc250_worker("worker-43"))
        self.assertTrue(is_bc250_worker("worker_43"))
        self.assertTrue(is_bc250_worker("43"))
        self.assertTrue(is_bc250_worker(".43"))
        self.assertTrue(is_bc250_worker("192.168.0.43"))
        self.assertTrue(is_bc250_worker("192.168.0.43:11434"))
        self.assertTrue(is_bc250_worker("bc250"))
        self.assertTrue(is_bc250_worker("bc250-1"))
        self.assertTrue(is_bc250_worker("BC-250"))


class TestPreflightChecks(unittest.TestCase):
    """사전 점검 로직 검증: 큐 활성 작업, 브로커 inflight, 원격 프로세스 검출 및 fail-open 차단."""

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
                {"task_id": "t3", "status": "claimed", "worker_id": "192.168.0.2"},
            ],
            "works": [],
        }
        res = check_queue(status_data)
        self.assertTrue(any(".43 대상 활성 태스크 0건" in r for r in res))

    def test_check_queue_fail_closed_on_missing_or_invalid_tasks(self):
        """tasks가 None이거나 list가 아니면 fail-open 하지 않고 PreflightCheckError 발생."""
        for invalid in (None, "not-a-list", 123, {"a": 1}):
            with self.subTest(invalid=invalid):
                status_data = {"tasks": invalid, "works": []}
                with self.assertRaises(PreflightCheckError) as ctx:
                    check_queue(status_data)
                self.assertIn("tasks 필드가 누락되었거나 목록이 아닙니다", str(ctx.exception))

        # tasks 키 자체가 없는 경우
        with self.assertRaises(PreflightCheckError):
            check_queue({"works": []})

    def test_check_queue_does_not_false_positive_worker_143(self):
        """worker-143은 .43으로 오인되어 차단되지 않아야 함."""
        status_data = {
            "tasks": [
                {"task_id": "t1", "status": "claimed", "worker_id": "worker-143"},
                {"task_id": "t2", "status": "claimed", "worker_id": "192.168.0.143"},
            ],
            "works": [],
        }
        res = check_queue(status_data)
        self.assertTrue(any(".43 대상 활성 태스크 0건" in r for r in res))

    def test_check_queue_blocks_worker_43(self):
        status_data = {
            "tasks": [
                {"task_id": "t1", "status": "claimed", "worker_id": "worker-43"},
            ],
            "works": [],
        }
        with self.assertRaises(PreflightCheckError):
            check_queue(status_data)

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

    def test_check_broker_inflight_fail_closed_on_missing_or_invalid_endpoints(self):
        """endpoints가 None이거나 list가 아니면 통과하지 않고 PreflightCheckError 발생."""
        for invalid in (None, "not-a-list", 123, {"a": 1}):
            with self.subTest(invalid=invalid):
                status_data = {"endpoints": invalid}
                with self.assertRaises(PreflightCheckError) as ctx:
                    check_broker_inflight(status_data)
                self.assertIn("endpoints 필드가 누락되었거나 목록이 아닙니다", str(ctx.exception))

        with self.assertRaises(PreflightCheckError):
            check_broker_inflight({})

    def test_check_remote_processes_detects_worker(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "1234 python3 /home/sim/worker.py\n"
        mock_proc.stderr = ""
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(PreflightCheckError) as ctx:
            check_remote_processes("192.168.0.43", runner=runner)
        self.assertIn("작업 프로세스 1건 실행 중", str(ctx.exception))

    def test_check_remote_processes_clean_with_shell_only(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "9999 bash\n"  # 셸 세션만 있는 경우 제외
        mock_proc.stderr = ""
        runner = MagicMock(return_value=mock_proc)

        res = check_remote_processes("192.168.0.43", runner=runner)
        self.assertTrue(any("잔여 작업 프로세스 0건" in r for r in res))

    def test_check_remote_processes_clean_rc1_no_match(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        runner = MagicMock(return_value=mock_proc)

        res = check_remote_processes("192.168.0.43", runner=runner)
        self.assertTrue(any("잔여 작업 프로세스 0건" in r for r in res))

    def test_check_remote_processes_pgrep_error_rc2(self):
        """pgrep 문법 에러(rc=2) 발생 시 fail-closed 차단."""
        mock_proc = MagicMock()
        mock_proc.returncode = 2
        mock_proc.stdout = ""
        mock_proc.stderr = "pgrep: invalid option"
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(PreflightCheckError) as ctx:
            check_remote_processes("192.168.0.43", runner=runner)
        self.assertIn("원격 프로세스 검사 실패", str(ctx.exception))

    def test_check_remote_processes_rc1_with_stderr(self):
        """rc=1 이어도 stderr가 존재하면 비정상으로 판정하고 PreflightCheckError 발생."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "warning: some unexpected error occurred"
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(PreflightCheckError) as ctx:
            check_remote_processes("192.168.0.43", runner=runner)
        self.assertIn("원격 프로세스 검사 실패", str(ctx.exception))

    def test_check_remote_processes_ssh_failure_rc255(self):
        """SSH 접속 불가(rc=255) 시 조용히 넘기지 않고 PreflightCheckError 발생."""
        mock_proc = MagicMock()
        mock_proc.returncode = 255
        mock_proc.stdout = ""
        mock_proc.stderr = "ssh: connect to host 192.168.0.43: Connection refused"
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(PreflightCheckError) as ctx:
            check_remote_processes("192.168.0.43", runner=runner)
        self.assertIn("원격 프로세스 검사 실패", str(ctx.exception))

    def test_check_remote_processes_runner_exception(self):
        """SSH 호출 중 타임아웃/네트워크 예외 발생 시 PreflightCheckError 발생."""
        runner = MagicMock(side_effect=TimeoutError("SSH connect timed out"))

        with self.assertRaises(PreflightCheckError) as ctx:
            check_remote_processes("192.168.0.43", runner=runner)
        self.assertIn("SSH 접속/실행 예외", str(ctx.exception))


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

    def test_execute_shutdown_failure_raises(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "sudo: a password is required"
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(ShutdownError) as ctx:
            execute_shutdown("192.168.0.43", dry_run=False, runner=runner)
        self.assertIn("전원 종료 명령 실행 실패", str(ctx.exception))

    def test_verify_shutdown_detects_disconnect(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 255  # Connection closed
        runner = MagicMock(return_value=mock_proc)

        verified = verify_shutdown("192.168.0.43", timeout=5, interval=0.01, runner=runner)
        self.assertTrue(verified)

    def test_verify_shutdown_times_out(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0  # 여전히 연결됨
        runner = MagicMock(return_value=mock_proc)

        with self.assertRaises(ShutdownError):
            verify_shutdown("192.168.0.43", timeout=0.05, interval=0.01, runner=runner)

    def test_verify_shutdown_transient_failure_does_not_early_exit(self):
        """1회 일시적 실패 후 다시 정상 연결되면 단절로 보지 않고 루프가 지속되어야 함."""
        # 1회차: SSH 실패, Ping 실패 (1회 실패)
        # 2회차: SSH 성공, Ping 성공 (복구 -> failures 리셋)
        # 3회차+: 계속 성공
        # 타임아웃 도달하여 ShutdownError 발생 검증 (1회 실패로 조기 리턴하지 않음을 증명)
        call_count = 0

        def alternating_runner(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = MagicMock()
            # 1회차 SSH(1) + Ping(2)은 실패, 이후(3+)는 성공
            if call_count <= 2:
                proc.returncode = 255
            else:
                proc.returncode = 0
            return proc

        with self.assertRaises(ShutdownError):
            verify_shutdown(
                "192.168.0.43",
                timeout=0.1,
                interval=0.02,
                runner=alternating_runner,
                consecutive_failures=2,
            )
        self.assertGreaterEqual(call_count, 3)

    def test_verify_shutdown_consecutive_failures_succeeds(self):
        """연속 실패(consecutive_failures >= 2)가 충족되면 단절 성공(True) 반환."""
        call_count = 0

        def fail_after_first_round(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = MagicMock()
            # 첫 1회차(1, 2)는 성공, 이후 연속 실패
            if call_count <= 2:
                proc.returncode = 0
            else:
                proc.returncode = 255
            return proc

        verified = verify_shutdown(
            "192.168.0.43",
            timeout=1.0,
            interval=0.01,
            runner=fail_after_first_round,
            consecutive_failures=2,
        )
        self.assertTrue(verified)

    def test_verify_shutdown_ping_alive_prevents_premature_exit(self):
        """SSH가 실패해도 Ping이 살아있으면 전원 차단으로 오판하지 않음."""
        ssh_runner = MagicMock()
        ssh_proc = MagicMock()
        ssh_proc.returncode = 255  # SSH 끊김
        ssh_runner.return_value = ssh_proc

        ping_runner = MagicMock()
        ping_proc = MagicMock()
        ping_proc.returncode = 0  # Ping은 여전히 응답함
        ping_runner.return_value = ping_proc

        with self.assertRaises(ShutdownError):
            verify_shutdown(
                "192.168.0.43",
                timeout=0.08,
                interval=0.02,
                runner=ssh_runner,
                ping_runner=ping_runner,
                consecutive_failures=2,
            )


class TestShutdownWorkflow(unittest.TestCase):
    """shutdown() 종합 워크플로우: 사전 점검 실패 차단 및 --force 동작 검증."""

    def test_preflight_failure_blocks_execute_shutdown(self):
        """사전 점검 실패 시 실제 전원 종료 명령(execute_shutdown)이 절대 호출되지 않아야 함."""
        runner = MagicMock()
        status_data = {
            "tasks": [
                {"task_id": "t1", "status": "claimed", "worker_id": "192.168.0.43"},
            ],
            "works": [],
            "endpoints": [{"name": "bc250", "host": "192.168.0.43:11434", "inflight": 0}],
        }

        with self.assertRaises(PreflightCheckError):
            shutdown(
                target="192.168.0.43",
                status_fetcher=lambda: status_data,
                runner=runner,
            )

        # poweroff 명령이 호출되지 않았음을 보증
        runner.assert_not_called()

    def test_force_converts_preflight_errors_to_warnings(self):
        """force=True 적용 시 사전 점검 에러가 warnings로 전환되고 종료 단계가 진행됨."""
        status_data = {
            "tasks": [
                {"task_id": "t1", "status": "claimed", "worker_id": "192.168.0.43"},
            ],
            "works": [],
            "endpoints": [{"name": "bc250", "host": "192.168.0.43:11434", "inflight": 0}],
        }

        res = shutdown(
            target="192.168.0.43",
            force=True,
            dry_run=True,
            status_fetcher=lambda: status_data,
        )

        self.assertTrue(res["ok"])
        self.assertTrue(res["dry_run"])
        warnings = res["preflight"]["warnings"]
        self.assertTrue(any("force 무시" in w for w in warnings))

    def test_check_only_does_not_execute(self):
        """check_only=True 시 사전 점검만 수행하고 종료 명령 미실행."""
        runner = MagicMock()
        status_data = {
            "tasks": [],
            "works": [],
            "endpoints": [{"name": "bc250", "host": "192.168.0.43:11434", "inflight": 0}],
        }

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        runner.return_value = mock_proc

        res = shutdown(
            target="192.168.0.43",
            check_only=True,
            status_fetcher=lambda: status_data,
            runner=runner,
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["check_only"])
        # execute_shutdown 명령(sudo -n systemctl poweroff)은 호출되지 않아야 함
        for call in runner.call_args_list:
            cmd = call[0][0]
            self.assertNotIn("poweroff", cmd)


class TestCli(unittest.TestCase):
    """CLI 반환 코드 검증 (대상 거절 rc=3, 점검 실패 rc=1, 종료 실패 rc=2, 성공 rc=0)."""

    def test_cli_target_refusal_returns_3(self):
        self.assertEqual(main(["--target", "192.168.0.2"]), 3)
        self.assertEqual(main(["--target", "192.168.0.57"]), 3)
        self.assertEqual(main(["--target", "localhost"]), 3)

    def test_cli_preflight_failure_returns_1(self):
        with patch("master.infra.bc250_shutdown.run_preflight_checks",
                   side_effect=PreflightCheckError("Active tasks running")):
            rc = main(["--check-only"])
            self.assertEqual(rc, 1)

    def test_cli_shutdown_failure_returns_2(self):
        with patch("master.infra.bc250_shutdown.run_preflight_checks",
                   return_value={"ok": True, "logs": [], "warnings": []}), \
             patch("master.infra.bc250_shutdown.execute_shutdown",
                   side_effect=ShutdownError("SSH poweroff failed")):
            rc = main([])
            self.assertEqual(rc, 2)

    def test_cli_dry_run_success_returns_0(self):
        with patch("master.infra.bc250_shutdown.check_queue", return_value=["ok"]), \
             patch("master.infra.bc250_shutdown.check_broker_inflight", return_value=["ok"]), \
             patch("master.infra.bc250_shutdown.check_remote_processes", return_value=["ok"]):
            rc = main(["--dry-run"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
