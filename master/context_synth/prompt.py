"""컨텍스트 MD 생성 프롬프트 조립 (소 1.2.1).

원본: `AgentTest/watcher/context.py` 의 `_SINGLE_FILE_ANALYSIS_PROMPT` + `_process_directory_group`
의 grounding 주입부.

[중요] **원본과 갈라지는 지점 셋.**

⑴ **코드 리뷰를 함께 만들지 않는다.** 원본은 한 번의 LLM 호출로 컨텍스트 MD *와* 코드 리뷰를
   생성하고 `=== CONTEXT_MD ===` / `=== CODE_REVIEW ===` 로 쪼갠다. 리뷰는 §5.2-D 판단 대상이라
   범위 밖이므로 **컨텍스트만 요구한다** — 요구하지 않는 섹션을 파싱하는 코드도 두지 않는다.
   부수 효과로 원본이 로컬 LLM 화이트리스트에서 `context_review` 를 뺀 이유(*"4B 모델이 통합
   프롬프트를 일관되게 처리할지 미검증"*)가 우리에겐 사라진다 — 한 가지만 시키기 때문이다.

⑵ **관계 그래프를 근거로 넣는다.** 원본은 `#include` dependents 만 주입했다. 우리는 중 1.1 에서
   **상속 그래프**까지 만들었으므로 부모·형제를 함께 준다 — `related_classes` 를 LLM 이 추측하는
   대신 **실측값으로 교정**할 수 있다.

⑶ **없는 근거를 없다고 적는다.** 도메인 규범(중 1.3)이 아직 없다. 빈 섹션을 감추면 다음 세션이
   "왜 도메인 맥락이 안 들어가지" 를 버그로 오해한다 — 매니페스트가 같은 규약을 쓴다.

프롬프트 본문(형식·작성 규칙)은 **원문 그대로** 옮겼다. 식별자 영어 유지·역할 한국어 혼합·
의역 반복 금지·`?` 경로 규약이 전부 회사 환경에서 조정된 값이라 손대지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 그룹당 본문 상한.
#
# [중요] **원본은 8,000자였다. 우리는 4,000이다** — 원본은 상용 API(Claude/agy)를 불렀지만 우리는
# 16GB UMA 보드의 35B IQ2_M 을 부른다. 실측 2026-08-08: 8,000자 본문(총 프롬프트 10.5KB)으로
# 8그룹 배치를 돌렸더니 **BC-250 이 먹통이 됐다** — ping 은 되는데 SSH banner exchange 가
# 끊기고 Ollama 가 무응답(메모리 압박 신호). 프롬프트가 길면 KV 캐시가 보드 한계를 넘는다.
# 상한은 CLI `--content-limit` 로 올릴 수 있지만, **올리기 전에 노드 여유를 확인할 것.**
#
# 🔴 [중요] **이 상한은 로컬 레인(브로커·Ollama)에만 건다** (`#782`, 사용자 결정 2026-10-10).
#    상용 CLI 레인(`agy`·`codex`)은 보드 KV 와 무관하므로 원본 본문을 **자르지 않고** 받는다
#    (`limit=None`). `--content-limit` 도 로컬 레인에만 적용된다 — 상용은 결정상 무제한이다.
#    [주의] 근거·관련 문서 상한(`GROUNDING_LIMIT`·`RELATED_*`)은 본문 상한이 아니라 그대로다.
CONTENT_LIMIT = 4000

# 근거 항목 상한. 원본이 dependents 를 10개로 끊었다 — 그 이상은 프롬프트를 밀어내고
# LLM 이 목록만 베끼게 된다.
GROUNDING_LIMIT = 10

# [중요] **원본 값 그대로.** `context.py:_build_related_context` 가 `n_results=3` 으로 관련 문서를
# 모으고 발췌를 400자로 자른다. 이 채널이 협력 클래스를 정확히 짚게 하는 근거다 —
# 우리는 그래프(dependents·상속)는 넣으면서 **RAG 채널을 빠뜨리고 있었다**(2026-08-08 발견).
RELATED_LIMIT = 3                 # 문서 수는 원본 그대로 — 이건 토큰 문제가 아니라 신호 문제다
RELATED_QUERY_BODY = 200          # 질의 = 파일 stem + 기존 문서 본문 앞 200자 (원본과 동일)

# [중요] **발췌 길이는 원본 400자에서 올렸다** (사용자 지시 2026-08-08).
# 원본의 400은 **상용 API 토큰 비용** 전제의 값이다. 우리는 로컬 LLM 을 브로커로 부르므로
# 토큰당 비용이 없다 — 관련 문서를 더 보여줄수록 협력 클래스를 정확히 짚는다.
#
# 다만 **무한정은 아니다.** 프롬프트 크기가 BC-250 을 넘어뜨린 전례가 있다(리포트 10 §8).
# 상한을 지키는 축은 두 개다: 이 값과 `synth.SYNTH_NUM_CTX`. **둘을 함께 올릴 것** —
# 발췌만 늘리면 컨텍스트 창을 넘어 뒤가 잘린다(모델이 조용히 앞부분만 본다).
RELATED_EXCERPT = 1500

# [중요] 태그는 영문+한글 병기다 (사용자 지시 2026-08-17). 원전 실물 근거: 문서 저장 도구의
# 태그 예시가 아예 한글이다 (`AgentTest/mcp/context_search/search_tools.py:678` —
# `["전투", "데미지", "HP"]`). 받아온 Project_Alpha 스냅샷 73건에 한글 태그가 섞인 이유이고,
# 우리 프롬프트에 언어 지침이 통째로 빠져 로컬 모델이 영문만 뽑던 것은 **이식 누락**이었다.
# 한글 질의가 문서에 닿는 길이 태그다(클래스명은 한글일 수 없다) — 범용어 금지는
# `thesaurus.register` 의 별칭 가드와 같은 이유·같은 날짜의 결정이다.
# 🔴 [중요] 「## 개선 필요 사항」 절은 **요구하지 않는다** (`#637`, 사용자 결정 2026-10-05 — 측정 없이 뺀다).
#    합성은 요약에만 집중한다. 그 절은 「초고」였고 초고는 리뷰 큐로 옮겨 갔다(`#633` 갈래 C).
#    소비자 셋(verify·synth 협력 신호·벡터)은 이미 그 절을 제외하고, 유일한 실사용이던 BM25 회수
#    손실은 감수한다. 기존 문서의 그 절은 소급 삭제하지 않는다 — 다음 합성 때 자연히 사라진다.
FORMAT = """\
아래 코드 파일을 분석해서 RAG 컨텍스트 MD 파일을 생성해줘.
반드시 아래 형식을 그대로 지켜줘. **다른 설명 없이 MD 내용만 출력해** — 코드 펜스로
감싸지 말고 `---` 로 바로 시작해. [중요] **frontmatter 는 두 번째 `---` 줄로 반드시 닫고**
그 다음에 `## 요약` 을 쓴다(닫는 줄을 빼먹는 실패가 실제로 있었다).

---
tags: [영문태그1, 영문태그2, ..., 한글개념태그1, 한글개념태그2]
category: 대분류/중분류/소분류
related_classes:
  - UExampleComponent: {path_hint}
  - AExampleActor: Source/Example/ExampleActor.h
---

## 요약
(이 섹션만 벡터 임베딩 대상 — 짧고 검색 친화적으로 작성)
- 3~5문장. 이 파일이 다루는 핵심 클래스/함수/매크로/UPROPERTY 식별자는 영어 그대로 노출하고,
  역할·도메인 설명은 한국어로 자연스럽게 혼합한다.
  예: "UMissionTask_Spawn은 몬스터 스포너 컴포넌트와 연동해 스폰 트리거를 관리한다."
- 식별자를 한국어로 번역하지 말 것. UE 매크로(UCLASS/UFUNCTION/UPROPERTY 등)와 함수 시그니처
  키워드는 원형 유지.
- 같은 단어를 의역해 반복하지 말고, 한 번 명명한 식별자를 그대로 다시 사용한다.
- [중요] **주석 처리된 코드는 요약에 기능으로 쓰지 말 것.** 주석 안에만 있는 함수·구조체·열거형을
  "관리한다"·"처리한다" 처럼 서술하면 검증 게이트가 문서를 거부한다(실측 실패 사례).
  대부분이 주석이면 **요약 첫 문장에 그 사실을 먼저** 적고, 살아 있는 기능만 나열한다.

tags 작성 규칙:
- 영문 기술 태그에 **한글 개념 태그 2~4개를 병기**한다 — 사람이 한글로 검색할 때 쓰는
  말이다. 예: 미션, 스폰, 대화창, 상태동기화. (C++ 클래스명은 한글이 될 수 없으므로
  한글 질의가 문서에 닿는 길은 태그뿐이다.)
- [중요] '처리'·'관리'·'기능'·'시스템' 처럼 **어느 문서에나 맞는 범용어는 태그가 아니다.**
  이 파일을 다른 파일과 **구분해 주는** 말만 쓴다. (그 말이 이 파일의 핵심 개념이면 쓴다 —
  예: 완료 수명주기를 정의하는 파일의 '완료 처리' 는 정당한 태그다.)

related_classes 작성 규칙:
- 🔴 위 형식의 두 줄은 **모양만 보여 주는 예시**다. `UExampleComponent`·`AExampleActor` 라는
  이름을 그대로 쓰지 말고 **이 파일의 실제 클래스명**으로 바꾼다. 모양은 언제나
  `  - 클래스명: 파일경로` 다 — 꺾쇠(`<`·`>`)로 감싸지 않는다.
- 자기 자신 클래스뿐 아니라 **협력 관계가 분명한 다른 파일의 클래스도 포함**한다.
  검색에서 두 클래스명을 동시에 던졌을 때 양쪽 모두 회수되어야 하기 때문.
- 협력 관계 판단 기준: #include / UPROPERTY 멤버 타입 / TWeakObjectPtr·TSharedPtr 참조 /
  강한 함수 호출 (Manager·Subsystem 의존 등). 단순한 forward declaration 만 있는 건 제외.
- 협력 클래스 파일 경로를 모르면 **경로 자리에만** `?` 로 적는다 — `  - UActorComponent: ?`
  (검색 토큰 오염 방지 — 키만 인덱싱된다).
  [중요] **항목 전체를 `- ?` 로 쓰지 말 것.** 클래스명을 모르면 그 줄을 **아예 쓰지 않는다.**
- [중요] 각 줄은 반드시 `클래스명: 경로` 다. 꺾쇠로 감싸거나(`- <AFoo>: …`), 경로를 이름
  자리에 두거나(`- Source/A/Foo.h: 설명`) 하면 **소비자가 그 줄을 통째로 버린다**(실측).

[중요] 사실 관계 규칙 — 이걸 어기면 RAG 가 없는 기능을 있다고 안내한다:
- **주석 처리된 코드(`//`·`/* */`·`#if 0`)를 살아 있는 기능처럼 서술하지 말 것.**
  주석 안에만 있는 함수·구조체는 "주석에 흔적이 남아 있다" 처럼 명시적으로 구분한다.
  대부분이 주석이면 요약 첫 문장에 그 사실을 먼저 적는다.
- 🔴 [중요] 그 규칙은 **함수·구조체만이 아니라 주석에만 나오는 모든 이름·약어**에 걸린다.
  코드에 실물이 없고 주석에만 있는 말을 요약에 쓰면 게이트가 문서를 거부한다.
  실측 실패: `// only add IMCs for local player controllers` 뿐인 파일에서 요약이 `IMC` 를
  실재 대상처럼 서술해 거부됐다. 그런 말은 **아예 쓰지 않거나** "주석에 언급만 있다" 로 적는다.
- 본문이 `...`/중간에서 끊겨 있으면 **끊긴 범위를 추측해 채우지 말고** "이 발췌에서
  확인되지 않음" 으로 남긴다.
- `related_classes` 의 경로는 **선언이 있는 헤더(`.h`)** 를 우선한다. 위 [실측] 목록에
  경로가 있으면 그 값을 그대로 쓰고, 없으면 `?`.

주의: "## 코멘트" 섹션은 절대 생성하지 마. 이 섹션은 개발자가 직접 작성하며 시스템이 별도 관리한다.
"""


@dataclass
class Grounding:
    """프롬프트에 실어 보낼 실측 근거. **비어 있으면 비었다고 적는다.**"""

    declared_classes: list[str] = field(default_factory=list)   # 이 파일이 정의하는 클래스
    ancestors: dict[str, list[str]] = field(default_factory=dict)
    siblings: dict[str, list[str]] = field(default_factory=dict)
    dependents: list[str] = field(default_factory=list)         # 이 파일을 #include 하는 쪽
    includes: list[str] = field(default_factory=list)           # 이 파일이 #include 하는 쪽
    related: list = field(default_factory=list)                 # (문서, 발췌) — RAG 채널
    domain_norms: str = ""                                      # 중 1.3 — 아직 없다

    @property
    def empty(self) -> bool:
        return not (self.declared_classes or self.dependents or self.includes or self.related)

    def render(self) -> str:
        out: list[str] = []
        if self.declared_classes:
            out.append("[실측 — 이 파일이 정의하는 클래스 (tree-sitter 파싱 결과)]\n"
                       + "\n".join(f"  - {c}" for c in self.declared_classes[:GROUNDING_LIMIT])
                       + "\n[요약 작성 지시] 위 실측 선언 중 최소 하나의 실제 이름과 역할을 "
                         "`## 요약`에 명시한다. 소문자 보조 구조체도 선언이다. 이름만 나열하지 "
                         "말고 소스에서 확인한 역할을 설명한다. 목록에 없는 선언을 지어내지 않는다.")
        anc = [f"  - {c} → {' → '.join(v[:4])}" for c, v in self.ancestors.items() if v]
        if anc:
            out.append("[실측 — 상속 사슬. `related_classes` 의 부모 쪽을 추측하지 말고 이 값을 쓸 것]\n"
                       + "\n".join(anc[:GROUNDING_LIMIT]))
        sib = [f"  - {c}: {', '.join(v[:5])}" for c, v in self.siblings.items() if v]
        if sib:
            out.append("[실측 — 같은 부모를 가진 형제 클래스 (역할 비교용 참고)]\n"
                       + "\n".join(sib[:GROUNDING_LIMIT]))
        if self.includes:
            out.append("[실측 — 이 파일이 #include 하는 프로젝트 내부 파일]\n"
                       + "\n".join(f"  - {d}" for d in self.includes[:GROUNDING_LIMIT]))
        if self.dependents:
            out.append("[실측 — 이 파일을 #include 하는 파일 (변경 시 영향 범위)]\n"
                       + "\n".join(f"  - {d}" for d in self.dependents[:GROUNDING_LIMIT])
                       + "\n  [주의] 역방향은 파일명 기준 근사다 — 같은 이름 헤더가 여러 모듈에 "
                         "있으면 무관한 항목이 섞일 수 있다.")
        if self.related:
            body = "\n\n".join(f"  [{f}]\n{ex}" for f, ex in self.related[:RELATED_LIMIT])
            out.append("[관련 파일 컨텍스트 — 의존 관계와 연동 로직 참고. "
                       "`related_classes` 를 채울 때 여기 나온 클래스를 우선 고려한다]\n" + body)
        if self.domain_norms:
            out.append("[도메인 규범 — 시스템 전체 구조 파악에만. 정합성 판단은 실제 코드 기준]\n"
                       + self.domain_norms)
        else:
            out.append("[도메인 규범]\n  _없음 — 마일스톤 2 의 중 1.3 이 만든다. "
                       "이 문서는 도메인 맥락 없이 작성된다._")
        return "\n\n".join(out)


# 🔴 `#848` — 상용 CLI(agy·codex)는 도구를 쓰는 에이전트다. 지시가 없으면 저장소를 뒤지고 테스트를
#    돌렸다(실측 2026-10-30 19:08: 186초 · 입력 140405 토큰 · 도구 호출 29회 — `.venv/bin/python -c` ·
#    `unittest` · `find /home/sim`). 판단 재료(본문 무제한·근거·관련 문서)는 이미 프롬프트에 있다.
#    [주의] **상용(`limit=None`)에만** 붙인다 — 로컬 모델은 도구가 없고 문맥 창만 먹는다. `#846` 과 같은 취지.
CLOUD_SCOPE_RULES = (
    "[작업 범위] 판단 근거는 아래 소스 본문·근거·관련 문서로 충분하다. 파일을 열어야 하면 대상 파일과 "
    "그 직접 import 대상만 필요한 만큼 본다. 테스트·린트·빌드·타입 검사를 실행하지 않고, 저장소 전체나 "
    "홈 디렉터리를 검색(find·grep -r 등)하지 않는다. 근거가 모이면 바로 문서를 출력한다."
)


def build(*, files: list[str], bodies: dict[str, str], grounding: Grounding,
          existing: str = "", limit: int | None = CONTENT_LIMIT) -> str:
    """프롬프트 한 덩어리.

    `limit=None` 이면 본문을 자르지 않는다 — 상용 CLI 레인 전용이다 (`#782`).

    `files` 는 **헤더 먼저** 정렬돼 있어야 한다(인터페이스 → 구현 순서). 정렬 자체는
    호출자(`synth.group`)가 한다 — 그룹 규칙과 같은 곳에 두는 게 맞다.
    """
    if not files:
        raise ValueError("파일이 없다 — 빈 프롬프트를 만들지 않는다")

    code = ""
    for f in files:
        body = bodies.get(f, "")
        if not body:
            continue
        code += f"// ── {f} ──\n{body}\n\n"
    if limit is not None:
        code = code[:limit]

    parts = [FORMAT.format(path_hint=files[0]), grounding.render()]
    if limit is None:
        parts.insert(1, CLOUD_SCOPE_RULES)

    dev_comments = ""
    if existing:
        from . import md as md_mod
        dev_comments = md_mod.extract_comments(existing)
    if dev_comments:
        parts.append("[개발자 코멘트 — 이미 인지된 사항이다. 참고만 하고 "
                     "이 섹션 자체는 생성하지 말 것]\n" + dev_comments)

    parts.append(f"파일 경로: {' + '.join(files)}\n```\n{code}\n```")
    return "\n\n".join(parts)
