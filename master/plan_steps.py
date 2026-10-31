"""태스크 실행 7단계의 **해당 여부 판정** — `#826` T4.

#826 §3 의 순서(버전 동기화 → 프리 에디터 → 소스 → 제네레이트 → 빌드 → 에디터 → 기록)가
프로젝트 타입(`profile.kind_of`)마다 어디까지 해당하는지를 정한다. 판정은 셋이다:

    실행       이 타입에서 늘 한다
    해당없음   이 타입에는 그 단계가 없다 — 사유를 남긴다(#826: 「해당 없음과 사유」)
    조건부     타입만으로는 못 정한다 — 태스크가 정한다(예: 클래스 추가·제거일 때만 제네레이트)

[중요] **모르는 타입은 판정하지 않는다** (`StepError`). `kind_of` 의 빈 값을 unreal 로 읽으면
엔진이 없는 프로젝트에 제네레이트·에디터 단계를 내보낸다 — 등재가 빈 kind 를 거절하는 것과
같은 이유다(`profile.missing`). `index_only` 도 거절한다 — 분산 작업을 받지 않는 타입이다.
[주의] 조건부 단계를 실제로 할지는 이 모듈이 정하지 않는다. 그 판단과 MCP 준비 확인은
에디터 연동(#856) 이후 태스크 쪽 몫이다.
"""
from __future__ import annotations

from dataclasses import dataclass

RUN, SKIP, COND = "실행", "해당없음", "조건부"

STEPS = (
    (1, "버전 동기화·상태 확인"),
    (2, "프리 에디터 작업"),
    (3, "소스 작업"),
    (4, "프로젝트 제네레이트"),
    (5, "소스코드 빌드"),
    (6, "에디터 작업"),
    (7, "작업 상태 확인·인수인계 기록"),
)

_NO_EDITOR = "에디터·어셋이 없는 타입이다"
_TABLE = {
    "code": {
        1: (RUN, "작업 기준 리비전 확인"),
        2: (SKIP, f"kind=code — {_NO_EDITOR}"),
        3: (RUN, "프로필 work_exts 안의 파일만"),
        4: (SKIP, "kind=code — 재생성할 프로젝트 파일이 없다"),
        5: (RUN, "kind=code — 정적 검사(pystatic)와 공식 통합 검사로 대신한다"),
        6: (SKIP, f"kind=code — {_NO_EDITOR}"),
        7: (RUN, "플랜 영역 마킹·노트"),
    },
    "unreal": {
        1: (RUN, "Git/SVN 업데이트와 기준 리비전 확인 — 프리 에디터보다 먼저"),
        2: (COND, "소스 변경 전 에디터 정리가 필요할 때(클래스 제거면 상속 어셋 조사·승인 뒤 제거)"),
        3: (RUN, "플랜에 따른 클래스 추가·수정·제거"),
        4: (COND, "클래스 추가·제거로 프로젝트 파일 재생성이 필요할 때"),
        5: (RUN, "UE 소스 빌드와 컴파일 결과 확인"),
        6: (COND, "플랜에 어셋 생성·편집·블루프린트 작업이 있을 때 — MCP 연결·도구 확인 뒤"),
        7: (RUN, "플랜 영역 마킹·노트"),
    },
}


class StepError(ValueError):
    """단계를 판정할 수 없다 — 사유 문장을 담는다."""


@dataclass(frozen=True)
class Step:
    no: int
    name: str
    applies: str
    reason: str


def steps_for_kind(kind: str) -> list[Step]:
    """프로젝트 타입 하나의 7단계 판정표."""
    k = (kind or "").strip()
    if k == "index_only":
        raise StepError("kind=index_only 는 분산 작업을 받지 않는다 (`#693`) — 실행 단계가 없다")
    if k not in _TABLE:
        raise StepError(f"프로젝트 타입을 모른다 ({k!r}) — 프로필 kind 를 먼저 적는다. "
                        "빈 값을 unreal 로 읽지 않는다")
    return [Step(no, name, *_TABLE[k][no]) for no, name in STEPS]


def steps_for_project(project: str, *, kind_of=None) -> list[Step]:
    """등록 프로필의 kind 로 판정한다."""
    if kind_of is None:
        from master.projects.profile import kind_of
    return steps_for_kind(kind_of(project))
