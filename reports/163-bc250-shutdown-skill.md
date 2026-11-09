# 163 — #702 BC-250 전용 안전 전원 종료 스킬 추가

> 2026-11-09 · Antigravity 지휘 · 시작 `9228cbfc2178751c602352998c5b63b279378a58` · 브랜치 `issue/702`

## 사용자 결정과 범위

- 사용자: 「지금껏 작업 큐 확인하고 끄던데 스킬이 없다고? ... 응 그럼 파이썬으로 하나의 스킬로 만들어줘 ... 진행해」
- 대상: BC-250 (.43) 전용 안전 전원 종료 스킬(`ax-bc250-shutdown`) 및 백엔드 파이썬 모듈(`master.infra.bc250_shutdown`).
- 핵심 계약:
  1. **.43 단독 대상 고정**: `.2`(Windows/UE5), `.33`(사용자 PC/게임 요청자), `.57`(마스터 sim-desktop) 비접촉 보장. 타 노드 입력 시 `TargetRefusalError`(rc=3) 즉시 거절 (force 옵션으로도 해제 불가).
  2. **사전 점검 3종**: 활성 큐 작업(claimed/submitted), 브로커 inflight(>0), 원격 잔여 프로세스(codex/claude/python/node) 자동 검사.
  3. **전원 종료 및 단절 확인**: `ssh sim@192.168.0.43 'sudo -n systemctl poweroff'` 실행 및 SSH probe 단절(rc!=0) 감지.

## 구현 상세

1. **`master/infra/__init__.py`**:
   - `master.infra` 패키지 초기화 및 `bc250_shutdown` 핵심 심볼 노출.
2. **`master/infra/bc250_shutdown.py`**:
   - `validate_target(target)`: 오직 `192.168.0.43`, `bc250-1`, `bc250`, `.43`만 허용.
   - `check_queue(status_data)`: `.43` 대상 활성 태스크 진행 중 시 `PreflightCheckError` 차단.
   - `check_broker_inflight(status_data)`: `.43` 엔드포인트 inflight > 0 진행 중 시 `PreflightCheckError` 차단.
   - `check_remote_processes(target)`: SSH `pgrep -u sim -l -f '[c]odex|[c]laude|[p]ython|[n]ode'` 실행, 잔여 작업 프로세스 검출 시 차단 (오프라인/단절 상태는 통과).
   - `execute_shutdown(target, dry_run)`: `sudo -n systemctl poweroff` 실행 (`--dry-run` 지원).
   - `verify_shutdown(target, timeout)`: SSH probe 루프를 통해 전원 차단 확인.
   - `main()`: `--dry-run`, `--check-only`, `--force`, `--target`, `--json` 지원 CLI.
3. **`master/skills/ax-bc250-shutdown/scripts/shutdown.py`**:
   - `master.infra.bc250_shutdown`을 호출하는 실행 스크립트.
4. **`master/skills/ax-bc250-shutdown/SKILL.md`**:
   - 발화 예시(「BC250 꺼줘」, 「BC-250 종료」 등) 및 사용 가이드, 문제 해결 규약 문서화.
5. **`master/test_bc250_shutdown.py`**:
   - 계약 및 단위 테스트 15종 (타겟 거절, 사전 점검 3종, dry-run, poweroff 호출, 단절 확인, CLI 반환 코드).

## 검증 결과

1. **단위 테스트 통과**:
   - `python -m unittest master.test_bc250_shutdown -v`
   - **`Ran 15 tests in 1.017s` · `OK`** (15/15 전수 통과).
2. **실측 1: dry-run 점검**:
   - `python master/skills/ax-bc250-shutdown/scripts/shutdown.py --dry-run`
   - 사전 점검 3종(큐 태스크 0건, 브로커 inflight 0건, 원격 잔여 프로세스 0건) 정상 통과 및 계획 출력 확인.
3. **실측 2: 비접촉 계약 위반 차단**:
   - `python master/skills/ax-bc250-shutdown/scripts/shutdown.py --target 192.168.0.2 --dry-run`
   - `[TARGET REFUSAL] 대상 '192.168.0.2' 거절: .2, .33, .57 비접촉 계약 위반. 오직 .43 (192.168.0.43)만 대상이다.` (rc=3) 즉시 거절 실측.
