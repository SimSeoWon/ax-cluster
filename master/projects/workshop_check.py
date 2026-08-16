"""워크숍 체크아웃이 자동화를 받아도 안전한지 판정한다 (PLAN §5.5.4-⑥-1).

**왜 필요한가.** 자동화는 브랜치를 바꾸고 경우에 따라 리셋한다. 사람이 커밋하지 않은
작업을 남겨 뒀다면 그걸 날린다. 클론을 하나 더 파는 대신 **시작 전에 막는다.**

[중요] **"더럽다"를 뭉뚱그리면 안 된다 — 추적 파일과 미추적은 위험이 다르다.**

    추적 파일 수정·스테이지  →  checkout / reset --hard 가 **날린다**   → 차단
    미추적 (`??`)            →  날리지 않는다 (`git clean` 만 지운다)   → 통과

실측(2026-08-08) `.2` 의 `E:\trunk\ModularStage` 는 `?? AgentWiki/`·`?? AgentWiki.zip` 로
**지금도 더럽다.** 뭉뚱그려 막았다면 자동화가 첫날부터 아무것도 못 했다.

[중요] **자동화는 `git clean` 을 절대 부르지 않는다.** 그게 미추적을 통과시켜도 되는 전제다.
이 모듈은 그래서 정리 기능을 제공하지 않는다 — 판정만 한다.

[중요] **검사하지 못하면 통과가 아니라 차단이다.** SSH 실패·타임아웃·저장소 아님·경로 없음은
전부 "안전을 확인하지 못했다"이지 "안전하다"가 아니다.

## [중요] 범위는 `Source/` 하위다 (사용자 결정 2026-08-09)

색인·그래프는 이미 `repo/Source/**` 한정인데(§5.2-E) **더티 체크만 저장소 전체를 보고
있었다.** 그 어긋남이 실제로 `.2` 를 막았다 — 실측:

    M Automation_ModularStage.slnx · M ModularStage.slnx · M ModularStage.uproject
    (`.uproject` 의 diff 는 `EngineAssociation` GUID → "5.8")

셋 다 **UE5/VS 가 프로젝트를 열 때 다시 쓰는 머신 지역 파일**이다. 사용자 판단:
*"그쪽은 리소스나 엔진, 에디터용 메타데이터 등 바뀔 여지가 커"* — 에디터를 열기만 해도
바뀌는 영역을 감시하면 게이트가 **항상 빨간불**이 되고, 항상 빨간 게이트는 게이트가 아니다.

[주의] **맞바꾼 것**: 범위 밖(`Content/` 의 `.uasset` 등)의 미커밋 변경은 이제 **차단하지 않는다.**
받아들일 수 있는 근거는 셋이다 — ⑴ 워커는 `Source/` 밖에 쓰지 않는다(스킬 §5)
⑵ 스킬이 `git clean`·`reset --hard` 를 금지하므로 남은 위험은 브랜치 전환뿐인데, git 은
로컬 수정을 덮어써야 하면 **체크아웃을 거부한다** ⑶ 사람이 실제로 작업하는 기계(`.33`)는
`requester` 라 애초에 파견 대상이 아니다.

[중요] **그래서 범위 밖도 세어서 보고한다.** 차단하지 않는 것과 못 본 것은 다르다 — 판정문에
"범위 밖 N건" 이 남지 않으면 다음 세션이 "깨끗하다" 를 저장소 전체로 오해한다.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .config import DRIVEN_SSH, ConfigError, ProjectConfig, Registry, Workshop

# SSH 가 응답하지 않는 경우를 위한 상한. 여기 걸리면 fail-closed 다.
DEFAULT_TIMEOUT = 20

# [중요] 차단 판정의 범위. 색인·그래프와 **같은 경계**여야 한다 (§5.2-E). 위 § 참조.
SOURCE_SCOPE: tuple = ("Source/",)


def _porcelain_path(line: str) -> str:
    """포세린 한 줄에서 경로. 이름변경(`R  old -> new`)은 **새 경로**를 본다."""
    p = line[3:].strip() if len(line) > 3 else ""
    if " -> " in p:
        p = p.split(" -> ", 1)[1]
    return p.strip('"').replace("\\", "/").lstrip("./")


def split_scope(paths: list, scope: tuple = SOURCE_SCOPE) -> tuple:
    """포세린 줄들을 (범위 안, 범위 밖) 으로 가른다. [중요] **밖도 버리지 않고 돌려준다.**"""
    inside, outside = [], []
    for line in paths:
        (inside if any(_porcelain_path(line).startswith(s) for s in scope)
         else outside).append(line)
    return inside, outside

Runner = Callable[[Sequence[str], int], subprocess.CompletedProcess]


def _run(cmd: Sequence[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd), capture_output=True, text=True, timeout=timeout, check=False
    )


@dataclass
class Cleanliness:
    """한 워크숍의 판정 결과."""

    host: str
    path: str
    ok: bool                                  # 자동화를 시작해도 되는가
    checked: bool                             # 실제로 검사에 성공했는가
    reason: str = ""
    blocking: list[str] = field(default_factory=list)   # 차단 사유(범위 안 추적 파일 변경)
    untracked: list[str] = field(default_factory=list)  # 통과시킨 미추적
    # [중요] 범위 밖의 추적 파일 변경. **차단하지 않지만 세어서 보고한다** — 차단하지 않는 것과
    # 못 본 것은 다르다(툴체인 재생성물이 여기 들어온다).
    out_of_scope: list[str] = field(default_factory=list)
    scope: tuple = SOURCE_SCOPE

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "path": self.path,
            "ok": self.ok,
            "checked": self.checked,
            "reason": self.reason,
            "blocking": self.blocking,
            "untracked": self.untracked,
            "out_of_scope": self.out_of_scope,
            "scope": list(self.scope),
        }


def parse_porcelain(text: str) -> tuple[list[str], list[str]]:
    """`git status --porcelain` 출력을 (차단 대상, 미추적) 으로 가른다.

    포세린 v1 은 앞 2칸이 상태 코드다. `??` 만 미추적이고 나머지는 전부 추적 파일의
    변경이다 — `!!`(무시됨)는 `--porcelain` 기본 출력에 나오지 않는다.
    """
    blocking: list[str] = []
    untracked: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("??"):
            untracked.append(line[3:].strip())
        else:
            blocking.append(line.rstrip())
    return blocking, untracked


def check_workshop(
    shop: Workshop,
    *,
    runner: Runner = _run,
    timeout: int = DEFAULT_TIMEOUT,
    scope: tuple = SOURCE_SCOPE,
) -> Cleanliness:
    """워크숍 한 대를 판정한다. **판정만 하고 아무것도 고치지 않는다.**"""
    res = Cleanliness(host=shop.host, path=shop.path, ok=False, checked=False, scope=scope)

    if not shop.drivable:
        # 대화형 워크숍은 마스터가 몰지 않으므로 검사 대상이 아니다.
        # ok=False 지만 이건 "차단"이 아니라 "해당 없음" 이다 — reason 으로 구분한다.
        res.reason = (
            f"driven={shop.driven} 이라 마스터가 원격으로 몰지 않는다 — 검사 대상이 아니다."
        )
        return res
    if not shop.path or not shop.user:
        res.reason = "driven=ssh 인데 path/user 가 없다 — 설정이 깨졌다."
        return res

    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={max(5, timeout // 2)}",
        f"{shop.user}@{shop.host}",
        f'git -C "{shop.path}" status --porcelain',
    ]
    try:
        proc = runner(cmd, timeout)
    except subprocess.TimeoutExpired:
        res.reason = f"SSH 가 {timeout}초 안에 응답하지 않았다 — 확인 실패이므로 차단한다."
        return res
    except OSError as e:
        res.reason = f"SSH 실행 실패: {e} — 확인 실패이므로 차단한다."
        return res

    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        tail = err[-1] if err else f"exit {proc.returncode}"
        res.reason = (
            f"원격 git 이 실패했다({tail}). 경로가 없거나 저장소가 아닐 수 있다 — "
            "확인 실패이므로 차단한다."
        )
        return res

    tracked, untracked = parse_porcelain(proc.stdout or "")
    # [중요] 한 번의 SSH 로 둘 다 얻는다 — 범위를 pathspec 으로 좁히면 밖을 **세지도 못한다.**
    blocking, outside = split_scope(tracked, scope)
    res.checked = True
    res.untracked = untracked
    res.blocking = blocking
    res.out_of_scope = outside
    where = "|".join(scope)
    if blocking:
        res.ok = False
        res.reason = (
            f"{where} 안의 추적 파일에 커밋되지 않은 변경이 {len(blocking)}건 있다. "
            "브랜치 전환·리셋이 이것을 날린다 — 사람이 정리할 때까지 시작하지 않는다."
        )
    else:
        res.ok = True
        # [중요] 좁혔다는 사실을 판정문에 남긴다. "깨끗하다" 를 저장소 전체로 오해하면 안 된다.
        res.reason = f"{where} 안의 추적 파일은 깨끗하다."
        if outside:
            res.reason += (
                f" [주의] 범위 밖 추적 변경 {len(outside)}건은 **차단하지 않는다**"
                f"(리소스·엔진·에디터 메타데이터는 열기만 해도 바뀐다): "
                + ", ".join(_porcelain_path(x) for x in outside[:3])
                + (" 외" if len(outside) > 3 else "")
            )
        if untracked:
            res.reason += (
                f" 미추적 {len(untracked)}건은 통과시킨다"
                " — checkout/reset 이 지우지 않는다. [중요] git clean 을 부르지 말 것."
            )
    return res


def check_project_workshops(
    name: str = "",
    *,
    registry: Registry | None = None,
    runner: Runner = _run,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """프로젝트의 워크숍 전부를 판정하고, 지금 작업을 보낼 수 있는 곳을 돌려준다.

    `name` 을 비우면 지금 마운트된 프로젝트를 본다.
    """
    reg = registry or Registry.load()
    target = name or reg.active
    if not target:
        raise ConfigError("active 가 비어 있고 name 도 주지 않았다.")
    if target not in reg.names:
        raise ConfigError(f"등록되지 않은 프로젝트다: {target}")

    cfg: ProjectConfig = reg.config_of(target)
    results = [
        check_workshop(shop, runner=runner, timeout=timeout)
        for shop in cfg.workshops.values()
    ]
    dispatchable = [r.host for r in results if r.ok]
    return {
        "project": target,
        "dispatchable": dispatchable,
        "results": [r.to_dict() for r in results],
        "note": (
            f"작업을 보낼 수 있는 워크숍: {', '.join(dispatchable)}"
            if dispatchable
            else "지금 작업을 보낼 수 있는 워크숍이 없다."
        ),
    }
