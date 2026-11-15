# 196 — #965 전수 테스트 속도 개선 (느린 파일 + 병렬 실행)

2026-11-15 · Claude · #967 배포 뒤 같은 세션에서 수행.

## 사용자 지시와 범위

- 「965번 먼저 진행하고, 자동리뷰에 나머지 지적사항들 먼저 고치고싶어」 — #965 → 남은 자동 리뷰 지적 → #968 순서.
- 인터뷰: 분류 modify(「응 수정 개선 하는 작업이야」) → 조사(A 느린 파일 + B 병렬 둘 다) → 명세(충돌 질문에
  「병렬 3회 반복 실패 0」 조건 추가 · 「멀티 쓰레드로 테스트를 진행하는 갯수도 컨피그로 빼자」) → 재현 건너뜀 →
  파급(설정은 저장소 안 `tests/test-parallel.json` + 환경변수) → `ax:spec` → 플랜 T1~T7 · C1~C5.
- 비범위: 상위 10 밖 파일 최적화 · 판정 로직·검사 수 축소 · pytest · 운영 코드 수정 · 서비스 재기동 · 배달.

## 사전 조사 코멘트의 대조

일감에 붙어 있던 06:31 원인 표는 가설로 다뤘다. 코드로 맞은 것: `.33` 실물 probe(`test_client_bundle.py:920`) ·
`redmine.py` 의 `key or api_key()` 10곳(대역 `sender` 를 줘도 `docker exec psql`) · `test_test_runnable` 의 노드마다
`get_source_segment`. **표에 없던 것**: `test_review` 의 6초는 픽스처가 아니라 `finalize` 기재 실패 재시도의
**실제 `time.sleep(3)` ×2** 였고, `test_pystatic`·`test_followup` 은 mypy 호출마다 **빈 캐시**(1.8초 vs 채운 캐시
0.4초, 실측)가 원인이었다. client_bundle 의 48.6초는 그날 `.33` 응답 지연이었다(재측정 3.6초).

## 바꾼 것 (`issue/965`)

| 커밋 | 태스크 | 내용 |
|---|---|---|
| `8743476` | T1 | `integration_checks.parallel_jobs(kind, root)` → `{jobs, source, reason}`. `AX_TEST_JOBS` 가 두 값 공통 덮어쓰기, 파일 없으면 1(종전 순차), 잘못된 값은 사유와 함께 1 |
| `d6bfb60` | T2 | `tests/integration/test_axcluster.py` — jobs>1 이면 첫 테스트에서 전체 `run_check` 를 스레드로 미리 돌리고 메서드 207개가 그 결과를 단정. 이름·출력(`FAIL: test_NN_…`, `work/followup.py` 가 해석) 유지. jobs=1 은 종전 테스트별 실행 |
| `ab025eb` | T3 | `python -m master.sweep` — 판정 rc, 수치 형식 A→B(종전 반복문과 같음), unittest 는 형식 C 로 **따로** 집계, 못 읽은 파일은 이름으로. `test_sweep.py` 25건 · `checks.json` 등록 |
| `f176851` | T4 | 실물 I/O 대역: client_bundle(`_facts`) · redmine(리더 미주입 `api_key` 가짜 키) · domain_index(벡터 채널 0건 — 머리말 계약) · test_runnable(`sys.path` 없는 줄은 건너뜀, 신구 판정 차이 0) · pystatic·followup(프로세스 내 mypy 캐시 공유, 실물 mypy 유지) |
| `92ba84c` | T5 | review·branch_prune·issue_flow 픽스처 템플릿 복사(원격 URL 재설정) · review finalize 의 재시도 sleep 대역 · service_freshness 실 저장소 의존 폐포만 메모 |

운영 코드는 `integration_checks.py`(설정 읽기 함수 추가)와 새 `master/sweep.py` 뿐이다. 상주 서비스가 import 하지
않으므로 재기동 대상이 없고, 워커 배달물도 아니다.

## 측정 (2026-11-15 19:24~19:31, 마스터 12코어)

| 항목 | 기준선 | 이번 | 판정 |
|---|---|---|---|
| 전수 병렬 8 | ~280초 | 26.7 · 27.3 · 27.2초 | C3 충족 |
| 전수 순차 `--jobs 1` | ~280초 | 165.0초 | 참고 |
| 통합 병렬 8 | ~232초 | 23.4초 ×3 | C3 충족 |
| 통합 순차 `AX_TEST_JOBS=1` | ~232초 | 220.9초 | 참고 |
| 검사 수 | 12122 · 207 | 12147 · 208 (+ test_sweep 25·1) · unittest 537 | C1 충족 |
| 병렬 반복 | — | 전수·통합 각 3회 실패 0 · 수가 순차와 같음 | C4 충족 |
| 설정 1 · 환경변수 | — | 파일 1 → 「병렬 1 · 출처 tests/test-parallel.json」 · env 1 → 「순차 실행 (env AX_TEST_JOBS)」 | C5 충족 |
| 상위 10 순차 합 | ~100초 | 40.2초 | **C2 제외**(사용자) |

상위 10 파일별(초, 전→후): review 19.0→8.1 · pystatic 15.4→6.9 · followup 12.9→6.6 · branch_prune 8.8→5.7 ·
issue_flow 7.2→5.5 · client_bundle 3.6→3.1 · service_freshness 7.3→2.4 · test_runnable 8.2→1.6 ·
domain_index 10.0→0.2 · redmine 7.4→0.1. 파일별 검사 수는 전부 전후 동일.

## C2 를 제외한 이유

남은 40초는 테스트가 **일부러 실물로 재는** 자리다 — 실제 git 머지·push·pre-push 훅, 「대역 없이」 실물 mypy.
더 줄이면 판정 대상이 바뀌어 스펙의 「같은 판정」과 부딪힌다. 병렬에서는 이 파일들이 다른 파일과 겹쳐 돌아
체감 시간(27초)에 거의 영향이 없다. 사용자: 「응 C2는 제외로 기록하고 리포트 진행해」.

## 남긴 관찰

- `test_nowork.py`·`test_rounds.py` 는 「실패 0건」만 찍어 수치를 못 읽는다. 종전 반복문은 이를 **조용히**
  건너뛰었고 새 실행기는 이름을 찍는다. 판정은 rc 라 영향이 없어 이번 범위에서 고치지 않았다.
- 종전 집계 12122 에는 unittest 형식 39파일(537건)이 들어 있지 않았다 — 새 실행기는 따로 보인다.
- 통합 병렬에서 `-f` 를 줘도 나머지 검사가 이미 실행돼 있다(보고는 첫 실패에서 멈춘다).

## 남은 것

- T7: 저장소 `CLAUDE.md` Tests 절의 bash 반복문을 `python -m master.sweep` 로 바꾸는 문구 — 자동 로드 문서라
  사용자 동의 뒤 반영 · 메모리 `full_test_sweep_before_commit` 갱신.

최종 결과는 Redmine #965 마감 노트.
