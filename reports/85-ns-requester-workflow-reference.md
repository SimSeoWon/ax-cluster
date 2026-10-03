# 85. .33 NS 요청자 작업 흐름 분석 — .57 인프라 정비의 참조

2026-10-03 · 사용자 “NS 에서 작업 요청을 받았을 때 어떻게 처리하는지 분석하면 되겠네”.
관련 일감: [#716](http://192.168.0.57:8080/issues/716).
원격 NS 파일·설정을 읽기 전용으로 확인했다. NS 소스·설정 변경, 신규 분산 작업,
서비스 재기동, 커밋·푸시는 하지 않았다. 새 작업의 실제 완주를 검증한 보고서는 아니다.

## 확인한 실물

작업장 `C:\Users\USER\Documents\NS`의 `CLAUDE.md`, `.claude/CLAUDE.md`,
`.claude/agents/code-writer.md`·`code-manager.md`·`source-analyzer.md`,
홈 및 프로젝트 로컬 `ax-request/SKILL.md`, 훅 domain_hint·pending_works·work_completion을 읽었다.
사본: `/tmp/ax-33-client-workflow/0.md`~`9.md`. MCP·훅 등록 요약은 `10.md`이며 자격 정보는 제외했다.
초기 조회 스크립트의 불필요한 `+`가 PowerShell 파싱 오류를 냈다. 사용자 NS 범위 정정 후
스크립트를 바로잡고 재조회에 성공했다. 원격 파일은 변경하지 않았다.

RAG는 현재 마운트 AXCluster에서 클라이언트·검색 구현을 질의했다. NS로 마운트를 바꾸지
않았으며 이를 NS 프로젝트 검색 결과라고 부르지 않는다. 참조 흐름의 주 근거는 NS 실물 지침과
등록 설정, 마스터가 관리하는 스킬·훅·client_mcp 코드다.

## 요청을 받은 뒤의 흐름

1. **컨텍스트 확보.** `.claude/CLAUDE.md:191`은 모든 코드 관련 요청에서 직접 소스 탐색에
   앞서 컨텍스트를 확보하게 한다. 코드 심볼이 있으면 온톨로지로 책임·도메인을 좁히고,
   RAG `ax-client.search_context`로 보강한다. 현재 코드로 구현 사실을 확정한다.
   작업 시작 직전 find_recipes·get_anti_patterns·find_history로 이전 패턴과 거절된 접근도 읽는다.
2. **계획과 사용자 선택.** 같은 파일331행부터 code-writer와 분산 등재를 구분한다.
   새 클래스3개 이상, 관계가 있는 시스템 변경은 전문 작성자를 자동 호출하지 않고 계획과
   a) AX 분산 b) 직접 처리 c) 작은 단위로 전문 에이전트 위임을 제시한다. 환경 미연결을 이유로
   분산 선택지를 지우지 않고 상태를 설명한다. API·여러 파일·구조 변경도 계획 확인이 먼저다.
3. **단독 처리도 위임.** ax-request §0.2와 code-writer 문서는 메인 세션이 대량 본문을
   혼자 작성하지 않도록 한다. 전문 에이전트가 템플릿(지정됐을 때), 레시피·안티패턴,
   컨텍스트·실제 소스를 읽고 작성한다. 메인 지휘자는 입력·출력 조율, 소스 대조, 최종 검증을 맡는다.
   작성 백엔드 우선순위 codex→agy→로컬과 전문 서브 에이전트 역할은 서로 다른 층이다.
4. **분산은 마스터 큐에 등재.** ax-request로 register_work를 호출하고, 요청자가 골조·동결
   계약을 작업 브랜치에 싣는다. 골조 push가 마스터 파견을 건다. 실제 파견 여부와 태스크 이동을
   확인하고 결과 종결까지 기다린다. 신규 등록·improve_work·finalize는 별도 호출이다.
5. **회수·검증·기록.** 완료 통보 후 ax-advance로 조각을 작업 브랜치에 모아 검사하고 사용자에게
   전진 여부를 묻는다. 최종 main 머지는 ax-review/finalize의 별도 결정이다.
   직접 처리에는 log_history·redmine_note·승인 후 커밋 연결, 작성 신호를 남긴다.
   위임자의 완료 주장이나 마커만으로 완료 판정하지 않는다.

## 실제 배선

- NS `.mcp.json`에 ax-client와 unreal-mcp가 있다. ax-client는 실측 Python312 절대경로와
  `.ax/lib/axmaster/clientside/client_mcp.py`를 사용한다. settings.local.json의 허용 목록에도
  두 서버가 있다. 홈/local 스코프 ax-client는 이번 요약에서 발견되지 않았다.
- settings.json의 PostToolUse Edit|Write에 domain_hint가 등록되어 있다. 수정 파일 stem으로
  마스터에서 이웃 컨텍스트3건을 조회하고 세션에 전달한다. 이것은 **편집 후 보강**이지
  작업 전 필수 검색을 대체하지 않는다.
- SessionStart와 UserPromptSubmit에 pending_works가 등록되어 있다.
- PostToolUse에 work_completion과 asyncRewake=true가 등록되어 있다. 등록 응답의 work_id·
  round를 보고 큐 종결을 감시하며 결과·실패를 알려 세션을 깨운다. 이번에 새 작업으로
  자동 고지 수신을 재실증하지는 않았다.
- code-writer의 tools 허용 목록에는 ax-client search_context·get_task_template·
  find_recipes·get_anti_patterns·log_writer_signal이 있다. 문서상 선언과 실제 세션에서
  도구를 호출할 수 있는지는 별개이며, 허용 목록만으로 현재 연결 성공을 단정하지 않는다.

## 그대로 복사하면 안 되는 부분

실물 지침에도 예전 내용이 섞여 있다. code-writer/code-manager 본문은 combined_search를
말하지만 tools는 ax-client search_context다. NS 공용 지침에는 폐지된 attempt 브랜치,
watch.exe 재기동, 클라이언트는 등재 금지라는 옛 표가 남아 있어 최신 ax-request와 모순된다.
NS `.claude/CLAUDE.md` 관리 블록 밖에는 다른 프로젝트의 Listen Server 설명도 남아 있다.
따라서 실제 호출 이름·프로젝트 프로필·현재 정본7단계와 대조하여 필요한 작업 흐름만 참조한다.

기존 NS의 작은 수정 자동 위임·문서 작업 직접 처리 예외와, 이번 사용자가 확정한
“RAG 검색 후 단독/분산을 묻고 사용자 결정에 따라 서브 에이전트를 구성” 요구도 구분한다.
이번 .57 지침 반영에서는 **새 사용자 결정이 우선**이며 작은 수정이라는 이유로 선택을
대신 결정하거나 기존 NS 예외를 그대로 적용하지 않는다. 이미 같은 작업의 방식이 확정되었으면
다시 묻지 않는다. 분석·조회만 하는 현재 단계에서 구현이나 원격 파견을 시작하지 않는다.

## .57에 반영할 형태

CLAUDE.md·AGENTS.md의 홈/저장소 진입점에는 짧은 필수 흐름을 둔다:
**RAG 조회·소스 대조 → 근거·대상·분해안을 보여 단독/분산 선택 요청 → 확정 방식에 맞는
서브 에이전트 구성 → 단독 수행 또는 AX 워커 파견 → 실물 회수·검증·기록**.
자세한 호출 계약은 마스터 스킬에 둔다. .57은 ax-projects MCP를, .33은 ax-client MCP를
사용하므로 도구 접두사를 그대로 복사하지 않는다. UE 에디터·빌드 규칙도 Python 인프라에 옮기지 않는다.
로컬 서브 에이전트와 AX 원격 워커의 실행 근거를 별도로 남긴다.

이번 분석은 참조 근거를 마련한 상태다. 자동 로드 지침·분산 스킬 본문 반영과 원격 배달은
아직 하지 않았고, #716의 남은 운영 준비·실증을 완료로 표시하지 않는다.
