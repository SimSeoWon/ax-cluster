# 153 — #820 조각 범위 밖 변경 감지 — [PSEUDO] 범위 검사 및 사람 게이트 연동

> 2026-11-08 · 일감 #820 · 작업 위치 `.ax-issues/820` (`issue/820`) · 시작 리비전 `0f1274d`
> 지휘: Antigravity (Gemini Flash Medium) · 구현 위임: Argon (`gemini-4-argon-medium`) 서브에이전트

## 1. 배경과 문제

- **문제 (실측 2026-10-11, #817 `review_runner` 조각)**:
  - 워커에게 import 삭제를 지시했으나 같은 파일의 `DRAFT_PROMPT` 펜스까지 지워버리는 이탈이 발생함.
  - 기존 게이트 체계(층1, 층2, ⑦ 정적·통합 검사, 사람 게이트) 어디에도 「지시받은 범위 밖을 변경했는가」를 감지하거나 고지하는 자리가 없었음.
- **오탐 실측 (2026-10-31 저널)**:
  - 지난 66개 .py 조각(337 덩어리) 분석 결과, 정당한 연쇄 변경(호출부 수정, 변수 선언 등)이 18% 존재하여 (a) 층1 차단으로 막을 경우 정상 조각을 거절하는 부작용 확인.
  - 따라서 **(b) ⑦ 사람 게이트 고지("범위 밖 변경 덩어리 N건")**에 결정적 정보로 제공하여 사람이 최종 판단할 수 있도록 설계 결정.
- **구현 방식**:
  - AST 기반 `[PSEUDO]` 지시 범위 분석 및 diff hunk 분류 로직을 **Gemini 4 Argon (`gemini-4-argon-medium`) 서브에이전트에게 위임**하여 구현.

---

## 2. 변경 내용

- **`master/work/scope_check.py` (신설)**:
  - `find_pseudo_spans(source: str) -> list[tuple[int, int]]`:
    - AST 파싱을 통해 `[PSEUDO]` 주석이 위치한 가장 안쪽 함수/클래스/최상위 문의 라인 범위를 산출.
  - `parse_diff_hunks(diff_text: str) -> list[dict]`:
    - Unified diff 헤더(`@@ -old,len +new,len @@`)와 변경 줄을 파싱하여 변경이 일어난 실제 old line 범위를 정확히 추출.
  - `classify_hunk(hunk: dict) -> str`:
    - 변경 내용을 `other`, `import`, `comment` 3가지 유형으로 분류.
  - `check_scope(base_source: str, diff_text: str, filename: str = "") -> ScopeReport`:
    - base 소스의 `[PSEUDO]` 범위와 diff hunk를 대조하여 범위 밖 변경 통계(`ScopeReport`) 집계.
  - `ScopeReport.render_line() -> str`:
    - `범위 밖 변경 덩어리 N건 (other X · import Y · comment Z)` 포맷 렌더링.
- **`master/test_scope_check.py` (신설)**:
  - 정상 범위 변경, 범위 밖 로직 수정(`other`), import 추가(`import`), 주석 추가(`comment`), 최상위 모듈 블록, PSEUDO 미포함 파일 등 7개 단위 테스트 전수 검증.
- **`master/work/followup.py`**:
  - `collect_scope_report(tree: Path | str, before: str, head: str) -> dict`:
    - 머지된 통합 작업 트리에서 `git diff --name-only <before>..<head>`로 대상 `.py` 파일을 조회하고, `before` 시점 코드와 diff를 비교하여 전체 범위 이탈 통계 집계.
  - `Followup` dataclass에 `scope_report: dict` 필드 추가.
  - `prepare()`: 머지 및 통합 검사 후 `collect_scope_report` 호출하여 결과 저장.
  - `render()`: `at_gate` 상태 고지 시 머지 조각 정보 다음 줄에 `범위 밖 변경 덩어리 N건 (...)` 안내 라인 출력 연동.
- **`master/test_followup.py`**:
  - `test_scope_report_rendered_at_gate`: 범위 이탈 존재 시 렌더링 포함 여부 및 정상 시 미출력 여부 검증 추가 (367/367 통과).

---

## 3. 검증 결과

1. **단위 검사**:
   - `master/test_scope_check.py`: 7/7 전수 통과.
   - `master/test_followup.py`: 367/367 전수 통과.
2. **공식 통합 검사**:
   - `tests/integration/checks.json` 188건: **`Ran 188 tests in 172.894s` · `OK` (188/188)** 통과.

---

최종 결과는 Redmine #820 마감 노트로 기록.
