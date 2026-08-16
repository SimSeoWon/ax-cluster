"""요청자 검수 빌드 어댑터(`#135`) 계약 테스트 — 🔴 **판정이 한 벌인가.**

이 어댑터의 존재 이유는 *"`.33` 이 자기 트리에서 빌드한다"* 이고, 위험은 **판정이 두 벌이
되는 것**이다. 그래서 여기서 재는 것은 빌드가 되느냐가 아니라:

    ① 명령을 `layer3_verify.build_build_command` 와 **공유**하는가
    ② 판정을 `parse_build_log` 와 **공유**하는가 (🔴 종료 코드를 보지 않는가)
    ③ 경로 유도가 `skeleton_gate` 와 **한 규칙**인가
    ④ 확인 불가를 **통과로 만들지 않는가**

실행: python3 master/test_build_local.py   (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import layer3_verify as L3            # noqa: E402
from master.work import build_local as B          # noqa: E402
from master.work import skeleton_gate as SG       # noqa: E402

PASS = FAIL = 0
UE5 = r"C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


class Proc:
    def __init__(self, out: str, rc: int = 0):
        self.stdout, self.stderr, self.returncode = out, "", rc


OK_LOG = "Build succeeded\nTotal execution time: 41.2 seconds\nResult: Succeeded\n"
BAD_LOG = "ERROR: ...\nResult: Failed (RulesError)\nTotal execution time: 3.1 seconds\n"


# ── ③ 경로 유도는 한 규칙 ─────────────────────────────────────

def test_build_bat_derivation_is_one_rule():
    bb = SG.build_bat_from_editor(UE5)
    check("에디터 경로에서 Build.bat 을 유도한다",
          bb == r"C:\Program Files\UE_5.8\Engine\Build\BatchFiles\Build.bat", bb)
    check("🔴 Epic Games 하위를 가정하지 않는다 (실측된 경로 그대로)", "Epic Games" not in bb)
    # 🔴 **두 배치가 실제로 공존한다** (프로브 실측 2026-08-16):
    #     .2  → C:\Program Files\UE_5.8\…            (Epic Games 없음)
    #     .33 → C:\Program Files\Epic Games\UE_5.8\… (있음)
    #    그래서 경로를 짐작하면 한쪽이 반드시 틀린다.
    epic = SG.build_bat_from_editor(
        r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe")
    check("🔴 Epic Games 하위 배치도 그대로 유도된다 (.33 실측)",
          epic == r"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat", epic)
    check("못 찾으면 빈 문자열", SG.build_bat_from_editor("") == ""
          and SG.build_bat_from_editor(r"C:\somewhere\else.exe") == "")

    class F:
        ue5 = UE5
    check("🔴 facts 판은 같은 규칙에 위임한다 (규칙이 두 벌이 아니다)",
          SG._build_bat_from(F()) == bb)
    check("슬래시 경로도 받는다",
          SG.build_bat_from_editor(UE5.replace("\\", "/")).endswith("Build.bat"))


# ── ① 명령 공유 ───────────────────────────────────────────────

def test_command_is_shared_with_workshop_path():
    seen = {}

    def runner(cmd, timeout):
        seen["cmd"] = cmd
        return Proc(OK_LOG)

    L3.run_build_local(r"C:\E\Build.bat", "XEditor", r"C:\p\X.uproject", runner=runner)
    local_cmd = seen["cmd"]
    expected = L3.build_build_command(r"C:\E\Build.bat", "XEditor", r"C:\p\X.uproject")
    check("🔴 명령을 build_build_command 로 만든다 (재조립하지 않는다)",
          expected in local_cmd, str(local_cmd))
    check("로컬은 cmd /c 로 돈다 (ssh 가 아니다)",
          local_cmd[:2] == ["cmd", "/c"] and not any("ssh" in str(c) for c in local_cmd),
          str(local_cmd[:2]))
    check("표준 UBT 인자가 그대로다",
          "-WaitMutex" in expected and "Win64 Development" in expected, expected)


# ── ② 판정 공유 — 🔴 종료 코드를 보지 않는다 ──────────────────

def test_verdict_ignores_exit_code():
    """🔴 실측: `Build.bat` 은 **실패해도 rc=0** 을 낸다. 그래서 로그로 판정한다."""
    ok = L3.run_build_local("b", "t", "u", runner=lambda c, t: Proc(OK_LOG, rc=1))
    check("성공 로그면 rc=1 이어도 통과", ok.passed, ok.summary())
    bad = L3.run_build_local("b", "t", "u", runner=lambda c, t: Proc(BAD_LOG, rc=0))
    check("🔴 실패 로그면 rc=0 이어도 불합격", not bad.passed, bad.summary())
    check("실패 사유를 남긴다", bad.detail or bad.result, bad.summary())


def test_unconfirmed_is_not_a_pass():
    """🔴 확인하지 못한 것과 통과한 것은 다르다."""
    import subprocess

    def boom(cmd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    r = L3.run_build_local("b", "t", "u", runner=boom, timeout=7)
    check("타임아웃은 통과가 아니다", not r.passed)
    check("타임아웃이라고 말한다", "7초" in (r.failure or ""), str(r.failure))

    r2 = L3.run_build_local("b", "t", "u", runner=lambda c, t: (_ for _ in ()).throw(OSError("없음")))
    check("실행 실패도 통과가 아니다", not r2.passed and "막는다" in (r2.failure or ""), str(r2.failure))


# ── ④ 어댑터 ──────────────────────────────────────────────────

def test_adapter_blocks_when_engine_missing():
    try:
        B.local_build_fn(project="X", ue5_cmd="")
        check("🔴 엔진을 못 찾으면 **만들 때** 죽는다", False, "조용히 만들어졌다")
    except B.BuildSetupError as e:
        check("🔴 엔진을 못 찾으면 **만들 때** 죽는다", True)
        check("무엇을 확인할지 말한다", "config.json" in str(e), str(e)[:80])


def test_adapter_reports_missing_uproject():
    fn = B.local_build_fn(project="ModularStage", ue5_cmd=UE5,
                          builder=lambda *a, **k: L3.parse_build_log(OK_LOG))
    with tempfile.TemporaryDirectory() as d:
        out = fn(d)
    check("🔴 uproject 가 없으면 빌드하지 않고 막는다", out["ok"] is False, str(out))
    check("이유를 말한다", "uproject" in out.get("summary", "") or ".uproject" in out.get("failure", ""),
          str(out))


def test_adapter_passes_verdict_through():
    seen = {}

    def builder(bb, tgt, up, **kw):
        seen.update(build_bat=bb, target=tgt, uproject=up)
        return L3.parse_build_log(OK_LOG)

    fn = B.local_build_fn(project="ModularStage", ue5_cmd=UE5, builder=builder)
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "ModularStage.uproject").write_text("{}", encoding="utf-8")
        out = fn(d)
    check("통과가 그대로 전달된다", out["ok"] is True and out["passed"] is True, str(out))
    check("검수 트리의 uproject 를 쓴다", seen["uproject"].endswith("ModularStage.uproject"),
          seen.get("uproject", ""))
    check("타깃은 <Project>Editor", seen["target"] == "ModularStageEditor", seen.get("target"))
    check("무엇으로 빌드하는지 밖에서 볼 수 있다",
          fn.build_bat.endswith("Build.bat") and fn.target == "ModularStageEditor")

    fn2 = B.local_build_fn(project="ModularStage", ue5_cmd=UE5,
                           builder=lambda *a, **k: L3.parse_build_log(BAD_LOG))
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "ModularStage.uproject").write_text("{}", encoding="utf-8")
        out2 = fn2(d)
    check("🔴 실패도 그대로 전달된다 (review 의 게이트가 이걸 본다)", out2["ok"] is False, str(out2))
    check("사람이 읽을 요약이 실린다", "BUILD" in out2.get("summary", ""), str(out2))


def main() -> int:
    for fn in (test_build_bat_derivation_is_one_rule, test_command_is_shared_with_workshop_path,
               test_verdict_ignores_exit_code, test_unconfirmed_is_not_a_pass,
               test_adapter_blocks_when_engine_missing, test_adapter_reports_missing_uproject,
               test_adapter_passes_verdict_through):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_build_local: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
