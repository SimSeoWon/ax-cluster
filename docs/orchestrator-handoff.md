# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **현재 체크포인트: 2026-10-10 17:33 KST · Codex · #787 catchup 운영 삭제 실증·통합 등록 완료, 승인된 커밋·배포 진행**.
  - **사용자 승인**: 「응 진행해」로 통합 목록 2개 등록·검증 변경 커밋/push/배포·반려 work의 보존 ref 하나 복원 push 후 타이머 자동 삭제 관측 승인.
  - **운영 실증 성공**: `20261010_0335_777_2_mkdtemp_774_5078e6e6/r1/7118f80b`의 `cfd986ad0ec1aa6b74eebee78b39617a7e0c2be6`을 원격 task ref 하나로 복원. 17:31:08 자연 catchup 타이머가 실제 삭제, #778 자동 노트 기록. triggers/dispatched/skipped/exceptions=0, 정리 1. 이후 원격 heads는 main만, 로컬 보존 ref의 팁 동일. 수동 sweep/apply·서비스 재시작 없음.
  - **검증**: `checks.json`에 branch_prune 69개·autodispatch 26개 등록. 정본 통합 31모듈·1,563개 검사 rc0(59.966초). 마스터 4프로젝트 가드 정상·onboard 80/80. 생산 코드 추가 변경 없음.
  - **커밋 대상**: `master/test_branch_prune.py`, `tests/integration/checks.json`, 이 인계서. 현재 HEAD `310e9f6`; 이 세 파일 커밋/push 후 clean 트리에서 마운트 AXCluster update 예정. 최종 해시·배달 결과는 #787 노트에 기록하고 되읽는다.
  - **남은 운영 관측**: ⑺ 전진 직후 삭제는 다음 승인된 전진에서 확인 필요하므로 #787은 진행 유지. #782 완료, #788 신규·미착수.

- **직전 체크포인트: 2026-10-10 17:28 KST · Codex · #782 커밋·배포·완료 · #787 가드 정비·catchup 회귀 완료, 후속 승인 대기**.
  - **저장소**: main, HEAD = origin/main `310e9f6` (#782 커밋·push 사용자 승인). 마운트 AXCluster `master.client update` rc0, .43·.2·.33 배달·검사 3/3, 출처 `310e9f6`(배달 시 clean). 새 push 색인기에 `cloud 무제한 8838자` 확인, 별도 재기동 없음. #782 완료(100%)·되읽기 확인; 전체 자동 합성 종료는 미조회.
  - **#787 진행**: 정본 `master.work.attempt install-hook`으로 ModularStage·NS·MotionForge 마스터 가드 갱신(rc0 각각), AXCluster 포함 status 4/4 정상. `test_onboard` 80/80으로 기존 live 79/80 해소. 비마운트 배달·마운트 전환 없음.
  - **미커밋**: `master/test_branch_prune.py`(기존 로컬 서브 에이전트) + 이 인계서. 실제 임시 Git에서 `drain(catchup=True, prune_fn=None)→sweep_terminal→apply_terminal→삭제` 회귀 14개 추가. 종결 work만 2ref 삭제, 진행·pending·unknown·main 보존, 보존 ref·이슈 노트 팁 일치, 멱등·catchup=False 무삭제. 에이전트와 지휘자 각각 69/69, diff check 통과. 생산 코드 변경 없음. 에이전트 완료.
  - **운영 실증 준비**: 원격 heads=main 하나 확인. 반려 work `20261010_0335_777_2_mkdtemp_774_5078e6e6` rejected·조각 2개 failed·worker codex. 보존 `refs/ax/pruned/task/<work>/r1/7118f80b` = `cfd986ad0ec1aa6b74eebee78b39617a7e0c2be6` commit 존재. 이 서브 ref 하나 복원 push 후 수동 정리 없이 catchup 타이머 삭제를 관측하는 안으로 승인 질문(미응답). 아직 원격 ref 안 씀. timer active/waiting, 최근 catchup 17:20:51 rc0.
  - **다음 결정/승인**: ① `test_branch_prune` 및 기존 `test_autodispatch` checks.json 등록 질문 미응답(목록 미수정) ② 위 복원 push 승인 후 catchup 실제 삭제·보존 ref·#778 노트·저널 관측 ③ 검증한 회귀 변경 커밋·push·배포 승인. ⑺ 전진 직후 실제 운영 삭제는 다음 승인된 전진에서 관측 필요. #787 노트에 상세 결과 기록·되읽기. #788 신규·미착수.

- **직전 체크포인트: 2026-10-10 17:20 KST · Codex · #782 재검증·CLI 설명 보완 · #787 후속 확인 · 통합 검사 통과, 커밋 미승인**.
  - **저장소**: main, HEAD = origin/main `20eeaa4`. 미커밋 6파일: 이 인계서, `master/context_synth/{prompt.py,synth.py,__main__.py}`, `master/test_context_synth.py`, `master/test_pydigest.py`. 코드 4파일은 Claude 결과 인수, `__main__.py`는 로컬 전용 상한 설명 한 줄 추가. 커밋·push·배달·재기동·실제 LLM·재합성 미실행.
  - **지휘**: 사용자 「#782·#787 이어서 시작」에 따라 마스터 담당 `codex`로 기록·되읽기(17:10). 워커 전역 `codex`·출처 state 재확인, 변경 없음. 기존 로컬 서브 에이전트 방식으로 읽기 검토와 CLI 설명 보완 완료; 실행 중 에이전트 없음.
  - **검사**: 합성 235/235 · pydigest 24/24 · 병렬 합성 25/25 · 브랜치 정리 55/55 · diff check 통과. 정본 통합은 **샌드박스 밖에서 29모듈·1,468개 검사, rc0(54.297초)**.
    기본 샌드박스 재실행은 source_scope 28/32 실패: gitea 그룹 누락 → `sg`의 `Cannot open audit interface - aborting.` → `_expand_gitlinks`가 조회 실패를 빈 포인터로 읽어 「포인터 없다」로 표시. 같은 검사는 승인된 샌드박스 해제 후 32/32. 관련 3파일은 HEAD와 동일, 진단 패치 없음. 실패·정정은 #782·#787 노트에 기록·되읽기.
  - **#782 남음**: 검증한 미커밋 변경의 커밋 승인. `ax-projects` 확인한 즉시 import 경로에서는 synth import를 찾지 못함(전체 전이 import·실제 sys.modules 미확인), 필수 재기동으로 단정하지 않는다. 조사표는 이미 #782 노트에 있음; 후보 상한 변경은 미승인.
  - **#787 남음**: catchup 운영 로그 16:49:47·17:00:16에 정리0·예외0 관측(실제 대상 브랜치 자동 삭제 성공은 미실증). 비마운트 ModularStage·NS·MotionForge 가드 재설치 미실행; 정본 `master.work.attempt install-hook <프로젝트>` 확인. `test_branch_prune`의 checks.json 등록 질문 미응답, 목록 수정 없음. `drain(catchup=True)→sweep_terminal` 배선 검사는 현 테스트에 없으며 대상 확대 없이 새 검사를 추가하지 않았다.
  - **다음**: #782 커밋 승인 · #787 통합 검사 등록 및 비마운트 가드 정비 범위 결정 · 다음 종결/전진에서 자동 삭제 실관측. #788은 신규·미착수 그대로.

- **직전 체크포인트: 2026-10-10 17:04 KST · Claude · 사용자 토큰 부족으로 종료 — #782 서브 에이전트 실행 중 · #788 등록만**.
  - **저장소**: main, HEAD = origin/main `20eeaa4`(16:55 인계 커밋). 배달 출처 `993ec41`(문서 커밋만 뒤 — check 는 다음 코드 커밋 뒤 update 로 맞춘다).
    🔴 **#782 로컬 서브 에이전트는 끝났다(17:0x) — 결과는 미커밋 diff 4파일 · 내가 재실행: test_context_synth 통과 235·실패 0 · test_pydigest 24/24 · 조사표는 #782 노트** — 대상 `master/context_synth/synth.py`·`prompt.py`·(`__main__.py`)·그 테스트.
    지시: 커밋·push·배달·재기동·실제 재합성·LLM 호출 금지. 결과 보고는 이 세션에만 온다 → 이어받는 쪽은 **작업 트리 dirty diff 로 인수**하고
    검사를 직접 다시 돌린다(context_synth 테스트 전부). [주의] `ax-indexer` 는 작업 트리를 그대로 실행하므로 미커밋 변경이 다음 색인에 쓰인다.
    이 체크포인트 갱신은 미커밋(사용자 「작성」만 지시).
  - **#782 「진행」**(합성 4,000자 상한) 사용자 결정: ① 레인별 프롬프트 — 클라우드(agy·codex)는 상한 없이 원본, 로컬(gemma)은 종전 4,000자+요약본,
    종류별 1회만 빌드 ② 재합성은 새 push 부터만(일괄 재생성 없음) ③ 같은 부류 상한 넷(recipes_synthesizer 4,000/2,500 · review_runner DRAFT_MAX_CHARS 4,000 ·
    plan_register 합산 4,000 · review_gen.commit_diff 24,000)은 **조사만** — 어느 모델로 가는지·왜 있는지 표로 #782 에 남기고 클라우드행만 갈래를 묻는다.
    다음: 서브 에이전트 diff 재검증 → 커밋 승인 → (`ax-projects` 상주가 synth 를 import 하면 재기동 필요 여부 확인) → 조사표 노트.
  - **#788 「신규」(높음) — 등록만, 미착수**: 클라우드 1차(제미나이 agy → 코덱스 → 클로드 맨 뒤) · 로컬은 **클라우드 전부 한도 소진일 때만** 폴백
    (형식·사실 거부는 다른 클라우드로만, 모두 거부면 실패 기록) · 적용: 컨텍스트 합성·레인 모드 본문·온톨로지 합성 ·
    로컬 결과에 「재검증 필요」 표시(문서 frontmatter / 조각 기록·이슈 노트) → 한도 회복 뒤 주기 작업이 클라우드로 재작업하고 표시 해제.
    [주의] 2026-09-06 「claude 는 작성 체인 밖」을 뒤집는 결정이다. 사용자: 「사용하다보니 로컬 LLM의 장점을 크게 못느끼겠어」.
    선행: #782 가 같은 synth.py 를 고치는 중 — 그 뒤에 얹는다. 먼저 레인별 「한도 소진 vs 일반 실패」 판정 유무 확인.
    현황(코드): synth.py:69 agy→gemma4:e4b→codex→gemma3:12b · lanes.py:73 codex→agy→qwen2.5-coder:14b · ontology/synth.py:59 로컬 35B(상주 제거됨)가 기본.
  - **#787 「진행」·그 밖**: 16:55 체크포인트 그대로(자동 경로 실관측 전 · 다른 3 프로젝트 가드 stale · checks.json 등록 미정).
    #777·#781·#786 완료. 남은 결정: 정본 ⑤·CLAUDE.md 「제미나이·로컬 LLM 까지 써서」 문구(#784·#788 과 어긋남, CLAUDE.md 는 동의 후) ·
    #774 정정 3곳 · `.2` codex `127.0.0.1:8000/mcp` 오류 · `test_mount_gate.py` rc1(기존) · 기존 일감 #757 · #726 · #771 · #768 · #763(마지막).

- **직전 체크포인트(같은 세션): 2026-10-10 16:55 KST · Claude · #787 배포·잔존 정리·finalize 수정 · #777 축 main 반영(87ea5dc) · #777·#781·#786 완료**.
  - **저장소**: main, HEAD = origin/main `993ec41`. 이 세션 커밋(모두 사용자 승인 후 커밋·push): `5e3cbce`(#780) · `1da730e`(#783·#784·#785) ·
    `5dfd2b2`(#787 + 16:45 인계) · `87ea5dc`(finalize 머지, 파이프라인) · `993ec41`(#787 finalize 수정). 이 체크포인트 갱신만 미커밋(커밋 지시 없음).
    배달 `update` 마지막 rc0 · 3/3 · 출처 `993ec41`. 진행 중 work 0. 원격 heads = `main` 하나. 서브 에이전트 실행 중 없음.
  - **지휘 상태**(변경 안 함): 마스터 담당 기록 `claude`(10-06) · 워커 전역 모드 `codex`(10-09 22:58).
  - **#787 「진행」**(브랜치 자동 정리, 사용자 「절차에서 자동으로 정리했어야지」):
    - `5dfd2b2`: catchup 이 rejected/cancelled work 의 `task/<W>/*` 를 지운다(큐 재확인 · 로컬 `refs/ax/pruned/` 보존 · force-with-lease · 저널+이슈 노트에 ref·tip) ·
      ⑺ 전진 직후 머지한 서브 브랜치 삭제 · pre-push 가드 예외 둘(자기 base 에서 닿는 서브 브랜치 / 정리 코드가 넘긴 종결 work 하나) ·
      워커 체크아웃 `fetch.prune=true`(배달·check) · wcommit `fetch --prune` · 큐 종결 노트 문구 수정. CLI `python -m master.work.cleanup terminal|merged-subs [--apply]`(기본 미리보기).
    - 배포: 배달 3/3(fetch_prune 완료) · AXCluster 마스터 클론 가드 재설치(state ok) · `ax-task-queue` 16:48:57 재기동.
    - 잔존 정리(수동 CLI): #777 3 · 1차 3 삭제(#778·#781 노트) · 2차 r1 2 삭제 · `.33` `fetch --prune` 으로 stale 추적 참조 14개 정리.
    - **결함·수정 `993ec41`**: 전진 뒤 서브 브랜치를 지우자 finalize 가 「durable 이 origin 에 없다 — 통째 중단」(push 0). 사용자 갈래 1 —
      작업 브랜치에 제목이 정확히 `[ADVANCE] <work>: <durable>` 인 머지 커밋이 있으면 전진분으로 인정, 없으면 종전대로 중단.
    - 남음(닫지 않은 이유): ① 자동 경로(catchup sweep · advance 직후 삭제) 실관측 전 ② ModularStage·NS·MotionForge 마스터 클론 가드 stale
      (비마운트라 재설치 안 함 → `test_onboard` 라이브 1건 79/80) ③ `test_branch_prune` 을 `tests/integration/checks.json` 에 넣을지 미정.
  - **#777 축 종결**: 2차 재실증 work `20261010_1613_777_2_2_mkdtemp_783784785_94b9e4c3` ⑺ 전진 `5ab51fa` → finalize main `87ea5dc`
    (전진분 2건 인정 · base 자동 삭제 · #786 「완료」). test_recipes_read 42/42 · test_stale_unknown 27/27 · /tmp/tmp* 5→5.
    #777 · #781 사용자 지시로 「완료」. 전진·검수 트리 `/home/sim/ax-advance-<work>` · `/home/sim/ax-review-<work>` 는 남아 있다(파이프라인 소유).
  - **남은 결정·미수행**: #782(합성 4,000자 상한) 갈래 · 정본 ⑤·CLAUDE.md 「제미나이·로컬 LLM 까지 써서」 문구(#784 와 어긋남, CLAUDE.md 는 동의 후) ·
    #774 정정 3곳(「not logged into Antigravity 도 사라졌다」 — #774 노트·`831ed14`·인계서) · `.2` codex 로그 `127.0.0.1:8000/mcp` 연결 오류 미조사 ·
    `test_mount_gate.py` rc1(HEAD 에서도 동일) · 기존 일감 #757 · #726 · #771 · #768 · #763(마지막).

- **직전 체크포인트(같은 세션): 2026-10-10 16:45 KST · Claude · #780 축 종결(드라이런 2회로 실전 확인) · #787 브랜치 자동 정리 진행 중(로컬 서브 에이전트 2)**.
  - **저장소**: main, HEAD = origin/main `1da730e`. 이 세션 커밋(모두 사용자 승인 후 커밋·push): `5e3cbce`(#780) · `1da730e`(#783·#784·#785).
    배달 `update` 마지막 rc0 · 3/3 · 출처 `1da730e`. 훅 재설치(`ax-install-hook --apply`) rc0 · 4개 프로젝트. `ax-task-queue` 15:37:25 재기동(5e3cbce 반영).
    [주의] **#787 서브 에이전트 2개가 작업 트리를 고치는 중**(미커밋): A = `master/work/review.py`·`cleanup.py`·`pre_push_hook.sh`(+필요 시 task_queue·autodispatch),
    B = `master/client/**`·`client/**`·`wcommit.py`/`subbranch.py` fetch. 둘 다 커밋·배달·실제 브랜치 삭제·훅 재설치 금지로 지시했다.
    [주의] `ax-dispatch` 는 작업 트리를 그대로 실행한다 — 미커밋 변경도 다음 파견에 쓰인다.
  - **지휘 상태**(변경 안 함): 마스터 담당 기록 `claude`(10-06) · 워커 전역 모드 `codex`(10-09 22:58, state).
  - **#780 「완료」**(+하위 #783·#784·#785 「완료」, 사용자 지시): 원인·결정·실측은 이슈 노트. 요지 —
    - 층2 선언부 글자 예산 제거(클라우드 판정에 상한 없음 · 로컬 LLM 6,000자 예산은 유지) · 선언부는 조각 대상의 import 에서만, 가져다 쓴 이름만.
    - **실측: agy 는 `--add-dir` 1M자 파일까지 정확히 읽었다(16K~1M 5/5)** — 「GET 이라 글자 제한」은 근거 없음(기록에도 없었다).
    - 워커 지시문(두 사본 글자 동일): 스킬·설정 경로 명시(#783 — `.agents/` 가 git 제외라 rg 0건 → 지휘자 BLOCKED 였다) ·
      **본문은 지휘자가 직접 쓴다, 본문 초안 위임 금지**(#784 — 사용자 결정) · 조사 위임은 필요할 때만 · agy 절대 경로 `--add-dir`·5분 상한.
    - **마운트가 AXCluster 일 때만** 지시문 끝에 사실 문장(SELF_REPO_NOTE: 이 체크아웃의 AGENTS.md·CLAUDE.md 는 대화형 마스터 세션용, 검색 0건은 실패 아님) —
      원인: 배달된 AGENTS.md 의 「실패는 보고하는 자리」를 무인 워커 codex 가 rg exit 1 에 적용했다(.43 rollout 01a1248d 확인).
    - 조각 terminal 실패 즉시 work 이슈 노트 + 저널(다른 조각은 계속).
    - push 훅이 `task/<W>/base` push 에서 파견 신호를 즉시 쓴다(#785, 종전 색인 소비자 뒤에서 약 3분 대기 — 첫 진단 「물러난 소비자」는 틀렸고 정정함).
  - **드라이런 결과**: #777(03:37) 11분·커밋 0 → 1차(15:39) 약 19분·1조각 재시도 → **2차(16:14) push→종결 1분 17초 · 2/2 · 재시도 0 · 위임 0 · 층2 APPROVE 2건**
    · 지휘자 입력 토큰 116만/50만 → 22만/23만.
    - 2차 work `20261010_1613_777_2_2_mkdtemp_783784785_94b9e4c3`: **⑺ 전진 완료** `4274177`→`5ab51fa`(사용자 「이상 없어, 전진시켜」 · 통합 29/29 · /tmp/tmp* 5→5) ·
      이슈 #786 에 전진 노트 · `ready_for_review` · **finalize(main 머지) 미지시**. 전진 트리 `/home/sim/ax-advance-<work>` 남아 있음.
    - 1차 work `…1538_777_2_mkdtemp_780_c88dcb7f`: 사용자 지시로 `cancelled` · #781 노트(상태 미변경). #777 work 는 `rejected`.
    - [주의] 전진 첫 시도의 「TESTS FAILED 4」는 내 스크립트가 `Path(".venv/bin/python").resolve()` 로 시스템 파이썬을 넘긴 탓이었다(코드 결함 아님).
  - **#787(높음, 진행 중)** — 사용자: 「절차에서 자동으로 정리했어야지」. 결정: ① rejected/cancelled work 의 `task/<W>/*` 자동 삭제(ref·tip 기록, pre-push 가드 예외는 그 work 하나로 좁게 —
    「미병합은 사람 몫」을 이 경우에 한해 뒤집음) ② ⑺ 전진 직후 머지한 서브 브랜치 삭제 ③ 워커 클론 `fetch.prune`(.33 `git branch -r` 17개 vs 원격 10개 — #740·#772 잔재)
    ④ 고친 경로로 잔존 8개 정리(#777 3 · 1차 3 · 2차 서브 2; 2차 base 는 finalize 때).
    다음: 서브 에이전트 결과 직접 재검증 → 커밋 승인 → 배달·가드 재설치 → 잔존 정리(미리보기 후) → .33 읽기 확인.
  - **새 일감**: [#782](http://192.168.0.57:8080/issues/782) 합성 4,000자 상한이 agy 합성에도 걸림(로컬 보드 예산 잔재, `context_synth/prompt.py:35`) — 갈래 결정 대기.
  - **남은 결정·미수행**: 2차 work finalize 여부 · #781 닫기 · #782 갈래 · 정본 ⑤·CLAUDE.md 「제미나이·로컬 LLM 까지 써서」 문구 정리(#784 와 어긋남, CLAUDE.md 는 동의 후) ·
    #774 정정 3곳(「not logged into Antigravity 도 사라졌다」 — #774 노트·`831ed14`·인계서) · `.2` codex 로그 `127.0.0.1:8000/mcp` 연결 오류 미조사 ·
    `test_mount_gate.py` rc1(HEAD 에서도 동일, 기존 실패) · 남은 기존 일감 #757 · #726 · #771 · #768 · #763(마지막).

- **직전 체크포인트: 2026-10-10 03:50 KST · Claude · #774 실전 확인용 분산 작업(#777) 실패·강제 종료, 심각 일감 #780 등록 — 사용자 취침으로 종료**.
  - **저장소**: main, HEAD = origin/main `75f3580`. 이 체크포인트 갱신만 미커밋이다(커밋 승인 없음 — 사용자가 「작성」만 지시).
    배달 마지막 rc0 · 3/3 · 출처 `75f3580`. 진행 중 파견 0(03:48 강제 종료 확인).
  - **#777 분산 작업 — 실패**(사용자 지시 「#774 실전 확인용으로 분산 작업 하나 돌려보자」 → 내용은 사용자가 「#776 후속 — 테스트 2개
    임시폴더 정리」 선택): Redmine #777(인프라) · 분산 work 이슈 #778 · work `20261010_0335_777_2_mkdtemp_774_5078e6e6`.
    골조 `cfd986a`(`[DOC]` 3 · `[PSEUDO]` 3, 게이트 통과, 사용자 승인 후 base push 03:37:31). 조각 2개 병렬 · 지휘자 codex.
    - `.2` `b33b3851`(test_stale_unknown): 구현 완료(codex rc0 213초 · agy 중계 rc0 134초 · 입력 133만 토큰)인데
      **층2 `grounding_incomplete` → wcommit BLOCKED → failed**(03:41:25, 재시도 없음).
    - `.43` `7118f80b`(test_recipes_read): agy 1번째 호출 약 125초 · 응답 5,404B(**갈래 A 효과 확인 — read-only 오류 0, 로그 파일 정상 생성**).
      2번째 호출이 7분 넘게 끝나지 않아 **사용자 지시 「그냥 꺼」로 03:48 원격 codex·agy 강제 종료** → failed · work `rejected`.
      [주의] 강제 종료 때 `pkill -f "codex exec --json"` 이 SSH 셸 자신과도 맞아 rc255 가 났지만 대상은 모두 죽었다(재확인 0개).
    - 두 워커 모두 `main` · 추적 파일 변경 없음(확인). 조각 서브 브랜치·base 브랜치는 원격에 남아 있다(정리 안 함 — 사람 몫).
      골조 worktree 가 `scratchpad/ax-777-base` 에 남아 있다(`git worktree list`) — 스크래치가 지워지면 `git worktree prune` 필요.
  - **층2 차단 원인 — 재현으로 확정**: `declarations.from_commit(..., "cfd986ad0e", per_class=16000)` 가 두 조각 모두 `complete=False ·
    truncated=['client/runtime/client_mcp.py']`(101,811B). 선언부가 조각 대상이 아니라 **work 골조 파일 전체와 그 import** 를 모은다.
    잘림 1개로 `infer.py:1090` 이 판정 생략 → fail-closed 차단. 저널에는 잘린 파일명이 안 남는다.
  - **새 일감**: [#779](http://192.168.0.57:8080/issues/779) 느림 측정(보통) ·
    [#780](http://192.168.0.57:8080/issues/780) **높음** — 층2 grounding 잘림 전 조각 차단 · agy 위임 시간 상한 없음 ·
    `--add-dir` 상대 경로(agy 로그: `must be an absolute path` — ax-work 스킬 호출 모양이 상대 경로) · 실패 뒤에도 다른 조각 계속(무알림).
    사용자 반응: 「이따위로 처리하는게 어디있어」. 갈래는 #780 에 기록만, **결정 대기**.
  - **codex 는 스킬을 무시하지 않았다 — 글자 그대로 따랐다**(.43 rollout `01a121f4` · #780 노트): 03:37:58 `ax-work` SKILL 을 읽고,
    §4 「조사·분석은 agy 먼저」로 몇 줄 수정에 agy 2회(약 2분12초 · 6분10초), 중계용 「15분」 대기를 직접 호출에 적용,
    스킬 예시의 상대 `--add-dir` 사용. 03:47:32 구현 완료 보고 직후 강제 종료됐다. 「`main` 에서 구현」 이라고 보고 — 실제 브랜치 미확인.
    → 고칠 곳은 지휘자가 아니라 **스킬·파견 지시문**(#780).
  - 🔴 **정정 필요(미수행)**: #774 갈래 A 의 「not logged into Antigravity 도 사라졌다」는 **틀렸다** — 사전 측정 때 stderr 만 봤고
    agy 로그 파일에는 그때도 50줄 있었다. 이 서술이 #774 노트 · `831ed14` 커밋 주석·메시지 · 아래 03:31 내용에 남아 있다.
  - **#774 상태**: 「진행」 유지. 갈래 A(쓰기 허용)는 실전에서 효과 확인. 「종료 코드 0」 저널 줄은 조각이 끝나지 않아 미확인.
    갈래 D(모두 실패 시 BLOCKED)는 미관측. 노트는 이번 실전 결과를 아직 안 남겼다.
  - **그 밖에 이 세션(02:10~03:50) 진행분**: 아래 03:31 내용 그대로(#772·#775·#776 종결 · #774 A `831ed14` · D `c5a038f`).
  - **다음 작업**: #780 갈래 결정(층2 범위·상한 / agy 시간 상한·절대 경로 / 실패 전파) → 정정 3곳 → #774 실전 재확인.
    #777 은 열린 채로 둠(재시도는 #780 해결 뒤). 남은 기존 일감: #757 · #726 · #771 · #768 · #763(마지막).

- **직전 체크포인트(같은 세션): 2026-10-10 03:31 KST · Claude · #772·#775·#776 종결, #774 갈래 A·D 반영·배포 (실전 확인 대기)**.
  - **저장소**: main, HEAD = origin/main `58810f2`(#776). 이 세션 커밋: `f254b95`(02:04 인계·docs 12/15) ·
    `831ed14`(#774 A) · `5bb86ea`(02:54 인계) · `c5a038f`(#774 D) · `3a727cc`(03:11 인계) · `802846b`(#775) ·
    `7e1226c`(03:22 인계) · `58810f2`(#776). 모두 사용자 승인 후 커밋·push. 배달 `update` 마지막 rc0 · 3/3 · 출처 `58810f2`. 이 문서 갱신은 미커밋이며 커밋 승인은 아직 없다
    (커밋하면 배달이 한 칸 뒤처진다 — 배달은 지시 때만).
  - **지휘 상태**(02:10 조회, 변경 안 함): 마스터 담당 기록 `claude`(10-06) · 워커 전역 모드 `codex`(10-09 22:58).
    직전 세션은 Codex였지만 담당 기록은 갱신되지 않았다 — 교대 지시가 없어 그대로 두었다.
  - **#772 「완료」**(사용자 지시): main 머지 `2dc6d23`·배달 3/3·`ax-projects` 01:50:10 재기동·통합 1,277건을
    결과 노트로 남기고 닫았다. 되읽기 확인.
  - **#774 조사 결과**(근거: .43 codex rollout 사본 `~/ax-state/usage/raw/AXCluster/192.168.0.43/codex/sessions/2026/10/09/rollout-…01a1210e….jsonl`):
    `.43` 지휘자는 `codex exec -s workspace-write` 라 홈이 읽기 전용 → agy 가 `~/.gemini/antigravity-cli` 쓰기 실패를
    반복하며 응답을 못 냈다. rc130 은 codex 가 약 2분 8초 뒤 Ctrl-C 로 끊은 것. #764 의 샌드박스 밖 중계는
    Windows(`uses_session1`)에만 있어 Linux 는 직접 호출 — 10-09 `.43` 직접 호출 3/3 실패, `.2`·`.33` 중계 3/3 성공.
    「실패 뒤 직접 구현」은 파견 지시문(*"If a delegation fails … it is not a reason to stop"*)대로였다.
  - **#774 갈래 A 반영**(사용자 결정 · 로컬 서브 에이전트 · `831ed14`): Linux 이고 `facts.home` 이 있을 때만
    codex 명령에 `sandbox_workspace_write.writable_roots=["<home>/.gemini/antigravity-cli"]`. Windows·home 미상·
    claude 모드 무변화. 사전 실측(.43, 같은 명령): agy SUCCESS 12.5초 rc0, read-only 0건, 「not logged in」 소멸.
    `test_runner` 200/200 · 통합 28모듈 rc0(서브 에이전트 보고, 단위 검사는 직접 재실행).
    배달 `update` rc0 · 3/3 · 출처 `831ed14`. `ax-dispatch` 는 oneshot 이라 재기동 없음. Redmine #774 「진행」 + 노트.
  - **#774 갈래 D 반영**(사용자 결정 「위임 실패 시 BLOCKED」 → 이어서 「다음 레인 허용, 다 실패하면 BLOCKED」 ·
    로컬 서브 에이전트 · `c5a038f`): **10-09 `#764` 의 「위임이 실패해도 멈추지 않는다」를 뒤집었다.**
    파견 지시문 `runner.py` INSTRUCTION 과 세션 1 사본 `client/runtime/session1_conductor.py`(글자까지 같음 — 직접 대조):
    시도한 위임 실패(rc≠0 · 시간 초과 · 빈/쓸 수 없는 응답) → 레인 순서상 다음 활성 백엔드로 넘어갈 수 있다 →
    시도한 백엔드가 **모두** 실패하면 직접 구현하지 않고 원응답 보존·백엔드별 종료 코드·오류 기재 후 `RESULT: BLOCKED`.
    비활성 백엔드는 실패가 아니다. `ax-work` SKILL §4 와 97행 레인 순서 아래 한 줄도 같은 뜻.
    `test_runner` 211/211(직접 재실행) · test_client_bundle 468/468 · test_orchestration_control 27 OK ·
    통합 28모듈 rc0(서브 에이전트 보고). 배달 3/3(ax-work 스킬 갱신 포함). Redmine #774 노트·되읽기.
    [주의] BLOCKED 조각은 큐가 자동 재시도하지 않는다(`submit_fail` 은 `quota_exhausted` 만 살린다 — `revise.py` 서술).
  - **#775 「완료」**(사용자 지시로 등록 → 갈래 2 · 로컬 서브 에이전트 · `802846b`): `test_residency` 143/144 거짓 실패.
    원인 — `d0bf674`(#655) 이후 `deliver` 는 해시 캐시 래퍼이고 본체는 `_deliver` 인데 검사가 `deliver` 소스만 문자열로 봤다.
    수정: AST 호출 검사 두 단계(`deliver`→`_deliver`, `_deliver`→`refresh_residency(facts)`) → 145/145.
    `tests/integration/checks.json` 에 등록 → **정본 통합 29모듈** OK(둘 다 직접 재실행). 격리: connect 0 · 쓰기 /tmp 뿐
    (서브 에이전트 strace). 배달 3/3. 노트 남기고 닫음(인프라 일감 · 마스터가 닫는다).
  - **#776 「완료」**(사용자 지시로 등록 → 갈래 1 · 로컬 서브 에이전트 · `58810f2`): `test_residency` 두 검사가
    `mkdtemp()` 루트를 안 지워 실행마다 `/tmp/tmp*` 2개가 남았다. `try/finally` + `rmtree` — 잠금 쥐는 검사는 핸들을 먼저
    닫고 지운다. check 줄 변경 0. 145/145 · 실행 전후 30→30(직접 재실행, 수정 전 30→32). 배달 3/3. 노트 남기고 닫음.
    남음(일감 없음): 기존 `/tmp/tmp*` 30개는 출처 미확인이라 그대로 · 다른 `master/test_*.py` 의 mkdtemp 6파일 미조사.
  - **다음 작업·보류**: #774 닫는 조건 — 다음 `.43` 실전 파견 저널의 `[지휘자] 위임: agy … 종료 코드 0`(갈래 A).
    갈래 D 의 BLOCKED 경로는 모든 백엔드가 실제로 실패해야 보이므로 미실증.
    그 밖에는 직전 체크포인트 그대로:
    #757 Unreal 실증, #726 lane 연결, #771 A·B 보류, #768, #763(마지막, 마운트 Unreal 전환 후).
    진행 중 work 0 · hold 없음(02:10 조회). 마스터의 Codex app-server 프로세스 3개(10-09 17:32~)는 그대로 두었다.

- **직전 체크포인트: 2026-10-10 02:04 KST · Codex · #772 수정 main 반영, #773 마감, 배포·재시작·검사 완료**.
  - **저장소**: main, HEAD = origin/main `2dc6d23a2f8af2b6d588e157ce39feb4da3d0e94`.
    문서 갱신 전 트리 clean. 이번 문서 변경은 미커밋이며 문서 커밋·푸시 승인은 아직 없다.
  - **사용자 승인**: AX 워커 분산 방식, 골조 커밋·푸시, 실패 후 검증 재개, 「좋아 머지하고 드라이런하자」로
    ⑺ 전진·main 마감, 「배포와 재시작해」로 update·ax-projects 재시작을 승인했다.
  - **#772 구현**: `ax-projects` 신선도 감시에 `master/work/register.py`를 명시적으로 추가.
    디렉터리뿐 아니라 단일 `.py` 파일의 mtime도 판정한다. `master/work` 전체 감시나 자동 재시작은 추가하지 않았다.
    `master/test_service_freshness.py` 26건, `tests/integration/checks.json`에 검사 등록.
  - **분산 결과**: work `20261009_2313_772_ax_projects_9a055113`, task `21a0637d`, .43 codex.
    골조 `07311a1` → 워커 `b7fd210` → base 전진 `d1f9a6a` → main 머지 `2dc6d23a`.
    기존 `review.finalize_work(confirm=True)`가 큐 `merged`·Redmine [#773](http://192.168.0.57:8080/issues/773)
    「완료」100% 기록과 도달 가능한 원격 작업 브랜치 2개 정리를 수행했다. #772 자체 상태는 이 기록에서 단정하지 않는다.
  - **운영 반영**: `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update` rc0,
    .2/.33/.43 배달·검사 3/3, 출처 `2dc6d23a`.
    `scripts/ax-service-restart ax-projects` rc0: 10-09 22:52:49 → 10-10 01:50:10 KST,
    `active/running`, `Result=success`. 신선도 `check()`에서 queue·broker·projects 모두 현재 코드.
    재시작 뒤 MCP `get_worker_mode_tool()` 정상 응답: `codex`, source=state,
    10-09 22:58:01 사용자 요청 전환. 마스터 담당 기록은 이번 갱신에서 재조회하지 않았다.
  - **검증 범위**: main 기준 머지 시뮬레이션 충돌 없음·게이트 통과.
    배포·재시작 후 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`
    rc0, **28모듈·1,277건 통과**. 배달 계획·파일 대조·프로세스 신선도·MCP 응답·통합 검사이며,
    배포 후 새 work를 등재해 워커 파견을 다시 실행한 것은 아니다.
  - **#757·#726 실전 근거**: 이번 조각 `[layer2]` APPROVE, backend=agy·writer=codex,
    grounding 2·baseline 2/2 파일. 사용량 session_id `01a1210e-7d39-7491-b34a-fa9c93d236d6`와
    회수 rollout의 `conductor_metrics` 일치: 22호출, 입력 861,839·출력 6,043·캐시 808,320·비캐시 53,519.
    이는 Python 공통 경로 실증이다. Unreal Slate 재실증·lane 모드 연결을 완료했다고 주장하지 않는다.
  - **남은 결함·정정**: .43의 agy 위임은 홈 캐시 쓰기 오류(rc130) 후 codex 직접 구현으로 완료.
    후속 [#774](http://192.168.0.57:8080/issues/774)에 기록했으며 위임 결함은 수정하지 않았다.
    지휘자가 없는 `ReviewResult.summary()`를 호출해 출력 단계에서 예외를 냈으나 실제 검수는 통과했다.
    사용자 지적 후 기존 머지 승인으로 계속 처리했다. 이 출력 오류를 새 머지 승인 대기로 인계하지 않는다.
  - **다음 작업·보류**: #774 위임 오류, #757 Unreal 실증, #726 lane 연결, #771 A·B 보류, #768.
    사용자 결정상 **#763은 다른 작업을 모두 끝낸 뒤 마운트를 Unreal 프로젝트로 전환해 진행**한다.
    이번 배포·재시작·검사 명령은 모두 종료했다. 전체 큐·hold 상태는 문서 갱신 시 재조회하지 않았다.

- **직전 체크포인트: 2026-10-09 22:55 · Claude · #769·#770·#695·#696·#766 종결, 리포트 102·103, #757·#726·#771(A0) 반영**.
  - **저장소**: HEAD = origin/main `c211789`(#771 A0) — 이 문서 커밋이 그 위에 올라간다.
    이번 세션 커밋: `ca395da`(직전 인계서) · `d6dabac`(리포트 101·102) · `efc72be`·`33964b4`·`36dea0d`·`7c46c11`·
    `d7c8592`·`346b646`·`333b293`·`fcf6794`·`c1bf9ba`(인계서) · `83fdaaa`(#770 수정) · `98a5e23`(리포트 103) ·
    `ae67e62`·`6ade843`(#757) · `2ecfc1b`(#726) · `c211789`(#771). 모두 사용자 승인 후 커밋·push.
    배달 `update`(마운트 AXCluster) 마지막 rc=0 · 3/3 OK · 출처 `c211789`
    — **이 문서 커밋 뒤에는 다시 한 칸 뒤처진다**(배달은 지시 때만).
  - **지휘 상태**: 마스터 담당 기록 `claude`(10-06) · 워커 전역 모드 `claude`(10-09 14:02) — 조회만, 변경 안 함.
  - **운영 변경**: `ax-task-queue` 재기동 11:14:07 → 20:22:55(서비스 신선도 3/3 OK, broker·projects 는
    변경 경로 밖이라 재기동 안 함). 배달이 세 워커의 폐지 스킬 `distribute`·`review-work` 를 정리했다(설계대로).
    `ax-projects` 재기동 21:00:39(옛 코드 정지 91초 타임아웃) · 21:01:36(수정 코드 정지 5초, 정상 종료).
    `ax-task-queue` 재기동 21:26:26(#757 반영, 신선도 OK). `ax-projects` 재기동 22:37:45(#726 반영, 정지 5.4초) · 22:52:49(#771 A0 반영).
  - **#769 완료**: 실 조회 `redmine_get_wiki_page("아이디어수집")` → 8101 200 · Redmine 404 —
    경로·`ax-cluster` 귀속은 동작. 페이지는 `modularstage` 위키에 있다(`docs/10-references.md:36`, 문서 근거).
    사용자 결정: 위키 안 옮김 · 실 쓰기·되읽기는 첫 실사용 때 확인 · #768 은 일감 본문이 정본(댓글 기록).
    [주의] `CLAUDE.md` 작업 흐름 표·`docs/10` 의 「아이디어 = 위키 절 + 이슈」 서술은 그대로다 — #768 한 건의
    결정으로 이해했고, 규칙 변경 여부는 사용자에게 물었으나 답 없음.
  - **#770 완료**(등록·조사·수정 모두 사용자 지시): 9월 이후 `ax-projects` 재기동 70회 중 65회가 90초 SIGKILL.
    원인 — Claude Code 2.1.295(MCP 2026-07-28)가 `subscriptions/listen` POST 를 SSE 로 세션 내내 열어 두고
    SDK(mcp 2.0.0)가 종료 때 끝내지 않아 uvicorn(0.52.1)이 무한 대기. 스크래치 포트 재현으로 확정(실제 앱·최소
    서버 둘 다 100초+). 수정 `83fdaaa`(로컬 서브 에이전트 · `timeout_graceful_shutdown=5` + `[shutdown]` 로그) ·
    통합 25모듈 1,199건 · 운영 실측 정지 5초 `Deactivated successfully`. 종료 때 CancelledError 트레이스 1건은
    예상된 동작. SDK 상류 보고(갈래 ③)는 안 했다. 근거 전부 #770 노트.
  - **#757 부수 결함 수정**(사용자 결정 ① 취소 사유 구분 · 로컬 서브 에이전트): 조각 하나 취소가 work 를
    `cancelled` 로 닫아 finalize·`improve_work` 를 막던 문제. 취소에 `requester_handoff`(요청자가 ⑦ 에서 맡는다)
    추가 — 그 취소는 `no_work` 처럼 세어 `ready_for_review` 로 간다 · 큐 로그 `[handoff]` · 공지에 별도 절 ·
    `no_work` 와 동시 지정은 400. 호출: `runner.cancel(task_id, reason=…, requester_handoff=True)`.
    새 `test_requester_handoff`(21건)를 `checks.json` 에 등록 → 정본 통합 **26모듈 1,220건**.
    미확인: 400 HTTP 실경로 · 실제 플래그 취소 실증(다음 분산 work).
  - **#757 본건 수정 — 열어 둠(사용자 결정)**: 갈래 A(로컬 서브 에이전트) `6ade843` — 층2 에 대상 파일의 기준(골조)
    원본을 「BASE VERSION」 절로 싣고 「바뀐 부분만 판정 · 원본에 있는 관용구는 지적 금지」 지시(층1 의 `baseline`
    재사용, 신규 파일은 제외). 저널에 `[layer2] <task> 판정 … · backend=… · 작성=… · 그라운딩 … · 원본 k/m파일`
    · 생략 시 사유. 통합 26모듈 1,236건. 실제 agy 재현(당시 입력·선언 4개): 수정 전 1/2 오탐(5건) → 수정 후
    2/2 APPROVE. **판정 드라이런**(사용자 지시 최소안 · agy 11회 · 과거 층2 판정 7건 전부, 실제 파견과 같은 함수로 입력):
    오탐 조각 APPROVE 3/3(누계 5/5) · 기존 승인 6/6 유지(.py 3건 포함) · 진짜 오류 주입 2종(세미콜론·미선언 식별자)
    2/2 정확 검출. verifier 클로저·`[layer2]` 저널 줄은 지나지 않았다. 층2 는 `ax-dispatch`(oneshot)라 재기동 불필요. **다음 실전 파견의
    `[layer2]` 로그로 효과를 확인한 뒤 닫는다.**
  - **리포트**: 102(10-09 낮 Claude 세션 #762·#764·#740·#767 — 인계·레드마인 노트로 작성) · 101 후속 절 추가 ·
    103(#770 — 규모·가설 소거·실제 요청 확보·재현·수정·운영 실증).
  - 🔴 **정정 — #695 「finalize 거절 예상」 보류는 낡은 서술이었다**: work `20261009_0051_motionforge_aac50fe6`
    은 **10-09 01:23 이미 main 머지**(`35c4d78`, Reviewed-by Simkung) · #756 완료 · 런타임 크래시 수정 `6b59bf5`
    (Gitea ls-remote·Redmine #756 으로 확인). 01:30 체크포인트가 `.33` 의 마감을 몰랐다. `cancelled` 게이트를
    어떻게 통과했는지는 미확인 — 직전 01:20:54 마스터 루프백 PATCH 가 있으나 본문이 로그에 없다.
  - **#695·#696 완료**(사용자 결정 갈래 ① — 닫고 남은 것은 새 일감): #695 는 타입별(unreal/code) 분산 작업
    실증(MotionForge `35c4d78`·AXCluster `5d9a35b`)으로 종결. #696 은 10-09 실전 층2 판정 7회 + 사용량 기록
    `source=layer2` 7줄로 종결. 남은 C++ 서브모듈 2단계는 전제가 바뀌어(Kimodo → MotionForge `unreal`, 소스 경계에
    webui·scripts `.py` + 서브모듈 `vendor/kimodo.cpp`) **#771**「Unreal 프로젝트 안 혼합 소스 조각 파견」로 등록(미착수).
  - **#766 완료 — 과다가 아니라 집계 방식**(사용자 결정 D): 마스터에 복사된 codex rollout 원본
    (`~/ax-state/usage/raw/AXCluster/<host>/codex/sessions/…`)으로 측정 — 기록 입력 87만~317만은 호출마다 맥락 전체를
    다시 보낸 합(호출 22~49회 · 맥락 2만→6~9만 · 캐시 92~97%). **새 입력은 조각당 7.1만~8.6만.** 첫 호출 1.8~2.2만
    (자동 로드 문서 가설 불일치) · .33 49회는 agy 대기 폴링. 한도에서 캐시 반영 방식은 미확인.
  - **#726 반영 — 열어 둠(실전 확인 전)**: 사용자 결정 (가) 읽을 때 잇기 · 로컬 서브 에이전트 · `2ecfc1b`.
    codex `thread.started` id 를 파견 기록 `session_id` 로(사전 확인: .2 세션1 out.txt id = rollout 파일 id) ·
    `[usage]` 줄에 비캐시·캐시(%)·세션 · `session_usage.conductor_metrics`/`find_rollout` · `/usage` 비캐시/캐시 열 +
    「지휘 세션」 표(사본 없으면 「미수집」). 실측 rollout 3건에서 #766 손 측정값 전부 재현. 새 `test_conductor_metrics`
    등록 → 통합 **27모듈 1,251건**. 중간 실패: `test_usage_page:109` colspan 기대값 → 보고 후 승인 수정(6→8).
    미확인: 실전 파견의 `session_id` 기록 · lane 모드(`host=local`) 연결 · 「읽은 파일 목록」 은 범위 밖.
  - **#771 A0 반영 — A·B 보류, 열어 둠**(사용자 결정 · 로컬 서브 에이전트 · `c211789`): 등재 게이트
    (`register._check_targets`, 등록·개선요청 공통)가 ① `kind: unreal` 의 `.py` 대상을 거절(층2·⑦ 언어별 판정 전까지)
    ② 서브모듈 경로(config `source.submodules` ∪ 미러 `.gitmodules`) 아래 대상을 거절. 실경로 판정: Kimodo webui `.py`·
    `vendor/kimodo.cpp` 거절, 에디터 모듈 `.cpp` 통과. 통합 27모듈 1,251건. 재기동은 `ax-projects`(등재가 8103 에서 돈다).
    정정: MotionForge config 에 `submodules` 는 이미 있었다(갈래 정리 때 「없다」 는 출력 잘림 탓 오판).
    관찰(미수정): `service_freshness` 의 `ax-projects` 감시 경로에 `master/work` 가 없어 `register.py` 만 바뀌면 재기동
    필요를 못 알린다.
  - **남은 것**: #757·#726 실전 확인(다음 파견의 `[layer2]`·`[usage] … 세션` 줄) · #771 A·B(보류) · #763·#768 열림. 이번 세션(20~21시)의 기록은 리포트 101
    후속 절과 103, 그리고 이 체크포인트다(#757 수정은 레드마인 노트). 진행 중 work 0 · 보류(hold) 없음.

- **직전 체크포인트: 2026-10-09 20:08 · Codex · #769 커밋·푸시 완료·최종 인계**.
  - **저장소**: main, HEAD/origin 추적 참조 `40c1012271cd5a20b147d6f95a04cd0b4462905b`.
    사용자 「응 그리고 인수인계서 작성해줘」 승인으로 코드·테스트·스킬10파일과
    보고서101·색인·인계3파일 총13파일 커밋·origin/main 푸시 완료(rc0).
    원격 main `65c33d1→40c1012`, 색인 이벤트1건 큐잉 확인(색인 완료는 미조회).
    푸시 직후 트리 clean 확인. 최종 해시·결과를 덧붙인 **이 문서만 미커밋**으로 남긴다.
    후속 문서 커밋·푸시·운영 배포 승인은 아직 없다. 커밋 연결은 Redmine #769에 기록·되읽기.
  - **구현**: 위키 조회·append/replace, 기존 본문·부모 보존, 버전 충돌 거부, 저장 후 되읽기.
    기존 ax-client→8101→redmine 경로와 프로젝트 태그 계약을 사용.
    20:08 get_orchestration_tool 재조회: 마지막 마스터 담당 claude(10-06), 워커 모드 claude
    (10-09 14:02, source=state). 실제 이번 대화는 Codex이며 기록·모드를 변경하지 않았다.
  - **검사**: 위키12, redmine184, auth69, MCP194, spec217, tagging78,
    master_local81, bundle468 통과. 정본 통합25모듈1,199건 rc0. 독립 검토 최종 결과는 보고서101.
  - **실패·재개**: 패치 문맥 불일치→사용자 재개; 기존 spec의 실 모델 호출 차단→사용자
    tagging 대상 추가·caller 격리 승인; fake caller dict 반환 rc1→사용자 문자열 수정·재검증 승인.
    최종 spec은 테스트 대역만2회 호출, 오류 없음. 상세 [리포트101](../reports/101-redmine-wiki-mcp.md).
  - **남은 작업**: #769는 진행 유지. 운영 반영 후 네이티브 MCP 노출과
    실제 Redmine 위키 조회·쓰기·되읽기 실증 필요. #768 아이디어수집 위키 기록 미실행.
    실제 HTTP 서버·위키 쓰기는 격리 조합 검사로 대체했다고 주장하지 않는다.
    다음 순서: 최신 인계 문서 diff 보존·추가 커밋 승인 확인 → 깨끗한 승인 커밋에서 ax-deliver 정본 update와
    ax-task-queue 운영 반영 계획 제시·승인 → MCP 노출·실제 위키 검증. 현재 진행 중 파견 없음;
    구현·독립 검토 서브 에이전트 종료. 운영 큐·서비스·원격 프로세스는 이번 요청에서 재조회하지 않았다.
  - **이전 보류**: ax-projects SIGTERM 지연 조사 등록 여부 미답. 이전 Claude 세션
    #762·#764·#767·#740 리포트 미작성도 별도로 남는다.

- **직전 체크포인트: 2026-10-09 17:35 · Claude · 사용자 토큰 소진으로 종료**.
  - **저장소**: HEAD = origin/main `5d9a35b`(#740 finalize 머지). 미커밋은 **이 문서뿐**(커밋 승인 없음).
    오늘 커밋: 56c7535·ccb1824·ba12185(ax-gemini) · 3e5a545(이전 인계) · ce486f3·919c0f2·32964df·e454e82(#764)
    · 112e88e(#767) · 5d9a35b(#740 work 머지). 배달 `update` 마지막 3/3 OK(5d9a35b).
  - **마운트**: AXCluster(오늘 MotionForge 에서 전환). **지휘 상태**: 마스터 담당 기록 `claude`(10-06 그대로) ·
    워커 전역 모드 `claude`(14:02 재설정 · AXCluster 워커 3대 준비 검사 통과). #740 work 만 `codex` 스탬프로 돌았다.
    말하기 전에 `get_orchestration_tool` 로 재조회.
  - **완료(레드마인 「완료」)**: #762 ax-gemini 스킬(대화형 세션이 리서치·보고서를 Gemini 에 먼저 제안 ·
    `master.work.gemini_report` 가 백그라운드 실행·인용 범위 검사·usage_log 기록·agy 재시도 회복 판정) ·
    #764 워커 agy 위임(지시문·ax-work §4 · 계측 3a · 회수 `~/ax-state/delegations/<work>/<task>/` ·
    `.agy-work/` (`.ax` 밖 — Windows 샌드박스가 `.ax` 쓰기 거부, 루트 샌드박스 SID ACE 미상속) ·
    Windows 는 세션1 런처 `AgyRelay` 가 샌드박스 밖에서 agy 중계) · #767 중계 계측을 런처 기록으로 ·
    #740(분산 work 20261009_1650_740_1ef3aa99 → ⑦ 8b4597a→5d2fc4b → finalize 5d9a35b · #765 완료).
  - **운영 변경**: `.43` 에 agy 1.3.2 설치(마스터 바이너리 복사 · 사용자가 별도 터미널에서 로그인) ·
    세션 사용량 운영 reparse(백업 `~/claude-workspace/backups/usage-before-740-reparse-20261009/`) ·
    `ax-projects` 재기동 17:24:36 — 🔴 정지가 90초 안에 안 끝나 systemd SIGKILL(원인 미조사).
  - **열린 일감(오늘 등록)**: #763 .33 ax-gemini 사용량 기록 경로 · #766 codex 지휘자 조각당 입력 87만~317만
    토큰 원인(캐시 92~95%) · #768 [아이디어] 옵저빌리티 도입.
  - 🔴 **멈춘 자리 (사용자 답 대기)**: ① #768 을 위키 [[아이디어수집]] 에도 적으려 했으나 `ax-client` 에
    위키 쓰기 도구가 없다 — (가) 사용자가 웹에 붙여 넣기 (나) 위키 도구 신설 (다) 이번만 키 직접 사용(규칙 예외)
    중 선택 대기 · **우회하지 않았다**. ② `ax-projects` SIGTERM 90초 무응답 원인 조사를 일감으로 남길지 미답.
  - **알려진 것**: `test_residency` 1건 실패(「배달이 갱신을 부른다」)는 이번 변경 전에도 같다 · claude 모드 위임
    계측은 「미상」이고 Windows claude 모드(세션0)엔 중계 없음 · `.2`·`.43` 지휘자 출력에 codex MCP
    `127.0.0.1:8000/mcp` 연결 실패 줄(무관 · 미조사) · 마스터 로컬 브랜치 `task/20261003_2315_719…/base` 남음(옛 work).
  - **리포트 미작성**: 오늘 세션 리포트(`reports/`)는 아직 없다 — 다음 세션이 이 체크포인트와 레드마인
    #762·#764·#767·#740 노트로 작성할 것.

- **직전 체크포인트: 2026-10-09 01:30 · Claude · 사용자 당일 작업 종료** (BC250 종료 요청).
  - **저장소**: HEAD = origin/main `6b5e96e`, 미커밋은 이 문서뿐(커밋 승인 없음). 코드 변경 없음.
  - **지휘 상태**: 마스터 담당 기록 `claude`(10-06, 변경 안 함). **워커 전역 모드 `claude`**
    (10-09 00:49 사용자 지시 — Codex 사용 한도 소진, 02:40 해제 예고). `.43` Claude 로그아웃이었고
    사용자가 재로그인 → 강제 재검사 2/2. 말하기 전에 `get_orchestration_tool` 로 재조회.
  - **MotionForge 묶음**: #706 완료(합성 99/99·워터마크 f57b82b) · #259 onboard --confirm rc0
    (완료 조건 3 판정은 사람 몫, 진행 유지) · #709 90%(AX 등록 해제·트윈·.2/.43/.33 클론·.2
    예약작업·Gitea 저장소·Redmine kimodo 삭제. 남은 것 GitHub `SimSeoWon/Test_KimodoMotion` —
    사용자 웹 삭제 대기, 비로그인 200). 백업 `~/claude-workspace/backups/kimodomotion_webui-20261009/`.
    [주의] 프로젝트 등록 해제 명령이 없어 `projects.yaml` 손편집.
  - **#695 분산 재실증 (Unreal 에디터 미리보기 · 사용자 요구 3: 에디터 전용 월드 재생 · 생성 창에
    그 월드 · 캐릭터 모델 변경)**: 1차 work `20261009_0036…`(codex, #755) 4/4 한도 실패 → 취소.
    재등재 `20261009_0051_motionforge_aac50fe6`(claude, **#756**): 3조각 verified(.2 641b365·06bd3a9,
    .43 7d77bda), `0906d6fc`(MotionForgeEditorModule.cpp)는 층2 REQUEST_CHANGES 6건 **오탐**(#757)
    → 사용자 결정으로 취소 → `.33` ⑦: 3조각 머지·본문 직접 채움, BUILD OK 32.9s/8.6s,
    작업 브랜치 전진 `18492fe → e5c54b3`. 런타임 미확인(main 반영 뒤 확인 예정).
  - 🔴 **다음 막힘**: 조각 하나 취소로 work `merge_status=cancelled` (`logic_lifecycle._flip_if_all_terminal`)
    → `finalize_work` 는 ready_for_review/in_progress 만 받음(`review.py:677`) → **main 마감 거절 예상
    (미실행·코드 판독)**. 갈래(사용자 미결정): ① 큐 규칙 수정(인프라 변경, RAG·승인) ② `.33` 수동 main
    머지 ③ finalize 한 번 시도해 거절 확인. 근거 #757 노트.
  - **.2 정리**: Codex 데스크톱 앱 재기동 발견 → 종료(sandbox 서비스는 남김), 홈 그림자 스킬 백업 후
    삭제(`~/claude-workspace/backups/2-agents-skills-20261009/`), check 3/3 경고 없음 (#661 노트).
  - **옛 브랜치**: `task/20261009_0036…/*`(취소 work) 미병합으로 Gitea 에 남음.
  - **운영**: 진행 중 work 0. `ax-projects` 23:56:23 재기동. BC250(.43) 종료.
- **직전 체크포인트: 2026-10-08 23:45 · Claude** (Codex 한도 소진으로 인계서 없이 인수).
  Codex 미커밋 「제미나이 1차·로컬 폴백」 합성 변경을 사용자 승인으로 `4a9fb87` 커밋·푸시,
  `master.client update` 3/3. 사슬 agy→gemma4:e4b→codex→gemma3:12b, 호출·형식·사실 거부
  모두 다음 모델로. 커밋 전 23:24 색인기 타이머가 작업 트리 코드로 이미 돌아 agy 10건 전부
  통과(loaded/error 거부 해소)·synth_pending 비움·워터마크 f57b82b. 소스 경계(Kimodo
  webui/scripts/vendor 포함)는 사용자 결정으로 유지. 토큰은 usage_log.jsonl 에 기록, agy
  비용은 cost_known=false. 사용자 승인으로 /commit-flow 표기를 제미나이 1차·LOCAL_MODEL 폴백으로
  수정(검사 39/39, 미커밋) · ax-projects 23:56:23 재기동(PID 48818, 페이지 200 확인).
  마스터 담당·워커 모드 기록은 변경하지 않았다. 아래는 직전 Codex 체크포인트.
- **직전 체크포인트: 2026-10-08 · Codex `/root`**. 사용자 선택으로 로컬 서브 에이전트
  구현·독립 검토 완료. MotionForge 마운트·kind=unreal 유지, 워커 .2/.33/.43 배달 검사3/3.
  HEAD/origin `60e7908`(사용자 승인 커밋·푸시·배포). 현재 dirty는 응답기록 구현2파일과
  리포트100·이 인계서다. 응답기록 수정의 커밋·푸시·배포 승인은 아직 없다.
  온보딩 consumer.lock 공유·최종 미완료 rc1·Unreal 등록 루트 dirty 보호를 구현했다.
  개별218건과 정본 통합25모듈 통과, 독립 검토 추가 차단 없음.
  ax-projects는 사용자 승인으로 22:25:20 KST 재기동, 배포 재검사 rc0·3/3.
  수정본 온보딩 재실증은96/99그룹·워터마크미작성으로 rc1: 미완료 판정 운영검증.
  mat/loaded/error 미언급3건과 검색기 초기화경합 유력 오류를 후속 조사했다.
  프롬프트에 선언최소하나 지시·배치검색기1회초기화/검색직렬/해제 구현,
  60e7908 배포3/3·재온보딩98/99그룹으로 rc1, llm_final_norm_parity loaded 미언급 남음.
  사용자 요청 단일재시도도 같은사유 rc1. 실제 응답원문이 없어 원인확정하지 못했다.
  사용자 승인 응답기록 추가: twin/synth_attempts/uuid.json에 prompt/raw/정규화문서/
  형식·사실판정 저장, 정책유지. 개별203+25건·정본통합25모듈 통과·독립검토 차단없음.
  이 기록 기능을 사용한 실제모델 재시도는 아직 없으며 상세는 리포트100 마지막절.
  #745 정렬 분기 실증, same-version 생략 분기 미실증. #259/#706/#695 전체 완료 아님.
  상세 근거·한계는 `reports/100-motionforge-onboarding-and-plugin-scope.md`.
  마스터 담당·워커 전역 codex 모드는 변경하지 않았다.

- **직전 갱신: 2026-10-08 00:26 KST · Codex `/root` · 사용자 당일 작업 종료**.
  인계서 작성 후 사용자 「BC250 종료하고 오늘은 이만 끝내자」 요청을 수행했다.
- **저장소**: `/home/sim/ax-cluster`, main. 작성 직전 HEAD와 origin/main 모두
  `5b9ce99b209d9311ad53abf1655529b7a63caa8d`, 작업 트리 clean. 작성 후 미커밋은 이 문서만.
- **지휘 상태 실측**: 마지막 마스터 담당 기록은 `claude`(2026-10-06 00:11:55 KST),
  실제 이번 대화·작업은 Codex. 워커 전역 모드는 `codex`(2026-10-07 22:16:19 KST, 출처 state).
  `get_orchestration_tool()`로 재조회했으며 담당·모드를 변경하지 않았다. 기록은 세션 잠금이 아니다.
- **운영**: #754 코드75ff0c5 반영, ax-task-queue 00:08:45 KST 재기동·active/running.
  마지막 AXCluster 워커 배달·검사3/3 출처75ff0c5. 이후 문서 커밋5b9ce99는 재배달하지 않았다.
- **현재 일감**: #720·#700·#753·#754 모두 완료/100을 실제 Redmine에서 재조회.
  다음 일감은 선택되지 않았다. 새 구현·파견·커밋·푸시·재배달 승인은 없다.
- **진행 작업**: 조회된 큐 work5개 모두 merged3/cancelled2. 진행 중 로컬 테스트·update 없음,
  제공된 서브 에이전트 모두 종료. 상주 서비스와 dispatch path/timer는 계속 실행 중.

## 이전 세션 메타데이터 — 이력 전용

아래는 2026-10-04 Claude 인계 기록이며 현재 상태·승인으로 사용하지 않는다.
현재 체크포인트는 위 요약과 §0 첫 절을 따른다.

- **이전 갱신 시각**: 2026-10-04 20:25 KST — Claude · #725 마감·후속 배포 · 색인기 막힘 해소(#732 완료) · 워커 동기화 ·
  `.2` MCP 경고 수정 · `/ontology` 브라우저 확인 · 통합 검사 등록 · agy 사용량 기록(#728 완료)
- **지휘 도구 / 세션**: **Claude** 마스터. Codex 는 이 문서를 갱신하기 전에 한도가 소진됐다
  (마지막 Codex 갱신은 00:47 헤더 + §0 R9·R19 후속). 17:02:34 `record_master_conductor('claude')`.
  마스터의 Codex 프로세스(pid 20028)는 17:02 에 살아 있었고 17:20 재조회 시 없었다(내가 종료하지 않았다).
  담당 기록은 세션 잠금이 아니다.
- **상태**: 진행 중인 work·루프 없음. 색인기 커서 = HEAD(`fc9c4de` 시점) · 리뷰 큐 pending 0.
  미커밋은 이 문서뿐.
- **관련 일감**: 완료 — **#725** · **#732**(사실 게이트 파일 종류별 주석 규칙) · **#728**(agy 사용량 기록) ·
  신규(미착수) — **#726**(토큰 구성 측정) · **#727**(색인기 frontmatter 멈춤 — 형식 게이트·모델) ·
  **#733**(sink 밖 상용 CLI 호출 — 층2·게시판·review_gen 직접, claude·codex 진입점 포함) ·
  아이디어 **#729**(스펙 주도 개발) · **#730**(「클로드 모드」 — 출처 미확인) · **#731**(NotebookLM 리서치).
  열림(이전부터) — #700 · #701 · #716 · #720 · #721.
- **워커 지휘자 모드**: **`claude`** — 사용자 지시 「모든 워커들 클로드가 작업하도록」,
  17:02:28 `set_worker_mode_tool('claude')`, readiness 3/3 ok
  (`.43` 2.1.222 · `.2` 2.1.285 · `.33` 2.1.286). 말하기 전에 모드 도구로 재조회한다.
  🔴 [주의] **work 스탬프가 전역보다 우선한다** — 등재 때 찍힌 `worker_mode` 를 파견이 쓰고
  (`autodispatch.py:424`), `improve_work` 에서 `worker_mode` 를 비우면 큐가 기존 값을 유지한다
  (`task_queue/logic.py:245`). 전역 전환(2026-10-04 17:02 이전 등재분 = `codex` 스탬프) 뒤 옛 work 의 round 를
  열 때는 **`worker_mode="claude"` 를 명시**한다. 새 등재는 전역값 `claude` 를 따른다.
- **마운트**: `AXCluster` — `.57` 요청자, `.2`·`.33`·`.43` worker. `.43` 은 어젯밤 poweroff 기록이
  있으나 17:02 readiness 에 응답했다(켜져 있다).
- **소스**: 마스터 main = Gitea main `66a7a1f` 위에 이 문서 커밋 · 작업 트리 clean.
  `ax-projects` 17:37:50 재기동(MainPID 79173) — 7화면 200 · 사이드 메뉴 확인. `fc9c4de`(verify/synth)는 색인기가
  실행마다 새로 읽으므로 재기동 불필요(라이브 통과로 확인).
  **AXCluster 워커 3대 + `.43 ~/ax-cluster` 관리 클론 = `66a7a1f`** (18:1x, 사용자 「워커 모두 동기화」·「관리 클론도」):
  main·clean 확인 → `fetch origin main` → `merge --ff-only` → `plan → deliver → check AXCluster` **3/3 OK**
  (스킬·config·payload 10·태그·출처 HEAD 일치 · 배달 뒤 source clean 3/3). 다른 프로젝트 워커는 손대지 않았다.
  `.2` `claude_mcp_local=ax-client` 「등록했다는데 ~/.claude.json 에 없다」 경고는 **검사 오탐이었다** — 등록·연결은
  정상(`claude mcp get` Connected). 원인: PowerShell 5.1 `Get-Content -Raw` 가 UTF-8 을 CP949 로 읽어 한글 기록이
  JSON 을 깨뜨림(60,855자 근처 파싱 실패). `3e46078` 에서 `-Encoding UTF8` + 테스트(395/395) · 고친 함수를 `.2`·`.33`
  에 읽기 전용으로 돌려 둘 다 항목 확인. 재배달은 안 했다(다음 배포에서 경고 소멸 확인). 워커 소스는 `66a7a1f`
  (`3e46078` 은 마스터 측 배달 코드라 워커 동기화 불필요). 홈 중복 스킬 `~/.agents/skills/ax-work` 주의는 무해.

## 0. 지금 넘기는 상태 — 아래 이력보다 이 절이 최신

### 세션 종료·BC250 전원 종료 (2026-10-08 00:26 KST)

- 사용자 요청으로 BC250 #1 `.43`만 종료했다. 종료 직전 큐 work5개는 merged3/cancelled2,
  기존 `master.status.fetch_live()`의 bc250 healthy=true·inflight0·오류 없음,
  원격 Codex/Claude/Python/Node 작업 프로세스0을 확인했다.
- 문서에 등록된 `ssh sim@192.168.0.43 'sudo -n /usr/bin/systemctl poweroff'` 실행 rc0.
  좁은 승인 래퍼 `/tmp/ax-bc250-poweroff-20261008.sh`는 위 조회·프로세스 확인·종료만 수행했다.
- 종료 뒤 SSH 읽기 재조회 rc255, Connection timed out. 정상 종료 명령 성공 이후 접속 중단을 확인했다.
  다른 노드·마스터 서비스·워커 모드·담당 기록은 변경하지 않았다.
- 다음 세션에는 `.43` 전원을 켠 뒤 SSH·브로커·작업장 상태를 확인한다.
  이 인수인계서만 미커밋으로 남겼으며 추가 커밋·푸시는 승인받거나 실행하지 않았다.
- 인계 작성 중 문장부호 정리로 생긴 끝 공백10곳 때문에 형식 검사 실패·중단,
  사용자 「응」으로 공백 제거 승인 후 git diff --check rc0으로 회복했다.

### 교대 체크포인트 (2026-10-08 00:20 KST, Codex)

**이번 세션 결과** — 항목 정본은 Redmine, 상세 증거는 연결된 보고서.

| 일감 | 결과·커밋 | 검증·한계 |
|---|---|---|
| [#720](http://192.168.0.57:8080/issues/720) | Codex 한도 오류 원문 보존1699701, 배포 스킬ffc830f, 완료/100 | runner160·infer230·usage18, 통합25모듈1,153건; 실제 한도 소진은 미재현. 보고서97 |
| [#700](http://192.168.0.57:8080/issues/700) | 기존 실패 고지 수정의 실제 `.33` 수신 증거 확인, 문서f3ed507 푸시, 완료/100 | 실패1회·완료1회 알림과 사용자 보고를 수집 대화/해시로 대조. 새 실패 작업 없음. 보고서79 §4 |
| [#753](http://192.168.0.57:8080/issues/753) | `.33` e4b 모델별 상주 허용152f2fb 푸시, 완료/100 | provision69건·통합1,153건; 실제 ps 응답은 빈 목록, e4b 상주 중 실측은 없음. 보고서98 |
| [#754](http://192.168.0.57:8080/issues/754) | PUT 뒤 실제 필드 되읽기75ff0c5, 운영 반영·완료/100, 배포 기록5b9ce99 푸시 | redmine184건·통합1,153건, 실제 MCP 완료/100 되읽기, 워커 배달3/3. 보고서99 |

**서비스·배포 대조** (00:19 KST 조회)

- ax-task-queue PID63185, 10월8일00:08:45 KST 기동, active/running.
  ax-projects PID1246·ax-broker PID1235, 10월7일20:30:07 KST 기동, 둘 다 active/running.
- ax-dispatch.path·ax-dispatch.timer 모두 active/waiting.
  큐 목록5개는 merged3/cancelled2이며 자동 리뷰 큐·색인 커서는 이번 교대 작성에서 조회하지 않았다.
- 마지막 정본 배달은 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`.
  AXCluster `.43/.2/.33` 출처75ff0c5·clean 도장·스킬/config/payload 검사3/3.
  현재 마스터 HEAD5b9ce99와 출처가 다름을 숨기지 않는다. 새 HEAD에서 check/update는 이번에 재실행하지 않았다.
- 워커 Git 체크아웃 HEAD와 관리 클론 HEAD는 현재 미조회.
  배달물 일치와 Git 소스 동기화는 별개이며, #720 때 Windows SSH 인용 실패 뒤 정본 배달로 이어갔다.
  임시 소스 동기화 스크립트를 재사용하거나 실패한 파견을 완료로 추정하지 않는다.

**승인·실패·에이전트**

- #720·#753·#754는 사용자 선택에 따라 로컬 구현/독립 검토로 처리했다. 새 작업은 기존 스킬 절차와
  사용자 선택을 확인한다. 완료된 구현·검토 에이전트 산출물은 위 커밋에 회수됐다.
- #754의 최초 redmine181/184 실패 뒤 중단, 사용자 「응!」으로 테스트 키 주입 재개,
  최종184/184 통과. #753 상주 조건 미충족 중단 뒤 사용자 승인으로 GET 진단해 비상주 확인.
  현재 미해결 검사 실패·awaiting_resume 작업은 없다. 실패 이력과 검증 한계는 보고서에 보존.
- 사용자 승인으로 위 커밋들은 모두 origin/main에 푸시됐다. 이번 인계서 작성은 커밋·푸시 승인이 아니다.
  이번 요청으로 문서만 갱신했으며 서비스·모드·큐·원격 파일은 변경하지 않는다.

**바로 다음 작업**

1. 이 문서의 미커밋 diff와 실제 HEAD·Redmine·지휘 상태를 대조한다. 실제 교대 지시가 있을 때만
   ax-handoff의 `record_master_conductor_tool`로 인수를 기록한다. 현재 claude 기록을 생존 판정으로 읽지 않는다.
2. 다음 일감은 사용자 선택을 받는다. 열린 일감 조회는 ax-redmine의 기존 MCP만 사용한다.
3. 새 배포가 필요하면 깨끗한 승인 커밋에서 ax-deliver 정본 update를 사용한다.
   현재 문서 커밋 뒤 배달 출처가 뒤처졌음을 먼저 설명하고, 재배달·서비스 재시작을 자동 실행하지 않는다.
4. 보류: `.33` 머신 자동 로드 문서의 옛 provision 불일치 설명은 별도 갱신 동의가 필요하다.
   실제 워커 한도 소진·e4b 상주·무시된 부모 상태의 운영 재현은 완료 증거로 주장하지 않는다.

관련 문서: [공용 규칙](orchestrator-rules.md), [ax-handoff](../master/skills/ax-handoff/SKILL.md),
[보고서97](../reports/97-codex-quota-event-preservation.md), [보고서98](../reports/98-provision-model-residency-policy.md),
[보고서99](../reports/99-redmine-update-readback.md), [보고서79](../reports/79-worker-failure-notice.md).

아래 절은 작업 당시 체크포인트 이력이다. 위 조회·최종 커밋·Redmine 상태가 우선한다.

### #754 운영 반영·완료 (2026-10-08, Codex)

- 사용자 진행 승인, 기존 로컬 서브 에이전트 선택을 이어 구현1개·독립검토1개.
- redmine.py/test_redmine.py: PUT 뒤 요청 필드 되읽기, 미반영·확인 실패 `[주의]` 반환.
  기존 MCP 배선에서 ok:false, notes-only 추가 GET 없음·재PUT 없음·clear_parent 유지.
- redmine 회귀181/184 rc1. 새 회귀 통과, 기존 meta 버전 검사3건 실패.
  가짜 sender 호출에 키를 주지 않아 meta의 키 공백 조기 반환과 일치한다.
  Docker 샌드박스 차단 원인은 추론이며 stderr 직접 확인은 하지 않았다.
- 실패 뒤 코드·설정 수정 중단. 재개 승인 뒤 해당 검사에 key="test" 주입 제안.
  client_mcp167/167·live_guard8/8·auth69/69 rc0, diffcheck rc0, 독립검토 차단 결함 없음.
- 사용자 「응!」으로 재개·기존 가짜 API 검사 테스트 키 주입 승인.
  기존 meta 검사에 key="test"만 추가, 에이전트와 메인 각각184/184 rc0.
  메인 정본 통합25모듈1,153건 rc0(16.981초), 최종 diffcheck rc0·독립검토 차단 결함 없음.
- 사용자 「진행해!」로 코드2개+보고서99/색인/인계서 총5파일 커밋·푸시 승인.
  75ff0c50d3f8b31bae2391203a66c54eb1a1ed38 커밋·origin/main 푸시 완료.
- 사용자 「반영해!」 승인. 기존 전용 도구로 ax-task-queue 재기동:
  10월8일00:08:45 KST, active/running·result=success·PID63185.
  ax-deliver 정본 update rc0, 마운트된 AXCluster .43/.2/.33 배달·검사3/3·출처75ff0c5.
- 실제 MCP 완료/100 요청 ok:true → 별도 get_issue 완료/100 되읽기 성공. #754 완료.
  부모 상태 무시·조회 실패는 격리 회귀 범위이며 운영 실패 작업을 만들지 않았다.
  워커 소스 git 동기화·파견 없음. 상세 보고서99·Redmine #754.
- 배달 완료 뒤 결과 기록 문서3개(보고서99/색인/인계서), 사용자 「응」으로 커밋·푸시 승인.
  기록 커밋 해시는 Redmine #754 후속 노트를 따른다. 운영 반영 코드는75ff0c5.

### #753 구현·회귀 통과, 실제 비상주 확인 (2026-10-07, Codex)

- 사용자 #753 진행·로컬 서브 에이전트 승인. 구현1개·읽기 전용 독립검토1개.
- provision.py/test_provision.py: .33 e4b만 모델별 상주 허용,14b 보유만 허용.
  기존 resident bool·위치 인자·GET-only/pull 재검증/dry-run 계약 유지.
- 회귀69건 rc0, 메인 통합25모듈1,153건 rc0(17.301초), 실제diff·독립검토 차단결함 없음.
- 승인된 `/tmp/ax-753-check-approved.sh`로 기존 check_node의 .33 tags/ps 읽기만 수행.
  reachable=true, 모델e4b/14b 보유, missing=[], loaded=[], 위반없음.
  실제 e4b 상주 확인 조건 미충족으로 rc1. 기존 ps 예외 숨김 때문에 실상주 없음/조회오류
  구분 미확정. 코드·설정·조회스크립트 수정이나 모델 적재 없이 중단했다.
- 사용자 「응」으로 진단 재개. 기존 provision._get으로 ps GET 응답 직접 확인:
  `{"models": []}`, rc0. 조회오류가 아니라 현재 비상주임을 확인했다.
  모델·서비스 변경 없음. e4b가 상주 중인 운영 실측은 아직 없으며 정책은 회귀로 검증.
- 사용자 「응」으로 코드2파일+보고서98/색인/인계서 총5파일 커밋·푸시 승인.
  이 절은 커밋 전 검증 기록이며 실제 해시·푸시·완료 상태는 Redmine #753 후속 노트로 확인.
  배포·파견·모델 변경 없음. 상세는 보고서98와 Redmine #753.

### #700 실제 요청자 수신 확인 (2026-10-07, Codex)

- 사용자 「700 가자」에 따라 기존 보고서79·RAG 문서·현재 훅과 수집 대화 원본을 대조했다.
  수정 `6001207`은 이미 배포됐으며 새 실패 작업을 만들지 않았다.
- `.33` Kimodo 세션 `8683a2e8-5152-42a8-9444-9bfe348ff613`의 실제 task-notification:
  10월 2일 00:30:32 KST OAuth 실패 수신 → 00:30:40 사용자에게 실패 보고.
  00:36:01 같은 work 완료 수신 → 00:36:08 완료 보고·사람 게이트 유지.
  work `20261002_0029_work_2710d620`의 실패 알림1회·완료 알림1회, 동일 실패 반복 수신 없음.
- 대화 사본의 SHA256을 수집 색인과 대조했다. 보고서79 §4에 원본 경로·행·시각·UUID 기록.
  Redmine #700의 후속 노트가 완료 상태의 정본이다.
- 실패 조각 없이 pending만 남는 정지 및 Codex 요청자 자동 알림은 이번 증거의 범위 밖이다.
- 보고서79·이 문서만 갱신. 사용자 「커밋해줘」로 문서2개 커밋 승인.
  운영 코드·설정·큐·파견·배포 변경 없음. 실제 커밋 해시는 Redmine #700에서 확인.

### #720 로컬 구현·검증 완료 (2026-10-07, Codex) — 현재 상태

- 사용자 #720 진행·로컬 서브 에이전트 방식 승인. 구현 1개·읽기 전용 검토 1개.
- 실제 기준 HEAD `fddf060`, 소스·회귀 6파일 미커밋 및 보고서97·색인·이 문서 변경.
  커밋·푸시·배포·파견 없음. 마스터 담당 기록은 바꾸지 않았다.
- 사용자 「모두 코덱스가 워커 담당하게」에 따라 전역 워커 모드 `codex`로 변경·재조회.
  2026-10-07 22:16:19 KST · 출처 state · AXCluster .43/.2/.33 준비 검사 3/3,
  codex-cli 0.159.3. 실제 실행 성공과 기존 work 스탬프 변경은 의미하지 않는다.
- 구현: Codex `error`·`turn.failed` 원문을 usage meta.errors → wcommit notes에 보존하여
  기존 quota_exhausted 판정으로 연결. 소스 usage.py·runner.py·wcommit.py,
  검사 test_runner.py·test_usage_accounting.py·test_infer.py. 큐 정책 유지.
- 최종 개별 회귀: runner160/160·usage18/18·infer230/230 rc0, 전문 확인.
  메인 정본 통합25모듈 **1,153건** rc0(17.086초), 별도 usage18/18 rc0.
  메인 diff 확인·독립 최종 검토 차단 결함 없음.
- 검사 중 기존 helper verifier 누락·예외 숨김과 새 rc0 회귀 baseline 대역 오류로
  각각 중단했다가 사용자 「응」으로 재개·보정했다. 현재 미해결 검사 실패 없음.
- 구조화/raw 오류 중복 정리·합계3개 요약 제한·rc0 층1 실패 회귀까지 확인.
  실제 워커 파견·요청자 수신은 이번 격리 회귀의 검증 범위 밖이다.
- **사용자 「응 푸시하고 배포해줘」로 커밋·푸시·배포 승인**. 대상은 소스·회귀6파일 및
  보고서97·보고서색인·인계서9파일. 깨끗한 커밋에서 AXCluster 워커 소스 ff-only 동기화,
  마운트 update 및 ax-projects 운영 반영을 수행한다. 이 절은 배포 전 체크포인트이며
  실제 해시·기계별 배달·서비스 결과는 Redmine #720의 후속 노트로 대조한다.
- 상세: [보고서97](../reports/97-codex-quota-event-preservation.md), Redmine #720.

### 자동 리뷰 정리 · Redmine 정리 · 배달 속도 (2026-10-06 22:3x ~ 10-07 00:2x KST, Claude) — 다음 세션은 여기부터

**사용자 결정·승인** (전부 대화에서 받음 · 커밋·push·재기동은 건마다 승인)

- 「자동 리뷰 확인해줘」 → R49–R69 점검, 추천대로 처리. 이어서 이전 미처리 R27-1·R37-1·R41-1 처리.
- 「레드마인 확인할까」 → 오래된 일감은 「결이 다르거나 이미 됐거나 하면 안 되는」 것이 섞여 있다(사용자).
  4건 대조 뒤 추천 승인: #227·#721·#265 닫기 · #264 아이디어 버킷 · #696 유지.
- 「부모 변경 기능 추가하고 227 대응」 → 직접 구현(사용자 선택).
- 「655번 배달 속도 개선으로 마운트된 프로젝트만 하고, 마운트 변경시 업데이트 체크해서 이전 버전이면 업데이트」
  → #745 내용을 구현. 🔴 사용자 정정: **등재 기계는 전부 사용자 것**(`.33` 메인 작업 PC · `.57` 인프라 · 워커들)이라
  「남의 기계라 기본은 보고만」이라는 `sync_check` 근거는 틀렸다 → 전환 기본 `align=True`.
  자동 로드 문서(`~/CLAUDE.md`=`machines/sim-desktop.md`·저장소 `CLAUDE.md`·`AGENTS.md`) 수정 동의.
- 「655 해보자 시간도 체크」 → 측정하며 개선. 병렬 처리는 이득(약 6초) 대비 `cmd_check` 재구성 위험이 커서 **보류**(승인).

**한 것** (커밋 순)

| 커밋 | 내용 | 검증 |
|---|---|---|
| `9b76b46` | R68-1 `update_issue` 상태 건너뜀 사유 유실 수정 · 타입 힌트(R66-1·2·R67-1) | test_redmine 114 (수정 전 실패 확인) |
| `0a97643` | R27-1·R37-1·R41-1 스타일 | usage 5종 |
| `0e43f11` | `client/README.md` 반쯤 나뉜 상태와 이유(#265) | 문서 |
| `ffaf877` | `redmine_note` 에 `clear_parent`(#754 결함 2) | 라이브: #259 parent=null → #227 완료 |
| `f165ede` | `update` 기본 마운트만 · `--all` · `set_active` 기본 `align=True` · 문서 9곳(#745·#655) | 160초 (종전 10~20분) |
| `d0bf674` | SSH ControlMaster · 바뀐 파일만 쓰기 · 검사 해시 일괄(#655) | 28초 · 일괄 해시 = 개별 해시 3대 대조 |
| `f468176` | exclude 1회 · mcp 동일하면 재등록 생략 · 🔴 `cmd_check` 의 `dirty_only` 덮어쓰기 결함 수정 | **20초** · dirty 실행 요약 정상 |

- 자동 리뷰: **R1–R69 열린 지적 0** — 이번에 applied 10 · dismissed 2(R67-2·R67-3, 근거 노트).
  기록은 `master.context_synth.fix_index.set_status`(환경 `AX_PROJECTS_ROOT=/home/sim/ax-cluster`).
- Redmine 닫음: #721(파견 중 OAuth 실패 고지 미검증을 명시, 실제 발생 때 미고지면 재개) · #265 · #227 · #655.
  #264 → 아이디어 버킷. #745 → 마일스톤 6 「진행」. 신규 #754(「진행」).
- 새 표면: `redmine_note(clear_parent=true)` — 이 Redmine 은 **부모의 상태·완료율을 자식에서 계산**한다
  (#227 이 자식 #259 를 떼자 완료율 50→100 즉시 재계산). 열린 자식이 있는 부모는 닫히지 않는다.
- 새 환경 스위치: `AX_SSH_MUX=0`(연결 재사용 끄기) · `AX_DELIVER_ALL=1`(전부 다시 쓰기). 소켓 `~/.ssh/axmux-%C` · 120초 유지.

**미검증 · 주의**

- 🔴 **#754 결함 1 미해결**: `redmine_note` 는 Redmine 이 무시한 상태 변경도 `ok:true`·「갱신 (status_id…)」로 보고한다
  (자식 열린 부모가 실례). **상태를 바꿨으면 `redmine_get_issue`/목록으로 되읽어 확인한다.**
- #745: 마운트 전환 시 자동 맞춤의 **실물 미검증**(일부러 전환하지 않았다) — 다음 실제 전환(예: MotionForge #706) 때
  `sync` 결과의 aligned/건너뜀을 보고 닫는다.
- 비마운트 4프로젝트 작업장은 `ffaf877` 배달본이다 — 그 프로젝트를 쓰려면 전환(자동 맞춤) 또는 `update --all`.
- MCP 재연결 뒤에도 이 세션의 도구 스키마는 옛 것으로 보였지만 새 인자(`clear_parent`)가 실제로 통했다(#752 때와 같은 현상).
- #754 에 완료율 50 을 손으로 적었다 — 「done_ratio 는 손으로 적지 않는다」는 옛 규약과 어긋난다(사용자에게 알렸고 미결).

**바로 다음 (사용자가 고른다)**

- 8월에 만든 남은 일감 분류(이미 됨 · 결이 다름 · 하면 안 됨 · 유효) — #211·#230·#232·#234·#235·#272·#296·#322·#326·#333·#344·#363 등.
- #754 결함 1(PUT 뒤 되읽기 대조) · #745 전환 실물 확인 · #696 상용 층2 운영 라운드 · #700 실패 고지 실물.


### 문서 최신화 (2026-10-06 02:4x KST, Claude) — 다음 세션은 여기부터

**한 것** (사용자 「온보딩, readme, 클로드, 에이전트 등 문서들도 모두 최신화해」)

- 로컬 서브 에이전트 3개로 문서 17개 감사(읽기 전용) → 사용자 선택 「🔴 거짓 + 🟡 낡은 세부만 고침, ⚪ 줄이기 안 함」 ·
  `master/README.md` 누락 모듈 행 추가 승인 → 같은 에이전트가 수정, 메인이 diff 검토. `2f33b36` 한 커밋.
- 자동 로드 문서: 레인 순서 `codex → agy → 로컬` · `worker_daemon` build 한정 복원(#404) · 8103 `/api/v1` 공개 ·
  골조는 요청자(#339) · 없는 `infer collect` 삭제 · 워커 모드 값은 문서에 쓰지 않고 도구로 조회 ·
  「커밋마다 전체 update」 · #721 요약. `~/CLAUDE.md` 심볼릭 링크 유지 확인.
- 런북 §14.2-4 가 **#721 Claude 재로그인 절차의 정본**(헤드리스 `.43`: `ssh sim@192.168.0.43` → `claude auth login`,
  브라우저는 PC → force 재검사). `win-worker-2.md` 에 「재부팅 뒤 janus 로그인 필수」.
- Windows 사본 갱신: `C:\Users\janus\CLAUDE.md`·`C:\Users\USER\CLAUDE.md` — 덮기 전 둘 다 저장소 이전 커밋 버전과
  바이트 동일(손편집 없음) 확인, 갱신 뒤 해시 일치.
- [주의] `master/README.md` 수정을 서브 에이전트가 자동 권한 판정(「공유 자원 수정」)에 거부당했다 — 우회하지 않고
  사용자 허락을 받아 메인이 직접 고쳤다. 같은 일이 나면 같은 순서로.
- **#753 신규**: `provision.py` 가 `.33` 을 `resident=False` 로 두는데 실제는 `gemma4:e4b` 상주 — 코드는 안 고쳤다.

**남은 것 (사용자가 다음 일감을 고른다)**

- 감사가 「확인 못 함」으로 남긴 것: `.43` 상주 여부 · `[리뷰 요청]` 별도 이슈와 등재 이슈 노트가 둘 다 사실인지 ·
  `.33` `.claude/agents` 재배선 · `.2`/`.33` CLI 버전. ⚪ 줄이기 후보(원전 오인용 경위 중복 등)는 안 했다.
- #721 · #700: 실제 파견 중 실패 고지 실물 대기. #696 상용 층2 운영 라운드 미검증. #265 전면 개편은 #264 뒤.
- 재검토로 다시 쓴 #333 · #370 · #296 와 정정 노트의 #232 · #234 · #322 · #264 는 미착수.

### #752 · 오래된 일감 재검토 · #227·#236 (2026-10-06 01:5x KST, Claude)

**사용자 결정과 결과**

- 열린 일감 62건 중 2026-09-12 이전 생성분 26건을 로컬 서브 에이전트 3개로 현재 방향과 대조(읽기 전용),
  메인이 근거를 직접 재확인. 판정: 유효 21 · 재정의 3 · 소멸 후보 2.
- **#326**: 「취소」가 아니었다 — 사용자 설명: GitHub 토큰 발행이 필요해 AXCluster 적용 사례만 남기고
  우선순위를 매우 낮춘다. 사용자가 웹에서 「낮음」으로 변경. 10-05 보관처 결정은 유효(착수만 미룸).
  [주의] 위 00:07 이력 절의 「#326은 취소했고」는 이 의미로 읽는다.
- **#399 완료** — #700 에 흡수. 남는 틈(실패 조각 없이 pending · 활성 0 정지)은 #700 노트로 이관. #700 은 실물 수신 대기(진행).
- **#752 완료** `e2cc556` — `redmine_note`(MCP)·`update_issue`·큐 `/redmine/note` 가 `priority_name`·`subject`·
  `description` 을 받는다. 실물: #752 우선순위 왕복 · #333·#370·#296 제목·본문 교체 3/3.
  [주의] MCP 재연결 뒤에도 도구 목록에는 옛 스키마가 보였지만 실제 호출은 새 인자를 받았다(원인 미조사).
- **본문 재정의**: #333(기계 단위 열거 · 취소 work 브랜치 예외 · 워커 main 복귀) · #370(부모 — 남은 #372·#373) ·
  #296(#696 층2 경로부터 손 검증).
- **정정 노트**: #232(09-06 「0건」은 틀림 — 2종 남음, 제목 「2종」) · #234(fetch_work 를 distribute 스킬이 가리킴) ·
  #322 · #264(이동 대상 넷 — workshop_by_project) · #265.
- **#227 완료 · #236 완료** `13201f4`. #265 는 README 거짓 인용만 정정, 전면 개편은 #264 뒤.
  [주의] 커밋이 바뀌면 배달물이 같아도 `check` 가 「출처 HEAD 뒤처짐」으로 실패한다 — 배포는 항상 전체 update.

**남은 것**

- 사용자 요청(01:5x): 온보딩·README·CLAUDE·AGENTS 등 문서 최신화 — 자동 로드 문서는 계획·동의 후.
- #721 · #700: 실제 파견 중 실패 고지 실물 대기. #696 상용 층2 운영 라운드 미검증.

### #721 운영 반영 완료 · 실워커 검증 (2026-10-06 00:4x KST, Claude)

**사용자 승인과 경계**

- 「실검증 진행해」에서 방식은 확인 질문으로 **마스터에서 바로**(미커밋 작업 트리 + SSH) 선택.
- 「커밋하고 배포해줘」로 `cf9e268` 커밋·Gitea push·`.43` 관리 클론 동기화·등록 전체 배달·ax-projects 재기동.
- 「인수인계서 갱신하고 커밋 푸시해줘」로 이 문서 커밋.

**실워커 검증 (00:13~00:17) — `worker_mode_readiness("claude", "AXCluster")`**

1. 사전: 세 워커 홈에 `claude-auth.json` 없음 확인.
2. 첫 검사: `.2` 2.1.285 ok · `.33` 2.1.286 ok · **`.43` 2.1.222 failure_type=auth** — 캐시 3곳 저장(정규화 필드만).
   `.43` 직접 `claude auth status`: loggedIn=false · authMethod=none · rc 1 · credentials expiresAt=0 → 오판 아님.
3. 새 프로세스 재검사: 세 워커 cached=True, checked_at 동일 → 24시간 내 재사용(성공·실패 모두).
4. `.2` `invalidate_claude_auth` → 다음 검사 cached 실패 → `force=True` 로 ok 복구.
5. 사용자가 `.43` 에서 `claude auth login` → force 재검사 **3/3 ok**, `.43` 캐시 실패→성공 기록.

커밋 직전 정본 통합 25모듈 재실행 OK(16.6초) · `git diff --check` 통과. Redmine #721 노트 3건(검증·재로그인·배포).

**남은 것**

- #721 「진행」 유지: 실제 파견 중 OAuth 실패 → runner 분류·즉시 Redmine 노트·큐 `fail_detail`·요청자 수신은
  미검증. 다음 자연 발생 때 확인하고 닫는다. 일부러 로그아웃시켜 재현하지 않았다.
- #696 실제 상용 층2 운영 라운드 미검증(진행). #750 은 사용자가 뒤로 미뤘다. 다음 일감은 사용자 선택.
- 검증 스크립트는 세션 scratchpad 의 임시 파일이다(저장소 밖). 같은 확인은 보고서96의 정본 함수 조합으로 한다.

### (이력) Codex → Claude 인계 준비 — #721 마감 준비 (2026-10-06 00:07 KST)

**사용자 확정과 승인 경계**

- #721 진행 지시, 기존 **로컬 서브 에이전트** 방식. 워커별 마지막 검사 시각·결과를 워커에 저장하고
  **경과 24시간 미만이면 재사용**, 기록 없거나 24시간 경과 시 검사. 세션마다/매 파견마다 auth status를 다시 돌리지 않는다.
- 실제 인증 실패 시 정상 캐시 무효화·즉시 고지·코드 재작성 재시도 제외. 자동 `claude auth login` 금지.
- 추가 검토 에이전트 생성 thread limit 실패 뒤 사용자 「응 로컬 서브에이전트를 이야기하는거니?」로 재개,
  기존 구현2개 + 메인 직접 최종 검토로 완료했다. 해결되지 않은 검사 실패나 재개 대기 게이트는 없다.
- **#721 커밋·푸시·동기화·서비스 재시작은 아직 승인받지 않았다.** #696의 「푸시하고 동기화해줘」는
  #696에만 적용된다. 인계 요청은 #721 배포 승인으로 확대하지 않는다.

**미커밋 실물 — 13파일 전부 #721 변경**

```text
M  master/work/conductor.py
M  master/work/runner.py
M  master/work/revise.py
M  master/work/infer.py
M  master/test_orchestration_control.py
M  master/test_runner.py
M  master/test_revise.py
M  master/test_infer.py
M  tests/integration/checks.json
M  reports/README.md
M  docs/orchestrator-handoff.md
?? master/work/conductor_auth.py
?? reports/96-worker-claude-auth-cache.md
```

`conductor_auth`는 기존 bundle의 remote_read/remote_write/ssh를 사용한다. 캐시 상대 경로
`.cache/ax-dispatch/claude-auth.json`, host/user/home 대조, JSON loggedIn+종료코드 확인, 동시 첫 검사 잠금.
API `check_claude_auth(facts, force=True)`로 재로그인 뒤 강제 검사 가능. 실패 결과도 TTL 내 재사용한다.
runtime은 stderr도 회수하고, 실측 OAuth 실패를 짧은 표식으로 보존한다. rc0이라도 오류 JSON이면 실패 처리.
infer는 즉시 Redmine 노트·큐 fail_detail에 호스트/원인을 남긴다. 기존 요청자 훅을 재사용하며 훅 소스는 수정하지 않았다.
준비 실패 시 모드 변경 차단과 Codex 계약은 기존대로다. 보고서96에 상세·force 검사 함수 조합이 있다.

**검사 증거와 다음 순서**

1. 홈/저장소 지침과 이 문서의 최신 절, [보고서96](../reports/96-worker-claude-auth-cache.md), Redmine #721을 읽고
   HEAD/dirty를 대조한다. 경로 목록 조회와 본문 읽기는 별도 호출로 수행한다. 기존 서브 에이전트 실행 ID를 이전하지 않는다.
2. 실제 인수 후 ax-handoff 정본 `record_master_conductor_tool(agent="claude", why="사용자 지시로 #721 실제 인수 완료", by="claude")`
   호출·재조회. 워커 모드는 조회만 한다.
3. 검사 완료: orchestration27 · runner156 · revise67 · infer218. 정본 전체검사 **25모듈1,137건**, rc0, 16.943초.
   명령 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`.
   새 소스 변경이나 미해결 우려 없이 동일 검사를 반복할 필요는 없다. 인계 직전 whitespace 검사도 통과했다.
4. 다음 남은 것은 **실제 워커 auth status/캐시 저장 왕복·24시간 내 재사용과 실패 고지 수신 검증, 승인 후 커밋·운영 반영**.
   현재 #721은 구현·격리 검사 완료/운영 미검증이라 진행이다. 실제 워커 검사가 CLI/API 인증 성공 전체를 보장한다고 쓰지 않는다.
   커밋/배포 승인은 구체 변경·검증 결과를 보여 받은 뒤 실행한다. 배달은 깨끗한 커밋에서 등록전체 update 정본을 사용한다.
5. 레드마인 조회·쓰기는 ax-redmine의 **ax-client MCP만**. 누락/실패면 물으며 Python/curl/임시 파일로 우회하지 않는다.
   사용자가 선택한 분산 방식도 불명확한 호출 때문에 바꾸지 않는다.

**다른 작업은 다시 시작하지 말 것**

- #326은 취소했고 그 구현 변경은 모두 정리했다. AXCluster의 Gitea→제한 접근 토큰 기반 GitHub 미러 사례만 #326에 기록했다.
  신규 private 저장소 생성/미러 설정 능력·권한은 검증하지 않았다. 기존 Gitea push 경로는 정상이다.
- #696은 배포 완료, 실제 상용 층2 운영 라운드 미검증이라 진행. `/tmp/ax-696-update.log`는 이전 등록전체 배달 검사 로그다.
- #750(12b 합성 품질)은 사용자가 Gemini 대체 경로 때문에 뒤로 미뤘다. 새로운 다음 일감은 사용자 선택을 따른다.

### 최신 — #721 워커 Claude 인증 캐시·실패 고지 (2026-10-05 22:30 KST, Codex)

- 사용자 지정: 워커에 마지막 검사 시각·결과 저장, 경과 24시간 미만 재사용. 실행 중 인증 실패는 즉시 고지·재시도 제외.
- 기존 선택인 로컬 서브 에이전트 2개로 구현, 메인 직접 검토. 추가 검토 에이전트 생성은 thread limit로 중단했다가
  사용자 재개 확인 후 진행했다. 기준 HEAD `40ea0ab`, #721 소스·검사·통합 목록·보고서·이 인계 미커밋.
- `conductor_auth`의 워커 홈 캐시를 준비 검사와 실제 Claude 실행이 공유한다. 만료 오류 때 실패 기록으로 갱신,
  즉시 Redmine 및 큐 실패 상세에 원인 보존. 자동 로그인 없음. Codex·준비 실패 시 모드 유지 계약은 기존대로.
- 통합 **25모듈 1,137건 통과**, diff whitespace 통과. 실제 워커 캐시 왕복·요청자 수신 및 운영 반영은 아직.
  #721 진행 유지. [보고서96](../reports/96-worker-claude-auth-cache.md).
- #696은 아래 커밋 전 기록 이후 사용자 승인으로 `40ea0ab` 커밋·Gitea push·클론 동기화·전체 15작업장 배달/검사 완료.
  ax-projects 21:25:29 재기동. 실제 상용 층2 운영 라운드는 미검증이라 #696 진행 유지(Redmine 배포 노트 정본).
- #326은 사용자 취소로 구현 변경을 모두 정리했다. AXCluster의 Gitea→제한 토큰 기반 GitHub 미러 사례만
  #326에 기록했다. 새 저장소 생성·미러 구축은 하지 않았다.

### 최신 — #696 커밋 전 층2 복원 (2026-10-05 21:14 KST, Codex)

- 사용자 선택 **로컬 서브 에이전트** 3개로 구현·독립 검토. 기준 HEAD `f9bc7bf`, 관련 소스·검사·통합 목록·보고서 미커밋.
- `infer.commit_task → wcommit.run` 층1 뒤·커밋 앞에 동결 선언 기반 층2 연결. 실제 작성 계열 제외, 검증 중 heartbeat,
  호출별 layer2 usage sink 및 실패/판정 원문 보존. 검증 불가면 커밋/코드 재작성 차단.
- 통합 **23모듈 923건 통과**(infer190·wcommit59·grounding9 등), diff whitespace 검사 통과.
- 실제 상용 모델·운영 워커 실증 및 커밋·푸시·배포는 아직. #696 진행 유지, 다음은 사용자 승인 후 커밋/배포와 운영 실증.
  워커 모드·마스터 담당 기록·서비스는 변경하지 않았다. 세부 [보고서](../reports/95-layer2-worker-verification-restoration.md).

### 최신 — agy 허용 정리 · 도구 설명 ax-cluster 정정 · 워커 재배달 완료 · #748 agy 작업 중 (2026-10-05 17:10, Claude)

#### 후속 (20:50) — #751 정정·수정·종결

- 확인 결과 본문 현상 1은 **틀렸다** — 19:13 합성 agy 호출은 `usage_log.jsonl` 에 정상 기록(입력 13,035 · 출력 2,722).
  「미상」은 `[synth]` 로그 줄이 브로커 전용 usage dict 를 읽어서였다. 대시보드 영향 없음.
- 사용자 ① · 직접: `626477b` — `usage.sink` 가 구간의 상용 CLI 행을 모으고 `sink_cli_tokens()`(측정분만 합산) ·
  synth 로그 줄이 그 값을 찍는다. GroupResult 합계는 기존 계약(로컬만) 유지. test_usage_sink 35/35 ·
  test_context_synth 179/179 외 사용량 검사 통과. 커밋 칸(현상 2)은 범위에서 뺐다. #751 「완료」.
- 라이브 미확인: 상용 레인 합성은 e4b 형식 거부 때만 일어난다 — 다음 발생 때 로그 줄로 확인.

#### 후속 (19:41) — #727 종결 · AXCluster 색인 워터마크 2일 공백 복구

- **#727 「완료」**(사용자 ① 현재 증거): 12:20 이후 형식 게이트 멈춤 0 · 19:13 체인 첫 운영 동작
  (`review_runner` e4b 형식 거부 → agy 통과, 26초). 미확인: app.py 자체 재합성 · codex 단계.
  분리 **#750**(gemma3:12b 품질 결함이 사실 게이트 통과) · **#751**(합성 대체 agy 토큰 「미상」·사용량 행 커밋 칸 없음).
- 🔴 발견·복구: AXCluster `last_indexed_commit` 이 **10-03 13:19 부터 비어 있었다**(색인 170회차 「364/369 — 5개 미합성 ·
  워터마크 미기입」). 문서 없던 5그룹 = `master/broker/__init__` · `projects/__init__` · `task_queue/__init__` ·
  `task_queue/__main__` · `verdict` — 10-03 첫 전체 합성 로그는 있으나 문서 없음(#711 트윈 이름 변경 중 색인기 강제 종료로
  잃은 것으로 추정, 미확인). 변경 파일만 합성하므로 저절로는 안 채워진다. 사용자 승인으로 기존 경로
  `python -m master.context_synth fill` → 5건 통과(34초) · 369/369 → **19:40 회차 재색인 369 · 워터마크 `4d5b290`**.
- 미조사 경고: 합성 중 `[related] 검색기를 열지 못했다 — KeyError: …/AXCluster/vector_db`(#744 노트에도 있음).
  합성은 통과하지만 관련 문서 발췌가 프롬프트에 안 들어가고 있을 수 있다.

#### 후속 (19:30) — #633 확인 · #637 완료 · test_indexer 간헐 실패 수정

- #633(리뷰 큐 부모) 71% 는 낡은 값이 아니었다 — 자식 7 중 #637·#639 미착수. 사용자 「637 네가 직접 해」.
- **#637** `b0f605f`: `prompt.py` 합성 지시문에서 「## 개선 필요 사항」 절 제거(결정 2026-10-05 · 측정 없이 · 소급 삭제 없음).
  소비자 셋의 제외 로직은 유지. test_context_synth 178/178 · verify_gate 40/40. **라이브 19:28** 회차 새 합성 3건
  (prompt·test_context_synth·test_indexer.md) 절 없음 · 게이트 거부 0 → 「완료」. #633 은 #639 만 남았다.
- 검사 중 `test_indexer` 간헐 실패 발견(4회 중 2회, 변경 없이 0/3): 615행 실패 메시지가 앞 블록의 해시표를 써서
  두 픽스처 저장소가 다른 초에 만들어지면 KeyError(`a1e135e` 에서 유입). 사용자 승인으로 같이 수정 `2109d07` — 5/5 통과.
- 미확인: 19:20 회차 로그 「합성이 안 끝났다(364/369 그룹 — 5개 미합성) · 워터마크 미기입」 — 다음 회차는 정상 종료했으나
  그 5그룹이 채워졌는지는 보지 않았다.

#### 후속 (19:20) — 자동 리뷰 지적 6건 수정 · agy 쓰기 자동 허용 제거

- 새 미결 리뷰 R54(ff17826) 3 · R56(accd72a) 2 · R57(ef7022b) 1 — 코드 대조 6건 모두 유효. 사용자 「전부 고치고 푸시」.
- `ax-fix` 흐름(`client/runtime/fix_flow.py` prepare→diff→commit→release; 마스터엔 `.ax/config.json` 이 없어
  `fetch` 는 실패 — 지난번 Codex 와 같은 경로): `fix/R57` `3cab0b6`(도넛 툴팁 `<0.1%` 이중 escape) ·
  `fix/R56` `b466897`(agy args 비dict · 비숫자 토큰 줄) · `fix/R54` `7aaef90`(빈 예외 메시지 · 관리 블록 표시
  역순 거절 · 공백). main 머지 `dad2d07`·`2868129`·`0d9e218` → push. fix/ 브랜치는 남겼다.
- 검사: usage_page 11 · session_usage · client_master_local 81/81 · usage_dashboard 통과. fix_index 6건 applied.
- `master-local --check` 9/10 FAIL 발견 — 17:40 agy 「항상 허용」으로 쓰기 도구 `redmine_create_issue`·`redmine_note`
  가 자동 허용에 들어가 있었다. 사용자 ① → 두 줄 삭제(백업 `settings.json.bak-rm-write-*`) → **10/10 OK**.
  [주의] agy 에서 레드마인 쓰기를 「항상 허용」하면 재발한다.
- 여전히 보류 중인 낮음 리뷰: R48-1·R48-3 · R27-1 · R37-1 · R41-1 · 주간 플랜 P1·P2.

#### 후속 (19:13) — #744 종결 · #749 리뷰 큐 running 회수 (버그·개선 마일스톤 열린 일감 0)

- **#744 「완료」**: 15:23 머지 5건을 색인기가 15:27 회차에서 「조각 커밋이 걸었다」로 처리 · 리뷰 큐엔 수정 커밋만
  각자 파일로 등재. 미확인: 충돌 해소 머지(--cc 비어 있지 않음)의 라이브 경로.
- 확인 중 발견 → **#749** 등록·수정: 15:45 systemd `TimeoutStartSec=600` 이 소비자를 죽여 `075bbba2` 가
  `running` 으로 영구히 남았다(회수 경로 없음). 사용자 결정 「회수 + 시간 예산 · 직접」.
  커밋 **`f280038`** — `review_queue.consumer_lock()`(실행 전체 flock) + `reclaim_orphans()`(일시적 실패 1회,
  3회째 abandoned) · `review_runner` 프로젝트마다 잠금→회수→처리 · 예산 600초 중 남은 시간 < 480초면 꺼내지 않음.
  검사 큐 50/50 · 소비자 57/57 · review_gen 63/63 · enqueue 17/17. **라이브 19:11** 회차가 `075bbba2` 회수 →
  같은 회차 리뷰 완료(R58). 유닛 파일은 그대로. #749 「완료」.
- 버그·개선 마일스톤 열린 일감 **0**. ax-cluster 전체 열린 일감 63 (18:5x 조회 64건에서 #744 종결 · #749 는 등록 뒤 종결).

#### 후속 (18:56) — 버그·개선 마일스톤 정리 (사용자 「버그 목록 수정하자」)

- 4건 대조: #744·#714·#666 은 수정이 이미 커밋돼 있었고 코드가 필요한 것은 #736 뿐이었다.
- **#736** 사용자 선택 ③ · 루트 직접 구현: 계열 필터를 고르면 `/usage` 도넛이 그 계열 안의 모델별 비율
  (토큰 상위 6 + 기타). 집계는 계속 source=all, 모두 보기 보고서는 재사용. 커밋 **`ef7022b`** · push ·
  `test_usage_page` 10/10 · `ax-projects` 18:54:20 재기동 뒤 화면 확인 → 「완료」.
- **#666** → #727 로 넘겨 「완료」(d2c0619 뒤에도 거부 4건, #727 `75ca7f7` 이후 12:20~ 거부 0).
- **#714** 사용자 선택 ① 현재 증거로 「완료」 — 코드 `d2c0619` 배선 · `~/ax-spool/claimed/` 비어 있음.
  한계: 옛 고아 배치 2건의 소비 로그는 못 찾았고 운영 실증은 하지 않았다.
- **#744** 열림 유지 — 남은 것은 머지 커밋 라이브 처리 확인(다음 ⑺ 전진 때 저널 「머지 …」 줄).
- 버그·개선 마일스톤 열린 일감 = #744 하나. ax-cluster 전체 열린 일감은 18:3x 조회 때 67건(이후 #736·#714·#666 종결).

#### 후속 (17:55) — #748 agy 구현 반려 → 마스터 재구현 · 완료

- agy 구현 2회를 검토해 반려했다(기존 테스트 19건 덮어쓰기 · #728 계약 위반으로 대시보드 테스트 2건 실패 ·
  모델명 괄호 잘림 · 중복 테스트 파일). 사용자 결정으로 되돌리고(패치는 세션 scratchpad) 마스터가 재구현했다.
- 커밋 **`accd72a`**(agy 세션 수집 · 대시보드 세션 보기 gemini 수용 · #728 계약과 모두 보기 규칙 유지) +
  `fa3c4d3`(이 문서) — Gitea push(사용자 「응 모두 진행해」).
- 검증: 세션 수집 21/21 · 대시보드 11/11 · 사용량 검사 6종 · 원격 목록 읽기 전용 실측(claude·codex 건수 불변) ·
  마스터 실제 수집 agy 복사 173/보존 밖 82/오류 0 · `ax-projects` **17:53:59 재기동** 뒤 API gemini 세션 377건.
- 레드마인 **#748 · #747(중복) 「완료」**. 아래 1·2번은 해소됐다.
- 한계: 마스터 agy 대화 255 중 221 은 cwd 미상(미분류). 이 변경은 마스터 쪽 코드라 워커 재배달 불필요.

#### 새 세션이 먼저 할 것 (17:10 기록 — 위 후속으로 해소)

1. **#748 검토 대기**: 사용자가 Antigravity 에 레드마인 **#748** 을 등록·작업 지시했다(Claude 가 시킨 것 아님,
   일감 내용 미조회). 사용자: “파이썬 코드 작업이 끝나면 문제없는지 너에게 검토 요청할게”. 요청이 오면
   `git status`·diff 로 agy 변경을 읽고 검토한다. 17:09 시점 마스터 작업 트리는 clean 이었다(agy 변경 없음).
   커밋·push 는 별도 승인.
2. agy 변경이 커밋되면 그 HEAD 로 **워커 재배달이 다시 필요할 수 있다**(변경이 배달 대상 파일이면).

#### 이번 세션에서 한 것 (모두 사용자 지시)

- 인수인계 대조: HEAD `2457ad6` clean · 서비스 3종 active · `ax-client`/`ax-redmine` 도구가 새 세션에서 보임(이전 「먼저 할 것」 1번 해소).
- `master-local --check` 가 **9/10 FAIL**(agy approvals) — `~/.gemini/antigravity-cli/settings.json` 에 인계(16:50) 뒤
  16:51 에 `mcp(ax-client/get_orchestration)` 허용이 추가돼 있었다(누가 넣었는지 미확인 — agy 「항상 허용」 추정).
  사용자 선택 ①로 그 줄 삭제(백업 `settings.json.bak-rm-orch-<시각>`) → **10/10 OK**.
- `client/runtime/client_mcp.py` `redmine_create_issue` 설명 「… ModularStage 에 둔다」 → 「… ax-cluster(id 3) 에 둔다」.
  `test_client_mcp` 163/163. 커밋 **`decb048`** · Gitea push(사용자 「응 모두 푸시해」).
- 워커 재배달 `AX_PROJECTS_ROOT=$PWD PYTHONUNBUFFERED=1 .venv/bin/python -B -m master.client update` — **rc0 ·
  5프로젝트 × 3대 = 15/15 OK · FAIL 0** · 출처 HEAD `decb048` 일치 · 배달 중 마스터 트리·HEAD 변동 없음.
  이로써 `ff17826` 닫기 문구 + `decb048` 설명 정정이 워커에 반영됐다. 워커 Git 소스 체크아웃(fetch/pull)은 하지 않았다.

#### 미확인

- #748 일감 내용·agy 작업 진행 상태 · 큐 pending/claimed 수 · `reports/` 전문 재독 — 이번 세션에서 조회하지 않았다.

### 최신 — 워커 claude 전환 · 리뷰 UI 모듈 카드 · 마스터 LLM 3종 레드마인 경로 통일 (2026-10-05 16:49, Claude)

#### 새 세션이 먼저 할 것

1. **재시작 뒤 확인**: 이 Claude 세션은 `ax-client` 등록 **전에** 시작돼 도구가 안 보였다. 새 세션에서
   `mcp__ax-client__redmine_*` 도구와 `ax-redmine` 스킬이 보이는지 확인한다. 안 보이면
   `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client master-local --check` 로 원인을 본다.
2. **워커 재배달 — 사용자 실행 또는 허용 대기**: `client/runtime/client_mcp.py`(닫기 문구) 변경이 워커에 아직 없다.
   `master.client update` 를 Claude 가 돌리려 하자 **자동 권한 검사가 「공유 자원 변경」으로 거부**했다.
   우회하지 않았다. 사용자가 `! cd ~/ax-cluster && AX_PROJECTS_ROOT=$PWD .venv/bin/python -B -m master.client update`
   로 직접 돌리거나 허용해야 한다. 실행 중에는 작업 트리를 건드리지 않는다(#737).
3. **결정 대기**: `redmine_create_issue` 도구 설명에 「AX 인프라 건이면 … ModularStage 에 둔다」가 남아 있다
   (2026-09-28 결정 = `ax-cluster` id 3 과 불일치). 고칠지 사용자에게 묻는다 — 고치면 재배달 **전에** 같이 반영.

#### 사용자 결정 (이번 세션)

- 워커 지휘자 모드 `codex → claude` (16:14:07, `set_worker_mode_tool`). 기존 work 20개는 `worker_mode: codex`
  스탬프 — 그 work 의 개선요청 라운드는 `worker_mode="claude"` 를 명시해야 한다.
- 리뷰 UI: 사용자가 원한 것은 접기가 아니라 **원문 안 모듈 절 구분**. 원인은 `### 모듈` 이 `<h4>`, 하위 `## N.` 이
  `<h3>` 로 역전 렌더링된 것. 모듈 카드로 해결 — 사용자 화면 확인 “내가 원하는 모습이야”.
- **모든 LLM(Claude·Codex·Antigravity)이 레드마인을 조작할 수 있어야 한다.** 방식은 로컬 서브 에이전트.
- **닫기 규칙 ①**: AX 인프라(ax-cluster) 일감은 마스터가 검증 뒤 「완료」로 닫는다 · 게임·분산 작업 일감은 사람(.33).
- 쓰기 도구 자동 승인은 열지 않는다(Codex·agy 모두 읽기 3종만 자동 허용). agy 헤드리스 읽기 허용은 승인.
- 손 루트 `~/.codex/ax-client`, `/tmp` 즉석 레드마인 스크립트 4개(`check_redmine.py`·`update_redmine.py`·
  `ax-usage-redmine-readonly/register-20261005.py`)와 agy 허용 2줄 **삭제 승인·완료**.

#### 커밋 (모두 Gitea push · 사용자 승인)

- `ae5fc0a` 이전 Codex 인계 문서(로컬에만 있던 것을 함께 push).
- `2e7e7c3` 리뷰 상세 원문을 `### 모듈` 마다 카드(`section.mod`)로 — `master/webui/fixes_page.py`·`test_fixes_surface.py`.
- `ff17826` `master/client/master_local.py` + `python -m master.client master-local [--apply|--check]` ·
  `master/skills/ax-redmine/SKILL.md` · `client_mcp.py` redmine_note 닫기 문구 · `test_client_master_local.py`.

#### 실측·검증

- 테스트: `test_fixes_surface` 140/140 · `test_client_master_local` 79/79 · `test_client_mcp` 163/163 ·
  `test_client_spec` 213/213 · `test_client_bundle` 440/440(서브 에이전트 실행) · `test_mcp_servers` 48/0.
- `master-local --check` **OK 10/10** (루트 0700 · config project=AXCluster · token 해시 일치 0600 · claude(user) ·
  codex · codex approvals · agy · agy approvals · agy mcp list · stdio `redmine_meta` 35도구).
- 세 CLI 실측: `claude -p` · `codex exec` · `agy -p` 각각 `redmine_meta` → `versions_project=ax-cluster · versions 3`.
  스킬 가시성: codex·agy 모두 `ax-redmine` 포함 5개 확인.
- 레드마인 첫 실사용(새 경로, `claude -p` + ax-client 4도구만 허용): **#746** 등록→근거 노트→「완료」100% ·
  **#747**(agy 대화 사용량 수집) 「신규」. 둘 다 ax-cluster · 버그·개선 · 코드리뷰. 공개 읽기로 되읽어 확인.
- 리뷰 UI: `ax-projects` 16:21:38 재기동 → R48 HTML 에 카드 2개·건수 확인 → 사용자 브라우저 확인.

#### 홈 설정 변경 (백업 있음)

- 루트 `~/.local/share/ax-client/.ax/{config.json,token}` (설치기 생성).
- `~/.claude.json` user 스코프 `ax-client` · 백업 `~/.claude.json.bak-master-local-20261005-163724`.
- `~/.codex/config.toml` 관리 블록(`# BEGIN/END AX MANAGED MCP (master-local)`) · `enabled_tools` 제거 · 백업 `…-163724`.
- `~/.gemini/config/mcp_config.json` · 백업(0바이트) `…-163724`.
- `~/.gemini/antigravity-cli/settings.json` 허용 읽기 3종 추가(백업 `…-164224`) · 즉석 스크립트 허용 2줄 제거(백업 `.bak-rm-tmp-redmine-*`).
- 스킬 링크: `~/.claude/skills`·`~/.codex/skills`·`~/.gemini/config/skills` 모두 `ax-handoff·ax-mode·distribute·debate·ax-redmine`
  → `master/skills/*` (Codex `debate`·agy 전역 폴더는 신규).

#### 미확인·주의

- 마운트를 바꾸면 `~/.local/share/ax-client/.ax/config.json` 의 project 가 낡는다 → `--check` FAIL → `--apply` 재실행.
- agy 대화 세션 사용량은 집계에 없다(#747). `session_usage.SOURCES` 는 claude·codex 뿐.
- 서브 에이전트 위임 1건(스킬·도구 설명 작성)이 자동 권한 검사에 「Instruction Poisoning」으로 거부됐다 →
  사용자에게 초안을 대화로 보여 동의받은 뒤 루트가 직접 반영했다.

### 최신 — 리뷰 수정 5건 통합·운영 반영 완료 / 리뷰 UI 범위 확인 대기 (2026-10-05 15:58, Codex)

#### 사용자 결정과 다음 작업

- 작업 방식은 **로컬 서브 에이전트**로 선택했다. 같은 리뷰 작업에서 다시 분산 방식 질문을 하지 않는다.
- 사용자 승인으로 자동 리뷰 5건 수정·각 커밋, 이후 “진행해줘!”로 main 통합·Gitea push를 완료했다.
  이어 “서비스 재기동하고 워커 동기화 진행해”로 재기동과 등록 전체 배달을 완료했다.
- **새 요청 원문**: “리뷰 페이지에 각 파일 - 변경분 코딩 컨벤션 - 변경분 버그. 안정성, - 영향 분석이 있는데,
  파일 단위로 구분되도록 외곽선을 넣는다거나 열고 접는 기능이 있어야겠는데?”
- 읽기 조사와 RAG까지 완료했으며 **UI 코드는 아직 수정하지 않았다**. 처음에는 펼친 테두리 블록과
  native `<details>/<summary>`를 제안했다. 다만 현재 원문 `###` 제목은 **파일이 아닌 모듈(디렉터리)** 이다.
  다음 두 선택지를 질문했다: ① 기존 원문 묶음에 테두리·접기 추가 ② 세 하위 절을 실제 파일별로 생성하도록 생성 계약도 변경.
  마지막 “응 그리고 … 인수인계서 작성해!”는 두 선택지 중 번호를 특정하지 않았다. **범위를 결정했다고 간주하지 않는다**.
- **바로 다음 작업**: 위 범위를 사용자에게 짧게 확인 → `distribute` 기존 절차, 로컬 서브 에이전트 구현·독립 검토 →
  변경 파일/검사 결과 제시 → 새 커밋·push 승인. 이번 인계 문서의 커밋·push도 아직 승인되지 않았다.

#### 저장소·완료한 수정

- 작업 위치 `/home/sim/ax-cluster`, branch `main`, HEAD와 `origin/main` 모두
  `98c98a8a6f77c3f4abefa57b4b5bab03575b0df1`.인계 작성 전 clean, 작성 뒤 변경은 이 문서뿐이다.
- 수정은 `ax-fix` 정본 `client/runtime/fix_flow.py prepare/diff/commit/release`로 번호별 처리했다.
  각 `fix/Rxx` 브랜치는 삭제하지 않았다. 사용자 승인으로 각각 `git merge --no-ff` 뒤 `git push origin main` 완료.

| 항목 | 수정 커밋·브랜치 | 변경 |
|---|---|---|
| R48-2 | `5b45bad` · `fix/R48` | `stamp_dirty=None`을 뒤처짐으로 오분류하지 않음(`dirty is False`) |
| R25-1 | `2ddface` · `fix/R25` | 빈 모델 표의 ‘기록 없음’ 중복 제거 |
| R27-2 | `f2d76cf` · `fix/R27` | 일감 파일 OSError는 read_errors, ValueError/TypeError는 invalid_records |
| R30-2 | `075bbba` · `fix/R30` | 대소문자 무관 HEAD 탐색, 원문 index로 CSS 삽입(Unicode 위치 보존) |
| R43-1 | `df39ca3` · `fix/R43` | 실제 Git 검사 함수의 임시 저장소를 TemporaryDirectory로 정리 |

- main 병합 커밋 순서: `27aebaa` → `dd50dbe` → `dac4c8d` → `ffdbc2f` → **`98c98a8`**.
  GitHub 직접 push 없음. 정본은 Gitea `origin`; 원격 훅의 색인 이벤트 1건 큐잉 확인.
- 정본 리뷰 상태 `master.context_synth.fix_index`에 위 5건 applied 및 병합·push·검증 결과 기록/재조회 완료.
  기존 해결 R42-1은 `5223cfb`로 applied. 사용자 승인으로 R37-2와 R30-1은 dismissed.
- 15:57 재조회: **미결 리뷰 4문서·5항목**, 모두 낮음 — R48-1/R48-3/R27-1/R37-1/R41-1.
  각각 타입 힌트, 빈 dirties 호출 방어, 긴 줄, 테스트 내 import, pi 상수 지적이며 앞서 보류했다.
  P1/P2 주간 플랜은 별도 미결, 검토하지 않았다. 새 R49~R52는 지적 0건.

#### 검증·실패 기록

- 병합 후 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`
  **20/20 통과, 세부 판정 791건**(색인기 142, 사용량 집계 10, 사용량 페이지 8, 사이드 목록 8 포함).
  Gitea 권한 검사 때문에 동일 명령을 샌드박스 해제 승인으로 실행했다.
- 별도 클라이언트 회귀 `test_update_reports_dirty_tree`, `test_update_reports_head_movement`,
  `test_update_head_round_trip_is_reported`: **PASS=34 FAIL=0**. 전체 test_client_bundle는 실 SSH/운영 영향이 있어 돌리지 않았다.
- 번호별 검사와 독립 검토 통과: R48 34, R25 8, R27 10, R30 8, R43 대상 함수 11.
  `git diff --check` 및 main 통합 diff 검사 통과.
- **이번 실패**: 루트가 R27 추가 검증에서 존재하지 않는 함수 이름을 추측 입력해 AttributeError(rc1).
  실제 `test_request_read_errors_and_invalid_records_are_separate` 선언을 확인하지 않은 실행 실수였다.
  실패 보고 후 멈췄고 사용자 “응 다시 검증해” 승인으로 목록→선언 확인→정확한 함수 재실행 통과했다.
  코드 결함이나 검사 실패로 기록하지 않는다. 다음에는 실제 검사명 확인 뒤 실행한다.

#### 서비스 재기동·워커 배달 실측

- 기존 `scripts/ax-service-restart <unit>`(report73, master/service_restart.py)으로 순차 재기동:
  `ax-projects` **15:29:52**, `ax-task-queue` **15:30:02**, `ax-broker` **15:30:08 KST**.
  기동 시각 변화 + active/running + Result=success 확인. `/livez`(8101/8102/8103) 모두 `{ok:true}`.
  ax-projects는 기존 프로세스 stop-sigterm 종료를 기다린 뒤 정상 재기동했으며 강제 종료하지 않았다.
- 기존 호출:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster PYTHONUNBUFFERED=1 .venv/bin/python -B -m master.client update`
  (네트워크/원격 쓰기를 위해 같은 명령의 샌드박스 해제 승인).**최종 rc0·완료 줄 확인**.
- 등록 5프로젝트 **ModularStage, NS, KimodoMotion_WebUI, MotionForge, AXCluster** 각각
  `.2/.33/.43` **15/15 배달 후 최종 검사 OK**.config, 프로젝트 로컬 스킬, MCP 등록, 페이로드 해시,
  태그, 출처 마스터 HEAD 일치를 확인했다. 프로젝트별 원래 역할과 index_only 진입 문서 보존 계약을 유지했다.
- 배달 중 HEAD/dirty 변동 없음. UI 요청은 배달 중 들어왔지만 읽기 분석만 해서 clean을 유지했다.
- **위 동기화는 관리 자산 배달/검사다**.워커 Git 소스 체크아웃 HEAD나 `.43 ~/ax-cluster` 관리 클론을
  이번에 fetch/pull로 맞추지 않았고 최신 소스라고 주장하지 않는다. 필요한 경우 기존 호출 계약부터 확인한다.
  `scripts/sync-clones.sh`는 읽었지만 실행하지 않았다(옛 GitHub 라벨과 실제 origin=Gitea 구분 필요).
- 최신 systemd 조회: 상주 3종 active/running; `ax-indexer` 15:56:31, `ax-review-queue` 15:46:51,
  둘 다 oneshot inactive/dead·Result=success.별도 수동 작업/원격 파견 없음.

#### 리뷰 UI 조사 결과 / 서브 에이전트

- RAG `search_context_tool`에서 `master/webui/fixes_page.md` 검색 → 실제
  `AXCluster/context/master/webui/fixes_page.md` 전문 → `master/webui/fixes_page.py` 대조 완료.
- 현재 `render_detail`은 수정 항목 통합 표와 원문 전체를 보여 주고, `render_markdown`은 제목·표·본문을 escape한다.
  `master/context_synth/review_gen.py`의 생성 계약상 `###`는 모듈 단위(조사 에이전트가 97/272행 확인).
  제목만 접기 블록으로 감싸면 모듈 구분이 되며 실제 파일별 분석으로는 바뀌지 않는다.
- UI만 변경할 후보는 `master/webui/fixes_page.py`, `master/test_fixes_surface.py`.
  `items_detail[].file`로 수정 항목을 묶는 것은 가능하지만 원문 영향 분석은 모듈별이라 이를 임의로 파일에 귀속시키지 않는다.
  검사 계약 `.venv/bin/python -B master/test_fixes_surface.py`(스크립트 PASS/FAIL, unittest discovery 아님).
  범위 확정 뒤 테스트를 고른다. 아직 코드 변경·검사·브라우저 확인·새 Redmine 등록 없음.
- 로컬 에이전트: r48_fix(R48 구현), remaining_review_prep(R25/R27/R30/R43 구현 및 UI 읽기 분석),
  r48_review(독립 검토).모두 completed, 파일 쓰는 에이전트 없음. 새 세션에서 실행 ID 이전을 전제하지 않는다.

#### 기존 기능 호출 관련 사용자 결정 — 재발 금지

- MCP 목록에서 ax-client가 안 보이거나 역할 토큰이 없다고 Redmine 기능 부재로 판단하지 않는다.
  기존 설정/문서/소스를 확인하며, **호출 방법이 불명확하면 사용자에게 먼저 묻는다**.
  임시 Python 파일·스크립트·대체 경로를 만들지 않는다. 과거 /tmp 경로를 재사용해 우회하지 않는다.
- ax-client는 이 프로젝트의 로컬 stdio MCP이며 OpenAI 제품이나 systemd 서비스가 아니다.
  이번 초기 MCP 호출은 `/home/sim/.codex/ax-client/.ax/token` 역할 토큰 미구성으로 실패했다.
  실제 Redmine은 기존 `master.redmine.get_issue`를 통해 조회 성공했다(#744/#727 진행, #737 완료, #745 아이디어 — 당시 조회).
  기본 샌드박스에서 api_key가 빈 값이면 Docker 권한 차단 가능성: **동일한 좁은 기존 조회 명령**의
  샌드박스 해제 승인으로 확인, 키 자체 출력 금지.해당 일감은 인계 시 새로 조회하지 않았으므로 현 상태 재확인 필요.
- 홈 AGENTS.md/CLAUDE.md 링크 보존, 목록 확인과 읽기를 두 별도 도구 호출로 실행하며 에이전트에도 명시한다.
  RAG 본문을 실제 코드와 대조한다. 실패면 보고 후 멈추고 사용자 재개 승인을 따른다.
- UI는 미커밋 변경이 없으며 **이번 인계 문서 작성만 새 승인**이다. 인계를 커밋·push 승인으로 확대하지 않는다.

### 최신 — 자동 리뷰 점검 · #744 · #727 · #737 종결 · #745 (2026-10-05 14:45, Claude)

**커밋 (모두 Gitea push · 사용자 승인)**: `93dea06`·`a1e135e`(#744) · `75ca7f7`·`90ab208`(#727) · `f5d7f77`(/commit-flow) · `5223cfb`(#737).

- **자동 리뷰 점검(AXCluster)**: R1–R44, 지적 33개 중 24 처리 · 미처리 9개는 전부 「낮음」(R25-1·R27-1·R27-2·R30-1·R30-2·R37-1·R37-2·R41-1·R42-1 — R42-1 은 `5223cfb` 로 해결). **미처리 8개 적용/기각 결정은 사용자 대기**(추천: R37-2 기각, R25-1·R27-2 적용).
- **#744(진행)** 리뷰 큐 포기 15건의 원인 둘 수정: ① 머지 커밋 `git show` 빈 diff → 깨끗한 머지 스킵·충돌 해소분만 리뷰 ② 색인기 변경 파일이 부모가 아닌 직전 걸은 커밋 기준 → 첫 부모 기준(#727 「덧붙은 관찰」 원인). 추가로 걷기 위상 순서 + 커서 밖 완료 집합 `<twin>/analyzed_beyond.json`(멈춤 뒤 재걷기 0). **미확인: 라이브 머지 처리 · 커서 밖 집합 사용**(다음 ⑺ 전진 때 저널 「머지 …」).
- **#727(진행)** 합성 형식 거부 대체 사슬 `SYNTH_CHAIN = e4b → agy → codex → gemma3:12b`(claude 제외 · 첫 모델은 항상 로컬 · 상용은 레인당 1회 · 장애는 회로차단). 사용자 지시 「제미나이를 더 적극적으로」로 agy 를 둘째로. 막힘의 진짜 원인은 `---` 복구가 공백 든 category 를 거부한 것 → 복구 규칙 확장. 라이브: 색인 커서 `565e211 → 75ca7f7` 전진, 리뷰 R43·R44. **결정 대기**: 12b 품질 문제 별도 일감 · 사용량 행에 커밋 칸 · 상한 초과 파일 사전 라우팅/사실 게이트 체인. **미확인: 실제 agy·codex 합성 호출.**
- **#737 완료** — dirty 트리·HEAD 궤적 감지. [주의] **update 실행 중에는 커밋도 파일 수정도 하지 않는다**(13:4x 작업 트리 수정으로 rc 1 · 11/15 FAIL → `f5d7f77` 커밋·재기동·재실행 15/15).
- **#745(아이디어)** `update` 기본을 마운트 프로젝트만 · 마운트 전환 시 필요하면 갱신 · `--all` 유지.
- `/commit-flow` 화면에 대체 사슬(상수에서 읽음)·머지 처리 설명 추가, `ax-projects` 재기동 14:00:11.
- [주의] 기존 실패: `test_mount_gate`(수정 전 기준선부터 IndexError) · AXCluster `last_indexed_commit` 빈 값 = 「362/367 그룹 미합성」(그중 `master/test_board` 사실 게이트 given_up, 나머지 4개 미조사 — #259) · 색인기 경고 「[related] 검색기를 열지 못했다 KeyError .../AXCluster/vector_db」(미조사).

### 최신 — 리포트 94 후속 등록 · 버전 없는 일감 정리 (2026-10-05 12:30, Claude)

- 11:30 의 Codex 세션이 쓴 미추적 `reports/94-session-usage-preliminary-findings.md`(수집 원본 654개 예비 토큰 분석)의
  후속 일감을 사용자 지시로 등록: **#740** 파일 간 응답 중복(Claude `message.id` 추가 출현 360건) · **#741** 세션의 프로젝트·일감 출처
  보강(미분류 57%·work/task 0건) · **#742** 긴 세션 맥락 운영안(측정 먼저, #368 연결) · **#743** 도구 오류·반복 조회 요약(`is_error` 357건).
  #726 에 예비 결과·후속 번호·#623 연결 불일치 노트(종결 안 함). 리포트 「Redmine 연결」 절에 번호 기록 후 `3b9d2f3` 커밋·push.
  [주의] 리포트 수치는 **파일 간 중복 보정 전 예비값** — 확정 지표·절감 근거로 쓰지 않는다.
- 버전 없던 #706·#709·#710(10/3 MotionForge 이전분)을 마일스톤 6(17)에 붙임. **MotionForge 실증 묶음 = #706 → #259 → #695 → #709**
  (#706 마운트 전환·배달·graph/synth/index 가 첫 단계 · #710 은 자동 로드 문서라 동의 후 수정).
- `CLAUDE.md` 마일스톤 소유 문구는 `1109901` 에서 정정 완료.

### 최신 — Redmine 정리 마감 · 마일스톤 소유 · 범위 점검 · 판단 20건 (2026-10-05 12:00, Claude)

**요청 재해석** — 사용자: *"마일스톤 이름이 모듈러 스테이지고, 일부 일감도 지금 클러스터링 관련된 내용이 아닌거 같다"*.
처음엔 「오래된 일감 정리」로 잘못 읽어 낡음 분류(27건 종결)를 먼저 했다(그 작업도 단계마다 승인받음). 실제 요청 둘을 이어서 했다:
- **① 마일스톤 소유**: 버전 셋이 ModularStage 소유·system 공유라 「ModularStage - 마일스톤 6」으로 보였다. ax-cluster 에
  같은 이름 버전 재생성(마일스톤 6=**17** · 아이디어=**18** · 버그·개선=**19**), AX 일감 250건 이동(실패 0), 옛 5·6·16 공유 해제.
  [주의] 같은 이름이 둘 보이면 `redmine.resolve_version_id` 가 옛 버전(5)을 골랐다 — 공유 해제 뒤 17 로 해석 확인.
  부작용: MotionForge #697 의 버전이 비었다(MotionForge 는 버전이 없고 그쪽 일감 5건 모두 버전 없음 — 그대로 둔다).
- **② 범위 점검**(로컬 서브 에이전트 3명, 읽기 전용): 닫힌 190건 전부 AX. 열린 67건 중 8건 처리 —
  #218·#268·#215 종결(#268 의 게임 결정은 modularstage **#739** 로 이관) · #708 → modularstage 이동 · #403 종결(`machines/` 가
  AXCluster 워커 3대에 있으나 「모두 마스터가 관리하는 워커」라 감수) · #406 범위 재정의(푸시 기준 실증, `.33` 편입은 수작업이 있어 불인정) ·
  #368 아이디어로 좁힘(**잔여 토큰 임계(예: 20%)에서 인수인계서 작성을 먼저 제안** — 사용자 발상, 잔여 한도를 기계가 읽을 수 있는지 선결 측정) ·
  #709 한 일감 유지. 제목 정정: #326 · #695(**재실증 대상 MotionForge**) · #296.

**판단 필요 20건 — 결정 기록 완료**: 종결 #226·#238·#239·#252(→ 실행분 **#738**)·#356·#403 · 범위 재정의 #230·#406·#368 ·
보류 #650(ModularStage 마운트 뒤 · `.uproject` 수정 안 함) · 방향 결정 후 착수 대기는 아래 표.

| 착수 대기 묶음 | 일감 |
|---|---|
| 층2 되살리기(`wcommit`, agy→claude, **사용량 기록 염두**) | #696 + #734(`get_code`·`generate.dispatch` 제거) |
| 지휘자 모드: 개선요청이 공식 · 「이 work 만」 장애 대응 추가 | #392 |
| 트윈 Gitea private + GitHub 미러, 갱신마다 커밋·push | #326 |
| 워커 지시 abort 배선 | #344 |
| 합성: 「개선 필요 사항」 절 제거 · 큰 파일 대체 모델 | #637 · #727(+#666 함께 닫기) |
| scope 요청 = 리뷰 먼저 모아 플랜 | #639 |
| 작은 수정 | #227(`onboard` 안내) · #236(mcp.json 2항목 제거) |
| Claude 역할 스킬 → 체크아웃 | #738 |
| **MotionForge 실증 묶음** | #259 온보딩(최초 색인 — MotionForge `last_indexed_commit` 빈 값) → #695 재실증 → #709 정리 |

[주의] AXCluster `config.yaml` `last_indexed_commit` 도 비어 있다(색인기는 돌고 `analyzed_commit`=`f3c06fb`) — #259 실증 때 원인 확인.
분류표 파일은 재부팅으로 사라졌다(내용은 각 일감 노트에 있다). 열린 ax-cluster 일감 **62건**(마일스톤 6 45 · 아이디어 10 · 버그·개선 4 · 버전 없음 3) — 이후 종결·이동 반영 전 수치.

### 최신 — #737 수정 · Redmine 정리 (2026-10-05 01:20, Claude)

**#737** (update 실행 중 HEAD 이동): 사용자 선택 「감지해 따로 알림」 + 로컬 서브 에이전트. 커밋 `56e7a1c`
(`master/client/__main__.py` · `master/test_client_bundle.py`). 시작 HEAD 출력, 이동 시 「실행 중 마스터 HEAD 가 움직였다 A → B — 다시 실행하라」,
뒤처짐만인 검사 실패는 「실행 중 HEAD 이동 탓」 표기, rc 1 유지(자동 재실행·커밋 잠금 없음). test_client_bundle 407/407.
배포: push · `ax-projects` 재기동 00:37:36 · 워커 4곳 `56e7a1c` ff-only · update 15/15 OK(시작 HEAD 줄 정상, 이동 없음).
[주의] 이동 경로는 실물 미확인 · 종료 코드 숫자는 세션 교체로 못 받았다(성공 시에만 찍히는 완료 줄은 있음) · #737 은 아직 「신규」.

**Redmine 정리** (사용자 지시 「마일스톤에 모듈러 스테이지는 지워줘」·「개발 상황에 맞지 않는 일감」):
- 마일스톤 6 의 ModularStage 일감 107건(전부 완료 [AX]) → **ax-cluster 로 이동**(부모 먼저 · 실패 0 · 부모 관계 유지).
  버전 소유 프로젝트는 그대로 ModularStage(전체 공유). `CLAUDE.md` 219줄 「modularstage 에 기록으로 둔다」를 이동 사실로 정정(사용자 동의).
- 열린 77건을 로컬 서브 에이전트 3명이 읽기 전용 대조(HEAD `56e7a1c`): 완료됨 24 · 전제 소멸 3 · 유효 30 · 판단 필요 20.
  분류표 원본은 `/tmp/claude-1000/redmine-move/triage-{0,1,2}.md`(임시 — 재부팅 시 사라진다).
- 사용자 승인으로 **27건 완료 종결**(근거 노트): #169 #229 #233 #237 #240 #285 #289 #293 #317 #338 #365 #371 #388 #401 #404 #407
  #626 #628 #630 #631 #648 #661 #693 #701 #713 #716 #717. 자식 분리: #322·#326·#344(←#317) · #403·#406(←#401) · #252(←#229).
  [주의] Redmine 은 열린 자식이 있는 부모의 「완료」 전환을 **오류 없이 무시**한다 — #289·#401·#626 은 노트만 들어가고 상태가 안 바뀌어 자식 종결 뒤 재적용했다.
- 상태 변경: #695·#700·#711 → 진행 · #211 → 신규. 마일스톤 6 열린 일감 **50건**.

**판단 필요 20건 (사용자 답변 대기)**: #696(층2 되살리기 vs 「four gates」 서술 정정) · #392(라운드 중 지휘자 변경) · #326(트윈 보관 Gitea) ·
#227 · #226 · #230 · #238 · #239 · #236 · #252 · #344 · #734 · #356(알림 채널) · #637 · #639 · #650(ModularStage 프로필 — 등재 막힘) · #727 ·
#259 · #406 · #403(`machines/` 가 워커 3대에 복사). 별도 관찰: #232 — 스킬 2개가 아직 `mcp__master-orchestrator__` 를 부르며 배달된다.

### 최신 — #735 원본 보존 정책 · 계열별 도넛 · update 완료 (2026-10-05 00:30, Claude)

**사용자 결정**:
- 원본 보존 값은 `projects.yaml` 의 `usage.raw_retention_days`, 기본 30일. 세션 mtime 기준으로 **마스터 원본 사본과 색인 줄만** 지운다.
  숫자 스냅샷은 남긴다(웹UI 과거 사용량 유지), 기간 지난 워커 파일은 다시 받지 않는다, 워커 원본은 건드리지 않는다.
- `/usage` 원형 그래프 = **모델 계열별 토큰 비율**, 화면 기간·프로젝트 필터를 따르되 항상 `source=all`.
  서브 에이전트가 **계열 필터는 따르지 않게** 판단 → 사용자 「그대로 둬. 버그로 레드마인에 등록하고」 → **#736**.

**구현 (로컬 서브 에이전트) — 커밋 `d0ba940`**: `config.py` `Registry.raw_retention_days()`(잘못된 값은 fail-closed: 그 실행은
정리·거름 없이 수집만, 경고 로그 · `save()` 가 `usage` 키 보존함을 검사로 확인) · `session_usage.py` `prune_raw`, 목록 단계 mtime 거름,
CLI `--prune [--dry-run]` · `usage_page.py` 도넛(인라인 SVG) + 대체 표. 라이브 `projects.yaml` 에 키 추가(gitignore, 기존 바이트 동일).
검사: session_usage 19/19 · usage_page 8/8 · usage_dashboard 9/9 · routes 5/5 · nav 2/2 · cli_paths 40/40 · test_projects 76/76.

**배포·라이브**: push · `ax-projects` 재기동 00:06:03. `/usage` 진입 → 「보존 정리 — 기준일 2026-09-05 · 정리 22 · 4,808,957바이트 · 오류 0」,
기간 지난 원격 22개 재전송 안 함, 색인 648 · 스냅샷 691(유지), 도넛 표시.

**update**: `5fc6786` 실행은 도중 인계서 커밋 `4ac3099` 로 HEAD 가 움직여 ModularStage 검사 2건 「출처 1커밋 뒤」 → rc 1(**#737** 등록).
`d0ba940` 로 워커 4곳 ff-only 뒤 재실행 → **rc 0 · 15/15 OK**. [주의] update 실행 중에는 커밋하지 않는다(#737 해결 전 우회).

**남은 것**: #735 는 사용자 지시로 **완료 종결**(00:23 KST, 종결 노트에 커밋 5개 기록). #736·#737 미착수. 이전 열린 일감(#714·#666 운영 검증, #726·#727·#733 등)은 그대로.

### 최신 — #735 후속: 마스터 귀속 · 「모두 보기」 · 전체 최신화 (2026-10-04 23:50, Claude)

**사용자 결정**:
- *"마스터 세션은 ~/ax-cluster 면 AXCluster 로 귀속해"* → `session_usage.MASTER_CHECKOUTS`(레지스트리에 없으면 잇지 않고 로그).
  실 저장소 `--reparse`: 669 사본 중 local 39건 이동. 남은 local 미분류 99(cwd `/home/sim` 82 · `/tmp` 임시).
- 웹UI 소스에 **「모두 보기」(`source=all`)** 추가 — **계열별 출처 하나**(사용자 선택): claude·codex 는 대화 세션,
  gemini·local·unknown 은 작업 실행 기록. 근거: 워커 `codex exec` 파견이 그 기계 세션 파일에도 남는다
  (10/4 16:55 파견 4건을 워커 세션 사본에서 확인) → 단순 합산은 이중 계산. `all` 의 issues 는 빈 표.

**진단 메모** — 사용자 질문 「10/4 Claude · 10/3 Codex 가 없다」: 기본 소스 「작업 실행 기록」 기준이라 정상.
10/4 파견 4건은 모두 codex 모드, 10/3 codex 파견 3건(20:42)은 `measured:false` 실패 시도. 대화 세션엔 두 날 모두 두 계열 있음.

**커밋·배포** (각각 사용자 승인): `a5cc306`(마스터 귀속) · `5fc6786`(모두 보기). Gitea push, 로컬·원격 일치.
`ax-projects` 재기동 23:22:07 → 23:42:52 active. 라이브 `/api/v1/usage?source=all`(10/4) 1,748회 · 2.54억 토큰, `/usage` 에 「모두 보기」 표시.
검사: session_usage 13/13 · usage_dashboard 9/9 · usage_page 4/4 · usage_routes 5/5 · 통합 20/20.

**워커 최신화**:
- `a5cc306` 때 `master.client update` rc 0(5프로젝트 배달·검사 OK). [주의] **update 는 워커 체크아웃을 당기지 않았다** —
  `.43`/`.2` `66a7a1f`, `.33` `d061598` 에 머물러 있었다. 그래서 체크아웃은 main·clean 확인 후 `fetch` + `merge --ff-only` 로 따로 맞췄다.
- 현재 `.43 ~/ax-cluster` · `.43 ~/trunk/AXCluster` · `.2 E:\trunk\AXCluster` · `.33 C:\trunk\AXCluster` 모두 `5fc6786`.
- 🔴 `5fc6786` 기준 `master.client update` 를 백그라운드로 다시 돌리는 중(23:43 시작, 출력은 끝나야 나온다). **결과 미확인** —
  다음 지휘자는 rc 와 「[완료] 등록 프로젝트 5개」 줄을 확인하거나 다시 돌린다. 게임 프로젝트 체크아웃은 당기지 않았다(게임 소스 트리).

**남은 것 (미승인)**: 원본 사본 보존 정책. #735 는 열어 둔다(종결은 사용자 판단).

### 최신 — #735 세션 원본 로그 증분 수집 완료·배포 (2026-10-04 23:10, Claude)

**사용자 결정 (이 세션)**:

- Claude 인수(「응 클로드로 인수하고 로컬 서브 에이전트로 진행해」) → `record_master_conductor('claude')` 22:27:47.
- 보관 구조 **프로젝트/워커IP/도구** 선택: `~/ax-state/usage/raw/<프로젝트|_unassigned>/<IP|local>/<claude|codex>/<원본 상대경로>`
  + `raw/index.jsonl`(project·work_id·task_id·host·tool·origin·cwd·size·mtime·sha256). work 는 디렉토리 단계가 아니다.
- 진행 중 파일: **크기·mtime 이 바뀌면 통째로 재복사**(원자적 교체). 원격은 읽기 전용, 워커 원본 삭제는 범위 밖.
- Redmine 일감 **#735** 생성(ax-cluster · 코드리뷰 · 마일스톤 6). 노트 3건(구현·배포·후속).

**구현 (`8c1c93e`)**: `master/work/session_usage.py`(원본 증분 복사 · cwd↔`workshops.<host>.path` 최장 접두 귀속 ·
`.ax/work/<task_id>` 일 때만 task/work · 원본에서 숫자 스냅샷 재생성 · flock · `--reparse` · `refresh_in_background`) ·
`usage_dashboard.py`(session 프로젝트 필터) · `webui/app.py`(/usage 진입 시 배경 수집, 잠금 · 최소 5분) · 테스트 `test_session_usage.py` 12건 신규.
CLI: `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.work.session_usage all [--reparse]` — rc 2 = 레지스트리 못 읽음.

**실측에서 찾은 결함**: `.33` Windows tar 에 stdin 파일 목록 22.7KB 를 주면 0바이트로 멈춘다 → 묶음당 8KB(`STDIN_BUDGET`) + 마스터 쪽 ssh 감시 타이머.
측정 중 `.33` 에 남은 `tar.exe` 2개는 사용자 승인으로 `taskkill`, 재조회 0개.

**배포·검증**:
- crontab 04:17 수집 줄에 `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 추가(없으면 새 코드에서 rc 2).
- `ax-projects` 재기동 22:55:53 → 23:03:44(후속 `ecb395b` 반영). 8103 은 ax-projects 가 서비스하며 `AX_PROJECTS_ROOT` 가 있다.
- 라이브: `/api/v1/usage` 응답 0.72초, 배경 수집 15.2초 · 4대·2도구 669파일 ≈526MB · 오류 0 · 실 저장소에 AXCluster·KimodoMotion_WebUI·ModularStage·NS·_unassigned 생성.
  session·codex·2026-10-04 집계 **calls 0 → 831 · tokens 92,847,955**. 45초 뒤 재진입은 「간격 < 300초」로 건너뜀.
- 후속 `ecb395b`: `usage_page.py` session 안내 문구 정정 · `tests/integration/checks.json` 에 `test_session_usage.py` 등록(20개). 통합 20/20.

**남은 것 (미승인 — 인계만으로 진행하지 않는다)**:
- 마스터 local 세션은 등록 작업장이 아니라 전부 `_unassigned`. 귀속 규칙(예: cwd `~/ax-cluster` → AXCluster)은 사용자 결정.
- 원본 사본 보존 정책 없음(무기한 누적). `.33` codex 235건 중 226건은 cwd 가 `AppData\Local\Temp` 라 `_unassigned`.
- #714·#666 운영 검증, #726·#727·#733 등 이전 열린 일감은 그대로.

### 최신 — Codex 사용량 미표시 진단 · 원본 로그 캐싱 요청 (2026-10-04 22:19, Codex)

**사용자 목표·결정**:

- 사용자가 「왜 코덱스 작업한 토큰양 웹UI에 적용 안되고 있어」 → 「페이지가 열릴 때 갱신」 제안.
- 모든 워커 로그를 마스터에 캐싱, 이미 다운로드한 파일은 스킵하고 없는 파일만 가져오라는 지시.
  기록 중인 파일의 변경 갱신은 지휘자가 제안한 방식이며 세부 계약은 아직 구현 전이다.
- 사용자는 토큰 숫자뿐 아니라 **대화 내역을 분석할 수 있도록 원본 전체 수집**을 요청했고,
  마지막 지시는 「다 내 컴퓨터니 … 그대로 복사해와. 프로젝트/작업 워커의 IP 기준으로 디렉토리 정리해서 수집」.
  원본 내용은 그대로 복사한다. 추가 비밀값 마스킹 정책을 사용자에게 다시 요구하지 않는다.
- 워커 수집 후 원본 제거도 사용자가 아이디어로 언급했으나 이번에는 복사·수집만 범위로 안내했다.
  원격 원본 삭제는 실행하지 않았고 삭제 조건도 확정되지 않았다. 인계만으로 삭제하지 않는다.

**실제 진단 결과**:

- 기존 `master/work/session_usage.py`: Claude/Codex 홈 jsonl을 로컬 또는 원격 tar 스트림으로
  전부 읽고, `~/ax-state/usage/sessions/<host>/<tool>/*.json`에 **토큰 숫자만** 적립한다.
  원본 파일 캐시·이미 받은 파일 다운로드 생략·프로젝트/work 귀속 기능은 없다.
  기존 CLI는 `.venv/bin/python -m master.work.session_usage [local|IP ...]`지만 현재 요구의
  원본 복사·증분 수집을 수행하지 못하므로 아직 실행하지 않았다. 임시 대체 스크립트도 만들지 않았다.
- `master/work/usage_dashboard.py`는 위 숫자 스냅샷만 읽으며 수집을 호출하지 않는다.
  `master/webui/app.py`의 `/usage`·`/api/v1/usage` 역시 조회만 한다.
  기본 source=dispatch(작업 실행 기록), source=session(대화 세션 기록)은 별도이며 중복 합산 금지.
  현재 session 자료는 프로젝트·일감 귀속이 없고 project 필터를 걸면 해당 자료가 없다.
- 마스터 Codex 원본 오늘 로그는 존재. 기존 `parse_codex`로 숫자만 출력해 20:33 시작 마스터
  세션의 레코드202건, 입력25,604,440·출력54,677 확인(13:05:47Z 시점, 이후 계속 자람).
  21:48 서브 에이전트 세션도19건 확인. 대화 본문은 진단 로그에 출력하지 않았다.
- 적립 저장소의 Codex 스냅샷 검색은 매칭0. 실제 웹UI API
  `/api/v1/usage?source=session&family=codex&start=2026-10-04&end=2026-10-04`
  응답200, calls0·tokens=null·buckets/models비어 있음·read_errors0 확인.
- 등록된 systemd 타이머22개에 세션 수집 타이머 없음. timer/API 첫 샌드박스 조회는 막혔고
  승인된 **동일 읽기 명령**으로 sandbox 밖에서 재조회해 확인했다. 서비스 장애로 단정하지 않는다.

**조사·실행 방식 및 바로 다음 작업**:

- `master/skills/distribute/SKILL.md`와 실제 소스 대조. 현재 AX RAG MCP 도구가 노출되지 않음.
  새 기능 작업의 실제 소스 대조 사용과 **로컬 서브 에이전트 / AX 워커 분산** 선택을 질문했고
  아직 사용자 답변이 없다. 사용자는 대신 이 인계 작성을 요청했다. 선택 답변 전에는 구현·위임하지 않는다.
- 등록 정보 조회는 기존 `Registry.load()`로 완료: 프로젝트 ModularStage·NS·KimodoMotion_WebUI·
  MotionForge·AXCluster, active=AXCluster. 워커 IP `.2`(janus)·`.33`(user)·`.43`(sim).
  게임 프로젝트의 `.33`은 requester이기도 하므로 역할을 전역으로 추정하지 않는다.
- 지휘자 제안은 `프로젝트/작업/워커 IP/도구/원본 경로` 순서 보관, 실제 귀속을 확인할 수 없는
  로그는 미분류 보관, 동일 파일 스킵·변경 중 파일 갱신·캐시로부터 토큰 집계 및 페이지 진입 갱신 연결.
  이 세부 배치와 갱신 계약은 **제안**이며 실제 확정·구현은 다음 단계다. 모든 세션을 active프로젝트에
  임의 배정하지 않는다. 중복다운로드·중복집계·부분복사·진행중파일을 검증할 필요가 있다.
- 확장 대상 후보는 기존 session_usage.py·usage_dashboard.py·webui/app.py·usage_page.py와
  관련 검사다. 새 등록 일감·코드 변경·원본 복사·웹UI 수집 연결 모두 아직 없음.
- 모든 로컬 구현/리뷰 에이전트는 앞선 버그 작업을 완료했다. 이 새 작업에 배정된 에이전트는 없다.
  새 AX 파견·워커 재배달·원격 삭제·강제 종료를 실행하지 않았다. 큐 실행 상태는 이번 인계에서 미조회.
- 다음 지휘자는 세션 시작 AGENTS와 ax-handoff를 먼저 읽고 실제 경로 목록과 소스를 대조한다.
  등록 스킬 기존 도구를 사용한다. 호출 계약이 불명확하면 사용자에게 묻고 임시 스크립트로 우회하지 않는다.
  커밋·push는 매번 승인. 문서 한 벌만 유지하고 홈 AGENTS/CLAUDE 심볼릭 링크를 보존한다.

### 최신 — #715 종결 · #714/#666 로컬 수정 (2026-10-04, Codex)

- 실제 분류는 트래커 `코드리뷰`, 버전 `버그·개선`이다. AX 열린 3건, ModularStage 열린 0건 확인.
- #715: 현재 구현·회귀28/28·이전 실물 분배 기록을 대조해 사용자 지시로 완료100% 종결·재조회.
- #714·#666: 사용자 선택으로 로컬 서브 에이전트 2명 구현·1명 독립 리뷰 완료.
  AX RAG 도구가 없어 일감 본문·실제 소스 대조 사용. 기존 스풀 API 연결과 좁은 구분선 복구.
  코드 변경은 consumer.py·test_events.py·context_synth/md.py·test_context_synth.py 4파일.
- 담당 검사 events57/57·indexer103/103·gate17/17·context_synth135/135,
  지휘자 정본 통합19/19·diff 검사 통과. 운영 스풀 소비·실제 모델 합성·배포는 미검증.
- 사용자 「드라이런하자」 후 지휘자 기존 검사4종 재실행 **312/312**, rc 모두0.
  운영 claimed 이벤트3개 목록·SHA256, conductor/mode SHA256, projects/broker PID·기동시각,
  Git diff SHA256 전후 동일. related 환경변수·브로커 조회 경고는 있었으며 주입 LLM 검사다.
  검사 후 이 문서·리포트93에 결과만 추가했다.
- 기록: [리포트93](../reports/93-spool-recovery-and-frontmatter-repair.md).
  #714·#666은 운영 검증이 남아 열어 둔다. 드라이런 후 사용자 커밋·push 승인.
  **게시 완료**: `d2c0619` 커밋·Gitea push, 로컬·원격 HEAD 일치·clean 확인.
  Redmine #714·#666에는 구현·검사·미배포 노트 기록, 마지막 재조회 상태 신규0%.
  이후 운영 검증·종결·Redmine 재조회는 하지 않았다. #715는 완료100% 확인.
  운영 스풀 정리·서비스 재시작·새 AX 파견은 하지 않았다.

### 최신 — Codex 인수 · 워커 Codex 전환 · 인수인계 스킬 추출 (2026-10-04, Codex)

- 문서 최신화 후 경로 재발 방지 절차를 홈/저장소 AGENTS 정본에 추가:
  확인된 작업 위치에서 `rg --files -g 패턴` 목록 조회 → 별도 호출에서 반환된 실제 경로만 읽기.
  미확인 디렉터리를 목록 조회 인자로 넣지 않으며, 같은 절차를 서브 에이전트 지시에 명시한다.
  AGENTS.md, machines/sim-desktop-agents.md, README.md, master/README.md,
  이 인수인계서의 5파일을 `f215837`로 로컬 커밋했다. push·배포는 중단된 상태다.
  홈 AGENTS/CLAUDE 심볼릭 링크를 보존한다. 인수인계는
  `master/skills/ax-handoff/SKILL.md`의 절차로 이 파일 한 벌을 갱신한다.
  기존 스킬 기능을 과거 임시 산출물에 의존하는 실행 절차로 바꾸지 않는다.
  배달이 다시 요청되면 `master/skills/distribute/SKILL.md`와
  `docs/14-onboarding-runbook.md` §3을 따른다. 소스 동기화와 배달은 별도 단계이며
  등록 전체 배달·검사 명령은 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`다.
- 이번 문서 재개: 앞서 승인한 실제 소스 대조·로컬 서브 에이전트 방식을 유지한다.
  README·master/README·홈/저장소 AGENTS·CLAUDE 진입 문서와 이 파일만 대상으로 한다.
  7파일 최신화 완료·미커밋. 인수인계/모드 선택의 정본 스킬 연결, 새 work 기본값과
  기존 스탬프 유지, 로컬/원격 커밋 차이와 미배포 상태를 바로잡았다.
  서브 에이전트는 진입 문서 4파일을 담당했고 종료했다. 지휘자가 실제 diff를 재검토했다.
  검증: `git diff --check` rc0, 지휘자 확인 문서 링크 7/7·에이전트 확인 관련 링크 12/12,
  홈 AGENTS/CLAUDE 심볼릭 링크 보존 확인. 문서 변경이라 코드 검사는 추가 실행하지 않았다.
  상태 조회 `conductor.snapshot()`에서 master=codex, worker=codex/source=state,
  마지막 저장 20:52:56을 재확인했다. readiness 3/3은 앞선 전환 당시 결과이며
  이번 문서 작업에서 새 원격 실행·readiness·서비스 검사·Redmine 변경은 하지 않았다.
- 사용자 보충으로 #733 후속을 인수했다. 실제 `HEAD=origin/main=d020132`, 편집 전 clean 확인.
  `master/test_usage_cli_paths.py`의 checks.json 등록·출력 패턴 확인. **통합 19/19(신규 40건),
  Redmine #733 노트·열림 및 #734 신규 등록은 사용자 인계 내용이며 이번 세션에서 재조회하지 않았다.**
- #728은 앞 절의 실제 Antigravity 리뷰 기록(입력 29,589·출력 11,598, 합 41,187) 확인으로 완료.
  #733은 실제 Claude JSON 호출·게시판·층2 기록 확인이 남았다. #734는 현재
  `master/projects/mcp_server.py`의 `get_code()`가 `generate.dispatch()`의 필수 `context`를
  빠뜨리는 것을 소스로 확인했다. 경로 사용 여부와 유지/제거 판단은 미착수.
- `ax-projects` 실조회: MainPID 139669, 20:33:53 기동, active/running, Result=success.
  이번 세션에서 재시작하지 않았다. HTTP 화면 200은 사용자 인계 내용이며 재조회하지 않았다.
- 사용자 「클로드 토큰을 모두 사용했으니 워커들도 모두 코덱스」 지시.
  현재 세션에 AX MCP 없음; ax-mode의 직접 fallback와 실제 MCP 호출 경로 차이를 보고했고,
  사용자 승인으로 정본 `conductor.set_worker('codex', why=…, by='codex')` 사용.
  첫 sandbox 호출은 scp 읽기 실패(BundleError); 승인된 동일 명령을 sandbox 밖에서 실행해
  **20:42:28 Codex 전환**, AXCluster `.43`·`.2`·`.33` readiness **3/3**, Codex 0.159.3.
  readiness는 배달물·예약 런처 등록 검사이며 실제 로그인/셸/편집 실행 성공 검사는 아니다.
- `conductor.record_master('codex', …)` 20:43:36 실행 후 snapshot 재조회:
  master=codex, worker=codex, source=state. 담당 기록은 잠금/프로세스 판정이 아니다.
  **새 work 등재부터 Codex 스탬프**. 기존 work의 모드를 소급 변경하거나 새 파견을 하지 않았다.
- 사용자 「인수인계와 워커 지휘자 선택을 스킬로」 요청. 이번 작업에 한해 RAG MCP 부재를
  실제 소스 대조로 대신하고 **로컬 서브 에이전트 방식** 승인.
  `master/skills/ax-handoff/SKILL.md` 신규·`ax-mode` fallback 정정·홈/저장소 진입 지침 연결 완료.
  두 스킬 quick_validate rc0, git diff --check rc0. Claude 홈·Codex legacy/공식 홈 경로의
  ax-handoff 심볼릭 링크가 같은 저장소 정본을 가리킴을 확인했다. 홈 AGENTS/CLAUDE 링크 보존.
  Codex 홈 등록 첫 시도는 sandbox read-only로 실패해 승인된 좁은 등록 스크립트로 완료했다.
  독립 검토: 인수인계만 확인할 때 쓰기 없음·Codex 선택 시 준비 검사·실제 호출 이름 일치 확인.
  추가 조회에 없는 경로를 넣어 rc2가 된 에이전트 조회 실수가 있어 그 추가 조사는 중단했다.
  새 스킬은 work 스탬프 계약을 명시한다. machines/sim-desktop.md의 옛 「다음 조각부터」
  설명 두 곳도 이번 문서 최신화에서 실제 계약에 맞게 고쳤다. 전체 통합 검사는 이번에 재실행하지 않았다.
  드라이런 시점에는 커밋·푸시 승인이 없었다. 후속 사용자 요청으로 이 7파일의 커밋·Gitea push와
  ax-mode Codex 설정 재호출을 승인받았다. 서비스 재기동·워커 재배달·신규 파견은 요청하지 않았다.
- 사용자 「드라이런 먼저」 요청 후 기존 정본 검사만 격리 실행:
  `.venv/bin/python -B -m unittest master.test_orchestration_control master.test_worker_mode_transport -v`
  **21/21**(control 18·transport 3), `.venv/bin/python -B master/test_work_mode_stamp.py` **15/15**.
  실제 준비 검사에는 가짜 워커/런처 응답을 주입하고 상태·큐는 임시 환경을 사용한다.
  준비 실패 저장 차단·마스터/워커 분리·환경 우선순위·모드 전달·기존 work 스탬프 유지 확인.
  검사 전후 운영 conductor.json/mode.json SHA256, snapshot, git status 및 diff SHA256 모두 동일.
  이후 이 결과 기록만 인계서에 추가했다. 실제 원격 작업·파견·서비스 변경은 실행하지 않았다.
  독립 스킬 판단 드라이런 4상황 확인: 인계 조회만/명시 Codex 선택/.2 준비 실패/
  전역 Codex+기존 Claude round 2. 형식 검사뿐 아니라 호출 선택·승인/중단·스탬프 경계를 검토했다.
  실제 새 Claude/Codex 세션의 자동 스킬 선택·원격 셸 실행까지 검증한 것은 아니다.

### 최신 — 색인기 막힘 해소 · #732 완료 (2026-10-04 18:12, Claude)

- 수동 재합성 루프(`scratchpad/unstick.sh`)는 17:48 `a8b033b` 에서 **형식이 아닌 사실 게이트 거부**로 설계대로 중단했다.
  거부: `master/webui/routes` 「주석에만 있는 식별자: `_CONTEXT_SHELL_CSS`, `_SIDE_VARS`」 — 실제 코드 상수(routes.py:109·114).
  gemma3:12b 1회 재합성도 같은 거부 → 모델 문제 아님.
- 원인(재현): `verify.strip_comments` 가 C++ 전용이라 파이썬 주석 `# … static/*.html` 의 `/*` 를 블록 주석으로 읽어 뒤 코드를 삼켰다.
- 사용자 결정: 파일 종류별 규칙(C/C++·C#·Java·Python·HTML(규칙만)·XML·INI·JSON/.uplugin/.uproject) · 모르는 확장자는
  「주석에만 있는 식별자」 판정 생략(a) · 로컬 서브 에이전트. `synth.py` 프로젝트 live 집합도 같은 규칙(사용자 승인).
- `fc9c4de` push → 색인기가 **사람 개입 없이** routes 를 gemma4:e4b 로 통과 → 커서 HEAD · 리뷰 큐 pending 0 · done 31 · abandoned 15.
  워커 조각 4개·`e3b1513`·`d548b40`·`a8b033b`·`fc9c4de` 리뷰 완료(조각 지적: usage_page 1 · usage_dashboard 2).
  #732 노트 2건 + 「완료」 처리(사용자 「닫고」).
- 남은 한계(#732 노트): HTML 속성값 안 `<!--` · `.hh/.hxx/.cxx` 미등록 · INI `#` 줄은 근거 미확인으로 live.

**미결 / 다음 (최신)**:

1. [부분 확인 18:3x] `/ontology`·`/ontology/domain/Any` 를 Chrome(2560×945)으로 봤다 — 사이드 메뉴 7항목·`.on` 정상,
   원전 트리·패널·버튼 유지, 가로·세로 스크롤 없음, 그래프 영역 x=800~2560(1760×945) · 컨트롤 버튼 정위치.
   **미확인**: 실제 그래프 렌더링(AXCluster 는 `domains: []` — 데이터 없음, 마운트 전환 필요) ·
   760px 미만 배치(창 크기 변경 요청이 적용되지 않음 — 최대화 추정).
2. `fix_flow prepare` fetch 미강제 — 수정/일감화 미결.
3. [완료] 워커 3대·`.43` 관리 클론 `66a7a1f` 동기화 + 배달 3/3 · `.2` MCP 경고는 오탐 — `3e46078` 수정(다음 배달에서 소멸 확인).
4. #726 · #727 · #728 미착수. [완료] `d189f21` — `checks.json` 에 `test_usage_*` 4·`test_webui_side_nav`·`test_verify_filetypes`
   등록, 통합 검사 **18/18**. 그 5개 unittest 모듈은 스크립트 단독 실행 시 `No module named 'master'` 로 죽었다 — 다른
   테스트와 같은 `sys.path.insert(…parents[1])` 를 넣었다(`-m unittest` 23/23 유지).
   [완료] **Antigravity 토큰 기록**(#728, `8d67744`) — `call_agy_why` 를 `--output-format json` 으로 부르고 sink 안이면
   호출당 1행 · 리뷰 퇴고를 초고와 같은 sink 로 · 대시보드는 lane agy → gemini `Antigravity(모델 미상)`(agy JSON 에
   모델 키 없음 — 실측 agy 1.2.16). ax-projects 20:12:57 재기동. **라이브**: R34(`8d67744` 리뷰) → usage_log
   lane=agy · 입력 29,589 · 출력 11,598(추론 10,800) · `/api/v1/usage` gemini 1건 41,187. sink 밖 경로는 **#733** 로 분리.
5. `advance_work(confirm=True)` 트리 수정 소실 문제 미결 · 옛 로컬 브랜치 `task/20261003_2315_719…/base` 잔존 ·
   `.43 .ax/work` 잔재 2개 · 위키 [[아이디어수집]] 에 #729~#731 절 미기재(쓰기 경로 없음 · API 401).

### 최신 — #725 후속: 분류·사이드 메뉴 배포 · 색인기 막힘 · 일감 3건 (2026-10-04 17:46, Claude)

**배포 (사용자 「a-1로 하고 ① 같이 고쳐줘, 로컬 서브 에이전트로」 → 「커밋하고 푸시하고 배포해줘」)**:

- 로컬 서브 에이전트 2개(파일 비중첩) → 제가 합친 상태로 재검사: 웹UI 6파일 rc=0 · 사용량+새 메뉴 23/23 · 통합 12/12.
- `d548b40 fix(usage): classify dispatch records by conductor mode` — `mode`(claude/codex)를 model·lane 이 둘 다 빌 때만
  쓴다. 실데이터 9/1~10/4: unknown 16 → **claude 16**(캐시 포함 5,642,553 토큰).
- `a8b033b feat(webui): shared side nav on every page` — `/`·`/ontology*`·`/cluster` 는 `routes.wrap_side_nav` 로
  **서빙 시점** 감싼다(원전 `web_ui_original.py`·`static/` 바이트 불변, 2026-08-13 지시 유지) · `/reviews` 는 공용 셸.
  `status.py` 미수정(`cluster.html` 자족·외부 자원 0 테스트). 예전 주입 링크 버튼은 제거, 원전 바이트 속 링크는 남김.
  새 테스트 `master/test_webui_side_nav.py`.
- [주의] **브라우저 확인 안 했다** — `/ontology` 그래프(100vh)가 230px 좁아진 열에서 적응하는지, 760px 미만에서
  메뉴가 위로 쌓여 스크롤이 생기는 것, 메뉴 배경 `#161b22` vs 원전 `#1e1e1e`.

**`.2`·`.43` 동기화 질문 (사용자 「리뷰 작업 시작할 때 풀 받는거야?」)**: 두 워커 체크아웃 모두 `3d54637`(origin 추적도
같음, fetch 이후 없음). 파견은 `wcommit.py:135` 가 `fetch --all` 뒤 base 커밋에서 새로 가르므로 무관. `ax-fix` 는
`check` 가 `fetch origin main` 후 `origin/main` 대조(`fix_flow.py:233`) — 그러나 **`prepare` 는 스스로 fetch 하지
않는다**(`fix_flow.py:350`) · 순서를 코드가 강제하지 않는다. 고칠지·일감화 **미결**. `.43 .ax/work` 에 조각 아닌
잔재 2개(`ax_smoke_…` 10/3 12:14 · `ax_codex_readiness_…` 10/3 23:51) — 원인 미조사.

**색인기 막힘 (`#727`)**: `master/webui/app` 합성이 gemma4:e4b 에서 형식 게이트(frontmatter 누락)로 5회 중 4회 거부 →
커밋 단위 트랜잭션이라 커서가 멈춰 뒤 커밋의 합성·**자동 리뷰 등재**가 막혔다. 사용자 「2번」 → 「가로 진행」:
멈출 때마다 그 그룹만 `synth.run(changed=[app.py], commit=<멈춘 커밋>, model=FALLBACK_MODEL gemma3:12b)` 로
수동 재합성. 루프 스크립트 `scratchpad/unstick.sh`(색인 실행 → 형식 거부면 재합성 → 반복; 같은 커밋 재정지·비형식
사유·15회면 중단). 17:44 시점 커서 `e3b1513` · 리뷰 큐 pending 5 · running 1 · done 26 · abandoned 10.
수동 문서는 품질이 낮다(태그 줄에 `영문태그:` 잔재 · `UViewApp` 실재 미확인).
[주의] `3abcdb1a` 는 `app.py` 를 안 바꿨는데 `app` 그룹이 대상이 됐다 — 형제 커밋 순회 시 비교 기준 문제로 보이나 미검증.

**자동 리뷰 (질문 「분산 작업 끝내고 커밋했는데 자동 리뷰 시작해?」)**: 색인기가 커밋을 걸으며 리뷰 큐에 등재 →
`ax-review-queue` 가 로컬 초고 + **Antigravity 퇴고**. 작성자 `ax-cluster`(ADVANCE·머지)는 제외(abandoned)가 정상.
`f6f5aecb` 리뷰는 「행 0」(지적 0건)으로 저장됐다.

**토큰·agy (`#728`)**: 대시보드 gemini 0건은 화면이 아니라 기록 부재 — `review_runner.py:383` 의 `usage.sink` 가
초고만 감싸고 agy 퇴고(:396)·층2(`layer2_verify.py:128`)는 기록 경로가 없다.
마스터 대화 세션의 Claude 사용량은 `/usage?source=session` 에만 보인다(두 소스는 겹칠 수 있어 합산 안 함).

**미결 / 다음 (이 절)**:

1. 색인기 루프 결과 확인 → 리뷰 큐 상태 보고(사용자 요청 대기 중).
2. `/ontology` 등 사이드 메뉴 화면 브라우저 확인.
3. `fix_flow prepare` fetch 미강제 — 수정/일감화 미결.
4. 워커 3대 `master.client update`(ff-only + 재배달) 미실행 — 사용자 승인 필요.
5. #726 · #727 · #728 미착수 · `checks.json` 에 `test_usage_*`·`test_webui_side_nav` 미등록 ·
   `advance_work(confirm=True)` 트리 수정 소실 문제 미결 · 옛 로컬 브랜치 `task/20261003_2315_719…/base` 잔존.

### 최신 — #725 사용량 웹페이지 라운드 1 전진·마감·배포 · 지휘자 claude 전환 (2026-10-04 17:20, Claude)

**경위**: Codex 가 `#725`(「[AX] LLM 모델별 기간별 작업·토큰 사용량 웹페이지」)를 등재·파견한 뒤
이 문서를 갱신하기 전에 토큰이 소진됐다. 원요청: 레드마인 일감 기준 LLM(클로드·코덱스·제미나이·로컬)의
일간·주간·월간 작업과 토큰을 웹UI 신규 페이지로 시각화.

**work**: `20261004_1645_ax_llm_e6a404f5` · round 1 · 조각 4(codex 지휘) · 파견 4/4 · 실패 0 · 16:58:30 `ready_for_review`.

| 조각 | 워커 | 파일 |
|---|---|---|
| 0747b703 | .33 | `master/work/usage_dashboard.py` + `master/test_usage_dashboard.py` |
| d74ea13e | .43 | `master/webui/usage_page.py` + `master/test_usage_page.py` |
| 84fe23ff | .2 | `master/webui/app.py` + `master/test_usage_routes.py` |
| adb7d5fb | .2 | `master/webui/nav.py` + `master/test_usage_nav.py` |

**⑺ 전진 (사용자 「머지하고 검사 진행해줘」 → 「a로 고치고 재검사해줘」 → 「커밋하고 전진해줘」)**:

- `advance_work(confirm=False)` 로 4조각 머지 — 충돌 0, `610fdf4 → 75f70cc`.
- 사용량 테스트 13/15 — 실패 2, 둘 다 테스트 쪽 버그:
  ① 주간 9/28 기대값 4 → 3 (골조 계약 start/end 양끝 포함상 9/30 호출은 범위 밖 — 구현이 맞다)
  ② 400 안내 문구 검사 「잘못」 → 「올바르지」 (같은 조각의 테스트·구현 불일치).
- 수정 커밋 `e3b1513` · 재검사: 사용량 15/15 · `tests/integration` 12/12 · 웹UI 관련 회귀 18파일 통과.
- `task/20261004_1645_ax_llm_e6a404f5/base` **`610fdf4 → e3b1513` push**(fast-forward, force 없음) ·
  레드마인 #725 전진 노트(서버 ok:true). 검수 트리 `~/ax-advance-…` 는 지웠다.
- [주의] 테스트 실행법: `master` 는 패키지가 아니다. `unittest discover -s master` 는 상대 import 를
  깨뜨려 가짜 오류 3건을 낸다 — 저장소 루트에서 `python -B -m unittest master.test_usage_…` 로 돈다.

🔴 [주의] **`advance_work(confirm=True)` 는 트리 안 수정 커밋을 잃는다** — 재호출 시 검수 트리를
`worktree remove --force` 하고 origin 에서 재머지한다. `ax-advance` 스킬의 「버그면 이 트리에서 고쳐
커밋 → confirm=True」 순서는 현 코드로 성립하지 않는다. 이번엔 그 함수가 내준 push 명령을 손으로
실행했다. **고칠지·일감화할지는 사용자 미결.**

**토큰 (usage_log.jsonl, codex 지휘)**: 입력 합 4,054,512 중 캐시 3,814,144(94%) · 비캐시 약 24만
(조각당 5~7만) · 출력 약 1.7만. 누적 재전송은 에이전트 루프 공통(claude 도 같다). 원본 실행 기록은
남지 않아 사후 분해 불가 → **#726** 등록(측정 로그: 첫 턴 입력·턴 수·턴별 비캐시·읽은 파일,
codex·claude 비교표가 완료 조건). 착수 안 함.

**마감 (사용자 「#725 마감해줘」 → 「1~3 모두 진행해줘」)**:

- `finalize_work(confirm=False)` 로 먼저 통합 — `e3b1513` 포함 확인 · 8파일 +1,274 · 사용량 15/15 ·
  `tests/integration` 12/12 · 웹UI 회귀 6파일 rc=0. 그 뒤 `confirm=True`.
- **main `99147c4`** push · 큐 `merged` · 레드마인 #725 **완료**(마감 노트에 머지 커밋) ·
  원격 `task/20261004_1645_ax_llm_e6a404f5/*` 5개 삭제(전부 main 도달 가능, 잔존 0).
  조각 4개는 base 에 이미 든 상태라 「매니페스트 전용 — 머지 안 함」으로 찍힌다(정상).
- 마스터 체크아웃 `git pull --ff-only` (`6bb8a23 → 99147c4`) · `sudo -n systemctl restart ax-projects`
  (rc=124 polkit 대기였으나 ExecMainStartTimestamp 17:16:22 · 새 PID 로 판정 — 성공).
- `/api/v1/usage` 실데이터: 기본 30일(09-05~10-04) 호출 1,967 · 토큰 약 3,288만 · 연결 일감 13 ·
  **미연결 호출 1,899** — 대화 세션 사용분으로 추정하나 연결 규칙은 미검증.
- 정리: Codex 골조 worktree `~/ax-usage-…` 와 로컬 브랜치 `task/…/base`(`610fdf4`, main 포함 확인) 삭제.

**미결 / 다음**:

1. `test_usage_*` 4개는 `tests/integration/checks.json` 에 미등록.
2. `advance_work(confirm=True)` 가 트리 안 수정 커밋을 잃는 문제(위 🔴) — 고칠지·일감화 미결.
3. 미연결 호출 1,899건이 의도대로인지 확인.
4. 파견 로그의 `rmcp … 127.0.0.1:8000/mcp` 연결 오류(결과엔 영향 없음) — 원인 미조사.
5. `#726` 측정 로그 — 등록만, 미착수.
6. 옛 로컬 브랜치 `task/20261003_2315_719_target_files_316d6d14/base` 잔존 — 이번 작업과 무관해 두었다.

**진행 프로세스**: 파견·재기동 끝, 서브 에이전트 없음. 마스터 Codex 프로세스(pid 20028)는 17:20 재조회 시 없음(종료됨).

### R19 함수 정리·업로드/배포 승인 — 2026-10-04 후속

사용자 자동 리뷰 분석·상태 정리 뒤 R19의 lambda를 일반 함수로 수정하도록 승인했다.
로컬 구현/독립검토로 conductor.py의 value를 동일 동작의 지역 def로 정리,
메인 orchestration_control18/18 및 diff 검사 통과. R19-1 applied 기록됨.
「상태 변경하고 푸시하고 배포해줘」로 구현 커밋 연결·Gitea push·AXCluster3워커
소스동기화/배달 및 ax-projects 재시작을 승인받았다. 검증 근거는 리포트92,
실제 배포 결과는 #716 후속 노트로 대조한다.

### R9 수정·전체 드라이런 — 2026-10-04 후속

사용자 R9 검증→수정→로컬 서브 에이전트→드라이런→커밋/푸시/배포 승인,
조회 경로 오류로 중단한 뒤 「리뷰 상태도 변경해주고, 소스코드 올려」로 재개했다.
`infer.py` 상한 안내에 quota 제외 조건 추가, `test_infer.py` 실제 경로 회귀31건 추가.
infer154/154·revise64/64·독립 신규31/31·전체12모듈591건 통과.
기본 sandbox source_scope 실패는 승인된 동일 전체 검사 재실행으로 통과했다.
추가 메모리 역검증은 mock 연결 오류로 실패하여 성공 근거에서 제외했다.
리포트91은 배포 전 검증 기록이며 실제 업로드·워커 배달·서비스 반영 결과는 #716 후속 노트로 대조한다.
기존 c53cfc2 및 아래 종료 기록을 보존해 커밋·푸시하고, R9-1 applied 상태를 구현 커밋으로 기록한다.

### 세션 마감 — BC-250 종료 요청

사용자 「오늘은 여기까지 할게. BC250 꺼줘!」. 문서13개는 c53cfc2로 커밋 완료,
작업 트리 clean 확인; 이 커밋은 아직 푸시·재배달하지 않았다.
종료 전 실조회: 실행 중 큐 작업0, bc250 브로커 inflight0, 원격 Codex/Claude/Python/Node 프로세스0.
`.43`에 `sudo -n /usr/bin/systemctl poweroff` 실행 rc0. 이후 SSH 재조회는 접속 타임아웃으로
노드의 접속 종료를 확인했다. 다른 노드는 종료하지 않았다.
다음 세션에는 `.43` 전원을 켠 뒤 상태를 확인한다.
이 종료 기록은 c53cfc2 뒤의 미커밋 문서 변경이다.

### 최신 — R5 재검토·색인기 테스트 배포·문서 정리

**사용자 결정**: R5 검토→원인 조사→수정 승인→로컬 서브 에이전트 선택→드라이런→
「커밋 푸시 배포하자」→R5 재검토→「수정해줘」로 applied 처리→문서 최신화·인수인계 요청.
같은 작업의 로컬 방식을 문서 정리에도 유지했다. 이후 사용자 「커밋해줘!」로 문서 커밋 승인.
줄 끝 공백4곳을 정리하고 문서13개를 커밋한다. 푸시·재배달 승인은 받지 않았다.

**완료와 근거** ([리포트 90](../reports/90-r5-indexer-test-isolation-and-deployment.md)):

- R5는 골조493601d7 리뷰로, 지적10건은 후속 구현에 모두 반영돼 있다. 구현 커밋은 리포트90 표.
- 관련 첫 검사 indexer101/103의 원인은 초반 테스트가 실제 합성 브로커에 의존한 것.
  환경변수 설정+외부 호출 차단에서도 같은2건 실패, 성공 fixture 주입으로103/103 대조 실증.
- `master/test_indexer.py`만 코드 수정: 기존 synth_writes를 공용화, 성공 호출6곳에 명시적 주입.
  실패·NoChange·맞춤 합성·비활성화 검사는 보존. 운영 consumer의 스탬프 가드는 정상이다.
- 외부 연결 차단 직접 실행·manifest run_check 각각103/103, 연결 시도0.
  전체 통합12모듈560건 OK. 첫 실행 source_scope 실패는 sg gitea의 sandbox audit 제한;
  승인된 `/tmp/ax-r5-integration-dryrun.sh` 동일 검사 재실행으로 통과했다.
- b53fd84 커밋·Gitea push·ls-remote 확인. AXCluster3워커 main/clean 확인 후 ff-only 동기화,
  plan/deliver/check3/3 OK, payload10개·프로젝트 스킬·출처일치, 워크숍 소스clean3/3.
  `.2`의 기존 Claude MCP 대조 경고와 홈 중복 스킬 주의는 별개이며 Codex 프로젝트 설정은 통과했다.
- 배포 후 관련194/194 재검사. 사용자 승인으로 R5-1~10 모두applied 기록, 재조회10/10.
  `<twin>/fixes/index.json`은 런타임 정본, 다른 status 불변, 원본 리뷰 보존.
- Redmine #716에 종합 근거 노트를 기록·재조회 확인했고 상태는 신규로 유지했다.
  실조회 #718/#719/#722 완료, #716/#700/#701/#720/#721 신규.

**이번 문서 커밋 대상**: README.md, CLAUDE.md, AGENTS.md, machines/sim-desktop.md,
machines/sim-desktop-agents.md, master/README.md, docs/14-onboarding-runbook.md,
docs/windows-codex-remote.md, docs/orchestrator-rules.md, 이 인계서, reports/README.md,
reports/89-codex-worker-readiness-and-write-probes.md, 새 reports/90-r5-indexer-test-isolation-and-deployment.md.
홈 CLAUDE/AGENTS의 심볼릭 링크는 보존했다. 코드파일은 추가 변경하지 않았다.

**다음 세션**:

1. 위 main HEAD·문서 diff·R5 applied10건·Redmine 노트를 실제로 대조한다.
2. 이번 문서 커밋을 실제 git log로 확인하고, 푸시·재배달은 사용자 요청이 오면 실행한다.
3. #720 한도 이벤트 파싱, #721 Claude 인증 만료 검사, #716 완료 판단은 사용자가 선택한다.
   #700/#701은 코드 반영 기록과 별개로 Redmine이 신규라 완료로 단정하지 않는다.
4. `.ax` 쓰기 실패 근본 원인은 미확정. 세 워커 도구 실증을 새로운 Codex 분산 work의
   큐 등재~통합~finalize 완주로 확대하지 않는다. #719 다중 파일 조각 워커 완주도 미검증이다.

**진행 프로세스·에이전트**: 이번 진단·드라이런·배포 명령은 모두 종료했다.
indexer_fixture와 docs_entrypoints 로컬 에이전트는 담당 산출물을 반환했고 편집 중인 에이전트는 없다.
기존 AX 서비스는 계속 동작한다. 과거 failed/cancelled work나 운영 큐는 이 마감에서 정리하지 않았다.
문서 마감으로 현재 AX 큐가 비었다고 주장하지 않는다.

### 최신 (00:11) — 운영 반영과 Codex 전환 완료

사용자 「진행해줘」 승인으로 검증된5파일을 `00f8532` 커밋·Gitea push했다.
AXCluster 워커3대는 main/clean 확인 후 ff-only → 00f8532, 깨끗한 마스터에서 plan/deliver 실행.
`check AXCluster` **3/3 OK**, payload10개·프로젝트 스킬·태그·출처 HEAD 일치.
`.2` Claude 로컬 MCP 대조 주의는 기존과 같이 재현됐으나 Codex 프로젝트 설정 대조는 통과했다.
`ax-projects` 전용 도구 재기동 → 00:09:13 active/running·Result success.
공용 `set_worker_mode_tool('codex')` 00:10:33 성공(운영 readiness3/3), get 도구 재조회 source=state/codex 확인.
기존 등재 work의 모드 스탬프를 바꾸거나 신규 work를 파견하지 않았다.
Redmine #716의 이전 검증 노트는 중복 작성 없이 재조회 확인. 기록 스크립트의 str 반환값 오독은 고쳤다.
운영 결과 기록을 이 문서·리포트89에 추가했다. 사용자 「커밋해줘!」로 두 문서 커밋 승인.
푸시·재배달 승인은 없으며 운영 코드·배달 출처는00f8532 그대로다.

### 최신 (23:59) — Codex 워커 전환 준비 수정·검증 완료, 운영 반영 대기

사용자 로컬 방식 및 재개 승인으로 구현/독립검토. 리포트 [89](../reports/89-codex-worker-readiness-and-write-probes.md).
`master/work/conductor.py`와 `master/test_orchestration_control.py`만 코드 수정:
Session0 Codex 실행 probe → 실제 /IT LIMITED 예약 런처 XML·SSH 계정/SID·경로·배달 런처 검증,
프로젝트 로컬 `.agents/skills/ax-work` 확인. 정적 등록 검사와 실제 도구 실행은 별도로 표시한다.
루트 회귀18/18 OK·diff check OK, 수정 준비 검사 실측3/3 ok.

실제 Codex shell read·apply_patch completed·정확한 수정 결과·회수:
`.43` 성공, Windows 소스 경로 `.2`55초/`.33`43초 성공. Windows 진단 원본은 `.ax`에 보관 후
생성 파일만 제거해 두 트리 clean 복원. 첫 Windows `.ax` 대상 apply_patch는 실패했으며,
권한/런처/바이너리를 바꾸지 않은 소스 경로 비교는 성공했다. 실패 원인은 확정하지 않았다.
없는 경로·접근 거부 읽기 조회는 이번 작업에서만 계속 조사하도록 사용자 예외 승인.
첫 fixture SyntaxError는 재개 승인 후 고쳤다. 실제 실행 실패 중단 규칙은 유지.

아직 미실행: 커밋·Gitea push·서비스 재기동·운영 codex 모드 전환·소스 동기화·재배달.
워커 source HEAD 세 대 `a3eb788`(clean), 마스터90a65a5와 다름. 준비3/3를 전체 배달 버전 일치로 보지 않는다.
운영 워커 모드는 여전히 claude이며, 승인 뒤 서비스 반영과 공용 MCP codex 전환을 확인한다.
#720/#721 수정과 #716 완료 판정은 범위 밖. 아래23:25 기록은 수정 전 상태다.

### 최신 (23:25) — Codex 가 이어받을 자리

**오늘 끝난 것** (근거: 리포트 88 · Redmine 노트)
1. AXCluster 첫 분산 작업 #718 — #260·#375·#615 를 2라운드(3/3·4/4)로 → `f22f741`.
2. #719(조각의 `target_files` 중 첫 파일만 전달) — 분산 작업 #722, 한 파일짜리 조각 5/5 → `90a65a5`.
   `models.TaskRegisterReq.target_files` · `logic.register_task` 정규화 저장 · `register_tasks` POST ·
   `infer.task_targets()`. 재기동 뒤 실경로 확인: 다중 파일 조각 등재 → 큐 레코드 `target_files` 두 파일 →
   즉시 취소(파견 없음). [주의] **워커가 다중 파일 조각을 끝까지 채우는 완주는 아직** — 다음 실전 work 에서 본다.
3. 통합 검사 목록 7→12: broker_routing·workshop_check·source_scope·python_commit_review·build_local·
   skeleton_gate·revise·indexer·version·task_data·infer·integration_checks. 넣기 전 격리 실행(`unshare -rn`·
   가짜 ssh/scp/curl·임시 HOME)으로 부작용 0 확인. `test_client_spec`(실토큰·`.ax/` 캐시 쓰기)·`test_nowork`
   (요약에 건수 없음)은 제외.

**다음 후보 (사용자가 고른다 — 지휘자가 고르지 않는다)**
- **#720** codex 사용 한도가 한도 갈래로 안 잡힘 — JSON `error`/`turn.failed` 문구가 판정 입력 `c.notes` 에 없다.
  고칠 자리 후보: `usage.py`/`runner.py` 의 codex 이벤트 파싱. **codex 지휘로 돌릴 때 가장 먼저 아프다.**
- **#721** 지휘자 준비 검사가 인증 만료를 못 잡음 — `claude auth status`(JSON `loggedIn`) 추가 검토.
- #716 종결 판단(사용자).

**분산 작업 절차 — 오늘 실측한 순서** (`master/skills/distribute` + 아래 스크립트 형태)
1. RAG(`search_context_tool`) → 소스 대조 → 분해안 제시 → 사용자 승인.
2. 대상 모듈의 테스트가 `tests/integration/checks.json` 에 있는지 본다. 없으면 격리 실행으로 부작용을 확인하고 먼저 넣어 커밋.
3. `register_work(…, fixed_version="마일스톤 6 — 개선·확장")` 를 **Python 으로** 부른다 — MCP `register_work_tool` 은
   마일스톤을 못 넘겨 무버전 이슈가 된다. 등재 직후 파견은 「base 없음」으로 기다린다(정상).
4. `git worktree add -b task/<work>/base <옆 경로> origin/main` → `[DOC]`/`[PSEUDO]` 골조 → 커밋 →
   `skeleton_gate.check_head([조각 파일])` 조각별 → `git push origin task/<work>/base` 가 파견을 깨운다.
   지금도 **조각은 한 파일씩**이 안전하다(#719 는 고쳤지만 워커 완주 미확인).
5. 끝나면 `review.advance_work(confirm=False, build_fn=local_test_fn(start_dir="tests/integration",
   pattern="test_axcluster.py", python="/home/sim/ax-cluster/.venv/bin/python"))` → 실제 diff·`[PSEUDO]` 잔존·
   검사 건수 증가를 직접 보고 「버그냐 구조냐」를 사용자에게 → 승인 뒤 `confirm=True, decision_note=…`.
6. 더 고칠 것은 `improve_work(work_id, round=현재+1, specs)` · 끝이면 `review.finalize_work(confirm=True)`
   (main 머지·브랜치 정리·이슈 완료) → 마스터·`.43` `git pull` → 바뀐 코드가 서비스 안이면 재기동 승인.

**함정 (오늘 실측)**
- work 는 등재 시점 지휘자 모드로 **스탬프**되고 바꿀 표면이 없다(#392). 모드를 바꾸려면 조각 취소 → 재등재.
- `sudo -n systemctl restart ax-projects` 는 종료가 1분+ 걸려 명령이 늦게 돌아온다 — **기동 시각으로 판정**.
- `.43` 은 헤드리스 — 인증 복구는 사람이 별도 터미널에서 `ssh sim@192.168.0.43` → `claude auth login`
  (또는 codex 로그인). 마스터 세션의 원격 로그인 기동은 자동 권한 판정이 거부했다.
- 마감 뒤 색인·리뷰 큐가 워커 Ollama 를 수십 분 쓴다. 리뷰 큐는 `[ADVANCE]` 머지 커밋을 「diff 없음」으로 포기한다(정상 판정, 실패로 집계).
- 원격 노트·커밋 메시지는 **파일로 써서** 넘긴다(백틱 셸 치환 사고 2회 기록).

**남은 정리**
- 로컬 브랜치 `task/20261003_2315_719_target_files_316d6d14/base` — main 에 포함, 삭제 승인 대기.
- 이번 #719 경과는 리포트로 아직 안 썼다(리포트 88 은 #718 까지). 필요하면 89 로.


### 최신 — AXCluster 분산 작업 완주 (리포트 88)

- work `20261003_2046_axcluster_claude_260_375_615_54c7eb59`: 라운드1 3/3 → ⑦ 전진 → 라운드2 4/4
  (첫 파일만 전달된 결함 #719 때문에 남은 4파일을 한 파일짜리 조각으로) → ⑦ 전진 → finalize `f22f741`.
  브랜치 8개 자동 정리 · #718 완료. main 에서 통합 검사 `TESTS OK (10)` 426건.
- 첫 등재 `…_67758157`(codex 스탬프)은 codex 한도로 실패 → 조각 취소·work cancelled. 그 브랜치 5개(원격 base·미병합 조각 3 · 로컬 base)는 사용자 확인 후 21:40 삭제했다(조각 3개는 피드백 주석 커밋뿐).
- 마감 뒤 후속 처리: 색인 커서 `611fdba7→f22f741b`(#375 판정 첫 운영 통과) · 리뷰 큐 완료 12(R8~R12 등) · 포기 5 — 전부 `[ADVANCE]` 머지 커밋(고유 diff 없음 → deterministic 포기). 21:39 큐 0건.
- `.43` claude 인증은 사람이 `claude auth login` 으로 복구(21시경). 다음 세션은 #721 이 고쳐지기 전까지
  모드 변경 뒤 `claude auth status` 를 워커마다 직접 본다.
- 남은 판단: #719~#721 착수 순서 · #716 종결 여부 · 아래 이력의 「남은 일」은 이번에 대부분 소진됐다.


### 검증 완료 — Claude 인계 후 (최신, 아래 Codex 서술의 「미완료」를 대체)

리포트 [`87`](../reports/87-axcluster-integration-checks.md). 요지:

1. 5개 파일이 아래 서술과 일치. 회귀 직접 실행 15/15 OK.
2. 프로필 값으로 실제 `build_local.local_test_fn` 호출 → `TESTS OK (7)` · 3.4초 · 트리 불변.
   건수 broker14 · workshop77 · source_scope32 · python_commit_review7 · build_local36 ·
   skeleton_gate51 · integration_checks15. (샌드박스 밖 Claude 세션이라 source_scope 제약 없음.)
3. 저장소 밖 사본에 실패 주입 9/9 차단(rc1 · 0건 · 전부 skip · unittest 실패 · 파일 없음 ·
   빈 목록 · 깨진 JSON · 경계 밖 · 타임아웃). 한계: 자기 요약만 찍고 rc0 인 스크립트는 통과한다.
4. 연결: `payload/profile` → `bundle._tests_for` → 배달 `.ax/config.json` `tests` → `ax-advance`.
   **작업장 배달 전에는 효과 없음**(현 배달본 `384a07a`).
5. 공용 `parse_unittest` 가 첫 `Ran` 줄을 집어 실패 시 요약 숫자가 틀릴 수 있다(판정은 맞음).
   사용자 결정: #716 노트에만 남기고 고치지 않는다.

[완료] 커밋·푸시 `a3eb788`(Gitea · `.43 ~/ax-cluster` 동일). 워커 3대 AXCluster 체크아웃 ff-only →
`a3eb788`. 5프로젝트 `master.client update` rc=0 · 검사 15/15 OK · 출처 HEAD 일치 · AXCluster 워커
`tests` 새 값 실측. 아래 「남은 일」 1~4는 이로써 끝났다(#716 journal 참조).
[주의] deliver 가 `.2` Kimodo·AXCluster 에서 「claude_mcp_local … ~/.claude.json 에 없다」를 찍었으나
`claude mcp list` 실측은 ax-client Connected — 대조 오탐 추정, 원인 미조사.
남은 것: 분산 전체 실증(아래 5번)은 사용자 지시 대기. #716 완료 판정은 사용자 몫.

### 바로 다음 작업 — AXCluster 통합 검사 보완 (Codex 기록)

사용자 “보완작업은 어떻게 진행할거야?”→“진행해봐”로 구현을 승인했다. RAG와 기존 검사 계약을
조사한 뒤, 선택된 로컬 서브 에이전트 방식으로 구현·분류를 나눴다. 마지막 요청은 인수인계이므로
추가 검증·수정·배포를 멈췄다. **이번 변경에 대한 커밋·푸시 승인은 받지 않았다.**

문제: 기존 AXCluster 프로필의 `unittest discover -s master -p test_*.py`는
스크립트의 `__main__`/순수 함수 검사를 실행하지 않는다. 일부 TestCase만 실행돼 N>0을 만족해도
다른 검사의 누락이 감춰진다. 공용 `master/work/build_local.py`는 수정하지 않았다.

현재 구현 파일(새 파일4개 + 기존 프로필1개):

- `master/integration_checks.py`: 명시 JSON 검사 목록 검증, 각 스크립트 별도 Python 프로세스,
  rc·실행 건수·전체/실패/skip 증거 검사. 누락/0건/타임아웃/전부 skip/잘못된 목록은 차단.
  각 자식에 임시 AX_PROJECTS_ROOT·AX_GITEA_REPO_ROOT 및 -B를 적용한다.
  **환경 분리는 완전한 보안 샌드박스가 아니다. 검토된 목록만 실행해야 한다.**
- `master/test_integration_checks.py`: 실제 임시 자식 프로세스를 사용하는 회귀 TestCase15개.
- `tests/integration/checks.json`: 필수 검사7개를 명시. broker_routing, workshop_check,
  source_scope, python_commit_review, build_local, skeleton_gate 및 새 integration_checks.
  검사별180초 제한·출력 형식별 건수 정규식.
- `tests/integration/test_axcluster.py`: 목록을 읽어7개 unittest를 만들고 각 스크립트를 실제 실행.
- `master/client/payload/profile/AXCluster.yaml`: `test_start_dir: tests/integration`,
  `test_pattern: test_axcluster.py`로 변경. 나머지 프로필 값은 그대로다.

실행/검토 근거:

- 구현 에이전트 `/root/716_type_scope`가 새 회귀 검사 **직접 실행15/15 및
  `-m unittest master.test_integration_checks`15/15**, 당시 diff --check 통과를 보고했다.
  rc1·타임아웃·파일 없음·요약 누락/0건·total 불일치·failed>0·allskip·환경 비전파를 검증했다.
- 분류 에이전트 `/root/716_test_inventory`: 기존144파일 중 TestCase7파일을 AST로 식별했고
  후보9개만 전문 검토했다. **나머지135개 안전성은 미검토**, 전체144 검사 커버리지 아님.
  `test_client_bundle.py`는 실제 .33 SSH 및 기존 hooks/__pycache__ 삭제가 있어 목록에서 제외.
  layer1/project_profile은 실제 등록 프로젝트/소스 읽기 의존성이 있어 초기 목록에서 제외했다.
- 루트는 생성된 목록7개와 wrapper/프로필을 확인했고 broker·unittest 요약 샘플 정규식 매칭을
  확인했다. **전체7개 통합 실행과 실제 local_test_fn→wrapper 연결은 아직 실행하지 않았다.**
- `/root/716_independent_review`에 위5파일과 build_local 읽기 전용 리뷰를 요청했으나,
  인계 요청으로 중단을 통보했다. 반환된 부분 리뷰에서 주요 결함은 발견하지 않았고,
  프로필/discovery 호환·프로세스 분리·실패 차단·경로 검증을 확인했다.
  **검사 재실행, 7개 원본의 출력/부작용 전수 대조, 실제 어댑터 결과 검토는 미완료다.**

이어갈 순서:

1. `git status --short`와 위5파일 diff/신규 파일을 읽고, 회귀15개 보고와 구현을 대조한다.
   기존 dirty `docs/orchestrator-handoff.md`도 보존한다. 변경을 stash/reset/clean하지 않는다.
2. 프로필의 새 start_dir/pattern을 이용한 **실제 local_test_fn 통합 호출** 또는 아래 discovery를
   실행해 필수7개 모두 자식에서 실행되고 건수 증거가 통과하는지 확인한다:
   `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py`.
   source_scope는 임시 Git·sg gitea를 쓰므로 알려진 샌드박스 제약에는 좁은 실행 승인을 사용한다.
   실패 시 공용 실패중단 규칙을 따른다. fixture의 예상 실패는 테스트 성공과 구분한다.
3. 실제 프로필→공용 어댑터 연결 및 wrapper/manifest의 실패 차단을 독립 리뷰한다.
   범위 밖135검사를 자동으로 목록에 넣지 않는다. `/tmp` 전체 탐색도 금지한다.
4. 결과를 `reports/87-axcluster-integration-checks.md`(아직 생성 안 함), reports/README,
   이 인수인계 및 Redmine #716에 기록한다. **이번 보완 내용은 아직 Redmine에 반영하지 않았다.**
   스킬의 AXCluster 검사 경로 예시도 새 프로필과 일치하는지 확인한다.
5. 검증이 끝난 구체적 결과로 사용자에게 이번 변경의 커밋·푸시 승인을 받는다.
   승인 후 깨끗한 커밋에서 아래 기존 워커 동기화·재배달 과제를 이어간다.

현재 작업은 로컬 구현뿐이다. 새 운영 큐/Redmine 일감·브랜치·원격 파견·서비스 재기동·배달·
커밋·푸시는 하지 않았다. 아래15/15 드라이런 및 fixture6/6을 이7개 통합 실행 성공으로 읽지 않는다.

### 완료와 근거

- 사용자 “모두 커밋 푸시하고 동기화해” 승인으로 이전 미커밋20파일 전체를 커밋·Gitea push했다.
  Windows Codex 지침/워커 예외/브로커3노드 설정, NS 분석, #716 지침·검사·스킬이 포함됐다.
  GitHub는 Gitea 푸시 미러이며 직접 push하지 않았다. 미러 도착 자체는 이번에 따로 재조회하지 않았다.
- `distribute` 정본을 RAG→소스 대조→사용자 단독/분산 선택→서브 에이전트→실물 검증 흐름으로
  재작성했다. 등록 `kind`로 분기하며 정본7단계·병렬 기본·요청자 통합·별도 전진/finalize 승인을 유지한다.
  현재 노출되지 않은 improve/advance/finalize MCP 도구를 가정하지 않고 실제 모듈 계약으로 안내한다.
- `~/.codex/skills/distribute`와 공식 사용자 경로 `~/.agents/skills/distribute`는 모두
  `~/ax-cluster/master/skills/distribute` 링크다. 둘 다 정본/파일 존재를 재확인했다.
  **이번 인수인계 요청 직전 현재 세션의 제공 스킬 목록에 distribute가 실제 추가됐다.**
  따라서 앞선 “현재 세션 미노출” 기록은 갱신한다. 등록을 위해 반드시 세션을 닫아야 하는 것은 아니다.
  새 세션은 갱신된 진입 지침·인수인계를 다시 받는 데 유용하다.
- 타입별 더티 검사는 code SourceScope와 rename 양쪽/quoted 경로를 보호하고 index_only는 파견 제외.
  workshop77/77 + SourceScope32/32 + broker routing14/14 = 관련 검사123개 통과.
  스킬 형식 검사·독립 코드/forward 검토도 통과. code 서브모듈 내부 더티 검사는 일반화 한계가 있으나
  AXCluster는 submodules=[]다.
- `.43 ~/ax-cluster`는 ff-only 동기화 후 해시 일치. 이것은 `.43 ~/trunk/AXCluster` 워커 트리와 다르다.
- `ax-projects`는 19:24:55, `ax-broker`는 19:23:42 KST로 재기동됐다. 19:33 재조회 모두
  active/running·Result=success. 큐도 active/running이며 앞선 권한 승인 최신성 검사3서비스 모두
  stale=False·why 빈값이다. `ax-dispatch.path`·실제 따라잡기 타이머 `ax-dispatch.timer`는 active/waiting.

### 남은 일과 시작 조건

1. **작업장 동기화 재개 범위를 확인한다.** 기존 전체 동기화 지시가 있었지만, 목록 조회 오류 후
   공용 실패중단 규칙에 따른 재개 질문에 별도 답을 받지 않은 채 사용자 요청으로 인수인계를 작성했다.
   실패는 필수 AX_PROJECTS_ROOT 누락 조회였으며 루트 명시 재조회가 성공했다. 코드/서비스 장애 아님.
   없는 경로를 추정해 읽거나 동일 방식을 재질문하는 반복을 만들지 않는다.
2. **배달 출처를 깨끗한 커밋으로 준비한다.** 이 문서가 미커밋인 채로 배달하면 dirty=true다.
   이 문서 커밋·푸시는 별도 승인 후 처리하거나, 승인된 동기화에서 검증된 깨끗한 체크아웃을 사용한다.
   임의 stash/reset/clean으로 현재 변경을 숨기지 않는다.
3. **AXCluster 워커 소스 Git 동기화**: Windows `.2 E:\trunk\AXCluster`, `.33 C:\trunk\AXCluster`는
   마지막 preflight에서0ffd74b·더티없음. `.43 ~/trunk/AXCluster` 현재 HEAD는 이번에 재조회하지 않았다.
   등록 config의 경로·역할, 브랜치·더티 상태를 먼저 읽고 ff-only로 맞춘 뒤 실제 해시를 확인한다.
   사람의 게임 트리나 작업 브랜치를 강제로 바꾸지 않는다.
4. **등록 전체5프로젝트 작업장 배달·최종 검사**: `ModularStage`, `NS`, `KimodoMotion_WebUI`,
   `MotionForge`, `AXCluster`. 프로젝트를 임의로 골라 일부만 갱신하지 않는다.
   배달 계획을 읽고, 준비된 깨끗한 트리에서 아래 정식 명령을 실행한다:
   `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`.
   종료 결과·전 프로젝트 검사·출처 해시·프로젝트 로컬 skills/config·서비스 최신성을 대조한다.
   **현재까지 이 전체 update는 실행하지 않았다.**
5. **분산 전체 실증은 별도**: AXCluster의 Python 통합 실행기/기존 스크립트 검사 호환성을 확인하고
   실제 큐→골조→조각 브랜치→워커 구현/커밋→회수→요청자 통합을 실증한다. 0개 테스트는 통과 아님.
   이번 사용자는 전체 커밋·푸시·동기화를 지시했으며 신규 분산 작업을 고르거나 전진/finalize를
   승인한 것은 아니다. 이전 직접 apply_patch 프로브를 이 전체 흐름의 완주로 대체하지 않는다.

### 후속 테스트 — 현재 세션에서 실제 스킬 사용

사용자 “그럼 테스트해볼까?”로 distribute를 읽고 실제 MCP를 호출했다.
RAG 검색 성공·logged=true, AXCluster kind=code·blockers=[] 확인.
운영 check_workshops_clean_tool은 kind=code·master/client .py 경계로 세 워커 모두
checked/ok=true·blocking=[]·dispatchable3대를 반환했다. 스킬 quick_validate도 통과.
client check AXCluster는 세 워커 모두 배달 출처384a07a가 HEAD4fb7915보다3커밋 뒤여서
rc1이다. 스킬1종·payload10개는 일치하지만 출처 버전 검사는 실패다.
현재 마스터의 인수인계 문서는 여전히 미커밋. 실제 분산은 파견하지 않았다.
스킬 흐름/준비 검사와 동기화 후 실제 분산 중 테스트 범위를 사용자에게 물었으며 아직 미응답.

### 로컬 격리 드라이런 — 사용자 후속 요청

사용자 “드라이런 해볼까?” 승인으로 운영 큐/Git/워커를 변경하지 않는 하니스를 실행했다.
스크립트 `/tmp/ax-master-workflow-dryrun.py`, 산출물 `/tmp/ax-master-dryrun-y55d21bm/`의
`result.json`·`specs.json`·`queue_requests.json`·골조3개·격리 통합 fixture에 근거가 있다.
하니스15/15와 실제 local_test_fn으로 실행한 fixture unittest6/6 통과.
register_work에 모의 POST/PATCH 큐를 주입하고 실제 _post와 socket 연결은 금지했다.
실제 AXCluster 프로필의 Python 확장자 검사를 통과했으며, 3골조의 run_python·층1 동결 검사를
실행했다. 시그니처 변경·스텁 잔존·비Python 골조·구문 오류·테스트0개는 예상대로 거절했다.
등재 결과의 gate_checked=False도 확인했다: 등록 함수가 별도 골조 게이트 실행을 통과로
꾸며 기록하지 않는다. 골조 검사는 하니스에서 별도로3/3 실행한 것이다.
세 호스트별 서로 다른 브랜치 이름과 대상 파일을 산출했지만 **배정·병렬 실행은 모의 계획**이다.
Git HEAD·refs·status는 하니스 전후 동일. 실제 브랜치/커밋/push, 원격 워커·LLM층2·Git통합·
전진/finalize·Redmine 큐 등재는 실행하지 않았다. 후속 문서 기록만 이 dirty 파일에 추가했다.

읽기 전용 독립 관측에서 실제 호출 순서를 확인했다: work 등재로 ID 발급→base 이름 기록·
태스크 등재→요청자의 골조 브랜치 준비/검사/승인 커밋·push→원격 base 존재를 확인한 자동 파견.
**실제 등재와 골조 push는 자동 파견을 발동할 수 있어 드라이런으로 실행하면 안 된다.**
또 AXCluster의 unittest discovery는 순수 함수·__main__ 스크립트 검사를 누락할 수 있다.
test_broker_routing/test_workshop_check/test_source_scope 등은 실제 실행계약을 별도로 검토해야 한다.
이 fixture6개 통과를 AXCluster 전체 통합 검사 또는 실제 분산 완주로 확대하지 않는다.
하니스 산출물의 후속 독립 검토는 에이전트가 /tmp 전체 목록을 조회하다 접근 제한 디렉토리의
Permission denied를 만나 중단했다. 앞선 호출순서/테스트 계약 독립 관측은 완료됐지만,
산출물 독립 검토는 미완료다. 루트는 지정 result/queue JSON만 읽어15/15·TESTS OK(6)·
모의 큐 호출5개·실제 파견/Git 브랜치 생성 없음 기록을 직접 대조했다.

### 조회와 권한의 함정

- AX CLI는 작업 위치 `~/ax-cluster`, `.venv/bin/python`, AX_PROJECTS_ROOT 명시가 필요하다.
  조회에서 레지스트리를 직접 읽으면 `Registry.load(Path('/home/sim/ax-cluster'))`도 가능하다.
- Windows 옛 클론 조회 스크립트는 `.2` 출력 UTF8 decode오류를 냈다. 기존
  `/tmp/ax-axcluster-worker-deploy.py preflight`에서는 두대 rc0·클론/HEAD/깨끗함을 확인했다.
  출력 처리 오류를 워커 장애로 기록하지 않는다.
- 기본 샌드박스의 systemctl·sg gitea·Docker 조회 실패는 진단 결과로 남기고 좁은 승인 경로로
  재조회한다. 권한 승인은 OS sudo 비밀번호를 대신하지 않는다. 비밀값 출력 금지.
- 홈 AGENTS/CLAUDE 링크를 덮지 않는다. git 현재 트리와 Redmine journal을 함께 대조한다.

## 1. 오늘의 사용자 결정 (2026-10-03)

- 원격: **Gitea 정본**(`origin`) + **GitHub 푸시 미러**(Gitea 가 커밋 시 동기화). 🔴 **GitHub 직접 push 금지** —
  마스터 `github` 원격은 push 비활성. `.43` 도 `origin` = Gitea
- ax-cluster 를 프로젝트로 등록 — 트윈 이름 **`AXCluster`**(ax-cluster 는 저장소 루트와 겹쳐 `test_sandbox` 오탐)
- AXCluster profile: kind `code`(`.py`) · purpose `rnd` · AX 작업 요청자 = **마스터 세션**
- 합성 프롬프트: 비UE 의 긴 `.py` 는 **ast 요약본**(함수 본문 생략, 독스트링·주석 유지)
- 파이썬 그래프: 겹치는 클래스 이름만 모듈명(`master.verdict.Verdict`) · 테스트 파일은 클래스 그래프 제외 ·
  `related_classes` 의 `이름: ?` 는 그래프에 정확한 이름이 있을 때만 채움(**전 프로젝트**)
- 🔴 **컨텍스트 문서는 검색 보조다 — 작업 판단 근거는 실제 코드**
- 사용량 표시는 **토큰만**. `.33` 등 세션 기록은 로컬에 두고 마스터가 가져온다
- `.2` 상주 모델 = `gemma4:e4b`(종전 `qwen2.5-coder:14b`) — 합성을 두 노드에 나누려고
- 🔴 **AX 클러스터 기능 작업(AXCluster)에서는 `.33` 도 워커로 쓴다** — 등록·배달·진단 파일 수정 실증까지 확인(§3)

## 2. AXCluster 재합성 — 🔴 미완 (11:58 실측으로 정정)

- 색인기는 전체 따라잡기를 **하지 않았다** — push 이벤트 범위(`306576e→c657a7a`)의 **바뀐 소스 106건만**
  합성하고 끝났다. 문서 **76 / 347그룹** · 워터마크(`last_indexed_commit`) **비어 있음**
- 품질: `related_classes` 가 전부 `?` 인 문서 **69% → 25%**(76개 중 19) — 그래프·요약본 효과
- 병렬은 실물 확인됨: 11:44~ 브로커 `[route]` 가 `bc250` 20 · `rtx3060` 14 로 나눴다
- **남은 일**: 누락분 합성 → index. 색인기와 겹치지 않게 **push 를 멈춘 상태에서**:
  `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard AXCluster --confirm --only synth`
  (onboard 합성은 누락분만 · 동시 N 은 상주 노드 수) → `--only index`
- [주의] 색인기 타이머(10분)·push 이벤트도 합성을 띄운다 — 잠금이 없어 겹칠 수 있다.
  멈추려면 마운트를 옮겨야 한다(`systemctl stop` 은 NOPASSWD 밖)

## 3. 다음 작업

**최신 우선순위는 §0의 남은 일이다.** 워커 동기화·등록 전체 배달·검사부터 인계한다.
기존 별도 항목인 §2 재합성 미완, #713 웹 UI·토큰 사용량, AXCluster 분산 첫 전체 실증은
사용자가 고르는 다음 작업으로 남아 있다. 이전 §3의 브로커·문서 미커밋/스킬 미완 기록은
4fb7915와 §0 상태로 갱신한다. 과거 실측은 아래 이력과 reports/82·85·86에 보존했다.

## 4. 오늘 커밋 (모두 Gitea push · GitHub 미러 · `.43` pull 완료)

`183f32a` claim 범위(work 혼입 방지, 큐 재시작) · `ef239fb` 원격 문서 · `c595c01` 온보딩 ·
`4c0823f` 합성 요약본+토큰 로그 · `a0cbf42` 트윈 이름 AXCluster · `c237a93` 파이썬 그래프(#712) ·
`6a18918` 세션 수집기(#713 ②) · `306576e` 브로커 호출 사용량(#713 ①) · `c657a7a` 병렬 합성·분배(#715)

## 5. 남은 결함·주의

- `#714` 스풀 고아 배치를 아무도 재처리하지 않는다(`claimed/` 에 3건 남음 — 실손 없음)
- Kimodo 작업장 3대가 마스터보다 뒤다(재배달 필요, 범위 밖이라 안 함)
- `onboard` 의 conventions 문구 「색인 전용」은 code 타입엔 부정확(동작 결함 아님)
- 요약본 뒤에도 4,000자를 넘는 파이썬 파일 125개는 앞에서 잘린다
- 세션 수집기 `master/work/session_usage.py` 는 유닛 테스트가 없다

## 6. 관련 근거

Redmine `#711`~`#715` 노트 · `docs/14-onboarding-runbook.md` · 메모리 `context-docs-are-search-aid` · `codex-windows-ssh-sandbox` · 리포트82 · `docs/windows-codex-remote.md`


## Python 커밋 자동 리뷰 — 구현·검증 통과 (2026-10-03 17:00)

사용자 최초 지시와 kind 기준 정정, “응 진행해” 재개 승인으로 구현·검증했다.
등재·소비·프롬프트·예시는 등록된 프로젝트 kind로 통일한다. unreal=UE, code=Python,
index_only=자동 리뷰 제외. source 경계·work_exts, 큐 중복 방지·재시도·작성자 제외는 유지.
Python 함수·클래스 선언은 현재 트리가 아닌 대상 commit Git 객체에서 AST로 읽는다.
신규6+기존268=274/274 통과, diff --check 통과. 초기 검사 오탐과 승인 후 재개는 리포트83에 보존.
실제 Python commit6a18918을 격리 큐에서 브로커 e4b→Antigravity로 처리하여 최종 저장·done 확인.
아티팩트 /tmp/ax-python-review-live-1392e70e33da4f61a3a92afefb042484/.
운영 큐에 소급 등재하지 않았음. 서비스는 oneshot이므로 다음 기동 때 로컬 수정 소스를 읽는다.
**commit·Gitea push 완료 `7ec14f5`**, 새 운영 커밋의 push감지→자동 리뷰 종결은 아직 미검증.
커밋 검토 범위: 리뷰 코드·테스트5개 + docs/17-review-queue.md + reports/83-python-commit-review.md.
앞선 브로커·원격 문서 dirty 변경과 구분한다. README·reports 색인 갱신은 문서 dirty에 함께 남음.

사용자 “커밋해줘” 승인으로 Python 리뷰 코드·테스트5개 + 설계·실증 문서2개만 커밋했다.
커밋: `7ec14f5` (`review: enable Python commit reviews by project kind`). 푸시는 실행하지 않았다.

사용자 “푸시해줘!” 승인으로 `7ec14f5`를 Gitea origin/main에 푸시했다.
원격 훅에서 Sim/ax-cluster 색인 이벤트1건 큐잉을 확인했다. 리뷰 큐 등재·소비 완료와는 별개다.


## R1 실제 자동 리뷰·검토 완료 (2026-10-03)

운영 commit7ec14f5가 리뷰 큐에 자동 등재되고 17:26:34 첫 시도 done, R1 최종 리뷰 저장 확인.
사용자 “R1 검토해줘”로 지적1건을 운영 Python3.10.12에서 검증: ast.parse 널 바이트는
ValueError이며 SyntaxError만 잡는 declarations에서 전파됨. 격리 큐에서 running잔존·재claim불가 확인.
권고: SyntaxError·ValueError 처리, msg·lineno 모두 getattr, diff 리뷰 계속·큐종결 회귀.
코드·리뷰 원문·R1 상태는 수정하지 않음. 근거 reports/84-r1-python-review-validation.md.

사용자 “수정해줘!” 승인 후 R1 코드 수정 완료: review_runner에서 SyntaxError·ValueError를
잡고 msg·lineno를 안전하게 읽는다. 구문 오류·널 바이트 실제 임시 Git 커밋 모두 리뷰 done,
pending/running=0 회귀 검증. 관련 검사 141건 및 diff --check 통과. 대상 코드·테스트2개만
수정했으며 커밋·푸시 전이다. 리포트84에 수정과 검증 근거 추가. 운영 R1 상태는 변경하지 않음.

사용자가 RAG·서브 에이전트 누락을 지적했다. 최초 수정은 둘 다 없이 진행했음을 인정했다.
**수정 전 관련 RAG 컨텍스트를 조회하고, 위임할 때 그 근거를 함께 전달한다.**
보완으로 AXCluster active 확인 후 search_context_tool 2회 조회, 관련 본문·설계·현재 코드 대조,
로컬 서브 에이전트 r1_context_review에 독립 검토 위임. AX 원격 워커 파견은 아니다.
컨텍스트의 Python 설명 누락·__repr__ 미구현 오기와 검색 excerpt 누락을 관측했으나
검색·합성 설정은 변경하지 않았다. 근거 리포트84.
독립 검토도 R1 추가 코드 수정 불필요로 판정. 널 바이트는 Git 바이너리 diff가 될 수 있으므로
검증 범위는 큐 고착 방지·진단 전달이며 모든 변경 라인 전달 보장은 아니다.

## 사용자 확정 — .57 인프라 정비에도 RAG·분산 도구 활용 (2026-10-03)

사용자 원문: “.33 메인 작업 컴퓨터가 서브에이전트를 활용하고 분산 작업을 시키고,
RAG를 요청하는 스킬이나 MCP를 인프라 서버를 관리할 때도 활용하길 바래서 워커를 등록한거야.”
사용자 후속 정정: “아니 .33에서 작업 하라는게 아니라 .57 이 인프라 서버에서 작업할 때도
.33처럼 RAG와 분산 작업이 가능하도록 구정되어 있냐고”. **작업 장소를 .33으로 옮기라는
뜻이 아니다. .57의 지휘 세션이 인프라 정비에도 RAG·서브 에이전트·AX 워커 분산을 활용한다.**
마스터 직접 수정 뒤 로컬 서브 에이전트 검토만 추가하여 워커 분산까지 했다고 판단하지 않는다.
이번 R1은 마스터 직접 수정 후 RAG·로컬 독립 검토로 보완했고 AX 워커 분산은 수행하지 않았다.
다음 실행 전 관련 스킬·MCP 계약과 기존 승인 범위를 확인한다. 역할 설정·배달은 변경하지 않았다.

준비 상태 실측: .57 현재 세션에서 search_context_tool 성공, register_work_tool 노출,
서브 에이전트 위임 가능. ax-projects·ax-task-queue active/running, ax-dispatch.path active/waiting,
ax-dispatch-catchup.timer inactive/dead. AXCluster 프로필 kind=code, work_exts=.py, blockers 없음.
세 워커 SSH·Codex0.159.3 확인. client check AXCluster는 실패: 세 배달 출처384a07a가
현재 HEAD보다1커밋 뒤, ax-projects는 profile.py 변경 전 기동되어 재기동 필요 판정.
기존 마스터 distribute 스킬도 통합자·기본직렬·UE골조 등 현재 공용 규칙과 어긋난 옛 내용이며
Codex의 현재 제공 스킬 목록에는 distribute가 없다. RAG는 사용 가능하나 분산 준비 완료로
단정하지 않는다. 실패 규칙에 따라 재배달·재기동·스킬 수정은 실행하지 않고 상태만 보고한다.

사용자 “일단 일감으로 등록해”로 Redmine **#716** `[AX] .57 인프라 정비의 RAG·서브 에이전트·분산 작업 준비 정비`
등록 완료. AX Cluster 프로젝트, 마일스톤6, 신규 상태. 버전 불일치·서비스 재기동 필요·
마스터 분산 스킬 갱신·Python 소스 더티 검사 확인과 실제 .57→워커 흐름 검증을 범위로 기록했다.
등록만 했으며 작업 실행·재배달·재기동·커밋·푸시는 하지 않았다. 항목·진행 정본:
http://192.168.0.57:8080/issues/716.

사용자 최신 절차: CLAUDE.md·AGENTS.md·스킬에 **RAG 검색→단독/분산을 사용자에게 물음→
선택에 따라 서브 에이전트 구성→단독 처리 또는 AX 워커 분산→실물 검증**을 반영한다.
이어 “NS에서 작업 요청을 받았을 때” 실제 방식 분석·참조를 지시하여 .33 NS 지침·스킬·
에이전트·MCP·훅을 읽기 전용으로 대조했다. 근거 reports/85-ns-requester-workflow-reference.md.
NS의 기존 컨텍스트/온톨로지·계획/선택·전문 위임·큐 등재·asyncRewake·되먹임 흐름을
참조하되 combined_search/watch.exe/attempt/클라이언트 등재금지 등 낡은 문구는 복사하지 않는다.
자동 로드 지침·스킬 반영, 재배달·서비스 재기동은 아직 실행하지 않았다. 이전 처리 방식 질문은
지침 반영에 관한 것이며 이번 분석·참조 요청을 분산 실행 승인으로 읽지 않는다.
사용자 “아까 신설한 레드마인에 연결해둬!”로 #716 journal1480에 리포트85 경로·NS 분석 결과·
사용자 확정 절차·남은 반영/운영 검증을 연결하고 재조회 확인했다. 미커밋 보고서임을 명시했고
일감 상태는 신규로 유지했다.

사용자 “아까 리뷰 대응한거 커밋하면서 리뷰 상태값 변경하고” 승인으로 R1 수정 코드·테스트·
리포트84의3파일만 커밋: **95906c87914c081ff6fb64ad05443ccfc75b8bfb**
(`fix(R1-1): handle Python declaration parse failures safely`). 핵심7건 재확인 통과.
fix_index.set_status로 AXCluster **R1-1→applied**, 실제 branch=main·위 커밋을 기록하고
get_doc 재조회로 상태·해시 일치 확인했다. R1 전체 항목1/1 applied. 푸시는 하지 않았다.
브로커·원격 설정·NS 분석 등 앞선 dirty 변경은 이 커밋에 포함하지 않았다.

사용자 “푸시해줘!” 승인으로 95906c8을 Gitea origin/main에 푸시 완료.
git ls-remote의 refs/heads/main=95906c87914c081ff6fb64ad05443ccfc75b8bfb 일치 확인,
원격 훅의 색인 이벤트1건 큐잉 확인. R1-1 applied 노트에 원격 반영도 기록한다.
새 커밋의 자동 리뷰 종결은 아직 확인하지 않았다.

#716 선행 정비: 사용자 동의로 로컬 서브 에이전트 2개가 지침5파일과 타입별 더티 검사2파일을
수정했다. workshop 검사77/77, SourceScope 권한 해제 재검사32/32 통과. 독립 코드 검토 진행.
실제 따라잡기 타이머는 **ax-dispatch.timer**이며 active/waiting이다. 앞선
ax-dispatch-catchup.timer 조회로 비활성이라 기록한 내용은 이 실측으로 정정한다.
경로 추정 조회 오류가 반복돼 공용 실패 규칙에 따라 추가 편집 중단. 남은 distribute 스킬은
루트 직접 인수 예정이며 아직 원본이다. 보고서86에 변경·검사·실패·운영 미검증을 기록했다.
스킬 완성·Codex 연결·깨끗한 커밋 기준 배달/서비스 반영·분산 전체 실증이 남았다.
이번 #716 변경의 커밋·푸시는 승인받지 않았으며 배달·재기동·원격 파견도 하지 않았다.

사용자 “모두 커밋 푸시하고 동기화해”로 전체 현재 변경 승인. distribute 스킬은 루트가
현재 흐름으로 재작성 완료했고 형식/독립 forward 검토 통과. Codex legacy·공식 사용자 경로
링크를 좁은 권한 승인 스크립트로 등록했다. 관련 코드 검사123개 통과. 이전 미완료/승인없음
기록은 위 승인·완성 상태로 갱신한다. 이제 전체 변경을 커밋·Gitea push하고 클론·등록 전체
작업장 배달 및 ax-projects/ax-broker 반영을 수행할 예정. 실측 결과 정본은 #716 journal.
스킬 자동 감지가 공식 동작이지만 이 세션의 새 스킬 노출은 미확인. 다음 세션에서 distribute
노출과 정본 경로를 확인한다. 실제 분산 전체 흐름과 Python 통합 실행기 호환성은 미실증이다.
