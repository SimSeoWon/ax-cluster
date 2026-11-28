# 224 — 웨이파인더 분산 사이클 발주와 검수 인계 (#1039)

#1008의 P3다. 사용자는 웨이파인더 진행 시 단독·분산을 묻고, 분산이면 사이클마다 작업 가능한 노드의 티켓을 인터뷰로 확정해 발주하자고 했다(#1039 인터뷰 노트). 이 일감은 마스터에서 단독으로 개발했고 실제 분산 발주는 0건이다. 실제 두 워커 병렬 실행은 P4(원격 시작·마감) 뒤 P5에서 확인한다.

`issue_start_tool`: `repo=/home/sim/ax-cluster/.ax-issues/1039`, `branch=issue/1039`, `start_rev=ff988fe15be571f28038578da496951eb93bd4b2`. T1~T3는 Codex, T4 마무리는 교대 뒤 Claude가 했다(작성 계열 누적 codex·claude).

- T1 `56bc955`: 웨이파인더 스킬 §3에 단독·분산 선택을 넣었다. 분산은 작업 가능한 노드의 티켓만 준비하고, 각 티켓에서 착수 전 인터뷰로 명세·태스크·체크리스트를 확정한다. 준비는 Frontier·담당 없음을 유지하고 기존 번호를 재사용한다.
- T2 `c02c091`: `wayfinder_dispatch.preview`·`candidates` — 지도/Redmine 대조, 확정 스펙·플랜·체크리스트·선행 완료·점유를 확인해 준비된 티켓과 대기 사유를 돌려준다. 쓰기 0. 등록 워커 선택과 P2(#1038) 원자 예약.
- T3 `e065e8e`: 현재 예약의 티켓·워커에 한정한 기간 제한 권한(#1037)을 발급해 Linux SSH는 stdin, Windows 런처는 자식 환경으로 넘긴다. 권한값은 지시문·로그·응답에 남지 않는다. 기존 골조 파견의 인자 형식은 그대로다.
- T4: `dispatch_cycle` 과 MCP `wayfinder_dispatch_tool(root_id, node_ids, confirm, user_answer)`. 기본은 드라이런이고, `confirm=True` 와 사용자 발주 요청 원문이 있어야 실제 예약·실행한다. AXCluster 마운트·AXCluster Redmine 프로젝트 Root(`AX_PROJECT_NUMERIC_ID=3`)·워커 지휘자 모드 준비 검사를 통과한 등록 워커만 쓴다. 배정마다 병렬 실행하고, **종료가 확인된 배정만** `advance_node_assignment(…, to=NODE_REVIEW)` 로 검수 대기에 넘긴 뒤 같은 티켓에 검수 대기 노트를 남긴다. 종료 미확인은 `NODE_RUNNING` 점유를 유지하고, 이전 배정 ID의 신호는 P2가 거절한다.

## 중단과 재개

T4 공식 통합 검사가 11-28 00:35(KST) `test_skill_conventions` 53/54 로 실패했다. 원인은 이번 일감 T1이 쓴 `master/skills/ax-wayfinder/SKILL.md:100` 의 도구 이름에 `ax-projects:` 접두사가 빠진 것이다. Codex 세션은 토큰 소진으로 여기서 인계했고, 판정이 `resume` 인데 멈춘 경위는 #1040 에 따로 등록했다. 재개 세션에서 접두사를 붙이고 다시 검사했다. 인계 당시의 `/tmp/ax-1039-checks.sh` 는 재부팅으로 사라져 정본 명령을 직접 실행했다.

## 검사

작업 트리에서 `/home/sim/ax-cluster/.venv/bin/python -B`, `AX_PROJECTS_ROOT=/home/sim/ax-cluster`.

| 검사 | 결과 |
|---|---|
| `master/test_skill_conventions.py` | rc 0, 54/54 |
| `master/test_wayfinder.py` | rc 0, 252/252 |
| `master/test_mcp_servers.py` | rc 0, 85/85 |
| `master/test_redmine.py` | rc 0, 242/242 |
| `master/test_issue_lock.py` | rc 0, 68/68 |
| `master/test_runner.py` | rc 0, 462/462 |
| `-m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc 0, 221/221, 29.898초 |
| `git diff --check` | rc 0 |

`test_wayfinder` 의 T4 드라이런: #1039 단독 잠금을 유지한 격리 트윈에서 배정 두 건 중 종료 확인 건만 검수 대기로 넘어가고, 연결이 끊긴 건은 점유를 유지하며, 이전 배정의 늦은 종료 신호는 거절된다. 실제 워커 실행·Redmine 쓰기 0.

## P4·P5로 넘기는 것

- P4: 검수 대기 노드의 원격 시작·마감 — 검수 통과 마감에서 `to="finished"` 해제, 수정 승인 시 `NODE_REWORK` 로 같은 티켓 재예약.
- P5: 실제 등록 워커 두 대에 `wayfinder_dispatch_tool(confirm=True)` 로 발주해 병렬 실행·티켓 노트 왕복·검수 인계를 실물로 확인한다.

최종 결과는 Redmine #1039 마감 노트.
