# 93 — 고아 이벤트 배치 복구와 누락 frontmatter 구분선 복구

2026-10-04 · #714 · #666 · 로컬 서브 에이전트 2명 구현, 별도 1명 읽기 리뷰

사용자 「수정 완료는 일감 닫고 나머지 2개 수정하자」 및 「로컬 서브 에이전트에게 요청해」.
현재 세션에 AX RAG 도구가 없어 확인한 일감 본문과 실제 소스를 대조했다.
시작 HEAD=origin/main `15f620f`, clean. 드라이런 후 사용자 「커밋하고 푸시해」로
수정·검사·기록 6파일의 커밋·Gitea push 승인. 운영 배포는 미실행이다.

## #715 종결

`c657a7a`의 병렬 합성·inflight 분배가 현재 소스에 있음을 확인했다.
브로커 라우팅 14/14·병렬 합성 14/14 재실행 통과, 이전 실물 기록의
bc250 20건·rtx3060 14건 분배를 대조했다. 사용자 지시로 완료 100% 처리하고 재조회했다.

## #714

`master/events/consumer.py`에서 기존 `Spool.iter_all_pending()`을 소비 경로에 연결했다.
고아 배치를 먼저 처리하고 신규 이벤트를 claim한다. 결과 error·예외가 생기면 배치를
남기고, 모든 종료 경로에서 소비자 락을 해제한다. 기존 halted·synth_lost 판정은 유지한다.
게이트 defer·파견 트리거·미등록 reject 증거·비마운트 skip 정책을 보존하고
배치별 통계를 누적한다. 고아 처리 뒤 빈 신규 배치로 상태 폴링을 중복하지 않는다.

`master/test_events.py`에 회귀 19건 추가. 실제 운영 스풀은 변경하지 않았다.

## #666

`master/context_synth/md.py`에서 펜스를 제거한 뒤, frontmatter 필드를 잘라내기 전에
누락된 여는 구분선과 양쪽 구분선을 복구한다. 알려진 메타데이터 필드, tags/category,
명확한 본문 제목이 있는 경우만 허용한다. 손상·중복 필드·설명·불명확한 경계는 거부한다.
자연어 도입부와 여는 구분선 누락이 함께 있는 응답은 이번 복구 범위 밖이다.

`master/test_context_synth.py`에 회귀 18건 추가. 필드·본문·해시·source_commit·개발자
코멘트 보존을 검증했다. 기존 suite의 related 조회 환경변수·브로커 조회 경고는 있었으며
주입 LLM 기반 검사다. 실제 모델 합성 성공이나 운영 배포로 보고하지 않는다.

## 검증

- `.venv/bin/python -B master/test_events.py`: 57/57 (담당 실행)
- `.venv/bin/python -B master/test_indexer.py`: 103/103 (담당 실행, 통합 검사에서도 통과)
- `.venv/bin/python -B master/test_gate.py`: 17/17 (담당 실행)
- `.venv/bin/python master/test_context_synth.py`: 135/135 (담당 실행)
- `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`:
  지휘자 실행, 정본 19/19 통과
- 독립 읽기 리뷰: 심각한 결함 없음. `git diff --check` 통과.

구현 에이전트는 서로 다른 파일을 맡았고 종료했다. 지휘자가 실제 diff와 검사 결과를 대조했다.
구현·검증 시점에는 미커밋이었다. 후속 커밋·push 승인을 받았으며 게시 결과는 Git으로
대조한다. 배포·운영 고아 배치 소비·실물 합성은 미실행이다. #714·#666은 종결하지 않는다.

## 사용자 요청 드라이런

지휘자가 기존 events·gate·indexer·context_synth 검사 명령을 `-B`로 실행해
57+17+103+135 = **312/312**, 종료 코드 모두 0을 확인했다. indexer 출력은 첫 호출에서
잘려 같은 명령을 충분한 출력 한도로 재실행해 전문을 확인했다.
context_synth의 related 검색 환경변수 미설정·브로커 상태 조회 경고는 기존 검사에서
발생했고 실제 LLM 생성·모델 회수 함수는 주입 응답으로 실행했다. 운영 합성 실증은 아니다.

검사 전후 운영 claimed 이벤트 파일 3개의 목록·SHA256, conductor.json/mode.json SHA256,
ax-projects/ax-broker MainPID·기동 monotonic 시각 및 Git diff SHA256이 동일했다.
이 기록 추가만 검사 후 문서 변경이다. 운영 고아 배치를 실제로 소비하거나 서비스를 재시작하지 않았다.
