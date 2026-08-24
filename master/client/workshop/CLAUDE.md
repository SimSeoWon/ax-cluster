# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

This project is a multiplayer game built on **Unreal Engine 5** using a **Listen Server** network architecture.
In a listen server setup, the host machine acts as both server and client simultaneously.
All gameplay logic must account for this dual-role context.

---

## Gameplay Framework & Architecture

The codebase strictly follows the Unreal Engine native Gameplay Framework.
Full details: `.claude/rules/unreal-architecture.md`

| Class | Role |
|---|---|
| `AGameModeBase` | Server-only game rules, match state, and authoritative logic. Never replicated. |
| `AGameStateBase` | Replicated game state shared across all clients, including the host. |
| `APlayerState` | Per-player replicated data (score, ping, custom stats). Do **not** store per-player state in `PlayerController` or `Pawn`. |
| `APlayerController` | Input handling, HUD management, and client-to-server RPC entry points. |
| `APawn` / `ACharacter` | Visual representation and movement. Delegate complex logic to components. |
| `UActorComponent` | Encapsulate reusable business logic. Required for any logic that needs network replication. |

### Subsystems (No Singletons)

Do **not** create custom Singleton classes. Use Unreal's Subsystem framework instead.

| Subsystem | Use Case |
|---|---|
| `UGameInstanceSubsystem` | Persists across entire app lifecycle (e.g., UserProfileService, session management) |
| `UWorldSubsystem` | Tied to a specific level (e.g., MatchmakingService, EnvironmentManager) |
| `ULocalPlayerSubsystem` | Local player-specific data (e.g., LocalInputSettings, UIState) |

> **Rule:** Subsystems cannot replicate. Do **not** add RPCs or `Replicated` properties to subsystems.

### Data & Decoupling

- Static game data (item stats, configs) → `UDataTable` or custom `UPrimaryDataAsset`
- Do **not** hardcode magic numbers or strings in C++. Expose via `UPROPERTY(EditDefaultsOnly)`.
- Cross-class communication without tight coupling → `UINTERFACE`
- Blueprint-bindable events → `DECLARE_DYNAMIC_MULTICAST_DELEGATE` (e.g., `OnHealthChanged`)

---

## Listen Server — Special Considerations

Because the host is simultaneously a server and a client, the following rules are critical.

### Host Dual-Role Awareness
- The host's `APlayerController` runs in **both** server and client contexts.
- Use `IsLocalController()` to gate UI/HUD logic.
- Use `HasAuthority()` to gate gameplay state mutations.
- Do **not** conflate the two — they serve different purposes.

### RPC Behavior on the Host
- `Client_` RPCs targeting the host execute **immediately** (no network round-trip).
- `Server_` RPCs called from the host execute directly without serialization overhead.
- Avoid redundant state updates triggered by both direct logic and RPC on the host.

### Session Management
- Session lifecycle (`CreateSession`, `FindSessions`, `JoinSession`, `DestroySession`) must be managed in a dedicated `UGameInstanceSubsystem`.
- Do **not** handle session logic inside `AGameModeBase` or `APlayerController` directly.
- When the host player leaves, the session must be explicitly destroyed.

### Host Migration
- Configure `bUseSeamlessTravel` explicitly.
- If host migration is unsupported, ensure clients receive a clean disconnect notice when the host exits.
- Document the host-migration policy in `.claude/rules/session-management.md`.

---

## Networking & Replication

- All gameplay state mutations must guard with `HasAuthority()`
- RPC naming conventions (see `.claude/rules/code-style.md`):

| Prefix | Direction | Execution |
|---|---|---|
| `Server_` | Client → Server | Server only |
| `Client_` | Server → Client | Owning client only |
| `Multicast_` | Server → All | Server + all clients |
| `OnRep_` | — | RepNotify callback on clients |

- Server RPCs handling critical game state or client input **must** include `WithValidation` in the `UFUNCTION` macro.
- Variables requiring replication must be explicitly marked with `UPROPERTY(Replicated)` or `UPROPERTY(ReplicatedUsing=OnRep_FunctionName)` and registered in `GetLifetimeReplicatedProps`.
- Replicated subobject components must call `SetIsReplicatedByDefault(true)` in their constructor.
- Set `NetUpdateFrequency` and `MinNetUpdateFrequency` explicitly on performance-sensitive Actors. Do **not** rely on defaults.
- Group high-frequency replicated variables into a dedicated `UActorComponent` for fine-grained frequency control.

---

## Asset Loading

Full details: `.claude/rules/async-loading.md`

- Use `TSoftObjectPtr<T>` for asset instances (textures, meshes, sound cues).
- Use `TSoftClassPtr<T>` for Blueprint classes to be spawned.
- Do **not** use hard pointers (`T*` or `TObjectPtr<T>`) in `UPROPERTY` for heavy assets unless strictly required.
- Do **not** use `LoadObject<T>()`, `LoadClass<T>()`, or `ConstructorHelpers::FObjectFinder` during gameplay.
- Always load via `UAssetManager::GetStreamableManager().RequestAsyncLoad()`.
- Callback safety: validate the requesting object with `TWeakObjectPtr` or `IsValid()` before using the loaded asset.
- Call `SpawnActor` / `NewObject` **only after** the async load callback confirms the asset is fully loaded, and always on the **GameThread**.
- Cache frequently reused assets (UI widgets, common VFX) in `UGameInstanceSubsystem` or `UWorldSubsystem`.

---

## Pointers & Memory Management

Full details: `.claude/rules/code-style.md`

- Use `TObjectPtr<T>` instead of raw `T*` for all `UPROPERTY` object references in header files.
  - ✅ `UPROPERTY() TObjectPtr<AActor> TargetActor;`
  - Raw pointers are acceptable for local variables inside function bodies.
- Always check `IsValid(Object)` instead of `Object != nullptr`, especially before broadcasting delegates or calling RPCs.
- Any class-level UObject reference must be marked with `UPROPERTY()` to prevent accidental garbage collection.

---

## Casting & Type Checking

- Use `Cast<T>(Object)` and check the result directly with a `nullptr` check only.
  - ✅ `if (UMyComponent* Comp = Cast<UMyComponent>(Actor)) { ... }`
  - ❌ `if (Actor->IsA(...)) { Cast<...>(Actor)->... }` — never double-check with `IsA()`

---

## Include Style (IWYU)

- Keep header includes to an absolute minimum.
- Use forward declarations (`class UMyComponent;`) in `.h` files whenever possible.
- Include specific headers in `.cpp` files only.

---

## Code Rules Summary

- **All comments must be in Korean** (system purpose, important logic, networking behavior)
- Do not build monolithic Actors — delegate complex state and behavior to `UActorComponent`
- `FTimerHandle` must be a **member variable**, never a local variable inside a function
- Replicated components must be created in the constructor via `CreateDefaultSubobject` — never `NewObject` in `BeginPlay`
- `APlayerState` is the correct location for per-player replicated data

---

## Class Prefix Reference

| Prefix | Meaning |
|---|---|
| `A` | Actor |
| `U` | UObject / Component / Subsystem |
| `F` | Struct |
| `E` | Enum |
| `I` | Interface |

---

## Rule Files Reference

| File | Covers |
|---|---|
| `.claude/rules/unreal-architecture.md` | Subsystems, components, data assets, delegates |
| `.claude/rules/code-style.md` | Pointers, casting, RPC naming, IWYU |
| `.claude/rules/async-loading.md` | Soft references, async streaming, caching |
| `.claude/rules/session-management.md` | Listen server session lifecycle, host migration policy |

[주의] **프로젝트 고유 규칙은 이 표에 없다** (`#292`) — `master/client/workshop_by_project/<프로젝트>/`
에 있고 그 프로젝트에만 배달된다. **실제로 무엇을 받았는지는 AX 관리 블록의 실측 목록**을 본다.
(전수 실측 2026-08-24: `rules/mission-editor-mcp.md` 가 `AMissionPrefab`·헥스 타일 구조를 사실로
서술해 NS 에 가면 거짓이었다. 나머지 자산의 프로젝트 언급 5건은 **발화 예시**라 그대로 둔다.)

<!-- AgentWatch:Start -->
## AgentWatch — 자동화 컨텍스트 시스템

Git 커밋 감지 → RAG 컨텍스트 자동 갱신 → 다중 에이전트 분석이 자동으로 동작합니다.

### 필수 선행 절차 (BLOCKING — 모든 코드 관련 요청에 적용)

코드 분석, 기능 추가, 버그 수정, 리팩토링 등 **코드 관련 요청을 받으면 반드시 아래 순서를 먼저 실행**할 것.
Glob/Grep/Read로 직접 코드를 탐색하기 **전에** 이 절차를 완료해야 한다.

#### 1순위 — Ontology 정형 데이터 (디지털 트윈 자산)

> **역할 구분 (중요)**: ontology 는 **네비게이션의 1순위 진입점** — "어느 도메인·어느 클래스·무슨 책임인지" 를 빠르게 잡는 데 *먼저* 쓴다. 그러나 **구현 정합성·최종 판단의 권위는 실제 `.h/.cpp` 코드**다. ontology 는 코드에서 추출된 eventually-consistent 2차 자산이라 stale 할 수 있다 — **방향은 ontology, 확정은 코드**.

발화에 **PascalCase 코드 심볼** (UE 접두 `U*`/`A*`/`F*`/`E*`/`T*`, `Class::Method`, `UCLASS`/`UFUNCTION`/`UPROPERTY` 매크로) 이 등장하면 **RAG 보다 ontology 가 먼저**다. ontology 는:

- `mcp__ax-client__get_domain_layer(domain, layer)` — 그 층의 objects+actions+invariants **이름 목록** + 층 서술 + **tier·summary·layer_counts** + 계층/연관(`parent_domain`·`sub_domains`·`collaborated_by`). **layer 는 정수 1/2/3, 생략(0)이면 전체 층** — 원전의 `get_domain_manifest` 와 `list_actions` 를 이것이 함께 대신한다
- `mcp__ax-client__get_object_spec(domain, name)` — 클래스 1건 full spec (parent·file·tier·confidence·aliases·protected)
- `mcp__ax-client__get_action_spec(domain, name)` — 액션 1건 full spec (trigger/flow/objects_affected/evidence)
- `mcp__ax-client__find_invariants_by_class(class_name)` — 모든 도메인의 invariants 중 그 클래스가 얽힌 것. [주의] **휴리스틱이다** — 우리 `evidence` 는 산문이 아니라 `파일.cpp:84-90` 이라 ① 불변식 `text` 의 클래스명 또는 ② `evidence` 의 접두 뗀 이름(파일 stem)으로 맞힌다. 어느 규칙으로 맞았는지 `matched_by` 로 온다
- `mcp__ax-client__list_domains()` — 서버의 정규 도메인 카탈로그 (이름·tier·objects/actions 수). **도메인 이름을 모를 때 발견용**
- `mcp__ax-client__search_context(query, tags?, n?)` — 마스터 RAG 통합 검색 (시소러스 확장 포함)

[중요] **온톨로지의 정본은 마스터(`192.168.0.57:8103`)다.** 로컬 `mcp__context-search__*` 로 부르지 말 것 — 온톨로지를 리눅스 서버로 옮긴 뒤 그 인덱스는 낡았고, **비었다고 말하지 않고 0 으로 답한다** (실측 2026-08-20: 로컬 240항목은 전부 서버에 있고 서버가 54항목 앞서 있는데도 로컬 exe 는 objects/actions 를 0/0 으로 답했다). 없는 이름을 물으면 마스터 입구는 **404 로 시끄럽게** 답한다 — 그게 맞는 실패다.

[주의] **클래스명만으로는 도메인을 못 찾는다** — 원전 `get_object_spec(class_name)` 은 소속 도메인까지 찾아 줬지만 마스터 위임은 `(domain, name)` 이다. 도메인을 모를 때: ① `list_domains()` → ② 후보 도메인의 `get_domain_layer(도메인)` 이름 목록에서 그 클래스를 찾고 → ③ `get_object_spec(도메인, 클래스)`. `search_context(클래스명)` 결과의 `tags` 첫 항목이 대개 도메인이라 후보를 좁히는 데 쓰되, **그건 힌트이고 확정은 ①~③** 이다.

[주의] **마스터 미연결 시 조용히 낡지 않는다** — `ax-client` 는 마지막 정상 응답을 `_stale: true`·`_cached_at` 표기와 함께 준다. **`_stale` 이 보이면 그 값으로 등재·판정하지 말고 마스터 상태부터 확인한다.**

**도메인 이름 해석 (특히 클라이언트 모드 — 중요)**: ontology 도구는 **정규 이름(ASCII)** 으로 호출해야 한다. 도메인 식별자는 ASCII 가 원칙이며, 이름 결정은 다음 우선순위를 따른다:
1. **발화에 `[Identifier]` 대괄호가 있으면 그게 정규 이름** — 그대로 사용하고 한글 표현·추론으로 바꾸지 말 것. 예: `미션 에디터 창[MissionEditor]` → `get_domain_layer("MissionEditor")`.
2. 대괄호가 없고 이름이 모호하거나 한글이면 **먼저 `list_domains()` 로 서버 카탈로그를 확인**해 정규 이름을 찾아 매칭하라. 로컬 추측(스테일 시드·한글명)으로 바로 호출하면 서버에 없는 이름이라 부재 응답이 난다 (클라이언트는 도메인 이름의 권위가 서버에 있음).
3. **클래스 대괄호 표기 = RAG 시소러스 별칭 등록 신호 (Phase η.10/η.11/η.12.5)** — 발화가 `<구절>[ClassName]`(도메인이 아니라 **클래스**) 형태면, `add_object_alias(ClassName, "<구절>")` 를 호출해 등록한다 (**domain 인자가 없다** — 서버가 클래스 그래프에서 찾는다). **`edit_ontology_item(objects, {"aliases": [...]})`를 직접 쓰지 말 것** — 그건 top-level 얕은 덮어쓰기라 기존 별칭 전체가 사라지는 실제 함정이 있다(Phase η.11에서 발견). `add_object_alias`는 기존 별칭을 내부적으로 읽어 병합하므로 호출자가 현재 목록을 몰라도 안전하다 — 이미 등록된 표현이면 `status: "noop"`으로 조용히 스킵. 예: `몹 스폰 로직[AMonster]` → `add_object_alias("AMonster", "몹 스폰 로직")`. 다음 `search_context` 부터 이 표현이 자동으로 `AMonster`로 쿼리 확장된다(BM25·벡터·도메인추론 동시 개선). 사용자가 대괄호로 **직접 선언**한 것이라 silently auto-add 금지 원칙과 충돌 없음.

   **일괄 등록 절차 (Phase η.12.5, 2026-07-12 — 한 발화에 여러 쌍이 올 때)**: "시소러스에 추가해줘 미션 시스템[UMissionManager], 미션 종료[UMissionResultHandler]" 처럼 `<구절>[ClassName]` 쌍이 **복수** 등장할 수 있다. 다음 순서로 처리한다:
   1. 발화에서 모든 `<구절>[ClassName]` 쌍을 파싱한다 (건수 제한 없음).
   2. 쌍마다 `add_object_alias(ClassName, "<구절>")` 를 호출한다. [중요] **원전의 「등록 전 실존 검증」·「도메인 자동 해석」 두 단계는 사라졌다** (2026-08-20) — `domain` 인자가 없고, 오타 클래스는 서버가 클래스 그래프로 판정해 `not_found` 로 막는다. 다만 `not_found` 가 오면 **조용히 스킵하지 말고** 유사한 이름을 찾아 되묻는다 (예: "`UManager_Misison` 을 찾지 못했습니다 — `UManager_Mission` 을 말씀하신 건가요?").
   3. **결과를 일괄 요약** — 건별 `added`(신규)/`noop`(이미 등록됨)/`not_found`(클래스 그래프에 없음 = 오타이거나 미등록)/`rejected_short`·`rejected_generic`(마스터 범용어 가드) 를 한 번에 보고한다.
      [중요] **거부는 오류가 아니라 사유 문장이다** — `rejected_short`(공백 제거 4자 미만) · `rejected_generic`(정확 구 DF 가 코퍼스의 2.5% 초과, 별칭이 되면 그 표현이 든 모든 질의가 한 클래스로 쏠린다). 사용자에게 사유를 그대로 보여 주고 더 판별력 있는 표현을 받는다. **문턱값을 여기서 흉내내지 말 것** — 판정은 마스터 한 곳이고, 두 벌이 되면 갈라진다.
      사용자가 "그건 클래스가 아니다" 라고 하면 `mark_not_a_class("<표현>")` — 기록하지 않으면 같은 말을 매번 다시 묻게 된다.

**invariants 와 invariants_candidates 는 강한 도메인 제약 *후보* (검증 대상)** 다 — 방향을 잡는 신호이되 최종 권위는 아니다. ontology 가 실제 코드와 어긋나면 **실제 `.h/.cpp` 가 우선** (ontology 는 eventually-consistent 라 stale 가능). confidence 가 높아도 구현을 단정하기 전엔 코드로 확정하라.

이유: ontology 는 LLM 추출 + class_graph.db lookup 기반 **정형 OAF 데이터** (Object/Action/Function + tier + parent + evidence + confidence). RAG 가 *유사 문서 발췌* 라면 ontology 는 *구조화된 도메인 사양* — 단 **최종 정합성은 코드로 확정** (ontology 는 코드에서 추출된 2차 자산이라 원천이 아니다). 호출 비용도 작음 (yaml 1 파일 read = 검색·랭킹·요약 단계 없음).

#### Ontology 호출 순서 (Phase η.6.2 path-first)

도메인 진입 시 다음 5단계로 단계적 탐색 — L3 까지 안 내려가는 경우 90%+ (토큰 절감):

```
1. list_domains()                → 도메인·tier·objects/actions 수 (정규 이름 확정)
2. get_domain_layer(d, 1)        → L1 트렁크 진입 (대부분 케이스 여기서 답변 가능)
                                   [주의] layer 는 정수다. 생략(0)하면 전체 층 + 책임/카운트/계층
3. (필요 시) get_domain_layer(d, 2)  → 부모/기반 진입
4. (드물게)  get_domain_layer(d, 3)  → 리프 진입
5. get_object_spec(d, class) / get_action_spec(d, action) → 상세 메타 (이름 확정 후)
```

[주의] **L2 는 도메인마다 있고 없다** (실측 2026-08-20): `ProjectAlpha_UiViewManagement` L2=5 · `UiManagement` L2=2 · **나머지 5개 도메인은 L2=0**. 빈 층을 물으면 조용한 빈 목록이 아니라 `_note` 로 *"L2 에 항목이 없다 — 이 도메인이 가진 층은 ['L1','L3'] 이다"* 라고 답한다.

L1 = 도메인 책임 흐름 (변하지 않는 원칙, 트렁크) / L2 = 기반 구현 (부모/공통 패턴) / L3 = 휘발성 구현체 (리프). L1 은 **네비게이션·도메인 의미의 SSOT** (어느 도메인·무슨 책임인지 — 트렁크라 잘 안 변함) 이되, **구현 정합성의 최종 권위는 실제 코드**다. L1 으로 방향을 잡고 구현 판단은 `.h/.cpp` 로 확정하라. L3 는 가변성 높아 코드 병행 필수 ("지도 vs 지형" 비유: ontology = 지도(어디로 갈지 빠르게), 코드 = 지형(지금 실제 상태) — 길찾기는 지도로, 발 디딜 땐 지형 확인).

#### 도메인 계층·연관 탐색 (깊이 ↔ 넓이)

layer 가 *깊이*(L1→L2→L3, 더 구체적 구현)라면, 도메인 계층·연관은 *넓이*다. **`get_domain_layer(d)` 응답**의 `parent_domain`·`sub_domains`·`collaborated_by` 로 이동한다 (2026-08-20 부터 층 조회가 이 필드들을 함께 준다 — 왕복이 늘지 않는다). [주의] `collaborates_with`(정방향)는 우리 응답에 없다 — **역참조 `collaborated_by` 로 본다.**

- **상위 (`parent_domain`)** — 지금 도메인이 좁아 더 넓은 맥락·공통 규칙이 필요하면 상위 도메인 manifest 로 올라간다 (예: 참조 시스템 하위 → 코어 프레임워크 상위).
- **하위 (`sub_domains`)** — 더 구체적인 하위 영역이 따로 있으면 내려간다.
- **연관 (`collaborates_with` / `collaborated_by`)** — 데이터·호출이 오가는 옆 도메인. 한쪽만 선언돼 있어도 `collaborated_by`(역참조)로 양방향 탐색.

코드 작업·로그 분석에서 **한 도메인 안에서 답이 안 나오면, layer 를 더 파기 전에/후에 상위·연관 도메인도 함께 본다** (이벤트가 상위/연관 도메인에서 발행되는 등 cross-domain 흐름이 흔함).

#### 2순위 — RAG (검색)

ontology 에 없거나 보강이 필요할 때:

1. **RAG 검색**: `mcp__ax-client__search_context(query, tags?, n?)` — 대괄호 개념은 시소러스로 자동 확장된다 (`ToolSearch` 선행 로드 불필요)
2. **검색 결과의 `file`·`tags` 로 실제 소스 파일 위치 파악**
3. 그 이후에 `Read`로 소스 코드 직접 확인 — **확정은 코드**

이 절차를 건너뛰고 Glob/Grep부터 시작하지 말 것 — ontology + RAG 에 이미 요약·관계·태그가 색인되어 있으므로 검색이 훨씬 빠르고 정확하다.

#### 답변 마커

답변 시작에 데이터 소스 명시:
- **온톨로지 기반** — ontology 도구로 정형 데이터 확인 후 답변
- **RAG 기반** — ax-client `search_context` 결과 활용
- **일반 지식 기반** — 위 둘 다 0건 폴백

사용자가 답변의 신뢰 수준을 즉시 판단 가능.

### 브레인스토밍에서 코드 심볼이 등장한 경우 — ontology 자동 선행

옛 규칙 ("초안 답변 + 1회 RAG 제안 + 세션 합의") 폐기 (2026-05-25). 이유:

- 옛 가설 ("발산 단계는 RAG 비용 아끼자") 은 ontology 미보유 시점 보수. **디지털 트윈 보유 영역에서는 RAG 호출 비용 (수십 ms) < 잘못된 초안으로 추가 왕복 비용**. 발산 단계야말로 가설 검증 정확도가 핵심.
- ontology 도구는 RAG 와 달리 **YAML 1 파일 read** = 검색·랭킹·요약 단계 없음. 발산 흐름 끊지 않음.

**새 규칙** — 코드 심볼 등장 시 (브레인스토밍 / 작업 명령 무관):

1. `list_domains()` → 후보 도메인 확인, `get_domain_layer(d)` 의 이름 목록에서 그 심볼이 있는 도메인을 확정한다 (심볼이 흔하면 `search_context(심볼)` 의 `tags` 로 후보를 먼저 좁힌다)
2. 확정되면 `get_object_spec(d, 심볼)` + 그 도메인 `get_domain_layer(d)` 의 책임·invariants 목록을 함께 본다 (한 클래스의 불변식만 훑을 땐 `find_invariants_by_class(심볼)`)
3. **invariants 의 evidence/confidence 를 답변에 인용** — "ontology 가 가리키는 도메인 제약 후보" 로 제시 (구현을 단정해야 하면 실제 코드로 확정 후)
4. 미등록 심볼 (온톨로지 매핑 0건) → `search_context` 폴백 (RAG)
5. 둘 다 0건 → 일반 지식 답변

사용자에게 묻지 않음. 답변 시작에 데이터 소스 마커 명시.

**트리거 신호 (예시)**

| 분류 | 예시 |
|------|------|
| 코드 심볼 | UE 접두 클래스 (`U*`, `A*`, `F*`, `E*`, `T*`), `Class::Method` 메서드 표기, `UCLASS`/`UFUNCTION`/`UPROPERTY`/`USTRUCT` 매크로, 명시적 함수 시그니처 |

**분기 표 (단순)**

| 발화 형태 | 처리 |
|----------|-----|
| 코드 심볼 등장 | ontology 자동 선행 → 매칭 시 정형 데이터 답변, 미매칭 시 RAG 폴백, 0건 시 일반 지식 |
| 코드 심볼 없음 ("이 구조 어떻게 생각해?") | 일반 지식 발산, ontology/RAG 미호출 |

**이유**: 디지털 트윈 자산 ([[project_ontology_direction]] 추진) 활용도 = 본 시스템 핵심 가치. 코드 심볼 발화에서 ontology 미활용 = 자산 사장. 호출 비용 작고 정확도 큰 자산을 발산 단계라고 회피할 이유 없음.

### 전문 에이전트 위임 규칙 (BLOCKING)

사용자 요청이 아래 패턴에 해당하면 **직접 처리하지 말고** `Agent` 툴로 해당 전문 에이전트를 호출할 것.
각 에이전트는 전용 시스템 프롬프트와 도구를 보유하고 있어 직접 처리보다 정확하고 일관된 결과를 낸다.

| 요청 패턴 | `subagent_type` | 에이전트 산출물 |
|-----------|-----------------|---------------|
| "X 리뷰해줘", "X 분석·리뷰", "이 모듈 점검", "수정했어 검토해줘", "이거 닫아줘" | `code-validator` | 리뷰 MD 저장 + Redmine 등록 / 수정 완료 검증 + Resolved 처리 |
| "새 파일 컨텍스트 만들어줘", "이 모듈 요약" | `source-analyzer` | `.claude/context/*.md` 생성 |
| "프로젝트 구조 설명", "아키텍처 맵" | `project-analyzer` | 구조·의존·영향 리포트 |
| "네이밍 체크", "컨벤션 위반 찾아줘" | `code-convention` | 위반 테이블 |
| "X 기능 구현해줘", "이 코드 리팩터링" (단일 클래스·기존 클래스 미세 수정) | `code-writer` | 코드 초안 + 설명 |
| "X 시스템 추가", "Y 기능 만들어줘" — **신규 파일 3개 이상 + 클래스 간 상속/포함/import 관계** 또는 **여러 클래스가 묶이는 신규 시스템** | **`ax-request` 로 마스터에 등재** | 마스터가 골조·분해·파견·게이트를 한다 |
| "빌드 실패 분석", "의존성 변경 영향" | `build-integration` | 빌드 위험 리포트 |
| "전체 리뷰", "통합 리포트" | `code-manager` | 최종 리뷰 리포트 |
| "UE 로그 분석", ".log 봐줘" | `log-reviewer` | 에러 요약 + 원인 추정 |
| "크래시 분석", ".dmp 읽어줘" | `crash-diagnoser` | 크래시 원인 리포트 |
| "에셋 검증", ".uasset/.umap 체크" | `asset-validator` | 에셋 검증 리포트 |
| "리뷰 지적 상담", "이 지적 어떻게 하지", "의도된 기능", "이건 의도적이야" | `review-consultant` | 대화형 응답 + 코멘트 기록 (+ "의도된 기능" 시 Redmine·plan 일괄 갱신) |

**절대 금지**: 위 패턴을 받고도 메인 세션이 직접 파일을 읽고 리포트를 쓰는 것. 전문 에이전트는 MD 저장·MCP 호출·Redmine 등록 같은 부수 동작을 일관되게 처리하는데, 메인 세션이 대신 처리하면 이 체계가 깨진다.

#### `code-writer` vs **분산 등재** 분기 (사용자 확인 필수)

> [중요] **`/distribute` 스킬은 이 기계에 없다** (`#232` 로 2026-08-20 제거 · `#297` 정정
> 2026-08-24). **사라진 것이 아니라 자리가 옮겨졌다** — 분해·파견·게이트는 **마스터**가 하고,
> 이 기계는 `ax-request` 로 **등재만** 한다(단일 writer 는 서버 · `docs/8` §8.4).
> 아래 절차의 「`/distribute` 로 분산」은 전부 **「`ax-request` 로 등재」**로 읽는다.
> [주의] 지우기만 하지 않고 이렇게 적어 두는 이유는, 지우면 다음 세션이 *"그런 절차는 원래
> 없었다"* 로 읽기 때문이다(리포트 27 의 그 교훈).

다음 중 하나라도 해당하는 Plan 이면 **`code-writer` 자동 호출 금지** — 사용자에게 분산 여부를 명시적으로 묻기:

- 새 클래스 3개 이상 생성
- 클래스 간 부모-자식 또는 manager-leaf 관계 존재
- "X 시스템 추가" 류 시스템 단위 변경

질문 형식 (Plan 표시 직후):
> "이 작업은 신규 파일 N개 + 클래스 간 의존 관계가 있어 분산 워커로 클러스터링 가능합니다.
> - a) **`ax-request` 로 마스터에 등재**해 분산 처리 (마스터가 골조 + 인터페이스 동결 + 분해 + 워커 파견 + 3층 게이트를 한다)
> - b) 메인 세션이 직접 작성 (브랜치 격리 없이 즉시 진행, main 또는 사용자 지정 브랜치)
> - c) 작은 단위로 쪼개서 `code-writer` 위임"

판단 기준 — 사용자가 결정. 시스템 규모는 자동 트리거 아님:
- 분산 가치 (워커 수, 야간 가용성, 컨벤션 표준화 효과) 가 클 때 → a
- 빠른 처리 또는 사용자 직접 검수가 필요한 실험적 변경 → b
- 일부만 자동화하고 나머지는 단계별 처리 → c

이유: `code-writer` 는 단일 클래스·기존 코드 수정용. 다중 클래스 생성을 시키면 의사코드 단계 없이 본문까지 한 번에 써버려 분산 시스템이 무의미해진다. 반대로 모든 다중 클래스 작업을 자동으로 등재하면 빠른 일회성 작업까지 큐에 박히는 오버헤드. **결정은 사용자**.

**등재 후 브랜치 격리 거부 시**: 마스터가 등재를 거부한다 (main 보호가 양보 불가 안전장치 —
워커는 `attempt/<task_id>/<workshop>/<ts>` 에서만 작업한다). 격리 없이 진행하려면 a 가 아니라
b 를 고른다.

#### 옵션 a/b/c 모두 항상 제시 (BLOCKING — 환경 상태로 자동 거름 금지)

분기 질문에서 옵션을 빼면 안 되는 케이스:

- `mcp__ax-client__*` 가 **disconnected** 표시 (또는 응답에 `_stale: true`)
- 마스터의 큐(`ax-task-queue`)·프로젝트 서비스(`ax-projects`) 미동작
- `master_orchestrator` MCP 미연결
- 직전에 `task_queue --reset` 을 한 직후

**이유**: MCP 연결 상태는 환경 마찰이지 영구 제약 아님. [중요] **복구는 마스터에서 한다** — `systemctl status ax-task-queue ax-projects` 확인 후 필요하면 `sudo -n /usr/bin/systemctl restart <유닛>` ([주의] 성공 판정은 종료코드가 아니라 `ExecMainStartTimestamp` 로). 읽기 조회는 마스터가 죽어도 `_stale` 표기로 답하니 화면이 멈추지는 않지만 **`_stale` 값으로 결정하지 않는다.** ~~watch.exe 재기동~~ 은 이제 없다 — 원전 폴링 데몬은 2026-08-20 에 제거됐다. 분산 적합성 판단은 **작업 성격** (워커 가용성·표준화 가치 등) 기준이지 시스템 상태 기준 아님 — 결정은 사용자.

**올바른 처리**:
- 옵션 a/b/c 모두 제시
- 사용자가 a 선택 시: 미연결 MCP 재연결 절차를 사전 작업으로 안내 (예: "watch.exe 재기동 후 task_queue daemon 재연결 필요")
- 옵션 자체를 제외하지 말 것

**금지된 처리** (메인 세션이 옵션 가로채는 케이스):
- ❌ "MCP 연결 안 됐으니 a 빼고 b/c 만 제시"
- ❌ "task_queue daemon 미동작이라 분산 불가"
- ❌ "지금 환경에선 b 만 가능"

#### 분산 등재 — 이 기계는 **요청자**다 (BLOCKING)

[중요] **분해·파견은 마스터가 한다** — 이 기계에는 그 스킬이 없다(`#297`). 등재는 `ax-request`
한 곳으로만 가고, 그 뒤 절차(골조·동결·분해·게이트)는 마스터의 일이다. 아래 표는 **옛
`/distribute` 발동 조건**의 기록이다 — 지금은 `.ax/config.json` 의 `role` 이 그 자리를 대신한다:

| 상태 | 분산 등재 |
|---|---|
| `server_mode: true` (서버 PC) | ✅ 사용 가능 |
| `context_server_url` 설정됨 + `server_mode: false` (클라이언트 PC, 팀원) | ❌ 발동 금지 |
| 둘 다 미설정 (단독 모드, 개인 개발용) | ✅ 사용 가능 |

클라이언트 PC 에서 위 큰 작업 트리거가 들어오면:
> "이 PC 는 클라이언트 모드입니다. 분산 작업 등재는 서버 PC 에서만 수행하세요.
>  큰 작업이 필요하면 리더에게 요청하시거나, 작은 단위 수정은 `code-writer` 로 직접 진행 가능합니다."

이유: 워커 PC 가 work 를 등재하면 동일 task_queue 가 여러 곳에 생겨 진실의 원천이 깨짐. 분산 워커 게이트는 리더 PC 가 일원화하여 관리해야 한다.

#### 의도 기반 위임 (메타 규칙 — 키워드보다 우선)

위 표는 매핑 참고용이지 트리거 조건이 아니다. **요청의 의도가 코드 변경(생성·수정·삭제·리팩토링)이면 표현이 어떻든 적절한 전문 에이전트로 위임할 것.** 다음 규칙을 적용한다:

- **누적 대화 맥락으로 판단할 것** — 최신 메시지만 보고 트리거를 결정하지 말 것. 직전 턴에서 코드 변경 작업이 제시되었고 현재 턴이 그 실행을 승인·요청하는 응답("응", "ㅇㅇ", "시작해줘", "그렇게 해", "진행해", "ㄱㄱ" 등)이면 **현재 턴을 코드 작성 트리거로 간주**한다.
- **표현 동의어 무관**: 추가/변경/개선/수정/고쳐/바꿔/구현/짜줘/만들어줘/리팩터/정리해 등은 모두 `code-writer` 트리거.
- **표에 없는 신규 패턴**도 의도가 명확하면 가장 가까운 에이전트로 위임 (애매하면 `code-writer`).

#### Plan-first 확인 (위임 전 게이트)

의도가 코드 변경으로 판단되더라도, **다음 중 하나라도 해당하면 즉시 `code-writer`를 호출하지 말고 짧은 plan을 먼저 제시한 뒤 사용자 확인을 받을 것**:

- 사용자 발화가 결정형이 아닌 **반추·제안형**: "~해야겠다", "~하면 좋겠다", "~인 것 같다", "~하는 게 어때", "~필요할 듯"
- 변경 범위가 **2개 이상 파일** 또는 **다중 클래스**에 걸침
- **네트워크·동시성·라이프사이클·리플리케이션·스레딩·세션 관리** 등 구조적 결정 포함
- **공개 API 시그니처·데이터 스키마·UPROPERTY 멤버** 변경 (Blueprint/에셋 영향 가능)

Plan 형식: 영향 파일 목록, 핵심 변경 요약(3~5줄), 위험 요소(있으면) → 마지막에 "이 방향으로 진행할까요?"로 사용자 컨펌. 컨펌 받은 뒤에 `code-writer` 호출.

**즉시 실행 허용 (plan 생략)**: 단일 파일·소규모·명시 의도가 분명한 수정에 한함 — "이 한 줄 고쳐줘", "이 변수명 X로 바꿔줘", "오타 수정해줘", "이 import 추가해줘" 등.

#### 위임하지 말아야 하는 케이스 (negative triggers)

다음 카테고리는 **누적 맥락에 코드 키워드가 있어도** 메인 세션이 직접 처리한다 — 잘못된 위임은 의도치 않은 파일 수정과 토큰 낭비를 유발한다:

- **설명·요약·분석 결과 해설** — "이 함수 어떻게 동작해?", "이 리뷰 의미가 뭐야?", "이 패턴 설명해줘"
- **문서·리포트·계획서 작성** — `.md`/`.txt` 등 비소스 파일 작성, 회의록·주간 보고 등
- **의견·비교·아이디어 brainstorming** — "이거 어떻게 생각해?", "A랑 B 중에 뭐가 나아?" (단, **코드 심볼 동시 등장 시** 상단 "브레인스토밍에서 코드 심볼이 등장한 경우" 적용 — RAG 1회 제안)
- **계획만 수립하고 실행 보류** — "계획만 먼저", "검토만 해줘", "방향만 잡아보자"
- **단순 정보 조회** — 파일 경로, 함수 위치, 검색 결과, RAG 결과 설명, 이미 열려있는 에이전트 내부 작업

판단이 애매하면 사용자에게 "코드를 직접 수정할까요, 아니면 설명만 드릴까요?" 한 번 확인할 것.

### 컨텍스트 파일 위치 및 형식
- `.claude/context/<도메인>/` — 변경 소스 파일을 Claude가 요약한 MD 파일
- 프론트매터 스키마:
  ```yaml
  ---
  tags: [태그1, 태그2]
  category: 대분류/중분류
  related_classes:
    - ClassName: path/to/file.ext
  ---
  ```

### 리뷰 리포트 위치
- `.claude/reviews/<작성자>/YYYY-MM-DD_HHMM_<커밋해시>.md` — 커밋별 코드 리뷰 (자동)
- `.claude/reviews/<작성자>/ad_hoc_YYYY-MM-DD_HHMM_<토픽>.md` — 수동 리뷰 (code-validator)
- `.claude/reviews/<작성자>/YYYY-MM-DD_HHMM_<커밋해시>_assets.md` — 에셋 검증 결과
- `.claude/reviews/<작성자>/_health_report.md` — 작성자별 건강도 리포트
- `.claude/reviews/<작성자>/_weekly/` — 작성자별 주간 리포트

### 컨텍스트 코멘트
- 컨텍스트 MD 파일 끝에 `## 코멘트` 섹션으로 개발자 노트를 기록
- 코멘트 유형: `[리뷰]` / `[방향]` / `[고민]` / `[진행]` / `[메모]`
- 벡터 임베딩에서 제외 → 검색 품질 영향 없음
- 리뷰 시 에이전트가 참조 → 설계 맥락 이해 및 반복 지적 방지
- `review-consultant` 에이전트로 기록·상담

### 작업 히스토리 작성 규약 (Phase α′ — ontology 시드 원천)

비자명한 의사결정·아키텍처 변경·정책 변경을 처리한 직후 기록을 남긴다. 단순 버그 수정·리네이밍·문서 오탈자 같은 trivial 작업은 불필요. **history 는 ontology 시드의 1순위 원천** (plan v4.3 Phase α′) 이라, 안 남기면 다음 세션이 같은 결정을 처음부터 다시 한다.

🔴 [중요] **자리가 옮겨졌다 — 이 기계에 파일로 쓰지 않는다.** 종전 이 절은 `.claude/history/YYYY-MM-DD_HHMM_<작업요약>.md` 를 **로컬 파일로** 만들라고 적어 뒀다(원전 레이아웃: 원전은 데이터가 UE5 프로젝트의 `.claude/` 안에 있었다). 우리는 그 데이터를 **마스터의 디지털 트윈**으로 옮겼고, 이 줄이 따라오지 않아 실제로 한 세션이 *"작업했는데 히스토리가 없다"* 고 판단했다(2026-08-24, `#304`). 기록은 있었다 — 마스터에 있었다.

**적재 지점은 둘이고, 이 기계는 둘 다 탄다.** 어느 쪽인지에 따라 할 일이 정반대다:

| 경로 | 언제 | 누가 쓰나 | 세션이 할 일 |
|---|---|---|---|
| **직접 처리** | 이 세션이 스스로 코드를 고쳤다 | **너** — `log_history` MCP (마스터 대행) | 🔴 **부른다.** 안 부르면 기록이 없다 |
| **분산 작업** | 마스터에 등재해 워커가 처리했다 | **큐가 자동** — work 이 `merged`/`rejected` 로 종결될 때 | ❌ 아무것도 안 한다 (두 번 쓰면 중복이다) |

[중요] **쓰는 것은 서버 하나다** (「단일 writer」). `log_history` 는 이 기계가 파일을 만드는 것이 아니라 **마스터에게 쓰라고 시키는 것**이고, 그래서 이 기계에는 결과 파일이 안 생긴다. 확인하고 싶으면 마스터 트윈의 `history/` 를 본다 — 파일명은 마스터가 `YYYY-MM-DD_HHMM_<작업요약>.md` 로 짓는다.

[주의] **`work_id` 를 아는 경우엔 반드시 실어라.** 그 값이 어느 프로젝트의 트윈에 쓸지를 푸는 스탬프다. 없으면 마운트된 프로젝트로 간다 — 마운트가 내가 작업한 프로젝트와 다르면 **남의 트윈에 쌓인다.**

frontmatter 의무 필드 (`log_history` 인자와 1:1):

```yaml
---
date: YYYY-MM-DD HH:MM                            # 마스터가 찍는다
work_id: null or "<분산 작업 work_id>"            # 마스터에 등재된 작업이면 채움
session_id: null or "<UUID>"                      # 같은 작업 단위 그룹핑
decision_type: architecture | policy | experiment | revert | bugfix | refactor | infra | feature
affected_classes:                                 # CamelCase 식별자만 (BM25 related_classes 와 같은 토큰)
  - UMyClass
affected_domains:                                 # 승급된 도메인명
supersedes: null or "<이전 history 파일명>"        # 이전 결정을 뒤집을 때만 (drift 추적)
alternatives_considered:                          # 검토했으나 안 쓴 것 (negative knowledge — 이게 제일 귀하다)
  - "UMG 단독 (포커스를 직접 짜야 해서 제외)"
tags:                                             # 자유 태그 (BM25 매칭)
  - gamepad
user_quote: |
  사용자 직접 발화 인용 1~3줄 (WHY 신호 — 본문보다 강하다)
---

# <제목>

## 작업 개요
## 수정된 파일 목록
## 주요 설계 결정
## 후속 작업 / 미해결 검토
```

🔴 [중요] **리스트는 대시(`- item`)로만 쓴다.** 종전 예시의 `affected_classes: []` 같은 **인라인 형태를 소비자가 못 읽는다** — 원전 미니 파서가 스칼라 문자열로 읽어 `isinstance(list)` 검사에서 **통째로 버린다**(실측). 비어 있으면 키 뒤를 그냥 비워 둔다. 이 규약은 그 파서를 고칠 수 없어서 있는 것이 아니라, **소비자가 원전 것이라 형식이 계약이기 때문**이다.

[주의] `decision_type` 은 위 **8개 중 하나**여야 한다 — 그 밖의 값은 마스터가 422 로 거절한다(조용히 `feature` 로 바꾸지 않는다). 본문 구조는 자유이고 frontmatter 만 의무다. 후속 ontology 분류기·drift 추적기가 이것을 직접 소비한다.

### 에이전트 목록
`.claude/agents/SKILL_INDEX.md` 참고

### 등록된 MCP 서버
| 서버 | 실행 파일 | 주요 툴 |
|------|-----------|---------|
| `ax-client` | `py .ax/lib/axmaster/clientside/client_mcp.py` (마스터가 배달·손대지 말 것) | 조회 12: `search_context`, `list_domains`, `get_domain`, `get_domain_layer`, `get_object_spec`, `get_action_spec`, `find_invariants_by_class`, `list_works`, `get_work`, **`find_recipes`**, **`get_anti_patterns`**, **`find_history`** · 쓰기 대행 5: `add_object_alias`, `mark_not_a_class`, `redmine_note`, `log_writer_signal`, `log_history` · 조회 6(레드마인·템플릿): `redmine_list_issues`, `redmine_get_issue`, `redmine_meta`, `redmine_create_issue`, `redmine_link_commit`, `list_task_templates`/`get_task_template` |
| ~~`context-search`~~ | ~~`.claude/mcp/context_search.exe`~~ | **은퇴 (2026-08-20)** — 온톨로지가 마스터로 옮겨져 이 인덱스는 낡았고 0/0 으로 답한다. 색인 갱신(`rebuild_index`·`index_status`)은 마스터가 push 훅으로 자동 처리한다(`ax-indexer`) |
| `log-analyzer` | `.claude/mcp/log_analyzer.exe` | `analyze_log`, `search_log` |
| `crash-analyzer` | `.claude/mcp/crash_analyzer.exe` | `analyze_crash`, `analyze_crash_log` |
| `commandlet-runner` | `.claude/mcp/commandlet_runner.exe` | `find_unreal_editor`, `run_data_validation`, `run_commandlet` |
| `agy-query` | `.claude/mcp/agy_query.exe` | `agy_analyze`, `agy_status` (Antigravity CLI 미설치 시 안내 반환) |
| `redmine-tracker` | `.claude/mcp/redmine_tracker.exe` | `list_projects`, `list_issues`, `get_issue`, `create_issue`, `update_issue`, `list_trackers`, `list_statuses`, `create_review_issue`, `link_commit` (+ CLI: `--register-plan`) |
| `code-recipes` | — | [완료] **`ax-client` 가 흡수했다** (`#267`, 2026-08-23). 별 서버를 만들지 않았다: 레시피는 **마스터 트윈**에 있고 이 기계엔 그 디렉토리가 없어 큐가 대행한다. [주의] 그 전까지 이 표와 `code-writer` 에이전트가 **없는 서버**를 부르라고 적어 뒀다 |

[중요] **작업을 시작하기 직전에 `find_recipes` · `get_anti_patterns` · `find_history` 를 부른다** (`#267`, 원전 규약: *"code-writer 는 작업 시작 직후에 호출해 step-by-step 가이드를 컨텍스트로 받는다"*). **도구가 있어도 안 부르면 컨벤션 루프는 한 방향이다** — 합성은 돌지만 아무도 읽지 않는다. 같은 일을 앞서 한 기록이 있으면 **그 관습이 이 프로젝트의 컨벤션**이고, 거절된 접근 카탈로그는 이번 작업과 무관해 보여도 끝까지 훑는다.
[주의] **한글로 물어도 된다** — 태그에 한글이 함께 들어간다. 안 걸리면 레시피 목록이 사유와 함께 오고, *"아직 없습니다"* 는 고장이 아니라 신호가 덜 쌓인 것이다.

### 인프라 컴퓨터 이전 — 발화 규약 (BLOCKING, 2026-07-18)

"익스포트"/"백업"/"이전" 같은 단어만 보고 **절대 UE5 프로젝트 폴더(`Source/`, `Content/`,
`Binaries/`, `Intermediate/`, `Saved/`, `.git/` 등)를 zip으로 압축하지 말 것** — 실제로 이
오해석 때문에 GB 단위 백업을 셸에서 직접 시도한 사고가 있었다. 서버/클라이언트 모드의
인프라 컴퓨터(RAG 중앙 관리 PC)를 다른 하드웨어로 옮기는 요청은 아래 두 MCP 도구
(`export_infra_state`/`import_infra_state`)로만 처리한다 — Bash 로 `zip`/`Compress-Archive`
등을 직접 짜지 않는다.

| 발화 패턴 | 의미 | 호출할 도구 |
|----------|-----|------------|
| "익스포트해줘", "이 컴퓨터 상태 내보내줘", "인프라 컴퓨터 이전 준비" | `.claude/context/`+`.claude/ontology/domains/` 만 zip으로 압축 | `export_infra_state(output_zip, project_root=".")` |
| "이 zip 임포트해줘", "상태 복원해줘", "익스포트한 거 여기로 가져와줘" | 위 zip 복원 + 도메인 검색 인덱스 자동 동기화 | `import_infra_state(input_zip, project_root=".", force=False)` |

두 도구 모두 `.claude/vector_db/`(임베딩·BM25·class_graph.db·dependency_graph.db)는 건드리지
않는다 — 로컬 재계산 가능한 파생 자산이라 옮길 필요가 없기 때문(대상은 오직 LLM 합성
산출물인 컨텍스트 MD·온톨로지 YAML 두 가지). 임포트 후에는 `watch.exe` 재기동이 필요하다
(응답의 `next_step` 필드 참조).

### 운영 데이터 조회 도구 (σ.11)

`.claude/tools/sqlite3.exe` 와 `.claude/tools/jq.exe` 가 함께 배포된다. **운영 데이터를 자연어 분석할 때 즉석 PowerShell 스크립트를 짜는 대신 이 도구를 우선 사용**한다 — 2026-05-22 도메인 자동 승급 침묵 발견 경위에서 도구 부재가 silent failure 일제 감사의 1차 장벽으로 드러났던 사건의 대응.

| 데이터 | 위치 | 도구 | 예시 |
|---|---|---|---|
| BM25 인덱스 | `.claude/vector_db/bm25.db` | `sqlite3.exe` | `.claude/tools/sqlite3.exe .claude/vector_db/bm25.db ".schema"` |
| 클래스 상속 그래프 | `.claude/vector_db/class_graph.db` | `sqlite3.exe` | `.claude/tools/sqlite3.exe .claude/vector_db/class_graph.db "SELECT * FROM classes LIMIT 5"` |
| `#include` 의존 그래프 | `.claude/vector_db/dependency_graph.db` | `sqlite3.exe` | `.claude/tools/sqlite3.exe .claude/vector_db/dependency_graph.db ".tables"` |
| ChromaDB 메타 | `.claude/vector_db/chroma.sqlite3` | `sqlite3.exe` | 위와 동상 (raw 임베딩은 별도 컬렉션 디렉토리) |
| 검색 로그 | `.claude/search_log.jsonl` | `jq.exe` | `Get-Content search_log.jsonl \| .claude/tools/jq.exe -s 'group_by(.lang) \| map({lang: .[0].lang, count: length})'` |
| code-writer 신호 | `.claude/recipes/_signals.jsonl` | `jq.exe` | 위와 동상 |
| 토큰 사용량 | `.claude/logs/token_usage.jsonl` | `jq.exe` | 위와 동상 |

**호출 정신**: Glob/Grep 으로 SQLite 파일을 raw 로 읽지 말 것 — frontmatter·인덱스·외래키 정보가 가려져 분석 정확도 떨어진다. 항상 `sqlite3.exe` / `jq.exe` 로 구조화 쿼리.

**라이선스**: SQLite Public Domain, jq MIT (`.claude/tools/LICENSES/` 에 사본). 외부 네트워크 호출 없음, 운영 데이터는 PC 내부에서만 분석.


### 도메인 맵 (자동 생성)

| 도메인 | 개요 | 태그 | 소스 |
|--------|------|------|------|
| AlphaCoreGameFramework | 프로젝트 알파의 핵심 게임 프레임워크는 단일 메인 모듈(`Project_Alpha`) 내에서 언리얼 엔진의 다양한 시스템(네트워크, UI, AI | Build, ModuleRules, UBT, IncludePath, Dependencies, asset-loading, character, dialog, event, skeletal-mesh, async, animation | 2개 |
| GlobalEventSystem | 전역 이벤트 시스템은 언리얼 엔진 환경에서 모듈 간의 결합도를 최소화하기 위해 설계된 인터페이스 기반의 메시지 디스패처입니다. `UGlobalE | GlobalEventSystem, Interface, Mission, EventListener, UE5, global-event, event-dispatcher, interface, decoupling, listener-map | 2개 |
| MissionEditor | `AMissionPrefab` CDO 의 `TaskList`(`FMissionTaskInfo[]`)를 에디터 위젯으로 시각·편집·직렬화하는 시스 | mission-editor, editor-utility-widget, task-list, instanced-struct, prefab-cdo, blutility, mission-task-data, list-view | 8개 |
| MissionRuntime | 본 시스템은 언리얼 엔진 환경에서 미션의 생명주기와 실행 로직을 관리하는 계층형 프레임워크입니다. `UMissionTaskExecutor`를 중 | MissionSystem, PhaseB, TaskSystem, mission-task, multi-task, composite, executor, state-machine, TaskExecutor, Client-Side, Component, Mission, Sync, state-synchronization, mission | 5개 |
| MissionSystemTools | 미션 및 시스템 관리 도구는 언리얼 엔진의 에디터 유틸리티 위젯(EUW)을 활용하여 인게임 태스크와 미션 데이터를 시각적으로 편집할 수 있는 환 | UI, dialog, manager, singleton, table-driven, speech-bubble, sequential-playback, 에디터, 미션, 태스크, 위젯, SpawnObject, logging, json, debug | 4개 |
| ProjectAlpha_UiViewManagement | Project_Alpha의 UI 시스템은 `WNDUIViewManager`와 `WNDUIViewLayer`를 중심으로 뷰의 생명주기와 계층(La | UI, Project_Alpha, Dialog, Page, Popup, Widget, ProjectAlpha, Manager, ViewManagement, UMG, Lobby, BaseClass, UE5, Quest, SubQuest | 20개 |
| UiManagement | UI 관리 시스템은 CommonUI 프레임워크를 기반으로 게임 인스턴스 단위의 로컬 화면 레이아웃과 위젯의 동적 활성화를 제어하는 중앙 집중형  | UI, Subsystem, GameInstance, Manager, ModularStage, CommonUI, gameplay-tags, ui-layer, native-tags, commonui, layer-key | 2개 |

**기능 추가/변경 요청 시 워크플로우:**
1. `mcp__code-recipes__find_recipes` + `mcp__code-recipes__get_anti_patterns` 로 작업 단위 가이드·회피 카탈로그 먼저 조회
2. `combined_search`로 관련 도메인 문서 검색 — 도메인은 **시스템 수준 큰 그림** 만 담당 (시스템 개요·핵심 구현 패턴·확장 포인트)
3. `source_documents` 목록의 실제 코드를 읽고 작업 시작
<!-- AgentWatch:End -->
