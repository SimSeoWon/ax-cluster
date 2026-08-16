"""영구 유실 카나리 — 원전 `permanent_loss_canary.jsonl` 이식 (소 3.5.6 · `#182`).

[주의] **이 함수는 `events/consumer.py` 에 있었다.** 옮긴 이유는 층이다 — `context_search/rebuild`
가 카나리를 찍어야 하는데, `context_search` 가 `events` 를 부르면 **층 역전**이다. 기존 이름
(`from master.events.consumer import append_canary`)은 그대로 살아 있다(재수출).

## [중요] 승격 기준 — 원전이 except ~33개 중 딱 2개만 카나리로 올렸다

    *"skip 후 워터마크가 전진하느냐."*

    전진하지 않는 실패   다음 회차에 self-heal 된다 → **카나리 아님** (원전: *"self-heal 되는
                        걸 카나리로 만들면 노이즈"*)
    전진하는 실패        그 문서는 **영원히** 색인에 없다 → 카나리

[주의] **「전진하지 않는다」를 코드 한 줄로 판단하지 말 것.** 실측 2026-08-16(`#182` 이식):
우리 재색인 실패는 `return` 이라 워터마크 전에 빠져 self-heal 되지만, **도메인 색인 실패는
note 로 삼켜져** 정상 반환한다. 그리고 재색인 자체가 *"컨텍스트 MD 가 바뀔 때만"* 돌기 때문에

    푸시 A  MD 변경 → 재색인 → 벡터 OK · 도메인 색인 실패(삼킴) → digest·워터마크 전진
    푸시 B  소스만 변경 → "MD 변화 없음" 으로 재색인 **건너뜀** → 깨진 채 유지

[중요] 즉 **다음 회차가 오지 않으면 self-heal 도 오지 않는다.** 리포트 17 §12 의 *"트윈은 자랐는데
검색 색인은 닷새 전 것"* 이 같은 부류다.

## 지금 승격된 자리 (원전도 둘이었다)

    context-md-lost    컨텍스트 MD 합성이 그룹을 잃었다      `events/consumer.py`
    domain-index-gap   도메인(온톨로지) 색인이 실패했는데    `context_search/rebuild.py`
                       재색인은 성공으로 끝났다
"""
from __future__ import annotations

import json

# [중요] 원전 kind 식별자와 같은 뜻으로 쓴다 — 원전은 `context-md-lost` / `vector-index-gap` 이고,
#    우리 두 번째 자리는 **도메인 색인**이라 이름만 그 실체에 맞춘다(기제는 같다).
KIND_CONTEXT_MD_LOST = "context-md-lost"
KIND_DOMAIN_INDEX_GAP = "domain-index-gap"


def append_canary(paths, *, kind: str, detail: str, commit: str = "") -> bool:
    """[중요] **영구 유실을 누적 기록한다.**

    저널에 한 줄 찍는 것만으로는 원전이 남긴 지침 *"카나리가 **반복**되면 근본 원인(LLM 쿼터·
    타임아웃 등)을 먼저 해결할 것 — 재touch/rebuild 는 증상 복구일 뿐"* 을 따를 수 없다.
    **반복은 누적된 것을 봐야 보인다.**

    [주의] **기록에 실패해도 예외를 올리지 않는다** — 카나리를 쓰다 색인을 죽이면 본말전도다.
    대신 `False` 를 돌려주므로 호출자가 그 사실을 셀 수 있다.
    """
    from datetime import datetime, timezone
    try:
        p = paths.canary
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "kind": kind, "detail": detail[:500], "commit": commit}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False
