# 205 — #975 인수인계서 누적 가드: 수정안과 오탐 관측

2026-11-17 · Codex · 단독(로컬 서브 에이전트).

## 사용자 지시와 범위

- 「975번 진행하자」, 「버그에 가까운거 같아! 인수인계서 길이 체크에서 오동작 하는거잖아」.
- 누적 판정·정상 참조 허용·실제 과거 판 재현·파급 측정과 스펙을 단계별 확인했다.
- 「응! 추가로 500줄로 확장하는건 어떨까해!」 → 상한 150→500 및 정상500줄/501줄 실패 경계값 검사를 포함하는 질문에 「응!」.
- 「단독으로 진행해줘」, 「응 버그 수정이라 많은 태스크는 없어」 → T1 하나로 합친 제안에 「응 수정하고 진행해」.
- 편집 대상: master/test_handoff_size.py, 이 리포트, docs/orchestrator-handoff.md(후속 승인으로 검사 전 정리 포함).

## 실제 시작 상태

issue_start_tool(975) 응답 주요 필드 원문:

```json
{"ok":true,"issue_id":975,"branch":"issue/975","repo":"/home/sim/ax-cluster/.ax-issues/975","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"dfd00cb41c8e4ff98fc932d395ebdd4c6a81f44c","lock":"acquired"}
```

plan_transition_tool(T1, 작업중) 응답: from=대기, to=작업중, next.verdict=resume, next.ok=true.
git rev-parse --show-toplevel --git-common-dir HEAD(rc0): 위 worktree, /home/sim/ax-cluster/.git, 위 start_rev.
운영 저장소 시작 시 git status --short --branch(rc0): `## main...origin/main`.
마스터 마지막 담당 기록 claude, 워커 codex(source=state); 조회만 했고 변경하지 않았다.

## 근거와 수정안

RAG request_id=d389976a7f4d4fab90e762b5cbd83d7d, search_id=da14e89daea34abfbf62a9b391f3f7f5.
AXCluster/context/master/test_handoff_size.md 전문과 실제 소스를 대조했다.
기존 problems는 상한150, 이전 체크포인트 문구, 바로 다음 작업 절만 검사한다.
리포트199와 #842 본문·마감 노트에서 현재 체크포인트 한 벌 유지 의도를 확인했다.

로컬 에이전트 handoff_guard는 master/test_handoff_size.py만 편집했다.
MAX_LINES=500, 완료 절 반복·이력 절 표/목록·명시 완료 행 누적 검출, 양성6·음성8·경계값5 검사를 추가했다.
에이전트는 테스트·커밋하지 않았으며 부모가 실제 파일 diff와 과거 문서를 직접 대조했다.

## 실제 과거 문서 대조 — 오탐 발견으로 중단

cwd=/home/sim/ax-cluster/.ax-issues/975, 해석기=/home/sim/ax-cluster/.venv/bin/python -B.
subprocess.run(["git", "show", rev+":docs/orchestrator-handoff.md"], check=True, capture_output=True, text=True)
출력을 master.test_handoff_size.problems에 넣었다. 명령 rc0이며 결과는 다음과 같다.

| 판 | 줄 수 | 수정 전 | 수정안 |
|---|---:|---|---|
| 0504027 | 170 | 상한 초과만 | 누적 검출(마감 절11건 포함) |
| 9ae5e0b | 85 | problems=[] | 표·목록 누적15건 |
| 3d87401 | 57 | problems=[] | 표·목록 누적2건 — 정상 기준에 대한 오탐 |

오탐 원인 확인 조회(rc0)에서 다음 두 줄이 일반 완료 행 판정에 걸렸다:

```text
29:- #964·#966 배포 후 관측(C6): `ax-batch` 회차 `complete:true` · 완료 주차 재생성 없음 · 새 생성 호출이 `[agy]` 먼저.
38:- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842, 상한 150줄, 끝난 일감 표 금지).
```

29행은 남은 운영 관측이고 38행은 규칙 설명이다. 일감의 완료 상태가 아닌 문장 내 완료/마감 단어까지 넓게
해석했다. `git diff --check` rc0이나 완료 조건의 정상 판 통과는 충족하지 못했다.
코드 수정·추가 검사·커밋·마감을 중단해 사용자에게 보고했다.

## 재개 승인과 인계서 정리

현재 인계의 「이번 세션 마감 상태」도 완료 결과 나열로 검출될 예정이다.
전체 검사 전에 worktree 인계서를 현재 작업·남은 관측 중심으로 덮어쓰고 마감 뒤 재갱신하는 범위 질문을
비동기로 보냈다. 최종 질문 「오탐을 보완하고, 현재 인계서의 완료 이력 나열도 정리해 검사를 이어갈까요?」에
사용자가 「응!」으로 승인했다. 로컬 에이전트에 오탐 보완을 재위임했고 부모는 worktree 인계서에서
「이번 세션 마감 상태」의 완료 일감 나열을 제거하고 현재 작업·승인·검사 전 상태와 남은 관측을 남겼다.
기존 운영 계약·미해결 선택지는 유지했으며, 이번 MCP의 issue_id 인자 노출도 실제 도구 정의와 맞췄다.

## 재개 뒤 검증과 조회 실패로 중단

일반 설명문을 제외하도록 완료 상태를 일감 바로 뒤/독립 표 셀로 좁혔고, 이력 제목은 첫 연속 표·목록 블록에
적용한다. 이력 표 뒤 별도 문단의 잔여 관측은 이력 행으로 세지 않는다. 실제 정상 판 설명문 반례를 추가했다.

- 실제 과거 판 대조(rc0): 0504027 → 표·목록2건 및 마감절11건 누적; 9ae5e0b → 표·목록14건 누적;
  3d87401 → problems=[](정상 통과). 여기서 건수는 서로 다른 일감 번호 수다.
- `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_handoff_size.py`
  rc0: `OK test_handoff_size: 28/28 통과`. 양성6·음성10·경계값5와 기존7개다.
- `sh /tmp/ax-975-checks.sh static` rc0: 기존 master.work.pystatic.run_static 호출.
  pyflakes 파일1 차단0·노트0, mypy 파일1 차단0·노트0, setup_error 없음.
  import는 기존 정책상 test 파일 제외(checked0)이며 실제 실행 성공은 위 스크립트 검사로 확인했다.
- `sh /tmp/ax-975-checks.sh integration`은 사용자 샌드박스 해제 승인 뒤 실행했다.
  실제 #975 worktree에서 공식 명령 실행 rc0: `Ran 216 tests in 27.164s`, `OK`.
  원문 로그=/tmp/ax-975-integration.log. `git diff --check` rc0.

통합 검사 실행 중 루트가 `rg --files -g 'ax-975*' /tmp`로 로그 경로를 조회했다가 rc2가 났다.
보호된 시스템 디렉터리까지 검색한 불필요한 조회였다. stderr 원문 예:
`rg: /tmp/systemd-private-dfd7a9c043bf45df97e476967e6e3361-ModemManager.service-EgDOC3: Permission denied (os error 13)`.
로그·스크립트 경로 두 개도 나왔지만 실패를 성공으로 판단하지 않았다. 코드·검사 실패가 아닌 조회 범위 실수다.
사용자 규칙상 경로 부재 이외 조회 실패라 추가 작업을 멈췄고 이미 실행 중이던 통합 검사 결과만 회수했다.

## 재개 뒤 최종 검사와 커밋

「남은 전수 검사부터 마감·배달까지 재개할까요?」에 사용자는 「응!」으로 답했다.
이 재개 승인 뒤 코드 변경 없이 남은 전수만 실행했다.

`sh /tmp/ax-975-checks.sh sweep`(같은 사용자 승인 스크립트, 샌드박스 해제) rc0:

```text
SWEEP 242파일 · 12305/12305 통과(형식 A·B) · unittest 593/593 · 실패 파일 0개 · 32.0초
```

로그=/tmp/ax-975-sweep.log. 기존 test_nowork.py·test_rounds.py는 수치 못 읽음으로 이름이 표시되지만
두 파일 rc0이며 실패0 집계에 포함됐다. 테스트 임시 정리는 실행기가 자기 임시 경로에서 수행했다.

코드 커밋: `7647294be7064b55b6d2c9a04fce1dc060f58321`
(`fix(#975 T1): 인수인계서 누적 검출과 500줄 상한 보강`). 검사 뒤 코드 변경 없음.
리포트·현재 작업 인계 정리도 별도 일감 커밋에 담는다.
누적 검출은 명시적인 구조·상태 표지를 대상으로 하며 자유 산문의 의미 전체를 판단하지 않는다.
같은 일감 하나의 체크포인트는 허용하고 서로 다른 일감2개 이상을 누적으로 검출한다.
기존 인계의 완료 결과 나열은 실제로 검출돼 승인 범위에서 제거했다.

이 리포트 작성 시점에는 issue_finish·재기동·배달 미실행이며 issue_finish의 done·why 응답도 없다.
마감 뒤 결과의 정본은 Redmine이며, 인계서는 마감 뒤 문서 커밋·push 뒤 배달하는 기존 순서를 따른다.

세션 파일: ~/.codex/sessions/2026/11/17/rollout-2026-11-17T23-13-01-01a1e9da-9fd4-7722-9dc7-29dfe9cc8002.jsonl.
서브 세션: ~/.codex/sessions/2026/11/17/rollout-2026-11-17T23-25-34-01a1e9e6-1e43-7d60-a317-e49f63f2ec99.jsonl.

최종 결과는 Redmine 마감 노트.
