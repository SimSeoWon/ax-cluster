# CLAUDE.md — Windows worker `.2`

> [중요] **This file is a COPY, not a symlink.** Canonical:
> `sim@192.168.0.57:~/ax-cluster/machines/win-worker-2.md`. Edit there, then refresh here:
>
> ```bash
> scp ~/ax-cluster/machines/win-worker-2.md janus@192.168.0.2:C:/Users/janus/CLAUDE.md
> ```
>
> The other two machines symlink into a local `ax-cluster` clone; this box's only ax-cluster tree
> is the pipeline-owned worker checkout `E:\trunk\AXCluster` (not a place to symlink from), so it
> gets a copy. **Copies drift** — change the canonical file first. Structure: [`README.md`](README.md).


## Codex CLI (2026-09-05 설치)

`codex-cli 0.159.3`(2026-10-03 실측) · npm 전역 `C:\Users\janus\AppData\Roaming\npm\codex.ps1` ·
`codex login status` → **Logged in using ChatGPT**(설치 시점에 이미 인증돼 있었다).

🔴 [중요] **이 기계는 PowerShell 경로로 불러야 한다** — `cmd /c` 로 부르면
*"지정된 경로를 찾을 수 없습니다"* 가 **CP949 로 깨져** 온다(`.33` 은 cmd 로도 된다).

    powershell -NoProfile -Command "Set-Location $env:TEMP; Get-Content p.txt |
      codex exec --skip-git-repo-check --json -o last.txt"

[주의] **구독 한도는 네 대 공용이다**(2026-09-04: 429 하나로 4조각 중 3 사망).
본문 작성 **레인**(`lane` 모드)은 마스터에서 돈다. 그러나 워커 지휘자 모드가 `claude`/`codex`
이면 **이 기계에서** 그 에이전트가 체크아웃을 읽고 고친다 — codex 는 SSH 세션 0 에서 직접
돌리지 않고 `AxConductor_<프로젝트>`(`/IT /RL LIMITED`) 런처로 로그인 세션에서 돈다.
현재 모드는 `ax-mode` 로 조회한다.

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

[완료] 정리 후 배선 무손상 확인(2026-08-20 당시): `.ax/`(config·lib·token·claimer.lock) ·
당시 `AxClaimer` 실행 중 · 마스터 `client check` OK. (`AxClaimer` 는 이후 철거·개명됐다 — 아래
§ Resident tasks.)

## Identity

| | |
|---|---|
| **OS** | **Microsoft Windows 10 Pro 22H2** (version 2009, build 10.0.19045) |
| **Host / IP** | `DESKTOP-HV0I6DL` / **192.168.0.2** |
| **Account** | **`janus`** — a local **Administrator**. *Not* `sim`; `ssh sim@…` fails |
| **SSH** | `ssh janus@192.168.0.2` — passwordless. Master's key is in `C:\ProgramData\ssh\administrators_authorized_keys` (admin path, not `~/.ssh/`) |
| **GPU** | **NVIDIA GeForce RTX 3060 (12GB)** |
| **Checkouts** | `E:\trunk\` — ModularStage · NS · MotionForge (UE5) · KimodoMotion_WebUI · AXCluster (code) — see § Unreal projects |

This box is **two things at once**, which is the thing to keep straight:

1. **A workshop** — it owns UE5 project files, runs the engine, builds, `RunTests`, registers code.
2. **Inference endpoint #2** — Ollama on `:11434`, `gemma4:e4b` pinned (user 2026-10-03),
   serving the master broker (`:8102`). The 14b performance figures below are historical.

Both Windows PCs are reachable over SSH; Codex worker execution uses the interactive `/IT` conductor.
See [`../docs/windows-codex-remote.md`](../docs/windows-codex-remote.md) for required flags and verification. Full cluster inventory: `machines/sim-desktop.md`.

## Can / cannot — the session-0 boundary

```
SSH login     → SessionId 0   (services session — NO desktop access)
console janus → the interactive desktop session (measured 9 once; the ID is NOT fixed)
```

"Session 1" in this repo is a **launcher name** for the logged-in interactive session, not a
SessionId.

Windows session-0 isolation is an OS boundary, not a setting. Everything below follows from it.

### [완료] The master CAN do these over SSH

| | Notes |
|---|---|
| `UnrealEditor-Cmd` — commandlets, **build, `RunTests`** | Headless, session 0 is fine. This opens layer-3 verification to master control. [완료] Remote builds run here, driven by the master over SSH (`run_build_on_workshop` → `Build.bat`). (The 2026-09-12 resident build daemon, report 63, was withdrawn 2026-10-31 — `#860`.) |
| `git` operations in the checkout | On PATH |
| `gjc`, `node`, any CLI | Once `gjc` is installed |
| Read/write files, inspect state | |
| Reach the master's services | 8101 / 8102 / 8103 all verified reachable |

### [실패] The master CANNOT do these

| | Why |
|---|---|
| **Start the UE5 GUI editor** | Session 0 has no desktop. Launching it there is useless |
| **Start / stop Unreal MCP** | Its lifetime *is* the editor's lifetime → the interactive session only. **Don't design a remote procedure — there isn't one.** Whoever is at the desktop owns it |
| Anything needing a visible window | Same boundary |

### Process ownership rule

**For SSH-launched processes, the SSH connection is the owner.** When it closes, children die.
That is the design, not a bug — no supervisor, no orphans. If something must outlive the
connection, that's the signal to make it a **Windows Service / Scheduled Task**, not to hand-roll
a supervisor. (Same call the master made discarding `process_lifecycle.py` for systemd.)

Detail: `~/ax-cluster/docs/5_5-project-isolation.md` §5.5.4-⑥.

### No resident daemon — only the on-demand `AxConductor` launcher (user 2026-10-31, #860)

`AxClaimer` was removed by #320 (2026-08-27). `AxWorker` (#404/#405, a build daemon) was withdrawn
2026-10-31: the master drives builds over SSH (`run_build_on_workshop`). What remains:

    AxConductor_<프로젝트>     codex conductor launcher (/IT /RL LIMITED) — started by the master
                               with `schtasks /run` only when dispatching; not resident

[주의] Until #860 removes the registration code, delivering a mounted unreal project can
re-register `AxWorker`. If you see it, it is a leftover, not the design.

🔴 [중요] **After a reboot `janus` must log in** (console or RDP 3389). `/IT` tasks need an
interactive logon and this box has no auto-logon (`AutoAdminLogon` absent) — without it the
conductor launcher has no session and `.2` **silently drops out of dispatch**. Readiness checks
the task registration only, not that a session exists.

## Unreal projects

Convention on this box — **already established, don't invent a new one:**

```
E:\trunk\  ├─ ModularStage\    ← AX project. origin = Gitea Sim/ModularStage, branch main
           ├─ NS\              ← AX project (worker)
           ├─ MotionForge\     ← AX project (worker, UE5 plugin)
           ├─ KimodoMotion_WebUI\  ← AX project (worker, kind code)
           ├─ AXCluster\       ← AX project (worker, kind code) — pipeline-owned checkout
           ├─ Monster\
           ├─ PanoramaTest\
           └─ Project_Alpha\
```

`E:` had ~499GB free (2026-08-08). Each AX checkout is registered as that project's workshop
path in the master's `ax-projects` registry (`:8103`).

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
| **`qwen2.5-coder:14b`** | 8.37 GiB | Q4_K_M | ← historical pin (2026-08-08); current pin is gemma4:e4b |
| `gemma4:e4b` | 8.95 GiB | Q4_K_M |
| `gemma3:12b` | 7.59 GiB | Q4_K_M |
| `qwen3:8b` | 4.87 GiB | Q4_K_M |
| `llama3.1:latest` | 4.58 GiB | Q4_K_M |
| `llama3:latest` | 4.34 GiB | Q4_0 |
| `gemma2:2b` | 1.52 GiB | Q4_0 |

[중요] **`MAX_LOADED_MODELS=1`** — one resident model at a time. Swapping costs ~36s for 14b.
Anything premised on several models resident here at once does not hold.
[중요] **Don't repin the endpoint casually** — the master's broker pins gemma4:e4b (2026-10-03)
(`master/broker/config.py`).

### Commercial CLIs

| | Status | Notes |
|---|---|---|
| **Claude Code** | [완료] **2.1.225** (version as of probe) | `C:\Users\janus\.local\bin\claude.exe`. Auth is checked by the master with `claude auth status` and cached 24h at `%USERPROFILE%\.cache\ax-dispatch\claude-auth.json` (`#721`; passed 2026-10-06). If it fails, log in again as `janus` (`claude auth login`) and force a recheck — procedure: `docs/14-onboarding-runbook.md` §14.2-4 「Claude 준비 검사와 재로그인」 |
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

[중요] **8101 · 8102 · the MCP at 8103 require `Authorization: Bearer <token>`** (since
2026-08-08). The token lives on the master at `~/.config/ax-cluster/token`; ask for it rather
than inventing one. [주의] **8103's web UI and `/api/v1` are public (no login)** — never send a
sensitive body there; its `/control/*` write surface needs the requester token. All are *also*
LAN-only by firewall — don't expose them further.

## Hard rules

- [중요] **This machine owns files; the master does not.** The master assembles context and hands it
  over — applying code, building, testing, and committing happen *here*.
- **Several workers share each project** (`.2`·`.43`, plus `.33` for AXCluster; `.33` is the
  requester for the game projects), on the same repo and the same `task/<work>/…` branches.
  Claim/lease/fencing in the master's task queue is a **correctness requirement**, not overhead —
  don't work around it.
- [중요] **Never `push --force`, `reset --hard`, delete branches, or rewrite history** in a human
  session — describe the command instead.
