# 운영 상태

> 손으로 돌린 스냅샷이다(`python -m master.ops_snapshot`) — 라이브가 아니다. 지금 값은 원천을 다시 조회한다.

- 출처: `systemctl show <unit> -p ActiveState -p SubState -p ExecMainStartTimestamp` (읽기 전용)
- 출처: `git rev-parse HEAD` · `git status --porcelain` (마스터 체크아웃)
- 출처: 워커 `.ax/config.json` 의 `delivered_by` — `master.client.bundle.compare_version`
- 생성: 2026-11-24T23:44:02+09:00
- 마스터 HEAD: 54867337be74

## 마스터

| 항목 | 값 |
|---|---|
| HEAD | 54867337be74 |
| 작업트리 | clean |

## 상주 서비스

| 유닛 | ActiveState | SubState | 기동 시각 |
|---|---|---|---|
| ax-broker | active | running | Tue 2026-11-24 21:01:24 KST |
| ax-projects | active | running | Tue 2026-11-24 21:01:24 KST |
| ax-task-queue | active | running | Tue 2026-11-24 21:01:24 KST |

## 워커 배달 리비전 — 마운트 프로젝트 AXCluster

| 호스트 | 역할 | 배달 커밋 | 판정 | 뒤처짐 | 비고 |
|---|---|---|---|---|---|
| 192.168.0.2 | worker | 1fec5949baca | drifted | 1 | 1fec594 — HEAD 보다 1 커밋 뒤 (재배달 필요) |
| 192.168.0.33 | worker | 1fec5949baca | drifted | 1 | 1fec594 — HEAD 보다 1 커밋 뒤 (재배달 필요) |
| 192.168.0.43 | worker | 1fec5949baca | drifted | 1 | 1fec594 — HEAD 보다 1 커밋 뒤 (재배달 필요) |
