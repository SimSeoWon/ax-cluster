# CLAUDE.md — Windows worker `.2`

> [중요] **This file is a COPY, not a symlink.** Canonical:
> `sim@192.168.0.57:~/ax-cluster/machines/win-worker-2.md`. Edit there, then refresh here:
>
> ```bash
> scp ~/ax-cluster/machines/win-worker-2.md janus@192.168.0.2:C:/Users/janus/CLAUDE.md
> ```
>
> The other two machines symlink into a local `ax-cluster` clone; this box has no clone, so it
> gets a copy. **Copies drift** — change the canonical file first. Structure: [`README.md`](README.md).


## 원전 로컬 함대 — 정리됨, 다만 **설치본이 둘이다** (2026-08-20 · #226)

| 무엇 | 상태 |
|---|---|
| `E:\trunk\ModularStage\.claude\mcp\` (exe 12종 + onnx 87MB) | [완료] **삭제** — 미실행·미등록 확인 후. 회수 576.7MB |
| `.claude\daemons\worker.exe` | [완료] **삭제** (25.7MB) · 옛 로그 1건은 남겼다 |
| 원전 폴링 데몬 `watch.exe`+`config.json` | [완료] 삭제 (2026-08-20 · 리포트 27 §2). [중요] 그 config 가 **옛 토폴로지**(`.33:8100/8101`)를 가리켰다 |
| [중요] `E:\trunk\ModularStage\AgentWiki\` (90파일 191.4MB) | **그대로 둔다** (사용자 결정 2026-08-20: *"그럼 그냥 냅둬"*). [중요] **클러스터 찌꺼기가 아니라 사람의 도구다** — 원전의 **비개발자용 위키 클라이언트**이고, `%APPDATA%\Claude\claude_desktop_config.json` 이 `agentwiki` → 그 안의 `context_search.exe` 로 등록해 뒀다. **Claude Desktop**(WindowsApps `claude.exe`, 로그온 시 셸이 띄움)이 물고 돈다 — 실측: 그 경로에서 프로세스 4개 실행 중. [주의] 다만 **이미 옛 토폴로지로 깨져 있다**: 그 `config.json` 이 `http://192.168.0.33:8100`(응답 없음)을 가리키고 데이터는 **2026-07-12 에 멈춰 있다**(context 63 MD·벡터 캐시 전부). 즉 살아 있는 것은 프로세스이고 답은 낡았다. [중요] **목적을 갖고 둔 것이다** — 사용자 2026-08-20: *"`.33` 에서 비개발자용 처리 테스트 하려고 둔거라고"*. 그래서 서버 주소가 `.33:8100` 이다(그 시험은 `.33` 이 서버였던 시절). **원전 함대라는 이름표가 붙었다고 다 잔재가 아니다** — 지우지 말 것. 대응물(8103 뷰·`ax-client` 조회)로 옮길지는 열린 결정 |
| 아직 안 센 것 | `_archive_agenttest_20260809` · `tools` · `vector_db` · `vector_db_client` · `context.bak-20260718_165030` — 세지 않았으므로 판단하지 않는다 |

[중요] **삭제는 경로가 아니라 프로세스로 물어야 한다.** 파일 목록만 보고 지웠으면 살아 있는
세션의 MCP 를 끊었을 것이다 — 그것도 남의 기계에서. 정리 스크립트는 *"이 경로 아래 도는
프로세스"* 를 먼저 세고 있으면 중단한다.

[완료] 정리 후 배선 무손상 확인: `.ax/`(config·lib·token·claimer.lock) · `AxClaimer` 실행 중 ·
마스터 `client check` OK.

## Identity

| | |
|---|---|
| **OS** | **Microsoft Windows 10 Pro 22H2** (version 2009, build 10.0.19045) |
| **Host / IP** | `DESKTOP-HV0I6DL` / **192.168.0.2** |
| **Account** | **`janus`** — a local **Administrator**. *Not* `sim`; `ssh sim@…` fails |
| **SSH** | `ssh janus@192.168.0.2` — passwordless. Master's key is in `C:\ProgramData\ssh\administrators_authorized_keys` (admin path, not `~/.ssh/`) |
| **GPU** | **NVIDIA GeForce RTX 3060 (12GB)** |
| **UE5 project** | **`E:\trunk\ModularStage`** — see § Unreal projects |

This box is **two things at once**, which is the thing to keep straight:

1. **A workshop** — it owns UE5 project files, runs the engine, builds, `RunTests`, registers code.
2. **Inference endpoint #2** — Ollama on `:11434`, `qwen2.5-coder:14b` pinned, serving the master's
   broker (`:8102`). Runs 14b ~23% faster than the BC-250 board.

It is also **the only Windows machine the master can reach non-interactively** (SSH). The user's
main work PC (`.33`) is RDP-only. Full cluster inventory: `machines/sim-desktop.md`.

## Can / cannot — the session-0 boundary

```
SSH login     → SessionId 0   (services session — NO desktop access)
console janus → SessionId 9   (the interactive desktop)
```

Windows session-0 isolation is an OS boundary, not a setting. Everything below follows from it.

### [완료] The master CAN do these over SSH

| | Notes |
|---|---|
| `UnrealEditor-Cmd` — commandlets, **build, `RunTests`** | Headless, session 0 is fine. This opens layer-3 verification to master control. [주의] Session placement confirmed; **an actual remote build has not been run yet** |
| `git` operations in the checkout | On PATH |
| `gjc`, `node`, any CLI | Once `gjc` is installed |
| Read/write files, inspect state | |
| Reach the master's services | 8101 / 8102 / 8103 all verified reachable |

### [실패] The master CANNOT do these

| | Why |
|---|---|
| **Start the UE5 GUI editor** | Session 0 has no desktop. Launching it there is useless |
| **Start / stop Unreal MCP** | Its lifetime *is* the editor's lifetime → session 9 only. **Don't design a remote procedure — there isn't one.** Whoever is at the desktop owns it |
| Anything needing a visible window | Same boundary |

### Process ownership rule

**For SSH-launched processes, the SSH connection is the owner.** When it closes, children die.
That is the design, not a bug — no supervisor, no orphans. If something must outlive the
connection, that's the signal to make it a **Windows Service / Scheduled Task**, not to hand-roll
a supervisor. (Same call the master made discarding `process_lifecycle.py` for systemd.)

Detail: `~/ax-cluster/docs/5_5-project-isolation.md` §5.5.4-⑥.

### AxClaimer — the resident queue claimer (2026-08-18, #204)

Exactly the case above: a Scheduled Task (`AxClaimer`) wakes the claimer **every 5 minutes**
(pythonw, no console). A live instance holds the exclusive lock `.ax\claimer.lock`, so extra
wake-ups yield silently; after a crash the OS releases the lock and the next tick restarts it.
It runs **only while janus is logged on** (no stored password — same premise as the
origin's `worker.exe`). It claims **build and code(infer)** jobs (`--types=build,code` —
실전 pull 전환, user decision 2026-08-18). For code tasks it runs Claude locally, records facts
to `.ax\work\<task>\result.json`, and never submits — the master collects and judges.

    logs     E:\trunk\ModularStage\.ax\logs\claimer_<date>.log  — daily, boot-rotated (_N),
             7-day retention (#220). Per-task trace: .ax\logs\claimer_debug\<task_id>\
             (heartbeat.log · llm_stdout.log · llm_stderr.log · build.log — kept after the
             task ends, for post-mortem). Crash: claimer_crash.log
    stop     schtasks /end /tn AxClaimer  &  schtasks /change /tn AxClaimer /disable
    restart  /end → **wait a few seconds** → /run. Measured 2026-08-18: right after
             /end the OS may not have released `.ax\claimer.lock` yet, so an immediate /run
             bounces off the singleton and nothing runs — until the 5-min watchdog heals it
    code     delivered payload .ax\lib\axmaster\work\claimer.py — [중요] don't hand-edit; SSOT
             is the master repo and the next `deliver` overwrites it

## Unreal projects

Convention on this box — **already established, don't invent a new one:**

```
E:\trunk\  ├─ ModularStage\    ← the AX project. origin = Gitea Sim/ModularStage, branch main
           ├─ Monster\
           ├─ PanoramaTest\
           └─ Project_Alpha\
```

`E:` has ~499GB free. Registered as this project's workshop path in the master's `ax-projects`
registry (`:8103`).

[중요] **Automation reuses this checkout — so it must not destroy work in it.**

- **Block on modified/staged *tracked* files.** Those are what `checkout` / `reset --hard` destroy.
- **Untracked (`??`) files pass.** They survive both. As of 2026-08-08 the tree carries
  `?? AgentWiki/` and `?? AgentWiki.zip` — blocking on those would stop automation on day one.
- [중요] **Never run `git clean` here.** That is the assumption that makes untracked files safe.

```bash
git -C 'E:\trunk\ModularStage' status --porcelain | grep -v '^??' | head -1   # non-empty ⇒ do not start
```

[주의] **`DerivedDataCache` / `Intermediate` / `Binaries` / `Saved` exist and are expensive.** Outside
git, but regenerating them is a multi-tens-of-minutes build. Don't treat "delete and re-clone" as
cheap. If an isolated second checkout ever becomes necessary, share the DDC instead of rebuilding.

[주의] **Don't put a UE5 project under OneDrive.** `C:\Users\janus\OneDrive\문서\Unreal Projects\`
exists here (`LyraStarterGame`, unrelated to us) — new checkouts default there too easily.

## LLMs available on this machine
**어느 작업에 유리한지·환각이 있었는지는 [`llm-fitness.md`](llm-fitness.md) 에 실측으로 기록한다** — 모델 적합도는 머신 속성이 아니라 모델 속성이라 한 곳에 모았다. 여기(이 문서)는 **무엇이 설치돼 있는지**까지다.


### Local — Ollama `:11434` (7 models, measured 2026-08-08)

| Model | Size | Quant |
|---|---|---|
| **`qwen2.5-coder:14b`** | 8.37 GiB | Q4_K_M | ← **pinned**; what the master's broker routes here |
| `gemma4:e4b` | 8.95 GiB | Q4_K_M |
| `gemma3:12b` | 7.59 GiB | Q4_K_M |
| `qwen3:8b` | 4.87 GiB | Q4_K_M |
| `llama3.1:latest` | 4.58 GiB | Q4_K_M |
| `llama3:latest` | 4.34 GiB | Q4_0 |
| `gemma2:2b` | 1.52 GiB | Q4_0 |

[중요] **`MAX_LOADED_MODELS=1`** — one resident model at a time. Swapping costs ~36s for 14b.
Anything premised on several models resident here at once does not hold.
[중요] **Don't repin the endpoint casually** — the master's broker assumes 14b is resident
(`master/broker/config.py`).

### Commercial CLIs

| | Status | Notes |
|---|---|---|
| **Claude Code** | [완료] **2.1.225** | `C:\Users\janus\.local\bin\claude.exe`. `.claude.json` + a credential file present → looks authenticated (not verified by running it) |
| **Gemini CLI** | [완료] installed | `%APPDATA%\npm\gemini.cmd`, `~/.gemini` present |
| **`agy` (Antigravity)** | [실패] **not installed** | Only on the master. If research delegation is wanted here, install it first |
| `gjc` (gajae-code) | ⬜ **not installed** | Prerequisite for PLAN §9. `node` is present, so nothing blocks it |

**Claude Code here is an *orchestrator*, not a model backend.** Ollama cannot serve Claude, and
the Claude Code CLI is not an inference server — don't try to put it behind the master's broker.
This machine owns files; that is what makes a Claude session here valuable.

## The SSH PATH trap

The SSH session gets a minimal PATH. **`where` / `Get-Command` report installed tools as missing.**
This produced two wrong "not installed" calls while writing this file — verify by absolute path
before concluding anything is absent.

| On SSH PATH | Installed but NOT on SSH PATH |
|---|---|
| `git` (`C:\Program Files\Git\cmd\git.exe`) | `node` v24.11.1 (`C:\Program Files\nodejs\node.exe`)<br>`claude` (`C:\Users\janus\.local\bin\claude.exe`)<br>npm globals (`%APPDATA%\npm`) |

**Quoting over SSH is its own hazard.** Nested `powershell -Command "..."` through SSH mangles
`$env:` expansion and escaped quotes — several probes returned confidently wrong answers that way.
Write the script and pipe it in:

```bash
ssh janus@192.168.0.2 'powershell -NoProfile -Command "Invoke-Expression ([Console]::In.ReadToEnd())"' < probe.ps1
```

## Master's services (all reachable from here, verified 2026-08-08)

| Service | URL |
|---|---|
| task queue | `http://192.168.0.57:8101` |
| inference broker (Ollama-compatible) | `http://192.168.0.57:8102` |
| project registry (MCP) | `http://192.168.0.57:8103/mcp` |
| Gitea | `http://192.168.0.57:3000` |

[중요] **All of them require `Authorization: Bearer <token>`** (since 2026-08-08). The token lives on
the master at `~/.config/ax-cluster/token`; ask for it rather than inventing one. Only `/livez` is
open. They are *also* LAN-only by firewall — don't expose them further.

## Hard rules

- [중요] **This machine owns files; the master does not.** The master assembles context and hands it
  over — applying code, building, testing, and committing happen *here*.
- **Two workshops share this UE5 project** (`.2` and `.33`, same repo, same `task/<id>`
  branches). Claim/lease/fencing in the master's task queue is a **correctness requirement**, not
  overhead — don't work around it.
- [중요] **Never `push --force`, `reset --hard`, delete branches, or rewrite history** in a human
  session — describe the command instead.
