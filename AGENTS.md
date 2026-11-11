# AGENTS.md — AX 클러스터 저장소 (`~/ax-cluster`)

    AX-ENTRY-MARK: repo

> 위 표식은 **자동 로드 검증용**이다. 새 세션이 지시 없이 이 파일을 읽었는지 가리는 데
> 쓴다 (`docs/orchestrator-handoff.md` §바로 다음 작업). 지우지 않는다.

## 세션 시작에 읽을 것

1. **[`ax-handoff`](master/skills/ax-handoff/SKILL.md) 스킬**로 인수인계를 복원한다.
   `docs/orchestrator-handoff.md`와 `docs/orchestrator-rules.md`를 읽고 실제 상태를 대조하며,
   마스터 담당과 워커 지휘자 모드를 각각 확인한다. 모드 변경은 사용자 선택에 따른다.
2. `docs/milestones/7-improvements.md`(열린 마일스톤) · `docs/12-multi-project.md`(열린 축).
   [주의] **항목·진행은 레드마인(`:8080`)만** 본다.
3. `reports/` 를 **전문으로** 읽는다 — grep 은 대체가 아니다.

## 절대 놓치면 안 되는 것 (전문은 `docs/orchestrator-rules.md`)

- **커밋·푸시는 자율 실행 금지** — 매번 승인을 받는다.
- **실패는 고치는 자리가 아니라 보고하는 자리다** — rc≠0·차단·예외면 멈추고 사유와 갈래를 낸다.
  예외 하나: 읽기 전용 조회가 `No such file or directory` 면 확인된 경로로 다시 조회하고 보고에 남긴다.
  검색 대상 경로는 존재를 확인한 것만 쓴다.
- **지시받은 대상 밖의 파일은 건드리지 않는다.**
- **사람 게이트는 둘** — ⑺ 전진(`ax-advance`)과 finalize(`main` 머지).
- **`~/AgentTest` 는 참조 전용** — 수정·푸시 금지. 만들기 전에는 이 저장소의 기존 자산부터 읽고,
  원전은 참고만 한다(포팅 종료 2026-10-18).
- **사용자와의 대화는 한국어.**
- **작업장은 `.33` 이다** — Unreal 작업은 거기로 들어온다. 여기서 다루는 것은 클러스터 자체다.
  기계: `.57` 마스터(이 저장소) · `.2` 워커+추론(계정 `janus`, UE5) · `.33` **게임 요청자 · 사람의
  기계**(계정 `user`) · `.43` 워커+추론(계정 `sim`). **AXCluster 마운트 시 `.33`도 워커**로
  사용한다(사용자 2026-10-03); 마스터가 요청하며 게임 트리와 분리한 `C:\trunk\AXCluster`만 쓴다.
  [주의] **이 줄은 홈 진입 문서와 중복이다 — 일부러 그렇다.** Codex 는 저장소에서 시작하면
  홈 지침을 싣지 않는다(`docs/orchestrator-rules.md` §3.1). **두 진입 파일은 각각 자족적이어야
  한다** — 한쪽에만 규칙을 추가하지 않는다.
- 이 저장소의 작업 지침 전문은 [`CLAUDE.md`](CLAUDE.md) — **도구 이름이 붙어 있을 뿐
  내용은 도구 무관**이다. Codex 도 그 규칙을 따른다.

## 마스터 실행 환경 · 지휘자 교대

AX 마스터 지휘는 Claude·Codex만 맡는다(#829). Gemini 4 Argon/Antigravity는 지휘자가 범위를 지정한
서브 작업만 수행하며, 전역 설정·공용 지침·MCP 운영·일감 시작·마감·배포를 독자적으로 변경하거나
실행하지 않는다. 위임·검증 범위는 `docs/orchestrator-rules.md` §1.10을 따른다.

### 등록된 스킬 우회 금지 — 사용자 결정 2026-10-04

- 등록된 스킬이 있는 작업은 해당 스킬의 기존 도구·모듈·명령으로 실행한다.
- 실행 전에 사용할 스킬 경로와 실제 호출 명령을 사용자에게 밝힌다.
- **스킬의 절차나 호출 방법이 불명확하면 사용자에게 먼저 묻는다.** 답변 전에는 임시
  스크립트 작성·대체 경로 실행·처리 방식 변경을 하지 않는다.
- 기존 기능을 대신하는 임시 스크립트나 별도 실행 경로를 임의로 만들지 않는다. 기존 절차로
  처리할 수 없다면 실제 확인한 호출·제약과 부족한 기능을 제시하고 사용자 결정을 기다린다.
- 기억 속 파일의 부재를 시스템 기능의 부재로 판단하지 않는다. 사용자가 선택한 분산 방식을
  직접 처리로 바꾸거나, 요청 범위를 기존 분산 실행 코드·파견 계약 정비로 임의 확대하지 않는다.
- 권한 승인을 위한 좁은 스크립트도 기존 호출 방법을 확인한 뒤 승인받아 실행한다.
  권한 문제 규칙을 스킬 대체 경로를 만드는 근거로 사용하지 않는다.

### Codex의 RAG·경로·호출 근거 확인 — 사용자 결정 2026-10-04

- **RAG를 호출한 것만으로 근거 확인을 완료했다고 판단하지 않는다.** 검색 결과의 관련 문서
  본문을 읽고, 그 안의 경로·모듈·호출 방법을 실제 소스와 대조한 뒤 사용한다.
- 파일을 읽기 전에 해당 작업 위치에서 `rg --files`로 실제 경로를 확인한다. 숨김·무시 파일은
  문서에 명시된 대상에 한해 범위를 좁혀 확인한다. 기억·이전 대화 요약·디렉터리 관례로
  경로를 만들어 명령에 넣지 않는다.
- **경로 확인은 두 번의 별도 도구 호출로 실행한다.** 첫 호출은 확인된 작업 위치에서
  `rg --files -g '<파일명 또는 패턴>'`로 목록만 받는다. 존재를 확인하지 않은 디렉터리를
  `rg --files`의 검색 대상으로 넣지 않는다. 두 번째 호출에서 첫 결과에 실제로 나온
  경로만 `cat`·`sed`·`rg` 등의 읽기·검색 인자로 사용한다. 목록 조회와 파일 읽기를 같은
  호출에 미리 묶지 않는다. 경로가 없으면 없는 것으로 보고하며 추정 경로로 재조회하지 않는다.
- **서브 에이전트에도 같은 두 단계 절차를 작업 지시에 명시한다.** 지휘자는 확인된
  작업 위치와 허용 파일을 전달하며, 에이전트는 자신이 받은 실제 목록을 확인한 뒤 읽는다.
  「읽기 전에 경로 확인」이라는 문구만 전달하고 실행 여부를 확인한 것으로 간주하지 않는다.
- 실행 전에 근거 문서와 실제 호출 명령을 사용자에게 밝힌다. 근거가 없거나 문서와 실제
  소스가 다르면 **사용자에게 먼저 묻고**, 답변 전에는 다른 경로를 추측해 재조회하거나
  임시 스크립트 작성·대체 호출·처리 방식 변경을 하지 않는다.
- 독립 조회는 각각 실행 결과를 받아 종료 코드와 stderr를 확인한다. `;`로 조회를 연결해
  마지막 성공 코드로 앞선 실패를 덮지 않는다. 출력이 잘리면 확인한 것으로 판단하지 않는다.
- 이 규칙은 **Codex의 실행 지침**이다. 이를 이유로 Claude 문서·공용 스킬·분산 실행 코드·
  파견 계약을 임의로 수정하지 않는다.

**인프라 변경 요청도 RAG부터 시작한다**(사용자 2026-10-03, #716).
`ax-projects.search_context_tool`로 검색하고 현재 소스와 대조한 뒤 대상·근거·분해안을 보여
**단독(로컬 서브 에이전트) / AX 워커 분산**을 사용자에게 묻는다. 같은 작업에서 이미 정한
방식은 다시 묻지 않는다. 결정한 방식에 맞춰 서브 에이전트를 구성하고 산출물을 직접 검증·기록한다.
분산 준비가 부족하면 선행 정비를 알려 결정받으며, 즉시 파견 가능한 것으로 제시하지 않는다.
골조·소스 경계·검사는 등록 프로필 `kind`(`unreal`/`code`/`index_only`)로 분기한다.
세부 절차: [`master/skills/distribute/SKILL.md`](master/skills/distribute/SKILL.md).

- AX 도구 실행 전 작업 위치를 `/home/sim/ax-cluster` 로 맞춘다. Python 은 `.venv/bin/python` 을 쓴다.
- 프로젝트 CLI 는 환경변수가 필수다. 조회 예:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client plan NS`
  (`NS` 는 예시다. 대상 프로젝트를 명시한다.) `deliver`·`check` 도 같은 접두를 쓴다.
- 마운트된 프로젝트의 작업장을 현재 HEAD로 맞출 때는 프로젝트를 고르지 않고
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`를 쓴다
  (등록 전체는 `update --all`. 비마운트 프로젝트는 마운트 전환 때 뒤처진 기계만 맞춘다, #655).
  **커밋마다 실행한다** — 배달 출처 커밋이 HEAD보다 뒤처지면 해시가 같아도 `check`가 실패한다.
- **관리되는 Codex 자산은 프로젝트 체크아웃 안에도 있다.** 배달은 `<checkout>/.agents/skills`
  와 `<checkout>/.codex/config.toml`을 만들고 `check`가 대조한다(`#699`). 홈의 동명 스킬보다
  프로젝트 로컬 정본이 우선이다. 초기화·배달 뒤 이 둘이 없으면 정상 상태가 아니다.
- 마스터의 공용 호출 창구는 `ax-projects` MCP 다. Codex 설정은 `~/.codex/config.toml`,
  Claude 설정은 `~/.claude.json` 에 있다. 설정 추가만으로 현재 세션에 도구가 생겼다고 판단하지 않는다.
- 마스터 담당 조회는 [`ax-handoff`](master/skills/ax-handoff/SKILL.md) 스킬의
  `get_orchestration_tool()`을 쓴다. 마스터 담당은 마지막 인수 기록이며 프로세스 생존 판정·
  잠금·세션 실행이나 종료 기능이 아니다. 사용자가 마스터 교대를 지시했고 실제 인수를
  마친 경우에만 `record_master_conductor_tool(agent, why, by)`로 기록한다.
  단순 조회나 인수인계 읽기 요청은 기록 변경 승인이 아니다.
- 워커 지휘자 선택은 [`ax-mode`](master/skills/ax-mode/SKILL.md) 스킬 →
  `get_worker_mode_tool` / `set_worker_mode_tool` 이다. 변경은 준비 검사를 수행하는
  `conductor.set_worker()`를 거치며, MCP가 없을 때도 스킬의 같은 정본 호출을 따른다.
  마스터 대화 세션의 교대와 워커 모드 선택은 별개다. 선택 가능한 값은 `lane`·`claude`·`codex`.
  전역 모드는 새 work 등재의 기본값이며 기존 `work.worker_mode` 스탬프가 우선한다.
  전역 변경은 진행 조각·후속 라운드에 소급되지 않는다. 현재 모드·출처는 도구로 재조회하며
  최근 전환 근거는 [`인수인계서`](docs/orchestrator-handoff.md)에서 확인한다.
  `claude` 워커 인증 readiness는 `claude auth status` 24시간 캐시(워커 홈
  `.cache/ax-dispatch/claude-auth.json`, `#721`)이며, 실행 중 OAuth 실패는 재시도 없이 즉시
  보고된다. 재로그인은 사람 몫이다 → [`docs/14-onboarding-runbook.md`](docs/14-onboarding-runbook.md).
- 배달은 커밋된 깨끗한 트리에서 한다. 문서만 미커밋이어도 `delivered_by.dirty=true` 로 기록된다.
- **AX 인프라 일감은 레드마인 `ax-cluster`(id 3)에 `[AX]` 제목 접두로 둔다.** 게임·도구 일감은 각 프로젝트의
  `redmine.project`를 따른다. 리뷰 상태는 `<twin>/fixes/index.json`이 정본이며, 오래된 골조
  리뷰를 처리할 때 현재 소스·후속 구현 커밋·회귀 검사를 대조한다.
- **AXCluster 통합 검사는 `tests/integration/checks.json`이 명시 목록이다.** 실행은
  `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`.
  신규 검사는 `checks.json` 등록 여부를 `master/test_integration_coverage.py`로, 마스터 스킬 링크는 `master-local --check`로 확인한다 (`#929`).
  색인기 단위 검사는 가짜 합성기를 주입하며 실제 브로커 성공에 기대지 않는다.
- **Windows Codex 원격 실행**: `workspace-write` + `windows.sandbox="unelevated"` +
  `sandbox_workspace_write.network_access=true`, `/IT /RL LIMITED` 런처로 **로그인 사용자 세션**에서
  실행한다. “세션 1”은 고정 SessionId가 아니다. SSH 직접 실행·예약 작업 요청 성공을 실증으로
  대신하지 않는다. 실제 셸 읽기·apply_patch 쓰기·결과 회수를 확인한다.
  readiness는 예약 런처의 등록 계약 검사이며 로그인·인증·실행 성공을 보증하지 않는다.
  정본·진단·기억은 [`docs/windows-codex-remote.md`](docs/windows-codex-remote.md).
