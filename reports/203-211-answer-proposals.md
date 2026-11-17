# #211 기대 문서 제안 — 사용자 확정 전

원본은 `203-211-search-snapshot.jsonl`, 후보 ID와 연결 키는 `203-211-candidates.json`이다.
아래는 현재 코드·문서를 대조한 **현재 검색 재측정용 제안**이다. 과거 검색 당시의 문서 존재·내용까지 증명하지 않는다.
반환 상위 결과나 후속 구현 완료만으로 정답을 확정하지 않았다. 사용자 확정 전에는 채점하지 않는다.
로컬 에이전트 candidate_audit가 별도 경로 목록→본문 조회로 소스·문서를 대조했고,
첫5건(Q02/Q05/Q10/Q21/Q23)은 지휘자가 소스와 문서 본문을 추가 대조했다.
조사 명령은 rc0, 실행 테스트·운영 DB 측정 0.
2026-11-17 사용자 「맞는 것 같아!」로 직전 표의 Q02/Q05/Q10/Q21/Q23을 현재 재측정용 정답으로 확인했다.
확정값과 원문 답은 candidates.json의 expected/confirmed/confirmation에 기록했다.
이후 Q06은 사용자 의도 「쿨다운 중인데 계속 리뷰가 실패했다고 증가하는 이슈로 보였어」를 확인하고
소스·문서를 추가 대조하여 현재 재측정용 정답으로 기록했다.
이후 Q03/Q04/Q12에 사용자 「응 아마 레드마인에 코멘트나 플랜 섹션, 아니면  작업 레포트도 있을꺼야!」로
구체 의도를 확인하고 Redmine/리포트를 추가 대조했다.
이후 Q09/Q13/Q17/Q18/Q22를 당시 요청·찾아야 했던 것·제안 문서·근거(Redmine/커밋/소스 줄)로 나눠 제시했고
사용자 「응 다 맞는 것 같아!」로 확인했다.
이후 Q07/Q25/Q26/Q27/Q28(Q07은 parse.md, Q26은 batch/run.md 보강)을 같은 형식으로 제시했고
사용자 「응 다 맞아!」로 확인했다.
이후 사용자 지시 「최근 레드마인 작업들은 아마 작업 레포트도 있을꺼야 거기 먼저 찾아봐」로 Q01/Q08/Q15/Q16/Q20을
작업 리포트(research/837-fix-plan·136·137·141·143)와 커밋(a4517ab)으로 다시 대조해 Q15·Q16·Q20 기대 문서를 보강했다
(Q16에 맡는 문서가 없다고 한 앞선 제시는 경로 오인으로 틀렸다 — context_synth/issue_review.md 존재).
사용자 「상위 5개만 나와도 작업에 사용하니까 맞아」로 확인했다 — 기대 문서 중 하나라도 상위5면 작업에 쓰인다는
사용자 기준이며 bench_kr의 hit 정의(기대 문서 중 하나)와 같다. 현재 확정24/30이었다.
마지막 Q11/Q14/Q19/Q24/Q29/Q30도 리포트(research ssh-daemon·140·174·190·196)와 #863 플랜 노트로 대조해 제시했고,
평가 제외 대신 상위5 작업 사용 기준으로 실제 작업에 쓰인 문서를 정답으로 잡았다. 사용자 「응 다 맞아!」 → 확정30/30.

추가 기록 근거:
- Q03: #843 2026-10-30T07:50:48Z 노트, 커밋0941944, setup-host→C:\\trunk\\AXCluster 클론·배달·check 실증.
  리포트130의 사건은 원본 사용자 요청(보드교체·E드라이브SSD제거)과 직접 일치한다.
- Q04: #844 2026-10-30T09:31:25Z 마감노트, f3e3d96, review_runner.agy_only(workdir)·pinned_worktree 재사용,
  라이브git status보존을 3회 관측했다는 기록. 현재코드의 커밋리뷰 빈폴더/범위리뷰 고정트리 차이는 별도로 보존한다.
- Q12: #861 T4~T6 및 2026-10-31T12:01:50Z 사용자 결정 노트의 영구home-guides명령,
  12:12:17Z 노트의 bbd0110·백업·sha256되읽기와 종결노트의 4대정본일치. 범용doc_sync로 대체하지 않는다.
이는 기존 실행 기록의 대조이며 이 세션에서 워커 설치·격리 실증·홈문서 동기화를 다시 실행한 것은 아니다.

## 두 번째 제시의 명확성 부족 — 2026-11-17

Q01/Q03/Q04/Q06/Q08/Q12/Q15/Q16의 축약 의도·모듈명 표에 사용자:
「맞는것 같은데 이건 명확하지 않네」. 명확한 확인으로 취급하지 않았고 이8건은 미확정 유지한다.
모듈명이 관련되어 보이는 것과 요구에 답하는 정답 문서라는 것은 다르다.
이후 확인은 실제 요청·LLM 질의·찾아야 하는 구체 행동·소스 책임을 구분하여 제시한다.
사용자에게는 원래 의도의 일치 여부를 확인받고, 코드·문서의 정확한 대응은 지휘자가 근거로 검증한다.

Q06의 구체 기준(#847 본문 재조회): 쿨다운 중 호출 전 건너뛴 리뷰를 시도 횟수 소비 없이 다음 회차로 넘기는가.
단순히 「리뷰 실패·재시도 정책」 전반이 아니다. 기대 문서 review_queue.md의 대응 근거는
review_queue.py:102 classify, :114 model cooldown→QUOTA, :130 시도 미소비,
:329 finish, :361 시도 복원이다. 쿨다운 해제 로그까지의 요구 전체는 관련 러너와 추가 대조가 필요하다.
사용자 의도 확인 뒤 지휘자가 실제 claim→finish를 읽어 확인한 차이:
claim은 attempts를1 올리지만 finish가 QUOTA로 판정하면1을 되돌린다. 문서도 QUOTA의 attempts 미소비를 설명한다.
반면 history에는 실패 이력(result=failed)이 남는다. 따라서 「모든 실패 표시가 증가하지 않는다」로 확대하지 않는다.
Q08의 #373 본문은 원격추적 캐시 조사도 포함하므로 현재 「요청자 로컬 브랜치 정리」만으로
당시 요구 전체의 정답이라고 단정하지 않는다. 최종 변경 범위는 노트까지 대조해야 한다.

| ID | 의도 요약 | 기대 문서 제안 | 소스 근거 | 한계 |
|---|---|---|---|---|
| Q01 | 검색 로그 웹UI의 원문·요청·결과 추적 | master/webui/rag_logs.md · master/context_search/search_log.md | rag_logs.py:129,154,162,184 · search_log.py의 _snapshot/log_search/list_entries | 현재 문서는 후속 #855 확장 포함 |
| Q02 | 문서 최신화 plan/draft/apply 진입 | master/doc_sync/__main__.md | master/doc_sync/__main__.py:51,78 | 원문은 앞 대화에 의존하는 「응 스킬 연결부터 진행해」 |
| Q03 | 신규 워커 경로 이전·레포 초기화 | master/client/setup_host.md · client/init/bootstrap.md | setup_host.py:115,137,141,161 · bootstrap.py:85 | 당시 요구로 추가한 모듈, 과거 미반환을 오답으로 단정 금지 |
| Q04 | 리뷰 실행 디렉터리 격리 | master/context_synth/review_runner.md · master/context_synth/pinned_tree.md | review_runner.py:641,647,654,1061 | 현재 커밋 리뷰=빈 임시 디렉터리, 범위 리뷰=고정 worktree |
| Q05 | agy 한도 감지·쿨다운 | master/agy_models.md | master/agy_models.py:130,136,140,149 | 현재 재측정용 |
| Q06 | 리뷰 재시도·포기 상한 | master/context_synth/review_queue.md | review_queue.py:102,114,130,329,355,361,367 | 현재 구현에는 후속 #847 포함 |
| Q07 | Python 온톨로지 합성 프롬프트·발췌 | master/ontology/prompt.md · master/ontology/contexts.md | prompt.py:236,242,257,283 · contexts.py:315,378,400 | 온톨로지 데이터 추가 여부와 다른 합성 코드 질의 |
| Q08 | 분산 마감 뒤 요청자 브랜치 정리 | master/work/review.md | review.py:709,1348 | 현 구현은 도달 확인 뒤 update-ref -d, 질의의 branch -d와 차이 |
| Q09 | Redmine 본문 플랜·태스크 상태 갱신 | master/plan_tools.md · master/plan_block.md | plan_tools.py:145,276,309 | 당시 신규 구현, 현재 모듈로 과거 미반환 채점 금지 |
| Q10 | 이력 자유 검색의 단어 순서 무관 매칭 | master/context_synth/history_harvest.md | history_harvest.py:614,639 | 현재 코드 공백단어 AND, 원문은 T6 앞 대화에 의존 |
| Q11 | 옛 워커 상주 폐기 계약 | client/init/residency.md · master/client/bundle.md | residency.py:77,82,241,284 · bundle.py:1080,1143,2240 | 당시 전수 조사 대상 전체는 현재 코드로 복원 불가 |
| Q12 | 워커 홈 CLAUDE/AGENTS 동기화 | master/client/home_guides.md | home_guides.py:90,191,236,258 · client/__main__.py:1020 | 당시 요구로 추가한 모듈 |
| Q13 | 플랜 전이 거절·저널 집계 | master/plan_tools.md · master/plan_metrics.md | plan_tools.py:54,289 · plan_metrics.py:452,466 | plan_events 문서는 별도 미대조 |
| Q14 | 마운트 전환·폐기 페이로드 정리 | master/projects/logic.md · master/client/bundle.md | logic.py:178,189,219,390 · bundle.py:1080,1143,2240 | 질의의 build_step 실컴파일까지 완전한 정답임은 미확인 |
| Q21 | 실행 서비스 코드의 최신 여부 | master/service_freshness.md | service_freshness.py:501~536 | 기동 baseline/current 내용 해시 대조 |
| Q23 | BC-250 종료 전 점검 | master/infra/bc250_shutdown.md | bc250_shutdown.py:245~278 | 실제 poweroff 검증이 아니라 해당 책임 모듈 대조만 |

## 나머지 후보 조사(bench_design, 사용자 미확정)

| ID | 의도 요약 | 현재 재측정 기대 문서 제안 | 소스 근거 | 한계 |
|---|---|---|---|---|
| Q15 | 커밋 범위 리뷰·Redmine 결과 연결 | master/context_synth/issue_track.md · master/context_synth/issue_link.md · master/context_synth/issue_progress.md | issue_flow.py:583 · issue_track.py:312 · issue_link.py:87,154 | 당시 신규 연결 기능이어서 과거 미반환 오답 판정 금지 |
| Q16 | 일감 잠금·보류·취소·마감 | master/issue_lock.md · master/issue_flow.md | issue_lock.py:158,221,243 · issue_flow.py:806 | 질의의 높음리뷰 완료관문은 이후 계약 변경됨 |
| Q17 | 재기동 전 미공지 라운드 복구 | master/task_queue/logic.md · master/task_queue/logic_cleanup.md | logic.py:552 · logic_cleanup.py:26,34 | #891 수정 전후 구분 |
| Q18 | 스킬 reference/scripts 배달·해시 대조 | master/client/bundle.md | bundle.py:1712,1729,2093 | 현재는 바로 아래 파일 대상, 임의 깊이 재귀 아님 |
| Q19 | 스킬·훅·Codex·타이머 의존 전반 | 정답 지정 보류. work/followup·client/bundle은 부분 후보 | bundle.py:1578,1654 · followup.py 존재 | 분석 보고서 전체 의도라 코드1~3문서로 한정하면 축소. 미판정 권고 |
| Q20 | 운영main과 일감 worktree 분리 | master/issue_flow.md | issue_flow.py:297,444,491,607 | 당시 #905 설계는 이후 #906·#907에서 정정 |
| Q22 | 마감 후 재기동·인수인계·배달 | master/issue_wrapup.md | issue_wrapup.py:128,145 · _deliver:73 · _freshness:91 · _restart:96 | 당시 새 기능 도입 전 |
| Q24 | 프로젝트 등록 해제·트윈 폐기 | 정답 지정 보류. projects/logic은 참고일 뿐 삭제 본체 아님 | projects/logic.py:67은 등록 · 리포트174의 전용명령 부재와 직접정리 승인 | 기능 부재·수동승인 경로 사례. unregister 구현이 있다고 가정 금지 |
| Q25 | abort 지시→취소·원격 중단 | master/work/runner.md · master/task_queue/logic_claim.md · master/task_queue/logic_lifecycle.md | runner.py:1339,1378 · logic_claim.py:280,290 · logic_lifecycle.py:424 | #344 이전/현재 구분 |
| Q26 | work신호→레시피 합성 | master/context_synth/signals.md · master/context_synth/recipes_synthesizer.md | signals.py:74,112 · recipes_synthesizer.py:573 | 배치 등록 본체는 이번 조사 미대조라 전체 정답 확정 아님 |
| Q27 | relay CLI 한도 수집·표시 | master/relay/quota.md · master/relay/agents.md · master/relay/console.md | quota.py:44,73,125 · agents.py:184,368 · console.py:82,132 | 토큰으로 잔여율 추정 아님, 당시 #368 추가 전후 구분 |
| Q28 | Gemini 캐시·all 중복·프로젝트 귀속 | master/work/usage_dashboard.md · master/work/session_usage.md | usage_dashboard.py:203,241,413,439 · session_usage.py:427,460 | #949 전후 계약 변경 |
| Q29 | 착수 전 질문·기능 분해·범위 제시 | master/plan_tools.md 우선, master/interview.md 현재 보조 후보 | plan_tools.py:145 · interview.py:208,271 | 당시 핵심은 docs/issue-spec·스킬(색인 경계 밖), 인터뷰 강제는 후속 #960. 범위 판단 필요 |
| Q30 | 느린 검사·전수/통합 병렬 실행 | master/sweep.md · master/integration_checks.md | sweep.py:70,79,107,153 · 리포트196의 integration_checks.parallel_jobs | sweep은 당시 신규 구현, 개별 느린 검사 원인은 미대조 |

둘째 조사 묶음의 문서 source_commit(약식, 당시 문서 존재 증거 아님):
issue_track=627730e, issue_link=93d7688, issue_progress=27689c1,
issue_lock=da43835, issue_flow=1cad28f, task_queue/logic=e915275,
logic_cleanup=414af3f, work/followup=7d35840, issue_wrapup=ec30077,
work/runner=dd293ff, signals=d24f45a, recipes_synthesizer=e31da00,
relay/quota=7a23fb3, agents=28819d5, console=2a01d32,
usage_dashboard=034a13c, session_usage=2ecfc1b, interview=c14a446,
sweep/integration_checks=ed60bd9. logic_claim/logic_lifecycle은 문서 존재 확인만, source_commit 미조회.

Q19·Q24는 수치 채점용 정답 미확정 유지 권고다. Q14·Q26·Q29·Q30 등의 범위 한계도 사용자 확인 시 함께 제시한다.

## 문서 시점 대조(첫 조사 묶음)

source_commit은 조회 당시 문서의 필드이며 완전한 현재 HEAD 일치를 뜻하지 않는다.

| 문서 | source_commit |
|---|---|
| master/webui/rag_logs.md · master/context_search/search_log.md | a3418199d492a5d2fabc5334d147d980f249b40d |
| master/client/setup_host.md | 1cad28fea31ccc79acee1b8e1d8799e9bb6466f3 |
| client/init/bootstrap.md | 906fe60f667a7ebd0c07f1147ecefb45766f5f82 |
| master/context_synth/review_runner.md | 2cad7090e6b73f68e68f07968faf47d1c6322c90 |
| master/context_synth/pinned_tree.md | be6654bb55ff1903575f80ef167b3da3a8bd8b0e |
| master/context_synth/review_queue.md | 8331dac0af78eb74814793eda9994edc553d803d |
| master/ontology/prompt.md · master/ontology/contexts.md | b3733827a2384cb2776c35484d554bedfe9b59f2 |
| master/work/review.md | 21370af10cddb8bedfd5c796e2687b506439d438 |
| master/plan_tools.md · master/plan_block.md | 82a7287c4c72ae971dd3e34c0e6499fba4f0c24a |
| client/init/residency.md | c521568e0da56f22a50a4ada78c153e0975a31af |
| master/client/bundle.md | e2d67f76fe4ab63a4f421c27237e6825149da446 |
| master/client/home_guides.md | 462ac9db2d16d30c1a06cab62198fd1c895c05c0 |
| master/plan_metrics.md | 6569345b5b5997456191e9b513cd482d84e33ee0 |
| master/projects/logic.md | bfa970e9c97e20112b3950715a2423ec04a781ec |
| master/doc_sync/__main__.md | 31233896b8a4740a14c799990fe7df242fa5597a |
| master/agy_models.md | da438359f45e081ab746c1f12f5d114e6a84fc8c |
| master/context_synth/history_harvest.md | b5ec5eb1beb4d9943dccc0bad0a5ab34f9c909f3 |
| master/service_freshness.md | 1cad28fea31ccc79acee1b8e1d8799e9bb6466f3 |
| master/infra/bc250_shutdown.md | 6940a94befa4c70f29e890dbe3c4ff6435786cfe |
