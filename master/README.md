# master

192.168.0.57(리눅스 인프라 컴퓨터)에서 돌아갈 오케스트레이션 코드가 여기 들어간다.

## 지금 있는 것 (2026-08-09 기준)

| 파일 | 내용 |
|---|---|
| `verdict.py` | **층2 판정 계약 (fail-closed).** `contract_text()` 로 프롬프트에 계약을 붙이고 `parse_verdict()` 로 읽는다. **모든 실패 경로가 차단으로 떨어진다** |
| `layer2_verify.py` | 층2 검증기 — UE5/C++ 문법 프롬프트 + 백엔드 체인(`agy` → `claude`). `verify_files([(경로, 내용)])` |
| `test_*.py` | **테스트는 저장소 루트 `CLAUDE.md` 의 세는 법을 따른다.** pytest 불필요 — 각 파일을 그대로 실행한다. 목록은 저장소 루트 `CLAUDE.md` 참조 |
| `task_queue/` | **잡 분배 큐** (AgentTest `mcp/task_queue/` 이식, 2,717줄). HTTP 서비스 + MCP stdio |
| `auth.py` | 🔴 **공용 인증 — 공유 베어러 토큰, fail-closed.** 세 서비스가 같은 ASGI 미들웨어를 쓴다. 토큰이 없거나 약하거나 파일 권한이 열려 있으면 **서비스가 뜨지 않는다**. 열린 경로는 `/livez` 하나 |
| `layer3_verify.py` | **층3 판정 계약 (fail-closed).** UE5 자동화 로그(`Result={Success\|Fail}` + `TEST COMPLETE. EXIT CODE:`)와 UBT 빌드 로그(`Result: Succeeded\|Failed`)를 각각 파싱한다. 🔴 **프로세스 반환 코드를 읽지 않는다** — 실측에서 거짓 실패·거짓 성공이 둘 다 나왔다 |
| `broker/` | **추론 브로커** (Ollama API 호환). ✅ **가동 중** — `ax-broker.service` `:8102` |
| `projects/` | **프로젝트 레지스트리 MCP** — 등록·마운트 전환 + **워크숍 체크아웃**(경로·`driven`) + 더티 체크. ✅ **가동 중** — `ax-projects.service` `:8103`, 도구 **15종** + `role`(worker/requester) |
| `events/` | 이벤트 스풀 + **색인기**. Gitea `post-receive` → 스풀 → `ax-indexer.path`(inotify) → 재색인. 🔴 폴링 아님 |
| `provision.py` | Ollama 노드 **점검·원격 설치**. 🔴 `.33`(메인 작업 PC)은 `resident=False` — 상주시키지 않는다. `python -m master.provision check` |
| `work/` | 워크플로우 — **골조·동결 → 분해 → 파견 → 검증**. 2-tier 브랜치 · 매니페스트 · 도메인 규범(`norms.py`) · 헤더 선언(`declarations.py`). 🔴 **쓰는 주체는 하나**(통합자 `.2`, 2026-08-11) — 빌드해 본 주체가 커밋하므로 깨진 것이 원격에 못 박힌다. 지도는 `docs/4-work-loop.md` §4.5·§4.7, 권한은 `docs/8-git-authority.md` §8.4 |
| `work/skeleton.py` | 🔴 **골조 생성 + 인터페이스 동결** (중 1.1). 골조는 **텍스트로만** 낸다(마스터는 파일을 안 쓴다, §2.1). grounding = 관계 그래프(부모/자식·include) + **include 헤더의 타입** + 헤더 선언(#26) + 도메인 규범 + **휴리스틱**. 기본 레인 `claude:opus` — 🔴 A/B 실측: 동결 선언 opus **30** / agy 20 / 35B 10 / 14b **6**(+펜스 잔재). 골조는 **모든 조각의 계약**이라 값을 쓸 자리다. 동결 추출은 **결정적(LLM 0)** — 실제 헤더 857개로 회귀: 동결 12,719 · 본문 채움 시뮬 714건 **오탐 0** |
| `work/skeleton_gate.py` | 🔴 **골조 빌드 게이트** (소 1.1.5) — 통합자 `.2` 의 격리 트리에 놓고 UE5 를 세운 뒤 **통과해야 등재**. 원전은 빌드를 등재 *뒤*에 두었다가 **깨진 골조가 origin 에 박혀 워커 전원이 그 위에서 작업**했다. ⚠️ **게이트를 안 붙인 것은 통과가 아니라 미확인**(`Registered.gate_checked`). 실측: 콜드 144초 · 증분 35~65초 |
| `work/decompose.py` | **분해** (중 1.2) — §3 의 미결을 닫았다: 적용 순서 = 🔴 **의존이 먼저**(include 위상 정렬) · 입도 = **파일 불가분** · 파일 내 = `[PSEUDO:N]` 뎁스. 🔴 **묶음(동시)과 뎁스(순차)를 구분한다** — 안 그러면 겹침 검사가 뎁스를 위반으로 잡는다. ⚠️ 순환은 **보고만**(역추적이 basename 근사라 가짜일 수 있다). 계획은 `preview()` 를 **사람이 보고 자른다** |
| `work/heuristics.py` | 🔴 **대화형 휴리스틱** (소 1.1.6) — 골조가 *"여기서 추측했다"* 를 내놓고 **사람이 답한 것만** 적립된다(모델 제안을 적립하면 다음 골조가 자기 말을 근거로 반복한다). 🔴 **범위**: `project` / `domain:<D>` / `once`(적립 안 함) — 없으면 이번 작업의 결정이 남의 작업을 오염시킨다. 소 2.3.4 실패 카탈로그와 **짝** |
| `work/infer.py` | 🔴 **추론 파견** (중 1.3) — 워커는 **읽고 추론하고 텍스트로 답한다.** `python -m master.work.infer probe\|run\|run-p\|spool`. 🔴 **큐에 제출하지 않는다** — 태스크는 `claimed` 로 남고 제출은 통합자(소 1.4.3)가 한다. 응답은 **파일로** 온다(`.ax/work/<task>/response.txt` → `scp`): `.2` 콘솔이 CP949 라 stdout 은 한국어에서 깨진다(층3 이 같은 자리에서 죽었다). 판정은 **마커 + 응답 파일 둘 다** — 마커만 보면 *"DONE 이라 말하고 파일 안 씀"* 을, 파일만 보면 *"반쯤 쓰이다 죽음"* 을 통과시킨다. 🔴 스풀(`<프로젝트>/responses/`)이 **복구 단위**다 — 같은 기준 커밋의 통과분은 **다시 사지 않는다**. 🔴 실패한 선행의 후속은 **파견 않고 반납**(큐는 `failed` 를 의존 해소로 센다). 기본은 **직렬**(실측: 2대 = 12% 빠르고 90% 비쌈). ✅ 실전: 단건 45초·$0.27 · **워커 2대 동시 36초·$0.4725·통과 2/2**(윈도우+BC-250, 채널 동일). 🔴 실측 **캐시 생성 고정비 워커당 24~26K 토큰** — N대면 N번 낸다 |
| `work/integrate.py` | 🔴 **통합자 — 유일한 쓰기 주체** (중 1.4). `python -m master.work.integrate plan\|run`. **조각마다** 층1(무료·결정적) → 적용 → **UE5 빌드** → 🔴 통과하면 커밋, 실패하면 **되돌리고 커밋하지 않는다**(소 1.4.4). 🔴 §4.5 의 *"전부 적용 후 빌드 한 번"* 을 뒤집었다 — 증분 빌드 35~65초라 조각마다 세워도 싸고, **어느 조각이 깨졌는지 알 수 있다**. 🔴 **첫 실패에서 멈춘다**(적용 순서 = 의존 순서). 격리 트리는 체크아웃의 **형제**(`ax-wt-<work>`), detached HEAD, 재사용 시 기준으로 자동 복원. push 는 **ff-only · force 금지** — 거부되면 커밋은 트리에 남고 사람이 판단한다. 실측: 격리+빌드+커밋 **159초**(콜드 빌드 142초). 🔴 **층2 를 빌드 앞에** 두고(비싼 것 앞에 싼 것) 선언부 grounding 을 싣는다 — 못 실으면 `l2_grounded=False` 로 보고. 🔴 층3 `RunTests` 는 **work 단위 한 번**(실측 74초 — 문서의 미측정 DDC 비용이 이 값) · ⚠️ **테스트 0개라 fail-open + 경고**. 실패는 큐 되돌리기 + `[FEEDBACK]` + **레드마인 등재** + **실패 카탈로그 적립** |
| `work/layer1.py` | 🔴 **층1 — 결정적 자기검증** (중 2.1). 무료·즉시·LLM 0. 동결 위반 + 휘발 태그(`[PSEUDO:N]`·`[IMPL]`) + 🔴 **`[FEEDBACK]` 잔재** + 펜스. 🔴 **두 곳에 박혀 있다** — 응답 수락(`infer.judge`)과 적용 직전(`integrate.apply_one`). ①이 없으면 잔재가 스풀에 쌓이고 ②가 없으면 스풀 손질·재사용이 검사를 우회한다. ⚠️ 인코딩 유실 사본으로는 동결을 판정하지 않는다(없는 위반을 만든다) → **동결 미검사**로 기록 |
| `work/failures.py` | **실패 카탈로그** (소 2.3.4) — 판정 실패를 다음 골조 프롬프트로 되먹인다. 🔴 휴리스틱(사람이 답한 것만)과 **짝**이고, 이쪽은 **기계가 모아도 된다** — 근거가 컴파일러의 오류 문자열이지 모델의 의견이 아니다. ⚠️ 산문 요약은 적립하지 않는다. 파일·줄을 키에서 빼 **한 줄 + 횟수**로 접는다 |
| `bench_layer2.py` | **층2 모델 선정 벤치** (소 2.2.1) — 표본 7개(전부 실제로 났던 실패), 채점은 `verdict` 계약만. 🔴 실측: agy·sonnet·opus **동점**(4/5·오탐 0) → 싼 쪽 먼저 · 14b 는 선언부를 줘도 못 잡음 · **35B 는 오탐 2 로 탈락**. 🔴 **차이는 모델이 아니라 grounding** — 넷이 선언부 없이는 열거값 환각을 놓쳤다 |
| `work/porting.py` | **포팅 원본 대응** (소 1.3.5) — `python -m master.work.porting pairs\|find`. 🔴 실측 2026-08-12: 파일 1,654개 중 stem 그대로 같은 것 **9쌍**, **접두사 정규화 후 21쌍**(포팅이 개명을 거쳤다). 🔴 **퍼지 매칭 없음** — 틀린 원본은 원본 없는 것보다 나쁘다. 규칙(`exact`/`prefix`)을 결과에 실어 사람이 가늠한다. 🔴 **경로만** 싣는다(워커의 Claude 는 체크아웃을 읽는다 — 골조 생성과 반대인 이유) + **읽기 전용·복사 금지·Edit/Write 금지**를 매니페스트에 못박는다 |
| `work/distribute.py` | **`/distribute` 입구** (소 1.3.4) — `plan` → `register` → `dispatch`, 🔴 **단계마다 사람이 끊는다.** 계획은 **JSON 파일로** 낸다 — `preview()` 를 눈으로 보는 것만으로는 **자를 수 없다**. 사람이 그 파일에서 조각을 지우고, `register` 가 그것을 읽는다. 스킬 = `master/skills/distribute/`(`~/.claude/skills/distribute` 는 심볼릭 링크) |
| `work/runner.py` | **워커 러너** — 🔴 **구 토폴로지(워커가 커밋)다.** 지우지 않는다 — 되돌릴 수 있어야 한다(§8.4 ⚠️). 큐에서 집어 워커의 Claude 에 파견하고 결과를 제출한다. `python -m master.work.runner probe\|once\|loop`. 🔴 **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(실측: 두 워커 다 8101 이 401, AX MCP 0건). 하트비트도 마스터가 친다. 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄, 관대함은 **BLOCKED 쪽으로만**. 🔴 기준 절은 **파견 시점에 다시 푼다**. 실측 e2e 71초 |
| `work/cleanup.py` | **찌꺼기 정리** — 워커의 로컬 브랜치·부산물. `python -m master.work.cleanup plan\|apply`. 🔴 **워커는 스스로 못 지운다**(스킬이 브랜치 삭제 금지 — 의도). 삭제는 **팁이 `origin/<base>` 에서 도달 가능할 때만**, 나머지는 **보존**(fail-closed 의 방향이 보존이다). 원격은 안 건드린다. `failed` 부산물은 증거로 남긴다. ⚠️ `--format` 은 셸별로 감싼다 — `%(...)` 의 괄호가 POSIX 문법이라 안 감싸면 리눅스 워커만 조용히 실패한다 |
| `graph/` | **관계 그래프** — 상속(tree-sitter C++) + `#include`. 1,806 클래스 · 6,380 메서드 · 10,817 간선, 전체 스캔 2.9초. `python -m master.graph build\|status` |
| `ontology/` | **온톨로지** — YAML io(PyYAML 0) · stale · L1/L2/L3 · 멤버 제안 · 개념 계층 · **사실 게이트** · 패키지 쓰기 · **LLM 재합성**. `python -m master.ontology plan\|dry\|refresh`. 🔴 결정 규칙은 그 패키지 `__init__.py` 에 있다 |
| `context_synth/` | **컨텍스트 MD 합성** — 프롬프트·grounding·σ.7 게이트·**사실 게이트**·서킷브레이커. 색인기에 배선됨 |
| `client/` | **워커 번들** — 머신 프로브(실측) → config·스킬·CLAUDE.md 배달 → 🔴 **되읽어 해시 대조**. `python -m master.client probe\|plan\|deliver\|check` |
| `source_text.py` | 🔴 **CP949 44%** (실측 723/1,654). 소스는 전부 이걸 거쳐 읽는다 — 한글 주석이 최고 신호원이다 |
| `context_search/` | 검색 코어 — 벡터(ChromaDB) + BM25(FTS5) 를 RRF 로 융합. **마운트된 프로젝트의 디렉토리를 매 호출 해석**한다 (§5.5.2). 재색인: `python -m master.context_search.rebuild` |
| `requirements.txt` | 마스터 의존성. AgentTest 엔 없어 `build.bat:29` 기준으로 신규 작성 |
| `systemd/` | 유닛 **4개**(+`ax-indexer.path`) (§5.4.4 확정: systemd + venv). ✅ 전부 설치·enable·가동 중 — `systemctl status ax-task-queue ax-broker ax-projects` |

### task_queue 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r master/requirements.txt
AX_TASK_QUEUE_ROOT=/home/sim/ax-state PYTHONPATH=. \
  .venv/bin/python -m master.task_queue --serve /home/sim/ax-state 8101 0.0.0.0
```

**이식 시 바꾼 것 3가지** (원본과의 차이 — `../PLAN.md` §9.5):

| | AgentTest | 여기 |
|---|---|---|
| import | 플랫 (`from models import ...`, PyInstaller 전제) | 패키지 상대 import |
| 상태 루트 | `Path(__file__).parent.parent.parent` **역산** | `AX_TASK_QUEUE_ROOT` **명시 설정, 없으면 즉시 실패** |
| `--cleanup-branches` | root(=UE5 저장소)의 `worker/*` 브랜치 삭제 | 🔴 **거부** — 마스터 root 는 큐 상태 저장소라 조용한 no-op 이 된다 |

상태 저장소는 `/home/sim/ax-state`(로컬 git). 상태 전이마다 감사 커밋이 쌓인다 —
**UE5 저장소가 아니라 큐 자체의 상태**다(`../PLAN.md` §2.1).

```python
from layer2_verify import verify_files
v = verify_files([("Combat.cpp", src)])
if v.blocked:
    # v.failure 가 있으면 계약 위반(검증기가 판정을 못 냄), 없으면 실제 지적
    print(v.summary(), v.findings)
```

🔴 **AgentTest 원본과 결정적으로 다른 점** — 원본 `syntax_check` 는 **fail-open** 이었다
(docstring: *"checked=False = 양쪽 다 불가 → 호출자는 통과로 간주"*). 검증기가 죽거나
헛소리를 하면 조용히 통과했다는 뜻이다. 여기서는 **차단**한다. 근거·실측 = `../PLAN.md` §9.4.4.

**언어: Python 확정** (2026-08-06). 신규 작성이 아니라 **AgentTest 기존 자산 이식**이 주 작업이다.
근거와 상세 배치는 `../PLAN.md` §5.

> 🔴 **마스터는 인프라지 작업장이 아니다** (2026-08-07 확정). RAG·온톨로지로 **적합한 코드 뭉치를
> 조립해 윈도우에 건네는** 것까지가 역할이고, **파일 적용·빌드·테스트·코드 등록은 윈도우가 한다**
> (`../PLAN.md` §2.1). **파일을 소유하지 않는다.**
>
> BC-250 이 인계한 것은 **추론 연산**이다 — AgentTest 에선 팀원 PC 마다 로컬 LLM 을 각자 돌렸는데
> 그 부하를 보드가 넘겨받았을 뿐, 파일을 다루던 역할이 옮겨온 게 아니다.
>
> 마스터도 **오케스트레이터의 하나**로서 자기 모델 자원(Claude · Antigravity `agy` · BC-250)을 쓰지만,
> 그 오케스트레이션은 **모델 호출·라우팅·컨텍스트 조립**이지 파일 작업이 아니다(`../PLAN.md` §2.3).
> 나머지 둘은 **윈도우 UE5 PC 2대** 각각의 Claude Code(`../client/README.md`) — 총 3곳이다.

## 역할

- **컨텍스트 매니페스트 조립** — RAG·온톨로지·클래스그래프로 "적합한 코드 뭉치"를 만들어 건넨다.
  대규모 모듈은 **골조 생성 → 인터페이스 동결 → 클래스 단위 분할**까지 여기서(`../PLAN.md` §4.5)
- **추론 브로커** — 엔드포인트 라우팅·헬스체크·페일오버. ✅ **구현됨**(`broker/`, `:8102`).
  ⚠️ 엔드포인트는 **BC-250 만이 아니다** — RTX 3060 윈도우 PC 가 #2 다. 추론 노드를 호출하는 것은 마스터뿐이라는 원칙은 그대로
- **task_queue** — 잡 분배 + **능력 기반 라우팅**(`requires: ue5` 는 윈도우가 claim).
  ✅ **구현·실측 완료(2026-08-08)** — `requires ⊆ capabilities` 부분집합 매칭, fail-closed
- **층2 검증 호출** — 상용 모델 문법·API 검사(`agy` → Claude 폴백). ✅ **구현됨** — 위 `layer2_verify.py`
- **RAG 인덱스**(ChromaDB + BM25) · 온톨로지/관계그래프 · 디지털 트윈.
  "소스=정답" 원칙에 따라 **실제 소스 본문을 번들**한다
- **gajae-code 드라이버** — Deep-Interview/Ralplan/Ultragoal 단계 호출·조율
- 추론 노드 응답(stateless) 수신 및 후처리(펜스 제거·`[PSEUDO]` 잔재 검사)

## 추론 클라이언트 래퍼 (신규 작성 — 이식 아님)

Ollama 를 그대로 호출하지 않고 **얇은 Python 래퍼를 거친다.** 감시·검증·재시도를 걸 지점이 필요하다.
**이건 마스터 몫이다** — 노드를 일회용으로 유지해야 재구축이 쉽고, 검증에 필요한 태스크 컨텍스트
(동결 선언·매니페스트)가 여기 있으며, 노드 간 페일오버는 본질적으로 마스터의 책임이기 때문이다.

| 구분 | 내용 |
|---|---|
| 생존 감시 | `stream:true` 청크 간격 감시 — **생성 중 2s**, **첫 청크 120s+**(콜드 로드 36s + prefill 38s 합산 대비). 초과 시 연결 종료 + 다른 노드로 재할당 |
| 노드 상태 | 주기적 `/api/tags` 프로브 → 죽은 노드 라우팅 제외. `watcher/common_utils.local_llm_health_check_one_shot` 재사용 |
| 요청 정규화 | `"think": false` 주입(35B 필수), `num_predict`/`temperature` 정책, 타임아웃 |
| 응답 후처리 | 마크다운 펜스 제거, `[PSEUDO]` 잔재 검사 |
| 사전 검증 | 동결 인터페이스 위반 1차 검사 — 왕복 낭비 차단 |
| 라우팅 | 모델↔노드 고정 배정 반영 — **전환 비용 실측: 35B 66.9s / 14b 37.5s, 왕복 ≈100초**(2026-08-08 재측정. 기존 "36초"는 14b 방향만 본 값) |
| 계측 | tok/s·첫 청크 지연 기록 → 임계값 재조정 근거 |

근거와 실측 수치: `../PLAN.md` §6.

## 이식 대상 (AgentTest → 여기)

| 컴포넌트 | 규모 | Windows 의존 | 순서 |
|---|---|---|---|
| `mcp/task_queue/` | — | 5줄(둘 다 리눅스 분기 존재) | **1** — 루프 중추, 가장 가벼움 |
| `mcp/context_search/` | — | 사실상 0 (`sys.platform` 분기 0건) | 2 — ChromaDB 인덱스 이관 |
| `watcher/` | 21,171줄 | 19줄 | 3 — 가장 크나 순수 데이터라 기계적 |
| **`mcp/agy_query/`** | 194줄 | — | **4** — 층2 검증. 리눅스에선 PTY 코드 불필요(리포트 04) |
| **`mcp/local_llm_runner/`** | 144줄 | — | §6.4 래퍼와 중복 — **재사용/대체 먼저 결정** |
| `mcp/master_orchestrator/` 中 오케스트레이션 | — | — | 5 — UE 빌드 부분은 분리 |
| Component | Where |
| Layer-2 verdict contract (fail-closed) | `master/verdict.py`, `master/layer2_verify.py` |
| Layer-3 gate (UE5 automation logs, fail-closed) | `master/layer3_verify.py` |
| Inference broker (Ollama-compatible) | `master/broker/` — **live**, `ax-broker.service` `:8102` |
| Task queue (ported, 2,717 lines) | `master/task_queue/` — **live**, `ax-task-queue.service` `:8101` |
| Project registry (MCP) | `master/projects/` — **live**, `ax-projects.service` `:8103`. 🔴 **요청자의 온톨로지 창구**도 여기다(2026-08-09): `create_domain`·`edit_ontology_item`(편집=잠금)·`remove_ontology_item`(🔴 잠긴 것은 force 필요)·`lock`/`list_locked`·`unassigned_classes`(노출만)·`sync_ontology`(기본 계획만). 그 전에는 어휘(별칭)만 다룰 수 있고 **개념은 마스터 CLI 에만** 있었다 |
| Capability routing (`requires`/`capabilities`) | `master/task_queue/logic_claim.py` |
| Shared bearer auth (all 3 services, fail-closed) | `master/auth.py` |
| Event spool + **indexer** (Gitea hook → graphs → **synthesis** → reindex) | `master/events/` — **live**: `ax-indexer.path` (inotify) → `ax-indexer.service`. 🔴 **This is where the twin grows**: changed files → relation graphs (LLM 0) → context-MD synthesis (35B) → reindex. Lost groups are logged by name — the watermark has already advanced, so they can't be found again |
| Context search — **multilingual** vector + BM25 (+trigram KR table), RRF, `[대괄호]` focus | `master/context_search/` — context MDs (961 docs) **and now domain packages** (7, 소 2.1 ✅ 3/3). Domains live in a **separate DB + collection** (`bm25_domains.db` / `ontology_domains`) so they can't crowd out file-level hits; `search_norms` applies a 🔴 **triple noise gate** (BM25-zero ⇒ empty · vector-only needs threshold · hard cap). Wired into `rebuild_all`, skipped by fingerprint when unchanged |
| Workflow — 2-tier branches, manifest, registration, generate → layer2 → hand over, **domain norms** | `master/work/` — 소 2.3.1 ✅: `norms.py` turns `search_norms` hits into an invariants-first bundle in the manifest (≤2 domains × actions touching the target classes). **Measured**: same prompt/model, norms flipped the generated code from an invented member to 4/4 real ones and it honoured a real invariant — but **near-miss spellings survived** (`CurrentStep` vs real `Step`), which is why "ship source declarations to the node" is still open. 🔴 `master.work.generate` the *function* shadows the same-named submodule in `__init__` — import the module path directly. Map: `docs/4-work-loop.md` §4.7 |
| **Relation graphs** — inheritance (tree-sitter C++) + `#include` (중 1.1, **done 5/5**) | `master/graph/` — **1,806 classes · 6,380 methods · 10,817 include edges** on ModularStage, 2.9s full scan. `python -m master.graph build\|status`. ⚠️ reverse include lookup is basename-approximate (9 ambiguous headers) |
| **Ontology** — YAML io (no PyYAML) · stale · L1/L2/L3 layers · member proposals · concept hierarchy · **fact gate** · package writer · **LLM re-synthesis** (중 1.3, **8/13**) | `master/ontology/` — `python -m master.ontology status\|plan\|verify\|dry\|refresh`. 🔴 **`plan` → `dry` first**: `plan` sizes prompts with **no LLM**, `dry` synthesises without writing. Domain MD (intent) + source excerpts + graphs → actions/invariants → deterministic gates → package. 🔴 **Payload is chunked by `#include` cohesion and split across both nodes** — model name selects the node; the defaults are each node's **resident** model (any other evicts the pin). `claude`/`agy` are also valid lanes. Prompt budget is **measured** (2.79–2.85 chars/token, `num_ctx` 8192 both nodes). 🔴 Decision rules live in that package's `__init__.py` |
| **Context-MD synthesis** — prompt+grounding, σ.7 fence strip + σ.7-B save gate, stamping, batch circuit breaker (중 1.2) | `master/context_synth/` — `python -m master.context_synth one\|fill\|all\|status`. 909 source groups, all already documented from the snapshot. **Wired into the indexer** (changed files only). A **deterministic factuality gate** (`verify.py`) rejects docs describing commented-out code as live — **75% pass rate measured on the 35B (3/4)**, and the one rejection was a real catch. `sample N` dry-runs without touching snapshot docs. 🔴 **BC-250 reclaims ~170 MB per request and never gives it back until the model unloads** — `UNLOAD_EVERY=5` handles that; set 0 for dedicated-VRAM nodes |
| **찌꺼기 정리** — 워커의 로컬 브랜치·부산물 (중 2.5.4) | `master/work/cleanup.py` — `python -m master.work.cleanup plan\|apply`. 🔴 **워커는 스스로 못 지운다**(스킬이 브랜치 삭제를 금지 — 의도된 설계). 삭제 기준은 하나: **팁이 `origin/<base>` 에서 도달 가능한가**. 도달 불가·확인 실패는 **보존**한다(fail-closed 의 방향이 여기서는 보존). 🔴 **원격은 건드리지 않는다** — `push --delete` 는 사람의 판단. 부산물은 `verified`/`cancelled` 만 지우고 **`failed` 는 증거로 남긴다**. 우리 브랜치 위에 서 있으면 `main` 으로 되돌리고(체크아웃된 브랜치는 삭제 대상에서 빠지므로) **한 번 더 훑는다**. ⚠️ `--format` 은 셸별로 감싼다 — `%(...)` 의 괄호가 POSIX 문법이라 안 감싸면 리눅스 워커만 조용히 실패한다 |
| **계측 하네스** — 분산 대 단독 (토큰·시간·품질) | `master/bench.py` — `claude -p --output-format json` 의 usage 를 모아 팔별로 비교한다. 품질은 diff 의 식별자를 클래스 그래프와 대조(⚠️ enum·매크로는 오탐). 🔴 **매니페스트를 실행 위치에 놓고 읽히는지 확인한 뒤에만 잰다** — 그걸 안 해서 첫 결과를 통째로 버렸다(리포트 11 §19). 실측: 4파일 묶음이 파일당 **3.2배 싸다**; 워커 2대는 이 크기에서 **12% 빠르고 90% 비싸다** |
| **워커 러너** — claim → 기준 재해석 → scp → `claude -p` → 마커 → submit (중 2.5.3) | `master/work/runner.py` — `python -m master.work.runner probe\|once\|loop`. 🔴 **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(두 워커 모두 8101 이 401, AX MCP 0건이라 스킬의 전제가 틀려 있었다). 하트비트(리스 1200초)도 마스터가 대신 친다. 🔴 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄이고, 관대함은 **BLOCKED 쪽으로만** 연다. 🔴 기준 절은 **파견 시점에 다시 푼다** — durable 브랜치는 설계상 등록 이후 요청자가 만들므로 등록 시점 값은 반드시 낡는다. 선택 단계에서 **워킹트리까지 본다**(워커의 거부는 마지막 방어선이지 선택 기준이 아니다). 실측 e2e 71초 |
| **Worker bundle** — per-machine config · skill · CLAUDE.md merge, delivered over SSH (#21) | `master/client/` — `python -m master.client probe\|plan\|deliver\|check`. **Role-aware**: `worker` gets `ax-work`; `requester` (the human's PC) gets `ax-request`/`ax-ontology` and is **excluded from `drivable_hosts`** — `driven` (can we reach it) and `role` (may we dispatch to it) are different axes. 🔴 **Paths are never hardcoded**: the master generates `<checkout>/.ax/config.json` from the registry, because a worker's config was found pointing at *another machine's* path. Capabilities are **probed, not declared**, and the block states the *consequence* ("no UE5 ⇒ layer-3 cannot be verified here"). CLAUDE.md is merged **marker-delimited** — human text is never overwritten. 🔴 Delivery verifies by re-reading sha256; that caught PowerShell adding BOM/CRLF and an 18KB stdin hang, so transfers use `scp` |
| Ollama node check + remote install (no residency) | `master/provision.py` — `python -m master.provision check` |
| venv + deps | `.venv/`, `master/requirements.txt` |

**여기로 오지 않는 것** (Windows 잔류): **`worker/` 전체**(작업자 하네스 — 파일 소유 계층) ·
`ue_builder.py` · `ue_test_runner.py` · `executor_integration_build.py` · `tdd_dryrun.py` ·
`mcp/commandlet_runner/`.
통합 빌드 게이트는 인프라에 고정하지 않고 **task_queue 잡으로 큐잉 → UE5 보유 기계가 claim**하는
CI 러너 패턴으로 분리한다.

**선결 설치**: `claude` ✅ v2.1.223 / `agy` ✅ v1.1.10(리포트 04) /
~~`bun`·`node`~~ → **마스터엔 불필요**(2026-08-08) — gjc 는 loopback 제약상 윈도우에서 돈다(`../PLAN.md` §9).

## 설계 제약

- **파일을 소유하지 않는다** — 추론 노드와는 텍스트만 왕복. 실제 파일 I/O·컴파일·코드 등록은
  작업자(윈도우). **여기는 인프라지 작업장이 아니다.**
- **추론 요청은 stateless**, **피드백 누적은 git**(`task/<task_id>` 브랜치). 두 경로 분리.
- 검증은 3층 게이트(워커 자기검증 → 상용 모델 문법검사 → 실제 UE5 빌드). `../PLAN.md` §4.3.

상세 계획: `../PLAN.md`
