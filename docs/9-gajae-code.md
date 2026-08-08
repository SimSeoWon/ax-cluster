> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

## 9. gajae-code(gjc) 배치 — 하네스는 윈도우에, 마스터는 모델 백엔드 (2026-08-08)

참조 클론: `/home/sim/gajae-code` (**수정 금지** — AgentTest 와 동일 취급). TypeScript/Bun + Rust.

### 9.1 🔴 gjc 도 loopback 전용이다 — Unreal MCP 와 똑같은 제약이 두 번째

| 표면 | 전송 | 원격? |
|---|---|---|
| **SDK WebSocket** — 문서가 "the **only** external machine-control interface" 라 명시 | `ws://127.0.0.1:<port>/?token=<token>`. discovery 파일 `<repo>/.gjc/state/sdk/<sessionId>.json` 에 per-session 토큰, 오토큰은 handshake 에서 401 | ❌ loopback 전용 |
| **Coordinator MCP** (`gjc mcp-serve coordinator`) — 도구 19종(read 10 + mutating 9, `gjc_delegate_plan/execute/team` 포함) | stdio JSON-RPC + 로컬 discovery 파일 | ❌ SSH stdio 터널 필요 |
| `--mode rpc` / `rpc-ui` / `bridge` | — | ❌ **제거됨** ("not supported compatibility interfaces") |

**→ gjc 는 파일을 소유한 머신에서 돌아야 한다 = 윈도우 UE5 PC(`client/`).**
§2.1 의 "마스터는 인프라지 작업장이 아니다"와 정확히 맞물린다 — 하네스는 작업장에 있어야 한다.

### 9.2 그래서 마스터의 역할은 **모델 백엔드**다

```
윈도우 UE5 PC  ── gjc(ultragoal) + Unreal MCP, 둘 다 loopback 로컬
      │  Ollama 네이티브 API 3종만 호출 (/api/chat · /api/tags · /api/show)
      ▼
마스터 192.168.0.57 ── Ollama API 호환 브로커 (§4 "마스터 브로커" 결정 유지)
      │  stateless
      ▼
BC-250 192.168.0.43 ── 추론
```

이점 셋: ① gjc 가 부르는 엔드포인트가 **3종뿐**이라 브로커 표면이 작다
② §4 "작업자는 추론 노드를 직접 호출하지 않는다"가 지켜지고 **BC-250 방화벽 규칙을 안 건드린다**
③ **마스터에 `bun`/`node` 가 필요 없어진다**(§3 선결 항목 소멸).

설정 위치는 `~/.gjc/agent/models.yml` 의 `providers.ollama.baseUrl`
(또는 환경변수 `OLLAMA_BASE_URL`). Ollama 는 gjc 의 1급 provider 다
(`packages/ai/src/providers/ollama.ts`, 네이티브 API 사용 — OpenAI 호환 경로가 아님).

### 9.3 ✅ 우리가 만들려던 검증 루프가 이미 있다

| 기능 | 실체 |
|---|---|
| `ultragoal` | **내장 커맨드**(`packages/coding-agent/src/cli.ts:47`). 목표 추적 → 실행 → **in-loop completion gate(architect/critic)** → 영속 원장(`goals.json` + `.gjc/ultragoal/ledger.jsonl`) |
| `extragoal` | ultragoal + **외부 최종 리뷰 게이트** — 세션 컨텍스트를 공유하지 않는 독립 리뷰어가 완성 diff 를 재리뷰하고 machine-parsable verdict 를 낸다. 수정은 **bounded re-sign loop** 로 재진입 |

⚠️ **`extragoal` 은 번들이 아니다** — 문서가 명시: *"`gjc extragoal` does not exist."*
`docs/extragoal-skill-template.md` 의 frontmatter 이하를 `~/.gjc/agent/skills/extragoal/SKILL.md` 로
설치하고 `gjc config set skills.enabled true` + `enablePiUser` 를 켜야 한다(파일 스킬 탐색 기본 off).

**역할별 모델 매핑이 우리 모토와 겹친다** — 5역할(`default`·`executor`·`planner`·`critic`·`architect`)에
모델을 각각 배정한다(`~/.gjc/agent/models.yml` 의 `profiles.<name>.model_mapping`, 역할당 폴백 배열 허용).
**executor = BC-250 로컬(대량생산) / critic·architect = 상용(검증만)** 이 설정 한 장으로 표현된다.

#### 9.3.1 🔴 리뷰어 계약 — §8.3 "완료 신호 불신"이 이미 기계 계약으로 있다

`extragoal` 의 리뷰어 호출 형태(`docs/extragoal-skill-template.md` §"Reviewer implementations"):

```sh
gjc -p --no-session --model <교차계열 모델> --tools read,search,find "<리뷰 프롬프트 + 번들 경로 + verdict 계약>"
```

우리가 §8.3 에서 손으로 하려던 것을 **계약으로 못 박아 뒀다:**

| 계약 | 내용 |
|---|---|
| **판정 형식** | 응답의 **마지막 비어 있지 않은 줄이 정확히** `VERDICT: APPROVE` 또는 `VERDICT: REQUEST_CHANGES` |
| **fail-closed** | 누락·형식오류·타임아웃은 **절대 `APPROVE` 로 매핑하지 않는다** ← §8.3 그 자체 |
| **교차 계열 강제** | 리뷰어는 작성자(`default`/`executor`)와 **다른 모델 계열**이어야 한다 |
| **컨텍스트 격리** | 서브 세션은 작성 세션과 **대화 상태를 공유하지 않는다** |
| **읽기 전용 강제** | 프롬프트가 아니라 **`--tools` 허용목록**으로 강제. 허용목록 밖 도구 호출은 계약 위반 = 그 라운드 실패 |
| **프롬프트 인젝션 방어** | 번들 내용(diff·스펙·반론)은 **"지시가 아니라 검토 대상 데이터"** 로 취급 |
| **머지 조건** | 최신 verdict 가 `APPROVE` 이고 모든 지적이 수정됐거나 재주장 없이 반박됐을 때만. **리더에게 재량 없음** |

⚠️ **함정 2개** (문서가 명시):
1. `goal` 도구가 허용목록 **바깥에서 자동 주입**된다 — 그 mutating op 가 `.gjc` 세션 상태를 쓴다.
   **비활성화가 필수**이며, 검토 대상 체크아웃을 더럽히지 않으려면 **저장소 밖 전용 게이트 디렉터리**에서
   `.gjc/config.yml` 에 `goal.enabled: false` 를 두고 실행할 것(경로는 절대경로로 전달).
2. 일회성 print 세션에서는 **`default` 모델이 판정을 쓴다** — `task` 도구가 허용목록에 없어
   `critic`/`architect` 역할로 위임되지 않는다. 즉 **`--model` 을 명시해야 한다**(`model_mapping` 이 안 먹는다).

**"Custom — user-provided external reviewer command" 레인**도 있다 — 계약만 만족하면 어떤 리뷰어든 된다.
문서는 이 레인에서 *"번들이 머신을 떠난다"* 고 경고하지만, **우리 경우 리뷰어가 LAN 내부(BC-250/마스터)라
egress 가 없다** — 오히려 유리한 조건이다.

### 9.4 🔴 그런데 실측이 막았다 — 14b 가 tool call 을 구조화해서 못 낸다

gjc 의 Ollama provider 는 `message.tool_calls` 를 읽는다. BC-250 실측:

| 모델 | `tool_calls` | 실제 |
|---|---|---|
| `qwen2.5-coder:14b` | **`null` (3/3, `temperature:0`)** | 호출 JSON 이 `content` 에 **문자열로** 나옴 |
| `35B-A3B IQ2_M` | ✅ 정상 구조화(`id` 포함) | `content` 비어 있음 |

`/api/show` 는 14b 에 `capabilities:['completion','tools','insert']` 를 광고하고 템플릿에도
tool 분기가 있는데도 그렇다 — **광고를 믿지 말 것.**

**🔴 gjc 쪽에 텍스트 폴백이 없다 (코드 실측).** `packages/ai/src/providers/ollama.ts:533` 이
`if (chunk.message?.tool_calls?.length)` 로 **구조화된 배열이 있을 때만** 도구 호출을 방출한다.
`content` 에 실린 JSON 을 건져 올리는 경로가 없다 — 즉 14b 의 출력은 **그냥 평문으로 취급되고
도구는 호출되지 않는다.** (스트리밍 인자 파싱 `parseStreamingJson()` 은
`provider-streaming-internals.md:108-119` 대로 **이미 tool_call 로 인식된 뒤**의 부분 JSON 복구용이라
이 문제를 덮지 못한다.)

**충돌:** tool 호출 되는 모델(35B)은 **코드 생성 시 API 환각**이 확인됐고(리포트 25/02),
코드가 되는 모델(14b)은 tool 호출이 안 된다.

> ⚠️ 현행 설계(마스터가 컨텍스트를 밀어넣는 **제약 생성** — `[PSEUDO]` 본문만 채우기)는
> tool 호출을 요구하지 않아 14b 로 성립한다. **하네스를 에이전틱으로 바꾸는 순간 이 전제가 깨진다.**

#### 9.4.1 ✅ tool-calling 관문 벤치 완료 — 3모델 실측 (2026-08-08)

하네스 `~/claude-workspace/bin/bench_toolcall.py`. 관문 4종:
**①단발호출**(구조화 방출) **②도구선택**(3개 중 라우팅) **③멀티턴**(도구 결과 되먹임 — 루프의 본체) **④억제**(헛호출 참기).

| 모델 | ① | ② | ③ | ④ | 판정 |
|---|---|---|---|---|---|
| **`35B-A3B IQ2_M`** | ✅ | ✅ | ✅ | ✅ | **4/4 — executor 가능** |
| `devstral:24b` (14GB, 신규) | ✅ | ✅ | ❌ | ✅ | **3/4 — 부분** |
| `qwen2.5-coder:14b` | ❌ | ❌ | ❌ | ✅* | **1/4 — 불가** (*호출 자체를 못 해 자동 통과) |

**🔴 `devstral:24b` 탈락 사유 — 재현 확인**(`temperature:0`, 동일 결과 2회):
프롬프트에 **형식/답변스타일 지시가 붙으면 도구 호출을 빠뜨린다.**
`"What is the weather in Seoul?"` → 호출 ✅ / `"...? Answer in one sentence."` → 호출 ❌,
대신 `"I'll check the weather for you."` 라고 **말만 하고 멈춘다** / `"Use the tool, then ..."` → 호출 ✅.
**에이전틱 하네스의 시스템 프롬프트는 형식 지시로 가득하므로 실전에서 계속 터진다.**
35B 는 **같은 프롬프트로 멀티턴을 통과**했다.

**→ §3 의 "코드 생성 모델 후보 재평가"에서 `devstral:24b` 는 executor 로 부적합.**
(코드 품질은 측정하지 않았다 — 첫 관문에서 걸렸다.)

#### 9.4.2 제안 — 역할을 쪼갠다 (**미검증 가설**)

보드에서 4관문을 다 통과하는 모델은 35B 뿐인데, 그 모델은 **코드 생성 시 API 환각**이 있다(리포트 25/02).

→ **35B = 에이전틱 드라이버(도구 오케스트레이션) / 14b = 코드 본문 생성기를 "도구"로 호출.**
각 모델의 강점을 유지하고, **14b 의 tool-calling 결함은 호출당하는 쪽이라 무관**해진다.

🔴 **보류 — 보드 1대로는 성립하지 않는다 (2026-08-08 실측).**
전환 비용을 제대로 재보니 기존 문서의 "36초"는 **14b 방향만 본 값**이었다:

| 호출 | 시간 | 전환 페널티 |
|---|---|---|
| 35B (전환) | **66.9s** / 재현 64.6s | ~64s |
| 35B (상주) | 2.7s | — |
| 14b (전환) | **37.5s** | ~36s |
| 14b (상주) | 1.4s | — |

**35B↔14b 왕복 1회 = 약 100초.** 드라이버가 코드 생성기를 태스크당 2번만 불러도 200초가
순수 적재로 나간다. ~~이 배치는 보드가 2대가 되기 전까지 착수하지 않는다.~~

##### ✅ **보류 해제 (2026-08-08 실측) — 2번째 엔드포인트가 보드가 아니라 RTX 3060 이었다**

해제 조건은 "보드 2대"였고 그건 **게임 머신을 내주는 자원 배분 결정**이었다. 그런데
**보조 윈도우 PC 의 RTX 3060 12GB** 가 그 자리를 대신할 수 있다는 것이 실측으로 확인됐다.
엔드포인트가 둘이면 **각자 다른 모델을 상주**시켜 전환 자체가 발생하지 않는다.

| 엔드포인트 | 상주 모델 | 근거 |
|---|---|---|
| BC-250 (192.168.0.43) | `35B-A3B IQ2_M` (12.28 GiB) | **35B 를 담을 수 있는 유일한 기계** — 통합 메모리 ~15.6 GiB |
| RTX 3060 (192.168.0.2) | `qwen2.5-coder:14b` (9.57 GiB) | 12GB. 14b 를 BC-250 보다 **23% 빠르게** 돌린다 |

**왕복 실측 (양쪽 pinned, 2회 반복):**

| | 35B 드라이버 | 14b 코드생성기 |
|---|---|---|
| 1회차 | 3.06s | 0.94s |
| 2회차 | 2.63s | 0.59s |

**왕복 1회 ≈ 3.6초 — 보류 사유였던 ~100초 대비 약 28배.** 게임 머신을 내주지 않고 해제됐다.

🔴 **성립 조건 3가지 (깨지면 이 배치도 깨진다):**
1. **3060 PC 는 에디터를 띄우지 않는다** — 사용자 확정: 빌드만 돌린다. 빌드는 CPU 중심이라
   VRAM 을 안 먹지만, 에디터를 띄우면 14b(9.57 GiB)와 경합해 CPU 로 흘러넘친다.
   실측 여유가 **257 MiB** 뿐이라 `num_ctx` 도 8192 가 상한이다.
2. **3080 메인 PC 는 엔드포인트가 아니다** — 10GB 라 14b 의 실제 점유 9.57 GiB + 데스크톱
   ~2GB 를 못 받는다. 게다가 에디터를 실제로 쓰는 기계다.
3. **상주 고정이 유지돼야 한다** — 현재는 요청 단위 `keep_alive:-1`(런타임 고정)이라
   Ollama 재시작/재부팅이면 풀린다. BC-250 유닛은 아직 `KEEP_ALIVE=30m` 이다(변경에 root 필요).
   → **브로커 헬스루프가 기동 시 의도한 상주를 재확립하는 쪽이 낫다** — 재부팅에도 자동 복구된다.

⚠️ **3060 에서 `KV_CACHE_TYPE=q4_0` 은 쓰지 말 것 (실측).** BC-250 에선 이득인 설정이
3060 에선 **VRAM 도 속도도 손해**다 — 모델은 1.07GB 줄지만 역양자화 버퍼가 ~900MB 를
도로 먹어 순절약이 200MB 뿐인데 생성이 **31.1 → 25.1 t/s (−24%)** 로 깎인다.
대역폭이 병목인 보드와 연산 여유가 있는 dGPU 의 차이다. **엔드포인트별로 튜닝이 다르다.**

#### 9.4.3 ✅ 보드 1대에서 되는 길 — gjc 의 **런타임이 아니라 계약**을 가져온다

`extragoal` 의 **"Custom — user-provided external reviewer command"** 레인은
**도구 호출을 요구하지 않는다.** 계약이 하나뿐이다 — *응답의 마지막 비어 있지 않은 줄이
정확히 `VERDICT: APPROVE` 또는 `VERDICT: REQUEST_CHANGES`, 누락·형식오류·타임아웃은 fail-closed.*

**→ tool-calling 이 안 되는 14b 도 리뷰어는 할 수 있다.** 실측(2026-08-08):

| 케이스 | 결과 |
|---|---|
| 버그 있는 diff (음수 클램프 누락) | ✅ `VERDICT: REQUEST_CHANGES` — 형식·판정 모두 정확 (47.5s, 적재 포함) |
| 정상 diff (`FMath::Clamp`) | ✅ `VERDICT: APPROVE` (1.1s, 상주) |

⚠️ **표본 2개짜리 장난감 케이스다 — 신호이지 증명이 아니다.** UE5 실제 diff 로 재측정할 것.

⚠️ **교차 계열 제약이 남는다.** extragoal 은 리뷰어가 작성자와 **다른 모델 계열**일 것을 요구한다.
14b 가 작성도 리뷰도 하면 계약 위반이다. 보드 1대에서 성립하는 조합은:

| 배치 | 작성자 | 리뷰어 | 평가 |
|---|---|---|---|
| **A (모토 부합)** | BC-250 14b — **기존 제약 생성 경로**(gjc 아님, tool 불필요) | 상용(agy→Claude) | ✅ **§4.3 3층 게이트가 이미 이 모양이다.** gjc 에서 가져올 것은 **verdict 계약의 형태**뿐이고, 그건 설정 변경 없이 층2 에 이식 가능 |
| B | 상용(윈도우 gjc) | BC-250 14b | ⚠️ 모토가 뒤집힌다(상용이 대량생산) |

**→ 결론: 보드 1대 동안은 gjc 런타임을 도입하지 않는다.
대신 §8.3 의 층2 검증을 `VERDICT:` fail-closed 계약으로 바꾼다** — 이게 지금 당장 얻을 수 있는 실익이다.

#### 9.4.4 ✅ 구현 완료 — `master/` 의 첫 코드 (2026-08-08)

| 파일 | 내용 |
|---|---|
| `master/verdict.py` | 판정 계약 — `contract_text()`(프롬프트에 붙일 지시문) + `parse_verdict()`(**모든 실패 경로가 차단으로 떨어진다**) |
| `master/layer2_verify.py` | 층2 검증기 — UE5/C++ 문법 프롬프트 + 백엔드 체인(`agy`→`claude`) |
| `master/test_verdict.py` | 계약·체이닝 테스트 **19건 전부 통과** |

**AgentTest 원본과 무엇이 달라졌나** (`worker/claude_spawn.py:739` `syntax_check`):

| | AgentTest | 이식판 |
|---|---|---|
| 응답 형식 | 응답 **아무 데서나** `{"ok":...}` JSON 탐색 | **마지막 비어 있지 않은 줄**이 정확히 `VERDICT: ...` |
| 파싱 실패 | `None` → 호출자가 **통과 처리** | 🔴 **차단**(`failure="malformed"`) |
| 백엔드 부재·타임아웃 | `checked=False, ok=True` → **통과** | 🔴 **차단**(`no_backend` / `no_output`) |
| 원본 docstring | *"fail-open, 인프라 부재로 제출 막지 않음"* | fail-closed |

**설계 판단 3가지:**
1. **백엔드 체이닝** — "응답이 없는 것"과 "판정을 못 낸 것"을 구분한다. 전자는 다음 백엔드로
   넘어가지만, **후자는 거기서 차단**한다. 계약을 어긴 검증기를 다음 백엔드가 구제하면 fail-open 이 되살아난다.
2. **장식 정규화** — `**VERDICT: APPROVE**`·백틱·인용부호·마침표는 벗겨내고 읽되 **경고를 남긴다.**
   유사 토큰(`VERDICT: APPROVED`, `VERDICT: OK`, `verdict: approve`)은 **전부 차단**한다.
3. **본문 되읊기 허용** — 판정 토큰이 본문에도 나오면 경고만 남기고 **마지막 줄을 권위로** 삼는다.
   계약 원문이 "the LAST non-empty line"이고, 지시문 되읊기는 흔한 모델 행동이라 그걸로 막으면 헛차단이 는다.

**실측 (agy 백엔드, 2026-08-08):**

| 입력 | 결과 |
|---|---|
| 문법 오류 3개(세미콜론·괄호·중괄호 누락) | ✅ `REQUEST_CHANGES` — **지적 3건 전부 정확** |
| 정상 코드 | ✅ `APPROVE` |

⚠️ **테스트가 실제 버그를 하나 잡았다** — `backends or BACKENDS` 로 썼더니 **빈 목록이 falsy 라
"백엔드 없음"이 조용히 기본 체인으로 바뀌었다.** 호출자가 백엔드를 동적으로 계산해 빈 목록이
나오면 fail-open 이 된다. `backends is None` 검사로 고쳤다.

---
