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
- 8. 안개·범위 밖·목적지 편집

## 개요

정본: `~/ax-cluster/master/skills/ax-wayfinder/SKILL.md` · 일감 `#982` · 본체 `master/wayfinder.py`

- **Root = 지도**다. Root 일감은 목적지·노드 표·안개·비범위를 본문의 지도 영역에 담을 뿐 스스로 작업하지 않는다.
- **맵은 자란다**(`#1028`). 처음에 확정하는 것은 **목적지 하나**이고, 맵은 목적지 + 지금 집을 수 있는 첫 노드로
  시작한다. 다음 노드는 앞 노드가 끝나 무엇을 모르는지 드러난 뒤 4절(제안 → 동의 → 등록)로 붙는다 — 처음부터
  노드 사슬을 다 깔면 설계서를 먼저 다 만드는 분산 작업(work)과 같아진다.
- **노드는 지도에 먼저, 일감은 선점 때** 만든다(`#1036`). 착수 전 노드는 예정 키 P1·P2…로 지도에만 있다.
  선점하면 Root 하위 일감이 되고, 보통의 `ax-plan` 흐름(인터뷰·플랜·`ax-projects:issue_start_tool`·
  `ax-projects:issue_finish_tool`)으로 처리한다. 기존 번호만 있는 지도도 그대로 읽는다.
- 노드 타입은 셋 — **프리필**(미리 알아내야 하는 것) · **작업**(구현) · **검증**(확인).
- 노드 상태 — 완료 · Frontier(지금 집을 수 있음) · 작업중 · 차단 · 대기 · 재검증.
- 지도 영역이 기록이고 Redmine 의 부모·관계는 그 보이는 사본이다. 둘이 어긋나면 도구가 거절한다.
- Redmine 에서 노드는 **모두 Root 의 직속 하위 일감**이다. 파생 트리(누가 누구에서 나왔나)는 지도 표의 「부모」 칸과
  다이어그램에만 있다 — Redmine 은 열린 하위 일감이 있는 부모를 닫지 못하고 조상-후손 관계도 거절한다(#982 T7 실측).
  선행은 지도에 먼저 적고, 선점 때 이미 일감이 있는 선행과 형제 사이 `blocks` 를 건다.
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
    ax-projects:wayfinder_dispatch_tool(root_id, node_ids, confirm, user_answer)   분산 사이클 드라이런·발주
    ax-projects:wayfinder_sync_tool(root_id)                           다시 계산 — 바뀌었을 때만 Root 본문 쓰기
    ax-projects:wayfinder_propose_tool(root_id, title, type, parent, deps, summary, graduates)   새 노드 제안 (쓰기 0)
    ax-projects:wayfinder_register_tool(root_id, proposal, user_answer)   제안 등록 (사람 게이트)
    ax-projects:wayfinder_claim_tool(root_id, node_id, owner, prepare_only)   Frontier 선점 또는 분산 인터뷰용 티켓 준비
    ax-projects:wayfinder_verified_tool(root_id, node_id, evidence)    재검증 노드 완료 (근거 필수)
    ax-projects:wayfinder_close_tool(root_id, confirm, user_answer)    Root 마감 미리보기·마감 (사람 게이트)
    ax-projects:wayfinder_edit_propose_tool(root_id, op, target, text, reason)   맵 편집 제안 (쓰기 0)
    ax-projects:wayfinder_edit_apply_tool(root_id, proposal, user_answer)      맵 편집 적용 (사람 게이트)

## 2. 맵 만들기

1. **목적지를 인터뷰로 확정한다** — 끝났을 때 무엇이 되어 있나를 사용자 언어로 정한다. 인터뷰가 확정하는 것은
   **목적지 하나**다. 사용자가 말한 중간 경유지·방법 설명은 참조 자료다 — 맵에 노드로 옮기지 않는다(일감 본문·노트에
   남아 있다). 한 턴에 질문 하나, 가설과 추정 답을 먼저 보인다.
2. **첫 노드를 정한다** — 지금 바로 집을 수 있는 노드만 둔다(대개 「목적지까지 지금 무엇을 모르나」를 재는 프리필
   하나). 서로 의존 없는 출발점이 둘 이상이면 여럿도 된다. **선행이 걸린 노드는 만들지 않는다** — 도구가 거절한다.
   사용자가 이미 경계로 밝힌 것은 `out_of_scope`, 「모른다」고 분명히 한 것은 `fog` 에 적을 수 있다(선택).
3. **미리보기 → 보이고 동의받는다** — `ax-projects:wayfinder_create_tool(..., confirm=False)`. `nodes` 항목은
   `{"key", "title", "type", "parent": "Root", "deps": [], "summary"}` 이다. 쓰기는 0건이고 노드는 예정 키
   P1·P2…로 보인다. 목적지·첫 노드·안개·비범위를 사용자에게 보인다. 고치면 다시 미리보기.
4. **등록** — 명시 동의를 받은 뒤 같은 입력으로 `confirm=True`, `user_answer` 에 사용자 동의 원문을 싣는다.
   Root 지도만 쓴다(일감 0). `created` 는 입력 key → 예정 키다. 일감은 3절의 선점 때 만든다.
   도중 실패는 되돌리지 않는다 — 응답의 `created`·`step`·`why` 를 그대로 보고한다(7).

## 3. 진행 — Frontier 와 노드 처리

1. `ax-projects:wayfinder_status_tool(root_id)` 로 Frontier 와 대조 결과를 본다. `check.ok` 가 false 면 7로 간다.
2. 사용자에게 단독 처리와 분산 발주 중 어떤 방식으로 진행할지 묻는다. 이 작업의 방식을 이미 정했으면 그 답을 따른다.
3. 단독 처리에서는 Frontier가 여럿이면 어느 노드를 집을지 묻는다. 한 건씩 선점, 인터뷰, 플랜, 구현, 검증을 진행한다.
   `ax-projects:wayfinder_claim_tool(root_id, node_id, owner)` 로 선점한다. `node_id` 는 번호 또는 예정 키 P<n>이다.
   예정 노드면 일감·선행 blocks를 만들고, 지도 키와 그 키를 가리키는 부모·선행을 번호로 바꾼다.
   응답 `id` 는 일감 번호, `key` 는 옛 예정 키다. Redmine 담당자는 그대로다. 별도 동의 게이트는 없다.
4. **선점 응답의 `id`** 로 노드 일감을 보통의 `ax-plan` 흐름으로 처리한다 — `ax-projects:plan_start_tool` 부터.
5. 노드 일감을 `ax-projects:issue_finish_tool` 로 마감하면 맵이 자동으로 갱신된다(노드 표지 → Root sync).
   손으로 지도를 고치지 않는다.
   그다음 Frontier 가 비었고 목적지에 아직 닿지 않았으면, 끝난 노드의 결과로 드러난 다음 노드를 4절로 제안한다 —
   맵은 이렇게 자란다(`#1028`). 무엇을 붙일지는 사용자와 정한다.
6. 분산 발주는 사이클마다 반복한다.
   - 이번 사이클의 작업 가능한 노드를 보여 주고 사용자와 준비 대상을 정한다.
     `ax-projects:wayfinder_claim_tool(root_id, node_id, prepare_only=True)` 로 한 건씩 티켓을 준비한다.
     번호가 있는 Frontier는 그 티켓을 재사용한다. 준비한 노드는 담당 없이 Frontier에 남는다.
   - 각 티켓에서 `ax-projects:plan_start_tool`로 착수 전 인터뷰를 열고 사용자와 명세·태스크·개발 완료 체크리스트를 확정한다.
   - `ax-projects:wayfinder_dispatch_preview_tool(root_id, node_ids)` 로 드라이런한다.
     준비된 티켓, 대기 사유, 잠금 장부와 레지스트리 기준 예상 워커를 보여 준다.
     드라이런이 끝나면 사용자의 실제 발주 요청을 기다린다. 요청 뒤 같은 대상을
     `ax-projects:wayfinder_dispatch_tool(root_id, node_ids, confirm=True, user_answer=요청 원문)` 로 발주한다.
   - 이번 묶음의 결과를 티켓에서 모아 검수한다. 선행이 끝나거나 안개가 걷힌 노드는 다음 사이클에서 준비한다.
     수정이 필요한 노드는 같은 티켓에 근거와 수정 요구를 남긴다.
7. 지도가 실제와 다르게 보이면 `ax-projects:wayfinder_sync_tool(root_id)` 로 다시 계산한다. 바뀐 것이 없으면 쓰지 않는다.

## 4. 새 노드 — 제안 → 동의 → 등록

작업 중 지도에 없던 일이 드러나면 바로 일감을 만들지 않는다.

1. `ax-projects:wayfinder_propose_tool(root_id, title, type, parent, deps, summary)` — 쓰기 0건.
   `parent` 는 "Root" 또는 노드 번호·예정 키 P<n>이다. `deps` 도 번호·예정 키를 받는다.
   이 노드가 안개 한 줄을 구체화한 것이면 `graduates` 에 그 줄(글 또는
   1부터 센 번호)을 준다 — 등록 때 노드와 함께 안개에서 걷힌다(졸업).
2. 응답을 보인다 — `duplicates`(붙는 자리에서 Root 까지 **모든 단계의 형제**와 비교한 중복 후보 점수, 판정 아님)와
   `reverify`(이 노드가 추가되면 다시 확인해야 할 완료 노드) 둘 다.
3. 사용자에게 묻는다 — 새 노드로 등록 · 기존 형제 노드에 합치기 · 하지 않기.
4. 등록에 동의하면 `ax-projects:wayfinder_register_tool(root_id, proposal, user_answer)` — `proposal` 은 1의 응답
   그대로, `user_answer` 는 동의 원문이다. 합치기로 하면 등록하지 않고 그 형제 노드의 범위 안에서 처리한다.
   응답 `id` 는 새 예정 키다. 일감·blocks는 만들지 않으며 선점할 때 번호가 생긴다.

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

## 8. 안개·범위 밖·목적지 편집

노드 없이 지도만 바꾸는 일이다. 순서는 늘 **제안(쓰기 0) → 보이고 묻기 → 동의 원문으로 적용**이다.
지도 영역을 손으로 고치지 않는다 — Root 마감은 안개가 남아 있으면 거절되므로, 안개는 이 경로로만 줄인다.

    「기획서 나왔으니 ○○ 안개 걷어줘」   새 노드면 4절 + graduates · 노드 없이 결정만이면 fog_resolve
    「○○는 기존 것으로 충분하다고 정했어」 fog_resolve(target, reason=결정 근거 — Root 노트에만 남는다)
    「○○는 이번엔 안 해」               fog_to_out(target, reason)
    「□□ 노드는 이번 범위 아니야」        node_out(target=노드 번호 또는 예정 키, reason)
    「△△도 아직 모르겠어」              fog_add(text)
    목적지 문구 바꾸기                  destination(text)
    범위 밖 줄 고치기 · 다시 안개로       out_edit(target, text) · out_to_fog(target)

1. `ax-projects:wayfinder_edit_propose_tool(root_id, op, target, text, reason)` — `target` 은 줄 글 그대로 또는
   1부터 센 번호다. 응답의 `before`·`after` 를 사용자에게 보인다.
2. **node_out** 은 응답의 `relations`(지울 관계)·`dependents`(선행에서 빠질 노드)도 보인다. 파생 자식이 있거나
   이미 완료된 노드면 거절(`refused`)된다 — 자식 목록을 보이고 무엇부터 할지 묻는다.
   예정 노드는 지도에서만 뺀다(관계 삭제·일감 닫기 없음).
3. 동의를 받으면 `ax-projects:wayfinder_edit_apply_tool(root_id, proposal, user_answer)` — `proposal` 은 1의 응답
   그대로. node_out 이 `step: 노드 닫기` · `map_written: true` 로 끝나면 지도는 이미 범위 밖이다 — 그 노드 일감만
   닫히지 않은 것이므로 보고하고 사용자에게 묻는다.
