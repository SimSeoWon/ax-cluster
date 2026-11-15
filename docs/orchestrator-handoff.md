# 현재 AX 작업 인수인계

> 2026-11-15 — 사용자 「응 맞아 근데 너 토큰 없어. 인수인계서나 작성하고 멈춰」로 중단. **main=origin/main `6a750f692213005d518319e8066ddadee2746b56`**, 작성 전 트리 깨끗. 이번 인수인계 수정만 미커밋으로 남긴다. **#966 명세 확인 답을 받았지만 단계 기록 전**, 구현·플랜·worktree 없음. #964는 마감·서비스 재시작·켜진 두 기계 배달 완료, 실제 다음 회차 관측은 미완료다.

## 바로 이어받을 #966 — 생성 체인 LLM 사용 순위만 변경

- Redmine #966 「[AX] 생성 체인을 Antigravity 우선으로 전환 — 플랜·기각 후보·레시피·직접 리뷰 생성」, 마일스톤 8 — 개선·확장, 상태 신규. `ax-redmine` 기존 MCP로 등록·되읽기 완료.
- 사용자 의도 원문: 「플랜과 리뷰에서는 코덱스을 우선으로 할 필요 없을것 같아」 → 생성 체인 전체 적용 여부에 「응」 → 「응 맞아. 단순히 LLM 사용 순위만 변경하면 좋겠어」 → 「응 코드 리뷰와 플랜 작성은 중요도가 떨어지니까 이들은 안티그래비티를 우선적으로 사용하는게 내가 원하는거야 다른 것은 없어」.
- 합의: **기존 생성 체인 순서만 codex → agy → claude 에서 agy → codex → claude로**. 새 설정·분기·정책·구조 추가 없음. 기존 파일 쿨다운·실패 폴백·자동 리뷰 큐 교차 계열 규칙·층2 검증·워커 모드 유지. 앞서 생성 체인 전체(기각 후보 포함) 적용을 승인받았다.
- 코드 정본: `master/layer2_verify.py:702` `WHY_BACKENDS`. 소비자 `master/context_synth/review_gen.py:562` `commercial_chat`의 순회. 현재 코드는 여전히 codex 우선이며 **#966 코드 편집·검사·커밋·배포는 실행하지 않았다**.
- 관련 검사: `master/test_review_gen.py:385` 부근에 codex 1순위·그다음 agy/claude를 고정한 검사 2건 및 설명이 있다. 새 순서에 맞출 대상이다. `test_llm_cooldown`의 가짜 체인 주입은 실제 기본 순서와 구분한다. 자동 리뷰 큐는 commercial_chat을 쓰지 않고 `review_runner.agy_only/codex_only` 교차 계열 선택을 쓴다.
- RAG request `c4c984a63b9f40e3bfc35c319703f2bb`, search `db850fed204d4966b471b8d5dd489c1d`. 트윈 `context/master/context_synth/plan_generator.md`·`dismissal_candidates.md` 전문과 실제 소스 대조. 후자는 #964 이전 캐시 설명이라 현재 계약으로 믿지 않았다.
- `plan_start_tool(966, project=AXCluster)` → `verdict:interview_needed`, `ok:false`, next classify. **기존 기능 수정(modify)** 분류 기록 완료 → 조사(investigate) 기록 완료. 마지막 도구 응답 `next:specify`, `next_label:명세`. 범위·분류를 처음부터 다시 묻지 않는다.
- **받은 명세 확인 답(아직 도구에 기록하지 않음)**: 지휘자 「합의한 생성 체인의 순위만 Antigravity → Codex → Claude로 변경하고, 나머지 동작은 유지. 이 문장으로 확정할까요?」에 사용자 「응 맞아 근데 너 토큰 없어. 인수인계서나 작성하고 멈춰」. 다음 세션은 이 답으로 `interview_step_tool(966, step=specify, result=위 명세, user_answer=사용자 원문)`을 기록하고 응답의 다음 단계(파급 측정)를 따른다. 이번 세션은 사용자 중단 지시에 따라 쓰지 않았다.
- 이후 파급 측정 → 스펙 영역 승인·기록 → 플랜 제안·동의·등록 → `issue_start_tool` 응답 repo에서 구현. 기능은 순위 변경 한 가지이며 요구를 늘리지 않는다. 수행 방식은 #966에서 아직 선택·파견하지 않았다(#964는 이 세션 직접 수행). 기존 스킬의 단계·승인 절차를 따른다.
- 이 문서가 미커밋이면 새 issue_start가 깨끗한 main 조건으로 거절될 수 있다. 커밋·push는 사용자 승인 범위를 확인한다. 운영 main 소스는 편집하지 않는다.

## #964 마감 · 배포 후 관측 진행 중 — 주말 배치 매시 재실행·codex 소모

- 인터뷰 완료(분류 버그 → 조사 → 명세 → 재현 → 파급 → `ax:spec`) · 플랜 v3 등록(제안→동의, 자율성 0.5, T1~T4 · 체크리스트 C1~C6). 결정 원문은 Redmine #964 노트.
- 운영 `AXCluster/config.yaml` `batch.dismissal_candidates:true`로 복귀 완료(2026-11-15 16:20, 사용자 기존 승인). 배포 전 캐시 146건은 `/tmp/ax-964-live-before.json`에 읽기 대조용으로 보존했다. 복귀 결과는 Redmine #964 노트에 기록했다.
- T1 `70c82b1`: 기계 공용 파일 쿨다운(한도 1시간·그 밖 600초·성공 해제) + commercial_chat 연결. codex 우선 순서는 유지.
- T2 `f8c1002`: 시작 시 week·started_at·complete:false 저장, 완료 시 complete:true·completed_at. 게이트는 new/resume/done. 옛 계약 테스트 2건 변경은 사용자 「응」 승인으로 수행.
- T3 `855f823`: 캐시·stale를 대상 파일 blob + input_hash 기준으로 변경. 옛 항목은 기록된 main_sha에서 blob을 읽어 재사용. 운영 읽기 대조: 146건 중 재사용111·변경13·파일없음3·미결목록밖19(LLM 0·쓰기 0).
- 검사: 전수 233/233파일 rc0, 공식 통합 `Ran 207 tests in 256.369s` OK rc0, dismissal_candidates16/16·batch69/69. 리포트 `reports/193-964-weekly-candidates-resume.md`(`5853d9a`).
- 승인: 「커밋하고 배포해 재부팅해야 되는건가?」 및 「응 진행해」. 사용자는 ‘재부팅’이 서비스 재시작을 뜻했다고 정정했다. C5는 배포 후 관측이라 마감 전 게이트에서만 제외(사용자 동의), 실제 관측 요구 유지. C1~C4·C6 충족. T4는 배포·실물까지 끝내기 전 완료로 표시하지 않는다.
- main의 이전 미커밋 인계서는 `da63a90`로 보존·push 후 일감에 병합(`e531c917`)해 fast-forward 가능하게 했다. 마감 응답: repo `/home/sim/ax-cluster/.ax-issues/964`, done `[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, registered:true·closed:true·lock_released:true·why:"". 작성 계열 `['claude','codex']`.
- wrapup 1차 rc2는 인수인계 커밋 대기. `ecfb43e` 커밋·push 뒤 2차는 재시작 대상 없음, master.client update rc1(AXCluster:deliver). 사용자 「컴퓨터 하나 꺼져있어!」를 반영해 `.43` 배달은 보류. 인수인계 갱신 `6a750f6` 커밋·push 뒤 **기존 CLI deliver/check AXCluster --host=192.168.0.2 및 .33 모두 rc0(2/2)**: payload10·스킬1종·태그AXCluster·출처 마스터 HEAD 일치. 이 도장은 `6a750f6` 기준이며 이번 미커밋 인수인계 수정은 포함하지 않는다. 전체 3/3 완료라고 하지 않는다.
- 실제 첫 개선 후 회차: `ax-batch.timer`가 **16:23:33**에 기동(수동 강제 실행 아님), 산출물 `week=2026-W45`, `started_at=2026-11-15T16:23:33`, `complete:false`, `completed_at:null`, `main_sha=6a750f692213005d518319e8066ddadee2746b56`. 인계 직전 읽기 조회 **entries179**. 앞선 중간 대조는 새 항목/갱신43건(entries172)이었고, 현재 main에서 재사용 가능한 옛 항목110건은 그대로 유지(기존 bc566f0 기준111건과 구분). 모든 항목에 도달했거나 다음 실제 회차를 관측했다는 뜻은 아니다. T4·C5 실제 다음 회차 이어받기 미확인, 완료로 올리지 않았다.
- 첫 회차는 **기존 codex 우선 순서**로 돌고 있다. #966 승인만으로 실행 중 프로세스의 순서가 바뀌지 않는다. 자동 배치·타이머를 사용자 중단 요청만으로 끄거나 프로세스를 종료하지 않았다. 다음 세션은 실제 상태를 재조회한다.
- 관측 도구: `/tmp/ax-964-batch-status.sh`는 systemctl show 타이머·서비스와 journalctl 조회만 한다. 배달은 `/tmp/ax-964-online-deliver.sh`(기존 CLI .2·.33 deliver 후 check), 관련 로그·결과는 Redmine #964 노트. 임시 파일은 정본이 아니며 없어졌으면 기존 모듈·명령 계약을 먼저 확인한다.
- 앞선 인수인계 패치 1회는 잘못된 문맥 문자로 적용 실패(파일 변경 없음). 실패를 보고하고 멈췄으며 사용자 「응!」으로 재시도 승인.
- 세션 `~/.codex/sessions/2026/11/15/rollout-2026-11-15T15-55-28-01a1ddfd-52b8-7b93-b84d-f828e5c08d9d.jsonl`. 최종 마감·배달·실물 결과의 정본은 Redmine #964 노트.

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

1. 사용자 중단 지시로 이번 세션은 인수인계 작성만 하고 멈춘다. 다음 세션은 **#966 specify 확인 답 기록부터** 이어간다. 목적·범위·분류·명세를 다시 묻지 말고 위 승인 원문과 Redmine 단계 기록을 대조한다.
2. #964 실제 배치·다음 회차 관측도 미완료다. 위 T4·C5와 Redmine 최신 노트를 대조하며 #966 구현·배포와 구분한다. 이미 받은 #964 커밋·배포·C5 처리 승인을 다시 묻지 않는다.
3. `.43`은 켜진 뒤 기존 `master.issue_wrapup 964 --project AXCluster`로 전체 배달을 다시 확인한다. 꺼진 동안에는 기존 CLI `deliver/check AXCluster --host=<켜진 기계>`를 사용한다. 다른 일감은 사용자 선택을 기다린다.
4. 확인해 둘 실물: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943) · 운영 relay에서 한도 20% 이하 제안 배너(#368) · 리뷰 큐 로그의 `리뷰 컨텍스트` 줄(#946, 첫 실물 확인됨 19:28~19:53) · 합성이 멈춘 회차의 `색인 걷기가 아직 안 지났다` 줄(#950)
