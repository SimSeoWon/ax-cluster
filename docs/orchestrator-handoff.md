# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 직전 체크포인트(10-31 22:20 Claude — #861 T1~T5)는 git 이력 `525f4ee`.
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-31 22:38 KST · Claude · 사용자 지시
- **경위**: Codex 가 `#861` T1 진행 중 토큰 소진(19:45 무렵) → Claude 인수. 이후 `#861` T1~T6 완료·종결,
  `#860`·`#857` 종결까지 이 세션에서 했다.
- **저장소**: `~/ax-cluster` · `main` · HEAD=`origin/main`=`525f4ee`(+ 이 인계서 커밋) · 작업 트리 clean.
- **마운트**: **AXCluster**(T6 에서 ModularStage 로 갔다가 복귀). 배달 `.43`·`.2`·`.33` HEAD `525f4ee` 일치 · check 3/3 OK.
- **서비스**: `ax-projects` 재기동 22:31:57(사용자 승인) — 실행 커밋 `525f4ee`. 그 전에는 `fe10709` 로 돌아
  `set_active` 의 자동 align 이 `#831` 가드에 거절됐다(CLI `master.client update` 로 배달했다).
- **지휘 기록**: 마스터 담당 `claude`(10-21 기록 — 이번 인수는 기록하지 않았다, 사용자 지시 없음) · 워커 전역 `codex`(10-18).
- **실행 중**: 없음.
- **홈 지침**: `home-guides` 로 4대 전부 정본 일치(.2 CLAUDE/AGENTS 22:19 재기록 · 원격 `.bak-*` 백업 있음).

## 이번 세션 — 상주 데몬 철거 축 종결

| 일감 | 상태 | 요지 |
|---|---|---|
| `#861` | 완료 | T1 `bbd0110` 배달·check·ensure 상주 제거 + `home-guides` · T2 `5a39403` 플랜 빌드 서버 SSH · T3 `9a195e0` 데몬·buildjob 삭제, 계약 이전, 기배달 잔재 정리 · T4 `7add46b` 문서·RAG · T5 `462ac9d` 리뷰 반영(잔재 전수 탐지·프로세스 검사·빌드 선택 need_agent=False) · T6 실측 |
| `#860` | 완료 | 부모 — 할 일 6·완료 조건 3 을 #861 결과로 대조해 종결 |
| `#857` | 완료 | T7 = #861 T2 · T6 은 SSH 경로 실호출(방식 a) 근거로 마킹 |
| `#862` | 신규 | crontab 해제 경합 — 핵심 위험은 `462ac9d` 로 차단(읽기 실패 시 쓰지 않음). 줄 수 대조 추가 여부는 사람 결정 |
| `#863` | 신규 | 후속 실증: ① 실컴파일 빌드 ② 실 SSH 파견 ③ NS·MotionForge 마운트 때 `.43` 잔재 정리. 독립 일감(부모 해제 — 열린 자식이 있으면 부모 종결이 무시된다, #754) |

- T6 실측(22:2x): ModularStage 마운트 → 배달이 3대 데몬 파일 삭제·되읽기 · check 3/3 OK ·
  AxWorker*/AxClaimer* 0 · 데몬 프로세스 0 · `build_step('ModularStage', 4cd229f)` .2 PASS(up-to-date 1.3초, 컴파일 0) ·
  codex readiness .2/.43 OK · AXCluster 복귀 배달 3/3 OK.
- 확인된 사실: `.2` 의 접미사 없는 `AxConductor` 는 잔재가 아니라 **ModularStage 의 정식 런처 이름**(`conductor_task_name`).
- 비마운트 check 에서 `.43` NS·MotionForge 체크아웃에 폐기 페이로드 잔재 FAIL — 그 프로젝트 마운트 때 배달이 지운다(#863 ③).
- `.2` 에는 NS·MotionForge 체크아웃이 없다.
- 사용자 결정(이번 세션): home-guides 범위·생성 규칙 · 리비전 확인만 · 데몬 소스 삭제+계약 이전 · submission API 유지 ·
  잔재는 check FAIL · `#406` 은 열어 둠(상주 부분만 소멸) · T6 은 실측분으로 완료, 남은 것은 #863.

## 사용자 답을 기다리는 것 / 다음

1. 다음 작업은 사용자가 고른다. `#863` 은 「다음 실제 work·마운트」에서 판정하는 관찰형이다.
2. `#862` 추가 방어 여부.
3. 앞 세션에서 넘어온 결정: #839 ②·#840 ①·#791 D·#820·#372·#855 착수 방식 · #826 `next_steps` 표시 개선 여부.

## 바로 다음 작업

1. HEAD·dirty·Redmine·마운트 재조회.
2. 일감 재개는 `ax-plan` — `plan_start_tool` 먼저, 마킹은 `plan_transition_tool` 로만.
3. 마운트 전환·`.2` 빌드는 운영 행위 — 실행 전 승인. 전환 뒤 `master.client check <프로젝트>` 와 `home-guides` 로 대조
   (check 는 이제 상주 잔재·데몬 프로세스·폐기 페이로드·조회 실패를 FAIL 로 본다).
4. **기존 경로를 재사용하자고 하기 전에 그 경로의 폐기·복원 이력부터 grep**(reports·history·Redmine).

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- AXCluster 큐 고아 태스크 10건·스풀 26묶음 — 마운트 전환 handover 에 보고됨, 손대지 않음
- 마스터 worktree 2개 정리(#333) · #709 GitHub 저장소 삭제 · #211 RAG 정책 미착수 · #650(ModularStage 마운트 때 프로필)
