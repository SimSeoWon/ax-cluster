# #1053 — Claude Code 실험 기능 `Code Mode` (JS 도구 오케스트레이션) 리서치 및 AX 클러스터 활용 분석 보고서

> 작성일: 2026-11-28 · 작성: Antigravity (Gemini 4 Neon) 리서치 보고서  
> 관련 일감: Redmine `#1053` (`아이디어 — 추후 검토 수집`)  
> 비교·구분 일감: Redmine `#730` (`reports/research/2026-11-14-730-claude-code-mods.md`, Claude Code `Mods` TUI·훅 플러그인)  
> 마스터 환경 실측: `.57` sim-desktop 설치 버전 `Claude Code 2.1.332` (`v2.1.323+` 충족)  
> 목적: Claude Code의 실험 기능 **`Code Mode`(`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1`)**의 아키텍처·MCP 연동·보안/훅 영향·제약을 분석하고, AX 클러스터의 대화형 지휘·조사·오케스트레이션 활용 가능성과 경계를 정리함.

---

## 1. 개요: `Mods`(#730)와의 구분 및 `Code Mode`의 실체

| 구분 | Claude Code `Mods` (`#730`) | **Claude Code `Code Mode` (`#1053`)** |
| --- | --- | --- |
| **도입 버전** | `v2.1.287+` | `v2.1.323+` (`.57` 현재 `2.1.332` 설치) |
| **핵심 역할** | CLI 화면(TUI: `AbovePrompt`, `Pane`)과 이벤트 훅을 인프로세스 JS/TS 플러그인으로 **개조** | 모델이 여러 도구 호출을 **JavaScript 코드 한 블록으로 묶어 실행**하는 **프로그래매틱 도구 오케스트레이션** |
| **작성 주체** | 사람(또는 사전 개발)이 플러그인 파일로 작성·설치 | 실행 시점에 Claude 모델이 JS 플로우를 생성·실행(스킬/템플릿으로 패턴 유도 가능) |
| **활성화** | `.claude-plugin/` 설치 | Opt-in: `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1` |

`Code Mode`는 Anthropic의 **Programmatic Tool Calling** 개념을 Claude Code 터미널 CLI에 구현한 실험 기능이다.

---

## 2. 동작 원리 및 아키텍처

### 2.1 기존 순차 루프 vs `Code Mode` 루프

- **기존 방식 (Sequential Tool Loop)**:
  1. `Grep`/`Search` 호출 → 전체 출력이 모델 컨텍스트에 유입
  2. `Read` 호출 → 파일 전체 본문이 모델 컨텍스트에 유입
  3. `Edit` → `Bash`(테스트) 호출 → 매 단계 API 왕복 + 중간 로그 누적
- **`Code Mode` 방식 (Programmatic JS Orchestration)**:
  1. Claude가 파일 탐색·조건 분기·병렬 실행·문자열 필터링·MCP 호출을 담은 **단일 JavaScript 코드 블록**을 작성.
  2. 로컬 런타임에서 스크립트를 실행하며, 중간 출력·대용량 로그는 **로컬 변수 안에서 소비·필터링**됨.
  3. **최종 요약 객체/결과만** Claude의 대화 컨텍스트로 반환됨(UI 트랜스크립트에는 개별 도구 호출·diff와 원본 스크립트가 투명하게 표시).

```javascript
// 예시: 다중 파일 탐색 → 수정 → 테스트를 1회 JS 실행으로 묶고 최종 요약만 반환
const files = await $`rg -l "function retryPolicy" src`.text();
const target = files.trim().split("\n")[0];
await edit(target, "maxAttempts: 3", "maxAttempts: 5");
({ edited: target, tests: $`npm test -- retryPolicy`.nothrow() });
```

### 2.2 기대 효과 (토큰·속도)
- 다단계 조사·리팩터링·대량 검색 작업에서 중간 원문 출력이 컨텍스트에 쌓이지 않아 **토큰 소모 25~50% 절감** 및 **API 왕복 지연 단축** 효과가 보고됨.
- 특히 **MCP 서버**(`ax-projects`, `ax-client`)가 반환하는 대용량 JSON(이슈 목록, 검색 결과, 웨이파인더 상태 등)을 JS 안에서 바로 `filter`/`map`/조인해 핵심 필드만 모델에 올릴 수 있어 MCP 컨텍스트 비대화 해소에 시너지가 큼.

---

## 3. 활성화 조건 · 제약 · 타임아웃

### 3.1 활성화 방법 (Opt-in 전용)
- **단발 세션**: `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1 claude`
- **사용자 전역 설정** (`~/.claude/settings.json`):
  ```json
  { "env": { "CLAUDE_CODE_EXPERIMENTAL_CODE_MODE": "1" } }
  ```
- **보안 정책**: 저장소가 임의로 강제 활성화하지 못하도록 **프로젝트 로컬 설정 파일에서는 무시**되며, 조직 관리 정책(`0`)으로 차단 가능.

### 3.2 환경·기능 제약
- **필수 조건**: 네이티브 터미널 빌드(`v2.1.323+`) + 대화형 세션 + 직접 Anthropic API(구독/Console) + 지원 프론티어 모델(Sonnet/Opus/Haiku 5.5 등).
- **미지원(불가)**:
  - **`-p` (헤드리스/비대화형 출력 모드) 불가** → AX의 무인 워커 파견(`claude -p`)에는 적용 불가.
  - Bedrock / Vertex / 커스텀 게이트웨이 미지원.
  - 원격 제어, Chrome computer use, 데스크톱 세션 이전, 백그라운드 세션 포크와 병용 불가.
- **실행 타임아웃**:
  - 동기 대기 실행: **최대 10분**.
  - `auto` / `bypass-permissions` 백그라운드 실행: **최대 약 2시간**.

---

## 4. 권한 · 훅 · 보안 주의사항 (AX 클러스터 기준)

1. **개별 도구 규칙은 통과하나, 문자열 매칭 훅은 우회될 수 있음**
   - 스크립트 내부에서 호출되는 개별 도구도 기존 `deny`/`ask` 규칙과 `PreToolUse` 훅을 거친다.
   - 다만 `auto`/`bypass-permissions` 모드에서는 분류기가 실행 전 바깥 JS 블록을 검사하며, 동적 문자열 조합(예: `cd 'app' && git push`)은 단순 문자열 매칭 훅을 우회할 수 있으므로 보안 훅은 REPL 도구의 `tool_input.code`까지 함께 검사해야 안전하다.
2. **AX 기존 훅(`UserPromptSubmit` · `Stop`)과의 관계**
   - AX의 `prompt_ledger.py`와 `stop_gate.py`는 턴 입구/출구 훅이므로 `Code Mode` 내부 JS 실행과 직접 충돌하지 않는다.
   - 다만 `Code Mode`가 한 턴 안에서 여러 쓰기 도구를 연쇄 실행할 수 있으므로, **"커밋·푸시는 매번 승인"**·**"대상 밖 파일 수정 금지"** 같은 AX 규칙을 깨지 않도록 초기 실증은 반드시 **읽기·조사 전용 세션**에서 시작해야 한다.
3. **Claude 전용 기능 (Codex 비호환)**
   - AX 클러스터는 마스터와 워커에서 Claude와 Codex를 함께 운용한다. 공용 불변식·게이트·상태 관리는 기존 Python(`master/*`)과 서버(`8101`/`8103`)에 정본을 유지하고, `Code Mode`는 **Claude 대화형 지휘 세션의 가속 수단**으로만 제한해야 지휘자 간 동작 분열을 막을 수 있다.

---

## 5. AX 클러스터 오케스트레이션 활용 시나리오

1. **착수 전 인터뷰(`ax-plan`)의 조사·파급 측정 가속**:
   - 여러 문서(`reports/`, `docs/`), 소스 파일, `git log`, `search_context_tool` 결과를 JS 1회 실행으로 병렬 조회·필터링해 핵심 근거만 추출.
2. **MCP 대용량 응답 로컬 필터링**:
   - `redmine_list_issues`, `wayfinder_status_tool`, `list_works` 등의 긴 JSON 응답을 JS에서 집계·정렬해 필요한 요약 표만 컨텍스트에 올림.
3. **정형 JS 플로우 템플릿 사전 작성 (사용자 착안)**:
   - 반복되는 마스터 점검·조사 패턴(예: "열린 일감 + 최근 커밋 + 드리프트 의심 도메인 교차 점검")을 재사용 가능한 JS 스니펫 가이드로 정리해 두면, 매번 모델이 5~10턴씩 왕복하지 않고 1턴에 일관된 결과를 뽑을 수 있음.

---

## 6. 결론 및 권장 실증 순서

- **1단계 (무위험 실증)**: `.57` 마스터(현재 `Claude Code 2.1.332`)에서 `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1 claude`로 **읽기·조사 전용 세션**을 열어, 다중 파일 탐색 + `ax-projects` MCP 조회에서 실제 토큰·속도 절감과 `prompt_ledger`/`stop_gate` 훅 정상 동작 여부를 확인.
- **2단계 (템플릿화 검토)**: 실증에서 안정성과 절감 효과가 확인되면, 자주 쓰는 읽기/조사 오케스트레이션 패턴만 스킬 `reference/`에 선택형 JS 가이드로 정리(Codex 세션은 기존 절차 그대로 유지).
