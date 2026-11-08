# 157 — #924 마스터 담당 기록에 Antigravity 추가 및 Claude·Codex 호환 경로 정비

> 2026-11-08 · Antigravity (Gemini Flash Medium) · 일감 #924 · 시작 리비전 `4691993` · 작업 위치 `.ax-issues/924`(`issue/924`)

## 왜

사용자 요청(2026-11-08):
「그러네 클로드 코덱스만 허용했는데 이제 안티그래비티도 추가해야겠네」 → 「일단 일감을 추가해줘. 그리고 관련해서 신경써야 하는 부분들도 명시해주고」 → 「924번 진행해」.

종전 마스터 담당 기록(`master/work/conductor.py`, `client/runtime/client_mcp.py`, `master/skills/ax-handoff/scripts/conductor.py` 등)은 `claude`와 `codex`만 허용하도록 고정되어 있어 Antigravity가 마스터 지휘를 인수한 사실을 정본 도구·스키마로 기록할 수 없었다.
#920 아이디어에서 분리된 이 일감을 통해 Antigravity를 정식 마스터 담당 식별자로 추가하고 관련 CLI, MCP 도구 스키마, WebUI 레이블, 단위 검증을 정비한다.

## 변경 내용

1. **코어 기록 및 판정 (`master/work/conductor.py`)**:
   - `master_record()`: 읽기 허용 목록에 `antigravity` 추가. 기존에 혹시 기록되었을 수 있는 별칭 `agy` 읽기 시 `antigravity`로 정규화 수용.
   - `record_master(agent, why, by)`: 입력된 `agy`를 `antigravity`로 자동 정규화. 허용 식별자를 `("claude", "codex", "antigravity")`로 확장하고, 그 외 모르는 값은 명시적으로 `ValueError` 거절.
2. **WebUI 표시 레이블 (`master/webui/orchestration.py`)**:
   - `labels` 매핑에 `"antigravity": "Antigravity"`, `"agy": "Antigravity"` 추가하여 지휘 상태 카드에 정상 표기되도록 지원.
3. **MCP 도구 스키마 (`client/runtime/client_mcp.py`, `master/projects/mcp_server.py`)**:
   - `client_mcp.py`: `record_master_conductor` 도구의 `inputSchema.properties.agent.enum`에 `"antigravity"`, `"agy"` 추가.
   - `mcp_server.py`: `record_master_conductor_tool` 설명에 `antigravity` 지원 명시.
4. **CLI 인수 choices 및 스킬/문서 (`master/skills/ax-handoff/scripts/conductor.py`, `master/skills/ax-handoff/SKILL.md`, `docs/16-worker-orchestrator-mode.md`)**:
   - `conductor.py` CLI의 `record-master` positional `agent` choices에 `antigravity`, `agy` 추가.
   - `SKILL.md` 및 `docs/16-worker-orchestrator-mode.md`의 마스터 담당 설명에 `antigravity` 추가.
5. **단위 및 통합 검증 (`master/test_orchestration_control.py`)**:
   - `test_record_antigravity_and_alias()` 추가: antigravity 정본 기록/조회, WebUI `section()` Antigravity 레이블 노출, `agy` 별칭 POST 시 `antigravity` 정규화 저장, 미지원 식별자 400 거절 검증.

## 검증

- `master/test_orchestration_control.py`: rc0 **29/29 통과** (Antigravity 정본/별칭/거절 검증 포함).
- `master/test_client_mcp.py`: rc0 **350/350 통과** (클라이언트 MCP 계약 전수 통과).
- `conductor.py record-master --help`: choices에 `{claude,codex,antigravity,agy}` 정상 노출 확인.
- `git diff --check`: rc0 (공백·포맷 결함 없음).
- 공식 통합 검사: `tests/integration/checks.json` 191건 전수 통과 (`Ran 191 tests in 180.638s` · `OK`).

최종 결과는 Redmine 마감 노트.
