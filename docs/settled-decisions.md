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
- ⚠️ ~~**BC-250 stays inference-only**~~ — **superseded 2026-08-09** (see *Cluster shape* below).
  It now also holds the project clone and runs a worker agent. What still holds is the narrower
  rule: **the Ollama model never touches files** — inference is text-in/text-out. The *machine*
  hosting that model may also host an agent that reads its own checkout; the two roles coexist.
  🔴 Patching only one of these two statements is how they drifted — both are now consistent.

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

## Ontology refresh — 🔴 for new/changed domains, **not** over the received snapshot (2026-08-09)

Ran it for real once (레드마인 #24). **Mechanically healthy**: chunking, two-node split, fact gate
**100%** (4/4·5/5·5/5·6/6), 63s for `MissionEditor`. **But the content got shallower**:

    actions     14 → 9   · kept **1**  · lost 13 · new 8
    invariants   8 → 11  · kept **0**  · lost 8  · new 11

What was lost encoded *this system's design decisions* — *"`UTaskListEditorWidget` uses the
`AMissionPrefab` CDO as the source of truth and must resync via `ReloadFromCDO()`"*. What replaced
it was *framework mechanics any UE developer reads off the header* — *"abstract class, derived must
override `ApplyData()`"*. 🔴 **Both are true, so the fact gate passes** — it blocks *false*, not
*shallow*. Restored from backup.

🔴 **Corrected the same day (user caught it): that was the *local lane*, not "our synthesis".**
`synth.CLI_MODELS` has `claude`/`agy` lanes that the CLI could not select. With `--model claude`:
**27 actions / 24 invariants, gate 100%, snapshot-grade depth** (*"`SetSCSNodeVariableName`
returns bool, so callers must not assume success"*) — but **still lost 3 of 5 snapshot concepts**.
More items does not mean nothing is lost.

🔴 **The mitigation is a *separate* mark, not the verification lock.** `protected` means *"do not
replace this with a regeneration"* (provenance-based, bulk-applicable); `verified_by_user` means
*"a human checked this item"* (one at a time). Stamping 247 machine-produced snapshot items as
human-verified would destroy the signal that lets us find what a human actually reviewed.
`package.locked_items` honours **both**, so the effect is identical.

**Measured end state** (MissionEditor): protect 35 → `refresh --model claude` →
actions 14→37, invariants 8→32, **snapshot kept 14/14 and 8/8, all 5 concepts alive, +47 net**.
⚠️ **Do not protect what the synthesiser produced** — that must stay improvable.

🔴 **Protection never exempts verification.** `verify` still checks protected items (62 measured),
`sync` still fixes their paths and *reports* classes gone from the graph without deleting. The
open gap is design-rule prose with no call notation — which is why protection records
`protected_at` (the twin commit), the only handle 중 2.4.1 drift audit will have.

⚠️ `ModularStage/` is gitignored, so **back up before any refresh** (`~/ax-backups/`).

## Cluster shape — 🔴 one operator, N workers (user-confirmed 2026-08-09)

This is **not** AgentTest's team topology, and that difference removes machinery rather than
adding it.

| | Decided |
|---|---|
| **Roles** | `driven` (can we reach it) and `role` (may we dispatch to it) are **different axes**. `.33` has SSH yet is a `requester` and is excluded from `drivable_hosts` — never dispatch into the human's working tree |
| **Every worker holds the clone** | Source-based judgment is the worker's *primary* capability and **all workers are equal in it**. UE5 only decides who can run the layer-3 verdict |
| **durable `task/<id>`** | A **long-lived working space**, not something to merge fast. The requester creates it (the master cannot push — §2.1); `main` is merged **once, by the human, at the end** |
| **Always push the attempt** | Success *or* failure. Discarding failures destroys the evidence and the basis for feedback — and the model is **accumulative**: a rejected attempt is fixed, not reimplemented |
| **Feedback is code-located** | A `[FEEDBACK]` block goes into the file at the failing spot, exactly like `[PSEUDO]` skeletons. A queue text field cannot say *where*. `layer2_verify.py` already rejects leftover markers |
| **Layer-3 location** | The requester is fastest (UE5 is on `.33`) — but ⚠️ **never switch branches in the human's main tree**; use `git worktree`. `.2` is the unattended path |
| **Dropped by this shape** | per-author split, durable-merge CAS, and "the model holds merge authority" (`verify_worker.py`) — **not a redesign, simply unnecessary** |

🔴 **What is *not* dropped**: attempt-branch isolation, lease, and epoch fencing. Two worker
machines contend for real — the criterion is *"are there actually multiple concurrent actors?"*,
not *"is this a team feature?"*
→ [`8-git-authority.md`](8-git-authority.md) §8.4

## Worker configuration — 🔴 generated, never copied (2026-08-09)

A worker's `.mcp.json` was found pointing at `C:\Users\USER\Documents\ModularStage` — **another
machine's path**, character-for-character identical to `.33`'s registry entry. One worker's config
had been copied to another; every path in it was missing there, and it **failed silently**.

So: **the master generates per-machine config from the registry** (`python -m master.client
deliver`) into `<checkout>/.ax/config.json`, and **capabilities are probed, not declared**.
Delivery **re-reads and compares sha256** — that check caught four separate corruptions in one
session (a silent no-op `move`, PowerShell adding BOM/CRLF, an 18 KB stdin hang, and a duplicated
managed block). Transfers use `scp`; `CLAUDE.md` is merged **marker-delimited** so human text
survives.

## Worker dispatch — 🔴 the master mediates; workers get no queue token (2026-08-09)

Measured before writing any code: **both workers get 401 from `:8101`** and have **zero AX MCP
servers registered**. The `ax-work` skill's premise — *"MCP 는 등록에 헤더가 박혀 있다"* — was
simply **false**. Two ways out: hand the token to the workers, or have the master mediate.
**Mediation won**, on four grounds — reopen this file if any of them stops holding:

1. §5.5.4 already rejected a daemon on the same logic: SSH is open, so **the master pushes work in**.
2. The token never leaves the master. Copying it to two more machines widens exposure for nothing.
3. 🔴 **Lease heartbeats need a long-lived caller.** The lease is 1200s with a 30s reclaim loop; the
   master is already alive waiting on the SSH call. Telling the worker's Claude *"don't forget to
   heartbeat mid-task"* is exactly the kind of thing an LLM forgets — and forgetting frees the lease
   so **another worker claims the same task**.
4. The only credential a worker actually needs is **git**, which Gitea SSH keys already provide.

Consequences that are also settled: the verdict is a **fail-closed marker contract** (last three
lines `ATTEMPT`/`HEAD`/`RESULT`), and leniency opens **only toward `BLOCKED`** — `RESULT: BLOCKED —
reason` is accepted, `RESULT: DONE — …` is not. The base section of a manifest is **re-resolved at
dispatch time**, because the durable `task/<id>` is created by the requester *after* registration,
so a registration-time value is **guaranteed to go stale in the normal flow** (measured).

## Scope — 🔴 everything the master judges is `Source/` (user-confirmed 2026-08-09)

Indexing and graphs were **already** limited to `repo/Source/**` (§5.2-E) — measured: the
dependency and class graphs contain **1,662 files / 1,806 classes, 100% under `Source/`**.
The **dirty check was the one thing still looking at the whole repo**, and that mismatch is what
blocked `.2` from ever being dispatched to:

    M Automation_ModularStage.slnx · M ModularStage.slnx · M ModularStage.uproject
    (the `.uproject` diff is `EngineAssociation` GUID → "5.8")

All three are **rewritten by UE5/VS just from opening the project**. The user's call:
*"리소스나 엔진, 에디터용 메타데이터 등 바뀔 여지가 커"* — a gate watching an area that changes
on every editor launch is **permanently red**, and a permanently red gate is not a gate.

⚠️ **The trade**: uncommitted changes outside `Source/` (e.g. `Content/*.uasset`) no longer block.
Acceptable because ⑴ workers never write outside `Source/` (skill §5) ⑵ `git clean`/`reset --hard`
are forbidden, so the residual risk is branch switching — and git **refuses** a checkout that would
overwrite local modifications ⑶ the machine a human actually works on (`.33`) is a `requester` and
is never dispatched to.

🔴 **Out-of-scope dirt is still counted and reported** (`Cleanliness.out_of_scope`, named in
`reason`). *Not blocking* and *not looking* are different things — if the verdict just said
"깨끗하다", the next session would read it as repo-wide.

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

## Write authority — 🔴 **the master is the broker and the writer; workers build and report** (Flow Y, user-confirmed 2026-08-14)

🔴 **This supersedes the section below.** The origin's `local_llm_distributed_workers_plan_v5.0.md`
left this exact fork **explicitly undecided** (κ, *"추론 요청 주체 (κ.2 핵심 갈림) … 확정 필요"*),
noted that its own 2-layer split *"points to Flow Y"*, and the user chose **Flow Y** on 2026-08-14.

    ① master  (Linux, .57)   reads source from the canonical git · asks the inference nodes ·
                             🔴 **commits the returned diff to `task/<id>` / `attempt/<id>/<w>/<ts>`**
                             · all orchestration state lives here (κ.0)
    ② worker  (Windows)      **pull → UE compile / RunTests → report (pass/fail + log).**
                             🔴 **makes no judgment · stateless · may go dark at any time**
    node      (BC-250)       inference only — text in, text out, no files
    requester (.33)          registers · reviews · writes `[FEEDBACK]`

**What stays from v5 C.1–C.3** (Flow X and Flow Y share these — the fork is only *who pushes*):
2-tier branches (durable `task/<id>` + ephemeral `attempt/…`) · **epoch fencing** on the notify gate
(`submit_epoch < current_epoch` → zombie assignee rejected) · `cleanup_attempts` (ephemeral removed,
durable preserved) · `fake_worker` injection for a no-hardware dry run · accumulate-don't-rebuild on
reject (fast-forward durable to attempt, then add one `[FEEDBACK]` commit).

🔴 **The UE5 build gate is a queued job, not an SSH call.** κ.0: *"통합 빌드게이트는 인프라에
고정하지 않고 **task_queue 잡으로 큐잉 → UE5 있는 윈도우 워커가 claim** 하는 CI 러너 패턴"*, and
κ.8's port table marks `ue_builder.py`/`ue_test_runner.py` *"리눅스로 옮기는 대상 아님, 혼동 주의"*.
Linux forces **only** that relocation — nothing else in the shape.

⚠️ **Two labels to keep straight.** ① The section below is titled *"user-confirmed 2026-08-11"* but
was **not** — it was *"그래 해"* after I pushed it (user, 2026-08-13). ② *"One writer"* was never
ours to invent: `cluster_coordinator.verify_and_merge` already said *"durable 단일 writer 보존"* —
and **that writer was the server**, which is what Flow Y restores. → reports/14 §2 · §11.3.

⚠️ **`.2`-as-integrator may be the same mistake the origin already made and reverted** — a session
there invented a *"검증 전용 노드"* and the work was **reverted in full** because *"워커는
homogeneous"*. Check our special-cased `.2` role against that before hardening it.

## ~~Write authority — one writer: the integrator builds, then commits~~ (🔴 **superseded 2026-08-14**, mislabeled "user-confirmed 2026-08-11")

🔴 **Kept for the record, not for arguing from.** Its reasoning about *who* should not commit is
still useful; its conclusion (workers never write, `.2` is the sole writer) is replaced by Flow Y
above. Do not cite this section as a settled decision.

The pipeline used to have **N writers**: each worker edited its own clone, committed, and pushed an
`attempt/` branch; the master judged from a `RESULT:` marker. That is now replaced.

    requester   `.33`        registers · reviews · writes `[FEEDBACK]`   🔴 the pipeline never commits here
    worker      `.2` `.43`   **infers only** — reads the branch, answers 🔴 does not commit
    integrator  `.2`         **applies → UE5 build verdict → commits**   🔴 the only writer
    master      —            queue · manifest · routing · skeleton generation

**Why the change.** The old shape judged a task by the worker's own report, and **nobody asked
whether it compiles.** The predecessor hit exactly that: with build *after* registration, a broken
skeleton landed in `origin` and every worker built on top of it. Making the builder the committer
turns that from a rule into a structure — broken code cannot reach the remote.

It also removes a class of problems wholesale: worker git credentials, `attempt/` branch debris,
"workers may not delete branches", dirty-tree dispatch blocking, and half of the CAS/fencing —
all of it existed because several machines wrote. It is the same direction §5.2-D already took
(*"durable merge CAS · a model holding merge authority — unnecessary for one operator"*).

🔴 **The parallelism being given up was already suspect**: measured 2026-08-09, two workers were
**12% faster and 90% more expensive** (cache creation is a per-worker fixed cost). And layer 3 was
*already* serial on `.2` — the only machine that can run a UE5 verdict unattended. So the serial
bottleneck is **relocated, not introduced**.

🔴 **Why `.2` and not the requester.** The user's first sketch put applying on the main work PC.
`.2` is chosen instead because `.33` is **the human's machine** — guest rules apply (read-only by
preference, `git worktree` never a branch switch, uncommitted `.uasset` is unrecoverable) and its
availability is low (measured off during this very session). `.2` has UE5 5.8, is dedicated, and
already holds the layer-3 role.

**Known costs, accepted:**
- `.2` becomes a single point of failure for apply+build. Layer 3 already made it one; more work now
  rides on it.
- On `.2` the inference checkout and the apply checkout must not be the same tree → **worktree
  isolation**, the same trick §8.4 prescribes for the requester.
- The N-writer machinery (worker Gitea keys, `attempt/` branches, `work/cleanup.py`) becomes
  dormant. 🔴 **It is kept, not deleted** — this is reversible until measured otherwise.

## Distribution's value — 🔴 **incremental progress, not throughput** (user-reframed 2026-08-11)

> *"분산 작업의 장점은 비용이나 시간이라고 생각했는데, 어찌보면 증분이 아닐까해"*

Measured numbers refuse the throughput story: two workers ran **12% faster and 90% more
expensive** (cache creation is a per-worker fixed cost), the **3.2× saving came from batching**
(fewer calls), not from parallelism, and layer 3 was serial on `.2` all along.

What the machinery in §4.5 actually buys is that **work accumulates in a state that always
compiles**: the frozen interface stops pieces from breaking each other, the skeleton build gate
makes sure the base stands, dependency order decides what stacks on what, and the integrator
commits **only what built**. Under the 2026-08-11 write-authority decision every commit on a
durable branch is build-verified, so the branch is monotonically green.

🔴 **Verification is therefore a premise, not an option.** Piling up unverified output is debt,
not increment. Free local generation works because **wrong things do not accumulate** — not
because it is cheap. The predecessor's own correction (*reject = advance-and-amend, never
discard-and-regenerate*, 2026-06-21) is the same statement from the other side.

⚠️ This does not move the free/paid boundary. Measured (report 12 §7), a locally generated
skeleton froze **6 declarations where Opus froze 30** — that argues the *skeleton* is a contract
worth paying for, not that bodies should be. Bodies stay free-local plus verification.
