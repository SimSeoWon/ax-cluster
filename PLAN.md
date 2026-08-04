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

- [ ] BC-250 #2 현재 상태 확인 (도착/설치/OS 여부) — 2026-07-07 시점엔 "도착 대기 중"이었음, 현재 상태 재확인 필요
- [ ] 마스터(192.168.0.57)↔BC-250 #1 실제 네트워크 stateless 호출 테스트 (지금까진 BC-250 로컬 curl로만 검증)
- [ ] gajae-code를 이 오케스트레이션에 실제로 연결하는 방법 — WebSocket SDK로 마스터가 외부 컨트롤러 역할을 하는 구조가 유력, 상세 설계 필요
- [ ] 온톨로지 기반 디지털 트윈 설계 — 어떤 데이터를 온톨로지화할지 구체화 필요
- [ ] Unreal MCP(5.8.1+) 연동 방식 — 윈도우 UE5 PC 쪽에서 어떻게 노출/호출할지
- [ ] 마스터 쪽 오케스트레이션 언어(Python vs Go) 최종 결정 — 이번 대화에서 둘 다 언급됐으나 확정 안 됨
- [ ] BC-250 #1의 TTM/GTT 캡 상향 — 12B급 이상 모델을 워커로 쓰려면 선행 필요

---

## 4. 관련 문서
- 이 보드(BC-250 #1)의 하드웨어 작업 이력: `~/bc250-backup-staging/reports/`, `~/.claude/projects/-home-sim/memory/`
- AgentTest 2026-07-07 원 설계: `~/bc250-backup-staging/memory/project_agenttest_architecture.md`
- gajae-code: https://github.com/Yeachan-Heo/gajae-code
- AgentTest: https://github.com/SimSeoWon/AgentTest
