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

**다음 걸음 (순서대로)**

1. **대조** — `.33` 산출물 vs 원전 `watcher/` 템플릿. 어느 쪽이 앞서는지 세지 않고 정본을 정하면
   리포트 27 §3 의 실패(로컬이 54항목 뒤진 포크였다)를 반복한다
2. **위임 구멍 2개 이식** — Redmine 읽기·수정 8종 · task template 2종(+`code_recipes` 2종).
   [주의] **읽기라도 8103 에 두지 않는다** — 그 포트 `/api/v1/*` 는 무인증 공개라 일감 본문이 LAN 에
   열린다. `redmine_note` 와 같은 토큰 잠긴 큐(8101)에 붙인다
3. **재배선** — `agents/` 9종의 `tools:` 를 `mcp__ax-client__*` 로. 2 가 선행 조건
4. **배달 경로** — `deliver` 가 이 디렉토리를 보낸다. **그전까지 `.33` 사본이 실사용본이므로
   여기만 고치면 조용히 갈린다**
5. **템플릿화** — 프로젝트 고유 문자열 실측 `ModularStage` 13 · `MissionRuntime` 7 ·
   절대경로 6 · `Project_Alpha` 3. 두 번째 프로젝트가 실제로 생길 때 치환한다
