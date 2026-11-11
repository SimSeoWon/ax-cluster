# 170 — #932 미러에 없는 마감 해시의 30분 알림

> 2026-11-12 · Codex 지휘 · 로컬 Codex 서브에이전트 구현·독립 검토 · 구현 `c4a31e233c6901e3187778ef95d72c55bbde0f75`

## 승인·작업 위치

사용자 원문: 「이제 932번 진행하자」.
`plan_start_tool(932)` 응답은 `plan_needed, ok=false`였고 RAG·현재 소스를 대조한 뒤 두 질문을 제시했다.
권장안은 로컬 Codex 서브에이전트, 등록 후 30분 알림1회·waiting 유지·실제 서비스 검증과 정식 종결·마감·배달이었다.
사용자 「응 진행해줘」로 합의했다. #933이 등록 검증을 끝냈으므로 등록 경고와 해시 수정 UI는 제외했다.

`issue_start_tool(932)` 응답의 핵심 원문:

```json
{"ok":true,"issue_id":932,"branch":"issue/932","repo":"/home/sim/ax-cluster/.ax-issues/932","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"ba9f435c35e5056a45612239ad99605b0052184a","redmine":"레드마인 #932 갱신 (notes, status_id)","lock":"acquired","author":{"client":"codex-mcp-client","family":"codex","authors":["codex"]}}
```

시작 응답에 `done`·`why`는 없었다. 편집·검사·커밋은 응답 `repo`, 운영 checkout은 main을 유지한다.
플랜 T1 착수 노트에 일본어가 섞인 오기는 후속 한국어 노트로 정정했다. 코드 실행 실패는 관측하지 않았다.

## 원인 대조 — 항목별

1. **해시 추적의 무기한 침묵 — 참**: `issue_progress._sync_round`는 큐 항목이 없고 `_has_commit`이 거짓일 때 `waiting`·로그만 유지했다. 등록 경과 판정이 없었다.
2. **워터마크 없는 경우도 감지 — 종전에는 거짓**: 기존 `if not wm: continue`가 미러 조회보다 앞이라 부재도 검사하지 않았다. 부재 판정을 워터마크와 분리했다.
3. **범위 리뷰도 무기한 대기 — 거짓**: `review_queue.cap(WAIT)=12`, `drain`은 회차당 같은 항목1회다. `issue_progress._follow_summary`는 시도별 재시도와 최종 포기 노트를 보낸다. 기존 유한 재시도는 유지했다.
4. **범위의 모든 Git 오류를 부재로 오인 — 참**: `run_range`는 `cat-file` rc가0이 아니면 전부 「미러에 아직 없다」로 처리했다. 해시 추적과 엄격 조회 함수를 공유해 오류를 구분했다.
5. **정상 흐름에서 두 종류 부재 노트 중복 — 발생하지 않는 구조**: `all_hashes_terminal` 전에는 범위 리뷰를 등재하지 않는다. 새 경보는 해시를 waiting에 두므로 범위 리뷰가 새로 생기지 않는다. 이미 큐에 있는 해시는 기존 실패·포기 알림 경로를 따른다.
6. **해시 등록 자체의 검증 — 현재 구현됨**: #933·#934 완료 근거와 현행 소스가 있다. #932는 이전 데이터나 다른 경로에서 들어온 부재를 드러내는 마지막 방어다. #929 복구와 새 등록 검증을 다시 구현하지 않았다.

RAG request_id=`5ec13d63ec59453a82924606c9f79c7b`, search_id=`92eb39af3aa84e5b9caac7e2f8caaa84`.
검색된 `AXCluster/context/master/context_synth/{issue_progress,issue_track}.md`와 `.../master/test_issue_progress.md` 본문을 읽고 실제 소비자를 대조했다.

## 변경 계약

- 등록 시각(`registered_at`, 시간대 포함)에서 **1800초 이상** 경과했고 정상 Git 응답이 명시적으로 missing일 때만 경보한다. 잘못된·미래·시간대 없는 시각은 기한 판정 불가 로그를 남기고 단정하지 않는다.
- `git cat-file --batch-check=%(objecttype)`의 정확한 `commit`/`<sha>^{commit} missing`을 구분한다. rc·stderr·응답 형식·프로세스/시간 제한 오류는 `CommitLookupError`이며 부재 경보를 보내지 않는다.
- 기존 schema1의 해시에 선택 필드 `mirror_missing={why,detected_at,noted,noted_at,recovered_at}`를 추가했다. 기존 flock·원자 저장의 공개 `set_hash_missing`·`clear_hash_missing`으로만 쓴다. 해시 상태와 종결 노트의 `noted`는 바꾸지 않는다.
- 이번 조회에서도 부재가 확인된 미알림 해시를 회차당 한 노트로 묶는다. 성공한 뒤 표시를 저장하고, 전송 실패 시 다음 동기화에서 재시도한다. 같은 SHA의 성공한 알림 표시는 재부재에도 보존한다.
- 늦게 실제 도착하면 복구 시각을 남기고 기존 queue/워터마크·리뷰 흐름을 따른다. 새 실패 상태나 자동 종결을 도입하지 않았다.
- 범위 리뷰는 같은 조회 함수를 사용하며, 부재는 기존 WAIT12, 조회 오류는 별도 사유로 기존 분류기에 넘긴다. 별도의 범위 부재 노트를 추가하지 않았다.

## 검사 근거

작업 위치 `/home/sim/ax-cluster/.ax-issues/932`, Python `/home/sim/ax-cluster/.venv/bin/python`, `AX_PROJECTS_ROOT=/home/sim/ax-cluster`.

| 실행 | 결과 |
|---|---|
| `bash /tmp/ax-932-core-checks.sh` — `python -B master/test_issue_track.py`, `test_issue_progress.py`, `test_review_runner.py` | rc0 · 106/106·123/123·133/133 = **362건** |
| `bash /tmp/ax-932-static.sh` — 기존 `pystatic.run_static`로 시작 리비전과 변경6파일 대조 | rc0 · pyflakes 차단0/노트1, import3모듈 차단0, mypy call-arg 차단0/기타코드 노트6 |
| `bash /tmp/ax-932-integration.sh` — 공식 통합 `python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc0 · `Ran 193 tests in 206.072s` · `OK` |
| `git diff --check` | rc0 |

기한 직전/정확한 경계·워터마크 없음·복수 해시1노트·재읽기 중복0·전송 실패 재시도·조회 실패 억제·실제 커밋 조회 복귀/queued 연결·잘못된 등록 시각을 회귀했다.
임시 Git·조회 대역으로 만든 단위 조건은 운영 실증과 구분한다. 독립 검토에서 차단할 결함은 발견하지 못했다.
검사 스크립트는 확인한 기존 검사 호출의 샌드박스 해제 범위를 좁히기 위한 것이며 AX 기능 대체 경로가 아니다.

## 실물 검증 준비와 남은 단계

승인한 검증은 `issue_track.register`로 #932 라운드1에만 등재했다:

```json
{"issue_id":932,"round":1,"registered_at":"2026-11-12T00:13:53+09:00","base":"ba9f435c35e5056a45612239ad99605b0052184a","end":"9320932093209320932093209320932093209320","hashes":["9320932093209320932093209320932093209320"],"by":"codex #932 approved live missing-hash validation (not a work commit)"}
```

이는 사용자 승인 아래 고의로 등록한 부재 검증 식별자이며 실재 작업 커밋으로 제시하지 않는다. 실제30분은 **00:43:53**부터다. 등록 시각·시계는 바꾸지 않았다.
검증은 worktree의 기존 서비스 진입점 `python -m master.context_synth.review_runner --project AXCluster --limit 0`을 실제 등록 트윈·Git 미러·Redmine으로 실행한다. LLM 생성은0건이며 소비자 잠금·등록루트 가드를 유지한다. systemd의 운영 main 소스를 미리 바꾸지 않는다.
기한 전 미알림, 기한 뒤 실제 노트1회·waiting 유지·summary 미등재·재회차 중복0을 확인한 뒤 공개 set_hash/mark_hash_noted/set_summary로 검증 회차를 정식 종결한다.
그 뒤 실제 마감 회차를 별도로 등록하고 신선도 판정·인수인계 main 커밋·배달/check를 수행한다. 최종 실제 결과와 finish의 `repo`·`done`·`why` 원문은 Redmine에 남긴다.

한계: Redmine 전송과 표시 저장은 서로 다른 시스템이다. 전송 성공 직후 프로세스가 종료되면 중복 가능성이 있으며 정확히1회 분산 트랜잭션은 구현하지 않았다. 잘못된 등록 시각은 사람 확인 대상으로 남는다.
세션 파일: `~/.codex/sessions/2026/11/11/rollout-2026-11-11T23-49-01-01a1cb15-6c15-73b0-895f-c9ad856cd447.jsonl`.

최종 결과는 Redmine 마감 노트.
