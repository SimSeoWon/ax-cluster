# 현재 AX 작업 인수인계

> 2026-11-14 — #944(히스토리 파일명 충돌 시 기록 보존)을 main `7a40fe1`로 마감했다. Redmine 완료·100%.
> `issue_wrapup`이 의존 변경으로 판정한 `ax-task-queue`를 16:18:31 재기동했고 판정 깨끗. 이 인수인계 커밋 직후 같은 명령으로 배달·검사 예정. 최종 배달 결과는 Redmine #944 마감 노트가 정본이다.
> 항목·진행은 Redmine, 지난 상세는 Git 이력·리포트로 확인한다.

## 현재 결과 — #944 완료

- 사용자 「944 진행하자」·「응 로컬 서브 에이전트로 진행해」 승인. Codex가 `history_fix`에 구현·검사 패치 위임 후 diff·실행 결과를 직접 검증했다. 작성 계열 `['codex']`.
- `issue_start_tool`: repo `/home/sim/ax-cluster/.ax-issues/944`, checkout `/home/sim/ax-cluster`, start_rev `15cda680f1a213931815614480d48379a20135ad`. 운영 main은 편집하지 않았다(마감 후 승인된 이 문서 갱신만).
- 커밋 `c1ba57f`: `history_gen.write` 배타적 생성, 충돌 시 `_2`·`_3` 접미사. `c4ef271`: 회귀 검사. `7a40fe1`: 리포트 `reports/183-944-history-filename-collisions.md`.
- 검사: 생성·충돌34/34 · 종결29/29 · 파서47/47 · 정적 차단0(mypy 비차단4) · 공식 통합 `Ran 197 tests in 206.893s / OK` rc0. 6프로세스 동시 파일 쓰기와 검색·웹 UI 왕복 확인. 전수 검사는 별도 실행하지 않았다.
- `issue_finish(confirm=True)`: `done=[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, `registered=true`, `closed=true`, `why=""`. 리뷰 연결 「이음 0 · 큐에 없음 3」 — 리뷰 도착 미확인.
- `issue_wrapup` 1차: main=origin/main=7a40fe1 깨끗 · ax-task-queue 의존 변경 판정 → 16:02:16에서 16:18:31로 재기동(active), 재판정 깨끗. broker·projects 최신. 인수인계 대기 rc2, 배달 전. 이 커밋·push 뒤 `sh /tmp/ax-944-wrapup.sh` 재실행.
- 운영 과거 유실 건수는 미확인. journalctl의 오늘 `[history]` 조회가 출력 없이 rc1이라 중단했고, 사용자 「응」으로 미확인 유지·T2 재개 승인. 운영 트윈에 검사용 기록은 쓰지 않았다.
- 세션 `~/.codex/sessions/2026/11/14/rollout-2026-11-14T16-06-09-01a1d8e0-bb1a-7242-a57e-ed979a9f3a45.jsonl`.

## 직전 마감 — #943 완료

- 사용자 「943번 진행해」로 구현부터 마감·배달까지 승인. 구현·마감 Claude(`['claude']`). 보고서 `reports/182-943-internal-rejected-history.md`.
- 사용자 결정 셋(2026-11-14 대화): ① rejected 만 기록(cancelled 제외) ② 재작업으로 다시 열려도 라운드별로 둘 다 남긴다 ③ 과거 work 소급 없음.
- 커밋 `9287515`: `logic_cleanup._record_rejected_history`를 `_auto_cleanup_work_async` 앞에서 호출(내부 전이 네 경로 공통) · 본문에 라운드·실패 조각·사유 · 라운드당 한 번(`history_round`) · fail-soft · 라이브 큐 루트에서만 실트윈 해석. `ce2aa48`: 리포트.
- 검사: 신규 `master/test_history_terminal.py` 29/29 · 정적 차단 0 · 공식 통합 197건 OK · `master/test_*.py` 223파일 rc≠0 0개.
- `issue_finish(confirm=True)` 전 단계 완료(해시 2개 등록 · 완료 100). 리뷰 연결 「이음 0 · 큐에 없음 2」 — 리뷰 도착 미확인.
- wrapup: `ax-task-queue` 옛 코드 판정으로 재기동(16:02:16, 판정 깨끗) · 2차 실행에서 배달·검사 rc0.
- 안 잰 것: 라이브 큐에서 실제 work가 rejected로 끝나 기록이 생기는 실물(임시 큐까지만). 확인은 큐 로그의 `[history] … rejected(큐 내부 종결)` 줄.
- 일반 경로 파일명 충돌은 #944로 처리했다(위). 운영 과거 유실 건수는 미실측이다.

## #383 에서 실제로 안 잰 것

완료·배달 완료(main `2a4b859`). 상세는 `reports/181-383-pipeline-signals-recipe-batch.md`와 Redmine 마감 노트.

- 상용 체인으로 합성이 도는 실물. 첫 회차는 마운트된 프로젝트에 신호가 1건 이상 있는 토요일 22시 이후 `ax-batch.timer`다.
- 배치는 마운트된 프로젝트만 돈다. 신호가 있는 곳은 NS(12)·ModularStage(1)이고 마운트는 AXCluster라, NS 12건은 NS가 토요일 밤에 마운트돼 있어야 합성된다.
- 실제 분산 work의 finalize로 pipeline 신호가 쌓이는 것(임시 큐의 PATCH 라우트 호출까지만 쟀다).
- 합성기는 상용 체인 실패를 「클러스터 없음」으로 접어 0을 돌려준다 — 그때도 주간 마커가 써진다. 사유는 배치 로그의 합성기 줄에만 남는다.
- 범위 밖으로 뒀던 큐 내부 rejected 히스토리 누락은 #943으로 처리했다(위).

## 이전 마감분에서 이어지는 것 (#942 `master.relay`)

- 운영 실행: `cd /home/sim/ax-cluster` → `.venv/bin/python -m master.relay` (선택: `--issue N --agent codex`). 로그 `~/ax-state/relay`.
- 긴 작업·한도 소진·중단 뒤 이어가기, 레이어 안에서 issue_start/finish 호출은 미실증.
- #941 디스코드 연동은 미착수. 본문 설계는 #942에서 확정된 방향과 대조해야 한다. 자동 시작하지 않는다.
- 2026-11-14 구 일감 정리(9건 완료 종결 · #741·#368 노트 보강)의 상세는 커밋 `c51a3af`의 이 문서와 각 Redmine 노트에 있다.

## 지휘·승인·미확인

- 마스터 마지막 담당 기록은 claude(2026-11-14 15:48:34, 사용자 지시 — #383을 수행한 Claude 세션)다. 워커 전역 codex(state, 2026-10-18). 모드 변경 없음.
- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842).
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 · #383·#943·#944(도착 미확인). 최신은 각 Redmine 노트로 확인한다.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941 · #368.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #911·#938·#939 등 리서치는 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. 다음 일감은 사용자 선택을 기다린다. 자동 시작하지 않는다.
2. 확인해 둘 실물 둘: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943).
