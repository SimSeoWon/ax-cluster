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


def _decode(cmd: str) -> str:
    import base64
    head = "powershell -NoProfile -NonInteractive -EncodedCommand "
    assert cmd.startswith(head), cmd
    return base64.b64decode(cmd[len(head):]).decode("utf-16-le")


def test_registration_observation_distinguishes_errors():
    win, lin = _f(windows=True), _f(windows=False)
    T = R.TASKS_MARK
    cases = [
        (win, 0, f"{T}\\AxWorker", True, True, ["\\AxWorker"]),
        (win, 0, f"{T}\\AxClaimer;\\AxWorker_NS;\\AxWorker_Kimodo", True, True,
         ["\\AxClaimer", "\\AxWorker_NS", "\\AxWorker_Kimodo"]),
        (win, 0, "#< CLIXML\nAX_RESIDENCY_PRESENT=0", True, False, []),
        (win, 0, "AX_RESIDENCY_PRESENT=0", True, False, []),
        (win, 0, "", False, None, []),
        (win, 0, "noise only", False, None, []),
        (win, 0, f"{T}\\AxConductor_NS", False, None, []),       # 보호 이름은 잔재가 아니다 → 해석 실패
        (win, 0, f"{T}\\Ax Worker bad", False, None, []),         # 안전하지 않은 이름
        (win, 0, f"AX_RESIDENCY_PRESENT=0\n{T}\\AxWorker", False, None, []),  # 표식 둘
        (win, 1, "AX_RESIDENCY_ERROR=Access denied", False, None, []),
        (win, 255, "", False, None, []),
        (lin, 0, "PATH=/usr/bin\n", True, False, []),
        (lin, 0, "*/5 * * * * cd /p/NS && python old.py\n", True, False, []),
        (lin, 0, "PATH=/x\n*/5 * * * * cd /p/Other && python .ax/x/worker_daemon.py\n", True, True,
         ["*/5 * * * * cd /p/Other && python .ax/x/worker_daemon.py"]),
        (lin, 0, "*/5 * * * * cd /q && python claimer.py --types=code\n", True, True,
         ["*/5 * * * * cd /q && python claimer.py --types=code"]),
        (lin, 1, "no crontab for sim", True, False, []),
        (lin, 1, "permission denied", False, None, []),
        (lin, 127, "crontab: command not found", False, None, []),
        (lin, 255, "", False, None, []),
    ]
    for f, rc, text, known, present, names in cases:
        state = R.registration_status(rc, text, f)
        check(f"조회 결과를 구분 {f.windows}/{rc}/{text!r}",
              state["known"] is known and state["present"] is present
              and state["names"] == names, state)
    cmd = R.registration_query_command("NS", win)
    check("Windows 조회는 프로젝트 이름과 무관", cmd == R.registration_query_command("Other", win))
    check("[중요] cmd.exe 를 안전히 지난다 — | % ^ 따옴표가 평문에 없다",
          not any(c in cmd for c in "|%^\"'"), cmd)
    ps = _decode(cmd)
    check("Windows 전체 조회 실패를 숨기지 않음",
          "Get-ScheduledTask -ErrorAction Stop" in ps and "catch" in ps and "exit 1" in ps, ps)
    check("AxWorker*·AxClaimer* 전부를 찾는다",
          "-like 'AxWorker*'" in ps and "-like 'AxClaimer*'" in ps, ps)
    check("AxConductor·AX_Ollama 를 조회하지 않는다", "Conductor" not in ps and "Ollama" not in ps)
    check("Windows 부재·목록을 명시적 표식으로 낸다",
          "AX_RESIDENCY_PRESENT=0" in ps and R.TASKS_MARK in ps and "AX_RESIDENCY_ERROR=" in ps)
    check("Linux 부재 메시지 언어·stderr를 고정",
          R.registration_query_command("NS", lin) == "LC_ALL=C crontab -l 2>&1")


def test_legacy_registration_cleanup_is_targeted():
    win = _f(windows=True)
    check("ModularStage의 기존 작업 이름 보존", R.task_name("ModularStage") == "AxWorker")
    check("프로젝트별 기존 작업 이름 보존", R.task_name("NS") == "AxWorker_NS")
    unreg = dict(R.unregister_commands("NS", win))
    check("이름을 안 주면 옛 프로젝트 이름(호환)",
          list(unreg.values()) == ['schtasks /delete /f /tn "AxWorker_NS"'], unreg)
    found = ["\\AxClaimer", "\\AxWorker_NS", "\\AxWorker", "\\AxConductor_NS", "\\AX_Ollama33"]
    cmds = [c for _l, c in R.unregister_commands("AXCluster", win, names=found)]
    check("[중요] 찾은 잔재마다 하나씩 지운다(현재 프로젝트 무관)",
          cmds == ['schtasks /delete /f /tn "\\AxClaimer"',
                   'schtasks /delete /f /tn "\\AxWorker_NS"',
                   'schtasks /delete /f /tn "\\AxWorker"'], cmds)
    check("[중요] AxConductor·AX_Ollama33 는 절대 지우지 않는다",
          not any("Conductor" in c or "Ollama" in c for c in cmds), cmds)
    check("보호 판정은 대소문자 무관",
          not R.is_legacy_task("\\axconductor") and not R.is_legacy_task("ax_ollama33")
          and R.is_legacy_task("\\axworker_x"))
    lin = _f(windows=False, path="/home/sim/trunk/NS")
    unreg_l = dict(R.unregister_commands("NS", lin))["unregister"]
    check("cron 은 두 패턴 줄만 제거", "grep -vF -e worker_daemon -e claimer" in unreg_l, unreg_l)
    check("crontab 읽기 실패면 쓰지 않는다", unreg_l.startswith("c=$(crontab -l) || exit 1;"), unreg_l)
    check("PATH와 다른 cron 보존(통째 삭제 없음)", "crontab -r" not in unreg_l)


def test_linux_cron_filter_runs_for_real():
    """실제 bash 로 해제 파이프를 돌린다 — crontab 만 가짜 스크립트로 바꾼다."""
    import os
    import subprocess
    import tempfile
    lin = _f(windows=False, path="/home/sim/trunk/NS")
    cmd = dict(R.unregister_commands("NS", lin))["unregister"]
    before = ("PATH=/usr/local/bin:/usr/bin\n"
              "*/5 * * * * cd /home/sim/trunk/NS && /usr/bin/python3 .ax/lib/worker_daemon.py --types=build\n"
              "0 3 * * * /home/sim/backup.sh\n"
              "*/5 * * * * cd /home/sim/trunk/Other && /usr/bin/python3 claimer.py\n"
              "@reboot /usr/bin/true\n")
    with tempfile.TemporaryDirectory() as d:
        tab = os.path.join(d, "tab")
        with open(tab, "w") as fh:
            fh.write(before)
        fake = os.path.join(d, "crontab")
        with open(fake, "w") as fh:
            fh.write(f'#!/bin/bash\nif [ "$1" = "-l" ]; then cat {tab}; else cat > {tab}; fi\n')
        os.chmod(fake, 0o755)
        env = {**os.environ, "PATH": d + ":" + os.environ.get("PATH", "")}
        p = subprocess.run(["bash", "-c", cmd], env=env, capture_output=True, text=True)
        after = open(tab).read()
        check("해제 파이프 rc=0", p.returncode == 0, p.stderr)
        check("[중요] 다중 줄 — 두 패턴 줄만 빠지고 PATH·다른 줄 보존",
              after == "PATH=/usr/local/bin:/usr/bin\n0 3 * * * /home/sim/backup.sh\n@reboot /usr/bin/true\n",
              repr(after))
        st = R.registration_status(0, after, lin)
        check("해제 뒤 재조회는 부재", st["known"] and not st["present"], st)
        # crontab -l 실패 → 쓰지 않는다
        with open(fake, "w") as fh:
            fh.write(f'#!/bin/bash\nif [ "$1" = "-l" ]; then exit 2; else cat > {tab}; fi\n')
        p = subprocess.run(["bash", "-c", cmd], env=env, capture_output=True, text=True)
        check("[중요] 읽기 실패면 rc≠0 이고 crontab 을 덮지 않는다",
              p.returncode != 0 and open(tab).read() == after, (p.returncode, open(tab).read()))


def test_daemon_process_query():
    win, lin = _f(windows=True), _f(windows=False)
    cmd = R.daemon_process_query_command(win)
    check("프로세스 조회도 cmd.exe 안전", not any(c in cmd for c in "|%^\"'"), cmd)
    ps = _decode(cmd)
    check("Win32_Process 명령줄을 본다",
          "Get-CimInstance Win32_Process" in ps and "worker_daemon|claimer" in ps
          and "$PID" in ps and R.PROCS_DONE in ps and "exit 1" in ps, ps)
    check("Windows 조회는 종료하지 않는다", "Stop-Process" not in ps and "taskkill" not in ps.lower())
    lc = R.daemon_process_query_command(lin)
    check("Linux 는 pgrep 이 자기 셸을 잡지 않는 패턴",
          "pgrep" in lc and "[w]orker_daemon|[c]laimer" in lc and "kill" not in lc.replace("pgrep", ""), lc)
    for rc, out, known, pids in (
            (0, f"{R.PROCS_MARK}\n{R.PROCS_DONE}", True, []),
            (0, f"#< CLIXML\n{R.PROCS_MARK}1234,5678\n{R.PROCS_DONE}", True, ["1234", "5678"]),
            (0, f"{R.PROCS_MARK}12", False, []),               # 끝 표식 없음
            (0, "", False, []),
            (1, "AX_DAEMON_ERROR=denied", False, []),
            (0, f"{R.PROCS_MARK}abc\n{R.PROCS_DONE}", False, []),
            (255, "", False, [])):
        st = R.daemon_process_status(rc, out)
        check(f"프로세스 조회 판정 {rc}/{out!r}", st["known"] is known and st["pids"] == pids, st)
    # 실제 bash — 조회가 성공하고, 자기 셸은 잡지 않고, 진짜 프로세스는 잡는다.
    #    [주의] 「pid 가 비었다」는 단정하지 않는다 — 이 검사를 부른 상위 셸의 명령줄에 그
    #    낱말이 있으면 정당하게 잡힌다(실측: 같은 셸에서 이 파일을 쓰고 돌렸을 때).
    import subprocess
    p = subprocess.run(["bash", "-c", lc], capture_output=True, text=True)
    st = R.daemon_process_status(p.returncode, p.stdout)
    check("로컬 실제 실행: 조회 성공", st["known"], (p.returncode, p.stdout, p.stderr))
    decoy = subprocess.Popen(["bash", "-c", "exec -a fake_worker_daemon sleep 30"])
    try:
        import time
        time.sleep(0.3)
        p = subprocess.run(["bash", "-c", lc], capture_output=True, text=True)
        st2 = R.daemon_process_status(p.returncode, p.stdout)
        check("로컬 실제 실행: 데몬 이름 프로세스를 잡는다", st2["known"] and str(decoy.pid) in st2["pids"],
              (p.stdout, decoy.pid))
        own = [x for x in st2["pids"] if x not in st["pids"] and x != str(decoy.pid)]
        check("로컬 실제 실행: 조회 셸 자신은 잡지 않는다", own == [], (st["pids"], st2["pids"]))
    finally:
        decoy.kill()
        decoy.wait()


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
               test_linux_cron_filter_runs_for_real,
               test_daemon_process_query,
               test_python_probe_and_conductor_contract,
               test_session1_side_effects,
               test_compatibility_apis_never_touch_the_worker,
               test_claim_policy_is_preserved):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_residency: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
