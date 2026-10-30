# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-30 23시경 · Claude · 사용자 지시로 갱신(#849 완료 반영)
- **저장소**: `~/ax-cluster` · 소스 기준 `b373382`(그 위 문서 커밋만) = origin/main. 작업 트리 clean.
- **배달**: `master.client update` AXCluster `.43`·`.2`·`.33` **3/3 OK**, 출처 `b373382`.
  `.2` 홈 중복 `~/.agents/skills/ax-work` 주의 1건(종전과 같음, 프로젝트 로컬 정본 우선) — 수정하지 않았다.
- **지휘 기록**: 마스터 담당 `claude`(2026-10-21 기록 그대로) · 워커 전역 `codex`(state, 2026-10-18). 바꾸지 않았다.
- **실행 중**: 없음. 서비스 재시작·운영 도메인 등록·마운트 변경 없음. 임시 트윈·임시 worktree 전부 삭제.

## 이번 세션 — Codex 중단 정리 → #850

- **Codex 중단 경위**: #849 실증에서 마운트 AXCluster(`kind: code`, Python) 대신 UE5 고정 프롬프트를 보고
  묻지 않고 NS C++ 로 대상을 바꿨다. 사용자가 멈췄다. 대조 결과와 정정은 #849 노트(NS 드라이런·LFS
  재실행안 폐기). C++ 전제의 조사 초안·`/tmp/ax-849-dry-*` 는 사용자 지시로 삭제. 인계서 커밋 `32de69b`.
- **[#850](http://192.168.0.57:8080/issues/850) 완료** — 온톨로지 합성을 파일 언어별로 (`b373382`)
  - 갈림길 6개는 사용자가 추천안 채택(#850 첫 노트). 수행: 로컬 서브 에이전트 + Claude 독립 재확인
  - 발췌·파싱은 **확장자**, UE 전용 규칙만 `kind == unreal`. `.py` 는 AST 로 대상 클래스(신호 없으면 메서드 본문 우선)
  - 프롬프트 = 공통 본문 + 언어 블록. **unreal 의 C++ 조각은 바이트 동일**(sha256 고정 검사)
  - 이름 분리 = `parse.owner_class` 최장 접두(`::`·`.`·모듈 접두). `verify_facts` 는 원래 `.` 를 받아 손대지 않았다
  - `contexts.excerpt_header` 동작 불변 — 층2 grounding(`work/declarations.py`)·골조도 부른다
  - 검사: `master/test_*.py` 187개 8873/8873 · 통합 181 OK · 신규 `test_ontology_python` 83/83
  - 실물(임시 트윈, AXCluster `config.py` 3클래스, agy): dry actions 8·invariants 11 → refresh actions 11·invariants 10·서술 2.
    버림 0 · 표기 `Class.method` · 증거 줄 11/11 일치 · 마스터 `status --ignored` 불변 · 운영 트윈 변경 0
  - 레이어가 전부 L3 인 것은 추정기(도메인 내 상속 구조) 규칙대로다 — 결함 아님
- **[#849](http://192.168.0.57:8080/issues/849) 완료** — 남은 검증(agy 도구 호출 수)을 #848 방법으로 쟀다:
  agy 세션 기록 `~/.gemini/antigravity-cli/brain/<세션>/.system_generated/logs/transcript.jsonl` 의 `tool_calls`.
  #850 실물 5회 = 7·3·5·3·1회, 테스트·파이썬 0 · 마스터 라이브 경로 0 · read_file 은 BRIEF 와 고정 트리 안 대상 파일뿐.
  미실물: 재검증 배치(`ax-batch`) 진입·codex 레인(단위 검사만)
- 결정은 `log_history` 로 올렸다(트윈 `history/` 2건).

## 사용자 답을 기다리는 것

1. **#839 운영 근거 방식** — 출처·시각이 박힌 스냅샷 파일 vs `doc_sync` 가 직접 live 조회 (10-22 부터)
2. **#839 보호 문서 4개 실증**(claude·agents·home-claude·home-agents) — 어느 문서부터, 문서별 계획·동의·레인
3. **#840 로컬 조각의 cloud 재작성 반영** — 후보 보관 vs 후속 라운드 자동 준비
4. **#840 남은 구현** — 코드 조각 사실 실패 → 다음 cloud 재작성 루프 · context 쓰기 원자성(CAS)

## 바로 다음 작업

1. HEAD·dirty·Redmine 을 재조회한다. 다음 작업은 사용자가 고른다 — 스스로 착수하지 않는다.
2. agy 를 쓰는 실측은 공용 한도(리뷰 큐와 공유) 영향을 먼저 말한다. 도구 호출 수는 위 transcript 로 센다.
3. AXCluster 운영 온톨로지 도메인은 여전히 0개다. 도메인 등록은 사용자 결정 — #850 실물은 임시 트윈에서만 했다.

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- `.2` 새 경로에서 실제 Codex 셸 읽기·apply_patch·결과 회수 — 다음 파견에서 확인
- 비마운트 3개(ModularStage·NS·MotionForge)의 `.2` 클론 — 마운트 전환 때 `set_active` 가 한다
- #846 효과 재측정 — 리뷰 퇴고 소요·도구 호출 분포를 10-11~10-30 기준과 비교(한도 상향 B 판단 근거)
- 포기된 `f3e3d96` 리뷰 재등재 여부 — 사용자 미결정
- [#709](http://192.168.0.57:8080/issues/709) GitHub `SimSeoWon/Test_KimodoMotion` — 사용자가 웹에서 지운 뒤 404 확인하고 닫는다
- [#211](http://192.168.0.57:8080/issues/211) RAG 품질 — **지금은 로그 수집만**(사용자 결정). 착수 금지
- [#633](http://192.168.0.57:8080/issues/633) — 자식 [#639](http://192.168.0.57:8080/issues/639)
- 앞선 Claude 세션(.2 보드 교체·#843~#848)은 [리포트 130](../reports/130-worker2-board-swap-setup-host-ollama.md), #849 구현은 [리포트 131](../reports/131-849-ontology-pinned-tree.md)
