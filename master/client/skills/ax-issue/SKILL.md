---
name: ax-issue
description: Redmine 일감(`#N`) 하나를 이 기계에서 구현할 때 쓴다 — 플랜 영역을 확인·등록하고, 사람 작업 트리 옆 git worktree 의 `issue/<N>` 브랜치에서 작업하고, 승인 뒤 `origin main` 에 fast-forward 로 올린 다음 마스터에 마감을 등록한다. 시작·보류·재개·취소도 이 스킬이다. "#N 진행해", "#N 시작하자", "일감 이어서", "다음 태스크", "#N 마치자", "#N 보류", "#N 취소", "플랜 짜자", "/ax-issue" 같은 발화에 발동. Claude·Codex 공용. [중요] 분산 작업(워커에게 맡기는 work)은 이게 아니다 → `ax-request` · `ax-advance` · `ax-review`.
---

# ax-issue — Redmine 일감 하나를 worktree 에서 하고 마감을 등록한다 (요청자 측)

> 마스터가 생성해 배달한다. **손으로 고치지 말 것** — 다음 배달에 덮인다.
> 일감 `#884` T6 · 마스터 쪽 같은 규칙: `master/issue_infra.py` · 플랜 본체 `master/plan_tools.py`

## 0. [중요] 먼저 — 이 스킬인지 가른다

| 발화 | 뜻 | 갈 곳 |
|---|---|---|
| `#N 진행해` · `#N 시작하자` · `#N 이어서` · `다음 태스크` · `#N 마치자` · `#N 보류` · `#N 취소` | **Redmine 일감 하나를 이 기계에서 직접 구현** | [중요] **이 스킬** |
| `일감 등록` · `작업 요청해줘` · `워커한테 시켜` · `골조 확인` | 분산 작업(work)을 마스터에 등재 | `ax-request` |
| `라운드 종결` · `전진시켜` | 분산 작업의 작업 브랜치 전진 | `ax-advance` |
| `[리뷰 요청]` 이슈 · `머지 검토` · `검수 요청 받았어` | 분산 작업을 `main` 에 반영할지 | `ax-review` |
| `R12 검토` · `P3 수정` | 자동 리뷰·플랜 수정 항목 | `ax-fix` |

[주의] **`#N` 이 분산 작업의 `[리뷰 요청]` 이슈인지, 사람이 구현할 일감인지 먼저 확인한다.** 분산 작업
이슈는 `work_id` 가 붙어 있다(`redmine_get_issue` 로 본문을 본다). 애매하면 묻는다.

## 1. 도구 — `ax-client` MCP (마스터 8101 대행)

    plan_start(issue_id)                                 시작 판정 + 7단계 표 (읽기)
    plan_set(issue_id, tasks, why)                       플랜 등록·태스크 추가/편집
    plan_transition(issue_id, task_id, to, note)         상태 전이 — 상태를 바꾸는 유일한 쓰기
    issue_start(issue_id, check_only=true)               판정·잠금 점검만 (쓰기 0)
    issue_start(issue_id, branch, start_rev)             시작 기록 — 잠금 · Redmine 시작 리비전 노트
    issue_finish(issue_id, base, end, hashes, subjects)  마감 기록 — push **뒤에** 부른다
    issue_pause(issue_id, end)                           보류 기록 — 잠금 보류 · 노트
    issue_cancel(issue_id, confirm, delete_branch, …)    취소 — 기본은 미리보기

[중요] **도구는 기록만 한다 — git 은 이 기계에서 아래 명령으로 한다.** 인프라는 이 기계의 저장소를
만지지 않는다. 프로젝트 태그는 `ax-client` 가 `.ax/config.json` 에서 붙인다.
[중요] **잠금·추적 파일을 손으로 고치지 않는다** — 그 파일은 마스터 트윈에 있고, 거절은 고칠 자리가
아니라 보고할 자리다(§8).

## 2. [중요] 이 기계의 자리 — 사람 작업 트리는 건드리지 않는다

여기는 사람이 쓰는 기계다. 체크아웃(`$repo`)에는 커밋되지 않은 `.uasset`·소스가 있을 수 있다.

- **브랜치 전환·`reset`·`stash` 를 `$repo` 에서 하지 않는다.** 모든 작업은 옆 디렉토리 worktree
  (`$wt`)에서 한다. `$repo` 에서 쓰는 것은 `fetch`·`worktree add/remove`·`branch -d` 뿐이다.
- 게임 소스(`Source/**` · `*.uproject` · `Config/*.ini` · `Content/**`)를 고치기 전에 **계획을 말하고
  동의를 받는다**(`ax-request` §0.05 와 같은 규칙). 빌드·에디터 실행도 같다.
- 커밋은 사용자에게 묻고 한다. push·브랜치 삭제는 아래 승인 지점에서만 한다. **강제 push 는 없다.**

PowerShell 기준 변수(체크아웃 루트에서):

    $N    = <일감 번호>
    $repo = (git rev-parse --show-toplevel)
    $name = Split-Path $repo -Leaf
    $wt   = Join-Path (Split-Path $repo -Parent) "$name-issue-$N"
    $br   = "issue/$N"

## 3. 시작 — 플랜이 먼저다

1. `plan_start($N)`. `ok: false` 면 **구현하지 않는다.** 응답의 `next_action` 이 할 일이다.

        no_spec          스펙(무엇을·완료 조건)을 사용자와 먼저 쓴다
        plan_needed      ↓ 1-1 — 플랜을 짠다
        plan_invalid     형식 오류를 보여 주고 본문을 함께 고친다
        plan_violations  규칙 위반을 보여 주고 함께 고친다
        blocked          차단 사유·대기 선행을 보고하고 멈춘다
        plan_done        태스크는 끝났다 — 일감 완료는 스펙·승인 규칙으로 따로 판단한다
        resume · next    3 으로 간다

   1-1. 플랜 짜기: `search_context`(task_type=`user_command`, user_request=사용자 원문)로 기존 설계를
   찾고 **현재 소스와 대조한 뒤** 작은 태스크(목표·대상·선행·검증)를 **사용자와 대화로** 정한다.
   합의된 목록을 `plan_set` 으로 등록한다(`why` = 사용자 결정). `state`·`evidence` 는 넣지 않는다.

2. `issue_start($N, check_only=true)`. `ok: false` 면 §8 대로 보고하고 멈춘다. `lock_state` 가
   `paused` 면 §6-2(재개)로 간다.

3. worktree 를 만든다 — 이미 있으면 만들지 않는다:

        git -C $repo rev-parse --verify --quiet "refs/heads/$br"     # 출력이 있으면 브랜치가 이미 있다 → 멈추고 묻는다
        Test-Path $wt                                                 # True 면 멈추고 묻는다
        git -C $repo fetch origin main
        git -C $repo worktree add $wt -b $br origin/main
        $rev = git -C $wt rev-parse HEAD

4. `issue_start($N, branch="issue/$N", start_rev=$rev)`.
   - `ok: true` → 잠금이 잡히고 Redmine 에 시작 리비전이 남았다.
   - `ok: false` → 사유를 보고한다. 방금 만든 worktree 는 `origin/main` 그대로라 잃을 것이 없다 —
     지울지 사용자에게 묻고, 승인되면 `git -C $repo worktree remove $wt` · `git -C $repo branch -d $br`.

5. 첫 태스크를 `plan_transition($N, "T1", "작업중")` 으로 옮기고 `$wt` 안에서만 작업한다.

## 4. 진행 — 태스크마다 마킹한다

- 손대기 **전에** `작업중`, 끝나면 `완료` + `note` 에 근거(커밋 해시·검사 결과). 근거 없는 완료는 거절된다.
- 막히면 `차단` + 사유, 범위 밖이면 `해당없음` + 사유. 응답의 `next` 가 다음 판정이다.
- 커밋은 `$wt` 의 `$br` 에 쌓는다(`git -C $wt add …` · `git -C $wt commit …` — 사용자에게 묻고).

## 5. 종료 — 승인 뒤 `main` 에 fast-forward, 그 다음 등록

1. 점검 (어느 하나라도 어긋나면 멈추고 보고한다 — 고치지 않는다):

        git -C $wt status --porcelain                                 # 비어 있어야 한다
        git -C $wt fetch origin main
        git -C $wt merge-base --is-ancestor origin/main $br           # $LASTEXITCODE 0 이어야 한다
        $base   = git -C $wt merge-base origin/main $br
        $end    = git -C $wt rev-parse $br
        $hashes = @(git -C $wt log --reverse --format=%H "$base..$end")
        git -C $wt log --reverse --format="%H %s" "$base..$end"       # 사용자에게 보일 목록

   `--is-ancestor` 가 실패하면 `origin/main` 이 앞서 나간 것이다 — **rebase·머지는 사람이 정한다.**
   `$hashes` 가 비면 마칠 것이 없다.

2. [중요] **승인을 받는다.** 한 번에 보여 줄 것: 범위 `$base..$end` · 커밋 목록 · 바뀐 파일 수
   (`git -C $wt diff --stat $base $end`) · 이어서 할 일(아래 3~5: push · 마감 등록 · worktree 제거 ·
   로컬 브랜치 삭제). 승인 없이 push 하지 않는다.

3. push — fast-forward 만:

        git -C $wt push origin "${br}:main"

   거절되면 멈추고 출력 원문을 보고한다. `--force` 는 쓰지 않는다. 로컬은 그대로라 잃을 것이 없다.

4. `issue_finish($N, base=$base, end=$end, hashes=<$hashes 순서대로>, subjects=<같은 순서의 제목>)`.
   - `ok: true` · `registered: true` · `lock_released: true` → 마감 등록 완료. 5 로 간다.
   - `registered: false` → 잠금이 남아 있다. `why` 를 보고한다. 같은 인자로 다시 부르면 같은 범위는
     `already` 로 처리된다. worktree 는 등록이 될 때까지 남겨 둔다.
   - 그 밖의 `ok: false`(링크·노트 실패 등) → `done`·`why` 를 그대로 보고한다.

5. 정리 — 브랜치가 `origin/main` 에서 도달 가능할 때만 지운다:

        git -C $repo fetch origin main
        git -C $repo merge-base --is-ancestor $br origin/main         # $LASTEXITCODE 0 이어야 한다
        git -C $repo worktree remove $wt
        git -C $repo branch -d $br

   `branch -d` 가 거절하면(사람 트리의 HEAD 기준 판정) 멈추고 묻는다 — `-D` 는 사용자가 정한다.

해시별 커밋 리뷰와 종합 리뷰 결과는 리뷰 큐가 같은 일감에 노트로 남긴다. 기다리지 않고 다음
일감으로 가도 된다(잠금은 이미 풀렸다).

## 6. 보류·재개

### 6-1. 보류 — 잠금을 풀고 worktree·브랜치는 남긴다

    git -C $wt status --porcelain        # 비어 있어야 한다 (미커밋 변경이 있으면 커밋할지 사용자에게 묻는다)
    $end = git -C $wt rev-parse HEAD

`issue_pause($N, end=$end)`. 보류 중에는 다른 일감을 시작할 수 있다.

### 6-2. 재개

`issue_start($N, check_only=true)` 의 `lock_state` 가 `paused` 이고 `$wt` 가 있으면:

    $rev = git -C $wt merge-base origin/main $br

`issue_start($N, branch="issue/$N", start_rev=$rev)` → `resumed: true`. 잠금 기록의 시작 리비전이
유지된다. `$wt` 가 없으면 멈추고 묻는다(`git -C $repo worktree add $wt $br` 로 다시 세울지).

## 7. 취소 — 미리보기, 승인, 그리고 브랜치 삭제는 따로 승인

1. 목록을 만든다:

        $commits = @(git -C $wt log --reverse --format="%H %s" "origin/main..$br")
        $local   = @(git -C $repo log --format=%H "origin/main..$br" --not --remotes)

2. `issue_cancel($N, commits=$commits, local_only=$local)` — 미리보기(쓰기 0). `warning` 이 있으면
   **원격에 없는 커밋은 브랜치를 지우면 되살릴 수 없다** 는 사실과 그 목록을 사용자에게 보인다.
3. 취소 승인을 받으면 `issue_cancel($N, confirm=true, commits=…, local_only=…)` — 잠금 해제·「취소」 노트.
   브랜치 삭제까지 **별도로** 승인받았으면 `delete_branch=true` 를 함께 싣는다.
4. 응답의 `branch_delete_allowed` 가 `true` 일 때만 지운다:

        git -C $wt status --porcelain        # 비어 있지 않으면 멈추고 묻는다
        git -C $repo worktree remove $wt
        git -C $repo branch -D $br

   노트가 실패했으면(`ok: false` · `step: redmine`) 지우지 않는다 — 커밋 목록이 어디에도 안 남는다.

## 8. 거절·실패 — 보고하고 묻는다

| 응답 | 뜻 | 할 일 |
|---|---|---|
| `status: no_project_tag` | 이 체크아웃의 `.ax/config.json` 에 프로젝트가 없다 | 보고 — 배달 문제다. 우회하지 않는다 |
| `status: not_mounted` | 마스터의 마운트가 이 프로젝트가 아니다 | 보고하고 묻는다. 마운트 전환은 사람이 정한다 |
| `step: plan` | 플랜 판정이 ok 가 아니다 | §3-1 로 |
| `step: lock` · `#M 작업이 진행 중이다` | 다른 일감이 활성이다 | 그 문장을 보이고 #M 를 완료·보류·취소 중 무엇으로 할지 묻는다 |
| `step: lock` · `잠금 상태를 못 읽었다` | 마스터의 잠금 파일을 못 읽는다 | 보고 — **파일을 손으로 고치지 않는다** |
| `step: span` | 보낸 해시·범위 형식이 어긋났다 | §5-1 명령 출력을 다시 확인하고 보고 |
| `step: redmine` | Redmine 기록 실패 | `why` 를 보고. 시작이면 잠금이 안 잡혔다 |
| `status: plan_refused` | 플랜 규칙 거절(근거 없는 완료·선행 미완 등) | 사유를 보이고 함께 고친다 |
| git 명령 실패 | — | 출력 원문을 보고하고 멈춘다. 고쳐서 이어 가지 않는다 |

## 9. 일감을 「완료」로 닫을 때

`redmine_note(status_name="완료")` 는 마스터의 관문을 지난다. 그 일감의 종합 리뷰가 끝나지 않았거나
결정되지 않은 HIGH 지적이 있으면 `[주의] … 완료 거절` 로 아무것도 쓰이지 않는다. 사유 문장의 지적을
실제 코드와 대조해 버그면 고친 뒤 `applied`, 오탐·의도면 `update_fix_status(dismissed, note=사유)` —
어느 쪽인지는 사용자와 정한다. 태스크가 전부 완료돼도 일감을 닫는 것은 별도 판단이다.

## 10. 이 스킬이 바꾸지 않는 것

분산 작업의 등재·전진·마감(`ax-request` · `ax-advance` · `ax-review` → `finalize`)과 그 사람 게이트,
게임 소스 동의 규칙, 커밋 승인 규칙은 그대로다. 이 스킬의 `main` 반영은 **일감 브랜치 하나의
fast-forward** 뿐이고, 분산 작업의 `main` 머지와 다른 경로다.
