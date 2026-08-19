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
