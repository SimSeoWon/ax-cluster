"""2-tier 브랜치 규약 (AgentTest plan v5 C.1 이식).

    durable    task/<task_id>                       canonical — 검증 통과분 + 피드백 누적
    ephemeral  attempt/<task_id>/<workshop>/<ts>    1회용 시도 — 머지 후 폐기

[중요] **이 규약이 zombie race 를 구조적으로 없앤다.** 작업장 A 가 타임아웃되어 B 에 재배정돼도
A=`attempt/t5/HV0I6DL/t1`, B=`attempt/t5/JFVS693/t2` 로 **서로 다른 ref** 다. A 가 되살아나
push 해도 자기 죽은 브랜치로 갈 뿐 durable 과 B 를 건드리지 못한다. **공유 write 타깃이 없어
force-with-lease race 자체가 성립하지 않는다.**

§4.2 가 확정한 대로 **작업장이 2곳이고 같은 UE5 프로젝트를 본다** — 경쟁은 가정이 아니라
실재이므로 이 규약은 성능 최적화가 아니라 **정확성 요건**이다.

**원본에서 뺀 것:** `select_work_branch(distribution_mode, ...)` — pull 모드일 때 레거시
`worker/<id>/<task>` 를 쓰는 feature-flag 분기다. 우리에게는 **호환할 레거시 브랜치 이력이
없다.** 배포한 적 없는 모드를 위한 플래그는 검증할 수도 없으므로 넣지 않는다
(BM25 의 구 스키마 마이그레이션을 뺀 것과 같은 판단).

[주의] **`worker` 라는 단어를 쓰지 않는다.** 이 저장소에서 `worker/` 는 BC-250 추론 노드다(§4.1).
브랜치의 그 자리에 오는 것은 **작업장(workshop)** — 파일을 소유한 윈도우 PC 다.
"""
from __future__ import annotations

import re

DURABLE_PREFIX = "task"
ATTEMPT_PREFIX = "attempt"

# 브랜치명에 쓸 수 없는 문자를 걸러낸다. git 이 거부하는 것보다 좁게 잡는다 —
# 여기서 통과한 이름이 나중에 glob·파싱에서 깨지지 않아야 하므로 `/` 도 막는다.
_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


class BranchNameError(ValueError):
    """식별자가 브랜치명에 쓸 수 없다. **조용히 정규화하지 않는다** — 이름이 곧 정체성이라
    말없이 바꾸면 두 작업장이 서로 다른 것을 같은 것으로 볼 수 있다."""


def _check(kind: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise BranchNameError(f"{kind} 가 비었다")
    if not _SAFE.match(v):
        raise BranchNameError(
            f"{kind} 에 쓸 수 없는 문자가 있다: {value!r} — 허용: 영숫자 . _ -"
        )
    return v


def durable_branch(task_id: str) -> str:
    """canonical 브랜치. **단일 writer** — 검증을 통과시킨 쪽만 여기 merge 한다."""
    return f"{DURABLE_PREFIX}/{_check('task_id', task_id)}"


def attempt_branch(task_id: str, workshop: str, ts: str) -> str:
    """1회용 시도 브랜치.

    `ts` 를 인자로 받는 이유는 원본과 같다 — **테스트에서 시간을 고정**할 수 있어야 한다.
    같은 작업장이 재시도해도 ts 가 달라 브랜치가 겹치지 않는다.
    """
    return (f"{ATTEMPT_PREFIX}/{_check('task_id', task_id)}"
            f"/{_check('workshop', workshop)}/{_check('ts', ts)}")


def is_durable(name: str) -> bool:
    return (name or "").startswith(f"{DURABLE_PREFIX}/")


def is_attempt(name: str) -> bool:
    return (name or "").startswith(f"{ATTEMPT_PREFIX}/")


def attempt_glob(task_id: str) -> str:
    """그 task 의 모든 시도 브랜치 (일괄 정리용). 계층형이라 glob 이 깔끔하게 걸린다."""
    return f"{ATTEMPT_PREFIX}/{_check('task_id', task_id)}/*"


def parse_attempt(name: str) -> dict | None:
    """시도 브랜치명 → `{task_id, workshop, ts}`. 형식이 안 맞으면 `None`.

    **정확히 4토큰**만 받는다. task_id 에 `/` 가 없다는 전제이고, 그 전제는 `_check` 가 강제한다.
    """
    m = re.match(rf"^{ATTEMPT_PREFIX}/([^/]+)/([^/]+)/([^/]+)$", name or "")
    if not m:
        return None
    return {"task_id": m.group(1), "workshop": m.group(2), "ts": m.group(3)}


def parse_durable(name: str) -> str | None:
    """durable 브랜치명 → `task_id`. 아니면 `None`."""
    m = re.match(rf"^{DURABLE_PREFIX}/([^/]+)$", name or "")
    return m.group(1) if m else None
