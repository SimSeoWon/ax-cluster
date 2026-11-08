# #897 — 상주 서비스 신선도의 내용 비교 (2026-11-08, Codex)

## 지시·범위·작업 위치

- 사용자 원문: 「인수인계서 확인해」 → 「#897 작업 진행해」 → 「로컬 서브 에이전트로 진행해줘」.
- 패치 작성 오류 보고 뒤 사용자 원문: 「응 수정하고 진행해」. 기존 범위 구현·검증 재개 승인으로 해석했다. 커밋·push·운영 반영·재기동 승인으로 확대하지 않았다.
- 로컬 에이전트: `freshness_impl`(구현 4파일), `freshness_tests`(회귀 1파일), `handoff_review`(읽기 전용 독립 검토).
- 운영 `/home/sim/ax-cluster`: `main=origin/main=55a793747305e2615f29b1c6fbe1a528e8f1c906`, 작업 전·검사 중 `git status --short --branch`는 `## main...origin/main`만 출력(rc0).
- `issue_start_tool(897)` 응답 원문 주요 필드:

```json
{"ok":true,"issue_id":897,"branch":"issue/897","repo":"/home/sim/ax-cluster/.ax-issues/897","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"55a793747305e2615f29b1c6fbe1a528e8f1c906","redmine":"레드마인 #897 갱신 (notes, status_id)","lock":"acquired"}
```

- 편집·검사는 응답 `repo`에서만 했다. finish는 호출하지 않았으므로 `done`·`why` 응답은 없다. 새 커밋 해시도 아직 없다.
- 세션 파일: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T12-15-29-01a1b927-65c1-71a3-b8ac-25d9a2331e37.jsonl`.

## 근거 대조

1. **참 — mtime만으로 stale 판정**: 시작 리비전 `master/service_freshness.py:check()`의 `v.stale = v.newest > v.started`. 내용 비교가 없다. #897 본문은 2026-11-07 동일 내용 재작성 후 불필요한 재기동 실측을 적고 있다. 그 과거 현상을 이 세션에서 다시 운영 재현하지 않았다.
2. **참 — broker 홈 기록 불가**: 등록 유닛과 실제 `systemctl show`에서 `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths=`. 3개 서비스 모두 `StandardOutput=journal`, `StandardError=journal`. 권한 설정을 바꾸지 않고 stdout 기록을 선택했다.
3. **참 — 기존 감시 범위를 유지해야 함**: `RESIDENT`와 `docs/12-multi-project.md`는 projects의 `master/work/register.py` 단일 파일 감시를 명시한다. `master/work` 전체로 넓히지 않았다.
4. **부분 — newest가 내용 변경 시각인가**: 값은 감시 범위 파일의 최대 mtime일 뿐이다. `master/client/__main__.py`의 update 원인 요약은 이 값을 읽지만 내용 차이가 발생한 시각을 증명하지 못한다. 기존에도 있던 인과 요약 한계이며 이번 범위에서는 소비자를 편집하지 않았다. 최신/stale의 내용 비교 결과에는 영향이 없다.

RAG는 `search_context_tool(task_type="user_command", user_request="#897 작업 진행해", query="서비스 신선도 service_freshness 기동 코드 내용 해시 mtime ExecMainStartTimestamp", limit=5)`로 호출했다. request_id=`6d71db0e779c4d9b92ee1d0159f31c3c`. 반환한 service_freshness·test_service_freshness 문서 본문을 실제 소스와 대조했다. 파일 경로 목록 조회와 읽기는 별도 호출로 했다.

인수인계·공용 규칙·M7·다중 프로젝트 문서, 관련 리포트 73·86·138~144는 읽었다(일부는 독립 검토 에이전트가 전문 대조). 나머지 reports 전체 전문 읽기는 하지 못했으며 전체 복원 완료로 주장하지 않는다. 담당 조회는 마지막 master=`claude`, worker=`codex`, source=`state`였다. 담당 기록·워커 모드를 변경하지 않았다.

## 구현

- `master/service_freshness.py`: 선언 경로·Python 파일 목록·각 파일 SHA256을 정렬 집계한 기동 해시를 stdout 한 줄로 기록한다. `INVOCATION_ID`·서비스·스키마·감시 범위를 포함한다. 기동 때 코드가 없거나 읽기 실패면 판정 불가 근거를 기록한다.
- 검사는 현재 systemd InvocationID의 journal 마커만 조회하고 trusted `_SYSTEMD_INVOCATION_ID`, `_SYSTEMD_UNIT` 및 기록 형식을 확인한다. 로그 누락·손상·중복·조회 실패를 최신으로 접지 않는다. 조회 뒤 invocation이 바뀌면 재기동 중 판정 불가다.
- 현재 내용 해시를 비교하므로 같은 내용의 mtime 변경은 최신, 실제 내용 변경·Python 파일 추가·삭제는 stale이다. 기존 `check()`·`stale_lines()`·Verdict 진단 필드는 유지한다.
- `master/projects/__main__.py`, `master/broker/__main__.py`: 상주 모듈 import 전에 기록한다.
- `master/task_queue/__main__.py`: `--serve`일 때만 상주 import 전에 기록한다. stdio MCP·조회 CLI stdout은 보존한다.
- `master/test_service_freshness.py`: 위 동작, 오류 처리, 진입점 호출 순서를 회귀 검사한다. 임시 일반 파일·주입 runner 회귀이며 운영 실증으로 제시하지 않는다. 자동 재기동·유닛 설정 변경은 없다.

## 실패와 재개

1. 구현 후속 패치 실패 원문: `apply_patch verification failed: Failed to find expected lines in /home/sim/ax-cluster/.ax-issues/897/master/service_freshness.py:`. 실제 파일에 없는 문장을 문맥으로 지정했다. 앞선 구현만 적용됐고 실패 패치는 미적용이었다.
2. 테스트 교체 패치 실패 원문: `invalid patch: multiple operations target .../master/test_service_freshness.py`. 동일 파일 Delete+Add를 한 패치에 넣었다. 검증 단계 거절로 미적용이었다.
3. 사용자 실패 중단 규칙으로 두 에이전트 편집·검사를 멈추고 T1을 차단으로 기록했다. 사용자 「응 수정하고 진행해」 뒤 T1을 작업중으로 복원해 Update 패치로 재개했다. 실패를 운영 서비스 결함으로 보고하지 않았다.

## 검증 증거

작업 위치는 전부 `/home/sim/ax-cluster/.ax-issues/897`이다.

1. `git diff --check`: rc0, 출력 없음.
2. `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_service_freshness.py`: rc0, **통과 43 · 실패 0**.
3. 기존 `master.work.pystatic.run_static`을 시작 리비전 `55a793747305e2615f29b1c6fbe1a528e8f1c906`과 변경 Python 5파일에 적용: rc0. pyflakes 5파일 차단0·노트0, import 1모듈 차단0·환경0, mypy 5파일 차단0·비차단 assignment 노트2(projects 기존 app 래퍼 대입). 테스트 최종 보완분의 정적 검사 결과는 아래 최종 상태에 기록한다.
4. 공식 통합 명령:

```sh
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

정본 명령만 담은 `/tmp/ax-897-integration-approved.sh`를 샌드박스 해제 승인 후 실행했다. `id -Gn`은 `sim nogroup`이고 기본 샌드박스의 `sg gitea` 차단은 리포트86에서 확인된 제약이다. 공식 통합 결과는 아래 최종 상태에 기록한다.

## 운영 읽기 관측·한계

- 3서비스 모두 active/running. 기동 시각 queue·broker=`2026-11-08 09:51:51 KST`, projects=`2026-11-08 11:43:18 KST`.
- InvocationID: queue=`ca3854a2b79e41a6bff8167fe918175f`, broker=`1137f142600e479993efe83353567e7e`, projects=`083ce0b75cb54416b58f507c2f7d8052`.
- 기존 broker invocation의 일반 journal JSON 읽기는 rc0으로 trusted unit·invocation·MESSAGE 확인. 새 마커만 필터한 `journalctl --no-pager --all -o json -n 2 _SYSTEMD_INVOCATION_ID=1137f142600e479993efe83353567e7e '--grep=^AX_SERVICE_CODE_V1 '`는 rc1, stdout/stderr 없음. 아직 새 코드로 기동하지 않아 기준 마커가 없다.
- 새 `check()`의 Python 자식 systemctl은 기본 샌드박스에서 rc1로 읽기 불가였다. 코드 결함으로 고치지 않고 동일 읽기 명령만 담은 `/tmp/ax-897-freshness-readonly.sh`를 샌드박스 해제 승인으로 재실행(rc0). 실제 기동 시각 3개를 읽었고 모두 `stale=false`, `why="기동 코드 기록을 읽지 못했다 (journalctl rc=1)"`로 판정 불가를 보고했다. **stale=false만 떼어 최신으로 해석하면 안 된다.**
- 운영 최신/내용 변경의 완주 실증은 미실행이다. main 반영 및 승인된 재기동 후 기동 마커 생성·동일 내용 비교를 확인해야 한다. 이 세션은 재기동하지 않았다.
- 해시는 기동 직전 디스크 `.py`의 내용이다. 실제 프로세스 메모리·timestamp-valid pyc의 바이트 동일성, snapshot과 import 사이 파일 교체의 원자성까지 보증하지 않는다.

## 최종 상태

- 공식 통합 검사 rc0, `Ran 188 tests in 185.477s`, `OK`. 명시 목록 188개 전부 통과했고 skip·실패는 없다. `test_source_scope`도 32/32로 통과했다. 이는 명시 목록의 결과이며 목록 밖 검사를 실행했다고 주장하지 않는다.
- 최종 테스트 보완 뒤 `run_static`을 `master/test_service_freshness.py`에 재적용했다. rc0, pyflakes 1파일 차단0·노트0, mypy 1파일 차단0·노트0. 테스트 모듈은 기존 import 검사 계약의 제외 대상(checked=0)이며 import 1건 성공으로 세지 않았다.
- 마지막 `git diff --check` rc0. Python 변경5파일과 리포트1파일이 미커밋으로 남아 있다. 로컬 독립 검토 5파일에서 차단 지적은 없었다.
- 커밋·finish·배달·재기동 미실행. 제안 커밋 메시지: `fix: #897 상주 서비스 신선도를 기동 내용 해시로 판정`.
- T1 작업중, T2 선행 대기. 검사와 커밋 근거를 확보하기 전에 완료로 기록하지 않는다.
