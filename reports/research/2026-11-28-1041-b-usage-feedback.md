# #1041-B — 실사용 이력(검색 로그 + Git Co-change) 기반 온톨로지 후보 역환류 분석 보고서

> 작성일: 2026-11-28 · 일감: Redmine `#1044` (상위 `#1041`, `아이디어 — 추후 검토 수집`)  
> 대조 스킬: `ax-ontology` (`master/client/skills/ax-ontology/SKILL.md`), `distribute` (`master/skills/distribute/SKILL.md`)  
> 대조 코드: `master/context_search/search_log_analyzer.py`, `master/ontology/log_candidates.py`, `master/ontology/collect.py`, `master/ontology/unassigned.py`  
> NVIDIA 원전: `auto_ontology/semantic/sql_attribute_suggester.py`

---

## 1. 개요

NVIDIA `auto-ontology`는 정적 DB 스키마만 보지 않고 과거 SQL 쿼리 이력을 `sqlglot`으로 파싱해 자주 쓰이는 조건·집계식을 `SqlAttribute` 후보로 온톨로지에 역환류한다.

AX 클러스터에는 이미 **검색 로그 분석기(`search_log_analyzer.py`)**와 **제안 전용 리포트 패턴(`log_candidates.py`)**, **관계 수집 제안(`collect.py`)**이 갖춰져 있다. 여기에 **① `search_log`의 반복 0건/저점수 질의 → `aliases`/`tags` 후보**와 **② Git 커밋 이력의 공동 변경 클래스 쌍(co-change) → `collect.propose` 도메인 멤버/액션 후보**를 **제안 전용(자동 편입 없음)**으로 연결하는 방안을 검토한다.

---

## 2. 실제 코드쪽 내용

### 2.1 NVIDIA 원전 구현 및 주의할 실제 버그
- `auto_ontology/semantic/sql_attribute_suggester.py`:
  - `fetch_terms_with_sqls()` → `_extract_expressions(sql_text)`(`sqlglot` AST) → 상위 10개 식을 LLM에 전달해 `SqlAttribute` 제안.
  - **실제 코드에서 확인된 결함**: `_usage_score()`(L69-118)가 키 불일치 버그(`count_monthly_YYYY_MM` vs `count_{month}_{year}`) 때문에 현재 `return 0.0`으로 고정돼 있어 빈도 순위가 작동하지 않는다. AX 구현 시에는 반드시 **실제 카운트 기반 정렬 + 최소 표본 가드**를 처음부터 붙여야 한다.

### 2.2 AX 클러스터 기존 자산
- **`master/context_search/search_log_analyzer.py`**:
  - 이미 stdlib 전용·LLM 0으로 `search_log.jsonl`을 읽어 **4번 항목 "시소러스 후보(반복되는 0건 한국어 검색어)"**를 집계하고 있으며, `MIN_TOTAL_SAMPLE = 30` 표본 가드를 갖고 있다.
  - 다만 현재는 `<프로젝트 데이터>/analysis/`에 분석 리포트만 남길 뿐, `ax-ontology` 대화 흐름(`resolve_terms` / `add_object_alias`)과 직접 이어지지 않는다.
- **`master/ontology/log_candidates.py`**:
  - active 도메인의 invariant `evidence`를 파싱해 `<트윈>/ontology/_log_tagging_candidates.md`를 생성하는 **제안 전용·자동 등록 금지** 패턴의 정본이다. 이미 등록된 항목을 `[확정 등록됨]`으로 표기해 중복 제안을 걸러낸다.
- **`master/ontology/collect.py`**:
  - 현재 3가지 정적 근거만 수집: `조상 4단계` · `자식 1홉` · `#include 이웃`(`INCLUDE_FANOUT=4`, `INCLUDE_CANDIDATES=25`).
  - **Git co-change(최근 N개 커밋에서 같은 커밋에 함께 바뀐 파일의 클래스 쌍)**를 4번째 근거(`why="git co-change"`)로 추가할 수 있는 구조(`Candidate(name, why, via, file)`)가 이미 깔끔하게 열려 있다.

---

## 3. 주의사항

1. **자동 편입·자동 승급 절대 금지 (`ax-ontology` §0, `collect.py` L18)**:
   - 2026-06-01 / 2026-08-09 사용자 확정으로 자동 승급은 영구 비활성이다. 역환류 결과는 **반드시 제안 리포트(`_usage_candidates.md`) 또는 `collect.propose` 후보 목록**으로만 노출하고, 등록은 사람이 확정한다.
2. **대량 리팩터링·포맷팅 커밋 노이즈 필터링 필수**:
   - Git co-change는 한 커밋에 파일 50개가 동시에 바뀐 일괄 포맷팅/머지 커밋을 그대로 넣으면 모든 클래스가 서로 연결되는 폭발이 일어난다. **커밋당 변경 파일 수 상한(예: ≤10개) + 최소 동시 출현 횟수(예: ≥3회) + 최근 윈도우(예: 200커밋)** 가드가 필수다.
3. **표본 부족 시 「판단 보류」 유지**:
   - `search_log_analyzer.py`의 `MIN_TOTAL_SAMPLE = 30` 원칙처럼, 로그·커밋 표본이 얇을 때는 후보를 억지로 짜내지 말고 보류해야 한다.
4. **bare 저장소 읽기 경로 (`drift.py` 패턴 준수)**:
   - `master/ontology/drift.py`의 `_changed_between`처럼 `gitea_group.wrap_shell()`을 통해 bare 저장소를 읽기 전용으로 조회해야 서비스 컨텍스트(`NoNewPrivileges=true`)에서 조용히 빈 목록을 반환하는 함정(`#336`)을 피할 수 있다.

---

## 4. 좋은점

- **정적 그래프의 사각지대 보완**: `#include`나 상속이 없는 이벤트 버스·델리게이트·리플렉션·데이터 테이블 기반 결합(UE5에서 매우 흔함)도 **실제 함께 수정되는 Git 이력**으로는 포착된다.
- **한글 검색 공백의 실질적 해소**: `ax-ontology` §1에서 지적된 한글 별칭 부족 문제를, 사람이 매번 떠올리는 대신 `search_log`에서 실제로 실패한 한국어 질의어 상위 후보를 주기적으로 올려 줘 자연스럽게 메울 수 있다.
- **LLM 비용 0**: stdlib + `git log --name-only` + `search_log.jsonl` 1패스만으로 동작해 로컬 추론 노드에 부담이 없다.

---

## 5. 나쁜점 및 리스크

- **노이즈 후보 증가로 인한 검수 피로**: `collect.py`가 `#include` 1홉에서 후보 184개 폭발을 겪었듯, co-change 임계값이 느슨하면 공용 유틸리티·설정 파일이 모든 도메인 후보에 반복 등장한다.
- **이미 `mark_not_a_class` 처리된 용어 재제안 위험**: `search_log` 후보 제안 시 기존 `not_a_class` 목록 및 이미 등록된 `aliases`와 반드시 차집합 처리해야 같은 질문을 반복하지 않는다.
- **초기 프로젝트 효용 제한**: 커밋 이력이나 검색 로그가 적은 신규 온보딩 프로젝트에서는 당장 나올 후보가 거의 없다.

---

## 6. 실 작업 착수 시 권장 경계

- **1차 최소 범위**: `master/ontology/collect.py`에 `cochange_neighbours()`(순수 함수, 커밋당 파일 ≤10 · 최소 동시 출현 ≥3 · `classified_elsewhere` 제외) 추가 + `search_log_analyzer.py`의 시소러스 후보를 `not_a_class`/기존 `aliases`와 대조해 `_usage_candidates.md` 제안 리포트 출력 CLI.
