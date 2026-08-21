# `client/` — 클라이언트에서 도는 것 · 클라에 설치되는 것

[중요] **2026-08-22 부터 여기에 실물이 있다** (#263) — 그전까지 이 파일은 *"표지판만 있는 자리 ·
코드도 자산도 여기 없다"* 였고, 그 표지판이 `client` 를 **세 뜻**으로 만들었다(빈 표지판 ·
`master/client/` 배달기 · `master/clientside/` 클라 런타임). 기준은 **어디서 도는가**이고,
`master/` 는 이 인프라 서버(`.57`)에서 도는 코드다. → `docs/12-multi-project.md` §12.5-e

    client/runtime/     클라 기계에서 도는 코드 — client_mcp.py · ontology_cache.py
    master/client/      배달기 (SSH 를 쏘는 쪽이니 마스터가 맞다)

[주의] **claimer 사슬은 `master/work/` 에 남았다** (사용자 결정 ⓒ, 2026-08-22):
`claimer.py` → `build_local` → `layer3_verify` 인데 그 `layer3_verify` 를 **마스터도** 쓴다
(`work/integrate.py:423,486` 의 `__import__("master.layer3_verify")` — 정적 grep 에 안 걸린다).
옮기면 상대 임포트가 끊기거나 배달 때문에 저장소 코드를 고쳐야 한다.

[주의] **배달 위치는 안 바뀌었다** — 저장소가 `client/runtime/` 이어도 클라에는 여전히
`.ax/lib/axmaster/clientside/` 로 놓인다. `.33` 의 `.mcp.json` args 와 `.2`·`.43` 상주가 그 값을
가리키기 때문이다. 그 두 값을 가른 것이 `#262` 이고 `test_payload_split` 이 동결해 둔다.

[주의] **아래 표는 이동 전 기준이 섞여 있다 — 전면 개편은 `#265`.**

**배달하는 쪽**은 마스터에서 돈다(venv·레지스트리·SSH 키가 거기 있다) — 아래 표가 그것이다.
[주의] 표에 `client/runtime/` 이 빠져 있다: 이 표는 이동 전에 쓰였다(#265 가 다시 쓴다).

| | |
|---|---|
| `master/client/bundle.py` | 머신 프로브 · config 생성 · CLAUDE.md 병합 · SSH 배달 + **해시 대조** |
| `master/client/skills/ax-work/` | 워커가 받는 **작업 절차 스킬** (정본) |
| `master/client/payload/CLAUDE.md` | 체크아웃용 프로젝트 가이드 정본 (`/init` 산출, **머신 중립**) |
| `master/client/__main__.py` | `python -m master.client probe\|plan\|deliver\|check` |
| **`master/client/workshop/`** | [완료] **작업장 자산의 정본** (2026-08-20 · #226) — 에이전트 12종+`SKILL_INDEX` · 작업장 스킬 12종 · `rules/` 5 · `hooks/` · `.claude/CLAUDE.md` · `mcp.json`. 33파일 400KB. **요청자에게만** 배달된다 |
| `master/client/skills/ax-request`·`ax-ontology`·`ax-review` | 요청자가 받는 절차 스킬 (정본) |

[중요] **왜 저장소가 정본인가** (사용자 지적 2026-08-20): *"다른 프로젝트 세팅할때 그럼 너 뭘 보고
설정하려고?"* — 그전까지 작업장 자산은 게임 저장소(`.gitignore` 가 `.claude/` 를 뺀다)·이 저장소·
원전 어디에도 없었고, 실사용본은 `.33` 디스크뿐이었다. 원전도 배포 형태(`INSTALL.md`+`build.bat`)를
갖고 있었으니 이것은 새 설계가 아니라 **덜 된 이식**이다. → `master/client/workshop/README.md`

## 워커에 배달되는 것

    <체크아웃>/.ax/config.json            경로·능력·백엔드의 **유일한 출처** (마스터 생성)
    <체크아웃>/.ax/work/<task_id>/        작업 부산물 — `.git/info/exclude` 로 무시
    <체크아웃>/CLAUDE.md                  정본 본문 + [중요] **머신별 AX 관리 블록**
    <홈>/.claude/skills/ax-work/SKILL.md  작업 절차

## 요청자(`.33`)에 배달되는 것 — 워커보다 많다

    <체크아웃>/.ax/{config.json,token,lib/axmaster/**}   설정 · 역할 토큰 · 클라 MCP·검수 모듈
    <체크아웃>/.mcp.json                  [중요] **`ax-client` 항목만** 건드린다 (사람 도구와 공존)
    <체크아웃>/.claude/{agents,skills,rules,hooks}/       작업장 자산 31개 — 파일째 관리
    <체크아웃>/.claude/CLAUDE.md          [주의] **`AgentWatch:Start/End` 블록만** 교체.
                                          마커가 없으면 **안 쓴다** (사람 문서를 날리지 않는다)
    <홈>/.claude/skills/ax-{request,ontology,review}/     요청 절차

[중요] **역할 게이팅** — 작업장 자산은 워커에게 보내지 않는다(실측 2026-08-20: `.2`·`.43` 에
`.claude/agents`·`skills` **0건**). 사람이 대화로 쓰는 절차이고, 워커는 claimer·`ax-work` 로 돈다.

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

[중요] `.33` 은 SSH 가 열려 있어도 **`requester`** 라 `drivable_hosts` 에서 빠진다 — 사람이
편집 중인 트리에 일감을 파견하지 않는다.
