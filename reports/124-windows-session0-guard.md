# 124 — Windows SSH 세션 0 실행을 코드로 막는다 (#832)

2026-10-18 · Claude · 사용자 지시 「#832부터 착수해」 · 방식: 로컬 서브 에이전트 2 (사용자 선택)

## 왜

Windows OpenSSH 로 실행한 프로세스는 **SessionId 0 · `NT AUTHORITY\NETWORK`** 다(.33 실측). 사용자 자격 증명·대화형 세션이 필요한 도구가 거기서 실패한다 — codex 샌드박스 `0xC0000142`(리포트 61·62), agy 「not logged into Antigravity」(같은 날 `.33 gemini_report --remote` 실증, 재로그인해도 동일). 보고서 11건에 같은 부류가 반복됐고 매번 경로 하나에만 우회를 붙였다. 사용자: *"0번으로 해서 윈도우에서 처리못하는거 지금 몇달째 동일한 이슈를 계속 반복하는거야"* · *"이렇게 하지 말라고 누누히 말해도 또 0번으로 처리해서 오탐이 일어난거잖아"*.

## 사용자 결정

- 윈도우 `claude` 모드도 세션 1 런처로 보낸다(종전 codex 만) — claude 가 agy 에 위임하면 세션 0 에서 죽던 구멍을 닫는다.
- 범용 런처는 미룬다 — codex·claude 범위만.
- 준비 검사(런처 등록)를 claude 모드로 넓힌다.
- 리눅스 워커는 영향이 없어야 한다.

## 바뀐 것

| 자리 | 내용 |
|---|---|
| `client/runtime/winsession.py` (신규·배달) | `session_id()`(ctypes `ProcessIdToSessionId`, 비Windows 는 즉시 None) · `is_session0()` · 고정 거절 문구 `refuse_reason()` |
| `gemini_report.py` | 시작 즉시 세션 0 이면 종료 2(agy·모델 해석·큐 미접촉). Windows 에서 판정 모듈이 없으면 거절(재배달) |
| `session1_conductor.py` | job 의 `mode`(데이터, codex·claude 허용 목록 · 없으면 codex) · claude argv(마스터 `worker_command` 와 지시문 동일 검사) · 런처 자신이 세션 0 이면 rc 3 거절 · 판정 모듈 부재는 경고 후 진행 |
| `runner.py` | `uses_session1` = Windows AND codex/claude · claude 인증 사전 검사는 마스터에 유지 · 중계 기록 줄이 붙은 claude JSON 봉투를 읽도록(그대로면 agy 를 쓴 바로 그때 BLOCKED 로 오판) |
| `conductor.py` | Windows 런처 등록 검사를 claude 모드에도 |
| `ax-work`·`ax-gemini` SKILL.md | Windows 에서 `VIA_LAUNCHER` 없으면 agy 직접 호출 금지 · 세션 0 거절 안내 |

## 검증

- 공식 169/169 OK · `master/test_*.py` 173파일 rc 0.
- 리눅스 무영향: 수정 **전** 리눅스 claude·codex 명령 8조합 해시를 고정 → 수정 후 바이트 동일. 리눅스에서는 어떤 모드도 세션 1 아님. 세션 0 을 답하는 가짜 `windll` 을 심고 linux/darwin 으로 돌려도 거절 0 · 호출 0.
- 드라이런(SSH, 임시 파일 삭제): `.43` `None False` · `.33` `0 True` + 거절 문구 · `.2` `0 True`.
- [주의] `.2` 에서 확인 스크립트가 문구를 콘솔에 print 하다 `cp949` 로 죽었다(`—`). 런처는 UTF-8 파일에 쓰므로 무관, `gemini_report` 는 `.33` 전용이고 기존 로그에도 `—` 가 있어 신규 위험 아님 — 기록만.

## 남은 것

- 배달 뒤 `.33` 에서 SSH 로 `gemini_report` → 즉시 종료 2 실증.
- 윈도우 claude 의 세션 1 완주(파견 실물)는 다음 실제 분산 작업 때 — #830 `.2` 중계 확인과 함께. `claude.exe`/`.cmd` 탐색·인증 파일·긴 지시문 인자가 세션 1 에서 되는지 미실측.
