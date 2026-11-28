"""대화 장부 — 질문 장부와 입력 장부, 그리고 답 판정 (`#1040`).

사용자 결정(2026-11-28, #1040 인터뷰 노트): 인터뷰·플랜 단계는 **사용자와 실제 문답이 있었을 때만** 기록된다.
산문 규칙(「명시적 「예」」)은 지휘 모델이 「해당 없음」으로 넘길 수 있어서 #1037(11-27 22:15)에서
승인 아닌 답이 분류 승인으로 기록됐다. 이 모듈은 그 판정을 코드로 옮긴다.

    질문 장부   ask(issue, stage, question, recommended, alternatives, confidence, gaps)
                — 단계마다 묻기 전에 등록한다. 추천 1번 필수 · 대안 0~3 · 확신도 0~100.
    입력 장부   record_prompt(text, session, source)
                — `UserPromptSubmit` 훅이 사용자의 **실제 입력 원문**을 적는다(모델이 쓰지 않는다).
    판정        judge(issue, stage, user_answer, divergence, divergence_reason)
                — ① 그 단계의 질문이 있다 ② 답이 질문 **뒤** 실제 입력과 원문으로 같다
                  ③ 답이 보기 선택이거나 명시적 긍정이다. 자유 의견이면 「수정 요청」으로 돌려준다.
                — 확신도: 추천 선택·어긋남 없음이면 오르고, 보강·수정·뒤집기면 깎인다.
                  어긋남 등급과 이유는 에이전트가 적고, 계산과 일관성 검사는 여기서 한다.

[주의] 확신도 점수로 진행을 막지 않는다 — 에이전트 자기 평가라 검증할 수 없다(사용자 결정). 막는 것은
검증할 수 있는 것(질문 등록 · 원문 일치 · 답의 형태 · 등급의 일관성)뿐이다.
[주의] 깎는 폭은 첫 값이다 — 실사용하며 고친다(사용자 결정, #1040 열린 결정).

관문은 프로젝트 트윈 `config.yaml` 의 `interview_gate: enforce` 일 때만 켜진다(기본 꺼짐). 훅 배달이
서버 조임보다 먼저다(`docs/13` §13.6) — 배달·check 를 확인한 뒤 켠다.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

SCHEMA = 1
STATE_NAME = "interview_ledger.json"
LOCK_NAME = ".interview_ledger.lock"
CAP = 300                                   # 질문·입력 각각 최근 N 건만 남긴다

STEPS = ("classify", "investigate", "specify", "reproduce", "impact")
STAGES = STEPS + ("spec", "plan", "decision")   # decision = 인터뷰 밖 진행 중 결정(멈춤 사유로도 쓴다)
GATED = STEPS + ("spec", "plan")
MAX_ALTERNATIVES = 3
GAPS_BELOW = 70                             # 이보다 낮으면 「빈 것」을 적어야 한다

NONE, ADD, REVISE, FLIP = "none", "add", "revise", "flip"
DIVERGENCE = {NONE: "어긋남 없음", ADD: "보강", REVISE: "수정", FLIP: "뒤집기"}
CONFIRM, FOLLOWUP, STOP = "confirm", "followup", "stop"
RAISE = 20                                  # 추천 선택·어긋남 없음

GATE_KEY, GATE_ON = "interview_gate", "enforce"


class LedgerError(ValueError):
    """장부 규칙 거절 — 사유 문장을 담는다. 아무것도 쓰지 않았다."""


# ── 저장 ────────────────────────────────────────────────────────────────────

def default_root(project: str = "") -> Path:
    from master import issue_lock as IL
    return IL.default_root(project) if project else IL.default_root()


def _path(root) -> Path:
    return Path(root) / STATE_NAME


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _load(root) -> dict:
    p = _path(root)
    if not p.exists():
        return {"schema": SCHEMA, "questions": [], "prompts": [], "failures": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise LedgerError(f"대화 장부를 못 읽었다 ({p}: {type(e).__name__}) — 덮어쓰지 않았다") from e
    if (not isinstance(data, dict) or data.get("schema") != SCHEMA
            or not isinstance(data.get("questions"), list) or not isinstance(data.get("prompts"), list)
            or not isinstance(data.setdefault("failures", []), list)):
        raise LedgerError(f"대화 장부 형식이 아니다 ({p}) — 덮어쓰지 않았다")
    return data


def _save(root, data: dict) -> None:
    for key in ("questions", "prompts", "failures"):
        if len(data[key]) > CAP:
            del data[key][:len(data[key]) - CAP]
    p = _path(root)
    tmp = p.with_name(f"{STATE_NAME}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


@contextmanager
def _locked(root):
    d = Path(root)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / LOCK_NAME, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def gate_enabled(project: str = "", *, registry=None) -> bool:
    """프로젝트 트윈 `config.yaml` 의 `interview_gate: enforce` — 기본 꺼짐. 못 읽으면 꺼짐(종전 동작)."""
    try:
        if registry is None:
            from master.projects.config import Registry
            registry = Registry.load()
        name = project or registry.active
        return str(registry.config_of(name).raw.get(GATE_KEY, "")).strip() == GATE_ON
    except Exception:                                    # noqa: BLE001 — 설정 못 읽음 = 관문 꺼짐
        return False


# ── 질문 장부 ────────────────────────────────────────────────────────────────

def _text(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{what} 이(가) 비었다")
    return value.strip()


def ask(root, issue_id, stage: str, question: str, recommended: str, alternatives=(), confidence=None,
        gaps: str = "", *, prompt_id: str = "", require_prompt: bool = False) -> dict:
    """질문 하나를 등록한다. 같은 일감·단계의 답 안 받은 앞 질문은 이 질문으로 대체된다."""
    n = int(issue_id)
    if stage not in STAGES:
        raise LedgerError(f"모르는 단계 {stage!r} — {list(STAGES)}")
    q = _text(question, "질문")
    rec = _text(recommended, "추천 1번")
    alts = list(alternatives or [])
    if len(alts) > MAX_ALTERNATIVES:
        raise LedgerError(f"대안은 {MAX_ALTERNATIVES}개까지다 — 받은 {len(alts)}개")
    alts = [_text(a, f"대안 {i + 2}번") for i, a in enumerate(alts)]
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise LedgerError("확신도는 0~100 정수다")
    gaps = (gaps or "").strip()
    if confidence < GAPS_BELOW and not gaps:
        raise LedgerError(f"확신도 {confidence} < {GAPS_BELOW} — 무엇이 비었는지(gaps)를 적는다")
    item = {"id": uuid4().hex[:12], "issue_id": n, "stage": stage, "at": _now(), "question": q,
            "recommended": rec, "alternatives": alts, "confidence": confidence, "gaps": gaps,
            "status": "open"}
    with _locked(root):
        data = _load(root)
        if prompt_id or require_prompt:
            prompt = _current_prompt(data, prompt_id)
            item.update(session=prompt["session"], opened_by=prompt["id"])
        for old in data["questions"]:
            if (old["issue_id"] == n and old["stage"] == stage and old["status"] == "open"
                    and old.get("session") == item.get("session")):
                old["status"] = "replaced"
        data["questions"].append(item)
        _save(root, data)
    return {"ok": True, **item, "log": [f"[ledger] #{n} {stage} 질문 등록 — 확신도 {confidence} · 대안 {len(alts)}"]}


def open_questions(root, issue_id=None) -> list[dict]:
    """답을 기다리는 질문 — 질문 뒤에 사용자 입력이 아직 없는 것."""
    with _locked(root):
        data = _load(root)
    last_prompt = data["prompts"][-1]["at"] if data["prompts"] else ""
    out = []
    for q in data["questions"]:
        if q["status"] != "open" or (issue_id is not None and q["issue_id"] != int(issue_id)):
            continue
        if not last_prompt or last_prompt < q["at"]:
            out.append(dict(q))
    return out


# ── 입력 장부 ────────────────────────────────────────────────────────────────

def record_prompt(root, text: str, *, session: str = "", source: str = "") -> dict:
    """사용자 입력 원문 한 건 — 훅만 부른다. 빈 입력은 남기지 않는다."""
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "why": "빈 입력"}
    item = {"id": uuid4().hex, "at": _now(), "text": text, "session": str(session or "")[:80],
            "source": str(source or "")[:40]}
    with _locked(root):
        data = _load(root)
        data["prompts"].append(item)
        data.setdefault("stop_blocks", {}).pop(item["session"] or "-", None)   # 새 입력 = 연속 차단 초기화
        _save(root, data)
    return {"ok": True, "id": item["id"], "at": item["at"]}


def _current_prompt(data: dict, prompt_id: str) -> dict:
    """훅이 발급한 현재 턴의 입력 ID에서 세션을 확인한다."""
    if not prompt_id:
        raise LedgerError("입력 훅에서 받은 현재 턴의 prompt_id가 필요하다")
    seen: set[str] = set()
    for prompt in reversed(data["prompts"]):
        session = prompt.get("session")
        if not session or session in seen:
            continue
        if prompt["id"] == prompt_id:
            return prompt
        seen.add(session)
    raise LedgerError("입력 장부에서 해당 세션의 현재 사용자 입력을 확인할 수 없다")


def assess_answer(root, issue_id, stage: str, user_answer: str, *, prompt_id: str, action: str,
                  divergence: str, divergence_reason: str, option: int = 0) -> dict:
    """LLM이 해석한 답을 장부에 대조하고 확정·후속 질문·중단 상태를 기록한다."""
    n = int(issue_id)
    reason = _text(divergence_reason, "답변 해석 근거")
    if action not in (CONFIRM, FOLLOWUP, STOP):
        raise LedgerError("답변 해석은 confirm, followup, stop 중 하나다")
    if divergence not in DIVERGENCE:
        raise LedgerError("답변의 어긋남 등급(divergence)이 필요하다")
    with _locked(root):
        data = _load(root)
        prompt = _current_prompt(data, prompt_id)
        if prompt["text"] != user_answer:
            raise LedgerError("답변 원문이 현재 턴의 실제 사용자 입력과 일치하지 않는다")
        q = next((entry for entry in reversed(data["questions"])
                  if entry["issue_id"] == n and entry["stage"] == stage
                  and entry.get("session") == prompt["session"] and entry["status"] == "open"), None)
        if q is None or prompt["at"] <= q["at"]:
            raise LedgerError(f"#{n} {stage}: 같은 세션에 답변보다 먼저 등록된 질문이 없다")
        if any(entry.get("prompt_id") == prompt_id for entry in data["questions"]):
            raise LedgerError("같은 턴의 사용자 답변이 이미 처리됐다")
        if type(option) is not int or not 0 <= option <= len(q["alternatives"]) + 1:
            raise LedgerError("선택 번호가 등록된 보기 범위를 벗어난다")
        if option > 1 and divergence == NONE:
            raise LedgerError("대안 선택에는 추천안과의 차이를 기록한다")
        after = confidence_after(q["confidence"], divergence)
        status = {CONFIRM: "answered", FOLLOWUP: "followup_required", STOP: "stopped"}[action]
        q.update(status=status, answered_at=_now(), prompt_id=prompt_id, pick=option,
                 action=action, divergence=divergence, divergence_reason=reason, confidence_after=after)
        _save(root, data)
    line = f"확신도 {q['confidence']} → {after} · {DIVERGENCE[divergence]} — {reason}"
    return {"ok": True, "status": status, "question_id": q["id"], "user_answer": user_answer,
            "note_line": line, "pick": option}


# ── 답 판정 ──────────────────────────────────────────────────────────────────

# 명시적 긍정 — 낱말이 **전부** 이 목록이어야 한다(「응 진행해」는 긍정, 「응 근데 …」는 자유 의견).
_AFFIRM_WORDS = frozenset((
    "응", "네", "넵", "예", "그래", "좋아", "좋습니다", "맞아", "맞습니다", "이대로", "그대로", "그렇게",
    "확정", "확정해", "확정하자", "진행", "진행해", "진행하자", "등록", "등록해", "등록하자",
    "기록", "기록해", "기록하자", "가자", "해", "해줘", "ok", "okay", "yes"))
_WORD = re.compile(r"[가-힣A-Za-z]+")
_PICK = re.compile(r"(?:^|[^0-9])([1-4])\s*번")


def _affirm(answer: str) -> bool:
    words = [w.casefold() for w in _WORD.findall(answer)]
    return bool(words) and all(w in _AFFIRM_WORDS for w in words)


def classify_answer(answer: str, n_alternatives: int) -> tuple[str, int]:
    """답의 형태 → (`recommended`·`alternative`·`affirm`·`free`, 고른 번호 또는 0)."""
    m = _PICK.search(answer)
    if m:
        k = int(m.group(1))
        if k == 1:
            return "recommended", 1
        if k - 1 <= n_alternatives:
            return "alternative", k
    if _affirm(answer):
        return "affirm", 1
    return "free", 0


def confidence_after(before: int, divergence: str) -> int:
    if divergence == NONE:
        return min(100, before + RAISE)
    if divergence == ADD:
        return max(0, before - 10)
    if divergence == REVISE:
        return before // 2
    return 0


def judge(root, issue_id, stage: str, user_answer: str, *, divergence: str = "",
          divergence_reason: str = "") -> dict:
    """그 단계 질문에 대한 실제 답인지 판정하고 질문을 닫는다. 기록해도 되면 ok, 아니면 `LedgerError`.

    자유 의견은 질문을 「수정 요청」으로 닫고(확신도 갱신) `LedgerError` — 에이전트는 반영해 다시 묻는다.
    """
    n = int(issue_id)
    answer = _text(user_answer, "사용자 답")
    if divergence not in DIVERGENCE:
        raise LedgerError(f"어긋남 등급(divergence)을 적는다 — {list(DIVERGENCE)} 중 하나")
    with _locked(root):
        data = _load(root)
        qs = [q for q in data["questions"] if q["issue_id"] == n and q["stage"] == stage and q["status"] == "open"]
        if not qs:
            raise LedgerError(f"#{n} {stage}: 등록된 질문이 없다 — interview_ask 로 먼저 묻고 실제 답을 받는다")
        q = qs[-1]
        match = [p for p in data["prompts"] if p["at"] > q["at"] and p["text"].strip() == answer]
        if not match:
            raise LedgerError(f"#{n} {stage}: 답이 질문 뒤 사용자의 실제 입력과 원문으로 같지 않다 — "
                              "사용자가 입력한 문장을 그대로 넣는다")
        kind, pick = classify_answer(answer, len(q["alternatives"]))
        if kind in ("alternative", "free") and divergence == NONE:
            raise LedgerError(f"#{n} {stage}: 추천 1번이 아닌 답({kind})에 「어긋남 없음」을 적을 수 없다")
        if divergence != NONE and not (divergence_reason or "").strip():
            raise LedgerError(f"#{n} {stage}: 어긋남 {DIVERGENCE[divergence]} — 이유(divergence_reason)를 적는다")
        after = confidence_after(q["confidence"], divergence)
        q.update(status="revision" if kind == "free" else "answered", answered_at=_now(),
                 prompt_id=match[-1]["id"], kind=kind, pick=pick, divergence=divergence,
                 divergence_reason=(divergence_reason or "").strip(), confidence_after=after)
        _save(root, data)
    line = (f"확신도 {q['confidence']} → {after} · {DIVERGENCE[divergence]}"
            + (f" — {q['divergence_reason']}" if q["divergence_reason"] else "")
            + f" · 답 형태 {kind}" + (f" {pick}번" if pick else ""))
    if kind == "free":
        raise LedgerError(f"#{n} {stage}: 보기 선택·명시적 긍정이 아니다 — 수정 요청으로 반영해 결과를 다시 "
                          f"보이고 새로 묻는다 ({line})")
    return {"ok": True, "question_id": q["id"], "kind": kind, "pick": pick, "confidence_before": q["confidence"],
            "confidence_after": after, "note_line": line}


def check_answer(issue_id, stage: str, user_answer: str, *, divergence: str = "", divergence_reason: str = "",
                 project: str = "", root=None, enabled=None) -> dict | None:
    """기록 도구(인터뷰 단계·스펙 영역·플랜 등록)가 **쓰기 직전에** 부른다. 관문이 꺼졌으면 None(종전 동작).

    켜졌으면 `judge` 결과(확신도 줄 포함) — 거절이면 `LedgerError`. 판정은 질문을 닫으므로 다른 검사를 다
    통과한 뒤에 부른다.
    """
    if enabled is None:
        enabled = gate_enabled(project)
    if not enabled:
        return None
    return judge(default_root(project) if root is None else root, issue_id, stage, user_answer,
                 divergence=divergence, divergence_reason=divergence_reason)


# ── 실패 장부 (③, T4) ─────────────────────────────────────────────────────────
# 공용 규칙 §1.1(「실패하면 보고하고 멈춘다」)과 `plan_start` 의 resume 이 부딪혔다(#1039 00:35): 판정에 실패
# 정보가 없어서 모델이 둘 중 하나를 골랐다. 여기 적힌 실패를 `plan_tools.start` 가 읽어 갈라 준다 —
# 실패 경로가 **이번 일감의 변경**(시작 리비전 이후 커밋 + 미커밋) 안이면 resume(고치고 계속), 밖이거나
# 경로를 모르면 stop(보고). [주의] 「미커밋만」으로 보면 00:35 사례(T1 에 커밋된 SKILL.md)가 stop 이 된다.

def record_check(root, issue_id, check: str, rc: int, *, paths=(), summary: str = "") -> dict:
    """검사 결과 한 건. rc 0 이면 같은 검사의 열린 실패를 닫고, 아니면 열린 실패로 남긴다(같은 검사는 교체)."""
    n = int(issue_id)
    name = _text(check, "검사 이름")
    if isinstance(rc, bool) or not isinstance(rc, int):
        raise LedgerError("rc 는 정수다")
    clean = sorted({str(x).strip().lstrip("./") for x in (paths or []) if str(x).strip()})
    with _locked(root):
        data = _load(root)
        closed = 0
        for f in data["failures"]:
            if f["issue_id"] == n and f["check"] == name and f["status"] == "open":
                f["status"] = "passed" if rc == 0 else "replaced"
                f["closed_at"] = _now()
                closed += 1
        if rc != 0:
            data["failures"].append({"id": uuid4().hex[:12], "issue_id": n, "check": name, "rc": rc,
                                     "paths": clean, "summary": (summary or "").strip()[:500], "at": _now(),
                                     "status": "open"})
        _save(root, data)
    return {"ok": True, "issue_id": n, "check": name, "rc": rc, "closed": closed, "open": rc != 0}


def open_failures(root, issue_id) -> list[dict]:
    with _locked(root):
        data = _load(root)
    return [dict(f) for f in data["failures"] if f["issue_id"] == int(issue_id) and f["status"] == "open"]


def split_failures(failures: list[dict], changed) -> tuple[list[dict], list[dict]]:
    """(이번 일감 변경 안의 실패, 그 밖의 실패). 경로가 없거나 변경 목록을 모르면(`changed=None`) 밖으로 친다."""
    if changed is None:
        return [], list(failures)
    changed = {str(c).strip().lstrip("./") for c in changed}
    own, foreign = [], []
    for f in failures:
        (own if f["paths"] and all(p in changed for p in f["paths"]) else foreign).append(f)
    return own, foreign


# ── 멈춤 판정 (②, T5) ─────────────────────────────────────────────────────────
# #1039 00:27: plan_start 가 resume 을 줬는데 지휘자가 「재개했다」고 말하고 턴을 끝냈다. 막는 장치가 없었다.
# Stop 훅이 이 판정을 묻는다. 막는 것은 **일감 잠금이 활성이고 판정이 resume/next 인데 정당한 사유가 없을 때**뿐:
#   답 대기 질문(질문 장부) · 판정 stop(실패 장부) · 사용자의 멈춤 지시(입력 장부 마지막 문장).
# [중요] 사유 문장은 사실만 적는다 — 훅 경로 글의 명령형은 주입으로 거부된다(CLAUDE.md). 무엇을 할지는 스킬이 말한다.
STOP_WORDS = ("멈춰", "멈추", "멈춤", "중단", "그만", "스톱", "stop", "보류", "마무리", "인수인계", "끝내", "기다려",
              "잠깐", "나중에")
MAX_BLOCKS = 3                                        # 같은 세션 연속 차단 상한 — 넘으면 통과시키고 기록한다


def stop_check(root, *, active_issue, verdict: dict | None, session: str = "") -> dict:
    """`{"block": bool, "reason": str, ...}`. 판정을 못 하면 막지 않는다(fail-open)."""
    if not active_issue:
        return {"block": False, "reason": "활성 일감 없음"}
    n = int(active_issue)
    v = (verdict or {}).get("verdict", "")
    tasks = (verdict or {}).get("tasks") or []
    if v not in ("resume", "next"):
        return {"block": False, "reason": f"#{n} 판정 {v or '모름'}"}
    with _locked(root):
        data = _load(root)
        last = data["prompts"][-1] if data["prompts"] else None
        waiting = [q for q in data["questions"] if q["issue_id"] == n and q["status"] == "open"
                   and (last is None or last["at"] < q["at"])]
        if waiting:
            return {"block": False, "reason": f"#{n} 답 대기 질문 {waiting[-1]['stage']}"}
        if last and any(w in last["text"].casefold() for w in STOP_WORDS):
            return {"block": False, "reason": f"#{n} 사용자 멈춤 지시"}
        blocks = data.setdefault("stop_blocks", {})
        key = str(session or "-")[:80]
        count = int(blocks.get(key, 0)) + 1
        if count > MAX_BLOCKS:
            blocks[key] = 0
            _save(root, data)
            return {"block": False, "reason": f"#{n} 연속 차단 상한 {MAX_BLOCKS} — 통과(기록됨)", "overflow": True}
        blocks[key] = count
        _save(root, data)
    reason = (f"[AX 멈춤 판정] #{n} 일감 잠금 활성 · plan_start 판정 {v} · 대상 태스크 {', '.join(tasks) or '-'} · "
              f"답 대기 질문 없음 · 실패 장부 stop 아님 · 사용자 멈춤 지시 없음 ({count}/{MAX_BLOCKS})")
    return {"block": True, "reason": reason, "issue_id": n, "verdict": v, "tasks": tasks}


def reset_stop_blocks(root, session: str = "") -> None:
    """사용자 입력이 들어오면 그 세션의 연속 차단 수를 0 으로."""
    with _locked(root):
        data = _load(root)
        blocks = data.setdefault("stop_blocks", {})
        if blocks.pop(str(session or "-")[:80], None) is not None:
            _save(root, data)
