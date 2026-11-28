# #1041-E — MCP 도구 표면 큐레이션 및 읽기/쓰기 경계 강화 분석 보고서

> 작성일: 2026-11-28 · 일감: Redmine `#1047` (상위 `#1041`, `아이디어 — 추후 검토 수집`)  
> 대조 스킬: `ax-ontology` (`master/client/skills/ax-ontology/SKILL.md`), `ax-plan` (`master/skills/ax-plan/SKILL.md`), `ax-redmine` (`master/skills/ax-redmine/SKILL.md`), `distribute` (`master/skills/distribute/SKILL.md`)  
> 대조 코드: `master/projects/mcp_server.py`, `master/task_queue/mcp_server.py`, `master/task_queue/ontology_proxy.py`  
> NVIDIA 원전: `mcp/auto_ontology_mcp/tools.py`, `skills/nvidia-ontology-{setup,management,query}/SKILL.md`

---

## 1. 개요

NVIDIA `auto-ontology`는 OpenAPI에 87개 엔드포인트가 있지만, MCP 서버(`mcp/auto_ontology_mcp/tools.py`)에서는 **단 9개 읽기 전용 도구만 명시적 allow-list로 노출**하고 나머지는 전부 차단(`MCPType.EXCLUDE`)한다. 또한 기동 시 `missing_from_spec()`으로 업스트림 경로 변경을 즉시 실패 처리해 도구 표면이 조용히 줄어드는 사고를 막는다.

현재 AX 클러스터는 `ax-projects`(`master/projects/mcp_server.py`)에 **66개**, `ax-client`에 **65개**의 도구가 단일 MCP 서버에 혼재 노출되어 있다. 이 아이디어는 **에이전트 역할별(읽기 전용 조회/워커 vs 마스터 지휘/온톨로지 관리) MCP 도구 표면 분리·큐레이션과 도구 설명(description) 품질 표준화**를 검토한다.

---

## 2. 실제 코드쪽 내용

### 2.1 NVIDIA 원전 구현 (`mcp/auto_ontology_mcp/tools.py`)
- **명시적 allow-list**: `CURATED: tuple[ToolSpec, ...]` 7개 + 복합 도구 2개(`check_readiness`, `ask_question`) = 총 9개.
- **설계 원칙 (docstring L5-31)**:
  1. *"87개를 다 노출하면 그 한참 전부터 에이전트의 도구 선택 품질이 저하된다."*
  2. *"도구 설명은 개발자 API 문서가 아니라 프롬프트다 — 호출자의 문제 어휘로 언제 이 도구를 골라야 하는지 써야 한다."*
  3. *"원시 스키마 브라우저를 열지 않는다 — 열면 에이전트가 시맨틱 레이어를 우회한다."*
  4. **기동 시 계약 검증**: `missing_from_spec(openapi_spec)`이 allow-list 항목 누락 시 서버 기동을 실패시켜 침묵 드리프트를 차단.
- **스킬 3분리**: `nvidia-ontology-setup`(설치) · `nvidia-ontology-query`(읽기·검증, MCP) · `nvidia-ontology-management`(쓰기·인증, REST 전용).

### 2.2 AX 클러스터 기존 코드 현황
- **`master/projects/mcp_server.py` (`ax-projects`, 1,620줄, `@mcp.tool()` 66개)**:
  - 파일 상단 주석(L8-9)에 이미 *"이 서버가 프로젝트 레지스트리를 넘어 작업장의 단일 창구가 되고 있다. ... **다만 더 커지면 쪼갤 것**"*이라고 적혀 있다.
  - 현재 프로젝트 관리(`register_project`, `set_active`), RAG/온톨로지 읽기·쓰기(`search_context`, `create_domain`, `remove_ontology_item`, `sync_ontology`), 워크 등록(`register_work`), 플래닝/인터뷰(`plan_*`, `interview_*`), 웨이파인더(`wayfinder_*` 10종), 일감 시작/마감(`issue_*`), 워커 모드(`set_worker_mode`)가 **한 서버에 66개**로 뭉쳐 있다.
- **`ax-client` (65개 도구)**:
  - `.33` 요청자·서브에이전트가 쓰는 창구에도 조회(`search_context`, `get_object_spec`, `redmine_list_issues`)와 파괴적/쓰기 도구(`remove_ontology_item`, `rename_domain`, `redmine_delete_version`, `staging_discard`)가 함께 노출되어 있다.
- **실제 발생한 경계 사고 이력**:
  - `reports/167-931-refuse-ax-client-issue-on-master-requester.md` (`#931`): 마스터 요청자 프로젝트에서 `ax-client:issue_*`가 오호출되는 문제를 사후 거절 가드로 막아야 했다.
  - `GEMINI.md` (`#829`): Antigravity 같은 보조 에이전트에 쓰기/지휘 도구가 그대로 노출돼 있어 문서 규칙으로만 호출을 금지하고 있다.

---

## 3. 주의사항

1. **기존 배달 계약·스킬 호출명 하위 호환성 유지**:
   - `master/client/workshop/mcp.json`, `~/.claude.json`, `~/.codex/config.toml`, 그리고 모든 공용 스킬(`ax-plan`, `ax-redmine`, `ax-ontology`, `distribute`)이 현재 `ax-projects:*` / `ax-client:*` 도구 이름을 직접 참조한다.
   - 기존 서버를 갑자기 없애거나 도구 이름을 바꾸면 워커 배달(`master.client check`)과 모든 스킬이 깨진다. **읽기 전용 프로필/엔드포인트(예: `ax-read` 또는 `?profile=readonly`)를 추가**하는 점진적 분리가 안전하다.
2. **`mcp` 2.0.0 SDK 호환성 주의 (`mcp_server.py` L21-23)**:
   - 설치된 `mcp` 2.0.0에는 `fastmcp`가 없고 `mcp.server.MCPServer`만 있다. NVIDIA의 `FastMCP` `RouteMap` 코드를 그대로 옮길 수 없으며, `MCPServer` 등록 계층에서 allow-list 데코레이터/필터로 구현해야 한다.
3. **도구 수 감축이 기능 삭제로 이어지면 안 됨**:
   - 마스터 지휘자(Claude/Codex)는 여전히 웨이파인더·플랜·온톨로지 관리를 써야 한다. 목표는 기능 삭제가 아니라 **역할별 최소 권한 표면(예: 리서치/서브에이전트/워커 = 읽기 전용 10~15개)** 분리다.

---

## 4. 좋은점

- **도구 선택 정확도 향상 & 컨텍스트 토큰 절감**: 65~66개 도구 스키마를 매 턴 시스템 프롬프트에 싣는 비용과 오선택 확률을 크게 줄일 수 있다(특히 리서치·서브에이전트·워커 세션).
- **문서 규칙에만 의존하던 권한 경계를 구조적으로 강제**: "보조 에이전트는 쓰기/마감/삭제 도구를 부르지 말 것"을 지침 문구가 아니라 **읽기 전용 MCP 표면**으로 원천 차단 가능.
- **기동 시/테스트 시 표면 드리프트 자동 탐지**: NVIDIA의 `missing_from_spec()`처럼, 스킬이 참조하는 도구 목록과 실제 MCP 서버 노출 도구의 일치 여부를 `tests/integration/checks.json`에서 검증하면 스킬-서버 어긋남을 조기에 잡을 수 있다.

---

## 5. 나쁜점 및 리스크

- **설정·배달 경로 파편화**: MCP 서버 엔드포인트나 프로필이 늘어나면 `.57`·`.2`·`.33`·`.43` 및 Claude/Codex/Antigravity 설정 관리 포인트가 증가한다.
- **지휘 세션의 "권한 부족" 마찰**: 읽기 전용 표면으로 들어온 세션에서 갑자기 쓰기가 필요해지면 세션을 전환하거나 다른 창구를 써야 하는 불편이 생긴다(NVIDIA도 MCP는 읽기 전용, 쓰기는 REST+관리 스킬로 이원화해 같은 트레이드오프를 감수함).
- **도구 설명 일괄 정비 비용**: 60여 개 도구의 description을 "언제 쓸지" 중심으로 다듬는 작업은 코드 변경보다 검수·테스트 비용이 크다.

---

## 6. 실 작업 착수 시 권장 경계

- **1차 최소 범위**:
  1. 기존 `ax-projects` / `ax-client`는 그대로 유지하되, 각 도구를 `READ_ONLY` / `ONTOLOGY_WRITE` / `ORCHESTRATION` 태그로 분류하는 레지스트리 메타 추가.
  2. 보조 에이전트·워커용 **읽기 전용 프로필(10~15개 allow-list)** 노출 옵션과, 스킬 문서의 도구 참조 ↔ 실제 MCP 노출 도구 정합성 단위 테스트 추가.
