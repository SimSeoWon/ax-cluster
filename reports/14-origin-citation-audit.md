# 리포트 14 — 원전 미참조 전수 조사 · 마일스톤 3 정지 · 2026-08-13

> 🔴 **이 리포트는 "무엇을 만들었나" 가 아니라 "무엇을 안 보고 만들었나" 의 기록이다.**
> 사용자 지시 3점(2026-08-13 23시): ① 이 작업은 **윈도우+UE5 에서 돌던 서버 데몬을 리눅스+Gitea
> 로 옮기는 OS·환경 변경**이다 ② 이전 세션들이 **기존 프로젝트(원전)를 참조하지 않고** 진행했다
> ③ **그래서 원전 안 본 것 전수 조사부터.** 이어서: 리포트 작성 · 인용 0건 전부 하나씩 재검토 ·
> 기존 마일스톤 진행 정지 · 새 마일스톤 레드마인 등재 · 영향도 분석.
>
> 앞 리포트: [13 — 파이프라인 완주·3층 판정·웹 UI 복각](13-milestone3-inference-dispatch.md)

## §0. 요약 — 네 줄

    A  토폴로지    원전에 답이 있었고 그 파일은 우리 저장소에서 **0회** 언급됐다
    B  열린 9건    그중 4건은 원전에 구현체(623·288·416·459줄)가 있는데 제목만 옮겨 적었다
    C  되먹임      원전의 되먹임 기계 5종 전부 인용 0. 우리는 그 자리를 새로 설계했다
    D  온톨로지    대부분은 **의도적 미이식**(자동승급 폐기 = 사용자 결정). 둘만 설명 없이 빠졌다

🔴 **셋(리포트 13 §18)이 아니라 패턴이었다.** 웹 UI·로그인·뷰어 셋은 사용자가 눈으로 본 화면에서
드러난 것이고, 화면이 없는 자리에서는 드러나지 않았을 뿐이다.

## §1. 측정 방법 — 인용 census, 그리고 그 한계

**추측으로 "안 읽은 것 같다" 고 적지 않기 위해** 셀 수 있는 지표를 썼다.

    대상    원전 py/md **170파일** (`tests/` · `plan_archive/` · `history/` 제외)
    코퍼스  우리 저장소 전체 md·py·yaml·json·unit + `~/claude-workspace/reports/`
            = **54,356줄** (`.git`·`ModularStage`(게임 소스)·`.venv` 제외)
    지표    원전 파일의 **basename 이 코퍼스에 나타난 횟수**. 0 = 읽은 흔적 없음의 후보

    결과    인용 0건   **74파일 23,710줄**
            인용 있음  96파일 37,001줄

그 다음 **개념 단위**로 다시 셌다(파일명이 아니라 `review_work`·`task_template`·`@ms-contract`
같은 식별자). 마지막으로 결론이 걸린 상위 4건은 **실물을 열어 확인**했다.

### 🔴 이 지표는 양방향으로 틀린다 — 그래서 상한이지 손실량이 아니다

| | 반례 | 확인 |
|---|---|---|
| **인용됨 ≠ 읽음** | 원전 `docs/` 8종은 **전부 1회 이상** 인용됐다. 그런데 마일스톤 3 문서 스스로 그중 4종(`README.md` 842 · `watcher-internals.md` 543 · `runbook.md` 280 · `extending.md` 251)을 **미독**이라 적어 뒀다 | 인용 4~7회는 *"안 읽었다고 적은 문장"* 이었다 |
| **인용 0 ≠ 미이식** | `mcp/task_queue/logic_lifecycle.py` 는 인용 0인데 `verify_task`/`submit_fail` 로 **실제 이식돼 있다** | 우리 코드에 7군데 확인 |
| **파일 수 ≠ 개념 수** | 인용 0건 74파일 중 상당수가 원전 내부 facade 리팩터링 산물(2026-07-18 분리)이라 개념으로는 중복 | `ontology_manage_*` 3종·`logic_*` 3종 등 |

→ **개념 단위 손실 목록은 §2~§5 넷**이고, 23,710줄은 조사 대상의 상한이다.

## §2. 결과 A — 🔴 토폴로지: 원전에 답이 있었고 인용 0회

`mcp/master_orchestrator/cluster_coordinator.py` **200줄**. 열어서 확인한 것:

    assign_attempt()     🔴 서버가 브랜치명을 배정 — 워커는 받은 이름을 쓸 뿐(구성 안 함)
    push_attempt()       워커가 ephemeral attempt 브랜치에 commit·push
    verify_and_merge()   🔴 서버가 검증 후 durable 에 merge·push
                         주석 원문: **"durable 단일 writer 보존"**
                         epoch 게이트: submit_epoch < current_epoch → zombie assignee 거부
    cleanup_attempts()   ephemeral 일괄 제거 · **durable 보존**
    fake_worker()        `worker_fn` 주입 — 원격 PC·LLM 없이 드라이런

### 2.1 🔴 「쓰는 주체는 하나」는 발명이 아니었다 — 원전에 있었고, 그 하나는 **서버**다

    원전       워커 → ephemeral `attempt/` push  ·  **서버**가 verify → durable merge·push
    내 재설계  워커 → 텍스트 응답만              ·  통합자 `.2` 가 적용·빌드·커밋

같은 문장(*"단일 writer"*)을 쓰면서 **다른 것을 했다.** 원전에서 워커는 **쓴다** — 다만 ephemeral
브랜치에만 쓴다. 나는 원칙을 `.2` 로 옮기면서 **attempt 계층 · epoch fencing · fake 워커 주입까지
같이 버렸다.**

🔴 **그래서 08-09 결정(*"attempt 를 성공·실패 무관 push"*)이 맞는 이유가 여기서 나온다** —
attempt 는 ephemeral 이므로 실패를 push 해도 durable 이 더러워지지 않는다. 리포트 12 §5.1 이
*"한 무리의 문제가 통째로 사라진다(워커 git 인증·`attempt/` 찌꺼기·CAS/펜싱의 절반)"* 라고 적은 것은
**문제가 사라진 게 아니라 원전이 이미 풀어 둔 장치를 버린 것**이었다. `cleanup_attempts` 가
찌꺼기를, `epoch` 게이트가 펜싱을 이미 맡고 있었다.

### 2.2 OS 가 강제하는 것은 **한 스텝**이다

원전 인프라 PC(윈도우, UE5) = `watch.exe`(RAG) + `task_queue` 데몬 + `auto_cleanup` +
🔴 **1차 통합 빌드 게이트** (`README.md:380`). 리눅스로 오면서 못 도는 것은 **그 빌드 게이트뿐**이다.

    `verify_and_merge` 안의 **UE5 빌드 한 스텝만** `.2` 로 원격 위임한다
    나머지(assign · attempt push · epoch fencing · merge · cleanup)는 리눅스에서 그대로 돈다

⚠️ **Gitea 조차 강제된 변경이 아니다.** 원전 `docs/distributed-workers.md:351–357` 이 브랜치 보호
락을 **GitHub / Gitea / 베어 git** 셋으로 표에 적고 *"현재 팀 환경에 맞는 방식은 구현 시점에 확정"*
이라 남겨 뒀다 — 우리는 그 칸을 골랐을 뿐이다.

### 2.3 영향도 — 라벨과 이슈

🔴 마일스톤 3 문서의 「토폴로지가 바뀌었다 — 쓰는 주체는 하나다 **(사용자 확정 2026-08-11)**」 는
라벨이 틀렸다(사용자 2026-08-13: 제안이 아니라 *"그래 해"* 였다). 본문 스스로
*"사용자의 첫 스케치는 메인 작업 PC였다"* 고 적어 제목과 모순이다. `settled-decisions.md` §214 도
같은 라벨이라 **다음 세션이 재논의를 거부하게 되어 있다.**

    전제가 틀린 9건   #75 #76 #77 #78 #83 #111 #113 #114 #115
    부분 수정 2건     #67 #107
    실측 확인         11건 **전부 「완료」 상태 그대로** — 재오픈 안 됨 (2026-08-13 23시)

⚠️ `#115` *"실패는 커밋하지 않는다"* 는 `docs/8-git-authority.md` §8.4 의 *"실패도 커밋한다"* 와
**이미 모순**이다. 원전 기준으로는 §8.4 가 맞다(ephemeral 이니까).

## §3. 결과 B — 열린 9건 중 4건은 원전에 구현체가 있는데 인용 0

| 이슈 | 원전에 있는 것 | 우리 인용 |
|---|---|---|
| `#95` /review-work | `executor_review_finalize.py` **623줄** (review_work/reject_work/finalize_work) + `skill_defs_collab.py` **755줄** | `review_work` **0** · `reject_work` **0** |
| `#96` 작업유형 템플릿 | `ontology_task_manage.py` **288줄** 레지스트리 + `task_template_tools.py` + CRUD 라우트 — **43파일**에 걸침 | `task_template` **0** |
| `#97` /cluster-selftest | `cluster_selftest.py` **416줄** + §2 의 `fake_worker` 주입 | 5 (제목만) |
| `#98` /tdd-dryrun·/debate | `tdd_dryrun.py` **459줄** + `skill_defs_collab.py` | 2 · 2 (제목만) |
| `#104` BM25 원자성 | `smoke_bm25_related_classes.py` + `search_log_analyzer.py` 696줄 | — |
| `#106` tool-calling 모델 | 🔴 **원전에 없다** (`tool_calls` 0파일) | ✅ 진짜 신규 |

🔴 마일스톤 문서에 `#96` 은 *"원본은 `task.yaml` 을 HTTP 로 워커에 먹였다"* 한 줄, `#98` 은
*"대화형 보조 둘"* 이 전부다. **제목만 옮겨 적고 구현체를 안 봤다.** `#106` 만 원전에 대응물이 없는
진짜 신규 항목이다 — 나머지는 설계가 아니라 **이식**이었어야 한다.

## §4. 결과 C — 되먹임 기계 5종 전부 인용 0

    watcher/planner.py             주간 개선 플랜 생성 (평일 리뷰 누적 → 주말 배치, 사람이 확인 후 실행)
    watcher/recipes_synthesizer.py 629줄 — code-writer 신호 누적 → 레시피 합성 (유휴 시간 호출)
    watcher/review_collector.py    리뷰 수집
    watcher/history_harvest.py     755줄 — `.claude/history`+`.gemini/history` 통합 파서
    watcher/issue_classifier.py    이슈 분류

우리는 **소 1.1.6 휴리스틱**(사람의 답)과 **소 2.3.4 실패 카탈로그**(기계의 실패)를 두 고리로
**새로 설계했다**(리포트 12 §9). 원전엔 되먹임 기계가 이미 5종 있고, 그중 `planner.py` 는
*"코드를 직접 수정하지 않는다 — 사람이 확인 후 실행"* 이라 **우리가 세운 원칙과 같은 원칙**으로
이미 돌고 있었다.

⚠️ 리포트 12 §9 가 *"원전은 앞쪽(기계) 만 있었다"* 고 적었는데 **틀렸다** — `planner`+`review_collector`
가 사람 확인 고리다. 그 문장은 원전을 안 보고 쓴 것이다.

## §5. 결과 D — 온톨로지 η 계열: 대부분 의도적, 둘은 설명 없이 빠짐

- ✅ **의도적**: `ontology_classifier` 계열(~2,000줄, η.1). **자동승급 영구 비활성이 사용자 결정**
  (리포트 11 §4 · 리포트 10 `[[project_auto_promotion_disabled]]`). **손실이 아니다.**
- 🔴 **의도적이라고 적힌 바 없이 빠진 것 둘** — 둘 다 **LLM 0 · 결정적**이라 이 저장소가 가장
  선호하는 부류(*"결정적 게이트가 LLM 판단보다 위"*)다:

| 원전 | 무엇 | 우리 |
|---|---|---|
| `watcher/ontology_declared.py` **332줄** | `.h` 헤더 주석 **`@ms-contract`** 태그 → 디지털 트윈 동기화. 배경: *"invariants 는 전부 LLM 추출"* 이라는 문제를 결정적으로 보완 | `ms-contract` **0건** |
| `watcher/ontology_invalidation.py` | **부분 무효화** — stale 도메인을 통짜 재합성하지 않고 변경 클래스가 영향 주는 yaml 만 재-LLM. LLM 0 순수 로직 | `invalidation` **0건** |

⚠️ 이 둘이 특히 아픈 이유: 마일스톤 3 이 *"환각을 결정적 게이트로 잡는다"* 를 주제로 삼았고
**자동화 테스트가 0개라 §4.3 의 「컴파일을 통과하는 환각」을 못 잡는다**고 적어 뒀는데,
`@ms-contract`(사람이 헤더에 박는 계약)는 정확히 **그 구멍에 들어가는 결정적 장치**다.

## §6. 개념 단위 실측표

    개념                        우리 코퍼스   원전 파일 수
    review_work                      0            23
    reject_work                      0            11
    task_template                    0            43
    cluster_coordinator              0             8
    review_collector                 0             9
    history_harvest                  0            14
    issue_classifier                 0             6
    @ms-contract                     0            10
    invalidation                     0            13
    ontology_classifier              0            53   ← ✅ 의도적(자동승급 폐기)
    tool_calls                       0             0   ← ✅ 원전에 없음 = 진짜 신규
    cluster_selftest                 5            14   ← 제목만
    tdd_dryrun                       2            15   ← 제목만
    debate                           2            38   ← 제목만

## §7. 인용 0건 74파일 하나씩 재검토 — 1차 분류

분류 기준 넷:

    ① 이식됨 (이름 같거나 다름)  → 손실 아님
    ② 미이식 · 의도적            → 근거 문서가 있다
    ③ 🔴 미이식 · 손실           → 근거 없이 빠졌다. **새 마일스톤의 작업 항목**
    ④ 해당 없음                  → 원전 환경 전용 · 내부 facade 분리 산물

### 7.1 🔴 census 의 방법론 구멍을 먼저 고쳤다

1차 census 는 코퍼스를 **파일 내용**으로만 만들었다. 그래서 **같은 이름으로 이식했지만 문서에서
언급한 적 없는 파일**이 「인용 0」으로 잡혔다. 실제로:

    mcp/task_queue/{logic.py, logic_claim.py, logic_cleanup.py, logic_lifecycle.py,
                    logic_persist.py, models.py, persistence.py, reclaim.py, server.py}
    → master/task_queue/ 에 **파일명 9개가 동일하게 존재한다** = 이식됨

→ 「우리 저장소의 실제 basename 목록」 차원을 추가했다. 🔴 **census 지표는 이렇게 스스로도 틀린다 —
그래서 상한이지 손실량이 아니다**(§1 과 같은 이야기가 한 번 더 나왔다).

### 7.2 ① 이식됨 — 손실 아님 (28파일)

| 원전 | 우리 대응물 | 근거 |
|---|---|---|
| `task_queue/{logic_lifecycle,logic_persist,models}.py` | `master/task_queue/` 동명 | 🔴 **확인** — 파일 9개 동명 + `verify_task`/`submit_fail` 7군데 |
| `ontology_{synthesizer,refresh,pkg_audit,descriptions,drift,rename,path_sync,index_sync,prompt,loaders,types}.py` | `master/ontology/{synth,stale,package,layers,drift,edit,sync,prompt,parse}.py` + `context_search/domain_index.py` | ⚠️ **추정** — 이름이 짧아졌다. 라이브 실측이 뒷받침: 도메인 7개 · tier · objects · tags 정상 |
| `watcher/ontology_actions.py` (580) | 액션 카탈로그 | 🔴 **확인** — 라이브 측정: 도메인별 actions **5~14개** 존재 |
| `class_graph_ontology.py` · `class_graph_query.py` | `master/graph/` + `master/ontology/` | ⚠️ 추정 |
| `context_search/ontology_{query,mutation}_tools.py` · `ontology_routes.py` · `ontology_route_queries.py` · `ontology_manage_routes.py` · `ontology_manage_util.py` · `audit_{tools,routes}.py` · `search_routes.py` · `search_graph_tools.py` · `wiki_routes.py` | **MCP 도구 24종**(`projects/mcp_server.py`) + `webui/routes.py` | 🔴 표면이 **HTTP → MCP** 로 바뀐 아키텍처 차이. §7.5 참조 |
| `worker/task_client.py` | `master/work/infer.py` | 파견 채널이 **폴링 → SSH** 로 바뀜 |
| `master_orchestrator/executor.py` (39줄) | — | ④ facade 분리 산물 |

### 7.3 ② 미이식 · 의도적 — 근거 있음 (7파일 ~2,400줄)

| 원전 | 근거 |
|---|---|
| `ontology_classifier.py` 228 · `domain_upgrader.py` 178 · `scripts/ontology_dryrun.py` **1228** | 🔴 **자동승급 영구 비활성 = 사용자 결정** (리포트 11 §4 · 리포트 10 `[[project_auto_promotion_disabled]]`) |
| `wiki_nondev_expansion_plan_v1.0.md` 293 · `packaging/wiki_client/{INSTALL_GUIDE,my_thesaurus_template}.md` | 🕓 **비개발 직군·팀 배포 = 마일스톤 밖**(1인 구도 판단 보류) |
| `ax_incubating_workflow_plan_v1.0.md` 320 | 🕓 조직 구조(팀당 3~4인) — 같은 이유 |
| `tools/LICENSES/PLACEHOLDER.md` 8 | ④ 해당 없음 |

⚠️ 단 **②는 "지금 안 한다" 이지 "안 읽어도 된다" 가 아니다** — `ax_incubating` 320줄은 Redmine·Wiki
계층 매핑과 계측 4필드 스키마를 담고 있어 **우리 레드마인 규약과 충돌 여부를 확인해야 한다.**

### 7.4 🔴 ③ 미이식 · 손실 — 39파일 (새 마일스톤 작업 항목)

**7.4-A 토폴로지 (2건 · 663줄) — §2 에서 확인**

    cluster_coordinator.py 200            assign/attempt push/verify_and_merge/epoch fencing/fake_worker
    local_llm_distributed_workers_plan_v5.0.md 463   🔴 **사용자 확정 설계가 문서로 있다**

🔴 이 계획 문서의 목차가 결정적이다 — **전부 「사용자 확정」이 붙어 있다**:

    C.1  2-tier 브랜치 (durable task + ephemeral attempt)   ✅ 사용자 2026-06-13 확정
    C.2  분배 모델: pull → push (서버 분배)                  ✅ 방향 확정 (사용자 2026-06-13)
    C.3  피드백 루프 연속성 + **Git-as-feedback-bus**        (사용자 2026-06-13 핵심 통찰)
    C.4  N-워커 안전 (인터페이스 동결 — 강제)                ✅ 사용자 2026-06-21
    C.5  ~~인터페이스 리비전 사이클 (`/debate` Layer 1)~~ → 먼 백로그 강등 (전제 미충족)
    C.7  push 모드 리더 최종 통합·빌드                       ✅ 토폴로지 확정 (사용자 2026-06-21)
    κ.0  오케스트레이션 2층(인프라 클러스터 + 워커), **윈도우는 요청자 + 엔진 실행**

⚠️ **C.5 가 `/debate` 를 「전제 미충족」으로 강등해 뒀다.** 우리 `#98` 은 그 강등을 모르고 되살리려는
칸이다 — **이식이 아니라 재논의 대상**이다.
🔴 **C.7 「리더 최종 통합·빌드」가 우리 "통합자" 의 원본이다.** 즉 통합자 개념 자체는 원전에 있었고,
내가 없앤 것은 그 앞단(워커의 ephemeral push)이다.

**7.4-B 열린 이슈에 직결 (4건 · 1,775줄)** — §3 의 표

    executor_review_finalize.py 623 + skill_defs_collab.py 755   #95 /review-work · #98 /debate
    ontology_task_manage.py 288 + task_template_tools.py 109     #96 작업유형 템플릿
    cluster_selftest.py 416 (인용 5, 제목만) + fake_worker         #97 /cluster-selftest
    tdd_dryrun.py 459 (인용 2, 제목만)                            #98 /tdd-dryrun

🔴 **`#96` 은 라우트가 이미 있고 데이터만 없다** (라이브 실측):
`GET /api/v1/ontology/task/refactor` → `404 {"detail":"태스크 템플릿은 이 저장소에 아직 없다"}`.
정직한 메시지이지만, **원전엔 그 레지스트리가 288+109줄로 있다.**

**7.4-C 결정적 온톨로지 장치 2건 (522줄)** — §5

    ontology_declared.py 332    `@ms-contract` 헤더 주석 → 트윈 동기화. LLM 0
    ontology_invalidation.py 190  부분 무효화(영향 yaml 만 재-LLM). LLM 0  🔴 탐침 0건 확인

**7.4-D 되먹임 기계 7건 (2,287줄)** — §4. 🔴 `history_harvest` 탐침 **0건 확인**

    planner.py 143 · plan_generator.py 432 · plan_dedup.py 67 · review_collector.py 137
    issue_classifier.py 124 · recipes_synthesizer.py 629 · history_harvest.py 755

**7.4-E 감사·복구·튜닝 채널 5건 (1,893줄)**

    context_audit.py 737 + audit_tools/audit_routes    컨텍스트 MD 감사·복구·재생성
    search_log_analyzer.py 696 + rag_report.py 56      검색 채널 분석·튜닝 → 🔴 `#104` 와 연결
    client_index.py 199 + ontology_client_cache.py 165 클라이언트 로컬 RAG·폴백. 🔴 탐침 0건 확인

**7.4-F 운영 가드 2건 (314줄) — 🔴 이 둘이 우리 파이프라인과 직접 충돌한다**

    watch_state.py 233   🔴 **분산 작업 활성 검사 = Git 폴링 일시 중지 조건.**
                         우리는 `ax-indexer.path` 가 push 마다 색인을 깨운다 —
                         파이프라인이 커밋하는 중에 색인이 도는 것을 막는 장치가 **없다**
    worker/safety.py 81  워커 안전 가드(운영 워커 8 task 검증됨 — `audit_matrix.md` 확인)

**7.4-G 방법론·규범 문서 3건 (2,517줄) — 🔴 가장 아픈 셋**

| 원전 | 무엇 | 왜 아픈가 |
|---|---|---|
| `.agents/AGENTS.md` **21줄** | Antigravity 행동 수칙 5조. **3조 = "모호성 제거 — 임의로 해석하여 행동에 나서지 말고 반드시 질문"**. 1조 임의 수정 금지 · 5조 **직접 빌드·커밋 금지** | 🔴 **사용자가 2026-08-13 에 다섯 번 말한 그 규칙이 원전에 이미 문서로 있었다.** 우리는 그 규칙을 세 번 잃고 나서 `CLAUDE.md` 에 적었다 |
| `.claude/reviews/_silent_failure/audit_matrix.md` **99줄** | **Silent Failure 감사 매트릭스**(σ.1 발동 흔적 매핑 + σ.2 정적 검사). 원문: *"plan 의 `[x]` 가 실 작업 완료를 의미하지 않은 한 가지 사례"* — silent failure **4건**을 그렇게 찾아냈다 | 🔴 **오늘 내가 한 감사의 방법론이 원전에 이미 있었다.** 그리고 *"분모/분자를 손으로 적지 않는다"* 규칙의 원본이 여기다 |
| `plan_completed_v4.5.md` **2397줄** | v4.5 era 완료 기록 | 🔴 **"이미 만들어져 있는 것" 목록**이다. 이걸 안 읽은 것이 뷰어 229줄 사건의 구조적 원인 |

**7.4-H 나머지 (6건 · 1,393줄)** — 재검토 필요, 부분 이식 가능

    ontology_drift_mcp.py 329 · ontology_refresh_mcp.py 240 · ontology_manage_rename.py 323
      → 우리 `drift_audit_tool`/`sync_ontology_tool`/`edit_ontology_item_tool` 이 일부를 덮는다.
        🔴 **개명 cascade** 는 우리 도구에 없다(도메인·클래스명이 디렉토리·DB키·URL 에 박힌다)
    log_tagging_candidates.py 240 + ontology_log_tags.py 132  태깅 실증(η.12.3) — ②와 경계
    analyzer.py 269 + executor_helpers.py 305                 orchestrator 보조
    scripts/agy_probe.py 227 + tools/agy_apply.py 85          🔴 **agy 라이브 검증** —
      우리 메모리에 *"agy 는 출처를 지어낸다"* 가 있는데 원전엔 그 **드라이테스트가 있었다**

### 7.5 ⚠️ 라우트 79 vs 11 은 손실 지표가 **아니다**

원전 `context_search` 는 `/api/v1/` 라우트 **79개**, 우리는 **11개**다. 그러나:

    우리 마스터는 **MCP 도구 우선** — 같은 기능이 HTTP 가 아니라 MCP 도구 24종으로 나 있다
    🔴 복각 프론트엔드가 **실제로 호출하는** 라우트는 7종이고, 라이브 실측 **전부 등록돼 있다**
       (`object/{domain}/{class}`·`action/{domain}/{name}` 은 2세그먼트 — 1세그먼트로 재면 오탐)

⚠️ **내가 이 자리에서 오탐을 두 번 냈다**(1세그먼트 테스트 · 존재하지 않는 액션 이름). 라이브로
재고 응답 **본문**까지 읽어서야 갈렸다 — *"라우트 미등록"* 과 *"자원 없음"* 은 둘 다 404 다.

## §8. 영향도 분석

### 8.1 닫힌 42건 중 전제가 흔들리는 것

    전제가 틀린 9건   #75 #76 #77 #78 #83 #111 #113 #114 #115   (중 1.3 · 중 1.4 · 소 2.1.3)
    부분 수정 2건     #67 #107
    영향 없는 31건    분해 · 층2 · 층3 · 웹 UI · 골조 · 규범 · 색인

🔴 **닫힌 42건을 소급해 열지 않는다** — 리포트 12 §5.4 가 이미 정한 규칙(*"소급해서 열면 기록이
거짓이 된다"*). 당시 실제로 돌았고 실측도 있다. 대신 **새 마일스톤에서 재검토 항목으로 다시 세운다.**

### 8.2 열린 9건의 성격이 바뀐다

    #95 #96 #97 #98   설계 → 🔴 **이식**(원전에 623·397·416·459줄이 있다)
    #98 의 /debate    🔴 원전이 **「전제 미충족」으로 강등**해 둔 것 → 재논의 대상
    #104              원전 `search_log_analyzer` 696 + `smoke_bm25_related_classes` 가 있다
    #105              영향 없음 (하드웨어 실측)
    #106              ✅ 진짜 신규 — 원전에 `tool_calls` 0파일

### 8.3 🔴 코드에 이미 난 구멍 하나 (파이프라인 ↔ 색인)

`watch_state.py` 의 *"분산 작업 활성 검사 = Git 폴링 일시 중지"* 가 우리에게 없다. 우리는
`ax-indexer.path` 가 **push 마다** 색인을 깨우는데, 통합자가 조각마다 커밋·push 하므로
**한 work 안에서 색인이 여러 번 깨어난다.** 원전은 그 자리에 게이트를 뒀다.
⚠️ 실사용 문제인지는 **아직 안 쟀다** — `#104`(BM25 원자성)와 같은 자리일 가능성이 있다.

### 8.4 문서·라벨

    docs/milestones/3-work-pipeline.md   토폴로지 절 라벨 정정 (커밋 안 된 경고 블록 → 본문 반영)
    docs/settled-decisions.md §214       같은 라벨 → 정정. 🔴 안 고치면 다음 세션이 재논의를 거부한다
    docs/8-git-authority.md §8.4         「누가 무엇을 만드나」 표 재검토 (#115 와 이미 모순)
    reports/12-*.md §5.1                 *"한 무리의 문제가 사라진다"* → **장치를 버린 것**이었다
    reports/12-*.md §9                   *"원전은 앞쪽(기계)만 있었다"* → 🔴 **틀렸다**(planner 가 사람 고리)
    CLAUDE.md 양쪽                       원전 필독 목록에 `.agents/AGENTS.md` · `audit_matrix.md` ·
                                         `local_llm_distributed_workers_plan_v5.0.md` 추가


## §9. 마일스톤 3 정지 · 마일스톤 4 신설 (✅ 완료)

### 9.1 🔴 「진행 정지」를 어떻게 표현했나

상태 5종에 **「보류」가 없다**(1 신규 · 2 진행 · 3 해결 · 5 검토 · 4 완료). 이슈 상태로는
정지를 못 적는다. 🔴 **대신 버전에 `locked` 이 있고 그게 정확히 진행 정지다** — 기존 이슈는
남고 새 배정만 막히며 `open` 으로 되돌릴 수 있다.

    마일스톤 2 — 디지털 트윈 복원      closed
    마일스톤 3 — 실작업 파이프라인     🔴 **locked** (2026-08-13)   총 51 · 완료 42 · 열림 9
    마일스톤 4 — 원전 대조·재이식      open  (version id=3)         총 62 = 중 17 + 소 45

⚠️ **닫힌 42건을 소급해 열지 않았다** — 리포트 12 §5.4 의 규칙(*"소급해서 열면 기록이 거짓이
된다"*). 전제가 틀린 11건은 **마일스톤 4 의 재검토 항목으로 다시 세웠다.**

### 9.2 마일스톤 4 구조 — 대 4 / 중 17 / 소 45

🔴 **분자도 분모도 이 문서에 적지 않는다**(version *마일스톤 4* 가 센다). 구조만 남긴다.

| 대 | 중 | 이슈 |
|---|---|---|
| **대 1 토폴로지 원복** | 1.1 원전 설계 문서 정독 · 1.2 2-tier 복원 · 1.3 빌드 게이트만 `.2` 위임 · 1.4 문서·라벨 정정 | `#117` `#121` `#127` `#130` |
| **대 2 열린 4건을 이식으로 전환** | 2.1 /review-work · 2.2 작업유형 템플릿 · 2.3 /cluster-selftest · 2.4 /tdd-dryrun 이식 + **/debate 재논의** | `#135` `#138` `#141` `#144` |
| **대 3 미이식 자산 재검토·이식** | 3.1 ①추정 이식분 실물 대조 · 3.2 결정적 온톨로지 장치 · 3.3 되먹임 7종 · 3.4 감사·복구·튜닝 · 3.5 운영 가드 · 3.6 나머지+개명 cascade | `#147` `#151` `#154` `#159` `#163` `#166` |
| **대 4 방법론·규범 회수** | 4.1 `AGENTS.md` 5조 · 4.2 silent failure 감사 · 4.3 원전 필독 목록 제도화 | `#172` `#174` `#177` |

**사슬**: 🔴 **1.1 이 상류다** — 설계 문서를 안 읽고 1.2 를 하면 같은 실수를 반복한다.
`1.2.5 fake_worker → 2.3.2` (드라이런이 셀프테스트의 전제) · `1.2 → 1.3`(게이트는 merge 안의
한 스텝) · 대 3·대 4 는 사슬 밖이라 병행 가능. ⚠️ **`2.4.2` 는 작업이 아니라 질문이다**(C.5 강등).

### 9.3 열린 9건에 단 노트

    #95 #96 #97 #98 #104   「설계 → 이식」으로 성격 변경 + 대체 칸이 M4 에 있음 + 여기서 진행 안 함
    #93 #103 #105          영향 없음. 순서상 M4 가 먼저
    #106                   ✅ 원전에 대응물 없음 = 진짜 신규로 확인

노트 9/9 성공. 🔴 **상태는 건드리지 않았다** — 「진행 정지」는 버전이 표현하고, 이슈 상태를
손으로 바꾸면 분자가 거짓이 된다.

## §10. 남은 것 · 다음

    🕓 소 45개 실제 수행     이 리포트는 **무엇을 재검토할지**까지다. 재검토 자체는 M4 의 작업이다
    🕓 ①추정 11파일          온톨로지 이식분은 라이브 데이터로 뒷받침될 뿐 파일 대조는 안 했다 (소 3.1.1)
    🕓 소 3.5.1 측정 먼저    파이프라인↔색인 충돌이 실사용 문제인지 **재고 나서** 고친다 (추측 금지)
    🔴 다음 작업은 사용자가 정한다 — 대 1 이 상류지만 순서는 사용자의 몫이다

### 🔴 이 세션이 남기는 한 줄

**제약을 지키려고 요구를 희생하지 않는 것만으로는 부족했다 — 만들기 전에 그 자리에 무엇이
있는지 재는 절차가 없으면 같은 일이 반복된다.** census 는 그 절차의 초안이고, 스스로도 두 번
틀렸다(§1 · §7.1). 그 한계까지 같이 남긴다.
