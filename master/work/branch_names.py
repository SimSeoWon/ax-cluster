"""3-tier 브랜치 규약 — 작업 브랜치 · 조각 durable · 시도 (AgentTest plan v5 C.1 이식 + `#319`).

    base       task/<work_id>/base                              작업 브랜치 — 골조가 **실물로** 올라간다
    durable    task/<work_id>/<task_id>                          조각 — base 에서 갈라진다
    ephemeral  attempt/<work_id>/<task_id>/<workshop>/<ts>       1회용 시도 — 머지 후 폐기

[중요] **계층형 이름은 사용자 결정 ⓐ 다** (2026-08-27, `#317` 미결 ①). 제약 넷이 이 형태를
골랐다 — 근거 전문은 `#317` 의 「미결 ① 결정」 노트에 있고, 여기 옮겨 적는 것은 **이 파일을
고칠 때 깨지는 것**뿐이다:

    ① 훅은 `/` 를 넘는다   `work/pre_push_hook.sh` 의 POSIX `case "refs/heads/task/*"` 는
                            경로 구분자를 가리지 않는다 → **훅을 고칠 필요가 없다**
    ② ref 충돌            `task/W` 와 `task/W/T` 는 **공존 불가**(양방향 실측). 그래서 작업
                            브랜치가 `task/<work_id>` 일 수 없고 `…/base` 여야 한다
    ③ 이름의 SSOT 는 큐    `#197` 이 값을 치렀다 — 하니스가 자기 내부 id 로 durable 을 밀었더니
                            소비자가 *"origin 에 없다"* 로 통째 중단했다. **여기서 id 를 짓지 않는다**

[중요] **`base` 는 leaf 로 예약돼 있다** — `task/<W>/base` 를 durable 로 읽으면 조각 브랜치와
구별되지 않는다. `parse_durable` 이 그 한 자리를 명시적으로 뺀다.

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
BASE_LEAF = "base"                  # [중요] 예약어 — task_id 로 쓸 수 없다 (아래 `_check` 가 막는다)

# 브랜치명 **한 토큰**에 쓸 수 있는 문자. git 이 거부하는 것보다 좁게 잡는다 — 여기서 통과한
# 이름이 나중에 glob·파싱에서 깨지지 않아야 하므로 `/` 도 막는다. 계층은 이 함수가 아니라
# **조립 함수가** 만든다(토큰마다 따로 검사한다).
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
    if kind == "task_id" and v == BASE_LEAF:
        # [중요] 통과시키면 `task/<W>/base` 가 조각 durable 과 같은 이름이 된다 — 작업
        #    브랜치를 조각으로 착각해 머지·정리가 조용히 어긋난다.
        raise BranchNameError(f"task_id 로 {BASE_LEAF!r} 를 쓸 수 없다 — 작업 브랜치의 예약어다")
    return v


def base_branch(work_id: str) -> str:
    """작업 브랜치. **골조가 실물로 올라가는 자리**이고 조각들이 여기서 갈라진다 (`#319`).

    [중요] **마스터가 만들지 않는다** — 요청자(`.33`)가 골조를 커밋하고 push 한다. 마스터는
    없으면 **시끄럽게 실패**한다(`twin_base.resolve`). 조용히 `main` 으로 접으면 조각 N개가
    각자 다른 base 에서 나고, 그때 동결(인터페이스 고정)이 약속으로만 남는다.
    """
    return f"{DURABLE_PREFIX}/{_check('work_id', work_id)}/{BASE_LEAF}"


def durable_branch(work_id: str, task_id: str, round_no: int = 0) -> str:
    """조각 canonical 브랜치. **단일 writer** — 검증을 통과시킨 쪽만 여기 merge 한다.

    🔴 [중요] **라운드 번호가 이름에 들어간다** (사용자 2026-09-04: *"이미 전진했는데 그냥 다
    머지하는게 말이 안되는거니까. 이름 자체에 라운드 번호를 넣는건 좋은 아이디어"*).

        task/<work_id>/r2/<task_id>

    분산 작업(work) 하나는 여러 라운드를 돈다. 라운드 N 조각은 ⑺ 에서 이미 작업 브랜치로
    들어갔으므로, 라운드 N+1 의 머지 대상에 끼면 **이미 전진한 것을 또 머지**하게 된다.
    이름에 라운드가 있으면 목록만 봐도 갈린다.

    [주의] `round_no <= 0` 이면 옛 이름(`task/<work>/<task>`)을 그대로 낸다 — 라운드 스탬프가
    없는 레코드를 조용히 다른 브랜치로 보내지 않기 위해서다.
    """
    head = f"{DURABLE_PREFIX}/{_check('work_id', work_id)}"
    leaf = _check('task_id', task_id)
    return f"{head}/r{int(round_no)}/{leaf}" if int(round_no or 0) > 0 else f"{head}/{leaf}"


def attempt_branch(work_id: str, task_id: str, workshop: str, ts: str) -> str:
    """1회용 시도 브랜치.

    `ts` 를 인자로 받는 이유는 원본과 같다 — **테스트에서 시간을 고정**할 수 있어야 한다.
    같은 작업장이 재시도해도 ts 가 달라 브랜치가 겹치지 않는다.
    """
    return (f"{ATTEMPT_PREFIX}/{_check('work_id', work_id)}/{_check('task_id', task_id)}"
            f"/{_check('workshop', workshop)}/{_check('ts', ts)}")


def is_durable(name: str) -> bool:
    return (name or "").startswith(f"{DURABLE_PREFIX}/")


def is_attempt(name: str) -> bool:
    return (name or "").startswith(f"{ATTEMPT_PREFIX}/")


def is_base(name: str) -> bool:
    return parse_base(name) is not None


def attempt_glob(work_id: str, task_id: str) -> str:
    """그 조각의 모든 시도 브랜치 (일괄 정리용). 계층형이라 glob 이 깔끔하게 걸린다."""
    return (f"{ATTEMPT_PREFIX}/{_check('work_id', work_id)}"
            f"/{_check('task_id', task_id)}/*")


def work_glob(work_id: str) -> str:
    """그 작업의 **모든** 브랜치 — base·조각 durable 을 한 번에 훑는다 (`finalize` 정리)."""
    return f"{DURABLE_PREFIX}/{_check('work_id', work_id)}/*"


def parse_base(name: str) -> str | None:
    """작업 브랜치명 → `work_id`. 아니면 `None`."""
    m = re.match(rf"^{DURABLE_PREFIX}/([^/]+)/{BASE_LEAF}$", name or "")
    return m.group(1) if m else None


def parse_attempt(name: str) -> dict | None:
    """시도 브랜치명 → `{work_id, task_id, workshop, ts}`. 형식이 안 맞으면 `None`.

    [주의] **옛 4토큰 이름도 읽는다** (`attempt/<task_id>/<workshop>/<ts>`) — 그때는
    `work_id=None` 이다. 사용자 결정 2026-08-27: **읽기만 호환, 쓰기는 계층형만.**
    """
    m = re.match(rf"^{ATTEMPT_PREFIX}/([^/]+)/([^/]+)/([^/]+)/([^/]+)$", name or "")
    if m:
        return {"work_id": m.group(1), "task_id": m.group(2),
                "workshop": m.group(3), "ts": m.group(4)}
    m = re.match(rf"^{ATTEMPT_PREFIX}/([^/]+)/([^/]+)/([^/]+)$", name or "")
    if not m:
        return None
    return {"work_id": None, "task_id": m.group(1),
            "workshop": m.group(2), "ts": m.group(3), "legacy": True}


def parse_durable(name: str) -> dict | None:
    """조각 durable 브랜치명 → `{work_id, task_id}`. 아니면 `None`.

    [중요] **작업 브랜치(`…/base`)는 durable 이 아니다** — `None` 을 돌려준다. 그것을 조각으로
    읽으면 통합이 base 를 조각처럼 머지한다.
    [주의] **옛 한 칸짜리도 읽는다** (`task/<task_id>`) — 그때는 `work_id=None` 이고
    `legacy=True` 다. 사용자 결정 2026-08-27: **읽기만 호환, 쓰기는 계층형만.**
    근거: NS bare 에 `task/62efc6a6`(첫 완주 산출물, 머지 갈래 미결) · `task/6ff986ed` 가
    실재한다. 모르는 격으로 두면 `cleanup`·`finalize` 의 도달 가능 판정에서 **조용히 빠져**
    영원히 남는다.
    """
    m = re.match(rf"^{DURABLE_PREFIX}/([^/]+)/([^/]+)$", name or "")
    if m:
        if m.group(2) == BASE_LEAF:
            return None
        return {"work_id": m.group(1), "task_id": m.group(2)}
    m = re.match(rf"^{DURABLE_PREFIX}/([^/]+)$", name or "")
    if not m:
        return None
    return {"work_id": None, "task_id": m.group(1), "legacy": True}
