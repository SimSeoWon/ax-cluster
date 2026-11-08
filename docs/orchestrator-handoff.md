# 현재 AX 작업 인수인계

> 2026-11-08 12:00 Claude → Codex 인계 체크포인트. 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `9f7248d`의 이 파일·리포트138~143·각 일감 노트에 있다.
> 사용자 요청: 이 문서로 Codex 에서 이어서 진행해 본다. 열린 승인은 없다(아래 「바로 다음 작업」).

## 🔴 먼저 — 일감 작업 위치가 바뀌었다 (#907, 오늘 배포·실증)

- **AXCluster 일감은 운영 체크아웃에서 편집하지 않는다.** 운영 저장소 `/home/sim/ax-cluster` 는 서비스 10개가
  실행하는 코드라 **늘 `main`** 이다. `ax-projects:issue_start_tool(N)` 이
  `/home/sim/ax-cluster/.ax-issues/<N>` 에 `issue/<N>` worktree 를 만든다.
  **응답의 `repo` 가 편집·검사·커밋 위치**, `checkout` 은 운영 저장소(거기서 편집 금지).
- 경로는 `AXCluster/config.yaml` 의 `master_workspace.issue_worktree_root` 가 정한다 — **AXCluster(`requester: master`)
  전용**. 게임·언리얼 프로젝트는 `.33` 이 자기 worktree 에서 한다(ax-issue). 다른 프로젝트 config 에 이 절이 있으면
  읽기 단계에서 거절된다. 값이 없으면 시작이 거절된다(추정 없음).
- `finish(confirm=True)` = push → **운영 main fast-forward(= oneshot 서비스 코드 반영)** → worktree 제거 → 브랜치 삭제
  → 마감 추적·잠금 해제·완료. 상주 서비스(ax-projects·ax-task-queue·ax-broker) 재기동은 별도 승인.
- `pause` = worktree 제거(브랜치 유지), 재개 = `issue_start_tool` 이 worktree 를 다시 만든다. `cancel` 도 worktree 를 정리한다.
- 🔴 `AXCluster/repo`(`track.local_clone`)는 **색인기의 push 봉인 미러**다 — 작업 위치가 아니다(#906, 리포트 142).
  봉인 저장소·미러 안 경로는 코드가 거절한다.
- 실증: #909 를 MCP 로 시작·마감 — `done=[push, ff, worktree_remove, delete_branch, register, link, release, close, redmine]`.

## 오늘 완료한 일감 (Claude, 2026-11-08)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #893 | 미검토 커밋 목록 유실 수정 — 실경로(R270)에서 동작 확인, R268-1 오탐 기각 | `c62b2fb` |
| #906 | 일감 작업 위치를 운영 저장소로 복귀 + 봉인 저장소 거절. #905 `6a0a201` 의 미러 연결이 원인 | `201a81a` |
| #907 | 마스터 일감 worktree · `master_workspace`(AXCluster 전용) — 리포트 143 | `9f7248d` |
| #909 | #893 후속 — 해시 지적 0건이면 판정 절 요구 안 함(미검토 목록은 참고 절로) | `5de2c16` |

- 등록: **#910**(아래) · **#908** 아이디어(완료 근거 품질 관문 — 일감 아님).
- 정정(사용자 지적): 리포트 142 §5-1 — Codex 의 #905 첫 설계(`/home/sim/ax-issues/<N>`+`ReadWritePaths`)는 결함이 아니었다.
  실제 결함은 그 뒤 T4(`6a0a201`, 미러 연결) 하나였다. #906 본문 1·2번 지적은 사실과 반대였다.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`5de2c16`(+ 이 문서 커밋), 깨끗함 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음(git-ignore) |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 정상 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | `5de2c16` 배달 3/3 |

- `ax-projects` 11:43:18 KST 기동(`9f7248d` 코드 — #909 는 oneshot 리뷰 큐 쪽이라 재기동 불필요).
- 남은 worktree `ax-788-work`·`ax-896-local`·`ax-900-local`·advance 1개는 보존. 자동 정리하지 않는다.

## Codex 가 알아야 할 것

- **검사 실행**: 일감 worktree 에서 `master/test_*.py` 전수를 돌리면 `test_ontology`·`test_sandbox` 2건이 **늘 실패한다**
  (트윈 데이터 경로 가정) — #910. 그 2건만 실패면 회귀가 아니다. 운영 체크아웃에서는 통과한다.
- **샌드박스**: Codex 기본 샌드박스는 `sg gitea` 를 막아 `test_source_scope` 가 28/32 가 된다(리포트 86, `~/.codex/AGENTS.md`
  「Git 검증」 절). 원인 미확인으로 보고하지 말고, 그 명령만 좁혀 샌드박스 해제 승인을 요청한다.
- **검사 금지 지시가 있던 이유**: 11-07 Codex 의 「드라이런 실패」는 위 샌드박스 제약이었다. Git 검증은 실제 일감 실증이
  사용자 결정이다. 검사·커밋·push·재기동은 각각 승인 규칙대로.
- 테스트는 `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 준다. 전수 스크립트는 `ax-cluster/CLAUDE.md` 「Tests」 절.

## #910 — 다음 후보 (신규)

- http://192.168.0.57:8080/issues/910 — `test_ontology`·`test_sandbox` 가 일감 worktree 에서 실패.
  worktree 에는 미추적 트윈 데이터(`AXCluster/` 등)가 없다. 실패 원문은 본문에 있다. 원인은 **추정** 단계 — 코드로 확인부터.
- 이 일감 자체가 worktree 흐름의 두 번째 실증이 된다.

## 유지할 운영 상태

- 마스터 담당 기록 claude(11-07 22:44), 워커 전역 codex(state, 10-18). Codex 가 실제 인수하면 `ax-handoff` 절차로 기록한다.
- ax-projects active(11:43:18), ax-task-queue·ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음. 분산 등재 뒤 wait 실행·⑦ 사람 게이트 전달 규칙 유지.
- #893·#896·#899~#907·#909 완료: 리포트138~143·Redmine. 중복 마감·배포·산출물 재생성 금지.
- #894·#895·#897·#898·#910 신규. #885는 기존 사용자 보류 기록 유지. #884 T7의 닫는 방법은 미결.
- #890 R251·R252 및 후속 리뷰 처분은 최신 목록·코드와 대조 후 사용자 결정. 상태를 자동 변경하지 않는다.
- 큐/스풀 #709·#211·#650, ax-788-work, ax-review-788 반려#821, MotionForge·NS 잔재는 보존한다.
- 미결: doc_sync 의존 등록 보강, #883 중복 플랜 제목, 훅 wait 일시오류 비대칭, 마스터 MCP 토큰 평문
  (`~/.codex/config.toml` bearer 평문 — 11-08 조사 중 출력에 노출, 외부 전송 없음).

## 바로 다음 작업

1. `ax-handoff` 로 이 문서와 실제 상태(운영 main·`.ax-issues` 비어 있음·잠금 없음)를 대조한다.
2. 사용자가 고른 일감을 `ax-plan` 으로 진행한다 — 후보 #910. 시작은 `issue_start_tool`, 편집은 응답 `repo`(worktree).
3. 커밋·push·재기동·⑦ 전진·finalize는 기존 승인 규칙을 따른다.
