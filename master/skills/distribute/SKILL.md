---
name: distribute
description: AX 마스터에서 인프라 변경을 RAG로 조사하고 사용자 선택에 따라 로컬 서브 에이전트 또는 AX 워커에 맡긴다. 분산 요청·작업 분해·.57 인프라 정비에 사용한다.
---

# distribute — 마스터의 RAG·위임 입구

정본: `/home/sim/ax-cluster/master/skills/distribute/SKILL.md`.
홈의 Claude/Codex 스킬은 정본을 가리키는 링크로 유지한다.
공용 승인·실패·기록 규칙은 [orchestrator-rules](../../../docs/orchestrator-rules.md),
진행 상태는 [handoff](../../../docs/orchestrator-handoff.md)를 읽는다.

## 등록된 절차 우회 금지 — 사용자 결정 2026-10-04

- 이 스킬의 기존 도구·모듈·명령으로 실행하고, 실행 전에 스킬 경로와 실제 호출 명령을
  사용자에게 밝힌다.
- **절차나 호출 방법이 불명확하면 사용자에게 먼저 묻는다.** 답변 전에는 임시 스크립트
  작성·대체 경로 실행·처리 방식 변경을 하지 않는다.
- 기존 기능을 대신하는 임시 스크립트나 별도 실행 경로를 임의로 만들지 않는다. 기존 절차로
  처리할 수 없다면 실제 확인한 호출·제약과 부족한 기능을 제시하고 사용자 결정을 기다린다.
- 기억 속 파일의 부재를 시스템 기능의 부재로 판단하지 않는다. 사용자가 선택한 분산 방식을
  직접 처리로 바꾸거나, 요청 범위를 기존 분산 실행 코드·파견 계약 정비로 임의 확대하지 않는다.
- 권한 승인을 위한 좁은 스크립트도 기존 호출 방법을 확인한 뒤 승인받아 실행한다.
  권한 문제 규칙을 스킬 대체 경로를 만드는 근거로 사용하지 않는다.

## 요청을 받으면

1. 대상 프로젝트·일감·허용 파일을 확인한다. `.57`의 클러스터 정비도 이 흐름을 따른다.
2. `ax-projects.search_context_tool(query, limit)`로 RAG를 검색한 뒤 실제 소스와 대조한다.
   클래스가 명확하면 온톨로지·관련 이력도 확인한다. RAG의 오래된 산문을 현재 계약으로 믿지 않는다.
   결과의 질문은 사용자에게 전달하며 별칭·프로필을 추측해서 저장하지 않는다.
3. 근거·변경 대상·분해안·검증 방법을 제시하고 **단독(로컬 서브 에이전트) / AX 워커 분산**을
   사용자에게 묻는다. 같은 작업에서 이미 정한 선택은 재사용한다. 작은 변경이라는 이유로
   지휘자가 선택을 대신 정하지 않는다. 읽기·분석은 이 선택을 위한 준비다.
4. 결정한 방식으로 위임한다. 메인 지휘자는 결과 파일·검사·기록까지 책임진다.
   위임 응답의 “완료”만으로 판정하지 않는다.

분산 준비가 부족하면 사유와 선행 정비를 설명하고 사용자의 결정을 따른다.
분산을 당장 실행할 수 있다고 말하거나, 일시적 환경 문제로 선택지를 영구히 지우지 않는다.
`index_only`의 파견 제외는 타입 계약이며 환경 문제와 구분한다.

## 타입과 역할을 먼저 확인한다

`project_profile_tool(name)`의 등록 `kind`와 `blockers`를 읽는다. `.uproject` 유무,
사용자 문장의 “언리얼”, 테스트 설정 유무로 타입을 추정하지 않는다.

| kind | 계약 |
|---|---|
| unreal | 등록된 엔진·버전·소스 경계에 따른 UE 골조·빌드·RunTests |
| code | 프로필 `work_exts`, 트윈 `config.yaml`의 `source`, 테스트 계약을 사용. 현재 분산 허용은 `.py` |
| index_only | 색인·검색 대상. 소스 조각 파견은 제외 |
| 비어 있음 | 프로필 결정이 필요하며 분산 등재 차단을 우회하지 않음 |

AXCluster는 `code`, source roots=`master`,`client`, exts=`.py`, submodules=[]다.
검사 프로필은 `test_start_dir=master`, `test_pattern=test_*.py`지만 **실제 실행기와 테스트의
호환성도 확인**한다. unittest의 0개 실행을 성공으로 보지 않는다. 기존 스크립트 검사 통과를
분산 통합 검사 계약이 실증된 것처럼 보고하지 않는다.
서브모듈을 선언한 다른 code 프로젝트는 부모 Git 상태만으로 내부 소스 더티를 보장할 수 없다.

역할은 프로젝트별이다. 게임 요청자는 `.33`, AXCluster 정비 요청자는 `.57`이다.
AXCluster의 `.2`·`.33`·`.43` 워커는 별도 등록 체크아웃을 사용한다. `.33`의 게임 트리를
인프라 조각의 작업장으로 쓰지 않는다. 워커를 별도 “통합자”로 지정하지 않는다.

## 단독 — 로컬 서브 에이전트

조사·구현·검토 역할을 작업에 맞게 구성한다. 각 에이전트에 대상 파일, RAG 근거,
현재 계약, 검증 방법, 승인 범위를 전달한다. 서로 겹치지 않는 파일은 병렬로 맡길 수 있다.
공유 파일 편집은 순서를 정한다. 프로젝트 밖이나 사용자 트리를 정리하지 않는다.

Codex에서는 실제 제공된 `spawn_agent`/메시지 도구를 사용한다. Claude의 Agent 도구나
프로젝트 에이전트 파일을 Codex의 실행 가능한 내장 타입으로 가정하지 않는다.
Claude에서는 제공된 위임 도구와 실제 등록 에이전트 역할을 사용한다.
작성 레인과 워커 지휘자 모드는 별개다. 모드 조회·변경 자체는 `ax-mode` 스킬을 따른다.
사용자가 선택한 모델·방식을 임의로 바꾸지 않는다.

## 분산 — 준비 검사

쓰기 전에 현재 마운트·등록 프로필·역할을 확인한다. 준비 조회가 새 작업 등재를 뜻하지 않는다.

- 마스터 작업 위치 `/home/sim/ax-cluster`, Python `.venv/bin/python`.
- 현재 세션에 `ax-projects` 도구가 실제 노출돼 있는지 확인한다. 설정 파일만으로 판단하지 않는다.
- `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client plan <프로젝트>`로
  배달 계획을 확인한다. `check <프로젝트>`의 버전·payload·프로젝트 로컬 스킬·MCP 상태를 읽는다.
- 배달은 커밋된 깨끗한 트리에서 한다. 동기화 지시가 있으면
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`(마운트된 프로젝트)를,
  등록 전체가 필요하면 `update --all`을 쓴다.
- `check_workshops_clean_tool(name)`의 `dispatchable`과 사유를 확인한다. 소스 더티·SSH 실패를
  무시하지 않는다. `git clean`, 강제 reset/push로 준비 상태를 만들지 않는다.
- 큐·프로젝트 서비스와 `ax-dispatch.path`·`ax-dispatch.timer`를 확인한다.
  실제 따라잡기 타이머 이름은 `ax-dispatch.timer`이며 `ax-dispatch-catchup.service`를 깨운다.
  서비스 기동 시각보다 코드 수정이 늦으면 운영 반영을 별도로 확인한다.
- 선택된 워커 지휘자의 실제 실행·결과 회수 경로를 확인한다. Windows Codex는 로그인 사용자
  세션의 `/IT /RL LIMITED` 런처를 사용한다. 상세는
  [Windows Codex 원격 실행](../../../docs/windows-codex-remote.md).
  SSH 실행/예약 작업 요청 성공만으로 셸·apply_patch·회수 성공을 대신하지 않는다.

실패 시 공용 규칙대로 사유와 갈래를 보고하고 멈춘다. 서비스 재기동·배달·파견은 기존
사용자 승인 범위를 확인한다. 단순 도구 설정이나 직접 쓰기 프로브를 전체 분산 완주로 보지 않는다.

## 분산 — 정본 7단계

| 단계 | 실행 주체와 결과 |
|---|---|
| ① 요청·분해 | 요청자가 RAG와 실제 소스를 바탕으로 클래스/파일·계약·의존 관계를 정리 |
| ② 골조 | 요청자가 `task/<work_id>/base`의 실물 골조와 동결 선언을 준비 |
| ③ 등재·골조 확인 | 마스터 등재는 큐와 명세 등록. 타입별 골조 게이트를 확인 |
| ④ 조각 브랜치 | 골조 기준에서 조각별 서브 브랜치를 생성 |
| ⑤ 병렬 구현 | 워커가 자기 조각 브랜치에서 구현·결정적 검사·커밋·push, 이후 main 복귀 |
| ⑥ 회수·고지 | 마스터가 현재 라운드의 모든 조각 상태와 실패·완료를 요청자에게 전달 |
| ⑦ 통합·전진 | 요청자가 별도 worktree에서 조각을 모두 머지해 타입별 통합 검사를 한 번 수행. 사람 승인 뒤 base 전진 |

병렬이 기본이다(`autodispatch`는 `parallel=True`). 직렬은 사용자가 선택했을 때만 적용한다.
같은 물결의 파일이 겹치면 분해를 조정하고, 의존이 있는 조각의 순서를 보존한다.
워커는 본문 텍스트만 반환하는 방식이 아니라 자기 브랜치에 구현을 남긴다.

등재와 골조 기준 준비의 실제 호출 순서는 현재 API를 읽는다. 초기 골조 전 등재를 사용하는
경로도 있으므로, `work_id`를 만들기 위해 임의 값을 쓰거나 오래된 CLI의 자동 골조 생성을
정본으로 사용하지 않는다. **골조 기준의 원격 존재와 게이트 통과를 확인하기 전 파견하지 않는다.**

### 실제 호출 표면

- 마스터 현재 MCP: `register_work_tool(title, target_repo, specs_json, original_request,
  target_branch, project)`. `specs_json`은 `TaskSpec` 배열이며 target/header 파일, 골조,
  동결 계약, 의존 관계, 필요한 능력을 명시한다. code에 `requires=["ue5"]`를 붙이지 않는다.
- 등재 서비스는 Git 브랜치 생성·골조 커밋을 하지 않는다. 요청자 역할이 수행한다.
- 최초 등재와 개선 요청을 구분한다. 개선은 `master.work.register.improve_work`의
  `work_id`, `round=현재+1`, specs와 현재 base를 사용한다. 현재 MCP에 개선 도구가 없다면
  있다고 가정하지 말고 실제 모듈 호출 계약·큐 인증을 확인한다.
- 마스터 Python 구현은 `master.work.register`, `master.work.review`에 있다.
  요청자 배달본은 `.ax/lib`의 `axmaster`와 실제 `ax-client` 도구를 사용한다.
- 라운드 통합은 `review.fetch_work`로 work/tasks를 확인하고 `review.advance_work(...,
  build_fn=타입별 검사, confirm=False)`로 준비한다. 실제 결과의 질문을 사용자에게 전달한다.
  승인 후 `confirm=True`, `decision_note=사용자 판단`으로 base를 전진시킨다.
- 작업 전체 마감은 `review.review_work`로 별도 검수 후 `review.finalize_work`다.
  기본 `confirm=False`, 별도 finalize 승인 뒤 main 반영과 종결 결과를 확인한다.
  요청자에는 큐 토큰을 두지 않으므로 실제 `queue_api()`를 `api=`로 주입한다.

### 완료 이후 — 공통 핵심을 부른다 (`#798`)

⑥ 이후는 지휘자(Claude/Codex)와 무관하게 `master.work.followup` 한 곳이 집행한다.
수신자는 **타이머 하나**다 — 마스터에서는 훅을 쓰지 않는다(사용자 결정 2026-10-11):

    ax-followup.timer (1분) → `followup --scan --project AXCluster --repo /home/sim/ax-cluster`

하는 일은 큐 재조회 → 정본 옆 격리 worktree 에서 `advance_work(confirm=False, keep_tree=True)` →
공식 통합 검사 + 바뀐 파일 회귀 → 사람 게이트에서 멈춤 → 라운드당 Redmine 노트 한 번이다.
push·전진·`main` 은 없다. 기록: `~/.cache/ax-followup/followup.jsonl` · journal.

세션도 등재 뒤 큐를 **카운트다운 주기 조회**(`get_work`)로 따라가 완료를 직접 확인한다.
종결을 봤는데 준비 기록이 없으면 같은 핵심을 직접 부른다:

    AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.work.followup <work_id> \
        --repo /home/sim/ax-cluster --python /home/sim/ax-cluster/.venv/bin/python

`at_gate` 결과의 질문(「버그냐 구조냐」)을 사용자에게 전하고 거기서 멈춘다. `stopped`·`error`는
사유를 보고한다. 「완료 상태를 확인했다」로 턴을 끝내지 않는다 — 그 멈춤이 `#798` 이다.

골조·코드 커밋/푸시는 매번 별도 승인이다. ⑦ 전진과 finalize도 서로 다른 승인이다.
작업 시작 또는 분산 선택을 이 승인들 전체로 확대하지 않는다.
워커 조각 커밋은 승인된 파견의 계약으로 수행하며 요청자 main 반영 승인과 혼동하지 않는다.

## 검증과 기록

회수한 브랜치·커밋·실제 파일·검사 출력을 대조한다. 부분 성공은 분모와 남은 실패를 적는다.
요청자는 같은 파일을 다시 단독 구현해 실패한 파견을 성공으로 덮지 않는다.
분산 완주는 큐·골조·조각 구현·회수·통합·사람 게이트의 실증 범위를 구분해 보고한다.

진행 정본은 Redmine, 근거는 `reports/`, 다음 세션 상태는 handoff다.
단독 작업도 결정 근거·변경·검사·미커밋 여부를 기록한다. 배달 버전과 실행 서비스가 확인되지
않았으면 “분산 준비 완료”라고 쓰지 않는다.
