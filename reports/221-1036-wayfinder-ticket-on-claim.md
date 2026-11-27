# 221 — 웨이파인더 일감은 선점 때 만든다 (#1036)

> 2026-11-27 · 시작 6d6ac5759ce80034c6e9a7a3b2a7c12a4ad88249 · issue/1036

## 1. 요청과 인수

사용자 원문: 「다섯 개 전부 등록하되 시작할 때 레드마인을 할당하는건 안되는거야? 한 순간에 티켓을 막 발생시킬 필요가 있는건가」 → 「이 문제 먼저 수정해」.
#1008 후속 노드 다섯은 등록 보류. 착수 전 인터뷰·스펙·플랜은 Redmine #1036이 정본이다.
이전 세션은 T1(b3fd099) 완료, T2 두 파일 미커밋·test_wayfinder 214/218에서 사용 한도로 중단했다.
사용자 「응 인수인계서 먼저 확인하고 작업 멈춘거 확인해」에는 조회만 수행했고, 「진행해줘」로 구현·검사·마감 흐름을 재개했다.

실제 대조: 운영 main 6d6ac57 깨끗함. worktree는 issue/1036, b3fd099, master/wayfinder.py·master/test_wayfinder.py 변경만 있었다.
인수인계서는 #1036 착수 전 기록이고, 중단 상세는 #1036 마지막 노트(2026-11-27T12:26:07Z)에 있었다.
plan_start 응답: verdict=resume, ok=true, tasks=[T2]. issue_start 응답 원문 주요 필드:

```json
{"ok":true,"issue_id":1036,"branch":"issue/1036","repo":"/home/sim/ax-cluster/.ax-issues/1036","checkout":"/home/sim/ax-cluster","already":true,"start_rev":"6d6ac5759ce80034c6e9a7a3b2a7c12a4ad88249","lock":"already"}
```

authors는 ['claude','codex']다. 마스터 담당 기록 claude, 워커 전역 codex(state)는 변경하지 않았다.
프로세스 조회는 실행 환경에 따라 가시성이 달라 이전 세션 종료를 확정하지 않았다. 잠금은 issue_start 응답으로 #1036 활성을 확인했다.

## 2. 변경과 근거

- T1 b3fd099: map_block가 일감 번호와 예정 키 P<n>을 받고, map_diagram이 혼합 키를 그린다.
- T2 bcf684c: 생성·등록은 지도만 쓴다. claim이 예정 노드면 일감 생성 → 선행 blocks → 지도 키 및 부모·선행 참조 치환 → 작업중으로 바꾼다.
  대조는 예정 노드의 착수 전 상태만 검사하고, 예정 node_out은 지도만 쓴다. 번호만 있는 기존 맵 검사는 _legacy로 보존했다.
  남은 네 검사를 등록 뒤 예정 키·선점 뒤 번호 흐름에 맞췄다. 새 검사의 `or True`를 제거해 쓰기 0건을 실제 판정한다.
  혼합 키의 dependents 정렬은 id_key, 선행 미리보기는 label을 사용한다.
- T3 254d334: MCP claim.node_id는 int|str, propose.deps는 list[int|str]. 도구 설명과 ax-wayfinder 개요·§2·§3·§4 및 node_out 안내를 갱신했다.

기존 등록 즉시 일감 생성은 #982 스펙의 의도된 동작이었다. 이번 작업은 사용자와 확정한 기존 기능 수정이며, 기존 동작을 버그로 재분류하지 않는다.
범위 밖: 기존 맵 이관, .33 표면(#1007), 작업자별 잠금·워커 권한·분산 브랜치 정책.

## 3. 검사

worktree에서 AX_PROJECTS_ROOT=/home/sim/ax-cluster, Python=/home/sim/ax-cluster/.venv/bin/python을 사용했다.

| 명령 | 결과 |
|---|---|
| master/test_wayfinder.py | rc0 · 226/226 |
| master/test_mcp_servers.py | rc0 · 통과83·실패0 |
| master/test_skill_conventions.py | rc0 · 54/54 |
| master/test_issue_flow.py | rc0 · 200/200(직렬화 실패 주입 경고는 검사 출력) |
| master/test_issue_infra.py | rc0 · 129/129 |
| master/test_integration_coverage.py | rc0 · 2/2 |
| -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v | rc0 · 221/221 · 실패0 · 25.162초 |
| -B -m master.sweep | rc0 · 247파일 · A/B 12837/12837 · unittest663/663 · 실패파일0 · 29.3초 |
| git diff --check | rc0 |

공식 통합·전수는 Git 그룹 권한 때문에 승인된 /tmp/ax-1036-checks.sh로 샌드박스 밖에서 실행했다.
전수의 수치 못 읽음은 test_nowork.py·test_rounds.py 둘이며 종료코드는 모두0. map_block137/137·map_diagram57/57도 전수 통과에 포함된다.

수정 전 대조: git show b3fd099:master/wayfinder.py를 메모리 모듈로 읽고 새 test_create_map_confirm을 실행했다(파일·운영 변경 없음).
rc1: `created={'pre':1001,'sav':1002}` · 「일감0·관계0」·「쓰기는 Root 하나」 등 9개 실패 후 예정 P2 조회의 AttributeError.
즉 새 검사는 등록 즉시 티켓을 만드는 종전 코드를 거절한다. 운영 실증 결과로 해석하지 않는다.

## 4. 마감 뒤 확인과 남은 지점

C3는 운영 코드 재기동 뒤에만 확인한다. 시험 Root에 선행 없는 첫 노드 둘을 등록 → 노드 티켓0 → 하나 선점 → 티켓1·대조차이0 → 시험 일감 정리.
전후 최대 일감 번호를 확인하고 #1008 대조차이0도 확인한다. 시험 일감과 지도 조작은 기존 ax-client Redmine·ax-projects wayfinder 도구만 사용한다.
마감 체크리스트는 미확인 C3가 있으면 거절한다. 마감 뒤 확인 항목을 마감 전 충족으로 기록하지 않는다. 그 순서 결정은 사용자에게 묻는다.
운영 배포·재기동·배달은 아직 미실행. #1008 다음 노드 다섯도 아직 등록하지 않았다.

세션: ~/.codex/sessions/2026/11/27/rollout-2026-11-27T21-30-20-01a21cfc-34fb-7ef2-b236-c415aebce927.jsonl
조회 경로 확인 첫 명령은 결과 없이 rc1로 중단했고, 사용자 승인 뒤 등록 스킬 직접 읽기로 재개했다. 경로 부재 오류는 없었다.

최종 결과는 Redmine #1036 마감 노트.
