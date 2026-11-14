# 183 — #944 히스토리 파일명 충돌 시 기록 보존

2026-11-14 · Codex · 로컬 서브에이전트 `history_fix` 구현, 메인 세션 검증.

## 사용자 지시와 범위

- 사용자 원문: 「944 진행하자」 → 제안 플랜·방식 질문에 「응 로컬 서브 에이전트로 진행해」.
- 합의: 기본 파일명 유지, 충돌 시 `_2`, `_3` 접미사와 배타적 생성. 과거 파일 재작성·복원은 하지 않는다.
- RAG `search_context_tool` request_id `729416b0555347ed93c2542883861180`. 반환 문서
  `AXCluster/context/master/context_synth/history_gen.md`·`history_harvest.md` 전문과 실제 소스 대조.
- 소비자 근거: `history_harvest.walk_histories`는 `*.md` 열거, `parse_claude_history`는 frontmatter의
  날짜와 본문을 읽는다. `find_history`의 `search`와 웹 `api_history`도 같은 파서를 쓴다.
  파일명의 제목 뒤 접미사에 의존하는 계약은 이 경로에 없다. Gemini txt의 prefix 규칙은 별개다.

## 작업 위치와 커밋

`issue_start_tool(944)` 응답 원문 필드:

```json
{"ok":true,"issue_id":944,"branch":"issue/944","repo":"/home/sim/ax-cluster/.ax-issues/944","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"15cda680f1a213931815614480d48379a20135ad","lock":"acquired"}
```

재개 응답은 같은 repo·start_rev, `already:true`, `lock:already`. 작성 계열 `codex`, 누적 `['codex']`.

- `c1ba57f`: `history_gen.write()`가 `Path.open("x")`로 배타적 생성. 생성의 `FileExistsError`만
  다음 접미사로 재시도한다. 기타 생성·쓰기 오류는 호출자에 전파한다. 기존 라운드 이름 구분은 유지한다.
- `c4ef271`: 기존 `test_history_gen.py`에 회귀 검증 추가. 새 검사 파일은 없으며 공식 목록의 기존 항목으로 실행된다.
- 이 리포트 커밋은 검사 결과를 기록한다. 운영 체크아웃은 편집하지 않았다.

## 실물 검사와 결과

작업 위치는 위 repo. Python은 `/home/sim/ax-cluster/.venv/bin/python`.

- `master/test_history_gen.py`: 변경 전 24/24, 변경 후 **34/34**, rc0.
  고정 시각 동일 제목 3회 기본명·`_2`·`_3`, 모든 내용 불변, 48자 절단·금지문자 정규화 충돌 보존.
  spawn 6개 프로세스를 Barrier로 동시 시작해 실제 파일 수 6과 서로 다른 내용 6개가 일치함을 확인했다.
  `HH.search`와 `api_history`가 접미사 파일 포함 세 기록을 모두 읽는다. 권한 오류는 원문 전파·재시도 0.
- `master/test_history_terminal.py`: **29/29**, rc0.
- `master/test_history_harvest.py`: **47/47**, rc0.
- `git diff --check`: rc0.
- 승인된 `sh /tmp/ax-944-checks.sh`: rc0. Git 그룹 권한 검사를 위해 샌드박스 밖 실행.
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster`와 위 Python을 사용했다.
  - `pystatic.run_static(Path.cwd(), "15cda680f1a213931815614480d48379a20135ad", ["master/context_synth/history_gen.py", "master/test_history_gen.py"], python=sys.executable)`:
    pyflakes 2파일 차단0·노트0, import 1모듈 차단0·환경0, mypy 2파일 차단0.
    mypy 비차단 노트4는 기존 파서의 union-attr 3·assignment 1이다.
  - `-B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`:
    **Ran 197 tests in 206.893s / OK**, rc0. 임시 프로젝트·Git 조건 검사를 운영 실증으로 해석하지 않는다.

## 중단·재개와 한계

운영 유실 흔적 조회:

```text
journalctl -u ax-task-queue --since '2026-11-14 00:00:00' --grep='\[history\]' --no-pager -o cat
rc=1, stdout/stderr 없음
```

실패 규칙에 따라 메인·서브에이전트 중단. 사용자에게 운영 로그를 미확인으로 남기고 T2 재개할지 물었고
사용자가 「응」으로 승인해 재개했다. 이 응답을 유실 없음의 증거로 삼지 않는다. 운영 과거 유실 건수는 미확인이다.
동시 쓰기는 임시 디렉토리의 실제 프로세스 IO로 검증했으며, 운영 트윈에 검사용 기록을 적재하지 않았다.
배타적 생성은 기존 기록 덮어쓰기를 막는다. 디스크 오류 시 새 파일의 완전성 보장·원자적 공개는 이번 범위가 아니다.

세션 기록: `~/.codex/sessions/2026/11/14/rollout-2026-11-14T16-06-09-01a1d8e0-bb1a-7242-a57e-ed979a9f3a45.jsonl`.

최종 결과는 Redmine #944 마감 노트.
