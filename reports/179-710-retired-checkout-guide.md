# 179 — #710 삭제된 Kimodo 체크아웃 안내 정리

2026-11-14 · 지휘 Codex · 로컬 Codex 서브에이전트 수정, 주 지휘자 diff 검토·검사·마감·배달.

## 사용자 승인과 작업 위치

- 사용자 「710 진행하자」. 두 군데 삭제·ModularStage/NS Documents 경로 유지·단독 로컬 서브에이전트 수행의 구체안을 보여 준 뒤 「응!」 승인. 자동 로드 문서의 사전 동의 조건 충족.
- `plan_start_tool`: `verdict="plan_needed", ok=false`. RAG 검색은 관련도가 낮은 결과여서 근거로 단정하지 않고 현재 문서·등록·#709 노트와 직접 대조했다. T1/T2 합의 후 플랜 등록·시작.
- `issue_start_tool` 원문 주요 값: `repo="/home/sim/ax-cluster/.ax-issues/710"`, `checkout="/home/sim/ax-cluster"`, `branch="issue/710"`, `start_rev="6d021699aa24a2779e4bb646e7310087014dfd42"`, `lock="acquired"`, 작성 계열 `['codex']`. 운영 main 편집 없이 응답 repo에서 수정·검사·커밋.
- 세션 `~/.codex/sessions/2026/11/13/rollout-2026-11-13T23-55-29-01a1d568-1144-7ac1-9e5c-3c632e5f7f7a.jsonl`.

## 항목별 대조

1. **KimodoMotion_WebUI 현재형 체크아웃 안내 — 낡은 표기.** `machines/win-main-33.md`의 Identity 체크아웃 목록과 Unreal projects 표에 남아 있었다. #709 완료100 노트는 .33 두 옛 클론 삭제(2026-10-09)와 마지막 GitHub 저장소 삭제(11-12)를 확인한다. 현재 `list_projects_tool` 등록은 ModularStage·NS·AXCluster·ServerTest이며 Kimodo는 없다. 승인된 두 항목만 제거.
2. **ModularStage·NS 경로를 trunk로 바꿔야 한다 — 현재 근거 없음.** 등록의 .33 경로는 각각 `C:\Users\USER\Documents\ModularStage`, `C:\Users\USER\Documents\NS`로 문서와 일치한다. 일감 본문의 이전 예정만으로 경로를 바꾸지 않았다.
3. **sim-desktop.md·온보딩 예시도 수정해야 한다 — 이번 확인에서 불필요.** 앞의 두 경로 및 AXCluster 별도 `C:\trunk\AXCluster` 역할이 현재 등록과 맞는다. 과거 Kimodo 실증에 대한 역사적 서술도 지우지 않았다.

## 변경과 검증

- 커밋 `2c557a8`: `docs: remove retired Kimodo checkout from user PC guide (#710)`.
- 변경은 `machines/win-main-33.md` 1파일, 1추가·2삭제. 목록에서 `,KimodoMotion_WebUI` 제거, 표의 해당 프로젝트 한 행 삭제. 나머지 문구·경로 불변을 diff로 검토. `git diff --check` rc0.
- 실행 코드·검사 코드는 변경하지 않아 별도 회귀 테스트를 작성하지 않았다. 공식 통합 검사는 기존 명시 목록을 실행한다.
- 명령: worktree에서 `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`. 알려진 sg gitea 그룹 차단을 피하도록 해당 명령만 샌드박스 해제 승인으로 실행. 로그 `/tmp/ax-710-integration.log`.
- 공식 통합 **195건, 210.233초, OK, rc0**. 실행 코드 변경이 없어 Python 정적 검사 대상은 없다.

## 배달 계약과 한계

`machines/README.md`와 실제 `master/client/home_guides.py`를 대조했다. .33 홈 안내서는 `C:\Users\USER\CLAUDE.md` 복사본이므로 프로젝트 배달만으로 갱신됐다고 판단하지 않는다. 정본 `master.client home-guides --host=192.168.0.33 --apply`가 원격 기존 파일을 `.bak-<timestamp>`로 백업하고 DIFF 복사본만 쓴 뒤 SHA256을 되읽는다. .33의 AGENTS.md는 absent_ok라 새로 만들지 않는다. 이 작업에서는 홈 안내서 문구만 바꾸며 게임 트리·브랜치·등록 경로를 변경하지 않는다.

마감 뒤 홈 가이드 반영·서비스 신선도·프로젝트 배달 결과 및 `issue_finish`의 repo/done/why는 Redmine #710 최종 노트가 정본이다. 자동 리뷰 결과는 미확인이다.

최종 결과는 Redmine 마감 노트.
