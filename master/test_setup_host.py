"""워커 설치·이전 (`setup_host`) — 계획·경로 이전·낡은 상주 판정·실패 정지.

[중요] 실물 사건은 2026-10-30 `.2` 보드 교체다 — E: 가 빠지며 등록부 4개 경로와 상주 4개가
사라진 경로를 가리켰다. 여기서 재는 것은 *"순서를 지키고, 이름이 아니라 실측으로 지우는가"* 다.

`.venv/bin/python master/test_setup_host.py`
"""
from __future__ import annotations

import io
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import setup_host as S                         # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _shop(path, user="janus"):
    return types.SimpleNamespace(path=path, user=user, driven="ssh", role="worker",
                                 note="n", dispatch="")


def _reg(active="AXCluster", shops=None):
    shops = shops if shops is not None else {
        "AXCluster": {"192.168.0.2": _shop("E:\\trunk\\AXCluster")},
        "NS": {"192.168.0.2": _shop("E:\\trunk\\NS")},
        "Other": {"192.168.0.43": _shop("/home/sim/trunk/Other", "sim")},
    }
    return types.SimpleNamespace(
        active=active, names=list(shops),
        config_of=lambda n: types.SimpleNamespace(workshops=shops[n]))


def _quiet(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(*a, **k)
    return rc, buf.getvalue()


def test_relocate() -> None:
    check("윈도우 → 윈도우", S.relocate("E:\\trunk\\NS", "C:\\trunk") == "C:\\trunk\\NS")
    check("끝 구분자 무시", S.relocate("E:\\trunk\\NS\\", "C:\\trunk\\") == "C:\\trunk\\NS")
    check("리눅스", S.relocate("/old/NS", "/home/sim/trunk") == "/home/sim/trunk/NS")
    check("윈도우 판정", S.is_windows_path("C:\\trunk") and not S.is_windows_path("/home"))


def test_plan_moves_every_registered_project() -> None:
    """[중요] 경로는 등재된 **모든** 프로젝트를 옮긴다 — 클론은 마운트만."""
    moves = S.plan("192.168.0.2", "C:\\trunk", registry=_reg())
    got = {m.project: (m.old, m.new, m.mounted) for m in moves}
    check("두 프로젝트만", set(got) == {"AXCluster", "NS"}, str(got))
    check("마운트 표시", got["AXCluster"][2] and not got["NS"][2])
    check("새 경로", got["NS"][1] == "C:\\trunk\\NS")


def test_plan_new_host_needs_user() -> None:
    """[중요] 계정을 추측하지 않는다 — 신규 등재는 `--user` 가 있어야 한다."""
    reg = _reg(shops={"AXCluster": {}})
    try:
        S.plan("192.168.0.99", "C:\\trunk", registry=reg)
        check("user 없으면 거절", False)
    except ValueError:
        check("user 없으면 거절", True)
    moves = S.plan("192.168.0.99", "C:\\trunk", user="janus", registry=reg)
    check("신규 등재", len(moves) == 1 and moves[0].old == "" and moves[0].mounted
          and moves[0].user == "janus" and moves[0].new == "C:\\trunk\\AXCluster")


def test_no_mount_refuses() -> None:
    try:
        S.plan("h", "C:\\trunk", registry=_reg(active=""))
        check("마운트 없으면 거절", False)
    except ValueError:
        check("마운트 없으면 거절", True)


def test_dry_run_writes_nothing() -> None:
    calls = []
    S.logic.set_workshop = lambda *a, **k: calls.append(a)
    rc, out = _quiet(S.run, "192.168.0.2", "C:\\trunk", registry=_reg(),
                     ssh=lambda *a, **k: calls.append(a) or (0, ""),
                     deliver=lambda *a, **k: calls.append(a) or 0,
                     check=lambda *a, **k: calls.append(a) or 0)
    check("계획만 rc 0", rc == 0)
    check("아무것도 안 부른다", calls == [], str(calls))
    check("계획에 이동이 보인다", "E:\\trunk\\NS" in out and "C:\\trunk\\NS" in out, out)


def _confirm_run(task_out, *, deliver_rc=0, delete_rc=0):
    log = []
    S.logic.set_workshop = lambda proj, host, **k: log.append(("set", proj, k["path"],
                                                                k["user"], k["note"]))

    def ssh(host, user, cmd, **k):
        log.append(("ssh", cmd))
        if "/query" in cmd:
            return task_out(cmd)
        return (delete_rc, "")
    rc, out = _quiet(S.run, "192.168.0.2", "C:\\trunk", registry=_reg(), confirm=True, ssh=ssh,
                     deliver=lambda p, only: log.append(("deliver", p, only)) or deliver_rc,
                     check=lambda p, only: log.append(("check", p, only)) or 0)
    return rc, out, log


def test_confirm_order_and_stale_by_measurement() -> None:
    """[중요] 옛 경로를 **가리키는** 과제만 지운다 — 이름이 맞아도 다른 경로면 둔다."""
    def task_out(cmd):
        if "AxConductor_NS" in cmd:
            return (0, 'Task To Run: "pythonw.exe" "e:\\TRUNK\\NS\\.ax\\lib\\x.py"')
        if "AxConductor_AXCluster" in cmd:
            return (0, 'Task To Run: "pythonw.exe" "D:\\elsewhere\\x.py"')
        return (1, "ERROR: not found")
    rc, out, log = _confirm_run(task_out)
    check("rc 0", rc == 0, out)
    kinds = [e[0] for e in log]
    check("등록부가 먼저", kinds[:2] == ["set", "set"], str(kinds))
    check("필드 보존", ("set", "NS", "C:\\trunk\\NS", "janus", "n") in log, str(log))
    deletes = [e[1] for e in log if e[0] == "ssh" and "/delete" in e[1]]
    check("NS 지휘자만 해제", deletes == ["schtasks /delete /f /tn AxConductor_NS"], str(deletes))
    check("deliver→check 마지막", kinds[-2:] == ["deliver", "check"]
          and log[-2] == ("deliver", "AXCluster", "192.168.0.2"), str(log[-2:]))


def test_stops_on_failure() -> None:
    rc, out, log = _confirm_run(lambda c: (0, "E:\\trunk\\NS"), delete_rc=5)
    check("해제 실패면 rc 1", rc == 1)
    check("해제 실패면 배달 안 함", not any(e[0] == "deliver" for e in log))
    rc, out, log = _confirm_run(lambda c: (1, ""), deliver_rc=1)
    check("배달 실패면 rc 1", rc == 1)
    check("배달 실패면 check 안 함", not any(e[0] == "check" for e in log))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
