# worker

BC-250 노드(#1, #2)에서 돌아갈 코드/설정이 여기 들어갈 예정.

**역할 (계획, 부분 구현됨):**
- Ollama + Vulkan 로컬 LLM 추론 서비스 — BC-250 #1에서 이미 설치·검증 완료(Gemma 4 E4B 테스트 성공, 상세: `~/.claude/projects/-home-sim/memory/project_bc250_ollama_vulkan.md`)
- 마스터로부터 컨텍스트 문자열을 받아 stateless하게 추론·응답하는 HTTP API 래퍼(필요 시 Ollama API를 그대로 노출하거나 얇은 래퍼 추가)
- BC-250 #2 — 상태 미확인, 확인 후 #1과 동일 절차 적용 예정

상세 계획: `../PLAN.md`
