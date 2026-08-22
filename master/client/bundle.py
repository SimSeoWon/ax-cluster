"""워커 번들 — 머신별 config + 스킬을 **마스터가 생성해 배달한다** (레드마인 #21).

## [중요] 왜 마스터가 생성하는가 — 사본은 갈라진다

2026-08-09 실측: `.2` 의 워크숍에 있던 `.mcp.json` 이 `C:\\Users\\USER\\Documents\\ModularStage`
를 가리키고 있었다. 그건 **`.33` 의 경로**다(레지스트리와 글자까지 같다). 즉 한 워커의 설정이
다른 워커로 통째로 복사됐고, 계정도 경로도 다른 그쪽에서는 **전부 존재하지 않는 경로**였다.
에러 없이 죽어 있었다.

그래서 **경로를 스킬이나 문서에 박지 않는다.** 마스터가 레지스트리(각 호스트의 실제 경로를
아는 유일한 곳)를 근거로 **머신마다 다른 config 를 만들어** 배달한다.

## [중요] 능력은 선언하지 않고 잰다

`ue5` 같은 능력을 표에 손으로 적으면 그 표가 낡는다. 배달 전에 **각 머신을 프로브해서**
측정값을 config 에 넣는다 — `provision.py` 가 Ollama 에 대해 하는 것과 같은 방식이다.

## 산출물 — [중요] **체크아웃 안에 고정 경로로 둔다** (사용자 확정 2026-08-09)

    <체크아웃>/.ax/config.json            머신·프로젝트 설정. [중요] **비밀 없음**
    <체크아웃>/.ax/work/<task_id>/        작업 부산물 (로그·매니페스트 사본·중간물)
    <홈>/.claude/skills/ax-work/SKILL.md  작업 절차 (사용자 지시 1~4 의 계약)

사용자: *"프로젝트 클론한 곳 하위에 있어도 괜찮지, 근데 그거 찾는게 일이지 않니?"* — 맞다.
**cwd 안 고정 경로**라야 세 가지가 동시에 풀린다:

1. **찾을 일이 없다** — 에이전트는 항상 `./.ax/` 만 본다. 머신마다 경로가 달라도 상대경로는 같다
2. **`--add-dir` 가 필요 없다** — Claude Code 의 도구 범위가 cwd 기준이다(실측: help 원문
   *"the current directory"*). 홈에 두면 밖이라 매번 명시해야 한다
3. **워킹트리를 더럽히지 않는다** — [중요] 단, `.gitignore` 가 아니라 **`.git/info/exclude`** 에
   넣는다. 그쪽은 **커밋되지 않는 로컬 무시 목록**이라 소스 저장소에 push 할 필요가 없다
   (마스터는 push 할 수 없다 — §2.1). 부산물이 추적 파일을 더럽히면 **더티 체크가 다음 파견을
   막는다** — 지금 `.2` 가 이미 그 상태다.

스킬만 홈(`~/.claude/skills/`)에 둔다 — 절차는 프로젝트가 아니라 **머신의 능력**이고,
한 머신이 여러 프로젝트를 가질 수 있기 때문이다.

토큰은 이 번들에 넣지 않는다 — MCP 등록은 `claude mcp add --header` 가 자기 저장소에 넣는다.

## [중요] 배달했다고 믿지 않는다

`deliver()` 는 쓴 뒤 **되읽어 sha256 을 대조한다.** 저장소 하드룰(*위임한 백엔드의 "done" 을
믿지 말고 산출물을 검증하라*)이 SSH 원격 쓰기에도 그대로 적용된다 — 오늘 `move` 명령이
출력 없이 실패한 전례가 있다.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..projects.config import Registry
from . import spec

MASTER_HOST = "192.168.0.57"
SERVICES = {"task_queue": 8101, "broker": 8102, "projects": 8103}
# [중요] **표는 `spec.py` 가 소유한다** (#266). 여기 있던 정의를 옮겼다 — 같은 값이 두
#    곳에 있으면 다음에 갈린다(리포트 29 §7-5: *관례는 세기 전에 찾는다*).
SKILLS_BY_ROLE = spec.SKILLS_BY_ROLE
SKILL_NAME = "ax-work"          # (호환) 단수 참조가 남아 있는 곳

# [중요] **역할별 파이썬 페이로드** (중 2.1 `#135`, 사용자 결정 2026-08-16).
#   요청자 `.33` 의 `/review-work` 는 worktree 시뮬레이션·통합·정리 판정·검수 빌드를
#   **git 과 UE5 가 있는 곳**에서 해야 한다. 절차를 스킬 문서에만 쓰면 **로직이 두 벌**이 되고
#   다음에 갈라진다 — 마일스톤 4 가 생긴 바로 그 형태다. 그래서 모듈 자체를 배달한다.
#
#   [중요] **경로는 저장소 배치를 그대로 미러링한다** (`master/` → `axmaster/`). 평면으로 펴면
#   `build_local` 의 `from ..layer3_verify import …` 가 죽는다 — 그때 남는 선택지는 소스에
#   try/except 이중 임포트를 심는 것뿐이고, 그건 배달 때문에 **저장소 코드를 더럽히는** 짓이다.
#
#   [주의] **의존 폐포 전부**를 보낸다. 하나라도 빠지면 임포트에서 죽고, 그건 배달이 성공한 것처럼
#   보이는 실패다. 실측으로 확인한 폐포:
#       review → coordinator → branch_names
#       build_local → layer3_verify · skeleton_gate → layer3_verify
#   [중요] **토큰은 여전히 안 보낸다** — 큐·Redmine 호출은 MCP 가 한다(`review.api=` 주입).
PAYLOAD_PKG = "axmaster"

# [중요] **항목은 `(배달 상대경로, 저장소 경로)` 다** (#262, 2026-08-22). 그전까지 한 값이 두 뜻을
#    겸했고, 그래서 **저장소에서 파일을 옮기면 배달 위치가 따라 움직였다.** 배달 위치는 함부로
#    못 바꾼다 — `.33` 의 `.mcp.json` args 가 그 값이고(`mcp_entry_for`), `.2` schtasks·`.43` cron 이
#    `axmaster.work.claimer` 로 상주를 부른다(`work/claimer.py:27-28`). 둘을 갈라 두면 저장소
#    재배치(#263·#264)가 배달을 흔들지 않는다.
# [주의] **지금 두 값은 전부 같다.** 이 단계는 자리를 만드는 것이고 **동작은 바꾸지 않는다** —
#    배달 위치가 한 글자라도 달라지면 그것은 이 변경의 실패다(`test_payload_split`).


def _pair(dest: str, src: str = "") -> tuple:
    """`(배달 상대경로, 저장소 경로 — **저장소 루트 기준**)`.

    `src` 를 비우면 `master/<dest>` — 즉 **배달 트리가 `master/` 를 미러링**한다.
    [중요] 미러링이 기본인 이유는 상대 임포트다 — 평면으로 펴면 `build_local` 의
    `from ..layer3_verify import …` 가 죽는다(그 자세한 근거는 위 주석).
    [중요] 순서는 `workshop_files()` 와 **같다** — 그 함수가 이미
    `(체크아웃 기준 상대경로, 저장소 경로)` 를 돌려준다. 한 파일에 관례가 둘이면 다음에 갈린다.
    [주의] **경로가 실재하는지는 여기서 검사하지 않는다** — `payload_text()` 의
    *"배달할 모듈이 없다"* 와 테스트의 *"배달할 원문이 실재한다"* 가 이미 잡는다. 목록을
    한 벌 더 두면 그 두 벌이 갈리는 것이 새 결함이 된다.
    """
    return (dest, src or f"master/{dest}")


PAYLOAD_BY_ROLE = {
    # [중요] **배달 위치는 `clientside/` 그대로, 저장소 위치만 `client/runtime/` 이다** (#263).
    #    `.33` 의 `.mcp.json` args 가 배달 위치를 가리키므로 그것은 못 바꾼다 — 여기가 두 값을
    #    가른 것(#262)이 실제로 쓰이는 첫 자리다.
    #    [주의] claimer 사슬(`work/claimer.py`·`ax_safety`·`build_local`·`skeleton_gate`)은
    #    **`master/` 에 남는다** — `layer3_verify`(마스터도 `integrate.py` 에서 쓴다)를 상대경로로
    #    올려다보기 때문이다. 사용자 결정 ⓒ, 2026-08-22.
    "requester": (_pair("clientside/client_mcp.py", "client/runtime/client_mcp.py"),
                  _pair("clientside/ontology_cache.py", "client/runtime/ontology_cache.py"),
                  _pair("layer3_verify.py"), _pair("source_text.py"), _pair("utf8.py"),
                  _pair("work/branch_names.py"), _pair("work/coordinator.py"),
                  _pair("work/review.py"),
                  _pair("work/skeleton_gate.py"), _pair("work/build_local.py")),
    # worker (#204): 폴링 claimer + 안전 가드 + 빌드 호출 사슬. claimer 는 build 유형만
    # 집는다 (types 필터) — infer 는 현행 Flow Y(마스터 구동)가 계속 맡는다.
    "worker": (_pair("work/claimer.py"), _pair("work/ax_safety.py"),
               _pair("work/build_local.py"), _pair("work/skeleton_gate.py"),
               _pair("layer3_verify.py"),
               _pair("source_text.py"), _pair("utf8.py")),
}

AX_DIR = ".ax"                      # [중요] 체크아웃 안. 상대경로가 모든 머신에서 같다
CONFIG_REL = f"{AX_DIR}/config.json"
WORK_REL = f"{AX_DIR}/work"

# [중요] 관리 블록 마커 — 원본과 같은 방식(`project_claude_md.py` 의 `AgentWatch:Start/End`).
# **이 블록 안만 덮는다.** 밖은 사람(과 `/init`)의 것이라 절대 건드리지 않는다.
# 선언은 `spec.MD_BLOCKS` 다 (#266) — 마커 글자는 이미 배달된 파일 안에 있어 **바꿀 수 없다**.
_MD_AX = spec.md_block("ax")
MD_BEGIN = _MD_AX.begin
MD_END = _MD_AX.end
SSH_TIMEOUT = 60


class BundleError(RuntimeError):
    """배달할 수 없다. [중요] 조용히 건너뛰지 않는다."""


@dataclass
class HostFacts:
    """실측값. **선언이 아니다.**"""
    host: str
    user: str
    path: str
    driven: str
    role: str = "worker"
    os: str = ""
    home: str = ""
    claude: str = ""
    agy: bool = False
    ollama_models: int = 0
    ue5: str = ""                       # UnrealEditor-Cmd 경로. 없으면 빈 문자열
    checkout_ok: bool = False
    commit: str = ""
    errors: list = field(default_factory=list)

    @property
    def windows(self) -> bool:
        return self.os == "windows"

    @property
    def capabilities(self) -> list:
        """task_queue 의 능력 화이트리스트(`ue5`·`windows`)에 맞춘 **측정 결과**."""
        caps = []
        if self.ue5:
            caps.append("ue5")
        if self.windows:
            caps.append("windows")
        return caps

    @property
    def summary(self) -> str:
        s = (f"{self.host} ({self.user}) {self.os or '?'} · claude {self.claude or '[실패]'}"
             f" · agy {'OK' if self.agy else 'FAIL'} · ollama {self.ollama_models}종"
             f" · ue5 {'OK' if self.ue5 else 'FAIL'}")
        if self.checkout_ok:
            s += f" · 체크아웃 {self.commit or '?'}"
        else:
            s += " · [중요] 체크아웃 없음"
        if self.errors:
            s += " · [주의] " + "; ".join(self.errors[:2])
        return s


def _ssh(host: str, user: str, cmd: str, *, timeout: int = SSH_TIMEOUT) -> tuple:
    """SSH 한 번. `(rc, stdout)`. **예외를 던지지 않는다** — 실패도 사실이다."""
    try:
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", f"{user}@{host}", cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout)
        return p.returncode, (p.stdout or "").strip()
    except (subprocess.SubprocessError, OSError) as e:
        return 255, f"{type(e).__name__}: {e}"


# [중요] UE5 는 **한 곳에 있지 않다** — 실측 2026-08-09.
#
#     .2   C:\Program Files\UE_5.8\...              (소스 빌드/직접 설치)
#     .33  C:\Program Files\Epic Games\UE_5.8\...   (런처 설치)
#
# 한 경로만 보던 탓에 `.33` 이 **ue5 없음**으로 잘못 측정됐고, 능력은 층3 라우팅을 정하므로
# 그대로 뒀으면 *"UE5 를 가진 기계가 검증 못 하는 기계로 분류되는"* 상태가 된다. 표에 손으로
# 적지 않으려고 프로브를 만들었는데 **프로브 안에 경로를 박아 두면 같은 병이다.**
UE5_ROOTS = (r"C:\Program Files\Epic Games", r"C:\Program Files", r"D:\Epic Games", r"D:")
UE5_VERSIONS = ("5.8", "5.7", "5.6", "5.5", "5.4")      # 새 것 우선
UE5_REL = r"Engine\Binaries\Win64\UnrealEditor-Cmd.exe"


def ue5_globs(roots=UE5_ROOTS) -> list:
    """엔진이 설치될 만한 **디렉토리 글롭**. 버전을 나열하지 않는다 — 새 버전이 나오면
    목록이 낡는다. `UE_*` 로 훑고 **고르는 것은 파이썬에서** 한다."""
    return [f"{r}\\UE_*" for r in roots]


def _pick_ue5(paths: list, versions=UE5_VERSIONS) -> str:
    """찾은 것 중 하나. **선호 버전 우선**, 없으면 문자열 역순(대개 최신)."""
    for v in versions:
        for p in paths:
            if f"UE_{v}\\" in p or p.endswith(f"UE_{v}"):
                return p
    return sorted(paths, reverse=True)[0] if paths else ""


def _find_ue5(host: str, user: str, *, runner=None) -> str:
    """UnrealEditor-Cmd 경로. 없으면 빈 문자열. **읽기 전용, SSH 한 번.**

    [중요] **`if exist A (…) & if exist B (…)` 로 잇지 않는다.** cmd 는 괄호를 써도 `&` 뒤를
    **첫 조건의 참 분기 안**으로 넣는다 — 실측 2026-08-09: 첫 후보가 있는 `.33` 은 통과하고
    첫 후보가 없는 `.2` 는 **UE5 를 가졌는데 0줄**이었다(rc 는 양쪽 다 0이라 종료 코드로도
    구분되지 않는다). `for /d` 는 한 번에 정확히 돈다.
    """
    globs = " ".join(f'"{g}"' for g in ue5_globs())
    cmd = (f'for /d %i in ({globs}) do @if exist "%i\\{UE5_REL}" '
           f'echo %i\\{UE5_REL}')
    run = runner or (lambda c: _ssh(host, user, c))
    _rc, out = run(cmd)          # [중요] rc 로 판정하지 않는다 — 출력이 근거다
    found = [ln.strip() for ln in (out or "").splitlines()
             if ln.strip().lower().endswith("unrealeditor-cmd.exe")]
    return _pick_ue5(found)


def probe(host: str, user: str, path: str, driven: str, role: str = "worker") -> HostFacts:
    """머신 하나를 잰다. **읽기 전용** — 아무것도 바꾸지 않는다."""
    f = HostFacts(host=host, user=user, path=path, driven=driven, role=role)
    rc, out = _ssh(host, user, "uname -s 2>/dev/null || ver")
    if rc != 0 and not out:
        f.errors.append("SSH 실패")
        return f
    f.os = "windows" if ("Windows" in out or "Microsoft" in out) else "linux"

    if f.windows:
        rc, home = _ssh(host, user, "echo %USERPROFILE%")
        f.home = home.strip()
        rc, v = _ssh(host, user, r'"%USERPROFILE%\.local\bin\claude.exe" --version')
        f.claude = v.splitlines()[0].strip() if rc == 0 and v else ""
        rc, a = _ssh(host, user, r'if exist "%LOCALAPPDATA%\agy\bin\agy.exe" (echo YES) else (echo NO)')
        f.agy = "YES" in a
        f.ue5 = _find_ue5(host, user)
        rc, g = _ssh(host, user, f'cd /d {path} && git rev-parse --short HEAD')
    else:
        rc, home = _ssh(host, user, "echo $HOME")
        f.home = home.strip()
        rc, v = _ssh(host, user, "claude --version 2>/dev/null || true")
        f.claude = v.splitlines()[0].strip() if v else ""
        rc, a = _ssh(host, user, "command -v agy >/dev/null && echo YES || echo NO")
        f.agy = "YES" in a
        f.ue5 = ""                      # 리눅스 노드에 UE5 툴체인은 없다
        rc, g = _ssh(host, user, f"cd {shlex.quote(path)} && git rev-parse --short HEAD")

    f.checkout_ok = rc == 0 and bool(g) and " " not in g.strip()
    f.commit = g.strip() if f.checkout_ok else ""
    if not f.checkout_ok:
        f.errors.append(f"체크아웃을 못 읽었다: {g[:60]}")

    rc, n = _ssh(host, user, f"curl -s http://{host}:11434/api/tags")
    try:
        f.ollama_models = len(json.loads(n).get("models", [])) if rc == 0 and n else 0
    except (ValueError, AttributeError):
        f.ollama_models = 0
    return f


def _delivery_stamp() -> dict:
    """배달 시점의 마스터 정체. [중요] **배달을 막지 않는다** — 못 읽으면 사유만 싣는다."""
    try:
        from ..version import CONTRACT, identity

        idy = identity()
        return {"commit": idy.get("commit", ""), "commit_short": idy.get("commit_short", ""),
                "dirty": idy.get("dirty"), "contract": CONTRACT,
                **({"error": idy["error"]} if idy.get("error") else {})}
    except Exception as e:                                   # noqa: BLE001
        return {"commit": "", "error": f"{type(e).__name__}: {e}"}


def config_for(project: str, facts: HostFacts) -> dict:
    """머신 하나의 `.ax/config.json`. [중요] **비밀은 넣지 않는다.**"""
    return {
        "_note": "마스터가 생성해 배달한다. 손으로 고치지 말 것 — 다음 배달에 덮인다. "
                 "경로가 틀리면 마스터 레지스트리(ax-projects)를 고칠 것.",
        "_layout": {"config": f"./{CONFIG_REL}", "work": f"./{WORK_REL}/<task_id>",
                    "ignored_by": ".git/info/exclude (커밋되지 않는다)"},
        "generated_by": "master/client/bundle.py",
        # [중요] **누가 언제 배달했는지** (소 3.1.8 · `#191`). 이것이 없어서 작업장 번들이 어느
        #    마스터에서 왔는지 확인할 방법이 **전혀 없었다** — 원전이 `get_server_version` 을
        #    만든 계기와 같은 상태였다. `get_master_version_tool` 과 맞춰 드리프트를 본다.
        "delivered_by": _delivery_stamp(),
        "master": {"host": MASTER_HOST, "services": SERVICES,
                   "mcp": f"http://{MASTER_HOST}:{SERVICES['projects']}/mcp"},
        "this_host": {"host": facts.host, "user": facts.user, "os": facts.os},
        "project": project,
        "checkout": {"path": facts.path, "branch": "main"},
        "capabilities": facts.capabilities,
        "backends": {
            "claude": facts.claude or None,
            "agy": facts.agy,
            "ollama": f"http://{facts.host}:11434" if facts.ollama_models else None,
            "ollama_models": facts.ollama_models,
            "ue5_cmd": facts.ue5 or None,
        },
    }


def scp_source(facts: HostFacts, abs_path: str) -> str:
    """scp 의 원본 지정자. [중요] **윈도우 경로는 슬래시로 바꾼다.**

    실측 2026-08-09: 역슬래시를 그대로 주면 scp 가 자기 경로 검사에서
    `protocol error: filename does not match request` 로 거부한다 — **그런데 종료 코드는
    0 이다.** 즉 rc 로는 실패를 알 수 없다.
    """
    p = abs_path.replace("\\", "/") if facts.windows else abs_path
    return f"{facts.user}@{facts.host}:{p}"


def _remote_read(facts: HostFacts, abs_path: str) -> str:
    """원격 파일을 **scp 로 가져와** 읽는다. **없으면 빈 문자열, 못 읽으면 예외.**

    [중요] **셸 경유 읽기를 쓰지 않는다.** PowerShell `Get-Content` 를 SSH 로 돌렸더니 조용히
    빈 문자열이 돌아왔고, `merge_claude_md` 가 "마커 없음" 으로 오판해 **관리 블록을 두 번
    붙였다**(실측: `.2` 에 `AX:Begin` 2개).

    [중요] **그리고 그 뒤에도 같은 병이 남아 있었다** (실측 2026-08-09): 윈도우 경로를 역슬래시로
    주면 scp 가 거부하는데 **rc 가 0**이라, 이 함수가 조용히 `""` 를 돌려줬다. 그 결과
    `deliver` 는 *"기존 CLAUDE.md 가 없다"* 로 오판하고 **블록만 써서 덮었다** — 윈도우 두
    대에서 매번. 리눅스만 정상이라 **한쪽만 조용히 깨지는** 그 모양이었다.

    그래서 판정을 **rc 가 아니라 결과물**로 한다: 임시 파일을 **먼저 지우고** scp 한 뒤,
    ⑴ 생겼으면 그 내용이 진실이고(빈 파일도 정상) ⑵ 안 생겼는데 *No such file* 이면 없는
    것이며 ⑶ 그 밖은 **모르는 것이므로 예외**다. 모르는 것을 "없음" 으로 접으면 파일이 날아간다.
    """
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".axread")
    os.close(fd)
    os.unlink(tmp)                          # [중요] 존재 자체가 성공의 증거가 되게 한다
    try:
        r = subprocess.run(
            ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             scp_source(facts, abs_path), tmp],
            capture_output=True, text=True, timeout=SSH_TIMEOUT)
        if Path(tmp).exists():
            return Path(tmp).read_text(encoding="utf-8", errors="replace")
        err = ((r.stderr or "") + (r.stdout or "")).strip()
        if "No such file" in err or "not found" in err.lower():
            return ""                       # 진짜 없는 파일 — 생성 경로로 간다
        raise BundleError(
            f"{facts.host}: {abs_path} 를 읽지 못했다 (rc={r.returncode}) — {err[:160]}. "
            f"[중요] '없음' 으로 접지 않는다 — 그러면 병합이 기존 내용을 덮는다")
    except (subprocess.SubprocessError, OSError) as e:
        raise BundleError(f"{facts.host}: {abs_path} 읽기 실패 — {type(e).__name__}: {e}") from e
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass


def managed_block(project: str, facts: HostFacts) -> str:
    """머신별 AX 블록. **실측값만 들어간다.**"""
    caps = ", ".join(facts.capabilities) or "(없음)"
    build = (f"[완료] `{facts.ue5}`" if facts.ue5
             else "[실패] 없음")
    # [중요] 능력의 **결과**를 적는다. "ue5 [실패]" 만으로는 그게 무슨 뜻인지 알 수 없다.
    # [중요] **축을 UE5 로 잡지 않는다** (사용자 정정 2026-08-09).
    #
    # 이 기능의 주안점은 *"판단의 원천인 소스코드를 기반으로 Claude 가 판단한다"* 이고,
    # **그건 클론을 가진 모든 워커의 공통 능력**이다. UE5 유무는 그 다음 축(검증 가능 여부)이지
    # 워커의 급을 가르는 축이 아니다. 앞서 이 표가 UE5 를 앞세워 `.2` 만 온전한 것처럼 읽혔다.
    common = ("[중요] **소스를 근거로 판단한다** — 체크아웃 전체를 직접 읽고 선언부로 사실을 "
              "확인한다(**이것이 워커의 본령이고 모든 워커가 동등하다**) · 코드 작성·수정 · "
              "분석 · 온톨로지/문서 합성 · 로컬 LLM/`agy` 위임과 검증")
    if facts.ue5:
        can = common + " · 추가로 **UE5 C++ 빌드 · 에디터 자동화(`RunTests`) · `.uasset` 작업** · " \
                       "**층3 결정적 검증** — 여기서 쓴 코드는 여기서 판정까지 된다"
        cannot = "(없음)"
    else:
        # [중요] **못 하는 것은 컴파일이지 코드 작성이 아니다** (사용자 정정 2026-08-09).
        #    소스 클론이 여기 있으므로 읽고 쓰는 것은 전부 된다 — 판정만 못 한다.
        can = common
        cannot = ("**컴파일·에디터·자동화 테스트만** 안 된다 (리눅스, UE5 툴체인 없음). "
                  "[중요] **소스 판단·코드 작성은 다른 워커와 똑같이 된다** — 못 하는 것은 "
                  "*옳음의 최종 판정*뿐이다 → 산출물은 반드시 "
                  "`ue5` 능력을 가진 워커의 **층3 검증**을 거친다. 제출물에 "
                  "*\"이 머신에서 컴파일되지 않았다\"* 를 명시할 것. "
                  "[중요] `.uasset`·`.umap` 은 열 수도 없다 — 손대지 말 것")
    lines = [
        MD_BEGIN,
        "",
        f"## AX 클러스터 — 이 머신의 역할 (마스터 생성)",
        "",
        f"| | |",
        f"|---|---|",
        f"| 이 체크아웃 | `{facts.path}` |",
        f"| 호스트 | `{facts.host}` · 계정 `{facts.user}` · {facts.os} |",
        f"| 설정 | `./{CONFIG_REL}` — 경로·능력·백엔드의 **유일한 출처** |",
        f"| 부산물 | `./{WORK_REL}/<task_id>/` — `.git/info/exclude` 로 무시된다 |",
        f"| 능력(실측) | {caps} |",
        f"| UE5 툴체인 | {build} |",
        f"| **할 수 있는 것** | {can} |",
        f"| **할 수 없는 것** | {cannot} |",
        f"| 백엔드(실측) | claude `{facts.claude or '없음'}` · agy {'OK' if facts.agy else 'FAIL'}"
        f" · ollama {facts.ollama_models}종 |",
        f"| 마스터 | `{MASTER_HOST}` — 8101 큐 · 8102 브로커 · 8103 MCP(`ax-projects`) |",
        "",
        (f"[중요] **절차는 스킬 `{'` · `'.join(skills_for(facts.role))}` 에 있다.** "
         + ("마스터 일감을 받으면 그것부터 읽는다." if facts.role == "worker"
            else "[중요] **이 머신은 요청하는 쪽이다** — 큐에서 집지 않고, `attempt/` 브랜치를 "
                 "만들지 않는다. 등재는 **마스터 큐 한 곳으로만** 간다(단일 writer 는 서버). "
                 "[중요] **다만 「직접 처리」 차선은 여기에 있다** — 아래 분기를 보라.")),
        "",
        "[중요] **판단 기준은 소스 파일이다.** 매니페스트의 컨텍스트 문서·도메인 규범은 *어디를 볼지*",
        "알려주는 지도이지 사실의 원천이 아니다 — 시그니처·멤버명·enum 은 **선언부를 열어 확인**한다.",
        "규범과 소스가 어긋나면 **소스가 이긴다.**",
        "",
        *(["[중요] **이게 네가 로컬 모델보다 나은 지점이다.** Ollama 모델은 파일을 못 읽어 규범만 주면",
           "`CurrentStep`(실제는 `Step`) 같은 **한 글자 차이**를 지어낸다(실측). 너는 헤더를 열 수",
           "있으니 **정확한 선언을 뽑아 모델에게 넣어 주고**, 돌아온 것을 소스와 대조한다.",
           "",
           "[중요] **너 혼자 다 하지 않는다.** 대량 생성은 로컬 LLM/`agy` 에 위임하고 **너는 검증한다** —",
           "위임 결과의 \"완료\" 를 믿지 말고 산출물을 본다. 결정적 게이트가 최종 판정이다."]
          if facts.role == "worker" else
          ["[중요] **등록 전에 매니페스트의 결손을 읽는다.** *\"검색 결과가 없다\"* · *\"규범 grounding",
           "없이 진행된다\"* 가 적혀 있으면 그대로 보내지 말고 먼저 고친다 — 워커는 그 반쪽 근거로 짠다.",
           "",
           "[중요] **작업이 끝나면 되먹임을 남긴다** (원전 α′ 규약) — 코드 작업은 종료 직전(사용자",
           "최종 승인 후) `log_writer_signal`, 비자명한 의사결정·아키텍처 변경 직후엔 `log_history`.",
           "trivial(오탈자·단순 리네이밍)은 안 쓴다. 누락되면 그 작업의 패턴은 학습되지 않는다."]),
        "",
        ("[중요] **`git clean`·`reset --hard`·`main` 직접 push 금지.** 사람이 편집 중인 미커밋 파일이 "
         "있을 수 있고 `.uasset` 은 되살릴 수 없다. 작업은 `attempt/<task_id>/<workshop>/<ts>` 에서."
         if facts.role == "worker" else
         "\n".join([
             "[중요] **분기 — 직접 처리 vs 분해·분배** (원전 규칙 그대로 이식 · 사용자 재확인 2026-08-20).",
             "**결정은 사용자다. 시스템 규모는 자동 트리거가 아니다.**",
             "",
             "| 요청 | 어디서 |",
             "|---|---|",
             "| 「X 기능 구현해줘」·「이 코드 리팩터링」 — **단일 클래스·기존 클래스 미세 수정** "
             "| **여기서 직접 처리한다** — 요청한 기계가 하는 것이 빠르다 |",
             "| 「X 시스템 추가」·「Y 기능 만들어줘」 — **신규 파일 3개 이상 + 클래스 간 상속/포함/"
             "import 관계**, 또는 **여러 클래스가 묶이는 신규 시스템** | 마스터에 등재(`ax-request`)해 "
             "분해·분배 |",
             "",
             "애매하면 **a/b/c 를 모두 제시하고 사용자가 고른다** — a) 마스터 등재로 분산 · "
             "b) 여기서 직접 작성(브랜치 격리 없이 즉시, `main` 또는 사용자 지정 브랜치) · "
             "c) 작은 단위로 쪼개 직접 처리.",
             "",
             "[중요] **옵션을 환경 상태로 자동 거르지 말 것** (원전 BLOCKING) — 마스터 큐가 죽어 "
             "있어도 a 를 빼지 않는다. MCP 미연결은 환경 마찰이지 영구 제약이 아니다. 복구는 "
             "마스터에서 한다.",
             "",
             "이유(원전): 다중 클래스를 한 번에 직접 쓰면 **의사코드 단계 없이 본문까지 써버려 "
             "분산이 무의미해지고**, 반대로 모든 다중 클래스 작업을 큐에 박으면 **빠른 일회성 "
             "작업까지 오버헤드**다.",
             "",
             "[주의] **등재는 마스터 큐 한 곳으로만** — 원전의 이유 그대로: 워커 PC 가 work 를 "
             "등재하면 동일 큐가 여러 곳에 생겨 진실의 원천이 깨진다(그래서 로컬 `task_queue` "
             "등록을 2026-08-20 제거했다).",
             "",
             "[주의] 직접 처리해도 **사람이 편집 중인 트리다** — `git clean`·`reset --hard`·`main` "
             "강제 push 금지. 미커밋 `.uasset` 은 되살릴 수 없다.",
         ])),
        "",
        MD_END,
    ]
    return "\n".join(lines)


def merge_claude_md(existing: str, project: str, facts: HostFacts) -> str:
    """[중요] **관리 블록만 갈아끼운다.** 없으면 정본 본문 + 블록을 만든다.

    사용자 지시(2026-08-09): *"워커들이 클로드.md 파일이 없다면 생성하거나 있으면 마이그레이션
    하면서 추가할 내용을 고민해야겠지"*.

    - 파일이 없다 → `/init` 산출 정본 본문 + 관리 블록
    - 파일이 있고 마커가 있다 → **마커 사이만** 교체. 사람이 쓴 나머지는 그대로 둔다
    - 파일이 있고 마커가 없다 → **맨 뒤에 블록만 덧붙인다.** 기존 내용을 덮지 않는다
    """
    block = managed_block(project, facts)
    if not (existing or "").strip():
        body = (Path(__file__).with_name("payload") / "CLAUDE.md").read_text(encoding="utf-8")
        return body.rstrip() + "\n\n" + block + "\n"
    if MD_BEGIN in existing and MD_END in existing:
        # [중요] **블록이 여러 개면 전부 걷어내고 하나만 남긴다.** 읽기 실패로 두 번 붙은 파일이
        # 실제로 나왔다(`.2`, 2026-08-09). 병합이 스스로 고칠 수 있어야 한다.
        head = existing.split(MD_BEGIN)[0]
        rest = existing.split(MD_END)[-1]
        while MD_BEGIN in rest:
            rest = rest.split(MD_END)[-1] if MD_END in rest else rest.split(MD_BEGIN)[0]
        return head.rstrip() + "\n\n" + block + rest
    return existing.rstrip() + "\n\n" + block + "\n"


def _remote_write(facts: HostFacts, rel: str, content: str, *, base: str = "home") -> str:
    """원격 파일 쓰기 + **되읽어 sha256 대조.** 불일치면 예외.

    `base` — `"home"`(스킬) · `"checkout"`(config·부산물) · **`"abs"`**(`rel` 이 이미 절대경로).
    체크아웃 경로는 머신마다 다르므로 **레지스트리에서 온 값**(`facts.path`)을 쓴다. 코드에
    박지 않는다. `"abs"` 는 골조 게이트가 **격리된 worktree** 에 쓸 때 쓴다(소 1.1.5) —
    home 도 checkout 도 아닌 자리라서다.
    """
    want = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if base == "abs":
        # [중요] 절대경로는 그대로 쓴다. 해시 대조 전송은 그대로 재사용한다 — 그 검증이 실제로
        #    두 번(BOM/CRLF · stdin 미종료) 조용한 배달 사고를 잡았다.
        target = rel.replace("/", chr(92)) if facts.windows else rel
    else:
        root = facts.home if base == "home" else facts.path
        target = (f"{root}\\{rel.replace('/', chr(92))}" if facts.windows
                  else f"{root}/{rel}")
    if facts.windows:
        parent = target.rsplit("\\", 1)[0]
        mk = f'if not exist "{parent}" mkdir "{parent}"'
    else:
        parent = target.rsplit("/", 1)[0]
        mk = f"mkdir -p {shlex.quote(parent)}"
    rc, out = _ssh(facts.host, facts.user, mk)
    if rc != 0:
        raise BundleError(f"{facts.host}: 디렉토리 생성 실패 — {out[:120]}")

    # [중요] **scp 로 보낸다.** 처음엔 stdin 파이프를 썼는데 윈도우에서 두 번 물렸다:
    #   ⑴ `Set-Content -Encoding utf8` 이 **BOM 을 붙이고 CRLF 로 바꿔** 해시가 어긋났다
    #      (실측: 기대 62fc57b5 / 실측 3f797be7)
    #   ⑵ base64 + `[Console]::In.ReadToEnd()` 로 바꿨더니 **18KB 에서 stdin 이 안 닫혀 타임아웃**
    # scp 는 바이트를 그대로 옮기고 인코딩·줄바꿈을 건드리지 않는다. [중요] **검증이 두 번 다
    # 잡았다** — 없었으면 조용히 다른 파일이 배달됐을 것이다.
    import tempfile
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".ax",
                                     delete=False) as tf:
        tf.write(content)
        tmp = tf.name
    try:
        p = subprocess.run(
            ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             tmp, f"{facts.user}@{facts.host}:{target}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=SSH_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as e:
        raise BundleError(f"{facts.host}: 전송 실패 — {e}") from e
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass
    if p.returncode != 0:
        raise BundleError(f"{facts.host}: 전송 실패 — {(p.stderr or '')[:160]}")

    # [중요] 되읽어 대조한다. "썼다" 는 보고를 믿지 않는다.
    back = (f'powershell -Command "(Get-FileHash -LiteralPath \'{target}\' '
            f'-Algorithm SHA256).Hash"' if facts.windows
            else f"sha256sum {shlex.quote(target)} | cut -d' ' -f1")
    rc, got = _ssh(facts.host, facts.user, back)
    got = (got or "").strip().lower()
    if rc != 0 or got != want:
        raise BundleError(f"{facts.host}: 해시 불일치 — 기대 {want[:12]} 실측 {got[:12] or '없음'}")
    return target


def write_file(facts: HostFacts, path: str, content: str, *, base: str = "abs") -> str:
    """공개 이름 — 원격에 파일 하나를 쓰고 **해시로 대조**한다. 골조 게이트가 쓴다."""
    return _remote_write(facts, path, content, base=base)


# 이름의 선언은 `spec.MCP_BY_ROLE` 다 (#266) — 여기서는 그 한 항목의 이름만 꺼낸다.
MCP_SERVER_NAME = spec.MCP_BY_ROLE["requester"][0]


def mcp_entry_for(facts: HostFacts) -> dict:
    """`.mcp.json` 의 ax-client 항목. [중요] 경로는 상대·슬래시 — cwd 가 체크아웃 루트다.

    윈도우는 `py` 다 — 맨 `python` 은 스토어 스텁이라 버전도 안 찍는다(실측된 함정).
    """
    return {"command": "py" if facts.windows else "python3",
            "args": [f"{AX_DIR}/lib/{PAYLOAD_PKG}/clientside/client_mcp.py"]}


def merge_mcp_json(prev_text: str, facts: HostFacts) -> str:
    """기존 `.mcp.json` 에 ax-client 항목만 넣는다 — **사람이 쓴 다른 항목은 보존**한다
    (CLAUDE.md 관리 블록과 같은 규약, 원전 install_config.ps1 도 같은 방식이었다).

    [중요] 기존 파일이 깨진 JSON 이면 **덮지 않고 멈춘다** — 덮으면 사람 내용이 사라지고,
    그게 배달이 저지를 수 있는 최악이다.
    """
    txt = (prev_text or "").strip()
    if txt:
        try:
            data = json.loads(txt)
        except ValueError as e:
            raise BundleError(
                f"{facts.host}: 기존 .mcp.json 이 깨진 JSON 이다 — 덮지 않는다. "
                f"사람이 확인할 것 ({e})") from e
        if not isinstance(data, dict):
            raise BundleError(f"{facts.host}: 기존 .mcp.json 최상위가 객체가 아니다 — 덮지 않는다")
    else:
        data = {}
    servers = data.setdefault("mcpServers", {})
    servers[MCP_SERVER_NAME] = mcp_entry_for(facts)
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def skill_text(name: str = SKILL_NAME) -> str:
    p = Path(__file__).with_name("skills") / name / "SKILL.md"
    if not p.is_file():
        raise BundleError(f"스킬 원본이 없다: {p}")
    return p.read_text(encoding="utf-8")


def validate_spec(init=None) -> tuple:
    """선언과 저장소가 어긋난 곳을 **이름으로** 돌려준다. 빈 튜플이면 온전하다 (#266).

    [중요] **실측이 만든 함수다** (2026-08-22). `config.yaml` 에 없는 스킬을 선언해 `plan` 을
    돌렸더니 `skill_text` 의 `BundleError` 가 그대로 올라와 **생 트레이스백으로 죽었고**, 그
    바람에 뒤 호스트(`.43`)는 계획조차 나오지 않았다. 사유를 말해야 하는 자리에서 스택을
    보여주는 것은 *"거부도 200 + ok:false 로 말한다"* 관례에 어긋난다.

    [주의] 남의 기계를 하나도 건드리기 **전에** 부른다 — 절반 배달이 가장 고치기 어렵다.
    """
    problems = []
    root = Path(__file__).with_name("skills")
    for role in spec.SKILLS_BY_ROLE:
        for n in spec.skills_for(role, init):
            if not (root / n / "SKILL.md").is_file():
                problems.append(f"[{role}] 선언한 스킬의 원본이 없다: {n} "
                                f"({root / n / 'SKILL.md'})")
    return tuple(problems)


def payload_text(rel: str) -> str:
    """배달할 모듈 원문. `rel` 은 **저장소 루트 기준** 상대경로 (#263 부터).

    [중요] **저장소가 SSOT 다.**
    [주의] 기준이 `master/` 에서 저장소 루트로 바뀐 이유는 배달물이 `master/` 밖에도 살기
    때문이다(`client/runtime/`). 인자를 `payload_pairs()` 의 **둘째**로 받으면 자동으로 맞는다.
    """
    p = Path(__file__).resolve().parents[2] / rel
    if not p.is_file():
        raise BundleError(f"배달할 모듈이 없다: {p}")
    return p.read_text(encoding="utf-8")


def payload_dirs(role: str) -> tuple:
    """페이로드가 필요로 하는 **패키지 디렉토리**들 (`__init__.py` 를 놓을 자리).

    [중요] `__init__.py` 가 없으면 나머지는 임포트되지 않는 파일 더미가 된다 — 배달은 성공한
    것처럼 보이고 쓸 때 죽는다.
    [주의] **배달 위치 기준**이다 (#262) — 저장소 배치가 아니라 클라에 놓이는 자리를 센다.
    """
    dirs = {""}
    for dest in payloads_for(role):
        parent = str(Path(dest).parent)
        if parent not in (".", ""):
            dirs.add(parent)
    return tuple(sorted(dirs))


def payload_pairs(role: str) -> tuple:
    """이 역할이 받을 `(배달 상대경로, 저장소 경로)` 쌍들 (#262).

    [중요] **쓸 자리는 첫째, 읽을 원문은 둘째**다 — `workshop_files()` 와 순서가 같다.
    하나로 쓰면 저장소 재배치가 배달 위치를 끌고 간다 — 그것이 이 함수가 생긴 이유다.
    """
    if role not in PAYLOAD_BY_ROLE:
        raise BundleError(f"모르는 role: {role!r} (가능: {', '.join(PAYLOAD_BY_ROLE)})")
    return PAYLOAD_BY_ROLE[role]


def payloads_for(role: str) -> tuple:
    """이 역할이 받을 파이썬 모듈의 **배달 상대경로** (#262 이후 뜻이 하나다).

    [중요] 모르는 역할은 예외 (`skills_for` 와 같은 이유).
    [주의] 원문을 읽으려면 이 값이 아니라 `payload_pairs()` 의 첫째를 써야 한다 — 지금은 두
    값이 같아서 구별이 안 보이지만, 저장소가 재배치되면(#263·#264) 갈린다.
    """
    return tuple(dest for dest, _src in payload_pairs(role))


PAYLOAD_INIT = (
    '"""마스터가 배달한다. [중요] **손으로 고치지 말 것** — 다음 배달에 덮인다.\n\n'
    "저장소(`master/work/`)가 SSOT 이고 여기는 사본이다. 쓰는 법:\n\n"
    "    py -c \"import sys; sys.path.insert(0, '.ax/lib'); "
    'from axmaster.work import review\"\n"""\n'
)


# ─────────────────────────────────────────────────────────────
# 작업장 자산 (#226 4번) — 원전 `watch.exe` 가 첫 실행에 만들던 `.claude/` 구조
#
# [중요] **원전은 이것을 zip 에 넣지 않았다** — `build.bat` 이 zip 직전에 agents·skills·hooks 를
#    일부러 rmdir 하고, `watch.exe` 가 설치 시 **생성**했다(정본은 `watcher/agent_defs.py` 등
#    생성기). 우리는 생성기 대신 **저장소의 파일**을 정본으로 둔다 — 같은 배포 모델이고,
#    파일이면 diff·리뷰·3자 동기가 그대로 붙는다.
# [중요] **역할은 requester 뿐이다** (실측 2026-08-20: `.2`·`.43` 에 `.claude/agents`·`skills`
#    **0건**). 이 자산은 사람이 대화로 쓰는 절차이고, 워커는 claimer·`ax-work` 로 돈다.
#    워커에게도 필요해지면 그때 칸을 늘린다 — 안 쓰는 곳에 미리 뿌리지 않는다.
# [주의] `agents`·`skills`·`rules`·`hooks` 는 **파일째 관리**한다(원전도 매 실행 재생성했다).
#    반면 `.claude/CLAUDE.md` 는 **마커 블록만** 바꾼다 — 사람이 쓴 나머지를 날리지 않는다.
WORKSHOP_ROLES = ("requester",)
_MD_WS = spec.md_block("workshop")            # 선언은 spec.MD_BLOCKS (#266)
WORKSHOP_MD_REL = _MD_WS.rel
WS_BEGIN = _MD_WS.begin
WS_END = _MD_WS.end


def workshop_dir() -> Path:
    return Path(__file__).with_name("workshop")


def workshop_files(role: str) -> tuple:
    """이 역할이 받을 작업장 자산 — `(체크아웃 기준 상대경로, 저장소 절대경로)` 목록.

    [중요] `CLAUDE.md` 는 여기서 **제외**한다 — 병합 대상이라 쓰는 방식이 다르다.
    """
    if role not in WORKSHOP_ROLES:
        return ()
    root = workshop_dir()
    if not root.is_dir():
        return ()
    out = []
    for sub in ("agents", "skills", "rules", "hooks"):
        d = root / sub
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file():
                out.append((f".claude/{f.relative_to(root).as_posix()}", f))
    return tuple(out)


def workshop_text(src: Path) -> str:
    """자산 원문. [중요] **바이트로 읽어 개행을 보존한다** — `read_text()` 는 개행을 번역해
    읽어서 CRLF 를 LF 로 바꿔 보낸다(실측 2026-08-20에 그렇게 한 번 틀렸다). `_remote_write` 는
    `newline=""` 로 쓰므로 문자열에 든 `\r\n` 이 그대로 나간다."""
    if not src.is_file():
        raise BundleError(f"배달할 작업장 자산이 없다: {src}")
    return src.read_bytes().decode("utf-8")


def with_newlines(text: str, *, windows: bool) -> str:
    """개행을 **한 종류로** 통일한다 (윈도우 → CRLF, 그 밖 → LF).

    [중요] **병합은 개행을 섞는다.** `_remote_read` 는 `read_text()` 로 읽어 CRLF 를 **LF 로
    번역**하고(그 함수의 계약이다), 정본 파일은 CRLF 다 — 그대로 이어 붙이면 한 파일에 두
    종류가 섞인다(실측 2026-08-20: 배달 후 CRLF 362 + LF 172, 크기 172바이트 감소).
    [주의] **해시 대조는 이걸 못 잡는다** — 보낸 것과 도착한 것이 같은지만 재기 때문에,
    *"보낸 것 자체가 섞여 있었다"* 는 통과한다. 그래서 쓰기 직전에 통일한다.
    """
    flat = text.replace("\r\n", "\n").replace("\r", "\n")
    return flat.replace("\n", "\r\n") if windows else flat


def merge_workshop_md(existing: str, role: str) -> str:
    """`.claude/CLAUDE.md` — **마커 블록만** 정본으로 갈아끼운다.

    원전 `project_claude_md.py` 가 쓰던 `AgentWatch:Start/End` 마커를 그대로 쓴다.
    · 원격에 마커가 있으면 그 사이만 교체 (사람이 쓴 나머지는 그대로)
    · 마커가 없으면 **원격을 건드리지 않는다** — 어디가 관리 블록인지 모른 채 덮으면
      사람의 문서를 날린다. 대신 사유를 돌려준다(호출자가 사람에게 보여 준다)
    · 원격이 비었으면 정본을 그대로 놓는다
    """
    src = workshop_dir() / "CLAUDE.md"
    if role not in WORKSHOP_ROLES or not src.is_file():
        return ""
    canon = workshop_text(src)
    if WS_BEGIN not in canon or WS_END not in canon:
        raise BundleError(f"정본 {WORKSHOP_MD_REL} 에 관리 마커가 없다 — 배달 대상이 아니다")
    block = canon[canon.index(WS_BEGIN):canon.index(WS_END) + len(WS_END)]
    if not (existing or "").strip():
        return canon
    if WS_BEGIN in existing and WS_END in existing:
        head = existing[:existing.index(WS_BEGIN)]
        tail = existing[existing.index(WS_END) + len(WS_END):]
        return head + block + tail
    return ""          # [주의] 마커 없음 = 안 쓴다 (호출자가 사유를 싣는다)


def skills_for(role: str, init=None) -> tuple:
    """이 역할이 받을 스킬 이름들. [중요] 모르는 역할은 **빈 튜플이 아니라 예외**다 —
    조용히 아무것도 안 보내면 배달이 성공한 것처럼 보인다.

    `init` — `spec.ProjectInit`(프로젝트 절 오버레이). 안 주면 기본 표만 (#266).
    """
    if role not in SKILLS_BY_ROLE:
        raise BundleError(f"모르는 role: {role!r} (가능: {', '.join(SKILLS_BY_ROLE)})")
    return spec.skills_for(role, init)


INIT_TIMEOUT = 900


def run_init(facts: HostFacts, *, runner=None) -> dict:
    """체크아웃에서 `/init` 을 돌려 **프로젝트 유래 CLAUDE.md** 를 만든다 (레드마인 #64).

    [중요] **기본은 꺼져 있다** (`deliver(init=False)`). 실측 2026-08-09로 값을 재봤더니 값을 못 했다:

        /init 산출물   15,829자 · 클래스 언급 65 · 그래프 실재 39 · [중요] 22턴 $1.68
        payload 기본   13,325자 · 클래스 언급 55 · 그래프 실재 31 · 비용 0

    미상 목록이 **두 문서에서 글자까지 같았다** — `payload/CLAUDE.md` 자체가 예전 `/init`
    계열 산출물이기 때문이다. 새로 돌려 얻는 것은 클래스 언급 8개뿐이고 대가가 $1.68 이다.

    그러므로 값이 있는 경우는 하나다 — **payload 가 저장소 대비 낡았을 때**. 그때만
    `--init` 로 명시해 부른다. 그리고 **CLAUDE.md 가 없을 때만** 돈다(있으면 흔들지 않는다).

    왜 필요한가 — 사용자 지시였고(*"클론을 생성한 위치에서 클로드 `/init` 이 되어야 하고,
    거기 클로드 파일에 새로 추가되는 스킬이나 MCP 를 추가해줘야"*), **대가가 실측됐다**:
    프로젝트 컨텍스트가 없는 트리에서 에이전트가 방향을 잡느라 턴을 더 쓴다
    (8→5 · 12→10, 시간 26~35% 감소 · 리포트 11 §19).

    [주의] **일회성 비용이라 따로 보고한다.** 작업 비용에 섞으면 파견이 비싸 보인다.
    실패해도 배달을 막지 않는다 — AX 블록만으로도 동작은 한다(그 사실을 반환값에 적는다).
    """
    cd = f'cd /d "{facts.path}"' if facts.windows else f'cd "{facts.path}"'
    cmd = (f'{cd} && claude -p --output-format json --dangerously-skip-permissions '
           f'"/init"')
    run = runner or (lambda c: _ssh(facts.host, facts.user, c, timeout=INIT_TIMEOUT))
    rc, out = run(cmd)
    info = {"ran": True, "rc": rc, "cost_usd": 0.0, "turns": 0}
    t = (out or "").strip()
    if t.startswith("{"):
        try:
            d = json.loads(t)
            info["cost_usd"] = float(d.get("total_cost_usd") or 0.0)
            info["turns"] = int(d.get("num_turns") or 0)
        except (ValueError, TypeError):
            pass
    return info


def deliver(project: str, facts: HostFacts, *, dry_run: bool = False,
            init: bool = False, project_init=None) -> dict:
    """한 머신에 config + 스킬을 배달한다. [중요] **되읽어 대조까지가 배달이다.**

    [주의] **이름이 둘이라 헷갈리는 자리다.** `init` 은 원격에서 클로드 `/init` 을 돌릴지의
    **플래그**(`--init`)이고, `project_init` 은 `#266` 의 **사양 오버레이**(`spec.ProjectInit`)다.
    처음에 후자를 `init` 이라는 지역변수에 담아 **플래그를 가렸고**, 그러면 `--init` 없이도
    `/init` 이 도는 상태가 된다(실측 $1.68 짜리 호출이다). 이름을 갈라 둔 이유가 그것이다.

    `project_init` 을 주지 않으면 레지스트리에서 읽는다 — 그래서 **레지스트리 없이 부르려면
    명시**해야 한다(순수 유닛 테스트의 자리).
    """
    cfg = json.dumps(config_for(project, facts), ensure_ascii=False, indent=2) + "\n"
    # [중요] 프로젝트 절 오버레이 (#266) — 선언한 추가 스킬이 실제로 실리는 자리다. 선언이
    #    없으면 `EMPTY_INIT` 이라 종전과 **글자까지 같다**.
    pinit = spec.load_init(project) if project_init is None else project_init
    bad = validate_spec(pinit)
    if bad:
        raise BundleError("초기화 사양이 저장소와 어긋난다 (#266) — 배달하지 않는다:\n  "
                          + "\n  ".join(bad))
    if dry_run:
        return {"host": facts.host, "dry_run": True, "config_bytes": len(cfg),
                "skills": list(skills_for(facts.role, pinit)),
                "payload": list(payloads_for(facts.role)),
                "workshop": [rel for rel, _src in workshop_files(facts.role)]}
    # [중요] CLAUDE.md 는 **읽어서 병합**한다 — 덮어쓰면 사람이 쓴 것을 날린다
    md_path = (f"{facts.path}\\CLAUDE.md" if facts.windows else f"{facts.path}/CLAUDE.md")
    prev = _remote_read(facts, md_path)

    # [중요] 비어 있으면 **먼저 `/init`**, 그 위에 우리 블록을 얹는다 (#64).
    #    순서가 반대면 `/init` 이 우리 블록을 지우거나 감쌀 수 있다.
    init_info = {"ran": False}
    if init and not (prev or "").strip() and facts.claude:
        try:
            init_info = run_init(facts)
            prev = _remote_read(facts, md_path)          # /init 이 쓴 것을 다시 읽는다
        except Exception as e:                            # noqa: BLE001 — 배달을 막지 않는다
            init_info = {"ran": True, "error": f"{type(e).__name__}: {e}"}
    if init and not (prev or "").strip() and not facts.claude:
        init_info = {"ran": False, "error": "claude 가 없어 /init 을 돌릴 수 없다"}

    merged = merge_claude_md(prev, project, facts)
    written = {
        # [중요] config·부산물·CLAUDE.md 는 **체크아웃 안**, 스킬만 홈 (모듈 독스트링 참조)
        "config": _remote_write(facts, CONFIG_REL, cfg, base="checkout"),
        "claude_md": _remote_write(facts, "CLAUDE.md", merged, base="checkout"),
        "skills": [_remote_write(facts, f".claude/skills/{n}/SKILL.md", skill_text(n))
                   for n in skills_for(facts.role, pinit)],
        # [중요] 파이썬 페이로드 — 패키지로 둬야 모듈의 **상대 임포트가 그대로** 산다.
        #    `__init__.py` 를 먼저 쓰지 않으면 나머지는 임포트되지 않는 파일 더미가 된다.
        # [중요] 파이썬 페이로드 — 저장소 배치를 미러링한다(상대 임포트가 그대로 산다).
        #    `__init__.py` 를 **먼저** 놓는다 — 없으면 나머지는 임포트 안 되는 더미다.
        "payload": ([_remote_write(facts,
                                   f"{AX_DIR}/lib/{PAYLOAD_PKG}/{d + '/' if d else ''}__init__.py",
                                   PAYLOAD_INIT, base="checkout")
                     for d in payload_dirs(facts.role)]
                    + [_remote_write(facts, f"{AX_DIR}/lib/{PAYLOAD_PKG}/{dest}",
                                     payload_text(src), base="checkout")
                       for dest, src in payload_pairs(facts.role)]
                    ) if payload_pairs(facts.role) else [],
        "excluded": _ensure_ignored(facts),
    }
    # ── 작업장 자산 (#226 4번) — 원전 watch.exe 가 생성하던 `.claude/` 구조 ─────────
    # [중요] **손으로 맞추던 것을 배달 경로에 넣는다.** 3번 재배선까지 저장소와 `.33` 을 scp 로
    #    맞췄고, 그 상태로는 조용히 갈린다(리포트 27 §13). 배달은 되읽어 해시 대조까지 한다.
    ws = workshop_files(facts.role)
    if ws:
        written["workshop"] = [_remote_write(facts, rel, workshop_text(src), base="checkout")
                               for rel, src in ws]
        # [주의] `.claude/CLAUDE.md` 는 **마커 블록만** — 사람이 쓴 나머지를 날리지 않는다.
        prev_ws = _remote_read(facts, (f"{facts.path}\.claude\CLAUDE.md" if facts.windows
                                       else f"{facts.path}/.claude/CLAUDE.md"))
        merged_ws = merge_workshop_md(prev_ws, facts.role)
        if merged_ws:
            # [중요] 개행 통일 — 병합이 섞기 때문이다 (`with_newlines` 독스트링 참조)
            written["workshop_md"] = _remote_write(
                facts, WORKSHOP_MD_REL, with_newlines(merged_ws, windows=facts.windows),
                base="checkout")
        else:
            # [중요] 조용히 건너뛰지 않는다 — 왜 안 썼는지 말한다.
            written["workshop_md"] = ("건너뜀 — 원격 `.claude/CLAUDE.md` 에 "
                                      f"`{WS_BEGIN}` 마커가 없다 (어디가 관리 블록인지 모른 채 "
                                      "덮으면 사람의 문서를 날린다)")
    # ── 요청자 전용 (소 3.8.4): .mcp.json ─────────────
    if facts.role == "requester":
        prev_mcp = _remote_read(facts, (f"{facts.path}\\.mcp.json" if facts.windows
                                        else f"{facts.path}/.mcp.json"))
        written["mcp_json"] = _remote_write(facts, ".mcp.json",
                                            merge_mcp_json(prev_mcp, facts), base="checkout")
    # ── 역할 토큰 (#204 에서 requester 전용 → 역할 인식으로) ─────────────
    #    requester 는 클라 MCP 가, worker 는 claimer(#204)가 `.ax/token` 을 읽는다.
    #    [중요] 스코프는 큐 쪽에서 역할별로 강제된다 (auth.REQUESTER_SCOPE·WORKER_SCOPE).
    if facts.role in ("requester", "worker"):
        from .. import auth as _auth
        _rt = _auth.load_role_token(facts.role)
        if _rt:
            # [중요] 값은 출력에 싣지 않는다 — 경로만. _remote_write 가 해시로 대조한다.
            written["role_token"] = _remote_write(facts, f"{AX_DIR}/token", _rt + "\n",
                                                  base="checkout")
        else:
            written["role_token"] = (f"없음 — 마스터에서 `python -m master.auth init-role "
                                     f"{facts.role}` 후 재배달할 것")
    return {"host": facts.host, **written,
            "claude_md_mode": ("생성" if not (prev or "").strip()
                               else "블록 교체" if MD_BEGIN in (prev or "") else "블록 추가"),
            # [주의] 일회성 프로비저닝 비용 — **작업 비용과 섞지 않는다** (#64)
            "init": init_info,
            "verified": True}


def _ensure_ignored(facts: HostFacts) -> bool:
    """마스터가 체크아웃 안에 쓰는 것을 **`.git/info/exclude`** 에 넣는다 — `.gitignore` 가 아니다.

    `.gitignore` 는 커밋해야 효력이 있고 **마스터는 소스 저장소에 push 할 수 없다**(§2.1).
    `info/exclude` 는 클론 로컬이라 커밋 없이 즉시 듣는다. 이게 없으면 부산물이 워킹트리를
    더럽혀 **더티 체크가 다음 파견을 막는다.**

    목록의 선언은 `spec.GIT_EXCLUDES` 다 (#266). 이미 들어 있으면 다시 넣지 않는다(멱등).
    """
    lines = spec.git_excludes_for(facts.role)
    for line in lines:
        if facts.windows:
            cmd = (f'powershell -Command "$p=\'{facts.path}\\.git\\info\\exclude\'; '
                   f'if (-not (Test-Path $p) -or -not (Select-String -Path $p -SimpleMatch \'{line}\' -Quiet)) '
                   f'{{ Add-Content -LiteralPath $p -Value \'{line}\' }}; '
                   f'if (Select-String -Path $p -SimpleMatch \'{line}\' -Quiet) {{ echo OK }}"')
        else:
            q = shlex.quote(f"{facts.path}/.git/info/exclude")
            cmd = (f"grep -qxF {shlex.quote(line)} {q} 2>/dev/null || echo {shlex.quote(line)} >> {q}; "
                   f"grep -qxF {shlex.quote(line)} {q} && echo OK")
        rc, out = _ssh(facts.host, facts.user, cmd)
        if rc != 0 or "OK" not in out:
            raise BundleError(f"{facts.host}: .git/info/exclude 에 {line} 를 넣지 못했다 — {out[:120]}")
    return True


def tracked_managed(facts: HostFacts) -> tuple:
    """마스터가 쓰는 파일 중 **저장소가 추적 중인 것**의 이름 (#266).

    [중요] **`info/exclude` 는 추적 중인 파일에 아무 효력이 없다.** 프로젝트가 `CLAUDE.md` 를
    커밋해 두고 있으면 우리 관리 블록이 그것을 **modified** 로 만들고, 더티 체크가 다음 파견을
    막는다. 원전은 그때 index 에서 빼고 디스크를 보존했다(`_untrack_ambient_managed_files`).

    [주의] **여기서 고치지 않는다** — 사람의 저장소 인덱스를 바꾸는 일이라 이름으로 보고만
    한다. 처분은 `#259` onboard 의 확인 단계다.
    """
    names = " ".join(shlex.quote(n) if not facts.windows else n
                     for n in spec.AMBIENT_MANAGED)
    if facts.windows:
        cmd = f'cmd /c "cd /d {facts.path} && git ls-files -- {names}"'
    else:
        cmd = f"cd {shlex.quote(facts.path)} && git ls-files -- {names}"
    rc, out = _ssh(facts.host, facts.user, cmd)
    if rc != 0:
        return ()
    got = {x.strip().replace(chr(92), "/") for x in (out or "").splitlines() if x.strip()}
    return tuple(n for n in spec.AMBIENT_MANAGED if n in got)


def workshops(project: str) -> list:
    """레지스트리에서 이 프로젝트의 워크숍 목록. **경로의 유일한 출처다.**"""
    try:
        cfg = Registry.load().config_of(project)
    except Exception as e:                              # noqa: BLE001
        raise BundleError(f"프로젝트를 모른다: {project} ({e})") from e
    ws = cfg.workshops
    items = ws.values() if isinstance(ws, dict) else ws
    return [(w.host, w.user or "", w.path or "", w.driven, w.role) for w in items]
