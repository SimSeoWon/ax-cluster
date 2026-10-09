"""`#740` 파일 간 응답 중복 — 조각 1(session_usage)·조각 2(usage_dashboard)의 계약 검사.

    .venv/bin/python master/test_session_usage_dedupe.py

[DOC] 사용자 결정 2026-10-09 (가): 같은 (host, mid) · 같은 값 → 한 번만 · 값이 다르면 둘 다 세고 경고.
      실 LLM·SSH·네트워크 0 — 임시 디렉토리에 스냅샷 JSON 을 손으로 만들어 쓴다. 출력 형식은 저장소 관례
      (`check()` 와 마지막 줄 `OK|FAIL test_session_usage_dedupe: N/M 통과`)를 따른다.
      스냅샷 모양: {"host","tool","session_id","origin","collected_at","project","work_id","task_id","records":[…]}
      레코드 모양: {"ts","model","input","output","cache_read","cache_create","reasoning","mid"}
[DOC] 검사할 계약(전부):
      1 parse_claude 가 레코드에 mid 를 남긴다 · 파일 안의 같은 id 는 여전히 한 번만
      2 same_usage — 값이 같으면 참 · 하나라도 다르면 거짓 · ts 차이는 무시
      3 cross_file_duplicates — 두 파일에 같은 값(같음 1) · 세 번째 파일에 다른 값(충돌 1) · mid 없는 레코드
        (no_mid) · 깨진 파일(unreadable) · 반환 키가 전부 있다 · conflicts 에 절대 경로가 없다
      4 usage_dashboard.build_report(source="session") — 같음은 한 번만 합산(totals.tokens 가 줄어든다) ·
        duplicate_records 1 · 충돌은 둘 다 합산 · duplicate_conflicts 1 · 고정 경고 문구 · source="dispatch" 여도
        두 키가 0 으로 있다
      build_report 는 projects_root(빈 등록부)·queue_root·session_store·now 를 주입해 결정적으로 돈다 —
      기존 master/test_usage_dashboard.py 의 주입 방식을 그대로 본뜬다.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.work.session_usage import cross_file_duplicates, parse_claude, same_usage
from master.work.usage_dashboard import build_report

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label} — {detail}")


def _record(*, mid: str | None = "msg-1", output: int = 3,
            ts: str = "2026-10-15T00:00:00Z") -> dict:
    record = {"ts": ts, "model": "claude-sonnet-4-5", "input": 10,
              "output": output, "cache_read": 2, "cache_create": 1, "reasoning": 0}
    if mid is not None:
        record["mid"] = mid
    return record


def _snapshot(store: Path, host: str, name: str, records: list[dict]) -> Path:
    path = store / host / "claude" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "host": host, "tool": "claude", "session_id": name,
        "origin": f"{name}.jsonl", "collected_at": "2026-10-15T00:00:00",
        "project": None, "work_id": None, "task_id": None, "records": records,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _check_parse_claude() -> None:
    with TemporaryDirectory() as td:
        path = Path(td) / "session.jsonl"
        def line(mid: str | None, request_id: str, ts: str,
                 output_tokens: int = 3) -> str:
            message = {"model": "claude-sonnet-4-5", "usage": {
                "input_tokens": 10, "output_tokens": output_tokens,
                "cache_read_input_tokens": 2, "cache_creation_input_tokens": 1}}
            if mid is not None:
                message["id"] = mid
            return json.dumps({"type": "assistant", "sessionId": "session-1",
                               "timestamp": ts, "requestId": request_id,
                               "message": message})
        path.write_text("\n".join((
            line("msg-1", "request-1", "2026-10-15T00:00:00Z"),
            line("msg-1", "request-1", "2026-10-15T00:00:01Z", 999),
            line(None, "request-2", "2026-10-15T00:00:02Z"),
        )) + "\n", encoding="utf-8")
        with path.open(encoding="utf-8") as lines:
            session = parse_claude(lines)
        check("parse_claude: 파일 안 중복과 mid 보존",
              session is not None and session.session_id == "session-1"
              and [r.get("mid") for r in session.records] == ["msg-1", "request-2"]
              and session.records[0]["input"] == 10
              and session.records[0]["output"] == 3,
              f"records={None if session is None else session.records!r}")


def _check_same_usage() -> None:
    with TemporaryDirectory():
        first = _record()
        later = {**first, "ts": "2026-10-16T00:00:00Z"}
        check("same_usage: 시각 차이는 무시", same_usage(first, later))
        check("same_usage: mid 차이는 무시",
              same_usage(first, {**later, "mid": "msg-2"}))
        changes = {"model": "other", "input": 11, "output": 4,
                   "cache_read": 3, "cache_create": 2, "reasoning": 1}
        check("same_usage: 사용량 필드마다 차이를 구별",
              all(not same_usage(first, {**later, key: value})
                  for key, value in changes.items()))
        missing = {"model": "claude-sonnet-4-5"}
        check("same_usage: 없는 키는 None으로 비교",
              same_usage(missing, {**missing, "input": None})
              and not same_usage(missing, {**missing, "input": 0}))


def _check_cross_file_duplicates() -> None:
    with TemporaryDirectory() as td:
        store = Path(td) / "sessions"
        first = _record()
        _snapshot(store, "host-1", "a", [first])
        _snapshot(store, "host-1", "b", [_record(ts="2026-10-15T00:00:01Z")])
        _snapshot(store, "host-1", "c", [_record(output=7)])
        _snapshot(store, "host-1", "d", [_record(mid=None)])
        broken = store / "host-1" / "claude" / "e.json"
        broken.write_text("{broken", encoding="utf-8")
        stats = cross_file_duplicates(store, sample=1)
        keys = {"files", "records", "no_mid", "duplicate_ids", "extra_same",
                "extra_conflict", "conflicts", "unreadable"}
        check("cross_file_duplicates: 반환 키와 건수",
              keys <= stats.keys() and all(isinstance(stats[k], int) and stats[k] >= 0
                                            for k in keys - {"conflicts"})
              and (stats["files"], stats["records"], stats["no_mid"],
                   stats["duplicate_ids"], stats["extra_same"],
                   stats["extra_conflict"], stats["unreadable"]) == (4, 4, 1, 1, 1, 1, 1),
              f"stats={stats!r}")
        conflicts = stats.get("conflicts", [])
        check("cross_file_duplicates: 충돌 표본에 절대 경로 없음",
              len(conflicts) == 1 and conflicts[0].get("host") == "host-1"
              and conflicts[0].get("mid") == "msg-1"
              and len(conflicts[0].get("origins", [])) >= 2
              and all(Path(origin).name == origin and not Path(origin).is_absolute()
                      for origin in conflicts[0].get("origins", []))
              and str(store) not in json.dumps(conflicts, ensure_ascii=False),
              f"conflicts={conflicts!r}")


def _check_dashboard() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        projects_root = root / "projects"
        projects_root.mkdir()
        (projects_root / "projects.yaml").write_text(
            "version: 1\nactive: ''\nprojects: []\n", encoding="utf-8")
        store = root / "sessions"
        now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        def report(source: str) -> dict:
            return build_report(source=source, projects_root=projects_root,
                                queue_root=root / "queue", session_store=store, now=now)
        _snapshot(store, "host-1", "a", [_record()])
        single = report("session")
        _snapshot(store, "host-1", "b", [_record(ts="2026-10-15T00:00:01Z")])
        duplicate = report("session")
        _snapshot(store, "host-1", "c", [_record(output=7)])
        session = report("session")
        totals = session["totals"]
        check("build_report(session): 같은 값 한 번만 합산",
              single["totals"]["tokens"] == 16
              and duplicate["totals"]["tokens"] == 16
              and duplicate["totals"]["calls"] == 1
              and duplicate["totals"]["duplicate_records"] == 1,
              f"totals={duplicate['totals']!r}")
        check("build_report(session): 충돌은 두 값 모두 합산",
              totals["tokens"] == 36 and totals["calls"] == 2
              and totals["duplicate_records"] == 1,
              f"totals={totals!r}")
        warning = "같은 응답 id 인데 값이 다른 세션 기록이 있습니다(둘 다 셉니다)."
        check("build_report(session): 충돌을 합산하고 경고",
              totals["duplicate_conflicts"] == 1
              and session["warnings"].count(warning) == 1,
              f"totals={totals!r}, warnings={session['warnings']!r}")
        dispatch = report("dispatch")["totals"]
        check("build_report(dispatch): 중복 키를 0으로 제공",
              dispatch.get("duplicate_records") == 0
              and dispatch.get("duplicate_conflicts") == 0,
              f"totals={dispatch!r}")


def main() -> int:
    # [DOC] 위 계약 1~4 를 함수 하나씩으로 나눠 부르고, 각 함수는 자기 임시 디렉토리를 만들고 지운다.
    for label, run in (("parse_claude", _check_parse_claude),
                       ("same_usage", _check_same_usage),
                       ("cross_file_duplicates", _check_cross_file_duplicates),
                       ("usage_dashboard", _check_dashboard)):
        try:
            run()
        except Exception as exc:
            check(label, False, f"{type(exc).__name__}: {exc}")
    total = PASS + FAIL
    print(f"{'OK' if FAIL == 0 else 'FAIL'} test_session_usage_dedupe: {PASS}/{total} 통과")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
