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

## 10.1 레드마인 — **AX 인프라 이슈는 게임 프로젝트에 함께 둔다** (사용자 확정 2026-08-09)

`http://192.168.0.57:8080` · 마스터의 컨테이너(`redmine-redmine-1`, 8080→3000) · REST API 켜짐 ·
트래커 **`코드리뷰` 하나** · 상태 5종 · 우선순위 3종.

[중요] **AX 인프라 이슈를 따로 뗄지 물었고, 사용자가 "동일한 프로젝트" 로 확정했다** — AX 클러스터는
그 R&D 를 위한 도구이지 별개 산출물이 아니다. 그래서 **AX 일감은 `ModularStage`(id 1) 에 둔다.**
구분이 필요하면 제목 접두어 `[AX]` 만 쓴다(#21~#24 가 그 형태).

[중요] **그 결정은 「레드마인 프로젝트는 하나다」가 아니다** (정정 2026-08-24, 사용자 지적).
종전 이 절과 `redmine.py` 주석이 *"새 프로젝트를 만들지 말 것"* 이라고 **범위를 넓혀** 적었고,
그것이 상수(`PROJECT_ID = "modularstage"`)로 굳어 다중 프로젝트에서 깨졌다 — NS 의 통합 실패가
`ModularStage` 이슈로 등재됐다. **게임 프로젝트가 늘면 레드마인 프로젝트도 함께 늘고**, 게임
소스 일감이 어디로 갈지는 **`<트윈>/config.yaml` 의 `redmine.project`** 가 정한다(`#293`).

    AX 인프라 일감      → `ModularStage`  (`redmine.AX_PROJECT_ID` · 사용자 확정, 불변)
    게임 소스 일감      → `config.yaml` 의 `redmine.project`
                          (`ModularStage`→`modularstage` · `NS`→`ns`, 2026-08-24 신설)

[주의] **폴백하지 않는다** — `redmine.project` 가 없으면 등재를 거부하고 사유를 남긴다.
조용히 다른 프로젝트에 쓰면 그것이 오염이다(`#257` 이 요청 태그에서 내린 것과 같은 판단).

[주의] API 키는 저장소·`~/.config` 어디에도 없다. 마스터의 DB 에서 꺼낸다:
`docker exec redmine-db-1 psql -U redmine -d redmine -c "select value from tokens where action='api'"`
— [중요] **비밀이므로 문서·커밋에 값을 적지 않는다.**
