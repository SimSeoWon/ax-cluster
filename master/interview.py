"""착수 전 인터뷰 — 단계 기록과 진행 판정 (`#960` T2).

사용자 결정(2026-11-15, #960 인터뷰 노트): 인터뷰를 파라미터나 문서 서술로 두지 않고 **과정을 단계로 넣어
Python 이 거쳤는지 체크한다.** 질문 내용은 고정하지 않는다 — 내용은 세션의 LLM 이 만들고, 이 모듈은
**순서와 기록 여부**만 집행한다.

    분류(classify) → 조사(investigate) → 명세(specify) → 재현(reproduce) → 파급 측정(impact) → 스펙 영역

- 순서는 고정이다. 분류 뒤 단계 중 무엇을 하는지는 분류 문서 머리말 `steps` 가 정한다
  (`master/interview_categories.py`). 적용하지 않는 단계는 **이 모듈이 건너뜀 노트를 남긴다.**
- 각 단계는 결과 제시 → 사용자 확인 → **단계 노트**로 끝난다. 노트 첫 줄의 표지를 이 모듈이 붙인다:

      [ax:interview step=investigate category=bug v=1]

- 거절: 모르는 단계 · 순서 건너뜀 · 결과/사용자 답 빈칸 · 분류 전 다른 단계 · 플랜이 이미 있는 일감.
- 이미 거친 단계를 다시 기록할 수 있다(사용자가 「다르다」고 했을 때). 그러면 **최신 노트가 기준**이고,
  그 뒤 단계의 기록은 무효가 된다(앞 단계가 바뀌면 그 위에 쌓은 것도 다시 한다).
- 진행 상태는 **노트에서만** 복원한다 — 중단돼도 노트를 읽어 이어 간다(사용자: 「중간에 중단되어도
  해당 내용을 보고 추적할 수 있을 것 같네」).
- 사용자 답이 진짜인지는 판정하지 않는다(비범위) — 과정이 있었는지만 본다.
- 모든 단계를 거치면 `write_spec` 으로 스펙 영역(`master/spec_block.py`)을 쓴다 — 파급 측정 뒤에만 열린다.
  스펙 영역이 생기면 단계 기록은 닫힌다(인터뷰가 끝났다). 스펙을 고칠 때는 `write_spec` 을 다시 부른다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from master import interview_categories as IC
from master import plan_block as PB
from master import spec_block as SB

CLASSIFY = "classify"
ORDER: tuple[str, ...] = (CLASSIFY,) + IC.STEPS
# `#982` 트리거 A — 분류 응답에 싣는 질문(사실·선택지 서술). 답은 사용자에게서 받는다.
WAYFINDER_ASK = {
    "question": "이 신규 기능을 웨이파인더(맵 Root + 노드 일감)로 진행할까요? 아니면 단일 플로우로 진행할까요?",
    "how": "수락이면 ax-wayfinder 스킬 · 거절이면 이어서 조사 단계",
}
LABELS = {"classify": "분류", "investigate": "조사", "specify": "명세", "reproduce": "재현", "impact": "파급 측정"}
SPEC = "spec"                         # 모든 단계 뒤에 오는 자리 — 스펙 영역 기록(T3)
VERSION = 1
MARK = re.compile(r"^\[ax:interview ([^\]]*)\]")


class InterviewError(ValueError):
    """인터뷰 단계 기록 거절."""


class InterviewTransportError(InterviewError):
    """Redmine 읽기·쓰기 실패 — 판정이 아니다."""


@dataclass
class Record:
    step: str
    category: str
    skipped: bool
    text: str
    at: str = ""


@dataclass
class State:
    category: str = ""                                 # 분류가 아직 없으면 ""
    records: dict[str, Record] = field(default_factory=dict)   # 유효한 최신 기록 — ORDER 순
    next: str = CLASSIFY                               # 다음에 기록할 단계, 다 거쳤으면 SPEC
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"category": self.category, "next": self.next,
                "next_label": LABELS.get(self.next, "스펙 영역"),
                "done": [s for s in ORDER if s in self.records and not self.records[s].skipped],
                "skipped": [s for s in ORDER if s in self.records and self.records[s].skipped],
                "problems": self.problems}


def _attrs(line: str) -> dict | None:
    m = MARK.match(line.strip())
    if not m:
        return None
    return dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv)


def render(step: str, category: str, *, result: str = "", user_answer: str = "", skip_reason: str = "") -> str:
    head = f"[ax:interview step={step} category={category}{' skipped=1' if skip_reason else ''} v={VERSION}]"
    title = f"착수 전 인터뷰 — {LABELS[step]}"
    if skip_reason:
        return f"{head}\n{title} · 건너뜀\n\n사유: {skip_reason}"
    return f"{head}\n{title}\n\n## 결과\n\n{result.strip()}\n\n## 사용자 답\n\n{user_answer.strip()}"


def _invalidate_after(records: dict[str, Record], step: str) -> None:
    for s in ORDER[ORDER.index(step) + 1:]:
        records.pop(s, None)


def _applies(category: str, step: str, cats: dict) -> bool:
    cat = cats.get(category)
    return cat is None or cat.applies(step)


def _next(category: str, records: dict[str, Record], cats: dict) -> str:
    # `#969` ① — 분류 문서가 적용하지 않는 단계는 노트가 없어도 다음 단계가 아니다. 종전에는 건너뜀 노트
    #    (본 노트 뒤 두 번째 쓰기)만 빠져도 그 단계를 내놓아 기록이 양쪽으로 거절됐다(교착).
    if CLASSIFY not in records:
        return CLASSIFY
    for s in IC.STEPS:
        if s not in records and _applies(category, s, cats):
            return s
    return SPEC


def _missing_skips(category: str, records: dict[str, Record], cats: dict, nxt: str) -> list[str]:
    """다음 단계 앞인데 건너뜀 노트가 없는 미적용 단계 — 고장은 아니지만 기록이 빠졌음을 알린다."""
    before = IC.STEPS[:IC.STEPS.index(nxt)] if nxt in IC.STEPS else IC.STEPS
    return [s for s in before if s not in records and not _applies(category, s, cats)]


def state_of(journals: list, cats: dict | None = None) -> State:
    """노트(시간순)에서 인터뷰 진행 상태를 복원한다. 분류 문서가 깨졌으면 `CategoryError`."""
    cats = cats if cats is not None else IC.load()
    st = State()
    for j in journals or []:
        text = (j.get("notes") if isinstance(j, dict) else str(j)) or ""
        lines = text.replace("\r\n", "\n").split("\n", 1)
        a = _attrs(lines[0])
        if a is None:
            continue
        step, cat = a.get("step", ""), a.get("category", "")
        if step not in ORDER:
            st.problems.append(f"모르는 단계 표지 {step!r} — 무시")
            continue
        if step != CLASSIFY and cat != st.category:
            st.problems.append(f"{step}: 분류 {cat!r} ≠ 현재 분류 {st.category!r} — 무시")
            continue
        if step == CLASSIFY:
            if cat not in cats:
                st.problems.append(f"분류 노트의 분류 {cat!r} 가 분류 문서에 없다 — 무시")
                continue
            if cat != st.category:
                st.records.clear()
            st.category = cat
        _invalidate_after(st.records, step)
        st.records[step] = Record(step, cat, a.get("skipped") == "1", text, (j or {}).get("created_on", "")
                                  if isinstance(j, dict) else "")
    st.next = _next(st.category, st.records, cats)
    if st.category:
        for s in _missing_skips(st.category, st.records, cats, st.next):
            st.problems.append(f"{s}: 분류 {st.category!r} 가 적용하지 않는 단계인데 건너뜀 노트가 없다 "
                               "— 다음 단계 판정에는 영향이 없다(#969)")
    return st


def _plan_exists(body: str) -> bool:
    try:
        return PB.parse(body or "") is not None
    except PB.PlanError:
        return True


def _spec_exists(body: str) -> bool:
    try:
        return SB.exists(body or "")
    except SB.SpecError:
        return True


def _default_getter(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)


def _default_updater(issue_id, *, description: str, notes: str) -> str:
    from master import redmine
    return redmine.update_issue(issue_id, description=description, notes=notes)


def _default_noter(issue_id, notes: str) -> str:
    from master import redmine
    return redmine.update_issue(issue_id, notes=notes)


def _read(issue_id, getter) -> dict:
    got = getter(issue_id)
    if not isinstance(got, dict) or got.get("error"):
        reason = got.get("error") if isinstance(got, dict) else "응답 형식이 아니다"
        raise InterviewTransportError(f"#{issue_id} 를 읽지 못했다 — {reason}")
    return got


def _note(issue_id, text: str, noter) -> str:
    out = str(noter(issue_id, text))
    if out.startswith("[주의]"):
        raise InterviewTransportError(out)
    return out


def status(issue_id, *, getter=None, cats=None) -> dict:
    """읽기 전용 — 인터뷰가 어디까지 왔고 다음 단계가 무엇인지."""
    got = _read(issue_id, getter or _default_getter)
    cats = cats if cats is not None else IC.load()
    st = state_of(got.get("journals") or [], cats)
    body = got.get("description") or ""
    out = {"issue_id": issue_id, **st.as_dict(), "plan_exists": _plan_exists(body), "spec_exists": _spec_exists(body),
           "categories": [c.as_dict() for c in cats.values()]}
    if st.category:
        out["category_doc"] = cats[st.category].as_dict()["doc"]
        out["guide"] = cats[st.category].body      # 분류 문서 본문 — 파일을 못 읽는 표면(.33)도 같은 안내를 받는다
    return out


def record(issue_id, step: str, result: str, user_answer: str, *, category: str = "",
           getter=None, noter=None, cats=None) -> dict:
    """단계 하나를 기록한다. 적용하지 않는 뒤 단계는 건너뜀 노트로 이어서 남긴다.

    `category` 는 분류 단계에서만 받는다(다른 단계는 노트의 분류를 쓴다).
    """
    log: list[str] = []
    getter, noter = getter or _default_getter, noter or _default_noter
    cats = cats if cats is not None else IC.load()
    if step not in ORDER:
        raise InterviewError(f"모르는 단계 {step!r} — {list(ORDER)}")
    if not (result or "").strip():
        raise InterviewError(f"{LABELS[step]}: 결과가 비었다 — 사용자에게 보인 결과를 적는다")
    if not (user_answer or "").strip():
        raise InterviewError(f"{LABELS[step]}: 사용자 답이 비었다 — 결과를 보이고 확인받은 뒤 기록한다")
    got = _read(issue_id, getter)
    if _plan_exists(got.get("description") or ""):
        raise InterviewError(f"#{issue_id} 에 플랜 영역이 이미 있다 — 인터뷰가 아니라 플랜대로 진행한다")
    if _spec_exists(got.get("description") or ""):
        raise InterviewError(f"#{issue_id} 에 스펙 영역이 이미 있다 — 인터뷰는 끝났다. 스펙을 고치려면 write_spec")
    st = state_of(got.get("journals") or [], cats)
    if step == CLASSIFY:
        if category not in cats:
            raise InterviewError(f"분류 {category!r} 가 없다 — 등록된 분류 {sorted(cats)}")
        cat = category
    else:
        if category and category != st.category:
            raise InterviewError(f"분류는 분류 단계에서만 바꾼다 — 지금 {st.category!r}, 받은 값 {category!r}")
        if not st.category:
            raise InterviewError("분류가 먼저다 — 첫 질문으로 분류를 확정해 기록한다")
        cat = st.category
        if not cats[cat].applies(step):
            raise InterviewError(f"{LABELS[step]}: 분류 {cat!r} 문서가 이 단계를 적용하지 않는다")
    redo = step in st.records and not st.records[step].skipped
    if not redo and step != st.next:
        raise InterviewError(f"순서 건너뜀 — 다음 단계는 {LABELS.get(st.next, '스펙 영역')}({st.next}), "
                             f"받은 단계 {LABELS[step]}({step})")
    if step == CLASSIFY and st.records and st.category != cat:
        log.append(f"[interview] #{issue_id} 분류 변경 {st.category} → {cat} — 뒤 단계 기록 무효")
    elif redo:
        log.append(f"[interview] #{issue_id} {step} 재기록 — 최신 노트가 기준, 뒤 단계 기록 무효")
    written = [step]
    _note(issue_id, render(step, cat, result=result, user_answer=user_answer), noter)
    log.append(f"[interview] #{issue_id} {step} 기록 (분류 {cat})")
    # 기록 뒤 상태 — 적용하지 않는 단계를 건너뜀 노트로 남긴다
    records = dict(st.records)
    if step == CLASSIFY and st.category != cat:
        records.clear()
    _invalidate_after(records, step)
    records[step] = Record(step, cat, False, "")
    for s in IC.STEPS[IC.STEPS.index(step) + 1 if step in IC.STEPS else 0:]:
        if s in records or cats[cat].applies(s):
            break
        _note(issue_id, render(s, cat, skip_reason=f"분류 문서({cat})의 steps 에 이 단계가 없다"), noter)
        records[s] = Record(s, cat, True, "")
        written.append(f"{s}(건너뜀)")
        log.append(f"[interview] #{issue_id} {s} 건너뜀 — 분류 {cat}")
    nxt = _next(cat, records, cats)
    out = {"ok": True, "issue_id": issue_id, "step": step, "category": cat, "written": written,
           "next": nxt, "next_label": LABELS.get(nxt, "스펙 영역"),
           "category_doc": cats[cat].as_dict()["doc"], "guide": cats[cat].body, "log": log}
    # `#982` 트리거 A — 분류 문서 머리말 `wayfinder_ask` 가 참인 분류(신규 기능)만 확정 직후 묻는다.
    # [중요] 자동 경로로 모델에게 가는 글이라 명령형이 아니라 사실·선택지로 쓴다(명령형은 주입으로 거부된다).
    if step == CLASSIFY and cats[cat].wayfinder_ask:
        out["wayfinder_ask"] = dict(WAYFINDER_ASK)
        log.append(f"[interview] #{issue_id} 분류 {cat} — 웨이파인더 진행 여부 질문 첨부(wayfinder_ask)")
    return out


def write_spec(issue_id, content: str, user_answer: str, *, getter=None, updater=None, cats=None) -> dict:
    """인터뷰 마지막 — 확정 스펙(여섯 항목)을 스펙 영역에 쓴다. 본문의 영역 밖 글자는 그대로 둔다.

    파급 측정까지 모든 단계(또는 건너뜀)가 노트로 있어야 열린다. `user_answer` 는 요약을 보인 뒤 받은
    사용자 승인이다 — 비면 거절한다(진위는 판정하지 않는다).
    """
    getter, updater = getter or _default_getter, updater or _default_updater
    cats = cats if cats is not None else IC.load()
    if not (user_answer or "").strip():
        raise InterviewError("스펙 영역: 사용자 답이 비었다 — 요약을 보이고 승인받은 뒤 기록한다")
    got = _read(issue_id, getter)
    body = got.get("description") or ""
    if _plan_exists(body):
        raise InterviewError(f"#{issue_id} 에 플랜 영역이 이미 있다 — 스펙 영역은 플랜 전에 쓴다")
    st = state_of(got.get("journals") or [], cats)
    if st.next != SPEC:
        raise InterviewError(f"스펙 영역은 모든 단계 뒤에 쓴다 — 다음 단계는 "
                             f"{LABELS.get(st.next, st.next)}({st.next})")
    lack = SB.missing(content)
    if lack:
        raise InterviewError(f"스펙 여섯 항목 중 빠진 것 {lack} — docs/issue-spec.md §2 제목으로 쓴다")
    try:
        new_body = SB.put(body, content)
    except SB.SpecError as e:
        raise InterviewError(str(e)) from e
    replaced = SB.exists(body)
    note = (f"[ax:interview-spec v={SB.FORMAT_VERSION}]\n착수 전 인터뷰 — 스펙 영역 "
            f"{'갱신' if replaced else '기록'} (분류 {st.category})\n\n## 사용자 답\n\n{user_answer.strip()}")
    out = str(updater(issue_id, description=new_body, notes=note))
    if out.startswith("[주의]"):
        raise InterviewTransportError(out)
    return {"ok": True, "issue_id": issue_id, "category": st.category, "replaced": replaced,
            "next": "plan", "log": [f"[interview] #{issue_id} 스펙 영역 {'갱신' if replaced else '기록'}"]}
