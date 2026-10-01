# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **갱신 시각**: 2026-10-02 KST
- **지휘 도구 / 세션**: Codex
- **상태**: `#700`은 `6001207` 커밋·push·9작업장 배포·ax-projects 재시작 완료.
  실제 대화 수신은 미검증. `#701`·`#695` 수정·최종 회귀 10개 파일 통과.
  `0d22882` 커밋·push·9작업장 최종 검사와 큐·프로젝트 서비스 재시작 완료.
  최신 결과는 Redmine `#701`·`#695` 확인(리포트 80).
  읽기 진단은 `.43` SSH·`.2` 사용자 세션1에서 실제 Codex 파일4개 해시 일치 성공.
  `.2` SSH 세션0 실패와 대조 완료. 최초 진단의 `gpt-5.6-sol`은 1회 지정이었다.
  이후 업데이트 검증은 모델 override 없이 통과. 임시 진단 작업 제거·로그 TEMP 보존(리포트 81)
  후속 정식 CLI 업데이트는 두 워커 모두 `0.153.4 → 0.159.3` 완료(config 해시 불변).
  `.2`는 사용자가 세션을 종료한 뒤 업데이트했으며 강제 종료 없음.
  업데이트 후 `.43` SSH·`.2` 사용자 세션 기본 모델 실제 읽기 2/2 성공.
- **관련 일감**: `#695`(비UE 분산 작업) · `#698`(Windows Codex ACL, 구현 완료) ·
  `#699`(프로젝트 로컬 Codex 스킬·MCP, 구현 완료) · `#700`(실패 통보 누락, 열림) ·
  `#701`(실패 work 자동 종결 누락, 열림)
- **저장소·브랜치**: `~/ax-cluster` `main`, 운영 코드 배포 기준 `0d22882`.
  후속 문서 변경은 리포트81·색인·이 인계서 3개이며 사용자 커밋·push 승인 범위다.
  최신 HEAD·origin/main·dirty는 아래 명령으로 직접 대조(문서 커밋과 운영 코드 배포를 구분)
- **실행 중인 분산 work**: 없음. Kimodo 실증 work
  `20260930_2348_api_anatomy_report_post_apiposesanatomy_44e1a015`는 사용자 지시로
  `ready_for_review → cancelled`; 하위 태스크 2개의 `verified` 이력은 보존
- **워커 지휘자 모드**: `codex` (모드는 문서가 아니라 `~/.cache/ax-dispatch/mode.json` 재조회)
- **마운트**: `KimodoMotion_WebUI`

---

## Windows Codex 실행 시 반드시 구분할 세션

`.2`에서 SSH 직접 실행은 SessionId=0이었고 실제 Codex 셸이 `0xC0000142`로 실패했다.
같은 설치본·모델·명령은 로그인된 사용자 SessionId=1에서 네 파일 읽기에 성공했다.
**SSH는 작업 데이터 전송·런처 깨우기에 쓰고, Windows Codex는 기존 `/IT·LIMITED`
사용자 런처를 통해 실행한다.** 여기서 세션1은 경로 이름이며 숫자 1을 영구 가정하지 않는다.
`.43` Linux는 SSH 직접 Codex 읽기가 성공했다. `.33`은 파견 대상이 아니다.

기존 Python 정본은 `master/work/runner.py` → `client/init/residency.py` →
`client/runtime/session1_conductor.py`다. 새 스킬을 만들더라도 이 경로를 재사용한다.
스킬 지시만으로 OS 세션을 보장할 수 없다. 시도별 request_id 대조와 산출물 판정도 유지한다.
`.2` 홈 기본 모델은 변경하지 않았다. `0.159.3` 업데이트 뒤 모델 override 없는 사용자
세션 읽기가 성공해 종전 모델 지원 오류는 이번 호출에서 재현되지 않았다.
런처는 여전히 홈 기본값을 상속한다. 실제 운영 경로 전체 성공은 아직 미검증이다.
상세 실측·스킬 설계 권고는 리포트 81. 이번 문서 보강은 운영 코드·설정 변경이 아니다.
후속 승인된 CLI 업데이트는 두 워커 모두 완료했다. 기본 모델 실제 읽기 2/2 성공.
설정 변경은 없으며 결과는 리포트 81로 대조한다.
MCP 후속 진단: 허용 조회 `get_anti_patterns`로 직접 MCP 연결·실제 도구 호출 2/2 성공.
Codex 내부 네이티브 호출도 2/2 성공. `.2`는 최초 1회 비활성화 override에서
`invalid transport in mcp_servers.code-review`로 실패했으나 사용자 승인 후 그 진단 인자만
제외한 재검증이 통과했다. 영구 설정 변경 없음, 임시 작업 제거·로그 보존.
`.43`은 타 MCP 비활성화 진단, `.2`는 비활성화 없이 성공했다. 상세는 리포트 81.

## 현재 프로젝트 타입과 다음 실증 범위

`master/client/payload/profile/KimodoMotion_WebUI.yaml`은 `kind: code`, `purpose: tool`,
Python WebUI·C++ 엔진 포크 서브모듈, 분산 대상 `work_exts: [.py]`다. Unreal 프로젝트가 아니다.
AX 워커 기본 MCP 배달 대상은 `master/client/spec.py`의 `MCP_BY_ROLE`에 따라 `ax-client`다.
그 읽기 전용 MCP 호출은 두 워커에서 검증했다. 관측된 `unreal-mcp` localhost:8000 오류를
이 프로젝트의 완료 조건이나 새 분산 실증의 선행 장애로 삼지 않는다. 다른 설정층에서
노출된 항목의 귀속은 확정하지 않았고 이를 임의 삭제하거나 설정을 변경하지 않는다.

다음 실증은 `.33`의 Kimodo 프로젝트에서 작은 `.py` **새 work**를 요청하는 것이다.
기존 cancelled work는 재개하지 않는다. 마스터는 파견·워커 실행·결과 회수·실패 시 종결과
고지를 대조하고, 실제 `.33` 대화의 완료·실패 수신은 요청자 증거로 확인한다.
이 전체 흐름은 아직 미검증이며 새 work 등록을 마스터가 자율 실행하지 않는다.
⑦ 전진과 finalize는 별도 사용자 승인이다. UE 빌드·Unreal MCP는 이 실증의 검증 항목이 아니다.

## 1. 2026-09-30~10-01에 완료한 것

### 1-1. 비UE `kind: code` 첫 실증 (`#695`)

KimodoMotion_WebUI의 두 조각을 `.2`와 `.43`에 파견해 워커 커밋까지 만들었다. 이 실증에서
설치·재시도·통보 경계의 실제 결함을 확인했다.

- `.2`의 새 체크아웃에 Codex 샌드박스 쓰기 권한이 없어 첫 시도가 실패
- 재시도가 옛 결과 파일을 다시 읽어 한 번 헛돎 — 이후 `#695` 시도 격리 수정·배포(`0d22882`)
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
   검사 394/394, 프로젝트 검사 63/63 통과. `6001207` 커밋·push·9작업장 배포 완료이며
   최신 결과는 Redmine `#700`으로 대조한다. 실제 `.33` 세션 수신 증거와 훅 발행은 구분한다.
2. `#701` — 실패 라운드 terminal 분류·통보 오류 영속화·훅 표시·취소 파일과 사유 보존 수정.
3. `#695` — 옛 결과를 지우는 대신 시도별 결과 디렉터리와 request_id 대조 수정.
   검증 중단 두 차례는 사용자 승인 후 수정했고 최종 회귀 10개 파일 통과(리포트 80).
   이번 변경 커밋·push·배포는 승인됐으나 운영 새 work 등록·전진·finalize는 자동 실행하지 않는다.
4. `#695`의 ⑦ 통합·전진은 이번 실증 work를 취소했으므로 이어서 실행하지 않는다. 새 실증은
   업데이트 후 기본 모델 읽기 성공을 바탕으로 사용자 세션 실행 경계를 유지하고,
   프로젝트 로컬 스킬·MCP가 배포된 새 work로 시작한다. 준비 검사/스킬 보강은
   아직 구현 승인·변경 없음. 새 work 등록·전진·finalize는 별도 사용자 승인이다.
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
- `reports/81-worker-file-read-diagnosis.md` — 세션0/1 대조·분산 실행 계약·스킬 권고·정식 CLI 업데이트와 기본 모델 읽기 2/2 성공
- `master/client/{bundle.py,spec.py,__main__.py}`
- `client/init/bootstrap.py`
- `docs/12-multi-project.md`
- Redmine `#695`, `#698`, `#699`, `#700`, `#701`
