"""제출된 사실 읽기(`#857` T4) — `GET /api/v1/tasks/{id}/submission`.

[중요] 빌드 워커가 submit 에 싣는 `head_commit`·`self_check.build` 는 태스크 **본문에만** 저장돼
읽는 코드가 0곳이었다. 이 검사는 적힌 그대로 돌려주는지, 판정하지 않는지, 제출이 없을 때
「통과 정보 없음」과 섞지 않는지를 잰다. 실 큐(`~/ax-state`)를 만지지 않는다.

실행: .venv/bin/python master/test_task_submission.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue.logic import claim_task, register_task, register_work   # noqa: E402
from master.task_queue.logic_lifecycle import submission, submit_result        # noqa: E402
from master.task_queue.persistence import TaskIndex                            # noqa: E402

W = "w-.2"
PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _claimed(root: Path | None = None):
    root = root or Path(tempfile.mkdtemp(prefix="ax-857-sub-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="t", target_repo="/tmp/repo")
    register_task(idx, work_id=w["work_id"], type="build", task_data={}, stem="b")
    t = claim_task(idx, W, capabilities=["ue5"], types=["build"])
    return idx, t["task_id"], int(t.get("epoch", 1))


BUILD = {"build": {"ok": True, "passed": True, "summary": "Result: Succeeded", "seconds": 46.2,
                   "log_tail": "[1/5] Compile [x64] Ax857Probe.cpp\nResult: Succeeded"}}


def test_reads_submitted_facts():
    idx, tid, ep = _claimed()
    r = submission(idx, tid)
    check("제출 전에는 submitted False — 빈 결과를 통과로 읽지 않는다",
          r["ok"] and r["submitted"] is False and "self_check" not in r, str(r))
    submit_result(idx, tid, branch="", head_commit="4cd229f3fcb9", self_check=BUILD,
                  epoch=ep, worker_id=W)
    r = submission(idx, tid)
    check("제출 뒤 submitted True", r["ok"] and r["submitted"] is True, str(r))
    check("head_commit 을 그대로", r["head_commit"] == "4cd229f3fcb9", str(r))
    check("self_check 를 그대로 (판정하지 않는다)", r["self_check"] == BUILD, str(r))
    check("status 를 싣는다", r["status"] == "submitted")
    check("판정 필드를 만들지 않는다", "passed" not in r and "verdict" not in r, str(r))


def test_unknown_task():
    idx, _tid, _ep = _claimed()
    r = submission(idx, "없는-태스크")
    check("없는 태스크는 ok False + 사유", r["ok"] is False and "not found" in r["error"], str(r))


def test_last_submission_wins():
    idx, tid, ep = _claimed()
    submit_result(idx, tid, branch="", head_commit="aaa111", self_check={"build": {"ok": False}},
                  epoch=ep, worker_id=W)
    # 본문에 두 번째 제출이 쌓인 경우(재배정 뒤) — 마지막 것이 현재 제출이다
    path = idx.task_paths[tid]
    path.write_text(path.read_text(encoding="utf-8")
                    + '\n## self_check\n```json\n{"build": {"ok": true}}\n```\n'
                    + "\n## submit_meta\nbranch: \nhead_commit: bbb222\nat: 2026-10-31T18:00:00\n",
                    encoding="utf-8")
    r = submission(idx, tid)
    check("마지막 제출의 커밋", r["head_commit"] == "bbb222", str(r))
    check("마지막 제출의 self_check", r["self_check"] == {"build": {"ok": True}}, str(r))
    check("제출 횟수를 말한다", r["submissions"] == 2, str(r))


def test_broken_json_is_not_success():
    idx, tid, ep = _claimed()
    submit_result(idx, tid, branch="", head_commit="ccc", self_check={"build": {"ok": True}},
                  epoch=ep, worker_id=W)
    path = idx.task_paths[tid]
    path.write_text(path.read_text(encoding="utf-8").replace('"ok": true', '"ok": tru'),
                    encoding="utf-8")
    r = submission(idx, tid)
    check("깨진 self_check 는 ok False — 통과로 읽히지 않는다", r["ok"] is False, str(r))


def test_route_live():
    """실물 앱의 라우트 — 인증 미들웨어 포함, 임시 큐 루트."""
    import types
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from master.task_queue import server as S
    tmp = Path(tempfile.mkdtemp(prefix="ax-857-route-"))
    master_t, req_t, wrk_t = "m" * 40, "r" * 40, "w" * 40
    got = {}
    fake_uv = types.ModuleType("uvicorn")
    fake_uv.run = lambda app, **kw: got.setdefault("app", app)
    (tmp / "queue").mkdir(parents=True)
    # 서버가 읽을 큐 루트에 태스크를 미리 만든다 — HTTP 등재는 프로젝트 태그 계약(#257) 몫이라 여기선 우회
    idx, tid, ep = _claimed(tmp / "queue")
    submit_result(idx, tid, branch="", head_commit="4cd229f", self_check=BUILD, epoch=ep, worker_id=W)
    with patch.dict(sys.modules, {"uvicorn": fake_uv}), \
            patch.object(S, "load_token", return_value=master_t), \
            patch("master.auth.load_role_token",
                  side_effect=lambda role: {"requester": req_t, "worker": wrk_t}.get(role)):
        S._run_http_server(tmp / "queue", 0, "127.0.0.1")
    c = TestClient(got["app"])
    H = {"Authorization": f"Bearer {master_t}"}
    r = c.get("/api/v1/tasks/없는것/submission", headers=H)
    check("없는 태스크는 404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")
    r = c.get("/api/v1/tasks/x/submission")
    check("토큰 없으면 401", r.status_code == 401, str(r.status_code))
    r = c.get(f"/api/v1/tasks/{tid}/submission", headers=H)
    body = r.json() if r.status_code == 200 else {}
    check("제출된 태스크는 200 + 사실 그대로",
          body.get("submitted") is True and body.get("head_commit") == "4cd229f"
          and body.get("self_check") == BUILD, f"{r.status_code} {r.text[:200]}")
    r = c.get(f"/api/v1/tasks/{tid}/submission", headers={"Authorization": f"Bearer {wrk_t}"})
    check("워커 토큰도 읽을 수 있다(GET /api/v1/tasks 스코프)", r.status_code == 200, str(r.status_code))


def main() -> int:
    for fn in (test_reads_submitted_facts, test_unknown_task, test_last_submission_wins,
               test_broken_json_is_not_success, test_route_live):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_task_submission: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
