# #1041-C — 유사·구버전 클래스군(`term_families` 개념) 구분 표식 분석 보고서

> 작성일: 2026-11-28 · 일감: Redmine `#1045` (상위 `#1041`, `아이디어 — 추후 검토 수집`)  
> 대조 스킬: `ax-ontology` (`master/client/skills/ax-ontology/SKILL.md`), `distribute` (`master/skills/distribute/SKILL.md`)  
> 대조 코드: `master/ontology/package.py`, `master/ontology/edit.py`, `master/context_search/domain_index.py`, `master/ontology/verify_facts.py`  
> NVIDIA 원전: `auto_ontology/semantic/term_families.py`, `auto_ontology/semantic/semantic_fk.py`

---

## 1. 개요

NVIDIA `auto-ontology`는 마이그레이션이나 버전 업으로 인해 `OLD_ROOMS`/`NEW_ROOMS`, `V1_`/`V2_`처럼 이름 접두사만 다른 복제 테이블이 공존할 때, `term_families.py`가 이를 결정적으로 묶어 에이전트와 FK 추론기가 구버전 테이블을 현행으로 오인하지 않도록 분리한다.

AX 클러스터가 다루는 언리얼(UE5)·장기 운영 코드베이스에서도 `Legacy_*` · `Old_*` · `*_V2` · `Deprecated_*` 또는 리팩터링 과도기의 구·신 클래스가 공존하는 경우가 흔하다. 이 아이디어는 **도메인 `object` YAML에 구·신 대체 관계 / 패밀리 표식(예: `status: legacy` · `superseded_by`)을 두고 검색·컨텍스트 응답에 드러내 에이전트의 오수정을 막는 방안**을 검토한다.

---

## 2. 실제 코드쪽 내용

### 2.1 NVIDIA 원전 구현 (`auto_ontology/semantic/term_families.py`)
- 순수 함수(`detect_term_families(rows, edges)`), I/O 없음, LLM 0.
- 4단계 규칙:
  1. **Mirrored edges**: 접두사 `P`/`Q`를 떼어냈을 때 동일한 엣지 구조(`P_A.x — P_B.y` vs `Q_A.x — Q_B.y`).
  2. **Twins**: 접두사 제거 후 베이스 이름이 같고 컬럼 집합 Jaccard 유사도 ≥ `0.8` (미러 엣지 끝점은 `0.5`). `*_HIST` 이력 테이블은 제외.
  3. **Confirmation**: 쌍 증거 합계 ≥ `_MIN_PAIR_EVIDENCE (3)` 이상일 때만 패밀리 확정(우연한 이름 일치 배제).
  4. **Expansion**: 확정된 패밀리와 같은 접두사 내부로만 전이 확장(`DIM_DATE` 같은 공용 테이블 경유 오염 차단).
- `semantic_fk.py`에서 다른 패밀리의 복제 테이블로는 FK를 연결하지 못하도록 차단.

### 2.2 AX 클러스터 기존 코드 접점
- **`master/ontology/package.py`**:
  - `HUMAN_FIELDS = ("aliases",)` (L125) — `carry_human_fields()`가 재합성 시 사람이 넣은 필드를 항목 잠금(`verified_by_user`) 없이 필드 단위로 이월한다.
  - 만약 `superseded_by`나 `lifecycle`(`active`/`legacy`/`deprecated`) 같은 표식을 도입한다면, `HUMAN_FIELDS`에 포함시켜 재합성 시 유실되지 않게 보호할 수 있다.
- **`master/ontology/edit.py`**:
  - `edit()`이 `patch`를 얕게 병합하고 `verified_by_user: true`를 건다. `IMMUTABLE = ("name", "layer")`.
- **`master/context_search/domain_index.py`**:
  - `payload()`는 현재 `objects`의 `aliases`를 `tags`(가중치 3.0)에 올리고, `related_classes`에 파일 stem을 넣는다. `legacy`/`superseded_by` 표식이 있어도 현재 검색 결과 발췌에는 구분 표시가 없다.
- **`master/ontology/yaml_io.py`**:
  - PyYAML 의존성 0의 자체 직렬화기이므로 새 스칼라/리스트 필드는 `yaml_io` 왕복 호환성을 반드시 확인해야 한다.

---

## 3. 주의사항

1. **자동 레거시 판정 금지 — 제안 전용**:
   - DB 테이블의 `OLD_`/`NEW_`와 달리, 코드베이스에서는 `Old*`가 여전히 프로덕션에서 쓰이거나 `V2`가 실험용 미완성일 수 있다. 자동 탐지 결과는 **후보 제안**으로만 제시하고, 실제 `superseded_by` 기입은 사람(또는 명시적 `DEPRECATED`/주석 실측)만 확정해야 한다.
2. **순위 가중치 임의 변경 금지 (`domain_index.py` L54)**:
   - `WEIGHTS = (3.0, 1.5, 2.5, 1.0)`과 `RRF_K = 60`은 정답 집합 없이 바꾸면 순위가 드리프트하므로, 레거시 클래스를 검색에서 숨기거나 점수를 깎는 대신 **응답 메타/표시에 `[legacy → 대체: NewClass]` 경고 배지를 붙이는 방식**이 안전하다.
3. **항목 잠금(`verified_by_user`) 오남용 방지 (`edit.py` L20-25)**:
   - 별칭처럼 `superseded_by` 표식 하나 때문에 항목 전체가 잠겨 재합성이 영구 중단되면 안 된다. `package.HUMAN_FIELDS` 이월 방식이 적합하다.

---

## 4. 좋은점

- **에이전트 오수정 사고 예방**: 검색에서 이름 유사도 때문에 구버전 클래스가 먼저 걸렸을 때, 에이전트가 레거시 코드를 수정하거나 새 코드를 레거시 패턴으로 복사하는 실수를 크게 줄일 수 있다.
- **리팩터링 과도기 가시성 확보**: `V1`→`V2` 이전 중인 도메인에서 어떤 클래스가 정본이고 어떤 것이 이전 대상인지 온톨로지 지도 자체가 말해 준다.
- **구현 비용이 낮음**: `package.HUMAN_FIELDS` 확장 + `object` YAML 스칼라 필드 1~2개 + 조회 출력 포맷 보강만으로 1차 적용 가능.

---

## 5. 나쁜점 및 리스크

- **표식 최신화 유지비**: `V2`가 정본이 됐다가 다시 롤백되거나, 레거시 클래스가 삭제될 때 표식이 낡으면 오히려 잘못된 지도가 된다(`drift.py`와 연계 검사 필요).
- **Jaccard 기반 자동 쌍 감지의 코드 적용 한계**: DB 테이블은 컬럼 집합 비교가 잘 먹히지만, C++/Python 클래스는 리팩터링 시 메서드명과 시그니처가 크게 바뀌어 이름 접두사(`Legacy_`, `Old_`, `_V2`) 외의 자동 쌍 감지는 정확도가 낮을 수 있다.
- **프로젝트별 효용 편차**: 레거시 공존이 적은 소규모/신규 저장소에서는 우선순위가 낮다.

---

## 6. 실 작업 착수 시 권장 경계

- **1차 최소 범위**: 자동 패밀리 추론기보다 먼저, ① `object` YAML에 선택 필드 `lifecycle` / `superseded_by` 허용 (`package.HUMAN_FIELDS` 이월), ② `get_object_spec` 및 `search_context` 출력에 `[대체됨 → <NewClass>]` 한 줄 표시, ③ `verify_facts.py`에서 `superseded_by` 대상 클래스 실존 여부만 결정적 검증.
