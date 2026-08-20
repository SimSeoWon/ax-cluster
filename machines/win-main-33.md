# CLAUDE.md — Windows main work PC `.33`

Guidance for Claude Code sessions **on this machine**, and for the master when it drives it.
Cluster-wide rules live in [`sim-desktop.md`](sim-desktop.md); repo rules in
[`../CLAUDE.md`](../CLAUDE.md).

> [중요] **This is the human's machine.** Everything below follows from that one fact. `.2` is a
> workshop the master may drive freely; `.33` is where the user actually works, so the master
> is a **guest** here — it checks before acting and never takes resources the user needs.
> Probed 2026-08-08.

## Identity

| | |
|---|---|
| **OS** | **Microsoft Windows 11 Pro**, build 10.0.26200.8875 |
| **Host / IP** | `DESKTOP-FU2GNGL` / **192.168.0.33** |
| **Account** | **`user`** — *not* `janus` (that's `.2`), *not* `sim`. Both fail with `Permission denied` |
| **SSH** | `ssh user@192.168.0.33` — passwordless since 2026-08-08. Master's key is in `C:\ProgramData\ssh\administrators_authorized_keys` (admin path, same as `.2`) |
| **GPU** | **NVIDIA GeForce RTX 3080 (10 GB)**, driver 610.47 |
| **UE5** | **5.8.1** at `C:\Program Files\Epic Games\UE_5.8` — same version as `.2` |
| **UE5 project** | **`C:\Users\USER\Documents\ModularStage`** — see § Unreal projects |
| **git** | 2.53.0.windows.1 |

## 요청자 콘솔 — [중요] **여기가 언리얼 작업의 창구다** (사용자 2026-08-20)

사용자는 이 기계의 `ModularStage` 에서 실제 작업을 하다가 **여기서 `claude` 를 켜고 요청한다.**
마스터(`.57`)는 인프라 서버다 — 큐·브로커·색인·통합을 돌리는 자리이고, 마스터 세션이 등재하는 것은
**이 창구의 대행일 뿐**이다. 실측 2026-08-20: 배선은 **이미 다 배달돼 있었고**, 빠져 있던 것은
마스터 쪽 `CLAUDE.md` 의 이 한 문단이었다 (그래서 세션마다 마스터에서 시작하는 것으로 착각했다).

| 무엇 | 어디 (실측) |
|---|---|
| 스킬 3종 | `C:\Users\USER\.claude\skills\` — `ax-request`(등재) · `ax-ontology` · `ax-review`(`/review-work`). **홈에 두는 것이 계약** — 절차는 프로젝트가 아니라 머신의 능력 |
| 도구 (2026-08-20 확장) | `ax-client` **14종** — 조회 9: `search_context` · `list_domains` · `get_domain` · `get_domain_layer`(층 항목 + tier·summary·layer_counts·계층/연관) · `get_object_spec` · `get_action_spec` · `find_invariants_by_class` · `list_works` · `get_work` / 쓰기 대행 5: `add_object_alias` · `mark_not_a_class` · `redmine_note` · `log_writer_signal` · `log_history`. [중요] **읽기는 8103, 쓰기는 큐 8101** — 8103 의 `/api/v1/*` 는 무인증 공개라(실측: 토큰 없이 200) 쓰기를 둘 자리가 아니다 |
| 은퇴한 것 | **원전 폴링 데몬 `watch.exe` + `config.json` 삭제**(2026-08-20 · 백업 `~/claude-workspace/backups/legacy-watcher-20260820/`). 로컬 `context-search` 는 정본이 아니다 — 온톨로지가 마스터로 옮겨진 뒤 objects/actions 를 **0/0 으로 답한다**(실측: 로컬 240항목 전부 서버에 있고 서버가 54항목 앞섬). [완료] **`.mcp.json` 원전 exe 등록 5종 제거**(2026-08-20 · #226 4단계 · 16→11종): `context-search`·`task-queue`·`master-orchestrator`·`local-llm-runner`·`redmine-tracker`. [중요] **실측하니 이미 무장 해제였다** — 5종 전부 루트 `config.json` 에서 키·URL 을 읽는데 그 파일은 와처 정리 때 삭제됐다. 백업 `~/claude-workspace/backups/33-mcp-json-20260820/` |
| 갱신된 사람 문서 | `.claude/CLAUDE.md`(14곳) · `.claude/skills/manage-domain`(5곳+머리말) · `manage-task`(1곳) — 도구 이름을 `mcp__ax-client__*` 로. 백업 `~/claude-workspace/backups/33-claude-docs-20260820/`. [중요] **고칠 파일은 루트 `CLAUDE.md` 가 아니라 `.claude/CLAUDE.md`** 였다 |
| 클라 MCP | 체크아웃 루트 `.mcp.json` 의 `ax-client` = `py .ax/lib/axmaster/clientside/client_mcp.py` → 마스터 `8103/mcp` 위임. [완료] 사람이 쓰는 `gemini-cli`·`unreal-mission-editor`·`uelog-analyzer` **항목과 공존**(배달은 `ax-client` 항목만 건드린다) |
| [중요] 남은 참조 | **등록을 지워도 참조는 남는다** — `.claude/agents/` **9종 전부**의 `tools:` 허용목록이 `mcp__context-search__combined_search` 를(둘은 `mcp__redmine-tracker__*` 도) 아직 가리킨다. [주의] **서버가 없으면 오류가 아니라 그 도구 없이 그냥 돈다** — 리포트 27 §9-3 의 「조용히 0」과 같은 계열. 매핑: `combined_search`→`search_context` · `get_domain_manifest`→`get_domain_layer`. **위임 구멍 2개**: Redmine 읽기(`get_issue`·`list_issues`·`update_issue`·`list_statuses`·`list_trackers` — `ax-client` 에는 `redmine_note` 만) · `get_task_template`. 결정 대기(#226) |
| 배달물 | `.ax/config.json`(경로·능력 `ue5,windows`·UE5 5.8 실측) · `.ax/token`(**requester 역할** 토큰) · `.ax/lib` · `.ax/tasks` · `.ax/work` |
| 프로젝트 `CLAUDE.md` | `AX:Begin`~`AX:End` 관리 블록에 역할 계약이 이미 적혀 있다 — *"요청하는 쪽"*, *"여기서 소스를 고치지 않는다"* |
| 배달 시점 | 커밋 `8d55de9`. 저장소 HEAD 가 앞서가도 **번들 경로(`master/client`·`clientside`·`work/review.py`·`coordinator.py`·`layer3_verify.py`)에 변경이 없으면 재배달 불필요** — 2026-08-20 확인(HEAD `44274dc`, 해당 경로 무변경) |

[주의] **낡은 번들은 조용히 돈다** (`master/client/__main__.py` 의 경고) — `.33` 이 옛 review 로직으로
검수하면 그 판정 자체가 낡는다. 위 경로에 변경이 생기면 마스터에서
`python -m master.client deliver` 를 다시 돌린다.

검색은 이 머신에서 **`ax-client` MCP 의 `search_context`** 한 입구로만 간다 (시소러스 경유).
다른 경로로 돌면 한국어 질의가 조용히 나빠진다 — 절차 본문은 `ax-request` 스킬에 있다.

## Not an inference endpoint — the VRAM does not allow it

Measured with **only the Windows desktop running** (UE5 editor not open):

| | |
|---|---|
| VRAM total / in use / free | 10240 MiB / 2401 MiB / **7651 MiB** |
| `gemma4:e4b` (its only model) | **8.95 GiB** — does not fit the free VRAM |
| `qwen2.5-coder:14b` (the coder model) | 9.0 GB — does not fit either |
| `/api/ps` | empty — nothing resident |

Opening the editor takes more still. Pinning a model here would spill Ollama onto CPU **and**
compete with the user for VRAM on the machine they are using. The §4.4 model-switch cost is
~100 s round trip, so "load while they're away, unload when they return" thrashes.

**→ Checks and remote installs only** (user's decision, 2026-08-08). `master/provision.py`
lists this host with `resident=False` and **flags it if a model is ever loaded**. Pulls go over
plain HTTP (`POST /api/pull`) — no SSH, no file access, so *only text crosses the wire* holds.

Inference stays on **`.43`** (BC-250, 35B pinned) and **`.2`** (RTX 3060, 14b pinned).

## Can / cannot — same session-0 boundary as `.2`

SSH lands in **session 0**, which has no desktop. The user's interactive login is a different
session. This is a Windows boundary, not a permissions one — no flag works around it.

### [완료] The master CAN do these over SSH

| | Notes |
|---|---|
| `git` in the checkout (incl. `status --porcelain`) | On PATH. **The dirty check now covers this host** — see below |
| `UnrealEditor-Cmd` — commandlets, build, `RunTests` | Headless; session 0 is fine. [주의] **Not yet run here** — proven on `.2`, not on `.33` |
| Read/write files, inspect state | |
| `claude`, `agy`, `node` | All present, see § LLMs |
| Ollama check / `pull` | Over HTTP, no SSH needed |

### [실패] The master CANNOT do these

| | Why |
|---|---|
| **Start the UE5 GUI editor** | Session 0 has no desktop |
| **Start / stop Unreal MCP** | Its lifetime *is* the editor's → the interactive session owns it. **Don't design a remote procedure — there isn't one** |
| Anything needing a visible window | Same boundary |

### Extra rule that applies here and not to `.2`

**The user may be working right now.** Long GPU jobs, editor launches, branch switches, and
resets are not just technically risky — they interrupt a person. Prefer read-only probes;
for anything that writes, go through the dirty check first and let it say no.

## Unreal projects

`.uproject` files under `C:\Users\USER\Documents` (targeted search, 2026-08-08):

| Project | Path | |
|---|---|---|
| **ModularStage** | `C:\Users\USER\Documents\ModularStage` | **the mounted project** — see below |
| Project_Alpha | `C:\Users\USER\Documents\Project_Alpha` | The predecessor; its docs survive as `_archive/project_alpha_md/` in the twin's context |
| ServerTest | `C:\Users\USER\Documents\ServerTest` | |
| ListViewTest | `C:\Users\USER\Documents\Unreal Projects\ListViewTest` | |

### Both workshops track the same repository — the competition is real

```
.33  C:\Users\USER\Documents\ModularStage  →  origin gitea@192.168.0.57:Sim/ModularStage.git
.2   E:\trunk\ModularStage                 →  same repo (origin http://192.168.0.57:3000/Sim/ModularStage.git)
```

`.33`'s origin switched HTTP → SSH on 2026-08-17 (user, via SourceTree — OpenSSH client,
key `ax-requester-33`). **Gitea's SSH user is `gitea@`, not `git@`** — `git@192.168.0.57` fails
with `Permission denied (publickey)` even with a registered key. That trap cost a debugging
round; don't re-enter it.

`.33` was on `main` at `bc4b38f` when probed. **This is the measured basis for §4.2's premise**
that two workshops contend for the same `task/<id>` branches and the same task queue —
so claim / lease / fencing are a **correctness requirement**, not an optimization.

### The workshop registry entry was stale — fixed 2026-08-08

It read `driven: interactive` with the note *"SSH 없음(RDP 뿐)"* and carried no path. Now:

```yaml
192.168.0.33:
  driven: ssh
  user: user
  path: C:\Users\USER\Documents\ModularStage
```

**Consequence: the dirty check reaches this machine.** First run found one uncommitted change —
`Content/Blueprints/BP_MissionPrefab_C_0/BP_MissionPrefab_C_0.uasset`, i.e. the user's own
in-progress work — and correctly refused to dispatch. That is the behaviour we want here.

## LLMs available on this machine
**어느 작업에 유리한지·환각이 있었는지는 [`llm-fitness.md`](llm-fitness.md) 에 실측으로 기록한다** — 모델 적합도는 머신 속성이 아니라 모델 속성이라 한 곳에 모았다. 여기(이 문서)는 **무엇이 설치돼 있는지**까지다.


### Local — Ollama `:11434`

| Model | Size | Quant | |
|---|---|---|---|
| `gemma4:e4b` | 8.95 GiB | Q4_K_M | |
| `qwen2.5-coder:14b` | 9.0 GB | Q4_K_M | ← installed remotely by the master, 2026-08-08 |

**Both are on disk; neither fits the free VRAM, and neither is pinned.** That combination is
deliberate, not an oversight — `master/provision.py` declares this host `want=[CODER]` *and*
`resident=False`: **keep it on disk, never load it.** `/api/tags` answers "do we have it",
`/api/ps` answers "is it loaded" — different questions, and the check flags the second one
turning true. `/api/ps` was empty right after the install, as intended.

### Commercial CLIs

| | Status | Notes |
|---|---|---|
| **Claude Code** | [완료] **2.1.226** | `C:\Users\USER\.local\bin\claude.exe` |
| **`agy` (Antigravity)** | [완료] **1.0.16** | `C:\Users\USER\AppData\Local\agy\bin\agy.EXE`. [주의] **Older than the master's 1.1.10** — the Windows-era pitfalls (PTY, ANSI, argv order) that 1.1.10 fixed on Linux are **not verified fixed here**. Don't assume the master's experience transfers |
| `node` | [완료] | `C:\Program Files\nodejs\node.exe` |
| `bun` | [실패] not installed | Same gap as `.2`; prerequisite for PLAN §9 (gajae-code) |

[중요] **Never let `agy` run autonomously in a working directory here.** It uses
`--dangerously-skip-permissions`; AgentTest recorded it editing files without consent. Text in,
text out only — and on *this* machine those would be the user's files.

## The Python PATH trap — same shape as `.2`, different cause

```
where python
  C:\Users\USER\AppData\Local\Microsoft\WindowsApps\python.exe        ← Store stub, wins
  C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe    ← the real one

py -0p
  -V:3.12 *   C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe
```

`python --version` prints **`Python`** with no version — the stub swallows it. That output looks
like a truncated answer rather than a failure, which is exactly how it misleads.

**Use `py`, or the full path.** Never bare `python` in anything the master runs here.

## When something here changes

This file is a **copy**, like `win-worker-2.md` — `ax-cluster` is not cloned on this machine, so
there is nothing for a symlink to point at. Refresh it deliberately after measuring; see
[`README.md`](README.md) for the reasoning and the copy procedure.
