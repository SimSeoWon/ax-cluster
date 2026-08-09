"""워크숍 더티 체크 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_workshop_check.py

SSH 를 타지 않는다. `runner` 를 주입해 `git status --porcelain` 출력을 흉내낸다 —
검사 대상은 **판정 규칙**이지 SSH 가 아니다.

🔴 이 테스트가 지키는 불변식 (PLAN §5.5.4-⑥-1):
   1. 추적 파일 변경은 차단, 미추적(`??`)은 통과
   2. 검사에 실패하면 통과가 아니라 **차단** (fail-closed)
   3. 이 모듈은 아무것도 고치지 않는다 — `git clean` 을 부를 경로가 없어야 한다
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ax-wscheck-test-"))
os.environ["AX_PROJECTS_ROOT"] = str(_TMP / "root")
os.environ["AX_GITEA_REPO_ROOT"] = str(_TMP / "gitea")

from master.projects.config import DRIVEN_INTERACTIVE, DRIVEN_SSH, Workshop  # noqa: E402
from master.projects.workshop_check import (  # noqa: E402
    check_workshop,
    parse_porcelain,
)

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def fake(stdout: str = "", *, rc: int = 0, stderr: str = "", raises=None):
    """`runner` 대역. 마지막으로 받은 argv 를 `.cmd` 에 남긴다."""

    def run(cmd, timeout):
        run.cmd = list(cmd)
        run.timeout = timeout
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)

    run.cmd = []
    run.timeout = None
    return run


SSH_SHOP = Workshop(
    host="192.168.0.2", driven=DRIVEN_SSH, user="janus", path=r"E:\trunk\ModularStage"
)



def test_scope() -> None:
    """🔴 범위는 `Source/` 하위 — 색인·그래프와 같은 경계다 (사용자 결정 2026-08-09)."""
    print("\n[9] 🔴 더티 판정 범위는 Source/ 하위다")

    # 실측 재현: .2 를 막고 있던 그 3건 (전부 저장소 루트의 툴체인 재생성물)
    real = (" M Automation_ModularStage.slnx\n M ModularStage.slnx\n"
            " M ModularStage.uproject\n?? AgentWiki.zip\n")
    r = check_workshop(SSH_SHOP, runner=fake(real))
    check("🔴 툴체인 재생성물은 차단하지 않는다", r.ok, r.reason)
    check("차단 목록은 비어 있다", r.blocking == [], str(r.blocking))
    # 🔴 차단하지 않는 것과 못 본 것은 다르다
    check("🔴 범위 밖 3건을 세어서 들고 있다", len(r.out_of_scope) == 3, str(r.out_of_scope))
    check("🔴 판정문에 범위 밖을 남긴다", "범위 밖 추적 변경 3건" in r.reason, r.reason)
    check("🔴 판정문에 범위를 밝힌다 (전체로 오해 금지)", "Source/" in r.reason, r.reason)

    # 범위 안이면 여전히 막는다 — 게이트를 없앤 게 아니다
    mix = " M Source/Foo.cpp\n M ModularStage.uproject\n"
    r2 = check_workshop(SSH_SHOP, runner=fake(mix))
    check("🔴 Source/ 안은 그대로 차단한다", not r2.ok, r2.reason)
    check("차단 목록엔 범위 안만", r2.blocking == [" M Source/Foo.cpp"], str(r2.blocking))
    check("범위 밖은 따로 센다", len(r2.out_of_scope) == 1, str(r2.out_of_scope))

    # 이름변경은 **새 경로**로 판정한다
    ren = check_workshop(SSH_SHOP, runner=fake("R  old.cpp -> Source/new.cpp\n"))
    check("🔴 rename 은 새 경로로 본다", not ren.ok, str(ren.blocking))

    # 범위는 주입 가능하다
    wide = check_workshop(SSH_SHOP, runner=fake(" M Content/A.uasset\n"),
                          scope=("Source/", "Content/"))
    check("범위를 넓히면 다시 막는다", not wide.ok, wide.reason)


def main() -> int:
    print("[1] porcelain 파싱 — 추적 vs 미추적")
    blocking, untracked = parse_porcelain(
        " M Source/Foo.cpp\n"
        "A  Source/Bar.h\n"
        "?? AgentWiki/\n"
        "?? AgentWiki.zip\n"
    )
    check("추적 변경 2건", len(blocking) == 2, str(blocking))
    check("미추적 2건", untracked == ["AgentWiki/", "AgentWiki.zip"], str(untracked))
    check("빈 출력은 둘 다 0", parse_porcelain("") == ([], []))
    check("공백 줄 무시", parse_porcelain("\n  \n") == ([], []))

    print("\n[2] 🔴 미추적만 있으면 통과한다 (실측 상태 재현)")
    # .2 의 실제 상태: ?? AgentWiki/ · ?? AgentWiki.zip 뿐이다.
    # 뭉뚱그려 막았다면 자동화가 첫날부터 아무것도 못 했다.
    r = check_workshop(SSH_SHOP, runner=fake("?? AgentWiki/\n?? AgentWiki.zip\n"))
    check("ok=True", r.ok, r.reason)
    check("checked=True", r.checked)
    check("차단 없음", r.blocking == [], str(r.blocking))
    check("미추적 2건 보고", len(r.untracked) == 2, str(r.untracked))
    check("git clean 금지를 사유에 명시", "git clean" in r.reason, r.reason)

    print("\n[3] 🔴 추적 파일이 더러우면 차단한다")
    r = check_workshop(SSH_SHOP, runner=fake(" M Source/Foo.cpp\n?? scratch.txt\n"))
    check("ok=False", not r.ok, r.reason)
    check("checked=True (검사는 됐다)", r.checked)
    check("차단 목록에 추적 변경", r.blocking == [" M Source/Foo.cpp"], str(r.blocking))
    check("미추적은 따로 보고", r.untracked == ["scratch.txt"], str(r.untracked))
    for code in (" M", "M ", "A ", "MM", " D", "R "):
        rr = check_workshop(SSH_SHOP, runner=fake(f"{code} Source/x\n"))
        check(f"  {code!r} 는 차단", not rr.ok)

    print("\n[4] 깨끗하면 통과")
    r = check_workshop(SSH_SHOP, runner=fake(""))
    check("ok=True", r.ok, r.reason)
    check("미추적 언급 없음", "미추적" not in r.reason, r.reason)

    print("\n[5] 🔴 fail-closed — 확인 못 하면 통과가 아니다")
    r = check_workshop(SSH_SHOP, runner=fake("", rc=128, stderr="fatal: not a git repository"))
    check("git 실패 → 차단", not r.ok and not r.checked, r.reason)
    check("사유에 원문", "not a git repository" in r.reason, r.reason)

    r = check_workshop(
        SSH_SHOP, runner=fake(raises=subprocess.TimeoutExpired("ssh", 20)), timeout=20
    )
    check("타임아웃 → 차단", not r.ok and not r.checked, r.reason)
    check("타임아웃 사유 명시", "응답하지 않" in r.reason, r.reason)

    r = check_workshop(SSH_SHOP, runner=fake(raises=OSError("ssh: command not found")))
    check("SSH 실행 실패 → 차단", not r.ok and not r.checked, r.reason)

    # 🔴 가장 중요한 회귀: 실패 경로가 절대 ok=True 를 내면 안 된다.
    for bad in (
        fake("", rc=1),
        fake("", rc=255, stderr="Permission denied (publickey)."),
        fake(raises=subprocess.TimeoutExpired("ssh", 20)),
        fake(raises=OSError("boom")),
    ):
        check("  실패 경로는 절대 ok=True 가 아니다", not check_workshop(SSH_SHOP, runner=bad).ok)

    print("\n[6] 설정이 깨졌거나 대상이 아니면 몰지 않는다")
    r = check_workshop(Workshop(host="192.168.0.33", driven=DRIVEN_INTERACTIVE))
    check("interactive 는 검사 대상 아님", not r.ok and not r.checked, r.reason)
    check("사유가 '차단'이 아니라 '해당 없음'", "몰지 않는다" in r.reason, r.reason)
    r = check_workshop(Workshop(host="h", driven=DRIVEN_SSH, user="u"), runner=fake(""))
    check("ssh 인데 path 없으면 차단", not r.ok, r.reason)

    print("\n[7] 실제로 만드는 명령 — 읽기 전용이어야 한다")
    f = fake("")
    check_workshop(SSH_SHOP, runner=f)
    joined = " ".join(f.cmd)
    check("ssh 를 쓴다", f.cmd[0] == "ssh", joined)
    check("BatchMode — 비밀번호 프롬프트로 매달리지 않는다", "BatchMode=yes" in joined)
    check("계정@호스트", "janus@192.168.0.2" in joined, joined)
    check("경로가 원문 그대로(백슬래시 유지)", r"E:\trunk\ModularStage" in joined, joined)
    check("status --porcelain 만 부른다", "status --porcelain" in joined, joined)
    check("🔴 clean 을 부르지 않는다", "clean" not in joined, joined)
    check("🔴 reset 을 부르지 않는다", "reset" not in joined, joined)
    check("🔴 checkout 을 부르지 않는다", "checkout" not in joined, joined)
    check("타임아웃 전달됨", f.timeout == 20, str(f.timeout))

    print("\n[8] 🔴 어떤 입력에도 고치려 들지 않는다 — 호출 횟수와 argv 로 검증")
    # 문자열을 훑는 대신 **행위**를 본다: 무슨 상태를 받아도 명령은 정확히 한 번,
    # 그리고 그 한 번은 언제나 읽기 전용이어야 한다. "더러우니 정리하고 재시도" 같은
    # 경로가 생기면 여기서 걸린다.
    SCENARIOS = {
        "깨끗": "",
        "미추적만": "?? a\n?? b/\n",
        "추적 더러움": " M x\nA y\n",
        "섞임": " M x\n?? y\n",
        "대량": "".join(f" M f{i}\n" for i in range(50)),
    }
    for label, out in SCENARIOS.items():
        calls: list[list[str]] = []

        def rec(cmd, timeout, _c=calls):
            _c.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, out, "")

        check_workshop(SSH_SHOP, runner=rec)
        joined_all = " ".join(" ".join(c) for c in calls)
        ok = (
            len(calls) == 1
            and "status --porcelain" in joined_all
            and not any(v in joined_all for v in ("clean", "reset", "checkout", "restore"))
        )
        check(f"  '{label}' → 읽기 전용 1회만", ok, f"{len(calls)}회: {joined_all}")

    test_scope()

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
