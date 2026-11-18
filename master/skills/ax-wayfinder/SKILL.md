---
name: ax-wayfinder
description: AX 마스터에서 탐색이 필요한 큰 일감을 웨이파인더 맵으로 굴린다 — Root 일감 본문에 목적지·노드·안개를 적은 지도를 만들고, 집을 수 있는 노드(Frontier)를 골라 보통의 일감 흐름으로 처리하며, 새 노드는 제안과 사용자 동의 뒤에만 등록하고, Root 마감은 사람이 정한다. 신규 기능 인터뷰가 웨이파인더 진행을 물어 수락됐을 때나 "웨이파인더로 하자", "맵 만들어", "다음 노드 뭐야", "노드 추가", "/ax-wayfinder" 같은 발화에 발동. Claude·Codex 공용.
---

# ax-wayfinder — Root 일감의 지도로 탐색형 작업을 굴린다

## 목차

- 개요
- 사용 예
- 1. 도구
- 2. 맵 만들기
- 3. 진행 — Frontier 와 노드 처리
- 4. 새 노드 — 제안 → 동의 → 등록
- 5. 재검증
- 6. Root 마감
- 7. 어긋남·거절

## 개요

정본: `~/ax-cluster/master/skills/ax-wayfinder/SKILL.md` · 일감 `#982` · 본체 `master/wayfinder.py`

- **Root = 지도**다. Root 일감은 목적지·노드 표·안개·비범위를 본문의 지도 영역에 담을 뿐 스스로 작업하지 않는다.
- **노드 = 일감**이다. 노드 하나는 Root 의 하위 일감이고, 보통의 `ax-plan` 흐름(인터뷰·플랜·`ax-projects:issue_start_tool`·
  `ax-projects:issue_finish_tool`)으로 처리한다.
- 노드 타입은 셋 — **프리필**(미리 알아내야 하는 것) · **작업**(구현) · **검증**(확인).
- 노드 상태 — 완료 · Frontier(지금 집을 수 있음) · 작업중 · 차단 · 대기 · 재검증.
- 지도 영역이 기록이고 Redmine 의 부모·관계는 그 보이는 사본이다. 둘이 어긋나면 도구가 거절한다.
- 선행이 자기 조상·후손이면 Redmine 관계를 만들지 않는다 — Redmine 이 그 쌍을 거절하고(실측 422), 순서는
  「하위 일감」 트리가 보인다. 그 선행은 지도 표·다이어그램·Frontier 계산에만 남는다. 형제·다른 가지 선행만 `blocks` 다.
- 사람 게이트는 셋 — **맵 등록 · 새 노드 등록 · Root 마감**. 셋 다 사용자 동의 원문(`user_answer`) 없이는 쓰지 않는다.
- 지금 범위 밖: `.33` 요청자 표면(`ax-client`)과 원격 브랜치 연동. 이 스킬은 마스터 세션 전용이다.

## 사용 예

이런 발화로 이 스킬이 쓰인다(description 의 발동 예):

    「웨이파인더로 하자」 — 인터뷰의 웨이파인더 질문에 수락한 경우 포함
    「맵 만들어」
    「다음 노드 뭐야」
    「노드 추가」
    「/ax-wayfinder」

## 1. 도구

모두 `ax-projects` MCP 다. 응답은 JSON 이고, 규칙 거절은 `ok: false` + `refused: true` + `why`, 입력 형식 오류·
읽기 실패는 `ok: false` + `error` 다.

    ax-projects:wayfinder_create_tool(root_id, destination, nodes, fog, out_of_scope, confirm, user_answer)   맵 미리보기·등록
    ax-projects:wayfinder_status_tool(root_id)                         Frontier·상태 개수 + 지도/Redmine 대조 (읽기)
    ax-projects:wayfinder_sync_tool(root_id)                           다시 계산 — 바뀌었을 때만 Root 본문 쓰기
    ax-projects:wayfinder_propose_tool(root_id, title, type, parent, deps, summary)   새 노드 제안 (쓰기 0)
    ax-projects:wayfinder_register_tool(root_id, proposal, user_answer)   제안 등록 (사람 게이트)
    ax-projects:wayfinder_claim_tool(root_id, node_id, owner)          Frontier 노드 선점 (지도만)
    ax-projects:wayfinder_verified_tool(root_id, node_id, evidence)    재검증 노드 완료 (근거 필수)
    ax-projects:wayfinder_close_tool(root_id, confirm, user_answer)    Root 마감 미리보기·마감 (사람 게이트)

## 2. 맵 만들기

1. **인터뷰로 가른다** — 목적지(끝났을 때 무엇이 되어 있나)를 사용자 언어로 정하고, 할 일을 **분명한 것**과
   **애매한 것**으로 나눈다. 분명한 것은 노드가 되고, 애매한 것은 안개(`fog`)로 남기거나 그것을 밝힐 프리필 노드로
   만든다. 이번에 하지 않는 것은 `out_of_scope` 에 적는다. 한 턴에 질문 하나, 가설과 추정 답을 먼저 보인다.
2. **미리보기** — `ax-projects:wayfinder_create_tool(..., confirm=False)`. `nodes` 항목은
   `{"key", "title", "type", "parent": "Root" 또는 상위 key, "deps": [선행 key], "summary"}` 이다.
   쓰기는 0건이고 응답의 노드 번호는 임시 번호다.
3. **보이고 동의받는다** — 미리보기의 노드 표·선행·안개·비범위를 사용자에게 보인다. 고치면 2로 돌아간다.
4. **등록** — 명시 동의를 받은 뒤 같은 입력으로 `confirm=True`, `user_answer` 에 사용자 동의 원문을 싣는다.
   도중 실패는 되돌리지 않는다 — 응답의 `created`·`step`·`why` 를 그대로 보고한다(7).

## 3. 진행 — Frontier 와 노드 처리

1. `ax-projects:wayfinder_status_tool(root_id)` 로 Frontier 와 대조 결과를 본다. `check.ok` 가 false 면 7로 간다.
2. Frontier 가 여럿이면 어느 노드를 집을지 사용자에게 묻는다 — 순서는 내가 고르지 않는다.
3. `ax-projects:wayfinder_claim_tool(root_id, node_id, owner)` 로 선점한다. 지도만 바뀌고 Redmine 담당자는 그대로다.
4. 노드 일감을 **보통의 `ax-plan` 흐름**으로 처리한다 — `ax-projects:plan_start_tool` 부터.
5. 노드 일감을 `ax-projects:issue_finish_tool` 로 마감하면 맵이 자동으로 갱신된다(노드 표지 → Root sync).
   손으로 지도를 고치지 않는다.
6. 지도가 실제와 다르게 보이면 `ax-projects:wayfinder_sync_tool(root_id)` 로 다시 계산한다. 바뀐 것이 없으면 쓰지 않는다.

## 4. 새 노드 — 제안 → 동의 → 등록

작업 중 지도에 없던 일이 드러나면 바로 일감을 만들지 않는다.

1. `ax-projects:wayfinder_propose_tool(root_id, title, type, parent, deps, summary)` — 쓰기 0건.
   `parent` 는 "Root" 또는 노드 번호다.
2. 응답을 보인다 — `duplicates`(붙는 자리에서 Root 까지 **모든 단계의 형제**와 비교한 중복 후보 점수, 판정 아님)와
   `reverify`(이 노드가 추가되면 다시 확인해야 할 완료 노드) 둘 다.
3. 사용자에게 묻는다 — 새 노드로 등록 · 기존 형제 노드에 합치기 · 하지 않기.
4. 등록에 동의하면 `ax-projects:wayfinder_register_tool(root_id, proposal, user_answer)` — `proposal` 은 1의 응답
   그대로, `user_answer` 는 동의 원문이다. 합치기로 하면 등록하지 않고 그 형제 노드의 범위 안에서 처리한다.

## 5. 재검증

새 노드 등록으로 `재검증` 상태가 된 노드는 그 노드의 검사·확인을 다시 돌린다. 결과가 맞으면
`ax-projects:wayfinder_verified_tool(root_id, node_id, evidence)` 로 완료로 되돌린다 — `evidence` 는 다시 돌린
검사 이름과 결과(커밋 해시·통과 줄)다. 결과가 틀리면 완료로 되돌리지 않고 사용자에게 보고한다.

## 6. Root 마감

1. `ax-projects:wayfinder_close_tool(root_id)` — 미리보기. `blockers`(완료 아닌 노드·남은 안개)를 보인다.
2. 막는 것이 있으면 마감하지 않는다 — 그 목록이 다음 할 일 후보다.
3. 막는 것이 0건이고 사용자가 명시적으로 마감에 동의했을 때만 `confirm=True` + `user_answer`(동의 원문)로 부른다.
   짧은 수긍(「응」)은 앞에 마감을 물었을 때만 동의로 읽는다.

## 7. 어긋남·거절

- **어긋남** — `ax-projects:wayfinder_status_tool` 의 `check.differences` 나 쓰기 도구의 거절 `why` 에 지도와 Redmine
  (부모·`blocks` 관계·노드 표지)의 차이가 나오면 **손으로 고치지 않는다.** 차이 목록을 그대로 보이고 어떻게
  할지 사용자에게 묻는다.
- **거절**(`refused: true`) — 사유를 그대로 보고하고 사용자에게 묻는다. 우회 호출·임시 스크립트로 대신하지 않는다.
- **도중 실패**(`step`·`created`) — 이미 만들어진 번호와 멈춘 단계를 보고한다. 되돌리기·재시도는 사용자가 정한다.
- `error`(입력 형식·읽기 실패) — 입력을 고칠 수 있으면 고쳐 다시 미리보기부터, 읽기 실패면 보고하고 멈춘다.
