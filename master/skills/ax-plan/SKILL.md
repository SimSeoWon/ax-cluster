---
name: ax-plan
description: AX 마스터에서 Redmine 일감을 **시작·재개·진행 마킹**할 때 쓴다 — 이슈 본문의 플랜 영역(`ax:plan`)을 확인하고, 없으면 사용자와 플랜을 짜서 등록하고, 태스크를 하나씩 작업중→완료로 옮긴다. "#N 진행해", "#N 시작하자", "일감 이어서", "다음 태스크", "T3 완료로", "플랜 짜자", "/ax-plan" 같은 발화에 발동. Claude·Codex 공용.
---

# ax-plan — 일감의 플랜 영역으로 일한다

## 목차

- 개요
- 사용 예
- 1. 도구는 다섯 — `ax-projects` MCP
- 2. 일감을 시작할 때 — 구현보다 `ax-projects:plan_start_tool` 이 먼저다
- 3. 플랜을 짤 때 (`plan_needed`)
- 3-1. 일감 작업 시작·종료 — 브랜치와 리뷰 (`#879`, 마스터 AXCluster 저장소)
- 3-2. 한 번에 한 일감 — 잠금·보류·취소·완료 관문 (`#883`·`#889`)
- 4. 진행 마킹 — 시작할 때와 끝낼 때 둘 다
- 5. 이 스킬이 바꾸지 않는 것

## 개요

정본: `~/ax-cluster/master/skills/ax-plan/SKILL.md` · 일감 `#826` · 본체 `master/plan_tools.py`

## 사용 예

이런 발화로 이 스킬이 쓰인다(description 의 발동 예):

    「#N 진행해」
    「#N 시작하자」
    「일감 이어서」
    「다음 태스크」
    「T3 완료로」
    「플랜 짜자」

구획은 위 목차의 제목으로 찾아 읽는다 — 절차는 「1. 도구는 다섯 — `ax-projects` MCP」부터다.

## 1. 도구는 다섯 — `ax-projects` MCP

    ax-projects:plan_start_tool(issue_id)                       시작 판정 + 7단계 표 (읽기)
    ax-projects:plan_set_tool(issue_id, tasks, why)             플랜 등록·태스크 추가/편집
    ax-projects:plan_transition_tool(issue_id, task_id, to, note)   상태 전이 — 상태를 바꾸는 유일한 쓰기
    ax-projects:issue_start_tool(issue_id)                      작업 시작 — 로컬 issue/<N> · 시작 리비전 기록 (#879)
    ax-projects:issue_finish_tool(issue_id, confirm=False)      작업 종료 — main 적용 · 마감 추적 등록 · 잠금 해제 (#879·#884)

MCP 가 안 보이거나 실패하면 사유를 보고하고 묻는다. `ax-client:redmine_note` 로 본문 전체를 보내
플랜을 고치는 우회는 하지 않는다 — 그 경로는 T2 규칙(근거 없는 완료 거절 등)을 거치지 않는다.

## 2. 일감을 시작할 때 — 구현보다 `ax-projects:plan_start_tool` 이 먼저다

판정이 `ok: false` 면 **구현하지 않는다.** 응답의 `next_action` 이 할 일이다.

    no_spec          스펙(무엇을·완료 조건)을 사용자와 먼저 쓴다
    plan_needed      ↓ 3절 — 플랜을 짠다
    plan_invalid     형식 오류를 보여 주고 본문을 함께 고친다
    plan_violations  규칙 위반을 보여 주고 함께 고친다
    blocked          차단 사유·대기 선행을 보고하고 멈춘다
    plan_done        태스크는 끝났다 — 일감 완료는 스펙·승인 규칙으로 따로 판단한다
    resume           작업중 태스크를 **실제 코드·리비전과 대조한 뒤** 이어서 한다
    next             그 태스크를 `ax-projects:plan_transition_tool(…, "작업중")` 으로 옮기고 시작한다

`steps` 는 프로젝트 kind 별 7단계 표다 — `해당없음` 단계는 하지 않고, `조건부` 는 태스크가 정한다.

## 3. 플랜을 짤 때 (`plan_needed`)

1. `ax-projects:search_context_tool`(task_type=`user_command`, user_request=사용자 원문 그대로)로 기존 설계·기능을 찾는다
2. 결과를 **현재 소스와 대조한다** — 합성 문서는 어느 파일을 볼지 찾는 데까지다
3. 근거와 함께 작은 태스크(목표·대상·선행·검증)를 **사용자와 대화로** 정한다 — 추측으로 채우지 않는다
4. 합의된 목록을 `ax-projects:plan_set_tool` 로 등록한다. `why` 에 사용자 결정을 적는다

`tasks` 항목: `id`·`goal` 필수, `target`·`deps`(목록)·`check`·`steps` 선택. `state`·`evidence` 는
넣지 않는다 — 새 태스크는 「대기」로 들어간다. `steps` 는 그 태스크가 하는 **조건부 단계 번호**
(`ax-projects:plan_start_tool` 의 `steps` 표에서 「조건부」인 것, 예 `[2, 6]`)다 — 추측으로 채우지 말고 사용자와 정한다.

## 3-1. 일감 작업 시작·종료 — 브랜치와 리뷰 (`#879`, 마스터 AXCluster 저장소)

- 첫 태스크에 손대기 **전에** `ax-projects:issue_start_tool` 을 부른다. 플랜이 없거나 판정이 ok 가 아니면
  거절된다. 깨끗한 `main` = `origin/main` 이어야 하고, 아니면 사유를 보고하고 멈춘다(고치지 않는다).
  작업 저장소는 기존 `AXCluster/config.yaml`의 `track.local_clone`을 읽는 `ProjectPaths.repo`로 결정한다(`#905`).
  응답의 `repo`가 편집·커밋할 경로이며 그 저장소의 로컬 `issue/<N>`에서 작업한다. 시작 리비전은 Redmine에 남는다.
  운영 서비스 코드 위치를 작업 저장소로 추정하거나 별도 고정 경로를 만들지 않는다.
- 커밋은 응답 `repo`의 `issue/<N>`에 쌓는다. 운영 체크아웃에서 구현하지 않는다. 커밋 승인 규칙은 그대로다.
- 모든 태스크가 끝나면 `ax-projects:issue_finish_tool(N)`(기본 `confirm=False`)으로 범위·커밋 목록을 보여 주고
  **승인을 받은 뒤에만** `confirm=True` 로 부른다. 그 호출이 push·로컬 브랜치 삭제·**마감 추적 등록**
  (범위의 해시 전부)·색인기 리뷰 연결·**잠금 해제**·Redmine 「리뷰 요청」 노트와 **「완료」·100 닫기**를
  이어서 한다(`#884`·`#889` — main 적용 = 마감). 반영 대상은 설정된 작업 저장소의 main이다.
  운영 서비스 배포·재기동은 별도 승인이다. 기존 remote·쓰기 가드가 거절하면 우회하지 않고 보고한다.
  범위 리뷰를 직접 등재하지 않는다 — **해시별 커밋 리뷰**가
  끝날 때마다 진행 노트가 붙고, 모두 끝나면 **종합 리뷰 1회**가 걸려 그 결과가 같은 일감에 노트로 붙는다
  (닫힌 일감에도 붙는다 · 다시 열거나 새 일감을 만들지 않는다). 기다리지 않고 다음 일감으로 간다.
- 등록이 실패하면 잠금이 **남고 일감도 열린 채다**(`registered: false` · `closed: false` · `why`) — 리뷰가
  이어지지 않은 채 다음으로 가지 않게 하는 장치다. 사유를 보고하고 묻는다(같은 인자로 다시 부르면 같은
  범위는 `already`). 닫기만 실패하면(`closed: false` · `Redmine 닫기` in `why`) 노트는 남는다 — 보고하고 묻는다.
- `.33` 요청자는 같은 규칙을 `ax-client` 도구(`plan_*`·`issue_*`, 8101 대행)와 `ax-issue` 스킬로 쓴다 —
  git 은 그 기계의 worktree 에서 하고 인프라는 기록만 한다(본체 `master/issue_infra.py`).

## 3-2. 한 번에 한 일감 — 잠금·보류·취소·완료 관문 (`#883`·`#889`)

    ax-projects:issue_pause_tool(issue_id)                              보류 — 잠금 해제 · 브랜치 유지
    ax-projects:issue_cancel_tool(issue_id, confirm=False, delete_branch=False)   취소 — 기본은 미리보기

- `ax-projects:issue_start_tool` 가 일감 잠금을 잡는다. 잠금은 `ax-projects:issue_finish_tool` 가 **마감 추적 등록에 성공한 뒤** 푼다
  (`#884` T5, 사용자 결정 2026-11-04) — 그 전(작업 중·등록 실패)에는
  다른 일감의 `ax-projects:issue_start_tool`·「작업중」 전이가 `#N 작업이 진행 중이다` 로 거절된다 — 그 문장을
  사용자에게 보여 주고 **완료·보류·취소 중 무엇을 할지 묻는다.** 잠금 파일을 손으로 고치지 않는다.
- 보류는 설정된 작업 저장소의 `issue/<N>`이 깨끗할 때만 된다. 브랜치는 보존하고 같은 저장소의 main으로 복귀한다.
  재개는 `ax-projects:issue_start_tool(N)`을 다시 부르고 응답 `repo`에서 이어간다.
- 취소는 `confirm=False` 미리보기의 **로컬 전용 커밋 목록**을 보여 주고 승인을 받은 뒤 `confirm=True`.
  브랜치 삭제(`delete_branch=True`)는 그 목록을 보여 준 **별도 승인**이 있을 때만이다.
- 일감 마감은 **`ax-projects:issue_finish_tool` 하나**다 — main 에 적용하면 그 자리에서 「완료」·100 으로 닫힌다(`#889`,
  사용자 결정 2026-11-06·11-07). 손으로 「완료」를 보내면 `redmine.update_issue` 관문이 **일감 잠금만** 본다:
  그 일감이 아직 작업 중(잠금 활성·보류 — 등록된 프로젝트 트윈을 훑는다)이면 `[주의] … 완료 거절` 로
  아무것도 쓰지 않는다 — finish·보류·취소가 먼저다. 잠금 밖 일감은 그대로 닫힌다. 읽기 실패면 막는다.
  **리뷰는 관문이 아니다** — 해시별·종합 리뷰의 높음 지적은 노트·R번호 게시판·주간 플랜으로 올라가고,
  처리(수정 후 applied · 오탐이면 `ax-client:update_fix_status(dismissed, note=사유)`)는 사용자와 정해 별건으로 한다.

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
