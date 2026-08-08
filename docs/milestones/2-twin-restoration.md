> Part of the AX Cluster plan. Index: [`../../PLAN.md`](../../PLAN.md).

# 마일스톤 2 — 디지털 트윈 복원 (2026-08-08 착수)

> 🔴 **안 된 것과 사슬만 담는다.** 완료분은 [`1-infrastructure.md`](1-infrastructure.md) 로
> 보낸다 — 열린 마일스톤 하나만 읽는다. **이 문서를 150줄 안에 유지할 것.**

## 목표 (사용자 확정 2026-08-08) — **머리는 바꾸지 않는다**

1. **온톨로지 문서를 자동으로 작성한다** — 커밋마다 컨텍스트 문서를 쓰고, 연관 클래스 간
   관계를 그래프로 쓰고, 검색을 위해 BM25 를 얹고, 최종적으로 **사용자의 수동 명령과
   대화형으로 휴리스틱 정보가 포함된** 온톨로지 문서를 만든다
2. **그 트윈 데이터를 코드 작성 에이전트에게** 관련된 것만 추출해 전달한다

🔴 목표 ①의 마지막 절이 핵심이다. 온톨로지는 전자동이 **아니다** — `자동 승급 2026-06-01
영구 비활성`, 미배정 클래스도 *"노출만, 자동 편입 0"*, 지시가 *"도메인 클래스 추가는
지금처럼 명시적으로만"*. 휴리스틱은 그 자리를 메우는 **LLM 0 추천기**다.

## 산출물 — 4종 (5종이 아니다)

| | 산출물 | 생산자 | LLM |
|---|---|---|---|
| ① | 컨텍스트 문서 (**태그·related_classes·category 포함**) | `watcher/context.py` | 🔴 예 |
| ② | 관계 그래프 — 상속(tree-sitter) + `#include` | `class_graph_parse` · `dependency` | 아니오 |
| ③ | 온톨로지 문서 (도메인 yaml) | `ontology_synthesizer` + **사람** | 🔴 예 |
| ④ | 시소러스 (`aliases`) | 🔴 **사람이 등록** + `build_thesaurus_index` | 아니오 |

**태그는 별도 산출물이 아니다** — `context.py:48`·`318` 프롬프트가 ①의 프론트매터로 쓰게 한다.

## 파이프라인 (`watch.py` 커밋 처리 순서, 실측)

```
커밋 → process_commit  컨텍스트 MD + source_commit 스탬프 + 색인 upsert   🔴 LLM
     → update_dependency_graph / class_graph.update_incremental          LLM 0
     → sync_object_paths / [헤더변경시] sync_declared_contracts           LLM 0
     → 시간 게이트(평일 10시 이후 첫 폴링) → ontology_refresh.run         🔴 LLM
```

🔴 **컨텍스트 MD 가 온톨로지 재합성의 신호원이다.** Phase η.8 이 dirty 플래그를 없애고, MD 의
`source_commit` 갱신 → `compute_stale_domains` 가 "저장값 ≠ 문서값" 으로 stale 판정.
**컨텍스트 문서가 없으면 온톨로지는 자기가 낡은 줄 모른다.** 그리고 **LLM 을 쓰는 것만 게이트
뒤**다 — *"event-based race 본질 해소"*.

🔴 **이번 마일스톤의 메인은 대 1(데이터를 만드는 것).** 대 2 는 목표 ②라 같은 마일스톤이지만
생성 뒤에 붙고, 그보다 위 계층은 아래 「🕓 예정」에만 남긴다.

## 선행 조건 (태스크가 아니다 — 없으면 1.1 이 안 돈다)

🔴 **tree-sitter 미설치** — `tree_sitter`·`tree_sitter_cpp` 둘 다 없다(실측). 원본은 지연
import 하고 실패 시 **조용히 죽는다.** 설치 후 **UE 매크로 전처리가 리눅스에서 같은 결과를
내는지** 확인할 것. 안 하면 "돌았는데 결과 0" 이 난다.

---

## 작업 분류 — 대 2 · 중 8 · 소 32 → **완료 1 / 32**

### 대 1. 트윈 데이터 생성 (목표 ①) — 0 / 22 · 🔴 **이번 마일스톤 메인**

**중 1.1 관계 그래프** · LLM 0 · 커밋 즉시 — 0/5

| 소 | | 근거 |
|---|---|---|
| 1.1.1 | C++ 파서 — UE 매크로 전처리·클래스/메서드 추출 | `class_graph_parse.py` |
| 1.1.2 | DB 코어 — 스키마·`_db_lock` 단일소유·`ensure_schema` | `class_graph_db.py` |
| 1.1.3 | `build_full` / `update_incremental` / `is_bootstrapped` | `class_graph.py` |
| 1.1.4 | `methods` 테이블 — 메서드 소유권(온톨로지 **오탐 교차검증**) | `data-schema.md` |
| 1.1.5 | `#include` 의존 그래프 build/증분 | `dependency.py` |

**중 1.2 컨텍스트 문서** · 🔴 LLM — 1/5

| 소 | | 상태 |
|---|---|---|
| 1.2.1 | 변경 파일 → 프롬프트 조립 · 생성 | ❌ |
| 1.2.2 | MD 정제·스탬핑 (`content_hash`·`source_commit`) + 워터마크 read | ❌ 🔴 stale 신호원 |
| 1.2.3 | 프론트매터 — tags·related_classes·category | ❌ |
| 1.2.4 | LLM 라우팅·폴백·서킷브레이커·토큰추적 | ❌ |
| 1.2.5 | 벡터/BM25 색인 (rebuild·upsert·RRF·A/B 세대) | ✅ **961 / 961** |

**중 1.3 온톨로지 문서** · 수동·대화형 + 휴리스틱 — 0/9

| 소 | | 성격 |
|---|---|---|
| 1.3.1 | 도메인 생성 — 주제 기반 **수동** (`POST /domains`) | 사람 |
| 1.3.2 | 대화형 편집 (`/chat`) · draft→active (`/activate`) | 사람+LLM |
| 1.3.3 | 재합성 — objects/actions/invariants + **locked-item 병합** | 🔴 LLM |
| 1.3.4 | YAML writer / 수제 reader (PyYAML 의존 0) | LLM 0 |
| 1.3.5 | 레이어 추정 휴리스틱 — L1/L2/L3 **4 시그널** | LLM 0 |
| 1.3.6 | 미배정 클래스 노출 — 인접 SubDir 후보만 | LLM 0 |
| 1.3.7 | `description.md` + `verified_by_user` 검수 락 | 사람 |
| 1.3.8 | stale 판정 — 리비전 워터마크·MD 해시 비교 | LLM 0 |
| 1.3.9 | `path_sync` · `@ms-contract` declared invariant | LLM 0 |

**중 1.4 시소러스** — 0/3

| 소 | | 함정 |
|---|---|---|
| 1.4.1 | `aliases` 필드 + 등록 경로 (`<구절>[ClassName]`) | 사람이 등록 |
| 1.4.2 | **재합성 이월** | 🔴 안 하면 다음 합성에 사라진다 |
| 1.4.3 | 인덱스 빌더 + mtime fingerprint | — |

### 대 2. 트윈 소비 배선 (목표 ②) — 0 / 10 · 생성 뒤에 붙는다

**중 2.1 도메인 색인** — 0/3 · **중 2.2 검색 확장** — 0/2

| 소 | | |
|---|---|---|
| 2.1.1 | `sync_domain_index` → `bm25_domains.db` + `ontology_domains` | 🔴 검색 0건의 직접 원인 |
| 2.1.2 | `search_domain_norms` **노이즈 3중 차단** | 빼면 조용히 나빠진다 |
| 2.1.3 | fingerprint 기반 YAML↔색인 동기화 | — |
| 2.2.1 | `_expand_query_with_thesaurus` — substring 매칭 | 조사 미분리 대응 |
| 2.2.2 | 질의 → 도메인 자동 추론 (`class_ontology` 읽기) | 1.1 선행 |

**중 2.3 코드 작성 grounding** — 0/2 · **중 2.4 건강성·가시성** — 0/3

| 소 | | |
|---|---|---|
| 2.3.1 | `attach_norms` — 관련 도메인 규범 번들 | 🔴 **목표 ②의 종점** |
| 2.3.2 | 매니페스트 규범 섹션 | `manifest.py:154` 가 `"_미구현_"` |
| 2.4.1 | drift 감사 | — |
| 2.4.2 | 도메인 뷰어(웹) — 읽기 전용이면 yaml 파싱만으로 가능 | — |
| 2.4.3 | 상태 익스포트/임포트 | 다음 zip 수령 전 |

**사슬**: `1.2 → 1.2.5`(색인 트리거) · `1.2 → 1.3`(stale 신호원) · `1.1 → 1.3.3`(합성이 그래프를
읽는다) · `1.3 → 2.1 → 2.2/2.3`. 상류 **1.1·1.2**, 종점 **2.3.1**.

🔴 **1.2.5 조차 스스로 돌지 못한다** — 트리거가 컨텍스트 digest 변화인데 1.2 가 없어 안 바뀐다.
색인기 스킵 사유가 `"변화 없음 — 합성기 미이식"`. **2026-08-08 12:56 스냅샷 고정.**

---

## 🕓 예정 — 상위 레이어 (이 마일스톤 밖, 폐기 아님)

트윈을 **먹는 쪽**이다. 백엔드 `cluster_context.py` 가 *"매니페스트 수집 RAG+온톨로지"* 라,
생성부가 스냅샷 고정인 채 세우면 **고정된 8월 8일치 근거로 코드를 짜게 된다.** 이름·규모만
남기고 **상세는 쓰지 않는다** — 읽는 비용이 매 세션 붙는다.

| | 규모 | 착수 전 필독 |
|---|---|---|
| 🕓 `/distribute` — 계층 플랜 · **골조 생성** · 템플릿 매칭 · 코드베이스 분석 | 12단계 | `distributed-workers.md` 425줄 |
| 🕓 `/review-work` — 시뮬레이션 머지+빌드 · 통합 빌드 · finalize · reject · TDD 드라이런 | 7단계 | ↑ 같은 문서 |
| 🕓 작업 유형 템플릿 (`list`/`get_task_template`) | — | `ontology.md` Phase ζ |
| 🕓 `/cluster-selftest` — 이게 통과해야 "돈다" 고 말할 수 있다 | — | — |
| 🕓 `/tdd-dryrun` · `/debate` | — | — |
| 🕓 팀 기능 — 감사 · redmine · log/crash analyzer · code_recipes · commandlet_runner · 위키 | — | §5.2-D 판단 대상 |

🔴 **골조 생성 부재만은 기억할 것** — 우리 `register_work` 는 골조를 **인자로 받는다**(사람이
써 주는 전제). 원본은 `generate_skeletons` 가 만든다. §4.5 가 "골조 → 동결 → 병렬 본문" 으로
확정했는데 **첫 단계가 비어 있다.**

## 진행 규칙 (마일스톤 1 의 실패에서)

1. **"완료" 는 영역 전체에만.** 부분이면 분모를 같이 적는다 (`1 / 32`)
2. **조사 없이 라벨 붙이지 않는다** — 미루기 전에 열어본다
3. **소스보다 문서를 먼저 읽는다** — 인수인계 문서·독스트링에 답이 있었다
4. **줄 수를 작업량으로 쓰지 않는다** — `class_graph` 1,341줄이 "삭제 후 재스캔" 이었다
5. 🔴 **순서는 사용자가 정한다** — 사슬만 적고 임의로 고르지 않는다
6. **완료된 소분류는 즉시 지워** 마일스톤 1 로 보낸다. 여기 쌓지 않는다
7. **머리(목표·산출물)는 바꾸지 않는다** — 바뀌면 마일스톤 자체가 바뀐 것이다

## 미독 인수인계 문서

`data-schema.md`(206) ✅ · `ontology.md`(94)·`rag-system.md`(187) 부분. **미독: `README.md` 842 ·
`watcher-internals.md` 543 · `runbook.md` 280 · `extending.md` 251** (+ 예정분 425).
위 분류는 `watch.py` 실측이라 유효하다. 🔴 **중 1.2·1.3 착수 전 `watcher-internals.md`** —
컨텍스트 MD 생성·LLM 폴백·서킷브레이커의 내부 동작이 거기 있다.
