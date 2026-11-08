# 142 — #906 일감 작업 저장소 복귀 · 색인 미러 봉인 · Codex 수행 문제 대조

2026-11-08 · Claude · 일감 http://192.168.0.57:8080/issues/906 (연관 #905·#893)

## 1. 결론

#906 은 「Codex 가 설정 경로(`track.local_clone`)를 무시하고 새 경로를 하드코딩했다」는 전제로
등록됐다. 실제 소스·설정과 대조하니 **그 설정 경로가 작업 위치로 쓰면 안 되는 곳**이었고, 그 전제로
만든 #905 정정 커밋 `6a0a201` 이 main 에 배포돼 #893 마감을 막고 있었다. 가장 큰 문제는 Codex 의
행동이 아니라 **배포된 `6a0a201`** 이었다.

## 2. 근거 — `AXCluster/repo` 는 색인기의 ff 전용 미러다

- `track.local_clone: repo` 는 색인기(`master/events/consumer.py`)가 소스를 받는 클론이다.
  `consumer.py` 주석: *"마스터는 이 클론에 커밋하지 않으므로 항상 fast-forward 여야 하고, 아니라면
  그건 알아야 할 사고"*. 매 회차 `fetch --prune` → `merge --ff-only FETCH_HEAD`.
- `origin` push URL 은 `DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1`,
  `.git/hooks/pre-push` 는 `attempt/*`·`task/*` 외(main 포함)를 막는다 — 의도된 봉인이다.
- Codex 자신도 #905 15:39 노트에 *"색인용 repo를 임의로 편집하지 않는다"* 고 썼고, 8분 뒤 T4 에서
  그 클론을 일감 작업 위치로 연결했다.

## 3. `6a0a201` 이 실제로 만든 것 (실측)

| 증상 | 근거 |
|---|---|
| #893 마감 push 실패 | `issue_finish_tool(893, confirm=True)` → step push rc128 `remote-DISABLED` |
| 미러가 main 추적 중단 | 현재 브랜치 `issue/893` 에 upstream 없음 → `FETCH_HEAD` 두 줄 모두 `not-for-merge` → git 2.34 가 첫 줄(옛 `issue/900`)을 머지 → "Already up to date" 로 조용히 통과 |
| 미병합 커밋 색인 | `config.yaml` `last_indexed_commit`·`analyzed_commit` = `c62b2fb`(당시 origin/main 에 없음), 01:18 재색인 463건 |
| 작업 유실 위험(추론) | 일감 브랜치 첫 커밋 전 dirty 상태에서 ff 가 깨지면 `_recover_mirror` 가 `reset --hard FETCH_HEAD` 조건(미러에만 있는 커밋 0 · dirty)에 해당한다. 발생하지는 않았다 |

## 4. 한 것 (사용자 결정 2026-11-08: 운영 저장소 복귀 · #893 보류 · 이 세션에서 repo 직접 지정)

1. `#906` 시작 — 현 MCP 가 미러에 브랜치를 세우므로 `issue_flow.start(906, repo=/home/sim/ax-cluster)` 직접 호출.
   Codex 의 미커밋 인수인계서는 stash 로 옮겨 `issue/906` 에서 되살렸다.
2. **T1 `201a81a`** — `default_repo()` 를 운영 저장소 `REPO` 로 복귀. `_sealed()` 추가: `origin` push URL 이
   `DISABLED` 면 `start`·`finish` 가 브랜치·push 전에 거절한다(문서가 아니라 코드가 막는다).
   MCP `issue_*` 설명·`ax-plan` 스킬의 「`track.local_clone` = 작업 저장소」 문구 정정.
   `test_issue_flow` 150/150(신규 6건). 전수 213파일 10726/10727 — 실패 1건은 미커밋 인수인계서의
   「바로 다음 작업」 절 누락(T4 대상, 코드 무관).
3. **T2** — #893 보류(미러 → main) → `c62b2fb` 를 운영 저장소로 같은 해시로 이관 → #906 보류 →
   #893 재개·마감: origin/main = `c62b2fb`(ff), 마감 r1(R267)·완료 100. **해시를 유지한 이유**: 색인 커서가
   `c62b2fb` 라서, rebase 로 해시가 바뀌면 커서가 영원히 main 의 조상이 못 된다(`consumer.py` 의
   "커서가 이 이력의 조상이 아니다 — 사람이 봐야 한다"에 멈춤).
   **신호 수신 확인**(#893 승인 범위): push 2초 뒤 10:23:52 `ax-indexer` 이벤트 1건 `6a0a2013→c62b2fb1`,
   미러 HEAD = origin/main, 커서 일치. `deliver AXCluster` rc0 3/3. 이어 #906 재개·main merge `f321141`.

## 5. Codex 수행 문제 대조 (#906 본문 1~7)

| # | 내용 | 실제 원인 | 대응 |
|---|---|---|---|
| 1~3 | 설정 무시·하드코딩·역할 혼동 | 「설정 필드가 있다」를 「작업 위치다」로 읽고 그 필드의 **소비자**(consumer.py)와 봉인(pushurl·훅)을 판단에 넣지 않았다. 사용자 지적 뒤 정정이 반대 방향(미러)으로 갔다 | **코드 강제**: `_sealed()` 거절 + 회귀 검사 |
| 4 | 금지된 임시 Git 검사 재제안 | 「드라이런 실패」의 실체는 Codex 기본 샌드박스가 `sg gitea` 를 막아(`Cannot open audit interface`) `test_source_scope` 가 28/32 가 된 것. 리포트 86 에 같은 수치로 이미 기록돼 있었다. Claude(샌드박스 밖)에선 32/32 | `~/.codex/AGENTS.md` 문구를 원인·실측으로 정정(사용자 지시) |
| 5 | 잘못된 전제의 편집을 태스크 완료로 기록 | `plan_transition` 의 완료 근거는 텍스트면 통과한다 — 「편집 완료」도 근거로 받는다 | 기록. 근거 품질 관문은 코드화 여부를 사용자와 정할 것(제안만) |
| 6 | 같은 질문·사과 반복, 일본어 메시지 | 행동 문제, 코드로 막을 자리가 없다 | 기록 |
| 7 | 미확인 경로 조회·cwd 경합·패치 오타 | 절차 실수 | 기록 |

추가로, Codex 인수인계서는 다음 작업으로 *"기존 작업 저장소의 쓰기·main 반영 계약을 바로잡는다"* 를
적었다 — 따랐다면 다음 세션이 미러의 봉인을 여는 쪽으로 갔을 것이다. 인수인계서도 이 리포트 기준으로 다시 썼다.

## 6. 남은 것 (결정은 사용자)

- **#905 원래 문제 재개방** — 운영 체크아웃에서 작업하면 1분 주기 oneshot 서비스가 미커밋 코드를 실행한다.
  이번 복귀로 다시 열렸다. 별도 일감으로 사용자와 방식(① worktree · ② 고정 배포본 · ③ 경고) 결정.
- 미러에 남은 `issue/893` 브랜치 — 팁이 main 에서 도달 가능(잃을 것 없음). 삭제는 확인 후.
- `/home/sim/ax-issues/905` 초안 worktree(detached `6a0a201`) — 보존 중.
- `plan_transition` 완료 근거 품질 관문 — 아이디어 단계.
- `ax-projects` 재기동 — #906 main 반영 때 함께(MCP 의 `default_repo` 가 그때 바뀐다).
