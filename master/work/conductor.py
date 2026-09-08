"""마스터 담당 기록과 워커 모드 조회. 담당 기록은 프로세스 생존 판정이나 잠금이 아니다."""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from . import mode

STATE = Path.home() / ".cache/ax-dispatch/conductor.json"

def master_record():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("agent") not in ("claude", "codex"):
            raise ValueError("담당 기록 형식 오류")
        return data
    except FileNotFoundError:
        return {"agent": "unknown", "note": "담당 기록 없음"}
    except (OSError, ValueError) as exc:
        return {"agent": "unknown", "note": str(exc)}

def record_master(agent, why, by=""):
    if agent not in ("claude", "codex"):
        raise ValueError("마스터 담당은 claude 또는 codex")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("담당 기록 사유가 필요하다")
    if not isinstance(by, str):
        raise ValueError("기록자는 문자열이어야 한다")
    data = {"agent": agent, "why": why.strip(), "by": by.strip(),
            "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".conductor-", dir=STATE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False)
            out.write("\n")
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return {"ok": True, "master": data}

def snapshot():
    selected, source = mode.current()
    return {"ok": True, "master": master_record(),
            "worker": {"mode": selected, "source": source, "state": mode.read_state()},
            "note": "마스터는 마지막 담당 기록이며 실행 중임을 보증하지 않는다"}

def set_worker(selected, why, by=""):
    if not isinstance(selected, str) or not isinstance(by, str):
        raise ValueError("모드와 기록자는 문자열이어야 한다")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("워커 모드 변경 사유가 필요하다")
    saved = mode.set_mode(selected, why=why, by=by)
    return {**snapshot(), "saved": saved}
