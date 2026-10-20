> 작성: Gemini (agy 1.4.3 · gemini-3.8-flash-medium) · 실행: `master.work.gemini_report` · 2026-10-21 01:58 · 프로젝트 AXCluster
> 자료: src/AGENTS.md, src/CLAUDE.md, src/machines/sim-desktop.md, src/master/context_search/expand.py, src/master/context_search/search.py, src/master/context_synth/prompt.py, src/master/doc_sync/draft.py, src/master/work/infer.py, src/master/work/lanes.py, src/master/work/runner.py, src/web-sources.md
> 검증: 인용 5개 대조 — 일치 4 · 불일치 1 (불일치는 본문에 [검증 불일치] 표시) · 범위 검사(자동): 인용 126개 — 범위 안 126 · 범위 밖 0 · 파일 없음 0
> 소요 287초 · 토큰 입력 204559 / 출력 29969 / 캐시읽기 705794

## 요약

최근 컨텍스트 엔지니어링 연구와 산업계 기술 보고서(`src/web-sources.md:6-35`)는 LLM에 정보를 무조건 많이 제공하는 것보다 불필요하거나 중복된 정보를 배제하는 「가지치기(pruning)」와 「Just-in-Time 공급」이 에이전트의 성공률과 추론 비용, 모델 성능 안정성에 직결된다고 강조하고 있다.

AX 클러스터 코드베이스(`src/` 디렉터리 내 자산)를 컨텍스트 가지치기 관점에서 전수 점검한 결과, 네 가지 주요 LLM 진입 지점(자동 로드 문서, 워커 파견 지시문, RAG 검색 조립, 합성·문서 프롬프트) 전반에 걸쳐 심각한 토큰 과적 및 중복, 낡은 역사적 내러티브의 누적, 불필요한 예시·지침이 관찰되었다:
1. **자동 로드 문서**: `src/CLAUDE.md`, `src/AGENTS.md`, `src/machines/sim-desktop.md`는 세 문서 도합 1,042줄에 달하며, 세션 진입 시마다 무조건 로드되어 고정 비용을 발생시킨다. 내부에는 이미 닫힌 마일스톤(M1~M6)의 세부 역사, 과거 오인용 정정 과정, 삭제된 모듈(`integrate.py`, `carry.py`)의 내력과 세 문서 간 동일 규칙의 중복 기재가 다수 남아 있다.
2. **워커 파견 지시문**: `runner.py`, `infer.py`, `lanes.py`는 `ax-work`/`ax-infer` 스킬 문서가 이미 존재하는 상태에서 명령줄 프롬프트(`INSTRUCTION`)에 세부 위임 규칙, 파일 저장 경로, git/빌드 금지 목록 등 수십 줄의 엣지 케이스 규칙을 중복 전달하고 있다.
3. **RAG 검색 조립**: `search.py`와 `expand.py`는 시소러스 확장 시 원본 질의의 불용어를 유지한 채 최대 6개의 클래스명을 뒤에 이어 붙이고 48개의 후보를 긁어 RRF로 융합함으로써, 핵심 키워드 밀도를 희석하고 방해 문서(distractor)가 유입될 위험을 안고 있다.
4. **합성·문서 프롬프트**: `prompt.py`는 존재하지 않는 '도메인 규범'에 대한 안내문을 고정 주입하고 가짜 클래스 예시(`UExampleComponent`)를 포함하여 환각 방지용 변명 지침을 추가해야 하는 구조이며, `draft.py`는 단일 문서 수정을 위해 수만 자의 전체 문서와 줄 번호가 매겨진 방대한 근거 텍스트를 무조건 결합 전송하여 수만~십만 단위의 캐시 생성 토큰을 소모하고 있다.

이에 따라 본 보고서는 저장소 규칙(측정 없는 변경 금지)을 준수하는 8개의 「빼기」 개선 아이디어를 도출하고 각각의 대상 지점, 제외 대상, 기대 효과, 실측 검증 방법 및 잠재 위험을 제시한다.

---

## 1. 원칙 요약

`src/web-sources.md`에 기재된 1차 출처 원칙만을 정리한 요약이다. 웹 외부 지식은 일절 덧붙이지 않았다.

### S1. Anthropic Engineering — "Effective context engineering for AI agents" (2025-09-29)
`src/web-sources.md:6-15`
- **주의 예산 (attention budget)**: 새 토큰이 컨텍스트에 들어올 때마다 에이전트의 주의 예산이 일정량 소모된다 (`src/web-sources.md:8`).
- **컨텍스트 부패 (context rot)**: 컨텍스트 토큰이 증가할수록 정보 회수(retrieval) 정확도가 떨어진다 (`src/web-sources.md:9`).
- **목표**: 원하는 결과를 가져올 확률을 극대화하는 가장 작고 고신호인 토큰 집합(smallest set of high-signal tokens)을 찾는 것이다 (`src/web-sources.md:10`).
- **시스템 프롬프트 고도 (altitude)**: 쉽게 깨지는 하드코딩된 규칙 나열과 너무 막연한 지침 사이의 최적 균형을 유지해야 한다 (`src/web-sources.md:11`).
- **도구 집합**: 기능 중복이 최소화된 도구 세트를 제공해야 한다 (`src/web-sources.md:12`).
- **예시 제공**: 온갖 엣지 케이스 규칙을 나열하는 대신 소수의 대표 예시를 제공하는 것이 효과적이다 (`src/web-sources.md:13`).
- **Just-in-time 검색**: 파일 경로나 질의 식별자처럼 가벼운 포인터만 유지하고, 실제 내용은 필요한 순간에 읽는다 (`src/web-sources.md:14`).
- **처방 기법**: 압축(compaction), 구조화 메모(컨텍스트 밖 노트), 서브 에이전트(깨끗한 컨텍스트에서 작업 후 요약만 반환)를 활용한다 (`src/web-sources.md:15`).

### S2. Chroma Technical Report — "Context Rot: How Increasing Input Tokens Impacts LLM Performance" (2025-07-14)
`src/web-sources.md:17-23`
- **입력 길이에 따른 불안정**: 18개 모델 대상 실험 결과, 입력 길이만 늘어나도 단순한 과제에서조차 모델 성능이 불안정해진다 (`src/web-sources.md:19`).
- **방해 문단 (distractor)의 치명성**: 의미가 비슷한 방해 문단이 단 하나만 있어도 모델 정확도가 떨어지며, 네 개가 되면 하락 폭이 더욱 커진다 (`src/web-sources.md:20`).
- **질문-정답 의미 유사도 영향**: 질문과 정답 문단의 의미 유사도가 낮을수록, 입력 길이가 늘어남에 따라 성능이 더 급격하게 무너진다 (`src/web-sources.md:21`).
- **문맥 순서의 영향**: 논리적으로 정연하게 이어진 문서보다 오히려 무작위로 섞은(shuffled) 문맥이 더 좋은 결과를 보였다(저자도 반직관적이라 평가) (`src/web-sources.md:22`).
- **핵심 결론**: 관련 정보가 컨텍스트 안에 단순히 '존재하는 것'만으로는 충분하지 않으며, '어떻게 제시하느냐'가 성능을 좌우한다 (`src/web-sources.md:23`).

### S3. ETH Zurich / LogicStar — "Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?" (arXiv:2602.11988, 2026-02-12)
`src/web-sources.md:25-30`
- **저장소 수준 컨텍스트 파일의 비효율**: AGENTS.md, CLAUDE.md 같은 저장소 전역 컨텍스트 파일은 코딩 에이전트의 과제 성공률을 전반적으로 향상시키지 못했으며, 오히려 추론 비용을 평균 20% 이상 증가시켰다 (`src/web-sources.md:27`).
- **지침 vs 개요**: 에이전트는 파일 내의 구체적 지시사항은 잘 따랐으나, 저장소 전반에 대한 개요(overview) 정보는 과제 해결에 도움이 되지 않았다 (LLM 생성 파일, 개발자 작성 파일 모두 동일 경향) (`src/web-sources.md:28`).
- **권고 사항**: 컨텍스트 파일은 '비표준 코딩 관례'를 명시하는 용도에 유용하며, 성능 개선 시도는 실배포 전에 엄밀하게 평가되어야 한다 (`src/web-sources.md:29`).
- **[확인 불가] 세부 수치**: 2차 블로그에서 인용되던 SWE-bench Lite 수치 등은 원문에서 확인하지 못했다 (`src/web-sources.md:30`).

### S4. Drew Breunig — "How to Fix Your Context" (2025-06-26) / "How Long Contexts Fail"
`src/web-sources.md:32-35`
- **컨텍스트 실패 4대 유형**:
  1. *오염 (poisoning)*: 과거 오류 내용이 컨텍스트에 남아 반복 참조됨 (`src/web-sources.md:34`).
  2. *산만 (distraction)*: 모델 내부의 학습 지식보다 컨텍스트에 주어진 불필요한 정보에 과도하게 의존함 (`src/web-sources.md:34`).
  3. *혼동 (confusion)*: 불필요하거나 모호한 정보가 저품질 답변을 유도함 (`src/web-sources.md:34`).
  4. *충돌 (clash)*: 뒤에 주어지는 정보가 앞선 정보와 모순을 일으킴 (`src/web-sources.md:34`).
- **6대 처방**: RAG 활용, 도구 로드아웃(작업별 필요 도구만 탑재; 30개 초과 시 설명 중복 위험 인용), 격리(quarantine, 하위 작업을 깨끗한 컨텍스트로 격리), 가지치기(pruning), 요약, 외부 저장(offloading) (`src/web-sources.md:35`).

---

## 2. 지점별 분석

저장소 내에서 LLM으로 컨텍스트를 주입하는 4대 지점을 분석한다.

### 지점 1: 자동 로드 문서 (`src/CLAUDE.md`, `src/AGENTS.md`, `src/machines/sim-desktop.md`)
1. **무엇을 싣는가**:
   - `src/CLAUDE.md` (402줄): 인덱스 선언(`src/CLAUDE.md:17`), 세션 시작 필수 문서 읽기 지침(`src/CLAUDE.md:45-49`), 인수인계 및 지휘자 교대(`src/CLAUDE.md:31-41`), 닫힌 마일스톤(M1~M6)과 함정·교훈 목록(`src/CLAUDE.md:50-91`), 정본 7단계 토폴로지 및 오인용 반성 내력(`src/CLAUDE.md:59-73`), 4대 게이트(`src/CLAUDE.md:257-285`), 긴 셸 스크립트 테스트 집계문(`src/CLAUDE.md:321-356`), 운영 명령 모음(`src/CLAUDE.md:363-393`).
   - `src/AGENTS.md` (117줄): 세션 시작 읽을 문서(`src/AGENTS.md:8-16`), 절대 놓치면 안 되는 9개 절대 규칙(`src/AGENTS.md:19-35`), 등록된 스킬 우회 금지 지침(`src/AGENTS.md:38-50`), Codex용 RAG·경로 2단계 확인 규칙(`src/AGENTS.md:51-73`), 인프라 RAG 검색 시작 규칙(`src/AGENTS.md:74-80`), 작업 환경 및 CLI 실행법(`src/AGENTS.md:82-117`).
   - `src/machines/sim-desktop.md` (523줄): 머신 역할 및 인벤토리 표(`src/machines/sim-desktop.md:15-26, 403-412`), 지휘자 교대(`src/machines/sim-desktop.md:32-40`), 마일스톤 및 닫힌 마일스톤 교훈(`src/machines/sim-desktop.md:52-64`), 정본 7단계 전 과정 상세 기술(`src/machines/sim-desktop.md:66-195`), 백틱 셸 실행 함정 방어(`src/machines/sim-desktop.md:487-491`), 서비스 포트 및 NOPASSWD 목록(`src/machines/sim-desktop.md:475-486`).
2. **불필요하거나 중복이거나 낡았을 가능성이 있는 것**:
   - *파일 간 대규모 중복*: `src/AGENTS.md:30-32`는 "홈 진입 문서와 중복이다 — 일부러 그렇다. 두 진입 파일은 각각 자족적이어야 한다"고 명시하고 있으나, 이로 인해 지휘자 교대(`ax-handoff`), 인프라 변경 시 RAG 시작 규칙(`src/CLAUDE.md:23-29`, `src/AGENTS.md:74-80`, `src/machines/sim-desktop.md:44-50`), 기계 역할 및 IP 인벤토리가 세 문서에 완전히 중복 기재되어 매 세션마다 2중, 3중으로 토큰을 소모한다.
   - *과거의 오인용·삭제된 모듈 내러티브(역사적 사실)*: "one writer" 오인용 정정 내력(`src/CLAUDE.md:65-71`, `src/machines/sim-desktop.md:71-83`), 이미 1,000줄과 테스트 131건이 삭제 완료된 `integrate.py`의 과거 내력(`src/CLAUDE.md:133-134`, `src/machines/sim-desktop.md:85-87`), 이미 철거된 `carry.py`에 대한 경고(`src/CLAUDE.md:163-165`), 닫힌 M1~M6 마일스톤의 실패 교훈(`src/CLAUDE.md:50-56`, `src/machines/sim-desktop.md:52-64`)은 현재 실행할 행동 지침이 아님에도 인라인에 길게 남아 있다.
   - *도구 미사용 시 불필요한 운영 스크립트*: `CLAUDE.md:337-349`의 셸 스크립트 테스트 카운터는 에이전트가 호출할 필요가 없는 조사용 스크립트임에도 인라인에 포함되어 있다 (`src/CLAUDE.md:330`).
3. **원칙과의 대응**:
   - **S1 (Anthropic)**: 주의 예산 소모(`src/web-sources.md:8`) 및 Just-in-time 원칙 위배(`src/web-sources.md:14`). 필요 시 `docs/`나 `reports/`를 열람하게 하는 대신 세션 시작 시 1,000줄 이상의 문서를 강제 로드한다.
   - **S2 (Chroma)**: 과거의 잘못된 설계와 오인용 내력은 현재 유효한 규칙과 의미적으로 유사하지만 모순되거나 쓸모없는 방해 문단(distractor)으로 작동하여 Context Rot을 유발한다 (`src/web-sources.md:20-21`).
   - **S3 (ETH Zurich)**: 저장소 전반의 개요(overview)는 과제 해결에 도움이 되지 않으며 추론 비용만 20% 이상 증가시킨다 (`src/web-sources.md:27-28`). 비표준 코딩 관례만 남겨야 한다는 권고에 반한다 (`src/web-sources.md:29`).
   - **S4 (Drew Breunig)**: 폐기된 과거 설계와 현재 7단계 정본이 공존함으로써 충돌(clash) 및 혼동(confusion)의 위험을 초래한다 (`src/web-sources.md:34`).

---

### 지점 2: 워커 파견 지시문 (`src/master/work/runner.py`, `src/master/work/infer.py`, `src/master/work/lanes.py`)
1. **무엇을 싣는가**:
   - `src/master/work/runner.py`: 지시문 템플릿 `INSTRUCTION` (`src/master/work/runner.py:83-107`) 및 마스터 저장소 자체 마운트 시 추가되는 `SELF_REPO_NOTE` (`src/master/work/runner.py:115-119`).
     - 내용: `ax-work` 스킬 읽기 경로, 승인 대기/계획 제시 금지, `[DOC]` 및 `[PSEUDO]` 주석 읽기, 대상 파일 목록, 자체 작성 지시 및 agy 연구 위임 조건, agy 번호 매긴 JSON 파일 저장 규칙(`.agy-work/out/`), 위임 실패 시 백엔드 재시도 및 중단 규칙, git/UE5 빌드/Python 서버 및 테스트 금지, 마지막 줄 `RESULT: DONE/BLOCKED` 출력 규약.
   - `src/master/work/infer.py`: `INFER_INSTRUCTION` (`src/master/work/infer.py:68-85`).
     - 내용: `ax-infer` 스킬 준수 명시, 대상 파일 목록, `[DOC]` 주석 읽기, `[PSEUDO]` 마커 삭제 및 본문 채우기, `[DOC]/[STATE]/[BIND]/[REPLICATED]` 보존, 헤더 동결, git/소스 편집 금지, `./{work}/{task}/{resp}` 경로에 `=== FILE: <path> ===` 블록으로 작성, `RESPONSE: n / RESULT: DONE` 출력 규약.
   - `src/master/work/lanes.py`:
     - C++용 `INSTRUCTION` (`src/master/work/lanes.py:78-88`) 및 Python용 `INSTRUCTION_PY` (`src/master/work/lanes.py:95-109`).
     - `build_prompt`: 지시문 + 구현 대상 파일 목록 + 각 골조 파일의 전체 내용(`=== FILE: {rel} ===\n{skeleton[rel]}`) 결합 주입 (`src/master/work/lanes.py:167-174`).
2. **불필요하거나 중복이거나 낡았을 가능성이 있는 것**:
   - *스킬 문서와 명령줄 프롬프트의 이중 중복*: 워커의 `.agents/skills/ax-work/SKILL.md`에 이미 위임 규칙과 금지 사항이 정의되어 있음에도, `runner.py:83-107`의 `INSTRUCTION`에 agy 위임 세부 절차(raw JSON 저장 디렉터리, 번호 매기기, 백엔드 순서 재시도, 종료 코드 기록)와 온갖 금지령을 장황하게 나열하고 있다.
   - *워커 환경 오염에 대응하기 위한 땜질 지침*: 마스터 저장소 체크아웃의 `AGENTS.md`/`CLAUDE.md`가 무인 워커의 판단을 왜곡(검색 0건을 에러로 오판)하자 이를 덮기 위해 `SELF_REPO_NOTE`라는 문장을 추가로 주입하는 구조다 (`src/master/work/runner.py:109-119`).
   - *골조 전체 텍스트 주입*: `lanes.py`의 `build_prompt`는 채워야 할 대상 함수뿐 아니라 변경 없는 수백 줄의 클래스 전체 골조(주석, 멤버 변수, 다른 함수 선언 등)를 통째로 문자열 결합하여 전송한다 (`src/master/work/lanes.py:171-174`).
3. **원칙과의 대응**:
   - **S1 (Anthropic)**: 시스템 프롬프트 고도(altitude) 조절 실패 (`src/web-sources.md:11`). 스킬 문서에 둘 내용과 프롬프트에 둘 내용이 분리되지 않고 엣지 케이스 규칙이 나열되어 주의 예산을 낭비한다 (`src/web-sources.md:8, 13`).
   - **S2 (Chroma)**: 긴 지시문과 세부 위임 예외 처리 규정은 코드 구현이라는 주 태스크에 대해 방해 문단(distractor)으로 작용하여 정확도를 저하시킨다 (`src/web-sources.md:20`).
   - **S4 (Drew Breunig)**: 산만(distraction) 및 혼동(confusion) (`src/web-sources.md:34`). 지나치게 많은 금지 규칙("UE5 빌드 금지", "Python 서버 실행 금지", "git 금지", "agy raw JSON 저장")이 모델의 내부 코딩 지식 집중을 방해한다.

---

### 지점 3: RAG 검색 조립 (`src/master/context_search/search.py`, `src/master/context_search/expand.py`)
1. **무엇을 싣는가**:
   - `src/master/context_search/search.py`:
     - 원본 질의 수신 (`src/master/context_search/search.py:160`).
     - 시소러스 질의 확장 `expand_for` 호출 (`src/master/context_search/search.py:176-178`).
     - 대괄호 필터링 `focus()`: 질의에 `[...]`가 있으면 괄호 안 내용만 추출하고 나머지를 버림 (`src/master/context_search/search.py:97-104, 179`).
     - 벡터 검색 및 BM25 검색 후보 각각 `pool`개(기본 `limit * 3 = 24`, 최소 10) 호출 (`src/master/context_search/search.py:180-184`).
     - 각 문서당 발췌(excerpt) 400자 수집 (`src/master/context_search/search.py:161`).
     - RRF 순위 융합(`fuse`) 후 상위 `limit`(기본 8개) 문서를 반환 (`src/master/context_search/search.py:107-143, 184`).
   - `src/master/context_search/expand.py`:
     - 질의에 별칭이 부분 문자열로 매칭되면 원본 질의 뒤에 공백으로 클래스명을 최대 6개(`MAX_EXPAND = 6`) 덧붙임 (`src/master/context_search/expand.py:34, 60-100`).
     - 원본 질의를 지우지 않고 보존 (`src/master/context_search/expand.py:65-67, 99`).
2. **불필요하거나 중복이거나 낡았을 가능성이 있는 것**:
   - *대괄호 없는 질의의 불용어 잔재 및 신호 희석*: 사용자가 대괄호를 쓰지 않은 일반 질의의 경우, `focus()`를 거치지 않으므로 "에서", "부분이", "어디야" 같은 조사·불용어가 그대로 남는다 (`src/master/context_search/search.py:85-93`). 여기에 `expand.py`가 최대 6개의 클래스명을 뒤에 덧붙이면 질의가 장황해져 BM25 키워드 밀도가 희석되고 벡터 임베딩 품질이 저하된다.
   - *과도한 RRF 후보 풀(pool) 크기와 방해 문서 유입*: 최종 8개를 취하기 위해 양 채널에서 각각 24개씩 총 48개 후보를 끌어오는데 (`src/master/context_search/search.py:180`), 연관성이 낮은 문서나 유사한 방해 문단이 상위 8개 안으로 융합되어 들어올 가능성이 열려 있다.
3. **원칙과의 대응**:
   - **S1 (Anthropic)**: "가장 작고 고신호인 토큰 집합(smallest set of high-signal tokens)" 원칙 위배 (`src/web-sources.md:10`). 불용어와 과다하게 확장된 별칭이 신호 대 잡음비(SNR)를 악화시킨다.
   - **S2 (Chroma)**: 질문과 정답 간 유사도가 떨어질수록 컨텍스트 길이에 따라 성능이 급락한다 (`src/web-sources.md:21`). 의미가 유사한 방해 문단(distractor)이 유입될 경우 검색 기반 생성의 정확도가 떨어진다 (`src/web-sources.md:20`).
   - **S4 (Drew Breunig)**: 오염(poisoning) 및 산만(distraction) (`src/web-sources.md:34`). 부적절한 검색 결과가 후속 프롬프트에 주입되어 모델의 추론을 왜곡할 위험이 있다.

---

### 지점 4: 합성·문서 프롬프트 (`src/master/context_synth/prompt.py`, `src/master/doc_sync/draft.py`)
1. **무엇을 싣는가**:
   - `src/master/context_synth/prompt.py`:
     - `FORMAT` 템플릿: frontmatter 예시, 요약 지침, tags 작성 규칙, related_classes 작성 규칙, 사실 관계 규칙 등 약 60줄의 프롬프트 (`src/master/context_synth/prompt.py:71-133`).
     - `Grounding.render()`: 정의된 클래스 목록 최대 10개(`src/master/context_synth/prompt.py:155-159`), 상속 사슬 최대 10개(`src/master/context_synth/prompt.py:160-163`), 형제 클래스 최대 10개(`src/master/context_synth/prompt.py:164-167`), include 내부 파일 최대 10개(`src/master/context_synth/prompt.py:168-170`), dependents(이 파일을 include하는 파일) 최대 10개(`src/master/context_synth/prompt.py:171-175`), 관련 파일 RAG 컨텍스트 최대 3개 문서 × 발췌 1500자 = 최대 4,500자(`src/master/context_synth/prompt.py:49-59, 176-179`), 도메인 규범(`src/master/context_synth/prompt.py:180-186`).
     - 기존 개발자 코멘트 (`src/master/context_synth/prompt.py:212-219`).
     - 소스 코드 본문: 로컬 레인은 4,000자 상한, 상용 레인은 무제한 (`src/master/context_synth/prompt.py:40, 207-208`).
   - `src/master/doc_sync/draft.py`:
     - 대상 문서의 메타데이터와 **전체 기존 본문(`before`)** (`src/master/doc_sync/draft.py:28-29`).
     - 수집된 모든 근거 파일들의 **줄 번호가 붙은 전체 텍스트(`evidence`)** (`src/master/doc_sync/draft.py:20-27, 41`).
     - 지시문: 최신화 지침, 코드 실행 금지, JSON 객체 반환, edits 형식 안내 등 (`src/master/doc_sync/draft.py:30-42`).
2. **불필요하거나 중복이거나 낡았을 가능성이 있는 것**:
   - *부재하는 근거에 대한 메타 텍스트 주입*: `prompt.py`는 도메인 규범이 없으면 `[도메인 규범]\n _없음 — 마일스톤 2 의 중 1.3 이 만든다..._`라는 문장을 매번 주입한다 (`src/master/context_synth/prompt.py:183-186`). 없는 근거를 설명하기 위한 토큰 낭비다.
   - *가짜 예시 클래스명으로 인한 변명 지침 추가*: `FORMAT`에 `UExampleComponent`, `AExampleActor`라는 가짜 클래스 예시가 들어가 있어 (`src/master/context_synth/prompt.py:81-82`), "위 형식의 두 줄은 모양만 보여 주는 예시다... 이름을 그대로 쓰지 말고"라는 경고 지침을 추가로 실어야 하는 악순환이 발생한다 (`src/master/context_synth/prompt.py:106-108`).
   - *과도하게 확장된 RAG 발췌 길이*: 상용 토큰 비용이 들지 않는다는 이유로 원본 400자에서 1500자로 올렸다 (`src/master/context_synth/prompt.py:52-59`). 관련 문서 3개면 발췌만 4,500자에 달해 실제 코드 본문(4,000자 상한)보다 방대하다.
   - *doc_sync의 풀 텍스트 덤프*: `draft.py`는 변경이 필요한 좁은 절(section)뿐 아니라 문서 전체 본문(`before`)과 근거 파일 전체 텍스트(`evidence`)를 무조건 전송한다 (`src/master/doc_sync/draft.py:28-42`). 이로 인해 단일 문서 호출에 캐시 생성 토큰이 34,423~95,145개나 소모된다 (`src/web-sources.md:38`).
3. **원칙과의 대응**:
   - **S1 (Anthropic)**: 주의 예산 소모 및 컨텍스트 부패 (`src/web-sources.md:8-9`). Just-in-time 검색 대신 전체 텍스트를 무차별 덤프하고, 소수의 대표 예시 대신 오독 방지용 지침을 덧대는 구조다 (`src/web-sources.md:13-14`).
   - **S2 (Chroma)**: 4,500자에 달하는 관련 파일 발췌와 방대한 dependents 목록은 주 대상 파일 분석에 대해 방해 문단(distractor)으로 작동하여 모델 성능을 불안정하게 만든다 (`src/web-sources.md:19-20`).
   - **S4 (Drew Breunig)**: 오염(poisoning) 및 산만(distraction) (`src/web-sources.md:34`). 예시 클래스명이 환각을 유발하고, 불필요한 전체 본문 주입이 주의 집중을 방해한다. 가지치기(pruning)와 외부 저장(offloading)이 절실한 지점이다 (`src/web-sources.md:35`).

---

## 3. 개선 아이디어

저장소 규칙("개선은 실측이 앞선다 — 측정 없이 손대지 않는다", `src/CLAUDE.md:53-54, 87-88`)에 따라 구체적인 측정 방법을 포함한 8개의 「빼기」 개선 아이디어를 제안한다.

### 아이디어 1: 자동 로드 문서에서 역사적 내러티브 및 삭제 모듈 기록 가지치기
- **대상 지점**: 자동 로드 문서 (`src/CLAUDE.md`, `src/machines/sim-desktop.md`)
- **무엇을 빼거나 늦게 싣는가**:
  - 이미 종결된 M1~M6 마일스톤의 세부 기록 및 과거 실패 회고 (`src/CLAUDE.md:50-56`, `src/machines/sim-desktop.md:52-64`).
  - "one writer" 오인용 정정 내러티브 (`src/CLAUDE.md:65-71`, `src/machines/sim-desktop.md:71-84`).
  - 이미 삭제된 `integrate.py`와 철거된 `carry.py`의 과거 역사 서술 (`src/CLAUDE.md:133-134, 163-165`, `src/machines/sim-desktop.md:85-87`).
  - 조사용 셸 스크립트 테스트 집계 루프문 (`src/CLAUDE.md:337-349`).
  - 이 내용들은 인라인에서 제외하고 `docs/settled-decisions.md`나 milestone 회고 문서로 외부 저장(offloading)한다.
- **기대 효과**: 자동 로드 문서 크기 30~40% 감소(수천 토큰 절감), 초기 주의 예산(budget) 보존 (`src/web-sources.md:8`), 폐기된 과거 설계에 대한 모델의 혼동 및 충돌 방지 (`src/web-sources.md:34`).
- **측정 방법**:
  - 1) 파일 라인 수 및 문자/토큰 수 측정 (`wc -l`, `wc -c`, tiktoken 계측).
  - 2) 대화 세션 시작 시 Claude/Codex의 초기 입력 토큰 및 캐시 생성 토큰 비교 (`usage.jsonl`).
  - 3) 7단계 파이프라인 및 현재 규칙 관련 프롬프트 10회 질의 시 지침 준수율 비교 (기존 100% 유지 여부).
- **위험**: 모델이 해당 구조가 채택된 역사적 이유를 즉시 알지 못해, 사용자가 과거 구조와 관련된 질문을 할 때 문맥을 놓칠 수 있음 (대응: 필요 시 검색 가능한 문서 경로 링크 유지).

### 아이디어 2: AGENTS.md와 CLAUDE.md 간 중복 서술 제거 및 AGENTS.md 경량화
- **대상 지점**: 자동 로드 문서 (`src/AGENTS.md`, `src/CLAUDE.md`)
- **무엇을 빼거나 늦게 싣는가**:
  - `src/AGENTS.md:30-32`에서 자족성을 이유로 중복 기재했던 내용(지휘자 교대 지침, RAG 인프라 변경 시작 규칙, 머신 인벤토리/역할)을 삭제.
  - `src/AGENTS.md`에는 ETH Zurich 권고(`src/web-sources.md:29`)대로 오직 도구 무관 '비표준 코딩 관례'와 핵심 게이트 포인터만 남기고 30줄 이하로 압축.
- **기대 효과**: Codex 세션 시작 시의 고정 입력 토큰 절감, 저장소 개요 배제로 인한 추론 비용 절감(ETH Zurich 실측 평균 20% 절감 참고, `src/web-sources.md:27`). [검증 불일치] 인용 줄은 「컨텍스트 파일이 비용을 20% 넘게 올렸다」이다 — 빼면 20% 절감된다는 측정은 출처에 없다(추론).
- **측정 방법**:
  - 1) `AGENTS.md` 토큰 수 측정 (117줄 → 30줄 이하).
  - 2) Codex 세션 시작 시 소모 토큰 측정 (`parse_codex_jsonl` 계측).
  - 3) 스킬 우회 금지, 커밋 전 승인 등 필수 규칙 준수율 회귀 테스트 (10회 실행 시 위반 0건 유지 확인).
- **위험**: Codex가 `CLAUDE.md`를 참조하지 않고 `AGENTS.md`만 참조할 때 특정 운영 규칙을 놓칠 위험 (대응: 상세 운영 규칙은 `docs/orchestrator-rules.md`로 일원화하고 해당 경로를 필수 참조하도록 단일화).

### 아이디어 3: 워커 파견 지시문(INSTRUCTION)에서 스킬 중복 지침 및 엣지 케이스 규칙 제거
- **대상 지점**: 워커 파견 지시문 (`src/master/work/runner.py`)
- **무엇을 빼거나 늦게 싣는가**:
  - `src/master/work/runner.py:83-107`의 `INSTRUCTION`에서 `.agents/skills/ax-work/SKILL.md`에 이미 적혀 있는 agy 번호 매긴 JSON 저장 규칙, 백엔드 순서 재시도 엣지 케이스 지침, 장황한 금지령을 삭제.
  - 지시문은 "지정된 브랜치 확인, 골조 주석(`[DOC]`, `[PSEUDO]`) 구현, `RESULT: DONE/BLOCKED` 출력"의 핵심만 남김.
- **기대 효과**: 워커 파견 명령줄 프롬프트 길이 60% 이상 단축, 프롬프트 고도(altitude) 최적화 (`src/web-sources.md:11`), 모델의 주의 분산(distraction) 방지 (`src/web-sources.md:34`).
- **측정 방법**:
  - 1) `INSTRUCTION` 포맷 후 바이트/토큰 수 측정.
  - 2) `master/test_runner.py` 단위 테스트 통과 확인.
  - 3) 실제 워커 파견 테스트 10회 수행 시 층1 검증 통과율(`[PSEUDO]` 잔재 0) 및 정상 종료(`RESULT: DONE`) 비율 비교.
- **위험**: 워커가 `SKILL.md`를 열어보지 않고 곧바로 작업을 진행할 경우 세부 위임 포맷을 어길 위험 (대응: `runner.py:84`의 스킬 파일 열람 지침은 유지).

### 아이디어 4: 본문 작성 레인(lanes.py)의 골조 프롬프트 슬라이싱 (전체 파일 덤프 배제)
- **대상 지점**: 워커 파견 지시문 / 본문 작성 레인 (`src/master/work/lanes.py`)
- **무엇을 빼거나 늦게 싣는가**:
  - `build_prompt`(`src/master/work/lanes.py:167-174`)에서 변경 대상이 아닌 멤버 함수 본문이나 무관한 전체 골조 주석을 통째로 싣는 대신, 헤더의 클래스 선언 인터페이스와 `[PSEUDO]` 마커가 포함된 대상 함수 블록만 슬라이싱하여 주입.
- **기대 효과**: 본문 작성 프롬프트 토큰 대폭 절감, 로컬 14B 모델의 KV 캐시 메모리 압박 완화 (BC-250 보드 먹통 방지, `src/master/context_synth/prompt.py:31-33`), 모델의 불필요 코드 출력 및 markdown 펜스 생성 결함 감소.
- **측정 방법**:
  - 1) 골조 1개당 프롬프트 글자 수 및 토큰 수 전후 비교.
  - 2) `run_one` 실행 시간(초) 및 층1 통과율(헤더 동결 준수, 반환값 누락 없음) 측정.
  - 3) 로컬 14B 모델 실행 시 `.h`/`.cpp` 누락 발생 여부 비교 (`src/master/work/lanes.py:46-48`).
- **위험**: 함수 구현 시 클래스 내 다른 private 헬퍼나 멤버 변수의 선언 맥락이 부족하여 컴파일 에러 발생 가능 (대응: 헤더 선언부는 온전히 보존하고 구현 파일(`.cpp`)의 불필요한 기존 블록만 스텁화).

### 아이디어 5: RAG 시소러스 확장 시 불용어 제거 및 확장 토큰 상한 축소
- **대상 지점**: RAG 검색 조립 (`src/master/context_search/search.py`, `src/master/context_search/expand.py`)
- **무엇을 빼거나 늦게 싣는가**:
  - `expand.py`의 `MAX_EXPAND = 6`(`src/master/context_search/expand.py:34`) 상한을 2~3개로 축소.
  - 대괄호가 없는 질의에서도 "에서", "부분이", "어디야" 같은 불용어를 제거하는 간단한 토큰 필터링을 `focus()` 단계에 적용 (`src/master/context_search/search.py:85-93`).
- **기대 효과**: 질의의 고신호 토큰 비율(SNR) 상승 (`src/web-sources.md:10`), 의미가 유사하지만 무관한 방해 문서(distractor)의 검색 결과 유입 방지 (`src/web-sources.md:20`), BM25 및 벡터 순위 정확도 개선.
- **측정 방법**:
  - 1) **저장소 M2 규칙 준수**: "정답 집합 없이 손대지 않는다" (`src/CLAUDE.md:53-54, 87-88`)에 따라 기존 프로젝트의 질의-정답 문서 쌍 20개를 먼저 구축.
  - 2) 기존 쿼리 확장 방식과 축소/불용어 제거 방식 간의 Recall@8 및 MRR(Mean Reciprocal Rank) 측정.
  - 3) `search_log`에 기록되는 검색 소요 시간(`duration_ms`) 비교.
- **위험**: 확장 토큰 수를 줄였을 때 실제 필요한 연관 클래스가 질의에서 누락되어 검색되지 않을 위험 (Recall 저하) (대응: 반드시 구축된 정답 집합으로 평가 후 적용).

### 아이디어 6: context_synth 프롬프트에서 도메인 규범 '없음' 메타 안내문 및 가짜 예시 클래스명 제거
- **대상 지점**: 합성·문서 프롬프트 (`src/master/context_synth/prompt.py`)
- **무엇을 빼거나 늦게 싣는가**:
  - 도메인 규범이 없을 때 주입되는 `[도메인 규범]\n _없음 — 마일스톤 2 의 중 1.3 이 만든다..._` 문자열(`src/master/context_synth/prompt.py:183-186`)을 완전히 생략.
  - `FORMAT` 템플릿의 `UExampleComponent`, `AExampleActor` 가짜 클래스 예시(`src/master/context_synth/prompt.py:81-82`)를 구조적 플레이스홀더로 대체하고, 예시 이름을 베끼지 말라는 장황한 경고문(`src/master/context_synth/prompt.py:106-108`)을 삭제.
- **기대 효과**: 프롬프트 토큰 수백 자 절감, 모델이 가짜 클래스명을 요약에 인용하거나 환각하는 Breunig식 오염(poisoning) 및 산만(distraction) 방지 (`src/web-sources.md:34`).
- **측정 방법**:
  - 1) 렌더링된 프롬프트 총 문자 수 측정.
  - 2) 합성된 MD 파일에 가짜 클래스명(`UExampleComponent` 등) 또는 불필요한 메타 주석이 유입되는 빈도 전수 검사 (0건 유지).
  - 3) 합성된 MD의 검증 게이트 통과율 및 소요 시간 측정.
- **위험**: 모델이 frontmatter의 YAML 서식(`related_classes: - ClassName: Path`)을 이해하지 못하고 구문 오류를 일으킬 위험 (대응: tree-sitter 실측 클래스 목록이 이미 프롬프트에 들어가므로 위험은 극히 낮음).

### 아이디어 7: context_synth의 관련 파일 RAG 발췌 길이 롤백 (1500자 → 400~500자)
- **대상 지점**: 합성·문서 프롬프트 (`src/master/context_synth/prompt.py`)
- **무엇을 빼거나 늦게 싣는가**:
  - `RELATED_EXCERPT = 1500`(`src/master/context_synth/prompt.py:59`)으로 상향되었던 발췌 길이를 원본 수준인 400~500자로 축소.
- **기대 효과**: 프롬프트당 최대 3,000자(관련 문서 3개 × 1,000자) 이상의 토큰 즉시 절감, 로컬 모델의 컨텍스트 창 압박 완화, 방해 문단(distractor) 제거를 통한 주 소스 코드 집중도 향상 (`src/web-sources.md:19-20`).
- **측정 방법**:
  - 1) 발췌 1500자 vs 500자 설정 시 프롬프트 크기 및 BC-250 노드의 GPU 메모리/KV 캐시 사용량 측정.
  - 2) 생성된 MD의 `related_classes` 식별 정확도(실제 의존 관계 클래스 반영률) 20개 파일 대상 비교 평가.
  - 3) 합성 소요 시간 비교.
- **위험**: 관련 파일의 핵심 함수 시그니처가 500자 밖으로 잘려 나가 협력 클래스 누락이 발생할 위험 (대응: 발췌 500자 내에 헤더 선언부가 우선 오도록 발췌 로직 점검).

### 아이디어 8: doc_sync에서 문서 전체 본문 덤프 배제 및 대상 절(Section) 기반 프롬프팅
- **대상 지점**: 합성·문서 프롬프트 (`src/master/doc_sync/draft.py`)
- **무엇을 빼거나 늦게 싣는가**:
  - `_prompt(document)`(`src/master/doc_sync/draft.py:17-43`)에서 변경 대상 문서 전체(`before`)와 모든 근거 파일의 전체 줄 텍스트(`evidence`)를 무조건 전송하는 대신, 최신화가 필요한 특정 섹션과 직접 매칭된 근거 라인만 슬라이싱하여 전송.
- **기대 효과**: doc_sync 1회 호출당 소모되던 34,423~95,145 캐시 생성 토큰(`src/web-sources.md:38`)의 70% 이상 획기적 절감, 변경 불필요한 기존 역사나 지침을 모델이 임의로 훼손(오염/충돌)하는 사고 방지 (`src/web-sources.md:34`).
- **측정 방법**:
  - 1) `usage_log`(`usage.jsonl`)에 기록되는 `input_tokens`, `cache_creation_input_tokens`, 소요 시간 및 비용($) 전후 비교.
  - 2) 생성된 `edits`의 정확성(파싱 성공률 및 `before` 단일 매칭 여부) 검증.
  - 3) `doc_sync` 단위 테스트 통과 확인.
- **위험**: 문서의 앞뒤 맥락이 잘려 나가 섹션 간 어조나 상호 참조가 어색해질 위험 (대응: 섹션 전후 1~2개 헤더 수준의 개요 컨텍스트만 최소한으로 제공).

---

## 근거 목록

본 보고서에서 인용한 파일 경로 및 줄 번호 정본 목록이다 (링크 없이 일반 텍스트 표기):

- **웹 출처 및 실측 원칙**:
  - `src/web-sources.md:6-15` (Anthropic Engineering 원칙: 주의 예산, 컨텍스트 부패, 시스템 프롬프트 고도, JIT)
  - `src/web-sources.md:17-23` (Chroma Technical Report: 입력 길이 불안정성, 방해 문단 distractor 영향)
  - `src/web-sources.md:25-30` (ETH Zurich / LogicStar: 저장소 컨텍스트 파일의 추론 비용 20% 증가 및 개요 비효율)
  - `src/web-sources.md:32-35` (Drew Breunig: 컨텍스트 4대 실패 유형 및 6대 처방)
  - `src/web-sources.md:37-40` (저장소 실측: doc_sync 호출 시 캐시 생성 토큰 34,423~95,145, 자동 로드가 본문의 13배)

- **자동 로드 문서**:
  - `src/CLAUDE.md:17-19` (인덱스 선언 및 파일 길이가 세션 고정 비용이라는 경고)
  - `src/CLAUDE.md:23-29` (인프라 변경 시 RAG 시작 규칙)
  - `src/CLAUDE.md:31-41` (지휘자 교대 및 워커 지휘자 모드)
  - `src/CLAUDE.md:50-58` (닫힌 마일스톤 M1~M6 및 열린 마일스톤 M7)
  - `src/CLAUDE.md:59-73` (정본 7단계 토폴로지 및 오인용 반성 내력)
  - `src/CLAUDE.md:133-134` (integrate.py 삭제 내력)
  - `src/CLAUDE.md:163-165` (carry.py 철거 내력)
  - `src/CLAUDE.md:257-285` (4대 게이트 및 레인 체인 실측)
  - `src/CLAUDE.md:321-356` (통합 검사 및 셸 스크립트 테스트 카운터 루프)
  - `src/CLAUDE.md:363-393` (운영 명령 및 데몬 상태 확인)
  - `src/CLAUDE.md:397-402` (원격 저장소 및 복제본 동기화)
  - `src/AGENTS.md:8-16` (세션 시작 필수 문서 열람)
  - `src/AGENTS.md:19-35` (절대 규칙 9개 및 홈 진입 문서와의 의도적 중복 서술)
  - `src/AGENTS.md:38-50` (등록된 스킬 우회 금지)
  - `src/AGENTS.md:51-73` (Codex RAG 및 2단계 경로 확인 지침)
  - `src/AGENTS.md:74-80` (인프라 변경 시 RAG 시작 규칙 중복)
  - `src/AGENTS.md:82-117` (환경 변수, CLI 배달, 모드 전환 규칙)
  - `src/machines/sim-desktop.md:3-5` (인덱스 선언 및 세션 고정 비용 경고)
  - `src/machines/sim-desktop.md:21-25` (마스터와 워크숍 역할 구분)
  - `src/machines/sim-desktop.md:32-40` (지휘자 교대 인수인계)
  - `src/machines/sim-desktop.md:44-50` (인프라 변경 시 RAG 시작 규칙 중복)
  - `src/machines/sim-desktop.md:52-64` (닫힌 마일스톤 M1~M6 및 교훈)
  - `src/machines/sim-desktop.md:66-88` (정본 7단계 및 오인용 정정)
  - `src/machines/sim-desktop.md:97-195` (정본 7단계 상세 내역)
  - `src/machines/sim-desktop.md:201-210` (자동 경로 명령형 거부 실측)
  - `src/machines/sim-desktop.md:403-412` (머신 인벤토리 표)
  - `src/machines/sim-desktop.md:475-486` (시스템 데몬 재기동 및 NOPASSWD 목록)
  - `src/machines/sim-desktop.md:487-491` (백틱 셸 실행 함정)

- **워커 파견 지시문**:
  - `src/master/work/runner.py:83-107` (워커 파견 INSTRUCTION 템플릿)
  - `src/master/work/runner.py:109-119` (SELF_PROJECT 및 SELF_REPO_NOTE 주입부)
  - `src/master/work/runner.py:680-684` (worker_command 프롬프트 포맷팅)
  - `src/master/work/infer.py:68-85` (INFER_INSTRUCTION 지시문)
  - `src/master/work/lanes.py:73` (DEFAULT_LANES 순서)
  - `src/master/work/lanes.py:78-88` (UE5 C++ INSTRUCTION)
  - `src/master/work/lanes.py:95-109` (Python INSTRUCTION_PY)
  - `src/master/work/lanes.py:167-174` (build_prompt 전체 파일 골조 결합부)

- **RAG 검색 조립**:
  - `src/master/context_search/search.py:85-93` (대괄호 토큰 필터링의 불용어 배제 효과 실측)
  - `src/master/context_search/search.py:97-104` (focus 함수)
  - `src/master/context_search/search.py:107-143` (fuse RRF 랭킹 융합)
  - `src/master/context_search/search.py:160-198` (ContextSearch.search 메서드 및 pool 크기)
  - `src/master/context_search/expand.py:33-34` (MIN_TERM = 2, MAX_EXPAND = 6)
  - `src/master/context_search/expand.py:60-100` (expand 함수 및 클래스명 덧붙이기)

- **합성·문서 프롬프트**:
  - `src/master/context_synth/prompt.py:30-40` (CONTENT_LIMIT 상한 및 로컬/상용 분기)
  - `src/master/context_synth/prompt.py:44` (GROUNDING_LIMIT = 10)
  - `src/master/context_synth/prompt.py:49-51` (RELATED_LIMIT = 3, RELATED_QUERY_BODY = 200)
  - `src/master/context_synth/prompt.py:59` (RELATED_EXCERPT = 1500)
  - `src/master/context_synth/prompt.py:71-133` (FORMAT 템플릿 및 가짜 클래스 예시)
  - `src/master/context_synth/prompt.py:152-187` (Grounding.render 및 도메인 규범 '없음' 렌더링)
  - `src/master/context_synth/prompt.py:189-221` (build 함수)
  - `src/master/doc_sync/draft.py:17-43` (_prompt 함수 및 전체 본문/근거 결합)
  - `src/master/doc_sync/draft.py:58-98` (_parse 함수 및 edits 검증)
  - `src/master/doc_sync/draft.py:146-167` (generate 함수 및 LLM 호출)

---

## 확인 불가·한계

1. **[확인 불가] 2차 출처 인용 수치의 원문 검증**:
   - `src/web-sources.md:30`에 명시된 바와 같이, ETH Zurich 논문(arXiv:2602.11988)과 관련된 2차 블로그의 세부 수치(SWE-bench Lite -0.5%, 사람 작성 +4% 등)는 원문에서 확인되지 않았으며, 본 보고서 분석에서도 제외하였다.
2. **[추측] claude CLI 자동 로드 메모리의 구성 분해**:
   - `src/web-sources.md:39`에 따르면 `doc_sync`의 claude 레인 호출 시 3만~9만 개에 달하는 캐시 생성 토큰 중 claude CLI 내부 지침과 외부 로드 문서가 각각 몇 토큰씩 차지하는지 정확한 구성 분해는 실측되지 않았으므로 [추측]으로 분류된다.
3. **[확인 불가] 현재 활성화된 세션의 실제 프롬프트 토큰 점유율**:
   - 현재 대화 세션 환경의 실제 프롬프트 구성 토큰 비율은 런타임 검사 도구 호출 없이는 [확인 불가]이며, 본 보고서는 저장소에 커밋되어 있는 정적 소스 코드(`src/`)의 문자열과 상수 정의만을 근거로 분석하였다.
4. **[한계] 정답 집합(Answer Set) 부재에 따른 즉각 수정 금지**:
   - RAG 검색 조립(`search.py`, `expand.py`)의 가중치나 질의 확장 규칙은 저장소 불변 규칙("정답 집합 없이 손대지 않는다", `src/CLAUDE.md:53-54, 87-88`)에 따라 사전 구축된 정답 데이터셋 없이는 임의 수정할 수 없으며, 아이디어 5의 적용에 선행 조건으로 작용한다.
