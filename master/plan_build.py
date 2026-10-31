"""플랜 태스크의 **빌드 단계**(7단계 중 1·5) — `#857` T4.

마스터는 빌드하지 않는다(`test_no_integrator.BUILD_CALLERS_ALLOWED`). 그래서 이 모듈은
`buildjob`(#204) 큐 경로만 쓴다 — 잡을 올리면 UE5 워커의 상주 데몬이 집어 빌드하고 사실을
제출한다. 여기서 하는 것은 그 사실을 읽어 **결정적으로** 판정하는 것뿐이다:

    1 기준 리비전   워커가 빌드한 커밋(`head_commit`)이 기대 커밋과 같은가
    5 빌드          워커가 낸 `self_check.build.ok`

[중요] **둘 중 하나라도 아니면 실패다** — 다른 커밋을 빌드해 통과한 것은 그 태스크의 근거가
아니다. 판정이 나면 buildjob work 를 종결한다(종결 없이 두면 마운트 전환 가드 #210 에 걸린다).
[주의] 관찰이 시간 안에 안 끝나면 **종결하지 않는다** — 아직 도는 빌드를 실패로 닫지 않는다.
[주의] 플랜 마킹은 하지 않는다 — 돌려주는 `evidence` 를 호출자가 `plan_transition` 의 근거로 쓴다.
"""
from __future__ import annotations

import time

from master.work import buildjob

UNREAL = "unreal"


class BuildStepError(ValueError):
    """빌드 단계를 시작할 수 없다 — 사유 문장을 담는다."""


def _submission(task_id: str, api=None) -> dict:
    st, got = buildjob._call("GET", f"/api/v1/tasks/{task_id}/submission", api=api)
    if st != 200 or not isinstance(got, dict):
        return {"ok": False, "error": f"제출 사실 조회 실패 HTTP {st}"}
    return got


def _same_commit(a: str, b: str) -> bool:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    return bool(a and b) and (a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) >= 7


def build_step(project: str, *, expected_commit: str, kind: str = "", tree: str = "",
               watch_timeout: int = 2400, api=None, sleeper=time.sleep,
               kind_of=None) -> dict:
    """빌드 잡을 올리고 끝날 때까지 본 뒤 판정한다. 반환의 `evidence` 가 플랜 근거 한 줄이다."""
    if not (expected_commit or "").strip():
        raise BuildStepError("expected_commit 이 비었다 — 기준 리비전 없이 빌드 결과를 근거로 쓰지 않는다")
    if not kind:
        if kind_of is None:
            from master.projects.profile import kind_of
        kind = kind_of(project)
    if kind != UNREAL:
        raise BuildStepError(f"kind={kind or '(없음)'} — UE 빌드 단계는 unreal 프로젝트만이다 "
                             "(code 의 5단계는 정적·통합 검사다)")
    enq = buildjob.enqueue(project=project, tree=tree, api=api)
    if not enq.get("ok"):
        return {"ok": False, "stage": "enqueue", "detail": enq,
                "evidence": f"빌드 잡 등록 실패 — {enq.get('step')} HTTP {enq.get('http')}"}
    work_id, task_id = enq["work_id"], enq["task_id"]
    seen = buildjob.watch(task_id, timeout=watch_timeout, api=api, sleeper=sleeper)
    base = {"work_id": work_id, "task_id": task_id}
    if "status" not in seen:
        # 시간 초과·조회 실패 — 아직 돌 수 있다. 닫지 않는다
        return {**base, "ok": False, "stage": "watch", "closed": False, "detail": seen,
                "evidence": f"빌드 {task_id[:8]} 관찰 미완 — {seen.get('error')} (work 미종결)"}
    if seen["status"] not in ("submitted", "verified"):
        closed = buildjob.close(work_id, result="fail", api=api)
        return {**base, "ok": False, "stage": "build", "status": seen["status"], "closed": closed,
                "evidence": f"빌드 {task_id[:8]} {seen['status']} — 워커가 빌드를 끝내지 못했다"}
    sub = _submission(task_id, api=api)
    if not sub.get("ok") or not sub.get("submitted"):
        closed = buildjob.close(work_id, result="fail", api=api)
        return {**base, "ok": False, "stage": "submission", "detail": sub, "closed": closed,
                "evidence": f"빌드 {task_id[:8]} 제출 사실을 읽지 못했다 — {sub.get('error', '제출 없음')}"}
    build = ((sub.get("self_check") or {}).get("build") or {})
    commit = str(sub.get("head_commit") or "")
    passed = build.get("ok") is True
    rev_ok = _same_commit(commit, expected_commit)
    verdict = "pass" if (passed and rev_ok) else "fail"
    closed = buildjob.close(work_id, result=verdict, api=api)
    secs = build.get("seconds")
    parts = [f"빌드 {task_id[:8]}", f"커밋 {commit[:8] or '?'}",
             "PASS" if passed else "FAIL",
             f"{secs:.0f}초" if isinstance(secs, (int, float)) else "",
             str(build.get("summary") or "")[:60]]
    if not rev_ok:
        parts.append(f"[리비전 불일치 — 기대 {expected_commit[:8]}]")
    if not passed and build.get("failure"):
        parts.append(str(build["failure"])[:120])
    return {**base, "ok": verdict == "pass", "stage": "done", "passed": passed,
            "revision_ok": rev_ok, "commit": commit, "build": build, "closed": closed,
            "evidence": " · ".join(p for p in parts if p)}
