> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

## 5. 마스터 오케스트레이션 언어 — Python 확정 (2026-08-06)

**결론: Python.** 신규 선택이 아니라 *기존 자산을 이식*하는 문제였다. 근거는 AgentTest 코드베이스 실측.

### 5.1 근거

**① 이미 67,038줄이 동작 중이다** (199개 `.py`, plan v5.0 기준 533 테스트 통과)

| 영역 | 줄 수 |
|---|---|
| `mcp/` (task_queue · context_search · master_orchestrator) | 26,424 |
| `watcher/` (RAG · 온톨로지 · 클래스 그래프) | 21,171 |
| `tests/` | 14,246 |
| `worker/` | 3,657 |

**② Windows 의존이 92줄뿐이다 (0.14%)** — `win32`/`ctypes.windll`/`winreg`/`STARTUPINFO`/`.bat` 기준.

> ⚠️ **이 수치는 과대평가다 (2026-08-07 실측 정정).** grep 이 **주석·문자열까지 세고 있다.**
> `mcp/context_search/` 의 6건을 실제로 열어보니 3건은 "install.bat 을 다시 실행하세요" 안내 **문자열**,
> 2건은 **주석**, 1건은 docstring 의 `C:\temp\...` **예시 경로**였고 **진짜 코드는 1줄**
> (`llm_chat.py:196` — `agy_path.endswith(('.cmd','.bat'))`)뿐이다.
> **실질 이식 장벽은 이 숫자보다 훨씬 작다.** 판정 기준으로는 `sys.platform`/`os.name` 분기가 더 정확하며,
> 그 기준으로는 `context_search` 0건 · `task_queue` 2건(둘 다 리눅스 분기 존재) · `watcher/` 3건이다(§5.4.7).
게다가 가장 밀집한 곳이 **어차피 Windows 에 남아야 할 컴포넌트**다:
`ue_builder.py`(19) · `commandlet_runner`(5) · `ue_test_runner.py`(2).
**리눅스로 옮길 컴포넌트의 Windows 의존은 약 30줄.** 이식이지 재작성이 아니다.

**③ ChromaDB 는 Python 네이티브다.** Go 로 가면 벡터 DB 교체(Qdrant 등) + 임베딩 파이프라인
(ONNX `all-MiniLM-L6-v2`) 재구축까지 딸려온다. 언어 교체가 아니라 스택 교체가 된다.

**④ Go 의 강점이 이 워크로드에 안 맞는다**

| Go 장점 | 이 프로젝트 |
|---|---|
| 단일 바이너리 | 이미 PyInstaller 로 `.exe` 빌드 중(`build.bat`) |
| 동시성 | I/O 바운드(Ollama HTTP · git). asyncio 로 충분 |
| 실행 성능 | 병목은 **LLM 추론(초 단위)** — 오케스트레이션(ms)은 노이즈. 실측 14B 22 t/s |

### 5.2 이식 대상 — 컴포넌트 배치

2026-07-07 아키텍처 합의("RAG/온톨로지/그래프는 엔진과 무관한 순수 데이터 작업이므로 인프라에 둔다")를 구체화.

**A. 리눅스 마스터(57)로 이전** — 순수 데이터/판단 계층, UE5 무관

| 컴포넌트 | 규모 | Windows 의존 | 비고 |
|---|---|---|---|
| `watcher/` 전체 | 21,171줄 | 19줄 | git watch · RAG · 온톨로지 · 클래스 그래프. 정리 대상: `review.py`(5) · `network_firewall.py`(4) · `skill_defs_distribute.py`(4) · `process_lifecycle.py`(3) · `watch.py`/`common.py`/`agent_defs.py`(각 1). **⚠️ `process_lifecycle.py` 는 이식이 아니라 폐기 — §5.4** |
| `mcp/context_search/` | — | 6줄 | ChromaDB + BM25. `remote_client.py`(3) · `wiki_local_tools.py`/`search_tools.py`/`llm_chat.py`(각 1) |
| `mcp/task_queue/` | — | 5줄 | 작업 분배·claim·fencing. `logic_cleanup.py`(3) · `reclaim.py`/`persistence.py`(각 1) |
| `mcp/master_orchestrator/` 中 오케스트레이션 부분 | — | — | 골조 생성·분배·라우팅. **UE 빌드/테스트 부분은 제외**(아래 B) |
| **`mcp/agy_query/`** | 194줄 | — | 🔴 **§5.2 목록에 빠져 있던 것 추가** — Antigravity CLI(`agy`) 위임. 마스터가 오케스트레이션하려면 필수(층2 검증). **⚠️ 마스터에 `agy` 미설치** |
| **`mcp/local_llm_runner/`** | 144줄 | — | 🔴 **누락분 추가** — Ollama 위임. **§6.4 추론 래퍼와 역할이 겹치므로 재사용/대체를 먼저 정할 것**(§3 미결) |

**B. Windows 잔류** — 엔진 바운드, **다른 곳에서 할 수 없는 것만**

| 컴포넌트 | Windows 의존 | 사유 |
|---|---|---|
| `mcp/master_orchestrator/ue_builder.py` | 19줄 | `UE Build.bat` 실행 |
| `mcp/master_orchestrator/ue_test_runner.py` | 2줄 | `UnrealEditor-Cmd RunTests` |
| `mcp/master_orchestrator/executor_integration_build.py` | 3줄 | 통합 빌드 게이트 |
| `mcp/master_orchestrator/tdd_dryrun.py` | 1줄 | TDD 드라이런 |
| `mcp/commandlet_runner/` | 5줄 | UE 커맨드릿 |

| `worker/` 전체 | 14줄 | **작업자 하네스 — 파일을 소유하는 계층**(§2.1) |

> **⚠️ 2026-08-07 정정** — 한때 `worker/` 를 A(마스터 이전)로 옮겼으나 **되돌렸다.**
> 마스터는 인프라지 작업장이 아니다. BC-250 이 인계한 것은 **추론 연산**이지 파일 작업이 아니다.

**C. 빌드 러너는 고정하지 않는다** — 2026-07-07 합의대로 "1차 통합 빌드게이트"를 인프라에 박지 않고
**task_queue 잡으로 큐잉해 UE5 를 가진 기계가 claim 하는 CI 러너 패턴**으로 분리한다.
이래야 마스터가 UE5/Windows 에 묶이지 않는다.
**선결이던 능력 기반 라우팅**(`requires: ue5`)은 **2026-08-08 구현·실측 완료**다.
`master/task_queue` 가 task 의 `requires` 와 워커가 claim 시 신고한 `capabilities` 를
**부분집합 매칭(fail-closed)** 한다 — 능력을 신고하지 않은 워커는 `requires` 붙은 잡을 못 집는다.

| 계약 | 값 |
|---|---|
| task 쪽 | `POST /api/v1/tasks` 의 `requires: ["ue5"]` (빈값 = 아무나) |
| 워커 쪽 | `POST /api/v1/tasks/claim` 의 `capabilities: ["ue5"]` (**미신고 = 능력 없음**) |
| 허용 태그 | `ue5`(에디터+빌드 툴체인) · `windows`. **화이트리스트 밖은 등록 시점에 400** |
| 적용 범위 | write 잡 + **verify 잡 양쪽.** 검증자도 diff 를 쥐려면 파일 소유 기계여야 한다(§2.1) |
| 관측 | `GET /api/v1/admin/workers` 의 `capabilities` + 로그 `능력 미달로 N건 skip` |

**미지 태그를 등록 시점에 거부하는 이유**: claim 쪽이 fail-closed 라 오타 하나(`ue-5`)면
**아무 워커도 만족시킬 수 없는 task** 가 조용히 pending 에 굶는다. 조용한 기아보다 등록 실패가 낫다.
테스트 `master/test_capability_routing.py` (16건).

**D. 🔴 팀 때문에 존재하는 것 — 이식이 아니라 축소·폐기 후보 (2026-08-07 신설)**

§2.0 의 전제에 따라 **"이 컴포넌트가 팀 때문에 존재하나?"** 로 걸러낸다. 1인 클러스터에선 의미가 없거나
크게 단순해진다. **착수 전 개별 판단할 것 — 일괄 폐기하지 말 것.**

| 후보 | 팀 전용인 이유 |
|---|---|
| 작성자별 분리 (`reviews/<작성자>/` · `plans/<작성자>/`) | 작성자가 하나뿐 |
| 리더 검수 `/review-work` | 리더와 작업자가 동일인 |
| 비개발자 위키 클라이언트 (`AgentWiki`, `packaging/wiki_client/`, `build_wiki_client.bat`) | 기획팀 대상 — 범위 밖 |
| Redmine 연동 (`mcp/redmine_tracker/`, `planner_redmine.py`) | 팀 이슈 트래킹 |
| zip 패키징 · `install.bat` · `bump_version.ps1` | 설치해줄 팀원이 없음(마스터는 §5.4.3 대로 systemd) |
| PC 별 `config.json` 보존 로직 | PC 마다 VRAM 이 다른 팀 상황 전제 |

**⚠️ 반대로 걷어내면 안 되는 것**: claim/lease/fencing·reclaim. 1인이지만 **오케스트레이터가 셋이고
파일을 소유한 작업장이 2대**라
공유 자원 경쟁이 실재한다(§2.2-5).

#### 5.2-E ✅ 디지털 트윈의 범위 — **소스 한정** (사용자 지시 2026-08-08)

> **RAG 부터 디지털 트윈 전반 모두 소스 부분에 한정으로 관리한다.**

미결이던 "RAG 이식 범위 — 검색 코어만 vs 온톨로지까지" 의 답이다.
**둘 중 하나를 고르는 문제가 아니었다** — 범위를 가르는 축이 *모듈*이 아니라 **데이터**다.

##### ① 무엇이 트윈의 대상인가

| | |
|---|---|
| ✅ **대상** | `Source/**/*.{cpp,h,cs}` · `Config/**` — **코드와 그 코드에서 파생되는 것 전부** |
| ❌ **비대상** | `Content/**` (uasset 바이너리), 레벨·블루프린트·에셋 트윈 |

**이미 그 형태다 — 이관 비용이 0 이다.** 실측(2026-08-08):

- `ModularStage/config.yaml` 의 `index.include/exclude` 가 **이미 소스만** 잡고 있다
  (`Content/**` 제외 — 워킹트리 1.1GB 중 **1,021MB(93%)** 가 uasset 이다, §5.5.3)
- 확보한 온톨로지 **247개 yaml / 7개 도메인이 전부 소스 파생**이다.
  표본(`ProjectAlpha_UiViewManagement/domain.yaml`)의 객체가 `WNDUIViewManager` ·
  `UWNDUIViewBase` · `FViewDataBase` · `EUILayer` · `FGlobalEventSystem` —
  **전부 C++ 심볼**이고 도메인이 코드 모듈에 대응한다
- 컨텍스트 MD **1,055개**도 소스 기준이다(`.h`/`.cpp` 쌍이 MD 하나를 공유, §5.5.3-b)

→ **결정이 데이터 배치를 바꾸지 않는다.** 확정하는 값어치는 *지금* 이 아니라 나중에 있다:
"에셋도 트윈에 넣자" 는 요구가 왔을 때 **범위 밖이라고 말할 근거**가 생긴다.

##### ② 이식 범위 — 🔴 **기능으로 갈라라. 그리고 "만드는 쪽" 이 목표다** (2026-08-08 재정정)

> ⚠️ **이 절은 두 번 틀렸다.**
> ⑴ 첫 판 — `ontology_*` 를 한 덩어리로 묶어 "2단계" 로 미뤘다. 그 안에서 **합성/색인/조회/관리**
> 가 갈리는데 묶어 버려 "온톨로지는 큰 작업" 이라는 오판이 오래 남았다.
> ⑵ 두 번째 판 — 갈라 놓고는 *"데이터를 받아왔으니 **쓰는 쪽만** 옮기면 된다"* 고 결론했다.
> 🔴 **사용자가 확정한 목표 ①이 "온톨로지 문서를 자동으로 작성" 이므로 만드는 쪽이 곧 목표다.**
> 받아온 247 yaml 은 **출발점이지 대체물이 아니다** — 스냅샷은 자라지 않는다.

**남는 결정 = 갈라야 한다는 것.** 그리고 갈래는 **줄 수가 아니라 계산 성격**이다 —
LLM 0(커밋 즉시) / LLM 자동(게이트) / 사람·대화형 / 소비. 소분류와 진행 상태는
[`milestones/2-twin-restoration.md`](milestones/2-twin-restoration.md) (대 2 · 중 9 · 소 43).

🔴 **줄 수를 작업량으로 쓰지 않는다.** `class_graph` 1,341줄은 `data-schema.md` 기준
*"파일 삭제 → 재기동 시 풀 스캔"* 이고, 반대로 829줄짜리 `domain_index.py` 하나에 도메인
색인·규범 검색·**시소러스 빌더**가 같이 들어 있다.

| 기능 | 어디 | 마일스톤 2 |
|---|---|---|
| 컨텍스트 MD 합성 | `watcher/context*` | 🔴 중 1.2 — **상류** |
| 클래스·의존 그래프 | `watcher/class_graph*` · `dependency.py` | ✅ **중 1.1 완료** → `master/graph/` |
| 온톨로지 합성 (수동·대화형 + 휴리스틱) | `watcher/ontology_*` | 중 1.3 — **목표 ① 그 자체** |
| 도메인 색인 + 규범 검색 + **시소러스 빌더** | `mcp/context_search/domain_index.py` | 소 2.1.1·2.1.2·1.4.3 |
| 조회 도구·라우트 / 관리(CRUD) | `ontology_query_tools` · `ontology_manage*` | ⬜ 노출·편집이 필요해질 때 |
| 도메인 뷰어(웹) · 드리프트 · 상태 임포트 | `domain_viewer_routes` · `ontology_drift*` · `state_transfer` | 소 2.4.2 · 2.4.1 · 2.4.3 |

##### ②-1 🔴 `domain_index.py` 는 의존성이 stdlib 뿐이다 (실측)

```
domain_index.py 의 모듈 수준 import: json · re · pathlib · typing   ← 그게 전부다
                    (BM25FieldIndex·chromadb 는 함수 안에서 지연 import)
```

**이식에 연쇄가 없다.** 우리 `master/context_search/bm25.py`(이미 이식됨)를 그대로 재사용한다.
소비 배선(대 2)은 이 한 파일에 거의 다 들어 있어 **상류(중 1.1·1.2)보다 싸다** — 다만 **싸다는
것이 먼저 한다는 뜻은 아니다.** 색인할 데이터를 만드는 쪽이 없으면 스냅샷을 다시 색인할 뿐이다.

무엇을 만드나:

- **별도 BM25 DB**(`bm25_domains.db`) + **별도 벡터 컬렉션**(`ontology_domains`)
  — 컨텍스트 MD 색인과 **완전히 분리**된다. 서로 오염되지 않는다
- 도메인이 수십 개 규모라 **증분 없이 전체 재빌드**한다 (원본 주석 그대로)
- 색인 본문 = `summary` + `core_responsibilities` + `invariants` + 하위 `actions/*.yaml` ·
  `invariants/*.yaml` 본문. tags 채널에 도메인명도 넣어 자연어 발화가 걸리게 한다

🔴 **`search_domain_norms` 의 노이즈 차단 정책을 반드시 함께 옮길 것** — 원본이 회사 환경에서
검증했다고 기록한 규칙이다:

1. **BM25 0건이면 빈 결과.** 도메인 yaml 은 광범위한 신호라 벡터만으로는 무관한 질의에도
   약한 hit 이 난다. *"모든 검색에 도메인이 끼어드는"* 상태가 되는 것을 막는다
2. 벡터 단독 매칭은 `similarity ≥ 임계값`(기본 0.2)만 인정
3. 개수 상한 `top_k`(기본 2)

이 세 줄을 빼먹으면 **검색 품질이 조용히 나빠진다** — 결과가 늘어나므로 겉보기엔 좋아 보인다.

##### ②-2 🔴 우리가 이미 밟은 함정 — 임포트는 됐는데 sync 를 안 했다

`state_transfer.import_state` 의 독스트링이 자산을 두 부류로 갈라 **경고해 두었다**:

| 자산 | 복구 |
|---|---|
| 컨텍스트 벡터(`context_a/b`) · `bm25.db` · `class_graph.db` | 재기동 시 **자동 감지·재구축** |

🔴 **위 '재기동' 이 우리에게는 없다.** 원본 `watch.exe` 는 상주 데몬이라 재기동이라는 순간이
있지만, 우리 색인기는 inotify 로 깨어나는 oneshot 이다. 그래서 관계 그래프의 재구축을
**명시 명령**(`python -m master.graph build`)으로 두었다 — 자동 감지에 기대면 도메인 색인이
`sync_domain_index` 호출을 놓쳐 검색 0건이 된 것과 같은 방식으로 영영 안 돈다.

| **도메인 인덱스**(`bm25_domains.db` + `ontology_domains`) | 🔴 **자동 감지 없음 — `sync_domain_index` 를 명시 호출해야 한다** |

이유도 적혀 있다: 자동 sync 는 *"stale 도메인이 있을 때"* 재합성의 부수효과로만 도는데,
**임포트 직후에는 온톨로지가 소스와 이미 일치해 stale 이 아니라 그 경로가 영영 안 걸린다.**

우리 상태가 정확히 그것이다 — `ontology/_export_manifest.json` 은 있는데 `bm25_domains.db` 는
없다. **온톨로지 검색이 0건인 것은 "미이식" 이 아니라 "명시 호출 누락" 이었다.**

##### ③ 단계를 나눌 수 있다 — 둘은 서로 import 하지 않는다 (실측)

```
검색 코어 ─┬─▶ ontology_*  : import 0건
           └─▶ domain_*    : import 0건
온톨로지  ──▶ search_*     : import 0건
```

결합은 **`http_server.py` 의 라우트 등록부 한 곳뿐**이다(`register_ontology_routes` 등).
따라서 **검색 코어만 먼저 세우고 온톨로지를 나중에 붙이는 것이 가능하다.**

🔴 **단, 완전한 독립은 아니다.** 검색 코어가 `class_graph_query` 를 통해 `class_ontology`
테이블을 읽어 **질의에서 도메인을 추론**한다(`search_tools.py:285`, `search_backend.py:41`).
다행히 **그 테이블이 없으면 빈 결과로 떨어진다**(구 DB 호환 경로가 그렇게 돼 있다) —
즉 **온톨로지 없이도 검색은 돌고, 있으면 도메인 추론이 얹힌다.**
1단계를 먼저 세워도 되는 근거가 이것이다.

⚠️ **그 "얹힘" 이 여전히 빠져 있다 — 다만 이유가 바뀌었다** (2026-08-08 갱신).
`class_graph.db` 는 생겼다(클래스 1,806 · 메서드 6,380, 중 1.1 완료). 그런데 그 안의
**`class_ontology` 테이블이 0건**이라 도메인 자동 추론은 그대로 빈 결과다 — 그 테이블은
중 1.3(온톨로지 합성)이 채운다. 즉 **"DB 가 없다" 에서 "DB 는 있고 분류가 없다" 로 옮겨왔을
뿐**이고, 검색은 여전히 **설계된 성능이 아니다.** "돈다" 와 "제대로 돈다" 를 구분할 것.

##### ④ 이 결정이 풀어 주는 것

**이벤트 큐 소비자(§5.4.5-a)를 만들 수 있게 됐다.** 무엇을 색인할지가 정해졌기 때문이다:
`claim_batch()` → 프로젝트별 `last_indexed_commit` → HEAD 의 **소스 변경분**만 재색인.
`Content/` 를 보지 않으므로 **재색인 비용의 93% 가 애초에 발생하지 않는다.**

##### ④-1 진행 상태는 **마일스톤 문서에 둔다**

여기는 *무엇을 어떻게 하기로 했나* 만 담는다. 진행은
[`milestones/2-twin-restoration.md`](milestones/2-twin-restoration.md).

🔴 이 결정만 남긴다: **"완료" 는 영역 전체에만 쓴다.** 부분이면 분모를 같이 적는다.
만든 것만 골라 범위를 좁힌 뒤 완결을 선언하면 남은 일이 보이지 않는다 — 마일스톤 1 이
그렇게 실패했다.

##### ④-2 웹 UI — 🔴 이전 판단 **"마스터엔 화면이 없다" 를 뒤집는다**

그 판단은 데이터가 각 PC 에 흩어져 있던 때의 것이다. **지금은 마스터가 트윈을 단독으로
들고 있어 화면을 놓을 자리가 여기밖에 없다.** 사용자가 원본에서 쓰던 것도 그 화면이다
(*"데몬을 킬 때 웹서버를 켜서 저장된 디지털 트윈 정보를 보여줬다"*).

- `domain_viewer_routes.py` 555줄 — 도메인 뷰어. `cs_common`(이식됨) + `llm_chat`(선택) 의존
- 🔴 **읽기 전용 뷰어는 색인 없이도 된다** — yaml 을 직접 파싱해 트리로 보여주면 되므로
  `domain_index` 이식을 기다릴 필요가 없다. 급하면 이쪽이 빠르다
- 브라우저가 붙으므로 `master/auth.py` 에 **Basic 인증**이 필요하다(베어러 헤더를 브라우저가
  안 붙인다). 토큰 계층을 우회하지 말고 확장할 것

##### ⑤ 남은 실무 함정

- **임포트 형태가 다르다.** AgentTest 는 `from cs_common import ...` 처럼 **플랫 임포트**다
  (디렉터리를 `sys.path` 에 올려 쓴다). 마스터는 패키지 상대 임포트(`from .config import`)를
  쓰므로 **기계적이지만 전 파일에 걸친 수정**이 필요하다.
- **`project_root` 가 기동 시 고정된다** — §5.5.1 이 이미 짚은 것. 단일 마운트(§5.5.2)로
  회피하기로 했으므로 1단계에서는 코드를 고치지 않는다.
- **임베딩 모델은 `all-MiniLM-L6-v2`** — CPU 로 돌린다. §7 의 GPU 증설이 여기 가속용이지
  **필수는 아니다.**

### 5.3 이식 순서

이식 진행 상태는 [`milestones/2-twin-restoration.md`](milestones/2-twin-restoration.md).
아래는 **2026-08-07 당시의 순서 제안**이고 그 뒤 바뀐 지점이 있다 — 제안만 읽고 판단하지 말 것.

#### 원래 제안 (2026-08-07)

1. `mcp/task_queue/` — 루프의 중추이고 Windows 의존 5줄로 가장 가볍다. 먼저 옮겨 마스터에서 기동.
   **선결: 수명주기 주인 교체** — 현재 `watch.py` 가 자식 프로세스로 띄우고 감시한다(§5.4.3).
   떼어내 독립 서비스로 만드는 것이 이 단계의 실제 작업량이다.
2. `mcp/context_search/` — ChromaDB 인덱스 이관(재색인 필요 여부 확인).
3. `watcher/` — 가장 크지만 순수 데이터라 기계적. 단 **`watch.py` 의 폴링 루프는 그대로 옮기지 않는다**
   — Gitea 이벤트 구동으로 대체(§5.4.2). `process_lifecycle.py`·`network_firewall.py` 는 **폐기**(§5.4.3).
4. **`mcp/agy_query/` 이전** — 층2 검증용(**`agy` 설치 완료 — 리포트 04**). 리눅스에선 PTY 코드 불필요.
5. `master_orchestrator/` 분할 — 오케스트레이션 부분만 이전, UE 부분은 §5.2-B 로 남기고
   §5.2-C 의 큐 잡 패턴으로 연결.

**이식 시 함께 처리할 설정 변경**
- `local_llm_model` 기본값을 `gemma4:e4b` → **`qwen2.5-coder:14b`** 로 변경 (§4.4 참조).
  config 로 덮어쓰는 것만으로도 동작하지만, 기본값 자체를 바꿔야 설정 누락 시 조용한 Gemma 폴백을 막는다.
- 추론 엔드포인트 기본값 `http://localhost:11434` → BC-250 노드 주소로. 마스터에는 Ollama 가 없다.

**마스터 선결 설치 (2026-08-07 실측)**

| 도구 | 상태 | 필요한 이유 |
|---|---|---|
| `claude` | ✅ 있음 (`~/.local/bin/claude`, v2.1.223) | 층2 검증 폴백 · 마스터 오케스트레이션 |
| `agy` (Antigravity CLI) | ✅ **설치·인증·검증 완료 2026-08-07** (`~/.local/bin/agy`, **v1.1.10**) | 층2 검증 1순위(`syntax_check` 가 agy 우선) · `mcp/agy_query/` |
| `bun` / `node` | ❌ **없음** | gajae-code 가 TypeScript/Bun (§1) |

**🔴 `agy` 이식 부담이 크게 줄었다 — AgentTest 의 윈도우 대응책이 리눅스에선 불필요하다.**
`history/2026-06-28_1619_gemini_to_agy_migration.md` 가 기록한 함정 4종이 v1.1.10 에서 **전부 해소**됐다
(마스터 리포트 04 실측):

| AgentTest 기록 (2026-06-28, 윈도우) | 2026-08-07 리눅스 실측 |
|---|---|
| `agy -p` 가 비-TTY 면 0바이트 + 20s hang → **가상 PTY(pywinpty) 전환** | ✅ 순수 파이프로 정상 |
| 출력에 터미널 init ANSI 섞임 → **정규식 strip** | ✅ 깨끗한 텍스트 |
| **argv 순서 버그**(`-p` 를 맨 끝에, 6곳 정정) | ✅ 순서 무관 |
| `agy models` 스피너 TUI 미종료 | ✅ 즉시 반환 |

**→ `_agy_pty_call` 헬퍼(5개 호출부 중복) · `--collect-all winpty` 번들 · ANSI strip · argv 정정이
리눅스 이식 대상에서 빠진다.** `pywinpty` 는 윈도우 전용이라 어차피 등가물로 바꿔야 했는데 그 작업 자체가 사라졌다.
⚠️ 윈도우(`client/`)에도 적용되는지는 **미확인** — 별도 실측 필요.

**💡 신규 `--output-format json`** (AgentTest 시점엔 없던 옵션) — `status` · `response` ·
`usage{input/output/thinking/cache_read/total_tokens}` 를 구조화해 반환한다.
모토상 **상용 토큰 계측이 곧 비용 관리**인데 별도 계측 코드 없이 얻고,
`**TASK_COMPLETE**` 센티넬 파싱보다 견고하다. `stream-json` 도 있다.

**⚠️ agy 자율 에이전트에 저장소 작업을 위임하지 말 것** — AgentTest 가 사고를 기록했다
(agy 자율 에이전트가 동의 없이 `watcher/common.py` 수정). `--dangerously-skip-permissions` 를 쓰므로
작업 디렉터리를 가진 채 자율 실행시키면 파일을 건드린다. **층2 용도(텍스트 in/out)로만 쓸 것.**

**주의:** 위 줄 수/의존 집계는 2026-08-02 클론 기준이다.
→ **2026-08-07 마스터에서 재확인 완료**: 199개 `.py` / 67,038줄 / Windows 의존 **93줄**. 수치 유효.
마스터 클론 위치는 `/home/sim/AgentTest`(**참조용 — 수정하지 않는다**), 이 저장소는 `/home/sim/ax-cluster`.

### 5.4 마스터 실행 모델 — 폴링 데몬이 아니다 (2026-08-07)

AgentTest 를 그대로 옮기면 안 되는 이유가 여기 있다. **배포 형태와 실행 모델이 마스터에서는 성립하지 않는다.**

#### 5.4.1 AgentTest 의 현재 형태 (실측)

`build.bat` 이 PyInstaller `--onefile` 로 **exe 12종**을 빌드해 `AgentWatch.zip` 으로 배포하고,
팀원이 **UE5 프로젝트 루트에 압축 해제**한다. `watch.exe`(데몬) · `worker.exe` · MCP 서버 10종
(`context_search` `log_analyzer` `crash_analyzer` `commandlet_runner` `agy_query` `redmine_tracker`
`code_recipes` `task_queue` `master_orchestrator` `local_llm_runner`).

`watcher/watch.py main()` 이 `while True` 로 `poll_interval` 초마다 git fetch/pull → 새 커밋 감지 →
처리. MCP 서버와 task_queue 는 **자식 프로세스로 띄우고 `.poll()` 로 생존 감시**한다
(`common._server_proc`, `common._task_queue_proc`). `config.json` 은 PC 별 파일이라 재배포에도 보존된다.

**마스터에는 UE5 프로젝트 루트도 팀원별 사본도 없다.** 배포 단위(zip+exe)와 수명주기 관리를
그대로 옮길 수 없다.

#### 5.4.2 폴링 → 이벤트 구동 (Gitea 가 같은 박스에 있다)

`watch.exe` 가 폴링하는 건 **팀원 PC 가 git 서버 입장에서 외부인이라 알림받을 방법이 없기 때문**이다.
마스터는 반대로 **Gitea 를 직접 호스팅**한다(`gitea.service`, :3000). 알림을 받을 수 있다.

| | 폴링 (AgentTest) | 이벤트 (마스터) |
|---|---|---|
| 감지 지연 | `poll_interval` 초 | 즉시 |
| 유휴 시 비용 | 계속 fetch | 0 |
| 튜닝 | 간격 결정 필요 | 불필요 |

- **Gitea 웹훅** — push 시 지정 URL 로 HTTP POST. 같은 박스라 `localhost` 로 쏘면 네트워크 신뢰성 문제 없음.
- **`post-receive` 훅** — push 순간 서버에서 스크립트 직접 실행. 네트워크조차 안 탄다.
  ⚠️ 단 **훅 안에서 무거운 작업(RAG 색인 등)을 하면 그동안 push 가 멈춘다.** 훅은 알림만 던지고 즉시 종료할 것.

#### 5.4.2-a 🔴 훅 설치 지점 — `post-receive.d/` 다 (실측 2026-08-08)

`hooks/post-receive` 는 **Gitea 가 자동 생성하며 첫 줄이 `# AUTO GENERATED BY GITEA,
DO NOT MODIFY` 다.** 덮어쓰면 Gitea 내부 동작이 깨진다. 실제 내용은 디스패처다:

```bash
data=$(cat)                                   # stdin(refs)을 한 번 읽고
for hook in ${GIT_DIR}/hooks/${hookname}.d/*; do
  test -x "${hook}" && test -f "${hook}" || continue
  echo "${data}" | "${hook}"                  # 각 훅에 순차로 먹인다 (동기)
  exitcodes="${exitcodes} $?"
done
for i in ${exitcodes}; do [ ${i} -eq 0 ] || exit ${i}; done   # 하나라도 실패면 push 실패
```

→ **우리 훅은 `hooks/post-receive.d/ax-event` 로 설치한다.** (현재 그 디렉토리엔
Gitea 자신의 `gitea` 훅 1개만 있다.) 여기서 두 가지가 강제된다:

1. **디스패처가 훅을 동기로 기다린다.** §5.4.2 의 "즉시 종료" 요구가 관례가 아니라
   **기계적 사실**로 확인됐다. HTTP 호출조차 하지 말 것 — 큐가 느리면 push 가 그만큼 멈춘다.
2. 🔴 **훅이 0 이 아닌 값을 반환하면 push 자체가 거부된다.** 즉 이벤트 큐가 죽어 있을 때
   훅이 실패하면 **개발자가 push 를 못 한다.** 작업장을 막는 것은 어떤 경우에도 안 된다.

→ **훅은 로컬 스풀 파일에 append 하고 항상 `exit 0` 한다.** 네트워크도 서비스 의존도 없다
(파일 append 는 실패할 여지가 사실상 없다). 소비자가 그 스풀을 읽어 처리한다.
이렇게 하면 **push 를 막지 않으면서 이벤트도 잃지 않는다** — §5.4.5 가 요구한 영속성이
바로 이 스풀이다. 다른 곳의 fail-closed 원칙(§9.4.4)과 방향이 반대인데, **여기서 막히는
대상이 사람의 push 이기 때문**이다. 의도된 예외다.

**⚠️ 데몬이 없어지는 게 아니다.** 사라지는 건 폴링 루프뿐이고 상주 프로세스는 여전히 필요하다:
① 웹훅을 받을 쪽이 떠 있어야 하고 ② `task_queue` 는 작업자가 claim 하러 붙는 **HTTP 서버**라
태생이 상주 서비스이며 ③ RAG 인덱스·추론 브로커도 계속 살아 있어야 한다.

**작업자(윈도우) 쪽은 그대로다** — `worker.exe` 는 여전히 외부인이라 task_queue 에 폴링으로 붙는다.
폴링이 없어지는 것은 마스터 한정.

#### 5.4.3 수명주기는 systemd 가 가져간다 — `process_lifecycle.py` 는 폐기

리눅스의 데몬 = **systemd 서비스**. 이 박스의 `gitea.service` 가 정확히 그 형태다.
**PyInstaller 빌드는 불필요** — exe 로 묶는 건 "팀원 PC 에 Python/의존성이 없어서"인데
마스터는 통제 가능한 한 대뿐이라 venv 로 충분하다.

```ini
# /etc/systemd/system/ax-task-queue.service (예시)
[Service]
ExecStart=/home/sim/ax-cluster/.venv/bin/python -m master.task_queue
Restart=always
User=sim
[Install]
WantedBy=multi-user.target
```

| `watch.py` 가 손수 하던 것 | systemd |
|---|---|
| 자식 프로세스 `.poll()` 생존 감시 | `Restart=always` |
| Job Object 로 고아 프로세스 정리 (**Windows 전용**) | cgroup 자동 |
| 로그 파일 관리 | journald (`journalctl -u`) |
| 기동 순서 조율 | `After=` / `Requires=` |
| 포트 점유 해제·방화벽 규칙 (`network_firewall.py`, **Windows 전용**) | firewalld/ufw 로 별도 관리 |

**→ `process_lifecycle.py`·`network_firewall.py` 는 리눅스 등가물로 고쳐 쓸 게 아니라 폐기하고
systemd 에 넘긴다.** 각 컴포넌트를 독립 유닛으로 두면 §5.3-1 의 "task_queue 수명주기 주인" 문제도 사라진다.

#### 5.4.4 ✅ 확정 — **systemd + venv** (2026-08-08)

`~/CLAUDE.md`(마스터) 규약은 "새 서비스는 Docker Compose 선호"다(n8n·Redmine 이 그 패턴).
**그럼에도 systemd 로 간다** — 코드 실측 결과 이 워크로드는 호스트에 깊이 결합돼 있다:

| 결합 | 근거 (실측 2026-08-08) |
|---|---|
| **호스트 CLI + 홈 디렉터리 인증** | 층2 검증이 `agy`·`claude` 를 subprocess 호출 — `mcp/agy_query/server.py:70`, `mcp/context_search/llm_chat.py:71`. 바이너리는 `~/.local/bin`, 인증 상태는 홈 디렉터리 |
| **git + SSH 키** | `task_queue` 가 **매 상태 전이마다** `git add`/`commit`(감사 로그) — `mcp/task_queue/persistence.py:299~340`. `watcher/git_ops.py` subprocess `git` 8건 |
| **Gitea 가 호스트 systemd 서비스** | §5.4.2 `post-receive` 훅이 호스트에서 실행. 컨테이너면 훅→컨테이너 전달 경로를 별도 구축(브리지 IP 하드코딩) |
| **BC-250 LAN** | 보드 firewalld 가 **192.168.0.57 만** 11434 허용 — 컨테이너 NAT 출발지를 별도 검토해야 함 |
| **미래 CUDA** (§7) | nvidia-container-toolkit 한 겹 추가. 드라이버조차 미설치 |

**Compose 의 이점(의존성 격리·재현성)이 여기선 약하다** — 의존성이
`mcp chromadb fastapi uvicorn tree-sitter tree-sitter-cpp`(`build.bat:29` 기준, `pywinpty` 제외)
**전부 순수 pip 패키지**라 venv 로 동일하게 얻는다. `requirements.txt` 는 없어 이식 시 새로 만든다.

**규약과 어긋나지 않는다** — n8n·Redmine 은 업스트림 이미지를 그대로 쓰는 **완제품 외부 서비스**이고,
우리 코드는 호스트 자원(git·CLI 인증·Gitea 훅·LAN·홈)에 붙는 **자체 코드**다.
되돌리기 어려운 결정도 아니다(유닛을 나중에 컨테이너화 가능). 상세 = 마스터 리포트 06 §1.

#### 5.4.5 🔴 폴링이 공짜로 주던 3가지 — 웹훅으로 가면 직접 만들어야 한다

**기존 코드가 폴링 루프 자체를 안전장치로 쓰고 있다.** 그대로 이식하면 이벤트가 조용히 유실된다.

```python
# watcher/watch.py:646
if not _processing_lock.acquire(blocking=False):
    # 이전 사이클이 아직 처리 중 → 이번 틱은 건너뜀
```

폴링에서 **건너뛰는 건 안전하다** — 60초 뒤 다음 틱이 어차피 다시 본다.
웹훅에서 건너뛰면 **그 이벤트는 영영 사라진다.** 아무도 다시 알려주지 않는다.

| 성질 | 폴링에서 | 웹훅에서 | 대책 |
|---|---|---|---|
| **직렬화** | `_processing_lock` 으로 한 번에 한 사이클 | 동시 도착 시 겹침 | 단일 소비자 |
| **재시도** | 놓친 틱은 다음 틱이 처리 | 놓치면 유실 | **영속 큐** |
| **합치기** | 60초 안의 push 10개 = 재색인 1회 | push 10개 = 재색인 10회 | 중복 합치기(coalescing) |

세 번째가 특히 아프다 — 커밋을 연달아 밀면 무거운 RAG 재색인이 그 횟수만큼 돈다.

**→ 웹훅 전환의 전제조건은 영속 큐 + 단일 소비자다. 선택이 아니다.**
`post-receive` 훅은 큐에 넣고 즉시 종료한다(§5.4.2 의 "push 를 막지 말 것"과 같은 요구).

> **⚠️ 오케스트레이터가 셋이라 더 중요해졌다 (2026-08-08 갱신, 이전엔 "둘"로 적었다).**
> 윈도우 UE5 PC **2대**의 Claude Code 와 마스터가 **동시에** git·task_queue·RAG 를 건드리고,
> **두 작업장은 같은 UE5 프로젝트를 본다**(§4.2). 폴링 시절의 "이번 틱 건너뜀"이 안전했던 이유
> (다음 틱이 처리)가 사라지는 데다, 이제는 **세 주체가 경쟁**한다. 1인 프로젝트라고
> claim/fencing 을 걷어내면 안 되는 이유이기도 하다(§2.2-5 · §5.2-D).
> 실제로 도는 것을 확인했다 — 이중 claim 차단·stale epoch 거부(§9.5.3).

**⚠️ `task_queue` 와 합치지 말 것** — 성격이 다르다.

| | `task_queue` (기존) | 이벤트 큐 (신규) |
|---|---|---|
| 소비자 | 다수 (윈도우 작업자들) | **정확히 하나** (마스터 내부) |
| 필요한 것 | claim · lease · fencing · reclaim | 순서 보장 · 중복 합치기 |
| 현재 상태 | `idx.lock`(RLock)으로 촘촘히 보호됨 | 없음 |

`task_queue` 의 claim/lease 는 "외부 소비자 여럿이 경쟁한다"는 전제로 만든 물건이라
로컬 단일 소비자에는 과하다.

**원형으로 쓸 것이 이미 있다** — `.claude/_regenerate_queue.jsonl`.
`skill_defs_ontology.py:97` 이 "실제 LLM 재생성은 다음 폴링 사이클(최대 60초)에서 자동 수행"이라
적어둔 그 파일 큐다. 여기서도 폴링 사이클이 실행기 노릇을 하고 있다.

#### 5.4.5-a ✅ 이벤트 큐 설계 확정 (2026-08-08)

§5.4.5 가 요구한 세 가지(영속 · 단일 소비자 · 중복 합치기)를 어떻게 만들지 확정한다.

##### ① 저장 형태 — jsonl 이 아니라 **디렉토리 스풀**(파일 하나 = 이벤트 하나)

원형(`.claude/_regenerate_queue.jsonl`)은 append-only 파일이었다. **그대로 쓰지 않는다.**

append 방식은 소비 시점에 경합이 생긴다: 소비자가 파일을 통째로 가져가려고 rename 하는
순간, **이미 그 파일을 열고 있던 생산자가 rename 된 파일에 계속 쓴다.** 소비자는 이미
읽은 뒤라 그 이벤트를 놓친다. 창이 좁을 뿐 유실이고, **웹훅에서 유실은 영구다**(§5.4.5).

→ **파일 하나에 이벤트 하나.** 생산자는 임시 파일에 쓰고 `rename` 한다(같은 파일시스템에서
원자적). 소비자는 디렉토리를 나열해 처리하고 지운다. **락도 offset 도 필요 없고, 경합 창이
아예 없다.**

```
~/ax-spool/                       ← 🔴 git 저장소가 아니다. ax-state 에 두지 않는다
    incoming/   <ts>-<rand>.json    생산자(Gitea 훅)가 rename 으로 넣는다
    tmp/        …                   rename 전 임시 파일. 같은 FS 여야 원자적이다
    claimed/    <batch>/…           소비자가 통째로 옮겨 놓고 처리 중인 것
    rejected/   …                   검증 실패. **지우지 않는다** — 감사용
```

🔴 **`~/ax-state` 에 두지 않는 이유**: 그쪽은 상태 전이마다 **감사 커밋이 도는 git 저장소**다
(§9.5.2). 이벤트 스풀을 넣으면 push 한 번에 커밋이 쌓이고, 무엇보다 **스풀은 지워지는
것이 정상**인데 git 이력에는 영원히 남는다.

##### ② 단일 소비자 — `flock` 으로 강제한다

"하나만 돈다" 를 규약으로만 두면 언젠가 둘이 돈다. 소비자는 `~/ax-spool/consumer.lock` 을
**비차단 `flock`** 으로 잡고, 실패하면 **조용히 종료**한다(에러가 아니다 — 이미 돌고 있다는
뜻이다). 프로세스가 죽으면 커널이 락을 놓으므로 스테일 락이 남지 않는다.

##### ③ 합치기 — 키는 `project_id`, **머지가 아니라 최신 하나만 남긴다**

§5.5.3-⑤ 대로 키는 `project_id` 다. 배치 안에서 같은 프로젝트의 이벤트가 N 개면 **가장 최근
것 하나만 남기고 나머지는 버린다.**

🔴 **버려도 되는 이유는 워터마크가 커밋 해시이기 때문이다**(§5.5.3-c).
색인기는 "이 이벤트를 처리" 하는 게 아니라 **`last_indexed_commit` → 현재 HEAD 를 따라잡는다.**
중간 커밋을 개별로 알 필요가 없다. 워터마크가 타임스탬프였다면 이 합치기는 안전하지 않다 —
**두 결정이 서로를 떠받친다.**

버린 이벤트도 개수는 센다(`coalesced_away`). 무거운 재색인이 몇 번 절약됐는지가
이 큐의 존재 이유이므로, 그 수치가 안 보이면 효과를 알 수 없다.

##### ④ 직렬화도 `project_id` 단위 — 전역 락을 걸지 않는다

§5.5.3-⑤: 전역으로 만들면 프로젝트 A 의 재색인이 B 를 통째로 막는다. 소비자는 하나지만
**프로젝트별로 순서만 지키면 되고**, 서로 다른 프로젝트는 순서를 지킬 이유가 없다.
지금은 프로젝트가 1개라 차이가 없지만 **디스크에 쌓이는 형태**(합치기 키)를 지금 정해 두면
나중에 코드만 바꾸면 된다 — §5.5.2 와 같은 비대칭이다.

##### ⑤ 검증 — fail-closed, 그리고 **버리지 않는다**

| 검사 | 실패 시 |
|---|---|
| `project_id` 가 있는가 | `rejected/` (§5.5.3-⑤: 소급 불가) |
| 등록된 프로젝트인가 (`Registry.find_by_project_id`, **casefold**) | `rejected/` (§5.5.4-④) |
| JSON 이 깨지지 않았는가 | `rejected/` |

🔴 **거부한 이벤트를 지우지 않는다.** 조용히 사라지면 "훅이 안 오네" 와
"오는데 거부되네" 를 구분할 수 없다. 이 세션에서 대소문자 불일치 하나로 **모든 이벤트가
409 로 조용히 거부될 뻔한 것**(§5.5.4-④)이 바로 그 시나리오다.

##### ⑥ 재귀 차단 — 소비자에서 이중으로 (§5.5.3-d)

1. **추적 대상 저장소가 아니면 무시** — ⑤ 의 `project_id` 검증이 그대로 이 역할을 한다.
2. **`[ax-index]` 트레일러가 붙은 커밋만 있는 push 는 스킵** — 색인기가 만든 커밋이
   되돌아온 경우다. 현재 구조상 고리는 끊겨 있지만(§5.5.3-d), **끊겨 있음에 의존하지 않는다.**

##### ⑦ 훅은 넣고 즉시 끝난다

`post-receive` 는 **파일 하나 쓰고 종료**한다. 색인기를 부르지 않는다 — §5.4.2 의
"push 를 막지 말 것" 이고, 훅이 오래 걸리면 사용자의 `git push` 가 그만큼 멈춘다.

```sh
# post-receive.d/ax-enqueue  (§5.4.2-a — hooks/post-receive 를 직접 고치지 말 것)
while read old new ref; do
  printf '{"project_id":"%s","ref":"%s","old":"%s","new":"%s","at":"%s"}\n' \
    "$AX_PROJECT_ID" "$ref" "$old" "$new" "$(date -Is)" \
    > "$SPOOL/tmp/$$-$RANDOM.json"
  mv "$SPOOL/tmp/$$-$RANDOM.json" "$SPOOL/incoming/$(date +%s%N)-$$.json"
done
```

##### ⑧ 전달 보장 — at-least-once, 멱등으로 받는다

크래시하면 `claimed/<batch>/` 가 남는다. 소비자는 기동 시 **남은 배치를 먼저 다시 처리**한다.
따라서 **같은 이벤트가 두 번 처리될 수 있다.** exactly-once 를 만들지 않는 이유는
그럴 필요가 없기 때문이다 — 색인은 워터마크 기준 따라잡기라 **멱등**이다(③ 과 같은 근거).

##### 무엇을 만들었고 무엇을 안 만들었나

✅ **큐 자체**(`master/events/`) — enqueue · claim · coalesce · reject · 재기동 복구.
❌ **소비자(색인기)** — **의도적으로 안 만들었다.** 무엇을 색인할지가 미결이다
(§3 "RAG 이식 범위 결정": 검색 코어만 vs 온톨로지까지). 큐는 그 결정과 무관하게 필요하고
지금 만들 수 있으므로 분리했다. 소비자는 `claim_batch()` 를 호출해 배치를 받아 가면 된다.
❌ **Gitea 훅 설치** — 위 스크립트는 형태만 확정했다. 설치는 §5.4.2-a 의 `post-receive.d/`
지점에 root 로 넣어야 하고, 그때 `AX_PROJECT_ID` 를 저장소별로 박아야 한다.

#### 5.4.6 읽기/쓰기 충돌은 이미 해결돼 있다 — 더블 버퍼

**클라이언트 요청(읽기)과 인덱스 갱신(쓰기)을 한 줄로 세울 필요는 없다.**
`mcp/context_search/double_buffered_index.py` 가 이미 원자적 교체를 한다.

| 메서드 | 동작 |
|---|---|
| `begin_update(fresh=False)` | `_write_lock` 획득 후 Live→Work 복사. **임베딩까지 복사해 재계산 없음** |
| `commit_update()` | `_swap_lock` 안에서 Live↔Work 교체 + **태그 캐시 동시 교체** |
| `rollback_update()` | 실패 시 **Live 무영향** |
| `live` / `tag_cache` | 검색은 항상 Live 에서 즉시 응답 — **블로킹 없음** |

ChromaDB 컬렉션 `context_a` / `context_b` 를 번갈아 쓴다. 즉 재색인이 도는 동안에도
개발자는 기다리지 않고, **반쯤 갱신된 인덱스를 보는 일도 없다.**

**또 하나 이미 있는 조율** — `watch_state._has_active_distribute_work()`:
작업자에게 `in_progress` 작업이 있으면 **watcher 메인 루프가 일시 중지**한다.
docstring 이 밝힌 이유 두 가지: ① feature 브랜치 작업 중 main 인덱싱은 무의미
② **워커들과 git lock 경쟁 방지**. 즉 "클라이언트 작업이 진행 중이면 인덱스 갱신이 양보"가
이미 설계돼 있다. 이 게이트는 이식하되, "이번 틱 건너뜀"이 아니라 **큐에서 대기**로 바꿔야 한다(§5.4.5).

**⚠️ 단 더블 버퍼가 전부를 덮지는 않는다 — 확인할 것 3가지**

1. **BM25 는 더블 버퍼가 아니다.** `commit_update()` 주석: `# BM25 는 디스크 영속 + in-place 증분 — swap 불필요`.
   벡터 컬렉션과 태그 캐시는 원자적으로 교체되지만 BM25(SQLite FTS5)는 제자리 갱신이다.
   `_apply_bm25_incremental()` 도중 동시 검색이 **부분 갱신된 BM25 + 옛 Live 벡터**를 함께 볼 수 있다.
   실사용에서 문제가 되는지 **확인 후 판단할 것**(추측 금지).
2. **더블 버퍼는 인덱스 내부 일관성만 푼다.** §5.4.5 의 이벤트 유실은 그대로 남는다.
   `begin_update()` 의 `_write_lock.acquire()` 는 **블로킹**이라 겹친 갱신은 유실 대신 대기하지만,
   그 대기가 웹훅 HTTP 커넥션을 잡고 있으면 안 된다 — 큐가 여전히 필요한 이유.
3. **서버 모드 전용 기능이다.** docstring 이 "서버 모드에서 무중단 벡터 인덱싱"이라 명시한다.
   마스터가 쓸 모드가 정확히 그 모드다 — 유리한 조건이다.

#### 5.4.7 ✅ 기존 "서버 모드"와의 중복도 판정 완료 (2026-08-07)

AgentTest 는 이미 **서버/클라이언트 모드**를 갖고 있다(`CLAUDE.md`):
*"공용 서버 1대에서 Git 감시 + RAG 중앙 관리, 팀원 PC 의 Claude Code 는 HTTP 로 RAG 검색"*.
`docs/rag-system.md`·`docs/runbook.md` §11 정독 + 코드 실측으로 판정했다.

**결과가 계층별로 깨끗하게 갈린다:**

| 계층 | 판정 | 근거 (실측) |
|---|---|---|
| **RAG/온톨로지 서비스** (`context_search --serve`) | **거의 "리눅스에서 서버 모드 구동"** | `mcp/context_search/` 에 `sys.platform` 분기 **0건**. FastAPI+uvicorn+ChromaDB 전부 크로스플랫폼 |
| **`task_queue`** | **거의 그대로 이식** | 이미 독립 FastAPI/uvicorn 서비스. `sys.platform` 2건(`reclaim.py`·`persistence.py`)인데 **둘 다 `creationflags=... if win32 else 0` 으로 리눅스 분기가 이미 있음** |
| **`watcher/` git 감시** | **재설계** | 폴링→Gitea 이벤트(§5.4.2), `process_lifecycle`·`network_firewall` 폐기(§5.4.3) |
| **BC-250 추론 브로커** | **신규 작성** | 서버 모드에 존재하지 않음 (§6.4) |

**⚠️ "서버 모드 = 중앙 오케스트레이션"이 아니다.** `--serve` 는 **RAG 전용**이고
`http_server.py` 에 git 관련 코드가 한 줄도 없다. 실제 구조는:

```
watch.exe (서버 PC 에서 폴링) → 컨텍스트 MD 생성 → context_search --upsert → ChromaDB
context_search --serve (FastAPI) ← 팀원 PC 들이 HTTP 로 검색
```

**이미 중앙화된 것은 RAG/온톨로지 조회뿐이고 git 감시는 여전히 서버 PC 의 `watch.exe` 폴링이다.**
따라서 우리가 새로 만들 것(Gitea 이벤트 구동·추론 브로커)은 그대로 남는다.

**그대로 쓸 수 있는 자산** — `--serve` 의 HTTP 엔드포인트 30여 종:
검색(`combined`/`vector`/`tags`) · 인덱스(`upsert`/`rebuild`/`status`) · 도메인 CRUD ·
온톨로지 조회 9종 · `health`. 모드 전환도 **config 키(`server_mode`/`context_server_url`)만으로**
되도록 설계돼 있어 코드 변경이 필요 없다.

**인프라 이전 절차도 이미 문서화돼 있다** (`docs/runbook.md` §11):
`--export-state` / `--import-state` 로 **`.claude/context/`(컨텍스트 MD)와
`.claude/ontology/domains/`(온톨로지 YAML) 두 개만** 옮기면 된다.
`vector_db`·BM25·`class_graph.db`·`dependency_graph.db` 는 전부 파생 자산이라 재기동 시 자동 복구.
단 그 절차는 **"새 컴퓨터에 `AgentWatch.zip` 설치"를 전제**하므로 리눅스에선
`python -m context_search --serve` 로 대체하고, self-heal 트리거인 `watch.exe` 재기동은
포팅된 watcher 또는 `POST /api/v1/index/rebuild` 직접 호출로 대체해야 한다.

**→ 소비 쪽(대 2)은 그대로 쓸 수 있는 자산이 많아 싸다. 🔴 진짜 작업은 `watcher/` 쪽 —
데이터를 만드는 대 1 에 몰려 있고, 그것이 이번 마일스톤의 메인이다** (§5.2-E ②).

---

### 5.5 프로젝트 격리 — 다중 디렉토리 · 단일 마운트

→ Split out for size: [`5_5-project-isolation.md`](5_5-project-isolation.md)
