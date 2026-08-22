# sim-desktop — environment and privilege notes

Index: [`../sim-desktop.md`](../sim-desktop.md) (= the master's `~/CLAUDE.md`)

## PATH

`~/.local/bin` is on PATH via an explicit block in `~/.bashrc` (added 2026-08-02). It is also in
`~/.profile`, but `.profile` only runs for login shells, so a plain new terminal wouldn't have
found the `claude` binary without the `.bashrc` entry.

## [중요] `sudo` and `pkexec` are not the same thing here — don't conflate them

`sudo` on **this** machine requires a password **except for the narrowly-registered commands
listed below**. **And `pkexec <cmd>` works** — an authentication dialog appears on the user's
screen, and root is granted once they accept.

- Run it with `run_in_background: true` and **tell the user to look at their screen**
- **Never declare a privileged task impossible without trying `pkexec` first**
- Handle it on the master directly; don't hand the command off to the user to run

The BC-250 is genuinely stuck: headless since 2026-08-05, so no authentication agent can exist
there. Its procedure is in [`bc250-access.md`](bc250-access.md).

### Registered NOPASSWD commands — [중요] these exist because **automation is the premise**

The user's framing (2026-08-22): *"자동화를 전재로 프로젝트 구성중"*. A step that waits for a
human to click an auth dialog is not automated. So privileged steps that onboarding must run
unattended get a **narrow** sudoers rule — one wrapper path each, never a bare command.

| Rule file | Allowed | Why it must be unattended |
|---|---|---|
| `/etc/sudoers.d/ax-cluster-services` (pre-existing) | `systemctl restart` of `ax-task-queue`·`ax-broker`·`ax-projects`·`ax-indexer.service`·`ax-status.timer` | service ops during work |
| `/etc/sudoers.d/ax-install-hook` | `/usr/local/bin/ax-install-hook` (root:root 0755 wrapper) | new-project onboarding installs the Gitea `post-receive` hook; that step is in `spec.SERVER_STEPS` and must not stop for a click |

[주의] **The wrapper fixes paths and env itself** so the sudoers rule stays one literal path:

    exec env PYTHONPATH=/home/sim/ax-cluster AX_PROJECTS_ROOT=/home/sim/ax-cluster \
             AX_EVENT_SPOOL=/home/sim/ax-spool  <venv>/python -m master.events.install_hook "$@"

[중요] **Be honest about what this grants.** `install_hook.py` lives in `sim`'s repo, so anyone
who can edit that file can run code as root through this rule — it is effectively a `sim`→root
path. That cost was accepted deliberately (automation premise); the mitigation is that the rule
names **one wrapper path**, not a bare interpreter or a wildcard.

[주의] **`Path.home()` under root is a trap.** Running the installer as root made
`DEFAULT_SPOOL` resolve to `/root/ax-spool` — it created a spool in the wrong place, left the
real one's permissions untouched, and **reported success** (measured 2026-08-22). The hook runs as
`gitea` and the consumer as `sim`, so wrong permissions mean **the consumer cannot delete what the
hook wrote**. `events/install_hook.spool_dir()` now refuses to guess: `AX_EVENT_SPOOL` →
`SUDO_USER`/`PKEXEC_UID` → error.

## Python

`python3-venv` and `python3-pip` were **not** installed by default; they were added 2026-08-08 via
`pkexec apt-get install`. The AX cluster's venv is `~/ax-cluster/.venv`.

## GPU

NVIDIA GT 1030 (2GB). **No NVIDIA driver is installed** — `nvidia-smi` fails. Anything
CUDA-dependent needs the driver installed first.
The GTX 1070 expansion study is in [`../../docs/7-master-gpu.md`](../../docs/7-master-gpu.md).
