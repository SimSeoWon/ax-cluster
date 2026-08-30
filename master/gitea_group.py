"""`gitea` 그룹 승격 — **필요할 때만** `sg` 로 감싼다 (`#336` ②).

## 왜 이 모듈이 생겼나 (실측 2026-08-29 · 2026-08-30)

bare 저장소는 `gitea` 그룹으로 읽는다(§8.5). 그래서 호출부들이 `sg gitea -c '<cmd>'` 로
감쌌는데, **서비스 컨텍스트에서 그것이 죽는다**:

    ax-projects 유닛   User=sim · NoNewPrivileges=true · RestrictSUIDSGID=true
    실측 오류          bare 를 읽지 못했다 — `setgid: 명령을 허용하지 않음`

[중요] **정작 서비스는 `sg` 가 필요 없다.** `User=sim` 이라 `sim` 의 보조 그룹을 그대로
상속하고, 거기에 `gitea` 가 이미 있다. 실측 2026-08-30:

    getent group gitea            gitea:x:142:sim
    ax-projects MainPID 의 Groups  … 142 …          ← 이미 있다
    id sim                        … 142(gitea) …   ← 대화형도 있다

즉 `sg` 는 **없는 문제를 풀면서 있는 하드닝에 걸렸다.** `#336` ② 가 그 자리다 —
*"`#335`(요청자 등재 경로)를 열어도 등재는 MCP(=서비스)를 타므로 이 버그가 남아 있으면
요청자는 여전히 등재를 못 한다."*

[주의] 그렇다고 `sg` 를 통째로 걷어내지는 않는다. **세션이 그룹 추가 이전에 시작됐으면
프로세스에 그 그룹이 없다**(실측 2026-08-08: DB 에는 있는데 프로세스에는 없었다). 그때는
`sg` 가 유일한 길이다. 그래서 판정은 **DB 가 아니라 `os.getgroups()`** 다 — 지금 이 프로세스가
실제로 무엇을 들고 있는지.

## 정본은 여기 하나다

`events/consumer.py` 가 이 판정을 먼저 갖고 있었고(`_has_gitea_group`), `twin_base` ·
`ontology/drift` 는 **무조건** 감쌌다. 같은 판정이 세 벌이면 조용히 어긋난다 — 이 저장소가
`mcp_for` 에서 값을 치른 그 형태다(2026-08-23: 선언을 바꿨는데 배달이 안 따라왔다).
셋 다 여기를 부른다.

[주의] `sg` 는 호출마다 저널에 그룹 전환 두 줄을 남겨 **정작 읽어야 할 출력을 덮는다** —
안 감싸는 것이 이득이기도 하다.
"""
from __future__ import annotations

import os
import shlex

GROUP = "gitea"


def has_group(name: str = GROUP) -> bool:
    """이 **프로세스**가 그 그룹을 지금 들고 있나. [중요] DB 가 아니라 `os.getgroups()` 다."""
    import grp
    try:
        gid = grp.getgrnam(name).gr_gid
    except KeyError:
        return False
    return gid in os.getgroups() or gid == os.getgid()


def wrap(argv, *, group: str = GROUP, force: bool | None = None) -> list:
    """실행할 argv 를 돌려준다 — 그룹이 이미 있으면 **그대로**, 없으면 `sg` 로 감싼다.

    `force` 는 테스트 주입용이다(`True` 면 항상 감싸고 `False` 면 절대 안 감싼다) — 실제
    그룹 상태에 기대지 않고 두 갈래를 다 검증할 수 있어야 한다.
    """
    argv = list(argv)
    need = (not has_group(group)) if force is None else force
    if not need:
        return argv
    return ["sg", group, "-c", " ".join(shlex.quote(a) for a in argv)]


def wrap_shell(cmd: str, *, group: str = GROUP, force: bool | None = None) -> list:
    """이미 **문자열 한 줄**로 만들어진 명령을 감싼다.

    [주의] 호출부가 `f"git ls-remote --heads {shlex.quote(bare)}"` 처럼 문자열을 들고 있는
    자리가 있어서 둘 다 둔다. 감싸지 않을 때는 셸을 새로 띄우지 않기 위해 `shlex.split` 한다 —
    `sg ... -c` 는 셸을 타지만 직접 실행은 안 타므로, **두 갈래의 파싱 규칙을 같게** 맞춘다.
    """
    need = (not has_group(group)) if force is None else force
    if not need:
        return shlex.split(cmd)
    return ["sg", group, "-c", cmd]
