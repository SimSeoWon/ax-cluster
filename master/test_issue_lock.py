"""일감 잠금(`#883` T1) 계약 테스트 — [중요] **활성 일감이 있으면 다른 일감을 시작하지 않는가,
보류가 잠금을 푸는가, 깨진 상태 파일을 덮어쓰지 않는가, 동시 시작에서 이기는 쪽이 하나인가.**

임시 디렉토리만 쓴다 — 실 트윈 루트·Redmine·git 을 건드리지 않는다.
실행: .venv/bin/python master/test_issue_lock.py
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import issue_lock as IL    # noqa: E402

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


def acq(root, n, **kw):
    return IL.acquire(root, n, branch=f"issue/{n}", start_rev=f"rev{n}" * 4, **kw)


def t_acquire_free(tmp):
    logs = []
    r = acq(tmp, 7, by="t", why="시작", logf=logs.append)
    check("빈 자리 → ok", r["ok"] and not r.get("already") and not r.get("resumed"), str(r))
    cur = IL.current(tmp)
    check("current = #7 active", cur and cur["issue_id"] == 7 and cur["state"] == "active"
          and cur["branch"] == "issue/7", str(cur))
    check("is_tracked #7", IL.is_tracked(tmp, 7) and not IL.is_tracked(tmp, 8))
    check("로그 한 줄", logs and logs[0].startswith("[issue_lock] #7 acquire:"), str(logs))
    data = json.loads((tmp / IL.STATE_NAME).read_text(encoding="utf-8"))
    check("이력 기록", data["history"][-1]["op"] == "acquire" and data["history"][-1]["by"] == "t")
    check("빈 루트 current → None", IL.current(tmp / "none") is None)


def t_same_issue_already(tmp):
    acq(tmp, 7)
    r = acq(tmp, 7)
    check("같은 일감 → already", r["ok"] and r.get("already"), str(r))


def t_busy_names_holder(tmp):
    acq(tmp, 7)
    logs = []
    r = acq(tmp, 8, logf=logs.append)
    check("다른 일감 → busy", not r["ok"] and r["reason"] == "busy" and r["holder"] == 7
          and r["state"] == "active", str(r))
    check("사유에 #7·보류·취소", "#7" in r["why"] and "보류" in r["why"] and "취소" in r["why"], r["why"])
    check("거절도 로그", logs and "거절(busy)" in logs[0], str(logs))
    check("거절은 상태를 안 바꿈", IL.current(tmp)["issue_id"] == 7 and not IL.is_tracked(tmp, 8))


def t_pause_cycle(tmp):
    acq(tmp, 7)
    r = IL.pause(tmp, 7, why="급한 일")
    check("pause ok", r["ok"] and r["record"]["state"] == "paused", str(r))
    check("pause → 활성 비움", IL.current(tmp) is None)
    check("pause → 추적 유지", IL.is_tracked(tmp, 7) and 7 in IL.paused(tmp))
    r = acq(tmp, 8)
    check("보류 중 다른 일감 시작 ok", r["ok"], str(r))
    r = acq(tmp, 7)
    check("#8 활성 동안 #7 재개 → busy", not r["ok"] and r["holder"] == 8, str(r))
    r = IL.release(tmp, 8, op="complete")
    check("#8 완료", r["ok"] and r["was"] == "active", str(r))
    check("#8 추적 해제", not IL.is_tracked(tmp, 8))
    r = acq(tmp, 7)
    check("#7 재개 → resumed", r["ok"] and r.get("resumed") and r["record"]["state"] == "active"
          and "paused_at" not in r["record"], str(r))
    check("재개는 원래 시작 리비전 유지", r["record"]["start_rev"] == "rev7" * 4)
    check("재개 → 보류 목록 비움", IL.paused(tmp) == {})
    ops = [h["op"] for h in json.loads((tmp / IL.STATE_NAME).read_text())["history"]]
    check("이력 순서", ops == ["acquire", "pause", "acquire", "complete", "resume"], str(ops))


def t_pause_refusals(tmp):
    r = IL.pause(tmp, 7)
    check("활성 없음 pause → 거절", not r["ok"] and r["reason"] == "not_active", str(r))
    acq(tmp, 7)
    r = IL.pause(tmp, 8)
    check("다른 일감 pause → 거절(holder)", not r["ok"] and r["holder"] == 7, str(r))


def t_release(tmp):
    r = IL.release(tmp, 9, op="complete")
    check("모르는 일감 release → 거절", not r["ok"] and r["reason"] == "not_tracked", str(r))
    acq(tmp, 9)
    r = IL.release(tmp, 9, op="close")
    check("op 잘못 → 거절", not r["ok"] and r["reason"] == "bad_op", str(r))
    check("op 잘못 → 상태 유지", IL.is_tracked(tmp, 9))
    r = IL.release(tmp, 9, op="finish", by="issue_flow.finish")
    check("finish op → 활성 해제 (#884 T5)", r["ok"] and r["was"] == "active" and r["op"] == "finish"
          and not IL.is_tracked(tmp, 9), str(r))
    check("finish 이력", IL._load(tmp)["history"][-1]["op"] == "finish")
    acq(tmp, 9)
    IL.pause(tmp, 9)
    r = IL.release(tmp, 9, op="cancel")
    check("보류 일감 cancel ok", r["ok"] and r["was"] == "paused", str(r))
    check("cancel 뒤 추적 없음", not IL.is_tracked(tmp, 9) and IL.current(tmp) is None)


def t_corrupt_not_overwritten(tmp):
    p = tmp / IL.STATE_NAME
    for body in ("{깨짐", json.dumps({"schema": 99, "active": None, "paused": {}, "history": []}),
                 json.dumps({"schema": 1, "active": {"issue_id": "x"}, "paused": {}, "history": []}),
                 json.dumps([1, 2])):
        p.write_text(body, encoding="utf-8")
        for name, fn in (("acquire", lambda: acq(tmp, 7)), ("current", lambda: IL.current(tmp)),
                         ("release", lambda: IL.release(tmp, 7, op="cancel"))):
            try:
                fn()
                raised = False
            except IL.IssueLockError:
                raised = True
            check(f"깨진 파일 {name} → IssueLockError ({body[:12]})", raised)
        check(f"깨진 파일 안 덮어씀 ({body[:12]})", p.read_text(encoding="utf-8") == body)


def _proc_acquire(root, n, q):
    q.put((n, acq(Path(root), n)["ok"]))


def t_concurrent_processes(tmp):
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    ps = [ctx.Process(target=_proc_acquire, args=(str(tmp), 100 + i, q)) for i in range(8)]
    for p in ps:
        p.start()
    res = [q.get(timeout=30) for _ in ps]
    for p in ps:
        p.join(timeout=30)
    winners = [n for n, ok in res if ok]
    check("프로세스 8개 동시 → 승자 하나", len(winners) == 1, str(res))
    cur = IL.current(tmp)
    check("승자 = current", cur and winners and cur["issue_id"] == winners[0], str(cur))


def t_concurrent_threads(tmp):
    res, lock = [], threading.Lock()

    def go(n):
        r = acq(tmp, n)
        with lock:
            res.append((n, r["ok"]))
    ts = [threading.Thread(target=go, args=(200 + i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    check("스레드 8개 동시 → 승자 하나", sum(ok for _, ok in res) == 1, str(res))


def t_history_cap(tmp):
    for i in range(IL.HISTORY_CAP):
        acq(tmp, 1)
        IL.pause(tmp, 1)
    data = json.loads((tmp / IL.STATE_NAME).read_text(encoding="utf-8"))
    check("이력 상한", len(data["history"]) == IL.HISTORY_CAP, str(len(data["history"])))
    check("최근 것이 남음", data["history"][-1]["op"] == "pause")


def main() -> int:
    for fn in (t_acquire_free, t_same_issue_already, t_busy_names_holder, t_pause_cycle,
               t_pause_refusals, t_release, t_corrupt_not_overwritten,
               t_concurrent_processes, t_concurrent_threads, t_history_cap):
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_lock: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
