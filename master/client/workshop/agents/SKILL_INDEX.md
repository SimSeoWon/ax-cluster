# SKILL INDEX

에이전트 역할과 위임 기준을 정의합니다.
각 에이전트는 `.claude/agents/<name>.md` 단일 파일로 등록되어 Claude Code의 `Agent` 툴에서 `subagent_type`으로 호출됩니다.

| 에이전트 | 역할 | 주요 트리거 |
|----------|------|------------|
| `source-analyzer` | 변경 파일 → RAG 컨텍스트 MD 생성 | 새 파일 분석, 구조 파악 |
| `project-analyzer` | 저장소 전체 구조·아키텍처 분석 | 프로젝트 개요, 모듈 관계 |
| `code-convention` | 컨벤션(네이밍·주석·포맷) 검토 | 스타일 검사 |
| `code-writer` | 코드 초안·리팩터링 제안 | 기능 구현, 수정 |
| `code-validator` | 버그·안전성 탐지 + 수동 리뷰 + Redmine + 수정 완료 검증/Resolved 처리 | "리뷰해줘", "분석해서 점검", "수정했어 검토해줘", "이거 닫아줘" |
| `build-integration` | 빌드 스크립트·의존성 영향 분석 | 빌드 실패, 의존성 변경 |
| `code-manager` | 전문 에이전트 조율·통합 리포트 | 전체 리뷰, 파이프라인 |
| `log-reviewer` | UE5 로그 에러·경고 분석 | ".log 봐줘" |
| `crash-diagnoser` | 크래시 덤프·로그 원인 분석 | ".dmp 분석" |
| `asset-validator` | DataValidation 커맨드렛 결과 분석 | "에셋 검증" |
| `review-consultant` | 리뷰 지적 상담 + 코멘트 기록 + "의도된 기능" 시 Redmine·plan 일괄 갱신 | "이 지적 어떻게", "의도된 기능" |
| `ue-editor-operator` | UE 5.8+ 공식 Unreal MCP 래핑 — 온톨로지·RAG grounding 후 라이브 에디터 조작 (config `unreal_mcp_port` + 에디터 기동 필수) | "에디터에서 ~해줘", "블루프린트 수정", "레벨에 배치", "에디터 테스트" |

## 실행 방법
- **자동**: watch.py가 커밋 감지 시 컨텍스트 생성 + 자동 리뷰 수행 (에이전트 직접 호출 아님 — 내부 로직)
- **수동**: Claude Code 세션에서 사용자 요청 → 메인 Claude가 `Agent(subagent_type="...")` 호출

## RAG 검색
- `combined_search(query, tags?)` — 벡터 + 태그 통합 검색 (항상 우선 사용)
- `vector_search(query)` / `search_context(tags)` — 단독 검색 (특수한 경우)
- `rebuild_index()` / `index_status()` — 인덱스 관리
- watch.py가 컨텍스트 갱신 시 자동 인덱싱

## Redmine 이슈 관리
- `mcp__ax-client__redmine_list_issues` / `redmine_get_issue` / `redmine_create_issue` /
  `redmine_note`(코멘트·상태·완료율) / `redmine_meta`(상태·트래커·마일스톤 카탈로그) /
  `redmine_link_commit`
- [주의] **`create_review_issue`(리뷰 MD 자동 파싱)는 미이식** — 골라내는 일은 에이전트가 한다
- [중요] **API 키는 이 PC 에 없다** — 마스터(큐 8101)가 대행한다. `config.json` 설정 불필요
  (그 파일은 2026-08-20 에 삭제됐다)

## 컨텍스트 코멘트 시스템
- `.claude/context/<도메인>/<파일>.md`의 `## 코멘트` 섹션에 개발자 노트 기록
- 태그: `[리뷰]` / `[방향]` / `[고민]` / `[진행]` / `[메모]`
- 벡터 임베딩에서 제외 (검색 품질 유지) + 리뷰 시 에이전트가 참조
- 컨텍스트 MD 갱신 시 자동 보존
- `review-consultant` 에이전트가 기록 담당
