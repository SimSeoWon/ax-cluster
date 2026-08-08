# 06. 마스터 실행 모델 확정 + gajae-code 하네스 조사 (2026-08-08)

> 마스터 사본: `sim@192.168.0.57:~/claude-workspace/reports/06-master-execution-model-and-task-queue-port.md`
> 관련: AX PLAN.md §5.4.4(systemd vs Compose) · §5.3-1(이식 1단계) · §3(gajae-code 연결 방법) · §4.4(모델 배정) · §8.3(완료 신호 불신)
> 선행: 리포트 05(Unreal MCP 확정)

> 노드 사본: `sim@192.168.0.43:~/bc250-backup-staging/reports/26-master-execution-model-and-gjc-toolcall-bench.md`

**상태:** ✅ 완료 — 결론 4건 확정 + 🔴 신규 제약 3건 발견. 커밋 `a6e1b69`·`0cbdaf6` (origin·node 동기)

## 0. 세션 시작 시점의 live 상태 (실측)

| 항목 | 상태 |
|---|---|
| `~/ax-cluster` | `main` 클린, `origin`·`node`(BC-250) 3자 동기 (`5d3470e`) |
| BC-250 #1 (192.168.0.43) | 가동 중 — `qwen2.5-coder:14b` + `35B-A3B IQ2_M` 상주 |
| 마스터 서비스 | `gitea.service` active · n8n/redmine 컨테이너 up |
| 선결 도구 | `claude` ✅ · `agy` v1.1.10 ✅ · `node`/`bun` ❌ |
| 코드 | 0줄 — `master/`·`worker/`·`client/` 는 README 스텁 |
| 포트 8101 (task_queue 기본) | 비어 있음 (`ss -tln`) |

---

# 1. 마스터 실행 모델 — **systemd + venv 확정**

## 1.1 호스트에 결합된 것들 (AgentTest 코드 실측)

| 결합 | 근거 |
|---|---|
| **호스트 CLI + 홈 디렉터리 인증** | 층2 검증이 `agy`·`claude` 를 subprocess 로 호출 — `mcp/agy_query/server.py:70` (`agy --dangerously-skip-permissions`), `mcp/context_search/llm_chat.py:71`. 바이너리는 `~/.local/bin`, 인증 상태는 `~/.claude.json` 등 홈 디렉터리 |
| **git + SSH 키** | `task_queue` 가 **매 상태 전이마다** `git add`/`commit`(감사 로그) — `mcp/task_queue/persistence.py:299~340`. `watcher/git_ops.py` 는 subprocess `git` 8건 |
| **Gitea 가 호스트 systemd 서비스** | §5.4.2 의 `post-receive` 훅이 호스트에서 실행. 컨테이너면 훅→컨테이너 전달 경로를 따로 만들어야 함(브리지 IP 하드코딩) |
| **BC-250 LAN** | 보드 firewalld 가 **192.168.0.57 만** 11434 허용. 컨테이너 NAT 출발지 주소를 별도 검토해야 함 |
| **미래 CUDA** (§7 1070 Ti) | nvidia-container-toolkit 한 겹 추가 — 드라이버조차 아직 없음 |

## 1.2 Compose 의 이점이 여기선 약하다

의존성은 `mcp chromadb fastapi uvicorn tree-sitter tree-sitter-cpp` 뿐(`build.bat:29`, `pywinpty` 는 윈도우 전용이라 제외) — **전부 순수 pip 패키지**라 venv 로 동일하게 얻는다.
별도 `requirements.txt` 는 존재하지 않아 이식 시 새로 만든다.

## 1.3 `~/CLAUDE.md` 규약과의 관계

규약은 "새 서비스는 Docker Compose 선호"이고 n8n·Redmine 이 그 패턴이다.
**그 둘은 업스트림 이미지를 그대로 쓰는 완제품 외부 서비스**인 반면, 우리 코드는
호스트 자원(git·CLI 인증·Gitea 훅·LAN·홈 디렉터리)에 붙는 자체 코드다.
규약의 취지와 어긋나지 않는다고 판단해 **systemd + venv 로 확정**한다.
(되돌리기 어려운 결정이 아니다 — 유닛을 나중에 컨테이너화할 수 있다.)

---

# 2. `task_queue` 이식 — 실측한 실제 작업량

`sys.platform` 분기는 3건뿐이고 전부 `creationflags = ... if win32 else 0` 형태라 리눅스에서 무해하다
(`persistence.py:301,307` · `reclaim.py:58`). **진짜 작업은 다른 데 있다:**

| # | 문제 | 근거 | 대응 |
|---|---|---|---|
| 1 | **플랫 import** — `from models import ...` (패키지 상대 import 아님) | `logic.py:9,12,21,24,30,33` 외. PyInstaller 가 한 디렉터리로 묶는 전제 | `python -m` 실행하려면 상대 import 전환 |
| 2 | **`_project_root()` 가 파일 위치에서 역산** | `persistence.py:22-25` — `Path(__file__).parent.parent.parent`. exe 가 UE5 프로젝트 루트 안에 있다는 전제 | 마스터엔 UE5 루트가 없다. `--serve <project_root>` 인자는 이미 받으므로 **역산 폴백을 명시적 설정으로 교체** |
| 3 | 🔴 **감사 커밋이 어느 저장소로 가나** | `persistence.py:_git_repo()` 가 `root/.git` → `root/Source/.git` 순으로 탐색 | **설계 결정 필요.** UE5 소스가 아니라 **큐 자체의 상태**이므로 §2.1 과 충돌하지 않는다 — 마스터 소유 저장소를 따로 둘 것 |

규모 9파일 / 2,717줄. 실행 모드: `--serve <root> [port] [host]`(HTTP, 기본 8101) · `--status` · `--list` · `--reset` · `--reverify` · `--send-directive` · `--list-workers` · 무인자 = MCP stdio.

---

# 3. 🔴 gajae-code(gjc) 조사 — 사용자 아이디어 검토

> 사용자 제안(2026-08-08): *"로컬 LLM은 가재코드 하네스를 활용해 서브에이전트가 재검증하고 다시 코드 작업을 요청하게 해볼까?"*

`~/gajae-code` 에 참조 클론(`Yeachan-Heo/gajae-code`, **수정 금지 — AgentTest 와 동일 취급**). TypeScript/Bun + Rust.

## 3.1 ✅ 제안한 루프는 **이미 gjc 안에 있다**

| 기능 | 실체 | 근거 |
|---|---|---|
| `ultragoal` | **내장 커맨드.** 목표 추적 → 실행 → **in-loop completion gate(architect/critic)** → 영속 원장 | `packages/coding-agent/src/cli.ts:47` · `src/commands/ultragoal.ts` · `src/goals/` · `src/gjc-runtime/ultragoal-runtime.ts` |
| 산출물 | `goals.json` + `.gjc/ultragoal/ledger.jsonl` (실행 증적·불변식 체크·완료 영수증) | `docs/extragoal-skill-template.md:69,198` |
| `extragoal` | **ultragoal + 외부 최종 리뷰 게이트** — "세션 컨텍스트를 공유하지 않는 독립 리뷰어가 완성된 diff 를 재리뷰하고 machine-parsable verdict 를 낸다. 수정은 bounded re-sign loop 로 재진입" | `docs/extragoal-skill-template.md:3` |

**즉 "서브에이전트가 재검증하고 다시 코드 작업을 요청"이 `extragoal` 의 정의 그 자체다.**

⚠️ **단 `extragoal` 은 번들이 아니다** — 문서가 명시한다: *"Extragoal is **not** a bundled workflow skill; `gjc extragoal` does not exist."*
`docs/extragoal-skill-template.md` 의 frontmatter 이하를 잘라 `~/.gjc/agent/skills/extragoal/SKILL.md` 로 설치하고
`gjc config set skills.enabled true` + 해당 스캔(`enablePiUser`)을 켜야 한다. 파일 스킬 탐색은 기본 off.

## 3.2 ✅ 역할별 모델 매핑이 우리 모토와 정확히 겹친다

gjc 는 **5역할**(`default` · `executor` · `planner` · `critic` · `architect`)에 모델을 각각 배정한다
(`~/.gjc/agent/models.yml` 의 `profiles.<name>.model_mapping`, `docs/models.md:193-205`).
역할당 단일 selector 또는 **순서 있는 폴백 배열**을 받는다.

```yaml
profiles:
  ax-hybrid:
    model_mapping:
      executor:  ollama/<코더모델>          # 무료 로컬 = 대량생산
      critic:    anthropic/claude-sonnet-5  # 상용 = 검증만
      architect: anthropic/claude-sonnet-5
```

**모토("무료 로컬 LLM=대량생산, 상용 모델=검증만")가 설정 파일 한 장으로 표현된다.**
`ollama` 는 1급 provider 다 — `packages/ai/src/providers/ollama.ts`, 네이티브 API 사용.

## 3.3 🔴 **그런데 실측에서 막혔다 — 14b 가 tool call 을 구조화해서 못 낸다**

gjc 의 Ollama provider 는 `message.tool_calls` 를 읽는다. BC-250 에 직접 찔러본 결과:

| 모델 | `message.tool_calls` | 실제 출력 |
|---|---|---|
| `qwen2.5-coder:14b` | **`null` (3/3 실패, `temperature:0`)** | 호출 JSON 이 `content` 에 **문자열로** 나옴 — `{"name":"get_weather","arguments":{"city":"Seoul"}}` |
| `35B-A3B IQ2_M` | ✅ **정상 구조화** (`id` 포함) | `content` 비어 있음 |

`/api/show` 는 14b 에 대해 `capabilities: ['completion','tools','insert']` 를 광고하고
템플릿에도 tool 분기가 있다(1,615자, `tool_call` 포함). **광고와 실제가 다르다.**

**함의 — §4.4 모델 배정에 직격이다.**
- 지금까지: 14b = 코드 생성 / 35B = 컨텍스트 쿠킹
- 에이전틱 하네스의 `executor` 역할은 **tool 호출이 전제**인데 14b 로는 못 채운다
- 반대로 35B 는 리포트 02 에서 **코드 생성 시 API 환각**이 확인된 모델이다
- → **"tool 호출 되는 모델은 코드가 약하고, 코드 되는 모델은 tool 호출이 안 된다"** 는 충돌

> ⚠️ 이건 gjc 를 쓰든 안 쓰든 남는 문제다. 지금 구조(마스터가 컨텍스트를 밀어넣는 **제약 생성**,
> `[PSEUDO]` 본문만 채우기)는 tool 호출을 요구하지 않아 14b 로 성립한다.
> **하네스를 에이전틱으로 바꾸는 순간 전제가 깨진다.**

## 3.4 🔴 gjc 도 loopback 전용 — **Unreal MCP 와 똑같은 제약이 두 번째**

| 표면 | 전송 | 원격 가능? |
|---|---|---|
| **SDK WebSocket** (유일한 공식 기계 제어 인터페이스) | `ws://127.0.0.1:<port>/?token=<token>` | ❌ **loopback 전용.** discovery 파일 `<repo>/.gjc/state/sdk/<sessionId>.json` 에 토큰, 잘못된 토큰은 handshake 에서 401 |
| **Coordinator MCP** (`gjc mcp-serve coordinator`) | stdio JSON-RPC. 도구 19종(read 10 + mutating 9, `gjc_delegate_plan/execute/team` 포함) | ❌ 로컬 stdio + 로컬 discovery 파일 의존 — SSH stdio 터널 필요 |
| `--mode rpc` / `rpc-ui` / `bridge` | — | ❌ **제거됨.** "not supported compatibility interfaces" |

**→ PLAN §3 의 "WebSocket SDK 로 마스터가 외부 컨트롤러 역할" 가설은 그대로는 성립하지 않는다.**
`gjc` 는 **파일을 소유한 머신에서 돌아야 한다** = 윈도우 PC(`client/`).

## 3.5 그래서 배치가 이렇게 된다 (제안)

```
윈도우 UE5 PC  ── gjc(ultragoal/extragoal) + Unreal MCP, 둘 다 loopback 로컬
      │  모델 백엔드 호출 (/api/chat · /api/tags · /api/show — 단 3종)
      ▼
마스터 192.168.0.57 ── Ollama API 호환 브로커 (§4 "마스터 브로커" 결정 유지)
      │  stateless
      ▼
BC-250 192.168.0.43 ── 추론 (방화벽 0.57 만 허용 → 규칙 변경 불필요)
```

**이점 3가지:**
1. gjc 가 부르는 Ollama 엔드포인트가 **3종뿐**이라 브로커 표면이 작다
2. §4 "작업자가 추론 노드를 직접 호출하지 않는다" 가 지켜지고, **BC-250 방화벽 규칙을 건드릴 필요가 없다**
3. **마스터에 `bun`/`node` 가 필요 없어진다** — gjc 가 윈도우에서 도니까. §3 선결 항목 하나가 사라진다

---

# 4. 🟢 §8.3 보강 — agy 를 제대로 쓰는 법을 찾았다

리포트 05 에서 agy 는 **출처를 지어냈다**(도메인 루트만 인용, 핵심 절이 틀림).
이번엔 같은 도구로 **인용이 전부 맞았다.** 차이는 하나다.

| | 리포트 05 (실패) | 이번 (성공) |
|---|---|---|
| 입력 | 웹에서 찾으라고 지시 | **`--add-dir` 로 실제 파일을 쥐여줌** |
| 인용 | `unrealengine.com/` 같은 도메인 루트 | `docs/sdk.md:111-145` 같은 파일:줄번호 |
| 검증 결과 | 🔴 핵심 절 2건 오류 + 출처 위조 | ✅ spot-check 2건 **정확히 일치** |
| 소요 | 50s / 49,513 tok | 99.8s / 269,523 tok |

**→ 규칙: agy 에 "찾아라"라고 시키지 말고 "이 파일들을 읽어라"라고 시킨다.**
웹 리서치는 여전히 신뢰할 수 없다.

## 4.1 ⚠️ 이번에 내가 낸 버그 (agy 탓 아님)

1차 호출이 엉뚱한 답(`--dangerously-skip-permissions` 설명)을 냈다. 원인은 **내 argv 실수**다:

```bash
agy -p --dangerously-skip-permissions ... "프롬프트"   # ❌ -p 가 다음 토큰을 프롬프트로 먹음
agy --dangerously-skip-permissions ... -p "프롬프트"   # ✅ 프롬프트를 -p 바로 뒤에
```

리포트 04 의 "argv 순서 무관"은 **플래그끼리의 순서**를 뜻하지, `-p` 가 값을 안 먹는다는 뜻이 아니다.
**`-p` 는 반드시 프롬프트 직전에 둔다.**

또한 두 실행 모두 `--mode accept-edits` 였는데도 지시한 `./FINDINGS.md` 가 아니라
`./ref/FINDINGS.md` 에 썼다 — **§8.3 대로 산출물 경로까지 확인해야 한다**(`status:SUCCESS` 는 근거가 아니다).

---

---

# 4.5 🔬 tool-calling 관문 벤치 — 3모델 실측 (2026-08-08)

하네스: `~/claude-workspace/bin/bench_toolcall.py`. `/api/chat` + `tools`, `temperature:0`, `num_ctx:8192`.
**관문 4종** — 에이전트 루프가 실제로 요구하는 것들:

1. **단발호출** — 구조화된 `tool_calls` 를 내는가 (gjc 의 최소 요구, 텍스트 폴백 없음)
2. **도구선택** — 도구 3개 중 맞는 것을 고르는가 (라우팅)
3. **멀티턴** — 도구 **결과를 되먹였을 때** 루프가 이어지는가 (에이전트 루프의 본체)
4. **억제** — 도구가 필요 없을 때 헛호출을 참는가

| 모델 | 1.단발 | 2.선택 | 3.멀티턴 | 4.억제 | 판정 |
|---|---|---|---|---|---|
| **`35B-A3B IQ2_M`** | ✅ 5.0s | ✅ 4.9s | ✅ 6.8s | ✅ 3.7s | **4/4 — executor 가능** |
| `devstral:24b` (신규, 14GB) | ✅ 75.7s | ✅ 2.9s | ❌ | ✅ 2.2s | **3/4 — 부분** |
| `qwen2.5-coder:14b` | ❌ | ❌ | ❌ | ✅(호출 자체를 못 하니 자동 통과) | **1/4 — 불가** |

## 4.5.1 🔴 `devstral:24b` 의 실패 형태 — 재현 확인

3번만 실패한 게 이상해 격리 실험했다(`temperature:0`, **완전 재현**):

| 프롬프트 | `tool_calls` | `content` |
|---|---|---|
| `What is the weather in Seoul?` | ✅ | (비어 있음) |
| `... ? **Answer in one sentence.**` | ❌ | `"I'll check the weather for you."` |
| `... ? Answer in one sentence.` (재시도) | ❌ | 위와 **동일** |
| `... ? **Use the tool**, then answer in one sentence.` | ✅ | (비어 있음) |

**→ 프롬프트에 형식/답변스타일 지시가 붙으면 도구 호출을 빠뜨리고 "하겠다"고 말만 하고 멈춘다.**
에이전틱 하네스의 시스템 프롬프트는 형식 지시로 가득하므로 **실전에서 계속 터진다.**
35B 는 **같은 "Answer in one sentence" 프롬프트로 멀티턴을 통과**했다 — 차이가 분명하다.

또한 devstral 은 첫 호출에 **75.7초**가 걸렸다(모델 적재 포함). 14GB 라 15.6GiB 에 여유가 1.6GB 뿐이다.

## 4.5.2 함의 — §9.4 충돌의 해소 방향

**보드 위에서 4관문을 전부 통과하는 모델은 `35B-A3B IQ2_M` 뿐이다.**
그런데 그 모델은 리포트 02/25 에서 **코드 생성 시 API 환각**이 확인됐다.

→ **제안: 역할을 쪼갠다.** 35B 를 **에이전틱 드라이버(도구 오케스트레이션)** 로 쓰고,
코드 본문 생성은 **14b 를 "도구"로 호출**해 채운다. 각 모델의 강점을 유지하고
14b 의 tool-calling 결함은 **호출당하는 쪽이라 무관**해진다.
gjc 의 역할 매핑(`executor`/`critic`/…)과도 층이 맞는다 — 다만 이 배치는 **미검증 가설**이다.

🔴 **보류 — 전환 비용을 제대로 재보니 성립하지 않는다.** 기존 문서의 "36초"는 **14b 방향만** 본 값이었다:

| 호출 | 시간 | 전환 페널티 |
|---|---|---|
| 35B (전환) | **66.9s** / 재현 64.6s | ~64s |
| 35B (상주) | 2.7s | — |
| 14b (전환) | **37.5s** | ~36s |
| 14b (상주) | 1.4s | — |

**왕복 1회 ≈ 100초.** 드라이버가 코드 생성기를 태스크당 2번만 불러도 200초가 순수 적재로 나간다.
**보드 2대 전까지 착수하지 않는다.**

## 4.5.3 ✅ 보드 1대에서 되는 길 — gjc 의 **런타임이 아니라 계약**을 가져온다

`extragoal` 의 **"Custom — user-provided external reviewer command"** 레인은 **도구 호출을 요구하지 않는다.**
계약이 하나뿐이다 — *마지막 비어 있지 않은 줄이 정확히 `VERDICT: APPROVE`/`REQUEST_CHANGES`, fail-closed.*

**→ tool-calling 이 안 되는 14b 도 리뷰어는 된다.** 실측:

| 케이스 | 결과 |
|---|---|
| 버그 있는 diff (음수 클램프 누락) | ✅ `VERDICT: REQUEST_CHANGES` — 형식·판정 정확 (47.5s, 적재 포함) |
| 정상 diff (`FMath::Clamp`) | ✅ `VERDICT: APPROVE` (1.1s, 상주) |

⚠️ **표본 2개짜리 장난감 케이스 — 신호이지 증명이 아니다.** UE5 실제 diff 로 재측정할 것.
⚠️ **교차 계열 제약**상 14b 가 작성·리뷰를 겸하면 계약 위반이다. 성립 조합은
**작성=BC-250 14b(기존 제약 생성 경로, gjc 아님) / 리뷰=상용**이고, **이는 §4.3 3층 게이트와 이미 같은 모양**이다.

**→ 결론: 보드 1대 동안은 gjc 런타임을 도입하지 않고, 층2 검증을 `VERDICT:` fail-closed 계약으로 바꾼다.**

---

# 4.6 🔴 장비 구성 정정 (2026-08-08, 세션 말미)

계획 문서가 **두 군데 틀려 있었다.** 사용자 확정 실제 보유:
**윈도우 UE5 PC 2대 + BC-250 2대(#1 추론 / #2 Bazzite 게임 머신) + 리눅스 마스터.**

| 항목 | 계획이 적고 있던 것 | 실제 |
|---|---|---|
| 작업장 | 윈도우 **1대** | **2대** — 둘 다 언리얼 개발에 사용 |
| BC-250 #2 | "미구성 — #1 완성 후 복제" → (세션 중) "주문 후 도착 대기" | **Bazzite 게임 머신으로 가동 중.** #1 완성 후 전환 **의향**은 있으나 확정 아님 |

**파급 (가) — `claim/lease/fencing` 은 걷어낼 수 없다.**
§5.2-D 는 "1인 프로젝트니 팀 복잡도를 덜자"였는데, **파일을 소유한 작업장이 물리적으로 2대**다.
축소 판단 기준을 ***"팀 때문에 존재하나?"*** → ***"동시 접근하는 주체가 실제로 여럿인가?"*** 로 교정했다.
오케스트레이터도 둘이 아니라 **셋**(윈도우 2 + 마스터).
⬜ **신규 미결:** 두 작업장이 **같은 UE5 프로젝트를 보는지** — 전자면 같은 `task/<id>`·큐를 두고 경쟁이 실재하고,
후자면 라우팅에 **작업장 식별**이 필요하다.

**파급 (나) — 노드 증설은 셋업이 아니라 자원 배분 결정이다.**
#2 를 추론으로 돌리려면 **게임 머신을 내줘야 한다.** 계획은 #2 를 **조건부로만** 다룬다.
⚠️ **Bazzite 는 rpm-ostree 이미지형**이라 #1 에서 필수였던 TTM/GTT 캡 상향·커널 부팅 파라미터·
헤드리스(`multi-user.target`) 전환이 같은 절차로 되는지 **미확인**. 일반 Fedora 재설치가 더 쌀 수 있다.

> **교훈:** 이 항목은 한 세션에서 **세 번 고쳐 썼다**(미구성 → 도착 대기 → 게임 머신).
> 장비 보유 현황처럼 **사용자만 아는 사실**은 계획서에 추론으로 채우지 말고 **먼저 물어야 한다.**

---

# 5. 🧪 로컬 LLM 을 내 작업 보조로 써봤다 (사용자 제안, 2026-08-08)

> *"네가 작업할 때도 로컬 LLM을 보조로 쓰는 건 어때?"*

용도를 **대량 텍스트 선별(triage)** 하나로 좁혀 실증했다 — 모토를 내 작업에 그대로 적용:
**BC-250 이 "어디를 읽을지" 좁히고, 사실 확정은 내가 원문으로 한다.**

도구: `~/claude-workspace/bin/bc250-ask.sh` + `_bc250_ask.py` (stdin=컨텍스트, argv=지시문, stateless `/api/generate`).

## 5.1 실측 결과 — 과제: 문서 81개 중 어디를 읽어야 하나

| 지표 | 값 |
|---|---|
| 입력 | 15,540자 → **3,891 tok** (81개 문서의 파일명 + 소제목 인덱스) |
| prefill | **12.5s** |
| 생성 | 3,737 tok @ **57.4 t/s** |
| 총 | **79.4s** |

**정확도 (내가 원문으로 검증):**

| 항목 | 결과 |
|---|---|
| **파일명 환각** | ✅ **0건** — 댄 8개 파일 전부 실존 |
| (A) 헤드리스 실행 | ✅ 1순위 `environment-variables.md` **적중** — 실제로 여기 548줄에 `gjc -p --no-session` 이 있다 |
| (B) tool_calls 폴백 | 🔴 **1순위 `ai-schema-normalize.md` 오답**(관련 키워드 0건 — 스키마를 *보내는* 쪽 문서다). 4순위 `provider-streaming-internals.md` 가 정답이었다 |

**→ 목록은 쓸 만한데 순위를 믿으면 안 된다.** 8개 중 2개가 실제로 유용했다.

## 5.2 대가

- 🔴 **생성 3,737 토큰 중 ~95%가 "Thinking Process"** — "사고 과정은 쓰지 마라"는 지시를 무시했다.
  실제 답은 15줄. **저양자화 35B 는 지시 준수가 약하다.**
- 모델 전환 비용이 실재한다 — 14b 테스트와 번갈아 쓰다 매번 ~30s 재적재를 물었다(`MAX_LOADED_MODELS=1`).

## 5.3 🔴 새 하드웨어 제약 발견 — `num_ctx=32768` 은 못 쓴다

첫 시도에서 `num_ctx: 32768` 로 주자 **9분 59초 만에 HTTP 500** 이 났다
(보드 로그: `[GIN] ... | 500 | 9m59s | 192.168.0.57 | POST "/api/generate"`).
프롬프트가 152토큰뿐이었는데도 그랬다 — **KV 캐시 할당 자체가 문제**다.
당시 보드 메모리는 `total 14 / used 13 / available 0` (GiB).
`num_ctx: 8192` 로 낮추니 3,891토큰 입력이 79초에 정상 처리됐다.

**→ 35B-A3B IQ2_M 의 실용 컨텍스트 상한을 확정해야 한다.** 8192 는 되고 32768 은 안 된다.

## 5.4 ⚠️ 내가 낸 버그 (기록용)

1. **`python3 -` + heredoc** — 인터프리터가 stdin 을 **프로그램 소스로** 소비해
   `sys.stdin.read()` 에 컨텍스트가 안 들어갔다. 보드 로그의 `task.n_tokens = 152` 로 발각됐다
   (기대값 ~5,000). → 파이썬 프로그램을 별도 파일로 분리해 해결.
   **모델이 빈 자료를 받고도 지어내지 않고 "자료가 없다"고 거부한 것은 35B 의 좋은 신호다.**
2. `pkill -f bc250-ask` 가 **자기 명령줄까지 매칭**해 셸이 죽었다(exit 144).

## 5.5 판정

**쓸 값어치가 있되 용도가 좁다.** "N개 문서 중 어디를 볼까" 같은 **선별**에는 79초에 답이 나와
내가 81개를 읽는 것보다 훨씬 싸다. 다만 **순위·요약·사실은 신뢰 불가**라 반드시 원문 검증이 붙어야 한다.
이건 agy 에 대한 §4 의 결론과 **정확히 같은 형태**다 — 위임은 후보를 좁히는 데 쓰고, 확정은 1차 출처로.

---

## 6. 실행한 명령 / 변경

- `git clone --depth 30 https://github.com/Yeachan-Heo/gajae-code.git ~/gajae-code` (참조용, **수정 금지**)
- BC-250 tool-calling 실측: `/api/chat` + `tools` 페이로드 (14b 3회 / 35B 1회), `/api/show` capabilities 조회
- agy 리서치 2회 (스크래치 격리 디렉터리, `--add-dir` 로 문서 사본만 노출)
- PLAN.md 갱신 — §5.4.4 확정 · §3 항목 정리 · §9(신설) gjc 배치

---

# 6.5 이식 1단계 착수 — `task_queue` (2026-08-08 후반)

§5.4.7 판정("거의 그대로 이식")은 맞았다 — `sys.platform` 분기 3건은 전부 무해했다.
**진짜 작업은 플랫폼이 아니라 "전제"를 바꾸는 3곳이었다:**

| # | 원본 | 마스터에서 왜 깨지나 | 조치 |
|---|---|---|---|
| 1 | 플랫 import | PyInstaller 가 한 디렉터리로 묶는 전제 | 패키지 상대 import(7파일 24건) |
| 2 | `_project_root()` 파일 위치 역산 | UE5 루트가 없어 **`ax-cluster/` 에 상태를 쓴다** | `AX_TASK_QUEUE_ROOT` 명시. **폴백 없이 즉시 실패** |
| 3 | `--cleanup-branches` | root 가 큐 상태 저장소라 **조용한 no-op** | **거부**(브랜치 정리는 윈도우의 일) |

추가로 `server.py` 최상단의 `FastMCP` import 때문에 MCP SDK 없이는 HTTP 서비스조차 못 떴다 —
stdio 를 `mcp_server.py` 로 떼고 지연 import 로 바꿨다.

> ⚠️ **3번 거부를 처음엔 함수 중간에 넣었다** — 그 위치면 archive/purge 를 **이미 수행한 뒤**
> 실패를 반환한다. 진입부로 옮겨 아무것도 건드리기 전에 거부하도록 고쳤다.

**실측 — §4.2 의 "두 작업장 경쟁 방어"가 실제로 도는가:**
claim 시 `epoch=1`·`assignee` 부여 → **다른 워커의 같은 task claim 은 빈 응답**(이중 claim 없음) →
**stale epoch submit 은 거부**(`stale epoch 0 < current 1 (reassigned)`) → 재기동 후 디스크에서 복원.
감사 커밋은 `/home/sim/ax-state`(신설 로컬 git)에 상태 전이마다 누적.

## 6.6 systemd 등록 + LAN 개방

`ax-task-queue.service` 설치·enable·기동 (**is-enabled / is-active 확인**). 등록 **전에**
`ExecStart` 가 `PYTHONPATH` 없이 도는지 먼저 확인했다(`WorkingDirectory` 만으로 성립).

- 샌드박스 실적용: `ProtectSystem=strict` · `ProtectHome=read-only` · `NoNewPrivileges=yes` ·
  `ReadWritePaths=/home/sim/ax-state`. 그 상태에서 상태 쓰기·git 감사 커밋 정상.
- 🔴 **`Restart=always` 실동작 확인** — `kill -9` 후 재기동(`NRestarts=1`), 상태는 디스크에서 복원.
  **§5.4.3 의 "`process_lifecycle.py` 폐기하고 systemd 에 넘긴다"가 실증됐다.**
- ⚠️ 선결이던 `python3-venv`·`python3-pip` 가 이 박스에 없어 `pkexec` 로 설치했다.

**노출 실측 → LAN 한정 개방** (사용자 지시): `ufw` 기본 정책이 `deny (incoming)` 이라 8101 이
**LAN 에서 닿지 않았고**, `task_queue` 에는 **인증 계층이 0건**이다. 둘을 같이 보고
`ufw allow from 192.168.0.0/24 to any port 8101` 로 **출발지 한정** 개방했다.
BC-250 에서 실제로 호출해 도달·쓰기 확인. 출발지 한정이라 **라우터 포트포워딩 사고까지 막는다.**
🔴 **방어선이 방화벽 하나뿐** — `Anywhere` 로 넓히지 말 것, LAN 신뢰가 깨지면 인증 먼저.

## 6.7 문서 정합성 복구

`CLAUDE.md` 에 **실제 오류**가 있었다 — *"AgentTest 의 `worker/` 가 `master/` 로 이식된다"*.
`PLAN.md` §2.1 이 2026-08-07 에 정반대로 정정한 내용이라, 읽은 세션이 워커 하네스를 마스터로
옮기려 들 수 있었다. 그 외 "구현 없음"·"오케스트레이터 둘"·"#2 미확인"·해결된 Open decisions 4건을
전부 갱신했고, `worker/`·`client/` README 와 `~/CLAUDE.md`(머신 가이드)도 오늘 실측값으로 맞췄다.

**머신 가이드를 저장소로 옮겼다** — `machines/sim-desktop.md`·`machines/bc250-1.md` 를 정본으로 두고
각 머신 홈의 `~/CLAUDE.md` 를 **심볼릭 링크**로 걸었다(왕복 테스트로 정본 하나임 확인).
사본을 양쪽에 두면 갈라지는 것을 위 오류가 이미 증명했다.
BC-250 가이드는 `pkexec` 불가 사실이 **틀린 지시 뒤에** 있어 순서를 뒤집었다.

---

## 7. 이번 세션 산출물

**커밋 8건** (`ax-cluster`, origin·노드 3자 동기):

| 커밋 | 내용 |
|---|---|
| `a6e1b69` | §5.4.4 systemd 확정 · §9 신설(gjc 배치) |
| `0cbdaf6` | §9.4.1 tool-calling 벤치 · devstral 탈락 |
| `aa9cd70` | 전환 비용 정정(왕복 ~100초) · §9.4.3 보드 1대 경로 |
| `5ff80c6`·`5bde344` | 🔴 장비 구성 정정 — 윈도우 2대 · BC-250 #2 는 게임 머신 |
| `5e6c00d`·`6a4c874` | 층2 검증 fail-closed 계약 + `.gitignore` |
| `614abf0` | `task_queue` 이식 |
| `4a3afb9` | systemd 등록·enable + 노출 실측 |
| `7b85580` | 8101 LAN 한정 개방 |
| `8af9d99` | 전 문서 최신화(CLAUDE.md 오류 포함) |
| `d7ee6a1` | 머신 가이드 `machines/` 로 버전 관리 + 심볼릭 링크 |

**저장소 밖 산출물:**

| 위치 | 내용 |
|---|---|
| `/etc/systemd/system/ax-task-queue.service` | **가동 중**(enabled). `systemctl status ax-task-queue` |
| `/home/sim/ax-state` | 큐 상태 저장소(신설 로컬 git) — 상태 전이마다 감사 커밋 |
| `/home/sim/ax-cluster/.venv` | 마스터 venv (`python3-venv`/`pip` 는 `pkexec` 로 설치) |
| ufw 규칙 | `8101/tcp ALLOW IN 192.168.0.0/24` |
| `/home/sim/CLAUDE.md` | → `ax-cluster/machines/sim-desktop.md` **심볼릭 링크** |
| BC-250 `~/CLAUDE.md` | → `ax-cluster/machines/bc250-1.md` **심볼릭 링크** |
| `~/gajae-code` | 참조 클론 (**수정 금지** — AgentTest 와 동일 취급) |
| `~/claude-workspace/bin/bc250-ask.sh` + `_bc250_ask.py` | BC-250 선별 질의 도구 |
| `~/claude-workspace/bin/bench_toolcall.py` | tool-calling 관문 4종 벤치 (모델 인자 여러 개) |

## 남은 것

**다음 세션에서 바로 집을 것 (우선순위 순):**

- [ ] 🔴 **능력 기반 라우팅 (`requires: ue5`)** — 큐가 아직 `job_kind`(write/verify) 분기뿐이라
      **마스터 워커가 UE5 잡을 집어갈 수 있다.** 빌드 게이트를 CI 러너 패턴으로 돌리기 위한 선결
- [ ] **이식 2단계 `mcp/context_search/`(RAG)** — `sys.platform` 분기 **0건**이라 1단계보다 가볍다.
      ChromaDB 인덱스 이관(재색인 필요 여부 확인)이 실제 작업
- [ ] **층2 계약을 UE5 실제 diff 로 재측정** — 지금 근거는 표본 2개 장난감 케이스다
- [ ] **`task_queue` 인증** — 방어선이 ufw 하나뿐이다. LAN 신뢰가 깨지기 전에 붙일 것

**막혀 있는 것 (선결이 사람 결정이거나 외부):**

- [ ] `extragoal` 실동작 — 선결: 윈도우 PC 에 `bun`/`node` + `gjc` 설치
- [ ] `models.yml` 의 `ollama` provider 를 마스터 브로커 주소로 — 선결: 브로커 미구현
- [ ] §9.4.2 (35B=드라이버 / 14b=코드생성기) — **보류.** 왕복 전환 ~100초.
      BC-250 #2 가 추론 노드가 되어야 하고, 그건 **게임 머신을 내주는 사용자 결정**이다

**계속 남아 있는 숙제:**

- [ ] **장시간 안정성 재검증** (리포트 01 의 `MemAvailable` 단조 감소) — 무인 운용의 전제. 미해결
- [ ] **35B 실용 컨텍스트 상한 확정** — `8192` 정상 / `32768` 은 152토큰 프롬프트에도
      9m59s 후 HTTP 500. 그 사이 미측정. 보드는 이미 `KV_CACHE_TYPE=q4_0`+`FLASH_ATTENTION=1` 이다
- [ ] **이벤트 큐 설계** — Gitea 웹훅 전환의 전제. `task_queue` 와 합치지 말 것

---

**세션 종료 상태 (2026-08-08):** `ax-task-queue` 가동 중(enabled) · 저장소 3자 동기(`d7ee6a1`) ·
잔여 프로세스 없음 · **BC-250 은 세션 종료 시 원격 종료함**(재기동은 스마트 콘센트 재공급 → BIOS 자동 부팅).
