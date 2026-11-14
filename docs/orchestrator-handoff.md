# 현재 AX 작업 인수인계

> 2026-11-14 — #942 세 CLI 대화 중계 레이어를 main `3fc4772`·인계 `8291817`까지 반영하고 Redmine 완료·100% 및 배달(`master.issue_wrapup 942` rc0)을 확인했다.
> 이어서 오래된 일감 점검·드라이런을 수행해 9건(#322·#271·#269·#791·#650·#649·#372·#370·#826)을 완료(100%)로 닫고, #741·#368·#383에 실측·드라이런 노트를 기록했다.
> 항목·진행은 Redmine, 지난 상세는 Git 이력·리포트로 확인한다.

## 현재 결과 — #942 완료 및 구 일감 정리·드라이런

- **#942 (`master/relay/`) 마감·배달·자동 리뷰 완료**:
  - 구현 Claude, T7 인수·검사·마감 Codex (`['claude','codex']`). 보고서 `reports/180-942-relay-upper-layer.md`, 구현 커밋 `1dcc6a1`~`3fc4772`, 인계 `8291817`.
  - 검사: relay 113/113 · 정적 차단 0 · 공식 통합 196건 OK · 전수 222파일 rc0 · 세 CLI(claude→codex→agy→claude) 실제 교체·이어가기 rc0.
  - `master.issue_wrapup 942 --project AXCluster` 2차 실행(`829181731bd5`): 재기동 없음 · `master.client update` 배달·검사 rc0 · T7 완료 기록.
  - 자동 리뷰 도착: 해시별 R351~R354 및 종합 리뷰 **R355**(`1aed4703c974..3fc4772d9e44`, 지적 16건: 높음 0 · 중간 4 · 낮음 12) #942 노트에 등록됨.
- **2026-11-14 구 일감 전수 점검·격리 드라이런 및 종결 (사용자 승인)**:
  - **완료(100%) 종결 9건**:
    - `#322` (워커 SSH 단절 뒤 잔류 프로세스 방어): `layer3_verify.py:332-391` fail-closed 및 `logic_lifecycle.py:59-129` 4중 펜싱 확인 후 완료.
    - `#271` · `#269` (BC-250 RADV 28 tok/s 재현 및 72B 모델 배치): 로컬 LLM 우선순위 하향 결정으로 완료.
    - `#791` (다중 라운드 후속 실패 시 work rejected 및 base 삭제): `#821`(`b3daf6f`) 반영 및 10-31 격리 드라이런(반려 브랜치 보존·`infra_undecided` 보류) 확인으로 완료.
    - `#650` (프로필 대화 적립 및 미수집 등재 거절): `profile.py` 강제 기제 및 `profile.blockers()` 드라이런 실측 완료.
    - `#649` (작업장 `.claude/CLAUDE.md` 프로젝트별 분리): 마스터 배달 분리(A~D) 및 파생 `#851`·`#852` 완료 확인으로 종결.
    - `#372` · `#370` (분산 작업 라이프사이클 및 미정리 차단 게이트): 자식 `#371`·`#373` 자동 정리 안정화 및 `cleanup.survey_terminal` 드라이런(원격 잔여 `task/*` 0개) 확인으로 자식·부모 모두 완료.
    - `#826` (결정적 함수 플로우 본체): 교차 세션 `plan_start` 실호출 검증(T6 공백 해소) 및 Phase A·B(`#857`) 완주 확인 후 완료. 선행 `#856` 대기 중인 Phase C(`#858`)는 부모 해제(`parent=null`)하여 독립 일감으로 분리.
  - **실측·드라이런 노트 보강 3건 (열림 유지)**:
    - `#741` (세션 프로젝트·일감 출처 보강): `usage_dashboard.py` 현재 코드와 `~/ax-state/usage` 실측 대조 노트 기록.
    - `#368` (잔여 토큰 임계 인수인계 제안): Claude(`rate_limit_event` `unifiedWindows`)·Codex(롤아웃 JSONL `token_count.rate_limits`)·Antigravity(`stream-json` `usage`) 기계 판독 실측 완료 및 `#942`(`master.relay`) 연동 방향 노트 기록.
    - `#383` (분산 작업 휴리스틱·레시피·히스토리): 코드 대조 및 `NS/recipes/_signals.jsonl`(12건) 복사본 격리 드라이런 완료. 히스토리 경로 구분(`tags: [pipeline, ...]`)은 이미 동작 중이며, 미구현 원인은 ① 파이프라인 `signals.append_signal(..., source="pipeline")` 호출 누락 ② `master/batch/gates.py`·`run.py` `BATCHES`에 `recipes_synthesizer` 미등록임을 규명(아카이브 28일 컷오프 주의점 포함)해 `#383` 노트에 기록.

## 실행과 남은 제약 (#942 `master.relay`)

- 운영 실행: `cd /home/sim/ax-cluster` → `.venv/bin/python -m master.relay` (선택: `--issue N --agent codex`).
- 로그 `~/ax-state/relay` (`AX_RELAY_ROOT`), 디버그 `sessions/<N>/debug.log`, 원문 `raw-<에이전트>.jsonl`.
- 열린 채 중단하면 세션 유지. `/close`는 일감 완료·보고서 존재·잠금 해제를 확인해 로그 보관·세 세션 비우기만 한다. 일감 마감은 기존 도구 몫이다.
- 한 줄 입력만, agy출력은 모아서 표시, Linux `fcntl`·프로세스 그룹 사용. `.33` 이식·실행 래퍼는 범위 밖.
- 긴 작업·한도 소진·중단 뒤 이어가기, 레이어 안에서 issue_start/finish 호출은 미실증(비대화 세션 작성 계열 기록 포함).
- #941 디스코드 연동은 #942 다음 별도 작업이며 미착수. 본문의 터미널 창·agy 판단부 설계는 #942에서 확정된 방향과 대조해야 한다. 자동 시작하지 않는다.

## 지휘·승인·미확인

- 마스터 마지막 담당codex(2026-11-14 12:12:55 인수기록), 워커 전역codex(state,2026-10-18). 모드 변경 없음.
- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842).
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355. 다른 마감분의 최신 리뷰는 각 Redmine 노트로 확인한다.
- 결정·구현 대기: **#383**(진단·드라이런 완료, Claude 진행 예정) · #326 · #935 · #839 · #741 · #738 · #941.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8열림).
- `.2` 홈 중복스킬 경고는 #738축. 8103 LAN 리포트 공개는 사용자2026-11-13 결정으로 유지.
- #911·#938·#939 등 리서치는 `reports/research/`·해당 Redmine에 있으며 착수 승인이 아니다.
- ⑦전진·finalize·파괴적Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. **#383** (`[AX] 분산 작업이 휴리스틱(신호·레시피)을 수집하지 않는다`) — Redmine #383의 2026-11-14 진단·드라이런 노트를 근거로 Claude 세션에서 구현을 진행한다:
   - `master/batch/gates.py` 및 `master/batch/run.py` `BATCHES`에 `recipes_synthesizer.run_recipe_synthesis` 배치 등록
   - 분산 파이프라인 종결 시 `signals.make_record(..., source="pipeline")` + `signals.append_signal` 호출 배선
   - `recipes_synthesizer.py` `_archive_signals`의 28일 만료 기준(`timestamp` vs 아카이브 시각) 처리 검토
2. 그 밖의 일감(#941 등)은 사용자 선택을 기다리며 자동 시작하지 않는다.

