# 178 — #750 related 근거 검증과 YAML 미상 문자열 인용

2026-11-14 · 지휘 Codex · 로컬 Codex 서브에이전트 구현, 주 지휘자 diff 검토·검사·운영 교정.

## 승인과 작업 위치

- 사용자 원문: 「750 진행하자」 → 「응 단독으로 진행해줘!」. 가짜 related 근거 검사, 프롬프트 예시·태그 지시문 잔재 방지, 정상 외부 참조 통과 범위로 플랜 등록.
- 추가 결정: 「YAML에서 기존 ?표도 모두 정리하고 앞으로도 따옴표로 묶는게 맞아」. 기존 등록 프로젝트 문서 교정과 정본 출력 `"?"`를 T1/T2에 반영.
- `plan_start_tool`: 최초 `verdict="plan_needed", ok=false`; 플랜 합의·등록 뒤 시작. 재개는 `verdict="resume", ok=true, tasks=["T1"]`.
- `issue_start_tool` 응답: `repo="/home/sim/ax-cluster/.ax-issues/750"`, `checkout="/home/sim/ax-cluster"`, `branch="issue/750"`, `start_rev="a2290119c87ee7b67dd65f91556775511d1d41e3"`, `lock="acquired"`, 작성 계열 `['codex']`. 재개 응답은 `already=true`, `lock="already"`.
- 운영 main은 편집하지 않고 위 worktree에서 구현·검사·커밋한다. 세션: `~/.codex/sessions/2026/11/13/rollout-2026-11-13T23-55-29-01a1d568-1144-7ac1-9e5c-3c632e5f7f7a.jsonl`.

## 결함별 근거와 변경

1. **가짜 related 통과 — 사실.** 기존 `verify.verify`는 `claimed & ghost_pool`로 주석에만 있는 이름을 거부했다. 코드·주석 어디에도 없는 `UReviewGen`·`AReviewIssue`는 이 교집합에 없어 통과했다. related 이름을 선언·프로젝트 심볼·주석을 제거한 실제 소스 토큰과 정확 일치 대조한다. 그래프에 없어도 소스가 실제로 참조하는 엔진·외부 이름은 통과한다. Python qualified 이름과 매핑·블록/인라인 목록도 읽는다.
2. **프롬프트 예시 복사 — 예시 노출은 사실, 정상 개념 태그 자체는 오류 아님.** 구체적 예시 클래스와 태그 목록을 빈 목록 및 작성 규칙으로 바꿨다. `영문태그1`·`한글개념태그2`·생략 부호 같은 명백한 자리표시자만 형식 거부한다. `미션, 스폰, 대화창, 상태동기화`는 실제 문서에서 정당할 수 있어 금지하지 않는다.
3. **검사 문서와 저장 문서 불일치 — 기존 순서에 존재.** related 정규화가 사실 검사 뒤에 있어 검사 후 이름이 바뀔 수 있었다. 정규화를 사실 검사 앞으로 옮기고 원문 기록의 `normalized_doc`도 실제 검사 문서와 일치시켰다. 실패하면 기존 파일을 남기며 다음 모델 후보를 검사한다.
4. **bare `?` — 기존 AX가 허용했지만 표준 YAML 문자열이 아님.** #712 `c237a93`와 `related.normalize`는 이름을 알고 경로를 모르는 상태를 `이름: ?`로 허용했다. 표준 YAML은 `?`를 매핑 지시자로 읽는다. 사용자 결정으로 정본은 `이름: "?"`. `finalize`는 과거 형식 입력을 YAML 검사 전에 좁게 인용하고, graph의 정확한 이름이 있으면 경로로 채우는 동작은 유지한다. 소비자는 인용 표기를 기존 문자열 값 `?`로 읽는다.
5. **모델 체인 변경 — 이번 대상 아님.** 제목의 gemma3:12b는 현행 체인에 이미 없다. 현행 `LOCAL_MODEL="gemma4:e4b"`, `SYNTH_CHAIN=(*CLOUD_LANES, LOCAL_MODEL)`은 변경하지 않았다.

## 기존 문서 교정 계약

기존 `master.context_synth.related` CLI에 `--quote-unknown-only`를 추가했다. 기본은 계획이고 `--confirm`이 쓴다. 그래프 조회·경로 보정·문서 재합성을 하지 않는다. related 블록의 값·단독 항목·미상 키의 bare `?`만 인용하며 본문·스탬프·주석·필드 순서·CRLF를 유지한다. strict UTF8로 읽으며 읽기 실패를 숨기지 않는다. 반복 적용은 변경0이다. `_domains` 같은 색인 제외 문서도 인용 교정에는 포함한다.

운영 조회 명령(작업 위치 worktree, 해석기 `/home/sim/ax-cluster/.venv/bin/python`):

```sh
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m master.context_synth.related AXCluster --quote-unknown-only
```

NS·ModularStage·ServerTest에도 같은 명령을 각각 사용한다. 계획 실측: AXCluster 479파일 중 92파일180줄, NS 104파일 중 56파일85줄, ModularStage 1055파일 중 101파일231줄, ServerTest 0파일. 앞선 rg 검색은 CRLF 끝을 포함하지 않아 174파일334줄만 찾았고, 정본 전수 조회는 249파일496줄을 찾았다.

같은 명령에 `--confirm`을 붙여 각각 적용 rc0: AXCluster 92파일180줄, NS 56파일85줄, ModularStage 101파일231줄, ServerTest 0. 합계 249파일496줄. 적용 뒤 기본 계획 명령으로 다시 읽어 네 프로젝트 모두 `파일 0개 · 줄 0개`, `bare ? 잔여 0줄` 확인(rc0). 전수 조회 479+104+1055+0=1638 컨텍스트 문서. 별도 ontology YAML을 포함한 최초 목록은 1938파일이고 bare 표기는 컨텍스트 쪽에서 발견됐다. 새로 문서를 생성하거나 재합성하지 않았다.

## 실패 원문과 재개

- 불필요한 `/tmp` 전체 `rg --files` 조회가 systemd 보호 디렉터리 `Permission denied`로 rc2. 수정 없이 중단하고 사용자 「응 다시 진행해」로 재개.
- 새 strict YAML 검사에서 기존 `AReviewIssue: ?`가 파싱 실패. `test_context_synth.py` rc1, 새 related 검사 5건 실패 뒤 `AttributeError: 'NoneType' object has no attribute 'unknown_related'`. 기존 AX 규약과 표준 YAML을 혼동했다. 사용자 위 인용 결정에 따라 legacy 인용→YAML 검사 순서로 수정.
- 문서 1938개 경로를 명령 인자 하나로 전달해 `Argument list too long (os error 7)`. 사용자 「응」 뒤 100파일 묶음 조회로 재개. `rg` rc1·출력 없음은 일치 없음이라는 조회 결과이며 서비스/검사 실패로 해석하지 않았다.
- `apply_patch verification failed: Failed to find expected lines ... verify.py: 이름이 유령으로 잡혔다...`. 실제 줄은 `에 실재한다...`였다. 작성한 패치 문맥 오류, 마지막 묶음 전체 미적용 확인. 사용자 「수정해」 후 실제 줄로 적용.
- 공식 통합 1차 rc1: `Ran 74 tests in 72.058s`, `FAILED (failures=1)`, `test_verify_gate: 37/40 통과`. 실패3건 모두 `[중요] 실측 근거가 없는 related_classes: LogNS`. 공통 `_doc`는 LogNS 관계를 넣었지만 접두·한글 조사 검사는 GameMode 소스만 주고 다른 파일의 심볼 근거를 안 줬다. 실제 NS_H/NS_CPP의 살아 있는 식별자에서 known을 도출해 긍정·부정 대조군 모두에 전달했다. known 미전달 시 거부되는 대조 검사 추가. production 판정은 약화하지 않았다. 사용자 「그래 다시 테스트 시도해」 후 재검사.

## 검증 기록

- 관련 검사: `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python master/<검사>.py`. `test_related` 33/33 rc0, `test_context_synth` 251/251 rc0, `test_context_search` 96/96 rc0, `test_verify_gate` 41/41 rc0. 로그 `/tmp/ax-750-{related,context-synth,context-search,verify-gate}.log`.
- LLM을 주입한 실제 합성 진입점 검사: 가짜 related 저장 거부·기존 파일 보존, graph 경로 정규화 후 이름 검사·저장, 원문 기록 일치, 다음 모델의 정상 결과 저장. 상용 CLI·운영 LLM 호출로 품질을 측정한 결과는 아니다.
- 코드 커밋 `01307dc` — `fix: ground related names and quote unknown YAML paths (#750)` (10파일).
- 정적: `pystatic.run_static(".", "a2290119c87ee7b67dd65f91556775511d1d41e3", 변경파일10, python="/home/sim/ax-cluster/.venv/bin/python")`, rc0. pyflakes 차단0·기존0·노트2(0.3초), imports 6모듈 차단0·환경0(0.4초), mypy call-arg 차단0·기존0·노트50(40.7초). 전체 JSON `/tmp/ax-750-static.log`.
- 공식 통합 최종 **195건, 206.265초, OK, rc0**. 실행은 worktree에서 `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`, 로그 `/tmp/ax-750-integration.log`. 알려진 `sg gitea` 그룹 제한 때문에 이 명령만 샌드박스 밖 실행 승인을 받아 돌렸다.
- `git diff --check` rc0. T1은 코드 커밋·관련 검사·정적 근거로 완료 마킹했고, T2는 운영 교정·리포트·마감 뒤 절차를 수행 중이다. `issue_finish`의 done/why와 배달 결과는 Redmine 마감 노트에 남기며, 이후 결과를 이 리포트에 소급해 손으로 덧붙이지 않는다.

## 한계

실제 참조하는 이름인지 확인하는 검사이며 이름에 대응하는 경로의 정확성·협력 관계의 강도까지 증명하지 않는다. 기존 심볼 근거는 문자열 리터럴도 살아 있는 본문에 남기는 계약을 따른다. 정상 개념 태그가 내용과 관련 있는지까지 결정적 검사로 판단하지 않는다. 전체 기존 문서의 YAML 오류를 일괄 수리하는 작업은 아니며 물음표 인용만 교정한다. 자동 해시·종합 리뷰 결과는 마감 시점에 미확인이다.

최종 결과는 Redmine 마감 노트.
