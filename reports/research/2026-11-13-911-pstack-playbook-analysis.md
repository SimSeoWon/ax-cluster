# #911 — `cursor/plugins` 내 `pstack` 플레이북 정밀 분석 및 Redmine 스펙 아젠다 설계

> 2026-11-13 · Antigravity 리서치 보고서
> 관련 일감: Redmine `#911` (`[AX] 아이디어 — pstack 플레이북 분석: Redmine 일감 스펙 작성에 쓸 아젠다·항목 찾기`)
> 분석 대상: `https://github.com/cursor/plugins/tree/main/pstack` (커밋 `a5539b15a3d56e04992565aafee2b37051329ce3`)
> 목적: 로런 탠(`@poteto`)의 `pstack` 플러그인 실제 소스를 대조하여, AX 클러스터의 일감 착수 전 스펙 작성(`ax-plan` 앞단)과 완료 증거 검증(`#908`)에 이식할 핵심 아젠다 및 메커니즘을 도출함.

---

## 1. 개요 및 핵심 철학

- **핵심 슬로건**: *"If you want to go fast, go deep first"* (빨리 가려면 먼저 깊게 파고들어라)
- **설계 배경**: AI 코딩 에이전트가 사전 맥락 조사 없이 즉흥적으로 코드를 작성·수정(vibe coding)하거나, 단위 테스트 통과만으로 "완료했다"고 자가 보고하는 문제를 차단하기 위해 **엄격한 엔지니어링 규율을 플레이북(Playbook)과 검증 스크립트로 강제**하는 워크플로우 프레임워크다.
- **기본 작동 구조**:
  1. **프론트 라우터 (`/poteto-mode`)**: 사용자의 작업 요청을 분석하여 20여 종의 작업별 플레이북(`feature`, `bugfix`, `multi-phase-plan`, `session-pickup` 등) 중 하나를 매칭한다.
  2. **공정 잠금 (Playbook Locking)**: 선택된 플레이북의 세부 단계(Phases/Steps)를 에이전트의 활성 Todo 목록에 글자 그대로 복제하여, 임의 단계 생략이나 순서 변경을 금지한다.
  3. **전용 서브스킬 체인**: 조사(`/how`, `/why`) → 명세(`/sharpen`, `/architect`) → 재현(`repro-first`) → 파급 측정(`/blast-radius`) → 구현(`/tdd`) → 정제(`/unslop`) → 실물 증명(`prove-it-works`)을 순차 실행한다.

---

## 2. 실제 소스에서 확인된 스펙·플랜 핵심 메커니즘 6가지

### 2.1 `/sharpen` (`pstack/skills/sharpen/SKILL.md:7-16`) — 프롬프트/스펙 심화 4대 질문
작업을 단순히 양적으로 넓히는(bigger) 대신 질적으로 깊게(deeper) 만들기 위해 착수 전에 반드시 답해야 하는 4가지 질문이다:
1. 이 분야 최고의 엔지니어가 내가 미처 요청하지 않았더라도 당연히 먼저 확인·수행할 일은 무엇인가?
2. 누군가 요약·가공해 둔 2차 문서 대신 **가장 날것의 원천 자료(rawest material — 실제 코드, 에러 로그, 패킷, DB 스키마)** 어디서부터 출발할 것인가?
3. 사용할 구체적인 방법과 도구는 무엇인가?
4. 작성자나 요청자의 주관적 판단 외에 **결과가 옳음을 증명할 외부 기준(outside check)** 은 무엇인가?
- **결정 권한 보존 원칙**: *"Leave choices that are mine to make open instead of deciding them."* — 사람이 결정해야 할 설계 선택지를 에이전트가 임의로 닫지 않고 질문 형태로 열어 둔다.

### 2.2 `/in-your-own-words` (`pstack/skills/in-your-own-words/SKILL.md:7`) — 목표·문제 역복창
- 코드나 플랜을 한 줄이라도 작성하기 전에, 에이전트가 이해한 **사용자의 목표(goal)와 풀려는 핵심 문제(problem)** 를 자신의 언어로 먼저 역복창하여 초기 오해를 차단한다.

### 2.3 `/architect` + `rationale-template.md` (`pstack/skills/architect/references/rationale-template.md:5-35`) — 호출자 시점(Usage) 우선 명세
- 내부 구현이나 타입 정의보다 **Usage(호출자·사용자 시점의 사용 예시 2~3개)** 를 맨 먼저 작성한다(*"Usage is the spec. The types serve it"*).
- 스펙 문서의 7단 표준 구조:
  1. `Problem`: 기존 시스템의 제약과 이 문제가 비자명한 이유
  2. `Usage`: 호출자 시점의 구체적 호출/동작 예시
  3. `Shape`: 데이터 구조 우선 정의, 핵심 불변식(Invariants), 그리고 **시스템이 의도적으로 하지 않는 것(Non-goals)**
  4. `Synthesis decision`: 최종 채택한 설계 방향
  5. `Tradeoffs accepted`: *"We accept X in exchange for Y"* 형식의 명시적 트레이드오프 수용 선언
  6. `Alternatives considered`: 기각된 대안과 기각 사유
  7. `Open questions and risks`: 단정이 아닌 **질문 형태**로 기재하여 사람의 답변이 곧 설계 결정이 되도록 구성

### 2.4 `/figure-it-out` (`pstack/skills/figure-it-out/SKILL.md:15-33`) — 반증 가능한 완료 명제와 기준선 선행 캡처
- 착수 전 3가지 프레이밍을 강제한다:
  1. **반증 가능한 명제(Falsifiable Predicate) 형태의 완료 정의**: 무엇이 관측되면 실패이고 무엇이 관측되면 통과인지 명확히 판정 가능한 문장.
  2. **정량화된 범위와 사전 탐색이 드러낸 블로커**.
  3. **되돌리기 어려운 결정(One-way door) 식별** 및 파급 반경에 비례한 검증 강도(Rigor level) 설정.
- **작업 순서 원칙 (`riskiest-unknown-first`)**: 가장 위험하거나 불확실성이 큰 조각을 맨 먼저 검증하며, 기능 구현보다 **검증 하네스 구축과 변경 전 기준선(Pre-change baseline) 캡처**를 먼저 수행해 `old value vs new value`를 대조한다.

### 2.5 `multi-phase-plan.md` & `check-plan.mjs` (`pstack/skills/poteto-mode/scripts/check-plan.mjs:5-192`) — 플랜 구조의 정규식·스크립트 강제
- *"Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked."*
- 모든 작업 단계(Phase)마다 아래 **9개 하위 블록**을 고정 순서로 작성하게 하고, `check-plan.mjs` 스크립트가 기계적으로 검증한다:
  - `Depends on.` → `Files.` → `Build.` → **`You see.`** → `Verify, unit.` → `Verify, live.` → `Verify, perf.` → `Review gate.` → `Merge.`
- 특히 **`You see.`** 블록은 내부 코드 변경이 아니라 *"이 단계가 끝났을 때 터미널 로그나 화면에서 정확히 무엇이 관측되는가"* 를 1줄로 명시하게 강제한다.

### 2.6 `/correct` (`pstack/skills/correct/SKILL.md:17-30`) — 반복 실수의 4계층 구조적 차단
- 에이전트가 같은 실수를 2회 이상 반복할 때 프롬프트 문서만 늘리지 않고 아래 우선순위로 방어벽을 올린다:
  1. **아키텍처 변경**: 잘못된 호출이나 상태를 구조적으로 불가능하게 만듦 (단일 정본화, import 차단)
  2. **타입 / 린트 / CI 정적 검사**: 에러 메시지에 *올바른 대안 호출법*을 함께 출력
  3. **행동 기반 회귀 테스트 (Behavioral Test)**
  4. **문서/규칙 추가**: 1~3으로 잡을 수 없는 순수 판단 영역에만 최후 수단으로 사용하며, 규칙마다 강제하는 코드/검사를 표로 매핑

---

## 3. AX 클러스터 vs `pstack` 1:1 대조

| 비교 축 | `pstack` (`cursor/plugins`) | AX 클러스터 (`AXCluster`) | 시사점 및 결합 방향 |
| :--- | :--- | :--- | :--- |
| **핵심 철학** | *"Go deep first"* + *"Prove it works"* | *"읽어서 확인하지 말고 돌려서 확인한다"* + *"필수 과정은 파이썬이 강제한다"* | 두 시스템의 검증 철학이 100% 일치함 |
| **운영 토폴로지** | 단일 IDE / 로컬 세션 내 서브스킬 체이닝 | 멀티 머신 분산 클러스터 (`.57` 마스터, `.2`/`.43` 워커, `.33` 요청자) | `pstack`의 스펙·증명 규격을 마스터 지휘 스킬(`ax-plan`, `distribute`)에 이식 |
| **사전 조사** | `/how`, `/why` (Read-Only 코드 라인 인용) | `search_context_tool`(RAG) + 실제 소스 대조 + 원전 `~/AgentTest` 확인 | 이슈 스펙에 `how`/`why` 사전 맥락 칸을 명시화 |
| **초반 분류** | `/poteto-mode` 플레이북 분기 | 사용자 제안 3대 초반 질문 (기존 개선 vs 신기능 / 외부 레퍼런스 / 로컬 이식 소스) | `ax-plan` 착수 시 3대 초반 질문을 표준 트리아지(Triage)로 채택 |
| **플랜 검증기** | `check-plan.mjs` (`You see.`, `Verify, unit/live/perf` 체크) | `issue_progress.py` (`ax:plan` v2 파서: 목표·대상·단계·선행·검증·근거) | `ax:plan`의 `검증` 칸에 `You see` + `Unit/Live` 구체 증거 형식 반영 |

---

## 4. Redmine 일감 스펙(`#911`) 및 `ax-plan` 이식용 6대 표준 아젠다

우리 클러스터의 Redmine 일감 본문(스펙)과 `ax-plan`의 `no_spec` / `plan_needed` 단계에 도입할 최종 스펙 아젠다 구성안이다:

1. **문제와 사전 맥락 (`Problem & Grounding` — `/how`, `/why`, `/sharpen`)**
   - 단순 현상 요약이 아니라 현재 코드의 실제 동작(`how`), 기존 설계 의도·제약(`why`), 출발점인 원천 자료(`파일:줄번호`, 리포트 번호, 실측 로그)를 적는다.
2. **초반 분류 3대 질문 (`Triage & Porting Assets`)**
   - ① 기존 기능의 개선/버그 수정인가, 완전히 새로운 신기능인가?
   - ② 참조할 외부/내부 레퍼런스(문서·저장소·이슈)가 있는가?
   - ③ 원전(`~/AgentTest`)이나 다른 트윈/기존 모듈에서 이식·재사용할 소스코드가 있는가? (*만들기 전 3문* 연결)
3. **호출자/사용자 관측 결과 (`Usage & You see` — `/architect`, `multi-phase-plan`)**
   - 내부 구현 설명 대신, 작업 완료 후 호출자·운영자가 실제로 실행할 명령/API와 눈으로 보게 될 출력·화면 변화(`You see: <관측 상태>`)를 1~3줄로 먼저 정의한다.
4. **범위·비범위 및 파급 반경 (`Scope, Non-goals & Blast Radius`)**
   - 허용된 수정 대상 파일 목록, **이번 일감에서 의도적으로 건드리지 않는 비범위(`Out of scope` / `Non-goals`)**, 그리고 변경 시 영향받는 인접 모듈·상주 서비스(`ax-projects`, `ax-task-queue` 등)를 명시한다.
5. **반증 가능한 완료 조건과 실물 증거 (`Prove it works` — `#908` 연계)**
   - *"구현 완료"* 같은 자가 보고 금지.
   - ① 변경 전 기준선(Baseline 또는 실패 재현), ② 단위/정적/공식 통합 검사 명령과 기대 결과, ③ 실제 프로세스/HTTP/워커 라이브 확인 기준(`Pass when <관측 조건>`)을 명시한다.
6. **열린 결정과 트레이드오프 (`Open Questions & Tradeoffs` — `#939`·`#938` 연계)**
   - 에이전트가 임의로 닫지 않고 사람에게 물을 설계 갈림길(`#939` 사전 인터뷰 대상)과, 이번에 수용한 트레이드오프(`We accept X in exchange for Y`) 및 판단 유보 사항(`#938`)을 기록한다.
