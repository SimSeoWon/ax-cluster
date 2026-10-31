"""`#861` — 데몬이 아니라 **서버(큐·인증)가 강제하는** 워커 계약.

워커 상주 데몬(`work/worker_daemon.py`)과 그 테스트(`test_worker_daemon.py`)를 지웠다
(사용자 결정 2026-10-31, `#860`·`#861`). 그 테스트 안에는 데몬 내부 동작과 섞여 **서버가
강제하는 계약**이 있었다. 데몬과 함께 사라지면 안 되므로 실제 서버측 코드에 대고 다시 잰다:

    ① claim 의 유형 격리 — `types` 필터는 다른 유형을 훔치지 않는다, `requires` 는 능력 미달을 막는다
    ② 워커 토큰 스코프 — claim·heartbeat·submit·submit-fail 만 열리고 판단·등록은 403
       (`auth.WORKER_SCOPE` 를 **실제 미들웨어**에 꽂아 잰다 — 규칙을 다시 짜지 않는다)
    ③ 제출 신원 — worker_id 없는 submit/submit-fail, 남의 태스크 고지는 거부 (`#318`)
    ④ heartbeat note — 서버가 저장·보존·절단한다 (`#220`)

[주의] 데몬 안에서만 지켜지던 것(빌드 실패를 submit 으로 보고·싱글턴 잠금·로그 회전·
config 의 능력 읽기 등)은 여기 옮기지 않는다 — 서버가 강제한 적이 없는 계약이다.
더 깊은 신원·epoch 검사는 `test_submit_gates.py` 에 있다.

실행: .venv/bin/python -B master/test_queue_worker_contracts.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.auth import BearerAuthMiddleware, WORKER_SCOPE, generate_token  # noqa: E402
from master.task_queue.logic import claim_task, register_task, register_work  # noqa: E402
from master.task_queue.logic_claim import heartbeat  # noqa: E402
from master.task_queue.logic_lifecycle import submit_fail, submit_result  # noqa: E402
from master.task_queue.persistence import TaskIndex  # noqa: E402

PASS = FAIL = 0
W, OTHER = "w-.2", "w-.43"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _idx() -> tuple:
    idx = TaskIndex(Path(tempfile.mkdtemp(prefix="ax-861-contract-")))
    r = register_work(idx, title="t", target_repo="/tmp/repo")
    assert r.get("ok"), r
    return idx, r["work_id"]


# ── ① 유형 격리 ─────────────────────────────────────────────────

def test_types_filter_isolates() -> None:
    idx, wid = _idx()
    register_task(idx, work_id=wid, type="write", task_data={}, stem="w")
    got = claim_task(idx, W, capabilities=["ue5"], types=["build"])
    check("[중요] build 만 집는 claim 은 write 일감을 훔치지 않는다", got is None, str(got))
    check("  집지 않은 일감은 pending 그대로",
          all(t["status"] == "pending" for t in idx.tasks.values()))

    idx, wid = _idx()
    register_task(idx, work_id=wid, type="write", task_data={}, stem="w")
    r = register_task(idx, work_id=wid, type="build", task_data={}, stem="b", requires=["ue5"])
    got = claim_task(idx, W, capabilities=["ue5"], types=["build"])
    check("맞는 유형은 집는다", bool(got) and got["task_id"] == r["task_id"], str(got))

    idx, wid = _idx()
    r = register_task(idx, work_id=wid, type="write", task_data={}, stem="w")
    got = claim_task(idx, W, capabilities=["ue5"])
    check("types 없는 claim 은 종전대로 (하위호환)",
          bool(got) and got["task_id"] == r["task_id"], str(got))


def test_requires_blocks_missing_capability() -> None:
    idx, wid = _idx()
    register_task(idx, work_id=wid, type="build", task_data={}, stem="b", requires=["ue5"])
    got = claim_task(idx, OTHER, capabilities=[], types=["build"])
    check("[중요] ue5 가 없는 워커는 requires=[ue5] 일감을 집지 못한다", got is None, str(got))
    got = claim_task(idx, W, capabilities=["ue5"], types=["build"])
    check("  능력이 있는 워커는 집는다", bool(got) and got.get("worker_id") == W, str(got))


# ── ② 워커 토큰 스코프 (실제 미들웨어) ─────────────────────────────

async def _call(app, path: str, method: str, token: str) -> int:
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "path": path, "method": method,
             "headers": [(b"authorization", f"Bearer {token}".encode())]}
    await app(scope, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def test_worker_scope_via_middleware() -> None:
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    master_tok, worker_tok = generate_token(), generate_token()
    app = BearerAuthMiddleware(inner, master_tok, scoped=((worker_tok, WORKER_SCOPE),))

    def st(method, path):
        return asyncio.run(_call(app, path, method, worker_tok))

    for m, p in (("POST", "/api/v1/tasks/claim"),
                 ("POST", "/api/v1/tasks/abc123/heartbeat"),
                 ("POST", "/api/v1/tasks/abc123/submit"),
                 ("POST", "/api/v1/tasks/abc123/submit-fail")):
        check(f"워커 토큰으로 {m} {p} → 200", st(m, p) == 200, str(st(m, p)))
    # [중요] κ.0 경계 — 판단(verify)·등록·work 조작은 워커 토큰으로 못 한다 (401 아닌 403)
    for m, p in (("POST", "/api/v1/tasks/abc123/verify"),
                 ("POST", "/api/v1/tasks"),
                 ("POST", "/api/v1/works"),
                 ("PATCH", "/api/v1/works/abc"),
                 ("POST", "/api/v1/tasks/abc123/cancel")):
        check(f"[중요] 워커 토큰으로 {m} {p} → 403", st(m, p) == 403, str(st(m, p)))


# ── ③ 제출 신원 (`#318`) ─────────────────────────────────────────

def _claimed() -> tuple:
    idx, wid = _idx()
    register_task(idx, work_id=wid, type="build", task_data={}, stem="b")
    t = claim_task(idx, W, capabilities=["ue5"], types=["build"])
    return idx, t["task_id"], int(t.get("epoch", 1))


def test_submit_identity_is_server_enforced() -> None:
    idx, tid, ep = _claimed()
    r = submit_result(idx, tid, branch="", head_commit="abc", self_check={}, epoch=ep)
    check("[중요] worker_id 없는 submit 은 409 로 거부", not r.get("ok") and r.get("code") == 409
          and r.get("identity"), str(r))
    r = submit_result(idx, tid, branch="", head_commit="abc", self_check={}, epoch=ep,
                      worker_id=OTHER)
    check("[중요] 소유자가 아닌 고지자의 submit 거부", not r.get("ok") and r.get("identity"), str(r))
    r = submit_fail(idx, tid, "why", "detail", epoch=ep)
    check("[중요] worker_id 없는 submit-fail 거부", not r.get("ok") and r.get("identity"), str(r))
    check("  거부는 상태를 바꾸지 않는다", idx.tasks[tid]["status"] == "claimed")
    r = submit_result(idx, tid, branch="", head_commit="abc", self_check={}, epoch=ep,
                      worker_id=W)
    check("소유자 신원을 실은 submit 은 통과", r.get("ok") is True, str(r))


# ── ④ heartbeat note (`#220`) ────────────────────────────────────

def test_heartbeat_note_stored_and_preserved() -> None:
    idx, tid, _ep = _claimed()
    check("note 심박 성공", heartbeat(idx, tid, W, note="UE5 빌드 중")["ok"])
    check("note 저장", idx.tasks[tid].get("note") == "UE5 빌드 중" and idx.tasks[tid].get("note_at"))
    check("note 없는 심박 성공", heartbeat(idx, tid, W)["ok"])
    check("빈 note 는 이전 값을 지우지 않는다", idx.tasks[tid].get("note") == "UE5 빌드 중")
    heartbeat(idx, tid, W, note="x" * 500)
    check("서버가 200자로 자른다", len(idx.tasks[tid].get("note") or "") == 200)
    r = heartbeat(idx, tid, OTHER, note="남의 심박")
    check("[중요] 임대자가 아닌 워커의 심박은 거부", not r.get("ok"), str(r))
    check("  거부된 심박은 note 를 바꾸지 않는다", idx.tasks[tid].get("note") == "x" * 200)


if __name__ == "__main__":
    for fn in (test_types_filter_isolates,
               test_requires_blocks_missing_capability,
               test_worker_scope_via_middleware,
               test_submit_identity_is_server_enforced,
               test_heartbeat_note_stored_and_preserved):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_queue_worker_contracts: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
