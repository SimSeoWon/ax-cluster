# 73 — AX 서비스 영구 재시작 도구와 Codex 레드마인 접근 경계

2026-09-20 · Redmine `#647` 완료 100% · 커밋 `98da21f` · GitHub `main` push

## 1. 반복 임시 스크립트를 운영 경로에서 걷었다

종전 정본은 `sudo -n /usr/bin/systemctl restart <unit>`이었지만 Codex 승인 경계와 sudoers가
갈릴 때마다 `/tmp`의 좁은 스크립트를 다시 만드는 일이 반복됐다. `#647`은 저장소에 영구 사용자
명령을 두되, sim이 수정할 수 있는 저장소 스크립트 전체를 root로 실행하지 않는 것이 핵심이다.

    사용자 명령   scripts/ax-service-restart <unit>
    Python 판정   master/service_restart.py
    root helper   /usr/local/sbin/ax-service-restart-root  (root:root 0755)
    sudoers       /etc/sudoers.d/ax-service-restart       (root:root 0440)

root helper는 AX 유닛 8개만 받고 인자는 정확히 하나만 허용한다. 임의 유닛, 임의 systemctl 하위
명령, 추가 셸 인자는 helper와 sudoers 양쪽에서 거부한다. 최초 설치만 `pkexec`로 좁은
`install`·`visudo`를 호출하고, 이후 재시작은 NOPASSWD helper를 쓴다.

## 2. 성공은 반환 코드가 아니라 전후 상태다

재시작 전후 `ExecMainStartTimestampMonotonic`이 달라야 한다. 상주 simple 3종은
`active/running`, oneshot 5종은 `Result=success`와 `ExecMainStatus=0`을 요구한다. 처음 구현은
모든 유닛에 active/running을 요구해 oneshot을 항상 실패시킬 뻔했고, 운영 설치 전에 실제 unit의
`Type=`을 전수 확인해 갈랐다.

운영 실증은 새 도구로 `ax-projects`를 재시작했다.

    기동 시각  2026-09-20 14:30:08 → 14:44:50 KST
    최종 상태  active/running · Result=success · PID 101754
    회귀       신규 6/6 · 기존 서비스 19/19 · 프로젝트 63/63

## 3. Codex에서 레드마인 키가 「없는 것처럼」 보인 원인

`master.redmine.api_key()`는 환경변수 다음에 `docker exec redmine-db-1 psql ...`로 컨테이너
DB를 읽는다. Claude는 이 경로를 그대로 썼다. Codex 기본 샌드박스는 Docker 접근을 막고 이 함수는
예외 대신 빈 문자열을 반환하므로, 첫 조회가 실제 키 부재처럼 보였다.

샌드박스 해제 승인으로 같은 좁은 Python 조회를 재실행하자 키 존재와 `#647` 조회가 확인됐다.
키 자체는 출력하지 않았다. 다음 Codex가 반복하지 않도록 이 절차를
`machines/sim-desktop-agents.md`에 넣었다.

## 4. 이 세션의 기록 사고

레드마인 완료 노트를 Python `-c` 인자 안에 넣으면서 Markdown 백틱을 셸에서 안전하게 격리하지
않았다. 셸이 네 구절을 명령 치환해 커밋 해시, CLI 경로, 판정 필드 이름, `visudo` 글자가 노트에서
빠졌다. 이슈 상태 `완료`, 진행률 100%, 나머지 구현·설치·실증 근거는 정상 반영됐다.

[중요] 셸 인자에 기록 본문을 직접 싣지 않는다. 특히 백틱이 있는 본문은 저장소의 좁은 Python
도구나 안전한 입력 파일을 통해 전달해야 한다. 이번에는 실패 규칙에 따라 추가 노트로 덮지 않고
훼손 사실을 인계서와 이 리포트에 남겼다.
