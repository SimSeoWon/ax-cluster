# 현재 AX 작업 인수인계

> #1049 마감 뒤 체크포인트(Claude, 2026-11-28). #1040 훅 경로 결함을 고치고 운영에서 입력 장부·Stop 차단을 실측한 뒤 AXCluster 관문을 켰다.
> #1049 잠금 해제. 재기동 대상 없음(훅은 사건마다 새 프로세스, 서비스는 15:19 재기동본). 이 인계 커밋 push 뒤 `issue_wrapup 1049` 재실행으로 배달하며 결과는 #1049 마감 노트.
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
  노드 #1021 완료·100 — claude `parse_claude_json` 이 봉투 session_id 를, agy `run_agy` 가 끝난 뒤 `agy_trace.find_conversation`(BRIEF 표지)
  으로 대화 id(= brain/<id>)를 `usage_log` session_id 에 싣는다(폴백은 최종 시도만 · 못 찾으면 빈 값). 커밋 `5f7eac9`·`c97cc8a`·`b26f6db` · 리포트 214.
  마감 뒤 확인 완료(#1021 노트): 배달·check rc0 · 재기동 뒤 첫 운영 agy 호출 session_id 2b27ed16… = conversations/brain id. claude 운영 호출은 미발생(단위 검사만).
  범위 밖: ax-gemini(`gemini_report`) · local · 과거 행.
  노드 #1023(검증) 완료·100 — 코드 변경 없음 · `session_usage all` 재수집(4호스트 오류 0 · 정리 0) 전후: 장부 결합 982→989 · agy 결합 0→7
  (재기동 뒤 agy 운영 호출 7/7 → ledger 귀속) · work/task 7 · issue 16 유지 · 기존 귀속 변화 0 · 결함 없음. 리포트 215 `e10a2c5`.
  🔴 **Root #741 「완료」 마감**(사용자 「응, Root 마감해」) — 노드 6 완료 · 차이 0 · 안개 0. 마지막 안개는 결정으로 해소(사용자 「2번」):
  마스터 홈 세션은 추정 귀속하지 않고 미분류로 둔다 — /usage 원인별 표 master_home 행으로만 보인다(#1022). log_history 기록.
  기준선 대비: 미분류 2,608→1,658 · 장부 귀속 0→989 · work/task 0→7 · issue 0→16.
  남은 구멍: claude 비대화형 운영 호출 session_id 실측 미발생 · ax-gemini 경로 · 원인 모름 1,269(원본 없음).
  웨이파인더 후속 관찰(미등록): 인터뷰 분류에 「검증」 칸 없음 · 노드 일감에 wayfinder_ask 가 붙음 — 노드 표지로 분류를 읽는 쪽.
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
- 진행 중 일감 없음(잠금 없음, #1040 마감). 웨이파인더 #741 은 다음 노드 선택을, 다른 일감은 사용자 선택을 기다린다. 운영 분산 배정 기록 0건(실제 발주 0).

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
  #1039 는 Codex(T1~T3)가 토큰 소진으로 T4 에서 인계했고 Claude 가 이어받아 마감했다(작성 계열 누적 codex·claude).
- worktree 에는 `.venv` 가 없다 — 검사는 `/home/sim/ax-cluster/.venv/bin/python` 으로 돌린다. 마감 뒤 worktree 가 지워지므로 이어지는 명령은 운영 체크아웃에서 실행한다.
- 인계서는 한 벌로 덮어쓰며 끝난 일감 표·목록을 쌓지 않는다(#842·#975, 이번 변경의 상한 500줄).
- 미처리 리뷰: #929 · #930 · #931 · #934 · #829 · #942 의 R 번호 — 각 Redmine 노트. #211·#979·#980 커밋 리뷰·종합 리뷰는 도착하는 대로 각 일감 노트로 붙는다.
- 결정·구현 대기: #326 · #935 · #738 · #941 · #968 · #978. 조건 대기: #272 · #858.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다. 다른 일감은 사용자 선택을 기다린다.

## 바로 다음 작업

- **#1039 완료·100** — 커밋 `56bc955`·`c02c091`·`e065e8e`·`f5d263f`, 리포트 224. 웨이파인더 진행 시 단독·분산을 고르고, 분산은 사이클마다 준비된 티켓만 `ax-projects:wayfinder_dispatch_tool`(기본 드라이런 · `confirm=True`+발주 요청 원문)로 등록 워커에 예약·실행한다. 티켓 한정 권한(#1037)을 Linux stdin/Windows 런처 환경으로 넘긴다. 종료가 확인된 배정만 검수 대기 + 티켓 노트, 미확인은 점유 유지. 공식 통합 221/221, 스킬 규약 54/54.
  T4 중단(00:35 KST, `SKILL.md:100` 접두사 누락) 뒤 재개했다. 인계 당시 `/tmp/ax-1039-checks.sh` 는 재부팅(11-28 11:17)으로 사라져 정본 통합 명령을 직접 썼다.
- 🔴 **#1040 완료·100** — 커밋 `d11d0a0`..`cabf01e`(8건), 리포트 225. `master/interview_ledger.py` 질문 장부(`interview_ask` — 추천 1번 필수·대안 0~3·확신도 0~100) · 입력 장부(`UserPromptSubmit` 훅 `prompt_ledger.py`) · 실패 장부(`check_result_tool`).
  `interview_step`·`interview_spec`·`plan_set` 은 관문(`<트윈>/config.yaml` `interview_gate: enforce`)이 켜지면 질문 등록·질문 뒤 원문 일치·보기 선택/긍정을 판정하고 확신도 증감을 노트에 남긴다(자유 의견 = 수정 요청 거절).
  `plan_start` 는 열린 실패가 이번 일감 변경(시작 리비전 이후 커밋+미커밋) 안이면 resume, 밖이면 stop. `Stop` 훅 `stop_gate.py` 는 잠금+resume/next+사유 없음이면 막는다(그 일감을 다룬 세션만 · 관문 꺼지면 통과).
  마스터 훅은 `master-local --apply` 로 설치됨(Codex 세션이 실행, `--check` 15/15). **Codex 훅은 사람이 `/hooks` 승인 필요.**
  🔴 **AXCluster 관문 켜짐**(`AXCluster/config.yaml` `interview_gate: enforce`, 2026-11-28 15:30) — 마스터 인터뷰·스펙·플랜 기록은 이제 `ax-projects:interview_ask_tool` 로 먼저 묻고 사용자 원문 그대로 `user_answer` + `divergence` 를 넣어야 한다.
  운영 실측(#1049): 설치 훅 명령(Claude·Codex) 입력 장부 기록 · 실 세션 Stop 3회 차단 후 상한 통과(`~/ax-state/.claude/logs/task_queue_2026-11-28.log` `[ledger]`).
  남은 것: `.33` 요청자 훅은 게임 프로젝트 배달 때(그 프로젝트 관문은 배달·check 뒤) · Codex `/hooks` 승인 여부는 다음 Codex 세션에서 실기록으로 확인. 비범위: 미호출 단정(21:55 유형) · `.33` Codex 프로젝트 hooks.json.
- **#1049 완료·100** — #1040 결함: `prompt_ledger.REPO_CLIENT` 가 `parents[3]`(master/)이라 마스터 훅 둘 다 무동작이었다 → `parents[4]` · 저장소 클라 실호출 검사(A/B). 커밋 `20182f5`.
- **#1042 신규(버그/개선)** — doc_sync draft 가 문서 하나 실패로 배치 전체를 끝내 성공한 수정안까지 잃는다. 우회: `--id` 하나씩 실행.
- 문서 최신화 완료: `readme`·`onboarding`·`modules` codex 수정안 적용·커밋 `be4b920`(사용자 승인). 남은 지적(정보): onboarding Stop 조건에 `next` 누락 · modules `create_map` 규칙(처음 노드 전부 선행 없음) 덜 정확 · README 도구 표에 #1040 `interview_ask`·`check_result_tool` 없음 — 다음 doc_sync 때.
- **#1038 완료·100** — 커밋 `7c4fe88`·`44480a0`·`591150e`, 리포트 223. 서버가 분산 노드 한 건과 실제 워커 한 대를 원자적으로 예약한다. 실행 종료를 확인하면 워커를 풀고 노드는 검수 대기로 유지한다. 승인된 재작업은 같은 티켓을 사용한다. 지도에 워커와 검수 상태가 표시되며 단독 중복 착수와 Redmine 직접 마감을 차단한다. 공식 통합 221/221, 잠금 검사 68/68.
- **#1037 완료·100** — 커밋 `895f7e2`·`e7798e2`·`ffdef2e`, 리포트 222. 워커는 마스터가 서명한 티켓 한 건의 권한으로 스펙·플랜·노트를 읽고, 같은 티켓에 작업·검증 노트를 추가한다. 공식 통합 221/221, 실제 AX 앱과 Redmine 대역 왕복 270/270. 실제 발주에서 권한 발급·주입은 P3 범위다.
- **#1008 다음 노드 P4가 Frontier** — P4는 원격 시작과 검수·마감 연결이다(검수 통과 `to="finished"` 해제, 수정 승인 `NODE_REWORK` 재예약). P5 실증은 P4 완료를 기다린다. #1039 마감 시 지도 갱신, 마감 전 대조 차이 0. 사용자가 선택하기 전 다음 노드는 선점하지 않는다.
- #1008에서 합의한 분산 흐름: 명확한 일감만 먼저 만들고 사용자 인터뷰로 스펙·플랜을 확정한다. 사용자 요청 뒤 준비된 일감만 발주하고 결과를 같은 티켓에 기록한다. 이번 묶음의 결과가 모이면 검증하고, 걷힌 안개로 다음 묶음의 인터뷰를 준비한다. 실제 선언은 Git 기준 커밋, 구현·검증·재작업 지시는 Redmine이 정본이다.
- 🔴 #1036 완료·100 — 커밋 `b3fd099`·`bcf684c`·`254d334`·`d13ac7d` · 리포트 221.
  등록은 예정 키 P<n>으로 지도만 쓰고, claim이 일감·선행 blocks·키→번호(부모·선행 참조 포함)를 만든다.
  MCP claim node_id=int|str·propose deps=list[int|str], 스킬 개요·§2·§3·§4 갱신. 번호 지도 하위 호환 유지.
  공식 통합 221/221 · 전수 247파일 A/B 12837/12837·unittest663/663·실패0. test_wayfinder226/226.
  issue_finish: ok=true·registered=true·closed=true·lock_released=true·why="", end=d13ac7d8710bb9b4a74deba903477b1e1050f722.
  wrapup 1차 rc2(인계 대기): ax-task-queue 21:43:27·ax-projects21:43:33 KST 재기동, active·재판정 깨끗.
  운영 #1008에서 후속 5개를 예정 키로 등록(티켓 0) → P1 선점(#1037 생성) → 지도 대조 차이 0을 확인했다.
  예정 키를 받지 못한다는 이전 추정은 실제 MCP 호출 성공으로 정정했다. 별도 시험 Root 정리 시나리오는 미실행. 실증과 배달의 정본은 #1036 노트.
- 세션 시작: `ax-handoff` → `ax-projects:wayfinder_status_tool(741)` 로 Frontier·대조(마지막 확인 차이 0) 재확인.
- 웨이파인더 후속: #1024 완료·100(노드 일감엔 wayfinder_ask 생략 — `interview.record` 가 `map_block.parse_node` 로 판독, 깨진 표지도 생략+[주의] · 커밋 `c12981a`·`34e99a7` · 리포트 216).
  #1027 완료·100(#1024 마감 중 발견의 후속) — `map_block._marker_span` 이 인용(코드 스팬·``` / ~~~ 펜스)을 같은 길이 공백으로 가린
  사본에서 표지를 찾는다 · 인용 밖 깨진 표지는 그대로 거절 · 다섯 호출부(interview·on_node_closed·대조·노드 생성·put_node) 같이 바뀜.
  커밋 `eac2743`·`e2db97e`·`9947183` · 리포트 217. 마감 뒤 C4: 운영 코드 재현 정상 · `wayfinder_status(741)` 차이 0(#1027 노트).
  비범위: 들여쓰기 코드 블록 안 표지는 여전히 표지로 읽힌다(사례 없음).
  #1025 완료·100 — 착수 전 인터뷰 분류에 「검증」(`verify` · 코드 무변경 실물 판정 · 재현 건너뜀 · 웨이파인더 질문 없음) 추가.
  문서 하나(`master/skills/ax-plan/reference/category-verify.md`) · 코드 무변경 · 커밋 `5917ff1`·`a419b0d`·`8456ca1` · 리포트 218.
  `.33` 게임 요청자 인터뷰에도 보인다(공용 규약). 노드 타입 자동 분류(B)·「프리필」 칸은 비범위. 마감 뒤 C4: 운영 `plan_start_tool` 분류 4종 확인.
  🔴 #1028 완료·100 — **웨이파인더 맵은 목적지 + 지금 집을 수 있는 첫 노드로 시작해 자란다**(사용자 지적: 인터뷰가 확정하는 것은
  목적지 하나 · 중간 경유지 설명은 참조 자료 · 처음부터 다 까는 것은 오동작). `create_map` 이 노드 0개·선행 걸린 노드를 거절 ·
  스킬 §2(목적지 → 첫 노드 → 미리보기·동의 → 등록)·§3(노드 마감 뒤 다음 노드 제안). 원인 #982 스펙 「명확·모호 분류 후 맵 작성」→ 스킬 §2.
  커밋 `d0a981b`·`2ee42d6`·`f569e73` · 리포트 219. 마감 뒤 C4 실물: 시험 Root #1029 → 첫 노드 #1030 → 마감 → 제안·등록 #1031 · 차이 0 · 시험 3건 완료로 닫음.
  #1026 은 #1027 과 같은 결함으로 11-25 에 먼저 등록돼 있었다 — 중복으로 「완료」(사용자 결정). 등록 전 열린 일감 조회를 빠뜨린 탓.
- 🔴 **웨이파인더 Root #1008 — 목적지(사용자 정정 2026-11-27): Redmine 노드 일감(스펙·플랜·노트)이 작업 지시서가 되어, 의존 그래프에서
  기다릴 필요 없는 노드(서로 선행 없는 Frontier)를 등록된 워커들에 발주해 병렬로 진행한다.** 순서: 웨이파인더 1차 → 그 결과로 분산작업(work) 개선.
  기억 `redmine-ticket-dispatch-direction` — **골조 경로(work)에 태우는 쪽으로 설계하지 말 것**(내가 처음 그렇게 잡았다 정정받음).
  안개 1: 병렬 노드의 브랜치와 main 적용 — 사용자 의도는 #1008 전용 Root 원격 브랜치 → 코드 작업 노드만 의존 그래프 따라 자식 원격 브랜치 →
  최종 개발 main 머지 · 코드 없는 노드는 브랜치 없음(리포트 처리 A 노트만 / B Root 브랜치 커밋은 미정).
  첫 노드 #1032(프리필, 분류 검증) 완료 — 리포트 220 `8b9dd6f`. 판정: Q2·Q6 **가능**(더미 병렬 실측 `.43`·`.2` 약 8.0초 겹침) ·
  Q1 **조건부-정책**(워커 토큰 `WORKER_SCOPE` 에 Redmine 없음 — κ.0, 실측 403) · Q3·Q5 조건부 · Q4 **막힘**(issue_lock 활성 한 칸, #883) ·
  Q7 막힘-좁음(issue_finish main ff 고정 · 이름은 Root 잎 `wayfinder/<R>/root` + 형제 자식 `wayfinder/<R>/n<N>` 통과).
  리포트 220 §5 제안 노드 5건(P-a 워커 일감 읽기 · P-b 노드 단위 선점 · P-c 일감 발주 · P-d 원격 노드 일감 흐름 · P-e 실증) —
  사용자: 「다섯 개 전부 등록하되 시작할 때 레드마인을 할당하는건 안되는거야? 한 순간에 티켓을 막 발생시킬 필요가 있는건가」.
  종전 register_node는 등록 즉시 일감을 만들었다. 사용자 「이 문제 먼저 수정해」로 #1036에서 선점 시 생성으로 변경·main 반영.
  후속 노드 5건 등록 완료. P1은 #1037, P2는 #1038, P3는 #1039로 마감했고 P4가 Frontier다.
  [주의] `.2` 시계가 마스터보다 약 20초 늦다 — 병렬·로그 상관은 마스터 시각으로.
  노드 착수는 `wayfinder_claim_tool` → `ax-plan` 흐름. 측정 기준선 재실행: `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.session_provenance`.
  `master.sweep`·`workshop_paths()` 측정은 `AX_PROJECTS_ROOT` 없이 돌리면 실패한다(test_sandbox 포함 — 회귀 아님, 리포트 211 §4).
  🔴 worktree 에서 돌릴 때도 `AX_PROJECTS_ROOT=/home/sim/ax-cluster`(운영 루트)다 — `$PWD`(worktree)를 주면 test_sandbox 4/14 로 실패한다(#910 · 리포트 217 §3).
- #1032·#1028·#1025·#1027·#1024·#1023·#1021·#1022·#1019·#1020·#1018·#839·#1016 해시별·종합 리뷰는 도착하는 대로 각 일감 노트로 붙는다.
- 웨이파인더 후속 일감(착수는 사용자 결정): #1007 `.33` 언리얼 표면(`ax-client` 도구·`infra_finish` map_hook) · #1008 Root 원격 브랜치·노드 서브 브랜치(의존 없는 노드 분산).
- 다른 일감은 착수하지 않는다. 아래 항목은 사용자 선택 대기다.

- #978: `.33`·워커 검색(`client_mcp.tool_search_context`)도 `issue_id`·`purpose` 를 보내게(#979 스냅샷이 거기서도 남도록).
- #980 자동 「후보」 79건 중 사람 확정 여부 — 확정은 `rag_label_tool(status="확정", reviewer, basis)`.
- #211 리포트 203 개선안(혼합 질의 융합 가중 재측정 · 테스트 문서 감점 등)은 운영 변경 전 사용자 결정.
- 기록·이력 조회는 현재 노출된 `log_history`·`find_history`의 `issue_id` 인자를 쓴다.
