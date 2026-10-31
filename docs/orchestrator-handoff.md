# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 직전 체크포인트(10-31 18:45 Claude — #860 결정·#857 T1~T5)는 git 이력 `1366e08`.
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-31 22:20 KST · Claude · 사용자 지시(인수인계서 갱신, T6 은 다음에)
- **경위**: Codex 가 18:45 인계를 받아 `#861` T1 을 구현·검토하던 중 토큰 소진(19:45 무렵) → Claude 인수.
  Codex 미커밋 변경(T1)과 조사 보고서 6개를 대조·재검증해 이어받았다.
- **저장소**: `~/ax-cluster` · `main` · HEAD=`origin/main`=`462ac9d` · 작업 트리 clean(이 인계서 제외, 커밋 별도 승인).
- **마운트**: **AXCluster**. 배달 `.43`·`.2`·`.33` 전부 HEAD `462ac9d` 일치(update rc=0) · `check` 3/3 OK.
  `.43` `~/ax-cluster` 도 pull(`7add46b` 시점, 이후 커밋은 코드·`win-worker-2.md` — `.43` 링크 대상 `bc250-1.md` 는 그대로).
- **지휘 기록**: 마스터 담당 `claude`(10-21 기록 — 이번 인수는 기록하지 않았다, 사용자 지시 없음) · 워커 전역 `codex`(10-18).
- **실행 중**: 없음. Codex 샌드박스에서 1h39m 멈춰 있던 `test_task_submission.py` 는 사용자 승인으로 종료.
- **홈 지침**: `home-guides` 로 4대 전부 정본 일치(.2 CLAUDE/AGENTS 22:19 재기록, .33 CLAUDE 21:10 재기록 — 원격 `.bak-*` 백업 있음).

## 이번 세션 — `#861` (SSH 총괄 전환 뒤 데몬 회귀 정리) T1~T5 완료

| T | 커밋 | 요지 |
|---|---|---|
| T1 | `bbd0110` | 배달·check·ensure 가 어떤 kind 에도 AxWorker 를 만들거나 띄우지 않는다 · 잔재 해제 · 등록 조회 실패≠부재(check FAIL) · Windows worker 는 AxConductor 만(unreal 포함) · **`master.client home-guides`** 신설 |
| T2 | `5a39403` | `plan_build.build_step` = 서버 SSH(`run_build_on_workshop`) · 리비전 **확인만**(불일치·조회 실패·dirty → 빌드 안 함, 빌드 뒤 HEAD 이동 → 실패) — `#857` T7 동일 |
| T3 | `9a195e0` | `worker_daemon`·`ax_safety`·`buildjob`·`test_worker_daemon` 삭제 · 서버 계약 → `test_queue_worker_contracts` · 가드 `test_no_worker_daemon` · `spec.DEPRECATED_PAYLOAD`(배달이 지우고 check 가 잔재 FAIL) · submission API·일반 claim 은 유지 |
| T4 | `7add46b` | 현행 문서·스킬 15개 정정(정본 ⑤ 서버 배정 · 상주 없음) · RAG 좀비 컨텍스트 5건 삭제(백업: 세션 scratchpad) · `#406`·`#259` 정정 노트 |
| T5 | `462ac9d` | 통합 182 OK · 전수 196파일 9286/9286 · 독립 검토 지적 1·2·4·6·7 반영: AxWorker*/AxClaimer* 전수 탐지·해제(-EncodedCommand), check 의 데몬 프로세스 검사, 빌드 선택 `need_agent=False`, 오류 경로 검사 |

- 실측: `.2`·`.33` 예약 작업 AxWorker*/AxClaimer* 0 · 데몬 프로세스 0 · `.43` cron·프로세스 0 · 기배달 데몬 파일 3대 삭제 확인.
- 사용자 결정(이번 세션): home-guides 범위 4대·쓰기는 복사본만 · `.2` AGENTS 는 `win-worker-2.md` 에서 생성 ·
  `.33` AGENTS 는 만들지 않음 · 리비전 확인만 · 데몬 소스 삭제+계약 이전 · submission API 유지 · 잔재는 check FAIL.
- `log_history` 1건(home-guides 결정). 상세는 `#861` 노트(태스크별 근거).

## 사용자 답을 기다리는 것 / 다음

1. **`#861` T6 — 다음 세션으로 미룸(사용자 2026-10-31)**. 항목마다 승인:
   ① 마운트 전환(예: ModularStage) 뒤 3대 AxWorker/AxClaimer·데몬 프로세스 비재생성 + 비마운트 쪽 데몬 파일 잔재 정리
      (.2 ModularStage · .43 ModularStage·NS·MotionForge) ② 정상 SSH 파견·AxConductor 무손상 ③ `plan_build.build_step` 으로 `.2` 실빌드(`#857` T6).
   [주의] `build_step` 은 아직 운영 호출부가 없다 — 실증은 직접 호출로 한다.
2. **`#862`**(신규, crontab 해제 경합) — 핵심 위험은 `462ac9d` 로 막힘(읽기 실패 시 쓰지 않음). 줄 수 대조 추가 여부는 사람 결정.
3. **`#406`** 열어 둠 — 상주 부분만 소멸, 「새 워커 등록만으로 조각 1건」 조건은 유효(닫기 승인이 있었으나 본문 대조 뒤 보류를 보고함).
4. `.2` 에 접미사 없는 옛 예약 작업 `AxConductor` 가 `AxConductor_AXCluster` 와 함께 있다 — 처분 미결.
5. 앞 세션에서 넘어온 결정: #839 ②·#840 ①·#791 D·#820·#372·#855 착수 방식 · #826 `next_steps` 표시 개선 여부.

## 바로 다음 작업

1. HEAD·dirty·Redmine·마운트 재조회. 다음 작업은 사용자가 고른다.
2. 일감 재개는 `ax-plan` — `plan_start_tool(861)` 이 T6 을 가리킨다. 마킹은 `plan_transition_tool` 로만.
3. 마운트 전환·`.2` 빌드는 운영 행위다 — 실행 전 승인. 전환 뒤 `master.client check <프로젝트>` 와
   `home-guides` 로 대조(이제 check 가 잔재·프로세스·조회 실패를 FAIL 로 본다).
4. **기존 경로를 재사용하자고 하기 전에 그 경로의 폐기·복원 이력부터 grep**(reports·history·Redmine).

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- AXCluster 큐 고아 태스크 10건·스풀 26묶음 — 마운트 전환 handover 에 보고됨, 손대지 않음
- 마스터 worktree 2개 정리(#333) · #709 GitHub 저장소 삭제 · #211 RAG 정책 미착수 · #650(ModularStage 마운트 때 프로필)
