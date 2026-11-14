# 189 — #911 일감 스펙 템플릿과 `spec_missing` 경고

2026-11-14 · Claude · 이 세션이 직접 구현(사용자 선택).

## 발단과 결정

- 사용자: 「911 작업 진행하자! 아이디어에서 마일스톤 8 로 옮기고 작업 시작해줘」 → 버전을 「마일스톤 8 — 개선·확장」으로 옮김.
- 조사는 이미 있었다 — #911 노트 4건과 `reports/research/2026-11-13-911-pstack-playbook-analysis.md`(pstack 실제 저장소 `a5539b1` 대조, 6대 스펙 항목 제안).
- 현재 소스 대조: `master/plan_start.py` `assess` 의 `no_spec` 은 「플랜 영역 밖에 제목 아닌 줄이 하나라도 있으면 스펙」이다. 한 줄 본문도 통과한다.
- 사용자 결정(2026-11-14):
  - 범위 = 템플릿 + 스킬 + 코드 검사.
  - 검사 강도 = **경고만**. 판정은 바꾸지 않는다. 「게이트를 다섯 번째로 만들지 않는다」 교훈과 맞고, 열린 일감 대부분이 이 형식 이전이다.
  - #939(인터뷰 절차)·#908(완료 근거 관문)은 범위 밖이다. 문서에는 연결점만 둔다.
  - 수행 = 이 세션이 직접.

## 변경

- `docs/issue-spec.md`(신규) — 여섯 항목 `problem`·`triage`·`observe`·`scope`·`done`·`open`, 항목별 제목 열쇠말·작성법, 예시 본문. `PLAN.md` 에 15s 색인 행.
  - 사용자 제안 「초반 분류 3문」(기존 개선/신기능 · 레퍼런스 · 이식 소스)은 `triage` 로 넣었다.
  - pstack 의 `You see`·반증 가능한 완료 조건·질문 형태의 열린 결정은 `observe`·`done`·`open` 으로 넣었다.
- `master/plan_start.py` — `SPEC_SECTIONS`·`spec_missing(body)` 추가. 플랜 영역 밖의 **제목 줄만** 보고 열쇠말이 없으면 그 키를 돌려준다. `start_issue` 응답에 `spec_missing` 을 싣는다.
  - `assess`·`verdict`·`ok` 는 바뀌지 않는다.
  - `plan_tools.start` 와 8101 `plan_start_ep` 가 모두 `start_issue` 를 거치므로 `ax-projects`·`ax-client` 두 표면에 같이 실린다.
- `master/test_plan_start.py` — 4개 검사 함수 추가. 템플릿 문서의 예시 블록을 직접 읽어 누락 0 을 확인하므로 문서와 검출 규칙이 한 쌍으로 묶인다.
- 스킬 — `ax-plan` §2 에 `spec_missing` 처리(사용자에게 보이고 묻는다 · 스펙만 고치고 플랜 영역은 글자 그대로), `ax-redmine` §5 에 착수 일감은 템플릿으로 쓴다는 규칙을 넣었다.

## 안 한 것

- 판정 거절 — 사용자 결정으로 경고만 한다.
- 기존 열린 일감 본문의 소급 보강.
- `.33` 요청자 스킬(`ax-issue`) 문구 — 응답 필드는 같은 함수로 실리지만 스킬 지침은 이번 대상 목록 밖이다.
- 열쇠말은 부분 일치다. 「범위」는 「비범위」에도 걸리고, 다른 뜻의 제목(예: 「완료 조건 없음」)도 있다고 센다. 경고용이라 받아들였다.

## 검사

- `python3 master/test_plan_start.py` 44/44 rc0.
- `master/test_skill_conventions.py` 50/50 rc0.
- 공식 통합 `Ran 199 tests` OK.
- 전수 `master/test_*.py` 225파일: 11747/11748. 실패 1건은 `test_sandbox` 로, `AX_PROJECTS_ROOT` 미지정이라는 환경 조건 때문이다. 지정해 다시 돌리면 38/38 rc0.
- 실물(worktree 코드로 실제 Redmine 읽기). 기준선은 운영 `plan_start_tool(911)` 응답에 `spec_missing` 키가 없던 것이다.

  | 일감 | verdict | spec_missing |
  |---|---|---|
  | #911 | resume (ok) | 6개 전부 — 본문 제목이 「아이디어」·「연결할 기존 자산」·「볼 것」 |
  | #908 | plan_needed | triage·observe·scope·done — 「배경」·「열린 질문」 제목은 잡혔다 |
  | #939 | plan_needed | 6개 전부 |

- 운영 서비스 경로(재기동 뒤 `ax-projects:plan_start_tool`)는 마감 뒤에 확인한다.

최종 결과는 Redmine #911 마감 노트를 본다.
