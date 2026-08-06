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
│ (작업자)       │     이 문서의 client/ 디렉토리 — 파일을 소유하는 유일한 계층
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
- [~] **BC-250 #1 안정성 검증** — **단기(30분/65사이클) 통과 2026-08-06**: 성공률 100%,
      tok/s 26.57±0.27(1분기↔4분기 변화 0.00%), 커널 오류 0, GTT 7.89GB 고정(GPU 누수 없음).
      리서치 보고서가 경고한 고빈도 크래시 유형은 재현되지 않음. 상세 = 리포트 24 부록 B.
      **⬜ 장시간은 여전히 미검증** — 30분은 long-tail 을 보지 못한다. 특히 시스템 `MemAvailable` 이
      65사이클 동안 약 -620MB 단조 감소(부하 종료 후 소폭 회복)한 것이 미해결 관찰이라,
      무인 24시간 판단 전 수 시간 이상 재실행 필요.
- [ ] **코드 생성 모델 후보 재평가** — `devstral:24b`(Q4_K_M 14GB, SWE-Bench Verified 46.8%, 128K ctx)가
      15.6GiB 에 들어가는 유일한 신규 후보. 단 ① SWE-Bench 는 대부분 Python 저장소라 UE5 C++·매크로/
      리플렉션 체계로의 전이가 불확실 ② Devstral 은 **에이전틱 특화**인데 우리 파이프라인은 골조의
      `[PSEUDO]` 본문만 채우는 제약 생성이라 강점이 발휘될 형태가 아님 ③ 14GB 라 여유가 1.6GB 뿐이라
      컨텍스트 확장 여지가 거의 없음(현 14B 는 6.6GB 여유).
      → 추측 대신 **`bench_quality2.py` UE5 6종 하네스로 동일 잣대 측정**할 것.
      참고: `qwen3-coder` 는 공식 태그 최소 19GB(30B-A3B Q4_K_M)라 **적재 불가**. 7B/14B 밀집 모델이
      존재하지 않으며, 서드파티 저양자화는 오늘 35B-A3B IQ2 에서 확인된 API 환각 리스크가 있어 비권장.
- [x] ~~추론 노드 장애 감지 방식~~ — **스트리밍 하트비트 + 마스터측 Python 래퍼 확정 2026-08-06** (아래 §6)
- [ ] 원격 전원 재투입 수단(스마트 플러그/PDU) — GPU 크래시 시 소프트웨어로 복구 불가 (§6.5)
- [ ] **마스터 GPU 증설(GTX 1070 Ti)** — RAG 임베딩/리랭킹/LoRA 용 CUDA 확보 목적. 선결: PSU 용량 확인 + 드라이버 설치 (아래 §7)
- [ ] BC-250 #2 현재 상태 확인 (도착/설치/OS 여부)
- [x] ~~마스터가 git 변경을 어떻게 감지하나~~ — **Gitea 이벤트 구동으로 확정 2026-08-07** (§5.4.2).
      Gitea 를 마스터가 직접 호스팅하므로 폴링할 이유가 없다. `watch.py` 의 `while True` 폴링 루프는
      이식 대상이 아니다. 상주 프로세스 자체는 여전히 필요(웹훅 수신·task_queue HTTP 서버·RAG).
- [x] ~~`process_lifecycle.py`·`network_firewall.py` 처리~~ — **폐기 확정 2026-08-07** (§5.4.3).
      리눅스 등가물로 고쳐 쓰지 않고 systemd 에 넘긴다.
- [ ] **마스터 실행 모델 — systemd vs Docker Compose** (§5.4.4). 마스터 `~/CLAUDE.md` 규약은 Compose 선호,
      워크로드 성격은 systemd 가 단순. 이식 착수 전 결정 필요
- [ ] **이벤트 큐 설계** (§5.4.5) — 웹훅 전환의 전제조건. 영속 + 단일 소비자 + 중복 합치기.
      `.claude/_regenerate_queue.jsonl` 이 원형. **`task_queue` 와 합치지 말 것**
- [ ] **BM25 원자성 확인** (§5.4.6) — 더블 버퍼가 벡터/태그캐시만 덮고 BM25 는 제자리 갱신이다.
      실사용에서 문제인지 확인 후 판단(추측 금지)
- [ ] **기존 "서버 모드"와의 중복도 판정** (§5.4.7) — `docs/rag-system.md`·`docs/runbook.md` §11 정독 후
      "리눅스에서 서버 모드 구동"인지 재설계인지 결정. 이식 작업량이 크게 달라진다
- [ ] 작업자(윈도우) ↔ 마스터 경로 — AgentTest `task_queue` 를 리눅스 마스터로 이관
- [ ] gajae-code를 이 오케스트레이션에 실제로 연결하는 방법 — WebSocket SDK로 마스터가 외부 컨트롤러 역할을 하는 구조가 유력, 상세 설계 필요
- [ ] 온톨로지 기반 디지털 트윈 설계 — 어떤 데이터를 온톨로지화할지 구체화 필요
- [ ] Unreal MCP(5.8.1+) 연동 방식 — 윈도우 UE5 PC 쪽에서 어떻게 노출/호출할지
- [x] ~~마스터 쪽 오케스트레이션 언어(Python vs Go) 최종 결정~~ — **Python 확정 2026-08-06** (아래 §5)

---

## 4. 작업 루프 확정 (2026-08-06)

> 근거 실측: 리포트 24(속도·인프라), 리포트 25(모델 품질). 둘 다 `~/bc250-backup-staging/reports/`.

### 4.1 용어 — 코드베이스와의 충돌 주의

| 통칭 | 머신 | AgentTest 코드 용어 | **이 저장소 디렉터리** |
|---|---|---|---|
| 작업자 | 윈도우 UE5 PC | **`worker/`** (task_queue claim/write/verify 를 도는 쪽) | **`client/`** |
| 인프라 / 마스터 | 192.168.0.57 | master, `task_queue` 서버 | `master/` |
| 워커(구어) | BC-250 | **추론 노드** — 코드상 `worker` 가 *아님* | `worker/` |

`worker/worker.py` 는 윈도우 PC 에서 도는 코드다. BC-250 을 "워커"라 부르면 코드 탐색 시 오도된다.

**🔴 `worker` 라는 단어가 세 군데서 서로 다른 것을 가리킨다.** 이 저장소의 `worker/` 는 BC-250
추론 노드이고, AgentTest 의 `worker/` 는 윈도우 작업자이며, 후자는 이 저장소에서 **`client/`** 다
(2026-08-07 신설). 코드·문서를 오갈 때 반드시 디렉터리 기준으로 확인할 것.

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
- **⚠️ 코드 기본값이 아직 Gemma다 — 이식 시 반드시 교체할 것.** AgentTest 의 로컬 LLM 기본 모델이
  `gemma4:e4b` 로 하드코딩된 지점이 여럿이다: `watcher/config_init.py:65`(`"local_llm_model": "gemma4:e4b"`),
  `watcher/common.py:92`(`_local_llm_model` 초기값), `watcher/watch.py:141`(`config.get` 폴백).
  **지금 상태로 배선하면 위에서 확정한 코더 모델이 아니라 Gemma 가 호출된다.**
  다행히 `local_llm_model` 설정 키로 교체 가능하게 설계돼 있어 **코드 수정 없이 config 값만 바꾸면 된다**
  (다만 코드상 *기본값*은 여전히 Gemma 이므로, config 를 안 넣으면 조용히 Gemma 로 폴백한다).
  참고로 Gemma 가 나쁜 선택이었던 건 아니다 — 실측 57 t/s 로 14B 의 2배지만, 코딩 특화가 아니라
  UE5 도메인 정확도(=반려율)에서 밀린다(리포트 25).
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
| `watcher/` 전체 | 21,171줄 | 19줄 | git watch · RAG · 온톨로지 · 클래스 그래프. 정리 대상: `review.py`(5) · `network_firewall.py`(4) · `skill_defs_distribute.py`(4) · `process_lifecycle.py`(3) · `watch.py`/`common.py`/`agent_defs.py`(각 1). **⚠️ `process_lifecycle.py` 는 이식이 아니라 폐기 — §5.4** |
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
   **선결: 수명주기 주인 교체** — 현재 `watch.py` 가 자식 프로세스로 띄우고 감시한다(§5.4.3).
   떼어내 독립 서비스로 만드는 것이 이 단계의 실제 작업량이다.
2. `mcp/context_search/` — ChromaDB 인덱스 이관(재색인 필요 여부 확인).
3. `watcher/` — 가장 크지만 순수 데이터라 기계적. 단 **`watch.py` 의 폴링 루프는 그대로 옮기지 않는다**
   — Gitea 이벤트 구동으로 대체(§5.4.2). `process_lifecycle.py`·`network_firewall.py` 는 **폐기**(§5.4.3).
4. `master_orchestrator/` 분할 — 오케스트레이션 부분만 이전, UE 부분은 §5.2-B 로 남기고
   §5.2-C 의 큐 잡 패턴으로 연결.

**이식 시 함께 처리할 설정 변경**
- `local_llm_model` 기본값을 `gemma4:e4b` → **`qwen2.5-coder:14b`** 로 변경 (§4.4 참조).
  config 로 덮어쓰는 것만으로도 동작하지만, 기본값 자체를 바꿔야 설정 누락 시 조용한 Gemma 폴백을 막는다.
- 추론 엔드포인트 기본값 `http://localhost:11434` → BC-250 노드 주소로. 마스터에는 Ollama 가 없다.

**주의:** 위 줄 수/의존 집계는 2026-08-02 클론 기준이다.
→ **2026-08-07 마스터에서 재확인 완료**: 199개 `.py` / 67,038줄 / Windows 의존 **93줄**. 수치 유효.
마스터 클론 위치는 `/home/sim/AgentTest`(**참조용 — 수정하지 않는다**), 이 저장소는 `/home/sim/ax-cluster`.

### 5.4 마스터 실행 모델 — 폴링 데몬이 아니다 (2026-08-07)

AgentTest 를 그대로 옮기면 안 되는 이유가 여기 있다. **배포 형태와 실행 모델이 마스터에서는 성립하지 않는다.**

#### 5.4.1 AgentTest 의 현재 형태 (실측)

`build.bat` 이 PyInstaller `--onefile` 로 **exe 12종**을 빌드해 `AgentWatch.zip` 으로 배포하고,
팀원이 **UE5 프로젝트 루트에 압축 해제**한다. `watch.exe`(데몬) · `worker.exe` · MCP 서버 10종
(`context_search` `log_analyzer` `crash_analyzer` `commandlet_runner` `agy_query` `redmine_tracker`
`code_recipes` `task_queue` `master_orchestrator` `local_llm_runner`).

`watcher/watch.py main()` 이 `while True` 로 `poll_interval` 초마다 git fetch/pull → 새 커밋 감지 →
처리. MCP 서버와 task_queue 는 **자식 프로세스로 띄우고 `.poll()` 로 생존 감시**한다
(`common._server_proc`, `common._task_queue_proc`). `config.json` 은 PC 별 파일이라 재배포에도 보존된다.

**마스터에는 UE5 프로젝트 루트도 팀원별 사본도 없다.** 배포 단위(zip+exe)와 수명주기 관리를
그대로 옮길 수 없다.

#### 5.4.2 폴링 → 이벤트 구동 (Gitea 가 같은 박스에 있다)

`watch.exe` 가 폴링하는 건 **팀원 PC 가 git 서버 입장에서 외부인이라 알림받을 방법이 없기 때문**이다.
마스터는 반대로 **Gitea 를 직접 호스팅**한다(`gitea.service`, :3000). 알림을 받을 수 있다.

| | 폴링 (AgentTest) | 이벤트 (마스터) |
|---|---|---|
| 감지 지연 | `poll_interval` 초 | 즉시 |
| 유휴 시 비용 | 계속 fetch | 0 |
| 튜닝 | 간격 결정 필요 | 불필요 |

- **Gitea 웹훅** — push 시 지정 URL 로 HTTP POST. 같은 박스라 `localhost` 로 쏘면 네트워크 신뢰성 문제 없음.
- **`post-receive` 훅** — push 순간 서버에서 스크립트 직접 실행. 네트워크조차 안 탄다.
  ⚠️ 단 **훅 안에서 무거운 작업(RAG 색인 등)을 하면 그동안 push 가 멈춘다.** 훅은 알림만 던지고 즉시 종료할 것.

**⚠️ 데몬이 없어지는 게 아니다.** 사라지는 건 폴링 루프뿐이고 상주 프로세스는 여전히 필요하다:
① 웹훅을 받을 쪽이 떠 있어야 하고 ② `task_queue` 는 작업자가 claim 하러 붙는 **HTTP 서버**라
태생이 상주 서비스이며 ③ RAG 인덱스·추론 브로커도 계속 살아 있어야 한다.

**작업자(윈도우) 쪽은 그대로다** — `worker.exe` 는 여전히 외부인이라 task_queue 에 폴링으로 붙는다.
폴링이 없어지는 것은 마스터 한정.

#### 5.4.3 수명주기는 systemd 가 가져간다 — `process_lifecycle.py` 는 폐기

리눅스의 데몬 = **systemd 서비스**. 이 박스의 `gitea.service` 가 정확히 그 형태다.
**PyInstaller 빌드는 불필요** — exe 로 묶는 건 "팀원 PC 에 Python/의존성이 없어서"인데
마스터는 통제 가능한 한 대뿐이라 venv 로 충분하다.

```ini
# /etc/systemd/system/ax-task-queue.service (예시)
[Service]
ExecStart=/home/sim/ax-cluster/.venv/bin/python -m master.task_queue
Restart=always
User=sim
[Install]
WantedBy=multi-user.target
```

| `watch.py` 가 손수 하던 것 | systemd |
|---|---|
| 자식 프로세스 `.poll()` 생존 감시 | `Restart=always` |
| Job Object 로 고아 프로세스 정리 (**Windows 전용**) | cgroup 자동 |
| 로그 파일 관리 | journald (`journalctl -u`) |
| 기동 순서 조율 | `After=` / `Requires=` |
| 포트 점유 해제·방화벽 규칙 (`network_firewall.py`, **Windows 전용**) | firewalld/ufw 로 별도 관리 |

**→ `process_lifecycle.py`·`network_firewall.py` 는 리눅스 등가물로 고쳐 쓸 게 아니라 폐기하고
systemd 에 넘긴다.** 각 컴포넌트를 독립 유닛으로 두면 §5.3-1 의 "task_queue 수명주기 주인" 문제도 사라진다.

#### 5.4.4 미결 — systemd vs Docker Compose

`~/CLAUDE.md`(마스터) 규약은 **"새 서비스는 Docker Compose 선호"**다(n8n·Redmine 이 그 패턴).
반면 오케스트레이션 코드는 BC-250 과 LAN 통신하고 로컬 git/Gitea 를 봐야 해 systemd 가 단순하다.
**아직 정하지 않았다** — §3 미결 항목 참조.

#### 5.4.5 🔴 폴링이 공짜로 주던 3가지 — 웹훅으로 가면 직접 만들어야 한다

**기존 코드가 폴링 루프 자체를 안전장치로 쓰고 있다.** 그대로 이식하면 이벤트가 조용히 유실된다.

```python
# watcher/watch.py:646
if not _processing_lock.acquire(blocking=False):
    # 이전 사이클이 아직 처리 중 → 이번 틱은 건너뜀
```

폴링에서 **건너뛰는 건 안전하다** — 60초 뒤 다음 틱이 어차피 다시 본다.
웹훅에서 건너뛰면 **그 이벤트는 영영 사라진다.** 아무도 다시 알려주지 않는다.

| 성질 | 폴링에서 | 웹훅에서 | 대책 |
|---|---|---|---|
| **직렬화** | `_processing_lock` 으로 한 번에 한 사이클 | 동시 도착 시 겹침 | 단일 소비자 |
| **재시도** | 놓친 틱은 다음 틱이 처리 | 놓치면 유실 | **영속 큐** |
| **합치기** | 60초 안의 push 10개 = 재색인 1회 | push 10개 = 재색인 10회 | 중복 합치기(coalescing) |

세 번째가 특히 아프다 — 커밋을 연달아 밀면 무거운 RAG 재색인이 그 횟수만큼 돈다.

**→ 웹훅 전환의 전제조건은 영속 큐 + 단일 소비자다. 선택이 아니다.**
`post-receive` 훅은 큐에 넣고 즉시 종료한다(§5.4.2 의 "push 를 막지 말 것"과 같은 요구).

**⚠️ `task_queue` 와 합치지 말 것** — 성격이 다르다.

| | `task_queue` (기존) | 이벤트 큐 (신규) |
|---|---|---|
| 소비자 | 다수 (윈도우 작업자들) | **정확히 하나** (마스터 내부) |
| 필요한 것 | claim · lease · fencing · reclaim | 순서 보장 · 중복 합치기 |
| 현재 상태 | `idx.lock`(RLock)으로 촘촘히 보호됨 | 없음 |

`task_queue` 의 claim/lease 는 "외부 소비자 여럿이 경쟁한다"는 전제로 만든 물건이라
로컬 단일 소비자에는 과하다.

**원형으로 쓸 것이 이미 있다** — `.claude/_regenerate_queue.jsonl`.
`skill_defs_ontology.py:97` 이 "실제 LLM 재생성은 다음 폴링 사이클(최대 60초)에서 자동 수행"이라
적어둔 그 파일 큐다. 여기서도 폴링 사이클이 실행기 노릇을 하고 있다.

#### 5.4.6 읽기/쓰기 충돌은 이미 해결돼 있다 — 더블 버퍼

**클라이언트 요청(읽기)과 인덱스 갱신(쓰기)을 한 줄로 세울 필요는 없다.**
`mcp/context_search/double_buffered_index.py` 가 이미 원자적 교체를 한다.

| 메서드 | 동작 |
|---|---|
| `begin_update(fresh=False)` | `_write_lock` 획득 후 Live→Work 복사. **임베딩까지 복사해 재계산 없음** |
| `commit_update()` | `_swap_lock` 안에서 Live↔Work 교체 + **태그 캐시 동시 교체** |
| `rollback_update()` | 실패 시 **Live 무영향** |
| `live` / `tag_cache` | 검색은 항상 Live 에서 즉시 응답 — **블로킹 없음** |

ChromaDB 컬렉션 `context_a` / `context_b` 를 번갈아 쓴다. 즉 재색인이 도는 동안에도
개발자는 기다리지 않고, **반쯤 갱신된 인덱스를 보는 일도 없다.**

**또 하나 이미 있는 조율** — `watch_state._has_active_distribute_work()`:
작업자에게 `in_progress` 작업이 있으면 **watcher 메인 루프가 일시 중지**한다.
docstring 이 밝힌 이유 두 가지: ① feature 브랜치 작업 중 main 인덱싱은 무의미
② **워커들과 git lock 경쟁 방지**. 즉 "클라이언트 작업이 진행 중이면 인덱스 갱신이 양보"가
이미 설계돼 있다. 이 게이트는 이식하되, "이번 틱 건너뜀"이 아니라 **큐에서 대기**로 바꿔야 한다(§5.4.5).

**⚠️ 단 더블 버퍼가 전부를 덮지는 않는다 — 확인할 것 3가지**

1. **BM25 는 더블 버퍼가 아니다.** `commit_update()` 주석: `# BM25 는 디스크 영속 + in-place 증분 — swap 불필요`.
   벡터 컬렉션과 태그 캐시는 원자적으로 교체되지만 BM25(SQLite FTS5)는 제자리 갱신이다.
   `_apply_bm25_incremental()` 도중 동시 검색이 **부분 갱신된 BM25 + 옛 Live 벡터**를 함께 볼 수 있다.
   실사용에서 문제가 되는지 **확인 후 판단할 것**(추측 금지).
2. **더블 버퍼는 인덱스 내부 일관성만 푼다.** §5.4.5 의 이벤트 유실은 그대로 남는다.
   `begin_update()` 의 `_write_lock.acquire()` 는 **블로킹**이라 겹친 갱신은 유실 대신 대기하지만,
   그 대기가 웹훅 HTTP 커넥션을 잡고 있으면 안 된다 — 큐가 여전히 필요한 이유.
3. **서버 모드 전용 기능이다.** docstring 이 "서버 모드에서 무중단 벡터 인덱싱"이라 명시한다.
   마스터가 쓸 모드가 정확히 그 모드다 — 유리한 조건이다.

#### 5.4.7 재확인할 것 — 마스터가 만들려는 게 기존 "서버 모드"와 얼마나 겹치나

AgentTest `CLAUDE.md` 는 배포 모드를 **두 가지**로 적고 있다:

> 1. **로컬 모드**: 각 팀원 PC 에서 `watch.exe` 가 Git 감시 + 컨텍스트 생성 + 벡터 인덱싱을 로컬 수행
> 2. **서버/클라이언트 모드**: 공용 서버 1대에서 Git 감시 + RAG 중앙 관리, 팀원 PC 의 Claude Code 는 HTTP 로 RAG 검색

**2번이 우리가 마스터에서 하려는 것과 상당히 겹친다.** 이식 착수 전
`docs/rag-system.md`(context_search 3모드·HTTP API·더블 버퍼링)와
`docs/runbook.md` §11(인프라 컴퓨터 하드웨어 교체 — 익스포트/임포트)을 읽고,
**"리눅스에서 서버 모드를 돌리는 것"에 가까운지 재설계인지 판정할 것.**
전자라면 §5.3 이식 순서의 작업량이 크게 줄어든다.

---

## 6. 추론 노드 장애 감지·페일오버 (2026-08-06)

### 6.1 기존 하트비트로는 안 덮인다

AgentTest 에 이미 하트비트/lease 회수가 있다 — `worker/heartbeat.py`(directive `pause`/`resume`/
`drain`/`abort` 수신, `lease_lost` 시 진행 중 LLM kill) + `task_queue/reclaim.py`(`_reclaim_loop` 가
lease cutoff 로 회수, `_verify_loop` 가 stuck alert). **단 이건 작업자(윈도우) 계층이다.**

BC-250 은 task_queue 에 claim 하지 않는 **HTTP 추론 엔드포인트**라 하트비트를 보낼 주체가 아니다.
노드가 행 걸리면:

1. 마스터의 HTTP 요청이 응답 없이 매달림
2. 작업자는 **멀쩡히 살아서** 마스터 응답 대기 → **하트비트는 계속 정상 전송**
3. 따라서 lease 가 만료되지 않아 **회수 로직이 안 뜬다**
4. 태스크는 조용히 멈추고, `_verify_loop` 의 stuck alert 가 임계 시간 뒤에나 알림

즉 기존 메커니즘은 "작업자 죽음"을 잡지 **"추론 노드 죽음"을 못 잡는다.**

### 6.2 설계 — 스트리밍이 곧 하트비트

```
마스터 ──assign──▶ 노드 #1
                    │ stream:true 로 토큰 청크가 계속 흘러나옴 = 살아있다는 신호
                    ▼
마스터 ── 청크 간격 감시 ── 임계 초과 ──▶ 연결 끊고 노드 #N 으로 재할당
```

**별도 통신 인프라를 만들지 않는다.** Ollama `"stream": true` 의 토큰 청크가 그대로 생존 신호가 된다
— **작업 산출물 자체가 하트비트**다. 노드에 에이전트 코드를 심을 필요가 없어
"노드는 상태도 코드도 갖지 않는다"는 원칙과 [[feedback_no_communication_infra_creep]] 을 함께 지킨다.

### 6.3 임계값 — 실측 기반 (2026-08-06, `qwen2.5-coder:14b`)

`~/claude-workspace/bench_stream_gap.py` 로 측정. **두 구간을 반드시 분리해야 한다.**

| 구간 | 실측 | 임계값 제안 |
|---|---|---|
| 생성 중 청크 간격 | p50 **38.7ms** / p95 47.2ms / p99 51.0ms / 최대 51.1ms | **2s** (관측 최대의 ~40배) |
| 첫 청크까지 (웜, 모델 적재됨) | **1.07s** | — |
| 첫 청크까지 (콜드 로드) | **36.4s** (14B 최초 적재) | **120s 이상** |
| 첫 청크까지 (긴 프롬프트 prefill) | **38.1s** (2.5k 토큰 상당) | (위에 합산) |

**⚠️ 임계값 하나로 뭉뚱그리면 정상 동작을 죽음으로 오판한다.** 콜드 로드(36s) + 긴 prefill(38s) 가
겹치면 첫 청크까지 **70초 이상**이 정상이다. 반면 일단 생성이 시작되면 간격이 40ms 수준으로
매우 규칙적이라, 생성 중 2초 무응답은 명백한 이상이다.

### 6.4 Python 추론 클라이언트 래퍼 — `master/` 에 둔다

Ollama 를 그대로 호출하지 않고 **얇은 Python 래퍼를 거친다.** 감시·검증·재시도를 걸 지점이 필요하다.

**위치는 마스터 측**이다(노드 측 아님). 근거: ① 노드를 일회용으로 유지해야 재구축이 쉽다
② 검증에 필요한 태스크 컨텍스트(동결 선언·매니페스트)가 마스터에 있다 ③ 노드 간 페일오버는
본질적으로 마스터의 책임이다.

**책임**

| 구분 | 내용 |
|---|---|
| 생존 감시 | 스트리밍 청크 간격 감시(§6.3 2구간 임계), 초과 시 연결 종료 + 재할당 |
| 노드 상태 | 주기적 헬스 프로브(`/api/tags`) → 죽은 노드로 라우팅 중단. `watcher/common_utils.py` 의 `local_llm_health_check_one_shot`(`ollama_down` 판별) 재사용 |
| 요청 정규화 | `"think": false` 주입(35B 필수), `num_predict`·`temperature` 정책, 타임아웃 |
| 응답 후처리 | 마크다운 펜스 제거, `[PSEUDO]` 잔재 검사 |
| 사전 검증 | 동결 인터페이스 위반 검사 — 실 파이프라인의 `worker/validator._frozen_interface_violation` 과 동일 규칙을 여기서도 1차 적용해 왕복 낭비 차단 |
| 라우팅 | 모델↔노드 고정 배정(§4.4) 반영, 모델 전환 비용 36초 회피 |
| 계측 | 토큰 수·tok/s·첫 청크 지연 기록 → 임계값 재조정 근거 |

### 6.5 한계 — 이것으로 해결되지 않는 것

- **재할당할 곳이 있어야 한다.** BC-250 #2 가 없으면 감지는 되지만 페일오버는 불가능하다.
- **노드는 스스로 회복하지 못한다.** GPU 크래시 = 호스트 하드 행(단일 APU, 드라이버가 GPU 리셋 불가).
  소프트웨어로는 불가하고 **스마트 플러그/네트워크 PDU 등 원격 전원 재투입 수단**이 필요하다.
- **좀비 응답**: 늦게 살아난 노드가 응답을 보내도 마스터가 이미 재할당했으면 무시하면 된다.
  stateless HTTP 라 git push 하는 좀비 워커(C.2)만큼 위험하지 않아 epoch fencing 까지는 불필요하다.
- **빈도는 여전히 미지수.** 장시간 안정성 검증(§3) 이 선행되어야 한다. 주 1회면 스마트 플러그로 충분하고,
  하루 여러 번이면 이 보드를 무인 루프에 넣는 것 자체를 재고해야 한다.

---

## 7. 마스터 GPU 증설 검토 — GTX 1070 Ti (2026-08-06, 🔍 검토 단계)

> **아직 실행 안 함.** 사용자가 보유 중인 유휴 1070 Ti 를 마스터(192.168.0.57)에 증설하는 안.
> 선결 조건(PSU 용량 확인·드라이버 설치)이 남아 있어 확정이 아니다.

### 7.1 추론 노드 증설로는 부적합 — 두 가지 제약

**① 목표 모델이 안 들어간다**

| | 값 |
|---|---|
| 1070 Ti VRAM | **8GB** |
| `qwen2.5-coder:14b` (Q4_K_M) | **8.9GB** |

코드 생성 주력으로 확정한 모델(§4.4)이 **애초에 적재 불가**다. 시스템 RAM 부분 오프로드는
PCIe 를 타서 속도가 급락하므로 실용적 대안이 아니다.

**② 대역폭이 BC-250 보다 낮다**

`1070 Ti ~256 GB/s` < `BC-250 ~357 GB/s(실효)`. 생성 속도는 대역폭 바운드이므로
(§4 실측: 14B 26 t/s = 이론 40 t/s 의 65%), 양쪽에 다 올라가는 소형 모델이라면
**BC-250 이 오히려 빠르다.** "BC-250 과 같은 일을 나눠 한다"는 그림은 성립하지 않는다.

### 7.2 대신 BC-250 이 **원천적으로 못 하는** 일이 있다 — CUDA

BC-250 은 gfx1013 이라 ROCm 이 사실상 불가하고 **Vulkan 추론만** 된다. 1070 Ti 의 가치는
속도가 아니라 **CUDA 생태계 확보**다.

| 용도 | 근거 |
|---|---|
| **RAG 임베딩 가속** | 마스터가 ChromaDB + ONNX `all-MiniLM-L6-v2` 를 돌리는데 현재 **CPU**. GPU 이관 시 인덱싱 대폭 단축. **RAG 는 원래 마스터 몫**(2026-07-07 아키텍처)이라 설계 위반이 아님 |
| **리랭킹 모델** | cross-encoder 리랭킹은 GPU 없이는 실용성이 없다. RAG 품질 향상의 확실한 수단 |
| **LoRA 파인튜닝** | κ.7 이 "로컬 오픈웨이트는 LoRA 가능하나 **학습은 별도 CUDA 필요, BC-250 은 ROCm 부재로 비현실적**"이라 명시. 이게 그 CUDA 박스가 된다 |
| 소형 모델 오버플로 | 7~8B Q4 는 8GB 에 여유. 쿠킹용 보조 엔드포인트로 활용 가능 |

**즉 BC-250 과 경쟁이 아니라 보완이다.** 추론 노드는 BC-250, 마스터는 RAG/학습 가속기라는 역할 분담.

### 7.3 선결 조건

1. **PSU 용량 확인** — 1070 Ti 는 8핀 PCIe 보조전원 + TDP 180W. X99(HUANANZHI X99-QD4) + Xeon E5-2620 v3
   구성에 여유가 있는지 **물리 확인 필요**(소프트웨어로 판별 불가).
2. **NVIDIA 드라이버 설치** — 현재 마스터에 nvidia 모듈이 하나도 로드돼 있지 않다(`lsmod | grep nvidia` = 0).
   드라이버 + CUDA 툴킷 설치가 선행.
3. **전력 영향** — 마스터는 24시간 가동이므로 유휴 +10~15W 가 상시 추가된다.
   BC-250 유휴 80W 대비 작지만, 상시 비용이라는 점은 동일.

### 7.4 한계

Pascal 세대라 BF16 미지원, FP16 처리율이 낮다. **양자화 추론에는 실질 영향이 작지만**
학습은 최신 카드 대비 느리다. 다만 "LoRA 를 시도할 수 있느냐 없느냐"의 차이가 크다 —
BC-250 으로는 시도 자체가 불가능하다.

---

## 8. 관련 문서
- 이 보드(BC-250 #1)의 하드웨어 작업 이력: `~/bc250-backup-staging/reports/`, `~/.claude/projects/-home-sim/memory/`
- AgentTest 2026-07-07 원 설계: `~/bc250-backup-staging/memory/project_agenttest_architecture.md`
- gajae-code: https://github.com/Yeachan-Heo/gajae-code
- AgentTest: https://github.com/SimSeoWon/AgentTest
- 2026-08-06 인프라 작업(헤드리스·TTM/GTT·마스터 링크·방화벽·속도 벤치):
  `~/bc250-backup-staging/reports/24-ttm-gtt-tuning-headless-cluster-link.md`
- 2026-08-06 모델 품질 비교(UE5 태스크 6종): 
  `~/bc250-backup-staging/reports/25-model-quality-comparison-14b-vs-35b.md`
- 마스터(57)측 사본: `sim@192.168.0.57:~/claude-workspace/reports/`
