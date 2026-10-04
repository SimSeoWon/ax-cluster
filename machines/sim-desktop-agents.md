# AGENTS.md — sim-desktop 홈 (`/home/sim`)

    AX-ENTRY-MARK: home

> 위 표식은 **자동 로드 검증용**이다. 새 세션이 지시 없이 이 파일을 읽었는지 가리는 데 쓴다
> (`~/ax-cluster/docs/orchestrator-handoff.md` §바로 다음 작업). 지우지 않는다.
>
> [중요] **정본은 `~/ax-cluster/machines/sim-desktop-agents.md` 이고 `/home/sim/AGENTS.md` 는
> 심볼릭 링크다** — `~/CLAUDE.md` 와 같은 방식이다. 일반 파일로 덮지 않는다.

`/home/sim` 은 **개인 리눅스 홈서버 sim-desktop 의 홈이지 소프트웨어 저장소가 아니다.**
빌드·린트·테스트 도구가 없다. **코드베이스가 있다고 전제하지 않는다.**
이 기계는 AX 클러스터의 **마스터**다 — 큐·브로커·색인/온톨로지·저장소(`~/ax-cluster`).

## 세션 시작에 읽을 것

1. 🔴 **`~/ax-cluster/docs/orchestrator-handoff.md`** — 지금 무엇이 진행 중인가. **한 벌.**
2. 🔴 **`~/ax-cluster/docs/orchestrator-rules.md`** — 두 지휘자의 공용 규칙.
3. `~/ax-cluster/docs/milestones/6-improvements.md` · `~/ax-cluster/docs/12-multi-project.md`.
   [주의] **항목·진행은 레드마인(`:8080`)만.**
4. `~/ax-cluster/reports/` 를 **전문으로** 읽는다.

## 절대 놓치면 안 되는 것 (전문은 `docs/orchestrator-rules.md`)

- **커밋·푸시는 자율 실행 금지** — 매번 승인.
- **실패는 보고하는 자리다** — 고치지 않고 멈춘다. **대상 목록 밖 파일은 건드리지 않는다.**
- **사람 게이트는 둘** — ⑺ 전진과 finalize.
- **`~/CLAUDE.md` 와 `/home/sim/AGENTS.md` 는 둘 다 심볼릭 링크다** — 덮지 않는다.
- **`~/AgentTest` 는 참조 전용.**
- **사용자와의 대화는 한국어.**
- **작업장은 `.33` 이다** — Unreal 작업은 거기로 들어온다. 여기서 다루는 것은 클러스터 자체다.
- **권한 문제는 대상 명령을 좁힌 스크립트로 만들고 그 스크립트 실행 승인을 요청한다.** 승인
  창을 우회하려고 다른 경로를 만들지 않는다. [주의] Codex 실행 승인은 샌드박스 해제이고 OS의
  `sudo` 비밀번호를 대신하지 않는다 — 승인 뒤에도 sudo가 거절하면 그 실패를 그대로 보고한다.
- **진단용 패치와 운영 배포를 섞지 않는다.** 원인 확인을 위해 특정 PC에서 빌드한 Codex·Rust
  산출물을 `main`·온보딩·워커 설정에 넣지 않는다. 먼저 `reports/`에 원인·실증·범위를 기록하고,
  정식 upstream 릴리스 또는 별도 CI 산출물 계약이 확정된 뒤에만 배포 설계를 시작한다.
- **한 PC에서 얻은 바이너리를 정본으로 삼지 않는다.** 실증 PC는 재현을 위한 임시 환경일 뿐이며,
  신규 워커는 그 PC가 꺼져 있어도 초기화할 수 있어야 한다.

## 기계

    .57  sim-desktop  이 기계 · 마스터            (서비스 8080·8101·8102·8103)
    .2   Windows      워커 + 추론 · 계정 janus    (UE5 5.8 — 층3 판정 가능)
    .33  Windows      게임 요청자 · 계정 user     AXCluster 마운트 시 워커 · 사람의 기계
    .43  BC-250 #1    워커 + 추론 · 계정 sim      (Fedora, headless)

## 마스터 실행 환경 · 지휘자 교대

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

**인프라 변경 요청도 RAG부터 시작한다**(사용자 2026-10-03, #716).
`ax-projects.search_context_tool`로 검색하고 현재 소스와 대조한 뒤 대상·근거·분해안을 보여
**단독(로컬 서브 에이전트) / AX 워커 분산**을 사용자에게 묻는다. 같은 작업에서 이미 정한
방식은 다시 묻지 않는다. 결정한 방식에 맞춰 서브 에이전트를 구성하고 산출물을 직접 검증·기록한다.
분산 준비가 부족하면 선행 정비를 알려 결정받으며, 즉시 파견 가능한 것으로 제시하지 않는다.
골조·소스 경계·검사는 등록 프로필 `kind`(`unreal`/`code`/`index_only`)로 분기한다.
세부 절차: [`../master/skills/distribute/SKILL.md`](../master/skills/distribute/SKILL.md).

- AX 도구 실행 전 작업 위치를 `/home/sim/ax-cluster` 로 맞춘다. Python 은 `.venv/bin/python` 을 쓴다.
- **Codex 에서 레드마인 키 조회가 빈 문자열이면 키 부재로 단정하지 않는다.** `master.redmine.api_key()`는
  `AX_REDMINE_API_KEY` 다음에 `docker exec redmine-db-1 psql ...`로 컨테이너 DB를 읽는데, 기본
  샌드박스가 Docker 접근을 막으면 예외 대신 빈 문자열이 된다. 비밀값을 출력하지 않는 좁은
  `.venv/bin/python` 조회 명령을 샌드박스 해제 승인으로 다시 실행한다. 존재 확인은
  `print(bool(r.api_key()))`처럼 하고, 키 자체는 로그에 출력하지 않는다.
- Redmine 스크립트를 `/tmp`에 둘 때는 `sys.path.insert(0, "/home/sim/ax-cluster")`를 넣어
  `from master import redmine`이 스크립트 위치와 무관하게 성공하게 한다. `cd`만으로는 `/tmp`
  스크립트의 Python import 경로가 바뀌지 않는다.
- 프로젝트 CLI 는 환경변수가 필수다. 조회 예:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client plan NS`
  (`NS` 는 예시다. 대상 프로젝트를 명시한다.) `deliver`·`check` 도 같은 접두를 쓴다.
- 모든 등록 프로젝트·작업장을 현재 HEAD로 맞출 때는 프로젝트를 고르지 않고
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`를 쓴다.
- **관리되는 Codex 자산은 프로젝트 체크아웃 안에도 있다.** 배달은 `<checkout>/.agents/skills`
  와 `<checkout>/.codex/config.toml`을 만들고 `check`가 대조한다(`#699`). 홈의 동명 스킬보다
  프로젝트 로컬 정본이 우선이다. 초기화·배달 뒤 이 둘이 없으면 정상 상태가 아니다.
- 마스터의 공용 호출 창구는 `ax-projects` MCP 다. Codex 설정은 `~/.codex/config.toml`,
  Claude 설정은 `~/.claude.json` 에 있다. 설정 추가만으로 현재 세션에 도구가 생겼다고 판단하지 않는다.
- 워커 지휘자 선택은 `ax-mode` 스킬 → `get_worker_mode_tool` / `set_worker_mode_tool` 이다.
  마스터 대화 세션의 교대와 워커 모드 선택은 별개다. 선택 가능한 값은 `lane`·`claude`·`codex`.
- 배달은 커밋된 깨끗한 트리에서 한다. 문서만 미커밋이어도 `delivered_by.dirty=true` 로 기록된다.
- **AX 인프라 일감은 레드마인 `ax-cluster`(id 3)에 둔다.** 게임·도구 일감은 각 프로젝트의
  `redmine.project`를 따른다. 리뷰 상태는 `<twin>/fixes/index.json`이 정본이며, 오래된 골조
  리뷰를 처리할 때 현재 소스·후속 구현 커밋·회귀 검사를 대조한다.
- **AXCluster 통합 검사는 `~/ax-cluster/tests/integration/checks.json`이 명시 목록이다.**
  저장소에서 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`를
  실행한다. 색인기 단위 검사는 가짜 합성기를 주입하며 실제 브로커 성공에 기대지 않는다.
- **AXCluster 마운트 시 `.2`·`.33`·`.43`을 워커로 사용한다**(사용자 2026-10-03).
  요청자는 마스터이며 `.33`은 `C:\trunk\AXCluster`에서만 작업한다. 게임 requester 역할은 별개다.
- **Windows Codex 원격 실행**: `workspace-write` + `windows.sandbox="unelevated"` +
  `sandbox_workspace_write.network_access=true`, `/IT /RL LIMITED` 런처로 **로그인 사용자 세션**에서
  실행한다. “세션 1”은 고정 SessionId가 아니다. 실제 셸 읽기·apply_patch 쓰기·결과 회수를 확인한다.
  readiness는 예약 런처의 등록 계약 검사이며 로그인·인증·실행 성공을 보증하지 않는다.
  정본·진단·기억: [`~/ax-cluster/docs/windows-codex-remote.md`](../docs/windows-codex-remote.md).
