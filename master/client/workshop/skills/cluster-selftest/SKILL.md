---
name: cluster-selftest
description: 실 워커 클러스터(N대)가 push/2-tier/fencing/매니페스트 경로를 e2e 로 제대로 처리하는지 검증하는 self-provisioning 드라이런. 사람이 가짜 포팅 일감을 지어낼 필요 없이, 서버가 캔드(canned) push work 를 큐에 직접 주입해 워커가 claim→attempt 브랜치→durable merge→컨텍스트 매니페스트(온톨로지+RAG) 소비까지 자동 수행·검증·정리한다. 분산 클러스터 배포 직후 또는 distribution_mode 를 push 로 전환한 뒤 실 워커 동작을 확인할 때 사용. 서버 PC(task_queue 보유)에서만 의미.
---

# Cluster Self-Test — 실 워커 클러스터 드라이런

## 목적

`tests/smoke_cluster_2tier.py`(샌드박스, 서버가 fake 워커)는 코디네이터 git 로직만 본다.
본 스킬은 **실제 워커 PC 들을 실제로 태워** 다음을 한 번에 검증한다 (Plan v5 C.6 롤아웃 B):

- claim 시 **fencing epoch** 단조 증가 (재배정 stale 거부의 권위 기준)
- 워커가 **ephemeral `attempt/<task>/<worker>/<ts>`** 브랜치로 제출 (2-tier — 공유 write 타깃 없음)
- verify-loop 가 **durable `task/<task>`** 로 merge
- **스켈레톤 컨텍스트 매니페스트**(서버 1회 수집 = 온톨로지 규범 + RAG)가 git-carried 되어
  워커가 검색 없이 소비 — NONCE 라운드트립으로 증명

사람이 일감을 지어낼 필요가 없다 — 캔드 probe work 를 큐에 직접 주입한다(self-provisioning).

## 사용 금지 / 전제 (BLOCKING)

- **서버 PC 전용** — task_queue(8101)·master_orchestrator 가 도는 머신에서만. 클라(워커)
  PC 에서 호출 시 즉시 안내 후 종료. (서버 PC 판별: `config.json` 의 `server_mode=true` +
  `task_queue_autostart=true`, 또는 `http://localhost:8101/api/v1/health` 200.)
- **워커 ≥ 1대 폴링 중**이어야 claim 됨. 0대면 경고 — 워커 데몬 기동부터.
- distribution_mode 가 pull 이어도 무방 — 셀프테스트는 **push 경로를 강제**로 검증한다
  (단, 실 /distribute 가 push 로 동작하려면 별도로 config flip 필요).

## 절차

1. **환경 확인** — `http://localhost:8101/api/v1/health` 200 인지, `/api/v1/admin/workers`
   로 폴링 워커 수 확인. 0대면 사용자에게 워커 기동 안내 후 진행 여부 확인.
2. **드라이런 실행** — master_orchestrator MCP 도구 호출:
   - `mcp__master-orchestrator__cluster_selftest(repo="<프로젝트 루트>", tasks=<N>)`
   - 옵션:
     - `tasks`(기본 3) — 백엔드마다 등록할 **독립 작업 태스크 갯수**. 사용자가 "5개로 돌려줘"처럼
       지정하면 그 값 전달. probe 를 병렬 claim → 워커 ≥2·시간대 겹침이면 multi-worker 병렬까지 단정,
       워커 1대면 직렬로 순차 검증(둘 다 통과 조건). 클수록 부하·시간↑.
     - `backends`(기본 "local_llm,agy") — **백엔드별 write 격리 검증**. 각 백엔드에 tasks 개씩
       force_backend 로 태깅해 등록 → "로컬 LLM 이 코드 작성?"·"agy 가 코드 작성?"을 각각 판정
       (결과 JSON 의 `by_backend`). 한 쪽만 보려면 "local_llm" 또는 "agy" 로 지정. agy 케이스는
       agy 설치 워커가 폴링 중일 때만 통과. 총 등록 task = tasks × 백엔드 수.
     - `timeout_s`(기본 900) — 전체 대기 상한. tasks·backends 를 키우면 함께 늘릴 것.
     - `keep`(true 면 디버그용 정리 생략).
   - 도구가 캔드 work 주입 → 폴링 → 단정 → 정리까지 동기 수행하고 결과 JSON 반환.
3. **결과 보고** — 반환 JSON 의 `checks`(각 단정 pass/fail)·`milestones`(claimed worker·
   epoch / submitted attempt 브랜치 / verified)·`manifest`(rag_hits·norms 수)를 사용자에게
   요약. `ok=true` 면 실 워커 클러스터 e2e 통과.
4. **실패 진단** — `fails` 가 있으면 어느 단계에서 멈췄는지(milestones 로 판단):
   - claimed 없음 → 워커 미폴링 / 워커가 push 코드 빌드 아님(구 worker.exe) / 큐 미도달
   - submitted 가 `attempt/` 아님 → 워커가 구 빌드(2-tier 미적용)
   - verified 없음 → verify-loop / UE·검증 게이트 / LLM 실패 (master_orchestrator 로그 확인)
   - NONCE 미포함 → 매니페스트 미배선 워커 빌드 또는 매니페스트 수집 실패(context_search 8100)
   서버 로그(`task_queue_<date>.log`·`master_orchestrator_<date>.log`)를 함께 확인.

## 정리·안전

- 기본적으로 **흔적 0** — worktree·selftest/durable/attempt 브랜치(origin+로컬) 자동 제거.
  probe 파일은 throwaway 브랜치에만 있었고 main 미접촉. `keep=true` 면 디버그 위해 보존.
- worktree 격리라 라이브 데몬의 메인 작업트리·진행 중 실 work 를 건드리지 않는다.

## 종료

결과 보고 후 자연 종료. 재실행이 필요하면 다시 `/cluster-selftest`.
