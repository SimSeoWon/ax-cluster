"""#204 계약 테스트 — 유형 필터·워커 스코프·claimer 실행·buildjob 등록.

핵심 계약 넷:
① claim 의 `types` 필터 — build claimer 가 infer(write) 일감을 **절대 훔치지 않는다**
② WORKER_SCOPE — worker 토큰으로 verify·등록은 **못 한다** (κ.0 ①/② 경계의 강제)
③ claimer 는 판단하지 않는다 — 빌드 실패도 submit(사실 보고)이고, 착수 실패만 submit-fail
④ buildjob.enqueue 는 pull 모드 work + requires=["ue5"] build 태스크를 건다

실행: .venv/bin/python master/test_claimer.py  (task_queue 가 pydantic — venv)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.auth import WORKER_SCOPE  # noqa: E402
from master.task_queue.logic import register_work, register_task, claim_task  # noqa: E402
from master.task_queue.persistence import TaskIndex  # noqa: E402
from master.work import buildjob, claimer  # noqa: E402


def _idx() -> TaskIndex:
    root = Path(tempfile.mkdtemp(prefix="ax-claimer-"))
    idx = TaskIndex(root)
    r = register_work(idx, title="t", target_repo="/tmp/repo")
    assert r.get("ok"), r
    idx._wid = r["work_id"]
    return idx


# ── ① 유형 필터 ────────────────────────────────────────────────

def test_types_filter_skips_other_types():
    idx = _idx()
    register_task(idx, work_id=idx._wid, type="write", task_data={}, stem="w")
    got = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    assert got is None                       # write 일감을 훔치지 않는다


def test_types_filter_takes_matching_type():
    idx = _idx()
    register_task(idx, work_id=idx._wid, type="write", task_data={}, stem="w")
    r = register_task(idx, work_id=idx._wid, type="build", task_data={},
                      stem="b", requires=["ue5"])
    got = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    assert got and got["task_id"] == r["task_id"]


def test_no_types_is_backward_compatible():
    idx = _idx()
    r = register_task(idx, work_id=idx._wid, type="write", task_data={}, stem="w")
    got = claim_task(idx, "w-.2", capabilities=["ue5"])          # 기존 호출자 모양
    assert got and got["task_id"] == r["task_id"]


# ── ② 워커 스코프 ──────────────────────────────────────────────

def _scope_allows(method: str, path: str) -> bool:
    for rule in WORKER_SCOPE:
        m, pfx = rule[0], rule[1]
        sfx = rule[2] if len(rule) > 2 else ""
        if method == m and path.startswith(pfx) and (not sfx or path.endswith(sfx)):
            return True
    return False


def test_worker_scope_allows_claim_heartbeat_submit():
    assert _scope_allows("POST", "/api/v1/tasks/claim")
    assert _scope_allows("POST", "/api/v1/tasks/abc123/heartbeat")
    assert _scope_allows("POST", "/api/v1/tasks/abc123/submit")
    assert _scope_allows("POST", "/api/v1/tasks/abc123/submit-fail")


def test_worker_scope_denies_judgment_paths():
    # [중요] κ.0 경계 — 검증(판단)·등록·work 조작은 워커 토큰으로 불가
    assert not _scope_allows("POST", "/api/v1/tasks/abc123/verify")
    assert not _scope_allows("POST", "/api/v1/tasks")            # 등록
    assert not _scope_allows("POST", "/api/v1/works")
    assert not _scope_allows("PATCH", "/api/v1/works/abc")


# ── ③ claimer 실행 계약 ────────────────────────────────────────

class _FakeClient:
    def __init__(self, root):
        self.root = Path(root)
        self.project = "P"
        self.ue5_cmd = ""
        self.calls = []

    def heartbeat(self, tid):
        self.calls.append(("heartbeat", tid))

    def submit(self, tid, **kw):
        self.calls.append(("submit", tid, kw))
        return 200, {}

    def submit_fail(self, tid, reason, detail=""):
        self.calls.append(("submit-fail", tid, reason))
        return 200, {}


def test_build_failure_is_submitted_not_submitfail():
    """[중요] 빌드 FAIL 은 사실이지 사고가 아니다 — submit 으로 보고한다 (판단은 마스터)."""
    with tempfile.TemporaryDirectory() as tmp:
        c = _FakeClient(tmp)
        out = claimer.run_one(
            c, {"task_id": "t1", "type": "build", "task_data": {"tree": tmp}},
            build_fn=lambda tree: {"ok": False, "passed": False, "failure": "컴파일 에러"},
            log=lambda m: None)
        kinds = [x[0] for x in c.calls]
        assert kinds == ["heartbeat", "submit"], kinds
        assert out["build_ok"] is False and out["submit_http"] == 200


def test_setup_error_is_submitfail():
    with tempfile.TemporaryDirectory() as tmp:
        c = _FakeClient(tmp)

        def boom(tree):
            raise RuntimeError("Build.bat 없음")
        claimer.run_one(c, {"task_id": "t2", "type": "build", "task_data": {}},
                        build_fn=boom, log=lambda m: None)
        assert ("submit-fail", "t2", "build-setup") in [x[:3] for x in c.calls]


def test_unsupported_type_bounces():
    with tempfile.TemporaryDirectory() as tmp:
        c = _FakeClient(tmp)
        out = claimer.run_one(c, {"task_id": "t3", "type": "write"},
                              build_fn=lambda t: {}, log=lambda m: None)
        assert any(x[0] == "submit-fail" for x in c.calls)
        assert "지원 안 하는 유형" in out["outcome"]


# ── ④ buildjob 등록 ────────────────────────────────────────────

def test_enqueue_registers_pull_work_and_ue5_build_task():
    seen = []

    def fake_api(method, path, payload):
        seen.append((method, path, payload))
        if path == "/api/v1/works":
            assert payload["distribution_mode"] == "pull"
            return 200, {"ok": True, "work_id": "W1"}
        if path == "/api/v1/tasks":
            assert payload["type"] == "build" and payload["requires"] == ["ue5"]
            return 200, {"ok": True, "task_id": "T1"}
        raise AssertionError(path)
    got = buildjob.enqueue(tree="E:/trunk/ModularStage", api=fake_api)
    assert got == {"ok": True, "work_id": "W1", "task_id": "T1"}
    assert seen[1][2]["task_data"]["tree"] == "E:/trunk/ModularStage"


def test_enqueue_work_failure_reports_step():
    got = buildjob.enqueue(api=lambda m, p, b: (503, {"error": "down"}))
    assert not got["ok"] and got["step"] == "work"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 통과")
    sys.exit(1 if failed else 0)
