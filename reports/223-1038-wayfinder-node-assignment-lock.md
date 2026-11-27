# 223 — 웨이파인더 노드와 워커 배정 잠금 (#1038)

사용자는 #1008의 P2를 먼저 진행하라고 했다. Redmine 계정은 집에서 하나만 쓰므로 워커는 서버 배정으로 구분하고, 첫 버전은 한 워커가 한 노드만 실행하도록 정했다. 실행이 끝난 워커는 다른 노드에 배정할 수 있다. 결과를 반환한 노드는 검수까지 계속 보호한다.

`issue_start_tool`: `ok=true`, `repo=/home/sim/ax-cluster/.ax-issues/1038`, `branch=issue/1038`, `lock=acquired`, `start_rev=e707a28d6f93ad7eee3039e75acd18a68cfbd13b`.

- T1 `7c4fe88`: 프로젝트 트윈의 기존 `issue_lock.json`과 `flock`을 공유한다. 노드·워커 예약을 같은 임계 구역에서 판정한다. 노드당 한 계약, 워커당 실행 중인 한 노드다. 기존 잠금 형식은 그대로 읽는다. 확인된 종료는 검수 대기로, 승인된 수정은 재작업 대기로 옮긴다. 재배정마다 새 배정 ID를 발급해 이전 실행의 늦은 신호를 거절한다.
- T2 `44480a0`: 지도 상태 조회의 `assignments`에서 실제 워커와 실행·검수·재작업 상태를 보여 준다. 분산 배정된 노드는 단독 지도 선점·일감 시작·플랜 작업중 전이·Redmine 직접 완료·지도 범위 밖 이동을 거절한다. 기존 단독 활성 한 칸은 유지한다. 지도 조회는 Redmine 본문과 담당자 필드를 쓰지 않는다.

## P3·P4 연결

P3는 승인된 플랜, 노드 소속·선행·담당 범위, 등록 워커를 검증하고 동일 AXCluster 트윈에서 `reserve_node(lock_root, issue_id, root_id=…, worker=…)`를 호출한다. 성공한 현재 배정에 #1037 권한을 발행하고 파견한다. 실행 종료를 확인한 마스터가 `advance_node_assignment(…, assignment_id=…, to=NODE_REVIEW, by=…, why=…)`를 호출한다. 종료 확인이 어려우면 기존 점유를 유지한다. 한도 초과와 경쟁 실패는 파견으로 이어지지 않아야 한다.

P4는 검수 및 이에 연결되는 원격 시작·마감 표면을 맡는다. 수정 승인 뒤에는 `NODE_REWORK`로 옮겨 같은 티켓을 다시 예약할 수 있다. 검수 통과 마감에서는 보호를 우회할 권한을 승인된 마감 호출과 현재 배정으로 제한하고, 마감을 확인한 뒤 `to="finished"`로 기록을 해제한다. P2는 발주·SSH 연결이나 마감 관문의 예외를 열지 않았다.

## 검사

작업 트리에서 `/home/sim/ax-cluster/.venv/bin/python -B`를 사용했다. `AX_PROJECTS_ROOT=/home/sim/ax-cluster`.

| 검사 | 결과 |
|---|---|
| `master/test_issue_lock.py` | rc 0, 68/68 |
| `master/test_wayfinder.py` | rc 0, 233/233 |
| `master/test_issue_infra.py`, `master/test_plan_tools.py` | rc 0, 각각 129/129와 107/107 |
| `master/test_redmine_completion_gate.py`, `master/test_mcp_servers.py` | rc 0, 각각 49/49와 83/83 |
| `-m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc 0, 221/221, 실패 0, 30.080초 |
| `git diff --check` | rc 0 |

공식 통합은 승인된 `/tmp/ax-1038-checks.sh`로 Git 그룹 권한이 있는 환경에서 실행했다. 두 노드·두 워커 배정과 동일 노드·동일 워커 경쟁, 검수 대기, 재배정, 늦은 종료 신호, 지도 및 직접 닫기 차단을 검사했다. 실제 워커의 명령 실행과 Redmine 파견 노트 왕복은 P3·P4 연결 뒤 P5에서 확인한다.

최종 결과는 Redmine #1038 마감 노트.
