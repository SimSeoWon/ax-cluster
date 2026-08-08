> Part of the AX Cluster plan. Index: [`../../PLAN.md`](../../PLAN.md).

# 마일스톤 2 — 디지털 트윈 복원 (2026-08-08 착수)

> 🔴 **안 된 것과 사슬만 담는다.** 완료분은 [`1-infrastructure.md`](1-infrastructure.md) 에
> 있고 **평소 읽지 않는다.** 열린 마일스톤 하나만 읽는다 — 안 그러면 매 세션 비용이 된다.
> **이 문서를 150줄 안에 유지할 것.**

## 목표 (사용자 확정 2026-08-08)

1. **온톨로지 문서를 자동으로 작성한다** — 커밋마다 컨텍스트 문서를 쓰고, 연관 클래스 간
   관계를 그래프로 쓰고, 검색을 위해 BM25 를 얹고, 최종적으로 **사용자의 수동 명령과
   대화형으로 휴리스틱 정보가 포함된** 온톨로지 문서를 만든다
2. **그 트윈 데이터를 코드 작성 에이전트에게** 관련된 것만 추출해 전달한다

🔴 **목표 ①의 마지막 절이 설계의 핵심이다.** 온톨로지는 전자동이 아니다 —
`자동 승급 2026-06-01 영구 비활성`(`[[project_auto_promotion_disabled]]`), 미배정 클래스도
*"노출만, 자동 편입 0"*, 사용자 지시 *"도메인 클래스 추가는 지금처럼 명시적으로만"*.
휴리스틱은 그 자리를 메우는 **LLM 0 추천기**다(레이어 4-시그널 추정 · 인접 SubDir 후보).

## 산출물 — 4종이다 (5종이 아니다)

| 산출물 | 생산자 | LLM |
|---|---|---|
| ① 컨텍스트 문서 (**태그·related_classes·category 포함**) | `watcher/context.py` | 🔴 예 |
| ② 관계 그래프 — 상속(tree-sitter) + `#include` | `class_graph_parse.py` · `dependency.py` | 아니오 |
| ③ 온톨로지 문서 (도메인 yaml) | `ontology_synthesizer` 계열 + **사람** | 🔴 예 |
| ④ 시소러스 (`aliases`) | 🔴 **사람이 등록** + `build_thesaurus_index` | 아니오 |

**태그는 별도 산출물이 아니다** — `context.py:48`·`318` 의 프롬프트가 `tags: [...]` 를 ①의
프론트매터로 쓰게 한다. ①과 한 몸이다.

## 파이프라인 (`watch.py` 커밋 처리 순서, 실측)

```
커밋 감지
 ├ process_commit                  컨텍스트 MD + source_commit 스탬프 + 벡터/BM25 upsert  🔴 LLM
 ├ update_dependency_graph         #include 의존 그래프                                    LLM 0
 ├ class_graph.update_incremental  상속 그래프 (tree-sitter)                               LLM 0
 ├ sync_object_paths               object yaml `file:` 실측 동기화                          LLM 0
 ├ [헤더 변경 시] sync_declared_contracts   @ms-contract regex                             LLM 0
 └ 시간 게이트(평일 10시 이후 첫 폴링) → ontology_refresh.run   도메인 재합성              🔴 LLM
```

🔴 **컨텍스트 MD 가 온톨로지 재합성의 신호원이다.** Phase η.8 이 dirty 플래그를 없애고,
MD 의 `source_commit` 갱신 → `compute_stale_domains` 가 "오브젝트 저장값 ≠ 문서값" 으로
자연 stale 판정하게 바꿨다. **컨텍스트 문서가 없으면 온톨로지는 자기가 낡은 줄 모른다.**

🔴 **LLM 을 쓰는 것만 시간 게이트 뒤에 있다.** *"옛 매 폴링 인프라 폐기 — event-based race
본질 해소"*. 결정적 작업은 커밋 즉시.

## 🔴 이 마일스톤의 범위 = **데이터 생성** (사용자 확정 2026-08-08)

`/distribute`(12단계)·`/review-work`(7단계)도 큰 작업 하나지만 **이 마일스톤이 아니다.**
둘은 트윈을 **먹는 소비자**다 — `/distribute` 백엔드 `cluster_context.py` 가 하는 일이
*"매니페스트 수집 RAG+온톨로지"* 다. 생성부가 스냅샷 고정인 채로 세우면 **고정된 8월 8일치
근거로 코드를 짜게 된다.** 그래서 다음 마일스톤 후보로 이름만 남기고, 상세는 여기 쓰지 않는다
(읽는 비용이 매 세션 붙는다). 착수 전에 `distributed-workers.md`(425줄)를 읽는다.

## 선행 조건 (태스크가 아니다 — 없으면 A1 이 아예 안 돈다)

- 🔴 **tree-sitter 미설치** — 마스터에 `tree_sitter`·`tree_sitter_cpp` 둘 다 없다(실측
  2026-08-08). 원본은 `class_graph_parse.py` 에서 지연 import 하고 실패 시 조용히 죽는다.
  A1 착수 시 **먼저 설치하고 UE 매크로 전처리가 리눅스에서 같은 결과를 내는지 확인**할 것

## 서브 태스크 16개 — 1 / 16

**A. 결정적 (LLM 0) · 커밋 즉시**

| | | 우리 |
|---|---|---|
| A1 | 상속 그래프 `class_graph.db` (tree-sitter) | ❌ |
| A2 | 의존 그래프 `dependency_graph.db` | ❌ |
| A3 | object yaml `file:` path sync | ❌ |
| A4 | `@ms-contract` declared invariant | ❌ |
| A5 | 벡터/BM25 색인 (컨텍스트 채널) | ✅ **961 / 961** live=`a` |

**B. LLM 자동**

| | | 우리 |
|---|---|---|
| B1 | **컨텍스트 MD 합성** — 🔴 A5·B2 의 선행 | ❌ 0 / 1,036 |
| B2 | 온톨로지 재합성 (`ontology_refresh.run`) | ❌ 0 / 7 도메인 |

**C. 사람 (수동·대화형) + 휴리스틱**

| | | 우리 |
|---|---|---|
| C1 | 도메인 생성(주제 기반) · 대화형 편집(`/chat`) | ❌ |
| C2 | 레이어 추정 휴리스틱 (L1/L2/L3, 4 시그널) | ❌ |
| C3 | 미배정 클래스 노출 (인접 SubDir 추천) | ❌ |
| C4 | 시소러스 `aliases` 등록 + **재합성 이월** | ❌ 0 / 247 |
| C5 | `description.md` 검수 락 (`verified_by_user`) | ❌ |

**D. 소비 — 목표 ②**

| | | 우리 |
|---|---|---|
| D1 | `sync_domain_index` (도메인 색인 + 시소러스 캐시) | ❌ 🔴 온톨로지 검색 0건의 직접 원인 |
| D2 | 시소러스 쿼리 확장 (`_expand_query_with_thesaurus`) | ❌ |
| D3 | **도메인 규범 grounding**(`attach_norms`) — 목표 ②의 종점 | ❌ `manifest.py:154` 가 `"_미구현_"` |
| D4 | drift 감사 | ❌ |

**사슬**: `B1 → A5`(색인 트리거) · `B1 → B2`(stale 신호원) · `A1 → B2`(합성이 그래프를 읽는다) ·
`B2 → D1 → D2/D3`. 상류가 **A1·B1**, 종점이 **D3**.

🔴 **A5 조차 스스로 돌지 못한다.** 트리거가 컨텍스트 digest 변화인데 B1 이 없어 digest 가
안 바뀐다 — 색인기 스킵 사유가 `"변화 없음 — 합성기 미이식"`. 색인은 **2026-08-08 12:56
스냅샷 고정**이다.

## 마일스톤 1 이 만든 것은 이 16개가 아니다

`master/` 62 파일은 대부분 **작업 루프**다 — `task_queue`·`broker`·`work/`·`layer2/3_verify`·
`verdict`·`events`·`projects`·`provision`·`auth`. 파이프는 이었고, **파이프에 흐르는 정보를
만드는 능력이 없다.** 코드를 새로 짜도 트윈에 안 들어가고, 그 벌어짐이 **에러 없이 조용히**
진행된다.

## 알아낸 함정 (반복하면 손해)

- **시소러스 재합성 소실** — `synthesize_domain` 이 objects 를 매 합성마다 DB 에서 새로
  만든다. `aliases` 를 명시 이월하지 않으면 다음 합성에 사라진다 (원본이 겪고 고침)
- **시소러스는 substring 매칭** — 토큰 매칭 아님. BM25 토크나이저
  (`[A-Za-z0-9_]+|[가-힣]+`)가 조사를 안 떼서 "몬스터를" 이 한 토큰이다
- **`search_domain_norms` 노이즈 3중 차단** — ⑴ BM25 0건이면 빈 결과 ⑵ 벡터 단독은
  `similarity ≥ 0.2` ⑶ `top_k=2`. 빼먹으면 결과가 늘어 겉보기엔 좋아지고 품질은 나빠진다
- **`sync_domain_index` 는 자동 감지가 없다** — 임포트 직후엔 온톨로지가 소스와 일치해
  stale 경로가 영영 안 걸린다. 원본 `import_state` 독스트링이 경고해 뒀다
- **줄 수는 작업량이 아니다** — `class_graph.db` 1,341줄이 `data-schema.md` 기준
  *"파일 삭제 → 재기동 시 풀 스캔"* 이다

## 진행 규칙 (마일스톤 1 의 실패에서)

1. **"완료" 는 영역 전체에만.** 부분이면 분모를 같이 적는다 (`1 / 16`)
2. **조사 없이 라벨 붙이지 않는다** — "2단계"·"나중 문제" 로 미루기 전에 열어본다
3. **소스보다 문서를 먼저 읽는다** — 인수인계 문서·독스트링에 답이 있었다
4. **줄 수를 작업량으로 쓰지 않는다**
5. 🔴 **순서는 사용자가 정한다** — 사슬은 적되 임의로 하나 골라 파고들지 않는다
6. **이 문서를 150줄 안에 유지한다** — 완료된 줄은 즉시 지워
   [`1-infrastructure.md`](1-infrastructure.md) 로 보낸다. 여기 쌓지 않는다
7. **이 문서의 머리(목표·산출물)는 바꾸지 않는다** — 바뀌면 마일스톤 자체가 바뀐 것이다

## 미독 인수인계 문서

`data-schema.md`(206) ✅ · `ontology.md`(94)·`rag-system.md`(187) 부분.
**미독: `README.md` 842 · `watcher-internals.md` 543 · `runbook.md` 280 · `extending.md` 251
(+ 범위 밖 `distributed-workers.md` 425).**
위 16개는 `watch.py` 파이프라인 실측으로 세웠으므로 유효하다. 다만 **B1·B2 착수 전
`watcher-internals.md`(컨텍스트 MD 생성·LLM 폴백·서킷브레이커) 를 읽는다** — 생성부의
내부 동작이 그 문서에 있다.
