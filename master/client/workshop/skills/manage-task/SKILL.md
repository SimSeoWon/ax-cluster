---
name: manage-task
description: 재사용 가능한 "작업 유형 템플릿"(태스크 온톨로지)을 등록·조회·수정·제거한다. 도메인 온톨로지가 "어떤 개념·클래스가 있다"(구조 지식)면, 태스크 템플릿은 "이런 작업을 어떻게 추가하는가"(구조+예제+규약+계약)의 플레이북이다. 분산작업·에이전트가 리프 단 신규 구현 시 이 템플릿을 읽어 예제·규약대로 따라가 환각을 막는다(TDD 정합). 자연어 "작업 템플릿 등록/추가", "미션 태스크 추가 패턴 만들자", "이런 작업 유형 등록해줘", "태스크 템플릿 목록/수정/삭제" 에 발동. 도메인 등록(/manage-domain)의 태스크판.
---

# Manage Task — 태스크 템플릿(작업 유형) 레지스트리

## 목적
재사용 작업 유형을 `.claude/ontology/tasks/<TaskType>/task.yaml` 에 등록한다(도메인 `domains/` 와 나란히).
prescriptive — 사람이 "이 작업 유형 = 이런 구조·예제·규약·계약" 을 등록하면, `/distribute` 와 에이전트가
신규 작업 시 `get_task_template` 로 읽어 grounding(환각 차단). **도메인 검색 채널과 별개** — 검색
인덱싱 안 하는 구조 레지스트리(이름으로 get/list).

## 환경 확인 (BLOCKING)
1. `.claude/vector_db/class_graph.db` 존재 (example 구조 추론에 사용).
2. server_mode 면 `<server_url>/api/v1/ontology/*task_template*` HTTP, 단독이면 `context_search` MCP 직접.
   응답 실패 시 즉시 종료 + RAG 서버 상태 안내(localhost fallback 금지). 서버 PC 에서만 의미.

## 호출 방법
- `/manage-task list` — 등록된 템플릿 목록 (read-only)
- `/manage-task create <TaskType>` — 신규 등록 (대화형)
- `/manage-task show <TaskType>` — 단일 조회 (`get_task_template`)
- `/manage-task edit <TaskType>` — 필드 수정
- `/manage-task remove <TaskType>` — 제거
- 자연어 — "미션 태스크 추가 템플릿 만들자", "보스 레이드 같은 작업 유형 등록"

## 흐름

### 생성 (create) — 대화형, example 기반 `[INFERRED]` 구조 제안
1. **TaskType 결정** — **영문 PascalCase·무공백**(예 `MissionTaskAddition`). 한글 이름은 `title` 에.
   (도메인과 동일 — URL·도구 인자 안전. 비ASCII 면 거부됨.)
2. **example 인스턴스 지정** — 사용자에게 "이 작업 유형의 **기존 대표 사례** 클래스" 를 묻는다
   (예: SpawnMonsterTask). 그 클래스로부터 **그래프 조회로 structure 후보를 `[INFERRED]` 제시**:
   - `mcp__ax-client__get_object_spec(domain, class)` 로 베이스·동반 클래스
     ([주의] domain 인자 필요 · `find_ancestors`/`find_subclasses` 는 **아직 미위임** —
      부르기 전에 응답 여부를 확인하고, 없으면 추측으로 대체하지 말고 마스터에 요청한다)
   - `dependency_search(file, direction=both)` 로 함께 쓰이는 파일(에디터뷰·데이터·실행자 등)
   → 역할별 세트(structure) + 실측 경로(example.refs) 초안을 표로 제시. **LLM 추측 아니라 그래프 조회**.
3. **사용자 확정/정정** — structure(역할·class_pattern·base) / conventions(명명·베이스·금지) /
   contracts(preconditions·postconditions·acceptance — 자유서술, Phase ε 에서 정형화) 를 대화로 확정.
   silently 채우지 말 것 — 사람이 의미·규약을 확정.
3b. **TDD 사용 여부 확정 (`tdd` / `test_spec`)** — **기본 false(테스트 안 함)**. 사용자에게
   "이 작업 유형은 자동 테스트(red-green)로 검증할까요?" 를 묻는다. **켜는 기준**: "과업을 성공하면
   다음 단계로 넘어간다" 같은 **진행 불변식이 핵심**이라 깨지면 사용자가 소프트 프리징되는 작업유형
   (예: 미션 태스크). 켤 때만 `tdd=true` + `test_spec={filter:"<AutomationTest 필터 prefix>",
   covers:[검증할 계약 참조]}` 확정. **필터는 UE 프로젝트에 실재하는 `FAutomationTest` 이름 참조** —
   테스트 .cpp 자체는 사람/워커가 UE 프로젝트에 작성(이 레지스트리는 작성 안 함, 필터만 가리킴).
   tdd=false 면 test_spec 생략. **AskUserQuestion 으로 명시 확정 — 추측해서 켜지 말 것.**
   → tdd=true 로 켰는데 아직 테스트 .cpp 가 없으면 **`/generate-contract-test <TaskType>`** 안내:
   클라이언트(개발자) PC 에서 Claude 가 contracts·로컬 UE 소스 API 로 FAutomationTest 초안을 작성한다
   (값싼 워커가 아닌 Claude 가 테스트를 쓰는 게 TDD 분업의 핵심).
4. **확정 후에만** `create_task_template(task_type, title, summary, related_domains, structure,
   example, conventions, contracts, tdd, test_spec)` 호출. 결과 보고(path, structure_roles).

### 조회/소비 (show)
- `get_task_template(task_type)` → 구조 dict + raw YAML. **이게 소비 진입점** — `/distribute` 나
  code-writer 가 신규 작업(예 "보스 레이드 태스크") 시 매칭되는 템플릿을 읽어 구조·예제(참조 경로)·
  규약·계약대로 구현. (소비 자동 배선은 후속 — 현재는 사람/에이전트가 명시 조회.)

### 수정 (edit) / 제거 (remove)
- `edit_task_template(task_type, <변경 필드만>)` — 제공 인자만 갱신, 나머지 보존.
- `delete_task_template(task_type)` — 디렉토리째 제거.

## 안전 가드
- **TaskType 영문 PascalCase 강제** (비ASCII 거부) — URL·도구 인자 호환.
- **example 은 참조(경로 링크)** — 코드 스니펫 박제 금지(코드 변하면 stale). 실측 경로만.
- **검색 인덱싱 안 함** — 태스크 템플릿은 `ontology_domains`/`bm25_domains` 에 안 들어감(도메인 검색과
  경합 방지). 이름으로 get/list 하는 구조 레지스트리.
- **code_recipes 와 별개** — 레시피는 자동 합성 보조 신호, 템플릿은 사람이 등록한 권위 플레이북.
- **TDD 는 명시 opt-in (`tdd=true`)** — 기본 false. 문서(템플릿)에 tdd 미선언이면 **테스트 케이스를
  작성·실행하지 않는다**. tdd=true 인 템플릿만 통합 빌드 게이트가 `test_spec.filter` automation
  테스트를 실제 실행하고, 실패 시 빌드 실패와 동일 흐름(merge_status=build_failed)으로 반려한다.
