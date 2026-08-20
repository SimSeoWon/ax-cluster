# 27 — 창구는 `.33` (사용자 정정) + 원전 로컬 함대 정리 1~3단계

레드마인 **#226** (진행 · 마일스톤 6). 커밋 `821d110` · `7d523d7` · `bc6f720` · `fba533e` · `cb7af6e`.

## §1 시작 — 내가 틀렸고 사용자가 정정했다

세션 첫 질문: *"클러스터링 작업 완료된거 테스트해보려는데, .33에서 ModularStage 에서 클로드 cli 를
키고 명령하면 되는거야?"* 나는 **"아니다, 등록·파견은 마스터에서 한다"** 고 답했다. 사용자가
정정했다 — *"여긴 작업장이 아니야. 여긴 인프라서버고, .33에서 언리얼 프로젝트 작업중 너에게
요청하는거야"*.

대조 결과 **사용자가 맞았고 문서에도 그렇게 적혀 있었다**: `docs/8-git-authority.md` 요청자 행 =
①main 최신화 ②durable push ③**등록** ④리뷰·`[FEEDBACK]`. 게다가 `.33` 의 요청자 콘솔은
**이미 전부 배달돼 있었다** — 홈 스킬 3종(`ax-request`·`ax-ontology`·`ax-review`) · 체크아웃
`.mcp.json` 의 `ax-client` 항목(사람의 MCP 3종과 공존) · `.ax/{config,token,lib,tasks,work}` ·
프로젝트 `CLAUDE.md` 의 AX 관리 블록에 *"이 머신은 요청하는 쪽"*·*"여기서 소스를 고치지 않는다"*.

[중요] **빠져 있던 것은 마스터 쪽 `CLAUDE.md` 한 문단이었다.** 설계 문서에 있어도 **매 세션 자동
로드되는 파일이 말하지 않으면 매 세션 같은 착각을 한다.** 실전 1호(리포트 23)를 내가 마스터에서
돌린 것을 「설계」로 착각한 것이 이번 오답의 경로다.

→ `machines/sim-desktop.md` § About this directory 에 *"this box is infrastructure — the workshop
is `.33`"* 문단 + `.33` 인벤토리 행에 「언리얼 작업의 창구」 · `machines/win-main-33.md` 에
§ 요청자 콘솔 신설(배선 표 · 배달 커밋 대조 기준 · 낡은 번들 경고).

## §2 「로컬 와처 제거」 — 제안 전에 세어야 했다

사용자 제안: *"이참에 .33과 .2번에 기존 로컬 와처 모두 제거하는게 어떨까해."* 실측:

| 확인 | 결과 |
|---|---|
| 스케줄 작업 | `.33` 원전 계열 **0건** · `.2` 는 우리 `AxClaimer`(Running) 하나뿐. Run 키·시작 폴더 깨끗 |
| 프로세스 | `watch.exe`/`worker.exe` **미실행**. 도는 것은 클로드 세션이 띄우는 stdio MCP exe (`.33` 에 `context_search.exe`×2 · `task_queue.exe`×2) |
| [중요] 파일 | **`watch.exe`+`config.json` 이 두 기계 프로젝트 루트에 살아 있었다** (원전 폴링 데몬, 60초 git fetch) |
| [중요] 배선 | **`.2` 의 config 가 옛 토폴로지를 가리켰다** — `context_server_url: http://192.168.0.33:8100` · `task_queue_url: http://192.168.0.33:8101` = 「`.33` 이 서버, `.2` 가 워커」 시절 |
| [주의] 자격 | 양쪽 config 에 **Redmine API 키 평문** |

즉 **와처는 「돌고 있는 것」이 아니라 「무장된 채 잠들어 있는 것」**이었다. 누가 `watch.exe` 를
켜면 `.33` 은 `auto_review: true` 로 60초마다 돈다.

삭제: 백업(마스터 `~/claude-workspace/backups/legacy-watcher-20260820/`, 원본 타임스탬프 보존,
config 는 0600) → 미실행 재확인 → `del`. **git 무영향**(둘 다 `.gitignore` 33·34행 등재) ·
`.33` 의 미커밋 `.uasset` 무손상.

## §3 로컬 온톨로지 대조 — 이식은 전량, 로컬은 54항목 뒤진 포크

`.33` 세션 보고: 로컬 `context-search` exe 는 도메인 7개를 다 내놓으면서 objects/actions 를
**전부 0/0** 으로 답한다. 원인 확정(exe 내부)은 못 했지만 결정에는 무관했다:

    로컬 `.claude/ontology/domains/` 240항목 · 서버 294항목
    로컬에만 있는 것 **0건** (이식 누락 없음) · 서버가 앞선 것 **54건**
      MissionRuntime invariants +20 · actions +15 · MissionEditor +13 · GlobalEventSystem +6

[중요] **가장 위험한 실패는 「없다」고 답하는 입구가 아니라 「0」이라고 답하는 입구다.** 로컬 데이터가
비어 있지도 않았다 — 그래서 더 그럴듯하게 틀렸다. 새 입구는 없는 이름에 **404** 를 준다.

[주의] 개행 함정 — 첫 대조에서 로컬 240·서버 294가 **교집합 0** 으로 나왔다. PowerShell 출력의
CRLF 때문이었다. `comm` 은 그런 걸 말해 주지 않는다.

## §4 1단계 — 읽기 위임 3종 (커밋 `bc6f720`)

`get_domain_layer(domain, layer)` · `get_object_spec(domain, name)` · `get_action_spec(domain, name)`.
서버 라우트(`/api/v1/ontology/{domain,object,action}/…`)가 이미 있어 프록시만.

- 원전의 `get_domain_layer` 와 `list_actions` 를 **한 도구로** 받았다 — 층 서술과 그 층 항목은 늘
  같이 필요하고, 나누면 왕복만 는다
- [주의] 이 위임만 **응답을 줄인다** → `_stale`·`_cached_at`·`_note` 를 변환 뒤에도 실어 보낸다
  (#162 계약). 떨어뜨리면 마스터가 죽은 것을 아무도 모른다 — 전용 테스트로 고정
- 라이브: L3 필터 10/21/30 · 없는 이름 404 · 스킬(`ax-request` §2)에 「로컬 context-search 로
  부르지 않는다」를 실측째 기입 — **스킬을 안 고치면 `.33` 세션은 도구가 생긴 것을 모른다**

## §5 2단계 — 쓰기 위임, 그리고 라우트 위치가 바뀐 이유 (커밋 `fba533e`)

`add_object_alias(class_name, term)` · `mark_not_a_class(term)`.

[중요] **8103 에 두려다 실측이 막았다** — 그 포트의 `/api/v1/*` 는 `public_prefixes` 라
**무인증 공개**다(토큰 없이 200, `/mcp` 만 401). 읽기는 무인증 뷰와 같은 데이터라 그 자리가 맞지만
**온톨로지 yaml 을 고치는 쓰기는 LAN 아무나 부를 수 있는 자리에 둘 수 없다.** 요청자의 기존 쓰기
대행(`redmine/note`·`signals`)이 이미 토큰 잠긴 큐(8101)에 있으므로 같은 구조로 붙였다.

- `REQUESTER_SCOPE` 에 `("POST", "/api/v1/thesaurus/")` — 같은 경로의 GET 은 안 열린다(테스트)
- [중요] **가드는 우회하지 않는다** — #213 문턱(4자·DF 2.5%)은 `thesaurus.register` 안에 있고
  라우트가 그것을 탄다. 클라·라우트에 문턱 상수가 **복제되지 않았음**을 테스트가 지킨다
- 라이브(전부 비변경 케이스로 골랐다): `noop`(이미 등록) · `rejected_short: 2자 < 4` ·
  `not_found`(오타 클래스) · not-a-class `noop`. 별칭 11건·무시목록 불변 확인 + 큐 감사 로그 4줄
- [주의] `rejected_generic` 은 **라이브 미확인** — 4자 이상이면서 DF 2.5% 를 넘는 표현이 현
  코퍼스에 없다(최고 '미션 태스크' 2.29%). DF 주입 유닛이 덮는다. 미확인은 미확인으로 적는다

## §6 §D 채움 — 문안에 「미위임」을 적기보다 채우는 게 싸다 (커밋 `cb7af6e`)

3단계 문안을 쓰다 계층·연관(넓이) 탐색이 위임 밖임을 발견했다. 그대로 적으면 작업장 문서가
*"웹 UI 로 보라"* 를 정상 경로로 갖게 된다 → **사용자 결정으로 먼저 채웠다.**

- `get_domain_layer` 가 `tier`·`summary`·`layer_counts`·`parent_domain`·`sub_domains`·
  `collaborated_by` 를 함께 준다 (원전 `get_domain_manifest` 자리). **서버 응답에 이미 실려 오던
  값이라 왕복 증가 0** · [주의] `collaborates_with`(정방향)는 우리 응답에 없다 → 역참조로 본다
- `find_invariants_by_class` 신설 — 전용 라우트가 없어 **도메인 스윕**(7개, 같은 캐시 키).
  [중요] **원전과 데이터 모양이 달라 휴리스틱이 됐다**: 우리 `evidence` 는 산문이 아니라
  `파일.cpp:84-90` 이라 클래스명이 없다 → ① `text` 의 클래스명 ② `evidence` 의 **접두 뗀 이름**
  (파일 stem)으로 맞히고, **어느 규칙으로 맞았는지 `matched_by` 로 말한다.** 라이브: 7도메인
  10히트, `text`/`evidence`/`text+evidence` 구분됨
- 실측 부산물: **L2 는 도메인마다 있고 없다** — `ProjectAlpha_UiViewManagement` 5 ·
  `UiManagement` 2 · **나머지 5개는 0**. 원전 래더가 L2 를 당연히 있는 것처럼 적어 둔 것은
  이 프로젝트에서 반만 맞다. 빈 층은 조용한 빈 목록이 아니라 `_note` 로 사유를 말한다

## §7 3단계 — `.33` 문서 갱신 (저장소 밖)

[중요] **고칠 파일이 내가 생각한 파일이 아니었다** — `.33` 세션이 "프로젝트 CLAUDE.md" 라고 한 것은
루트가 아니라 **`.claude/CLAUDE.md`**(526줄)였고, 같은 도구 이름이 `manage-domain`·`manage-task`
스킬에도 있었다. 루트 `CLAUDE.md` 에는 `mcp__` 문자열이 아예 없다.

적용: `.claude/CLAUDE.md` **14곳** · `manage-domain/SKILL.md` 5곳+머리말 · `manage-task/SKILL.md` 1곳.
CRLF 보존(원본 전부 CRLF — 로컬 사본에서 고쳐 해시 대조 후 되돌림) · 백업
`~/claude-workspace/backups/33-claude-docs-20260820/` · `.33` git 상태 불변.

바뀐 것 중 사람이 알아야 할 셋:

1. **별칭 등록 절차가 5→3단계로 줄었다** — `domain` 인자가 없어져 「등록 전 실존 검증」·「도메인
   자동 해석」이 사라졌다(서버 `not_found` 가 대신한다)
2. **`get_object_spec` 은 `(domain, name)`** — 클래스명만으로 도메인을 못 찾는다. 대체 순서
   ①`list_domains` ②`get_domain_layer` ③`get_object_spec` 를 [주의] 로 적었다
3. **`watch.exe` 재기동으로 복구하라던 문구**를 마스터 유닛 확인·재시작으로 교체(그 파일은 오늘
   삭제됐다) — [주의] 성공 판정은 종료코드가 아니라 `ExecMainStartTimestamp`

## §8 남은 것 (#226 본문의 체크박스)

- 4단계 `.mcp.json` 원전 exe 등록 제거 (`context-search`·`task-queue`·`master-orchestrator`·
  `local-llm-runner`·`redmine-tracker`). 로컬 UE5·로그를 만지는 것들은 남는다
- `.claude/skills/distribute/SKILL.md` — 원전 로컬 오케스트레이션. `list_task_templates`·
  `get_task_template` 미위임이고 우리 `/distribute`+`ax-request` 와 중복 → **은퇴 여부 결정**
- 그래프 조회 3종 위임 여부(`find_ancestors`·`find_subclasses`·`dependency_search`) — 두 스킬의
  절차가 의존한다(머리말에 [주의] 기입)
- 확인 후 결정 3종(`code-recipes`·`gemini-query`/`agy-query`·`ontology_viewer`)
- [중요] **실증 테스트 자체** — 위는 전부 배선 정리다. `.33` 창구에서 실 일감 한 건을
  등록→claim→추론→collect→통합→병합까지 사람이 돌려 보는 것이 마무리 ([주의] `collect` 는 수동)

## §9 배운 것

1. [중요] **설계 문서에 있어도 자동 로드 문서가 말하지 않으면 매 세션 같은 착각을 한다.** 오답의
   경로는 "내가 지난번에 그렇게 했다" 였다 — **한 번의 실행을 설계로 읽지 말 것.**
2. [중요] **「제거하자」에는 먼저 세는 것이 답이다.** 와처는 프로세스로 안 돌고 **파일로** 살아
   있었고, 진짜 위험은 exe 가 아니라 **옛 토폴로지를 가리키는 config** 였다.
3. [중요] **조용히 0 으로 답하는 입구가 없다고 답하는 입구보다 위험하다.** 로컬 데이터가 비어
   있지도 않아서 더 그럴듯하게 틀렸다. 새 입구의 404 는 기능이다.
4. [중요] **쓰기 자리를 정하기 전에 인증 배선을 실측한다.** 읽기가 열린 포트라는 사실이 쓰기도
   거기 두라는 뜻이 아니다 — 8103 `/api/v1/*` 무인증 실측이 라우트를 8101 로 옮겼다.
5. **문안을 쓰다 발견한 구멍은 문안에 적기보다 채우는 게 싸다**(사용자 결정) — "웹 UI 로 보라" 가
   작업장 문서의 정상 경로가 되면 그 다음 세션은 그걸 규약으로 읽는다.
6. **이식은 데이터 모양까지 같지 않다** — `find_invariants_by_class` 가 휴리스틱이 된 이유는
   우리 `evidence` 가 산문이 아니라 파일:줄이기 때문이다. 그럴 때 **응답이 스스로 말하게** 한다
   (`matched_by`).
7. 도구 수: 클라 MCP **8 → 14종**(조회 9 + 쓰기 대행 5). 테스트 3463 → **3633**, 실패 0.

## §10 4단계 — `.mcp.json` 원전 exe 등록 제거 (2026-08-20 이어서)

`.33` 체크아웃 루트 `.mcp.json`: **16종 → 11종.** 제거는 #226 본문이 지정한 5종 그대로 —
`context-search` · `task-queue` · `master-orchestrator` · `local-llm-runner` · `redmine-tracker`.
「확인 후 결정 3종」(`gemini-query`·`code-recipes`·`agy-query`)은 손대지 않았다.

[중요] **지우기 전에 세었더니 5종은 이미 무장 해제 상태였다.** 원전 소스 대조:

    redmine_tracker/server.py:87        config.json → redmine_api_key
    context_search/remote_client.py:21  config.json → context_server_url
    task_queue/logic_cleanup.py:19      config.json → redmine 설정
    master_orchestrator/common.py:175   config.json → distribution_mode·agy_path
    local_llm_runner/server.py:48       config.json → local_llm_endpoint·model

전부 **프로젝트 루트 `config.json`** 에서 설정을 읽는데, 그 파일은 §2 의 와처 정리에서 삭제됐다
(실측: 루트에 남은 json 은 `.mcp.json` 하나뿐). 즉 §2 는 데몬만 죽인 게 아니라 **이 5종의 자격·주소를
같이 걷어갔다** — 등록만 살아 있고 기능은 어제부터 죽어 있었다. 그래서 이번 제거는 위험이 아니라 정리다.

안전 확인 순서(전부 실측): `.gitignore:40` 등재 → git 무영향 · 편집 전 `tasklist` 에 claude 세션과
legacy exe **0건** · scp 백업(`~/claude-workspace/backups/33-mcp-json-20260820/`) · 줄끝은 **LF**(이번엔
CRLF 함정 없음) · 남은 11종은 값·**키 순서까지 바이트 동일** · JSON 유효 · 사용자 미커밋 `.uasset` 불변.

### [중요] 부수 발견 — 등록을 지워도 참조는 남고, 그 실패는 조용하다

제거 전 `.claude/**/*.md` 참조 실측(tasks·history 제외):

| 제거된 서버 | 참조하는 곳 |
|---|---|
| `context-search` | **에이전트 9종 전부**의 `tools:` + `CLAUDE.md`(§7 에서 은퇴 표기) + `distribute`·`manage-domain` + 스킬 8종의 `context_search` 언급 |
| `redmine-tracker` | `code-validator`(도구 8종 + 절차 3곳) · `review-consultant`(도구 3종 + 절차 2곳) · `CLAUDE.md:477`(도구 목록 아직 살아 있음) |
| `master-orchestrator` | `cluster-selftest` · `distribute` · `review-work` · `tdd-dryrun` |
| `task-queue` | `CLAUDE.md`(산문) · 위 네 스킬 |
| `local-llm-runner` | **0건** |

[주의] **`tools:` 에 없는 서버를 적어 두면 오류가 아니다 — 그 도구 없이 그냥 돈다.** §9-3 의
「조용히 0 으로 답하는 입구」와 같은 실패 계열이고, 이번 것은 한 단계 더 조용하다(응답이 아니라
**능력**이 사라진다). 8종은 온톨로지 검색을 잃은 채 그럴듯하게 답할 것이다.

바로 대체되는 것: `combined_search`→`mcp__ax-client__search_context` · `list_domains`→동명 ·
`get_domain_manifest`→`get_domain_layer`(§6 에서 매니페스트 필드를 동승시켜 둔 것이 여기서 쓰인다).

**위임 구멍 2개 — 사용자 결정 대기:**

1. **Redmine 읽기·수정 미위임** — `get_issue`·`list_issues`·`update_issue`·`list_statuses`·
   `list_trackers`. `ax-client` 에는 `redmine_note`(노트 추가) 하나뿐이다. `code-validator`·
   `review-consultant` 의 절차가 이것에 의존한다
2. **`get_task_template` 미위임** — `code-writer` 가 쓴다(`list_task_templates` 와 함께 기지의 미위임)

선택지: ⓐ 마스터에 Redmine 읽기 위임을 추가하고 에이전트를 재배선 · ⓑ 에이전트·스킬을 은퇴
(우리 `/distribute`·`ax-review` 가 대체) · ⓒ 매핑 가능한 것만 재배선하고 구멍은 [주의] 로 표기.

[중요] **이 결정은 「distribute 은퇴 여부」와 같은 결정이다** — `master-orchestrator`·`task-queue` 를
참조하는 네 스킬(`cluster-selftest`·`distribute`·`review-work`·`tdd-dryrun`)은 전부 원전 로컬
오케스트레이션이고, 우리 클러스터가 그 자리를 이미 갖고 있다. 하나씩 재배선할지, 묶어서 은퇴할지가
같은 질문이다.

## §11 대조 — 「어느 쪽이 정본인가」를 세고 나서 정했다 (2026-08-20)

사용자 지적 둘이 방향을 바꿨다. ① *"단일 파일의 수정이라면 요청한 `.33` 이 직접 처리하는게
빠를꺼야 … 뭘 바꾸려는거야?"* — 내가 낸 선택지(에이전트 은퇴 / 구멍은 [주의] 표기)는 전부
**바꾸는** 얘기였다. 이 프로젝트는 포팅이므로 질문은 *"원전에서 되던 것 중 아직 안 옮겨진 게
무엇인가"* 여야 했다. ② *"다른 프로젝트 세팅할때 그럼 너 뭘 보고 설정하려고?"* — 작업장 자산이
**어느 저장소에도 없었다**(게임 저장소 `.gitignore` 가 `.claude/` 전체를 뺀다 · `git ls-files
.claude` = 0).

### 원전은 무엇을 배포했나 (`build.bat` 실측)

exe **12종** + onnx 임베딩 + `tools/{sqlite3,jq}`. [중요] **zip 에 에이전트·스킬은 없다** —
`build.bat` 이 zip 직전에 `agents`·`skills`·`hooks`·`context`·`CLAUDE.md`·`.mcp.json` 을 **일부러
rmdir 한다**(*"PC 별 환경 파일이 zip 에 섞이면 클라 PC 가 자기 설정을 덮어쓴다"*). `watch.exe` 가
첫 실행에 생성한다 — **원전의 정본은 파일이 아니라 생성기**다(`agent_defs.py` 41KB ·
`skill_defs_*.py` 149KB · `project_claude_md.py` 30KB · `config_init.py`·`setup.py` 49KB).
우리 대응물은 `master/client/bundle.py` + `skills/ax-*` 로 **이미 같은 모양**이고, 빠진 것은
그 생성기의 나머지 절반이었다.

### 대조 결과 — 정본은 한쪽이 아니다

원전 템플릿을 직접 import·렌더해서 `.33` 산출물과 비교했다(`setup.py:_build_agent_md` 재현).

| 항목 | 앞선 쪽 |
|---|---|
| 에이전트 11종 · 스킬 10종 | **동일** (드리프트 0) |
| `ue-editor-operator` | **원전** — `.33` 이 37줄 부족 |
| `manage-domain`·`manage-task`·`CLAUDE.md` 블록·`.mcp.json` | **우리** (어제 재배선) |
| `manage-contract` | 원전에만 — [완료] `#152` 재범위(태그 소스 0건), 새 구멍 아님 |

[중요] **렌더러를 잘못 재현해 한때 12종 전부 「다름」으로 읽혔다** — 프론트매터 닫는 `---` 를
빼먹었다. 그대로 보고했으면 *"`.33` 산출물이 전부 드리프트했다"* 는 거짓 판정이 됐다.
**대조 도구부터 대조 대상으로 검증한다**(원전 렌더러 코드를 읽고 한 줄씩 맞춘 뒤 재실행).

[중요] **`.33` 에 빠진 37줄 중 실질은 계약 기능이 아니라 운영 교훈이다** — *"쓰기 성공 응답을
믿지 말 것 — `set` 계열이 no-op 에도 `true` 를 반환한다"*(원전 실측 2026-08-02)와 **mutation 후
재조회 검증 의무**. 작업장의 에디터 조작 에이전트가 그것을 모르는 상태였다. 이식 가치가 분명한
쪽은 이것이고, §4(게임 소스 갭 → `manage-contract` 핸드오프)는 `#152` 결정에 묶여 있다.

## §12 위임 구멍 이식 — `ax-client` 14 → 21종 (2026-08-20)

대조(§11)가 정한 순서의 2번. **원전에서 되던 것을 옮긴 것이고, 새로 설계한 것은 없다.**

| 새 도구 | 원전 자리 | 어디로 |
|---|---|---|
| `redmine_list_issues` | `redmine_tracker.list_issues` | **큐 8101** `GET /api/v1/redmine/issues` |
| `redmine_get_issue` | `.get_issue` | 큐 `GET /api/v1/redmine/issue/{id}` |
| `redmine_meta` | `.list_statuses` + `.list_trackers` | 큐 `GET /api/v1/redmine/meta` |
| `redmine_create_issue` | `.create_issue` | 큐 `POST /api/v1/redmine/issue` |
| `redmine_link_commit` | `.link_commit` | 큐 `POST /api/v1/redmine/link-commit` |
| `list_task_templates`·`get_task_template` | `context_search.get_task_template` | **8103** — 라우트가 이미 있었다 |

[중요] **읽기라도 8103 에 두지 않았다.** §5 에서 배운 것을 그대로 적용했다 — 그 포트의
`/api/v1/*` 는 무인증 공개라 **일감 본문과 검수 이력이 LAN 아무에게나 열린다.** 반대로
온톨로지·태스크 템플릿은 공개 뷰가 이미 같은 데이터를 보여 주므로 8103 이 맞는 자리다.
**「읽기냐 쓰기냐」가 아니라 「그 데이터가 공개 표면에 있어도 되냐」가 기준이다.**

원전과 다르게 한 곳 둘:

- **`list_statuses`+`list_trackers` → `meta` 하나로.** 절차가 늘 둘을 같이 쓴다(상태 이름 확인
  → 갱신). 나누면 왕복만 는다. 버전(마일스톤) 목록과 [중요] *"닫힌 상태는 「완료」뿐"* 이라는
  **우리 규약 문장을 응답에 실어** 보낸다 — 도구가 스스로 말하지 않으면 세션이 상태를 잘못 고른다
- **`fixed_version` 은 부분 일치.** 우리 버전명이 *"마일스톤 6 — 개선·확장"* 처럼 길어서 사람은
  `마일스톤 6` 만 쓴다(실측). [주의] 트래커·버전 이름을 못 찾으면 **조용히 전체를 주지 않고
  `error`** 로 답한다 — 필터가 안 걸린 목록은 거짓말이다

### [주의] `code_recipes` 2종은 이식하지 않았다 — 입력이 0이다

실측: 신호 `ModularStage/recipes/_signals.jsonl` **1건** < 합성 문턱 **5**(`RECIPE_MIN_SIGNALS`),
그래서 합성된 레시피·안티패턴 **0건**. `#152`(`@ms-contract` 태그가 미러 소스에 0건 → 재범위)와
**같은 판단**이다 — 없는 것 위에 도구를 얹으면 도구가 거짓으로 빈 답을 준다.
`code-recipes` MCP 등록은 `.mcp.json` 에 남아 있어 `code-writer` 의 참조는 깨지지 않는다.

### 게이트마다 라이브 (전부 실측)

    유닛      3633 → 3657 통과 · 실패 0 (신규 계약 테스트 2벌 포함)
    스코프    요청자 토큰 200 · **워커 토큰 403** · 무토큰 401 · **8103 에는 404**
    조회      meta = 상태 5종(신규·진행·해결·검토·완료)·트래커 1·우선순위 3·버전 6
              issues(status=open, fixed_version="마일스톤 6") → **3건** (#226·#169·#211)
              issue/226 → 노트 2건·description 2693자 · issue/999999 → `error: #999999 없음 (404)`
    쓰기      link-commit ×3 (2be9fc2·5527115·ac2621b → #226) → 노트 5건으로 실제 증가 확인
    배달      `client check` 가 `.33` 불일치를 먼저 짚었다(스킬 3종·client_mcp.py) → `deliver`
              → [중요] **`.mcp.json` 은 `ax-client` 항목만 건드린다**(11종 유지, 4단계 결과 무손상)
    실물      `.33` 배달본 stdio 왕복 — 21종 · 한글 질의 통과 · 없는 템플릿 404 · 0건은 0건이라 말함

[주의] **`redmine_create_issue` 는 라이브 미확인이다** — 확인하려면 실제 이슈가 생긴다. 일감을
만드는 것은 사람의 결정이므로(§*"다음 작업을 스스로 고르지 않는다"*) 유닛으로만 덮었다.
§5 의 `rejected_generic` 과 같은 처리 — **미확인은 미확인으로 적는다.**

[중요] **깨진 테스트가 계약 변경을 증언했다** — `test_client_bundle` 의
*"요청자에게 「소스를 고치지 않는다」를 말한다"* 가 빨간불이 됐다. **그 문장이 요구를 좁힌
자리였다.** 테스트를 원전 규칙(분기·경계·a/b/c·마스터 큐 단일)으로 갈아 고정했다.

## §13 재배선 — 32곳, 그리고 「지우지 않고 말하기」 (2026-08-20)

§11 이 정한 순서의 3번. 먼저 머지 방향대로 **`ue-editor-operator` 를 원전본으로 올렸다**
(56 → 90줄 — §11 이 짚은 mutation 재조회 검증 의무·리플렉션 한계·게임소스 갭 절차가 들어왔다).
그 위에 재배선했다.

| 옛 이름 | 새 이름 | 건수 |
|---|---|---|
| `context-search__combined_search` | `ax-client__search_context` | 10 |
| `redmine-tracker__update_issue` | `ax-client__redmine_note` | 4 |
| `redmine-tracker__list_statuses`·`list_trackers` | `ax-client__redmine_meta` | 5 |
| `redmine-tracker__get_issue` | `ax-client__redmine_get_issue` | 4 |
| `redmine-tracker__list_issues`·`create_issue`·`link_commit` | 각 대응물 | 4 |
| `context-search__get_task_template` | `ax-client__get_task_template` | 2 |
| `context-search__get_domain_manifest`·`list_domains`·`get_object_spec` | 각 대응물 | 3 |
| `code-recipes__log_writer_signal` | `ax-client__log_writer_signal` | 2 |

총 **32곳 · 9파일**. [중요] **매핑을 명시적으로 뒀다** — 정규식 일괄 치환은 미이식 도구까지
이름만 바꿔 **「있는 척하는 도구」**를 만든다. 안 바꾼 것은 `unreal-mcp`(로컬 에디터가 맞는 자리)와
`code-recipes__find_recipes`·`get_anti_patterns`(합성 입력 0건, §12).

### [중요] 죽은 허용목록 항목은 지우고, 사라진 절차는 **말한다**

`tools:` 에 남은 죽은 항목을 걷어냈다 — **그게 조용한 실패의 자리**다. 다만 지우면서 그 능력이
없어진 사실을 본문에 [주의] 로 남겼다. 지우기만 하면 다음 세션은 **그 절차가 원래 없었다고 읽는다.**

- `code-validator`: 14 → 12종. `create_review_issue`(리뷰 MD 파싱 → 심각도별 이슈 자동 생성)는
  **미이식** → 대신 *"골라내는 일은 네가 한다"* 로 3단계 절차를 적어 줬다(`mid` 이상만 골라 →
  `redmine_create_issue` → URL 조립). [주의] 모듈별 한 건씩 — 원전이 그룹핑한 이유가 그것이다
- `ue-editor-operator`: 11 → 9종. **그래프 조회 3종**(`find_subclasses`·`dependency_search`·
  `find_ancestors`)은 위임 여부가 아직 #226 의 열린 칸이다 → *"필요하면 **선언부를 직접 읽어라** —
  이 프로젝트 규약이 이미 그렇다"*. **없는 도구를 부르거나 추론으로 때우지 않는다**를 명시
- 중복 정리: `list_statuses`+`list_trackers` 가 둘 다 `redmine_meta` 로 접히면서 허용목록에
  같은 이름이 두 번 생겼다(§12 의 「하나로 합침」 결정이 남긴 흔적) — 순서 보존 dedup

### 재발 방지 — 테스트가 이제 이것을 본다

`test_client_bundle::test_workshop_assets_reference_only_live_tools` (5칸):

    ① 에이전트에 은퇴 서버 참조 0건        ② 어디든 `tools:` 줄에 죽은 항목 0건
    ③ 참조된 `mcp__ax-client__*` 가 전부 실재하는 21종 안 (지어낸 이름 금지)
    ④ 남은 옛 이름은 **알려진 결정 대기분뿐** (#226)   ⑤ 미이식·미위임을 [주의] 로 말한다

[중요] **「어디서나 0건」은 틀린 규칙이었다** — 처음 그렇게 쓰자 정당한 언급 둘이 빨간불이 됐다:
`CLAUDE.md`·`manage-domain` 의 *"로컬 `context-search` 는 은퇴했다, 부르지 말 것"*(**금지 문장**)과
원전 로컬 오케스트레이션 스킬 4종(`distribute`·`cluster-selftest`·`review-work`·`tdd-dryrun` —
**은퇴 여부 결정 대기**). 그래서 강한 규칙은 에이전트와 `tools:` 줄에만 걸고, 나머지는
**알려진 목록과 같은지**를 잰다 — 결정 대기 목록이 조용히 늘면 그때 빨간불이 된다.

### 실측

    유닛      3657 → 3664 통과 · 실패 0
    이름 검증 참조된 ax-client 도구 15종 전부 실재 (21종 중) — 지어낸 이름 0
    .33 적용  에이전트 10파일 전송(백업 `~/claude-workspace/backups/33-agents-20260820/`)
              → 옛 이름 **0건** · `mcp__ax-client__` **10파일** · git 상태 불변(사용자 `.uasset`만)

[주의] **개행 함정을 또 밟았다** — `ue-editor-operator` 를 원전본으로 쓸 때 `read_text()` 로
CRLF 를 판정했다. 그 함수는 개행을 **번역해서 읽어** `'\r\n' in text` 가 늘 False 다 → LF 로
써 버렸고 형제 파일들과 달라졌다. **개행 판정은 `read_bytes()` 로** 한다. 리포트 27 §3 의
CRLF 함정과 같은 계열이고, 그때는 비교에서, 이번엔 쓰기에서 걸렸다.

## §14 배달 경로 — 손으로 맞추던 것을 계약으로 (2026-08-20)

§11 이 정한 순서의 4번. 3번까지는 저장소를 고친 뒤 **scp 로 손수 맞췄다** — 그 상태에서는
누가 한쪽만 고치면 조용히 갈린다.

    plan     `.claude/ 작업장 자산 31개 (agents 13 · hooks 1 · rules 5 · skills 12)` +
             `.claude/CLAUDE.md — AgentWatch:Start 블록만 교체`
    deliver  31개 쓰기(되읽어 해시 대조) + 마커 병합
    check    요청자 행에 `작업장 자산 31개 일치` — **한 번의 ssh 로 트리 해시**를 뜬다

[중요] **역할 게이팅**: 워커에게는 안 보낸다. 실측이 근거다 — `.2`·`.43` 에 `.claude/agents`·
`skills` **0건**. 이 자산은 사람이 대화로 쓰는 절차이고, 워커는 claimer·`ax-work` 로 돈다.
안 쓰는 곳에 미리 뿌리면 그쪽도 낡기 시작한다.

[중요] **두 가지 쓰기 방식을 섞지 않았다.** `agents`·`skills`·`rules`·`hooks` 는 **파일째**
(원전도 매 실행 재생성했다). `.claude/CLAUDE.md` 는 **마커 블록만** — 그 파일에는 사람이 쓴
프로젝트 지식이 섞여 있다. [주의] **마커가 없으면 안 쓰고 사유를 돌려준다** — 어디가 관리
블록인지 모른 채 덮으면 사람 문서가 날아간다(옛 사고: 셸 경유 읽기가 빈 문자열을 줘서 블록이
두 번 붙은 일이 있었다. 같은 함정의 반대편이다).

### [중요] 실결함 하나 — 배달이 개행을 섞었다. 해시 대조로는 안 잡힌다

첫 배달 직후 실측: `.claude/CLAUDE.md` 가 **CRLF 362 + LF 172 혼합**, 크기 172바이트 감소.
원인은 병합의 두 입력이 서로 다른 개행을 쓰기 때문이다 —

    _remote_read()  → read_text() 로 읽는다 → **CRLF 를 LF 로 번역**(그 함수의 계약)
    정본 파일        → read_bytes() 로 읽는다 → CRLF 그대로
    head + block + tail  → 한 파일에 두 종류가 섞인다

[중요] **해시 대조는 이걸 못 잡는다** — *보낸 것과 도착한 것이 같은지*만 재기 때문에
*"보낸 것 자체가 섞여 있었다"* 는 통과한다. **배달 검증이 있어도 배달물이 옳다는 뜻은 아니다.**
`with_newlines(text, windows=)` 로 쓰기 직전에 통일했고, 재배달 후 **원본과 바이트 동일**
(43882 bytes · CRLF 534 · LF 0) 확인.

[완료] 옛 경로(루트 `CLAUDE.md`)에는 이 병이 없다 — 세 대 모두 **순수 LF**(.33 278 · .2 262 ·
.43 261줄). 전체가 `_remote_read` 를 지나 한 종류로 수렴한 덕이다. 이번 것만 정본이 CRLF 라
섞였다.

[주의] **개행 함정을 오늘 세 번 밟았다** — §11 대조에서(비교), §13 원전본 쓰기에서(`read_text`
판정), §14 병합에서(두 입력의 개행 차이). 규칙 하나로 정리한다: **파일의 개행을 판단하거나
보존해야 하면 `read_bytes()` 를 쓴다. `read_text()` 는 개행을 번역한다.**

### 실측

    유닛      3664 → 3681 통과 · 실패 0 (배달 계약 테스트 17칸 신설)
    배달      31개 · `.claude/CLAUDE.md` 마커 병합 → 사람 문서 **0줄 변경**(바이트 동일)
    check     `.33` 작업장 자산 31개 일치 · `.2`·`.43` 은 대상 아님(역할 게이팅)
    git       `.33` 상태 불변 (사용자 미커밋 `.uasset` 1건 그대로)

## §15 `.2` 원전 바이너리 정리 — 602.4MB, 그리고 **셋째 설치본**을 찾았다 (2026-08-20)

사용자 승인으로 `.2`(윈도우 워커)의 원전 exe 함대를 지웠다. `.33` 의 `worker.exe` 와 같은
부류(재빌드 가능한 AgentTest 산출물)라 백업 없이.

    E:\trunk\ModularStage\.claude\mcp\        18 files  576.7 MB  (exe 12종 + onnx 임베딩 모델)
    E:\trunk\ModularStage\.claude\daemons\worker.exe   25.7 MB
    → 실측 회수 602.4 MB (E 드라이브 free 증가로 확인)

[중요] **「잠들어 있다」는 내 판단이 틀렸다 — 돌고 있는 것이 있었다.** 지우기 직전 프로세스를
세니 `context_search.exe` **4개**가 살아 있었다. 그런데 경로가 달랐다:

    실행 중 : E:\trunk\ModularStage\**AgentWiki**\.claude\mcp\context_search.exe  (4개)
              20:56 에 `claude.exe`(pid 21248) 가 띄운 stdio MCP — 살아 있는 세션이다
    삭제 대상: E:\trunk\ModularStage\.claude\mcp\*                          (미실행 · 미등록)

**`.2` 에는 원전 AgentWiki 설치본이 따로 있다** — 우리가 한 번도 세지 않은 **셋째 설치본**
(mcp 7파일 190.2MB, 무손상). `.33`·`.2` 의 프로젝트 루트만 보고 「원전 함대를 정리했다」고
적었던 §2 는 그만큼 좁았다.

[중요] **경로가 아니라 프로세스로 물었기 때문에 살았다.** 삭제 스크립트가 첫 단계에서
*"이 경로 아래 도는 프로세스"* 를 세고, 있으면 **중단**한다(`ABORT`). 파일 목록만 보고 지웠으면
살아 있는 세션의 MCP 를 끊었을 것이다 — 그리고 그건 남의 기계에서다.

[주의] `.2` 에는 아직 `_archive_agenttest_20260809`·`tools`·`vector_db`·`vector_db_client`·
`context.bak-20260718_165030` 이 남아 있다. **세지 않았으므로 판단하지 않는다** — 다음 정리의
입력이다.

정리 후 배선 확인: `.ax/`(config·lib·token·claimer.lock) 무손상 · `AxClaimer` 실행 중 ·
`client check` 세 대 모두 OK · 큐 200.
