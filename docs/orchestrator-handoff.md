# 현재 AX 작업 인수인계

> 2026-11-14 — #368(잔여 한도 표시와 임계치 기반 인수인계 제안) 구현·검증·리포트 커밋까지 `issue/368` worktree(`6db5ae2`)에서 완료된 뒤 Codex 한도 소진으로 멈췄다. Claude가 이어받아 `T3` 완료 전이·`issue_finish(368, confirm=True)`·`issue_wrapup 368`·배달을 마무리한다.
> 직전 #944(히스토리 파일명 충돌 시 기록 보존)는 main `7a40fe1`로 마감·배달 완료(인수인계 커밋 `174d178`).
> 항목·진행은 Redmine, 지난 상세는 Git 이력·리포트로 확인한다.

## 진행 중 체크포인트 — #368 마감 대기 (Codex 한도 소진 → Claude 인계)

- **사용자 승인**: 「응 진행해줘」 · 「로컬 서브에이전트로 진행해줘」로 #368 구현부터 마감·배달까지 승인(§1.9). Codex 한도 소진 뒤 「클로드가 이어서 작업할 수 있도록 인수인계서 작성해서 커밋하고 푸시해줘」 지시.
- **작업 위치·브랜치**: worktree `/home/sim/ax-cluster/.ax-issues/368`, 브랜치 `issue/368`, `start_rev` `174d178f77b4efb60484eff38cb3c01c285e4ed5`, 작성 계열 `['codex']`. worktree 및 운영 `main` 모두 dirty 없음.
- **완료된 커밋 (`issue/368` HEAD `6db5ae2`)**:
  - `e3c88b1`: `master/relay/quota.py`, `master/relay/agents.py`, `master/relay/store.py` — Claude `rate_limit_event` 및 Codex 세션 rollout `token_count.rate_limits` 수집·저장(T1 완료).
  - `ed6f03d`: `master/relay/console.py` — 턴 종료·`/status` 한도 표시, 기본 20% 이하(`--quota-threshold` / `AX_RELAY_QUOTA_THRESHOLD`) 인수인계 제안, 창·리셋별 중복 경고 억제(T2 완료).
  - `d514b43`: `master/test_relay.py`, `master/README.md`, `master/relay/console.py` — 회귀 검사 추가(147/147) 및 문서 갱신.
  - `6db5ae2`: `reports/184-368-relay-quota-handoff.md` — 검증 및 실제 CLI 관측 기록.
- **완료된 검증 (`T3`)**:
  - `master/test_relay.py`: 147/147 통과 (rc0).
  - 실제 CLI PONG 실증 (`/tmp/ax-368-live.sh` rc0): Claude(`f9e90703-972f-4532-9caf-b6a070fd8fe1`, 5h 23%·7d 79%) 및 Codex(`01a1d932-46e6-7292-a93d-de1a2fda4010`, 5h 29%·7d 89%) 수집·표시 확인.
  - 정적·공식 통합 (`/tmp/ax-368-checks.sh` rc0): pyflakes 5파일 차단 0 · import 4모듈 차단 0 · mypy 5파일 차단 0(비차단 26) · 공식 통합 `Ran 197 tests in 215.291s / OK` rc0.
- **Codex 세션 로그**: `~/.codex/sessions/2026/11/14/rollout-2026-11-14T16-06-09-01a1d8e0-bb1a-7242-a57e-ed979a9f3a45.jsonl`.
- **주의 (`issue_start` base 비교)**: 이 인수인계서 커밋이 `main`에 먼저 올라가므로 `main`이 `issue/368`의 `start_rev`(`174d178`)보다 1커밋 앞서게 된다. `issue_finish` 시 fast-forward 조건을 확인하고 필요 시 `issue/368`을 `main` 위로 리베이스하거나 절차를 대조해 마감한다.

## 직전 마감 — #944 완료

- 사용자 「944 진행하자」·「응 로컬 서브 에이전트로 진행해」 승인. Codex가 `history_fix`에 구현·검사 패치 위임 후 diff·실행 결과를 직접 검증했다. 작성 계열 `['codex']`.
- `issue_start_tool`: repo `/home/sim/ax-cluster/.ax-issues/944`, checkout `/home/sim/ax-cluster`, start_rev `15cda680f1a213931815614480d48379a20135ad`. 운영 main은 편집하지 않았다(마감 후 승인된 이 문서 갱신만).
- 커밋 `c1ba57f`: `history_gen.write` 배타적 생성, 충돌 시 `_2`·`_3` 접미사. `c4ef271`: 회귀 검사. `7a40fe1`: 리포트 `reports/183-944-history-filename-collisions.md`.
- 검사: 생성·충돌34/34 · 종결29/29 · 파서47/47 · 정적 차단0(mypy 비차단4) · 공식 통합 `Ran 197 tests in 206.893s / OK` rc0. 6프로세스 동시 파일 쓰기와 검색·웹 UI 왕복 확인. 전수 검사는 별도 실행하지 않았다.
- `issue_finish(confirm=True)`: `done=[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, `registered=true`, `closed=true`, `why=""`. 리뷰 연결 「이음 0 · 큐에 없음 3」 — 리뷰 도착 미확인.
- `issue_wrapup`: main=origin/main=7a40fe1 깨끗 · ax-task-queue 의존 변경 판정 → 16:02:16에서 16:18:31로 재기동(active), 재판정 깨끗. broker·projects 최신. 인수인계 커밋(`174d178`) 후 배달·검사 완료.
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
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941 · #368(마감 진행 중).
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #911·#938·#939 등 리서치는 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. **#368 마감 완결 (Claude 인계)**:
   - `/home/sim/ax-cluster/.ax-issues/368` (`issue/368`, HEAD `6db5ae2`) 상태와 Redmine #368 대조.
   - `plan_transition_tool(368, "T3", "완료", reason=...)` 전이.
   - `issue_finish_tool(368, confirm=True)` 실행 (필요 시 `main`의 이 인수인계 커밋 위로 `issue/368` 리베이스 후 실행).
   - `.venv/bin/python -m master.issue_wrapup 368` → 완료 결과를 이 인수인계서에 반영·커밋·push → `issue_wrapup 368` 재실행(`master.client update`·`check` rc0).
2. 그 다음 일감은 사용자 선택을 기다린다. 자동 시작하지 않는다.
3. 확인해 둘 실물 둘: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943).
