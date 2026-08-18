# 24 — #220 claimer 작업별 로그 축적 (원전 worker_debug 회귀) + /cluster 「지금」 열

## §1 발단 — 「클러스터링 작업 시작하자」의 오해석과 교정

세션 시작 발화를 직전 세션(리포트 23 분산 실전)의 연장으로 읽고 /distribute 를 발동,
#169 태깅 후보에서 대상(UMissionMultiTaskBase)까지 임의로 골라 계획을 세웠다. 사용자 교정:
**"레드마인 일감을 하는거 아닌거 같은데?"** — 맞다. #169 의 실 태깅·확정 기입은 게임팀 몫이고
(제안형 계약), 태깅 구현 확대는 열린 일감이 아니었다. 승인했으면 일감 없는 작업에 골조 opus +
추론 + 빌드 비용을 썼을 것. plan 단계 정지 구조 덕에 실 피해 0 (계획 JSON 만 생성 → 삭제).
[중요] 교훈은 메모리에 적립: **그 발화 = 레드마인 [AX] 열린 일감 조회 → 사용자가 고름.**
/distribute 는 "분산 작업/워커들한테" 같은 명시 발화에만.

## §2 사용자의 진짜 요구 — 원전 대조가 이식 누락을 확인

사용자: *"기존 로직에서도 데몬 빌드부터 활성화 이후 각 작업마다 로그를 쌓아뒀는데"* →
원전 실물 확인 (worker/common.py:89-99 · heartbeat.py:86-101 · claude_spawn.py · worker.py:443):

    원전   .claude/logs/worker_<date>.log       일별 + 부팅 _N 회전 + fsync
           .claude/logs/worker_debug/<task_id>/  작업별: heartbeat.log(매 심박) +
                                                 LLM stdout/stderr 실시간. 종료 후 보존, 7일
    우리   .ax/logs/claimer.log                  머신당 1개, 상한 절단(회전 아님)
           작업별은 result.json(사후 사실)뿐     진행 중 추적 없음

[중요] census 는 4파일 모두 인용 있음이었다 — **인용됨 ≠ 전부 이식** (docs/11 §11.2.1)의 실증
사례가 하나 더 늘었다 (#214 와 같은 부류). → **#220 등록** (마일스톤 6, 사용자 승인). 사용자
추가 결정: ③ 쌓인 로그를 /cluster 웹UX 에 띄워 어느 작업 중인지 표현.

## §3 구현 (커밋 69f3e2d + 902a040)

    ① 작업별   .ax/logs/claimer_debug/<task_id>/ — heartbeat.log(매 심박+note),
              llm_stdout.log·llm_stderr.log(Popen 파이프 실시간 스트림), build.log(요약+꼬리 16KB)
    ② 회전     claimer_<date>.log 일별 + 부팅 _N 회전(원전 common.py·우리 task_queue 와 동일
              이식) + retention 7일 스윕(상주 부팅 시, 지운 수를 로그에). 옛 절단 방식은
              문제가 난 날의 **앞부분(원인)** 을 지우는 결함이라 폐기
    ③ /cluster 심박에 note(「지금 하는 일」 200자) 동승 → 큐 task.note/note_at →
              실시간 층 표 「지금」 열(note+나이). 위상 전환(실체화→추론→종료, 빌드 시작→종료)은
              **즉시 심박 1회** — 240s 간격만으로는 위상을 통째로 놓친다. SSH 무접촉(#216) 유지

설계 주의 둘:
- [중요] **stderr 는 stdout 에 섞지 않았다** — collect 의 `RESULT:` 말미 마커 계약이 stderr
  혼입으로 깨질 수 있다. 분리 계약을 테스트로 박음.
- 빈 note 심박은 이전 note 를 유지한다 — 심박마다 note 를 만들 의무를 워커에 지우지 않는다.
- 부수 개선: 빌드 잡도 심박 스레드로 (전에는 착수 시 1회뿐 — 109~194s 빌드에서 리스가 낡았다).
- _Heart 의 note 전달 여부는 **초기화 때 시그니처로 판정** — 호출 시 TypeError 폴백은 beat
  내부의 TypeError 까지 삼켜 심박을 조용히 절반만 돌게 한다.

## §4 실측 — 라이브가 또 결함을 잡았다

테스트 3534/3534 (신규 8건: note 저장/유지/절단 · 회전 · retention · 즉시 심박 · 스트림/stderr
분리 · run_infer 디버그 · UI 열 2건). 그러나 [중요] **.2 라이브 부팅이 유닛이 못 본 순서 결함을
잡았다**: ax_safety.apply_all 이 로그 2줄을 먼저 써서 오늘 파일을 만들고, 그 **다음** 회전이
그 파일을 _1 로 밀어 부팅 자신의 줄이 두 파일로 갈렸다. 회전을 첫 로그 앞으로 이동(902a040),
재부팅으로 한 파일 수렴 확인 (23:08:29 guards+boot 동일 파일, 이전분 _2 회전).
**"게이트마다 라이브 런 하나"** — M3 의 교훈이 다섯 번째로 맞았다.

## §5 배포

- 마스터: ax-task-queue·ax-projects 재기동 (ExecMainStartTimestamp 검증 — #216 의 D-Bus 함정
  절차대로). /cluster 서빙 페이지에서 「지금」 열 렌더 확인.
- 배달: deliver 2회(초판+수정) — .2·.33·.43 **3곳 모두 해시 대조 통과.** [주의] 세션 초 probe 의
  .33 SSH 실패는 일시적이었다 (사용자 확인 "원격 접속 가능" + 배달 실증).
- 데몬: .2 AxClaimer /end→(10s)→/run — [주의] 가이드의 잠금 해제 지연 함정 그대로 지킴.
  .43 은 pkill 후 cron 재기동. [중요] .43 원격 pkill 은 `pkill -f 'claime[r]'` — 패턴에
  claimer 가 그대로 들어가면 **원격 셸 자신을 죽인다** (exit 255 실측).
- 클론 동기화: GitHub push + .43 ax-cluster pull (사용자 승인).

## §6 남은 것

- [대기] 사용자 브라우저에서 실 작업 중 「지금」 열 실사용 소감 (#220 해결→완료 전환 판단)
- [대기] 실 분산 작업에서 claimer_debug/<task_id>/ 실전 검증 (다음 파견 때 자연 확인)
- 개선 여지(미착수): note 를 브로커 recent 칩에도 잇기 · /cluster 에서 debug 로그 꼬리 열람
  (SSH 무접촉과의 절충 필요 — 스냅샷 주기에 실을지)
