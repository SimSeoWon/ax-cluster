# master

192.168.0.57(리눅스 인프라 컴퓨터)에서 돌아갈 오케스트레이션 코드가 여기 들어간다.

## 지금 있는 것

[중요] **이 표가 모듈 설명의 SSOT 다** — 저장소 루트 `CLAUDE.md` 가 *"표는 여기 두지 않는다"* 며
이리로 보낸다. 새 모듈을 만들면 **여기에 행을 추가한다.** [중요] **기준일을 적지 않는다** —
「2026-08-09 기준」이라 적어 뒀더니 닷새 뒤에도 그 상태로 남아 신규 6종을 통째로 몰랐다
(리포트 12 §11 에 같은 사고가 이미 있었다: *"README 가 오늘 만든 것을 통째로 모르고 있었다"*).

| 파일 | 내용 |
|---|---|
| `verdict.py` | **층2 판정 계약 (fail-closed).** `contract_text()` 로 프롬프트에 계약을 붙이고 `parse_verdict()` 로 읽는다. **모든 실패 경로가 차단으로 떨어진다** |
| `layer2_verify.py` | 층2 검증기 — UE5/C++ 문법 프롬프트 + 백엔드 체인(`agy` → `claude`). `verify_files([(경로, 내용)])` |
| `test_*.py` | **테스트는 저장소 루트 `CLAUDE.md` 의 세는 법을 따른다.** pytest 불필요 — 각 파일을 그대로 실행한다. 목록은 저장소 루트 `CLAUDE.md` 참조 |
| `task_queue/` | **잡 분배 큐** (AgentTest `mcp/task_queue/` 이식, 2,717줄). HTTP 서비스 + MCP stdio |
| `auth.py` | [중요] **공용 인증 — 공유 베어러 토큰, fail-closed.** [주의] **뷰 경로(`/view/`)는 기본 공개다** — 조작 불가능한 읽기 전용 화면에 토큰을 요구하면 안 쓰이게 된다(사용자 결정). 잠그려면 `AX_VIEW_REQUIRE_TOKEN=1` + `init-view`. 세 서비스가 같은 ASGI 미들웨어를 쓴다. 토큰이 없거나 약하거나 파일 권한이 열려 있으면 **서비스가 뜨지 않는다**. 열린 경로는 `/livez` 하나 |
| `layer3_verify.py` | **층3 판정 계약 (fail-closed).** UE5 자동화 로그(`Result={Success\|Fail}` + `TEST COMPLETE. EXIT CODE:`)와 UBT 빌드 로그(`Result: Succeeded\|Failed`)를 각각 파싱한다. [중요] **프로세스 반환 코드를 읽지 않는다** — 실측에서 거짓 실패·거짓 성공이 둘 다 나왔다 |
| `broker/` | **추론 브로커** (Ollama API 호환). [완료] **가동 중** — `ax-broker.service` `:8102` |
| `projects/` | **프로젝트 레지스트리 MCP** — 등록·마운트 전환 + **워크숍 체크아웃**(경로·`driven`) + 더티 체크. [완료] **가동 중** — `ax-projects.service` `:8103`, 도구 **15종** + `role`(worker/requester) |
| `events/` | 이벤트 스풀 + **색인기**. Gitea `post-receive` → 스풀 → `ax-indexer.path`(inotify) → 재색인. [중요] 폴링 아님 |
| `provision.py` | Ollama 노드 **점검·원격 설치**. [중요] `.33`(메인 작업 PC)은 `resident=False` — 상주시키지 않는다. `python -m master.provision check` |
| `work/` | 워크플로우 — **골조·동결 → 분해 → 파견 → 검증**. 2-tier 브랜치 · 매니페스트 · 도메인 규범(`norms.py`) · 헤더 선언(`declarations.py`). [중요] **「쓰는 주체는 하나」는 맞지만 그 하나는 통합자가 아니라 서버다** — 원전 `cluster_coordinator.py`(인용 0회)의 `verify_and_merge` 주석이 *"durable 단일 writer 보존"* 이고, 작업장은 **ephemeral `attempt/` 를 push** 한다. 리눅스가 강제하는 변경은 **UE5 빌드가 `.2` 로 가는 것 하나뿐**. 복구는 `coordinator.py`(이식·실증 완료) + [중요] **`attempt.py`(배선 완료 2026-08-14 — 마스터가 쓴다)** → 마일스톤 4. 지도는 `docs/4-work-loop.md` §4.5·§4.7, 권한은 `docs/8-git-authority.md` §8.4 |
| `work/skeleton.py` | [중요] **골조 생성 + 인터페이스 동결** (중 1.1). 골조는 **텍스트로만** 낸다(마스터는 파일을 안 쓴다, §2.1). grounding = 관계 그래프(부모/자식·include) + **include 헤더의 타입** + 헤더 선언(#26) + 도메인 규범 + **휴리스틱**. 기본 레인 `claude:opus` — [중요] A/B 실측: 동결 선언 opus **30** / agy 20 / 35B 10 / 14b **6**(+펜스 잔재). 골조는 **모든 조각의 계약**이라 값을 쓸 자리다. 동결 추출은 **결정적(LLM 0)** — 실제 헤더 857개로 회귀: 동결 12,719 · 본문 채움 시뮬 714건 **오탐 0** |
| `work/skeleton_gate.py` | [중요] **골조 빌드 게이트** (소 1.1.5) — 통합자 `.2` 의 격리 트리에 놓고 UE5 를 세운 뒤 **통과해야 등재**. 원전은 빌드를 등재 *뒤*에 두었다가 **깨진 골조가 origin 에 박혀 워커 전원이 그 위에서 작업**했다. [주의] **게이트를 안 붙인 것은 통과가 아니라 미확인**(`Registered.gate_checked`). 실측: 콜드 144초 · 증분 35~65초 |
| `work/decompose.py` | **분해** (중 1.2) — §3 의 미결을 닫았다: 적용 순서 = [중요] **의존이 먼저**(include 위상 정렬) · 입도 = **파일 불가분** · 파일 내 = `[PSEUDO:N]` 뎁스. [중요] **묶음(동시)과 뎁스(순차)를 구분한다** — 안 그러면 겹침 검사가 뎁스를 위반으로 잡는다. [주의] 순환은 **보고만**(역추적이 basename 근사라 가짜일 수 있다). 계획은 `preview()` 를 **사람이 보고 자른다** |
| `work/heuristics.py` | [중요] **대화형 휴리스틱** (소 1.1.6) — 골조가 *"여기서 추측했다"* 를 내놓고 **사람이 답한 것만** 적립된다(모델 제안을 적립하면 다음 골조가 자기 말을 근거로 반복한다). [중요] **범위**: `project` / `domain:<D>` / `once`(적립 안 함) — 없으면 이번 작업의 결정이 남의 작업을 오염시킨다. 소 2.3.4 실패 카탈로그와 **짝** |
| `work/infer.py` | [중요] **추론 파견** (중 1.3) — 워커는 **읽고 추론하고 텍스트로 답한다.** `python -m master.work.infer probe\|run\|run-p\|spool`. [중요] **큐에 제출하지 않는다** — 태스크는 `claimed` 로 남고 제출은 통합자(소 1.4.3)가 한다. 응답은 **파일로** 온다(`.ax/work/<task>/response.txt` → `scp`): `.2` 콘솔이 CP949 라 stdout 은 한국어에서 깨진다(층3 이 같은 자리에서 죽었다). 판정은 **마커 + 응답 파일 둘 다** — 마커만 보면 *"DONE 이라 말하고 파일 안 씀"* 을, 파일만 보면 *"반쯤 쓰이다 죽음"* 을 통과시킨다. [중요] 스풀(`<프로젝트>/responses/`)이 **복구 단위**다 — 같은 기준 커밋의 통과분은 **다시 사지 않는다**. [중요] 실패한 선행의 후속은 **파견 않고 반납**(큐는 `failed` 를 의존 해소로 센다). 기본은 **직렬**(실측: 2대 = 12% 빠르고 90% 비쌈). [완료] 실전: 단건 45초·$0.27 · **워커 2대 동시 36초·$0.4725·통과 2/2**(윈도우+BC-250, 채널 동일). [중요] 실측 **캐시 생성 고정비 워커당 24~26K 토큰** — N대면 N번 낸다 |
| `work/integrate.py` | [중요] **통합자** (중 1.4). [주의] *"유일한 쓰기 주체"* 라고 적어 뒀던 것은 정정됐다 — 원전에서 durable 을 쓰는 것은 **서버**이고(위 `work/` 행), 이 파일은 그 자리에서 **빌드 단계**를 맡는다. `python -m master.work.integrate plan\|run`. **조각마다** 층1(무료·결정적) → 적용 → **UE5 빌드** → [중요] 통과하면 커밋, 실패하면 **되돌리고 커밋하지 않는다**(소 1.4.4). [중요] §4.5 의 *"전부 적용 후 빌드 한 번"* 을 뒤집었다 — 증분 빌드 35~65초라 조각마다 세워도 싸고, **어느 조각이 깨졌는지 알 수 있다**. [중요] **첫 실패에서 멈춘다**(적용 순서 = 의존 순서). 격리 트리는 체크아웃의 **형제**(`ax-wt-<work>`), detached HEAD, 재사용 시 기준으로 자동 복원. push 는 **ff-only · force 금지** — 거부되면 커밋은 트리에 남고 사람이 판단한다. 실측: 격리+빌드+커밋 **159초**(콜드 빌드 142초). [중요] **층2 를 빌드 앞에** 두고(비싼 것 앞에 싼 것) 선언부 grounding 을 싣는다 — 못 실으면 `l2_grounded=False` 로 보고. [중요] 층3 `RunTests` 는 **work 단위 한 번**(실측 74초 — 문서의 미측정 DDC 비용이 이 값) · [주의] **테스트 0개라 fail-open + 경고**. 실패는 큐 되돌리기 + `[FEEDBACK]` + **레드마인 등재** + **실패 카탈로그 적립** |
| `work/layer1.py` | [중요] **층1 — 결정적 자기검증** (중 2.1). 무료·즉시·LLM 0. 동결 위반 + 휘발 태그(`[PSEUDO:N]`·`[IMPL]`) + [중요] **`[FEEDBACK]` 잔재** + 펜스. [중요] **두 곳에 박혀 있다** — 응답 수락(`infer.judge`)과 적용 직전(`integrate.apply_one`). ①이 없으면 잔재가 스풀에 쌓이고 ②가 없으면 스풀 손질·재사용이 검사를 우회한다. [주의] 인코딩 유실 사본으로는 동결을 판정하지 않는다(없는 위반을 만든다) → **동결 미검사**로 기록 |
| `work/failures.py` | **실패 카탈로그** (소 2.3.4) — 판정 실패를 다음 골조 프롬프트로 되먹인다. [중요] 휴리스틱(사람이 답한 것만)과 **짝**이고, 이쪽은 **기계가 모아도 된다** — 근거가 컴파일러의 오류 문자열이지 모델의 의견이 아니다. [주의] 산문 요약은 적립하지 않는다. 파일·줄을 키에서 빼 **한 줄 + 횟수**로 접는다 |
| `bench_layer2.py` | **층2 모델 선정 벤치** (소 2.2.1) — 표본 7개(전부 실제로 났던 실패), 채점은 `verdict` 계약만. [중요] 실측: agy·sonnet·opus **동점**(4/5·오탐 0) → 싼 쪽 먼저 · 14b 는 선언부를 줘도 못 잡음 · **35B 는 오탐 2 로 탈락**. [중요] **차이는 모델이 아니라 grounding** — 넷이 선언부 없이는 열거값 환각을 놓쳤다 |
| `work/porting.py` | **포팅 원본 대응** (소 1.3.5) — `python -m master.work.porting pairs\|find`. [중요] 실측 2026-08-12: 파일 1,654개 중 stem 그대로 같은 것 **9쌍**, **접두사 정규화 후 21쌍**(포팅이 개명을 거쳤다). [중요] **퍼지 매칭 없음** — 틀린 원본은 원본 없는 것보다 나쁘다. 규칙(`exact`/`prefix`)을 결과에 실어 사람이 가늠한다. [중요] **경로만** 싣는다(워커의 Claude 는 체크아웃을 읽는다 — 골조 생성과 반대인 이유) + **읽기 전용·복사 금지·Edit/Write 금지**를 매니페스트에 못박는다 |
| `work/distribute.py` | **`/distribute` 입구** (소 1.3.4) — `plan` → `register` → `dispatch`, [중요] **단계마다 사람이 끊는다.** 계획은 **JSON 파일로** 낸다 — `preview()` 를 눈으로 보는 것만으로는 **자를 수 없다**. 사람이 그 파일에서 조각을 지우고, `register` 가 그것을 읽는다. 스킬 = `master/skills/distribute/`(`~/.claude/skills/distribute` 는 심볼릭 링크) |
| `work/runner.py` | **워커 러너** — [중요] **구 토폴로지(워커가 커밋)다.** 지우지 않는다 — 되돌릴 수 있어야 한다(§8.4 [주의]). 큐에서 집어 워커의 Claude 에 파견하고 결과를 제출한다. `python -m master.work.runner probe\|once\|loop`. [중요] **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(실측: 두 워커 다 8101 이 401, AX MCP 0건). 하트비트도 마스터가 친다. 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄, 관대함은 **BLOCKED 쪽으로만**. [중요] 기준 절은 **파견 시점에 다시 푼다**. 실측 e2e 71초 |
| `work/cleanup.py` | **찌꺼기 정리** — 워커의 로컬 브랜치·부산물. `python -m master.work.cleanup plan\|apply`. [중요] **워커는 스스로 못 지운다**(스킬이 브랜치 삭제 금지 — 의도). 삭제는 **팁이 `origin/<base>` 에서 도달 가능할 때만**, 나머지는 **보존**(fail-closed 의 방향이 보존이다). 원격은 안 건드린다. `failed` 부산물은 증거로 남긴다. [주의] `--format` 은 셸별로 감싼다 — `%(...)` 의 괄호가 POSIX 문법이라 안 감싸면 리눅스 워커만 조용히 실패한다 |
| `work/coordinator.py` | [중요] **2단 브랜치 조율 — 원전 `cluster_coordinator.py`(200줄) 이식** (2026-08-14, 대 1). `assign_attempt`(서버가 브랜치명을 배정, **git 접촉 0**) · `push_attempt`(ephemeral `attempt/<id>/<workshop>/<ts>`, **force 허용** — durable 엔 절대 금지) · `verify_and_merge`([중요] **epoch 펜싱** — `submit_epoch < current_epoch` 면 좀비로 보고 병합 거부, **게이트는 notify 쪽이지 push 쪽이 아니다**) · `cleanup_attempts`([중요] **기본 `delete=False` — 세기만 한다**, 우리 08-09 결정인 증거 보존과 일치). **일부러 다르게 한 것**: 원전의 `worker` → 우리는 `workshop`(이 저장소에서 `worker` 는 BC-250 추론 노드라 세 뜻이 겹친다) · [중요] **`remote` 가 인자다**(기본 `origin` = 원전 그대로). 마스터 정본은 `origin` push 가 봉인돼 있어 그 인자 하나가 환경 차이를 흡수한다 |
| `work/attempt.py` | [중요] **마스터측 attempt 계층 — Flow Y 배선** (소 1.2.2, 2026-08-14). `coordinator.py` 는 이식돼 있었지만 **실 파이프라인이 한 번도 부르지 않았다**(실측: import 하는 곳이 테스트와 `selftest` 뿐) — 이 파일이 그 배선이다. `ensure_attempt_tree`(작업 트리는 정본 **옆** `ax-wt-<work>`, 정본은 `main` 에 남는다 — 색인기의 `merge --ff-only` 전제) · `apply_responses`(원전이 만든 **주입 seam** `work_fn` 에 실전 적용을 끼운다 → 드라이런과 실전이 같은 경로) · `push_attempt_for`([중요] **성공·실패 무관** — 이 계층은 판정하지 않는다. §8.4 *"실패도 커밋한다"*) · `merge_verified`(epoch 게이트 → 통과분만 durable) · `plan_remote_cleanup`/`apply_remote_cleanup`(소 1.2.4 — [중요] **도달 가능한 것만**, durable 은 원전대로 보존·세기만). push 는 두 번째 remote `gitea-write` 로 가고 클론의 `pre-push` 훅이 `attempt/*`·`task/*` 밖과 **미병합 삭제**를 거부한다. [중요] **문구 대조를 쓰지 않는다** — 이 기계는 `ko_KR` 이라 git 이 한국어로 말한다(실측: `"nothing to commit"` 판정이 조용히 빗나갔다). 실 Gitea 실증: attempt push · 좀비 epoch 거부(부작용 0) · durable 생성 · 색인기 `재색인 건너뜀`. [주의] **`merge_verified` 를 부르는 파이프라인 호출자는 아직 없다** — 빌드 게이트를 큐 잡으로 만드는 `#128` 의 몫. `python -m master.work.attempt status\|install-hook\|plan\|apply` ([중요] **`plan` 이 기본**, `apply` 는 대화형 세션에서 부르지 않는다) |
| `batch/` | [중요] **유휴 배치 구동 주체** (소 3.4.4, 2026-08-14) — 원전 `watch.py` 유휴 사이클의 리눅스 대응. [주의] **폴링 루프로 복각하지 않았다**: `docs/3-open-items.md` §5.4.2 가 *"`while True` 폴링 루프는 이식 대상이 아니다"*, §5.4.3 이 *"systemd 에 넘긴다"* 로 확정해 뒀다 → 자리는 `ax-batch.timer` 다. `gates.py` = 원전 `watch_state` 84~233 이식(활성·입력최소치·시각·요일·최소간격 다섯 조건 + `_last_*` 마커). [중요] **게이트를 하나로 접었다** — 원전이 스스로 *"recipe 합성 게이트와 **동일 구조**"* 라 적어 뒀고 상수만 다르다. `now` 는 주입 가능(원전이 `attempt_branch(ts=…)` 를 인자로 둔 것과 같은 이유). `run.py` = 구동 + CLI([중요] **`plan` 이 기본**, 부작용 0). [중요] 순서가 중요하다: **①일시중지 게이트 → ②시간 게이트** — 뒤집으면 작업 중에도 도는 창이 생긴다. 종료코드 **4 = 일시중지**(색인기와 같은 규약, `SuccessExitStatus=4`). `--force` 는 시각·요일·간격·입력최소치를 넘지만 [중요] **활성 플래그와 일시중지 게이트는 못 넘는다**(첫 판은 문서와 코드가 어긋나 있었다) |
| `context_search/search_log.py` | [중요] **검색 로그 기록기** (소 3.4.5) — 원전 `cs_common._log_search` 계열 이식. 스키마 그대로(ts·results·zero_hit·query·lang·result_details·caller). [주의] **`Hit.to_dict()` 로 적으면 채널 분해가 조용히 전부 빈다**(그것은 `bm25_score`·`vector_rank`·`bm25_rank` 를 버린다) → 필드 직접 읽기. [중요] **표면 census 를 모듈에 못박았다** — 기록 2곳(MCP `search_context_tool` · 웹UI `api_search`) / 미기록 4곳(기계 생성 질의). 원전의 `except: pass` 는 **fail-open 만** 옮기고 침묵은 안 옮겼다(σ 기준) |
| `client/ontology_cache.py` | [중요] **클라이언트 온톨로지 폴백 캐시** (소 3.4.3) — 원전 `ontology_client_cache.py` 이식. **last-known-good, TTL 없음**(온톨로지는 중앙 SSOT — 시간으로 버리면 마스터가 오래 꺼진 동안 아무것도 못 낸다). [중요] **3분기 `outcome` 이 핵심이다**: `ok`(캐시 워밍) · **`absent`(서버가 「없다」고 답함 → 폴백·캐시 안 한다)** · `unreachable`(stale 폴백 + `_stale`/`_cached_at` 주입). [주의] `absent` 에 폴백하면 **사람이 지운 개념이 되살아난다** — 합치면 안 된다. 모르는 outcome 은 **예외**다. 에러·파싱 불가는 적재하지 않는다(캐시에 있는 것은 언제나 마지막 「정상」 데이터). **왜 우리에게 더 필요한가**: 실측 — 작업장 `.claude/vector_db` 가 **없고** MCP 등록도 0건이라 온톨로지는 마스터에만 있다. 진짜 소비자는 **요청자 `.33`**(스킬 `ax-ontology` 가 MCP 조회를 쓴다) — 작업장은 `ax-infer` 가 *"큐 401 이 정상, 우회로를 찾지 않는다"* 로 **의도적 차단**이다. 실 구동: 실 마스터 → `server` · 실제 404 → `absent`(캐시 안 늘어남) · 닫힌 포트 → `stale` · 미스 → `miss` |
| `client/vector_fallback.py` | **클라이언트 벡터 폴백** (소 3.4.3) — 원전 `client_index.py` 이식. [중요] **해시가 같으면 임베딩을 다시 만들지 않는다**(없으면 폴백이 매 검색마다 임베딩해 마스터가 멈춘 상황에서 **더 느려진다**). [중요] **원전과 다르게 임베더는 우리 것을 쓴다** — 원전은 Chroma 기본 `all-MiniLM-L6-v2` 인데 우리 `embedding.py` 가 *"영어 전용 … 한글 질의가 두 채널 모두 실패했다"* 로 이미 기각해 뒀다. 그대로 옮기면 **폴백이 한글 질의에 무력해진다**(σ.9.0 의 `mtime`→git 과 같은 부류: 기제는 옮기고 구성요소는 우리 것). 결과에 `source=client_cache_vector` 를 박아 *"코퍼스가 아니라 가진 것 중에서"* 를 표시한다 |
| `context_search/context_audit.py` | [중요] **컨텍스트 MD 진단** (소 3.4.1) — 원전 737줄 이식, **읽기 전용 기본·LLM 0**. 8분류(valid·pence_wrapped·natural_prefix·shell_only·empty_summary·no_frontmatter·dir_named·**orphan_stem**). [중요] **분류 순서가 판정을 바꾼다** — `dir_named` → `orphan_stem` → 내용. 실측으로 증명됐다: 사전 스캔의 「본문 50자 미만 147건」이 감사에선 `shell_only` **39건**이고, 차이 108건은 orphan 으로 먼저 잡혔다(순서를 바꾸면 **재생성할 소스가 없는 108건이 재생성 대상**이 된다). [주의] **배치가 아니다 — 요청 시 돈다**(원전 `watch.py` 가 유휴 사이클에서 부르지 않는다). 복구는 [중요] **계획이 기본**이고 펜스·자연어 도입부만(걷어내서 **나아지는 것만**), `dir_named`·`orphan_stem` 은 **옮기지 않는다**(사람의 판단). 실측 1,037건: valid 886 · shell_only 39 · orphan 112 → [중요] **좀비 11건 발견, 8건이 미전파된 개명**(`#167` 의 실증) |
| `context_search/search_log_analyzer.py` | **검색 로그 분석** (소 3.4.2) — 원전 696줄 이식, **stdlib·LLM 0**. 채널 기여도 · 언어 갭 · BM25 0건 진단 · [중요] **반복 0건 한국어 검색어 → 시소러스 후보**(자동 반영 없음) · 도메인 빈도 · **RRF k 튜닝 시뮬레이션**(우리 `RRF_K=60` 이 맞는지 잰다). [중요] **표본이 얇으면 판단을 보류한다**(`MIN_TOTAL_SAMPLE=30`) — 오판이 무판정보다 비싸다. 임계값·판정 문구는 **원전 그대로**(바꾸면 과거 리포트와 비교 불가). [주의] `tag` 집계는 늘 0 이다 — 우리 융합은 2채널이고, 그 0 이 리포트에서 그 사실을 말해 준다 |
| `work/pre_push_hook.sh` | [중요] **쓰기 표면 가드의 원본(SSOT)** — `attempt.py install-hook` 이 정본 클론의 `.git/hooks/pre-push` 로 복사한다. [주의] **`.git/hooks/` 는 어느 저장소도 추적하지 않는다** — 훅을 그쪽에서만 고치면 클론을 다시 만들 때 **가드가 조용히 사라진다**(`events/post_receive_hook.py` 가 같은 규약을 같은 이유로 못박아 뒀다). `attempt.py status` 가 *"설치됐나"* 와 *"원본과 같나"* 를 **갈라서** 답한다 |
| `work/selftest.py` | [중요] **실증 하네스** — 게이트마다 라이브 1회를 붙이라는 규칙(리포트 13 §14)을 코드로 만든 것. `run_dry()` 임시 저장소 · `run_live()` **실 Gitea + 실 작업장 + 실 `claude -p`**. 핵심은 **NONCE 왕복**: 서버가 토큰을 **매니페스트에만** 심고, 그것이 durable 산출물에 나타나면 **git 으로 실린 컨텍스트가 실제로 읽혔다**는 증명이다(작업장 함수는 NONCE 를 인자로 받지 않고 **디스크에서 읽는다** — 안 그러면 아무것도 증명하지 않는다). 워크트리 둘(서버 역할·작업장 역할)을 만들어 매니페스트가 **git 외의 경로로 새지 않음**을 강제한다. 실측: 스크립트 15/15 · 실 `claude` 15/15 · 큐 경유 e2e 26/26, **잔재 0**. [주의] 처음엔 **운으로 통과**했다(`work_id` 를 양쪽에서 따로 계산했는데 초가 우연히 같았다) — 계약에 넣어 고쳤다 |
| `work/conventions.py` | **코드 규약 부착** — `UE_PROHIBITIONS`(개명·상속 변경·모듈 이동 금지: [중요] **블루프린트 에셋이 조용히 깨진다**) + `repo/CLAUDE.md § Code conventions` 를 **읽어서** 싣는다(SSOT 는 그 파일이고, 우리는 **명명된 절만** 잘라 온다). `manifest.build` 에서 도메인 규범 **앞**에 붙는다. [중요] **그 파일의 부재는 `degraded` 가 아니라 본문 주석**이다 — 프로젝트에서 gitignore 대상이라 부재가 정상이고, **늘 빨간 게이트는 게이트가 아니다** |
| `events/gate.py` | [중요] **색인 일시정지 게이트** (원전 이식, #164). 작업이 돌고 있으면 색인을 미룬다 — 실측 근거: 셀프테스트의 push 가 색인기를 **15번 깨웠고 14번은 할 일이 없었다**. [중요] 조건은 **`in_progress` 하나뿐**(원전 독스트링: *"Phase 2 변경 — `in_progress` 만 pause 조건"*. `ready_for_review` 도 센다고 적었던 내 메모가 틀렸다). HTTP 우선·실패 시 디스크 대체·[중요] **모르면 진행**(`degraded` 이유를 실어서). 미룬 것은 유닛 종료코드 **4**(`SuccessExitStatus=4`)로 알리고 `ax-indexer.timer` 가 따라잡는다. [주의] **스풀이 비어도 폴링해야 한다** — 안 그러면 미뤄 둔 일이 영원히 안 잡힌다. [중요] **순서 함정**: 이 게이트를 붙이기 전에 큐를 청소해야 한다 — `in_progress` 로 굳은 4건이 색인을 **조용히 영구 정지**시킬 상태였다(#186 을 먼저 처리한 이유) |
| `sqlite_util.py` | **동시 접근 공통 설정** — `busy_timeout` 10초 + WAL. 색인기와 검색이 같은 DB 를 만지므로 없으면 `database is locked` 로 조용히 실패한다. `graph/db.py`·`graph/dependency.py`·[중요] **`context_search/bm25.py`**(빠져 있던 곳)에 적용 |
| `sigma_audit.py` | [중요] **조용한 실패 감사 — 원전 `.claude/reviews/_silent_failure/audit_matrix.md`(99줄, 인용 0회) 이식**. **σ.2 스캐너**: 함수 전체를 감싼 `try` + 넓은 핸들러 + 조용한 `return`/`pass` + 로그 없음. `python -m master.sigma_audit`. [중요] **좁히는 조건 셋이 이식의 본체였다** — 첫 이식은 **114건**, 원전은 **6건**이었고 그 격차가 곧 덜 이식된 증거였다: ① 넓은 핸들러만(`sqlite3.OperationalError` 처럼 좁게 잡은 것은 **의도**) ② 예외를 값으로 돌려주면 조용하지 않다(우리 MCP 도구 24개가 그 형태) ③ 의도는 **핸들러 주석에서도** 찾는다. [중요] ②③은 **원전 문서에 글자로 없다**(사람 검토자의 암묵 판단) — **글자만 옮기면 우리 관례를 결함으로 센다**. [주의] **판정은 사람이 한다**: 스캐너는 *"의도가 적혀 있지 않다"* 까지고, 적혀 있으면 그것은 설계다. **σ.1 발동 매트릭스는 일부러 코드로 만들지 않았다**(절차는 이 모듈 주석에 있다 — 코드로 만들면 「주장된 경로를 파싱」하는 취약한 것이 되고 그게 또 하나의 조용히 틀리는 자리가 된다). 재검증 주기 = **마일스톤 갱신 시점** |
| `graph/` | **관계 그래프** — 상속(tree-sitter C++) + `#include`. 1,806 클래스 · 6,380 메서드 · 10,817 간선, 전체 스캔 2.9초. `python -m master.graph build\|status` |
| `ontology/` | **온톨로지** — YAML io(PyYAML 0) · stale **판정과 settle** · L1/L2/L3 · 멤버 제안 · 개념 계층 · **사실 게이트** · 패키지 쓰기 · **LLM 재합성** · **부분 무효화**(변경분만) · **레이어 책임 서술**. `python -m master.ontology plan\|dry\|refresh\|describe`. [중요] 결정 규칙은 그 패키지 `__init__.py` 에 있다 |
| `context_synth/` | **컨텍스트 MD 합성** — 프롬프트·grounding·σ.7 게이트·**사실 게이트**·서킷브레이커. 색인기에 배선됨 |
| `client/` | **워커 번들** — 머신 프로브(실측) → config·스킬·CLAUDE.md 배달 → [중요] **되읽어 해시 대조**. `python -m master.client probe\|plan\|deliver\|check` |
| `status.py` | **클러스터 상태 화면** (중 3.2) — `python -m master.status show\|html`. [중요] **새 서비스 0**: 도메인 뷰어와 같은 표면(자립형 HTML 한 장, 외부 자원 0). [중요] 수집은 **전부 읽기 전용**이고 **주기 가드 120초**(BC-250 은 부하로 커널이 멈춘 전례). [중요] 닿지 않는 것을 값 없음으로 접지 않고, **역할로 판정이 갈린다**(요청자가 꺼진 것은 정상일 수 있다). 상태는 **아이콘+라벨+색**, 히어로는 하나. [주의] 추세 그래프 없음(이력이 희박하면 없는 추세를 보인다) · 온도 구간은 **관례**라고 화면에 적는다.<br>[중요] **갱신은 `ax-status.timer`(5분) 가 한다 — 브라우저 새로고침으로는 수집이 일어나지 않는다**(사용자 지적 2026-08-13: *"70분째 갱신 안되는데?"*). `REFRESH_SEC` 는 타이머의 `OnUnitActiveSec` 과 **한 쌍**이고(`test_status` 가 대조한다) `MIN_INTERVAL`(120초) < 5분 < `viewer.STALE_SEC`(15분) 순서를 지켜야 한다 — 주기가 임계값보다 길면 낡음 경고가 **늘 떠서** 안 읽힌다. 가드에 걸린 실행은 종료코드 **3**(`EXIT_TOO_SOON`)이고 유닛이 `SuccessExitStatus=3` 로 받는다 — 사람이 손으로 돌린 직후의 타이머 실행을 `failed` 로 남기면 진짜 고장과 구별되지 않는다.<br>[중요] **팔레트는 원전(`webui/web_ui_original.py`)의 `:root` 와 같다** — `#0d1117`/`#161b22`. 라이트 모드를 **일부러 두지 않는다**: 이웃 화면에 없으므로 이 화면만 흰 배경으로 뒤집히면 다른 앱으로 읽힌다(사용자 지적: *"클러스터 환경만 색테마가 달라"*) |
| `viewer.py` | **읽기 전용 화면 서빙** (중 3.2 후속) — 8103 의 `/view/` 에 `cluster.html`·`domains.html` 을 낸다. [중요] **새 포트·유닛·ufw 0**: 이미 열려 있고 인증된 포트에 라우터로 붙였다. [중요] **인증 없이 열린다**(사용자 결정 2026-08-13) — 이 경로는 조작이 불가능하고(GET/HEAD·화이트리스트·수집 유발 없음), 규칙의 글자를 지키려고 **쓰이지 않는 화면**을 만드는 것이 더 나쁘다. 남는 방어는 **ufw LAN 한정**. [중요] API 경로는 그대로 잠겨 있다 · `AX_VIEW_REQUIRE_TOKEN=1` 로 되돌릴 수 있다(그때만 뷰 토큰이 쓰인다). [중요] **요청이 수집을 유발하지 않는다**(파일만 읽어 준다) · 낡으면 **배너로 박는다** · 경로는 **화이트리스트** |
| `source_text.py` | [중요] **CP949 44%** (실측 723/1,654). 소스는 전부 이걸 거쳐 읽는다 — 한글 주석이 최고 신호원이다 |
| `context_search/` | 검색 코어 — 벡터(ChromaDB) + BM25(FTS5) 를 RRF 로 융합. **마운트된 프로젝트의 디렉토리를 매 호출 해석**한다 (§5.5.2). 재색인: `python -m master.context_search.rebuild` |
| `requirements.txt` | 마스터 의존성. AgentTest 엔 없어 `build.bat:29` 기준으로 신규 작성 |
| `systemd/` | 유닛 **4개**(+`ax-indexer.path`) (§5.4.4 확정: systemd + venv). [완료] 전부 설치·enable·가동 중 — `systemctl status ax-task-queue ax-broker ax-projects` |

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
| Workflow — 2-tier branches, manifest, registration, generate → layer2 → hand over, **domain norms** | `master/work/` — 소 2.3.1 [완료]: `norms.py` turns `search_norms` hits into an invariants-first bundle in the manifest (≤2 domains × actions touching the target classes). **Measured**: same prompt/model, norms flipped the generated code from an invented member to 4/4 real ones and it honoured a real invariant — but **near-miss spellings survived** (`CurrentStep` vs real `Step`), which is why "ship source declarations to the node" is still open. [중요] `master.work.generate` the *function* shadows the same-named submodule in `__init__` — import the module path directly. Map: `docs/4-work-loop.md` §4.7 |
| **Relation graphs** — inheritance (tree-sitter C++) + `#include` (중 1.1, **done 5/5**) | `master/graph/` — **1,806 classes · 6,380 methods · 10,817 include edges** on ModularStage, 2.9s full scan. `python -m master.graph build\|status`. [주의] reverse include lookup is basename-approximate (9 ambiguous headers) |
| **Ontology** — YAML io (no PyYAML) · stale · L1/L2/L3 layers · member proposals · concept hierarchy · **fact gate** · package writer · **LLM re-synthesis** (중 1.3, **8/13**) | `master/ontology/` — `python -m master.ontology status\|plan\|verify\|dry\|refresh`. [중요] **`plan` → `dry` first**: `plan` sizes prompts with **no LLM**, `dry` synthesises without writing. Domain MD (intent) + source excerpts + graphs → actions/invariants → deterministic gates → package. [중요] **Payload is chunked by `#include` cohesion and split across both nodes** — model name selects the node; the defaults are each node's **resident** model (any other evicts the pin). `claude`/`agy` are also valid lanes. Prompt budget is **measured** (2.79–2.85 chars/token, `num_ctx` 8192 both nodes). [중요] Decision rules live in that package's `__init__.py`.<br>**Ported 2026-08-15 (M4 중 3.2 · 소 3.1.4)**: **partial invalidation** — only the yaml a changed class is mentioned in is re-LLM'd (`invalidate.py`, origin η.7.2/.3); the **watermark settle** that makes stale converge (`stale.settle` — [중요] without it a domain stays stale forever, and it must **skip classes whose chunk failed**); manifest `md_hash` stamping (the signal the partial/full decision reads); a **domain-index sync at the end of a batch** (origin η.2.5 — otherwise a grown twin is invisible to search); and **layer responsibility descriptions** (`descriptions.py`, origin η.7.4, **1 LLM call per domain**, full-rebuild only, read back through MCP `get_layer_description_tool`). [중요] Both new writers honour **`verified_by_user` *and* `protected`** — the snapshot must not be overwritten by our drafts |
| **Context-MD synthesis** — prompt+grounding, σ.7 fence strip + σ.7-B save gate, stamping, batch circuit breaker (중 1.2) | `master/context_synth/` — `python -m master.context_synth one\|fill\|all\|status`. 909 source groups, all already documented from the snapshot. **Wired into the indexer** (changed files only). A **deterministic factuality gate** (`verify.py`) rejects docs describing commented-out code as live — **75% pass rate measured on the 35B (3/4)**, and the one rejection was a real catch. `sample N` dry-runs without touching snapshot docs. [중요] **BC-250 holds memory per request and never gives it back until the model unloads.** [주의] **Re-measured 2026-08-15**: ~60 MB for small requests (the old ~170 MB figure was larger prompts), and [중요] **`UNLOAD_EVERY` never actually fires** — its counter resets on every `_lane` call and our domains have 1–3 chunks per lane (measured: ~14 heavy-lane requests, 0 reclaims). The board went down twice; see `machines/bc250-1.md` |
| **찌꺼기 정리** — 워커의 로컬 브랜치·부산물 (중 2.5.4) | `master/work/cleanup.py` — `python -m master.work.cleanup plan\|apply`. [중요] **워커는 스스로 못 지운다**(스킬이 브랜치 삭제를 금지 — 의도된 설계). 삭제 기준은 하나: **팁이 `origin/<base>` 에서 도달 가능한가**. 도달 불가·확인 실패는 **보존**한다(fail-closed 의 방향이 여기서는 보존). [중요] **원격은 건드리지 않는다** — `push --delete` 는 사람의 판단. 부산물은 `verified`/`cancelled` 만 지우고 **`failed` 는 증거로 남긴다**. 우리 브랜치 위에 서 있으면 `main` 으로 되돌리고(체크아웃된 브랜치는 삭제 대상에서 빠지므로) **한 번 더 훑는다**. [주의] `--format` 은 셸별로 감싼다 — `%(...)` 의 괄호가 POSIX 문법이라 안 감싸면 리눅스 워커만 조용히 실패한다 |
| **계측 하네스** — 분산 대 단독 (토큰·시간·품질) | `master/bench.py` — `claude -p --output-format json` 의 usage 를 모아 팔별로 비교한다. 품질은 diff 의 식별자를 클래스 그래프와 대조([주의] enum·매크로는 오탐). [중요] **매니페스트를 실행 위치에 놓고 읽히는지 확인한 뒤에만 잰다** — 그걸 안 해서 첫 결과를 통째로 버렸다(리포트 11 §19). 실측: 4파일 묶음이 파일당 **3.2배 싸다**; 워커 2대는 이 크기에서 **12% 빠르고 90% 비싸다** |
| **워커 러너** — claim → 기준 재해석 → scp → `claude -p` → 마커 → submit (중 2.5.3) | `master/work/runner.py` — `python -m master.work.runner probe\|once\|loop`. [중요] **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(두 워커 모두 8101 이 401, AX MCP 0건이라 스킬의 전제가 틀려 있었다). 하트비트(리스 1200초)도 마스터가 대신 친다. [중요] 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄이고, 관대함은 **BLOCKED 쪽으로만** 연다. [중요] 기준 절은 **파견 시점에 다시 푼다** — durable 브랜치는 설계상 등록 이후 요청자가 만들므로 등록 시점 값은 반드시 낡는다. 선택 단계에서 **워킹트리까지 본다**(워커의 거부는 마지막 방어선이지 선택 기준이 아니다). 실측 e2e 71초 |
| **Worker bundle** — per-machine config · skill · CLAUDE.md merge, delivered over SSH (#21) | `master/client/` — `python -m master.client probe\|plan\|deliver\|check`. **Role-aware**: `worker` gets `ax-work`; `requester` (the human's PC) gets `ax-request`/`ax-ontology` and is **excluded from `drivable_hosts`** — `driven` (can we reach it) and `role` (may we dispatch to it) are different axes. [중요] **Paths are never hardcoded**: the master generates `<checkout>/.ax/config.json` from the registry, because a worker's config was found pointing at *another machine's* path. Capabilities are **probed, not declared**, and the block states the *consequence* ("no UE5 ⇒ layer-3 cannot be verified here"). CLAUDE.md is merged **marker-delimited** — human text is never overwritten. [중요] Delivery verifies by re-reading sha256; that caught PowerShell adding BOM/CRLF and an 18KB stdin hang, so transfers use `scp` |
| Ollama node check + remote install (no residency) | `master/provision.py` — `python -m master.provision check` |
| **2-tier branch topology + σ audit + indexing gate** (M4, 2026-08-14) | `master/work/coordinator.py` · `master/work/selftest.py` · `master/events/gate.py` · `master/sigma_audit.py` — see the top table for the detail. [중요] **This row exists because the two tables overlap**: the Korean table above is the SSOT, this one is a path lookup. When they disagree, the top one wins |
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

## 설계 제약

- **파일을 소유하지 않는다** — 추론 노드와는 텍스트만 왕복. 실제 파일 I/O·컴파일·코드 등록은
  작업자(윈도우). **여기는 인프라지 작업장이 아니다.**
- **추론 요청은 stateless**, **피드백 누적은 git**(`task/<task_id>` 브랜치). 두 경로 분리.
- 검증은 3층 게이트(워커 자기검증 → 상용 모델 문법검사 → 실제 UE5 빌드). `../PLAN.md` §4.3.

상세 계획: `../PLAN.md`
