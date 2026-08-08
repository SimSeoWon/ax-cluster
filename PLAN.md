# AX Cluster — 계획 문서 (색인)

**최종 목표 (AX, AI Transformation):** 언리얼 엔진 5 게임 제작 프로젝트 전체 공정에 AI 활용도를
근본적으로 끌어올리는 것. 단순 코딩 보조를 넘어 온톨로지 기반 디지털 트윈, Unreal MCP(UE 5.8.1+),
코드 작성 보조 에이전트를 하나의 파이프라인으로 통합한다.

**작성일:** 2026-08-05 · **절 단위 분리:** 2026-08-08 (1,839줄 단일 파일 → `docs/` 12개)

> 🔴 **이 파일은 색인이다. 내용은 `docs/` 안에 있다.**
> **§ 번호는 분리 전과 동일하다** — 다른 문서·커밋 메시지의 `§5.5.3-④` 같은 상호참조가 그대로 유효하다.
> 내용을 고칠 때는 `docs/` 쪽 파일을 고치고, 새 절을 만들면 아래 표에 한 줄 추가할 것.

---

## 목차

| § | 문서 | 무엇을 읽게 되나 | 이 절에서 확정된 것 |
|---|---|---|---|
| 1 | [배경](docs/1-background.md) | 이전 프로젝트에서 이어지는 부분과 BC-250 인프라 검증 현황 | ROCm 불가(GFX1013) → Ollama Vulkan 백엔드로 우회 |
| 2 | [아키텍처](docs/2-architecture.md) | 마스터·윈도우 작업장 2대·BC-250 의 역할 분담과 토폴로지 | 파일은 윈도우에, 마스터는 컨텍스트 공급 인프라, BC-250 은 추론 노드 |
| 3 | [미정/다음 단계](docs/3-open-items.md) | 확정분과 미결 과제 현황 — **작업 시작 전 여기부터** | 추론 요청 주체 = 마스터 브로커 |
| 4 | [작업 루프](docs/4-work-loop.md) | 태스크 한 건이 도는 경로와 환각 검증 파이프라인 | 검증 3층 — 층1 자기검증 / 층2 문법·API / 층3 UE5 빌드 |
| 5 | [마스터 오케스트레이션](docs/5-master-orchestration.md) | 언어 선정 근거, 이식 대상·순서, systemd 실행 모델 | Python 확정 + systemd+venv 실행 모델 |
| 5.5 | [프로젝트 격리](docs/5_5-project-isolation.md) | 다중 프로젝트 디렉토리 레이아웃과 마운트 규약 | 다중 디렉토리 · **단일 마운트**(불일치 요청은 409 fail-closed) |
| 6 | [노드 장애·페일오버](docs/6-node-failover.md) | 노드 생존 감시와 원격 전원 복구 | 스트리밍 청크 간격 = 하트비트 (별도 통신 인프라 금지) |
| 7 | [마스터 GPU 증설](docs/7-master-gpu.md) | GTX 1070 Ti 를 RAG 임베딩용 CUDA 로 쓰는 검토 | **미결** — PSU PCIe 보조전원 확인이 선결 |
| 8 | [git 조작 권한](docs/8-git-authority.md) | 사람 세션과 파이프라인의 권한 경계 | 사람 세션은 파괴적 git 금지 / 파이프라인은 task 브랜치만 자율 |
| 9 | [gajae-code(gjc) 배치](docs/9-gajae-code.md) | gjc 를 어디서 돌리나, 왜 14b 로 막혔나 | gjc 는 윈도우 실행 + 층2 에 VERDICT fail-closed 계약 |
| 9.5 | [task_queue 이식](docs/9_5-task-queue.md) | 이식 1단계 결과와 서비스 등록 | 이식 완료 · `ax-task-queue` 가동 · 8101 LAN 한정 |
| 10 | [관련 문서](docs/10-references.md) | 원 설계·리포트·외부 저장소 링크 모음 | — |

---

## 지금 돌고 있는 것 (2026-08-08)

| 서비스 | 포트 | 유닛 | 방어선 |
|---|---|---|---|
| task_queue | 8101 | `ax-task-queue.service` | 🔴 인증 없음 — ufw LAN 한정이 전부 |
| 추론 브로커 | 8102 | `ax-broker.service` | 🔴 인증 없음 — ufw LAN 한정이 전부 |
| 프로젝트 레지스트리(MCP) | 8103 | `ax-projects.service` | 🔴 인증 없음 — ufw LAN 한정이 전부 |

추론 엔드포인트 **2개**: BC-250 #1(35B pinned) · RTX 3060 윈도우 PC(14b pinned).
**`Anywhere` 로 넓히지 말 것** — 세 서비스 모두 인증 계층이 없다.

머신별 운영 가이드는 [`machines/`](machines/README.md), 세션 작업 기록은
`~/claude-workspace/reports/` 와 `sim@192.168.0.43:~/bc250-backup-staging/reports/`.
