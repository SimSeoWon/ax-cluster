# 208 — #1016 doc_sync 인벤토리 근거: 새 모듈이 문서 최신화에서 빠지지 않게

> 2026-11-24 · Redmine `#1016` · 마일스톤 8 - 버그/개선 · 작업 브랜치 `issue/1016` · 시작 `6cfbdcc`
> 진행: 착수 전 인터뷰(분류 버그) · 로컬 서브에이전트(T1~T3) · 지휘 Claude(T4)

## 1. 왜

`doc_sync` 는 등록부의 고정 `evidence` 만 읽었다. `--since` 도 바뀐 경로를 등록 `target`·`evidence` 와의 교집합으로만 대조했다(`registry.py` 149-150).
readme·modules 의 근거는 7개 파일뿐이고 운영 모듈은 271개다. 그래서 다른 모듈이 바뀌면 두 문서는 `no-registered-dependency-change` 로 조용히 빠졌다. `--id` 로 강제해도 그 모듈은 프롬프트에 실리지 않았다.
#982 때는 `6cfbdcc` 에서 등록부에 파일 4개를 손으로 넣어 우회했다. 그 우회는 다음 일감의 모듈을 막지 못한다.

빈도 실측(`8b516b2..HEAD`): `master` 를 건드린 커밋 252 · 새 운영 모듈·스킬 61 · 등록부 수정 커밋 2.

기준선(LLM 0):
- `plan --since bb3d39d --until 91a928a`(`master/redmine.py` 변경) → readme·modules 모두 제외
- `plan --since c005e5f --until c7a34c5`(`master/issue_flow.py`·`issue_infra.py` 변경) → readme·modules 모두 제외

## 2. 정한 것 (인터뷰)

- 분류는 버그다(사용자 결정). 지휘자 가설은 「설계대로라 수정」이었다.
- 문서 계약 「자동 검색한 모든 파일을 LLM에 보내지 않는다」는 「전문을 무더기로 보내지 않는다」는 뜻으로 고친다. **결정적 인벤토리만 자동**이고 전문은 등록된 것만이다.
- 미문서화 모듈 감지는 **목록만** 낸다. 두 README 에 이름이 없는 모듈이 60개가 넘어, 거부로 두면 늘 막히기 때문이다.

## 3. 만든 것

| 태스크 | 커밋 | 내용 |
|---|---|---|
| T1 | `9b139a4` | 등록부 `inventory: true`(readme·modules) · 가상 근거 `inventory:master` · 새 사유 `inventory-source-changed` · 문서별 `undocumented` |
| T2 | `ba5a0ed` | draft 프롬프트의 미언급 모듈 정보 구획 · plan 출력 `undocumented_count`·`undocumented` · apply 왕복 검사 |
| T3 | `649123e` | `docs/document-sync.md`·`ax-docsync` 스킬 계약 문구 |

인벤토리:
- 운영 모듈 경로 + docstring 첫 줄(테스트·`__pycache__`·심볼릭링크 제외) · 스킬 이름·설명 · 두 `mcp_server.py` 의 `@mcp.tool()` 함수 이름(AST, import 없음).
- 모듈 271 · 스킬 12 · MCP 도구 68 · 25,896자. 두 번 수집하면 해시가 같다.
- `apply.py` 는 고치지 않았다. 재수집해 근거의 개수·경로·해시를 대조하므로, 인벤토리 원천 docstring 이 draft 와 apply 사이에 바뀌면 「오래되거나 변조된 근거」로 거부된다.

새 사유는 기존 사유가 `no-registered-dependency-change` 이고 인벤토리 문서일 때만 붙는다. 기존 사유·우선순위와 비인벤토리 문서 동작은 그대로다. 원천은 경로 모양으로 판정해 삭제된 모듈도 잡는다.

미언급 판정: 전체 경로·`master` 상대 경로·점 표기가 부분 문자열로 있거나, 파일 이름이 단어 경계로 있으면 언급으로 본다. 현재 readme 155/271 · modules 82/271 · 둘 다 미언급 62.

## 4. 검증 (LLM 0)

- C1: 기준선 두 범위에서 readme·modules 가 `inventory-source-changed` 로 포함됐다. matched 는 각각 `master/redmine.py`, `master/issue_flow.py`·`master/issue_infra.py`. 나머지 6문서는 종전대로 제외다.
- C2: 프롬프트에 `inventory:master:112 master/issue_flow.py …`·`inventory:master:213 master/wayfinder.py …` 줄과 미언급 구획이 있다.
- C3: 대역 생성기(unchanged)로 만든 수정안이 apply 미리보기를 통과했다(ok · 변경 0). stale 거부는 단위 검사로 확인했고, 운영 소스를 바꾸는 실물 시험은 하지 않았다.
- C4: `test_doc_sync_*` registry 18 · draft 15 · cli 10 · apply 20 · `test_skill_conventions` 54/54 · `master.sweep` 245파일 12,769/12,769 · 공식 통합 219건 실패 0.

## 5. 남는 것

- 미언급 목록은 정보일 뿐이다. LLM 이 목록을 보고도 `unchanged` 로 판정하는 경우는 사람의 diff 검토가 잡는다.
- 프롬프트가 크다 — readme 224,482자 · modules 244,257자. 늘어난 몫은 인벤토리 약 26K자이고 나머지는 원래 있던 본문·등록 근거 전문이다.
- 미언급 62개 모듈을 실제로 README 에 반영하는 일은 이번 범위가 아니다.

최종 결과는 Redmine `#1016` 마감 노트에 있다.
