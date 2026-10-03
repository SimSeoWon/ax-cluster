# 83. Python 커밋 자동 리뷰 — 구현·검증 (초기 실패 기록 포함)

2026-10-03 · 사용자 지시: “응 일단 커밋시 자동 리뷰 기능 시작하자.”
커밋 리뷰 기능을 수정하는 승인으로 처리했고 저장소 커밋·푸시는 실행하지 않았다.

## 원전과 구현 범위

원전 `~/AgentTest/watcher/context.py` 295–373의 변경 diff 한정 리뷰·두 표 계약,
`watcher/common_utils.py`의 trivial 판정을 확인했다. 원전은 UE 전제다.
기존 AX의 큐·재시도·로컬 초안→Antigravity 최종 검증을 재사용한다.

- `master/events/consumer.py`: 비UE 전체 제외를 index_only 제외로 좁혔다.
  code 프로젝트는 공유 소스 선택기를 거쳐 커밋당 큐에 등재한다.
- `master/context_synth/review_gen.py`: 프로젝트 scope·work_exts로 Python 리뷰 범위를 정하고,
  등재·소비·직접 리뷰가 같은 선택기를 사용한다. Python 프롬프트와 예시를 분리했다.
  기존 빈 표 계약과 모순됐던 “(없음) 행을 쓰라”는 문구를 헤더만 쓰도록 정정했다.
- `master/context_synth/review_runner.py`: Python 커밋의 Git 객체에서 AST 함수·클래스 선언을
  읽는다. 현재 작업 트리와 섞지 않는다. 파싱 실패도 diff 검토 근거로 명시한다.
- `master/projects/profile.py`: 자동 리뷰 제외 조건에 관한 낡은 주석을 정정했다.
- `master/test_python_commit_review.py`: 임시 Git 저장소와 실제 큐를 이용한 검증 5건.
  모델 호출만 주입하며 운영 큐·게임 트리·origin은 수정하지 않는다.

## 검증 결과와 중단

`.venv/bin/python master/test_python_commit_review.py` — **5건 중 4건 통과·1건 실패**.
`git diff --check` 통과. 기존 리뷰 회귀·실제 모델 호출·운영 반영은 아직 수행하지 않았다.

실패는 `test_commit_is_queued_once_and_reviewed_with_python_prompts`의
`assertNotIn("Blueprint", prompt)`다. Python 프롬프트가
“프로젝트 규약을 지어내거나 UE·Blueprint 규칙을 적용하지 않는다”라는 **금지문**을 포함해 실패했다.
실패 지점 앞에서는 중복 없는 큐 등재, source 밖 제외, 두 모델 단계 호출,
done 상태와 리뷰 저장을 확인했다. 실패 이후의 표 파싱·초안 삭제 assertions는 실행되지 않았다.
나머지 4건은 commit 선언부 사용·index_only 제외·경계 밖 제외·구문 오류 diff 유지 검증이다.

공용 규칙의 “명령·게이트·빌드 실패 시 코드·설정을 고치지 않고 보고·멈춤”에 따라
실패 후 테스트나 구현을 수정하지 않았다. 운영 서비스 재시작·커밋·푸시도 하지 않았다.

재개 방안: 금지문은 유지하고 검사 대상을 UE 전용 역할·영향 분석·예시의 유입 여부로
좁혀 오탐을 없앤 뒤, Python 신규 테스트와 기존 리뷰 큐/생성/등재/소비 회귀를 실행한다.
통과 후 기존 실제 Python 커밋 한 건으로 실제 모델 호출을 별도 격리 기록에서 검증한다.
이 결과를 승인 전 운영 리뷰 큐 완료로 해석하지 않는다.


## 승인 후 재개·최종 검증 (17:00 KST)

사용자가 “언리얼 프로젝트인지 확인하면 되는 거 아니야?”라고 방향을 정정하고 “응 진행해”로
재개를 승인했다. 프롬프트·예시·로컬 초안의 선택까지 **등록된 프로젝트 kind**로 통일했다.
파일 확장자는 code의 작업 범위와 파서 선택에만 쓰며 프로젝트 타입 추론에는 쓰지 않는다.
Blueprint 단어 전체 부재 검사 대신 UE 역할·예시·영향 분석이 code에 유입되지 않는지 검사하고,
동일 .py 파일이어도 unreal/code 등록 값에 따라 두 모델의 역할이 달라지는 검증을 추가했다.

- 신규 Python 커밋 테스트: 6/6.
- review_enqueue 17/17, review_gen 63/63, review_runner 30/30, review_queue 41/41,
  review_collect 20/20, indexer 97/97. 합계 기존268 + 신규6 = **274/274**.
- git diff --check 통과.

실제 커밋 `6a18918c4088f77f0eaa958011d14e24aa102d40`의 전체 변경 파일
`master/work/session_usage.py`를 사용했다. 모델을 주입하지 않고 기존 브로커 e4b 초안
(11.509초, 222자)→실제 Antigravity 퇴고→최종 정형 리뷰·격리 R1을 생성했다.
큐 pending1→running→done1, 로컬 초안 실패 사유 없음, 최종 format_ok=true,
parseable_rows=5, 초안 잔존0. 지적 내용의 정확도를 전수 판정한 실증은 아니다.

아티팩트: `/tmp/ax-python-review-live-1392e70e33da4f61a3a92afefb042484/evidence.json`,
최종 리뷰 `reviews/SimSeoWon/2026-10-03_1700_6a18918c.md`(같은 격리 디렉토리).
입력은 마운트된 AXCluster의 실제 미러, 출력·큐·R번호는 별도 진단 디렉토리다.
운영 AXCluster 큐·R번호와 게임 프로젝트 상태는 수정하지 않았다.

기존 oneshot 색인기·리뷰 큐는 매 기동 시 소스를 다시 읽으므로 별도 서비스 설정 변경은 없다.
로컬 소스는 구현됐지만 **커밋·Gitea push 및 신규 운영 커밋의 자동 감지→리뷰 종결 실증은 아직**이다.
실행 경로는 Gitea commit/push 감지→소스 경계에 맞는 리뷰 등재→큐 타이머 소비다.
워커가 로컬 commit만 하고 push하지 않은 상태를 마스터가 즉시 감지한다고 주장하지 않는다.

커밋 요청 범위: 리뷰 코드·주석·테스트5개(`review_gen.py`, `review_runner.py`,
`events/consumer.py`, `projects/profile.py`, `test_python_commit_review.py`)와
`docs/17-review-queue.md`, 이 리포트83. 앞선 브로커·원격 설정 문서 미커밋 변경은 별도로 남는다.
