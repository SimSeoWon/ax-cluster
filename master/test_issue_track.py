"""일감 마감 추적(`#884` T1) 계약 테스트 — [중요] **등록 검증·라운드·해시 전이 규칙·종결 판정·
깨진 상태 파일 보존·동시 갱신에서 유실이 없는가.**

임시 디렉토리만 쓴다 — 실 트윈 루트·Redmine·git·리뷰 큐를 건드리지 않는다.
실행: .venv/bin/python master/test_issue_track.py
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import issue_track as IT    # noqa: E402

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


def sha(i: int) -> str:
    return f"{i:040x}"


B, E = "b" * 40, "e" * 40


def reg(root, n=7, hashes=(1, 2, 3), base=B, end=E, **kw):
    return IT.register(root, n, project="AXCluster", base=base, end=end,
                       hashes=[sha(i) for i in hashes], **kw)


def t_register_validation(tmp):
    bad = [
        dict(issue_id=0, base=B, end=E, hashes=[sha(1)]),
        dict(issue_id="x", base=B, end=E, hashes=[sha(1)]),
        dict(issue_id=7, base="abc", end=E, hashes=[sha(1)]),
        dict(issue_id=7, base=B, end="", hashes=[sha(1)]),
        dict(issue_id=7, base=B, end=E, hashes=[]),
        dict(issue_id=7, base=B, end=E, hashes=["1234567"]),
        dict(issue_id=7, base=B, end=E, hashes=sha(1)),
    ]
    want = ["bad_issue", "bad_issue", "bad_sha", "bad_sha", "no_hashes", "bad_sha", "no_hashes"]
    for kw, w in zip(bad, want):
        n = kw.pop("issue_id")
        r = IT.register(tmp, n, project="AXCluster", **kw)
        check(f"검증 {w}", not r["ok"] and r["reason"] == w, str(r))
    r = IT.register(tmp, 7, project="", base=B, end=E, hashes=[sha(1)])
    check("project 비면 거절", not r["ok"] and r["reason"] == "bad_project", str(r))
    check("거절은 파일 안 만듦", not (tmp / IT.STATE_NAME).exists())
    logs = []
    r = IT.register(tmp, 7, project="AXCluster", base=B.upper(), end=E,
                    hashes=[sha(1).upper(), sha(2), sha(1)], by="t", logf=logs.append)
    check("등록 ok", r["ok"] and r["round"] == 1 and not r.get("already"), str(r))
    cur = IT.current(tmp, 7)
    check("소문자 정규화·중복 제거", [h["sha"] for h in cur["hashes"]] == [sha(1), sha(2)]
          and cur["base"] == B, str(cur))
    check("전부 waiting", all(h["state"] == "waiting" and h["noted"] is False and h["findings"] is None
                              for h in cur["hashes"]))
    check("summary waiting", cur["summary"]["state"] == "waiting" and cur["summary"]["noted"] is False)
    check("로그 한 줄", logs and logs[0].startswith("[issue_track] #7 register:"), str(logs))
    check("반환 log", r["log"] == logs)
    check("history", cur["history"] and cur["history"][-1]["op"] == "register")
    check("미등록 current → None", IT.current(tmp, 8) is None and IT.current(tmp / "none", 7) is None)


def t_idempotent(tmp):
    reg(tmp)
    r = reg(tmp)
    check("같은 범위 → already", r["ok"] and r.get("already") and r["round"] == 1, str(r))
    check("라운드 하나", len(IT.rounds(tmp, 7)) == 1)
    r = reg(tmp, hashes=(1, 2))
    check("같은 범위 다른 해시 → hashes_mismatch", not r["ok"] and r["reason"] == "hashes_mismatch", str(r))
    check("거절은 라운드 안 늘림", len(IT.rounds(tmp, 7)) == 1)


def t_new_round_and_cap(tmp):
    reg(tmp)
    IT.set_hash(tmp, 7, sha(1), state="done")
    r = reg(tmp, base=sha(100), end=sha(101), hashes=(9,))
    check("다른 범위 → 라운드 2", r["ok"] and r["round"] == 2, str(r))
    rs = IT.rounds(tmp, 7)
    check("옛 라운드 보존", len(rs) == 2 and rs[0]["hashes"][0]["state"] == "done", str(rs))
    check("current = 최신", IT.current(tmp, 7)["round"] == 2)
    for i in range(IT.ROUND_CAP + 3):
        reg(tmp, base=sha(200 + i), end=sha(300 + i), hashes=(i + 1,))
    rs = IT.rounds(tmp, 7)
    check("라운드 상한", len(rs) == IT.ROUND_CAP, str(len(rs)))
    check("번호는 단조 증가", rs[-1]["round"] == 2 + IT.ROUND_CAP + 3 and rs[0]["round"] == rs[-1]["round"] - IT.ROUND_CAP + 1,
          str([r["round"] for r in rs]))
    r = IT.set_hash(tmp, 7, sha(1), state="done", round=1)
    check("정리된 라운드 → no_round", not r["ok"] and r["reason"] == "no_round", str(r))


def t_transitions(tmp):
    reg(tmp, hashes=(1, 2, 3, 4))
    logs = []
    r = IT.set_hash(tmp, 7, sha(1), state="queued", serial="R12", logf=logs.append)
    check("waiting→queued", r["ok"] and r["hash"]["serial"] == "R12" and not r["all_terminal"], str(r))
    check("로그", logs and logs[0].startswith("[issue_track] #7 set_hash:") and "R12" in logs[0], str(logs))
    r = IT.set_hash(tmp, 7, sha(1), state="queued", serial="R13")
    check("queued→queued serial 갱신", r["ok"] and r["hash"]["serial"] == "R13", str(r))
    r = IT.set_hash(tmp, 7, sha(1), state="skipped")
    check("queued→skipped 거절", not r["ok"] and r["reason"] == "bad_transition" and r["state"] == "queued", str(r))
    r = IT.set_hash(tmp, 7, sha(1), state="done", findings=3)
    check("queued→done", r["ok"] and r["hash"]["findings"] == 3 and r["hash"]["serial"] == "R13", str(r))
    r = IT.set_hash(tmp, 7, sha(1), state="done")
    check("done→done already", r["ok"] and r.get("already"), str(r))
    r = IT.set_hash(tmp, 7, sha(1), state="abandoned")
    check("done→abandoned 거절", not r["ok"] and r["reason"] == "bad_transition", str(r))
    r = IT.set_hash(tmp, 7, sha(2), state="skipped", why="소스 변경 없음")
    check("waiting→skipped", r["ok"] and r["hash"]["why"] == "소스 변경 없음", str(r))
    r = IT.set_hash(tmp, 7, sha(3), state="abandoned", why="재시도 상한")
    check("waiting→abandoned", r["ok"], str(r))
    r = IT.set_hash(tmp, 7, sha(4), state="waiting")
    check("waiting 지정 거절", not r["ok"] and r["reason"] == "bad_state", str(r))
    r = IT.set_hash(tmp, 7, sha(4), state="bogus")
    check("모르는 상태 거절", not r["ok"] and r["reason"] == "bad_state", str(r))
    r = IT.set_hash(tmp, 7, sha(99), state="done")
    check("모르는 sha 거절", not r["ok"] and r["reason"] == "unknown_sha", str(r))
    r = IT.set_hash(tmp, 8, sha(1), state="done")
    check("미등록 일감 거절", not r["ok"] and r["reason"] == "not_registered", str(r))
    r = IT.set_hash(tmp, 7, sha(4).upper(), state="done")
    check("마지막 → all_terminal", r["ok"] and r["all_terminal"], str(r))


def t_terminal_pure(tmp):
    rnd = {"hashes": [{"sha": "a", "state": "done"}, {"sha": "b", "state": "abandoned"},
                      {"sha": "c", "state": "skipped"}]}
    check("섞인 종결 → True", IT.all_hashes_terminal(rnd) and IT.pending_hashes(rnd) == [])
    rnd["hashes"].append({"sha": "d", "state": "queued"})
    rnd["hashes"].append({"sha": "e", "state": "waiting"})
    check("미종결 있음 → False", not IT.all_hashes_terminal(rnd) and IT.pending_hashes(rnd) == ["d", "e"])
    check("빈 라운드 → False", not IT.all_hashes_terminal({"hashes": []}) and not IT.all_hashes_terminal(None))


def t_issue_of_hash(tmp):
    reg(tmp, n=7, hashes=(1, 2))
    reg(tmp, n=8, hashes=(2, 3), base=sha(50), end=sha(51))
    check("둘 다 열림 → 최신 등록 #8", IT.issue_of_hash(tmp, sha(2)) == 8)
    check("하나에만 → #7", IT.issue_of_hash(tmp, sha(1).upper()) == 7)
    check("없는 해시 → None", IT.issue_of_hash(tmp, sha(77)) is None)
    for s in (2, 3):
        IT.set_hash(tmp, 8, sha(s), state="skipped")
    IT.set_summary(tmp, 8, state="done", item_id="range:x", serial="R40")
    check("닫힌 라운드 무시 → #7", IT.issue_of_hash(tmp, sha(2)) == 7)
    check("닫힌 것만 → None", IT.issue_of_hash(tmp, sha(3)) is None)
    op = IT.open_rounds(tmp)
    check("open_rounds = #7 만", [(r["issue_id"], r["round"]) for r in op] == [(7, 1)], str(op))
    # 같은 일감 새 라운드 — 옛 라운드도 열려 있으면 둘 다 나오고, 해시는 최신 라운드로
    reg(tmp, n=7, hashes=(1,), base=sha(60), end=sha(61))
    op = IT.open_rounds(tmp)
    check("옛 라운드도 열림", [(r["issue_id"], r["round"]) for r in op] == [(7, 1), (7, 2)], str(op))
    check("빈 루트 open_rounds", IT.open_rounds(tmp / "none") == [] and IT.issue_of_hash(tmp / "none", sha(1)) is None)


def t_noted(tmp):
    reg(tmp, hashes=(1, 2))
    r = IT.mark_hash_noted(tmp, 7, sha(1))
    check("미종결 noted 거절", not r["ok"] and r["reason"] == "not_terminal", str(r))
    IT.set_hash(tmp, 7, sha(1), state="done", findings=0)
    r = IT.mark_hash_noted(tmp, 7, sha(1))
    check("종결 noted ok", r["ok"] and r["hash"]["noted"] is True, str(r))
    cur = IT.current(tmp, 7)
    check("noted 저장", cur["hashes"][0]["noted"] and not cur["hashes"][1]["noted"])
    r = IT.mark_hash_noted(tmp, 7, sha(2), noted=False)
    check("noted=False 는 언제나", r["ok"], str(r))
    r = IT.mark_hash_noted(tmp, 7, sha(9))
    check("모르는 sha", not r["ok"] and r["reason"] == "unknown_sha", str(r))


def t_summary(tmp):
    reg(tmp, hashes=(1, 2))
    r = IT.set_summary(tmp, 7, state="queued", item_id="range:7")
    check("해시 미종결 → hashes_pending", not r["ok"] and r["reason"] == "hashes_pending"
          and r["pending"] == [sha(1), sha(2)], str(r))
    r = IT.set_summary(tmp, 7, state="bogus")
    check("모르는 상태", not r["ok"] and r["reason"] == "bad_state", str(r))
    IT.set_hash(tmp, 7, sha(1), state="done")
    IT.set_hash(tmp, 7, sha(2), state="abandoned")
    logs = []
    r = IT.set_summary(tmp, 7, state="queued", item_id="range:7", serial="R50", logf=logs.append)
    check("queued ok", r["ok"] and r["summary"]["item_id"] == "range:7" and r["summary"]["serial"] == "R50", str(r))
    check("로그", logs and logs[0].startswith("[issue_track] #7 summary:"), str(logs))
    r = IT.set_summary(tmp, 7, state="queued")
    check("같은 상태 → already", r["ok"] and r.get("already"), str(r))
    r = IT.set_summary(tmp, 7, state="failed")
    check("queued→failed", r["ok"], str(r))
    check("failed 는 열림", [x["issue_id"] for x in IT.open_rounds(tmp)] == [7])
    r = IT.set_summary(tmp, 7, state="done", noted=True)
    check("done + noted", r["ok"] and r["summary"]["noted"] is True and r["summary"]["item_id"] == "range:7", str(r))
    r = IT.set_summary(tmp, 7, state="running")
    check("done→running 거절", not r["ok"] and r["reason"] == "closed", str(r))
    r = IT.set_summary(tmp, 7, state="done")
    check("done→done already", r["ok"] and r.get("already"), str(r))
    check("닫히면 open_rounds 에서 빠짐", IT.open_rounds(tmp) == [])
    r = IT.set_summary(tmp, 9, state="abandoned")
    check("미등록", not r["ok"] and r["reason"] == "not_registered", str(r))


def t_corrupt_not_overwritten(tmp):
    p = tmp / IT.STATE_NAME
    cases = [b"{not json", json.dumps({"schema": 99, "records": {}}).encode(),
             json.dumps({"schema": 1, "records": {"7": [{"issue_id": 8, "round": 1}]}}).encode(),
             json.dumps({"schema": 1, "records": []}).encode()]
    for i, raw in enumerate(cases):
        p.write_bytes(raw)
        for name, fn in (("register", lambda: reg(tmp)),
                         ("set_hash", lambda: IT.set_hash(tmp, 7, sha(1), state="done")),
                         ("current", lambda: IT.current(tmp, 7)),
                         ("open_rounds", lambda: IT.open_rounds(tmp))):
            try:
                fn()
                check(f"깨짐{i} {name} 예외", False, "예외 없음")
            except IT.IssueTrackError as e:
                check(f"깨짐{i} {name} 예외", "덮어쓰지 않았다" in str(e), str(e))
        check(f"깨짐{i} 바이트 그대로", p.read_bytes() == raw)


def _proc_set(root, i, q):
    try:
        r = IT.set_hash(root, 7, sha(i), state="done", findings=i)
        q.put((i, r["ok"]))
    except Exception as e:                              # noqa: BLE001
        q.put((i, f"{type(e).__name__}: {e}"))


def t_concurrent_processes(tmp):
    N = 16
    reg(tmp, hashes=range(1, N + 1))
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    ps = [ctx.Process(target=_proc_set, args=(str(tmp), i, q)) for i in range(1, N + 1)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(30)
    res = [q.get(timeout=5) for _ in ps]
    check("프로세스 전부 ok", all(ok is True for _, ok in res), str(res))
    cur = IT.current(tmp, 7)
    check("유실 없음", all(h["state"] == "done" and h["findings"] == int(h["sha"], 16) for h in cur["hashes"]),
          str([(h["sha"][-2:], h["state"]) for h in cur["hashes"]]))
    check("전부 종결", IT.all_hashes_terminal(cur))
    check("임시 파일 없음", not list(tmp.glob("*.tmp")))


def t_history_cap(tmp):
    reg(tmp, hashes=(1,))
    for i in range(IT.HISTORY_CAP + 5):
        IT.set_hash(tmp, 7, sha(1), state="queued", serial=f"R{i}")
    h = IT.current(tmp, 7)["history"]
    check("이력 상한", len(h) == IT.HISTORY_CAP, str(len(h)))
    check("최근 것이 남음", f"R{IT.HISTORY_CAP + 4}" in h[-1]["msg"], h[-1]["msg"])


def main() -> int:
    for fn in (t_register_validation, t_idempotent, t_new_round_and_cap, t_transitions, t_terminal_pure,
               t_issue_of_hash, t_noted, t_summary, t_corrupt_not_overwritten,
               t_concurrent_processes, t_history_cap):
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_track: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
