# master

192.168.0.57(리눅스 인프라 컴퓨터)에서 돌아갈 오케스트레이션 코드가 여기 들어갈 예정.

**언어: Python 확정** (2026-08-06). 신규 작성이 아니라 **AgentTest 기존 자산 이식**이 주 작업이다.
근거와 상세 배치는 `../PLAN.md` §5.

## 역할

- 작업 분배 (task_queue) — 작업자(윈도우)에게 잡 분배, BC-250 추론 노드로 요청 브로커
- RAG 인덱스(ChromaDB + BM25), 온톨로지/관계그래프, 디지털 트윈
- 컨텍스트 매니페스트 조립 — "소스=정답" 원칙에 따라 실제 소스 본문을 번들
- gajae-code 드라이버 — Deep-Interview/Ralplan/Ultragoal 단계 호출·조율
- Claude / 안티그래비티 API 호출 (검증 단계)
- 추론 노드 응답(stateless) 수신 및 후처리

## 이식 대상 (AgentTest → 여기)

| 컴포넌트 | 규모 | Windows 의존 | 순서 |
|---|---|---|---|
| `mcp/task_queue/` | — | 5줄 | **1** — 루프 중추, 가장 가벼움 |
| `mcp/context_search/` | — | 6줄 | 2 — ChromaDB 인덱스 이관 |
| `watcher/` | 21,171줄 | 19줄 | 3 — 가장 크나 순수 데이터라 기계적 |
| `mcp/master_orchestrator/` 中 오케스트레이션 | — | — | 4 — UE 빌드 부분은 분리 |

**여기로 오지 않는 것** (Windows 잔류): `ue_builder.py` · `ue_test_runner.py` ·
`executor_integration_build.py` · `tdd_dryrun.py` · `mcp/commandlet_runner/` · `worker/` 전체.
통합 빌드 게이트는 인프라에 고정하지 않고 **task_queue 잡으로 큐잉 → UE5 보유 작업자가 claim**하는
CI 러너 패턴으로 분리한다.

## 설계 제약

- **파일을 소유하지 않는다** — 추론 노드와는 텍스트만 왕복. 실제 파일 I/O·컴파일은 작업자(윈도우).
- **추론 요청은 stateless**, **피드백 누적은 git**(`task/<task_id>` 브랜치). 두 경로 분리.
- 검증은 3층 게이트(워커 자기검증 → 상용 모델 문법검사 → 실제 UE5 빌드). `../PLAN.md` §4.3.

상세 계획: `../PLAN.md`
