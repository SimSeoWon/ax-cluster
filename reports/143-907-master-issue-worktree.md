# 143 — #907 마스터 일감 worktree · `master_workspace` (AXCluster 전용)

2026-11-08 · Claude · 일감 http://192.168.0.57:8080/issues/907 (연관 #905·#906)

## 1. 문제와 범위

AX 서비스 10개가 `WorkingDirectory=/home/sim/ax-cluster` 에서 `python -m master.…` 로 돌아 **작업 트리의 코드**를
읽는다. 일감을 그 운영 체크아웃에서 작업하면 1분 주기 oneshot(ax-followup 등)이 **미커밋 코드**를 실행한다(#905 실측).

🔴 **AXCluster 한정 문제다** — 마스터가 요청자(`requester: master`)이고 작업 대상 소스가 곧 마스터 서비스 코드인
프로젝트는 AXCluster 뿐이다. 게임·언리얼 프로젝트는 `.33` 이 자기 worktree 에서 작업하고(ax-issue) 마스터
서비스가 그 소스를 실행하지 않는다. 사용자 지적(2026-11-08): *"언리얼 전용 프로젝트는 .33 에서 작업하니 저
경로를 오인하면 오동작"* — 그래서 범위를 문서가 아니라 **코드로** 묶었다.

배경 정정: 사용자는 `AXCluster/repo` 를 작업 공간으로 알고 있었다. 실제로는 색인기의 push 봉인 미러이고
(리포트 142), 마스터용 작업 공간 항목은 config 에 **없었다** — 이번에 처음 만든다.

## 2. 결정 (사용자 2026-11-08)

- 방식 ① 일감마다 worktree · 위치 `/home/sim/ax-cluster/.ax-issues/<N>`(git-ignore, 유닛 변경 불필요 — `ax-projects` 는
  `ProtectSystem=strict`·`ReadWritePaths=/home/sim/ax-cluster`) · 경로는 config 에 명시 · 구현은 이 세션.

## 3. 한 것

| 대상 | 내용 | 검사 |
|---|---|---|
| `master/projects/config.py` | `master_workspace.issue_worktree_root` → `ProjectConfig.master_issue_worktree_root`. `requester: master` 가 아니면 **읽기 단계 ConfigError**, 상대 경로·비매핑 거절, 절 없으면 빈 값(추정 없음), `to_yaml` 왕복 | `test_projects` 신규 7 |
| `master/issue_flow.py` | `_workspace()`: 운영 호출(repo 미지정)은 config 값으로 worktree 방식 — requester≠master·kind=unreal·값 없음·색인 미러 안이면 거절. start/재개 = `worktree add`(운영 main 유지, 응답 `repo`=worktree·`checkout`=운영), finish = push → 운영 main `merge --ff-only` → worktree 제거 → `branch -d`, pause = worktree 제거(브랜치 유지), cancel = worktree 제거. repo 명시 호출은 종전 인플레이스 | `test_issue_flow` 173/173(신규 23) |
| `master/client/bundle.py` | 변경 없음 — `config_for` 가 화이트리스트라 실릴 길이 없음을 확인 | 회귀 검사 2(worker·requester 배달물에 키·경로 없음) |
| 문서 | `ax-plan` 3-1·3-2, MCP `issue_*` 설명 — 「AXCluster 전용 · 응답 repo=worktree · 게임은 `.33`」 | `test_skill_conventions` 41/41 |
| `.gitignore` | `/.ax-issues/` | — |

부트스트랩: #907 자체는 이전 방식으로 시작됐으므로(운영 체크아웃 `issue/907`) 편집·검사는 별도
`/home/sim/ax-907-dev` worktree 에서 하고 커밋 때만 운영 쪽에 반영했다 — 작업 중 미커밋 코드가 서비스에
실리지 않게.

## 4. 배포 절차 (승인 후)

1. `AXCluster/config.yaml`(미추적 운영 데이터)에 `master_workspace: {issue_worktree_root: /home/sim/ax-cluster/.ax-issues}`.
   **이 값이 없으면 배포 직후 MCP `issue_start_tool` 이 거절한다** — 그래서 재기동 전에 넣는다.
2. #907 finish → `ax-projects` 재기동(`ExecMainStartTimestamp` 판정) → `deliver AXCluster`.
3. 실증: 다음 실제 일감의 `issue_start_tool` 응답 `repo` 가 `.ax-issues/<N>` 이고 운영 체크아웃이 `main` 인지.

## 5. 남은 것

- `kind=unreal` 거절 분기는 프로필 의존이라 단위 검사가 없다(requester 판정이 먼저 막는다).
- 상주 서비스(ax-projects·ax-task-queue·ax-broker)는 finish 의 ff 뒤에도 재기동 전까지 옛 코드다 — 종전과 같다.
