---
name: ax-handoff
description: AX 마스터 Claude/Codex 세션을 교대하거나 토큰 소진 뒤 작업을 이어받을 때 인수인계와 실제 상태를 대조하고, 마스터 담당 기록 및 사용자가 선택한 워커 지휘자 모드를 기존 도구로 연결한다.
---

# ax-handoff — 인수인계와 지휘 상태

## 목차

- 개요
- 작업 복원
- 마스터 담당과 워커 지휘자
- 다음 인계

## 개요

정본: `~/ax-cluster/master/skills/ax-handoff/SKILL.md`.
근거: [`docs/15-orchestrator-handoff.md`](../../../docs/15-orchestrator-handoff.md) §15.4,
[`docs/orchestrator-rules.md`](../../../docs/orchestrator-rules.md) §2,
[`docs/16-worker-orchestrator-mode.md`](../../../docs/16-worker-orchestrator-mode.md) §16.6·16.9·16.10.

## 작업 복원

작업 위치는 `/home/sim/ax-cluster`로 맞춘다. 읽기 전에 `rg --files`로 실제 경로를 확인한다.
인수인계서 `docs/orchestrator-handoff.md` 한 벌과 공용 규칙을 읽고 사용자 보충 내용까지 합쳐
목표·승인 대상·남은 작업·실패·실행 중 작업을 복원한다. 진입 지침이 요구하는 마일스톤·
다중 프로젝트 문서와 `reports/` 전문 읽기도 따른다. 개인 기억을 정본으로 삼지 않는다.

- HEAD·브랜치·작업 트리와 dirty diff, 관련 Redmine 일감, 프로세스·서비스·로그를 실제 상태와
  대조한다. 오래된 완료 주장만으로 작업을 중복 실행하지 않는다.
- 확인한 상태와 인계 기록의 주장·미조회·미검증을 구분해 보고한다. 조회 실패를 서비스 장애나
  키 부재로 단정하지 않는다. 비밀값을 출력하지 않고 진입 지침의 기존 조회·권한 절차를 따른다.
- 이전 세션이나 에이전트가 여전히 같은 파일을 쓰는지 불명확하면 읽기 조사만 하고 충돌을
  해소한다. 서브 에이전트 실행 ID 이전을 전제하지 않고 담당 파일·산출물·로그로 인수한다.
- 기존 승인과 분산 방식을 범위·근거와 함께 이어받는다. 교대만으로 승인 범위를 넓히거나
  이미 받은 승인을 다시 요구하지 않는다. 미승인 커밋·푸시·⑺ 전진·finalize와
  `awaiting_resume` 재개 조건은 그대로 유지한다. 실패하면 보고하고 중단한다.

## 마스터 담당과 워커 지휘자

**마스터 담당**은 `claude`/`codex`/`antigravity`의 마지막 인수 기록이다. 프로세스 생존 판정·잠금·세션
실행이나 종료 기능이 아니다. **워커 모드**는 `lane`/`claude`/`codex` 전역 선택이며, 대량 생성
레인 `codex → agy → 로컬` 및 보는 일의 모델 체인과 별개다.

실행 전 사용할 스킬 경로와 호출을 알린다. 현재 노출된 `ax-projects` MCP를 우선한다:

    조회       ax-projects:get_orchestration_tool()
    담당 기록  ax-projects:record_master_conductor_tool(agent, why, by)

MCP가 현재 세션에 없으면 기존 정본 함수를 같은 작업 위치에서 호출한다:

```bash
.venv/bin/python master/skills/ax-handoff/scripts/conductor.py snapshot
```

사용자가 마스터 교대를 지시했고 실제 인수를 마친 경우에만 담당 기록을 남긴다. 아래 모드·
사유·기록자는 실제 지시에 맞춘다. 단순 조회나 인수인계 읽기 요청은 기록 변경 승인이 아니다.

```bash
.venv/bin/python master/skills/ax-handoff/scripts/conductor.py record-master codex --why "사용자 지시로 실제 작업 인수 완료" --by codex
```

워커 조회·변경은 [`ax-mode`](../ax-mode/SKILL.md)를 읽고 그 기존 호출을 따른다. 사용자가
명시한 선택이 있으면 준비 검사 후 전환·재조회하며, 선택이 없으면 현재 상태만 확인한다.
토큰 소진이나 마스터 담당 기록만 보고 워커 모드를 자동 선택하지 않는다. 호출 경로가 문서와
다르거나 절차가 불명확하면 사용자에게 먼저 묻고 임시 스크립트·대체 호출을 만들지 않는다.

전역 변경은 새 work 등재의 기본값이다. 기존 `work.worker_mode` 스탬프·진행 조각·라운드에
소급해 덮어쓰지 않는다. 스탬프 없는 옛 work의 전역 참조는 별도로 확인한다. 준비 검사 통과와
실제 원격 실행 성공을 구분해 보고한다.

## 다음 인계

승인된 범위에서 체크포인트를 `docs/orchestrator-handoff.md` 한 벌에 갱신한다. 목표·승인·
HEAD/dirty·검증·미확인·실행 중 작업·다음 작업과 관련 문서/Redmine 링크를 남긴다.
교대를 위해 강제 종료·커밋·푸시·브랜치 삭제를 자동 수행하지 않는다. 비밀값은 기록하지 않는다.
