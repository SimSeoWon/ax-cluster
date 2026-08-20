---
name: generate-contract-test
description: 태스크 템플릿의 contracts(pre/post/acceptance)를 검증하는 UE FAutomationTest .cpp 초안을 Claude 가 작성한다. 클라이언트(개발자) PC 에서 실행 — Claude(고신뢰) 가 테스트(명세)를 쓰고, 값싼 분산 워커(Gemma/Gemini)는 구현을 하고, 서버 통합 빌드 게이트가 위반을 잡는 TDD 분업의 "테스트 작성" 단계. 로컬 UE 소스에서 실제 API 를 읽어 컴파일되는 테스트를 만들고, 사람이 검토·커밋한 뒤 템플릿에 tdd:true + test_spec.filter 를 등록한다. 자연어 "이 작업유형 계약 테스트 만들어줘", "MissionTaskAddition TDD 테스트 생성", "contracts 검증 테스트 작성" 에 발동. 분산 작업 결과 검수(/review-work)나 템플릿 등록(/manage-task)과 별개.
---

# Generate Contract Test — 계약 검증 FAutomationTest 작성 (클라이언트측 Claude)

## 본질 (WHY)
TDD 게이트의 목적은 **값싼 LLM 워커(무비용 로컬 Gemma + 토큰 넉넉한 Gemini) 출력의 안전망**이다.
그 검증 테스트를 또 값싼 LLM 이 짜면 자기검증 모순이므로, **신뢰도 높은 Claude 가 테스트(명세)를
작성**하고 값싼 워커는 구현만 한다. 클라이언트 PC 가 적임 — (1) Claude 보유 (2) UE 소스 체크아웃
보유(실제 API 로 컴파일되는 테스트 작성 가능) (3) 서버에 contracts·온톨로지를 검색 요청 가능.
**테스트는 사람 SSOT** — Claude 는 초안, 사람이 검토·커밋. 자동 커밋·환각 API 금지.

## 환경 확인 (BLOCKING)
1. **UE 소스 체크아웃 존재** — `*.uproject` + `Source/`. 본 스킬은 **클라이언트(개발자) PC** 에서 실행
   (서버 빌드 PC 아님). 없으면 즉시 종료 — "UE 프로젝트 루트에서 실행".
2. **서버 RAG/온톨로지 접근** — `get_task_template` 호출 가능(server_mode 면 `<server_url>` HTTP,
   단독이면 `context_search` MCP). 실패 시 종료 + 서버 상태 안내(localhost fallback 금지).
3. **TaskType 인자** — `/generate-contract-test <TaskType>`.

## 흐름
1. **템플릿·계약 로드** — `get_task_template(<TaskType>)` → contracts(pre/post/acceptance) +
   structure + example.refs + summary 수집.
   - **contracts 비어있으면 중단** — 검증할 명세가 없음. "`/manage-task edit <TaskType>` 로
     pre/post/acceptance 먼저 등록" 안내 후 종료.
   - `tdd` 가 이미 false 여도 진행 가능(작성 후 true 로 켬). 단 작업유형이 "시작→성공→다음 단계"
     처럼 **테스트 가능한 명확한 성공 기준**이 있는지 사용자에게 확인 — 없으면 TDD 부적합 안내.
2. **실제 API 확보 (환각 차단의 핵심)** — example.refs 경로 + structure 의 class_pattern 에 해당하는
   클래스를 **로컬 UE 소스에서 Read** 해 실제 헤더 시그니처(함수·프로퍼티·접근자) 확인. 부족하면
   `combined_search`(서버 RAG)로 관련 클래스·호출 패턴 보강. **읽어서 확인한 API 만 사용** — 추측 금지.
3. **FAutomationTest .cpp 초안 작성** — 각 contract 를 테스트 단언으로 매핑:
   - pre/post/acceptance → `TestTrue/TestEqual/TestNotNull` 등. 검증 불가한 항목은 주석으로 `// TODO:
     수동 검증 — <이유>` 명시(거짓 통과 금지).
   - 매크로: 단순 단위면 `IMPLEMENT_SIMPLE_AUTOMATION_TEST`, 시나리오면 `..._COMPLEX_...`.
     flags = `EAutomationTestFlags::ApplicationContextMask | ...::ProductFilter`(헤드리스 `-nullrhi`
     호환). 테스트 이름(필터 경로)은 **프로젝트 컨벤션 따라** 결정(예 `"Project.Mission.Progression"`).
   - 배치 위치: 프로젝트 테스트 컨벤션(예 `Source/<Module>/Private/Tests/`) 따름 — 기존 테스트 있으면
     그 위치·네이밍 미러.
4. **사람 검토** — 초안 .cpp 와 "필터 경로 / 커버하는 contract 항목 / 배치 경로" 를 제시. 사용자가
   수정·승인. **승인 전 파일 쓰기·커밋 금지**.
5. **배치 + 템플릿 등록** — 승인 시:
   - .cpp 를 결정된 경로에 Write (기존 테스트 파일이면 Edit 로 추가).
   - `edit_task_template(<TaskType>, tdd=true, test_spec={"filter": "<필터 경로>", "covers": [매핑한
     contract 참조]})` 호출 — **필터는 .cpp 의 매크로 이름 문자열과 정확히 일치**해야 서버 게이트가
     0건 매칭 안 함.
   - 커밋은 사용자가(테스트=사람 SSOT). 본 스킬은 작성·등록까지, push 는 안내만.
6. **실행은 서버 게이트가** — 실제 red-green(컴파일+RunTests)은 **서버측 통합 빌드 게이트**
   (`integration_build` / `/review-work`)가 머지 전에 수행. 클라이언트 로컬 빌드+`UnrealEditor-Cmd
   RunTests` 로 사전 확인은 선택(비용 큼 — 안내만, 강제 X).

## 안전 가드
- **테스트 = 사람 SSOT** — Claude 초안, 사람 검토·커밋. 자동 커밋 금지([[feedback_claude_internals_autoclean]]
  의 "기계 산출물"이 아닌 소스코드 영역).
- **읽은 API 만** — example.refs·헤더에서 확인한 시그니처만 사용. 환각 API 로 비컴파일 .cpp 를 만들면
  통합 빌드를 깨뜨려 역효과.
- **필터 일치** — `test_spec.filter` ⟺ .cpp 매크로 이름 정확히 일치(불일치 시 RunTests 0건 →
  서버 카나리 `[verify-test] 매칭 0건`).
- **자기검증 모순 회피** — 본 스킬은 **Claude** 가 작성. 같은 값싼 LLM(Gemma/Gemini 워커)이 테스트도
  짜는 것 금지(검증 의미 상실).
- **검색 채널 불변식 유지** — 템플릿 자체는 도메인 검색에 미인덱싱. 본 스킬은 get/edit_task_template
  (구조 레지스트리)만 사용.
