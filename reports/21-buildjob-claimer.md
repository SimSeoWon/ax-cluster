# 21 — #204 1단계: 빌드 게이트를 큐 잡으로 + 작업장 claimer

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

## §4 남은 것

    1. 커밋 (승인 대기)
    2. 추론 pull 확장 — 사용자 확인 후 (#204 이슈 노트에 기록)
    3. claimer 상주 데몬화 여부(지금은 --once 수동/호출식) — 미정, 사용자 결정
    4. E2E 산출물: work 20260818_0113_buildjob… 는 submitted 로 남아 있다 — 검증(verify)
       은 마스터의 판단 영역이라 손대지 않았다
