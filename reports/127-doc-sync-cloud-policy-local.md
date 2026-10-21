# 127 — #839·#840 로컬 구현과 통합 실패 체크포인트

2026-10-21 · Codex · 기준 main `4f40439` = origin/main

## 승인·방식

사용자가 #839·#840을 선택하고 로컬 서브 에이전트를 지시했다. `distribute`·`ax-redmine`·
`ax-handoff` 기존 절차와 실제 소스를 대조했다. 워커 파견·커밋·push·배포·서비스 재기동은 없다.
처음 잘못 지정한 루트 `systemd` 조회 오류(rc2)는 보고 후 사용자 재개 지시를 받았다.
이후 `rg` 매칭 없음(rc1)은 코드·검사 실패가 아닌 정상 검색 결과임을 사용자에게 설명했고
사용자가 문제없음을 확인하여 작업을 계속했다. 실제 검사 실패의 중단 규칙은 유지한다.

## #839 — 영향 문서 탐지 구현, 전체 완료 아님

수정 5파일: `master/doc_sync/registry.py`, `master/doc_sync/__main__.py`,
`master/test_doc_sync_registry.py`, `master/test_doc_sync_cli.py`, `docs/document-sync.md`.

`plan`·`draft`의 opt-in `--since`·`--until`로 커밋 범위의 변경 경로를 읽고 등록 문서 정본·근거와
대조한다. rename old/new·삭제·등록목록 변경·명시 ID 교집합을 처리하고 포함·제외 사유를 남긴다.
비교 범위는 커밋이지만 실제 본문은 현재 작업 트리라는 점과 dirty 여부를 출력한다.
영향 없음은 LLM의 `unchanged` 판정과 별개다. 삭제된 등록 근거는 기존 등록 검증에서 거절한다.

직접검사 registry 11/11·CLI 9/9 통과. 실제 저장소에서 다음 읽기 전용 명령도 rc0:

```bash
.venv/bin/python -B -m master.doc_sync plan --since HEAD~1
```

최근 커밋의 CLAUDE·home-claude 2건을 포함하고 나머지 6건을 제외 사유와 함께 출력했다.
보호 문서 원본 쓰기나 실제 LLM draft는 실행하지 않았다.

미결정: Redmine·운영 상태를 출처/시각 있는 스냅샷 파일로 선택 문서 근거에 연결할지,
doc_sync의 직접 live 수집까지 구현할지. `ax-docsync` §0의 사람 결정 규칙 때문에 답을 기다린다.
보호 문서 4개 실제 실증은 문서별 계획·동의·레인 선택 전이다. 교차 계열 검토는 선택 사항이다.

## #840 — 생성 정책·표시·문서 주기 구현, 미완·미검증 부분 있음

신규: `master/work/llm_policy.py`, `master/work/revalidation.py`,
`master/test_llm_policy.py`, `master/test_revalidation.py`.
기존 수정: `context_synth/synth.py`, `ontology/synth.py`, `work/lanes.py`, `work/infer.py`,
`work/runner.py`, `batch/run.py`, `batch/gates.py`, 관련 직접검사들과 공식 `checks.json`.

부모 #788의 실제 결정과 과거 `65951cb` 계약을 대조했다. 기본 순서는 agy→codex,
앞 둘 모두 quota일 때만 Claude, 세 cloud 모두 quota일 때만 local이다. 형식·사실·일반 오류가
섞이면 Claude/local로 넘기지 않는다. 모델 본문에 quota 단어가 있는 것과 실제 실패 채널을
구분한다. 명시 단일 cloud 호출은 유지하며 local 단독 지정으로 quota 조건을 우회할 수 없다.

- context는 문서 frontmatter에 `needs_revalidation`, 모델·소스 목록·지문을 남긴다.
- ontology는 domain manifest `generation`에 같은 의미의 메타데이터를 남긴다.
- lane 성공의 local 결과는 별도 영속 기록·제출 self_check·이슈 노트에 표시한다.
  골조를 못 읽으면 Claude로 바로 우회하던 경로는 실패를 드러내도록 바꿨다.
- 문서 배치는 기존 유휴 타이머/게이트를 사용하고 표시 문서만 cloud-only로 재합성한다.
  소스 및 산출물 지문을 쓰기 직전에 다시 대조한다. 신규 서비스 설치·기동은 없다.
- 조각은 주기 배치가 자동 덮어쓰기·재개·표시 해제를 하지 않는다. 별도 후보 보관과
  후속 라운드 자동 준비 중 반영 방식을 사용자에게 질문했고 답을 기다린다.
- 코드 조각의 사실 판정은 기존 wcommit 층2·bounded revise 경로다. 동일 호출 안에서
  사실 실패 후 다음 cloud로 즉시 재작성하는 루프는 미구현이므로 전체 정책 완성으로 보지 않는다.

직접검사 통과: 정책 5/5, context 212/212, ontology 50/50, synth_parallel 29/29,
lanes 43/43, infer 327/327, runner 410/410, 재검증 12/12, 기존 batch 50/50.
실제 모델·브로커 생성·워커 파견 없이 주입된 호출자로 검사했다.

## 실제 통합 실패 — 수정하지 않고 중단

```bash
.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

**rc1·실행 36파일 중 35통과/1실패**. 이후 항목은 `-f` 때문에 미실행이다.
실패는 `master/test_review_gen.py:390-391`의 구정책 기대값:

```python
LN.DEFAULT_LANES[0] == "codex"
```

새 순서는 agy이므로 해당 파일은 89/90 통과했다. `layer2_verify.WHY_BACKENDS`의 리뷰/계획 생성
체인과 본문 작성 체인은 별도 범위다. 이 검사를 갱신한다는 이유로 다른 생성/검증 체인을
임의 변경하지 않는다. `test_review_gen.py`는 최초 허용 편집 목록 밖이므로 수정 승인 전이다.
다른 직접검사 통과를 전체 통합 통과로 주장하지 않는다.

## 읽기 전용 리뷰에서 남은 결함

1. ontology의 cloud 레이어 서술이 활성 L1·L2 중 L1만 반환해도 기존 local L2 서술을
   보존한 채 `descriptions_revalidated=True`로 전체 표시를 해제할 수 있다.
   활성 비보호 레이어 coverage를 확인하거나 누락 시 표시를 유지해야 한다.
2. 문서 재검증이 정렬 첫 2건을 먼저 자른다. 그 대상이 소스 변경·영구 실패 상태면
   뒤 문서가 계속 처리되지 않는다. 실제 호출 예산 적용 또는 회전 방식이 필요하다.
3. 스캔의 leaf/direct-parent symlink 검사는 있으나 context/ontology 루트의 정본 경계를
   확인하지 않는다. 루트·상위 경계 검사가 필요하다.
4. context 쓰기는 기존 직접 write 방식이다. 지문 검사 직후 다른 writer가 쓰는 창을
   원자적 compare-and-swap으로 막는 보장까지 제공하지 않는다.

이 결함들은 테스트 실패 이후 수정하지 않았다. 검사·서브 에이전트는 모두 종료됐다.
코드·검사·문서 변경은 미커밋으로 보존한다. #839·#840은 진행이며 완료 처리하지 않았다.

## 2026-10-22 재개 — Claude · 실패 수정과 커밋

사용자 「#839 #840 실패 수정 이어서 하자」 → 범위 확대 「응 넓혀줘!」 → 「결과 나오면 커밋하고 배포해줘」.
로컬 서브 에이전트 없이 이 세션이 직접 고쳤다.

고친 것:

- `master/test_review_gen.py` — 구정책 검사 `DEFAULT_LANES[0] == "codex"` 를 #788 본문 결정
  (agy → codex → claude → 로컬)과 `exclude_author`(#379) 교차 계열 검사로 바꿨다.
  리뷰/계획 생성 체인(`WHY_BACKENDS`)과 검증 체인(`BACKENDS`)은 바꾸지 않았다. 93/93.
- 결함 ① `ontology/synth.py` — 잠기지 않은 활성 레이어 서술이 빠지면 format 실패로 다음 cloud 에 넘긴다.
  cloud 가 모두 일부만 주면 재검증 표시와 기존 로컬 서술이 남는다. 53/53 · 수정을 빼면 새 검사 3건 실패(실측).
- 결함 ② `work/revalidation.py` — `limit` 은 실제 재합성 호출만 센다(소스 변경·경계 거절은 안 셈).
  호출한 대상의 시도 시각을 `<twin>/revalidation/document_attempts.json` 에 남겨 가장 오래 안 본 것부터 고른다.
- 결함 ③ 같은 파일 — context·ontology·domains 루트가 symlink 이거나 트윈 밖으로 풀리면 스캔을 거절한다. 재검증 14/14.
- 처음으로 `-f` 없이 공식 통합을 끝까지 돌려 새 실패 2건을 찾았다(Codex 실행은 36번째에서 멈춰 못 봤다):
  - `test_client_spec.py:571` — 단독 로컬 주입 `chain=["fake"]` 를 #840 정책이 거절. cloud 셋을 quota 로 주입해 정책 경로로 고쳤다.
  - 🔴 `test_descriptions.py:224` — `describe_domain` 기본 모델이 agy 가 되어 **검사가 실제 agy 를 불렀다**
    (이 세션의 통합 2회분으로 추정, 사용량 기록 미대조). cli 를 주입해 막았다.
- `tests/integration/checks.json` 에 `master/test_handoff_size.py`(#842) 추가.

검증 (PATH 앞에 호출을 기록하고 실패하는 가짜 `agy`·`codex`·`claude`·`ssh`·`scp` 를 둔 채):

- 공식 통합 `test_axcluster.py` **181/181 rc0** · 상용 CLI 호출 0건
- `master/test_*.py` 전수 **185파일 rc0 · 9,115/9,115** · 상용 CLI 호출 0건
- [주의] 통합 중 SSH 시도 24건이 기록됐다(`.43`·`.33` 탐침, `fake@fake` scp) — 가짜 ssh 가 막았다.
  기존 검사의 실제 SSH 의존이며 이번 범위 밖이라 손대지 않았다.

남은 것(미결정 그대로): #839 근거 방식 · 보호 문서 4개 실증 · #840 조각 재작업 반영 방식 ·
코드 조각 사실 실패 → 다음 cloud 재작성 루프 · context 쓰기 비원자(CAS 아님).
