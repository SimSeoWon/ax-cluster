# 96. 워커 Claude 인증 검사 주기와 실패 고지

2026-10-05 22:30 KST · Redmine #721 · Codex · 로컬 구현 완료, 운영 반영 전.
기준 HEAD `40ea0ab66c1f0b84902fa57ec9097571f4f84e00`.

## 결정과 근거

사용자는 매 명령마다 인증을 조회하는 대신 워커에 마지막 검사 시각과 결과를 저장하고,
다음 호출에서 검사 후 24시간 경과 여부를 확인하도록 지정했다. 달력 날짜 기준이 아니다.
실행 중 인증 실패는 캐시와 별도로 즉시 고지하고 코드 재작성 재시도를 중단한다.
인증 복구 로그인은 자동 실행하지 않는다.

RAG `search_context_tool`이 반환한 worker_daemon 문서 본문은 CI 실행·보고에 관한 것이다.
지휘자 인증 계약의 근거로 확대하지 않고 현재 `conductor.py`, `runner.py`, `infer.py`,
`revise.py`, 원전 AgentTest verifier의 관련 판정 흔적과 리포트 79·89를 대조했다.
현재 준비 검사는 버전·스킬만 확인했고 OAuth 실패 분류는 없었다.
기존 즉시 Redmine 노트와 요청자 실패 표시 경로는 이미 있었다.

[Claude 공식 CLI 문서](https://code.claude.com/docs/en/cli-reference)는 `claude auth status`의
JSON 응답과 로그인 시 exit 0, 미로그인 시 exit 1을 명시한다.
이 검사는 CLI 로그인 상태이며 이후 API 요청의 성공까지 보증하지 않는다.
실측 만료 문자열은 `Failed to authenticate: OAuth session expired and could not be refreshed`다.

## 구현

- `master/work/conductor_auth.py`: 기존 `bundle._remote_read`, `_remote_write`, `_ssh` 사용.
  워커 홈 `.cache/ax-dispatch/claude-auth.json`에 시각·결과·정규화한 사유 저장.
  Windows도 해당 계정 홈의 같은 상대 경로를 사용한다. CLI 원문·메일·토큰은 저장하지 않는다.
  host/user/home을 대조하고 24시간 미만이면 성공·실패 결과를 재사용한다.
  기록 누락·손상·미래 시각·계정 불일치는 재검사한다. 동일 프로세스의 같은 워커 병렬 검사는
  잠금으로 중복을 막는다. 서로 다른 마스터 프로세스까지 분산 잠금을 제공하는 것은 아니다.
  읽기·저장 실패는 성공으로 통과시키지 않고, 저장 실패 후 기존 정상 기록 재사용을 막는다.
- `conductor.py`: Claude 준비 검사도 같은 캐시를 사용한다. 준비 실패 시 모드를 바꾸지 않는
  기존 계약과 Codex 준비 경로를 유지했다. 개별 워커 제외 정책은 새로 만들지 않았다.
- `runner.py`: 실제 Claude 실행 전 캐시 조회, stderr 회수, OAuth 오류 때 실패 기록으로 갱신.
  rc 실패 또는 JSON `is_error=true`인 실제 오류를 짧은 고정 표식으로 반환한다.
  긴 출력의 뒤쪽만 보존하는 기존 실패 경로에서도 인증 원인이 남는다.
- `revise.py`, `infer.py`: 인증 실패를 한도·일반 코드 실패보다 먼저 판정해 재시도를 제외한다.
  즉시 Redmine 고지와 큐 `fail_detail`에 워커·상세 원인을 남겨 기존 요청자 알림이 표시하게 한다.
  저장·연결 오류를 곧바로 로그아웃으로 단정하지 않는다.
- `tests/integration/checks.json`: runner와 orchestration 검사를 명시 목록에 추가(23→25 모듈).

재로그인 후 관리자가 `check_claude_auth(facts, force=True)`를 호출하면 실패 캐시가 남아 있어도
다시 검사한다. 전체 준비 검사에서는 다음 정본 함수 조합을 사용할 수 있다.

```python
from functools import partial
from master.work.conductor import worker_mode_readiness
from master.work.conductor_auth import check_claude_auth
worker_mode_readiness("claude", "AXCluster",
                      auth_checker=partial(check_claude_auth, force=True))
```

## 검증과 현재 상태

로컬 구현 에이전트 2개와 메인 지휘자의 직접 검토로 수행했다. 추가 독립 검토 에이전트 생성이
세션 thread limit로 실패했을 때 코드 변경 없이 중단했고, 사용자 재개 확인 뒤 위 방식으로 진행했다.
각 에이전트는 경로 목록 확인과 파일 읽기를 별도 도구 호출로 수행했다.
직접 검토에서 rc 실패 때 notes가 비어 상세 사유를 잃는 경로를 보완하고 회귀를 추가했다.

- 개별: orchestration 27/27 · runner 156/156 · revise 67/67 · infer 218/218.
- 정본 통합 명령 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`:
  **25모듈 1,137건 통과**, rc 0, 16.943초.
- 24시간 경계·손상/미래 기록·실패 재사용·강제 재검사·병렬 첫 검사·Windows 경로·비밀값 차단·
  저장 장애·실측 OAuth 오류·긴 출력·rc 0 오류 JSON·즉시 고지·재시도 제외·실패 상세를 검증했다.
- `git diff --check` 통과. 커밋·push·배달·서비스 재시작은 하지 않았다.

실제 워커의 auth status/캐시 저장 왕복과 실제 요청자 세션 수신은 아직 검증하지 않았다.
운영 반영 전이므로 #721은 진행으로 유지한다. 후속은 승인된 깨끗한 커밋에서 배포하고,
첫 검사와 24시간 내 재사용을 실제 워커에서 확인하는 것이다.
