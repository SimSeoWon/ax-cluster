"""`work/workmodel.py` 계약 테스트 (`#363` 1단계) — 조각 4상태 · 실패 종류 · 권고.

[중요] 상태 값은 큐 코드(`task_queue/logic_*.py`·`reclaim.py`)가 실제로 쓰는 것 전부를 잰다.
사유 문구는 큐·`infer`·`layer1` 이 실제로 쓰는 모양(실측 #734 의 `last_feedback` 포함)으로 만든다.
네트워크·실제 큐를 쓰지 않는다 — `Work.load` 는 `fetch` 주입으로 잰다.

실행: .venv/bin/python -B master/test_workmodel.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import branch_names as BN   # noqa: E402
from master.work import revise as RV         # noqa: E402
from master.work import workmodel as WM      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# 실측 #734 (2026-10-11 12:26) — 두 조각의 `last_feedback` 원문 모양
FB_734_A = ("[fp:f703f2c105b0] [중요] 층1 — 층1 이 막았다 — 커밋하지 않는다 — 층1 위반 1: "
            "master/projects/mcp_server.py: 동결 위반 — 동결 인터페이스 변경/삭제: "
            "def get_code(task_id: str, instruction: str, target_file: str='', project: str='') -> str")
FB_734_B = ("[fp:73785f4413c3] [중요] 층1 — 층1 이 막았다 — 커밋하지 않는다 — 층1 위반 1: "
            "master/work/generate.py: 동결 위반 — 동결 인터페이스 변경/삭제: class Dispatch(); "
            "def Dispatch.code(self) -> str; def Dispatch.ok(self) -> bool 외 2")
FB_STUB = ("[fp:0123456789ab] [중요] 층1 — 층1 이 막았다 — 커밋하지 않는다 — 층1 위반 1: "
           "master/work/x.py: 본문이 안 채워졌다 (스텁 그대로) — f")


def T(**kw) -> WM.Task:
    return WM.Task(dict(kw))


def kind_of(task: WM.Task, peers: int = 0) -> str:
    return task.classify(peers_frozen=peers)[0]


def test_state_mapping():
    table = {"pending": ("대기", False), "claimed": ("작업중", False), "submitted": ("작업중", False),
             "verified": ("성공", False), "failed": ("실패", False), "cancelled": ("실패", False),
             "needs_revision": ("실패", True), "stuck": ("실패", False)}
    for st, (want, retry) in table.items():
        t = T(task_id="a", status=st, attempt_count=1)
        check(f"상태 {st} → {want}", t.state == want and t.retryable is retry and t.known,
              f"{t.state} {t.retryable}")
    check("큐 코드의 상태 전부를 다룬다", set(WM.STATUS_STATE) == set(table))
    for st in ("weird", ""):
        t = T(task_id="a", status=st)
        check(f"[중요] 미상 상태 `{st}` → 미상 (대기로 접지 않는다)",
              t.state == "미상" and not t.known and t.state != "대기", t.state)
        check(f"미상 상태 `{st}` → kind unknown", kind_of(t) == "unknown")
    t = T(task_id="a", status="needs_revision", attempt_count=2)
    check("재시도 예정 라벨 n/MAX", t.state_label == f"실패·재시도 예정 (시도 2/{RV.MAX_ATTEMPTS})", t.state_label)
    check("MAX 는 revise 값", WM.MAX_ATTEMPTS == RV.MAX_ATTEMPTS == 3)
    for st in ("pending", "claimed", "submitted", "verified"):
        check(f"실패 아닌 {st} → 종류 없음", T(task_id="a", status=st).classify() == ("", ""))


def test_reason_keys():
    t = T(status="failed", fail_reason="BLOCKED", fail_detail="층1 위반", last_feedback="옛")
    check("failed 사유 = fail_reason — fail_detail", t.reason == "BLOCKED — 층1 위반", t.reason)
    check("cancelled 사유 = cancel_reason", T(status="cancelled", cancel_reason="c", last_feedback="x").reason == "c")
    check("needs_revision 사유 = last_feedback", T(status="needs_revision", last_feedback="f").reason == "f")
    check("옛 키 폴백", T(status="failed", failure="옛 사유").reason == "옛 사유")
    check("worker: worker_id 없으면 assignee", T(worker_id=None, assignee="192.168.0.2").worker == "192.168.0.2")


def test_kinds():
    # code — 첫 단일 동결 위반 · 스텁 · terminal 층1
    check("needs_revision 첫 동결 위반 1건 → code",
          kind_of(T(status="needs_revision", attempt_count=1, last_feedback=FB_734_A), peers=1) == "code")
    check("needs_revision 스텁 → code",
          kind_of(T(status="needs_revision", attempt_count=2, last_feedback=FB_STUB), peers=0) == "code")
    check("failed 층1 시도 1 (피드백 못 실음) → code",
          kind_of(T(status="failed", attempt_count=1, fail_reason="BLOCKED", fail_detail=FB_STUB)) == "code")
    # quota · environment · auth — revise 표지 그대로
    check("quota (429 + limit)", kind_of(T(status="failed", attempt_count=1, fail_reason="BLOCKED",
                                           fail_detail="429 You've hit your session limit")) == "quota")
    check("environment (0xC0000142)", kind_of(T(
        status="failed", attempt_count=1, fail_reason="BLOCKED",
        fail_detail="[fp:aaaaaaaaaaaa] codex runner exited 0xC0000142")) == "environment")
    check("auth (OAuth 만료 문구)", kind_of(T(
        status="failed", attempt_count=1, fail_reason="BLOCKED",
        fail_detail="Claude 인증 확인 실패 @192.168.0.2: Failed to authenticate: OAuth session expired "
                    "and could not be refreshed")) == "auth")
    check("auth (AX 사전 검사 표식)", kind_of(T(status="failed", attempt_count=1, fail_reason="BLOCKED",
                                              fail_detail="AX_CLAUDE_AUTH_FAILED")) == "auth")
    # repeat — fail_detail 지문 == 직전 last_feedback 지문
    rep = T(status="failed", attempt_count=2, fail_reason="BLOCKED",
            fail_detail="[fp:abcdefabcdef] RESULT: BLOCKED 승인 필요",
            last_feedback="[fp:abcdefabcdef] RESULT: BLOCKED 승인 필요")
    check("repeat — 같은 지문", kind_of(rep) == "repeat", str(rep.classify()))
    diff = T(status="failed", attempt_count=1, fail_reason="BLOCKED",
             fail_detail="[fp:abcdefabcdef] RESULT: BLOCKED", last_feedback="[fp:111111111111] x")
    check("[중요] `[fp:` 접두만으로는 repeat 아님 (모든 실패에 붙는다)", kind_of(diff) != "repeat", kind_of(diff))
    # cap
    check("cap — failed 시도 3 · 비동결", kind_of(T(status="failed", attempt_count=3, fail_reason="BLOCKED",
                                                  fail_detail=FB_STUB)) == "cap")
    check("cap — verify:reject 시도 3", kind_of(T(status="failed", attempt_count=3,
                                                fail_reason="verify:reject", fail_detail="층2 차단")) == "cap")
    # cancelled
    c = T(status="cancelled", cancel_reason="사용자: 골조 설계 결함", last_feedback=FB_734_A, attempt_count=1)
    check("cancelled — 사람 취소 (동결 위반 피드백이 남아도)", kind_of(c, peers=2) == "cancelled"
          and "골조 설계 결함" in c.classify()[1], str(c.classify()))
    check("cancelled — no_work", T(status="cancelled", no_work=True).classify()[1].startswith("할 일 없음"))
    check("cancelled — requester_handoff",
          "requester_handoff" in T(status="cancelled", requester_handoff=True).classify()[1])
    # unknown
    check("unknown — failed 표지 없음 시도 1", kind_of(T(status="failed", attempt_count=1,
                                                      fail_reason="파견 실패", fail_detail="ssh timeout")) == "unknown")
    st = T(status="stuck", reclaim_count=4)
    check("unknown — stuck (큐가 다시 집지 않는다)", kind_of(st) == "unknown" and "stuck" in st.classify()[1])


def test_skeleton_rule():
    one = T(status="needs_revision", attempt_count=1, last_feedback=FB_734_A)
    check("[중요] 단일 첫 동결 위반 → code (워커 실수)", kind_of(one, peers=1) == "code")
    again = T(status="needs_revision", attempt_count=2, last_feedback=FB_734_A)
    check("[중요] 같은 조각 시도 2 에도 동결 위반 → skeleton", kind_of(again, peers=1) == "skeleton",
          str(again.classify(peers_frozen=1)))
    capped = T(status="failed", attempt_count=3, fail_reason="BLOCKED", fail_detail=FB_734_A)
    check("동결 위반 상한 도달 → cap 보다 skeleton", kind_of(capped, peers=1) == "skeleton")
    check("[중요] 같은 라운드 동결 위반 2건 → skeleton", kind_of(one, peers=2) == "skeleton")
    stub2 = T(status="needs_revision", attempt_count=2, last_feedback=FB_STUB)
    check("시도 2 라도 동결 위반이 아니면 code", kind_of(stub2, peers=2) == "code")
    check("frozen 은 막힌 상태만", not T(status="cancelled", cancel_reason="동결 위반").frozen
          and one.frozen)
    why = again.classify(peers_frozen=1)[1]
    check("skeleton 근거 문구", "재할당·재시도로 고칠 수 없다 — 골조 변경 결정 필요" in why, why)


def _work(tasks, **w):
    base = {"work_id": "20261011_1224_734_x_e2c2b8e6", "project": "AXCluster", "round": 1,
            "merge_status": "in_progress"}
    base.update(w)
    return WM.Work.from_record(base, tasks)


def test_decide_actions():
    tasks = [
        {"task_id": "a", "status": "needs_revision", "round": 1, "attempt_count": 1, "last_feedback": FB_STUB},
        {"task_id": "b", "status": "failed", "round": 1, "attempt_count": 1, "fail_reason": "BLOCKED",
         "fail_detail": "codex 0xC0000142"},
        {"task_id": "c", "status": "failed", "round": 1, "attempt_count": 1, "fail_reason": "BLOCKED",
         "fail_detail": "AX_CLAUDE_AUTH_FAILED"},
        {"task_id": "d", "status": "failed", "round": 1, "attempt_count": 2, "fail_reason": "BLOCKED",
         "fail_detail": "[fp:abcdefabcdef] x", "last_feedback": "[fp:abcdefabcdef] x"},
        {"task_id": "e", "status": "failed", "round": 1, "attempt_count": 3, "fail_reason": "BLOCKED",
         "fail_detail": FB_STUB},
        {"task_id": "f", "status": "cancelled", "round": 1, "cancel_reason": "사람"},
        {"task_id": "g", "status": "claimed", "round": 1, "worker_id": "192.168.0.43"},
        {"task_id": "h", "status": "verified", "round": 1},
        {"task_id": "i", "status": "pending", "round": 1},
        {"task_id": "j", "status": "mystery", "round": 1},
        {"task_id": "k", "status": "failed", "round": 1, "attempt_count": 1, "fail_reason": "BLOCKED",
         "fail_detail": "rate limit reached — quota"},
    ]
    before = copy.deepcopy(tasks)
    w = _work(tasks)
    got = {d["task_id"]: (d["kind"], d["action"]) for d in w.decide()}
    want = {"a": ("code", "retry"), "b": ("environment", "reassign"), "c": ("auth", "notify_human"),
            "d": ("repeat", "stop"), "e": ("cap", "notify_human"), "f": ("cancelled", "none"),
            "g": ("", "none"), "h": ("", "none"), "i": ("", "none"), "j": ("unknown", "notify_human"),
            "k": ("quota", "reassign")}
    for tid, exp in want.items():
        check(f"decide {tid} → {exp}", got.get(tid) == exp, str(got.get(tid)))
    check("decide 항목 모양", all(set(d) == {"task_id", "state", "kind", "action", "reason"} for d in w.decide()))
    check("[중요] decide 는 읽기 전용 (원본 dict 불변)", tasks == before)
    for d in w.decide():
        for bad in ("하세요", "하라", "해라", "실행하"):
            if bad in d["reason"]:
                check(f"권고 근거에 명령형 `{bad}` 없음 ({d['task_id']})", False, d["reason"])
    c = w.counts()
    check("counts 4상태 + 미상", c == {"대기": 1, "작업중": 1, "성공": 1, "실패": 7, "미상": 1}, str(c))
    check("blocked = 실패 조각", [t.task_id for t in w.blocked()] == ["a", "b", "c", "d", "e", "f", "k"])
    check("running = 작업중", [t.task_id for t in w.running()] == ["g"])
    check("unknown 조각", [t.task_id for t in w.unknown()] == ["j"])


def test_round_filtering():
    tasks = [{"task_id": "r1a", "status": "failed", "round": 1, "attempt_count": 1, "fail_reason": "x"},
             {"task_id": "r2a", "status": "claimed", "round": 2},
             {"task_id": "r2b", "status": "needs_revision", "round": 2, "attempt_count": 1,
              "last_feedback": FB_734_A},
             {"task_id": "r2c", "status": "needs_revision", "round": 2, "attempt_count": 1,
              "last_feedback": FB_734_B}]
    w = _work(tasks, round=2)
    check("round_tasks 기본 = 지금 라운드", [t.task_id for t in w.round_tasks()] == ["r2a", "r2b", "r2c"])
    check("round_tasks(1)", [t.task_id for t in w.round_tasks(1)] == ["r1a"])
    check("counts 는 지금 라운드만", w.counts() == {"대기": 0, "작업중": 1, "성공": 0, "실패": 2}, str(w.counts()))
    check("decide 는 지금 라운드만", [d["task_id"] for d in w.decide()] == ["r2a", "r2b", "r2c"])
    check("[중요] 지난 라운드 동결 위반은 이번 라운드 동시 위반에 안 센다 · 이번 라운드 2건 → skeleton",
          [d["kind"] for d in w.decide()] == ["", "skeleton", "skeleton"], str(w.decide()))
    old = _work([{"task_id": "x", "status": "verified"}, {"task_id": "y", "status": "pending"}], round=3)
    check("스탬프 없는 옛 레코드는 거르지 않는다", [t.task_id for t in old.round_tasks()] == ["x", "y"])
    mixed = _work([{"task_id": "x", "status": "verified", "round": 0},
                   {"task_id": "y", "status": "pending", "round": 1},
                   {"task_id": "z", "status": "pending", "round": 2}], round=2)
    check("round 0 은 지금 라운드에 포함 (advance_work 규칙)", [t.task_id for t in mixed.round_tasks()] == ["x", "z"])


def test_work_from_record_and_load():
    wid = "20261011_1224_734_mcp_get_code_generatedispatch_e2c2b8e6"
    w = WM.Work.from_record({"work_id": wid, "project": "AXCluster", "round": "2", "merge_status": "cancelled",
                             "target_branch": "task/custom/base"}, [{"task_id": "t", "status": "pending"}])
    check("from_record 사실", (w.work_id, w.project, w.round, w.merge_status) == (wid, "AXCluster", 2, "cancelled"))
    check("base_branch: 저장된 target_branch 가 이긴다", w.base_branch == "task/custom/base", w.base_branch)
    w2 = WM.Work.from_record({"work_id": wid}, [])
    check("base_branch: 없으면 work_id 에서 유도 (branch_names)", w2.base_branch == BN.base_branch(wid),
          w2.base_branch)
    check("round 기본 1", w2.round == 1)
    check("from_record 는 원본을 복사한다", w.raw is not None and isinstance(w.tasks[0], WM.Task))
    calls = []

    def fetch(work_id, *, api=None):
        calls.append((work_id, api))
        return {"work_id": work_id, "round": 1}, [{"task_id": "t", "status": "verified", "round": 1}]
    lw = WM.Work.load(wid, api="API", fetch=fetch)
    check("load: fetch 주입·api 전달", calls == [(wid, "API")] and lw.counts()["성공"] == 1, str(calls))
    try:
        WM.Work.load("nope", fetch=lambda work_id, *, api=None: ({}, []))
        check("load: 없는 work → LookupError", False)
    except LookupError:
        check("load: 없는 work → LookupError", True)


def main() -> int:
    for fn in (test_state_mapping, test_reason_keys, test_kinds, test_skeleton_rule,
               test_decide_actions, test_round_filtering, test_work_from_record_and_load):
        fn()
    print(f"통과 {PASS} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
