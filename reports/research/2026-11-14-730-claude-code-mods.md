# #730 — Claude Code `Mods` (인프로세스 개조 플러그인) 기능 분석 및 AX 클러스터 대조 보고서

> 2026-11-14 · Antigravity 리서치 보고서
> 관련 일감: Redmine [`#730`](http://192.168.0.57:8080/issues/730) (`[AX][아이디어] 「클로드 모드」 기능 검토 — 사용자가 본 기능 (상세 미확인)`)
> 분석 대상: `https://code.claude.com/docs/ko/plugins/mods/overview` (영문 정본: `https://code.claude.com/docs/en/plugins/mods/overview`, 하위 문서 `create`, `events`, `reference`)
> 대조 내부 문서: `docs/16-worker-orchestrator-mode.md` (`#385`), `master/skills/ax-mode/SKILL.md`, `master/skills/ax-handoff/SKILL.md` (`#384`)
> 목적: Redmine `#730`에 등록된 「클로드 모드」의 정확한 기술적 실체(`Mode`가 아닌 `Mod`)를 규명하고, CLI 개조 범위·토큰 소모 메커니즘·AX 클러스터 지휘 체계와의 중첩 여부를 분석함.

---

## 1. 요약 (Executive Summary)

1. **실체 규명 (`Mode`가 아니라 `Mod`)**:
   - 사용자가 본 「클로드 모드」는 실행 모드(`Mode`)가 아니라 **Claude Code(`v2.1.287+`)에 도입된 인프로세스(In-process) 확장 플러그인 시스템인 `Mods` (Modifications)** 이다. (마스터 `.57`에는 현재 `Claude Code 2.1.323`이 설치되어 있어 지원 대상임.)
   - 별도의 번들러나 빌드 단계 없이 TypeScript/JavaScript 모듈(`hooks/register.ts` 또는 `.js`)을 Claude Code 프로세스 내부에서 직접 로드하여 `register(on, options)` 미들웨어 체인으로 실행한다.
2. **CLI 수정 가능 여부 → 가능 (본래 CLI 터미널 개조용 기능)**:
   - Claude Code CLI 터미널 화면(TUI)의 특정 렌더 위치(`AbovePrompt`, 사이드 패널 `Pane`, 기존 `Spinner`/`ToolUse` 컴포넌트 등)를 Ink(React 기반 TUI) 요소로 직접 다시 그리거나 추가할 수 있다.
   - CLI 슬래시 명령어(`$.command.register`) 및 도구를 동적 등록하고, 프롬프트 제출·도구 호출 이벤트를 가로채어 관찰(`Observe`)·재작성(`Rewrite`)·즉시 응답/차단(`Answer`)할 수 있다.
3. **추가 토큰 소모 여부 → 기본 0 토큰 (컨텍스트 주입 시에만 발생)**:
   - Mod 코드는 LLM이 아니라 **로컬 CPU에서 도는 JS/TS 함수**이므로, 터미널 UI 렌더링(`ui.render`), 로컬 조건문 기반 도구 차단(Guard), LLM을 거치지 않는 슬래시 명령어 즉시 응답(`Answer`)에는 **토큰이 단 1개도 소모되지 않는다(0 토큰)**.
   - 오히려 텍스트 전체가 프롬프트 컨텍스트에 실리는 `SKILL.md`와 달리, Mod의 코드는 모델 컨텍스트에 들어가지 않아 **단순 상태 조회·정적 가드 작업에서는 토큰을 절약**한다.
   - 단, Mod가 프롬프트나 도구 결과를 `Rewrite`하여 텍스트를 덧붙이거나 모델이 호출할 새 Tool 스키마를 노출할 때만 그 텍스트 길이만큼 입력 토큰이 추가된다.
4. **AX 클러스터(`#385` · `#384`)와의 관계 → 겹치지 않음**:
   - 우리 클러스터의 워커 지휘자 모드(`worker_mode ∈ {lane, claude, codex}`, `#385`) 및 마스터 담당 교대(`#384`)와는 층위가 완전히 다르다.
   - 클러스터의 공용 게이트(`wcommit` 층1, `ax-followup.timer`)는 Claude와 Codex 양쪽 지휘자에 공통 적용되어야 하므로 Claude 전용인 `Mods`로 대체할 수 없다. 다만 **대화형 Claude CLI 세션의 무토큰(0 토큰) 상단 상태 표시줄(`AbovePrompt`)이나 로컬 실수 방지 가드** 용도로는 보조 활용 가치가 있다.

---

## 2. Claude Code `Mods` 아키텍처 상세 분석

### 2.1 정의 및 디렉터리 구조
`Mod`는 일반 Claude Code 플러그인(`.claude-plugin/plugin.json`)에 인프로세스 훅 진입점(`hooks/hooks.json`의 `"modules"` 배열)을 추가한 형태다.

```text
my-mod/
├── .claude-plugin/
│   └── plugin.json          # 플러그인 매니페스트 (이름, 버전, 설명)
└── hooks/
    ├── hooks.json           # {"modules": ["./register.ts"]} — 이 키가 플러그인을 Mod로 만듦
    └── register.ts          # export function register(on, options) { ... }
```

- **무빌드 로드**: Claude Code 런타임이 `.ts` / `.js` 파일을 직접 읽어들이므로 별도의 `webpack`/`esbuild` 컴파일 단계 없이 즉시 실행된다.
- **미들웨어 체인 구조**: `on(eventName, filter?, async ($, e, next) => { ... })` 시그니처를 사용하며, `await next(e)`를 호출해 다음 미들웨어 또는 기본 엔진 동작으로 이벤트를 넘기거나, `next(e)`를 호출하지 않고 가로채어(Short-circuit) 차단·대체 응답을 반환할 수 있다.

### 2.2 기존 확장 수단(Skills / MCP / Settings Hooks)과의 비교

| 비교 항목 | Skills (`SKILL.md`) | MCP 서버 (`ax-client` 등) | Settings Hooks (`settings.json`) | **Mods (`hooks/register.ts`)** |
|---|---|---|---|---|
| **실행 주체·위치** | LLM 프롬프트 컨텍스트 | 외부 프로세스 (stdio / HTTP) | 외부 셸 스크립트 (자식 프로세스 spawn) | **Claude Code 프로세스 내부 (In-process JS/TS)** |
| **CLI 화면(TUI) 개조** | 불가 | 불가 | 불가 | **가능 (`ui.render`로 `AbovePrompt`, `Pane` 등 렌더링)** |
| **이벤트 개입 깊이** | 모델의 자율 판단에 의존 | 모델이 도구를 호출할 때만 동작 | `PreToolUse` 등에서 exit code/JSON 반환 | **프롬프트·도구·렌더링·명령어 전 구간 미들웨어 개입** |
| **프로세스 오버헤드** | 없음 (프롬프트 토큰 소모) | 상주 데몬 또는 연결 비용 | 매 이벤트마다 프로세스 fork/exec 비용 | **없음 (동일 런타임 내 함수 호출)** |
| **기본 토큰 비용** | 스킬 로드 시 입력 토큰 소모 | 도구 스키마 노출 시 입력 토큰 소모 | 0 토큰 (출력을 컨텍스트에 넣을 때만 발생) | **0 토큰 (프롬프트에 텍스트 주입 시에만 발생)** |

---

## 3. 핵심 질문 1: CLI도 수정할 수 있는가?

**결론: 예. Claude Code 자체가 터미널 CLI 애플리케이션이며, `Mods`는 CLI 터미널 화면(TUI)과 CLI 실행 동작을 직접 뜯어고치는 기능이다.**

### 3.1 CLI 터미널 화면(TUI) 개조 (`ui.render`)
Claude Code의 터미널 UI는 React 기반 터미널 렌더러(Ink 계열 박스 모델)로 그려진다. Mod는 `on('ui.render', { component: '...' }, ...)` 훅을 통해 터미널 화면 구성을 실시간으로 바꾼다:
- **`AbovePrompt` (프롬프트 상단 밴드)**: 사용자가 명령을 입력하는 프롬프트 창 바로 위에 커스텀 상태 표시줄을 고정 렌더링한다 (예: 현재 Git 브랜치, 마운트된 프로젝트, 남은 토큰/컨텍스트 게이지).
- **`Pane` (사이드 패널)**: 대화 트랜스크립트 옆에 실시간 에이전트 작업 트리, 파일 변경 목록, 로그 뷰어 등을 분할 패널로 띄운다.
- **기본 컴포넌트 래핑·교체**: `Spinner`, `ToolUse`, 메시지 블록 등 기존 CLI 출력 컴포넌트를 가로채어 표시 형식을 바꾸거나 요약한다.

```typescript
// 예시: CLI 프롬프트 상단(AbovePrompt)에 상태 바 렌더링 (토큰 소모 0)
export function register(on) {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const { Box, Text } = $.ui.resolve(e);
    const below = await next(e);
    return (
      <Box flexDirection="column">
        <Text color="cyan">[AX-Cluster] Project: AXCluster | Worker Mode: codex</Text>
        {below}
      </Box>
    );
  });
}
```

### 3.2 CLI 슬래시 명령어 및 실행 흐름 개조
- **커스텀 슬래시 명령어 등록 (`$.command.register` / `command.run`)**:
  - `session.start` 이벤트에서 `await $.command.register({ name: 'ax-status', description: '...' })`로 CLI 명령어를 등록하고, `on('command.run', ...)`에서 처리한다.
- **프롬프트·도구 호출 제어 (`Observe` / `Rewrite` / `Answer`)**:
  1. `Observe` (관찰): 어떤 도구가 몇 번 호출됐는지, 어떤 파일이 수정됐는지 인메모리 카운터나 로컬 로그에 기록하고 `return next(e)`로 통과시킨다.
  2. `Rewrite` (재작성): 사용자가 입력한 짧은 프롬프트나 도구 인자를 모델/실행기에 넘기기 전에 정형화된 형식으로 바꾼다.
  3. `Answer` (즉시 응답/차단): 위험한 명령(예: 미승인 `git push`, `rm -rf`)이나 로컬에서 바로 답할 수 있는 조회 요청을 `next(e)` 호출 없이 Mod가 직접 차단하거나 답을 돌려준다.

> **비대화형(`claude -p`) 실행 시의 제약**:
> 워커 파견처럼 `claude -p --output-format json`으로 실행하는 헤드리스(headless) 단발 모드에서는 대화형 터미널 TUI가 뜨지 않으므로 `ui.render`(`AbovePrompt`, `Pane`)는 화면에 나타나지 않는다. 비대화형에서는 이벤트·도구 후킹만 의미가 있다.

---

## 4. 핵심 질문 2: 추가로 토큰이 나가는가?

**결론: Mod의 실행 자체는 로컬 CPU의 JS/TS 함수 호출이므로 추가 토큰이 전혀 나가지 않는다(0 토큰). 오직 Mod가 LLM 프롬프트에 텍스트를 밀어 넣을 때만 토큰이 나간다.**

| 동작 유형 | 구체적 예시 | 추가 토큰 소모 여부 | 이유 |
|---|---|---|---|
| **1. CLI UI 렌더링** | `ui.render`로 `AbovePrompt`에 Git 브랜치·큐 상태·토큰 미터 표시 | **0 토큰 (없음)** | 터미널 화면 버퍼(stdout)에 그리는 로컬 UI 작업이며 LLM API 요청에 포함되지 않음 |
| **2. 로컬 가드·차단 (Guard)** | `Bash` 도구 호출에서 `git commit`/`git push`나 금지 경로 수정을 JS 정규식으로 검사해 차단 | **0 토큰 (없음)** | 도구 실행 직전에 JS 함수가 검사하여 막으므로 추가 LLM 추론이 일어나지 않음 |
| **3. 슬래시 명령 로컬 처리** | `/ax-status` 입력 시 Mod가 `localhost:8101` API를 조회해 터미널에 바로 출력 (`Answer`) | **0 토큰 (오히려 절약)** | LLM에게 프롬프트를 보내지 않고 로컬 JS가 응답을 끝냄 (`SKILL.md`를 읽혀 LLM이 도구를 부르게 하는 것보다 토큰 절약) |
| **4. 프롬프트/도구 결과 Rewrite** | 사용자 프롬프트마다 뒤에 500자짜리 규칙 안내문을 자동으로 덧붙여 전송 | **입력 토큰 증가** | LLM으로 나가는 `messages` 페이로드가 길어지므로 덧붙인 문자열 길이만큼 매 턴 입력 토큰 과금 |
| **5. LLM용 커스텀 Tool 등록** | 모델이 자율 호출할 수 있는 새 Tool을 등록 | **입력+출력 토큰 증가** | 시스템 프롬프트에 Tool JSON 스키마가 상시 포함되고, 모델이 해당 도구를 호출할 때 턴 왕복 토큰 발생 |
| **6. AI에게 Mod 제작 요청** | 대화창에서 `/plugin-authoring` 스킬로 *"이런 Mod 만들어줘"*라고 요청 | **생성 시 1회 소모** | Mod를 개발하는 과정에서 Claude와 대화한 일반 세션 토큰 |

---

## 5. 보안 및 권한 특성 (주의사항)

- **비샌드박스 실행 (High-Privilege)**:
  - Mod의 JS/TS 코드는 샌드박스에 갇히지 않고 **Claude Code를 실행한 OS 사용자 권한 그대로** 프로세스 내부에서 돈다.
  - 즉, 파일 시스템 읽기/쓰기, 환경변수(`process.env`), 네트워크 요청, 세션 내 모든 프롬프트·응답 원문에 접근할 수 있다.
- **내장 안전장치**:
  - `claude plugin validate <경로>`: 설치·로드 전에 매니페스트와 훅 구조를 정적 검증.
  - `--safe-mode` 플래그 또는 설정 파일의 `"disableAllHooks": true`: 문제 발생 시 모든 Mod/Hook 비활성화.
  - 엔터프라이즈 정책(`allowManagedModsOnly`): 승인된 관리형 Mod만 로드 허용.

---

## 6. AX 클러스터 구조와의 대조 (`#730` 확인 과제)

Redmine `#730` 본문에서 요구한 확인 항목인 **「우리 지휘자 모드(`lane`/`claude`/`codex`, `#385`)·마스터 지휘자 교대(`#384`)·워커 지휘 경로와 겹치는지」**를 대조한 결과는 다음과 같다.

### 6.1 개념·층위 대조표

| 구분 | AX 워커 지휘자 모드 (`#385`, `ax-mode`) | AX 마스터 지휘자 교대 (`#384`, `ax-handoff`) | Claude Code `Mods` (`#730`) |
|---|---|---|---|
| **정본 위치** | `master/work/mode.py` · `conductor.py` | `docs/orchestrator-handoff.md` · `conductor.py` | Claude Code CLI 내부 플러그인 (`.claude-plugin/`) |
| **선택/동작 값** | `lane` / `claude` / `codex` | `claude` / `codex` (마스터 담당 기록) | JS/TS `register(on)` 이벤트 핸들러 |
| **역할** | 마스터가 SSH로 워커에 조각 파견 시 어느 실행 엔진을 쓸지 결정 | 마스터 대화 세션 교대 시 작업 상태 복원 및 인수 기록 | 단일 Claude Code CLI 세션의 화면(TUI) 및 로컬 이벤트 개조 |
| **중첩 여부** | **겹치지 않음 (서버 파견 스위치 vs 로컬 CLI 플러그인)** | **겹치지 않음 (다중 도구 인수 절차 vs 단일 도구 플러그인)** | **독립된 로컬 UI/이벤트 확장 기능** |

### 6.2 AX 클러스터 도입 타당성 및 한계

1. **클러스터 핵심 게이트·공용 규칙 대체 불가 (도입 비권장 영역)**:
   - AX 클러스터는 마스터와 워커 모두 **Claude와 Codex 두 지휘자를 함께 운영**한다.
   - `AGENTS.md` 규칙상 마스터 후속 처리는 훅 대신 `ax-followup.timer` 단일 경로를 쓰며, 워커 산출물 판정은 `wcommit` 층1 검사가 담당한다.
   - 만약 핵심 제약이나 자동화 로직을 Claude Code 전용 `Mod`로 구현하면 **Codex 지휘 세션이나 `lane` 모드에서는 동작하지 않아 지휘자 간 동작 불일치**가 발생한다.
2. **보조 편의 도구로서의 활용 가능 영역 (추후 선택적 검토)**:
   - **무토큰(0 토큰) 상단 상태 바 (`AbovePrompt`)**: 사람이 마스터(`.57`)나 요청자(`.33`)에서 대화형으로 Claude Code CLI를 띄워 쓸 때, 프롬프트 바로 위에 `현재 마운트 프로젝트 · 워커 모드(lane/claude/codex) · 활성 work 상태`를 상시 표시하는 TUI 상태 바를 붙이면 **컨텍스트 토큰을 전혀 쓰지 않고** 현재 클러스터 상태를 한눈에 볼 수 있다.
   - **대화형 세션의 로컬 실수 방지 가드**: 대화형 Claude 세션에서 미승인 `git push`나 심볼릭 링크(`~/CLAUDE.md`, `~/AGENTS.md`) 덮어쓰기 시도를 `PreToolUse` 인프로세스 훅으로 즉시 경고·차단하는 보조 안전망으로 쓸 수 있다.

---

## 7. 참고 자료 및 출처

- 공식 문서 (한국어): `https://code.claude.com/docs/ko/plugins/mods/overview`
- 공식 문서 (영문):
  - Overview: `https://code.claude.com/docs/en/plugins/mods/overview`
  - Create a Mod: `https://code.claude.com/docs/en/plugins/mods/create`
  - React to Events: `https://code.claude.com/docs/en/plugins/mods/events`
  - Mods Reference: `https://code.claude.com/docs/en/plugins/mods/reference`
- 내부 대조 문서:
  - `docs/16-worker-orchestrator-mode.md` (`#385` 워커 지휘자 모드 설계 및 실증)
  - `master/skills/ax-mode/SKILL.md`
  - `master/skills/ax-handoff/SKILL.md` (`#384` 마스터 지휘자 교대)
