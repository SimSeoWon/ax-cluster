# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **갱신 시각**: 2026-10-03 11:50 KST — Claude 토큰 소진 직전, **Codex 로 넘긴다**(사용자 지시)
- **지휘 도구 / 세션**: Claude → Codex
- **상태**: 교대 준비. 무인 작업 없음 — §2 재합성은 **미완**(76/347)
- **관련 일감**: `#711`(ax-cluster 자신을 파이프라인에 태운다) · `#712`(파이썬 그래프, 구현됨) ·
  `#713`(LLM 사용량 통합 + 웹 UI) · `#714`(스풀 고아 배치) · `#715`(병렬 합성·브로커 분배, 구현됨)
- **워커 지휘자 모드**: `codex` (`~/.cache/ax-dispatch/mode.json` 재조회)
- **마운트**: `AXCluster` (트윈 `~/ax-cluster/AXCluster/`, project_id `Sim/ax-cluster`)
- **HEAD**: `c657a7a` (`origin` = Gitea). 이 인계 파일만 미커밋

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
- 🔴 **AX 클러스터 기능 작업(AXCluster)에서는 `.33` 도 워커로 쓴다** — 아래 §3, 아직 안 함

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
2. **`.33` 을 AXCluster 워커로 등재** (사용자 지시, 미착수):
   - `set_workshop_tool(name="AXCluster", host="192.168.0.33", driven="ssh", user="user",
     path="C:\\trunk\\AXCluster", role="worker")` → `python -m master.client deliver AXCluster` → `check`
   - 🔴 Windows 라 codex 는 **세션 1 런처**(`schtasks /IT`) 경유여야 한다 — SSH 직접은 `0xC0000142`.
     사람이 쓰는 데스크톱 세션에서 codex 가 돈다는 점을 사용자에게 한 번 알린다
   - 손님 규칙: 게임 작업 트리와 분리(`C:\trunk\AXCluster`) · 쓰기 전 dirty 확인
   - 🔴 **자동 로드 문서 수정 필요** — `machines/sim-desktop.md` 의 「`.33` never dispatched to」를
     「AXCluster 에서는 worker」로. **문구를 보여 주고 동의를 받은 뒤** 고친다
   - 합성 추론에 `.33` 을 쓰는 것은 별개 질문(사용자: *".33은 왜 안써?"* — 답 미전달). 실측: `.33` 여유 VRAM
     7.6GB 였고 e4b 실측 3.0GiB 라 **들어간다**. 다만 사람의 작업 PC(UE5·게임과 경합) — 브로커 엔드포인트
     추가 여부를 사용자에게 묻는다
3. **`.2` 문서 갱신** — 자동 로드 문서의 「`.2` 14b pinned」 → e4b (동의 후)
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

Redmine `#711`~`#715` 노트 · `docs/14-onboarding-runbook.md` · 메모리 `context-docs-are-search-aid`
