# 201 — #973 테스트가 실제 레드마인에 쓰던 누수 · 라이브 판정을 예약 시점에 고정

2026-11-16 · Claude · #972 전수 1회차의 `test_rounds` 간헐 실패에서 출발. 같은 세션.

## 무엇이 일어났나

- #972 전수 1회차에서 `test_rounds` 「작업장 요청자 — 등재 본문 ③ 이 그 호스트다」가 한 번 실패했다(단독 실행은 통과).
- 재현하려고 같은 파일을 16개 동시에 돌렸더니 1회 실패(반대 방향으로 섞임) **+ 실제 레드마인 NS 에 #974
  「[분산 작업] 상호작용」이 생겼다**(22:20:58 KST). 같은 제목의 #872(2026-11-01)도 있었다.
  **테스트가 실제 레드마인에 닿는지 확인하지 않고 부하 실행을 돌린 것은 내 판단 실수다.** 둘 다 사용자 지시로 테스트 잔재
  노트를 남기고 「완료」로 닫았다.

## 원인

- 기존 방어(`test_redmine_live_guard`, 2026-09-13 NS 198건 사고 뒤): 임시 큐 루트는 실제 설정(URL·컨테이너 DB 키·
  `project_of`)으로 폴백하지 않는다. 라이브 판정 = `AX_TASK_QUEUE_ROOT` 와 같은 경로.
- 구멍: 비동기 레드마인 작업 3곳(등재 이슈·라운드 공지·조각 실패 노트)이 **스레드 안에서 늦게** 판정했다.
  `test_rounds.test_registration_itself_triggers_dispatch` ⓑ 가 ⓐ 의 임시 루트를 `AX_TASK_QUEUE_ROOT` 로 라이브 선언하는
  틈에, ⓐ 의 `_work()` 등재가 띄운 스레드가 늦게 돌면 실제 설정으로 게시했다.
- 간헐 실패도 같은 뿌리: 앞 검사의 늦은 스레드가 뒤 검사 `_texts_for` 가 patch 한 게시 함수로 들어가 `made[0]` 을 차지.
  같은 제목이 같은 분에 등재되면 work_id 도 같아서(`…_682fa5e5`) 본문만 보고는 구별이 안 됐다.

## 바꾼 것 (`issue/973`)

- `f88d714` T1 — `logic_cleanup._spawn_redmine_job`: 예약 시점(호출 스레드)에 `is_live_queue_root` 를 재서 스레드 지역값으로
  고정한다. `_read_redmine_config` 는 고정값이 있으면 그것을 쓴다. 테스트들이 쓰는 기존 patch 서명은 그대로다.
  서비스는 늘 라이브 루트라 동작이 같다. 회귀: `test_redmine_live_guard` [6] — `idx.lock` 으로 등재 스레드를 붙잡고 루트를
  라이브로 바꿔도 게시 0. **수정 전 코드로 같은 시나리오를 돌리면 게시 1회**(가짜 URL)로, 검사가 결함을 잡는 것을 확인했다.
- `414af3f` T2 — `test_rounds` 격리: 실행 내내 실제 게시·노트 함수를 「호출되면 기록 + 실패」 대역으로 막고 끝에 0회를 단언 ·
  작업 스레드 이름(`REDMINE_JOB_THREAD`)으로 검사마다 자기 작업을 patch 안에서 끝낸다 · `_texts_for` 는 앞 작업을 기다린 뒤
  patch 하고 자기 work_id 본문만 집는다(제목도 kind 별) · ⓑ 는 새 루트를 라이브로 선언한다.

## 검증

- 관련 검사 rc0: `test_redmine_live_guard` 12/12 · `test_rounds` · `test_notice_recovery` 40 · `test_nowork` ·
  `test_requester_handoff` 22 · `test_failed_work_terminal` · `test_history_terminal` 29 · `test_infra_undecided` 67.
- 부하 재현(대역·수정 적용 **뒤에만**): `test_rounds` 16 동시 × 3 = 48회 — 실패 0 · 막힌 호출 0.
  Redmine 전체 최신 번호 전 #974 → 후 #974(새 일감 0).
- 전수 `master.sweep` rc0: 236파일 12282/12282 · unittest 542/542. 공식 통합 `Ran 210` OK.

## 범위 밖으로 남긴 것

- `test_mcp_servers` 도 전역으로 `AX_TASK_QUEUE_ROOT` 를 임시 경로로 둔다. `AX_PROJECTS_ROOT` 도 임시라 NS 를 못 풀고
  등재 호출이 없어 지금은 이슈가 나지 않지만 같은 꼴의 위험이다. 이제 늦은 스레드 경로는 T1 이 막는다.

## 같은 세션의 관측 — #971·#972 마감 뒤

- #972(커밋 기준 관계 근거) 배포 뒤 `ax-indexer` 회차(22:10:42)에서 `master/plan_metrics` 가 @6569345 로 사실 통과·저장
  (22:12:08), 커서가 @1cad28f·@4e3fa21 로 전진했다. #972 C4·#971 C5 충족 근거.

최종 결과는 Redmine #973 마감 노트.
