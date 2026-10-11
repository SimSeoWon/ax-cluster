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


def test_failure_decisions():
    task = {"task_id": "a", "round": 2, "attempt_count": 2, "last_feedback": FB_STUB}
    original = copy.deepcopy(task)
    cases = [
        ({"notes": ["AX_CLAUDE_AUTH_FAILED", "usage limit"]}, "auth", RV.REJECT),
        ({"notes": ["usage limit"]}, "quota", RV.REJECT),
        ({"notes": ["0xC0000142"]}, "environment", RV.REJECT),
        ({"notes": ["usage limit"], "stage": "층2"}, "code", RV.REVISE),
        ({"layer2_failure": "invalid judgement"}, "verification", RV.REJECT),
        ({}, "code", RV.REVISE),
    ]
    for kwargs, kind, verdict in cases:
        got = WM.decide_failure(task, issues=[FB_STUB], **kwargs)
        check(f"순수판정 {kind}", (got.kind, got.verdict) == (kind, verdict), str(got))
    got = WM.decide_failure(task, issues=[FB_734_A])
    check("시도2지만 직전스텁 → 첫동결은 code", got.kind == "code", str(got))
    prev = dict(task, last_feedback=FB_734_A)
    got = WM.decide_failure(prev, issues=[FB_734_A])
    check("직전동결 + 현재동결 → skeleton", got.kind == "skeleton" and got.verdict == RV.REJECT)
    notes = ["same"]
    prev = dict(task, last_feedback=RV.tag_detail(FB_734_A, RV.output_fingerprint(notes)))
    got = WM.decide_failure(prev, issues=[FB_734_A], notes=notes)
    check("동결반복은 fp반복보다 우선해 해당태스크만 종결", got.kind == "skeleton", str(got))
    decisions = [WM.decide_failure(dict(task, task_id=tid), issues=[FB_734_A]) for tid in ("a", "b")]
    check("동시 두조각 첫동결은 각각 재시도", all(d.kind == "code" and d.verdict == RV.REVISE for d in decisions))
    pending = T(status="pending", release_reason="quota_exhausted", release_detail=WM.failure_detail("usage limit", "quota"))
    check("pending 실패이력은 대기상태 유지", pending.state == WM.WAITING and pending.assignable)
    check("pending 저장종류는 재할당 권고", pending.recorded_failure_kind == "quota" and pending.classify()[0] == "quota")
    got = WM.decide_failure(dict(task, attempt_count=3), issues=[FB_STUB])
    check("일반상한 → cap", got.kind == "cap" and got.verdict == RV.REJECT)
    got = WM.decide_failure(dict(task, last_feedback=RV.tag_detail("x", RV.output_fingerprint(notes))),
                            issues=[FB_STUB], notes=notes)
    check("일반 fp반복 → repeat", got.kind == "repeat")
    detail = WM.failure_detail(FB_734_A, "code", "abcdefabcdef")
    check("종류 표지는 fp 접두 보존", RV.repeated_output(detail, "abcdefabcdef"))
    check("종류 저장표지는 레거시 attempt 추정보다 우선",
          T(status="needs_revision", attempt_count=3, last_feedback=detail).classify(peers_frozen=2)[0] == "code")
    for kind in WM.KINDS:
        tagged = WM.failure_detail("summary without markers", kind)
        check(f"저장표지 {kind} 복구", T(status="failed", fail_detail=tagged).classify()[0] == kind)
    check("판정은 입력을 수정하지 않는다", task == original)


def test_work_rework_after_other_tasks_finish():
    skeleton = {"task_id": "a", "status": "failed", "round": 1,
                "fail_detail": WM.failure_detail(FB_734_A, "skeleton")}
    success = {"task_id": "b", "status": "verified", "round": 1, "worker_id": "done-worker"}
    for st in ("pending", "needs_revision", "claimed", "submitted"):
        w = _work([skeleton, success, {"task_id": "c", "status": st, "round": 1}])
        check(f"다른 {st} 남으면 골조재작업 최종고지유예", not w.finished and not w.rework_required)
        check(f"{st}도 성공결과 보존", w.execution_summary()["successful_tasks"][0]["task_id"] == "b")
    for tasks in ([skeleton, success], [success, skeleton]):
        w = _work(tasks)
        summary = w.execution_summary()
        check("실행종결 후 골조 재작업 필요 순서무관", w.finished and w.rework_required)
        check("재작업 조각과 성공 조각 함께보존", [t["task_id"] for t in summary["rework_tasks"]] == ["a"]
              and [t["task_id"] for t in summary["successful_tasks"]] == ["b"])
    q = {"task_id": "quota", "status": "pending", "round": 1,
         "release_reason": "quota_exhausted", "release_detail": WM.failure_detail("quota", "quota")}
    w = _work([skeleton, q])
    check("한도재할당 대기 있으면 골조고지유예", len(w.assignable()) == 1 and not w.rework_required)
    check("quota대기 Work권고는 재할당", w.decide()[1]["action"] == "reassign")
    legacy = [dict(skeleton, fail_detail=FB_734_A, attempt_count=1),
              dict(skeleton, task_id="other", fail_detail=FB_734_B, attempt_count=1), success]
    check("종결시 레거시 동라운드동결 종합", _work(legacy).rework_required)
    tagged = [dict(skeleton, fail_detail=WM.failure_detail(FB_734_A, "code")),
              dict(skeleton, task_id="other", fail_detail=WM.failure_detail(FB_734_B, "code")), success]
    for tasks in (tagged, list(reversed(tagged))):
        w = _work(tasks)
        check("종결시 code표지첫동결2건은 Work골조판단 순서무관", w.rework_required and len(w.pending_rework()) == 2)
        check("Work종합해도 Task원래종류 code보존", all(t.recorded_failure_kind == "code" for t in w.pending_rework()))
    legacy_repeats = [dict(skeleton, fail_detail=FB_734_A, last_feedback=FB_734_A, attempt_count=1),
                      dict(skeleton, task_id="other", fail_detail=FB_734_B, last_feedback=FB_734_B, attempt_count=1), success]
    check("최종레거시동결repeat2건도골조종합", _work(legacy_repeats).rework_required)
    w = _work([dict(skeleton, target_files=["master/a.py", "master/b.py"]), success])
    p = w.rework_plan(integrated_head="merged-head", integrated_tree="/integrated-tree")
    check("다음골조계획은통합기준과라운드명시", p["integrated_head"] == "merged-head"
          and p["integrated_tree"] == "/integrated-tree" and p["next_round"] == 2)
    check("다음골조계획에실패대상과성공재사용", p["repairs"][0]["targets"] == ["master/a.py", "master/b.py"]
          and p["successful_tasks"] == ["b"])
    check("다음골조는전체취소또는수정후다음라운드사람선택", set(p["decision_options"]) == {"cancel_work", "fix_and_next_round"}
          and all(o["requires_confirmation"] for o in p["decision_options"].values()))


def test_parallel_continues_after_skeleton_failure():
    import threading
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch
    from master.work import infer as I, runner as R, wcommit as WC
    tasks = [{"task_id": tid, "work_id": "w", "round": 1, "status": "pending", "epoch": 7,
              "attempt_count": 2, "last_feedback": FB_734_A if tid == "a" else ""} for tid in ("a", "b", "c")]
    tasks_by_id = {t["task_id"]: t for t in tasks}
    workers = [SimpleNamespace(host=h, capabilities=[]) for h in ("one", "two")]
    queue_lock = threading.Lock()
    started = threading.Barrier(2)
    next_claimed = threading.Event()
    claimed_hosts = {}
    def claim(host, capabilities, **kw):
        with queue_lock:
            task = next((t for t in tasks if t["status"] == "pending"), None)
            if task:
                task.update(status="claimed", worker_id=host)
                claimed_hosts[task["task_id"]] = host
                if task["task_id"] == "c":
                    next_claimed.set()
            return task
    def api(method, path, body=None):
        if method == "POST" and path.endswith("/a/submit-fail"):
            tasks_by_id["a"].update(status="failed", fail_reason=body["reason"], fail_detail=body["detail"])
            return {"ok": True}
        raise AssertionError(f"예상밖 호출 {method} {path}")
    def dispatch(paths, facts, task, **kw):
        tid = task["task_id"]
        if tid in ("a", "b"):
            started.wait(timeout=3)
        if tid == "a":
            return I.commit_task(paths, facts, task, work_id="w", base="abc", want=[], branch="a", api=api)
        if tid == "b":
            if not next_claimed.wait(3):
                raise AssertionError("골조실패 워커가 다음태스크를 집지 않았다")
        task["status"] = "verified"
        return I.Response(task_id=tid, worker=facts.host, status=R.DONE)
    with ExitStack() as stack:
        stack.enter_context(patch.object(I, "prescreen_nowork"))
        stack.enter_context(patch.object(I, "_free_workers", return_value=(workers, [])))
        stack.enter_context(patch.object(R, "waiting_summary", return_value={"reclaimed": 0}))
        stack.enter_context(patch.object(R, "claim", side_effect=claim))
        stack.enter_context(patch.object(I, "dispatch_task", side_effect=dispatch))
        stack.enter_context(patch("master.work.twin_base.local_baseline", return_value={}))
        stack.enter_context(patch.object(WC, "run", return_value=WC.Committed(task_id="a", stage="층1",
            reason="동결 위반", layer1_violations=[FB_734_A])))
        stack.enter_context(patch("master.work.usage.record", return_value={"lane": "", "input_tokens": 0,
            "output_tokens": 0, "cost_known": False, "measured": False}))
        stack.enter_context(patch.object(I._MODE, "current", return_value=("codex", "test")))
        notice = stack.enter_context(patch.object(I, "_notify_blocked"))
        embed = stack.enter_context(patch.object(RV, "embed"))
        hand = I.run_many(SimpleNamespace(name="T", usage_log=Path("/unused")), limit=3,
                          facts=workers, clean=False, work_id="w", api=api)
    w = _work(tasks)
    check("골조실패 워커가 바로 다른태스크 처리", claimed_hosts.get("a") == claimed_hosts.get("c")
          and tasks_by_id["c"]["status"] == "verified", str(claimed_hosts))
    check("병렬 실행중 다른워커 성공결과 회수", tasks_by_id["b"]["status"] == "verified"
          and len(hand.items) == 3)
    check("골조태스크는 재시도/즉시고지 안함", not embed.called and not notice.called)
    check("모두소진후 Work골조재작업+성공보존", w.rework_required
          and [t["task_id"] for t in w.execution_summary()["successful_tasks"]] == ["b", "c"])


def test_stale_skeleton_does_not_change_queue_or_success():
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch
    from master.work import infer as I, wcommit as WC
    tasks = [{"task_id": "a", "status": "claimed", "round": 1, "epoch": 8, "worker_id": "new-owner"},
             {"task_id": "b", "status": "verified", "round": 1, "worker_id": "done-owner"}]
    before = copy.deepcopy(tasks)
    with ExitStack() as stack:
        stack.enter_context(patch("master.work.twin_base.local_baseline", return_value={}))
        stack.enter_context(patch.object(WC, "run", return_value=WC.Committed(task_id="a", stage="층1",
            reason="동결 위반", layer1_violations=[FB_734_A])))
        stack.enter_context(patch("master.work.usage.record", return_value={"lane": "", "input_tokens": 0,
            "output_tokens": 0, "cost_known": False, "measured": False}))
        stack.enter_context(patch.object(I._MODE, "current", return_value=("codex", "test")))
        notice = stack.enter_context(patch.object(I, "_notify_blocked"))
        result = I.commit_task(SimpleNamespace(usage_log=Path("/unused")), SimpleNamespace(host="old-owner"),
            {"task_id": "a", "attempt_count": 2, "epoch": 7, "last_feedback": FB_734_A},
            work_id="w", base="abc", want=[], branch="a", api=lambda *a: {"ok": False, "reason": "stale epoch"})
    check("epoch거절은 큐와다른성공증거 안바꿈", tasks == before and not _work(tasks).rework_required)
    check("epoch거절 골조즉시고지없음", not notice.called)


def main() -> int:
    for fn in (test_state_mapping, test_reason_keys, test_kinds, test_skeleton_rule,
               test_decide_actions, test_round_filtering, test_work_from_record_and_load,
               test_failure_decisions, test_work_rework_after_other_tasks_finish,
               test_parallel_continues_after_skeleton_failure, test_stale_skeleton_does_not_change_queue_or_success):
        fn()
    print(f"통과 {PASS} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
