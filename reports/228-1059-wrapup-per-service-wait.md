# 228 — 마감 정리가 상주마다 자기 oneshot 만 기다린다 (#1059)

#1050 마감 뒤 작업내역 분석에서 나온 일감이다. 사용자는 「모두 등록하자」로 #1055–#1060 을 등록했고 「1059부터 진행하자」로 착수했다.
`issue_start_tool`: `repo=/home/sim/ax-cluster/.ax-issues/1059` · `branch=issue/1059` · `start_rev=efc9117`.

## 무엇이 멈췄나

`master.issue_wrapup 1050` 1회차(18:09)가 900초 상한에서 rc 1 「재기동하지 않았다」로 끝났다. 재기동은 하나도 되지 않았다.

- 18:08:45 마감 push 가 `ax-indexer` 를 깨웠다(18:09:18). 색인기는 바뀐 파일을 agy 로 하나씩 다시 합성했다(파일당 52~165초).
  테스트 파일도 합성했다(test_tagging 86초 · 입력 40,001 토큰).
- ④는 재기동 대상 셋(`ax-task-queue`·`ax-broker`·`ax-projects`)이 기다리는 oneshot 의 **합집합**
  `['ax-dispatch','ax-indexer','ax-review-queue']` 이 모두 빌 때까지 아무것도 재기동하지 않았다.
- #922 의 의도는 상주마다 자기가 쓰는 oneshot 만 기다리는 것이었다(`WAIT_FOR`). `ax-projects` 는 기다릴 것이 없다.
  그런데 대상이 여럿이면 합집합으로 바뀌어 그 의도가 깨졌다. 기존 `test_wait_per_service_922` 는 대상을 하나씩만 봤다.

재현: 운영 코드 그대로 `test_issue_wrapup` 대역에 대상 셋을 두고 `ax-review-queue` 를 계속 돌렸다. 결과는 rc 1 · restart [] 이다.
운영 wrap1.log 와 같은 모양이다(스크래치패드 repro1059.py, 커밋 안 함).

## 고친 것 — `1202de4`

- `master/issue_wrapup.py` ④: 상주마다 `WAIT_FOR.get(t, ONESHOTS)` 만 본다. 매 틱마다 자기 oneshot 이 빈 상주부터 재기동한다.
- 상한을 넘기면 이미 재기동한 상주를 다시 판정하고 rc 1 로 끝난다. 이유에는 재기동하지 않은 상주와 재기동한 상주를 나눠 적는다.
  재실행하면 신선도 판정 때문에 남은 상주만 재기동된다.
- 전부 재기동하면 대상 전체를 다시 판정한다(종전과 같다).
- `docs/orchestrator-rules.md` §1.9 와 `ax-plan` SKILL 에 「상주마다」를 한 줄씩 보탰다.

## 검사

- `test_issue_wrapup` 46/46. 새 `test_wait_independent_1059` 는 7검사다.
  대상 셋 + 리뷰 큐·색인기를 계속 돌리면 projects·task-queue 는 재기동되고 broker 만 rc 1 로 남는다(이유에 broker).
  재실행하면 broker 만 재기동된다.
- `master.sweep` 249파일 13042/13043. 유일한 실패 `test_sandbox` 는 `AX_PROJECTS_ROOT` 미설정이었다.
  운영 유닛 값으로 다시 돌리면 38/38 이다. `test_mcp_servers` 86/0 · 공식 통합 223/223 · `test_skill_conventions` 54/54.
- 운영 실측(C4)은 이 일감의 마감 wrapup 이 새 코드로 도는 첫 회차다. 결과는 Redmine 마감 노트에 남긴다.

## 일감 밖으로 넘긴 것

- `master-local --check`(운영 체크아웃)가 FAIL 13/15 다. codex·agy 승인에 #1050 신규 도구 `wayfinder_node_start`·`wayfinder_node_submit` 이 없다.
  codex `--apply` 는 `~/.codex/config.toml` 의 ax-client 블록 뒤에 붙은 `[hooks.state.*]`(사람의 /hooks 승인)까지 걷어내는 편집이라,
  도구가 스스로 거절했다. 사용자 결정(질문 `c865506e2fd7`, 「1번으로 가자」): 손대지 않고 **#1061** 로 넘긴다.
- 비범위 부원인 둘은 그대로 남았다. 색인기는 테스트 파일까지 합성하고(#211 측정에서도 상위5의 41%), 범위 안 커밋마다 따로 합성해 같은 파일을 여러 번 합성한다
  (#1050: .py 16개 · 합성 약 27회 추정). 900초 값도 바꾸지 않았다.
- 관측만 했다: 질문 장부가 백그라운드 작업 알림을 사용자 입력으로 기록해 분류 답이 한 번 거절됐다. 일감으로 등록하지 않았다.

최종 결과는 Redmine #1059 마감 노트에 있다.
