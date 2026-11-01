"""현행 검수·후속 검사·정리에서 공유하는 Git 실행 헬퍼.

#234에서 폐기된 selftest 및 2-tier attempt 실행부를 제거했다. GitError·_git_cmd·_git·
_git_rc·_noop_log는 review/followup/cleanup/revise/attempt가 쓰므로 유지한다.
커밋 신원·서명 비활성·타임아웃·반환 형식은 기존 계약 그대로다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT = 120


class GitError(RuntimeError):
    """git 이 실패했다. **삼키지 않는다** — 여기서 조용히 넘어가면 브랜치 상태를 모른 채
    다음 단계가 돈다(이 저장소가 반복해 물린 *조용히 틀리는* 유형)."""


def _git_cmd(repo: Path, *args: str) -> list:
    """git 명령줄 조립 — [중요] **커밋 신원의 단일 출처.**

    인자로 박는 이유: 마스터의 전역 git 설정에 의존하면 환경마다 달라진다. `_git` 과
    `_git_rc` 가 **같은 이 함수**를 쓴다 — 따로 만들면 신원·서명 설정이 조용히 갈라진다.
    """
    return ["git", "-c", "user.email=cluster@local", "-c", "user.name=ax-cluster",
            "-c", "commit.gpgsign=false", "-C", str(repo), *args]


def _git(repo: Path, *args: str, check: bool = True) -> str:
    """git 한 번. 성공 시 stdout(strip). `check=False` 면 실패도 문자열로 돌려준다."""
    r = subprocess.run(_git_cmd(repo, *args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args)} → rc={r.returncode}\n{(r.stderr or '').strip()}")
    return (r.stdout or "").strip()


def _git_rc(repo: Path, *args: str, timeout: int = 0) -> tuple:
    """git 한 번 — `(rc, stdout+stderr)`. [중요] **실패가 정상 결과인 자리**에서 쓴다.

    머지 충돌·`ls-remote` 부재처럼 *"실패했다"* 가 곧 답인 연산은 예외로 만들면 흐름이
    끊긴다(원전도 `(rc, out)` 형태를 쓴다).

    [주의] **출력 문구로 판정하지 말 것.** 이 기계는 `ko_KR` 이라 git 메시지가 번역된다 —
    *"nothing to commit"* 대조가 조용히 빗나간 전례가 있다(마일스톤 함정 목록). **rc 로
    판정하고**, 문구는 사람에게 보여 줄 때만 쓴다.
    """
    r = subprocess.run(_git_cmd(repo, *args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout or GIT_TIMEOUT)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _noop_log(stage: str, msg: str) -> None:
    pass
