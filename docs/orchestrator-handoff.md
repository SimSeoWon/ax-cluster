# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **현재 인수**: **Claude** · 마스터 담당 기록 2026-10-04 22:27:47 KST (사용자 지시로 Codex 에서 인수).
  **현재 갱신: 2026-10-05 00:35 KST**. main = origin/main `f03f374`(워커 체크아웃은 `d0ba940`, 차이는 이 문서뿐) 실제 재조회, 이 문서만 미커밋(커밋 승인됨).
  워커 지휘자 모드 `codex` / `source=state`(20:52:56) — 이번 인수에서 바꾸지 않았다.
  **#735 완료로 종결**(사용자 지시 2026-10-05, 진행률 100% 재조회) — 원본 로그 수집 · 마스터 AXCluster 귀속 · 「모두 보기」 · **원본 보존 30일** · 계열별 도넛.
  AXCluster 체크아웃 4곳 `d0ba940`. `master.client update`(d0ba940) **rc 0 · 15/15 OK**.
  신규 버그 일감 **#736**(도넛이 계열 필터 무시 — 사용자 「그대로 둬」) · **#737**(update 실행 중 커밋 시 검사 실패). 신규 파견은 없다.

아래 메타데이터는 이전 Claude 인계(20:25) 시점의 기록이며 현재 상태는 §0 첫 절을 따른다.

- **이전 갱신 시각**: 2026-10-04 20:25 KST — Claude · #725 마감·후속 배포 · 색인기 막힘 해소(#732 완료) · 워커 동기화 ·
  `.2` MCP 경고 수정 · `/ontology` 브라우저 확인 · 통합 검사 등록 · agy 사용량 기록(#728 완료)
- **지휘 도구 / 세션**: **Claude** 마스터. Codex 는 이 문서를 갱신하기 전에 한도가 소진됐다
  (마지막 Codex 갱신은 00:47 헤더 + §0 R9·R19 후속). 17:02:34 `record_master_conductor('claude')`.
  마스터의 Codex 프로세스(pid 20028)는 17:02 에 살아 있었고 17:20 재조회 시 없었다(내가 종료하지 않았다).
  담당 기록은 세션 잠금이 아니다.
- **상태**: 진행 중인 work·루프 없음. 색인기 커서 = HEAD(`fc9c4de` 시점) · 리뷰 큐 pending 0.
  미커밋은 이 문서뿐.
- **관련 일감**: 완료 — **#725** · **#732**(사실 게이트 파일 종류별 주석 규칙) · **#728**(agy 사용량 기록) ·
  신규(미착수) — **#726**(토큰 구성 측정) · **#727**(색인기 frontmatter 멈춤 — 형식 게이트·모델) ·
  **#733**(sink 밖 상용 CLI 호출 — 층2·게시판·review_gen 직접, claude·codex 진입점 포함) ·
  아이디어 **#729**(스펙 주도 개발) · **#730**(「클로드 모드」 — 출처 미확인) · **#731**(NotebookLM 리서치).
  열림(이전부터) — #700 · #701 · #716 · #720 · #721.
- **워커 지휘자 모드**: **`claude`** — 사용자 지시 「모든 워커들 클로드가 작업하도록」,
  17:02:28 `set_worker_mode_tool('claude')`, readiness 3/3 ok
  (`.43` 2.1.222 · `.2` 2.1.285 · `.33` 2.1.286). 말하기 전에 모드 도구로 재조회한다.
  🔴 [주의] **work 스탬프가 전역보다 우선한다** — 등재 때 찍힌 `worker_mode` 를 파견이 쓰고
  (`autodispatch.py:424`), `improve_work` 에서 `worker_mode` 를 비우면 큐가 기존 값을 유지한다
  (`task_queue/logic.py:245`). 전역 전환(2026-10-04 17:02 이전 등재분 = `codex` 스탬프) 뒤 옛 work 의 round 를
  열 때는 **`worker_mode="claude"` 를 명시**한다. 새 등재는 전역값 `claude` 를 따른다.
- **마운트**: `AXCluster` — `.57` 요청자, `.2`·`.33`·`.43` worker. `.43` 은 어젯밤 poweroff 기록이
  있으나 17:02 readiness 에 응답했다(켜져 있다).
- **소스**: 마스터 main = Gitea main `66a7a1f` 위에 이 문서 커밋 · 작업 트리 clean.
  `ax-projects` 17:37:50 재기동(MainPID 79173) — 7화면 200 · 사이드 메뉴 확인. `fc9c4de`(verify/synth)는 색인기가
  실행마다 새로 읽으므로 재기동 불필요(라이브 통과로 확인).
  **AXCluster 워커 3대 + `.43 ~/ax-cluster` 관리 클론 = `66a7a1f`** (18:1x, 사용자 「워커 모두 동기화」·「관리 클론도」):
  main·clean 확인 → `fetch origin main` → `merge --ff-only` → `plan → deliver → check AXCluster` **3/3 OK**
  (스킬·config·payload 10·태그·출처 HEAD 일치 · 배달 뒤 source clean 3/3). 다른 프로젝트 워커는 손대지 않았다.
  `.2` `claude_mcp_local=ax-client` 「등록했다는데 ~/.claude.json 에 없다」 경고는 **검사 오탐이었다** — 등록·연결은
  정상(`claude mcp get` Connected). 원인: PowerShell 5.1 `Get-Content -Raw` 가 UTF-8 을 CP949 로 읽어 한글 기록이
  JSON 을 깨뜨림(60,855자 근처 파싱 실패). `3e46078` 에서 `-Encoding UTF8` + 테스트(395/395) · 고친 함수를 `.2`·`.33`
  에 읽기 전용으로 돌려 둘 다 항목 확인. 재배달은 안 했다(다음 배포에서 경고 소멸 확인). 워커 소스는 `66a7a1f`
  (`3e46078` 은 마스터 측 배달 코드라 워커 동기화 불필요). 홈 중복 스킬 `~/.agents/skills/ax-work` 주의는 무해.

## 0. 지금 넘기는 상태 — 아래 이력보다 이 절이 최신

### 최신 — #735 원본 보존 정책 · 계열별 도넛 · update 완료 (2026-10-05 00:30, Claude)

**사용자 결정**:
- 원본 보존 값은 `projects.yaml` 의 `usage.raw_retention_days`, 기본 30일. 세션 mtime 기준으로 **마스터 원본 사본과 색인 줄만** 지운다.
  숫자 스냅샷은 남긴다(웹UI 과거 사용량 유지), 기간 지난 워커 파일은 다시 받지 않는다, 워커 원본은 건드리지 않는다.
- `/usage` 원형 그래프 = **모델 계열별 토큰 비율**, 화면 기간·프로젝트 필터를 따르되 항상 `source=all`.
  서브 에이전트가 **계열 필터는 따르지 않게** 판단 → 사용자 「그대로 둬. 버그로 레드마인에 등록하고」 → **#736**.

**구현 (로컬 서브 에이전트) — 커밋 `d0ba940`**: `config.py` `Registry.raw_retention_days()`(잘못된 값은 fail-closed: 그 실행은
정리·거름 없이 수집만, 경고 로그 · `save()` 가 `usage` 키 보존함을 검사로 확인) · `session_usage.py` `prune_raw`, 목록 단계 mtime 거름,
CLI `--prune [--dry-run]` · `usage_page.py` 도넛(인라인 SVG) + 대체 표. 라이브 `projects.yaml` 에 키 추가(gitignore, 기존 바이트 동일).
검사: session_usage 19/19 · usage_page 8/8 · usage_dashboard 9/9 · routes 5/5 · nav 2/2 · cli_paths 40/40 · test_projects 76/76.

**배포·라이브**: push · `ax-projects` 재기동 00:06:03. `/usage` 진입 → 「보존 정리 — 기준일 2026-09-05 · 정리 22 · 4,808,957바이트 · 오류 0」,
기간 지난 원격 22개 재전송 안 함, 색인 648 · 스냅샷 691(유지), 도넛 표시.

**update**: `5fc6786` 실행은 도중 인계서 커밋 `4ac3099` 로 HEAD 가 움직여 ModularStage 검사 2건 「출처 1커밋 뒤」 → rc 1(**#737** 등록).
`d0ba940` 로 워커 4곳 ff-only 뒤 재실행 → **rc 0 · 15/15 OK**. [주의] update 실행 중에는 커밋하지 않는다(#737 해결 전 우회).

**남은 것**: #735 는 사용자 지시로 **완료 종결**(00:23 KST, 종결 노트에 커밋 5개 기록). #736·#737 미착수. 이전 열린 일감(#714·#666 운영 검증, #726·#727·#733 등)은 그대로.

### 최신 — #735 후속: 마스터 귀속 · 「모두 보기」 · 전체 최신화 (2026-10-04 23:50, Claude)

**사용자 결정**:
- *"마스터 세션은 ~/ax-cluster 면 AXCluster 로 귀속해"* → `session_usage.MASTER_CHECKOUTS`(레지스트리에 없으면 잇지 않고 로그).
  실 저장소 `--reparse`: 669 사본 중 local 39건 이동. 남은 local 미분류 99(cwd `/home/sim` 82 · `/tmp` 임시).
- 웹UI 소스에 **「모두 보기」(`source=all`)** 추가 — **계열별 출처 하나**(사용자 선택): claude·codex 는 대화 세션,
  gemini·local·unknown 은 작업 실행 기록. 근거: 워커 `codex exec` 파견이 그 기계 세션 파일에도 남는다
  (10/4 16:55 파견 4건을 워커 세션 사본에서 확인) → 단순 합산은 이중 계산. `all` 의 issues 는 빈 표.

**진단 메모** — 사용자 질문 「10/4 Claude · 10/3 Codex 가 없다」: 기본 소스 「작업 실행 기록」 기준이라 정상.
10/4 파견 4건은 모두 codex 모드, 10/3 codex 파견 3건(20:42)은 `measured:false` 실패 시도. 대화 세션엔 두 날 모두 두 계열 있음.

**커밋·배포** (각각 사용자 승인): `a5cc306`(마스터 귀속) · `5fc6786`(모두 보기). Gitea push, 로컬·원격 일치.
`ax-projects` 재기동 23:22:07 → 23:42:52 active. 라이브 `/api/v1/usage?source=all`(10/4) 1,748회 · 2.54억 토큰, `/usage` 에 「모두 보기」 표시.
검사: session_usage 13/13 · usage_dashboard 9/9 · usage_page 4/4 · usage_routes 5/5 · 통합 20/20.

**워커 최신화**:
- `a5cc306` 때 `master.client update` rc 0(5프로젝트 배달·검사 OK). [주의] **update 는 워커 체크아웃을 당기지 않았다** —
  `.43`/`.2` `66a7a1f`, `.33` `d061598` 에 머물러 있었다. 그래서 체크아웃은 main·clean 확인 후 `fetch` + `merge --ff-only` 로 따로 맞췄다.
- 현재 `.43 ~/ax-cluster` · `.43 ~/trunk/AXCluster` · `.2 E:\trunk\AXCluster` · `.33 C:\trunk\AXCluster` 모두 `5fc6786`.
- 🔴 `5fc6786` 기준 `master.client update` 를 백그라운드로 다시 돌리는 중(23:43 시작, 출력은 끝나야 나온다). **결과 미확인** —
  다음 지휘자는 rc 와 「[완료] 등록 프로젝트 5개」 줄을 확인하거나 다시 돌린다. 게임 프로젝트 체크아웃은 당기지 않았다(게임 소스 트리).

**남은 것 (미승인)**: 원본 사본 보존 정책. #735 는 열어 둔다(종결은 사용자 판단).

### 최신 — #735 세션 원본 로그 증분 수집 완료·배포 (2026-10-04 23:10, Claude)

**사용자 결정 (이 세션)**:

- Claude 인수(「응 클로드로 인수하고 로컬 서브 에이전트로 진행해」) → `record_master_conductor('claude')` 22:27:47.
- 보관 구조 **프로젝트/워커IP/도구** 선택: `~/ax-state/usage/raw/<프로젝트|_unassigned>/<IP|local>/<claude|codex>/<원본 상대경로>`
  + `raw/index.jsonl`(project·work_id·task_id·host·tool·origin·cwd·size·mtime·sha256). work 는 디렉토리 단계가 아니다.
- 진행 중 파일: **크기·mtime 이 바뀌면 통째로 재복사**(원자적 교체). 원격은 읽기 전용, 워커 원본 삭제는 범위 밖.
- Redmine 일감 **#735** 생성(ax-cluster · 코드리뷰 · 마일스톤 6). 노트 3건(구현·배포·후속).

**구현 (`8c1c93e`)**: `master/work/session_usage.py`(원본 증분 복사 · cwd↔`workshops.<host>.path` 최장 접두 귀속 ·
`.ax/work/<task_id>` 일 때만 task/work · 원본에서 숫자 스냅샷 재생성 · flock · `--reparse` · `refresh_in_background`) ·
`usage_dashboard.py`(session 프로젝트 필터) · `webui/app.py`(/usage 진입 시 배경 수집, 잠금 · 최소 5분) · 테스트 `test_session_usage.py` 12건 신규.
CLI: `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.work.session_usage all [--reparse]` — rc 2 = 레지스트리 못 읽음.

**실측에서 찾은 결함**: `.33` Windows tar 에 stdin 파일 목록 22.7KB 를 주면 0바이트로 멈춘다 → 묶음당 8KB(`STDIN_BUDGET`) + 마스터 쪽 ssh 감시 타이머.
측정 중 `.33` 에 남은 `tar.exe` 2개는 사용자 승인으로 `taskkill`, 재조회 0개.

**배포·검증**:
- crontab 04:17 수집 줄에 `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 추가(없으면 새 코드에서 rc 2).
- `ax-projects` 재기동 22:55:53 → 23:03:44(후속 `ecb395b` 반영). 8103 은 ax-projects 가 서비스하며 `AX_PROJECTS_ROOT` 가 있다.
- 라이브: `/api/v1/usage` 응답 0.72초, 배경 수집 15.2초 · 4대·2도구 669파일 ≈526MB · 오류 0 · 실 저장소에 AXCluster·KimodoMotion_WebUI·ModularStage·NS·_unassigned 생성.
  session·codex·2026-10-04 집계 **calls 0 → 831 · tokens 92,847,955**. 45초 뒤 재진입은 「간격 < 300초」로 건너뜀.
- 후속 `ecb395b`: `usage_page.py` session 안내 문구 정정 · `tests/integration/checks.json` 에 `test_session_usage.py` 등록(20개). 통합 20/20.

**남은 것 (미승인 — 인계만으로 진행하지 않는다)**:
- 마스터 local 세션은 등록 작업장이 아니라 전부 `_unassigned`. 귀속 규칙(예: cwd `~/ax-cluster` → AXCluster)은 사용자 결정.
- 원본 사본 보존 정책 없음(무기한 누적). `.33` codex 235건 중 226건은 cwd 가 `AppData\Local\Temp` 라 `_unassigned`.
- #714·#666 운영 검증, #726·#727·#733 등 이전 열린 일감은 그대로.

### 최신 — Codex 사용량 미표시 진단 · 원본 로그 캐싱 요청 (2026-10-04 22:19, Codex)

**사용자 목표·결정**:

- 사용자가 「왜 코덱스 작업한 토큰양 웹UI에 적용 안되고 있어」 → 「페이지가 열릴 때 갱신」 제안.
- 모든 워커 로그를 마스터에 캐싱, 이미 다운로드한 파일은 스킵하고 없는 파일만 가져오라는 지시.
  기록 중인 파일의 변경 갱신은 지휘자가 제안한 방식이며 세부 계약은 아직 구현 전이다.
- 사용자는 토큰 숫자뿐 아니라 **대화 내역을 분석할 수 있도록 원본 전체 수집**을 요청했고,
  마지막 지시는 「다 내 컴퓨터니 … 그대로 복사해와. 프로젝트/작업 워커의 IP 기준으로 디렉토리 정리해서 수집」.
  원본 내용은 그대로 복사한다. 추가 비밀값 마스킹 정책을 사용자에게 다시 요구하지 않는다.
- 워커 수집 후 원본 제거도 사용자가 아이디어로 언급했으나 이번에는 복사·수집만 범위로 안내했다.
  원격 원본 삭제는 실행하지 않았고 삭제 조건도 확정되지 않았다. 인계만으로 삭제하지 않는다.

**실제 진단 결과**:

- 기존 `master/work/session_usage.py`: Claude/Codex 홈 jsonl을 로컬 또는 원격 tar 스트림으로
  전부 읽고, `~/ax-state/usage/sessions/<host>/<tool>/*.json`에 **토큰 숫자만** 적립한다.
  원본 파일 캐시·이미 받은 파일 다운로드 생략·프로젝트/work 귀속 기능은 없다.
  기존 CLI는 `.venv/bin/python -m master.work.session_usage [local|IP ...]`지만 현재 요구의
  원본 복사·증분 수집을 수행하지 못하므로 아직 실행하지 않았다. 임시 대체 스크립트도 만들지 않았다.
- `master/work/usage_dashboard.py`는 위 숫자 스냅샷만 읽으며 수집을 호출하지 않는다.
  `master/webui/app.py`의 `/usage`·`/api/v1/usage` 역시 조회만 한다.
  기본 source=dispatch(작업 실행 기록), source=session(대화 세션 기록)은 별도이며 중복 합산 금지.
  현재 session 자료는 프로젝트·일감 귀속이 없고 project 필터를 걸면 해당 자료가 없다.
- 마스터 Codex 원본 오늘 로그는 존재. 기존 `parse_codex`로 숫자만 출력해 20:33 시작 마스터
  세션의 레코드202건, 입력25,604,440·출력54,677 확인(13:05:47Z 시점, 이후 계속 자람).
  21:48 서브 에이전트 세션도19건 확인. 대화 본문은 진단 로그에 출력하지 않았다.
- 적립 저장소의 Codex 스냅샷 검색은 매칭0. 실제 웹UI API
  `/api/v1/usage?source=session&family=codex&start=2026-10-04&end=2026-10-04`
  응답200, calls0·tokens=null·buckets/models비어 있음·read_errors0 확인.
- 등록된 systemd 타이머22개에 세션 수집 타이머 없음. timer/API 첫 샌드박스 조회는 막혔고
  승인된 **동일 읽기 명령**으로 sandbox 밖에서 재조회해 확인했다. 서비스 장애로 단정하지 않는다.

**조사·실행 방식 및 바로 다음 작업**:

- `master/skills/distribute/SKILL.md`와 실제 소스 대조. 현재 AX RAG MCP 도구가 노출되지 않음.
  새 기능 작업의 실제 소스 대조 사용과 **로컬 서브 에이전트 / AX 워커 분산** 선택을 질문했고
  아직 사용자 답변이 없다. 사용자는 대신 이 인계 작성을 요청했다. 선택 답변 전에는 구현·위임하지 않는다.
- 등록 정보 조회는 기존 `Registry.load()`로 완료: 프로젝트 ModularStage·NS·KimodoMotion_WebUI·
  MotionForge·AXCluster, active=AXCluster. 워커 IP `.2`(janus)·`.33`(user)·`.43`(sim).
  게임 프로젝트의 `.33`은 requester이기도 하므로 역할을 전역으로 추정하지 않는다.
- 지휘자 제안은 `프로젝트/작업/워커 IP/도구/원본 경로` 순서 보관, 실제 귀속을 확인할 수 없는
  로그는 미분류 보관, 동일 파일 스킵·변경 중 파일 갱신·캐시로부터 토큰 집계 및 페이지 진입 갱신 연결.
  이 세부 배치와 갱신 계약은 **제안**이며 실제 확정·구현은 다음 단계다. 모든 세션을 active프로젝트에
  임의 배정하지 않는다. 중복다운로드·중복집계·부분복사·진행중파일을 검증할 필요가 있다.
- 확장 대상 후보는 기존 session_usage.py·usage_dashboard.py·webui/app.py·usage_page.py와
  관련 검사다. 새 등록 일감·코드 변경·원본 복사·웹UI 수집 연결 모두 아직 없음.
- 모든 로컬 구현/리뷰 에이전트는 앞선 버그 작업을 완료했다. 이 새 작업에 배정된 에이전트는 없다.
  새 AX 파견·워커 재배달·원격 삭제·강제 종료를 실행하지 않았다. 큐 실행 상태는 이번 인계에서 미조회.
- 다음 지휘자는 세션 시작 AGENTS와 ax-handoff를 먼저 읽고 실제 경로 목록과 소스를 대조한다.
  등록 스킬 기존 도구를 사용한다. 호출 계약이 불명확하면 사용자에게 묻고 임시 스크립트로 우회하지 않는다.
  커밋·push는 매번 승인. 문서 한 벌만 유지하고 홈 AGENTS/CLAUDE 심볼릭 링크를 보존한다.

### 최신 — #715 종결 · #714/#666 로컬 수정 (2026-10-04, Codex)

- 실제 분류는 트래커 `코드리뷰`, 버전 `버그·개선`이다. AX 열린 3건, ModularStage 열린 0건 확인.
- #715: 현재 구현·회귀28/28·이전 실물 분배 기록을 대조해 사용자 지시로 완료100% 종결·재조회.
- #714·#666: 사용자 선택으로 로컬 서브 에이전트 2명 구현·1명 독립 리뷰 완료.
  AX RAG 도구가 없어 일감 본문·실제 소스 대조 사용. 기존 스풀 API 연결과 좁은 구분선 복구.
  코드 변경은 consumer.py·test_events.py·context_synth/md.py·test_context_synth.py 4파일.
- 담당 검사 events57/57·indexer103/103·gate17/17·context_synth135/135,
  지휘자 정본 통합19/19·diff 검사 통과. 운영 스풀 소비·실제 모델 합성·배포는 미검증.
- 사용자 「드라이런하자」 후 지휘자 기존 검사4종 재실행 **312/312**, rc 모두0.
  운영 claimed 이벤트3개 목록·SHA256, conductor/mode SHA256, projects/broker PID·기동시각,
  Git diff SHA256 전후 동일. related 환경변수·브로커 조회 경고는 있었으며 주입 LLM 검사다.
  검사 후 이 문서·리포트93에 결과만 추가했다.
- 기록: [리포트93](../reports/93-spool-recovery-and-frontmatter-repair.md).
  #714·#666은 운영 검증이 남아 열어 둔다. 드라이런 후 사용자 커밋·push 승인.
  **게시 완료**: `d2c0619` 커밋·Gitea push, 로컬·원격 HEAD 일치·clean 확인.
  Redmine #714·#666에는 구현·검사·미배포 노트 기록, 마지막 재조회 상태 신규0%.
  이후 운영 검증·종결·Redmine 재조회는 하지 않았다. #715는 완료100% 확인.
  운영 스풀 정리·서비스 재시작·새 AX 파견은 하지 않았다.

### 최신 — Codex 인수 · 워커 Codex 전환 · 인수인계 스킬 추출 (2026-10-04, Codex)

- 문서 최신화 후 경로 재발 방지 절차를 홈/저장소 AGENTS 정본에 추가:
  확인된 작업 위치에서 `rg --files -g 패턴` 목록 조회 → 별도 호출에서 반환된 실제 경로만 읽기.
  미확인 디렉터리를 목록 조회 인자로 넣지 않으며, 같은 절차를 서브 에이전트 지시에 명시한다.
  AGENTS.md, machines/sim-desktop-agents.md, README.md, master/README.md,
  이 인수인계서의 5파일을 `f215837`로 로컬 커밋했다. push·배포는 중단된 상태다.
  홈 AGENTS/CLAUDE 심볼릭 링크를 보존한다. 인수인계는
  `master/skills/ax-handoff/SKILL.md`의 절차로 이 파일 한 벌을 갱신한다.
  기존 스킬 기능을 과거 임시 산출물에 의존하는 실행 절차로 바꾸지 않는다.
  배달이 다시 요청되면 `master/skills/distribute/SKILL.md`와
  `docs/14-onboarding-runbook.md` §3을 따른다. 소스 동기화와 배달은 별도 단계이며
  등록 전체 배달·검사 명령은 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`다.
- 이번 문서 재개: 앞서 승인한 실제 소스 대조·로컬 서브 에이전트 방식을 유지한다.
  README·master/README·홈/저장소 AGENTS·CLAUDE 진입 문서와 이 파일만 대상으로 한다.
  7파일 최신화 완료·미커밋. 인수인계/모드 선택의 정본 스킬 연결, 새 work 기본값과
  기존 스탬프 유지, 로컬/원격 커밋 차이와 미배포 상태를 바로잡았다.
  서브 에이전트는 진입 문서 4파일을 담당했고 종료했다. 지휘자가 실제 diff를 재검토했다.
  검증: `git diff --check` rc0, 지휘자 확인 문서 링크 7/7·에이전트 확인 관련 링크 12/12,
  홈 AGENTS/CLAUDE 심볼릭 링크 보존 확인. 문서 변경이라 코드 검사는 추가 실행하지 않았다.
  상태 조회 `conductor.snapshot()`에서 master=codex, worker=codex/source=state,
  마지막 저장 20:52:56을 재확인했다. readiness 3/3은 앞선 전환 당시 결과이며
  이번 문서 작업에서 새 원격 실행·readiness·서비스 검사·Redmine 변경은 하지 않았다.
- 사용자 보충으로 #733 후속을 인수했다. 실제 `HEAD=origin/main=d020132`, 편집 전 clean 확인.
  `master/test_usage_cli_paths.py`의 checks.json 등록·출력 패턴 확인. **통합 19/19(신규 40건),
  Redmine #733 노트·열림 및 #734 신규 등록은 사용자 인계 내용이며 이번 세션에서 재조회하지 않았다.**
- #728은 앞 절의 실제 Antigravity 리뷰 기록(입력 29,589·출력 11,598, 합 41,187) 확인으로 완료.
  #733은 실제 Claude JSON 호출·게시판·층2 기록 확인이 남았다. #734는 현재
  `master/projects/mcp_server.py`의 `get_code()`가 `generate.dispatch()`의 필수 `context`를
  빠뜨리는 것을 소스로 확인했다. 경로 사용 여부와 유지/제거 판단은 미착수.
- `ax-projects` 실조회: MainPID 139669, 20:33:53 기동, active/running, Result=success.
  이번 세션에서 재시작하지 않았다. HTTP 화면 200은 사용자 인계 내용이며 재조회하지 않았다.
- 사용자 「클로드 토큰을 모두 사용했으니 워커들도 모두 코덱스」 지시.
  현재 세션에 AX MCP 없음; ax-mode의 직접 fallback와 실제 MCP 호출 경로 차이를 보고했고,
  사용자 승인으로 정본 `conductor.set_worker('codex', why=…, by='codex')` 사용.
  첫 sandbox 호출은 scp 읽기 실패(BundleError); 승인된 동일 명령을 sandbox 밖에서 실행해
  **20:42:28 Codex 전환**, AXCluster `.43`·`.2`·`.33` readiness **3/3**, Codex 0.159.3.
  readiness는 배달물·예약 런처 등록 검사이며 실제 로그인/셸/편집 실행 성공 검사는 아니다.
- `conductor.record_master('codex', …)` 20:43:36 실행 후 snapshot 재조회:
  master=codex, worker=codex, source=state. 담당 기록은 잠금/프로세스 판정이 아니다.
  **새 work 등재부터 Codex 스탬프**. 기존 work의 모드를 소급 변경하거나 새 파견을 하지 않았다.
- 사용자 「인수인계와 워커 지휘자 선택을 스킬로」 요청. 이번 작업에 한해 RAG MCP 부재를
  실제 소스 대조로 대신하고 **로컬 서브 에이전트 방식** 승인.
  `master/skills/ax-handoff/SKILL.md` 신규·`ax-mode` fallback 정정·홈/저장소 진입 지침 연결 완료.
  두 스킬 quick_validate rc0, git diff --check rc0. Claude 홈·Codex legacy/공식 홈 경로의
  ax-handoff 심볼릭 링크가 같은 저장소 정본을 가리킴을 확인했다. 홈 AGENTS/CLAUDE 링크 보존.
  Codex 홈 등록 첫 시도는 sandbox read-only로 실패해 승인된 좁은 등록 스크립트로 완료했다.
  독립 검토: 인수인계만 확인할 때 쓰기 없음·Codex 선택 시 준비 검사·실제 호출 이름 일치 확인.
  추가 조회에 없는 경로를 넣어 rc2가 된 에이전트 조회 실수가 있어 그 추가 조사는 중단했다.
  새 스킬은 work 스탬프 계약을 명시한다. machines/sim-desktop.md의 옛 「다음 조각부터」
  설명 두 곳도 이번 문서 최신화에서 실제 계약에 맞게 고쳤다. 전체 통합 검사는 이번에 재실행하지 않았다.
  드라이런 시점에는 커밋·푸시 승인이 없었다. 후속 사용자 요청으로 이 7파일의 커밋·Gitea push와
  ax-mode Codex 설정 재호출을 승인받았다. 서비스 재기동·워커 재배달·신규 파견은 요청하지 않았다.
- 사용자 「드라이런 먼저」 요청 후 기존 정본 검사만 격리 실행:
  `.venv/bin/python -B -m unittest master.test_orchestration_control master.test_worker_mode_transport -v`
  **21/21**(control 18·transport 3), `.venv/bin/python -B master/test_work_mode_stamp.py` **15/15**.
  실제 준비 검사에는 가짜 워커/런처 응답을 주입하고 상태·큐는 임시 환경을 사용한다.
  준비 실패 저장 차단·마스터/워커 분리·환경 우선순위·모드 전달·기존 work 스탬프 유지 확인.
  검사 전후 운영 conductor.json/mode.json SHA256, snapshot, git status 및 diff SHA256 모두 동일.
  이후 이 결과 기록만 인계서에 추가했다. 실제 원격 작업·파견·서비스 변경은 실행하지 않았다.
  독립 스킬 판단 드라이런 4상황 확인: 인계 조회만/명시 Codex 선택/.2 준비 실패/
  전역 Codex+기존 Claude round 2. 형식 검사뿐 아니라 호출 선택·승인/중단·스탬프 경계를 검토했다.
  실제 새 Claude/Codex 세션의 자동 스킬 선택·원격 셸 실행까지 검증한 것은 아니다.

### 최신 — 색인기 막힘 해소 · #732 완료 (2026-10-04 18:12, Claude)

- 수동 재합성 루프(`scratchpad/unstick.sh`)는 17:48 `a8b033b` 에서 **형식이 아닌 사실 게이트 거부**로 설계대로 중단했다.
  거부: `master/webui/routes` 「주석에만 있는 식별자: `_CONTEXT_SHELL_CSS`, `_SIDE_VARS`」 — 실제 코드 상수(routes.py:109·114).
  gemma3:12b 1회 재합성도 같은 거부 → 모델 문제 아님.
- 원인(재현): `verify.strip_comments` 가 C++ 전용이라 파이썬 주석 `# … static/*.html` 의 `/*` 를 블록 주석으로 읽어 뒤 코드를 삼켰다.
- 사용자 결정: 파일 종류별 규칙(C/C++·C#·Java·Python·HTML(규칙만)·XML·INI·JSON/.uplugin/.uproject) · 모르는 확장자는
  「주석에만 있는 식별자」 판정 생략(a) · 로컬 서브 에이전트. `synth.py` 프로젝트 live 집합도 같은 규칙(사용자 승인).
- `fc9c4de` push → 색인기가 **사람 개입 없이** routes 를 gemma4:e4b 로 통과 → 커서 HEAD · 리뷰 큐 pending 0 · done 31 · abandoned 15.
  워커 조각 4개·`e3b1513`·`d548b40`·`a8b033b`·`fc9c4de` 리뷰 완료(조각 지적: usage_page 1 · usage_dashboard 2).
  #732 노트 2건 + 「완료」 처리(사용자 「닫고」).
- 남은 한계(#732 노트): HTML 속성값 안 `<!--` · `.hh/.hxx/.cxx` 미등록 · INI `#` 줄은 근거 미확인으로 live.

**미결 / 다음 (최신)**:

1. [부분 확인 18:3x] `/ontology`·`/ontology/domain/Any` 를 Chrome(2560×945)으로 봤다 — 사이드 메뉴 7항목·`.on` 정상,
   원전 트리·패널·버튼 유지, 가로·세로 스크롤 없음, 그래프 영역 x=800~2560(1760×945) · 컨트롤 버튼 정위치.
   **미확인**: 실제 그래프 렌더링(AXCluster 는 `domains: []` — 데이터 없음, 마운트 전환 필요) ·
   760px 미만 배치(창 크기 변경 요청이 적용되지 않음 — 최대화 추정).
2. `fix_flow prepare` fetch 미강제 — 수정/일감화 미결.
3. [완료] 워커 3대·`.43` 관리 클론 `66a7a1f` 동기화 + 배달 3/3 · `.2` MCP 경고는 오탐 — `3e46078` 수정(다음 배달에서 소멸 확인).
4. #726 · #727 · #728 미착수. [완료] `d189f21` — `checks.json` 에 `test_usage_*` 4·`test_webui_side_nav`·`test_verify_filetypes`
   등록, 통합 검사 **18/18**. 그 5개 unittest 모듈은 스크립트 단독 실행 시 `No module named 'master'` 로 죽었다 — 다른
   테스트와 같은 `sys.path.insert(…parents[1])` 를 넣었다(`-m unittest` 23/23 유지).
   [완료] **Antigravity 토큰 기록**(#728, `8d67744`) — `call_agy_why` 를 `--output-format json` 으로 부르고 sink 안이면
   호출당 1행 · 리뷰 퇴고를 초고와 같은 sink 로 · 대시보드는 lane agy → gemini `Antigravity(모델 미상)`(agy JSON 에
   모델 키 없음 — 실측 agy 1.2.16). ax-projects 20:12:57 재기동. **라이브**: R34(`8d67744` 리뷰) → usage_log
   lane=agy · 입력 29,589 · 출력 11,598(추론 10,800) · `/api/v1/usage` gemini 1건 41,187. sink 밖 경로는 **#733** 로 분리.
5. `advance_work(confirm=True)` 트리 수정 소실 문제 미결 · 옛 로컬 브랜치 `task/20261003_2315_719…/base` 잔존 ·
   `.43 .ax/work` 잔재 2개 · 위키 [[아이디어수집]] 에 #729~#731 절 미기재(쓰기 경로 없음 · API 401).

### 최신 — #725 후속: 분류·사이드 메뉴 배포 · 색인기 막힘 · 일감 3건 (2026-10-04 17:46, Claude)

**배포 (사용자 「a-1로 하고 ① 같이 고쳐줘, 로컬 서브 에이전트로」 → 「커밋하고 푸시하고 배포해줘」)**:

- 로컬 서브 에이전트 2개(파일 비중첩) → 제가 합친 상태로 재검사: 웹UI 6파일 rc=0 · 사용량+새 메뉴 23/23 · 통합 12/12.
- `d548b40 fix(usage): classify dispatch records by conductor mode` — `mode`(claude/codex)를 model·lane 이 둘 다 빌 때만
  쓴다. 실데이터 9/1~10/4: unknown 16 → **claude 16**(캐시 포함 5,642,553 토큰).
- `a8b033b feat(webui): shared side nav on every page` — `/`·`/ontology*`·`/cluster` 는 `routes.wrap_side_nav` 로
  **서빙 시점** 감싼다(원전 `web_ui_original.py`·`static/` 바이트 불변, 2026-08-13 지시 유지) · `/reviews` 는 공용 셸.
  `status.py` 미수정(`cluster.html` 자족·외부 자원 0 테스트). 예전 주입 링크 버튼은 제거, 원전 바이트 속 링크는 남김.
  새 테스트 `master/test_webui_side_nav.py`.
- [주의] **브라우저 확인 안 했다** — `/ontology` 그래프(100vh)가 230px 좁아진 열에서 적응하는지, 760px 미만에서
  메뉴가 위로 쌓여 스크롤이 생기는 것, 메뉴 배경 `#161b22` vs 원전 `#1e1e1e`.

**`.2`·`.43` 동기화 질문 (사용자 「리뷰 작업 시작할 때 풀 받는거야?」)**: 두 워커 체크아웃 모두 `3d54637`(origin 추적도
같음, fetch 이후 없음). 파견은 `wcommit.py:135` 가 `fetch --all` 뒤 base 커밋에서 새로 가르므로 무관. `ax-fix` 는
`check` 가 `fetch origin main` 후 `origin/main` 대조(`fix_flow.py:233`) — 그러나 **`prepare` 는 스스로 fetch 하지
않는다**(`fix_flow.py:350`) · 순서를 코드가 강제하지 않는다. 고칠지·일감화 **미결**. `.43 .ax/work` 에 조각 아닌
잔재 2개(`ax_smoke_…` 10/3 12:14 · `ax_codex_readiness_…` 10/3 23:51) — 원인 미조사.

**색인기 막힘 (`#727`)**: `master/webui/app` 합성이 gemma4:e4b 에서 형식 게이트(frontmatter 누락)로 5회 중 4회 거부 →
커밋 단위 트랜잭션이라 커서가 멈춰 뒤 커밋의 합성·**자동 리뷰 등재**가 막혔다. 사용자 「2번」 → 「가로 진행」:
멈출 때마다 그 그룹만 `synth.run(changed=[app.py], commit=<멈춘 커밋>, model=FALLBACK_MODEL gemma3:12b)` 로
수동 재합성. 루프 스크립트 `scratchpad/unstick.sh`(색인 실행 → 형식 거부면 재합성 → 반복; 같은 커밋 재정지·비형식
사유·15회면 중단). 17:44 시점 커서 `e3b1513` · 리뷰 큐 pending 5 · running 1 · done 26 · abandoned 10.
수동 문서는 품질이 낮다(태그 줄에 `영문태그:` 잔재 · `UViewApp` 실재 미확인).
[주의] `3abcdb1a` 는 `app.py` 를 안 바꿨는데 `app` 그룹이 대상이 됐다 — 형제 커밋 순회 시 비교 기준 문제로 보이나 미검증.

**자동 리뷰 (질문 「분산 작업 끝내고 커밋했는데 자동 리뷰 시작해?」)**: 색인기가 커밋을 걸으며 리뷰 큐에 등재 →
`ax-review-queue` 가 로컬 초고 + **Antigravity 퇴고**. 작성자 `ax-cluster`(ADVANCE·머지)는 제외(abandoned)가 정상.
`f6f5aecb` 리뷰는 「행 0」(지적 0건)으로 저장됐다.

**토큰·agy (`#728`)**: 대시보드 gemini 0건은 화면이 아니라 기록 부재 — `review_runner.py:383` 의 `usage.sink` 가
초고만 감싸고 agy 퇴고(:396)·층2(`layer2_verify.py:128`)는 기록 경로가 없다.
마스터 대화 세션의 Claude 사용량은 `/usage?source=session` 에만 보인다(두 소스는 겹칠 수 있어 합산 안 함).

**미결 / 다음 (이 절)**:

1. 색인기 루프 결과 확인 → 리뷰 큐 상태 보고(사용자 요청 대기 중).
2. `/ontology` 등 사이드 메뉴 화면 브라우저 확인.
3. `fix_flow prepare` fetch 미강제 — 수정/일감화 미결.
4. 워커 3대 `master.client update`(ff-only + 재배달) 미실행 — 사용자 승인 필요.
5. #726 · #727 · #728 미착수 · `checks.json` 에 `test_usage_*`·`test_webui_side_nav` 미등록 ·
   `advance_work(confirm=True)` 트리 수정 소실 문제 미결 · 옛 로컬 브랜치 `task/20261003_2315_719…/base` 잔존.

### 최신 — #725 사용량 웹페이지 라운드 1 전진·마감·배포 · 지휘자 claude 전환 (2026-10-04 17:20, Claude)

**경위**: Codex 가 `#725`(「[AX] LLM 모델별 기간별 작업·토큰 사용량 웹페이지」)를 등재·파견한 뒤
이 문서를 갱신하기 전에 토큰이 소진됐다. 원요청: 레드마인 일감 기준 LLM(클로드·코덱스·제미나이·로컬)의
일간·주간·월간 작업과 토큰을 웹UI 신규 페이지로 시각화.

**work**: `20261004_1645_ax_llm_e6a404f5` · round 1 · 조각 4(codex 지휘) · 파견 4/4 · 실패 0 · 16:58:30 `ready_for_review`.

| 조각 | 워커 | 파일 |
|---|---|---|
| 0747b703 | .33 | `master/work/usage_dashboard.py` + `master/test_usage_dashboard.py` |
| d74ea13e | .43 | `master/webui/usage_page.py` + `master/test_usage_page.py` |
| 84fe23ff | .2 | `master/webui/app.py` + `master/test_usage_routes.py` |
| adb7d5fb | .2 | `master/webui/nav.py` + `master/test_usage_nav.py` |

**⑺ 전진 (사용자 「머지하고 검사 진행해줘」 → 「a로 고치고 재검사해줘」 → 「커밋하고 전진해줘」)**:

- `advance_work(confirm=False)` 로 4조각 머지 — 충돌 0, `610fdf4 → 75f70cc`.
- 사용량 테스트 13/15 — 실패 2, 둘 다 테스트 쪽 버그:
  ① 주간 9/28 기대값 4 → 3 (골조 계약 start/end 양끝 포함상 9/30 호출은 범위 밖 — 구현이 맞다)
  ② 400 안내 문구 검사 「잘못」 → 「올바르지」 (같은 조각의 테스트·구현 불일치).
- 수정 커밋 `e3b1513` · 재검사: 사용량 15/15 · `tests/integration` 12/12 · 웹UI 관련 회귀 18파일 통과.
- `task/20261004_1645_ax_llm_e6a404f5/base` **`610fdf4 → e3b1513` push**(fast-forward, force 없음) ·
  레드마인 #725 전진 노트(서버 ok:true). 검수 트리 `~/ax-advance-…` 는 지웠다.
- [주의] 테스트 실행법: `master` 는 패키지가 아니다. `unittest discover -s master` 는 상대 import 를
  깨뜨려 가짜 오류 3건을 낸다 — 저장소 루트에서 `python -B -m unittest master.test_usage_…` 로 돈다.

🔴 [주의] **`advance_work(confirm=True)` 는 트리 안 수정 커밋을 잃는다** — 재호출 시 검수 트리를
`worktree remove --force` 하고 origin 에서 재머지한다. `ax-advance` 스킬의 「버그면 이 트리에서 고쳐
커밋 → confirm=True」 순서는 현 코드로 성립하지 않는다. 이번엔 그 함수가 내준 push 명령을 손으로
실행했다. **고칠지·일감화할지는 사용자 미결.**

**토큰 (usage_log.jsonl, codex 지휘)**: 입력 합 4,054,512 중 캐시 3,814,144(94%) · 비캐시 약 24만
(조각당 5~7만) · 출력 약 1.7만. 누적 재전송은 에이전트 루프 공통(claude 도 같다). 원본 실행 기록은
남지 않아 사후 분해 불가 → **#726** 등록(측정 로그: 첫 턴 입력·턴 수·턴별 비캐시·읽은 파일,
codex·claude 비교표가 완료 조건). 착수 안 함.

**마감 (사용자 「#725 마감해줘」 → 「1~3 모두 진행해줘」)**:

- `finalize_work(confirm=False)` 로 먼저 통합 — `e3b1513` 포함 확인 · 8파일 +1,274 · 사용량 15/15 ·
  `tests/integration` 12/12 · 웹UI 회귀 6파일 rc=0. 그 뒤 `confirm=True`.
- **main `99147c4`** push · 큐 `merged` · 레드마인 #725 **완료**(마감 노트에 머지 커밋) ·
  원격 `task/20261004_1645_ax_llm_e6a404f5/*` 5개 삭제(전부 main 도달 가능, 잔존 0).
  조각 4개는 base 에 이미 든 상태라 「매니페스트 전용 — 머지 안 함」으로 찍힌다(정상).
- 마스터 체크아웃 `git pull --ff-only` (`6bb8a23 → 99147c4`) · `sudo -n systemctl restart ax-projects`
  (rc=124 polkit 대기였으나 ExecMainStartTimestamp 17:16:22 · 새 PID 로 판정 — 성공).
- `/api/v1/usage` 실데이터: 기본 30일(09-05~10-04) 호출 1,967 · 토큰 약 3,288만 · 연결 일감 13 ·
  **미연결 호출 1,899** — 대화 세션 사용분으로 추정하나 연결 규칙은 미검증.
- 정리: Codex 골조 worktree `~/ax-usage-…` 와 로컬 브랜치 `task/…/base`(`610fdf4`, main 포함 확인) 삭제.

**미결 / 다음**:

1. `test_usage_*` 4개는 `tests/integration/checks.json` 에 미등록.
2. `advance_work(confirm=True)` 가 트리 안 수정 커밋을 잃는 문제(위 🔴) — 고칠지·일감화 미결.
3. 미연결 호출 1,899건이 의도대로인지 확인.
4. 파견 로그의 `rmcp … 127.0.0.1:8000/mcp` 연결 오류(결과엔 영향 없음) — 원인 미조사.
5. `#726` 측정 로그 — 등록만, 미착수.
6. 옛 로컬 브랜치 `task/20261003_2315_719_target_files_316d6d14/base` 잔존 — 이번 작업과 무관해 두었다.

**진행 프로세스**: 파견·재기동 끝, 서브 에이전트 없음. 마스터 Codex 프로세스(pid 20028)는 17:20 재조회 시 없음(종료됨).

### R19 함수 정리·업로드/배포 승인 — 2026-10-04 후속

사용자 자동 리뷰 분석·상태 정리 뒤 R19의 lambda를 일반 함수로 수정하도록 승인했다.
로컬 구현/독립검토로 conductor.py의 value를 동일 동작의 지역 def로 정리,
메인 orchestration_control18/18 및 diff 검사 통과. R19-1 applied 기록됨.
「상태 변경하고 푸시하고 배포해줘」로 구현 커밋 연결·Gitea push·AXCluster3워커
소스동기화/배달 및 ax-projects 재시작을 승인받았다. 검증 근거는 리포트92,
실제 배포 결과는 #716 후속 노트로 대조한다.

### R9 수정·전체 드라이런 — 2026-10-04 후속

사용자 R9 검증→수정→로컬 서브 에이전트→드라이런→커밋/푸시/배포 승인,
조회 경로 오류로 중단한 뒤 「리뷰 상태도 변경해주고, 소스코드 올려」로 재개했다.
`infer.py` 상한 안내에 quota 제외 조건 추가, `test_infer.py` 실제 경로 회귀31건 추가.
infer154/154·revise64/64·독립 신규31/31·전체12모듈591건 통과.
기본 sandbox source_scope 실패는 승인된 동일 전체 검사 재실행으로 통과했다.
추가 메모리 역검증은 mock 연결 오류로 실패하여 성공 근거에서 제외했다.
리포트91은 배포 전 검증 기록이며 실제 업로드·워커 배달·서비스 반영 결과는 #716 후속 노트로 대조한다.
기존 c53cfc2 및 아래 종료 기록을 보존해 커밋·푸시하고, R9-1 applied 상태를 구현 커밋으로 기록한다.

### 세션 마감 — BC-250 종료 요청

사용자 「오늘은 여기까지 할게. BC250 꺼줘!」. 문서13개는 c53cfc2로 커밋 완료,
작업 트리 clean 확인; 이 커밋은 아직 푸시·재배달하지 않았다.
종료 전 실조회: 실행 중 큐 작업0, bc250 브로커 inflight0, 원격 Codex/Claude/Python/Node 프로세스0.
`.43`에 `sudo -n /usr/bin/systemctl poweroff` 실행 rc0. 이후 SSH 재조회는 접속 타임아웃으로
노드의 접속 종료를 확인했다. 다른 노드는 종료하지 않았다.
다음 세션에는 `.43` 전원을 켠 뒤 상태를 확인한다.
이 종료 기록은 c53cfc2 뒤의 미커밋 문서 변경이다.

### 최신 — R5 재검토·색인기 테스트 배포·문서 정리

**사용자 결정**: R5 검토→원인 조사→수정 승인→로컬 서브 에이전트 선택→드라이런→
「커밋 푸시 배포하자」→R5 재검토→「수정해줘」로 applied 처리→문서 최신화·인수인계 요청.
같은 작업의 로컬 방식을 문서 정리에도 유지했다. 이후 사용자 「커밋해줘!」로 문서 커밋 승인.
줄 끝 공백4곳을 정리하고 문서13개를 커밋한다. 푸시·재배달 승인은 받지 않았다.

**완료와 근거** ([리포트 90](../reports/90-r5-indexer-test-isolation-and-deployment.md)):

- R5는 골조493601d7 리뷰로, 지적10건은 후속 구현에 모두 반영돼 있다. 구현 커밋은 리포트90 표.
- 관련 첫 검사 indexer101/103의 원인은 초반 테스트가 실제 합성 브로커에 의존한 것.
  환경변수 설정+외부 호출 차단에서도 같은2건 실패, 성공 fixture 주입으로103/103 대조 실증.
- `master/test_indexer.py`만 코드 수정: 기존 synth_writes를 공용화, 성공 호출6곳에 명시적 주입.
  실패·NoChange·맞춤 합성·비활성화 검사는 보존. 운영 consumer의 스탬프 가드는 정상이다.
- 외부 연결 차단 직접 실행·manifest run_check 각각103/103, 연결 시도0.
  전체 통합12모듈560건 OK. 첫 실행 source_scope 실패는 sg gitea의 sandbox audit 제한;
  승인된 `/tmp/ax-r5-integration-dryrun.sh` 동일 검사 재실행으로 통과했다.
- b53fd84 커밋·Gitea push·ls-remote 확인. AXCluster3워커 main/clean 확인 후 ff-only 동기화,
  plan/deliver/check3/3 OK, payload10개·프로젝트 스킬·출처일치, 워크숍 소스clean3/3.
  `.2`의 기존 Claude MCP 대조 경고와 홈 중복 스킬 주의는 별개이며 Codex 프로젝트 설정은 통과했다.
- 배포 후 관련194/194 재검사. 사용자 승인으로 R5-1~10 모두applied 기록, 재조회10/10.
  `<twin>/fixes/index.json`은 런타임 정본, 다른 status 불변, 원본 리뷰 보존.
- Redmine #716에 종합 근거 노트를 기록·재조회 확인했고 상태는 신규로 유지했다.
  실조회 #718/#719/#722 완료, #716/#700/#701/#720/#721 신규.

**이번 문서 커밋 대상**: README.md, CLAUDE.md, AGENTS.md, machines/sim-desktop.md,
machines/sim-desktop-agents.md, master/README.md, docs/14-onboarding-runbook.md,
docs/windows-codex-remote.md, docs/orchestrator-rules.md, 이 인계서, reports/README.md,
reports/89-codex-worker-readiness-and-write-probes.md, 새 reports/90-r5-indexer-test-isolation-and-deployment.md.
홈 CLAUDE/AGENTS의 심볼릭 링크는 보존했다. 코드파일은 추가 변경하지 않았다.

**다음 세션**:

1. 위 main HEAD·문서 diff·R5 applied10건·Redmine 노트를 실제로 대조한다.
2. 이번 문서 커밋을 실제 git log로 확인하고, 푸시·재배달은 사용자 요청이 오면 실행한다.
3. #720 한도 이벤트 파싱, #721 Claude 인증 만료 검사, #716 완료 판단은 사용자가 선택한다.
   #700/#701은 코드 반영 기록과 별개로 Redmine이 신규라 완료로 단정하지 않는다.
4. `.ax` 쓰기 실패 근본 원인은 미확정. 세 워커 도구 실증을 새로운 Codex 분산 work의
   큐 등재~통합~finalize 완주로 확대하지 않는다. #719 다중 파일 조각 워커 완주도 미검증이다.

**진행 프로세스·에이전트**: 이번 진단·드라이런·배포 명령은 모두 종료했다.
indexer_fixture와 docs_entrypoints 로컬 에이전트는 담당 산출물을 반환했고 편집 중인 에이전트는 없다.
기존 AX 서비스는 계속 동작한다. 과거 failed/cancelled work나 운영 큐는 이 마감에서 정리하지 않았다.
문서 마감으로 현재 AX 큐가 비었다고 주장하지 않는다.

### 최신 (00:11) — 운영 반영과 Codex 전환 완료

사용자 「진행해줘」 승인으로 검증된5파일을 `00f8532` 커밋·Gitea push했다.
AXCluster 워커3대는 main/clean 확인 후 ff-only → 00f8532, 깨끗한 마스터에서 plan/deliver 실행.
`check AXCluster` **3/3 OK**, payload10개·프로젝트 스킬·태그·출처 HEAD 일치.
`.2` Claude 로컬 MCP 대조 주의는 기존과 같이 재현됐으나 Codex 프로젝트 설정 대조는 통과했다.
`ax-projects` 전용 도구 재기동 → 00:09:13 active/running·Result success.
공용 `set_worker_mode_tool('codex')` 00:10:33 성공(운영 readiness3/3), get 도구 재조회 source=state/codex 확인.
기존 등재 work의 모드 스탬프를 바꾸거나 신규 work를 파견하지 않았다.
Redmine #716의 이전 검증 노트는 중복 작성 없이 재조회 확인. 기록 스크립트의 str 반환값 오독은 고쳤다.
운영 결과 기록을 이 문서·리포트89에 추가했다. 사용자 「커밋해줘!」로 두 문서 커밋 승인.
푸시·재배달 승인은 없으며 운영 코드·배달 출처는00f8532 그대로다.

### 최신 (23:59) — Codex 워커 전환 준비 수정·검증 완료, 운영 반영 대기

사용자 로컬 방식 및 재개 승인으로 구현/독립검토. 리포트 [89](../reports/89-codex-worker-readiness-and-write-probes.md).
`master/work/conductor.py`와 `master/test_orchestration_control.py`만 코드 수정:
Session0 Codex 실행 probe → 실제 /IT LIMITED 예약 런처 XML·SSH 계정/SID·경로·배달 런처 검증,
프로젝트 로컬 `.agents/skills/ax-work` 확인. 정적 등록 검사와 실제 도구 실행은 별도로 표시한다.
루트 회귀18/18 OK·diff check OK, 수정 준비 검사 실측3/3 ok.

실제 Codex shell read·apply_patch completed·정확한 수정 결과·회수:
`.43` 성공, Windows 소스 경로 `.2`55초/`.33`43초 성공. Windows 진단 원본은 `.ax`에 보관 후
생성 파일만 제거해 두 트리 clean 복원. 첫 Windows `.ax` 대상 apply_patch는 실패했으며,
권한/런처/바이너리를 바꾸지 않은 소스 경로 비교는 성공했다. 실패 원인은 확정하지 않았다.
없는 경로·접근 거부 읽기 조회는 이번 작업에서만 계속 조사하도록 사용자 예외 승인.
첫 fixture SyntaxError는 재개 승인 후 고쳤다. 실제 실행 실패 중단 규칙은 유지.

아직 미실행: 커밋·Gitea push·서비스 재기동·운영 codex 모드 전환·소스 동기화·재배달.
워커 source HEAD 세 대 `a3eb788`(clean), 마스터90a65a5와 다름. 준비3/3를 전체 배달 버전 일치로 보지 않는다.
운영 워커 모드는 여전히 claude이며, 승인 뒤 서비스 반영과 공용 MCP codex 전환을 확인한다.
#720/#721 수정과 #716 완료 판정은 범위 밖. 아래23:25 기록은 수정 전 상태다.

### 최신 (23:25) — Codex 가 이어받을 자리

**오늘 끝난 것** (근거: 리포트 88 · Redmine 노트)
1. AXCluster 첫 분산 작업 #718 — #260·#375·#615 를 2라운드(3/3·4/4)로 → `f22f741`.
2. #719(조각의 `target_files` 중 첫 파일만 전달) — 분산 작업 #722, 한 파일짜리 조각 5/5 → `90a65a5`.
   `models.TaskRegisterReq.target_files` · `logic.register_task` 정규화 저장 · `register_tasks` POST ·
   `infer.task_targets()`. 재기동 뒤 실경로 확인: 다중 파일 조각 등재 → 큐 레코드 `target_files` 두 파일 →
   즉시 취소(파견 없음). [주의] **워커가 다중 파일 조각을 끝까지 채우는 완주는 아직** — 다음 실전 work 에서 본다.
3. 통합 검사 목록 7→12: broker_routing·workshop_check·source_scope·python_commit_review·build_local·
   skeleton_gate·revise·indexer·version·task_data·infer·integration_checks. 넣기 전 격리 실행(`unshare -rn`·
   가짜 ssh/scp/curl·임시 HOME)으로 부작용 0 확인. `test_client_spec`(실토큰·`.ax/` 캐시 쓰기)·`test_nowork`
   (요약에 건수 없음)은 제외.

**다음 후보 (사용자가 고른다 — 지휘자가 고르지 않는다)**
- **#720** codex 사용 한도가 한도 갈래로 안 잡힘 — JSON `error`/`turn.failed` 문구가 판정 입력 `c.notes` 에 없다.
  고칠 자리 후보: `usage.py`/`runner.py` 의 codex 이벤트 파싱. **codex 지휘로 돌릴 때 가장 먼저 아프다.**
- **#721** 지휘자 준비 검사가 인증 만료를 못 잡음 — `claude auth status`(JSON `loggedIn`) 추가 검토.
- #716 종결 판단(사용자).

**분산 작업 절차 — 오늘 실측한 순서** (`master/skills/distribute` + 아래 스크립트 형태)
1. RAG(`search_context_tool`) → 소스 대조 → 분해안 제시 → 사용자 승인.
2. 대상 모듈의 테스트가 `tests/integration/checks.json` 에 있는지 본다. 없으면 격리 실행으로 부작용을 확인하고 먼저 넣어 커밋.
3. `register_work(…, fixed_version="마일스톤 6 — 개선·확장")` 를 **Python 으로** 부른다 — MCP `register_work_tool` 은
   마일스톤을 못 넘겨 무버전 이슈가 된다. 등재 직후 파견은 「base 없음」으로 기다린다(정상).
4. `git worktree add -b task/<work>/base <옆 경로> origin/main` → `[DOC]`/`[PSEUDO]` 골조 → 커밋 →
   `skeleton_gate.check_head([조각 파일])` 조각별 → `git push origin task/<work>/base` 가 파견을 깨운다.
   지금도 **조각은 한 파일씩**이 안전하다(#719 는 고쳤지만 워커 완주 미확인).
5. 끝나면 `review.advance_work(confirm=False, build_fn=local_test_fn(start_dir="tests/integration",
   pattern="test_axcluster.py", python="/home/sim/ax-cluster/.venv/bin/python"))` → 실제 diff·`[PSEUDO]` 잔존·
   검사 건수 증가를 직접 보고 「버그냐 구조냐」를 사용자에게 → 승인 뒤 `confirm=True, decision_note=…`.
6. 더 고칠 것은 `improve_work(work_id, round=현재+1, specs)` · 끝이면 `review.finalize_work(confirm=True)`
   (main 머지·브랜치 정리·이슈 완료) → 마스터·`.43` `git pull` → 바뀐 코드가 서비스 안이면 재기동 승인.

**함정 (오늘 실측)**
- work 는 등재 시점 지휘자 모드로 **스탬프**되고 바꿀 표면이 없다(#392). 모드를 바꾸려면 조각 취소 → 재등재.
- `sudo -n systemctl restart ax-projects` 는 종료가 1분+ 걸려 명령이 늦게 돌아온다 — **기동 시각으로 판정**.
- `.43` 은 헤드리스 — 인증 복구는 사람이 별도 터미널에서 `ssh sim@192.168.0.43` → `claude auth login`
  (또는 codex 로그인). 마스터 세션의 원격 로그인 기동은 자동 권한 판정이 거부했다.
- 마감 뒤 색인·리뷰 큐가 워커 Ollama 를 수십 분 쓴다. 리뷰 큐는 `[ADVANCE]` 머지 커밋을 「diff 없음」으로 포기한다(정상 판정, 실패로 집계).
- 원격 노트·커밋 메시지는 **파일로 써서** 넘긴다(백틱 셸 치환 사고 2회 기록).

**남은 정리**
- 로컬 브랜치 `task/20261003_2315_719_target_files_316d6d14/base` — main 에 포함, 삭제 승인 대기.
- 이번 #719 경과는 리포트로 아직 안 썼다(리포트 88 은 #718 까지). 필요하면 89 로.


### 최신 — AXCluster 분산 작업 완주 (리포트 88)

- work `20261003_2046_axcluster_claude_260_375_615_54c7eb59`: 라운드1 3/3 → ⑦ 전진 → 라운드2 4/4
  (첫 파일만 전달된 결함 #719 때문에 남은 4파일을 한 파일짜리 조각으로) → ⑦ 전진 → finalize `f22f741`.
  브랜치 8개 자동 정리 · #718 완료. main 에서 통합 검사 `TESTS OK (10)` 426건.
- 첫 등재 `…_67758157`(codex 스탬프)은 codex 한도로 실패 → 조각 취소·work cancelled. 그 브랜치 5개(원격 base·미병합 조각 3 · 로컬 base)는 사용자 확인 후 21:40 삭제했다(조각 3개는 피드백 주석 커밋뿐).
- 마감 뒤 후속 처리: 색인 커서 `611fdba7→f22f741b`(#375 판정 첫 운영 통과) · 리뷰 큐 완료 12(R8~R12 등) · 포기 5 — 전부 `[ADVANCE]` 머지 커밋(고유 diff 없음 → deterministic 포기). 21:39 큐 0건.
- `.43` claude 인증은 사람이 `claude auth login` 으로 복구(21시경). 다음 세션은 #721 이 고쳐지기 전까지
  모드 변경 뒤 `claude auth status` 를 워커마다 직접 본다.
- 남은 판단: #719~#721 착수 순서 · #716 종결 여부 · 아래 이력의 「남은 일」은 이번에 대부분 소진됐다.


### 검증 완료 — Claude 인계 후 (최신, 아래 Codex 서술의 「미완료」를 대체)

리포트 [`87`](../reports/87-axcluster-integration-checks.md). 요지:

1. 5개 파일이 아래 서술과 일치. 회귀 직접 실행 15/15 OK.
2. 프로필 값으로 실제 `build_local.local_test_fn` 호출 → `TESTS OK (7)` · 3.4초 · 트리 불변.
   건수 broker14 · workshop77 · source_scope32 · python_commit_review7 · build_local36 ·
   skeleton_gate51 · integration_checks15. (샌드박스 밖 Claude 세션이라 source_scope 제약 없음.)
3. 저장소 밖 사본에 실패 주입 9/9 차단(rc1 · 0건 · 전부 skip · unittest 실패 · 파일 없음 ·
   빈 목록 · 깨진 JSON · 경계 밖 · 타임아웃). 한계: 자기 요약만 찍고 rc0 인 스크립트는 통과한다.
4. 연결: `payload/profile` → `bundle._tests_for` → 배달 `.ax/config.json` `tests` → `ax-advance`.
   **작업장 배달 전에는 효과 없음**(현 배달본 `384a07a`).
5. 공용 `parse_unittest` 가 첫 `Ran` 줄을 집어 실패 시 요약 숫자가 틀릴 수 있다(판정은 맞음).
   사용자 결정: #716 노트에만 남기고 고치지 않는다.

[완료] 커밋·푸시 `a3eb788`(Gitea · `.43 ~/ax-cluster` 동일). 워커 3대 AXCluster 체크아웃 ff-only →
`a3eb788`. 5프로젝트 `master.client update` rc=0 · 검사 15/15 OK · 출처 HEAD 일치 · AXCluster 워커
`tests` 새 값 실측. 아래 「남은 일」 1~4는 이로써 끝났다(#716 journal 참조).
[주의] deliver 가 `.2` Kimodo·AXCluster 에서 「claude_mcp_local … ~/.claude.json 에 없다」를 찍었으나
`claude mcp list` 실측은 ax-client Connected — 대조 오탐 추정, 원인 미조사.
남은 것: 분산 전체 실증(아래 5번)은 사용자 지시 대기. #716 완료 판정은 사용자 몫.

### 바로 다음 작업 — AXCluster 통합 검사 보완 (Codex 기록)

사용자 “보완작업은 어떻게 진행할거야?”→“진행해봐”로 구현을 승인했다. RAG와 기존 검사 계약을
조사한 뒤, 선택된 로컬 서브 에이전트 방식으로 구현·분류를 나눴다. 마지막 요청은 인수인계이므로
추가 검증·수정·배포를 멈췄다. **이번 변경에 대한 커밋·푸시 승인은 받지 않았다.**

문제: 기존 AXCluster 프로필의 `unittest discover -s master -p test_*.py`는
스크립트의 `__main__`/순수 함수 검사를 실행하지 않는다. 일부 TestCase만 실행돼 N>0을 만족해도
다른 검사의 누락이 감춰진다. 공용 `master/work/build_local.py`는 수정하지 않았다.

현재 구현 파일(새 파일4개 + 기존 프로필1개):

- `master/integration_checks.py`: 명시 JSON 검사 목록 검증, 각 스크립트 별도 Python 프로세스,
  rc·실행 건수·전체/실패/skip 증거 검사. 누락/0건/타임아웃/전부 skip/잘못된 목록은 차단.
  각 자식에 임시 AX_PROJECTS_ROOT·AX_GITEA_REPO_ROOT 및 -B를 적용한다.
  **환경 분리는 완전한 보안 샌드박스가 아니다. 검토된 목록만 실행해야 한다.**
- `master/test_integration_checks.py`: 실제 임시 자식 프로세스를 사용하는 회귀 TestCase15개.
- `tests/integration/checks.json`: 필수 검사7개를 명시. broker_routing, workshop_check,
  source_scope, python_commit_review, build_local, skeleton_gate 및 새 integration_checks.
  검사별180초 제한·출력 형식별 건수 정규식.
- `tests/integration/test_axcluster.py`: 목록을 읽어7개 unittest를 만들고 각 스크립트를 실제 실행.
- `master/client/payload/profile/AXCluster.yaml`: `test_start_dir: tests/integration`,
  `test_pattern: test_axcluster.py`로 변경. 나머지 프로필 값은 그대로다.

실행/검토 근거:

- 구현 에이전트 `/root/716_type_scope`가 새 회귀 검사 **직접 실행15/15 및
  `-m unittest master.test_integration_checks`15/15**, 당시 diff --check 통과를 보고했다.
  rc1·타임아웃·파일 없음·요약 누락/0건·total 불일치·failed>0·allskip·환경 비전파를 검증했다.
- 분류 에이전트 `/root/716_test_inventory`: 기존144파일 중 TestCase7파일을 AST로 식별했고
  후보9개만 전문 검토했다. **나머지135개 안전성은 미검토**, 전체144 검사 커버리지 아님.
  `test_client_bundle.py`는 실제 .33 SSH 및 기존 hooks/__pycache__ 삭제가 있어 목록에서 제외.
  layer1/project_profile은 실제 등록 프로젝트/소스 읽기 의존성이 있어 초기 목록에서 제외했다.
- 루트는 생성된 목록7개와 wrapper/프로필을 확인했고 broker·unittest 요약 샘플 정규식 매칭을
  확인했다. **전체7개 통합 실행과 실제 local_test_fn→wrapper 연결은 아직 실행하지 않았다.**
- `/root/716_independent_review`에 위5파일과 build_local 읽기 전용 리뷰를 요청했으나,
  인계 요청으로 중단을 통보했다. 반환된 부분 리뷰에서 주요 결함은 발견하지 않았고,
  프로필/discovery 호환·프로세스 분리·실패 차단·경로 검증을 확인했다.
  **검사 재실행, 7개 원본의 출력/부작용 전수 대조, 실제 어댑터 결과 검토는 미완료다.**

이어갈 순서:

1. `git status --short`와 위5파일 diff/신규 파일을 읽고, 회귀15개 보고와 구현을 대조한다.
   기존 dirty `docs/orchestrator-handoff.md`도 보존한다. 변경을 stash/reset/clean하지 않는다.
2. 프로필의 새 start_dir/pattern을 이용한 **실제 local_test_fn 통합 호출** 또는 아래 discovery를
   실행해 필수7개 모두 자식에서 실행되고 건수 증거가 통과하는지 확인한다:
   `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py`.
   source_scope는 임시 Git·sg gitea를 쓰므로 알려진 샌드박스 제약에는 좁은 실행 승인을 사용한다.
   실패 시 공용 실패중단 규칙을 따른다. fixture의 예상 실패는 테스트 성공과 구분한다.
3. 실제 프로필→공용 어댑터 연결 및 wrapper/manifest의 실패 차단을 독립 리뷰한다.
   범위 밖135검사를 자동으로 목록에 넣지 않는다. `/tmp` 전체 탐색도 금지한다.
4. 결과를 `reports/87-axcluster-integration-checks.md`(아직 생성 안 함), reports/README,
   이 인수인계 및 Redmine #716에 기록한다. **이번 보완 내용은 아직 Redmine에 반영하지 않았다.**
   스킬의 AXCluster 검사 경로 예시도 새 프로필과 일치하는지 확인한다.
5. 검증이 끝난 구체적 결과로 사용자에게 이번 변경의 커밋·푸시 승인을 받는다.
   승인 후 깨끗한 커밋에서 아래 기존 워커 동기화·재배달 과제를 이어간다.

현재 작업은 로컬 구현뿐이다. 새 운영 큐/Redmine 일감·브랜치·원격 파견·서비스 재기동·배달·
커밋·푸시는 하지 않았다. 아래15/15 드라이런 및 fixture6/6을 이7개 통합 실행 성공으로 읽지 않는다.

### 완료와 근거

- 사용자 “모두 커밋 푸시하고 동기화해” 승인으로 이전 미커밋20파일 전체를 커밋·Gitea push했다.
  Windows Codex 지침/워커 예외/브로커3노드 설정, NS 분석, #716 지침·검사·스킬이 포함됐다.
  GitHub는 Gitea 푸시 미러이며 직접 push하지 않았다. 미러 도착 자체는 이번에 따로 재조회하지 않았다.
- `distribute` 정본을 RAG→소스 대조→사용자 단독/분산 선택→서브 에이전트→실물 검증 흐름으로
  재작성했다. 등록 `kind`로 분기하며 정본7단계·병렬 기본·요청자 통합·별도 전진/finalize 승인을 유지한다.
  현재 노출되지 않은 improve/advance/finalize MCP 도구를 가정하지 않고 실제 모듈 계약으로 안내한다.
- `~/.codex/skills/distribute`와 공식 사용자 경로 `~/.agents/skills/distribute`는 모두
  `~/ax-cluster/master/skills/distribute` 링크다. 둘 다 정본/파일 존재를 재확인했다.
  **이번 인수인계 요청 직전 현재 세션의 제공 스킬 목록에 distribute가 실제 추가됐다.**
  따라서 앞선 “현재 세션 미노출” 기록은 갱신한다. 등록을 위해 반드시 세션을 닫아야 하는 것은 아니다.
  새 세션은 갱신된 진입 지침·인수인계를 다시 받는 데 유용하다.
- 타입별 더티 검사는 code SourceScope와 rename 양쪽/quoted 경로를 보호하고 index_only는 파견 제외.
  workshop77/77 + SourceScope32/32 + broker routing14/14 = 관련 검사123개 통과.
  스킬 형식 검사·독립 코드/forward 검토도 통과. code 서브모듈 내부 더티 검사는 일반화 한계가 있으나
  AXCluster는 submodules=[]다.
- `.43 ~/ax-cluster`는 ff-only 동기화 후 해시 일치. 이것은 `.43 ~/trunk/AXCluster` 워커 트리와 다르다.
- `ax-projects`는 19:24:55, `ax-broker`는 19:23:42 KST로 재기동됐다. 19:33 재조회 모두
  active/running·Result=success. 큐도 active/running이며 앞선 권한 승인 최신성 검사3서비스 모두
  stale=False·why 빈값이다. `ax-dispatch.path`·실제 따라잡기 타이머 `ax-dispatch.timer`는 active/waiting.

### 남은 일과 시작 조건

1. **작업장 동기화 재개 범위를 확인한다.** 기존 전체 동기화 지시가 있었지만, 목록 조회 오류 후
   공용 실패중단 규칙에 따른 재개 질문에 별도 답을 받지 않은 채 사용자 요청으로 인수인계를 작성했다.
   실패는 필수 AX_PROJECTS_ROOT 누락 조회였으며 루트 명시 재조회가 성공했다. 코드/서비스 장애 아님.
   없는 경로를 추정해 읽거나 동일 방식을 재질문하는 반복을 만들지 않는다.
2. **배달 출처를 깨끗한 커밋으로 준비한다.** 이 문서가 미커밋인 채로 배달하면 dirty=true다.
   이 문서 커밋·푸시는 별도 승인 후 처리하거나, 승인된 동기화에서 검증된 깨끗한 체크아웃을 사용한다.
   임의 stash/reset/clean으로 현재 변경을 숨기지 않는다.
3. **AXCluster 워커 소스 Git 동기화**: Windows `.2 E:\trunk\AXCluster`, `.33 C:\trunk\AXCluster`는
   마지막 preflight에서0ffd74b·더티없음. `.43 ~/trunk/AXCluster` 현재 HEAD는 이번에 재조회하지 않았다.
   등록 config의 경로·역할, 브랜치·더티 상태를 먼저 읽고 ff-only로 맞춘 뒤 실제 해시를 확인한다.
   사람의 게임 트리나 작업 브랜치를 강제로 바꾸지 않는다.
4. **등록 전체5프로젝트 작업장 배달·최종 검사**: `ModularStage`, `NS`, `KimodoMotion_WebUI`,
   `MotionForge`, `AXCluster`. 프로젝트를 임의로 골라 일부만 갱신하지 않는다.
   배달 계획을 읽고, 준비된 깨끗한 트리에서 아래 정식 명령을 실행한다:
   `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`.
   종료 결과·전 프로젝트 검사·출처 해시·프로젝트 로컬 skills/config·서비스 최신성을 대조한다.
   **현재까지 이 전체 update는 실행하지 않았다.**
5. **분산 전체 실증은 별도**: AXCluster의 Python 통합 실행기/기존 스크립트 검사 호환성을 확인하고
   실제 큐→골조→조각 브랜치→워커 구현/커밋→회수→요청자 통합을 실증한다. 0개 테스트는 통과 아님.
   이번 사용자는 전체 커밋·푸시·동기화를 지시했으며 신규 분산 작업을 고르거나 전진/finalize를
   승인한 것은 아니다. 이전 직접 apply_patch 프로브를 이 전체 흐름의 완주로 대체하지 않는다.

### 후속 테스트 — 현재 세션에서 실제 스킬 사용

사용자 “그럼 테스트해볼까?”로 distribute를 읽고 실제 MCP를 호출했다.
RAG 검색 성공·logged=true, AXCluster kind=code·blockers=[] 확인.
운영 check_workshops_clean_tool은 kind=code·master/client .py 경계로 세 워커 모두
checked/ok=true·blocking=[]·dispatchable3대를 반환했다. 스킬 quick_validate도 통과.
client check AXCluster는 세 워커 모두 배달 출처384a07a가 HEAD4fb7915보다3커밋 뒤여서
rc1이다. 스킬1종·payload10개는 일치하지만 출처 버전 검사는 실패다.
현재 마스터의 인수인계 문서는 여전히 미커밋. 실제 분산은 파견하지 않았다.
스킬 흐름/준비 검사와 동기화 후 실제 분산 중 테스트 범위를 사용자에게 물었으며 아직 미응답.

### 로컬 격리 드라이런 — 사용자 후속 요청

사용자 “드라이런 해볼까?” 승인으로 운영 큐/Git/워커를 변경하지 않는 하니스를 실행했다.
스크립트 `/tmp/ax-master-workflow-dryrun.py`, 산출물 `/tmp/ax-master-dryrun-y55d21bm/`의
`result.json`·`specs.json`·`queue_requests.json`·골조3개·격리 통합 fixture에 근거가 있다.
하니스15/15와 실제 local_test_fn으로 실행한 fixture unittest6/6 통과.
register_work에 모의 POST/PATCH 큐를 주입하고 실제 _post와 socket 연결은 금지했다.
실제 AXCluster 프로필의 Python 확장자 검사를 통과했으며, 3골조의 run_python·층1 동결 검사를
실행했다. 시그니처 변경·스텁 잔존·비Python 골조·구문 오류·테스트0개는 예상대로 거절했다.
등재 결과의 gate_checked=False도 확인했다: 등록 함수가 별도 골조 게이트 실행을 통과로
꾸며 기록하지 않는다. 골조 검사는 하니스에서 별도로3/3 실행한 것이다.
세 호스트별 서로 다른 브랜치 이름과 대상 파일을 산출했지만 **배정·병렬 실행은 모의 계획**이다.
Git HEAD·refs·status는 하니스 전후 동일. 실제 브랜치/커밋/push, 원격 워커·LLM층2·Git통합·
전진/finalize·Redmine 큐 등재는 실행하지 않았다. 후속 문서 기록만 이 dirty 파일에 추가했다.

읽기 전용 독립 관측에서 실제 호출 순서를 확인했다: work 등재로 ID 발급→base 이름 기록·
태스크 등재→요청자의 골조 브랜치 준비/검사/승인 커밋·push→원격 base 존재를 확인한 자동 파견.
**실제 등재와 골조 push는 자동 파견을 발동할 수 있어 드라이런으로 실행하면 안 된다.**
또 AXCluster의 unittest discovery는 순수 함수·__main__ 스크립트 검사를 누락할 수 있다.
test_broker_routing/test_workshop_check/test_source_scope 등은 실제 실행계약을 별도로 검토해야 한다.
이 fixture6개 통과를 AXCluster 전체 통합 검사 또는 실제 분산 완주로 확대하지 않는다.
하니스 산출물의 후속 독립 검토는 에이전트가 /tmp 전체 목록을 조회하다 접근 제한 디렉토리의
Permission denied를 만나 중단했다. 앞선 호출순서/테스트 계약 독립 관측은 완료됐지만,
산출물 독립 검토는 미완료다. 루트는 지정 result/queue JSON만 읽어15/15·TESTS OK(6)·
모의 큐 호출5개·실제 파견/Git 브랜치 생성 없음 기록을 직접 대조했다.

### 조회와 권한의 함정

- AX CLI는 작업 위치 `~/ax-cluster`, `.venv/bin/python`, AX_PROJECTS_ROOT 명시가 필요하다.
  조회에서 레지스트리를 직접 읽으면 `Registry.load(Path('/home/sim/ax-cluster'))`도 가능하다.
- Windows 옛 클론 조회 스크립트는 `.2` 출력 UTF8 decode오류를 냈다. 기존
  `/tmp/ax-axcluster-worker-deploy.py preflight`에서는 두대 rc0·클론/HEAD/깨끗함을 확인했다.
  출력 처리 오류를 워커 장애로 기록하지 않는다.
- 기본 샌드박스의 systemctl·sg gitea·Docker 조회 실패는 진단 결과로 남기고 좁은 승인 경로로
  재조회한다. 권한 승인은 OS sudo 비밀번호를 대신하지 않는다. 비밀값 출력 금지.
- 홈 AGENTS/CLAUDE 링크를 덮지 않는다. git 현재 트리와 Redmine journal을 함께 대조한다.

## 1. 오늘의 사용자 결정 (2026-10-03)

- 원격: **Gitea 정본**(`origin`) + **GitHub 푸시 미러**(Gitea 가 커밋 시 동기화). 🔴 **GitHub 직접 push 금지** —
  마스터 `github` 원격은 push 비활성. `.43` 도 `origin` = Gitea
- ax-cluster 를 프로젝트로 등록 — 트윈 이름 **`AXCluster`**(ax-cluster 는 저장소 루트와 겹쳐 `test_sandbox` 오탐)
- AXCluster profile: kind `code`(`.py`) · purpose `rnd` · AX 작업 요청자 = **마스터 세션**
- 합성 프롬프트: 비UE 의 긴 `.py` 는 **ast 요약본**(함수 본문 생략, 독스트링·주석 유지)
- 파이썬 그래프: 겹치는 클래스 이름만 모듈명(`master.verdict.Verdict`) · 테스트 파일은 클래스 그래프 제외 ·
  `related_classes` 의 `이름: ?` 는 그래프에 정확한 이름이 있을 때만 채움(**전 프로젝트**)
- 🔴 **컨텍스트 문서는 검색 보조다 — 작업 판단 근거는 실제 코드**
- 사용량 표시는 **토큰만**. `.33` 등 세션 기록은 로컬에 두고 마스터가 가져온다
- `.2` 상주 모델 = `gemma4:e4b`(종전 `qwen2.5-coder:14b`) — 합성을 두 노드에 나누려고
- 🔴 **AX 클러스터 기능 작업(AXCluster)에서는 `.33` 도 워커로 쓴다** — 등록·배달·진단 파일 수정 실증까지 확인(§3)

## 2. AXCluster 재합성 — 🔴 미완 (11:58 실측으로 정정)

- 색인기는 전체 따라잡기를 **하지 않았다** — push 이벤트 범위(`306576e→c657a7a`)의 **바뀐 소스 106건만**
  합성하고 끝났다. 문서 **76 / 347그룹** · 워터마크(`last_indexed_commit`) **비어 있음**
- 품질: `related_classes` 가 전부 `?` 인 문서 **69% → 25%**(76개 중 19) — 그래프·요약본 효과
- 병렬은 실물 확인됨: 11:44~ 브로커 `[route]` 가 `bc250` 20 · `rtx3060` 14 로 나눴다
- **남은 일**: 누락분 합성 → index. 색인기와 겹치지 않게 **push 를 멈춘 상태에서**:
  `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard AXCluster --confirm --only synth`
  (onboard 합성은 누락분만 · 동시 N 은 상주 노드 수) → `--only index`
- [주의] 색인기 타이머(10분)·push 이벤트도 합성을 띄운다 — 잠금이 없어 겹칠 수 있다.
  멈추려면 마운트를 옮겨야 한다(`systemctl stop` 은 NOPASSWD 밖)

## 3. 다음 작업

**최신 우선순위는 §0의 남은 일이다.** 워커 동기화·등록 전체 배달·검사부터 인계한다.
기존 별도 항목인 §2 재합성 미완, #713 웹 UI·토큰 사용량, AXCluster 분산 첫 전체 실증은
사용자가 고르는 다음 작업으로 남아 있다. 이전 §3의 브로커·문서 미커밋/스킬 미완 기록은
4fb7915와 §0 상태로 갱신한다. 과거 실측은 아래 이력과 reports/82·85·86에 보존했다.

## 4. 오늘 커밋 (모두 Gitea push · GitHub 미러 · `.43` pull 완료)

`183f32a` claim 범위(work 혼입 방지, 큐 재시작) · `ef239fb` 원격 문서 · `c595c01` 온보딩 ·
`4c0823f` 합성 요약본+토큰 로그 · `a0cbf42` 트윈 이름 AXCluster · `c237a93` 파이썬 그래프(#712) ·
`6a18918` 세션 수집기(#713 ②) · `306576e` 브로커 호출 사용량(#713 ①) · `c657a7a` 병렬 합성·분배(#715)

## 5. 남은 결함·주의

- `#714` 스풀 고아 배치를 아무도 재처리하지 않는다(`claimed/` 에 3건 남음 — 실손 없음)
- Kimodo 작업장 3대가 마스터보다 뒤다(재배달 필요, 범위 밖이라 안 함)
- `onboard` 의 conventions 문구 「색인 전용」은 code 타입엔 부정확(동작 결함 아님)
- 요약본 뒤에도 4,000자를 넘는 파이썬 파일 125개는 앞에서 잘린다
- 세션 수집기 `master/work/session_usage.py` 는 유닛 테스트가 없다

## 6. 관련 근거

Redmine `#711`~`#715` 노트 · `docs/14-onboarding-runbook.md` · 메모리 `context-docs-are-search-aid` · `codex-windows-ssh-sandbox` · 리포트82 · `docs/windows-codex-remote.md`


## Python 커밋 자동 리뷰 — 구현·검증 통과 (2026-10-03 17:00)

사용자 최초 지시와 kind 기준 정정, “응 진행해” 재개 승인으로 구현·검증했다.
등재·소비·프롬프트·예시는 등록된 프로젝트 kind로 통일한다. unreal=UE, code=Python,
index_only=자동 리뷰 제외. source 경계·work_exts, 큐 중복 방지·재시도·작성자 제외는 유지.
Python 함수·클래스 선언은 현재 트리가 아닌 대상 commit Git 객체에서 AST로 읽는다.
신규6+기존268=274/274 통과, diff --check 통과. 초기 검사 오탐과 승인 후 재개는 리포트83에 보존.
실제 Python commit6a18918을 격리 큐에서 브로커 e4b→Antigravity로 처리하여 최종 저장·done 확인.
아티팩트 /tmp/ax-python-review-live-1392e70e33da4f61a3a92afefb042484/.
운영 큐에 소급 등재하지 않았음. 서비스는 oneshot이므로 다음 기동 때 로컬 수정 소스를 읽는다.
**commit·Gitea push 완료 `7ec14f5`**, 새 운영 커밋의 push감지→자동 리뷰 종결은 아직 미검증.
커밋 검토 범위: 리뷰 코드·테스트5개 + docs/17-review-queue.md + reports/83-python-commit-review.md.
앞선 브로커·원격 문서 dirty 변경과 구분한다. README·reports 색인 갱신은 문서 dirty에 함께 남음.

사용자 “커밋해줘” 승인으로 Python 리뷰 코드·테스트5개 + 설계·실증 문서2개만 커밋했다.
커밋: `7ec14f5` (`review: enable Python commit reviews by project kind`). 푸시는 실행하지 않았다.

사용자 “푸시해줘!” 승인으로 `7ec14f5`를 Gitea origin/main에 푸시했다.
원격 훅에서 Sim/ax-cluster 색인 이벤트1건 큐잉을 확인했다. 리뷰 큐 등재·소비 완료와는 별개다.


## R1 실제 자동 리뷰·검토 완료 (2026-10-03)

운영 commit7ec14f5가 리뷰 큐에 자동 등재되고 17:26:34 첫 시도 done, R1 최종 리뷰 저장 확인.
사용자 “R1 검토해줘”로 지적1건을 운영 Python3.10.12에서 검증: ast.parse 널 바이트는
ValueError이며 SyntaxError만 잡는 declarations에서 전파됨. 격리 큐에서 running잔존·재claim불가 확인.
권고: SyntaxError·ValueError 처리, msg·lineno 모두 getattr, diff 리뷰 계속·큐종결 회귀.
코드·리뷰 원문·R1 상태는 수정하지 않음. 근거 reports/84-r1-python-review-validation.md.

사용자 “수정해줘!” 승인 후 R1 코드 수정 완료: review_runner에서 SyntaxError·ValueError를
잡고 msg·lineno를 안전하게 읽는다. 구문 오류·널 바이트 실제 임시 Git 커밋 모두 리뷰 done,
pending/running=0 회귀 검증. 관련 검사 141건 및 diff --check 통과. 대상 코드·테스트2개만
수정했으며 커밋·푸시 전이다. 리포트84에 수정과 검증 근거 추가. 운영 R1 상태는 변경하지 않음.

사용자가 RAG·서브 에이전트 누락을 지적했다. 최초 수정은 둘 다 없이 진행했음을 인정했다.
**수정 전 관련 RAG 컨텍스트를 조회하고, 위임할 때 그 근거를 함께 전달한다.**
보완으로 AXCluster active 확인 후 search_context_tool 2회 조회, 관련 본문·설계·현재 코드 대조,
로컬 서브 에이전트 r1_context_review에 독립 검토 위임. AX 원격 워커 파견은 아니다.
컨텍스트의 Python 설명 누락·__repr__ 미구현 오기와 검색 excerpt 누락을 관측했으나
검색·합성 설정은 변경하지 않았다. 근거 리포트84.
독립 검토도 R1 추가 코드 수정 불필요로 판정. 널 바이트는 Git 바이너리 diff가 될 수 있으므로
검증 범위는 큐 고착 방지·진단 전달이며 모든 변경 라인 전달 보장은 아니다.

## 사용자 확정 — .57 인프라 정비에도 RAG·분산 도구 활용 (2026-10-03)

사용자 원문: “.33 메인 작업 컴퓨터가 서브에이전트를 활용하고 분산 작업을 시키고,
RAG를 요청하는 스킬이나 MCP를 인프라 서버를 관리할 때도 활용하길 바래서 워커를 등록한거야.”
사용자 후속 정정: “아니 .33에서 작업 하라는게 아니라 .57 이 인프라 서버에서 작업할 때도
.33처럼 RAG와 분산 작업이 가능하도록 구정되어 있냐고”. **작업 장소를 .33으로 옮기라는
뜻이 아니다. .57의 지휘 세션이 인프라 정비에도 RAG·서브 에이전트·AX 워커 분산을 활용한다.**
마스터 직접 수정 뒤 로컬 서브 에이전트 검토만 추가하여 워커 분산까지 했다고 판단하지 않는다.
이번 R1은 마스터 직접 수정 후 RAG·로컬 독립 검토로 보완했고 AX 워커 분산은 수행하지 않았다.
다음 실행 전 관련 스킬·MCP 계약과 기존 승인 범위를 확인한다. 역할 설정·배달은 변경하지 않았다.

준비 상태 실측: .57 현재 세션에서 search_context_tool 성공, register_work_tool 노출,
서브 에이전트 위임 가능. ax-projects·ax-task-queue active/running, ax-dispatch.path active/waiting,
ax-dispatch-catchup.timer inactive/dead. AXCluster 프로필 kind=code, work_exts=.py, blockers 없음.
세 워커 SSH·Codex0.159.3 확인. client check AXCluster는 실패: 세 배달 출처384a07a가
현재 HEAD보다1커밋 뒤, ax-projects는 profile.py 변경 전 기동되어 재기동 필요 판정.
기존 마스터 distribute 스킬도 통합자·기본직렬·UE골조 등 현재 공용 규칙과 어긋난 옛 내용이며
Codex의 현재 제공 스킬 목록에는 distribute가 없다. RAG는 사용 가능하나 분산 준비 완료로
단정하지 않는다. 실패 규칙에 따라 재배달·재기동·스킬 수정은 실행하지 않고 상태만 보고한다.

사용자 “일단 일감으로 등록해”로 Redmine **#716** `[AX] .57 인프라 정비의 RAG·서브 에이전트·분산 작업 준비 정비`
등록 완료. AX Cluster 프로젝트, 마일스톤6, 신규 상태. 버전 불일치·서비스 재기동 필요·
마스터 분산 스킬 갱신·Python 소스 더티 검사 확인과 실제 .57→워커 흐름 검증을 범위로 기록했다.
등록만 했으며 작업 실행·재배달·재기동·커밋·푸시는 하지 않았다. 항목·진행 정본:
http://192.168.0.57:8080/issues/716.

사용자 최신 절차: CLAUDE.md·AGENTS.md·스킬에 **RAG 검색→단독/분산을 사용자에게 물음→
선택에 따라 서브 에이전트 구성→단독 처리 또는 AX 워커 분산→실물 검증**을 반영한다.
이어 “NS에서 작업 요청을 받았을 때” 실제 방식 분석·참조를 지시하여 .33 NS 지침·스킬·
에이전트·MCP·훅을 읽기 전용으로 대조했다. 근거 reports/85-ns-requester-workflow-reference.md.
NS의 기존 컨텍스트/온톨로지·계획/선택·전문 위임·큐 등재·asyncRewake·되먹임 흐름을
참조하되 combined_search/watch.exe/attempt/클라이언트 등재금지 등 낡은 문구는 복사하지 않는다.
자동 로드 지침·스킬 반영, 재배달·서비스 재기동은 아직 실행하지 않았다. 이전 처리 방식 질문은
지침 반영에 관한 것이며 이번 분석·참조 요청을 분산 실행 승인으로 읽지 않는다.
사용자 “아까 신설한 레드마인에 연결해둬!”로 #716 journal1480에 리포트85 경로·NS 분석 결과·
사용자 확정 절차·남은 반영/운영 검증을 연결하고 재조회 확인했다. 미커밋 보고서임을 명시했고
일감 상태는 신규로 유지했다.

사용자 “아까 리뷰 대응한거 커밋하면서 리뷰 상태값 변경하고” 승인으로 R1 수정 코드·테스트·
리포트84의3파일만 커밋: **95906c87914c081ff6fb64ad05443ccfc75b8bfb**
(`fix(R1-1): handle Python declaration parse failures safely`). 핵심7건 재확인 통과.
fix_index.set_status로 AXCluster **R1-1→applied**, 실제 branch=main·위 커밋을 기록하고
get_doc 재조회로 상태·해시 일치 확인했다. R1 전체 항목1/1 applied. 푸시는 하지 않았다.
브로커·원격 설정·NS 분석 등 앞선 dirty 변경은 이 커밋에 포함하지 않았다.

사용자 “푸시해줘!” 승인으로 95906c8을 Gitea origin/main에 푸시 완료.
git ls-remote의 refs/heads/main=95906c87914c081ff6fb64ad05443ccfc75b8bfb 일치 확인,
원격 훅의 색인 이벤트1건 큐잉 확인. R1-1 applied 노트에 원격 반영도 기록한다.
새 커밋의 자동 리뷰 종결은 아직 확인하지 않았다.

#716 선행 정비: 사용자 동의로 로컬 서브 에이전트 2개가 지침5파일과 타입별 더티 검사2파일을
수정했다. workshop 검사77/77, SourceScope 권한 해제 재검사32/32 통과. 독립 코드 검토 진행.
실제 따라잡기 타이머는 **ax-dispatch.timer**이며 active/waiting이다. 앞선
ax-dispatch-catchup.timer 조회로 비활성이라 기록한 내용은 이 실측으로 정정한다.
경로 추정 조회 오류가 반복돼 공용 실패 규칙에 따라 추가 편집 중단. 남은 distribute 스킬은
루트 직접 인수 예정이며 아직 원본이다. 보고서86에 변경·검사·실패·운영 미검증을 기록했다.
스킬 완성·Codex 연결·깨끗한 커밋 기준 배달/서비스 반영·분산 전체 실증이 남았다.
이번 #716 변경의 커밋·푸시는 승인받지 않았으며 배달·재기동·원격 파견도 하지 않았다.

사용자 “모두 커밋 푸시하고 동기화해”로 전체 현재 변경 승인. distribute 스킬은 루트가
현재 흐름으로 재작성 완료했고 형식/독립 forward 검토 통과. Codex legacy·공식 사용자 경로
링크를 좁은 권한 승인 스크립트로 등록했다. 관련 코드 검사123개 통과. 이전 미완료/승인없음
기록은 위 승인·완성 상태로 갱신한다. 이제 전체 변경을 커밋·Gitea push하고 클론·등록 전체
작업장 배달 및 ax-projects/ax-broker 반영을 수행할 예정. 실측 결과 정본은 #716 journal.
스킬 자동 감지가 공식 동작이지만 이 세션의 새 스킬 노출은 미확인. 다음 세션에서 distribute
노출과 정본 경로를 확인한다. 실제 분산 전체 흐름과 Python 통합 실행기 호환성은 미실증이다.
