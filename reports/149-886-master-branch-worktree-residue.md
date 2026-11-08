# 149 — #886 마스터 로컬 브랜치·worktree 잔재 정리와 열거 빈틈

> 2026-11-08 · Claude · 일감 #886 · 시작 리비전 `eff4ca6` · 작업 위치 `.ax-issues/886`(`issue/886`)

## 사용자 지시·결정

- 「#886 진행해」 → `plan_start` 판정 `plan_needed` → RAG(request_id `37f5884a1c504999bb901a0dfb1762c1`)와
  현재 Git·`cleanup machines` 열거를 대조한 뒤 네 가지를 물었다. 사용자는 모두 추천안을 골랐다.
  1. 병합 잔재(fix/R* 8 · worktree 2) **전부 삭제**
  2. 미병합 증거 3개 **보존 ref 후 정리** — 기존 `refs/ax/pruned` 이름공간을 쓴다
  3. `ax-896-local` 미커밋 초안 **diff 보관 후 제거**
  4. `cleanup machines` 열거 빈틈 **이번에 고침**(읽기 전용 유지 · 자동 삭제 없음)
- 삭제 직전 13건 목록을 다시 보여 주고 「응 13건 삭제 진행해」로 실행했다.

## 재조사 (T1, 11-08 · main=origin/main=`eff4ca6`)

| 대상 | 상태 | 처분 |
|---|---|---|
| `fix/R25·27·30·43·48·54·56·57` | 전부 `branch --merged main` | `branch -d` |
| worktree `ax-900-local` `e41b53e` | main 포함 · 변경 0 · ignored `.ax/` | `worktree remove` |
| worktree `ax-advance-20261018_1728_831_…4a7db0e4` `95693c0` | main 포함 · 변경 0 · ignored `.ax/` · work merged | `worktree remove` |
| worktree `ax-788-work` `b510d2f` | main 밖 8 · 다른 ref 없음 · 리포트 107 증거 | 보존 ref → `worktree remove` |
| `task/20261010_0335_…774…/base` `cfd986a` | 반려 work · 고유 1 · #821 보존 | 보존 ref → `branch -D` |
| `task/20261010_1538_…780…/base` `c7ede9e` | 취소 work · 고유 1 | 보존 ref → `branch -D` |
| worktree `ax-896-local` `fed2dc5` | 수정 3 · 미추적 1(11-07 16:31~41) | diff 보관 → `worktree remove --force` |

- 일감 본문(11-05)과 다른 점: `/tmp/ax-234-cleanup` 죽은 등록은 이미 없었다. `ax-896-local`·`ax-900-local` 은 그 뒤 생겼다.
- `ax-896-local` 초안: 추가 22줄 중 21줄이 이미 main 에 있고, 남은 1줄은 #907 이 바꾼 마감 안내 문구다.
  미추적 리포트 138 은 main 의 같은 파일과 바이트 동일하다 — #896 의 마감 전 초안으로 판단했다.
- 범위 밖(손대지 않음): `AXCluster/repo` 미러의 `/tmp/ax-pinned-k8fzn012/tree`(54b5632)·`ax-review-20261010_1742_788_1_46881e71`, 원격 `origin/issue/900`.

## 처리 (T2·T3·T4)

- 보존 ref(마스터 로컬, push 안 함):
  - `refs/ax/pruned/worktree/ax-788-work` = `b510d2f6dd6d91e07c79a63f0a0ee47a2addc5ba`(main 밖 8)
  - `refs/ax/pruned/task/20261010_0335_777_2_mkdtemp_774_5078e6e6/base` = `cfd986ad0ec1aa6b74eebee78b39617a7e0c2be6`
  - `refs/ax/pruned/task/20261010_1538_777_2_mkdtemp_780_c88dcb7f/base` = `c7ede9e2659038f86beaadec0191e0b97487a87b`
  - 복구: `git -C /home/sim/ax-cluster worktree add --detach <경로> refs/ax/pruned/worktree/ax-788-work`,
    `git -C /home/sim/ax-cluster branch <이름> refs/ax/pruned/task/<W>/base`
- 896 초안 보관: `reports/research/2026-11-08-886-ax-896-local-draft.patch`(277줄). 원 트리에서 `git apply --check -R` 통과.
  복구: `git worktree add --detach <경로> fed2dc5 && git -C <경로> apply <파일>`.
- 삭제 13건 전부 rc0. 처리 뒤 `refs/heads` = `main`·`issue/886`, worktree = 운영 저장소·`.ax-issues/886`,
  `worktree prune --dry-run` 대상 0, 운영 main=origin/main=`eff4ca6` 깨끗함.
- `git worktree remove` 는 ignored 파일만 있는 트리를 `--force` 없이 지웠다(ax-900-local·ax-advance·ax-788-work).

## 재발 경로와 열거 수정 (T5)

- 잔재가 쌓인 경로: `fix/R*` 는 이름으로 보아 리뷰 지적(R번호) 처리용 로컬 브랜치가 머지 뒤 남은 것(만든 경로는 확인하지 않았다), `ax-*-local`·`ax-788-work` 는
  #907 이전(운영 저장소 옆) 손 worktree, `ax-advance-*` 는 ⑦ 전진 트리다. #907 이후 일감 브랜치·worktree 는
  `issue_finish` 가 지운다 — 새 일감 경로에서는 같은 축적이 줄어든다.
- 빈틈: `cleanup.scan_repo(local_branches=True)` 가 `refs/heads/task`·`attempt` 만 열어, 병합된 `fix/R*` 8개가
  `cleanup machines` 에 한 줄도 나오지 않았다.
- 수정(`master/work/cleanup.py`): `refs/heads` 전부를 연다. 기준 브랜치·worktree 소유 브랜치 제외,
  `task/`·`attempt/` 는 종전 큐 대조, `issue/<N>` 은 늘 「볼 것」(보류 중이면 main 에 도달해도 지우면 안 된다),
  그 밖은 도달 판정(도달 → 후보 · 아니면 볼 것 + 고유 커밋 수). 쓰기 명령 0 은 그대로다.
- 회귀(`master/test_cleanup.py` `test_machine_scan_other_local_branches_886`): 실제 git 저장소에서 병합 fix → 후보,
  미병합 fix → 볼 것·고유 1, main 에 도달한 `issue/9` → 볼 것, 기준 브랜치 제외, worktree 소유 `issue/10` 은
  worktree 줄에서만, 쓰기 명령 0.
- 자동 삭제는 넣지 않았다(사용자 결정). 정리는 지금처럼 열거 → 사람 승인 → 손 실행이다.

## 검증

- `test_cleanup` rc0 **90/90**(기준 main 84/84 + 신규 6).
- 정적(`pystatic.run_static`, 기준 `eff4ca6`, 2파일): pyflakes 차단 0·노트 1(기존 f-string), import 차단 0,
  mypy 차단 0·비차단 노트(기존 줄). `git diff --check` rc0.
- 새 코드로 운영 저장소 `scan_repo(local_branches=True)`: 볼 것 1(작업 중 `.ax-issues/886`) · 후보 0.
- 공식 통합(정본 명령, worktree): rc0 **`Ran 188 tests in 166.725s`·`OK`(188/188)**.
- 사용자 「응 결과 나오면 커밋하고 마감까지 진행해」 — 커밋·마감 승인. 배달·재기동은 이 승인에 없다
  (`cleanup` 은 상주 서비스가 아니라 CLI 라 재기동 대상이 아니다).

최종 결과는 Redmine 마감 노트.
