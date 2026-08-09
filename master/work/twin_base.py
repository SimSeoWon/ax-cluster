"""작업의 **기준 커밋** — 트윈과 워커 소스를 같은 자리에 묶는다 (레드마인 #21).

## 🔴 ①과 ②는 같은 커밋을 쓴다

    durable `task/<id>` 를 만드는 기준 커밋
      ==  매니페스트의 `twin_commit`
      ==  `<프로젝트>/config.yaml` 의 `index.last_indexed_commit`

**따로 만들 필요가 없다.** 트윈(컨텍스트 문서·온톨로지·그래프)이 그 커밋 기준으로 지어졌으니,
브랜치를 **그 커밋에서 따면** 워커가 받는 소스와 매니페스트의 근거가 **정의상 일치**한다.

지금은 네 좌표(bare · 마스터 미러 · 워터마크 · 워커 체크아웃)가 **우연히** 맞아 있을 뿐이고,
어긋나도 **에러가 나지 않는다** — 매니페스트가 준 클래스·시그니처가 안 맞는데 로컬 LLM 은
주어진 텍스트대로 짠다. 그래서 커밋을 **적어서 보낸다.**

## 🔴 마스터는 읽기만 한다

브랜치를 **만드는 것은 요청자**다 — 마스터는 소스 저장소에 push 할 수 없다(§2.1).
여기서 하는 일은 **이름을 계산하고, 존재를 확인하고, 없으면 무엇을 해야 하는지 말해 주는 것**
까지다.

bare 저장소 읽기에는 `gitea` 그룹이 필요한데 **대화형 세션에는 그 그룹이 없다**(파일상으론
있다 — 재로그인 미실행, 리포트 08 §7.4-2). 서비스는 `SupplementaryGroups=gitea` 로 이미 갖고
있고, 여기서는 **`sg` 로 우회**한다. 읽기 전용이라 §2.1 위반이 아니다.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..context_search.paths import ProjectPaths
from ..projects.config import ConfigError, ProjectConfig
from .branch_names import durable_branch

GIT_TIMEOUT = 30


class TwinBaseError(RuntimeError):
    """기준 커밋을 정할 수 없다. 🔴 **모르는 채로 진행하지 않는다.**"""


@dataclass
class Base:
    """작업 하나의 기준. 🔴 **없는 값을 빈 문자열로 얼버무리지 않는다.**"""
    commit: str
    branch: str
    exists: bool = False
    bare: str = ""
    error: str = ""              # 확인 자체를 못 했으면 그 사유

    @property
    def checked(self) -> bool:
        """존재 여부를 **실제로 확인했나.** `exists=False` 와 "확인 못 함" 은 다르다."""
        return not self.error

    @property
    def summary(self) -> str:
        s = f"{self.branch} @ {self.commit[:8]}"
        if not self.checked:
            return s + f" · ⚠️ 확인 못 함({self.error})"
        return s + (" · ✅ 원격에 있다" if self.exists else " · 🔴 원격에 없다 — 요청자가 만들어야 한다")

    @property
    def instruction(self) -> str:
        """요청자가 실행할 것. 🔴 **마스터가 대신 하지 않는다.**"""
        if self.exists:
            return ""
        return (f"git fetch origin && "
                f"git branch {self.branch} {self.commit} && "
                f"git push -u origin {self.branch}")


def _config(paths: ProjectPaths) -> ProjectConfig:
    """프로젝트 설정. 🔴 **읽기 실패도 이 모듈의 예외로 바꾼다** — 호출자가 `ConfigError` 를
    따로 알아야 하면 베스트에포트 경로가 깨진다(매니페스트 조립이 등록을 막으면 안 된다)."""
    try:
        return ProjectConfig.load(paths.config)
    except ConfigError as e:
        raise TwinBaseError(f"프로젝트 설정을 읽지 못했다: {e}") from e


def twin_commit(paths: ProjectPaths) -> str:
    """트윈이 지어진 커밋. 🔴 **없으면 예외** — 빈 문자열은 "모른다" 를 감춘다."""
    cfg = _config(paths)
    c = (cfg.last_indexed_commit or "").strip()
    if not c:
        raise TwinBaseError(
            f"`index.last_indexed_commit` 이 비었다 ({paths.config}). 트윈이 어느 커밋 기준인지"
            f" 모르는 상태로 작업을 내보내면 워커가 낡은 소스에서 짠다 — 먼저 색인하라")
    return c


def _bare_path(paths: ProjectPaths) -> str:
    return (_config(paths).bare_path or "").strip()


def remote_heads(paths: ProjectPaths, *, runner=None) -> dict:
    """bare 의 브랜치 목록 `{이름: 커밋}`. **읽기 전용.**

    `runner` 는 테스트 주입용 — 실제로는 `sg gitea -c 'git ls-remote --heads <bare>'`.
    """
    bare = _bare_path(paths)
    if not bare:
        raise TwinBaseError(f"`track.bare_path` 가 비었다 ({paths.config})")
    cmd = f"git ls-remote --heads {shlex.quote(bare)}"
    if runner is not None:
        rc, out = runner(cmd)
    else:
        try:
            p = subprocess.run(["sg", "gitea", "-c", cmd], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
            rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        except (subprocess.SubprocessError, OSError) as e:
            rc, out = 255, f"{type(e).__name__}: {e}"
    if rc != 0:
        raise TwinBaseError(f"bare 를 읽지 못했다 — {out.strip()[:160]}")
    heads = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            heads[parts[1][len("refs/heads/"):]] = parts[0]
    return heads


def resolve(paths: ProjectPaths, task_id: str, *, runner=None) -> Base:
    """태스크의 기준을 정한다 — 커밋·브랜치명·존재 여부.

    🔴 **확인 실패를 "없음" 으로 접지 않는다.** 없는 것과 못 본 것은 호출자가 달리 다뤄야 한다:
    전자는 *"요청자가 만들면 된다"*, 후자는 *"왜 못 봤는지 먼저 조사"* 다.
    """
    b = Base(commit=twin_commit(paths), branch=durable_branch(task_id))
    try:
        heads = remote_heads(paths, runner=runner)
    except TwinBaseError as e:
        b.error = str(e)
        return b
    b.bare = _bare_path(paths)
    b.exists = b.branch in heads
    return b


def manifest_section(base: Base) -> list:
    """매니페스트에 넣을 줄. 🔴 **없으면 없다고 쓴다.**"""
    out = [f"- 기준 커밋: `{base.commit}` — **이 매니페스트의 모든 근거가 이 시점 기준이다**",
           f"- 작업 브랜치: `{base.branch}`"]
    if not base.checked:
        out.append(f"- ⚠️ 브랜치 존재를 확인하지 못했다 — {base.error}")
    elif base.exists:
        # 🔴 있으면 있다고 적는다. 침묵하면 낡은 "아직 없다" 와 구분이 안 된다 — 실측
        # 2026-08-09: 등록 시점 매니페스트가 그대로 남아 워커가 있는 브랜치를 없다고 믿었다.
        out.append("- ✅ 그 브랜치가 원격에 있다 — **여기서 시작한다**")
    else:
        out.append("- 🔴 **그 브랜치가 원격에 아직 없다.** 요청자가 먼저 만들어야 워커가 "
                   "작업할 곳이 생긴다:")
        out.append(f"      {base.instruction}")
    out.append("")
    out.append("🔴 **워커는 시작 전 이 커밋까지 `fetch` + fast-forward 로만 따라잡는다.** "
               "못 따라잡으면 작업하지 말고 보고할 것 — `reset --hard` 로 맞추면 사람이 "
               "편집 중이던 것이 사라진다.")
    return out
