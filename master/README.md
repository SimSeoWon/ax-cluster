# master

192.168.0.57(리눅스 인프라 컴퓨터)에서 돌아갈 오케스트레이션 코드가 여기 들어갈 예정.

**역할 (계획, 미구현):**
- 작업 분배 (task_queue) — BC-250 워커들에게 잡 claim 방식으로 분배
- RAG 인덱스, 온톨로지/관계그래프, 디지털 트윈
- gajae-code 드라이버 — Deep-Interview/Ralplan/Ultragoal 단계 호출·조율
- Claude / 안티그래비티 API 호출
- 워커 응답(stateless) 수신 및 후처리

상세 계획: `../PLAN.md`
