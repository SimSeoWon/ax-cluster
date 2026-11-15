"""생성 체인(`commercial_chat`)의 **파일 쿨다운** — `#964` T1.

사용자 결정(2026-11-15, #964 스펙 영역): 한도에 걸린 백엔드를 매 항목·매 회차 먼저 두드리지 않는다. 메모리 쿨다운
(`layer2_verify._cooldown`)은 프로세스가 끝나면 사라지는데 `ax-batch` 는 매시간 **새 프로세스**라 소용이 없었다 —
그래서 「언제까지 건너뛴다」 시각을 **파일에 기록하고 호출 전에 지금과 비교**한다(사용자: 「마지막 마킹된 시간으로
지금 시간을 비교하는게 더 안전하겠네」).

    한도·쿼터 실패(사유에 limit·quota·429·usage)   1시간
    그 밖의 실패                                   600초
    성공                                          쿨다운 해제

- 기계 하나에 파일 하나다(`~/.cache/ax-llm/cooldown.json`, `AX_LLM_COOLDOWN_FILE` 로 바꾼다) — 쿼터는 기계 전체에
  걸리고 `ax-batch`·`ax-review-queue`·`ax-projects` 가 같은 체인을 쓴다.
- 쓰기는 잠금(`fcntl`) 아래 임시 파일 → 교체로 한다. 파일이 깨졌으면 빈 상태로 읽는다(쿨다운이 없을 뿐 막지 않는다).
- [중요] **쿨다운은 순서를 바꾸지 않는다** — 순서는 `layer2_verify.WHY_BACKENDS`(agy → codex → claude, `#966`)가
  정하고, 여기서는 쿨다운 중인 것만 건너뛴다.
- 걸고 풀 때 `[cooldown]` 로그 줄을 남긴다(stderr — 배치는 저널로 간다).
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

QUOTA_SEC = 3600
OTHER_SEC = 600
LIMIT_RE = re.compile(r"limit|quota|429|usage", re.I)


def default_path() -> Path:
    env = os.environ.get("AX_LLM_COOLDOWN_FILE")
    return Path(env) if env else Path.home() / ".cache" / "ax-llm" / "cooldown.json"


def _log(msg: str) -> None:
    print(f"[cooldown] {msg}", file=sys.stderr, flush=True)


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(path.suffix + ".lock"), "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def classify(why: str) -> tuple[str, int]:
    """실패 사유 → (종류, 초). 한도·쿼터 표지가 있으면 1시간."""
    return ("quota", QUOTA_SEC) if LIMIT_RE.search(why or "") else ("other", OTHER_SEC)


def remaining(name: str, *, path: Path | None = None, now: float | None = None) -> float:
    """남은 초(0 이면 부를 수 있다)."""
    path = Path(path) if path else default_path()
    now = time.time() if now is None else now
    entry = _read(path).get(name) or {}
    try:
        return max(0.0, float(entry.get("until", 0)) - now)
    except (TypeError, ValueError):
        return 0.0


def mark(name: str, why: str, *, path: Path | None = None, now: float | None = None) -> dict:
    """실패를 기록하고 쿨다운을 건다. 기록한 항목을 돌려준다."""
    path = Path(path) if path else default_path()
    now = time.time() if now is None else now
    kind, sec = classify(why)
    entry = {"until": now + sec, "kind": kind, "seconds": sec, "at": now, "why": (why or "")[:300]}
    with _locked(path):
        data = _read(path)
        data[name] = entry
        _write(path, data)
    _log(f"{name} 쿨다운 {sec}초({kind}) — {(why or '사유 미기록')[:120]}")
    return entry


def clear(name: str, *, path: Path | None = None) -> bool:
    """성공했으면 쿨다운을 푼다. 걸려 있던 게 있었으면 True."""
    path = Path(path) if path else default_path()
    if name not in _read(path):            # 걸린 게 없으면 잠금·파일을 만들지 않는다(성공 경로의 흔한 경우)
        return False
    with _locked(path):
        data = _read(path)
        if name not in data:
            return False
        data.pop(name)
        _write(path, data)
    _log(f"{name} 쿨다운 해제 — 응답을 받았다")
    return True


def state(*, path: Path | None = None, now: float | None = None) -> dict:
    """관측용 `{백엔드: {남은 초, 종류, 사유}}` — 만료된 것은 뺀다."""
    path = Path(path) if path else default_path()
    now = time.time() if now is None else now
    out = {}
    for name, e in _read(path).items():
        left = float(e.get("until", 0)) - now if isinstance(e, dict) else 0
        if left > 0:
            out[name] = {"remaining": round(left, 1), "kind": e.get("kind"), "why": e.get("why")}
    return out
