# 144 — #910 일감 worktree의 검사 경로 분리

일감: http://192.168.0.57:8080/issues/910 · 2026-11-08 · Codex

## 사용자 지시와 승인 범위

- 사용자 원문: `910 진행해` → `로컬 서브 에이전트로 진행해줘.`
- RAG·현재 소스 대조 후 제시한 두 검사 수정 및 실제 일감 worktree 검증 플랜을 로컬 서브 에이전트 방식으로 진행한다.
- 커밋·push·main 반영·마감·서비스 재기동 승인은 받지 않았다. 운영 데이터는 읽기만 한다.
- RAG request_id: `4701b82f939541a383046fea17d2dfa2`.

## 시작 실증과 작업 위치

`issue_start_tool(910)` 응답 발췌:

```json
{"ok":true,"issue_id":910,"branch":"issue/910","repo":"/home/sim/ax-cluster/.ax-issues/910","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"5bc4c8bd226d6884e410aa11cda8d23b2fd424af","lock":"acquired"}
```

작업 위치는 응답 `repo`다. `git rev-parse --show-toplevel --git-common-dir` rc0:

```text
/home/sim/ax-cluster/.ax-issues/910
/home/sim/ax-cluster/.git
```

운영 체크아웃 `git status --short --branch` rc0: `## main...origin/main`(미커밋 변경 없음).
별도 커밋은 아직 없다. finish는 실행하지 않았으므로 `done`·`why` 응답도 없다.

## 원인별 근거와 변경

1. **참 — 온톨로지 실물 검사 경로 가정.** `master/test_ontology.py` §6의 두 glob이
   `Path(__file__)` 기반 `_ROOT/ModularStage/ontology/domains`를 읽었다. 미추적 데이터가 없는
   일감 worktree에서는 manifest를 찾을 수 없다. import용 `_ROOT`는 유지하고 실물 데이터만
   기존 `master.projects.config.projects_root()`(`AX_PROJECTS_ROOT`, 폴백 없음)에서 읽는다.
   데이터 루트 미설정·snapshot 부재는 `[건너뜀]` 사유를 출력하고 통과 수에 가산하지 않는다.
   잘못 설정한 루트의 ConfigError는 숨기지 않는다. 실물 내용 단언은 유지했다.
2. **참 — 서비스 권한 기대 경로 가정.** `master/test_sandbox.py`는 같은 ROOT로 유닛 사본·트윈·권한을
   모두 검사했다. 유닛 `ReadOnlyPaths`는 운영 경로인데 worktree 절대 경로와 비교해 실패했다.
   사본은 `SOURCE_ROOT`(현재 worktree), 트윈·권한은 기존 `projects_root()`로 분리했다.
   운영 루트와 유닛의 `WorkingDirectory`·`Environment=AX_PROJECTS_ROOT` 일치도 확인한다.
   운영 트리와 소스 worktree의 최상위 항목 모두를 운영 배포 경로에 대조해 새 항목 보호 누락도 검출한다.

유닛·운영 설정·미러·운영 트윈 파일은 변경하지 않았다. 구현 파일별 로컬 에이전트 2개와
읽기 전용 독립 검토 에이전트 1개를 사용했고, 최종 diff에서 차단 결함이 없다는 검토를 받았다.

## 검사 명령과 관측

모든 명령의 cwd는 `/home/sim/ax-cluster/.ax-issues/910`이다. 실행 해석기는
`/home/sim/ax-cluster/.venv/bin/python`이며 `-B`로 코드 worktree의 bytecode 생성을 막았다.

```bash
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_ontology.py
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_sandbox.py
```

- ontology rc0: `통과 144 · 실패 0`. 실물 manifest 7개와 object 40개 검사를 실제 실행했고 건너뜀 없음.
- sandbox rc0: `OK test_sandbox: 44/44 통과`. 운영 데이터·권한·유닛 사본/실물 일치 검사 포함.
- `master.work.pystatic.run_static('.', '5bc4c8bd226d6884e410aa11cda8d23b2fd424af',
  ['master/test_ontology.py', 'master/test_sandbox.py'], python=sys.executable, flakes_python=sys.executable)` rc0.
  pyflakes 차단0·노트1, mypy 차단0·노트56, setup_error 없음. import는 기존 정책상 test 파일을 제외해
  checked0이며 import 실행 성공 근거로 세지 않는다. 두 스크립트의 실제 실행 성공은 위에 따로 있다.
- `git diff --check` rc0.

### 공식 통합 검사와 샌드박스 제약

```bash
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

기본 샌드박스 rc1: `Ran 3 tests in 1.115s`, `FAILED (failures=1)`.
`test_source_scope`가 28/32였고 실패 원문 중:

```text
FAIL [중요] 펼치면 서브모듈 안 변경 파일이 된다 — [] vendor/eng: 04c4e553 에 서브모듈 포인터가 없다(삭제?)
FAIL   사유 없음 — vendor/eng: 04c4e553 에 서브모듈 포인터가 없다(삭제?)
FAIL [중요] 제외(ggml) 변경은 경계에서 떨어진다 — []
FAIL 첫 커밋(빈 트리 기준)은 서브모듈 전체를 펼친다 — ['webui/server.py'] vendor/eng: b0b7e649 에 서브모듈 포인터가 없다(삭제?)
FAIL test_source_scope: 28/32 통과
```

리포트86 및 사용자 「Git 검증」 지침에 해당한다. 소스·권한 설정을 고치지 않고,
동일한 공식 명령만 담은 `/tmp/ax-910-integration.sh`를 작성해 샌드박스 해제 승인을 받은 후
`sh /tmp/ax-910-integration.sh`로 재실행했다. 실제 #910 worktree에서의 검사이며
임시 Git 조건을 운영 성공 근거로 삼지 않는다.

재실행 rc0: `Ran 188 tests in 177.838s` · `OK`.
`[AXCluster] master/test_source_scope.py: 검사 32건 통과 (32 checks)`도 확인했다.
두 수정 검사는 공식 목록에 없으므로 위 실제 데이터 루트 명령으로 별도 실행한 결과와 구분한다.

## 멈춘 지점과 미확인

T1은 실제 두 검사 결과, T2는 공식 통합188/188과 기록을 근거로 완료 마킹했다.
T2 응답: `next.verdict=plan_done`, `next.ok=false`,
`next_action=모든 태스크가 끝났다 — 일감 완료는 스펙·완료 조건과 승인 규칙으로 따로 판단한다`.
`redmine_get_issue(910)` 되읽기에서 상태 `진행`·done_ratio0·T1/T2 완료와 검사 근거를 확인했다.
문서 갱신 후 `master/test_handoff_size.py` rc0: `OK test_handoff_size: 7/7 통과`.
커밋·push·마감·배달·서비스 재기동은 미실행이며 별도 승인 대상이다.

세션 파일: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T11-53-17-01a1b913-1317-7e20-8e9f-c8d3778cea29.jsonl`.
