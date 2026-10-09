"""LLM 모델별 기간별 작업·토큰 대시보드 집계 골조.

[DOC] 사용자: 레드마인 일감별 Claude/Codex/Gemini/로컬 LLM 작업과 토큰을
일간·주간·월간으로 보는 신규 웹페이지. 비용·대화 본문은 출력하지 않는다.

동결 인터페이스: build_report의 이름·인자·기본값·반환 표기와 아래 JSON 계약.
UI 조각 master/webui/usage_page.py, 라우트 조각 master/webui/app.py가 소비한다.
공개 함수 변경 금지. 비공개 보조 함수는 추가 가능. 불필요한 lambda 대신 이름 있는 함수.

입력/집계 계약:
- period=daily|weekly|monthly. Asia/Seoul 달력 기준, 주 시작 월요일, 월 시작 1일.
  ISO/UTC 시각은 KST로 변환. usage_log의 naive 시각은 기존 마스터 KST로 해석.
- start/end=YYYY-MM-DD, 양끝 포함. 기본 최근 30일, 최대 366일. 역전·잘못된 값은
  ValueError. now 주입으로 날짜를 결정적으로 검사한다.
- family=""|claude|codex|gemini|local|unknown. 실제 model/lane/tool로 분류한다.
  lane=agy(Antigravity)는 model이 있으면 그 이름으로(gemini-* → gemini) 분류하고, 없으면
  gemini로 분류하며 model 표기는 'Antigravity(모델 미상)'이다. 사용자는 이 레인을 일관되게
  "제미나이(안티그래비티)"라고 부르고(2026-10-04), agy JSON에는 모델 키가 없어(실측
  2026-10-04) 'agy=unknown'이면 실사용이 대시보드에서 사라진다(#728). 그 밖에 model이
  없으면 '모델 미상'.
- source=dispatch|session|all. 두 소스는 서로 겹친다 — 워커의 `codex exec`·`claude -p` 파견은
  usage_log 에도, 그 기계의 세션 jsonl 에도 남는다(실측 2026-10-04: 16:55 파견 4건이 워커 세션
  파일로도 잡혔다). 그래서 단순 합산은 하지 않는다. [중요] **all 은 계열별로 출처 하나만 쓴다**
  (사용자 결정 2026-10-04): claude·codex 는 session, 그 밖의 계열(gemini·local·unknown)은
  dispatch. all 은 일감 귀속이 반쪽(claude·codex 가 빠진다)이므로 issues=[] 이다.
- dispatch: 등록 프로젝트별 usage_log.jsonl, work_id로 큐 _request.md의 project,
  title, redmine_issue_id와 연결. 활성·보관 일감 모두 고려. 연결 실패는 unlinked_calls.
- session: 기존 session_usage.DEFAULT_STORE 숫자 스냅샷만 읽는다. SSH/수집 실행 금지.
  일감 귀속이 없으므로 issues=[]. 스냅샷의 project(세션 cwd 가 등록 작업장 체크아웃 아래일 때만,
  2026-10-04 원본 복사와 함께)로 project 필터를 적용한다 — project 없는 스냅샷은 전체 보기에만 든다.
- projects_root/queue_root/session_store는 서버·검사 주입 전용. 웹 쿼리로 경로를 받지 않는다.
  기본 Registry/AX_TASK_QUEUE_ROOT(또는 ~/ax-state)/DEFAULT_STORE를 사용한다.
- 등록되지 않은 project, 잘못된 period/family/source는 ValueError. project=""는 전체.
- measured=False는 미계측이며 토큰 0으로 표현하지 않는다. tokens는 측정된 호출만 합산,
  측정 호출 0건이면 None. 측정된 0은 0. 실패 rc!=0 호출도 사용량에 포함한다.
- Claude input은 cache_read/cache_create 제외 값이므로 총 토큰에 캐시를 더한다.
  Codex input은 cached input을 포함하므로 다시 더하지 않는다. reasoning은 output의
  부분집합이며 다시 더하지 않는다. 합계 정의를 warnings/화면에 명시한다.
- 깨진 JSON/잘못된 레코드/읽기 실패는 건수·고정 경고로 표시한다. 실제 예외는 stderr,
  화면/API에는 절대 경로·원문·인증값을 출력하지 않는다. 필터 이후에 모든 표를 집계한다.

반환 JSON 계약 (추가 키는 가능, 아래 키는 반드시 존재):
{period,start,end,project,family,source,timezone:'Asia/Seoul',generated_at,
 projects:[프로젝트명], warnings:[고정 문자열],
 totals:{calls,measured_calls,unmeasured_calls,failed_calls,tokens,input_tokens,
         output_tokens,cache_read,cache_create,reasoning_tokens,issues,unlinked_calls,
         duplicate_records,duplicate_conflicts},
 buckets:[{date:'YYYY-MM-DD'(구간 첫날),family,calls,measured_calls,
           unmeasured_calls,failed_calls,tokens}],
 models:[{family,model,calls,measured_calls,unmeasured_calls,failed_calls,tokens}],
 issues:[{issue_id:양의정수,title,project,work_ids:[str],families:[str],calls,
          measured_calls,unmeasured_calls,failed_calls,tokens,last_at}]}
숫자 계수는 비음수 정수. tokens만 int|None. 일감 title은 큐에 저장된 제목임을 명시.
일감 상세 링크는 UI가 고정 Redmine URL과 issue_id로 만든다.
기간별/모델별 측정 토큰 합계는 totals.tokens와 일치해야 한다.

참조(실제 존재 확인): master/work/usage.py, master/work/session_usage.py,
master/task_queue/persistence.py, master/projects/config.py.
RAG: AXCluster/context/master/work/usage.md 및 session_usage.md.
허용 파일: 이 파일과 master/test_usage_dashboard.py만.

🔴 `#740` 파일 간 응답 중복 (사용자 결정 2026-10-09 (가)) — 세션 소스에만 적용:
- Claude 세션 레코드에 응답 id(`mid`)가 있으면 (스냅샷 host, mid) 로 파일 간 중복을 가린다.
  판정은 `session_usage.same_usage` **하나**를 쓴다(규칙 두 벌 금지). 「처음」은 스냅샷 경로 정렬 순서.
- 같음 → 뒤엣것은 집계에서 빼고 totals.duplicate_records 에 1 더한다.
- 충돌(값이 다름) → 뒤엣것도 집계하고 totals.duplicate_conflicts 에 1 더하며, 고정 경고
  "같은 응답 id 인데 값이 다른 세션 기록이 있습니다(둘 다 셉니다)." 를 한 번 싣는다.
- mid 가 없는 레코드(옛 스냅샷·codex·agy)는 지금처럼 그대로 센다.
- totals 에 duplicate_records·duplicate_conflicts 키는 **항상** 있다(dispatch 소스면 0).
검사: python -B -m unittest master.test_usage_dashboard -v (임시 숫자 로그, 실제 LLM 0).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..projects.config import Registry
from ..task_queue.persistence import _read_md, _tasks_dir
from .session_usage import DEFAULT_STORE, same_usage


_KST = ZoneInfo("Asia/Seoul")
_FAMILIES = ("claude", "codex", "gemini", "local", "unknown")
_AGY_UNKNOWN_MODEL = "Antigravity(모델 미상)"
_PERIODS = ("daily", "weekly", "monthly")
_SOURCES = ("dispatch", "session", "all")
_SESSION_FAMILIES = ("claude", "codex")     # all 에서 세션 기록이 맡는 계열 — 나머지는 작업 실행 기록
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read", "cache_create",
                 "reasoning_tokens")
_ACCOUNTING = ("토큰 합계: Claude 입력+출력+캐시 읽기+캐시 생성, "
               "Codex 입력(캐시 포함)+출력. 추론은 출력에 포함됩니다. "
               "측정된 호출만 합산합니다.")


def _warn(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _error(kind: str, exc: Exception) -> None:
    print(f"[usage-dashboard] {kind}: {type(exc).__name__}: {exc}", file=sys.stderr)


def _day(value: str, label: str) -> date:
    try:
        if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}는 YYYY-MM-DD 날짜여야 합니다.") from exc


def _timestamp(value: object, *, naive_kst: bool) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("시각 없음")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_KST if naive_kst else timezone.utc)
    return dt.astimezone(_KST)


def _family(model: str, lane: str, tool: str = "") -> str:
    value = model.casefold()
    name = lane.casefold().split(":", 1)[0]
    tool = tool.casefold()
    if "claude" in value or "anthropic" in value or name == "claude" or tool == "claude":
        return "claude"
    if "codex" in value or value.startswith(("gpt-", "o1", "o3", "o4")) or name == "codex" or tool == "codex":
        return "codex"
    if "gemini" in value or name == "gemini" or tool == "gemini":
        return "gemini"
    if (name == "agy" or tool == "agy") and not value:
        return "gemini"                 # 머리말 계약: Antigravity 는 모델 미상이어도 gemini
    if name == "local" or tool == "local" or value.startswith(("qwen", "llama", "deepseek", "mistral")):
        return "local"
    return "unknown"


_CONDUCTOR_FAMILIES = {"claude": "claude", "codex": "codex"}


def _conductor_family(raw: dict, model: str, lane: str) -> str:
    """dispatch 레코드의 mode(워커 지휘자 lane|claude|codex)로 계열을 보충한다.

    model·lane 이 둘 다 비었을 때만 쓴다 — 명시 증거가 있으면 그쪽이 이긴다.
    mode=lane 은 지휘 에이전트가 없다는 뜻이라 계열을 정하지 않는다.
    """
    if model or lane:
        return "unknown"
    mode = raw.get("mode") or ""
    if not isinstance(mode, str):
        raise ValueError("모드 형식")
    return _CONDUCTOR_FAMILIES.get(mode.strip().casefold(), "unknown")


def _number(record: dict, key: str) -> int:
    value = record.get(key, 0)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"잘못된 숫자: {key}")
    return value


def _bucket_start(day: date, period: str) -> str:
    if period == "weekly":
        day -= timedelta(days=day.weekday())
    elif period == "monthly":
        day = day.replace(day=1)
    return day.isoformat()


def _empty_counts() -> dict:
    return {"calls": 0, "measured_calls": 0, "unmeasured_calls": 0,
            "failed_calls": 0, "tokens": None}


def _add_counts(row: dict, record: dict) -> None:
    row["calls"] += 1
    row["measured_calls" if record["measured"] else "unmeasured_calls"] += 1
    row["failed_calls"] += int(record["failed"])
    if record["measured"]:
        row["tokens"] = (row["tokens"] or 0) + record["tokens"]


def _normal_record(raw: dict, *, session: bool, tool: str = "") -> dict:
    if not isinstance(raw, dict):
        raise ValueError("레코드 형식")
    at = _timestamp(raw.get("ts"), naive_kst=not session)
    model = raw.get("model") or ""
    lane = raw.get("lane") or ""
    if not isinstance(model, str) or not isinstance(lane, str):
        raise ValueError("모델 형식")
    family = _family(model, lane, tool)
    if family == "unknown" and not session:
        family = _conductor_family(raw, model, lane)
    if not model:
        if lane.startswith("local:") and ":" in lane:
            model = lane.split(":", 1)[1]
        elif lane.casefold().split(":", 1)[0] == "agy" or tool == "agy":
            model = _AGY_UNKNOWN_MODEL
        else:
            model = "모델 미상"
    if session:
        amounts = {key: _number(raw, key.replace("_tokens", "") if key.endswith("_tokens") else key)
                   for key in _TOKEN_FIELDS}
        measured = True
        failed = False
        work_id = ""
    else:
        if not isinstance(raw.get("measured"), bool):
            raise ValueError("계측 형식")
        amounts = {key: _number(raw, key) for key in _TOKEN_FIELDS}
        measured = raw["measured"]
        rc = raw.get("rc", 0)
        if isinstance(rc, bool) or not isinstance(rc, int):
            raise ValueError("종료 코드 형식")
        failed = rc != 0
        work_id = raw.get("work_id") or ""
        if not isinstance(work_id, str):
            raise ValueError("일감 ID 형식")
    if not measured:
        tokens = None
    elif "claude" == family:
        tokens = (amounts["input_tokens"] + amounts["output_tokens"] +
                  amounts["cache_read"] + amounts["cache_create"])
    else:
        tokens = amounts["input_tokens"] + amounts["output_tokens"]
    return {"at": at, "family": family, "model": model, "measured": measured,
            "failed": failed, "work_id": work_id, "amounts": amounts, "tokens": tokens}


def _request_map(root: Path, warnings: list[str], errors: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    tasks = _tasks_dir(root)
    if not tasks.is_dir():
        return result
    try:
        paths = sorted(tasks.rglob("_request.md"))
    except OSError as exc:
        _error("큐 목록 읽기", exc)
        errors["read_errors"] += 1
        _warn(warnings, "일감 연결 자료를 읽지 못했습니다.")
        return result
    for path in paths:
        try:
            meta, _ = _read_md(path)
            wid = meta.get("work_id")
            issue = meta.get("redmine_issue_id")
            if not isinstance(wid, str) or not wid:
                raise ValueError("일감 ID 없음")
            try:
                issue_id = int(issue)
            except (ValueError, TypeError):
                issue_id = 0
            result[wid] = {"issue_id": issue_id, "project": meta.get("project") or "",
                           "title": str(meta.get("title") or "")}
        except (OSError, ValueError, TypeError) as exc:
            _error("일감 읽기", exc)
            errors["invalid_records" if isinstance(exc, (ValueError, TypeError)) else "read_errors"] += 1
            _warn(warnings, "일감 연결 자료 중 읽지 못한 항목이 있습니다.")
    return result


def _read_dispatch(root: Path, names: list[str], warnings: list[str], errors: dict):
    for name in names:
        path = root / name / "usage_log.jsonl"
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        yield name, _normal_record(json.loads(line), session=False)
                    except (ValueError, TypeError) as exc:
                        _error("사용량 레코드", exc)
                        errors["invalid_records"] += 1
                        _warn(warnings, "사용량 로그에 잘못된 레코드가 있습니다.")
        except OSError as exc:
            _error("사용량 로그 읽기", exc)
            errors["read_errors"] += 1
            _warn(warnings, "사용량 로그를 읽지 못했습니다.")


def _read_sessions(root: Path, warnings: list[str], errors: dict):
    # [DOC] `#740` — 위 머리말 「파일 간 응답 중복」 절이 계약이다. 판정은 `same_usage` 로만 한다.
    #       errors 에 duplicate_records·duplicate_conflicts 를 더한다(키는 build_report 가 0 으로 만들어 둔다).
    # [PSEUDO] 아래 루프에서 tool=="claude" 이고 raw 에 mid 가 있으면 (data["host"], mid) 로 처음 레코드를 기억하고,
    #          다시 나오면 same_usage 가 참일 때 건너뛰며 errors["duplicate_records"] += 1,
    #          거짓이면 그대로 yield 하고 errors["duplicate_conflicts"] += 1 · 고정 경고를 _warn 으로 한 번 싣는다.
    if not root.is_dir():
        return
    try:
        paths = sorted(root.glob("*/*/*.json"))
    except OSError as exc:
        _error("세션 목록 읽기", exc)
        errors["read_errors"] += 1
        _warn(warnings, "세션 스냅샷을 읽지 못했습니다.")
        return
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise ValueError("스냅샷 형식")
            tool = data.get("tool") or ""
            if tool not in ("claude", "codex", "agy"):
                raise ValueError("세션 도구")
            owner = data.get("project") or ""
            if not isinstance(owner, str):
                raise ValueError("세션 프로젝트")
            for raw in data["records"]:
                try:
                    yield owner, _normal_record(raw, session=True, tool=tool)
                except (ValueError, TypeError) as exc:
                    _error("세션 레코드", exc)
                    errors["invalid_records"] += 1
                    _warn(warnings, "세션 스냅샷에 잘못된 레코드가 있습니다.")
        except (OSError, ValueError, TypeError) as exc:
            _error("세션 스냅샷 읽기", exc)
            errors["invalid_records" if isinstance(exc, (ValueError, TypeError)) else "read_errors"] += 1
            _warn(warnings, "세션 스냅샷을 읽지 못했습니다.")

def _read_all(root: Path, names: list[str], store: Path, warnings: list[str], errors: dict):
    """source=all — 계열별로 출처 하나. claude·codex 는 세션, 그 밖은 작업 실행 기록."""
    for origin, rec in _read_sessions(store, warnings, errors):
        if rec["family"] in _SESSION_FAMILIES:
            yield origin, rec
    for origin, rec in _read_dispatch(root, names, warnings, errors):
        if rec["family"] not in _SESSION_FAMILIES:
            yield origin, rec


def build_report(project: str = "", period: str = "daily", start: str = "",
                 end: str = "", family: str = "", source: str = "dispatch", *,
                 projects_root=None, queue_root=None, session_store=None, now=None) -> dict:
    # [DOC] 위 동결 계약에 맞는 읽기 전용 보고서. 다른 조각의 구현을 기다리지 않는다.
    if period not in _PERIODS or family not in ("", *_FAMILIES) or source not in _SOURCES:
        raise ValueError("period, family 또는 source가 잘못되었습니다.")
    clock = now or datetime.now(_KST)
    if isinstance(clock, date) and not isinstance(clock, datetime):
        clock = datetime.combine(clock, datetime.min.time(), tzinfo=_KST)
    if not isinstance(clock, datetime):
        raise ValueError("now가 잘못되었습니다.")
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=_KST)
    clock = clock.astimezone(_KST)
    last = _day(end, "end") if end else clock.date()
    first = _day(start, "start") if start else last - timedelta(days=29)
    if first > last or (last - first).days >= 366:
        raise ValueError("기간은 순서대로 최대 366일이어야 합니다.")
    registry = Registry.load(Path(projects_root) if projects_root is not None else None)
    if project and project not in registry.names:
        raise ValueError("등록되지 않은 프로젝트입니다.")
    names = [project] if project else list(registry.names)
    warnings = [_ACCOUNTING, "일감 제목은 큐에 저장된 제목입니다."]
    if source == "all":
        _warn(warnings, "모두 보기: Claude·Codex는 대화 세션 기록, 그 밖의 계열은 작업 실행 기록에서 셉니다"
                        "(같은 호출을 두 번 세지 않습니다). 일감별 표는 작업 실행 기록에서 봅니다.")
    if source in ("session", "all"):
        _warn(warnings, "세션 사용량에는 일감 귀속이 없습니다. 프로젝트는 세션 작업 경로로만 정합니다.")
        if project:
            _warn(warnings, "프로젝트 필터는 작업 경로가 등록 작업장에 속한 세션만 포함합니다.")
    totals = {**_empty_counts(), "input_tokens": 0, "output_tokens": 0,
              "cache_read": 0, "cache_create": 0, "reasoning_tokens": 0,
              "issues": 0, "unlinked_calls": 0, "invalid_records": 0, "read_errors": 0}
    buckets: dict[tuple[str, str], dict] = {}
    models: dict[tuple[str, str], dict] = {}
    issues: dict[int, dict] = {}
    # [DOC] `#740` — 중복 집계 두 칸도 여기서 0 으로 연다(totals.update(errors) 로 보고서에 실린다).
    # [PSEUDO] 아래 dict 에 "duplicate_records": 0, "duplicate_conflicts": 0 을 더하고 위 totals 초기값에도 같은 두 키를 0 으로 둔다.
    errors = {"invalid_records": 0, "read_errors": 0}
    qroot = (Path(queue_root) if queue_root is not None else
             Path(os.environ.get("AX_TASK_QUEUE_ROOT") or Path.home() / "ax-state"))
    links = _request_map(qroot, warnings, errors) if source == "dispatch" else {}
    store = Path(session_store) if session_store is not None else DEFAULT_STORE
    records = (_read_dispatch(registry.root, names, warnings, errors) if source == "dispatch" else
               _read_sessions(store, warnings, errors) if source == "session" else
               _read_all(registry.root, names, store, warnings, errors))
    for origin, rec in records:
        if project and source != "dispatch" and origin != project:
            continue
        day = rec["at"].date()
        if day < first or day > last or (family and rec["family"] != family):
            continue
        _add_counts(totals, rec)
        if rec["measured"]:
            for key in _TOKEN_FIELDS:
                totals[key] += rec["amounts"][key]
        bucket_key = (_bucket_start(day, period), rec["family"])
        bucket = buckets.setdefault(bucket_key, {"date": bucket_key[0], "family": rec["family"],
                                                 **_empty_counts()})
        _add_counts(bucket, rec)
        model_key = (rec["family"], rec["model"])
        model_row = models.setdefault(model_key, {"family": rec["family"], "model": rec["model"],
                                                  **_empty_counts()})
        _add_counts(model_row, rec)
        if source != "dispatch":
            continue
        link = links.get(rec["work_id"])
        if (not link or link["project"] != origin or not link["issue_id"]
                or link["issue_id"] < 0):
            totals["unlinked_calls"] += 1
            continue
        issue_id = link["issue_id"]
        issue = issues.setdefault(issue_id, {"issue_id": issue_id, "title": link["title"],
                                             "project": origin, "work_ids": [], "families": [],
                                             **_empty_counts(), "last_at": ""})
        if rec["work_id"] not in issue["work_ids"]:
            issue["work_ids"].append(rec["work_id"])
        if rec["family"] not in issue["families"]:
            issue["families"].append(rec["family"])
        _add_counts(issue, rec)
        issue["last_at"] = max(issue["last_at"], rec["at"].isoformat())
    for issue in issues.values():
        issue["work_ids"].sort()
        issue["families"].sort()
    totals["issues"] = len(issues)
    totals.update(errors)
    return {"period": period, "start": first.isoformat(), "end": last.isoformat(),
            "project": project, "family": family, "source": source, "timezone": "Asia/Seoul",
            "generated_at": clock.isoformat(), "projects": names, "warnings": warnings,
            "totals": totals, "buckets": [buckets[k] for k in sorted(buckets)],
            "models": [models[k] for k in sorted(models)],
            "issues": sorted(issues.values(), key=lambda row: row["issue_id"])}
