"""재합성 프롬프트 — actions(L2) · invariants(L3) 추출 (소 1.3.3 의 LLM 부분).

원본: `watcher/ontology_actions._PROMPT_HEADER` · `build_action_prompt` /
`watcher/ontology_invariants` 의 프롬프트.

## [중요] 두 번 부른다 — 합치지 않는다

actions 와 invariants 를 한 번에 뽑으면 프리필을 절반으로 줄일 수 있다. **안 한다.**
두 프롬프트는 금지 규칙이 서로 다르고(actions 는 통신 인프라 금지, invariants 는 신호
6종 한정), 우리의 실측된 실패 모드가 **문장력이 아니라 지시 준수**이기 때문이다
(리포트 10 §9.2 — 14b 가 frontmatter 닫는 줄을 빼먹었다). 규칙을 섞으면 그 축이 나빠진다.
원본도 같은 이유로 모듈을 갈라 뒀다.

## [중요] 프롬프트 문구를 안전장치로 믿지 않는다

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


def commercial(body: str) -> str:
    """상용 에이전트에만 추가하는 파일 열람 범위. 로컬 프롬프트는 그대로 둔다."""
    return ("[상용 CLI 작업 범위]\n"
            "제공된 도메인 자료와 소스 발췌를 우선 사용한다. 추가 확인은 현재 작업 디렉터리의 "
            "해당 도메인에 직접 관련된 소스 파일 열람으로 한정한다. "
            "테스트 실행, 빌드, 저장소 전체 탐색, 파일 변경을 하지 않는다. "
            "주어진 근거가 부족하면 추측하지 말고 해당 항목을 생략한다.\n\n" + body)

# ── 규칙 블록 — 공통 몸통 + 언어 블록 (`#850`) ─────────────────────────────────
#
# [중요] **unreal(또는 kind 미기재) 프로젝트의 C++ 조각은 종전 문자열과 바이트 단위로 같다**
#    (`test_ontology_python.py` 가 고정본과 대조한다). 언어 블록은 조각 멤버의 **파일 확장자**가
#    고르고(`contexts.lang_of`), UE 전용 규칙을 실을지는 **프로젝트 kind** 만 정한다.
#    혼합 조각(C++ + Python)이면 해당 블록을 모두 싣는다.
# [주의] invariant 신호 6종의 **이름은 그대로**다 — `parse.VALID_SIGNALS` 가 그 이름으로 거른다.
#    언어 블록은 이름마다 그 언어의 대응물만 정의한다.

_INTRO_UE = "당신은 Unreal Engine 5 프로젝트의 "
_INTRO = "당신은 소프트웨어 프로젝트의 "

_A_COMMON_HEAD = """**도메인 내부 액션**을 종합 기술 문서로 추출한다.

액션은 함수 1:1 매핑이 **아니다** — 의미 단위다.
누가(trigger) → 누구에게(actor) → 무엇을(operation) → 어떤 순서로(flow) 작동하는지 쓴다.
같은 함수가 여러 액션의 구현일 수 있고, 같은 액션이 진입점을 여럿 가질 수 있다.

OAF 분류:
  - Action   : 같은 도메인 오브젝트의 **상태를 바꾸는** 트랜잭션
  - Function : 순수 계산 (상태 변경 없음, 입력 → 출력)

== 추출 대상 — 반드시 같은 도메인 안에서만 ==
  [완료] 아래 「대상 클래스」 목록 안의 클래스끼리의 호출·상태 변경
  [완료] 같은 도메인 멤버 변수 변경
"""

_A_EVENTS = {
    "ue": """  [완료] 이벤트 **발행** → `triggers_events` (3패턴 모두):
     (1) `OnXxx.Broadcast(...)` / `ExecuteIfBound(...)` 같은 표준 델리게이트
     (2) 자체 디스패처 — `FGlobalEventSystem::ExecuteEvent<IEventXxx>(...)` 등
     (3) 람다 콜백 등록 트리거 — `Service->Bind([this](){...})` 의 **호출자 쪽**
  [완료] 이벤트 **구독** → `subscribed_to` (3패턴 모두):
     (1) `AddDynamic` / `AddUObject` / `BindUObject` / `AddLambda` / `AddRaw`
     (2) 인터페이스 상속 — `class UWidget : public IEventXxx` + 메서드 override
     (3) 람다 핸들러 — 람다 본문이 사실상 핸들러
""",
    "cpp": """  [완료] 이벤트 **발행** → `triggers_events`:
     (1) 콜백 호출 — 보관한 `std::function` / 함수 포인터 호출, 리스너 목록 순회 통지
     (2) 자체 디스패처·시그널 — `emit` / `notify` / `dispatch` 류 호출
  [완료] 이벤트 **구독** → `subscribed_to`:
     (1) 핸들러 등록 — `connect` / `subscribe` / `addListener` 류 호출, 람다 핸들러
     (2) 인터페이스 상속 — 리스너 인터페이스 상속 + 메서드 override
""",
    "python": """  [완료] 이벤트 **발행** → `triggers_events`:
     (1) 콜백 호출 — 등록된 콜백·훅 목록을 순회해 부르는 것, 주입받은 callable 호출
     (2) 자체 디스패처·시그널 — `emit` / `notify` / `dispatch` / `send` 류 메서드
  [완료] 이벤트 **구독** → `subscribed_to`:
     (1) 핸들러 등록 — `subscribe` / `connect` / `add_listener` 류 호출, 데코레이터 등록
     (2) 상속 — 핸들러 기반 클래스 상속 + 메서드 override
""",
}

_A_FORBID_HEAD = """
== 절대 추출 금지 ==
"""

_A_COMM = {
    "ue": """  [실패] 통신 인프라 — 형태 불문: FSocket / FHttpModule / IOnlineSubsystem / Connect / Send /
     Receive / Packet / WebSocket / TCP / UDP / IPC / RPC 매크로(Server_*/Client_*/Multicast_*)
     / 외부 REST SDK. 통신은 별도 도메인의 책임이다
""",
    "cpp": """  [실패] 통신 인프라 — 형태 불문: 소켓 / HTTP 클라이언트 / Connect / Send / Receive / Packet /
     WebSocket / TCP / UDP / IPC / RPC 스텁 / 외부 REST SDK. 통신은 별도 도메인의 책임이다
""",
    "python": """  [실패] 통신 인프라 — 형태 불문: socket / urllib / requests / httpx / aiohttp / websocket /
     IPC / RPC 클라이언트 / 외부 REST SDK. 통신은 별도 도메인의 책임이다
""",
}

_A_FORBID_TAIL = """  [실패] 도메인 밖 클래스 호출 — 「대상 클래스」에 없는 이름은 flow·objects_affected 에 쓰지 말 것
  [실패] 자명한 getter/setter 한 줄 함수, 컴파일러가 검증하는 시그니처 정합성
  [실패] 별도 events 항목 — 이벤트는 위 두 채널에 흡수한다

== 출력 정신 ==
  - 의미 있는 것만 5~15건. 억지로 채우지 말 것
  - `name` 은 **의미 단위 PascalCase** (예: AddTaskItem) — 함수명 그대로 쓰지 말 것
  - `description` 은 **한국어**. 의미와 맥락을 쓴다
"""

_A_PRIMARY = {
    "cpp": """  - `implementation.primary` 는 `"클래스명::메서드명"` 형식. **발췌에서 실제로 본 것만**
""",
    "python": """  - `implementation.primary` 는 `"클래스명.메서드명"` 형식. **발췌에서 실제로 본 것만**
  - 「대상 클래스」 이름에 모듈 경로가 붙어 있으면(`pkg.mod.Class`) 그 이름 그대로 쓴다
""",
    "mixed": """  - `implementation.primary` 는 C++ 클래스면 `"클래스명::메서드명"`, Python 클래스면
    `"클래스명.메서드명"` 형식. **발췌에서 실제로 본 것만**
  - 「대상 클래스」 이름에 모듈 경로가 붙어 있으면(`pkg.mod.Class`) 그 이름 그대로 쓴다
""",
}

_A_TAIL_HEAD = """  - `evidence` 는 `"<파일>:<줄 또는 메서드>"`. 못 대면 그 항목을 내지 말 것
  - confidence 0.5 미만이면 출력하지 말 것

[중요] **발췌에 없는 것은 지어내지 말 것.** 없는 호출을 쓰면 결정적 게이트가 그 항목을 버린다.

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
"""

_A_IMPL = {
    "cpp": "클래스::메서드",
    "python": "클래스.메서드",
    "mixed": "클래스::메서드 또는 클래스.메서드",
}

_A_TAIL = """      "evidence": "<파일:줄>",
      "confidence": 0.0
    }
  ]
}"""

_I_HEAD = """**도메인 invariant** 를 추출한다.

invariant 는 "이 도메인에서 항상 참이어야 하는 규칙" 이다. """

_I_SURFACE = {
    "ue": "매크로 표면이 아니라",
    "other": "선언 표면이 아니라",
}

_I_HEAD2 = """
**코드 본문**에서 온다. 아래 6가지 신호만 근거로 쓴다:

"""

_I_SIGNALS = {
    "ue": """  function-signature : const/virtual/override, 반환 타입이 강제하는 계약
  lifetime-pattern   : TSharedPtr/TWeakPtr/TUniquePtr, 소유권·GC 독립성
  algorithm          : 초기화 순서, 상태 머신 전이, early-return 권한 검사
  check-statement    : check() / ensure() / verify() 가 못박은 전제
  comment            : @invariant / @precondition 또는 한국어 설명 주석
  lock-pattern       : FScopeLock / CriticalSection / RAII 로 지켜지는 것
""",
    "cpp": """  function-signature : const/virtual/override/noexcept, 반환 타입이 강제하는 계약
  lifetime-pattern   : std::unique_ptr/std::shared_ptr/std::weak_ptr, RAII 소유권
  algorithm          : 초기화 순서, 상태 머신 전이, early-return 권한 검사
  check-statement    : assert() / static_assert / 조건 위반 시 throw 가 못박은 전제
  comment            : @invariant / @precondition 또는 한국어 설명 주석
  lock-pattern       : std::mutex + lock_guard/unique_lock/scoped_lock 으로 지켜지는 것
""",
    "python": """  function-signature : 타입 힌트·반환 타입, @abstractmethod / Protocol / @property 가 강제하는 계약
  lifetime-pattern   : with 컨텍스트 매니저(__enter__/__exit__) · try/finally 가 지키는 자원 소유·해제
  algorithm          : 초기화 순서, 상태 머신 전이, early-return 권한 검사
  check-statement    : assert / 조건 위반 시 raise 가 못박은 전제
  comment            : docstring 의 계약 서술 · @invariant / [중요] 류 표식 또는 한국어 설명 주석
  lock-pattern       : threading.Lock/RLock 의 `with lock:` · 파일 잠금(fcntl) 으로 지켜지는 것
""",
}

_I_TAIL = """
== 절대 추출 금지 ==
  [실패] 컴파일러가 이미 강제하는 것 (타입 일치, 시그니처 정합성) — 가치 없다
  [실패] 도메인 밖 클래스에 대한 규칙
  [실패] 발췌에 근거가 없는 일반론 ("메모리 누수를 피해야 한다" 류)

== 출력 정신 ==
  - 의미 있는 것만 5~12건
  - `name` 은 **의미 단위 PascalCase** (예: ServerOnlyExecutorRegistration)
  - `text` 는 **한국어 한두 문장.** 무엇이 항상 참인지 단정형으로
  - `evidence` 는 `"<파일>:<줄 또는 메서드>"`. 못 대면 그 항목을 내지 말 것
  - `source_signal` 은 위 6가지 중 하나를 그대로
  - confidence 0.5 미만이면 출력하지 말 것

[중요] **발췌에 없는 것은 지어내지 말 것.**

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

_LABEL = {"cpp": "C++", "python": "Python"}


def is_ue(kind: str) -> bool:
    """UE 전용 규칙을 싣나. [중요] **kind 가 비었거나 모르는 값이면 싣는다** — 종전 동작이다."""
    from ..projects.profile import NON_UNREAL_KINDS          # noqa: PLC0415
    return (kind or "") not in NON_UNREAL_KINDS


def langs_of(ctx: DomainContexts) -> tuple:
    """조각 멤버의 언어 — **파일 확장자로만.** 아무 것도 모르면 `("cpp",)`(종전 동작)."""
    from .contexts import lang_of                            # noqa: PLC0415
    got = {lang_of(getattr(c, "file", "")) for c in ctx.items} - {""}
    return tuple(x for x in ("cpp", "python") if x in got) or ("cpp",)


def _pick(table: dict, langs: tuple, ue: bool) -> str:
    """언어 블록을 고른다. 하나면 그대로, 여럿이면 언어 이름표를 붙여 차례로 싣는다."""
    keys = [("ue" if (lang == "cpp" and ue and "ue" in table) else lang) for lang in langs]
    if len(keys) == 1:
        return table[keys[0]]
    return "".join(f"  ({_LABEL[lang]} 소스)\n" + table[k] for lang, k in zip(langs, keys))


def actions_rules(langs: tuple = ("cpp",), ue: bool = True) -> str:
    """actions 규칙 블록. `actions_rules(("cpp",), True)` 는 종전 문자열과 같다."""
    form = langs[0] if len(langs) == 1 else "mixed"
    intro = _INTRO_UE if (ue and "cpp" in langs) else _INTRO
    return (intro + _A_COMMON_HEAD + _pick(_A_EVENTS, langs, ue) + _A_FORBID_HEAD
            + _pick(_A_COMM, langs, ue) + _A_FORBID_TAIL + _A_PRIMARY[form] + _A_TAIL_HEAD
            + f'      "implementation": {{"primary": "<{_A_IMPL[form]}>", '
              f'"related": ["<{_A_IMPL[form]}>"]}},\n'
            + _A_TAIL)


def invariants_rules(langs: tuple = ("cpp",), ue: bool = True) -> str:
    """invariants 규칙 블록. `invariants_rules(("cpp",), True)` 는 종전 문자열과 같다."""
    ue_cpp = ue and "cpp" in langs
    intro = _INTRO_UE if ue_cpp else _INTRO
    surface = _I_SURFACE["ue" if ue_cpp else "other"]
    return (intro + _I_HEAD + surface + _I_HEAD2 + _pick(_I_SIGNALS, langs, ue) + _I_TAIL)


# 종전 이름 — unreal 의 C++ 조각에 실리는 것이 이것이다.
_ACTIONS_RULES = actions_rules()
_INVARIANTS_RULES = invariants_rules()


def _body(doc: DomainDoc | None, ctx: DomainContexts, rules: str, tail: str) -> str:
    parts: list = [rules, "", f"== 도메인: {ctx.domain} =="]

    if doc is not None:
        text = doc.summary_text[:DOMAIN_TEXT_CHARS]
        if text:
            parts += ["", "[도메인 서술 — 사람이 쓴 의도]", text]
        # [중요] 경계가 없으면 없다고 말한다. "경계를 지켜라" 만 쓰고 경계를 안 주면
        #    모델은 자기가 상상한 경계를 지킨다.
        if not (doc.boundary_in or doc.boundary_out):
            parts.append("(이 도메인 문서에는 명시된 경계 절이 없다 — "
                         "아래 「대상 클래스」 목록이 유일한 경계다.)")

    names = sorted(ctx.names)
    parts += ["", f"[대상 클래스 {len(names)}개 — [중요] 이 목록 밖의 이름을 쓰지 말 것]",
              ", ".join(names)]
    if ctx.note:
        parts += ["", ctx.note]

    parts += ["", "[소스 발췌]"]
    for item in ctx.items:
        parts += ["---", item.block()]

    parts += ["", tail]
    return "\n".join(parts)


def actions(doc: DomainDoc | None, ctx: DomainContexts) -> str:
    """actions 추출 프롬프트. 규칙 블록은 조각 멤버의 언어와 프로젝트 kind 가 고른다."""
    rules = actions_rules(langs_of(ctx), is_ue(getattr(ctx, "kind", "")))
    return _body(doc, ctx, rules, "== JSON 응답 ==")


def invariants(doc: DomainDoc | None, ctx: DomainContexts) -> str:
    """invariants 추출 프롬프트. 규칙 블록은 조각 멤버의 언어와 프로젝트 kind 가 고른다."""
    rules = invariants_rules(langs_of(ctx), is_ue(getattr(ctx, "kind", "")))
    return _body(doc, ctx, rules, "== JSON 응답 ==")
