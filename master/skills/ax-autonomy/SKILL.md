---
name: ax-autonomy
description: AX 마스터에서 Redmine 일감 플랜의 **자율성 값(0~1, 기본 0.5)** 을 바꾸고 남은(대기) 태스크만 다시 짠 플랜을 제안한다 — 시작된 태스크·근거·개발 완료 체크리스트는 그대로, 등록은 사용자 동의 뒤. "자율성 바꿔", "자율성 0.8로", "태스크 더 크게 묶어", "더 잘게 쪼개", "/ax-autonomy" 같은 발화에 발동. Claude·Codex 공용.
---

# ax-autonomy — 자율성 값을 바꾸고 남은 태스크를 다시 제안한다

## 목차

- 개요
- 1. 도구
- 2. 절차
- 3. 이 스킬이 하지 않는 것

## 개요

정본: `~/ax-cluster/master/skills/ax-autonomy/SKILL.md` · 일감 `#963` · 본체 `master/plan_proposal.py`

자율성은 플랜 전체에 걸린 값이다(플랜 시작 표지 `autonomy=`, 없으면 0.5). 값이 태스크 세밀도와 어떻게
대응하는지는 `#948` 이 정한다 — 지금은 값을 기록하고, **남은 태스크를 어떻게 다시 짤지는 사용자와 대화로** 정한다.

## 1. 도구

    ax-projects:plan_autonomy_tool(issue_id, value, why, tasks)    값 변경 이력 노트 + 대기 태스크만 다시 짠 제안
    ax-projects:plan_set_tool(issue_id, tasks, why, user_answer)   동의 뒤 등록 — 최신 제안과 같은 목록이어야 한다
    ax-projects:plan_start_tool(issue_id)                          지금 플랜·자율성 확인(읽기)

## 2. 절차

1. `ax-projects:plan_start_tool` 로 지금 플랜을 읽고, 지금 값과 대기 태스크를 사용자에게 보인다.
2. 새 값과, 그 값으로 대기 태스크를 어떻게 다시 짤지(쪼갤지·묶을지·그대로 둘지)를 사용자와 정한다.
   모호하거나 정보가 없으면 묻는다 — 추측으로 채우지 않는다.
3. `ax-projects:plan_autonomy_tool(issue_id, value, why, tasks=다시 짠 대기 태스크)` — `tasks` 를 비우면 지금 대기
   태스크를 그대로 다시 제안한다. 시작된 태스크(작업중·완료·차단·해당없음)와 근거, 체크리스트는 자동으로 옮겨진다.
4. 제안 표(응답의 `tasks` 순서 = 시작된 태스크 + 새 대기 태스크)를 보이고 동의를 받는다. 고치면 3 을 다시 한다.
5. 동의를 받으면 그 목록 그대로 `ax-projects:plan_set_tool(…, user_answer=사용자 동의 원문)`. 이때 본문의 자율성 값이 바뀐다.

## 3. 이 스킬이 하지 않는 것

- 값↔세밀도 대응을 스스로 정하지 않는다(`#948`).
- 시작된 태스크를 바꾸거나 빼지 않는다 — 도구가 거절한다.
- 동의 없이 등록하지 않는다 — `user_answer` 가 비면 거절된다.
