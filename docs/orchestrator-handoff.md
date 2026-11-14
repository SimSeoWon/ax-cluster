# 현재 AX 작업 인수인계

> 2026-11-14 — #947(서비스 신선도 기동 기록 파일 사본 · 판정 불가 사유 구분) 마감 완료(1회차 main `24c65a5` · 2회차 `3e46d78`, Claude). 직전 #946은 main `851f60e`로 마감·배달 완료.
> 다음 일감은 사용자 선택을 기다린다. 항목·진행은 Redmine, 지난 상세는 Git 이력·리포트로 확인한다.

## 직전 마감 — #947 완료

- 발단: #946 wrapup 의 `ax-projects` 「의존 판정 불가(journalctl rc=1)」 → rc=1 은 `--grep` 무매치(기록 부재). 저널 4.0G 상한·가장 오래된 줄 10:10:02 > 기동 10:09:42. 원인은 snap `nordvpnd` AppArmor DENIED audit(10분 91,535건). 🔴 **사용자 결정: 마스터에서 NordVPN 제거**(`snap remove --purge nordvpn`, 크롬 확장도 사용자가 제거) · `ax-projects` 재기동(19:35:55, 승인).
- 승인: 「ax-projects 재기동하고 일감도 등록해줘」 → #947 등록 · 「947번 진행해줘」 · 작업 방식 「이 세션이 직접」. 작성 계열 `['claude']`.
- 커밋 `b9ec8e8`(T1·T2: `record_startup` 이 `~/ax-state/service-code/<unit>.json` 에도 원자적 기록(`AX_SERVICE_CODE_DIR`), 실패해도 기동 계속 · `_record` 파일 우선·저널 폴백 · 사유 「기록 없음」/「저널 회전 가능(시각)」/「읽지 못했다 rc+stderr」) · `24c65a5`(리포트 `reports/186-947-service-code-record-file.md`).
- 검사: `test_service_freshness` 통과 81 · `test_client_bundle` 661/661 · `test_issue_wrapup` 39/39 · `test_service_restart` 75 · 공식 통합 `Ran 199 tests / OK` · pyflakes 0.
- `issue_finish(confirm=True)` 전 단계 완료 · 「완료」·100. 리뷰 연결 「이음 0 · 큐에 없음 2」.
- wrapup(1회차): `ax-task-queue`(19:48:17)·`ax-projects`(19:48:22) 의존 변경 재기동 → 기록 파일 생성 · 저널 grep 없이 파일로 판정 확인.
- 2회차(T4): `ax-broker` 를 사용자 승인으로 재기동(19:50:09)했더니 `ProtectHome=read-only` 로 파일 쓰기 실패(EROFS — fail-soft 로 저널 폴백). 사용자 「ⓐ로 진행해줘」 → `master/systemd/ax-broker.service` 에 `ReadWritePaths=-/home/sim/ax-state/service-code` 한 줄 · 유닛 샌드박스 회귀 검사(`test_units_can_write_record_947`, 수정 전 유닛이면 실패) · `test_service_freshness` 84 · 공식 통합 OK. 커밋 `3e46d78`.
- 마감 뒤 설치: pkexec 로 `/etc/systemd/system/ax-broker.service` 반영(저장소와 동일 확인) · daemon-reload · broker 재기동 19:56:39 → `ax-broker.json` 생성. **세 서비스 모두 파일로 판정, 저널 grep 0회, 판정 깨끗.**
- [주의] 실측: `ax-projects` 는 `ProtectSystem=strict` + `ProtectHome=false` 에서 `ax-state` 쓰기 허용 없이도 파일을 썼다 — strict 가 왜 막지 않았는지는 설명 못 했다(검사 기준은 실측대로 ProtectHome 기준).
- 리뷰 연결 「큐에 없음」(1회차 2 · 2회차 1). 이 커밋 직후 배달.

## 직전 마감 — #946 완료

- 승인: 「946번 진행해줘」 → 플랜 질문에 커밋 양식 `종류(#N T#): 제목` · 강제는 규약 기록 + 리뷰 로그만 · 로컬 서브에이전트. 진행 중 결정: 🔴 **일감·태스크가 없어도 리뷰는 종전대로 동작, 컨텍스트는 보조** · `test_issue_progress` 대역 추가 · T# 없으면 태스크 규칙 두 줄 생략. 「응 끝나면 마감까지 진행해」. 작성 계열 `['claude']`.
- 커밋 `e100c12`(T1·T2: `master/commit_scope.py` 파서 = `plan_metrics.WORK_SCOPE_RE` 같은 객체 · `master/context_synth/issue_context.py` 수집 · `docs/orchestrator-rules.md` §1.9 규약) · `32e45f5`(T3·T4: `build_prompt` 주입 · `review_runner.commit_context`/`range_context` 이중 fail-soft · 수집은 `main()`만) · `851f60e`(리포트 `reports/185-946-review-issue-context.md`).
- 검사: 관련 10파일 rc0 · 공식 통합 `Ran 199 tests / OK` · 전수 225파일 중 rc≠0 은 `test_sandbox.py` 하나(`AX_PROJECTS_ROOT` 미설정 — main 도 동일, 설정 시 38/38). 실물 드라이런(LLM 0)으로 갈래 넷 확인.
- `issue_finish(confirm=True)` 전 단계 완료 · 「완료」·100. 리뷰 연결 「이음 0 · 큐에 없음 3」 — 리뷰 도착 미확인.
- `issue_wrapup`: `ax-task-queue` 의존 변경 판정 → 16:18:31→19:26:33 재기동, 재판정 깨끗 · broker 최신 · 🔴 **`ax-projects` 는 「의존 판정 불가(journalctl rc=1)」로 재기동하지 않았다** — 미확인으로 둔다. 이 커밋 직후 배달.
- 안 잰 것: 운영 리뷰 큐가 이 컨텍스트로 실제 리뷰한 결과(첫 회차 = 이 일감의 해시별 리뷰 · 확인은 리뷰 큐 로그 `[리뷰큐] <sha8> 리뷰 컨텍스트 …`) · 오탐·미탐 감소 A/B · `.33` 게임 트윈 실물.
- 이 일감부터 커밋 제목은 `종류(#N T#): 제목` 이다(§1.9).

## #383 에서 실제로 안 잰 것

완료·배달 완료(main `2a4b859`). 상세는 `reports/181-383-pipeline-signals-recipe-batch.md`와 Redmine 마감 노트.

- 상용 체인으로 합성이 도는 실물. 첫 회차는 마운트된 프로젝트에 신호가 1건 이상 있는 토요일 22시 이후 `ax-batch.timer`다.
- 배치는 마운트된 프로젝트만 돈다. 신호가 있는 곳은 NS(12)·ModularStage(1)이고 마운트는 AXCluster라, NS 12건은 NS가 토요일 밤에 마운트돼 있어야 합성된다.
- 실제 분산 work의 finalize로 pipeline 신호가 쌓이는 것(임시 큐의 PATCH 라우트 호출까지만 쟀다).
- 합성기는 상용 체인 실패를 「클러스터 없음」으로 접어 0을 돌려준다 — 그때도 주간 마커가 써진다. 사유는 배치 로그의 합성기 줄에만 남는다.
- 범위 밖으로 뒀던 큐 내부 rejected 히스토리 누락은 #943으로 처리했다(main `9287515`, 리포트 182).

## 이전 마감분에서 이어지는 것 (#942 `master.relay`)

- 운영 실행: `cd /home/sim/ax-cluster` → `.venv/bin/python -m master.relay` (선택: `--issue N --agent codex`). 로그 `~/ax-state/relay`.
- 긴 작업·한도 소진·중단 뒤 이어가기, 레이어 안에서 issue_start/finish 호출은 미실증.
- #941 디스코드 연동은 미착수. 본문 설계는 #942에서 확정된 방향과 대조해야 한다. 자동 시작하지 않는다.
- 2026-11-14 구 일감 정리(9건 완료 종결 · #741·#368 노트 보강)의 상세는 커밋 `c51a3af`의 이 문서와 각 Redmine 노트에 있다.

## 지휘·승인·미확인

- 마스터 마지막 담당 기록은 claude(2026-11-14 15:48:34, 사용자 지시 — #383을 수행한 Claude 세션)다. #368 인계 때 이미 claude라 재기록하지 않았다. 워커 전역 codex(state, 2026-10-18). 모드 변경 없음.
- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842).
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 · #383·#943·#944·#368·#946·#947(도착 미확인). 최신은 각 Redmine 노트로 확인한다.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #911·#938·#939 등 리서치는 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. 다음 일감은 사용자 선택을 기다린다. 자동 시작하지 않는다.
2. 확인해 둘 실물: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943) · 운영 relay에서 한도 20% 이하 제안 배너(#368) · 리뷰 큐 로그의 `리뷰 컨텍스트` 줄과 #946 해시별 리뷰(#946)
