# 227 — 웨이파인더 원격 노드 일감 흐름: 워커 착수·제출과 마스터 검수 (#1050)

#1008의 P4다. P1(#1037) 티켓 한정 읽기·노트, P2(#1038) 노드·워커 원자 예약, P3(#1039) 권한 전달·종료 확인 뒤 검수 대기 위에
배정된 워커의 원격 착수·결과 제출과 마스터의 검수(통과 마감·재작업)를 연결했다. 실제 분산 발주는 0건이고, 두 워커 병렬 실증은 P5다.

`issue_start_tool`: `repo=/home/sim/ax-cluster/.ax-issues/1050`, `branch=issue/1050`, `start_rev=0d145c845ed75611736346de117d35c0ca36ffe3`.
T1은 Codex, Codex 토큰 소진 인계(`9329791`) 뒤 T2·T3은 Claude가 했다(작성 계열 누적 codex·claude, 마스터 담당 기록 claude).

## 사용자 결정 둘

플랜이 「구현 플랜에서 확인한다」로 남긴 열린 결정을 진행 중 질문으로 물었다. 결정 질문을 답으로 닫는 도구가 없어
(`interview_ledger.assess_answer` 는 인터뷰·플랜 경로에서만 불린다) 두 결정은 #1050 노트로 남겼다.

- T2 (질문 `f5635d8f8fb5`, 「1번으로 가자.」): 서버 확정 방식. 작성 계열은 발주 지휘자 모드, 커밋 범위는 서버가 Gitea 에서 구한다.
  워커 자기신고는 받지 않는다. 플랜 태스크 전이는 워커에게 열지 않는다.
- T3 (질문 `8d817e82de10`, 「1번으로 가자.」): 검수 도구 하나 · 기본 미리보기 · `confirm=True` + 승인 원문.
  pass 순서는 배정 「승인됨」 → 티켓 「완료」·100 → 맵 갱신 → 배정 해제이고, 다시 부르면 끝난 단계는 건너뛴다.
  작업 노드만 제출 결과가 필수다(프리필·검증은 없이도 통과).

## 변경

- T1 `86ddd76` (Codex): 노드 티켓 권한 v2 — 티켓·워커·배정 ID·만료 서명. 8101 조회·노트는 현재 실행 배정과 일치할 때만.
  배정 전이와 노트 쓰기가 `node_guard` 를 공유한다.
- T2 `7de7ef2`:
  - `issue_lock.reserve_node(family=)` 가 발주 지휘자 모드를 배정에 남긴다(codex/claude). 재작업 예약은 `rework` 표지.
    `start_node_work`·`submit_node_result` 는 현재 실행 배정·같은 워커에만 쓴다.
  - 8101 `POST /api/v1/wayfinder/issue/{id}/start`·`/submit` (노드 권한 전용). start 는 승인 플랜 판정을 통과해야 하고
    Gitea main 기준 리비전과 브랜치 `wayfinder/<Root>/n<N>` 을 기록한다(재작업은 남은 브랜치의 main 갈림점).
    submit 은 그 브랜치 끝을 Gitea 에서 읽어 `issue_infra.verify_span` 으로 해시·제목을 구한다.
  - ax-client `wayfinder_node_start`·`wayfinder_node_submit`, 워커 지시문(runner·Windows 런처 사본) 갱신.
- T3 (이 리포트와 같은 커밋):
  - `issue_lock.NODE_ACCEPTED` — 검수 통과 기록 뒤 마감·해제가 남은 상태. `finished` 는 검수 대기·승인됨에서 허용.
  - `wayfinder_dispatch.review` + MCP `ax-projects:wayfinder_review_tool`. 티켓 마감은 그 배정이 「승인됨」일 때만
    통과하는 관문을 넘겨 닫는다. 검수 도구 밖의 직접 마감은 기존 관문(#1038)이 계속 막는다.
  - 웨이파인더 스킬 §1 도구 목록·§3-6 검수 단계, 지도 배정 표시에 「검수 통과 · 마감 중」.

## 검사

작업 트리에서 `/home/sim/ax-cluster/.venv/bin/python -B`, `AX_PROJECTS_ROOT=/home/sim/ax-cluster`. 모두 rc 0.

| 검사 | 결과 |
|---|---|
| `master.test_auth` | 93/93 |
| `master.test_issue_lock` | 79/79 |
| `master.test_wayfinder` | 267/267 |
| `master.test_tagging` | 304/304 |
| `master.test_runner` | 462/462 |
| `master.test_mcp_servers` | 86/86 |
| `master.test_redmine` | 242/242 |
| `master.test_skill_conventions` | 54/54 |
| 공식 통합 `tests/integration` | 223/223 |
| `git diff --check` | rc 0 |

- `test_tagging` 의 착수·제출 11건은 실제 AX 앱과 실제 임시 git 저장소(bare + 작업 클론 push)로 돈다. Redmine 만 대역이다.
  계열 없는 배정·승인 플랜 없음·착수 전 제출·push 전 제출 거절, 자기신고 계열·해시 422, 재배정 뒤 이전 권한 403·쓰기 0.
- `test_wayfinder` 검수 14건: 실행 중 배정 거절 · 미리보기 쓰기 0 · 제출 없는 작업 노드 거절 · 마감 실패 뒤 승인됨 유지 →
  재시도 마감 → 맵 실패 뒤 배정 유지 → 재시도 해제(마감 노트 1회) · 재작업 노트·상태 → 다음 발주 후보.
- 첫 실행 실패 넷은 모두 이번 변경의 기대값·사본이었다(auth·tagging 허용 목록, runner 런처 지시문 사본, issue_lock 장부 검증의
  새 상태, mcp_servers 도구 수). 실패 장부에 기록하고 같은 검사 rc 0 으로 닫았다.

## 측정하지 않은 것

- 실제 워커(.43·.2·.33)가 AXCluster Gitea 에 `wayfinder/*` 브랜치를 push 할 권한. `.43` 체크아웃의 push 주소는 열려 있다(읽기만 확인).
- 실제 원격 지휘자(codex/claude)가 새 지시문대로 착수 → 커밋·push → 제출을 도는지. P5 실증에서 확인한다.
- Root 브랜치 통합(지도 「안개」, 사용자 의도: Root 원격 브랜치 → 코드 노드 자식 브랜치 → main)은 범위 밖이다.

최종 결과는 Redmine #1050 마감 노트.
