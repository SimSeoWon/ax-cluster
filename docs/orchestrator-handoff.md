# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 직전 체크포인트(10-31 22:38 Claude — #861·#860·#857 종결)는 git 이력 `c65a7e2`.
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-31 23:06 KST · Claude · 사용자 지시(토큰 부족으로 인계)
- **저장소**: `~/ax-cluster` · `main` · HEAD=`origin/main`=`e7d0600`(+ 이 인계서 커밋) · 작업 트리 clean.
- **마운트**: **AXCluster**. 배달은 `c65a7e2` 기준 3대 일치 — **`e7d0600`·인계서 커밋 뒤 `master.client update` 미실행**
  (바뀐 것은 마스터 전용 `plan_*` 모듈이라 배달물 변화는 없을 것이나 check 의 출처 커밋 대조가 실패한다 — 다음 세션에 승인 받아 update).
- **서비스**: `ax-projects` 재기동 23:04:02(사용자 승인) — 실행 커밋 `e7d0600`(거절 기록 포함).
- **지휘 기록**: 마스터 담당 `claude`(10-21 기록 — 이번 인수 미기록, 사용자 지시 없음) · 워커 전역 `codex`(10-18).
- **실행 중**: 없음. **홈 지침**: `home-guides` 4대 정본 일치(22:19 기준, 이후 machines/ 변경 없음).

## 이번 세션 요약 (상세는 각 일감 노트)

- 상주 데몬 철거 축 종결 — `#861`(T1~T6) · `#860` · `#857` 완료. 후속 `#862`(crontab 경합, 핵심 위험 차단됨) · `#863`(실컴파일 빌드·실 SSH 파견·NS/MotionForge 잔재 — 관찰형).
- `.2` 의 접미사 없는 `AxConductor` = ModularStage 정식 런처(잔재 아님).
- **`#864` 일감 플랜(SDD) 효능 측정** — 진행 중, 아래.

## `#864` — 진행 상황 (플랜 영역이 정본, `plan_start_tool(864)` 은 T4 를 가리킨다)

| T | 상태 | 요지 |
|---|---|---|
| T1 | 완료 | `master/plan_events.py` — 규칙 거절을 `AXCluster/plan_events.jsonl` 에 기록(예외 그대로). 실측: 의도적 거절 1건 기록 되읽기 |
| T2 | 완료 | `master/plan_metrics.py issue <ids>` — 리드·차단·근거·범위 이탈(근사)·거절·재개 정확도(공백 ≥30분 근사) |
| T3 | 완료 | `baseline --version-id 19` · `compare` — M6 버그/개선 32건 기준선 |
| T4 | 대기 | **첫 측정 보고서** `reports/` 새 번호 — #861·#857·#852 대 M6 기준선 수치표·한계 |
| T5 | 대기 | 사용자가 고른 M7 버그 몇 건을 ax-plan 으로 진행 → 비교 보고 |

첫 실측(참고용, 플랜 표본 3건):

    기준선 M6 32건   리드 중앙 4.42h · 평균 49.96h · 재개 2건(3회: #799 2 · #748 1) · 종결 근거 해시 100%/검사 94%
    플랜 3건         리드 중앙 5.32h · 평균 8.72h  · 재개 0 · 종결 근거 해시 100%/검사 67%
    플랜 전용         #861 재개 정확도 1/1 · 범위 이탈 #861 36% · #857 78% · #852 85%(본문 언급 커밋 혼입 — 근사 한계)

- 실행: `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.plan_metrics issue 861 857 852` / `baseline --version-id 19` / `compare --version-id 19 --issues 861 857 852`.
- 서브 에이전트가 정한 설계(사용자 확인 전): 거절 기록은 getter 미주입 호출(MCP·실 Redmine)에서만 남는다 — 테스트 대역이 운영 기록에 쓰지 않게. MCP 래퍼는 caller 를 넘기지 않아 빈칸.
- 해석 주의: M6 도 종결 근거가 이미 높아 그 지표로는 차이가 안 보인다. 평균 리드 차이는 M6 「해결」 방치 2건(#821·#819) 탓이 크다.

## 사용자 답을 기다리는 것 / 다음

1. `#864` T4 착수(보고서) — 그 뒤 T5 시험 대상 일감 선택(M7 버그/개선 열린 일감에서).
2. `e7d0600` 이후 `master.client update` 실행 승인.
3. 위 설계 선택(거절 기록 범위·caller 빈칸) 확인.
4. `#862` 추가 방어 여부 · 앞 세션 미결: #839 ②·#840 ①·#791 D·#820·#372·#855 · #826 `next_steps` 표시.

## 바로 다음 작업

1. HEAD·dirty·Redmine·마운트 재조회 → `plan_start_tool(864)` (T4 next 예상).
2. 마킹은 `plan_transition_tool` 로만 — 거절은 이제 `plan_events.jsonl` 에 쌓인다(측정 데이터).
3. 운영 행위(배달·재기동·마운트 전환·빌드)는 실행 전 승인.
4. **기존 경로를 재사용하자고 하기 전에 그 경로의 폐기·복원 이력부터 grep**(reports·history·Redmine).

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- AXCluster 큐 고아 태스크 10건·스풀 26묶음 — 손대지 않음 · 마스터 worktree 2개(#333) · #709 · #211 · #650
