"""작업의 **기준** — 조각들이 갈라져 나오는 **작업 브랜치** (레드마인 #21 · `#319`).

## [중요] 기준은 이제 트윈 커밋이 아니라 **작업 브랜치 tip** 이다 (`#319`, 2026-08-27)

    조각 durable `task/<work_id>/<task_id>` 가 갈라지는 자리
      ==  작업 브랜치 `task/<work_id>/base` 의 tip
      ==  요청자가 **골조를 실물로 커밋한** 커밋

**왜 바뀌었나**: 종전 기준은 `index.last_indexed_commit`(사실상 `main`)이었고, 그래서 조각
N개가 **각자 main 에서 독립적으로** 났다. 골조는 브랜치에 없고 매니페스트 텍스트로만 실려
워커마다 자기 트리에 따로 썼다. 그 결과 **인터페이스 동결이 약속으로만 존재**했다 — 같은
헤더를 본다는 보장이 git 에 없었다. 작업 브랜치에 골조가 실물로 있으면 조각들이 **같은 커밋의
같은 헤더**를 본다.

## [중요] 없으면 **시끄럽게 실패한다** — 조용히 main 으로 접지 않는다

`#319` 완료 조건 2 가 못박은 자리다. 접으면 위의 "각자 main 에서 난다" 가 그대로 돌아오고,
**아무도 그것을 모른다.** `resolve()` 는 없으면 `exists=False` 로 두고 `commit` 을 비운다 —
호출자가 그 값으로 브랜치를 따려다 실패해야 한다.

[주의] **트윈 커밋은 여전히 쓴다** — 작업 브랜치를 *처음 만들 때*의 출발점(`instruction`)과
매니페스트의 "근거 시점" 표기가 그것이다. 사라진 것은 *"조각의 기준"* 이라는 역할뿐이다.

지금은 네 좌표(bare · 마스터 미러 · 워터마크 · 워커 체크아웃)가 **우연히** 맞아 있을 뿐이고,
어긋나도 **에러가 나지 않는다** — 매니페스트가 준 클래스·시그니처가 안 맞는데 로컬 LLM 은
주어진 텍스트대로 짠다. 그래서 커밋을 **적어서 보낸다.**

## [중요] 마스터는 읽기만 한다

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
from .branch_names import base_branch

GIT_TIMEOUT = 30


class TwinBaseError(RuntimeError):
    """기준 커밋을 정할 수 없다. [중요] **모르는 채로 진행하지 않는다.**"""


@dataclass
class Base:
    """작업 하나의 기준. [중요] **없는 값을 빈 문자열로 얼버무리지 않는다.**

    `commit` 은 **작업 브랜치의 tip** 이다(`#319`). 브랜치가 없으면 비어 있고, 그때
    `twin` 이 "여기서 만들라" 의 출발점을 들고 있다.
    """
    commit: str
    branch: str
    twin: str = ""               # 트윈이 지어진 커밋 — 작업 브랜치를 **처음 만들 때**의 출발점
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
            return s + f" · [주의] 확인 못 함({self.error})"
        return s + (" · [완료] 원격에 있다" if self.exists else " · [중요] 원격에 없다 — 요청자가 만들어야 한다")

    @property
    def instruction(self) -> str:
        """요청자가 실행할 것. [중요] **마스터가 대신 하지 않는다.**

        [중요] 작업 브랜치는 **골조를 담아야** 쓸모가 있다(`#319`). 브랜치만 따면 조각들이
        빈 base 에서 갈라지고, 동결은 다시 약속으로만 남는다. 그래서 골조 커밋과 UHT 검사를
        같이 적는다 — `#317` 미결 ①·② 가 정한 순서다.
        """
        if self.exists:
            return ""
        start = self.twin or "origin/main"
        return (f"git fetch origin && "
                f"git switch -c {self.branch} {start} && "
                f"#  골조 .h + 주석 작업지시서를 여기 커밋한다 (실물로) && "
                f"#  UHT 게이트를 통과시킨다 (풀 빌드가 아니다 — `#317` 미결 ② 결정) && "
                f"git push -u origin {self.branch}")


def _config(paths: ProjectPaths) -> ProjectConfig:
    """프로젝트 설정. [중요] **읽기 실패도 이 모듈의 예외로 바꾼다** — 호출자가 `ConfigError` 를
    따로 알아야 하면 베스트에포트 경로가 깨진다(매니페스트 조립이 등록을 막으면 안 된다)."""
    try:
        return ProjectConfig.load(paths.config)
    except ConfigError as e:
        raise TwinBaseError(f"프로젝트 설정을 읽지 못했다: {e}") from e


def twin_commit(paths: ProjectPaths) -> str:
    """트윈이 지어진 커밋. [중요] **없으면 예외** — 빈 문자열은 "모른다" 를 감춘다."""
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


def resolve(paths: ProjectPaths, work_id: str, *, runner=None) -> Base:
    """**작업 브랜치**의 기준을 정한다 — 이름·tip 커밋·존재 여부 (`#319` 완료 조건 2).

    [중요] **확인 실패를 "없음" 으로 접지 않는다.** 없는 것과 못 본 것은 호출자가 달리 다뤄야 한다:
    전자는 *"요청자가 만들면 된다"*, 후자는 *"왜 못 봤는지 먼저 조사"* 다.

    [중요] **없으면 `commit` 이 빈 채로 돌아온다 — 조용히 트윈 커밋으로 접지 않는다.**
    접으면 조각 N개가 각자 그 커밋에서 나고(=옛 동작), 골조가 base 에 없다는 사실이 아무
    데도 안 남는다. 빈 값을 받은 호출자는 브랜치를 딸 수 없어 **거기서 멈춘다.**
    """
    b = Base(commit="", branch=base_branch(work_id))
    try:
        b.twin = twin_commit(paths)
    except TwinBaseError as e:
        # [주의] 트윈 커밋은 **출발점 안내용**이다 — 없다고 작업 브랜치 조회까지 막지 않는다.
        #    브랜치가 이미 있으면 안내가 필요 없고, 그 경우까지 죽이면 등록이 못 돈다.
        b.error = str(e)
    try:
        heads = remote_heads(paths, runner=runner)
    except TwinBaseError as e:
        b.error = str(e)
        return b
    b.error = ""
    b.bare = _bare_path(paths)
    b.exists = b.branch in heads
    if b.exists:
        b.commit = heads[b.branch]
    return b


def manifest_section(base: Base) -> list:
    """매니페스트에 넣을 줄. [중요] **없으면 없다고 쓴다.**

    [중요] `#319` 로 이 절의 무게가 커졌다 — 골조가 **여기 적힌 브랜치에 실물로** 있고,
    매니페스트에는 더 이상 골조 텍스트가 실리지 않는다(완료 조건 3). 이 절이 틀리면 워커는
    골조를 어디서도 못 찾는다.
    """
    out = [f"- 작업 브랜치: `{base.branch}` — **조각은 여기서 갈라진다**",
           f"- 기준 커밋(작업 브랜치 tip): `{base.commit or '(미상)'}` — "
           f"**이 매니페스트의 모든 근거가 이 시점 기준이다**",
           "- [중요] **골조는 이 브랜치에 실물로 있다** — 매니페스트에 텍스트로 싣지 않는다 "
           "(`#319`). 체크아웃하면 헤더가 이미 트리에 있고, 그것이 인터페이스 동결이다"]
    if base.twin:
        out.append(f"- (참고) 트윈이 지어진 커밋: `{base.twin}`")
    if not base.checked:
        out.append(f"- [주의] 브랜치 존재를 확인하지 못했다 — {base.error}")
    elif base.exists:
        # [중요] 있으면 있다고 적는다. 침묵하면 낡은 "아직 없다" 와 구분이 안 된다 — 실측
        # 2026-08-09: 등록 시점 매니페스트가 그대로 남아 워커가 있는 브랜치를 없다고 믿었다.
        out.append("- [완료] 그 브랜치가 원격에 있다 — **여기서 시작한다**")
    else:
        out.append("- [중요] **그 브랜치가 원격에 아직 없다.** 요청자가 먼저 만들어야 워커가 "
                   "작업할 곳이 생긴다:")
        out.append(f"      {base.instruction}")
    out.append("")
    out.append("[중요] **워커는 시작 전 이 커밋까지 `fetch` + fast-forward 로만 따라잡는다.** "
               "못 따라잡으면 작업하지 말고 보고할 것 — `reset --hard` 로 맞추면 사람이 "
               "편집 중이던 것이 사라진다.")
    return out
