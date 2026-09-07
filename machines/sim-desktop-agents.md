# AGENTS.md — sim-desktop 홈 (`/home/sim`)

    AX-ENTRY-MARK: home

> 위 표식은 **자동 로드 검증용**이다. 새 세션이 지시 없이 이 파일을 읽었는지 가리는 데 쓴다
> (`~/ax-cluster/docs/orchestrator-handoff.md` §바로 다음 작업). 지우지 않는다.
>
> [중요] **정본은 `~/ax-cluster/machines/sim-desktop-agents.md` 이고 `/home/sim/AGENTS.md` 는
> 심볼릭 링크다** — `~/CLAUDE.md` 와 같은 방식이다. 일반 파일로 덮지 않는다.

`/home/sim` 은 **개인 리눅스 홈서버 sim-desktop 의 홈이지 소프트웨어 저장소가 아니다.**
빌드·린트·테스트 도구가 없다. **코드베이스가 있다고 전제하지 않는다.**
이 기계는 AX 클러스터의 **마스터**다 — 큐·브로커·색인/온톨로지·저장소(`~/ax-cluster`).

## 세션 시작에 읽을 것

1. 🔴 **`~/ax-cluster/docs/orchestrator-handoff.md`** — 지금 무엇이 진행 중인가. **한 벌.**
2. 🔴 **`~/ax-cluster/docs/orchestrator-rules.md`** — 두 지휘자의 공용 규칙.
3. `~/ax-cluster/docs/milestones/6-improvements.md` · `~/ax-cluster/docs/12-multi-project.md`.
   [주의] **항목·진행은 레드마인(`:8080`)만.**
4. `~/ax-cluster/reports/` 를 **전문으로** 읽는다.

## 절대 놓치면 안 되는 것 (전문은 `docs/orchestrator-rules.md`)

- **커밋·푸시는 자율 실행 금지** — 매번 승인.
- **실패는 보고하는 자리다** — 고치지 않고 멈춘다. **대상 목록 밖 파일은 건드리지 않는다.**
- **사람 게이트는 둘** — ⑺ 전진과 finalize.
- **`~/CLAUDE.md` 와 `/home/sim/AGENTS.md` 는 둘 다 심볼릭 링크다** — 덮지 않는다.
- **`~/AgentTest` 는 참조 전용.**
- **사용자와의 대화는 한국어.**
- **작업장은 `.33` 이다** — Unreal 작업은 거기로 들어온다. 여기서 다루는 것은 클러스터 자체다.

## 기계

    .57  sim-desktop  이 기계 · 마스터            (서비스 8080·8101·8102·8103)
    .2   Windows      워커 + 추론 · 계정 janus    (UE5 5.8 — 층3 판정 가능)
    .33  Windows      요청자 · 계정 user          [중요] 파견 대상이 아니다 · 사람의 기계
    .43  BC-250 #1    워커 + 추론 · 계정 sim      (Fedora, headless)
