"""생산자② code-writer 신호 적재 (#206) — 원전 `mcp/code_recipes/server.py:120` 이식.

[중요] 저장하는 것은 코드가 아니라 **작업이 진행된 과정**이다: 무엇을 하려 했고(intent),
트윈에서 무엇을 찾아 읽었고(queries/files_read), 무엇을 고쳤고(files_modified), 몇 라운드의
피드백을 돌았고(iterations), 무엇이 거절됐고(rejected_approaches), 어떤 에러를 어떻게
복구했나(error_recoveries). 원전에서 code-writer 에이전트가 작업 종료 직전에 이 레코드를
`.claude/recipes/_signals.jsonl` 에 한 줄 append 하고, 소비자(recipes_synthesizer, `#157`)가
유휴 시간에 LLM 으로 클러스터링해 **레시피(작업 절차서) + 안티패턴 카탈로그**로 합성한다.
다음 작업이 시작할 때 find_recipes 로 그 절차서를 받는다 — 경험이 트윈으로 돌아오는 루프다.

우리 적재 지점 둘 (둘 다 트윈을 먼저 받고 작업하는 경로다):
    파이프라인   통합자가 게이트 통과분을 커밋할 때 자동 적재 — intent 는 큐의 task 제목
    요청자(.33)  클라 MCP `log_writer_signal` → 8101 `POST /api/v1/signals` (requester 스코프,
                redmine/note 와 같은 마스터 대행 자리 — 8103 `/api/v1` 은 공개 읽기 표면이라 안 된다)

[중요] 게이트 **불합격은 여기 안 온다** — 실패 카탈로그(소 2.3.4, `work/failures.py`)가 이미
받아서 다음 골조 프롬프트에 싣는다. 원전의 error_recoveries 는 「복구된」 에러(증상+해결
쌍)다 — 파이프라인엔 그 대응물이 아직 없어 비워 두고, 요청자 경로만 사람이 채운다.

[중요] 한국어 서술 속 코드 식별자는 [대괄호]로 감싼다 (원전 규약) — 합성 단계의 영문 번역에서
식별자가 뭉개지는 것을 막는다. 예: "미션 매니저[Manager_Mission]에 태스크 추가".

스키마는 원전 그대로 + `source`("pipeline"|"requester") 한 필드만 추가 — 소비자는 .get 으로
읽으므로(원전 `_read_signals` 는 필드 무검사 JSONL) 추가 필드는 계약을 깨지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RECIPES_DIRNAME = "recipes"
SIGNALS_FILENAME = "_signals.jsonl"


def signals_path(paths) -> Path:
    return Path(paths.root) / RECIPES_DIRNAME / SIGNALS_FILENAME


def make_record(*, intent: str, queries=(), files_read=(), files_modified=(),
                iterations: int = 1, feedback_notes: str = "",
                rejected_approaches=(), error_recoveries=(),
                session_id: str = "", work_id: str = "", source: str = "") -> dict:
    """원전 레코드 스키마 글자대로. intent 없으면 ValueError — 신호의 축이다."""
    if not (intent or "").strip():
        raise ValueError("intent 는 필수다")
    try:
        iterations_int = max(1, int(iterations))
    except (ValueError, TypeError):
        iterations_int = 1
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "intent": intent.strip(),
        "queries": list(queries or []),
        "files_read": list(files_read or []),
        "files_modified": list(files_modified or []),
        "iterations": iterations_int,
        "feedback_notes": (feedback_notes or "").strip(),
        "rejected_approaches": list(rejected_approaches or []),
        "error_recoveries": list(error_recoveries or []),
    }
    # 원전 규약: 선택 필드는 값이 있을 때만 싣는다
    if (session_id or "").strip():
        record["session_id"] = session_id.strip()
    if (work_id or "").strip():
        record["work_id"] = work_id.strip()
    if (source or "").strip():
        record["source"] = source.strip()
    return record


def append_signal(paths, record: dict) -> str:
    """JSONL 한 줄 append. 반환은 저장 경로 — 호출자가 로그에 남긴다."""
    p = signals_path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(p)


def read_signals(paths) -> list:
    """소비자(원전 `_read_signals`)와 같은 눈: JSONL, 깨진 줄은 건너뛴다."""
    p = signals_path(paths)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
