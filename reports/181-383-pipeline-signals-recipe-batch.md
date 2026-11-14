# 181 — #383 분산 작업 신호 적재와 레시피 합성 배치

2026-11-14 · Claude(마스터 세션) · 일감 `#383` · 브랜치 `issue/383` (시작 리비전 `c51a3af`)

## 1. 무엇이 문제였나

사용자 지적(2026-09-07): 분산 작업이 휴리스틱(신호·레시피)을 수집하지 않는다.
같은 날 앞선 세션의 진단 노트(`#383` 2026-11-14)가 원인을 둘로 좁혔고, 이번 세션이 현재 소스와 다시 대조했다.

| 증상 | 원인 (소스 대조) |
|---|---|
| 분산 작업이 신호를 한 건도 안 남긴다 | `signals.append_signal` 호출부가 `server.py` 의 요청자 경로(`POST /api/v1/signals`) 한 곳뿐. 파이프라인 쪽은 통합자 삭제(2026-09-03) 때 함께 사라졌다 |
| 신호가 문턱을 넘어도 레시피가 0건 | 합성기(`recipes_synthesizer`, `#157`)는 있는데 `batch/run.py` 의 `BATCHES` 에 없었다 — 구동 주체가 없었다 |
| (함정) 묵은 신호는 합성 직후 사라진다 | 아카이브 28일 만료가 신호 **적재** 시각 기준 |

히스토리 경로 구분(본문의 세 번째 물음)은 진단 노트대로 이미 동작 중이라 손대지 않았다.

## 2. 사용자 결정 (2026-11-14, 대화)

1. 신호 단위 — **work 종결(merged)당 1건**. rejected 는 적재하지 않는다.
2. 배치 주기 — **주 1회 토요일 22시**. 원전 기본은 매일 22시인데, 합성이 상용 체인을 쓰고
   문턱 미달 신호가 남아 있으면 도는 날마다 호출이 나가서 줄였다. 트윈 `config.yaml` 의
   `batch.recipe_synthesis_schedule: daily` 로 되돌릴 수 있다.
3. 아카이브 만료 — **옮긴 시각(`archived_at`) 기준**. 옛 줄은 종전대로 `timestamp`.
4. 큐 내부 rejected 전이(`logic.py`)가 히스토리 기록을 안 부르는 건은 **범위 밖**.

작업 방식: 변경이 파일 서너 개라 서브에이전트·워커 분산 없이 이 세션이 worktree 에서 직접 했다.

## 3. 바꾼 것

| 커밋 | 내용 |
|---|---|
| `5e10121` | `gates.RECIPE_SYNTHESIS`(weekly·saturday·22시·입력 1건) + `run.BATCHES` 에 `_recipe_count`/`_recipe_run` 등록. 낡은 「배치가 아직 없다」 주석 정정 |
| `d24f45a` | `signals.record_work_merged`·`work_files` 추가. `patch_work_ep` 의 merged 전이 훅(히스토리 자동 기록 바로 뒤)에서 호출 — fail-soft, 응답 `signal_written`/`signal_error` |
| `e31da00` | `_archive_signals` 가 옮길 때 `archived_at` 을 찍고 만료를 그 시각부터 센다 |
| (이 커밋) | `master/README.md` 신호·합성기 두 행을 현행으로 + 이 리포트 |

파이프라인 신호에 실리는 것: `intent` = work 제목, `files_modified` = 조각 파일(단수·복수 필드, 중복 제거),
`iterations` = 라운드 수, `feedback_notes` = 검수 노트, `source` = `pipeline`. 큐가 모르는
`queries`·`files_read`·`error_recoveries` 는 비운다.

로그: 큐 로그에 `[signal] <work> merged → pipeline 신호 1건 (파일 N개 · 라운드 R) → <경로>` 와 실패 시
`[signal] [주의] … 적재 실패`. 배치는 합성기 줄 전부와 시작·끝 한 줄씩(대기 신호 수 · 생성 수 · 아카이브 이동 수).

## 4. 검사

- `master/test_batch.py` 69/69 · `test_signals.py` 39/39 · `test_recipes.py` 22/22 · `test_recipes_read.py` 42/42 — 모두 rc0.
  `test_signals` 는 **실제 8101 앱의 PATCH 라우트**를 임시 큐로 부른다: merged 1건 · rejected 0건 ·
  적재가 죽어도 종결 성립.
- 정적 검사(`pystatic.run_static`, 변경 8파일): pyflakes·imports·mypy 차단 0.
- 공식 통합 검사·`master/test_*.py` 전수: 아래 「5-1」.

### 격리 드라이런 (LLM 0 · 운영 트윈 무변경)

NS 신호 12건(2026-09-20~27 적재) 복사본에 `record_work_merged` 로 1건을 더하고, 배치 경로(`run.run`)에
가짜 chat 만 끼워 돌렸다.

    입력 13건 (requester 12 · pipeline 1)
    게이트   토 21시 시각 미달 · 토 22시 조건 충족 · 일 22시 요일 불일치
    실행     레시피 1건 · 신호 13→7건 · 아카이브 6건
    아카이브  6건 전부 archived_at 있음 · 가장 오래된 적재 2026-09-20 도 남음 · pipeline 신호 포함
    마커     기록됨 → 같은 밤 재판정 「간격 미달 (6일 필요)」
    운영 NS/recipes/_signals.jsonl 바이트 동일

[주의] 드라이런의 안티패턴 집계는 「카탈로그 라인 추출 실패 — 갱신 스킵」으로 끝났다. 내가 준 가짜 응답이
형식에 안 맞아서이고, 그 경로는 이번에 바꾸지 않았다(`test_recipes` 가 따로 잰다).

## 5. 한계 — 실제로 안 잰 것

- **실제 상용 체인으로 합성이 도는 것은 못 봤다.** 가짜 chat 뿐이다. 첫 실물은 마운트된 프로젝트에 신호가
  1건 이상 있는 토요일 22시 이후 `ax-batch.timer` 회차다.
- **배치는 마운트된 프로젝트만 돈다.** 지금 신호가 있는 곳은 NS(12)·ModularStage(1)이고 마운트는 AXCluster 라,
  그 12건은 NS 가 토요일 밤에 마운트돼 있어야 합성된다.
- **실제 분산 work 의 finalize 로 신호가 쌓이는 것은 못 봤다.** 임시 큐의 라우트 호출까지다.
- 합성기는 상용 체인 실패를 「클러스터 없음」으로 접어 0 을 돌려주므로, 그 경우에도 주간 마커가 써져 한 주를
  기다린다. 사유는 배치 로그의 합성기 줄에만 남는다.
- AXCluster 같은 `requester: master` 일감 흐름(`issue_finish`)은 work 를 만들지 않으므로 신호를 남기지 않는다.

### 5-1. 통합·전수 결과

- 공식 통합(`tests/integration` `test_axcluster.py`, worktree · `AX_PROJECTS_ROOT=/home/sim/ax-cluster`): `Ran 196 tests in 196.328s` · `OK` · rc0.
- 전수: `master/test_*.py` 222파일을 파일마다 별도 프로세스로 실행 — rc≠0 파일 0개.
- 전수 뒤에 README 두 행과 이 리포트를 더했다. 문서를 읽는 검사(`README`·`reports/` 를 언급하는 `master/test_*.py`)만 다시 돌려 전부 rc0.
- `git diff --check` rc0.

최종 결과는 Redmine `#383` 마감 노트.
