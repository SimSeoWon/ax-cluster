# AX Cluster 전반적 기술 아키텍처 및 서브시스템 정밀 분석

> 작성: Antigravity (Gemini 4 Argon Medium) · 2026-11-14
> 자료: `README.md`, `PLAN.md`, `docs/2-architecture.md`, `docs/4-work-loop.md`, `docs/12-multi-project.md`, `docs/13-request-tagging.md`, `docs/16-worker-orchestrator-mode.md`, `docs/17-review-queue.md`, `docs/orchestrator-rules.md`, `docs/issue-spec.md`, `docs/orchestrator-handoff.md`
> 목적: AX 클러스터(`~/ax-cluster`)의 하드웨어 토폴로지, 디지털 트윈 파이프라인, 7단계 분산 코딩 루프, 멀티 에이전트 지휘·교차 검증 체계, 다중 프로젝트 격리 구조 및 현재 진화 과제를 종합 정리함.

---

## 목차

1. [시스템 정의 및 핵심 설계 철학](#1-시스템-정의-및-핵심-설계-철학)
2. [하드웨어 토폴로지 및 노드별 실행 책임](#2-하드웨어-토폴로지-및-노드별-실행-책임)
3. [핵심 서브시스템 4대 기둥](#3-핵심-서브시스템-4대-기둥)
   - 3.1 [이벤트 구동 디지털 트윈 파이프라인](#31-이벤트-구동-디지털-트윈-파이프라인)
   - 3.2 [사용자 확정 7단계 분산 작업 루프와 타입별 검증 게이트](#32-사용자-확정-7단계-분산-작업-루프와-타입별-검증-게이트)
   - 3.3 [멀티 에이전트 지휘 교대 및 교차 계열(Cross-Family) 견제](#33-멀티-에이전트-지휘-교대-및-교차-계열cross-family-견제)
   - 3.4 [다중 프로젝트 단일 마운트 격리 및 선언형 배달](#34-다중-프로젝트-단일-마운트-격리-및-선언형-배달)
4. [저장소 패키지 구조 및 상주 서비스 맵](#4-저장소-패키지-구조-및-상주-서비스-맵)
5. [기술적 강점 및 현재 진화 중인 과제](#5-기술적-강점-및-현재-진화-중인-과제)
6. [근거 문서 및 소스 색인](#6-근거-문서-및-소스-색인)

---

## 1. 시스템 정의 및 핵심 설계 철학

**AX Cluster**는 1인 개발자가 집 안의 이기종 멀티 머신(Linux 마스터 서버 1대 + Windows PC 2대 + AMD BC-250 보드 1대)을 묶어 **① 코드베이스의 디지털 트윈(관계 그래프·컨텍스트 문서·하이브리드 검색·온톨로지)을 자동 구축**하고, **② 프로젝트 타입(`kind`)별 결정론적 검증 게이트와 교차 계열(Cross-Family) AI 오케스트레이션으로 분산 코딩을 수행**하는 자체 호스팅(Self-hosted) 분산 AI 소프트웨어 팩토리다(`README.md:3-6`, `PLAN.md:3-11`).

시스템 전체를 관통하는 5대 엔지니어링 원칙은 다음과 같다:

1. **마스터는 컨텍스트·큐·검증 인프라이지 작업장이 아니다 (`README.md:139-140`)**:
   - 무거운 파일 I/O, 엔진 빌드(UE5), 런타임 테스트는 파일을 소유한 워커/요청자 머신에서 수행하고, 마스터(`.57`)는 디지털 트윈에서 관련 컨텍스트를 조립·중개하며 게이트를 관장한다.
2. **분산이 주는 가치는 처리량(Throughput)이 아니라 증분(Incremental Progress)이다 (`README.md:122-125`, `PLAN.md:60-62`)**:
   - 모든 조각 작업이 결정론적 게이트(층1·층2·층3)를 통과해 **"항상 컴파일·검증되는 상태로 쌓인다"**는 점이 분산 파이프라인의 핵심 가치다.
3. **읽어서 확인하지 말고 돌려서 확인한다 (`docs/orchestrator-rules.md:41-42`)**:
   - 에이전트의 자가 완료 보고나 문서상 기록을 그대로 믿지 않고, 실제 실행 결과·프로세스 기동 시각(`ExecMainStartTimestamp`)·파일 해시·Redmine 및 Git 실물 상태로만 판정한다.
4. **필수 과정과 불변식은 산문이 아니라 Python 코드로 강제한다 (Fail-Closed)**:
   - 사실 게이트(식별자 환각 적발), 층1(인터페이스 동결), 요청 태그 대조(`MOUNT`/`STAMP`), Epoch Fencing 등 핵심 안전장치는 모두 코드로 강제하며 미확인 상태는 통과시키지 않는다.
5. **문서는 지도(Navigation)이며 수치는 단일 정본에서만 읽는다 (`README.md:134-137`, `PLAN.md:63-67`)**:
   - 일감 진행률 분자/분모는 Redmine(`:8080`)에서만 읽고, 테스트 개수는 테스트 러너와 `tests/integration/checks.json`으로만 검증하여 문서와 실제 상태의 표류(Drift)를 원천 차단한다.

---

## 2. 하드웨어 토폴로지 및 노드별 실행 책임

2026-11-07 사용자 결정으로 확정된 클러스터 내 4대 머신의 역할과 책임 경계는 다음과 같다(`AGENTS.md:43-55`, `README.md:6-18`):

| 노드 | 호스트 / OS | 하드웨어·환경 특성 | 클러스터 역할 및 실행 책임 |
|---|---|---|---|
| **`.57`** | `sim-desktop`<br>(Ubuntu 22.04) | 리눅스 홈서버 | **인프라 마스터**: Gitea, Redmine(`:8080`), 작업 큐(`:8101`), 추론 브로커(`:8102`), 프로젝트 레지스트리·MCP·웹UI(`:8103`), 색인기·리뷰 큐·후속 처리 타이머 상주.<br>`AXCluster` 프로젝트 마운트 시에는 **요청자(Requester)** 겸 통합자 역할을 수행. |
| **`.2`** | Windows 워커<br>(계정 `janus`) | RTX 3060 + UE 5.8 | **보조 워커 + 로컬 추론 노드**: 마스터가 파견한 조각 구현 수행.<br>`unreal` 프로젝트의 **층3(UE5 빌드 + `RunTests`) 판정 전담**.<br>로컬 LLM(`gemma4:e4b`, `qwen2.5-coder:14b`) 추론 서빙. |
| **`.33`** | Windows 작업기<br>(계정 `user`) | 사람의 주 개발 PC | **사용자 작업 PC (게임 요청자)**: Unreal 게임 프로젝트를 개발·요청하고 골조 작성 및 ⑺ 전진·finalize 통합을 수행.<br>단, `AXCluster` 마운트 시에만 게임 트리와 분리된 `C:\trunk\AXCluster`에서 승인된 보조 워커 역할을 수행. |
| **`.43`** | `BC-250 #1`<br>(계정 `sim`) | Fedora Headless<br>(AMD GFX1013) | **보조 워커 + 로컬 추론 노드**: ROCm 미지원 아키텍처를 Ollama Vulkan 백엔드로 구동(`PLAN.md:82`).<br>조각 구현 워커 및 로컬 추론 엔드포인트(35B/로컬 모델) 역할 수행. |

### 네트워크·보안 및 무상주(Daemonless) 원격 실행 구조
- **이중 방어선 (`README.md:253-256`, `PLAN.md:134-135`)**:
  - 1차 방어선: `ufw` 방화벽을 통한 LAN(`192.168.0.0/24`) 한정 접근 제어.
  - 2차 방어선: `~/.config/ax-cluster/token`(`0600`) 기반 베어러 토큰 인증(토큰 부재 시 서비스 기동 자체를 거부하는 fail-closed). `:8103`의 조회용 웹 UI와 `/api/v1`은 1인 다기계 열람 편의를 위해 공개하되, 제어 표면(`/control/*`)은 요청자 토큰 전용(무인증 `401`, 워커 토큰 `403`)으로 격리되어 있다(`docs/16-worker-orchestrator-mode.md:241-248`).
- **워커 무상주 및 마스터 중개 (`docs/12-multi-project.md:9-16`, `README.md:127`)**:
  - 워커 머신에는 큐를 폴링하는 상주 프로세스(cron, schtasks, 빌드 데몬)를 일절 두지 않는다(`#320`, `#860`).
  - 워커에는 큐 토큰조차 배포하지 않으며, 마스터(`.57`)가 SSH로 작업을 밀어 넣고 하트비트와 커밋 회수를 직접 중개한다.
  - Windows 워커(`.2`, `.33`)에서 Codex CLI를 원격 실행할 때는 SSH Session 0의 Window Station/Desktop 권한 한계(`0xC0000142`)를 해결하기 위해 `workspace-write` + `windows.sandbox="unelevated"` + `network_access=true` 설정과 `/IT /RL LIMITED` 예약 런처로 로그인 사용자 세션에서 실행한다(`AGENTS.md:124-129`, `docs/16-worker-orchestrator-mode.md:181-198`).

---

## 3. 핵심 서브시스템 4대 기둥

### 3.1 이벤트 구동 디지털 트윈 파이프라인

코드가 Gitea에 push되면 사람의 개입 없이 디지털 트윈(그래프·컨텍스트·검색 색인·온톨로지)이 갱신되는 파이프라인이다(`README.md:72-81`, `README.md:149-185`).

```
Gitea push ──► post-receive 훅 ──► 이벤트 스풀 ──► ax-indexer.path (inotify)
                                                       │
               ┌───────────────────────────────────────┴───────────────────────────────────────┐
               ▼                                       ▼                                       ▼
   [1. 관계 그래프 증분]                   [2. 컨텍스트 MD 합성]                   [3. 비동기 리뷰 큐 등재]
   master/graph/ (LLM 0)                   master/context_synth/                   master/context_synth/review_queue.py
   · tree-sitter C++ / UE 매크로           · 브로커(8102) 경유 gemma4:e4b          · 색인 스레드는 기다리지 않고
   · 상속 그래프 + #include 의존성         · σ.7 펜스 제거 + 저장 전 형식 게이트     커밋 전체 변경분만 큐에 등록
                                           · [사실 게이트] 주석에만 있거나
                                             소스에 없는 식별자 주장 결정적 거부
                                                       │
                                                       ▼
                                           [4. 하이브리드 재색인 & A/B 교체]
                                           master/context_search/
                                           · 벡터: fastembed 다국어 384차원 (## 요약 절만)
                                           · 키워드: SQLite FTS5 단어 + 한글 Trigram
                                           · A/B 더블버퍼 포인터 무중단 교체
```

1. **색인 일시정지 게이트 (`master/events/gate.py`)**:
   - 작업 큐에 진행 중인 분산 작업(`in_progress`)이 있으면 색인기가 로컬 LLM 추론 자원을 경합하지 않도록 즉시 멈추고 종료 코드 `4`(`SuccessExitStatus=4`)로 나간다(`README.md:183-185`, `PLAN.md:129-130`). 미뤄진 색인은 10분 주기의 `ax-indexer.timer`가 따라잡는다.
2. **사실 게이트 기반 환각 차단 (`master/context_synth/verify.py`, `master/ontology/verify_facts.py`)**:
   - 로컬 LLM이 합성한 컨텍스트 문서나 온톨로지 문서에서 실제 소스 코드에 존재하지 않는 식별자(또는 주석에만 적힌 식별자)나 허위 호출 관계를 주장하면 저장 전에 결정론적으로 적발해 거부한다(`README.md:77`, `README.md:163`, `README.md:173`).
3. **한국어 친화적 하이브리드 검색 (`master/context_search/`)**:
   - PyTorch 없이 구동되는 ONNX 기반 `fastembed`(다국어 384차원) 벡터 검색과, SQLite FTS5 단어 + **한글 Trigram 색인(`bm25.py`)**을 RRF(Reciprocal Rank Fusion)로 결합한다(`README.md:150-153`).
   - `[클래스명]` 대괄호 구문과 시소러스(`thesaurus.py`)를 통해 도메인 용어를 확장하며, 한국어 조사나 짧은 별칭으로 인한 오확장을 막는 가드가 내장되어 있다(`README.md:154-155`).
   - 모든 검색은 `/rag-logs`에 사용자 원문·확장 질의·반환 스냅샷·채널 점수로 기록되어 사후 정량 평가(`Hit@k`)의 기반이 된다(`README.md:324-342`).
4. **무의존성 온톨로지 및 잠금 보호 (`master/ontology/`)**:
   - 외부 PyYAML 없이 자체 파서/직렬화기(`yaml_io.py`)로 도메인 계층(L1/L2/L3)과 불변식(Invariants)을 관리한다.
   - 사용자가 편집한 항목은 자동으로 잠금(`locked`/`protected`) 처리되어, 이후 자동 재생성이나 익스포트/임포트 병합(`transfer.py`)이 사람의 검수 결과를 덮어쓰지 못한다(`README.md:166-177`).

---

### 3.2 사용자 확정 7단계 분산 작업 루프와 타입별 검증 게이트

2026-09-02 사용자가 확정한 **7단계 분산 파이프라인**은 요청자·마스터·워커의 책임을 명확히 분리하고, 프로젝트 타입(`kind: unreal` vs `kind: code`)에 맞는 결정론적 게이트를 적용한다(`README.md:11-27`, `README.md:83-111`, `PLAN.md:4-11`).

```
[⑴~⑶ 요청자 (.33 게임 / .57 AXCluster)]
  RAG 컨텍스트 검색 ──► 동작 계획 및 인터페이스 동결 골조([PSEUDO]) 작성 ──► task/<work>/base 커밋·push 및 work 등재
                                                                                      │
[⑷ 마스터 (.57)]                                                                     ▼
  골조 게이트(skeleton_gate) 확인 ──► 의존성·파일 불가분(batching) 분해 ──► 서브 브랜치(task/<work>/<task_id>) 생성 및 병렬 파견
                                                                                      │
[⑸ 워커 (.2 / .43 / .33)]                                                            ▼
  격리 worktree에서 본문 구현 (mode: lane / claude / codex) ──► 층1·층2·조각 게이트 통과 시 서브 브랜치 커밋·push (`wcommit`)
                                                                                      │
[⑹ 마스터 ax-followup.timer (1분 주기)]                                              ▼
  전 조각 종결 감지 ──► 격리 worktree에서 조각 통합 및 회귀 검사 준비 ──► Redmine 노트 기록 후 사람 게이트(at_gate) 대기
                                                                                      │
[⑺ 요청자 — 사람 게이트 2곳]                                                         ▼
  ① ⑺ 전진 (ax-advance: "버그냐 구조 수정이냐" 판정 → 후속 라운드 r<N> 또는 통과)
  ② finalize (confirm=True 승인 시에만 main 최종 머지 및 일감 완료 처리)
```

- **파일 불가분 묶음 (`master/work/batching.py`)**:
  - C++의 `.h`/`.cpp` 쌍처럼 쪼개면 컴파일이 깨지는 단위는 `모듈+경로+stem` 키로 묶어 같은 조각에 배정하고, `[PSEUDO:N]` 깊이에 따라 동시 실행(묶음)과 순차 실행(뎁스)을 구분한다(`README.md:197`, `README.md:208`).
- **3층 결정론적 검증 게이트 (`README.md:202-226`, `PLAN.md:5-7`)**:
  1. **층1 (`master/work/layer1.py`)**: `[PSEUDO]` 미구현 잔재, `[FEEDBACK]` 태그 잔류, 골조 인터페이스(선언부)의 임의 변경·삭제 여부를 즉시 검사한다(추가는 허용하되 기존 선언 변경·삭제는 위반).
  2. **층2 (`master/verdict.py`)**: 작성 모델과 다른 계열(`exclude_author`)의 상용 모델이 헤더 선언부(`declarations.py`) 및 도메인 불변식(`norms.py`)을 근거로 의미적 정합성을 판정한다.
  3. **층3 (`master/layer3_verify.py`)**:
     - `unreal`: `.2` 워커에서 실제 UE5 컴파일 및 `RunTests` 실행.
     - `code`: `pyflakes` · `import` 검증 · `mypy(call-arg)` · `tests/integration/checks.json` 공식 통합 검사 실행.
- **Epoch Fencing (`master/work/coordinator.py`, `master/task_queue/`)**:
  - 타임아웃이나 재할당으로 인해 뒤늦게 도착한 낡은 좀비 워커의 산출물이 브랜치를 오염시키지 못하도록 epoch 번호로 펜싱한다(`README.md:99-101`, `README.md:189`).

---

### 3.3 멀티 에이전트 지휘 교대 및 교차 계열(Cross-Family) 견제

특정 상용 AI 모델의 토큰 한도 소진(Quota exhaustion)과 단일 모델의 자기합리화 편향을 동시에 막기 위해 **지휘·작성·리뷰의 모델 계열을 교차 배치**한다(`docs/orchestrator-rules.md:143-164`, `docs/16-worker-orchestrator-mode.md`).

| 구분 | 주체 및 우선순위 체인 | 핵심 규칙 및 근거 |
|---|---|---|
| **마스터 지휘자** | `Claude` ↔ `Codex` 양방향 교대 | `ax-handoff` 스킬 및 `master.relay`로 세션 교대. 기록상의 "완료"를 믿지 않고 `HEAD`·`dirty diff`·Redmine·서비스 상태를 실물 대조(`docs/orchestrator-rules.md:165-182`). |
| **서브 위임 (대화형)** | 지휘자 로컬 서브에이전트 / `Gemini 4 Argon` | Argon(`gemini-4-argon-medium`)은 지휘자가 스크래치 사본과 범위를 지정한 리서치(`ax-gemini`)나 작은 구현 패치 제안(`--task implementation`)에만 사용하며 마스터 지휘는 맡지 않음(`#829`). |
| **워커 실행 모드** | `lane` · `claude` · `codex` (`ax-mode`) | `lane`은 마스터가 `codex → agy → 로컬(qwen2.5-coder:14b)` 체인으로 텍스트만 생성. `claude`/`codex`는 워커 현지 CLI가 체크아웃을 읽고 오케스트레이션. 모드는 work 등재 시 `work["worker_mode"]`로 스탬프 고정(`#389`). |
| **커밋 자동 리뷰 큐** | 로컬 초안(`gemma4:e4b`) → 상용 2차 퇴고 | `ax-review-queue.timer`(10분 주기). 작성 계열에 `agy`가 있으면 `Codex` 단독, 그 외에는 `Antigravity` 단독으로 교차 리뷰하여 `R<번호>` 부여(`docs/orchestrator-rules.md:160-163`, `docs/17-review-queue.md`). |
| **다자 설계 토론** | `debate` 스킬 (3사이클) | 비자명한 아키텍처 결정 시 독립 의견 → 상호 반문·검토 → 재답변의 3사이클 토론을 거쳐 `reports/debates/`에 기록. |

---

### 3.4 다중 프로젝트 단일 마운트 격리 및 선언형 배달

하나의 마스터 서버와 워커 풀에서 여러 프로젝트(`AXCluster`, `ModularStage`, `NS`, `KimodoMotion_WebUI` 등)를 안전하게 전환·운영하는 아키텍처다(`docs/12-multi-project.md`, `docs/13-request-tagging.md`).

1. **설치는 여럿, 활성 마운트는 하나 (`docs/12-multi-project.md:233-245`)**:
   - 각 워커·요청자 PC에 여러 프로젝트의 체크아웃을 설치해 두는 것은 허용하되, 클러스터가 실제로 요청·분배·색인하는 대상은 마스터의 활성 마운트(`reg.active`) 단 하나뿐이다.
   - 마운트 전환(`set_active`) 시 미종결 작업이 있으면 임의로 지우거나 단순 거절하지 않고, 정리 대상을 이름으로 제시해 사용자의 `confirm=True` 승인을 받는다(`docs/12-multi-project.md:282-304`).
2. **요청 태깅 계약 (`MOUNT` vs `STAMP`, `docs/13-request-tagging.md`)**:
   - 모든 쓰기 표면과 주요 조회 표면은 요청에 프로젝트 태그를 실어야 한다.
   - 태그가 현재 마운트와 다르거나 빈 태그면 서버가 `HTTP 200 + ok:false + 사유`로 거절(fail-closed)하여 타 프로젝트 트윈 오염을 막는다(`docs/12-multi-project.md:324-337`).
3. **선언형 클라이언트 사양 및 배달 대조 (`client/spec.py`, `master/client/`)**:
   - 역할(`requester` / `worker`)과 프로젝트 프로필(`kind`)에 따라 배달할 런타임(`client/runtime/`), 스킬(`.agents/skills`, `~/.claude/skills`), 설정(`.ax/config.json`, `.codex/config.toml`), Git 제외 규칙(`info/exclude`)을 선언 표(`client/spec.py`) 한 곳에서 관리한다(`docs/12-multi-project.md:498-557`).
   - 커밋 및 마감 시 `master.client update`로 마운트된 프로젝트의 모든 작업장에 배달하고, `check`로 마스터 `HEAD` 리비전과 파일 해시 일치를 검증한다(`AGENTS.md:92-98`).
4. **Redmine 중심 일감 완결 파이프라인 (`master/issue_wrapup.py`, `docs/issue-spec.md`)**:
   - 착수 전 스펙 6항목(`problem`·`triage`·`observe`·`scope`·`done`·`open`)과 `<!-- ax:plan:begin v=2 -->` 표로 태스크를 관리한다(`#911`, `#939`).
   - 일감 마감 시 `issue_finish` → `master.issue_wrapup <N>`이 상주 서비스 신선도(`service_freshness.py`)를 판정해 필요한 유닛만 재기동하고, 인수인계서 커밋 확인 후 전 워커 배달까지 일관된 순서로 집행한다(`docs/orchestrator-rules.md:121-141`).

---

## 4. 저장소 패키지 구조 및 상주 서비스 맵

### 4.1 `~/ax-cluster` 핵심 패키지 역할 요약 (`README.md:146-238`)

| 경로 | 역할 및 주요 모듈 |
|---|---|
| `master/context_search/` | 다국어 벡터(`index.py`, `embedding.py`) + FTS5/한글 Trigram(`bm25.py`) + 시소러스(`thesaurus.py`, `expand.py`) + RRF 융합(`search.py`) + A/B 세대 교체(`generation.py`). |
| `master/context_synth/` | 로컬 LLM 컨텍스트 합성(`synth.py`, `prompt.py`), 식별자 사실 게이트(`verify.py`), 커밋 단위 리뷰 큐 및 소비자(`review_queue.py`, `review_runner.py`). |
| `master/ontology/` | 무의존성 YAML 직렬화(`yaml_io.py`), 계층 추정(`layers.py`), 사실 검증(`verify_facts.py`), 편집 잠금·보호(`edit.py`, `package.py`), 드리프트 감사(`drift.py`), 자립형 뷰어(`view.py`). |
| `master/graph/` | LLM 0 결정론적 `tree-sitter` C++/UE 파서(`parse.py`), 상속 그래프(`class_graph.py`), `#include` 의존성(`dependency.py`). |
| `master/events/` | Gitea `post-receive` 훅 소비자(`consumer.py`), 분산 작업 중 색인 일시정지 게이트(`gate.py`). |
| `master/work/` | 골조 생성·동결(`skeleton.py`, `skeleton_gate.py`), 분해·묶음(`decompose.py`, `batching.py`), 워커 파견·회수(`infer.py`, `runner.py`), 지휘자/모드(`conductor.py`, `mode.py`), 층1(`layer1.py`), 무인 후속 준비(`followup.py`), 전진·마감(`review.py`). |
| `master/task_queue/` | 분산 작업·태스크 상태 기계, claim/lease, epoch fencing(`server.py`, `logic_lifecycle.py`). |
| `master/broker/` | `:8102` Ollama 호환 추론 브로커 — `.2` 및 `.43` 추론 노드 라우팅, 모델 핀 유지, 헬스체크. |
| `master/projects/` | `:8103` 프로젝트 레지스트리, 마스터 공용 `ax-projects` MCP 서버(`mcp_server.py`), `/control/*` 제어 라우트. |
| `master/webui/` | `:8103` 웹 대시보드 — Context Server(`/`), 온톨로지(`/ontology`), 클러스터 상태(`/cluster`), 커밋 흐름(`/commit-flow`), RAG 로그(`/rag-logs`), 리뷰(`/reviews`), 사용량(`/usage`), 온보딩(`/onboarding`). |
| `client/` | 워커·요청자에 배달되는 클라이언트 런타임(`client/runtime/client_mcp.py`), 초기화 부트스트랩(`client/init/`), 배달 선언 사양(`client/spec.py`). |
| `docs/` & `reports/` | 아키텍처·운영 설계 정본(`PLAN.md` 색인) 및 세션별 실측·검증 리포트(`reports/1`~`192+`, `reports/research/`). |

### 4.2 마스터(`.57`) 가동 systemd 유닛 요약 (`README.md:242-252`, `PLAN.md:114-128`)

| 유닛 이름 | 포트 / 주기 | 역할 |
|---|---|---|
| `ax-task-queue.service` | `8101` (HTTP) | 분산 작업·조각 큐, Redmine 연동 대행, 사용량 수집 (`/api/v1/*`) |
| `ax-broker.service` | `8102` (HTTP) | 로컬 LLM 추론 브로커 (`.2` RTX 3060 / `.43` BC-250 라우팅) |
| `ax-projects.service` | `8103` (HTTP) | 프로젝트 레지스트리 + `ax-projects` MCP 서버 + 웹 UI + `/control/*` |
| `ax-indexer.path` / `.timer` | inotify / 10분 | Gitea push 이벤트 감지 → 미러 fetch → 그래프·합성·재색인·리뷰 큐 등재 |
| `ax-review-queue.timer` | 10분 주기 | 커밋 리뷰 큐 소비자 (로컬 `gemma4:e4b` 초안 → 상용 교차 계열 퇴고 → `R<N>`) |
| `ax-followup.timer` | 1분 주기 | 분산 작업 조각 완료 시 격리 worktree 통합·검사 준비 및 사람 게이트 대기(`#798`) |
| `ax-status.timer` | 5분 주기 | `/cluster` 화면용 클러스터 상태 스냅샷 갱신 (브라우저 새로고침 시 SSH 폭주 방지) |
| `ax-batch.timer` | 1시간 주기 | 유휴 시간대 배치 작업 실행 (RAG 채널 분석, 주간 레시피 합성 `#383` 등) |

---

## 5. 기술적 강점 및 현재 진화 중인 과제

### 5.1 아키텍처 강점
1. **단위 테스트와 통합 검사의 촘촘한 방어망**:
   - `tests/integration/checks.json`에 명시된 공식 통합 검사(199개 테스트)와 `master/test_*.py` 225개 파일(약 11,790+ 테스트 케이스)이 모든 게이트, 파서, 라우트, 심지어 삭제된 레거시 코드의 부활 방지(`test_no_integrator.py`, `test_retired_code.py`)와 조용한 예외 삼키기 감사(`sigma_audit.py`)까지 검증한다(`README.md:381-425`, `docs/orchestrator-handoff.md:59`).
2. **문서와 실행 코드의 결합 (Executable Documentation)**:
   - 온보딩 런북(`test_runbook.py`), 스킬 규약(`test_skill_conventions.py`), 일감 스펙 템플릿 예시(`test_plan_start.py`)를 테스트가 직접 파싱·실행하여 문서가 실제 코드와 어긋나면 즉시 검출한다(`PLAN.md:100`, `docs/issue-spec.md:51`).
3. **실패 경험의 제도화**:
   - M1~M7을 거치며 겪은 실제 장애(예: 마운트 밖 색인 오염 `#242`, 태그 검증 순서 역전으로 인한 로그 폭주 `#277`, Windows Session 0 샌드박스 실패 `#401`, 마감 뒤 배달 누락 `#916`)가 모두 결정론적 가드와 단일 래퍼 도구(`master.issue_wrapup`, `service_freshness`, `worker_mode_readiness`)로 흡수되어 재발을 차단한다.

### 5.2 현재 진화 중인 핵심 과제 (`docs/orchestrator-handoff.md`)
1. **착수 전 컨텍스트 수집·인터뷰의 Python 플로우 강제 (`#960` — 당면 최우선 버그/개선)**:
   - `#911`(`pstack` 기반 6대 스펙 템플릿)과 `#939`(`addyosmani/agent-skills` 기반 사전 인터뷰 및 Capability Map)를 문서와 `spec_missing` 경고로 도입했으나, 지휘 에이전트가 여전히 피상적인 질문만 던지고 사용자와 합의 없이 독단적으로 플랜을 확정하는 문제가 발생했다(`docs/orchestrator-handoff.md:6-18`).
   - 이를 해결하기 위해 **일감 착수 → 플랜 유무 확인 → 작업 성격(버그 회귀 추적 / 신기능 기획·레퍼런스 / 기존 기능 수정)에 따른 조사·문답 루프**를 단순 프롬프트 지침이 아니라 **Python 실행 플로우**로 강제하는 설계가 진행 중이다(`docs/orchestrator-handoff.md:30-52`).
2. **플랜 태스크 완료 근거 품질 관문 고도화 (`#908`, `#961`)**:
   - `plan_transition`으로 태스크를 `완료`로 넘길 때, 단순 텍스트나 `"검사 실행 안 함"` 같은 미실시 문구를 걸러내고 실제 커밋·테스트 결과·실증 근거가 포함되었는지 검증하는 관문이 강화되고 있다(`docs/orchestrator-handoff.md:20-28`).
3. **외부 에이전트 엔지니어링 스킬셋의 단계적 이식 아카이브 (`#952`~`#959`, `#945`)**:
   - `pstack`의 반복 실수 4계층 구조적 차단(`/correct`, `#953`), 변경 전 기준선 선행 캡처(`/figure-it-out`, `#954`), 마감 전 AI Slop 정제 및 파급 반경 실측(`/unslop`·`/blast-radius`, `#955`), 그리고 `addyosmani/agent-skills`의 확증 편향 제거 리뷰(`doubt-driven`, `#957`), 테스트 하향 꼼수 차단(`Floor Guard`, `#958`), 실패 경로 압축(`context-engineering`, `#959`) 등이 아이디어 파이프라인에 체계화되어 있다.
4. **한국어 RAG 검색 품질 정량 평가 (`#211`, `#855`)**:
   - `/rag-logs`를 통해 축적된 실사용 한국어 질의 스냅샷을 바탕으로 정답 집합(30건+)을 구축하고 `Hit@k`를 측정해 검색 가중치와 시소러스를 정량 개선하는 과제가 예정되어 있다(`README.md:339-342`, `docs/orchestrator-handoff.md:94`).

---

## 6. 근거 문서 및 소스 색인

- `README.md:1-452` — 클러스터 개요, 7단계 파이프라인, 패키지 트리, 상주 서비스, MCP 도구 및 테스트 체계
- `PLAN.md:1-139` — 마일스톤 M1~M7 이력, `kind`(`unreal`/`code`) 게이트 정의, `docs/` 전체 색인
- `AGENTS.md:1-129` — 저장소 작업 수칙, PC 타입별 실행 책임, 분산 등재 후 `ax-followup.timer` 대기 규약
- `docs/12-multi-project.md:1-560` — 다중 프로젝트 격리, 단일 마운트 원칙, 선언형 클라이언트 사양(`client/spec.py`)
- `docs/16-worker-orchestrator-mode.md:1-306` — 워커 지휘자 모드(`lane`/`claude`/`codex`), Windows readiness, per-work 스탬프(`#389`)
- `docs/17-review-queue.md:1-348` — 비동기 커밋 리뷰 큐, 로컬 1차 초안 + 상용 교차 퇴고, Python 커밋 자동 리뷰(`#9`)
- `docs/orchestrator-rules.md:1-284` — Claude·Codex 공용 지휘 규칙, 일감 완결 흐름(`master.issue_wrapup`), 교차 계열 원칙(`#829`)
- `docs/issue-spec.md:1-92` — Redmine 일감 스펙 6항목 템플릿 및 `plan_start.spec_missing` 경고 계약(`#911`)
- `docs/orchestrator-handoff.md:1-104` — 최신 운영 상태(`main cc3cdb0`), `#911`·`#939`·`#961` 마감 내역 및 `#960` 진행 맥락
