# 222 — 웨이파인더 워커의 노드 티켓 조회와 검증 노트 (#1037)

> #1008 첫 개발 노드 · issue/1037 · 시작 0ddea4abc37a661e266eaaee792c7bb7ecb97d9d

사용자는 확정된 플랜을 워커에게 발주하고, 워커가 처리 내용·검사 결과·부족한 점·개선 필요를 같은 티켓에 직접 기록하는 흐름을 선택했다. #1037은 티켓 접근을 구현한다. 실제 배정과 파견의 연결은 #1008의 P3에서 한다.

`issue_start_tool` 응답: `ok=true`, `repo=/home/sim/ax-cluster/.ax-issues/1037`, `checkout=/home/sim/ax-cluster`, `already=false`, `lock=acquired`, 작성 계열 `codex`. `plan_transition_tool`에서 T1·T2를 작업중→완료로 기록했다.

## 구현

- T1 `895f7e2`: 마스터가 서명한 발주 권한에 티켓 번호, 작성 주체, 만료를 묶는다. 큐 인증에서 그 권한으로 허용하는 것은 해당 티켓 GET과 해당 티켓의 노트 POST 두 요청이다.
- T2 `e7798e2`: 두 라우트가 노드 표지와 실제 Redmine 부모를 대조한다. GET에서 비공개 노트는 제외한다. POST 모델은 `notes`만 받으며 서버가 서명된 워커 이름을 붙인다. 기존 요청자 Redmine 경로는 종전 계약을 쓴다.

## P3 연결 계약

마스터는 사용자 발주 요청과 승인된 계획, 선행 및 담당 범위 검사가 끝난 배정에서 `issue_node_ticket_grant(master_token, issue_id, worker, expires_at=…)`를 호출한다. 워커의 배정된 실행 환경에 결과만 `AX_NODE_TICKET_GRANT`로 주입한다. 마스터 토큰은 마스터에 둔다. 이 권한은 만료가 있는 bearer 자격이므로 로그와 작업 지시에는 싣지 않는다. 실제 발급 시점과 전달·종료 정리는 P3가 맡는다.

워커는 `wayfinder_get_node_ticket(issue_id)`와 `wayfinder_append_node_note(issue_id, notes)`를 부른다. 운영에서 P3 연결 후에는 실제 배정 한 건으로 조회 → 검사 결과 추가 → 같은 티켓에서 되읽기를 확인한다. 다른 티켓 조회는 403이어야 한다. 현 일감은 정상 HTTP 앱과 대역 Redmine으로 이 경로를 사전 검증했다.

## 검증

작업 트리에서 Python은 `/home/sim/ax-cluster/.venv/bin/python`, `AX_PROJECTS_ROOT=/home/sim/ax-cluster`를 사용했다.

| 검사 | 결과 |
|---|---|
| `-B master/test_auth.py` | rc0, 86/86 |
| `-B master/test_redmine.py` | rc0, 242/242 |
| `-B master/test_client_mcp.py` | rc0, 397/397 |
| `-u -B master/test_tagging.py` | rc0, 270/270 |
| `-B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc0, 221/221, 실패 0, 29.900초 |
| `git diff --check` | rc0 |

첫 인증 검사는 새 403 호출에 `challenge`가 빠져 rc1로 중단했다. 사용자 재개 뒤 보완하고 통과했다. 기본 샌드박스의 서버 라우트 검사는 응답 대기가 길어 승인된 `/tmp/ax-1037-checks.sh`의 서버 및 공식 통합 검사 결과를 사용했다. 실 Redmine에 시험 노트를 쓰거나 워커를 파견하지 않았다.

최종 결과는 Redmine #1037 마감 노트.
