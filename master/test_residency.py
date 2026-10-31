"""#861: 상주 금지, 관측 실패 구분, 로그인 런처와 안전한 옛 등록 해제."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client.init import residency as R
from master.client import bundle
from master.client import __main__ as cli
from master.client.bundle import HostFacts

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _f(*, windows, ue5="", role="worker", path="/p/NS"):
    return HostFacts(host="h", user="u", path=path, driven="ssh", role=role,
                     os="windows" if windows else "linux", ue5=ue5, checkout_ok=True)


def test_no_combination_can_restore_residency():
    for windows in (True, False):
        for role in ("worker", "requester"):
            for ue5 in ("", "x"):
                f = _f(windows=windows, role=role, ue5=ue5)
                for project, mounted in (("NS", "NS"), ("NS", "Other"), ("NS", "")):
                    for flags in ({}, {"code": True}, {"index_only": True}):
                        state = R.desired_state(project, mounted, f, **flags)
                        check(f"상주 금지 {windows}/{role}/{ue5}/{mounted}/{flags}",
                              state.required is False and "SSH" in state.reason, state)
                check("등록 명령을 만들지 않는다", R.commands("NS", f) == [])
                check("기동 명령을 만들지 않는다", R.ensure_commands("NS", f) == [])
                check("깃발·종료·갱신 명령을 만들지 않는다",
                      R.refresh_commands(f, force=True, pid=42) == [])
                check("옛 상태를 갱신 대상으로 읽지 않는다",
                      not R.needs_refresh({"running": 1, "stale": 1, "busy": 0}))
    check("스탬프 없는 옛 호출도 금지", R.desired_state("NS", "NS").required is False)
    check("blocked_reason도 같은 정책", R.blocked_reason("NS", "NS") == R.DECOMMISSIONED_REASON)


def test_plan_does_not_offer_a_daemon():
    for win in (True, False):
        f = _f(windows=win, ue5="x")
        text = "\n".join(R.plan_lines("NS", f, mounted="NS"))
        check("계획은 폐기 정책을 명시", R.DECOMMISSIONED_REASON in text, text)
        check("계획은 등록·폴링 명령을 안내하지 않음",
              "/sc minute" not in text and "*/5" not in text and "--types" not in text, text)
        check("계획에서 로그인 런처는 Windows만 안내",
              ("AxConductor_NS" in text) == win, text)
        refreshed = "\n".join(R.refresh_plan_lines(f, {"running": 1, "stale": 1}))
        check("구 갱신 계획도 폐기를 안내", R.DECOMMISSIONED_REASON in refreshed)


def test_registration_observation_distinguishes_errors():
    win, lin = _f(windows=True), _f(windows=False)
    cases = [
        (win, 0, "AX_RESIDENCY_PRESENT=1", True, True),
        (win, 0, "AX_RESIDENCY_PRESENT=0", True, False),
        (win, 0, "", False, None),
        (win, 1, "AX_RESIDENCY_ERROR=Access denied", False, None),
        (win, 255, "", False, None),
        (lin, 0, "PATH=/usr/bin\n", True, False),
        (lin, 0, "*/5 * * * * cd /p/NS && python old.py\n", True, True),
        (lin, 1, "no crontab for sim", True, False),
        (lin, 1, "permission denied", False, None),
        (lin, 127, "crontab: command not found", False, None),
        (lin, 255, "", False, None),
    ]
    for f, rc, text, known, present in cases:
        state = R.registration_status(rc, text, f)
        check(f"조회 결과를 구분 {f.windows}/{rc}/{text}",
              state["known"] is known and state["present"] is present, state)
    cmd = R.registration_query_command("NS", win)
    check("Windows 전체 조회 실패를 숨기지 않음",
          "Get-ScheduledTask -ErrorAction Stop" in cmd and "catch" in cmd, cmd)
    check("Windows 부재를 명시적 표식으로 낸다",
          "AX_RESIDENCY_PRESENT=0" in cmd and "AX_RESIDENCY_PRESENT=1" in cmd)
    check("Linux 부재 메시지 언어·stderr를 고정",
          R.registration_query_command("NS", lin) == "LC_ALL=C crontab -l 2>&1")


def test_legacy_registration_cleanup_is_targeted():
    win = _f(windows=True)
    check("ModularStage의 기존 작업 이름 보존", R.task_name("ModularStage") == "AxWorker")
    check("프로젝트별 기존 작업 이름 보존", R.task_name("NS") == "AxWorker_NS")
    unreg = dict(R.unregister_commands("NS", win))["unregister"]
    check("기존 작업 이름만 삭제", unreg == "schtasks /delete /f /tn AxWorker_NS", unreg)
    lin = _f(windows=False, path="/home/sim/trunk/NS")
    other = _f(windows=False, path="/home/sim/trunk/Other")
    unreg_l = dict(R.unregister_commands("NS", lin))["unregister"]
    check("우리 cron 표식만 제거", R.cron_marker(lin) in unreg_l and "grep -vF" in unreg_l)
    check("PATH와 다른 cron 보존", "crontab -r" not in unreg_l and "echo" not in unreg_l)
    check("다른 프로젝트 표식과 분리", R.cron_marker(other) != R.cron_marker(lin))


def test_python_probe_and_conductor_contract():
    check("Python 경로는 PATH와 LOCALAPPDATA 실측",
          R.PYTHONW_PROBE.startswith("where pythonw")
          and "%LOCALAPPDATA%" in R.PYTHONW_PROBE and "Python3*" in R.PYTHONW_PROBE)
    check("실측 Python 경로 파싱",
          R.parse_python_probe("noise\nC:\\Py\\pythonw.exe\n") == r"C:\Py\pythonw.exe")
    check("경로 미확인은 추측하지 않음", R.parse_python_probe("missing") == "")
    check("콘솔 관측용 경로 변환 보존",
          R.console_python(r"C:\Py\pythonw.exe") == r"C:\Py\python.exe")
    win = _f(windows=True, path=r"C:\trunk\NS")
    cmd = dict(R.conductor_register_commands("NS", win, python_path=r"C:\Py\pythonw.exe"))[
        "conductor-register"]
    check("로그인 세션 런처는 유지", "/tn AxConductor_NS " in cmd, cmd)
    check("LIMITED /IT 계약 보존", "/it /rl LIMITED" in cmd)
    check("런처는 폴링 데몬이 아님",
          "session1_conductor.py" in cmd and "worker_daemon.py" not in cmd
          and "/sc minute" not in cmd)
    check("인터프리터와 스크립트 인용 보존", cmd.count('\\"') == 4, cmd)
    check("런처 실행 명령을 데몬 기동과 구분",
          R.conductor_run_command("NS", win) == "schtasks /run /tn AxConductor_NS")
    check("Linux에는 Windows 런처 없음",
          R.conductor_register_commands("NS", _f(windows=False)) == [])


def test_session1_side_effects():
    cmds = dict(R.crash_dialog_commands(_f(windows=True)))
    check("Windows 크래시 모달 차단 보존",
          "DontShowUI" in cmds.get("crash-dialog-off", ""), cmds)
    check("크래시 설정은 사용자 범위",
          "HKCU" in cmds["crash-dialog-off"] and "HKLM" not in cmds["crash-dialog-off"])
    check("Linux 크래시 설정 건드리지 않음", R.crash_dialog_commands(_f(windows=False)) == [])
    src = (Path(__file__).resolve().parent.parent
           / "client" / "runtime" / "session1_conductor.py").read_text(encoding="utf-8")
    check("런처는 시간 초과 프로세스 트리를 정리",
          "_kill_tree" in src and "/T" in src and "killpg" in src)
    check("시간 초과에서 트리 정리를 호출",
          "TimeoutExpired" in src and "_kill_tree(proc)" in src)


def test_compatibility_apis_never_touch_the_worker():
    def forbidden(*args, **kwargs):
        raise AssertionError("폐기된 데몬 경로가 원격 명령을 실행했다")
    for win in (True, False):
        f = _f(windows=win, ue5="x")
        r = bundle.ensure_worker_daemon("NS", f, runner=forbidden)
        check("구 ensure API는 원격 호출 없이 폐기 안내", r.get("retired") is True)
        r = bundle.refresh_residency(f, runner=forbidden, sleeper=forbidden)
        check("구 refresh API는 원격 호출 없이 폐기 안내", r.get("retired") is True)
    with patch.object(cli, "_facts", forbidden):
        out = StringIO()
        with redirect_stdout(out):
            rc = cli.cmd_ensure("NS", only="192.168.0.2")
        check("CLI ensure는 probe도 실행하지 않음",
              rc == 0 and R.DECOMMISSIONED_REASON in out.getvalue())


def test_claim_policy_is_preserved():
    from master.task_queue import tagging as T
    from master.task_queue.models import ClaimReq
    check("정상 claim의 MOUNT 정책 보존",
          T.POLICY.get("POST /api/v1/tasks/claim") == T.MOUNT)
    check("정상 claim의 태그 필수 계약 보존", T.requires_tag("POST", "/api/v1/tasks/claim"))
    check("정상 claim의 프로젝트 축 보존", "project" in ClaimReq.model_fields)


if __name__ == "__main__":
    for fn in (test_no_combination_can_restore_residency,
               test_plan_does_not_offer_a_daemon,
               test_registration_observation_distinguishes_errors,
               test_legacy_registration_cleanup_is_targeted,
               test_python_probe_and_conductor_contract,
               test_session1_side_effects,
               test_compatibility_apis_never_touch_the_worker,
               test_claim_policy_is_preserved):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_residency: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
