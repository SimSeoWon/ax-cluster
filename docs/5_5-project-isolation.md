> AX Cluster 계획 문서의 일부다. 색인은 [`../PLAN.md`](../PLAN.md).
> § 번호는 분리 전과 같다 — 다른 문서의 상호참조가 그대로 유효하다.

### 5.5 프로젝트 격리 — **다중 디렉토리 · 단일 마운트** (2026-08-08 확정)

#### 5.5.1 문제 — 격리는 설계된 적이 없다, 공짜로 따라왔을 뿐이다

AgentTest 에서 프로젝트별 분리는 설계의 산물이 아니라 **DB 가 UE5 프로젝트 디렉토리 안에
있었기 때문에 위치가 곧 격리**였던 것이다. 데이터를 프로젝트 밖(마스터)으로 빼는 순간
그 성질이 사라진다. §5.4.7 이 "거의 그대로 이식 가능"이라고 판정한 `context_search --serve`
에도 **프로젝트 1개 전제가 코드에 박혀 있다** — 실측:

| 위치 | 전제 |
|---|---|
| `mcp/context_search/http_server.py:29` | `run_http_server(project_root, port=8100)` — 루트가 **기동 시 인자로 고정**되고 `register_*_routes(app, project_root, ...)` 로 전 라우트가 클로저에 캡처. **요청 단위로 프로젝트를 고를 방법이 없다** |
| `mcp/context_search/double_buffered_index.py:24` | `DoubleBufferedIndex(claude_dir)` → `claude_dir/vector_db`, 컬렉션명 `context_a`/`context_b` **고정**. 컬렉션명에도 메타데이터에도 프로젝트 식별자가 없다 |
| `mcp/context_search/ontology_route_loaders.py:17,64` | `base_dir/.claude/ontology/domains`, `base_dir/.claude/vector_db/class_graph.db` |

`task_queue` 가 이미 겪은 함정(§9.5.1 / `_project_root()` 가 "exe 가 프로젝트 루트 안에
있다"를 전제)과 **같은 종류가 프로젝트 축으로 한 번 더 나온 것**이다.

#### 5.5.2 결정 — 런타임은 1개, 레이아웃은 N개

> **디렉토리는 프로젝트마다 늘어나고, 서버는 그중 정확히 하나만 마운트한다.
> 마운트되지 않은 프로젝트 요청은 답하지 않고 거부한다.**

지금 UE5 프로젝트는 1개이고 **동시에 1개만 운영한다**(사용자 지시 2026-08-08).
그럼에도 지금 못박는 이유는 비대칭 때문이다:

| | 지금 하면 | 나중에 하면 |
|---|---|---|
| **경로 규약 · 이벤트 스키마** | 디렉토리가 비어 있어 **공짜** | 데이터 이사 + 감사 히스토리 소급 불가 |
| **요청 단위 라우팅 · 컬렉션 분리** | 안 씀 | **비용 동일** (순수 코드, 마이그레이션 0) |

→ **디스크에 쌓이는 것만 지금 정하고, 순수 코드는 두 번째 프로젝트가 생길 때 쓴다.**

#### 5.5.3 규약 (5개)

**① 경로 — `ax-cluster` 하위에 프로젝트명 디렉토리, 커밋하지 않는다** (사용자 지시 2026-08-08).
프로젝트마다 디렉토리가 나란히 추가되고, 그중 **하나만 마운트**된다.

```
~/ax-cluster/                          ← 인프라 코드 저장소 (GitHub·BC-250 동기화)
    projects.yaml                      ← 루트 config: 추적 목록 + active. 커밋한다
    .gitignore                         ← /ModularStage/ … 프로젝트 디렉토리를 제외
    ModularStage/                      ← 🔴 gitignore. 마스터 로컬 전용 데이터
        .git/                            자체 저장소(원격 없음·훅 없음) — 원본을 잠근다
        context/                         원본 · 텍스트 · 추적
        ontology/domains/                원본 · 텍스트 · 추적
        repo/                            소스 클론 · 파생 · 자체 .gitignore 로 제외
        vector_db/                       파생 · 바이너리 · 제외
    <다음프로젝트>/                     ← 같은 모양으로 나란히 추가
```

🔴 **프로젝트 추가와 마운트 전환은 대화형으로 처리한다 — 스킬 또는 MCP 도구를 만든다**
(사용자 지시 2026-08-08). 사람이 YAML 을 손으로 고치고 서비스를 재기동하는 절차가 아니다.

```
"ModularStage 로 바꿔줘"        → 도구가 active 수정 + 서비스 재기동 + 결과 보고
"NextProject 를 추가해줘"       → 디렉토리 생성 + projects.yaml 등록 + .gitignore 한 줄
                                  + 초기 클론 + 3자 일치 검사까지
```

`projects.yaml` 은 **SSOT 로 남는다** — 도구가 그 파일을 고치는 것이고, 파일을 우회해
메모리에서만 바꾸지 않는다. 그래야 "지금 뭐가 켜져 있나"가 파일 하나로 확정되고
diff·이력도 남는다. 대화형 인터페이스와 파일 SSOT 는 충돌하지 않는다.

**이미 배선이 있다** — `master/task_queue/mcp_server.py` 가 MCP 서버 패턴을 쓰고 있고,
AgentTest 의 `mcp/context_search/` 도 같은 형태다. 새 계층이 아니라 기존 패턴의 확장이다.

디렉토리는 전부 그대로 남아 있고 마운트 대상만 바뀐다. 마운트되지 않은 프로젝트 요청은
③ 에 따라 409 로 거부된다.

```yaml
# ~/ax-cluster/projects.yaml  (실제 파일, 2026-08-08 작성)
version: 1
active: ModularStage                   # 🔴 없거나 목록에 없으면 기동 실패
projects:
  ModularStage:
    dir: ModularStage                  # ax-cluster 하위 디렉토리명
    project_id: sim/modularstage       # Gitea 저장소 식별자 (훅 이벤트가 이걸로 온다)
    bare_path: /var/lib/gitea/gitea-repositories/sim/modularstage.git
    clone_url: http://192.168.0.57:3000/sim/modularstage.git
    branch: main
    engine: "5.8.1"                    # .uproject 에서 못 읽는다(EngineAssociation 이 GUID)
    index:
      include: ["Source/**/*.cpp", "Source/**/*.h", "Source/**/*.cs", "Config/**"]
      exclude: ["Content/**"]          # 1,021MB / 전체의 93%
```

**디렉토리명(`ModularStage`)과 `project_id`(`sim/modularstage`)를 분리했다.** 전자는 사람이
보는 이름, 후자는 훅 이벤트가 실어 오는 Gitea 식별자다. 규약 ② 의 "별칭 금지"는 여전히
유효하다 — `project_id` 는 **여기서 지어내지 않고 Gitea 값을 그대로 적는다.**

🔴 **유지보수 함정**: 프로젝트를 추가할 때마다 `.gitignore` 에 한 줄을 넣어야 한다.
빠뜨리면 그 디렉토리가 자체 `.git` 을 갖고 있어 **gitlink(서브모듈)로 `git status` 에
나타난다** — 조용히 커밋되지는 않으니 치명적이진 않지만, 반드시 눈으로 확인할 것.
(공통 상위 디렉토리 하나로 묶으면 `.gitignore` 한 줄로 끝나지만, 배치는 위 지시를 따른다.)

🔴 **Gitea 저장소 ROOT 는 `/var/lib/gitea/gitea-repositories` 다 (실측 2026-08-08).**
표준 배치의 `data/` 세그먼트가 **없다** — `app.ini` `[repository] ROOT` 실측값이고,
표준 경로를 가정하면 `post-receive` 훅이 조용히 엉뚱한 곳에 설치된다.
`ROOT_URL = http://192.168.0.57:3000/`, `RUN_USER = gitea`.
소유자 `sim` 아래 저장소 5개(`geminiscripter`·`project_alpha`·`modularstage`·
`scenariowriter`·`servertest`) 중 **`modularstage` 가 UE5 프로젝트다** (확인 2026-08-08).

**`sim/modularstage` 실측 (2026-08-08):** bare 저장소 **1,006MB**, 브랜치 `main` ·
`upgrade/ue5.8`. 최근 커밋이 `MCP 추가`, 그 앞이 *"모듈 구조 정리 — 순환 의존 해소 +
StructUtils 제거 / 5.8 API 대응 — Target.cs 버전업, include 경로, SavePackage,
StaticEnum, TObjectPtr Sort, UButton getter"*. **엔진은 UE 5.8.1 로 올라갔다**
→ §3 의 Unreal MCP 전제조건(5.8+)이 **충족됐다.**

🔴 **색인 대상은 소스뿐이다 — 실측 비율이 93:7 이다** (워킹트리 실측 2026-08-08):

| | 크기/개수 |
|---|---|
| 워킹트리 전체 | 1.1 GB |
| `Content/` (uasset 바이너리) | **1,021 MB — 93%** |
| `Source/**/*.{cpp,h,cs}` | **1,662 개 파일** ← 색인 대상은 사실상 이것뿐 |

제외 패턴은 `project.yaml` 에 둔다. 바이너리를 걸러내지 않으면 색인 비용의 대부분이
버려지는 데이터에 쓰인다.

⚠️ **엔진 버전은 `.uproject` 에서 읽을 수 없다.** `EngineAssociation` 이
`{9A68EB04-4D04-82B4-E2C3-6BB594AC0D6E}` — 로컬 엔진 빌드 등록 GUID 다.
온톨로지에 엔진 버전을 1급 속성으로 넣으려면 `Target.cs`/빌드 설정에서 뽑거나
`project.yaml` 에 명시해야 한다.

#### 5.5.3-a ✅ 마스터의 읽기 경로 — 초기 사본 확보 완료, 갱신 경로는 미결

**문제**: bare 저장소는 `gitea:gitea` 소유이고 `/var/lib/gitea` 가 `drwxr-x---` 라
`sim` 이 traverse 하지 못한다. HTTP 는 하드닝 때문에 익명 접근이 **401** 이다.
**마스터 서비스는 `sim` 으로 돌기 때문에 두 문 모두 닫혀 있다.**

✅ **초기 사본은 확보했다 (2026-08-08)** — `~/ax-cluster/ModularStage/`
아래 `repo.git`(bare 사본 1,006MB) + `repo`(워킹트리 1.1GB, `main`). 이제 root 없이 읽힌다.
이것은 §5.5 규약 ⓑ 의 첫 실물이고, §2.1 "마스터는 파일을 소유하지 않는다"와 충돌하지 않는다 —
그 원칙이 금지하는 것은 편집·빌드이고, 읽기 전용 색인 사본은 §2.1 이 마스터 몫으로 지정한
RAG/온톨로지 그 자체다.

⚠️ **git 2.34.1 함정 (2026-08-08 실측)**: `safe.directory` 는 **system/global config 에서만**
읽힌다. `-c safe.directory=...` 도 `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0` 환경변수도 **무시된다**
(둘 다 `fatal: detected dubious ownership` 로 실패). root 로 남의 저장소를 다루는 스크립트는
`git clone` 대신 `cp -a` 를 쓰거나 global config 를 건드려야 한다.

#### 5.5.3-b ✅ 온톨로지 자산 이관 완료 (2026-08-08)

윈도우 메인 작업용 PC(**192.168.0.33**)에서 `--export-state` 산출물
(`infra_state_20260808.zip`, 1.5MB)을 받아 규약 경로에 배치했다.
(다른 윈도우 PC는 **192.168.0.2** — UE5 설치됨, SSH 22 열림, 무인증 키는 미교환.)

```
~/ax-cluster/ModularStage/
    context/           1,056개 · 5.0MB   원본  (Source 927 · _domains 19 · _archive 101)
    ontology/domains/    254개 · 1.3MB   원본  (도메인 7개)
    ontology/_export_manifest.json       source_version 1.1.355
    repo/ · repo.git/                    사본/파생
```

**도메인 7개**: `AlphaCoreGameFramework` · `GlobalEventSystem` · `MissionEditor` ·
`MissionRuntime` · `MissionSystemTools` · `ProjectAlpha_UiViewManagement` · `UiManagement`.
구조는 `<도메인>/L1|L3/{objects,actions}/<이름>.yaml` — **계층(L1/L3)이 이미 들어가 있다.**

✅ **신선도 검증 통과 — 재추출 불필요** (실측):

| | 시각 |
|---|---|
| 5.8 API 대응 커밋 `9efbfc1` | 2026-08-02 16:29:43 |
| `MCP 추가` `bc4b38f` | 2026-08-02 16:45:39 |
| **컨텍스트 MD 최종 갱신** | **2026-08-02 17:35:40** ← 두 커밋보다 나중 |

즉 모듈 구조 정리·5.8 API 대응이 **반영된 뒤** 추출된 자산이다.
컨텍스트 MD 927개 : 소스 1,662개는 커버리지 부족이 아니라 `.h`/`.cpp` 쌍이 MD 하나를
공유하기 때문이다(표본 확인: `FHexGridSceneProxy.{h,cpp}` → MD 1개).

⚠️ **`StructUtils` 는 잔재가 아니다.** 현재 소스에 10건 남아 있으나 전부
`#include "StructUtils/InstancedStruct.h"` — 커밋 메시지의 "include 경로" 항목에 해당하는
5.8 경로 변경이다. 커밋 요약만 보고 "제거하다 만 흔적"으로 판단하면 틀린다.

✅ **원본 버전 관리 완료 (2026-08-08).** 이 자산은 이관 전까지 **윈도우 1대에만 있었고
git 에도 없었다**(§5.4.7 기준 원본이라 재색인으로 복구되지 않는다). 프로젝트 디렉토리를
**로컬 git 저장소로 만들어 잠갔다** — `~/ax-cluster/ModularStage/`, 최초 커밋
`0cd8140`, 추적 1,312개. `.gitignore` 로 `vector_db/`·`bm25.db`·`class_graph.db`·
`dependency_graph.db`(파생)와 `repo/`·`repo.git/`(원본이 Gitea 에 있음)을 제외한다.
저장소를 **프로젝트당 하나**로 둔 것은 §5.5 의 프로젝트 격리와 경계를 일치시키기 위해서다.

#### 5.5.3-c 🔴 색인 워터마크 — 커밋 해시를 기록한다 (2026-08-08 확정)

**문제**: 지금은 "어디까지 색인했나"를 알 방법이 없다. 실제로 2026-08-08 신선도 판정을
**MD 수정시각과 커밋 시각을 비교해 추정**하는 방식으로 했다(§5.5.3-b). 우연히 답이 나왔을
뿐이고, 재색인 대상을 고르는 데는 쓸 수 없다.

**결정: 갱신할 때마다 대응 소스 커밋 해시를 남긴다.** 세 층위에 둔다.

| 층위 | 위치 | 성격 |
|---|---|---|
| **파일 단위** | 컨텍스트 MD frontmatter 의 `source_commit` | **진실.** 부분 실패해도 파일별로 정확 |
| **프로젝트 워터마크** | `~/ax-cluster/<프로젝트>/index_state.json` | 파생. 빠른 판단용 캐시 |
| **이벤트** | 스풀 줄의 `oldrev`/`newrev` | 훅이 **이미 받는다** |

세 번째가 공짜다 — `post-receive` 의 stdin 형식이 `<oldrev> <newrev> <refname>` 이라
(§5.4.2-a 의 디스패처가 `data=$(cat)` 로 읽어 그대로 넘긴다) 훅은 **정확히 필요한 해시를
이미 손에 쥐고 있다.** 스풀 줄에 그대로 실으면 된다.

**이것이 증분 갱신을 가능하게 한다:**

```
git diff <last_indexed_commit>..<newrev> --name-only -- Source/
        → 재생성이 필요한 MD 만 정확히 나온다
```

컨텍스트 MD 927개를 매번 다시 만드는 대신 바뀐 것만 건드린다. §5.4.5 가 요구한 중복 합치기도
이 위에서 자연스럽다 — 연속 push 를 합칠 때 **가장 오래된 `oldrev` 와 가장 최신 `newrev`**
만 남기면 된다.

🔴 **폴백이 반드시 필요하다.** 히스토리가 바뀌면(force push·rebase) 워터마크가 무효가 된다.
갱신 전에 **`git merge-base --is-ancestor <last_indexed> <newrev>` 로 검증**하고,
조상이 아니면 **전체 재색인으로 폴백**한다. §8 이 사람 세션의 force push 를 금지하지만
파이프라인 작업자는 `task/<id>` 브랜치에서 자율이므로 배제할 수 없다.

**온톨로지 저장소의 커밋 메시지에도 대응 소스 커밋을 적는다.** 최초 커밋 `0cd8140` 이 이미
`bc4b38f` 를 명시했다 — 두 저장소의 대응 관계가 히스토리로 남는다.

#### 5.5.3-d 🔴 자기 유발 재귀 금지 — 색인 산출물은 이벤트를 만들면 안 된다

색인기가 컨텍스트 MD 를 갱신하고 커밋하는데, 그 커밋이 다시 훅 이벤트를 만들면
**무한 재귀**가 된다. 현재 구조에서는 고리가 끊겨 있다 (확인 2026-08-08):

```
Gitea  sim/modularstage.git      ← 훅이 걸릴 곳 (소스 저장소)
         │ push
         ▼
      스풀 → 색인기 → 컨텍스트 MD 갱신
                          │ commit
                          ▼
~/ax-cluster/ModularStage/   원격 없음 · 활성 훅 없음 ⇒ 이벤트 안 남
```

⚠️ **폴링에서는 안 터지던 것이 이벤트 구동에서는 터진다.** 폴링은 산출물이 안정되면
수렴한다(내용이 같으면 다음 사이클에 할 일이 없다). 이벤트는 **커밋 행위 자체가 이벤트를
만들기 때문에 내용이 같아도 무한히 돈다.** §5.4.5 가 꼽은 "폴링이 공짜로 주던 3가지"에
이어지는 네 번째다.

**불변식 3개 — 어기면 즉시 재귀한다:**

1. **온톨로지/컨텍스트 저장소에 훅을 걸지 않는다.** Gitea 리모트를 붙이더라도
   훅 없는 백업 전용으로만 쓴다(§9.5.2 의 `ax-state` 와 같은 취급).
2. **색인 산출물을 소스 저장소에 커밋하지 않는다.** AgentTest 는 `.claude/` 가 UE5 프로젝트
   디렉토리 안에 있어서 이 구조로 회귀하기 쉽다 — §5.5 가 "데이터를 프로젝트 밖으로"
   결정한 이유와 같은 방향이고, **이벤트 구동에서는 그 회귀가 곧바로 재귀가 된다.**
3. **소비자가 이중으로 막는다.** ⓐ 이벤트의 저장소가 추적 대상 소스 저장소가 아니면 무시
   (§5.5.3-③ 의 409 와 같은 fail-closed), ⓑ 색인기가 만든 커밋에는 트레일러
   `[ax-index]` 를 달고 소비자가 그것을 스킵한다.

✅ **영구 갱신 경로 해결 — ⓐ 채택 (2026-08-08).** `sim` 을 `gitea` 그룹(gid 142)에 추가했다.
`/var/lib/gitea` 는 이미 `drwxr-x---` 라 그룹 실행권한이 있어 추가 `chmod` 는 불필요했다.
`repo/` 의 origin 을 bare 저장소로 직접 물리고 **root 없이 `fetch` 성공**을 실측했다
(`bc4b38f` 확인). 이제 훅 이벤트마다 무인으로 증분 갱신이 가능하다.

```
origin  /var/lib/gitea/gitea-repositories/sim/modularstage.git   (fetch)
origin  DISABLED://…                                            (push)  ← 명시적으로 막았다
```

**push 를 막은 것은 §2.1·§5.5.3-d 의 강제다** — 마스터는 소스 저장소에 쓰지 않는다.
URL 을 지우지 않고 `DISABLED://` 로 둔 것은 실수로 push 했을 때 **조용히 성공하는 대신
눈에 띄게 실패**시키기 위해서다.

⚠️ **운영 주의 2가지**
1. **`safe.directory` 를 global config 에 넣어야 한다** — `sim` 소유가 아닌 저장소라
   git 2.34.1 의 dubious ownership 검사에 걸린다. `-c`·환경변수는 무시되므로
   `git config --global --add safe.directory <bare_path>` 가 유일한 방법이다(§5.5.3-a).
2. **그룹 변경은 이미 떠 있는 프로세스에 소급되지 않는다.** 기존 로그인 셸과 이전에 기동된
   systemd 서비스는 `gitea` 그룹 없이 돌고 있다 — 색인 서비스를 등록할 때 재기동이 필요하다
   (테스트는 `sg gitea -c '…'` 로 했다).

🔴 **미결이었던 항목 (해결됨, 기록용) — 영구 갱신 경로.** 훅 이벤트마다 fetch 하는 것은 **무인 서비스**라 `pkexec` 를
쓸 수 없다(인증 창을 볼 사람이 없다). 초기 사본만으로는 끝나지 않는다:
- **ⓐ `sim` 을 `gitea` 그룹에 추가** (+ `/var/lib/gitea` 에 `g+rx`) — 명령 한 번, 비밀정보 없음
- **ⓒ Gitea 액세스 토큰/배포키** → `http://localhost:3000` 으로 fetch — 파일시스템 배치와
  무관해지지만 토큰 관리가 생기고, 그 토큰이 `ModularStage/` 안에 놓이면 취급에 주의가 필요하다

→ 앞서 ⓐ 를 "Gitea DB 까지 열린다"는 이유로 낮게 봤으나 **그 판단은 정정한다**: 이 박스는
1인 사용이고 `sim` 은 이미 `pkexec` 로 root 가 된다. 그룹 추가로 새로 열리는 실질적 경계가 없다.
인터넷 노출은 Gitea 의 HTTP 계층 문제라 이것과 무관하다.

`bare_path` 가 필요한 이유는 `post-receive` 훅이 **거기 살기 때문**이다(§5.4.2).
훅 설치 대상과 색인 대상이 같은 config 한 곳에서 읽혀야 둘이 어긋나지 않는다.

**기동 시 3자 일치 검사 — 어긋나면 실패한다:**
루트 config 의 `projects` 목록 · 실제 디렉토리 · 각 `project.yaml` 의 `project_id`.
셋 중 하나라도 어긋난 채로 돌면 **어느 인덱스가 어느 저장소 것인지 확신할 수 없게 된다.**

원본/파생 경계는 §5.4.7 에서 이미 확정됐다(원본은 `context/`·`ontology/domains/` 둘뿐,
나머지는 재기동 시 자동 복구). 그 경계를 디렉토리 구조로 굳힌다. config 2종은 **원본**이다.

🔴 **`~/ax-state` 안에 두지 말 것.** 거기는 상태 전이마다 커밋하는 감사 로그 저장소다
(§9.5.2, 현재 `.git` 744K). 색인마다 통째로 바뀌는 바이너리를 넣으면 저장소가 부풀고
감사 로그로서의 가치도 같이 죽는다. **루트를 완전히 분리한다.**

**② `project_id` 는 Gitea 저장소 식별자를 그대로 쓴다.** `post-receive` 훅이 어느
저장소에서 온 이벤트인지 이미 알고 있으므로 `<owner>/<repo>` 를 슬러그화해 쓴다.
**사람이 따로 짓는 별칭을 두지 말 것** — 별칭은 반드시 실제 저장소명과 어긋나고,
그 순간 어느 인덱스가 어느 저장소 것인지 확신할 수 없게 된다.

**③ 단일 마운트 + 명시적 거부 (fail-closed).**

| 상황 | 응답 |
|---|---|
| 요청에 `project_id` 없음 | **400** — 기본값으로 때우지 않는다 |
| `project_id` ≠ 마운트된 프로젝트 | **409** — 마운트된 `project_id` 를 응답 본문에 명시 |
| `/health` | 마운트된 `project_id` 를 항상 노출 |
| 프로젝트 전환 | **서비스 재기동**(환경변수 변경 → `restart`). 런타임 전환 API 를 두지 않는다 |

이 저장소가 이미 두 번 쓴 패턴이다 — 능력 기반 라우팅(`requires ⊆ capabilities`,
fail-closed)과 층2 verdict(§9.4.4). **조용히 답하는 것보다 거부가 낫다.**

**④ 환경변수는 `AX_DATA_ROOT` **하나뿐**, 폴백 없이 즉시 실패.** 마운트 대상은 환경변수가
아니라 **루트 config 의 `active`** 가 정한다 — 환경변수는 "config 가 어디 있나"만 답한다.
`AX_TASK_QUEUE_ROOT` 와 같은 처방이다(§9.5.1) — 폴백을 두면 루트를 잘못 잡아도 조용히
돌다가 **재기동 후에야 "인덱스가 사라졌다"로 발견**된다.

마운트 대상을 config 에 두는 이유: ⓐ systemd 유닛을 건드리지 않고 전환된다,
ⓑ 파일이라 diff·백업·이력이 남는다, ⓒ `projects` 목록과 `active` 가 **같은 파일에
있어 3자 일치 검사가 한 번에 된다**.

**⑤ 이벤트 페이로드에 `project_id` 필수.** 프로젝트가 1개여도 넣는다. 5개 중 유일하게
**소급이 불가능한** 항목이다 — `project_id` 없는 이벤트가 감사 히스토리에 남으면
그게 어느 프로젝트 것이었는지 되살릴 방법이 없다.
연동해서 **§5.4.5 의 중복 합치기 키와 단일 소비자 직렬화 단위도 `project_id` 기준**으로
잡는다. 전역으로 만들면 프로젝트 A 의 재색인이 B 를 통째로 막고, 합치기를 전역으로 하면
서로 다른 프로젝트의 이벤트가 하나로 뭉개진다.

#### 5.5.4 지금 하지 말 것

- **요청 단위 라우팅 / 프로젝트별 컬렉션 분리** — 순수 코드, 나중 비용 동일
- **프로젝트 등록·해제 CLI, 멀티 프로젝트 UI** — 2개째가 생길 때 만든다
- **임베딩 모델 공유 최적화** — 프로세스가 1개면 문제 자체가 없다

→ 두 번째 프로젝트가 생기는 날 할 일이 **"데이터 이사 + 코드 수정"이 아니라 "코드 수정"만**
남는다. 지금 투자로 사는 것은 그것뿐이고, 그것으로 충분하다.

#### 5.5.5 램 증설 판단과의 연결

마스터 램 증설(16GB, 현재 사용 2GB · 메모리 압박 avg300 0.00 · swap 미사용)은 **불필요**로
판단했는데, 그 유일한 반례가 여기다. 프로젝트당 프로세스를 띄우는 방식으로 가면 ONNX
`all-MiniLM-L6-v2` 임베딩 모델이 프로젝트 수만큼 중복 적재된다. **단일 마운트 방식은
그것을 구조적으로 회피한다** — 램이 아니라 설계로 푸는 쪽이다. (§7 의 GPU 증설 검토와는
별개 사안: 그쪽은 임베딩 *가속*이지 다중 적재가 아니다.)

---
