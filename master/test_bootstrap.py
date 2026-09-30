"""체크아웃 부트스트랩 (`#254`) — 명령 조립과 역할별 갈림.

[중요] **NS 라이브 런이 이 파일의 내용을 정했다** (리포트 31). 함정 셋이 실물에서 나왔고,
셋 다 우리 코드의 논리 오류가 아니라 **환경**이었다 — 유닛으로는 절대 안 나오는 부류다.
그래서 여기서 재는 것은 *"그 환경에 맞는 명령을 조립하는가"* 다.

    ⓐ 윈도우 소유권    `.33`·`.2` 두 대에서 `.git` 이 `BUILTIN\\Administrators` 소유가 됐다
    ⓑ 빈 저장소 브랜치  커밋 0개면 로컬 기본값(`master`)으로 잡힌다 — 우리 설정은 `main`
    ⓒ LFS 는 역할별     빌드 기계는 실물(134MB), 판단 기계는 포인터(4MB)

`python3 master/test_bootstrap.py`
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client.init import bootstrap as B                              # noqa: E402
from master.client.bundle import HostFacts                          # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _cfg(branch="main", url="gitea@h:Sim/NS.git", name="NS"):
    return types.SimpleNamespace(branch=branch, clone_url=url, name=name)


def _facts(*, windows, ue5="", codex="", path="/p/NS", ok=False):
    return HostFacts(host="h", user="u", path=path, driven="ssh", role="worker",
                     os="windows" if windows else "linux", ue5=ue5, codex=codex,
                     checkout_ok=ok)


def test_needs_and_plan() -> None:
    """[중요] 체크아웃이 없으면 **계획에 배달 항목으로** 나와야 한다 (완료 조건 1)."""
    f = _facts(windows=False, ok=False)
    check("없으면 대상이다", B.needs_bootstrap(f))
    check("있으면 대상이 아니다", not B.needs_bootstrap(_facts(windows=False, ok=True)))
    lines = B.plan_lines(f, _cfg())
    check("계획 줄이 난다", len(lines) >= 2, str(lines))
    check("무엇을 클론할지 든다", "gitea@h:Sim/NS.git" in lines[0], lines[0])
    check("브랜치를 든다", "main" in lines[0], lines[0])
    check("[중요] 빈 저장소 브랜치 함정을 계획에 적는다",
          any("master" in l for l in lines), str(lines))
    check("있으면 계획 줄이 없다", B.plan_lines(_facts(windows=False, ok=True), _cfg()) == [])


def test_lfs_is_role_based() -> None:
    """[중요] **역할별로 갈린다** — 선언이 아니라 `ue5` **probe 실측**으로 판정한다."""
    check("빌드 기계는 실물", B.wants_lfs(_facts(windows=True, ue5="C:/UE/cmd.exe")))
    check("[중요] UE5 없는 기계는 포인터", not B.wants_lfs(_facts(windows=False)))

    ptr = dict(B.commands(_facts(windows=False), _cfg()))
    check("포인터 기계는 smudge 를 끈다", "GIT_LFS_SKIP_SMUDGE=1" in ptr["clone"], ptr["clone"])
    real = dict(B.commands(_facts(windows=True, ue5="x", path=r"E:\t\NS"), _cfg()))
    check("[중요] 빌드 기계는 끄지 않는다 (에셋이 필요하다)",
          "GIT_LFS_SKIP_SMUDGE" not in real["clone"], real["clone"])


def test_windows_ownership() -> None:
    """[중요] 소유권 교정이 **윈도우에만** 붙고, 소유자를 **원격에서 평가**한다."""
    win = dict(B.commands(_facts(windows=True, ue5="x", path=r"E:\t\NS"), _cfg()))
    check("윈도우엔 owner 단계가 있다", "owner" in win)
    check("[중요] icacls /setowner 를 쓴다 (safe.directory 로 덮지 않는다)",
          "/setowner" in win["owner"] and "safe.directory" not in win["owner"], win["owner"])
    check("[중요] 소유자를 원격에서 평가한다 (컴퓨터 이름을 표로 들지 않는다)",
          "%COMPUTERNAME%" in win["owner"] and "%USERNAME%" in win["owner"], win["owner"])
    check("🔴 `%USERDOMAIN%` 을 쓰지 않는다 — SSH 에선 WORKGROUP 으로 풀린다 (`#695` 실측)",
          "%USERDOMAIN%" not in win["owner"], win["owner"])
    check("재귀·계속 플래그", "/T" in win["owner"] and "/C" in win["owner"], win["owner"])

    lin = dict(B.commands(_facts(windows=False), _cfg()))
    check("[주의] 리눅스엔 owner 단계가 없다", "owner" not in lin, str(list(lin)))


def test_windows_codex_acl() -> None:
    """`#695` — codex 가 있는 Windows 클론은 샌드박스 수정 ACE 를 받는다."""
    win = dict(B.commands(_facts(windows=True, codex="codex-cli 0.test",
                                 path=r"E:\t\NS"), _cfg()))
    check("codex Windows엔 ACL 단계가 있다", "codex_acl" in win, str(list(win)))
    acl = win.get("codex_acl", "")
    check("CodexSandboxUsers 로컬 그룹에 주고 기계 이름은 원격 평가",
          "%COMPUTERNAME%\CodexSandboxUsers" in acl, acl)
    check("하위 파일·디렉터리에 수정 권한 상속",
          "(OI)(CI)(M)" in acl and "/T" in acl and "/C" in acl, acl)
    check("codex 없는 Windows엔 없는 로컬 그룹을 요구하지 않는다",
          "codex_acl" not in dict(B.commands(_facts(windows=True, path=r"E:\t\NS"), _cfg())))
    check("리눅스에는 codex 가 있어도 Windows ACL 단계가 없다",
          "codex_acl" not in dict(B.commands(_facts(windows=False, codex="codex"), _cfg())))
    lines = B.plan_lines(_facts(windows=True, codex="codex", path=r"E:\t\NS"), _cfg())
    check("계획에 Codex 쓰기 권한이 보인다",
          any("CodexSandboxUsers" in line for line in lines), str(lines))


def test_empty_repo_branch() -> None:
    """[중요] 빈 저장소는 로컬 기본값(`master`)으로 잡힌다 → HEAD 를 맞춘다."""
    for win, path in ((False, "/p/NS"), (True, r"E:\t\NS")):
        cmds = dict(B.commands(_facts(windows=win, ue5="x" if win else "", path=path), _cfg()))
        check(f"branch 단계가 있다 (windows={win})", "branch" in cmds)
        check(f"symbolic-ref 로 맞춘다 (windows={win})",
              "symbolic-ref HEAD refs/heads/main" in cmds["branch"], cmds["branch"])
    # 다른 브랜치를 설정하면 그 값을 쓴다 — `main` 을 박지 않는다
    cmds = dict(B.commands(_facts(windows=False), _cfg(branch="dev")))
    check("[주의] 설정의 branch 를 쓴다 (main 하드코딩 아님)",
          "refs/heads/dev" in cmds["branch"] and "-b dev" in cmds["clone"], str(cmds))


def test_path_split() -> None:
    """[주의] 윈도우 경로를 posix 구분자로 자르면 통째로 남는다 — 구분자를 골라야 한다."""
    check("윈도우", B._split(r"E:\trunk\NS", True) == (r"E:\trunk", "NS"),
          str(B._split(r"E:\trunk\NS", True)))
    check("윈도우 깊은 경로",
          B._split(r"C:\Users\USER\Documents\NS", True) == (r"C:\Users\USER\Documents", "NS"))
    check("리눅스", B._split("/home/sim/trunk/NS", False) == ("/home/sim/trunk", "NS"))
    check("끝 구분자 허용", B._split("/home/sim/trunk/NS/", False) == ("/home/sim/trunk", "NS"))
    # 부모 디렉토리를 먼저 만든다 — 없으면 클론이 실패한다
    cmds = dict(B.commands(_facts(windows=False), _cfg()))
    check("부모를 먼저 만든다", cmds["mkdir"].startswith("mkdir -p"), cmds["mkdir"])


def test_clone_url_required() -> None:
    """[중요] `clone_url` 이 비면 **거부한다** — bare 경로는 그 기계에 없다."""
    try:
        B.commands(_facts(windows=False), _cfg(url=""))
        check("[중요] clone_url 없으면 거부", False, "통과해버렸다")
    except ValueError as e:
        check("clone_url 없으면 거부", "clone_url" in str(e), str(e))


def test_probe_stays_read_only() -> None:
    """[중요] `probe` 의 「읽기 전용」 계약을 깨지 않았다 (`#254` [주의])."""
    import inspect
    from master.client import bundle
    src = inspect.getsource(bundle.probe)
    for bad in ("git clone", "mkdir", "icacls", "symbolic-ref"):
        check(f"probe 가 {bad} 를 하지 않는다", bad not in src)
    check("독스트링이 읽기 전용을 말한다", "읽기 전용" in (bundle.probe.__doc__ or ""))
    # 부트스트랩은 **별 함수**다
    check("별 단계로 있다", callable(getattr(bundle, "bootstrap_checkout", None)))
    bsrc = inspect.getsource(bundle.bootstrap_checkout)
    check("[중요] 놓은 뒤 다시 재서 확인한다 (「했다」를 믿지 않는다)",
          "probe(" in bsrc and "checkout_ok" in bsrc)
    check("클론 실패를 삼키지 않는다", "클론 실패" in bsrc)


def test_owner_failure_is_a_failure() -> None:
    """🔴 `#695` — 소유권 교정이 rc≠0 이면 **실패로 올린다**(종전: 사유만 남기고 aligned)."""
    from master.client import bundle
    saved = bundle._ssh, B.needs_bootstrap, bundle.probe
    calls = []

    def fake_ssh(host, user, cmd, timeout=0):
        calls.append(cmd)
        return (52, "0 files processed; 0 failed") if "/setowner" in cmd else (0, "")

    class _After:
        checkout_ok, commit, errors = True, "abc1234", []

    bundle._ssh, B.needs_bootstrap = fake_ssh, (lambda f: True)
    bundle.probe = lambda *a, **k: _After()
    try:
        try:
            bundle.bootstrap_checkout("X", _facts(windows=True, ue5="x", path=r"E:\t\X"), cfg=_cfg())
            check("🔴 owner rc≠0 → BundleError", False, "예외가 안 났다")
        except bundle.BundleError as e:
            check("🔴 owner rc≠0 → BundleError", "소유권 교정 실패" in str(e) and "rc=52" in str(e), str(e))
        check("  클론은 그 전에 돌았다 (클론을 되돌리지 않는다)", any("git clone" in c for c in calls))
        bundle._ssh = lambda h, u, c, timeout=0: (0, "")
        r = bundle.bootstrap_checkout("X", _facts(windows=True, ue5="x", path=r"E:\t\X"), cfg=_cfg())
        check("  owner rc=0 이면 종전 그대로 통과", r.get("commit") == "abc1234", str(r))
    finally:
        bundle._ssh, B.needs_bootstrap, bundle.probe = saved


def test_codex_acl_failure_is_a_failure() -> None:
    """`#695` — ACL grant 실패를 성공으로 접지 않는다."""
    from master.client import bundle
    saved = bundle._ssh, B.needs_bootstrap, bundle.probe
    calls = []

    def fake_ssh(host, user, cmd, timeout=0):
        calls.append((cmd, timeout))
        if "CodexSandboxUsers" in cmd:
            return 5, "Access is denied"
        return 0, ""

    class _After:
        checkout_ok, commit, errors = True, "abc1234", []

    bundle._ssh, B.needs_bootstrap = fake_ssh, (lambda f: True)
    bundle.probe = lambda *a, **k: _After()
    facts = _facts(windows=True, ue5="x", codex="codex-cli 0.test", path=r"E:\t\X")
    try:
        try:
            bundle.bootstrap_checkout("X", facts, cfg=_cfg())
            check("codex ACL rc≠0 → BundleError", False, "예외가 안 났다")
        except bundle.BundleError as e:
            check("codex ACL rc≠0 → BundleError",
                  "Codex 샌드박스 쓰기 권한 설정 실패" in str(e) and "rc=5" in str(e),
                  str(e))
        acl_calls = [(cmd, timeout) for cmd, timeout in calls if "CodexSandboxUsers" in cmd]
        check("ACL 단계는 소유권 교정과 같은 긴 timeout",
              bool(acl_calls) and acl_calls[0][1] == B.OWNER_TIMEOUT, str(acl_calls))
        check("ACL 실패 뒤 branch·probe로 진행하지 않는다",
              not any("symbolic-ref" in cmd for cmd, _timeout in calls), str(calls))
    finally:
        bundle._ssh, B.needs_bootstrap, bundle.probe = saved


if __name__ == "__main__":
    for fn in (test_needs_and_plan, test_lfs_is_role_based, test_windows_ownership,
               test_windows_codex_acl,
               test_empty_repo_branch, test_path_split, test_clone_url_required,
               test_probe_stays_read_only, test_owner_failure_is_a_failure,
               test_codex_acl_failure_is_a_failure):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_bootstrap: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
