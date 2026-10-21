"""생성 호출의 quota 전용 폴백 정책 (#840). 응답 본문은 실패 분류에 넣지 않는다."""
from __future__ import annotations

import re

from . import revise

CLOUD_LANES = ("agy", "codex", "claude")
FAILURE_KINDS = ("quota", "format", "facts", "error", "write")


def family(lane: str) -> str:
    name = str(lane or "").partition(":")[0]
    return name if name in CLOUD_LANES else "local"


def classify_failure(error: str, *, kind: str = "error") -> str:
    """호출 실패 채널만 quota로 분류한다. 검증·쓰기 실패는 quota 문구와 무관하다."""
    if kind != "error":
        if kind not in FAILURE_KINDS:
            raise ValueError(f"unknown failure kind: {kind}")
        return kind
    text = str(error or "").lower()
    evidence = re.search(
        r"insufficient_quota|resource_exhausted|quota_exhausted|"
        r"(?:quota|credits?)[\s:._-]+(?:exhausted|exceeded|depleted)|"
        r"(?:exhausted|exceeded|insufficient)[\s:._-]+quota|"
        r"(?:hit|reached|exceeded)[^\n]{0,30}(?:usage|session|rate) limit|"
        r"(?:usage|session|rate) limit[^\n]{0,30}(?:hit|reached|exceeded|exhausted)|"
        r"rate limit(?:ed|ing)|429[^\n]{0,60}(?:too many|retry|rate limit)|"
        r"too many requests", text)
    hit = revise.quota_exhausted([error]) or "resource_exhausted" in text
    return "quota" if evidence and hit else "error"


def eligible(lane: str, attempts, *, allow_local: bool = True) -> bool:
    """앞선 실제 시도에 근거해 다음 호출을 허용한다. 쓰기 실패 뒤에는 호출하지 않는다."""
    attempts = list(attempts)
    if any(a.get("kind") in ("write", "success") for a in attempts):
        return False
    seen = {family(a.get("lane", "")): a.get("kind") for a in attempts}
    name = family(lane)
    if name in seen:
        return False
    if name == "agy":
        return not seen
    if name == "codex":
        return "agy" in seen
    if name == "claude":
        return all(seen.get(n) == "quota" for n in CLOUD_LANES[:2])
    return allow_local and all(seen.get(n) == "quota" for n in CLOUD_LANES)


def next_lane(attempts, *, local_model: str = "", allow_local: bool = True) -> str | None:
    for lane in (*CLOUD_LANES, *((local_model,) if local_model else ())):
        if eligible(lane, attempts, allow_local=allow_local):
            return lane
    return None
