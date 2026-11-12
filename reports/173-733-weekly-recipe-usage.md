# 173 — #733 주간 플랜·레시피 상용 호출의 사용량 기록

2026-11-12 · 지휘 Codex · 구현 제안 Gemini gemini-4-argon-medium · 적용·검증 Codex · 구현 커밋 `2a82cbb`.

## 승인과 작업 위치

사용자 원문: 「그래 733 진행해」, 「로컬 서브에이전트로 진행해! 아마 제미나이 아르곤 토큰 많을꺼야 아르곤으로 진행해」.
제안 플랜(주간 플랜·레시피 sink, 회귀·실제 호출·통합·마감·배달)에 대한 승인으로 해석했다.
최초 패치 실패를 보고한 뒤 사용자 「응! 왜 실패한거야?」로 Argon 수정 요청을 승인했다.
`plan_start_tool(733)`은 `verdict=plan_needed, ok=false`였다. RAG 본문과 실제 소비자를 대조해 T1을 등록했다.

`issue_start_tool(733)` 핵심 원문:

```json
{"ok":true,"issue_id":733,"branch":"issue/733","repo":"/home/sim/ax-cluster/.ax-issues/733","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"bdd3a2818dbf26d26d31d049fdb5afbec1d1dde4","lock":"acquired","author":{"client":"codex-mcp-client","family":"codex","authors":["codex"]}}
```

시작 응답에 `done`·`why`는 없다. 편집·검사·커밋은 응답의 repo, 운영 checkout은 main이다.
RAG request_id=c66c850b793a4fe68acf5ef92db920bf, search_id=4b874ede26ba433cb607529b0ddeeaa4.
`AXCluster/context/master/context_synth/{planner,plan_generator}.md`와 `master/test_planner.md` 본문을 읽고 실제 호출부와 대조했다.

## 결함 항목별 대조

1. 주간 플랜 기록 누락 — 참. planner의 작성자별 generate_improvement_plans 호출에 sink가 없고 plan_generator는 commercial_chat을 직접 사용했다. 해당 호출에 source=weekly_plan, task_id=주차:작성자를 부여했다.
2. 레시피 합성 기록 누락 — 참. 클러스터·개별 합성·안티패턴이 commercial_chat을 직접 사용했다. run_recipe_synthesis 전체에 source=recipe_synthesis, task_id=프로젝트를 부여했다. 활성 신호가 없어 아카이브만 보는 분기도 포함한다.
3. 범위 플랜 기록 누락 — 거짓. #639 scope_plan은 이미 별도 sink를 가진다. 공통 plan_generator에 새 sink를 넣지 않아 기존 출처를 보존했다.
4. claude·codex 공용 CLI emit 누락 — 현재 거짓. 기존 구현과 test_usage_cli_paths가 성공·실패별 1행, 레인 중복 방지를 검증한다. 이 구현은 다시 만들지 않았다.
5. 게시판 채팅 경로 — 현재 완료 조건으로 재사용 불가. #812에서 제거됐다는 기존 일감 노트와 기존 검사 계약을 따랐다.

## Argon 위임과 실패 원문

정본 master/client/skills/ax-gemini/SKILL.md §4-1의 master.work.gemini_report --task implementation을 사용했다.
스크래치 `/tmp/ax-gemini-733/src/`에 사본 8개만 전달하고 파일 편집·명령·MCP·재위임·git·운영 조작을 금지했다.
CLI sandbox/plan의 완전 격리를 검증한 것은 아니다.

- 최초 샌드박스 호출 rc1: `Failed to start: listen tcp 127.0.0.1:0: socket: operation not permitted`. 승인 후 같은 호출을 샌드박스 밖에서 실행.
- 첫 Argon 성공 rc0, 실제 모델 gemini-4-argon-medium(log 일치), 287.5초, 입력 89611·출력 28187·캐시읽기 151714. 폴백 없음.
- 최초 git apply rc128: `error: corrupt patch at line 259`. recipes hunk 선언 53/55 vs 실제 54/56, test_recipes 선언 new21 vs 실제22. 소스 변경 0 확인 후 중단·보고했다. 별도로 아카이브 후 원본 리뷰 복사 결함도 발견했다.
- 사용자 승인 후 v2 Argon rc0, 같은 실제 모델(log 일치), 503.5초, 입력193990·출력42331·캐시읽기143835. 폴백 없음.
- v2의 전체 패치 내용·허용 파일·hunk 8개의 행 수를 Codex가 검토했다. git apply rc0. 변경은 소스2·기존검사3파일이다.
- 첫 제안과 수정본은 reports/research/2026-11-12-733-usage-proposal{,-v2}.md에 보존한다. 첫 제안은 채택하지 않았음을 검증 머리말에 표시했다.
- Argon 작성 사실을 여기에 명시한다. issue_start의 자동 작성 계열은 codex뿐이므로 agy 자동 리뷰만으로 교차 계열 검증됐다고 주장하지 않는다. Codex가 직접 전체 패치를 검토하고 검사했다.

## 검사와 실제 관측

작업 repo에서 `AX_PROJECTS_ROOT=/home/sim/ax-cluster`, 해석기 `/home/sim/ax-cluster/.venv/bin/python`.

| 명령 | 결과 |
|---|---|
| python -B master/test_usage_cli_paths.py | rc0, 57/57 |
| python -B master/test_planner.py | rc0, 67/67 |
| python -B master/test_recipes.py | rc0, 18/18 |
| bash /tmp/ax-733-checks.sh의 기존 pystatic.run_static(base=bdd3a2818dbf26d26d31d049fdb5afbec1d1dde4, 변경5파일) | pyflakes 차단0·노트1, import2개 차단0, mypy call-arg 차단0·비차단 노트9 |
| git diff --check | rc0 |
| python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v | rc0, Ran 194 tests in 204.239s, OK |

검사 범위: 예외 후 재시도별 기록·바깥 sink 복원·scope_plan 출처 불변·레시피 세 호출별1행·신호0건 안티패턴1행.
공식 통합은 최종 코드 상태에서 실행했다. 로그 `/tmp/ax-733-static.log`, `/tmp/ax-733-integration.log`.

실제 호출: `/home/sim/ax-cluster/.venv/bin/python -B /tmp/ax-733-live.py` rc0.
기존 test_planner/test_recipes fixture의 격리 입력과 기존 run_weekly_plans/run_recipe_synthesis를 사용했다.
실제 commercial_chat 기본 체인을 빈 작업 디렉터리에서 호출했고, 운영 트윈 AXCluster/usage_log.jsonl에 기록했다.
Redmine 등록과 운영 리뷰 아카이브는 하지 않았다. 입력 자료는 합성 조건이며 운영 결함을 발견했다는 주장이 아니다.

- 23:47:23 weekly_plan · task_id=2026-W45:사람 · lane=codex · rc0 · measured=true · 입력18696·출력522·캐시12288 · 16.3초 · session_id=01a1d03a-0b95-70e1-be0a-169c02ee04a8. 플랜1건 생성.
- 23:47:28 recipe_synthesis · task_id=NS(검사 자료의 프로젝트명) · lane=codex · rc0 · measured=true · 입력18830·출력63·캐시12288 · 5.3초 · session_id=01a1d03a-4acf-7001-8183-0b062a88079f. 신호 없는 아카이브 안티패턴1건 집계.
- codex 비용은 cost_known=false로 미상이다. 무료로 해석하지 않는다. 레시피 세 단계의 실제 상용 호출은 이번에 따로 실행하지 않았고 가짜 CLI 회귀 근거다.

경로 조회 실패: `.agents` 부재는 확인된 master/skills로 재조회했다. 홈 전체 및 /tmp 전체 목록 조회에서 무관한 비공개 디렉터리 Permission denied가 발생했다. 사용자의 「좁게 잡으면 된다는거잖아」 지시에 따라 확인된 대상 경로로 제한했다. 이후 경로 존재 조회는 깊이와 대상을 좁혀야 한다.

현재 세션: ~/.codex/sessions/2026/11/12/rollout-2026-11-12T23-17-23-01a1d01e-d294-7680-8cf8-661b8454f17f.jsonl.

최종 결과는 Redmine 마감 노트.
