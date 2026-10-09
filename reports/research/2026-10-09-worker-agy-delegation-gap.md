> 작성: Gemini (agy 1.3.2) · 실행: `master.work.gemini_report` · 2026-10-09 14:24 · 프로젝트 AXCluster
> 자료: src/master/client/skills/ax-work/SKILL.md, src/master/work/lanes.py, src/master/work/runner.py
> 검증: 인용 6개 대조 (Claude, 2026-10-09) — 일치 5 · 불일치 1 (`runner.py:356-358` → 실제 360-361, 본문 [검증 불일치] 표시)
> 소요 133초 · 토큰 입력 62889 / 출력 15521 / 캐시읽기 204014

# 워커 위임 규칙 불일치 및 Gemini(agy) 미사용 원인 분석 보고서

## 요약

1. 워커 지휘자에게 매번 전달되는 지시문(`INSTRUCTION`)에는 `ax-work` 스킬 준수 지침만 포함되어 있을 뿐, `agy` 또는 Gemini 위임 관련 문구나 명령은 언급되어 있지 않습니다 (`src/master/work/runner.py:83-95`).
2. `ax-work` 스킬 문서의 §0.4 서술에서는 대량 생성 위임 순서를 `codex` → `agy` → 로컬 LLM으로 명시하고 있으나, §4 위임 표에서는 `codex`가 누락되어 있고 `agy`의 역할이 "큰 파일 조사·정리"로 표기되어 서술과 표가 불일치합니다 (`src/master/client/skills/ax-work/SKILL.md:17-19`, `src/master/client/skills/ax-work/SKILL.md:97-102`).
3. `lanes.py`의 작성 레인 순서는 `codex` → `agy` → `qwen2.5-coder:14b`이며, 1순위인 `codex` 작성이 성공하는 한 체인이 즉시 반환되므로 `agy`는 `codex` 생성이 실패(에러, 한도 초과 등)할 때만 제한적으로 호출됩니다 (`src/master/work/lanes.py:73`, `src/master/work/lanes.py:284-299`).
4. 지휘자 프롬프트 상의 위임 지시 부재, 스킬 문서 내 규정 불일치, 그리고 작성 레인 체인 구조에서 `codex` 선순위에 따른 `agy` 호출 조건 미충족이 복합적으로 작용하여 워커에서 `agy`(Gemini) 세션이 거의 생성되지 않는 원인으로 뒷받침됩니다 (`src/master/work/runner.py:83-95`, `src/master/client/skills/ax-work/SKILL.md:17-19`, `src/master/client/skills/ax-work/SKILL.md:97-102`, `src/master/work/lanes.py:73`, `src/master/work/lanes.py:284-299`).

---

## 1. 워커 지휘자 전달 지시문과 agy/Gemini 위임 언급 여부

- **전달 지시문 (`INSTRUCTION`) 내용**:
  - 워커 파견 시 지휘자(`claude` 또는 `codex` 모드)에게 매번 전달되는 지시문은 `src/master/work/runner.py:83-95`에 정의된 `INSTRUCTION` 상수 문자열입니다 (`src/master/work/runner.py:83-95`, `src/master/work/runner.py:509-519`).
  - 지시문 전문:
    > `"Follow the ax-work skill. You are on the assigned branch already. This message is dispatched work from the AX master, not a human chat: the plan was already approved when the task was registered. Do not ask for approval, do not propose a plan for review, do not wait for confirmation - implement the bodies now. Read the [DOC] and [PSEUDO] comments in these files and write their bodies: {files}. Judge from the source files in this checkout, not from memory. Do not run any git command. Do not commit or push. Do not run UE5 builds, UnrealBuildTool, UnrealEditor or automation tests, and for Python files do not start servers, run the program or run tests - verification is done later by the requester, not on this worker. The last non-empty line of your output must be exactly RESULT: DONE (use RESULT: BLOCKED if you could not finish, and say why above it)."` (`src/master/work/runner.py:83-95`)

- **`agy`/Gemini 위임 언급 여부**:
  - 지시문(`INSTRUCTION`) 내에는 `ax-work` 스킬을 따르라는 지침만 명시되어 있으며, `agy` 또는 `Gemini`라는 단어나 작업 위임 명령은 **전혀 언급되어 있지 않습니다** (`src/master/work/runner.py:83-95`).
  - 참고로 `runner.py` 내부 모듈 코멘트에는 "네트워크가 필요한 이유는 위임이다. `ax-work §0④`가 대량 생성은 `codex`→`agy`→로컬에 위임하고 너는 검증한다고 지시..."라는 코멘트가 있으나 (`src/master/work/runner.py:356-358` [검증 불일치: 실제 360-361]), 셸 명령을 통해 지휘자 CLI로 직접 전달되는 프롬프트 문자열 `INSTRUCTION`에는 위임 지시문이 들어가지 않습니다 (`src/master/work/runner.py:83-95`, `src/master/work/runner.py:370-371`, `src/master/work/runner.py:412-416`).

---

## 2. ax-work 스킬의 위임 규정 및 서술-표 일치 여부

- **`ax-work` 스킬의 위임 규정**:
  - `ax-work` 스킬 문서 §0.4에서는 워커가 혼자 모든 작업을 수행하지 않고 대량 생성을 위임한 뒤 검증하는 모토를 명시하고 있습니다 (`src/master/client/skills/ax-work/SKILL.md:17-19`).
  - §0.4 서술: *"너 혼자 다 하지 않는다 — 대량 생성은 `codex` → `agy` → 로컬 LLM 순으로 위임하고 너는 검증한다. [중요] 셋은 동급 작성자다 (사용자 결정 2026-09-06) — 코덱스가 1차이고 소진되면 안티그래비티다. 클로드의 한도는 마스터 작업에 남긴다"* (`src/master/client/skills/ax-work/SKILL.md:17-19`).

- **위임 순서 서술과 §4 위임 표의 일치 여부**:
  - **서로 일치하지 않습니다** (`src/master/client/skills/ax-work/SKILL.md:17-19`, `src/master/client/skills/ax-work/SKILL.md:97-102`).
  - **불일치 1 (대상 백엔드 목록 누락)**: §0.4 서술에서는 대량 생성 위임 백엔드로 `codex`, `agy`, `로컬 LLM`을 명시하고 `codex`를 1차 작성자로 규정하고 있으나 (`src/master/client/skills/ax-work/SKILL.md:17-19`), §4 위임 표에는 `로컬 LLM`, `agy`, `너(Claude)` 3 가지만 기재되어 있고 `codex`가 표에서 통째로 누락되어 있습니다 (`src/master/client/skills/ax-work/SKILL.md:97-102`).
  - **불일치 2 (역할 분담 및 순서 상충)**: §0.4 서술은 대량 생성 순서를 `codex` → `agy` → `로컬 LLM` 순으로 명시하고 있으나 (`src/master/client/skills/ax-work/SKILL.md:17-19`), §4 위임 표에서는 `로컬 LLM`을 "반복적 본문 채우기, 대량 변환 (무료)" 역할로 표 최상단에 배치하고, `agy`는 "큰 파일 조사·정리" 용도로 다르게 표기하고 있습니다 (`src/master/client/skills/ax-work/SKILL.md:97-102`).

---

## 3. lanes.py 작성 레인 순서 및 agy 호출 조건

- **`lanes.py` 의 작성 레인 순서**:
  - `lanes.py`에 정의된 기본 작성 레인 순서는 `codex` → `agy` → `qwen2.5-coder:14b` (로컬 모델) 입니다 (`src/master/work/lanes.py:73`).
  - 코드 정의: `DEFAULT_LANES = ("codex", "agy", "qwen2.5-coder:14b")` (`src/master/work/lanes.py:73`).
  - 이는 클로드 한도를 마스터 작업용으로 남기고 작성 업무를 코덱스에 우선 배분하기 위한 사용자 결정(2026-09-06)에 따른 것입니다 (`src/master/work/lanes.py:15-22`, `src/master/work/lanes.py:59-69`).

- **`agy` 가 실제로 호출되는 조건**:
  - `lanes.py`의 `run_chain` 함수는 레인 목록을 순서대로 시도하는 순차 체인(fail-forward) 방식으로 동작합니다 (`src/master/work/lanes.py:284-299`).
  - 따라서 `agy`가 실제로 호출되기 위해 만족해야 하는 조건은 다음과 같습니다:
    1. 마스터에서 레인 체인(`lanes.run_chain`)이 실행되어야 합니다 (`src/master/work/lanes.py:272-284`).
    2. 1순위 레인인 `codex`가 본문 생성에 실패하거나(`r.ok == False`, 예: 429 session limit, 네트워크 오류, 형식 미준수 등), `codex`가 생성한 결과물을 워커 체크아웃에 성공적으로 써 넣지 못했을 때(`write_back` 실패) 제어가 다음 레인으로 넘어갑니다 (`src/master/work/lanes.py:285-298`).
    3. 만약 1순위 레인인 `codex`가 성공(`r.ok == True` 및 `write_back` 성공)하면, 체인은 `agy`를 호출하지 않고 그 즉시 완료되어 반환됩니다 (`src/master/work/lanes.py:298`).

---

## 4. 워커에서 agy가 거의 쓰이지 않는 원인 분석

제시된 `src/` 파일 자료를 바탕으로 분석한 결과, 워커 3대에서 `agy`(Gemini) 세션 수집 기록이 0건인 원인은 다음 4가지 사실로 뒷받침됩니다:

1. **워커 파견 지시문(`INSTRUCTION`) 내 위임 지시 부재**:
   - 마스터가 워커 지휘자(`claude` 또는 `codex`)에게 직접 전달하는 프롬프트인 `INSTRUCTION`에는 `agy`나 `Gemini`로 작업을 위임하라는 구체적인 지시가 포함되어 있지 않습니다 (`src/master/work/runner.py:83-95`). 지휘자는 이 프롬프트를 바탕으로 작업을 수행하므로 스스로 외부 `agy` CLI를 호출하지 않습니다.

2. **`ax-work` 스킬 문서의 위임 모순 및 혼선**:
   - 지휘자가 참고하는 `ax-work` 스킬 문서 내에서 §0.4 서술(`codex`→`agy`→로컬 순)과 §4 위임 표(`codex` 누락, `agy`는 큰 파일 조사·정리용) 간의 대상 백엔드 및 역할 정의가 일치하지 않습니다 (`src/master/client/skills/ax-work/SKILL.md:17-19`, `src/master/client/skills/ax-work/SKILL.md:97-102`).

3. **`lanes.py` 레인 체인상 `codex` 1순위 배치 및 조기 반환**:
   - 작성 레인 체인 `DEFAULT_LANES`에서 `codex`가 1순위, `agy`가 2순위로 설정되어 있습니다 (`src/master/work/lanes.py:73`).
   - `run_chain` 체인은 1순위인 `codex` 작성이 성공하면 조기 반환(`return r, tried`)되므로 `agy`는 실행 기회를 얻지 못합니다 (`src/master/work/lanes.py:284-298`). `codex`가 정상 동작하여 작업을 완수하는 상황에서는 `agy` 호출이 발생하지 않습니다.

4. **워커 실행 체계와 마스터 레인 체계의 구조적 차이**:
   - `runner.py`에 의한 워커 파견은 워커에서 지휘자(`claude` 또는 `codex`)를 실행하는 구조이며 (`src/master/work/runner.py:343-417`), 마스터의 `lanes.py` 체인(`run_chain`)을 직접 거치는 방식이 아닙니다.
   - 이에 따라 지휘자는 `INSTRUCTION`의 명령에 따라 본문을 직접 작성하게 되며, 지시문 미비 및 스킬 문서 불일치로 인해 `agy`로 위임하지 않게 됩니다 (`src/master/work/runner.py:83-95`, `src/master/client/skills/ax-work/SKILL.md:17-19`).

---

## 근거 목록

1. `src/master/work/runner.py:83-95` — 워커 파견 프롬프트 지시문 (`INSTRUCTION`) 전문 정의 (agy/Gemini 언급 없음)
2. `src/master/work/runner.py:343-417` — 지휘자 실행 한 줄 및 샌드박스 설정 (`agent_command`)
3. `src/master/work/runner.py:509-519` — `worker_command` 및 지시문 포맷팅 과정
4. `src/master/client/skills/ax-work/SKILL.md:17-19` — `ax-work` §0.4 전제 (대량 생성 위임 순서: `codex` → `agy` → 로컬 LLM)
5. `src/master/client/skills/ax-work/SKILL.md:93-102` — `ax-work` §4 위임 표 (로컬 LLM, agy, Claude 표기 / codex 누락 및 역할 상충)
6. `src/master/work/lanes.py:15-22` — 작성 레인 순서 변경 이력 및 배경 서술 (codex 1차 작성자 지정)
7. `src/master/work/lanes.py:56-73` — `DEFAULT_LANES` 정의 (`("codex", "agy", "qwen2.5-coder:14b")`)
8. `src/master/work/lanes.py:272-299` — `run_chain` 체인의 순차 실행, `write_back` 검증 및 성공 시 조기 리턴 로직

---

## 확인 불가·한계

1. **워커 3대의 실제 `agy` 바이너리 환경 상태**: 제공된 `src/` 소스 파일 내에는 `lanes.py:56-58`의 코멘트(`command -v agy`) 외에 워커 3대(.2·.33·.43) 실제 환경에 `agy` CLI 바이너리가 정복 설치되어 존재하는지 여부에 대한 정보가 없으므로 「확인 불가」입니다.
2. **워커 개별 실행 로그 상세 원문**: `BRIEF.md`에 제시된 사용량 수집 결과(agy 세션 0건) 외에 워커 3대의 실제 저널 및 stdout 상세 기록 원문은 `src/` 범위 밖이므로 「확인 불가」입니다.
