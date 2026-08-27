# 14. 신규 프로젝트 온보딩 런북

> [중요] **이 문서는 실행용이다.** 절차 조각이 `docs/5` · 마일스톤 문서에 흩어져 있던 것이
> `#256` 의 문제였다. 그래서 여기엔 **명령**과 **「안 됐으면 무엇이 안 보이나」**만 있다 —
> *왜* 그렇게 하는지는 [`12-multi-project.md`](12-multi-project.md)·[`13-request-tagging.md`](13-request-tagging.md)·
> [`5_5-project-isolation.md`](5_5-project-isolation.md) 에 있고, 실행에 그 문서가 **필요하지는
> 않다.**
>
> 사양(어느 스킬·MCP·이그노어가 어느 역할에 가는가)의 정본은 코드다:
> [`master/client/spec.py`](../master/client/spec.py). 표를 여기 두 벌로 만들지 않는다.

## 14.0 한 줄 요약

    서버 절  python -m master.projects.onboard <프로젝트>            ← 계획(읽기 전용)
             python -m master.projects.onboard <프로젝트> --confirm   ← 실행
    클라 절  python -m master.client plan|deliver|check <프로젝트>
    마운트   set_active_tool(<프로젝트>)                              ← 사람 승인 자리

[중요] **`--confirm` 없이는 아무것도 쓰지 않는다.** 이 저장소의 관례다(`cleanup plan|apply` ·
`finalize_work(confirm=False)` · `handover apply --confirm`).

## 14.1 서버 절 — 아홉 단계

`onboard` 가 **실측으로** 무엇이 남았는지 답한다. 순서는 코드가 강제한다(선결이 깨진 단계는
`[막힘]` 으로 나오고 **판정을 시도하지 않는다** — *"안 만들었다"* 와 *"만들 수 없었다"* 를
섞지 않기 위해서다).

| # | 단계 | 무엇 | 안 됐으면 무엇이 안 보이나 |
|---|---|---|---|
| 1 | `bare` | Gitea bare 저장소 | `onboard` 가 `[남음] bare` · 이 단계는 **`onboard` 가 못 만든다**(Gitea 에서 만든다) |
| 2 | `register` | 트윈 디렉토리 + `config.yaml` | 뒤 단계가 전부 `[막힘]` — 경로를 풀 수 없어 **아무것도 잴 수 없다** |
| 3 | `hook` | `post-receive.d/ax-index` + `ax-project-id` | push 해도 **트윈이 자라지 않는다.** 에러가 아니라 **침묵**이다 |
| 4 | `clone` | 트윈 안의 소스 워킹트리 | 뒤 단계가 전부 `[막힘]` |
| 5 | `guard` | 마스터 클론의 **pre-push 쓰기 가드** (`#125`) | [중요] **마스터의 오발 push 를 아무도 안 막는다** — `task/*` 밖 push · `main` 이동 · 미병합 삭제가 통과한다. 에러가 아니라 **침묵**이다 |
| 6 | `conventions` | 미러의 `CLAUDE.md` — **컨벤션의 원천** | 워커 매니페스트의 컨벤션이 **영구히 빈다.** 에러가 아니라 침묵이다 — 워커가 관례 없이 코드를 쓴다 |
| 7 | `graph` | 클래스·의존 그래프 | 검색이 클래스를 못 찾는다 (`classes=0`) |
| 8 | `synth` | 컨텍스트 MD (**`Source/` 한정**) | `N/M 그룹` 이 안 채워진다. [주의] 문서 **개수**가 아니라 **문서 없는 그룹 수**로 판정한다(`#274`) |
| 9 | `index` | 벡터·BM25 + 워터마크 | `last_indexed_commit` 이 빈 값 → 훅이 와도 **따라잡을 기준이 없다** |

> [중요] **`hook`(3)과 `guard`(5)는 다른 것이다.** 이름이 비슷해 **있는 줄 알았고, 그래서 NS 가
> 무방비로 돌았다**(`#330`, 실측 2026-08-28):
>
>     hook   Gitea **서버**의 post-receive — **받은** push 에 반응해 재색인을 트리거
>     guard  마스터 **자기 클론**의 pre-push — **나가는** push 를 막는다
>
> 하는 일이 정반대다. [주의] **`guard` 는 반드시 `clone` 뒤**여야 한다 — LFS 저장소를 클론하면
> git-lfs 가 자기 pre-push 훅을 그 자리에 넣는다(NS 가 그랬다). 먼저 깔면 클론이 덮는다.
>
> [중요] **이미 온보딩된 프로젝트도 이 단계로 낫는다** — 설치는 멱등이다:
>
>     AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm --only guard
>
> 가드가 없으면 `carry.publish` 가 push 직전에 **막는다**(`#329`, fail-closed) — 그 사유가
> 이 명령을 가리킨다.

### 1 · `bare` — Gitea 저장소 (온보딩 밖)

Gitea 웹 또는 API 로 만든다. [중요] **private 로 만든다** — 게임 소스다.
`onboard` 는 이 단계를 **확인만** 한다:

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트>
#   [완료] bare  … /var/lib/gitea/gitea-repositories/sim/<이름>.git
```

### 2 · `register` — 트윈 등록

MCP 도구다(마스터의 `ax-projects`, 포트 8103):

```
register_project_tool(name="NS", project_id="Sim/NS",
                      bare_path="/var/lib/gitea/gitea-repositories/sim/ns.git",
                      clone_url="gitea@192.168.0.57:Sim/NS.git", branch="main")
```

[중요] `project_id` 는 **훅이 보내는 이름**과 같아야 한다(`Sim/NS` — 대소문자는 무시되지만
**형식은 `소유자/저장소`**). 다르면 훅이 와도 어느 프로젝트인지 못 찾고 **조용히 건너뛴다**.

### 3~9 · 나머지는 한 명령

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm
# 끊어 돌리려면 (synth 는 LLM·시간을 태운다)
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm --only hook,clone,conventions,graph
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm --only synth --limit 5
```

[중요] **`hook` 은 무인으로 돈다** — `sudo -n /usr/local/bin/ax-install-hook --apply` 가
NOPASSWD 로 등록돼 있다(`#273`). 사람이 인증창을 누르는 단계는 없다.
[주의] 실행 뒤 `onboard` 가 **다시 재서** 찍는다 — 「했다」를 믿지 않는다.

[중요] **`conventions` 는 미러에 `CLAUDE.md` 를 놓는 단계다 (`#294`).** 워커 매니페스트의
컨벤션은 `<트윈>/repo/CLAUDE.md` 의 `## Code conventions` 절에서 오는데, 배달
(`master.client deliver`)은 각 기계의 **체크아웃**에만 가므로 미러는 이 단계가 채운다.
안 됐으면 파견된 워커가 **관례 없이 코드를 쓴다** — 에러가 아니라 침묵이라 산출물을 봐야 안다
(실측 2026-08-24: NS 미러에 파일이 없었고, ModularStage 는 사람이 놓아 둬서 **우연히** 돌았다).
판정은 「파일이 있다」가 아니라 **「절이 읽힌다」**다 — 절 이름이 계약(`WANTED_SECTIONS`)이라
파일만 있고 절이 없으면 매니페스트는 여전히 빈다.
[주의] **이미 있으면 덮지 않는다**(사람이 확정한 관례가 있을 수 있다). 미러도 더럽히지 않는다 —
프로젝트 `.gitignore` 에 `/CLAUDE.md` 가 있다고 기대할 수 없어(NS 는 UE 템플릿이라 없었다)
**`.git/info/exclude`** 에 넣는다. 소스의 `.gitignore` 를 고치는 것은 게임 소스를 건드리는 것이다.

## 14.2 클라 절 — 작업장 등재 → 클론 → 배달 → 대조

### 1 · 작업장 등재 (**`role` 을 반드시 준다**)

```
set_workshop_tool(name="NS", host="192.168.0.2",  driven="ssh", user="janus",
                  path="E:\\trunk\\NS",                    role="worker")
set_workshop_tool(name="NS", host="192.168.0.43", driven="ssh", user="sim",
                  path="/home/sim/trunk/NS",               role="worker")
set_workshop_tool(name="NS", host="192.168.0.33", driven="ssh", user="user",
                  path="C:\\Users\\USER\\Documents\\NS",   role="requester")
```

[중요] **`role` 을 빼면 기본값 `worker` 가 붙어 사람의 기계에 작업이 파견된다.**
`.33` 은 `requester` 다 — `drivable_hosts` 에서 제외되는 근거가 이 값이다.
안 됐으면: `deliver` 가 그 기계에 **워커 payload·스킬을 배달**하고, 파견이 그 기계로 간다.

### 2 · 체크아웃이 없는 기계 → 클론

`deliver` 가 체크아웃 없는 기계를 **부트스트랩 대상**으로 보고한다. 맞추는 것은 전환
동기화 경로다:

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from master.projects import logic; print(logic.sync_check('NS', align=True))"
```

[중요] 클론은 역할별로 갈린다 — **UE5 있는 기계만 LFS 실물**을 받는다(`.2` 134MB /
`.43` 포인터 4MB). 판정은 `ue5` **probe 실측**이다(선언이 아니다).
안 됐으면: `check` 가 `체크아웃 없음` 으로 남고, 그 기계는 파견 대상에서 조용히 빠진다.

[주의] **윈도우는 소유권 교정이 딸린다** — 마스터의 SSH 세션이 관리자라 `git clone` 이 만든
`.git` 이 `BUILTIN\Administrators` 소유가 되고, 사람의 세션에서 git 이 **전부 거부**한다
(`fatal: detected dubious ownership`, rc=128). `icacls /setowner` 로 맞춘다 — `safe.directory`
로 덮지 않는다(정상 저장소와 구분되지 않아야 한다).

### 3 · 배달 → 대조

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client plan    <프로젝트>   # 쓰지 않는다
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client deliver <프로젝트>
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client check   <프로젝트>
```

[주의] **`#277`(배달이 상주를 갱신하지 않는다)의 자리는 비었다** — `#320` 이 상주를 걷어
갱신할 프로세스가 없다. 배달은 이제 **파일을 놓는 것으로 끝난다.** 상주가 부활하면
「도는 것이 새 코드인가」가 다시 배달의 일부가 된다(그 사고: 옛 코드가 거절을 태스크로 읽고 폭주).

[주의] **마스터 트리가 dirty 면 `check` 가 통과하지 않는다** — 커밋이 같아도 그 커밋이 배달
내용을 다 말하지 못한다(`dirty_master`). **커밋이 먼저다.**

[중요] **여기서 규약이 같이 간다 — 사람이 옮겨 적을 것은 없다** (`#309`, 사용자 지시
2026-08-24: *"워커쪽에 기입되는 내용은 하나의 프로젝트에 디펜던시가 되지 않고, 신규 프로젝트를
등록한다고 할 때 셋업시 처리할 수 있도록 관리되어야 해"*). 이 명령 하나가 두 축을 같이 놓는다:

    역할 축 (프로젝트 무관)   `.claude/CLAUDE.md` 관리 블록 · 스킬 · 작업장 자산 · 클라 MCP
                             — 새 프로젝트에서 **글자까지 같다**
    프로젝트 축 (매번 생성)   블록의 「소스 트리 실측」 절(`.uproject`·Targets·Modules·빌드
                             명령·그 프로젝트만의 자산) + `.ax/config.json` 태그

[주의] **프로젝트 축을 본문에 적지 않는 이유**: 본문은 파일이 있으면 병합이 건드리지 않으므로
(사람 것을 지키는 규약) 첫 배달 때 굳어 늙는다. 블록은 매 배달마다 통째로 갈린다.

[주의] **`AX_PROJECTS_ROOT` 를 빼먹으면 블록이 조용히 거짓이 된다** — 종전에는 트윈 경로 해석
실패를 삼켜 *"`.uproject` 를 찾지 못했다"* 로 렌더했다(`#309` 에서 고쳐 지금은 사유가 표에
찍힌다). 위 명령줄에 그 변수가 붙어 있는 것이 우연이 아니다.

### 4 · 상주 등록 — **없다** (`#320`, 2026-08-27)

🔴 [중요] **이 단계는 사라졌다. 워커에 켤 것이 없다.** `.2` 의 schtasks `AxClaimer_NS` 와 `.43`
의 `*/5` cron 감시자를 **둘 다 걷었고**, 선언이던 `client/init/residency.py` 도 지웠다. 지금
**큐를 폴링하는 프로세스는 어느 워커에도 없다.**

    빌드   마스터가 `run_build_on_workshop` 으로 `Build.bat` 를 직접 부른다
           → 워커에 **파이썬 페이로드가 필요 없다**
    추론   마스터가 `infer run` 으로 민다

[주의] **그래서 온보딩이 끝나도 워커는 조용하다 — 정상이다.** 등재해도 아무도 집지 않는다.
종전 이 자리엔 *"태스크를 등록해도 아무도 집지 않으면 상주의 체크아웃을 보라"* 가 있었는데,
지금은 **집는 주체 자체가 없는 것이 설계**다. 버그로 오진하지 않는다.

[중요] **부활하면 같이 부활하는 것이 넷이다** — `#312`(사람이 끊는 구간을 없앤다) ·
`#314`(일시정지·재개) · `#315`(감시자 생존 확인) · `#316`(한 기계 상주 2개). 넷 다 **고쳐서**
닫힌 것이 아니라 대상이 사라져 **소멸**로 닫혔다. 되살릴 때 그 노트부터 읽는다.
그리고 `#311` 의 ⓐ 규칙(**상주는 마운트를 따른다 — 한 기계에 두 프로젝트를 동시에 켜지
않는다**)은 결정으로 살아 있다. 근거: claim 정책이 `MOUNT` 라 비마운트 claim 은 거르는 것이
아니라 **거절**된다(실측 2026-08-25 · 마운트 NS).

    project="NS"            → 204            정상 (큐가 비었다)
    project="ModularStage"  → 200 ok:false   status=not_mounted
    project=""              → 200 ok:false   status=no_project_tag

부활 조건과 철거 실측은 `#320` 노트에 있다.

## 14.3 마운트 — 마지막, 사람 승인 자리

```
set_active_tool("<프로젝트>")            # align=True 면 3대 재배달까지 맞춘다
```

[중요] **마운트는 동시에 하나다** (§5.5.2). 마운트 밖 프로젝트의 **쓰는** 요청은
`200 + ok:false` 로 거절된다 — 사유가 셋이다(`no_project_tag`·`not_mounted`·
`project_mismatch`). → [`13-request-tagging.md`](13-request-tagging.md)

[중요] 전환은 **인계**다 — 떠나는 프로젝트에 남는 것을 다섯 부류로 낸다. 미종결 work 가 있으면
**거부**된다:

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.handover survey <프로젝트>   # 조사
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.handover plan   <프로젝트>   # 계획
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.handover apply  <프로젝트> --confirm
```

[주의] **미종결·`failed`·미병합 durable 은 지우지 않는다**(사용자 결정 2026-08-23) — 증거를
지우면 왜 실패했는지 다시 물을 수 없다. 그것들은 사람이 종결시킨다.
안 됐으면: 전환은 되는데 그 work 의 기록·신호가 **새 프로젝트 트윈에 착지**한다.

## 14.4 전체 확인 — 세 줄

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트>   # 서버 9단계 + 3대
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client check <프로젝트>       # 배달본 해시 대조
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.ontology status               # 도메인·stale 판정
```

[중요] **`ontology status` 의 「판정 불가」를 「최신」으로 읽지 않는다** (`#275`) — 이관 문서
1,010/1,055 건에 `source_commit` 이 없어 **비교할 근거가 없다.** 그 값은 소스가 바뀌어
재합성될 때 붙는다.

## 14.5 [주의] 이 런북이 만들어지며 드러난 구멍 둘

절차를 명령으로 적으려 하자 **실행 표면이 없는 자리**가 나왔다 — 산문으로만 적었으면 안 보였다.

    onboard CLI 없음     `run` 이 *"python -m master.projects.onboard <name> --confirm"* 을
                         안내하는데 **그 명령이 존재하지 않았다**(라이브러리뿐). 그래서 절차가
                         문서가 아니라 **세션의 기억**에 살았다 → 만들었다
    role 을 못 준다      `logic.set_workshop` 엔 `role` 이 있는데 **MCP 도구가 안 열어 뒀다**.
                         즉 `requester`(사람의 기계)를 문서화된 표면으로 등재할 수 없었다 →
                         열었다. 기본값(`worker`)에 기대면 사람 기계에 파견이 간다
