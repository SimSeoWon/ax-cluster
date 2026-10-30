# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-30 · Codex 작성(사용자 지시로 중단) → Claude 대조·정리
- **상태**: 사용자가 작업의 신뢰성 문제를 지적하고 Codex 작업을 멈췄다. Claude 가 인계서를 실제 상태와
  대조했고, 사용자 지시로 #850 등록·#849 정정 노트·조사 초안과 임시 폴더 삭제를 했다. 추가 구현·실증 없음.
- **저장소**: `~/ax-cluster` · 소스 기준 `fd97d62` = origin/main(이 인계서 커밋은 그 위). 소스 3파일·리포트 131은 커밋·푸시됨.
- **배달**: 사용자 승인 후 `master.client update` AXCluster `.43`·`.2`·`.33` **3/3 OK**, 출처 `fd97d62`, rc=0.
  `.2` 홈 중복 `~/.agents/skills/ax-work` 주의 1건(프로젝트 로컬 정본 우선), 수정하지 않았다.
- **지휘 기록**: 마스터 담당 `claude`(2026-10-21) · 워커 전역 `codex`(state, 2026-10-18). 바꾸지 않았다.
- **실행 중**: 없음. 서비스 재시작·운영 도메인 등록·마운트 변경 없음.

## 현재 작업 — #849의 검증 공백과 사용자 정정

- [#849](http://192.168.0.57:8080/issues/849)는 마지막 조회 **진행**, 완료로 닫지 않았다.
- 사용자 기준: **등록 타입·언어·소스 경계를 확인하고 해당 프로젝트에 맞게 합성·검증한다.**
  언리얼이면 언리얼, AXCluster면 Python이다. 도메인 합성 자체가 언리얼 전용인 것이 아니다.
- Codex 실패: 마운트 AXCluster(`kind: code`, Python, `.py`)를 알고도 UE5 고정 프롬프트를 보고
  C++를 검증 전제로 판단해 **사용자 확인 없이 NS 소스로 실증 대상을 바꿨다.**
  잘못된 전제로 작업·승인 요청을 반복했다. NS 드라이런을 재개하지 않는다.
- `fd97d62`: 로컬 서브 에이전트로 `master/ontology/synth.py`의 agy·codex 작업 폴더를 시작 미러 HEAD
  SHA의 pinned_worktree로 연결. 배치 공유·직접 호출 정리·생성 실패 시 라이브 폴백 금지.
  `master/ontology/prompt.py` 상용 범위 규칙과 `master/test_ontology_synth.py` 검사 추가.
- 회귀 **64/64**, 공식 통합 **181/181** 통과는 실제 기록이다. 추가 검사는 `source.txt`와
  모의 CLI, 진입점 본체 mock을 쓴다. **Python 도메인 합성의 유효성을 입증하지 않는다.**
  앞선 완료 주장만으로 신뢰하지 말고 변경분을 독립 재검토해야 한다.
- SHA 고정은 CLI 작업 폴더만이다. 프롬프트 발췌·사실 검증은 기존 `paths.repo`를 읽는다.

## 읽기 전용 재확인 — 아직 수정하지 않음

1. 프로필 `master/client/payload/profile/AXCluster.yaml`: `kind: code`, Python 중심, `.py`.
   MCP 조회도 동일. 그래프 `master/graph/class_graph.py:142`는 Python을 AST로 처리한다.
   시스템 전체가 Python 미지원인 것은 아니다.
2. `master/ontology/prompt.py:43,102`와 `descriptions.py:63`: UE5 전제 고정, 프로젝트 타입 반영 없음.
   → 2~5는 **[#850](http://192.168.0.57:8080/issues/850)** 으로 분리 등록했다(신규).
3. `master/ontology/contexts.py:161,171`: Python도 파일 앞 1200자를 `.h 선언부`로 표시하고,
   `.h`가 아니면 body는 빈 문자열. 대상 클래스 본문을 선택해 발췌하지 않는다.
4. `master/ontology/parse.py:92`: 클래스 구분은 `::`만 분리. `DomainResult.summary`는 도메인 밖으로
   버리고 `DomainResult::summary`는 수용하는 현상을 기존 parse.actions로 재현했다.
5. 기존 excerpt_header/body에 `master/ontology/synth.py`를 넣은 읽기 전용 재현(rc=0):
   header 1199자, body 0자, `class DomainResult` 포함 false. dot 항목 0/1, colon 항목 1/1.
6. `fd97d62^..fd97d62` diff: contexts/descriptions/parse/verify_facts 변경 없음.
   위 공백은 기존부터 있었다. **#849가 이를 해결하거나 검증한 것은 아니다.**

## 잘못 진행한 드라이런과 보존 증거

- 조사 초안 `reports/research/2026-10-30-849-dry-run.md`(C++ 전제, 미커밋)와 임시 루트
  `/tmp/ax-849-dry-vYgLSMXs`(NS 미러 `0533518` 독립 복제본, 로컬 변경 없음)는 **사용자 지시로 삭제했다.**
  운영 NS 소스·도메인은 수정하지 않았다. 아래 수치는 그 실행의 기록이다.
- graph 성공: 클래스 139·메서드 823. 첫 plan은 manifest 인라인 목록 오류로 멤버 0.
  중단·사용자 승인 후 줄 목록으로 수정 → 멤버 1·청크 1·요청 2.
- dry는 pinned worktree 생성 rc=128로 실패. `git lfs logs last`: `Content/Audio/Classes/SC_Ambience.uasset`
  smudge `remote missing object`. checkout에만 GIT_LFS_SKIP_SMUDGE를 줬고 dry에는 빠졌다.
  **agy 호출 0회**, actions/invariants 0. cmd_dry rc=0이므로 종료코드만으로 성공 처리 금지.
- 운영 registry·NS config 체크섬 불변은 Codex 기록. 전체 전후 status 비교 완료는 주장하지 않는다.
- 상세 실패·배달 기록과 사용자 정정(NS 드라이런·LFS 재실행안 폐기)은 #849 노트. [리포트 131](../reports/131-849-ontology-pinned-tree.md)은
  커밋 시점 기록이며 이후 사용자 정정을 반영하지 못했다.

## 앞선 Claude 세션 기록 — [리포트 130](../reports/130-worker2-board-swap-setup-host-ollama.md)

- **`.2` 보드 교체 복구.** E: SSD 제거 → 체크아웃 루트를 `C:\trunk` 로 옮겼다
  - [#843](http://192.168.0.57:8080/issues/843) **완료** — `setup-host` 진입점 + `ax-worker-setup` 스킬 (`0941944`)
  - 실증: 등록부 4개 이전 · 낡은 상주 4개 해제 · AXCluster 클론·배달·check OK · codex readiness 3/3
- **`.2` Ollama 복구** — 앱 설정의 모델 경로를 사용자가 `C:\Ollama` 로 바꿨다. 모델 3종을 다시 받았다(e4b 상주)
  - 원격 재기동 두 번 실패(`0x80070534` · `/IT` 무반응, 원인 미확정) — 리포트 130 표
- **`.2` 시스템 node → v24.22.2** (Brotli CVE, 리포트 129 미조치분)
- **`.2` UE 5.8.4 확인** — 엔진 CL 58902052 · `probe` ue5 OK (런처 기록만 5.8.1)
- **provision 35B 정리** (`cd803a4`) · `.gitignore` 에 `.mypy_cache/` 추가 (`206a3dc`) — 생성 주체는 리뷰 큐 agy 로 확정(리포트 130)
- [#844](http://192.168.0.57:8080/issues/844) **완료** — 리뷰 큐 agy 를 리뷰 커밋의 고정 트리에서 돌린다 (`f3e3d96`)
  - 실물 3회: 고정 트리에서 돌았고, 정리됐고, 마스터 `status --ignored` 불변. 리뷰 자체는 실패 → #845·#846
- [#845](http://192.168.0.57:8080/issues/845) **완료** — agy 한도 판정을 실제 소진 문구로만 좁혔다 (`faa2306`)
  - 정상 CLI 로그의 `quota`·스레드 번호 `429` 가 모든 실패를 600초 쿨다운으로 만들었다(로그 248개 중 247 → 17)
- [#846](http://192.168.0.57:8080/issues/846) **완료** — 리뷰 퇴고 프롬프트에 작업 범위 규칙 (`674dfb4`)
  - 타임아웃 원인은 에이전트 탐색이었다(200초 이상 회차 평균 도구 호출 25.5회·테스트 23/37). 첫 적용 43초·5회. **1건** — 분포 재측정은 다음 세션
- [#847](http://192.168.0.57:8080/issues/847) **완료** — 리뷰 큐에서 agy 쿨다운은 한도 갈래(시도 미소비) · 그 회차 중단 (`6e94591`)
  - 분류 규칙은 리뷰 큐에만(사용자 결정 — 공용 마커 그대로) · 실서비스 실증 없음(진짜 소진에서만 도는 경로)
- [#848](http://192.168.0.57:8080/issues/848) **완료** — 색인기 컨텍스트 합성의 상용 CLI 를 고정 트리에서 · 상용 프롬프트에 범위 규칙 (`6f9d81a`)
  - 실물: 합성 3그룹 agy 도구 호출 1·10·3회(전엔 29회), 테스트 0, 마스터 트리 불변
- 작업 기록(`log_history`) 누락을 사용자가 지적 → 이후 결정마다 올림(트윈 `history/` 15→23)

## 사용자 답을 기다리는 것 (2026-10-22 부터 그대로)

1. **#839 운영 근거 방식** — 출처·시각이 박힌 스냅샷 파일 vs `doc_sync` 가 직접 live 조회
2. **#839 보호 문서 4개 실증**(claude·agents·home-claude·home-agents) — 어느 문서부터, 문서별 계획·동의·레인
3. **#840 로컬 조각의 cloud 재작성 반영** — 후보 보관 vs 후속 라운드 자동 준비
4. **#840 남은 구현** — 코드 조각 사실 실패 → 다음 cloud 재작성 루프 · context 쓰기 원자성(CAS)

## 바로 다음 작업

1. 코드 수정·실증·NS 재시도를 자동 시작하지 않는다. 다음 작업은 사용자가 고른다.
2. 재개 지시가 오면 #850(AXCluster/Python 합성 입력·프롬프트·파싱)부터 — 갈림길은 이슈 본문, 착수 때 사용자와 정한다.
   #849 의 로컬 서브 에이전트 선택은 #849 범위만이다. #850 수행 방식은 다시 묻는다.
3. #849 실증(합성 1회 전후 `status --ignored` 불변 · agy 도구 호출 수)은 #850 상태를 고려해 대상을 정한다.

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- `.2` 새 경로에서 실제 Codex 셸 읽기·apply_patch·결과 회수 — 다음 파견에서 확인
- 비마운트 3개(ModularStage·NS·MotionForge)의 `.2` 클론 — 마운트 전환 때 `set_active` 가 한다
- [#849](http://192.168.0.57:8080/issues/849) 위 절. fd97d62 배달됨, 실제 합성 0회 · [#850](http://192.168.0.57:8080/issues/850) Python 합성 결함.
- #846 효과 재측정 — 리뷰 퇴고 소요·도구 호출 분포를 10-11~10-30 기준과 비교(한도 상향 B 판단 근거)
- 포기된 `f3e3d96` 리뷰 재등재 여부 — 사용자 미결정
- [#709](http://192.168.0.57:8080/issues/709) GitHub `SimSeoWon/Test_KimodoMotion` — 사용자가 웹에서 지운 뒤 404 확인하고 닫는다
- [#211](http://192.168.0.57:8080/issues/211) RAG 품질 — **지금은 로그 수집만**(사용자 결정). 착수 금지
- [#633](http://192.168.0.57:8080/issues/633) — 자식 [#639](http://192.168.0.57:8080/issues/639)
