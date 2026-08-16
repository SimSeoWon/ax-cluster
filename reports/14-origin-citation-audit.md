# 리포트 14 — 원전 미참조 전수 조사 · 마일스톤 3 정지 · 2026-08-13

> [중요] **이 리포트는 "무엇을 만들었나" 가 아니라 "무엇을 안 보고 만들었나" 의 기록이다.**
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

[중요] **셋(리포트 13 §18)이 아니라 패턴이었다.** 웹 UI·로그인·뷰어 셋은 사용자가 눈으로 본 화면에서
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

### [중요] 이 지표는 양방향으로 틀린다 — 그래서 상한이지 손실량이 아니다

| | 반례 | 확인 |
|---|---|---|
| **인용됨 ≠ 읽음** | 원전 `docs/` 8종은 **전부 1회 이상** 인용됐다. 그런데 마일스톤 3 문서 스스로 그중 4종(`README.md` 842 · `watcher-internals.md` 543 · `runbook.md` 280 · `extending.md` 251)을 **미독**이라 적어 뒀다 | 인용 4~7회는 *"안 읽었다고 적은 문장"* 이었다 |
| **인용 0 ≠ 미이식** | `mcp/task_queue/logic_lifecycle.py` 는 인용 0인데 `verify_task`/`submit_fail` 로 **실제 이식돼 있다** | 우리 코드에 7군데 확인 |
| **파일 수 ≠ 개념 수** | 인용 0건 74파일 중 상당수가 원전 내부 facade 리팩터링 산물(2026-07-18 분리)이라 개념으로는 중복 | `ontology_manage_*` 3종·`logic_*` 3종 등 |

→ **개념 단위 손실 목록은 §2~§5 넷**이고, 23,710줄은 조사 대상의 상한이다.

## §2. 결과 A — [중요] 토폴로지: 원전에 답이 있었고 인용 0회

`mcp/master_orchestrator/cluster_coordinator.py` **200줄**. 열어서 확인한 것:

    assign_attempt()     [중요] 서버가 브랜치명을 배정 — 워커는 받은 이름을 쓸 뿐(구성 안 함)
    push_attempt()       워커가 ephemeral attempt 브랜치에 commit·push
    verify_and_merge()   [중요] 서버가 검증 후 durable 에 merge·push
                         주석 원문: **"durable 단일 writer 보존"**
                         epoch 게이트: submit_epoch < current_epoch → zombie assignee 거부
    cleanup_attempts()   ephemeral 일괄 제거 · **durable 보존**
    fake_worker()        `worker_fn` 주입 — 원격 PC·LLM 없이 드라이런

### 2.1 [중요] 「쓰는 주체는 하나」는 발명이 아니었다 — 원전에 있었고, 그 하나는 **서버**다

    원전       워커 → ephemeral `attempt/` push  ·  **서버**가 verify → durable merge·push
    내 재설계  워커 → 텍스트 응답만              ·  통합자 `.2` 가 적용·빌드·커밋

같은 문장(*"단일 writer"*)을 쓰면서 **다른 것을 했다.** 원전에서 워커는 **쓴다** — 다만 ephemeral
브랜치에만 쓴다. 나는 원칙을 `.2` 로 옮기면서 **attempt 계층 · epoch fencing · fake 워커 주입까지
같이 버렸다.**

[중요] **그래서 08-09 결정(*"attempt 를 성공·실패 무관 push"*)이 맞는 이유가 여기서 나온다** —
attempt 는 ephemeral 이므로 실패를 push 해도 durable 이 더러워지지 않는다. 리포트 12 §5.1 이
*"한 무리의 문제가 통째로 사라진다(워커 git 인증·`attempt/` 찌꺼기·CAS/펜싱의 절반)"* 라고 적은 것은
**문제가 사라진 게 아니라 원전이 이미 풀어 둔 장치를 버린 것**이었다. `cleanup_attempts` 가
찌꺼기를, `epoch` 게이트가 펜싱을 이미 맡고 있었다.

### 2.2 OS 가 강제하는 것은 **한 스텝**이다

원전 인프라 PC(윈도우, UE5) = `watch.exe`(RAG) + `task_queue` 데몬 + `auto_cleanup` +
[중요] **1차 통합 빌드 게이트** (`README.md:380`). 리눅스로 오면서 못 도는 것은 **그 빌드 게이트뿐**이다.

    `verify_and_merge` 안의 **UE5 빌드 한 스텝만** `.2` 로 원격 위임한다
    나머지(assign · attempt push · epoch fencing · merge · cleanup)는 리눅스에서 그대로 돈다

[주의] **Gitea 조차 강제된 변경이 아니다.** 원전 `docs/distributed-workers.md:351–357` 이 브랜치 보호
락을 **GitHub / Gitea / 베어 git** 셋으로 표에 적고 *"현재 팀 환경에 맞는 방식은 구현 시점에 확정"*
이라 남겨 뒀다 — 우리는 그 칸을 골랐을 뿐이다.

### 2.3 영향도 — 라벨과 이슈

[중요] 마일스톤 3 문서의 「토폴로지가 바뀌었다 — 쓰는 주체는 하나다 **(사용자 확정 2026-08-11)**」 는
라벨이 틀렸다(사용자 2026-08-13: 제안이 아니라 *"그래 해"* 였다). 본문 스스로
*"사용자의 첫 스케치는 메인 작업 PC였다"* 고 적어 제목과 모순이다. `settled-decisions.md` §214 도
같은 라벨이라 **다음 세션이 재논의를 거부하게 되어 있다.**

    전제가 틀린 9건   #75 #76 #77 #78 #83 #111 #113 #114 #115
    부분 수정 2건     #67 #107
    실측 확인         11건 **전부 「완료」 상태 그대로** — 재오픈 안 됨 (2026-08-13 23시)

[주의] `#115` *"실패는 커밋하지 않는다"* 는 `docs/8-git-authority.md` §8.4 의 *"실패도 커밋한다"* 와
**이미 모순**이다. 원전 기준으로는 §8.4 가 맞다(ephemeral 이니까).

## §3. 결과 B — 열린 9건 중 4건은 원전에 구현체가 있는데 인용 0

| 이슈 | 원전에 있는 것 | 우리 인용 |
|---|---|---|
| `#95` /review-work | `executor_review_finalize.py` **623줄** (review_work/reject_work/finalize_work) + `skill_defs_collab.py` **755줄** | `review_work` **0** · `reject_work` **0** |
| `#96` 작업유형 템플릿 | `ontology_task_manage.py` **288줄** 레지스트리 + `task_template_tools.py` + CRUD 라우트 — **43파일**에 걸침 | `task_template` **0** |
| `#97` /cluster-selftest | `cluster_selftest.py` **416줄** + §2 의 `fake_worker` 주입 | 5 (제목만) |
| `#98` /tdd-dryrun·/debate | `tdd_dryrun.py` **459줄** + `skill_defs_collab.py` | 2 · 2 (제목만) |
| `#104` BM25 원자성 | `smoke_bm25_related_classes.py` + `search_log_analyzer.py` 696줄 | — |
| `#106` tool-calling 모델 | [중요] **원전에 없다** (`tool_calls` 0파일) | [완료] 진짜 신규 |

[중요] 마일스톤 문서에 `#96` 은 *"원본은 `task.yaml` 을 HTTP 로 워커에 먹였다"* 한 줄, `#98` 은
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

[주의] 리포트 12 §9 가 *"원전은 앞쪽(기계) 만 있었다"* 고 적었는데 **틀렸다** — `planner`+`review_collector`
가 사람 확인 고리다. 그 문장은 원전을 안 보고 쓴 것이다.

## §5. 결과 D — 온톨로지 η 계열: 대부분 의도적, 둘은 설명 없이 빠짐

- [완료] **의도적**: `ontology_classifier` 계열(~2,000줄, η.1). **자동승급 영구 비활성이 사용자 결정**
  (리포트 11 §4 · 리포트 10 `[[project_auto_promotion_disabled]]`). **손실이 아니다.**
- [중요] **의도적이라고 적힌 바 없이 빠진 것 둘** — 둘 다 **LLM 0 · 결정적**이라 이 저장소가 가장
  선호하는 부류(*"결정적 게이트가 LLM 판단보다 위"*)다:

| 원전 | 무엇 | 우리 |
|---|---|---|
| `watcher/ontology_declared.py` **332줄** | `.h` 헤더 주석 **`@ms-contract`** 태그 → 디지털 트윈 동기화. 배경: *"invariants 는 전부 LLM 추출"* 이라는 문제를 결정적으로 보완 | `ms-contract` **0건** |
| `watcher/ontology_invalidation.py` | **부분 무효화** — stale 도메인을 통짜 재합성하지 않고 변경 클래스가 영향 주는 yaml 만 재-LLM. LLM 0 순수 로직 | `invalidation` **0건** |

[주의] 이 둘이 특히 아픈 이유: 마일스톤 3 이 *"환각을 결정적 게이트로 잡는다"* 를 주제로 삼았고
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
    ontology_classifier              0            53   ← [완료] 의도적(자동승급 폐기)
    tool_calls                       0             0   ← [완료] 원전에 없음 = 진짜 신규
    cluster_selftest                 5            14   ← 제목만
    tdd_dryrun                       2            15   ← 제목만
    debate                           2            38   ← 제목만

## §7. 인용 0건 74파일 하나씩 재검토 — 1차 분류

분류 기준 넷:

    ① 이식됨 (이름 같거나 다름)  → 손실 아님
    ② 미이식 · 의도적            → 근거 문서가 있다
    ③ [중요] 미이식 · 손실           → 근거 없이 빠졌다. **새 마일스톤의 작업 항목**
    ④ 해당 없음                  → 원전 환경 전용 · 내부 facade 분리 산물

### 7.1 [중요] census 의 방법론 구멍을 먼저 고쳤다

1차 census 는 코퍼스를 **파일 내용**으로만 만들었다. 그래서 **같은 이름으로 이식했지만 문서에서
언급한 적 없는 파일**이 「인용 0」으로 잡혔다. 실제로:

    mcp/task_queue/{logic.py, logic_claim.py, logic_cleanup.py, logic_lifecycle.py,
                    logic_persist.py, models.py, persistence.py, reclaim.py, server.py}
    → master/task_queue/ 에 **파일명 9개가 동일하게 존재한다** = 이식됨

→ 「우리 저장소의 실제 basename 목록」 차원을 추가했다. [중요] **census 지표는 이렇게 스스로도 틀린다 —
그래서 상한이지 손실량이 아니다**(§1 과 같은 이야기가 한 번 더 나왔다).

### 7.2 ① 이식됨 — 손실 아님 (28파일)

| 원전 | 우리 대응물 | 근거 |
|---|---|---|
| `task_queue/{logic_lifecycle,logic_persist,models}.py` | `master/task_queue/` 동명 | [중요] **확인** — 파일 9개 동명 + `verify_task`/`submit_fail` 7군데 |
| `ontology_{synthesizer,refresh,pkg_audit,descriptions,drift,rename,path_sync,index_sync,prompt,loaders,types}.py` | `master/ontology/{synth,stale,package,layers,drift,edit,sync,prompt,parse}.py` + `context_search/domain_index.py` | [주의] **추정** — 이름이 짧아졌다. 라이브 실측이 뒷받침: 도메인 7개 · tier · objects · tags 정상 |
| `watcher/ontology_actions.py` (580) | 액션 카탈로그 | [중요] **확인** — 라이브 측정: 도메인별 actions **5~14개** 존재 |
| `class_graph_ontology.py` · `class_graph_query.py` | `master/graph/` + `master/ontology/` | [주의] 추정 |
| `context_search/ontology_{query,mutation}_tools.py` · `ontology_routes.py` · `ontology_route_queries.py` · `ontology_manage_routes.py` · `ontology_manage_util.py` · `audit_{tools,routes}.py` · `search_routes.py` · `search_graph_tools.py` · `wiki_routes.py` | **MCP 도구 24종**(`projects/mcp_server.py`) + `webui/routes.py` | [중요] 표면이 **HTTP → MCP** 로 바뀐 아키텍처 차이. §7.5 참조 |
| `worker/task_client.py` | `master/work/infer.py` | 파견 채널이 **폴링 → SSH** 로 바뀜 |
| `master_orchestrator/executor.py` (39줄) | — | ④ facade 분리 산물 |

### 7.3 ② 미이식 · 의도적 — 근거 있음 (7파일 ~2,400줄)

| 원전 | 근거 |
|---|---|
| `ontology_classifier.py` 228 · `domain_upgrader.py` 178 · `scripts/ontology_dryrun.py` **1228** | [중요] **자동승급 영구 비활성 = 사용자 결정** (리포트 11 §4 · 리포트 10 `[[project_auto_promotion_disabled]]`) |
| `wiki_nondev_expansion_plan_v1.0.md` 293 · `packaging/wiki_client/{INSTALL_GUIDE,my_thesaurus_template}.md` | [대기] **비개발 직군·팀 배포 = 마일스톤 밖**(1인 구도 판단 보류) |
| `ax_incubating_workflow_plan_v1.0.md` 320 | [대기] 조직 구조(팀당 3~4인) — 같은 이유 |
| `tools/LICENSES/PLACEHOLDER.md` 8 | ④ 해당 없음 |

[주의] 단 **②는 "지금 안 한다" 이지 "안 읽어도 된다" 가 아니다** — `ax_incubating` 320줄은 Redmine·Wiki
계층 매핑과 계측 4필드 스키마를 담고 있어 **우리 레드마인 규약과 충돌 여부를 확인해야 한다.**

### 7.4 [중요] ③ 미이식 · 손실 — 39파일 (새 마일스톤 작업 항목)

**7.4-A 토폴로지 (2건 · 663줄) — §2 에서 확인**

    cluster_coordinator.py 200            assign/attempt push/verify_and_merge/epoch fencing/fake_worker
    local_llm_distributed_workers_plan_v5.0.md 463   [중요] **사용자 확정 설계가 문서로 있다**

[중요] 이 계획 문서의 목차가 결정적이다 — **전부 「사용자 확정」이 붙어 있다**:

    C.1  2-tier 브랜치 (durable task + ephemeral attempt)   [완료] 사용자 2026-06-13 확정
    C.2  분배 모델: pull → push (서버 분배)                  [완료] 방향 확정 (사용자 2026-06-13)
    C.3  피드백 루프 연속성 + **Git-as-feedback-bus**        (사용자 2026-06-13 핵심 통찰)
    C.4  N-워커 안전 (인터페이스 동결 — 강제)                [완료] 사용자 2026-06-21
    C.5  ~~인터페이스 리비전 사이클 (`/debate` Layer 1)~~ → 먼 백로그 강등 (전제 미충족)
    C.7  push 모드 리더 최종 통합·빌드                       [완료] 토폴로지 확정 (사용자 2026-06-21)
    κ.0  오케스트레이션 2층(인프라 클러스터 + 워커), **윈도우는 요청자 + 엔진 실행**

[주의] **C.5 가 `/debate` 를 「전제 미충족」으로 강등해 뒀다.** 우리 `#98` 은 그 강등을 모르고 되살리려는
칸이다 — **이식이 아니라 재논의 대상**이다.
[중요] **C.7 「리더 최종 통합·빌드」가 우리 "통합자" 의 원본이다.** 즉 통합자 개념 자체는 원전에 있었고,
내가 없앤 것은 그 앞단(워커의 ephemeral push)이다.

**7.4-B 열린 이슈에 직결 (4건 · 1,775줄)** — §3 의 표

    executor_review_finalize.py 623 + skill_defs_collab.py 755   #95 /review-work · #98 /debate
    ontology_task_manage.py 288 + task_template_tools.py 109     #96 작업유형 템플릿
    cluster_selftest.py 416 (인용 5, 제목만) + fake_worker         #97 /cluster-selftest
    tdd_dryrun.py 459 (인용 2, 제목만)                            #98 /tdd-dryrun

[중요] **`#96` 은 라우트가 이미 있고 데이터만 없다** (라이브 실측):
`GET /api/v1/ontology/task/refactor` → `404 {"detail":"태스크 템플릿은 이 저장소에 아직 없다"}`.
정직한 메시지이지만, **원전엔 그 레지스트리가 288+109줄로 있다.**

**7.4-C 결정적 온톨로지 장치 2건 (522줄)** — §5

    ontology_declared.py 332    `@ms-contract` 헤더 주석 → 트윈 동기화. LLM 0
    ontology_invalidation.py 190  부분 무효화(영향 yaml 만 재-LLM). LLM 0  [중요] 탐침 0건 확인

**7.4-D 되먹임 기계 7건 (2,287줄)** — §4. [중요] `history_harvest` 탐침 **0건 확인**

    planner.py 143 · plan_generator.py 432 · plan_dedup.py 67 · review_collector.py 137
    issue_classifier.py 124 · recipes_synthesizer.py 629 · history_harvest.py 755

**7.4-E 감사·복구·튜닝 채널 5건 (1,893줄)**

    context_audit.py 737 + audit_tools/audit_routes    컨텍스트 MD 감사·복구·재생성
    search_log_analyzer.py 696 + rag_report.py 56      검색 채널 분석·튜닝 → [중요] `#104` 와 연결
    client_index.py 199 + ontology_client_cache.py 165 클라이언트 로컬 RAG·폴백. [중요] 탐침 0건 확인

**7.4-F 운영 가드 2건 (314줄) — [중요] 이 둘이 우리 파이프라인과 직접 충돌한다**

    watch_state.py 233   [중요] **분산 작업 활성 검사 = Git 폴링 일시 중지 조건.**
                         우리는 `ax-indexer.path` 가 push 마다 색인을 깨운다 —
                         파이프라인이 커밋하는 중에 색인이 도는 것을 막는 장치가 **없다**
    worker/safety.py 81  워커 안전 가드(운영 워커 8 task 검증됨 — `audit_matrix.md` 확인)

**7.4-G 방법론·규범 문서 3건 (2,517줄) — [중요] 가장 아픈 셋**

| 원전 | 무엇 | 왜 아픈가 |
|---|---|---|
| `.agents/AGENTS.md` **21줄** | Antigravity 행동 수칙 5조. **3조 = "모호성 제거 — 임의로 해석하여 행동에 나서지 말고 반드시 질문"**. 1조 임의 수정 금지 · 5조 **직접 빌드·커밋 금지** | [중요] **사용자가 2026-08-13 에 다섯 번 말한 그 규칙이 원전에 이미 문서로 있었다.** 우리는 그 규칙을 세 번 잃고 나서 `CLAUDE.md` 에 적었다 |
| `.claude/reviews/_silent_failure/audit_matrix.md` **99줄** | **Silent Failure 감사 매트릭스**(σ.1 발동 흔적 매핑 + σ.2 정적 검사). 원문: *"plan 의 `[x]` 가 실 작업 완료를 의미하지 않은 한 가지 사례"* — silent failure **4건**을 그렇게 찾아냈다 | [중요] **오늘 내가 한 감사의 방법론이 원전에 이미 있었다.** 그리고 *"분모/분자를 손으로 적지 않는다"* 규칙의 원본이 여기다 |
| `plan_completed_v4.5.md` **2397줄** | v4.5 era 완료 기록 | [중요] **"이미 만들어져 있는 것" 목록**이다. 이걸 안 읽은 것이 뷰어 229줄 사건의 구조적 원인 |

**7.4-H 나머지 (6건 · 1,393줄)** — 재검토 필요, 부분 이식 가능

    ontology_drift_mcp.py 329 · ontology_refresh_mcp.py 240 · ontology_manage_rename.py 323
      → 우리 `drift_audit_tool`/`sync_ontology_tool`/`edit_ontology_item_tool` 이 일부를 덮는다.
        [중요] **개명 cascade** 는 우리 도구에 없다(도메인·클래스명이 디렉토리·DB키·URL 에 박힌다)
    log_tagging_candidates.py 240 + ontology_log_tags.py 132  태깅 실증(η.12.3) — ②와 경계
    analyzer.py 269 + executor_helpers.py 305                 orchestrator 보조
    scripts/agy_probe.py 227 + tools/agy_apply.py 85          [중요] **agy 라이브 검증** —
      우리 메모리에 *"agy 는 출처를 지어낸다"* 가 있는데 원전엔 그 **드라이테스트가 있었다**

### 7.5 [주의] 라우트 79 vs 11 은 손실 지표가 **아니다**

원전 `context_search` 는 `/api/v1/` 라우트 **79개**, 우리는 **11개**다. 그러나:

    우리 마스터는 **MCP 도구 우선** — 같은 기능이 HTTP 가 아니라 MCP 도구 24종으로 나 있다
    [중요] 복각 프론트엔드가 **실제로 호출하는** 라우트는 7종이고, 라이브 실측 **전부 등록돼 있다**
       (`object/{domain}/{class}`·`action/{domain}/{name}` 은 2세그먼트 — 1세그먼트로 재면 오탐)

[주의] **내가 이 자리에서 오탐을 두 번 냈다**(1세그먼트 테스트 · 존재하지 않는 액션 이름). 라이브로
재고 응답 **본문**까지 읽어서야 갈렸다 — *"라우트 미등록"* 과 *"자원 없음"* 은 둘 다 404 다.

## §8. 영향도 분석

### 8.1 닫힌 42건 중 전제가 흔들리는 것

    전제가 틀린 9건   #75 #76 #77 #78 #83 #111 #113 #114 #115   (중 1.3 · 중 1.4 · 소 2.1.3)
    부분 수정 2건     #67 #107
    영향 없는 31건    분해 · 층2 · 층3 · 웹 UI · 골조 · 규범 · 색인

[중요] **닫힌 42건을 소급해 열지 않는다** — 리포트 12 §5.4 가 이미 정한 규칙(*"소급해서 열면 기록이
거짓이 된다"*). 당시 실제로 돌았고 실측도 있다. 대신 **새 마일스톤에서 재검토 항목으로 다시 세운다.**

### 8.2 열린 9건의 성격이 바뀐다

    #95 #96 #97 #98   설계 → [중요] **이식**(원전에 623·397·416·459줄이 있다)
    #98 의 /debate    [중요] 원전이 **「전제 미충족」으로 강등**해 둔 것 → 재논의 대상
    #104              원전 `search_log_analyzer` 696 + `smoke_bm25_related_classes` 가 있다
    #105              영향 없음 (하드웨어 실측)
    #106              [완료] 진짜 신규 — 원전에 `tool_calls` 0파일

### 8.3 [중요] 코드에 이미 난 구멍 하나 (파이프라인 ↔ 색인)

`watch_state.py` 의 *"분산 작업 활성 검사 = Git 폴링 일시 중지"* 가 우리에게 없다. 우리는
`ax-indexer.path` 가 **push 마다** 색인을 깨우는데, 통합자가 조각마다 커밋·push 하므로
**한 work 안에서 색인이 여러 번 깨어난다.** 원전은 그 자리에 게이트를 뒀다.
[주의] 실사용 문제인지는 **아직 안 쟀다** — `#104`(BM25 원자성)와 같은 자리일 가능성이 있다.

### 8.4 문서·라벨

    docs/milestones/3-work-pipeline.md   토폴로지 절 라벨 정정 (커밋 안 된 경고 블록 → 본문 반영)
    docs/settled-decisions.md §214       같은 라벨 → 정정. [중요] 안 고치면 다음 세션이 재논의를 거부한다
    docs/8-git-authority.md §8.4         「누가 무엇을 만드나」 표 재검토 (#115 와 이미 모순)
    reports/12-*.md §5.1                 *"한 무리의 문제가 사라진다"* → **장치를 버린 것**이었다
    reports/12-*.md §9                   *"원전은 앞쪽(기계)만 있었다"* → [중요] **틀렸다**(planner 가 사람 고리)
    CLAUDE.md 양쪽                       원전 필독 목록에 `.agents/AGENTS.md` · `audit_matrix.md` ·
                                         `local_llm_distributed_workers_plan_v5.0.md` 추가


## §9. 마일스톤 3 정지 · 마일스톤 4 신설 ([완료] 완료)

### 9.1 [중요] 「진행 정지」를 어떻게 표현했나

상태 5종에 **「보류」가 없다**(1 신규 · 2 진행 · 3 해결 · 5 검토 · 4 완료). 이슈 상태로는
정지를 못 적는다. [중요] **대신 버전에 `locked` 이 있고 그게 정확히 진행 정지다** — 기존 이슈는
남고 새 배정만 막히며 `open` 으로 되돌릴 수 있다.

    마일스톤 2 — 디지털 트윈 복원      closed
    마일스톤 3 — 실작업 파이프라인     [중요] **locked** (2026-08-13)   총 51 · 완료 42 · 열림 9
    마일스톤 4 — 원전 대조·재이식      open  (version id=3)         총 62 = 중 17 + 소 45

[주의] **닫힌 42건을 소급해 열지 않았다** — 리포트 12 §5.4 의 규칙(*"소급해서 열면 기록이 거짓이
된다"*). 전제가 틀린 11건은 **마일스톤 4 의 재검토 항목으로 다시 세웠다.**

### 9.2 마일스톤 4 구조 — 대 4 / 중 17 / 소 45

[중요] **분자도 분모도 이 문서에 적지 않는다**(version *마일스톤 4* 가 센다). 구조만 남긴다.

| 대 | 중 | 이슈 |
|---|---|---|
| **대 1 토폴로지 원복** | 1.1 원전 설계 문서 정독 · 1.2 2-tier 복원 · 1.3 빌드 게이트만 `.2` 위임 · 1.4 문서·라벨 정정 | `#117` `#121` `#127` `#130` |
| **대 2 열린 4건을 이식으로 전환** | 2.1 /review-work · 2.2 작업유형 템플릿 · 2.3 /cluster-selftest · 2.4 /tdd-dryrun 이식 + **/debate 재논의** | `#135` `#138` `#141` `#144` |
| **대 3 미이식 자산 재검토·이식** | 3.1 ①추정 이식분 실물 대조 · 3.2 결정적 온톨로지 장치 · 3.3 되먹임 7종 · 3.4 감사·복구·튜닝 · 3.5 운영 가드 · 3.6 나머지+개명 cascade | `#147` `#151` `#154` `#159` `#163` `#166` |
| **대 4 방법론·규범 회수** | 4.1 `AGENTS.md` 5조 · 4.2 silent failure 감사 · 4.3 원전 필독 목록 제도화 | `#172` `#174` `#177` |

**사슬**: [중요] **1.1 이 상류다** — 설계 문서를 안 읽고 1.2 를 하면 같은 실수를 반복한다.
`1.2.5 fake_worker → 2.3.2` (드라이런이 셀프테스트의 전제) · `1.2 → 1.3`(게이트는 merge 안의
한 스텝) · 대 3·대 4 는 사슬 밖이라 병행 가능. [주의] **`2.4.2` 는 작업이 아니라 질문이다**(C.5 강등).

### 9.3 열린 9건에 단 노트

    #95 #96 #97 #98 #104   「설계 → 이식」으로 성격 변경 + 대체 칸이 M4 에 있음 + 여기서 진행 안 함
    #93 #103 #105          영향 없음. 순서상 M4 가 먼저
    #106                   [완료] 원전에 대응물 없음 = 진짜 신규로 확인

노트 9/9 성공. [중요] **상태는 건드리지 않았다** — 「진행 정지」는 버전이 표현하고, 이슈 상태를
손으로 바꾸면 분자가 거짓이 된다.

## §10. 남은 것 · 다음

### 10.1 [중요] 사용자가 순서를 못박았다 — 리눅스 적용이 1번 (2026-08-13, 등재 직후)

> *"일단 리눅스 환경에 적용하는 것이 1번이야. 개선은 그 뒤라는걸 명심하면 좋겠어"*

그 기준으로 **방금 만든 M4 를 스스로 검사했다.** 45개 중 41개는 순수 포팅이었고 **4개는 내가
「이식」이라 이름 붙여 놓고 실제로는 개선**이었다 → 노트를 달아 대 1~3 이후로 미뤘다
(`#146` /debate 되살리기 · `#169` log 태깅 · `#176` σ 감사 실행 · `#178` census 규칙 제도화).

[중요] **그리고 하나는 우선순위를 거꾸로 써 놨다.** 소 3.5.1(`#164` `watch_state`)에 *"실사용 문제인지
먼저 측정한다(추측 금지)"* 라고 적었는데, 그것은 **새로 만들 때**의 규칙이다. **원전에 이미 있는
가드는 재지 않고 옮긴다 — 원전이 이미 값을 치렀다.** 설명을 정정하고, **검증은 이식 후**로 옮겼다.
[주의] `#104`(BM25 원자성, M3)도 같은 모양이라 노트를 달았다 — 원전에 `search_log_analyzer.py` 696줄이
**있으므로** 재기 전에 이식이 먼저다.

[주의] **이 정정이 이 리포트의 다섯 번째 자기 정정이다**(§1 · §7.1 · §7.5 오탐 2건 · 여기).
지표도 분류도 우선순위도 한 번씩 틀렸다 — **틀린 자리를 남겨 두는 것이 이 리포트의 값이다.**

    [대기] 소 45개 실제 수행     이 리포트는 **무엇을 재검토할지**까지다. 재검토 자체는 M4 의 작업이다
    [대기] ①추정 11파일          온톨로지 이식분은 라이브 데이터로 뒷받침될 뿐 파일 대조는 안 했다 (소 3.1.1)
    [대기] 소 3.5.1 측정 먼저    파이프라인↔색인 충돌이 실사용 문제인지 **재고 나서** 고친다 (추측 금지)
    [중요] 다음 작업은 사용자가 정한다 — 대 1 이 상류지만 순서는 사용자의 몫이다

## §11. 소 1.1.1 — 원전 설계 문서 463줄 정독 (`#118`)

전문을 읽었다(요약본으로 대신하지 않았다 — 이 문서가 인용 0회였던 것이 M4 가 생긴 이유다).
결과: **§2 의 결론은 유지되지만 그림이 하나 더 있었고, 그 하나가 소 1.2 의 전제를 흔든다.**

### 11.1 [중요] 이 저장소의 존재 자체가 원전에 설계돼 있었다 — κ.9

`κ.9 저장소 분리 전략: 4갈래 → 2-repo` (사용자 2026-07-18 질의, 심층 검토). 결론:

    ⓐ 위키 클라이언트 + ⓑ 프로그래머 클라이언트  →  AgentTest 유지
    ⓒ 리눅스 마스터 + ⓓ BC-250 추론 노드        →  **신규 리눅스 저장소**   ← [중요] ax-cluster 가 이것이다

모노레포·4-repo·submodule 을 각각 기각한 근거까지 붙어 있다. 그리고 **이관 실행 지침**이 있다:

> *"새 저장소는 빈 저장소가 아니라 **본 저장소를 히스토리째 clone 후 remote 교체**로 시작하는
> 걸 권장 — `docs/*.md` 설계 결정 로그와 `history/` 가 '왜 이렇게 됐나'의 고고학 자료라,
> **복사본에서 히스토리가 끊기면 신규 repo 쪽 Claude 세션들이 같은 시행착오를 반복한다.**"*

[중요] **그 예측이 정확히 실현됐다.** ax-cluster 는 히스토리 없이 시작했고, 이 마일스톤 4 가 바로
*"같은 시행착오 반복"* 의 청구서다. 원전은 그것을 **2026-07-18 에 미리 적어 뒀다.**

[주의] 그리고 *"신규 repo 는 반대로 「리눅스 전용」 정책을 자기 CLAUDE.md 에 세우는 것이 대칭적으로
옳다 — 양쪽 다 크로스플랫폼 분기 금지, 경계는 HTTP/zip 계약"* 도 이미 지정돼 있다.

**κ.9 는 크로스-repo 계약 드리프트를 최대 리스크로 지목하고 계약 표면 6개에 SSOT 를 배정해 뒀다**:
HTTP API `/api/v1/*` · 온톨로지 YAML 스키마 · 컨텍스트 MD frontmatter · `state_transfer` zip
레이아웃 · 검색/텔레메트리 스키마 · 버전 핸드셰이크. 우리 저장소에 이 표가 없다.

### 11.2 κ.8 — Windows 의존 실측표가 이미 있었다

포팅 대상 7지점이 grep 근거와 함께 표로 있다: `process_lifecycle.py`(Job Object) ·
`network_firewall.py`(netstat/taskkill/netsh) · winpty ConPTY **3곳 중복**(→ 리눅스는 네이티브
PTY 라 *"오히려 더 단순해짐"*) · `CREATE_NEW_CONSOLE` · `CREATE_NO_WINDOW`(*"이미 안전, 변경
불필요"*) · `build.bat`/PowerShell.

[중요] 그리고 우리 논쟁의 답이 그 표 안에 있다:

> `ue_builder.py`/`ue_test_runner.py` — *"κ.0/κ.1 설계상 이미 「실행 레이어(빌드/컴파일)는
> 윈도우 워커에 남는다」로 해소됨 — **리눅스로 옮기는 대상 아님, 혼동 주의**"*

**「빌드 게이트만 `.2` 로」가 내 판단이 아니라 원전 표현과 일치한다.** 소 1.3.1 은 확인됐다.
κ.0 은 그 메커니즘까지 지정한다 — *"통합 빌드게이트는 인프라에 고정하지 않고 **task_queue 잡으로
큐잉 → UE5 있는 윈도우 워커가 claim** 하는 **CI 러너 패턴**"*. 우리 층3 의 원본이다.

### 11.3 [중요] 원전에 그림이 **둘** 있고, 뒤의 것은 **미확정**이다

    v5 C.1~C.7 (2026-06)   워커가 ephemeral attempt push → **서버**가 durable merge
                           → 리더가 feature 위에 durable 집합 모아 머지·빌드 (C.7)
    Phase κ (2026-07-08)   ①마스터 = 판단·상태 전부 · ②워커 = **엔진 바운드 실행만, 판단 안 함,
                           stateless**. 개인 윈도우 PC 라 언제 꺼져도 됨

그리고 **κ 미결정 사항**에 이렇게 적혀 있다:

> **추론 요청 주체 (κ.2 핵심 갈림)**: ②워커가 직접 노드에 추론 요청(**Flow X**, 현
> `worker.py` content-return) vs **마스터(①)가 브로커** — 마스터가 git 정본서 소스 읽어 노드에
> 추론 요청 → **받은 diff 를 task/attempt 브랜치에 commit**, ②는 pull → UE 컴파일/RunTests →
> 보고(**Flow Y**). 위 2층 물리 분리 강화(사용자 2026-07-08)는 **Flow Y** 를 가리킴 …
> **확정 필요** — 확정 시 κ.2 재서술.

[중요] **그러면 내가 M3 에서 한 재설계는 완전히 틀린 것이 아니었다 — Flow Y 의 변형이었다.**
그리고 원전은 *"2층 물리 분리 강화가 Flow Y 를 가리킨다"* 고까지 적어 뒀다. 다만 **셋이 다르다**:

| | 쓰는 주체 | attempt 브랜치 | 워커가 하는 일 |
|---|---|---|---|
| v5 C.1~C.3 | 워커(ephemeral) + 서버(durable) | [완료] 있다 | 추론 + push + 검증 |
| **κ Flow Y** (미확정) | [중요] **마스터** | [완료] **있다**(마스터가 거기 commit) | pull → UE 빌드/RunTests → 보고 |
| 내 M3 재설계 | 통합자 `.2` | [실패] **없앴다** | 텍스트 응답만 |

**내가 틀린 것은 「워커가 안 쓴다」가 아니라 ① attempt 계층·epoch fencing 을 없앤 것과
② 쓰는 주체를 마스터가 아니라 `.2` 로 둔 것이다.** κ.0 은 *"오케스트레이션 상태 전부가 마스터에
산다"* · *"소스=정답의 정본은 git 저장소(마스터)"* 라고 못박는다.

[주의] **그래서 소 1.2(2-tier 복원)는 지금 진행할 수 없다** — C.1 대로 되돌릴지, κ Flow Y 로 갈지가
**원전에서도 미확정**이다. 사용자 결정 사항이다(§11.5).

### 11.4 그 밖에 확인된 것 (이식 시 전제)

-  **모토**: *무료 로컬 LLM = 대량 생산 / 상용 모델 = 검증.* *"이 모토를 어기는 설계(서버측
  per-task LLM 검증 등)는 도입 금지"* — 우리 층2 가 상용인 것은 모토와 정합
- [중요] **claim 우선순위 정정(2026-07-05)**: **write 우선 1, verify 2**. 옛 *"verify 우선 + author
  무조건 제외"* 는 워커 1대에서 **starvation** 을 냈다. author 제외는 **완화** — 다른 워커
  attempt 를 우선하되 없으면 자기 것도 검증한다(작성=로컬·검증=상용이라 **모델 수준 독립성**은
  유지). [주의] 그 논의 중 원전 세션이 *"검증 전용 노드"* 를 발명·배선했다가 **전량 revert** 했다 —
  워커는 homogeneous 다. 우리가 `.2` 를 「통합자」라는 특수 역할로 만든 것이 같은 부류인지 봐야 한다
- **C.4 동결은 강제** — `_frozen_decls` 가 결정적(LLM 0)이고, 우리 `frozen_decls` 와 같은 설계.
  [주의] 원전이 적어 둔 미커버: 생성자/소멸자(반환타입 없음) · 단독 멤버변수 rename
- **C.3 읽기 범위 3단**: 기본 = HEAD + **직전 피드백 commit 1개** + in-file 태그 / 맥락 =
  `[FEEDBACK]`·`[CONTEXT]` 블록(bounded·curated) / escalation = 더 깊은 `git log`(비쌈)
- **in-file 태그 2부류**: 제품(ship) `[PRE]/[POST]/[DOC]` vs 작업 스캐폴딩(strip)
  `[PSEUDO]/[FEEDBACK]/[CONTEXT]` — 우리 층1 규칙과 일치
- **매니페스트는 git-carried**(`.claude/tasks/<id>/context.md`), 워커는 **검색 대신 읽기만**.
  [주의] **`work_id` 키 폴백**이 이미 있다(`for _key in (task_id, work_id)`) — task_id 는 등록 후
  발급되므로 경로 키를 work_id 로 두는 것이 원전의 해법
- **κ.3 소스=정답**: 저장 데이터(RAG/온톨로지)는 **네비게이션**일 뿐 정답이 아니다. 매니페스트에
  **실제 소스 본문**을 싣는다. 라우팅 2 regime — (a) 미리 모을 수 있으면 무료 로컬 / (b) 파봐야
  알면 read-툴 모델. [주의] 판정 방법은 **미결정**
- **제약**: 새 supervisor 데몬  · 통신 인프라 creep  · 배포 후 자동작동

### 11.5 [중요] 규범 충돌 하나 — 커밋 권한

원전 `CLAUDE.md` 와 `.agents/AGENTS.md` 5조가 같은 말을 한다:

> *"`git commit`(및 push/merge/rebase/reset/branch 삭제)은 Claude 가 실행하지 않는다 —
> **사용자가 명령형으로 지시해도 마찬가지다.** … '커밋할까요?' 처럼 묻지도 않고, '커밋
> 부탁드립니다' 처럼 **사용자에게 요청하는 형태로만** 표현한다."*
> Why: 2026-07-12 *"중간 커밋하고 올게"*(사용자 1인칭 서술)를 지시로 오독해 임의 커밋한 사건.

[주의] **우리 `ax-cluster/CLAUDE.md` 는 force-push·reset·rebase·브랜치 삭제만 금지하고 커밋은
허용한다.** 그래서 나는 이 세션에서 커밋·푸시를 했다. **어느 쪽이 맞는지는 사용자 결정이다** —
κ.9 가 *"신규 repo 는 자기 정책을 세운다"* 고 했으니 의도적 차이일 수도 있지만, 커밋 권한은
플랫폼 문제가 아니라 **권한 문제**라 대칭 논리가 그대로 적용되지 않는다. 소 4.1.1 로 넘긴다.

## §12. 소 1.1.2 — 미독 4종 1,919줄 정독 (`#119`)

`README.md` 842 · `watcher-internals.md` 544 · `runbook.md` 281 · `extending.md` 252.
[중요] **가장 값진 것은 `watcher-internals.md` 의 「Silent Failure 가드(σ 계열)」 결정 로그다** —
이 저장소가 *"조용히 틀리는 것"* 을 경계하는 문화의 **원천**이고, 거기 실측이 붙어 있다.

### 12.1 [중요] 우리 코드에 살아 있는 결함 셋 (실측)

원전 σ 가드 4종을 우리 코드와 대조했다. **둘은 이식돼 있고, 둘은 없고, 하나는 불일치다.**

| 원전 가드 | 우리 |
|---|---|
| CP949 폴백 (`read_text_resilient`: UTF-8 strict → CP949 → replace) | [완료] **이식됨** — `master/source_text.py` 가 원전 사고를 직접 인용까지 해 뒀다 |
| SQLite WAL + `busy_timeout=10000` | [주의] **절반** — `graph/db.py`·`graph/dependency.py` 는 있고 [중요] **`context_search/bm25.py` 는 없다** |
| lone surrogate 가드 (`strip_lone_surrogates`+`safe_dumps`) | [중요] **없다** — 우리 MCP 서버에 `json.dumps` **34곳**(projects 28 · task_queue 6) |
| 콘솔 출력 UTF-8 강제 (`sys.stdout.reconfigure`) | [중요] **없다** (`reconfigure` 0건) |

**① [중요] `#104`(BM25 원자성)의 답이 나왔다 — 재기 전에 이식이 먼저다.**
`bm25.py:158-162` 는 `mmap_size`/`cache_size`/`temp_store` 만 걸고 **WAL·busy_timeout 을 안 건다.**
그런데 `bm25.db` 는 **두 프로세스**가 연다 — `ax-indexer`(`master.events.consumer`, 쓰기)와
`ax-projects`(`master.projects`, 읽기). `RLock` 은 프로세스 **안**만 막는다. 우리 `graph/db.py:84`
스스로 *"같은 프로세스 안의 쓰기 직렬화. **프로세스 간에는 아래 WAL + busy_timeout 이 담당한다**"*
라고 적어 두고 bm25 에는 빠뜨렸다. [중요] **형제 모듈과의 불일치라 추측이 아니다.**
원전이 실측한 실패 모드가 정확히 이것이다(2026-06-05): *"기본 `busy_timeout=0` 이라 동시 쓰기 시
즉시 `database is locked` → 상위 `log(skip)` 으로 삼켜져 **해당 사이클 변경이 영구 유실**"*.
[주의] 원전은 bm25 를 *"단일 프로세스 영속 연결(RLock)뿐이라 교차 경합 없음"* 으로 판정했는데
**우리 구조는 다르다** — 그래서 같은 결론을 물려받을 수 없다.
[주의] 원전이 **명시적으로 기각한 것**도 같이 옮긴다: *"`locked` 명시 재시도 루프는 미채택 —
busy_timeout 이 SQLite 네이티브 블록-후-재시도이고 WAL 이 읽기↔쓰기 경합을 제거"*.

**② [중요] lone surrogate 는 세션을 통째로 죽인다.** 원전 실측(2026-06-06): lone UTF-16 surrogate 가
MCP 결과 str 에 섞이면 FastMCP 의 `json.dumps(ensure_ascii=True)` 가 **에러 없이** `\udXXX` 로
내보내고 → Claude Code(Node)가 JS lone surrogate 로 파싱 → Anthropic 요청 직렬화에서 **400 으로
요청 전체 거부 = 세션 사망**. 원전은 `server.py` 의 `json.dumps` **64곳**을 `safe_dumps` 로 일괄
교체했다. [주의] **우리에게 직접 생산자는 없다**(`surrogateescape` 0건) 그리고 **원전도 원천을 특정
못했다**(*"raw request body 없이 단정 불가 → 카나리가 다음 발생 시 증거 수집"*). 그래서 이건
「버그 수정」이 아니라 **싼 가드 + 카나리** 이식이다.
[중요] 그리고 진단 분리를 기억할 것: *"한글은 BMP 단일 코드유닛이라 **mojibake 와 surrogate 400 은
별개 현상**"* — 한글 절단으로는 surrogate 가 절대 안 깨진다.

**③ 콘솔 UTF-8** — 원전은 한국어 Windows 콘솔(CP949)에서 em-dash·박스드로잉을 print 하면
`UnicodeEncodeError` 로 **로그 한 줄 없이 프로세스 즉사**하는 것을 겪고 `common.py` 최상단에
`reconfigure(encoding='utf-8', errors='replace')` 를 넣었다. 원전 스스로 *"동일 인코딩 문제군의
**세 번째 다리**"* 라고 적었다(읽기·직렬화·출력). [중요] **우리는 리포트 13 에서 `.2` 의 CP949 로
층3 이 죽은 것을 이미 겪었다** — 같은 문제군의 그 다리다.

### 12.2 [중요] 메타 교훈 하나가 우리 층1 이중 배치를 겨눈다

> σ.10 cleanup 책임 축소(2026-05-26): production 에서 `MissionRuntime` 도메인 **수동 등록 직후
> 다음 사이클에 자동 삭제**되는 사고. 원인 = 같은 기준(`_has_meaningful_body`)을 **승급과 정리
> 두 단계에 중복 적용**해 「신규 등록 직후 본문이 얇은 살아있는 파일」을 좀비로 오탐.
> **메타 교훈: "silent failure 가드를 두 단계에 같은 기준으로 중복 적용하면 false positive 를
> 양산한다. 단계별 책임 분리 — 승급(자격 검사) vs 정리(실재 검사)."**

[주의] 우리는 층1 을 *"무료라 두 번 돌린다"* 며 **응답 수락과 적용 직전 두 곳**에 박았다(소 2.1.3).
[중요] **같은 함정인지 확인해야 한다.** 다만 우리 층1 은 결정적 문법 검사라 *"얇은 신규 파일"* 같은
상태 의존 판정이 아니어서 성격이 다를 가능성이 크다 — **그래도 검증 없이 다르다고 하지 않는다.**

### 12.3 카나리 승격의 판별 기준 (그대로 쓸 수 있다)

원전은 `watch.py` 의 except **~33개 중 딱 2개만** 카나리로 승격했다. 기준이 한 줄이다:

    [중요] **"skip 후 `.watch_state` 워터마크가 전진하느냐"**
       예외를 던지는 경로  → 전파 → 워터마크 미전진 → 다음 사이클 self-heal (안전)
       예외를 삼켜 정상 리턴 → 워터마크 전진 → **영구 유실**            ← 이것만 카나리

    kind=context-md-lost   모듈 MD 미생성인데 워터마크 전진
    kind=vector-index-gap  MD 는 있으나 벡터 인덱스 미반영
    → `.claude/reviews/_silent_failure/permanent_loss_canary.jsonl` (새 측정 인프라 0)

[주의] 나머지 31개는 **일부러 안 건드렸다** — *"self-heal 되는 걸 카나리로 만들면 노이즈"*.
[중요] 우리 색인기·파이프라인에 이 판별을 한 번 돌려야 한다.

### 12.4 [중요] `#96`(작업유형 템플릿)이 층3 `RunTests` 의 **전제**였다

README 후처리 절: *"모든 task verified 직후 feature 브랜치에서 UE Build.bat → 빌드 통과 시,
작업의 **태스크 템플릿 중 `tdd:true` 인 것의 `test_spec.filter`** automation 테스트를
`UnrealEditor-Cmd RunTests` 로 실행"*.

즉 **무엇을 돌릴지는 태스크 템플릿이 정한다.** 우리는 `#96` 을 미이식으로 뒀고 층3 은
*"돌릴 테스트가 없다"* 며 fail-open 이다 — [중요] **그 두 사실이 같은 원인이다.** 마일스톤 3 이
*"테스트 0개는 코드로 메울 수 없다"* 고 적은 것은 절반만 맞다: 테스트를 **쓰는 것**은 프로젝트
결정이지만, **돌릴 것을 지정하는 배선**은 `#96` 이식이다. [주의] 원전 fail-open 조건도 다르다 —
*"엔진 미가용 등 **인프라** 이슈"* 이지 *"테스트가 없음"* 이 아니다.
그리고 `/manage-task` 스킬이 `tdd`/`test_spec` 을 켜는 표면이고, `/tdd-dryrun` 은 **분산
파이프라인 밖에서** 그 계약 테스트를 서버 단독으로 검증·튜닝한다(흔적 0).

### 12.5 [중요] `.2` 통합자 특수 역할 — 원전이 정면으로 부정한다

    README.md:383   "리더 PC = 워커 PC = 동일 dist 배포. **별도 검증 PC 불필요.**"
    README.md:381   클라-워커 PC = 모든 직원(리더 포함) — 평소엔 worker, 리더 권한 시 /review-work

리포트 13·§11.4 가 남긴 우려(*"검증 전용 노드를 발명했다가 전량 revert"*)가 **문서로도 확증**됐다.
[중요] 역할은 **PC 가 아니라 권한**이다. Flow Y 에서 마스터가 쓰기 주체가 됐으므로 `.2` 는
*"UE5 를 가진 워커"* 로 되돌아가야 하고, 「통합자」라는 **머신 고정 역할은 지워야 한다.**
κ.0 의 CI 러너 패턴(빌드 잡을 큐에 올리고 UE5 워커가 claim)이 정확히 그 형태다.

### 12.6 코드 생성 프롬프트에 들어가야 하는 금지 3종

원전 리뷰 프롬프트의 금지 규칙 — [중요] **이유가 UE 특유라 우리 파이프라인에도 그대로 걸린다**:

    클래스/컴포넌트/함수/UPROPERTY 멤버 리네이밍 금지   Blueprint 에셋이 C++ 상속 +
    클래스 상속 구조 변경 금지                          UPROPERTY 직렬화 → 이름 변경 시 **에셋 깨짐**
    모듈 간 코드 이동 금지                              빌드 의존성 + 에셋 참조 파괴

*"LLM 은 코드만 분석 가능 — **UE5 에셋 의존 관계(Blueprint 상속·데이터테이블 참조)는 파악 불가**"*
이고 `UCLASS(Blueprintable)`/`(BlueprintType)` 은 특히 주의. [주의] 우리 `frozen_decls` 는 **선언
동결**이라 리네이밍의 일부를 막지만 **모듈 간 이동은 못 막는다.**

### 12.7 그 밖에 건진 것 (이식·확인 목록)

- [중요] **`/manage-contract` 스킬이 `@ms-contract` 의 사용자 표면**이다 — 계약을 대화형 수집 →
  `.h` 주석 태그 작성 → 커밋 시 declared invariant 자동 등재. **소 3.2.1 은 스킬까지 한 벌이다**
- [중요] **판정은 출력 문자열이 아니라 exit code 로** (2026-06-04 실측): headless 호출에서 CLI 가
  *"256-color support not detected"* 경고와 함께 **자체 non-zero 종료** → 매번 폴백이 돌던 사고.
  *"경고 텍스트는 실패 **결과** 화면이지 판정 입력이 아니다."* 해법도 우리에게 필요한 형태다 —
  PC 마다 환경변수 수동 등록이 아니라 **호출 시점 `env=` 주입**(`COLORTERM`/`TERM`)으로 배포
  산출물이 자동으로 들고 간다. 우리도 SSH 로 `claude -p`·`agy` 를 부른다
- **도메인명은 영문 PascalCase 강제** — 이름이 **디렉토리 = DB 키 = URL 경로 = MCP 도구 인자**로
  그대로 쓰여 비ASCII 는 `URL can't contain control characters` 로 도구를 깨뜨린다.
  *"transport 인코딩으로 우회하지 말고 **생성 시점에** 영문으로 명명"*
- **`redmine_tracker.update_issue(notify_children=True)`** — `parent_issue_id` 하위 이슈 전원에
  변경 알림 노트 자동(2026-07-25). [중요] 우리 M4 가 중(부모)–소(자식) 구조라 그대로 쓸 만하다
- **정보 3분할**: 도메인 문서(시스템 큰 그림·팀 공유·RAG) / 레시피(작업 step-by-step·로컬) /
  안티패턴(함정 카탈로그·로컬 단일 파일 ~500–1500 토큰이라 매 작업 주입 가능)
- **`.mcp.json`/`settings.json` 머지 정책**: 관리 대상은 **항상 덮어쓰기**, 사용자 항목은 보존,
  `CLAUDE.md` 는 `<!-- AgentWatch:Start/End -->` **마커 구역만** 갱신
- **co-commit 분석 제거(2026-05-18)**: 운영 측정 결과 **호출 0건** → 삭제. 측정으로 기능을 **빼는**
  선례다 — *"영향 범위는 dependency + related_classes + 증분 + 통합 빌드 게이트로 커버"*
- **`force_all` 재합성 금지** — 토큰 과소모 + **비결정성으로 inv/act 개수 변동(버그 아님)**
- **합성 산출물 vs 인덱스** — `ontology/domains/`·`context/*.md` 는 **원본**(지우면 LLM 재합성 비용),
  `vector_db/` 는 파생. 이관은 **앞의 둘만** 옮긴다
- [주의] **헬스체크 prefix 매칭 함정**: 모델 태그를 prefix 로 매칭하면 `gemma4:e4b` 로 통과하고
  실제 호출은 없는 모델명으로 실패한다. 우리 브로커의 상주 모델 판정도 같은 모양인지 볼 것
- **`_ensure_port_free`**: **부모가 죽은 orphan 만** taskkill, 부모 생존 점유자는 경고만
  (*"동명 exe 일괄 학살 금지"* — 다른 세션의 MCP child 보호)

## §13. 소 1.1.3 — `plan_completed_v4.5.md` 2,397줄 **색인 추출** (`#120`)

[중요] **전문 정독하지 않았다 — 사용자 지시로 색인만 뽑았다.** 이 문서는 v4.5 시대 **완료 기록**이라
목적이 *"이미 만들어져 있는 것"* 목록이고, 서사는 이미 `docs/` 로 승격돼 있다. 항목명 단위로
기계 추출(`- [x] **이름**` 패턴, **279건**)해 아래 색인을 만들고 걸리는 절만 펼쳤다.

### 13.1 「이미 있는 것」 색인 — 원전 항목군 대 우리 상태

| 원전 | 항목 | 우리 |
|---|---|---|
| **I-1** 인프라 토대 | zip 배포 · 운영모드 3 · config 마이그레이션 · Job Object · 잔여프로세스 정리 · 포트 점유 · 중복실행 방지 · 빌드 전 테스트 · 버전 자동증가 | ④ 대부분 **윈도우 exe 배포 전용** — κ.8 이 이관 대상 아님으로 판정 |
| **I-2** RAG | ChromaDB+MiniLM 384 · **더블버퍼 원자 swap** · BM25 FTS5 · 필드 가중치(tags×3/related×2.5/category×1.5/body×1) · 정규식 사전 토큰화 · 증분 · **부트스트랩/warm-reload/schema-migration 분기** · 페이지 캐시 워밍 · **운영 카나리 4종** · RRF k=60 · search_log 2000건 회전 | [완료] 대부분 이식. [중요] **카나리 4종·워밍 없음**(§13.2) |
| **I-3** 분산 워커 | `/distribute` · master_orchestrator · task_queue · worker · `/review-work` · 태그 체계 · 뎁스 분할 · 포팅 지원 · **1차 통합 빌드 게이트** · Redmine status **동적 매핑** | 대 1·대 2 가 다룬다. `/review-work` = `#135` |
| **I-4** 자동화 | stem 단위 컨텍스트+리뷰 통합 · trivial 스킵 · 의존 그래프 증분 · 에셋 검증 · **리뷰 범위=변경분+영향분석** · 작성자별 기록 · 코멘트 시스템 · **코멘트는 임베딩 제외** | [주의] 코멘트 시스템·작성자별 분리 미이식 (리뷰 파이프라인 자체가 우리 범위 밖) |
| **I-5** 학습·진화 | 도메인 자동승급 · code_recipes(신호→야간 합성→안티패턴 4섹션) · 주간 플랜(비용제어·금지규칙) | ② 자동승급 폐기 · [중요] 나머지는 `#154~#158`(되먹임 7종) |
| **I-6** 분석 MCP RAG | log/crash analyzer 자동 연결 · 가중치 식별자 추출 · `_COMMON_WORDS` 오탐 차단 · HTTP-only · 로컬 폴백 | [대기] 미이식 (UE 로그·크래시 분석은 우리 범위에 아직 없다) |
| **I-7** Redmine | 수동 즉시등록 · 주간배치 · **Cross-week dedup** · Description 완결화 · **status 동적 매핑** · 실패 시 정상진행 | [주의] 우리는 `status_id:4` 하드코딩 — 마일스톤 3 이 *"근거 없이 맞는 중"* 이라 적어 뒀다 |
| **I-8** `/debate` | N역할 독립 spawn · 3사이클 · 자연어 트리거 · 보고서 자동생성 · **Step 0 비용 가드** | `#146` — [중요] 단 C.5 가 강등해 둔 것 (개선) |
| **I-9** 안정성 | LLM 교차 폴백 · 서킷브레이커 · **누적 커밋 처리** · pull 실패 안내 · lease 20분 · 로그 | [완료] 브로커·큐에 이식 |
| **I-10** 구조 | 에이전트 11종 · MCP 10종 · 스킬 3종 | 우리는 MCP 도구 24 + 스킬 2 (구조가 다르다) |
| **I-11** 코드 분리 | [중요] **1,000줄+ 는 책임 단위 분리 + 원본은 facade** | [주의] 우리 최대 `integrate.py` 794줄 — 아직 여유 |
| **η.1~η.8** 온톨로지 | 분류·YAML 합성·규범 디스커버리·Action 카탈로그·Drift·State-based refresh·**Layer 분리+path audit 카나리**·**리비전 워터마크 partial refresh**·**History Harvest** | `#148`(대조) · `#158`(History Harvest) |
| **σ.1~σ.16** Silent Failure | 감사 매트릭스 · 정적 검사 · [중요] **카나리 로그 의무화** · 펜스 가드 · 도메인 trigger 가드 · **운영 데이터 조회 도구** · archive 휴리스틱 | `#175~#176` · [중요] σ.3 은 §13.2 |

### 13.2 [중요] 색인이 새로 찾아낸 것 — 운영 카나리가 없다

    [BM25 startup]     [BM25 commit]     [search latency]     [BM25 0건 진단]     → 우리 코드 **0건**
    페이지 캐시 워밍(시작 시 더미 MATCH 로 콜드미스 회피)                        → 없음

**σ.3 이 「카나리 로그 의무화」를 독립 항목으로 세워 뒀다.** 원전에서 이게 실제로 값을 했다 —
`watcher-internals.md` σ.10 항목이 *"카나리 로그(`stale_filtered=6`)가 원인을 즉시 가리켜 σ.10
자체의 silent failure 방지 효과 입증"* 이라고 적고 있다. [중요] **배치·게이트가 자기 숫자를 로그에
남기지 않으면 조용히 틀린 것을 사람이 못 본다.** → 소 3.5.8 신설.

[주의] 원전 실측 성능도 같이 옮겨 둔다(우리 회귀 기준선): **BM25 902건 풀빌드 170ms / 16건 증분 47ms.**

### 13.3 [완료] 되돌리지 말 것 — 우리가 이미 더 낫게 푼 것 둘

색인 대조 중 확인했다. **원전보다 개선된 것이라 「이식」 명목으로 되돌리면 퇴행이다:**

- **BM25 원자성** — 원전은 *"제자리에서 지우고 다시"* 인데 우리 `bm25.py:17` 은 **세대별 테이블
  둘(`bm25_a`/`bm25_b`)** 로 나눴다. [중요] **마일스톤 3 §5.4.6 의 *"더블버퍼가 BM25 는 안 덮는다"*
  는 이미 해소돼 있었다** — 그래서 `#104`/`#179` 에 남은 것은 원자성이 아니라 **프로세스 간
  락(WAL·busy_timeout)** 하나다. 진단이 좁혀졌다
- **더블버퍼 기동 시점** — `generation.py:5-9` 가 원전과의 차이를 실측해 뒀다: 원전은 부팅 때
  무조건 `context_a` 를 Live 로 잡는데, 우리는 프로세스가 갈려서 그러면 **재기동 순간 빈
  `context_a` 를 보고 검색이 0건**이 된다. 고쳐 놨다

### 13.4 방법에 대해

[중요] **색인 추출이 이 문서에 대해서는 옳은 선택이었다** — 279개 항목명이 다 나왔고, 걸리는 절
(I-2 · σ.3 · I-11)만 펼쳐서 결함 1건과 개선 확인 2건을 얻었다. [주의] 다만 **소 1.1.1·1.1.2 에
같은 방법을 썼으면 실패했을 것**이다: 저쪽의 값은 항목명이 아니라 **「사용자 확정」 라벨과 실측
서사**(κ 미결정 Flow X/Y · σ 결정 로그)에 있었고 그건 항목명에 안 나온다.
**문서의 성격이 읽는 법을 정한다 — 완료 기록은 색인, 설계·결정 로그는 정독.**

## §14. 소 1.2.1 — `cluster_coordinator.py` 200줄 대조 · Flow Y 이식 설계 (`#122`)

### 14.1 [주의] 내가 틀린 것 먼저 — 마스터에 소스 정본이 **있다**

`ModularStage/Source` 를 보고 *"마스터에 프로젝트 클론이 없다"* 고 했는데 **틀렸다.**
사용자 지적으로 다시 찾았다 — 정본은 `ax-cluster/ModularStage/**repo/**` 다:

    추적 파일 2,228 · branch main · HEAD b1ba6af   (리포트 13 의 워커 체크아웃과 같은 커밋)
    fetch  /var/lib/gitea/gitea-repositories/sim/modularstage.git   ← 로컬 bare, 네트워크 0
    push   [중요] DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1

[중요] **push URL 이 사유를 담은 문자열로 봉인돼 있다.** 규칙을 문서에만 적지 않고 **기계가 거부하게**
만든 것이라, 이 저장소에서 가장 잘 만든 가드 중 하나다. `ModularStage/.gitignore` 가 `repo/` 를
제외해 트윈 저장소와 섞이지도 않는다.

### 14.2 [중요] 그래서 Flow Y 가 **기존 원칙과 정면으로 충돌한다**

    Flow Y (원전 κ, 미확정 → 사용자 확정 2026-08-14)
        마스터가 소스를 읽어 노드에 추론 요청 → **받은 diff 를 attempt 브랜치에 commit·push**

    우리 §2.1 (settled) · CLAUDE.md 하드룰 · work/twin_base.py · push URL 봉인
        [중요] "마스터는 인프라지 작업장이 아니다 · **파일을 소유하지 않는다** · 마스터는 소스
           저장소에 push 할 수 없다 · 브랜치를 **만드는 것은 요청자**다"

**넷이 같은 말을 하고 있고 그중 하나는 기계 장치다.** 라벨만 고쳐서 넘길 수 없다.

[주의] 다만 원전 κ.1 은 그 경계를 우리보다 **가늘게** 그었다: *"BC-250 노드는 파일을 갖지 않고,
**마스터는 정본 git 저장소를 보유** — RAG·온톨로지·소스 조립은 소스를 **읽는** 작업이라 원칙 위반
아님. 파일을 **수정·컴파일** 하는 것만 파일 소유 워커에 남는다."* 즉 원전 기준으로 금지된 것은
**수정·컴파일**이고 우리는 그것을 *"파일 I/O 자체"* 로 넓게 읽었다.

### 14.3 이식 대조표 — 5칸 중 **셋은 이미 돼 있었다**

| 원전 | 우리 | 상태 |
|---|---|---|
| `branch_names.py` (durable `task/<id>` · attempt 4토큰 · glob · parse) | `work/branch_names.py` | [완료] **이식 + 개선** — `BranchNameError` 검증 추가(*"조용히 정규화하지 않는다"*) · `parse_durable` 추가 · `worker_id`→`workshop` 개명 · `select_work_branch`(pull 레거시 플래그) **의도적 제거** |
| epoch fencing (`submit_epoch < current_epoch` → zombie 거부) | `task_queue/logic_claim.py:200` 배정마다 단조 증가 · `:118` verifier_epoch · `logic_lifecycle._is_stale_epoch` · `models.py:98` · server 배선 | [완료] **완전 이식** → [중요] **`#124` 는 이미 완료다** |
| 매니페스트 4함수 (`manifest_rel`/`build`/`write`/`read`) | `work/manifest.py` (`manifest_path`/`build`/`write`/`read`/`collect`) | [완료] 이식 |
| `cleanup_attempts` — `push --delete` 로 원격 ephemeral 제거 | `work/cleanup.py` — `_OURS=^(attempt|task)/`, 원격은 **세기만 하고 건드리지 않음** | [주의] **의도적으로 다르다**(§14.4) |
| `assign_attempt` · `push_attempt` · `fake_worker` · `run_round` | — | [중요] **없다** |

### 14.4 [주의] `cleanup_attempts` 는 「복원」이 아니라 **판단**이다

우리 `cleanup.py` 는 원격 attempt 를 일부러 안 지운다 — 주석 원문: *"`push --delete` 는 하지
않는다. 원격 attempt/task 를 없애는 것은 **요청자와 사람의 판단**이고, *'항상 attempt 를 push
한다'* 는 **증거 보존**이 목적이므로."* 그리고 08-09 결정(*"attempt 를 성공·실패 무관 push"*)이
그 근거다.

원전은 반대로 **리더의 terminal 결정(finalize/reject) 시 `_cleanup_all_work_branches` 로 일괄
정리**한다(v5 C.7). [중요] **둘 다 일관성이 있고 시점이 다르다** — 원전은 *"work 가 끝났으면 지운다"*,
우리는 *"사람이 지운다"*. `#125` 를 그냥 「복원」하면 증거 보존 결정을 말없이 뒤집는다.

### 14.5 [중요] 프로젝트 `CLAUDE.md` 가 이식 설계의 절반을 갖고 있었다

`ModularStage/repo/CLAUDE.md` — 마스터 미러의 로컬 문서(gitignore 대상). 우리 저장소에서 **인용 0회**.

**① 커밋 규약이 이미 우리 파이프라인을 전제한다:**

    "This repo is also written to by the AX cluster's distributed pipeline,
     so history mixes human and machine commits."
    [skeleton] <feature>: N files for distributed implementation
    [verify-merge] <hash> <path> by <workshop-host>          ← [중요] workshop 이 verify-merge 한다
    [review fix] <what> (work=<work-id>)
    Merge work <work-id>: <Title>   + Reviewed-by: / Refs-work: 트레일러
    Work branches: work/<YYYYMMDD_HHMM>_<slug>

[주의] `[verify-merge] … by <workshop-host>` 는 **Flow X 형태**다. Flow Y 로 가면 이 규약도 바뀐다.

**② [중요] 빌드가 여기서 깨질 수 있다 (층3 에 직결):**

    빌드 대상은 `ModularStageEditor` 뿐 — `ModularStage`(Game) 은 Build.cs 가 UnrealEd 를
      bBuildEditor 밖에 둬서 **clean build 자체가 불가**
    편집기 모듈은 `ShadowVariableWarningLevel = Error` → [중요] **변수 하나만 가려도 하드 빌드 실패**
    `Project_Alpha` (~1,400파일) = **legacy reference only, 빌드·리팩터 금지** — 코드는 여기서
      *포팅해 나온다*. 우리 `porting.py` 의 「원본」이 이것이다
    `Source/MissionTools/` 는 gitignored (별도 `MissionEditorMCP` 저장소)

**③ [중요] 우리 「파일 전체 반환」 프로토콜이 노이즈 diff 를 만든다 — 새 위험:**

> *"Some older `Build.cs` / source comments are **mojibake** (cp949 read as UTF-8). **Leave them;
> don't "fix" the encoding as a drive-by, it produces noisy diffs.**"*

우리 `source_text.decode` 는 CP949 폴백이라 **읽으면 제대로 읽힌다.** 그런데 워커 프로토콜이
*"파일 전체 내용을 쓴다"* 이므로, 그 파일을 건드리면 **mojibake 주석이 정상 한글로 정규화되어**
프로젝트가 명시적으로 금지한 노이즈 diff 가 된다. [주의] **층1 이 이걸 못 잡는다** — 문법은 맞고
동결 선언도 안 깨지니까. 마일스톤 3 이 남긴 *"인코딩이 유실된 사본으로 동결을 판정하지 않는다"* 와
같은 자리인데 **방향이 반대**다(그쪽은 못 읽는 문제, 이쪽은 **너무 잘 읽는** 문제).

**④ 코드 규약 — 생성 프롬프트에 실려야 한다** (우리 매니페스트가 나르는지 확인 필요):
주석은 **한국어** · 헤더 `UPROPERTY` 객체 참조는 전부 `TObjectPtr<T>` · `IsValid(X)` (`!= nullptr`
금지) · `Cast<T>` 결과 직접 검사(`IsA()` 후 `Cast` 금지) · IWYU(`.h` 전방선언 / `.cpp` include,
**되돌리면 안 되는 구체 사례 2건 명시**) · `FTimerHandle` 은 항상 멤버 · 복제 컴포넌트는 생성자
`CreateDefaultSubobject`(`BeginPlay` 의 `NewObject` 금지) · 매직넘버 금지 → `UPROPERTY(EditDefaultsOnly)`
· [중요] **서브시스템은 절대 복제되지 않는다** · 이벤트는 **local-scope only**.

### 14.6 Flow Y 이식 설계 — 남은 것은 «누가 어떻게 쓰나» 하나

셋이 이미 됐으니 설계의 실질은 **`assign_attempt` + `push_attempt` 의 자리**다.

    Flow Y 흐름 (κ.0 + κ.3 + CI 러너 패턴)
      ① 마스터: 큐에서 배정(epoch↑) → 정본에서 소스 읽기 → 매니페스트(이미 있음) →
                노드/상용에 추론 요청 → **파일 전체 텍스트** 수신
      ② 마스터: 층1 → attempt 브랜치에 commit·push          ← [중요] 여기가 §2.1 충돌 지점
      ③ 큐: 빌드 잡 등재 → UE5 워커가 claim → pull → 빌드/RunTests → 보고 (판단 안 함)
      ④ 마스터: 보고를 받아 durable merge (epoch fencing 은 이미 있다)

②의 구현 후보 셋. [중요] **우리 응답이 이미 「파일 전체 텍스트」라 (B)가 성립한다:**

| | 방식 | §2.1 | 비용 |
|---|---|---|---|
| A | 마스터에 격리 worktree 를 만들어 파일을 쓰고 commit·push | [중요] **위반** — 원칙·하드룰·push 봉인 셋을 고쳐야 한다 | 낮음(기존 `integrate.py` 재사용) |
| **B** | [중요] **bare 저장소에 git plumbing** — `hash-object -w` → `update-index`/`mktree` → `commit-tree` → `update-ref`. **워킹트리 0 · 파일 I/O 0** | [완료] **문자 그대로 지킨다** (git 객체만 쓴다) | 중간(plumbing 코드 + 테스트) |
| C | 마스터가 「쓰기 주체」이나 실제 git 연산은 요청자/워커에 지시 | [완료] 유지 | 사실상 **Flow X 회귀** |

[주의] (B)는 부수 효과도 하나 해결한다 — **mojibake 파일을 건드리지 않은 채로 두는 것이 쉬워진다**
(변경된 blob 만 새로 쓰고 나머지는 base tree 그대로 재사용하므로 §14.5-③ 의 노이즈 diff 위험이
구조적으로 줄어든다).

### 14.7 [중요] 구조가 바뀐 이유 — **에이전트는 한 곳, 저장소는 여럿** (사용자 2026-08-14)

> *"기존 윈도우에서 처리할 때와 달리 **에이전트가 배치된 곳이 하나고 다른 레포들을 관리할 수
> 있어야 해서** 구조가 조금 바뀌었어."*

이것이 §14.1 의 디렉토리 모양을 설명한다. 원전은 **PC 마다 배포**되고 각 PC 에 프로젝트가
**하나**라 경로가 프로젝트 루트 기준이었다(`paths.py:5-6` 이 그 차이를 적어 뒀다 —
*"AgentTest 는 루트를 기동 시 인자로 고정했다"*). 우리는 마스터 한 대가 **N개 저장소**를 관리한다:

    projects.yaml            active: ModularStage   [중요] 가리키는 프로젝트는 한 번에 하나
    <프로젝트>/
      config.yaml
      context/      원본 · 컨텍스트 MD
      ontology/     원본 · 도메인 yaml
      repo/         [중요] **소스 클론** — 색인 대상은 `repo/Source` 뿐 (push 봉인)
      manifests/  responses/
      bm25.db · bm25_domains.db · class_graph.db     파생

[중요] **그래서 §2.1 의 *"파일을 소유하지 않는다"* 는 *"미러를 갖지 않는다"* 가 아니라 *"작업장이
아니다 = 수정·빌드하지 않는다"* 로 읽어야 한다.** 미러 N개는 트윈을 짓기 위한 **읽기 자산**이고,
push 봉인이 그 읽기 전용성을 기계로 강제한다. 원전 κ.1 이 그은 경계(*"읽기는 위반 아님, 수정·컴파일만
워커"*)와 **정확히 같다** — 우리가 문장을 더 넓게 읽고 있었을 뿐이다.

[주의] **그리고 이 사실이 §14.6 의 선택에 무게를 준다**: (A)는 마스터에 작업 worktree 를 두는데
그것을 **N개 프로젝트마다** 둬야 하므로 *"작업장이 아니다"* 를 깨는 표면이 N배가 된다.
(B)는 프로젝트마다 **bare 에 객체만** 쓰므로 N개에 균일하게 확장되고 미러의 읽기 전용성이 유지된다.

[중요] **A / B / C 는 사용자 결정 사항이다** — §2.1 은 settled 이고 push 봉인은 기계 장치다.
내 판단으로 고르지 않는다.

## §15. 소 2.3.2 — 셀프테스트: 드라이런 → [중요] **실 작업장·실 Gitea 실증** (`#143`)

### 15.1 무엇을 증명했나

    1단계 `run_dry`    격리 임시 저장소 + fake 작업장                       31/31 (음성 테스트 포함)
    2a   `run_live`    실 작업장(.43) · 실 Gitea · 스크립트 작업 단계        15/15
    2b   `run_live`    같은 경로 + [중요] **실 `claude -p` 가 매니페스트를 읽음**  15/15

[중요] **증명된 명제 하나**: 서버가 **매니페스트에만** 실은 NONCE 가 durable 산출물에 나타난다 =
서버 수집 컨텍스트가 **git 으로 실려 가 실 백엔드가 읽고 소비했다.** NONCE 를 프롬프트에 싣지
않았으므로 백엔드는 디스크의 매니페스트에서 찾는 수밖에 없었다.

[주의] **증명하지 않은 것**: *"마스터가 쓰기 주체"*. 마스터 정본은 push 봉인이라 git 쓰기는 전부
작업장에서 돌았고 마스터는 **조율 + 독립 검증**(읽기)만 했다. 그건 `#123` 이 정할 일이다.

**격리**: 작업장 메인 체크아웃 미접촉 — 옆에 worktree 둘(`wtA` 서버 역할 / `wtB` 작업장 역할).
`wtB` 는 `worktree add <base2>` 라 **매니페스트를 git 으로만** 받는다(`ls-files` 추적 +
`status --porcelain` 클린으로 단정).

### 15.2 [중요] 실증이 집어낸 결함 셋 — 전부 단위 테스트가 통과하는 동안

**① `fetch rc=128` — 마스터가 bare 를 못 읽었다.** `consumer.py` 머리말이 2026-08-08 에 실측해
적어 둔 함정을 그대로 밟았다: *"`gitea` 그룹이 없으면 git 이 「저장소가 아니다」라고 하는데
**실제 원인은 권한**이다 — 메시지가 원인을 감춘다."* 대화형 세션은 그룹 추가 **이전에 시작**됐으면
그것이 없다(`id -nG` 확인, `/etc/group` 엔 `sim` 이 있다). [중요] 고치면서 **그룹 판정을 다시 쓰지
않고 색인기의 `_git` 을 재사용**했다 — 복제하면 어긋난다.

**② `work_id` 를 밖에서 계산해 통과가 운이었다.** 2b 첫 구동은 통과했지만, 내 스캐폴딩이
`work_id` 를 따로 만들고 `run_live` 는 자기 것을 만들어서 **초가 우연히 맞아** 매니페스트 경로가
일치했을 뿐이었다. [중요] **계약으로 막았다** — `work_fn_cmd(gidx, probe_rel, nonce_key, work_id)` 로
하니스가 넘긴다. 고치고 재구동해 통과를 다시 확인했다.
[주의] *"통과했으니 됐다"* 로 넘어갔으면 증명이 아니라 우연을 기록한 셈이 된다.

**③ 로컬 `attempt` 브랜치가 남았다 — 원격만 보고 「흔적 0」이라 단정했다.** `wtB` 가
`checkout -B <attempt>` 로 만든 브랜치는 **공유 저장소의 ref** 라 worktree 를 지워도 남는다.
3회 구동에서 **로컬 7개**가 쌓였다(원격은 깨끗). [중요] **단정을 원격에만 걸어 둔 것이 결함이었다** —
`정리 후 작업장 로컬에도 흔적 0` 을 추가했다.
[주의] 그리고 고치는 중에 **패턴을 또 틀렸다**: `for-each-ref 'refs/heads/attempt/{id}.*'` 는 그 `*`
가 `/` 를 넘지 못하는데 브랜치명이 `attempt/<id>.<i>/<host>/<ts>` 로 슬래시가 셋이다
(실측: for-each-ref **0건** / `branch --list` **6건**). 검증된 쪽으로 바꿨다.

### 15.3 [중요] `#164`(파이프라인 ↔ 색인) 의 실측값이 나왔다

셀프테스트 3회 구동이 만든 push 로:

    색인기 깨어남   **15회**
    실제 색인       **1회 미만** — 14회가 `재색인 건너뜀 (컨텍스트 MD 변화 없음)`
    로그 실물       `[완료] Sim/ModularStage: b1ba6af9→b1ba6af9 · 재색인 건너뜀`

[완료] **오염은 없다** — 두 겹이 막았다: 소비자가 `merge --ff-only FETCH_HEAD` 로 **main 만** 전진시키고,
diff 를 **`-- Source`** 로 한정한다. 셀프테스트 브랜치는 main 을 움직이지 못한다.
[중요] **그러나 낭비는 실재하고 이제 숫자가 있다** — 원전 `watch_state.py` 의 *"분산 작업 활성 검사 =
Git 폴링 일시 중지"* 가 없어서다. 소 3.5.1(`#164`)은 이제 **추측이 아니라 15:14 라는 실측** 위에 있다.

### 15.4 사후 상태 (직접 확인)

    .43     main @ b1ba6af · dirty 0줄 · worktree 1개 · selftest 잔여 0 · 임시 디렉토리 0
    Gitea   selftest 브랜치 0개
    [주의] 2026-08-09 자 옛 잔여물(`attempt/177293f3/…` 등 로컬 2·원격 7)은 **내 것이 아니고
       건드리지 않았다** — 이전 세션의 찌꺼기다. 지우는 것은 사람의 판단(`work/cleanup.py` 규약)

전체 스위트 **1280/1280** ([주의] **이 수는 불완전하다 — §18 정정**). [주의] `run_live` 는 실 하드웨어가 필요해 단위 스위트에 넣지 않았다 —
명시 호출 전용이다. 그 사실 자체가 위험이므로 여기 적는다: **자동으로 돌지 않는 검증은 안 돌게 된다.**

### 15.5 큐를 거친 e2e — **26/26** (`#141` 핵심 잔여 해소)

`run_live(via_queue=True)` 가 실 큐(8101)를 거쳐 돈다. 우회하지 않고 **큐가 정하게** 했다:

    work 등재 → task N 등재(depends_on 없음) → [중요] **claim** (어느 probe 를 받을지 큐가 정한다)
    → epoch 발급 확인 → 작업장 편집 → attempt push → **submit(epoch 동봉)** → **verify(pass)**
    → [중요] 큐 상태가 `verified` → 마스터 독립 NONCE 검증 → **work 종결** → 흔적 0

[중요] **claim 을 우리가 순서대로 고르지 않은 것이 중요하다** — 고르면 claim 로직(우선순위·의존·epoch
발급)을 **재는 게 아니라 우회하는** 것이 된다. 반환된 `task_id` 로 어느 probe 인지 되찾는다.

**work 종결까지 붙였다** — 원전 실측(2026-06-21, 배포에서 5건): *"task cancel·브랜치 삭제만으론
work 메타가 `in_progress` 로 잔존해 watcher 가 paused 되고 큐에 잔재가 쌓인다."*
`PATCH /api/v1/works/<id> {merge_status: cancelled}` 로 닫고 **단정으로 지킨다.**

### 15.6 [중요] 그 결함이 지금 우리 큐에 실재한다 — 그리고 칸 사이 상호작용이 하나 있다

큐 실측(2026-08-14, `works 8 / tasks 10` 중 내 것은 정상 종결된 1 work · 2 task):

    [중요] in_progress 로 박힌 work **4건**   20260808_1809 · 20260808_1846 · 20260809_1742 · 20260809_2113
                                          (전부 verified 0/1 — 완료된 적이 없다)
    ready_for_review 로 멈춘 work 3건     20260808_1806 · 20260809_1737 · 20260809_2107
    tasks                                submitted 2 · failed 2 (전부 2026-08-09 자 옛 잔재)

**지금은 아프지 않다** — 원전에서 이것이 아픈 이유가 `watch_state.py` 의 *"분산 작업 활성 검사 =
Git 폴링 일시 중지"* 인데, [중요] **우리에게 그 가드가 아직 없다**(그것이 `#164`다).

[중요] **그래서 순서 위험이 생긴다**: `#164`(watch_state 가드)를 **큐를 치우기 전에** 이식하면,
박혀 있는 `in_progress` 4건이 그 순간부터 **색인을 계속 멈춘다.** 가드가 의도대로 동작하는데
결과는 *"색인이 조용히 안 돈다"* 가 된다 — 이 저장소가 반복해 물린 그 유형이다.
→ **`#164` 이식 전에 큐 잔재를 먼저 정리**해야 한다. 두 칸이 순서로 묶였다.

[주의] **내가 치우지 않았다.** `work/cleanup.py` 규약이 *"원격 attempt/task 를 없애는 것은 요청자와
사람의 판단"* 이고, 이 7건은 **2026-08-08/09 세션의 실작업 잔재**(내 시험 산출물이 아니다).
지우려면 사람의 결정이 필요하다.

## §16. 소 3.5.9 — 큐·원격 잔재 정리 (`#186`, 사용자 승인 2026-08-14)

### 16.1 [중요] 새로 만들지 않았다 — 기존 도구가 이미 있었다

`work/cleanup.py` 의 `plan`/`apply` 를 썼다(CLAUDE.md 운영 명령에 있는 그것). [주의] 첫 호출은
`AX_PROJECTS_ROOT` 없이 죽었는데 **그게 정상**이다 — §5.5.3-④ fail-closed, 폴백 없음.

**도구의 판단이 나보다 보수적이었다.** 지우겠다고 한 것은 **`.2` 의 로컬 `task/49c34650` 하나**뿐:

    보존  attempt/… (3건)        "origin/main 에 병합되지 않았다 — **증거일 수 있다**"
    보존  .ax/work/<id>/ submitted  "아직 진행 중이다"
    보존  .ax/work/<id>/ failed     "**왜 실패했는지 볼 유일한 기록이다**"
    보존  .ax/work/bench-*/         "큐에 없다 — **모르는 것을 지우지 않는다**"
    [중요] 원격은 통째로 미접촉        "원격 attempt/task 를 없애는 것은 요청자와 사람의 판단"

[중요] **이유를 달아 보존하는 것이 이 도구의 값이다.** 내가 손으로 지웠으면 *"failed 인데 뭐"* 로
넘어갔을 자리다.

### 16.2 큐 메타데이터 — 도구가 안 건드리는 곳

`#186` 의 실제 블로커는 git 이 아니라 **큐의 work 메타데이터**였다. `merge_status` 를
`cancelled` 로 닫았다 — [중요] **메타데이터만이고 브랜치·산출물은 손대지 않는다.**

    before   in_progress 4 · ready_for_review 3   (전부 **verified 0/N** — 완료된 적 없음)
    after    [중요] **active 0건** · 8건 전부 cancelled

정리 대상 7건은 전부 2026-08-08/09 자 **배선 확인·e2e 시험 작업**이다(*"워크플로우 복구 배선 확인"* ·
*"골조 전달 확인"* · *"[AX] 러너 배선 e2e"* ×4). [주의] `ready_for_review` 도 **v0/2** 라
*"좋은 결과가 검토 대기"* 가 아니라 *"전부 terminal 인데 verified 0"* 이었다 — 상태 이름만 보고
*"사람의 결정이 걸려 있다"* 고 판단하면 틀린다.

[주의] **내가 또 잘렸다** — 첫 PATCH 7건 중 **5건이 404**. 화면에 34자로 잘린 `work_id` 를 그대로
타이핑했다. [중요] **id 를 API 에서 읽어** 다시 돌렸다(200×5). *사람이 보는 표시를 식별자로 쓰지 않는다.*

### 16.3 사후 상태 — 증거 보존 확인

    큐        work 8건 전부 cancelled · **active 0** → [중요] `#164` 의 순서 블로커 해소
    산출물    `.2` 9개 · `.43` 4개  — **그대로**
    attempt   로컬 3 · **Gitea 원격 3 전부 그대로** (증거)
    삭제된 것 `.2` 의 **로컬** `task/49c34650` 1건 (도구의 판단)

[주의] **원격 `task/*` 4건은 남아 있다** — `cleanup.py` 가 원격을 절대 건드리지 않는 정책이라서다.
`#164` 를 막지 않으므로(가드는 **큐의 active work** 를 본다) 그대로 뒀다. 지울지는 별도 판단이다.

[중요] **`#164`(watch_state 가드)를 이제 이식할 수 있다** — 이식하는 순간 색인이 조용히 멈추는
조건이 사라졌다.

## §17. 소 3.5.1 — 색인 일시 중지 게이트 이식 (`#164`)

`master/events/gate.py` + 소비자 배선 + `ax-indexer.timer` + `SuccessExitStatus=4`.
`test_gate.py` **17/17** · 전체 **1297/1297** ([주의] **불완전 — §18 정정**). 원전 = `watcher/watch_state._has_active_distribute_work`.

### 17.1 [중요] 내가 적어 둔 지침이 틀렸고, 원전 정독이 잡았다

`#164` 에 *"`{merged, rejected, cancelled}` 제외 전부가 active 이므로 `ready_for_review` 도
active"* 라고 적어 뒀는데 **원전은 정반대를 말한다:**

> *"**Phase 2 변경: `in_progress` 만 pause 조건.** `ready_for_review` 는 auto_cleanup 이 이미
> main 으로 복귀시킨 시점이라 **watcher 재개해야 함**(리뷰 결정은 비동기)."*

[주의] **원전에 「active」가 둘 있는데 내가 섞었다** — cleanup·중복검사용 집합과 **pause 조건**은
다른 개념이다. 전자를 후자로 옮겨 적었다. [중요] 그 정정을 **테스트로 못박았다**(`ready_for_review` ·
`merged` · `rejected` · `cancelled` · 빈 값 전부 *"멈추지 않는다"* 를 단정).

pause 이유(원전): *"feature 브랜치 작업 중 main 인덱싱 무의미 + **워커들과 git lock 경쟁 방지**"*.

### 17.2 [중요] 실증이 내 구현의 결함을 둘 더 집어냈다

**① 유닛이 빨갰다 — 내가 방금 쓴 주석이 실시간으로 재현됐다.** 게이트가 종료코드 4를 내는데
설치본에 `SuccessExitStatus=4` 가 없어 `status=4/NOPERMISSION → Failed with result 'exit-code'`
가 떴다. [중요] **저장소 사본만 고치고 설치본을 잊었다** — *"늘 빨간 유닛은 유닛이 아니다"* 를 적어
놓고 그 상태를 만들었다. `pkexec` 로 반영 후 확인: `status=4` 인데 `is-failed` = **inactive**(초록).

**② [중요] *"유실 아님"* 이 틀렸다.** 게이트가 멈출 때 스풀을 **비우도록** 짰다(남기면 `.path` 가
조건이 계속 참이라 재트리거를 반복할 수 있어서). 그런데 소비자는 `for ev in batch.events` **안에서만**
일해서 **이벤트가 0건이면 fetch 조차 하지 않았다.** 실측이 그 자리를 그대로 보여줬다 —
게이트가 넘긴 뒤 재실행이 `이벤트 0건 → 프로젝트 **0개**` 였다. **타이머를 붙여도 따라잡지 못한다.**

→ **소비자를 진짜 state-based 로 고쳤다**: 스풀이 비면 등록된 프로젝트마다 **합성 이벤트 한 건**으로
상태 대조를 돈다(미러 fetch 는 로컬 bare 라 ms 단위). 이제 `이벤트 0건 → 프로젝트 **1개** ·
`b1ba6af9→b1ba6af9 · 재색인 건너뜀`. [중요] **타이머가 별도 모드 없이 그대로 따라잡기가 된다.**
[주의] `project_id` 를 못 읽는 프로젝트는 조용히 건너뛰지 않고 `poll_skipped` 로 센다.

### 17.3 게이트만 두지 않았다 — 타이머를 **같은 커밋에** 넣었다

리포트 13 §19.3 이 상태 화면에서 물린 것: *"가드는 맞고 결론이 틀렸다. 가드를 두고 타이머를 안
두면 **갱신 주체가 아무도 없다.**"* [중요] 그 교훈을 이번엔 **가드와 같은 커밋에** 적용했다.

    ax-indexer.timer   OnBootSec=3min · OnUnitActiveSec=10min · RandomizedDelaySec=30s
    근거               분산 작업 한 바퀴가 분 단위(파견 45초·통합 빌드 142초·RunTests 74초)라
                       작업 종료 후 10분 내 따라잡는다. `.path` 가 push 마다 깨우므로 이 타이머는
                       **게이트에 걸린 동안만** 실질적으로 일한다 — 더 짧으면 헛기동만 늘어난다
                       (실측: 15회 중 14회가 이미 `재색인 건너뜀`)

### 17.4 실증 (실 큐·실 유닛)

    in_progress work 생성 → 유닛 기동 → [중요] `색인 일시 중지 … 1건` · 종료코드 4 · **유닛 초록**
    work 종결          → 유닛 기동 → `Finished` · 상태 대조 정상
    타이머             enabled·active · 다음 발동 10분 뒤 (실측 확인)
    사후               work 11건 전부 cancelled · **in_progress 0** (내 probe 3건도 종결)

[주의] **게이트가 「모르면 진행」으로 기울어 있다** — 큐에도 디스크에도 못 물으면 멈추지 않고
`degraded` 에 사유를 실어 로그에 남긴다. 항상 멈추는 게이트는 색인을 영구 정지시키고 그건
게이트가 아니라 고장이다. [중요] 대신 그 선택이 **워커와 경쟁할 위험을 조용히 택하는 것**이라는 점을
모듈 주석에 적어 뒀다 — 나중에 뒤집으려면 그 문장을 보고 뒤집어야 한다.

## §18. [중요] 이 세션이 인용한 테스트 수치가 전부 불완전했다 — 그리고 근원은 문서였다

### 18.1 무엇이 틀렸나

    내가 인용한 값   1249 · 1280 · 1297 · 1307       (리포트 §14·§15·§17 · 레드마인 노트 여럿)
    [중요] 진짜 값       **2268/2268** (파일 50개 · 실패 0)

**실패 판정은 맞았다** — 종료코드와 `Error` 문자열로 봤으니 *"실패 0"* 은 정확하다. [중요] **틀린 것은
숫자다.** 테스트 파일이 **두 형식**을 쓰는데 내 명령이 앞것만 잡았다:

    형식 A (37파일)   `[완료] test_x: 21/21 통과`
    형식 B (13파일)   `====…`  /  `통과 46 · 실패 0`  /  `====…`      ← 마지막 줄이 **구분선**

### 18.2 [중요] 근원은 내 즉흥 명령이 아니라 **`CLAUDE.md` 에 적힌 명령**이었다

    for f in master/test_*.py; do .venv/bin/python "$f" 2>&1 | tail -1; done

이 저장소가 *"수가 아니라 **세는 법**을 적는다"* 며 남긴 명령이 **그 세는 법이 틀린** 것이었다.
나는 그것을 따랐다. → **명령을 고쳤다**(두 형식 + 종료코드 판정, 왜 틀렸는지 주석에 남김).

### 18.3 [주의] 그 방법이 **오류를 감춘다** — 그게 더 나쁘다

같은 세션에서 `sqlite_util` import 를 잘못 넣어 **테스트 3개가 `NameError` 로 죽었는데**,
크래시한 파일은 수치를 안 찍으므로 **합계가 1307 그대로 보였다.** 사람이 보는 숫자가 변하지
않으니 *"통과했다"* 로 넘어갈 수 있었다.

[중요] **이것이 이 저장소가 반복해 물린 「조용히 틀리는」 유형이고, 이번엔 그 대상이 나 자신의 측정
도구였다.** σ 계열이 만든 규칙(*"`[x]` 마킹은 검증 가능한 인공물의 실 존재와 짝지어야 한다"*)이
테스트 합계에도 그대로 적용된다 — **합계는 인공물이 아니라 파생값이고, 파생값은 스스로를 검증하지
않는다.**

[주의] 그리고 이번 세션의 다른 세 실수와 **같은 부류**다: 1세그먼트 경로로 라우트를 재고(§7.5),
`for-each-ref` 패턴이 `/` 를 못 넘는 것을 모르고 정리했다 하고(§15.2-③), 화면에 잘린
`work_id` 를 타이핑했다(§16.2). [중요] **네 번 다 「사람이 보는 표시를 실체로 착각」했다.**

### 18.4 정정 범위

리포트의 해당 수치에 *"불완전 — §18 정정"* 을 달았고, `CLAUDE.md` 의 명령을 고쳤다.
레드마인 노트의 수치는 **지우지 않고** 이 절을 근거로 남긴다 — 기록에서 지우면 *왜 틀렸나*가
사라진다.

## §19. 소 3.5.3 — SQLite 동시성 PRAGMA 를 한 자리로 (`#179`)

`master/sqlite_util.py` 신설 · `test_sqlite_util.py` **10/10**.

    적용   graph/db.py · graph/dependency.py · [중요] context_search/bm25.py (빠져 있던 곳)
    실측   bm25.db → `{'journal_mode': 'wal', 'busy_timeout': 10000}`
    사후   색인기 1회 정상 · 검색 `indexed_documents: 1056` 정상

[중요] **값을 한 자리에 모은 이유는 이번 결함 자체가 「흩어져서」 생겼기 때문이다.** `graph/db.py` 가
스스로 *"프로세스 간에는 WAL + busy_timeout 이 담당한다"* 고 적어 두고 **형제 모듈 bm25 에서
빠뜨렸다.** 테스트가 *"`busy_timeout` 을 직접 `execute` 하는 곳이 없다"* 를 단정해 재발을 막는다.

### 19.1 [주의] 실측이 원전 서술을 정정했다

원전은 *"기본 `busy_timeout=0` 이라 동시 쓰기 시 즉시 `database is locked`"* 라 적었는데, 그것은
**raw SQLite** 기준이다. Python `sqlite3.connect` 는 `timeout=5.0` 기본값이라 **5000** 이 걸린다
(실측: 새 연결이 `busy_timeout: 5000`). [중요] **실제 갭은 WAL 부재였다** — WAL 이 없으면 읽기↔쓰기가
서로 막아 그 5초에 닿을 확률이 크게 오른다. 원전의 결론(둘 다 걸어라)은 맞고 **근거 문장만** 달랐다.

[주의] 원전이 **기각한 것도 옮겼다**: *"`locked` 명시 재시도 루프는 미채택 — `busy_timeout` 이 네이티브
블록-후-재시도이고 WAL 이 경합을 제거하므로 redundant."* 재시도 루프를 새로 만들지 말 것.

## §20. 소 3.5.5 — [중요] **우리에게 해당하지 않는다** (`#181` 재범위)

원전이 고친 것은 **한국어 윈도우 콘솔(CP949)** 에서 em-dash·박스드로잉·이모지를 `print` 하면
`UnicodeEncodeError` 로 **로그 한 줄 없이 프로세스가 즉사**하는 문제다. 우리 마스터 실측:

    systemd 아래   stdout: **utf-8** · fs: utf-8 · preferred: UTF-8   (PEP 538 로케일 강제)
    출력 시험      em-dash · 박스 ─│ · 이모지 [중요] **성공**
    저널 실물      [중요]·[완료]·한글이 이미 정상 출력 중

[중요] **리눅스 마스터에 이 수정을 넣는 것은 카고 컬트다.** κ.8 이 같은 함정에 *"혼동 주의"* 를 달아 둔
것과 같은 자리 — 그 표가 `ue_builder.py`/`ue_test_runner.py` 를 *"리눅스로 옮기는 대상 아님"* 이라
명시했듯, 콘솔 인코딩 가드도 **CP949 콘솔이 있는 쪽**의 것이다.

[주의] **그러나 「해당 없음」이 아니라 「자리가 다르다」** — 우리 Python 이 `.2`(윈도우)에서 도는 자리가
생기면 그때 필요하다. 지금은 `.2` 에서 우리가 돌리는 것이 git·UE·`claude -p` 뿐이라 해당이 없다.
[중요] 인코딩 문제군의 **읽기**(`source_text.decode`)는 이미 이식됐고 **직렬화**(surrogate, `#180`)는
아직 남았다 — 세 다리 중 둘째만 남은 셈이다.

## §21. 소 3.5.4 — [중요] **치환을 이식하지 않았다** (`#180` 재범위)

원전이 겪은 것: lone UTF-16 surrogate 가 MCP 결과에 섞이면 `json.dumps(**ensure_ascii=True**)` 가
**에러 없이** `\udXXX` 를 내보내고 → Claude Code(Node) 파싱 → Anthropic 요청 직렬화에서 **400 으로
요청 전체 거부 = 세션 사망**. 그래서 `server.py` 의 `json.dumps` **64곳**을 `safe_dumps`
(surrogate → U+FFFD)로 일괄 교체했다.

### 21.1 실측 — 우리에게 그 실패 모드가 없다

    원전 방식 `ensure_ascii=True`    dumps OK · encode OK      → [중요] **조용히 나간다** (세션 사망 경로)
                                     `'{"a": "\\ud800"}'` 이 그대로 와이어에 오른다
    우리 방식 `ensure_ascii=False`   dumps OK · encode **실패** → [완료] 그 호출만 loud 하게 죽는다
                                     `UnicodeEncodeError: 'utf-8' codec can't encode '\ud800'`

라이브러리가 도구 호출마다 `except Exception` 으로 격리해 `is_error=True` 를 돌려준다(`server.py:421`).

### 21.2 [중요] 그래서 치환을 이식하면 **퇴행이다**

원전이 U+FFFD 치환을 택한 이유는 **대안이 세션 사망**이었기 때문이다. 우리는 이미 loud 하다 —
치환을 넣으면 **loud 실패를 조용한 U+FFFD 로 바꾸는 것**이고, 이 저장소가 가장 경계하는
*"조용히 틀리는 것"* 을 스스로 만드는 셈이다.

[주의] **별도 카나리도 필요 없다.** 원전이 카나리를 둔 이유는 *"원천을 특정 못해 다음 발생 시 증거를
모으겠다"* 였는데, 우리에게는 `UnicodeEncodeError` 의 트레이스백이 **그 자체로 카나리**다.

### 21.3 [중요] 그러나 그 보호는 **우연이다** — 그것만 규약으로 못박았다

`ensure_ascii=False` 는 한국어를 그대로 내보내려고 쓴 것이고, surrogate 보호는 **부수 효과**다.
누가 원전 코드를 베끼거나 *"ASCII 가 안전하다"* 고 생각해 바꾸면 **보호가 조용히 사라진다.**

`test_mcp_boundary.py` **7/7** 이 그 자리를 지킨다:

    ① 우리 방식은 encode 에서 실패한다(loud) · 원전 방식은 조용히 나간다   ← 전제 자체를 단정
    ② 경계에 `ensure_ascii=True` 가 없다
    ③ [중요] `json.dumps(` 개수 == `ensure_ascii=False` 개수  ← **생략하면 기본이 True** 라 그것도 잡는다
    ④ 경계에서 조용한 치환(`errors=replace/ignore`)을 쓰지 않는다

**결론**: `#180` 은 «완료»가 아니라 «재범위»다 — 이식할 것이 없고, **이식하지 않는 이유를 테스트로
남겼다.** `#181` 과 같은 처리다(자리가 다르다 / 이식이 퇴행이다).

## §22. 소 3.5.8 — BM25 0건 진단 (`#184`) · §23. 소 3.5.2 — 자리가 없다 (`#165`)

**§22.** `bm25.diagnose(query)` + `stats()`. [주의] **원전처럼 로그를 찍지 않았다** — 이 저장소의
모듈은 **사실을 반환하고 호출자가 찍는다**(테스트 가능·전역 상태 없음). 원전 카나리는 `watch.exe`
의 **상주 콘솔**에 묶인 방식이었다. **기제를 옮기고 형태는 우리 것으로** 뒀다.

    "미션 태스크 실행"      → results=10 · "결과가 있다"
    "존재하지않는단어xyzq"  → results=0  · [중요] "토큰이 하나도 색인 어휘와 맞지 않는다"
    빈 색인                → results=0  · [중요] "색인이 비어 있다"

[중요] 필요 근거는 실제 사건이다 — 리포트 13 §19.1 에서 *"도메인이 비어있어"* 라는 보고를 받고
처음부터 재야 했다. [주의] **만드는 중 낸 버그 둘을 실측이 잡았다**: `self._table`(모듈 함수를 메서드로)
· [중요] **`count` 를 property 로 착각** — 메서드라 `self.count == 0` 이 항상 False 였고 *"색인이 비어
있다"* 분기가 **죽어 있었다**(`stats()` 가 바운드 메서드를 반환하는 것을 보고 잡았다).

**§23.** `worker/safety.py`(QuickEdit freeze 가드·절전 차단·크래시 핸들러)는 **윈도우 콘솔 데몬**
전제다. 우리 `worker/` 는 **README 뿐**이고 파견은 **SSH `claude -p`** — 상주 데몬이 없다.
`QuickEdit`/`SetThreadExecutionState`/`faulthandler` 우리 코드에 **0건**. `#181` 과 같은 판정:
**「해당 없음」이 아니라 「자리가 없다」.**

[중요] **재범위 셋(`#180` `#181` `#165`)의 공통 구조**: 원전의 수정은 옳았고 그 수정이 겨눈 **조건이
우리에게 없다.** 그대로 옮기면 카고 컬트(181·165)이거나 **퇴행**(180)이다. κ.8 이
`ue_builder.py`/`ue_test_runner.py` 에 *"리눅스로 옮기는 대상 아님, 혼동 주의"* 를 달아 둔 것과
같은 부류 — [중요] **포팅에서 「안 옮기는 판단」도 근거가 필요하다.** 셋 다 **닫지 않았다.**

## §24. 중 3.1 — ①추정 이식분 **실물 대조** 3/3 (`#147`)

[중요] **이름 대조를 쓰지 않았다.** §7.1 에서 그것이 **양방향으로** 틀리는 것이 이미 드러났다 —
동명 이식을 「인용 0」으로 잡고, 이름이 달라진 이식을 「미이식」으로 잡는다. 그래서 **공개 함수 ·
능력 이름** 단위로 봤다.

### 24.1 온톨로지 11파일 (`#148`) — 이식 8 · 미이식 2

| 원전 | 우리 | |
|---|---|---|
| `ontology_synthesizer` | `synth.py` + `package.py` | [완료] `merge_preserve_locked` 는 **동명** |
| `ontology_refresh` | `stale.py` | [완료] `compute_stale_domains`→`compute` |
| `ontology_drift` | `drift.py` | [완료] `audit_drift`→`audit` |
| `ontology_path_sync` | `sync.py` | [완료] |
| `ontology_index_sync` | `context_search/domain_index.py` | [완료] `fingerprint`/`stored_fingerprint` — 같은 기제 |
| `ontology_loaders` | `domain_md.py` + `contexts.excerpt_body` | [완료] |
| `ontology_types` | 각 모듈의 dataclass | [완료] 구조 차이 |
| `ontology_prompt` | `prompt.py` | [완료] 단 `build_classification_prompt` 는 **의도적 미이식**(자동승급 폐기) |
| [중요] `ontology_descriptions` **270** | — | **미이식** → `#187` |
| [중요] `ontology_pkg_audit` **235** | — | **미이식** → `#188` |
| `ontology_rename` | — | 이미 `#167` |

[중요] **`ontology_descriptions` 를 놓칠 뻔한 이유가 중요하다** — 우리 `layers.py` 가 이름이 비슷해서
대응처럼 보이지만, 그것은 **다른 원전 파일**(`ontology_layers.py`, Phase η.6.1)의 이식본이고
**레이어 *추정*(LLM 0)** 이다. *"레이어가 무엇인가"* 와 *"그 레이어가 무슨 책임을 지는가"* 는
다른 산출물이다. **정황 둘이 일치**했다 — §7.5 라우트 대조에서
`/api/v1/ontology/description/{domain}/{layer}` 가 「원전에만」에 있었고, 원전 소비 도구에
`get_layer_description`(산출물이 `verified_by_user` 로 잠긴다)이 있었다.

[주의] `pkg_audit` 도 같은 함정 — 우리 `drift.audit` 은 *"트윈과 소스가 어긋났나"* 이고 원전
`pkg_audit` 은 *"도메인 MD ↔ 패키지 yaml **구조 정합**"* 이다. **원전은 둘을 다 갖고 있었다.**

### 24.2 graph 2파일 (`#149`) — [중요] **미이식이 더 나은 사례**

`class_graph_query`(7): `find_ancestors`/`find_siblings`/`find_subclasses` **동명 이식** ·
`infer_domain_from_query`→`context_search/infer.py` · `domain_class_files`→`work/skeleton.py`.

**`class_graph_ontology`(16함수)는 일부러 안 옮겼다.** 실측:

    class_graph.db   classes **1806** · methods **6380** · [중요] domains **0** · class_ontology **0**
    ontology/domains/  도메인 **7개** (채워져 있다)

`infer.py` 머리말이 근거다 — *"출처는 패키지 yaml 이다 — DB 표가 아니다. … **죽은 표를 근거로
삼지 않는다.**"*

[중요] **그 선택이 원전의 문제군 하나를 원천 제거한다.** 원전은 DB 표와 MD/YAML **둘**을 갖고 있었고,
어긋남을 잡으려고 **η.4 drift 감사**(*"inactive 도메인 · archive 잔재 · **NULL 도메인 분류**"*)를
따로 만들어야 했다. 출처가 하나면 그 감사가 **필요하지 않다.** → **되돌리지 말 것.**

[주의] **정정 하나**: `graph/__main__.py` 가 두 표에 *"← 중 1.3 이 채운다"* 를 출력했는데 **거짓
약속**이었다(중 1.3 은 추론 파견이고, 채우지 않는 것이 **결정**이다). → *"[중요] 일부러 비움 (SSOT 는
`ontology/*.yaml`)"* 로 바꾸고 근거를 주석에 남겼다. **우리 출력이 우리 설계를 잘못 말하고 있었다.**

### 24.3 MCP/HTTP 표면 (`#150`) — 능력 이름으로 재야 했다

[중요] **함수 수로는 못 잰다** — 원전은 능력 하나당 **(MCP 도구 + HTTP 라우트 + impl) 3벌**이라
12파일에 공개함수 **132개**다. 능력 이름: 원전 MCP 도구 **40개** vs 우리 **24개**.

    [완료] 대응        add_object_alias→add_alias_tool · create_domain→create_domain_tool ·
                  audit_ontology_drift→drift_audit_tool · edit_ontology_item **동명** ·
                  delete_ontology_item→remove_ontology_item_tool · refresh_ontology→sync_ontology_tool ·
                  export/import_infra_state→transfer.py · delete_domain→webui 라우트
    ② 자리 없음    cleanup_inactive_domain · cleanup_null_classifications
                  ([중요] 자동승급 폐기 + DB 표 미사용이라 **정리할 대상 자체가 없다**) ·
                  위키 계열 6종 (비개발직군 확장 = 마일스톤 밖)
    [중요] 기존 칸     태스크 템플릿 5종(#138/#140) · 컨텍스트 MD 감사 4종(#160) ·
                  analyze_search_log(#161) · rename 2종(#167) · log 태깅 2종(#169)
    [중요] 신규 3건    멤버 제거·필드 편집(#189) · 스테이징 편집 세션(#190) · 버전 핸드셰이크(#191)

**`#190` 스테이징 세션이 특히 아프다** — 원전 근거가 사용자 발견이었다: *"오탐 하나 고치려면
도메인 전체 `refresh-ontology` 가 필요하다."* 그 해법을 원전은 *"`DoubleBufferedIndex` 철학
이식"* 이라 적었고 [중요] **우리는 그 더블버퍼를 이미 갖고 있다**(`bm25_a`/`bm25_b`). 같은 철학을
온톨로지 편집에 적용하는 칸이다. [주의] 우리는 **항목 단위 편집은 되고** 「여러 항목을 모아 한 번에
확정/취소」가 없다 — 편집 도중 실패하면 **반쪽 상태가 남는다.**

**`#191` 버전 핸드셰이크는 원전이 우리에게 남긴 지시였다** — κ.9 계약 표면 6개 중 하나로
*"**기존 자산 재사용** — `get_server_version` 이 이미 있다. 신규 repo 는 독립 버저닝으로 가되
**이 조회 경로 유지**"* 라고 적혀 있는데 이행하지 않았다.

### 24.4 [중요] 분모가 세 번째로 움직였다 (70 → 75)

    62 → 67   소 1.1.2 정독이 σ 가드 결함 5건을 찾아서
    67 → 68   소 1.1.3 색인이 BM25 카나리 부재를 찾아서
    70 → 75   중 3.1 대조가 미이식 5건을 찾아서
    (68 → 70 은 큐 잔재 정리 · 매니페스트 배달 경로)

[중요] **전부 「읽거나 재서」 나왔다.** 마일스톤 3 에서 원전 독파가 칸 넷을 찾아 32→36 이 된 것과
같은 형태다 — 그래서 `CLAUDE.md` 에 *"그 움직임은 정상이고 기록한다"* 를 적었다.

## §25. 중 4.2 — σ 감사 도입 (`#174`·`#175`·`#176`)

`master/sigma_audit.py` + `test_sigma_audit.py` **22/22** · 전체 **2339/2339**.
원전 `audit_matrix.md` **99줄** 이식 — 그 문서는 우리 저장소에서 **인용 0회**였다.

### 25.1 왜 이것을 골랐나 — 이번 세션의 데이터

내가 이 세션에 낸 결함이 **9건**이고 **전부 같은 부류**였다: *조용히 틀리는 것*. 그중 둘은
**측정 도구 자신**이 조용히 틀린 것이다(테스트 합계 · σ.1 검사식). 원전에 그 탐지법이 99줄로
있었고, 그 문서가 만들어진 계기가 정확히 같은 것이다:

> *"plan v4.5.1 에 σ.1·σ.2 모두 `[x] 완료` 로 마킹되어 있었으나 **디렉토리 자체 부재 + 산출물
> 미생성 확인.** plan 의 `[x]` 가 실 작업 완료를 의미하지 않은 사례."*

### 25.2 [중요] σ.1 — 이번 세션의 「완료」 22건을 세 축으로 대조했다

    축   ① 실 코드   ② 실 산출물   ③ 카나리/증거    — **셋은 서로를 대신하지 못한다**
    결과 완료 주장 22건 · [중요] 축이 빈 것 **0건**

[중요] **그런데 첫 실행은 1건(`#124`)을 잡았고, 그것은 감사 자신의 검사식이 틀린 것이었다** —
`grep -c`(개수 `3`)에서 문자열 `"stale_epoch"` 을 찾고 있었다. 실물은 있었다
(`test_coordinator.py:133-134` 가 *"stale epoch 은 거부된다"* · *"`stale_epoch:1<2`"* 를 단정).

[주의] **오탐 1건이 이 감사의 값을 깎지 않는다 — 오히려 그 반대다.** 원전이 σ.1 산출물을
*"자기 자신이 부재였음을 인정하고 백필"* 로 시작한 이유가 이것이겠다. **검사식도 감사 대상이다.**

[주의] σ.1 을 **코드로 만들지 않았다.** 원전도 사람이 표를 만들었고, 값은 *"세 축을 독립으로 확인하는
절차"* 에 있다. 코드로 만들면 「주장된 산출물 경로를 파싱」하는 취약한 것이 되고 **그것이 또 하나의
조용히 틀리는 자리**가 된다. 절차는 `sigma_audit.py` 의 σ.1 주석에 뒀다 — 돌리는 사람이 코드 옆에서
읽어야 한다. 재검증 주기는 원전대로 **마일스톤 갱신 시점**이다.

### 25.3 σ.2 정적 검사 — [중요] 좁히는 조건 셋이 이식의 본체였다

첫 이식은 **114건**을 냈다. 원전은 **6건**이었다. 그 격차가 곧 이식이 덜 된 증거였고, 원전
패턴 문장을 다시 읽어 조건 셋을 채웠다:

    ① 넓은 핸들러만        원전 원문에 *"`except Exception`(또는 bare except)"* 이 있었다.
                          `sqlite3.OperationalError`·`TypeError, ValueError` 처럼 **좁게 잡은 것은
                          의도적**이다 — 무엇이 날아오는지 알고 그것만 받는다        114 → 54
    ② 예외를 값으로 돌려주면 조용하지 않다   `except E as e: return _fail(e)` — 실패가 **데이터로
                          전파**된다. 우리 MCP 도구 24개가 전부 그 형태다              54 → 38
    ③ 의도는 **핸들러 주석**에서도 찾는다    독스트링만 보면 주석이 소실된다. 핸들러가 셋인 함수는
                          독스트링 하나로 어느 것을 말하는지 알 수 없다                 → 35

[중요] **②·③은 원전 문서에 글자로 없다** — 사람 검토자가 암묵적으로 하던 판단이다. **글자만 옮기면
우리 관례를 결함으로 센다.**

최종: **파일 120개 · silent fallback 51건 · 의도 없음 35건 (주기 16건).**

### 25.4 [중요] 스캐너가 자기 버그를 테스트로 잡았다

`bare except:` — **가장 위험한 형태**가 **안 잡히고 있었다.** `_is_broad` 가 `"(bare)"` 를
`strip("()")` 로 벗겨 놓고 원래 문자열과 비교했다. `test_sigma_audit` 의 *"bare except 는 잡는다"*
가 실패로 드러냈다.

[주의] 이것이 이 세션 **열 번째** 같은 부류의 실수이고, **처음으로 테스트가 먼저 잡았다.**

### 25.5 분류 — 원전처럼 «전부 고치지 않았다»

원전은 6건 중 **4건을 「정상 fallback 이라 유지」**로 판정하고 조치를 *"docstring 으로 의도 명시"*
로 뒀다. 우리도 그렇게 했다 — [중요] **스캐너는 판정을 내리지 않는다.** *"의도가 적혀 있지 않다"* 를
찾아 줄 뿐이고, 적혀 있으면 그것은 **설계**다.

16건 중 위험 순으로 둘을 처리했다:

| 자리 | 판정 | 조치 |
|---|---|---|
| `task_queue/reclaim.py` ×2 | [중요] **주기 루프에서 pass/continue** — 타임스탬프가 영구히 깨지면 그 task 는 **영원히 회수되지 않는다** | `except Exception` → **`ValueError`** (`fromisoformat` 이 내는 것). **의도를 구조로** 만들었다 — 주석보다 좁은 예외가 낫다 |
| `ontology/stale.py:104` | **유지 + 의도 명시** | 근거 둘을 적었다: ① 대상 `class_ontology` 는 **일부러 비어 있다**(소 3.1.2) — 정상 경로에서도 `{}` 다 ② stale 판정은 **못 읽으면 stale 로 기울어야** 안전하다(반대로 기울면 낡은 트윈이 조용히 남는다) |

[주의] 남은 14건은 **분류만 하고 두었다** — 원전의 절제(*"self-heal 되는 걸 카나리로 만들면
노이즈"*)를 따른다. 목록은 `python -m master.sigma_audit` 이 언제든 다시 낸다.

### 25.6 [주의] 내 분류를 정정했다

`#176`(σ 감사 **1회 실행**)을 §7.3 에서 **개선**으로 분류해 대 1~3 뒤로 미뤄 뒀는데 **과했다.**
감사를 돌리면 **놓친 이식이 나온다** — 인용 census 가 그랬듯 **포팅의 도구**이지 그 위에 얹는
개선이 아니다. 그래서 `#175`(이식)와 함께 돌렸다.

## §26. 세션 마감 (2026-08-14 02시)

**레드마인 마일스톤 4: 75/22 완료** · 전체 테스트 **2339/2339**(파일 50개) · 3자 클론 동기 `80bcba1`.

### 26.1 닫힌 것 · 남긴 것

    [완료] 중 1.1  원전 설계 문서 정독 3/3      [완료] 중 1.4  문서·라벨 정정 4/4
    [완료] 중 3.1  ①추정 이식분 대조 3/3        [완료] 중 4.2  σ 감사 도입 2/2
    [진행] 중 3.5  운영 가드 — 6 완료 · [중요] 재범위 3(닫지 않음)
    [진행] 중 1.2  2-tier 복원 — 3 완료 · 1 판단 대기 · 1 갈림길

    신설 모듈  work/coordinator · work/selftest · work/conventions · events/gate ·
              sqlite_util · sigma_audit  (+ bm25.diagnose · consumer.append_canary)
    신설 유닛  ax-indexer.timer (+ ax-indexer.service 에 SuccessExitStatus=4) — pkexec 로 반영
    테스트     8종 신설

### 26.2 [중요] 판단을 넘긴 채 남아 있는 것

    #123 · #127 · #128   **갈림길 하나로 수렴** — 작업장에 폴링 주체(claimer)를 둘 것인가.
                         큐 인프라는 이미 다 있고 실증도 통과했다(e2e 26/26). 없는 것은 폴링 주체
                         하나이고, 만들면 #165(worker/safety 가드)도 같이 필요해진다
    #125                 ephemeral 을 **언제** 지울지 (원전=work 종료 시 / 우리=사람이)
    #146                 `/debate` 를 되살릴지 — [중요] 원전 C.5 가 「전제 미충족」으로 **강등**해 뒀다
    #185                 매니페스트를 git-carried 로 되돌릴지 (지금은 scp)
    재범위 3건           `#180`(이식이 퇴행) · `#181`·`#165`(자리가 다르다·없다) — **닫지 않았다**

### 26.3 [중요] 이 세션이 스스로에 대해 배운 것

내가 낸 결함이 **10건**이고 **전부 조용히 틀리는 부류**였다. 그중 **셋은 측정 도구 자신**이 틀린
것이다 — 테스트 합계(세션 내내, 근원은 `CLAUDE.md` 의 명령) · σ.1 검사식 · σ.2 의 `bare except`
판정. [주의] **여덟은 실측·실구동이 잡았고, 마지막 하나만 테스트가 먼저 잡았다.**

그리고 같은 형태가 네 번 반복됐다 — [중요] **사람이 보는 표시를 실체로 착각**했다:
1세그먼트 경로로 라우트를 재고(§7.5) · `for-each-ref` 패턴이 `/` 를 못 넘는 것을 모르고 정리했다
하고(§15.2) · 화면에 34자로 잘린 `work_id` 를 타이핑했다(§16.2) · 마지막 줄만 보는 명령으로 테스트를
셌다(§18).

### 26.4 [중요] README 둘 — 문서 최신화에서 내가 또 빠뜨린 것

사용자 지적(*"ReadMe 문서는?"*)으로 잡았다. **문서 최신화를 했다고 보고한 직후였고, 고친 것은
`PLAN.md`·마일스톤·머신 가이드·리포트 색인 넷뿐이었다.** [주의] 리포트 12 §11 에 **같은 사고가 이미
기록돼 있다** — *"`README.md` 와 `master/README.md` 가 오늘 만든 것을 통째로 모르고 있었다"*.
[중요] **재발한 이유는 「문서」의 목록을 매번 머리로 떠올렸기 때문이다** — 앞서 고친 넷은 이 세션에서
내가 만졌던 파일이고, README 는 안 만졌으니 떠오르지 않았다.

측정된 낡음 **넷**:

    ① [중요] 흐름도의 원리가 틀렸다   README.md — "쓰는 주체는 하나다(통합자 .2)"
                                  리포트 12 §11 에서 "워커가 커밋한다"를 이것으로 고쳤는데,
                                  §2 가 그 고친 값을 다시 뒤집었다. **정정이 정정을 부른다**
    ② 신규 6모듈을 통째로 모른다   coordinator · selftest · conventions · gate · sqlite_util
                                  · sigma_audit — 양쪽 README 에서 인용 **0회**
    ③ [중요] 틀린 세는 법이 남아 있었다 README.md 의 `| tail -1` — §18 에서 CLAUDE.md 는 고쳤는데
                                  **같은 명령의 두 번째 사본을 못 봤다**
    ④ [중요] 표 구분선이 빠져 있었다    master/README.md:131 — `| Component | Where |` 뒤에 `|---|`
                                  가 없어 **영문 20행이 위 4열 표의 행으로** 렌더링됐다

**④ 는 세션 내내 아무도 못 본 것이다** — 마크다운은 오류를 내지 않고 **조용히 다르게 그린다.**
[중요] σ.2 가 코드에서 찾는 것과 정확히 같은 형태(**실패가 실패로 보이지 않는다**)이고, 문서에는
그 스캐너가 없다. 그래서 검사식을 두 개 만들어 돌렸다: **구분선 없는 표 헤더** · **헤더와 열수가
다른 행**. [주의] **후자는 첫 실행에서 16건을 냈고 전부 오탐이었다** — 인라인 코드의
이스케이프된 `\|`(`plan\|run`)를 열 구분자로 셌다. **§25 의 「검사식도 감사 대상이다」가 또 맞았다.**

고친 것: 흐름도에 **2단 브랜치 그림 + 「리눅스가 강제하는 변경은 하나」** 를 넣고 지금 도는 모양은
*"[주의] M3 가 만든 모양"* 으로 표시([주의] `coordinator.py` 는 **미배선**이라 지금은 그 그림이 여전히
맞다 — 배선된 것처럼 적으면 그게 더 나쁘다) · 구조 트리에 6모듈 · 테스트 표에 계약 7행 ·
세는 법은 **CLAUDE.md 한 벌만 남기고** README 는 실패만 보는 명령으로 축약([중요] 두 벌이라 어긋났다) ·
구분선 복구 + *"기준일을 적지 않는다"*(「2026-08-09 기준」이 닷새 낡음의 원인이었다) ·
「이식 대상」 표에 *"1·2·4 는 끝났다"* 와 **κ.8 이 「안 옮긴다」를 이미 판단해 뒀다**는 인용.

검증: 표 열수 어긋남 **0** · 구분선 없는 표 **0** · 링크 8/8 · README 가 주장한 파일 13/13 실재.

### 26.5 다음 세션이 먼저 읽을 것

    ① docs/milestones/4-origin-reconciliation.md   — [중요] 「최우선 규칙」과 「함정 목록」
    ② 이 리포트의 §2 · §11.3 · §24                — 토폴로지 · Flow X/Y · 대조하는 법
    ③ python -m master.sigma_audit                — 14건이 분류 대기다

[중요] **다음 작업은 사용자가 정한다.** 후보는 `#154`(되먹임 7종) · `#172`(AGENTS.md 나머지 4조) ·
`#187`~`#191`(대조가 찾은 미이식 5건) · `#138`(작업유형 템플릿 — 단 층3 구멍의 절반만 닫는다).

### [중요] 이 세션이 남기는 한 줄

**제약을 지키려고 요구를 희생하지 않는 것만으로는 부족했다 — 만들기 전에 그 자리에 무엇이
있는지 재는 절차가 없으면 같은 일이 반복된다.** census 는 그 절차의 초안이고, 스스로도 두 번
틀렸다(§1 · §7.1). 그 한계까지 같이 남긴다.
