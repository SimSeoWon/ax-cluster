> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

## 10. 관련 문서
- 이 보드(BC-250 #1)의 하드웨어 작업 이력: `~/bc250-backup-staging/reports/`, `~/.claude/projects/-home-sim/memory/`
- AgentTest 2026-07-07 원 설계: `~/bc250-backup-staging/memory/project_agenttest_architecture.md`
- gajae-code: https://github.com/Yeachan-Heo/gajae-code
- AgentTest: https://github.com/SimSeoWon/AgentTest
- 2026-08-06 인프라 작업(헤드리스·TTM/GTT·마스터 링크·방화벽·속도 벤치):
  `~/bc250-backup-staging/reports/24-ttm-gtt-tuning-headless-cluster-link.md`
- 2026-08-06 모델 품질 비교(UE5 태스크 6종):
  `~/bc250-backup-staging/reports/25-model-quality-comparison-14b-vs-35b.md`
- [중요] **저장소 작업 리포트는 저장소 안으로 옮겼다** (2026-08-08): [`../reports/`](../reports/) —
  **06~35** (2026-08-23 기준 · 15 는 마스터 로컬). 밖에 두면 3자 동기에서 빠지고, 실제로 안 읽혔다.
  어느 리포트에 무엇이 있는지는 [`../reports/README.md`](../reports/README.md) 표로 본다.
- 하드웨어·인프라 로그(01·03·04·05): `sim@192.168.0.57:~/claude-workspace/reports/`

## 10.1 레드마인 — **AX 인프라 일감은 전용 프로젝트 `ax-cluster` 에 둔다** (사용자 결정 2026-09-28)

`http://192.168.0.57:8080` · 마스터의 컨테이너(`redmine-redmine-1`, 8080→3000) · REST API 켜짐 ·
트래커 **`코드리뷰` 하나** · 상태 5종 · 우선순위 3종.

    AX 인프라 일감      → `ax-cluster` (id 3)   `redmine.AX_PROJECT_ID`
    게임·유틸 소스 일감 → `config.yaml` 의 `redmine.project`
                          (`ModularStage`→`modularstage` · `NS`→`ns` · `KimodoMotion_WebUI`→`kimodo`)

[중요] **종전 결정 「AX 일감은 `ModularStage`(id 1) 에 `[AX]` 접두어로 함께 둔다」(2026-08-09)는
폐기됐다.** 비UE 유틸 프로젝트(`kimodo`, `#693`)가 들어오며 AX 가 한 게임의 도구가 아니게 됐다
(사용자 2026-09-28: *"이참에 프로젝트도 나누자. 클러스터링과 kimodomotion"*).
이전 방식: 열린 `[AX]` 69건을 `ax-cluster` 로 옮겼고, **닫힌 것은 `modularstage` 에 기록으로 남는다.**
`[AX]` 접두어는 옮긴 뒤에도 제목에 그대로 있다.

[중요] **마일스톤 버전은 전체 공유(`sharing: system`)다** — `마일스톤 6 — 개선·확장` ·
`아이디어 — 추후 검토 수집` · `버그·개선` 은 `modularstage` 소속 그대로 공유로 바꿨다. 버전을 새로
만들어 쪼개면 M6 진행률이 두 벌이 된다. 닫힌 마일스톤(1~5)은 공유하지 않았다.
[주의] 위키 [[아이디어수집]] 과 `[아이디어]` 접두어 열린 이슈 7건은 **`modularstage` 에 남아 있다**
(이번 이전은 `[AX]` 만 — 옮길지는 미정).

[주의] **폴백하지 않는다** — `redmine.project` 가 없으면 등재를 거부하고 사유를 남긴다.
조용히 다른 프로젝트에 쓰면 그것이 오염이다(`#257` 이 요청 태그에서 내린 것과 같은 판단).

[주의] API 키는 저장소·`~/.config` 어디에도 없다. 마스터의 DB 에서 꺼낸다:
`docker exec redmine-db-1 psql -U redmine -d redmine -c "select value from tokens where action='api'"`
— [중요] **비밀이므로 문서·커밋에 값을 적지 않는다.**
