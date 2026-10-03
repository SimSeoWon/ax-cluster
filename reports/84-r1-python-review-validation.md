# 84. AXCluster R1 지적 검토

2026-10-03 · 사용자 “R1 검토해줘” · 수정 없이 검증했다.
대상 R1은 `7ec14f5d7b8b2ba3f12e8ec3e0e290cf32483140`의 실제 운영 자동 리뷰다.
17:26:34에 큐 done, 첫 시도 완료, 최종 리뷰 저장을 확인했다.
격리 진단의 R1이나 NS의 R번호와 구분한다.

## 판정: 유효 1건 / 전체 지적 1건

`master/context_synth/review_runner.py:140`은 Python 소스를 ast.parse로 파싱하지만
154행의 except는 SyntaxError만 잡는다. 운영 실행 환경 `.venv/bin/python`은 3.10.12다.

- `ast.parse('def f(): pass\n\x00')` → ValueError: source code string cannot contain null bytes.
- 동일 입력을 declarations에 넘겨 ValueError가 그대로 전파되는 것을 확인했다.
- SyntaxError 대조 입력은 기존 진단 문자열로 반환됐다.
- 운영 큐가 아닌 임시 큐에서 실제 claim·declarations 호출을 실행하고 Git 읽기만 주입했다.
  ValueError 전파 뒤 counts={pending:0, running:1, done:0, failed:0, abandoned:0}.
  다음 claim은 None: running 항목을 재시도 대상으로 꺼내지 못한다.

따라서 위험은 선언부 추출 중단뿐 아니라 리뷰 소비자 회차 종료와 해당 항목의 running 잔존이다.
운영 R1 자체의 커밋은 널 바이트 입력이 없어서 성공했으며 지금 큐가 고착됐다는 뜻은 아니다.

권장 수정 범위는 SyntaxError·ValueError를 잡아 파싱 실패 근거로 반환하고 diff 리뷰를
계속하도록 하는 것이다. ValueError에는 msg·lineno가 없으므로 **둘 다 getattr로 처리**해야 한다.
리뷰의 msg 처리 권고만 적용하고 e.lineno를 그대로 남기면 AttributeError가 다시 발생한다.
널 바이트 입력이 최종 큐 종결까지 도달하는 회귀 검증을 추가하는 것이 적절하다.

지적 내용은 현재 운영 환경에서 재현됐으므로 오탐이 아니다. 코드 수정, 리뷰 원문 변경,
R1 상태 변경, 커밋·푸시는 하지 않았다. 이 리포트와 인수인계만 검증 근거로 남긴다.

## 사용자 수정 승인 후 구현·검증

사용자 “수정해줘!” 승인으로 `master/context_synth/review_runner.py`와
`master/test_python_commit_review.py`를 수정했다. SyntaxError·ValueError를 함께 잡고
msg·lineno가 없는 예외도 안전하게 진단 문자열로 반환한다. 파싱 실패 근거와 DIFF를
모델에 전달하여 리뷰를 계속한다.

실제 임시 Git 커밋의 구문 오류·널 바이트 입력 두 가지로 등재→claim→리뷰 생성→done을
검증했다. 모델 호출만 주입했고, 두 입력 모두 최종 파일 저장과 pending/running=0을 확인했다.
Python 커밋 리뷰 7건, runner 30건, review_gen 63건, queue 41건: 총 141건 통과.
`git diff --check`도 통과했다. 운영 리뷰 원문·R1 상태는 변경하지 않았고 커밋·푸시는 하지 않았다.

## 컨텍스트 조회 누락과 재검토

사용자가 컨텍스트 분석·RAG의 목적은 작업 전에 더 풍부한 근거를 제공하는 것이라고 지적했다.
최초 R1 수정은 RAG 조회와 서브 에이전트 없이 수행했다. 수정 성공과 별개로 이 절차를 놓쳤다.
이후 수정 전 관련 RAG 컨텍스트를 조회하고, 위임 시 조회 근거를 함께 전달한다.

보완 검토에서 `list_projects_tool`로 active=AXCluster를 확인하고 `search_context_tool`에
`review_runner declarations Python ast.parse 파싱 실패 SyntaxError ValueError 커밋 자동 리뷰 큐 running done 재시도`,
`review_runner` 두 질의를 전달했다. 둘 다 ok=true, project=AXCluster, logged=true였다.
회수된 review_queue·review_gen·test_review_runner 컨텍스트와 review_runner 본문,
설계 문서17·현재 코드·수정 diff를 대조했다. 큐 상태 전이, 커밋 기준 선언 추출,
로컬 초안→Antigravity, 최종 저장 후 초안 제거 계약을 검토 근거로 사용했다.

조회 한계도 확인했다. BM25 결과 일부는 excerpt가 비었고 review_runner 직접 질의의 상위
결과에도 해당 본문이 없었다. review_runner 컨텍스트는 source_commit=7ec14f5인데 Python
선언 추출 설명이 빠졌으며 `RunnerResult.__repr__` 미구현 주장은 실제 코드와 달랐다.
따라서 컨텍스트 본문을 읽고 현재 소스와 대조했으며, 검색·합성 설정은 변경하지 않았다.
사용자 지적에 따라 로컬 서브 에이전트 `r1_context_review`에 읽기 전용 독립 검토도 맡겼다.
이는 AX 원격 워커 파견과 구분한다.

독립 검토 결과: 에이전트도 active·RAG를 직접 확인하고 계약과 코드를 대조하여
R1 수정에 추가 코드 변경이 필요하지 않다고 판정했다. 양 모델의 진단 전달과 최종 저장·
초안 제거 후 done 흐름을 확인했다. 다만 널 바이트 파일은 Git이 바이너리로 인식할 수 있어
DIFF가 `Binary files differ`일 수 있다. 이번 검증은 큐 고착 방지와 진단 전달을 보장하며
모든 변경 소스라인이 모델에 전달된다는 보장은 아니다. 운영 큐·리뷰 상태는 변경하지 않았다.
