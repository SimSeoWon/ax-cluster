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

    전체     python -m master.projects.onboard <프로젝트>            ← 서버·클라 계획(읽기 전용)
             python -m master.projects.onboard <프로젝트> --confirm   ← 서버 실행 → 전 작업장 배달·대조
    진단     python -m master.client plan|check <프로젝트>            ← 클라만 읽기 전용으로 확인
    마운트   set_active_tool(<프로젝트>)                              ← 사람 승인 자리

[중요] **`--confirm` 없이는 아무것도 쓰지 않는다.** 이 저장소의 관례다(`cleanup plan|apply` ·
`finalize_work(confirm=False)` · `handover apply --confirm`).

[중요] 전체 실행은 서버 절이 끝난 뒤 등록된 모든 SSH 작업장에 `deliver`하고 곧바로 **전체
`check`**를 돈다. 버전 스탬프만 같아도 `AGENTS.md`·스킬·페이로드·MCP 중 하나가 빠지면
온보딩은 실패다. `--only hook,clone`처럼 서버 단계만 지정한 복구 실행은 클라를 건드리지 않는다.

## 14.1 서버 절 — 열 단계

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
| 6 | `profile` | 🔴 **사람만 아는 것**을 받아 적립한다 (`#650`) — 엔진 확정 여부·엔진·버전·언어 정책·용도·장르·**왜 존재하는가** 한 문단. 적립처는 `payload/profile/<P>.yaml`(git 관리). 물을 문장은 `project_profile` 이 주고, 답은 `set_project_profile` 로 적립한다. [중요] **이 단계는 자동으로 안 끝난다** — 측정으로 안 나오는 값이라 사람이 답해야 한다. [주의] 측정 가능한 것(EngineAssociation·모듈·확장자 분포)은 **질문할 때 근거로만** 보여 주고 저장하지 않는다 (`#294`: 규약은 결정이지 측정이 아니다) | 🔴 **그 프로젝트에 분산 작업을 등재할 수 없다** — `register_work` 가 거절한다. 그리고 배달되는 `CLAUDE.md` 의 첫 문단이 *"프로젝트 서술이 비어 있다"* 로 남는다. [중요] 그 공백을 지휘자가 **다른 문서로 메우다** 남의 프로젝트 설명을 사실로 읽는다 (실측 2026-09-20: `.33` 의 NS 콘솔이 ModularStage 의 *"multiplayer · Listen Server"* 를 NS 의 사실로 읽었다, `#649`) |
| 7 | `conventions` | 미러의 `CLAUDE.md` — **컨벤션의 원천**. [중요] **정본에서 와야 한다** (`payload/claude_md/<P>.md` 또는 `<트윈>/claude_md.md`) — 정본이 없으면 이 단계는 `[남음]` 이다 | 워커 매니페스트의 컨벤션이 **영구히 빈다.** 에러가 아니라 침묵이다 — 워커가 관례 없이 코드를 쓴다. [중요] **더 나쁜 경우**: 정본 없이 통과하면 골격+실측이 규약 자리에 굳어 워커가 그것을 계약으로 받는다 (NS 실측 2026-09-01: *"한글 주석 0개 → 주석은 영문"* 이 골조 계약과 충돌) |
| 8 | `graph` | 클래스·의존 그래프 | 검색이 클래스를 못 찾는다 (`classes=0`) |
| 9 | `synth` | 등록된 `source` 경계의 컨텍스트 MD (UE 기본값 `Source/`) | `N/M 그룹` 이 안 채워진다. [주의] 문서 **개수**가 아니라 **문서 없는 그룹 수**로 판정한다(`#274`) |
| 10 | `index` | 벡터·BM25 + 워터마크 | `last_indexed_commit` 이 빈 값 → 훅이 와도 **따라잡을 기준이 없다** |

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

### 3~10 + 클라 배달·대조 · 나머지는 한 명령

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm
# 끊어 돌리려면 (synth 는 LLM·시간을 태운다)
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm --only hook,clone,conventions,graph
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트> --confirm --only synth --limit 5
```

첫 명령은 서버 10단계 뒤 §14.2의 등록된 작업장 전부를 `checkout → deliver → check`까지
이어 간다. 따라서 신규 프로젝트에서 별도의 `master.client deliver`는 정상 절차가 아니다.

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
위 게임 프로젝트 예에서 `.33`은 `requester`다 — `drivable_hosts`에서 제외되는 근거가 이 값이다.
역할은 프로젝트별이다. AXCluster에서는 `.57`이 요청자이고 `.2`·`.33`·`.43`이 워커다.
`.33`은 게임 트리 대신 `C:\trunk\AXCluster`를 사용한다.
안 됐으면: `deliver` 가 그 기계에 **워커 payload·스킬을 배달**하고, 파견이 그 기계로 간다.

### 2 · 체크아웃이 없는 기계 → 클론

`plan`은 체크아웃 없는 기계의 클론 계획을 보여 주고, `deliver`는 먼저 체크아웃을
**부트스트랩한 뒤 다시 프로브하여 배달**한다. 부트스트랩에 실패한 호스트는 실패로 기록하고
그 호스트의 배달은 건너뛴다. 신규 프로젝트 전체 구성은 §14.1의 `onboard --confirm`을 따른다.
전환 동기화 경로를 별도로 사용할 때는:

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

#### 워커 한 대 신규 설치·경로 이전

체크아웃 루트를 새로 정하거나 옮길 때는 `setup-host`를 사용한다. 프로젝트 인자는 받지 않고
마운트된 프로젝트를 대상으로 한다. `--host`와 `--root`는 필수이며 계정은 `--user`로 지정할 수 있다.
기본은 계획만 출력하고, `--confirm`으로 등록부 경로 변경 → 낡은 상주 해제 → 클론·배달 → 대조를 수행한다.

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client setup-host --host=<ip> --root=<경로>
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client setup-host --host=<ip> --root=<경로> --confirm
```

### 3 · 배달 → 대조

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client probe   <프로젝트>   # 읽기 전용 실측
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client plan    <프로젝트>   # 쓰지 않는다
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client deliver <프로젝트>
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client check   <프로젝트>
```

저장소 변경 뒤에는 **마운트된 프로젝트**의 작업장을 같은 HEAD로 맞춘다. 프로젝트는 사람이 고르지
않는다 — 마운트(`projects.yaml` 의 `active`)가 정한다:

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client update         # 마운트된 프로젝트만
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client update --all   # 등록 전체 (종전 기본)
```

🔴 2026-10-06 부터 기본은 마운트 하나다(`#655`·`#745`, 사용자 결정) — 등록 전체가 5개 × 3대라 한 번에
15~20분이 걸렸다. 비마운트 프로젝트는 **마운트 전환 때** 맞춘다: `set_active` 가 그 프로젝트의 기계를
마스터 버전과 대조해 뒤처진 기계만 재배달한다(기본 `align=True`, 보고만 원하면 `align=False`).
마운트가 비어 있으면 폴백 없이 멈춘다(rc 2). `--all`은 `Registry.names` 전체에 먼저 배달한 뒤, 배달에 성공한 프로젝트 전부를 다시
검사한다. 뒤 프로젝트의 배달이 앞 프로젝트의 전역 설정을 덮는 경우까지 종료 상태에서 확인하기
위해서다. 신규 프로젝트도 등재되는 순간 자동 포함되며, 한 프로젝트의 배달이 실패해도 나머지는
시도한다. 하나라도 실패하면 전체 rc=1이다. 신규 프로젝트 최초 구성은 위 §14.1의
`onboard --confirm`이 checkout→deliver→check까지 수행하므로 별도 수동 배달을 끼우지 않는다.

[주의] **마스터 트리가 dirty 면 `check` 가 통과하지 않는다** — 커밋이 같아도 그 커밋이 배달
내용을 다 말하지 못한다(`dirty_master`). **커밋이 먼저다.**
[주의] **배달본의 출처 커밋이 마스터 HEAD 보다 뒤처져도 `check` 는 실패한다** — 파일 해시가
모두 같아도 그렇다(`master/client/__main__.py` 의 `behind` 판정). 저장소가 전진했으면 `update` 로
다시 배달한다.

`update`는 시작·검사 직전·종료 시점의 마스터 HEAD와 dirty 상태를 관측한다(`#737`).
시작부터 dirty여도 경고 후 배달은 계속하므로, 실행 전에 먼저 커밋한다. 실행 중에는 마스터에
커밋하거나 작업 트리를 수정하지 않는다. 관측된 HEAD 이동이나 clean→dirty 변화가 있으면
검사가 통과했어도 전체 rc=1이다. 자동 재실행이나 커밋 잠금은 하지 않는다. HEAD가 움직였으면
다시 실행하고, dirty해졌으면 먼저 커밋한 뒤 다시 실행한다. 서비스 재기동은 기존 승인 절차를 따른다.

`config.json`의 `checkout.branch`는 해당 프로젝트 레지스트리의 기본 브랜치를 따른다(`#260`).
배달은 체크아웃 안의 `.agents/skills`와 `.codex/config.toml`도 구성·대조한다(`#699`).
홈의 동명 스킬만 있는 상태를 정상 배달로 판단하지 않는다.
프로필이 색인 전용 또는 `kind: code`인 프로젝트는 루트 `CLAUDE.md`·`AGENTS.md`에 관리 블록을
쓰지 않고 기존 사람 파일을 보존한다. Claude의 ax-client는 `.mcp.json` 대신 해당 체크아웃의
로컬 스코프(`~/.claude.json`)에 등록하며, `check`도 그 등록을 대조한다.
`check`는 그 밖에도 네 가지를 대조한다.
- Windows에서는 Python 절대경로를 확인한다. 경로를 못 찾았으면 Codex 로컬 도구를 실행할 수 없으므로 실패다.
- 워커 클론이 원격에서 지운 브랜치의 원격추적 ref를 남기지 않는지 본다(`fetch_prune`, `#787`).
- 워커의 agy 호출이 `--model`로 넘길 정본 id가 배달됐는지 본다(`#830`).
- `~/.agents/skills`에 남은 우리 이름의 홈 중복 스킬은 실패로 치지 않는다. 프로젝트 로컬 정본이 우선하므로 `[주의]`로만 보고한다.

한 대만 먼저 보거나 사람 기계를 빼려면 `probe`·`plan`·`deliver`·`check`에 `--host=<ip>`를 준다(`#407`). 값은 레지스트리의 호스트와 정확히 일치해야 한다. 모르는 호스트를 주면 0대에 조용히 배달하지 않고 거절한다.
소스 동기화와 payload 배달은 별도다. 작업장 소스가 `main`·clean인지 확인하고
`fetch → merge --ff-only`로 승인된 커밋을 맞춘 뒤 배달 출처와 함께 대조한다.

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

### 4 · 상주 없음 — 배달은 금지 등록을 해제한다 (`#861`)

워커·요청자에 상주 데몬은 없다 — 서버(.57)가 SSH 로 총괄한다(사용자 확정 2026-10-31, `#860`).
별도 수동 단계는 없고 `deliver`/`onboard`가 아래 상태를 맞춘다(`#861` `bbd0110`).

    모든 kind · 모든 역할       미등록 — `AxWorker`/`AxClaimer` 상주를 등록하지 않는다
    Windows worker             `AxConductor_<project>` 로그인 런처만(/IT /RL LIMITED) —
                               파견 때 서버가 `schtasks /run` 으로 그때만 건다
    과거 등록 잔재              프로젝트 이름 무관(`AxWorker*`·`AxClaimer*` · `worker_daemon`/`claimer` cron) — `deliver`가 전부 해제·재조회, `check`는 실행 중 데몬 프로세스도 FAIL
    `check`                    잔재가 있거나 등록 조회 자체가 실패하면 FAIL(조회 실패 ≠ 없음)

폐기 페이로드 `work/worker_daemon.py`·`work/ax_safety.py`의 배달 사본도 정리 대상이다.
현재 배달 대상인 경로는 보존하고, 나머지는 `deliver`가 제거 후 되읽어 확인한다.
`check`는 폐기 사본이 남았거나 조회 자체가 실패하면 해당 호스트를 FAIL로 판정한다.

`ensure`는 아무것도 하지 않는다. 데몬 소스(`worker_daemon.py`·`buildjob.py`)는 지웠고
(`#861` T3, `9a195e0`) `master/test_no_worker_daemon.py`가 부활을 막는다.
과거 NS 상주 실측을 AXCluster의 상태로 읽지 않는다.

🔴 [중요] **다만 「등재해도 아무도 집지 않는다」는 2026-09-01 부터 틀리다** (`#340`, `c33316e`).
파견은 **자동**이다 — 요청자가 `task/<work_id>/base`를 push하면 그 이벤트가
`ax-dispatch.path`를 깨운다. 조각 완료 뒤 요청자가 `ax-advance`로 통합·검사하고,
**사람 승인 뒤 ⑺ 전진**한다. `main` 반영은 별도의 **finalize 승인**이다.
게임 요청자는 `.33`, AXCluster 요청자는 `.57`이며 통합자를 따로 두지 않는다.
[주의] 자동 파견 트리거도 별도 축으로 살아 있다. 온보딩 뒤에는 상주 잔재가 없는지뿐 아니라
**「트리거 유닛이 무장돼 있나」**도 확인한다:

    systemctl is-enabled ax-dispatch.path ax-dispatch.timer     둘 다 enabled 여야 한다
    journalctl -u ax-dispatch -u ax-dispatch-catchup -n 30      「안 건 이유」도 찍힌다

[주의] **침묵은 정상이 아니다.** 골조를 올렸는데 `[dispatch]` 줄이 하나도 없으면 배선이 죽은
것이다 — 그 침묵이 2026-08-29~31 이틀을 태웠다(리포트 44 §1).
[주의] 세션 한도로 멈추면 **재개는 사람 지시**다(사용자 결정 2026-09-01) —
`.33` 세션 시작 훅이 「재개 대기」를 고지하고, 푸는 것은
`python -m master.work.autodispatch --resume <프로젝트> <work_id>` 뿐이다.

[중요] claim 정책은 여전히 `MOUNT`라 비마운트 claim은 거르는 것이 아니라 **거절**된다
(실측 2026-08-25 · 마운트 NS). 다만 이 정책은 **더 이상 상주를 정하지 않는다** — 상주 자체가 없다.

    project="NS"            → 204            정상 (큐가 비었다)
    project="ModularStage"  → 200 ok:false   status=not_mounted
    project=""              → 200 ok:false   status=no_project_tag

이력: 철거 `#320`, 복원 `#401`·`#405`(리포트 63)은 2026-10-31 철회됐다(`#860`·`#861`).
`#311` ⓐ 「상주는 마운트를 따른다」는 그 복원기의 규칙으로 기록에만 남는다.

#### Codex 준비 검사와 실제 실행

Windows Codex 준비 검사는 SSH Session 0에서 `codex sandbox`를 실행하지 않는다.
`AxConductor_<project>` XML의 InteractiveToken·LeastPrivilege·활성화·계정/SID·
Python 절대경로·배달 런처 경로를 확인한다. 이 등록 검사는 인증·현재 로그인·실제 도구 실행을
보장하지 않는다. `/IT /RL LIMITED` 로그인 사용자 세션에서 셸 읽기·`apply_patch` 수정·
내용 재독해·결과 회수를 별도로 확인한다. 고정 SessionId=1을 요구하지 않는다.
실행 계약과 `.ax` 쓰기 실패의 미확정 범위는
[Windows Codex 원격 실행](windows-codex-remote.md)·[리포트 89](../reports/89-codex-worker-readiness-and-write-probes.md).
모드는 `ax-mode`의 공용 조회/변경 도구를 사용하며 기존 work의 모드 스탬프에는 소급되지 않는다.

#### Claude 준비 검사와 재로그인 (`#721`)

지휘자 모드가 `claude`이면 준비 검사와 실제 실행 직전에 워커에서 `claude auth status`를 확인한다
(`master/work/conductor_auth.py`). 결과는 워커 계정 홈의 `.cache/ax-dispatch/claude-auth.json`에
시각·성공 여부·정규화한 사유로 남고, **검사 후 24시간 미만이면 성공·실패를 그대로 재사용한다**
(달력 날짜 기준이 아니다). Windows도 해당 계정 홈의 같은 상대 경로다. 기록 누락·손상·미래 시각·
계정 불일치는 재검사한다. 인증 복구 로그인은 **자동으로 하지 않는다**.

실패하면 사람이 그 워커에서 다시 로그인한다:

    .43(헤드리스)  ssh sim@192.168.0.43 → claude auth login
                   인증 페이지는 사람의 PC 브라우저에서 연다(TTY 는 사용자 터미널)
    Windows       해당 계정(janus / user)으로 claude auth login

로그인 뒤 실패 캐시가 남아 있으므로 **강제 재검사**로 캐시를 갱신한다:

```python
from functools import partial
from master.work.conductor import worker_mode_readiness
from master.work.conductor_auth import check_claude_auth
worker_mode_readiness("claude", "<프로젝트>",
                      auth_checker=partial(check_claude_auth, force=True))
```

실측 2026-10-06 00:13–00:17 (`cf9e268` 배포 후 `.2`·`.33`·`.43`): 첫 검사가 캐시를 저장했고
`.43` 이 로그아웃 상태(`loggedIn=false`, `expiresAt=0`)로 발견됐다. 캐시 재사용을 확인한 뒤
사용자가 `ssh sim@192.168.0.43` 에서 `claude auth login` 을 실행했고(브라우저는 PC), 강제 재검사
3/3 통과. [주의] **실행 중 인증 실패의 즉시 고지 경로는 아직 라이브로 검증하지 않았다.**
근거·구현: [리포트 96](../reports/96-worker-claude-auth-cache.md).

`code` 통합 검사는 프로젝트 프로필의 검사 계약을 읽는다. AXCluster는
`tests/integration/checks.json`에 명시된 스크립트를 별도 프로세스로 실행한다.
검사 방법과 최신 배포 실측은 [리포트 90](../reports/90-r5-indexer-test-isolation-and-deployment.md).

### 5 · 요청자 에디터 — Unreal MCP (UE5 프로젝트만)

요청자(`role=requester`)는 **에셋을 만들어야 한다** — PP 머티리얼·PPV·InputAction·DataTable·
위젯 BP 는 에디터 밖에서 만들 수 없다. 마스터는 그 자리에 못 간다(SSH 는 세션 0 이고 데스크톱이
없다). 그래서 **그 기계의 `claude` 가 에디터 안의 MCP 서버에 로컬로 붙는 것**이 설계된 경로다.

`<체크아웃>/<이름>.uproject` 의 `Plugins` 에 둘을 켠다:

```json
{ "Name": "ModelContextProtocol", "Enabled": true, "TargetAllowList": ["Editor"] },
{ "Name": "EditorToolset",        "Enabled": true, "TargetAllowList": ["Editor"] }
```

[중요] **`TargetAllowList` 를 `Editor` 로 묶는다.** `ModelContextProtocol`(에디터 UI 의 이름은
**"Unreal MCP"**, 5.8 1st-party)은 Runtime 모듈도 갖고 있어서 안 묶으면 **패키징에 실려 나간다** —
인증 계층이 없는 서버다.

나머지는 사람이 에디터에서 한다: 재시작 → `Editor Preferences > General > Model Context Protocol`
의 **Auto Start Server** → 콘솔 `ModelContextProtocol.GenerateClientConfig Claude` 로 그 기계의
`claude` 에 서버를 등재 → `claude` 재시작.

[완료] **`.mcp.json` 을 둘이 같이 쓴다 — 서로 지우지 않는다** (실측 2026-08-29). UE 는 그 파일에
`unreal-mcp` 를 **병합해** 넣고(`ax-client` 가 남는다), 배달의 `merge_mcp_json` 도 ax-client 항목만
넣고 나머지를 보존한다(깨진 JSON 이면 덮지 않고 멈춘다). 리스너는 `127.0.0.1:8000` 이어야 한다 —
`0.0.0.0` 이나 LAN IP 로 잡히면 **인증 없는 서버가 LAN 에 열린 것**이므로 포트 설정을 되돌린다.

[중요] **마스터는 이 서버에 붙지 않는다.** loopback 전용 + non-loopback `Origin` 거부 + 인증 없음이고
Epic 이 *"not safe to expose beyond the local machine"* 이라고 적었다(리포트 05 에서 확정). SSH
터널로 끌어오는 길은 미검증이고 **설계하지 않는다**(`docs/5_5-project-isolation.md` §Unreal MCP).

[주의] 도구를 공급하는 것은 **툴셋**이다 — `EditorToolset` 이 최소이고 필요할 때 한 줄씩 늘린다
(`UMGToolSet` 위젯 BP · `GameplayTagsToolset` · `ConfigSettingsToolset` · `AutomationTestToolset`).
`AllToolsets` 는 한 줄이지만 Experimental 25종을 프로젝트에 영구히 끌어온다. **머티리얼 전용
툴셋은 없다**(5.8 목록 실측) — PP 머티리얼은 사람이 만드는 편이 확실하다.

안 됐으면: `Edit > Plugins` 에 "Unreal MCP" 가 없거나, 있어도 `claude` 의 MCP 목록에 그 서버가
안 보인다. 후자는 `GenerateClientConfig` 를 안 한 것이다.

[완료] **`#335` 로 코드가 됐다** (2026-08-30) — `uproject` 는 여전히 게임 소스라 `deliver` 가
만지지 않는다. 대신 **동의 게이트가 있는 별도 명령**을 만들었다:

```
python -m master.client uproject <프로젝트>            계획만 (쓰지 않는다)
python -m master.client uproject <프로젝트> --confirm  요청자의 .uproject 에 쓴다
```

선언은 `<트윈>/config.yaml` 의 `init.uproject_plugins` 이고 **기본값은 비어 있다** — 선언하지
않은 프로젝트를 건드리지 않는다. `TargetAllowList` 가 빈 항목은 **거부**한다.
[중요] **사람 단계는 순서가 있다 — 재시작이 먼저다.** 재시작 전에는 플러그인이 로드되지 않아
아래 항목이 화면에 **없다**(실측 2026-08-30: 그래서 *"에디터에 설정에 해당 옵션 없는데?"* 가 났다):

    1. 에디터 재시작
    2. `Edit > Plugins` 에 **"Unreal MCP"** 확인 (`ModelContextProtocol` 로는 안 보인다)
    3. `Editor Preferences > General > Model Context Protocol` → Auto Start Server
    4. 콘솔 `ModelContextProtocol.GenerateClientConfig Claude`
    5. `claude` 재시작

라이브 확인(2026-08-30 `.33`): `TCP 127.0.0.1:8000 LISTENING` — **loopback 전용**이고
`.mcp.json` 에 `ax-client` 와 공존한다. 마스터에서는 연결되지 않는다(설계대로).

[완료] **이제 세션이 스스로 안다** (`#374`, 2026-09-06) — `.claude/hooks/editor_mcp.py` 가
세션 시작에 한 줄을 낸다(`pending_works.py` 가 부른다). 🔴 **「포트 열림」과 「이 세션이
붙었다」는 다르다**: MCP 는 세션 시작에 한 번만 붙어서, **세션보다 늦게 켠 에디터에는 못
붙는다**(2026-09-05 에 그것을 모른 채 작업했다). 그래서 훅은 세션 시작에 재서 적어 두고,
나중 턴에는 그 기록과 비교해 `붙음 / 꺼짐 / 🔴 열렸지만 이 세션은 못 붙었다` 를 가른다.
[중요] **막지 않는다 · 대신 켜 주지 않는다** — 고지만 하고, 기동은 사람의 결정이다.
지금 서버만 다시 재려면 `py .claude/hooks/editor_mcp.py`.
[중요] **실증은 `<체크아웃>/.ax/editor_mcp.log` 로 한다** — 세션 시작 1건 + 판정이 바뀐 턴만
한 줄씩(JSON, 최근 200줄). **조용한 세션 시작도 남으므로**(`spoke:false`) 「훅이 돌았나」와
「무슨 판정이었나」를 사람 세션을 방해하지 않고 되짚을 수 있다.
🔴 [중요] **재연결이 필요한 경우는 하나뿐이다 — 「세션 시작에 서버가 없었을 때」** (실측
2026-09-06, 가짜 MCP 서버로 6회):

    세션 시작에 붙어 있었다  3초 중단 ✅ · **75초 중단 ✅**  → 리빌드는 **사람이 할 일이 없다**
    세션 시작에 없었다      2초 ✅ · **10 · 20 · 55 · 170초 ❌ 도구없음** → `/mcp reconnect` 필요

[주의] **종전 서술 「세션 시작에 한 번만 붙고 자동 재시도가 없다」는 폐기됐다.** 원전 런북
§12-5 를 지금 도구로 재보지 않고 옮긴 것이 출처였다.
즉 위 §12-5 인용(*"도구가 안 보이면 세션 재시작"*)은 **지금 도구에서는 과한 처방**이다 —
필요한 것은 `/mcp reconnect <서버>` 이고, 그것마저 리빌드 경로에는 필요 없다.

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

## 14.4 전체 확인

```bash
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard <프로젝트>   # 서버 10단계 + 등록 작업장
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client check <프로젝트>       # 배달본 해시 대조
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client update                  # 마운트된 프로젝트를 현재 HEAD로 (--all = 등록 전체)
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.ontology status               # 도메인·stale 판정
```

[중요] **`ontology status` 의 「판정 불가」를 「최신」으로 읽지 않는다** (`#275`) — 이관 문서
1,010/1,055 건에 `source_commit` 이 없어 **비교할 근거가 없다.** 그 값은 소스가 바뀌어
재합성될 때 붙는다.

### RAG 검색 로그 확인

배달·서비스 반영 뒤 [RAG 검색 로그](http://192.168.0.57:8103/rag-logs)에서 대상 프로젝트를 선택한다(`#837`).

1. 실제 사용자 명령으로 검색할 때 `task_type="user_command"`, `user_request`에는 실제 입력을 그대로 전달한다.
   같은 명령의 후속 검색에는 반환 `request_id`를 재사용한다. 원문을 못 받았으면 미수집으로 남긴다.
2. 반환 `search_id`로 `/rag-logs?search_id=<검색ID>`를 열어 원문·LLM 질의·확장/실제 질의·결과 순위와 본문을
   저장 로그와 대조한다. 요청 전체는 `request_id` 필터, 조회 API는 `/api/v1/rag-logs`다.
3. 한 요청의 여러 검색, 결과 없음·오류·작업 분류 필터, 메뉴 재진입을 확인한다. 날짜는 저장된 시각의
   기록일 기준이며 현재 서버는 KST다. `context_synthesis`처럼 사용자 원문이 없는 자동 작업도 구분한다.

원문 자동 캡처는 현재 Claude UserPromptSubmit 훅의 `.ax/rag_requests/<request_id>.json` 경로다.
Codex/native MCP는 실제 원문을 명시 전달하며, 전체 CLI 자동 캡처가 있다고 가정하지 않는다.
원본 로그는 `<트윈>/search_logs/YYYY-MM-DD.jsonl`에 자동 삭제 회전 없이 누적하고 기존
`search_log.jsonl`은 최근 2,000건 캐시로 유지한다. 기록 실패는 반환값·서버 로그로 확인한다.

배달 성공과 실행 서비스 반영은 별개다. `master.client check <프로젝트>`는 마스터 서비스 신선도
실패를 전체 실패에 포함한다. 반면 서비스 의존 모듈 변경은 재기동 권장 `[주의]`로만 표시하며,
그 자체로 검사 실패나 종료 코드에 반영하지 않는다(`#918`). 신선도 조회 자체가 실패한 경우도
정상으로 간주하지 않고 전체 실패에 포함한다.
서비스 신선도 실패나 의존 모듈 변경 경고를 보고하고, 재기동은 기존 승인 절차에 따라
승인 후 `scripts/ax-service-restart <유닛>`을 실행해 기동 시각·상태를 확인한 뒤 재검사한다.
`check`는 서비스를 자동 재기동하지 않는다. 검사를 통과시키려고 원격 파일이나 서비스 상태를 임의 수정하지 않는다.

**현재 운영 단계는 로그 수집이다.** 한글 질의 품질과 적중률은 이후 표본에 정답 문서·관련성 판정을
붙여 평가한다. 결과가 있다는 사실을 적중으로 세지 않으며, 근거 없이 검색 설정을 바꾸지 않는다.

## 14.5 [주의] 이 런북이 만들어지며 드러난 구멍 셋

절차를 명령으로 적으려 하자 **실행 표면이 없는 자리**가 나왔다 — 산문으로만 적었으면 안 보였다.

    onboard CLI 없음     `run` 이 *"python -m master.projects.onboard <name> --confirm"* 을
                         안내하는데 **그 명령이 존재하지 않았다**(라이브러리뿐). 그래서 절차가
                         문서가 아니라 **세션의 기억**에 살았다 → 만들었다
    role 을 못 준다      `logic.set_workshop` 엔 `role` 이 있는데 **MCP 도구가 안 열어 뒀다**.
                         즉 `requester`(사람의 기계)를 문서화된 표면으로 등재할 수 없었다 →
                         열었다. 기본값(`worker`)에 기대면 사람 기계에 파견이 간다
    요청자 에디터 없음    UE5 프로젝트인데 **요청자가 에셋을 만들 수 있게 하는 단계가 없었다**.
                         NS 는 2026-08-22 온보딩을 마쳤는데도 에셋 작업 경로가 열려 있지 않았고,
                         2026-08-29 상호작용 작업에서 드러나 §14.2-5 가 신설됐다
