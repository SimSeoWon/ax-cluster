# 현재 AX 작업 인수인계

> 2026-11-17 — Codex. 사용자 「토큰 없으니 인수인계서만 작성하자」로 #211 작업을 중단하고 이 파일만 갱신.
> #211은 마감 전이며 잠금은 그대로다. pause/cancel/finish·커밋·push·배달을 이 인계 때문에 실행하지 않는다.

## 작업 위치·실제 Git

- 운영 체크아웃 /home/sim/ax-cluster: main=origin/main=3d874011ac7e4bd41f389b159fc6bedb6e11632e.
  인계 작성 직전 clean. 이 파일 갱신으로 운영 트리에 문서 미커밋이 생긴다. 다음 issue_start 전 처리에 주의.
- #211 issue_start 응답: ok=true, repo=/home/sim/ax-cluster/.ax-issues/211,
  checkout=/home/sim/ax-cluster, branch=issue/211, already=false,
  start_rev=3d874011ac7e4bd41f389b159fc6bedb6e11632e, lock=acquired, author.family=codex.
  편집·검사·커밋은 응답 repo에서만 한다(색인 미러 AXCluster/repo는 작업 위치 아님).
- worktree HEAD=d4b69d7. 인계 직전 git status: ?? reports/203-211-ground-truth.tsv 한 개.
- 일감 커밋: 740ac72(T1 후보·원본 보존), cde8bdc(T2 소스 대조 제안),
  3d2ba8b(첫5건 확인), 26e239a(Q06 쿨다운 의도), d4b69d7(Q03/Q04/Q12 기록 대조).
  모두 로컬 issue/211에만 있다. main 반영·push·배달·서비스 재기동 없음.

## #211 승인·범위·진행

- 사용자 「211번 진행하자」, 분류 「기능 수정」, 단독(로컬 서브 에이전트) 선택.
  ax-plan 인터뷰→ax:spec→T1~T4/C1~C6/autonomy0.5 제안·등록→issue_start까지 완료.
- 주 대상은 현재 마운트되어 주로 사용한 AXCluster. 사용자 온톨로지는 별도로 추가하지 않은 상태.
  AXCluster 실사용 정답 집합·4변형 비교·개선안까지. 운영 검색 설정·가중치·온톨로지 추가는 비범위.
  ModularStage 자연확정4/30·30건 기준은 그대로 보존하며 AXCluster와 합산하지 않는다.
- Redmine 마지막 플랜: T1 완료(740ac72), T2 작업중, T3·T4 대기, C1 충족·나머지 미확인.
  T3는 T2 선행이라 아직 코드 편집·측정·테스트를 하지 않았다.
- 후보30건은 목적 표집(주제 다양화), 무작위·대표성·정책 판정 충분조건 아님.
  원본 동결127검색/122요청, #855운영확인989e3120 제외 모집단126/121,
  한글포함120검색/고유119질의. 선정30검색/30요청·원문누락0·스냅샷누락0·188문서.
  기존 hangul_only(한글+영문식별자 없음) 대상은 Q15 한 건, 나머지29는 혼합.
- 최신 사용자: 「응 아마 레드마인에 코멘트나 플랜 섹션, 아니면  작업 레포트도 있을꺼야!」.
  의도 확인을 반복해서 퀴즈처럼 묻지 말고 기존 코멘트·플랜·리포트부터 대조한다.
  단 이 답을 남은21건의 일괄 확정으로 확대하지 않았다.

## 산출물·확정 정답

전부 #211 worktree의 reports/ 안이다. 읽기 전에 rg --files로 목록→다음 별도 호출로 본문 확인.
- 203-211-search-snapshot.jsonl: 원본 user_command, ts<2026-11-16T23:25:00.
  SHA256 82ef995a0a76aeb1514db682b0ec9505c5c44a659b2b298e015b26cea8d61817.
- 203-211-candidates.json: Q01~Q30·search_id·선정근거·expected·confirmed·사용자답·소스근거.
- 203-211-answer-proposals.md: 30건 소스 대조 제안과 한계·문서 source_commit.
- 203-211-kr-search-evaluation.md: 세션 근거 리포트(203). 최종 결과는 Redmine 마감 노트.
- 203-211-ground-truth.tsv: 기존5열+candidate_id/request_id로 내보낸 미커밋30행.
  아래 검증 실패가 남아 있다. 삭제·덮어쓰기·재실행으로 실패를 숨기지 않는다.
- 현재 JSON 확정9/30: Q02(doc_sync), Q03(setup_host/bootstrap), Q04(review_runner/pinned_tree),
  Q05(agy_models), Q06(review_queue), Q10(history_harvest), Q12(home_guides),
  Q21(service_freshness), Q23(bc250_shutdown). 미확정21.
  사용자 원문과 source basis는 JSON에 보존. 첫5건 답 「맞는 것 같아!」.
  Q06 답 「쿨다운 중인데 계속 리뷰가 실패했다고 증가하는 이슈로 보였어」.
  Q03/Q04/Q12는 위 최신 「응…레드마인…레포트」 답과 #843/#844/#861로 확인.
- Q06: claim은 attempts를 올리고 finish가 cooldown→QUOTA이면 이를 되돌린다.
  history.failed 이력은 별도로 남으므로 모든 실패 표시가 증가하지 않는다고 설명하면 틀림.
- #843 노트 2026-10-30T07:50:48Z(0941944), #844 09:31:25Z(f3e3d96),
  #861 10-31T12:01:50Z 사용자결정·12:12:17Z(bbd0110)·T4~T6/종결노트가 이번3건 근거.
- Redmine 최신 T2 노트는 확정6/30까지다. 그 뒤 JSON9건(d4b69d7)은 아직 노트에 추가하지 않았다.

## 방금 검증 실패 — 수정하지 않고 멈춤

- TSV 생성 자체 rc0. 이어 awk 검증 rc1:
  rows=29 confirmed=9 pending=20 bad_columns=0 (기대30/9/21).
- 원인 조사만 수행: Q01 실제 질의가 "#837 RAG 검색 로그 웹UI …"로 시작한다.
  awk !/^#/가 이 데이터행을 주석으로 뺐다. NR>1로 세니 data_rows=30 confirmed=9.
  기존 master/bench_kr.py:35~37도 ln.startswith("#")를 전부 건너뛰므로
  Q01을 나중에 confirmed=y로 해도 누락되는 계약이다. 현재 확정9건 자체는 보존되어 있다.
- 아직 로더·질의·검사식을 수정하지 않았다. 사용자에게 실패를 알린 뒤 인계 작성 지시가 왔다.
  재개 시 이 실패의 처리(원문 #질의 보존+헤더 구분을 T3에서 수정할지)를 먼저 결정한다.
  실패 후 추가 코드·설정 수정·테스트·커밋은 하지 않았다.

## 마지막 기록 대조 결과 — 아직 산출물에 반영 전

로컬 에이전트 candidate_audit/bench_design의 추가 조사 최종 응답을 이 인계로 보존한다.
둘 다 읽기 전용·명령rc0·파일쓰기/검사/운영쓰기0. 원문 요구→기록→현재소스 순으로 대조했다.
아래는 사용자 미확정 제안이며 기존 answer-proposals의 초기 정답을 그대로 쓰지 말 것.
- Q01/#837: reports/research/2026-10-20-837-fix-plan.md에서 동일질의로 매핑.
  노트 10-20T15:06:24Z/a3418199. UI+search_log 외 채널순위 본체 domain_index.md 추가 필요.
- Q07/#850: 10-30T12:51:59Z 결정(확장자별파싱·발췌/kind별UE규칙), b373382.
  ontology/prompt·contexts 외 ontology/parse.md도 기대 문서(최장 클래스 접두사 파싱).
- Q08/#373: 10-18T13:21:41Z 노트가 범위를 로컬base정리로 재정의.
  10-30T15:33:49Z 사용자선택A, a4517ab. 정답 work/review.md, cleanup은 보조.
- Q09/#826: reports/132-826-plan-block-phase-a.md와 노트10-31T06:39:27Z.
  79a3c0d·4cab2b1·2552ff4, plan_block/plan_tools 제안 근거 충분.
- Q11/#860: 전수조사 요구. residency/bundle/runner는 부분 근거이며 하나라도 hit면 충분하다는 판정 금지.
  삭제된 worker_daemon이 당시 반환된 것도 조사에 유효할 수 있다.
- Q13/#864: 거절기록+읽기전용지표+SDD기준선, e7d0600, plan_tools/plan_metrics 근거 충분.
- Q14/#863: 실컴파일·SSH파견·마운트잔재 실증의 복합요구.
  plan_build+projects/logic+client/bundle(추가 runner) 필요, 앞 제안 logic/bundle만으로 불완전.
- Q15/#879(#826 PhaseD): 11-03T14:53:41Z/bcdd290.
  issue_flow+issue_track+issue_progress 현재 제안, 당시 구현은 range큐/review_runner임을 구분.
- Q16/#883: 잠금·보류·취소는 issue_lock/issue_flow.
  당시 높은리뷰 완료관문은 issue_review도 필요하고 이후 #884/#889로 계약 변경.
- Q17/#891: 11-07T05:03:58Z·05:04:05Z/265a639, task_queue/logic+logic_cleanup 근거 충분.
- Q18/#890: 11-07T06:00:05Z/e2d67f7, client/bundle의 reference/scripts 배달·해시 대상.
- Q19/#899: 분석전용·보고서140이 산출물(0942b195a275).
  코드문서1~3개로 전체정답을 강제하지 말고 미판정/평가범위밖 권고.
- Q20/#905→#906/#907: 현재 issue_flow 정답, 보고서141/143. 최초 경로설계를 정본으로 쓰지 않음.
- Q22/#921: 보고서154가 축약사용자답을 이슈로 연결. aea3f94, issue_wrapup 정답 근거.
- Q24/#936: 보고서174·본문의 unregister명령부재·Registry.load/save 수동승인.
  projects/logic을 삭제기능 정답으로 삼으면 틀림. 기능부재/운영사례 분리 권고.
- Q25/#344: 5782dd2·c66e58b·c7a9835/a16e67c. runner+logic_claim+logic_lifecycle.
- Q26/#383: 플랜11-14T06:33:55Z, merged당1신호·토요일22시합성·아카이브시각기준.
  signals+recipes_synthesizer+batch/run.md(배치연결)로 보강, 5e10121/d24f45a/e31da00.
- Q27/#368: 보고서184, 최종main 33124e7/5805b74/902f4e9/05f8f48(리베이스전해시쓰지않음).
  relay/quota+agents+console 제안 유지.
- Q28/#949: 8c86c29/034a13c/aadb77b, usage_dashboard+session_usage 제안 유지.
- Q29/#939: 보고서190·T2 docs/issue-spec(9baaf90), T3 ax-plan/distribute(faba5f7).
  interview.md는 후속#960이라 정답에서 제외. plan_tools는 부속경고만. 코드검색 범위밖/부분근거 권고.
- Q30/#965: 원문 "965번 조사만 진행해줘". 새 sweep보다 당시 느린검사 원인조사가 핵심.
  보고서196·사전노트11-15T06:31:30Z·재검증10:03:22Z.
  test_client_bundle/test_review/test_pystatic(+test_followup)로 제안 변경, sweep만을 정답으로 강제 금지.
- 기록으로 의도가 명확하다는 것과 코드검색 범위에 온전한 정답이 있다는 것은 다르다.

## T3 설계 주의·기타 인계

- 기존 suppress_logging은 벡터 중복만 억제. ContextSearch.search finally는 log_search를 무조건 호출.
  ContextIndex/Bm25Index 생성자도 컬렉션/테이블 생성·commit 가능. 운영DB에 벤치 직접 실행 금지.
  고정 복사색인·평가로그 분리의 일관된 계약을 먼저 정해야 한다(복사 절차 미확정).
- baseline limit15는 pool45, gated는BM25 15. 차이 자체를 버그라 단정하지 말고 조건·MRR@15 명시.
  KR_ROUTING 전역복원·연결close·동일세대/자료·확정0건 미판정 처리가 필요하다.
- 인계 전 지휘조회: 마지막 담당기록 claude(11-14), 워커 codex(state). 변경하지 않았다.
- #855 잔여 issue_lock 실관측은 확인: search_id 8c548bc7a6094f6996f9fdc6267eff25,
  issue_id=211, issue_id_source=issue_lock, purpose보존. #855 자체 기록은 미갱신.
- 색인기 30분timeout·#971개명 합성 관측, #964/#966 배치·agy처리량, #383실합성, relay한도연계는
  이전 인계의 잔여 관측이며 이번에는 후속 완료 판정하지 않았다. 운영 상태는 재조회 필요.
- 미처리리뷰는 각Redmine노트. #929/#930/#931/#934/#829/#942 등 이전 미결을 임의 처리하지 않음.
- 다른 일감 선택·워커모드변경·⑦전진·finalize·자동로드문서변경 승인은 없다.
- 세션: ~/.codex/sessions/2026/11/16/rollout-2026-11-16T23-38-59-01a1e4cc-0b40-7b63-9498-c818714aac0f.jsonl.
