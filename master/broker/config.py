"""브로커 엔드포인트 설정 — PLAN §9.4.2.

기본값은 **2026-08-08 실측으로 확정된 배치**다. `AX_BROKER_CONFIG` 로 JSON 파일을
가리키면 그걸 쓴다 — task_queue 이식 때 배운 대로 **경로 역산이 아니라 명시 설정**이다.

`pin` = 이 엔드포인트가 **상주시켜야 할 모델**. 헬스루프가 이걸 재확립한다.
BC-250 유닛은 아직 `KEEP_ALIVE=30m` 이고 3060 의 `-1` 도 Ollama 재시작이면 풀리므로,
**상주 유지의 책임은 브로커에 있다** (재부팅에도 자동 복구되는 쪽이 낫다는 판단).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .routing import Endpoint

CODER = "qwen2.5-coder:14b"
DRIVER = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"

# 실측 확정 배치 (PLAN §9.4.2):
#   BC-250  = 35B 를 담을 수 있는 유일한 기계 (통합 ~15.6 GiB) → 에이전틱 드라이버
#   RTX3060 = 14b 를 BC-250 보다 23% 빠르게 (31.1 vs 25.2 t/s)  → 코드 본문 생성기
_DEFAULT = [
    {"name": "bc250",   "host": "192.168.0.43:11434", "prefer": [DRIVER], "pin": DRIVER},
    {"name": "rtx3060", "host": "192.168.0.2:11434",  "prefer": [CODER],  "pin": CODER},
]


# [중요] `num_ctx` 가 요청마다 다르면 Ollama 가 **모델을 통째로 다시 올린다** (2026-08-08 실측:
# 같은 35B 인데 num_ctx 만 바꿨더니 61.6s 재적재). 호출자가 지정하지 않으면 이 값을 넣어
# 사고를 막는다. 8192 인 이유는 리포트 06 §5.3 — 35B 는 32768 에서 9분 59초 후 HTTP 500 이
# 나고 8192 는 정상이다. 3060 도 여유가 257 MiB 뿐이라 8192 가 상한이다.
DEFAULT_NUM_CTX = int(os.environ.get("AX_BROKER_NUM_CTX", "8192"))


def load_endpoints() -> tuple[list[Endpoint], dict[str, str]]:
    """(엔드포인트 목록, {name: pin 모델}) 반환."""
    raw = _DEFAULT
    cfg = os.environ.get("AX_BROKER_CONFIG", "").strip()
    if cfg:
        p = Path(cfg)
        if not p.is_file():
            # [중요] 폴백 없이 실패 — 설정을 가리켰는데 없으면 조용히 기본값으로 도는 게 더 나쁘다.
            raise SystemExit(f"AX_BROKER_CONFIG 가 가리키는 파일이 없다: {p}")
        raw = json.loads(p.read_text(encoding="utf-8"))
    eps = [Endpoint(name=e["name"], host=e["host"], prefer=list(e.get("prefer") or []))
           for e in raw]
    pins = {e["name"]: e["pin"] for e in raw if e.get("pin")}
    return eps, pins
