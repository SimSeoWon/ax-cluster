---
name: manage-domain
description: 도메인 온톨로지를 생성·제거·수정하는 통합 관리 인터페이스. 도메인 1건을 모든 표면(MD + 패키지 yaml + class_graph DB + 도메인 검색 인덱스)에서 일괄 제거하거나, 멤버(클래스)·필드(요약·태그·상위도메인·협력도메인)를 수정하거나, 명시 스펙으로 새 도메인을 생성한다. L1/L2/L3 개별 항목(오탐 action/invariant 등)을 도메인 전체 재합성 없이 직접 수정·삭제하고, 대화형 편집 세션 중엔 스테이징 사본에서 작업해 라이브 서비스에 영향을 주지 않는다. 자연어 발화 "도메인 삭제/제거", "X 도메인 지워줘", "도메인에 클래스 추가", "이 클래스를 MissionRuntime 에 넣자", "도메인 협력관계 수정", "서브도메인 만들어줘", "새 도메인 생성", "이 액션/불변조건 내용 고쳐줘", "이 항목 삭제해줘" 등에 발동. 검색 동시출현 기반 자동승급(폐기)과 달리 사람이 결정한 구조를 모든 표면에 일관 반영. cleanup_inactive_domain(DB row·inactive 한정)의 상위 도구.
---

# Manage Domain — 도메인 CRUD 통합 관리

> [주의] **온톨로지 조회·별칭 등록은 마스터 위임(`mcp__ax-client__*`)으로 바뀌었다** (2026-08-20).
> 로컬 `mcp__context-search__*` 는 은퇴했다 — 그 인덱스는 낡았고 objects/actions 를 0/0 으로 답한다.
>
> [주의] **그래프 조회 3종은 아직 위임되지 않았다** — `find_ancestors` · `find_subclasses` ·
> `dependency_search`. 이 절차들이 그것에 의존하므로, 부르기 전에 **응답이 오는지 먼저 확인**하고
> 안 오면 마스터에 위임 추가를 요청한다. 조용히 추측으로 대체하지 말 것.

## 목적

도메인 생성/제거/수정 인터페이스. 기존엔 제거(`cleanup_inactive_domain`)가 DB row·inactive
한정이고, 생성(`/api/v1/domains`)이 검색기반이라 불완전했음. 본 스킬은 **모든 표면**을
일관 처리:

1. `.claude/context/_domains/<D>.md` (사람 SSOT)
2. `.claude/ontology/domains/<D>/` (기계 SSOT 패키지 — objects/actions/invariants/manifest)
3. `class_graph.db` — `domains` row + `class_ontology`(ontology_domain=D) rows
4. 도메인 검색 인덱스 — `ontology_domains`(ChromaDB) + `bm25_domains.db`

## 환경 확인 (필수, BLOCKING)

1. `.claude/vector_db/class_graph.db` 존재 확인 (배포 프로젝트/메타 저장소).
2. server_mode 면 `<server_url>/api/v1/ontology/*` HTTP. 단독 모드면 `context_search` MCP
   도구 직접 호출. 응답 실패 시 즉시 종료 + RAG 서버 상태 안내 (localhost fallback 금지).
3. 서버 PC(=watch.exe 호스트)에서만 의미 — 비대상 PC 면 안내 후 종료.

## 호출 방법

- `/manage-domain list` — 도메인 목록 + 상태 + 멤버 수 (read-only)
- `/manage-domain remove <D>` — 완전 제거 (active 면 `--force` 요구)
- `/manage-domain edit <D>` — 멤버 추가/제거·필드 수정 대화
- `/manage-domain create <Name>` — 명시 스펙 신규 도메인
- `/manage-domain rename <old> <new>` — 도메인 개명 (모든 표면 + 참조 일괄)
- `/manage-domain rename-class <old> <new>` — **클래스** 개명·이동 cascade (force-full 재합성)
- `/manage-domain edit-item <D> <layer_type> <item_name>` — L1/L2/L3 항목 1건 편집(patch) + 재합성 잠금
- `/manage-domain remove-item <D> <layer_type> <item_name>` — L1/L2/L3 항목 1건 삭제
- `/manage-domain edit-session start|commit|discard <D>` — 오래 걸리는 대화형 편집용 스테이징 세션
- `/manage-domain log-tags <D> [list|set|remove]` — 실증 테스트용 로그 태그/CVar 사이드카 관리 (η.12.3)
- 자연어 — "X 도메인 삭제", "이 클래스 MissionRuntime 에 넣자", "협력 도메인에 Y 추가", "X 도메인 이름을 Y 로 바꿔줘", "클래스 A 를 B 로 개명했어", "이 액션 설명 틀렸어 고쳐줘", "이 불변조건 지워줘", "이 도메인 로그 태그 등록해줘", "게임팀이 CVar 넣었대, 온톨로지에 기입해줘"

## 흐름

### 제거 (remove)

1. `audit_ontology_drift` + `_domains/*.md` 로 대상 도메인 현황 파악 — status(active/draft),
   멤버 수, 패키지 obj/act 수를 사용자에게 **표면별 영향 요약**으로 보고.
2. AskUserQuestion 으로 삭제 확정. **active 도메인이면 별도 경고** + `--force`(allow_active)
   명시 확인 — 사용자 SSOT 가 사라짐을 분명히 고지.
3. `delete_domain(domain_name, allow_active=<bool>)` 호출. 4개 표면 일괄 정리.
4. 결과 보고 — surfaces(md/package_files/db_domain_row/db_classifications) + reindex 카운트.

### 수정 (edit)

- **멤버 추가** — 후보를 도메인에 편입. 후보 출처 = `.claude/context/_domains/_unassigned.md`
  (미분류 워크리스트 — active 도메인 인접 후보 + 추천 도메인) 또는 사용자가 지정한 클래스.
  **자동 점수·편입 X** — 아래를 대화로 진행하며 그 자리에서 신호를 끌어와 가이드·경고·옵션 제시:

  1. **적합성 가이드** — 후보별로 구조 신호를 조회해 **근거와 함께** 제시 (단정 금지):
     - `find_ancestors` / `find_subclasses` — 후보의 조상·자손이 대상 도메인 멤버인가
       (`mcp__ax-client__get_domain_layer(domain)` 로 멤버 확인 — 이름 목록·책임·layer_counts 가
       한 응답에 온다). 같은 상속 계층이면 **강한 적합 신호**.
     - `dependency_search(file, direction=both)` — 후보 파일이 도메인 멤버 파일과 #include 결합
       (보조 신호 — basename 매칭이라 약하게 가중).
     - `mcp__ax-client__get_object_spec(domain, class)` — 후보 kind/tier/parent/file
       ([주의] domain 인자가 필요하다). _unassigned.md 의 SubDir 인접은
       **약한 기본 신호**.
     → "이 클래스는 <근거>로 적합해 보임 / 애매함 / 다른 도메인이 더 맞아 보임" 을 근거로 보고.
  2. **크기 경고** — `mcp__ax-client__get_domain_layer(domain)` 의 `layer_counts` 합으로 규모 확인.
     편입 후 과대(가이드 임계: 멤버 ~40+ 또는 L3 편중)면 경고하고 서브도메인 분리를 옵션으로 띄움.
  3. **서브도메인 제안** — 후보가 특정 하위 경로/책임에 군집하거나 도메인이 비대하면
     `create_domain(name, members=[...], parent_domain=<대상>)` 분리를 제안 (독립 패키지, 계층 링크).
  4. **옵션 제시 / 의견 질의** — AskUserQuestion 으로: (a) 그대로 `add_domain_members`
     (b) 서브도메인으로 분리(`create_domain` parent_domain=) (c) 보류·제외. 적합성이 약하면
     그 점을 명시하고 사용자 의견을 물을 것.
  5. **확정 후에만** `add_domain_members(domain, class_names)` 또는 `create_domain(...)`.
     active 면 재합성 trigger 큐잉됨. **silently auto-add 절대 금지** — 가이드·경고·옵션
     제시까지가 Claude 몫, 결정·편입은 유저.
- **멤버 제거** — `remove_domain_members(domain, class_names)`.
- **배치 편집 (per-edit refresh 누적 차단)** — 한 도메인에서 멤버를 **여러 번 연속 add/remove** 할
  때는 매 호출 `defer_refresh=True` 로 재합성 트리거를 보류하고, 편집을 **모두 마친 뒤**
  `/refresh-ontology <도메인>` 1회로 클린 full 재합성. per-edit partial(scope) 재합성이 반복되면
  중복·stale 이 누적된다 (add 는 기본 partial). 단발 편집이면 그냥 호출(기본 즉시 partial).
- **필드 수정** — `edit_domain_field(domain, parent_domain=/status=/tags=/collaborates_with=/summary=)`.
  제공한 인자만 적용. `collaborates_with`/`parent_domain` 편집이 뷰어 연관/계층 링크를 갱신.

### 항목 편집 (edit-item / remove-item / edit-session)

**왜 존재하는가 (방향성)** — 지금까지 L1(objects)/L2(actions)/L3(invariants) 는 LLM
생성만 가능했다. 개별 항목 하나(오탐 action, 잘못 귀속된 invariant 등)를 고치려면
도메인 전체를 `/refresh-ontology`(LLM 재합성, 비결정적)로 통째 재생성해야 했다 — 항목
하나 고치자고 나머지 전부가 흔들리는 구조. 이 서브커맨드는 **항목 단위로 직접
편집·삭제**하고 `verified_by_user: true` 로 잠가 다음 재합성이 그 항목을 덮어쓰지 않게
한다. 서버가 상시 서비스 중이므로, 오래 걸리는 대화형 편집은 `edit-session` 으로
스테이징 사본에서 진행 — 라이브는 세션을 `commit` 할 때만 한 번에 교체된다
(`context_search` 의 `DoubleBufferedIndex` 와 동일한 Live/Work 철학). 짧은 1회 편집이면
세션 없이 `edit-item`/`remove-item` 만 호출해도 즉시 라이브에 반영된다 — 세션은 "오래
대화하며 여러 번 고칠 때" 를 위한 선택적 안전장치일 뿐, 매번 강제하지 않는다.

- `/manage-domain edit-session start <D>` — 스테이징 사본 생성(멱등 — 이미 있으면 이어서
  사용). 이후 이 도메인의 `edit-item`/`remove-item` 호출은 자동으로 사본을 대상으로 삼는다.
- `/manage-domain edit-item <D> <layer_type> <item_name>` — 현재 항목 내용을 조회해 보여준
  뒤, AskUserQuestion 으로 고칠 필드:값을 확정 → `edit_ontology_item(domain, layer_type,
  item_name, patch)` 호출. `layer_type` ∈ `objects`/`actions`/`invariants`. patch 는
  top-level 키만 얕게 덮어씀 — `trigger`/`flow`/`implementation` 같은 중첩 필드를 고치려면
  그 키 전체를 다시 넘길 것. 결과에 `verified_by_user: true` 가 세팅됐고 다음 재합성에서도
  보존됨을 사용자에게 안내.
  - **응용 — RAG 시소러스 별칭 (Phase η.10/η.11)**: 클래스의 한국어·영문 별칭(몬스터/몹/
    괴물/적/Enemy 등)을 등록하면, 다음 `search_context` 부터 그 표현이 쿼리에 등장할 때
    자동으로 클래스명이 덧붙어 BM25·벡터·도메인추론 세 채널이 동시에 혜택을 받는다.
    **등록은 반드시 전용 도구 `mcp__ax-client__add_object_alias(class_name, alias)` 로 할 것**
    (2026-08-20: **domain 인자 없음** — 서버가 찾는다. 범용어·짧은 표현은 마스터 가드가
    `rejected_…` 사유로 거부한다) —
    이 `edit-item`(patch={"aliases":[...]})으로 직접 덮어쓰면 top-level 얕은 덮어쓰기라
    기존 별칭 전체가 사라지는 함정이 있다(Phase η.11 에서 발견). `add_object_alias` 는
    기존 목록을 내부에서 읽어 병합하므로 안전하게 누적된다. 사용자가 작업 요청에
    `<구절>[ClassName]` 형태로 직접 선언하면(예: "몹 스폰 로직[AMonster]") 그 자체가
    등록 신호 — 메인 세션이 **자동으로** `add_object_alias` 를 호출한다(사람이 스킬을
    별도 실행할 필요 없음, 이미 등록된 표현이면 조용히 스킵).
- `/manage-domain remove-item <D> <layer_type> <item_name>` — 항목 내용을 표시하고 삭제
  확정(**되돌릴 수 없음** 명시) 후 `delete_ontology_item(domain, layer_type, item_name)` 호출.
- `/manage-domain edit-session commit <D>` — 스테이징 사본 → 라이브 원자적 교체(rename swap)
  + 도메인 인덱스 1회 재빌드. 세션 중 라이브가 바뀐 게 감지되면(백그라운드 재합성 등)
  경고만 하고 그대로 진행 — 온톨로지 편집은 저빈도 이벤트라 새 락·머지 인프라 없이 로그
  가시성으로 충분하다는 판단([[feedback_use_system_logs]]).
- `/manage-domain edit-session discard <D>` — 스테이징 사본 폐기, 라이브 무영향.

### 실증 테스트용 로그 태그/CVar 사이드카 (log-tags)

**왜 존재하는가** — 기획팀이 `AgentWiki` 로 실제 플레이 로그를 대조해 체크리스트를 실증하려면,
어떤 로그 태그(카테고리)를 켜야 하는지·그 태그를 켜는 콘솔변수(CVar)가 뭔지가 온톨로지에
있어야 한다(`docs/rag-system.md` § η.12.3). **저작 방향은 (b) 개발자 선작성으로 확정** —
게임팀이 실제 코드에 CVar+태깅 로그를 먼저 구현한 **뒤**, 이 서브커맨드로 사람이 실제
이름을 확정 기입한다. 자동 생성·자동 편입 없음 — 배치가 만드는 것은 어디에 태깅하면
좋을지 제안하는 리포트(`_domains/_log_tagging_candidates.md`)뿐, 사이드카 자체는 항상
사람이 확정한다.

- `/manage-domain log-tags <D> list` — 현재 등록된 entries 조회 (`get_log_categories`).
- `/manage-domain log-tags <D> set <tag> <cvar> [related_invariants...]` — entry 등록·갱신
  (`set_log_category`, tag 기준 upsert). `related_invariants` 를 넘기면 그 invariant 들의
  `list_invariants` 등 조회 응답에 `log_tags` 필드가 자동 첨부되어, 위키 세션이 "이 invariant
  는 로그로 검증 가능하다"를 스스로 판단하게 된다 — 등록 전 `_log_tagging_candidates.md` 의
  제안값(권장 tag/cvar 이름)을 기본값으로 보여주되, 실제 구현과 다르면 사용자 확인 후 수정.
- `/manage-domain log-tags <D> remove <tag>` — entry 1건 삭제(**되돌릴 수 없음**, 삭제 전 내용
  표시·확정).
- 사용자가 "게임팀이 LogMissionAnnihilation 이랑 mission.LogAnnihilation.Enable 넣었대" 처럼
  실제 구현 완료를 전해주면, 관련 invariant 를 함께 물어(또는 `_log_tagging_candidates.md`
  에서 추정) `set` 을 호출 — 자동 추측으로 임의 기입하지 말 것.

### 개명 (rename)

- `rename_domain(old, new)` — 모든 표면(MD+category / 패키지 dir+manifest / class_graph 키 이전 /
  타 도메인 parent_domain·협력 도메인 참조 / 인덱스) 일괄. **결정적(LLM 0)·분류 보존**.
  `--rename-english`(비영문 자동변환)와 별개 — 임의 old→new (예: 참조 시스템에 `ProjectAlpha_` 접두사).
- new 는 영문·무공백 강제(비ASCII 거부), 이미 존재하면 충돌 거부. 즉시 반영(트리거 비동기 아님).

### 클래스 개명·이동 (rename_class)

- `rename_class(old, new[, new_path])` — **클래스**(도메인 아님) 개명/이동 cascade. 소스에서
  클래스를 rename/move 했을 때 온톨로지를 1-step 으로 정착: 영향 도메인 related_classes old→new
  치환 + old 분류 제거 + 영향 active 도메인 **force full 재합성**(partial 아님 → 새 클래스 합성).
- **옛 object yaml 즉시 삭제** — `rename_domain` 이 옛 패키지를 `shutil.move` 로 옮기는 것과 동일
  정신. 온톨로지 yaml 은 기계 산출물이라 자동 정리(`.claude/` 내부는 시스템 관리, 수동 삭제 X).
  MD 본문(prose) old 언급은 사람 편집 영역이라 "수동 갱신 필요" 안내만.
- **status=need_path 면** 새 클래스 경로를 class_graph 에서 확정 못 한 것(미인덱스·옛/새 공존).
  **추측하지 말고 사용자에게 새 파일 경로를 물어** `new_path` 로 재호출.
- 코드 작성 에이전트가 소스에서 클래스를 개명/이동한 직후 본 도구를 호출하면 매핑이 깨끗하게 정착됨.

### 생성 (create)

- `create_domain(name, members=[...], parent_domain="", summary="", collaborates_with=[...], status="draft")`.
- 이름은 **영문 PascalCase 강제** (비ASCII 거부). 멤버는 명시 클래스명 (검색 추측 X).
- 서브도메인은 `parent_domain=<부모>` 지정 — 독립 패키지로 생성되고 뷰어 부모 페이지에
  계층 링크로 노출 (오브젝트/액션은 병합 X).
- draft 로 시작 → 검토 후 활성화 (`edit_domain_field(status="active")` 또는 기존 `/activate`).

## 안전 가드

- **active 제거는 `--force`(allow_active=True) 명시 후만** — 기본 거부 (SSOT 보호).
- **삭제는 되돌릴 수 없음** — Step 2 확정 전 표면별 영향(특히 멤버/분류 수) 반드시 보고.
- **멤버 편입은 사용자 확정 후만** — 적합성·크기·서브도메인을 **근거와 옵션으로** 제시(자동
  점수 레이어 없음, 대화 중 신호 조회)하되 결정·편입은 유저 명시. silently auto-add 절대 금지
  ([[feedback_artifact_addition_default]]). 후보 진입점 = `_domains/_unassigned.md`.
- **항목 삭제(remove-item)는 되돌릴 수 없음** — 삭제 전 항목 내용을 반드시 보여주고 확정받을
  것. 편집(edit-item)은 `verified_by_user: true` 잠금이 걸려 이후 재합성에서 보존됨을 고지.
- 합성(objects/actions yaml 재생성)은 watch.exe 가 trigger 신호로 비동기 처리 (최대 60초).
