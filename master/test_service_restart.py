"""`#647` allowlist와 전후 판정 회귀 + `#360` 복구 경로."""
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import service_restart as S


class R:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def _show(active="inactive", result="success"):
    return (f"ExecMainStartTimestampMonotonic=1\nExecMainStartTimestamp=t\n"
            f"ActiveState={active}\nSubState=dead\nResult={result}\nExecMainStatus=0\n")


def check_360():
    """🔴 `#360` — 파견 유닛이 죽었을 때 마스터가 복구할 수 있나. 반환: (실패수, 전체수)."""
    bad = total = 0

    def say(name, cond, detail=""):
        nonlocal bad, total
        total += 1
        if not cond:
            bad += 1
            print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))

    # ── ① reset-failed 는 failed 를 지우고 전후를 말한다 ──
    calls = []
    shows = iter((_show("failed", "start-limit-hit"), _show("inactive", "success")))

    def run(cmd, **kw):
        calls.append(cmd)
        return R(out=next(shows)) if cmd[:2] == ["systemctl", "show"] else R()

    got = S.reset_failed("ax-dispatch.path", run=run)
    say("helper 를 reset-failed 형태로 부른다",
        calls[1] == ["sudo", "-n", S.HELPER, "reset-failed", "ax-dispatch.path"], str(calls))
    say("전후를 말한다",
        got["before"] == "failed/start-limit-hit" and got["after"] == "inactive/success", str(got))
    say("failed 였다고 기록한다", got["was_failed"] is True, str(got))

    # ── ② 🔴 rc=0 이어도 여전히 failed 면 실패다 (`#647` 이 재시작에서 배운 것과 같다) ──
    shows2 = iter((_show("failed", "start-limit-hit"), _show("failed", "start-limit-hit")))
    try:
        S.reset_failed("ax-dispatch.service",
                       run=lambda c, **k: (R(out=next(shows2))
                                           if c[:2] == ["systemctl", "show"] else R()))
        say("🔴 rc=0 이어도 failed 면 실패로 본다", False, "예외가 안 났다")
    except RuntimeError as e:
        say("🔴 rc=0 이어도 failed 면 실패로 본다", "failed" in str(e), str(e))

    # ── ③ 허용 밖은 helper 를 부르지도 않는다 ──
    for unit in ("nginx", "nginx.path", "ax-nope.service"):
        seen = []
        try:
            S.reset_failed(unit, run=lambda c, **k: (seen.append(c), R(out=_show()))[1])
            say(f"{unit} 을 거절한다", False, "통과했다")
        except ValueError:
            say(f"{unit} 을 거절한다", True)
        say(f"  {unit}: helper 를 안 부른다", not seen, str(seen))

    # ── ④ recover 는 존재하는 유닛만 보고, 남의 유닛을 안 끌어온다 ──
    listing = ("ax-dispatch.path            enabled  enabled\n"
               "ax-dispatch.service         disabled enabled\n"
               "ax-dispatch.timer           enabled  enabled\n"
               "ax-dispatch-catchup.service static   -\n")
    shows4 = iter([_show("failed", "start-limit-hit"), _show()] * 3)

    def run4(cmd, **kw):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return R(out=listing)
        return R(out=next(shows4)) if cmd[:2] == ["systemctl", "show"] else R()

    names = [r["unit"] for r in S.recover("ax-dispatch", run=run4)]
    say("🔴 .service·.path·.timer 를 전부 본다",
        names == ["ax-dispatch.path", "ax-dispatch.service", "ax-dispatch.timer"], str(names))
    say("🔴 ax-dispatch-catchup 을 끌어오지 않는다",
        not any("catchup" in n for n in names), str(names))

    # ── ⑤ failed 가 아닌 것도 「지나갔다」고 남긴다 ──
    shows5 = iter([_show("active", "success"), _show("active", "success")])

    def run5(cmd, **kw):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return R(out="ax-status.timer  enabled enabled\n")
        return R(out=next(shows5)) if cmd[:2] == ["systemctl", "show"] else R()

    say("[주의] failed 가 아니면 그렇게 기록한다",
        S.recover("ax-status", run=run5)[0]["was_failed"] is False)

    # ── ⑥ 🔴 root helper 자체의 판정 — **가짜 systemctl 로** 돌린다 ──
    #    [중요] 운영 유닛을 대상으로 「통과하는 경우」를 재면 **실제로 재시작된다.**
    #    2026-09-20 에 그렇게 `ax-projects` 를 재시작했다. 그래서 여기서는 가짜를 꽂는다.
    import subprocess as sp
    import tempfile
    root = pathlib.Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as td:
        fake = pathlib.Path(td) / "systemctl"
        fake.write_text('#!/bin/sh\necho "CALLED $*"\n', encoding="utf-8")
        fake.chmod(0o755)
        mine = pathlib.Path(td) / "helper"
        mine.write_text((root / "scripts" / "ax-service-restart-root")
                        .read_text(encoding="utf-8")
                        .replace("/usr/bin/systemctl", str(fake)), encoding="utf-8")

        def h(*a):
            r = sp.run(["/bin/sh", str(mine), *a], capture_output=True, text=True, timeout=15)
            return r.returncode, (r.stdout + r.stderr).strip()

        for args, why in ((("nginx",), "남의 유닛"),
                          (("reset-failed", "nginx"), "남의 유닛 복구"),
                          (("restart", "ax-dispatch.path"), "🔴 .path 재시작"),
                          (("restart", "ax-dispatch.timer"), "🔴 .timer 재시작"),
                          (("stop", "ax-dispatch"), "허용 밖 verb"),
                          (("reset-failed", "ax-dispatch.socket"), "허용 밖 접미어"),
                          (("a", "b", "c"), "인자 3개")):
            rc, out = h(*args)
            say(f"helper 거절: {why}", rc == 2 and "CALLED" not in out, f"rc={rc} {out}")

        for args, want in ((("ax-projects",), "restart ax-projects"),
                           (("restart", "ax-dispatch"), "restart ax-dispatch"),
                           (("reset-failed", "ax-dispatch.path"), "reset-failed ax-dispatch.path"),
                           (("reset-failed", "ax-dispatch-catchup.service"),
                            "reset-failed ax-dispatch-catchup.service")):
            rc, out = h(*args)
            say(f"helper 통과: {want}", rc == 0 and out == f"CALLED {want}", f"rc={rc} {out}")

    # ── ⑦ sudoers 가 helper 의 허용 집합을 덮는가 ──
    sudoers = (root / "scripts" / "ax-service-restart.sudoers").read_text(encoding="utf-8")
    for base in S.RECOVERABLE:
        for suf in ("", ".service", ".path", ".timer"):
            say(f"sudoers: reset-failed {base}{suf}",
                f"ax-service-restart-root reset-failed {base}{suf}" in sudoers)
    # 🔴 [주의] **2인자 restart 는 sudoers 에 없다** — helper 는 대칭으로 받지만 권한은
    #    안 열려 있다(실측 2026-09-20: 암호를 묻는다). 이 칸은 그 비대칭이 **의도**임을
    #    못으로 박는다. 열려면 여기가 먼저 빨개진다.
    say("🔴 sudoers 에 2인자 restart 는 없다",
        "ax-service-restart-root restart " not in sudoers, "2인자 restart 가 열렸다")
    for base in S.ALLOWED:
        # [주의] 종전 1인자 형태가 **그대로 남아 있어야** 한다 — 새 sudoers 가 깔리기 전에
        #    형태를 갈아엎으면 기존 재시작이 통째로 죽는다.
        say(f"sudoers: 종전 재시작 {base}",
            f"ax-service-restart-root {base}," in sudoers or
            sudoers.rstrip().endswith(f"ax-service-restart-root {base}"))
    return bad, total


def main() -> int:
    calls = []
    shows = iter((
        "ExecMainStartTimestampMonotonic=1\nExecMainStartTimestamp=old\nActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\n",
        "ExecMainStartTimestampMonotonic=2\nExecMainStartTimestamp=new\nActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\n",
    ))
    def run(cmd, **kwargs):
        calls.append(cmd)
        return R(out=next(shows)) if cmd[:2] == ["systemctl", "show"] else R()
    before, after = S.restart("ax-projects", run=run)
    assert before["ExecMainStartTimestampMonotonic"] == "1"
    assert after["ExecMainStartTimestampMonotonic"] == "2"
    assert calls[1] == ["sudo", "-n", S.HELPER, "ax-projects"]
    shows = iter((
        "ExecMainStartTimestampMonotonic=1\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n",
        "ExecMainStartTimestampMonotonic=2\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n",
    ))
    S.restart("ax-status", run=run)
    try:
        S.restart("ssh", run=run)
    except ValueError:
        pass
    else:
        raise AssertionError("미허용 유닛을 받았다")
    assert S.main(["ax-projects", "extra"]) == 2
    bad, extra = check_360()
    print(f"통과 {6 + extra - bad} · 실패 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
