# 현재 AX 작업 인수인계

> 2026-11-14 — #950(마감 추적 조기 skipped — 워터마크 ≠ 걷기 커서 · 닫힌 회차 조회) 마감 완료(main `ee90bef`, Claude). 직전 #947은 2회차까지 마감·배달 완료.
> 다음 일감은 사용자 선택을 기다린다. 항목·진행은 Redmine, 지난 상세는 Git 이력·리포트로 확인한다.

## 직전 마감 — #950 완료

- 발단: #946 뒤 리뷰 큐에서 `902f4e99`(#368)가 메시지로 일감을 찾고 작성 계열 「미상」. 사용자 「902f4e99 추적 기록 안 맞은 원인 확인해줘」 → 원인: `issue_progress` 규칙 ②가 워터마크 `last_indexed_commit`(합성 완료 표시, 이벤트 끝으로 한 번에 찍힘)을 기준으로 써서, 색인 걷기(리뷰 등재 자리)가 합성 실패로 멈춘 사이 조기 skipped → 종합 리뷰 먼저 → 회차 닫힘 → 늦은 커밋 리뷰가 추적 조회 None.
- 승인: 「일감 등록하고 진행해줘」 → #950 · 범위 「둘 다」 · 「이 세션이 직접」. 작성 계열 `['claude']`.
- 커밋 `27689c1`(T1: 규칙 ② 기준 = `analyzed_commit` + 같은 커서에 묶인 `analyzed_beyond.json`, 커서 없으면 워터마크 폴백·로그) · `627730e`(T2: `issue_track.round_of_hash_any` 열린 우선·닫힌 포함 → `commit_authors`(닫힌 회차를 활성 잠금보다 앞에)·`issue_context` 기본 조회. `issue_of_hash` 계약은 유지) · `ee90bef`(리포트 `reports/187-950-issue-track-walk-cursor.md`).
- 검사: `test_issue_progress` 133 · `test_issue_track` 111 · `test_review_runner` 171 · `test_issue_link` 40 · `test_issue_context` OK · 공식 통합 `Ran 199 tests / OK`. 실물: `902f4e99` → 일감 368 · 계열 `('codex',)`.
- `issue_finish` 전 단계 완료 · 「완료」·100. wrapup: `ax-task-queue`(20:10:02)·`ax-projects`(20:10:07) 의존 변경 재기동, 판정 깨끗 · broker 최신. 이 커밋 직후 배달.
- 안 잰 것: 걷기가 멈춘 새 회차가 waiting 으로 버티다 이어지는 운영 실물(확인: `색인 걷기가 아직 안 지났다` 로그). 이미 닫힌 #368 회차 기록은 소급하지 않았다.

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
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 · #383·#943·#944·#368·#946·#947·#950(도착 미확인). 최신은 각 Redmine 노트로 확인한다.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #911·#938·#939 등 리서치는 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. 다음 일감은 사용자 선택을 기다린다. 자동 시작하지 않는다.
2. 확인해 둘 실물: 토요일 22시 이후 `ax-batch` 로그의 `recipe_synthesis` 줄(#383) · 다음 rejected 라운드의 큐 로그 `[history] … rejected(큐 내부 종결)` 줄(#943) · 운영 relay에서 한도 20% 이하 제안 배너(#368) · 리뷰 큐 로그의 `리뷰 컨텍스트` 줄(#946, 첫 실물 확인됨 19:28~19:53) · 합성이 멈춘 회차의 `색인 걷기가 아직 안 지났다` 줄(#950)
