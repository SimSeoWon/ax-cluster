# #796 원격 작업 취소와 잔여 실행 생명주기

2026-10-11 · Codex · 진행 정본 [#796](http://192.168.0.57:8080/issues/796)

사용자가 #796을 선택하고 로컬 서브 에이전트 수정·검증을 승인했다. `distribute`의 RAG·현재 소스 대조·방식 선택 및 `ax-redmine`의 MCP 조회·기록 절차를 따른다. 커밋·푸시·배포 승인은 아직 없다.

## 기존 Claude 실패와 현재 프로세스

10월 10일 파견 로그에서 D(.2)21:23:21, C(.33)21:23:32, A(.43)21:26:04의 Claude 호출은 session limit로 rc=1 종료했다. 조각은 pending으로 돌아가고 워커 5시간 차단 및 마스터 hold가 설정됐다. 대기열에 남은 일과 살아 있는 CLI 프로세스는 다르다. 이 로그만으로 Claude 프로세스 잔존을 확정하지 않는다.

읽기 전용 원격 조회에서 AXCluster 빌드 워커 probe는 .43/.2/.33 모두 running=0, busy=0, stale=0 등 잔존 표시가 없었다. .2/.33 AxConductor_AXCluster 예약 작업은 Ready였으며 해당 파견의 session1_conductor/Claude print CLI 프로세스는 확인되지 않았다. Windows Claude 데스크톱 앱은 실패한 파견보다 먼저 시작된 별도 프로세스이고 AXCluster 작업 명령이 아니었다. .2의 pythonw PID91420 worker_daemon은 MotionForge 소속이었다. 이를 #788 실패 잔존으로 취급하거나 종료하지 않았다.

진단 중 Windows 구분에 driven 값을 쓴 후속 조회가 .43에서 PowerShell 부재 rc127을 냈다. .43의 최초 Linux 프로세스 조회는 성공했고, 오류 조회로 환경을 고치지 않았다. .2 소속 확인은 샌드박스 SSH rc255 뒤 같은 읽기 전용 명령을 실행 승인으로 재조회하여 rc0·MotionForge=true를 확인했다. 명령줄이나 자격 정보를 출력하지 않았다.

## 확인된 소스 결함과 수정 범위

Windows Codex `runner.run_worker_session1`은 요청별 job 파일을 보내지만 마스터 timeout 또는 런처 기동 실패 뒤 원격 job을 취소하지 않는다. 런처 main은 완료 표시 없는 job을 나중에도 실행한다. 요청자 대기 종료와 원격 실행 수명이 분리돼 지연 실행이나 잔여 작업이 가능하다. 이는 당시 Claude 실패 경로의 원인 실증과는 별개다.

`session1_conductor.run_job`은 timeout 때만 프로세스 트리를 종료하며, 일반 communicate 예외에서는 실행 프로세스 정리가 빠져 있다. 기존 큐 cancel API는 상태를 취소로 바꾸고 단일 task 조회 API가 존재한다. 일시적인 heartbeat 실패를 명시적 취소로 해석하지 않는다.

허용 구현 파일은 `master/work/runner.py`, `client/runtime/session1_conductor.py`, `master/test_runner.py`다. 요청별 취소 표시, job 유효 시간, 명시적 큐 취소 확인과 실행 예외의 프로세스·중계 정리를 검증한다. 다른 프로젝트의 상주 서비스, 자동 hold·재시도 정책, 직접 SSH Claude 실행 계약은 변경하지 않는다. 운영 워커 파견이나 LLM 호출 없이 로컬 회귀를 수행한다.

## 재현과 구현

수정 전 HEAD84abb5b 런처 소스를 별도 모듈로 로드하고 cancel.flag가 있는 job에 무해한 실제 Python 프로세스를 지정했다. 프로세스 실행1회, rc0였다. 수정 후 취소·만료 job은 실행0회, rc1로 끝나며 main을 반복해도 실행0회다. 변경 전 비교는 검증 때만 사용하고 현재 HEAD에 따라 결과가 바뀌는 역사 비교 테스트를 영구 회귀 목록에 남기지 않았다.

요청별 cancel.flag와 job expires_at을 추가했다. 마스터는 큐의 명시적 cancelled 상태, 시간 초과, 기동 실패, 요청자 예외에서 해당 request_id에 취소를 전달한다. 취소 뒤 해당 시도의 done.flag를 최대15초 조회해 런처 완료 확인과 전달 성공·종료 미확인을 구분한다. 취소 신호를 보낸 것만으로 원격 프로세스 전체 종료를 확정하지 않는다.

런처는 실행 전 취소·만료를 확인하고 실행 중에도 확인해 해당 프로세스 트리를 종료한다. Codex/agy 일반 communicate 예외에서도 살아 있는 해당 프로세스만 종료·회수하며, relay 시작과 shutdown의 경합 및 중계 종료 미확인도 기록한다. 레거시 job에는 expires_at이 없어 기존 계약을 유지한다. 실제 부모·자식 프로세스 취소 종료, Codex/agy 예외 회수, 큐 조회 실패 오탐 회피, 취소 전달 실패 및 ACK를 로컬에서 확인했다.

## 검사와 운영 범위

첫 구현 최종 runner239/239 및 root 독립 autodispatch26/26 통과, diff check 통과. 공식 통합31/31(61.990초)은 runner239를 포함해 통과했다. 기본 샌드박스에서는 source_scope가 서브모듈 포인터 조회로28/32 실패했고, 같은 공식 명령을 실행 승인으로 재실행해32/32 및 전체31/31을 확인했다. 범위 밖 source_scope 코드는 변경하지 않았다.

최종 검토에서 job 전송 예외 뒤 부분 기록이 남을 가능성과 비영점 정상 완료 로그 누락을 추가로 확인해 허용3파일에서 보완했다. 전송 예외에서도 해당 시도를 취소하며, 실제 Python exit3의 원래 출력·rc·종료 로그를 보존한다. 이 두 회귀를 포함한 최종 runner241/241, diff check 통과. 최종 코드로 공식 통합31/31(61.203초) 재실행 통과했으며 runner241 및 autodispatch26을 포함한다.

운영 워커에는 배포하지 않았고 Windows 운영 프로세스 종료 실증도 아직 없다. POSIX 실제 프로세스 트리 종료와 마스터/Windows 명령 계약은 회귀로 검사했다. expires_at은 마스터와 워커의 시각이 맞는 조건에 의존한다. 직접 SSH Claude 실행 계약을 고치거나 당시 Claude quota가 잔존 원인이었다고 주장하지 않는다.

이전 #795는 cancelled, #793은 rejected이며 새 분산 작업을 등재하지 않았다. main84abb5b와 기존 미커밋 기록을 유지한다. 커밋·푸시·배포 승인 전이며 #796은 진행 상태로 둔다.

## 사용자 승인 후 커밋·배포 — 00:15 KST

사용자 「응」으로 #796 수정과 관련기록 커밋·푸시·워커배포를 승인했다. main7f70309fc115df866439ab804e7a67ac104a0b37에 구현3파일과 앞선106실증/107정리/108 및 인계 기록을 함께 커밋했다(11파일). Gitea push rc0, 실제 origin/main ref일치 확인. 배포 시작부터 종료까지 마스터 트리는 clean, HEAD7f70309를 유지했다.

`ax-deliver` 정본 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update` rc0. 마운트AXCluster .43/.2/.33 모두 배포·되읽기 검사통과3/3. payload10개, 프로젝트 로컬 skills·Codex MCP/config, 배달 출처HEAD 일치. code프로젝트의 빌드상주는 미등록으로 유지하고 세션1런처만 등록됐다.

`master.service_freshness.check`는 ax-task-queue/ax-broker/ax-projects 모두 현재코드로 판정했다. 초기 sandbox의 systemctl읽기 차단 뒤 같은 검사명령을 실행승인으로 재조회했다. 이번 변경은 발동형 파견/런처 코드이므로 서비스 재시작은 필요하지 않았다. ax-projects 시작22:04:44·active/running 유지 확인.

ax-redmine으로 커밋연결 및 #796 완료100% 기록 후 되읽기 확인했다. 최종runner241/241·공식통합31/31 및 실제 로컬프로세스정리검증, 워커파일배포3/3에 근거하며 Windows 실제 운영취소·새분산완주 실증은 하지 않았다. 새work 등재/파견 없음. 이 배포 후 보고서와 인계서 결과 기록만 미커밋이며 추가커밋승인으로 확대하지 않는다.
