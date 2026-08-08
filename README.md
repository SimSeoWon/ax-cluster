# AX Cluster

집의 여러 컴퓨터를 묶어 **UE5 프로젝트의 디지털 트윈을 만들고, 그 트윈으로 코드 작성을
돕는** 오케스트레이션 저장소.

**플랫폼**: 리눅스 마스터(Ubuntu 22.04) + 윈도우 작업장 2대 + BC-250 추론 보드 1대

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

[트윈을 쓰는 길 — 작업 요청]
작업장 Claude → search_context (대괄호 해석 → 시소러스 확장 → 융합 검색)
             → register_work → 매니페스트 수집(1회) → 생성 → 층2 검증 → 코드 인계
             → 작업장이 적용·빌드·층3(UE5 RunTests) → 판정
```

추론은 **마스터 브로커(8102)** 를 거쳐 노드로 간다 — 컨텍스트 합성은 `gemma4:e4b`,
코드 생성은 `qwen2.5-coder:14b`. 모델별 적합도·환각 실측은
[`machines/llm-fitness.md`](machines/llm-fitness.md).

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
│   │   ├── documents.py        컨텍스트 MD 파싱. 벡터는 「## 요약」 절만 임베딩
│   │   ├── generation.py       A/B 세대 포인터(영속) — 프로세스가 갈려 있어 필요
│   │   └── paths.py            🔴 경로는 상수가 아니라 함수 — 마운트 전환에 재기동 불필요
│   ├── context_synth/          ← 컨텍스트 MD 합성 (중 1.2)
│   │   ├── prompt.py           프롬프트 + grounding 3채널(관련문서 3·도메인 1·관계그래프)
│   │   ├── md.py               σ.7 펜스 제거 · 저장 전 게이트 · content_hash/source_commit
│   │   ├── verify.py           🔴 사실 게이트 — 주석에만 있는 식별자를 결정적으로 적발
│   │   └── synth.py            배치·서킷브레이커·모델 회수
│   ├── ontology/               ← 온톨로지 문서 (중 1.3) — PyYAML 의존 0
│   │   └── yaml_io.py          우리가 쓴 것만 우리가 읽는다. 안 바뀌면 안 쓴다
│   ├── graph/                  ← 관계 그래프 (중 1.1, LLM 0)
│   │   ├── parse.py            tree-sitter C++ · UE 매크로 전처리
│   │   ├── class_graph.py      상속 그래프 + methods 소유권
│   │   └── dependency.py       `#include` 의존 그래프
│   ├── events/                 ← Gitea 훅 → 스풀 → 색인기 (트윈이 자라는 지점)
│   ├── work/                   ← 작업 루프 — 2단 브랜치·매니페스트·생성·인계
│   ├── broker/                 ← 추론 브로커 (Ollama 호환, 노드 라우팅·핀 유지)
│   ├── task_queue/             ← 작업 큐 (claim·lease·epoch fencing·능력 라우팅)
│   ├── projects/               ← 프로젝트 레지스트리 + **작업장의 MCP 단일 창구**
│   ├── source_text.py          🔴 CP949 대응 — 소스의 44%가 CP949 다
│   ├── auth.py                 3서비스 공용 베어러 인증 (fail-closed)
│   ├── verdict.py              층2 판정 계약 (fail-closed)
│   └── layer3_verify.py        층3 게이트 — UE5 빌드·RunTests 로그
├── <프로젝트명>/               ← 디지털 트윈 데이터 (gitignore)
│   ├── context/  ontology/     원본 — 합성 산출물
│   ├── repo/                   소스 클론. 🔴 색인 대상은 `Source/` 뿐
│   └── vector_db/ bm25.db …    파생 — 재색인으로 복구된다
├── docs/                       ← 설계 결정 (§ 번호가 커밋에 박혀 있다)
│   └── milestones/             ← 진행 상태. **열린 것 하나만 읽는다**
├── machines/                   ← 머신별 운영 규칙 + LLM 적합도 실측
├── reports/                    ← 세션별 결정·실측·함정 기록
├── worker/  client/            ← 아직 README 스텁
└── PLAN.md                     ← docs/ 색인
```

---

## 가동 중인 서비스

| 서비스 | 포트 | 유닛 |
|---|---|---|
| 작업 큐 | 8101 | `ax-task-queue.service` |
| 추론 브로커 | 8102 | `ax-broker.service` |
| 프로젝트 레지스트리 (MCP) | 8103 | `ax-projects.service` |
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

# 운영
curl -s localhost:8102/health | python3 -m json.tool     # 노드별 상주 모델
systemctl status ax-task-queue ax-broker ax-projects ax-indexer.path
journalctl -u ax-indexer -n 30 --no-pager                # push → 트윈 성장 이력
.venv/bin/python -m master.events.install_hook           # Gitea 훅 설치 점검
```

---

## MCP 도구 (작업장 Claude 가 쓰는 창구)

`ax-projects`(8103) 하나가 작업장의 단일 창구다.

| 도구 | 하는 일 |
|---|---|
| `search_context` | 🔴 **검색 입구는 이것 하나** — 대괄호 해석 → 시소러스 확장 → 융합 검색 |
| `resolve_terms` · `add_alias` · `mark_not_a_class` | 별칭 조회·등록. 마스터는 묻지 않고 **물을 재료**를 준다 |
| `register_work` · `get_manifest` · `get_code` | 작업 등록 → 매니페스트 수령 → 생성+층2 거친 코드 수령 |
| `register_project` · `set_active` · `list_projects` | 트윈 프로젝트 등록·전환 |
| `set_workshop` · `check_workshops_clean` 외 | 작업장 등록·더티 체크 |

**규약**: `[대괄호]`는 **클래스에만** 쓴다. 미등록이면 마스터가 후보를 돌려주고, 작업장
Claude 가 사용자에게 물어 등록한다 — 다음 검색부터 자동 확장된다.

---

## 테스트

**879건, 전부 통과. pytest 없음** — 각 파일이 단독 실행된다.

```bash
python3 master/test_verdict.py                       #  19
.venv/bin/python master/test_work.py                 # 145
.venv/bin/python master/test_context_synth.py        # 102   σ.7 게이트·사실 게이트·서킷브레이커
.venv/bin/python master/test_context_search.py       #  82   마운트 라우팅·RRF·대괄호
.venv/bin/python master/test_graph.py                #  80   Source 한정·fail-closed·유령 행 방지
.venv/bin/python master/test_ontology.py             #  38   YAML 왕복 보존 (PyYAML 의존 0)
.venv/bin/python master/test_layer3_verify.py        #  63
.venv/bin/python master/test_projects.py             #  63
.venv/bin/python master/test_indexer.py              #  49   ff-only 미러·다이제스트·트윈 성장
# 그 외: mcp_servers 31 · workshop_check 47 · auth 46 · events 38 · provision 43
#        capability_routing 16 · broker_routing 9 · broker_health 8
```

---

## 세 클론을 동기 상태로 유지할 것

마스터(`sim@192.168.0.57:~/ax-cluster`) · BC-250 #1(`sim@192.168.0.43:~/ax-cluster`) ·
GitHub(**private — 유지할 것.** LAN 주소와 방화벽 규칙이 들어 있다).
보드는 `main` 이 체크아웃돼 있어 **push 가 거부된다 — 그쪽에서는 `git pull`** 을 쓴다.

## 관련

- 전신 프로젝트 — `~/AgentTest` (🔴 **참조 전용. 수정·push 금지**)
- 저장소에서 일할 때의 규칙 — [`CLAUDE.md`](CLAUDE.md)
