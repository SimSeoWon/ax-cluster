# 229 — master-local 이 사람의 Codex /hooks 승인을 지우려다 막히던 것 (#1061)

#1059 마감 중에 나온 일감이다. 사용자 결정 `c865506e2fd7`(「1번으로 가자」)로 #1059 밖으로 넘겼고, 「1061부터 진행하자」로 착수했다.
`issue_start_tool`: `repo=/home/sim/ax-cluster/.ax-issues/1061` · `branch=issue/1061` · `start_rev=c8b9ed0`.

## 증상과 원인

#1050 마감 뒤 `master.client master-local --check` 가 FAIL 13/15 였다. codex·agy 승인 목록에 #1050 신규 도구
`wayfinder_node_start`·`wayfinder_node_submit` 이 없었다. `--apply` 의 codex 편집은 「관리 대상 MCP 승인 밖의 설정이 바뀌는 편집이다」로 거절됐다.

- 주원인: Codex 에서 `/hooks` 를 승인하면 `~/.codex/config.toml` 에 승인 상태 `[hooks.state.*]` 가 생긴다.
  이 표 3개가 관리 블록 END 표시 바로 앞, 곧 블록 **안**(314~321행, END 는 322행)에 들어갔다.
  `_strip_codex_entry` 는 BEGIN~END 를 통째로 걷으므로 사람의 승인 상태까지 지우게 되고, 쓰기 전후를 대조하는 `codex_text` 의 보증이 이를 잡아 거절했다.
  계기는 `4ad7247`(#1040 T6 — 마스터에 codex 훅 배달 → 사람이 `/hooks` 승인)이다.
- 부원인: 승인 정렬(`master-local --apply`)이 마감 흐름에 없다. 그래서 새 MCP 도구는 누군가 손으로 돌릴 때까지 승인 목록에서 빠진다.

재현: 운영 코드에 `hooks.state` 가 블록 안에 든 합성 config 를 주고 새 도구 승인을 더하면 같은 문장으로 거절된다(scratchpad r1061/repro.py, 커밋 안 함).

## 고친 것

- `4c1f0b0` T1 — `_strip_codex_entry` 가 블록 안에서 `mcp_servers.ax-client` 밖의 표는 걷지 않고 블록 자리(앞)에 남긴다. 걷은 것 목록에 「남의 표 N개는 블록 밖으로 옮겨 보존」을 보고한다.
  `test_foreign_table_inside_block_1061` 은 다섯 가지를 본다. 거절하지 않는다 · `hooks.state` 파싱 결과가 그대로다 · 블록 밖에 놓인다 · 다시 돌려도 결과가 같다 · 블록 중간에 낀 남의 표도 보존한다.
- `7c1ec7d` T2·T3 — `issue_wrapup` ⑥ 배달 뒤에 ⑥-2 마스터 정렬(`master-local --apply` → `--check`)을 넣었다.
  실패·예외면 rc 1 이고 노트는 남기지 않는다. dry-run 과 인수인계 대기(rc 2)에서는 건너뛰고, 성공하면 노트에 정렬 결과를 적는다.
  공용 규칙 §1.9 와 ax-plan SKILL 에 한 줄씩 보탰다.

## 검사

- `test_client_master_local` 147/147 · `test_issue_wrapup` 55/55 · `test_skill_conventions` 54/54.
- 수정본 재현: 「썼다 · hooks.state 남음」. 운영 main 코드는 여전히 거절한다(대조).
- 운영 설정을 대상으로 메모리에서만 계획을 돌렸다(쓰기 없음). 거절이 없고, `hooks.state` 키와 값이 전후 같으며, 새 도구 2개가 승인 목록에 들어간다.
- `master.sweep` 13101/13102 · unittest 663/663. 유일한 실패 `test_handoff_size` 는 #1061 밖이다.
  #1059 마감 뒤 인수인계 커밋 `c8b9ed0` 이 마감 절 2건을 남긴 탓이다. 사용자 결정 `1df912782660`(「1번으로 가자」)에 따라 #1061 마감 뒤 인수인계 커밋에서 한 벌로 덮어쓴다.
- 운영 `--apply`·`--check` 실측(C2)은 이 일감의 마감 wrapup ⑥-2 가 첫 회차다. 운영 체크아웃은 마감 전까지 옛 코드이고, worktree 코드로 운영 홈에 쓰면 기동 경로가 worktree 를 가리킬 수 있다.

최종 결과는 Redmine #1061 마감 노트에 있다.
