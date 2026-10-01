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
