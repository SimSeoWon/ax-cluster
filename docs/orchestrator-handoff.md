# 현재 AX 작업 인수인계

> 2026-11-08 Claude 체크포인트. 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `6a0a201`의 이 파일·리포트138~142·각 일감 노트에 있다.

## #906 — 일감 작업 저장소 복귀 · 색인 미러 봉인 (Claude · 진행 중)

- http://192.168.0.57:8080/issues/906 · 플랜 T1~T3 완료, T4(이 문서·리포트) 진행. 잠금 활성.
- 작업 위치: **운영 저장소 `/home/sim/ax-cluster` 의 `issue/906`** — `201a81a`(T1) + main merge `f321141`.
- 결론: #905 정정 `6a0a201`이 일감 작업 위치를 **색인기의 ff 전용 미러**(`AXCluster/repo`, `track.local_clone`)로
  바꾼 것이 문제였다. 그 미러는 `origin` push가 `DISABLED://…`(PLAN §2.1), pre-push가 main을 막는 **의도된 봉인**이다.
  결과: #893 마감 push rc128 · 미러 main 추적 중단 · 미병합 커밋 색인. 근거: `reports/142-906-issue-repo-sealed-mirror.md`.
- T1: `issue_flow.default_repo()` = 운영 저장소 `REPO`. `_sealed()` — `origin` push URL이 `DISABLED`면 `start`·`finish`가
  브랜치·push 전에 거절. MCP `issue_*` 설명·`ax-plan` 스킬 정정. `test_issue_flow` 150/150, 전수 10726/10727(실패 1 =
  이 문서 형식, 재작성으로 해소 대상).
- 🔴 **배포 전 함정**: 실행 중인 `ax-projects`(MCP)는 아직 `6a0a201` 코드다 — `issue_*_tool` 을 부르면 **미러에 브랜치를
  세운다.** #906이 main에 들어가고 `ax-projects`가 재기동되기 전까지 일감 흐름은
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -c "from master import issue_flow as F; F.start(N, repo='/home/sim/ax-cluster')"`
  처럼 **repo 를 명시해** 부른다(사용자 승인 2026-11-08, #906 한정).

## #893 — 완료 (이번 세션에 마감)

- `c62b2fb`를 미러에서 운영 저장소로 **같은 해시로** 옮겨 재개·`finish(confirm=True)`: origin/main=`c62b2fb`(ff),
  마감 추적 r1(R267)·잠금 해제·완료100. 해시를 유지한 이유: 색인 커서가 `c62b2fb`였다(rebase하면 커서가 영영 조상이 못 됨).
- 신호 수신 확인: push 2초 뒤 10:23:52 `ax-indexer` 이벤트 1건 `6a0a2013→c62b2fb1` · 미러 HEAD=origin/main · 커서 일치.
- `master.client deliver AXCluster` rc0 · `.43`·`.2`·`.33` 3/3. 서비스 재기동은 #906 반영 때 함께.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소(일감 작업 위치) | `/home/sim/ax-cluster` | `issue/906` @ `f321141`, main=origin/main=`c62b2fb` |
| 색인 미러(작업 위치 아님) | `/home/sim/ax-cluster/AXCluster/repo` | main=origin/main=`c62b2fb`, 깨끗함. 옛 `issue/893` 브랜치 잔존(main에서 도달 가능) |
| 옛 #905 초안 보관 | `/home/sim/ax-issues/905` | `6a0a201` detached. 작업 위치가 아니다. 자동 삭제 안 함 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | `c62b2fb` 배달 3/3 |

- 미러는 **늘 main 끝을 따라가는 거울**이다(`consumer.py` `fetch` → `merge --ff-only`). 그 위에 브랜치를 세우면
  upstream 없는 브랜치라 `FETCH_HEAD`가 전부 not-for-merge가 되고 색인기가 조용히 main을 놓친다.
- `/home/sim/ax-788-work`·`ax-896-local`·`ax-900-local`·기존 advance worktree는 보존. 자동 정리하지 않는다.

## Codex 관련 — 사용자 결정 2026-11-08

- Codex의 「Git 드라이런 실패」 실체: 기본 샌드박스가 `sg gitea`를 막아(`Cannot open audit interface`)
  `test_source_scope` 28/32. 리포트 86에 같은 수치로 이미 있었다. 샌드박스 밖(Claude)은 32/32.
- `~/.codex/AGENTS.md` 「Git 검증」 절을 원인·실측으로 정정했다. 사용자 결정(Git 검증은 실제 작업 실증)은 유지.
- #906 본문 1~7 대조는 리포트 142 §5. 1~3은 코드 강제(`_sealed`), 5는 `plan_transition` 근거 품질 관문 —
  코드화 여부는 사용자 결정 대기.

## 유지할 운영 상태

- 마스터 담당 기록 claude(11-07 22:44), 워커 전역 codex(state, 10-18). 이번 세션에서 변경하지 않았다.
- ax-projects active(11-08 00:56:09 기동, `6a0a201` 코드), ax-task-queue·ax-followup.timer·ax-indexer.path active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음. 분산 등재 뒤 wait 실행·⑦ 사람 게이트 전달 규칙 유지.
- #899·#901~#905·#896·#900 완료: 리포트138~141·Redmine. 중복 마감·배포·산출물 재생성 금지.
- #894·#895·#897·#898 신규. #885는 기존 사용자 보류 기록 유지. #884 T7의 닫는 방법은 미결.
- #890 R251·R252 및 후속 리뷰 처분은 최신 목록·코드와 대조 후 사용자 결정. 상태를 자동 변경하지 않는다.
- 큐/스풀 #709·#211·#650, ax-788-work, ax-review-788 반려#821, MotionForge·NS 잔재는 보존한다.
- 미결: doc_sync 의존 등록 보강, #883 중복 플랜 제목, 훅 wait 일시오류 비대칭, 마스터 MCP 토큰 평문
  (`~/.codex/config.toml` 에 bearer 평문 — 11-08 조사 중 출력에 노출, 외부 전송 없음).

## 바로 다음 작업

1. #906 T4 커밋 승인 → `finish(906)` 미리보기 → 승인 시 main 반영(운영 저장소, repo 명시 호출).
2. `ax-projects` 재기동(`scripts/ax-service-restart ax-projects`, ExecMainStartTimestamp로 판정) → MCP `issue_*` 가
   운영 저장소를 쓰는지 다음 실제 일감에서 확인. `deliver AXCluster`.
3. 사용자 결정 대기: ① #905 원래 문제(운영 체크아웃 작업 중 oneshot이 미커밋 코드 실행) 별도 일감화
   ② 미러의 옛 `issue/893` 브랜치 삭제 ③ `/home/sim/ax-issues/905` 정리 ④ 완료 근거 품질 관문.
4. 다음 일감은 사용자 선택. 커밋·push·재기동·⑦ 전진·finalize는 기존 승인 규칙을 따른다.
