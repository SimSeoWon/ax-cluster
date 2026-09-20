# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).
> 🔴 [주의] **「완료」만 대조하면 부족하다** — 이 문서의 **관측 서술**(무엇이 어떻게 보였다)도
> 대조 대상이다. 2026-09-20 에 그걸 안 해서 틀린 관측을 이슈에 적립했다.

- **갱신 시각**: 2026-09-21 01:28 KST
- **지휘 도구 / 세션 식별자**: **Codex**
- **상태**: **교대 준비** — Windows Python 경로·상주 원하는 상태·전체 작업장 업데이트
  플로우 구현 및 운영 배포 완료. 이 인계서만 미커밋.
- **관련 일감 / 목표**: 이번 수정에 연결된 신규 Redmine 일감 없음 · `#652`, `#360` 완료.
  다음 AX 항목은 Redmine에서 사용자가 고른다.
- **저장소·브랜치·HEAD**: `~/ax-cluster` `main` **`3a310ed`** · origin과 일치 · 미푸시 0.
- **현재 dirty**: `docs/orchestrator-handoff.md` 한 파일 — 이 인계 기록.
- **실행 중인 작업·프로세스**: 없음 · `hold.json` 없음 · 서브 에이전트 없음.
- **서비스**: `ax-task-queue` active/running(2026-09-20 20:04 KST) ·
  `ax-projects` active/running(20:20 KST) · `ax-status` inactive/dead + Result=success
  (oneshot 정상, 2026-09-21 01:23 KST).

---

## 🔴 1. 바로 다음 작업

### ⑴ 이 인계서 커밋·푸시 승인 받기

커밋·푸시는 매번 사용자 승인이 필요하다. 대상은 이 파일 한 개다.

    docs: 전체 작업장 업데이트 플로우를 인계한다

### ⑵ 문서 커밋 뒤 전체 업데이트를 마지막에 한 번 실행

현재 클라이언트는 `3a310ed`와 일치한다. 이 문서를 커밋하면 HEAD가 다시 전진하므로 커밋·푸시
**뒤에** 아래 명령을 실행해야 모든 등록 작업장의 출처 리비전이 새 HEAD와 다시 같아진다.

    AX_PROJECTS_ROOT=/home/sim/ax-cluster \
      .venv/bin/python -m master.client update

이 명령은 프로젝트별 배포 여부를 사람이 다시 판단하는 자리가 아니다. 레지스트리의 모든
프로젝트와 작업장을 배달·검사하며, 하나라도 실패하면 rc=1이다.

### ⑶ 다음 AX 항목은 사용자가 고른다

종전 후보 `#396`도 Redmine 현재 상태를 다시 확인한 뒤 사용자 선택을 받는다.

---

## 2. 이번 교대에서 완료한 것

### 2.1 `.33` Codex의 Python 경로를 초기화 산출물로 만들었다

Codex 세션의 PATH가 대화형 SSH와 달랐는데 `.mcp.json`과 `ax-fix`가 bare `py`에 의존했다.

- `HostFacts.python`과 config `backends.python`에 실측 절대경로 저장
- `.mcp.json`의 `ax-client.command`와 `ax-fix`가 같은 절대경로 사용
- Windows에서 경로를 못 찾으면 `check` 실패
- 신규 프로젝트 온보딩도 같은 bundle/config/skill 경로를 쓰므로 자동 적용

커밋 `78f7578`.

### 2.2 상주 등록의 원하는 상태를 한 함수로 통합했다

`deliver`와 `check`가 같은 기계를 반대로 판정하던 중복 규칙을 없앴다.

- `client/init/residency.py::desired_state()`가 requester·daemon·작업 유형·현재 마운트를 판정
- `plan`·`deliver`·`check`가 같은 결정을 소비
- 원하는 상태가 미등록이면 과거 등록도 제거하고 부재를 되읽음
- NS 마운트 중 ModularStage 상주는 `.2`에서도 미등록이 정상

커밋 `6d1ea50`.

### 2.3 검사기의 마운트 조회 오류를 숨기지 않게 했다

`master/client/__main__.py`가 import하지 않은 `Registry`를 호출하고 `except Exception: pass`로
`NameError`를 숨겨 마운트를 빈 문자열로 바꾸고 있었다.

- `bundle.Registry`를 명시적으로 사용
- 조회 실패를 빈 마운트로 접지 않고 전파
- NS 마운트에서 ModularStage 미등록이 정상이라는 회귀 테스트 추가

커밋 `2ca5a12`.

### 2.4 전체 등록 작업장을 맞추는 단일 `update` 플로우를 만들었다

    AX_PROJECTS_ROOT=/home/sim/ax-cluster \
      .venv/bin/python -m master.client update

- 프로젝트 인자를 받지 않고 `Registry.names` 전체 사용
- 신규 프로젝트는 레지스트리에 등록되는 순간 자동 포함
- 프로젝트별 `deliver → check`
- 일부 실패를 전체 성공으로 접지 않으며 나머지 등록 프로젝트도 계속 시도
- 깨진/빈 레지스트리는 시작 전에 fail-closed

커밋 `3a310ed`.

---

## 3. 운영 배포와 검증

`3a310ed` 푸시 뒤 새 `update` 명령을 실제 실행했다.

| 프로젝트 | `.2` worker | `.33` requester | `.43` worker |
|---|---|---|---|
| ModularStage | OK | OK | OK |
| NS | OK | OK | OK |

- 두 프로젝트 모두 config·스킬·payload·AGENTS.md·Codex MCP·역할 토큰 대조 통과
- 모든 작업장의 `delivered_by.commit`이 당시 마스터 HEAD `3a310ed`와 일치
- `.2`: NS 상주 `AxWorker_NS` 등록 정상
- `.2`: ModularStage는 현재 마운트가 NS이므로 상주 미등록 정상
- `.33`: requester이므로 두 프로젝트 모두 상주 미등록 정상
- `.43`: 집을 작업 유형이 없어 두 프로젝트 모두 상주 미등록 정상
- 전체 명령 rc=0: `등록 프로젝트 2개를 현재 HEAD로 배달·검사했다`

### 테스트

- 검사 마운트 수정까지: 5753/5753
- 전체 `update` 플로우 추가 뒤: **5757/5757 · 실패 파일 0개**

기본 Codex 샌드박스의 첫 전수 테스트는 소켓 생성 EPERM과 Docker 기반 Redmine 키 조회 차단으로
실패했다. 같은 테스트를 샌드박스 해제 상태로 재실행해 전부 통과했다. 코드 회귀로 기록하지 않는다.

---

## 4. 제거한 옛 스킬 사본

`.2`에 Codex가 배달본 대신 읽을 수 있는 shadow copy가 있었다. 삭제 전 각 경로에
`SKILL.md` 한 파일만 있음을 확인하고 사용자 승인 뒤 정확히 두 디렉터리만 삭제했다.

    C:\Users\janus\.agents\skills\ax-work
    C:\Users\janus\.agents\skills\ax-infer

삭제 직후 부재를 확인했고 이후 두 프로젝트 전체 검사에서 재발하지 않았다. 삭제 사본 자체는
복구 불가지만 정본은 저장소와 `.claude`/`.codex` 배달 위치에 남아 있다.

---

## 5. 실패와 교훈

1. 같은 날 마운트 오판과 리비전 불일치를 반복했다. 전자는 실제 마운트 대신 예외로 생긴 빈
   문자열을 썼고, 후자는 사람이 기억해야 하는 프로젝트별 배포 순서를 남겨 둔 것이 문제였다.
2. 새 고정 동사는 `update`다. “모든 컴퓨터를 현재 리비전으로 맞춘다”에서 지휘자가 프로젝트별
   `deliver` 필요성을 다시 추론하지 않는다.
3. `update`는 HEAD를 배포 출처로 기록한다. **마지막 문서 커밋 뒤에 실행**해야 한다.
   업데이트 뒤 다시 커밋하면 작업장은 다시 한 커밋 뒤가 된다.
4. 인계서 첫 교체 시도는 `apply_patch`에서 같은 파일을 Delete+Add 대상으로 동시에 지정해
   원자적으로 거절됐다. 파일 변화는 없었고, 두 번째 시도는 `Update File`로 정상 적용했다.

---

## 6. 관련 파일

    master/client/__main__.py
    master/client/bundle.py
    client/init/residency.py
    master/client/skills/ax-fix/SKILL.md
    master/test_client_bundle.py
    master/test_residency.py
    docs/orchestrator-rules.md
    docs/15-orchestrator-handoff.md
