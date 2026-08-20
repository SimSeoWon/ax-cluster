# workshop — 작업장 클라이언트 자산

> 반입 2026-08-20 (#226). [주의] **이것은 아직 정본이 아니다** — `.33` 디스크에서 베껴 온
> **생성기의 산출물 스냅샷**이다. 아래 §3 이 그 차이와 다음 걸음을 적는다.

## §1 원전은 무엇을 배포했나 (`~/AgentTest/build.bat` 실측)

`AgentWatch.zip` = **exe 12종 + 번들 자산**. UE5 프로젝트 루트에 풀면 끝이다(`INSTALL.md`).

| # | 산출물 | 자리 | 이식본의 대응물 |
|---|---|---|---|
| 1 | `watch.exe` | 루트 | **은퇴** — 마스터 큐(8101) + 기계별 claimer (#204). 2026-08-20 삭제 |
| 2 | `context_search.exe` | `.claude/mcp/` | 마스터 `ax-projects`(8103) + `ax-client` 조회 9종 |
| 3 | `log_analyzer.exe` | `.claude/mcp/` | **로컬 유지** — UE5 로그는 그 기계 것 |
| 4 | `crash_analyzer.exe` | `.claude/mcp/` | **로컬 유지** |
| 5 | `commandlet_runner.exe` | `.claude/mcp/` | **로컬 유지** (UE5 커맨드릿) |
| 6 | `agy_query.exe` | `.claude/mcp/` | 로컬 `agy` CLI (마스터에도 있다) |
| 7 | `redmine_tracker.exe` | `.claude/mcp/` | [주의] **미이식** — `ax-client` 에 `redmine_note` 하나뿐 |
| 8 | `code_recipes.exe` | `.claude/mcp/` | [주의] **미이식** — `log_writer_signal` 만 이식됨 |
| 9 | `task_queue.exe` | `.claude/mcp/` | 마스터 큐 8101 (단일 writer) |
| 10 | `worker.exe` | `.claude/daemons/` | 마스터 claimer + `ax-work` 스킬. **2026-08-20 삭제**(재빌드 가능한 산출물이라 백업 없이) |
| 11 | `master_orchestrator.exe` | `.claude/mcp/` | 마스터 통합자·파이프라인 |
| 12 | `local_llm_runner.exe` | `.claude/mcp/` | 마스터 브로커 8102 |
| + | `onnx_model/`(임베딩) | `.claude/mcp/` | 마스터 벡터 색인 |
| + | `tools/{sqlite3,jq}.exe` | `.claude/tools/` | **로컬 유지** (세션이 db·jsonl 을 직접 질의) |

[주의] `.33` 에 있는 `gemini_query.exe`·`ontology_viewer.exe` 는 **이 12종에 없다** — 옛 버전 잔재다.

## §2 [중요] zip 에는 에이전트·스킬이 없다 — `watch.exe` 가 **생성**한다

`build.bat` 은 zip 직전에 이것들을 **일부러 지운다**: `agents`·`skills`·`hooks`·`context`·`plans`·
`recipes`·`reviews`·`logs`·`tasks`·`vector_db`·`worktrees`·`CLAUDE.md`·`.mcp.json`·`config.json`
(*"PC 별 환경 파일이 zip 에 섞이면 클라 PC 가 자기 설정을 덮어쓴다"*). `INSTALL.md` 3단계가
*"`.claude\` 폴더 구조가 생성되고 … `agents\` ← 에이전트 9개"* 라고 말하는 그대로다.

**즉 원전의 정본은 파일이 아니라 생성기다** (`~/AgentTest/watcher/`, 참조 전용):

    agent_defs.py 41KB + agent_templates.py      → .claude/agents/*.md
    skill_defs_ontology.py 63KB + skill_defs_distribute.py 49KB
      + skill_defs_collab.py 37KB + skill_templates.py   → .claude/skills/*/SKILL.md
    project_claude_md.py 30KB                    → 프로젝트 CLAUDE.md
    config_init.py 21KB · setup.py 28KB          → config.json · .mcp.json · 폴더 구조

우리 이식본의 대응물은 **`../bundle.py`**(AX 블록 생성) + **`../skills/ax-*`**(파일 보관)다.
아키텍처는 이미 같은 모양이고, **빠진 것은 그 생성기의 나머지 절반** — 에이전트 12종 · 작업장
스킬 11종 · 프로젝트 `CLAUDE.md` 본문.

## §3 그래서 이 디렉토리의 성격 — 스냅샷이지 정본이 아니다

| 무엇 | 어디서 왔나 | 성격 |
|---|---|---|
| `agents/` 12종 + `SKILL_INDEX.md` | `.33` 디스크 | **생성기 산출물** — 원전 `agent_defs.py` 와 드리프트했을 수 있다(미대조) |
| `skills/` 11종 + `debate` | `.33` 디스크 | **생성기 산출물** — 원전 `skill_defs_*.py` 와 미대조 |
| `CLAUDE.md` 534줄 | `.33` 디스크 | **생성기 산출물**(`project_claude_md.py`) + 사람 편집이 섞였다 |
| `rules/` 5종 | `.33` 디스크 | [중요] **생성기가 없다** — 사람이 쓴 UE5 코딩·아키텍처 지식이다. 성격이 다르며, 게임 저장소가 `.gitignore` 로 빼 왔으니 **어디에도 버전 관리되지 않던 사람의 지식**이다 |
| `hooks/domain_hint.py` | `.33` 디스크 | 생성기 산출물 |
| `mcp.json` | `.33` 디스크 | 등록 11종 (원전 exe 5종 제거 후 · #226 4단계) |

## §4 대조 결과 (2026-08-20 실측 · 원전 템플릿을 직접 렌더해서 비교)

[중요] **정본은 한쪽이 아니다 — 항목마다 앞선 쪽이 다르다.** 그래서 단순 복사로는 안 된다.

| 항목 | 앞선 쪽 | 실측 |
|---|---|---|
| 에이전트 11종 | **동일** | 드리프트 0 (`agent_defs.AGENT_DEFINITIONS` 렌더 == `.33` 파일) |
| `ue-editor-operator` | **원전** | `.33` 이 **37줄 부족**. 빠진 것: ① [중요] *"쓰기 성공 응답을 믿지 말 것 — set 계열이 no-op 에도 true 를 반환"*(원전 실측 2026-08-02) + **mutation 후 재조회 검증 의무** ② 범용 리플렉션 한계(`FInstancedStruct`) 대응 ③ §4 게임 소스 갭 → 핸드오프 절차 ④ `get_object_spec` 도구 |
| 스킬 10종 | **동일** | 드리프트 0 |
| `manage-contract` 스킬 | 원전에만 | [완료] **새 구멍이 아니다** — `@ms-contract` 태그가 미러 소스에 **0건**이라 M4 에서 **재범위**로 판정된 항목(`#152`, 닫지 않음). 게임 소스가 태그를 쓰기 시작하면 그때 |
| `manage-domain`·`manage-task` | **우리** | 어제 재배선 (+16 · +3줄) |
| 프로젝트 `CLAUDE.md` 관리 블록 | **우리** | 원전 338줄 vs `.33` 363줄 · 차이 89줄 — 원전에만 32줄(교체된 옛 도구 목록) · `.33` 에만 57줄(`mcp__ax-client__*` 재배선 · 별칭 절차 5→3단계 · 가드 사유 문안) |
| `.mcp.json` | **우리** | 원전 10종 − 제거 5 + `ax-client` + 사람 도구 5(`gemini-cli`·`unreal-mission-editor`·`uelog-analyzer`·`unreal-mcp`·`gemini-query`) |

[주의] **`.33` 배포본은 옛 빌드다** — `ue-editor-operator` 의 누락과 `manage-contract` 미배포가
같은 시점을 가리킨다. 리포트 27 §3(로컬 온톨로지가 54항목 뒤진 포크)과 **같은 실패 계열**이고,
이번에는 세고 나서 정했다.

**다음 걸음 (순서대로)**

1. [완료] **대조** — 위 §4. 머지 방향이 정해졌다: 에이전트·스킬은 **원전 → 저장소**,
   재배선분(`manage-domain`·`manage-task`·`CLAUDE.md`·`mcp.json`)은 **우리 것 유지**
2. [완료] **위임 구멍 이식** (2026-08-20) — `ax-client` **14 → 21종**. Redmine 5종
   (`redmine_list_issues`·`redmine_get_issue`·`redmine_meta`·`redmine_create_issue`·
   `redmine_link_commit`) + 태스크 템플릿 2종. [중요] **읽기라도 8103 에 두지 않았다** — 그 포트
   `/api/v1/*` 는 무인증 공개라 일감 본문이 LAN 에 열린다(라이브: 요청자 200 · **워커 403** ·
   무토큰 401 · 8103 에는 404). 기준은 「읽기냐 쓰기냐」가 아니라 **「그 데이터가 공개 표면에
   있어도 되냐」**다 — 온톨로지·템플릿은 공개 뷰와 같은 데이터라 8103 이 맞다.
   [주의] **`code_recipes` 2종은 이식하지 않았다 — 입력이 0이다.** 실측: 신호 1건 < 합성 문턱 5,
   합성물 0건. `#152`(`@ms-contract` 0건 → 재범위)와 같은 판단. `code-recipes` MCP 등록은
   `.mcp.json` 에 남아 있어 `code-writer` 참조는 깨지지 않는다
3. **재배선** — `agents/` 9종의 `tools:` 를 `mcp__ax-client__*` 로. 2 가 선행 조건
4. **배달 경로** — `deliver` 가 이 디렉토리를 보낸다. **그전까지 `.33` 사본이 실사용본이므로
   여기만 고치면 조용히 갈린다**
5. **템플릿화** — 프로젝트 고유 문자열 실측 `ModularStage` 13 · `MissionRuntime` 7 ·
   절대경로 6 · `Project_Alpha` 3. 두 번째 프로젝트가 실제로 생길 때 치환한다
