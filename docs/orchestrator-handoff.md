# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 직전 체크포인트(10-31 17:20 Claude — #826 Phase A·#852)는 git 이력 `3184a9b`, 리포트 132.
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-31 18:45 KST · Claude · 사용자 지시(토큰 부족으로 인계)
- **저장소**: `~/ax-cluster` · `main` · HEAD=`origin/main`=`f29aaf0`. 미커밋: 이 인계서뿐(커밋은 별도 승인).
- **마운트**: **AXCluster**. 배달 `.43`·`.2`·`.33` 전부 HEAD 일치(update rc=0, f29aaf0).
- **서비스 재기동**(사용자 승인): `ax-task-queue` 18:05:01 · `ax-projects` 18:18:23.
- **지휘 기록**: 마스터 담당 `claude`(10-21) · 워커 전역 `codex`(10-18). 바꾸지 않았다.
- **실행 중**: 없음. `.2` 상주 데몬은 **정지·등록 해제**(AxWorker 삭제, pid 59676 종료, 재조회 0).
- **설정 변경(트윈, git 밖)**: `ModularStage/config.yaml` `clone_url` HTTP → `gitea@192.168.0.57:Sim/ModularStage.git`
  (.2 세션0 HTTP 자격증명 실패 해소, 사용자 승인). 백업은 세션 scratchpad. `.2` 에 `C:\trunk\ModularStage` 클론 생김(4cd229f).

## 🔴 이번 세션의 큰 결정 — 워커·요청자 상주 데몬 폐기, 서버(.57) SSH 총괄

- 사용자 확정 2026-10-31: *"상주하는 서버가 모두 ssh로 총괄 처리할 수 있는데?"* · **정본 ⑤ = 「서버가 다음 조각을 배정」**(pull 폐기).
- 경위: `#320`(08-27) 상주 전폐 → `#404`(09-12) .2 빌드 상주 복원 → 이번 세션이 #404 를 「기존 자산」으로 보고
  #857 T4 를 buildjob·데몬 경로로 구현(`03af704`) — 사용자 지적 *"폐기했다고 히스토리 있는데 왜 쓴건데"*.
- 원인 정리: 메모리 6곳(정본 7단계의 「원전 데몬을 옮겨라」·「부활 조건」 등)과 CLAUDE.md 셋(`~/CLAUDE.md`·저장소·
  `win-worker-2.md`+.2 사본)을 고쳤다 — `f29aaf0`. 결정은 `log_history` 2건.
- 정리 일감 **[#860](http://192.168.0.57:8080/issues/860)** — 전수 조사 노트 있음. 요지:
  데몬이 실제로 받던 일은 `buildjob` 뿐 · `client/init/residency.py` 는 데몬 상주 + **세션1 런처(AxConductor, 유지)** 겸용 ·
  빌드 대체는 `layer3_verify.run_build_on_workshop`(SSH, 호출부 0, 가드 `test_no_integrator.BUILD_CALLERS_ALLOWED` 가 막음) ·
  M7 일감 중 데몬 전제: **#406**(데몬 자기 갱신) · **#344**(directive 를 데몬이 따름) · **#259**(온보딩에 claimer 상주).
  [주의] 배달 코드가 아직 상주를 등록한다 — **unreal 프로젝트를 마운트하면 .2 에 AxWorker 가 되살아난다**(#860 T1 전까지).

## 이번 세션 — 완료한 것

- #729·#826 → M7, `[아이디어]` 제거. #856 에 Monolith MIT 배포 조건 노트.
- **#826 Phase A(T1~T6) 완료** · **#852 완료** — 리포트 132(`5ecb719`). 플랜 영역 형식 v1/v2, MCP `plan_*_tool`, 스킬 `ax-plan`.
- #826 하위 분리: **#857** Phase B(unreal 소스 경로) · **#858** Phase C(에디터·MCP, #856 선행). 본문 [보충](제네레이트 불필요).
- **#857 진행**(플랜 v1 표, 마킹은 전부 `plan_transition`):

  | T | 상태 | 커밋·근거 |
  |---|---|---|
  | T1 | 완료 | .2 임시 worktree 실측 — Build.bat 이 새 UCLASS 를 **제네레이트 없이** 컴파일(46초) |
  | T2 | 완료 | `aec663b` 플랜 형식 v2 「단계」 칸 |
  | T3 | 완료 | `d49af03` `plan_steps.steps_for_task` |
  | T4 | 완료(**재작업 대상**) | `03af704` buildjob 경로 + `GET /api/v1/tasks/{id}/submission` — 데몬 폐기로 T7 이 대체 |
  | T5 | 완료 | `fe10709` unreal 4단계 해당없음 |
  | T7 | 대기 | **빌드 단계를 서버 SSH(run_build_on_workshop)로 재연결** — 가드 변경과 맞물림(#860 T2) |
  | T6 | 차단 | 실증 — T7 뒤. 데몬 경로 빌드 4624089c(PASS 104초)는 사실로만 남김 |

- 커밋(이 세션): `79a3c0d` `4cab2b1` `a02e7ee` `90ed562` `2552ff4` `b5ec5eb` `aec663b` `d49af03` `03af704` `fe10709` `f29aaf0`
  + 문서 `3184a9b` `5ecb719`. 마지막 코드 검사: 전수 194개 9121/9121 · 통합 181 OK.

## 사용자 답을 기다리는 것

1. **#860 플랜 초안**(대화에서 제시, 아직 미등록) — T1 배달 상주 등록 제거(런처 유지) · T2 가드 재정의 ·
   T3 데몬 코드 처분(#857 T7 뒤) · T4 #406·#344·#259 재정의 · T5 docs 정정 · T6 실측(마운트 전환해도 AxWorker 안 생김).
   미결: ① T3 에서 `buildjob`·submission 엔드포인트까지 지울지 ② T4 를 이 플랜에서 할지 ③ 등록 여부·수행 방식(로컬/AX 워커).
2. #826 다음 단계는 #857·#858 로 나눔(완료). `next_steps` 표시 개선 여부(원전 계약이라 결함 아님) 미결.
3. 앞 세션에서 넘어온 결정: #839 ②·#840 ①·#791 D·#820·#372·#855 착수 방식.

## 바로 다음 작업

1. HEAD·dirty·Redmine·마운트 재조회. 다음 작업은 사용자가 고른다.
2. 일감 시작은 `ax-plan` 스킬 — `plan_start_tool` 먼저, 마킹은 `plan_transition_tool` 로만.
3. #860 플랜 미결 3개를 묻고 등록 → T1·T2 → #857 T7 → #860 T3 순.
4. **기존 경로를 재사용하자고 하기 전에 그 경로의 폐기·복원 이력부터 grep**(reports·history·Redmine) — 이번 세션의 실수.
5. 미검증: #826 T6 「다른 세션이 다음 태스크를 집는지」 — 새 세션에서 `plan_start_tool(826)`·`(852)` → plan_done 확인.

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- AXCluster 큐 고아 태스크 10건·스풀 26묶음 — 마운트 전환 handover 에 보고됨, 손대지 않음
- 마스터 worktree 2개 정리(#333) · #709 GitHub 저장소 삭제 · #211 RAG 정책 미착수 · #650(ModularStage 마운트 때 프로필)
