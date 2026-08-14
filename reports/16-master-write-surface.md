# 16. 마스터 쓰기 표면 — Flow Y 배선의 선결 (2026-08-14)

> 마일스톤 4 · 대 1 토폴로지 원복 · **중 1.2 2-tier 복원** (`#121`) — 잔여 `#123`·`#125`.
> 🔴 **이 절은 실행 *전에* 썼다** (CLAUDE.md § 작업 일지 규칙). Gitea 는 공유 인프라다.

## §1 세션 시작 상태 (실측)

    ax-cluster 세 클론     ee65203 동일 · 작업트리 청결 (마스터·GitHub·.43)
    마스터 서비스          ax-task-queue · ax-broker · ax-projects · ax-indexer.path/.timer · ax-status.timer  전부 정상
    큐                     works 0 · 색인 게이트 paused=False("진행 중 작업 없음")
    기계                   .57 ✅ · .43 ✅(부팅 9분) · .2 ✅ · 🔴 .33 꺼짐
    레드마인 M4            22/75 완료 (version *마일스톤 4* = id 3)

⚠️ **리포트 15 의 종료 시퀀스는 ① 만 실행됐다** — `.2`·`.33`·`.57` 은 안 껐고, 마스터는 6일째
가동 중이다. `.43` 은 이 세션 직전에 물리 버튼으로 다시 켜졌다.

## §2 `#123` 의 정체 — 이식이 아니라 **배선**이 남아 있었다

`master/work/coordinator.py`(217줄)는 원전 `cluster_coordinator.py`(200줄) 함수 6개를 전부
갖고 있고 실 Gitea 실증도 통과했다(리포트 14 §15). 🔴 **그런데 그것을 `import` 하는 곳은
`test_coordinator.py` 와 `selftest.py` 둘뿐이다** — 실 파이프라인(`runner`→`infer`→`integrate`)은
2-tier 브랜치를 **한 번도 쓰지 않는다.**

    실측: grep -rn "from .coordinator\|work.coordinator" --include=*.py .
          → master/test_coordinator.py:25 · master/work/selftest.py:51   (끝)

## §3 🔴 갈림길 — Flow Y 는 마스터의 push 봉인과 정면으로 부딪힌다

Flow Y(사용자 확정 2026-08-14)는 *"마스터가 받은 diff 를 task/attempt 브랜치에 **commit**"* 이다.
그런데 마스터 정본의 push 는 **의도적으로 봉인**돼 있다:

    /home/sim/ax-cluster/ModularStage/repo
      origin  /var/lib/gitea/gitea-repositories/sim/modularstage.git   (fetch)
      origin  DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1  (push)

근거는 `docs/2-architecture.md` §2.1·§2.2-1 *"마스터는 여전히 파일을 소유하지 않는다"* 이고,
`selftest.py` 가 1단계를 **임시 저장소**에서 돌린 이유도 이 봉인이었다.

**사용자 결정 (2026-08-14): 「별도 쓰기 표면 추가」.** 정본 `origin` 의 push 봉인은 **그대로
두고**(오발 push 를 시끄럽게 죽이는 가드로 남긴다), 같은 클론에 push 가능한 두 번째 remote 와
attempt 전용 worktree 를 둔다. 🔴 정본 트리는 계속 `main` 에 앉아 있으므로 §5.5 가 기대는
*"정본은 fetch 전용"* 불변식을 건드리지 않는다.

## §4 전송 경로 — 파일시스템 push 는 **불가능**하다 (실측)

    sg gitea -c 'ls -ld /var/lib/gitea/gitea-repositories/sim/modularstage.git'
    → drwxr-xr-x 8 gitea gitea      🔴 그룹은 r-x, **쓰기 없음**

🔴 **그래서 bare 에 직접 push 할 수 없다.** 억지로 `g+w` 를 주면 Gitea 의 receive 훅·브랜치
보호·DB 갱신을 **우회**해 쓰게 된다 — 그건 가드를 여는 것이 아니라 없애는 것이다.
→ 쓰기는 **Gitea 정규 경로(SSH)** 로 간다. 작업장 `.43` 이 이미 그 경로를 쓴다(실측):

    origin  gitea@192.168.0.57:Sim/ModularStage.git   (fetch·push)

⚠️ 그리고 `sim` 은 `/etc/group` 상 `gitea` 그룹인데 **이 대화형 셸 프로세스에는 그 그룹이 없다**
— §5.5 가 적어 둔 *"그룹 변경은 떠 있는 프로세스에 소급되지 않는다"* 함정. 읽기 확인은
`sg gitea -c` 로만 된다. 서비스는 `SupplementaryGroups=gitea` 로 이미 갖고 있다.

## §5 🔴 별개 발견 — `main` 은 서버측 보호가 **없고**, 넣을 수도 없다

    GET /api/v1/repos/Sim/ModularStage/branch_protections  →  []
    GET /api/v1/user/keys  →  ax-worker-2 · ax-worker-43 · ax-requester-33   (마스터 키 없음)

🔴 **네 대가 전부 같은 Gitea 계정 `Sim` 으로 인증한다.** 등록된 것은 저장소별 배포키가 아니라
계정 키(`/user/keys`)다. Gitea 의 브랜치 보호 화이트리스트는 **사용자 단위**이므로, 같은 계정을
쓰는 기계들 사이를 **원리적으로 구분할 수 없다.** 즉 *"마스터는 `main` 에 못 쓴다"* 를 서버에
넣는 방법이 지금 구조에는 없다.

→ **가드는 클라이언트측에 둔다**(마스터 클론의 `pre-push` 훅). 🔴 이것은 이식 위에 얹는 개선이
아니라 **봉인을 여는 비용**이다 — 원전 인프라 PC 는 push 권한을 그냥 갖고 있었고, 우리는 §2.1
때문에 봉인을 뒀으므로, 봉인을 좁히려면 대체 가드가 같은 커밋에 있어야 한다
(마일스톤 4 「가드를 만들면 깨울 주체를 같은 커밋에 넣는다」의 같은 결).

⚠️ **기계별 Gitea 신원 분리는 이 세션의 범위 밖이다** — 사용자 결정이 필요한 별개 항목이라
아래 「남은 것」에 적는다.

## §6 실행할 명령 (이 절은 실행 전에 적었다)

    ① 마스터 키 등록 — 워커에 한 것과 같은 방식 (§8.5)
       POST /api/v1/user/keys   title=ax-master-write   key=~/.ssh/id_rsa.pub
       되돌리기: DELETE /api/v1/user/keys/<id>

    ② 인증 확인
       ssh -T gitea@192.168.0.57                        → "authenticated with the key named ax-master-write"
       git ls-remote gitea@192.168.0.57:Sim/ModularStage.git

    ③ 쓰기 표면 추가 (정본 clone 안, origin 은 손대지 않는다)
       git -C ModularStage/repo remote add gitea-write gitea@192.168.0.57:Sim/ModularStage.git
       되돌리기: git remote remove gitea-write

    ④ 🔴 대체 가드 — pre-push 훅 (attempt/* · task/* 만 통과)
       ModularStage/repo/.git/hooks/pre-push
       되돌리기: rm 그 파일

    ⑤ 실증 — 훅이 막는 것과 통과시키는 것을 **둘 다** 잰다
       push --dry-run gitea-write HEAD:refs/heads/main            → 🔴 훅이 거부해야 한다
       push --dry-run gitea-write HEAD:refs/heads/attempt/probe/… → 통과해야 한다

## §7 실행 기록

    ① 키 등록      ✅ id=4 `ax-master-write` (SHA256:nJK1+FYa…)
    ② 인증 확인    ✅ "authenticated with the key named ax-master-write" · ls-remote 통과
    ③ 쓰기 표면    ✅ remote `gitea-write` 추가 · origin push 봉인은 **그대로**
    ④ pre-push     ✅ 원본 `master/work/pre_push_hook.sh` → 설치 `…/repo/.git/hooks/pre-push`
    ⑤ 실증         ✅ 아래 §8

### 🔴 스스로 잡은 규약 위반 하나 — 훅을 저장소 밖에만 뒀다

처음엔 훅을 `.git/hooks/pre-push` **에만** 썼다. 🔴 **그 디렉토리는 어느 저장소도 추적하지
않는다** — 클론을 다시 만드는 순간 **가드가 조용히 사라진다.** 가드에는 최악의 실패다.
그리고 이 저장소는 그 함정을 **이미 문서로 못박아 뒀다**: `events/post_receive_hook.py` 머리말
*"이 파일이 원본이고 `install_hook.py` 가 복사한다. 훅을 저장소 밖에서만 고치면 다음 사람이
원본을 못 찾는다."*

→ 같은 규약으로 정정했다: 원본은 `master/work/pre_push_hook.sh`(SSOT), 설치·검증은

    python -m master.work.attempt status        # 설치됐나 · 원본과 같나 · 실행 가능한가
    python -m master.work.attempt install-hook  # 원본에서 설치 (덮어쓴다 — 원본이 SSOT)

⚠️ 검증기가 **첫 실행에서 불일치를 잡았다**(설치본에 SSOT 머리말이 없었다) — 즉 *"설치돼 있다"*
와 *"원본과 같다"* 를 가르는 것이 실제로 일한다.

## §8 가드 실증 — 🔴 **허용과 거부를 둘 다 쟀다**

| | 결과 |
|---|---|
| `attempt/guardprobe/master/t1` (실 dry-run) | ✅ `[new branch]` — 훅 통과 |
| `probe-guard-check` (실 dry-run) | 🔴 훅 거부 |
| `main` (훅 직접 입력) | 🔴 훅 거부 |
| `main` 되감기 (실 dry-run) | ⚠️ **훅이 아니라 git 의 non-fast-forward 가 막았다** |
| 삭제 — 미병합 attempt | 🔴 거부 (병합 안 됨 = 증거) |
| 삭제 — 병합된 durable | ✅ 통과 |
| 삭제 — tracking ref 없음 | 🔴 거부 (판정 불가 → **보존**) |
| dry-run 이 만든 ref | **0건** (`ls-remote` 로 확인) · 정본 청결·`main` 유지 |

🔴 **측정 도구가 조용히 틀린 자리 하나 — 스스로 잡았다.** `main` push 를 dry-run 으로 재려
했는데 정본 HEAD == 원격 `main` 이라 *"Everything up-to-date"* 로 **훅이 아예 안 불렸다.**
되감기(`HEAD~1`)로 바꿨더니 이번엔 **git 의 ff 검사**가 먼저 막아 역시 훅이 안 불렸다.
→ 훅에 **직접 입력을 넣어** 판정했다. ⚠️ 마일스톤 4 의 *"측정 도구 자신이 조용히 틀린다"* 가
이 세션에도 나왔다. **`rc` 가 0/1 인 것만 보고 「가드가 동작했다」로 접으면 틀린다 — 누가
막았는지를 봐야 한다.**

⚠️ **삭제 검증은 git 을 부르지 않고 훅에 직접 입력했다.** `CLAUDE.md` 가 대화형 세션의 브랜치
삭제를 승인이 있어도 금지하므로, `--dry-run` 이어도 그 명령을 만들지 않았다.

## §9 소 1.2.2 (`#123`) — 마스터측 attempt 계층을 **배선**했다

신규 `master/work/attempt.py`. 🔴 이식본 `coordinator.py` 의 함수를 **그대로 쓴다** —
`assign_attempt` · `push_attempt` · `verify_and_merge`, 그리고 원전이 만들어 둔 **주입 seam**
(`work_fn`)에 실전용 적용 함수를 끼운다. 드라이런(`fake_workshop`)과 실전이 **같은 경로**를 탄다.

    ensure_attempt_tree   <프로젝트>/ax-wt-<work_id> — 정본 **옆**. 정본은 main 에 남는다
    apply_responses       Response.files({경로: 완성 본문}) 를 쓰고 **되읽어 확인**
    push_attempt_for      🔴 성공·실패 **무관** push. 이 계층은 판정하지 않는다
    merge_verified        epoch 게이트 → 통과분만 durable

**원전과 다르게 둔 것 하나 추가** (`coordinator.py` 머리말 ④): `remote` 가 인자다. 원전 인프라
PC 는 `origin` 에 push 할 수 있었고 우리는 봉인돼 있으니, **그 인자 하나가 환경 차이를 전부
흡수한다.** 기본값은 원전 동작(`origin`) — `selftest` 의 임시 저장소가 그 경로다.

### 🔴 `#115` 와 §8.4 의 모순을 정리했다

`integrate.py` 의 *"실패는 커밋하지 않는다"* 는 근거가 *"쓰는 주체가 하나라 **실패 attempt 를
남길 브랜치가 없다**"* 였다. **그 전제가 사라졌다** — attempt 계층이 돌아왔으므로 §8.4
*"실패도 커밋한다"* 가 맞다. ⚠️ **문장을 지우지 않고** 그 파일에 *"이 토폴로지에서만"* 이라는
교차 참조를 달았다(§8.4 규약: 두 토폴로지를 나란히 두고 측정으로 고른다).

### 실 구동 (임시 저장소 아님 — 실제 Gitea)

    attempt push        cfc419fd → attempt/probe-flowy/master/20260814-live1  ✅ 원격 확인
    본문 왕복           .ax/probe/flowy.md 내용 일치 ✅
    🔴 정본 불변        b1ba6af9 → b1ba6af9 · branch main · 청결 ✅
    좀비 epoch (1<2)    🔴 거부 · durable **안 생김** (부작용 0) ✅
    epoch 통과 (2==2)   durable task/probe-flowy 신규 생성 ✅ 원격 확인
    색인기 반응         깨어남 → `b1ba6af9→b1ba6af9 · 재색인 건너뜀` ✅ 스풀 잔량 0

🔴 **색인기 반응은 예측을 실측으로 확인한 것이다.** `post_receive_hook` 은 **ref 를 안 가리고**
전부 스풀에 넣지만, `consumer.process_event` 는 `ev.ref` 를 **보지 않고** 정본에서
`merge --ff-only FETCH_HEAD` 를 하고 그 for-merge 항목은 `main` 의 업스트림뿐이다 →
attempt push 는 `from == to`. 리포트 14 §17 이 이미 잰 경로와 같다.

### 🔴 이식본이 잡은 우리 결함 — locale

테스트 ⑧(같은 내용 재제출)이 실패했다. *"변경이 없다"* 를 `"nothing to commit" in str(e)` 로
판정했는데 **이 기계는 `ko_KR.UTF-8` 이라 git 이 한국어로 말한다.** 트리 상태(`status
--porcelain`)로 판정하도록 고쳤다. ⚠️ **`integrate.py` 는 아직 문구 대조를 쓴다** — 거기는 git 이
영어인 윈도우 작업장에서 도는 코드라 지금은 맞지만, **마스터로 옮겨오면 같은 자리에서 깨진다.**
같은 부류를 `plan_remote_cleanup` 에서도 미리 없앴다(종료코드 대신 `merge-base` **값** 비교).

## §10 소 1.2.4 (`#125`) — 정리 시점: **도달 가능한 것만** (사용자 결정 2026-08-14)

결정을 부르기 전에 실측했고, 그 실측이 선택을 바꿨다:

    원격 attempt 4건    🔴 **전부** main 에서 도달 불가 (그 커밋이 거기만 있다)
    원격 durable 5건    4건은 병합됨(bc4b38f4) · 1건은 이 세션 probe
    응답 스풀           **1건뿐** — 2026-08-09 태스크는 **하나도 없다**

🔴 **원전대로 work 종료 시 `delete=True` 를 돌렸다면 실패 시도 3건의 유일한 사본이 사라졌다.**
⚠️ 단서: 그 셋은 스풀 설계(소 1.3.2) *이전*의 산물이다. 이후 작업은 스풀이 유료 LLM 출력을
들고 있어 조건이 다르다 — 그래도 채택한 기준이 더 안전하다. **병합되면 자동으로 삭제 대상이
되므로 영구 누적이 아니다**(테스트로 그 성질을 고정했다).

기준은 `work/cleanup.py` 가 로컬 브랜치에 쓰는 것과 **같은 것 하나**이고, **두 겹**으로 넣었다:

    호출자   attempt.plan_remote_cleanup / apply_remote_cleanup — 계획을 내고 그것만 지운다
    최후방   클론의 pre-push 훅 — 같은 기준을 **한 번 더** 판정한다

⚠️ **범위는 ephemeral 뿐 — durable 은 원전대로 보존**하고 세어서 보고만 한다.
🔴 **판정 불가는 언제나 보존**이다(tracking ref 없음·fetch 실패·git 실패).

**실 저장소 계획 실행(삭제 없음)** — 손 측정과 정확히 일치:

    ephemeral 삭제 대상 0 · 보존 4 · durable 5건(건드리지 않음)

## §11 중 4.1 (`#172`/`#173`) — `AGENTS.md` 5조 대조·이식

원전 `.agents/AGENTS.md` 21줄. 🔴 **조항마다 판정이 갈렸다** — 다섯을 뭉텅이로 옮기지 않았다.

| 원전 조항 | 우리 상태 | 판정 |
|---|---|---|
| **3조** 모호성 제거 | 🔴 **부분 누락** — 우리 건 *"설계 갈림길"* 만 다뤘다 | **이식** |
| **4조** 상세한 사전 설명 (검토 비용) | 🔴 없다 | **이식** |
| **5조** 직접 빌드·커밋 금지 | 커밋은 있다(의도적 완화) · 🔴 **빌드 조항 없음** | **부분 이식** |
| **1조** 임의 수정 금지 | 없다 | **범위 좁혀 이식** (사용자 결정) |
| **2조** 툴 사용 사전 동의 | 없다 | 🔴 **안 옮긴다** (근거 아래) |

### 🔴 3조가 이 세션에서 실제로 걸렸다 — 그래서 값이 측정된 이식이다

원전: *"사용자 입력이 **작업 지시인지 단순 질문인지** 모호한 경우, 임의로 해석하여 행동에 나서지
말고 반드시 질문을 던져 의도를 재확인하십시오."* 우리 규칙은 *"설계에 갈림길이 있으면 묻는다"*
뿐이었다 — **입력 자체의 모호성**은 안 덮었다.

실측: 같은 세션에서 `응` 이 **두 번** 왔다. 첫 번은 커밋 승인이었고 **두 번은 단순 수긍**이었다
(앞에 물음이 없었다). 두 번째를 승인으로 읽었으면 **다음 마일스톤 작업을 임의로 시작**했을 것이다.
🔴 이것은 원전이 *"1인칭 서술(「중간 커밋하고 올게」)을 나에게 내린 지시로 오독"* 해 사고를 낸 것과
**같은 계열**이고, 원전은 그 규칙을 **이미 문서로 갖고 있었다.**

### 1조 — 범위는 사용자가 정했다 (2026-08-14)

원전 1조는 *모든* 파일을 덮지만, 그 조항이 겨눈 조건은 **사람의 UE5 프로젝트를 에이전트가 직접
만지는 상황**이었다. 우리에게 그 조건이 실재하는 자리는 둘이고, 사용자가 그 범위를 골랐다:

    ① 자동 로드 문서   CLAUDE.md 전부 — 🔴 한 줄이 **모든 다음 세션의 행동**을 바꾼다
    ② 게임 소스        미러·워크트리·원격 체크아웃 (미커밋 .uasset 은 복구 불가)

도구 코드(`master/`·`docs/`·`reports/`)는 **커밋 승인 게이트**가 그 역할을 한다 — 커밋 전에는
아무것도 영구화되지 않는다. ⚠️ 이번 세션에 제가 자동 로드 문서를 **사전 동의 없이** 고쳤고
(§9 의 문서 정정 4곳), 그 사실이 이 범위를 고르는 근거로 쓰였다.

### 🔴 2조는 안 옮긴다 — 근거

*"단순 파일 읽기라도 몰래 툴을 호출해서는 안 된다."* 그 조항이 겨눈 조건은 **사람이 툴 호출을 볼
수 없는 에이전트**다. Claude Code 는 모든 툴 호출을 터미널에 띄우므로 *"몰래 호출"* 이 **구조적으로
불가능**하다 — 옮기면 카고 컬트다. ⚠️ 조항의 나머지 절반(*"무엇을 하려는지 사전에 간략히 설명"*)은
이미 관례이고 **4조 이식이 그것을 문서화**한다. 🔴 **재범위는 닫지 않는다** — 무인 잡(cron·타이머)
세션은 사람이 보지 않으므로 전제가 다르다.

## §12 테스트

    신규   master/test_attempt.py                 40/40   (실제 git · 실제 worktree)
    전체   2379/2379 통과 · 실패 파일 0개

## 남은 것

- **`#128` 빌드 게이트를 큐 잡으로** — 마스터가 attempt 를 올리면 작업장이 그것을 **claim →
  pull → UE 빌드/RunTests → 보고** 하고, 마스터가 `merge_verified` 를 부른다. 🔴 지금은
  `merge_verified` 를 부르는 **파이프라인 호출자가 없다** — 라이브러리와 실증만 있다
- ⚠️ **`integrate.py` 의 문구 대조**(`"nothing to commit"`) — 지금 자리에서는 맞지만 마스터로
  옮기면 깨진다. `#129`(경로 정리)에서 같이 볼 것
- ⚠️ **기계별 Gitea 신원 분리** — 네 대가 계정 `Sim` 하나라 서버측 브랜치 보호로 마스터를
  제한할 수 없다. 그것이 되면 가드를 클라이언트에서 서버로 옮길 수 있다. **사용자 결정 사항**
- 🔴 **`main` 에 서버측 보호가 없다**(`branch_protections` = `[]`). 위 항목과 묶여 있다
- 정리 대상으로 남긴 것: `ax-wt-probe-flowy` 워크트리 · 로컬/원격 probe 브랜치
  (🔴 **대화형 세션이 지우지 않는다** — 명령만 남긴다)

      git -C ~/ax-cluster/ModularStage/repo worktree remove ax-wt-probe-flowy   # 사람이 판단
      # 원격 probe 브랜치는 병합 안 됐으므로 훅이 거부한다 — 지우려면 사람이 Gitea UI 에서
