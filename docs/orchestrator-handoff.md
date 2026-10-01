# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **갱신 시각**: 2026-10-01 KST
- **지휘 도구 / 세션**: Codex
- **상태**: `#700`은 `6001207` 커밋·push·9작업장 배포·ax-projects 재시작 완료.
  실제 대화 수신은 미검증. `#701`·`#695` 수정·최종 회귀 10개 파일 통과.
  사용자 승인에 따라 커밋·push·배포 진행; 최신 결과는 Redmine `#701`·`#695` 확인(리포트 80)
- **관련 일감**: `#695`(비UE 분산 작업) · `#698`(Windows Codex ACL, 구현 완료) ·
  `#699`(프로젝트 로컬 Codex 스킬·MCP, 구현 완료) · `#700`(실패 통보 누락, 열림) ·
  `#701`(실패 work 자동 종결 누락, 열림)
- **저장소·브랜치**: `~/ax-cluster` `main`, 기준 HEAD `6001207`(origin/main 동일).
  `#701`·`#695` 수정·테스트·리포트가 미커밋. 현재 HEAD·dirty는 아래 명령으로 직접 대조
- **실행 중인 분산 work**: 없음. Kimodo 실증 work
  `20260930_2348_api_anatomy_report_post_apiposesanatomy_44e1a015`는 사용자 지시로
  `ready_for_review → cancelled`; 하위 태스크 2개의 `verified` 이력은 보존
- **워커 지휘자 모드**: `codex` (모드는 문서가 아니라 `~/.cache/ax-dispatch/mode.json` 재조회)
- **마운트**: `KimodoMotion_WebUI`

---

## 1. 2026-09-30~10-01에 완료한 것

### 1-1. 비UE `kind: code` 첫 실증 (`#695`)

KimodoMotion_WebUI의 두 조각을 `.2`와 `.43`에 파견해 워커 커밋까지 만들었다. 이 실증에서
설치·재시도·통보 경계의 실제 결함을 확인했다.

- `.2`의 새 체크아웃에 Codex 샌드박스 쓰기 권한이 없어 첫 시도가 실패
- 재시도가 옛 결과 파일을 다시 읽어 한 번 헛돎 — `#695` 기록, 별도 수정은 아직 없음
- 프로젝트 로컬 관리 스킬·MCP가 초기화되지 않아 실행 문맥이 홈 자산에 의존
- 워커 실패가 `.33` 완료 훅에 통보되지 않음(`#700`)
- 통보가 끊긴 work가 `ready_for_review`에 남아 프로젝트 전환 테스트를 막음(`#701`)

실증 work는 정상 결과로 전진시키지 않고 `cancelled`로 강제 종결했다. 두 하위 태스크의
`verified`는 감사 이력으로 남겼다. 취소 뒤 `master/test_projects.py` 63/63 통과.

### 1-2. Windows Codex 쓰기 권한 (`#698`, `906fe60`)

Windows 부트스트랩이 새 체크아웃 ACL에 `CodexSandboxUsers` 수정 권한을 부여하도록 수정했다.
특정 PC의 임시 ACL 수정을 정본으로 삼지 않고, 신규 프로젝트 초기화가 재현 가능하게 만든 변경이다.

### 1-3. 프로젝트 로컬 Codex 스킬·MCP (`#699`, `63ea616`)

초기화·배달·검사가 다음을 관리한다.

- `<checkout>/.agents/skills/...`
- `<checkout>/.codex/config.toml`의 `ax-client`
- 위 관리 산출물의 `.git/info/exclude`
- 프로젝트 cwd에서의 MCP 대조

홈에 같은 이름의 스킬이 있어도 프로젝트 로컬 정본이 우선한다. 관련 회귀는
`test_projects` 63/63, `test_client_bundle` 393/393, `test_bootstrap` 48/48 — 합계 504/504.

`63ea616`은 `origin/main`에 push했다. 이후 `master.client update`로 ModularStage·NS·
KimodoMotion_WebUI의 등록 작업장 9개 조합을 배달·검사했고 전부 최종 `OK`였다.

[주의] Kimodo `.2` 배달 중 Claude 로컬 MCP가 등록 직후 `~/.claude.json`에 없다는 경고가
1회 있었으나 최종 프로젝트 검사는 `OK`; Codex MCP 검사는 통과했다. 재발하면 별도 결함으로 분리한다.

## 2. 열려 있는 결함과 다음 작업

1. `#700` — 요청자 로그에서 `needs_revision` 관측 뒤 고지 누락을 확인했다. 로컬 수정은
   조각 실패 즉시 고지·실패 사유 필드·최종 완료 감시 재개를 포함한다. 완료 훅 13개와 배달
   검사 394/394, 프로젝트 검사 63/63 통과. 사용자 커밋·push·배포 승인 후 진행 중이며
   최신 결과는 Redmine `#700`으로 대조한다. 실제 `.33` 세션 수신 증거와 훅 발행은 구분한다.
2. `#701` — 실패 라운드 terminal 분류·통보 오류 영속화·훅 표시·취소 파일과 사유 보존 수정.
3. `#695` — 옛 결과를 지우는 대신 시도별 결과 디렉터리와 request_id 대조 수정.
   검증 중단 두 차례는 사용자 승인 후 수정했고 최종 회귀 10개 파일 통과(리포트 80).
   이번 변경 커밋·push·배포는 승인됐으나 운영 새 work 등록·전진·finalize는 자동 실행하지 않는다.
4. `#695`의 ⑦ 통합·전진은 이번 실증 work를 취소했으므로 이어서 실행하지 않는다. 새 실증은
   프로젝트 로컬 스킬·MCP가 배포된 새 work로 시작한다.
5. Kimodo 테스트가 `vendor/kimodo.cpp` 서브모듈을 요구한다. `ax-advance` 검수 worktree의
   서브모듈 처리 방식은 아직 결정·구현되지 않았다.

## 3. 받는 세션의 첫 확인

```bash
cd /home/sim/ax-cluster
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

- Redmine `#698`·`#699`는 구현·검증·배포 완료 상태인지 확인한다.
- `#700`·`#701`은 열린 결함으로 남아 있어야 한다.
- 큐에서 위 Kimodo work의 `merge_status=cancelled`를 확인한다.
- 미커밋 변경이 있다면 보존한다. 후속 커밋·push에는 별도 사용자 승인이 필요하다.

## 4. 관련 근거

- `reports/77-kimodo-followups-and-shadow-skill.md` — 직전 Kimodo 온보딩과 그림자 스킬 조사
- `reports/78-kimodo-code-worker-skill-and-cleanup.md` — 이번 실증·수정·배포
- `reports/79-worker-failure-notice.md` — `#700` 원인·로컬 수정·워커 설정 현황
- `reports/80-failed-work-and-session1-retry.md` — `#701`·`#695` 변경 범위와 검증 중단 원인
- `master/client/{bundle.py,spec.py,__main__.py}`
- `client/init/bootstrap.py`
- `docs/12-multi-project.md`
- Redmine `#695`, `#698`, `#699`, `#700`, `#701`
