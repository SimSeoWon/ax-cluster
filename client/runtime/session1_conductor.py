"""세션 1 지휘자 런처 — 윈도우 워커에서 `codex exec` 를 **로그온 세션**에서 돌린다 (`#401`).

## 왜 필요한가 (실측 2026-09-12)

Windows OpenSSH 는 **세션 0** 에서 프로세스를 만들고, 거기서는 codex 의 제한 토큰 샌드박스
자식이 `0xC0000142` 로 죽는다. 그래서 SSH 로 민 지휘자는 `ax-work` SKILL.md **조차 읽지
못한 채** 본문을 썼고 층1 이 막았다(그날 조각 2건이 그렇게 죽었다).

    SSH 가 직접 실행                세션 0   ❌ 0xC0000142
    SSH → schtasks /run (`/IT`)     세션 1   ✅ exit_code 0 · turn.completed

`/IT` 로 등록된 작업은 SSH 가 **부탁만** 하고 프로세스는 스케줄러가 세션 1 에 만든다.

## 🔴 [중요] 이 파일은 **명령을 받지 않는다**

마스터가 주는 것은 `job.json` 의 **`task_id` 와 `files` 뿐**이고, **실행 파일과 플래그는
이 런처가 소유한다.** 2026-09-12 에 「마스터가 임의 셸 문자열을 파일로 떨구고 스케줄러가
실행하는」 구조를 만들었다가 폐기했다 — 인증도 계약도 없는 **로컬 원격실행 면**이었기
때문이다. 그 차이가 이 주석의 요점이다: **데이터는 받고, 명령은 받지 않는다.**

[주의] `files` 는 그대로 프롬프트에 들어가므로 **경로 모양만 받는다** — 셸에 넘기지 않는다.

## 규약

    입력   <checkout>/.ax/session1/<task_id>/job.json   {"task_id","files","mode"}
    출력   같은 디렉토리의 out.txt · rc.txt · done.flag  (done.flag 를 **맨 마지막에** 쓴다)

[중요] `done.flag` 가 마지막인 것은 마스터가 그것으로 완료를 판정하기 때문이다 —
반쯤 쓰인 `out.txt` 를 읽으면 안 된다.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

JOB_DIR = ".ax/session1"
JOB, OUT, RC, DONE = "job.json", "out.txt", "rc.txt", "done.flag"

# [중요] 마스터 `runner.INSTRUCTION` 과 **같은 글자**여야 한다 — 배달물은 마스터를 import 하지
#    않으므로(`clientside` 규약) 값을 복사한다. 갈리면 워커가 다른 계약으로 일한다.
INSTRUCTION = (
    "Follow the ax-work skill. You are on the assigned branch already. "
    "Read the [DOC] and [PSEUDO] comments in these files and write their bodies: {files}. "
    "Judge from the source files in this checkout, not from memory. "
    "Do not run any git command. Do not commit or push. "
    "The last non-empty line of your output must be exactly RESULT: DONE "
    "(use RESULT: BLOCKED if you could not finish, and say why above it)."
)


def _codex_exe() -> str:
    """codex 실행 파일. 🔴 **Windows 에서 `codex` 는 `codex.cmd` 다** (실측 2026-09-12).

    `subprocess` 는 셸을 안 타므로 PATH 에서 `codex` 를 못 찾고 `FileNotFoundError:
    [WinError 2]` 로 죽는다 — 첫 실물 왕복이 정확히 그렇게 실패했다. `shutil.which` 가
    `PATHEXT` 를 보므로 그것으로 **잰다**(경로를 박지 않는다 — 기계마다 다르다).
    [주의] 못 찾으면 그대로 `codex` 를 돌려준다 — 실패 사유가 로그에 남는 편이 낫다.
    """
    import shutil
    return shutil.which("codex") or "codex"


def build_argv(root: Path, files, approvals=()) -> list:
    """codex 인자. 🔴 **여기가 플래그의 주인이다** — 마스터가 주지 않는다.

    `agent_command` 의 codex 절과 같은 값을 쓴다: 쓰기는 작업공간으로 묶고 네트워크만 연다
    (레인 위임이 브로커 HTTP 라서다). Windows 는 `unelevated` 를 못 박는다(`#401` 완화).
    """
    argv = [_codex_exe(), "exec", "--json", "-s", "workspace-write",
            "-c", "sandbox_workspace_write.network_access=true"]
    if sys.platform.startswith("win"):
        argv += ["-c", 'windows.sandbox="unelevated"']
    for a in approvals or ():
        argv += ["-c", a]
    argv += ["--skip-git-repo-check", "-C", str(root),
             INSTRUCTION.format(files=", ".join(str(f) for f in files) or "(none given)")]
    return argv


def run_job(root: Path, d: Path) -> int:
    """job 하나를 돌리고 결과를 남긴다. 반환은 rc."""
    job = json.loads((d / JOB).read_text(encoding="utf-8"))
    files = job.get("files") or []
    argv = build_argv(root, files, job.get("approvals") or ())
    try:
        p = subprocess.run(argv, cwd=str(root), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                           timeout=int(job.get("timeout") or 3600))
        out, rc = (p.stdout or "") + (p.stderr or ""), p.returncode
    except Exception as e:                                   # noqa: BLE001
        out, rc = f"[런처] 실행 실패 — {type(e).__name__}: {e}", 1
    (d / OUT).write_text(out, encoding="utf-8")
    (d / RC).write_text(str(rc), encoding="utf-8")
    (d / DONE).write_text("done", encoding="utf-8")          # [중요] 맨 마지막
    return rc


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
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / JOB).is_file() and not (d / DONE).exists():
            run_job(root, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
