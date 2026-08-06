# client

**윈도우 UE5 PC**(팀원 각자의 작업 머신)에서 도는 코드가 들어갈 자리.

> ⚠️ **이름 주의 — 이 저장소의 3계층**
>
> | 디렉터리 | 머신 | 역할 |
> |---|---|---|
> | [`master/`](../master/README.md) | 192.168.0.57 (리눅스) | 오케스트레이션·RAG·판단·라우팅 |
> | [`worker/`](../worker/README.md) | BC-250 #1·#2 (리눅스) | **추론 노드** — 텍스트 in/out만 |
> | **`client/`** | 윈도우 UE5 PC | **작업자** — 파일 소유·컴파일·테스트 |
>
> AgentTest 코드의 `worker/`(윈도우에서 도는 작업자 하네스)가 **여기에 해당한다.**
> 이 저장소의 `worker/` 와 이름이 겹치지만 다른 것이다. `../PLAN.md` §4.1 참조.

## 역할

**파일을 소유하는 유일한 계층이다.** 실제 파일 I/O·컴파일·테스트가 여기서만 일어난다.

- task_queue 에 잡을 claim → 결과 write → verify (`../PLAN.md` §4.2 루프의 ①⑤⑥)
- UE5 빌드 + `RunTests` — 3층 게이트의 **층3**(`../PLAN.md` §4.3)
- 워커 자기검증 — 동결 인터페이스 위반·펜스/`[PSEUDO]` 잔재 = **층1**
- 상태 추출 후 마스터에 보고
- 피드백은 git `task/<task_id>` 브랜치에 커밋으로 누적

## 여기 남는 것 (AgentTest 에서 이식하지 않고 잔류)

`../PLAN.md` §5.2-B. 전부 **엔진 바운드**라 파일 소유 측에서만 가능하다.

| 컴포넌트 | Windows 의존 | 사유 |
|---|---|---|
| `worker/` 전체 | 14줄 | 작업자 하네스 자체 |
| `mcp/master_orchestrator/ue_builder.py` | 19줄 | `UE Build.bat` 실행 |
| `mcp/master_orchestrator/ue_test_runner.py` | 2줄 | `UnrealEditor-Cmd RunTests` |
| `mcp/master_orchestrator/executor_integration_build.py` | 3줄 | 통합 빌드 게이트 |
| `mcp/master_orchestrator/tdd_dryrun.py` | 1줄 | TDD 드라이런 |
| `mcp/commandlet_runner/` | 5줄 | UE 커맨드릿 |

**통합 빌드 게이트는 인프라에 고정하지 않는다** — task_queue 잡으로 큐잉해
**UE5 를 가진 아무 작업자가 claim** 하는 CI 러너 패턴(`../PLAN.md` §5.2-C).
이래야 마스터가 UE5/Windows 에 묶이지 않는다.

## 마스터와의 경계

| client/ | master/ |
|---|---|
| 파일 I/O · 컴파일 · 테스트 | 파일을 소유하지 않음 |
| 잡 claim · 결과 write | 잡 분배 · 라우팅 · 판단 |
| 층1 자기검증 · 층3 UE5 빌드 | 층2 상용 모델 문법검사 |

- **BC-250 추론 노드를 직접 호출하지 않는다** — 마스터 브로커 경유(`../PLAN.md` §4.2).
  노드 방화벽도 `192.168.0.57` 에서만 11434 를 허용하도록 잠겨 있다.
- **폴링은 여기 남는다.** 마스터는 Gitea 를 직접 호스팅해 이벤트 구동으로 가지만(`../PLAN.md` §5.4.2),
  작업자는 git 서버 입장에서 외부인이라 task_queue 에 폴링(또는 롱폴링)으로 붙는다.

## 배포 형태

AgentTest 의 현행 방식이 그대로 유효한 유일한 계층이다 — PyInstaller `--onefile` exe 를
`AgentWatch.zip` 으로 배포하고 팀원이 **UE5 프로젝트 루트에 압축 해제**한다.
`config.json` 은 PC 별 파일이라 재배포에도 보존된다(PC 마다 VRAM 이 달라 모델을 다르게 두려고).
상세: `../PLAN.md` §5.4.1.

마스터(§5.4.3)와 달리 **여기서는 exe 빌드가 계속 필요하다** — 팀원 PC 에 Python/의존성이 없기 때문.

상세 계획: [`../PLAN.md`](../PLAN.md)
