# master

192.168.0.57(리눅스 인프라 컴퓨터)에서 돌아갈 오케스트레이션 코드가 여기 들어간다.

## 지금 있는 것 (2026-08-09 기준)

| 파일 | 내용 |
|---|---|
| `verdict.py` | **층2 판정 계약 (fail-closed).** `contract_text()` 로 프롬프트에 계약을 붙이고 `parse_verdict()` 로 읽는다. **모든 실패 경로가 차단으로 떨어진다** |
| `layer2_verify.py` | 층2 검증기 — UE5/C++ 문법 프롬프트 + 백엔드 체인(`agy` → `claude`). `verify_files([(경로, 내용)])` |
| `test_*.py` | **테스트 1,126건, 전부 통과.** pytest 불필요 — 각 파일을 그대로 실행한다. 목록은 저장소 루트 `CLAUDE.md` 참조 |
| `task_queue/` | **잡 분배 큐** (AgentTest `mcp/task_queue/` 이식, 2,717줄). HTTP 서비스 + MCP stdio |
| `auth.py` | 🔴 **공용 인증 — 공유 베어러 토큰, fail-closed.** 세 서비스가 같은 ASGI 미들웨어를 쓴다. 토큰이 없거나 약하거나 파일 권한이 열려 있으면 **서비스가 뜨지 않는다**. 열린 경로는 `/livez` 하나 |
| `layer3_verify.py` | **층3 판정 계약 (fail-closed).** UE5 자동화 로그(`Result={Success\|Fail}` + `TEST COMPLETE. EXIT CODE:`)와 UBT 빌드 로그(`Result: Succeeded\|Failed`)를 각각 파싱한다. 🔴 **프로세스 반환 코드를 읽지 않는다** — 실측에서 거짓 실패·거짓 성공이 둘 다 나왔다 |
| `broker/` | **추론 브로커** (Ollama API 호환). ✅ **가동 중** — `ax-broker.service` `:8102` |
| `projects/` | **프로젝트 레지스트리 MCP** — 등록·마운트 전환 + **워크숍 체크아웃**(경로·`driven`) + 더티 체크. ✅ **가동 중** — `ax-projects.service` `:8103`, 도구 **15종** + `role`(worker/requester) |
| `events/` | 이벤트 스풀 + **색인기**. Gitea `post-receive` → 스풀 → `ax-indexer.path`(inotify) → 재색인. 🔴 폴링 아님 |
| `provision.py` | Ollama 노드 **점검·원격 설치**. 🔴 `.33`(메인 작업 PC)은 `resident=False` — 상주시키지 않는다. `python -m master.provision check` |
| `work/` | 워크플로우 — 2-tier 브랜치 · 매니페스트 · 생성→층2→인계 · **도메인 규범 번들**(`norms.py`, 소 2.3.1). 루프는 돈다(실측 20.1s APPROVE). 지도는 `docs/4-work-loop.md` §4.7, 브랜치 수명주기는 `docs/8-git-authority.md` §8.4 |
| `work/runner.py` | **워커 러너** — 큐에서 집어 워커의 Claude 에 파견하고 결과를 제출한다. `python -m master.work.runner probe\|once\|loop`. 🔴 **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(실측: 두 워커 다 8101 이 401, AX MCP 0건). 하트비트도 마스터가 친다. 판정은 **fail-closed 마커** `ATTEMPT`/`HEAD`/`RESULT` 마지막 세 줄, 관대함은 **BLOCKED 쪽으로만**. 🔴 기준 절은 **파견 시점에 다시 푼다**. 실측 e2e 71초 |
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
