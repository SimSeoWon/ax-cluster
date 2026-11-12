# 174 — #936 MotionForge 등록·클론·트윈 폐기

2026-11-13 · Codex · 운영 자료 삭제 및 문서 정리, 소스 코드 변경 없음.

## 사용자 결정과 범위

- 「936번 진행해」: 일감 착수 및 승인된 범위의 기록·마감·배달.
- 「깃티에 있는 저장소는 내가 제거했어.」: Gitea 삭제는 사용자 실행 보고다. 마스터가 삭제를 재실행하거나 원격 부재 검증을 했다고 기록하지 않는다.
- 「응 남은 클론도 모두 제거하고 백업 남길 필요없어.」: 남은 클론·트윈 폐기, 신규 백업 생성 안 함. 일감의 기존 백업 요구는 이 명시 지시로 제외했다.
- 정확한 삭제 목록과 .33의 미커밋 DefaultEditor.ini·미추적 Content/MotionForge/가 함께 없어진다고 제시한 직후 「응」으로 삭제 재확인을 받았다. 같은 질문에서 #709 선례대로 등록부 직접 정리를 승인받았다.
- 프로젝트 전용8건 폐기 마감·#759/#760 AX 공통 문제 보존 제안에 「응!」 승인.
- machines/win-main-33.md·win-worker-2.md·bc250-1.md의 MotionForge 현재 체크아웃 표기만 제거하는 계획에 「응」 승인. 나머지 오래된 Kimodo 표기·경로는 이번 대상이 아니다.

Redmine motionforge 프로젝트는 #759/#760과 종결 이력을 보존하려고 유지한다. 프로젝트 삭제·보관 전환·이슈 프로젝트 이동은 실행하지 않았다. 사용자가 승인한 이슈 보존을 프로젝트 전체 삭제로 확대하지 않았다.
UE 5.9 대체 범위는 사용자 배경 설명이며 엔진 기능을 별도로 검증하거나 대체 구현을 만든 작업이 아니다.

## 시작과 호출 근거

plan_start_tool(936): `verdict=plan_needed, ok=false`, 기존 플랜 없음. 사용자와 삭제·백업·일감 처분 범위를 정한 뒤 T1/T2를 등록했다.

issue_start_tool(936) 핵심 원문:

```json
{"ok":true,"issue_id":936,"branch":"issue/936","repo":"/home/sim/ax-cluster/.ax-issues/936","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"7e09726d9123bd35275a877afc9ef63e1e872cfa","lock":"acquired","author":{"client":"codex-mcp-client","family":"codex","authors":["codex"]}}
```

시작 응답에는 done·why가 없다. 편집·검사·커밋 위치는 응답 repo, 운영 checkout은 main이다.
RAG request_id=ecac78430ae84d6e80d9ce2f6696bac0, search_id=e9d8ed85081e45f6858bb5fe72dc7a73.
AXCluster/context/master/projects/logic.md 본문과 master/projects/logic.py·config.py·mcp_server.py를 대조했다.
프로젝트 등록 해제 전용 명령은 없고 remove_workshop은 워크숍 등록만 해제하며 디렉터리를 지우지 않는다. master.work.handover는 미머지 자료를 보존하는 계약이라 프로젝트 폐기 대체 명령으로 사용하지 않았다.
#709 노트의 수동 등록 해제 선례와 Registry.load/save 구현을 확인한 뒤 사용자 승인을 받아 같은 등록부 계약으로 제거했다. Registry.save는 raw의 usage 등 다른 설정을 보존한다.
원격 호출은 실제 구현을 읽은 master.client.bundle._ssh(host,user,cmd,timeout)을 사용했다. 스크립트는 확인한 호출의 고정 대상 승인용이며 별도 프로젝트 삭제 기능을 새로 만들지 않았다.

## 삭제 전 실측

`/home/sim/ax-cluster/.venv/bin/python /tmp/ax-936-inventory.py` rc0. 세 PC는 순서대로 조회했고 각 SSH rc0.

| 위치 | 실제 조회 |
|---|---|
| .2 janus, C:\trunk\MotionForge | 존재·일반 디렉터리(링크 아님), main...origin/main, status 변경0·stash0·로컬 branches에서 remotes 밖 커밋 출력0. AxConductor_MotionForge 존재(State=3). 경로를 포함한 실행 파일 프로세스 출력 없음 |
| .33 user, C:\trunk\MotionForge | 존재·일반 디렉터리(링크 아님), main...origin/main, ` M Config/DefaultEditor.ini`, `?? Content/MotionForge/`, stash0·remotes 밖 커밋 출력0. MotionForge 예약 작업·경로를 포함한 실행 파일 프로세스 출력 없음 |
| .43 sim, /home/sim/trunk/MotionForge | 존재, main...origin/main [behind 10], 변경·stash·remotes 밖 로컬 커밋 출력0 |
| 마스터 MotionForge/repo | main...origin/main, 변경0. main=6b59bf5158cfcc5b7719388a6d57636781cfa1bd. refs/ax/cleanup-base, refs/ax/pruned/task/20261009_0036_motionforge_aac50fe6/r1/{48589038,c7f3b7d3,df626954,f82f5e6c}, refs/ax/revise/0906d6fc 존재 |

remotes는 로컬 원격추적 ref와 비교했으며 이미 삭제된 Gitea를 fetch하지 않았다. 미push 없음 판정은 원격 현재 상태 보증이 아니다. 프로세스 조회는 ExecutablePath 필터이며 모든 에디터 내부 로드 모듈을 조사한 것은 아니다.

## 승인된 삭제와 되읽기

`/home/sim/ax-cluster/.venv/bin/python /tmp/ax-936-delete-approved.py` 전체 rc0. 고정 목록만 삭제했다. Windows·마스터 트윈의 링크 거부, Linux 클론의 심볼릭 링크 거부 조건을 두었다.

```text
{"host":"192.168.0.2","rc":0,"output":"ABSENT=C:\\trunk\\MotionForge\nABSENT=AxConductor_MotionForge"}
{"host":"192.168.0.33","rc":0,"output":"ABSENT=C:\\trunk\\MotionForge"}
{"host":"192.168.0.43","rc":0,"output":"ABSENT=/home/sim/trunk/MotionForge"}
{"registry":["ModularStage","NS","AXCluster","ServerTest"],"active":"AXCluster"}
ABSENT=/home/sim/ax-cluster/MotionForge
```

.33 미커밋·미추적 자료, 마스터 트윈의 context·ontology·responses·리뷰·DB·로컬 미러·보존 ref를 포함해 전체 제거했다. 백업 파일·bundle·tgz를 만들지 않았다. Gitea 삭제는 사용자 보고이고 GitHub 저장소 삭제는 승인된 고정 목록에 없으므로 실행하지 않았다.
삭제 뒤 MCP list_projects_tool: MotionForge 없음, active=AXCluster, problems=[]. projects.yaml 직접 되읽기에서도 projects4개·active·usage.raw_retention_days=30 보존 확인.
실행과 결과는 #936 노트에 기록했고 redmine_get_issue로 되읽었다. T1은 이 실제 부재·등록 결과를 근거로 완료 처리했다.

## 열린 일감의 개별 처분

각 이슈 본문을 먼저 읽었다. 사용자 승인 뒤 redmine_note로 개별 사유를 기록하고 완료·100, 8건 모두 get_issue로 확인했다. 구현 성공을 의미하는 완료가 아니라 폐기 종결임을 각 노트에 적었다.

| 이슈 | 판단 근거·결과 |
|---|---|
| #694 | kimodo.cpp 원본 추종 스크립트·스킬은 폐기한 프로젝트의 서브모듈 유지보수. 폐기 |
| #697 | 옛 KimodoMotion_WebUI에서 이관한 포즈 해부학 API 기능. 폐기, 분산 구현 완료 주장 없음 |
| #703 | 프로젝트 생성 요청 자료형 검증. 폐기 |
| #704 | 위 기능의 codex 분산 작업. 폐기 |
| #707 | 삭제한 플러그인의 follow-upstream.ps1 MAX_PATH 수정. 대상 소멸로 폐기 |
| #755 | 프로젝트 뷰포트 기능. 기존 cancelled work 이력과 프로젝트 폐기로 종결 |
| #758 | 비SOMA 리타깃 제품 결정. 프로젝트 소멸로 폐기 |
| #761 | 원격 브랜치·로컬 보존 ref 정리. 원격은 사용자 삭제 보고, 클론·로컬 ref는 실제 전체 삭제 관측. 종결 |
| #759 | 에디터 런타임 검증 공백. 프로젝트와 별개인 AX 공통 문제로 보존. 신규·0 확인 |
| #760 | 부분 취소 work 및 ⑦ 커밋 보존 문제. AX 공통 문제로 보존. 신규·0 확인 |

두 보존 이슈의 현행 코드상 재현·해결 여부를 이번에 판정하지 않았고 새 유지 노트를 반복해서 달지 않았다. 기존 motionforge 프로젝트에 이력과 함께 남겼다. AX 프로젝트로 이동했다고 주장하지 않는다.
#771은 이전 세션에서 이미 폐기 종결됐다는 인수인계와 기존 정리 이력이 있어 중복 조작하지 않았다.

## 문서·검사·한계

승인된 세 machines 문서에서 MotionForge 현재 체크아웃 표기만 제거했다. 삭제한 트윈 안 기록을 다시 복원하거나 기존 역사 리포트의 MotionForge 언급을 지우지 않았다.
소스 변경이 없어 별도 가짜 삭제 테스트나 Python 정적 검사를 추가하지 않았다. 실제 경로 부재와 MCP 등록 조회가 운영 검증 근거다.
git diff --check rc0. 공식 통합은 `/tmp/ax-936-checks.sh`에서 `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` 실행, rc0·`Ran 194 tests in 209.308s`·`OK`. 로그 `/tmp/ax-936-integration.log`.

이 세션 파일: ~/.codex/sessions/2026/11/12/rollout-2026-11-12T23-17-23-01a1d01e-d294-7680-8cf8-661b8454f17f.jsonl.
삭제 실행 자체의 실패는 관측하지 않았다. 임시 스크립트와 검사 로그는 /tmp 경로에 있으며 코드 기능으로 배포하지 않는다.

최종 결과는 Redmine 마감 노트.
