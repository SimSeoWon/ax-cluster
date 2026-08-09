> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Repo working guidance: [`../CLAUDE.md`](../CLAUDE.md).

# Settled — don't relitigate

Everything here is a **decision closed with evidence**. Don't reopen it unless a new measurement
contradicts it. If one does, fix this file *and* the corresponding § document — patching only one
side is how they drift apart.

## Premise (settled 2026-08-07)

AgentTest was **team** infrastructure — every teammate's Windows PC ran its own local LLM. This
cluster is **one person pooling their own machines at home**: BC-250 inherits that *inference
compute*, and much of AgentTest's complexity is *team* complexity that should be **trimmed, not
ported** (§2.0, §5.2-D).

🔴 **But "is this here because of a team?" is the wrong question.** The right one is
***"do multiple actors touch this concurrently?"*** The **two Windows UE5 PCs work on the same
project** — same repo, same `task/<id>` branches, same queue. So **claim/lease/fencing is a
correctness requirement, not team bloat.** Verified live: a second worker cannot claim a held task,
and a stale-epoch submit is rejected (§9.5.3).

## Closed in §4–§6

- **Python for the master orchestrator** — it's a port, not a rewrite
- **Master-as-broker for inference requests** — orchestration and brokering are different layers:
  many orchestrators, one broker
- **Model assignment** — `qwen2.5-coder:14b` for code generation, `35B-A3B IQ2_M` for context cooking
- **Streaming chunk gaps as the heartbeat** — don't build separate communication infrastructure
- **Gitea event-driven, not polling**, on the master (§5.4)
- **BC-250 stays inference-only** — the file-owning harness stays on Windows (§2.1, §2.3)

## Closed on 2026-08-08

- **systemd + venv, not Docker Compose** (for the master's own services). The workload is bound to
  host git, SSH keys, the `agy`/`claude` CLIs and their home-dir auth, and the Gitea hook (§5.4.4).
  `process_lifecycle.py` is **discarded, not ported** — `Restart=always` replaces it (verified by
  `kill -9`).
- **`gjc` runs on Windows; the master is only its model backend.** The SDK WebSocket is
  loopback-only and `--mode rpc/bridge` was removed, so "master as remote controller" is impossible
  (§9.1). The master serves the three Ollama endpoints `gjc` calls (`/api/chat`, `/api/tags`,
  `/api/show`). `bun`/`node` are therefore a **Windows** prerequisite, not a master one.
- **Layer-2 verification is fail-closed** (§9.4.4). AgentTest's `syntax_check` was deliberately
  fail-open (`checked=False` → caller treats as pass); the port inverts that. A verdict must be the
  **last non-empty line**, exactly `VERDICT: APPROVE` or `VERDICT: REQUEST_CHANGES` — missing,
  malformed, timed out, or no backend all **block**.
- **`qwen2.5-coder:14b` cannot emit structured `tool_calls`** (3/3 failures at `temperature:0`; the
  JSON leaks into `content`), even though `/api/show` advertises `capabilities:['tools']`, and
  `gjc` has no text fallback. Only `35B-A3B` passes all four tool-calling gates — but that model
  hallucinates APIs when generating code. **Don't design an agentic executor around the local
  models yet** (§9.4).

## Ontology — 🔴 domain auto-promotion is discarded, in both producers (2026-08-09)

AgentTest has **two** producers of domain MDs (`context/_domains/<D>.md`), and they write
**different section schemas**. Measured on the received snapshot:

| Producer | Sections written | frontmatter | Our 7 domains |
|---|---|---|---|
| **Auto-promotion** — `watcher/domain.py:577` | `## 시스템 개요` **only** | `status: draft`, no `created_by` | **6** |
| **`ontology-register` skill** — `mcp/context_search/domain_seed.py:299` | 개요 + 핵심 책임 · 도메인 경계 · 핵심 invariants · 협력 도메인 · 사용자 의도 메모 | `status: active`, `created_by: ontology-register` | 1 (`MissionEditor`) |

**Auto-promotion is discarded — do not port it.** Two independent reasons: the user reports it
**misbehaved badly** in practice (2026-08-09), and the original itself disabled it permanently on
2026-06-01. Nothing needs deleting on our side — **it was never ported** (0 lines in `master/`);
this entry exists so a later session doesn't "restore" it as a missing feature.

**Consequence — domain MDs are created only by interactive registration** (소 1.3.1 / 1.3.2).
The 6 auto-promoted domains were hand-enriched into a *third* de-facto schema
(`시스템 개요` + `핵심 구현 패턴` + `확장 포인트`) which `agent_defs.py:132` tells agents to read.
🔴 **The MD parser must accept all of these.** Porting the original's fixed 6-section regex makes
**6 of 7 domains parse to empty with no error** — measured: `GlobalEventSystem` yields 322 chars
under the original patterns vs **1,225** when unknown sections are kept (`master/ontology/domain_md.py`).
Same failure family as the `is_empty` filter that silently dropped 149 documents.

🔴 **6 of 7 domains have no `## 도메인 경계`.** That section is what keeps synthesis from pulling
in other domains' classes. Do **not** compensate with prompt wording alone — the deterministic
guards do it: `allowed_classes` filtering plus the fact gate (`ontology/verify_facts.py`, call
relations checked against the 6,380-row `methods` table).

## Terminology — 🔴 `worker` means three different things

| Whose `worker` | What it actually is |
|---|---|
| This repo's `worker/` | the BC-250 **inference node** |
| AgentTest's `worker/` | the **operator harness** on the Windows PCs — it owns files, so it **stays there** |
| What this repo calls that layer | `client/` |

Always disambiguate by directory (§4.1).

> ⚠️ An earlier version of this text said AgentTest's `worker/` "ports to `master/`".
> **That was wrong**, and §2.1 corrected it on 2026-08-07: what BC-250 took over is *inference
> compute*, not file work. The harness never leaves Windows.
