---
name: distribute
description: 분산 코드 생성 시스템에 새 작업을 등재한다. 사용자와 대화로 요구사항을 수집하고 클래스/모듈 계층 플랜을 작성·승인받은 뒤, 스켈레톤 파일을 생성하고 (UE 도메인이면 리제너레이트도 실행한 후) task_queue 에 leaf → manager 순서로 등재한다. 도메인 무관 — UE5 UI 위젯, UE5 게임플레이 시스템, 서비스·매니저 클래스, Python/MCP 도구 등 여러 클래스/모듈이 상속·포함·import 관계로 묶이는 작업에 모두 적용. 단일 함수 수정 같은 작은 작업에는 사용 금지.
---

# Distribute — 분산 작업 등재 스킬

## 목적

서버측 마스터(=현 Claude Code 세션)가 **클래스/모듈 설계·인터페이스 결정**까지 마치고 본문 구현은 **클라이언트 워커들에게 분산**시킨다. 워커는 야간/주말 유휴 시간에 의사코드만 보고 본문을 채운다.

본 스킬은 사용자와 대화로 요구사항을 수집 → 플랜 → 승인 → 스켈레톤 작성 → (UE 도메인이면) UE 리제너레이트 → task_queue 등재의 한 사이클을 자동화한다.

## 적용 도메인

도메인 무관 패턴 — 예시:

| 도메인 | 작업 단위 | 예시 |
|--------|-----------|------|
| **UE5 UI (UMG/Slate)** | 위젯 파일 (.h/.cpp 페어) | `UMS_InventorySlot` + `UMS_ItemTooltip` + `UMS_InventoryHUD` |
| **UE5 게임플레이** | 컴포넌트·액터·서비스 클래스 | `UMS_DamageReceiver` + `UMS_HealthComponent` + `UMS_DamageMediator` |
| **Service/Manager** | 매니저·라이브러리 클래스 | `UMS_TooltipManager` + `UMS_NotificationQueue` |
| **Python/MCP** | 모듈·클래스 | `tag_index.py` + `frontmatter_parser.py` + `IndexCoordinator` |
| **일반 C++ 라이브러리** | 헤더 + 구현 페어 | 자체 유틸·알고리즘 라이브러리 |

도메인에 따라 사용하는 의사코드 태그 집합과 검증 항목이 다르다 (Step 4 참조).

## 호출 방법

**현재 분산 작업은 "포팅" 시나리오만 지원합니다** — 워커 LLM 이 신규 설계까지 일관되게 잡아내기 어려워 1차 범위를 포팅으로 한정. 따라서 **참조할 원천 소스 폴더가 필수**.

- `/distribute <원천소스폴더> <기능 설명>` — 포팅 작업 (정상 형태)
- `/distribute <기능 설명>` — 원천 폴더 누락 → Step 0 에서 사용자에게 요청
- `/distribute` — 인자 없음 → Step 0 에서 작업 내용 + 원천 폴더 요청

자연어 트리거:
- "`C:/Projects/OldGame/Source/Legacy/UI/` 폴더 보고 인벤토리 UI 포팅해줘"
- "이전 프로젝트의 X 시스템 이식 작업으로 등재해"
- "UE4 의 Y 매니저를 UE5 서브시스템으로 옮겨"

원천 폴더 없이 신규 개발 요청만 들어왔을 때:
- "분산 작업은 현재 포팅 (참조 코드 있는 이식) 만 지원합니다. 어디 있는 어떤 코드를 옮길지 원천 소스 폴더의 절대경로를 알려주세요."
- 사용자가 "참조 없이 그냥 만들어" 하면 → "그 경우 분산 등재 대신 메인 세션에서 직접 작성하거나 `code-writer` 위임을 권합니다." 로 안내 후 즉시 종료.

## 사용 금지 (BLOCKING)

다음 경우 스킬 발동 X:

- **단일 함수 수정** — 분산할 가치 없음 (마스터가 직접 수정)
- **기존 클래스 미세 변경** — 의사코드 contract 가 의미 없음
- **task_queue 서버 미동작** — 먼저 `task_queue.exe --serve <root>` 확인 요청
- **스켈레톤 거주 repo 가 없음** — UE 게임 repo 경로 확인 필요

부적합 시 사용자에게 확인:
> "이 작업은 분산보다 직접 처리가 빠릅니다. 그래도 진행할까요?"

## 모든 Step 공통 — git 직접 호출 금지 (BLOCKING)

distribute 흐름 동안 메인 세션은 **`Bash` 도구로 git 명령을 직접 호출하지 않는다**. 모든 git 작업은 `master_orchestrator` MCP 도구로 위임:

| 하지 말 것 | 대신 사용 |
|---|---|
| `Bash("git checkout -b ...")` | `mcp__master-orchestrator__prepare_work_branch` |
| `Bash("git add ...; git commit ...")` | `mcp__master-orchestrator__register_skeletons` 가 내부에서 처리 |
| `Bash("git push ...")` | 위 두 도구가 자동 push |
| `Bash("git status")` 진단용 | 상태 확인은 master_orch 응답값 또는 `git rev-parse --abbrev-ref HEAD` 1회만 (idempotent 점검 시) |

**이유**: 메인 세션의 Bash 도구가 잡은 git 핸들이 master_orchestrator 의 git 작업과 lock 충돌. `.git/index.lock` 또는 ref lock 점유 시 master_orch 의 `git checkout -b` 가 무한 대기 → distribute 전체 hang. 메인 세션 종료 (창 닫기) 로만 풀림.

git 상태 확인 필요한 경우 (Step 3.5 idempotent 점검 등) 에는 짧은 read-only 명령 (`git rev-parse --abbrev-ref HEAD`) 1회만 허용. 그 외는 절대 X.

## 모든 Step 공통 — 진행 가시성 (BLOCKING)

스킬 흐름 중 사용자 가시성을 위해 **모든 step 마다 다음 4가지를 반드시** 수행한다:

1. **Step 진입 알림** — Step 시작 직전 한 줄로 사용자에게 알림. 예: `[Step 3.5/8] 브랜치 분리 시작합니다.`
2. **상태 idempotent 점검** — Step 본 동작 진입 전 현재 상태 확인. 이미 완료된 상태면 skip 하고 그 사실을 사용자에게 보고. 예: 이미 feature 브랜치 위면 prepare_work_branch 호출 안 함, "이미 격리됨" 보고
3. **MCP 호출 직후 결과 1줄 보고** — 도구 응답 받으면 즉시 핵심만 1줄로 사용자에게 출력. 다음 도구 호출이나 LLM 추론을 시작하기 전에. 예: `prepare_work_branch 결과: branch=feature/X, pushed=true, base=9b470abf` 한 줄 출력 후 Step 4 진입
4. **Step 완료 알림 + 다음 step 진입** — Step 끝나면 `[Step N/8 완료] 요약` 출력 후 다음 step 진입 알림

**침묵 금지** — MCP 도구 호출 직후 30초 이상 메인 세션이 다른 추론·도구 호출에 들어가면 사용자 입장에서 "hang" 으로 보임. 결과 받으면 항상 즉시 보고 후 다음 단계.

**도구 hang 감지** — MCP 호출이 30초 이상 응답 없으면 사용자에게 안내:
> "도구 응답이 늦습니다. `.claude/logs/master_orchestrator_<오늘>.log` 또는 `task_queue_<오늘>.log` 끝부분 확인 부탁드립니다.
> 함수 진입 흔적이 있는데 응답이 안 오면 권한 prompt 가 백그라운드에 떠있을 수 있습니다 (Claude Code UI 확인)."

## 진행 절차

### [Step 0/8] 환경 확인 (BLOCKING)

다음 모두 충족돼야 진행:

1. **task_queue 서버 health check** — `mcp__task-queue__status_summary` 호출 가능. 정상이면 watch.exe 가 자동 spawn 한 데몬 동작 중. 실패하면 `.claude/logs/task_queue_stdout.log` 와 `task_queue_<date>.log` 점검, 사용자에게 watch.exe 재기동 요청 (수동 명령 금지 — 자동 시작이 표준)
2. **UE 게임 repo 경로** — 사용자 설정 또는 `config.json` 의 `repo_dir` 확인. 없으면 사용자에게 절대경로 요청
3. **master_orchestrator 접근 가능** — `mcp__master-orchestrator__analyze_skeletons` 호출 가능
4. **UE 엔진 root (UE 도메인일 때만)** — 우선순위:
   - a) `<project_root>/config.json` 의 `ue_engine_root` (PC 별 1회 설정)
   - b) `.uproject` `EngineAssociation` 자동탐지 (Launcher 설치판만 동작)
   - c) 둘 다 실패하면 사용자에게 묻기:
     > "UE 엔진 root 경로를 입력하세요. 소스 빌드는 자동탐지 불가입니다.
     > 예시: `D:/UE5_Source/UnrealEngine` (Engine/Build/BatchFiles/Build.bat 가 있는 디렉토리)"
     → 받은 값은 `config.json` 의 `ue_engine_root` 에 저장 (다음부터 묻지 않도록 Read/Edit 도구로 직접 갱신)
   소스 빌드 엔진은 자동탐지가 안되므로 a 또는 c 필수.

하나라도 미충족 시 진행 중단, 사용자에게 명시적 안내.

5. **PC 역할 확인** — `<project_root>/config.json` 의 `server_mode` / `context_server_url` 확인:
   - `server_mode: true` (서버 PC) 또는 둘 다 미설정 (단독 모드) → 진행
   - `context_server_url` 설정됨 (클라이언트 PC) → **즉시 중단**:
     > "이 PC 는 클라이언트 모드입니다. 분산 작업 등재는 서버 PC 에서만 수행하세요.
     > 큰 작업이 필요하면 리더에게 요청하시거나, 작은 단위 수정은 `code-writer` 또는 메인 세션 직접 처리로 진행하세요."

6. **분산 의사 확인** (BLOCKING) — Plan 작성 전이지만, /distribute 가 호출됐다는 건 사용자가 분산 의사를 표현한 것. 그래도 호출 직후 한 번 더 명시 확인:
   > "이 작업을 분산 워커 시스템에 등재할까요? 다음 동작이 일어납니다:
   > - feature 브랜치 자동 생성
   > - 스켈레톤 (의사코드만 박힌 .h/.cpp/.py) 작성
   > - task_queue 에 work + tasks 등재 (워커 PC 들이 야간/주말에 본문 채움)
   > - UE 도메인이면 GenerateProjectFiles + 빌드 게이트
   > - 다음주 리더 그룹 리뷰 후 main 머지
   >
   > 빠른 일회성 작업이면 'no' 후 메인 세션이 직접 처리하거나 `code-writer` 사용을 권장합니다."

   사용자 'no' 또는 망설이면 즉시 종료 + `code-writer` 위임 또는 메인 직접 처리 안내.

7. **원천 소스 폴더 (`source_dir`) 필수 확인** (BLOCKING) — 현재 분산 작업은 포팅만 지원. 호출 인자에서 폴더 경로를 추출 못했으면 진행 전 사용자에게 명시 요청:
   > "분산 작업은 현재 **포팅 (참조 코드 있는 이식) 시나리오만 지원**합니다.
   > 워커가 같은 stem 의 원천 파일을 자동 매칭해서 의도 파악에 활용하므로 원천 소스 폴더의 절대경로가 필요합니다.
   >
   > 예: `C:/Projects/OldGame/Source/Legacy/UI/`
   >
   > 어떤 폴더의 코드를 참조하시겠습니까? (없으면 분산 등재 대신 메인 세션 직접 처리 또는 `code-writer` 위임을 권합니다)"

   - 사용자가 경로 제시 → 디스크 존재 검증 (`os.path.isdir` 또는 Glob 1회) → 통과해야 다음 step
   - 사용자가 "없다" 또는 "참조 없이" 응답 → 즉시 종료 + 대안 안내. 추측 절대 X
   - 경로가 존재하지 않음 → 다시 입력 요청 (반복)

### [Step 1/8] 대화형 요구사항 수집

**먼저 도메인을 확인** — 이후 질문 세트가 도메인에 따라 달라진다.

```
Q: 어떤 도메인의 작업입니까?
   - UE5 UI (UMG 위젯)
   - UE5 게임플레이 (액터·컴포넌트)
   - UE5 서비스/매니저
   - Python/MCP 도구
   - 일반 C++ 라이브러리
   - 기타 (직접 입력)
```

도메인 확정 후 공통 질문:

1. **어떤 기능을 만드는가?** (예: "인벤토리 위젯 패밀리", "데미지 처리 시스템", "태그 인덱스 모듈")
2. **메인 사용처·호출 흐름은?** (어디서 누가 호출하는지)
3. **기존 베이스 클래스/베이스 모듈이 있는가?** (프로젝트 표준 부모)
4. **외부 의존이 있는가?** (워커가 호출만 할 매니저·서비스·외부 라이브러리)
5. **데이터 타입·DTO 가 있는가?**
6. **컨벤션 룰북 참조가 필요한가?**

도메인별 추가 질문:

| 도메인 | 추가 질문 |
|--------|----------|
| UE5 UI | BindWidget 멤버 명명, BP 위젯 명명 규칙 |
| UE5 게임플레이 | Replication 필요 여부, HasAuthority 가드 위치, RPC 종류 |
| UE5 서비스 | 싱글톤·서브시스템 여부, 라이프사이클 |
| Python/MCP | 외부 패키지 의존 가능 여부, 비동기 함수 여부, 타입 힌트 강제 |
| 일반 C++ | 헤더 only 여부, 템플릿 사용, 외부 라이브러리 의존 |

답변이 모호하면 더 묻기. 추측해서 진행 X.

**원천 소스 폴더 (`source_dir`) — 필수 확인** (Step 0 의 7번에서 이미 받았어야 함):

7. **원천 소스 폴더** (`source_dir`) — 워커가 참조할 이전 프로젝트 소스 절대경로
   예: `C:/Projects/OldGame/Source/Legacy/UI/`
   → 워커가 같은 stem 의 파일을 찾아 참조 소스로 활용
   → 분산 작업은 현재 **포팅만 지원**. source_dir 없이 진행 금지 — Step 0 으로 돌아가 사용자에게 재요청

추가로 확인:
- 클래스/모듈을 몇 개로 쪼갤지 (3개? 5개? 10개?)
- 작업 큐 우선순위 (시급한 것 / 일반)
- **forbidden_patterns** — 워커가 쓰면 안 되는 패턴. 도메인별 예시:
  - UE 공통: `GEngine->`, `UKismetSystemLibrary::PrintString`, `UE_LOG` 임의 사용
  - 게임플레이: 클라에서 권위 없는 상태 변경, `Server_*` 함수의 `HasAuthority()` 누락
  - Python: `eval`, `exec`, 절대경로 하드코딩, `print` (logger 사용 강제)

### [Step 1.4/8] 분산 중복 작업 사전 검사 (BLOCKING)

분석·스켈레톤 생성 같은 비싼 단계 진입 전에 같은 slug + target_repo 의 active work (merge_status not in {merged, rejected, cancelled}) 가 있는지 확인. 중복 발견 시 사용자에게 명시 confirm 받은 후에만 진행.

```
mcp__master-orchestrator__check_work_duplicates(
    target_repo="<repo 절대경로 — Step 0 에서 확정한 game_repo_path>",
    title="<Step 1 의 1번 답으로 결정된 work_title>",
    queue_url="http://localhost:8101"
)
```

응답: `{ok, slug, target_repo, duplicates: [{work_id, title, target_branch, merge_status, redmine_issue_id, total, verified, created}, ...]}`

**분기**:

- `duplicates: []` → 흐름 변수 `confirm_duplicate=False` 로 두고 다음 단계로 (정상 흐름)
- `duplicates: [...]` (1건 이상) → BLOCKING 알림:

  ```
  ⚠ 동일한 내용의 분산 작업이 이미 진행 중이거나 머지를 대기 중입니다.

  • work_id   : 20260510_1621_<slug>
    제목      : <title>
    브랜치    : origin/feature/<slug>_20260510
    진행상태  : 8/10 verified, merge_status=ready_for_review
    Redmine  : #9                              (있을 때만)
    생성     : 2026-05-10T16:21:00+09:00

  정말 신규 분산 작업으로 추가 등록하시겠습니까?
    예  → 새 work 를 별개로 등록하고 분석/스켈레톤 진행
    아니오 → 즉시 종료. 기존 work 에 task 추가 또는 finalize 로 머지 권장
  ```

  사용자 응답 처리:
  - **예** → 흐름 변수 `confirm_duplicate=True` 로 설정. Step 1.5 이후 정상 흐름 진행. **Step 7 register_skeletons 호출 시 반드시 `confirm_duplicate=True` 명시** (없으면 task_queue 가 또 거절).
  - **아니오** → 즉시 흐름 종료. 사용자에게 다음 안내:
    > 기존 work `<work_id>` 에 task 를 추가로 등재하려면 별도로 등재 도구를 사용하시거나, 머지 단계라면 `master_orchestrator --finalize <work_id> --repo <repo>` 로 진행하세요.

> **방어 깊이**: 사용자가 어떤 이유로 사전 confirm 을 안 하고 Step 7 까지 진행해도 task_queue 가 자체 dedupe 로 거절 (`{ok:False, reason:"duplicate", duplicates:[...]}`). 그 경우도 동일 알림 후 confirm 받아 `confirm_duplicate=True` 로 재호출.

### [Step 1.5/8] 기존 코드 분석 — agy 위임 (선택)

**이식·리팩토링 작업이고 참조할 기존 소스가 있을 때만** 수행. 신규 개발이면 스킵.

```
mcp__master-orchestrator__analyze_codebase(
    repo_path="<git repo 경로>",
    context="<요구사항 요약 — 어떤 기능을 이식/리팩토링하는지 한 문단>"
)
```

결과 분석 문자열을 `analysis_result` 로 보관 → Step 2 `generate_work_plan` 의 `analysis` 인자로 전달.
결과 1줄 보고: `[Step 1.5/8] 분석 완료: files_analyzed=N`

**상용 CLI 쿨다운 감지**: 응답이 `"AgyCooldown:"` 으로 시작하면 상용 CLI 토큰 소진 상태.
→ 분석 스킵하고 Step 2 로 진입. Claude 가 요구사항만으로 직접 플랜 작성.
> `[Step 1.5/8] agy 쿨다운 중 (until=<시각>). 분석 스킵 → Claude 직접 플랜 작성.`

완료 알림: `[Step 1.5/8 완료] → Step 2 플랜 작성.`

### [Step 1.5b/8] 작업 유형 템플릿 매칭 (Phase ζ — 등록된 템플릿이 있으면 plan 의 권위 골격)

분산 작업이 **등록된 작업 유형 템플릿**(예 `MissionTaskAddition` = "미션 태스크 추가" 플레이북)에
해당하면, 그 템플릿의 구조·예제·규약을 plan 의 뼈대로 쓴다 (자유 설계 대신 검증된 패턴 → 환각 차단).

1. `mcp__context-search__list_task_templates()` 로 등록 템플릿 목록 조회.
2. 이번 작업이 어떤 템플릿에 해당하는지 판단: **사용자가 명시했으면 그것**, 아니면 title·related_domains·
   키워드로 **후보를 제안하고 사용자 확인**. 매칭 없으면 템플릿 없이 기존 자유 흐름(생략, Step 2 로).
3. 매칭 시 `mcp__context-search__get_task_template("<name>")` → 흐름 변수 `matched_template` + 그 구조 보관.
   - `structure`(역할별 클래스 세트)를 **Step 2 plan 의 행으로** 매핑 (신규 작업명으로 치환 —
     예 SpawnMonster→BossRaid: enum 값·`FMissionTaskData_BossRaid`·`UMissionTask_BossRaid`·executor
     dispatch·editor 위젯…).
   - `example.refs`(기존 1건 실측 경로)는 `Read` 로 패턴 확인용 (복사 X).
   - `conventions` → Step 7 의 `forbidden_patterns`/`convention_refs` 인자에 합류.
   - 템플릿은 **작업유형 권위** — 따르되 최종 정합은 실제 코드(example.refs Read)로 확인(도메인 온톨로지
     소비와 동일 정신: 네비·예제는 템플릿, 확정은 코드).

> 매칭 안 되면 이 단계 전체 생략 — 템플릿은 등록된 작업 유형에만 적용. 새 유형이면 작업 후 `/manage-task`
> 로 템플릿화 권유 가능(선택).

### [Step 2/8] 계층 플랜 작성

수집한 정보로 플랜 작성. 표 형태로 사용자에게 제시. 도메인에 따라 필드 조정.

**agy 위임 옵션 (파일이 많거나 복잡할 때 권장)**:

```
mcp__master-orchestrator__generate_work_plan(
    analysis="<Step 1.5 분석 결과 또는 빈 문자열>",
    task_description="<Step 1 요구사항 전체>",
    repo_path="<게임 repo 경로>"
)
```

응답의 `plan.files` 를 아래 표 형태로 변환해 사용자에게 제시 후 Step 3 승인 진행. `plan` JSON 은 Step 4 `generate_skeletons` 인자로 그대로 전달.

**상용 CLI 쿨다운 감지**: 응답에 `"cli_cooldown": true` 가 있으면 상용 CLI 토큰 소진 상태.
→ Claude 가 직접 아래 표 형식으로 플랜 작성 (위임 없이 진행).
> `[Step 2/8] agy 쿨다운 중 (until=<시각>). Claude가 직접 플랜을 작성합니다.`

직접 작성 시 (쿨다운 또는 소규모 작업): 아래 기존 표 형식 그대로 작성.

**UE5 UI 예시**:
```
| # | 클래스명 | 역할 | 부모 | 포함 | 계층 |
| 1 | UMS_InventorySlot | 단일 슬롯 | UMS_BaseWidget | UButton, UImage | L0 |
| 2 | UMS_ItemTooltip | 툴팁 | UMS_BaseWidget | UTextBlock | L0 |
| 3 | UMS_InventoryHUD | 그리드 컨테이너 | UMS_BaseWidget | UMS_InventorySlot[] | L1 |
```

**UE5 게임플레이 예시**:
```
| # | 클래스명 | 역할 | 부모 | 의존 | 계층 |
| 1 | UMS_HealthComponent | 체력 보관·변동 | UActorComponent | - | L0 |
| 2 | UMS_DamageReceiver | 데미지 수신·HasAuthority 체크 | UActorComponent | UMS_HealthComponent | L1 |
| 3 | UMS_CombatMediator | 가해자·피해자 결합 | UObject | UMS_DamageReceiver | L2 |
```

**Python/MCP 예시**:
```
| # | 모듈/클래스 | 역할 | import 의존 | 계층 |
| 1 | frontmatter_parser.py | YAML frontmatter 파싱 함수 | - | L0 |
| 2 | tag_index.py | 태그 → 파일 역색인 | frontmatter_parser | L1 |
| 3 | IndexCoordinator | 다중 인덱스 통합 관리 | tag_index | L2 |
```

플랜 표 + 다음 메타 섹션:

```
## 계층 의존성
(L0/L1/L2 가 누가 누구에 의존하는지 자연어 설명)

## 큐 등재 순서
1. <leaf 1> (L0) — 의존 없음
2. <leaf 2> (L0) — 의존 없음
3. <manager> (L1) — depends_on=[1, 2]

## 메타
- 도메인: <UE5 UI / UE5 게임플레이 / Python/MCP / ...>
- base_commit 기준 브랜치: <repo>/main 의 최신
- forbidden_patterns: <도메인별 명시>
- 컨벤션 참조: <있으면 경로>
- 예상 본문 분량: 클래스당 N-M줄
- UE 리제너레이트 필요: 예 / 아니오 (UE 도메인이면 예)
```

각 클래스/모듈마다 **함수·메서드 목록 미리보기** 도메인 형식에 맞게:

UE C++:
```
### UMS_InventorySlot
- NativeConstruct() — 버튼 바인딩
- SetItem(UMS_ItemInstance*) — 아이콘·카운트 갱신
```

Python:
```
### tag_index.py
- build_index(md_files: Iterable[Path]) -> int
- search(tags: list[str], match_all: bool = False) -> list[Path]
- list_tags() -> list[str]
```

### [Step 3/8] 사용자 승인 (BLOCKING)

플랜 제시 후 명시적 승인. **브랜치 격리는 필수이고 이름은 항상 자동 생성** — 사용자가 main/master 같은 보호 브랜치명을 실수로 입력해 격리가 무력화되는 것을 사전 차단.

> 이 플랜으로 진행할까요?
>
> 진행 시 자동 동작:
> - feature 브랜치 자동 생성 (`feature/<slug>_<YYYYMMDD>`)
> - 모든 commit 이 그 브랜치에 들어감, main 은 무결
> - 다음주 리더 그룹 리뷰 후 main 머지 결정
>
> **승인 명령**:
> - 진행: '예' / 'yes' / '진행' / 'go'
> - 수정: 어느 부분을 어떻게 바꿀지 알려주세요
> - 취소: '취소' / '아니오'

**브랜치명 사용자 지정 옵션 없음** — 자동 생성만. 만약 사용자가 명시 브랜치명을 강하게 원하면 스킬 종료 후 `git branch -m feature/<auto> <원하는이름>` 으로 사후 변경.

격리 거부 시 스킬 즉시 종료:
> "본 스킬은 브랜치 격리 없이 진행할 수 없습니다 (main 보호 + 주간 리뷰 게이트가 핵심 안전장치).
> 격리 없이 진행하시려면 `/distribute` 가 아니라 메인 세션이 직접 작성하거나 `code-writer` 위임을 사용하세요."

승인 없이 다음 단계 진행 절대 금지. 사용자가 수정 요청하면 Step 2 로 돌아가서 플랜 재작성.

다음 단계로 전달: `branch_isolation=True`, `target_branch=""` (자동 생성 강제).

### [Step 3.5/8] 브랜치 분리 + 원격 동기화 (Write 전 필수, BLOCKING)

진입 알림 출력: `[Step 3.5/8] 브랜치 분리 시작합니다. 로컬 + origin push.`

**(가) idempotent 상태 점검**: Bash 로 `git rev-parse --abbrev-ref HEAD` 실행. 결과가 이미 `feature/...` 형태면 사용자에게 알리고 prepare_work_branch 호출 skip:
> `[Step 3.5/8] 이미 feature 브랜치 위 (X). 분리 단계 skip 합니다.`

main 또는 다른 브랜치면 prepare_work_branch 호출.

**(나) MCP 호출**:
```
mcp__master-orchestrator__prepare_work_branch(
    repo="<git repo 경로>",
    title="<work title — Step 1 의 기능 설명에서 도출>",
    branch_isolation=True,
    target_branch=""   # 항상 비움 — feature/<slug>_<YYYYMMDD> 자동 생성 (보호 브랜치명 차단)
)
```

내부 동작:
- 로컬 `git checkout -b feature/<slug>_<YYYYMMDD>` (즉시)
- `git push -u origin feature/<slug>_<YYYYMMDD>` (ref 만, 빠름)

응답: `{ok, branch, base_commit, isolated, pushed, push_error}`.

**(다) 결과 1줄 즉시 보고** — 응답 받자마자 다음 도구 호출·LLM 추론 들어가기 전에 반드시 사용자에게 출력:
> `[Step 3.5/8] 결과: branch=feature/X, base=abc12345, pushed=true` (성공 시)
> `[Step 3.5/8] 결과: branch=feature/X, pushed=false, error=<push_error>` (push 실패 시)

응답의 `branch`/`base_commit` 을 **메모해뒀다가 Step 7 의 `target_branch` 로 그대로 전달**.

**`pushed=False` 면 사용자에게 명시 안내**:
> "feature 브랜치 origin push 실패: <push_error>
> 이대로 진행하면 워커 PC 들이 이 작업을 fetch 못합니다.
> git auth (credential.helper / SSH key) 점검 후 재시도하시거나, 단독 모드에서만 진행할 거면 무시 가능합니다."

`ok=False` 면 (브랜치 자체 생성 실패) 즉시 중단.

**git auth 사전 구성 필요** — push 가 대화형 인증 요구하면 자동화가 멈춤. 한 번 인증되면 credential manager 가 캐싱. 5분 timeout 후 fail-safe 종료.

**완료 알림**: `[Step 3.5/8 완료] feature 브랜치 격리 OK. → Step 4 스켈레톤 작성으로 진입.`

### [Step 4/8] 스켈레톤 작성 (BLOCKING)

진입 알림: `[Step 4/8] 스켈레톤 N개 작성 시작합니다.` (N은 plan 의 파일 개수)
완료 알림: `[Step 4/8 완료] N개 파일 작성. → Step 5 사전 검증.`

사용자 승인 후 **아래 두 가지 방식 중 하나를 선택**한다. 혼용 금지.

#### 방식 A — agy 위임 (파일이 많거나 보일러플레이트가 많을 때 권장)

```
mcp__master-orchestrator__generate_skeletons(
    work_plan_json="<Step 2/3 에서 확정된 plan JSON 전체>",
    repo_path="<게임 repo 경로>"
)
```

응답의 `results` 로 생성된 파일 목록 확인. 오류 파일은 직접 Edit/Write 로 보정 후 Step 5 진입.
결과 1줄 보고: `[Step 4/8] agy 스켈레톤 생성 결과: created=N, failed=M`

**상용 CLI 쿨다운 감지**: 응답에 `"cli_cooldown": true` 가 있으면 상용 CLI 토큰 소진 상태.
→ 방식 B(직접 Write)로 전환해 나머지 파일들을 Claude 가 작성.
> `[Step 4/8] agy 쿨다운 중 (until=<시각>). 방식 B로 전환 — Claude Write 도구로 직접 작성합니다.`

#### 방식 B — 직접 작성 (소규모·단순 작업, 세밀한 제어가 필요할 때)

**현재 Claude 세션 (마스터)** 이 `Write` 도구로 직접 작성한다.

**다른 에이전트 위임 금지** (BLOCKING):
- ❌ `code-writer` 호출 금지 — 분산 워커가 task 받아 본문 채울 때 쓰는 도구. 마스터가 호출하면 의사코드 단계를 건너뛰고 본문까지 한 번에 써버려 분산이 무의미해짐
- ❌ `source-analyzer`, `project-analyzer` 등 분석 에이전트 호출 금지 — 분석은 Step 1-2 에서 끝났음. Step 4 는 작성 단계
- ✅ 허용: `Read`, `Write`, `Glob`, `Grep`, `mcp__context-search__*` 같은 직접 도구만

**역할 분리 원칙**:
- **마스터 (현재 세션)** = 클래스 설계 + 시그니처 결정 + `[PSEUDO]` 영문 의사코드 박기
- **워커 (분산 PC)** = task 받아 의사코드 → 본문 변환 (code-writer 사용)

본 단계에서 자동으로 sub-agent 호출 충동이 들면 **즉시 중단** — 사용자에게 "스킬 정책상 마스터가 직접 작성합니다" 안내 후 Write 로 진행.

도메인에 맞는 repo 의 적절한 위치에 파일 작성. 위치는 Step 1 에서 확인한 경로 또는 사용자 표준 경로 사용.

**모든 의사코드 영문 작성** — 워커 LLM 토큰 효율 + 가독성. 한국어 의사코드 금지.

**본문은 비워둠** — `{}` (C++), `Super::` 호출만, `pass` / `raise NotImplementedError` (Python). 마스터가 본문을 채우면 워커 분산이 무의미.

#### 의사코드 태그 (도메인 무관 코어)

| 태그 | 용도 | 위치 | 워커 처리 |
|------|------|------|----------|
| `[PSEUDO]` | 함수/메서드 본문 의사코드 (단일 태스크) | 함수 선언 위 | **제거** 후 본문 구현 |
| `[PSEUDO:N]` | 뎁스 N 에서 구현할 의사코드 (N=1,2,3…) | 함수 선언 위 | **제거** 후 본문 구현 (해당 뎁스 워커만) |
| `[IMPL]` | 구현 힌트 (특정 패턴 사용 지시) | 함수 선언 또는 본문 내 | **제거** 후 지시 반영 |
| `[DOC]` | 영구 문서 주석 (동작 설명·API 명세) | 함수/멤버 선언 위 | **보존** — 절대 제거 금지 |
| `[STATE]` | 상태 멤버 + 초기값 의도 | 멤버 선언 위 | **보존** |

#### 뎁스 기반 분할 (선택 — 함수 수가 많거나 복잡도 차이가 큰 클래스)

`[PSEUDO:N]` 을 쓰면 파일 1개가 N단계 순차 태스크로 등재됨. 뎁스 N 태스크는 뎁스 N-1 완료·검증 후에만 시작.

| 뎁스 | 대상 함수 유형 예시 |
|------|-----------------|
| `[PSEUDO:1]` | 초기화·생성자·BeginPlay·단순 헬퍼 — 다른 함수에 의존 없음 |
| `[PSEUDO:2]` | 핵심 기능 함수 — 뎁스 1 결과를 전제로 구현 |
| `[PSEUDO:3]` | 복잡한 상호작용·외부 시스템 연동 — 뎁스 2 완료 후 구현 |

> 뎁스 없이 `[PSEUDO]` 만 쓰면 파일 전체가 하나의 태스크 (기존 방식 유지).
> 함수 총 수가 20개 미만이거나 복잡도 차이가 없으면 분할하지 말 것 — 오버헤드만 늘어남.

> **getter/setter 주석 금지**: 단순 반환/대입 함수(`GetX()`, `SetX()`)에는 `[DOC]`·`[PSEUDO]` 어떤 주석도 달지 말 것.
> 시그니처 자체가 의도를 표현하므로 주석이 오히려 워커 노이즈가 됨.
>
> **단, 다음 경우는 `[DOC]` 필수**:
> - 서버/클라이언트 권한이 얽힌 함수
> - Replication 부수효과가 있는 함수
> - 비명백한 side-effect 가 있는 public API

#### UE5 특화 태그 (UE 도메인일 때만)

| 태그 | 용도 | 워커 처리 |
|------|------|----------|
| `[BIND]` | UMG `BindWidget` 멤버 (UMG 위젯에서만) | **보존** |
| `[REPLICATED]` | `UPROPERTY(Replicated)` 네트워크 동기화 멤버 | **보존** |

#### 도메인별 .h/.cpp 또는 .py 형식

**UE C++ (.h)**:
- `#pragma once`
- forward declaration
- `<Name>.generated.h` include
- `UCLASS()` + 상속 + `GENERATED_BODY()`
- `UPROPERTY()` 메타 플래그 (필요시 `[BIND]` / `[REPLICATED]` 주석 동반)
- `UFUNCTION()` 메타 플래그
- 함수 선언 위 `[PSEUDO]` 영문 의사코드
- 델리게이트 선언

**UE C++ (.cpp)**:
- `#include "<Name>.h"`
- 본문은 모두 스텁 (`{}` 또는 `Super::` 호출만)

**Python (.py)**:
- 모듈 docstring (1-2줄)
- import 문 (필요한 것만)
- `[STATE]` 모듈/클래스 변수 + 타입 힌트 + 초기값
- 함수/메서드 시그니처 (타입 힌트 포함)
- 함수 위 `[PSEUDO]` 영문 의사코드
- 본문은 `raise NotImplementedError` 또는 `pass`

**일반 C++ (.h)**:
- `#pragma once`
- 클래스 선언 + 상속
- 함수 선언 + `[PSEUDO]` 의사코드

**일반 C++ (.cpp)**:
- `#include "<Name>.h"`
- 본문은 빈 스텁 또는 `throw std::logic_error("not implemented")`

작성 예시는 `docs/pseudocode_format.md` (있으면) 또는 본 스킬의 도메인 가이드 참조.

### [Step 5/8] 사전 검증 (선택)

진입 알림: `[Step 5/8] 의존성 분석 시작합니다.`

등재 전 의존성·계층을 미리 확인하려면:

```
mcp__master-orchestrator__analyze_skeletons(skeleton_dir="<absolute_path>")
```

응답의 `hierarchy` 가 의도한 leaf→manager 순서와 일치하는지 확인. 어긋나면 #include / 부모 클래스 누락 점검.

결과 1줄 보고: `[Step 5/8] hierarchy: L0=N L1=M L2=K ... — Plan 과 일치/불일치`
완료 알림: `[Step 5/8 완료] → Step 6 빌드 사전 검증.`

### [Step 6/8] 빌드 사전 검증 — working tree 가 컴파일 통과하는가 (BLOCKING)

진입 알림: `[Step 6/8] 빌드 사전 검증 시작 (5분 timeout). 스켈레톤은 아직 commit 전.`

**소요 시간 사전 안내** — Build.bat 가 N분 걸릴 수 있으니 사용자에게 미리 알림.

이 단계는 **register_skeletons 가 commit + push 하기 전** working tree 상태에서 빌드 검증한다. Step 4 에서 Write 한 스켈레톤 + 사용자의 .uproject/.Build.cs 가 컴파일 통과해야만 Step 7 (등재) 진입.

> **핵심 원칙**: register_skeletons (commit + push) 가 한 번 호출되면 그 시점의 working tree 가 origin 에 박혀 되돌리기 비싸다. broken 스켈레톤·잘못된 클래스명·.uproject 플러그인 누락 등은 working tree 단계에서 잡고 가야 한다. 이 단계가 그 책임을 진다.

```
mcp__master-orchestrator__build_project(
    project_root="<repo path>",
    config="Development",          # Development | DebugGame | Shipping
    engine_root="<Step 0-4 에서 결정한 엔진 root>"  # config.json 에 있으면 비워도 됨
)
```

엔진 경로 우선순위 (Step 0-4 와 동일):
1. `engine_root` 인자
2. `<project_root>/config.json` 의 `ue_engine_root`
3. `.uproject` `EngineAssociation` 자동탐지 (Launcher 설치판만)
4. `HKCU\Epic Games\Unreal Engine\Builds` GUID 매핑 (소스 빌드 등록 케이스)

내부 동작:
- `<engine>/Engine/Build/BatchFiles/Build.bat <Project>Editor Win64 <config> -project="<.uproject 절대경로>" -waitmutex -NoHotReload`
- working tree 의 .h/.cpp/.uproject/.Build.cs 를 그대로 컴파일 — git commit 여부 무관
- stdout/stderr 캡처해서 결과 반환

응답: `{ok, exit_code, log_tail, duration_seconds, engine_root, engine_resolved_via, target, config}`

**결과 1줄 즉시 보고**:
- 통과: `[Step 6/8] 결과: ok=true, duration=Xs, target=ModularStageEditor, engine_via=launcher_manifest`
- 실패: `[Step 6/8] 결과: ok=false, exit=N, duration=Xs, log_tail 마지막 5줄`

**빌드 실패 시 흐름 (BLOCKING)** — 마스터의 책임 절차:
1. log_tail / exit_code 분석. 보통 forward decl 누락·include 빠짐·UPROPERTY 메타 오류·잘못된 클래스명·.uproject 플러그인 누락·.Build.cs 의존 누락.
2. broken 파일을 `Edit` 도구로 정정. 대상은 두 종류:
   - 스켈레톤 (.h/.cpp) — Step 4 에서 마스터가 직접 작성한 파일들
   - 프로젝트 파일 (.uproject / *.Build.cs / *.Target.cs) — 사용자 repo 의 기존 파일이지만 이번 작업에 필요한 모듈/플러그인 추가 시
3. **git commit 하지 말 것** — Step 6 재시도까지 working tree 만 수정. commit 은 Step 7 의 register_skeletons 가 통째로 처리.
4. build_project 재호출 → 통과 시 Step 7 진입.
5. **5회 연속 실패 시** 사용자에게 보고 + 분산 작업 abort 권장. 시그니처가 근본적으로 잘못됐을 가능성 — 플랜 재검토 필요.

> **수정한 프로젝트 파일은 Step 7 의 `skeleton_files` 인자에 추가** — 마스터가 .uproject 또는 .Build.cs 를 수정했으면 register_skeletons 호출 시 `skeleton_files` 에 그 경로들도 함께 명시. 그래야 같은 [skeleton] commit 에 묶여 origin 에 박힘. 누락 시 fix 가 commit 안 되어 워커들의 base_commit 이 broken 상태로 남는 사고 발생.

완료 알림: `[Step 6/8 완료] → Step 7 큐 등재.`

### [Step 7/8] task_queue 등재 (브랜치 + commit + UE regen + work/tasks)

진입 알림: `[Step 7/8] work + N tasks 큐 등재 시작.`

**전제**: Step 6 빌드 검증 통과 — 이 시점의 working tree 는 buildable 보장됨. register_skeletons 가 이걸 그대로 commit 하면 워커들의 base_commit 도 buildable.

**중복 검사 결과 반영**: Step 1.4 에서 결정된 `confirm_duplicate` 흐름 변수를 그대로 전달. 사용자가 "예" 했으면 `True`, 중복 없었으면 `False`. 만약 빠뜨리면 task_queue 가 거절 (`reason:"duplicate"`) — 그 경우 사용자에게 알림 후 confirm 받아 재호출.

```
mcp__master-orchestrator__register_skeletons(
    skeleton_dir="<absolute_path>",
    title="<work title — Step 1 의 기능 설명에서 도출, 영문 권장>",
    queue_url="http://localhost:8101",
    repo="<game_repo_path>",                  # 비우면 skeleton_dir 부터 .git 자동 탐색
    target_repo="<repo path>",                 # work 메타에 기록할 target (보통 repo 와 동일)
    reference_repo="<참조 프로젝트 경로>",      # 선택, Step 1 에서 확인했을 때만
    source_dir="<원천 소스 폴더 절대경로>",    # 포팅 작업 시만 — 없으면 생략 (워커 포팅 참조용)
    ue_regen=True,                             # UE 도메인일 때만 True (IDE solution 재생성)
    branch_isolation=<Step 3 결정>,            # True/False
    target_branch="<Step 3.5 prepare_work_branch 응답의 branch 값>",  # 같은 값을 그대로 전달
    engine_root="<Step 0-4 에서 결정한 엔진 root>",  # config.json 에 있으면 비워도 됨
    plan_md="<Step 2 에서 사용자에게 보여준 Plan markdown 전체 본문>",
    skeleton_files=[                           # ← Step 2 plan 의 파일 목록 + Step 6 fix 시 수정한 .uproject/.Build.cs 추가
        "Source/ModularStage/UI/Base/UIWidgetBase.h",
        "Source/ModularStage/UI/Base/UIViewBase.h",
        "ModularStage.uproject",                # ← Step 6 fix 에서 수정했으면 명시
        "Source/ModularStage/ModularStage.Build.cs",  # ← 같음
        ...                                    # plan 표의 모든 .h 경로 (cpp 자동 페어링)
    ],
    forbidden_patterns=[...],
    convention_refs=[...],
    confirm_duplicate=<Step 1.4 결정>,         # 사용자가 중복 알고도 진행 confirm 했을 때만 True
    task_template="<Step 1.5b 매칭 템플릿명 또는 생략>"  # ζ — 매칭됐으면 그 이름. 모든 task_data 에 링크돼 워커/code-writer 가 get_task_template 로 grounding
)
```

**거절 응답 처리** — `{ok:False, reason:"duplicate", duplicates:[...]}` 가 돌아오면:
- 메인 세션이 사용자에게 동일 형식의 알림 후 진행 의사 재확인
- "예" → `confirm_duplicate=True` 로 동일 호출 재시도 (commit 은 이미 origin 에 박힘 — work 등록만 다시)
- "아니오" → Step 7 중단. 이미 push 된 feature 브랜치는 cleanup_stale_branches 또는 사용자 수동 처리

**`skeleton_files` 명시 의무 (BLOCKING)**: Step 2 plan 에서 결정된 파일 목록 + Step 6 빌드 fix 에서 수정한 프로젝트 파일을 모두 그대로 전달. 디렉토리 스캔 fallback 은 leftover/기존 파일까지 잡아오므로 사용 금지. plan 과 1:1 일치 보장 + 사용자 WIP 보호 + Step 6 fix 누락 차단.

내부 동작:
- (`branch_isolation=True` 일 때) feature 브랜치 idempotent 보장 (Step 3.5 가 이미 만들어 둠)
- 스켈레톤 분석 → 계층 산정 (.h/.hpp/.py 모두 인식)
- UE 리제너레이트 (`ue_regen=True` 일 때만) — IDE 용 VS solution 갱신. Build.bat 검증은 Step 6 에서 이미 끝남
- git add + commit ("[skeleton] <title>: N files for distributed implementation")
  - 이 commit 은 Step 6 빌드 통과를 보장된 working tree → buildable base_commit
- **`git push origin feature/X` — skeleton commit 을 워커가 fetch 가능하게 동기화**
- POST /api/v1/works → work_id 획득
- **`plan_md` 가 있으면 `<work_id>/_plan.md` 작성** (frontmatter 자동 추가, 리뷰 시 승인된 플랜 추적용)
- 각 클래스/모듈을 task_queue 에 등재 (의존성·계층 순서 보존, work_id 첨부)

응답: `{ok, work_id, title, target_branch, base_commit, registered_count, tasks: [...]}`

**결과 1줄 즉시 보고**: `[Step 7/8] 결과: work_id=20260502_..., registered=N/N, branch=feature/X` (성공 시)
실패 시: `[Step 7/8] 실패: <error>. 로그: .claude/logs/master_orchestrator_<오늘>.log`

**`plan_md` 포함 의무**: Step 2 에서 사용자에게 보여준 플랜 markdown 본문 (테이블·계층 의존성·메타·함수 미리보기 전체) 을 그대로 전달. 리더 그룹 주간 리뷰 시 "뭘 승인했는지 vs 뭐가 만들어졌는지" 비교 자료로 사용됨.

완료 알림: `[Step 7/8 완료] → Step 8 보고.`

### [Step 8/8] 사용자에게 보고

```
✅ 분산 작업 등재 완료

**work_id**: 20260502_1530_ui_system
**브랜치**: feature/ui_system_20260502  (격리됨, main 보호)
**base_commit**: a1b2c3d
**등재된 task**: 8개
**UE 빌드**: ✅ 통과 (45초)  또는  ⚠️ 실패 — 스켈레톤 점검 필요

| # | task_id | 클래스 | 계층 | 의존 |
|---|---------|--------|------|------|
| 1 | abc12345 | UMS_InventorySlot | L0 | - |
| 2 | def67890 | UMS_ItemTooltip | L0 | - |
| 3 | 9876fedc | UMS_InventoryHUD | L1 | abc12345, def67890 |
| ... |

**워커 작동 시간**: 클라이언트 PC 들이 22:00-08:00 동안 polling.
**예상 처리 시간**: leaf 병렬 → manager 순차 = 약 30분~1시간 (워커 6대 가용 시).
**리뷰 게이트**: 모든 task 완료되면 `_request.md.merge_status: ready_for_review` 자동 전환.
다음주 리더 그룹 리뷰 후 `master_orchestrator --review <work_id> --approve` 로 main 머지.
```

작업 기록은 `history/YYYY-MM-DD_HHMM_distribute_<work_id>.md` 에 자동 저장. **frontmatter 8필드 의무** (Phase α′ ontology 시드):

```yaml
---
date: YYYY-MM-DD HH:MM
work_id: "<Step 7 에서 발급된 work_id>"          # /distribute 의 핵심 cross-ref 키
session_id: null
decision_type: architecture                       # /distribute 는 거의 항상 신규 시스템 구조 변경
affected_classes: [<스켈레톤에 포함된 클래스명 전체>]
affected_domains: [<자동 승급 도메인 매칭 시>]
supersedes: null
alternatives_considered: []                       # Step 0 에서 사용자에게 a/b/c 옵션 제시 후 선택된 내역
tags: [distribute, <시스템_키워드>]
user_quote: |
  Step 1 에서 캡처한 사용자 요구사항 원문
---
```

본문 내용:
- 사용자 요구사항 (Step 1)
- 승인된 플랜 + 브랜치 결정 (Step 2/3)
- 빌드 결과 (Step 6)
- 등재된 task 목록 (Step 7 결과)
- base_commit + 게임 repo 경로

## 핵심 주의 사항

1. **사용자 승인 + 브랜치 결정 전 파일 작성·등재 금지** — Step 3 의 BLOCKING 게이트
2. **시그니처는 결정해야 함** — 함수 시그니처·UPROPERTY 메타·델리게이트 시그니처는 마스터가 모두 박을 것. 워커가 결정하지 않게 (의사코드 contract)
3. **forbidden_patterns 명시** — 워커 LLM 이 자주 쓰는 안티패턴(`GEngine->`, `printf` 등) 은 task 메타에 박아 워커 LLM 이 회피
4. **계층 검증** — `analyze_skeletons` 결과의 hierarchy 가 사용자 의도와 일치하는지 확인. 의도와 다르면 #include 또는 부모 클래스 누락 가능성
5. **base_commit 일관성** — 워커가 checkout 할 베이스. 스켈레톤 commit 직후 등재해야 워커가 정확한 의사코드를 받음
6. **UE 빌드 사전 검증 = commit 차단** — Step 6 빌드 실패 시 register_skeletons 는 호출 전 단계라 origin 에 아직 아무 것도 박히지 않은 상태. 마스터가 working tree 에서 fix 후 build 재시도. 통과 후에만 Step 7 등재. 즉 broken 스켈레톤이 워커에게 도달할 가능성 0. (구버전: commit 후 빌드 검증 → fix 가 working tree 에만 남는 race 존재했음)
7. **단일 클래스 작업 거절** — 스켈레톤 1~2개는 분산 가치 없음. Step 0 에서 거를 것 (3개 미만이면 직접 작성 권장)
8. **엔진 경로 — 명시 인자 / config.json 우선, 자동탐지는 폴백** — 소스 빌드 엔진은 레지스트리·Program Files 어디에도 없음. `<project_root>/config.json` 의 `ue_engine_root` 가 PC 별 1회 설정의 표준 위치. Launcher 설치판은 자동탐지가 동작하지만 보조 폴백으로만 다루고, 결정 못하면 사용자에게 묻기 → config.json 갱신. 빌드 산출물(exe·스킬)에는 어떤 절대경로도 박지 않음.

## 비용·성능 안내

- 스킬 1회 실행: 사용자 대화 N턴 + 스켈레톤 작성 (LLM 토큰 ~10-30k) + UE regen (~30s) + 큐 등재 (~수 ms × N)
- 워커 측 비용: task 1건당 LLM 호출 1-3회 (재시도 포함), 총 ~5-30k 토큰

## 종료

큐 등재 완료 후 추가 작업 묻지 않음 (대화 자연 종료).
다음 작업이 필요하면 새 `/distribute` 호출로 받음.
