"""웨이파인더에서 이번 사이클에 발주할 노드와 워커를 고른다."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from . import auth, issue_lock, map_block, plan_block, plan_start, spec_block, wayfinder
from .work import runner


def plan_problem(issue: dict, *, rework: bool) -> str:
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


def candidates(root_id: int, node_ids, *, rm=None, lock_root=None, registered_workers=None) -> dict:
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

    active, paused, assignments = issue_lock.snapshot(lock_root)
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
        elif (active and active["issue_id"] == node_id) or node_id in paused:
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
                why = plan_problem(issue, rework=rework)
        if why:
            waiting.append({"id": node_id, "why": why})
        else:
            ready.append({"id": node_id, "title": node.title})
    result = {"ok": True, "root_id": root_id, "ready": ready, "waiting": waiting}
    if registered_workers is not None:
        busy = {rec["worker"].casefold() for rec in assignments.values()
                if rec["state"] == issue_lock.NODE_RUNNING}
        available = []
        for host in registered_workers:
            key = host.casefold()
            if key not in busy:
                available.append(host)
                busy.add(key)
        result["worker_candidates"] = [
            {"id": node["id"], "worker": host} for node, host in zip(ready, available)
        ]
        result["awaiting_worker"] = [
            {"id": node["id"], "why": "현재 배정 기록상 비어 있는 등록 워커가 없다"}
            for node in ready[len(available):]
        ]
    return result


def preview(root_id: int, node_ids) -> dict:
    """레지스트리와 잠금 장부로 예상 배정을 계산한다. 워커 연결 상태는 발주 시 확인한다."""
    from .projects.config import Registry
    from .work import mode

    config = Registry.load().config_of(runner.SELF_PROJECT)
    selected, _ = mode.current()
    registered = [shop.host for shop in config.workshops.values() if shop.drivable and shop.user and shop.path]
    result = candidates(root_id, node_ids, registered_workers=registered if selected in runner.SESSION1_MODES else ())
    result.update(dry_run=True, worker_mode=selected)
    if selected not in runner.SESSION1_MODES:
        result["worker_reason"] = f"티켓 발주를 지원하는 워커 지휘자 모드가 아니다 ({selected})"
    return result


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
        result = issue_lock.reserve_node(lock_root, issue_id, root_id=root_id, worker=worker.host, family=mode)
        if result.get("ok"):
            return {"ok": True, "worker": worker, "record": result["record"]}
        if result.get("reason") != "worker_busy":
            return result
        pool = [other for other in pool if other.host.casefold() != worker.host.casefold()]
    return {"ok": False, "why": "배정 가능한 등록 워커가 없다"}


def run_assignment(lock_root, record: dict, worker, *, mode: str) -> dict:
    """현재 예약에만 티켓 권한을 발급하고 배정된 워커를 실행한다."""
    issue_id = record["issue_id"]
    current = issue_lock.node_assignments(lock_root).get(issue_id)
    if current != record or record["state"] != issue_lock.NODE_RUNNING or worker.host != record["worker"]:
        return {"rc": 1, "termination_confirmed": False, "why": "현재 배정과 실행 요청이 일치하지 않는다"}
    try:
        grant = auth.issue_node_ticket_grant(auth.load_token(), issue_id, worker.host,
                                            assignment_id=record["assignment_id"],
                                            expires_at=int(time.time()) + runner.DEFAULT_TIMEOUT)
    except (auth.AuthError, ValueError, OSError) as error:
        return {"rc": 1, "termination_confirmed": True,
                "why": f"권한 발급 실패로 워커를 실행하지 않았다 ({type(error).__name__})"}

    termination_confirmed = False

    def confirm_exit():
        nonlocal termination_confirmed
        termination_confirmed = True

    try:
        rc, _ = runner.run_node_ticket(worker, issue_id, assignment_id=record["assignment_id"],
                                       grant=grant, mode=mode, on_exit=confirm_exit)
    except Exception as error:  # 실행을 시작했을 수 있으므로 종료 근거를 확인한다.
        return {"rc": 1, "termination_confirmed": termination_confirmed,
                "why": f"워커 실행 경로 오류 ({type(error).__name__})"}
    return {"rc": rc, "termination_confirmed": termination_confirmed,
            "why": f"워커 실행 종료 확인 (rc={rc})" if termination_confirmed else "원격 종료 미확인"}


def _run_and_handoff(lock_root, rm, reservation: dict, mode: str) -> dict:
    record, worker = reservation["record"], reservation["worker"]
    issue_id = record["issue_id"]
    result = run_assignment(lock_root, record, worker, mode=mode)
    result.update(id=issue_id, worker=record["worker"], assignment_id=record["assignment_id"])
    if not result["termination_confirmed"]:
        result["state"] = issue_lock.NODE_RUNNING
        return result
    transition = issue_lock.advance_node_assignment(
        lock_root, issue_id, assignment_id=record["assignment_id"], to=issue_lock.NODE_REVIEW,
        by="master", why=result["why"])
    if not transition["ok"]:
        result.update(why=transition["why"], reason=transition.get("reason"))
        return result
    result["state"] = issue_lock.NODE_REVIEW
    note = (f"웨이파인더 배정 검수 대기 — Root #{record['root_id']} · 워커 {record['worker']} · "
            f"배정 {record['assignment_id']} · {result['why']}. 같은 티켓의 워커 작업·검증 노트를 확인한다.")
    try:
        written = rm.update_issue(issue_id, notes=note)
    except Exception as error:
        written = f"[주의] Redmine 기록 실패 ({type(error).__name__})"
    result["redmine"] = written
    return result


def dispatch_cycle(root_id: int, node_ids, user_answer: str, *, rm=None, lock_root=None,
                   workers=None, worker_mode=None, clean=None) -> dict:
    """승인된 사이클을 예약·실행하고 확인된 종료를 검수 대기로 넘긴다."""
    if not user_answer.strip():
        return {"ok": False, "why": "사용자의 실제 발주 요청 원문이 필요하다"}
    lock_root = issue_lock.default_root() if lock_root is None else lock_root
    rm = wayfinder._port(rm)
    checked = candidates(root_id, node_ids, rm=rm, lock_root=lock_root)
    if not checked["ok"] or not checked["ready"]:
        return checked

    if worker_mode is None:
        from .work import mode

        worker_mode, _ = mode.current()
    if worker_mode not in runner.SESSION1_MODES:
        return {"ok": False, "root_id": checked["root_id"],
                "why": f"티켓 발주를 지원하는 워커 지휘자 모드가 아니다 ({worker_mode})"}
    if workers is None:
        from . import redmine
        from .client import bundle
        from .projects.config import Registry
        from .work import conductor

        registry = Registry.load()
        config = registry.config_of(runner.SELF_PROJECT)
        if registry.active != runner.SELF_PROJECT:
            return {"ok": False, "why": "AXCluster가 마운트되어 있어야 한다"}
        if wayfinder._get(rm, checked["root_id"]).get("project_id") != redmine.AX_PROJECT_NUMERIC_ID:
            return {"ok": False, "why": "AXCluster Redmine 프로젝트의 Root만 발주할 수 있다"}
        probed = {}

        def probe(*registration):
            facts = bundle.probe(*registration)
            probed[facts.host] = facts
            return facts

        readiness = conductor.worker_mode_readiness(
            worker_mode, runner.SELF_PROJECT, registry=registry, prober=probe)
        configured = {shop.host for shop in config.workshops.values() if shop.drivable and shop.user and shop.path}
        workers = [probed[row["host"]] for row in readiness["hosts"] if row["ok"] and row["host"] in configured]
        clean = runner.cleanliness(runner.SELF_PROJECT)
    if not workers:
        return {"ok": False, "root_id": checked["root_id"], "why": "발주할 수 있는 등록 워커가 없다",
                "waiting": checked["waiting"]}

    reservations = []
    for node in checked["ready"]:
        reserved = reserve_worker(lock_root, checked["root_id"], node["id"], workers, mode=worker_mode, clean=clean)
        if reserved["ok"]:
            reservations.append(reserved)
        else:
            checked["waiting"].append({"id": node["id"], "why": reserved["why"]})
    results = []
    if reservations:
        with ThreadPoolExecutor(max_workers=len(reservations)) as pool:
            jobs = [pool.submit(_run_and_handoff, lock_root, rm, reserved, worker_mode) for reserved in reservations]
            results = [job.result() for job in jobs]
    return {"ok": bool(results) and all(r.get("state") == issue_lock.NODE_REVIEW and r["rc"] == 0
                                       and not r["redmine"].startswith("[주의]") for r in results),
            "root_id": checked["root_id"], "waiting": checked["waiting"], "results": results}


# ── 검수 (`#1050` T3) ───────────────────────────────────────────────────────
#
# 사용자 결정(#1050 노트, 「1번으로 가자.」): 도구 하나 · 기본 미리보기 · confirm=True + 사용자 원문일 때만 쓴다.
# pass 순서 = 배정 「승인됨」 → 티켓 「완료」·100(이 배정에 한해 완료 관문 통과) → 맵 갱신 → 배정 해제.
# 각 단계는 끝났는지 먼저 보고 건너뛰므로, 중간 실패 뒤 같은 호출을 다시 부르면 남은 단계부터 이어 간다.
# rework = 근거 노트 → 같은 티켓 재작업 상태. Root 브랜치 머지는 하지 않는다(범위 밖).

VERDICTS = ("pass", "rework")
NEEDS_RESULT = ("작업",)          # 제출 결과(커밋 범위)가 있어야 통과하는 노드 타입


def _review_view(issue_id: int, record: dict | None, issue: dict, node_type: str) -> dict:
    view = {"id": issue_id, "status": issue.get("status"), "type": node_type}
    if record:
        view.update(worker=record["worker"], assignment_id=record["assignment_id"], state=record["state"],
                    family=record.get("family", ""), branch=record.get("branch", ""))
        result = record.get("result")
        if result:
            view["result"] = {k: result[k] for k in ("base", "end", "hashes", "subjects", "authors", "summary")}
    return view


def _pass_note(record: dict, why: str, user_answer: str) -> str:
    result = record.get("result")
    if result:
        commits = "\n".join(f"- `{h[:12]}` {s}" for h, s in zip(result["hashes"], result["subjects"]))
        span = (f"범위 `{result['base'][:12]}..{result['end'][:12]}` (커밋 {len(result['hashes'])}건) · "
                f"브랜치 `{result['branch']}` · 작성 계열 {', '.join(result['authors'])}\n{commits}")
    else:
        span = f"제출된 커밋 범위 없음 · 작성 계열 {record.get('family') or '기록 없음'}"
    return (f"웨이파인더 검수 통과 — 워커 {record['worker']} · 배정 {record['assignment_id']}\n{span}\n\n"
            f"검수 근거: {why}\n사용자 승인: {user_answer}")


def review(issue_id: int, verdict: str, why: str = "", *, confirm: bool = False, user_answer: str = "",
           rm=None, lock_root=None, map_hook=None) -> dict:
    """검수 대기 배정을 통과(마감·해제) 또는 재작업으로 넘긴다. 기본은 미리보기(쓰기 0)."""
    if type(issue_id) is not int or issue_id <= 0:
        return {"ok": False, "why": "노드 일감 번호가 필요하다"}
    if verdict not in VERDICTS:
        return {"ok": False, "why": f"판정은 {'/'.join(VERDICTS)} 중 하나다"}
    lock_root = issue_lock.default_root() if lock_root is None else lock_root
    rm = wayfinder._port(rm)
    map_hook = wayfinder.on_node_closed if map_hook is None else map_hook
    with issue_lock.node_guard(lock_root, issue_id):
        record = issue_lock.node_assignments(lock_root).get(issue_id)
        issue = wayfinder._get(rm, issue_id)
        try:
            marker = map_block.parse_node(issue.get("description") or "")
        except map_block.MapError:
            marker = None
        node_type = marker.type if marker else ""
        view = _review_view(issue_id, record, issue, node_type)
        allowed = (issue_lock.NODE_REVIEW, issue_lock.NODE_ACCEPTED) if verdict == "pass" else (issue_lock.NODE_REVIEW,)
        problem = ""
        if marker is None:
            problem = "웨이파인더 노드 표지가 없는 일감이다"
        elif record is None:
            problem = "분산 배정이 없다 — 이미 해제됐거나 발주되지 않았다"
        elif record["root_id"] != marker.root:
            problem = "배정의 Root 와 노드 표지의 Root 가 다르다"
        elif record["state"] not in allowed:
            problem = (f"검수할 수 있는 상태가 아니다 ({record['state']}) — 원격 종료가 확인돼 검수 대기인 배정만 "
                       "받는다")
        elif verdict == "pass" and node_type in NEEDS_RESULT and not record.get("result"):
            problem = f"{node_type} 노드는 제출된 결과(커밋 범위)가 있어야 통과한다 — 재작업으로 돌리거나 제출을 확인한다"
        if problem:
            return {"ok": False, "why": problem, "node": view}
        if not confirm:
            return {"ok": True, "dry_run": True, "verdict": verdict, "node": view}
        if not why.strip() or not user_answer.strip():
            return {"ok": False, "why": "검수 근거와 사용자 승인 원문이 필요하다", "node": view}
        aid, steps = record["assignment_id"], []

        def advance(to):
            got = issue_lock._advance_node_assignment(lock_root, issue_id, assignment_id=aid, to=to,
                                                      by="master", why=why)
            if not got["ok"]:
                raise _ReviewStop("ledger", got["why"])
            steps.append(to)

        try:
            if verdict == "rework":
                written = rm.update_issue(issue_id, notes=(
                    f"웨이파인더 검수 — 재작업 · 워커 {record['worker']} · 배정 {aid}\n\n"
                    f"재작업 근거: {why}\n사용자 승인: {user_answer}"))
                if str(written).startswith("[주의]"):
                    raise _ReviewStop("redmine", written)
                steps.append("note")
                advance(issue_lock.NODE_REWORK)
                return {"ok": True, "verdict": verdict, "steps": steps, "node": view}
            if record["state"] == issue_lock.NODE_REVIEW:
                advance(issue_lock.NODE_ACCEPTED)
            if issue.get("status") != wayfinder.DONE:
                def gate(n):
                    current = issue_lock.node_assignments(lock_root).get(int(n))
                    ok = bool(current and current["assignment_id"] == aid
                              and current["state"] == issue_lock.NODE_ACCEPTED)
                    return {"apply": not ok, "ok": ok,
                            "why": "검수 통과한 배정의 마감" if ok else "검수 통과 기록과 배정이 맞지 않는다"}

                written = rm.update_issue(issue_id, notes=_pass_note(record, why, user_answer),
                                          status_name=wayfinder.DONE, done_ratio=100, completion_gate=gate)
                if str(written).startswith("[주의]") or wayfinder._get(rm, issue_id).get("status") != wayfinder.DONE:
                    raise _ReviewStop("redmine", str(written))
                steps.append("closed")
            mapped = map_hook(issue_id, rm=rm)
            if not mapped.get("ok"):
                raise _ReviewStop("map", str(mapped.get("why") or mapped))
            steps.append("map")
            advance("finished")
        except _ReviewStop as stop:
            return {"ok": False, "verdict": verdict, "step": stop.step, "why": stop.why, "steps": steps,
                    "retry": "같은 호출을 다시 부르면 끝난 단계는 건너뛰고 이어 간다", "node": view}
        return {"ok": True, "verdict": verdict, "steps": steps, "node": view}


class _ReviewStop(Exception):
    def __init__(self, step: str, why: str):
        super().__init__(why)
        self.step, self.why = step, why
