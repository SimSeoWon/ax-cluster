"""claimer 상주 등록 (`#255`) — **두 기계가 한 선언에서 나온다.**

[중요] **실물과 대조해 만들었다** (2026-08-22). 문서만 보고 짜면 틀린다 — 실제로 두 번 틀렸다:

    ⓐ `pythonw` 가 **PATH 에 없다** (`where pythonw` 빈 값 · 실물은 `%LOCALAPPDATA%` 아래)
    ⓑ `schtasks /tr` 은 전체를 한 인자로 받고 **안쪽 인용을 `\\"` 로 이스케이프**해야 한다.
      그냥 주니 cmd 가 두 번째 토큰을 옵션으로 읽어 *"잘못된 인수/옵션"* 으로 거부했다

그리고 임시 작업(`AxProbeQuote`)으로 형태를 확인한 뒤 기존 `AxClaimer` 의 Task_To_Run 과
**글자까지 대조**했다 — 같았다.

`python3 master/test_residency.py`
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client.init import residency as R                              # noqa: E402
from master.client.bundle import HostFacts                           # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _f(*, windows, ue5="", path="/p/M"):
    return HostFacts(host="h", user="u", path=path, driven="ssh", role="worker",
                     os="windows" if windows else "linux", ue5=ue5, checkout_ok=True)


def test_types_from_probe() -> None:
    """[중요] 유형은 **probe 실측(`ue5`)** 에서 나온다 — 표로 들지 않는다."""
    check("UE5 있으면 build,code", R.types_for(_f(windows=True, ue5="x")) == "build,code")
    check("없으면 code", R.types_for(_f(windows=False)) == "code")


def test_task_name_per_project() -> None:
    """[중요] 한 기계에 둘이 설치될 수 있다(`#250`) → 이름이 갈려야 한다."""
    check("ModularStage 는 기존 이름 유지", R.task_name("ModularStage") == "AxClaimer")
    check("다른 프로젝트는 접미", R.task_name("NS") == "AxClaimer_NS")
    check("[중요] 두 이름이 다르다", R.task_name("NS") != R.task_name("ModularStage"))


def test_windows_command_shape() -> None:
    """실물과 같은 형태여야 한다 — 인용이 이 함수의 핵심이다."""
    c = dict(R.commands("ModularStage", _f(windows=True, ue5="x", path=r"E:\t\M"),
                        python_path=r"C:\Py\pythonw.exe"))["register"]
    check("schtasks /create /f (멱등)", "/create /f" in c, c)
    check("5분 주기", "/sc minute /mo 5" in c, c)
    check("[주의] 대화형 전용(/it) — 사람 PC 에 백그라운드 상주를 심지 않는다", "/it" in c, c)
    check("권한 상승 없음(/rl LIMITED)", "/rl LIMITED" in c, c)
    check("[중요] 안쪽 인용을 이스케이프한다", '\\"C:\\Py\\pythonw.exe\\"' in c, c)
    check("스크립트도 이스케이프", "claimer.py" in c and c.count('\\"') == 4, c)
    check("유형이 붙는다", "--types=build,code" in c, c)
    check("pythonw 를 쓴다 (콘솔 창 없음)", "pythonw" in c, c)


def test_linux_command_preserves_path_line() -> None:
    """[중요] **PATH 줄을 지키고 우리 줄만 갈아끼운다** — 실측: `.43` crontab 첫 줄이 PATH= 다."""
    c = dict(R.commands("ModularStage", _f(windows=False, path="/home/sim/trunk/M")))["register"]
    check("crontab -l 을 읽어서 다시 쓴다", "crontab -l" in c and "| crontab -" in c, c)
    check("[중요] 우리 줄만 제외한다 (grep -vF 마커)", "grep -vF" in c, c)
    check("[주의] 통째로 지우지 않는다", "crontab -r" not in c, c)
    check("마커가 체크아웃 경로다", "/home/sim/trunk/M &&" in c, c)
    check("5분 주기", "*/5 * * * *" in c, c)
    check("출력을 버린다 (감시자 로그 폭증 방지)", ">/dev/null 2>&1" in c, c)


def test_gate_before_second_project() -> None:
    """[중요] **`#248` 전에는 두 번째 프로젝트의 상주를 켜지 않는다** (`#251` 실측 근거)."""
    check("마운트와 같으면 막지 않는다", R.blocked_reason("M", "M") == "")
    why = R.blocked_reason("NS", "ModularStage")
    check("[중요] 다르면 막는다", bool(why), why)
    check("사유가 #248 을 가리킨다", "#248" in why, why)
    check("잠금은 체크아웃·큐는 공유라는 근거를 든다", "큐는 공유" in why, why)

    lines = R.plan_lines("NS", _f(windows=False), mounted="ModularStage")
    check("계획에 그 사유가 찍힌다", any("지금 켜지 않는다" in l for l in lines), str(lines))
    ok = R.plan_lines("ModularStage", _f(windows=False), mounted="ModularStage")
    check("같은 프로젝트면 그 줄이 없다", not any("지금 켜지 않는다" in l for l in ok), str(ok))


def test_python_probe() -> None:
    """[중요] 경로를 **박지 않고 잰다** — `Python310` 같은 버전 디렉토리가 들어간다."""
    check("PATH 먼저 본다", R.PYTHONW_PROBE.startswith("where pythonw"))
    check("LOCALAPPDATA 후보를 훑는다", "%LOCALAPPDATA%" in R.PYTHONW_PROBE)
    check("버전을 와일드카드로", "Python3*" in R.PYTHONW_PROBE)
    out = ("C:\\Users\\janus\\AppData\\Local\\Programs\\Python\\Python310\\pythonw.exe\n" * 2)
    check("출력에서 한 줄을 고른다",
          R.parse_python_probe(out).endswith("pythonw.exe"), R.parse_python_probe(out))
    check("[주의] 못 찾으면 빈 문자열 (추측하지 않는다)",
          R.parse_python_probe("INFO: 파일을 찾을 수 없습니다") == "")


# ── 배달 뒤 갱신 (#277) ────────────────────────────────────────────────────────

def test_probe_command_never_uses_pythonw() -> None:
    """[중요] **`pythonw` 는 콘솔이 없어 stdout 이 사라진다** — 관측은 출력이 목적이다."""
    w = _f(windows=True, ue5="x", path=r"E:\t\NS")
    c = R.probe_command(w, python_path=r"C:\P\Python310\pythonw.exe")
    check("pythonw 를 쓰지 않는다", "pythonw.exe" not in c, c)
    check("콘솔판으로 바꾼다", "python.exe" in c, c)
    check("console_python 이 접미만 바꾼다",
          R.console_python(r"C:\P\Python310\pythonw.exe") == r"C:\P\Python310\python.exe")
    check("이미 콘솔판이면 그대로", R.console_python("/usr/bin/python3") == "/usr/bin/python3")
    check("[중요] 인터프리터를 박지 않는다 (`.2` 는 PATH 에 없다)",
          r"C:\P\Python310" in c, c)
    lin = R.probe_command(_f(windows=False, path="/p/NS"))
    check("리눅스는 절대경로 인터프리터", "/usr/bin/python3" in lin, lin)
    check("[주의] 판정 로직이 명령줄에 없다 (파이썬 안에 있다)",
          "--probe" in lin and "for /f" not in lin and "powershell" not in lin.lower(), lin)


def test_probe_parse_distinguishes_unknown_from_false() -> None:
    """[중요] **「모른다」와 「거짓」은 다르다** — 모르면 건드리지 않는다."""
    st = R.parse_probe("running=1\nstale=0\nbusy=0\nboot_mtime=5\ncode_mtime=5\n잡음")
    check("읽는다", st.get("running") == 1 and st.get("stale") == 0, str(st))
    check("모르는 키는 버린다", "잡음" not in st)
    check("stale=0 → 갱신 안 한다", not R.needs_refresh(st))
    check("[중요] 빈 응답 → 갱신 안 한다 (모르는 것을 고치지 않는다)",
          not R.needs_refresh(R.parse_probe("")))
    check("[중요] stale 키가 없으면 갱신 안 한다",
          not R.needs_refresh({"running": 1}))
    check("stale=1 → 갱신한다", R.needs_refresh(R.parse_probe("stale=1")))
    # [주의] 안 도는 것은 갱신 대상이 아니다 — 감시자가 새 코드로 띄운다
    lines = R.refresh_plan_lines(_f(windows=False), R.parse_probe("running=0\nstale=0"))
    check("상주 없음을 그렇게 말한다", any("상주 없음" in l for l in lines), str(lines))


def test_kill_is_pid_targeted() -> None:
    """[중요] **이름으로 죽이면 남의 프로젝트 상주까지 죽는다** — `#250` 이 깨진다."""
    w = _f(windows=True, ue5="x", path=r"E:\t\NS")
    f = _f(windows=False, path="/p/NS")
    for facts, want, bad in ((w, "taskkill /f /pid 4242", "/im"),
                             (f, "kill 4242", "pkill")):
        cmds = dict(R.refresh_commands(facts, force=True, pid=4242))
        check(f"pid 로 죽인다 (windows={facts.windows})", cmds["kill"] == want, cmds["kill"])
        check(f"이름/패턴으로 죽이지 않는다 (windows={facts.windows})",
              bad not in cmds["kill"], cmds["kill"])
    # pid 를 모르면 강제 종료를 **건너뛴다**
    cmds = dict(R.refresh_commands(f, force=True))
    check("[중요] pid 를 모르면 죽이지 않는다", "kill 0" not in cmds["kill"]
          and "pid 를 모른다" in cmds["kill"], cmds["kill"])
    # 깃발은 언제나 먼저
    order = [lbl for lbl, _ in R.refresh_commands(f, force=True, pid=1)]
    check("깃발이 먼저, 강제 종료가 나중", order == ["flag", "kill"], str(order))
    check("[주의] force 없이는 강제 종료가 없다",
          [l for l, _ in R.refresh_commands(f)] == ["flag"])


def test_claimer_state_is_process_based() -> None:
    """[중요] **완료 조건 2** — 판정이 파일 해시가 아니라 **도는 프로세스**를 본다.

    그리고 **완료 조건 4** — 옛 코드가 도는 상태를 재현해 잡는지 잰다.
    """
    import os
    import tempfile
    import time as _t
    from master.work import claimer as C

    root = Path(tempfile.mkdtemp())
    (root / ".ax" / "lib" / "axmaster").mkdir(parents=True)
    (root / ".ax" / "config.json").write_text("{}", encoding="utf-8")
    lib = root / ".ax" / "lib" / "axmaster" / "x.py"
    lib.write_text("# v1", encoding="utf-8")

    st = C.probe_state(root)
    check("안 돌고 있으면 running=False", not st["running"])
    check("[중요] 안 도는 것은 stale 이 아니다 (감시자가 새 코드로 띄운다)", not st["stale"])

    C.write_boot_stamp(root); C.touch_alive(root)
    st = C.probe_state(root)
    check("부팅 스탬프 뒤 running", st["running"])
    check("갓 배달된 코드로 떴으면 stale 아님", not st["stale"])
    check("pid 를 남긴다 (강제 종료가 pid 로만 돌 수 있게)", st["pid"] == os.getpid())

    # ── 옛 코드가 도는 상태 재현: 코드만 새로 놓는다 (프로세스는 그대로)
    os.utime(lib, (_t.time() + 5, _t.time() + 5))
    st = C.probe_state(root)
    check("[중요] **옛 코드로 돌고 있음을 잡는다**", st["stale"],
          f"boot={st['boot_mtime']} code={st['code_mtime']}")
    check("근거를 함께 낸다", st["code_mtime"] > st["boot_mtime"])

    # ── 진행 중 태스크를 죽이지 않는다 (완료 조건 3)
    (root / ".ax" / C.BUSY_FILE).write_text("T1", encoding="utf-8")
    check("처리 중을 말한다", C.probe_state(root)["busy"])
    (root / ".ax" / C.BUSY_FILE).unlink()

    # ── 깃발 계약
    check("깃발이 없으면 False", not C.restart_requested(root))
    (root / ".ax" / C.RESTART_FILE).write_text("1", encoding="utf-8")
    check("깃발을 본다", C.restart_requested(root))
    check("probe 가 그것도 보고한다", C.probe_state(root)["restart_pending"])
    C.clear_restart(root)
    check("치우면 사라진다", not C.restart_requested(root))

    # ── alive 가 낡으면 「도는 것이 아니다」
    (root / ".ax" / C.ALIVE_FILE).write_text(str(int(_t.time()) - 10_000), encoding="utf-8")
    check("[주의] alive 가 낡으면 running=False (죽은 프로세스의 스탬프에 속지 않는다)",
          not C.probe_state(root)["running"])

    # ── 트리 전체를 본다 (claimer.py 만 보지 않는다)
    src = (Path(__file__).resolve().parent / "work" / "claimer.py").read_text(encoding="utf-8")
    check("[중요] lib 트리 전체의 mtime 을 본다", "rglob" in src and "lib_mtime" in src)
    check("[중요] 루프가 claim **전에** 깃발을 본다",
          src.index("restart_requested(root)") < src.index("task = c.claim(types)"))
    check("busy 마커를 finally 로 지운다", "finally:" in src and "busy.unlink()" in src)
    # [중요] **관측이 부작용을 갖지 않는다** — probe 는 잠금을 *잡아 보고 즉시 놓는다*.
    #    (잡히면 아무도 없다는 뜻이므로 그것이 판정이다. 쥐고 있으면 진짜 상주가 못 뜬다.)
    lock_src = src[src.index("def someone_holds_lock"):src.index("def probe_state")]
    check("잠금을 얻으면 즉시 닫는다", "f.close()" in lock_src, lock_src[:80])
    check("[중요] 잠금 파일을 지우지 않는다 (지우면 싱글턴이 깨진다)",
          "unlink" not in lock_src)
    main_src = src[src.index("def main("):]
    check("[중요] main 은 probe 를 상주 경로 **앞에서** 끝낸다",
          main_src.index('"--probe" in argv')
          < main_src.index("acquire_singleton(root)"), "관측이 상주를 띄운다")
    # 옛 코드(스탬프 없음)를 잠금으로 잡는다 — 이것이 실물 사고의 상태다
    check("[중요] 잠금 축이 있다 (스탬프만 보면 옛 코드를 「안 돈다」로 읽는다)",
          "someone_holds_lock" in src and "no_stamp" in src)
    check("깃발은 부팅 시각으로 거른다 (앞 프로세스에게 내려진 요구를 먹지 않는다)",
          "booted_at" in src)


def test_stale_flag_is_not_eaten_by_the_new_process() -> None:
    """[중요] **앞 프로세스에게 내려진 깃발을 새 프로세스가 먹으면 한 주기를 버린다.**

    실측 2026-08-22: 옛 상주를 강제 종료한 뒤 깃발이 남았고, 감시자가 새 코드로 되살린
    프로세스가 그것을 보고 **즉시 물러났다**(cron 5분을 버렸다).
    """
    import tempfile
    import time as _t
    from master.work import claimer as C
    root = Path(tempfile.mkdtemp())
    (root / ".ax").mkdir(parents=True)
    flag = root / ".ax" / C.RESTART_FILE
    flag.write_text("1", encoding="utf-8")
    old_flag = int(flag.stat().st_mtime)
    check("관측용 호출은 존재만 본다", C.restart_requested(root))
    check("[중요] 내가 뜨기 전 깃발은 내 것이 아니다",
          not C.restart_requested(root, booted_at=old_flag + 5))
    check("내가 뜬 뒤 깃발은 내 것이다",
          C.restart_requested(root, booted_at=old_flag - 5))
    # 마스터도 치운다 — 놓은 쪽이 치우는 것이 옳다
    from client.init import residency as _R
    cmds = dict(_R.clear_flag_commands(_f(windows=False, path="/p/NS")))
    check("리눅스 제거 명령", cmds["clear"] == "rm -f /p/NS/.ax/claimer.restart", cmds["clear"])
    cmds = dict(_R.clear_flag_commands(_f(windows=True, ue5="x", path=r"E:\t\NS")))
    check("윈도우 제거 명령은 조용히 실패한다(2>nul)", "2>nul" in cmds["clear"], cmds["clear"])
    import inspect
    from master.client import bundle
    rsrc = inspect.getsource(bundle.refresh_residency)
    check("[중요] 강제 종료 뒤 깃발을 치운다",
          rsrc.index("clear_flag_commands") > rsrc.index("force=True"), "치우지 않는다")


def test_deliver_refreshes_residency() -> None:
    """[중요] **완료 조건 1** — 배달 절차 자체가 확인한다(사람 눈이 아니다)."""
    import inspect
    from master.client import bundle
    src = inspect.getsource(bundle.deliver)
    check("배달이 갱신을 부른다", "refresh_residency(facts)" in src, "배달이 파일만 놓고 끝난다")
    rsrc = inspect.getsource(bundle.refresh_residency)
    check("관측 → 요구 → 재관측", rsrc.count("probe_command") >= 2, "재관측이 없다")
    check("[중요] 못 읽으면 아무것도 안 한다", "건드리지 않는다" in rsrc)
    check("[중요] busy 면 강제 종료하지 않는다",
          rsrc.index('after.get("busy")') < rsrc.index("force=True"))
    check("강제 종료는 pid 로만", "pid=pid" in rsrc)
    check("[주의] requester 는 대상이 아니다", 'facts.role != "worker"' in rsrc)

    # 주입 이음으로 전체 흐름을 잰다 — 옛 코드(깃발 무시)를 재현
    calls = []

    def fake_run(cmd, timeout=60):
        calls.append(cmd)
        if "--probe" in cmd:
            return 0, "running=1\nstale=1\nbusy=0\npid=777\nboot_mtime=1\ncode_mtime=9\n"
        return 0, ""

    f = _f(windows=False, path="/p/NS")
    r = bundle.refresh_residency(f, runner=fake_run)
    check("깃발을 무시하는 코드는 강제 종료된다", r.get("pid_killed") == 777, str(r))
    check("kill 이 pid 로 나갔다", any(c == "kill 777" for c in calls), str(calls))
    check("깃발도 먼저 나갔다", any("claimer.restart" in c for c in calls))

    # 깃발을 아는 코드: 두 번째 probe 에서 stale 이 풀린다
    seq = iter(["running=1\nstale=1\nbusy=0\npid=5\n", "running=0\nstale=0\n"])

    def fake_ok(cmd, timeout=60):
        return (0, next(seq)) if "--probe" in cmd else (0, "")

    r = bundle.refresh_residency(f, runner=fake_ok)
    check("[중요] 깃발만으로 끝나면 죽이지 않는다", r.get("refreshed") == "깃발", str(r))

    # 처리 중이면 기다린다
    seq2 = iter(["running=1\nstale=1\nbusy=1\npid=5\n", "running=1\nstale=1\nbusy=1\npid=5\n"])
    r = bundle.refresh_residency(f, runner=lambda c, timeout=60:
                                (0, next(seq2)) if "--probe" in c else (0, ""))
    check("[중요] 처리 중이면 강제 종료하지 않는다 (완료 조건 3)",
          "pending" in r and not r.get("pid_killed"), str(r))

    # 못 읽으면 아무것도 안 한다
    r = bundle.refresh_residency(f, runner=lambda c, timeout=60: (1, "connection refused"))
    check("[중요] probe 를 못 읽으면 손대지 않는다", r.get("unknown") is True, str(r))
    check("사유를 남긴다", "건드리지 않는다" in (r.get("why") or ""))

    # requester 는 건너뛴다
    req = _f(windows=True, ue5="x", path=r"C:\p\NS")
    req = req.__class__(**{**req.__dict__, "role": "requester"})
    r = bundle.refresh_residency(req, runner=lambda c, timeout=60: (0, "stale=1"))
    check("requester 는 건너뛴다", "skipped" in r, str(r))


if __name__ == "__main__":
    for fn in (test_types_from_probe,
               test_task_name_per_project,
               test_windows_command_shape,
               test_linux_command_preserves_path_line,
               test_gate_before_second_project,
               test_python_probe,
               test_probe_command_never_uses_pythonw,
               test_probe_parse_distinguishes_unknown_from_false,
               test_kill_is_pid_targeted,
               test_claimer_state_is_process_based,
               test_stale_flag_is_not_eaten_by_the_new_process,
               test_deliver_refreshes_residency):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_residency: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
