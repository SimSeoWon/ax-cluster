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


def eligible(lane: str, attempts, *, allow_local: bool = True, excluded=()) -> bool:
    """앞선 실제 시도에 근거해 다음 호출을 허용한다. 쓰기 실패 뒤에는 호출하지 않는다.

    `excluded` (#840 ②) — **앞 재시도에서 형식·사실 검사에 진 클라우드**. 그 클라우드는 다시
    부르지 않고, 그 자리를 건너뛴 것으로 본다(agy 가 빠졌으면 codex 가 첫 순서). [중요] 빠진 것은
    「한도 소진」이 아니다 — claude·로컬을 여는 조건(앞 클라우드 전부 quota)을 채우지 않는다.
    """
    attempts = list(attempts)
    if any(a.get("kind") in ("write", "success") for a in attempts):
        return False
    out = {family(x) for x in excluded or ()}
    seen = {family(a.get("lane", "")): a.get("kind") for a in attempts}
    name = family(lane)
    if name in seen or name in out:
        return False
    if name == "agy":
        return not seen
    if name == "codex":
        return "agy" in seen or "agy" in out
    if name == "claude":
        return all(seen.get(n) == "quota" for n in CLOUD_LANES[:2])
    return allow_local and all(seen.get(n) == "quota" for n in CLOUD_LANES)


def next_lane(attempts, *, local_model: str = "", allow_local: bool = True,
              excluded=()) -> str | None:
    for lane in (*CLOUD_LANES, *((local_model,) if local_model else ())):
        if eligible(lane, attempts, allow_local=allow_local, excluded=excluded):
            return lane
    return None


# ── #840 ② — 재시도를 넘어 「진 클라우드」를 나르는 표지 ─────────────────────────────
#    큐는 실패 detail 의 앞 600자를 `last_feedback` 으로 남기고 다음 시도의 task 에 싣는다.
#    표지는 **누적**이다 — 시도 N 이 앞 시도들의 것까지 다시 적는다(last_feedback 은 덮어쓴다).
LANE_FAIL_RE = re.compile(r"\[lane-fail:([a-z0-9_.,:-]*)\]")
FAULT_KINDS = ("format", "facts")


def parse_lane_failures(text) -> list:
    """`[lane-fail:agy:facts,codex:format]` → `[{lane, kind}]`. 없거나 모르는 값은 버린다."""
    m = LANE_FAIL_RE.search(str(text or ""))
    out = []
    for item in (m.group(1).split(",") if m else ()):
        lane, _, kind = item.partition(":")
        if family(lane) in CLOUD_LANES and kind in FAULT_KINDS and \
                all(family(o["lane"]) != family(lane) for o in out):
            out.append({"lane": family(lane), "kind": kind})
    return out


def format_lane_failures(failures) -> str:
    items = [f"{f['lane']}:{f['kind']}" for f in failures or ()]
    return f"[lane-fail:{','.join(items)}]" if items else ""


def add_lane_failure(failures, lane: str, kind: str) -> list:
    """누적 목록에 이번 실패를 더한다. 클라우드·형식/사실만, 같은 클라우드는 한 번."""
    out = [dict(f) for f in failures or ()]
    name = family(lane)
    if name in CLOUD_LANES and kind in FAULT_KINDS and all(f["lane"] != name for f in out):
        out.append({"lane": name, "kind": kind})
    return out
