"""플랜 빌드 단계(`#861` T2 = `#857` T7) 계약 테스트 — [중요] **다른 커밋을 빌드한 통과를 근거로
쓰지 않는가, 리비전을 모르면 빌드하지 않는가, 빌드는 서버가 SSH 로 워커에서 돌리는가.**

SSH·빌드 실행기는 가짜로 주입한다 — 실 워커·실 빌드를 두드리지 않는다.
실행: .venv/bin/python -B master/test_plan_build.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_build as PBD   # noqa: E402
from master.client import bundle       # noqa: E402

PASS = FAIL = 0

UE5 = r"C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
TREE = r"D:\trunk\ModularStage"
HEAD = "4cd229f3fcb9aa00112233445566778899aabbcc"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _facts(**over):
    f = bundle.HostFacts(host="192.168.0.2", user="janus", path=TREE, driven="ssh",
                         os="windows", home=r"C:\Users\janus", claude="2.1.222",
                         ue5=UE5, checkout_ok=True, commit="4cd229f")
    for k, v in over.items():
        setattr(f, k, v)
    return f


class FakeSsh:
    """`bundle._ssh` 대역 — HEAD 는 순서대로 내준다(빌드 전·후)."""

    def __init__(self, heads=(HEAD, HEAD), head_rc=0, status_out="", status_rc=0):
        self.heads, self.head_rc = list(heads), head_rc
        self.status_out, self.status_rc = status_out, status_rc
        self.calls: list = []

    def __call__(self, host, user, cmd):
        self.calls.append((host, user, cmd))
        if "rev-parse HEAD" in cmd:
            if self.head_rc != 0:
                return self.head_rc, "ssh: connect to host 192.168.0.2 port 22: Connection refused"
            return 0, self.heads.pop(0) if len(self.heads) > 1 else self.heads[0]
        if "status --porcelain" in cmd:
            return self.status_rc, self.status_out
        return 1, "unexpected"


class FakeBuild:
    """`run_build_on_workshop` 의 runner 대역 — UBT 로그를 돌려준다."""

    def __init__(self, ok=True, raise_timeout=False):
        self.ok, self.raise_timeout = ok, raise_timeout
        self.calls: list = []

    def __call__(self, cmd, timeout):
        self.calls.append((list(cmd), timeout))
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        out = ("Total execution time: 46.20 seconds\nResult: Succeeded\n" if self.ok else
               "Foo.cpp(12): error C2065: 'Bar': undeclared identifier\n"
               "Total execution time: 12.00 seconds\nResult: Failed (OtherCompilationError)\n")
        return subprocess.CompletedProcess(cmd, 0 if self.ok else 6, stdout=out, stderr="")


def _run(ssh=None, build=None, **kw):
    kw.setdefault("expected_commit", "4cd229f")
    kw.setdefault("kind", "unreal")
    kw.setdefault("facts", [_facts()])
    return PBD.build_step("ModularStage", ssh=ssh or FakeSsh(), build_runner=build or FakeBuild(),
                          timeout=kw.pop("timeout", 60), **kw)


def test_pass_with_matching_revision():
    s, b = FakeSsh(), FakeBuild()
    r = _run(s, b)
    check("같은 커밋 + 빌드 통과 → ok", r["ok"] and r["passed"] and r["revision_ok"]
          and r["stage"] == "done", str(r))
    check("근거에 호스트·커밋·PASS·초", all(x in r["evidence"] for x in
                                       ("192.168.0.2", "4cd229f3", "PASS", "46초")), r["evidence"])
    check("빌드는 한 번", len(b.calls) == 1, str(b.calls))
    cmd = " ".join(b.calls[0][0]) if b.calls else ""
    check("[중요] SSH 로 워커에서 Build.bat 을 부른다",
          cmd.startswith("ssh") and "janus@192.168.0.2" in cmd
          and r"C:\Program Files\UE_5.8\Engine\Build\BatchFiles\Build.bat" in cmd, cmd)
    check("타깃·uproject 가 실린다",
          "ModularStageEditor" in cmd and r"D:\trunk\ModularStage\ModularStage.uproject" in cmd, cmd)
    check("timeout 이 실행기로 간다", b.calls and b.calls[0][1] == 60)
    check("리비전은 빌드 전후로 읽는다",
          sum("rev-parse HEAD" in c[2] for c in s.calls) == 2, str(s.calls))
    check("트리 경로를 따옴표로 싣는다", all(f'"{TREE}"' in c[2] for c in s.calls), str(s.calls))
    check("build 요약이 실린다", r["build"].get("passed") is True and "raw_tail" not in r["build"],
          str(r["build"]))


def test_tree_override():
    s, b = FakeSsh(), FakeBuild()
    r = _run(s, b, tree=r"E:\other\ModularStage")
    cmd = " ".join(b.calls[0][0]) if b.calls else ""
    check("tree 를 주면 그 경로를 쓴다", r["ok"] and r"E:\other\ModularStage\ModularStage.uproject" in cmd
          and all(r'"E:\other\ModularStage"' in c[2] for c in s.calls), cmd)


def test_revision_mismatch_no_build():
    s, b = FakeSsh(heads=("deadbeef12345678",)), FakeBuild()
    r = _run(s, b)
    check("[중요] 다른 커밋이면 실패", not r["ok"] and not r["revision_ok"] and r["stage"] == "revision", str(r))
    check("[중요] 빌드하지 않는다", b.calls == [], str(b.calls))
    check("근거에 리비전 불일치", "리비전 불일치 — 기대 4cd229f" in r["evidence"], r["evidence"])


def test_revision_query_failure_no_build():
    s, b = FakeSsh(head_rc=255), FakeBuild()
    r = _run(s, b)
    check("[중요] 조회 실패는 일치가 아니다", not r["ok"] and r["stage"] == "revision"
          and not r["revision_ok"], str(r))
    check("근거에 조회 실패", "조회 실패" in r["evidence"], r["evidence"])
    check("빌드하지 않는다", b.calls == [])
    s, b = FakeSsh(heads=("fatal: not a git repository",)), FakeBuild()
    r = _run(s, b)
    check("해석 불가 HEAD 도 조회 실패", not r["ok"] and "조회 실패" in r["evidence"] and b.calls == [],
          str(r))
    s, b = FakeSsh(status_rc=128), FakeBuild()
    r = _run(s, b)
    check("상태 조회 실패도 빌드 안 함", not r["ok"] and "조회 실패" in r["evidence"] and b.calls == [],
          str(r))


def test_dirty_tree_no_build():
    s, b = FakeSsh(status_out=" M Source/ModularStage/Foo.cpp"), FakeBuild()
    r = _run(s, b)
    check("[중요] 추적 파일이 더러우면 실패", not r["ok"] and r["stage"] == "revision", str(r))
    check("빌드하지 않는다", b.calls == [])
    check("근거에 더러운 파일", "Foo.cpp" in r["evidence"], r["evidence"])


def test_build_failure():
    r = _run(build=FakeBuild(ok=False))
    check("빌드 실패 → ok False", not r["ok"] and not r["passed"] and r["revision_ok"]
          and r["stage"] == "done", str(r))
    check("근거에 FAIL·실패 사유", "FAIL" in r["evidence"] and "C2065" in r["evidence"], r["evidence"])


def test_build_timeout_is_fail():
    r = _run(build=FakeBuild(raise_timeout=True), timeout=7)
    check("[중요] 시간 초과는 FAIL", not r["ok"] and not r["passed"] and r["stage"] == "done", str(r))
    check("근거에 실패 사유(시간)", "FAIL" in r["evidence"] and "7초 안에 끝나지 않았다" in r["evidence"],
          r["evidence"])


def test_head_moved_after_build():
    s = FakeSsh(heads=(HEAD, "0123456789abcdef0123"))
    r = _run(s)
    check("[중요] 빌드 뒤 HEAD 가 움직이면 실패", not r["ok"] and r["passed"] and not r["revision_ok"],
          str(r))
    check("근거에 [리비전 변동]", "[리비전 변동]" in r["evidence"], r["evidence"])
    s = FakeSsh(heads=(HEAD, HEAD))
    s2_calls = []

    def flaky(host, user, cmd):
        s2_calls.append(cmd)
        if "rev-parse" in cmd and sum("rev-parse" in c for c in s2_calls) == 2:
            return 255, "timeout"
        return s(host, user, cmd)
    r = _run(flaky)
    check("빌드 뒤 HEAD 조회 실패도 통과로 안 읽는다", not r["ok"] and "[리비전 변동]" in r["evidence"],
          r["evidence"])


def test_no_ue5_worker():
    s, b = FakeSsh(), FakeBuild()
    r = _run(s, b, facts=[_facts(ue5=""), _facts(host="192.168.0.33", role="requester")])
    check("UE5 워커가 없으면 stage pick", not r["ok"] and r["stage"] == "pick", str(r))
    check("거절 사유를 근거에", "능력 부족" in r["evidence"] and "requester" in r["evidence"], r["evidence"])
    check("SSH·빌드 0", s.calls == [] and b.calls == [])
    r = _run(s, b, facts=[])
    check("워크숍이 비어도 stage pick", not r["ok"] and r["stage"] == "pick", str(r))


def test_no_build_bat():
    s, b = FakeSsh(), FakeBuild()
    r = _run(s, b, facts=[_facts(ue5=r"C:\weird\UnrealEditor-Cmd.exe")])
    check("Build.bat 유도 실패 → stage build · 빌드 안 함",
          not r["ok"] and r["stage"] == "build" and b.calls == [], str(r))


def test_refusals_do_no_ssh():
    s, b = FakeSsh(), FakeBuild()
    for kw, word in (({"expected_commit": ""}, "기준 리비전"), ({"kind": "code"}, "unreal"),
                     ({"kind": ""}, "unreal")):
        try:
            if kw.get("kind") == "":
                PBD.build_step("X", expected_commit="4cd229f", kind_of=lambda p: "",
                               facts=[_facts()], ssh=s, build_runner=b)
            else:
                _run(s, b, **kw)
            ok = False
        except PBD.BuildStepError as e:
            ok = word in str(e)
        check(f"{kw} → 거절", ok)
    check("거절은 SSH·빌드를 하지 않는다", s.calls == [] and b.calls == [], str(s.calls))


def test_short_commit_rules():
    check("7자 미만 접두는 같은 커밋으로 치지 않는다", not PBD._same_commit("4cd229f3", "4cd"))
    check("접두 일치(7자 이상)", PBD._same_commit("4cd229f3fcb9", "4cd229f"))
    check("빈 값은 불일치", not PBD._same_commit("", "4cd229f"))
    r = _run(expected_commit="4cd")
    check("짧은 기대 커밋으로는 통과하지 않는다", not r["ok"] and r["stage"] == "revision", str(r))


def test_source_uses_ssh_runner_not_daemon():
    src = (Path(__file__).resolve().parent / "plan_build.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    body = code.split('"""', 2)[-1]     # 모듈 docstring 뒤
    check("[중요] buildjob 을 쓰지 않는다", "buildjob" not in body)
    check("[중요] 제출 사실(/submission)을 읽지 않는다", "/submission" not in body)
    check("[중요] run_build_on_workshop( 으로 빌드한다", "run_build_on_workshop(" in body)
    check("로컬 빌드(run_build_local)를 부르지 않는다", "run_build_local(" not in src)


def main() -> int:
    for fn in (test_pass_with_matching_revision, test_tree_override,
               test_revision_mismatch_no_build, test_revision_query_failure_no_build,
               test_dirty_tree_no_build, test_build_failure, test_build_timeout_is_fail,
               test_head_moved_after_build, test_no_ue5_worker, test_no_build_bat,
               test_refusals_do_no_ssh, test_short_commit_rules,
               test_source_uses_ssh_runner_not_daemon):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_build: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
