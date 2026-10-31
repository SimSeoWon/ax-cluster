# SSH·데몬 회귀 — Gemini 보고서 전체 검수

작성: Codex · 2026-10-31 · 소스 HEAD `1366e08035602599496cf3cf62fe666ff2e718f8`.

검수 대상: [Gemini 원 보고서](2026-10-31-ssh-daemon-regression-audit.md).
이 문서는 앞선 [핵심 10건 표본 검증](2026-10-31-ssh-daemon-regression-audit-codex-verification.md)을 확장한다.

## 판정

**보고서 전체를 검수했다. 핵심 결론은 맞지만 원 보고서를 그대로 구현 지시서로 쓰면 안 된다.**

요약·조사 방법·결정 이력·발견 20개·회귀 경로 4개·파일 목록·유지 대상·권고 5단계·근거 목록·한계를 모두 읽고 대조했다. 인용 71개는 전부 검수표에 넣었고, 쉼표로 이어지는 추가 줄 범위도 별도 검사했다. 앞서 제외했던 원격 머신의 등록·프로세스·배달 잔재와 홈/체크아웃 진입 지침도 조회했다.

현재 3대에서 대상 AX 작업 데몬은 조회되지 않았다. 하지만 3대의 AXCluster에 데몬 파일과 옛 체크아웃 지침이 남아 있으며, `.2` 홈의 Claude/Codex 진입 지침도 서로 다르다. 코드·배달·검사가 아직 옛 동작을 정당화하므로 **현재 실행 중이 아님**과 **다음 작업에서 재생성되지 않음**을 구분해야 한다.

## 발견 20개 전부의 검수 결과

| ID | 판정 | 대조 결과·정확한 해석 |
|---|---|---|
| D-01 | 확인 | `client/init/residency.py:294`의 판정은 requester/code/index_only/데몬 미배달/UE5 없음/비마운트를 제외하고 True. Unreal이라는 단어만으로 무조건 등록하는 것은 아니다. 현재 마운트 AXCluster(code)에서는 필요 판정이 False다. |
| D-02 | 보정 | `bundle.py:2072` 및 `:2377`의 재등록 경로는 맞다. **refresh가 즉시 schtasks /run을 호출한다는 설명은 틀림**. 갱신은 상태 관찰·restart 깃발·필요시 PID 종료이며, 신규 등록 뒤에는 5분 감시자가 기동할 수 있다. 즉시 기동은 별도 ensure 경로다. |
| D-03 | 확인 | `master/client/__main__.py:547`은 required인데 미등록이면 실패. `:618` 이후 전체 판정에 포함되고 최종 rc=1이 된다. code나 UE5 없는 워커의 미등록까지 실패시키는 것은 아니다. |
| D-04 | 확인 | `master/test_no_integrator.py:100`의 허용 목록 밖 SSH 빌드 호출을 검사한다. 서버가 UE5를 로컬로 실행하는 것과 서버가 SSH로 빌드를 주관하는 것을 가드가 구분하지 못한다. |
| D-05 | 확인 | `master/test_plan_build.py:141`은 plan_build에 두 빌드 호출 문자열이 없을 것을 요구한다. **현재 제약**은 확인했지만, 이 검사가 과거 구현 선택을 일으켰다는 인과·실패 실행 기록까지 입증한 것은 아니다. |
| D-06 | 확인 | `master/plan_build.py:53` enqueue → watch → submission 조회·판정·종결. SSH 연결 구현이 아니다. |
| D-07 | 확인 | `master/client/bundle.py:169`의 worker payload에 데몬·ax_safety가 포함된다. 실제 3대 AXCluster에서도 두 파일 해시를 읽었다. |
| D-08 | 확인 | `worker_daemon.py:54` 기본 20초, `:138` claim, `:195` submit. 기본 build, opt-in 코드 경로의 오래된 설명도 남아 있다. 등록 제거와 실행 파일 제거는 별개다. |
| D-09 | 확인 | `ax_safety.py`의 crash/sleep/quick-edit 가드 및 production import가 worker_daemon에 한정되는 것을 전수 검색으로 대조했다. 삭제 승인이나 이미 배달된 파일 제거까지 뜻하지 않는다. |
| D-10 | 확인 | `buildjob.py:72`는 distribution_mode=pull로 work를 등록하고 이어서 build 태스크를 등록한다. **큐 전체의 pull 필드와 branch/verify 호환 계약까지 모두 같은 폐기 대상으로 볼 수는 없다.** |
| D-11 | 별도 판단 | submission 라우트·핸들러·태깅은 존재한다. 하지만 **읽기 API 자체는 SSH 정책 위반이 아님**. 현재 production 소비자는 plan_build이고 핸들러는 일반 제출 사실을 읽는다. SSH 전환 뒤 유지/삭제를 판단한다. |
| D-12 | 보정 | worker_daemon 검사와 공식 목록 등록은 맞다. 그러나 이 파일에는 유형 격리·worker 권한·제출 신원 같은 일반 보안 계약도 있다. **파일 전체를 삭제한다면 일반 계약을 다른 검사로 보존해야 한다.** |
| D-13 | 확인 | `test_residency.py:561` 이후 UE5 워커 required=True를 단언한다. 단순 행렬 검사뿐 아니라 required의 생산 기준을 바꿔야 한다. |
| D-14 | 추론 유지 | RAG가 데몬을 현역처럼 설명하는 본문과 실제 검색 반환은 확인. 특정 후속 에이전트가 이것 때문에 회귀했다는 모델 내부 인과는 미입증. source 잔존 중 문서만 삭제하면 재합성될 위험도 추론이다. |
| D-15 | 확인 | `docs/14-onboarding-runbook.md:208` 이후 상주 재등록을 현행 절차로 안내한다. 최신 정책과 충돌한다. |
| D-16 | 확인 | `master/README.md:67`·`:102`·`:115`, client README, bc250 문서에 옛 규범이 남아 있다. bc250 문서는 이 보드의 상주 부재를 맞게 말하면서 다른 UE5 워커의 상주를 정상으로 설명하는 형태다. |
| D-17 | 보정 | ax-worker-setup 스킬의 3단계는 배달·상주 등록을 말한다. **스킬이 직접 AxWorker 생성 명령을 제공하는 것은 아님**. 2단계의 옛 등록 해제는 필요한 철거 기능이므로 유지할 수 있다. |
| D-18 | 확인 | #406 본문은 데몬 자기 git pull과 SSH의 설치·기동 한정을 목표로 한다. 현 SSH 작업 주관과 직접 충돌한다. |
| D-19 | 보정 | #344는 옛 데몬 구조를 **복원 지시하는 이슈가 아님**. 상주 제거 뒤 directive가 소비·폐기되는 문제를 설명하고, 서버 파견 루프가 따르기/표면 폐기/현상 유지의 선택을 요청한다. 첫 두 선택은 현재 구조와 양립 가능하다. |
| D-20 | 확인 | #259 본문의 오래된 클라 절에 deliver→claimer 상주→check가 남아 있다. 서버 SSH 초기화 자체는 올바른 목표이며, 그 전체 목표를 폐기할 이유는 없다. |

분류: **확인 14 · 설명/처분 보정 4 · API 처분 별도 판단 1 · 추론 1 = 20개**. 독립 버그 20개 또는 새 발견 20개라는 뜻은 아니다.

## 보고서의 나머지 주장과 권고 검수

### 조사 방법·통계

- 자료 718개는 사본 분석 범위이며 전체 디스크·모든 트윈을 뜻하지 않는다. RAG 문서 4개와 최신 결정 2개는 표본이다.
- 같은 사본 718개에 14개 키워드군을 재적용한 매칭 파일은 467개다. [파일별 목록](2026-10-31-ssh-daemon-regression-audit-inventory.md)에 무매칭 파일까지 모두 남겼다.
- 보고서 표의 일부 매칭 수·파일 수는 재현값과 다르다. 정확한 통계는 앞 검증 문서의 줄 단위 결과를 따른다.
- 줄 범위 유효성이 내용 일치를 보장하지 않는다. 예: runner.py:305-311은 heartbeat가 아닌 Codex 파서다. 실제 `_Beater`는 `:1053` 이후, claim은 `:1167`, infer의 사용례는 `master/work/infer.py:1053`이다.

### 결정 이력·회귀 경로

- #320 철거→#404 복원→#860 철회와 #857 T4 큐 경로·T6 빌드 기록은 이슈와 최신 결정 원문에 있다. 과거 실증을 이번에 재실행한 것으로 보고하지 않는다.
- #404는 ⑤ pull 서술과 Windows 세션 0 문제를 복원 근거로 적었다. 세션 0 문제를 해결하는 런처와 상주 큐 폴링의 필요성은 별개다.
- #857 T1의 SSH 빌드 2회 성공은 해당 리비전·시험 조건의 실증이다. 보고서의 **기술적으로 완벽히 동작**이라는 일반화는 과도하다.
- Cycle 1의 재등록 위험은 확인. refresh→즉시 실행 화살표는 잘못됐다. 등록 후 스케줄러 실행 또는 명시적 ensure와 구분한다.
- Cycle 2의 check 실패는 코드로 확인. 그 실패 뒤 사람이 반드시 deliver를 실행한다는 부분은 가능한 운영 경로이지 자동 코드 경로가 아니다.
- Cycle 3의 코드·가드 충돌은 확인. **테스트가 실제 깨졌고 그래서 회피했다**는 과거 실행 기록은 이 자료에서 확보하지 못했다. 본문은 의도/인과를 확정하는 표현을 줄여야 한다.
- Cycle 4는 보고서처럼 추론으로 유지한다. RAG가 폐기 소스를 정확히 요약했더라도 설계 기준으로 재사용하면 위험하다.

### 유지 대상·권고

- `build_local.py`는 자동 SSH 브리지가 아니다. 기본은 `builder or run_build_local`이다. 보고서에 이미 불일치 표시했다.
- `supersedes: ["404", "204"]` 권고는 현 단일 문자열·결정 파일명 계약과 다르므로 실행하면 안 된다. 이미 불일치 표시했다.
- AxConductor는 주기적인 큐 폴링 데몬이 아니다. 단, 현재 등록 명령은 `/sc once /st 23:59`의 **일회 예약 트리거를 포함**하므로 문자 그대로 오직 수동 /run으로만 실행될 수 있다고 단정하는 설명은 부정확하다. 이번 실물 조회에서는 트리거 상세까지 읽지 않았다.
- AxConductor·서버 systemd·Ollama·서버 claim/heartbeat·골조 SSH/UHT 게이트는 유지 대상이다. 일반 worker 권한·제출 신원 검사도 보존해야 한다.
- 오래된 AxWorker를 해제하는 코드까지 지우면 철거를 어렵게 한다. 미등록 정상만 확인하고 **금지 등록 존재를 실패로 보는 검사**를 잃어서도 안 된다.
- 신규 등록 차단을 먼저 하고 SSH 대체를 실증한 뒤 폐포를 정리하는 순서는 타당하다. 문서 경고와 이슈 정정까지 철거 후로 미룰 필연성은 없다.
- 원 보고서의 최종 실증은 .2만 본다. 완료 조건은 3대 전체와 모든 등록 대상 프로젝트의 관련 배달물·스케줄러이며, 로그인 런처·SSH 파견의 무손상도 확인해야 한다.
- 마운트 전환·배달은 실제 쓰기다. 원 보고서의 즉시 수행 표현은 승인·플랜·대상 목록 확인을 대신하지 못한다. 이번 검수에서는 실행하지 않았다.

## Gemini가 놓친 회귀 입구와 분류 보정

| 항목 | 근거 | 판정 |
|---|---|---|
| 별도 데몬 시작 CLI | `master/client/__main__.py:728` → `bundle.ensure_worker_daemon:2275` → `residency.ensure_commands:161` | 실제 schtasks /run 또는 Linux nohup 경로. ensure는 desired_state의 code/마운트 조건을 그대로 소비하지 않는다. 등록 부재·타입·프로세스 상태 등 분기를 함께 정리해야 한다. 이번에는 실행하지 않음. |
| 모든 워커의 체크아웃 지침이 옛 정책 | 3대 AXCluster CLAUDE.md: .2 382행, .33/.43 381행 | #404의 build 상주 복원을 정상으로 설명. 아래 원격 증거에 줄·해시 보존. |
| .2 홈 Claude/Codex 지침 불일치 | `C:\Users\janus\CLAUDE.md:109` 대 `C:\Users\janus\AGENTS.md:109` | 전자는 No resident daemon, 후자는 AxWorker/AxConductor now 및 5분 상주 설명. **확인된 별도 회귀 입구**. |
| 배달 도장과 git 체크아웃은 다른 축 | 3대 .ax 출처 f29aaf0, 체크아웃 HEAD는 서로 다른 과거 커밋 | payload 배달 일치를 체크아웃의 커밋 문서 최신화로 해석하면 안 됨. 임의 reset/checkout 없이 조회만 함. |
| 배달 템플릿의 옛 대응표 | `master/client/workshop/README.md:12`, `:21` | watch.exe/worker.exe 대체로 AxWorker/worker_daemon을 현행 안내. 원 보고서의 파일별 전체 목록에서 빠짐. |
| 옛 ⑤를 현행 정본으로 인용 | `master/client/spec.py:150`, `docs/8-git-authority.md:93` | 다음 작업을 요청한다는 표현이 최신 서버 배정 결정과 충돌. 역사 인용이라도 현행 정본 표지가 있어 회귀 가능. |
| 이력 경고 자체를 잔재로 오인 | 원 보고서가 `docs/orchestrator-handoff.md`를 잔재 전체 목록에 포함 | 현재 인계서는 철거 정책과 남은 위험을 올바르게 경고한다. 단순 데몬 언급만으로 수정/삭제 대상이 아님. |
| pull 필드를 모두 지우는 과잉 수정 위험 | `task_queue/models.py:58`, `logic.py:100`, `logic_claim.py:32`·`:102` | 큐 내부 분배·verify/backpressure 호환 계약이다. 서버 SSH/원격 폴링과 항상 일대일로 같지 않다. 사용처 판정 없이 제거 금지. |

이미 제거된 infer의 pull 회수 절(`master/work/infer.py:1566`)은 현재 잔재가 아니다. 오래된 기억의 해당 줄을 그대로 현재 결함으로 복사하지 않았다.

## 원격 3대 실물 대조

등록부에 있는 모든 4개 프로젝트의 워커/요청자 경로를 조회했다. 비마운트 프로젝트는 읽기만 했으며 배달하지 않았다. 파일 해시 조회가 비어 있는 경우를 무조건 파일 없음으로 단정하지 않았다.

| 머신 | 예약 작업 / cron | 대상 프로세스 | AXCluster 배달 파일 | AXCluster 체크아웃 HEAD |
|---|---|---|---|---|
| .2 | AxConductor·AxConductor_AXCluster, AxWorker/AxClaimer 없음 | Python/watch/worker 이름과 명령행을 함께 제한한 조회에서 0 | worker_daemon.py·ax_safety.py 존재 | 0941944666d598399a567b58a3700660e77bb3e5 |
| .33 | AxConductor_AXCluster·AX_Ollama33, AxWorker/AxClaimer 없음 | 같은 기준으로 0 | 두 파일 존재 | 749675ca7ac5c67a4dbbf72161fead3846426a85 |
| .43 | user cron은 PATH 한 줄 | ps 조회·로컬 필터로 0 | 두 파일 존재 | 169970124034d59223f0646ec9e19e0e8c45d555 |

- 3대 AXCluster `.ax/config.json`의 delivered_by.commit은 `f29aaf0`, dirty=false다. master HEAD `1366e08`과 다르지만 이번에 임의 동기화하지 않았다.
- .2 ModularStage에도 두 데몬 파일이 남아 있다. .43의 ModularStage·NS·MotionForge에도 남아 있다.
- .2 NS·MotionForge는 config 조회가 빈 응답이었다. **클론 없음과 접근/읽기 실패를 확정 구분하지 못했으며 장애로 단정하지 않았다.**
- .33의 게임 프로젝트는 requester 역할이므로 데몬 파일 해시가 없는 것을 AXCluster worker 상태와 혼동하지 않았다.
- 전체 디스크에서 임의로 개명된 실행파일·다른 사용자 계정·모든 systemd 시스템/사용자 유닛까지 포렌식한 결과는 아니다. 알려진 AX 이름·등록 경로·프로세스 패턴에 대한 시점 조회다.
- 기본 .43 프로세스 필터 조회 rc=1은 부재 판정에 사용하지 않고, 별도의 ps 조회 rc=0과 필터 결과로 재확인했다.

## 홈 지침·메모리

- 마스터의 `.claude/projects/-home-sim/memory`에서 54개 Markdown 경로를 열거해 관련 표현을 전수 검색했다. server_ssh_no_worker_daemon·distributed_pipeline_intended_shape·pipeline_redesign_axis·codex_windows_ssh_sandbox는 최신 폐기 결정을 명시한다.
- AgentTest 배포 모델 문서는 **AgentTest의 역사**를 설명하며 AX의 현 실행 규범으로 사용하면 안 된다. 같은 단어가 있다고 삭제 대상으로 잡지 않았다.
- 분산 7단계 메모리에는 SSH 변경은 반영됐지만 다른 오래된 구현 공백 설명이 남아 있다. 데몬 회귀와 다른 축은 이번에 고치지 않았다.
- 마스터 `.codex/AGENTS.md`는 스킬 우회 금지 기억이며 데몬 복원 지시가 아니다.
- 원격 홈에서 존재가 확인된 CLAUDE.md·AGENTS.md의 관련 문장을 조회했다. `.2`의 불일치는 위 표와 같다. `.43` 홈 CLAUDE는 UE5 워커의 상주를 여전히 정상 설명한다. `.33` 조회 범위에서는 데몬 복원 지시를 발견하지 못했다.
- 원격 모든 세션 메모리·캐시·Codex 내부 DB의 전수 해석까지 했다는 주장은 하지 않는다. 이번 전체 검수는 **Gemini 보고서의 모든 항목**에 대한 검수이며 모든 머신 저장장치의 무결성 보증이 아니다.

## 검사 결과

| 기존 검사 | 결과 |
|---|---:|
| test_no_integrator | 14/14 |
| test_plan_build | 21/21 |
| test_residency | 145/145 |
| test_worker_daemon | 22/22 |
| test_task_submission | 15/15 |
| test_client_bundle | 536/536 |
| 합계 | **753/753, 6개 파일 전부 rc=0** |

기본 샌드박스에서 제출 API 검사는 종료가 지연됐다. 동일 검사만 180초 제한으로 승인된 샌드박스 해제 실행했고 15/15로 종료했다. 실제 큐·워커가 아닌 임시 TaskIndex·가짜 전송/빌더·TestClient 검사다. 다른 검사도 파일별 종료코드를 따로 확인했다.

**통과의 의미는 현행 코드 계약이 유지됨**이다. 데몬을 금지하는 새 정책에 맞는다는 뜻이 아니다. 데몬 payload·required=True·SSH 빌드 금지까지 통과 조건에 들어 있으므로 회귀 검사를 정책에 맞춰 재정의할 필요가 있다. 구현 변경이 없어 공식 통합 전수·UE 빌드·실제 파견·마운트 전환은 실행하지 않았다.

## 산출물과 다음 판단

- [인용 전체 대조표](2026-10-31-ssh-daemon-regression-full-review-citations.md)
- [원격 조회 증거](2026-10-31-ssh-daemon-regression-full-review-evidence.json)
- [718개 파일 검색 목록](2026-10-31-ssh-daemon-regression-audit-inventory.md)

정리 우선순위는 **상주 생성·요구·ensure 경로 차단과 정상 런처 보존 → 가드·SSH 빌드 연결 → 대체 실증 → 코드·배달 잔재 정리**다. 워커 체크아웃 및 .2 홈 AGENTS 지침 불일치는 함께 다룰 독립 대상이다. 현행 문서·스킬·RAG·이슈의 정정도 필요하다. 다음 구현 플랜에는 일반 권한 검사 보존, 금지 등록 검출, 3대 비재생성 실측을 완료 조건으로 넣어야 한다.

검수 외 코드·설정·서비스·예약 작업·원격 파일·마운트·Redmine은 변경하지 않았다. 보고서 파일만 작성·표시했으며 커밋·푸시는 하지 않았다.
