# 16 — 워커 지휘자 모드 (Claude / Codex) — 변경안

일감 [`#385`](http://192.168.0.57:8080/issues/385) · 실측 리포트 `56` ·
[중요] `#384`(마스터 **대화 세션** 인수인계)와 **별개 축**이다. 연결만 하고 묶지 않는다.

**요구** (사용자 2026-09-08): 마스터가 SSH 로 워커에 서브태스크를 맡길 때, **그 수행을
지휘하는 주체**를 Claude / Codex 중에서 고른다. 지휘자가 필요에 따라 제미나이·로컬 모델에
본문 작성을 맡기는 것은 **그 아래 역할**이다.

> [완료] **구현됐다** (2026-09-08). 아래 A~F 는 배선된 형태를 적는다.
> 상태는 **「구현 완료, 운영 반영·실제 파견 검증 대기」**다.

---

## 16.1 지금 구조 — 두 층이 섞여 있다

| | 지휘자 | 하위 작성 모델 |
|---|---|---|
| 어디서 도나 | **워커** (SSH) | **마스터** |
| 무엇을 하나 | 체크아웃을 읽고 판단하고 고친다 · 스킬을 따른다 | 텍스트만 만든다 |
| 코드 | `runner.py:285` · `infer.py:172` | `lanes.py:73` |
| 선택지 | **`claude` 하드코딩** | `codex → agy → 로컬` |

[중요] `ax-work` 스킬 §0 ②④ 가 이미 *"네가 오케스트레이션한다"* · *"대량 생성은
`codex`→`agy`→로컬에 위임하고 **너는 검증한다**"* 라고 적는다. **요구는 새 개념이 아니라
스킬에 적힌 것을 코드가 못 고르는 상태다.**

🔴 **정상 파견에는 지금 지휘자가 없다** — `infer.py:804-810` 은 레인이 기본이고 `run_worker` 는
골조를 못 읽었을 때의 폴백이다. **스위치만 만들면 평소 안 타는 경로를 바꾸게 된다.**

[주의] `lanes.py:75` 주석이 `AX_LANES` 환경변수를 약속하는데 **읽는 코드가 0건**이고,
`run_chain(lanes=...)` 인자를 `infer.py:811` 이 안 넘긴다. 죽은 약속이므로 이 축에서 함께 정리한다.

---

## 16.2 변경안

### A. 명령 생성을 한 자리로 모으고 갈래를 준다

`runner.worker_command()` 와 `infer.infer_command()` 는 지시문만 다른 같은 모양이다.
`agent_command(facts, task_id, files, *, mode, instruction)` 하나로 모은다.

    mode="claude"   cd <path> && claude -p --output-format json
                    --dangerously-skip-permissions "<instr>"
    mode="codex"    cd <path> && codex exec --json
                    --dangerously-bypass-approvals-and-sandbox -C "<path>" "<instr>" < /dev/null
                    (윈도우는 `< NUL`)

[완료] **권한 범위를 좁혔다** (실측 2026-09-08). 샌드박스만 바꿔 브로커 `curl` 로 판정:

    -s workspace-write                        파일 수정 O · 네트워크 X (curl rc=7)
    -s workspace-write + network_access=true  파일 수정 O · 네트워크 O (HTTP 401)  ← 채택
    -s danger-full-access                     둘 다 O — 디스크 전체가 열린다
    --dangerously-bypass-approvals-and-sandbox 둘 다 O — 샌드박스 자체가 없다

🔴 네트워크가 필요한 이유는 **위임**이다 — `ax-work` §0④ 의 로컬 LLM 위임은 브로커 HTTP 다.
그래서 **쓰기는 작업공간으로 묶고 네트워크만 여는** 가운데 값을 쓴다.

### B. 계측 파서를 갈래로

`_unwrap()`(`runner.py:139`)은 단일 JSON 전제다. codex 는 JSONL 이라 갈래가 필요하다.

    claude   {"result": …, "total_cost_usd": …, "usage": {…}}         (지금 그대로)
    codex    JSONL — 본문은 마지막 `item.completed` 의 `item.text`
                     (`item.type == "agent_message"`)
             토큰은 `turn.completed` 의 `usage`

매핑:

    input_tokens                 ← usage.input_tokens
    output_tokens                ← usage.output_tokens
    cache_creation_input_tokens  ← usage.cache_write_input_tokens
    cache_read_input_tokens      ← usage.cached_input_tokens
    total_cost_usd               ← 🔴 **없다**

🔴 [중요] **비용 미상을 0 으로 접지 않는다.** `Outcome.cost_usd` 는
`float(usage.get("total_cost_usd") or 0.0)` 이라 미상이 **「공짜」로 읽힌다.** 기존 계약
*"비어 있으면 모른다"*(`runner.py:105`)는 codex 에 안 맞는다 — usage 는 **있는데** 비용만 없다.
→ `usage["cost_unknown"] = True` 를 싣고, `cost_usd` 를 `Optional[float]` 로 바꾸거나
집계 쪽에서 미상을 **따로 센다.** *"계측 없이 분산이 이득인가를 논할 수 없다"*(`runner.py:283`)가
그 자리의 근거다.

[중요] `_unwrap` 의 관대함은 유지한다 — *"JSON 이 아니어도 실패로 보지 않는다. 계측이 없는
것과 작업이 실패한 것은 다르다."* 판정은 어느 쪽이든 **마커**로 읽는다.

### C. 지시문은 갈래를 만들지 않는다

실측(리포트 56 ⓒ): codex 가 `.claude/skills/ax-work/SKILL.md` 를 **찾아 읽고**, 한글 규칙을
인용하며 `RESULT: BLOCKED` 로 멈췄고, 설정을 주니 층1 기준(`[PSEUDO]` 0 · `[DOC]` 보존 ·
선언 동결)을 만족하며 구현했다. → **`INSTRUCTION` 을 도구별로 가를 이유가 없다.**

[주의] 다만 **자동 로드가 아니라 탐색**이다. 배달이 스킬을 체크아웃에 두므로 지금 배선 그대로
성립하지만, 「자동으로 실린다」고 적으면 안 된다.

### D. 커밋 경계는 그대로

지휘자는 git 을 만지지 않고, `wcommit` 이 마스터에서 결정적으로 커밋한다. 되읽기·층1 도 그대로.
**게이트는 하나도 안 줄어든다** — 누가 썼든 디스크 상태로 판정한다.

### E. 🔴 레인과의 관계 — 여기가 결정 자리다

세 안이 있고, **비용과 정본 충실도가 반대로 간다.**

    ① 대체    골조가 있어도 지휘자를 돌린다. 레인은 지휘자가 **자기 안에서** 부른다
              (`ax-work` §0④ 가 이미 그렇게 지시한다)
              + 정본 ⑸ 에 가장 가깝다 — 워커가 오케스트레이션한다
              − 조각마다 지휘자 토큰이 든다. 지금 레인은 마스터에서 텍스트만 만들어 싸다

    ② 병존    `mode ∈ {lane, claude, codex}`. `lane` 은 지금 그대로
              + 기본값을 `lane` 으로 두면 **운영 무변화**이고 되돌리기가 값 하나다
              + A/B 를 실측할 수 있다 (①은 ②의 한 값으로 도달 가능)
              − 경로가 둘이라 「어느 쪽으로 돌았나」를 로그가 반드시 밝혀야 한다

    ③ 폴백만  지금처럼 골조를 못 읽을 때만. 스위치는 그 폴백의 주체만 고른다
              + 가장 작다
              − **요구를 거의 만족하지 않는다** — 평소에는 지휘자가 안 돈다

🔴 **② 로 결정됐다** (사용자 2026-09-08): *"lane / claude / codex 를 명시적으로 선택하게 하고,
선택한 모드가 정상 파견 경로에 적용되도록 구현하면 돼. 기존 lane 은 비교·복귀용으로 남길 수 있어."*

[중요] **기본값은 아직 결정되지 않았다** (같은 날 정정) — 선택 기능을 요구한 것과 기본값을
정한 것은 다르다. 코드의 상수 이름이 `_UNDECIDED_DEFAULT` 인 이유가 그것이고, 값은 **현재
동작(레인) 유지**다. 사람이 정하면 이름과 값을 함께 바꾼다.

**적용 시점** (실측): 모드는 `infer.py:810` 의 `llm()` 안에서 **조각마다 파견 직전에** 읽는다.
→ 변경은 **다음 조각부터**이고 이미 SSH 가 나간 조각에는 소급되지 않는다. 배치를 고정하려면
`run_many(mode=...)` 로 명시한다(출처 `arg`). 우선순위는 **인자 > `AX_WORKER_MODE` > 저장 상태
> 현재 동작**이고, 조회가 **출처를 함께** 돌려준다.

### F. 모드가 어디에 저장되나

[중요] **MCP 와 스킬은 양자택일이 아니다** (사용자 정정 2026-09-08): *"서버에는 모드 조회·변경
기능을 한 벌 두고, 양쪽 스킬이 그것을 호출하면 네가 요청한 사용 방식이 돼."*

    서버 한 벌   `get_worker_mode_tool` · `set_worker_mode_tool`  (`master/projects/mcp_server.py`)
                 정본 로직은 `master/work/mode.py`
    스킬 한 벌   `master/skills/ax-mode` — `~/.claude/skills` 와 `~/.codex/skills` 양쪽에서
                 **링크로** 본다. [완료] 실측 2026-09-08: Codex 새 세션이 지시 없이 집어
                 「lane · claude · codex」를 답했다 → `~/.codex/skills/` 로 사용자 스킬이 선다

값의 수명: 저장 상태는 **재부팅을 넘는다**(`~/.cache/ax-dispatch/mode.json`).
1회 실행은 `AX_WORKER_MODE`, 배치 고정은 인자다.

---

## 16.3 순서

    [완료] 권한 범위 좁히기 · B 계측 파서 · A 명령 갈래 · E 결정(②) · F 표면(도구+스킬)
    [완료] 종단 검증 — `.43`·`.2` 양쪽에서 모드 → 명령 → SSH → `parse_result` 까지
    [남음] 운영 유닛 반영 · **실제 큐 파견 검증** · 기본값 결정(사람)

[주의] 죽은 `AX_LANES` 주석 정리는 **아직 안 했다** — `lanes.py:75` 가 여전히 없는 환경변수를
약속한다. 지휘자 모드(`AX_WORKER_MODE`)는 세 경로를 **전부 실제로 읽는 코드**로 넣었다.

[중요] 각 단계에 **실물 한 번**을 붙인다 — 이 저장소는 유닛이 다 통과한 채로 두 번 태웠다.

---

## 16.4 실증 결과 (2026-09-08) — 파견까지 통과, 층1 에서 멈췄다

**통과** — 모드가 실제 큐 파견에 실렸다. 파견 로그:

    01:46:20  안 건다 — base 가 원격에 없다              등재 트리거, 설계대로 거절
    01:46:58  파견 시작 — pending 1건 · base e37b8ece
    01:47:11  [subbranch] f4db3ad4 → …/r1/f4db3ad4 신설
    01:47:14  [mode] f4db3ad4 지휘자=codex (출처 state) — 워커에서 실행한다
    01:48:39  [wcommit] 층1 이 막았다 — 커밋하지 않는다

**막힌 것** — `[PSEUDO]` 잔재로 층1 차단. **커밋은 안 됐다**(조각 브랜치가 base 그대로).

원인 조사에서 **내 첫 진단이 틀렸다**: *"체크아웃에 `ax-work` 가 없다"* → 스킬은 설계상
**홈**에 간다(`base="home"`). 파일은 정상 배달돼 있었다. 실제 원인은 **도구마다 자동 로드
경로가 다르다**는 것이고, 실측이 갈랐다 — 읽기는 rc=0 인데
*"ax-work is not listed among my available skills"*. → `spec.SKILL_HOMES` 로 각 도구 경로에
같은 한 벌을 배달하게 고쳤다(`3b7c536`).
[주의] **그것이 그 실패의 직접 원인인지는 재시도로 확인해야 한다.**

## 16.5 🔴 발견한 별도 결함 — 계측이 사라진다

`wcommit.py:267` 이 `rc, out = llm(...)` 의 **`out` 을 rc≠0 일 때 사유 문자열로만 쓰고 버린다.**
`Committed` 에 계측 필드가 없고 `Response(usage=…)` 는 옛 경로(`infer_task`)에서만 채워진다.

    실측   스풀 f4db3ad4.json → usage: {} · tail: ""   (codex 가 85초 돌았는데 0)

🔴 **층1 차단 때문이 아니다 — 정본 ⑸ 경로는 성공해도 계측을 회수하지 않는다.** 레인 모드도
같다(`llm` 이 합성 문자열을 돌려준다). `--output-format json` 을 붙여 온 이유
(*"계측 없이 분산이 이득인가를 논할 수 없다"*)가 이 경로에서 무력화돼 있다. → 별도 일감.

## 16.6 지휘 상태 표면 — `.33` 에서 바꾸고 웹에서 본다 (2026-09-08 추가)

사용자 요구: *"`.33` 에서 변경을 처리할 수 있고, 웹UX 에서 상태를 보면 좋겠는데?
지금 마스터가 코덱스가 주관하는지 아니면 클로드가 주관하는지"*

    master/work/conductor.py          담당 기록 + 워커 모드 조회 (원자적 교체)
    master/projects/control_route.py  요청자 인증을 거치는 `/control/*` 3종
    master/webui/orchestration.py     `/cluster` 의 「지휘 상태」 카드
    MCP                               `.33` 요청자 3종 + 마스터 2종 · 테스트 8건

🔴 [중요] **두 상태를 섞지 않는다.**

    마스터 담당    claude / codex      **마지막으로 기록된** 지휘자.
                                      프로세스 생존 판정도, 잠금도, 세션 실행·종료도 **아니다**
    워커 실행 모드  lane/claude/codex   다음 **조각**부터 적용되는 전역 설정.
                                      실행 중인 조각에 소급되지 않는다 ·
                                      프로젝트별·워커별 선택은 **없다**

**운영 서비스 실측** (유닛이 아니다):

    GET  /control/orchestration  요청자 토큰   200
    GET  /control/orchestration  무인증        401
    POST /control/worker-mode    워커 토큰     403
    /cluster (무인증 공개)        카드 렌더 · `/home/sim` 0건
    check NS                     3대 전부 OK · 마스터 HEAD 와 같다
    ax-projects 재기동            ExecMainStartTimestamp 22:37:21 → 23:46:26

[중요] **쓰기를 `/api/v1` 아래 두지 않았다** — 그쪽은 8103 에서 무인증 공개다.

🔴 [중요] **예외 문자열을 무인증 화면에 올리지 않는다** (결함 1건, 배포 전에 고쳤다).
`orchestration.py` 가 `str(OSError)`·`note` 를 그대로 실었는데 거기엔 **절대 경로**가 들어 있다 —
`api_history` 가 본문·절대 경로를 의도적으로 빼는 것과 **같은 자리**다. 고정 문구로 바꾸고
**두 경로를 주입 실증**했다.

## 16.7 남은 것

    [완료] ① 재배달 → ② `check` (3대 OK) → ③ ax-projects 재기동 (2026-09-08, 승인받음)
    [남음] ④ 실증 work 재시도 — 아래 §16.8
    [남음] ⑤ 계측 결함 → **`#387` 로 분리됨**  ⑥ 기본값 결정 (사람)  ⑦ 운영 파견 전환 (사람)

[주의] **새 work 생성 금지 · 미병합 브랜치 삭제 금지** (사용자 지시 2026-09-08).
남은 브랜치 2건은 `#385` 노트에 목록으로 있다.

## 16.8 🔴 재시도 경로 — 있는데 **이 실패엔 못 쓴다** (2026-09-08 규명)

종전 서술 *"지원되는 재시도 경로를 못 찾았다"* 는 **절반만 맞았다.**

    있다   POST /api/v1/tasks/{task_id}/reverify      (task_queue/server.py:392)
    구현   logic_lifecycle.py:291 reverify_task
           status 를 `failed` → **`submitted`** 로만 뒤집는다
    전제   "커밋이 이미 올라가 있고 verify-loop 가 다시 본다"

🔴 **우리 실패는 커밋 *전*이다** — 층1 이 `wcommit` 에서 막았고 조각 브랜치는 base 그대로다.
`submitted` 로 만들면 **없는 산출물을 있다고 적는 것**이다.
`failed → pending`(재파견) 경로는 큐에 **없다** (failed 전이는 `reverify` 하나뿐).

→ 갈래 둘, **사람이 정한다**:

    ⓐ 재파견 경로를 새로 만든다      큐 API 추가 = 코드 변경. 가장 곧지만 표면이 는다
    ⓑ `cancel` 후 같은 work 에 round 2  「새 work 생성 금지」에 **걸리지 않는다**(같은 work).
                                     다만 브랜치가 `task/<work>/r2/<조각>` 으로 새로 나고
                                     r1 잔재 2건은 그대로 남는다

[중요] **인과는 아직 안 섰다** — 스킬 배달 경로를 고쳤지만(`3b7c536`), 그것이 층1 차단의
원인이었는지는 **재시도로만** 확인된다 (사용자 정정: *"스킬이 안 보였다는 사실과, 그것이
그 실패를 일으켰다는 판정은 다르다"*).
