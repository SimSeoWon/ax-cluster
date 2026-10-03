# 90. R5 재검토와 색인기 테스트 격리·배포

2026-10-04 · Codex 마스터 · 사용자 R5 검토→원인 조사→수정→로컬 방식→드라이런→
커밋·푸시·배포→R5 상태 반영→문서·레드마인·인수인계 갱신 승인.

## R5의 대상과 현재 판정

R5는 골조 커밋 `493601d78f12d0b3fcf7ec2615969f76c1b329c9`의 리뷰다.
당시 함수의 `NotImplementedError`와 테스트 `pass`·`[PSEUDO]` 지적 10건은 유효했다.
후속 두 라운드 구현으로 모두 반영됐으므로 현재 main의 미해결 결함으로 다시 고치지 않았다.

| 항목 | 구현 근거 |
|---|---|
| R5-1 | `_branch_for` 레지스트리 조회·main 폴백 `053200a` |
| R5-2 | 미스탬프 문서가 남으면 커서 전진 차단 `a28c6a8` |
| R5-3~5 | 출력 정규화 지문·직전 지문 비교·detail 접두사 `cb4bb47` |
| R5-6~7 | infer의 반복 REJECT·submit_fail 지문 연결 `32a1e0b` |
| R5-8 | 배달 브랜치 회귀 `e0e8e7e` |
| R5-9 | 옛 스탬프 차단·새 스탬프 전진 회귀 `4e9131e` |
| R5-10 | 지문·반복·길이 제한·infer 연결 회귀 `3453463` |

사용자 「수정해줘」는 재검토 결과에 따라 리뷰 상태를 정리하는 승인으로 실행했다.
`fix_index.set_status`로 R5-1~10을 `applied`에 기록하고 각 구현 커밋·검증 근거를 저장했다.
재조회 `applied:10`, 다른 리뷰 status 불변 확인. 상태는 트윈의 런타임
`AXCluster/fixes/index.json`에 있으며 소스 커밋과 별개다. 원본 리뷰 문서는 보존했다.

## 드러난 테스트 의존과 원인 실증

첫 관련 검사에서 version 27/27·revise 64/64는 통과했으나 indexer는 101/103이었다.
실패는 [3] 「커서가 최신이면 다시 걷지 않는다」와 「최신 사유를 보존한다」 두 칸이었다.
초반 `process_event`가 가짜 Git·색인기를 받으면서 `synth_run`을 생략해 실제 브로커 합성을
실행했다. 합성 실패로 source_commit 스탬프가 안 생겨 커서가 멈췄고, 다음 검사가 최신 커서를
전제로 하므로 연쇄 실패했다. 운영 consumer의 스탬프 가드는 계약대로 작동했다.

환경변수 없는 첫 실행에는 AX_PROJECTS_ROOT 오류도 있었다. 원인 조사에서 임시 프로젝트·
Gitea 루트를 설정하고 외부 호출을 차단해도 같은 101/103이었다. 성공 문서 스탬프를 찍는
가짜 합성기를 메모리에 주입한 비교는 103/103이었다. 환경변수 설정만의 해결로 판단하지 않았다.

RAG `search_context_tool`의 test_indexer 문서를 현재 소스와 대조하고, 원전 AgentTest의
`tests/test_revision_watermark.py`에서 frontmatter·stem 그룹 스탬프 계약을 참조했다.
사용자가 로컬 방식을 선택한 뒤 구현 서브 에이전트가 `master/test_indexer.py` 한 파일만 수정:
기존 `synth_writes`를 모듈 범위로 옮겨 성공 경로 6곳에 명시적으로 주입했다.
실패·NoChange·맞춤 합성·합성 비활성화 케이스는 유지했다. 메인이 diff와 실행 결과를 검증했다.

## 검사

- 임시 프로젝트·Gitea 루트, socket.connect audit 차단으로 직접 실행 **103/103**.
  동일 manifest의 `run_check` 경로도 **103/103**, 두 실행 모두 연결 시도 **0건**.
- 전체 드라이런:
  `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`.
  **12모듈, 560건, rc0** (14+77+32+7+36+51+64+103+27+11+123+15).
- 첫 전체 실행은 source_scope에서 실패: consumer의 Git wrapper가 `sg gitea`를 부르지만
  기본 샌드박스에 그룹이 없고 `Cannot open audit interface - aborting.`을 반환했다.
  전용 `/tmp/ax-r5-integration-dryrun.sh` 실행 승인을 받아 동일 검사 재실행으로 통과했다.
  운영 코드를 패치하거나 권한 검사를 우회하지 않았다.
- 배포 후 R5 재검토에서 관련 manifest 검사 **194/194** (version 27·indexer 103·revise 64).
  `git diff --check` 통과, 변경 밖 파일 없음.

## 커밋·푸시·배포

사용자 「커밋 푸시 배포하자」로 `b53fd8469f4ddc8528959db13c6087eeb0ca077a`
(`test: isolate indexer checks from synthesis broker`) 커밋·Gitea main push.
`git ls-remote origin refs/heads/main`으로 동일 해시를 확인했다. 이 읽기 조회도 샌드박스가
SSH를 막아 승인된 재실행으로 확인했다.

AXCluster 세 워커 `.43`·`.2`·`.33`의 main/clean을 확인하고
`fetch origin main → merge --ff-only origin/main`으로 같은 b53fd84에 맞췄다.
깨끗한 마스터에서 `plan → deliver → check AXCluster`, 최종 **3/3 OK**:
프로젝트 스킬·payload 10개·태그·배달 출처 HEAD 일치, 이후 워크숍 source clean **3/3**.
`.2`의 기존 Claude 로컬 MCP 대조 경고와 홈 중복 스킬 주의는 남지만 Codex 프로젝트 설정은 통과했다.
서비스 코드 수정은 없어 재시작하지 않았다. 서비스에 반영된 Codex 준비 코드는
00f8532이며 ax-projects의 마지막 재시작 실측은 00:09:13(리포트 89).

이 배포에 3e01ea9의 기존 마감 문서 커밋도 함께 포함됐다. 다른 프로젝트나
`.43 ~/ax-cluster` 관리 사본은 이번에 맞추지 않았다. 새로운 work 등재·워커 파견은 없었다.

## 문서·레드마인·다음 세션

사용자 요청으로 README·repo/home 정본 CLAUDE/AGENTS·온보딩·Windows 실행 문서·
공용 규칙·모듈 색인·리포트·기존 인수인계서를 최신화했다. 홈의 두 심볼릭 링크는 보존했다.
문서의 고정 결과는 이 보고서에 모으고 실행 지침에서는 검사 방법과 정본 링크를 안내한다.

Redmine #716에 이번 R5·검사·커밋·배포·문서 갱신 근거 노트를 남기고 재조회로 검증했다.
상태는 신규로 유지했다. 이번 조회에서 #716·#700·#701·#720·#721은 신규,
#718·#719·#722는 완료다. 코드 반영과 Redmine 완료 판정을 혼동하지 않는다.

문서 갱신 뒤 사용자 「커밋해줘!」로 문서13개 커밋을 승인했다. 문서 검사에서 발견된 인계서의
줄 끝 공백4곳을 정리하고 커밋한다. 푸시·재배달은 별도 승인 없이 실행하지 않는다.
다음 작업은 [인수인계서](../docs/orchestrator-handoff.md)와 Redmine을 대조한 뒤 사용자가 선택한다.
#720 한도 분류·#721 Claude 인증 만료 검사, Windows .ax 쓰기 실패 근본 원인,
새 Codex 모드의 큐 파견~finalize 완주와 다중 파일 조각 워커 완주는 아직 별개다.
