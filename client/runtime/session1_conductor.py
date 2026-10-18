"""세션 1 지휘자 런처 — 윈도우 워커에서 지휘자(`codex exec` · `claude -p`)를 **로그온 세션**에서 돌린다
(`#401` codex · `#832` claude).

## 왜 필요한가 (실측 2026-09-12)

Windows OpenSSH 는 **세션 0** 에서 프로세스를 만들고, 거기서는 codex 의 제한 토큰 샌드박스
자식이 `0xC0000142` 로 죽는다. 그래서 SSH 로 민 지휘자는 `ax-work` SKILL.md **조차 읽지
못한 채** 본문을 썼고 층1 이 막았다(그날 조각 2건이 그렇게 죽었다).

    SSH 가 직접 실행                세션 0   ❌ 0xC0000142
    SSH → schtasks /run (`/IT`)     세션 1   ✅ exit_code 0 · turn.completed

`/IT` 로 등록된 작업은 SSH 가 **부탁만** 하고 프로세스는 스케줄러가 세션 1 에 만든다.

🔴 `#832` (사용자 결정 2026-10-18) — **claude 모드도 이 길로 온다.** claude 자체는 세션 0 에서도
돌지만(파일 자격, `#721`) ax-work 스킬대로 agy 에 위임하면 agy 가 세션 0 에서 로그인을 못 본다
(*"You are not logged into Antigravity"*). 아래 agy 중계를 claude 도 받으려고 같은 런처를 탄다.
[주의] 범위는 codex·claude 둘뿐이다 — 범용 런처가 아니다(`MODES`).

## 🔴 [중요] 이 파일은 **명령을 받지 않는다**

마스터가 주는 것은 `job.json` 의 **`task_id`·`files`·`mode` 같은 데이터뿐**이고, **실행 파일과
플래그는 이 런처가 소유한다.** `mode` 는 허용 목록(`MODES`)의 이름 하나일 뿐 명령이 아니다 —
목록 밖이면 아무것도 돌리지 않고 거절한다(폴백 없음). 2026-09-12 에 「마스터가 임의 셸 문자열을 파일로 떨구고 스케줄러가
실행하는」 구조를 만들었다가 폐기했다 — 인증도 계약도 없는 **로컬 원격실행 면**이었기
때문이다. 그 차이가 이 주석의 요점이다: **데이터는 받고, 명령은 받지 않는다.**

[주의] `files` 는 그대로 프롬프트에 들어가므로 **경로 모양만 받는다** — 셸에 넘기지 않는다.

## 규약

    입력   <checkout>/.ax/session1/<task_id>/<request_id>/job.json
           {"task_id","files","request_id","mode"}; 옛 단일 task 디렉터리도 읽는다
           `mode` 가 없으면 codex 다 — `#832` 이전 마스터가 보낸 job 의 뜻 그대로(하위 호환)
    출력   같은 디렉토리의 out.txt · rc.txt · done.flag  (done.flag 를 **맨 마지막에** 쓴다)
    로그   같은 디렉토리의 launcher.log                  (사건마다 한 줄 · 덧붙인다)

[중요] `done.flag` 가 마지막인 것은 마스터가 그것으로 완료를 판정하기 때문이다 —
반쯤 쓰인 `out.txt` 를 읽으면 안 된다.

## 🔴 [중요] 로그를 남긴다 (실측 2026-09-13)

종전 런처는 **로그를 하나도 남기지 않았다.** 실증 7분 동안(18:54~19:02) 마스터 저널에는
아무것도 없었고, codex 가 UE5 빌드를 돌리다 UnrealBuildTool 이 두 번 죽어 **오류 창이 떴다는
사실**을 사람이 워커에 SSH 로 들어가서야 찾았다. 그래서 사건마다 `launcher.log` 에 한 줄씩
남기고, 마스터가 결과를 회수할 때 그것을 저널로 가져간다(`runner.run_worker_session1`).
[주의] 로그 쓰기 실패는 작업을 막지 않는다 — 조용히 넘기되 작업 결과 파일은 그대로 쓴다.

## 🔴 agy 위임 중계 (`#764`, 사용자 결정 2026-10-09 ⓑ)

Windows 에서는 codex 샌드박스 안의 agy 가 죽는다 — 실측 `.2`: agy 가 홈
`C:/Users/<user>/.gemini/antigravity-cli/conversations/*.tmp` 저장에서 *"Access is denied"* 로 실패해
출력 0바이트. SSH(세션 0)로 부르면 *"authentication failed or timed out"* 이다. 그래서 **샌드박스 밖이고
로그온 세션인 이 런처가 agy 를 대신 돈다**:

    지휘자   .agy-work/in/<n>/ 에 자료·BRIEF.md → 빈 파일 .agy-work/in/<n>.go
    런처     codex 가 도는 동안 2초마다 *.go 를 본다 → agy … --add-dir in/<n> → out/<n>.json·.err·.done
    지휘자   out/<n>.done 이 생길 때까지 기다렸다가 out/<n>.json 을 읽는다

[중요] **명령은 받지 않는다** — 받는 것은 요청 이름(`[A-Za-z0-9_-]`)뿐이고 실행 파일·플래그·프롬프트는 여기
고정이다(위 원칙 그대로). 런처가 job 을 시작할 때 `.agy-work/VIA_LAUNCHER` 를 써서 지휘자에게 「중계가
있다」를 알린다 — **중계가 실제로 도는 경로에서만** 그 표시가 생긴다.

## 🔴 agy 모델은 정본 id 로 못 박는다 (`#830`)

설정의 모델 이름은 별칭이고, 별칭이 조용히 「Gemini 4 Argon」으로 풀려 그 한도를 태웠다. 그래서
중계는 배달된 `<checkout>/.ax/config.json` 의 `backends.agy_model`(정본 id, 예
`gemini-3.8-flash-medium`)을 읽어 **`agy --model <id>`** 로 넘긴다. 폴백·쿨다운은 없다.
값이 없거나 정본 모양(`[a-z0-9][a-z0-9.-]*`)이 아니거나 `gemini-` 로 시작하지 않거나 `argon` 이
들어 있으면 **agy 를 부르지 않고** 실패 결과(`.err` 사유 · `.done` rc **78**)와 로그 줄을 남긴다.

`--log-file out/<n>.log` 도 넘기고, 끝나면 그 로그를 배달된 `work/usage.py` 의 `parse_agy_log` 로
읽어 **실제 모델**을 대조한다(사용자 결정 ⓐ — 파서는 그 한 곳이다, 두 번째를 만들지 않는다).
로그에 모델이 없으면 봉투(`parse_agy_json`)의 모델을 `agy_model_id` 로 정규화해 쓴다(`gemini_report` 와 같다).
실제 ≠ 요청 **이거나 실제를 모르면** 거절한다 — `.json`·`.log` 는 증거로 남기고 `.err` 끝에 사유,
`.done` rc **79**. 파서를 못 불러오면 그것도 거절(rc 79)이고 이때는 agy 를 **부르지 않는다**
(버릴 출력에 한도를 쓰지 않는다). [주의] agy 자체가 실패한 경우(rc≠0)는 그 rc 를 그대로 두고
판정 사유만 덧붙인다 — 시간 초과(124)·실행 실패(127)가 79 에 묻히지 않게.

    rc 78   설정 결함 — 모델 값이 없거나 정본 gemini id 가 아니다 · agy 를 부르지 않았다
    rc 79   모델 판정 거절 — 실제 모델 불일치·미상, 또는 파서 로드 실패
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

JOB_DIR = ".ax/session1"
# 🔴 `#832` — job.json 의 `mode` 허용 목록. 이름만 받고 argv 는 `build_argv` 가 만든다.
MODES = ("codex", "claude")
# [중요] 필드가 **없을 때만** codex 다 — `#832` 이전 마스터는 mode 를 안 실었고 그때 이 런처는
#    codex 만 돌렸다(하위 호환). 필드가 있는데 목록 밖(빈 값·null·"lane" 포함)이면 거절이다.
DEFAULT_MODE = "codex"
MODE_REFUSE_RC = 2                   # 모드 거절 — 지휘자를 돌리지 않았다
SESSION0_REFUSE_RC = 3               # 세션 0 거절 — 지휘자를 돌리지 않았다 (`#832`)
JOB, OUT, RC, DONE = "job.json", "out.txt", "rc.txt", "done.flag"
CANCEL = "cancel.flag"
LOG = "launcher.log"

# [중요] 마스터 `runner.INSTRUCTION` 과 **같은 글자**여야 한다 — 배달물은 마스터를 import 하지
#    않으므로(`clientside` 규약) 값을 복사한다. 갈리면 워커가 다른 계약으로 일한다.
INSTRUCTION = (
    "Follow the ax-work skill. Read it by path at .agents/skills/ax-work/SKILL.md and the machine config at .ax/config.json - "
    "both are excluded from git, so search tools that honor ignore files (rg, git ls-files) will not list them; open them directly. "
    "You are on the assigned branch already. "
    "This message is dispatched work from the AX master, not a human chat: the plan was already approved when the task was registered. "
    "Do not ask for approval, do not propose a plan for review, do not wait for confirmation - implement the bodies now. "
    "Read the [DOC] and [PSEUDO] comments in these files and write their bodies: {files}. "
    "Judge from the source files in this checkout, not from memory. "
    "Read and edit the target files yourself and write their bodies yourself - do not delegate body drafts "
    "to agy, codex exec or the local broker. Per section 4 of the ax-work skill, delegate research to agy only when you "
    "judge it necessary - file size is not a reason to delegate, and not delegating is not a failure. "
    "Do not run any git command. Do not commit or push. "
    "Do not run UE5 builds, UnrealBuildTool, UnrealEditor or automation tests, "
    "and for Python files do not start servers, run the program or run tests - "
    "verification is done later by the requester, not on this worker. "
    "Save each raw agy JSON response as a numbered file in .agy-work/out/ - the master collects it. "
    "If a delegation you attempt fails (non-zero exit, timeout, or an empty or unusable response), "
    "you may retry that work with the next enabled backend in the lane order; "
    "if every backend you tried fails, do not do that work yourself: keep the raw response files in .agy-work/out/, "
    "state each backend, exit code and error, and stop with RESULT: BLOCKED. "
    "A backend that is not enabled in .ax/config.json is not a failure - just do not delegate to it. "
    "Above the RESULT line, list what you delegated, to which backend, and how you checked it. "
    "The last non-empty line of your output must be exactly RESULT: DONE "
    "(use RESULT: BLOCKED if you could not finish, and say why above it)."
)


def _log(d: Path, msg: str) -> None:
    """`<job 디렉토리>/launcher.log` 에 시각과 함께 한 줄 덧붙인다. **예외를 던지지 않는다.**"""
    try:
        with open(d / LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:                                        # noqa: BLE001
        pass


def _codex_exe() -> str:
    """codex 실행 파일. 🔴 **Windows 에서 `codex` 는 `codex.cmd` 다** (실측 2026-09-12).

    `subprocess` 는 셸을 안 타므로 PATH 에서 `codex` 를 못 찾고 `FileNotFoundError:
    [WinError 2]` 로 죽는다 — 첫 실물 왕복이 정확히 그렇게 실패했다. `shutil.which` 가
    `PATHEXT` 를 보므로 그것으로 **잰다**(경로를 박지 않는다 — 기계마다 다르다).
    [주의] 못 찾으면 그대로 `codex` 를 돌려준다 — 실패 사유가 로그에 남는 편이 낫다.
    """
    import shutil
    return shutil.which("codex") or "codex"


def _claude_exe() -> str:
    """claude 실행 파일 (`#832`). `_codex_exe` 와 같은 이유로 `shutil.which` 로 잰다 —
    설치 방식에 따라 `claude.exe`(네이티브) 또는 `claude.cmd`(npm) 다."""
    return shutil.which("claude") or "claude"


# 🔴 job.json 의 `self_repo` 가 참일 때만 지시문 끝에 붙이는 사실 문장 (`#783`, 사용자 2026-10-10).
#    그 체크아웃의 AGENTS.md·CLAUDE.md 는 사람이 앉은 마스터 세션용 규칙이다 — 무인 워커의 codex 가
#    「실패는 보고하는 자리」를 읽고 검색 0건(rg exit 1)에 BLOCKED 로 멈췄다(실측 2026-10-10 `.43`).
#    [주의] 명령형이 아니라 사실로 쓴다 — 자동 경로의 명령형은 주입으로 거부된 실측이 있다(리포트 60).
#    [중요] 마스터 `runner.SELF_REPO_NOTE`과 **같은 글자**여야 한다.
SELF_REPO_NOTE = (
    "This checkout is the AX master's own repository: its AGENTS.md and CLAUDE.md describe "
    "interactive master sessions with a human present, not dispatched work like this one. "
    "A search that finds no matches is not a failure."
)

def instruction(files, self_repo: bool = False) -> str:
    """지휘자 지시문 — 마스터 `runner.worker_command` 와 같은 조립(지시문 + 자기 저장소 문장)."""
    return (INSTRUCTION.format(files=", ".join(str(f) for f in files) or "(none given)")
            + (" " + SELF_REPO_NOTE if self_repo else ""))


def build_argv(root: Path, files, approvals=(), self_repo: bool = False,
               mode: str = DEFAULT_MODE) -> list:
    """지휘자 인자. 🔴 **여기가 플래그의 주인이다** — 마스터가 주지 않는다.

    codex: `agent_command` 의 codex 절과 같은 값을 쓴다: 쓰기는 작업공간으로 묶고 네트워크만 연다
    (레인 위임이 브로커 HTTP 라서다). Windows 는 `unelevated` 를 못 박는다(`#401` 완화).
    claude (`#832`): `agent_command` 의 claude 절과 같은 플래그·순서다
    (`claude -p --output-format json --dangerously-skip-permissions "<지시문>"`). 디렉토리는
    `-C` 가 아니라 `run_job` 의 `cwd` 로 준다(마스터 쪽 `cd /d` 와 같은 뜻). `approvals` 는 codex 전용이다.
    목록 밖 모드는 `ValueError` — 호출부(`run_job`)가 먼저 거르므로 여기 오면 계약 위반이다.
    """
    text = instruction(files, self_repo)
    if mode == "claude":
        return [_claude_exe(), "-p", "--output-format", "json",
                "--dangerously-skip-permissions", text]
    if mode != "codex":
        raise ValueError(f"모르는 지휘자 모드: {mode!r}")
    argv = [_codex_exe(), "exec", "--json", "-s", "workspace-write",
            "-c", "sandbox_workspace_write.network_access=true"]
    if sys.platform.startswith("win"):
        argv += ["-c", 'windows.sandbox="unelevated"']
    for a in approvals or ():
        argv += ["-c", a]
    argv += ["--skip-git-repo-check", "-C", str(root), text]
    return argv


def job_mode(job: dict) -> tuple:
    """`(모드, "")` 또는 `("", 거절 사유)`. 예외를 던지지 않는다.

    [중요] 필드가 없으면 codex(하위 호환 — `DEFAULT_MODE` 주석). 있는데 허용 목록 밖이면 거절이다.
    """
    if "mode" not in job:
        return DEFAULT_MODE, ""
    mode = job.get("mode")
    if isinstance(mode, str) and mode in MODES:
        return mode, ""
    return "", f"job.json 의 mode 가 허용 목록 {list(MODES)} 밖이다: {mode!r} — 실행하지 않는다"


_WINSESSION = None


def _winsession_paths() -> list:
    """`winsession.py` 후보 — 이 파일과 **같은 디렉토리**다(배달본 `clientside/` · 저장소 `client/runtime/`)."""
    return [Path(__file__).resolve().parent / "winsession.py"]


def _load_winsession():
    """`winsession.py` 를 **경로로** 로드한다(`_load_usage` 와 같은 방식). 실패면 예외."""
    global _WINSESSION
    if _WINSESSION is not None:
        return _WINSESSION
    for src in _winsession_paths():
        if not src.is_file():
            continue
        spec = importlib.util.spec_from_file_location("ax_s1_winsession", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _WINSESSION = mod
        return mod
    raise FileNotFoundError("winsession.py 가 배달되지 않았다 — " + " · ".join(map(str, _winsession_paths())))


def session_check(d: Path) -> tuple:
    """`(세션 id 또는 None, 거절 사유)` — 사유가 빈 문자열이면 진행. 예외를 던지지 않는다 (`#832`).

    🔴 `/IT` 등록이 어긋나 런처가 세션 0 에서 떴다면 지휘자를 돌려 봐야 늦고 엉뚱한 오류로 죽는다
    (codex `0xC0000142` · agy 로그인 없음) — 그래서 시작 전에 고정 사유로 거절한다.
    [주의] 모듈을 못 불러오면 **경고만 남기고 진행한다** — 이 검사는 보조 방어다. 옛 배달본에는
    `winsession.py` 가 없고, 그것 때문에 지금 도는 세션 1 경로를 막으면 안 된다.
    """
    try:
        ws = _load_winsession()
    except Exception as e:                                   # noqa: BLE001
        _log(d, f"[주의] 세션 판정 모듈(winsession.py)을 못 불러왔다 — 판정 없이 진행 "
                f"({type(e).__name__}: {e})")
        return None, ""
    try:
        sid = ws.session_id()
        if ws.is_session0():
            return sid, (ws.refuse_reason() or f"세션 0 이다 · SessionId={sid}")
        return sid, ""
    except Exception as e:                                   # noqa: BLE001
        _log(d, f"[주의] 세션 판정 실패 — 판정 없이 진행 ({type(e).__name__}: {e})")
        return None, ""


AGY_ROOT, AGY_MARK = ".agy-work", "VIA_LAUNCHER"
AGY_PROMPT = ("Read BRIEF.md in the added directory and follow it exactly. "
              "Return the result as your response. Do not create or modify files.")
AGY_POLL, AGY_LIMIT = 2.0, 300   # #780: 5-minute hard cap per relayed agy call
_REQ = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
# 🔴 `#830` — 정본 모델 id 모양. 별칭(`Gemini 3.8 Flash` 등 공백·대문자)은 여기서 걸린다
_AGY_MODEL = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
AGY_BAD_MODEL_RC = 78                # 설정 결함(EX_CONFIG) — agy 를 부르지 않았다
AGY_MODEL_REJECT_RC = 79             # 실제 모델 불일치·미상 · 파서 로드 실패 — 출력을 버린다
CONFIG_REL = ".ax/config.json"
_USAGE = None                        # 로드한 `work/usage.py` (한 번만 로드한다)


def _usage_paths() -> list:
    """`work/usage.py` 후보. 배달본은 `axmaster/clientside/` 옆 `axmaster/work/`, 저장소는 `master/work/`."""
    here = Path(__file__).resolve()
    return [here.parents[1] / "work" / "usage.py",            # 배달본 (.ax/lib/axmaster/work)
            here.parents[2] / "master" / "work" / "usage.py"]  # 저장소에서 직접 실행 (client/runtime)


def _load_usage():
    """배달된 `work/usage.py` 를 **경로로** 로드한다(`ontology_cache` 와 같은 방식). 실패면 예외."""
    global _USAGE
    if _USAGE is not None:
        return _USAGE
    for src in _usage_paths():
        if not src.is_file():
            continue
        spec = importlib.util.spec_from_file_location("ax_s1_usage", src)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod          # dataclass 가 자기 모듈을 sys.modules 에서 찾는다
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(spec.name, None)
            raise
        _USAGE = mod
        return mod
    raise FileNotFoundError("work/usage.py 가 배달되지 않았다 — " + " · ".join(map(str, _usage_paths())))


def model_verdict(usage, want: str, log_file: Path, stdout: str) -> tuple:
    """`(실제 모델, 출처, 거절 사유)` — 사유가 빈 문자열이면 일치. 예외를 던지지 않는다.

    [중요] 실제를 **모르면 거절**이다(사용자 결정 2026-10-18) — 모르는 것을 일치로 보지 않는다.
    """
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else ""
        lg = usage.parse_agy_log(text)
        parsed = usage.parse_agy_json(stdout or "")
        env = parsed[3] if parsed else ""
        actual = lg.get("model") or (usage.agy_model_id(env) if env else "")
        source = lg.get("model_source") or ("envelope" if env else "")
    except Exception as e:                                   # noqa: BLE001
        return "", "", f"모델 판정 실패 — {type(e).__name__}: {e}"
    if not actual:
        return "", "", (f"실제 모델 미상 — agy 로그({'있음' if text else '없음'})·봉투에서 모델을 읽지 "
                        f"못했다(요청 {want}), 출력을 버린다")
    if actual != want:
        return actual, source, f"모델 불일치 — 요청 {want} · 실제 {actual}, 출력을 버린다"
    return actual, source, ""


def _agy_exe() -> str:
    return shutil.which("agy") or "agy"


def agy_model(root: Path) -> tuple:
    """배달된 설정의 `backends.agy_model` → `(id, "")` 또는 `("", 거절 사유)`. 예외를 던지지 않는다.

    [중요] 폴백이 없다 — 값이 없거나 모양이 틀리면 agy 를 부르지 않는다(별칭이 아무 모델로나 풀린다).
    """
    try:
        cfg = json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        return "", f"{CONFIG_REL} 를 못 읽었다 — {type(e).__name__}: {e}"
    backends = cfg.get("backends") if isinstance(cfg, dict) else None
    model = backends.get("agy_model") if isinstance(backends, dict) else None
    if not model:
        return "", f"{CONFIG_REL} 에 backends.agy_model 이 없다"
    if not isinstance(model, str) or not _AGY_MODEL.match(model):
        return "", f"backends.agy_model 이 정본 id 모양이 아니다: {model!r}"
    if not model.startswith("gemini-"):
        return "", f"backends.agy_model 이 gemini- 로 시작하지 않는다: {model!r}"
    if "argon" in model:
        return "", f"backends.agy_model 이 Argon 이다 — 워커에서 쓰지 않는다: {model!r}"
    return model, ""


class AgyRelay(threading.Thread):
    """codex 가 도는 동안 `.agy-work/in/*.go` 를 처리한다. 순서대로 하나씩 · 예외를 던지지 않는다."""

    def __init__(self, root: Path, d: Path):
        super().__init__(daemon=True)
        self.root, self.d = root, d
        self.stop = threading.Event()
        self.handled: set = set()
        self.proc = None

    def run(self) -> None:
        inn = self.root / AGY_ROOT / "in"
        while not self.stop.is_set():
            try:
                for go in sorted(inn.glob("*.go")):
                    name = go.stem
                    if name in self.handled or self.stop.is_set():
                        continue
                    self.handled.add(name)
                    if not _REQ.match(name):
                        _log(self.d, f"🔴 agy 중계 — 이름 규칙 밖 요청을 버렸다: {name!r}")
                        continue
                    self.serve(name)
            except Exception as e:                           # noqa: BLE001
                _log(self.d, f"🔴 agy 중계 스캔 실패 — {type(e).__name__}: {e}")
            self.stop.wait(AGY_POLL)

    def serve(self, name: str) -> None:
        out = self.root / AGY_ROOT / "out"
        out.mkdir(parents=True, exist_ok=True)
        req = self.root / AGY_ROOT / "in" / name
        t0, rc, so, se = time.monotonic(), 2, "", ""
        model, why = agy_model(self.root)
        log_file = out / f"{name}.log"
        usage, ran = None, False
        if model and (req / "BRIEF.md").is_file():
            try:
                usage = _load_usage()
            except Exception as e:                           # noqa: BLE001
                why = f"agy 로그 파서(work/usage.py)를 못 불러왔다 — {type(e).__name__}: {e}"
        if not (req / "BRIEF.md").is_file():
            se = f"{req / 'BRIEF.md'} 가 없다"
        elif not model:
            # 🔴 `#830` — 부르지 않는다. 사유는 `.err` 와 런처 로그 둘 다에 남는다
            se, rc = f"[런처] agy 를 부르지 않았다 — {why}", AGY_BAD_MODEL_RC
            _log(self.d, f"🔴 agy 중계 거절 — 요청 {name} · {why}")
        elif usage is None:
            # 🔴 실제 모델을 대조할 수 없으면 버릴 출력이다 — 한도를 쓰지 않는다
            se, rc = f"[런처] agy 를 부르지 않았다 — {why}", AGY_MODEL_REJECT_RC
            _log(self.d, f"🔴 agy 중계 거절 — 요청 {name} · {why}")
        else:
            ran = True
            argv = [_agy_exe(), "--dangerously-skip-permissions", "--output-format", "json",
                    "--model", model, "--log-file", str(log_file),
                    "--add-dir", str(req), "-p", AGY_PROMPT]
            _log(self.d, f"agy 중계 시작 — 요청 {name} · 실행 파일 {argv[0]} · 모델 {model} · "
                         f"로그 {log_file}")
            kw = ({"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
                  if sys.platform.startswith("win") else {"start_new_session": True})
            try:
                self.proc = subprocess.Popen(argv, cwd=str(req), stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                             text=True, encoding="utf-8", errors="replace", **kw)
                if self.stop.is_set():
                    _kill_tree(self.proc)
                try:
                    so, se = self.proc.communicate(timeout=AGY_LIMIT)
                    rc = self.proc.returncode
                except subprocess.TimeoutExpired:
                    _kill_tree(self.proc)
                    so, se = self.proc.communicate(timeout=30)
                    se = (se or "") + f"\n[런처] agy 시간 초과 {AGY_LIMIT}초 — 프로세스 트리를 죽였다"
                    rc = 124
            except Exception as e:                           # noqa: BLE001
                se, rc = f"[런처] agy 실행 실패 — {type(e).__name__}: {e}", 127
            finally:
                if self.proc is not None and self.proc.poll() is None:
                    _kill_tree(self.proc)
                    try:
                        self.proc.wait(timeout=30)
                    except Exception:
                        _log(self.d, "🔴 agy 종료 뒤 프로세스 회수 실패")
                self.proc = None
        if ran:
            # 🔴 `#830` — 실제 모델 대조. `.json`·`.log` 는 증거로 그대로 남는다
            actual, source, bad = model_verdict(usage, model, log_file, so)
            if bad:
                se = (se or "")[-3000:] + f"\n[런처] {bad}"
                if rc == 0:
                    rc = AGY_MODEL_REJECT_RC
            _log(self.d, f"{'🔴 ' if bad else ''}agy 중계 모델 — 요청 {name} · 요청 모델 {model} · "
                         f"실제 {actual or '(미상)'} (출처 {source or '없음'}) · 로그 {log_file} "
                         f"({'있음' if log_file.is_file() else '없음'}) · 판정 "
                         + (f"거절 — {bad}" if bad else "일치"))
        try:
            (out / f"{name}.json").write_text(so or "", encoding="utf-8")
            (out / f"{name}.err").write_text((se or "")[-4000:], encoding="utf-8")
            (out / f"{name}.done").write_text(str(rc), encoding="utf-8")      # 맨 마지막
        except Exception as e:                               # noqa: BLE001
            _log(self.d, f"🔴 agy 중계 결과를 못 썼다 — {type(e).__name__}: {e}")
        _log(self.d, f"agy 중계 끝 — 요청 {name} · rc={rc} · {int(time.monotonic() - t0)}초 · "
                     f"출력 {len(so or '')}자")

    def shutdown(self) -> None:
        self.stop.set()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            _kill_tree(proc)
            try:
                _log(self.d, "🔴 codex 가 끝났는데 agy 중계가 돌고 있었다 — 프로세스 트리를 죽였다")
            except OSError:
                pass
        self.join(timeout=10)


def _start_relay(root: Path, d: Path):
    """중계를 띄우고 표시를 쓴다. 실패하면 `None` — 지휘자는 표시가 없으니 직접 호출로 간다."""
    relay = None
    try:
        base = root / AGY_ROOT
        (base / "in").mkdir(parents=True, exist_ok=True)
        (base / "out").mkdir(parents=True, exist_ok=True)
        relay = AgyRelay(root, d)
        relay.start()
        (base / AGY_MARK).write_text("agy requests are served by the session-1 launcher\n",
                                     encoding="utf-8")
        _log(d, f"agy 중계 대기 — {base / 'in'} 의 *.go")
        return relay
    except Exception as e:                                   # noqa: BLE001
        if relay is not None and relay.ident is not None:
            relay.shutdown()
        try:
            (root / AGY_ROOT / AGY_MARK).unlink()
        except OSError:
            pass
        try:
            _log(d, f"🔴 agy 중계를 못 띄웠다 — {type(e).__name__}: {e}")
        except Exception:                                   # noqa: BLE001
            pass
        return None


def _stop_relay(root: Path, d: Path, relay) -> bool:
    if relay is None:
        return True
    relay.shutdown()
    try:
        (root / AGY_ROOT / AGY_MARK).unlink()
    except OSError:
        pass
    _log(d, f"agy 중계 종료 — 처리 {len(relay.handled)}건")
    if relay.is_alive():
        _log(d, "🔴 agy 중계 스레드 종료 미확인")
        return False
    return True


def _kill_tree(proc) -> None:
    """프로세스 **트리**를 죽인다. [중요] 직계만 죽이면 손자(codex → dotnet)가 남는다."""
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=30)
        else:
            import os
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:                                        # noqa: BLE001
        try:
            proc.kill()
        except Exception:                                    # noqa: BLE001
            pass


def run_job(root: Path, d: Path) -> int:
    """job 하나를 돌리고 결과를 남긴다. 반환은 rc."""
    t0 = time.monotonic()
    rc = 1
    out = ""
    try:
        job = json.loads((d / JOB).read_text(encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        _log(d, f"🔴 job.json 을 못 읽었다 — {type(e).__name__}: {e}")
        job = {}
    files = job.get("files") or []
    limit = int(job.get("timeout") or 3600)
    def stopped():
        if (d / CANCEL).exists():
            return "요청자 취소"
        if job.get("expires_at") and time.time() >= float(job["expires_at"]):
            return "요청 기한 만료"
        return ""
    def finish():
        (d / OUT).write_text(out, encoding="utf-8")
        (d / RC).write_text(str(rc), encoding="utf-8")
        _log(d, f"결과 기록 — rc={rc} · 전체 {int(time.monotonic() - t0)}초 · done.flag 를 쓴다")
        (d / DONE).write_text(str(job.get("request_id") or "done"), encoding="utf-8")
        return rc
    reason = stopped()
    if reason:
        out = f"[런처] {reason} — 실행하지 않았다"
        _log(d, out)
        return finish()
    mode, bad_mode = job_mode(job)
    sid, s0 = session_check(d)
    _log(d, f"job 집음 — task={job.get('task_id', d.name)} · 모드 {mode or '(거절)'} · "
            f"파일 {len(files)} · 제한 {limit}초 · 세션 {sid if sid is not None else '미상'}")
    if bad_mode:
        # 🔴 `#832` — 폴백하지 않는다. 모르는 이름을 codex 로 돌리면 마스터가 고른 지휘자와 갈린다
        rc, out = MODE_REFUSE_RC, f"ERROR [런처] {bad_mode}\nRESULT: BLOCKED"
        _log(d, f"🔴 모드 거절 — {bad_mode}")
        return finish()
    if s0:
        # 🔴 `#832` — 세션 0 이면 지휘자도 agy 중계도 띄우지 않는다(VIA_LAUNCHER 를 쓰지 않는다)
        rc, out = SESSION0_REFUSE_RC, f"ERROR [런처] {s0}\nRESULT: BLOCKED"
        _log(d, f"🔴 세션 0 거절 — SessionId={sid} · {s0}")
        return finish()
    argv = build_argv(root, files, job.get("approvals") or (), self_repo=job.get("self_repo") is True,
                      mode=mode)
    _log(d, f"argv 준비 — 모드 {mode} · 실행 파일 {argv[0]}")
    # 🔴 [중요] **자식까지 죽여야 한다** (실측 2026-09-12). 세션 1 은 데스크톱이 있어서
    #    크래시가 **모달 대화상자**로 뜨고, 그러면 프로세스가 무한 대기한다 — 세션 0 에서는
    #    데스크톱이 없어 조용히 죽던 것이 여기서는 매달린다. 실제로 `dotnet`(UBT) 둘이
    #    CPU 0 으로 남아 사람이 창을 닫아 줘야 했다.
    #    `subprocess.run` 의 timeout 은 **직계만** 죽이므로 손자(codex → dotnet)가 남는다.
    #    [주의] Windows 는 `taskkill /T`, POSIX 는 프로세스 그룹으로 — 같은 뜻의 두 방법이다.
    kw = {}
    if sys.platform.startswith("win"):
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    relay = _start_relay(root, d)                           # `#764` — 지휘자보다 먼저 (codex·claude 둘 다)
    proc = None
    try:
        proc = subprocess.Popen(argv, cwd=str(root), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", **kw)
        _log(d, f"{mode} 시작 — pid={proc.pid} · 실행 파일 {argv[0]}")
        deadline = time.monotonic() + limit
        completed = False
        while True:
            reason = stopped()
            remaining = deadline - time.monotonic()
            if reason or remaining <= 0:
                _kill_tree(proc)
                out = proc.communicate(timeout=30)[0] or ""
                out += f"\n[런처] {reason or '시간 초과'} — 프로세스 트리를 죽였다"
                _log(d, f"🔴 {reason or f'시간 초과 {limit}초'} — 프로세스 트리를 죽였다 (pid={proc.pid})")
                break
            try:
                out = proc.communicate(timeout=min(1, remaining))[0] or ""
                rc = proc.returncode
                completed = True
                break
            except subprocess.TimeoutExpired:
                continue
        if completed:
            _log(d, f"{mode} 종료 — rc={rc} · {int(time.monotonic() - t0)}초 · 출력 {len(out)}자")
    except Exception as e:                                   # noqa: BLE001
        out, rc = f"[런처] 실행 실패 — {type(e).__name__}: {e}", 1
        _log(d, f"🔴 실행 실패 — {type(e).__name__}: {e}")
    finally:
        if proc is not None and proc.poll() is None:
            _kill_tree(proc)
            try:
                proc.wait(timeout=30)
            except Exception:
                _log(d, "🔴 종료 뒤 프로세스 회수 실패")
                out += "\n[런처] 프로세스 종료 미확인"
                rc = 1
        if not _stop_relay(root, d, relay):
            out += "\n[런처] agy 중계 종료 미확인"
            rc = 1
    return finish()


def find_root() -> Path:
    """체크아웃 루트. 🔴 **`Path.cwd()` 를 쓰지 않는다** (실측 2026-09-12).

    작업 스케줄러는 cwd 를 `C:\\Windows\\System32` 로 준다 — 거기서 `.ax/session1` 을 찾으니
    **아무 job 도 못 보고 조용히 0 으로 끝났다.** 첫 실물이 정확히 그렇게 실패했다(파일은
    갔는데 결과가 안 나왔다). 배달 위치가 고정이므로 **자기 위치에서 거슬러 올라간다**:

        <체크아웃>/.ax/lib/axmaster/clientside/session1_conductor.py
                   └ parents[0]=clientside · [1]=axmaster · [2]=lib · [3]=.ax · [4]=체크아웃

    [주의] 워커 데몬이 `find_root` 로 같은 일을 한다 — 그쪽은 처음부터 그렇게 짜여 있었고,
    이 런처만 cwd 에 기댔다.
    """
    here = Path(__file__).resolve()
    for up in (4, 3):                        # 배달본(4) · 저장소에서 직접 실행(느슨)
        cand = here.parents[up] if len(here.parents) > up else None
        if cand and (cand / ".ax").is_dir():
            return cand
    return Path.cwd()


def main(argv=None) -> int:
    """대기 중인 job 을 **전부** 돈다. 인자를 받지 않는다 — 스케줄러가 인자를 못 준다."""
    root = find_root()
    base = root / JOB_DIR
    if not base.is_dir():
        return 0
    # #695: every retry has a separate result directory. Legacy jobs remain readable.
    jobs = list(base.glob("*/job.json")) + list(base.glob("*/*/job.json"))
    for job_path in sorted(jobs):
        d = job_path.parent
        if not (d.is_dir() and (d / JOB).is_file()):
            continue
        done = d / DONE
        if not done.exists():
            run_job(root, d)
            continue
        # 🔴 [주의] **관찰 로그 — 동작은 바꾸지 않는다** (가설 확인용, 2026-09-13).
        #    완료 뒤에 `job.json` 이 다시 쓰였다면 마스터가 **재시도**를 보낸 것인데, `done.flag` 가
        #    남아 있어 이 런처는 그 job 을 돌리지 않는다. 그러면 마스터가 **이전 시도의 결과**를
        #    다시 읽을 수 있다 — 09-12 로그의 「재시도 출력이 글자까지 같다」가 그것인지 가린다.
        try:
            if (d / JOB).stat().st_mtime > done.stat().st_mtime:
                _log(d, "🔴 [주의] job.json 이 done.flag 보다 새롭다 — 이전 결과가 남아 이 job 을 "
                        "돌리지 않았다 (재시도가 옛 결과를 읽을 수 있다)")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
