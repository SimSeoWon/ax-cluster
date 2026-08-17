# 21 — #204: 빌드 게이트 큐 잡 + 작업장 claimer (1단계) · 추론 pull (2단계)

착수는 사용자 지시(2026-08-18)로 — 이슈의 착수 조건(UE5 워커 2대+ 또는 push 방식이 실제로
아플 때)은 **사용자가 해제**했다. 범위도 사용자 확정: *"일단 기능 작동을 확인하고 확장"* —
빌드 잡 + claimer 먼저, 추론 pull 은 그 다음.

## §1 설계 — κ.0 CI 러너 패턴, 경계는 토큰이 강제한다

원전 κ.0 (`local_llm_distributed_workers_plan_v5.0.md:276`): 통합 빌드게이트를 인프라에
고정하지 않고 task_queue 잡으로 큐잉 → UE5 있는 워커가 claim. 워커의 계약은 **실행+보고,
판단 없음** — 재시도·에스컬레이션·머지는 마스터(①)가 보고된 사실로 결정한다.

    마스터        work/buildjob.py — enqueue(전용 work + type="build"·requires=["ue5"]
                  태스크) · watch(사실만 내민다, 해석 없음)
    작업장        work/claimer.py — 폴링 데몬. claim 에 types=["build"] 신고, 빌드 실행,
                  pass/fail+로그 꼬리를 submit. **실패도 submit 이다** — submit-fail 은
                  "실행 자체가 안 됐다"에만
    안전 가드     work/ax_safety.py — 원전 worker/safety.py(81줄) 글자대로 이식.
                  [중요] #165 의 부활 조건("상주 데몬이 생길 때")을 claimer 가 정확히 충족.
                  crash handler · sleep guard · quick-edit guard (뒤 둘은 윈도우 전용)
    토큰          auth.WORKER_SCOPE — claim·heartbeat·submit·submit-fail·GET tasks 만.
                  [중요] 등록·verify·정리는 이 토큰으로 **못 한다** — κ.0 ①/② 경계를
                  스코프가 강제. 규칙 3번째 원소는 접미사(task_id 가 경로 중간이라
                  접두어만으론 verify 를 못 가른다)
    유형 필터     claim 요청의 types — [중요] requires 는 "태스크에 필요한 능력"이지 "워커가
                  다룰 유형"이 아니다. ue5 능력을 신고한 빌드 claimer 가 requires 빈
                  infer 태스크를 집으면 Flow Y 의 일감을 훔친다. None = 전 유형(하위호환)
    배달          deliver 의 역할 토큰이 requester 전용 → 역할 인식으로. worker 페이로드에
                  claimer 폐포 7종 (판단 모듈 review·coordinator 는 **안 간다** — 테스트로
                  계약화)

[중요] Flow Y 의 SSH 직접 경로는 그대로 있다(§8.4 — 기존 기제는 측정이 뒤집기 전까지
가역 보존). 경로 선택은 호출자가 명시하고, 조용한 폴백은 없다.

## §2 라이브 E2E (2026-08-18 01:13~01:15)

    01:13:53   마스터: buildjob enqueue → work 등록 + task 515348bf (type=build)
    01:14:06   .2: claimer --once — claim 즉시 성공 (worker_id=192.168.0.2)
    01:15:56   UE5 빌드 109.1s PASS → submit HTTP 200
    큐 상태     submitted · assignee=192.168.0.2 · epoch=1 · attempt_count=1 —
               사실이 전부 마스터에 남았다

스코프 라이브 확인 (실 서비스 8101 대상):

    worker 토큰   claim → 204(허용·잡 없음) · works 등록 → 403 · verify → 403
    [중요] 403 이지 401 이 아니다 — 신원은 맞고 권한이 없다는 구분이 살아 있다

배달: `.2`(worker)·`.33`(requester)·`.43`(worker) 3대 전부 해시 대조 통과. worker 역할에
`.ax/token`(worker 스코프) 첫 배달. [주의] `.43` 은 ue5 능력이 없으므로 claimer 를 돌려도
빌드 잡을 집지 못하는 게 설계다 — 파일만 놓였고 기동은 안 했다.

테스트: 전체 3489/3489 (claimer·buildjob·스코프 신규 11 포함).

## §3 운영 — sudoers 설치 (사용자 직접, 2026-08-18)

`/etc/sudoers.d/ax-cluster-services` — `systemctl restart` 5종(ax-task-queue · ax-broker ·
ax-projects · ax-indexer.service · ax-status.timer) NOPASSWD. 사용자가 직접 설치하고 확인.
이제 세션이 서비스 재기동을 비밀번호 없이 집행할 수 있다 — [중요] 단, 원전 5조의 결은
그대로다: 대화형 세션이 **임의로** 재기동하지 않고, 코드 반영 등 사유가 있을 때 한다.
이번 세션 확인 시점에 큐 서비스는 이미 새 코드로 재기동돼 있었다(01:03).

## §4 남은 것 (1단계 시점 — §5 이후 갱신)

    1. 커밋 — [완료] 5c11f06
    2. 추론 pull 확장 — [완료] §5 (사용자 지시로 착수, 같은 날)
    3. claimer 상주 데몬화 여부(지금은 --once 수동/호출식) — 미정, 사용자 결정
    4. E2E 산출물: work 20260818_0113_buildjob… — [완료] §7 의 close 로 종결(merged)

## §5 #204 2단계 — 추론 pull (사용자 지시 "추론 pull 확장 진행해")

### 설계의 갈림길과 그 답 — 확정 결정 > 원전 코드

원전 대조에서 갈림길이 하나 나왔다. 원전 토폴로지(cluster_coordinator.py)는 **워커가
구현체를 ephemeral `attempt/` 브랜치로 push** 하고 서버가 verify_and_merge 한다 — pull
워커가 응답을 git 으로 돌려보내는 그 모양이 원전에 실재한다. 그러나 **Flow Y (사용자 확정
2026-08-14)** 가 「워커는 추론 텍스트만, attempt 쓰기는 마스터」를 이미 확정했고, M4 의
교훈이 정확히 「확정 결정 > 원전 코드」다. 그래서:

    회수 = 마스터 주도 scp **읽기** (push 파견의 read_response 와 같은 자리·같은 수단)

[중요] #185(git-carried)와 모순이 아니다 — #185 가 scp 를 버린 이유는 *"pull 데몬은 claim
시점에 마스터가 밀어줄 수 없다"* (배달 방향, 마스터 부재)였고, 회수는 마스터가 루프에
있는 시점(collect·통합)에 일어나므로 그 제약이 성립하지 않는다.

### 무엇이 생겼나

    워커 (claimer)   --types=build,code opt-in. code 태스크: durable task/<id> 를 자기
                     클론에서 fetch+show 로 실체화(#185 전제 — blob sha 기록) → claude -p
                     (ax-infer, 프롬프트는 infer.py 정본과 글자 동일 — 테스트가 대조) →
                     사실을 result.json 에 (rc·stdout·blob·epoch·소요). [중요] 판단도
                     submit 도 없다 — 태스크는 claimed 로 남는다(push 파견과 동일 계약,
                     submit 은 통합자가 빌드 통과 후). DONE 기록은 재사용(이중 구매 방지,
                     epoch 만 갱신 — fencing 규약), BLOCKED 는 다시 돈다
    마스터 (collect)  python -m master.work.infer collect — claimed 상태 code 태스크의
                     result.json+response.txt 를 scp 로 읽어 **push 파견과 같은 judge
                     (마커+층1) → 같은 스풀**에 넣는다. 이후 통합자 경로는 완전 합류.
                     [중요] blob 불일치는 fail-closed (워커가 본 지시서 ≠ 정본이면 want
                     목록부터 신뢰 불가) · epoch 어긋남은 [주의] 로 남기고 큐 fencing 에 맡김

### 라이브 E2E (2026-08-18 01:48~01:52, 실 비용 $0.21)

    등록      [pull-e2e] work + code 태스크 5ebaba14 · carry.publish → task/5ebaba14
    .2 워커   claimer --once --types=code: claim → materialize(blob 1c66249d 대조) →
             claude 추론 32s → result.json+response.txt 기록, submit 없음
    마스터    collect: 회수 1 — judge DONE · 파일 1(AxPullProbe.h 85자, 지시 사양 그대로) ·
             층1 통과 · epoch 1 · base b1ba6af9 · $0.2132 계측까지 스풀에 안착

[중요] **E2E 가 실 함정 하나를 또 잡았다 (CP949 세 번째)**: 내 로그 문구의 em-dash(—)
하나가 `.2` 콘솔 인코딩에서 **프로세스를 통째로 죽였다** (ax_safety 크래시 핸들러가 잡음 —
이식한 가드가 첫 실전에서 제 몫을 했다). 콘솔 print 를 encode-replace 로 감싸 수정,
같은 자리에서 라이브 재확인(em-dash → `?`, 생존). 기록(result.json)은 크래시 **전에**
끝나 있어 collect 는 무영향이었다 — 원자적 기록을 로그보다 먼저 두는 순서가 옳았다.

## §6 buildjob close — 1단계의 구멍을 2단계가 메웠다

test_projects 가 실 큐를 읽다가 걸렸다: 1단계 E2E 의 buildjob work 가 **미종결로 남아
프로젝트 전환 가드(#210)를 막고 있었다.** 종결 단계가 설계에 없었던 것 —
`buildjob close <work> --result=pass|fail` 신설 (verify → auto-cleanup 의 되덮기
(ready_for_review)를 기다렸다가 merged/rejected 를 쓴다).

[주의] 실측 함정 둘: ① 마지막 verify 가 auto-cleanup 을 **비동기로** 깨우고 그 끝이
merge_status 를 되덮는다 — 종결을 먼저 쓰면 뒤집힌다 ② 단건 GET /works/<id> 는
`{"work": {...}}` 로 감싼다(목록 GET 과 다름) — 이걸 안 읽어 폴링이 60초를 헛기다렸다.
둘 다 테스트에 실물 모양 그대로 새김. 1단계 work 는 close 로 merged 종결 완료.

## §7 남은 것 (2단계 시점 — §8 이후 갱신)

    1. 커밋 — [완료] f59e0da
    2. gitea 잔재 task/5ebaba14 — [완료] 사용자 삭제 (2026-08-18)
    3. claimer 상주 데몬화 — [완료] §8 (사용자 지시, 같은 날)
    4. 실전 pull 전환 — 미정 (사용자 결정 대기, §8 의 상주는 build 만 집는다)

## §8 상주 데몬화 (사용자 지시 "상주 데몬화도 진행해")

원전 대조: worker.exe 는 **로그온된 사용자 세션의 콘솔 데몬**이었다 (runbook §1·§3 —
watch.exe 의 Job Object 자식, 사람이 띄움). 같은 전제(claude 인증·git 키 = 그 사용자의
것)를 유지하되 자가 재기동을 얹었다:

    상주 형태     claimer 를 스위치 없이 부르면 폴링 상주 (20s). pythonw 로 콘솔 없이
    싱글턴       .ax/claimer.lock **배타 잠금** — PID 파일이 아니라 OS 잠금이라 크래시
                 뒤 stale 판정이 필요 없다. 두 번째 인스턴스는 로그 남기고 exit 0
    감시자       윈도우 작업 스케줄러 `AxClaimer`, 5분마다 재호출 — 살아 있으면 잠금에
                 막혀 물러나고, 죽었으면 다음 틱에 되살아난다. 로그온 세션 한정(무암호,
                 원전과 같은 전제) — 로그아웃 중에는 다음 로그온까지 쉰다
    유형         [중요] **build 만** — 실전 pull 전환(code)은 사용자 미결정이라 상주가
                 실 work 를 임의로 집기 시작하면 안 된다 (조용한 경로 전환 금지 §8.4)
    능력 신고     [중요] 하드코딩(["ue5"]) → config.json 실측값으로 — .43 처럼 UE5 없는
                 워커가 허위 신고로 빌드 잡을 집는 잠재 결함을 함께 제거
    로그         claimer.log 512KB 상한 (넘으면 뒤 절반) · pythonw 무콘솔 OSError 흡수

라이브 검증 (2026-08-18 02:07~02:12):

    기동        schtasks /run → boot poll 20s · sleep-guard 활성 · quick-edit 해당 없음
    싱글턴      ssh 로 2번째 인스턴스 → "이미 상주 중" exit 0 (+ CP949 안전 출력 재확인)
    실전 claim  enqueue 3초 만에 **데몬이 스스로** 집음 → 빌드 2.4s PASS (무변경 트리의
               UBT up-to-date 단락 — 정상) → submit → close 로 종결

[중요] **close 의 경합, 실측 2라운드**: verify 는 merge_status 를 **두 번** 쓴다 — 동기
flip(ready_for_review, verify 핸들러 안)과 **비동기 auto-cleanup 의 마지막 쓰기**. 1차
수정(비-in_progress 대기)은 동기 flip 만 보고 통과해 같은 초에 merged 가 되덮였다
(01:43 의 첫 close 가 살았던 건 응답 포장 버그로 60초를 헛기다린 **우연**). 최종 형태:
**쓰고 → 되읽고 → 되덮였으면 다시 쓴다** (cleanup 은 verify 당 1회라 유한). 되덮임의
실물 순서를 테스트에 새김.

테스트: 전체 3504/3504 (§8 시점).

## §9 실전 pull 전환 (사용자 지시 "실전 pull 전환도 진행해")

    .2   AxClaimer /tr 에 --types=build,code (schtasks 재생성 — /change 는 암호를 물어 불가)
    .43  claude 인증 라이브 확인("OK" 2.3s) 후 편입 — **cron 감시자** (*/5분, PATH 명시)
         + 상주 폴링, --types=code 만 (ue5 없음 — caps 도 config 실측이라 build 는 애초에
         못 집는다). linger=no·sudo 불가라 systemd user 서비스 대신 cron — 무권한으로 같은
         감시자 패턴

라이브 왕복 (2026-08-18 02:22~02:31, 프로브 태스크 7019c4d5):

    1차 실패    .2 데몬이 claim 20초 안에 집었으나 fetch 가 "Gitea: Failed to execute git
               command" — [중요] **사용자가 gitea SSH 문제를 확인·수정** (근본 원인)
    구조 구멍   같은 자리에서 발견: 등록 순서상 durable publish 는 태스크 등록 **뒤**라
               (task_id 가 나와야 브랜치명이 생긴다 — 원전도 같은 모순을 work_id 폴백으로
               풀었다) 20s 폴링 데몬은 publish 전에 claim 할 수 있다 → **실체화 재시도
               5회×15s** 를 claimer 에 (재시도는 판단이 아니라 운송의 인내, 상한 후
               fail-closed)
    되살리기    failed → reverify(→submitted) → verify(revise)(→needs_revision) — 큐의
               설계된 피드백 경로로 **같은 태스크·같은 durable** 재사용 (새 잔재 0)
    2차 성공    [중요] **교차 복구 실측** — .2 가 실패시킨 태스크를 .43 데몬이 epoch 2 로
               집어 완주: claim → 실체화(blob 대조) → 추론 21s($0.23) → result.json →
               마스터 collect → judge DONE → 스풀 (파일 1, 사양 그대로)

[주의] 재기동 레이스 실측: /end 직후 /run 은 잠금 해제 지연에 튕겨 **아무것도 안 도는**
상태가 될 수 있다 — 5분 감시자가 메우지만, 손 재기동은 /end → 몇 초 → /run 순서로.

정리: 프로브 task cancel + work cancelled (미종결 0). gitea 잔재 task/7019c4d5 — 사용자
삭제 대상. 문서: win-worker-2.md(types 갱신·재기동 절차) · bc250-1.md(claimer 절 신설,
.43 은 심볼릭 링크라 pull 로 반영).

이로써 #204 전체 완료: 빌드 큐잡 → 추론 pull → 상주화 → 실전 전환. 이후 등록되는 실
work 의 code 태스크는 두 데몬이 pull 로 집는다 — 마스터 push 파견(infer run)은 §8.4
대로 가역 보존.
