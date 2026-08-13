# AX Cluster

집의 여러 컴퓨터를 묶어 **UE5 프로젝트의 디지털 트윈을 만들고, 그 트윈으로 코드 작성을
돕는** 오케스트레이션 저장소.

**플랫폼**: 리눅스 마스터(Ubuntu 22.04) + 윈도우 2대(작업장 1 · 요청자 1) + BC-250 1대

> **지금 어디까지 왔나** (2026-08-10): **마일스톤 2 닫힘 — 트윈이 자라고, 색인되고, 코드
> 작성에 전달된다.** 두 목표 모두 끝까지 관통했다. **마일스톤 3(실작업 파이프라인) 착수** —
> 큰 작업을 **분해·골조 생성**(§4.5 의 빈 첫 칸)으로 쪼개 워커 2대가 동시에 짜고, 순차 적용한
> 뒤 **3층 결정적 게이트**로 판정한다.
> 🔴 **분자는 여기 적지 않는다** — 레드마인(version *마일스톤 3*)이 계산한다.
>
> 이 README 는 **구조 + 기능 + 사용법**만 다룬다. 설계 결정·진화 로그는
> [`PLAN.md`](PLAN.md) → [`docs/`](docs/) 가 SSOT 이고, **지금 어디까지 왔는지**는
> [`docs/milestones/`](docs/milestones/) 의 **열린 마일스톤 하나**만 읽으면 된다.
> 세션 기록은 [`reports/`](reports/), 머신별 운영 규칙은 [`machines/`](machines/).

---

## 개요

목표는 둘이다.

1. **온톨로지 문서를 자동으로 작성한다** — 커밋마다 컨텍스트 문서를 쓰고, 연관 클래스 간
   관계를 그래프로 쓰고, 검색을 위해 BM25 를 얹고, 최종적으로 사용자의 수동 명령과
   대화형으로 휴리스틱이 포함된 온톨로지 문서를 만든다
2. **그 트윈 데이터를 코드 작성 에이전트에게** 관련된 것만 추출해 전달한다

```
[트윈이 자라는 길 — 커밋 이벤트 구동]
Gitea push → post-receive 훅 → 스풀 → inotify → 색인기
                              → 관계 그래프 증분 (tree-sitter, LLM 0)
                              → 변경분 컨텍스트 MD 합성 (로컬 LLM)
                                 · σ.7 펜스 제거 + 저장 전 형식 게이트
                                 · 🔴 사실 게이트 — 주석에만 있는 식별자 주장은 거부
                              → 벡터(다국어) + BM25 재색인, A/B 세대 무중단 교체

[트윈을 쓰는 길 — 작업 요청]  ⚠️ 아래는 **지금 도는 것**(M3 가 만든 모양). 원전의 모양은 그 밑에
요청자(.33) → search_context → "이런 기능이 필요하다" → register_work + durable `task/<id>`
마스터      → 🔴 골조 생성(claude:opus) — 관계 그래프·헤더 선언·규범·휴리스틱으로 grounding
           → 골조가 되묻는다 → 🔴 **사람이 답한다** → 인터페이스 동결(결정적)
           → 🔴 골조 빌드 게이트: 통합자 `.2` 에서 세워 보고 **통과해야 등재**
           → 분해(의존 순서·파일 불가분) → 매니페스트 배달(포팅이면 원본 경로도)
워커        → durable 을 읽고 **추론만** (`ax-infer`) → `response.txt` 로 답한다 (커밋 없음)
마스터      → 응답을 되읽어 fail-closed 판정 → **스풀**(적용 순서대로 · 기준 커밋과 함께)
통합자(.2)  → 층1 → **층2**(선언부 grounding) → 적용 → **조각마다 UE5 빌드** → 통과분만 커밋
           → **work 단위 RunTests** → push (ff-only). ⚠️ 테스트 0개라 RunTests 는 fail-open
```

🔴 **위 그림의 「통합자만 커밋한다」는 절반만 맞다 — 원전에 이미 답이 있었다**(2026-08-13 발견).
`~/AgentTest/mcp/task_queue/cluster_coordinator.py`(200줄, 우리 저장소에서 **인용 0회**)의
`verify_and_merge` 주석이 *"durable 단일 writer 보존"* 이다. 즉 **「쓰는 주체 하나」는 내 발명이
아니고, 그 하나는 통합자가 아니라 서버다.** 원전의 모양은 **2단 브랜치**다:

```
durable  task/<id>                                    ← 🔴 **서버만** 쓴다 (verify_and_merge)
ephemeral attempt/<id>/<workshop>/<ts>                ← 작업장이 자유롭게 push (force 허용)
                                                        epoch 이 낡으면 병합 거부(좀비 차단)
```

🔴 **리눅스가 강제하는 변경은 정확히 하나다** — `verify_and_merge` 안의 **UE5 빌드 단계가 `.2` 로
간다.** 그 밖에 M3 에서 바꾼 것은 포팅이 아니라 재설계였다. 복구 상태: `work/coordinator.py`
이식 완료 + 실 Gitea·실 작업장·실 `claude` 로 실증(리포트 14 §14~§15), ⚠️ **아직 라이브
파이프라인에 배선되지 않았다** — 그래서 위 그림이 지금은 여전히 맞다. 남은 것 = 마일스톤 4.

분산이 주는 것은 처리량이 아니라 **증분**이다 — 실측상 워커 2대는 12% 빠르고 90% 비쌌고,
값은 *"작업이 항상 컴파일되는 상태로 쌓인다"* 는 데 있다(§4.5). 🔴 그 값은 위 두 모양 **어느
쪽에서도 같다** — 증분을 지키는 것은 브랜치 토폴로지가 아니라 **게이트**이기 때문이다.

🔴 **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(실측: 워커는 8101 에 401). 하트비트도
마스터가 대신 친다. 요청자→워커 한 바퀴 **1분 29초** 실측.

추론은 **마스터 브로커(8102)** 를 거쳐 노드로 간다 — 컨텍스트 합성은 `gemma4:e4b`,
코드 생성은 `qwen2.5-coder:14b`. 모델별 적합도·환각 실측은
[`machines/llm-fitness.md`](machines/llm-fitness.md).

🔴 **문서는 지도지 정답이 아니다.** 모든 문서는 **소스코드라는 원천**을 바탕으로 찾고
이해하기 쉽게 하는 네비게이션이다. 판단 기준은 *"맞는 자리를 찾을 수 있나"* 이지
*"증명되게 옳은가"* 가 아니다 — 근사는 허용하되, **없는 것을 있다고 하면 틀린 자리로
보내므로** 사실 게이트는 둔다.

🔴 **마스터는 인프라지 작업장이 아니다.** 파일 I/O·빌드·테스트는 파일을 소유한 윈도우에서
하고, 마스터는 컨텍스트를 조립해 건넨다. 노드는 **텍스트만** 주고받는다.

---

## 저장소 구조

```
ax-cluster/
├── master/                     ← 마스터가 돌리는 것 전부 (Python, systemd + venv)
│   ├── context_search/         ← 검색 코어 — 벡터(다국어)·BM25(+trigram)·RRF 융합
│   │   ├── index.py            벡터. A/B 더블버퍼, 임베딩 모델 교체 시 컬렉션 재생성
│   │   ├── bm25.py             FTS5. 단어 테이블 + 한글 trigram 테이블
│   │   ├── embedding.py        다국어 384차원(fastembed/ONNX, PyTorch 불필요)
│   │   ├── search.py           RRF 융합 + `[대괄호]` 포커스
│   │   ├── thesaurus.py        별칭표 — 조회·후보 제시·대화형 등록
│   │   ├── expand.py           질의 확장 — 🔴 부분 문자열(한국어 조사) · 짧은 별칭 차단
│   │   ├── infer.py            질의 → 도메인 **결정적** 추론 — 🔴 모르면 비운다
│   │   ├── documents.py        컨텍스트 MD 파싱. 벡터는 「## 요약」 절만 임베딩
│   │   ├── generation.py       A/B 세대 포인터(영속) — 프로세스가 갈려 있어 필요
│   │   └── paths.py            🔴 경로는 상수가 아니라 함수 — 마운트 전환에 재기동 불필요
│   ├── context_synth/          ← 컨텍스트 MD 합성 (중 1.2)
│   │   ├── prompt.py           프롬프트 + grounding 3채널(관련문서 3·도메인 1·관계그래프)
│   │   ├── md.py               σ.7 펜스 제거 · 저장 전 게이트 · content_hash/source_commit
│   │   ├── verify.py           🔴 사실 게이트 — 주석에만 있는 식별자를 결정적으로 적발
│   │   └── synth.py            배치·서킷브레이커·모델 회수
│   ├── ontology/               ← 온톨로지 문서 (중 1.3) — PyYAML 의존 0
│   │   ├── yaml_io.py          우리가 쓴 것만 우리가 읽는다. 안 바뀌면 안 쓴다
│   │   ├── stale.py            워터마크 2개 비교 — 어느 도메인을 재합성할지
│   │   ├── layers.py           L1/L2/L3 추정 — 구조 우선, git 은 강등만
│   │   ├── collect.py          멤버 후보 **제안** — 조상·자식·include 이웃
│   │   ├── hierarchy.py        개념 계층 — 하위 문서를 object 로, 순환 방지
│   │   ├── verify_facts.py     🔴 온톨로지 사실 게이트 — 호출 관계를 실측과 대조
│   │   ├── package.py          패키지 쓰기 — 🔴 검수 잠금은 덮지 않는다
│   │   ├── edit.py             편집이 곧 잠금 · 일괄 보호(`protected`) — 재생성이 못 덮는다
│   │   ├── drift.py            드리프트 감사 — 커밋 차이가 아니라 **근거 파일 변경**으로 좁힌다
│   │   └── view.py             🔴 자립형 HTML 뷰어 한 장 — 서비스를 또 띄우지 않는다
│   ├── graph/                  ← 관계 그래프 (중 1.1, LLM 0)
│   │   ├── parse.py            tree-sitter C++ · UE 매크로 전처리
│   │   ├── class_graph.py      상속 그래프 + methods 소유권
│   │   └── dependency.py       `#include` 의존 그래프
│   ├── events/                 ← Gitea 훅 → 스풀 → 색인기 (트윈이 자라는 지점)
│   │   └── gate.py             🔴 **색인 일시정지 게이트** — 작업 중이면 색인을 미룬다(실측: 셀프
│   │                              테스트의 push 가 색인기를 15번 깨웠고 14번은 할 일이 없었다).
│   │                              ⚠️ 조건은 `in_progress` **하나뿐**(원전 Phase 2) · 모르면 진행
│   ├── work/                   ← 작업 루프 — 골조·분해·**추론 파견**·검증
│   │   ├── coordinator.py      🔴 **2단 브랜치 조율 (원전 이식)** — durable 은 **서버만** 쓴다.
│   │   │                          `assign_attempt`(git 접촉 0) · `push_attempt`(ephemeral, force 허용)
│   │   │                          · `verify_and_merge`(**epoch 펜싱** — 낡은 좀비는 병합 거부)
│   │   │                          · `cleanup_attempts`(🔴 **기본은 세기만** — 잔재는 증거다)
│   │   ├── selftest.py         🔴 **실증 하네스** — `dry`(임시 저장소) / `live`(실 Gitea·실 작업장).
│   │   │                          매니페스트에만 심은 NONCE 가 durable 산출물에 나타나면
│   │   │                          **git 으로 실린 컨텍스트가 실제로 읽혔다**는 증명이 된다
│   │   ├── conventions.py      🔴 UE 금지사항(개명·상속변경·모듈이동 — 블루프린트 에셋이 깨진다) +
│   │   │                          `repo/CLAUDE.md § Code conventions` 를 **읽어** 매니페스트에 싣는다
│   │   ├── skeleton.py         🔴 골조 생성 + **인터페이스 동결**(결정적, LLM 0). 텍스트만 낸다
│   │   ├── skeleton_gate.py    🔴 **등재 전에 세워 본다** — 빌드 통과해야 등재
│   │   ├── decompose.py        분해 — 의존 순서·파일 불가분·`[PSEUDO:N]` 뎁스
│   │   ├── heuristics.py       🔴 대화형 휴리스틱 — **사람이 답한 것만**, 범위(project/domain/once)
│   │   ├── infer.py            🔴 **추론 파견** — 워커는 커밋 안 한다. 응답은 **파일로** 온다
│   │   ├── layer1.py           🔴 **층1** — 동결·잔재·`[FEEDBACK]`. 수락·적용 **양쪽**에서 돈다
│   │   ├── integrate.py        🔴 **통합자** — 층1→층2→적용→빌드→커밋. 실패는 되돌린다
│   │   ├── failures.py         실패 카탈로그 — 판정 원문을 다음 골조로 되먹인다
│   │   ├── porting.py          포팅 원본 대응 — 🔴 경로만·읽기 전용. 실측 동명 9 → 정규화 21쌍
│   │   ├── distribute.py       `/distribute` 입구 — 🔴 plan→register→dispatch, 단계마다 사람이 끊는다
│   │   ├── runner.py           ⚠️ **구 토폴로지**(워커가 커밋) — 되돌릴 수 있게 남겨 둔다
│   │   ├── batching.py         🔴 파일 불가분 묶음 — 열쇠는 **모듈+경로+stem**(basename 아님)
│   │   ├── declarations.py     헤더 선언 주입 — 실측 환각 2 → 0
│   │   ├── norms.py            도메인 규범(invariants 중심) 부착
│   │   └── cleanup.py          찌꺼기 정리 — 🔴 병합된 것만, 원격은 안 건드린다
│   ├── transfer.py             상태 익스포트/임포트 — 🔴 두 벌(compat·full) · 임포트는 **병합**
│   ├── broker/                 ← 추론 브로커 (Ollama 호환, 노드 라우팅·핀 유지)
│   ├── task_queue/             ← 작업 큐 (claim·lease·epoch fencing·능력 라우팅)
│   ├── projects/               ← 프로젝트 레지스트리 + **작업장의 MCP 단일 창구**
│   ├── status.py               클러스터 상태 수집·렌더 — 🔴 읽기 전용·주기 가드 120초
│   ├── viewer.py               ⚠️ 옛 `/view` (→ `/cluster` 302). 서빙은 `webui/` 가 한다
│   ├── webui/                  🔴 **원전 웹 UI 복각** — Context Server·온톨로지 뷰어·게시판
│   ├── source_text.py          🔴 CP949 대응 — 소스의 44%가 CP949 다
│   ├── sqlite_util.py          🔴 **동시 접근 공통 설정** — `busy_timeout` 10초·WAL. 색인기와
│   │                              검색이 같은 DB 를 만지므로 이걸 안 걸면 `database is locked`
│   ├── sigma_audit.py          🔴 **조용한 실패 스캐너 (원전 σ 감사 이식)** — 넓은 핸들러 +
│   │                              의도가 안 적힌 것을 찾는다. ⚠️ **판정은 사람이 한다**
│   ├── auth.py                 3서비스 공용 베어러 인증 (fail-closed)
│   ├── verdict.py              층2 판정 계약 (fail-closed)
│   └── layer3_verify.py        층3 게이트 — UE5 빌드·RunTests 로그
├── <프로젝트명>/               ← 디지털 트윈 데이터 (gitignore)
│   ├── context/  ontology/     원본 — 합성 산출물 (도메인 색인 대상)
│   ├── repo/                   소스 클론. 🔴 색인 대상은 `Source/` 뿐
│   └── vector_db/ bm25.db …    파생 — 재색인으로 복구된다
├── docs/                       ← 설계 결정 (§ 번호가 커밋에 박혀 있다)
│   └── milestones/             ← 진행 상태. **열린 것 하나만 읽는다**
├── machines/                   ← 머신별 운영 규칙 + LLM 적합도 실측
├── reports/                    ← 세션별 결정·실측·함정 기록
├── client/                     ← 워커 번들: 머신별 config·스킬·CLAUDE.md 배달
├── worker/                     ← 아직 README 스텁 (BC-250 추론 노드 쪽)
└── PLAN.md                     ← docs/ 색인
```

---

## 가동 중인 서비스

| 서비스 | 포트 | 유닛 |
|---|---|---|
| 작업 큐 | 8101 | `ax-task-queue.service` |
| 추론 브로커 | 8102 | `ax-broker.service` |
| 프로젝트 레지스트리 (MCP) + **웹 UI** | 8103 | `ax-projects.service` (`/`·`/ontology`·`/cluster`) |
| 색인기 | — | `ax-indexer.path`(inotify) → `ax-indexer.service` |

🔴 셋 다 **베어러 토큰 필수**(`~/.config/ax-cluster/token`, 0600) — 토큰이 없으면 **서비스가
뜨지 않는다**(fail-closed). 방화벽 LAN 한정은 **별개의 두 번째 층**이다. `Anywhere` 로 넓히지 말 것.

---

## 사용법

```bash
# 트윈 만들기 — 관계 그래프 (LLM 0, 1,654 파일 ≈ 2.9초)
.venv/bin/python -m master.graph build            # 상속 + #include
.venv/bin/python -m master.graph status

# 트윈 만들기 — 컨텍스트 MD 합성
.venv/bin/python -m master.context_synth status   # 소스 그룹 vs 문서 대비
.venv/bin/python -m master.context_synth sample 4 # 🔴 dry-run — 스냅샷을 안 건드리고 통과율만
.venv/bin/python -m master.context_synth fill     # 문서 없는 그룹만 보충

# 색인
.venv/bin/python -m master.context_search.rebuild # 전체 재색인 (A/B 한 번 교체)

# 온톨로지 — 🔴 이 순서로 (plan 은 아무것도 안 바꾼다)
.venv/bin/python -m master.ontology plan|dry|refresh
.venv/bin/python -m master.ontology drift          # 트윈과 소스가 어긋난 곳
.venv/bin/python -m master.ontology view           # 자립형 HTML 한 장

# 상태 주고받기
.venv/bin/python -m master.transfer export         # 두 벌(full·compat) + README
.venv/bin/python -m master.transfer import <zip>   # 🔴 기본은 계획만 · --apply 는 먼저 백업

# 분산 작업 (마일스톤 3 대 1) — 🔴 단계마다 사람이 끊는다. 스킬: /distribute
.venv/bin/python -m master.work.distribute plan     <프로젝트> <슬러그> <클래스:파일…>
#   → 계획 JSON 이 나온다. 🔴 **사람이 그 파일에서 조각을 지운다** (눈으로는 자를 수 없다)
.venv/bin/python -m master.work.distribute register <프로젝트> <슬러그> "<제목>" <저장소>
#   → 골조는 claude:opus 로 만들고(계약이라 값을 쓴다), 통합자 `.2` 에서 세워 본 뒤 등재한다
.venv/bin/python -m master.work.distribute dispatch <프로젝트> <work_id> 4
.venv/bin/python -m master.work.porting  pairs      # 포팅 원본↔대상 대응 (실측 9 → 정규화 21쌍)

# 워커에 일 시키기
.venv/bin/python -m master.client probe            # 머신 실측 — 경로·능력·체크아웃
.venv/bin/python -m master.client deliver          # config·스킬·CLAUDE.md 배달 (해시 대조)
.venv/bin/python -m master.work.infer probe        # 누가 추론을 받을 수 있나 (큐 무접촉)
.venv/bin/python -m master.work.infer run          # 🔴 추론 파견 (직렬 기본) — 커밋하지 않는다
.venv/bin/python -m master.work.infer spool <work> # 응답 스풀 — 어디까지 진행됐나
.venv/bin/python -m master.work.integrate plan <프로젝트> <work>   # 🔴 먼저 본다 (안 쓴다)
.venv/bin/python -m master.work.integrate run  <프로젝트> <work> [durable]
.venv/bin/python -m master.work.runner once        # ⚠️ 구 토폴로지: 워커가 커밋한다
.venv/bin/python -m master.work.cleanup plan       # 🔴 먼저 본다 — 아무것도 안 지운다
.venv/bin/python -m master.work.cleanup apply      # 병합된 브랜치·끝난 부산물만 삭제

# 운영
.venv/bin/python -m master.status show                   # 머신·서비스·큐 요약 (읽기 전용)
.venv/bin/python -m master.status html                   # → <프로젝트>/cluster.html 한 장
#   🔴 다른 머신에서 보기: http://192.168.0.57:8103  ← 인증 없음 (원전 웹 UI)
#      / = Context Server · /ontology = 도메인 뷰어+그래프 · /cluster = 클러스터 상태
#   🔴 최소 간격 120초 — BC-250 을 자주 두드리지 않는다 (넘기려면 --force)
curl -s localhost:8102/health | python3 -m json.tool     # 노드별 상주 모델
systemctl status ax-task-queue ax-broker ax-projects ax-indexer.path
journalctl -u ax-indexer -n 30 --no-pager                # push → 트윈 성장 이력
.venv/bin/python -m master.events.install_hook           # Gitea 훅 설치 점검
```

---

## MCP 도구 (작업장 Claude 가 쓰는 창구)

`ax-projects`(8103) 하나가 작업장의 단일 창구다. **26종.**

| 도구 | 하는 일 |
|---|---|
| `search_context` | 🔴 **검색 입구는 이것 하나** — 대괄호 해석 → 시소러스 확장 → 융합 검색 |
| `infer_domain` | 질의가 말하는 도메인을 **결정적으로** 판단 — 🔴 모르면 비운다(추측 안 함) |
| `resolve_terms` · `add_alias` · `mark_not_a_class` | 별칭 조회·등록. 마스터는 묻지 않고 **물을 재료**를 준다 |
| `register_work` · `get_manifest` · `get_code` | 작업 등록 → 매니페스트 수령 → 생성+층2 거친 코드 수령 |
| `create_domain` · `edit_ontology_item` · `remove_ontology_item` | 온톨로지 편집 — 🔴 **편집이 곧 잠금** |
| `lock`·`list_locked` · `protect`·`list_protected` | 사람 검수 잠금 / 🔴 **일괄 보호**(재생성이 못 덮는다) |
| `sync_ontology` · `drift_audit` · `unassigned_classes` | 경로·선언 동기화 · 어긋남 감사 · 미배정 노출 |
| `register_project` · `set_active` · `list_projects` | 트윈 프로젝트 등록·전환 |
| `set_workshop` · `check_workshops_clean` 외 | 작업장 등록·더티 체크 |

**규약**: `[대괄호]`는 **클래스에만** 쓴다. 미등록이면 마스터가 후보를 돌려주고, 작업장
Claude 가 사용자에게 물어 등록한다 — 다음 검색부터 자동 확장된다.

---

## 테스트

**전부 통과. pytest 없음** — 각 파일이 단독 실행된다.

🔴 **여기에 개수를 적지 않는다.** 하루에 여섯 번 고쳤고, 마일스톤 분자를 레드마인으로 옮긴
것과 **같은 이유**다 — 수치가 아니라 **세는 법**을 적는다.

```bash
# 실패만 본다 — 🔴 **판정은 종료코드로** 한다
for f in master/test_*.py; do .venv/bin/python "$f" >/dev/null 2>&1 || echo "🔴 실패 $f"; done
```

🔴 **합계를 세는 명령은 [`CLAUDE.md`](CLAUDE.md) 에 한 벌만 둔다** — 두 곳에 적으면 어긋난다.
그리고 그 명령은 **2026-08-14 에 고쳐졌다**: 옛 `| tail -1` 은 ① 마지막 줄이 구분선인 파일
13개를 못 셌고 ② **크래시한 파일은 수치를 안 찍어 합계가 그대로 보였다** — import 실수로 테스트
파일 3개가 죽었는데 합계가 안 변해서 못 봤다. **세는 도구가 조용히 틀리면 세션 내내 틀린다.**

| 파일 | 무엇을 지키나 |
|---|---|
| `test_verdict.py` | 층2 판정 계약 — 🔴 venv 없이 도는 **순수 로직** |
| `test_work.py` · `test_runner.py` | 작업 루프 · 워커 파견(fail-closed 마커·계측) |
| `test_skeleton.py` | 골조 · 🔴 **동결**(추가는 허용, 변경·삭제는 위반) · 태그 계약 |
| `test_skeleton_gate.py` | 🔴 **fail-closed** — 미확인은 통과가 아니다 |
| `test_decompose.py` | 의존 순서 · 🔴 **묶음(동시) vs 뎁스(순차)** 구분 |
| `test_heuristics.py` | 🔴 사람이 답한 것만 · **범위**(project/domain/once) |
| `test_infer.py` | 🔴 **fail-closed 파견 판정** — 마커+응답파일 둘 다 · 스풀 재사용 · 선행 실패 차단 |
| `test_integrate.py` | 🔴 **실패는 커밋하지 않는다** · 격리는 형제 트리 · push 는 ff-only(force 금지) |
| `test_viewer.py` | 🔴 **자격증명 분리 양방향** · 경로 화이트리스트 · 읽기 전용 · 낡음 배너 |
| `test_status.py` | 🔴 읽기 전용 명령만 · 주기 가드 · 상태는 색만으로 전달하지 않는다 |
| `test_layer1.py` | 🔴 휘발 태그·`[FEEDBACK]` 잔재 · 동결 의미(추가 허용/변경 위반) · fail-closed |
| `test_porting.py` | 🔴 못 찾으면 **붙이지 않는다** · 원본이 대상 목록으로 **새지 않는다** |
| `test_batching.py` | 🔴 **파일 불가분** — `.h`/`.cpp` 는 붙이고 **다른 모듈의 동명 파일은 가른다** |
| `test_ontology.py` | YAML 왕복 보존(PyYAML 의존 0) · 잠금 보존 · 사실 게이트 |
| `test_transfer.py` | 익스포트 두 벌 · 🔴 임포트는 **병합**(보호 필드 이월) |
| `test_context_synth.py` | σ.7 게이트 · 사실 게이트 · 서킷브레이커 |
| `test_context_search.py` | 마운트 라우팅 · RRF · 대괄호 · 시소러스 확장 |
| `test_graph.py` | `Source/` 한정 · fail-closed · 유령 행 방지 |
| `test_indexer.py` | ff-only 미러 · 다이제스트 · 트윈 성장 |
| `test_coordinator.py` | 🔴 **2단 브랜치** — 낡은 epoch 은 **부작용 없이** 거부(durable 안 움직임·좀비 attempt 는 증거로 보존). 🔴 **주입이 아니라 실제 git**(임시 bare + 클론)으로 잰다 |
| `test_selftest.py` | 🔴 매니페스트가 **git 으로만** 도착하는지 · NONCE 왕복 · 잔재 0(로컬 ref 까지) |
| `test_gate.py` | 🔴 일시정지 조건은 `in_progress` **하나뿐** · HTTP 실패 시 디스크 대체 · **모르면 진행** |
| `test_conventions.py` | UE 금지사항 · `repo/CLAUDE.md` 절 추출. ⚠️ **파일 없음은 degraded 가 아니다**(그 파일은 gitignore 대상이라 부재가 정상 — 늘 빨간 게이트는 게이트가 아니다) |
| `test_sigma_audit.py` | 🔴 **좁히는 조건 셋** — 넓은 핸들러만 · 예외를 값으로 돌려주면 조용하지 않다 · 의도는 **주석에서도** 찾는다. 🔴 이 파일이 스캐너의 `bare except` 누락을 **먼저 잡았다** |
| `test_sqlite_util.py` · `test_bm25_diagnose.py` | 동시 접근 설정 적용 · 🔴 검색이 **왜** 0건인지(용어 미일치 vs 색인 비어 있음) |
| 그 외 | 🔴 **위 표는 전부가 아니다** — 목록은 `ls master/test_*.py` 가 답이고, 이 표는 **놓치면 안 되는 계약**만 적는다 |

🔴 **venv 가 필요한 것과 아닌 것이 섞여 있다** — `python3` 로 도는 것은 순수 로직뿐이고,
나머지는 `.venv/bin/python` 이다(pydantic·pyyaml·fastembed).

---

## 세 클론을 동기 상태로 유지할 것

마스터(`sim@192.168.0.57:~/ax-cluster`) · BC-250 #1(`sim@192.168.0.43:~/ax-cluster`) ·
GitHub(**private — 유지할 것.** LAN 주소와 방화벽 규칙이 들어 있다).
보드는 `main` 이 체크아웃돼 있어 **push 가 거부된다 — 그쪽에서는 `git pull`** 을 쓴다.

## 관련

- 전신 프로젝트 — `~/AgentTest` (🔴 **참조 전용. 수정·push 금지**)
- 저장소에서 일할 때의 규칙 — [`CLAUDE.md`](CLAUDE.md)
