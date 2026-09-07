"""워커 **지휘자 모드** — SSH 파견의 실행 주체를 고른다 (`#385`, 사용자 요구 2026-09-08).

## 무엇을 고르는가

    lane     마스터에서 텍스트만 만들어 워커에 써 넣는다 (`lanes.run_chain`)
             → 워커에서 도는 에이전트가 **없다**
    claude   워커에서 `claude -p` 를 지휘자로 돌린다
    codex    워커에서 `codex exec` 를 지휘자로 돌린다

[중요] **지휘자와 하위 작성 모델은 다른 층이다.** 지휘자는 워커에서 돌며 체크아웃을 읽고
판단하고 `ax-work` 스킬을 따른다. 그 지휘자가 대량 생성을 `codex`→`agy`→로컬에 **위임하는
것**이 하위 층이고, 그쪽 순서는 `lanes.DEFAULT_LANES` 다. 둘을 같은 스위치로 묶지 않는다.

## [중요] 기본값은 **아직 정해지지 않았다** (사용자 2026-09-08)

*"기본값 lane 은 아직 제안이야. Claude/Codex 선택 기능을 요청했다는 사실과 별개로,
기본값까지 결정된 것은 아니야."*

그래서 `_UNDECIDED_DEFAULT` 는 **결정된 기본값이 아니라 「현재 동작 유지」**다. 지금 코드가
레인으로 돌고 있으므로 그 값을 유지해 **운영을 바꾸지 않는다.** 사람이 정하면 그때 이 상수의
이름과 값을 함께 바꾼다 — 이름이 `DEFAULT` 가 아닌 이유가 그것이다.

## 어디에 남는가

    ~/.cache/ax-dispatch/mode.json      재부팅을 넘는다 (`hold.json` 과 같은 자리)
    AX_WORKER_MODE                      환경변수 — 일회 실행·테스트용, 상태보다 **우선**
    인자                                호출부가 명시하면 그것이 **가장 우선**

[주의] `lanes.py:75` 가 약속만 하고 없던 `AX_LANES` 와 같은 실수를 반복하지 않는다 —
**여기 적힌 세 경로는 전부 아래 코드가 실제로 읽는다.** 약속만 적지 않는다.

## [주의] 이 모듈은 상태만 관리한다

서버의 조회·변경 표면(MCP 도구 한 벌)과 양쪽 스킬은 **이 함수들을 부른다.** 표면을 도구마다
따로 구현하지 않는다 — 한 벌을 두고 Claude 스킬·Codex 스킬이 같은 것을 호출한다
(사용자 정정 2026-09-08: *"MCP와 스킬은 양자택일이 아니야"*).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

#: 고를 수 있는 값. [중요] 이 밖의 값은 **거절한다** — 조용히 기본값으로 접지 않는다.
MODES = ("lane", "claude", "codex")

#: [중요] **결정된 기본값이 아니다** — 현재 동작(레인)을 유지하는 값이다. 위 머리말 참조.
_UNDECIDED_DEFAULT = "lane"

ENV = "AX_WORKER_MODE"
STATE_DIR = Path.home() / ".cache" / "ax-dispatch"
STATE = STATE_DIR / "mode.json"


class ModeError(ValueError):
    """모르는 모드. [주의] 사유를 실어 보낸다 — 이 저장소 관례(조용한 실패를 만들지 않는다)."""


def _check(m: str) -> str:
    m = (m or "").strip().lower()
    if m not in MODES:
        raise ModeError(f"모르는 지휘자 모드: {m!r} — 가능한 값 {list(MODES)}")
    return m


def read_state() -> dict:
    """저장된 것 그대로. 없거나 깨졌으면 `{}`. [주의] 깨진 파일을 **고치지 않는다** — 보고한다."""
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def current(explicit: str = "") -> tuple:
    """`(모드, 출처)`. 출처는 `arg` · `env` · `state` · `current-behaviour` 중 하나.

    [중요] **출처를 함께 돌려준다** — 「왜 이 모드로 돌았나」를 로그가 말할 수 있어야 한다.
    경로가 둘 이상이면 그것을 밝히지 않는 로그는 나중에 아무 도움이 안 된다.
    """
    if (explicit or "").strip():
        return _check(explicit), "arg"
    env = (os.environ.get(ENV) or "").strip()
    if env:
        return _check(env), "env"
    got = (read_state().get("mode") or "").strip()
    if got:
        return _check(got), "state"
    return _UNDECIDED_DEFAULT, "current-behaviour"


def set_mode(m: str, *, why: str = "", by: str = "") -> dict:
    """모드를 남긴다. **재부팅을 넘는다.** 저장한 내용을 돌려준다.

    [주의] 이것은 **기록이지 잠금이 아니다** — 명시 인자와 환경변수가 여전히 이긴다.
    """
    m = _check(m)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    d = {"mode": m, "at": datetime.now().astimezone().isoformat(timespec="seconds"),
         "why": (why or "").strip(), "by": (by or "").strip()}
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return d


def clear() -> bool:
    """저장된 모드를 지운다(현재 동작으로 되돌린다). 지웠으면 `True`."""
    try:
        STATE.unlink()
        return True
    except OSError:
        return False


def describe(explicit: str = "") -> str:
    """사람이 읽을 한 줄 — 조회 표면이 그대로 쓴다."""
    m, src = current(explicit)
    d = read_state()
    tail = ""
    if src == "state" and d:
        tail = f" (기록 {d.get('at', '')}{' · ' + d['why'] if d.get('why') else ''})"
    if src == "current-behaviour":
        tail = " (기본값 미결정 — 현재 동작 유지)"
    return f"지휘자 모드 = {m} · 출처 {src}{tail}"
