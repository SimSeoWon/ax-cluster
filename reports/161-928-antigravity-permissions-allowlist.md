# 161 — #928 Antigravity 툴 승인 팝업 반복 해결 — permissions.allow 일괄 사전 등록 및 마스터 생성기 연결

- **일시**: 2026-11-09
- **이슈**: #928 (선행: #926)
- **지휘 세션**: Antigravity (Gemini 3.8 Flash Medium)
- **작업 위치**: `.ax-issues/928` (`issue/928`) · 시작 리비전 `dffdf5f`

---

## 1. 배경과 문제

- **문제 (#926 실측 발견)**:
  Antigravity 세션 실행 중 MCP 도구 및 셸 명령 호출 시마다 사용자 UI에 권한 승인 팝업이 반복 발생하였다.
  사용자가 승인할 때마다 `settings.json`의 `permissions.allow`에 도구가 하나씩 사후 등록되는 구조였으며, 기존 인수인계서에 언급된 `toolExecutionPolicy: always-proceed`는 Antigravity 바이너리에 실재하지 않는 가상 설정으로 판명되었다.
- **원인 분석**:
  Antigravity는 보안상 `mcp(*)` 같은 포괄 와일드카드를 거부하고, `mcp(<server>/<tool>)` 형식의 도구 단위 및 `command(<prefix>)` 접두사 매칭으로 권한을 검사한다.
  또한 기존 `master.client master-local` 생성기는 agy 권한에 `READ_APPROVE` 3개만 등록하고 검사 조건도 정확한 일치(`==`)로 제한하여, 클러스터 필수 도구 및 CLI 명령어가 누락되어 있었다.

---

## 2. 해결 내용

1. **`settings.json` 권한 화이트리스트 일괄 사전 등록 (T1)**:
   - [`~/.gemini/antigravity-cli/settings.json`](file:///home/sim/.gemini/antigravity-cli/settings.json)의 `permissions.allow`에 다음 항목들을 일괄 등록:
     - `ax-projects` MCP 도구 45종 전수 (`mcp(ax-projects/issue_start_tool)`, `plan_set_tool` 등)
     - `ax-client` MCP 도구 64종 전수 (`mcp(ax-client/redmine_note)`, `list_locked` 등)
     - 클러스터 필수 CLI 접두사 20종 (`command(git)`, `command(git -C)`, `command(python3)`, `command(.venv/bin/python)`, `command(cd /home/sim/ax-cluster)`, `command(AX_PROJECTS_ROOT=)`, `command(systemctl)`, `command(journalctl)`, `command(agy)` 등)
   - 총 92개 항목을 합집합하여 누적 241개 항목으로 화이트리스트를 완비하였다.

2. **`master/client/master_local.py` 생성기 및 검사기 정비 (T2)**:
   - `AGY_BASE_COMMANDS` 상수를 신설하여 기본 CLI 명령 접두사를 정의.
   - `agy_permissions_text`에 `extra_commands` 파라미터를 추가하여 기본 명령 접두사를 함께 반영.
   - `check()` 검사에서 정확한 일치(`==`) 대신 부분집합 포함(`set(READ_APPROVE).issubset(set(appr))`)으로 완화하여, 사전에 등록된 도구들이 있어도 대조를 통과하도록 개선.
   - `master/test_client_master_local.py`에 확장 검증 케이스를 추가하고 88/88 전수 통과 확인.

3. **리포트 160 정정 (T3)**:
   - #926 실증 리포트에서 가상의 설정 및 "팝업 0건" 주장을 실측 사실(수동 승인 반복 발생 및 #928로 이관 해결)로 정정.

---

## 3. 검증 결과

1. **단위 검증 (`master/test_client_master_local.py`)**:
   - `88/88 통과` (OK).
2. **포맷 검사**:
   - `git diff --check`: rc 0.
3. **공식 통합 검사 (`tests/integration/test_axcluster.py`)**:
   - 공식 통합 목록(191건): 전수 통과.

---

최종 결과는 Redmine 마감 노트.
