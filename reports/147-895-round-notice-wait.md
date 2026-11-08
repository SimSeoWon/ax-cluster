# 147 — #895 라운드 공지 검사에서 멱등 표시 저장 대기

2026-11-08 · Codex · http://192.168.0.57:8080/issues/895

## 지시·범위

- 사용자 원문: 「895번 진행해」 → 「로컬 서브 에이전트로 진행해줘」.
- 합의 플랜: T1 `master/test_rounds.py`의 대기를 멱등 표시 저장까지로 수정, T2 정적·공식 통합 검사와 근거 기록.
- 구현 에이전트 `rounds_fix`, 읽기 전용 독립 검토 `rounds_review`. 두 에이전트 모두 경로 목록 조회(rc0)와 파일 읽기를 별도 호출했다.
- 커밋·push·마감·배달·서비스 재기동 승인은 아직 없다.
- 세션 파일: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T15-33-25-01a1b9dc-9c24-7cf2-b6b2-a378290954d0.jsonl`.

## 시작·RAG 근거

`plan_start_tool(895)`은 `verdict=plan_needed`, `ok=false`였다. 사용자 방식 선택 후 `plan_set_tool`로 T1/T2를 등록했다.
RAG request_id=`81e2529c032a4dd2aebe60878f90061f`. 반환 문서 `AXCluster/context/master/test_rounds.md`와
`test_notice_recovery.md` 본문을 읽고 실제 `master/test_rounds.py`, `master/task_queue/logic_cleanup.py`와 대조했다.

`issue_start_tool(895)` 응답 주요 필드 원문:

```json
{"ok":true,"issue_id":895,"branch":"issue/895","repo":"/home/sim/ax-cluster/.ax-issues/895","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"331b2601681cf85b59f907c0752325c3a9aed90a","redmine":"레드마인 #895 갱신 (notes, status_id)","lock":"acquired"}
```

편집·검사는 응답 `repo`에서만 했다. 운영 체크아웃 `git status --short --branch` rc0은 `## main...origin/main`뿐이다.
finish 미호출로 `done`·`why` 응답은 없다. 새 커밋도 없다.

## 결함별 판정과 수정

1. **참 — 노트만 기다리는 경쟁.** 기존 `test_completion_is_a_note_not_a_new_issue`는 `if notes: break` 후
   `noticed_round==1`을 단언했다. `logic_cleanup.py:655–661`은 `_redmine_add_note` 성공 뒤
   `_record_notification_outcome`을 호출한다. 노트 존재만으로 저장 완료를 보증할 수 없다.
2. **참 — 같은 잠금으로 저장 완료 관측 가능.** `_record_notification_outcome`의 `idx.lock` 안에서
   `noticed_round` 설정과 `_save_work`가 실행된다(`logic_cleanup.py:22–36`). 테스트도 같은 잠금을 얻고
   `noticed_round==1`을 확인하도록 변경했다. sleep은 잠금 밖이다.
3. **미재현 — 과거 부하 실패.** 이 세션에서 수정 전 간헐 실패를 재현하지 않았다. 과거 병렬·단독 실패는 #895 본문 기록이며,
   이번 변경 근거는 현재 소스의 순서와 동기화 계약이다.

변경은 테스트 +4/-2줄이다. 200회·0.01초 대기 한도와 기존 노트·브랜치·멱등 단언은 유지했다.
독립 검토는 차단 지적 없음: 잠금 밖 sleep, 저장 완료 후 관측, 뒤의 메타 갱신·로그가 복구되는 Redmine 모의 함수를
재사용하지 않음을 확인했다. 운영 코드는 변경하지 않았다.

## 검증

cwd는 `/home/sim/ax-cluster/.ax-issues/895`, 해석기는 `/home/sim/ax-cluster/.venv/bin/python`이다.

- `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_rounds.py`
  rc0, `OK test_rounds: 실패 0건`. 스크립트가 총수를 출력하지 않아 총 통과 수로 환산하지 않았다.
- `git diff --check` rc0.
- `master.work.pystatic.run_static('.', '331b2601681cf85b59f907c0752325c3a9aed90a', ['master/test_rounds.py'], python=sys.executable, flakes_python=sys.executable)`
  rc0. pyflakes 1파일 차단0·노트0, mypy 1파일 차단0·비차단 노트22, setup_error 없음.
  테스트 파일은 기존 import 검사 제외 대상으로 checked0이며 import 성공 1건으로 세지 않았다.
- 공식 통합 명령은 아래와 같다. 알려진 `sg gitea` 샌드박스 제약 때문에 해당 명령만 담은
  `/tmp/ax-895-integration.sh`를 샌드박스 해제 승인 뒤 실행했다.

```sh
AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

공식 통합 결과: rc0, `Ran 188 tests in 186.623s`, `OK`。188/188 통과, 실패·skip 없음。
`test_source_scope`도 32/32 통과했다. 수정한 `test_rounds.py`는 이 명시 목록에 없으므로 위 별도 실행 근거와 구분한다.

## 조회 실패와 재개

준비 중 존재를 확인하지 않은 `.agents`를 `rg --files` 인자에 넣어 rc2,
`rg: .agents: No such file or directory (os error 2)`가 발생했다. 수정 없이 멈춰 보고했고,
사용자 「로컬 서브 에이전트로 진행해줘」 뒤 합의한 범위로 재개했다. 경로·설정을 만들지 않았다.
새 리포트 번호 확인의 `rg --files -g '147*' -g '148*' reports` rc1·출력 없음은 매칭 없음이며,
후속 전체 리포트 파일 목록 조회 rc0으로 기존 최대 번호146을 확인했다.

## 멈춘 지점

미커밋이며 커밋·push·마감 승인 대기다. 전체 reports 전문 복원과 워커 배달 상태 확인은 하지 않았다.
최종 결과는 Redmine 마감 노트.
