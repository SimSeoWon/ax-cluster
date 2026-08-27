> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

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

[중요] **그 「거부」는 지금 반만 강제된다** (실측 2026-08-22 · 두 번째 프로젝트 NS 가 생겨서
드러났다). 두 축을 섞지 말 것:

    훅 → 색인기    [완료] `#242` — `consumer.process_event` 가 **git 을 부르기 전에** 막고,
                   빈 스풀 폴링도 마운트된 하나만 돈다. **`active` 가 비어도 막는다**(fail-closed).
                   라이브 확인: 마운트 밖 이벤트가 `?→?` 로 건너뛰어진다(커밋도 안 읽는다)
    요청 표면      [완료] 2026-08-22 — `#257`·`#243`. 선언 표(`task_queue/tagging.py`)가 35개
                   라우트에 정책을 붙이고, **쓰는 표면은 태그 없음도 거절**한다(사용자 결정:
                   *"엉뚱한 데이터로 오염되는거잖아"*). `resolve_mounted_only()` 는 이제
                   프로덕션 호출자를 갖는다. 라이브 6/6 거절 확인
    claim 축       [완료] 2026-08-22 — `#247`·`#248`. `ClaimReq.project` 가 생기고 `claimer._call`
                   이 값을 싣는다(읽어 두고 안 보내던 것). 큐는 후보를 **work 스탬프**로 거른다.
                   숨은 선결로 스탬프 없는 옛 work 21건을 백필했다 → 25/25

[중요] **위 셋의 위험도가 다르다.** *요청 표면*은 **지금 트리거된다** — 마운트가 A 인데
요청에 `project: B` 를 담으면 B 의 트윈에 써진다(리포트 29: *"태그가 강제가 아니라 우회의
열쇠였다"*). 반면 *claim 축*은 **두 프로젝트의 태스크가 큐에 동시에 있고 + 다른 프로젝트의
claimer 가 돌아야** 성립한다 — 실측 2026-08-22: 미종결 work 0건 · project 스탬프는 전부
`ModularStage` · claimer 상주는 ModularStage 체크아웃 하나뿐. **잠재이고 현재 노출은 아니다.**

[주의] **claim 축은 2026-08-27 이후 트리거될 수 없다** — `#320` 이 워커 상주를 걷어 **claim 을
보내는 주체가 없다.** 위 문단의 「두 조건」 중 하나가 구조적으로 안 채워진다. 필터 자체는
그대로 살아 있고, 상주가 부활하면 이 위험도 그대로 돌아온다.

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
    ModularStage/                      ← [중요] gitignore. 마스터 로컬 전용 데이터
        .git/                            자체 저장소(원격 없음·훅 없음) — 원본을 잠근다
        context/                         원본 · 텍스트 · 추적
        ontology/domains/                원본 · 텍스트 · 추적
        repo/                            소스 클론 · 파생 · 자체 .gitignore 로 제외
        vector_db/                       파생 · 바이너리 · 제외
    <다음프로젝트>/                     ← 같은 모양으로 나란히 추가
```

[중요] **프로젝트 추가와 마운트 전환은 대화형으로 처리한다 — 스킬 또는 MCP 도구를 만든다**
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
③ 에 따라 거부된다 — [중요] **형태는 `409` 가 아니라 `200 + ok:false + 사유`** 다
(§12.5-c 확정 2026-08-22, 아래 ③ 표 참조).

[주의] **아래는 2026-08-23 에 실물로 갱신했다** (`#227` 소 3.1). 종전 예시는 `projects:` 아래에
**프로젝트별 키**를 그렸는데, 실물은 그렇지 않다 — 루트는 **이름 목록**만 들고 상세는 각
`<프로젝트>/config.yaml` 에 산다. 그 분리가 이 설계의 요점이다: 프로젝트를 하나 추가할 때
루트 파일은 **한 줄**만 자란다.

```yaml
# ~/ax-cluster/projects.yaml  (실측 2026-08-23)
version: 1
active: ModularStage                   # [중요] 없거나 목록에 없으면 기동 실패
projects:                              # **이름 목록뿐이다** — 상세는 각 프로젝트 파일에
- ModularStage
- NS
```

```yaml
# ~/ax-cluster/ModularStage/config.yaml  (프로젝트별 상세가 여기 있다)
project_id: Sim/ModularStage           # Gitea 저장소 식별자 (훅 이벤트가 이걸로 온다)
bare_path: /var/lib/gitea/gitea-repositories/sim/modularstage.git
clone_url: gitea@192.168.0.57:Sim/ModularStage.git
branch: main
index:
  last_indexed_commit: 4cd229f3…       # 워터마크 (#244 — 색인한 것이 있을 때만 전진)
  include: ["Source/**/*.cpp", "Source/**/*.h", "Source/**/*.cs", "Config/**"]
  exclude: ["Content/**"]              # 1,021MB / 전체의 93%
workshops:                             # host → driven/role/user/path (#227 소 1.1: role 필수)
- host: 192.168.0.2
  role: worker
  driven: ssh
  user: janus
  path: E:\trunk\ModularStage
```

**디렉토리명(`ModularStage`)과 `project_id`(`Sim/ModularStage`)를 분리했다.** 전자는 사람이
보는 이름, 후자는 훅 이벤트가 실어 오는 Gitea 식별자다. 규약 ② 의 "별칭 금지"는 여전히
유효하다 — `project_id` 는 **여기서 지어내지 않고 Gitea 값을 그대로 적는다.**

[중요] **유지보수 함정**: 프로젝트를 추가할 때마다 `.gitignore` 에 한 줄을 넣어야 한다.
빠뜨리면 그 디렉토리가 자체 `.git` 을 갖고 있어 **gitlink(서브모듈)로 `git status` 에
나타난다** — 조용히 커밋되지는 않으니 치명적이진 않지만, 반드시 눈으로 확인할 것.
(공통 상위 디렉토리 하나로 묶으면 `.gitignore` 한 줄로 끝나지만, 배치는 위 지시를 따른다.)

[중요] **Gitea 저장소 ROOT 는 `/var/lib/gitea/gitea-repositories` 다 (실측 2026-08-08).**
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

[중요] **색인 대상은 소스뿐이다 — 실측 비율이 93:7 이다** (워킹트리 실측 2026-08-08):

| | 크기/개수 |
|---|---|
| 워킹트리 전체 | 1.1 GB |
| `Content/` (uasset 바이너리) | **1,021 MB — 93%** |
| `Source/**/*.{cpp,h,cs}` | **1,662 개 파일** ← 색인 대상은 사실상 이것뿐 |

제외 패턴은 `project.yaml` 에 둔다. 바이너리를 걸러내지 않으면 색인 비용의 대부분이
버려지는 데이터에 쓰인다.

[주의] **엔진 버전은 `.uproject` 에서 읽을 수 없다.** `EngineAssociation` 이
`{9A68EB04-4D04-82B4-E2C3-6BB594AC0D6E}` — 로컬 엔진 빌드 등록 GUID 다.
온톨로지에 엔진 버전을 1급 속성으로 넣으려면 `Target.cs`/빌드 설정에서 뽑거나
`project.yaml` 에 명시해야 한다.

#### 5.5.3-a [완료] 마스터의 읽기 경로 — 초기 사본 확보 완료, 갱신 경로는 미결

**문제**: bare 저장소는 `gitea:gitea` 소유이고 `/var/lib/gitea` 가 `drwxr-x---` 라
`sim` 이 traverse 하지 못한다. HTTP 는 하드닝 때문에 익명 접근이 **401** 이다.
**마스터 서비스는 `sim` 으로 돌기 때문에 두 문 모두 닫혀 있다.**

[완료] **초기 사본은 확보했다 (2026-08-08)** — `~/ax-cluster/ModularStage/`
아래 `repo.git`(bare 사본 1,006MB) + `repo`(워킹트리 1.1GB, `main`). 이제 root 없이 읽힌다.
이것은 §5.5 규약 ⓑ 의 첫 실물이고, §2.1 "마스터는 파일을 소유하지 않는다"와 충돌하지 않는다 —
그 원칙이 금지하는 것은 편집·빌드이고, 읽기 전용 색인 사본은 §2.1 이 마스터 몫으로 지정한
RAG/온톨로지 그 자체다.

[주의] **git 2.34.1 함정 (2026-08-08 실측)**: `safe.directory` 는 **system/global config 에서만**
읽힌다. `-c safe.directory=...` 도 `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0` 환경변수도 **무시된다**
(둘 다 `fatal: detected dubious ownership` 로 실패). root 로 남의 저장소를 다루는 스크립트는
`git clone` 대신 `cp -a` 를 쓰거나 global config 를 건드려야 한다.

#### 5.5.3-b [완료] 온톨로지 자산 이관 완료 (2026-08-08)

윈도우 메인 작업용 PC(**192.168.0.33**)에서 `--export-state` 산출물
(`infra_state_20260808.zip`, 1.5MB)을 받아 규약 경로에 배치했다.
(다른 윈도우 PC는 **192.168.0.2** — UE5 설치됨, SSH 22 열림.
 ~~무인증 키는 미교환~~ → **2026-08-08 교환 완료: `ssh janus@192.168.0.2` 무비밀번호 접속됨.**
 계정은 `sim` 이 아니라 `janus` 다. 상세는 `machines/sim-desktop.md` § Machine inventory.)

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

[완료] **신선도 검증 통과 — 재추출 불필요** (실측):

| | 시각 |
|---|---|
| 5.8 API 대응 커밋 `9efbfc1` | 2026-08-02 16:29:43 |
| `MCP 추가` `bc4b38f` | 2026-08-02 16:45:39 |
| **컨텍스트 MD 최종 갱신** | **2026-08-02 17:35:40** ← 두 커밋보다 나중 |

즉 모듈 구조 정리·5.8 API 대응이 **반영된 뒤** 추출된 자산이다.
컨텍스트 MD 927개 : 소스 1,662개는 커버리지 부족이 아니라 `.h`/`.cpp` 쌍이 MD 하나를
공유하기 때문이다(표본 확인: `FHexGridSceneProxy.{h,cpp}` → MD 1개).

[주의] **`StructUtils` 는 잔재가 아니다.** 현재 소스에 10건 남아 있으나 전부
`#include "StructUtils/InstancedStruct.h"` — 커밋 메시지의 "include 경로" 항목에 해당하는
5.8 경로 변경이다. 커밋 요약만 보고 "제거하다 만 흔적"으로 판단하면 틀린다.

[완료] **원본 버전 관리 완료 (2026-08-08).** 이 자산은 이관 전까지 **윈도우 1대에만 있었고
git 에도 없었다**(§5.4.7 기준 원본이라 재색인으로 복구되지 않는다). 프로젝트 디렉토리를
**로컬 git 저장소로 만들어 잠갔다** — `~/ax-cluster/ModularStage/`, 최초 커밋
`0cd8140`, 추적 1,312개. `.gitignore` 로 `vector_db/`·`bm25.db`·`class_graph.db`·
`dependency_graph.db`(파생)와 `repo/`·`repo.git/`(원본이 Gitea 에 있음)을 제외한다.
저장소를 **프로젝트당 하나**로 둔 것은 §5.5 의 프로젝트 격리와 경계를 일치시키기 위해서다.

#### 5.5.3-c [중요] 색인 워터마크 — 커밋 해시를 기록한다 (2026-08-08 확정)

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

[중요] **폴백이 반드시 필요하다.** 히스토리가 바뀌면(force push·rebase) 워터마크가 무효가 된다.
갱신 전에 **`git merge-base --is-ancestor <last_indexed> <newrev>` 로 검증**하고,
조상이 아니면 **전체 재색인으로 폴백**한다. §8 이 사람 세션의 force push 를 금지하지만
파이프라인 작업자는 `task/<id>` 브랜치에서 자율이므로 배제할 수 없다.

**온톨로지 저장소의 커밋 메시지에도 대응 소스 커밋을 적는다.** 최초 커밋 `0cd8140` 이 이미
`bc4b38f` 를 명시했다 — 두 저장소의 대응 관계가 히스토리로 남는다.

#### 5.5.3-d [중요] 자기 유발 재귀 금지 — 색인 산출물은 이벤트를 만들면 안 된다

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

[주의] **폴링에서는 안 터지던 것이 이벤트 구동에서는 터진다.** 폴링은 산출물이 안정되면
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
   ([주의] **fail-closed 의 형태는 `409` 가 아니라 「건너뛰고 사유를 남긴다」** — 훅 경로엔
   HTTP 응답이 아예 없다. 실측 2026-08-22: `consumer.process_event` 가 `skipped` 로 돌려준다.
   `409` 는 ③ 의 HTTP 초안에서 흘러온 표현이다), ⓑ 색인기가 만든 커밋에는 트레일러
   `[ax-index]` 를 달고 소비자가 그것을 스킵한다.

[완료] **영구 갱신 경로 해결 — ⓐ 채택 (2026-08-08).** `sim` 을 `gitea` 그룹(gid 142)에 추가했다.
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

> [중요] **보강 2026-08-14 — 봉인은 남고, 쓰기는 옆문으로 간다** (Flow Y, 사용자 확정).
> 같은 클론에 push 전용 두 번째 remote 가 붙었다:
>
> ```
> gitea-write  gitea@192.168.0.57:Sim/ModularStage.git   (fetch·push)   ← attempt/* · task/* 만
> origin       DISABLED://…                             (push)         ← 봉인 유지
> ```
>
> [주의] **왜 bare 에 직접 안 쓰나** — 실측: bare 는 `drwxr-xr-x gitea:gitea` 라 `gitea` 그룹에
> **쓰기가 없다.** `g+w` 를 주면 Gitea 의 receive 훅·브랜치 보호·DB 갱신을 **우회**하게 되므로,
> 쓰기는 Gitea 정규 경로(SSH)로만 간다. 읽기는 지금처럼 파일시스템 + `sg gitea` 다.
>
> [중요] **§5.5 의 불변식은 안 깨진다** — 정본 트리는 계속 `main` 에 앉아 있고 마스터는 정본에
> 커밋하지 않는다. 작업은 `<프로젝트>/ax-wt-<work_id>` 워크트리에서 일어난다(정본 **옆**).
> 그리고 attempt push 는 색인기를 깨우지만 `merge --ff-only FETCH_HEAD` 의 for-merge 항목이
> `main` 의 업스트림뿐이라 **`from == to` 로 재색인을 건너뛴다**(실측: `b1ba6af9→b1ba6af9`).
> → `reports/16-master-write-surface.md`

[주의] **운영 주의 2가지**
1. **`safe.directory` 를 global config 에 넣어야 한다** — `sim` 소유가 아닌 저장소라
   git 2.34.1 의 dubious ownership 검사에 걸린다. `-c`·환경변수는 무시되므로
   `git config --global --add safe.directory <bare_path>` 가 유일한 방법이다(§5.5.3-a).
2. **그룹 변경은 이미 떠 있는 프로세스에 소급되지 않는다.** 기존 로그인 셸과 이전에 기동된
   systemd 서비스는 `gitea` 그룹 없이 돌고 있다 — 색인 서비스를 등록할 때 재기동이 필요하다
   (테스트는 `sg gitea -c '…'` 로 했다).

[중요] **미결이었던 항목 (해결됨, 기록용) — 영구 갱신 경로.** 훅 이벤트마다 fetch 하는 것은 **무인 서비스**라 `pkexec` 를
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

[중요] **`~/ax-state` 안에 두지 말 것.** 거기는 상태 전이마다 커밋하는 감사 로그 저장소다
(§9.5.2, 현재 `.git` 744K). 색인마다 통째로 바뀌는 바이너리를 넣으면 저장소가 부풀고
감사 로그로서의 가치도 같이 죽는다. **루트를 완전히 분리한다.**

**② `project_id` 는 Gitea 저장소 식별자를 그대로 쓴다.** `post-receive` 훅이 어느
저장소에서 온 이벤트인지 이미 알고 있으므로 `<owner>/<repo>` 를 슬러그화해 쓴다.
**사람이 따로 짓는 별칭을 두지 말 것** — 별칭은 반드시 실제 저장소명과 어긋나고,
그 순간 어느 인덱스가 어느 저장소 것인지 확신할 수 없게 된다.

**③ 단일 마운트 + 명시적 거부 (fail-closed).**

[중요] **아래 표는 2026-08-22 에 배선된 실물로 갱신했다.** 종전 표는 `400`/`409` 를 적었고,
그 형태는 **채택되지 않았다** — `ax-client` 가 4xx/5xx 를 [미연결]로 읽어 **지난 스냅샷을
정답처럼 돌려주기** 때문이다(§12.5-c). 그리고 「프로젝트 전환 = 서비스 재기동」도 채택되지
않았다: `set_active` 가 런타임에 바꾸고 다음 호출이 바로 새 경로를 본다(`paths.resolve` 가
매 호출 레지스트리를 읽는다).

| 상황 | 응답 (실물) |
|---|---|
| 요청에 태그 없음 · **쓰는** 표면 | **200 + `ok:false` + `status:no_project_tag`** — 기본값으로 때우지 않는다. 태그가 없으면 마운트로 「가정」하게 되고 그것이 오염 경로다 |
| 요청에 태그 없음 · **읽는** 표면 | 통과 — 오염이 없다. 태그는 필터로만 쓴다(`GET works?project=NS`) |
| 태그 ≠ 마운트 | **200 + `ok:false` + `status:not_mounted`** — 마운트된 이름을 본문에 명시 |
| 태그 ≠ 그 work 의 스탬프 | **200 + `ok:false` + `status:project_mismatch`** — [중요] 이 축은 마운트와 비교하지 않는다(`#210`) |
| `/health`·`/livez` | 프로젝트 축이 없다(`OPEN`) |
| 프로젝트 전환 | `set_active` — **런타임**. 재기동하지 않는다 |

[중요] **사유를 셋으로 가른 이유는 고칠 곳이 다르기 때문이다**: `no_project_tag` 는 발신자
배선, `not_mounted` 는 마운트 전환, `project_mismatch` 는 요청자의 착각이다.

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

#### 5.5.4 [중요] 워크숍 측 체크아웃 — 관례를 채택한다, 데몬은 두지 않는다 (2026-08-08 확정)

**빈칸이었다.** §5.5.1~3 은 전부 **마스터의 디지털 트윈**(`~/ax-cluster/<Project>/`) 이야기다.
정작 UE5 프로젝트가 실제로 빌드되는 **윈도우 작업장 쪽 경로는 결정된 적이 없었다.**
사용자가 "그럼 .2 에 언리얼 프로젝트 설치 장소는 어떻게 관리할 거냐"고 물어서 드러났다.

##### 실측 — 관례가 이미 있다 (192.168.0.2, 2026-08-08)

```
E:\trunk\  ├─ ModularStage\    ← origin = http://192.168.0.57:3000/Sim/ModularStage.git
           │                     branch main · bc4b38f "MCP 추가" (마스터 bare 와 일치)
           ├─ Monster\
           ├─ PanoramaTest\
           └─ Project_Alpha\
```

`E:\trunk\<ProjectName>\` — **마스터의 `~/ax-cluster/<Project>/` 와 같은 모양이다.**
E: 드라이브 여유 499GB. 새 관례를 만들 이유가 없다 → **이걸 채택하고 등록만 한다.**

##### ① 데몬을 두지 않는다 — SSH 가 이미 그 일을 한다

AgentTest 가 `watch.exe` 폴링 데몬을 둔 이유는 **팀원 PC 에 접근 경로가 없었기 때문**이다
(메모리 `agenttest-deployment-model`: zip 을 UE5 루트에 풀고 `while True` 로 git 을 폴링).
지금 `.2` 는 SSH 가 열려 있다 — 마스터가 밀어넣을 수 있다.

**데몬을 두는 것은 SSH 가 이미 주는 것을 다시 만드는 것이고, §5.4 가 마스터에 대해 폴링을
기각한 것과 같은 논리다.** 그리고 AgentTest 의 수명주기 문제(자식 프로세스 감독의 주인이
`watch.exe` 였던 것)를 그대로 물려받지 않는 길이기도 하다.

[중요] **단, 데몬이 하던 일 중 하나는 남는다.** UE5 에디터 내장 MCP 와 `gjc` 는 **loopback 전용**이라
그 PC *안에서* 떠 있어야 한다(§9.1, `client/README.md` 4·5). 이것은 **상시 데몬이 아니라
작업 단위로 SSH 로 띄우고 끝나면 내리는** 형태로 충족된다. 상시화는 필요해진 뒤에 하고,
할 때도 "무엇이 그 프로세스의 주인인가"를 먼저 정하고 한다.

##### ② 머신마다 구동 방식이 다르다 — 이건 우연이 아니라 기록할 사실이다

| 머신 | 구동 | 근거 |
|---|---|---|
| `.2` (RTX 3060) | **`driven: ssh`** — 마스터가 밀어넣는다 | SSH 22 열림 (`janus`), 무비밀번호 |
| `.33` (메인 작업 PC) | **`driven: interactive`** — 마스터가 몰지 않는다 | **SSH 없음(RDP 뿐)**. 사용자가 앉아서 Claude Code 로 작업 |

`.33` 은 대화형이므로 경로 등록도 데몬도 필요 없다. 자동화가 필요해지면 선택지는
ⓐ SSH 를 열거나 ⓑ 거기만 데몬을 두는 것이고, **ⓑ 를 고르기 전에 ⓐ 를 먼저 검토한다.**

##### ③ 레지스트리 스키마 — `ax-projects`(8103) 를 확장한다, 새 계층을 만들지 않는다

프로젝트 레지스트리가 이미 있다(§5.5.3-①, `master/projects/`). 워크숍 경로는 그 안에 넣는다.

```yaml
ModularStage:
  project_id: Sim/ModularStage         # [주의] 대소문자 — 아래 ④
  workshops:
    "192.168.0.2":
      user: janus
      path: 'E:\trunk\ModularStage'
      driven: ssh
    "192.168.0.33":
      driven: interactive              # 경로 없음 — 마스터가 몰지 않는다
```

**마스터가 경로를 아는 것은 파일을 소유하는 것이 아니다** — §2.1 위반이 아니라 라우팅
메타데이터다. 마스터는 여전히 그 디렉토리를 읽지도 쓰지도 않는다.

##### ④ [완료] 대소문자 — 확정 (2026-08-08, Gitea DB 실측)

**Gitea 는 이름을 두 벌로 들고 있다.** DB(`repository` 테이블)를 직접 읽어 확정했다:

| 컬럼 | 값 | 쓰임 |
|---|---|---|
| `owner_name` / `name` | **`Sim/ModularStage`** | 표시용. **훅 페이로드가 싣는 `full_name` 이 이것** |
| `lower_name` | **`modularstage`** | **디스크 경로 · 동일성 판정** |

소유자 `Sim` 아래 5개 저장소가 전부 CamelCase 다
(`GeminiScripter`·`ModularStage`·`Project_Alpha`·`ScenarioWriter`·`ServerTest`).
§5.5.3 에 적힌 소문자 목록은 `lower_name` 을 본 것이었다 — **둘 다 실재하는 값이고,
어느 한쪽이 틀린 게 아니다.**

**결정 — Gitea 자신의 모델을 그대로 따른다:**

> **저장은 표시용 정규값으로, 비교는 casefold 로, 디스크 경로는 소문자로.**
> 표시 이름은 라벨이고 **동일성은 소문자다.** Gitea 가 `lower_name` 컬럼을 따로 두는
> 이유가 그것이다.

§5.5.4 초안은 "둘 중 하나를 고르라"고 했지만, 실측해 보니 **고를 문제가 아니었다** —
두 값은 용도가 다르고 둘 다 필요하다. 하나로 통일하려 했다면 어느 쪽을 골라도 깨진다:

| 잘못된 통일 | 무엇이 깨지나 |
|---|---|
| 전부 `Sim/ModularStage` 로 | `resolve_bare_path` 가 `gitea-repositories/`**`Sim/ModularStage`**`.git` 를 찾다 실패한다 — **그런 디렉토리는 없다** |
| 전부 `sim/modularstage` 로 | 훅이 `Sim/ModularStage` 로 오는데 config 는 소문자 → 규약 ③ 의 **fail-closed 에 전부 걸려 색인이 조용히 안 돈다**([주의] 형태는 409 가 아니라 「건너뛴다」) |

**구현 (`master/projects/`, 2026-08-08):**

| 함수 | 역할 |
|---|---|
| `normalize_project_id()` | 동일성 키 — casefold + strip |
| `project_id_disk_path()` | 디스크 경로용 소문자 접기 |
| `Registry.find_by_project_id()` | 훅 페이로드 → 프로젝트명. **대소문자 무시**, 못 찾으면 빈 문자열(호출자가 fail-closed — 소비자는 **건너뛴다**) |

`resolve_bare_path()` 는 이제 `Sim/ModularStage` 를 받아도 소문자 경로를 찾는다.
`ModularStage/config.yaml` 의 `project_id` 는 **`Sim/ModularStage`** 로 갱신했고,
`bare_path`/`clone_url` 은 소문자 그대로 뒀다 — 디스크와 URL 은 그게 맞다.

[중요] **casefold 비교를 넣은 이유는 관용이 아니라 rename 방어다.** Gitea 에서 대소문자만
바꾸는 rename 은 `lower_name` 을 바꾸지 않는다. 표시값만 비교하면 그 rename 한 번에
훅이 전부 거부되고, **아무 에러 없이 색인만 멈춘다.**

##### ④-1 [주의] 실측 중 나온 운영 사실 두 가지

**1. Gitea DB 경로가 `/usr/local/bin/data/gitea.db` 다.**
`app.ini` 의 `[database] PATH` 가 **상대 경로**(`data/gitea.db`)로 적혀 있어 Gitea 의
작업 디렉토리(`/usr/local/bin`) 기준으로 풀린 결과다. 표준 배치(`/var/lib/gitea/data/`)를
가정하면 엉뚱한 곳을 본다. `DB_TYPE = sqlite3` 인데 `HOST = 127.0.0.1:3306` 이 남아 있는
것도 혼동을 부른다 — **sqlite3 에서 `HOST` 는 쓰이지 않는다.**

**2. `sim` 은 `gitea` 그룹에 등록돼 있지만 현재 세션에는 반영돼 있지 않다.**
`id sim` 에는 `142(gitea)` 가 보이는데 실행 중인 셸의 `id` 에는 없다 — 그룹 추가 후
**재로그인하지 않았다.** 그래서 `/var/lib/gitea` 가 `drwxr-x---`(그룹 r-x)인데도
`sim` 프로세스는 traverse 하지 못한다. §5.5.3-a 가 "읽기에는 sim 이 gitea 그룹에
있어야 한다"고 적어둔 조건이 **파일상으로는 충족, 런타임으로는 미충족**인 상태다.
DB 조회는 `pkexec` 로 했다. 재로그인하면 root 없이 읽힌다.

##### ⑤ UE5 특유의 제약 세 가지

- [중요] **워크숍마다 별도 체크아웃이 필수다 — 공유 불가.** 작업장이 2대이고 둘이 같은 프로젝트의
  같은 `task/<id>` 브랜치를 만진다(§4.2). 하나의 워킹트리를 공유하면 claim/lease/fencing 이
  방어하려던 것이 워킹트리 레벨에서 그대로 터진다.
- [중요] **파생물을 "지우고 다시 받으면 된다"로 전제하지 말 것.** `.2` 실측에
  `DerivedDataCache` · `Intermediate` · `Binaries` · `Saved` 가 전부 존재한다. git 밖이 맞지만
  **재생성이 빌드 수십 분**이다. 워크숍 초기화·전환 절차를 짤 때 이것을 비용으로 계산한다.
- [주의] **OneDrive 동기화 경로에 UE5 프로젝트를 두지 말 것.** `.2` 에
  `C:\Users\janus\OneDrive\문서\Unreal Projects\LyraStarterGame` 가 있다(우리 것은 아니다).
  `E:\trunk\` 관례를 쓰는 한 걸리지 않지만, 새 워크숍을 세팅할 때 기본 경로가
  OneDrive 아래로 잡히는 사고가 흔하다.

##### ⑥ [완료] loopback 프로세스 수명주기 — 세션 경계가 주인을 정한다 (2026-08-08 확정)

§5.5.4-① 이 "작업 단위로 SSH 로 띄우고 내린다"고만 적고 **누가 주인인가를 미뤄뒀다.**
실측해 보니 **하나의 답이 아니었다** — 윈도우의 세션 격리가 프로세스를 두 부류로 가른다.

**실측 (192.168.0.2, 2026-08-08):**

```
SSH 로 들어온 프로세스의 SessionId = 0      ← 서비스 세션
query session → console  janus  9  활성     ← 데스크톱은 세션 9
```

[중요] **윈도우 세션 0 은 데스크톱에 접근할 수 없다.** SSH 로 GUI 앱을 띄우면 세션 0 에서
돌고 사용자 화면에는 나타나지 않는다. 이건 설정으로 우회하는 게 아니라 OS 의 격리다.

**그래서 주인이 갈린다:**

| 프로세스 | 데스크톱 필요? | 마스터가 SSH 로 소유 가능? | 주인 |
|---|---|---|---|
| **Unreal MCP** (GUI 에디터 내장) | [완료] 세션 9 | [실패] **구조적으로 불가** | **세션 9 의 사람** (또는 그 세션의 Claude Code) |
| **`gjc`** (CLI 하네스) | [실패] | [완료] | **마스터** — 작업 단위 |
| **`UnrealEditor-Cmd`** (commandlet · 빌드 · RunTests) | [실패] | [완료] | **마스터** — 작업 단위 |

**① Unreal MCP 는 설계에서 뺀다 — 띄우는 절차를 만들 수 없다.**
에디터 내장 MCP 의 수명은 **에디터의 수명**이고, 에디터는 세션 9 의 GUI 앱이다.
마스터가 원격으로 여는 경로가 없다. §9.1 이 "loopback 전용이라 마스터가 붙을 수 없다"고
한 것은 *네트워크* 이야기였는데, **세션 경계에서 한 번 더 막힌다** — 붙을 수 없는 게
아니라 **띄울 수도 없다.**
→ `ue-editor-operator` 서브에이전트는 계속 그 PC 안에서 돈다(`client/README.md` 4).
마스터는 이 프로세스에 대해 아무 수명주기 책임도 지지 않는다.

**② `gjc` 와 `UnrealEditor-Cmd` 는 SSH 세션이 곧 수명이다.**

> **SSH 연결이 주인이다.** 연결이 끊기면 자식도 죽는다 — 이게 버그가 아니라 **설계다.**

작업 단위로 띄우고 작업이 끝나면 연결을 닫는다. 감독자(supervisor)가 필요 없고,
고아 프로세스도 생기지 않는다. **AgentTest 가 `watch.exe` 로 자식을 `.poll()` 감시해야
했던 이유가 여기서 사라진다** — 그때는 프로세스를 소유할 주체가 그 PC 안에밖에 없었다.

[중요] **"SSH 세션보다 오래 살아야 한다"가 나오면 그건 서비스가 필요하다는 신호다.**
그때 손으로 감독자를 짜지 말고 **윈도우 서비스 또는 작업 스케줄러**에 넘긴다 —
마스터에서 `process_lifecycle.py` 를 폐기하고 systemd 에 넘긴 것(§5.4.3)과 같은 판단이다.
**필요해지기 전에는 하지 않는다.**

**③ [완료] 층3 원격 구동 — 실검증 완료 (2026-08-08).**
`UnrealEditor-Cmd` 가 세션 0 에서 돈다는 것은 **`RunTests` 를 마스터가 SSH 로 몰 수 있다**는
뜻이다(§4.3 층3). 추측이 아니라 **실제로 돌려서 확인했다.**

엔진: `C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe`
(`.uproject` 의 `EngineAssociation` 이 GUID → **`5.8`** 로 전환됨, 사용자 작업 2026-08-08.
런처 기록 `C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat` 가 권위 있는 출처다 —
HKLM 레지스트리에는 5.4/5.5 만 있어 5.8 을 못 찾는다).

```bat
UnrealEditor-Cmd.exe <uproject> -ExecCmds="Automation RunTests <필터>; Quit" ^
    -unattended -nopause -nosplash -nullrhi -stdout -NoLogTimes
```

`-nullrhi` 가 핵심이다 — RHI 를 띄우지 않으므로 데스크톱 없는 세션 0 에서 성립한다.

| 실행 | 결과 |
|---|---|
| `Automation List` | 45초. 엔진 초기화(ZenServer·DDC·셰이더 워커 5) → 테스트 **8,726개** 열거 → `EXIT CODE: 0` |
| `Automation RunTests System.Core.Algo` | 25초. **5건 전부 `Result={Success}`**, 실패 0 → `EXIT CODE: 0` |

##### ③-1 [중요] 판정 신호를 잘못 고르면 층3 게이트가 통째로 틀린다

실검증에서 **함정 두 개**가 나왔다. 둘 다 "그럴듯한 신호"가 틀린 경우다.

**1. SSH 의 종료 코드를 믿으면 안 된다 — 양방향으로 틀린다.**

| 실행 | 실제 결과 | `ssh` 종료 코드 |
|---|---|---|
| `UnrealEditor-Cmd` (테스트 통과) | 성공 (`EXIT CODE: 0`) | **1** ← 거짓 실패 |
| `Build.bat` (성공) | `Result: Succeeded` | 0 |
| `Build.bat` (**실패**) | `Result: Failed (RulesError)` | **0** ← **거짓 성공** |

[중요] **마지막 줄이 위험한 쪽이다 — 실패한 빌드를 통과시킨다.**
감싼 배치의 `%ERRORLEVEL%` 는 빌드에서는 맞았지만(0 vs 8) **에디터 실행에서는 기록조차
되지 않았다.** 래퍼로도 메울 수 없다.
→ **종료 코드로 게이트하지 말고 로그를 파싱하라. 예외 없다.**

**2. `Error` 문자열로 판정하면 안 된다.**
**전부 통과한 실행에 `LogAutomationTest: Error` 가 15줄 있었다.** 실패를 일부러 유발해
보는 부정 경로 검사들이 그렇게 로그를 남긴다. `grep -i error` 로 게이트를 짜면
**통과한 빌드를 실패로 판정한다.**

**→ 올바른 신호는 이 둘뿐이다:**

```
LogAutomationController: Display: Test Completed. Result={Success|Fail} Name={..} Path={..}
LogAutomationCommandLine: Display: **** TEST COMPLETE. EXIT CODE: N ****
```

`Result={Fail}` 개수 == 0 **그리고** `EXIT CODE: 0` 일 때만 통과다.
둘 중 하나라도 없으면(로그가 잘렸거나 프로세스가 죽었거나) **fail-closed 로 실패 처리**한다 —
§9.4.4 의 층2 VERDICT 계약이 "마지막 비어 있지 않은 줄" 을 못박은 것과 같은 종류의 규약이고,
같은 이유로 필요하다.

##### ③-2 [완료] `Build.bat` 원격 구동 — 실검증 완료 (2026-08-08)

Jenkins 등이 쓰는 표준 UBT 호출을 그대로 SSH 로 돌렸다. **환경은 이미 갖춰져 있었다** —
`Build.bat` · `UnrealBuildTool.exe` · **Visual Studio Community 2022 (C++ 도구)**.
프로젝트 타깃은 `ModularStageEditor`(같은 `Source/` 에 `Project_AlphaEditor` 도 있다).

```bat
call "<Engine>\Engine\Build\BatchFiles\Build.bat" ModularStageEditor Win64 Development ^
     -Project="E:\trunk\ModularStage\ModularStage.uproject" -WaitMutex
```

| 실행 | 로그 판정 | 소요 |
|---|---|---|
| `ModularStageEditor` (증분) | **`Result: Succeeded`** · `Target is up to date` | **1.9초** |
| `NoSuchTargetXYZ` | **`Result: Failed (RulesError)`** | 1.0초 |

증분이라 빠르다 — 사용자가 이미 빌드를 성공시켜 둔 상태였다. **콜드 빌드는 여전히 수십 분
예상**이며 측정하지 않았다.

[중요] **빌드의 판정 신호는 테스트와 다르다:**

```
Result: Succeeded | Failed (<사유태그>)
Total execution time: N seconds
```

`TEST COMPLETE. EXIT CODE:` 는 여기 나오지 않는다 — 도구가 다르면 계약도 다르다.
게이트는 둘을 각각 파싱해야 한다(`master/layer3_verify.py` 가 그렇게 돼 있다).

##### ⑥-1 자동화가 쓸 체크아웃 — 기존 것을 쓰고, 더러우면 멈춘다

**질문:** 마스터 자동화가 사람의 `E:\trunk\ModularStage` 를 그대로 써도 되나, 아니면
전용 클론을 따로 파야 하나 (사용자 제기 2026-08-08).

**결정 — 지금은 기존 것을 쓴다.** 근거는 §5.5.2 와 같은 **비용 비대칭**이다:

| | 지금 재사용 | 지금 분리 |
|---|---|---|
| 디스크 | 0 | +1.1GB |
| **DerivedDataCache · Binaries** | **이미 빌드돼 있다** | **처음부터 재생성 — 빌드 수십 분** (§5.5.4-⑤) |
| 나중에 필요해지면 | 클론 한 번 | 이미 했음 |

`.2` 는 *워커*로 지정된 머신이고 사람의 메인 작업 PC 는 `.33` 이다(§5.5.4-②).
동시 사용이 실제로 일어나지 않는 동안 재생성 비용을 미리 낼 이유가 없다.

[중요] **단, 진짜 위험은 충돌이 아니라 데이터 손실이다.** 자동화는 브랜치를 바꾸고 경우에
따라 리셋한다. 사람이 커밋하지 않은 작업을 남겨 뒀다면 그걸 날린다.
→ **fail-closed 로 막는다.** 클론을 하나 더 파는 것보다 싸고, 방어 대상이 정확하다.

[주의] **단 "더럽다"를 뭉뚱그리면 안 된다 — 추적 파일과 미추적 파일은 위험이 다르다.**
실측(2026-08-08) `E:\trunk\ModularStage` 는 **지금도 더럽다**: `?? AgentWiki/`, `?? AgentWiki.zip`.
전부 미추적이다. 이걸 뭉뚱그려 막으면 **자동화가 첫날부터 아무것도 못 한다.**

| 상태 | `git checkout` / `reset --hard` 가 날리나 | 판정 |
|---|---|---|
| 추적 파일 수정·스테이지 (` M`·`M `·`A `) | **날린다** | [중요] **차단** |
| 미추적 (`??`) | 날리지 않는다 (`git clean` 만 지운다) | [완료] 통과 |

**규칙: 추적 파일에 변경이 있으면 시작하지 않는다. 미추적은 통과시킨다.
그리고 자동화는 `git clean` 을 절대 부르지 않는다** — 그게 미추적을 안전하게 만드는 전제다.

```bash
# 차단 조건: 미추적(??)을 제외하고 남는 게 있으면 더티
git -C <path> status --porcelain | grep -v '^??' | head -1
```

**분리해야 하는 시점 — 아래 중 하나라도 참이 되면 그때 판다:**

- 사람이 `.2` 에서 그 프로젝트를 실제로 작업하기 시작한다
- `.2` 에서 태스크를 **동시에 2개 이상** 돌린다
- 자동화가 `main` 이 아닌 브랜치를 오래 물고 있어야 한다

분리할 때는 **DDC 를 공유**하면 재생성 비용 대부분을 피할 수 있다
(UE5 의 공유 DDC 경로 설정). 클론마다 DDC 를 새로 굽지 않아도 된다.

##### ⑥-2 선결 설치 현황 (192.168.0.2, 실측 2026-08-08)

| 도구 | 상태 | 비고 |
|---|---|---|
| `node` | [완료] **v24.11.1** | `C:\Program Files\nodejs\node.exe`. `client/README.md` 의 "⬜ 미설치" 는 **낡았다** |
| `npm` 전역 | [완료] | `%APPDATA%\npm` — 현재 `gemini.cmd` 하나 |
| `claude` | [완료] 2.1.225 | `C:\Users\janus\.local\bin\claude.exe` |
| `git` | [완료] | PATH 에 있음 |
| **`gjc`** | ⬜ **미설치** | §9 의 전제. node 가 있으니 설치 자체는 막힌 게 없다 |
| **`bun`** | ⬜ 미설치 | `gjc` 가 Bun 런타임을 요구하면 선결 |

[주의] **SSH 세션 PATH 가 최소라 `where`/`Get-Command` 로는 안 보인다** —
절대경로로 확인해야 한다(`machines/sim-desktop.md` § `.2` SSH access notes).
이 함정 때문에 이 표를 만드는 동안 node 를 두 번 "미설치"로 오판했다.

##### 미결

- [x] ~~`workshops` 스키마 + `ax-projects` 도구~~ — **완료 2026-08-08.** 도구 7종,
      `.2`(ssh·janus·`E:\trunk\ModularStage`) · `.33`(interactive) 실등록
- [x] ~~④ 의 대소문자 정규값 확정~~ — **완료 2026-08-08.** `Sim/ModularStage`(표시) /
      `modularstage`(동일성). 구현·테스트 완료, `config.yaml` 갱신됨
- [x] ~~loopback 프로세스 수명주기 — 누가 주인인가~~ — **완료 2026-08-08** (⑥).
      세션 0/9 경계가 갈랐다: Unreal MCP 는 마스터가 **띄울 수도 없고**(설계에서 제외),
      `gjc`·`UnrealEditor-Cmd` 는 **SSH 연결이 곧 수명**이다(감독자 불필요)
- [x] ~~**층3 원격 구동 실검증**~~ — **완료 2026-08-08** (⑥-③). `Automation List`(8,726개 열거) ·
      `RunTests System.Core.Algo`(5건 전부 Success) 둘 다 SSH·세션 0 에서 성공.
      판정 신호 함정 2건(SSH 종료 코드 · `Error` 문자열)을 ⑥-③-1 에 기록
- [x] ~~**`Build.bat` 원격 구동 확인**~~ — **완료 2026-08-08** (⑥-③-2). 증분 1.9초 성공 ·
      없는 타깃 `Failed (RulesError)`. [중요] 실패해도 `ssh` 는 0 을 낸다는 것이 여기서 드러났다
- [ ] **콜드 빌드 실측** — 증분만 쟀다. 전체 빌드 소요는 여전히 미측정(수십 분 예상)
- [x] ~~**층3 게이트 구현**~~ — **완료 2026-08-08.** `master/layer3_verify.py` +
      테스트 44건. 통과 조건 4가지(완료 마커 · `EXIT CODE 0` · `Fail` 0건 · `Success` ≥1),
      나머지는 전부 fail-closed. **판정에 프로세스 반환 코드도 `Error` 문자열도 쓰지 않는다.**
      실제 `.2` 로 end-to-end 검증(`PASS(5건)`).
      [주의] 실측 정정: 매치 없는 필터는 UE 5.8 에서 **`EXIT CODE: -1`** 이다 —
      "매치 없어도 exit 0" 이라던 초안 근거는 틀렸다. 규칙은 이중 방어로 남긴다
- [ ] **`gjc`(+필요시 `bun`) 설치** — `.2` 에 미설치. node v24.11.1 은 있다 (⑥-2)
- [x] ~~**자동화 진입 전 더티 체크 구현**~~ — **완료 2026-08-08.**
      `master/projects/workshop_check.py` + MCP 도구 `check_workshops_clean_tool`(8종째).
      추적 파일만 차단 · 미추적 통과 · **확인 실패는 차단**(fail-closed) · `git clean` 없음.
      테스트 47건(`test_workshop_check.py`) — SSH 없이 runner 주입으로 판정 규칙만 검사

---

#### 5.5.5 지금 하지 말 것

- **요청 단위 라우팅 / 프로젝트별 컬렉션 분리** — 순수 코드, 나중 비용 동일
- **프로젝트 등록·해제 CLI, 멀티 프로젝트 UI** — 2개째가 생길 때 만든다
- **임베딩 모델 공유 최적화** — 프로세스가 1개면 문제 자체가 없다

→ 두 번째 프로젝트가 생기는 날 할 일이 **"데이터 이사 + 코드 수정"이 아니라 "코드 수정"만**
남는다. 지금 투자로 사는 것은 그것뿐이고, 그것으로 충분하다.

#### 5.5.6 램 증설 판단과의 연결

마스터 램 증설(16GB, 현재 사용 2GB · 메모리 압박 avg300 0.00 · swap 미사용)은 **불필요**로
판단했는데, 그 유일한 반례가 여기다. 프로젝트당 프로세스를 띄우는 방식으로 가면 ONNX
`all-MiniLM-L6-v2` 임베딩 모델이 프로젝트 수만큼 중복 적재된다. **단일 마운트 방식은
그것을 구조적으로 회피한다** — 램이 아니라 설계로 푸는 쪽이다. (§7 의 GPU 증설 검토와는
별개 사안: 그쪽은 임베딩 *가속*이지 다중 적재가 아니다.)

---
