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
SYNTH = "gemma4:e4b"
DRIVER = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"

# [중요] 35B 상주 해제 (#105 판정, 사용자 결정 ⓐ 2026-08-17). 실측이 배치를 뒤집었다:
#   통상 순차 추론(num_ctx 8192)만으로 사이클당 ~120MB GPU(GTT) 할당이 자라 4분/11사이클에
#   가용 47MB 붕괴 — 유휴에도 반납 없음, ollama 재시작으로만 회복 (리포트 19 §8). 8/15 OOM
#   은 배치 탓이 아니라 이 구조였다. 35B 는 층2 벤치에서도 오탐 2로 탈락했던 모델이다.
# 새 배치:
#   BC-250  = 합성 모델(e4b, ~5GB — 여유 ~10GB) 상주. [중요] e4b 가 폴백으로 35B 옆에
#             실리던 것이 옛 OOM 위험이었는데, 이제 e4b 가 정식 상주라 그 위험도 소멸
#   RTX3060 = 코더 14b (그대로)
#   35B(DRIVER) = **핀 없음.** 에이전틱 드라이버 자리는 공석 — M6 #106(tool-calling 모델
#             확보)이 그 자리의 후속이다. 상수는 라우팅 회귀 방지를 위해 남긴다
_DEFAULT = [
    {"name": "bc250",   "host": "192.168.0.43:11434", "prefer": [SYNTH], "pin": SYNTH},
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
