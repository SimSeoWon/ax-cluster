# #754 레드마인 갱신 되읽기 — 재개 뒤 회귀 통과

2026-10-08 00:01 KST · Codex · 기준 HEAD `152f2fb`.

사용자가 #754 진행을 승인했다. 기존 로컬 서브 에이전트 선택을 이어 구현 1개와
읽기 전용 독립 검토 1개로 진행했다. RAG redmine/test_redmine 본문, 현재 소스,
참조 전용 AgentTest executor_helpers의 PUT-only 원전을 대조했다.

## 구현 범위

- `master/redmine.py`: PUT 뒤 코멘트 외 전송 필드를 GET으로 되읽는다.
  상태·완료율·우선순위·제목·본문·마일스톤·부모를 비교한다.
- 불일치 및 GET/응답 오류는 `[주의]` 문자열을 반환한다. 기존 서버는 이 접두를
  `ok:false`로 전달하고 클라이언트는 응답을 그대로 반환하므로 해당 배선 수정은 없다.
- 요청값·실제값과 자식 번호를 진단 근거로 제시하되 원인을 단정하지 않는다.
  이미 PUT이 실행되어 코멘트나 일부 필드가 반영됐을 수 있음을 알리고 재PUT하지 않는다.
- 기존 clear_parent 계약과 코멘트만 보낼 때 GET 생략을 유지한다.
  `master/test_redmine.py`에 무시된 갱신·부분 반영·모든 필드 비교·부모 해제 응답·조회 오류
  및 불완전한 응답 회귀를 추가했다.

## 검사와 중단

- 구현 에이전트의 `.venv/bin/python master/test_redmine.py`: **181/184 통과, rc1**.
  새 회귀는 통과했으나 기존 `test_meta_versions_follow_the_project`의 3개 확인이 실패했다.
- 메인 확인: client_mcp 167/167, redmine_live_guard 8/8, auth 69/69, 각각 rc0.
  `git diff --check` rc0. 독립 검토에서 구현 차단 결함은 발견하지 않았다.
- 원인 대조: 기존 검사는 `RM.meta(project="ns", sender=s)`에 키를 주지 않는다.
  기존 meta는 sender 주입 여부와 관계없이 키가 비면 조회 전에 error를 반환한다.
  versions=[], versions_project=None, 버전 GET 없음이라는 세 실패와 일치한다.
  Docker 접근 차단에 따른 키 조회 실패는 샌드박스 환경과 일치하는 추론이며,
  실제 Docker stderr는 이번에 확인하지 않았다. 비밀값 조회·대체 호출은 하지 않았다.
- 실패 뒤 코드·설정을 고치지 않고 중단했다. 재개 시 기존 가짜 sender 검사에
  `key="test"`를 주입하는 수정으로 실제 DB 의존을 제거할 수 있다. 사용자 재개 승인이 필요하다.

## 사용자 재개와 최종 확인

- 사용자 「응!」으로 테스트 키 주입·재검증을 승인했다. 같은 구현 에이전트가
  기존 `RM.meta(project="ns", sender=s)` 호출에 `key="test"`만 추가했다.
  검사 조건과 운영 meta 코드는 유지했다.
- 에이전트와 메인에서 각각 `.venv/bin/python master/test_redmine.py` 실행:
  **184/184 통과, rc0**. 기존 실패 세 건을 포함해 전부 통과했다.
- 메인 정본 `.venv/bin/python -B -m unittest discover -s tests/integration
  -p test_axcluster.py -f -v`: **25개 모듈, 1,153건**, 16.981초, rc0.
- 최종 `git diff --check` rc0. 독립 검토에서 변경 실물과 테스트 키 주입을 대조해
  차단 결함이 없음을 확인했다. 최초 실패와 중단 이력은 위에 보존한다.

사용자 「진행해!」로 코드2파일·보고서99·색인·인계서 총5파일의 커밋·푸시를 승인했다.
이 문서는 커밋 전 검증 기록이며 실제 커밋 해시·푸시 결과는 Redmine #754 후속 노트에서 확인한다.
서비스 재시작·워커 배달 없음.
운영 MCP는 이번 신코드 반영을 검증하지 않았으며 #754는 진행 상태를 유지한다.
진행 정본은 [Redmine #754](http://192.168.0.57:8080/issues/754).
