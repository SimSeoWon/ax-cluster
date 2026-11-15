# 197 — #969 자동 리뷰 「중간」 지적 중 실제 결함 22묶음(53건) 수정

2026-11-15 · Claude · #965 마감 뒤 같은 세션에서 수행.

## 사용자 지시와 범위

- 「자동리뷰에 나머지 지적사항들 먼저 고치고싶어」 → 분포(열린 283건: 높음 1 · 중간 76 · 낮음 206) →
  「3번으로 대조해서 표로 보여줘」 → 높음·중간 77건을 코드와 대조(main `810a3d5`).
- 대조 결과: **이미 고쳐짐 12 · 오탐 12**(근거 노트와 함께 dismissed — 「높음」 R381-1 은 오탐: `plan_tools.py:36`
  에 import 가 있었다) · **실제 결함 53건 = 22묶음**. 같은 결함을 리뷰 두 번이 겹쳐 지적한 쌍이 많았다.
- 「응 A·B 처리하고 C는 일감 등록해줘」 → #969. 인터뷰 bug → 조사 → 명세(22묶음 전부, 「큼」 1~5 우선,
  낮음 206건 비범위) → 재현 → 파급(4-a 방식 결정) → `ax:spec` → 플랜 T1~T8 · C1~C5.

## 재현 먼저 (「큼」 1~5)

저장소 밖 스크립트(scratchpad `repro969.py`)로 고치기 전에 다섯 다 재현했다: ① 수정 분류 인터뷰에서 건너뜀
노트 하나가 빠지면 재현·파급 기록이 양쪽 다 거절되는 교착 ② `plan_start` 재료 수집 예외가 시작 판정 전체를 죽임
③ 키가 빠진 제안 JSON 이 `KeyError` ④-a ssh 「Permanently added」 경고 한 줄이 #929 의 「stderr 있으면 비정상」에
걸려 정상 종료를 막음 ④-b ping 을 **실행하지 못했는데** ssh 실패와 합쳐 「꺼짐=True」 ⑤ 기동 복구가 재통보
표지를 먼저 지우고 저장해, 그 사이 죽으면 표지·보낸 기록이 둘 다 없는 조각이 남음.

## 바꾼 것 (`issue/969`)

| 커밋 | 태스크 | 내용 |
|---|---|---|
| `c14a446` | T1 ① | `_next` 가 분류 문서가 적용하는 단계만 낸다 · 빠진 건너뜀 노트는 `problems` 한 줄 |
| `9f63965` | T2 ②③ | 재료 실패는 `materials.error` · 필수 키 없는 제안은 `broken` → `ProposalError` |
| `6940a94` | T3 ④ | ssh 세 명령에 `-o LogLevel=ERROR`(계약 유지) · ping 실행 실패는 `ShutdownError`(확인 불가), 시간 초과는 무응답 그대로 |
| `4800bd7` | T4 ⑤ | 복구는 표지를 지우지 않고 `resend=True` 로 재통보 · 거절 건은 생략 집계 |
| `28819d5` | T5 6~10 | synth claude 레인 고정 트리·OSError · 범위 노트 재시도 상한 5 · relay store 원자 순번·잠금 읽기·archive 잠금·객체 아닌 줄 · relay agents 예외 시 프로세스·파이프 정리 · master_local 기본 명령 권한 대조·손상 TOML |
| `a4564ba` | T6 11~16 | plan_metrics 손상 이전 본문 · spec_block 첫 줄 플랜 제목 · md `problem` 없는 YAMLError · 머리말 뒤 개행 · 온톨로지 `kind` enum(복수형) · conductor 두 개 JSON 한 줄(신규 `test_skill_scripts.py`) |
| `dd293ff` | T7 17~22 | 분리된 worktree 취소 거절 · ssh 실패 stderr 로그 · prefer `:latest` · submission 잠금 · freshness 테스트 유닛 계정 홈 · related_classes 인라인 주석 |

## 결정과 그 근거

- **4-a 는 계약을 지키고 경고만 껐다**(사용자 1번 선택). `test_bc250_shutdown:218` 의 「rc=1 이어도 stderr 있으면
  비정상」은 #929 가 일부러 정한 fail-closed 다 — 리뷰 권고(stderr 무시)를 따르면 그 계약을 뒤집는다.
  실물 `.43`: 기본 ssh 는 stderr 에 경고, `LogLevel=ERROR` 는 빈칸, 원격 rc 는 둘 다 1.
- runner 의 stderr 는 반환이 아니라 **로그**로 보존했다 — 호출자가 stdout 끝의 `RESULT:` 줄을 읽는다.
- 회귀 검사는 결함마다 수정 전 실패를 확인했다. T6 은 이전 커밋 임시 worktree 에 새 테스트만 복사해 대조했다
  (`test_skill_conventions` 는 고칠 자리가 그 테스트 파일 자체라 같은 패턴의 분류 문서 검사로 확인).

## 측정

- 전수 `master.sweep`: 235파일 · 12206/12206(형식 A·B, 종전 12147 + 59) · unittest 540/540 · 실패 0 · 29.6초.
- 공식 통합: Ran 209 OK(208 + 신규 `test_skill_scripts`) · 병렬 25.6초.
- `repro969.py`: ①~⑤ 정상 동작으로 바뀜(④-a 는 스크립트가 경고를 직접 넣으므로 그대로 — 실물로 확인).
- 리뷰 지적 53건 `applied`(커밋 해시·`issue/969`). 열린 지적은 「중간」 0 · 「낮음」 206 남음.

## 남은 것

- 「낮음」 206건 대조 — 비범위(사용자 결정). 마감 뒤 별도 일감으로 등록한다.
- 재기동(task-queue·projects·broker)·세 워커 배달(`client_mcp.py`)·`master-local --check` 는 마감 wrapup 몫.

최종 결과는 Redmine #969 마감 노트.
