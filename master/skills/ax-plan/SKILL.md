---
name: ax-plan
description: AX 마스터에서 Redmine 일감을 **시작·재개·진행 마킹**할 때 쓴다 — 이슈 본문의 플랜 영역(`ax:plan`)을 확인하고, 없으면 사용자와 플랜을 짜서 등록하고, 태스크를 하나씩 작업중→완료로 옮긴다. "#N 진행해", "#N 시작하자", "일감 이어서", "다음 태스크", "T3 완료로", "플랜 짜자", "/ax-plan" 같은 발화에 발동. Claude·Codex 공용.
---

# ax-plan — 일감의 플랜 영역으로 일한다

정본: `~/ax-cluster/master/skills/ax-plan/SKILL.md` · 일감 `#826` · 본체 `master/plan_tools.py`

## 1. 도구는 다섯 — `ax-projects` MCP

    plan_start_tool(issue_id)                       시작 판정 + 7단계 표 (읽기)
    plan_set_tool(issue_id, tasks, why)             플랜 등록·태스크 추가/편집
    plan_transition_tool(issue_id, task_id, to, note)   상태 전이 — 상태를 바꾸는 유일한 쓰기
    issue_start_tool(issue_id)                      작업 시작 — 로컬 issue/<N> · 시작 리비전 기록 (#879)
    issue_finish_tool(issue_id, confirm=False)      작업 종료 — main 적용 · 범위 리뷰 요청 (#879)

MCP 가 안 보이거나 실패하면 사유를 보고하고 묻는다. `redmine_note` 로 본문 전체를 보내
플랜을 고치는 우회는 하지 않는다 — 그 경로는 T2 규칙(근거 없는 완료 거절 등)을 거치지 않는다.

## 2. 일감을 시작할 때 — 구현보다 `plan_start_tool` 이 먼저다

판정이 `ok: false` 면 **구현하지 않는다.** 응답의 `next_action` 이 할 일이다.

    no_spec          스펙(무엇을·완료 조건)을 사용자와 먼저 쓴다
    plan_needed      ↓ 3절 — 플랜을 짠다
    plan_invalid     형식 오류를 보여 주고 본문을 함께 고친다
    plan_violations  규칙 위반을 보여 주고 함께 고친다
    blocked          차단 사유·대기 선행을 보고하고 멈춘다
    plan_done        태스크는 끝났다 — 일감 완료는 스펙·승인 규칙으로 따로 판단한다
    resume           작업중 태스크를 **실제 코드·리비전과 대조한 뒤** 이어서 한다
    next             그 태스크를 `plan_transition_tool(…, "작업중")` 으로 옮기고 시작한다

`steps` 는 프로젝트 kind 별 7단계 표다 — `해당없음` 단계는 하지 않고, `조건부` 는 태스크가 정한다.

## 3. 플랜을 짤 때 (`plan_needed`)

1. `search_context_tool`(task_type=`user_command`, user_request=사용자 원문 그대로)로 기존 설계·기능을 찾는다
2. 결과를 **현재 소스와 대조한다** — 합성 문서는 어느 파일을 볼지 찾는 데까지다
3. 근거와 함께 작은 태스크(목표·대상·선행·검증)를 **사용자와 대화로** 정한다 — 추측으로 채우지 않는다
4. 합의된 목록을 `plan_set_tool` 로 등록한다. `why` 에 사용자 결정을 적는다

`tasks` 항목: `id`·`goal` 필수, `target`·`deps`(목록)·`check`·`steps` 선택. `state`·`evidence` 는
넣지 않는다 — 새 태스크는 「대기」로 들어간다. `steps` 는 그 태스크가 하는 **조건부 단계 번호**
(`plan_start` 의 `steps` 표에서 「조건부」인 것, 예 `[2, 6]`)다 — 추측으로 채우지 말고 사용자와 정한다.

## 3-1. 일감 작업 시작·종료 — 브랜치와 리뷰 (`#879`, 마스터 AXCluster 저장소)

- 첫 태스크에 손대기 **전에** `issue_start_tool` 을 부른다. 플랜이 없거나 판정이 ok 가 아니면
  거절된다. 깨끗한 `main` = `origin/main` 이어야 하고, 아니면 사유를 보고하고 멈춘다(고치지 않는다).
  성공하면 로컬 `issue/<N>` 에서 일하고 시작 리비전이 Redmine 에 남는다.
- 커밋은 `issue/<N>` 에 쌓는다. 커밋 승인 규칙은 그대로다.
- 모든 태스크가 끝나면 `issue_finish_tool(N)`(기본 `confirm=False`)으로 범위·커밋 목록을 보여 주고
  **승인을 받은 뒤에만** `confirm=True` 로 부른다. 그 호출이 push·로컬 브랜치 삭제·범위 리뷰 등재·
  Redmine 「리뷰 요청」 노트를 이어서 한다. 리뷰 결과 노트는 리뷰 큐가 끝난 뒤 같은 일감에 붙는다.
- `.33` 요청자 경로와 게임 저장소는 이 도구의 범위가 아니다(후속).

## 3-2. 한 번에 한 일감 — 잠금·보류·취소·완료 게이트 (`#883`)

    issue_pause_tool(issue_id)                              보류 — 잠금 해제 · 브랜치 유지
    issue_cancel_tool(issue_id, confirm=False, delete_branch=False)   취소 — 기본은 미리보기

- `issue_start` 가 일감 잠금을 잡는다. 잠금은 `issue_finish` 뒤에도 **Redmine 「완료」까지** 남는다.
  다른 일감의 `issue_start`·「작업중」 전이는 `#N 작업이 진행 중이다` 로 거절된다 — 그 문장을
  사용자에게 보여 주고 **완료·보류·취소 중 무엇을 할지 묻는다.** 잠금 파일을 손으로 고치지 않는다.
- 보류는 깨끗한 `issue/<N>` 에서만 된다. 재개는 `main` 에서 `issue_start_tool(N)` 을 다시 부른다.
- 취소는 `confirm=False` 미리보기의 **로컬 전용 커밋 목록**을 보여 주고 승인을 받은 뒤 `confirm=True`.
  브랜치 삭제(`delete_branch=True`)는 그 목록을 보여 준 **별도 승인**이 있을 때만이다.
- 「완료」로 닫으면 `redmine.update_issue` 가 판정한다: 그 일감의 범위 리뷰가 끝나지 않았거나
  (대기·실패·포기) **미판정 높음 지적**(open·accepted·failed)이 있으면 `[주의] … 완료 거절` 로
  아무것도 쓰지 않는다. 할 일은 사유 문장에 있다 — 리뷰 재등재, 지적을 실제 코드와 대조해
  **버그면 수정 후 applied**, 오탐·의도면 `update_fix_status(dismissed, note=사유)`(사유 필수).
  어느 쪽인지는 사용자와 정한다. 통과하면 잠금이 풀린다(`warn` 이면 해제 실패 — 사람이 본다).

## 4. 진행 마킹 — 시작할 때와 끝낼 때 둘 다

- 태스크에 손대기 **전에** `작업중` 으로 옮긴다 (선행이 안 끝났으면 거절된다)
- 끝나면 `완료` + `note` 에 근거(커밋 해시·검사 결과). 근거 없는 완료는 거절된다
- 막히면 `차단` + 사유, 이번 범위가 아니면 `해당없음` + 사유
- 응답의 `next` 가 다음 판정이다 — 다음 태스크를 고르는 것은 그 판정이지 내 짐작이 아니다

[주의] 완료는 되돌리지 못한다. 잘못 마킹했으면 사용자에게 알리고 본문을 함께 고친다.
[주의] 같은 일감을 두 세션이 동시에 마킹하지 않는다 — 나중 쓰기가 앞의 수정을 덮는다.

## 5. 이 스킬이 바꾸지 않는 것

커밋·푸시·배달·서비스 재기동의 승인 규칙, ⑦ 전진·finalize 게이트, 일감의 Redmine 상태
(「완료」로 닫기)는 그대로다. 태스크가 전부 완료돼도 일감을 닫는 것은 별도 판단이다.
