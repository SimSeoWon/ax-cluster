"""생산자② code-writer 신호 (#206) 계약 테스트.

재는 것 넷:
    ① 레코드 스키마    원전 log_writer_signal 글자대로 — intent 필수, 선택 필드는 값 있을 때만
    ② 왕복 계약       쓴 줄을 소비자(원전 _read_signals)의 눈으로 다시 읽는가 · 깨진 줄 스킵
    ③ 클라 자리       .33 MCP 도구가 마스터 대행 POST 를 올바른 본문으로 부르는가
    ④ 파이프라인 배선  work merged 종결당 1건 · rejected 는 0건 · 적재 실패는 응답·로그 (#383)

실행: .venv/bin/python master/test_signals.py   (LLM 0 · 네트워크 0 — 전부 주입)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import signals as SG          # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        self.root = root


def fixture():
    return P(Path(tempfile.mkdtemp(prefix="ax-sg-")))


# ── ① 레코드 스키마 ───────────────────────────────────────────

def test_record_schema():
    r = SG.make_record(intent="미션 매니저[Manager_Mission]에 태스크 추가",
                       files_modified=[{"path": "Source/M/A.cpp", "summary": "신규"}],
                       work_id="w1", source="pipeline")
    for k in ("timestamp", "intent", "queries", "files_read", "files_modified",
              "iterations", "feedback_notes", "rejected_approaches", "error_recoveries"):
        check(f"[중요] 원전 필수 필드 {k}", k in r, str(sorted(r)))
    check("선택 필드는 값 있을 때만 — session_id 없음", "session_id" not in r)
    check("work_id 는 실렸다", r.get("work_id") == "w1")
    check("iterations 기본 1", r["iterations"] == 1)
    check("[대괄호] 식별자가 원형 보존된다", "[Manager_Mission]" in r["intent"])

    try:
        SG.make_record(intent="  ")
        check("[중요] intent 없으면 ValueError", False)
    except ValueError:
        check("[중요] intent 없으면 ValueError", True)
    check("iterations 쓰레기값은 1 로 접는다",
          SG.make_record(intent="x", iterations="셋")["iterations"] == 1)
    check("iterations 0 이하도 1", SG.make_record(intent="x", iterations=0)["iterations"] == 1)


# ── ② 왕복 — 소비자의 눈으로 ─────────────────────────────────

def test_roundtrip_and_broken_lines():
    p = fixture()
    SG.append_signal(p, SG.make_record(intent="첫 작업", source="requester"))
    path = Path(SG.append_signal(p, SG.make_record(intent="둘째 작업", source="pipeline")))
    check("[중요] 경로 계약 — recipes/_signals.jsonl (원전 파일명 그대로)",
          path.as_posix().endswith("recipes/_signals.jsonl"), str(path))
    with path.open("a", encoding="utf-8") as f:
        f.write("{깨진 줄\n\n")
    got = SG.read_signals(p)
    check("[중요] 깨진 줄은 스킵, 성한 것은 다 읽는다 (원전 _read_signals 규약)",
          len(got) == 2 and got[0]["intent"] == "첫 작업", str(len(got)))
    check("빈 파일이면 빈 리스트", SG.read_signals(fixture()) == [])


# ── ③ 클라 자리 (.33 MCP) ─────────────────────────────────────

def _load_client():
    import importlib.util
    f = Path(__file__).resolve().parents[1] / "client" / "runtime" / "client_mcp.py"
    spec = importlib.util.spec_from_file_location("_cm", f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_client_tool_posts_master_mediated():
    cm = _load_client()
    calls = []

    def fake_api(method, path, payload=None):
        calls.append((method, path, payload))
        return {"ok": True, "stored_at": "…", "intent": payload["intent"]}

    got = cm.dispatch_tool("log_writer_signal", {
        "intent": "터치 버튼[SquareTouchButton] 스타일 게터 전환",
        "files_modified": [{"path": "Source/M/B.cpp", "summary": "게터 사용"}],
        "iterations": 2, "feedback_notes": "리네이밍 제안은 거절됨",
    }, api=fake_api)
    m, path, payload = calls[0]
    check("[중요] 마스터 대행 POST /api/v1/signals (redmine_note 와 같은 구조)",
          (m, path) == ("POST", "/api/v1/signals"), f"{m} {path}")
    check("본문에 과정 필드가 실린다",
          payload["iterations"] == 2 and payload["files_modified"]
          and payload["feedback_notes"], str(sorted(payload)))
    check("응답 그대로 반환", got.get("ok") is True)

    tool = next(t for t in cm.TOOLS if t["name"] == "log_writer_signal")
    check("intent 가 required 로 선언돼 있다",
          tool["inputSchema"].get("required") == ["intent"])
    try:
        cm.dispatch_tool("log_writer_signal", {"intent": ""}, api=fake_api)
        check("[중요] intent 비면 클라에서 막는다 (왕복 전에)", False)
    except cm.ClientError:
        check("[중요] intent 비면 클라에서 막는다 (왕복 전에)", True)

    from master.auth import REQUESTER_SCOPE
    check("[중요] requester 스코프가 POST /api/v1/signals 를 연다",
          ("POST", "/api/v1/signals") in REQUESTER_SCOPE, str(REQUESTER_SCOPE))


# ── ④ 파이프라인 배선 (#383) ──────────────────────────────────

# [주의] 통합자가 커밋할 때 적재하던 배선은 통합자 삭제(2026-09-03)와 함께 사라졌고, 그 뒤
# `source="pipeline"` 호출부가 0곳이었다. `#383` 이 work 의 merged 종결 훅으로 다시 이었다.

def test_pipeline_signal_on_work_merged():
    p = fixture()
    work = {"work_id": "w-383", "title": "히트박스[UHitBox] 판정 추가", "round": 3,
            "review_decision": {"notes": "판정 반경이 좁다 — 다음에 보정"}}
    tasks = [{"task_id": "t1", "target_file": "Source/M/UHitBox.cpp",
              "header_file": "Source/M/UHitBox.h"},
             {"task_id": "t2", "target_file": "Source/M/UHitBox.cpp",          # 중복 — 한 번만
              "target_files": ["Source/M/UHitBox.cpp", "Source/M/Extra.cpp", " "]}]
    stored = SG.record_work_merged(p, work, tasks)
    got = SG.read_signals(p)
    check("[중요] work 당 1건 · 저장 경로를 돌려준다",
          len(got) == 1 and stored.endswith("recipes/_signals.jsonl"), f"{len(got)} {stored}")
    r = got[0]
    check("[중요] source=pipeline · work_id · intent=work 제목",
          r.get("source") == "pipeline" and r.get("work_id") == "w-383"
          and r["intent"] == "히트박스[UHitBox] 판정 추가", str(r))
    check("iterations = 라운드 수", r["iterations"] == 3, str(r["iterations"]))
    check("files_modified = 조각 파일 전부(단수·복수 필드) · 중복 제거 · 요청자 신호와 같은 모양",
          r["files_modified"] == [{"path": "Source/M/UHitBox.cpp", "summary": ""},
                                  {"path": "Source/M/UHitBox.h", "summary": ""},
                                  {"path": "Source/M/Extra.cpp", "summary": ""}],
          str(r["files_modified"]))
    check("검수 노트가 feedback_notes 로 간다", r["feedback_notes"] == "판정 반경이 좁다 — 다음에 보정")
    check("큐가 모르는 과정 필드는 비운다",
          r["queries"] == [] and r["files_read"] == [] and r["error_recoveries"] == [])

    p2 = fixture()
    SG.record_work_merged(p2, {"work_id": "w-x", "round": "쓰레기"}, [])
    r2 = SG.read_signals(p2)[0]
    check("제목 없는 work 는 work_id 가 intent · 라운드 쓰레기값은 1",
          r2["intent"] == "w-x" and r2["iterations"] == 1 and r2["files_modified"] == [], str(r2))
    try:
        SG.record_work_merged(fixture(), {}, [])
        check("[중요] 제목도 work_id 도 없으면 정직하게 예외 (호출자가 fail-soft)", False)
    except ValueError:
        check("[중요] 제목도 work_id 도 없으면 정직하게 예외 (호출자가 fail-soft)", True)


def _queue_client(root: Path):
    """실제 8101 앱 + **실제 임시 큐**(`test_ontology_proxy` 의 하니스 · 소켓은 열지 않는다)."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from master.task_queue import server as SV
    from master.task_queue.persistence import TaskIndex
    idx = TaskIndex(root)
    with patch.object(SV, "TaskIndex", return_value=idx), \
            patch.object(SV, "_bootstrap_log_rotation"), \
            patch.object(SV, "recover_stuck_works", return_value=[]), \
            patch.object(SV, "load_token", return_value=_TOKEN), \
            patch("master.auth.load_role_token", return_value=""), \
            patch("threading.Thread.start"), patch("uvicorn.run") as run:
        SV._run_http_server(root, 0, "127.0.0.1")
    return TestClient(run.call_args.args[0]), idx


_TOKEN = "master-" + "m" * 40


def test_server_hook_lays_signal_only_on_merged():
    """실제 PATCH 라우트 — merged 1건 · rejected 0건 · 적재가 죽어도 종결은 성립한다."""
    from unittest.mock import patch
    from master.task_queue import server as SV
    from master.task_queue.logic import register_work

    root = Path(tempfile.mkdtemp(prefix="ax-sg-queue-"))
    twin = fixture()
    client, idx = _queue_client(root)
    hdr = {"Authorization": "Bearer " + _TOKEN}
    logs = []

    def new_work(title):
        # 등재 라우트는 마운트 관문을 지난다 — 여기서 재는 것은 종결 훅이라 코어로 직접 등재한다
        return register_work(idx, title=title, target_repo="R", project="T").get("work_id", "")

    with patch("master.context_search.paths.resolve", lambda name="": twin), \
            patch("master.context_synth.history_gen.record_work_terminal",
                  lambda *a, **k: "history.md"), \
            patch.object(SV, "_tq_log", lambda m, *_a, **_k: logs.append(m)):
        w1 = new_work("신호 배선 검사 — merged")
        check("(준비) work 등재", bool(w1), w1)
        r = client.patch(f"/api/v1/works/{w1}", headers=hdr,
                         json={"project": "T", "merge_status": "merged"}).json()
        got = SG.read_signals(twin)
        check("[중요] merged 전이 → pipeline 신호 1건", r.get("ok") and len(got) == 1
              and got[0].get("source") == "pipeline" and got[0].get("work_id") == w1,
              f"{r} / {got}")
        check("응답에 저장 경로가 실린다",
              str(r.get("signal_written", "")).endswith("recipes/_signals.jsonl"), str(r))
        check("[중요] 로그 한 줄이 남는다 (볼 사건 = 적재)",
              any("[signal]" in m and w1 in m and "pipeline" in m for m in logs), str(logs))

        w2 = new_work("신호 배선 검사 — rejected")
        r = client.patch(f"/api/v1/works/{w2}", headers=hdr,
                         json={"project": "T", "merge_status": "rejected"}).json()
        check("[중요] rejected 는 적재하지 않는다 (실패 카탈로그의 몫)",
              r.get("ok") and "signal_written" not in r and len(SG.read_signals(twin)) == 1,
              f"{r} / {len(SG.read_signals(twin))}")

        w3 = new_work("신호 배선 검사 — 적재 실패")
        logs.clear()

        def boom(*a, **k):
            raise OSError("디스크가 찼다")

        with patch.object(SG, "record_work_merged", boom):
            r = client.patch(f"/api/v1/works/{w3}", headers=hdr,
                             json={"project": "T", "merge_status": "merged"}).json()
        check("[중요] 적재가 죽어도 종결은 성립하고 응답·로그로 말한다",
              r.get("ok") and "신호 적재 실패" in r.get("signal_error", "")
              and any("[signal]" in m and "실패" in m for m in logs), f"{r} / {logs}")
    client.close()


def main() -> int:
    for fn in (test_record_schema, test_roundtrip_and_broken_lines,
               test_client_tool_posts_master_mediated,
               test_pipeline_signal_on_work_merged,
               test_server_hook_lays_signal_only_on_merged):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_signals: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
