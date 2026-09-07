# 54 — 지휘 교대 ① 조사: Claude 쪽 지침·기억·스킬·훅·MCP 목록화

작성 2026-09-07 · 일감 [#384](http://192.168.0.57:8080/issues/384) (마일스톤 6) ·
설계 `docs/15-orchestrator-handoff.md` §15.6 ①

역할 분담(사용자 2026-09-07): **Claude 가 ① 조사, Codex 가 자기 쪽 실측.** 이 문서는
Claude 쪽 실물만 적는다. **Codex 접근 가능 여부는 판정하지 않고 「미확인」으로 남긴다.**
문서를 먼저 만들면 실제로 지원되지 않는 기능까지 공통 규칙으로 적게 되므로, ②는 이 조사와
Codex 실측을 합친 뒤에 쓴다.

---

## 54.1 Claude 세션이 마스터 `.57` 에서 실제로 로드하는 것

전부 실측(파일 존재·설정 내용 확인). 「추정」은 없다.

### ⓐ 지침 (자동 로드)

| 실물 | 경로 | 크기/형태 |
|---|---|---|
| 세션 지침 | `/home/sim/CLAUDE.md` → **심볼릭 링크** → `~/ax-cluster/machines/sim-desktop.md` | 34,615 B |
| 상세 분리본 | `machines/sim-desktop.d/` · `win-main-33.md` · `win-worker-2.md` · `bc250-1.md` · `llm-fitness.md` | 참조 시 로드 |
| 저장소 작업 지침 | `~/ax-cluster/CLAUDE.md` | 저장소 안에서 작업할 때 |
| 트윈별 지침 | `ax-cluster/{ModularStage,NS}/repo/CLAUDE.md` | 프로젝트별 |

[중요] `AGENTS.md` 는 **어디에도 없다** (`find` 전수 0건). Codex 진입점은 아직 존재하지 않는다.

### ⓑ 기억 (Claude 전용 저장소)

`~/.claude/projects/-home-sim/memory/` — **29개 파일 + 색인 `MEMORY.md`**.
색인만 매 세션 자동 로드되고, 본문은 관련될 때 끌어온다.

    type=feedback   13건   작업 방식에 대한 사용자 지시
    type=project     8건   진행 중 작업·목표·제약
    type=reference    1건   외부 자료 포인터
    type=user         2건   사용자 프로필
    (frontmatter 에 type 이 없는 옛 형식 3건 포함)

### ⓒ 스킬

| 이름 | 실체 | 비고 |
|---|---|---|
| `distribute` | `~/.claude/skills/distribute` → **심볼릭 링크** → `ax-cluster/master/skills/distribute` | 저장소가 정본 |
| `debate` | `~/.claude/skills/debate` → **심볼릭 링크** → `ax-cluster/master/skills/debate` | 저장소가 정본 |
| 공식 마켓플레이스 | `~/.claude/plugins/marketplaces/claude-plugins-official` (스킬 31개) | 범용, 클러스터와 무관 |
| 요청자·워커 스킬 6종 | `master/client/skills/{ax-request,ax-review,ax-advance,ax-work,ax-ontology,ax-infer}` | **마스터 세션에 안 붙는다** — `.33`/워커로 배달되는 자산 |

[중요] 마스터 세션이 쓰는 스킬 2개는 **둘 다 저장소 안이 정본이고 홈은 링크뿐**이다.
→ 도구가 바뀌어도 내용은 저장소에 남는다. 옮겨야 할 것은 **파일이 아니라 「어떻게 발동되는가」**다.

### ⓓ 훅 — **마스터에는 하나도 없다**

    ~/.claude/settings.json          hooks 키 0건 (model/theme/tui/permissions 7개뿐)
    ~/.claude/settings.local.json    hooks 키 0건 (permissions.allow 583개)
    ~/.claude/hooks/                 디렉토리 없음
    ax-cluster/.claude/              디렉토리 없음

Claude Code 훅은 **요청자 `.33` 만** 받는다 — `master/client/spec.py:354 managed_hooks_for()`
가 `role == "requester"` 일 때만 `MANAGED_HOOKS` 를 낸다. 그 셋은
`PostToolUse(Edit|Write)→domain_hint.py` · `SessionStart(startup|resume|clear)→pending_works.py` ·
`UserPromptSubmit→pending_works.py`.

🔴 [중요] **그래서 마스터에는 「새 세션에게 무언가를 자동으로 고지하는 층」이 존재하지 않는다.**
`.33` 이 「리뷰 대기」를 매 턴 고지받는 구조를 마스터는 안 갖고 있다. 인수인계 기록을 만들어도
**새 지휘자가 스스로 읽으러 가지 않으면 아무 일도 일어나지 않는다** — 이것은 Codex 만의 문제가
아니라 **지금 Claude 도 마찬가지**다. ②에서 다뤄야 할 설계 구멍이다.

[주의] 이것과 **git 훅은 다른 종류다.** `ax-install-hook`(→ `master.events.install_hook`),
bare 의 `post-receive.d/ax-index`, 트윈의 `pre-push` 가드는 **도구와 무관하게 돈다.**
누가 지휘하든 영향받지 않는다.

### ⓔ MCP

    ax-projects   HTTP   http://192.168.0.57:8103/mcp   Authorization: Bearer <토큰>
    선언 위치     ~/.claude.json 의 전역 mcpServers (Claude 전용 파일)
    도구 수       33종 (register_work · search_context · 온톨로지 편집·조회 등)
                  [정정] 초판에 35종으로 적었다 — 실제로 세면 33종이고,
                  Codex 의 `tools/list` 실측(리포트 55)도 33종이다

[중요] **stdio 가 아니라 HTTP 다.** 서버는 도구 중립이고, 붙는 쪽 설정만 도구별이다.
`~/.codex/config.toml` 에는 지금 `[mcp_servers]` 항목이 **없다**(현재 내용은
`projects."/home/sim".trust_level = "trusted"` 와 TUI 설정뿐).

[주의] 토큰 값은 여기 적지 않는다. **위치만**: `~/.claude.json` 전역 `mcpServers` ·
작업장의 `.mcp.json` · `.ax/token` · 역할 스코프 토큰은 `master/auth.py` 가 발급.

---

## 54.2 분류 — 무엇을 공용으로 옮기고, 무엇이 도구 전용인가

### Ⓐ 공용으로 옮길 **사용자 결정** (도구와 무관하게 지켜야 함)

기억·지침에 흩어져 있으나 **내용은 Claude 의 기능이 아니라 사용자의 결정**이다.
`docs/orchestrator-rules.md` 로 옮길 후보. 괄호는 현재 근거 위치.

| 결정 | 현재 위치 |
|---|---|
| 커밋·푸시는 **매번 승인**받고 실행 | 기억 `git-commit-needs-approval` (사용자 2026-08-14) |
| 사람 게이트는 **둘** — ⑺ 전진(`ax-advance`)과 finalize(`main` 머지) | `sim-desktop.md` · 정본 7단계 |
| **실패는 고치는 자리가 아니라 보고하는 자리** (rc≠0·차단·예외 → 멈춤) | `sim-desktop.md` · 기억 `judgment-gap-observable-rules` |
| **지시받은 대상 밖의 파일은 건드리지 않는다** | 같음 |
| **사용자가 세션에 있으면 추측을 적립하지 않고 묻는다** | 같음 |
| **만들기 전에 원전(`~/AgentTest`)을 읽는다** · 원전은 **수정·푸시 금지** | `sim-desktop.md` · 기억 `ax-cluster-repos` |
| 만들기 전 3문: ①원전에 있나 ②이미 잡는 게 있나 ③오탐이면 뭐가 죽나 | 기억 `verify-by-running-not-reading` |
| **실증은 깨끗한 상태에서만** — 실패가 남은 채 이어가지 않는다 | 기억 `live-test-starts-clean` |
| 작성 레인 `codex → agy → 로컬`, 검토 레인 `agy → claude` (교차 계열) | 기억 `agent-lane-priority` · `lanes.py` |
| 「클러스터 작업」 발화로 **파견을 스스로 발동하지 않는다** | 기억 `cluster-work-means-redmine` |
| 기록 삼분할 — **레드마인이 항목의 정본**, 리포트는 저장소 안, 마일스톤은 서술 | 기억 `cluster-work-journal` · `docs-stay-concise` |
| 레드마인 상태 전이: **분산 작업만 `.33`**, `[AX]` 인프라 일감은 마스터가 닫는다 | 기억 `redmine-status-belongs-to-33` |
| 긴 작업은 **단계마다 끊어 보고** | 기억 `long-work-needs-progress-notice` |
| 권한 필요한 일은 **지휘자가 직접 처리**(사용자에게 명령을 떠넘기지 않는다) | 기억 `sudo-privilege-handling` |
| `~/CLAUDE.md` 는 **심볼릭 링크** — 일반 파일로 덮지 말 것 | 기억 `cluster-work-journal` |
| **사용자와의 대화는 한국어** | `sim-desktop.md` |

[주의] `claude-docs-in-english`(지침 문서는 영문으로) 는 **토큰 비용 근거**라 Codex 에도
같은 논리가 서지만, 「2.7배」는 Claude 측 실측이다. 공용으로 적되 **근거를 도구 하나의
실측으로 명시**한다.

### Ⓑ Claude 전용 — 그대로 옮길 수 없는 것

| 항목 | 왜 전용인가 |
|---|---|
| `~/.claude/projects/-home-sim/memory/` 기억 29건 | Claude 고유 저장소·자동 로드 계약. Codex 는 `~/.codex/memories_1.sqlite` 라는 **별도 저장소**를 쓴다 — 서로 안 읽는다 |
| `settings.local.json` 의 **permissions.allow 583개** | Claude 의 승인 모델 전용. Codex 는 샌드박스/승인 정책이 다르다 — **이전 불가, 재구축 대상** |
| 서브에이전트 유형 (`Explore` · `Plan` · `general-purpose` · `fork`) | Claude Code 고유. §15.2 가 이미 「실행 ID 이전 불가」를 전제 |
| `MANAGED_HOOKS` 3종 (`.33`) | Claude Code 훅 계약(`PostToolUse`/`SessionStart`/`UserPromptSubmit`). Codex 동등물 미확인 |
| `model: opus[1m]` · `tui` · `theme` | 도구 설정 |
| 마켓플레이스 스킬 31종 | 클러스터 업무와 무관 |

### Ⓒ 도구 무관 — 어느 쪽이 지휘하든 그대로 도는 것

- **git 훅** — bare `post-receive.d/ax-index`, 트윈 `pre-push` 가드, `ax-install-hook`
- **AX 서비스** — `ax-task-queue`(8101) · `ax-broker`(8102) · `ax-projects`(8103) ·
  `ax-indexer` · `ax-status.timer` (systemd 가 돌린다, 대화 세션과 무관)
- **파견 배선** — `ax-dispatch.path` · `~/.cache/ax-dispatch/hold.json` 의 보류(재부팅을 넘는다)
- **레드마인**(8080) · **Gitea** — 정본 저장소
- **스킬 2종의 내용** — 저장소 안이 정본이고 홈은 링크
- **MCP 서버 자체** — HTTP 엔드포인트라 붙는 쪽만 다르다

🔴 [중요] **교대가 멈추는 것은 대화뿐이다.** §15.4 마지막 문단과 같은 결론이 실물로 확인됐다 —
「세션이 끝났으니 작업도 멈췄다」고 가정하면 안 된다.

---

## 54.3 이번 조사에서 나온 것

**① 마스터에 고지 층이 없다** (54.1 ⓓ). `.33` 은 매 턴 고지받는데 `.57` 은 그런 층이 없다.
인수인계 파일을 만들어도 **새 세션이 스스로 읽지 않으면 안 보인다.** ②의 설계 항목.

**② Claude 기억 안에 이미 모순이 있다 — 기억을 인계 정본으로 쓰면 안 된다는 실증.**
`ns_pipeline_first_run_state.md` 의 본문은 *"등재 완료 … 다음은 `.33` 이 골조 push"* 인데,
같은 기억의 색인 줄은 *"2026-08-30 NS 를 전부 지웠다 · 되살리지 말 것"* 이다. 본문이
지워지기 **전** 상태로 굳어 있다. `pipeline_redesign_axis.md` 도 description 이
*"실증은 아직 시작 전"* 인 채로 남아 있다(본문은 축이 닫혔다고 적는다).
→ §15.4 ④ *"기록의 완료 주장을 그대로 믿지 않는다"* 는 **Codex 를 못 믿어서가 아니라
기록 일반의 성질**이다. 공용 규칙에 그 근거로 적는다.

**③ 색인 누락 1건.** `ax_cluster_solo_direction.md` 가 `MEMORY.md` 에 없다 — 파일은 있는데
자동 로드 색인에서 빠져 있어 사실상 안 읽힌다. (내용: 이 클러스터는 팀 인프라가 아니라
1인이 집의 여러 컴퓨터를 묶는 것.) **Ⓐ 후보이면서 지금 Claude 도 놓치고 있던 결정.**

**④ Codex 는 이미 마스터에서 돌고 있다.** `~/.codex/` 존재(`auth.json` · `config.toml` ·
`history.jsonl` · 자체 스킬 6종 · `memories_1.sqlite`), 저장소에도 `master/audit_issues_codex.py`
`bench_lane_codex.py` 가 있다. 다만 **작성 레인의 실행 주체**로 쓰인 것이고, **대화형 지휘자로
쓴 기록은 없다** — §15.2 의 전제와 일치.

**⑤ `#384` 는 아직 「신규」이고 노트가 없다.** 조회 2026-09-07 23:48 — 트래커 「코드리뷰」,
버전 「마일스톤 6 — 개선·확장」.

---

## 54.4 Codex 확인 항목 — **전부 미확인. 판정은 Codex 쪽 실측이 한다**

사용자 보고(2026-09-07)로 **이미 확인된 것**:

    [확인] 파일 읽기·수정
    [확인] 승인 후 Redmine 조회·등록
    [차단] 서비스 상태 조회 — 샌드박스

아래는 **아직 확인하지 않은 것**과 기대 동작이다.

| # | 항목 | 기대 동작 | 확인 방법(제안) |
|---|---|---|---|
| 1 | `AGENTS.md` 자동 로드 위치 | 새 세션이 지시 없이 공용 규칙을 읽는다 | 후보 경로에 표식 한 줄을 넣고 새 세션이 그것을 언급하는지 |
| 2 | 홈(`/home/sim`)과 저장소(`~/ax-cluster`) **양쪽**에서의 로드 | 어느 디렉토리에서 열어도 같은 규칙을 본다 | 두 위치에서 각각 새 세션 |
| 3 | MCP `ax-projects` 연결 | `config.toml [mcp_servers]` 로 8103/mcp 에 붙어 33종 사용 | 읽기 도구 1종 호출(예: 프로젝트 목록) |
| 4 | SSH — `.2` `.33` `.43` | 무암호 접속, 원격 명령 실행 | `ssh sim@192.168.0.43 hostname` |
| 5 | `sudo -n /usr/bin/systemctl restart <unit>` | NOPASSWD 로 통과 | **실제 재시작 말고** `systemctl show` 류 무해한 것부터 |
| 6 | `sudo -n /usr/local/bin/ax-install-hook --apply` | 무인 통과 | 온보딩이 무인이어야 하므로 필수 |
| 7 | 훅/자동 고지 동등물 | 세션 시작에 인수인계 기록을 자동으로 본다 | 없으면 ②에서 **다른 수단**을 설계 (54.3 ①) |
| 8 | 서브에이전트 동등물 | 담당 파일·완료 조건을 지정해 위임하고 산출물을 회수 | 없으면 §15.4 ⑤ 를 「지휘자 직접 수행」으로 축소 |
| 9 | 로컬 HTTP 접근 (8080·8101·8102·8103) | 큐·브로커·레드마인 조회 | 서비스 상태 조회가 막혔다면 **HTTP 도 막혔는지** 별도 확인 |
| 10 | `python -m master.*` 실행 | `.venv/bin/python` 으로 저장소 코드 실행 | `master.task_queue --status` |
| 11 | 긴 실행/백그라운드 프로세스 | 파견·빌드처럼 오래 도는 작업을 띄우고 로그를 회수 | |
| 12 | 승인 모델의 입자 | Claude 의 allow 583개에 대응하는 것이 무엇인가 | **재구축 비용 산정용** |

[주의] 9번은 5번과 **별개**다. 「서비스 상태 조회 차단」이 systemctl/D-Bus 차단인지
네트워크 차단인지에 따라 ②의 설계가 갈린다 — 후자면 큐 조회조차 못 하므로 인수인계 기록에
**상태 스냅샷을 미리 적어둬야** 한다.

---

## 54.5 ②로 넘어갈 때

Codex 실측이 오면 다음을 합쳐 쓴다. **아직 쓰지 않았다.**

    docs/orchestrator-rules.md       54.2 Ⓐ 를 근거(누가·언제 결정)와 함께. Ⓑ 는 「도구별」로
                                     따로 표시하고 공통 규칙으로 쓰지 않는다
    docs/orchestrator-handoff.md     §15.5 양식 한 벌
    machines/sim-desktop.md          공용 문서 링크 연결 — [중요] 심볼릭 링크 보존
    AGENTS.md                        확인 항목 1·2 의 **실측 결과가 나온 뒤** 그 위치에

[중요] **54.3 ① 이 먼저 풀려야 ②가 의미를 가진다.** 읽으러 가게 만드는 수단이 없으면
파일만 늘어난다. 후보는 셋 — ⓐ 양쪽 진입점 지침 첫머리에 「먼저 읽어라」를 박는다(수단이
같아 대칭적) · ⓑ Claude 는 `SessionStart` 훅, Codex 는 동등물(확인 항목 7) · ⓒ 사용자가
전환할 때 직접 지시. **ⓐ 는 지금 당장 가능하고 ⓑ 는 7번 결과에 달렸다.**
