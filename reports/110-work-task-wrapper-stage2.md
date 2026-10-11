# #363 Work/Task 래퍼 2단계 인수와 병렬 처리 정책

## 인수 근거

사용자가 붙여넣은 Claude 대화와 Redmine #363, 실제 HEAD `0159337`을 대조했다.
1단계는 커밋됐고 작업 트리는 깨끗했다. Claude의 2단계 서브 에이전트는
429로 중단됐으며 그 구현은 트리에 남아 있지 않았다. 기존 인수인계서의
최상단 12:15 체크포인트는 최신 작업보다 오래됐다.

AXCluster 큐의 work 18건·조각 54개를 조회했으며 pending/needs_revision/
claimed/submitted 조각은 없었다. 워커 전역 지휘자 모드는 codex였다.
이는 큐 조회이며 원격 PC의 잔존 프로세스 검사와는 다르다.

## 최신 사용자 결정

처음 대화의 work 파견 보류 방식을 사용자가 수정했다.

> 태스크 래퍼에 저장만 해 상태를 그리고 워커에게 재할당할지만 체크하고,
> 골조 문제라 실패라면 그냥 다른 작업으로 전환해서 처리해.
> 그리고 더이상 할당할 작업이 없을때 골조 문제라면 분산작업 태스크 래퍼쪽에서
> 다시 작업 해야한다고 하고.

태스크별 실패 판단·결과 기록과 work 종료 집계를 분리한다. 골조 실패 태스크는
종결하며 다른 워커와 대기 태스크를 중단하지 않는다. 배정 가능한 태스크와
실행 중인 태스크가 소진된 뒤 Work가 골조 재작업 필요를 고지한다.
전역 세션 한도 보류 정책은 기존대로 유지한다.

## 현재 미커밋 구현

- workmodel의 순수 실패 판단을 infer가 사용한다. 인증·할당량·환경·층2 검증 불가·
  반복 출력·상한 갈래를 유지하고, 현재 및 직전 피드백의 동결 위반은 골조 실패로 기록한다.
- `[fp:…] [kind:…]`를 실패 사유에 저장한다. 할당량 실패도 큐 레코드에 사유를 남기며
  pending 복귀·워커 5시간 차단·다른 워커 재할당은 유지한다.
- Work는 배정 가능·실행 중·종결·골조 재작업 필요와 성공 조각을 읽기 전용으로 집계한다.
- 골조 실패의 즉시 노트는 생략한다. 라운드 종결 Redmine 노트와 wait에
  골조 재작업 필요 및 보존된 성공 조각을 함께 표시한다.
- 신규 work 보류·resume·실패 잠금 및 run_many 제어 변경은 제거했다.
  autodispatch 및 그 테스트는 HEAD와 같다.
- test_revise의 직접 호출 위치 검사 4개는 실제 실패 처리 경로 검사로 변경했다.

수정 대상은 workmodel/infer/followup, 큐 lifecycle/cleanup과 해당 회귀 테스트다.
운영 보류·잠금 파일, 워커 설정, 커밋·push·배포·서비스 재기동은 변경하지 않았다.

## 검증과 중단 지점

- 기존 test_infer 무수정: 250/250 통과(최초 구현 시점, 최종 재검증은 남음).
- test_revise: 67/67 통과.
- test_workmodel: 130/130 통과. 실제 infer.run_many를 가짜 큐/실행기로 호출해
  골조 실패 워커가 다음 태스크를 처리하고 다른 워커의 실행 중 결과를 회수하는 것을 검사했다.
- test_failed_work_terminal: 21개 통과. 할당량 사유 rebuild·재할당·fencing,
  골조 실패 후 다른 조각 계속 처리·최종 고지·성공 증거 보존을 확인했다.
- test_followup: **294/297, 3개 실패**. 실패 후 구현과 추가 검사를 중단했다.
- 공식 통합 검사 32개는 이번 변경에서 아직 실행하지 않았다.

실패 3개는 두 레거시 동결 실패의 fail_detail과 last_feedback에 같은 지문이 있는
케이스다. Task의 기존 repeat 우선 분류 때문에 Work 최종 골조 목록에서 빠진다.
새 tagged skeleton 및 tagged code의 종료 집계는 통과했다.

제안된 보완: 태스크의 기존 분류를 변경하지 않고 Work의 최종 집계가
같은 라운드의 복수 동결 위반을 골조 재작업으로 종합하게 한다.
사용자에게 보완·전체 검증 계속 여부를 질문했으며 답변 전에는 수정하지 않는다.

## 남은 작업

최종 집계 보완에 대한 사용자 결정, 후속 출력 검사 재실행, 관련 회귀 및 공식 통합 검사,
최종 코드 리뷰와 기록 갱신이 남아 있다. 커밋·push·배포는 별도 승인 대상이다.
#363 전체 호출부 점진 이행은 이번 2단계와 별개이며 완료로 닫지 않는다.

## 추가 승인: 실패 라운드 통합 후 수정 골조

사용자가 드라이런 결과를 확인한 뒤 다음 흐름을 지정하고 구현을 승인했다.

> 분산작업용 브랜치에 모두 머지하고 거기서 수정해야할 내용을 담은
> 2차 작업 내용을 골조로 생성해 2라운드를 시작해야해!

실패 이력과 병렬 계속 정책은 유지한다. 라운드 결과를 작업 base에 통합하고,
통합본에서 수정·미완성 항목을 다음 골조로 정리한 뒤 같은 work의 다음 라운드를 연다.
작업 브랜치 전진과 main finalize의 기존 사람 게이트는 유지한다.
이번 승인은 구현·격리 검증이며 운영 전진·골조 커밋/push·새 파견을 뜻하지 않는다.

진행 중인 변경: 레거시 복수 동결 집계 보완, followup의 재작업 통합 준비,
재작업 전용 review 통합, cleanup의 결과 브랜치 보존,
통합 전진 기록을 바탕으로 한 개선 등재/reopen 연결과 회귀 검사.
일반 반려·취소·finalize 경로는 기존 계약을 유지한다.
verify-then-commit 방식에서 차단된 시도는 커밋이 없을 수 있으므로
실제로 남아 있는 결과와 없는 결과의 사유를 구분해 다음 골조의 근거로 제공한다.
최종 구현 및 검사 결과는 아래에 추가한다.

## 1차 드라이런 구현 결과

사용자 재개 승인 후 위 흐름을 연결했다. Work가 전체 상태를 종합하고
Python 후속 흐름이 「분산 작업 전체 취소」와 「현재 통합본 수정 후 다음 라운드
골조 준비」를 물음과 구조화된 선택지로 제공한다. 선택 전에 자동 취소·등재하지 않는다.

- `Work.pending_rework`가 표지 없는 레거시 동결 반복도 라운드 전체에서 종합한다.
  태스크의 기존 반복 출력 분류는 유지한다. `rework_plan`은 통합 HEAD/트리,
  수정 대상·사유·성공 결과 재사용과 사람의 선택지를 제공한다.
- followup은 골조 실패를 기록한 채 다른 조각을 기다리고, rejected로 종결된
  재작업 라운드의 통합 준비를 `advance_work(rework=True, confirm=False)`로 수행한다.
  wait는 그 준비 결과를 기다리며, 같은 라운드의 오래된 stopped 기록은 이력을 보존해
  새 준비로 연결한다. 일반 반려·취소·마감·과거 error 기록의 동작은 유지한다.
- 재작업 통합은 성공 durable, 실패 태스크의 남아 있는 durable 및 기록된 마지막
  attempt의 커밋된 소스를 작업 base에 모은다. 실패를 verified로 바꾸지 않는다.
  결과 커밋이 없는 경우는 missing_results로 표시한다. 무검증 시도는 출처를 명시하며
  일반 finalize의 성공 결과 전용 통합에는 섞지 않는다.
- rejected 재작업의 결과 브랜치는 보존한다. 사람이 전체 취소한 cancelled 작업은
  기존 정리 절차를 사용할 수 있다.
- 재작업 통합 트리에 작성한 수정 골조를 재호출 때 강제로 삭제하지 않는다.
  기존 통합 검사 성공과 confirm 승인 뒤 base를 전진하며, 전진 근거를 기존
  review_decision에 기록한다. 검사 실패 시에는 push하지 않고 트리를 보존한다.
- `improve_work(rework=True, expected_base_commit=…)`는 수정 골조의 원격 tip과
  통합 HEAD의 조상 관계를 확인한 후 기존 reopen으로 2차 라운드를 연다.
  기존 MCP→서버→등재 함수와 큐 API에 재작업 인자를 연결했다.
- 현재 라운드의 조각만 종결 집계한다. 지난 라운드의 실패를 보존하면서도
  새 라운드의 pending/claimed 조각을 기다리고 전부 끝난 뒤 ready로 종결한다.

### 격리 드라이런 증거

실제 워커나 운영 큐 대신 임시 Git 원격/작업 트리와 가짜 API·실행기를 사용했다.
실패 워커의 다음 작업 처리 및 병렬 결과 회수, 커밋된 성공·실패 소스 통합,
통합 트리의 수정 골조 보존, 전진 기록, 통합본을 이어받은 2차 골조 등재,
2차 조각 일부 완료 시 in_progress 유지, 최종 성공을 확인했다.
층1/층2 차단으로 미커밋인 실패 본문은 Git 머지 대상이 아니며 수정 근거로 남는다.

- workmodel 134/134, followup 315/315, review 176/176.
- client_mcp 199/199, failed_work_terminal 21개, cleanup 46/46.
- rounds 실패 0건, no_integrator 14/14. diff 공백 검사 통과.
- 부모가 followup/review/rounds/failed_work_terminal/no_integrator를 직접 재실행했다.
  client_mcp 검사는 부모가 실행했고 나머지 담당 검사 출력과 변경 소스를 대조했다.
- 공식 통합 검사 32/32 통과(64.899초). infer 250/250, revise 67/67,
  workmodel 134/134 및 기존 파견·브랜치·검증 경로 포함.

작업 트리는 미커밋이다. 커밋/push/배포·서비스 재기동·실제 파견 및 운영 전진은 실행하지 않았다.
#363의 남은 호출부 점진 이행 및 실제 워커 실증은 이번 1차 드라이런의 완료 범위 밖이다.

## Claude 인수 후 diff 검토와 보완 (2026-10-11)

검토 중 결함 1건을 임시 큐로 재현했다. 한도 반납 경로가 pending 조각에 `fail_reason`·
`fail_detail`을 남기는데 이 필드는 claim에서 지워지지 않고 `verify_task`는 `setdefault`라,
한도 반납 → 다른 워커 재할당 → 검증 reject 시 최종 실패가 `quota_exhausted`·`[kind:quota]`로
남았다(Task 분류 `quota` → 재할당 권고, `.33` 훅은 `fail_detail`을 먼저 읽어 옛 사유 표시).

사용자 선택 B: 한도 반납 사유를 `release_reason`·`release_detail`에 저장하고, workmodel은
pending 상태에서만 그 필드를 읽는다. `fail_*`는 최종 실패 사유 의미를 유지한다.
동시 다조각 첫 동결 위반의 1회 재시도는 사용자 결정으로 현행 유지.

수정: `logic_lifecycle.py`(한도 반납 필드), `workmodel.py`(pending 사유 키),
`test_failed_work_terminal.py`(기존 단언 이전 + 재현 회귀 검사 1건), `test_workmodel.py`(픽스처).
검사: failed_work_terminal 22개, followup 315/315, review 176/176, client_mcp 199/199,
cleanup 46/46, infer 250/250, no_integrator 14/14, workmodel·rounds·revise 실패 0,
공식 통합 32/32(63.1초). 커밋·push·배포 없음.

## 실제 워커 재작업 라운드 실증 (2026-10-11, Claude)

커밋 `fbb207c` 배포·서비스 재기동(16:08) 뒤 사용자 지시로 실증. work
`20261011_1615_363_probe_3f14bef1`(Redmine #803), 워커 지휘자 codex, 병렬.
골조(`master/rework_probe/`): alpha는 `parse_pair(text) -> tuple`을 동결하면서 `[PSEUDO]`가
`(text, sep) -> dict`로 바꾸라고 지시(의도된 골조 결함), beta는 정상.

| 시각 | 사건 |
|---|---|
| 16:15 | 등재 → base `23d462a` push → 파견 2건 (alpha `.2`, beta `.43`) |
| 16:16 | beta 층2 APPROVE → 커밋 `7aed087`. alpha 시도1: `.2` codex가 모순을 감지하고 미수정 BLOCKED → 층1 「스텁 그대로」 → `code` 재시도 |
| 16:21 | alpha 시도2 `.43`: 지시대로 시그니처 변경 → 층1 동결 위반(첫 위반) → `code` 재시도 |
| 16:31 | alpha 시도3: 동결 위반 연속 → **`skeleton` 종결**, 라운드 `rejected` |
| 16:32 | followup 타이머(1분)가 다음 회차에 재작업 통합 준비 → at_gate |

결함(#805): 재작업 통합이 실패 조각 서브 브랜치의 `[revise]` 피드백 커밋 2개를 머지해
통합 트리 `alpha.py` 머리에 `/* AUTO-VERIFY FEEDBACK */`가 들어가 SyntaxError, 근거는
「검증 완료」로 표시됐다. 통합 검사 32/32는 probe 모듈을 import하지 않아 통과했다(#804 사례).
사용자 「원천적으로 고쳐야지」 → `301ddac`: 피드백이 아닌 가장 최근 워커 커밋까지만 머지,
없으면 `missing_results`, 실패 조각 근거는 항상 미검증. 수정 전 코드에서 새 회귀 6건 실패 확인.
배포 후 오염 트리 제거(승인) → `--force` 재준비: beta만 머지, alpha 결과 없음, 피드백 블록 0.

이후(각 단계 사용자 승인):
- 통합 트리에서 라운드 2 골조 커밋 `560e51a` → `advance_work(rework=True, confirm=True)` 통합 32/32,
  base `23d462ac→560e51aa`, `review_decision=rework_advanced`.
- `improve_work(round=2, rework=True, expected_base_commit=560e51aa…)` → 큐 round 2,
  `rework_previous_round=1`. alpha(`e4b0c048`) `.43` 구현 → 층2 APPROVE → 현재 라운드만 집계해
  `ready_for_review` → ⑦ at_gate(통합 32/32). 통합본을 실제 실행해 지시대로 동작 확인.
- 마감 추천안 A: 일반 ⑦ 전진 `560e51aa→7d11255d` → `reject_work` → `sweep_terminal`이 probe
  원격 브랜치 2건 삭제(팁 해시 #803 기록), scratch worktree 제거. `main` 미접촉.

미실증: 「전체 취소」 선택 · 같은 라운드 다조각 동시 동결 종합 · 실패 조각에 워커 커밋이 남은 통합(단위만).
후속 일감: #805(수정) · #806(`.py` 피드백 C 주석, 버그) · #807(BLOCKED 골조 충돌 신호, 결정) ·
#804(통합 검사 보강 아이디어, 사례 추가).
