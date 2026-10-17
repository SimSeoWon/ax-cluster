# #815 ⑤ — ⑦ 회귀 선택 보강: import·경로 언급까지 고른다

2026-10-17 23:05 ~ · Claude · 마스터 담당 `codex`·워커 모드 `codex`는 바꾸지 않았다. 구현은 사용자 선택에 따라
**로컬 서브 에이전트**가 했고, diff·전수·드라이런은 마스터가 직접 대조했다.

## 계기와 사전 실측

지금까지 ⑦은 바뀐 파일과 같은 이름의 `master/test_<stem>.py`만 골랐다. 그래서 10-11 #805·#363이 `work/review.py`에
배달되지 않는 상대 import를 넣었을 때, 그것을 잡던 `test_client_bundle`이 ⑦에서 돌지 않았다(#815 ⑤의 계기).

착수 전에 「같은 이름 + 직접 import + 경로 언급」 규칙을 저장소에 그대로 적용해 몇 개가 골리는지 쟀다
(모듈 204 · 테스트 171).

- 모듈 하나가 고르는 테스트: 중앙값 2 · 평균 2.9 · 최대 38(`context_search/paths.py`).
- 고르는 수가 늘어나는 모듈은 138개, 그래도 0개인 모듈은 26개다.
- `work/review.py`는 7개를 고르고, 그 안에 `test_client_bundle`이 들어 있다.
- 간접 import는 세지 않았다.

사용자 결정은 둘이다. 규칙은 「직접 import + 경로 언급」(간접 import 제외), 진행은 로컬 서브 에이전트.

## 구현 (`04463ef`)

- `regression_targets(tree, files, logf=None)`
  - 검사 트리 안의 테스트를 호출당 한 번 `ast`로 파싱해 캐시한다.
  - 직접 import로 치는 형태: `import a.b` · `from a.b import` · `from a import b`(여러 줄 괄호 · 별칭 포함).
    파싱에 실패하면 정규식으로 판정하고 노트를 남긴다.
  - 경로 언급: `work/review.py`나 `master/work/review.py` 문자열. 앞뒤가 이름 글자면 언급으로 치지 않는다.
  - 순서는 같은 이름이 먼저, 나머지는 정렬. 파일마다 이유별 건수 노트를 달고, `code_build_fn`이 로그를 한 줄 찍는다.
  - 공식 목록 제외와 「대응 없음」 노트는 그대로다.

## 드라이런이 찾은 것 — 검사 트리에서 항상 실패하는 테스트

1차 드라이런에서 무해한 변경(주석 한 줄)도 ⑦이 실패했다. 새로 골린 테스트 일부가 마스터 체크아웃이 아닌 트리에서는
**변경과 무관하게** 실패했기 때문이다. 검사용 worktree에서 전수를 돌리니 171개 중 4개가 그랬다.

| 테스트 | 원인 | 처분(사용자 선택 1번) |
|---|---|---|
| `test_client_bundle` | 실제 레지스트리(NS uproject)를 읽는 검사 2건 | 임시 `AX_PROJECTS_ROOT` 픽스처 트윈으로 바꿈. 검사 내용은 그대로 |
| `test_followup` | 「wait 명령」 검사가 `/home/sim/ax-cluster`를 기대 | 기대값을 테스트의 체크아웃 기준으로(`mcp_server`는 변경 없음) |
| `test_ontology` | git 밖 트윈의 도메인 manifest가 필요 | `MASTER_ENV_TESTS` — ⑦에서 빼고 「마스터 전수가 돈다」 노트 |
| `test_sandbox` | 설치된 유닛과 실제 루트의 트윈을 검사 | 같음 |

이 문제는 옛 규칙에도 숨어 있었다(`followup.py`를 바꾸면 `test_followup`이 같은 이름으로 골려 실패했을 것이다).
새 규칙에서는 이 테스트들이 훨씬 자주 골리면서 드러났다. `test_client_bundle`을 격리한 덕에 ⑥의 선행 조건도 풀렸다.
다만 그 테스트의 `bundle.probe(.33)`는 아직 실제 SSH로 접속한다.

- 검사: `test_followup` 347/347 · `test_client_bundle` 503/503(마스터 · 격리 worktree 양쪽) · 전수 171파일 실패 0.

## 드라이런 (격리 worktree, ⑦이 부르는 `followup.code_build_fn` 그대로)

미커밋 테스트 수정을 기준 커밋으로 먼저 올리고, 그 위에 한 커밋을 더 얹어 비교했다. 큐·레드마인·원격에는 쓰지 않았다.
worktree 잔여는 0.

| 경우 | 결과 |
|---|---|
| A — `work/review.py`에 배달되지 않는 `revise` 상대 import(#805·#363 회귀 재현) | **차단**. 경로로 골린 `test_client_bundle`이 잡았다. 옛 규칙이면 `test_review`만 돌아 놓쳤다 |
| B — 주석 한 줄 | 통과 · ⑦ 전체 147초 |

선택 자체는 1초 남짓이다(review.py 5건 · paths.py 32건).

## 운영 메모

- 커밋 `04463ef`, push, 배달 3/3 OK. 재기동은 없다(⑦은 `ax-followup.timer`가 매번 새 프로세스로 돈다).
- #815에 노트를 남겼다. 진척률은 자식(#820) 때문에 Redmine이 계산한다. 항목은 6개 중 ③②⑤ 3개가 끝났다.

## 남은 것

- #815: ① 동작 정합(작업 방식 결정) · ④ 층2 `[PSEUDO]` 이행 · ⑥ 공식 목록 확대(`test_client_bundle`의 실 SSH probe 처리부터)
  · mypy 한계 셋 · `logic.py` 재수출 · `test_runner` 간헐.
- 선택 규칙의 알려진 느슨함(서브 에이전트 보고):
  - 최상위 모듈 `master/foo.py`는 경로 기준이 `foo.py` 하나라 다른 디렉터리의 같은 이름도 걸린다.
  - 문자열 동적 import(`importlib.import_module`)는 잡지 않는다.
  - `from pkg import name`은 함수인지 하위 모듈인지 구분하지 않는다.
- 이전 보고서의 남은 것은 그대로다.

### 이후 경과

- 같은 날 #815 ⑥ 공식 통합 목록 34 → 167 — [리포트 120](120-815-official-list-expansion.md). ⑤ 의 선택은 공식 목록에 아직 없는 새 테스트를 받는 안전망이 됐다.
