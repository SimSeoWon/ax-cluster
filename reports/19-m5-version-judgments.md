# 19 — 마일스톤 5: 두 버전 대조·판정

M4 이식 중 「우리 방식 vs 원전 방식」으로 갈린 자리들의 판정 기록. 규칙(마일스톤 문서):
둘 다 읽고 실측 → 대조표 → 진 쪽은 부활 조건과 함께 닫는다. 순서는 사용자가 정한다
(#185 부터 — 사용자 지시 2026-08-17).

## §1 #185 매니페스트 배달 경로 — scp(우리) ↔ git-carried(원전) 대조

### 두 구현의 실물

    원전   mcp/master_orchestrator/cluster_coordinator.py:147 `write_context_manifest`
           — 서버가 골조 HEAD 에 `.claude/tasks/<id>/context.md` 를 `git add -f` + commit.
           워커는 base 체크아웃 → 디스크에서 **읽기만** (`read_context_manifest`, 검색 0).
           push 는 골조를 싣는 그 push 에 무임승차 — 별도 전송이 없다.
    우리   master/work/manifest.py — 등록 시 1회 수집은 같으나 저장이 **트윈 파생물**
           (`<프로젝트>/manifests/<task_id>.md`). 파견 때마다 runner.deliver_manifest 가
           scp 로 워커의 `./.ax/work/<task>/manifest.md` 에 밀어 넣는다 (infer.py:329).

### [중요] 우리 scp 선택의 전제가 이미 죽었다

manifest.py 머리말의 근거: *"우리 마스터는 소스 저장소에 push 할 수 없다(pushurl 비활성)"*.
이 전제는 **2026-08-14 Flow Y 로 폐기됐다** — 마스터는 gitea-write 로 attempt/*·task/* 를
push 한다. 더 중요하게, **git-carried 에 마스터 push 는 애초에 필요 없다**: 매니페스트는
골조에 실리고, 골조는 `.2`(워커) 클론에서 push 된다 — 마스터 훅의 제약 밖이다.

### 이미 반쯤 원전 방식이다 (실측)

    드라이런 #143     NONCE 증명이 git-carried 성질에 기댄다 — **원전 방식으로 돌고 있다**
                     (selftest.py MANIFEST_REL_FMT = `.ax/tasks/<work>/context.md`)
    gitea 실물       selftest 브랜치 3개 전부 context.md 를 싣고 있다 (ls-tree 확인)
    실전 경로        task/177293f3 (실 durable) 는 **0건** — 지금의 실전만 scp 다

### 대조표

| 성질 | scp (우리) | git-carried (원전) |
|---|---|---|
| 검색 1회화 (C.2) | 성립 (등록 시 1회 수집 동일) | 성립 |
| 파견 전송 | 파견마다 SSH+scp 1회 (라이브 실증 됨) | **0** — 골조 push 에 무임승차, 체크아웃이 배달 |
| 재배정 | 마스터가 재-scp (마스터 개입 필수) | 새 작업장이 base 체크아웃만 하면 자동 |
| 이력 추적 | manifests/<id>.md 에 base_commit 기록 — **역방향(커밋→컨텍스트)은 트윈 생존에 의존** | *"어떤 컨텍스트로 이 코드가 나왔나"* 가 git 히스토리에 영구·전 클론 복제 |
| 유실 시 복구 | 재수집 가능하나 **그때의 검색 결과 ≠ 그날의 검색 결과** (RAG 인덱스는 자란다) | 커밋과 함께 동결 — 불변 |
| 저장소 오염 | 없음 | `.ax/tasks/*.md` 가 히스토리에 남는다 — [주의] **원전이 이미 안고 살던 비용** (`.claude/tasks/` 커밋). merge 되면 main 에도 감 (#197 검수 트리 실측: files_changed 에 context.md 포함) |
| gitignore 함정 | 해당 없음 | `add -f` 필요 — 소 2.3.2 에서 **이미 이식됨** |
| 폴링 데몬 확장(M6 #204) | 데몬이 매니페스트를 **못 받는다** — 마스터 push 채널이 없는 토폴로지에서 죽는 경로 | 데몬이 pull 만 하면 받는다 — 원전이 이 방식이었던 **진짜 이유** (원전 워커 = git 폴링 데몬) |
| 전환 비용 | — | 골조 커밋 시점(.2)에 context.md 동반 commit + infer 프롬프트의 읽기 경로 변경. **기제는 selftest 에 이미 있다** |

### 판정 재료 요약

scp 가 이기는 칸이 「저장소 오염 없음」 하나인데, 그 비용은 원전이 이미 수용했던 것이고
`.ax/` 라는 기계 디렉토리 하나로 격리된다. 반면 git-carried 는 재배정·이력 추적·전송 0 에
더해 **M6 폴링 데몬 확장의 전제 조건**이다 — scp 는 마스터가 밀어 넣는 토폴로지에서만 살고,
원전의 워커(폴링 데몬)는 pull 밖에 못 한다. 우리 scp 의 선택 근거(마스터 push 불가)는
Flow Y 로 소멸.

### 판정 (사용자 확정 2026-08-17): **git-carried 로 되돌린다**

부활 조건: 히스토리에 남는 `.ax/tasks/*.md` 가 사람의 작업(SourceTree 가독성 등)을 실제로
방해한다고 사용자가 판단하면 scp 로 복귀 — `runner.deliver_manifest` 는 그래서 지우지 않는다.

### 이식 (`master/work/carry.py`)

    publish       매니페스트를 durable `task/<task_id>` 에 commit·push (마스터 쓰기 표면 안,
                  §8.4 정합). 멱등 — tip 과 같으면 커밋 0, 바뀌면 tip 위에 새 커밋 (이력 보존).
                  커밋 메시지는 원전 그대로. `.gitignore` 함정은 `add -f` (소 2.3.2 교훈).
    materialize   워커가 fetch + `git show` 로 자기 클론에서 꺼내 scp 시절과 **같은 경로**
                  (.ax/work/<task>/manifest.md)에 놓는다 — 소비 형식 불변, 운송만 교체.
                  [중요] blob sha 대조 (scp 의 sha256 되읽기와 같은 자리). stdout 을 건너는
                  것은 sha 뿐이라 CP949 함정이 성립하지 않는다.
    배선          등록(register_work) 시 publish · 파견(run_once/dispatch_task) 시 재-publish
                  (refresh 반영, 멱등)+materialize. **조용한 scp 폴백 없음** — 주입(테스트)만
                  기존 scp 자리를 그대로 잰다.

### 라이브 실측 (실 gitea + 실 워커 2대)

    publish        6.6s — task/selftest-carry-0817 신설, 정본 클론의 pre-push 훅 통과 (task/* 허용)
    .43 (리눅스)    실체화 1.1s · blob 대조 통과 · 워커에 브랜치 안 생김 (임시 ref 만)
    .2  (윈도우)    실체화 1.3s · blob 대조 통과 · cmd 리다이렉트로 UTF-8 본문 무손상
    멱등           같은 본문 재-publish → 커밋 0 ("내용이 durable tip 과 같다")
    [주의] 실측이 함정 하나를 재연했다: .2 경로를 손으로 박았다가 실패 — **경로는 레지스트리가
    정본**이라는 기존 규칙의 재확인 (실전 파견은 facts 를 레지스트리에서 받으므로 무관).

테스트 28건 신규 (실 git 픽스처: bare 원격 + 워커 클론 왕복 · 멱등 · fail-closed 4종 ·
양 OS 명령 모양 · 등록 배선). 전체 3408/3408.

[대기] 검증 브랜치 `task/selftest-carry-0817` 삭제는 사람의 자리다 (대화형 세션 브랜치 삭제
금지 규칙):  `git push gitea-write --delete task/selftest-carry-0817` — 단, 정본 훅이 삭제를
막으므로 gitea 웹 UI 에서 지우는 쪽이 간단하다.
