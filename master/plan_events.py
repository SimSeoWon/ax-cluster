"""플랜 **거절 기록** — `#864` T1.

`plan_tools.transition`·`set_plan` 이 규칙 위반으로 거절한 시도를 한 줄씩 남긴다. Redmine 노트는
**성공한** 전이만 남기므로(거절은 쓰기 전에 끝난다), 「규칙이 몇 번·무엇을 막았나」는 여기서만
보인다. `plan_metrics` 가 읽는다.

    <AXCluster 트윈>/plan_events.jsonl      한 줄 = 거절 하나 (schema_version 1)

[중요] **기록 위치는 마운트와 무관하게 AXCluster 트윈이다** — 플랜 도구는 AX 인프라 일감을 마킹하고,
마운트가 게임 프로젝트로 바뀌어도 같은 파일에 쌓여야 이슈별 집계가 끊기지 않는다. 경로는
레지스트리(`AX_PROJECTS_ROOT`)로 풀고 하드코딩하지 않는다. 테스트는 `path` 로 주입한다.
[중요] **기록 실패는 거절을 바꾸지 않는다** — `record` 는 예외를 삼키고 stderr 에 경고만 낸다.
[주의] **규칙 거절만 적는다.** Redmine 읽기·쓰기 실패(전송 실패)는 규칙이 막은 것이 아니므로
여기 없다 — `plan_tools.PlanTransportError` 가 그 구분이다.
"""
from __future__ import annotations

import fcntl
import json
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
PROJECT = "AXCluster"
FILE_NAME = "plan_events.jsonl"
LOCK_NAME = ".plan-events.lock"

# 같은 프로세스 안 동시 append 는 이 락, CLI·서비스 사이는 형제 락 파일의 flock (search_log 와 같은 방식).
_lock = threading.Lock()

# 사유 문장 → 종류. 문장은 plan_state·plan_tools·plan_block 의 것이다 — 바뀌면 `other` 로 떨어진다
# (기록은 남고 종류만 잃는다). 순서가 의미다: 앞의 것이 먼저 잡힌다.
KINDS = (
    ("no_plan", re.compile(r"플랜 영역이 없다")),
    ("unknown_task", re.compile(r"^없는 태스크")),
    ("unknown_state", re.compile(r"모르는 상태")),
    ("disallowed_transition", re.compile(r"는 허용되지 않는다")),
    ("missing_note", re.compile(r"에는 .+가 필요하다")),
    ("unsettled_deps", re.compile(r"선행 태스크가 끝나지 않았다")),
    ("set_state_or_evidence", re.compile(r"set_plan 으로 못 바꾼다")),
    ("set_started_removed", re.compile(r"시작된 태스크는 목록에서 뺄 수 없다")),
    ("set_violations", re.compile(r"규칙 위반이 생긴다")),
    ("missing_why", re.compile(r"why 가 비었다")),
    ("invalid_input", re.compile(r"tasks 가 비었다|객체가 아니다|id·goal 은 필수다")),
)


def classify(reason: str) -> str:
    for kind, rx in KINDS:
        if rx.search(reason or ""):
            return kind
    return "format" if reason else "other"


def default_path(*, registry=None) -> Path:
    """레지스트리에서 AXCluster 트윈을 찾아 그 아래 `plan_events.jsonl`. 마운트는 보지 않는다."""
    from master.projects.config import ConfigError, Registry
    reg = registry or Registry.load()
    if PROJECT not in reg.names:
        raise ConfigError(f"{PROJECT} 가 등록되지 않았다 — 거절 기록 위치를 정할 수 없다")
    return reg.dir_of(PROJECT) / FILE_NAME


def build(op: str, issue_id, error: BaseException, *, task_id: str = "", from_state: str = "",
          to: str = "", note: str = "", caller: str = "", tasks=None, now=None) -> dict:
    note = (note or "").strip()
    reason = str(error)
    entry = {
        "schema_version": SCHEMA_VERSION,
        "ts": (now or datetime.now().astimezone()).isoformat(),
        "op": op, "issue_id": int(issue_id) if str(issue_id).isdigit() else issue_id,
        "task_id": task_id or "", "from": from_state or "", "to": to or "",
        "error_type": type(error).__name__, "kind": classify(reason), "reason": reason,
        "note_present": bool(note), "note_len": len(note),
    }
    if tasks is not None:
        entry["tasks"] = list(tasks)
    if caller:
        entry["caller"] = caller
    return entry


def append(entry: dict, path: Path) -> None:
    """한 줄 append. 실패는 예외로 올린다 — 삼키는 것은 `record` 의 몫이다."""
    line = json.dumps(entry, ensure_ascii=False)
    p = Path(path)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        with (p.parent / LOCK_NAME).open("a") as lockfile:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
            with p.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")


def record(op: str, issue_id, error: BaseException, *, path=None, **fields) -> bool:
    """거절 하나를 남긴다. 어떤 실패도 올리지 않는다 — 돌려준 bool 이 기록 여부다."""
    try:
        target = Path(path) if path is not None else default_path()
        append(build(op, issue_id, error, **fields), target)
        return True
    except Exception as exc:                              # noqa: BLE001 — 기록이 거절을 바꾸면 안 된다
        print(f"[plan_events] 거절 기록 실패(거절 자체는 그대로): {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return False


def read(path=None, *, issue_id=None) -> list[dict]:
    """기록 전부(또는 한 이슈). 파일이 없으면 빈 목록, 깨진 줄은 건너뛴다."""
    p = Path(path) if path is not None else default_path()
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if issue_id is None or str(entry.get("issue_id")) == str(issue_id):
            out.append(entry)
    return out
