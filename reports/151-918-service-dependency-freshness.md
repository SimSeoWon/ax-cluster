# 151 — #918 상주 서비스 신선도: import 의존을 두 번째 등급으로

> 2026-11-08 · Claude · 일감 #918 · 시작 리비전 `4aaf4d2` · 작업 위치 `.ax-issues/918`(`issue/918`)

## 왜

#917(`93d7688`)이 `master/context_synth/issue_track.py` 등 5파일을 바꿨는데, 배달 뒤 `service_freshness.check()` 가
세 서비스 모두 「최신」이었다. `RESIDENT` 감시 경로가 각 서비스 디렉터리뿐이라, ax-projects·ax-task-queue 가
`issue_infra` 를 거쳐 쓰는 `issue_track`·`issue_link` 나 `master/auth.py` 의 변경을 보지 못한다.

## 실측과 사용자 결정

- 진입 모듈(`python -m master.task_queue|broker|projects`)에서 정적 import 를 따라가면(함수 안 지연 import 포함)
  ax-projects 156 · ax-task-queue 145 · ax-broker 8 파일(진입·직접 경로 포함).
- 11-01 이후 master·client 커밋 76 중 ax-projects 의존을 바꾼 것 57, ax-task-queue 48 — 이것을 종전처럼 [중요]·
  check FAIL 로 올리면 거의 매 커밋 빨갛다(코드 주석 「넓게 잡지 않는다」·#772 와 같은 걱정).
- 사용자 선택: **두 등급**(직접 경로 = 종전 [중요] stale · 나머지 의존 = [주의] 「재기동 권장」, rc 영향 없음),
  수행은 이 세션에서 직접. RAG request_id `b17c3674898d48409bdeaf6eb0d1ad2a`.

## 변경

- `master/service_freshness.py`
  - `ENTRY`(서비스 → 진입 모듈) · `dependencies(unit)` — AST 로 import 폐포(저장소 `master`·`client` 만, `a.b.c` 는
    `a`·`a.b` 의 `__init__` 포함)를 구하고 직접 경로를 뺀다. 실패는 사유로 돌려준다(「의존 없음」으로 접지 않는다).
  - `record_startup` — 기동 기록에 `deps`·`deps_digest`·`deps_why` 를 **같은 version 1 의 선택 필드**로 덧붙인다
    (옛 판독기와 호환). 실측 기록 줄 3,848자(ax-projects) — journald 기본 LineMax 48K 이내.
  - `_record` 분리 — `_baseline` 의 반환·사유 계약은 그대로.
  - `Verdict.dep_changed`·`dep_files`·`dep_why`·`dep_line`, `_judge_deps`, `dep_lines()`.
    직접 판정이 stale·판정 불가면 의존은 보지 않는다. 의존 1차 거름(기동 뒤 변경 흔적 없음 → 조용) 뒤 기동 기록의
    의존 목록·해시와 대조한다. 목록이 달라져도(새 import) 바뀐 것으로 본다. 옛 기록(의존 필드 없음)은
    「다음 재기동부터 판정한다」 [주의].
  - `stale_lines()` 는 바꾸지 않았다 — 상태 화면(`status.py`)의 문제 목록에는 의존 등급이 들어가지 않는다.
- `master/client/__main__.py` — update/check 의 마스터 서비스 블록 뒤에 「[주의] 마스터 서비스 의존 모듈 N건 —
  재기동 권장(판정 실패 아님)」을 찍는다. `bad`·rc·`fresh_bad` 에는 넣지 않는다.
- 자동 재기동은 여전히 없다(`docs/11` §11.5).

## 검증

- `test_service_freshness` rc0 **67/67**(기존 51 + 신규 16): 임시 저장소에서 지연 import 포함 폐포 · 기동 기록 필드 ·
  변경 없음 조용 · 의존 변경 → [주의]·stale 아님·`stale_lines` 빔 · 자동 재기동 없음 · 새 import 로 목록 증가 ·
  직접 변경은 종전 [중요] · 옛 기록 → 판정 불가 [주의]. 실저장소에서 task_queue·projects 의존에
  `issue_infra`·`issue_track`·`auth` 포함, 직접 경로 파일 없음, broker 의존에 `auth`.
- `test_client_bundle` 661/661 · `test_stale_unknown` 27/27 · `test_status` 82/82 rc0.
- 정적(`pystatic.run_static`, 기준 `4aaf4d2`, 3파일): pyflakes·import 차단 0 · mypy 차단 0·비차단 노트 4. `git diff --check` rc0.
- 공식 통합(정본 명령, worktree): rc0 **`Ran 188 tests in 177.601s`·`OK`(188/188)**.
- 사용자 「결과 나오면 커밋하고 마감, broker 재기동까지 진행해」·「배달도 같이 진행해」 — 커밋·마감·ax-broker 재기동·배달 승인.

## 이번에 드러난 것

- worktree 코드로 운영 서비스를 판정해 보니 **ax-broker 의 의존 `master/auth.py` 가 기동(12:31:47) 뒤 바뀌어 있었다** —
  #898(`54b5632`)이 `auth.py` 를 고쳤고, 그때 ax-task-queue 만 재기동했다. broker 는 옛 `auth.py` 로 돈다.
- 배포 직후에는 세 서비스 모두 「기동 기록에 의존 목록이 없다(#918 이전 기동)」 [주의] 가 뜬다 — 다음 재기동부터 판정된다.

최종 결과는 Redmine 마감 노트.
