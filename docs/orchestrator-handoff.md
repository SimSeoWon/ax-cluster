# 현재 AX 작업 인수인계

> 2026-11-08 11:00 Claude 체크포인트. 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `e9b156c`의 이 파일·리포트138~142·각 일감 노트에 있다.

## 이번 세션 결과 — #906·#893 완료, #907·#908 등록

- **#906 완료·배포** (http://192.168.0.57:8080/issues/906): main=origin/main=`e9b156c`
  (`201a81a` T1 · `f321141` main merge · `e9b156c` 문서). 근거: `reports/142-906-issue-repo-sealed-mirror.md`.
  - 일감 작업 위치 = **운영 저장소 `/home/sim/ax-cluster`**. `issue_flow._sealed()` — `origin` push URL이
    `DISABLED`인 저장소(색인 미러)면 `start`·`finish`가 브랜치·push 전에 거절한다.
  - `ax-projects` 재기동 10:30:14 KST → MCP `issue_*_tool`이 새 코드. **MCP 경로 실증은 다음 실제 일감에서**
    (이번 두 일감은 `issue_flow`를 repo 명시로 직접 호출했다).
  - 해시 리뷰 R269 지적 0 · 종합 리뷰 R270 지적 0 · 회차 닫힘. `deliver AXCluster` 3/3.
- **#893 완료·실경로 확인**: `c62b2fb`(해시 유지) main 반영 · push 2초 뒤 색인기 신호 수신 ·
  `deliver` 3/3. #906 종합 리뷰 R270이 #893 조건(해시 지적 0 · 리뷰 없는 해시 2)으로 돌아
  미검토 커밋 절이 프롬프트·노트에 실렸고 형식 1회 통과. R268-1(낮음, `None` 순회)은 오탐으로 **기각**
  (호출부 `review_gen.py:810` 한 곳이 `findings or []`).
- **#907 신규** — #905 원래 문제(운영 체크아웃 작업 중 oneshot 서비스가 미커밋 코드 실행)가 #906 복귀로
  다시 열렸다. 방식 ①worktree ②고정 배포본 ③경고 — **사용자 결정 전, 착수 안 함.**
- **#908 아이디어** — `plan_transition` 완료 근거 품질 관문(버전 「아이디어 — 추후 검토 수집」, 일감 아님).
- 정리: 색인 미러의 옛 `issue/893` 삭제(main 도달 확인 후 `branch -d`), `/home/sim/ax-issues/905` worktree 제거
  (detached `6a0a201`·변경 0 확인) — 둘 다 사용자 지시.

## #907 — 마스터 일감 worktree (Claude · 진행 중)

- http://192.168.0.57:8080/issues/907 · 플랜 T1~T3 완료, T4 진행. 근거: `reports/143-907-master-issue-worktree.md`.
- 🔴 **AXCluster(`requester: master`) 전용.** 운영 체크아웃은 늘 `main`, 일감은 `AXCluster/config.yaml`
  `master_workspace.issue_worktree_root`(`/home/sim/ax-cluster/.ax-issues`)`/<N>` worktree 에서 한다 —
  **MCP `issue_start_tool` 응답의 `repo` 가 편집 위치**다. 게임·언리얼 프로젝트는 `.33` 경로(ax-issue)이고,
  그 config 에 `master_workspace` 가 있으면 읽기 단계에서 거절된다.
- 배포 순서(리포트 143 §4): config 값 기입 → finish → `ax-projects` 재기동 → deliver → 다음 실제 일감으로 실증.
  **값 없이 재기동하면 MCP `issue_start_tool` 이 거절한다.**
- #906 MCP 실증 완료: `issue_start_tool(907)` 응답 repo=`/home/sim/ax-cluster`, 색인 미러 브랜치 없음.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소(일감 작업 위치) | `/home/sim/ax-cluster` | main=origin/main=`e9b156c` (이 문서 갱신 전 깨끗함) |
| 색인 미러(작업 위치 아님) | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · `e9b156c`=origin/main · 커서 정상 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | `e9b156c` 배달 3/3 |

- 미러는 **늘 main 끝을 따라가는 거울**이다(`consumer.py` `fetch` → `merge --ff-only`, push 봉인 PLAN §2.1).
  그 위에 브랜치를 세우면 upstream 없는 브랜치라 `FETCH_HEAD`가 전부 not-for-merge가 되고 색인기가 조용히 main을 놓친다.
- 남은 worktree `ax-788-work`·`ax-896-local`·`ax-900-local`·advance 1개는 보존. 자동 정리하지 않는다.

## Codex 관련 — 사용자 결정 2026-11-08

- Codex의 「Git 드라이런 실패」 실체: 기본 샌드박스가 `sg gitea`를 막아(`Cannot open audit interface`)
  `test_source_scope` 28/32. 리포트 86에 같은 수치로 이미 있었다. 샌드박스 밖(Claude)은 32/32.
- `~/.codex/AGENTS.md` 「Git 검증」 절을 원인·실측으로 정정했다(이후 같은 절에 「`sg gitea` 차단 시 해당 명령만
  좁혀 샌드박스 해제 승인 요청」 줄이 추가돼 있다). 사용자 결정(Git 검증은 실제 작업 실증)은 유지.
- #906 본문 1~7 대조는 리포트 142 §5. 2~3(T4 미러 연결)은 코드 강제(`_sealed`), 5는 #908로 이관.
  [주의] 1번(첫 설계 `/home/sim/ax-issues/<N>`+`ReadWritePaths`)은 **결함이 아니었다** — §5-1 정정(사용자 지적).

## 유지할 운영 상태

- 마스터 담당 기록 claude(11-07 22:44), 워커 전역 codex(state, 10-18). 이번 세션에서 변경하지 않았다.
- ax-projects active(11-08 10:30:14 기동, `e9b156c`), ax-task-queue·ax-followup.timer·ax-indexer.path·
  ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음. 분산 등재 뒤 wait 실행·⑦ 사람 게이트 전달 규칙 유지.
- #893·#896·#899~#906 완료: 리포트138~142·Redmine. 중복 마감·배포·산출물 재생성 금지.
- #894·#895·#897·#898 신규. #885는 기존 사용자 보류 기록 유지. #884 T7의 닫는 방법은 미결.
- #890 R251·R252 및 후속 리뷰 처분은 최신 목록·코드와 대조 후 사용자 결정. 상태를 자동 변경하지 않는다.
- 큐/스풀 #709·#211·#650, ax-788-work, ax-review-788 반려#821, MotionForge·NS 잔재는 보존한다.
- 관찰: 해시 지적 0이어도 미검토 해시가 있으면 종합 리뷰가 빈 「해시별 지적 판정」 절을 요구한다(#893 부수 효과).
  R270은 1회 통과 — 형식 재시도·실패가 반복되면 그때 보고.
- 미결: doc_sync 의존 등록 보강, #883 중복 플랜 제목, 훅 wait 일시오류 비대칭, 마스터 MCP 토큰 평문
  (`~/.codex/config.toml` bearer 평문 — 11-08 조사 중 출력에 노출, 외부 전송 없음).

## 바로 다음 작업

1. #907 커밋·finish·배포(리포트 143 §4 순서) — 사용자 승인 대기.
2. 배포 후 다음 실제 일감에서 `issue_start_tool` 응답 `repo`가 `/home/sim/ax-cluster/.ax-issues/<N>`이고
   운영 체크아웃이 `main`인지 확인(#907 실증).
3. 다음 일감은 사용자 선택. 커밋·push·재기동·⑦ 전진·finalize는 기존 승인 규칙을 따른다.
