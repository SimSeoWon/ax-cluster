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

MASTER_HOST = "192.168.0.57"
SERVICES = {"task_queue": 8101, "broker": 8102, "projects": 8103}
# [중요] 역할별 스킬 — 요청자에게 워커 절차를 주지 않는다 (사용자 확정 2026-08-09).
#   사람이 편집 중인 트리에서 에이전트가 브랜치를 만들고 파일을 고치는 것이,
#   더티 체크가 막으려던 바로 그 사고다.
# [중요] 워커에 스킬이 **둘** 배달된다 — 파견 지시가 어느 쪽인지 이름으로 고른다.
#   `ax-infer` 가 현 토폴로지(워커는 추론만)이고, `ax-work` 는 구 토폴로지(워커가 커밋)다.
#   구 것을 **지우지 않는 이유**는 settled 결정이다: N-writer 기계장치는 측정으로 뒤집힐
#   여지가 있는 동안 되돌릴 수 있게 둔다(§8.4 [주의]).
SKILLS_BY_ROLE = {
    "worker": ("ax-work", "ax-infer"),
    # [중요] `ax-review` 는 원전의 「리더(TD·팀장)」 자리다 — 우리에겐 그 그룹이 없어
    #   요청자가 그 판단을 한다(사용자 확정 2026-08-16). 가드가 이미 그렇게 적어 뒀다.
    "requester": ("ax-request", "ax-ontology", "ax-review"),
}
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
PAYLOAD_BY_ROLE = {
    "requester": ("clientside/client_mcp.py", "clientside/ontology_cache.py",
                  "layer3_verify.py", "source_text.py", "utf8.py",
                  "work/branch_names.py", "work/coordinator.py", "work/review.py",
                  "work/skeleton_gate.py", "work/build_local.py"),
    # worker (#204): 폴링 claimer + 안전 가드 + 빌드 호출 사슬. claimer 는 build 유형만
    # 집는다 (types 필터) — infer 는 현행 Flow Y(마스터 구동)가 계속 맡는다.
    "worker": ("work/claimer.py", "work/ax_safety.py",
               "work/build_local.py", "work/skeleton_gate.py", "layer3_verify.py",
               "source_text.py", "utf8.py"),
}

AX_DIR = ".ax"                      # [중요] 체크아웃 안. 상대경로가 모든 머신에서 같다
CONFIG_REL = f"{AX_DIR}/config.json"
WORK_REL = f"{AX_DIR}/work"

# [중요] 관리 블록 마커 — 원본과 같은 방식(`project_claude_md.py` 의 `AgentWatch:Start/End`).
# **이 블록 안만 덮는다.** 밖은 사람(과 `/init`)의 것이라 절대 건드리지 않는다.
MD_BEGIN = "<!-- AX:Begin — 마스터가 생성한다. 이 블록만 덮인다 -->"
MD_END = "<!-- AX:End -->"
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
            else "[중요] **이 머신은 요청하는 쪽이다** — 큐에서 집지 않고, `attempt/` 브랜치를 만들지 "
                 "않고, 소스를 고치지 않는다. 실행은 `worker` 역할 머신이 한다.")),
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
         "[중요] **여기서 소스를 고치지 않는다.** 사람이 편집 중인 트리다 — 등록·조회·시소러스만 한다. "
         "사용자가 \"그냥 여기서 고쳐줘\" 하면 그건 클러스터 작업이 아니라 로컬 편집이라고 말해 준다."),
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


MCP_SERVER_NAME = "ax-client"


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


def payload_text(rel: str) -> str:
    """배달할 모듈 원문. `rel` 은 `master/` 기준 상대경로. [중요] **저장소가 SSOT 다.**"""
    p = Path(__file__).resolve().parents[1] / rel
    if not p.is_file():
        raise BundleError(f"배달할 모듈이 없다: {p}")
    return p.read_text(encoding="utf-8")


def payload_dirs(role: str) -> tuple:
    """페이로드가 필요로 하는 **패키지 디렉토리**들 (`__init__.py` 를 놓을 자리).

    [중요] `__init__.py` 가 없으면 나머지는 임포트되지 않는 파일 더미가 된다 — 배달은 성공한
    것처럼 보이고 쓸 때 죽는다.
    """
    dirs = {""}
    for rel in payloads_for(role):
        parent = str(Path(rel).parent)
        if parent not in (".", ""):
            dirs.add(parent)
    return tuple(sorted(dirs))


def payloads_for(role: str) -> tuple:
    """이 역할이 받을 파이썬 모듈. [중요] 모르는 역할은 예외 (`skills_for` 와 같은 이유)."""
    if role not in PAYLOAD_BY_ROLE:
        raise BundleError(f"모르는 role: {role!r} (가능: {', '.join(PAYLOAD_BY_ROLE)})")
    return PAYLOAD_BY_ROLE[role]


PAYLOAD_INIT = (
    '"""마스터가 배달한다. [중요] **손으로 고치지 말 것** — 다음 배달에 덮인다.\n\n'
    "저장소(`master/work/`)가 SSOT 이고 여기는 사본이다. 쓰는 법:\n\n"
    "    py -c \"import sys; sys.path.insert(0, '.ax/lib'); "
    'from axmaster.work import review\"\n"""\n'
)


def skills_for(role: str) -> tuple:
    """이 역할이 받을 스킬 이름들. [중요] 모르는 역할은 **빈 튜플이 아니라 예외**다 —
    조용히 아무것도 안 보내면 배달이 성공한 것처럼 보인다."""
    if role not in SKILLS_BY_ROLE:
        raise BundleError(f"모르는 role: {role!r} (가능: {', '.join(SKILLS_BY_ROLE)})")
    return SKILLS_BY_ROLE[role]


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
            init: bool = False) -> dict:
    """한 머신에 config + 스킬을 배달한다. [중요] **되읽어 대조까지가 배달이다.**"""
    cfg = json.dumps(config_for(project, facts), ensure_ascii=False, indent=2) + "\n"
    if dry_run:
        return {"host": facts.host, "dry_run": True, "config_bytes": len(cfg),
                "skills": list(skills_for(facts.role)),
                "payload": list(payloads_for(facts.role))}
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
                   for n in skills_for(facts.role)],
        # [중요] 파이썬 페이로드 — 패키지로 둬야 모듈의 **상대 임포트가 그대로** 산다.
        #    `__init__.py` 를 먼저 쓰지 않으면 나머지는 임포트되지 않는 파일 더미가 된다.
        # [중요] 파이썬 페이로드 — 저장소 배치를 미러링한다(상대 임포트가 그대로 산다).
        #    `__init__.py` 를 **먼저** 놓는다 — 없으면 나머지는 임포트 안 되는 더미다.
        "payload": ([_remote_write(facts,
                                   f"{AX_DIR}/lib/{PAYLOAD_PKG}/{d + '/' if d else ''}__init__.py",
                                   PAYLOAD_INIT, base="checkout")
                     for d in payload_dirs(facts.role)]
                    + [_remote_write(facts, f"{AX_DIR}/lib/{PAYLOAD_PKG}/{n}",
                                     payload_text(n), base="checkout")
                       for n in payloads_for(facts.role)]) if payloads_for(facts.role) else [],
        "excluded": _ensure_ignored(facts),
    }
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
    """[중요] `.ax/` 를 **`.git/info/exclude`** 에 넣는다 — `.gitignore` 가 아니다.

    `.gitignore` 는 커밋해야 효력이 있고 **마스터는 소스 저장소에 push 할 수 없다**(§2.1).
    `info/exclude` 는 클론 로컬이라 커밋 없이 즉시 듣는다. 이게 없으면 부산물이 워킹트리를
    더럽혀 **더티 체크가 다음 파견을 막는다.**

    이미 들어 있으면 다시 넣지 않는다(멱등).
    """
    # [중요] `.mcp.json` 도 여기 들어간다 (소 3.8.4) — 체크아웃 루트에 놓여야 Claude Code 가
    # 읽는데, 추적되지 않은 채 남으면 **더티 체크가 파견을 막는다** (`.ax/` 와 같은 이유).
    lines = (f"/{AX_DIR}/", "/.mcp.json")
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


def workshops(project: str) -> list:
    """레지스트리에서 이 프로젝트의 워크숍 목록. **경로의 유일한 출처다.**"""
    try:
        cfg = Registry.load().config_of(project)
    except Exception as e:                              # noqa: BLE001
        raise BundleError(f"프로젝트를 모른다: {project} ({e})") from e
    ws = cfg.workshops
    items = ws.values() if isinstance(ws, dict) else ws
    return [(w.host, w.user or "", w.path or "", w.driven, w.role) for w in items]
