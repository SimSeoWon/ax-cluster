# 185 — #946 자동 리뷰에 커밋 메시지·일감·플랜 컨텍스트 주입

2026-11-14 · Claude · 로컬 서브에이전트 2개(T1·T2 / T3·T4). 메인이 diff·실행·실물 대조로 검증.

## 사용자 결정과 범위

「946번 진행해줘」 뒤 플랜 질문에 세 가지를 골랐다.
- 커밋 양식은 `종류(#N T#): 제목`이다(태스크 여럿 `T1,T2`, 일감 여럿 `#861 T2, #857 T7`). 옛 꼴 `(#N)` 꼬리는 일감만 풀린다.
- 강제는 「규약 기록 + 리뷰 로그만」이다. 게이트·경고로 막지 않는다.
- 작업은 로컬 서브에이전트가 한다.

진행 중에 결정이 셋 더 나왔다.
- 🔴 **일감 번호·태스크 정보가 없어도 리뷰는 종전대로 동작해야 한다.** 일감·플랜은 있으면 쓰는 보조다.
- `test_issue_progress.py`의 main() 검사에 Redmine 대역을 넣는다. 이 파일은 대상 밖이었지만 승인을 받았다.
- T#가 없으면 태스크 규칙 두 줄을 빼고 일반 대조 한 줄만 남긴다.

RAG request_id `56de18b6bdda493d8f50555193b19641`. 대조한 결과는 다음과 같았다.
- 커밋 리뷰 프롬프트에는 메시지가 아예 없었다.
- 범위 리뷰에는 `range_history`(커밋 로그)만 있었다.
- 해시→일감은 `issue_track`으로 이미 결정적으로 풀린다. T#는 어디에도 없었다.
- 최근 40커밋 중 `(#N T#)` 꼴은 0건이었다. 모두 `feat: … (#N)` 꼬리 꼴이라 `plan_metrics.WORK_SCOPE_RE`의 작업 커밋 판정에도 잡히지 않았다.

## 커밋

- `e100c12` T1·T2
  - `master/commit_scope.py`: 순수 파서 `parse`·`parse_message`. `SCOPE_RE`를 `plan_metrics.WORK_SCOPE_RE`와 같은 객체로 둔다.
  - `master/context_synth/issue_context.py`: `collect`는 issue_track을 먼저 보고 메시지를 보조로 쓴다. 예외를 올리지 않고 결과마다 로그 한 줄을 남긴다. 렌더러는 셋이다(`commit_section`·`draft_section`·`range_section`).
  - `docs/orchestrator-rules.md` §1.9에 규약을 적었다.
- `32e45f5` T3·T4
  - `build_prompt(issue_context, message, issue_tasks)`: 셋이 모두 비면 바이트 단위로 같다(골든 해시 불변).
  - `review_runner.commit_context`·`range_context`: 수집기 예외를 이중으로 감싼다.
  - 초고에는 짧은 태스크 절만 싣는다.
  - 수집은 `main()`만 켠다(`context_collect` 기본 None). 단위 검사가 실 Redmine에 닿지 않게 하려는 것이다.

## 갈래별 동작 (실물 드라이런, LLM 0)

| 입력 | 결과 |
|---|---|
| `902f4e9` 옛 꼴 `(#368)`, 추적 기록 있음 | `ok (track)` · 일감 절 + 일반 규칙 한 줄 · 태스크 규칙 없음 · 초고 절 없음 |
| `e100c12` `feat(#946 T1,T2)` | `ok (message)` · 태스크 2건 · 태스크 규칙 두 줄 · 초고에 T1·T2 행 |
| `fc700c2` 인수인계 문서 커밋 | `no_issue` · 커밋 메시지 절만 · 규칙 없음 |
| 범위 #946 `fc700c2..HEAD` | `ok (given)` · 스펙 + 플랜 + 커밋별 태스크(`e100c12 [T1,T2]` · `32e45f5 [T3,T4]`) |

Redmine 실패와 수집기 예외는 단위 검사로 확인했다. 그 경우 프롬프트에는 메시지 절만 실리고, 범위 리뷰 프롬프트는 수집기 없는 기준과 같다.

## 검사

- `test_commit_scope` 17 OK · `test_issue_context` 20 OK · `test_plan_metrics` 75/75
- `test_review_gen` 132/132 · `test_review_runner` 169/169 · `test_review_range` 90/90 · `test_review` 223/223 · `test_review_queue` 65/65
- `test_scope_plan` 100/100 · `test_python_commit_review` OK · `test_issue_progress` 124/124(대역, `AX_REDMINE_URL` 해제 상태)
- pyflakes: 새 경고 0(기존 4건은 HEAD에도 있다)
- 공식 통합 `Ran 199 tests in 188.862s / OK` rc0 (신규 2파일 등록 포함)
- `master/test_*.py` 전수 225파일 — rc≠0 은 `test_sandbox.py` 1개. 원인은 `AX_PROJECTS_ROOT` 미설정이다(폴백 없음).
  운영 main 에서도 같은 조건이면 rc1 이고, `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 주면 38/38 통과한다 — 이번 변경과 무관하다.

## 안 잰 것

- 운영 리뷰 큐가 실제 커밋을 이 컨텍스트로 리뷰한 결과(상용 호출). 첫 회차는 이 일감 마감 뒤 해시별 리뷰다. 확인할 곳은 리뷰 큐 로그의 `[리뷰큐] <sha8> 리뷰 컨텍스트 …` 줄이다.
- 오탐·미탐이 실제로 줄었는지. 같은 커밋을 컨텍스트 유무로 A/B 하지 않았다.
- `.33` 요청자 게임 프로젝트 트윈에서의 동작. 일감 번호가 다른 Redmine 프로젝트여도 `get_issue`는 번호로 읽지만, 실물로 확인하지는 않았다.

최종 결과는 Redmine #946 마감 노트에 있다.
