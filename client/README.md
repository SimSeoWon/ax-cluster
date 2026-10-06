# `client/` — 클라이언트에서 도는 것 · 클라에 설치되는 것

[중요] **2026-08-22 부터 여기에 실물이 있다** (#263) — 그전까지 이 파일은 *"표지판만 있는 자리 ·
코드도 자산도 여기 없다"* 였고, 그 표지판이 `client` 를 **세 뜻**으로 만들었다(빈 표지판 ·
`master/client/` 배달기 · `master/clientside/` 클라 런타임). 기준은 **어디서 도는가**이고,
`master/` 는 이 인프라 서버(`.57`)에서 도는 코드다. → `docs/12-multi-project.md` §12.5-e

    client/runtime/     클라 기계에서 도는 코드 — client_mcp.py · ontology_cache.py
    master/client/      배달기 (SSH 를 쏘는 쪽이니 마스터가 맞다)

[주의] **빌드 사슬은 `master/` 에 남았다** (사용자 결정 ⓒ, 2026-08-22):
`work/build_local.py` → `layer3_verify` 인데 그 `layer3_verify` 를 **마스터도** 쓴다
(`work/skeleton_gate.py` 가 `run_build_on_workshop` 으로 `.2` 에 SSH 빌드를 민다).
옮기면 상대 임포트가 끊기거나 배달 때문에 저장소 코드를 고쳐야 한다.
[주의] 종전 근거였던 `claimer.py`(상주 claimer)는 `#320`(`b28d889`)으로, `work/integrate.py` 는
통합자 삭제(2026-09-04)로 **둘 다 없다** — 이 문단은 2026-10-06 그 사실에 맞춰 다시 썼다(`#265`).

[주의] **배달 위치는 안 바뀌었다** — 저장소가 `client/runtime/` 이어도 클라에는 여전히
`.ax/lib/axmaster/clientside/` 로 놓인다. `.33` 의 `.mcp.json` args 와 `.2`·`.43` 상주가 그 값을
가리키기 때문이다. 그 두 값을 가른 것이 `#262` 이고 `test_payload_split` 이 동결해 둔다.

## 지금은 반씩 나뉘어 있다 — 의도된 상태다 (2026-10-06)

`client/` 를 「클라에 설치되는 것 전부」로 만드는 결정(사용자 2026-08-22)은 **절반만** 실행됐다.

    client/runtime/ · client/init/          옮겼다 (#263) — 클라에서 도는 코드
    master/client/{payload, skills,          아직 여기 있다 — 배달 **내용물**
                   workshop, workshop_by_project}

나머지 이동(`#264`)은 **아이디어 버킷으로 미뤘다** (사용자 2026-10-06): 동작상 얻는 것이 없고
배달 해시·테스트·경로를 흔들며, 그 사이 `workshop_by_project`·kind 별 게이팅으로 대상이 커졌다.
그래서 `master/client/` 의 내용물은 **빠뜨린 것이 아니다** — 옮기려면 `#264` 를 다시 연다.

[중요] **공용 모듈은 이동 대상이 아니다** — `master/layer3_verify.py`·`source_text.py`·`utf8.py`·
`work/*` 는 클라로도 배달되지만 **마스터도 쓴다**. 「클라로 가니 `client/` 로」라고 읽고 옮기면
마스터 쪽 임포트가 끊긴다. → `docs/12-multi-project.md` §12.5-e

[중요] **어느 파일이 어느 역할에 가는가의 정본은 `master/client/bundle.py` 의 `PAYLOAD_BY_ROLE`
하나다** (스킬 목록은 `master/client/spec.py`). 디렉토리를 열어 보는 것으로는 알 수 없고,
`client/` 로 옮겨도 그 사실은 안 바뀐다.

**배달하는 쪽**은 마스터에서 돈다(venv·레지스트리·SSH 키가 거기 있다) — 아래 표가 그것과,
배달되는 클라 코드(`client/`)다.

| | |
|---|---|
| `master/client/bundle.py` | 머신 프로브 · config 생성 · CLAUDE.md 병합 · SSH 배달 + **해시 대조** |
| `master/client/skills/ax-work/`·`ax-infer/` | 워커가 받는 **작업 절차 스킬** (정본) — `ax-work` 는 서브 브랜치 커밋, `ax-infer` 는 추론만 |
| `master/client/payload/CLAUDE.md` | 체크아웃용 프로젝트 가이드 정본 (`/init` 산출, **머신 중립**) |
| `master/client/__main__.py` | `probe\|plan\|deliver\|check <프로젝트>` · `update`(등록 프로젝트 전체 배달→대조) |
| **`master/client/workshop/`** | [완료] **작업장 자산의 정본** (2026-08-20 · #226) — `agents/`·`skills/`·`rules/`·`hooks/` · `.claude/CLAUDE.md`(kind 별 변형 `CLAUDE.code.md`·`CLAUDE.index_only.md`). **요청자에게만** 배달된다(`bundle.WORKSHOP_ROLES`). [주의] 같은 디렉토리의 `README.md`·`mcp.json` 은 **배달물이 아니다**(`test_client_bundle.py` 가 지킨다). 개수는 `find master/client/workshop -type f` 로 센다 |
| `master/client/workshop_by_project/<프로젝트>/` | 프로젝트별 작업장 자산 변형 (`#292`) — 지금은 `ModularStage` 하나 |
| `master/client/skills/ax-request`·`ax-ontology`·`ax-advance`·`ax-review`·`ax-fix` | 요청자가 받는 절차 스킬 (정본). 역할·kind 별 목록의 정본은 `master/client/spec.py`(`kind: code` 는 `ax-fix` 제외, `index_only` 는 `ax-ontology` 만) |
| `client/runtime/` | 클라 기계에서 도는 코드 — `client_mcp.py`·`ontology_cache.py`·`fix_flow.py`·`session1_conductor.py`. 배달 위치는 `.ax/lib/axmaster/clientside/` |
| `client/init/` | `bootstrap.py` · `residency.py`(상주 등록 명령 조립과 `desired_state()`) |

[중요] **왜 저장소가 정본인가** (사용자 지적 2026-08-20): *"다른 프로젝트 세팅할때 그럼 너 뭘 보고
설정하려고?"* — 그전까지 작업장 자산은 게임 저장소(`.gitignore` 가 `.claude/` 를 뺀다)·이 저장소·
원전 어디에도 없었고, 실사용본은 `.33` 디스크뿐이었다. 원전도 배포 형태(`INSTALL.md`+`build.bat`)를
갖고 있었으니 이것은 새 설계가 아니라 **덜 된 이식**이다. → `master/client/workshop/README.md`

## 워커에 배달되는 것

    <체크아웃>/.ax/config.json            경로·능력·백엔드의 **유일한 출처** (마스터 생성)
    <체크아웃>/.ax/work/<task_id>/        작업 부산물 — `.git/info/exclude` 로 무시
    <체크아웃>/CLAUDE.md                  정본 본문 + [중요] **머신별 AX 관리 블록**
    <체크아웃>/.agents/skills/<스킬>/SKILL.md   프로젝트 로컬 Codex 정본 (`#699`) — `ax-work`·`ax-infer`
    <체크아웃>/.codex/config.toml          프로젝트 Codex MCP 블록 (`#699`)
    <홈>/{.claude,.codex}/skills/<스킬>/  같은 스킬 한 벌을 도구별 자리에 (`spec.SKILL_HOMES`)

[중요] Windows의 `backends.python`은 초기화 프로브가 찾은 **절대경로**다. 프로젝트의
`.mcp.json` `ax-client.command`와 `ax-fix`가 이 값을 사용하며 bare `py`/`python` PATH에 기대지 않는다.

[중요] 상주 등록 여부는 `client/init/residency.py::desired_state()` 한 곳이 정한다. 역할·daemon
배달 여부·실측 능력·현재 마운트를 함께 보고 plan/deliver/check가 같은 결정을 소비하며,
deliver는 켜면 안 되는 과거 등록도 제거한 뒤 부재를 되읽는다.

## 요청자(`.33`)에 배달되는 것 — 워커보다 많다

    <체크아웃>/.ax/{config.json,token,lib/axmaster/**}   설정 · 역할 토큰 · 클라 MCP·검수 모듈
    <체크아웃>/.mcp.json                  [중요] **`ax-client` 항목만** 건드린다 (사람 도구와 공존)
    <체크아웃>/.claude/{agents,skills,rules,hooks}/       작업장 자산 — 파일째 관리 (개수는 프로젝트·kind 별로 다르다, `check` 출력이 센다)
    <체크아웃>/.claude/CLAUDE.md          [주의] **`AgentWatch:Start/End` 블록만** 교체.
                                          마커가 없으면 **안 쓴다** (사람 문서를 날리지 않는다)
    <체크아웃>/.agents/skills/ · <홈>/{.claude,.codex}/skills/   요청 절차 — ax-{request,ontology,advance,review,fix}

[중요] **역할 게이팅** — 작업장 자산은 워커에게 보내지 않는다(실측 2026-08-20: `.2`·`.43` 에
`.claude/agents`·`skills` **0건**). 사람이 대화로 쓰는 절차이고, 워커는 마스터의 SSH 파견과 `ax-work` 로 돈다(상주 claimer 는
`#320` 으로 철거됐고, 남은 상주는 build 한정 `work/worker_daemon.py` — `#404`).

[주의] **병합은 개행을 섞는다** — `_remote_read` 는 `read_text()` 로 읽어 CRLF 를 LF 로 번역하고
정본 파일은 CRLF 다. 해시 대조는 *보낸 것과 도착한 것*만 재므로 이걸 못 잡는다. 그래서 쓰기 직전
`with_newlines()` 로 통일한다 (실측 2026-08-20: 첫 배달이 CRLF 362 + LF 172 혼합을 만들었다).

[중요] **경로를 문서에 박지 않는다.** 2026-08-09 실측: `.2` 의 `.mcp.json` 이 `.33` 의 경로를
가리키고 있었다(한 워커 설정이 다른 워커로 복사됨). 그래서 머신별 값은 **마스터가 레지스트리를
근거로 생성**한다.

[중요] **배달했다고 믿지 않는다.** 쓴 뒤 되읽어 sha256 을 대조한다 — 실제로 두 번 잡았다
(PowerShell 이 BOM·CRLF 를 넣음 / 18KB 에서 stdin 이 안 닫힘). 지금은 `scp` 로 보낸다.

## 역할 (`role`) — `driven` 과 다른 축

    driven   닿을 수 있나        ssh | interactive
    role     시켜도 되나         worker | requester

[중요] 역할은 **프로젝트별**이다. 게임 프로젝트에서 `.33` 은 SSH 가 열려 있어도 **`requester`** 라
`drivable_hosts` 에서 빠진다 — 사람이 편집 중인 트리에 일감을 파견하지 않는다. AXCluster 에서는
`.33` 이 `C:\trunk\AXCluster` 의 **worker** 이고 요청자는 마스터다(사용자 2026-10-03).
