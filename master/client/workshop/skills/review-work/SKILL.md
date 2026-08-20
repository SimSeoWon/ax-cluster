---
name: review-work
description: 분산 작업의 ready_for_review/build_failed work 를 리더가 검증한다. work_id 또는 Redmine 이슈 번호를 받아 시뮬레이션 머지 + 빌드 + diff 요약을 보여주고, 리더 의사결정(승인/반려/추가 검토)을 받아 finalize 또는 reject 를 호출한다. main 안전 보장 — 시뮬레이션 머지는 임시 브랜치에서만 수행. 트리거: "#N 리뷰", "N번 일감 리뷰/검토", "work N 리뷰", "분산 작업 리뷰", "머지 검토", "리뷰/검수 요청을 받았어" 처럼 분산 워커가 올린 검수 요청을 리더가 받았을 때. 일반 코드/PR 리뷰(code-validator) 와 구분할 것 — "#N" 또는 "일감" 단어가 보이면 거의 항상 이 스킬이며, "리뷰" 키워드만 보고 code-validator 로 빠지지 말 것.
---

# Review Work — 리더 검증·머지 대화형 스킬

## 호출 형태

```
/review-work <work_id>            # work_id 직접 지정
/review-work #<redmine_issue_id>  # Redmine 이슈 번호 (구현 — 메타에서 work 매칭)
/review-work                      # 인자 없음 → ready_for_review·build_failed 목록 보여주고 선택
```

## 사용 시나리오

CTO/리더 그룹이 분산 작업 완료 알림 (Redmine 이슈) 을 받아 머지 결정을 내릴 때.

## 흐름

### [Step 0/5] 환경 확인 (BLOCKING)

분산 환경에서는 `task_queue.exe` 데몬이 **인프라 PC 한 대에만** 있고, 리더/개발 PC 들은 `master_orchestrator.exe` 와 게임 repo 만 가지고 원격 task_queue 를 호출하는 구조다. 따라서 로컬 `task_queue.exe` 존재 여부는 체크하지 않으며, health 도 `config.json` 의 `task_queue_url` 로 원격 확인한다.

**체크 순서**:

1. **로컬 `master_orchestrator.exe` 존재** — `.claude/mcp/master_orchestrator.exe` 가 있어야 시뮬레이션 머지·빌드 가능. 없으면 즉시 종료:
   > "이 PC 에 master_orchestrator.exe 가 없습니다. /review-work 는 게임 repo + master_orchestrator 가 설치된 PC (리더/개발 PC) 에서 동작합니다."

2. **게임 repo (git 작업 디렉토리)** — 현재 작업 디렉토리에서 `git rev-parse --is-inside-work-tree` 성공해야 함. 실패면 종료:
   > "현재 디렉토리가 git repo 가 아닙니다. 게임 repo 루트에서 실행하세요."

3. **`task_queue_url` resolve** — `config.json` 에서 `task_queue_url` 을 읽음. 누락이거나 `localhost:8101` 인데 8101 응답이 없으면 종료:
   > "config.json 의 task_queue_url 이 비어 있습니다. 인프라 PC 의 task_queue 주소를 설정해야 합니다."

4. **원격 health check** — `GET <task_queue_url>/api/v1/health` (curl 또는 PowerShell `Invoke-WebRequest`). 응답 실패 시 종료:
   > "인프라 PC 의 task_queue 데몬 (<url>) 이 응답하지 않습니다. 인프라 PC 에서 `task_queue.exe` 가 떠 있는지 확인 (예: 8101 포트) 후 다시 시도하세요."

이 셋만 통과하면 진입 OK. `server_mode: false` 인 클라이언트 PC 라도 원격 task_queue 가 응답하면 정상 케이스다 — server_mode 플래그는 `/review-work` 진입 조건과 무관 (Git 감시·RAG 서버 역할에만 영향).

**BLOCKING 의 엄격성** — 네 단계 중 어느 하나라도 실패하면 **즉시 종료**. 다음 행동은 **금지**:
- 원격 health 실패 후 `localhost:8101` 로 자율 재시도
- task_queue 미응답 상태에서 `review_work` MCP 를 "혹시" 호출
- Redmine 직접 조회 + git branch 직접 검사로 우회 진단 진행
- 다른 master_orch 도구 (`integration_build` 등) 로 우회

종료 메시지만 사용자에게 보여주고 빠진다. `/review-work` 는 task_queue 응답 없이는 단 한 발자국도 못 가는 흐름 — 우회는 시간 낭비 + 잘못된 fallback (예: localhost) 위험만 만든다.

### [Step 1/5] 검토 대상 결정

**queue_url 결정** (BLOCKING — 모든 작업 전에): repo/config.json 의 `task_queue_url` 을 읽어 변수에 저장. localhost 또는 누락이면 사용자에게 즉시 보고하고 종료. 이후 모든 HTTP 호출은 이 URL 을 사용.

- 인자가 work_id 패턴 (`YYYYMMDD_HHMM_<slug>`) 이면 그대로 사용
- 인자가 `#<숫자>` 이면 Redmine 이슈 번호 — `GET <queue_url>/api/v1/works` 로 전체 work 조회 후 `redmine_issue_id` 매칭
- 인자가 없으면 — `GET <queue_url>/api/v1/works` 로 `merge_status in (ready_for_review, build_failed)` 인 work 목록을 사용자에게 표시하고 선택받기:

  ```
  검토 대상 work 가 N개 있습니다:

  1. 20260510_1855_ui_event_subsystem_commonui_layer_system
     상태: ready_for_review | Redmine: #9 | 통합빌드: ✅ 통과
     제목: UI Event Subsystem CommonUI Layer System

  2. 20260511_0930_inventory_widget_family
     상태: build_failed | Redmine: #12 | 통합빌드: ❌ 실패
     제목: Inventory Widget Family

  어떤 work 를 검토하시겠습니까? (번호 또는 work_id)
  ```

### [Step 2/5] 시뮬레이션 머지 + 빌드

```
mcp__master-orchestrator__review_work(
    work_id="<선택된 work_id>",
    repo="<game repo 절대경로>",
    queue_url="",                   # 비우면 repo/config.json 의 task_queue_url 자동 사용
    engine_root="",                 # 비우면 config.json 의 ue_engine_root 자동
    skip_build=False                # 시간 급하면 True (시뮬레이션 머지만)
)
```

> **queue_url 처리**: 비어있거나 `http://localhost...` 면 repo/config.json 의 `task_queue_url` 을 자동 읽음 (분산 환경 — 인프라 PC IP). 클라-워커 PC 들의 config.json 에는 인프라 PC IP 가 박혀있으므로 별도 명시 불필요. 다른 task_queue 로 강제하고 싶을 때만 명시.

> **호출 실패 처리** — `review_work` MCP 가 task_queue 미응답으로 실패하면 **즉시 종료**. **금지 행동**:
> - `queue_url="http://localhost:8101"` 같이 인자 바꿔서 재시도 (config 의 IP 가 정답이고 localhost 는 분산 환경에서 잘못된 fallback)
> - Redmine 직접 조회 + git branch 검사로 우회 진단 진행
> - 다른 master_orch 도구 (`integration_build` 등) 로 우회
>
> 종료 메시지: "task_queue 데몬 미응답으로 review_work 호출 실패. 인프라 PC 의 task_queue.exe 상태 확인 후 다시 시도하세요." Step 0/5 health check 와 같은 정신 — task_queue 없이는 어떤 단계도 의미 없음.

응답 구조:
```
{
  ok, work_id, title, target_branch, redmine_issue_id,
  build_passed, build_skipped,
  diff_summary,           # git diff main..review --stat 출력
  recent_commits,         # 최근 20개 commit oneline
  files_changed,          # 변경 파일 목록 (최대 100개)
  files_changed_count,
  exit_code, duration_seconds,
  conflicts?,             # main 과 충돌 시 True
  build_log_tail?,        # 빌드 실패 시 마지막 로그
  status_flipped?,        # build_failed 자동 flip 여부
}
```

> 도구가 자동으로 임시 브랜치 review/<work_id> 를 만들어 main + origin/<feature> 머지 후 빌드. 종료 시 임시 브랜치 삭제 + 원래 브랜치 복귀. **main 은 절대 안 건드림**.

### [Step 3/5] 결과 보고

응답을 사람이 읽기 좋게 정리해서 사용자에게 표시:

```
✅/❌ 검증 결과 — <title> (work_id: <work_id>)

머지 시뮬레이션: ✅ main + origin/<feature_branch> 충돌 없음
                  ❌ 충돌 — main 과 머지 불가 (수동 해결 필요)

통합 빌드:        ✅ 통과 (exit=0, 32.4s)
                  ❌ 실패 (exit=6, 7.5s)

변경 요약:
  - 파일 18개 변경
  - +728 / -0 라인
  - 최근 commit:
      a1b2c3d [verify-merge] xxxxxx by DESKTOP-...
      e4f5g6h [verify-merge] yyyyyy by DESKTOP-...
      ...

[ 빌드 실패 시 ]
빌드 로그 마지막:
  <log_tail 마지막 30줄>

연결된 Redmine 이슈: #<id>
```

### [Step 4/5] 의사결정 받기 (BLOCKING)

**빌드 통과 + 충돌 없음** — `AskUserQuestion` 으로 다음 옵션 제시:
- **승인 (finalize)**: main 으로 머지 + push + 원격 feature 삭제 + Redmine 닫기
- **반려 (reject)**: 코멘트 남기고 종료, feature 브랜치는 보관 (재작업 가능)
- **추가 검토**: 흐름 종료 (사용자가 코드 더 보고 다시 호출)

**빌드 실패 또는 충돌** — `AskUserQuestion` 으로 다음 옵션 제시:
- **여기서 fix (Recommended)**: 리더가 review 자리에서 직접 패치 + 안티패턴 등록 + 재빌드 → finalize 진입
- **반려 (reject)**: 사유와 함께 종결, feature 브랜치 보관
- **종료**: 그대로 두고 빠지기 (다른 사람이 처리하거나 나중에 재시도)

**'여기서 fix'** 선택 시 **Step 4.5 in-place fix 흐름**으로 진입 (아래). 나머지는 Step 5 결정 실행.

### [Step 4.5/5] In-place Fix 흐름 (빌드 실패 시만)

리더가 review 시점에 메인은 이미 다음 작업 진행 중 — 워커에 재분산 보내면 너무 늦음. 그러니 리더가 그 자리에서 fix 하고 안티패턴으로 등록해서 다음 분산 작업이 같은 함정 안 밟도록 하는 흐름.

#### 4.5.1 빌드 에러 분류 + 원인 추정 + **즉시 fix 진행**

`build_log_tail` 에서 다음 패턴 분류:

**[자동 fix 카테고리]** — 원인 + 패치 범위가 명확. 보고 후 사용자 결정 묻지 말고 4.5.2 로 즉시 진행:
- UHT `Unable to find parent class type` / `Unrecognized type` → 부모 클래스 헤더의 모듈이 `*.Build.cs` 의 `PublicDependencyModuleNames`/`PrivateDependencyModuleNames` 에 없음. 추가로 `.uproject` 의 `Plugins` 섹션에 해당 플러그인이 enabled 인지도 확인.
- 링커 `unresolved external symbol` → 다른 모듈 함수 호출인데 의존 모듈 누락. 또는 `DLLEXPORT` 누락.
- `cannot access private member` → 워커가 verify 단계에서 못 잡은 접근 위반. 함수 시그니처 또는 friend 선언 필요.

**[사용자 진단 요청 카테고리]** — 의도 파악 필요. 사용자에게 보고하고 멈춤:
- 위 패턴에 안 잡히는 컴파일/링크 에러
- 순환 의존성, 모듈 구조 자체 결함처럼 work 범위 밖일 가능성 있는 항목
- 분산 작업과 무관한 기존 main 의 빌드 결함으로 의심되는 항목 (이 경우 work 의 build_failed 가 아닌 별도 이슈로 분리 권고)

**보고 + 진행 형태** (자동 fix 카테고리):
> "빌드 실패 원인: `UCommonActivatableWidget` 부모 클래스 못 찾음 → `ModularStage.Build.cs` 의 PublicDependencyModuleNames 에 'CommonUI', 'UMG' 누락. 지금 fix 적용 + push + 재빌드 진행합니다."

→ 이렇게 보고 후 곧바로 4.5.2 진입. **"이렇게 fix 할까요?" 같이 결정 묻기 금지** — 추정이 확실한 패치 범위(.Build.cs 모듈 추가 / .uproject 플러그인 enable / friend 추가 등) 는 진행하는 것이 기본. 단, 4.5.2 가 git push 까지 가는 흐름이라 그 직전 단계에서 작업 데몬 영향이 있으면 그때 한 번만 확인.

#### 4.5.2 fix 적용 — feature 브랜치에 직접 commit + push

**중요**: 임시 review 브랜치는 review_work 가 끝나며 삭제됐음. fix 는 **origin 의 feature 브랜치 위에** 올려야 finalize 가 그걸 머지함.

```
git fetch origin <target_branch>
git checkout <target_branch>           # feature/<...> 로 직접 체크아웃
git pull --ff-only origin <target_branch>
# 파일 편집 (.Build.cs, .uproject, 원본 코드 등)
git add <changed files>
git commit -m "[review fix] <원인 요약> (work=<work_id>)"
git push origin <target_branch>
```

이건 메인 세션이 `Edit` 도구로 직접 작성 + `master_orchestrator` MCP 의 `prepare_work_branch` / `git` 위임 도구는 안 거치고 **직접 bash git 호출**. **단**, 다른 work 의 분산 작업이 동시 진행 중이면 race 가능 — 메인 브랜치 작업과만 충돌 안 나면 OK.

> **주의**: `<target_branch>` 가 `feature/...` 형식인지 review_work 응답의 `target_branch` 필드로 확인. main/master 면 즉시 중단.

#### 4.5.3 안티패턴 엔트리 작성 — `_distribute_failures.md`

리더가 작성하거나 메인 세션이 초안 제시 후 사용자 확인:

```
{repo}/.claude/recipes/_distribute_failures.md
```

엔트리 포맷 (append):
```markdown

## <에러 한 줄 요약>
- **발견**: YYYY-MM-DD work `<work_id>`
- **증상**: <빌드/검증 에러 메시지 한 줄>
- **원인**: <왜 워커가 못 잡았는지 — 근본 원인>
- **회피**: <분석/스켈레톤 단계가 다음에 어떻게 해야 하는지 — 행동 규칙>
```

작성한 엔트리는 `AskUserQuestion` 으로 본문 확인받음 (사용자가 표현·범위 다듬을 수 있게). 승인 후 파일에 append + commit + push (같은 feature 브랜치):

```
git add .claude/recipes/_distribute_failures.md
git commit -m "[anti-pattern] <엔트리 제목> (work=<work_id>)"
git push origin <target_branch>
```

#### 4.5.4 통합 빌드 재실행 — `--auto-flip`

```
mcp__master-orchestrator__integration_build(
    work_id=<work_id>,
    repo=<repo>,
    queue_url="",
    auto_flip=True              # 통과 시 build_failed → ready_for_review 자동 PATCH
)
```

응답:
- `ok=True`, `build_passed=True`, `status_flipped=True` → 빌드 통과 + 상태 회복. **Step 4.5.5 finalize 진입**.
- `ok=True`, `build_passed=False` → 여전히 실패. 빌드 로그 보여주고 사용자에게 추가 fix 또는 종료 선택받기 (Step 4.5.1 로 루프).

#### 4.5.5 finalize 결정

빌드 통과 후 사용자에게 한 번 더 확인:
> "통합 빌드 통과. 이제 main 머지 진행할까요? (승인/연기)"

승인 → Step 5 의 finalize 호출 (안티패턴이 같이 머지되며 task_queue 가 자동 통지받음).
연기 → 그대로 두기. 나중에 사용자가 `/review-work <work_id>` 재호출로 다시 진입.

### [Step 5/5] 결정 실행

승인 → finalize:
```
mcp__master-orchestrator__finalize_work(
    work_id=<work_id>,
    repo=<repo>,
    queue_url="",                       # 비우면 config.json 자동
    reviewer="<리더 이름 — 사용자에게 받기>"
)
```
응답의 매트릭스 (merge_status, merged_branch, redmine_issue_id, anti_patterns_notified?) 를 사용자에게 보고. `anti_patterns_notified` 가 있으면 새 안티패턴 엔트리가 task_queue 에 통지된 것 — 다음 `/distribute` 분석/플랜/스켈레톤 단계가 그 함정을 회피.

반려 → reject:
1. 반려 사유를 사용자에게 받음 (BLOCKING — `AskUserQuestion`)
2. 호출:
```
mcp__master-orchestrator__reject_work(
    work_id=<work_id>,
    repo=<repo>,
    queue_url="",                       # 비우면 config.json 자동
    reviewer="<리더 이름>",
    reason="<사유 본문>"
)
```
응답 보고 — feature 브랜치는 보관됨, Redmine 이슈에 반려 코멘트.

## 안전장치

- **main 무변경**: review_work 는 시뮬레이션 머지만 — 실제 main 변경/push 는 finalize 만 수행
- **status flip 자동**: 빌드 실패 시 build_failed 로 자동 PATCH — finalize 가 거절됨 (이중 안전망)
- **임시 브랜치 자동 정리**: review/<work_id> 는 함수 종료 시 무조건 삭제
- **stash 보호**: server WIP 가 있으면 자동 stash → 종료 시 pop. pop 실패해도 stash 는 보존
- **in-place fix 의 push 대상**: feature 브랜치만 — main 직접 push 절대 금지
- **안티패턴 통지**: finalize 가 머지 commit 의 `_distribute_failures.md` 변경을 감지해 task_queue 에 자동 POST. 별도 호출 불필요

## 절대 하지 말 것

- 메인 세션이 직접 main 으로 git merge / push 호출 — review_work / finalize_work / reject_work MCP 만 사용 (단, Step 4.5 in-place fix 의 feature 브랜치 commit/push 는 예외 — 메인 미변경)
- 사용자 의사결정 없이 finalize 자동 호출 — '추가 검토' 가 default 안전 옵션
- skip_build=True 를 자동으로 켜기 — 사용자가 명시 요청한 경우만 (운영자 안전 위해 빌드는 default 수행)
- 사용자 확인 없이 `_distribute_failures.md` 엔트리 작성 — 표현·범위는 리더 판단 영역
