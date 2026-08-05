# AX Cluster — 계획 문서

**최종 목표 (AX, AI Transformation):** 언리얼 엔진 5 게임 제작 프로젝트 전체 공정에 AI 활용도를 근본적으로 끌어올리는 것. 단순 코딩 보조를 넘어 온톨로지 기반 디지털 트윈, Unreal MCP(UE 5.8.1+), 코드 작성 보조 에이전트를 하나의 파이프라인으로 통합한다.

**작성일:** 2026-08-05 (이 논의가 진행된 세션 기준)

---

## 1. 배경 — 기존 프로젝트에서 이어지는 부분

### AgentTest (https://github.com/SimSeoWon/AgentTest)
기존 윈도우 기반 오케스트레이션 프로젝트. 현재 문제: RAG/온톨로지 문서 작성 등 무거운 데이터 작업이 윈도우 UE5 워커 컴퓨터에서 불필요하게 돌고 있음 — 리눅스 인프라 컴�트와 분리 필요.

**2026-07-07 합의된 설계**(원본: `~/bc250-backup-staging/memory/project_agenttest_architecture.md`)가 이 프로젝트의 전신 — 아래 구조는 그 설계를 계승/구체화한 것.

### gajae-code (https://github.com/Yeachan-Heo/gajae-code)
코드 작성 품질 보장용 외부 하네스. TypeScript/Bun 기반, `gjc` CLI로 실행. LLM-agnostic(Claude/OpenAI/Gemini/xAI 등), WebSocket SDK로 외부 컨트롤러 연동 가능.

플로우: **Deep-Interview**(모호한 요구사항 명확화) → **Ralplan**(구현 방안 수립+비판) → **Ultragoal**(실행/수정/검증 추적) → **Team**(tmux 기반 병렬 워커, 선택적). 철학: "Interview before guessing", "Plan before mutation" — 단계마다 사람이 검토 가능한 근거를 남김.

### BC-250 로컬 LLM 인프라 (이 세션에서 구축)
BC-250 #1(1호기)에서 이미 검증 완료:
- CU 언락(38/40)·CPU 코어 언락(8c/16t)·GPU governor·SMU OC·ACPI SSDT fix — 전부 재부팅 검증 완료
- Ollama 0.32.5 + Vulkan 백엔드(`OLLAMA_IGPU_ENABLE=1`이 핵심) — ROCm은 이 칩(GFX1013)에서 정상적으로 불가능(rocblas 미지원), Vulkan으로 우회 성공
- Gemma 4 E4B 모델로 실제 추론 테스트 성공(100% GPU, stateless 패턴 확인)
- **미해결:** TTM/GTT 캡 상향(12B급 이상 모델용), 스왑/zram 재설정, CPU governor 재검토 — 전부 재부팅 필요, 다음 세션 진행 예정

상세: `~/.claude/projects/-home-sim/memory/project_bc250_ollama_vulkan.md`, `project_bc250_local_llm_pivot.md`, `project_bc250_fedora_cu_unlock.md`, `project_bc250_acpi_fix_fedora.md`

---

## 2. 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│  마스터 (192.168.0.57, 리눅스)                              │
│  - 오케스트레이션 중추 (Python/Go)                            │
│  - RAG 인덱스, 온톨로지/관계그래프, 디지털 트윈                    │
│  - task_queue: 작업 분배, 워커 claim                          │
│  - gajae-code 드라이버 (Deep-Interview/Ralplan/Ultragoal)   │
│  - Claude / 안티그래비티 API 호출                              │
└───────────────┬─────────────────────────────────────────┘
                │ 내부망 (인터넷 비노출)
       ┌────────┴────────┐
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ BC-250 #1     │  │ BC-250 #2     │
│ (워커, 리눅스)  │  │ (워커, 리눅스)  │   ← 이 문서의 worker/ 디렉토리
│ Ollama+Vulkan │  │ 상태: 미확인/   │
│ 로컬 LLM 추론  │  │ 미구축 (설정   │
│ stateless API │  │ 필요 시 확인) │
└──────────────┘  └──────────────┘

┌──────────────┐
│ 윈도우 UE5 PC  │  ← 엔진 실행 + 상태 추출로 역할 축소
└──────────────┘
```

**설계 원칙 (AgentTest 2026-07-07 합의 계승):**
1. BC-250 워커는 파일을 직접 읽고 쓰지 않는다 — 텍스트(컨텍스트/코드조각/diff)만 주고받는다.
2. 검증은 LLM 판단보다 결정론적 게이트(테스트/타입체커/린터)를 우선한다. gajae-code의 Ultragoal 단계가 이 역할.
3. 컨텍스트 전처리(요약/청크분류/임베딩)는 BC-250 로컬 LLM에 맡겨 API 비용/레이턴시를 줄인다.
4. 마스터→워커 호출은 stateless — 컨텍스트 문자열을 매 요청마다 던지고, 응답 후 자동으로 상태가 남지 않는다(Ollama `/api/generate`에서 `context` 필드를 재사용하지 않는 방식으로 이미 검증됨).

---

## 3. 미정/다음 단계

- [x] ~~마스터(192.168.0.57)↔BC-250 #1 실제 네트워크 stateless 호출 테스트~~ — **완료 2026-08-06**
      (`/api/tags` + `/api/generate` 정상, 60.6 t/s). 상세 = 리포트 24 §6
- [x] ~~BC-250 #1의 TTM/GTT 캡 상향~~ — **완료 2026-08-06**. GTT 3.73 → **15.10 GiB**,
      Ollama 인식 11.7 → **15.6 GiB**. 14B(8.9GB)·35B-A3B(13GB) 모두 100% GPU 적재 확인. 리포트 24 §3·§4
- [x] ~~추론 요청 주체(워커 직접 vs 마스터 브로커)~~ — **마스터 브로커로 확정 2026-08-06** (아래 §4)
- [ ] **BC-250 #1 장시간 안정성 검증** — 클러스터에 물리기 전 필수 관문.
      GPU 크래시 = 호스트 하드 행(원격 복구 불가)이라 무인 루프의 최대 리스크
- [ ] BC-250 #2 현재 상태 확인 (도착/설치/OS 여부)
- [ ] 작업자(윈도우) ↔ 마스터 경로 — AgentTest `task_queue` 를 리눅스 마스터로 이관
- [ ] gajae-code를 이 오케스트레이션에 실제로 연결하는 방법 — WebSocket SDK로 마스터가 외부 컨트롤러 역할을 하는 구조가 유력, 상세 설계 필요
- [ ] 온톨로지 기반 디지털 트윈 설계 — 어떤 데이터를 온톨로지화할지 구체화 필요
- [ ] Unreal MCP(5.8.1+) 연동 방식 — 윈도우 UE5 PC 쪽에서 어떻게 노출/호출할지
- [x] ~~마스터 쪽 오케스트레이션 언어(Python vs Go) 최종 결정~~ — **Python 확정 2026-08-06** (아래 §5)

---

## 4. 작업 루프 확정 (2026-08-06)

> 근거 실측: 리포트 24(속도·인프라), 리포트 25(모델 품질). 둘 다 `~/bc250-backup-staging/reports/`.

### 4.1 용어 — 코드베이스와의 충돌 주의

| 통칭 | 머신 | AgentTest 코드 용어 |
|---|---|---|
| 작업자 | 윈도우 UE5 PC | **`worker/`** (task_queue claim/write/verify 를 도는 쪽) |
| 인프라 / 마스터 | 192.168.0.57 | master, `task_queue` 서버 |
| 워커(구어) | BC-250 | **추론 노드** — 코드상 `worker` 가 *아님* |

`worker/worker.py` 는 윈도우 PC 에서 도는 코드다. BC-250 을 "워커"라 부르면 코드 탐색 시 오도된다.

### 4.2 루프

```
작업자(윈도우, 파일 소유)
   │  ① 수정 대상 코드 뭉치 + 태스크를 텍스트로 전달
   ▼
마스터(57) ── RAG/온톨로지로 컨텍스트 매니페스트 조립, 라우팅 판단
   │  ② stateless 추론 요청 (텍스트 in/out, 파일 접근 없음)
   ▼
BC-250 추론 노드 ── 로컬 LLM 이 코드 생성
   │  ③ 결과 텍스트(diff/구현) 반환
   ▼
마스터 ── ④ 작업자에게 전달
   ▼
작업자 ── ⑤ 파일 적용 + 컴파일 + 테스트 (여기서만 파일 I/O 발생)
   │  ⑥ 피드백
   ▼
git `task/<task_id>` 브랜치에 커밋으로 누적 → 다음 라운드 워커가 읽어감
```

- **파일은 윈도우를 떠나지 않는다.** 텍스트(코드조각/diff)만 왕복 — κ.1 원칙. 클로드 코드 자체의
  "원격 추론 + 로컬 실행" 분리와 같은 패턴.
- **추론 요청은 stateless**(Ollama `context` 필드 미재사용), **피드백 누적은 git**
  (plan v5.0 C.3 git-as-feedback-bus). 두 경로를 분리하는 이유는 토큰 비용 —
  라운드마다 누적 컨텍스트를 프롬프트로 재주입하면 인바운드 토큰이 폭증한다.
- **마스터 브로커 확정**: 작업자가 BC-250 을 직접 호출하지 않는다. 상태·판단·라우팅이 전부 마스터에
  있고, BC-250 방화벽도 `192.168.0.57` 에서만 11434 를 허용하도록 이미 잠겨 있다(리포트 24 §7).

### 4.3 🔴 환각 검증은 3층 — **컴파일만으로는 절반밖에 못 잡는다**

리포트 25 의 UE5 태스크 6종 실측에서, 오류 유형에 따라 잡히는 층이 갈렸다:

| 실측 오류 | 컴파일 | 실제로 잡는 층 |
|---|---|---|
| `FLifetimeProperty::AddRepNotifies` (35B, 없는 API) | ❌ 실패 | 층3 |
| `IsPendingKill()` on `TSoftObjectPtr` (14B) | ❌ 실패 | 층3 |
| `Cast<IInteractable>` 직접 호출 (**양쪽 모델**) | ✅ **통과** | 층2 또는 테스트 |
| `IsValid()` false → nullptr 로직 오류 (**양쪽 모델**) | ✅ **통과** | 테스트 |
| `FText::FromString` 지역화 우회 (35B) | ✅ **통과** | 층2 |

**절반이 컴파일을 통과한다.** `interface`·`softptr` 은 두 모델 모두 틀렸고 둘 다 "빌드는 되는데
런타임에 잘못 동작"하는 유형이다. 따라서:

```
층1  워커 자기검증 (무료·즉시·결정론적)
     동결 인터페이스 위반 · 펜스/[PSEUDO] 잔재
     기존 구현: AgentTest `worker/validator._frozen_interface_violation`

층2  상용 모델 문법·API 검사 (저비용)
     환각 API 를 컴파일 전에 선제 차단 → 층3 호출 횟수 절감
     기존 구현: plan v5.0 `worker/claude_spawn.syntax_check` (agy 우선, Claude 폴백)

층3  실제 UE5 빌드 + RunTests (고비용·최종 권위)
     기존 구현: Phase ζ.3c `FAutomationTest`
```

층2가 필요한 이유는 비용이다 — UE5 빌드는 분 단위라 모든 시도를 컴파일할 수 없다.
환각 API 는 상용 모델이 읽으면 대체로 잡히므로(“`DOREPLIFETIME` 이 맞다”) 층2에서 걸러낸다.

**모토 정합**: 층1 무료, 층2는 검증(고레버리지)에만 상용 토큰, 층3은 결정론적. 작성은 여전히 무료 로컬.

### 4.4 모델 배정 (리포트 25 결론)

| 역할 | 모델 | 근거 |
|---|---|---|
| **UE5 C++ 코드 생성** | `qwen2.5-coder:14b` (Q4_K_M, 8.9GB) | 도메인 관용구 정확, 환각 없음. 유일 결함(마크다운 펜스)은 파이프라인이 제거 |
| **컨텍스트 쿠킹**(요약·청크분류) | `35B-A3B IQ2_M` (13GB) | prefill 6.5× · 생성 3~4× 우위. 단 코드 생성에선 API 환각으로 부적합 |

- 두 모델 **동시 상주 불가**(8.9+13GB > 15.6GB, `MAX_LOADED_MODELS=1`), 전환 비용 36초.
  → 보드 2대가 되면 **모델을 보드별로 고정 배정**: `#1 = 14B(생성)`, `#2 = 35B(쿠킹)`.
- 35B 호출 시 API 에 **`"think": false` 필수** — 없으면 사고 과정을 출력해 토큰을 낭비한다.
- **로컬 LLM 공통 취약 영역**: `BlueprintNativeEvent` 의 `Execute_` 규약, `TSoftObjectPtr` 로드 패턴을
  두 모델 모두 틀렸다. 골조/매니페스트에 해당 패턴을 명시하거나, 이 유형은 상용 모델로 라우팅한다
  (κ.3 의 (b) regime).

### 4.5 이 절의 한계

- 위 "환각 API" 판정은 **코드 정독 근거이며 실제 UE5 컴파일로 확정하지 않았다** — 윈도우 PC 필요.
- 태스크당 1회 샘플(`temperature=0`). 6종은 1종보다 낫지만 통계적 결론은 아니다.
- BC-250 장시간 안정성 미검증 — 이 루프의 최대 미해결 리스크.

---

## 5. 마스터 오케스트레이션 언어 — Python 확정 (2026-08-06)

**결론: Python.** 신규 선택이 아니라 *기존 자산을 이식*하는 문제였다. 근거는 AgentTest 코드베이스 실측.

### 5.1 근거

**① 이미 67,038줄이 동작 중이다** (199개 `.py`, plan v5.0 기준 533 테스트 통과)

| 영역 | 줄 수 |
|---|---|
| `mcp/` (task_queue · context_search · master_orchestrator) | 26,424 |
| `watcher/` (RAG · 온톨로지 · 클래스 그래프) | 21,171 |
| `tests/` | 14,246 |
| `worker/` | 3,657 |

**② Windows 의존이 92줄뿐이다 (0.14%)** — `win32`/`ctypes.windll`/`winreg`/`STARTUPINFO`/`.bat` 기준.
게다가 가장 밀집한 곳이 **어차피 Windows 에 남아야 할 컴포넌트**다:
`ue_builder.py`(19) · `commandlet_runner`(5) · `ue_test_runner.py`(2).
**리눅스로 옮길 컴포넌트의 Windows 의존은 약 30줄.** 이식이지 재작성이 아니다.

**③ ChromaDB 는 Python 네이티브다.** Go 로 가면 벡터 DB 교체(Qdrant 등) + 임베딩 파이프라인
(ONNX `all-MiniLM-L6-v2`) 재구축까지 딸려온다. 언어 교체가 아니라 스택 교체가 된다.

**④ Go 의 강점이 이 워크로드에 안 맞는다**

| Go 장점 | 이 프로젝트 |
|---|---|
| 단일 바이너리 | 이미 PyInstaller 로 `.exe` 빌드 중(`build.bat`) |
| 동시성 | I/O 바운드(Ollama HTTP · git). asyncio 로 충분 |
| 실행 성능 | 병목은 **LLM 추론(초 단위)** — 오케스트레이션(ms)은 노이즈. 실측 14B 22 t/s |

### 5.2 이식 대상 — 컴포넌트 배치

2026-07-07 아키텍처 합의("RAG/온톨로지/그래프는 엔진과 무관한 순수 데이터 작업이므로 인프라에 둔다")를 구체화.

**A. 리눅스 마스터(57)로 이전** — 순수 데이터/판단 계층, UE5 무관

| 컴포넌트 | 규모 | Windows 의존 | 비고 |
|---|---|---|---|
| `watcher/` 전체 | 21,171줄 | 19줄 | git watch · RAG · 온톨로지 · 클래스 그래프. 정리 대상: `review.py`(5) · `network_firewall.py`(4) · `skill_defs_distribute.py`(4) · `process_lifecycle.py`(3) · `watch.py`/`common.py`/`agent_defs.py`(각 1) |
| `mcp/context_search/` | — | 6줄 | ChromaDB + BM25. `remote_client.py`(3) · `wiki_local_tools.py`/`search_tools.py`/`llm_chat.py`(각 1) |
| `mcp/task_queue/` | — | 5줄 | 작업 분배·claim·fencing. `logic_cleanup.py`(3) · `reclaim.py`/`persistence.py`(각 1) |
| `mcp/master_orchestrator/` 中 오케스트레이션 부분 | — | — | 골조 생성·분배·라우팅. **UE 빌드/테스트 부분은 제외**(아래 B) |

**B. Windows 잔류** — 엔진 바운드, 파일 소유 측에서만 가능

| 컴포넌트 | Windows 의존 | 사유 |
|---|---|---|
| `mcp/master_orchestrator/ue_builder.py` | 19줄 | `UE Build.bat` 실행 |
| `mcp/master_orchestrator/ue_test_runner.py` | 2줄 | `UnrealEditor-Cmd RunTests` |
| `mcp/master_orchestrator/executor_integration_build.py` | 3줄 | 통합 빌드 게이트 |
| `mcp/master_orchestrator/tdd_dryrun.py` | 1줄 | TDD 드라이런 |
| `mcp/commandlet_runner/` | 5줄 | UE 커맨드릿 |
| `worker/` 전체 | 14줄 | 작업자(윈도우) 하네스 자체 |

**C. 빌드 러너는 고정하지 않는다** — 2026-07-07 합의대로 "1차 통합 빌드게이트"를 인프라에 박지 않고
**task_queue 잡으로 큐잉해 UE5 를 가진 아무 작업자가 claim 하는 CI 러너 패턴**으로 분리한다.
이래야 마스터가 UE5/Windows 에 묶이지 않는다.

### 5.3 이식 순서 (제안)

1. `mcp/task_queue/` — 루프의 중추이고 Windows 의존 5줄로 가장 가볍다. 먼저 옮겨 마스터에서 기동.
2. `mcp/context_search/` — ChromaDB 인덱스 이관(재색인 필요 여부 확인).
3. `watcher/` — 가장 크지만 순수 데이터라 기계적. `network_firewall.py`·`process_lifecycle.py` 는
   리눅스 등가물로 교체 또는 제거 검토.
4. `master_orchestrator/` 분할 — 오케스트레이션 부분만 이전, UE 부분은 §5.2-B 로 남기고
   §5.2-C 의 큐 잡 패턴으로 연결.

**주의:** 위 줄 수/의존 집계는 2026-08-02 클론 기준이다. 착수 전 최신 저장소에서 재확인할 것.

---

## 6. 관련 문서
- 이 보드(BC-250 #1)의 하드웨어 작업 이력: `~/bc250-backup-staging/reports/`, `~/.claude/projects/-home-sim/memory/`
- AgentTest 2026-07-07 원 설계: `~/bc250-backup-staging/memory/project_agenttest_architecture.md`
- gajae-code: https://github.com/Yeachan-Heo/gajae-code
- AgentTest: https://github.com/SimSeoWon/AgentTest
- 2026-08-06 인프라 작업(헤드리스·TTM/GTT·마스터 링크·방화벽·속도 벤치):
  `~/bc250-backup-staging/reports/24-ttm-gtt-tuning-headless-cluster-link.md`
- 2026-08-06 모델 품질 비교(UE5 태스크 6종): 
  `~/bc250-backup-staging/reports/25-model-quality-comparison-14b-vs-35b.md`
- 마스터(57)측 사본: `sim@192.168.0.57:~/claude-workspace/reports/`
