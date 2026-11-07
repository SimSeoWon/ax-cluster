# #905 — 운영 main과 일감 worktree 분리

## 최신 정정 산출물 — #906 Claude 인계

사용자 최종 지시로 잘못 만든 경로 모델을 제거하고 기존 config를 쓰는 작은 변경으로 다시 작성했다.
`master/issue_worktree.py`는 제거했고, `ax-projects.service`는 기준 HEAD 내용으로 돌아갔다.
현재 미커밋 변경은 `master/issue_flow.py`, `master/projects/mcp_server.py`,
`master/skills/ax-plan/SKILL.md`, 인수인계서, 이 보고서 5파일이다.

`issue_flow.default_repo()`는 기존 `resolve("AXCluster").repo`를 호출한다.
start/finish/pause/cancel의 명시 repo 인자는 그대로 우선하며, 미지정일 때만 기존 설정을 읽는다.
시작/재개 성공 응답과 마감 요약에 `repo`를 추가했다. 기존 인플레이스 로컬 일감 브랜치 흐름과
main 점유 방어는 유지했다. 새 경로·별도 경로 필드·권한 확대·배포 자동화는 추가하지 않았다.

남은 계약은 해결했다고 보고하지 않는다. 실제 `AXCluster/repo`는 origin push DISABLED이고,
설치된 `.git/hooks/pre-push`도 attempt/*·task/* 외 main push를 차단한다.
기존 main 쓰기 계약이 연결되지 않은 채 gitea-write로 바꾸거나 훅을 우회하지 않았다.
그 저장소에 있던 미추적 `graph.db`도 수정·삭제하지 않았다. 작업 브랜치와 색인 소비자의 관계까지
기존 설정·호출 계약으로 확인해야 하며 이번에는 실제 start/finish를 실행하지 않았다.

T4는 이 제약을 남긴 상태이며 #905 전체 완료가 아니다. 코드·검사·테스트·실증·커밋·push·main 반영·
서비스 설치·재기동 미실시. 초안 보관 worktree는 삭제하지 않았으며 더 이상 정식 작업 경로로 제안하지 않는다.

Codex 수행 문제는 **#906 신규·높음·마일스톤 7 - 버그/개선**으로 등록하고 되읽었다.
설정 무시·새 경로 하드코딩·금지 검사 재제안·역할 혼동·잘못된 완료 기록·같은 질문/사과 반복·절차 실패를
구체 사례로 기록했다. Claude가 수정하도록 요청한 일감이며 Codex는 그 일감을 시작하거나 닫지 않는다.

아래는 잘못 진행했던 이전 내역과 정정 과정의 기록이다. 현재 구현으로 재적용하지 않는다.

## 정정 — 기존 작업 위치 계약 대조 후 현재 수정안 적용 보류

사용자가 작업 전용 저장소의 목적과 최초부터 반복된 위치 혼동을 지적했다.
앞서 T1~T3를 구현 완료로 기록했지만, 이는 편집이 끝났다는 뜻이며 설계 확정이나 운영 적용 완료가 아니다.
현재 `ax-issues/<N>` 하드코딩 수정안과 유닛 쓰기 범위 추가는 커밋·배포 대상에서 보류한다.
변경 파일은 보존하며 자동 삭제·원복하지 않는다.

기존 계약을 #711 사용자 결정, 등록 `AXCluster/config.yaml`, 리포트82·85·88,
`master/projects/config.py`, `master/context_search/paths.py`, `master/work/subbranch.py`,
`master/work/review.py`, 실제 Git top/common-dir·remote·worktree 조회로 대조했다.
후속 RAG request는 `cd9c864a594944ceaf5f321617708a92`다. 검사·테스트는 실행하지 않았다.

| 역할 | 확인한 위치와 계약 |
|---|---|
| 운영 서비스 소스 | `.57 /home/sim/ax-cluster` — 실제 유닛 WorkingDirectory |
| AXCluster 색인용 클론 | `/home/sim/ax-cluster/AXCluster/repo` — `track.local_clone=repo`, origin push 차단, gitea-write 별도 |
| AXCluster 워커 구현 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\\trunk\\AXCluster` — 등록된 작업용 체크아웃 |
| AXCluster 요청자 | 설정 `requester: master`, #711 결정은 마스터 세션의 골조·⑦ 전진·finalize 책임 |
| 기존 통합 경로 | `review_tree_path(repo, work_id)`가 넘겨받은 repo 옆 `ax-review-<work_id>`를 계산 |
| Unreal 요청자 | `.33`의 등록된 해당 프로젝트 체크아웃. AXCluster 워커 역할·경로와 별개 |

연결 누락은 구체적이다. `master/projects/mcp_server.py`의 issue_start/finish 도구는
`issue_flow.start/finish(issue_id)`를 호출하고 프로젝트 작업 repo를 전달하지 않는다.
`master/issue_flow.py`는 `Path(__file__).resolve().parent.parent`를 기본 repo로 사용하므로
운영 코드 경로가 곧 작업 경로가 된다. 등록된 워커 경로·색인용 클론·요청자 역할과 분리되지 않는다.
`ProjectConfig.requester`는 master라는 역할만 저장하며 마스터 요청자 작업 체크아웃 경로 필드는 없다.

따라서 이번에 만든 `ax-issues/<N>`도 같은 운영 저장소를 기준으로 한 새 위치 가정일 뿐이다.
기존 저장소를 검토하기 전에 그 가정을 구현한 것이 잘못이었다. 색인용 repo를 곧바로 편집하거나
등록된 워커 저장소를 마스터 로컬 작업장으로 해석하는 것도 하지 않는다.
수정 방향은 기존 프로젝트별 요청자·워커·운영·색인 역할을 일감 흐름에 연결하는 것으로 다시 잡아야 한다.

## 결정과 범위

2026-11-08 사용자 선택은 ① 일감별 격리 worktree, 로컬 서브 에이전트 구현이다.
검사·테스트를 실행하지 말라는 지시를 적용했다. Git은 드라이런이 불가능하며 실증 테스트만
가능하다는 결정은 `/home/sim/.codex/AGENTS.md`에 저장했다. 이번 작업에서 실증은 승인되지 않았다.
커밋·push·main 반영·서비스 유닛 설치·재기동은 별도 승인이다.

근거는 Redmine #905, RAG request `caac96bb44094fb5b7228ad4b5c3b693`,
합성 문서 `issue_flow.md`·`service_freshness.md`와 실제 소스·설치된 유닛의 읽기 대조다.
설치된 oneshot 7개의 WorkingDirectory가 `/home/sim/ax-cluster`인 사실을 조회했다.
임시 Git 조건에서 나온 결과로 운영 결함을 판정하지 않았다.

## 실제 작업 위치

시작 리비전은 `63a8ddf952f57f76c4a38c88b4ec86f0ec5a4bee`다.
기존 `issue_start_tool(905)`가 만든 `issue/905`를 운영 트리에서 편집하지 않고,
운영 체크아웃을 main으로 복귀시킨 뒤 영속 worktree를 만들었다.
처음 `/home/sim/ax-issue-905`에 만들었고, 서비스 쓰기 범위를 좁히기 위해
`/home/sim/ax-issues/905`로 옮겼다. `/home/sim/ax-issues` 루트도 준비했다.
이는 실제 구현 위치 준비이며 가상 저장소를 이용한 검사가 아니다.

## 구현

- `master/issue_worktree.py`: primary worktree를 운영 경로로 해석하고 일감 경로를
  운영 저장소 옆 `ax-issues/<N>`으로 고정한다. 등록 경로·브랜치·common-dir를 대조하며
  운영 main 이외의 main 점유와 경로 충돌은 거절한다.
- `master/issue_flow.py`: start는 격리 worktree와 브랜치를 생성하고 `repo`로 편집 위치를 반환한다.
  재개·보류·취소도 운영 main을 바꾸지 않는다. 취소 시 경로와 브랜치는 기본 보존하며
  별도 브랜치 삭제 승인 시에도 경로는 detach로 보존한다.
- finish는 원격 push → 운영 main fast-forward → 일감 worktree detach 보존 → 브랜치 삭제 →
  기존 마감 추적·리뷰 연결·잠금 해제·Redmine 마감을 따른다. Git 단계 실패는 완료된 단계와
  사유를 반환하고 인프라 마감으로 진행하지 않는다. 잠금의 시작 리비전으로 범위를 유지한다.
- `master/projects/mcp_server.py`와 `master/skills/ax-plan/SKILL.md`: 실제 편집 위치와
  마감·보류·취소의 경로 보존 정책을 안내한다.
- `master/systemd/ax-projects.service`: 사용자 추가 승인으로 `ReadWritePaths=/home/sim/ax-issues`를
  소스에 추가했다. 홈 전체에 대한 쓰기 범위를 확대하지 않는다.

## 실행하지 않은 것과 다음 승인

검사·테스트·정적 분석·코드 실행·실증·커밋·push·운영 반영·서비스 설치·재기동은 하지 않았다.
읽기 대조만으로 실행 성공을 주장하지 않는다. 기존 임시 Git 검사 파일도 변경하지 않았다.
현재 서비스는 운영 main의 옛 코드를 실행하므로 새 격리 흐름이 적용됐다고 보고하지 않는다.

운영 반영 전 커밋과 마감 승인이 필요하며, 유닛 설치·재기동도 별도 승인이다.
#905는 이미 격리 작업본에서 진행 중이므로, 현재 실행 중인 옛 MCP finish를 그대로 호출하면
운영 main에서 일감 브랜치를 요구한다. 새 finish를 어떤 기존 호출로 적용할지는 승인 시
실제 모듈·서비스 상태와 함께 확정한다. 임시 스크립트나 강제 브랜치 전환으로 우회하지 않는다.

기존 제약도 남아 있다. 마감 추적 등록·잠금 해제가 끝난 뒤 Redmine 닫기만 실패하면
잠금의 시작 리비전이 없어 finish 재호출만으로 범위를 복원하지 못할 수 있다.
이번 변경은 그 인프라 재시도 계약까지 확대하지 않았다.

## 준비 중 실패 기록

초기 경로 조회에서 미확인 `systemd/`를 검색 대상으로 넣어 rc2가 발생했다. 실제 위치는
`master/systemd/`이며 사용자 재개 지시 뒤 확인된 경로로 이어갔다.
worktree 이동과 서브 에이전트의 읽기가 겹쳐 옛 cwd 생성 실패 1건이 있었다. 변경은 없었고
새 cwd에서 파일 목록을 다시 확인했다. 인수인계 패치의 문맥 오타로 적용 실패 1건이 있었으며
문서는 변경되지 않았다. 사용자 재개 지시 뒤 정확한 본문으로 다시 적용했다.
