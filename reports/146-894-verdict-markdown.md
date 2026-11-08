# 146 — #894 종합 리뷰 판정 칸의 마크다운 처리

2026-11-08 · Codex · 일감 http://192.168.0.57:8080/issues/894

## 사용자 지시와 범위

- 사용자 원문: `894번 진행해` → `단독으로 진행해줘`.
- 플랜: T1 판정 파서 수정, T2 기존 회귀 검사 확장·공식 검사·결과 기록. 로컬 서브 에이전트 `fix_894`가 구현하고 마스터가 diff와 실제 실행을 검증했다.
- 경로 조회 실패 보고 뒤 사용자 `응`: 같은 worktree에서 구현 재개 승인이다. 커밋·push·main 반영·배달·재기동 승인으로 확대하지 않았다.
- RAG request_id=`c4097e972df74b1c84ece5f282faff8c`. 운영 트윈의 `master/context_synth/review_gen.md`와 `master/test_review_gen.md` 전문을 현재 소스와 대조했다.

## 시작 응답과 실제 작업 위치

`issue_start_tool(894)` 응답 주요 필드 원문:

```json
{"ok":true,"issue_id":894,"branch":"issue/894","repo":"/home/sim/ax-cluster/.ax-issues/894","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"9dc20292937ce6976b9f5b4fe57689504cb1b688","redmine":"레드마인 #894 갱신 (notes, status_id)","lock":"acquired"}
```

편집·검사는 응답 `repo`에서 수행했다. 재개 전 `git status --short --branch` rc0: `## issue/894`.
운영 저장소 시작 조회 rc0: `## main...origin/main`, 미커밋 변경 없음.
새 커밋은 아직 없다. finish 미호출이므로 `done`·`why` 응답은 없다.

## 근거와 변경

1. **참 — 꾸민 판정 파싱 실패.** `parse_verdicts`가 판정 칸 원문의 `startswith`만 검사했다. 백틱·별표·밑줄이 앞에 붙으면 남음/해소와 일치하지 않는다. 비교용 문자열의 선행 꾸밈과 공백만 제거하고, 알려진 판정이 아니면 원문을 보존한다.
2. **참 — 소비자 집계 영향.** 현재 `review_runner.track_note_text`는 파서가 돌려준 판정이 집계 키와 다르면 `판정 없음`으로 센다. 실제 함수 호출 회귀에서 꾸민 두 판정이 `남음 1 · 해소 1 · 판정 없음 0`으로 집계됨을 확인했다.
3. **현재에는 해당 없음 — 본문의 완료 게이트 영향 주장.** 인수인계와 현행 ax-plan은 #889 이후 main 적용 시 마감하며 리뷰가 완료 관문이 아니라고 명시한다. 과거 게이트 설명을 현재 운영 결함으로 확대하지 않았다. 완료 정책·리뷰 재생성은 수정 범위에 넣지 않았다.

변경은 `master/context_synth/review_gen.py`의 최소 파서 수정과 `master/test_review_range.py`의 회귀 19건 추가다. 기존 판정 접두 설명·번호 정규화·첫 중복 행 우선·다음 절 경계·미지 판정 원문·빈 판정 처리를 유지한다. 프롬프트는 바꾸지 않았다.

## 실패와 재개

에이전트가 worktree에 있는지 확인하지 않은 디렉터리를 검색 대상으로 넣었다:

```text
rg --files -g 'review_gen.md' AXCluster/context
rc=2
rg: AXCluster/context: IO error for operation on AXCluster/context: No such file or directory (os error 2)
```

이때 편집·검증 전 중단하고 사용자에게 보고했다. RAG 문서는 운영 트윈에만 있으며 worktree의 코드 경로가 아니다. 사용자 `응` 뒤 부모가 이미 읽은 근거를 전달하고 재개했다. 조회 실패를 인프라 기능 부재로 해석하거나 임시 대체 호출을 만들지 않았다.

## 검사 증거

cwd=`/home/sim/ax-cluster/.ax-issues/894`, Python=`/home/sim/ax-cluster/.venv/bin/python`, `AX_PROJECTS_ROOT=/home/sim/ax-cluster`, `-B`.

- 에이전트 `parse_verdicts` 직접 호출 rc0, 13/13 통과. 마스터 별도 실제 호출 rc0, 6/6 통과(백틱·굵게·밑줄·혼합·기존 접두·미지 원문).
- `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_review_range.py`: 에이전트·마스터 각각 rc0, `OK test_review_range: 75/75 통과`. 기존 fixture의 임시 Git 조건은 회귀 검사이며 운영 Git 실증이 아니다. 실제 노트 집계 검사는 회차 조회만 대역이고 LLM·Redmine·Git을 호출하지 않는다.
- 기존 `master.work.pystatic.run_static`에 기준 리비전 `9dc20292937ce6976b9f5b4fe57689504cb1b688` 및 변경 파서 파일을 전달: rc0. pyflakes 차단0·비차단 unused import 노트2, import checked1·환경0·차단0, mypy 차단0·비차단 operator 노트1. setup_error 모두 빈 문자열.
- 변경 검사 파일의 `pyflakes_check`: rc0, 차단0·노트0. 테스트 파일은 import 검사 제외 정책 대상이며 별도 실제 실행 결과는 위에 있다.
- `git diff --check`: rc0, 출력 없음.
- 공식 통합 검사는 아래 기존 명령만 담은 `/tmp/ax-894-integration-check.sh`를 샌드박스 해제 승인 후 실행했다. 기본 샌드박스의 `sg gitea` 차단은 리포트86·사용자 Git 검증 지침에 근거한다.

```sh
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

공식 검사 rc0: `Ran 188 tests in 186.590s` · `OK`. 실패·skip 없음. source_scope 32/32, review_gen 109/109, review_runner 109/109 포함. 명시 목록에 없는 `test_review_range.py`는 위 별도 검사로 검증했다. 전수 `master/test_*.py`를 실행한 결과로 확대하지 않는다.

## 현재 멈춘 지점

T1은 실제 함수 호출 결과를 근거로 완료 전이했고 커밋 전임을 근거 칸에 명시했다. T2도 회귀75/75·공식188/188·정적 검사와 이 기록을 근거로 완료 전이했다. 응답 원문: `next={"verdict":"plan_done","ok":false,"tasks":[],"detail":[],"next_action":"모든 태스크가 끝났다 — 일감 완료는 스펙·완료 조건과 승인 규칙으로 따로 판단한다"}`. `redmine_get_issue(894)` 되읽기에서 T1/T2 완료·검사 근거·일감 상태 진행·done_ratio0을 확인했다. 플랜 태스크 완료와 일감 마감·운영 반영을 구분한다.
커밋·push·finish·배달·재기동은 하지 않았다. 제안 커밋 메시지: `fix: #894 종합 리뷰의 마크다운 판정 인식`.
인수인계·관련 리포트86·136·137·143~145를 읽었으나 reports 전체 전문 복원을 완료했다고 주장하지 않는다.

세션 파일: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T15-01-38-01a1b9bf-846b-7191-85f4-2227f69aeeb7.jsonl`.
서브 에이전트 세션: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T15-04-50-01a1b9c2-72ce-7063-b61b-c090669d5095.jsonl`.
