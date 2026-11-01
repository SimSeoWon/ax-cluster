# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 직전 체크포인트(10-31 23:06 Claude — #864 T1~T3)는 git 이력 `228bb1d`.
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-11-01 22:58 KST · Claude · 사용자 지시
- **저장소**: `~/ax-cluster` · `main` · HEAD=`origin/main`=`355c033`(+ 이 인계서, 커밋 여부는 git 으로 확인) · 그 외 작업 트리 clean.
- **마운트**: **AXCluster**(#863 에서 MotionForge→NS→AXCluster, ModularStage→AXCluster 왕복 뒤 복귀). 배달은 이 인계서
  커밋 직후 update 로 맞춘다 — 그 뒤 커밋이 생기면 `check` 출처 대조만 어긋난다(다음 update 는 승인 받아).
  MotionForge·NS·ModularStage 도 이번 세션에 3대 최신·check OK. `.2` 에 `C:\trunk\MotionForge`·`C:\trunk\NS` 를 **새로 클론**했다.
  `#868` 로 **문서(`docs/`·`reports/`)만 바뀐 커밋은 전환 align 이 통과**한다. 코드 커밋 직후는 여전히 #831 가드로
  막힌다 → CLI update 또는 `ax-projects` 재기동. `#869` 로 기동 커밋 = **서비스 기동 시점 HEAD**(기동 로그 `[drift] 기동 커밋 …`).
- **서비스**: 11-01 15:48 재부팅. `ax-projects` 는 20:02:02 재기동(기동 커밋 `77aa3ae`) · `ax-broker` 는 21:00:30 재기동(`4f46230`, 상한 4) — 둘 다 사용자 승인.
  [주의] `.2` 도 재부팅됐는지는 미확인 — 세션 1 과제는 `janus` 로그인이 있어야 돈다.
- **지휘 기록**: 마스터 담당 `claude`(10-21 기록 — 이번 인수 미기록, 사용자 지시 없음) · 워커 전역 `codex`(10-18).
- **실행 중**: 없음.

## 이번 세션 요약 (상세는 각 일감 노트·리포트)

- `#864` T4 — 리포트 133 `68f87eb`: 플랜 3건 대 M6 기준선 32건, **효능 판단 불가**(실표본 2건 · 기준선 분포 안 ·
  #852 는 종결 11분 전 플랜 부착).
- `#862` — 사용자 선택으로 T5 시험 대상, ax-plan T1·T2 로 진행 → **완료로 닫음**. `c521568`: Linux crontab 해제가
  임시 파일 + 줄 수 대조 뒤에만 설치, `crontab -l` 실패·`grep` rc≥2·불일치면 `AX_CRON_ERROR=` + 미설치
  (본문 밖 결함 `grep` rc 2 → 빈 crontab 설치 경로도 막음). 전수 9440/9440 · 통합 184 · `.43` 실측 5경우.
  첫 전수에서 `test_client_bundle` 가짜 SSH(옛 문자열 판별) 3건 실패 → 보고·승인 뒤 대상 추가.
- `#864` T5 — 리포트 134 `effe540`: #862 플랜 등록→종결 18분, 생성→종결 18.17h 중 대기 17.9h 라 비교 불성립.
  도구 한계 4건 새로 확인(아래 2).
- `#865` — 도구 한계 4건 개선, ax-plan T1~T5 → **완료로 닫음**. `39a0f34` `master/plan_metrics.py`:
  검사 수치 OK·N경우·rc · 작업 커밋(`종류(#N…)`) 범위 이탈 · 플랜 갱신 분류(저널 description 전후) · 착수 리드.
  #862 범위 이탈 0% · 대상 확장 1회 · 착수 0.29h. 비교: 착수 리드 중앙 기준선 2.73h(13/32) vs 플랜 2.94h(3/3) — 차이 없음.
  남는 한계: 「대상」 칸 토큰이 적으면 이탈 과대(#857 76%) · 종결 직전 플랜 부착은 착수 아님(#852).
- `#863` — **완료로 닫음**. T1 `.43` 잔재 정리(MotionForge·NS 전환 align, 4체크아웃 확인) · T2 `.2` touch 드라이런으로
  `build_step` PASS 실컴파일(UBT `Compile Module.ModularStage.cpp`·58.3초) · T3 실 work `20261101_1818_863_t3_…`(#866)
  `.43` codex 파견 → 워커 커밋 → ⑦ 전진 `e27b0258→e7b415a4` → finalize `main` `020cffd`(F541 한 줄) · check 3대 OK.
  codex 입력 35만 토큰(캐시 91%). 미확인(FAIL 경로·Windows 세션 1)은 **`#867`**, #831 가드 문제는 **`#868`**.
- `#868` — **완료로 닫음**. `f35d0da` `code_drift()`: 기동..HEAD diff 가 전부 docs/·reports/ 면 허용, 그 밖·diff 실패는 거부.
  실측: 문서만 커밋 `e79fe5c` 직후 AXCluster 복귀 align 3대 성공(오전 같은 조건 3대 실패) · CLI check OK. 빈틈은 **`#869`**.
- `#869` — **완료로 닫음**. `ffaa139` ax-projects 가 기동 때 bundle import → 기동 커밋 = 기동 시점 HEAD(로그 한 줄).
  실측: 재기동 직후 로그 `ffaa139` · 문서만 커밋 `c2cf511` 뒤 첫 전환부터 align 성공 · check OK. 기동 뒤 .py 커밋 거부의 서비스 실측은 안 함(사용자 결정).
- `#867` — **완료로 닫음**. T1 FAIL 경로 드라이런(.2 미추적 임시 .cpp → `build_step` FAIL · 근거에 `error C2065` 줄 · UBT 로그 일치 · 복구 PASS).
  T2 work `20261101_1912_867_t2_…`(#870) 3조각 병렬 — **.2·.33 Windows 세션 1 실파견 완주**(런처·codex rc0·회수) · .43 SSH →
  ⑦ 전진 → finalize `main` `c5003d8`(미사용 import 3건). 층1 차단 2건은 자동 재시도 1회로 해소 — 원인은 내 골조 문구
  「그 외 변경 금지」가 `[PSEUDO]` 제거와 충돌 → `ax-request` §3.5 지침 추가 `eddaa86`, ModularStage update 로 `.33` 배달 확인.
- ModularStage 전환 때 기동 커밋 `ffaa139`≠`eddaa86`(.py·스킬 변경)로 align 이 #831 에 **의도대로 막혔다** — #868·#869 의
  「코드 커밋 직후 거부」가 서비스로 실측됐다. CLI update 로 맞춘 뒤 재기동·AXCluster 복귀(3대 same).
- `#851` — **완료로 닫음**. `77aa3ae` RAG 융합 검색: BM25 단독 히트에 같은 세대 Chroma `get(ids)` 로 meta·발췌를 채운다
  (순위·점수 불변). 운영 재현 질의 상위 8건 동일 · bm25 단독 2건 meta·발췌 실림. 문서 합성 발췌에도 반영되는 동작 변화.
  [주의] T1 전이 노트에 없는 해시(a9e1f8c)를 오기 → 정정 노트. 커밋 확인 뒤에 마킹할 것.
- `#853` — **완료로 닫음**. 노드 실효 `OLLAMA_NUM_PARALLEL` 은 이미 1(.43·.2 로그, .33 미확인) — 빈틈은 브로커 적체.
  `4f46230` 브로커 노드별 동시 요청 상한(`AX_BROKER_NODE_CAP` 기본 4 · 0=무제한) · 포화면 즉시 503 · 상주 포화 시 재적재 금지.
  실측: 동시 3·7 전부 200 · 동시 9 → 8×200 + 1×503(0.02초). 기본 4 는 사용자 결정(2 면 동시 7 중 3건 503).
- 데몬 잔재 전수 확인(사용자 지시) — 등록 4프로젝트×3기계 check: 상주·프로세스·폐기 페이로드 전부 없음. 예약 작업은 정식
  런처(AxConductor*)·AX_Ollama33 뿐. 단 AXCluster 워커 체크아웃 로컬 main 이 옛 커밋(.43 10-07)이라 데몬 소스가 남아 있었다
  → .43·.33 ff 로 정리 · 원인 `#871` **완료로 닫음** `6b1fa78`: 사이클 복귀가 `checkout -B main origin/main` 으로 로컬 main 을
  원격에 맞춘다(.2 드라이런 836004c→6931118). 세 워커 AXCluster main 모두 6931118. 게임 체크아웃은 다음 사이클부터 맞춰진다.
- `#333` — **완료로 닫음**. ⓐ `53f5b7d` `cleanup plan` 끝 「기계 단위」 구역·`cleanup machines`(읽기 전용) · ⓑ 는 #787 로 이미
  구현됨을 대조 · ⓒ(가) `dfd9c24` 워커 main 뒤처짐 표시 + apply 가 `merge --ff-only`(운영 apply 로 3대 5커밋 뒤 → 일치) ·
  ④ 프로브 work(#873) 1조각 → ⑦ 준비 → 취소 → terminal·machines·plan 이 브랜치·worktree·부산물 전부 잡음.
  프로브 문구는 새 ax-request 지침대로 써서 첫 시도 통과. 마스터 프로브 잔재 3개 삭제(사용자 승인 — 통합 머지 커밋
  a45bc7d 는 마스터에만 있던 자동 머지라 확인받고 삭제). 관찰 ⑴ 취소 work worktree 큐 대조 ⑵ 마스터 로컬 task/* 열거 → `#874`.
- `master.client update` 여러 차례(커밋마다·ModularStage 포함) 모두 3대 OK. `.2` 홈 중복 스킬 경고가 `ax-work`·`ax-infer` 2개로 늘었다(#661 계열, 생성 시점 미확인).

## 플랜(SDD) 효능 축 — `#864`·`#865` 둘 다 닫음

`#864` 조건 ④는 #862 1건으로 충족(사용자 결정 16:29). 결론: 현재 표본으로는 효능 판단 불가 — 표본이 늘면
`python -m master.plan_metrics compare --version-id 19 --issues <ids>` 로 다시 본다(착수 리드·플랜 갱신 포함).

## 사용자 답을 기다리는 것 / 다음

1. 다음 일감 선택(열린 M7 일감에서 — 사용자가 고른다). M7 버그/개선 열린 일감: `#874`(낮음) 하나. 오늘 연 #866~#877 중 열린 것 없음.
- `#875` — **완료로 닫음**. `3134e7c` `review.cancel_work(confirm=False 기본)` — 확인 시 미종결 조각 취소 → 큐
  cancelled → 그 이슈에 「[취소]」 노트 + 「완료」·100 · reject 노트도 실제 게시 · ax-review 「6.1 취소」(큐 직접 PATCH 금지).
  `355c033` 대행 게시가 `ok:false` 를 실패로 보고 3초 간격 3회 재시도(finalize 공용 — 같은 구멍이 있었다).
  실측: 프로브 #876 에서 422 를 「게시됨」으로 오보 → 수정 뒤 #877 에서 422 → 재시도 성공 재현. 프로브 이슈
  #873(손 종결)·#876·#877 모두 「완료」. ⑦ 대기 work 취소는 이제 `cancel_work` 로 — 큐에 직접 PATCH 하지 말 것.
2. 앞 세션 설계 선택 확인 — 거절 기록은 getter 미주입(MCP·실 Redmine) 호출에서만 · MCP 래퍼 caller 빈칸.
3. 앞 세션 미결: #839 ②·#840 ①·#791 D·#820·#372·#855 · #826 `next_steps` 표시.

## 바로 다음 작업

1. HEAD·dirty·Redmine·마운트 재조회 → 사용자가 고른 일감으로 진행(스스로 고르지 않는다).
2. 플랜 마킹은 `plan_transition_tool` 로만 — 거절은 `AXCluster/plan_events.jsonl` 에 쌓인다(현재 1건, #864 실증용).
3. 운영 행위(배달·재기동·마운트 전환·빌드)는 실행 전 승인.
4. **기존 경로를 재사용하자고 하기 전에 그 경로의 폐기·복원 이력부터 grep**(reports·history·Redmine).
5. 검사 대역이 명령 **문자열 모양**으로 판별하는 곳이 더 있을 수 있다 — 명령을 바꾸면 전수부터 돌린다(#862 사례).

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- AXCluster 큐 고아 태스크 10건·스풀 26묶음 — 손대지 않음 · #709 · #211 · #650
- `cleanup plan` 이 보이는 잔재(삭제는 목록 확인·승인 뒤): 마스터 `ax-788-work`(도달 불가 — 커밋은 미러 refs/ax/pruned 보존)·
  `ax-advance-…831…`(후보) · AXCluster 미러 `ax-review-20261010_1742_788_1_…`(도달 불가)
- 전환 인계 조사가 보고한 잔여(손대지 않음): MotionForge 미병합 durable `task/20261009_0051_motionforge_aac50fe6/r1/0906d6fc`
  (사람 몫)·스풀 2 · NS 고아 태스크 2·스풀 1
