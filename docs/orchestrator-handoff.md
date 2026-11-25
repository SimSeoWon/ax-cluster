# 현재 AX 작업 인수인계

> 2026-11-26 — #1022 마감 직후 체크포인트(Claude). 이번 세션: #741 지도 안개 2줄 해소 · 노드 #1020·#1019·#1022 완료.
> main 은 이 인계 커밋까지 · 일감 잠금 없음 · `ax-projects` 재기동됨(wrapup 판정). 이 커밋 직후 `issue_wrapup 1022` 재실행으로 배달한다(배달 예정).
> 결과·근거의 정본은 Redmine과 reports/다. 이 문서는 현재 작업·남은 관측·다음 행동 한 벌만 유지한다.

## 현재 상태

- **웨이파인더 실증 — Root #741(세션 프로젝트·일감 출처 보강, 분류 신규 기능)**: 맵 등록(노드 6 · blocks 9 · 안개 3 · 범위 밖 3, 사용자 「등록해」).
  노드 #1018 프리필 완료·100 — `python -m master.work.session_provenance [--json]`(읽기 전용) · 커밋 `5a4cd6c`·`206c6bc` · 리포트 210.
  기준선: 색인 2,662 · 미귀속 2,608(empty_cwd 1,499 agy · tmp_ax 983 · master_home 112 · other 14) · work/task 0 ·
  usage_log 결합 가능 codex 974행(967 tmp_ax).
  노드 #1020 완료·100 — `session_usage.issue_of` 로 색인·스냅샷에 `issue_id`(등록 체크아웃 안 `.ax-issues/<N>` 만) · `_norm` 연속 구분자 접기 ·
  `session_provenance` 「issue_id 채워짐」 줄. 운영 reparse 로 14/14 채움(이동 0 · 미귀속 2,608 유지). 커밋 `804df8b`·`093a18b`·`a3efbcf` · 리포트 211.
  지도 편집(사용자 승인): 안개 「agy 세션 ID」→ #1021 첫 확인 항목으로 합침 · 안개 「issue 필드」→ 새 필드로 해소. 남은 안개 1(마스터 홈 세션 정책).
  노드 #1019 완료·100 — 확정 장부 우선 귀속: `session_usage.load_ledger`(usage_log session_id) → 장부 프로젝트가 cwd 보다 앞서고
  work·task 는 dispatch 행에서만(결정 A — 다른 출처 task_id 칸은 버림) · 색인 `attributed_by`·`ledger_source` · /usage 경고 문구 갱신.
  운영 reparse: 장부 974 · 이동 967 · 미귀속 2,618→1,651 · tmp_ax 983→16. 커밋 `506346b`·`cc12321`·`09e2fd2` · 리포트 212.
  노드 #1022 완료·100 — 수집이 미분류 원인(`unassigned_cause`, classify 한 벌)을 스냅샷에 싣고 `build_report` 추가 키 `unassigned` ·
  /usage 「미분류 세션 — 원인별」 표 · 세션 안내문 #1019 반영(#1019 파급 측정 누락분). reparse 뒤 9/1~11/26: empty_cwd 1,514 ·
  master_home 110(36억) · tmp_ax 12 · other 4 · unknown 1,269(65억, 원본 없음). 커밋 `e047a80`·`ca3fc84`·`c8894b3`·`a96eb46` · 리포트 213.
  **Frontier = #1021**(agy 대화 id 확인이 첫 항목). #1023 은 #1021 대기. 남은 tmp_ax 는 장부에 session_id 없는 호출(#1021 몫).
  관찰: 노드 일감에도 `wayfinder_ask` 가 붙는다(노드 표지 있으면 묻지 않는 쪽이 맞다 — 후속 후보, 아직 일감 미등록).
  Root #741 은 「신규」로 열려 있다(지도일 뿐 잠금 없음). 노드 #1019~#1023 은 마일스톤 8 — 개선·확장.
- #839 doc_sync 운영 스냅샷(분류 신규 기능): 완료·100, T1~T4·C1~C4 충족. 커밋 4건 `5486733..c3ac616` · 리포트 209.
  `python -m master.ops_snapshot` → `docs/snapshots/redmine-open.md`(ax-cluster 열린 일감 메타, 아이디어는 건수만) ·
  `docs/snapshots/ops-state.md`(상주 서비스 · HEAD · 워커 배달 리비전). 손으로 돌려 커밋 · 못 닿으면 rc 1 · handoff 근거에만 등록(2→4).
  워커 판정은 돌린 체크아웃의 HEAD 와 대조한다 — 운영 체크아웃에서 돌린다. 재기동 불필요(wrapup 판정 셋 다 최신).
  ③ 보호 문서 4개 실증 · ④ 교차 계열 검토는 #1017(아이디어 버킷, 사용자 지시)로 뗐다.
- 마일스톤 표기: 자동 로드 문서 3곳(`machines/sim-desktop.md`·`CLAUDE.md`·`AGENTS.md`)을 M8 로 고쳤다(`1fec594`, 사용자 지시). M8 전용 문서는 없고 `7-improvements.md` 를 이어 쓴다.
- #1016 doc_sync 인벤토리 근거(분류 버그): 완료·100, T1~T4·C1~C4 충족. 커밋 4건 `9b139a4..a7d2d10` · 리포트 208.
  등록부 `inventory: true`(readme·modules) 문서는 가상 근거 `inventory:master`(운영 모듈 경로+docstring 첫 줄 · 스킬 · `@mcp.tool` 이름)를 자동으로 받는다.
  `--since` 새 사유 `inventory-source-changed` · plan `undocumented_count`·`undocumented` · draft 프롬프트 미언급 구획(정보만, unchanged 를 막지 않음). 전문은 여전히 등록 evidence 만.
  재기동 불필요(상주 서비스 무관, wrapup 신선도 판정 셋 다 최신). 미언급 모듈 62개(두 README 공통)를 실제로 반영하는 일은 범위 밖.
- #982 웨이파인더 맵: 완료·100(배달·스킬 링크 13/13 끝). 커밋 10건 `eabb4af..6140388` · 리포트 206.
  Root 일감 본문 `ax:map`(노드 표·다이어그램·안개) + 노드 일감 `ax:node` 표지 · 도구 `ax-projects:wayfinder_*_tool` 8종 · 스킬 `ax-wayfinder`.
- 🔴 Redmine 에서 노드는 **모두 Root 직속**이다 — 파생 트리는 지도 「부모」 칸에만(실측: 조상-후손 blocks 422 · 열린 자식 있는 부모는 안 닫힘).
- 발동 A: 인터뷰 분류가 신규 기능이면 응답에 `wayfinder_ask` 가 실린다(ax-plan 스킬이 조사 전에 묻는다).
- #1000 맵 안개 편집: 완료·100, T1~T5·C1~C6 충족. 커밋 4건 `cb69f60..65241fd` · 리포트 207.
  `wayfinder_edit_propose_tool`/`wayfinder_edit_apply_tool`(fog_add·fog_resolve·fog_to_out·destination·out_edit·out_to_fog·node_out)
  + `wayfinder_propose_tool(graduates)`. 해소 근거는 Root 노트에만(사용자 A). 파생 자식 있는 노드 범위 밖은 거절(A).
- **완료 노드는 범위 밖으로 돌리지 않는다** — 사용자 확인 2026-11-19: node_out 은 마감 정리·중요하지 않아 유보할 때 쓴다(#1000 노트).
- 진행 중 일감 없음(잠금 없음). 웨이파인더 #741 은 다음 노드 선택을, 다른 일감은 사용자 선택을 기다린다.

## #979·#980 으로 바뀐 것 (운영 계약)

- #979: 검색 로그·`log_history` 에 일감 번호(직접·잠금 관측)와 **그 시점** 스냅샷(제목·「문제·맥락」·작업중 태스크·status)이 남는다.
  `find_history` `issue_id` 필터 · `/rag-logs` 는 당시 스냅샷을 먼저. 현재 Codex 도구에는 `log_history`·`find_history`의 `issue_id`가 노출된다.
- #980: `python -m master.search_usefulness [--issue N] [--json] [--apply]` — 요청별로 반환 문서와 그 일감 커밋 파일·리포트 언급을
  대조해 근거(있음·일부·없음·확인불가)를 추정한다. `--apply` 는 `rag_labels` 에 검증자 auto·「후보」(사람 판정 보존·재실행 멱등).
  운영 실행 완료: labels 2→81(추가 79), 요청 125 = 있음47·일부8·없음20·확인불가50, 연결 80 중 원문 번호 후보 76.
  **확정은 사람만** — `rag_label_tool(status="확정", reviewer, basis)`. 한계: 부모·자식 일감 미추적(#860→#861).

## #211 에서 이어지는 것 — 사용자 결정 대기 (착수 승인 아님)

- 측정(세대 b, 30건 · hangul_only 1/mixed 29): baseline hit@5 .733/MRR .624 · kr_on 더 낮음(.595) · 게이팅 판정 불가.
  실패 8건 중 6건은 BM25 1~2위 정답을 벡터 오답이 밀어냄 · 상위5의 41% 가 `test_*.md` · 진단 「BM25 단독−테스트」 .967/.872.
- 리포트 203 의 개선안 5건(KR 끔 유지 · 혼합 질의 융합 가중 재측정 · 테스트 문서 감점 · 벡터 모델 점검 · 순수 한글 수집)은
  **운영 변경 전 사용자 결정**이다. 검색 가중치는 정답 집합(이제 `reports/203-211-ground-truth.tsv` 30건) 위에서만 손댄다(M2 규칙).
- 벤치: `master/bench_kr.py --gt reports/203-211-ground-truth.tsv [--json]` — 색인 임시 사본·로그 억제로 운영 로그에 쓰지 않는다(실측 1353→1353).
- 커밋 변경 파일 대조는 #980 의 `search_usefulness` 로 도구화됐다(검색 유용성 후보 판정 — 정답 집합 후보 제안은 비범위).

## 남은 관측 (이전 인계에서 이어짐 — 이번에 판정하지 않음)

- `ax-indexer` 30분 timeout 회차 반복 기록과 #971 개명 합성 — 11-17 00:21 이후 회차는 거부 0 으로 끝났다(이벤트 0). 개명 문서 저장은 미확인.
- #964·#966 `ax-batch` 관측 · agy 처리량 감소 보고 · #383 실합성 · #942 relay 한도 연계 · #943·#950 로그 줄 — 재조회 필요.
- `.33`·워커 `client_mcp.tool_search_context` 는 `issue_id`·`purpose` 미전송(#978).

## 지휘·승인·미확인

- 마스터 마지막 담당 기록 claude(2026-11-14) · 워커 전역 codex(state, 2026-10-18). 이번 세션 변경 없음.
- worktree 에는 `.venv` 가 없다 — 검사는 `/home/sim/ax-cluster/.venv/bin/python` 으로 돌린다. 마감 뒤 worktree 가 지워지므로 이어지는 명령은 운영 체크아웃에서 실행한다.
- 인계서는 한 벌로 덮어쓰며 끝난 일감 표·목록을 쌓지 않는다(#842·#975, 이번 변경의 상한 500줄).
- 미처리 리뷰: #929 · #930 · #931 · #934 · #829 · #942 의 R 번호 — 각 Redmine 노트. #211·#979·#980 커밋 리뷰·종합 리뷰는 도착하는 대로 각 일감 노트로 붙는다.
- 결정·구현 대기: #326 · #935 · #738 · #941 · #968 · #978. 조건 대기: #272 · #858.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다. 다른 일감은 사용자 선택을 기다린다.

## 바로 다음 작업

- 세션 시작: `ax-handoff` → `ax-projects:wayfinder_status_tool(741)` 로 Frontier·대조(마지막 확인 차이 0) 재확인.
- #741 다음 노드는 #1021 스탬프 누락 방지(유일한 Frontier) — agy 대화 id 확인이 첫 항목, agy 1회 = 공용 쿼터. 착수는 사용자 결정.
  노드 착수는 `wayfinder_claim_tool` → `ax-plan` 흐름. 측정 기준선 재실행: `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.session_provenance`.
  `master.sweep`·`workshop_paths()` 측정은 `AX_PROJECTS_ROOT` 없이 돌리면 실패한다(test_sandbox 포함 — 회귀 아님, 리포트 211 §4).
- #1022·#1019·#1020·#1018·#839·#1016 해시별·종합 리뷰는 도착하는 대로 각 일감 노트로 붙는다.
- 웨이파인더 후속 일감(착수는 사용자 결정): #1007 `.33` 언리얼 표면(`ax-client` 도구·`infra_finish` map_hook) · #1008 Root 원격 브랜치·노드 서브 브랜치(의존 없는 노드 분산).
- 다른 일감은 착수하지 않는다. 아래 항목은 사용자 선택 대기다.

- #978: `.33`·워커 검색(`client_mcp.tool_search_context`)도 `issue_id`·`purpose` 를 보내게(#979 스냅샷이 거기서도 남도록).
- #980 자동 「후보」 79건 중 사람 확정 여부 — 확정은 `rag_label_tool(status="확정", reviewer, basis)`.
- #211 리포트 203 개선안(혼합 질의 융합 가중 재측정 · 테스트 문서 감점 등)은 운영 변경 전 사용자 결정.
- 기록·이력 조회는 현재 노출된 `log_history`·`find_history`의 `issue_id` 인자를 쓴다.
