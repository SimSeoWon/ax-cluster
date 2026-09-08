# 57 — Codex → Claude 인계 (한도 소진) + 지휘 상태 표면

작성 2026-09-08 · 일감 [`#384`](http://192.168.0.57:8080/issues/384) §15.6 ④⑤ ·
[`#385`](http://192.168.0.57:8080/issues/385) · 커밋 `54a0669` · `16d751a`

---

## 57.1 이 세션이 실제로 한 것

사용자가 *"코덱스쪽에서 주도해서 진행해볼게"* 로 Codex 에 지휘를 넘겼고, Codex 가
`#385`(워커 지휘자 모드)를 이어받아 지휘 상태 표면을 구현하던 **도중에 한도가 소진됐다**
(*"You've hit your usage limit … Sep 9th, 2026 3:58 AM"*). 사용자가 미리 지시해 둔 대로
(*"코덱스 토큰 거의 없으니 이거 작업 끝나면 클로드에서 이어받아 처리하면 될 것같아"*)
Claude 가 이어받아 **커밋·배달·재기동까지 마감**했다.

🔴 **`#384` §15.6 ④(Codex → Claude)와 ⑤(중단 복구)를 실제로 돈 것이다** — 계획은
*"실제 한도를 소진시키지 않고 예고 없는 종료를 **모사**한다"* 였는데 **모사할 필요가 없었다.**

**결과: 잃은 변경 0 · 중복 작업 0 · 재설명 0.**

## 57.2 받는 쪽이 한 대조 — 「기록을 믿지 않는다」가 실제로 돈 자리

`orchestrator-rules.md` §2.4 대로 HEAD·dirty·이슈·프로세스를 **직접** 봤다.

    HEAD·dirty     `1d2ab49` · 미커밋 9파일 (신규 4 · 수정 5)
    프로세스·포트   임시 HTTP 서버 잔재 **없음** — Codex 가 정리하고 끊겼다
    운영 상태       `mode.json` 무변경(2026-09-08T01:45:15 그대로) · 서비스 6종 active
    테스트          **직접 재실행**: test_orchestration_control 8/8 · test_auth 60/60 ·
                   test_client_mcp 147/147 · test_viewer 79/79 — 전부 재현됐다
    인증 층위       `BearerAuthMiddleware` 가 `ControlApp` 을 **바깥에서** 감싼다 ·
                   `/control/*` 는 `public_prefixes`·`OPEN_PATHS` 에 없고 `REQUESTER_SCOPE` 에만 있다

[중요] **Codex 의 보고는 전부 사실과 일치했다.** 어긋난 곳이 없었다는 것이지, 대조가
불필요했다는 뜻이 아니다 — §5 의 전제는 **기록 일반의 성질**이지 도구 불신이 아니다.

## 57.3 🔴 이 교대에서 드러난 것 — 진입 문서 결함의 **재발**

Codex 가 `master.client plan NS` 에서 `AX_PROJECTS_ROOT` 미설정으로 멈췄다(§1.1 준수 —
고치지 않고 보고했다). 원인을 쟀더니 **도구 차이가 아니었다**:

    셸 프로파일           `~/.bashrc`·`~/.profile`·현재 셸 → **0건**
                         = **Claude 도 안 주면 똑같이 실패한다**
    Claude 가 안 걸린 이유  `~/.claude/settings.local.json` 의 허용 규칙 ~10건이
                         `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 **명령 접두에 통째로** 박아 뒀고,
                         `ax-cluster/CLAUDE.md:321` 이 그 형태로 명령을 적는다
    🔴 AGENTS.md         `master.client`·`venv/bin/python`·`AX_PROJECTS_ROOT` **전부 0건**

= 2026-09-08 에 이미 잡았던 **「두 진입 파일은 각각 자족적이어야 한다」의 재발**이다.
`AGENTS.md` 를 **홈 지침** 기준으로만 채우고 **저장소 `CLAUDE.md` 의 명령 블록**은 안 옮겼다.

🔴 **더 값이 큰 자리는 MCP 미배선이다.** `~/.codex/config.toml` 은 93바이트,
`[mcp_servers]` **0건**이다. 마스터 호출 경계는 **이미 MCP** 이고 그 서버는 systemd 아래에서
환경을 갖춘 채 돈다. Claude 는 `mcp__ax-projects__*` 로 불러 그 변수를 만질 일이 **없고**,
Codex 는 MCP 가 없어 **생 셸로 내려가서** 전제에 걸렸다.
→ 지침을 더 쌓을 것이 아니라 **연결할 일**이다. (미착수)

## 57.4 래퍼(RHI 식) 질문 — 원전 대조

사용자 질문: *"언리얼에 RHI 처럼 코덱스, 클로드 이런식으로 래핑하는게 좋을가?"*

「만들기 전 3문」 ①(원전에 있나)을 돌렸다. **있다. 다만 클래스 계층이 아니다.**

    ~/AgentTest/worker/worker.py:78         _VALID_WRITE_BACKENDS = ("", "local_llm", "agy", "claude")
                                            문자열 enum · 모르는 값은 경고 후 거절
    ~/AgentTest/worker/claude_spawn.py:243  call_llm(prompt, cfg, cwd, ..., force_kind)
                                            **함수 하나**가 라우팅 · `_call_cli_llm` 안에서 kind 분기
                                            폴백은 **한 겹만** (로컬 LLM → claude)

🔴 [중요] **판정은 어댑터에 넣지 않는다.** 원전 주석 그대로:
*"출력의 `TASK_COMPLETE` 는 보조 신호, 최종 판정은 `_validate_disk_after_agent`"*.
우리 `wcommit` 되읽기·층1 이 그 자리다.

→ 우리 `agent_command(mode=...)` + 갈래 파서가 **이미 그 모양**이다. Codex 의 결론
(*"얇게 감싸는 것"* · *"어댑터와 폴백 정책을 분리"* · *"층1 차단과 도구 장애를 구분"*)은
셋 다 원전과 일치한다. **새로 만들 것이 적다.**

[중요] `AX_PROJECTS_ROOT` 는 **이 축이 아니다** — 래퍼로 감싸면 §57.3 의 구멍을 **가린다**.

## 57.5 지휘 상태 표면 (`54a0669`)

    master/work/conductor.py          담당 기록 + 워커 모드 조회 (원자적 교체)
    master/projects/control_route.py  요청자 인증을 거치는 `/control/*` 3종
    master/webui/orchestration.py     `/cluster` 의 「지휘 상태」 카드
    master/test_orchestration_control.py  8건
    MCP                               `.33` 요청자 3종 + 마스터 2종

🔴 [중요] **두 상태를 섞지 않는다** — 화면과 도구 설명이 둘 다 그렇게 적는다:

    마스터 담당    claude / codex      **마지막으로 기록된** 지휘자.
                                      생존 판정도 잠금도 세션 실행·종료도 **아니다**
    워커 실행 모드  lane/claude/codex   다음 **조각**부터 적용 · 실행 중인 조각엔 소급 안 됨

**운영 서비스 실측** (유닛이 아니다 — 「돌려서 확인한다」):

    GET  /control/orchestration  요청자 토큰   200
    GET  /control/orchestration  무인증        **401**
    POST /control/worker-mode    워커 토큰     **403**
    /cluster (무인증 공개)        카드 렌더 · `/home/sim` **0건**
    check NS                     3대 전부 OK · 마스터 HEAD 와 같다 (직전엔 3커밋 뒤 + dirty)
    ax-projects 재기동            ExecMainStartTimestamp 22:37:21 → 23:46:26
    재기동 뒤                    MCP 도구 2종이 **실제로 등장**했다 — 배선이 산 증거

### 🔴 Claude 가 고친 결함 1건 — 무인증 화면의 절대 경로

`orchestration.py` 가 `str(OSError)` 와 `note`(예외 문자열이 들어오는 자리)를 **그대로**
화면에 실었다. 8103 은 `/api/v1` 까지 무인증 공개라(실측 2026-08-25) 읽기 실패 한 번에
`[Errno 13] Permission denied: '/home/sim/.cache/ax-dispatch/conductor.json'` 같은 것이 찍힌다.
`api_history` 가 본문·절대 경로를 의도적으로 빼는 것과 **같은 자리**다.

고정 문구로 바꾸고 **두 경로를 주입 실증**했다(`note` 경로 · 예외 경로 모두 `/home/sim` 0건).

[중요] 이것은 **유닛 8건이 다 통과한 채로** 남아 있던 것이다. 이 저장소가 두 번 태운 그
부류(§「유닛이 다 통과한 채로」)와 같고, 잡은 방법도 같다 — **실물로 한 번 그려 봤다.**

## 57.6 🔴 재시도 경로 — 있는데 이 실패엔 못 쓴다

종전 기록 *"지원되는 재시도 경로를 못 찾았다"* 는 **절반만 맞았다.**

    있다   POST /api/v1/tasks/{task_id}/reverify   (task_queue/server.py:392)
    구현   logic_lifecycle.py:291 — `failed` → **`submitted`** 로만 뒤집는다
    전제   "커밋이 이미 올라가 있고 verify-loop 가 다시 본다"

🔴 우리 실패는 **커밋 전**이다(층1 이 `wcommit` 에서 막았고 조각 브랜치는 base 그대로).
`submitted` 는 **없는 산출물을 있다고 적는 것**이 된다. `failed → pending` 은 큐에 **없다**.
→ 갈래 둘(ⓐ 재파견 경로 신설 ⓑ `cancel` 후 같은 work 에 round 2)이고 **사람이 정한다**.
상세: `docs/16-worker-orchestrator-mode.md` §16.8.

## 57.7 이번에 바로잡은 수치

`README.md` 의 MCP 도구 **「26종」** → **37종**. 두 방법으로 재서 일치시켰다:
`@mcp.tool()` 데코레이터 37개 · 이 세션에 실제로 붙은 도구 37종.
[주의] 리포트 `54`·`55` 의 **33종**은 틀린 값이 아니라 **그때의 값**이다 —
워커 지휘자 모드 2종(`f2cd6a2`)과 지휘 상태 2종(`54a0669`)이 들어와 33 + 2 + 2 = 37.

## 57.8 남은 것

    `#384`  ⑥ 종결 — 두 방향 인계의 **시간·추가 설명량** 계량. 그 전엔 닫지 않는다
            Codex MCP 연결(`config.toml`) — 미착수, §57.3 이 근거
    `#385`  실증 재시도(§57.6 의 ⓐ/ⓑ 결정) · 기본값 결정(지금 저장값은 실증용 `codex`) ·
            운영 파견 전환
    `#387`  파견 계측이 사라진다 — 정본 ⑸ 경로가 성공해도 usage 를 회수하지 않는다
