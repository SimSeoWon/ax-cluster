# Uber Agent Skills 최적화 체크리스트 분석 및 AX 클러스터 스킬 체계 대조 보고서

> 작성일: 2026-11-28 · 작성: Antigravity (Gemini 4 Neon) 리서치 보고서  
> 관련 일감: Redmine `#1052` (`아이디어 — 추후 검토 수집`)  
> 분석 대상: Uber Engineering Blog — *Optimizing Uber's Agent Skills* (`https://www.uber.com/us/en/blog/optimizing-ubers-agent-skills/`) 및 관련 에이전트 스킬 운영 아키텍처 (월 100만 회 호출 · 5,000+ 사내 스킬 규모)  
> 대조 대상(AX 클러스터): `docs/skill-authoring.md`, `master/test_skill_conventions.py`, `master/skills/*` · `master/client/skills/*` · `master/client/workshop/skills/*` (실측 30개 스킬)  
> 목적: 우버의 대규모 Agent Skills 설계·최적화·평가 체크리스트를 분석하고, AX 클러스터의 현행 스킬 규약·테스트와 대조하여 **이미 확보한 강점**, **부족한 4가지 축**, **도입 시 주의사항**을 정리함.

---

## 1. 개요: 우버가 풀려는 문제와 핵심 철학

우버는 1년 만에 사내 에이전트 스킬을 1개에서 **5,000개 이상**, 월간 호출 **100만 회** 규모로 키우면서 *"스킬을 많이 만들수록 오히려 컨텍스트가 오염되고, 오발동·미발동·낡은 절차로 에이전트 품질이 떨어지는 문제"*에 직면했다. 이를 해결하기 위해 우버는 스킬을 단순 프롬프트 조각이 아니라 **버전 관리·스펙·정량 평가(Evals)·자가 개선 루프를 갖춘 소프트웨어 산출물**로 다루는 체크리스트와 파이프라인을 정립했다.

---

## 2. 우버 Agent Skills 최적화 체크리스트 상세 분석

### 2.1 3단계 점진적 공개 (Progressive Disclosure — 3-Layer Rule)
대규모 스킬 카탈로그에서 컨텍스트 윈도우 폭발과 토큰 비용을 막기 위해 스킬을 3개 계층으로 분리 로딩한다.

| 계층 | 로딩 시점 | 포함 내용 | 우버 기준선 |
| --- | --- | --- | --- |
| **Tier 1 (Discovery)** | **상시 로딩** | `SKILL.md` YAML frontmatter의 `name` + `description` | **스킬당 ~100 토큰** 이내 |
| **Tier 2 (Activation)** | **스킬 발동 시** | `SKILL.md` 본문 핵심 절차 | **500줄 미만**, 단일 워크플로우 집중 |
| **Tier 3 (On-Demand)** | **특정 단계 도달 시** | 상세 레퍼런스·스키마·템플릿·실행 스크립트 | `references/` · `scripts/` · `assets/` 분리 |

### 2.2 Frontmatter `description` 최적화 (트리거 품질 결정)
- 에이전트가 스킬을 켤지 말지 판단할 때 보는 유일한 텍스트가 Tier 1 `description`이다.
- **수동적 요약 금지**: *"이 스킬은 X를 처리합니다"* 대신 **명령형 트리거**(*"~할 때 이 스킬을 쓴다"*)로 작성.
- **경계 명시**: 어떤 의도·키워드·파일 유형에서 발동해야 하는지(그리고 언제 쓰지 말아야 하는지)를 좁고 선명하게 적어 **미발동(under-trigger)**과 **오발동(over-trigger)**을 동시에 억제.
- **네이밍 규약**: `name`은 폴더명과 정확히 일치(소문자·숫자·단일 하이픈, 1~64자).

### 2.3 Spec-First & Ablation / Trajectory 평가 (Evals)
- **Spec-First**: `SKILL.md`를 바로 쓰지 않고 기대 산출물·대상 모델·경계를 적은 `spec.md`를 먼저 작성한 뒤 스킬과 테스트 프롬프트 세트를 도출.
- **Ablation 테스트 (있음 vs 없음)**: 실제 사용자 프롬프트를 깨끗한 환경에서 **스킬 활성 / 비활성으로 2회 리플레이**하고 블라인드 판정(Blind Judge)으로 실효성을 검증.
- **Trajectory(경로) 지표 측정**: 최종 답의 정답 여부뿐 아니라 **도구 오류 수 · 도구 호출 횟수 · 세션 소요 시간**을 함께 추적.
  - 우버 사내 DW 질의 스킬 실측 사례: 스킬 없이 실행했을 때 대비 스킬 적용 시 **도구 오류 6배 감소 · 도구 호출 13% 감소 · 실행 시간 31% 단축**.
- **단위 경제성 공식**: `Users × Sessions × Turns × Requests × Tokens × Token Price`로 토큰 비용을 실시간 가시화.

### 2.4 Git 거버넌스 & Papercut 자가 개선 루프
- **Git 정본 & 소유권**: 모든 스킬을 중앙 Git 저장소에 두고 명시적 소유자·PR 코드리뷰·변경 이력을 관리.
- **Papercut 피드백 루프**: 에이전트가 스킬을 수행하다 겪은 작은 결함(낡은 CLI 플래그, 깨진 도구 호출, 모호한 분기 등 **papercut**)을 자동 수집해 스킬 소유자에게 환류하는 지속 정비 루프 운영.

---

## 3. AX 클러스터 현행 스킬 체계 실측 및 1:1 대조

### 3.1 AX 클러스터 스킬 실측 현황 (2026-11-28 기준)
- **정본 규약**: [docs/skill-authoring.md](file:///home/sim/ax-cluster/docs/skill-authoring.md) + 자동 강제 검사 [master/test_skill_conventions.py](file:///home/sim/ax-cluster/master/test_skill_conventions.py) (`#890` T7 · `#898`).
- **등록 스킬 총계**: **30개** (`master/skills/*` · `master/client/skills/*` · `master/client/workshop/skills/*`).
- **본문 길이**: 최대 **467줄** (전 스킬 500줄 미만 규약 통과, 단 일부 대형 스킬은 상한 근접).
- **Tier 1 `description` 합계**: **7,168자** (스킬당 평균 **239자**, 최대 **444자**).
  - 상위 5개: `generate-contract-test`(444자) · `ax-issue`(388자) · `refresh-ontology`(345자) · `cleanup-drift`(339자) · `ontology-register`(317자).

### 3.2 항목별 1:1 대조표

| 체크리스트 항목 | Uber 기준 | AX 클러스터 현황 (`test_skill_conventions.py`) | 격차 / 판정 |
| --- | --- | --- | --- |
| **Tier 1 `name` 규약** | 폴더명 일치, 1~64자 소문자·하이픈 | `NAME = ^[a-z0-9-]{1,64}$`, `name == d.name` 자동 강제 | **동등 (충족)** |
| **Tier 1 `description` 예산** | 스킬당 ~100 토큰 목표, 트리거·비범위 명시 | 상한 **1,024자** (실측 평균 239자, 최대 444자, 총 7,168자). 비범위 표기 비일관 | **개선 여지 있음** |
| **Tier 2 본문 길이 & 구조** | 500줄 미만, 단일 워크플로우 | **500줄 미만** + 100줄 초과 시 앞 100줄 내 `## 목차`·`사용 예` 자동 강제 | **AX가 구조 검사 더 엄격** |
| **Tier 3 분리 (`reference/`·`scripts/`)** | 무거운 문서·스크립트 분리 | `reference/`·`scripts/` 1단계 번들 + 링크 실존 + 인라인 `python -c` 금지 | **동등 (충족)** |
| **도구/권한 정합성** | 스킬 실행 중 도구 오류 최소화 | 배달 역할별 MCP 서버·실재 도구 일치 검증 (`#898`, `role_tool_problems`) | **AX 고유 강점** |
| **행동 평가 (Ablation / Trajectory)** | 있음 vs 없음 리플레이 · 오류/호출/시간 측정 | **없음** (정적 문법·구조 검사만 존재) | **가장 큰 공백** |
| **교차 모델 검증 (Claude vs Codex)** | 대상 모델별 동작 검증 | 수동 경험 의존 (`#1050`·`#1051`에서 Codex만 오동작 사후 발견) | **도입 가치 높음** |
| **Papercut 피드백 루프** | 실행 중 마찰 자동 수집·환류 | 실패 장부(`record_check`)·MCP 오류 로그는 있으나 스킬 정비 환류 미연결 | **도입 가치 높음** |

---

## 4. AX 클러스터에 도입 검토할 핵심 아이디어 4선

### 4.1 경량 스킬 행동 평가(Trajectory / Ablation Eval) 하네스 ★ 최우선
- **문제**: `test_skill_conventions.py`는 형식만 잡는다. `#1050`·`#1051`에서 보았듯, 같은 스킬(`ax-plan`)과 같은 서버라도 **Claude와 Codex의 해석·에러 반응이 달라** 운영 중에야 장애가 터진다.
- **AX 적용안**:
  - 핵심 마스터·요청자 스킬(`ax-plan`, `ax-redmine`, `distribute`, `ax-ontology`, `ax-issue`)마다 3~5개의 **고정 시나리오 프롬프트(정상 2 · 경계/오발동 방지 1 · 실패/거절 복구 1~2)**를 `reference/evals.yaml`(또는 별도 `tests/skill_evals/`)로 둠.
  - 스킬 수정 시 Claude/Codex에서 리플레이해 **도구 오호출 횟수 · 거절 후 복구 여부 · 기대 MCP 도구 호출 순서(Trajectory)**를 대조(무거운 5,000개 규모 인프라가 아니라 핵심 5개 스킬 대상 경량 스위트).

### 4.2 Tier 1 `description` 다이어트 & 비범위(Negative Trigger) 규약 추가
- **문제**: 현재 30개 스킬의 `description` 합계가 7,168자이며 상한이 1,024자로 느슨하다. 스킬이 50개 이상으로 늘면 매 턴 컨텍스트를 갉아먹고 유사 스킬(`ax-ontology` vs `ontology-register` vs `refresh-ontology`, `ax-plan` vs `ax-issue`) 간 오발동이 잦아진다.
- **AX 적용안**:
  - `docs/skill-authoring.md` 및 `test_skill_conventions.py`에 `description` 권장/경고 상한(예: 300자 경고, 500자 실패) 검토.
  - 유사 역할 스킬 쌍에 **"이럴 때는 쓰지 않음 → `<다른 스킬>`"** 한 줄을 명시해 오발동 차단.

### 4.3 Papercut(스킬 마찰) 자동 수집 → 정비 후보 리포트
- **문제**: 세션 중 스킬 지침과 실제 도구/플래그가 어긋나거나 모델이 반복적으로 같은 에러를 맞아도, 사람이 직접 일감을 열지 않으면 기록이 흩어진다.
- **AX 적용안**:
  - 이미 축적 중인 `interview_ledger.json`(실패 장부 `failures` · `stop_blocks`), `task_queue` 4xx/거절 로그, `search_log`에서 **반복 거절 패턴을 주간/온디맨드 스크립트(LLM 0)**로 집계해 `reports/` 또는 `_skill_papercuts.md`로 제안(자동 수정 없음, `#1041-B`와 동일 철학).

### 4.4 `SKILL.md` 상한 근접 스킬의 Tier 3(`reference/`) 분리 점검
- 현재 최대 길이 스킬이 467줄로 500줄 상한에 근접해 있다. 조건부 절차나 장문 예시를 `reference/`로 분리하면 활성화(Tier 2) 시 컨텍스트 점유를 줄이고 모델 주의력 분산을 완화할 수 있다.

---

## 5. 주의사항 및 배제할 요소

1. **우버의 5,000개 스킬용 중앙 마켓플레이스/인프라 직수입 금지**: AX는 30개 규모의 소수정예 홈 클러스터다. 별도 평가 플랫폼이나 DB를 세우지 말고 기존 `master/test_skill_conventions.py` + Git + 가벼운 시나리오 리플레이 수준으로 유지해야 한다.
2. **스킬 `description` 과도 축약으로 인한 한국어 트리거 누락 주의**: AX 스킬은 한국어 자연어 발화(`"일감 이어서"`, `"워커에 배포해"`)로 발동되므로, 영어 기준 100토큰을 기계적으로 자르면 핵심 한국어 발화 예시가 빠져 오히려 미발동(under-trigger)이 늘 수 있다. **중복 서술과 부가 설명을 줄이고 핵심 발화·비범위만 남기는 방향**이 안전하다.
3. **LLM 블라인드 판정기(Judge) 남용 금지**: 로컬 추론 노드(`.2`/`.43`) 자원 제약을 고려해, 1차 평가는 **도구 호출 시퀀스·인자·거절 복구 여부 같은 결정적 Trajectory 검사**를 우선하고 LLM 판정은 필요 시 상용 세션에서만 보조로 사용한다.

---

## 6. 결론

AX 클러스터의 **정적 스킬 규약(`docs/skill-authoring.md` · `test_skill_conventions.py`)은 이미 우버 체크리스트의 구조·보안 항목을 거의 동등하거나 더 엄격하게 충족**하고 있다. 지금 AX에 가장 큰 레버리지를 줄 다음 단계는 정적 규약 추가가 아니라, **① 핵심 스킬 대상 경량 Trajectory/Ablation 평가(특히 Claude↔Codex 교차 검증), ② 유사 스킬 간 `description` 경량화 및 비범위 명시, ③ 기존 실패/거절 로그 기반 Papercut 환류 루프** 3가지다.
