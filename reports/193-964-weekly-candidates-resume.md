# 193 — #964 주말 기각 후보 재개·파일 기준 캐시

2026-11-15 · Codex · 기존 Claude 작업을 같은 일감 worktree에서 인수.

## 사용자 지시와 범위

- 「인수인계서 확인해」 → 조회만 수행, 마스터 담당·워커 모드는 변경하지 않았다.
- 「964번 진행중이었어」 → T2 테스트 기대값 변경 승인 대기 상태를 알렸다.
- 「응」 → 옛 계약을 기대하는 테스트 2건을 새 확정 스펙으로 변경하도록 승인.
- 「커밋하고 배포해 재부팅해야 되는건가?」 → 커밋·배포 승인.
- Redmine #964의 앞쪽 초안과 확정 ax:spec은 다르다. 정본은 확정 스펙:
  codex 우선 순서는 유지, 기계 공용 파일 쿨다운, 산출물 주차·완료 상태,
  대상 파일 blob + input_hash 캐시·stale. 대상 밖 체인·워커 모드는 바꾸지 않는다.
- 등록 플랜 노트의 수행 방식 원문: 「응 등록하고 직접 진행해」.

## 시작 상태·기존 도구

- 운영 `/home/sim/ax-cluster`: main `bc566f0065d48222ce89d9992a8fcb65c9117e9a`,
  dirty는 이전 세션의 `docs/orchestrator-handoff.md` 하나.
- 일감 worktree HEAD `70c82b1db86f00c2db058da741e0f3d873394cf4`:
  gates.py·dismissal_candidates.py 미커밋. T1 파일 쿨다운은 이미 커밋됨.
- ax-handoff·ax-plan·ax-redmine·ax-deliver 기존 스킬과 MCP 사용.
- `plan_start_tool(964, project=AXCluster)` → `verdict:resume`, `ok:true`, `tasks:[T2]`.
- `issue_start_tool(964)` 응답 원문 필드:
  `ok:true`, `branch:issue/964`, `repo:/home/sim/ax-cluster/.ax-issues/964`,
  `checkout:/home/sim/ax-cluster`, `already:true`, `lock:already`,
  `start_rev:bc566f0065d48222ce89d9992a8fcb65c9117e9a`,
  `author:{client:codex-mcp-client,family:codex,authors:[claude,codex]}`.
  이 성공 응답에 `done`·`why` 필드는 없었다.
- 마스터 마지막 담당 기록 claude, 워커 모드 codex(source=state). 생존 판정은 아니다.
- 운영 `AXCluster/config.yaml`의 `batch.dismissal_candidates:false` 확인.

## 구현·커밋

- T1(선행 Claude): `70c82b1db86f00c2db058da741e0f3d873394cf4`.
- T2: `f8c10020eb21e88a4dfff577f2aa8e8f1f3ff813`.
  시작 시 week·started_at·complete:false를 원자 저장, 끝나면 complete:true·completed_at.
  게이트는 new/resume/done, 옛 마커는 완료 판단에 쓰지 않는다.
  중단 안내는 다음 주말이 아니라 다음 회차로 맞췄다(다른 배치 문구 유지).
- T3: `855f82353b2ffa420efd510ffbe14b612bf71df1`.
  새 항목에 file·source_blob 기록. 대상 blob + input_hash가 같으면 main이 전진해도 재사용.
  옛 항목은 기록된 main_sha에서 대상 blob을 읽어 재사용하고 원래 판정 main 기록을 보존한다.
  없는 파일·리비전은 재사용하지 않는다. 목록 stale도 동일 기준이며 LLM을 호출하지 않는다.
- 기존 테스트 2건은 사용자 승인으로 계약을 갱신했다.
  추가 회귀는 현재/옛 캐시의 무관 커밋 재사용, 입력만 변경, 대상 파일 삭제,
  옛 리비전 부재를 다룬다.

## 검사·실측 근거

작업 위치 `/home/sim/ax-cluster/.ax-issues/964`,
접두 `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B`.

- `-m unittest master.test_dismissal_candidates -v`: T2 12/12 rc0, T3 16/16 rc0.
  중단 뒤 저장된 첫 항목을 재판정하지 않고 같은 주말에 남은 항목 처리,
  완료 뒤 토·일 건너뜀·다음 주차 new 확인.
  임시 Git·가짜 판정기 조건이며 운영 LLM 성공의 실증이 아니다.
- `master/test_batch.py`: 69/69 rc0.
- `git diff --check`: rc0.
- T3 운영 캐시 읽기 전용 대조 rc0:
  repo `/home/sim/ax-cluster/AXCluster/repo`(읽기만 하는 색인 미러),
  main `bc566f0065d48222ce89d9992a8fcb65c9117e9a`, entries146 active348,
  reusable111 changed13 missing_target3 inactive19.
  `_load`·`_inputs`·`_blob`·`_entry_blob`만 호출했고 LLM·캐시 쓰기 없음.
- 전수: `master/test_*.py` 233파일 전부 rc0(`FULL PASS files=233`).
  공식 통합: `-m unittest discover -s tests/integration -p test_axcluster.py -f -v`
  → `Ran 207 tests in 256.369s`, `OK`, rc0.
  실행 `/tmp/ax-964-checks.sh`, Git 그룹 권한 제약을 피하도록 좁은 스크립트의
  샌드박스 해제 승인을 받았다. 로그 `/tmp/ax-964-check-results/`.

## 배포·실물 관측의 경계

- PC 전체 재부팅은 필요하지 않다. 상주 재기동은 `master.issue_wrapup 964`의
  서비스 신선도 판정 대상으로 한정한다. ax-batch·ax-review-queue는 oneshot이다.
- C5는 배포 뒤 관측인데 마감은 미확인 체크리스트를 거절한다.
  관측 요구를 유지하면서 배포 뒤 같은 일감 노트로 기록하는 순서에 대해 사용자 답을 요청했다.
  답 없이 C5 충족·제외를 기록하거나 마감 게이트를 우회하지 않는다.
- 실제 배치 관측·설정 복귀·배달 결과는 아직 이 문서 작성 시점에 실행하지 않았다.
- 세션 파일:
  `~/.codex/sessions/2026/11/15/rollout-2026-11-15T15-55-28-01a1ddfd-52b8-7b93-b84d-f828e5c08d9d.jsonl`.

최종 결과는 Redmine #964 마감 노트.
