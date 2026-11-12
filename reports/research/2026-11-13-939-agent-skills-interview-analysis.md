# #939 — `addyosmani/agent-skills` 선행 분석: 사전 인터뷰(`interview-me`) 및 클러스터 이식 설계

> 2026-11-13 · Antigravity 리서치 보고서
> 관련 일감: Redmine `#939` (`[AX] 아이디어 — addyosmani/agent-skills 분석: 작업 시작 전 인터뷰 로직 등 클러스터 이식 요소 발굴`)
> 분석 대상: `https://github.com/addyosmani/agent-skills` (커밋 `301b02b12bff98e4688e6984af6556802322bbde`)
> 목적: Addy Osmani의 `agent-skills` 저장소(21개 스킬, 7개 커맨드, 4개 레퍼런스)를 전수 분석하여, 작업 시작 전 인터뷰 로직(`interview-me`)을 비롯한 핵심 엔지니어링 가드레일을 AX 클러스터 및 사내 AX 인프라에 이식하는 방안을 정립함.

---

## 1. 저장소 개요 및 아키텍처 철학

- **구성**: 21개 엔지니어링 스킬(`skills/*/SKILL.md`), 7개 슬래시 커맨드(`commands/*.md`), 4개 오케스트레이션 레퍼런스(`references/*.md`), 멀티 에이전트 플러그인 매니페스트(`.claude-plugin/`, `.cursor-plugin/`, `.codex/`, `.gemini/`).
- **생명주기 6단계 모델**:
  - **Define(정의) → Plan(계획) → Build(구현) → Verify(검증) → Review(리뷰) → Ship(배포)**
  - 각 단계 전환마다 **사람의 의도 확인 게이트(Human Gate)** 와 **에이전트의 기준 하향·우회 꼼수를 막는 하한선 가드(Floor Guard)** 를 짝지어 배치한 것이 가장 큰 특징이다.
- **점진적 공개 (Progressive Disclosure)**:
  - 21개 스킬 본문을 상시 시스템 프롬프트에 다 넣지 않고, 세션 시작 시에는 각 스킬의 `description`(발동 조건과 역할 요약)만 노출한 뒤 해당 단계에 진입할 때만 개별 `SKILL.md`와 `references/`를 로드해 컨텍스트 예산을 아낀다.

---

## 2. 핵심 분석: 작업 시작 전 인터뷰 로직 (`skills/interview-me/SKILL.md:1-235`)

단순히 *"애매하면 질문하라"*는 선언적 지시가 아니라, **사용자의 답변 피로도를 최소화하면서 에이전트의 숨은 가정을 강제로 수면 위로 끌어올리는 6단계 프로토콜**로 설계되어 있다.

### 2.1 발동 조건 및 무인(Non-interactive) 환경 가드 (`SKILL.md:14-36`)
- **발동 조건**: 계획·스펙·코드를 작성하기 전, 아래 4대 요소 중 하나라도 비어 있거나 모호할 때 발동한다:
  1. `Who` (누가/어느 호출자가 쓰는가)
  2. `Why` (왜 지금 필요한가 / 기존 문제는 무엇인가)
  3. `Success` (무엇이 관측되면 성공인가)
  4. `Constraint` (하드 제약과 비범위는 무엇인가)
- **무인 실행 금지 가드 (`Loading Constraints`)**:
  - CI 파이프라인, 배치 작업, 무인 워커 파견 등 사람이 대화창에 없는 비대화형 컨텍스트에서는 **절대 인터뷰를 발동하지 않고**, 에이전트가 채택한 가정을 `ASSUMPTIONS` 블록으로 명시한 뒤 진행한다.
  - **AX 클러스터 정합성**: 우리 클러스터의 리포트 64 원칙(*"워커는 묻지 않는다 — 질문은 마스터 대화창에서만"*)과 정확히 부합한다.

### 2.2 Step 1 — 코드/문서 선조회 후 가설(`HYPOTHESIS`) + 확신도(`CONFIDENCE %`) 제시 (`SKILL.md:54-69`)
- **Detect before you ask (`constraint-driven-development/SKILL.md:40-49`)**:
  - 저장소의 코드, 설정 파일, 기존 문서에서 읽어서 알 수 있는 사실을 사람에게 물어보지 않는다.
- **첫 턴 가설·확신도 의무 표기**:
  - 첫 질문 전에 반드시 에이전트가 현재 이해한 1문장 가설과 확신도(%)를 먼저 브리핑한다:
    ```text
    HYPOTHESIS: <사용자가 달성하려는 목표 1문장 추정>
    CONFIDENCE: ~65% — <70% 미만일 경우 무엇이 비어 있는지 1줄 이유 필수>
    ```

### 2.3 Step 2 — 한 번에 질문 1개 + 에이전트의 추정 답안(`GUESS`) 동봉 (`SKILL.md:71-89`)
- 한 턴에 질문 4~5개를 번호 매겨 쏟아내면 사용자의 인지 부담이 급증하고 답변 품질이 떨어진다. **가장 불확실성이 큰 질문 단 1개**만 던진다.
- 이때 빈칸 질문만 던지지 않고 **에이전트의 추정 답안(`GUESS`)과 그 근거 1줄**(필요시 모를 때의 기본값 `DEFAULT if unsure`)을 반드시 함께 붙인다:
  ```text
  Q: <가장 핵심적인 갈림길 질문 1개>
  GUESS: <에이전트의 추정 답안 — 코드/문서 근거 1줄>
  DEFAULT if unsure: <사용자가 유보할 경우 채택할 안전한 기본값>
  ```
- **효과**: 사람은 백지에서 답을 작문하는 것보다 에이전트의 틀린 추정을 교정(*"아니, A가 아니라 B야"*)하는 것이 훨씬 빠르며, 에이전트가 머릿속으로 어떤 전제를 깔고 있는지 즉시 드러난다.

### 2.4 Step 3 — "Want vs. Should Want" 탐침 (`SKILL.md:91-106`)
- 사용자가 관성적인 모범답안이나 유행어(*"확장성 있게"*, *"엔터프라이즈급으로"*, *"베스트 프랙티스대로"*)로 답하면, 그대로 수용해 과잉 설계(Over-engineering)로 가는 대신 한 번 더 찌른다:
  - *"남에게 이 설계를 정당화할 필요가 없다면, 지금 당장 실제로 필요한 가장 단순한 동작은 무엇인가요?"*

### 2.5 Step 4 & 5 — 6줄 구조화 요약(`Restate`) + 명시적 승인 (`SKILL.md:108-145`)
- 인터뷰를 마칠 때 반드시 사용자의 언어로 아래 **6개 필수 항목**을 요약해 보여준다:
  1. `Outcome`: 1문장 결과 요약
  2. `User`: 대상 사용자 또는 호출 컴포넌트
  3. `Why now`: 배경 및 해결하려는 문제
  4. `Success`: 관찰 가능한 완료 기준
  5. `Constraint`: 하드 제약 조건
  6. **`Out of scope`: 이번에 하지 않을 것 (생략 불가 필수 항목)**
- **위임과 승인의 구분**: 사용자가 *"알아서 해줘(Whatever you think)"*라고 답하면 승인으로 간주하지 않고, 가장 갈리는 지점의 **구체적 선택지 2개(A vs B)**로 좁혀 명시적 선택을 받는다.

### 2.6 Step 6 — 수렴 판정 및 **즉시 턴 종료(Terminal Turn)** (`SKILL.md:147-169`)
- **종료 기준**: 확신도가 `~95%`에 도달해 *"다음 질문 3개에 대한 사용자의 반응을 예측할 수 있는가?"*를 충족하거나, 여러 라운드 후에도 확신도가 더 오르지 않을 때(남은 미확정 사항을 `Open assumptions`로 기록하고 종료).
- **Terminal Action 규칙**: 사용자가 6줄 요약에 승인하기 전이나 직후 같은 턴에서 곧바로 하위 구현 도구를 호출하지 않고 **즉시 턴을 멈춰 단계 경계를 지킨다**.

---

## 3. 클러스터에 이식 가치가 높은 추가 스킬 5선

### 3.1 `spec-driven-development` (`skills/spec-driven-development/SKILL.md:22-175`)
- **Phase 0 (Capability Map)**: 단일 요청에 독립적으로 검증 가능한 기능이 여러 개 묶여 있으면, 상세 스펙 작성 전에 **10줄 이내의 기능 분해 표(`Module id` | `Responsibility` | `Depends on` | `Build order`)**를 먼저 제안해 승인받는다.
- **3-Tier Boundaries**: 스펙에 `Always do`(항상 지킬 것) / `Ask first`(먼저 물어볼 것) / `Never do`(절대 건드리지 말 것) 3단 경계와 `ASSUMPTIONS I'M MAKING`을 명시한다.

### 3.2 `doubt-driven-development` (`skills/doubt-driven-development/SKILL.md:50-194`)
- 비자명한 아키텍처·보안·동시성 변경을 커밋하기 전에 수행하는 5단계 반론 검증 루프(`CLAIM` → `EXTRACT` → `DOUBT` → `RECONCILE` → `STOP`):
  - **핵심 기법 (`Step 2 EXTRACT`, line 74-96)**: 검토자(서브에이전트 또는 교차 모델 CLI)에게 넘길 때 **작성자의 주장(`CLAIM`)과 자기변호 논리는 완전히 제거하고, 순수 산출물(`ARTIFACT`)과 계약 조건(`CONTRACT`)만 추출**하여 확증 편향을 원천 차단한다. 외부 CLI 호출 시에는 프롬프트 인젝션과 셸 깨짐을 막기 위해 셸 보간(shell interpolation)을 금지하고 파일/stdin으로만 전달한다.
  - **판정 우선순위 (`Step 4 RECONCILE`, line 133-155)**: `1. 계약 오독(Contract misread)` > `2. 유효·조치 필요(Valid + actionable)` > `3. 유효한 트레이드오프(Valid trade-off)` > `4. 노이즈(Noise)` 순으로 분류하며, 2사이클 연속 유효 지적이 0건이면 **"Doubt theater(보여주기식 의심)"**로 판정해 즉시 멈춘다(최대 3사이클).

### 3.3 `constraint-driven-development` (`skills/constraint-driven-development/SKILL.md:160-240`)
- **Floor Guard (에이전트 5대 꼼수 차단)**: 에이전트가 테스트·린트 게이트를 통과시키려고 기준선 자체를 낮추는 현상을 막기 위해 `git diff`에서 다음 5가지를 감사한다:
  1. 커버리지·성능·검증 임계치 하향 조정
  2. 기존 테스트 삭제, `@skip` 처리, 또는 핵심 assertion 제거
  3. 린터/타입 체커 억제 주석(`# noqa`, `# type: ignore`, `eslint-disable`) 무단 추가
  4. 미완성 스텁(`TODO`, `FIXME`, `pass`, `raise NotImplementedError`) 잔류
  5. 승인되지 않은 예외 목록(allowlist/ignorelist) 추가
- **Ratchet (`Measured, not yet enforced`)**: 레거시 코드베이스가 당장 이상적인 기준을 충족하지 못할 때 억지 목표를 세우는 대신, **오늘의 실측치를 기준선(Baseline)으로 박고 "현재보다 나빠지지 않을 것"만 강제**한다.

### 3.4 `context-engineering` (`skills/context-engineering/SKILL.md:123-325`)
- **Confusion Management (line 123-152)**: 스펙과 실제 코드가 충돌할 때 에이전트가 조용히 하나를 골라 덮어쓰지 않고, `CONFUSION:` 또는 `MISSING REQUIREMENT:` 블록으로 선택지 A/B와 코드 영향도를 제시해 멈춘다.
- **Dead-end Compression (line 210-310)**: 탐색 중 기각된 가설이나 실패한 경로는 긴 시행착오 로그를 남기지 않고 **"기각된 경로 1줄 결론(이유 포함)"**으로 압축하여 컨텍스트 오염을 막는다.

### 3.5 `source-driven-development` & `references/orchestration-patterns.md`
- **UNVERIFIED 명시 & 비신뢰 데이터 취급**: 근거 문서가 없으면 추측하지 않고 `UNVERIFIED`로 표기하며, 외부에서 읽어들인 문서·이슈 본문은 명령이 아닌 비신뢰 데이터(Untrusted Data)로 취급한다.
- **오케스트레이션 반패턴 (`orchestration-patterns.md:50-115`)**: 지휘자가 사용자 원문을 자기 말로 요약·변형해 워커에 전달하는 'Paraphrasing Router'는 토큰을 2배로 쓰면서 원문 제약을 손실시키므로, 검증된 원문 계약과 파일 경로 목록을 직접 전달하고 호출 깊이는 `depth <= 1`로 유지한다.

---

## 4. AX 클러스터 매핑 및 단계별 도입 로드맵

| `agent-skills` 핵심 요소 | AX 클러스터 접점 | 이식 우선순위 및 적용 방법 |
| :--- | :--- | :--- |
| **`interview-me`** (`Detect before ask` + `HYPOTHESIS/CONFIDENCE` + `1 Q & GUESS` + `6줄 Restate`) | `master/skills/ax-plan/SKILL.md` (`no_spec` / `plan_needed`), `#911`, `#938` | **[1순위]** `ax-plan` 착수 전 인터뷰 표준 프로토콜로 채택 (`#911`의 6대 스펙 항목 및 `#938`의 판단 유보 필드와 결합) |
| **`spec-driven` Phase 0 Capability Map & 3단 경계** | `master/skills/distribute/SKILL.md` | **[1순위]** 다중 조각 분산 일감 분해 시 10줄 이내 `Capability Map` 표와 `Always / Ask first / Never` 경계를 먼저 제시 |
| **`doubt-driven` `EXTRACT` & 2사이클 종료** | `master/skills/debate/SKILL.md` 및 리뷰 프롬프트 | **[2순위]** 리뷰어/토론 에이전트 입력에서 작성자의 자기변호(`CLAIM`)를 제거하고 `diff + 스펙 계약`만 전달 |
| **`constraint-driven` `Floor Guard` 5대 감사** | `master/pystatic.py`, `followup.py`, `#908` | **[2순위]** 마감 전 `git diff`에서 assertion 삭제·`@skip`·무단 `# noqa`·미완성 스텁을 자동 검출하는 완료 게이트 추가 |
| **`context-engineering` `CONFUSION` & 실패 1줄 압축** | `docs/orchestrator-handoff.md`, `reports/`, `#841` | **[3순위]** 인수인계서와 리포트 작성 시 기각된 경로는 1줄로 압축하고, 스펙-코드 충돌 시 `CONFUSION` 블록으로 보고 |
