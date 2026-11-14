# 현재 AX 작업 인수인계

> 2026-11-14 — #939(착수 전 인터뷰·기능 분해 표 이식 · `plan_set` `spec_missing` 경고) 마감 완료(main `bb12896`, Claude). 직전 #911 마감·배달 완료.
> 다음 일감은 사용자 선택을 기다린다. 항목·진행은 Redmine, 지난 상세는 Git 이력·리포트로 확인한다.

## 직전 마감 — #939 완료

- 승인: 「939번도 진행 … PStack처럼 상위 부모 일감 만들고, 이번에는 초반 플랜 작성 부분을 이식하는 일감을 진행하자」. 부모 아카이브 #956(아이디어) + 자식 아이디어 #957(doubt-driven)·#958(Floor Guard)·#959(context-engineering) 생성, #939 를 #956 자식·마일스톤 8 로 이동·제목 변경·본문을 스펙 템플릿으로 재작성(spec_missing `[]`). pstack 쪽은 사용자가 Antigravity 로 #952 부모·#953~#955 자식을 만들고 #911 을 연결했다.
- 사용자 결정: 범위 인터뷰 + Capability Map(3단 경계) · `plan_set` 응답 경고만 · 이 세션이 직접 · 확신도 표기 「높음·중간·낮음」. 작성 계열 `['claude']`.
- 커밋 `b196a3a`(T1: `set_plan` 응답 `spec_missing`) · `9baaf90`(T2: `docs/issue-spec.md` §4 인터뷰 · §5 기능 분해 표·3단 경계) · `faba5f7`(T3: ax-plan §2·§3 · distribute 「요청을 받으면」 3) · `bb12896`(리포트 `reports/190-939-interview-capability-map.md`).
- 검사: `test_plan_tools` 48/48 · `test_plan_start` 44/44 · `test_skill_conventions` 50/50 · 전수 225파일 11794/11794 실패 0(AX_PROJECTS_ROOT 지정) · 공식 통합 `Ran 199` OK · `master-local --check` 13/13.
- wrapup: `ax-task-queue`(21:27:38)·`ax-projects`(21:27:43) 재기동, 판정 깨끗. 재기동 뒤 #939 무변경 재등록으로 운영 `plan_set_tool` 응답 `spec_missing: []` 확인(노트 1건 추가 · 상태 보존 plan_done). 이 커밋 직후 배달.
- 안 함: 거절 게이트 · `.33` 요청자 스킬 · MCP 도구 설명문.

## 직전 마감 — #911 완료

- 승인: 「911 작업 진행하자! 아이디어에서 마일스톤 8 로 옮기고 작업 시작해줘」 → 버전 「마일스톤 8 — 개선·확장」으로 이동. 사용자 결정: 범위 템플릿+스킬+코드 검사 · **경고만**(판정 불변) · #939·#908 범위 밖 · 이 세션이 직접. 작성 계열 `['claude']`.
- 커밋 `6e46635`(T1·T2: `docs/issue-spec.md` 여섯 항목 · `plan_start.spec_missing` → `start_issue` 응답) · `9f20819`(T3: ax-plan §2·ax-redmine §5) · `734a055`(리포트 `reports/189-911-issue-spec-template.md`).
- 검사: `test_plan_start` 44/44 · `test_skill_conventions` 50/50 · 공식 통합 `Ran 199` OK · 전수 225파일 중 실패 1 = `test_sandbox`(AX_PROJECTS_ROOT 미지정, 지정 시 38/38).
- wrapup: `ax-task-queue`(20:44:41)·`ax-projects`(20:44:47) 의존 변경 재기동, 판정 깨끗. 재기동 뒤 `ax-projects:plan_start_tool(908)`·`ax-client:plan_start(911)` 응답에 `spec_missing` 실림 · verdict 불변. 이 커밋 직후 배달.
- 안 함: 기존 열린 일감 본문 소급 보강 · `.33` `ax-issue` 스킬 문구 · 거절 게이트.

## #383 에서 실제로 안 잰 것

완료·배달 완료(main `2a4b859`). 상세는 `reports/181-383-pipeline-signals-recipe-batch.md`와 Redmine 마감 노트.

- 상용 체인으로 합성이 도는 실물. 첫 회차는 마운트된 프로젝트에 신호가 1건 이상 있는 토요일 22시 이후 `ax-batch.timer`다.
- 배치는 마운트된 프로젝트만 돈다. 신호가 있는 곳은 NS(12)·ModularStage(1)이고 마운트는 AXCluster라, NS 12건은 NS가 토요일 밤에 마운트돼 있어야 합성된다.
- 실제 분산 work의 finalize로 pipeline 신호가 쌓이는 것(임시 큐의 PATCH 라우트 호출까지만 쟀다).
- 합성기는 상용 체인 실패를 「클러스터 없음」으로 접어 0을 돌려준다 — 그때도 주간 마커가 써진다. 사유는 배치 로그의 합성기 줄에만 남는다.
- 범위 밖으로 뒀던 큐 내부 rejected 히스토리 누락은 #943으로 처리했다(main `9287515`, 리포트 182).

## 이전 마감분에서 이어지는 것 (#942 `master.relay`)

- 운영 실행: `cd /home/sim/ax-cluster` → `.venv/bin/python -m master.relay` (선택: `--issue N --agent codex`). 로그 `~/ax-state/relay`.
- 긴 작업·한도 소진·중단 뒤 이어가기, 레이어 안에서 issue_start/finish 호출은 미실증.
- #941 디스코드 연동은 미착수. 본문 설계는 #942에서 확정된 방향과 대조해야 한다. 자동 시작하지 않는다.
- 2026-11-14 구 일감 정리(9건 완료 종결 · #741·#368 노트 보강)의 상세는 커밋 `c51a3af`의 이 문서와 각 Redmine 노트에 있다.

## 지휘·승인·미확인

- 마스터 마지막 담당 기록은 claude(2026-11-14 15:48:34, 사용자 지시 — #383을 수행한 Claude 세션)다. #368 인계 때 이미 claude라 재기록하지 않았다. 워커 전역 codex(state, 2026-10-18). 모드 변경 없음.
- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842).
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 · #383·#943·#944·#368·#946·#947·#950·#949·#911·#939(도착 미확인). 최신은 각 Redmine 노트로 확인한다.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #938 등 리서치와 아이디어 부모 #952·#956(자식 #953~#955·#957~#959)은 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. 다음 일감은 사용자 선택을 기다린다. 자동 시작하지 않는다.
2. 확인해 둘 실물: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943) · 운영 relay에서 한도 20% 이하 제안 배너(#368) · 리뷰 큐 로그의 `리뷰 컨텍스트` 줄(#946, 첫 실물 확인됨 19:28~19:53) · 합성이 멈춘 회차의 `색인 걷기가 아직 안 지났다` 줄(#950)
