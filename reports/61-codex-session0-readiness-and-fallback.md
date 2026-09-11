# 61 — Windows Session 0 Codex 불능 · 전환 readiness · Claude 폴백

## 61.1 결과

2026-09-11~12의 `#398` 라이브 파견은 모델 능력이 아니라 **Windows 실행 환경**을 갈랐다.
`.43` Fedora의 Codex 조각은 정상 완료됐고, `.2` Windows에서는 모델이 지시를 이해한 뒤에도
셸 프로세스를 시작하지 못했다. 전역 워커 모드는 사용자 지시로 `claude`로 되돌렸다.

## 61.2 원인과 부분 성공

`.2`의 `[windows] sandbox="elevated"`는 Windows OpenSSH Session 0에서 runner를 띄울 때
`0xC0000142`로 죽었다. 모델 호출 0 probe도 `timed out after 15000ms connecting runner
pipe-in`을 재현했다. 직접 실행과 `.43` 대조군은 성공했고, `unelevated` override에서는 sandbox
프로세스가 시작됐다.

공개 원인은 `openai/codex#37722`와 일치한다. `CreateProcessWithLogonW`로 만든
`CodexSandboxOffline` 프로세스가 상속하는 Window Station/Desktop에 해당 SID의 ACE가 없어
초기화에 실패한다. 이슈의 ACE 추가→성공→원복→재실패 A-B-A와 우리 오류 문자열이 같다.

그러나 `unelevated`는 완전한 해결이 아니었다. 조각 `16d2adf7`은 파일 3개를 고쳐
`75239c2b`로 커밋하고 verified됐지만, 같은 실행의 PowerShell `command_execution` 3건은
계속 `0xC0000142`였다. 워커는 `ax-work/SKILL.md`와 소스를 셸로 읽지 못한 채 프롬프트만으로
작업했다. 통합 빌드는 최종 통과했지만 정상 워커로 볼 수 없다.

## 61.3 같이 드러난 결함

- `#399`: 파견이 끝나 활성 실행이 0인데 work가 종결 상태가 아니면 `.33` 요청자에게 신호가
  가지 않는다. 최종 완료 신호는 동작했지만 **중간 정지 공지**는 여전히 없다.
- `#387`: 성공·실패 실행의 usage가 스풀과 로그에 남는 것은 `#398`에서 실물 확인됐다.
  비용 필드가 없는 Codex 실행은 계속 **비용 미상**으로 읽어야 한다.
- `#398`과 후속 `#400`은 `.33`에서 통합 빌드·전진·main 반영까지 끝나 Redmine 완료다.

## 61.4 전환을 Python 절차로 만들었다

커밋 `b326cba`는 `set_worker_mode`가 `mode.json`만 쓰던 동작을 바꾼다.

1. 활성 프로젝트의 SSH 워커를 구한다.
2. 선택한 지휘자의 CLI 버전과 `ax-work` 스킬을 확인한다.
3. Windows Codex이면 실제 Session 0에서 sandbox 셸 probe를 실행한다.
4. 모든 워커가 통과할 때만 모드를 저장한다. 하나라도 실패하면 기존 모드를 보존한다.

MCP와 제어 API는 같은 `master.work.conductor.set_worker` 경로를 쓴다. NS 실물 결과:

    claude  .2 2.1.266 OK · .43 2.1.222 OK
    codex   .2 0.153.4 shell probe exit 1 · .43 0.153.4 OK

회귀는 `test_orchestration_control` 11/11, `test_client_bundle` 308/308,
`test_mcp_servers` 48/48, `test_work_mode_stamp` 15/15과 `git diff --check`를 통과했다.

## 61.5 현재 경계

- 전역 워커 모드: `claude`.
- `.43` BC-250: 2026-09-12 00:50 KST 종료, 이후 SSH timeout 확인.
- `b326cba`: 로컬 커밋 완료. **origin push·배달·서비스 재시작은 아직 하지 않았다.**
- readiness는 운영 완화책이다. `.2`의 Windows Codex 셸 결함 자체는 `#401`로 열어 둔다.
- Session 0 Window Station/Desktop ACE 수정은 보안 객체 변경이므로 별도 승인과 최소 권한·회수
  검증 없이는 적용하지 않는다.
