"""마운트 전환 인계 조사 — **남은 것을 다섯 부류 전부 이름으로** 낸다 (`#253`).

## 왜 이 모듈이 있나

사용자 정정(2026-08-22): *"당연히 마운트 변경되면 등록된 작업 태스크들 모두 정리해야지. 그냥
바라보는 레포만 바꾸는건 잘못된거지"*.

[주의] `#253` 이 처음 적은 설계가 틀렸다 — *"큐가 안 주므로 claimer 는 자동으로 할 일이
없어진다"*. **일을 안 주는 것과 정리된 것은 다르다.**

## [중요] 잠긴 문 안을 보는 도구가 없었다

    `#210` 가드         미종결 work 가 있으면 전환을 **거절**한다 (문을 잠근다)
    `cleanup.py`        `verified`·`cancelled` 만 지운다 — `failed` 보존은 **의도**다
    `cleanup remote`    병합 확인분만 지운다 (`#219`)
    `set_active`        정리 호출 **0건** — 거절만 한다

즉 거절은 되는데 **무엇을 치워야 하는지 이름으로 말해 주는 것**이 없었다. 이 모듈이 그 자리다.

[중요] **조사만 한다 — 아무것도 지우지 않는다.** 지우는 주체·범위·`force` 는 `#253` 의
[미결] 셋이고 사용자 결정 자리다(이 저장소 관례: `plan` 이 기본, `apply` 는 대화형 세션이
부르지 않는다).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# [중요] 다섯 부류다. **하나라도 빠지면 미완**이라고 `#253` 완료 조건이 못박았다.
KINDS = ("queue", "workers", "remote_ephemeral", "remote_durable", "spool")

TERMINAL = ("merged", "rejected", "cancelled")      # task_queue.logic 과 같은 집합


@dataclass
class Leftover:
    """한 부류의 남은 것. [중요] **수가 아니라 이름**을 담는다 — 셈만 주면 사람이 판단할 수 없다."""

    kind: str
    names: list = field(default_factory=list)
    note: str = ""
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.names)


def _queue_leftovers(name: str, *, api=None) -> Leftover:
    """미종결 work·task. [중요] **프로젝트 스탬프로 거른다** — 백필(`#248`)이 그 선결이었다."""
    from ..task_queue import tagging                      # noqa: F401 — 태그 축의 정본 표시
    out = Leftover("queue")
    try:
        if api is None:
            from . import runner
            works = runner._api("GET", f"/api/v1/works?project={name}") or []
            tasks = runner._api(f"GET", f"/api/v1/tasks?project={name}&limit=500") or []
        else:
            works = api("GET", f"/api/v1/works?project={name}") or []
            tasks = api("GET", f"/api/v1/tasks?project={name}&limit=500") or []
    except Exception as e:                                 # noqa: BLE001
        out.error = f"큐를 못 봤다 — 아무것도 판정하지 않는다: {e}"
        return out
    # [주의] 스탬프가 **이 프로젝트인 것만** 센다. 필터는 옛 work(무스탬프)를 남기므로
    #    여기서 한 번 더 조인다 — 그러지 않으면 남의 프로젝트 잔재를 이 전환의 몫으로 센다.
    mine = [w for w in works
            if (w.get("project") or "").strip() == name
            and (w.get("merge_status") or "in_progress") not in TERMINAL]
    ids = {w.get("work_id") for w in mine}
    for w in mine:
        wt = [t.get("task_id") for t in tasks
              if t.get("work_id") == w.get("work_id")
              and (t.get("status") or "") not in ("verified", "cancelled")]
        out.names.append(f"{w.get('work_id')} [{w.get('merge_status') or 'in_progress'}]"
                         + (f" · 태스크 {len(wt)}" if wt else ""))
    orphan = [t.get("task_id") for t in tasks
              if t.get("work_id") not in ids
              and (t.get("status") or "") not in ("verified", "cancelled")]
    if orphan:
        out.names.extend(f"(고아 태스크) {t}" for t in orphan)
    out.note = "미종결 work 는 `#210` 가드가 **돌아올 때 전환을 다시 막는다**"
    return out


def _worker_leftovers(name: str, *, surveyor=None, prober=None) -> Leftover:
    """워커의 `.ax/work/<task_id>/` 부산물. 기계마다 이름을 낸다."""
    out = Leftover("workers")
    from ..client import bundle as _b
    from . import cleanup
    survey = surveyor or (lambda f: cleanup.survey(f))
    probe = prober or (lambda h, u, p, d, r: _b.probe(h, u, p, d, r))
    try:
        shops = _b.workshops(name)
    except Exception as e:                                 # noqa: BLE001
        out.error = f"작업장 목록을 읽지 못했다: {e}"
        return out
    for host, user, path, driven, role in shops:
        if role != "worker" or not user or not path:
            continue                    # [주의] 요청자(`.33`)는 사람의 기계다 — 세지 않는다
        try:
            facts = probe(host, user, path, driven, role)
            plan = survey(facts)
        except Exception as e:                             # noqa: BLE001
            out.names.append(f"{host}: (조사 실패 — {type(e).__name__}: {e})")
            continue
        # [주의] 실물 필드 이름과 모양을 **확인해서** 쓴다 — `HostPlan.drop_dirs`/`keep_dirs`
        #    는 `[(task_id, 사유)]` **튜플**이다. 추측해 문자열로 쓰면 `('t1', 'verified')`
        #    같은 것이 보고에 실린다.
        for task_id, why in list(getattr(plan, "drop_dirs", []) or []):
            out.names.append(f"{host}: {task_id} — {why} (지울 수 있다)")
        for task_id, why in list(getattr(plan, "keep_dirs", []) or []):
            out.names.append(f"{host}: {task_id} — {why} (보존)")
        for br, why in list(getattr(plan, "keep", []) or []):
            out.names.append(f"{host}: 브랜치 {br} — {why}")
        for err in list(getattr(plan, "errors", []) or []):
            out.names.append(f"{host}: (오류) {err}")
    out.note = "워커 부산물은 전환과 무관하게 남는다 — `cleanup apply` 가 지운다"
    return out


def _remote_leftovers(paths, *, git=None) -> tuple:
    """원격 브랜치를 **일회용(attempt)과 durable(task)로 갈라** 낸다.

    [중요] durable 은 원전대로 **보존**이 맞다 — 그래도 **셈은 남아야** 한다(`#253`).
    지우는 것과 세는 것은 다른 일이고, 세지 않으면 사람이 판단할 근거가 없다.
    """
    from . import cleanup
    from .branch_names import is_durable
    eph, dur = Leftover("remote_ephemeral"), Leftover("remote_durable")
    try:
        plan = cleanup.survey_remote(paths, git=git) if git else cleanup.survey_remote(paths)
    except Exception as e:                                 # noqa: BLE001
        eph.error = dur.error = f"원격을 못 봤다: {e}"
        return eph, dur
    if getattr(plan, "error", ""):
        eph.error = dur.error = plan.error
        return eph, dur
    # [주의] `keep` 이 **병합 안 된 것**이다 — 그것이 남은 것이다. `delete` 는 이미 도달 가능하다.
    for ref, tip, why in list(getattr(plan, "keep", [])):
        (dur if is_durable(ref) else eph).names.append(f"{ref} @{tip[:8]} — {why}")
    reachable = len(list(getattr(plan, "delete", [])))
    eph.note = f"병합 확인된 {reachable}건은 `cleanup remote --apply` 가 지운다"
    dur.note = "durable 미병합은 **사람 몫** — 원전대로 보존이 맞다(셈만 남긴다)"
    return eph, dur


def _spool_leftovers(paths) -> Leftover:
    """`<프로젝트>/responses/` 의 회수분."""
    out = Leftover("spool")
    try:
        d = paths.responses
    except AttributeError:
        out.error = "responses 경로를 모른다"
        return out
    if not d.is_dir():
        out.note = "스풀 디렉토리가 없다"
        return out
    for child in sorted(d.iterdir()):
        n = len(list(child.iterdir())) if child.is_dir() else 1
        out.names.append(f"{child.name}" + (f" ({n}건)" if child.is_dir() else ""))
    out.note = "스풀은 회수(`infer collect`) 뒤 남는다 — 전환하면 어느 프로젝트 것인지 흐려진다"
    return out


def survey_project(name: str, *, api=None, paths=None, git=None,
                   surveyor=None, prober=None) -> dict:
    """전환 전 인계 조사 — **다섯 부류 전부**. [중요] 아무것도 지우지 않는다.

    반환의 `clean` 은 *"전환해도 남는 것이 없다"* 이고, `unknown` 은 **못 본 부류가 있다**는
    뜻이다. [주의] 그 둘을 섞으면 「모르는데 깨끗하다」가 된다 — 조사 실패를 통과로 접지 않는다.
    """
    from ..context_search.paths import resolve
    p = paths or resolve(name)
    eph, dur = _remote_leftovers(p, git=git)
    kinds = {
        "queue": _queue_leftovers(name, api=api),
        "workers": _worker_leftovers(name, surveyor=surveyor, prober=prober),
        "remote_ephemeral": eph,
        "remote_durable": dur,
        "spool": _spool_leftovers(p),
    }
    missing = [k for k in KINDS if k not in kinds]
    assert not missing, f"부류가 빠졌다: {missing}"          # 완료 조건이 「다섯 전부」다
    unknown = [k for k, v in kinds.items() if v.error]
    total = sum(v.count for v in kinds.values())
    return {
        "project": name,
        "kinds": {k: {"count": v.count, "names": v.names, "note": v.note, "error": v.error}
                  for k, v in kinds.items()},
        "total": total,
        "unknown": unknown,
        # [중요] 못 본 부류가 있으면 **깨끗하다고 말하지 않는다** (fail-closed).
        "clean": total == 0 and not unknown,
        "note": ("남은 것이 없다 — 전환해도 잔재가 생기지 않는다" if total == 0 and not unknown
                 else f"못 본 부류 {len(unknown)}개 — 판정 불가: {', '.join(unknown)}"
                 if unknown and total == 0
                 else f"남은 것 {total}건" + (f" · 못 본 부류 {len(unknown)}개" if unknown else "")),
    }


def render(rep: dict) -> str:
    """사람이 읽을 보고. [중요] **이름을 낸다** — 셈만 주면 판단할 수 없다."""
    lines = [f"전환 인계 조사 — {rep['project']} · 남은 것 {rep['total']}건"]
    for kind in KINDS:
        k = rep["kinds"][kind]
        head = f"  [{kind}] {k['count']}건"
        if k["error"]:
            lines.append(f"{head} — [주의] {k['error']}")
            continue
        lines.append(head + (f" — {k['note']}" if k["note"] else ""))
        for n in k["names"][:20]:
            lines.append(f"      · {n}")
        if k["count"] > 20:
            lines.append(f"      … 그리고 {k['count'] - 20}건 더")
    lines.append(f"  → {rep['note']}")
    if not rep["clean"]:
        lines.append("  [중요] 지우는 주체·범위는 `#253` 의 [미결] — 이 도구는 **조사만** 한다")
    return "\n".join(lines)
