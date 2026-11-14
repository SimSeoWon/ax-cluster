"""CLI가 관측한 구독 한도 (#368). 사용 토큰으로 잔여율을 추정하지 않는다.

Claude는 stream-json 이벤트, Codex는 해당 세션의 rollout JSONL만 읽는다.
인증 파일·네트워크에는 접근하지 않으며 수집 불가는 빈 windows와 사유로 돌려준다.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path

TAIL_BYTES = 1024 * 1024
META_BYTES = 256 * 1024
_SESSION = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def unknown(source: str, reason: str) -> dict:
    return {"source": source, "observed_at": None, "windows": {}, "reason": reason}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def _window(used, reset, *, scale: float) -> dict | None:
    amount, epoch = _number(used), _number(reset)
    if amount is None or not 0 <= amount <= scale or epoch is None or epoch <= 0:
        return None
    return {"remaining_pct": round(100 - amount * 100 / scale, 6), "resets_at": epoch}


def claude_snapshot(event: dict, *, now=None) -> dict:
    snapshot = unknown("claude", "한도 이벤트의 유효한 창이 없다")
    info = event.get("rate_limit_info") if isinstance(event, dict) else None
    windows = info.get("unifiedWindows") if isinstance(info, dict) else None
    if not isinstance(windows, dict):
        return snapshot
    for key in ("five_hour", "seven_day"):
        raw = windows.get(key)
        value = _window(raw.get("utilization"), raw.get("resetsAt"), scale=1) if isinstance(raw, dict) else None
        if value is not None:
            snapshot["windows"][key] = value
    if snapshot["windows"]:
        observed = _number(time.time() if now is None else now)
        if observed is None or observed <= 0:
            return unknown("claude", "관측 시각이 유효하지 않다")
        snapshot.update(observed_at=observed, reason="")
    return snapshot


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def _read_codex(path: Path, session: str) -> dict:
    with path.open("rb") as stream:
        first = stream.readline(META_BYTES + 1)
        if len(first) > META_BYTES or not first.endswith(b"\n"):
            return unknown("codex", "세션 메타데이터가 없거나 너무 크다")
        meta = json.loads(first)
        payload = meta.get("payload") if isinstance(meta, dict) else None
        if (not isinstance(meta, dict) or meta.get("type") != "session_meta"
                or not isinstance(payload, dict)
                or (payload.get("id") or payload.get("session_id")) != session):
            return unknown("codex", "rollout 세션 ID가 일치하지 않는다")
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        start = max(0, size - TAIL_BYTES)
        stream.seek(start)
        tail = stream.read(TAIL_BYTES)
    lines = tail.split(b"\n")
    if start:
        lines = lines[1:]                 # tail 시작이 줄 중간일 수 있다
    lines = lines[:-1]                    # 쓰기 중인 마지막 부분 줄은 읽지 않는다
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        if (not isinstance(event, dict) or event.get("type") != "event_msg"
                or not isinstance(payload, dict) or payload.get("type") != "token_count"):
            continue
        snapshot = unknown("codex", "마지막 token_count의 한도가 미확인이다")
        limits = payload.get("rate_limits")
        observed = _timestamp(event.get("timestamp"))
        if not isinstance(limits, dict) or observed is None or observed <= 0:
            return snapshot
        if limits.get("limit_id") not in (None, "codex"):
            return unknown("codex", "다른 한도 그룹의 이벤트다")
        for slot in ("primary", "secondary"):
            raw = limits.get(slot)
            if not isinstance(raw, dict):
                continue
            key = {300: "five_hour", 10080: "seven_day"}.get(raw.get("window_minutes"))
            value = _window(raw.get("used_percent"), raw.get("resets_at"), scale=100)
            if key and value is not None:
                snapshot["windows"][key] = value
        if snapshot["windows"]:
            snapshot.update(observed_at=observed, reason="")
        return snapshot
    return unknown("codex", "최근 rollout 구간에 token_count가 없다")


def codex_snapshot(session: str, *, codex_home=None) -> dict:
    """정확한 세션의 메타데이터와 최대 1MiB tail을 읽는다. 실패는 대화 실패가 아니다."""
    if not isinstance(session, str) or not _SESSION.fullmatch(session):
        return unknown("codex", "세션 ID가 없거나 UUID 형식이 아니다")
    root = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    try:
        paths = list(root.glob(f"sessions/*/*/*/rollout-*-{session}.jsonl"))
        if len(paths) != 1:
            return unknown("codex", "해당 세션 rollout이 없거나 여러 개다")
        return _read_codex(paths[0], session)
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        return unknown("codex", f"rollout 수집 불가 ({type(error).__name__})")
