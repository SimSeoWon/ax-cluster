# 182 — #943 큐 내부 rejected 종결의 히스토리 기록

2026-11-14 · Claude(마스터 세션) · 일감 `#943` · 브랜치 `issue/943` (시작 리비전 `b4e8767`)

## 1. 무엇이 문제였나

`#383` 진단의 부수 관찰에서 나온 건이다. work 종결의 사실 기록(`history_gen.record_work_terminal`)은
`PATCH /api/v1/works/{work_id}` 훅 한 곳에서만 불렸다. 조각 실패로 큐가 **스스로** 라운드를 뒤집는
전이(`logic_lifecycle._flip_if_all_terminal`)는 그 라우트를 지나지 않는다.

실측(2026-11-14): 큐에 rejected work 8건 · cancelled 11건, 트윈 세 곳(NS·AXCluster·ModularStage)의
`tags: [pipeline, rejected]` 히스토리는 **0건**. 실패 사유 자체는 Redmine 종결 노트에 남고 있었다.

## 2. 사용자 결정 (2026-11-14, 대화)

1. **rejected 만** 기록한다. cancelled 는 적지 않는다(대부분 프로브·즉시 취소).
2. rejected work 가 재작업으로 다시 열려 나중에 merged 로 끝나도 **라운드별로 둘 다 남긴다.**
   같은 라운드의 중복만 막는다.
3. 과거 종결 work 는 **소급하지 않는다.**

작업 방식: 변경이 파일 서너 개라 이 세션이 worktree 에서 직접 했다(`#383` 과 같은 방식).

## 3. 바꾼 것 — 커밋 `9287515`

- `task_queue/logic_cleanup.py` — `_record_rejected_history` 를 `_auto_cleanup_work_async` 맨 앞에서 부른다.
  내부 전이 네 경로(post-fail · post-verify · post-cancel · boot-recover)가 모두 이 함수를 지나므로 자리가 하나다.
  - `merge_status == "rejected"` 일 때만 쓴다.
  - 본문에 라운드 번호와 실패 조각·사유(`fail_detail` → `last_feedback` → `verdict_feedback` → `fail_reason` 순,
    200자)를 싣는다. 인프라 판단 불가(`#821`) 조각은 그렇게 표시한다.
  - 같은 라운드 중복은 work 레코드의 `history_round` 가 막는다 — 기동 복구의 재공지(`#891`)가 같은 함수를
    다시 부르기 때문이다. 기록에 성공했을 때만 표시를 쓰므로, 실패하면 다음 재공지 때 다시 시도한다.
  - fail-soft: 기록이 죽어도 공지는 간다. 기록·생략·실패 모두 큐 로그에 `[history]` 한 줄.
  - 🔴 `_history_paths` 는 **라이브 큐 루트에서만** 실트윈을 푼다(`persistence.is_live_queue_root`). 임시 루트로
    도는 검사가 등록된 프로젝트의 `history/` 에 쓰지 않게 하는 장치다.
- `context_synth/history_gen.py` — `record_work_terminal` 에 선택 인자 `round_no`·`failures`. 주면 본문에 라운드와
  「실패 조각」 절이 붙고 파일명에 `r<N> <종결>` 이 붙는다. 안 주면 종전과 같다.
- `task_queue/server.py` — PATCH 훅이 rejected 기록을 남긴 뒤 같은 `history_round` 표시를 쓴다
  (사람이 반려한 라운드를 내부 경로가 다시 쓰지 않게).
- `master/test_history_terminal.py` 신규(`checks.json` 등록) · `master/README.md` 한 행.

### 만들다가 걸린 것

히스토리 파일명은 `분 단위 시각 + 제목` 이다. 같은 work 의 라운드 1·2 가 같은 분에 기록되자 **두 번째가 첫
번째를 덮어썼다**(신규 검사 29건 중 1건 실패로 드러남). 라운드 기록의 파일명에 `r<N> <종결>` 을 붙여 갈랐다.
[주의] 일반 경로(`write`)의 「같은 분 · 같은 제목이면 덮어쓴다」는 그대로다 — 이번 범위가 아니다.

## 4. 검사

- `master/test_history_terminal.py` 29/29 — 임시 큐로 **실제 `submit_fail` → 전이 → 후처리**를 돌린다:
  내부 rejected 1건 기록 · 재기동 재공지 중복 0 · 성공 라운드·cancelled 0건 · 재작업 라운드 별도 기록 ·
  기록 실패해도 공지 진행 · 임시 루트는 실트윈 미해석 · PATCH 표시.
- 인접: `test_history_gen` 24/24 · `test_notice_recovery` 35/35 · `test_signals` 39/39 · `test_work_mode_patch` rc0.
- 정적 검사(`pystatic.run_static`): pyflakes·imports·mypy 차단 0.
- 검사 뒤 운영 트윈 `history/` 에 검사용 제목의 파일이 없음을 확인했다.

### 4-1. 통합·전수 결과

- 공식 통합(`tests/integration` `test_axcluster.py`, worktree · `AX_PROJECTS_ROOT=/home/sim/ax-cluster`): `Ran 197 tests in 196.835s` · `OK` · rc0 (신규 검사 1건 포함).
- 전수: `master/test_*.py` 223파일을 파일마다 별도 프로세스로 실행 — rc≠0 파일 0개.
- 전수 뒤에도 운영 트윈 `history/` 에 검사용 제목의 파일 없음.
- 전수 뒤에 더한 것은 이 리포트뿐이다. `git diff --check` rc0.

## 5. 한계 — 실제로 안 잰 것

- **라이브 큐에서 실제 work 가 rejected 로 끝나 기록이 생기는 것은 못 봤다.** 임시 큐까지다. 첫 실물은 배포 뒤
  조각 실패로 끝나는 첫 분산 라운드다 — 큐 로그의 `[history] … rejected(큐 내부 종결)` 줄로 확인한다.
- 실트윈 경로 해석(`resolve(work.project)`)은 검사에서 바꿔 끼웠다. 그 줄 자체는 PATCH 훅의 `_paths_for` 와 같은
  호출이지만 이 자리에서 돈 적은 없다.
- 과거 rejected 8건에는 기록이 없다(결정 3).

최종 결과는 Redmine `#943` 마감 노트.
