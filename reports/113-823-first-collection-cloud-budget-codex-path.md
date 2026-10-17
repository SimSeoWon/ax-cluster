# #823 첫 주말 수집 — 상용 LLM 토큰 예산 제거 · codex 탐색 경로 · 이미 해소 후보

2026-10-17 14:00 ~ 15:50 · Claude · 마스터 담당 `codex`·워커 모드 `codex` 미변경.

## 발단 — 첫 수집이 판정 0건

인계 확인 중 #823 첫 주말 수집(10:12, `ax-batch`)을 봤다. `complete:true` 로 끝나 주간 마커까지
찍혔는데 4건(P9~P12)이 전부 `unjudged` 였다. LLM 호출 없이 프롬프트 크기만 재계산해 원인을 갈랐다.

| 항목 | 사유 |
|---|---|
| P9 · P11 | `input_budget` — 추정 비용 35,175 · 41,627 > `TOKEN_BUDGET` 24,000 |
| P12 | `ValueError` — 소스가 `MAX_SOURCE` 24,000자 초과 |
| P10 | 예산 안(21,113) — 체인이 정상 응답, 모델 판정이 unjudged |

비용 = 프롬프트 UTF-8 바이트 + 4096 이라 한글 설명(3바이트/자) + 소스 전문이면 중간 파일도 넘는다.

## 사용자 결정 — 토큰 한도는 로컬 LLM 에만

예산을 없애자면서 내가 「호출 건수 상한 20」「소스 한도 200,000자」를 다시 제안했다. 사용자:
*"토큰에 한도가 있다면 그건 로컬 LLM에 한정된 내용이 맞는거 같아. 왜 자꾸 한도를 두려는거야?"*
상용 호출은 CLI 구독이라 토큰당 비용이 없고(사용량 로그 `cost_usd` 0), 근거 없는 방어적 한도였다.
기억 `no-token-budget-for-cloud-llm` 으로 남겼다.

- `cd4f270` — `dismissal_candidates`: `TOKEN_BUDGET`·`MAX_SOURCE`·`input_budget` 경로 제거, `collect()`
  는 늘 complete. `unjudged` 도 모델 reason 저장. `plan_generator`/`planner`: `PLAN_TOKEN_BUDGET`·
  `token_budget` 매개변수 제거(`tokens_used` 는 기록용 추정치로 유지).
- 플랜의 2,000자 소스 발췌는 **유지**(사용자 결정). 대신 *"2000자 이상의 프롬프트를 보내는 것이 아니라
  어떤 파일을 읽어라는 식으로 오케스트레이션"* → **#825** 로 등록(상용 체인이 고정 SHA 읽기 전용 작업
  트리를 직접 읽게 한다 · 근거 대조는 마스터가 그대로).

## codex 「not a snap cgroup」 — 인증 만료가 아니었다

사용자는 인증 만료를 의심했지만 `codex login status` 는 정상(`Logged in using ChatGPT`)이었다.

- `layer2_verify.py:360` 이 `shutil.which("codex")` 로 찾는데 `ax-batch.service` 에 PATH 가 없어
  systemd 기본 PATH 의 **`/snap/bin/codex`** 가 잡혔다 — 0.114.0 rev34, 발행인 **jcat(jcat-nysasounds)**,
  OpenAI 공식이 아니다. 시스템 서비스 cgroup 에서 snap 실행이 거부된 것이 실패 사유.
- 분산 작업 영향(사용자 질문): 9-20 이후 이 오류는 `ax-batch` 에서만 났다(파견·큐 0건). 워커 모드
  `codex` 는 워커 기계의 codex 를 쓰고, 층2 검증 체인은 `agy → claude` 라 무관했다.
- 처리(사용자 지시): `3446e09` `ax-batch.service` 에 `PATH=/home/sim/.local/bin:…`(ax-followup 과 같은 줄),
  `/etc` 설치 + `daemon-reload` · `snap remove codex` · `/usr/local/bin/codex → ~/.local/bin/codex`
  링크(agy·claude 와 같은 방식). 서비스 기본 PATH 로 `codex-cli 0.162.1` 인식·로그인 확인.
  첫 pkexec 는 인증 창이 닫혀(`Request dismissed`) 재시도 승인 뒤 실행했다.

## 드라이런 → 운영 수집 1회 → P9·P10·P11 applied

- 드라이런(실 트윈·실 체인, 결과는 scratchpad, `D._path` 교체로 운영 json 무접촉): 4건 전부 codex
  판정, 오류 0, 29초, P12 입력 95,994 토큰.
- 운영 수집(사용자 「주말 수집 먼저 진행하자」): `batch.run run --force` 는 다른 배치(주간 플랜)까지
  돌려서 쓰지 않고 `collect()` 만 직접 호출, 주간 마커 무접촉. 25초 · 오류 0. P9·P10·P11 은 모델이
  「이미 수정」, P12 는 유효한 지적(비대화형 SSH codex PATH).
- 코드 대조(현 main `3446e09`): P9 `plan_register.py` 305~315·344~345행, P10 `planner.py` 119행,
  P11 `test_planner.py` 247행~ 실제 본문·`NotImplementedError` 없음·38/38. 원 지적은 #632 골조
  `b111c8a` 대상 리뷰, 본문은 워커 커밋 `7bc489f` 이후. 사용자 승인으로 셋 다 `applied`(플랜 `acted`).

## 이미 해소 후보도 목록에 (`bd49c81`)

프롬프트가 「이미 수정」을 `unjudged` 로 보내 목록에 안 나왔다. 사용자 결정으로 판정 `resolved` 추가 —
candidate 처럼 근거 1~3줄(수정이 보이는 줄)을 원문 대조. `read_results` 행에 `verdict`, 새
`resolved_count`(`count` 는 기각 후보만). 공개 `/reviews`: 「주말 기각 후보 N건 · 이미 해소 후보 M건」
(건수만). 첫 `update` 가 `ax-projects` 옛 코드(12:28 기동) 때문에 check rc=1 → 승인 재기동
(15:40:46) 뒤 rc=0 3/3.

## 아이디어 세 건

위키 [[아이디어수집]] 은 `modularstage` 에 있어 위키 도구(ax-cluster 귀속)가 닿지 않는다(404). #768
선례대로 일감 본문을 정본으로 했고, 사용자도 *"일감 본문으로 충분해, 위키는 그대로 둬"*.

- **#826** Redmine 일감 → 코드 → GenerateProjectFiles → 빌드 → 에디터 컴파일 → Monolith MCP·언리얼
  내장 MCP → 블루프린트까지 결정적 함수 플로우(커맨드-스킬-MCP). 착수 전 확인: 대화형 세션 전제 ·
  두 MCP 기능 범위 실측 · 블루프린트의 결정적 게이트.
- **#827** REA(AI 리버스 엔지니어링 오픈소스) 활용 — 저장소·라이선스·기능 **미확인**으로 기록.
- **#828** 등록 프로젝트의 RAG·저장소를 분석해 다른 프로젝트로 기능 단위 이식. 착수 전: 「기능 단위」
  경계 · 마운트 전용 규칙과 두 프로젝트 동시 취급(예외가 아니라 설계로) · 결정적 판정과 kind 차이.

## 운영 메모

- 전수 검사 3회(커밋마다) — 실패 파일은 매번 기존 2개(`test_mount_gate` · `test_sandbox`, #815)뿐.
  첫 회의 합계 248 은 `Ran N` 형식만 센 내 집계 실수다. 판정은 종료코드로 했다.
- 커밋: `cd4f270` · `3446e09` · `bd49c81`, 셋 다 push·배달 3/3 OK.
- 서비스: `ax-batch.service` 유닛 교체(daemon-reload) · `ax-projects` 15:40:46 재기동.

## 남은 것

- #823: 10-24 주말 회차가 새 코드로 처음 돈다 — `resolved` 판정·화면 문구 실표시 확인 후 종결 판단.
  `/fixes` 인증 응답의 근거 포함은 여전히 검사 없음.
- #825: 착수 시점 미정(착수 시 RAG·원전 확인 먼저).
- P12(비대화형 SSH codex PATH) 미결.
- `ax-dispatch`·`ax-task-queue`·`ax-indexer` 유닛엔 여전히 PATH 가 없다 — 지금은 `/usr/local/bin` 링크로 해결.
- 이전 보고서의 남은 것(#818 · #821 · #815 · #807 · #814 · #363 3단계 · #820)은 그대로.

### 이후 경과

- 같은 날 17:20 까지 버그·개선 #798 · #814 · #799 · #763 을 해결 — [리포트 114](114-bug-batch-798-814-799-763.md).
