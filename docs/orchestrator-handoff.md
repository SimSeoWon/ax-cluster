# 현재 AX 작업 인수인계

> 2026-11-15 16:58 — **#966 마감 완료**(main `9e31a2a`, 완료·100). `ax-task-queue` 16:57:54 · `ax-projects` 16:57:59 재기동, 재판정 깨끗. 이 문서 커밋·push 뒤 wrapup 재실행으로 배달한다(`.43` 꺼짐 — 켜진 `.2`·`.33`만). #964·#966 의 배포 후 관측(C6)이 남았다.

## #966 마감 — 생성 체인 agy 1순위 · 배포 후 관측 남음

- 사용자 의도: 「코드 리뷰와 플랜 작성은 중요도가 떨어지니까 … 안티그래비티를 우선적으로 … 다른 것은 없어」. `WHY_BACKENDS` 를 **agy → codex → claude** 로 바꾼 것뿐이다(쿨다운·폴백·리뷰 큐 교차 계열·층2 `BACKENDS`·본문 레인·워커 모드 불변).
- 인터뷰 분류 modify → 조사 → 명세 → 재현 건너뜀 → 파급 → `ax:spec`. 플랜 v3 T1·T2 · C1~C6 · 자율성 0.5. 수행은 이 Claude 세션 직접(작성 계열 `['claude']`).
- 커밋: `58808bb`(앞 세션 인계서 보존 — issue_start 깨끗한 main 조건) · `9655bc5` T1 · `9e31a2a` 리포트 `reports/194-966-generation-chain-agy-first.md`.
- 파급 측정을 틀렸다: 기본 순서를 기대값으로 고정한 검사 6건(`test_llm_cooldown:107` · `test_usage_cli_paths` 5건)을 놓쳤고 실행이 잡았다. 사용자 승인(A안)으로 기대값을 agy 로 맞췄다. 정정 노트 Redmine #966.
- 검사: 전수 233파일 rc0 12107/12107 · 공식 통합 `Ran 207` OK.
- 체크리스트: C1~C4 충족 · **C5·C6 마감 전 게이트에서만 제외**(사용자 「응 제외로 기록하고 마감까지 진행해」, 요구는 유지).
- 마감: done `[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]` · closed · lock_released.
- **C6 관측(#964 C5 겸함, 결과는 #964·#966 양쪽 노트)**: ① 16:23:33 시작 `ax-batch` 회차(2026-W45 · 그 프로세스는 옛 codex 우선 코드로 끝까지 돈다)가 `complete:true` 로 끝나는지 ② 다음 회차가 완료 주차를 재생성하지 않는지(게이트 done·LLM 0) ③ 새 생성 호출이 있으면 `[agy]` 가 먼저 시도되는지. C5 근거(재기동 판정·배달)는 wrapup 결과 노트로.

## #964 마감 · 배포 후 관측 진행 중 — 주말 배치 매시 재실행·codex 소모

- 마감·배포 완료(main `e531c917` 이후), 상세는 리포트 `reports/193-964-weekly-candidates-resume.md` 와 Redmine #964 노트. 운영 `batch.dismissal_candidates:true` 복귀 완료.
- 남은 것은 T4·C5 실제 다음 회차 관측뿐 — 위 #966 C6 로 함께 본다. 이미 받은 커밋·배포·C5 처리 승인을 다시 묻지 않는다.
- 16:38 기준 `ax-batch.service` activating(16:23:33 시작), 로그에 `[layer2] [codex]` 호출이 이어졌다. 관측 도구 `/tmp/ax-964-batch-status.sh`(조회만) · 배포 전 캐시 `/tmp/ax-964-live-before.json` — 임시 파일이며 정본이 아니다.

## 그 밖에 남은 것

- `.43` 꺼짐(No route to host) — 켜지면 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.issue_wrapup 960 --project AXCluster` 와 `963` 을 다시 실행(배달·노트).
- #965 전수 테스트 속도 개선(신규, 기준선 232파일 281초) — 착수 때 인터뷰.
- #963 T8 은 #964 에서 실물 관측으로 완료(제안→동의→v3 등록→마감 미리보기 `step: checklist` 멈춤).

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

- 마스터 마지막 담당 기록은 claude(2026-11-14 15:48:34)다. 2026-11-15 #966 을 Claude 세션이 이어받아 마감했고, 기록이 이미 claude 라 재기록하지 않았다. 워커 전역 codex(state, 2026-10-18). 모드 변경 없음.
- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842).
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 · #383·#943·#944·#368·#946·#947·#950·#949·#911·#939·#908·#964·#966(도착 미확인). 최신은 각 Redmine 노트로 확인한다.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #938 등 리서치와 아이디어 부모 #952·#956(자식 #953~#955·#957~#959)은 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. 이 문서 커밋·push 뒤 `master.issue_wrapup 966 --project AXCluster` 재실행 → 배달. `.43` 꺼져 있으면 rc1 이 정상이고, 켜진 기계는 기존 CLI `deliver/check AXCluster --host=<켜진 기계>` 로 맞춘다. 결과를 #966 노트(C5 근거)로 남긴다.
2. #964·#966 배포 후 관측(위 C6 ①②③). 자동 배치·타이머를 끄지 않는다.
3. `.43` 이 켜지면 `master.issue_wrapup 960`·`963`·`964`·`966 --project AXCluster` 재실행(배달·노트).
4. 확인해 둘 실물: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943) · 운영 relay에서 한도 20% 이하 제안 배너(#368) · 합성이 멈춘 회차의 `색인 걷기가 아직 안 지났다` 줄(#950). 다른 일감은 사용자 선택을 기다린다.
