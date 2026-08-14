"""엔드포인트 헬스체크 + 상주 재확립 — PLAN §9.4.2.

두 가지 일을 한다:
  1. `/api/tags`·`/api/ps` 로 각 노드의 **보유 모델**과 **지금 VRAM 에 올라온 모델**을 갱신
  2. 의도한 상주(`pin`)가 풀려 있으면 **다시 올린다**

2번이 있는 이유 — 상주 고정이 지금은 요청 단위 `keep_alive:-1` 이라 Ollama 재시작이나
보드 재부팅이면 풀린다. BC-250 유닛은 `KEEP_ALIVE=30m` 이라 유휴 30분이면 내려간다.
유닛을 고치려면 root 가 필요하고, 무엇보다 **재부팅에도 자동 복구되는 쪽이 낫다.**
"""
from __future__ import annotations

import logging
import time

from .config import DEFAULT_NUM_CTX
from .routing import Endpoint

log = logging.getLogger("ax-broker.health")

# 재적재는 비싸다(35B ~61s). 실패해도 매 사이클 재시도하면 노드를 계속 두드리게 되므로
# 같은 엔드포인트에 대해 이 간격 안에는 다시 시도하지 않는다.
_REPIN_BACKOFF_SEC = 300


def _name_matches(a: str, b: str) -> bool:
    """Ollama 는 `x` 와 `x:latest` 를 같게 취급한다."""
    if a == b:
        return True
    return a.removesuffix(":latest") == b.removesuffix(":latest")


async def refresh(ep: Endpoint, client) -> None:
    """한 엔드포인트의 보유·상주·건강을 실측으로 갱신. 예외를 밖으로 던지지 않는다
    — 노드 하나가 죽었다고 헬스루프가 멈추면 나머지도 같이 눈이 먼다."""
    try:
        r = await client.get(f"http://{ep.host}/api/tags", timeout=8.0)
        r.raise_for_status()
        ep.models = [m["name"] for m in (r.json().get("models") or [])]
        ep.healthy = True
        ep.last_error = ""
        ep.resident_known = True
    except Exception as e:
        ep.healthy = False
        ep.models = []
        ep.resident = None
        ep.resident_known = False       # 🔴 모른다 — 없다가 아니다
        ep.last_error = f"{type(e).__name__}: {e}"
        return
    try:
        r = await client.get(f"http://{ep.host}/api/ps", timeout=8.0)
        r.raise_for_status()
        loaded = r.json().get("models") or []
        ep.resident = loaded[0]["name"] if loaded else None
        ep.resident_known = True
    except Exception as e:
        # tags 가 됐는데 ps 가 실패한 건 부분 장애다. 건강 판정은 유지하되 상주는 모른다고 본다.
        # 🔴 **그 「모른다」를 값으로 남긴다** — 예전엔 `None`(=없다)과 구별이 안 돼서
        # `ensure_pinned` 가 재적재를 걸었다.
        ep.resident = None
        ep.resident_known = False
        ep.last_error = f"ps: {type(e).__name__}: {e}"


async def ensure_pinned(ep: Endpoint, pin: str, client, state: dict) -> bool:
    """`pin` 이 상주하고 있지 않으면 다시 올린다. 실제로 적재를 시도했으면 True.

    🔴 **in-flight 요청이 있으면 건드리지 않는다.** `MAX_LOADED_MODELS=1` 이라 다른 모델을
    올리면 지금 쓰이는 모델이 **쫓겨난다** — 폴백으로 14b 를 쓰는 중에 브로커가 35B 를
    복구하려 들면 그 요청을 죽이는 꼴이다. 재확립은 노드가 놀 때만 한다.
    """
    if not ep.healthy or not pin:
        return False
    if ep.resident and _name_matches(ep.resident, pin):
        return False
    if not ep.resident_known:
        # 🔴 **판정 불가는 보존**이다. `/api/ps` 를 못 읽은 노드에 35B 적재를 거는 것은
        # 힘들어하는 보드에 가장 비싼 일을 시키는 것이다 (2026-08-15: 그 직후 멈췄다).
        log.info("[repin] %s 건너뜀 — 상주를 못 읽었다 (없다는 뜻이 아니다)", ep.name)
        return False
    if state.get("inflight", {}).get(ep.name, 0) > 0:
        log.info("[repin] %s 건너뜀 — 처리 중인 요청이 있다 (쫓아내면 안 된다)", ep.name)
        return False
    last = state.setdefault("repin_at", {}).get(ep.name, 0.0)
    if time.time() - last < _REPIN_BACKOFF_SEC:
        return False
    state["repin_at"][ep.name] = time.time()
    log.warning("[repin] %s 상주 복구 시도: %s → %s", ep.name, ep.resident or "(없음)", pin)
    try:
        r = await client.post(
            f"http://{ep.host}/api/generate",
            # 🔴 **`num_ctx` 를 반드시 싣는다.** 안 실으면 Ollama 가 모델 기본
            # `context_length`(35B 는 262144) 전제로 KV 를 잡는다 — BC-250 여유가 2.2GB 인데
            # 그 할당이 ~2.0GB 다(리포트 10 §8). 프록시 경로(`server.py`)에는 이 가드가
            # 있었고 **이 경로에만 없었다**(2026-08-15 실측: repin 직후 보드 정지).
            # 값이 프록시와 **같아야** 한다 — 다르면 다음 요청이 통째로 재적재된다(61.6s 실측).
            json={"model": pin, "prompt": "ok", "stream": False, "keep_alive": -1,
                  "options": {"num_predict": 1, "temperature": 0,
                              "num_ctx": DEFAULT_NUM_CTX}},
            timeout=300.0,
        )
        r.raise_for_status()
        ep.resident = pin
        log.warning("[repin] %s 상주 복구 완료: %s", ep.name, pin)
        return True
    except Exception as e:
        log.error("[repin] %s 실패: %s: %s", ep.name, type(e).__name__, e)
        return False
