# AX Cluster

집의 여러 컴퓨터를 묶어 **프로젝트의 디지털 트윈을 만들고, 타입별 검증 게이트로 코드 작성을
돕는** 분산 코딩 클러스터. `unreal`(UE5/C++)과 `code`(AXCluster/Python) 프로젝트를 다룬다.

**플랫폼**: 리눅스 마스터(Ubuntu 22.04) + 윈도우 2대(작업장 `.2` · 게임 요청자 `.33` — AXCluster 에서는 `.33` 도 워커) + BC-250 1대

> **현재 방향**: M1~M6는 마감됐고 **마일스톤 7(개선·확장, 2026-10-18 개시)**을 진행한다.
> 원전 포팅은 종료했으며 프로젝트 `kind`별 골조·소스 경계·검사 계약을 따른다.
> 항목과 진행 상태는 Redmine, 현재 운영·승인·검증은 [인수인계서](docs/orchestrator-handoff.md)가 정본이다.
>
> 🔴 **파이프라인의 정본은 사용자의 7단계다** (확정 2026-09-02) — 요청자 `.33` 이 골조를 만들고,
> 마스터가 조각내 파견하고, **워커가 자기 서브 브랜치에 커밋**하고, **통합은 다시 `.33`** 이 한다.
> 「통합자」는 2026-09-04 에 **삭제**됐다(약 1,000줄). 사람 게이트는 **둘** — ⑺ 전진과 finalize.
> 자세히: [`docs/16-worker-orchestrator-mode.md`](docs/16-worker-orchestrator-mode.md) ·
> [`machines/sim-desktop.md`](machines/sim-desktop.md).
> 요청자·통합 위치는 프로젝트별이다. 게임은 `.33`, **AXCluster는 마스터 `.57`이 요청자**이며
> `.2`·`.33`·`.43`이 워커다(`.33`은 `C:\trunk\AXCluster`에서 작업).
>
> 🔴 **비UE `kind: code` 프로젝트도 같은 7단계 경로를 쓴다** (`#695`, 첫 실증
> KimodoMotion_WebUI). 프로젝트 초기화·배달은 체크아웃 안에 `.agents/skills`와
> `.codex/config.toml`을 만들고 검사한다(`#699`, `63ea616`). Windows 워커 부트스트랩은
> Codex 샌드박스 계정의 체크아웃 수정 권한도 함께 건다(`#698`, `906fe60`). 2026-10-01에
> ModularStage·NS·KimodoMotion_WebUI의 등록 작업장 9개 조합을 현재 HEAD로 배달·검사했다.
> [주의] 첫 실증은 스킬 실패가 요청자에게 통보되지 않고 work가 미종결로 남는 결함을 잡았다
> (`#700`·`#701`); 해당 work는 `cancelled`로 강제 종결했다. 이후 수정·배포와 현재 이슈 상태는
> 레드마인과 [`docs/orchestrator-handoff.md`](docs/orchestrator-handoff.md)에서 확인한다.
>
> **지휘자는 둘이다** (사용자 2026-09-07) — 마스터 대화 세션을 **Claude ↔ Codex** 가 한도에 따라
> 교대한다. [`ax-handoff`](master/skills/ax-handoff/SKILL.md)로 인수인계·사용자 보충·실제 상태와
> 승인 범위를 대조한다. 공용 규칙은 [`docs/orchestrator-rules.md`](docs/orchestrator-rules.md),
> 현재 담당·운영 모드·검증 결과는 한 벌 [`docs/orchestrator-handoff.md`](docs/orchestrator-handoff.md)에 둔다.
> **워커 지휘자는 [`ax-mode`](master/skills/ax-mode/SKILL.md)로 `lane`/`claude`/`codex` 중 선택한다.**
> 사용자 선택 후 준비 검사를 통과해야 저장한다. 전역 선택은 **새 work 등재의 기본값**이며,
> 기존 work의 `worker_mode` 스탬프와 후속 라운드는 소급 변경하지 않는다.
> 두 마스터 스킬은 Claude·Codex 홈에서 같은 저장소 정본을 가리킨다(`d061598`).
> 세션 시작 지침은 홈과 저장소의 AGENTS·CLAUDE에 연결돼 있다. 홈의 두 파일은
> `machines/sim-desktop-agents.md`·`machines/sim-desktop.md`를 가리키는 심볼릭 링크로 유지한다.
> Windows readiness는 SSH Session 0의 샌드박스 실행 대신 `/IT /RL LIMITED` 예약 런처의
> 등록 계약을 검사한다(`00f8532`). 등록 통과 뒤에도 로그인·인증과 실제 읽기·apply_patch·결과
> 회수를 별도로 확인한다. 실증·배포 기록: [리포트 89](reports/89-codex-worker-readiness-and-write-probes.md).
> R5 골조 리뷰의 후속 구현 검증과 색인기 검사 격리(`b53fd84`), AXCluster 세 워커 배포 기록은
> [리포트 90](reports/90-r5-indexer-test-isolation-and-deployment.md)에 있다.
>
> M6의 최근 변화는 **리뷰를 색인 스레드에서 분리한 커밋 단위 큐**다. 색인은 기다리지 않고
> 등재만 하며, 별도 타이머가 로컬 LLM 1차 초안을 만든 뒤 Antigravity가 원본 diff와 대조해
> 정형 리뷰로 퇴고한다. 이 소비자는 **마스터 `.57`에서만** 돌며 Claude는 자동 경로에 없다.
> 설계: [`docs/17-review-queue.md`](docs/17-review-queue.md).
>
> 열린 축 하나는 **다중 프로젝트**이고 착수 순서는
> [`docs/12-multi-project.md`](docs/12-multi-project.md) §12.3-a 다.
> [중요] **분자는 여기 적지 않는다** — 레드마인(version *마일스톤 7*)이 계산한다.
> [주의] 버전 *아이디어 — 추후 검토 수집* 은 **일감이 아니다**(집계 금지).
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
                                 · [중요] 사실 게이트 — 주석에만 있는 식별자 주장은 거부
                              → 벡터(다국어) + BM25 재색인, A/B 세대 무중단 교체
                              → 리뷰 큐에 커밋 등재 (색인은 기다리지 않는다)
별도 타이머                   → 로컬 LLM 1차 초안 → Antigravity 퇴고
                              → 정형 리뷰 + R번호 → 성공한 초안 제거 → 주말 개선 플랜의 기존 입력

[트윈을 쓰는 길 — 사용자 확정 7단계]
요청자       → 컨텍스트 검색 → 모든 대상의 동작 계획 → 주석 작업지시서가 든 골조 작성
             → `task/<work>/base`에 골조 커밋·push → work 등재
마스터       → 골조 파일 기준으로 조각 분해 → 작업 브랜치에서 조각별 서브 브랜치 생성
             → 워커 모드(`lane`/`claude`/`codex`)에 따라 `.2`·`.43`로 병렬 파견
               (AXCluster 마운트 시 `.33`도 워커, 요청자는 마스터)
워커         → 자기 서브 브랜치에서 본문 구현 → 결정적 게이트 → 커밋·push
마스터       → 모든 조각 완료를 요청자에게 통보
요청자       → 조각 브랜치를 작업 브랜치에 머지 → 프로젝트별 검사 한 번
             → ⑺ 사람 게이트에서 「버그냐 구조 수정이냐」 결정 → 다음 라운드 또는 finalize

[주의] UE 프로젝트의 빌드는 `.2`가 맡고, `kind: code` 프로젝트는 프로필의 빌드·테스트 계약을
쓴다. 요청자는 게임 `.33`, AXCluster `.57`이며, 실패 통보와 work의 terminal 상태는
각각 확인한다(`#700`·`#701`의 현재 상태는 레드마인 정본).
```

[중요] **「durable 단일 writer」는 서버 한 명만 쓴다는 뜻이 아니다.** 원전
`~/AgentTest/mcp/task_queue/cluster_coordinator.py`의 `verify_and_merge`에서 검증 워커의
epoch fencing을 가리킨다. 사용자 확정 7단계의 현재 브랜치 모양은 다음과 같다.

```
base      task/<work_id>/base                       ← 요청자가 만든 작업 브랜치·골조
round 1   task/<work_id>/<task_id>                  ← base에서 갈라진 워커 조각 브랜치
round N   task/<work_id>/r<N>/<task_id>             ← 전진 뒤 개선 라운드의 조각 브랜치
[소멸] attempt/…                                     ← 철거됨 (`#327`)

[중요] 계층형은 `#319`(2026-08-27, 사용자 결정 ⓐ) — 종전 평평한 이름은 **읽기만 호환**.
```

[중요] **리눅스가 강제하는 변경은 정확히 하나다** — `verify_and_merge` 안의 **UE5 빌드 단계가 `.2` 로
간다.** 그 밖에 M3 에서 바꾼 것은 포팅이 아니라 재설계였다. 지금은 요청자가 골조와 통합을,
워커가 조각 브랜치의 구현과 커밋을, 마스터가 분해·파견·통보를 맡는다.
🔴 [중요] **ephemeral `attempt/` 계층은 미래가 아니라 철거됐다** (`#317` 미결 ⑦ → `#327`,
2026-08-27). 종전 이 자리엔 *"아직 안 배선된 것 하나"* 로 적혀 있었다 — 배선하지 않기로 **결정**한
것이다. 지금은 워커가 격리된 워크트리에서 조각 브랜치에 커밋·push하고, 요청자 `.33`이
⑺에서 작업 브랜치로 통합한다. 격리는 브랜치와 워크트리가 함께 지킨다(`#321`).
[주의] 그 계층이 지키려던 것 — **실패의 증거** — 는 스풀(`read_runs`)과 레드마인 노트에 남는다.
`attempt/*` 이름은 pre-push 허용 목록과 `plan_remote_cleanup`(옛 모양의 찌꺼기 청소)에만 남아 있다.

분산이 주는 것은 처리량이 아니라 **증분**이다 — 실측상 워커 2대는 12% 빠르고 90% 비쌌고,
값은 *"작업이 항상 컴파일되는 상태로 쌓인다"* 는 데 있다(§4.5). [중요] 그 값은 위 두 모양 **어느
쪽에서도 같다** — 증분을 지키는 것은 브랜치 토폴로지가 아니라 **게이트**이기 때문이다.

[중요] **워커에 큐 토큰을 주지 않는다 — 마스터가 중개한다**(실측: 워커는 8101 에 401). 하트비트도
마스터가 대신 친다. 요청자→워커 한 바퀴 **1분 29초** 실측.

추론은 **마스터 브로커(8102)** 를 거쳐 노드로 간다 — 컨텍스트 합성은 `gemma4:e4b`.
본문 작성 레인은 `codex → agy → 로컬` 순이고(`master/work/lanes.py`), `qwen2.5-coder:14b` 는
그 로컬 폴백 자리다. 모델별 적합도·환각 실측은
[`machines/llm-fitness.md`](machines/llm-fitness.md).

[중요] **문서는 지도지 정답이 아니다.** 모든 문서는 **소스코드라는 원천**을 바탕으로 찾고
이해하기 쉽게 하는 네비게이션이다. 판단 기준은 *"맞는 자리를 찾을 수 있나"* 이지
*"증명되게 옳은가"* 가 아니다 — 근사는 허용하되, **없는 것을 있다고 하면 틀린 자리로
보내므로** 사실 게이트는 둔다.

[중요] **마스터는 인프라지 작업장이 아니다.** 파일 I/O·빌드·테스트는 파일을 소유한 윈도우에서
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
│   │   ├── expand.py           질의 확장 — [중요] 부분 문자열(한국어 조사) · 짧은 별칭 차단
│   │   ├── infer.py            질의 → 도메인 **결정적** 추론 — [중요] 모르면 비운다
│   │   ├── documents.py        컨텍스트 MD 파싱. 벡터는 「## 요약」 절만 임베딩
│   │   ├── generation.py       A/B 세대 포인터(영속) — 프로세스가 갈려 있어 필요
│   │   └── paths.py            [중요] 경로는 상수가 아니라 함수 — 마운트 전환에 재기동 불필요
│   ├── context_synth/          ← 컨텍스트 MD 합성 (중 1.2)
│   │   ├── prompt.py           프롬프트 + grounding 3채널(관련문서 3·도메인 1·관계그래프)
│   │   ├── md.py               σ.7 펜스 제거 · 저장 전 게이트 · content_hash/source_commit
│   │   ├── verify.py           [중요] 사실 게이트 — 주석에만 있는 식별자를 결정적으로 적발
│   │   ├── synth.py            배치·서킷브레이커·모델 회수
│   │   ├── review_queue.py     커밋 단위 리뷰 큐 — 상태·잠금·갈래별 재시도
│   │   └── review_runner.py    별도 소비자 — 로컬 초안 → Antigravity 정형 리뷰·R번호
│   ├── ontology/               ← 온톨로지 문서 (중 1.3) — PyYAML 의존 0
│   │   ├── yaml_io.py          우리가 쓴 것만 우리가 읽는다. 안 바뀌면 안 쓴다
│   │   ├── stale.py            워터마크 2개 비교 — 어느 도메인을 재합성할지
│   │   ├── layers.py           L1/L2/L3 추정 — 구조 우선, git 은 강등만
│   │   ├── collect.py          멤버 후보 **제안** — 조상·자식·include 이웃
│   │   ├── hierarchy.py        개념 계층 — 하위 문서를 object 로, 순환 방지
│   │   ├── verify_facts.py     [중요] 온톨로지 사실 게이트 — 호출 관계를 실측과 대조
│   │   ├── package.py          패키지 쓰기 — [중요] 검수 잠금은 덮지 않는다
│   │   ├── edit.py             편집이 곧 잠금 · 일괄 보호(`protected`) — 재생성이 못 덮는다
│   │   ├── drift.py            드리프트 감사 — 커밋 차이가 아니라 **근거 파일 변경**으로 좁힌다
│   │   └── view.py             [중요] 자립형 HTML 뷰어 한 장 — 서비스를 또 띄우지 않는다
│   ├── graph/                  ← 관계 그래프 (중 1.1, LLM 0)
│   │   ├── parse.py            tree-sitter C++ · UE 매크로 전처리
│   │   ├── class_graph.py      상속 그래프 + methods 소유권
│   │   └── dependency.py       `#include` 의존 그래프
│   ├── events/                 ← Gitea 훅 → 스풀 → 색인기 (트윈이 자라는 지점)
│   │   └── gate.py             [중요] **색인 일시정지 게이트** — 작업 중이면 색인을 미룬다(실측: 셀프
│   │                              테스트의 push 가 색인기를 15번 깨웠고 14번은 할 일이 없었다).
│   │                              [주의] 조건은 `in_progress` **하나뿐**(원전 Phase 2) · 모르면 진행
│   ├── work/                   ← 작업 루프 — 골조·분해·**추론 파견**·검증
│   │   ├── coordinator.py      [중요] **2단 브랜치 조율 (원전 이식)** — `selftest` 드라이런용. 「단일 writer」= epoch 펜싱.
│   │   │                          `assign_attempt`(git 접촉 0) · `push_attempt`(ephemeral, force 허용)
│   │   │                          · `verify_and_merge`(**epoch 펜싱** — 낡은 좀비는 병합 거부)
│   │   │                          · `cleanup_attempts`([중요] **기본은 세기만** — 잔재는 증거다)
│   │   ├── selftest.py         [중요] **실증 하네스** — `dry`(임시 저장소) / `live`(실 Gitea·실 작업장).
│   │   │                          매니페스트에만 심은 NONCE 가 durable 산출물에 나타나면
│   │   │                          **git 으로 실린 컨텍스트가 실제로 읽혔다**는 증명이 된다
│   │   ├── conventions.py      [중요] UE 금지사항(개명·상속변경·모듈이동 — 블루프린트 에셋이 깨진다) +
│   │   │                          `repo/CLAUDE.md § Code conventions` 를 **읽어** 매니페스트에 싣는다
│   │   ├── skeleton.py         [중요] 골조 생성 + **인터페이스 동결**(결정적, LLM 0). 텍스트만 낸다
│   │   ├── skeleton_gate.py    [중요] **등재 전에 세워 본다** — 빌드 통과해야 등재
│   │   ├── decompose.py        분해 — 의존 순서·파일 불가분·`[PSEUDO:N]` 뎁스
│   │   ├── heuristics.py       [중요] 대화형 휴리스틱 — **사람이 답한 것만**, 범위(project/domain/once)
│   │   ├── infer.py            [중요] **추론 파견** — 워커 지휘자 실행·조각 커밋·결과 회수
│   │   ├── mode.py             워커 모드·출처·영속 상태 — 기존 work 스탬프가 전역보다 우선
│   │   ├── conductor.py        마스터 담당 기록·워커 준비 검사·모드 전환의 정본
│   │   ├── layer1.py           [중요] **층1** — 동결·잔재·`[FEEDBACK]`. 수락·적용 **양쪽**에서 돈다
│   │   ├── review.py           요청자의 전진·finalize — 사람 게이트를 거쳐 통합·검사
│   │   ├── failures.py         실패 카탈로그 — 판정 원문을 다음 골조로 되먹인다
│   │   ├── porting.py          포팅 원본 대응 — [중요] 경로만·읽기 전용. 실측 동명 9 → 정규화 21쌍
│   │   ├── distribute.py       `/distribute` 입구 — [중요] plan→register→dispatch, 단계마다 사람이 끊는다
│   │   ├── runner.py           워커 선택·파견·응답 회수와 조각 커밋 주기
│   │   ├── batching.py         [중요] 파일 불가분 묶음 — 열쇠는 **모듈+경로+stem**(basename 아님)
│   │   ├── declarations.py     헤더 선언 주입 — 실측 환각 2 → 0
│   │   ├── norms.py            도메인 규범(invariants 중심) 부착
│   │   └── cleanup.py          찌꺼기 정리 — [중요] 병합된 것만. 원격은 `remote` 서브커맨드만(병합 확인분)
│   ├── transfer.py             상태 익스포트/임포트 — [중요] 두 벌(compat·full) · 임포트는 **병합**
│   ├── broker/                 ← 추론 브로커 (Ollama 호환, 노드 라우팅·핀 유지)
│   ├── task_queue/             ← 작업 큐 (claim·lease·epoch fencing·능력 라우팅)
│   ├── projects/               ← 프로젝트 레지스트리 + **작업장의 MCP 단일 창구**
│   ├── status.py               클러스터 상태 수집·렌더 — [중요] 읽기 전용·주기 가드 120초
│   ├── viewer.py               [주의] 옛 `/view` (→ `/cluster` 302). 서빙은 `webui/` 가 한다
│   ├── webui/                  [중요] **원전 웹 UI 복각** — Context Server·온톨로지·게시판·`/commit-flow`
│   ├── source_text.py          [중요] CP949 대응 — 소스의 44%가 CP949 다
│   ├── sqlite_util.py          [중요] **동시 접근 공통 설정** — `busy_timeout` 10초·WAL. 색인기와
│   │                              검색이 같은 DB 를 만지므로 이걸 안 걸면 `database is locked`
│   ├── sigma_audit.py          [중요] **조용한 실패 스캐너 (원전 σ 감사 이식)** — 넓은 핸들러 +
│   │                              의도가 안 적힌 것을 찾는다. [주의] **판정은 사람이 한다**
│   ├── auth.py                 3서비스 공용 베어러 인증 (fail-closed)
│   ├── verdict.py              층2 판정 계약 (fail-closed)
│   └── layer3_verify.py        층3 게이트 — UE5 빌드·RunTests 로그
├── <프로젝트명>/               ← 디지털 트윈 데이터 (gitignore)
│   ├── context/  ontology/     원본 — 합성 산출물 (도메인 색인 대상)
│   ├── repo/                   소스 클론. [중요] 색인 대상은 `Source/` 뿐
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
| 프로젝트 레지스트리 (MCP) + **웹 UI** | 8103 | `ax-projects.service` (`/`·`/ontology`·`/cluster`·`/commit-flow`·`/rag-logs`) |
| ↳ 지휘 제어 표면 | 8103 | `/control/*` — **요청자 토큰 전용** (무인증 401 · 워커 403) |
| 색인기 | — | `ax-indexer.path`(inotify) → `ax-indexer.service` |
| 리뷰 큐 소비자 | — | `ax-review-queue.timer`(10분) → `ax-review-queue.service` |

[중요] 세 서비스는 **베어러 토큰**(`~/.config/ax-cluster/token`, 0600)으로 뜬다 — 토큰이 없으면
**서비스가 뜨지 않는다**(fail-closed). [주의] **8103 의 웹 UI 와 `/api/v1` 은 공개**다(`master/webui/app.py`
`PREFIXES`; 되돌리려면 `AX_VIEW_REQUIRE_TOKEN=1`) — 그쪽에 민감한 본문을 두지 않는다. 쓰기 표면
`/control/*` 은 요청자 토큰 전용이다. 방화벽 LAN 한정은 **별개의 두 번째 층**이다. `Anywhere` 로 넓히지 말 것.

---

## 사용법

```bash
# 트윈 만들기 — 관계 그래프 (LLM 0, 1,654 파일 ≈ 2.9초)
.venv/bin/python -m master.graph build            # 상속 + #include
.venv/bin/python -m master.graph status

# 트윈 만들기 — 컨텍스트 MD 합성
.venv/bin/python -m master.context_synth status   # 소스 그룹 vs 문서 대비
.venv/bin/python -m master.context_synth sample 4 # [중요] dry-run — 스냅샷을 안 건드리고 통과율만
.venv/bin/python -m master.context_synth fill     # 문서 없는 그룹만 보충

# 색인
.venv/bin/python -m master.context_search.rebuild # 전체 재색인 (A/B 한 번 교체)

# 온톨로지 — [중요] 이 순서로 (plan 은 아무것도 안 바꾼다)
.venv/bin/python -m master.ontology plan|dry|refresh
.venv/bin/python -m master.ontology drift          # 트윈과 소스가 어긋난 곳
.venv/bin/python -m master.ontology view           # 자립형 HTML 한 장

# 상태 주고받기
.venv/bin/python -m master.transfer export         # 두 벌(full·compat) + README
.venv/bin/python -m master.transfer import <zip>   # [중요] 기본은 계획만 · --apply 는 먼저 백업

# 분산 작업 (마일스톤 3 대 1) — [중요] 단계마다 사람이 끊는다. 스킬: /distribute
.venv/bin/python -m master.work.distribute plan     <프로젝트> <슬러그> <클래스:파일…>
#   → 계획 JSON 이 나온다. [중요] **사람이 그 파일에서 조각을 지운다** (눈으로는 자를 수 없다)
.venv/bin/python -m master.work.distribute register <프로젝트> <슬러그> "<제목>" <저장소>
#   → 프로젝트 kind의 골조·검사 계약을 확인하고 등재한다
.venv/bin/python -m master.work.distribute dispatch <프로젝트> <work_id> 4
.venv/bin/python -m master.work.porting  pairs      # 포팅 원본↔대상 대응 (실측 9 → 정규화 21쌍)

# 워커에 일 시키기
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client probe <프로젝트>    # 머신 실측
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client plan <프로젝트>     # 쓰기 전 계획
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client deliver <프로젝트>  # 한 프로젝트 배달
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client check <프로젝트>    # 한 프로젝트 대조
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client update              # 마운트된 프로젝트 배달→대조 (--all = 등록 전체)
.venv/bin/python -m master.work.infer probe        # 누가 추론을 받을 수 있나 (큐 무접촉)
.venv/bin/python -m master.work.infer run-p <프로젝트> 4 # 병렬 파견; 워커가 자기 조각을 커밋
.venv/bin/python -m master.work.infer spool <work> # 응답 스풀 — 어디까지 진행됐나
# 전진·finalize는 요청자의 ax-advance 스킬과 ax-projects MCP; 승인 게이트를 따른다
.venv/bin/python -m master.work.runner once <프로젝트> # 워커 한 조각의 실행 주기
.venv/bin/python -m master.work.cleanup plan       # [중요] 먼저 본다 — 아무것도 안 지운다
.venv/bin/python -m master.work.cleanup apply      # 병합된 브랜치·끝난 부산물만 삭제

# 운영
.venv/bin/python -m master.status show                   # 머신·서비스·큐 요약 (읽기 전용)
.venv/bin/python -m master.status html                   # → <프로젝트>/cluster.html 한 장
#   [중요] 다른 머신에서 보기: http://192.168.0.57:8103  ← 인증 없음 (원전 웹 UI)
#      / = Context Server · /ontology = 도메인 뷰어+그래프 · /cluster = 클러스터 상태
#      [중요] /cluster 상단 「지휘 상태」 = 마스터 담당(claude/codex) + 워커 실행 모드
#         마스터 담당은 **마지막으로 기록된** 지휘자다 — 생존 판정도 잠금도 아니다
#   [중요] 최소 간격 120초 — BC-250 을 자주 두드리지 않는다 (넘기려면 --force)
curl -s localhost:8102/health | python3 -m json.tool     # 노드별 상주 모델
systemctl status ax-task-queue ax-broker ax-projects ax-indexer.path
journalctl -u ax-indexer -n 30 --no-pager                # push → 트윈 성장 이력
.venv/bin/python -m master.events.install_hook           # Gitea 훅 설치 점검
```

---

## RAG 검색 로그

[RAG 검색 로그](http://192.168.0.57:8103/rag-logs)에서 프로젝트·기간·검색어·작업 분류·상태·요청 ID로
조회한다. 상세에는 **사용자 원문 → LLM 검색 질의 → 확장·실제 검색어 → 당시 반환 결과**가 연결된다.
한 요청의 여러 검색을 모아 볼 수 있고, 반환 순위·본문·채널 점수를 당시 스냅샷으로 확인한다(`#837`).

사용자 명령 검색은 `task_type="user_command"`, `user_request`에 실제 입력 전체를 전달하고,
후속 검색은 반환된 `request_id`를 재사용한다. 원문을 받지 못한 호출은 미수집으로 남기며 추정하지 않는다.
현재 자동 원문 캡처는 Claude UserPromptSubmit 훅 경로이며 Codex/native MCP는 명시 전달한다.

지금은 **실사용 로그 수집 단계**다. 반환 결과 유무를 적중률로 해석하지 않는다. 이후 한글 질의
표본에 정답 문서·관련 결과 판정을 붙여 Hit@k 등을 평가하고, 품질이 낮으면 질의 변환·확장·순위·색인
자료를 대조한다. 현재 단계에서 검색 가중치·형태소 분석기·trigram·별칭을 자동 조정하지 않는다.
보존·배포 후 확인 방법은 [온보딩 런북](docs/14-onboarding-runbook.md#rag-검색-로그-확인)을 참고한다.

## 운영 문서 최신화

등록한 README·CLAUDE·AGENTS·온보딩·인수인계 문서는 `master.doc_sync`의
**계획 → LLM 수정안 → 검증·승인 적용**으로 갱신한다. 원문·근거·등록 목록을 대조하며
보호 문서에는 별도 승인이 필요하다. [등록 목록과 사용법](docs/document-sync.md)을 참고한다.

## MCP 도구 (Claude·Codex가 쓰는 창구)

`ax-projects`(8103) 하나가 작업장의 단일 창구다. [중요] **개수는 여기 적지 않는다** —
`master/test_mcp_servers.py` 가 실제 등록 목록으로 개수를 고정한다(그 파일이 정본). 아래 표는
**주요 도구**만 적는다.

| 도구 | 하는 일 |
|---|---|
| `search_context` | [중요] **검색 입구는 이것 하나** — 대괄호 해석 → 시소러스 확장 → 융합 검색 |
| `infer_domain` | 질의가 말하는 도메인을 **결정적으로** 판단 — [중요] 모르면 비운다(추측 안 함) |
| `resolve_terms` · `add_alias` · `mark_not_a_class` | 별칭 조회·등록. 마스터는 묻지 않고 **물을 재료**를 준다 |
| `register_work` | 작업 등록 (`get_code` 는 `#734` 로 걷혔다 — 층2 는 `wcommit` `#696`) |
| `create_domain` · `edit_ontology_item` · `remove_ontology_item` | 온톨로지 편집 — [중요] **편집이 곧 잠금** |
| `lock`·`list_locked` · `protect`·`list_protected` | 사람 검수 잠금 / [중요] **일괄 보호**(재생성이 못 덮는다) |
| `sync_ontology` · `drift_audit` · `unassigned_classes` | 경로·선언 동기화 · 어긋남 감사 · 미배정 노출 |
| `register_project` · `set_active` · `list_projects` | 트윈 프로젝트 등록·전환. 등록 뒤 다음 단계는 `python -m master.projects.onboard <이름>`(계획 → `--confirm`, `#227`) |
| `set_workshop` · `check_workshops_clean` 외 | 작업장 등록·더티 체크 |
| `get_worker_mode` · `set_worker_mode` | `ax-mode`의 워커 지휘자 조회·선택. 준비 검사 후 저장하며 **새 work 등재부터 기본값**으로 사용. 기존 work 스탬프·진행 조각에 소급하지 않음 |
| `get_orchestration` · `record_master_conductor` | 마스터 담당 + 워커 모드 조회 / 담당 기록 — [중요] 기록일 뿐 **세션 실행·종료·잠금이 아니다** |

**규약**: `[대괄호]`는 **클래스에만** 쓴다. 미등록이면 마스터가 후보를 돌려주고, 작업장
Claude 가 사용자에게 물어 등록한다 — 다음 검색부터 자동 확장된다.

---

## 테스트

pytest는 쓰지 않는다. 스크립트형 검사와 unittest 검사가 함께 있으며,
AXCluster 통합 검사의 명시 목록은 `tests/integration/checks.json`이다.

[중요] **여기에 개수를 적지 않는다.** 하루에 여섯 번 고쳤고, 마일스톤 분자를 레드마인으로 옮긴
것과 **같은 이유**다 — 수치가 아니라 **세는 법**을 적는다.

```bash
# AXCluster 통합 검사 — 첫 실패에서 멈추고 출력·종료코드·완료 신호를 대조한다
.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

[중요] **합계를 세는 명령은 [`CLAUDE.md`](CLAUDE.md) 에 한 벌만 둔다** — 두 곳에 적으면 어긋난다.
그리고 그 명령은 **2026-08-14 에 고쳐졌다**: 옛 `| tail -1` 은 ① 마지막 줄이 구분선인 파일
13개를 못 셌고 ② **크래시한 파일은 수치를 안 찍어 합계가 그대로 보였다** — import 실수로 테스트
파일 3개가 죽었는데 합계가 안 변해서 못 봤다. **세는 도구가 조용히 틀리면 세션 내내 틀린다.**

| 파일 | 무엇을 지키나 |
|---|---|
| `test_verdict.py` | 층2 판정 계약 — [중요] venv 없이 도는 **순수 로직** |
| `test_work.py` · `test_runner.py` | 작업 루프 · 워커 파견(fail-closed 마커·계측) |
| `test_skeleton.py` | 골조 · [중요] **동결**(추가는 허용, 변경·삭제는 위반) · 태그 계약 |
| `test_skeleton_gate.py` | [중요] **fail-closed** — 미확인은 통과가 아니다 |
| `test_decompose.py` | 의존 순서 · [중요] **묶음(동시) vs 뎁스(순차)** 구분 |
| `test_heuristics.py` | [중요] 사람이 답한 것만 · **범위**(project/domain/once) |
| `test_infer.py` | [중요] **fail-closed 파견 판정** — 마커+응답파일 둘 다 · 스풀 재사용 · 선행 실패 차단 |
| `test_no_integrator.py` | 삭제된 통합자 코드와 호출 경로의 부활을 차단 |
| `test_viewer.py` | [중요] **자격증명 분리 양방향** · 경로 화이트리스트 · 읽기 전용 · 낡음 배너 |
| `test_status.py` | [중요] 읽기 전용 명령만 · 주기 가드 · 상태는 색만으로 전달하지 않는다 |
| `test_layer1.py` | [중요] 휘발 태그·`[FEEDBACK]` 잔재 · 동결 의미(추가 허용/변경 위반) · fail-closed |
| `test_porting.py` | [중요] 못 찾으면 **붙이지 않는다** · 원본이 대상 목록으로 **새지 않는다** |
| `test_batching.py` | [중요] **파일 불가분** — `.h`/`.cpp` 는 붙이고 **다른 모듈의 동명 파일은 가른다** |
| `test_ontology.py` | YAML 왕복 보존(PyYAML 의존 0) · 잠금 보존 · 사실 게이트 |
| `test_transfer.py` | 익스포트 두 벌 · [중요] 임포트는 **병합**(보호 필드 이월) |
| `test_context_synth.py` | σ.7 게이트 · 사실 게이트 · 서킷브레이커 |
| `test_context_search.py` | 마운트 라우팅 · RRF · 대괄호 · 시소러스 확장 |
| `test_graph.py` | `Source/` 한정 · fail-closed · 유령 행 방지 |
| `test_indexer.py` | ff-only 미러 · 다이제스트 · 트윈 성장 · 문서 스탬프와 커서. 합성 성공 케이스는 가짜 합성기를 주입해 브로커 없이 검사 |
| `test_coordinator.py` | [중요] **2단 브랜치** — 낡은 epoch 은 **부작용 없이** 거부(durable 안 움직임·좀비 attempt 는 증거로 보존). [중요] **주입이 아니라 실제 git**(임시 bare + 클론)으로 잰다 |
| `test_selftest.py` | [중요] 매니페스트가 **git 으로만** 도착하는지 · NONCE 왕복 · 잔재 0(로컬 ref 까지) |
| `test_gate.py` | [중요] 일시정지 조건은 `in_progress` **하나뿐** · HTTP 실패 시 디스크 대체 · **모르면 진행** |
| `test_conventions.py` | UE 금지사항 · `repo/CLAUDE.md` 절 추출. [주의] **파일 없음은 degraded 가 아니다**(그 파일은 gitignore 대상이라 부재가 정상 — 늘 빨간 게이트는 게이트가 아니다) |
| `test_sigma_audit.py` | [중요] **좁히는 조건 셋** — 넓은 핸들러만 · 예외를 값으로 돌려주면 조용하지 않다 · 의도는 **주석에서도** 찾는다. [중요] 이 파일이 스캐너의 `bare except` 누락을 **먼저 잡았다** |
| `test_sqlite_util.py` · `test_bm25_diagnose.py` | 동시 접근 설정 적용 · [중요] 검색이 **왜** 0건인지(용어 미일치 vs 색인 비어 있음) |
| 그 외 | [중요] **위 표는 전부가 아니다** — 목록은 `ls master/test_*.py` 가 답이고, 이 표는 **놓치면 안 되는 계약**만 적는다 |

[중요] **venv 가 필요한 것과 아닌 것이 섞여 있다** — `python3` 로 도는 것은 순수 로직뿐이고,
나머지는 `.venv/bin/python` 이다(pydantic·pyyaml·fastembed).

---

## 클론과 원격을 동기 상태로 유지할 것

정본 원격은 **Gitea**(`gitea@192.168.0.57:Sim/ax-cluster.git`)이고, 마스터(`~/ax-cluster`)와
BC-250 #1(`sim@192.168.0.43:~/ax-cluster`)이 둘 다 그것을 `origin` 으로 쓴다.
GitHub(**private — 유지할 것.** LAN 주소와 방화벽 규칙이 들어 있다)는 **Gitea 가 미는 푸시 미러**다 —
[중요] **GitHub 에 직접 push 하지 않는다**(미러가 덮어쓰고 Gitea 에 없는 것을 지운다).
보드는 `main` 이 체크아웃돼 있어 **push 가 거부된다 — 그쪽에서는 `git pull`** 을 쓴다.

## 관련

- Windows Codex 원격 실행 — [`docs/windows-codex-remote.md`](docs/windows-codex-remote.md).
  `workspace-write`·`windows.sandbox="unelevated"`·네트워크 허용과 `/IT /RL LIMITED` 런처를 함께 쓴다.
  로그인 사용자 세션이 필요하며 “세션 1”은 고정 SessionId가 아니다. 파일 수정까지 실행해 확인한다.

- 전신 프로젝트 — `~/AgentTest` ([중요] **참조 전용. 수정·push 금지**)
- 저장소에서 일할 때의 규칙 — [`CLAUDE.md`](CLAUDE.md)


커밋 자동 리뷰는 등록된 프로젝트 타입을 따른다: `unreal`은 UE, `code`는 Python,
`index_only`는 제외. Gitea push 감지→리뷰 큐 등재→로컬 초안·Antigravity 검증으로 실행한다.
운영 계약과 실증: [리뷰 큐](docs/17-review-queue.md#9-python-커밋-자동-리뷰-사용자-2026-10-03),
[리포트83](reports/83-python-commit-review.md).
