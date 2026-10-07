# 리포트 79 — 워커 실패 고지와 Codex 설정 확인

- 날짜: 2026-10-01
- 일감: `#700` (부모 `#695`)
- 기록 시점: 로컬 구현·회귀 검증 완료 후 사용자 커밋·push·배포 승인.
  이후 커밋·배포·실제 세션 수신 검증 결과는 Redmine `#700`에서 확인

## 1. 실제 요청자 로그

Kimodo 실증 work `20260930_2348_api_anatomy_report_post_apiposesanatomy_44e1a015`의
요청자 `.33` 로그를 등록 경로
`C:\Users\USER\Documents\KimodoMotion_WebUI\.ax\work_completion.jsonl`에서 조회했다.
`hook_fired`와 `watch_started` 이후 `pending 2 → claimed 2 → claimed 1/verified 1 →
needs_revision 1/verified 1`이 기록됐지만 조회된 로그에는 `signal_emitted`가 없었다.
감시가 실제로 시작됐으므로 이 사례를 단순 훅 미등록으로 판정하지 않는다.

기존 `wait_for_work`는 work 전체가 `ready_for_review`·`merged`·`cancelled`일 때만
알렸다. 따라서 `needs_revision`을 관측해도 실패 사실을 알리지 않았다. 또한 실패 렌더러는
`last_feedback`·`verdict_feedback`만 읽고 일반 submit-fail이 저장하는
`fail_reason`·`fail_detail`을 빠뜨렸다.

## 2. 수정과 검증

- `failed`·`needs_revision` 조각은 work 전체 완료 전에도 사유를 고지한다.
- 실패 고지와 최종 완료의 중복 억제를 구분한다. 실패 고지가 최종 완료를 막지 않는다.
- 실패 고지 뒤 다음 도구 호출에서 완료 감시를 다시 건다. PostToolUse 등록 matcher도
  이에 맞게 변경했다. 세션별 기록과 기존 잠금으로 다른 세션·중복 감시를 구분한다.
- 세션 시작/매 턴 안전망에도 큐의 실패 사유를 표시한다.
- 큐 상태·재시도 정책·상위 work 종결 계약은 변경하지 않았다(`#701` 별도).
- `master/test_work_completion.py`: 13개 통과.
- `master/test_client_bundle.py`: 394/394 통과.
- `master/test_projects.py`: 63/63 통과. 합계 470개 통과.
- `git diff --check`: 통과.

실제 `.33` 대화가 알림을 수신했다는 검증은 아직 없다. 테스트의 `signal_emitted`를
실제 수신 증거로 일반화하지 않는다. 배달은 사용자 승인으로 커밋·push한 깨끗한 트리에서
수행한다.

## 3. 워커 설정 — 현재 값 확인, 읽기 문제는 미확정

두 워커 모두 `codex-cli 0.153.4`이며 Kimodo 프로젝트가 홈 config에서 `trusted`로
등록돼 있고 프로젝트 `.codex/config.toml`에 `ax-client`가 있다.
`.2`의 `windows.sandbox`는 `unelevated`이고 체크아웃 루트에
`CodexSandboxUsers:(OI)(CI)(M)` ACE가 있다. `.43` 체크아웃은 `sim` 소유다.

이 확인은 SSH 계정이 파일을 읽은 결과이지 Codex 샌드박스 안에서 읽은 실증이 아니다.
사용자가 추가로 보고한 파일 읽기 실패의 대상 경로·실행 오류는 아직 확인하지 못했다.
따라서 두 워커의 모든 Codex 읽기 권한이 정상이라고 판정하지 않는다. `#698`은 신규
Windows 클론 ACL의 수정이고, 기존 체크아웃 권한의 전수 검사는 그 이슈 범위 밖이다.

## 4. 실제 대화 수신 확인 (2026-10-07, Codex)

기존 수집된 `.33` Claude 대화 원본에서 남은 수신 증거를 확인했다. 새 work 등재·실패
주입·재파견 없이 읽기 전용으로 검증했으며, 기존 수정 커밋은 `6001207`이다.

- 프로젝트 `KimodoMotion_WebUI`, 세션 `8683a2e8-5152-42a8-9444-9bfe348ff613`.
- 수집 사본: `/home/sim/ax-state/usage/raw/KimodoMotion_WebUI/192.168.0.33/claude/projects/C--Users-USER-Documents-KimodoMotion-WebUI/8683a2e8-5152-42a8-9444-9bfe348ff613.jsonl`.
  색인 `raw/index.jsonl`은 host `.33`, 원본 경로, cwd, 수집 시각 `2026-10-04T23:16:39`를 기록한다.
  실제 파일 SHA256과 색인 값은 `101e20488673b06b113011664e55301b4c25669e98a36e7da4df61ec70821908`로 일치한다.
- 원본 121행: `2026-10-01T15:30:32.355Z`(10월 2일 00:30:32 KST), work
  `20261002_0029_work_2710d620`, 조각 `939bff0e`의 OAuth 만료·본문 작성 rc=1이
  `Stop hook feedback`으로 수신됐다. `origin.kind=task-notification`,
  `promptSource=system`, `turnOrigin=task_notification`이므로 사람이 타이핑한 알림이 아니다.
- 124행: `15:30:40.676Z`, 세션이 로그인 만료로 구현 조각이 실패했고 테스트 조각은 진행
  중이라는 사실을 사용자에게 보고했다. 알림 UUID `a9de05fd-7767-401e-82da-a250853af1ba`에서
  훅 첨부·assistant 응답으로 이어지는 parentUuid 연결도 확인했다.
- 163행: `15:36:01.482Z`, 같은 work의 `ready_for_review`·`verified 2` 완료 알림이
  `PostToolUse:Bash`를 통해 수신됐다. 171행 `15:36:08.414Z`에서 세션이 완료를 보고하고
  사람 판단 전 머지·전진을 보류했다. 실패 고지가 최종 완료 고지를 막지 않았다.
- 해당 work의 실제 task-notification 메시지는 실패 1회와 완료 1회다. 큐에 넣는 이벤트,
  훅 첨부의 복제 문구를 별도 알림으로 세지 않는다. 이 세션에서 같은 실패 반복 수신은 없다.

기존 「실제 수신 증거 없음」은 당시 확인 범위의 기록이다. 이번 대조로 #700의 수신 조건을
충족했다. 실패 조각 없이 pending만 남고 실행이 멎는 경우의 알림은 여전히 미검증이며,
이 실증을 그 경우나 Codex 요청자 세션의 자동 깨우기 검증으로 일반화하지 않는다.
완료 상태의 정본은 Redmine #700 후속 노트다. 코드 수정·커밋·푸시·추가 배포는 하지 않았다.
