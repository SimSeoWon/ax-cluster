# 203 — #211 AXCluster 실사용 한글 검색 정합성 평가

작성: Codex · 2026-11-16 · 진행 중. 아직 품질 측정·정답 확정·마감 전이다.

## 사용자 결정·작업 위치

- 사용자 「211번 진행하자」 → 「응 기능 수정이야. 한글 사용시 정합성을 테스트할 수 있도록 근거는 충분히 수집되었니?」.
- 별도 AXCluster 정답 집합·ModularStage 기존 기준 유지에 「응!」, 정답 집합 구축·비교 측정·개선안 제시까지에 「응!」.
- 「응 지금 마운트 된건 AX 클러스터고 이 것을 주로 사용했어. 그리고 온톨로지는 딱히 아직 추가한거 없는 상태야」.
- T1~T4 제안과 수행 방식 선택 질문에 「단독으로 진행해줘」. 로컬 서브 에이전트로 조사·검증한다.
- 확정 스펙은 Redmine #211 `ax:spec`, 플랜은 `ax:plan`(T1~T4, C1~C6, autonomy=0.5).
- `issue_start_tool(211)` 원문 주요 필드:
  `ok=true`, `branch=issue/211`, `repo=/home/sim/ax-cluster/.ax-issues/211`,
  `checkout=/home/sim/ax-cluster`, `already=false`,
  `start_rev=3d874011ac7e4bd41f389b159fc6bedb6e11632e`, `lock=acquired`, `author.family=codex`.
  편집·검사·커밋은 응답의 repo에서만 한다. 운영 체크아웃은 main으로 보존한다.
- 스펙의 완료 범위는 정답 집합·4변형 비교·개선안까지다. 운영 검색 설정·가중치·온톨로지·ModularStage 정답표는 변경하지 않는다.

## T1 — 모집단 동결

실사용 로그 원본은 `/home/sim/ax-cluster/AXCluster/search_logs/*.jsonl`이다.
`search_log.jsonl`은 회전 가능한 최근 캐시라 누적 분모의 정본으로 쓰지 않는다(`master/context_search/search_log.py`).

동결 명령(운영 루트에서 수행, rc0):

```sh
jq -cs 'map(select(.task_type == "user_command" and .ts < "2026-11-16T23:25:00")) | unique_by(.search_id) | sort_by(.ts,.search_id)[]' AXCluster/search_logs/*.jsonl > /home/sim/ax-cluster/.ax-issues/211/reports/203-211-search-snapshot.jsonl
```

- 동결 파일: `reports/203-211-search-snapshot.jsonl` — 127검색/122요청.
- 시각: 2026-10-20T23:35:31.645991+09:00 ~ 2026-11-16T23:18:24.498733+09:00.
- SHA256: `82ef995a0a76aeb1514db682b0ec9505c5c44a659b2b298e015b26cea8d61817` (`sha256sum`, rc0).
- 이번 #211 조사 검색 `59ac206e1c2e4f2d9ce467d02ce9a0b3`은 위 시각 밖이다. 원문 「응!」를 가진 이번 조사 검색을 기존 개발 요구 표본으로 취급하지 않는다.
- #855 운영 확인용 `989e3120e41c42f99fe910b98a50701d`는 동결 파일 안에 보존하되 후보 모집단에서 제외한다.
- 제외 뒤 126검색/121요청, 한글 포함120검색/고유119질의(jq 독립 집계 rc0, 로컬 후보 조사와 일치).
- 기존 `bench_kr.hangul_only` 기준은 한글 포함 + 영문 식별자 토큰 없음이다. 해당 실사용 검색은 `34a8ae32e10d41a1b3e72f1d9716131b` 1건이다.
  대부분이 식별자 혼합 질의여서 순수 한글 게이팅의 품질 판정에 충분한 자료라고 확대 해석하지 않는다.
- 같은 request_id의 재검색은 독립 요청으로 세지 않고, 동일 질의 중복 및 평가용 검색을 구분한다.
- 후보30건은 주제 다양화를 위한 검토 규모다. 통계적 대표 표본 또는 정책 판정의 충분조건이 아니다.

## 측정 전 발견 — 소스 근거, 미실행

1. `master/context_search/search.py:226`의 `finally`는 `search_log.log_search`를 무조건 호출한다.
   기존 `suppress_logging()`으로 벡터 내부의 중복 기록은 억제하지만 바깥 융합 검색 기록은 막지 않는다.
   따라서 앞 인터뷰의 「기존 억제 계약 활용」만으로 분모 오염 방지가 충족된다고 볼 수 없다.
2. `ContextIndex` 생성 경로는 `get_or_create_collection`, 모델 불일치 경로는 delete/create를 할 수 있다.
   `Bm25Index` 생성 경로도 CREATE VIRTUAL TABLE 및 commit이 있다. 평가용 생성자를 운영 DB에 직접 실행하지 않는다.
3. 기존 `run_variant`는 baseline 검색의 기본 pool=45(limit15×3)와 gated BM25 limit15를 사용한다.
   비교 조건과 반환 cutoff를 명시하여 반복 가능한 실측을 설계해야 한다. 아직 우열·회귀로 판정하지 않는다.

현재 운영 측정·평가 도구 실행·테스트는 하지 않았다. 정답 확정 전이다.

## 후보 산출물 검증

`reports/203-211-candidates.json`은 Q01~Q30과 원본 search_id·주제·선정 근거를 담는다.
원문 query/user_request/request_id/ts/result_snapshot은 동결 파일과 search_id로 연결한다.
첫5개 소스 대조 제안(Q02·Q05·Q10·Q21·Q23)은 proposed_expected/basis에만 기록했다.
expected=[]·confirmed=false라 아직 채점 정답이 아니다.

`jq -s --slurpfile c reports/203-211-candidates.json … reports/203-211-search-snapshot.jsonl` 검증(rc0):
후보30·원본 일치30·요청30·고유 질의30·원문 누락0·스냅샷 누락0·스냅샷 문서188·
기존 hangul_only1·제외 대상 선정0·전 후보 미확정 true.
T1은 데이터 산출물로 검증했고 아직 코드 변경이 없어 실행 테스트는 하지 않았다.

## 조회 오류·정정

- `ModularStage/search_logs`와 `pyproject.toml`을 존재 확인 없이 조회 인자에 넣어 `No such file or directory` rc2가 발생했다.
  전자는 존재 확인된 `ModularStage/search_log.jsonl`로 재조회했고 후자는 근거에서 제외했다. 생성·설정 변경하지 않았다.
- 분류 첫 노트를 한국어가 아닌 언어로 기록하여 같은 `interview_step_tool(classify)`로 한국어 정정 노트를 남겼다.
- T2 설계 조사에서도 존재를 확인하지 않은 `master/sandbox.py`를 조회 인자에 넣어 rc2가 났다.
  확인된 `master/context_search`·`master/test_sandbox.py`만으로 다시 조회(rc0)했고 경로를 생성하지 않았다.
- 위 오류는 검색 품질·저장소 결함의 근거가 아니다.

## 재개 근거

- T1 커밋 `740ac72f871c94d0375edf87b490112c536044a4`, 완료 전이 성공. C1 충족.
- T2 작업중, T3~T4 대기. 첫5건 사용자 확정 질문 대기, 현재 확정0/30.
- 후보30건 소스 대조 제안은 `203-211-answer-proposals.md`에 보존했다.
  Q19(스킬·훅·타이머 전반 분석)·Q24(등록 해제 기능 부재/수동 경로)는 정량 정답을 억지 지정하지 않고 미판정 권고다.
  Q14·Q26·Q29·Q30은 요구 전체와 부분 책임의 차이를 명시했다. 정답 수를 맞추려고 미확정을 확정하지 않는다.
- 신규 개발을 요청했던 과거 질의는 현재 완성된 모듈을 현재 재측정의 정답 후보로 제안할 수 있으나,
  그 문서가 당시에도 존재했다고 가정하여 과거 검색을 실패로 채점하지 않는다. 과거 스냅샷/현재 재측정은 분리한다.
- 후보·정답은 완료 근거와 사용자 확인 전까지 확정하지 않는다.
- #855 인계의 잔여 관측도 실제 확인됨: #211 잠금 뒤 검색
  `8c548bc7a6094f6996f9fdc6267eff25`의 원본 로그는 `issue_id=211`,
  `issue_id_source=issue_lock`, purpose 보존이었다. #855 상태를 별도로 변경하지 않았다.
- 세션: `~/.codex/sessions/2026/11/16/rollout-2026-11-16T23-38-59-01a1e4cc-0b40-7b63-9498-c818714aac0f.jsonl`.

최종 결과는 Redmine #211 마감 노트.
