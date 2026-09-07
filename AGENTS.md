# AGENTS.md — AX 클러스터 저장소 (`~/ax-cluster`)

    AX-ENTRY-MARK: repo

> 위 표식은 **자동 로드 검증용**이다. 새 세션이 지시 없이 이 파일을 읽었는지 가리는 데
> 쓴다 (`docs/orchestrator-handoff.md` §바로 다음 작업). 지우지 않는다.

## 세션 시작에 읽을 것

1. 🔴 **`docs/orchestrator-handoff.md`** — 지금 무엇이 진행 중인가. **한 벌만 있다.**
2. 🔴 **`docs/orchestrator-rules.md`** — 두 지휘자(Claude · Codex)가 함께 지키는 규칙.
3. `docs/milestones/6-improvements.md`(열린 마일스톤) · `docs/12-multi-project.md`(열린 축).
   [주의] **항목·진행은 레드마인(`:8080`)만** 본다.
4. `reports/` 를 **전문으로** 읽는다 — grep 은 대체가 아니다.

## 절대 놓치면 안 되는 것 (전문은 `docs/orchestrator-rules.md`)

- **커밋·푸시는 자율 실행 금지** — 매번 승인을 받는다.
- **실패는 고치는 자리가 아니라 보고하는 자리다** — rc≠0·차단·예외면 멈추고 사유와 갈래를 낸다.
- **지시받은 대상 밖의 파일은 건드리지 않는다.**
- **사람 게이트는 둘** — ⑺ 전진(`ax-advance`)과 finalize(`main` 머지).
- **`~/AgentTest` 는 참조 전용** — 수정·푸시 금지. 만들기 전에 거기부터 읽는다.
- **사용자와의 대화는 한국어.**
- 이 저장소의 작업 지침 전문은 [`CLAUDE.md`](CLAUDE.md) — **도구 이름이 붙어 있을 뿐
  내용은 도구 무관**이다. Codex 도 그 규칙을 따른다.
