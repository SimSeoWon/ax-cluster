"""relay(`#942`) 계약 테스트 — 세션 저장소 · 에이전트 호출부 · 작업 경계 · 콘솔.

임시 디렉터리와 가짜 실행 파일만 쓴다 — 실제 CLI·Redmine·일감 잠금을 건드리지 않는다.
실행: .venv/bin/python master/test_relay.py
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.relay import agents as A   # noqa: E402
from master.relay import boundary as B  # noqa: E402
from master.relay import store as S    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def run(fn):
    with tempfile.TemporaryDirectory() as d:
        try:
            fn(Path(d))
        except Exception as e:                          # noqa: BLE001
            check(fn.__name__, False, f"예외 {type(e).__name__}: {e}")


# ── 저장소 (T2) ──────────────────────────────────────────────────────────────

def t_store_open_and_seq(tmp):
    r = S.open_session(tmp, 7)
    check("새 세션", r["resumed"] is False and r["issue"] == 7, str(r))
    check("시작 기록이 1번", S.last_seq(tmp, 7) == 1 and S.read(tmp, 7)[0]["kind"] == "session")
    a = S.append(tmp, 7, kind="user", agent="claude", text="안녕")
    b = S.append(tmp, 7, kind="agent_text", agent="claude", text="네", data={"k": 1})
    check("순번 단조 증가", (a["seq"], b["seq"]) == (2, 3), f"{a['seq']},{b['seq']}")
    check("after 로 뒤만 읽는다", [x["seq"] for x in S.read(tmp, 7, after=2)] == [3])
    check("data 보존", S.read(tmp, 7, after=2)[0]["data"] == {"k": 1})
    r2 = S.open_session(tmp, 7)
    check("다시 열면 이어감", r2["resumed"] is True and S.last_seq(tmp, 7) == 3, str(r2["resumed"]))
    check("열린 세션 목록", S.sessions(tmp) == [7], str(S.sessions(tmp)))


def t_store_concurrent_append(tmp):
    S.open_session(tmp, 3)
    def work(k):
        for i in range(25):
            S.append(tmp, 3, kind="user", text=f"{k}-{i}")
    ths = [threading.Thread(target=work, args=(k,)) for k in range(4)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    seqs = [x["seq"] for x in S.read(tmp, 3)]
    check("동시 쓰기 — 순번 빠짐·중복 없음", seqs == list(range(1, 102)), f"{len(seqs)}건 끝 {seqs[-1]}")


def t_store_agent_state(tmp):
    S.open_session(tmp, 5)
    st = S.update_agent(tmp, 5, "codex", session="abc", seen=4, current=True)
    check("에이전트 칸 갱신", st["agents"]["codex"]["session"] == "abc" and st["current"] == "codex", str(st))
    check("다른 에이전트는 그대로", S.state(tmp, 5)["agents"]["claude"]["session"] == "")
    dbg = S.debug_path(tmp, 5).read_text(encoding="utf-8")
    check("세션 ID 변경이 디버그 로그에 남는다", "codex 세션 ID (없음) → abc" in dbg, dbg[-200:])
    for bad, kw in (("gpt", {}), ("codex", {"nope": 1})):
        try:
            S.update_agent(tmp, 5, bad, **kw)
            check(f"거절 {bad} {kw}", False, "예외 없음")
        except S.StoreError:
            check(f"거절 {bad} {kw}", True)


def t_store_corrupt_not_overwritten(tmp):
    S.open_session(tmp, 9)
    p = S.session_dir(tmp, 9) / S.STATE_NAME
    p.write_text("{깨짐", encoding="utf-8")
    try:
        S.open_session(tmp, 9)
        check("깨진 상태는 멈춘다", False, "예외 없음")
    except S.StoreError:
        check("깨진 상태는 멈춘다", True)
    check("덮어쓰지 않았다", p.read_text(encoding="utf-8") == "{깨짐")
    with open(S.log_path(tmp, 9), "a", encoding="utf-8") as fh:
        fh.write("json 아님\n")
    recs = S.read(tmp, 9)
    check("못 읽는 로그 줄은 버리지 않는다", recs[-1]["kind"] == "unreadable" and recs[-1]["text"] == "json 아님")


def t_store_archive(tmp):
    S.open_session(tmp, 4)
    S.update_agent(tmp, 4, "claude", session="sid-1", current=True)
    S.append(tmp, 4, kind="user", agent="claude", text="내용")
    r = S.archive(tmp, 4, why="일감 완료")
    dest = Path(r["dest"])
    check("보관소로 옮겼다", dest.is_dir() and not S.session_dir(tmp, 4).exists(), str(dest))
    kept = [json.loads(x) for x in (dest / S.LOG_NAME).read_text(encoding="utf-8").splitlines()]
    check("로그 보존 + 보관 기록", kept[-1]["kind"] == "session" and "보관" in kept[-1]["text"] and len(kept) == 3)
    check("열린 세션 없음", S.sessions(tmp) == [])
    r2 = S.open_session(tmp, 4)
    check("다시 열면 빈 세션", r2["resumed"] is False and r2["state"]["agents"]["claude"]["session"] == ""
          and S.last_seq(tmp, 4) == 1, str(r2["state"]["agents"]["claude"]))
    try:
        S.archive(tmp, 99)
        check("없는 세션 보관 거절", False, "예외 없음")
    except S.StoreError:
        check("없는 세션 보관 거절", True)
    check("루트 디버그 로그에 보관 기록", "#4 →" in S.debug_path(tmp).read_text(encoding="utf-8"))


# ── 에이전트 호출부 (T3) ─────────────────────────────────────────────────────
# 이벤트 줄은 2026-11-14 실측(리포트 180 T1 절)에서 나온 형식이다.

CLAUDE_LINES = [
    {"type": "system", "subtype": "init", "session_id": "c-1", "permissionMode": "bypassPermissions",
     "mcp_servers": [{"name": "ax-projects", "status": "connected"}]},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                   "input": {"command": "echo relay-ok"}}]}},
    {"type": "rate_limit_event"},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "relay-ok"}]}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "끝났습니다"}]}},
    {"type": "brand_new_event", "x": 1},
    {"type": "result", "subtype": "success", "is_error": False, "session_id": "c-1", "result": "끝났습니다",
     "num_turns": 2, "usage": {"input_tokens": 5, "output_tokens": 7}},
]
CODEX_LINES = [
    {"type": "thread.started", "thread_id": "x-1"},
    {"type": "turn.started"},
    {"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": "/bin/bash -lc 'echo relay-ok'",
                                      "aggregated_output": "", "exit_code": None, "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "i1", "type": "command_execution", "command": "/bin/bash -lc 'echo relay-ok'",
                                        "aggregated_output": "relay-ok\n", "exit_code": 0, "status": "completed"}},
    {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": "ZEBRA-17"}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
]
AGY_LINES = [
    {"event": "init", "conversation_id": "g-1", "init": {"model": "m", "permission_mode": "always-proceed"}},
    {"event": "step_update", "step_update": {"conversation_id": "g-1", "step_index": 0, "state": "DONE", "step_type": "user_input"}},
    {"event": "step_update", "step_update": {"step_index": 5, "state": "ACTIVE", "step_type": "tool", "tool_name": "run_command",
                                             "tool_info": {"name": "run_command", "parameters": {"CommandLine": "echo relay-ok"}}}},
    {"event": "step_update", "step_update": {"step_index": 5, "state": "DONE", "step_type": "tool", "tool_name": "run_command",
                                             "tool_info": {"name": "run_command", "output": "relay-ok\r\n"}}},
    {"event": "step_update", "step_update": {"step_index": 6, "state": "ACTIVE", "step_type": "agent_response", "text_delta": "ZEBRA"}},
    {"event": "step_update", "step_update": {"step_index": 6, "state": "DONE", "step_type": "agent_response", "text_delta": "-17\n"}},
    {"event": "result", "result": {"conversation_id": "g-1", "status": "SUCCESS", "response": "ZEBRA-17\n",
                                   "num_turns": 2, "usage": {"total_tokens": 9}}},
]

FAKE = r"""#!/usr/bin/env python3
import json, os, sys
d = os.environ["RELAY_FAKE_DIR"]
name = os.path.basename(sys.argv[0])
with open(os.path.join(d, name + ".argv"), "a") as fh:
    fh.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\n")
sys.stderr.write(os.environ.get("RELAY_FAKE_STDERR", ""))
sys.stdout.write(open(os.path.join(d, name + ".out")).read())
sys.exit(int(os.environ.get("RELAY_FAKE_RC", "0")))
"""


def fake_bins(tmp: Path, **outs) -> None:
    """가짜 claude·codex·agy 를 만들고 환경 변수로 가리킨다. `outs[이름]` = 그 실행 파일이 찍을 줄 목록."""
    for name in A.AGENTS:
        p = tmp / name
        p.write_text(FAKE, encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
        lines = outs.get(name, [])
        (tmp / f"{name}.out").write_text("".join((x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)) + "\n"
                                                 for x in lines), encoding="utf-8")
        os.environ[f"AX_RELAY_{name.upper()}_BIN"] = str(p)
    os.environ["RELAY_FAKE_DIR"] = str(tmp)
    os.environ.pop("RELAY_FAKE_RC", None)
    os.environ.pop("RELAY_FAKE_STDERR", None)
    os.environ.pop("AX_RELAY_AGY_MODEL", None)


def argv_of(tmp: Path, name: str) -> list:
    return [json.loads(x) for x in (tmp / f"{name}.argv").read_text(encoding="utf-8").splitlines()]


def kinds(evs) -> list:
    return [e["kind"] for e in evs if e["kind"] not in ("meta", "delta")]


def t_agents_build_cmd(tmp):
    fake_bins(tmp)
    c, sid = A.build_cmd("claude", "안녕")
    check("claude 새 세션은 호출자가 ID 를 정한다", sid and c[-3:] == ["--session-id", sid, "안녕"]
          and "--dangerously-skip-permissions" in c and c[1:5] == ["-p", "--output-format", "stream-json", "--verbose"], str(c))
    c, sid = A.build_cmd("claude", "안녕", "S1")
    check("claude 이어가기", sid == "" and c[-3:] == ["--resume", "S1", "안녕"], str(c))
    c, _ = A.build_cmd("codex", "안녕")
    check("codex 새 세션", c[1:] == ["exec", "--json", "--dangerously-bypass-approvals-and-sandbox", "안녕"], str(c))
    c, _ = A.build_cmd("codex", "안녕", "T1")
    check("codex 이어가기", c[1:] == ["exec", "resume", "--json", "--dangerously-bypass-approvals-and-sandbox", "T1", "안녕"], str(c))
    c, _ = A.build_cmd("agy", "안녕", "G1")
    check("agy 는 입력을 -p= 에 붙인다", c[-1] == "-p=안녕" and c[-3:-1] == ["--conversation", "G1"]
          and "-p" not in c, str(c))
    os.environ["AX_RELAY_AGY_MODEL"] = "m-x"
    c, _ = A.build_cmd("agy", "안녕")
    check("agy 모델 지정", c[c.index("--model") + 1] == "m-x" and "--conversation" not in c, str(c))
    os.environ.pop("AX_RELAY_AGY_MODEL")
    check("- 로 시작하는 입력은 옵션으로 읽히지 않게", A.build_cmd("codex", "-x")[0][-1] == " -x")
    try:
        A.build_cmd("gpt", "x")
        check("모르는 에이전트 거절", False, "예외 없음")
    except ValueError:
        check("모르는 에이전트 거절", True)


def _run(tmp, agent, **kw):
    evs, dbg, raw = [], [], []
    r = A.run(agent, "입력", cwd=str(tmp), on_event=evs.append, dbg=lambda w, m: dbg.append(f"[{w}] {m}"),
              raw_sink=raw.append, **kw)
    return r, evs, dbg, raw


def t_agents_claude(tmp):
    fake_bins(tmp, claude=CLAUDE_LINES)
    r, evs, dbg, raw = _run(tmp, "claude")
    check("claude 성공", r.ok and r.rc == 0 and r.session == "c-1" and r.text == "끝났습니다", str(r))
    check("claude 이벤트 순서", kinds(evs) == ["system", "tool_call", "tool_result", "agent_text", "raw", "result"], str(kinds(evs)))
    tc = [e for e in evs if e["kind"] == "tool_call"][0]
    check("도구 호출 내용", tc["text"] == "Bash" and tc["data"]["input"] == {"command": "echo relay-ok"})
    check("도구 결과 내용", [e for e in evs if e["kind"] == "tool_result"][0]["text"] == "relay-ok")
    check("모르는 이벤트는 원문 보존 + 디버그", [e for e in evs if e["kind"] == "raw"][0]["data"] == {"type": "brand_new_event", "x": 1}
          and any("모르는 이벤트 claude.brand_new_event" in x for x in dbg))
    check("usage", r.usage == {"input_tokens": 5, "output_tokens": 7})
    check("받은 줄 원문 전부 보관", len(raw) == len(CLAUDE_LINES))
    check("디버그에 실행·끝 기록", any("claude 실행" in x for x in dbg) and any("claude 끝 — rc=0" in x for x in dbg))
    check("디버그에 입력 본문을 싣지 않는다", not any('"입력"' in x for x in dbg))
    a = argv_of(tmp, "claude")[0]
    check("새 세션 인자", "--session-id" in a and a[-1] == "입력", str(a))
    _run(tmp, "claude", session="c-1")
    a2 = argv_of(tmp, "claude")[1]
    check("이어가기 인자", a2[-3:] == ["--resume", "c-1", "입력"], str(a2))


def t_agents_codex(tmp):
    fake_bins(tmp, codex=CODEX_LINES)
    r, evs, dbg, raw = _run(tmp, "codex")
    check("codex 성공", r.ok and r.session == "x-1" and r.text == "ZEBRA-17", str(r))
    check("codex 이벤트 순서", kinds(evs) == ["system", "tool_call", "tool_result", "agent_text", "result"], str(kinds(evs)))
    tr = [e for e in evs if e["kind"] == "tool_result"][0]
    check("명령 결과·종료 코드", tr["text"] == "relay-ok\n" and tr["data"]["exit_code"] == 0 and tr["data"]["is_error"] is False)
    _run(tmp, "codex", session="x-1")
    check("codex 이어가기 인자", argv_of(tmp, "codex")[1][:2] == ["exec", "resume"] and argv_of(tmp, "codex")[1][-2:] == ["x-1", "입력"])
    fake_bins(tmp, codex=[{"type": "thread.started", "thread_id": "x-2"},
                          {"type": "turn.failed", "error": {"message": "usage limit reached"}}])
    r, evs, dbg, _ = _run(tmp, "codex")
    check("codex 실패 이벤트", not r.ok and "usage limit reached" in r.error and kinds(evs)[-1] == "error", str(r.error))
    check("실패해도 세션 ID 는 남는다", r.session == "x-2")


def t_agents_agy(tmp):
    fake_bins(tmp, agy=AGY_LINES)
    r, evs, dbg, raw = _run(tmp, "agy")
    check("agy 성공", r.ok and r.session == "g-1" and r.text == "ZEBRA-17\n", str(r))
    check("agy 이벤트 순서", kinds(evs) == ["system", "tool_call", "tool_result", "agent_text", "result"], str(kinds(evs)))
    check("조각은 delta 로 흘리고 끝에 한 번 합친다", [e["text"] for e in evs if e["kind"] == "delta"] == ["ZEBRA", "-17\n"]
          and [e["text"] for e in evs if e["kind"] == "agent_text"] == ["ZEBRA-17"])
    check("도구 결과", [e for e in evs if e["kind"] == "tool_result"][0]["text"] == "relay-ok\r\n")
    check("agy 인자", argv_of(tmp, "agy")[0][-1] == "-p=입력")


def t_agents_failures(tmp):
    fake_bins(tmp, claude=["이건 json 이 아니다", CLAUDE_LINES[0], "[1,2]"])
    os.environ["RELAY_FAKE_RC"] = "3"
    os.environ["RELAY_FAKE_STDERR"] = "boom: not logged in\n"
    r, evs, dbg, raw = _run(tmp, "claude")
    check("종료 코드 실패", not r.ok and r.rc == 3 and "종료 코드 3" in r.error and "not logged in" in r.error, r.error)
    check("해석 못 한 줄 수", r.unparsed == 2, str(r.unparsed))
    check("해석 못 한 줄도 이벤트로 남긴다", [e["data"]["line"] for e in evs if e["text"] == "claude.unparsed"] == ["이건 json 이 아니다", "[1,2]"])
    check("오류 출력이 디버그에 남는다", any("agents.stderr" in x and "not logged in" in x for x in dbg))
    check("해석 실패가 디버그에 남는다", sum("해석 못 한 줄" in x for x in dbg) == 2)
    os.environ.pop("RELAY_FAKE_RC")
    os.environ.pop("RELAY_FAKE_STDERR")
    os.environ["AX_RELAY_CODEX_BIN"] = str(tmp / "없는실행파일")
    r, evs, dbg, _ = _run(tmp, "codex")
    check("실행 파일 없음", not r.ok and "실행하지 못했다" in r.error and any("기동 실패" in x for x in dbg), r.error)
    big = "가" * (A.RESULT_CAP + 50)
    fake_bins(tmp, codex=[{"type": "item.completed", "item": {"id": "i", "type": "command_execution",
                                                             "aggregated_output": big, "exit_code": 1}}])
    r, evs, _, _ = _run(tmp, "codex")
    tr = evs[0]
    check("큰 결과는 자르고 표시한다", len(tr["text"]) == A.RESULT_CAP and tr["data"]["truncated"] is True
          and tr["data"]["full_chars"] == len(big) and tr["data"]["is_error"] is True)


# ── 작업 경계 (T4) ───────────────────────────────────────────────────────────

def mk_boundary(tmp, *, issues=None, active=None, lock_error=None, list_error=""):
    issues = issues or {}
    logs = []
    def lister():
        return {"error": list_error} if list_error else {"issues": [{"id": k, **v} for k, v in issues.items()]}
    def getter(n):
        return dict(issues[int(n)], id=int(n)) if int(n) in issues else {"error": f"#{n} 없음 (404)"}
    def lock_current():
        if lock_error:
            raise RuntimeError(lock_error)
        return {"issue_id": active, "state": "active"} if active else None
    (tmp / "reports").mkdir(exist_ok=True)
    b = B.AxIssueBoundary(lister=lister, getter=getter, lock_current=lock_current, reports_dir=tmp / "reports",
                          dbg=lambda w, m: logs.append(f"[{w}] {m}"))
    return b, logs


def t_boundary_open(tmp):
    iss = {7: {"subject": "일곱", "status": "신규"}, 8: {"subject": "여덟", "status": "진행"},
           9: {"subject": "아홉", "status": "완료"}}
    b, logs = mk_boundary(tmp, issues=iss, active=8)
    c = b.candidates()
    check("후보 목록 + 활성 표시", c["ok"] and [(x["id"], x["active"]) for x in c["issues"]] == [(7, False), (8, True), (9, False)], str(c))
    r = b.may_open(7)
    check("다른 일감이 작업 중이면 거절", not r["ok"] and "#8 작업이 진행 중" in r["why"], str(r))
    check("작업 중인 그 일감은 연다", b.may_open(8)["ok"])
    b2, _ = mk_boundary(tmp, issues=iss)
    check("잠금이 비었으면 연다", b2.may_open(7)["ok"] and b2.may_open(7)["subject"] == "일곱")
    check("완료된 일감은 열지 않는다", not b2.may_open(9)["ok"] and "이미" in b2.may_open(9)["why"])
    check("없는 일감 거절", not b2.may_open(99)["ok"] and "조회 실패" in b2.may_open(99)["why"])
    b3, logs3 = mk_boundary(tmp, issues=iss, lock_error="파일 깨짐")
    r = b3.may_open(7)
    check("잠금 조회 실패는 거절 + 사유", not r["ok"] and "일감 잠금 조회 실패" in r["why"] and "파일 깨짐" in r["why"], str(r))
    check("판정이 디버그에 남는다", any("boundary.may_open" in x and "거절" in x for x in logs3))
    b4, _ = mk_boundary(tmp, list_error="HTTP 500")
    check("목록 조회 실패", not b4.candidates()["ok"] and "HTTP 500" in b4.candidates()["why"])


def t_boundary_closable(tmp):
    iss = {7: {"subject": "일곱", "status": "완료"}, 8: {"subject": "여덟", "status": "진행"}}
    b, logs = mk_boundary(tmp, issues=iss)
    r = b.closable(7)
    check("보고서 없으면 거절", not r["ok"] and "작업 보고서가 없다" in r["why"], str(r))
    (tmp / "reports" / "180-7-something.md").write_text("x", encoding="utf-8")
    (tmp / "reports" / "181-77-other.md").write_text("x", encoding="utf-8")
    r = b.closable(7)
    check("완료 + 보고서 + 잠금 해제 → 마무리 가능", r["ok"] and len(r["reports"]) == 1 and r["reports"][0].endswith("180-7-something.md"), str(r))
    (tmp / "reports" / "182-8-x.md").write_text("x", encoding="utf-8")
    r = b.closable(8)
    check("완료가 아니면 거절", not r["ok"] and "「진행」" in r["why"], str(r))
    b2, _ = mk_boundary(tmp, issues=iss, active=7)
    r = b2.closable(7)
    check("잠금이 활성이면 거절", not r["ok"] and "잠금이 아직 활성" in r["why"], str(r))
    b3, _ = mk_boundary(tmp, issues=iss, lock_error="읽기 실패")
    check("잠금 조회 실패면 거절", not b3.closable(7)["ok"] and "읽기 실패" in b3.closable(7)["why"])
    check("없는 일감 거절", not b.closable(99)["ok"])
    check("판정이 디버그에 남는다", any("boundary.closable" in x and "마무리 가능" in x for x in logs))

TESTS = [t_store_open_and_seq, t_store_concurrent_append, t_store_agent_state,
         t_store_corrupt_not_overwritten, t_store_archive,
         t_agents_build_cmd, t_agents_claude, t_agents_codex, t_agents_agy, t_agents_failures,
         t_boundary_open, t_boundary_closable]


def main() -> int:
    for fn in TESTS:
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_relay: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
