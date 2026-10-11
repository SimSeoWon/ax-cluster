> 작성: Gemini (agy 1.3.3 · gemini-3.6-flash-high) · 실행: `master.work.gemini_report` · 2026-10-11 17:49 · 프로젝트 AXCluster
> 자료: src/issue-804-and-facts.md, src/master/client/payload/profile/AXCluster.yaml, src/master/work/decompose.py, src/master/work/followup.py, src/master/work/layer1.py, src/master/work/pyskel.py, src/origin/worker/validator.py, src/tests/integration/checks.json, src/tests/integration/test_axcluster.py
> 작성: Gemini · 위임·검증: 마스터 Claude · 2026-10-11 · 검증: 인용 6개 대조 — 일치 4 · 불일치 2 (불일치는 본문에 [검증 불일치] 표시) · 범위 검사(자동): 인용 107개 — 범위 안 103 · 범위 밖 4 · 파일 없음 0
> 소요 250초 · 토큰 입력 97433 / 출력 36067 / 캐시읽기 558270

## 요약

현재 AXCluster의 `.py` 검증은 조각 단위(층1)에서 `ast.parse` 기반 구문 파싱, 동결 시그니처, 스텁 미구현을 잡지만 import 오류·미정의 이름·타입 불일치는 잡지 못한다. ⑦ 통합 검사(`code_build_fn`)는 `checks.json`의 32개 공식 검사와 변경 파일의 `master/test_<stem>.py`만 실행하므로, 대응 테스트가 없는 신규·수정 모듈은 import조차 되지 않는 치명적 사각지대가 있다. 원전(`origin/worker/validator.py`)은 C++ 전용이라 `.py` 정적 검증이 전무했다. 후보 중 `pytest --collect-only`는 최상위 코드 실행 부작용과 스크립트 수집 오탐 위험이 크고, `mypy`는 미타입 코드베이스에서 오탐이 폭발하며, 둘 다 마스터 venv에 미설치 상태다. 따라서 최소 변경으로 최대 구멍을 막는 방안은 ⑦ 통합 단계에 표준 라이브러리(`ast.parse`) 기반 바뀐 파일 전수 구문 검사를 회귀 0차 관문으로 추가하는 것이다.

---

## 1. 현재 검증이 잡는 것과 놓치는 것

### (1) 조각 단위(층1) 검증의 실태

- **실행 위치**: 워커 응답 수락 직전인 `infer.judge`와 디스크 적용 직전인 `integrate.apply_one`의 두 지점에서 fail-closed 방식으로 동작한다(src/master/work/layer1.py:3-10). 워커가 보낸 파일 딕셔너리를 메모리/디스크 쓰기 직전에 검증하는 "결정적·무료·LLM 0" 게이트다(src/master/work/layer1.py:1, src/master/work/layer1.py:108-119). **[검증 불일치]** 인용 줄은 layer1.py 머리말 그대로지만 그 머리말이 낡았다 — `integrate.py` 는 삭제됐고(test_no_integrator) 현재 호출 지점은 `wcommit.py:360` 이다(마스터 대조 2026-10-11).
- **잡는 결함**:
  1. **휘발 태그 잔재**: 소스 코드 주석 머리에 남은 `[PSEUDO]`, `[PSEUDO:N]`, `[IMPL]` 태그(src/master/work/layer1.py:68-71, src/master/work/layer1.py:121-126).
  2. **피드백 블록 잔재**: `[FEEDBACK]` 태그 문자열 및 `AUTO-VERIFY FEEDBACK` 여는 줄(C 주석 및 `#` 주석)(src/master/work/layer1.py:55, src/master/work/layer1.py:76-77, src/master/work/layer1.py:127-131).
  3. **마크다운 펜스 잔재**: 코드 앞뒤의 ```` ``` ```` 마크다운 펜스(src/master/work/layer1.py:132-133).
  4. **파이썬 구문 오류(SyntaxError)**: `pyskel.parse(text)`를 통해 `ast.parse`를 호출하여 파싱 실패 시 차단한다(src/master/work/layer1.py:136-140, src/master/work/pyskel.py:49-55). 이는 기준 원본(`baseline`) 유무와 무관하게 모든 `.py` 파일에 강제된다(src/master/work/layer1.py:135-140).
  5. **동결 인터페이스 변경·삭제**: 기준 원본이 있을 때, 모듈 최상위 함수·클래스 및 클래스 메서드의 시그니처(이름, 인자, 반환 표기 등 `ast.unparse` 비교)를 대조하여 변경이나 삭제를 차단한다(추가는 허용)(src/master/work/layer1.py:148-151, src/master/work/pyskel.py:30-47, src/master/work/pyskel.py:72-82).
  6. **스텁 미구현 잔존**: 골조에서 `# [PSEUDO]` 주석을 몸 안에 가졌던 함수가 구현 후에도 본문이 `raise NotImplementedError` 또는 `...`만으로 남아 있으면 미구현으로 차단한다(src/master/work/layer1.py:153-157, src/master/work/pyskel.py:84-128).
- **놓치는 결함**:
  1. **import 오류**: 존재하지 않는 모듈/패키지 import, 모듈 경로 오타, 패키지 미설치 등(`ModuleNotFoundError`, `ImportError`)을 전혀 검증하지 못한다(src/issue-804-and-facts.md:9-10).
  2. **미정의 이름(NameError)**: 함수 본문이나 모듈 레벨에서 정의되지 않은 변수, 함수, 클래스, 임포트 심볼을 참조하는 오류를 잡지 못한다(src/issue-804-and-facts.md:9-10).
  3. **타입·속성 불일치**: 인자 개수 불일치, 타입 오류(`TypeError`), 존재하지 않는 객체 속성 참조(`AttributeError`) 등을 잡지 못한다(src/issue-804-and-facts.md:9-10).
  4. **신규 파일의 동결·스텁 누락**: 기준 원본이 없는 신규 `.py` 파일은 동결 대조 대상이 없어 동결 위반 및 스텁 잔존 검사가 스킵된다(src/master/work/layer1.py:146-147, src/master/work/layer1.py:168). 골조 게이트 역시 신규 파일은 기준 커밋에 없어 검사를 건너뛴다(src/master/work/decompose.py:403, src/master/work/decompose.py:418-419).

### (2) ⑦ 통합 단위(`code_build_fn`) 검증의 실태

- **실행 구성**: ① 공식 통합 검사(`unittest discover`)와 ② 이번 라운드 변경분의 회귀 검사(`regression_targets` -> `run_regression`)로 구성된다(src/master/work/followup.py:221-235).
- **테스트·회귀 선택 기준**:
  1. **① 공식 통합 검사**:
     - 실행 명령: `python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`(src/master/work/followup.py:227-228, src/master/work/followup.py:256, src/master/work/followup.py:313).
     - 동작 방식: `tests/integration/test_axcluster.py`를 실행하며, 이 스크립트는 `tests/integration/checks.json`에 하드코딩된 32개 검사 목록을 읽어 각 검사를 별도 프로세스(`run_check`)로 실행한다(src/tests/integration/test_axcluster.py:17, src/tests/integration/test_axcluster.py:25-27, src/tests/integration/checks.json:1-162, src/issue-804-and-facts.md:24).
     - **중요 특성**: `test_axcluster.py` 자체는 다른 master 테스트나 작업 모듈을 import하지 않는다(src/tests/integration/test_axcluster.py:24).
  2. **② 회귀 검사**:
     - 변경 파일 추출: `git diff base_ref HEAD --name-only`로 이번 라운드(`base_ref..HEAD`)에서 바뀐 파일 목록을 얻는다(src/master/work/followup.py:122-127, src/master/work/followup.py:285).
     - 선택 규칙(`regression_targets`):
       - `__init__.py`, `tests/` 하위 파일, `.py`가 아닌 확장자는 대상에서 제외한다(src/master/work/followup.py:154-155).
       - 변경 파일이 `master/test_*.py` 자체이면 그 파일을 회귀 대상으로 선정한다(src/master/work/followup.py:156-157).
       - 그 밖의 `<경로>/<stem>.py`에 대해서는 트리에 `master/test_<stem>.py`가 존재하는지 확인한다(src/master/work/followup.py:158-160).
       - `master/test_<stem>.py`가 트리에 없으면 "대응 회귀 검사 없음" 사유를 `notes`에 남기고 회귀 대상에서 제외한다(src/master/work/followup.py:161-162).
       - 이미 `checks.json`(공식 목록)에 등록된 테스트면 "공식 목록에 있다"는 사유를 남기고 회귀 대상에서 제외한다(src/master/work/followup.py:163-165).
       - 회귀 대상이 0건이면 실패가 아니라 "회귀 대상 0건 (바뀐 경로 기준) — 없음"으로 정상 처리된다(src/master/work/followup.py:232-233, src/master/work/followup.py:291, src/issue-804-and-facts.md:25).
- **새로 생기거나 바뀐 모듈의 import 여부**:
  - 새로 생기거나 바뀐 모듈은 **전혀 import되지 않을 수 있다**(src/issue-804-and-facts.md:24-25).
  - 바뀐 모듈에 대응하는 `master/test_<stem>.py` 파일이 트리에 아직 없는 경우 회귀 검사 대상이 0건이 되며, 공식 32개 검사 스크립트 중 해당 모듈을 import하는 곳이 없다면 통합 검사 과정 전체에서 해당 모듈은 단 한 번도 로드되지 않는다(src/master/work/followup.py:160-162, src/issue-804-and-facts.md:24-25).
  - **실측 사례 (#805)**: 2026-10-11 재작업 통합 트리의 `master/rework_probe/alpha.py` 머리에 C 주석 블록이 들어가 명백한 `SyntaxError`였음에도 불구하고, 대응 테스트(`master/test_alpha.py`)가 없어 회귀 대상 0건이 찍혔고, 공식 32개 검사는 이 새 모듈을 import하지 않아 32/32 전원 통과하는 사각지대가 발생했다(src/issue-804-and-facts.md:23-25).
- **통합 검사가 잡는 것과 놓치는 것**:
  - **잡는 것**: `checks.json`에 명시된 32개 기존 정본 검사의 통과 여부 및, 트리에 이미 존재하는 `master/test_<stem>.py` 회귀 테스트의 통과 여부(src/master/work/followup.py:248-311, src/tests/integration/checks.json:1-162).
  - **놓치는 것**: 대응 `master/test_<stem>.py`가 아직 없는 신규 모듈 및 수정 모듈의 구문 오류(`SyntaxError`), import 오류(`ImportError`), 정의되지 않은 이름(`NameError`), 런타임 오류 전체(src/master/work/followup.py:160-162, src/issue-804-and-facts.md:23-25).

---

## 2. 원전 대조

### (1) 원전(`src/origin/worker/validator.py`)의 검사 존재 여부

- 원전에는 `.py` 정적 검증이나 파이썬에 준하는 검사가 **전혀 없었다**(src/origin/worker/validator.py:1-707).
- 원전은 Windows + Unreal Engine 5 (C++) 기반 환경의 파이프라인이었다(src/master/client/payload/profile/AXCluster.yaml:4-7, src/origin/worker/validator.py:17-23).

### (2) 원전이 수행한 검사와 위치

- **수행 위치**:
  1. `_validate_disk_after_agent`: 워커의 에이전트가 디스크 파일을 직접 수정한 직후 호출되는 검증(src/origin/worker/validator.py:522-638).
  2. `_validate_llm_output`: LLM 완성 출력 문자열에 대한 프로토콜 검증(src/origin/worker/validator.py:667-706).
- **수행 내용**:
  1. **인터페이스 동결 검사**: C++ 헤더 파일(`.h`)에 대해 UE 매크로(`_DECL_MACRO_RE`), 클래스 선언(`_CLASS_DECL_RE`), 함수 시그니처(`_FUNC_SIG_RE`)를 정규식으로 추출하여 골조 헤더 선언의 변경/삭제를 차단했다(src/origin/worker/validator.py:17-60, src/origin/worker/validator.py:568-575).
  2. **마커 잔재 검사**: `[PSEUDO]` 마커 잔재 검출(src/origin/worker/validator.py:554-557).
  3. **펜스 및 피드백 잔재**: 마크다운 코드 펜스(```` ``` ````) 및 `/* AUTO-VERIFY FEEDBACK ... */` 주석 블록 잔재 검출(src/origin/worker/validator.py:563-566, src/origin/worker/validator.py:684-691).
  4. **`#include` 손실 검사**: 원본에 있던 `#include` 행이 누락되었는지 검사(src/origin/worker/validator.py:577-584, src/origin/worker/validator.py:699-705).
  5. **무단 파일 수정 차단**: `git status`를 확인하여 허용된 target 및 header 외 파일 수정을 차단(src/origin/worker/validator.py:585-634).
  6. **첫 줄 일치 검사**: LLM 출력 첫 줄이 대상 파일 첫 줄과 일치하는지 대조(src/origin/worker/validator.py:692-698).

### (3) 원전과 AXCluster의 차이점 및 분화 배경

- C++에서는 컴파일러(UBT/UHT)가 빌드 단계에서 구문·심볼 오류를 잡아주었으므로 원전 검증기는 헤더 정규식 대조만으로 충분했다(src/master/work/pyskel.py:17).
- 반면 Python은 헤더 파일이 없고(`is_header(".py") == False`) 선언과 정의가 한 몸이라 원전의 정규식 검사가 완전히 무력화되었으며, 2026-09-30 실측에서 시그니처 변경과 함수 삭제가 층1을 그대로 통과하는 문제가 발생했다(src/master/work/pyskel.py:5-8).
- 이에 따라 AXCluster는 `#695` P3에서 비로소 AST 기반의 `pyskel.py`를 신설하여 구문 파싱, 시그니처 동결, 스텁 미구현 검출을 도입했다(src/master/work/pyskel.py:1-21).
- 또한 원전의 "워커 제출 전 자기검증"은 워커의 계약 위반 실측에 따라 마스터가 응답을 수락하고 적용하는 자리(`layer1.py`)의 "verify-then-commit" 구조로 이전되었다(src/master/work/layer1.py:12-15, src/issue-804-and-facts.md:28).

---

## 3. 후보 비교

### 후보 목록
- **(a) `pytest --collect-only`**: 테스트를 실행하지 않고 수집만 수행 (자료 밖 일반 지식 — 출처 없음)
- **(b) `pyflakes`**: 실행 없이 AST 정적 분석으로 미정의 이름·미사용 import 검출 (src/issue-804-and-facts.md:17)
- **(c) `mypy`**: 실행 없이 정적 타입 검사 수행 (src/issue-804-and-facts.md:18)
- **(d) 바뀐 `.py`의 `py_compile`/구문 검사 (`ast.parse`)**: 표준 라이브러리를 통한 순수 파이썬 문법 검사 (src/master/work/pyskel.py:49-55)
- **(e) 바뀐 모듈 실제 import 검사**: 서브프로세스 또는 `importlib`로 모듈을 실제로 로드 (src/issue-804-and-facts.md:15)

### 종합 비교표

| 비교 축 | (a) `pytest --collect-only` | (b) `pyflakes` | (c) `mypy` | (d) 바뀐 `.py` 구문 검사 (`ast.parse`) | (e) 바뀐 모듈 실제 import |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **잡는 결함** | 테스트 수집 단계의 import 오류, 구문 오류, 수집 가능한 모듈 결함 (src/issue-804-and-facts.md:14) | 미정의 이름(NameError), 미사용 import 등 정적 결함 (src/issue-804-and-facts.md:17) | 정적 타입 불일치, 속성 부재(AttributeError) (src/issue-804-and-facts.md:18) | 파이썬 구문 오류(`SyntaxError`, `IndentationError`) (src/master/work/pyskel.py:49-55) | 최상위 import 오류(`ModuleNotFoundError`), 모듈 최상위 구문·이름 오류 (src/issue-804-and-facts.md:14-15) |
| **오탐 위험** | **매우 높음**: 저장소의 스크립트형 테스트와 비표준 수집 패턴에서 수집 실패 발생 위험 (src/issue-804-and-facts.md:16) (자료 밖 일반 지식 — 출처 없음) | **낮음~중간**: 동적 속성 할당 등에서 경고 가능하나 미정의 이름 필터링 시 안정적 (자료 밖 일반 지식 — 출처 없음) | **극도로 높음**: 타입 힌트 미비 및 동적 모듈 로딩(`setattr` 등)으로 대량의 거짓 양성 오류 폭발 (src/tests/integration/test_axcluster.py:27) (자료 밖 일반 지식 — 출처 없음) | **0**: 파이썬 표준 문법 파싱이므로 정상 코드에 대한 오탐 없음 (src/master/work/layer1.py:38-40) | **높음**: CLI 스크립트 등 인자·환경변수가 필요한 모듈 import 시 예외 발생 (src/issue-804-and-facts.md:16) (자료 밖 일반 지식 — 출처 없음) |
| **import 부작용** | **있음**: 수집 과정에서 모듈을 실제로 import하므로 최상위 코드가 실행됨 (src/issue-804-and-facts.md:15) | **없음**: 코드를 실행하지 않고 AST만 분석함 (src/issue-804-and-facts.md:17) | **없음**: 타입 분석 단계에서 코드를 실행하지 않음 (src/issue-804-and-facts.md:18) | **없음**: 바이트코드/AST 파싱만 수행하며 실행하지 않음 (src/master/work/pyskel.py:49-55) | **매우 큼**: 모듈 최상위 코드가 무조건 실행되므로 소켓, 서브프로세스, 파일 변조 위험 (src/issue-804-and-facts.md:15) |
| **설치·배달 필요** | **필요**: 마스터 venv에 미설치 상태 (src/issue-804-and-facts.md:22) | **필요**: 마스터 venv에 미설치 상태 (src/issue-804-and-facts.md:22) | **필요**: 마스터 venv에 미설치 상태 (src/issue-804-and-facts.md:22) | **불필요 (0)**: 파이썬 표준 라이브러리 내장 (src/master/work/pyskel.py:8) | **불필요 (0)**: 파이썬 표준 인터프리터 자체 기능 (src/master/work/followup.py:241) |
| **기존 검사 중복** | 층1의 `ast.parse` 및 32개 공식 검사와 부분 중복 (src/master/work/layer1.py:136, src/tests/integration/checks.json:1-162) | 층1의 구문 검사와 일부 겹치나 미정의 이름 탐지는 신규 보강 (src/issue-804-and-facts.md:17) | 층1 동결 검사와 거의 중복 없음 (src/issue-804-and-facts.md:18) | **층1과는 완전 중복이나, ⑦ 통합 단위에서는 누락되어 있던 부분임** (src/issue-804-and-facts.md:23-27) | 32개 공식 검사가 이미 import하는 모듈과 부분 중복 (src/tests/integration/checks.json:1-162) |

### 위치별 적합성 세부 비교

#### [위치 1] 층1 조각 단위 (`master/work/layer1.py`, `pyskel.py`)
- **실행 환경**: 커밋 전 메모리 파일 딕셔너리(`files: dict`)를 대조하는 "즉시·무료·LLM 0" 단계다(src/master/work/layer1.py:1, src/master/work/layer1.py:108-119, src/issue-804-and-facts.md:28).
- **후보별 평가**:
  - `pytest --collect-only`: 디스크에 전체 파일 트리가 커밋되기 전이므로 수집 자체가 성립하지 않으며, 외부 패키지 미설치로 실행 불가다(src/issue-804-and-facts.md:22). **부적합.**
  - `pyflakes`: 문자열 기반 AST 분석이 가능하므로 층1의 철학("실행 없는 분석")에 가장 부합한다(src/issue-804-and-facts.md:17). 그러나 마스터 venv에 설치되어 있지 않다(src/issue-804-and-facts.md:22).
  - `mypy`: 단일 파일 인메모리 검사로는 상호 참조를 풀 수 없고 무수히 많은 에러를 낸다 (자료 밖 일반 지식 — 출처 없음). **부적합.**
  - `py_compile` / `ast.parse`: **이미 층1에 완벽히 구현되어 작동 중이다**(src/master/work/layer1.py:136-140, src/issue-804-and-facts.md:26).
  - 실제 import: 조각 단위에서 프로세스를 띄워 import하면 의존 파일 부재로 실패하며 부작용이 크다(src/issue-804-and-facts.md:15). **부적합.**

#### [위치 2] ⑦ 통합 단위 (`master/work/followup.py`의 `code_build_fn`)
- **실행 환경**: 모든 조각이 커밋되고 통합 트리(디스크)가 완성된 후, 공식 테스트와 회귀를 돌리는 단계다(src/master/work/followup.py:221-235).
- **후보별 평가**:
  - `pytest --collect-only`: 마스터 venv 미설치(src/issue-804-and-facts.md:22), 스크립트형 테스트 수집 실패로 인한 오탐 위험(src/issue-804-and-facts.md:16), 최상위 코드 실행 부작용(src/issue-804-and-facts.md:15)으로 인해 부적합하다.
  - `pyflakes`: ⑦ 통합 트리의 변경 파일 전체를 대상으로 실행 없는 정적 분석을 수행할 수 있어 이상적이지만, 마스터 venv에 패키지 설치가 선행되어야 한다(src/issue-804-and-facts.md:22).
  - `mypy`: 미타입 코드베이스 전체에서 방대한 오류를 발생시켜 정상 통합을 차단한다(src/master/work/layer1.py:38-40) (자료 밖 일반 지식 — 출처 없음). **부적합.**
  - `py_compile` / `ast.parse`: **⑦ 통합 단위에 현재 가장 필요한 최소 변경 안이다.** #805처럼 대응 테스트가 없어 32개 검사를 우회한 모듈의 구문 오류를 100% 잡아내며, 설치가 필요 없고 오탐과 부작용이 0이다(src/issue-804-and-facts.md:22-25).
  - 실제 import: 격리된 서브프로세스로 돌릴 수 있으나, 환경 변수나 인자를 요구하는 모듈의 최상위 코드 실행 부작용 및 오탐 제어가 까다롭다(src/issue-804-and-facts.md:15-16).

---

## 4. 권고

### (1) 3대 질문 관점의 검토

1. **① 원전에 있나**:
   - 원전(`origin/worker/validator.py`)에는 파이썬 정적 검증이 전혀 없었다(src/origin/worker/validator.py:1-707).
   - 원전은 C++ 컴파일러(조각 빌드)와 테스트가 잡았으며(src/master/work/pyskel.py:17), 원전의 규약을 억지로 끌어올 수 없다.
2. **② 이미 잡는 게 있나**:
   - **조각 단위(층1)**: 이미 `ast.parse`를 통해 정상 작업 조각의 구문 오류(`SyntaxError`)를 커밋 전에 100% 잡고 있다(src/master/work/layer1.py:136-140, src/issue-804-and-facts.md:26).
   - **⑦ 통합 단위(`code_build_fn`)**: 이번 라운드 변경 파일 중 대응 회귀 테스트(`master/test_<stem>.py`)가 없는 파일은 공식 32개 검사가 import하지 않는 한 **구문 오류조차 잡지 못하고 통과시킨다**(src/master/work/followup.py:160-162, src/issue-804-and-facts.md:23-25).
3. **③ 오탐이면 뭐가 죽나**:
   - `pytest --collect-only`나 `mypy`를 도입하면:
     - 마스터 venv에 설치가 안 되어 있어 통합 검사 프로세스 자체가 죽는다(src/issue-804-and-facts.md:22).
     - 스크립트형 테스트 수집 오류나 미타입 어노테이션 에러로 인해 멀쩡한 작업이 오탐으로 차단되어 라운드 전체가 죽는다(src/issue-804-and-facts.md:16, src/issue-804-and-facts.md:29).
     - "정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다"는 프로젝트 제1원칙을 정면으로 위반하게 된다(src/master/work/layer1.py:38-40, src/issue-804-and-facts.md:29-30).

### (2) 최종 권고안: ⑦ 통합 단위의 `ast.parse` 전수 구문 검사 추가

**권고 안**:
⑦ 통합 검사 함수인 `code_build_fn`(src/master/work/followup.py:221) 내부에서, 회귀 검사를 수행하기 직전에 **이번 라운드에서 바뀐 모든 `.py` 파일(`changed_files`)에 대해 표준 라이브러리 `ast.parse`를 수행하는 '0차 구문 관문'을 추가한다.**

**선정 근거**:
1. **실측된 최대 구멍(#805) 완벽 차단**:
   - #805 사례에서 드러났듯, 조각 단위를 우회한 파일(피드백 커밋 등)이나 대응 회귀 테스트가 없는 신규 모듈은 32/32 통합 검사를 그대로 통과해버린다(src/issue-804-and-facts.md:23-27).
   - `changed_files` 목록(src/master/work/followup.py:285)을 직접 순회하여 구문을 검사하면, 대응 테스트 유무와 상관없이 바뀐 모든 파일의 구문 오류를 통합 단계에서 즉시 차단한다.
2. **오탐 위험 0**:
   - 파이썬 표준 문법 유효성만 파싱하므로 문법이 정상인 코드를 오탐으로 차단할 위험이 전무하다(src/master/work/layer1.py:38-40). **[검증 불일치]** 인용한 layer1.py:38-40 은 「없는 위반을 만들지 않는다」는 정책 문장이지 구문 검사의 오탐이 전무하다는 근거가 아니다 — 「전무」는 보고서의 추론이다(마스터 대조 2026-10-11).
3. **설치·환경 배달 불필요 (비용 0)**:
   - 마스터 `.venv`에 pytest, mypy, pyflakes가 모두 없는 상태에서도(src/issue-804-and-facts.md:22), 파이썬 내장 `ast` 모듈만으로 즉시 동작한다(src/master/work/pyskel.py:8).
4. **부작용 0**:
   - 코드를 import하거나 실행하지 않으므로 모듈 최상위 코드 실행으로 인한 부작용이 전혀 없다(src/issue-804-and-facts.md:15).
5. **극소 변경**:
   - `followup.py`의 `code_build_fn` 내에 `changed_files`를 순회하는 수 줄의 루프만 추가하면 되므로 코드베이스 변경이 최소화된다.

*(참고: 추후 미정의 이름(NameError)까지 잡고자 한다면 2단계로 `pyflakes` 도입을 검토할 수 있으나, 이는 마스터 venv에 패키지 설치가 선행되어야 하므로(src/issue-804-and-facts.md:22) 최소 변경 원칙에 부합하지 않는다. 따라서 1단계는 표준 `ast.parse` 전수 검사가 최선이다.)*

---

## 근거 목록

- src/issue-804-and-facts.md:5 — #804 사용자 제안 내용
- src/issue-804-and-facts.md:9-10 — 층1의 현재 한계(import 오류·미정의 이름·타입 불일치 미검출)
- src/issue-804-and-facts.md:14-16 — pytest --collect-only의 특성, 최상위 코드 실행 및 스크립트 수집 오탐 위험
- src/issue-804-and-facts.md:17 — pyflakes의 특성(실행 없는 정적 검사)
- src/issue-804-and-facts.md:18 — mypy의 특성(실행 없는 타입 검사)
- src/issue-804-and-facts.md:22 — 마스터 venv에 pytest·mypy·pyflakes 미설치 실측 사실
- src/issue-804-and-facts.md:23-25 — #805 실측 사례(alpha.py 구문 오류가 32/32 통합 검사 통과 및 회귀 0건)
- src/issue-804-and-facts.md:26-27 — 층1의 구문 오류 차단 및 피드백 커밋 우회 경로
- src/issue-804-and-facts.md:28 — verify-then-commit 파이프라인 구조
- src/issue-804-and-facts.md:29-30 — "게이트를 다섯 번째로 만들지 않는다" 프로젝트 규칙 및 3대 질문
- src/issue-804-and-facts.md:31 — AXCluster profile 요약
- src/master/work/pyskel.py:1-21 — `.py` 골조 검사 설계 의도, C++와의 차이, 검사 항목(동결·스텁·구문)
- src/master/work/pyskel.py:30-47 — 시그니처 추출(`_sig`) 및 AST 순회(`_walk`)
- src/master/work/pyskel.py:49-55 — `pyskel.parse` (`ast.parse` 기반 구문 파싱)
- src/master/work/pyskel.py:57-82 — 동결 인터페이스 추출 및 위반 판정(`violation`)
- src/master/work/pyskel.py:84-128 — 스텁 판정(`_is_stub`) 및 미구현 잔존 검출(`unfilled`)
- src/master/work/layer1.py:1-15 — 층1 검증 개요, 배치 위치(수락 전/적용 직전 fail-closed), 워커 검증의 마스터 이전
- src/master/work/layer1.py:18-25 — 층1 검사 항목 및 보존 태그 규칙
- src/master/work/layer1.py:27-33 — `[FEEDBACK]` 잔재 차단 배경
- src/master/work/layer1.py:38-40 — fail-closed 원칙 ("정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다")
- src/master/work/layer1.py:51-52 — `_is_py` 확장자 검사
- src/master/work/layer1.py:68-81 — 태그 정규식(`_VOLATILE`, `_FEEDBACK_BLOCK`)
- src/master/work/layer1.py:83-105 — `Layer1` 결과 데이터클래스
- src/master/work/layer1.py:108-169 — `check` 함수 본체 (구문 검사 136-140, 동결 검사 148-160, 스킵 처리 164-168)
- src/master/work/followup.py:24 — `code` 판 통합 검사 정의
- src/master/work/followup.py:76-88 — 공식 통합 검사 설정(OFFICIAL_START_DIR, OFFICIAL_PATTERN, OFFICIAL_MANIFEST, REGRESSION_PATTERNS)
- src/master/work/followup.py:122-127 — `changed_files` (`git diff base_ref HEAD`)
- src/master/work/followup.py:130-168 — `regression_targets` (대응 테스트 탐색 및 제외 규칙)
- src/master/work/followup.py:183-204 — `run_regression` (회귀 스크립트 실행 및 결과 파싱)
- src/master/work/followup.py:221-245 — `code_build_fn` 통합 검사 본체 정의
- src/master/work/followup.py:256-279 — ① 공식 통합 검사 실행 (`unittest discover`)
- src/master/work/followup.py:281-299 — ② 회귀 검사 실행
- src/master/work/followup.py:300-311 — 종합 통과 판정 (`integ.passed and reg_ok`)
- src/tests/integration/test_axcluster.py:1-31 — 공식 통합 검사 러너 (`checks.json` 동적 로드 및 서브프로세스 실행)
- src/tests/integration/test_axcluster.py:24 — "다른 master 테스트를 import하지 않는다" 명시
- src/tests/integration/checks.json:1-162 — 공식 검사 32개 정본 매니페스트
- src/master/work/decompose.py:392-433 — `python_skeleton_gate` (골조 게이트 및 신규 파일 스킵 규칙)
- src/master/client/payload/profile/AXCluster.yaml:1-13 — AXCluster 프로필 정의 (kind: code, test_pattern, test_start_dir, work_exts)
- src/origin/worker/validator.py:9-60 — 원전 인터페이스 동결 검사 원칙 및 C++ 정규식 추출
- src/origin/worker/validator.py:522-638 — 원전 `_validate_disk_after_agent` (C++ 대상 디스크 검증 항목들)
- src/origin/worker/validator.py:667-706 — 원전 `_validate_llm_output` (LLM 출력 프로토콜 검증)

---

## 확인 불가·한계

1. **워커 머신의 venv 패키지 설치 현황**: `src/issue-804-and-facts.md:22`에는 마스터 노드(`.venv`)에 pytest·mypy·pyflakes가 미설치되어 있다는 사실만 기재되어 있으며, 분산 워커 노드(`.2`, `.43`)의 venv 설치 현황은 자료에 없어 확인 불가다.
2. **저장소 전체 모듈 구조**: `checks.json`에 명시된 32개 검사 파일과 `src/`에 제공된 파일 외에, 실제 AXCluster 전체 레포지토리에 존재하는 총 파이썬 모듈 수 및 개별 모듈의 최상위 코드 배치 상태는 제공된 파일 범위 밖이라 확인 불가다.
3. **외부 도구 세부 동작**: pytest의 버전별 상세 수집 알고리즘이나 pyflakes의 AST 노드 순회 규칙, mypy의 타입 추론 세부 구현은 `src/` 자료에 없으므로 (자료 밖 일반 지식 — 출처 없음)에 의존하여 분석하였다.
