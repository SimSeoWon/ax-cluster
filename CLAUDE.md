# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Planning-stage repository for **AX** (AI Transformation) — raising AI usage across an entire Unreal Engine 5 game production pipeline, not just code assistance: ontology-based digital twin, Unreal MCP (UE 5.8.1+), and code-writing agents unified into one pipeline, run from a small Linux cluster (1 master + BC-250 worker nodes).

**Implementation has started in `master/` (2026-08-08).** `worker/` and `client/` are still README-only stubs.

| What exists | Where |
|---|---|
| Layer-2 verdict contract (fail-closed) | `master/verdict.py`, `master/layer2_verify.py` |
| Tests — 35, all passing | `master/test_verdict.py` (19) + `master/test_capability_routing.py` (16). No pytest needed |
| `task_queue` (ported, 2,717 lines) | `master/task_queue/` — **live** as `ax-task-queue.service` on `:8101` |
| Capability routing (`requires`/`capabilities`) | `master/task_queue/logic_claim.py`, tests in `master/test_capability_routing.py` |
| venv + deps | `.venv/`, `master/requirements.txt` |

```bash
python3 master/test_verdict.py                    # 19 tests, no pytest needed
.venv/bin/python master/test_capability_routing.py  # 16 tests — needs the venv (pydantic)
systemctl status ax-task-queue                    # the running service
journalctl -u ax-task-queue -f                    # its logs
AX_TASK_QUEUE_ROOT=/home/sim/ax-state \
  .venv/bin/python -m master.task_queue --serve /home/sim/ax-state 8101 0.0.0.0
```

There is still no linter or CI config — don't invent tooling commands. Check `PLAN.md` for what's decided versus open.

**This repo exists on two machines**: the master (`sim@192.168.0.57:~/ax-cluster`) and BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), both tracking `git@github.com:SimSeoWon/ax-cluster.git` (**private — keep it that way**, it contains LAN addresses and firewall rules). Check whether the two are in sync before working.

## Architecture (from PLAN.md)

🔴 **`worker` means three different things.** This repo's `worker/` is the BC-250 inference node. AgentTest's `worker/` is the operator harness that runs on the Windows PCs — it **stays there** (it owns files), and this repo calls that layer `client/`. Always disambiguate by directory. See `PLAN.md` §4.1.

> ⚠️ An earlier version of this file said AgentTest's `worker/` "ports to `master/`". **That was wrong** and `PLAN.md` §2.1 corrected it on 2026-08-07: what BC-250 took over is *inference compute*, not file work. The harness never leaves Windows.

**Premise (settled 2026-08-07):** AgentTest was **team** infrastructure — every teammate's Windows PC ran its own local LLM. This cluster is **one person pooling their own machines at home**: BC-250 inherits that *inference compute*, and much of AgentTest's complexity is *team* complexity that should be trimmed, not ported (`PLAN.md` §2.0, §5.2-D).

🔴 **The master is infrastructure, not a workshop.** It assembles the right code chunk from RAG/ontology and hands it over; the Windows PC applies it, builds, tests, and registers the code — or asks again. Files never leave Windows. Don't put file I/O or tool-calling on the master (`PLAN.md` §2.1, §2.3).

**There are three orchestrators** (corrected 2026-08-08 — this file previously said two): Claude Code on **each of the two Windows UE5 PCs**, plus the master (which orchestrates with Claude, Antigravity `agy`, and BC-250).

🔴 **The two Windows PCs work on the *same* UE5 project.** Two file-owning workshops hit the same repo, the same `task/<id>` branches, and the same queue — so **claim/lease/fencing is a correctness requirement, not team bloat**. When judging what to trim from AgentTest, the question is not *"does this exist because of a team?"* but ***"do multiple actors touch this concurrently?"*** Verified live: a second worker cannot claim a held task, and a stale-epoch submit is rejected (`PLAN.md` §9.5.3).

- `master/` — infrastructure: RAG index, ontology/graph, task_queue, the BC-250 inference broker, layer-2 verification calls (agy → Claude), and the `gajae-code` driver. It orchestrates *model calls and routing*, never file work.
- `worker/` — code/config for the BC-250 **inference nodes**. Pure text in/out, never touches files — not workers (`PLAN.md` §2.3). **BC-250 #1 runs Ollama + Vulkan. #2 is a Bazzite gaming machine, not an inference node** — converting it means giving up that machine, so never assume a second node exists (`PLAN.md` §3).
- `client/` — the **two** Windows UE5 PCs, the **workshops**: user-facing Claude Code, the only layer that owns files, applies code, runs UE5 build + `RunTests` (layer 3), and registers passing code. AgentTest's `worker/` harness stays here, as does `gajae-code` (`gjc`) and Unreal MCP — both are loopback-only, so the master cannot drive them remotely (`PLAN.md` §9.1).
- Master↔worker calls are meant to be **stateless**: master sends a context string per request, worker infers and responds, no state persists between calls (already validated against BC-250 #1's Ollama API by not reusing its `context` field).
- Neither the master nor the inference nodes read/write project files — only text (context/code fragments/diffs) crosses the wire. All file I/O happens on Windows.
- Deterministic gates (tests/linters/type-checkers) take priority over LLM judgment for verification — this is `gajae-code`'s `Ultragoal` stage's job once wired in.

## Related, external to this repo

- [AgentTest](https://github.com/SimSeoWon/AgentTest) — the predecessor Windows-based orchestration project this cluster is meant to take over the RAG/ontology workload from.
- [gajae-code](https://github.com/Yeachan-Heo/gajae-code) — the coding-agent harness (`gjc` CLI, TypeScript/Bun) this project plans to drive from the master.
- BC-250 #1 has its own hardware/OS setup history in `sim@192.168.0.43:~/bc250-backup-staging/reports/` (master-side copies in `sim@192.168.0.57:~/claude-workspace/reports/`) — read there before touching CU unlock, ACPI, SMU OC, or other board-level config; none of that belongs in this repo.
- AgentTest is cloned on the master at `/home/sim/AgentTest` as **reference only — do not modify or push to it.** Port code *out* of it; never edit it in place.

## Settled — don't relitigate (PLAN.md §4–§6)

Python for the master orchestrator (it's a port, not a rewrite); master-as-broker for inference requests (orchestration and brokering are different layers — many orchestrators, one broker); `qwen2.5-coder:14b` for code generation and `35B-A3B IQ2_M` for context cooking; streaming chunk gaps as the node heartbeat; **Gitea event-driven instead of polling** on the master (§5.4); **BC-250 stays inference-only** and the file-owning harness stays on Windows (§2.1, §2.3).

Settled 2026-08-08:
- **systemd + venv**, not Docker Compose, for the master's services — the workload is bound to host git, SSH keys, the `agy`/`claude` CLIs and their home-dir auth, and the Gitea hook (§5.4.4). `process_lifecycle.py` is **discarded**, not ported; `Restart=always` replaces it (verified by `kill -9`).
- **`gjc` runs on Windows, the master is only its model backend.** The SDK WebSocket is loopback-only and `--mode rpc/bridge` was removed, so "master as remote controller" is impossible (§9.1). The master serves the three Ollama endpoints `gjc` calls (`/api/chat`, `/api/tags`, `/api/show`). `bun`/`node` are therefore a **Windows** prerequisite, not a master one.
- **Layer-2 verification is fail-closed** (§9.4.4). AgentTest's `syntax_check` was deliberately fail-open ("checked=False → caller treats as pass"); the port inverts that. A verdict must be the last non-empty line, exactly `VERDICT: APPROVE` or `VERDICT: REQUEST_CHANGES`; anything else — missing, malformed, timed out, no backend — **blocks**.
- **`qwen2.5-coder:14b` cannot emit structured `tool_calls`** (3/3 at `temperature:0`; the JSON leaks into `content`) even though `/api/show` advertises `capabilities:['tools']`, and `gjc` has no text fallback. Only `35B-A3B` passes all four tool-calling gates — but that model hallucinates APIs when generating code. Don't design an agentic executor around the local models yet (§9.4).

## git operations — two different rule sets (PLAN.md §8)

**Human sessions (this one):** commit/push on request is fine. **Never run** `push --force`, `reset --hard`, branch/tag deletion, `rebase`, or history rewriting — not even when told; describe the command instead. Don't read a first-person statement ("I'll commit and come back") as an instruction to you; that exact misreading caused an incident in AgentTest, whose CLAUDE.md responded by banning Claude commits outright.

**Pipeline workers (master's worker processes):** the human rule does NOT apply — they autonomously commit/push `task/<id>` and attempt branches and advance durable via CAS. They must never push to `main` directly or force-push. The branch boundary is what separates the two rule sets.

**Never trust a delegated backend's "done".** Measured 2026-08-07: `agy` returned `status:"SUCCESS"`/`"DONE"` while writing no file (print mode needs `--mode accept-edits`). Always verify the artifact — file exists, diff applied, build passes — not just the status. This is why `worker/validator.py` and the layer-1 gate exist.

## Open decisions (see PLAN.md §3)

Resolved during 2026-08-08 (see "Settled" above): the execution model, BC-250 #2's state, how `gjc` is driven, and the Unreal MCP integration point. Still open:

- **`task_queue` has no auth layer at all** (0 hits for auth/token/Depends). Port 8101 is open **LAN-only** via `ufw allow from 192.168.0.0/24`; the firewall is the *only* defence. Never widen that rule to `Anywhere`, and add auth before trusting the LAN less (§9.5.6).
- **Event queue design** — prerequisite for the Gitea webhook switch: durable + single-consumer + coalescing (§5.4.5). Do not merge it into `task_queue`; the two have different consumer models.
- **RAG/ontology port** (`mcp/context_search/`) and the **BC-250 inference broker** — neither has been started.
