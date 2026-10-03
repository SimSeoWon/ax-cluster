# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **갱신 시각**: 2026-10-03 KST (마운트 전환 직전)
- **지휘 도구 / 세션**: Claude
- **상태**: 작업 중 — ax-cluster 자신을 분산 파이프라인에 태우는 온보딩(`#711`)
- **관련 일감**: `#711`(이 축) · `#706`(MotionForge 마운트, ax-cluster 뒤로 밀림) ·
  `#700`·`#701`·`#695`(열림, 아래 §3)
- **워커 지휘자 모드**: `codex` (말하기 전에 `~/.cache/ax-dispatch/mode.json` 재조회)
- **마운트**: `KimodoMotion_WebUI` → **ax-cluster 로 전환 예정**(사용자 지시 2026-10-03)

## 1. 사용자 결정 (2026-10-03)

- 클러스터 정비도 워커(BC-250)를 쓴다 → ax-cluster 를 **등록·마운트 대상**으로 삼는다.
  마운트 규칙(§12.5-a)에 예외를 두지 않는다.
- 원격: **Gitea 정본**(`gitea@192.168.0.57:Sim/ax-cluster.git`) + **GitHub 푸시 미러**
  (HTTPS 세분화 토큰, 커밋 시 동기화). 🔴 **GitHub 직접 push 금지** — 미러가 덮어쓰고 지운다.
  마스터 `github` 원격은 push URL 비활성. 마스터·`.43` 의 `origin` = Gitea.
- AX 작업의 요청자(골조·⑦ 전진·finalize) = **마스터 세션**. 작업장은 **`.43` 만**(worker).
- profile: kind `code`(`.py`) · purpose `rnd` · language·overview·테스트 위치는 사용자가 초안을
  「그대로」 확정(`master/client/payload/profile/ax-cluster.yaml`).
- 순서: claim 범위 수정 마무리 → Gitea → 등록 → **ax-cluster 로 바로 마운트**(MotionForge 보다 먼저).

## 2. 완료 (검증 포함)

- `183f32a` work 혼입 방지 — push 파견이 자기 work 만 claim. 신규 회귀 11/11(기대값 정정:
  verifier_id 는 부재가 아니라 None) · `master/test_*.py` 139파일 전부 통과 ·
  `ax-task-queue` 재시작 09:55:06(진행 태스크 0 확인 후). 실제 claim 실물은 아직 없다.
- Gitea `Sim/ax-cluster` 생성(private) · 푸시 미러 동기화 오류 없음 ·
  `ef239fb` push 후 5초 안에 GitHub 반영(자동 동기화 실물 확인).
- `ef239fb` 문서: `machines/sim-desktop.md`·`CLAUDE.md` 의 원격 서술을 Gitea 정본으로.
- 트윈 `ax-cluster` 등록 · hook · clone · guard · profile 완료. source 경계 = `master`·`client`
  의 `.py`(트윈 `config.yaml`, 저장소 밖). conventions 는 비UE라 설계상 해당 없음
  (`onboard.py:440`, 문구 「색인 전용」은 code 타입엔 부정확 — 동작 결함 아님).

## 3. 열린 것

- **남은 온보딩**: 마운트 전환 → graph · index · synth → `.43` 작업장 등재·배달·대조 →
  작은 AX 일감으로 첫 실증(⑦ 전진·finalize 는 사람 승인).
- **미결**: 마스터 세션이 요청자가 되는 등재·통합 표면이 `.33` 없이 성립하는지 확인 필요.
- `#700`·`#701`·`#695` 는 코드 배포됨(`6001207`·`0d22882`)이나 Redmine 상 신규 — 실물 확인 전.
  `#695` 시도 격리 수정은 실제 재시도로 아직 확인 못 함(다음 `.2` 재시도의 `[세션1]` request_id 로 판정).
- 취소된 Kimodo work 3개의 미병합 durable 브랜치 9개·스풀 3건 — **보존**(사람 몫, 사용자 결정 2026-08-23).

## 4. Windows Codex 실행 시 구분할 세션 (계속 유효)

`.2` 에서 SSH 직접 실행(세션 0)은 Codex 셸이 `0xC0000142` 로 죽는다. **SSH 는 데이터 전송·런처
깨우기에만 쓰고, Codex 는 `/IT·LIMITED` 사용자 런처(세션 1)로 돌린다.** 정본 경로는
`master/work/runner.py` → `client/init/residency.py` → `client/runtime/session1_conductor.py`.
재부팅 뒤 `janus` 로그온이 없으면 `.2` 는 조용히 파견에서 빠진다. `.43`(리눅스)은 SSH 직접 성공.

## 5. 받는 세션의 첫 확인

```bash
cd /home/sim/ax-cluster
git status --short --branch && git rev-parse HEAD origin/main
```

- 마운트가 무엇인지(`list_projects_tool`의 `active`)와 트윈 `ax-cluster` 의 onboard 상태
  (`AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard ax-cluster`).
- `.43` 전원(2026-10-03 사용자가 켬).

## 6. 관련 근거

- 리포트 64·66(`.2` 재시도 원인) · 78·80·81(Kimodo 실증·`#695`·세션 0/1)
- `docs/14-onboarding-runbook.md` · `docs/12-multi-project.md` · Redmine `#711`
