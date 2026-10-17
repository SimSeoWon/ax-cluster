# #825 1차 — 상용 체인이 고정 SHA 작업 트리를 직접 읽는다 (기각 후보 수집)

2026-10-17 20:45 ~ 21:15 · Claude · 마스터 담당 `codex`·워커 모드 `codex` 미변경. 구현은 사용자 선택으로
**로컬 서브 에이전트**에 맡겼다. diff·전수·드라이런은 마스터가 직접 대조했다. 범위는 사용자 선택으로
**기각 후보 수집(`dismissal_candidates`)만**이다. `plan_generator`·`recipes_synthesizer`는 바꾸지 않았다.

## 착수 전 — RAG·현행 코드·원전

- RAG: `commercial_chat`을 쓰는 곳은 셋이다(`plan_generator`·`recipes_synthesizer`·`dismissal_candidates`).
  모두 `review_gen.commercial_chat` 하나로 들어간다.
- 현행: 세 백엔드 모두 프롬프트만 넘긴다(`layer2_verify.py`).
  - codex는 빈 임시 디렉터리를 cwd로 잡는다.
  - agy는 BRIEF 디렉터리만 `--add-dir`로 받는다.
  - claude는 cwd를 지정하지 않는다.
  - 그래서 기각 후보 수집이 소스 전문을 JSON에 실었다(P12 95,994 토큰, 보고서 113).
- 원전: `~/AgentTest/mcp/master_orchestrator/common.py:418` `call_cli_llm(prompt, cwd=…)`와
  `llm_tools.py:52·76·126`의 `cwd=repo_path`가 선례다. 원전은 에이전트를 저장소 안에서 돌렸는데,
  이식 과정에서 cwd가 빠졌다.
  - 원전이 준 것은 살아 있는 저장소다. 고정 SHA의 분리 worktree는 원전보다 좁은 방식이다.
- CLI 플래그(`--help`로 확인): codex `-s read-only -C`, claude `--tools`, agy `--add-dir`.
  - agy에는 읽기 전용을 강제할 수단이 없다(`--dangerously-skip-permissions`).
  - agy의 `--mode plan`·`--sandbox`는 실측하지 않아 쓰지 않았다.

## 구현 (`be6654b`)

- **`layer2_verify`**: 세 백엔드에 `workdir=` 인자를 추가했다. 주지 않으면 실행 인자와 하위 호출 모양이
  종전과 같다(기존 검사가 `_run_rc`·`_codex_run`을 바꿔 끼우기 때문이다).
  - codex: `-s read-only -C <dir>`. workdir가 있으면 `.33` 원격으로 떨어지지 않는다(트리가 마스터에 있다).
  - agy: 두 번째 `--add-dir`를 붙이고, 지시문이 BRIEF의 절대 경로를 직접 가리킨다.
  - claude: `--tools Read,Grep,Glob`에 cwd를 준다.
  - 호출마다 백엔드와 작업 디렉터리를 로그로 한 줄 남긴다.
- **`review_gen.commercial_chat(workdir=)`**: 받은 값을 넘기기만 한다.
- **신규 `pinned_tree.pinned_worktree`**: 저장소 밖 임시 디렉터리에 detached worktree를 만든다.
  - 나올 때 항상 `worktree remove --force`와 `prune`을 한다.
  - 직전에 `status --porcelain`을 돌려, 트리에 쓴 흔적이 있으면 경고 로그를 남긴다.
  - 근거는 본 저장소의 `git show sha:file`과 대조하므로, 트리에 쓰더라도 판정은 오염되지 않는다.
- **`dismissal_candidates`**:
  - 프롬프트에는 대상 경로·지적 본문·기준 SHA만 싣는다.
  - 고정 트리는 수집 한 번에 하나만 만들어 모든 항목이 같이 쓴다.
  - 트리 생성에 실패하면 그 수집에서는 unjudged로 처리하고 다시 만들지 않는다.
  - `_validate`는 그대로 둔다.
- 검사: `test_pinned_tree.py`(신규 4건)·`test_dismissal_candidates`·`test_usage_cli_paths`(51/51,
  백엔드별 workdir 없음/있음의 실행 인자·cwd). 전수 170파일에서 실패는 기존 2개(#815)뿐이다.

## 드라이런 (실 트윈·실 체인, 결과·사용량은 scratchpad)

- 입력은 5건이었다: P12, 그리고 이번 주에 새로 생긴 리뷰 지적 R153-1·R153-2·R154-1·R155-1.
- 5건 모두 codex가 응답했다. 71초, 오류 0건.
- 트리는 하나를 `2c93f68`(main)으로 만들었고 끝난 뒤 제거됐다. worktree 목록·`/tmp` 잔여 0, 쓰기 경고 0.
- 판정은 5건 모두 unjudged였다. 지적이 아직 유효하다는 뜻이다.
  - 이유가 현재 코드를 구체적으로 인용했다. 예: R155-1은 *"`cm._call`을 람다로 덮어쓰고 finally에서
    복원하지 않는다"*. 에이전트가 파일을 직접 읽었다는 근거다.

### 토큰 — 예상과 반대

| | 입력 | 캐시 | 캐시 제외 |
|---|---|---|---|
| P12 종전(소스 첨부, 보고서 113) | 95,994 | 미기록 | — |
| P12 직접 읽기 | 154,300 | 116,352 | 37,948 |
| 새 4건(프롬프트 1천 자대) | 65,030~69,277 | 43,008~49,664 | 15,622~25,991 |

원인은 둘로 추정한다. 측정하지는 않았다.
- 도구를 왕복할 때마다 문맥 전체를 다시 보낸다.
- 트리 안의 `AGENTS.md`(10,668바이트)를 codex가 자동으로 읽는다.

상용 호출에 한도를 두지 않는다는 규칙(기억 `no-token-budget-for-cloud-llm`) 때문에 이것이 막을 근거는
아니다. 다만 「소스를 빼면 토큰이 준다」는 가정은 이번 측정으로 깨졌다. #825 노트에 적었다.

## 운영 메모

- 커밋 `be6654b`, push. 배달 3/3 OK(HEAD와 같음). `.2`의 홈 중복 스킬 경고는 종전과 같다.
- 재기동은 하지 않았다. `ax-batch`가 회차마다 새 프로세스로 코드를 읽는다.
- #825는 「진행」 상태로 두고 구현·드라이런·토큰 표·남은 것을 노트로 남겼다.

## 남은 것

- 「에이전트가 직접 읽고 낸 줄 번호를 원문과 대조하는 경로」는 라이브로 확인하지 못했다(candidate·resolved가
  0건). 10-24 주말 회차에서 본다(#823 확인과 같은 회차).
- claude `--tools`와 agy 다중 `--add-dir`도 실측하지 못했다. 체인이 codex에서 끝났기 때문이다.
- `plan_generator`·`recipes_synthesizer` 전환은 사용자 결정 대기다(토큰 실측을 보고 판단).
- 이전 보고서의 남은 것은 그대로다: `.33` 실측 셋 · #798 마지막 라이브 · `watch.exe` 훅 · #815.

### 이후 경과

- 같은 날 21:30 #815 기존 실패 2건 해소, 전수 실패 0 — [리포트 116](116-815-two-stale-failures-cleared.md).
