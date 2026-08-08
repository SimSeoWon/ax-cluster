# client

**윈도우 UE5 PC 2대**에서 도는 코드가 들어갈 자리. **이 클러스터의 작업장이다.**

> 🔴 **작업장은 2대이고, 둘은 같은 UE5 프로젝트를 본다** (2026-08-08 확정).
> 파일을 소유하는 주체가 물리적으로 둘이므로 **`task_queue` 의 claim/lease/fencing 은
> 성능 최적화가 아니라 정확성 요건**이다 — 걷어낼 후보가 아니다(`../PLAN.md` §4.2).

> ⚠️ **이름 주의 — 이 저장소의 3계층**
>
> | 디렉터리 | 머신 | 역할 |
> |---|---|---|
> | [`master/`](../master/README.md) | 192.168.0.57 (리눅스) | **인프라** — RAG · 온톨로지 · 큐 · 추론 브로커 |
> | [`worker/`](../worker/README.md) | BC-250 **#1** (리눅스) | **추론 노드** — 텍스트 in/out만 (#2 는 게임 머신) |
> | **`client/`** | 윈도우 UE5 PC **×2** | **작업장** — 오케스트레이션 + 파일 소유·빌드·코드 등록 |
>
> AgentTest 코드의 `worker/`(윈도우에서 도는 작업자 하네스)가 **여기에 해당하며 그대로 남는다.**
> 이 저장소의 `worker/`(BC-250 추론 노드)와 이름이 겹치지만 다른 것이다 — `../PLAN.md` §4.1.

## 역할 — 여기가 **작업장**이다 (2026-08-07 개정)

1. **오케스트레이터** — 사용자가 앉아서 지시하는 곳. 여기 Claude Code 가 작업을 요청하고
   마스터가 조립해 준 코드 뭉치를 받는다(`../PLAN.md` §2.1).
   **PC 2대 각각이 오케스트레이터이고, 마스터까지 합쳐 총 3곳**이다.
2. **파일을 소유하는 유일한 계층** — 코드 적용, 층1 자기검증, **층3 UE5 빌드 + `RunTests`**,
   통과 시 **코드 등록(커밋)**, 실패 시 **재요청**.
3. **적용 풀(pool)** — 대규모 모듈은 클래스 단위 응답이 병렬로 도착하므로 **순차 적용 큐**가 필요하다.
   마스터의 task_queue 와 **별개 큐**다(`../PLAN.md` §4.5).
4. **Unreal MCP 구동** — 에디터 내장 MCP 는 **loopback 전용**이라 마스터가 붙을 수 없다.
   `ue-editor-operator` 서브에이전트가 여기서 로컬 `127.0.0.1:8000/mcp` 로 몬다(`../PLAN.md` §3).
5. **`gajae-code`(`gjc`) 구동** — 같은 이유로 여기서 돈다. SDK WebSocket 이 loopback 전용이고
   (`ws://127.0.0.1:<port>/?token=`) `--mode rpc/bridge` 는 제거돼 **마스터가 원격 컨트롤러가 될 수 없다**
   (`../PLAN.md` §9.1). 마스터는 대신 **모델 백엔드**로 붙는다.

## 🔴 층3 는 마스터가 원격으로 몰 수 있다 — `.2` 한정 (2026-08-08 실증)

`UnrealEditor-Cmd` 와 `Build.bat` 은 **윈도우 세션 0**(SSH)에서 정상 동작한다.
`-nullrhi` 로 RHI 를 안 띄우면 데스크톱이 없어도 된다.

| 실행 (SSH, 세션 0) | 결과 |
|---|---|
| `Automation List` | 45초, 테스트 8,726개 열거 |
| `Automation RunTests System.Core.Algo` | 25초, 5건 전부 `Result={Success}` |
| `Build.bat ModularStageEditor` (증분) | 1.9초, `Result: Succeeded` |

🔴 **판정은 로그로만 한다.** `ssh` 종료 코드는 **양방향으로 틀린다** —
에디터 성공에 1(거짓 실패), **빌드 실패에 0(거짓 성공)**. `grep error` 도 안 된다:
통과한 실행에도 `LogAutomationTest: Error` 가 나온다. 게이트는 `master/layer3_verify.py`.

❌ **반대로 UE5 GUI 에디터와 Unreal MCP 는 마스터가 띄울 수 없다** — 세션 0 에는 데스크톱이
없다. 그 둘의 주인은 데스크톱 세션의 사람이다(`../docs/5_5-project-isolation.md` §5.5.4-⑥).

`.33` 은 SSH 가 없어 위 전부 해당 없음 — 대화형으로만 쓴다.

## 여기 필요한 선결 설치

| 도구 | 상태 | 왜 |
|---|---|---|
| `node` | ✅ **v24.11.1** (`.2`, 실측 2026-08-08) | `C:\Program Files\nodejs\node.exe`. ⚠️ SSH 세션 PATH 에 없어 `where` 로는 안 보인다 — 절대경로로 확인할 것 |
| `bun` | ⬜ 미설치 (`.2`) | `gjc` 가 Bun 런타임을 요구하면 선결. **마스터가 아니라 여기 필요하다**(2026-08-08 정정) |
| `gjc` | ⬜ 미설치 | 위 4·5번 |
| `extragoal` 스킬 | ⬜ 미설치 | **번들이 아니다** — `gjc extragoal` 명령은 존재하지 않는다. `docs/extragoal-skill-template.md` 의 frontmatter 이하를 `~/.gjc/agent/skills/extragoal/SKILL.md` 로 설치하고 `gjc config set skills.enabled true` + `enablePiUser` 를 켜야 한다 |

⚠️ **모델 배정 주의** — `gjc` 의 역할 매핑(`~/.gjc/agent/models.yml` 의 `model_mapping`)에서
`executor` 를 BC-250 로컬 모델로 두려면 **tool-calling 이 되는 모델이어야 한다.**
`qwen2.5-coder:14b` 는 **구조화된 `tool_calls` 를 못 낸다**(`../worker/README.md`) —
지금 상태로는 로컬 모델을 에이전틱 executor 로 쓸 수 없다(`../PLAN.md` §9.4).

> AgentTest 의 `worker/`(작업자 하네스)는 **여기 그대로 남는다.** 마스터는 인프라지 작업장이 아니다.
> BC-250 이 인계한 것은 팀원 PC 들이 각자 돌리던 **추론 연산**이지 파일 작업이 아니다.

## 여기 남는 것 (AgentTest 에서 이식하지 않고 잔류)

`../PLAN.md` §5.2-B.

| 컴포넌트 | Windows 의존 | 사유 |
|---|---|---|
| **`worker/` 전체** | 14줄 | **작업자 하네스 — 파일을 소유하는 계층** |
| `mcp/master_orchestrator/ue_builder.py` | 19줄 | `UE Build.bat` 실행 |
| `mcp/master_orchestrator/ue_test_runner.py` | 2줄 | `UnrealEditor-Cmd RunTests` |
| `mcp/master_orchestrator/executor_integration_build.py` | 3줄 | 통합 빌드 게이트 |
| `mcp/master_orchestrator/tdd_dryrun.py` | 1줄 | TDD 드라이런 |
| `mcp/commandlet_runner/` | 5줄 | UE 커맨드릿 |

## 마스터와의 경계

| client/ 〈작업장〉 | master/ 〈인프라〉 |
|---|---|
| **파일 소유** · 코드 적용 · 코드 등록 | **파일을 소유하지 않음** |
| 층1 자기검증 · **층3** UE5 빌드·`RunTests` | **층2** 상용 모델 문법검사 |
| 오케스트레이션 ①(사용자 접점) | 컨텍스트 매니페스트 조립 · 잡 분배 · RAG · 추론 브로커 |

- **BC-250 추론 노드를 직접 호출하지 않는다** — 마스터 브로커 경유(`../PLAN.md` §4.2).
  노드 방화벽도 `192.168.0.57` 에서만 11434 를 허용하도록 잠겨 있다.
  오케스트레이터가 셋이어도 **브로커는 하나**다.
- **폴링은 여기 남는다.** 마스터는 Gitea 를 직접 호스팅해 이벤트 구동으로 가지만(`../PLAN.md` §5.4.2),
  이 PC 는 git 서버 입장에서 외부인이라 task_queue 에 폴링(또는 롱폴링)으로 붙는다.
- ⚠️ **능력 기반 라우팅(`requires: ue5`)이 아직 없다** — 빌드 게이트를 인프라에 고정하지 않고
  큐 잡으로 돌리는 CI 러너 패턴(`../PLAN.md` §5.2-C)의 선결 조건. §3 미결 항목.

## ✅ 붙을 준비가 된 것 — task_queue (2026-08-08)

마스터의 `task_queue` 가 **systemd 서비스로 가동 중**이고 LAN 에서 닿는다.

| 항목 | 값 |
|---|---|
| 엔드포인트 | `http://192.168.0.57:8101/api/v1/` |
| 서비스 | `ax-task-queue.service` (enabled, `Restart=always`) |
| 방화벽 | **LAN 한정** — `ufw allow from 192.168.0.0/24 to any port 8101` |
| 헬스체크 | `GET /api/v1/health` |
| 워커 흐름 | `POST /tasks/claim` → `POST /tasks/{id}/heartbeat` → `POST /tasks/{id}/submit` |

🔴 **claim 시 받은 `epoch` 를 submit 에 그대로 실어야 한다.** stale epoch 는 거부된다
(`stale epoch 0 < current 1 (reassigned)`) — 좀비 워커가 남의 작업을 덮어쓰는 것을 막는 장치다.
**작업장이 2대라 이건 실제로 발동한다.**

🔴 **`Authorization: Bearer <token>` 이 필요하다 (2026-08-08부터).** 토큰은 마스터의
`~/.config/ax-cluster/token` 에 있다. `/livez` 만 열려 있다.
⚠️ 방화벽도 그대로다 — 이 엔드포인트를 LAN 밖으로 노출하지 말 것.

## 배포 형태 — 재검토 대상

AgentTest 는 PyInstaller `--onefile` exe 를 `AgentWatch.zip` 으로 배포하고 팀원이
UE5 프로젝트 루트에 압축 해제하는 방식이다(`../PLAN.md` §5.4.1).

**그 배포 의식은 "설치해줄 팀원"이 있어서 존재했다.** 1인 클러스터에선 이 PC 도 내 기계이므로
zip 패키징·`install.bat`·`bump_version.ps1` 은 **축소·폐기 후보**다(`../PLAN.md` §5.2-D).
다만 마스터(§5.4.3, systemd)와 달리 윈도우에서 무엇으로 띄울지는 **아직 정하지 않았다.**

상세 계획: [`../PLAN.md`](../PLAN.md)
