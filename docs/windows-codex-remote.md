# Windows Codex 원격 실행 — AX 운영 설정

2026-10-03 사용자 지시로 기록. `.2`와 `.33`의 AXCluster 작업에 적용한다.
실증과 버전별 결과는 [리포트 82](../reports/82-axcluster-workers-and-codex-remote.md).

## 실행 계약

Windows에서는 SSH로 `codex exec`를 직접 실행하지 않는다. SSH는 작업 데이터를 보내고
`schtasks /run /tn AxConductor_<project>`로 요청만 한다. Codex는 `/IT /RL LIMITED`로
등록된 작업을 통해 **해당 계정의 로그인 세션**에서 실행한다. 로그인 세션이 없으면 작업이
실행되지 않을 수 있다. `schtasks /run` 성공만으로 실행 성공을 판정하지 않는다.

**“세션 1”은 런처 경로의 이름이며 고정된 Windows SessionId가 아니다.** `.33`에서는
2026-10-03 `USER`의 SessionId **18**에서 실행됐다. RDP 로그인도 대화형 세션이다.
`Win32_ComputerSystem.UserName`이 비어 있다는 이유만으로 로그인 부재를 단정하지 않는다.
계정별 프로세스의 SessionId와 예약 작업의 실행 기록을 함께 확인한다.

런처가 사용하는 핵심 인수:

```text
--sandbox workspace-write
-c windows.sandbox="unelevated"
-c sandbox_workspace_write.network_access=true
```

프로젝트 작업 디렉토리를 명시하고, 부트스트랩은 체크아웃의 `CodexSandboxUsers` 수정 ACL을
설정한다. 플래그만 바꾸면 SSH 직접 실행의 `0xC0000142`가 해결된다고 판단하지 않는다.
마스터는 `job.json`의 task_id·files·approvals·timeout을 보내며 실행 명령은 워커 런처가 만든다.
수동 명령 문자열을 원격 실행 입력으로 추가하지 않는다.

구현 정본:

- [실행 인수](../client/runtime/session1_conductor.py) `build_argv`
- [예약 작업 등록](../client/init/residency.py) `conductor_register_commands`
- [파견·회수](../master/work/runner.py) `uses_session1` · `run_worker_session1`

## 성공 판정과 진단

정상 판정에는 실제 `codex exec`의 셸 읽기와 **apply_patch 파일 수정**, 수정 결과 재독해,
worker rc, `done.flag`·`rc.txt`·출력 회수, 대상 밖 변경 없음이 필요하다.
일반 `cmd.exe` 실행, CLI 버전 출력, task 생성, `check` 통과만으로 파일 수정이 된다고 말하지 않는다.
셸 쓰기로 우회한 성공은 apply_patch 성공과 구분한다.

아티팩트는 `<checkout>/.ax/session1/<task_id>/<request_id>/`에 남는다.
로그인 부재로 남은 진단 요청은 나중에 로그인했을 때 실행될 수 있으므로 해당 요청만 취소하고
진단 파일을 보관·정리한다. 실제 작업의 자동 취소나 광범위한 프로세스 종료로 일반화하지 않는다.

공식 CLI만 설치한다. `.33`은 2026-10-03 공식 npm `@openai/codex@0.159.3`으로 갱신했다.
특정 PC에서 만든 패치 바이너리, 샌드박스 우회, 자동 로그인 설정을 배포 해법으로 넣지 않는다.
버전 일치만으로 결함이 해결됐다고 판단하지 않는다.

2026-10-03 재검증: `.33` 공식 0.159.3 + 기존 `/IT` 런처에서 실제 `apply_patch`가 completed로
종결됐고 `RESULT: DONE`, rc=0, 반환값 일치, 대상 밖 변경 없음, 진단 파일 정리 뒤 clean을 확인했다.
결과 회수 53초. 종전 0.157.1에서는 apply_patch가 실패하고 PowerShell 쓰기로 우회했으므로
이번 결과와 구분한다. 버전 변경 뒤 성공했지만 실패의 근본 원인은 확정하지 않았다.

공식 참고: [Codex CLI 설치](https://learn.chatgpt.com/docs/codex/cli),
[Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox).
위 예약 작업 경로와 SessionId 관측은 AX의 실측이며 공식 문서의 보장으로 인용하지 않는다.

## AXCluster와 `.33`의 범위

AXCluster가 마운트된 동안 `.2`·`.33`·`.43`을 워커로 사용한다(사용자 2026-10-03).
AXCluster 요청자는 마스터 세션이다. `.33` 체크아웃은 `C:\trunk\AXCluster`이며
게임 프로젝트의 requester 역할과 작업 트리는 별개다. 역할은 프로젝트별이며
`dispatch`만으로 requester를 worker로 바꾸지 않는다. 쓰기 전 dirty를 확인한다.

`.33`의 Ollama는 `AX_Ollama33` 예약 작업(S4U·Limited·AtStartup)으로 로그인 없이 구동하도록
설정했고 `gemma4:e4b`를 pull하여 `keep_alive=-1`, context 8192로 상주시켰다.
`AX_READY` 응답과 `/api/ps`를 확인했다. 재부팅 후 동작은 미검증이며 Codex의 `/IT` 작업과
Ollama의 S4U 작업은 서로 다르다.

2026-10-03 사용자 승인으로 브로커를 재시작하여 `.33`을 운영 반영했다. `.43`·`.2`·`.33`
모두 healthy·e4b resident이며 동시 진단3건이 각 노드로 분배·완료된 것을 확인했다.
새 합성 배치는 상주 노드 수로 자동 동시3을 선택한다. 이미 시작한 배치는 시작 시의 동시 수를
유지한다. 소스 변경은 미커밋·미푸시다. 최신 상태는 인수인계서에서 확인한다.
