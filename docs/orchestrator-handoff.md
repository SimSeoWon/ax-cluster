# 현재 AX 작업 인수인계

> 2026-11-08 15:30 Claude 체크포인트(#894 마감 후). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `9f7248d`의 이 파일·리포트138~146·각 일감 노트에 있다. 열린 승인·진행 중 일감은 없다.

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
- 실증 5회: #909·#912(Claude), #910(Codex 시작·커밋 → Claude 마감), #897·#894(Codex 시작·마감) — 모두
  `done=[push, ff, worktree_remove, delete_branch, register, link, release, close, redmine]`.

## 오늘 완료한 일감 (Claude, 2026-11-08)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #893 | 미검토 커밋 목록 유실 수정 — 실경로(R270)에서 동작 확인, R268-1 오탐 기각 | `c62b2fb` |
| #906 | 일감 작업 위치를 운영 저장소로 복귀 + 봉인 저장소 거절. #905 `6a0a201` 의 미러 연결이 원인 | `201a81a` |
| #907 | 마스터 일감 worktree · `master_workspace`(AXCluster 전용) — 리포트 143 | `9f7248d` |
| #909 | #893 후속 — 해시 지적 0건이면 판정 절 요구 안 함(미검토 목록은 참고 절로) | `5de2c16` |
| #910 | worktree 에서 `test_ontology`·`test_sandbox` 상시 실패 해소(Codex 구현·리포트 144) + Claude 보완 | `1f07442`·`2142338` |
| #897 | 상주 서비스 신선도를 기동 내용 해시로 판정 — Codex 구현·리포트 145, 상주 3개 재기동(12:31) | `172cea8` |
| #912 | #897 후속 — journal 조회 `-n 2` 제거(Codex 발견) · mtime 1차 거름 복원(journal 보존 ≈18시간) | `478a820` |
| #894 | 종합 리뷰 판정 칸의 마크다운 꾸밈(`` `남음` ``·`**해소**`) 인식 — Codex 단독, 리포트 146 | `c47d5b2` |

- 등록: **#908**·**#911** 아이디어(완료 근거 품질 관문 · pstack 플레이북 분석 — 일감 아님, #911 원문 링크 미기록).
- #897/#912 신선도 판정(`master/service_freshness.py`): 기동 뒤 감시 경로(.py·디렉터리, `__pycache__` 제외)에 변경 흔적이
  없으면 journal 없이 **최신**, 있으면 기동 때 journal 에 남긴 `AX_SERVICE_CODE_V1` 기록과 내용 해시로 판정. 기록이 없으면
  판정 불가(최신으로 접지 않음). 실증: 두 경로 모두 세 서비스 최신 · `master.client update` rc0 · 신선도 경고 없음.
  [주의] systemd 249 는 `journalctl -n` 을 `--grep` 보다 먼저 적용한다 — 기록 조회에 `-n` 을 붙이지 않는다.
- #910 Claude 검토(사용자 「추천대로」): Codex 리포트 주장 대조 일치. 추가 발견 ① 미커밋 Codex 세션 리포트가 finish 를
  막음 → 커밋(`reports/research/2026-11-08-910-codex-git-verification.md`, 대화 전문) ② 새 `test_sandbox` 가
  `AX_PROJECTS_ROOT` 없이 traceback → 사유 + `0/1 통과` 실패로.
- 정정(사용자 지적): 리포트 142 §5-1 — Codex 의 #905 첫 설계(`/home/sim/ax-issues/<N>`+`ReadWritePaths`)는 결함이 아니었다.
  실제 결함은 그 뒤 T4(`6a0a201`, 미러 연결) 하나였다. #906 본문 1·2번 지적은 사실과 반대였다.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`c47d5b2`(+ 이 문서 커밋), 깨끗함 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 정상 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | `c47d5b2` 배달·검사 3/3 OK |

- 상주 서비스 재기동(#897, 사용자 요청): ax-task-queue 12:31:43 · ax-broker 12:31:47 · ax-projects 12:31:57 KST — 기동 기록 정상.
  #912 는 판정하는 쪽 코드라 재기동 불필요.
- `.2` 검사에 `[주의] 홈 중복 스킬 ~/.agents/skills/ax-work`(#661 부류, 실패 아님) — 손대지 않았다.
- 남은 worktree `ax-788-work`·`ax-896-local`·`ax-900-local`·advance 1개는 보존. 자동 정리하지 않는다.

## Codex 가 알아야 할 것

- **마감 뒤 기록**: finish 결과는 Redmine 뿐 아니라 그 일감 리포트(최종 상태 절)와 이 문서에도 맞춘다 — #894 에서 빠졌다.
- **보류·재개 미실증**: worktree 방식의 `issue_pause_tool` → `issue_start_tool` 재개는 아직 실제로 돌려 보지 않았다.
- **검사 기준**: `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 주고 일감 worktree 에서 전수 — #910 이후 **실패 0 이 기준**
  (11-08 13시 #912 기준 10790/10790). 실패가 있으면 회귀로 본다. 공식 통합 목록은 `tests/integration/checks.json`.
- **샌드박스**: Codex 기본 샌드박스는 `sg gitea` 를 막아 `test_source_scope` 가 28/32 가 된다(리포트 86, `~/.codex/AGENTS.md`
  「Git 검증」 절). 원인 미확인으로 보고하지 말고, 그 명령만 좁혀 샌드박스 해제 승인을 요청한다.
- **검사 금지 지시가 있던 이유**: 11-07 Codex 의 「드라이런 실패」는 위 샌드박스 제약이었다. Git 검증은 실제 일감 실증이
  사용자 결정이다. 검사·커밋·push·재기동은 각각 승인 규칙대로.
- 테스트는 `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 준다. 전수 스크립트는 `ax-cluster/CLAUDE.md` 「Tests」 절.

## 유지할 운영 상태

- 마스터 담당 기록 claude(11-07 22:44), 워커 전역 codex(state, 10-18). Codex 가 실제 인수하면 `ax-handoff` 절차로 기록한다.
- ax-projects·ax-task-queue·ax-broker active(12:31 재기동), ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음. 분산 등재 뒤 wait 실행·⑦ 사람 게이트 전달 규칙 유지.
- #893·#894·#896·#897·#899~#907·#909·#910·#912 완료: 리포트138~146·Redmine. 중복 마감·배포·산출물 재생성 금지.
- #895·#898 신규. #885는 기존 사용자 보류 기록 유지. #884 T7의 닫는 방법은 미결.
- #890 R251·R252 및 후속 리뷰 처분은 최신 목록·코드와 대조 후 사용자 결정. 상태를 자동 변경하지 않는다.
- 큐/스풀 #709·#211·#650, ax-788-work, ax-review-788 반려#821, MotionForge·NS 잔재는 보존한다.
- 미결: doc_sync 의존 등록 보강, #883 중복 플랜 제목, 훅 wait 일시오류 비대칭, 마스터 MCP 토큰 평문
  (`~/.codex/config.toml` bearer 평문 — 11-08 조사 중 출력에 노출, 외부 전송 없음).

## 바로 다음 작업

1. `ax-handoff`로 이 문서와 실제 상태(운영 main·`.ax-issues` 비어 있음·잠금 없음)를 대조한다.
2. 다음 일감은 사용자가 고른다 — 열린 신규: #895·#898. 시작은 `issue_start_tool`, 편집은 응답 `repo`.
3. 커밋·push·재기동·⑦ 전진·finalize는 기존 승인 규칙을 따른다. 다른 일감을 자동 시작하지 않는다.
