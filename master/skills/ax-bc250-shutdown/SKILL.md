---
name: ax-bc250-shutdown
description: BC-250(.43) 전용 안전 전원 종료 스킬. 활성 큐 작업·브로커 inflight·원격 잔여 프로세스를 사전 점검하고 `sudo -n systemctl poweroff` 실행 및 SSH 단절 확인. "BC250 꺼", "BC250 꺼줘", "BC-250 종료", ".43 꺼줘", "/ax-bc250-shutdown" 같은 발화에 발동. Claude·Codex·Antigravity 공용.
---

# ax-bc250-shutdown — BC-250 (.43) 전용 안전 전원 종료

## 목차

- 개요
- 0. 무엇을 하는가
- 1. 절대 하지 않는 것 (.2·.33·.57 비접촉 계약)
- 2. 실행 명령
- 3. 사전 점검 (Pre-flight checks) 3종
- 4. 전원 종료 및 단절 확인
- 5. 문제 해결

## 개요

> 정본: `~/ax-cluster/master/skills/ax-bc250-shutdown/SKILL.md` · 모듈 `master/infra/bc250_shutdown.py`
> 근거: 일감 `#702` · [docs/6-node-failover.md](../../../docs/6-node-failover.md) · [reports/69-bc250-shutdown-20260919.md](../../../reports/69-bc250-shutdown-20260919.md)

사용자가 **"BC250 꺼줘"**, **"BC-250 종료"**, **".43 꺼줘"** 등의 지시를 내렸을 때,
임시 셸 스크립트나 일회성 명령 대신 검증된 단일 파이썬 모듈로 안전 점검 후 전원을 종료한다.

## 0. 무엇을 하는가

1. **사전 점검 3종**: 큐 작업 잔여 여부, 브로커 inflight 추론 여부, 원격 `.43` 상의 잔여 작업 프로세스(codex/claude/python 등) 확인.
2. **안전 종료**: `ssh sim@192.168.0.43 'sudo -n systemctl poweroff'` 실행.
3. **단절 확인**: 종료 후 SSH 재조회 타임아웃/연결 거부를 감지하여 실제 전원 차단 확인.

## 1. 절대 하지 않는 것 (.2·.33·.57 비접촉 계약)

- **오직 `.43` (192.168.0.43 / bc250-1)만 대상이다.**
- `.2` (Windows/UE5), `.33` (사용자 작업 PC/게임 요청자), `.57` (마스터 sim-desktop) 등 다른 머신은 대상 인자로 지정될 수 없으며, 코드가 실행 전 엄격히 거절(`TargetRefusalError`, rc=3)한다.
- `--force` 플래그를 주더라도 대상 노드 비접촉 계약은 해제되지 않는다.

## 2. 실행 명령

작업 위치 `/home/sim/ax-cluster`에서 실행한다:

```bash
# 1) 계획만 확인 (실행 안 함)
.venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py --dry-run

# 2) 사전 안전 점검만 수행
.venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py --check-only

# 3) 실제 안전 전원 종료 실행
.venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py

# 4) JSON 출력 형식
.venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py --json
```

## 3. 사전 점검 (Pre-flight checks) 3종

1. **큐 점검 (`check_queue`)**:
   - `master.status.fetch_live()`의 tasks/works 데이터를 조회.
   - `.43`에 할당된 활성(claimed, submitted 등) 태스크가 있으면 `PreflightCheckError`(rc=1)로 즉시 중단.
2. **브로커 점검 (`check_broker_inflight`)**:
   - 브로커 엔드포인트 목록 중 `.43` 호스트의 `inflight > 0`인 경우 즉시 중단.
3. **원격 프로세스 점검 (`check_remote_processes`)**:
   - SSH `pgrep -u sim -l -f '[c]odex|[c]laude|[p]ython|[n]ode'`로 잔여 작업 프로세스 점검. 작업 프로세스가 돌고 있으면 즉시 중단.
   - 단, 대상 노드가 이미 전원 종료되어 SSH 연결이 거부되는 경우(rc 255 등)는 오프라인 상태로 인식하고 통과.

## 4. 전원 종료 및 단절 확인

- **명령**: `.43`의 `systemctl poweroff`에는 NOPASSWD가 설정되어 있어 no-TTY 환경에서도 비밀번호 없이 `sudo -n systemctl poweroff`로 즉시 실행된다.
- **단절 확인**: 종료 명령 직후 `ssh -o ConnectTimeout=2 sim@192.168.0.43 true` 프로브 루프를 돌아 연결이 끊기는 시점을 포착, 전원이 완전히 차단되었음을 확인한다.

## 5. 문제 해결

- **[TARGET REFUSAL] (rc=3)**: `.43` 이외의 잘못된 타겟이 지정됨. 대상을 확인하고 수정한다.
- **[PREFLIGHT FAILED] (rc=1)**: 진행 중인 큐 작업이나 원격 작업 프로세스가 존재함. 작업을 먼저 완료 또는 취소(`ax-client:issue_cancel` 등)한 뒤 재시도한다.
- **[SHUTDOWN FAILED] (rc=2)**: 종료 명령 후 타임아웃(기본 30초) 내에 SSH 연결이 끊기지 않음. 네트워크 상태나 노드 로그를 확인한다.
