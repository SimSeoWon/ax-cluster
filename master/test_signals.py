"""생산자② code-writer 신호 (#206) 계약 테스트.

재는 것 넷:
    ① 레코드 스키마    원전 log_writer_signal 글자대로 — intent 필수, 선택 필드는 값 있을 때만
    ② 왕복 계약       쓴 줄을 소비자(원전 _read_signals)의 눈으로 다시 읽는가 · 깨진 줄 스킵
    ③ 클라 자리       .33 MCP 도구가 마스터 대행 POST 를 올바른 본문으로 부르는가
    ④ 통합자 배선     통과분만 적재 · intent=큐 제목(조회 실패 시 task_id) · 실패는 note

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


# ── ④ 통합자 배선 ─────────────────────────────────────────────

def test_integrator_lays_signals_for_passed_only():
    from master.work import integrate as IG
    p = fixture()
    itg = IG.Integration(work_id="w-9")
    ok = IG.Applied(task_id="t-ok", files=["Source/M/A.cpp"], commit="abc123")
    bad = IG.Applied(task_id="t-bad", files=["Source/M/B.cpp"], error="층1 불합격")
    itg.applied = [ok, bad]

    def fake_api(method, path, payload=None):
        assert path == "/api/v1/tasks/t-ok"
        return {"task_id": "t-ok", "title": "히트박스[UHitBox] 판정 추가"}

    IG._lay_signals(p, itg, api=fake_api)
    got = SG.read_signals(p)
    check("[중요] 통과분만 적재된다 (불합격은 실패 카탈로그 소관)",
          len(got) == 1 and got[0]["work_id"] == "w-9", str(len(got)))
    check("intent = 큐의 task 제목 (사람이 쓴 요청)",
          got[0]["intent"] == "히트박스[UHitBox] 판정 추가", got[0]["intent"])
    check("source=pipeline", got[0].get("source") == "pipeline")
    check("고친 파일이 실린다",
          got[0]["files_modified"] == [{"path": "Source/M/A.cpp", "summary": ""}])

    p2 = fixture()
    itg2 = IG.Integration(work_id="w-10")
    itg2.applied = [IG.Applied(task_id="t-x", files=["f"], commit="def456")]

    def dead_api(method, path, payload=None):
        raise RuntimeError("큐 죽음")

    IG._lay_signals(p2, itg2, api=dead_api)
    got2 = SG.read_signals(p2)
    check("[중요] 제목 조회 실패해도 task_id 로 남긴다 — 신호 유실이 더 비싸다",
          len(got2) == 1 and got2[0]["intent"] == "t-x", str(got2))

    class BadPaths:
        root = "/proc/없는곳/여긴못쓴다"

    itg3 = IG.Integration(work_id="w-11")
    itg3.applied = [IG.Applied(task_id="t-y", files=["f"], commit="aaa111")]
    IG._lay_signals(BadPaths(), itg3, api=dead_api)
    check("적재 실패는 통합을 안 막고 note 로 말한다 (조용한 실패 금지)",
          "신호 적재 실패" in itg3.note, itg3.note)


def main() -> int:
    for fn in (test_record_schema, test_roundtrip_and_broken_lines,
               test_client_tool_posts_master_mediated,
               test_integrator_lays_signals_for_passed_only):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_signals: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
