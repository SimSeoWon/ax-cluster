> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

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
