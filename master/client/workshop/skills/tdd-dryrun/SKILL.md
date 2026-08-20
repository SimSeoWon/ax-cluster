---
name: tdd-dryrun
description: 태스크 템플릿의 TDD 계약(3a 루브릭 + 3c 실제 테스트)을 분산 파이프라인 밖에서 검증·튜닝한다. 서버에서 Claude 에이전트가 contracts 로 테스트를 만들고, 준수/위반 샘플을 구현해, red-green 이 닫히는지 단계별 로그로 확인한다. Git 브랜치·Redmine·task_queue 에 흔적을 안 남기는 스테이징 — 결과를 보고 실제 분산 TDD 게이트·템플릿을 보정. 자연어 "TDD 드라이런", "<TaskType> 계약 테스트 검증", "tdd 드라이런 돌려줘", "TDD 1차 테스트" 에 발동. 분산 작업 검수(/review-work)나 템플릿 등록(/manage-task)과 별개.
---

# TDD Dry-run — 서버측 계약 테스트 검증 하니스

## 본질 (WHY)
분산작업에 TDD 를 바로 적용하면 Git 브랜치·Redmine 이슈·task_queue 등재로 여러 곳에 흔적이
남는다. 본 스킬은 **분산 파이프라인 밖에서 3a+3c 전 과정을 Claude 에이전트로 단독 실행**하고
**단계별 세부 로그**를 남겨, 메커니즘이 제대로 도는지(위반은 잡히고 준수는 통과 — red-green 이
닫히는지) 검증한다. 사용자가 로그·problem 을 보고 실제 분산 TDD 게이트·템플릿 contracts/test_spec
을 보정하는 스테이징. **흔적 0** — 임시 worktree, push·Redmine·queue 미접촉.

## 환경 확인 (BLOCKING)
1. **로컬 `master_orchestrator.exe` 존재** (`.claude/mcp/master_orchestrator.exe`) + **게임 repo**
   (UE 프로젝트 git 루트). 없으면 즉시 종료:
   > "이 PC 에 master_orchestrator.exe / 게임 repo 가 없습니다. /tdd-dryrun 은 서버(리더/개발) PC 에서 동작합니다."
2. **claude CLI** (PATH) — 테스트·샘플 생성 에이전트가 `claude -p` 로 돈다. 없으면 생성 단계가
   fail-open(하니스는 완주하되 red-green 미검증)되니 사전 안내.
3. **with_ue_test=True(기본, 3c 포함) 시 UE 엔진 해결 가능** — `config.json` 의 `ue_engine_root`
   또는 `engine_root` 인자. 첫 시도엔 **`with_ue_test=False`(3a 루브릭만, UE 빌드 없음)** 로
   가볍게 돌려보길 권장.
4. context_search 응답 (`get_task_template` — contracts 조달). 실패 시 종료 + 서버 상태 안내.

## 입력 파싱
`/tdd-dryrun <TaskType> [자유 서술 미션...]` — 첫 토큰이 **TaskType**(등록된 템플릿 이름), 그 뒤
자유 서술이 있으면 **그 미션을 `spec` 으로** 넘긴다. 예:
- `/tdd-dryrun MissionTaskAddition` → 합성 샘플로 일반 검증.
- `/tdd-dryrun MissionTaskAddition 신규 미션: 적 5마리 처치 시 성공, 기존 Wait 처럼 Stateful` →
  `task_type=MissionTaskAddition`, `spec="신규 미션: 적 5마리 처치 시 성공, 기존 Wait 처럼 Stateful"`.

첫 토큰이 TaskType 인지 모호하면(등록 목록에 없으면) `list_task_templates` 로 확인 후 사용자에게
어느 템플릿인지 되묻는다. 서술만 있고 TaskType 가 불명확하면 추측 금지.

## 호출
사용자에게 (a) 대상 TaskType (b) 게임 repo 경로 (c) UE 테스트 포함 여부 (d) 서술 미션 유무를
확인한 뒤:

```
mcp__master-orchestrator__tdd_dryrun(
    task_type="<TaskType>",
    repo="<게임 repo 절대경로>",
    with_ue_test=<true=3a+3c 전체 / false=3a 루브릭만 경량>,
    spec="<선택: 사용자 서술 미션 — 있으면 합성 대신 이 미션으로 구현·검증>",
    engine_root="<선택: config 미설정 시 UE 엔진 경로>"
)
```

- **spec 효과**: 주면 준수 시나리오=서술 미션 충실 구현(green 기대) / 위반 시나리오=같은 미션을
  계약 1개 위반(red 기대). 비우면 템플릿 일반 합성 샘플. **테스트(Step A)는 spec 무관**하게 템플릿
  contracts 기반 — 특정 미션이 그 계약을 만족하는지 검사하는 구조.
- **대상 전제**: 템플릿에 contracts(pre/post/acceptance)가 있어야 함. 없으면 하니스가 중단하며
  "/manage-task 로 먼저 등록" 안내 — 그 경우 먼저 contracts 를 채운다.
- `tdd` 플래그는 드라이런에 **불필요** — 드라이런은 tdd:true 로 켤지 **판단하기 위한** 검증 단계.

## 결과 해석
응답 `verdict`:
- `red_green_closed=true` — 위반 샘플이 잡히고(✗) 준수 샘플이 통과(✓). 계약·테스트가 유효 →
  템플릿에 `tdd=true` + `test_spec.filter` 등록을 고려(`/manage-task edit`).
- `red_green_closed=false` + `problems[]` — 예: "위반을 못 잡음(계약 느슨)" / "준수가 실패(과엄격·
  거짓양성)". 이걸 보고 contracts 문구나 테스트를 보정.
- 단계별 세부 로그 = `log_dir`(`.claude/reviews/_tdd_dryrun/<TaskType>_<ts>/` — summary.jsonl +
  A_test_gen/B_impl_*/C_rubric_*/D_build|test_* 로그). master_orchestrator 로그의 `[tdd-dryrun]`
  카나리도 함께 본다.
- **생성 테스트 보존** = `log_dir/generated/` 에 Claude 가 만든 테스트 .cpp 가 복사됨(worktree 는
  teardown 시 삭제되지만 이건 남음). 결과가 쓸만하면 이걸 실제 UE 프로젝트에 채택 + `/manage-task
  edit` 으로 `test_spec.filter` 등록 → 실제 분산 게이트에서 사용.

## 절대 하지 말 것
- 드라이런 결과를 실제 분산 작업 머지 판단에 직접 쓰기 — 드라이런은 **검증·튜닝 스테이징**이지
  머지 게이트가 아니다(머지 게이트는 verify-merge 의 통합 빌드 + 3a/3c).
- 결과를 보고 사용자 확인 없이 템플릿 `tdd=true` 자동 설정 — 켜는 건 사용자 판단(/manage-task).
- 로컬에 게임 repo·UE 엔진 없는 PC 에서 with_ue_test=True 로 강행 — 3c 빌드가 무의미하게 실패.
