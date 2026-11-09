# 164 — #929 BC-250 종료 점검 fail-open 차단·단절 판정 강화 및 누락 방지 자동화

> 2026-11-10 · Antigravity 지휘 · 시작 `5efb6792822ca51ff6e19945af5bcf1702076314` · 브랜치 `issue/929`

## 배경과 범위

`#702`(`c1b2537`, 리포트 163)로 추가된 BC-250 전원 종료 스킬(`ax-bc250-shutdown`)에 대해 Claude 및 Codex의 사후 검토에서 지적된 5가지 미흡점을 보완하고, 향후 누락을 원천 차단하는 검사를 자동화했다.

1. **사전 점검 fail-open 차단 (`master/infra/bc250_shutdown.py`)**:
   - `check_queue`: `tasks=None` 또는 비정상 데이터 시 `PreflightCheckError` 차단. worker 식별 시 단어 경계(`(?:^|\D)43(?:\D|$)`) 매칭을 적용해 `worker-143` 오탐 방지.
   - `check_broker_inflight`: `endpoints=None` 시 fail-open 통과하던 경로 제거, `PreflightCheckError` 차단.
   - `check_remote_processes`: 원격 SSH 명령 끝의 `|| true` 제거. pgrep 정상 미검출(rc=1, stderr 비어있음)만 프로세스 0건으로 통과시키고, pgrep 오류(rc>1, stderr 존재) 및 SSH 연결 불가(rc=255)는 `PreflightCheckError`로 차단.
2. **단절 판정 강화 (`verify_shutdown`)**:
   - SSH 1회 실패로 인한 조기 전원 차단 오판 방지.
   - Ping(`ping -c 1 -W 1`) 및 SSH probe를 병행하고, 연속 실패(consecutive failures >= 2)를 충족할 때만 단절로 판정.
3. **Claude 스킬 링크 및 누락 검사 자동화 (`master/client/master_local.py`)**:
   - `~/.claude/skills/ax-bc250-shutdown` 심볼릭 링크 연결.
   - `master-local --check`에 `master/skills/*` ↔ `~/.claude/skills` 대조 검사 항목 추가.
   - `master-local --apply` 시 누락된 Claude 스킬 심볼릭 링크 자동 생성 지원.
4. **공식 통합 검사 등록 및 누락 방지 자동화 (`tests/integration/`)**:
   - `tests/integration/checks.json`에 `master/test_bc250_shutdown.py` (35 checks) 등록.
   - 신규 단위 검사 `master/test_integration_coverage.py`를 작성하여 `checks.json` 누락 테스트 발생 시 즉시 FAIL 차단 (의도적 제외 26종은 명시 상수로 관리).
   - 공식 통합 검사 수 191종 → 193종으로 확장.
5. **문서 및 계약 보완**:
   - `master/skills/ax-bc250-shutdown/SKILL.md`: `ax-client:issue_cancel` 오안내 정정(일감 관리 도구와 프로세스 종료 구분), 물리 전원 재가동 필수 안내, `--force` 실제 우회 범위 명시.
   - `CLAUDE.md`, `AGENTS.md`: 통합 검사 누락 방지 검사 및 스킬 링크 대조 검사 지침 1줄 보완.

## 검증 결과

1. **단위 및 계약 테스트 35/35 전수 통과**:
   - `cd /home/sim/ax-cluster/.ax-issues/929 && .venv/bin/python -m unittest master.test_bc250_shutdown -v`
   - `Ran 35 tests in 0.932s · OK`
2. **마스터 로컬 설치기 단위 테스트 113/113 통과**:
   - `cd /home/sim/ax-cluster/.ax-issues/929 && .venv/bin/python master/test_client_master_local.py`
   - `OK test_client_master_local: 113/113 통과` (스킬 누락 감지 및 자동 링크 생성 검증 포함)
3. **통합 검사 커버리지 검사 2/2 통과 및 미등록 차단 실측**:
   - `cd /home/sim/ax-cluster/.ax-issues/929 && .venv/bin/python -m unittest master.test_integration_coverage -v`
   - `Ran 2 tests in 0.004s · OK`
   - 미등록 더미 테스트 추가 시 `FAIL` 차단 실측 완료.
4. **스킬 규약 및 홈 가이드 검사**:
   - `test_skill_conventions`: 50/50 통과
   - `test_home_guides`: 47/47 통과
5. **공식 통합 검사 (신규 2종 개별 검증)**:
   - `test_192_test_bc250_shutdown`: 검사 35건 통과
   - `test_193_test_integration_coverage`: 검사 2건 통과
