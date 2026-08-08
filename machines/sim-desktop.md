# CLAUDE.md — sim-desktop (마스터)

> 🔴 **이 파일은 색인이다.** 매 세션 자동 로드되므로 길이가 곧 모든 작업의 비용이다.
> **놓치면 안 되는 규칙만 여기 두고, 나머지는 [`sim-desktop.d/`](sim-desktop.d/) 로 뺐다.**
> 내용을 늘릴 일이 생기면 여기가 아니라 그쪽 파일에 쓸 것.
>
> 정본은 `~/ax-cluster/machines/sim-desktop.md` 이고 `/home/sim/CLAUDE.md` 는 **심볼릭 링크**다 —
> 일반 파일로 덮어쓰지 말 것. 구조 설명은 [`README.md`](README.md).

## 이 디렉터리에 대해

`/home/sim` 은 **sim-desktop** — 개인 리눅스 홈서버의 홈 디렉터리다. **소프트웨어 저장소가 아니다.**
빌드·린트·테스트 도구가 없다. **코드베이스가 있다고 가정하지 말 것.**

- Host `sim-desktop`, LAN **192.168.0.57** (+ Docker 브리지 172.17–19.0.1)
- Ubuntu 22.04.2 LTS (jammy) · xrdp(3389) 로도 접속 가능
- Locale `ko_KR.UTF-8` — **사용자는 한국어로 소통한다. 한국어로 답할 것.**

## AX 클러스터에서의 역할 — 이 머신이 **마스터**다

프로젝트 저장소는 **여기** `~/ax-cluster` 에 있다 (색인은 `PLAN.md`, 내용은 `docs/`).
사본이 BC-250 #1(`sim@192.168.0.43:~/ax-cluster`)과 GitHub(`SimSeoWon/ax-cluster`,
**private — 유지할 것**. LAN 주소와 방화벽 규칙이 들어 있다)에 있다. 셋을 동기 상태로 유지한다.
보드의 `main` 은 체크아웃돼 있어 push 가 거부되므로 **그쪽은 `git pull`**.
🔴 `~/AgentTest` 는 선행 프로젝트 클론 — **참조 전용. 수정도 push 도 금지.**

```
sim-desktop (this box, 192.168.0.57)  = 마스터: 오케스트레이션, RAG 색인,
                                         온톨로지/그래프, 작업 분배
        │  internal LAN only
        ▼
BC-250 #1 (192.168.0.43)               = 추론 노드: Ollama + Vulkan, stateless
BC-250 #2                               = 🎮 Bazzite 게임 머신 — 추론 노드가 아니다.
                                          전환한다는 건 그 머신을 포기한다는 뜻이다.
                                          2번째 보드가 있다고 가정하지 말 것.
Windows UE5 PC ×2                       = 작업장: 파일 소유, 엔진 실행, 빌드/RunTests,
                                          코드 등록. 둘은 같은 UE5 프로젝트를 만진다.
```

🔴 **추론 엔드포인트는 2개고, 둘 다 보드가 아니다** (2026-08-08 갱신):
**BC-250 #1 (35B pinned)** 와 **RTX 3060 윈도우 PC (14b pinned)**.
각 엔드포인트가 `MAX_LOADED_MODELS=1` 이라 모델 교체는 ~64s(35B)/~36s(14b), 왕복 ~100s 다.
**엔드포인트 하나 안에서의 병렬 추론이나 모델 여러 개 상주를 전제한 설계는 성립하지 않는다.**

### 설계 규칙 (AgentTest 2026-07-07 아키텍처 계승)

- 추론 노드는 **파일을 만지지 않는다** — 텍스트(컨텍스트/코드 조각/diff)만 오간다.
  파일 I/O 와 빌드는 그 파일을 소유한 머신에서 한다.
- 마스터→노드 호출은 **stateless** (Ollama `/api/generate` 의 `context` 필드를 의도적으로 재사용 안 함).
- 검증은 **결정적 게이트(테스트/타입체커/린터)가 LLM 판단보다 우선**한다.
- 🔴 **모델을 BC-250 보드들에 샤딩하지 말 것** — 각 보드는 독립 엔드포인트이고 마스터는 *요청*을
  분산한다. 보드는 1GbE 에 PCIe 슬롯이 없어 텐서/파이프라인 병렬은 대역폭에서 굶는다.

## 세부 문서

| 필요한 것 | 파일 |
|---|---|
| 자체 호스팅 서비스 · 포트 · **🔴 인증 없는 AX 서비스 3종의 방화벽 규칙** | [`sim-desktop.d/services.md`](sim-desktop.d/services.md) |
| BC-250 접근 — SSH · **sudo 가 TTY 없이 걸리는 함정** · 하드웨어 작업 전 정독 의무 | [`sim-desktop.d/bc250-access.md`](sim-desktop.d/bc250-access.md) |
| PATH · **`pkexec` 로 권한 처리** · Python · GPU | [`sim-desktop.d/environment.md`](sim-desktop.d/environment.md) |
| 클러스터 설계 — 확정/미결 | `~/ax-cluster/PLAN.md` → `docs/` |
| 저장소에서 작업할 때의 지침 | `~/ax-cluster/CLAUDE.md` |

## 🔴 작업 기록

`~/claude-workspace/reports/` 에 번호순 작업 리포트를 쌓는다
(BC-250 의 `~/bc250-backup-staging/reports/` 규약과 대응).

- **세션 시작 시 리포트를 정독할 것** — grep 으로 대체 금지. 유사 표현이 걸러져 이미 기록된 것을
  재조사한 사고 이력이 있다.
- **재부팅이 필요하거나 접속을 잃을 위험이 있는 인프라 작업은, 실행 *전에* 명령을 리포트에 먼저 쓰고
  작업 *도중*에도 갱신할 것** — 연결이 끊기면 무엇을 시도했는지 복원할 매체는 파일뿐이다.
- 작업 후 선행 리포트의 "남은 것" 목록도 완료 표시로 갱신할 것.
