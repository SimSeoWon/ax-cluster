> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

## 5. 마스터 오케스트레이션 언어 — Python 확정 (2026-08-06)

**결론: Python.** 신규 선택이 아니라 *기존 자산을 이식*하는 문제였다. 근거는 AgentTest 코드베이스 실측.

### 5.1 근거

**① 이미 67,038줄이 동작 중이다** (199개 `.py`, plan v5.0 기준 533 테스트 통과)

| 영역 | 줄 수 |
|---|---|
| `mcp/` (task_queue · context_search · master_orchestrator) | 26,424 |
| `watcher/` (RAG · 온톨로지 · 클래스 그래프) | 21,171 |
| `tests/` | 14,246 |
| `worker/` | 3,657 |

**② Windows 의존이 92줄뿐이다 (0.14%)** — `win32`/`ctypes.windll`/`winreg`/`STARTUPINFO`/`.bat` 기준.

> ⚠️ **이 수치는 과대평가다 (2026-08-07 실측 정정).** grep 이 **주석·문자열까지 세고 있다.**
> `mcp/context_search/` 의 6건을 실제로 열어보니 3건은 "install.bat 을 다시 실행하세요" 안내 **문자열**,
> 2건은 **주석**, 1건은 docstring 의 `C:\temp\...` **예시 경로**였고 **진짜 코드는 1줄**
> (`llm_chat.py:196` — `agy_path.endswith(('.cmd','.bat'))`)뿐이다.
> **실질 이식 장벽은 이 숫자보다 훨씬 작다.** 판정 기준으로는 `sys.platform`/`os.name` 분기가 더 정확하며,
> 그 기준으로는 `context_search` 0건 · `task_queue` 2건(둘 다 리눅스 분기 존재) · `watcher/` 3건이다(§5.4.7).
게다가 가장 밀집한 곳이 **어차피 Windows 에 남아야 할 컴포넌트**다:
`ue_builder.py`(19) · `commandlet_runner`(5) · `ue_test_runner.py`(2).
**리눅스로 옮길 컴포넌트의 Windows 의존은 약 30줄.** 이식이지 재작성이 아니다.

**③ ChromaDB 는 Python 네이티브다.** Go 로 가면 벡터 DB 교체(Qdrant 등) + 임베딩 파이프라인
(ONNX `all-MiniLM-L6-v2`) 재구축까지 딸려온다. 언어 교체가 아니라 스택 교체가 된다.

**④ Go 의 강점이 이 워크로드에 안 맞는다**

| Go 장점 | 이 프로젝트 |
|---|---|
| 단일 바이너리 | 이미 PyInstaller 로 `.exe` 빌드 중(`build.bat`) |
| 동시성 | I/O 바운드(Ollama HTTP · git). asyncio 로 충분 |
| 실행 성능 | 병목은 **LLM 추론(초 단위)** — 오케스트레이션(ms)은 노이즈. 실측 14B 22 t/s |

### 5.2 이식 대상 — 컴포넌트 배치

2026-07-07 아키텍처 합의("RAG/온톨로지/그래프는 엔진과 무관한 순수 데이터 작업이므로 인프라에 둔다")를 구체화.

**A. 리눅스 마스터(57)로 이전** — 순수 데이터/판단 계층, UE5 무관

| 컴포넌트 | 규모 | Windows 의존 | 비고 |
|---|---|---|---|
| `watcher/` 전체 | 21,171줄 | 19줄 | git watch · RAG · 온톨로지 · 클래스 그래프. 정리 대상: `review.py`(5) · `network_firewall.py`(4) · `skill_defs_distribute.py`(4) · `process_lifecycle.py`(3) · `watch.py`/`common.py`/`agent_defs.py`(각 1). **⚠️ `process_lifecycle.py` 는 이식이 아니라 폐기 — §5.4** |
| `mcp/context_search/` | — | 6줄 | ChromaDB + BM25. `remote_client.py`(3) · `wiki_local_tools.py`/`search_tools.py`/`llm_chat.py`(각 1) |
| `mcp/task_queue/` | — | 5줄 | 작업 분배·claim·fencing. `logic_cleanup.py`(3) · `reclaim.py`/`persistence.py`(각 1) |
| `mcp/master_orchestrator/` 中 오케스트레이션 부분 | — | — | 골조 생성·분배·라우팅. **UE 빌드/테스트 부분은 제외**(아래 B) |
| **`mcp/agy_query/`** | 194줄 | — | 🔴 **§5.2 목록에 빠져 있던 것 추가** — Antigravity CLI(`agy`) 위임. 마스터가 오케스트레이션하려면 필수(층2 검증). **⚠️ 마스터에 `agy` 미설치** |
| **`mcp/local_llm_runner/`** | 144줄 | — | 🔴 **누락분 추가** — Ollama 위임. **§6.4 추론 래퍼와 역할이 겹치므로 재사용/대체를 먼저 정할 것**(§3 미결) |

**B. Windows 잔류** — 엔진 바운드, **다른 곳에서 할 수 없는 것만**

| 컴포넌트 | Windows 의존 | 사유 |
|---|---|---|
| `mcp/master_orchestrator/ue_builder.py` | 19줄 | `UE Build.bat` 실행 |
| `mcp/master_orchestrator/ue_test_runner.py` | 2줄 | `UnrealEditor-Cmd RunTests` |
| `mcp/master_orchestrator/executor_integration_build.py` | 3줄 | 통합 빌드 게이트 |
| `mcp/master_orchestrator/tdd_dryrun.py` | 1줄 | TDD 드라이런 |
| `mcp/commandlet_runner/` | 5줄 | UE 커맨드릿 |

| `worker/` 전체 | 14줄 | **작업자 하네스 — 파일을 소유하는 계층**(§2.1) |

> **⚠️ 2026-08-07 정정** — 한때 `worker/` 를 A(마스터 이전)로 옮겼으나 **되돌렸다.**
> 마스터는 인프라지 작업장이 아니다. BC-250 이 인계한 것은 **추론 연산**이지 파일 작업이 아니다.

**C. 빌드 러너는 고정하지 않는다** — 2026-07-07 합의대로 "1차 통합 빌드게이트"를 인프라에 박지 않고
**task_queue 잡으로 큐잉해 UE5 를 가진 기계가 claim 하는 CI 러너 패턴**으로 분리한다.
이래야 마스터가 UE5/Windows 에 묶이지 않는다.
**선결이던 능력 기반 라우팅**(`requires: ue5`)은 **2026-08-08 구현·실측 완료**다.
`master/task_queue` 가 task 의 `requires` 와 워커가 claim 시 신고한 `capabilities` 를
**부분집합 매칭(fail-closed)** 한다 — 능력을 신고하지 않은 워커는 `requires` 붙은 잡을 못 집는다.

| 계약 | 값 |
|---|---|
| task 쪽 | `POST /api/v1/tasks` 의 `requires: ["ue5"]` (빈값 = 아무나) |
| 워커 쪽 | `POST /api/v1/tasks/claim` 의 `capabilities: ["ue5"]` (**미신고 = 능력 없음**) |
| 허용 태그 | `ue5`(에디터+빌드 툴체인) · `windows`. **화이트리스트 밖은 등록 시점에 400** |
| 적용 범위 | write 잡 + **verify 잡 양쪽.** 검증자도 diff 를 쥐려면 파일 소유 기계여야 한다(§2.1) |
| 관측 | `GET /api/v1/admin/workers` 의 `capabilities` + 로그 `능력 미달로 N건 skip` |

**미지 태그를 등록 시점에 거부하는 이유**: claim 쪽이 fail-closed 라 오타 하나(`ue-5`)면
**아무 워커도 만족시킬 수 없는 task** 가 조용히 pending 에 굶는다. 조용한 기아보다 등록 실패가 낫다.
테스트 `master/test_capability_routing.py` (16건).

**D. 🔴 팀 때문에 존재하는 것 — 이식이 아니라 축소·폐기 후보 (2026-08-07 신설)**

§2.0 의 전제에 따라 **"이 컴포넌트가 팀 때문에 존재하나?"** 로 걸러낸다. 1인 클러스터에선 의미가 없거나
크게 단순해진다. **착수 전 개별 판단할 것 — 일괄 폐기하지 말 것.**

| 후보 | 팀 전용인 이유 |
|---|---|
| 작성자별 분리 (`reviews/<작성자>/` · `plans/<작성자>/`) | 작성자가 하나뿐 |
| 리더 검수 `/review-work` | 리더와 작업자가 동일인 |
| 비개발자 위키 클라이언트 (`AgentWiki`, `packaging/wiki_client/`, `build_wiki_client.bat`) | 기획팀 대상 — 범위 밖 |
| Redmine 연동 (`mcp/redmine_tracker/`, `planner_redmine.py`) | 팀 이슈 트래킹 |
| zip 패키징 · `install.bat` · `bump_version.ps1` | 설치해줄 팀원이 없음(마스터는 §5.4.3 대로 systemd) |
| PC 별 `config.json` 보존 로직 | PC 마다 VRAM 이 다른 팀 상황 전제 |

**⚠️ 반대로 걷어내면 안 되는 것**: claim/lease/fencing·reclaim. 1인이지만 **오케스트레이터가 셋이고
파일을 소유한 작업장이 2대**라
공유 자원 경쟁이 실재한다(§2.2-5).

### 5.3 이식 순서 (제안)

1. `mcp/task_queue/` — 루프의 중추이고 Windows 의존 5줄로 가장 가볍다. 먼저 옮겨 마스터에서 기동.
   **선결: 수명주기 주인 교체** — 현재 `watch.py` 가 자식 프로세스로 띄우고 감시한다(§5.4.3).
   떼어내 독립 서비스로 만드는 것이 이 단계의 실제 작업량이다.
2. `mcp/context_search/` — ChromaDB 인덱스 이관(재색인 필요 여부 확인).
3. `watcher/` — 가장 크지만 순수 데이터라 기계적. 단 **`watch.py` 의 폴링 루프는 그대로 옮기지 않는다**
   — Gitea 이벤트 구동으로 대체(§5.4.2). `process_lifecycle.py`·`network_firewall.py` 는 **폐기**(§5.4.3).
4. **`mcp/agy_query/` 이전** — 층2 검증용(**`agy` 설치 완료 — 리포트 04**). 리눅스에선 PTY 코드 불필요.
5. `master_orchestrator/` 분할 — 오케스트레이션 부분만 이전, UE 부분은 §5.2-B 로 남기고
   §5.2-C 의 큐 잡 패턴으로 연결.

**이식 시 함께 처리할 설정 변경**
- `local_llm_model` 기본값을 `gemma4:e4b` → **`qwen2.5-coder:14b`** 로 변경 (§4.4 참조).
  config 로 덮어쓰는 것만으로도 동작하지만, 기본값 자체를 바꿔야 설정 누락 시 조용한 Gemma 폴백을 막는다.
- 추론 엔드포인트 기본값 `http://localhost:11434` → BC-250 노드 주소로. 마스터에는 Ollama 가 없다.

**마스터 선결 설치 (2026-08-07 실측)**

| 도구 | 상태 | 필요한 이유 |
|---|---|---|
| `claude` | ✅ 있음 (`~/.local/bin/claude`, v2.1.223) | 층2 검증 폴백 · 마스터 오케스트레이션 |
| `agy` (Antigravity CLI) | ✅ **설치·인증·검증 완료 2026-08-07** (`~/.local/bin/agy`, **v1.1.10**) | 층2 검증 1순위(`syntax_check` 가 agy 우선) · `mcp/agy_query/` |
| `bun` / `node` | ❌ **없음** | gajae-code 가 TypeScript/Bun (§1) |

**🔴 `agy` 이식 부담이 크게 줄었다 — AgentTest 의 윈도우 대응책이 리눅스에선 불필요하다.**
`history/2026-06-28_1619_gemini_to_agy_migration.md` 가 기록한 함정 4종이 v1.1.10 에서 **전부 해소**됐다
(마스터 리포트 04 실측):

| AgentTest 기록 (2026-06-28, 윈도우) | 2026-08-07 리눅스 실측 |
|---|---|
| `agy -p` 가 비-TTY 면 0바이트 + 20s hang → **가상 PTY(pywinpty) 전환** | ✅ 순수 파이프로 정상 |
| 출력에 터미널 init ANSI 섞임 → **정규식 strip** | ✅ 깨끗한 텍스트 |
| **argv 순서 버그**(`-p` 를 맨 끝에, 6곳 정정) | ✅ 순서 무관 |
| `agy models` 스피너 TUI 미종료 | ✅ 즉시 반환 |

**→ `_agy_pty_call` 헬퍼(5개 호출부 중복) · `--collect-all winpty` 번들 · ANSI strip · argv 정정이
리눅스 이식 대상에서 빠진다.** `pywinpty` 는 윈도우 전용이라 어차피 등가물로 바꿔야 했는데 그 작업 자체가 사라졌다.
⚠️ 윈도우(`client/`)에도 적용되는지는 **미확인** — 별도 실측 필요.

**💡 신규 `--output-format json`** (AgentTest 시점엔 없던 옵션) — `status` · `response` ·
`usage{input/output/thinking/cache_read/total_tokens}` 를 구조화해 반환한다.
모토상 **상용 토큰 계측이 곧 비용 관리**인데 별도 계측 코드 없이 얻고,
`**TASK_COMPLETE**` 센티넬 파싱보다 견고하다. `stream-json` 도 있다.

**⚠️ agy 자율 에이전트에 저장소 작업을 위임하지 말 것** — AgentTest 가 사고를 기록했다
(agy 자율 에이전트가 동의 없이 `watcher/common.py` 수정). `--dangerously-skip-permissions` 를 쓰므로
작업 디렉터리를 가진 채 자율 실행시키면 파일을 건드린다. **층2 용도(텍스트 in/out)로만 쓸 것.**

**주의:** 위 줄 수/의존 집계는 2026-08-02 클론 기준이다.
→ **2026-08-07 마스터에서 재확인 완료**: 199개 `.py` / 67,038줄 / Windows 의존 **93줄**. 수치 유효.
마스터 클론 위치는 `/home/sim/AgentTest`(**참조용 — 수정하지 않는다**), 이 저장소는 `/home/sim/ax-cluster`.

### 5.4 마스터 실행 모델 — 폴링 데몬이 아니다 (2026-08-07)

AgentTest 를 그대로 옮기면 안 되는 이유가 여기 있다. **배포 형태와 실행 모델이 마스터에서는 성립하지 않는다.**

#### 5.4.1 AgentTest 의 현재 형태 (실측)

`build.bat` 이 PyInstaller `--onefile` 로 **exe 12종**을 빌드해 `AgentWatch.zip` 으로 배포하고,
팀원이 **UE5 프로젝트 루트에 압축 해제**한다. `watch.exe`(데몬) · `worker.exe` · MCP 서버 10종
(`context_search` `log_analyzer` `crash_analyzer` `commandlet_runner` `agy_query` `redmine_tracker`
`code_recipes` `task_queue` `master_orchestrator` `local_llm_runner`).

`watcher/watch.py main()` 이 `while True` 로 `poll_interval` 초마다 git fetch/pull → 새 커밋 감지 →
처리. MCP 서버와 task_queue 는 **자식 프로세스로 띄우고 `.poll()` 로 생존 감시**한다
(`common._server_proc`, `common._task_queue_proc`). `config.json` 은 PC 별 파일이라 재배포에도 보존된다.

**마스터에는 UE5 프로젝트 루트도 팀원별 사본도 없다.** 배포 단위(zip+exe)와 수명주기 관리를
그대로 옮길 수 없다.

#### 5.4.2 폴링 → 이벤트 구동 (Gitea 가 같은 박스에 있다)

`watch.exe` 가 폴링하는 건 **팀원 PC 가 git 서버 입장에서 외부인이라 알림받을 방법이 없기 때문**이다.
마스터는 반대로 **Gitea 를 직접 호스팅**한다(`gitea.service`, :3000). 알림을 받을 수 있다.

| | 폴링 (AgentTest) | 이벤트 (마스터) |
|---|---|---|
| 감지 지연 | `poll_interval` 초 | 즉시 |
| 유휴 시 비용 | 계속 fetch | 0 |
| 튜닝 | 간격 결정 필요 | 불필요 |

- **Gitea 웹훅** — push 시 지정 URL 로 HTTP POST. 같은 박스라 `localhost` 로 쏘면 네트워크 신뢰성 문제 없음.
- **`post-receive` 훅** — push 순간 서버에서 스크립트 직접 실행. 네트워크조차 안 탄다.
  ⚠️ 단 **훅 안에서 무거운 작업(RAG 색인 등)을 하면 그동안 push 가 멈춘다.** 훅은 알림만 던지고 즉시 종료할 것.

#### 5.4.2-a 🔴 훅 설치 지점 — `post-receive.d/` 다 (실측 2026-08-08)

`hooks/post-receive` 는 **Gitea 가 자동 생성하며 첫 줄이 `# AUTO GENERATED BY GITEA,
DO NOT MODIFY` 다.** 덮어쓰면 Gitea 내부 동작이 깨진다. 실제 내용은 디스패처다:

```bash
data=$(cat)                                   # stdin(refs)을 한 번 읽고
for hook in ${GIT_DIR}/hooks/${hookname}.d/*; do
  test -x "${hook}" && test -f "${hook}" || continue
  echo "${data}" | "${hook}"                  # 각 훅에 순차로 먹인다 (동기)
  exitcodes="${exitcodes} $?"
done
for i in ${exitcodes}; do [ ${i} -eq 0 ] || exit ${i}; done   # 하나라도 실패면 push 실패
```

→ **우리 훅은 `hooks/post-receive.d/ax-event` 로 설치한다.** (현재 그 디렉토리엔
Gitea 자신의 `gitea` 훅 1개만 있다.) 여기서 두 가지가 강제된다:

1. **디스패처가 훅을 동기로 기다린다.** §5.4.2 의 "즉시 종료" 요구가 관례가 아니라
   **기계적 사실**로 확인됐다. HTTP 호출조차 하지 말 것 — 큐가 느리면 push 가 그만큼 멈춘다.
2. 🔴 **훅이 0 이 아닌 값을 반환하면 push 자체가 거부된다.** 즉 이벤트 큐가 죽어 있을 때
   훅이 실패하면 **개발자가 push 를 못 한다.** 작업장을 막는 것은 어떤 경우에도 안 된다.

→ **훅은 로컬 스풀 파일에 append 하고 항상 `exit 0` 한다.** 네트워크도 서비스 의존도 없다
(파일 append 는 실패할 여지가 사실상 없다). 소비자가 그 스풀을 읽어 처리한다.
이렇게 하면 **push 를 막지 않으면서 이벤트도 잃지 않는다** — §5.4.5 가 요구한 영속성이
바로 이 스풀이다. 다른 곳의 fail-closed 원칙(§9.4.4)과 방향이 반대인데, **여기서 막히는
대상이 사람의 push 이기 때문**이다. 의도된 예외다.

**⚠️ 데몬이 없어지는 게 아니다.** 사라지는 건 폴링 루프뿐이고 상주 프로세스는 여전히 필요하다:
① 웹훅을 받을 쪽이 떠 있어야 하고 ② `task_queue` 는 작업자가 claim 하러 붙는 **HTTP 서버**라
태생이 상주 서비스이며 ③ RAG 인덱스·추론 브로커도 계속 살아 있어야 한다.

**작업자(윈도우) 쪽은 그대로다** — `worker.exe` 는 여전히 외부인이라 task_queue 에 폴링으로 붙는다.
폴링이 없어지는 것은 마스터 한정.

#### 5.4.3 수명주기는 systemd 가 가져간다 — `process_lifecycle.py` 는 폐기

리눅스의 데몬 = **systemd 서비스**. 이 박스의 `gitea.service` 가 정확히 그 형태다.
**PyInstaller 빌드는 불필요** — exe 로 묶는 건 "팀원 PC 에 Python/의존성이 없어서"인데
마스터는 통제 가능한 한 대뿐이라 venv 로 충분하다.

```ini
# /etc/systemd/system/ax-task-queue.service (예시)
[Service]
ExecStart=/home/sim/ax-cluster/.venv/bin/python -m master.task_queue
Restart=always
User=sim
[Install]
WantedBy=multi-user.target
```

| `watch.py` 가 손수 하던 것 | systemd |
|---|---|
| 자식 프로세스 `.poll()` 생존 감시 | `Restart=always` |
| Job Object 로 고아 프로세스 정리 (**Windows 전용**) | cgroup 자동 |
| 로그 파일 관리 | journald (`journalctl -u`) |
| 기동 순서 조율 | `After=` / `Requires=` |
| 포트 점유 해제·방화벽 규칙 (`network_firewall.py`, **Windows 전용**) | firewalld/ufw 로 별도 관리 |

**→ `process_lifecycle.py`·`network_firewall.py` 는 리눅스 등가물로 고쳐 쓸 게 아니라 폐기하고
systemd 에 넘긴다.** 각 컴포넌트를 독립 유닛으로 두면 §5.3-1 의 "task_queue 수명주기 주인" 문제도 사라진다.

#### 5.4.4 ✅ 확정 — **systemd + venv** (2026-08-08)

`~/CLAUDE.md`(마스터) 규약은 "새 서비스는 Docker Compose 선호"다(n8n·Redmine 이 그 패턴).
**그럼에도 systemd 로 간다** — 코드 실측 결과 이 워크로드는 호스트에 깊이 결합돼 있다:

| 결합 | 근거 (실측 2026-08-08) |
|---|---|
| **호스트 CLI + 홈 디렉터리 인증** | 층2 검증이 `agy`·`claude` 를 subprocess 호출 — `mcp/agy_query/server.py:70`, `mcp/context_search/llm_chat.py:71`. 바이너리는 `~/.local/bin`, 인증 상태는 홈 디렉터리 |
| **git + SSH 키** | `task_queue` 가 **매 상태 전이마다** `git add`/`commit`(감사 로그) — `mcp/task_queue/persistence.py:299~340`. `watcher/git_ops.py` subprocess `git` 8건 |
| **Gitea 가 호스트 systemd 서비스** | §5.4.2 `post-receive` 훅이 호스트에서 실행. 컨테이너면 훅→컨테이너 전달 경로를 별도 구축(브리지 IP 하드코딩) |
| **BC-250 LAN** | 보드 firewalld 가 **192.168.0.57 만** 11434 허용 — 컨테이너 NAT 출발지를 별도 검토해야 함 |
| **미래 CUDA** (§7) | nvidia-container-toolkit 한 겹 추가. 드라이버조차 미설치 |

**Compose 의 이점(의존성 격리·재현성)이 여기선 약하다** — 의존성이
`mcp chromadb fastapi uvicorn tree-sitter tree-sitter-cpp`(`build.bat:29` 기준, `pywinpty` 제외)
**전부 순수 pip 패키지**라 venv 로 동일하게 얻는다. `requirements.txt` 는 없어 이식 시 새로 만든다.

**규약과 어긋나지 않는다** — n8n·Redmine 은 업스트림 이미지를 그대로 쓰는 **완제품 외부 서비스**이고,
우리 코드는 호스트 자원(git·CLI 인증·Gitea 훅·LAN·홈)에 붙는 **자체 코드**다.
되돌리기 어려운 결정도 아니다(유닛을 나중에 컨테이너화 가능). 상세 = 마스터 리포트 06 §1.

#### 5.4.5 🔴 폴링이 공짜로 주던 3가지 — 웹훅으로 가면 직접 만들어야 한다

**기존 코드가 폴링 루프 자체를 안전장치로 쓰고 있다.** 그대로 이식하면 이벤트가 조용히 유실된다.

```python
# watcher/watch.py:646
if not _processing_lock.acquire(blocking=False):
    # 이전 사이클이 아직 처리 중 → 이번 틱은 건너뜀
```

폴링에서 **건너뛰는 건 안전하다** — 60초 뒤 다음 틱이 어차피 다시 본다.
웹훅에서 건너뛰면 **그 이벤트는 영영 사라진다.** 아무도 다시 알려주지 않는다.

| 성질 | 폴링에서 | 웹훅에서 | 대책 |
|---|---|---|---|
| **직렬화** | `_processing_lock` 으로 한 번에 한 사이클 | 동시 도착 시 겹침 | 단일 소비자 |
| **재시도** | 놓친 틱은 다음 틱이 처리 | 놓치면 유실 | **영속 큐** |
| **합치기** | 60초 안의 push 10개 = 재색인 1회 | push 10개 = 재색인 10회 | 중복 합치기(coalescing) |

세 번째가 특히 아프다 — 커밋을 연달아 밀면 무거운 RAG 재색인이 그 횟수만큼 돈다.

**→ 웹훅 전환의 전제조건은 영속 큐 + 단일 소비자다. 선택이 아니다.**
`post-receive` 훅은 큐에 넣고 즉시 종료한다(§5.4.2 의 "push 를 막지 말 것"과 같은 요구).

> **⚠️ 오케스트레이터가 셋이라 더 중요해졌다 (2026-08-08 갱신, 이전엔 "둘"로 적었다).**
> 윈도우 UE5 PC **2대**의 Claude Code 와 마스터가 **동시에** git·task_queue·RAG 를 건드리고,
> **두 작업장은 같은 UE5 프로젝트를 본다**(§4.2). 폴링 시절의 "이번 틱 건너뜀"이 안전했던 이유
> (다음 틱이 처리)가 사라지는 데다, 이제는 **세 주체가 경쟁**한다. 1인 프로젝트라고
> claim/fencing 을 걷어내면 안 되는 이유이기도 하다(§2.2-5 · §5.2-D).
> 실제로 도는 것을 확인했다 — 이중 claim 차단·stale epoch 거부(§9.5.3).

**⚠️ `task_queue` 와 합치지 말 것** — 성격이 다르다.

| | `task_queue` (기존) | 이벤트 큐 (신규) |
|---|---|---|
| 소비자 | 다수 (윈도우 작업자들) | **정확히 하나** (마스터 내부) |
| 필요한 것 | claim · lease · fencing · reclaim | 순서 보장 · 중복 합치기 |
| 현재 상태 | `idx.lock`(RLock)으로 촘촘히 보호됨 | 없음 |

`task_queue` 의 claim/lease 는 "외부 소비자 여럿이 경쟁한다"는 전제로 만든 물건이라
로컬 단일 소비자에는 과하다.

**원형으로 쓸 것이 이미 있다** — `.claude/_regenerate_queue.jsonl`.
`skill_defs_ontology.py:97` 이 "실제 LLM 재생성은 다음 폴링 사이클(최대 60초)에서 자동 수행"이라
적어둔 그 파일 큐다. 여기서도 폴링 사이클이 실행기 노릇을 하고 있다.

#### 5.4.6 읽기/쓰기 충돌은 이미 해결돼 있다 — 더블 버퍼

**클라이언트 요청(읽기)과 인덱스 갱신(쓰기)을 한 줄로 세울 필요는 없다.**
`mcp/context_search/double_buffered_index.py` 가 이미 원자적 교체를 한다.

| 메서드 | 동작 |
|---|---|
| `begin_update(fresh=False)` | `_write_lock` 획득 후 Live→Work 복사. **임베딩까지 복사해 재계산 없음** |
| `commit_update()` | `_swap_lock` 안에서 Live↔Work 교체 + **태그 캐시 동시 교체** |
| `rollback_update()` | 실패 시 **Live 무영향** |
| `live` / `tag_cache` | 검색은 항상 Live 에서 즉시 응답 — **블로킹 없음** |

ChromaDB 컬렉션 `context_a` / `context_b` 를 번갈아 쓴다. 즉 재색인이 도는 동안에도
개발자는 기다리지 않고, **반쯤 갱신된 인덱스를 보는 일도 없다.**

**또 하나 이미 있는 조율** — `watch_state._has_active_distribute_work()`:
작업자에게 `in_progress` 작업이 있으면 **watcher 메인 루프가 일시 중지**한다.
docstring 이 밝힌 이유 두 가지: ① feature 브랜치 작업 중 main 인덱싱은 무의미
② **워커들과 git lock 경쟁 방지**. 즉 "클라이언트 작업이 진행 중이면 인덱스 갱신이 양보"가
이미 설계돼 있다. 이 게이트는 이식하되, "이번 틱 건너뜀"이 아니라 **큐에서 대기**로 바꿔야 한다(§5.4.5).

**⚠️ 단 더블 버퍼가 전부를 덮지는 않는다 — 확인할 것 3가지**

1. **BM25 는 더블 버퍼가 아니다.** `commit_update()` 주석: `# BM25 는 디스크 영속 + in-place 증분 — swap 불필요`.
   벡터 컬렉션과 태그 캐시는 원자적으로 교체되지만 BM25(SQLite FTS5)는 제자리 갱신이다.
   `_apply_bm25_incremental()` 도중 동시 검색이 **부분 갱신된 BM25 + 옛 Live 벡터**를 함께 볼 수 있다.
   실사용에서 문제가 되는지 **확인 후 판단할 것**(추측 금지).
2. **더블 버퍼는 인덱스 내부 일관성만 푼다.** §5.4.5 의 이벤트 유실은 그대로 남는다.
   `begin_update()` 의 `_write_lock.acquire()` 는 **블로킹**이라 겹친 갱신은 유실 대신 대기하지만,
   그 대기가 웹훅 HTTP 커넥션을 잡고 있으면 안 된다 — 큐가 여전히 필요한 이유.
3. **서버 모드 전용 기능이다.** docstring 이 "서버 모드에서 무중단 벡터 인덱싱"이라 명시한다.
   마스터가 쓸 모드가 정확히 그 모드다 — 유리한 조건이다.

#### 5.4.7 ✅ 기존 "서버 모드"와의 중복도 판정 완료 (2026-08-07)

AgentTest 는 이미 **서버/클라이언트 모드**를 갖고 있다(`CLAUDE.md`):
*"공용 서버 1대에서 Git 감시 + RAG 중앙 관리, 팀원 PC 의 Claude Code 는 HTTP 로 RAG 검색"*.
`docs/rag-system.md`·`docs/runbook.md` §11 정독 + 코드 실측으로 판정했다.

**결과가 계층별로 깨끗하게 갈린다:**

| 계층 | 판정 | 근거 (실측) |
|---|---|---|
| **RAG/온톨로지 서비스** (`context_search --serve`) | **거의 "리눅스에서 서버 모드 구동"** | `mcp/context_search/` 에 `sys.platform` 분기 **0건**. FastAPI+uvicorn+ChromaDB 전부 크로스플랫폼 |
| **`task_queue`** | **거의 그대로 이식** | 이미 독립 FastAPI/uvicorn 서비스. `sys.platform` 2건(`reclaim.py`·`persistence.py`)인데 **둘 다 `creationflags=... if win32 else 0` 으로 리눅스 분기가 이미 있음** |
| **`watcher/` git 감시** | **재설계** | 폴링→Gitea 이벤트(§5.4.2), `process_lifecycle`·`network_firewall` 폐기(§5.4.3) |
| **BC-250 추론 브로커** | **신규 작성** | 서버 모드에 존재하지 않음 (§6.4) |

**⚠️ "서버 모드 = 중앙 오케스트레이션"이 아니다.** `--serve` 는 **RAG 전용**이고
`http_server.py` 에 git 관련 코드가 한 줄도 없다. 실제 구조는:

```
watch.exe (서버 PC 에서 폴링) → 컨텍스트 MD 생성 → context_search --upsert → ChromaDB
context_search --serve (FastAPI) ← 팀원 PC 들이 HTTP 로 검색
```

**이미 중앙화된 것은 RAG/온톨로지 조회뿐이고 git 감시는 여전히 서버 PC 의 `watch.exe` 폴링이다.**
따라서 우리가 새로 만들 것(Gitea 이벤트 구동·추론 브로커)은 그대로 남는다.

**그대로 쓸 수 있는 자산** — `--serve` 의 HTTP 엔드포인트 30여 종:
검색(`combined`/`vector`/`tags`) · 인덱스(`upsert`/`rebuild`/`status`) · 도메인 CRUD ·
온톨로지 조회 9종 · `health`. 모드 전환도 **config 키(`server_mode`/`context_server_url`)만으로**
되도록 설계돼 있어 코드 변경이 필요 없다.

**인프라 이전 절차도 이미 문서화돼 있다** (`docs/runbook.md` §11):
`--export-state` / `--import-state` 로 **`.claude/context/`(컨텍스트 MD)와
`.claude/ontology/domains/`(온톨로지 YAML) 두 개만** 옮기면 된다.
`vector_db`·BM25·`class_graph.db`·`dependency_graph.db` 는 전부 파생 자산이라 재기동 시 자동 복구.
단 그 절차는 **"새 컴퓨터에 `AgentWatch.zip` 설치"를 전제**하므로 리눅스에선
`python -m context_search --serve` 로 대체하고, self-heal 트리거인 `watch.exe` 재기동은
포팅된 watcher 또는 `POST /api/v1/index/rebuild` 직접 호출로 대체해야 한다.

**→ §5.3 의 이식 순서 판단은 유효하고, 1·2단계 작업량은 예상보다 적다.
진짜 작업은 3단계 `watcher/` 재설계와 신규 브로커에 몰려 있다.**

---

### 5.5 프로젝트 격리 — 다중 디렉토리 · 단일 마운트

→ Split out for size: [`5_5-project-isolation.md`](5_5-project-isolation.md)
