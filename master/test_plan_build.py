"""플랜 빌드 단계(`#857` T4) 계약 테스트 — [중요] **다른 커밋을 빌드한 통과를 근거로 쓰지 않는가,
마스터가 빌드를 직접 부르지 않는가, 아직 도는 빌드를 닫지 않는가.**

큐는 가짜 `api` 로 주입한다 — 실 큐·실 워커를 두드리지 않는다.
실행: python3 master/test_plan_build.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_build as PBD   # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class FakeQueue:
    """buildjob 이 부르는 큐 API — 빌드 결과를 정해 둔다."""

    def __init__(self, *, status="submitted", commit="4cd229f3fcb9", ok=True, submitted=True,
                 never_ends=False):
        self.status, self.commit, self.ok = status, commit, ok
        self.submitted, self.never_ends = submitted, never_ends
        self.calls: list = []
        self.merge = ""

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "POST" and path == "/api/v1/works":
            return 200, {"work_id": "w-857build"}
        if method == "POST" and path == "/api/v1/tasks":
            return 200, {"task_id": "t-857build-0001"}
        if method == "GET" and path == "/api/v1/tasks":
            st = "claimed" if self.never_ends else self.status
            return 200, [{"task_id": "t-857build-0001", "work_id": "w-857build", "status": st,
                          "type": "build"}]
        if method == "GET" and path.endswith("/submission"):
            if not self.submitted:
                return 200, {"ok": True, "submitted": False}
            return 200, {"ok": True, "submitted": True, "head_commit": self.commit,
                         "self_check": {"build": {"ok": self.ok, "summary": "Result: Succeeded"
                                                  if self.ok else "Result: Failed",
                                                  "seconds": 46.2,
                                                  "failure": "" if self.ok else "C2065"}}}
        if method == "GET" and path == "/api/v1/works":
            return 200, [{"work_id": "w-857build"}]
        if method == "POST" and path.endswith("/verify"):
            return 200, {"ok": True}
        if method == "PATCH" and path.startswith("/api/v1/works/"):
            self.merge = payload["merge_status"]
            return 200, {"ok": True}
        if method == "GET" and path.startswith("/api/v1/works/"):
            return 200, {"work": {"merge_status": self.merge}}
        return 404, {"error": path}


def _run(q, **kw):
    kw.setdefault("expected_commit", "4cd229f")
    kw.setdefault("kind", "unreal")
    return PBD.build_step("ModularStage", api=q, sleeper=lambda s: None, **kw)


def test_pass_with_matching_revision():
    q = FakeQueue()
    r = _run(q)
    check("같은 커밋 + 빌드 통과 → ok", r["ok"] and r["passed"] and r["revision_ok"], str(r))
    check("근거에 태스크·커밋·PASS·초", all(x in r["evidence"] for x in ("t-857bui", "4cd229f3", "PASS", "46초")),
          r["evidence"])
    check("buildjob work 를 merged 로 종결", q.merge == "merged", q.merge)
    check("build 타입·ue5 요구로 등록",
          any(c[1] == "/api/v1/tasks" and c[2]["type"] == "build" and c[2]["requires"] == ["ue5"]
              for c in q.calls if c[0] == "POST"))


def test_revision_mismatch_is_failure():
    q = FakeQueue(commit="deadbeef1234")
    r = _run(q)
    check("[중요] 다른 커밋을 빌드한 통과는 실패", not r["ok"] and r["passed"] and not r["revision_ok"], str(r))
    check("근거에 리비전 불일치를 적는다", "리비전 불일치" in r["evidence"], r["evidence"])
    check("rejected 로 종결", q.merge == "rejected", q.merge)


def test_build_failure():
    q = FakeQueue(ok=False)
    r = _run(q)
    check("빌드 실패 → ok False", not r["ok"] and not r["passed"], str(r))
    check("실패 사유를 근거에", "C2065" in r["evidence"] and "FAIL" in r["evidence"], r["evidence"])
    check("rejected 로 종결", q.merge == "rejected")


def test_watch_timeout_does_not_close():
    q = FakeQueue(never_ends=True)
    r = _run(q, watch_timeout=0)
    check("[중요] 관찰 미완은 실패지만 닫지 않는다", not r["ok"] and r["closed"] is False and q.merge == "",
          str(r))


def test_worker_failed_or_no_submission():
    q = FakeQueue(status="failed")
    r = _run(q)
    check("워커 failed → 실패·rejected", not r["ok"] and r["stage"] == "build" and q.merge == "rejected", str(r))
    q = FakeQueue(submitted=False)
    r = _run(q)
    check("제출 사실 없음 → 실패(통과로 읽지 않는다)", not r["ok"] and r["stage"] == "submission", str(r))


def test_refusals_before_enqueue():
    q = FakeQueue()
    for kw, word in (({"expected_commit": ""}, "기준 리비전"), ({"kind": "code"}, "unreal"),
                     ({"kind": ""}, "unreal")):
        try:
            if kw.get("kind") == "":
                PBD.build_step("X", expected_commit="4cd229f", api=q, kind_of=lambda p: "",
                               sleeper=lambda s: None)
            else:
                _run(q, **kw)
            ok = False
        except PBD.BuildStepError as e:
            ok = word in str(e)
        check(f"{kw} → 거절", ok)
    check("거절은 큐에 아무것도 올리지 않는다", q.calls == [], str(q.calls))


def test_short_commit_rules():
    check("7자 미만 접두는 같은 커밋으로 치지 않는다", not PBD._same_commit("4cd229f3", "4cd"))
    check("접두 일치(7자 이상)", PBD._same_commit("4cd229f3fcb9", "4cd229f"))
    check("빈 값은 불일치", not PBD._same_commit("", "4cd229f"))


def test_master_still_does_not_build():
    src = (Path(__file__).resolve().parent / "plan_build.py").read_text(encoding="utf-8")
    check("[중요] run_build_on_workshop·run_build_local 을 부르지 않는다",
          "run_build_on_workshop(" not in src and "run_build_local(" not in src)


def main() -> int:
    for fn in (test_pass_with_matching_revision, test_revision_mismatch_is_failure,
               test_build_failure, test_watch_timeout_does_not_close,
               test_worker_failed_or_no_submission, test_refusals_before_enqueue,
               test_short_commit_rules, test_master_still_does_not_build):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_build: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
