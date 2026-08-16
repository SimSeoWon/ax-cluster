"""소 1.3.3 재합성 — 도메인 MD 파싱 · 조각화 · 응답 파서 (LLM 0 로 검증한다).

[중요] **LLM 을 부르지 않는다.** 여기서 지키는 것은 모델의 품질이 아니라 **그 주변의 계약**이다:
스키마가 달라도 안 비는가 · 조각이 클래스를 잃지 않는가 · 파서가 도메인 밖을 막는가.

각 파일 독립 실행 규약을 따른다 — `python3 master/test_ontology_synth.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology import domain_md, parse            # noqa: E402
from master.ontology.contexts import ClassContext, DomainContexts   # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── 도메인 MD 파싱 ──────────────────────────────────────────────
# [중요] 실물 스키마가 두 가지다 (settled-decisions: 자동승급 출신 6 / ontology-register 1).

_REGISTER_SCHEMA = """---
tags: [a, b]
status: active
related_classes:
  - UFoo: Source/X/Foo.h
  - UBar: Source/X/Bar.h
---

## 시스템 개요

개요 본문.

## 핵심 책임

- 책임 하나
- 책임 둘

## 도메인 경계

**포함**:
- 안쪽 것

**제외**:
- 바깥 것

## 핵심 invariants

- 항상 참인 것

## 협력 도메인

- 다른도메인

## 사용자 의도 메모

메모 본문.
"""

_PROMOTED_SCHEMA = """---
tags: [c]
status: active
related_classes:
  - UBaz: Source/Y/Baz.h
---

## 시스템 개요

짧은 개요.

## 핵심 구현 패턴

패턴 서술이 여기 길게 들어간다.

## 확장 포인트

확장 서술.
"""


def test_domain_md() -> None:
    a = domain_md.parse_text(_REGISTER_SCHEMA, domain="A")
    check("register 스키마: 책임", a.responsibilities == ["책임 하나", "책임 둘"], str(a.responsibilities))
    check("register 스키마: 경계", (a.boundary_in, a.boundary_out) == (["안쪽 것"], ["바깥 것"]))
    check("register 스키마: invariants", a.invariants == ["항상 참인 것"])
    check("register 스키마: 협력", a.collaborators == ["다른도메인"])
    check("register 스키마: 결손 없음", a.missing == [], str(a.missing))
    check("related_classes 는 단일키 dict 리스트를 읽는다",
          a.related_classes == {"UFoo": "Source/X/Foo.h", "UBar": "Source/X/Bar.h"},
          str(a.related_classes))
    check("active 판정", a.active)
    check("tags", a.tags == ["a", "b"], str(a.tags))

    b = domain_md.parse_text(_PROMOTED_SCHEMA, domain="B")
    # [중요] 이 테스트가 이 모듈의 존재 이유다 — 원본 파서라면 여기서 전부 빈다.
    check("승급 스키마: 개요만으로 죽지 않는다", b.summary.strip() == "짧은 개요.")
    check("승급 스키마: 핵심 구현 패턴을 살린다", "패턴 서술" in b.patterns, b.patterns[:40])
    check("승급 스키마: 확장 포인트를 살린다", "확장 서술" in b.extension_points)
    check("[중요] 승급 스키마에서도 서술이 비지 않는다",
          len(b.summary_text) > len(b.summary), f"{len(b.summary_text)} vs {len(b.summary)}")
    check("[중요] 없는 정규 섹션을 결손으로 보고한다",
          set(b.missing) == {"responsibilities", "boundary", "invariants",
                             "collaborators", "intent_notes"}, str(b.missing))

    c = domain_md.parse_text("본문만 있고 frontmatter 가 없다", domain="C")
    check("frontmatter 없어도 죽지 않는다", c.frontmatter == {} and not c.active)

    d = domain_md.parse_text(_PROMOTED_SCHEMA.replace("## 확장 포인트", "## 듣도보도 못한 절"),
                             domain="D")
    check("[중요] 모르는 섹션을 버리지 않는다", "듣도보도 못한 절" in d.extra, str(list(d.extra)))


# ── 조각 고지 ───────────────────────────────────────────────────

def test_chunk_note() -> None:
    c = DomainContexts(domain="D", members_total=20,
                       items=[ClassContext(name="UA"), ClassContext(name="UB")])
    check("한 조각이면 고지 없음", c.note == "")
    c.part = (2, 5)
    check("[중요] 조각이면 '일부다' 를 프롬프트에 적는다",
          "5조각 중 2번째" in c.note and "추측하지 말 것" in c.note, c.note)
    c.truncated = ["UC", "UD"]
    check("예산 제외도 함께 고지", "UC" in c.note and "UD" in c.note)
    check("summary 에 조각 번호", "[2/5]" in c.summary, c.summary)


# ── actions 응답 파서 ───────────────────────────────────────────

def _actions_payload(**over) -> str:
    import json
    item = {"name": "DoThing", "kind": "Action", "description": "설명",
            "implementation": {"primary": "UA::Run", "related": ["UB::Help"]},
            "flow": [{"step": 1, "actor": "UA", "operation": "실행"}],
            "objects_affected": ["UA", "UB"],
            "evidence": "A.cpp:10", "confidence": 0.9}
    item.update(over)
    return json.dumps({"actions": [item]}, ensure_ascii=False)


def test_actions_parse() -> None:
    allowed = {"UA", "UB"}
    p = parse.actions(_actions_payload(), allowed=allowed)
    check("정상 항목 통과", len(p.items) == 1, p.summary)
    check("layer 는 아직 안 붙는다(합성기가 붙인다)", "layer" not in p.items[0])

    p = parse.actions(_actions_payload(evidence=""), allowed=allowed)
    check("[중요] 근거 없으면 버린다", not p.items and p.dropped.get("근거 없음") == 1, p.summary)

    p = parse.actions(_actions_payload(confidence=0.3), allowed=allowed)
    check("신뢰도 미달 버림", not p.items and p.dropped.get("신뢰도 미달") == 1)

    p = parse.actions(_actions_payload(implementation={"primary": "UOutside::Run"}),
                      allowed=allowed)
    check("[중요] 도메인 밖 구현이면 액션째 버린다",
          not p.items and p.dropped.get("구현이 도메인 밖이거나 없음") == 1, p.summary)

    p = parse.actions(_actions_payload(
        flow=[{"step": 1, "actor": "UOutside", "operation": "x"},
              {"step": 2, "actor": "UA", "operation": "y"}]), allowed=allowed)
    check("[중요] 도메인 밖 actor 는 단계만 버린다",
          len(p.items) == 1 and len(p.items[0]["flow"]) == 1, str(p.items))

    p = parse.actions(_actions_payload(objects_affected=["UA", "UOutside"]), allowed=allowed)
    check("objects_affected 도 도메인 안으로 거른다",
          p.items[0]["objects_affected"] == ["UA"], str(p.items[0].get("objects_affected")))

    p = parse.actions(_actions_payload(implementation={"primary": "UA::Run",
                                                       "related": ["UOut::X", "UB::Y"]}),
                      allowed=allowed)
    check("related 도 거른다", p.items[0]["implementation"]["related"] == ["UB::Y"])

    p = parse.actions(_actions_payload(kind="Nonsense"), allowed=allowed)
    check("kind 는 폴백한다(항목을 죽이지 않는다)", p.items[0]["kind"] == "Action")

    p = parse.actions("여기 있습니다:\n```json\n" + _actions_payload() + "\n```\n끝.",
                      allowed=allowed)
    check("[중요] 펜스·군말이 붙어도 JSON 을 건진다", len(p.items) == 1, p.summary)

    for bad, why in (("", "빈 응답"), ("설명만 하고 끝", "JSON 없음"),
                     ("{망가진 json", "파싱 실패"), ('{"other": []}', "키 없음")):
        try:
            parse.actions(bad, allowed=allowed)
            check(f"[중요] {why} 은 예외여야 한다", False, bad[:20])
        except parse.ResponseError:
            check(f"{why} → ResponseError", True)


# ── invariants 응답 파서 ────────────────────────────────────────

def _inv_payload(**over) -> str:
    import json
    item = {"name": "Rule", "text": "항상 참", "evidence": "A.h:5",
            "source_signal": "algorithm", "confidence": 0.8}
    item.update(over)
    return json.dumps({"invariants": [item]}, ensure_ascii=False)


def test_invariants_parse() -> None:
    p = parse.invariants(_inv_payload())
    check("정상 invariant 통과", len(p.items) == 1, p.summary)

    p = parse.invariants(_inv_payload(source_signal="made-up"))
    check("[중요] 신호 종류가 6종 밖이면 버린다",
          not p.items and p.dropped.get("신호 종류 불명") == 1, p.summary)

    p = parse.invariants(_inv_payload(evidence=""))
    check("근거 없으면 버린다", not p.items)

    a = parse.invariants(_inv_payload(name="")).items[0]["name"]
    b = parse.invariants(_inv_payload(name="")).items[0]["name"]
    check("[중요] 이름 없으면 결정적 해시명 (같은 입력 → 같은 파일명)", a == b and a.startswith("Invariant_"), a)

    c = parse.invariants(_inv_payload(name="", text="다른 내용")).items[0]["name"]
    check("내용이 다르면 다른 이름", c != a)


# ── 병합 ────────────────────────────────────────────────────────

def test_merge() -> None:
    from master.ontology.synth import merge_items
    items, coll = merge_items([[{"name": "A", "confidence": 0.6}],
                               [{"name": "A", "confidence": 0.9}, {"name": "B"}]])
    by = {i["name"]: i for i in items}
    check("조각 간 같은 이름은 하나로", len(items) == 2, str(items))
    check("[중요] 신뢰도 높은 쪽을 남긴다", by["A"]["confidence"] == 0.9, str(by["A"]))
    check("충돌을 센다", coll == 1, str(coll))
    items, coll = merge_items([[{"name": ""}, {"name": "A"}]])
    check("이름 없는 항목은 안 남는다", len(items) == 1 and coll == 0)


def main() -> int:
    for fn in (test_domain_md, test_chunk_note, test_actions_parse,
               test_invariants_parse, test_merge):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_ontology_synth: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
