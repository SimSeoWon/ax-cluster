"""플랜 거절 기록(`#864` T1) — [중요] **거절마다 정확히 한 줄, 성공·전송 실패는 0줄,
기록이 실패해도 거절 예외는 그대로인가.**

실 Redmine·실 트윈을 건드리지 않는다 — getter/updater 와 기록 경로를 주입한다.
실행: .venv/bin/python -B master/test_plan_events.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB     # noqa: E402
from master import plan_events as PE    # noqa: E402
from master import plan_state as PS     # noqa: E402
from master import plan_tools as PT     # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class FakeIssue:
    def __init__(self, body: str, answer: str = ""):
        self.body, self.answer, self.writes = body, answer, []

    def get(self, iid):
        return {"id": iid, "description": self.body}

    def update(self, iid, *, description, notes):
        self.writes.append(notes)
        if self.answer:
            return self.answer
        self.body = description
        return "ok"


def _plan_body(states=("대기", "대기")) -> str:
    tasks = [PB.Task("T1", states[0], "읽기", "a.py"),
             PB.Task("T2", states[1], "쓰기", "b.py", ["T1"])]
    return PB.append("## 스펙\n", tasks)


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _expect_reject(fn) -> BaseException | None:
    try:
        fn()
    except PB.PlanError as e:
        return e
    return None


def run() -> None:
    tmp = Path(tempfile.mkdtemp())
    log = tmp / "twin" / "plan_events.jsonl"

    def kw(fake):
        return {"getter": fake.get, "updater": fake.update, "events_path": log}

    # ① 허용되지 않는 전이 대기→완료
    f = FakeIssue(_plan_body())
    e = _expect_reject(lambda: PT.transition(864, "T1", "완료", "abc1234", **kw(f),
                                             caller="test"))
    rows = _lines(log)
    check("① 대기→완료 거절", isinstance(e, PS.TransitionError))
    check("① 한 줄", len(rows) == 1, str(rows))
    r = rows[-1] if rows else {}
    check("① 필드", r.get("op") == "transition" and r.get("issue_id") == 864
          and r.get("task_id") == "T1" and r.get("from") == "대기" and r.get("to") == "완료"
          and r.get("error_type") == "TransitionError" and r.get("kind") == "disallowed_transition"
          and r.get("note_present") is True and r.get("note_len") == 7
          and r.get("caller") == "test" and r.get("schema_version") == 1, str(r))
    check("① ts 에 시간대", "+" in r.get("ts", "") or r.get("ts", "").endswith("Z"), r.get("ts", ""))
    check("① 쓰기 없음", f.writes == [])

    # ② 선행 미완료 착수
    e = _expect_reject(lambda: PT.transition(864, "T2", "작업중", **kw(FakeIssue(_plan_body()))))
    r = _lines(log)[-1]
    check("② 선행 거절", isinstance(e, PS.TransitionError) and len(_lines(log)) == 2)
    check("② 종류·노트", r["kind"] == "unsettled_deps" and r["note_present"] is False
          and r["note_len"] == 0 and "caller" not in r, str(r))

    # ③ 근거 없는 완료
    e = _expect_reject(lambda: PT.transition(864, "T1", "완료", "  ",
                                             **kw(FakeIssue(_plan_body(("작업중", "대기"))))))
    r = _lines(log)[-1]
    check("③ 근거 거절", isinstance(e, PS.TransitionError) and r["kind"] == "missing_note"
          and r["from"] == "작업중" and len(_lines(log)) == 3, str(r))

    # ④ set_plan 이 상태·근거를 실음
    e = _expect_reject(lambda: PT.set_plan(864, [{"id": "T1", "goal": "g", "state": "완료"}],
                                           "왜", **kw(FakeIssue(_plan_body()))))
    r = _lines(log)[-1]
    check("④ set 거절", isinstance(e, PT.PlanToolError) and r["op"] == "set"
          and r["kind"] == "set_state_or_evidence" and r["tasks"] == ["T1"]
          and r["error_type"] == "PlanToolError" and len(_lines(log)) == 4, str(r))

    # ⑤ 플랜 영역 없음
    e = _expect_reject(lambda: PT.transition(864, "T1", "작업중", **kw(FakeIssue("## 스펙\n"))))
    r = _lines(log)[-1]
    check("⑤ 영역 없음", isinstance(e, PT.PlanToolError) and r["kind"] == "no_plan"
          and r["from"] == "" and len(_lines(log)) == 5, str(r))

    # ⑥ 성공은 0줄
    f = FakeIssue(_plan_body())
    out = PT.transition(864, "T1", "작업중", "시작", **kw(f))
    check("⑥ 성공", out["ok"] and len(_lines(log)) == 5)
    out = PT.set_plan(864, [{"id": "T1", "goal": "읽기"}, {"id": "T2", "goal": "쓰기",
                                                         "deps": ["T1"]}], "왜", **kw(f))
    check("⑥ set 성공 0줄", out["ok"] and len(_lines(log)) == 5)

    # ⑦ 전송 실패(읽기·쓰기)는 기록하지 않는다
    def bad_get(iid):
        return {"error": "HTTP 500"}
    e = _expect_reject(lambda: PT.transition(864, "T1", "작업중", getter=bad_get,
                                             updater=f.update, events_path=log))
    check("⑦ 읽기 실패 0줄", isinstance(e, PT.PlanTransportError) and len(_lines(log)) == 5)
    e = _expect_reject(lambda: PT.transition(864, "T1", "작업중", "x",
                                             **kw(FakeIssue(_plan_body(), answer="[주의] 실패"))))
    check("⑦ 쓰기 실패 0줄", isinstance(e, PT.PlanToolError) and len(_lines(log)) == 5)

    # ⑧ getter 를 주입하고 경로를 안 주면 기록하지 않는다(대역이 운영 기록을 오염시키지 않음)
    called = []
    orig = PE.record
    PE.record = lambda *a, **k: called.append(1) or True
    try:
        f = FakeIssue(_plan_body())
        _expect_reject(lambda: PT.transition(864, "T1", "완료", "x", getter=f.get, updater=f.update))
    finally:
        PE.record = orig
    check("⑧ 주입 대역은 기록 안 함", called == [])

    # ⑨ 기록 실패(OSError)가 거절 예외를 바꾸지 않는다
    blocker = tmp / "file-not-dir"
    blocker.write_text("x")
    err = io.StringIO()
    with redirect_stderr(err):
        e = _expect_reject(lambda: PT.transition(
            864, "T1", "완료", "x", getter=FakeIssue(_plan_body()).get,
            updater=lambda *a, **k: "ok", events_path=blocker / "plan_events.jsonl"))
    check("⑨ 같은 예외", isinstance(e, PS.TransitionError) and "허용되지 않는다" in str(e), repr(e))
    check("⑨ stderr 경고", "거절 기록 실패" in err.getvalue(), err.getvalue())

    # ⑩ 경로 해석 실패(레지스트리 없음)도 삼킨다
    def no_registry(**_):
        raise RuntimeError("AX_PROJECTS_ROOT 없음")
    orig_default = PE.default_path
    PE.default_path = no_registry
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            ok = PE.record("transition", 1, PS.TransitionError("x"))
    finally:
        PE.default_path = orig_default
    check("⑩ 경로 해석 실패도 False 반환", ok is False and "AX_PROJECTS_ROOT" in err.getvalue())

    # ⑪ 레지스트리로 AXCluster 트윈을 푼다(마운트와 무관)
    class Reg:
        names, active = ["ModularStage", "AXCluster"], "ModularStage"
        def dir_of(self, n):
            return tmp / n
    check("⑪ 기본 경로", PE.default_path(registry=Reg()) == tmp / "AXCluster" / "plan_events.jsonl")

    class Reg2(Reg):
        names = ["ModularStage"]
    try:
        PE.default_path(registry=Reg2())
        check("⑪ 미등록 거절", False)
    except Exception as exc:            # noqa: BLE001
        check("⑪ 미등록 거절", "AXCluster" in str(exc))

    # ⑫ 동시 append — 줄이 겹치지 않는다
    conc = tmp / "conc" / "plan_events.jsonl"
    def worker(i):
        for j in range(50):
            PE.append(PE.build("transition", i, PS.TransitionError("y" * 2000), task_id=f"T{j}"),
                      conc)
    th = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    rows = _lines(conc)
    check("⑫ 400줄 전부 파싱", len(rows) == 400, str(len(rows)))

    # ⑬ 분류·읽기
    check("⑬ 모르는 사유", PE.classify("이상한 사유") == "format" and PE.classify("") == "other")
    check("⑬ 잠금 거절(#883)", PE.classify("#879 작업이 진행 중이다(issue/879) — #883 의 태스크를 "
                                          "작업중으로 옮기지 않는다") == "lock_busy")
    check("⑬ 이슈 필터", len(PE.read(log, issue_id=864)) == 5 and PE.read(log, issue_id=1) == [])
    check("⑬ 없는 파일", PE.read(tmp / "none.jsonl") == [])


if __name__ == "__main__":
    run()
    total = PASS + FAIL
    if FAIL:
        print(f"FAIL test_plan_events: {PASS}/{total} 통과")
        sys.exit(1)
    print(f"OK test_plan_events: {PASS}/{total} 통과")
