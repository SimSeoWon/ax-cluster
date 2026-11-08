# 160 — #926 Antigravity 지휘 통합 실증 (ax-projects 시작·Argon 위임·Codex 리뷰)

- **일시**: 2026-11-09
- **이슈**: #926 (선행: #920)
- **지휘 세션**: Antigravity (Gemini 3.8 Flash Medium)
- **서브에이전트 위임**: Gemini 4 Argon (`gemini-4-argon-medium`)
- **검증 대상**: `ax-projects` MCP 기반 일감 시작(`author.family=agy`), Argon 서브에이전트 위임, 태스크 단위 완결형 권한 정책 UX, Streamable HTTP MCP 세션 동작, 이종 패밀리(`Codex`) 교차 리뷰 라우팅

---

## 1. 배경과 목적

#920에서 Antigravity(`agy`)를 AX 클러스터의 세 번째 마스터 지휘자로 편입하고, MCP 호출 출처 기반 `author.family` 기록·이종 모델 교차 리뷰 라우팅·Argon 서브에이전트 위임 규칙을 수립하였다.

본 보고서(#926)는 코드 및 단위 테스트 수준에서 정비된 #920의 계약이 **실제 Antigravity 대화형 세션**에서 끝단 간(End-to-End) 정상 작동하는지 실증한 결과를 기록한다. 주요 목적은 다음과 같다.

1. Antigravity 세션에서 `ax-projects:issue_start_tool` 호출 시 `clientInfo` 식별 및 `author.family == 'agy'` 스탬프가 정확히 기록되는지 확인
2. 일감 플랜 가드(`step=plan`) 및 전용 worktree 생성 계약 검증
3. 지휘 세션(Flash Medium)과 구현 서브에이전트(Argon) 간 역할 분리 및 산출물 검증 흐름 실증
4. 도구 호출 중간 승인 팝업 없는 태스크 단위 완결 원칙(① 착수/플랜 승인, ② 완료/판단 보고) 작동 확인
5. `author.family == 'agy'` 일감에 대한 리뷰 큐의 `Codex` 단일 교차 검증 라우팅 확인

---

## 2. 실증 항목 및 실측 결과

### 2.1 `ax-projects:issue_start_tool(926)` 호출 및 출처 스탬프 검증

Antigravity 세션에서 `call_mcp_tool`을 통해 `ax-projects` 서버(`:8103`)의 `issue_start_tool(issue_id=926)`을 직접 호출하여 플랜 가드와 시작 상태를 실측하였다.

- **플랜 가드(`step=plan`) 작동 확인**:
  이슈 본문에 `ax:plan` 블록이 없는 상태에서 최초 호출 시, `issue_flow.start`가 작업을 시작하지 않고 플랜 수립 단계로 거절(`step=plan`)함을 확인하였다. 이후 `plan_start_tool` 및 `plan_set_tool`로 플랜을 등록한 뒤 재호출하여 정상 진입하였다.
- **실측 응답 및 상태 데이터**:
  ```json
  {
    "ok": true,
    "issue_id": 926,
    "repo": "/home/sim/ax-cluster/.ax-issues/926",
    "branch": "issue/926",
    "start_rev": "e937622",
    "author": {
      "family": "agy",
      "client": "antigravity-client"
    },
    "authors": ["agy"]
  }
  ```
- **검증 항목 요약**:
  - `author.family`: `'agy'` 정확히 기록됨
  - `client`: `'antigravity-client'`, 누적 `authors`: `['agy']` 확인
  - 일감 전용 worktree(`/home/sim/ax-cluster/.ax-issues/926`)가 기준 리비전 `start_rev = e937622`에서 정상 분기·생성됨

### 2.2 Argon(`gemini-4-argon-medium`) 서브에이전트 위임 및 지휘 세션 검증

`GEMINI.md`의 위임 규칙에 따라 지휘 세션(Gemini 3.8 Flash Medium)은 전체 진행과 상태 전이를 관장하고, 보고서 작성·코드 구현·복합 추론은 Argon(`gemini-4-argon-medium`) 서브에이전트에 위임하였다.

- **위임 흐름**:
  1. 지휘 세션이 작업 위치(`/home/sim/ax-cluster/.ax-issues/926`)와 진입 지침(`AGENTS.md`, `AX-ENTRY-MARK: repo`)을 확인한 뒤 요구사항과 컨텍스트를 정리하여 서브에이전트 호출
  2. Argon 서브에이전트가 독립 컨텍스트에서 산출물 초안 및 분석 수행 후 결과 반환
  3. 지휘 세션이 반환된 산출물을 직접 대조·검증하여 워크스페이스에 반영

### 2.3 대화형 UX 및 권한 게이트 (태스크 단위 완결 원칙)

작업 중 도구 호출마다 승인 창이 뜨거나 턴이 끊기는 문제를 방지하기 위해 설정한 실행 정책을 실증하였다.

- **적용 설정**:
  - 실행 모드: `mode: "accept-edits"` (`--mode accept-edits`)
  - 도구 실행 정책: `toolExecutionPolicy: "always-proceed"`
- **실측 결과**:
  - 파일 읽기/쓰기(`read_file`, `write_file`, `edit_file`), 셸 명령 실행(`run_command`), MCP 도구 호출(`call_mcp_tool`) 전 과정에서 **중간 승인 팝업 0건** 달성
  - 사용자와의 상호작용이 **① 태스크 착수/플랜 승인 시점**과 **② 태스크 완료/결과 판단 보고 시점** 두 곳으로 엄격히 고정되어, 태스크 내부 구현·검증이 단일 호흡으로 완결됨을 확인하였다.

### 2.4 이종 패밀리 교차 리뷰 라우팅 (`Codex` 단일 검증)

AX 클러스터의 교차 리뷰 규칙은 작성자 패밀리(`author.family`)와 다른 패밀리의 모델을 리뷰어로 배정한다.

- **라우팅 판정 결과**:
  - 일감 #926의 `authors`가 `['agy']`(`author.family == 'agy'`)로 기록됨에 따라, 자동 리뷰 큐는 동일 패밀리(`agy`)를 배제하고 **`Codex`를 단일 검증 모델로 선택**함을 확인하였다.
  - `Codex` 실패 시에도 작성자 패밀리인 `agy`로 폴백(fallback)하지 않고 실패를 그대로 보고하는 격리 계약이 유지된다.

---

## 3. 발견 사항 및 관측

### 3.1 `notifications/roots/list_changed` 400 응답과 MCP 도구 호출 세션의 독립성

Antigravity 클라이언트가 `:8103` Streamable HTTP MCP 서버(`ax-projects`)와 통신할 때 다음과 같은 프로토콜 동작이 관측되었다.

- **관측 현상**:
  - Antigravity 클라이언트가 워크스페이스 루트 변경 알림인 `notifications/roots/list_changed`를 전송할 때, `:8103` 서버에서 `400 Bad Request`를 반환하는 로그가 관측됨.
- **원인 및 영향 분석**:
  - `~/.gemini/antigravity-cli/mcp/ax-projects/`에 배치된 JSON 스키마를 통해 `call_mcp_tool`이 실행될 때는 각 도구 호출이 독립적인 HTTP POST 세션을 수립하여 요청을 처리한다.
  - 따라서 초기화 이후 비동기 알림(`notifications/roots/list_changed`)의 `400 Bad Request` 응답은 실제 도구 호출 세션에 영향을 주지 않으며, `issue_start_tool`, `plan_start_tool`, `plan_set_tool`, `plan_transition_tool` 등 모든 MCP 호출은 **HTTP 200 OK**로 차단 없이 정상 처리됨을 확인하였다.

---

## 4. 검증 결과 및 향후 영향

| 검증 항목 | 기대 기준 | 실측 결과 | 판정 |
|---|---|---|---|
| `issue_start_tool` 출처 기록 | `author.family == 'agy'`, `client == 'antigravity-client'` | `family: 'agy'`, `client: 'antigravity-client'`, `authors: ['agy']` | **통과** |
| 일감 worktree 및 플랜 가드 | 미플랜 시 `step=plan` 거절, 승인 후 worktree 생성 | `.ax-issues/926` (`start_rev: e937622`) 생성 및 가드 작동 확인 | **통과** |
| Argon 서브에이전트 위임 | 복합 추론·구현 Argon 위임 및 지휘 세션 검증 | `gemini-4-argon-medium` 위임 및 산출물 검증 완료 | **통과** |
| 권한 게이트 및 대화형 UX | 중간 팝업 0건, 착수/완료 2회 상호작용 고정 | `accept-edits` + `always-proceed` 하에서 무중단 완결 확인 | **통과** |
| MCP Streamable HTTP 호출 | `:8103` `ax-projects` 도구 정상 호출 | `roots/list_changed` 400 무관하게 모든 POST 도구 호출 200 OK | **통과** |
| 교차 리뷰 라우팅 | `author.family == 'agy'` 시 `Codex` 단독 배정 | `Codex` 단일 리뷰 모델 선택 (agy 폴백 없음) 확인 | **통과** |

### 향후 영향

1. **3대 지휘자 체제 실전 가동**: Claude·Codex에 이어 Antigravity(`agy`)가 `ax-projects` MCP와 일감 worktree 규약을 완전히 준수하며 실전 일감을 지휘·마감할 수 있음이 입증되었다.
2. **모델 한도 분산 및 비용 최적화**: 지휘는 경량·고속 모델(Flash Medium)이 맡고 고난도 추론·구현만 Argon 서브에이전트에 위임하는 구조가 정착되어, 응답 지연과 토큰 소모를 동시에 줄일 수 있다.
3. **MCP 알림 핸들링 참고 지표 확보**: 추후 Streamable HTTP MCP 서버 게이트웨이 개선 시 `notifications/roots/list_changed`를 무시(202 Accepted 또는 204 No Content)하도록 다듬으면 불필요한 400 로그 노이즈를 줄일 수 있다(기능상 블로커 아님).

최종 결과는 Redmine 마감 노트.
