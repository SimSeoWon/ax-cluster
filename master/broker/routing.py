"""마스터 브로커의 라우팅 결정 — PLAN §4 (오케스트레이터는 여럿, 브로커는 하나).

작업자(윈도우 gjc·하네스)는 추론 노드를 **직접 부르지 않는다.** 마스터가 요청을 받아
모델별로 엔드포인트를 고르고, 죽어 있으면 폴백한다. 이 파일은 그 **결정 로직만** 담는다
(HTTP 는 `server.py`) — 결정이 순수 함수라야 노드 없이 테스트할 수 있기 때문이다.

[중요] 전제 (2026-08-08 실측): **엔드포인트마다 상주 모델이 다르다.**
`MAX_LOADED_MODELS=1` 이라 한 엔드포인트에서 모델을 바꾸면 재적재가 붙는다
(BC-250 37.9s / 3060 8.8~45s). 라우팅의 존재 이유가 **이 재적재를 피하는 것**이므로,
"아무 데나 되는 곳"이 아니라 **그 모델이 이미 상주한 곳**을 1순위로 고른다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Endpoint:
    """추론 엔드포인트 하나. `models` 는 헬스체크가 채우는 실측 보유 목록."""
    name: str
    host: str                      # "192.168.0.43:11434"
    prefer: list[str] = field(default_factory=list)   # 이 노드가 상주시키기로 한 모델
    models: list[str] = field(default_factory=list)   # /api/tags 실측 (헬스체크가 갱신)
    resident: Optional[str] = None  # /api/ps 실측 — 지금 VRAM 에 올라와 있는 모델
    healthy: bool = False
    last_error: str = ""
    # [중요] **「상주 없음」과 「상주를 못 읽었다」는 다르다.** `/api/ps` 가 실패해도 `resident` 는
    # `None` 이 되는데, 그 값을 *"모델이 안 올라와 있다"* 로 읽으면 재적재를 부른다 —
    # 힘들어하는 노드에 **가장 비싼 일**(35B 적재)을 시키는 경로다(2026-08-15 실측: 그 직후
    # 보드가 멈췄다). 규약은 이미 있다 — *"판정 불가는 언제나 보존"*(리포트 16 §10).
    resident_known: bool = True


def _has_model(ep: Endpoint, model: str) -> bool:
    """모델 보유 여부. Ollama 는 `name` 과 `name:latest` 를 같게 취급하므로 맞춰준다."""
    if not model:
        return False
    want = {model, model + ":latest"}
    if model.endswith(":latest"):
        want.add(model[: -len(":latest")])
    return bool(want & set(ep.models))


def choose(endpoints: list[Endpoint], model: str,
           inflight: Optional[dict] = None, cap: int = 0) -> tuple[Optional[Endpoint], str]:
    """모델을 처리할 엔드포인트 선택. (선택, 사유) 반환. 없으면 (None, 사유).

    우선순위 — 재적재 비용을 피하는 순서다:
      1. 건강 + 보유 + **이미 상주 중**       → 적재 0초
         🔴 그런 노드가 **여럿이면 처리 중 요청(`inflight`)이 적은 쪽** (`#715`). 설계 규칙
         *"모델은 보드에 쪼개지 않고 마스터가 요청을 나눈다"* 의 이행이다 — 종전엔 목록의 첫
         노드만 골라, 같은 모델이 둘에 상주해도 한쪽만 일했다. 같으면 목록 순서(종전과 같다)
      2. 건강 + 보유 + `prefer` 에 지정됨     → 설계상 그 모델의 집
      3. 건강 + 보유                          → 폴백 (재적재를 물지만 응답은 된다)

    🔴 `cap` (`#853`) — 노드별 동시 요청 상한(0 = 무제한, 종전 동작). 노드의 실효
    `OLLAMA_NUM_PARALLEL` 은 이미 1 이라 넘친 요청은 노드 대기열(512)에 쌓여 브로커 읽기
    타임아웃(900초)까지 기다리다 죽었다(09-19 `.2` inflight=4). 상한에 찬 노드는 건너뛰고,
    후보가 전부 차면 **즉시 (None, "포화 …")** — 호출자가 503 으로 바로 안다.
    [중요] 상주 노드가 전부 포화여도 **다른 노드 재적재로 흘리지 않는다** — 부하 중인 클러스터에
    가장 비싼 일(적재)을 얹는 경로다(2026-08-15 보드 정지 · `#105`).
    """
    alive = [e for e in endpoints if e.healthy]
    if not alive:
        return None, "건강한 엔드포인트가 없다"
    owners = [e for e in alive if _has_model(e, model)]
    if not owners:
        return None, f"'{model}' 을 가진 건강한 엔드포인트가 없다"

    load = inflight or {}

    def _full(x: Endpoint) -> bool:
        return cap > 0 and load.get(x.name, 0) >= cap

    hot = [e for e in owners
           if e.resident and _has_model(Endpoint(e.name, e.host, models=[e.resident]), model)]
    if hot:
        free = [e for e in hot if not _full(e)]
        if not free:
            return None, (f"포화 — '{model}' 상주 노드 {len(hot)}곳이 모두 처리 중 상한 {cap}건이다 "
                          f"(재적재로 흘리지 않는다 · #853)")
        e = min(free, key=lambda x: load.get(x.name, 0))    # min 은 같으면 앞의 것 — 목록 순서
        return e, (f"{e.name}: 이미 상주 중 (적재 0)"
                   + (f" · 처리 중 {load.get(e.name, 0)} (상주 {len(hot)}곳 중 최소)"
                      if len(hot) > 1 else ""))
    room = [e for e in owners if not _full(e)]
    if not room:
        return None, (f"포화 — '{model}' 을 가진 노드 {len(owners)}곳이 모두 처리 중 상한 {cap}건이다 (#853)")
    for e in room:
        if model in e.prefer:
            return e, f"{e.name}: prefer 지정 (재적재 필요)"
    e = room[0]
    return e, f"{e.name}: 폴백 — prefer 노드가 죽었거나 미지정 (재적재 필요)"


def union_tags(endpoints: list[Endpoint]) -> list[str]:
    """건강한 엔드포인트들의 모델 합집합. `/api/tags` 응답용 —
    작업자에게는 클러스터가 **하나의 Ollama** 로 보여야 한다."""
    out: set[str] = set()
    for e in endpoints:
        if e.healthy:
            out.update(e.models)
    return sorted(out)
