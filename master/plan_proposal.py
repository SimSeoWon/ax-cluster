"""플랜 확정 — **제안 → 동의 → 등록** (`#963` T2).

사용자 결정(2026-11-15, #963 스펙 영역): 플랜 작성 한 자리에서 처리하던 것을 스펙 확정(#960)과 **플랜 확정**
두 단계로 나눈다. 플랜 확정은 세 칸이다.

    제안   propose(issue, tasks, checklist, why, autonomy)  → 표지 노트 [ax:plan-proposal v=1]
    동의   사용자가 표를 보고 동의하거나 고친다 — 고치면 다시 propose, **최신 제안이 기준**
    등록   plan_tools.set_plan(…, user_answer=…)            → 최신 제안과 같은 목록일 때만

- 제안 노트에는 사람이 읽는 표와, 대조에 쓰는 JSON 이 함께 실린다. 진행 상태는 노트에서만 복원한다.
- 제안은 **태스크 목록 + 개발 완료 체크리스트 + 자율성 값**(기본 0.5 · `#948` 이 세밀도를 정한다)이다.
- [중요] 제안 흐름에 들어온 일감(제안 노트가 하나라도 있거나 새 플랜)은 `set_plan` 이 제안과 대조한다. 제안 노트가
  하나도 없는 **옛 플랜 편집은 지금처럼** 동작한다(비범위: 소급).
- 플랜을 만드는 중에 모호하거나 정보가 없으면 사용자에게 묻는다 — 이 모듈이 그것을 대신하지 않는다.
"""
from __future__ import annotations

import json
import re

from master import plan_block as PB
from master import spec_block as SB

VERSION = 1
MARK = f"[ax:plan-proposal v={VERSION}]"
MARK_RE = re.compile(r"^\[ax:plan-proposal v=(\d+)\]")
JSON_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)


class ProposalError(PB.PlanError):
    """제안·대조 규칙 거절 — `PlanError` 계열이라 기존 표면이 같은 모양(plan_refused)으로 돌려준다."""


def _deps_of(raw) -> list[str]:
    if isinstance(raw, str):
        return [d.strip() for d in re.split(r"[·,]", raw) if d.strip() and d.strip() != PB.NO_DEPS]
    return [str(d).strip() for d in (raw or []) if str(d).strip()]


def _steps_of(raw) -> list[int]:
    if isinstance(raw, str):
        return sorted({int(x) for x in re.split(r"[·,]", raw) if x.strip().isdigit()})
    return sorted({int(x) for x in (raw or [])})


def normalize_tasks(tasks) -> list[dict]:
    """대조용 태스크 목록 — 상태·근거는 받지 않는다(set_plan 과 같은 규칙)."""
    if not isinstance(tasks, list) or not tasks:
        raise ProposalError("tasks 가 비었다")
    out = []
    for raw in tasks:
        if not isinstance(raw, dict):
            raise ProposalError(f"태스크 항목이 객체가 아니다: {raw!r}")
        banned = [k for k in ("state", "evidence") if k in raw]
        if banned:
            raise ProposalError(f"{raw.get('id', '?')}: {', '.join(banned)} 는 제안에 넣지 않는다 — 상태는 전이 도구로만")
        tid, goal = str(raw.get("id") or "").strip(), str(raw.get("goal") or "").strip()
        if not tid or not goal:
            raise ProposalError(f"id·goal 은 필수다: {raw!r}")
        out.append({"id": tid, "goal": goal, "target": str(raw.get("target") or "").strip(),
                    "deps": _deps_of(raw.get("deps")), "check": str(raw.get("check") or "").strip(),
                    "steps": _steps_of(raw.get("steps"))})
    return out


def normalize_checklist(items) -> list[dict]:
    """체크리스트 — 문자열 목록이거나 {id?, item} 목록. ID 가 없으면 C1… 순서로 붙인다."""
    out = []
    for i, raw in enumerate(items or [], 1):
        if isinstance(raw, str):
            cid, item = f"C{i}", raw.strip()
        elif isinstance(raw, dict):
            cid, item = str(raw.get("id") or f"C{i}").strip(), str(raw.get("item") or "").strip()
        else:
            raise ProposalError(f"체크리스트 항목이 문자열·객체가 아니다: {raw!r}")
        if not item:
            raise ProposalError(f"{cid}: 체크리스트 항목이 비었다")
        out.append({"id": cid, "item": item})
    return out


def to_tasks(norm: list[dict], old: dict) -> list[PB.Task]:
    """정규화 목록 → Task. 이미 있던 태스크는 상태·근거를 지킨다."""
    from master import plan_state as PS
    return [PB.Task(t["id"], old[t["id"]].state if t["id"] in old else PS.WAITING, t["goal"], t["target"],
                    list(t["deps"]), t["check"], old[t["id"]].evidence if t["id"] in old else "", list(t["steps"]))
            for t in norm]


def to_checklist(norm: list[dict], old: list[PB.Check]) -> list[PB.Check]:
    prev = {c.id: c for c in old}
    return [PB.Check(c["id"], prev[c["id"]].state if c["id"] in prev else "미확인", c["item"],
                     prev[c["id"]].evidence if c["id"] in prev else "") for c in norm]


def _draft(body: str, tasks: list[dict], checklist: list[dict], autonomy: float) -> str:
    """제안이 실제 플랜 형식으로 성립하는지 — 선행·ID 규칙은 plan_block 이 판정한다."""
    current = PB.parse(body)
    old = {t.id: t for t in (current.tasks if current else [])}
    new = to_tasks(tasks, old)
    cl = to_checklist(checklist, current.checklist if current else [])
    out = PB.replace(body, new, checklist=cl, autonomy=autonomy) if current else \
        PB.append(body, new, checklist=cl, autonomy=autonomy)
    PB.parse(out)
    return out


def render_note(prop: dict, why: str) -> str:
    rows = ["| ID | 목표 | 대상 | 선행 | 검증 |", "|---|---|---|---|---|"]
    for t in prop["tasks"]:
        rows.append(f"| {t['id']} | {t['goal']} | {t['target']} | {'·'.join(t['deps']) or PB.NO_DEPS} | {t['check']} |")
    checks = [f"- {c['id']} {c['item']}" for c in prop["checklist"]] or ["- (없음)"]
    data = json.dumps(prop, ensure_ascii=False, indent=1)
    return (f"{MARK}\n플랜 제안 — 태스크 {len(prop['tasks'])} · 체크리스트 {len(prop['checklist'])} · "
            f"자율성 {prop['autonomy']:g}\n\n사유: {why.strip()}\n\n" + "\n".join(rows)
            + "\n\n개발 완료 체크리스트\n\n" + "\n".join(checks) + f"\n\n```json\n{data}\n```")


def proposals(journals) -> list[dict]:
    """노트(시간순) 속 제안들. 표지는 있는데 JSON 이 깨진 것은 `broken` 으로 싣는다."""
    out = []
    for j in journals or []:
        text = ((j.get("notes") if isinstance(j, dict) else str(j)) or "").replace("\r\n", "\n")
        if not MARK_RE.match(text):
            continue
        m = JSON_RE.search(text)
        try:
            data = json.loads(m.group(1)) if m else None
        except json.JSONDecodeError:
            data = None
        # `#969` ③ — 객체여도 필수 키가 빠지면 깨진 제안이다(종전: 대조 자리에서 KeyError)
        ok = isinstance(data, dict) and isinstance(data.get("tasks"), list) \
            and isinstance(data.get("checklist"), list) and "autonomy" in data
        out.append(data if ok else {"broken": True})
    return out


def latest(journals) -> dict | None:
    got = proposals(journals)
    return got[-1] if got else None


def _default_getter(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)


def _default_noter(issue_id, notes: str) -> str:
    from master import redmine
    return redmine.update_issue(issue_id, notes=notes)


def _read(issue_id, getter) -> dict:
    got = getter(issue_id)
    if not isinstance(got, dict) or got.get("error"):
        reason = got.get("error") if isinstance(got, dict) else "응답 형식이 아니다"
        raise PB.PlanError(f"#{issue_id} 를 읽지 못했다 — {reason}")
    return got


def propose(issue_id, tasks, checklist, why: str, *, autonomy=None, getter=None, noter=None) -> dict:
    """플랜 제안을 노트로 남긴다. `autonomy` 를 비우면 지금 플랜 값(없으면 0.5)."""
    getter, noter = getter or _default_getter, noter or _default_noter
    if not (why or "").strip():
        raise ProposalError("why 가 비었다 — 무엇을 근거로 이 표를 제안하는지 노트로 남긴다")
    norm = normalize_tasks(tasks)
    cl = normalize_checklist(checklist)
    got = _read(issue_id, getter)
    body = got.get("description") or ""
    current = PB.parse(body)
    if current is None:
        try:
            has_spec = SB.exists(body)
        except SB.SpecError as e:
            raise ProposalError(f"스펙 영역이 깨졌다 — {e}") from e
        if not has_spec:
            raise ProposalError("스펙 영역이 없다 — 착수 전 인터뷰를 마친 뒤 플랜을 제안한다 (#960)")
    value = PB.autonomy_value(autonomy) if autonomy is not None else (current.autonomy if current else
                                                                      PB.DEFAULT_AUTONOMY)
    _draft(body, norm, cl, value)                     # 형식·선행 규칙을 지금 판정한다
    prop = {"tasks": norm, "checklist": cl, "autonomy": value}
    out = str(noter(issue_id, render_note(prop, why)))
    if out.startswith("[주의]"):
        raise PB.PlanError(out)
    return {"ok": True, "issue_id": issue_id, "tasks": [t["id"] for t in norm],
            "checklist": [c["id"] for c in cl], "autonomy": value, "next": "동의를 받아 plan_set(user_answer=…)",
            "log": [f"[plan_proposal] #{issue_id} 제안 — 태스크 {len(norm)} · 체크리스트 {len(cl)} · 자율성 {value:g}"]}


def gate(journals, body: str, tasks, user_answer: str) -> dict | None:
    """`set_plan` 이 부른다. 제안 흐름이면 대조 뒤 등록할 제안을, 옛 플랜 편집이면 None.

    제안 흐름 = 새 플랜이거나 제안 노트가 하나라도 있는 일감.
    """
    current = PB.parse(body)
    props = proposals(journals)
    if current is not None and not props:
        return None                                    # 옛 플랜 편집 — 지금처럼(비범위: 소급)
    if not props:
        raise ProposalError("플랜 제안이 없다 — 표를 보이고 plan_propose 로 제안을 남긴 뒤 동의를 받아 등록한다 (#963)")
    prop = props[-1]
    if prop.get("broken"):
        raise ProposalError("최신 플랜 제안 노트의 JSON 이 깨졌다 — 다시 제안한다")
    if not (user_answer or "").strip():
        raise ProposalError("사용자 답이 비었다 — 최신 제안에 대한 사용자 동의를 user_answer 로 싣는다")
    norm = normalize_tasks(tasks)
    if norm != prop["tasks"]:
        want, got_ids = [t["id"] for t in prop["tasks"]], [t["id"] for t in norm]
        diff = next((t["id"] for t, p in zip(norm, prop["tasks"]) if t != p), None)
        raise ProposalError(f"최신 제안과 다른 목록이다 — 제안 {want} · 받은 것 {got_ids}"
                            + (f" · 처음 다른 태스크 {diff}" if diff else "") + " — 바꾸려면 다시 제안한다")
    return prop


# ── 자율성 변경과 재플랜 (`#963` T5) ─────────────────────────────────────────────────────────────

AUTONOMY_MARK = f"[ax:plan-autonomy v={VERSION}]"


def _task_dict(t: PB.Task) -> dict:
    return {"id": t.id, "goal": t.goal, "target": t.target, "deps": list(t.deps), "check": t.check,
            "steps": list(t.steps)}


def change_autonomy(issue_id, value, why: str, *, tasks=None, getter=None, noter=None) -> dict:
    """자율성 값을 바꾸고 **대기 태스크만** 다시 짠 플랜 제안을 남긴다 — 등록은 동의 뒤 `set_plan`.

    `tasks` 는 세션이 사용자와 다시 짠 **대기 태스크 목록**이다(비우면 지금 대기 태스크 그대로 재제안). 시작된
    태스크(작업중·완료·차단·해당없음)와 근거, 개발 완료 체크리스트는 그대로 제안에 옮긴다. 값↔세밀도 대응은
    `#948` 의 몫이라 이 함수는 태스크를 스스로 쪼개거나 묶지 않는다.
    """
    from master import plan_state as PS
    getter, noter = getter or _default_getter, noter or _default_noter
    if not (why or "").strip():
        raise ProposalError("why 가 비었다 — 자율성을 왜 바꾸는지 노트로 남긴다")
    new_value = PB.autonomy_value(value)
    got = _read(issue_id, getter)
    body = got.get("description") or ""
    plan = PB.parse(body)
    if plan is None:
        raise ProposalError("플랜 영역이 없다 — 자율성은 플랜 제안(plan_propose)의 autonomy 로 정한다")
    started = [t for t in plan.tasks if t.state != PS.WAITING]
    kept = [_task_dict(t) for t in started]
    if tasks is None:
        waiting = [_task_dict(t) for t in plan.tasks if t.state == PS.WAITING]
    else:
        waiting = normalize_tasks(tasks) if tasks else []
        clash = sorted({t["id"] for t in waiting} & {t.id for t in started})
        if clash:
            raise ProposalError(f"시작된 태스크 ID 를 대기 목록에 쓸 수 없다: {', '.join(clash)} — 시작된 태스크는 그대로 둔다")
    full = kept + waiting
    if not full:
        raise ProposalError("태스크가 하나도 없다 — 대기 태스크 목록을 준다")
    cl = [{"id": c.id, "item": c.item} for c in plan.checklist]
    _draft(body, full, cl, new_value)                 # 선행·ID 규칙 판정(시작된 태스크 상태 보존 포함)
    old_value = plan.autonomy
    hist = (f"{AUTONOMY_MARK}\n자율성 {old_value:g} → {new_value:g}\n\n사유: {why.strip()}\n"
            f"보존: 시작된 태스크 {', '.join(t.id for t in started) or '없음'} · 체크리스트 {len(cl)}개\n"
            f"재제안: 대기 태스크 {', '.join(t['id'] for t in waiting) or '없음'}")
    out = str(noter(issue_id, hist))
    if out.startswith("[주의]"):
        raise PB.PlanError(out)
    prop = {"tasks": full, "checklist": cl, "autonomy": new_value}
    out = str(noter(issue_id, render_note(prop, f"자율성 {old_value:g} → {new_value:g} 재플랜 — {why.strip()}")))
    if out.startswith("[주의]"):
        raise PB.PlanError(out)
    return {"ok": True, "issue_id": issue_id, "autonomy": {"from": old_value, "to": new_value},
            "kept": [t["id"] for t in kept], "replanned": [t["id"] for t in waiting], "tasks": [t["id"] for t in full],
            "next": "제안 표를 보이고 동의를 받아 plan_set(tasks=제안 목록, user_answer=…)",
            "log": [f"[plan_proposal] #{issue_id} 자율성 {old_value:g} → {new_value:g} · 보존 {len(kept)} · 재제안 {len(waiting)}"]}
