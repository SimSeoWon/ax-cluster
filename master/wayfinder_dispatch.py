"""웨이파인더에서 이번 사이클에 발주할 노드와 워커를 고른다."""
from __future__ import annotations

from . import issue_lock, map_block, plan_block, plan_start, spec_block, wayfinder
from .work import runner


def _plan_problem(issue: dict, *, rework: bool) -> str:
    body = issue.get("description") or ""
    try:
        spec = spec_block.parse(body)
        if not spec or spec_block.missing(spec):
            return "확정된 명세가 필요하다"
        plan = plan_block.parse(body)
    except (spec_block.SpecError, plan_block.PlanError) as error:
        return str(error)
    if not plan or not plan.tasks or not plan.checklist:
        return "승인된 태스크와 개발 완료 체크리스트가 필요하다"
    verdict = plan_start.assess(body)
    allowed = {"next", "resume", "plan_done"} if rework else {"next"}
    if verdict.verdict not in allowed:
        return f"플랜 {verdict.verdict} — {verdict.next_action}"
    return ""


def candidates(root_id: int, node_ids, *, rm=None, lock_root=None) -> dict:
    """요청 대상만 대조하고 발주 가능 여부와 대기 사유를 돌려준다."""
    root_id = wayfinder._issue_id(root_id, "Root")
    node_ids = list(dict.fromkeys(wayfinder._node_ref(node, "노드") for node in node_ids))
    if not node_ids:
        raise wayfinder.WayfinderError("이번 사이클에서 발주할 노드를 지정한다")
    lock_root = issue_lock.default_root() if lock_root is None else lock_root
    rm = wayfinder._port(rm)
    block = wayfinder.compute_states(wayfinder.load(root_id, rm=rm))
    differences = wayfinder._differences(rm, root_id, block)
    if differences:
        return {"ok": False, "root_id": root_id, "why": "지도와 Redmine 대조 결과에 차이가 있다",
                "differences": differences}

    assignments = issue_lock.node_assignments(lock_root)
    active = issue_lock.current(lock_root) or {}
    paused = issue_lock.paused(lock_root)
    ready, waiting = [], []
    for node_id in node_ids:
        node = block.node(node_id)
        assignment = assignments.get(node_id)
        rework = bool(assignment and assignment["root_id"] == root_id
                      and assignment["state"] == issue_lock.NODE_REWORK)
        if node is None:
            why = "Root 지도에 없는 노드다"
        elif map_block.is_planned(node_id):
            why = "티켓을 준비하고 착수 전 인터뷰를 진행해야 한다"
        elif assignment and not rework:
            why = "실행 중이거나 검수 대기인 배정이 있다"
        elif active.get("issue_id") == node_id or node_id in paused:
            why = "단독 일감 잠금으로 관리 중이다"
        elif node.state != wayfinder.FRONTIER and not (rework and node.state == wayfinder.WORKING):
            why = f"발주 가능한 지도 상태가 아니다 ({node.state})"
        else:
            issue = wayfinder._get(rm, node_id)
            deps_done = all(
                block.node(dep).state == wayfinder.DONE
                and wayfinder._get(rm, dep).get("status") == wayfinder.DONE for dep in node.deps
            )
            if not deps_done:
                why = "완료되지 않은 선행 일감이 있다"
            elif issue.get("status") == wayfinder.DONE:
                why = "이미 마감된 일감이다"
            else:
                why = _plan_problem(issue, rework=rework)
        if why:
            waiting.append({"id": node_id, "why": why})
        else:
            ready.append({"id": node_id, "title": node.title})
    return {"ok": True, "root_id": root_id, "ready": ready, "waiting": waiting}


def reserve_worker(lock_root, root_id: int, issue_id: int, facts, *, mode: str, clean=None) -> dict:
    """가용 워커를 고르고 P2의 원자 예약을 사용한다. 경쟁으로 찬 워커는 다음 후보로 넘긴다."""
    if mode not in runner.SESSION1_MODES:
        return {"ok": False, "why": f"티켓 발주를 지원하는 워커 지휘자 모드가 아니다 ({mode})"}
    running = {rec["worker"].casefold() for rec in issue_lock.node_assignments(lock_root).values()
               if rec["state"] == issue_lock.NODE_RUNNING}
    pool = [worker for worker in facts if worker.host.casefold() not in running
            and worker.driven == "ssh" and getattr(worker, mode)]
    while pool:
        pick = runner.pick_worker(pool, clean=clean, need_agent=False)
        if pick.chosen is None:
            return {"ok": False, "why": pick.summary}
        worker = pick.chosen
        result = issue_lock.reserve_node(lock_root, issue_id, root_id=root_id, worker=worker.host)
        if result.get("ok"):
            return {"ok": True, "worker": worker, "record": result["record"]}
        if result.get("reason") != "worker_busy":
            return result
        pool = [other for other in pool if other.host.casefold() != worker.host.casefold()]
    return {"ok": False, "why": "배정 가능한 등록 워커가 없다"}
