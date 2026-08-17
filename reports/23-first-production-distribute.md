# 23 — 분산 작업 첫 실전 (실 게임 코드) + durable_base 이음새 수정

사용자 지시 "분산 작업 실전 한 번 돌려보자". 대상은 #169 태깅 리포트에서 골랐고,
**pull 데몬 체제의 첫 실전 완주**가 됐다: 등록 → 데몬 자가 claim → 추론 → collect →
통합(빌드 게이트) → durable push까지 사람 손 없이 (등록·통합 지시만 사람).

## §1 대상 선정에서 배운 것 — 레거시 모듈 함정

처음 합의한 `AlphaCharAssetLoader_Event` 는 **실물 확인에서 탈락**: 저장소 CLAUDE.md 에
`Source/Project_Alpha` 는 *"Legacy reference only — .uproject 에 없음, 빌드하지 말 것"*.
[중요] **태깅 리포트(#169)의 후보 85건에는 레거시 모듈 것이 섞여 있다** — 온톨로지가
Source/ 전체를 색인하기 때문. 실증 테스트가 성립하려면 실행되는 모듈이어야 하므로
`UMissionTaskExecutor`(실 모듈 미션 핵심, 후보 4건)로 교체. 리포트를 볼 때 이 축을
같이 봐야 한다 — 개선 여지(모듈 표기)로 남긴다.

## §2 실행 기록 (work 20260818_0329_123_invariant_4_9dc507bd)

    plan       조각 1 · 물결 1 (h 87 + cpp 264줄). instruction 에 invariant 4건의 태깅
               사양 기입 (기능 변화 0 · 카테고리 LogMissionExecutor · CVar
               ms.Mission.LogExecutor 기본 꺼짐 · 정상 경로 틱 무로그)
    register   골조 opus 생성 — 동결 계약에 새 로그 카테고리 선언 포함, CVar 골조 완비.
               [주의] **골조 빌드 게이트 미확인** — CLI 가 gate 를 배선하지 않았고,
               이번 골조는 수정 작업용 **부분 골조**(기존 include 생략 명시)라 단독
               빌드 자체가 성립하지 않는다. 신규-파일 골조용 장치 — 수정 작업의 검증은
               통합 단계의 조각별 UE5 빌드가 맡는다. 미확인은 미확인으로 보고했다
    claim      [중요] 등록 직후 .43 데몬이 자가 claim — **등록↔publish 경합이 실전에서
               실제 발생**했고(실체화 1/5 실패) §9(리포트 21) 의 재시도 가드가 15초
               후 살렸다. 가드의 첫 실전 구조 (예측→구현→실측 순서가 맞았다)
    추론        .43 claude 174s · $0.78 → result.json (submit 없음)
    collect    회수 1 · 층1 통과 · 파일 2 (11,237자)
    검수        diff 눈검사: h +5/-0 · cpp +39/-2 (그 -2 는 지시된 기존 로그 승격).
               invariant 4건 전부, 한국어 주석·[DOC]·enum 이름 출력 등 관례 유지
    통합 1차    격리 트리 @ 기준커밋 · UE5 빌드 194s PASS · 커밋 — [중요] **push ff 거부**
    통합 2차    (§3 수정 후) durable 팁 위에 재적용 · 빌드 67s(증분) PASS ·
               **push 완료: task/88d84bfe ← 4cd229f3** · 태스크 submitted
    층3         RunTests fail-open (에디터 exit -1 · 자동화 테스트 0개 — 알려진 구멍,
               사람이 본다)

## §3 durable_base — #185 와 integrate 의 이음새 버그 (실전이 잡음)

durable `task/<id>` 는 등록 시점에 **매니페스트 커밋을 이미 얹고 있다**(#185). 통합자는
기준 커밋 위에 커밋했으므로 durable 팁과 **형제 분기** — ff push 가 구조적으로 거부된다.
이전 셀프테스트들이 못 본 이유: selftest 경로는 durable 을 다른 방식으로 세웠다.

수정 (`integrate.durable_base`): durable 팁이 ① 기준 커밋의 자손이고 ② 기준→팁 diff 가
대상 파일과 **무접촉**이면(매니페스트 커밋뿐) 팁 위에 짓는다 — ff 성립. 조건이 안 맞으면
기준 유지 + 시끄럽게(기존 fail-closed 그대로, push 는 사람이 판단). [주의] 동결 대조
원본(baseline)은 계속 **추론 기준 커밋** — 응답이 근거한 소스와 대조해야 의미가 있다.
테스트 5건 신규 (전체 3463 — test_projects 1건은 이 실 work 가 열려 있어 전환 가드가
옳게 막는 것: 결함이 아니라 상태).

## §4 남은 것 — 사람의 자리

    1. [중요] **main 병합은 사용자 몫**: gitea 의 `task/88d84bfe`(4cd229f3 — 매니페스트
       커밋 + 태깅 커밋)를 검토해 main 에 머지. [주의] 매니페스트 커밋(.ax/tasks/...)이
       히스토리에 함께 온다 — #185 판정의 부활 조건("소스트리 가독성을 방해하면 scp 복귀")
       을 볼 첫 실물이다
    2. 머지 후: `log-tags set` 으로 사이드카 확정 기입 (tag=LogMissionExecutor ·
       cvar=ms.Mission.LogExecutor · invariant 4건) — 저작 방향 (b) 의 "구현 뒤 기입"
    3. 머지 후: `cleanup remote --apply` 가 durable 을 자동 삭제 (병합 도달 가능해지므로)
    4. work 종결(verify) — 머지 확인 후
    5. 개선 여지 기록: 태깅 리포트에 모듈(빌드 대상 여부) 표기 · distribute CLI 의
       골조 게이트 배선(신규 파일 작업용)

비용: 골조 opus 1회 + 추론 $0.78 + 빌드 2회(194s+67s). 사람 개입: 대상 합의 · 계획 확인 ·
register/integrate 지시 · (남은) 머지 검토.
