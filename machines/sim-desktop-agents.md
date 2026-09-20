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
    .33  Windows      요청자 · 계정 user          [중요] 파견 대상이 아니다 · 사람의 기계
    .43  BC-250 #1    워커 + 추론 · 계정 sim      (Fedora, headless)

## 마스터 실행 환경 · 지휘자 교대

- AX 도구 실행 전 작업 위치를 `/home/sim/ax-cluster` 로 맞춘다. Python 은 `.venv/bin/python` 을 쓴다.
- **Codex 에서 레드마인 키 조회가 빈 문자열이면 키 부재로 단정하지 않는다.** `master.redmine.api_key()`는
  `AX_REDMINE_API_KEY` 다음에 `docker exec redmine-db-1 psql ...`로 컨테이너 DB를 읽는데, 기본
  샌드박스가 Docker 접근을 막으면 예외 대신 빈 문자열이 된다. 비밀값을 출력하지 않는 좁은
  `.venv/bin/python` 조회 명령을 샌드박스 해제 승인으로 다시 실행한다. 존재 확인은
  `print(bool(r.api_key()))`처럼 하고, 키 자체는 로그에 출력하지 않는다.
- 프로젝트 CLI 는 환경변수가 필수다. 조회 예:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client plan NS`
  (`NS` 는 예시다. 대상 프로젝트를 명시한다.) `deliver`·`check` 도 같은 접두를 쓴다.
- 마스터의 공용 호출 창구는 `ax-projects` MCP 다. Codex 설정은 `~/.codex/config.toml`,
  Claude 설정은 `~/.claude.json` 에 있다. 설정 추가만으로 현재 세션에 도구가 생겼다고 판단하지 않는다.
- 워커 지휘자 선택은 `ax-mode` 스킬 → `get_worker_mode_tool` / `set_worker_mode_tool` 이다.
  마스터 대화 세션의 교대와 워커 모드 선택은 별개다. 선택 가능한 값은 `lane`·`claude`·`codex`.
- 배달은 커밋된 깨끗한 트리에서 한다. 문서만 미커밋이어도 `delivered_by.dirty=true` 로 기록된다.
