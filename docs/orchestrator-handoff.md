# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **갱신 시각**: 2026-10-03 12:45 KST — Codex, AXCluster 워커·원격 Codex 실증과 기억 기록
- **지휘 도구 / 세션**: Codex (Claude 인계 수령)
- **상태**: 원격 파일 수정 실증 통과. §2 재합성 **미완** 정정은 보존. 브로커 .33 운영 반영·3노드 동시 추론 확인
- **관련 일감**: `#711`(ax-cluster 자신을 파이프라인에 태운다) · `#712`(파이썬 그래프, 구현됨) ·
  `#713`(LLM 사용량 통합 + 웹 UI) · `#714`(스풀 고아 배치) · `#715`(병렬 합성·브로커 분배, 구현됨)
- **워커 지휘자 모드**: `codex` (`~/.cache/ax-dispatch/mode.json` 재조회)
- **마운트**: `AXCluster` (트윈 `~/ax-cluster/AXCluster/`, project_id `Sim/ax-cluster`)
- **HEAD**: `7ec14f5` (사용자 커밋 승인으로 Python 자동 리뷰 7파일 커밋). Gitea origin/main push 완료; 브로커·원격 설정 문서 변경은 미커밋

## 1. 오늘의 사용자 결정 (2026-10-03)

- 원격: **Gitea 정본**(`origin`) + **GitHub 푸시 미러**(Gitea 가 커밋 시 동기화). 🔴 **GitHub 직접 push 금지** —
  마스터 `github` 원격은 push 비활성. `.43` 도 `origin` = Gitea
- ax-cluster 를 프로젝트로 등록 — 트윈 이름 **`AXCluster`**(ax-cluster 는 저장소 루트와 겹쳐 `test_sandbox` 오탐)
- AXCluster profile: kind `code`(`.py`) · purpose `rnd` · AX 작업 요청자 = **마스터 세션**
- 합성 프롬프트: 비UE 의 긴 `.py` 는 **ast 요약본**(함수 본문 생략, 독스트링·주석 유지)
- 파이썬 그래프: 겹치는 클래스 이름만 모듈명(`master.verdict.Verdict`) · 테스트 파일은 클래스 그래프 제외 ·
  `related_classes` 의 `이름: ?` 는 그래프에 정확한 이름이 있을 때만 채움(**전 프로젝트**)
- 🔴 **컨텍스트 문서는 검색 보조다 — 작업 판단 근거는 실제 코드**
- 사용량 표시는 **토큰만**. `.33` 등 세션 기록은 로컬에 두고 마스터가 가져온다
- `.2` 상주 모델 = `gemma4:e4b`(종전 `qwen2.5-coder:14b`) — 합성을 두 노드에 나누려고
- 🔴 **AX 클러스터 기능 작업(AXCluster)에서는 `.33` 도 워커로 쓴다** — 등록·배달·진단 파일 수정 실증까지 확인(§3)

## 2. AXCluster 재합성 — 🔴 미완 (11:58 실측으로 정정)

- 색인기는 전체 따라잡기를 **하지 않았다** — push 이벤트 범위(`306576e→c657a7a`)의 **바뀐 소스 106건만**
  합성하고 끝났다. 문서 **76 / 347그룹** · 워터마크(`last_indexed_commit`) **비어 있음**
- 품질: `related_classes` 가 전부 `?` 인 문서 **69% → 25%**(76개 중 19) — 그래프·요약본 효과
- 병렬은 실물 확인됨: 11:44~ 브로커 `[route]` 가 `bc250` 20 · `rtx3060` 14 로 나눴다
- **남은 일**: 누락분 합성 → index. 색인기와 겹치지 않게 **push 를 멈춘 상태에서**:
  `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard AXCluster --confirm --only synth`
  (onboard 합성은 누락분만 · 동시 N 은 상주 노드 수) → `--only index`
- [주의] 색인기 타이머(10분)·push 이벤트도 합성을 띄운다 — 잠금이 없어 겹칠 수 있다.
  멈추려면 마운트를 옮겨야 한다(`systemctl stop` 은 NOPASSWD 밖)

## 3. 다음 작업 (순서)

1. **재합성 완료 확인** — 위 §2. 사용량은 이제 트윈 `AXCluster/usage_log.jsonl` 에 `source=synth` 로 남는다(`#713` ①)
2. **AXCluster 워커·원격 Codex 실증 확인** (등록·배달·단일 파일 실증 완료, 전체 파이프라인 미검증):
   - `.2` `E:\trunk\AXCluster`, `.33` `C:\trunk\AXCluster` 정식 클론0ffd74b·worker 등록,
     `.43` 포함 deliver/check OK. 마스터 최신 HEAD와 워커 소스 동기화는 별개로 남음.
   - `.2`·`.43` 실제 소스 읽기/쓰기 확인. `.33` 공식 npm Codex0.159.3 업데이트 뒤
     **apply_patch completed·rc0·DONE·반환값 일치·대상 밖 변경 없음·회수53초·정리 뒤 clean** 확인.
   - **필수 설정**: workspace-write + windows.sandbox="unelevated" + network_access=true,
     `/IT /RL LIMITED` 런처. “세션1”은 경로 이름이지 고정 SessionId 아님(.33 USER SessionId18).
     SSH 직접 Codex의 셸0xC0000142는 재현됨. 로그인 부재·쓰기 도구 실패·결과 회수를 구분한다.
   - `.33` 게임 requester·사람 트리는 별개. 대기하던 진단 요청은 해당 요청만 취소·정리했음.
3. **상주 추론·문서 반영**:
   - `.33` 현재 공식 gemma4:e4b pull·keep_alive=-1/context8192 로드, AX_READY·/api/ps 확인.
     AX_Ollama33은 S4U/Limited/AtStartup, Codex /IT와 별개. 재부팅·상주 복원 미검증.
   - 사용자 “브로커 반영해줘” 승인으로 rtx3080(.33:11434, SYNTH pin)을 **운영 반영**.
     routing14/14·health11/11 통과. `scripts/ax-service-restart ax-broker`로 재시작,
     12:43:44 KST 기동·active/running·Result=success. 3노드 healthy/resident 확인.
     동시 진단3건이 bc250·rtx3060·rtx3080 각각으로 분배되어 done=true, eval_count64로 응답.
     3노드 동시 inflight 확인. 소스는 **미커밋·미푸시**이며 재시작으로 로컬 변경을 적용한 상태.
   - 사용자 “진행해…메모리와 문서들” 승인으로 AGENTS·CLAUDE 정본·README·기계 문서·
     Claude 메모리·공용 기억 갱신. 홈 symlink 보존. .2 상주 e4b·.33 AXCluster worker 예외 반영.
   - 근거: `reports/82-axcluster-workers-and-codex-remote.md`, `docs/windows-codex-remote.md`.
     다음 기록 확정: 검토된 변경 commit/push 승인 → 깨끗한 커밋에서 재배달.
     새 합성은 상주 노드 수로 동시3을 선택하며 이미 시작한 배치는 시작 시 정한 동시 수를 유지한다. 자동 로드 문서 수정 승인을 커밋 승인으로 넓히지 않음.
4. **`#713` ③ 웹 UI** — `8103` 에 사용량 그래프(토큰만, 수치만). 원천: 트윈 `usage_log.jsonl`(파견·합성·온톨로지·리뷰) +
   `~/ax-state/usage/sessions/<host>/<tool>/*.json`(대화 세션, crontab 04:17 수집)
5. AXCluster 첫 실증 — 작은 AX 일감 하나 등재 → `.43` 파견 → ⑦ 전진(사람 승인)

## 4. 오늘 커밋 (모두 Gitea push · GitHub 미러 · `.43` pull 완료)

`183f32a` claim 범위(work 혼입 방지, 큐 재시작) · `ef239fb` 원격 문서 · `c595c01` 온보딩 ·
`4c0823f` 합성 요약본+토큰 로그 · `a0cbf42` 트윈 이름 AXCluster · `c237a93` 파이썬 그래프(#712) ·
`6a18918` 세션 수집기(#713 ②) · `306576e` 브로커 호출 사용량(#713 ①) · `c657a7a` 병렬 합성·분배(#715)

## 5. 남은 결함·주의

- `#714` 스풀 고아 배치를 아무도 재처리하지 않는다(`claimed/` 에 3건 남음 — 실손 없음)
- Kimodo 작업장 3대가 마스터보다 뒤다(재배달 필요, 범위 밖이라 안 함)
- `onboard` 의 conventions 문구 「색인 전용」은 code 타입엔 부정확(동작 결함 아님)
- 요약본 뒤에도 4,000자를 넘는 파이썬 파일 125개는 앞에서 잘린다
- 세션 수집기 `master/work/session_usage.py` 는 유닛 테스트가 없다

## 6. 관련 근거

Redmine `#711`~`#715` 노트 · `docs/14-onboarding-runbook.md` · 메모리 `context-docs-are-search-aid` · `codex-windows-ssh-sandbox` · 리포트82 · `docs/windows-codex-remote.md`


## Python 커밋 자동 리뷰 — 구현·검증 통과 (2026-10-03 17:00)

사용자 최초 지시와 kind 기준 정정, “응 진행해” 재개 승인으로 구현·검증했다.
등재·소비·프롬프트·예시는 등록된 프로젝트 kind로 통일한다. unreal=UE, code=Python,
index_only=자동 리뷰 제외. source 경계·work_exts, 큐 중복 방지·재시도·작성자 제외는 유지.
Python 함수·클래스 선언은 현재 트리가 아닌 대상 commit Git 객체에서 AST로 읽는다.
신규6+기존268=274/274 통과, diff --check 통과. 초기 검사 오탐과 승인 후 재개는 리포트83에 보존.
실제 Python commit6a18918을 격리 큐에서 브로커 e4b→Antigravity로 처리하여 최종 저장·done 확인.
아티팩트 /tmp/ax-python-review-live-1392e70e33da4f61a3a92afefb042484/.
운영 큐에 소급 등재하지 않았음. 서비스는 oneshot이므로 다음 기동 때 로컬 수정 소스를 읽는다.
**commit·Gitea push 완료 `7ec14f5`**, 새 운영 커밋의 push감지→자동 리뷰 종결은 아직 미검증.
커밋 검토 범위: 리뷰 코드·테스트5개 + docs/17-review-queue.md + reports/83-python-commit-review.md.
앞선 브로커·원격 문서 dirty 변경과 구분한다. README·reports 색인 갱신은 문서 dirty에 함께 남음.

사용자 “커밋해줘” 승인으로 Python 리뷰 코드·테스트5개 + 설계·실증 문서2개만 커밋했다.
커밋: `7ec14f5` (`review: enable Python commit reviews by project kind`). 푸시는 실행하지 않았다.

사용자 “푸시해줘!” 승인으로 `7ec14f5`를 Gitea origin/main에 푸시했다.
원격 훅에서 Sim/ax-cluster 색인 이벤트1건 큐잉을 확인했다. 리뷰 큐 등재·소비 완료와는 별개다.


## R1 실제 자동 리뷰·검토 완료 (2026-10-03)

운영 commit7ec14f5가 리뷰 큐에 자동 등재되고 17:26:34 첫 시도 done, R1 최종 리뷰 저장 확인.
사용자 “R1 검토해줘”로 지적1건을 운영 Python3.10.12에서 검증: ast.parse 널 바이트는
ValueError이며 SyntaxError만 잡는 declarations에서 전파됨. 격리 큐에서 running잔존·재claim불가 확인.
권고: SyntaxError·ValueError 처리, msg·lineno 모두 getattr, diff 리뷰 계속·큐종결 회귀.
코드·리뷰 원문·R1 상태는 수정하지 않음. 근거 reports/84-r1-python-review-validation.md.

사용자 “수정해줘!” 승인 후 R1 코드 수정 완료: review_runner에서 SyntaxError·ValueError를
잡고 msg·lineno를 안전하게 읽는다. 구문 오류·널 바이트 실제 임시 Git 커밋 모두 리뷰 done,
pending/running=0 회귀 검증. 관련 검사 141건 및 diff --check 통과. 대상 코드·테스트2개만
수정했으며 커밋·푸시 전이다. 리포트84에 수정과 검증 근거 추가. 운영 R1 상태는 변경하지 않음.

사용자가 RAG·서브 에이전트 누락을 지적했다. 최초 수정은 둘 다 없이 진행했음을 인정했다.
**수정 전 관련 RAG 컨텍스트를 조회하고, 위임할 때 그 근거를 함께 전달한다.**
보완으로 AXCluster active 확인 후 search_context_tool 2회 조회, 관련 본문·설계·현재 코드 대조,
로컬 서브 에이전트 r1_context_review에 독립 검토 위임. AX 원격 워커 파견은 아니다.
컨텍스트의 Python 설명 누락·__repr__ 미구현 오기와 검색 excerpt 누락을 관측했으나
검색·합성 설정은 변경하지 않았다. 근거 리포트84.
독립 검토도 R1 추가 코드 수정 불필요로 판정. 널 바이트는 Git 바이너리 diff가 될 수 있으므로
검증 범위는 큐 고착 방지·진단 전달이며 모든 변경 라인 전달 보장은 아니다.

## 사용자 확정 — .57 인프라 정비에도 RAG·분산 도구 활용 (2026-10-03)

사용자 원문: “.33 메인 작업 컴퓨터가 서브에이전트를 활용하고 분산 작업을 시키고,
RAG를 요청하는 스킬이나 MCP를 인프라 서버를 관리할 때도 활용하길 바래서 워커를 등록한거야.”
사용자 후속 정정: “아니 .33에서 작업 하라는게 아니라 .57 이 인프라 서버에서 작업할 때도
.33처럼 RAG와 분산 작업이 가능하도록 구정되어 있냐고”. **작업 장소를 .33으로 옮기라는
뜻이 아니다. .57의 지휘 세션이 인프라 정비에도 RAG·서브 에이전트·AX 워커 분산을 활용한다.**
마스터 직접 수정 뒤 로컬 서브 에이전트 검토만 추가하여 워커 분산까지 했다고 판단하지 않는다.
이번 R1은 마스터 직접 수정 후 RAG·로컬 독립 검토로 보완했고 AX 워커 분산은 수행하지 않았다.
다음 실행 전 관련 스킬·MCP 계약과 기존 승인 범위를 확인한다. 역할 설정·배달은 변경하지 않았다.

준비 상태 실측: .57 현재 세션에서 search_context_tool 성공, register_work_tool 노출,
서브 에이전트 위임 가능. ax-projects·ax-task-queue active/running, ax-dispatch.path active/waiting,
ax-dispatch-catchup.timer inactive/dead. AXCluster 프로필 kind=code, work_exts=.py, blockers 없음.
세 워커 SSH·Codex0.159.3 확인. client check AXCluster는 실패: 세 배달 출처384a07a가
현재 HEAD보다1커밋 뒤, ax-projects는 profile.py 변경 전 기동되어 재기동 필요 판정.
기존 마스터 distribute 스킬도 통합자·기본직렬·UE골조 등 현재 공용 규칙과 어긋난 옛 내용이며
Codex의 현재 제공 스킬 목록에는 distribute가 없다. RAG는 사용 가능하나 분산 준비 완료로
단정하지 않는다. 실패 규칙에 따라 재배달·재기동·스킬 수정은 실행하지 않고 상태만 보고한다.

사용자 “일단 일감으로 등록해”로 Redmine **#716** `[AX] .57 인프라 정비의 RAG·서브 에이전트·분산 작업 준비 정비`
등록 완료. AX Cluster 프로젝트, 마일스톤6, 신규 상태. 버전 불일치·서비스 재기동 필요·
마스터 분산 스킬 갱신·Python 소스 더티 검사 확인과 실제 .57→워커 흐름 검증을 범위로 기록했다.
등록만 했으며 작업 실행·재배달·재기동·커밋·푸시는 하지 않았다. 항목·진행 정본:
http://192.168.0.57:8080/issues/716.

사용자 최신 절차: CLAUDE.md·AGENTS.md·스킬에 **RAG 검색→단독/분산을 사용자에게 물음→
선택에 따라 서브 에이전트 구성→단독 처리 또는 AX 워커 분산→실물 검증**을 반영한다.
이어 “NS에서 작업 요청을 받았을 때” 실제 방식 분석·참조를 지시하여 .33 NS 지침·스킬·
에이전트·MCP·훅을 읽기 전용으로 대조했다. 근거 reports/85-ns-requester-workflow-reference.md.
NS의 기존 컨텍스트/온톨로지·계획/선택·전문 위임·큐 등재·asyncRewake·되먹임 흐름을
참조하되 combined_search/watch.exe/attempt/클라이언트 등재금지 등 낡은 문구는 복사하지 않는다.
자동 로드 지침·스킬 반영, 재배달·서비스 재기동은 아직 실행하지 않았다. 이전 처리 방식 질문은
지침 반영에 관한 것이며 이번 분석·참조 요청을 분산 실행 승인으로 읽지 않는다.
사용자 “아까 신설한 레드마인에 연결해둬!”로 #716 journal1480에 리포트85 경로·NS 분석 결과·
사용자 확정 절차·남은 반영/운영 검증을 연결하고 재조회 확인했다. 미커밋 보고서임을 명시했고
일감 상태는 신규로 유지했다.

사용자 “아까 리뷰 대응한거 커밋하면서 리뷰 상태값 변경하고” 승인으로 R1 수정 코드·테스트·
리포트84의3파일만 커밋: **95906c87914c081ff6fb64ad05443ccfc75b8bfb**
(`fix(R1-1): handle Python declaration parse failures safely`). 핵심7건 재확인 통과.
fix_index.set_status로 AXCluster **R1-1→applied**, 실제 branch=main·위 커밋을 기록하고
get_doc 재조회로 상태·해시 일치 확인했다. R1 전체 항목1/1 applied. 푸시는 하지 않았다.
브로커·원격 설정·NS 분석 등 앞선 dirty 변경은 이 커밋에 포함하지 않았다.

사용자 “푸시해줘!” 승인으로 95906c8을 Gitea origin/main에 푸시 완료.
git ls-remote의 refs/heads/main=95906c87914c081ff6fb64ad05443ccfc75b8bfb 일치 확인,
원격 훅의 색인 이벤트1건 큐잉 확인. R1-1 applied 노트에 원격 반영도 기록한다.
새 커밋의 자동 리뷰 종결은 아직 확인하지 않았다.

#716 선행 정비: 사용자 동의로 로컬 서브 에이전트 2개가 지침5파일과 타입별 더티 검사2파일을
수정했다. workshop 검사77/77, SourceScope 권한 해제 재검사32/32 통과. 독립 코드 검토 진행.
실제 따라잡기 타이머는 **ax-dispatch.timer**이며 active/waiting이다. 앞선
ax-dispatch-catchup.timer 조회로 비활성이라 기록한 내용은 이 실측으로 정정한다.
경로 추정 조회 오류가 반복돼 공용 실패 규칙에 따라 추가 편집 중단. 남은 distribute 스킬은
루트 직접 인수 예정이며 아직 원본이다. 보고서86에 변경·검사·실패·운영 미검증을 기록했다.
스킬 완성·Codex 연결·깨끗한 커밋 기준 배달/서비스 반영·분산 전체 실증이 남았다.
이번 #716 변경의 커밋·푸시는 승인받지 않았으며 배달·재기동·원격 파견도 하지 않았다.

사용자 “모두 커밋 푸시하고 동기화해”로 전체 현재 변경 승인. distribute 스킬은 루트가
현재 흐름으로 재작성 완료했고 형식/독립 forward 검토 통과. Codex legacy·공식 사용자 경로
링크를 좁은 권한 승인 스크립트로 등록했다. 관련 코드 검사123개 통과. 이전 미완료/승인없음
기록은 위 승인·완성 상태로 갱신한다. 이제 전체 변경을 커밋·Gitea push하고 클론·등록 전체
작업장 배달 및 ax-projects/ax-broker 반영을 수행할 예정. 실측 결과 정본은 #716 journal.
스킬 자동 감지가 공식 동작이지만 이 세션의 새 스킬 노출은 미확인. 다음 세션에서 distribute
노출과 정본 경로를 확인한다. 실제 분산 전체 흐름과 Python 통합 실행기 호환성은 미실증이다.
