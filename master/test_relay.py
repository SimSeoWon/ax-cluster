"""relay(`#942`) 계약 테스트 — 세션 저장소 · 에이전트 호출부 · 작업 경계 · 콘솔.

임시 디렉터리와 가짜 실행 파일만 쓴다 — 실제 CLI·Redmine·일감 잠금을 건드리지 않는다.
실행: .venv/bin/python master/test_relay.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


TESTS = [t_store_open_and_seq, t_store_concurrent_append, t_store_agent_state,
         t_store_corrupt_not_overwritten, t_store_archive]


def main() -> int:
    for fn in TESTS:
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_relay: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
