# 184 — #368 잔여 한도 표시와 인수인계 제안

2026-11-14 · Codex · 로컬 서브에이전트 `quota_collect`(수집·콘솔), `quota_tests`(회귀). 메인이 diff·실행 검증.

## 사용자 결정과 범위

사용자 「다음 유용해 보이는건 368번이었어」 뒤 조회·범위 제안에 「응 진행해줘」,
플랜과 방식 질문에 「로컬 서브에이전트로 진행해줘」. 아이디어 버전에서
`마일스톤 8 — 개선·확장`으로 옮겨 되읽었다. 이번 범위는 master.relay의 표시·사전 제안이다.
자동 교대·인수인계서 자동 작성·기존 CLI TUI에 상태줄을 설치하는 것은 포함하지 않는다.

RAG request_id `2acd743e853e4150bc01d0a17f0759db`. 반환된 relay/__init__ 문서와
추가로 확인한 agents·console 컨텍스트 본문, 실제 소스·리포트180을 대조했다.
기존 코드는 Claude rate_limit_event를 meta로 받되 UI에 내지 않았고 store는 session·seen·turns만 저장했다.

## 위치·커밋

issue_start_tool(368) 응답 필드:

```json
{"ok":true,"repo":"/home/sim/ax-cluster/.ax-issues/368","checkout":"/home/sim/ax-cluster","branch":"issue/368","already":false,"start_rev":"174d178f77b4efb60484eff38cb3c01c285e4ed5","lock":"acquired","author":{"family":"codex","authors":["codex"]}}
```

- `e3c88b1`: quota.py, agents.Result.quota·수집 연결, store 한도·경고 저장 및 reset 비움.
- `ed6f03d`: 턴 끝·/status 표시, 기본20% 경고, CLI·환경변수 설정, 중복 억제.
- `d514b43`: test_relay 회귀와 README 안내, 콘솔 줄바꿈 정리.
- 이 리포트 커밋은 아래 검사 결과를 기록한다. 운영 체크아웃은 일감 구현 중 편집하지 않았다.

## 동작 계약

Claude는 stream-json unifiedWindows의 utilization·resetsAt을 읽는다. Codex는
thread ID UUID와 파일 헤더 session_meta ID가 일치하는 rollout만 읽는다(CODEX_HOME 지원).
메타256KiB·끝1MiB로 읽기량을 제한하며 최신 token_count가 null이면 이전 정상값을 추정하지 않는다.
기록 시각·source·창별 잔여율·리셋 시각을 보관한다. 인증 파일·추가 네트워크 API를 쓰지 않는다.

턴 끝 현재 에이전트, /status는 모든 에이전트를 표시한다. 관측15분 초과·미래 시각·리셋 경과·누락은
미확인. 사용 토큰으로 잔여율을 추정하지 않는다. agy 한도도 미확인이다.
`--quota-threshold` 또는 `AX_RELAY_QUOTA_THRESHOLD`(0~100, 기본20) 이하에서 인수인계서 갱신과
/agent 교대를 제안한다. 창·리셋별 경고를 저장해 콘솔 재개 후에도 중복 억제하고 회복하면 해제한다.
화면의 제안만 추가하며 LLM 프롬프트 삽입·자동 교대·재시도는 하지 않는다.

## 검사와 실측

작업 위치는 위 repo, Python `/home/sim/ax-cluster/.venv/bin/python`.

- `master/test_relay.py`: T1/T2 기존113/113 → 추가 회귀 **147/147**, rc0.
  실제 가짜 subprocess에서 parser→Result→상태 저장→재개/status→경고 억제→reset 연결,
  정확한20% 경계·21% 회복·새 리셋 경고, 미래/만료/잘못된값, Codex 세션 혼입·null·부분줄 검증.
- `git diff --check`: rc0. 읽기 전용 추가 검토에서 구체 결함 추가 발견 없음.
- `sh /tmp/ax-368-live.sh`: rc0, 기존 agents.run으로 실제 CLI에 도구 사용 없는 PONG 응답 요청.
  - Claude session `f9e90703-972f-4532-9caf-b6a070fd8fe1`: rc0, PONG,
    observed_at `1794645311.6241167`, 5h23% reset `1794655800`, 7d79% reset `1795208400`.
  - Codex session `01a1d932-46e6-7292-a93d-de1a2fda4010`: rc0, PONG,
    observed_at `1794645316.549`, 5h29% reset `1794658303`, 7d89% reset `1795245103`.
  - 두 실행 모두 quota_line에서 잔여율·현지 리셋 시각을 표시했다. 조회 당시의 관측값이며 현재 값은 아니다.
- 과거 실제 Codex session `01a1d801-eada-77e2-9456-bfc03ed8677c`를 신규 수집기로 읽어
  5h33%·7d13%·관측/리셋 epoch를 확인했다. 오래된 값은 UI의 유효성 필터에서 미확인 처리한다.
- `sh /tmp/ax-368-checks.sh`: rc0. Git 그룹 권한 때문에 승인된 샌드박스 밖 실행.
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 지정, 기존 pystatic.run_static에 시작리비전과 변경5개 py 전달.
  pyflakes5파일 차단0·노트0, import4모듈 차단0·환경0, mypy5파일 차단0·비차단26노트.
  공식 `-B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`:
  **Ran 197 tests in 215.291s / OK**, rc0. relay147건 포함. 별도 전수는 실행하지 않았다.

## 한계·남은 관측

실제 CLI 두 실행은 기본 임계보다 높았다. 실제 한도20% 도달과 사람의 교대 선택은 실증하지 않았다.
경고·상태 재개 연결은 가짜CLI·임시 파일로 검증했다. 긴 도구 실행 중에는 경고하지 않고 턴 끝에 제안한다.
API/CLI 로그 형식이 바뀌거나 tail 범위에서 관측을 못 찾으면 미확인으로 표시한다.
기존 relay를 실행한 프로세스는 새 코드로 다시 실행해야 기능을 사용한다.

세션 기록: `~/.codex/sessions/2026/11/14/rollout-2026-11-14T16-06-09-01a1d8e0-bb1a-7242-a57e-ed979a9f3a45.jsonl`.

최종 결과는 Redmine #368 마감 노트.
