---
name: ax-review
description: 워커들이 올린 분산 작업 결과를 검수해서 main 에 반영할지 판단한다. "#N 리뷰", "일감 검토", "work <ID> 리뷰", "머지 검토", "검수 요청 받았어", "/review-work" 같은 발화에 발동. 파일 하나 봐 달라는 국소 코드 리뷰는 이게 아니다.
---

# ax-review — 올라온 작업을 검수한다 (요청자 측)

> 마스터가 생성해 배달한다. **손으로 고치지 말 것** — 다음 배달에 덮인다.

## 0. [중요] 먼저 — 이 스킬인지 아닌지 가른다

원전이 같은 혼동으로 값을 치렀다. 단어만 보고 오지 말 것:

| 발화 | 뜻 | 갈 곳 |
|---|---|---|
| `#N 리뷰` · `일감 리뷰` · `work <ID>` · `머지 검토` · `검수 요청 받았어` | 워커 결과를 **main 에 넣을지 판단** | [중요] **이 스킬** |
| `이 파일 봐 줘` · `이 변경 검토해 줘` · `취약점 봐 줘` | 국소 코드 품질 검토 — 머지 결정 없음 | 일반 코드 리뷰 |

신호가 없으면 **묻는다.** 추측으로 검수 절차를 돌리면 사람 시간만 버린다.

## 1. [중요] 이 자리가 무엇인가 — 원전의 「리더」다

원전에는 TD·팀장 같은 **리더 그룹**이 이 판단을 했다. 우리에겐 그 자리가 없어서
**요청자(이 기계)가 그 역할을 한다** (사용자 확정 2026-08-16). 근거는 이미 코드에 있다 —
마스터의 `pre-push` 가드가 거부하며 이렇게 말한다: *"main 을 옮기는 것은 사람의 자리다 —
요청자(.33)에서 한다."*

    한다        시뮬레이션 통합 · UE5 빌드 · 승인/반려 판단 · main 반영 · Redmine 통지
    [중요] 안 한다   사람의 워킹트리에서 브랜치 전환 · 브랜치 삭제 · force push

## 2. 도구는 배달돼 있다 — 두 층이다

**MCP 도구 (ax-client — `.mcp.json` 에 등록돼 있다):**

    list_works(status?)      큐의 work 목록 — 검수 대상은 보통 ready_for_review
    get_work(work_id)        work 메타 + tasks 전체. 반환 그대로 review 인자에 넣는 모양
    redmine_note(...)        레드마인 코멘트 (마스터 경유 — 키는 이 PC 에 없다)

[중요] **결정(반려·승인) 도구는 MCP 에 없다 — 일부러 없다.** 결정은 아래 review 모듈이
검증된 절차(통째 중단·confirm 게이트)로만 한다. 절차는 한 벌뿐이어야 한다.

**파이썬 모듈 (git·빌드가 필요한 작업):**

    py -c "import sys; sys.path.insert(0,'.ax/lib'); from axmaster.work import review, build_local"

[중요] **`python` 이 아니라 `py` 다** — 이 PC 의 `python` 은 스토어 스텁이라 버전도 안 찍는다.
배달본은 저장소 배치의 미러다(`master/` → `axmaster/`). **손으로 고치지 말 것** — 다음 배달에 덮인다.

review 의 큐 호출자는 클라 MCP 모듈이 준다:

    from axmaster.clientside.client_mcp import queue_api
    review.reject_work(..., api=queue_api())

자격은 `.ax/token`(requester 역할 토큰 — 검수 경로만 열린다, 스코프 밖은 403)이고 마스터가
배달한다. [미구성]/[미연결]/[자격]/[스코프] 오류가 나오면 그 문장의 조치를 따른다.

## 3. 검수 — [중요] 사람의 트리를 건드리지 않는다

    review.review_work(repo, work_id=..., work=..., tasks=..., build_fn=...)

이것이 하는 일: `<체크아웃 옆>/ax-review-<work_id>` worktree 를 **원격 main** 위에 세우고,
feature(골조·글루) + **verified durable 집합**을 순서대로 머지한 뒤 요약을 낸다.
**어디에도 push 하지 않는다.**

[중요] **원전은 이 자리에서 `git stash` + `checkout main` 을 한다. 우리는 안 한다.**
그 트리는 원전에선 서버의 것이었지만 여기서는 **사람이 편집 중인 트리**다. 실측(2026-08-16)
으로 이 PC 에 커밋 안 된 `.uasset` 이 있었고, 원전 방식이면 그것이 stash 로 들어갔다가
pop 실패 시 **로그 한 줄**로 끝난다. 바이너리는 되살릴 수 없다.

[주의] 통합이 **충돌하거나 verified 인데 durable 이 없으면 통째 중단**한다. 부분 머지를 남기지
않는다 — 그 상태로 빌드하면 무엇이 문제인지 알 수 없다.

## 4. 빌드는 여기서 돈다

이 PC 에 UE5 가 있으니 **검수 트리 위에서 바로 빌드**한다:

    cfg  = json.load(open(".ax/config.json", encoding="utf-8"))
    bfn  = build_local.local_build_fn(project=cfg["project"],
                                      ue5_cmd=cfg["backends"]["ue5_cmd"])
    res  = review.review_work(repo, work_id=..., work=..., tasks=..., build_fn=bfn)

[중요] **엔진 경로를 손으로 적지 않는다** — 마스터가 **프로브해서** `config.json` 에 넣은 값이다.
없으면 추측하지 말고 마스터에 배달을 다시 요청한다. [중요] `local_build_fn` 은 엔진을 못 찾으면
**만들 때 죽는다** — 검수를 절반 돌린 뒤 *"빌드는 못 했지만 통과"* 로 끝나는 것이 최악이다.

[중요] 판정은 **로그 파싱**이다 — 종료 코드는 양방향으로 틀린다(`Build.bat` 이 **실패해도 0** 을
낸 실측이 있다). 타임아웃·실행 실패도 통과가 아니다: **확인 못 한 것과 통과한 것은 다르다.**

빌드가 실패하면 도구가 Redmine 코멘트 **본문을 만들어 둔다.** 보내는 것은 §7.

## 5. 승인 — [중요] 사용자의 승인 발화가 있고 나서

    review.finalize_work(repo, work_id=..., work=..., tasks=..., reviewer=..., confirm=False)

**`confirm=False` 가 기본이다.** 통합만 하고 **트리를 남긴 채** 실행할 명령을 돌려준다.
사용자가 *"승인"* 이라고 말한 **뒤에** `confirm=True` 로 다시 부른다.

[중요] 그때도 `main` 브랜치를 갈아타지 않는다 — worktree 에서 `HEAD:main` 으로 push 한다.
[주의] 그래서 **이 PC 의 로컬 `main` 은 그대로다.** 끝나면 사람이 `git pull` 하면 된다.

**push 가 거부되면 밀어내지 않는다.** 통합 결과는 그 트리에 그대로 있고 잃은 것이 없다.
사람이 판단한다.

## 6. 반려

    review.reject_work(repo, work_id=..., work=..., tasks=..., reviewer=..., reason=...)

큐 상태를 `rejected` 로 바꾸고 코멘트 본문을 만든다. [중요] **브랜치를 지우지 않는다** —
반려된 작업의 durable 은 `main` 에 도달하지 않으므로 **전부 보존**된다. 실패한 시도도
조사 자산이다(누적 모델).

반려를 **코드로 전하려면** `[FEEDBACK]` 블록을 그 자리에 박아 commit·push 한다 —
골조의 `[PSEUDO]` 와 같은 자리, 같은 방식이다. 큐의 텍스트만으로는 워커가 **어디를**
고칠지 모른다. [중요] 재구현이 아니라 **수정**이다.

## 7. Redmine 은 마스터를 거친다

MCP 도구 `redmine_note(issue_id, notes, status_name?, done_ratio?)` 를 쓴다.

[중요] **API 키는 이 기계에 없다** — 마스터의 컨테이너 DB 에만 있다. 도구는 본문만 만들고
마스터가 대신 쓴다(사용자 결정 2026-08-16). 역할 토큰이 이 경로를 연다.

[주의] 상태 이름은 **이 Redmine 에 실재하는 것**만 듣는다 — 신규·진행·해결·검토·완료.
반려에 해당하는 상태는 **없으므로** 기본은 상태를 안 바꾸고 코멘트만 남긴다.
승인은 「해결」이다 — [중요] **「완료」로 닫지 않는다. 닫는 것은 사람의 판단이다.**

## 8. 정리는 명령만 준다

    plan = review.plan_branch_cleanup(repo, tasks=..., target_branch=...)
    plan.commands()      # git push origin --delete <ref> …

[중요] **우리가 지우지 않는다.** 기준은 **도달 가능성**이다 — `origin/main` 에서 도달 가능한
것만 삭제 후보다. 도달 불가면 그 커밋이 **거기에만 있을 수 있다.** 실측이 그 기준을 골라
줬다: 원격 attempt 4건이 전부 미도달이었고 일괄 삭제했으면 실패 시도 3건의 유일한 사본이
사라졌다.

명령을 사람에게 **보여 주고**, 실행은 사람이 한다.

## 9. [중요] 막히면 멈추고 묻는다

    통합 충돌 · verified 인데 durable 부재 · push 거부 · 빌드 실패 원인 불명

전부 **사람이 판단할 자리**다. 임의로 재시도하거나 우회하지 않는다.
