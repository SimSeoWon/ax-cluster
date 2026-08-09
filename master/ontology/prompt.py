"""재합성 프롬프트 — actions(L2) · invariants(L3) 추출 (소 1.3.3 의 LLM 부분).

원본: `watcher/ontology_actions._PROMPT_HEADER` · `build_action_prompt` /
`watcher/ontology_invariants` 의 프롬프트.

## 🔴 두 번 부른다 — 합치지 않는다

actions 와 invariants 를 한 번에 뽑으면 프리필을 절반으로 줄일 수 있다. **안 한다.**
두 프롬프트는 금지 규칙이 서로 다르고(actions 는 통신 인프라 금지, invariants 는 신호
6종 한정), 우리의 실측된 실패 모드가 **문장력이 아니라 지시 준수**이기 때문이다
(리포트 10 §9.2 — 14b 가 frontmatter 닫는 줄을 빼먹었다). 규칙을 섞으면 그 축이 나빠진다.
원본도 같은 이유로 모듈을 갈라 뒀다.

## 🔴 프롬프트 문구를 안전장치로 믿지 않는다

"cross-domain 을 추출하지 말 것" 은 **부탁**이다. 실제 차단은 `parse.py` 의
`allowed_classes` 필터와 `verify_facts` 의 사실 게이트가 한다 — *결정적 게이트가 LLM
판단보다 우선*(`~/CLAUDE.md`). 문구는 좋은 응답을 **유도**할 뿐이다.

## 결손을 본문에 적는다

클래스가 예산에 안 들어가면 `DomainContexts.note` 가 그 사실을 프롬프트에 싣는다.
숨기면 모델은 **보이는 것이 전부**라고 가정하고, 없는 클래스를 지어내 빈칸을 채운다.
매니페스트 결손 명시와 같은 규칙이다.
"""
from __future__ import annotations

from .contexts import DomainContexts
from .domain_md import DomainDoc

# 도메인 서술 상한. 넘으면 자른다 — `contexts.TOTAL_CHARS` 와 합쳐 `num_ctx` 안에 든다.
DOMAIN_TEXT_CHARS = 1800

_ACTIONS_RULES = """당신은 Unreal Engine 5 프로젝트의 **도메인 내부 액션**을 종합 기술 문서로 추출한다.

액션은 함수 1:1 매핑이 **아니다** — 의미 단위다.
누가(trigger) → 누구에게(actor) → 무엇을(operation) → 어떤 순서로(flow) 작동하는지 쓴다.
같은 함수가 여러 액션의 구현일 수 있고, 같은 액션이 진입점을 여럿 가질 수 있다.

OAF 분류:
  - Action   : 같은 도메인 오브젝트의 **상태를 바꾸는** 트랜잭션
  - Function : 순수 계산 (상태 변경 없음, 입력 → 출력)

== 추출 대상 — 반드시 같은 도메인 안에서만 ==
  ✅ 아래 「대상 클래스」 목록 안의 클래스끼리의 호출·상태 변경
  ✅ 같은 도메인 멤버 변수 변경
  ✅ 이벤트 **발행** → `triggers_events` (3패턴 모두):
     (1) `OnXxx.Broadcast(...)` / `ExecuteIfBound(...)` 같은 표준 델리게이트
     (2) 자체 디스패처 — `FGlobalEventSystem::ExecuteEvent<IEventXxx>(...)` 등
     (3) 람다 콜백 등록 트리거 — `Service->Bind([this](){...})` 의 **호출자 쪽**
  ✅ 이벤트 **구독** → `subscribed_to` (3패턴 모두):
     (1) `AddDynamic` / `AddUObject` / `BindUObject` / `AddLambda` / `AddRaw`
     (2) 인터페이스 상속 — `class UWidget : public IEventXxx` + 메서드 override
     (3) 람다 핸들러 — 람다 본문이 사실상 핸들러

== 절대 추출 금지 ==
  ❌ 통신 인프라 — 형태 불문: FSocket / FHttpModule / IOnlineSubsystem / Connect / Send /
     Receive / Packet / WebSocket / TCP / UDP / IPC / RPC 매크로(Server_*/Client_*/Multicast_*)
     / 외부 REST SDK. 통신은 별도 도메인의 책임이다
  ❌ 도메인 밖 클래스 호출 — 「대상 클래스」에 없는 이름은 flow·objects_affected 에 쓰지 말 것
  ❌ 자명한 getter/setter 한 줄 함수, 컴파일러가 검증하는 시그니처 정합성
  ❌ 별도 events 항목 — 이벤트는 위 두 채널에 흡수한다

== 출력 정신 ==
  - 의미 있는 것만 5~15건. 억지로 채우지 말 것
  - `name` 은 **의미 단위 PascalCase** (예: AddTaskItem) — 함수명 그대로 쓰지 말 것
  - `description` 은 **한국어**. 의미와 맥락을 쓴다
  - `implementation.primary` 는 `"클래스명::메서드명"` 형식. **발췌에서 실제로 본 것만**
  - `evidence` 는 `"<파일>:<줄 또는 메서드>"`. 못 대면 그 항목을 내지 말 것
  - confidence 0.5 미만이면 출력하지 말 것

🔴 **발췌에 없는 것은 지어내지 말 것.** 없는 호출을 쓰면 결정적 게이트가 그 항목을 버린다.

== 응답 포맷 (JSON 만. 다른 텍스트·설명·코드펜스 금지) ==
{
  "actions": [
    {
      "name": "<의미 단위 PascalCase>",
      "kind": "Action" | "Function",
      "description": "<한국어>",
      "trigger": {"type": "user_input"|"event"|"external_call", "source": "<진입점>", "description": "<맥락>"},
      "flow": [{"step": 1, "actor": "<대상 클래스>", "operation": "<무엇을>", "target": "<무엇에>", "note": "<선택>"}],
      "objects_affected": ["<대상 클래스>"],
      "triggers_events": ["<이벤트명>"],
      "subscribed_to": ["<이벤트명>"],
      "implementation": {"primary": "<클래스::메서드>", "related": ["<클래스::메서드>"]},
      "evidence": "<파일:줄>",
      "confidence": 0.0
    }
  ]
}"""

_INVARIANTS_RULES = """당신은 Unreal Engine 5 프로젝트의 **도메인 invariant** 를 추출한다.

invariant 는 "이 도메인에서 항상 참이어야 하는 규칙" 이다. 매크로 표면이 아니라
**코드 본문**에서 온다. 아래 6가지 신호만 근거로 쓴다:

  function-signature : const/virtual/override, 반환 타입이 강제하는 계약
  lifetime-pattern   : TSharedPtr/TWeakPtr/TUniquePtr, 소유권·GC 독립성
  algorithm          : 초기화 순서, 상태 머신 전이, early-return 권한 검사
  check-statement    : check() / ensure() / verify() 가 못박은 전제
  comment            : @invariant / @precondition 또는 한국어 설명 주석
  lock-pattern       : FScopeLock / CriticalSection / RAII 로 지켜지는 것

== 절대 추출 금지 ==
  ❌ 컴파일러가 이미 강제하는 것 (타입 일치, 시그니처 정합성) — 가치 없다
  ❌ 도메인 밖 클래스에 대한 규칙
  ❌ 발췌에 근거가 없는 일반론 ("메모리 누수를 피해야 한다" 류)

== 출력 정신 ==
  - 의미 있는 것만 5~12건
  - `name` 은 **의미 단위 PascalCase** (예: ServerOnlyExecutorRegistration)
  - `text` 는 **한국어 한두 문장.** 무엇이 항상 참인지 단정형으로
  - `evidence` 는 `"<파일>:<줄 또는 메서드>"`. 못 대면 그 항목을 내지 말 것
  - `source_signal` 은 위 6가지 중 하나를 그대로
  - confidence 0.5 미만이면 출력하지 말 것

🔴 **발췌에 없는 것은 지어내지 말 것.**

== 응답 포맷 (JSON 만. 다른 텍스트·설명·코드펜스 금지) ==
{
  "invariants": [
    {
      "name": "<의미 단위 PascalCase>",
      "text": "<한국어 한두 문장>",
      "evidence": "<파일:줄>",
      "source_signal": "function-signature|lifetime-pattern|algorithm|check-statement|comment|lock-pattern",
      "confidence": 0.0
    }
  ]
}"""


def _body(doc: DomainDoc | None, ctx: DomainContexts, rules: str, tail: str) -> str:
    parts: list = [rules, "", f"== 도메인: {ctx.domain} =="]

    if doc is not None:
        text = doc.summary_text[:DOMAIN_TEXT_CHARS]
        if text:
            parts += ["", "[도메인 서술 — 사람이 쓴 의도]", text]
        # 🔴 경계가 없으면 없다고 말한다. "경계를 지켜라" 만 쓰고 경계를 안 주면
        #    모델은 자기가 상상한 경계를 지킨다.
        if not (doc.boundary_in or doc.boundary_out):
            parts.append("(이 도메인 문서에는 명시된 경계 절이 없다 — "
                         "아래 「대상 클래스」 목록이 유일한 경계다.)")

    names = sorted(ctx.names)
    parts += ["", f"[대상 클래스 {len(names)}개 — 🔴 이 목록 밖의 이름을 쓰지 말 것]",
              ", ".join(names)]
    if ctx.note:
        parts += ["", ctx.note]

    parts += ["", "[소스 발췌]"]
    for item in ctx.items:
        parts += ["---", item.block()]

    parts += ["", tail]
    return "\n".join(parts)


def actions(doc: DomainDoc | None, ctx: DomainContexts) -> str:
    """actions 추출 프롬프트."""
    return _body(doc, ctx, _ACTIONS_RULES, "== JSON 응답 ==")


def invariants(doc: DomainDoc | None, ctx: DomainContexts) -> str:
    """invariants 추출 프롬프트."""
    return _body(doc, ctx, _INVARIANTS_RULES, "== JSON 응답 ==")
