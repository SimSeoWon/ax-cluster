# 89. Codex 워커 준비 검사와 실제 쓰기 검증

2026-10-03 23:59 KST · #716 후속 · Codex 마스터.
사용자 「코덱스가 워커들 처리할 수 있도록 수정해줘」, 로컬 방식 선택 및 실패 후 재개 승인.

## 변경과 근거

RAG `search_context_tool`로 session1_conductor/residency 관련 문서를 검색하고 현재 소스와 대조했다.
기존 `master/work/conductor.py`는 Windows Codex 준비 검사를 SSH Session 0의
`codex sandbox cmd.exe`로 수행했다. 실제 `runner.run_worker_session1`은 `/IT /RL LIMITED`
예약 작업으로 로그인 사용자 세션에서 실행한다. 서로 다른 경로의 실패가 모드 전환을 막았다.

로컬 구현 에이전트와 읽기 전용 검토 에이전트로 다음 두 파일만 코드 수정했다.

- `master/work/conductor.py`: Codex의 프로젝트 로컬 `.agents/skills/ax-work/SKILL.md` 확인.
  Windows는 `schtasks /query /tn <프로젝트 런처> /xml` 및 `whoami /user /fo csv /nh`로
  InteractiveToken, LeastPrivilege, 활성화 여부, 실행 계정/SID, Python 절대경로,
  해당 체크아웃의 배달 런처 경로와 런처 파일을 검증한다. 임의 명령 입력 면은 추가하지 않았다.
  XML이 생략하는 기본 LeastPrivilege/Enabled=true를 처리한다. SessionId=1을 강제하지 않는다.
- `master/test_orchestration_control.py`: 정상 등록·SID·기본값 생략·python.exe/pythonw.exe,
  틀린 세션·권한·계정·경로·XML·CSV·누락 배달물 등의 거부 회귀를 추가했다.

등록 검사는 인증·로그인·실제 모델 도구 실행 성공을 보장하지 않으며 반환 note에 별도 실증을 명시했다.
원전 AgentTest의 조사된 backend 실행 코드에는 이 Codex 예약 작업 계약을 대체할 근거가 없었다.

## 검사와 실제 워커 실측

- 루트 직접 `.venv/bin/python -B -m unittest master.test_orchestration_control`: **18/18 OK**.
  구현 에이전트의 최종 검사도 18/18. 독립 읽기 리뷰에서 차단성 문제 없음. `git diff --check` 통과.
- 수정한 `worker_mode_readiness('codex', 'AXCluster')` 실제 조회: **3/3 ok**, 세 워커 공식 CLI 0.159.3.
- 읽기 조회: `.2`의 explorer SessionId=1, `.33`=18. 예약 작업 UserId SID가 SSH 계정과 일치.
  요청 시작 전 미완료 session1 job 0건. 워커 소스 HEAD는 세 대 모두 `a3eb788`, Git clean.
  마스터 HEAD `90a65a5`와 워커 소스는 다르다. 이 결과를 전체 배달 버전 정합 검사로 확대하지 않는다.

| 워커 | 진단 대상 | 결과 |
|---|---|---|
| `.43` | `.ax/work/ax_codex_readiness_7c4be9abca324072ad55c2905303b5cf/probe.py` | rc0, RESULT DONE, shell read 2회, apply_patch completed 1회, 내용 정확, Git 불변 |
| `.2` | `master/_ax_codex_probe_031b90b65f83477c8c7689f447abeb87.py` | rc0, RESULT DONE, shell read 2회, apply_patch completed 1회, 정확한 내용, 55초 회수 |
| `.33` | `master/_ax_codex_probe_5d2ba43ec69c418c9ab77a08f5b13bdb.py` | rc0, RESULT DONE, shell read 2회, apply_patch completed 1회, 정확한 내용, 43초 회수 |

Windows는 기존 배달 런처와 workspace-write/unelevated 설정을 그대로 사용했다. 진단 파일 밖
Git 변경 없음. 성공한 소스 진단 파일 두 개는 내용·신원을 확인해 `.ax/work/<task>/completed_source_probe.py`
로 보관하고 생성했던 원본만 제거했다. 제거 후 양쪽 Git clean. session1 결과와 로그는 보존했다.
소스 파일 구현·큐 파견·커밋·통합·finalize의 분산 전체 완주 검증은 아니다.

마스터 출력 아티팩트:
`/tmp/ax-codex-worker-smoke-results-20261003/` (`.ax` 진단),
`/tmp/ax-codex-source-smoke-results-20261004/` (Windows 소스 진단).
파일 이름의 20261004와 달리 실제 실행 시각은 2026-10-03 23시대다.

## 실패와 검색 결과

처음 조회에서 없는 파일/경로와 `/tmp` 전용 디렉터리 접근 거부로 중단을 반복했다.
사용자가 이번 작업의 읽기 전용 파일 없음·접근 거부는 범위를 좁혀 조사하도록 예외를 승인했다.
실제 코드·검사·워커 실행 실패 중단 규칙은 유지했다.

첫 새 테스트 실행은 raw string 끝의 역슬래시로 SyntaxError, 실행 0건이었다. 재개 승인 후
fixture를 수정하고 위 회귀를 통과했다.
첫 Windows `.ax/work` 진단은 양쪽 shell read/회수 rc0였으나 apply_patch failed/RESULT BLOCKED였다.
대체 셸 쓰기로 성공을 만들지 않고 중단했다. 재개 승인 뒤 ACL·로그를 읽고 소스 경로 비교 진단을 했다.
`.ax`와 `master`의 ACL 차이를 관측했지만 실패의 근본 원인은 확정하지 않았다.
ACL·sandbox 설정·런처·바이너리를 바꾸지 않고 소스 경로에서 두 대 모두 성공했다.

사용자 요청으로 공식 문서를 검색하고 페이지를 열어 확인했다:
[Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)는 unelevated의 제한 토큰/ACL
경계를 설명한다. [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)는
기본 보호 경로 `.git`·`.agents`·`.codex`를 명시하며 `.ax`는 목록에 없다.
따라서 `.ax` 이름 자체가 보호돼 실패했다고 단정하지 않는다. `sandbox.log` 필터 조회에는
해당 진단 요청의 원인을 확정할 오류 줄이 없었다. 공식 문서를 현재 AX 실측의 보장으로 인용하지 않는다.

## 운영 반영 대기

코드·문서 미커밋. 서비스 재기동·워커 모드 변경·소스 Git 동기화·재배달은 하지 않았다.
운영 ax-projects는 이전 conductor를 이미 import한 상태이므로 로컬 검사 성공이 운영 반영은 아니다.
승인 후 Gitea 커밋·푸시, 필요한 소스/배달 정합화와 ax-projects 재기동,
공용 `set_worker_mode_tool('codex')` 변경 및 실제 조회로 확인한다.
`#720` 한도 분류와 `#721` Claude 인증 검사는 범위 밖이며 수정하지 않았다. #716 완료 판정도 남아 있다.
