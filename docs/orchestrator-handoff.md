# 현재 AX 작업 인수인계

> 현재 체크포인트 한 벌이다. 11월 1일 상세 요약은 Git `c4d4fc1`, #840·#788 상세는 `013eedf`, #879~#881 상세는 `bd10209`, #883 상세는
> `2e54988`, #888(진단·처방 C·라운드 3)·#891 상세는 `0a9bef9` 의 이 파일과 리포트 135~137에 있다. 항목·진행의 정본은 Redmine이다.
> HEAD·dirty·마운트·모드는 재조회한다.

## #904 완료 체크포인트 — Claude · 2026-11-08 KST

- **#904 완료·100** — `work_completion --wait`가 영구 조회 거절(HTTP 401·403·404, 사용자 결정으로 404 포함)에서
  즉시 rc 2로 끝난다. 판정은 `ClientError.__cause__`의 HTTPError 코드(문구 파싱 안 함), 연결 실패·5xx는 재시도 유지.
  사용자 승인으로 rc 2 설명 두 곳(ax-request `reference/wait-for-completion.md`·`client_mcp.WAIT_NOTE`)도 맞췄다.
- 커밋 `38270c3` = main = origin/main. 회귀 3종 수정 전 4실패→통과, 전수 213파일 11103/11103·실패0,
  pystatic 차단0. `.43` 실경로 403 → 즉시 rc2(종전 5회 재시도 rc4). **404 실경로는 미도달**(워커 토큰 403 선행, 단위만).
- 배달: AXCluster `update` 3/3 OK·출처 HEAD(`client_mcp.py` 워커 3대 반영). 훅·참조문서는 `.33` unreal 마운트 전환 때.
- 범위 밖 관찰(#904 노트): 훅 경로 `wait_for_work`는 반대로 일시 오류 한 번에 `watch_error`로 끝난다 — 일감화 미정.

## #901 완료 체크포인트 — Claude · 2026-11-07 23:3x KST

- **#901 완료·100** — `pending_works`가 `editor_mcp`에 루트 보정 payload를 넘긴다(하위 폴더 세션 침묵 해소).
  커밋 `0cf37f7` = main = origin/main. 회귀 ⑩(훅 배치 서브프로세스) 수정 전 실패→후 통과,
  전수 213파일 11100/11100·실패0, pystatic 차단0. finish 8단계 성공·잠금 해제. 리뷰 링크 「큐에 없음 1」.
- 배달: AXCluster `update` 3/3 OK·출처 HEAD 동일(사용자 승인). 이 훅은 unreal 요청자 자산이라
  `.33` 반영은 ModularStage·NS·MotionForge 마운트 전환 때. `.2` 홈 그림자 ax-work는 check [주의](FAIL 아님).
- #899 드라이런 결함 후보를 등록: **#902**(조각 즉시 실패 표시 미저장) · **#903**(followup ⑦ 노트 무재시도) ·
  **#904**(`--wait` 403 재시도→rc4). #902·#903은 「중복 쪽 vs 그대로」 설계 결정이 먼저다. 착수는 사용자 선택.

## #899 완료 체크포인트 — Claude · 2026-11-07 23:0x KST

- 마스터 담당 **claude**로 재인수(22:44, 사용자 지시). 직전 인계 커밋 `7bf0dcb` 사용자 승인 push.
- **#899 완료·100** (분석 전용, 코드·설정·배달·서비스 변경 0). 로컬 서브 에이전트 3개(읽기 전용) 취합.
  보고서 `reports/140-899-skill-hook-codex-path-analysis.md`, 커밋 `0942b19` = main = origin/main.
  finish 8단계 성공·라운드1 해시1 등록·잠금 해제. 링크 단계 「큐에 없음 1」 — 해시별 리뷰 노트는 미도착.
- 결론: 분모 26(마스터9·요청자/워커9·워크숍8)+훅5. 훅 직접 의존은 ax-request 하나. Codex는
  4대 `hooks stable true`이나 AX 미배선(미실증). 전송/저장 창은 #891만 중복 쪽, 조각 즉시 실패
  (`logic_cleanup.py:776` 미저장)·work_completion·followup 노트는 누락 쪽.
- **보고서 §7 미결 선택지 9개는 사용자 결정 전 착수 금지.** 범위 밖: 마스터 `~/.claude.json`·
  `~/.codex/config.toml`에 ax-projects 토큰 평문 — 처리 여부 미정, 값은 어디에도 옮기지 않았다.

## #896·#900 완료 체크포인트 — Codex · 2026-11-07 21:03 KST

- **#896 완료·100**. 사용자 커밋·배포·finish 별도 승인 후 `1ecf58b` main 반영·push 완료.
  당시 `main=origin/main=1ecf58b`, `issue/896` 삭제·잠금 해제·마감 추적 라운드1 해시2개 등록.
  이후 인수인계70332d1을 승인받아 commit/push했다. 현재 상태는 아래 #900 기록을 따른다.
- **#900 완료·100**. T1~T4 완료, 사용자 승인 커밋 `e41b53e`를 main에 반영했다.
  현재 `main=origin/main=e41b53e`. issue/900 로컬 브랜치 삭제·마감추적 라운드1 등록·잠금 해제 성공.
  `/home/sim/ax-900-local`은 같은 커밋의 격리 작업본으로 보존. 자동 삭제·재적용하지 않는다.
  이번 인수인계 갱신 전 트리는 깨끗했으며, 갱신 뒤 이 문서만 미커밋이다. 커밋 승인은 별도.
- **배포 순서 오류와 정정**: main 반영 전에 issue/900 HEAD를 배달하고 완료라고 보고했다.
  사용자 지적 뒤 승인받아 finish 미리보기→main 반영→main 기준 update→드라이런 순서로 다시 처리했다.
  이전 작업 브랜치 배달을 정식 main 배포로 설명하지 않는다. 이후에도 main 반영을 먼저 대조한다.
- **최종 배포**: e41b53e main 기준 AXCluster `.43`·`.2`·`.33` 배달·검사3/3, rc0.
  `.2` 기존 홈 중복 스킬1 주의 유지. 배달은 관리 자산 일치이며 실제 파견 성공과 구분한다.
- **배포 후 드라이런**: main에서 `master/test_planner.py` 67/67·rc0.
  정상 생성·요약/인덱스/등록/아카이브, 질문 거절·실패 원문/리뷰 보존·재시도·중복스킵 검증.
  임시 데이터·LLM/등록 대역 사용이며 실제 상용 생성 재실행은 아니다.
  ax-batch는 oneshot으로 다음 발동이 새 코드다. 재기동하지 않았고 timer active/waiting 확인.
  직전 service 21:01:54 KST·Result success. #900으로 다른 상주 서비스는 재기동하지 않았다.
- **#896 검증**: 관련 회귀144/144·issue_infra69/69·정적 차단0·독립 검토 추가지적0.
  공식 통합의 기존 `test_source_scope` 28/32 실패는 기준에서도 동일. 사용자 결정으로
  이번 변경 밖 테스트 실패는 더 조사하거나 #896 차단 근거로 삼지 않았다.
  임시 Git 테스트 조건을 실제 운영 플로우의 결함으로 설명하지 않는다.
- **실제 마감에서 새 경로 확인**: `push → switch -C main 1ecf58b → delete_branch →
  register → link → release → close → redmine`, ok·registered·lock_released·closed 모두 true.
  옛 main을 거치지 않는다. 같은 로컬 repo의 다른 main worktree 점유·조회 실패는 push 전 거절.
- **#896 당시 배포**: AXCluster `.43`·`.2`·`.33` 3/3 OK, 출처 `1ecf58b`. 기본 샌드박스 접근 실패 뒤
  동일 기존 명령만 담은 승인 스크립트로 재실행해 rc0. `.2` 기존 홈 중복 스킬1 주의 유지.
  `ax-projects` 재기동 **16:41:42 KST**, active/running 확인. 다른 서비스 재기동 없음.
- **PC 타입 명세**: `9166654`도 함께 main 반영. 홈 CLAUDE/AGENTS의 정본
  `machines/sim-desktop.md`·`machines/sim-desktop-agents.md`에 마스터/보조 워커/사용자 PC 명시.
  `.33` 사용자 트리에서 자동 리뷰를 실행한다고 추측하지 않는다. AXCluster 전용 워커 역할은 별도.
- 근거: Redmine #896 최신 노트·`reports/138-896-finish-checkout-verification.md`.
  `/home/sim/ax-896-local`의 미커밋 사본은 보존했다. 재적용하거나 자동 정리하지 않는다.
  아래 과거 상태보다 이 체크포인트와 Redmine 최신 기록을 우선한다.

## #900 — 질문 응답을 주간 플랜으로 저장한 결함

- 마일스톤 **7 - 버그/개선**, 완료·100. 사용자 「인수인계서 작성하고 900번 진행해」 뒤
  제안 플랜·인수인계 commit/push·로컬 서브 에이전트 방식 승인. 한도 중단 뒤 초기화·재개 승인.
  RAG request `21eda88ebd7f41c48d312558046178f8`로 plan_generator/planner/test_planner 및
  layer2_verify 문서를 검색·본문 읽기·현재 소스 대조했다. 매 단계 새 근거가 필요하면 RAG를
  쓰되 같은 검색을 매 명령마다 반복하지 않는다.
- **P13~P15(2026-W44) 모두 실제 개선안 대신 Gemini 위임 여부를 묻는 문장을 저장**했다.
  `ax-gemini` 대화형 지침이 응답에 인용돼 있으나 실제 유입 경로는 미확정.
  생성기의 두 경로가 빈 응답만 제외하고 raw 본문을 저장·성공 집계하는 사실은 확인했다.
- 실제 호출: `planner.run_weekly_plans → plan_generator.generate_improvement_plans →
  review_gen.commercial_chat → layer2_verify.WHY_BACKENDS(codex→agy→claude)`.
  생성 체인과 교차 계열 리뷰 체인을 혼동하지 않는다. 옛 합성 문서의 체인 설명만 믿지 않는다.
- **P13 원본3건은 R218-1~3 applied(#881)**. 현재 성공 git stdout 분리·Redmine 예외 변환·
  이벤트 직렬화 예외 처리가 남아 있다. **P14 Path import3건도 이미 제거**. P15는 타입 표기 권고.
  이미 해소된 지적을 새 구현 작업으로 반복하지 않는다.
- T1/T2 완료: 무인 응답 계약·필수구획/본문 구조 검사, 전체 주차 후보 검증 뒤에만 공개.
  실패 시 JSONL 원문 진단만 남기고 정상 요약·등록·아카이브를 보류해 재시도 가능.
  완료 주수도 summary 있는 주차만 집계. 수정 대상은 plan_generator/planner/test_planner3파일.
  스킬·공용 LLM 체인 변경 없음. 구조 검사는 의미 전체 판정을 보장하지 않는다.
- **검증**: planner67/67·batch59/59·정적차단0·독립검토 추가지적0. 실제 P15 원본5건으로
  Codex가 질문 없이 가이드1건 생성, 별도 `/tmp/ax-900-live-p15-xbomtqen`에 보존·본문 확인.
  사용량 issue900_validation/P15 기록. 통합은 아래 명시적 제외 범위로 통과. 운영 산출물 처리도 완료했다.
- **T3 승인 처리 완료**: P13/P14 원문보존·dismissed·되읽기 확인. P15는 같은 번호·경로·
  원본리뷰4개·pending/open 유지, 실제 가이드로 재생성했다. 타입 힌트 코드는 바꾸지 않았다.
  기존 본문·요약·인덱스는 실제 W44의 _before_issue900.q9wSqU에 보존. 요약 유효1·무효2,
  인덱스 W44=1 확인. 원본 리뷰는 삭제·이동하지 않았다. 상세 리포트139.
- 통합은 기존 source_scope 1건을 사용자 결정으로 제외. 98개 통과 후 handoff_size가182줄로
  실패해 중단. 승인 후 축약·형식7/7, 잔여88/88 통과. 합계187/187(기존1개 제외).
  로그 /tmp/ax-900-integration.log 및 /tmp/ax-900-integration-resume.log.
- 자동 리뷰 조회 시점: 최신 R251(해시)·R252(#890 종합), 각각 높음0·중간6·낮음10이며 실질 중복.
  경로 지적은 resolve()·마스터 스킬 링크 계약을 고려해야 한다. 적용·기각 상태는 바꾸지 않았다.
  #896 새 리뷰 결과는 당시 목록에 없었다. 재조회 대상이며 완료를 추정하지 않는다.
- **#899**: 11-07 Claude가 분석 완료·마감(위 체크포인트·리포트140).

## 이어받을 운영 상태

- 마스터 담당 기록 claude(11-07 22:44), 워커 전역 codex. 마운트 AXCluster. 자동 변경하지 않는다.
- #888·#889·#890·#891 완료. 상세 리포트135~137·Redmine·Git 0a9bef9 인계서.
- #889 finish 등록 성공 시 완료100, 리뷰는 닫힌 일감에 노트만 추가. 자동 재개·새 일감 없음.
  활성·보류 잠금은 손 닫기 거절. 실제 .33 세션 호출은 미실증, 서버 경로 드라이런은 통과.
- #891 notice_pending·기동 복구 재공지의 SIGTERM 드라이런 통과. 실제 운영 종결1회 미확인.
  수신 뒤 죽으면 중복 가능(유실보다 중복 선택). R248-1 비정수 메타 int() 오류 별건 여부 미결.
- #890 스킬 규약은 docs/skill-authoring.md·master/test_skill_conventions.py.
  ax-handoff/ax-mode 직접 호출은 scripts/conductor.py. .33 요청자 번들·reference 실사용은
  게임 프로젝트 마운트 전환 때 확인. AXCluster 배달과 구분한다.
- #893 리뷰 생략목록 유실·#894 판정서식 파서·#895 테스트 경합·#897 mtime 신선도 오판·
  #898 요청자에 없는 MCP 호출: 등록, 처방·순서 미결. #896은 완료.
- #884 T7은 #889로 의미가 바뀌어 닫는 방법 사용자 결정 필요. #885는 #884까지 보류.
- 주말 기각 후보는 기준37b8fed에서 48기각·5해소·60보류, 상태 미변경. 최신 대조 전 일괄처리 금지.
  Codex108호출·입력 약8.7M 기록은 Redmine. #892 기록·비용 분석은 아이디어 버킷.
- #259 ServerTest는 등록만. 초기화·합성·배달·마운트 미실행.
- #839②·#791D·#820·#372·#855·#826(자식858은856 선행)은 상태 재조회.
- 큐/스풀 #709·#211·#650, ax-788-work, ax-review-788 반려#821, MotionForge·NS 잔재 보존.
  정식 취소는 review.cancel_work. 직접 PATCH·자동 삭제 금지.
- 서비스는 운영 체크아웃 코드로 돈다. 새 코드는 격리 worktree에서 검증한다.
  ax-projects(8103)는 MCP 서버. 관련 변경 반영 후 재기동은 별도 승인.
- 마스터 followup 수신자는 ax-followup.timer 하나, 마스터 훅 없음. 등재 wait 즉시 실행·게이트 전달.
- 유닛 RUN_BUDGET 계약은 설치본 먼저. Monitor는 줄 버퍼링 유지. plan_set_tool은 전체 목록 덮어쓰기.
- doc_sync 의존 등록 보강과 #883 중복 플랜 제목은 미처리. 변경은 사용자 결정에 따른다.

## 바로 다음 작업

1. #900은 main 반영·배포·드라이런·마감 완료다. 중복 finish·재생성·배포하지 않는다.
   Redmine 최신 노트가 최종 기록이다. 리포트139의 커밋 승인 대기 문구는 마감 전 기록이다.
2. #899·#901·#904 완료. 다음 일감(#902·#903 — 설계 결정 먼저)·리포트140 §7 선택지는 사용자 선택. 커밋·push·배달은 매번 승인.
3. #890 R251·R252와 #896 새 자동 리뷰는 최신 목록·노트로 확인. 상태 변경·재개·별건 생성은 자동으로 하지 않는다.
   #893~#898 중 #896은 끝났다. #884 닫는 방법·#885 보류·#891 낮음 별건 여부 등은 그대로 미결.
   스킬을 만들거나 고치면 `master/test_skill_conventions.py`를 돌린다.
4. 일감 작업은 `issue_start_tool` → 커밋 → `issue_finish_tool` 미리보기 → 승인 → `confirm=True`(이제 이것이 「완료」다). 커밋·운영 배달·
   재기동·유닛 설치는 각각 승인을 확인한다. 실패 시 코드·설정을 자동 수정하지 않고 보고·중단한다.
5. **문서 최신화 남은 몫**(11-04): doc_sync 등록 목록(`docs/document-registry.json`)에 issue_flow·review_runner·review_queue 등이 의존 파일로
   없다 — 보강은 사용자가 정한다. #883 본문 `## 플랜` 제목 중복도 미처리.
