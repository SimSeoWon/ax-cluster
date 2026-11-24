# 209 — #839 운영 스냅샷: Redmine·서비스 상태를 doc_sync 근거 파일로

> 2026-11-24 · Redmine `#839` · 마일스톤 8 — 개선·확장 · 작업 브랜치 `issue/839` · 시작 `1fec594`
> 진행: 착수 전 인터뷰(분류 신규 기능, 단일 플로우) · 로컬 서브에이전트(T1·T2 코드) · 지휘 Claude(실물·등록·T4)

## 1. 왜

`doc_sync` 는 등록된 근거 **파일**만 읽는다. 문서 계약(`docs/document-sync.md`)은 「Redmine 결과를 반영하려면
먼저 파일로 준비해 근거에 넣는다」고 적어 두었지만, 그 파일을 만드는 도구가 없었다. 그래서 인수인계서의
「결정 대기 #…」·재기동·배달 결과 같은 사실은 근거 없이 남았다.

10-30 사용자 결정(#839 노트): 방식 (a) **스냅샷 파일**. (b) live 조회는 근거가 커밋에 묶이지 않고 doc_sync 가
토큰·네트워크를 다루게 돼 기각. 착수 세부(범위·시점·위치·민감 제외)는 이번 인터뷰에서 정했다.

#838 에서 넘어온 나머지 — ① 영향 문서 탐지는 `3123389` 로 끝났고, 10-30 관찰(「등록 근거만큼만 본다」)은
#1016 인벤토리로 풀렸다. ③ 보호 문서 4개 실증 · ④ 교차 계열 검토는 이번 비범위(마감 때 새 일감으로 뗀다).

기준선(C1, LLM 0, worktree `1fec594`): `plan --since 9f5e6be` → `handoff` 는 `no-registered-dependency-change`
로 제외, 근거는 `master/skills/ax-handoff/SKILL.md`·`docs/orchestrator-rules.md` 2개뿐.

## 2. 정한 것 (인터뷰)

- 범위: Redmine 열린 일감 **메타데이터** + 운영 상태(상주 서비스 · 마스터 HEAD · 워커 배달 리비전). 본문·노트는 싣지 않는다.
- 시점: doc_sync **밖**의 별도 명령을 사람이 손으로 돌리고 커밋한다. doc_sync 는 네트워크 0 그대로.
- 위치·등록: `docs/snapshots/` 두 파일, **`handoff` 근거에만**. 보호 문서에 등록하면 스냅샷 커밋마다 후보가 된다.
- 열린 결정 두 개는 추천안대로: 못 닿으면 파일은 쓰되 rc 1 · 이름 `master.ops_snapshot`.

## 3. 만든 것

| 커밋 | 내용 |
|---|---|
| `5486733` | `master/ops_snapshot.py`·`master/test_ops_snapshot.py`(대역 18건) · `tests/integration/checks.json` 등록 |
| `8d81b49` | 첫 실물 스냅샷 두 장 · `docs/document-registry.json` handoff 근거 2→4 |
| `c726506` | `docs/document-sync.md`·`ax-docsync` 스킬 — 사용법과 「handoff 대상이면 plan 전에 스냅샷」 |

- Redmine: 공개 읽기 API(키 없음, `issue_snapshot` 과 같은 길) · 100건씩 페이지 · 받은 수와 `total_count` 를 둘 다 보인다 ·
  아이디어 버킷은 건수만 · 프로젝트는 `ax-cluster` 고정(서브에이전트 초안은 마운트를 따랐다 — 스펙대로 고정으로 고쳤다).
- 서비스: `service_freshness.RESIDENT` 의 셋을 `systemctl show`(LoadState·ActiveState·SubState·ExecMainStartTimestamp).
- 워커: `bundle.workshops` + `delivered_stamp` + `compare_version` 재사용. 무거운 `probe` 는 돌리지 않는다 —
  `delivered_stamp` 가 필요한 것은 host·user·path·windows 뿐이다. 「못 닿음」과 「판정 unknown」을 가르려고
  도장을 먼저 읽어 `config.json` 을 워커마다 두 번 읽는다(받아들인 비용).
- 못 닿은 원천은 `닿지 않았다: 사유` + rc 1. 출력은 절대 경로·메일·`token=` 꼴을 가린다.

## 4. 실물 확인

- C3 (`5486733` 에서, rc0): 열린 51건 = API `total_count` 51 · 아이디어 37 · 상주 셋 active/running ·
  워커 `.2`·`.33`·`.43` 리비전 실림. 출력에 `/home/`·`C:\`·메일·토큰 0건.
  워커는 `drifted 1` 로 찍혔다 — 생성기 커밋이 아직 배달 전이었고, 이 명령은 **돌린 체크아웃의 HEAD** 와 대조한다.
  그래서 갱신은 운영 체크아웃에서 마감·배달 뒤에 돌리는 것으로 문서에 적었다.
- C4: 스냅샷만 바꾼 커밋(스크래치 클론, `8d81b49` 위) → `plan --since 8d81b49` 가 **`handoff` 하나만**
  `registered-dependency-changed` 로 골랐다(나머지 7개 제외). 대역 생성기 draft(LLM 0) 프롬프트 38,621자에
  두 스냅샷 경로·「열린 일감: 51건」·서비스 행·워커 행이 실렸다.
- 등록부 변경 범위(`1fec594..8d81b49`)로는 8개 문서가 모두 `registry-changed` 로 잡힌다 — 기존 동작이고 의도와 맞다.

검사: `test_ops_snapshot` 18/18 · `test_doc_sync_registry`·`test_doc_sync_cli`·`test_skill_conventions` OK ·
공식 통합 220/220 OK · sweep 246파일 12769/12769 · unittest 633/633 rc0(첫 sweep 은 새 검사 미등록으로 `test_integration_coverage` 실패 →
사용자 승인으로 `checks.json` 에 추가).

## 5. 남는 것

- 스냅샷은 손으로 갱신한다 — 낡을 수 있다(받아들인 트레이드오프). 자동 주기·`issue_wrapup` 연동은 비범위.
- Windows 워커의 scp 판독은 이번 실물에서 `.2`·`.33` 둘 다 통과했다.
- ③ 보호 문서 4개 실증 · ④ 교차 계열 검토는 마감 때 새 일감으로 뗀다(버전은 그때 묻는다).
- 기록 중 내 실수 하나: 기준선 첫 호출에 없는 `--json` 옵션을 줘 rc2 — 옵션을 빼고 다시 돌렸다.

최종 결과는 Redmine #839 마감 노트가 정본이다.
