"""LLM 응답 파서 — actions · invariants (소 1.3.3 의 LLM 부분).

원본: `watcher/ontology_actions.parse_action_response` ·
`watcher/ontology_invariants` 의 응답 파서.

## 🔴 여기가 진짜 방어선이다

프롬프트의 "cross-domain 을 쓰지 말 것" 은 부탁이다. **실제 차단은 여기서 한다** —
`allowed` 밖의 이름은 버리고, 근거(`evidence`) 없는 항목은 버리고, 신뢰도 미달은 버린다.
그 다음 `verify_facts` 가 호출 관계를 `methods` 실측과 대조한다. 두 단계 다 결정적이다.

## 관대하게 읽고 엄하게 거른다

응답에서 **JSON 블록만 뽑아 쓴다** — 로컬 모델은 앞뒤에 말을 붙이거나 코드펜스를 두른다
(실측: 14b 가 frontmatter 닫는 줄을 빼먹는 것과 같은 계열의 형식 실패). 형식 관용은
**읽는 단계**에만 적용하고, 내용 판정은 봐주지 않는다.

🔴 **버린 것을 센다.** `Parsed.dropped` 가 이유별 집계다. 조용히 버리면 "모델이 5건만
냈다" 와 "20건 냈는데 15건이 걸렸다" 를 구분할 수 없고, 그러면 프롬프트를 고칠 근거가 없다.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

MIN_CONFIDENCE = 0.5
VALID_KINDS = {"Action", "Function"}
VALID_SIGNALS = {
    "function-signature", "lifetime-pattern", "algorithm",
    "check-statement", "comment", "lock-pattern",
}
TRIGGER_TYPES = {"user_input", "event", "external_call"}

# 첫 `{` 부터 마지막 `}` 까지. 모델이 앞뒤에 말을 붙여도 본문을 건진다.
_JSON = re.compile(r"\{.*\}", re.S)
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


class ResponseError(ValueError):
    """응답을 읽을 수 없다. 🔴 빈 결과로 위장하지 않는다 — 호출자가 유실로 센다."""


@dataclass
class Parsed:
    items: list = field(default_factory=list)
    dropped: dict = field(default_factory=dict)      # 사유 → 건수
    raw_count: int = 0

    def drop(self, why: str) -> None:
        self.dropped[why] = self.dropped.get(why, 0) + 1

    @property
    def summary(self) -> str:
        s = f"{len(self.items)}/{self.raw_count}건"
        if self.dropped:
            s += " · 버림 " + ", ".join(f"{k} {v}" for k, v in sorted(self.dropped.items()))
        return s


def _json_block(text: str) -> dict:
    if not (text or "").strip():
        raise ResponseError("응답이 비었다")
    s = _FENCE.sub("", text.strip())
    m = _JSON.search(s)
    if not m:
        raise ResponseError(f"JSON 블록이 없다 (앞 120자: {s[:120]!r})")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ResponseError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(data, dict):
        raise ResponseError("최상위가 객체가 아니다")
    return data


def _strs(v, allowed: set | None = None) -> list:
    if not isinstance(v, list):
        return []
    out = [str(x).strip() for x in v if x and str(x).strip()]
    return [x for x in out if x in allowed] if allowed is not None else out


def _conf(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _class_of(qualified: str) -> str:
    return qualified.split("::", 1)[0] if "::" in qualified else qualified


def actions(text: str, *, allowed: set, min_confidence: float = MIN_CONFIDENCE) -> Parsed:
    """actions 응답 → `package.write(actions=…)` 에 그대로 넣을 dict 리스트.

    `allowed` 는 프롬프트에 실린 클래스 집합이다. 🔴 **`implementation.primary` 의 클래스가
    그 안에 없으면 액션 자체를 버린다** — 원본과 같은 강한 필터다. 도메인 밖 구현을 가리키는
    액션은 이 도메인의 액션이 아니다.
    """
    data = _json_block(text)
    raw = data.get("actions")
    if not isinstance(raw, list):
        raise ResponseError("`actions` 배열이 없다")
    out = Parsed(raw_count=len(raw))

    for item in raw:
        if not isinstance(item, dict):
            out.drop("항목이 객체가 아님")
            continue
        name = str(item.get("name") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not name:
            out.drop("이름 없음")
            continue
        if not evidence:
            out.drop("근거 없음")
            continue
        conf = _conf(item.get("confidence"))
        if conf < min_confidence:
            out.drop("신뢰도 미달")
            continue

        kind = str(item.get("kind") or "").strip()
        if kind not in VALID_KINDS:
            kind = "Action"          # 원본과 같은 폴백 — 분류 실패가 항목을 죽이지는 않는다

        impl_raw = item.get("implementation")
        impl: dict = {}
        if isinstance(impl_raw, dict):
            primary = str(impl_raw.get("primary") or "").strip()
            if primary and _class_of(primary) in allowed:
                impl["primary"] = primary
            related = [r for r in _strs(impl_raw.get("related"))
                       if _class_of(r) in allowed]
            if related:
                impl["related"] = related
        if not impl.get("primary"):
            out.drop("구현이 도메인 밖이거나 없음")
            continue

        entry: dict = {"name": name, "kind": kind, "implementation": impl,
                       "evidence": evidence, "confidence": round(conf, 3)}

        desc = str(item.get("description") or "").strip()
        if desc:
            entry["description"] = desc

        trig = item.get("trigger")
        if isinstance(trig, dict):
            t = str(trig.get("type") or "").strip().lower()
            norm: dict = {"type": t if t in TRIGGER_TYPES else "event"}
            for k in ("source", "description"):
                v = str(trig.get(k) or "").strip()
                if v:
                    norm[k] = v
            entry["trigger"] = norm

        flow: list = []
        for i, step in enumerate(item.get("flow") or []):
            if not isinstance(step, dict):
                continue
            actor = str(step.get("actor") or "").strip()
            op = str(step.get("operation") or "").strip()
            if not actor or not op or actor not in allowed:
                continue          # 🔴 도메인 밖 actor 는 단계째 버린다
            s: dict = {"step": step.get("step") or (i + 1), "actor": actor, "operation": op}
            for k in ("target", "note"):
                v = str(step.get(k) or "").strip()
                if v:
                    s[k] = v
            flow.append(s)
        if flow:
            entry["flow"] = flow

        affected = _strs(item.get("objects_affected"), allowed)
        if affected:
            entry["objects_affected"] = affected
        for key in ("triggers_events", "subscribed_to"):
            ev = _strs(item.get(key))
            if ev:
                entry[key] = ev

        out.items.append(entry)
    return out


def invariants(text: str, *, min_confidence: float = MIN_CONFIDENCE) -> Parsed:
    """invariants 응답 → dict 리스트.

    invariant 는 클래스 이름을 직접 주장하지 않는 경우가 많아 `allowed` 필터를 걸지 않는다.
    대신 **근거(`evidence`) 없는 항목을 버린다** — 근거 없는 invariant 는 검증할 수 없고,
    검증할 수 없는 규칙은 지도에 그릴 수 없다.
    """
    data = _json_block(text)
    raw = data.get("invariants")
    if not isinstance(raw, list):
        raise ResponseError("`invariants` 배열이 없다")
    out = Parsed(raw_count=len(raw))

    for item in raw:
        if not isinstance(item, dict):
            out.drop("항목이 객체가 아님")
            continue
        body = str(item.get("text") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not body:
            out.drop("본문 없음")
            continue
        if not evidence:
            out.drop("근거 없음")
            continue
        conf = _conf(item.get("confidence"))
        if conf < min_confidence:
            out.drop("신뢰도 미달")
            continue
        signal = str(item.get("source_signal") or "").strip()
        if signal not in VALID_SIGNALS:
            out.drop("신호 종류 불명")
            continue

        name = str(item.get("name") or "").strip() or _fallback_name(body, evidence)
        out.items.append({
            "name": name,
            "text": body,
            "evidence": evidence,
            "source_signal": signal,
            "confidence": round(conf, 3),
        })
    return out


def _fallback_name(text: str, evidence: str) -> str:
    """이름을 안 주면 **결정적** 해시명. 같은 invariant 는 항상 같은 파일명이 된다."""
    h = hashlib.sha1(f"{text}|{evidence}".encode("utf-8", "ignore")).hexdigest()[:8]
    return f"Invariant_{h}"
