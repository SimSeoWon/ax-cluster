# 현재 AX 작업 인수인계

> 2026-11-15 오후 — **작성 기준 main `0b4969c` · #963 마감·재기동(14:14) 완료, 이 문서 커밋 직후 배달 예정 · 다음 착수 일감에서 #963 실물 확인(T8 남은 부분)**. 사용자 「다음 착수할 일감으로 실물 확인하고 963 마감 진행해」.
> 이 세션은 크래시한 세션 `3c6bcc1c` 의 #960 인터뷰를 트랜스크립트로 복원해 이어 갔다(크래시 세션의 쓰기 호출 0건 확인).
> 🔴 `.43`(BC-250) 이 `No route to host` 로 꺼져 있어 #960 배달이 남았다(사용자 「1번으로 하고 963 진행하자」). 켜지면 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.issue_wrapup 960 --project AXCluster` 와 같은 명령의 `963` 을 다시 부른다.

## 다음 — 다음 착수 일감에서 #963 실물 확인 (#963 T8 은 「작업중」으로 남아 있다)

- 사용자 선택: 확인용 일감을 따로 만들지 않고 **다음에 착수하는 일감**으로 본다. 착수 일감은 사용자가 고른다.
- 관측할 것: 인터뷰(#960) → `plan_propose`(제안 노트 `[ax:plan-proposal v=1]`) → 사용자 동의 → `plan_set(user_answer=…)` 로 v3 플랜(표지 `autonomy=` · 체크리스트 표) 등록 → 체크리스트 「미확인」 상태에서 `issue_finish` **미리보기**(`confirm=False`, 쓰기 0)가 `step: checklist` 로 멈추는 것.
- 확인되면 `ax-projects:plan_transition_tool(963, "T8", "완료", 근거)` 로 닫는다. #960 T7 은 이미 완료(#963 인터뷰로 관측).

## 직전 마감 — #963 완료 (스펙 확정과 플랜 확정 분리)

- 스펙: #960 흐름의 첫 실사용 — 분류(신규 기능) → 조사 → 명세 → 재현 건너뜀(자동) → 파급 측정 → `ax:spec` (Redmine #963 04:18~04:33Z 노트). 열린 결정 셋은 플랜 제안 전에 사용자와 정했다: 자율성 = 플랜 시작 표지 속성 · 체크리스트 충족 = 작업 중 전이 도구 · 자율성 스킬 `.33` 배달. 기능 분해 표 A~G 승인 → 태스크 T1~T8 동의 → 「직접 진행」. 작성 계열 `['claude']`.
- 도중 추가(사용자): **T9 공용 테스트 픽스처** — 「테스트 플로우를 개선하는게 근본을 고치는거지?」. `master/testkit_issue.py` 가 일감 상태를 실제 흐름(스펙 → 제안 → 동의 → 등록)으로 만든다 — 다음에 흐름 단계가 늘면 여기만 고친다. 전수 테스트 속도는 T8 에서 측정만 하고 개선은 **#965**(신규 등록, 마일스톤 8 — 개선·확장).
- 만든 것: v3 플랜(`plan_block` — `autonomy=` · 체크리스트 `C<n>` 미확인/충족/제외, v1·v2 바이트 보존) · `plan_proposal`(제안 노트 · `set_plan` 은 최신 제안과 같은 목록 + `user_answer` 일 때만 · 구조 검사 뒤에 대조) · 체크리스트 전이(충족 = 근거 · 제외 = 사유 + 사용자 답) · `plan_checklist` + `issue_infra.checklist_gate` 를 마스터 `issue_flow.finish` 와 `.33` `infra_finish` 둘 다 · `change_autonomy`(대기 태스크만 재제안) · 표면 `plan_propose`·`plan_autonomy`(ax-projects·8101 MOUNT·ax-client) · `ax-plan`·`ax-issue` 안내 · `ax-autonomy` 스킬 2벌(요청자 배달).
- 커밋: `c479fad` T1 · `b3f0dec` T9(+T2 핵심) · `7108766` T2 · `99f92ee` T3 · `4671cbc` T4 · `b495027` T5 · `02e3aab` T6 · `0d2b57a` T7 · `0b4969c` T8 고정 목록.
- 계약 변경으로 바꾼 기대값(전부 사용자 승인): `test_set_steps_v2` 「v2」→「v2 이상」 · `test_client_spec`·`test_client_bundle` 요청자 스킬 고정 목록에 `ax-autonomy`.
- 검사: 전수 232파일 12620/12620(수정 뒤) · 공식 통합 `Ran 206` OK. 전수 시간 281초 — 상위 `test_client_bundle` 48.6 · `test_review` 23.4 · `test_pystatic` 16.9(표는 #965).
- wrapup: `ax-task-queue`·`ax-broker`·`ax-projects` 14:14 재기동, 판정 깨끗. 이 커밋 직후 배달. `~/.claude/skills/ax-autonomy` 링크는 `master-local` 로 맞춘다.

## 직전 마감 — #960 완료 (착수 전 인터뷰를 Python 흐름으로 강제)

- 스펙: 2026-11-15 인터뷰로 사용자 승인(Redmine #960 03:08Z 노트 — 결정 15건 원문). 플랜 T1~T7 사용자 동의 뒤 등록, 「직접 진행」. 작성 계열 `['claude']`.
- 흐름: 일감 지정 → 플랜 영역 있으면 진행 → 없고 `ax:spec` 있으면 `plan_needed` → 둘 다 없으면 `interview_needed`. 인터뷰는 **분류 → 조사 → 명세 → 재현(분류 문서 steps 에 있을 때만) → 파급 측정 → 스펙 영역** 고정 순서이고, 단계마다 결과 제시 → 사용자 확인 → `interview_step` 노트. 진행은 노트에서만 복원한다. 새 플랜은 스펙 영역이 없으면 `set_plan` 이 거절한다(플랜이 있는 옛 일감 편집은 그대로).
- 분류 문서: `master/skills/ax-plan/reference/category-{bug,modify,feature}.md` — YAML 머리말 `name`·`label`·`steps`, 하나라도 깨지면 전체 거절. 분류 추가 = 문서 하나 추가. 본문은 응답 `guide` 로도 실린다(`.33` 도 같은 안내).
- 커밋: `1e985b4` T1 분류 문서·로더 · `a9457df` T2 `master/interview.py` · `fd43218` T3 `master/spec_block.py` · `456f921` T4 판정·재료(`master/interview_materials.py`)·`set_plan` 게이트 · `c6876be` T5 ax-projects·8101(`/api/v1/interview/step·spec`, MOUNT)·ax-client · `4b039a1` T6 ax-plan·issue-spec·checks.json · `f26093e` T6 ax-issue 요청자 스킬(사용자 승인으로 범위 포함). 선행 `5f6fc5f` 는 Antigravity 분석 문서 커밋(issue_start 깨끗한 main 조건, 사용자 선택).
- 검사: 전수 229파일 12486/12486 실패 0(AX_PROJECTS_ROOT 지정) · 공식 통합 `Ran 203` OK. T4 에서 옛 계약을 기대하던 `test_plan_start`·`test_plan_tools`·`test_issue_flow` 기대값은 사용자 승인으로 새 계약에 맞췄다. 재료 수집 실경로(#960) rag 6 · 보고서 3 · 최근 완료 10 · 실패 0.
- wrapup: `ax-task-queue`·`ax-broker`·`ax-projects` 13:15 재기동, 판정 깨끗. 이 커밋 직후 배달.
- 분리: 플랜 제안·동의 2단계와 마감 시 스펙 기반 체크리스트 → **#963**. 열린 결정으로 남긴 것: 파급 측정을 우리 환경에서 구체적으로 어떻게 할지(실사용하며 다듬기로 함).
- `master-local --check` 는 배달 뒤 실행해 결과를 Redmine 마감 노트에 덧붙인다.

## 직전 마감 — #961 완료 (‘검사 실행 안 함’ 검출 누락)

- #908 확인에서 기존 검사74/74 rc0에도 `커밋 abc1234 · 검사 실행 안 함`이 빈 경고를 반환함을 재현했다. 사용자 지시로 버그/개선 #961 등록 후 착수했다. 사용자 「검사 실행 안 함 부분을 처리하려고 추가했어」·「내가 원한건 저걸 전달받아서 수정해야 된다고 일감 추가한거야!」 — 문구 추가가 아니라 검출 누락 수정이다.
- T1 검출식·재현 회귀, T2 공식 통합·리포트·마감·배달을 제시한 뒤 사용자 「이 세션에서 직접 처리하자」. 커밋 `897a7e7`(T1) · `609c8aa`(리포트192). 다른 표현 전체 확장·새 거절 정책·#960은 범위 밖이다.
- `issue_start`의 repo `/home/sim/ax-cluster/.ax-issues/961`에서 작업했다. `issue_finish(confirm=True)` → `ok:true`, `done:[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, `registered:true`, `closed:true`, `lock_released:true`, `why:""`. 마감 추적 라운드1·2해시, 작성 계열 `['codex']`.
- 검사: `test_plan_tools` **82/82 rc0**. 공식 통합 **Ran 199 tests in 216.834s, OK, rc0**. 처음 sandbox 통합은 source_scope28/32 rc1(리포트86의 Git 그룹 권한 제약과 같은 양상); 승인된 동일 명령을 밖에서 실행해 통과했다. 코드·저장소를 권한 실패 때문에 바꾸지 않았다.
- 직접 호출 결과: 재현 입력에 기존 `[주의] 완료 근거에 「검사 실행 안 함」 … (#908)` 반환. 검사 대역을 통한 transition 응답·노트 경고, 완료 상태·근거 원문 보존도 확인했다. 실제 운영 완료 전이를 검증 목적으로 만들지는 않았다. #908 마감 이력은 Redmine #908·리포트191을 본다.
- wrapup 1차: ax-task-queue **22:22:53**, ax-projects **22:22:59** 재기동, 재기동 뒤 판정 깨끗. 인수인계 대기 rc2 뒤 문서 `cc3cdb0` 커밋·push 완료. 같은 `master.issue_wrapup 961` 재실행 **rc0**, 마운트된 AXCluster `master.client update` 배달·검사 완료, 출처 마스터 HEAD 일치. Redmine **22:24:35** 최종 노트(main `cc3cdb0935f2` · 배달 rc0), 완료·100 되읽기 확인. 이 문서의 이후 미커밋 수정은 배달 대상에 포함되지 않는다.
- 리포트 `reports/192-961-not-run-detection.md`; 세션 `~/.codex/sessions/2026/11/14/rollout-2026-11-14T21-58-14-01a1da23-141d-7523-a3eb-bf0850f55788.jsonl`.

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
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 · #383·#943·#944·#368·#946·#947·#950·#949·#911·#939·#908(도착 미확인). 최신은 각 Redmine 노트로 확인한다.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #938 등 리서치와 아이디어 부모 #952·#956(자식 #953~#955·#957~#959)은 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. 사용자 「토큰 없으니 인수인계서만 작성해줘」로 중단한다. 다음 세션은 #960의 위 의도·첫 과정 결과를 이어받아 나머지를 대화로 정한다. 목적을 처음부터 다시 묻거나 미합의 구현안·태스크를 등록하지 않는다. 다른 일감은 사용자 선택을 기다린다.
2. 사용자 「커밋하고 푸시해줘」 승인으로 이 문서를 main에 커밋·push한다. 다음 세션은 실제 HEAD·dirty를 대조한다. #961의 배달 기준은 `cc3cdb0`이며 이 추가 문서 커밋의 배달은 이번 요청 범위에 포함하지 않는다. 세션 파일은 #961 절에 기록했다.
3. 확인해 둘 실물: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943) · 운영 relay에서 한도 20% 이하 제안 배너(#368) · 리뷰 큐 로그의 `리뷰 컨텍스트` 줄(#946, 첫 실물 확인됨 19:28~19:53) · 합성이 멈춘 회차의 `색인 걷기가 아직 안 지났다` 줄(#950)
