# master

192.168.0.57(리눅스 인프라 컴퓨터)에서 돌아갈 오케스트레이션 코드가 여기 들어간다.

AXCluster의 통합 검사는 `tests/integration/checks.json`의 명시 목록을
`master/integration_checks.py`로 별도 프로세스에서 실행하고 종료 코드·실행 건수를 대조한다.
실행: `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`.
[중요] 공식 목록은 ⑦ 이 검사 트리(격리 worktree)에서 그대로 돈다 — **사실상 전수**다(`#815` ⑥, 2026-10-18). 빠지는 것은 건수를 찍지 않는 테스트와 `followup.MASTER_ENV_TESTS`(마스터 실 배치·트윈을 보는 검사 — 커밋 전 전수가 돈다)뿐이다. [주의] 새 테스트는 「격리 worktree · 빈 `AX_PROJECTS_ROOT`」에서 통과해야 공식 목록에 들어간다 — 실 레지스트리·고정 경로를 읽으면 검사 트리에서 항상 실패한다.
`test_indexer.py`는 Git·색인·문서 합성기를 주입해 실제 브로커에 의존하지 않는다.
Windows Codex 준비 검사는 예약 작업의 정적 등록을 검증하며 실제 도구 실행은 별도 실증이다.
변경·검사·배포 근거: [리포트 89](../reports/89-codex-worker-readiness-and-write-probes.md)·
[리포트 90](../reports/90-r5-indexer-test-isolation-and-deployment.md).

마스터 세션을 이어받을 때는 [`ax-handoff`](skills/ax-handoff/SKILL.md)로 인수인계와 실제 상태,
기존 승인 범위를 대조한다. 워커 지휘자 선택은 [`ax-mode`](skills/ax-mode/SKILL.md)를 사용한다.
MCP가 없으면 같은 정본 `work.conductor.snapshot()`·`set_worker()`를 호출하며, 준비 검사를
건너뛰는 `mode.set_mode()` 직접 호출은 운영 전환에 쓰지 않는다. 전역 모드는 새 work 등재의
기본값이고 기존 work와 후속 라운드는 저장된 `worker_mode`를 유지한다.
현재 담당·모드·검증·관련 일감 상태는 [인수인계서](../docs/orchestrator-handoff.md)에서 확인한다.
인수인계서 갱신도 `ax-handoff`의 기존 절차를 따른다. 인프라 조사·위임·배달은
[`distribute`](skills/distribute/SKILL.md)를 사용하며, 호출 방법이 불명확하면 먼저 사용자에게 묻는다.

## 지금 있는 것

[중요] **이 표가 모듈 설명의 SSOT 다** — 저장소 루트 `CLAUDE.md` 가 *"표는 여기 두지 않는다"* 며
이리로 보낸다. 새 모듈을 만들면 **여기에 행을 추가한다.** [중요] **기준일을 적지 않는다** —
「2026-08-09 기준」이라 적어 뒀더니 닷새 뒤에도 그 상태로 남아 신규 6종을 통째로 몰랐다
(리포트 12 §11 에 같은 사고가 이미 있었다: *"README 가 오늘 만든 것을 통째로 모르고 있었다"*).

| 파일 | 내용 |
|---|---|
| `doc_sync/` | 등록 운영 문서 최신화(`#838`). `plan`은 문서·정본·근거를 읽기 전용으로 수집하고, `draft`는 기존 계측 LLM 경로로 인용·diff가 있는 수정안을 저장한다. `apply`는 현재 입력 재검증 후 승인 ID만 적용한다. CLAUDE·AGENTS 보호·심볼릭 링크·반복 적용을 검사한다. `python -m master.doc_sync plan\|draft\|apply`(기본 등록목록 `docs/document-registry.json`). `plan`·`draft`는 `--id`(반복 지정 가능)와 영향 문서 탐지 범위인 `--since`·`--until`을 받는다. `--since` 지정 시 `--until`의 기본값은 HEAD다. `draft`는 `--project`(사용량을 기록할 마운트된 프로젝트)와 `--out`을 받는다. `--out`은 아직 없는 파일이어야 하고 등록목록·문서·근거 파일을 덮을 수 없다. 레인은 `--lane codex\|claude`이며 자동 폴백은 없다. 응답을 해석하지 못하면 원문을 `<out>.raw.txt`에 남긴다. `apply`는 `--confirm`·`--approve <id>`가 없으면 미리보기만 하고, 보호 문서에는 `--allow-protected`가 필요하다. LLM은 파일을 쓰지 않으며 자동 커밋·배포·서비스 재기동은 없다. [사용법](../docs/document-sync.md) |
| `skills/ax-handoff/SKILL.md` | 마스터 인수인계 복원·실제 상태/승인 대조·마스터 담당과 워커 모드 구분. Claude/Codex 홈은 같은 정본을 참조 |
| `skills/ax-mode/SKILL.md` | 워커 지휘자 선택. MCP와 동일한 준비 검사·저장·재조회 호출을 사용 |
| `work/mode.py` | `lane`/`claude`/`codex` 저장값과 실제 선택 출처 관리. 명시 인자·환경변수가 저장값보다 우선 |
| `work/conductor.py` | 담당 기록·상태 조회·워커 준비 검사 후 모드 저장. 담당 기록은 프로세스 생존 판정이나 잠금이 아님 |
| `verdict.py` | **층2 판정 계약 (fail-closed).** `contract_text()` 로 프롬프트에 계약을 붙이고 `parse_verdict()` 로 읽는다. **모든 실패 경로가 차단으로 떨어진다** |
| `layer2_verify.py` | 층2 검증기 — UE5/C++ 문법 프롬프트 + 백엔드 체인(`agy` → `claude`). `verify_files([(경로, 내용)])` · `workdir=`(`#825`): 고정 SHA 작업 트리를 직접 읽게 한다(codex `-s read-only -C` · agy 두 번째 `--add-dir` · claude `--tools Read,Grep,Glob`). agy 생성·검증은 공용 `run_agy`의 명시 모델 정책을 따른다(`#830`) · [주의] 계약 끝 *"or violate the spec"* 때문에 **claude 는 `[PSEUDO]` 위반을 막고 agy 는 안 막는다**(`#815` ④ 실측 2/3 · 0/2) — 백엔드에 따라 갈린다(처리 결정 대기) |
| `agy_models.py` | agy 공용 모델 정책(`#830`) — 기본 `gemini-3.8-flash-medium`, 자동 Argon 제외. canonical 모델 목록 사전 검사·호출별 실제 모델 로그 대조·모델별 지속 쿨다운. 사용자 명시 모델과 `allow_argon=True`가 함께 있어야 Argon 수동 호출 가능. 상태는 `AX_PROJECTS_ROOT/.ax/agy/models.json`(시험용 `AX_AGY_STATE_PATH` 우선). 요청 모델·실제 모델·확인 출처를 사용량에 남긴다. 기본 내부 폴백은 없으며 다른 계열을 자동 추가하지 않는다 |
| `test_*.py` | **테스트는 저장소 루트 `CLAUDE.md` 의 세는 법을 따른다.** pytest 불필요 — 각 파일을 그대로 실행한다. 목록은 저장소 루트 `CLAUDE.md` 참조 |
| `task_queue/` | **잡 분배 큐** (AgentTest `mcp/task_queue/` 이식, 2,717줄). HTTP 서비스 + MCP stdio |
| `task_queue/tagging.py` | [중요] **요청 태그 정책의 정본** (`#257`·`#258`, 2026-08-22) — 35개 라우트에 4정책(`OPEN`/`TAG`/`MOUNT`/`STAMP`). **선언 없는 라우트가 생기면 `test_tagging.py` 가 깨진다** — 엔드포인트마다 `if` 를 뿌리면 다음 것이 빠지기 때문이고, `#243` 이 시소러스 둘만 배선하고 `signals`·`history`·`claim` 을 남긴 사고가 그 실측이다. [중요] **`MOUNT`(마운트와 대조, 태그 없음도 거절)와 `STAMP`(work 스탬프로 판정, 대조만)를 가르는 것이 핵심** — `STAMP` 에 마운트를 강제하면 `#210`(미종결 work 는 원래 프로젝트로)을 깨뜨린다. 거절 사유 셋(`no_project_tag`·`not_mounted`·`project_mismatch`)은 **고칠 곳이 다르기 때문**에 가른 것이고, 형태는 전부 **200 + `ok:false`**(§12.5-c: 4xx/5xx 는 `ax-client` 가 [미연결]로 읽어 낡은 스냅샷을 정답처럼 돌려준다) |
| `systemd/*.service` | [주의] **저장소 사본이 정본이다 — 실물을 손으로 고치지 말 것.** 실측 2026-08-22: 실물에만 3줄 더 있었고(`AX_PROJECTS_ROOT` 포함) 다음 배포가 그것을 되돌린다. `test_sandbox.py` 가 **사본==실물**을 잰다. 그리고 유닛에 **프로젝트 이름을 박지 않는다**(`#276`) — 박혀 있던 동안 시소러스 대행이 처음부터 500 이었다 |
| `auth.py` | [중요] **공용 인증 — 공유 베어러 토큰, fail-closed.** [주의] **뷰 경로(`/view/`)는 기본 공개다** — 조작 불가능한 읽기 전용 화면에 토큰을 요구하면 안 쓰이게 된다(사용자 결정). 잠그려면 `AX_VIEW_REQUIRE_TOKEN=1` + `init-view`. 세 서비스가 같은 ASGI 미들웨어를 쓴다. 토큰이 없거나 약하거나 파일 권한이 열려 있으면 **서비스가 뜨지 않는다**. 열린 경로는 `/livez` 하나 |
| `layer3_verify.py` | **층3 판정 계약 (fail-closed).** UE5 자동화 로그(`Result={Success\|Fail}` + `TEST COMPLETE. EXIT CODE:`)와 UBT 빌드 로그(`Result: Succeeded\|Failed`)를 각각 파싱한다. [중요] **프로세스 반환 코드를 읽지 않는다** — 실측에서 거짓 실패·거짓 성공이 둘 다 나왔다 |
| `broker/` | **추론 브로커** (Ollama API 호환). [완료] **가동 중** — `ax-broker.service` `:8102` |
| `projects/` | **프로젝트 레지스트리 MCP** — 등록·마운트 전환 + **워크숍 체크아웃**(경로·`driven`) + 더티 체크. [완료] **가동 중** — `ax-projects.service` `:8103`. 도구 수는 `master/test_mcp_servers.py` 가 고정한다(세지 말고 거기서 읽는다) + `role`(worker/requester). 등록 뒤 남은 단계는 `projects/onboard.py`(`python -m master.projects.onboard <P>` — 계획, `--confirm` 실행, `#259`·`#227`) |
| `events/` | 이벤트 스풀 + **색인기**. Gitea `post-receive` → 스풀 → `ax-indexer.path`(inotify) → 재색인. [중요] 폴링 아님 |
| `provision.py` | Ollama 노드 **점검·원격 설치**. [중요] `.33`(메인 작업 PC)은 `resident=False` — 상주시키지 않는다. [주의] 실제는 2026-10-03 승인으로 `gemma4:e4b` 가 상주한다 — 코드와의 불일치는 `#753`. `python -m master.provision check` |
| `work/` | 워크플로우 — 정본 7단계(사용자 확정 2026-09-02). 골조는 **요청자가** 작업 브랜치 `task/<work>/base` 에 커밋하고(UHT 게이트), 마스터는 **분해 → 조각마다 서브 브랜치(`task/<work>/<조각>`, 라운드 N 은 `task/<work>/r<N>/<조각>`) → 파견**, 워커가 **자기 서브 브랜치에 커밋**하고, 요청자가 ⑺ 에서 머지·전진한다. 도메인 규범(`norms.py`) · 헤더 선언(`declarations.py`). [주의] 「쓰는 주체는 서버 하나」는 **원전 오인용**이었다 — 원전의 *"durable 단일 writer"* 는 검증 워커와 epoch 펜싱을 말한다(저장소 `CLAUDE.md`). 통합자·매니페스트·마스터측 attempt 배선은 걷혔다(2026-09-02~04, `#327`). `coordinator.py`는 현행 검수·정리의 공용 Git 헬퍼만 유지하며, selftest와 옛 2-tier 실행부는 #234에서 제거했다. 지도는 `docs/4-work-loop.md` §4.5·§4.7, 권한은 `docs/8-git-authority.md` §8.4 |
| `work/skeleton.py` | **인터페이스 동결 · `[PSEUDO]` 계수 유틸** — 지금 쓰는 곳은 `pseudo_count`·`depths`(`decompose`·`wcommit`)다. [주의] **마스터는 골조를 만들지 않는다**(`#339`, 2026-08-30) — 골조 생성은 요청자 몫이고, 이 파일의 생성 경로(기본 레인 `claude:opus`)는 그 전 기록이다. 동결 추출은 **결정적(LLM 0)** — 실제 헤더 857개로 회귀: 동결 12,719 · 본문 채움 시뮬 714건 **오탐 0** |
| `work/skeleton_gate.py` | [중요] **골조 빌드 게이트** (소 1.1.5) — `.2` 에서 UE5 를 세운 뒤(`run_build_on_workshop`/UHT) **통과해야 등재**. 원전은 빌드를 등재 *뒤*에 두었다가 **깨진 골조가 origin 에 박혀 워커 전원이 그 위에서 작업**했다. [주의] **게이트를 안 붙인 것은 통과가 아니라 미확인**(`Registered.gate_checked`). 실측: 콜드 144초 · 증분 35~65초 |
| `work/decompose.py` | **분해** (중 1.2) — §3 의 미결을 닫았다: 적용 순서 = [중요] **의존이 먼저**(include 위상 정렬) · 입도 = **파일 불가분** · 파일 내 = `[PSEUDO:N]` 뎁스. [중요] **묶음(동시)과 뎁스(순차)를 구분한다** — 안 그러면 겹침 검사가 뎁스를 위반으로 잡는다. [주의] 순환은 **보고만**(역추적이 basename 근사라 가짜일 수 있다). 계획은 `preview()` 를 **사람이 보고 자른다** |
| `work/heuristics.py` | [중요] **대화형 휴리스틱** (소 1.1.6) — 골조가 *"여기서 추측했다"* 를 내놓고 **사람이 답한 것만** 적립된다(모델 제안을 적립하면 다음 골조가 자기 말을 근거로 반복한다). [중요] **범위**: `project` / `domain:<D>` / `once`(적립 안 함) — 없으면 이번 작업의 결정이 남의 작업을 오염시킨다. 소 2.3.4 실패 카탈로그와 **짝** |
| `work/infer.py` | [중요] **추론 파견** (중 1.3) — 워커는 **읽고 추론하고 텍스트로 답한다.** `python -m master.work.infer probe\|run\|run-p\|spool`. 통과한 응답은 `commit_task → wcommit` 이 층1·층2(`#696`) 뒤 워커의 서브 브랜치에 커밋한다. 응답은 **파일로** 온다(`.ax/work/<task>/response.txt` → `scp`): `.2` 콘솔이 CP949 라 stdout 은 한국어에서 깨진다(층3 이 같은 자리에서 죽었다). 판정은 **마커 + 응답 파일 둘 다** — 마커만 보면 *"DONE 이라 말하고 파일 안 씀"* 을, 파일만 보면 *"반쯤 쓰이다 죽음"* 을 통과시킨다. [중요] 스풀(`<프로젝트>/responses/`)이 **복구 단위**다 — 같은 기준 커밋의 통과분은 **다시 사지 않는다**. [중요] 실패한 선행의 후속은 **파견 않고 반납**(큐는 `failed` 를 의존 해소로 센다). 기본은 **직렬**(실측: 2대 = 12% 빠르고 90% 비쌈). [완료] 실전: 단건 45초·$0.27 · **워커 2대 동시 36초·$0.4725·통과 2/2**(윈도우+BC-250, 채널 동일). [중요] 실측 **캐시 생성 고정비 워커당 24~26K 토큰** — N대면 N번 낸다. [주의] 옛 pull 회수 `collect`(claimer 산출물 회수)는 claimer 철거(`#320`)와 함께 없어졌다. 지휘자 모드가 `claude` 면 인증 실패를 즉시 고지하고 재시도에서 뺀다(`#721`, `conductor_auth`) |
| ~~`work/integrate.py`~~ | **삭제됨** (2026-09-04) — 통합자(약 1,000줄 · 테스트 131건). `master/test_no_integrator.py` 가 부활을 막는다. ⑺ 통합은 요청자가 `review.advance_work`(`ax-advance`)로 하고, 조각 단위 검증은 워커 커밋 사이클(`wcommit`)의 층1·층2 가 맡는다. 근거·실측은 리포트와 `docs/4-work-loop.md` |
| `work/layer1.py` | [중요] **층1 — 결정적 자기검증** (중 2.1). 무료·즉시·LLM 0. 동결 위반 + 휘발 태그(`[PSEUDO:N]`·`[IMPL]`) + [중요] **`[FEEDBACK]` 잔재** + 펜스. [중요] **두 곳에 박혀 있다** — 응답 수락(`infer.judge`)과 워커 커밋 직전(`wcommit` — 디스크에서 다시 읽어 검사). ①이 없으면 잔재가 스풀에 쌓이고 ②가 없으면 스풀 손질·재사용이 검사를 우회한다. [주의] 인코딩 유실 사본으로는 동결을 판정하지 않는다(없는 위반을 만든다) → **동결 미검사**로 기록 |
| `work/failures.py` | **실패 카탈로그** (소 2.3.4) — 판정 실패를 다음 골조 프롬프트로 되먹인다. [중요] 휴리스틱(사람이 답한 것만)과 **짝**이고, 이쪽은 **기계가 모아도 된다** — 근거가 컴파일러의 오류 문자열이지 모델의 의견이 아니다. [주의] 산문 요약은 적립하지 않는다. 파일·줄을 키에서 빼 **한 줄 + 횟수**로 접는다 |
| `bench_layer2.py` | **층2 모델 선정 벤치** (소 2.2.1) — 표본 7개(전부 실제로 났던 실패), 채점은 `verdict` 계약만. [중요] 실측: agy·sonnet·opus **동점**(4/5·오탐 0) → 싼 쪽 먼저 · 14b 는 선언부를 줘도 못 잡음 · **35B 는 오탐 2 로 탈락**. [중요] **차이는 모델이 아니라 grounding** — 넷이 선언부 없이는 열거값 환각을 놓쳤다 |
| `work/porting.py` | **포팅 원본 대응** (소 1.3.5) — `python -m master.work.porting pairs\|find`. [중요] 실측 2026-08-12: 파일 1,654개 중 stem 그대로 같은 것 **9쌍**, **접두사 정규화 후 21쌍**(포팅이 개명을 거쳤다). [중요] **퍼지 매칭 없음** — 틀린 원본은 원본 없는 것보다 나쁘다. 규칙(`exact`/`prefix`)을 결과에 실어 사람이 가늠한다. [중요] **경로만** 싣는다(워커의 Claude 는 체크아웃을 읽는다 — 골조 생성과 반대인 이유) + **읽기 전용·복사 금지·Edit/Write 금지**를 매니페스트에 못박는다 |
| `work/distribute.py` | **`/distribute` 입구** (소 1.3.4) — `plan` → `register` → `dispatch`, [중요] **단계마다 사람이 끊는다.** 계획은 **JSON 파일로** 낸다 — `preview()` 를 눈으로 보는 것만으로는 **자를 수 없다**. 사람이 그 파일에서 조각을 지우고, `register` 가 그것을 읽는다. 스킬 = `master/skills/distribute/`(`~/.claude/skills/distribute` 는 심볼릭 링크) |
| `work/followup.py` | **⑦ 준비·대기** (`#798`) — `ax-followup.timer` 1분 · `code_build_fn` = 공식 통합 + 회귀 + 정적(`pystatic`). 회귀 선택(`#815` ⑤): 같은 이름 + **직접 import(ast)** + **경로 언급**(전이 제외) · 공식 목록·`MASTER_ENV_TESTS` 는 빼고 노트 · 파일마다 이유 로그 |
| `work/pystatic.py` | **⑦ 정적 검사** — pyflakes(문법·undefined name 차단, `#804`) · import · **mypy `[call-arg]` 만 차단**(`#815` ②, 나머지는 노트 — attr-defined·union-attr 76/76 오탐 실측). base 에 있던 것은 안 막음 · 못 돌면 fail-closed. [주의] 무표기 함수 본문은 mypy 가 안 본다 |
| `context_synth/pinned_tree.py` | **고정 SHA 분리 worktree** (`#825`) — 저장소 밖 임시 · 항상 제거 · 쓰기는 `status --porcelain` 경고 로그. 기각 후보 수집이 상용 체인에 cwd 로 준다 |
| `work/runner.py` | **워커 러너 — 현행 파견기** (`autodispatch` 가 부른다: claim → SSH → submit). 지휘자 모드 `claude`/`codex` 실행과 Windows 세션 1 런처(`uses_session1`)도 여기서 간다. 큐에서 집어 워커의 Claude 에 파견하고 결과를 제출한다. `python -m master.work.runner probe\|once\|loop`. [중요] **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(실측: 두 워커 다 8101 이 401, AX MCP 0건). 하트비트도 마스터가 친다. 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄, 관대함은 **BLOCKED 쪽으로만**. [중요] 기준 절은 **파견 시점에 다시 푼다**. 실측 e2e 71초 |
| `work/cleanup.py` | **찌꺼기 정리** — 워커의 로컬 브랜치·부산물. `python -m master.work.cleanup plan\|apply\|remote [--apply]`. [중요] **워커는 스스로 못 지운다**(스킬이 브랜치 삭제 금지 — 의도). 삭제는 **팁이 `origin/<base>` 에서 도달 가능할 때만**, 나머지는 **보존**(fail-closed 의 방향이 보존이다). [중요] **원격은 `remote` 서브커맨드가** 병합 확인분(attempt/task)만 지운다 (#219, 사용자 결정 2026-08-18 — 원전 cleanup_attempts 회귀 · pre-push 훅 #125 가 이중 가드). 미병합 원격은 계속 사람 몫. `failed` 부산물은 증거로 남긴다. [주의] `--format` 은 셸별로 감싼다 — `%(...)` 의 괄호가 POSIX 문법이라 안 감싸면 리눅스 워커만 조용히 실패한다 |
| ~~`work/claimer.py`~~ · ~~`work/worker_daemon.py`~~ · ~~`work/ax_safety.py`~~ · ~~`work/buildjob.py`~~ | **철회됨** (2026-10-31, 사용자 결정 `#860`·`#861`). `claimer.py` 는 `#320`(08-27)에 철거, `#404` 가 `worker_daemon.py`(+`ax_safety.py`)로 build 한정 복원했던 상주와 빌드 큐 잡 `buildjob.py` 를 저장소째 지웠다. 서버(.57)가 SSH 로 총괄한다(빌드는 `plan_build`). 이미 배달된 사본은 `spec.DEPRECATED_PAYLOAD` 로 `deliver` 가 지우고 `check` 가 잔존·조회 실패를 FAIL 로 본다. 서버측 계약(유형 격리·워커 스코프·제출 신원)은 `test_queue_worker_contracts.py`, 부활 방지는 `test_no_worker_daemon.py` |
| `work/coordinator.py` | **공용 Git 헬퍼** — `GitError`·`_git_cmd`·`_git`·`_git_rc`·`_noop_log`. review·followup·cleanup·revise·attempt가 공유한다. 커밋 신원·서명 비활성·타임아웃·반환 계약을 유지한다. selftest 전용 2-tier 배정·push·병합·정리·가짜 작업장 함수는 #234에서 제거했다. |
| `work/attempt.py` | [중요] **쓰기 표면 가드 + 원격 정리** (`#327` 이후). `install-hook`/`status` 가 `work/pre_push_hook.sh`(SSOT)를 정본 클론에 설치·대조하고, [중요] **git-lfs 훅과 공존한다**(실측 2026-08-28: `git lfs install` 이 덮어 NS 가드가 통째로 사라져 있었다 — stdin 을 버퍼에 담아 가드 먼저, 그다음 LFS 에 위임). `plan_remote_cleanup`/`apply_remote_cleanup`(소 1.2.4 — [중요] **도달 가능한 것만**, durable 은 보존·세기만). [주의] **마스터측 attempt 배선(`push_attempt_for`·`merge_verified`·`apply_responses`·`ensure_attempt_tree`)은 `#327` 로 걷혔다** — `#317` 미결 ⑦ 이 「검증 후 커밋」을 정본으로 확정했고, 그 배선은 **프로덕션 호출자 0 · bare 에 attempt 브랜치 0** 이었다. `python -m master.work.attempt status|install-hook|plan|apply` ([중요] **`plan` 이 기본**) |
| `batch/` | [중요] **유휴 배치 구동 주체** (소 3.4.4, 2026-08-14) — 원전 `watch.py` 유휴 사이클의 리눅스 대응. [주의] **폴링 루프로 복각하지 않았다**: `docs/3-open-items.md` §5.4.2 가 *"`while True` 폴링 루프는 이식 대상이 아니다"*, §5.4.3 이 *"systemd 에 넘긴다"* 로 확정해 뒀다 → 자리는 `ax-batch.timer` 다. `gates.py` = 원전 `watch_state` 84~233 이식(활성·입력최소치·시각·요일·최소간격 다섯 조건 + `_last_*` 마커). [중요] **게이트를 하나로 접었다** — 원전이 스스로 *"recipe 합성 게이트와 **동일 구조**"* 라 적어 뒀고 상수만 다르다. `now` 는 주입 가능(원전이 `attempt_branch(ts=…)` 를 인자로 둔 것과 같은 이유). `run.py` = 구동 + CLI([중요] **`plan` 이 기본**, 부작용 0). [중요] 순서가 중요하다: **①일시중지 게이트 → ②시간 게이트** — 뒤집으면 작업 중에도 도는 창이 생긴다. 종료코드 **4 = 일시중지**(색인기와 같은 규약, `SuccessExitStatus=4`). `--force` 는 시각·요일·간격·입력최소치를 넘지만 [중요] **활성 플래그와 일시중지 게이트는 못 넘는다**(첫 판은 문서와 코드가 어긋나 있었다) |
| `context_search/search_log.py` | **RAG 공통 요청 문맥·누적 로그**(`#837`) — `search_context`의 원문·분류·request_id를 검색에 전달하고 개별 search_id로 확장/실제 질의·오류·빈 결과·당시 결과 스냅샷을 연결한다. 일반·직접 벡터·규범 검색과 내부 소비 경로를 계측한다. 원본 `search_logs/YYYY-MM-DD.jsonl`은 자동 삭제 회전 없이 누적하고 `search_log.jsonl`은 최근 2,000건 캐시다. `list_entries`·`get_entry`로 조회하며 기록 실패를 관측한다. 채널 순위·점수는 필드로 직접 보존한다. 사용자 원문은 확보된 값만 기록하고 검색 질의로 대체하지 않으며, 미수집 여부와 출처를 별도 필드로 남긴다. 프로세스 내 락과 `.search-log.lock`의 파일 락으로 CLI·서비스 사이 누적 원본 추가와 최근 캐시 회전을 직렬화한다 |
| `client/ontology_cache.py` | [중요] **클라이언트 온톨로지 폴백 캐시** (소 3.4.3) — 원전 `ontology_client_cache.py` 이식. **last-known-good, TTL 없음**(온톨로지는 중앙 SSOT — 시간으로 버리면 마스터가 오래 꺼진 동안 아무것도 못 낸다). [중요] **3분기 `outcome` 이 핵심이다**: `ok`(캐시 워밍) · **`absent`(서버가 「없다」고 답함 → 폴백·캐시 안 한다)** · `unreachable`(stale 폴백 + `_stale`/`_cached_at` 주입). [주의] `absent` 에 폴백하면 **사람이 지운 개념이 되살아난다** — 합치면 안 된다. 모르는 outcome 은 **예외**다. 에러·파싱 불가는 적재하지 않는다(캐시에 있는 것은 언제나 마지막 「정상」 데이터). **왜 우리에게 더 필요한가**: 실측 — 작업장 `.claude/vector_db` 가 **없고** MCP 등록도 0건이라 온톨로지는 마스터에만 있다. 진짜 소비자는 **요청자 `.33`**(스킬 `ax-ontology` 가 MCP 조회를 쓴다) — 작업장은 `ax-infer` 가 *"큐 401 이 정상, 우회로를 찾지 않는다"* 로 **의도적 차단**이다. 실 구동: 실 마스터 → `server` · 실제 404 → `absent`(캐시 안 늘어남) · 닫힌 포트 → `stale` · 미스 → `miss` |
| ~~`context_search/vector_fallback.py`~~ | **#234에서 제거** — 운영 소비자·배달 경로가 없는 벡터 폴백 이식분이었다. 실제 MCP가 사용하는 SQLite 온톨로지 캐시(`client/runtime/ontology_cache.py`)는 보존한다. |
| `context_search/context_audit.py` | [중요] **컨텍스트 MD 진단** (소 3.4.1) — 원전 737줄 이식, **읽기 전용 기본·LLM 0**. 8분류(valid·pence_wrapped·natural_prefix·shell_only·empty_summary·no_frontmatter·dir_named·**orphan_stem**). [중요] **분류 순서가 판정을 바꾼다** — `dir_named` → `orphan_stem` → 내용. 실측으로 증명됐다: 사전 스캔의 「본문 50자 미만 147건」이 감사에선 `shell_only` **39건**이고, 차이 108건은 orphan 으로 먼저 잡혔다(순서를 바꾸면 **재생성할 소스가 없는 108건이 재생성 대상**이 된다). [주의] **배치가 아니다 — 요청 시 돈다**(원전 `watch.py` 가 유휴 사이클에서 부르지 않는다). 복구는 [중요] **계획이 기본**이고 펜스·자연어 도입부만(걷어내서 **나아지는 것만**), `dir_named`·`orphan_stem` 은 **옮기지 않는다**(사람의 판단). 실측 1,037건: valid 886 · shell_only 39 · orphan 112 → [중요] **좀비 11건 발견, 8건이 미전파된 개명**(`#167` 의 실증) 아카이브 이동 도우미 3종과 전용 검사는 #234에서 제거했다(운영·CLI·MCP 호출 없음). 진단·펜스/도입부 복구·사람 판단 분류는 유지한다. |
| `context_search/search_log_analyzer.py` | **검색 로그 분석** (소 3.4.2) — 원전 696줄 이식, **stdlib·LLM 0**. 채널 기여도 · 언어 갭 · BM25 0건 진단 · [중요] **반복 0건 한국어 검색어 → 시소러스 후보**(자동 반영 없음) · 도메인 빈도 · **RRF k 튜닝 시뮬레이션**(우리 `RRF_K=60` 이 맞는지 잰다). [중요] **표본이 얇으면 판단을 보류한다**(`MIN_TOTAL_SAMPLE=30`) — 오판이 무판정보다 비싸다. 임계값·판정 문구는 **원전 그대로**(바꾸면 과거 리포트와 비교 불가). [주의] `tag` 집계는 늘 0 이다 — 우리 융합은 2채널이고, 그 0 이 리포트에서 그 사실을 말해 준다 |
| `work/pre_push_hook.sh` | [중요] **쓰기 표면 가드의 원본(SSOT)** — `attempt.py install-hook` 이 정본 클론의 `.git/hooks/pre-push` 로 복사한다. [주의] **`.git/hooks/` 는 어느 저장소도 추적하지 않는다** — 훅을 그쪽에서만 고치면 클론을 다시 만들 때 **가드가 조용히 사라진다**(`events/post_receive_hook.py` 가 같은 규약을 같은 이유로 못박아 뒀다). `attempt.py status` 가 *"설치됐나"* 와 *"원본과 같나"* 를 **갈라서** 답한다 |
| ~~`work/selftest.py`~~ | **#234에서 제거** — 폐기된 매니페스트·2-tier 경로에 의존했고, 호출 스킬은 #232에서 먼저 철거됐다. 옛 NONCE 드라이런·실 Gitea/작업장 selftest는 현행 파이프라인의 실행 경로가 아니다. 과거 실측은 reports/18-selftest-stage2.md와 Git 이력에 남는다. 현행 ⑦ 검사는 followup·pystatic·공식 통합 목록을 따른다. |
| `work/conventions.py` | **코드 규약 부착** — `UE_PROHIBITIONS`(개명·상속 변경·모듈 이동 금지: [중요] **블루프린트 에셋이 조용히 깨진다**) + `repo/CLAUDE.md § Code conventions` 를 **읽어서** 싣는다(SSOT 는 그 파일이고, 우리는 **명명된 절만** 잘라 온다). `manifest.build` 에서 도메인 규범 **앞**에 붙는다. [중요] **그 파일의 부재는 `degraded` 가 아니라 본문 주석**이다 — 프로젝트에서 gitignore 대상이라 부재가 정상이고, **늘 빨간 게이트는 게이트가 아니다** |
| `events/gate.py` | [중요] **색인 일시정지 게이트** (원전 이식, #164). 작업이 돌고 있으면 색인을 미룬다 — 실측 근거: 셀프테스트의 push 가 색인기를 **15번 깨웠고 14번은 할 일이 없었다**. [중요] 조건은 **`in_progress` 하나뿐**(원전 독스트링: *"Phase 2 변경 — `in_progress` 만 pause 조건"*. `ready_for_review` 도 센다고 적었던 내 메모가 틀렸다). HTTP 우선·실패 시 디스크 대체·[중요] **모르면 진행**(`degraded` 이유를 실어서). 미룬 것은 유닛 종료코드 **4**(`SuccessExitStatus=4`)로 알리고 `ax-indexer.timer` 가 따라잡는다. [주의] **스풀이 비어도 폴링해야 한다** — 안 그러면 미뤄 둔 일이 영원히 안 잡힌다. [중요] **순서 함정**: 이 게이트를 붙이기 전에 큐를 청소해야 한다 — `in_progress` 로 굳은 4건이 색인을 **조용히 영구 정지**시킬 상태였다(#186 을 먼저 처리한 이유) |
| `sqlite_util.py` | **동시 접근 공통 설정** — `busy_timeout` 10초 + WAL. 색인기와 검색이 같은 DB 를 만지므로 없으면 `database is locked` 로 조용히 실패한다. `graph/db.py`·`graph/dependency.py`·[중요] **`context_search/bm25.py`**(빠져 있던 곳)에 적용 |
| `sigma_audit.py` | [중요] **조용한 실패 감사 — 원전 `.claude/reviews/_silent_failure/audit_matrix.md`(99줄, 인용 0회) 이식**. **σ.2 스캐너**: 함수 전체를 감싼 `try` + 넓은 핸들러 + 조용한 `return`/`pass` + 로그 없음. `python -m master.sigma_audit`. [중요] **좁히는 조건 셋이 이식의 본체였다** — 첫 이식은 **114건**, 원전은 **6건**이었고 그 격차가 곧 덜 이식된 증거였다: ① 넓은 핸들러만(`sqlite3.OperationalError` 처럼 좁게 잡은 것은 **의도**) ② 예외를 값으로 돌려주면 조용하지 않다(우리 MCP 도구 24개가 그 형태) ③ 의도는 **핸들러 주석에서도** 찾는다. [중요] ②③은 **원전 문서에 글자로 없다**(사람 검토자의 암묵 판단) — **글자만 옮기면 우리 관례를 결함으로 센다**. [주의] **판정은 사람이 한다**: 스캐너는 *"의도가 적혀 있지 않다"* 까지고, 적혀 있으면 그것은 설계다. **σ.1 발동 매트릭스는 일부러 코드로 만들지 않았다**(절차는 이 모듈 주석에 있다 — 코드로 만들면 「주장된 경로를 파싱」하는 취약한 것이 되고 그게 또 하나의 조용히 틀리는 자리가 된다). 재검증 주기 = **마일스톤 갱신 시점** |
| `graph/` | **관계 그래프** — 상속(tree-sitter C++) + `#include`. 1,806 클래스 · 6,380 메서드 · 10,817 간선, 전체 스캔 2.9초. `python -m master.graph build\|status` |
| `ontology/` | **온톨로지** — YAML io(PyYAML 0) · stale **판정과 settle** · L1/L2/L3 · 멤버 제안 · 개념 계층 · **사실 게이트** · 패키지 쓰기 · **LLM 재합성** · **부분 무효화**(변경분만) · **레이어 책임 서술**. `python -m master.ontology plan\|dry\|refresh\|describe`. [중요] 결정 규칙은 그 패키지 `__init__.py` 에 있다 |
| `context_synth/` | **컨텍스트 MD 합성** — 프롬프트·grounding·σ.7 게이트·**사실 게이트**·서킷브레이커. 색인기에 배선됨 |
| `client/` | **워커 번들** — 머신 프로브(실측) → config·스킬·CLAUDE.md 배달 → **되읽어 해시 대조**. `probe\|plan\|deliver\|check <프로젝트>` · `update`는 마운트된 프로젝트만 배달→대조, 등록 전체는 `update --all` |
| `status.py` | **클러스터 상태 화면** (중 3.2) — `python -m master.status show\|html`. [중요] **새 서비스 0**: 도메인 뷰어와 같은 표면(자립형 HTML 한 장, 외부 자원 0). [중요] 수집은 **전부 읽기 전용**이고 **주기 가드 120초**(BC-250 은 부하로 커널이 멈춘 전례). [중요] 닿지 않는 것을 값 없음으로 접지 않고, **역할로 판정이 갈린다**(요청자가 꺼진 것은 정상일 수 있다). 상태는 **아이콘+라벨+색**, 히어로는 하나. [주의] 추세 그래프 없음(이력이 희박하면 없는 추세를 보인다) · 온도 구간은 **관례**라고 화면에 적는다.<br>[중요] **갱신은 `ax-status.timer`(5분) 가 한다 — 브라우저 새로고침으로는 수집이 일어나지 않는다**(사용자 지적 2026-08-13: *"70분째 갱신 안되는데?"*). `REFRESH_SEC` 는 타이머의 `OnUnitActiveSec` 과 **한 쌍**이고(`test_status` 가 대조한다) `MIN_INTERVAL`(120초) < 5분 < `viewer.STALE_SEC`(15분) 순서를 지켜야 한다 — 주기가 임계값보다 길면 낡음 경고가 **늘 떠서** 안 읽힌다. 가드에 걸린 실행은 종료코드 **3**(`EXIT_TOO_SOON`)이고 유닛이 `SuccessExitStatus=3` 로 받는다 — 사람이 손으로 돌린 직후의 타이머 실행을 `failed` 로 남기면 진짜 고장과 구별되지 않는다.<br>[중요] **팔레트는 원전(`webui/web_ui_original.py`)의 `:root` 와 같다** — `#0d1117`/`#161b22`. 라이트 모드를 **일부러 두지 않는다**: 이웃 화면에 없으므로 이 화면만 흰 배경으로 뒤집히면 다른 앱으로 읽힌다(사용자 지적: *"클러스터 환경만 색테마가 달라"*) |
| `viewer.py` | **읽기 전용 화면 서빙** (중 3.2 후속) — 8103 의 `/view/` 에 `cluster.html`·`domains.html` 을 낸다. [중요] **새 포트·유닛·ufw 0**: 이미 열려 있고 인증된 포트에 라우터로 붙였다. [중요] **인증 없이 열린다**(사용자 결정 2026-08-13) — 이 경로는 조작이 불가능하고(GET/HEAD·화이트리스트·수집 유발 없음), 규칙의 글자를 지키려고 **쓰이지 않는 화면**을 만드는 것이 더 나쁘다. 남는 방어는 **ufw LAN 한정**. [중요] API 경로는 그대로 잠겨 있다 · `AX_VIEW_REQUIRE_TOKEN=1` 로 되돌릴 수 있다(그때만 뷰 토큰이 쓰인다). [중요] **요청이 수집을 유발하지 않는다**(파일만 읽어 준다) · 낡으면 **배너로 박는다** · 경로는 **화이트리스트** |
| `source_text.py` | [중요] **CP949 44%** (실측 723/1,654). 소스는 전부 이걸 거쳐 읽는다 — 한글 주석이 최고 신호원이다 |
| `context_search/` | 검색 코어 — 벡터(ChromaDB) + BM25(FTS5) 를 RRF 로 융합. **마운트된 프로젝트의 디렉토리를 매 호출 해석**한다 (§5.5.2). 재색인: `python -m master.context_search.rebuild` |
| `requirements.txt` | 마스터 의존성. AgentTest 엔 없어 `build.bat:29` 기준으로 신규 작성 |
| `systemd/` | 유닛 목록은 `ls master/systemd` 가 답한다(서비스·타이머·path — 큐·브로커·프로젝트·색인기·파견·배치·리뷰 큐·상태) (§5.4.4 확정: systemd + venv). [완료] 전부 설치·enable·가동 중 — `systemctl status ax-task-queue ax-broker ax-projects` |
| `work/autodispatch.py` | **자동 파견** (`#340`) — 골조 push·등재가 `ax-dispatch.path` 를 깨우면 끝까지 배당한다. 걸었는지와 왜 안 걸었는지를 **둘 다** `[dispatch]` 로 찍는다 · 세션 한도 보류는 `--resume` 으로만 푼다 |
| `work/subbranch.py` | 정본 ⑷ — 조각마다 작업 브랜치에서 갈라진 **서브 브랜치**를 push 한 번으로 만든다(worktree·체크아웃 없음) |
| `work/wcommit.py` | 정본 ⑸-a — **워커가 자기 서브 브랜치에 커밋**하는 사이클. 디스크에서 다시 읽어 층1 → 층2(`#696`) → 커밋·push → `main` 복귀 · 조각 브랜치·원격추적·`.ax/work/<task>` 정리 |
| `work/lanes.py` | 본문 작성 **레인** — `DEFAULT_LANES` 가 정본(`agy → codex → claude → 로컬`, #788). 로컬은 클라우드 셋 모두 한도 소진일 때만(`work/llm_policy.py`) · 로컬 결과는 「재검증 필요」 표시 |
| `work/revalidation.py` | **로컬 산출물 재검증** (#788·#840) — 표시 기록(`<트윈>/revalidation/records.json`) · 문서 재합성(`run_documents`) · 조각 정산(`settle_tasks`, LLM 0) · 조각 후보 생성(`run_tasks` — 클라우드만, 층1 통과분을 `task/<W>/r<N>/<T>-cloud` 로 push, 표시 유지). 매일 00시 `cloud_revalidation` 배치(`batch/run.py`)가 이 순서로 돈다. 채택은 ⑦ `advance_work(adopt=[…])` 의 사람 선택뿐 · 미채택 후보는 지우지 않고 cleanup·finalize 보고에 따로 나온다. 머리말을 못 읽는 문서는 「표시 없음」 + 요약 한 줄 |
| `work/register.py` | 작업 등록 — `/distribute` 의 마스터 몫(원전 `executor_work_register.py` 이식) |
| `work/review.py` | 요청자 검수·⑺ 전진(`advance_work`)·마감(`finalize_work`)·반려(`reject_work`). 기본은 `confirm=False` — 승인 발화가 트리거 · ⑺ 은 로컬 생성 조각·클라우드 후보를 보이고 `adopt=[…]` 로 조각별 채택(#840, 기본은 원래 조각) |
| `work/revise.py` | **상한 있는 재시도** (`#388`) — 층1 이 막은 조각에 고칠 기회를 준다. 인증 실패(`#721`)·한도는 재시도에서 뺀다 |
| `work/handover.py` | 마운트 전환 인계 조사 (`#253`) — 남은 것을 다섯 부류 전부 이름으로 낸다 |
| `work/conductor_auth.py` | **워커 Claude 인증 24시간 보관** (`#721`) — `claude auth status` 결과를 워커 홈 `.cache/ax-dispatch/claude-auth.json` 에. 자격 정보는 읽거나 저장하지 않는다. 재로그인 뒤 `force=True` (절차: `docs/14-onboarding-runbook.md` §14.2-4) |
| `work/session_usage.py` · `work/usage.py` · `work/usage_dashboard.py` | 사용량 계측 — 대화 세션 수집(`#713`·`#748`) · 레인 토큰 실측(어느 모델이 얼마를 썼나) · 모델별·기간별 대시보드 집계 |
| `work/build_local.py` | 요청자(`.33`)의 검수 빌드 — `review_work(build_fn=…)` 에 꽂는 어댑터(`layer3_verify` 사슬) |
| `work/branch_names.py` · `work/twin_base.py` | 브랜치 이름 규약 · 작업의 **기준**(작업 브랜치 tip) (`#319`) |
| `work/batching.py` · `work/generate.py` · `work/logs.py` | 태스크 묶기(파일 불가분, `#65`) · 코드 생성 + 층2 통과 · 파견 기록(`#323` — 화면이 읽는다) |
| `work/pyskel.py` | `.py` 골조의 동결·스텁 잔존·구문 — 층1 의 Python 판 (`#695`) |
| `work/tdd_dryrun.py` | TDD 드라이런 하니스 — 원전 이식(`#145`). [주의] 진입점 없음 — 처분은 `#234`·`#232` |
| `redmine.py` | Redmine 이슈 조회·생성·**갱신**(노트·상태·진척·마일스톤·부모·우선순위·제목·본문 — `#752`). 키는 마스터에만 있고 응답·로그에 내보내지 않는다 |
| `plan_block.py` | Redmine 이슈 본문 안 **플랜 영역**(`<!-- ax:plan:begin v=N -->` ~ `<!-- ax:plan:end -->`) 읽기/쓰기 (`#826` T1). 형식 v2(`#857`)는 「단계」 칸(조건부 단계 선언)을 더한다 — v1 본문은 그대로 읽고 쓰며, 단계를 선언할 때만 v2 로 올린다. 태그 사이만 다루고 영역 밖 본문은 바이트 그대로 둔다. 형식이 어긋나면 고쳐 읽지 않고 `PlanError` 로 거절한다. 상태 전이 규칙은 여기 없다(T2) |
| `plan_state.py` | 플랜 태스크 **상태 전이 강제** (`#826` T2). 전이는 `transition` 하나 — 근거 없는 완료·사유 없는 차단/해당없음·선행 미완료 착수·완료 되돌리기를 `TransitionError` 로 거절한다. `violations` 는 사람이 고친 본문의 규칙 위반을 읽기만 한다 |
| `plan_start.py` | 「일감 시작」 진입점 (`#826` T3). 이슈 본문으로 `no_spec`·`plan_needed`·`plan_invalid`·`plan_violations`·`resume`·`next`·`blocked`·`plan_done` 판정과 다음 행동 문장을 낸다. 판정만 하고 쓰지 않는다 — [중요] `plan_needed` 에서 구현으로 넘어가지 않는 것이 호출자 계약이다 |
| `plan_steps.py` | 태스크 실행 7단계의 **해당 여부 판정** (`#826` T4). 프로필 `kind` 로 단계마다 실행·해당없음·조건부와 사유를 낸다 — code 는 2·4·6 해당없음, unreal 은 2·6 조건부·4 해당없음(제네레이트 불필요, `#857` T1 실측). [중요] 빈·모르는 kind 와 `index_only` 는 `StepError` 로 거절한다(빈 값을 unreal 로 읽지 않는다). `steps_for_task`(`#857`)는 태스크 「단계」 선언으로 조건부를 실행/해당없음으로 확정하고, 조건부가 아닌 단계 선언은 거절한다 |
| `plan_tools.py` | 플랜 도구 본체 (`#826` T5) — `start`(판정+7단계 표) · `set_plan`(등록·편집, 상태·근거는 못 바꿈, 시작된 태스크는 못 뺌) · `transition`(상태 전이+노트). MCP `plan_*_tool` 3종과 스킬 `master/skills/ax-plan` 이 이것을 부른다. [주의] 읽고-쓰기 사이 사람 수정은 덮인다 — 같은 일감 동시 마킹 금지 |
| `plan_build.py` | 플랜 태스크의 **빌드 단계**(7단계 1·5, `#861` T2 = `#857` T7). `build_step` 이 `runner.pick_worker(requires=("ue5",))` 로 고른 UE5 워커에서 `layer3_verify.run_build_on_workshop` 를 SSH 로 구동한다 — 마스터는 로컬 빌드를 하지 않는다. 리비전은 **조회만**: 빌드 전 HEAD 불일치·조회 실패·추적 파일 dirty 면 빌드하지 않고, 빌드 뒤 HEAD 가 움직였으면 실패. 근거 한 줄(`evidence`)을 돌려주고 플랜 마킹은 호출자 몫. [주의] 종전 `buildjob` 큐 경로(`#857` T4)는 철회·삭제됐다(`#861` T3) |
| `plan_events.py` | 플랜 **거절 기록** (`#864` T1). `plan_tools.transition`·`set_plan` 의 규칙 거절(`PlanError` 계열)을 레지스트리로 푼 **AXCluster 트윈**의 `plan_events.jsonl` 에 한 줄씩 남기고 예외는 그대로 올린다(마운트 무관). Redmine 읽기·쓰기 실패(`PlanTransportError`)는 남기지 않는다. 기록 실패는 거절을 바꾸지 않는다(stderr 경고). getter 를 주입한 호출은 `events_path` 를 줄 때만 기록한다 |
| `plan_metrics.py` | 플랜 **효용 계측** (`#864` T2·T3, 읽기 전용·LLM 0). `python -m master.plan_metrics issue <id...>` — 상태별·태스크 리드타임·차단/되돌림·완료 노트 근거(해시/검사 수치)·범위 이탈(대상 칸 대조, 근사)·거절·재개 정확도(N분 공백, 근사). `baseline --version-id N` — 플랜 없는 일감의 리드·재개·해결 체류·종결 노트 근거. `compare` 는 같은 지표만 나란히, 플랜 전용은 N/A. 모두 `--json` |
| `service_restart.py` · `service_freshness.py` | 승인 뒤 부르는 AX 서비스 재시작·복구 CLI(`scripts/ax-service-restart`, `#647`) · 서비스가 **도는 코드**가 최신인가(`#301` — `update` 가 보고한다) |
| `version.py` | 마스터 정체 — 버전 핸드셰이크(`get_master_version`, `#191`) |
| `census.py` · `canary.py` | 원전 인용 census(`#177`) · 영구 유실 카나리(`#182`) |
| `gitea_group.py` · `transfer.py` · `utf8.py` · `agy_probe.py` | `gitea` 그룹 승격(`#336`) · 상태 익스포트/임포트 · 콘솔 UTF-8 강제(`#181`) · agy 라이브 프로브(`#171`) |
| `webui/` | 8103 웹 UI — `/cluster` · `/ontology` · `/onboarding` · `/usage` · `/rag-logs` 등. `/api/v1` 은 무인증 공개, 쓰기 `/control/*` 는 요청자 토큰 |
| `webui/rag_logs.py` | RAG 로그 목록·요청 묶음·검색 상세(`#837`). 원문·LLM 질의·실제 검색어·당시 결과를 조회하며 자동 작업과 원문 미수집을 구분한다. 오래된 선택 검색은 페이지 밖이어도 표시한다. 등록 프로젝트 경계·조회 API는 `webui/app.py`가 담당한다 |
| `projects/onboard.py` | 신규 프로젝트 온보딩 — 등록 한 번으로 서버·클라 전부(`#259`). 기본은 계획, `--confirm` 이 실행 |
| `task_queue/reclaim.py` | 큐의 리스 회수·verify backlog 백그라운드 스레드(Plan v5 C.3 카나리). [주의] 모듈 독스트링이 없다 — 세부는 소스 확인 필요 |

### task_queue 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r master/requirements.txt
AX_TASK_QUEUE_ROOT=/home/sim/ax-state PYTHONPATH=. \
  .venv/bin/python -m master.task_queue --serve /home/sim/ax-state 8101 0.0.0.0
```

**이식 시 바꾼 것 3가지** (원본과의 차이 — `../PLAN.md` §9.5):

| | AgentTest | 여기 |
|---|---|---|
| import | 플랫 (`from models import ...`, PyInstaller 전제) | 패키지 상대 import |
| 상태 루트 | `Path(__file__).parent.parent.parent` **역산** | `AX_TASK_QUEUE_ROOT` **명시 설정, 없으면 즉시 실패** |
| `--cleanup-branches` | root(=UE5 저장소)의 `worker/*` 브랜치 삭제 | [중요] **거부** — 마스터 root 는 큐 상태 저장소라 조용한 no-op 이 된다 |

상태 저장소는 `/home/sim/ax-state`(로컬 git). 상태 전이마다 감사 커밋이 쌓인다 —
**UE5 저장소가 아니라 큐 자체의 상태**다(`../PLAN.md` §2.1).

```python
from layer2_verify import verify_files
v = verify_files([("Combat.cpp", src)])
if v.blocked:
    # v.failure 가 있으면 계약 위반(검증기가 판정을 못 냄), 없으면 실제 지적
    print(v.summary(), v.findings)
```

[중요] **AgentTest 원본과 결정적으로 다른 점** — 원본 `syntax_check` 는 **fail-open** 이었다
(docstring: *"checked=False = 양쪽 다 불가 → 호출자는 통과로 간주"*). 검증기가 죽거나
헛소리를 하면 조용히 통과했다는 뜻이다. 여기서는 **차단**한다. 근거·실측 = `../PLAN.md` §9.4.4.

**언어: Python 확정** (2026-08-06). 신규 작성이 아니라 **AgentTest 기존 자산 이식**이 주 작업이다.
근거와 상세 배치는 `../PLAN.md` §5.

> [중요] **마스터는 인프라지 작업장이 아니다** (2026-08-07 확정). RAG·온톨로지로 **적합한 코드 뭉치를
> 조립해 윈도우에 건네는** 것까지가 역할이고, **파일 적용·빌드·테스트·코드 등록은 윈도우가 한다**
> (`../PLAN.md` §2.1). **파일을 소유하지 않는다.**
>
> BC-250 이 인계한 것은 **추론 연산**이다 — AgentTest 에선 팀원 PC 마다 로컬 LLM 을 각자 돌렸는데
> 그 부하를 보드가 넘겨받았을 뿐, 파일을 다루던 역할이 옮겨온 게 아니다.
>
> 마스터도 **오케스트레이터의 하나**로서 자기 모델 자원(Claude · Antigravity `agy` · BC-250)을 쓰지만,
> 그 오케스트레이션은 **모델 호출·라우팅·컨텍스트 조립**이지 파일 작업이 아니다(`../PLAN.md` §2.3).
> 나머지 둘은 **윈도우 UE5 PC 2대** 각각의 Claude Code(`../client/README.md`) — 총 3곳이다.

## 역할

- **컨텍스트 매니페스트 조립** — RAG·온톨로지·클래스그래프로 "적합한 코드 뭉치"를 만들어 건넨다.
  대규모 모듈은 **골조 생성 → 인터페이스 동결 → 클래스 단위 분할**까지 여기서(`../PLAN.md` §4.5)
- **추론 브로커** — 엔드포인트 라우팅·헬스체크·페일오버. [완료] **구현됨**(`broker/`, `:8102`).
  [주의] 엔드포인트는 **BC-250 만이 아니다** — RTX 3060 윈도우 PC 가 #2 다. 추론 노드를 호출하는 것은 마스터뿐이라는 원칙은 그대로
- **task_queue** — 잡 분배 + **능력 기반 라우팅**(`requires: ue5` 는 윈도우가 claim).
  [완료] **구현·실측 완료(2026-08-08)** — `requires ⊆ capabilities` 부분집합 매칭, fail-closed
- **층2 검증 호출** — 상용 모델 문법·API 검사(`agy` → Claude 폴백). [완료] **구현됨** — 위 `layer2_verify.py`
- **RAG 인덱스**(ChromaDB + BM25) · 온톨로지/관계그래프 · 디지털 트윈.
  "소스=정답" 원칙에 따라 **실제 소스 본문을 번들**한다
- **gajae-code 드라이버** — Deep-Interview/Ralplan/Ultragoal 단계 호출·조율
- 추론 노드 응답(stateless) 수신 및 후처리(펜스 제거·`[PSEUDO]` 잔재 검사)

## 추론 클라이언트 래퍼 (신규 작성 — 이식 아님)

Ollama 를 그대로 호출하지 않고 **얇은 Python 래퍼를 거친다.** 감시·검증·재시도를 걸 지점이 필요하다.
**이건 마스터 몫이다** — 노드를 일회용으로 유지해야 재구축이 쉽고, 검증에 필요한 태스크 컨텍스트
(동결 선언·매니페스트)가 여기 있으며, 노드 간 페일오버는 본질적으로 마스터의 책임이기 때문이다.

| 구분 | 내용 |
|---|---|
| 생존 감시 | `stream:true` 청크 간격 감시 — **생성 중 2s**, **첫 청크 120s+**(콜드 로드 36s + prefill 38s 합산 대비). 초과 시 연결 종료 + 다른 노드로 재할당 |
| 노드 상태 | 주기적 `/api/tags` 프로브 → 죽은 노드 라우팅 제외. `watcher/common_utils.local_llm_health_check_one_shot` 재사용 |
| 요청 정규화 | `"think": false` 주입(35B 필수), `num_predict`/`temperature` 정책, 타임아웃 |
| 응답 후처리 | 마크다운 펜스 제거, `[PSEUDO]` 잔재 검사 |
| 사전 검증 | 동결 인터페이스 위반 1차 검사 — 왕복 낭비 차단 |
| 라우팅 | 모델↔노드 고정 배정 반영 — **전환 비용 실측: 35B 66.9s / 14b 37.5s, 왕복 ≈100초**(2026-08-08 재측정. 기존 "36초"는 14b 방향만 본 값) |
| 계측 | tok/s·첫 청크 지연 기록 → 임계값 재조정 근거 |

근거와 실측 수치: `../PLAN.md` §6.

## 이식 대상 (AgentTest → 여기)

| 컴포넌트 | 규모 | Windows 의존 | 순서 |
|---|---|---|---|
| `mcp/task_queue/` | — | 5줄(둘 다 리눅스 분기 존재) | **1** — 루프 중추, 가장 가벼움 |
| `mcp/context_search/` | — | 사실상 0 (`sys.platform` 분기 0건) | 2 — ChromaDB 인덱스 이관 |
| `watcher/` | 21,171줄 | 19줄 | 3 — 가장 크나 순수 데이터라 기계적 |
| **`mcp/agy_query/`** | 194줄 | — | **4** — 층2 검증. 리눅스에선 PTY 코드 불필요(리포트 04) |
| **`mcp/local_llm_runner/`** | 144줄 | — | §6.4 래퍼와 중복 — **재사용/대체 먼저 결정** |
| `mcp/master_orchestrator/` 中 오케스트레이션 | — | — | 5 — UE 빌드 부분은 분리 |

[주의] **위 표는 2026-08-06 의 착수 순서다 — 1·2·4 는 끝났다.** 무엇이 실제로 있는지는 이 문서
맨 위 표가 답이다. [중요] **그리고 이 표가 「끝」을 뜻하지 않는다** — 원전 인용 census(리포트 14)가
**우리 저장소에서 한 번도 언급되지 않은 원전 파일 74개 / 23,710줄**을 셌다. 컴포넌트 단위로
옮겼다고 그 안의 설계까지 옮겨진 것은 아니다.

### 어디에 놓였나 (컴포넌트 → 경로)

[중요] **아래 표는 구분선이 빠져 있어서 위 4열 표의 행으로 렌더링되고 있었다**(2026-08-14 발견) —
GitHub 에서 20행이 열 어긋난 채 보였다. 표를 나눌 때 `|---|` 를 빼먹지 말 것.

| Component | Where |
|---|---|
| Layer-2 verdict contract (fail-closed) | `master/verdict.py`, `master/layer2_verify.py` |
| Layer-3 gate (UE5 automation logs, fail-closed) | `master/layer3_verify.py` |
| Inference broker (Ollama-compatible) | `master/broker/` — **live**, `ax-broker.service` `:8102` |
| Task queue (ported, 2,717 lines) | `master/task_queue/` — **live**, `ax-task-queue.service` `:8101` |
| Project registry (MCP) | `master/projects/` — **live**, `ax-projects.service` `:8103`. [중요] **요청자의 온톨로지 창구**도 여기다(2026-08-09): `create_domain`·`edit_ontology_item`(편집=잠금)·`remove_ontology_item`([중요] 잠긴 것은 force 필요)·`lock`/`list_locked`·`unassigned_classes`(노출만)·`sync_ontology`(기본 계획만). 그 전에는 어휘(별칭)만 다룰 수 있고 **개념은 마스터 CLI 에만** 있었다 |
| Capability routing (`requires`/`capabilities`) | `master/task_queue/logic_claim.py` |
| Shared bearer auth (all 3 services, fail-closed) | `master/auth.py` |
| Event spool + **indexer** (Gitea hook → graphs → **synthesis** → reindex) | `master/events/` — **live**: `ax-indexer.path` (inotify) → `ax-indexer.service`. [중요] **This is where the twin grows**: changed files → relation graphs (LLM 0) → context-MD synthesis (35B) → reindex. Lost groups are logged by name — the watermark has already advanced, so they can't be found again |
| Context search — **multilingual** vector + BM25 (+trigram KR table), RRF, `[대괄호]` focus | `master/context_search/` — context MDs (961 docs) **and now domain packages** (7, 소 2.1 [완료] 3/3). Domains live in a **separate DB + collection** (`bm25_domains.db` / `ontology_domains`) so they can't crowd out file-level hits; `search_norms` applies a [중요] **triple noise gate** (BM25-zero ⇒ empty · vector-only needs threshold · hard cap). Wired into `rebuild_all`, skipped by fingerprint when unchanged |
| Workflow — work branch + per-piece sub-branches (정본 7단계), registration, dispatch, worker commit, **domain norms** | `master/work/` — 소 2.3.1 [완료]: `norms.py` turns `search_norms` hits into an invariants-first bundle in the manifest (≤2 domains × actions touching the target classes). **Measured**: same prompt/model, norms flipped the generated code from an invented member to 4/4 real ones and it honoured a real invariant — but **near-miss spellings survived** (`CurrentStep` vs real `Step`), which is why "ship source declarations to the node" is still open. [중요] `master.work.generate` the *function* shadows the same-named submodule in `__init__` — import the module path directly. Map: `docs/4-work-loop.md` §4.7 |
| **Relation graphs** — inheritance (tree-sitter C++) + `#include` (중 1.1, **done 5/5**) | `master/graph/` — **1,806 classes · 6,380 methods · 10,817 include edges** on ModularStage, 2.9s full scan. `python -m master.graph build\|status`. [주의] reverse include lookup is basename-approximate (9 ambiguous headers) |
| **Ontology** — YAML io (no PyYAML) · stale · L1/L2/L3 layers · member proposals · concept hierarchy · **fact gate** · package writer · **LLM re-synthesis** (중 1.3, **8/13**) | `master/ontology/` — `python -m master.ontology status\|plan\|verify\|dry\|refresh`. [중요] **`plan` → `dry` first**: `plan` sizes prompts with **no LLM**, `dry` synthesises without writing. Domain MD (intent) + source excerpts + graphs → actions/invariants → deterministic gates → package. [중요] **Payload is chunked by `#include` cohesion and split across both nodes** — model name selects the node; the defaults are each node's **resident** model (any other evicts the pin). `claude`/`agy` are also valid lanes. Prompt budget is **measured** (2.79–2.85 chars/token, `num_ctx` 8192 both nodes). [중요] Decision rules live in that package's `__init__.py`.<br>**Ported 2026-08-15 (M4 중 3.2 · 소 3.1.4)**: **partial invalidation** — only the yaml a changed class is mentioned in is re-LLM'd (`invalidate.py`, origin η.7.2/.3); the **watermark settle** that makes stale converge (`stale.settle` — [중요] without it a domain stays stale forever, and it must **skip classes whose chunk failed**); manifest `md_hash` stamping (the signal the partial/full decision reads); a **domain-index sync at the end of a batch** (origin η.2.5 — otherwise a grown twin is invisible to search); and **layer responsibility descriptions** (`descriptions.py`, origin η.7.4, **1 LLM call per domain**, full-rebuild only, read back through MCP `get_layer_description_tool`). [중요] Both new writers honour **`verified_by_user` *and* `protected`** — the snapshot must not be overwritten by our drafts |
| **Context-MD synthesis** — prompt+grounding, σ.7 fence strip + σ.7-B save gate, stamping, batch circuit breaker (중 1.2) | `master/context_synth/` — `python -m master.context_synth one\|fill\|all\|status`. 909 source groups, all already documented from the snapshot. **Wired into the indexer** (changed files only). A **deterministic factuality gate** (`verify.py`) rejects docs describing commented-out code as live — **75% pass rate measured on the 35B (3/4)**, and the one rejection was a real catch. `sample N` dry-runs without touching snapshot docs. [중요] **BC-250 holds memory per request and never gives it back until the model unloads.** [주의] **Re-measured 2026-08-15**: ~60 MB for small requests (the old ~170 MB figure was larger prompts), and [중요] **`UNLOAD_EVERY` never actually fires** — its counter resets on every `_lane` call and our domains have 1–3 chunks per lane (measured: ~14 heavy-lane requests, 0 reclaims). The board went down twice; see `machines/bc250-1.md` |
| **찌꺼기 정리** — 워커의 로컬 브랜치·부산물 (중 2.5.4) | `master/work/cleanup.py` — `python -m master.work.cleanup plan\|apply\|remote [--apply]`. [중요] **워커는 스스로 못 지운다**(스킬이 브랜치 삭제를 금지 — 의도된 설계). 삭제 기준은 하나: **팁이 `origin/<base>` 에서 도달 가능한가**. 도달 불가·확인 실패는 **보존**한다(fail-closed 의 방향이 여기서는 보존). [중요] **원격은 `remote` 서브커맨드만** 병합 확인분을 지운다(#219) — 미병합 원격의 `push --delete` 는 사람의 판단. 부산물은 `verified`/`cancelled` 만 지우고 **`failed` 는 증거로 남긴다**. 우리 브랜치 위에 서 있으면 `main` 으로 되돌리고(체크아웃된 브랜치는 삭제 대상에서 빠지므로) **한 번 더 훑는다**. [주의] `--format` 은 셸별로 감싼다 — `%(...)` 의 괄호가 POSIX 문법이라 안 감싸면 리눅스 워커만 조용히 실패한다 |
| **계측 하네스** — 분산 대 단독 (토큰·시간·품질) | `master/bench.py` — `claude -p --output-format json` 의 usage 를 모아 팔별로 비교한다. 품질은 diff 의 식별자를 클래스 그래프와 대조([주의] enum·매크로는 오탐). [중요] **매니페스트를 실행 위치에 놓고 읽히는지 확인한 뒤에만 잰다** — 그걸 안 해서 첫 결과를 통째로 버렸다(리포트 11 §19). 실측: 4파일 묶음이 파일당 **3.2배 싸다**; 워커 2대는 이 크기에서 **12% 빠르고 90% 비싸다** |
| **워커 러너** — claim → 기준 재해석 → scp → `claude -p` → 마커 → submit (중 2.5.3) | `master/work/runner.py` — `python -m master.work.runner probe\|once\|loop`. [중요] **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(두 워커 모두 8101 이 401, AX MCP 0건이라 스킬의 전제가 틀려 있었다). 하트비트(리스 1200초)도 마스터가 대신 친다. [중요] 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄이고, 관대함은 **BLOCKED 쪽으로만** 연다. [중요] 기준 절은 **파견 시점에 다시 푼다** — durable 브랜치는 설계상 등록 이후 요청자가 만들므로 등록 시점 값은 반드시 낡는다. 선택 단계에서 **워킹트리까지 본다**(워커의 거부는 마지막 방어선이지 선택 기준이 아니다). 실측 e2e 71초 |
| **Worker bundle** — per-machine config · skill · CLAUDE.md merge, delivered over SSH (#21) | `master/client/` — `probe\|plan\|deliver\|check <project>` and **`update` for every registered project/workshop**. **Role-aware**: `worker` gets `ax-work`; `requester` gets requester skills and is excluded from `drivable_hosts`. Paths and Windows Python are probed, then written to `<checkout>/.ax/config.json`; `.mcp.json` and `ax-fix` consume that absolute Python path rather than ambient `py`. Residency has one desired-state decision across plan/deliver/check (role · daemon · capability · active mount), and delivery reconciles stale registrations. Delivery re-reads sha256; `update` runs deliver→check for the whole registry and returns failure if any project fails. CLAUDE.md is marker-merged so human text is preserved |
| Ollama node check + remote install (no residency) | `master/provision.py` — `python -m master.provision check` |
| **정본 7단계·공용 Git·σ 감사·색인 게이트** | `master/work/subbranch.py` · `master/work/wcommit.py` · `master/work/review.py` · `master/work/coordinator.py` · `master/events/gate.py` · `master/sigma_audit.py`. 옛 selftest·2-tier 실행부는 #234에서 제거했다. |
| venv + deps | `.venv/`, `master/requirements.txt` |

**여기로 오지 않는 것** (Windows 잔류): **`worker/` 전체**(작업자 하네스 — 파일 소유 계층) ·
`ue_builder.py` · `ue_test_runner.py` · `executor_integration_build.py` · `tdd_dryrun.py` ·
`mcp/commandlet_runner/`.
[완료] **이 판단은 원전이 이미 내려 뒀다** — κ.8 의 윈도우 의존 포팅 표가 `ue_builder.py`·
`ue_test_runner.py` 를 *"리눅스로 옮기는 대상 아님, **혼동 주의**"* 로 표시한다. [중요] **「안 옮긴다」는
판단에도 근거가 필요하다**(M4 규칙) — 안 옮긴 것과 빠뜨린 것은 문서상 구별되지 않기 때문이다.
통합 빌드 게이트는 인프라에 고정하지 않고 **task_queue 잡으로 큐잉 → UE5 보유 기계가 claim**하는
CI 러너 패턴으로 분리한다.

**선결 설치**: `claude` [완료] v2.1.223 / `agy` [완료] v1.1.10(리포트 04) /
~~`bun`·`node`~~ → **마스터엔 불필요**(2026-08-08) — gjc 는 loopback 제약상 윈도우에서 돈다(`../PLAN.md` §9).

| `context_synth/review_gen.py` | **생산자① 자동 코드리뷰** (#205) — 유저 커밋 → `reviews/<작성자>/`. [중요] 백엔드는 **상용 체인**(원전 기본값 — 14b 는 라이브에서 재시도 포함 2회 산문, 탈락 실측). 형식은 지시가 아니라 **검증기+재시도 1회**가 지킨다(검증 정규식 = 소비자 파서 그대로). trivial/파이프라인(author=ax-cluster) 스킵. 소비자 배선은 `events/consumer._auto_review` — fail-soft + 카나리 2종 · 「## 4. 골조 지시 이행」(`#815` ④): diff 에 **지워진 `[PSEUDO]`** 가 있는 커밋(워커 조각)에만 요청(`removed_pseudo_lines`) — 불이행 / 골조 모순 행 → R 항목(intent · mid/low) → /fixes · 기각 후보, 주간 플랜 제외. 요청했는데 빠지면 형식 위반. 없는 커밋은 프롬프트 바이트 동일 |
| `context_synth/signals.py` | **생산자② code-writer 신호** (#206) — 코드가 아니라 **작업 과정**(intent·검색·파일·피드백·거절·복구)을 `recipes/_signals.jsonl` 에. 적재는 지금 하나다: 요청자가 큐 `POST /api/v1/signals`(redmine/note 와 같은 대행, `task_queue/server.py`). [주의] 「통합자가 통과분만 자동 적재」하던 경로는 통합자 삭제(2026-09-04)로 없어졌다 — `#383` 이 그 공백을 다룬다. [중요] 큐 유닛 샌드박스는 `recipes/`·`history/` **두 디렉토리만** 연다 |
| `context_synth/history_gen.py` | **생산자③ 작업 기록** (#207) — 원전 α′ frontmatter. work 종결(merged/rejected) 시 큐가 자동 기록 + `.33` `log_history` 대행. [중요] **원전 미니 파서는 인라인 리스트를 통째로 버린다** — 대시 리스트만 (emission/parser 쌍 왕복 테스트) |
| `context_synth/review_collector.py` `issue_classifier.py` | **소비자①** (#156) — 리뷰 MD → 구조화 이슈(원전 글자대로: 심각도 정규화·`[리뷰]` 코멘트 제외·라인 버킷 중복 제거·3파일+ 반복 패턴). [중요] **이 파서가 생산자 형식 계약 그 자체** — 「(없음)」 자리표시는 여기서 쓰레기 이슈 10건으로 측정돼 생산자에서 제거됐다 |
| `context_synth/planner.py` (+`plan_generator`·`plan_dedup`·`plan_archive`·`plan_register`) | **소비자② 주간 플랜** (#155) — 리뷰→플랜 MD→**실 Redmine 이슈**(트래커 코드리뷰, id 를 frontmatter 에 되적어 다음 주는 갱신). [중요] Step 0(draft 자동 승급)은 **미이식** — 「자동 승급 영구 비활성」 확정 결정의 적용. *"코드를 직접 수정하지 않는다 — 사람이 확인 후 실행"* (원전 원문) |
| `context_synth/recipes_synthesizer.py` | **소비자③** (#157) — 신호→LLM 클러스터→임계치(≥5) 도달만 레시피 합성→아카이브(28일)→`_anti_patterns.md` 4섹션. [주의] 읽기 도구(find_recipes 등)는 원전 code_recipes MCP 소관 — code-writer 배선 때 |
| `context_synth/history_harvest.py` | **소비자④** (#158) — `.claude`(8필드)+`.gemini`(6섹션 A/B/C) 통합 read-only 파서 → 온톨로지 narrative 시드. 실물 코퍼스는 `.33` 에서 받아 `history/`·`history_gemini/`. audit 도메인 원천 = **온톨로지 YAML** (class_graph.db domains 는 비어 있음 실측) |
| ~~`work/carry.py`~~ | **삭제됨** (2026-09-02, `53fc90f` 매니페스트 철거) — 지시는 골조의 `[DOC]`·`[PSEUDO]` 주석으로 git 이 나른다 |
| `ontology/edit_field.py` | **도메인 MD 필드 편집** (#189, MCP `edit_domain_field_tool`) — 원전 두 갈래: parent/tags/collab 는 manifest 직접 패치+인덱스(LLM 0), summary/status 는 MD-only. [중요] tags 통째 치환으로 사라지는 **한글 태그를 크게 보고** (#194 지점 7) · 이름은 조용한 정규화 대신 거부(한글 허용, 지점 5) |
| `ontology/log_tags.py` | **실증 테스트 로그 태그 사이드카** (#169, 원전 η.12.3) — `domains/<D>/log_categories.yaml` CRUD. [중요] 저작 방향 (b): 게임팀이 코드에 구현한 뒤 사람이 확정 기입, 자동 생성·편입 없음. 매치 없음 = `log_tags` 필드 **부재**(null 아님 — 실증 불가와 미확인의 구분). 뷰어(/ontology)가 invariant 에 자동 첨부. CLI `log-tags` · MCP 3종 |
| `ontology/log_candidates.py` | **태깅 권장 지점 리포트** (제안형, LLM 0) — invariant evidence 기반, `<트윈>/ontology/_log_tagging_candidates.md`. 확정 등록분은 버리지 않고 [확정 등록됨] 표기(원전은 파서 한계로 dedup 포기). [주의] 후보에 **레거시 모듈**(빌드 안 되는 Source/Project_Alpha)이 섞인다 — 실증 대상은 실 모듈에서 고를 것 (첫 실전 실측, 리포트 23 §1) |
| `../client/runtime/client_mcp.py` | [주의] **`master/` 밖으로 나갔다** (#263, 2026-08-22) — 클라 기계에서 도는 코드이므로 `client/` 소속이다. **배달 위치는 `axmaster/clientside/client_mcp.py` 그대로**(`.33` 의 `.mcp.json` args). **`.33` 로컬 stdio MCP** (stdlib 단일 파일, 번들로 배달) — 도구 목록의 정본은 그 파일의 `TOOLS` 다(조회 · 레드마인 대행 · work 등재/개선요청 · 모드 · fix 계열 등). `redmine_note` 는 우선순위·제목·본문도 바꾼다(`#752`). 결정 도구는 없다 — 검수는 배달된 review 모듈이 유일 절차 |
| `bench_kr.py` | **한글 검색 정답 집합 벤치** (#211) — `analysis/kr_ground_truth.tsv`(자연=로그 실물·구조=별칭+한글 태그) 위에서 4변형(baseline/kr_on/gated/kr+gated) × hit@1/5/MRR. [중요] 1차 실측: **게이팅이 hit@1 5배**(0.153→0.787) — bm25.py 가설(진범=RRF 벡터 상관 오답) 확인. 자연 확정 30건 전엔 스스로 「판정 보류」를 찍는다 |

## 설계 제약

- [주의] **「파일을 소유하지 않는다」는 Flow Y(2026-08-14)와 #185(2026-08-17)로 좁혀졌다** —
  마스터는 조각 서브 브랜치(`task/*`)를 **만들고**, 커밋은 워커가 한다(정본 ⑷⑸). attempt 계층과
  매니페스트는 걷혔다(`#327`, 2026-09-02). **`main` 과 빌드는 여전히 못 한다.** 실제 컴파일·에디터 작업은 작업자(윈도우). **여기는 인프라지 작업장이 아니다.**
- **추론 요청은 stateless**, **피드백 누적은 git**(`task/<work_id>/<task_id>` 브랜치). 두 경로 분리.
- 검증은 3층 게이트(워커 자기검증 → 상용 모델 문법검사 → 실제 UE5 빌드). `../PLAN.md` §4.3.

상세 계획: `../PLAN.md`
