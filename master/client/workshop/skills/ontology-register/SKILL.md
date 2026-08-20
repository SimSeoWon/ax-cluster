---
name: ontology-register
description: 사용자가 지정한 시스템 (예 — Mission/UI/Combat/HostMigration) 을 분석해 도메인 MD 를 `.claude/context/_domains/` 에 등록한다. 자동 생성이 아닌 **사용자와의 질의문답으로 의도·목적·경계·invariants 를 명시적으로 캐치**하는 게 핵심 — 자동 승급 도메인이 부족하거나 search_log 가 비어있는 환경에서 사람 주도로 도메인 형성. 자연어 트리거 "Mission 시스템 분석해서 도메인으로 만들어줘", "Combat 도메인 등록", "이 시스템 도메인화" 등에 자동 발동. Phase η.2 MVP.
---

# Ontology Register — 사용자 주도 도메인 등록

## 목적

자동 도메인 승급 (`search_log.jsonl` 동시출현 기반) 이 동작하려면 운영 누적 데이터가 필요한데, baseline 컨텍스트 손실·메가클러스터·신규 환경 등으로 search_log 가 비어있을 때 작동 불능. 이때 **사용자가 잘 아는 시스템을 직접 지정하면** 본 스킬이:

1. RAG (combined_search) + class_graph (find_subclasses/find_ancestors) + dependency_graph (#include) 로 자동 데이터 수집
2. 사용자에게 **질의문답으로 의도·목적·경계·invariants** 캐치
3. 합의된 내용으로만 도메인 MD 작성 → 자동 승급 도메인과 같은 위치·형식으로 저장

자동 생성된 텍스트로 도메인 본문을 채우지 않는다 — 본문은 반드시 사용자와 합의된 내용. 이게 핵심 정신.

## 호출 방법

사용자 발화:
- `/ontology-register <system_name>` — 명시 호출
- "Mission 시스템 분석해서 도메인으로 만들어줘"
- "Combat 도메인 등록"
- "Inventory 시스템 도메인화"
- "HostMigration 도메인 만들어줘"

## 진행 절차

### Step 0 — 시스템 이름 확정

사용자 발화에서 시스템 이름 추출. 모호하거나 추출 불가 시 한 번만 질문:

> "어떤 시스템을 도메인으로 등록할까요? (예: Mission, UI, Combat, HostMigration)"

### Step 1 — 자동 데이터 수집

`context_search` MCP 의 `collect_domain_seed(system_keyword=<이름>)` 호출. 반환된 `brief` 를 사용자에게 그대로 보여준다 (Markdown 요약 — 관련 컨텍스트 MD / 관련 클래스 / 상속 그래프 / 의존성 클러스터).

수집된 데이터가 비어있거나 너무 적으면 (컨텍스트 MD 0건, 클래스 0개) 사용자에게 알림:

> "수집된 시드 데이터가 너무 적습니다 (컨텍스트 N건, 클래스 M개). 시스템 이름이 정확한지, 또는 베이스라인 컨텍스트가 부족한지 확인이 필요합니다."

이 경우 사용자가 진행 여부 결정 (수동 입력으로 진행 / 다른 시스템 이름 / 중단).

### Step 2 — 질의문답 (핵심 단계)

수집된 시드를 입력으로 사용자와 **여러 라운드** 질의문답:

**라운드 1 — 의도·목적**
- "이 도메인의 핵심 책임을 한 문장으로 표현하면? (예: '플레이어에게 부여되는 미션 진행 상태를 추적·갱신하는 시스템')"
- "이 시스템이 왜 존재하나요? 어떤 문제를 해결하나요?"

**라운드 2 — 도메인 경계**
- "수집된 N개 클래스 중 이 도메인에 포함시킬 것은? (사용자가 inclusion 확정)"
- "포함시키지 않을 경계 클래스는? (예: 'UWidget 은 UI 도메인 소속이라 본 도메인에서 제외')"
- "도메인 어디까지가 책임 범위인가요? (예: '미션 데이터 모델까지 — 보상 지급은 Reward 도메인')"

**sub-entity 분리 vs 통합 판정 가이드** — 시드에 sub-entity 후보가 보일 때 (예: `Mission ↔ MissionTask`, `Quest ↔ QuestObjective`, `Inventory ↔ ItemSlot`) 다음을 사용자에게 명시 질문하고 합의:

4-Tier 는 도메인 **간** 계층이지 도메인 **내부** hierarchy 가 아니다. sub-entity 를 별도 Tier 로 올리는 게 아니라, **같은 Tier 3 Domain 안의 OAF Object** 로 통합할지 **별도 Tier 3 Domain** 으로 분리할지의 결정.

다음 신호 중 **하나라도 강하면 분리** (별도 도메인) 권장:
- sub-entity 가 상위 도메인 없이도 의미가 성립함 (예: `MissionTask` 가 데일리 챌린지·튜토리얼·이벤트에서 공유)
- 다른 도메인이 sub-entity 를 직접 참조함 (예: Quest·Achievement 가 `MissionTask` 를 직접 사용)
- sub-entity 의 라이프사이클·권한·invariants 가 상위와 다름 (예: `MissionTask` 는 클라 권한으로 진행도 갱신, `Mission` 은 서버 권한으로 상태 전이)
- sub-entity 의 변경 빈도·작성자가 상위와 다름 (운영상 다른 팀이 만지면 도메인 분리가 자연스러움)

신호가 모두 약하면 **통합** — sub-entity 가 항상 상위 도메인의 sub-object 로만 존재하면 같은 도메인의 OAF Object 로 분류. 별도 도메인 등록 X.

**분리 결정 시 추가 질문** — 사용자에게:
- "[sub_entity] 도메인과 [parent] 도메인을 잇는 매핑 규칙이 있나요? (Tier 4 Bridge 후보 — 예: `MissionTaskCompleted` 이벤트 → `Mission.AdvanceState`)"
- "분리하면 [sub_entity] 도메인을 본 흐름 끝나고 별도로 `/ontology-register` 호출해서 등록할까요?"

분리 권장 신호가 명확하지 않은 회색 지대면 사용자 결정 우선. 에이전트가 임의 판정 금지.

**라운드 3 — 핵심 invariants**
- "이 도메인에서 반드시 지켜져야 하는 규칙은? (예: '미션 상태는 Pending → Active → Completed 순서로만 전이', 'Server 권한에서만 상태 변경')"
- "위반 시 게임 로직이 깨지는 조건은?"

**라운드 4 — 협력 도메인**
- "어떤 도메인과 자주 협력하나요? (예: UI / Reward / Quest)"
- "협력 인터페이스는 무엇인가요? (이벤트, 직접 호출, 데이터 공유)"

**라운드 5 — 자유 형식 의도 메모 (선택)**
- "도메인 MD 에 남기고 싶은 자유 형식 메모가 있나요? (설계 의도, 역사적 맥락, 알려진 제약 등)"

각 라운드는 `AskUserQuestion` 도구로 실행. 사용자가 항목 단위로 답변하거나 자유 텍스트로 입력 가능. 라운드마다 사용자가 "건너뛰기" 선택 시 해당 섹션은 비워둠 (모든 섹션이 필수는 아님 — `## 시스템 개요` 만 필수).

### Step 3 — 도메인 MD 초안 미리보기

사용자 합의된 항목으로 `build_domain_md_template` 의 출력 (frontmatter + 섹션) 미리보기. 그대로 사용자에게 보여주고:

> "이 내용으로 `.claude/context/_domains/<도메인명>.md` 에 저장할까요?"

`AskUserQuestion`:
1. 저장 (기존 파일 없으면 신규, 있으면 거부)
2. 저장 + 덮어쓰기 (기존 파일 무시)
3. 항목 수정 (어느 섹션을 다시 캐치할지 선택 → Step 2 의 해당 라운드 반복)
4. 취소

### Step 4 — 저장 실행

선택에 따라 `register_domain_md` MCP 도구 호출. 인자는 Step 2 의 합의 결과 그대로 전달. 저장 전 검증 게이트 (σ.7-B 동일 정신 — frontmatter 시작 + 최소 길이 + `## 시스템 개요` 섹션 필수) 가 자동 적용.

저장 성공 시 출력 경로를 사용자에게 알림. 실패 시 (예: 검증 실패, 이미 존재 등) 사용자가 원인 보고 → Step 3 으로 복귀.

### Step 5 — 사후 안내

저장 후:
- "다음 watch.exe 폴링 사이클에서 벡터 인덱스에 자동 반영됩니다 (combined_search 에서 검색 가능)."
- "추가 도메인이 필요하면 같은 흐름 반복 — `<다른 시스템> 분석해서 도메인으로 만들어줘`"

## BLOCKING — 호출 금지 사항

- **자동 텍스트로 본문 채우기 금지** — 본문은 반드시 사용자와의 질의문답으로 합의된 내용. 시드 데이터는 사용자가 답변하는 데 도움이 되는 입력일 뿐 본문 텍스트가 아님
- **사용자 확정 없이 저장 금지** — Step 3 미리보기·Step 4 확정 의사 없이 저장 진행 불가
- **여러 도메인 일괄 등록 금지** — 한 번에 하나의 시스템만. 일괄 등록은 정확성을 희생하므로 자동 승급 흐름이 이미 그 역할 수행
- **`.claude/context/_domains/` 외 위치 금지** — Phase η.2 MVP 단계에서는 자동 승급 호환 위치 고정. YAML 위치 (η.2 정식) 는 후속 작업

## 관련 도구

- `collect_domain_seed(system_keyword, project_root, max_classes, include_dependencies)` — 시드 데이터 수집
- `register_domain_md(domain_name, summary, ..., overwrite)` — 사용자 합의 결과 저장
- HTTP 엔드포인트: `/api/v1/ontology/collect_seed` / `/api/v1/ontology/register_domain`

## 운영 환경 권장

- **자동 승급 도메인이 부족한 환경** (신규 배포 / σ.7 사고 직후 / search_log 부재) 에 우선 사용
- **사용자가 잘 아는 시스템부터** 1~2개 등록 → 자동 승급이 누적되기 전 첫 도메인 ground truth 확보
- 본 스킬로 등록된 도메인은 `created_by: ontology-register` frontmatter 필드로 자동 승급 도메인과 구별 가능
