# sim-desktop — environment and privilege notes

Index: [`../sim-desktop.md`](../sim-desktop.md) (= the master's `~/CLAUDE.md`)

## PATH

`~/.local/bin` is on PATH via an explicit block in `~/.bashrc` (added 2026-08-02). It is also in
`~/.profile`, but `.profile` only runs for login shells, so a plain new terminal wouldn't have
found the `claude` binary without the `.bashrc` entry.

## 🔴 `sudo` and `pkexec` are not the same thing here — don't conflate them

`sudo` on **this** machine requires a password (no NOPASSWD). **But `pkexec <cmd>` works** — an
authentication dialog appears on the user's screen, and root is granted once they accept.

- Run it with `run_in_background: true` and **tell the user to look at their screen**
- **Never declare a privileged task impossible without trying `pkexec` first**
- Handle it on the master directly; don't hand the command off to the user to run

The BC-250 is genuinely stuck: headless since 2026-08-05, so no authentication agent can exist
there. Its procedure is in [`bc250-access.md`](bc250-access.md).

## Python

`python3-venv` and `python3-pip` were **not** installed by default; they were added 2026-08-08 via
`pkexec apt-get install`. The AX cluster's venv is `~/ax-cluster/.venv`.

## GPU

NVIDIA GT 1030 (2GB). **No NVIDIA driver is installed** — `nvidia-smi` fails. Anything
CUDA-dependent needs the driver installed first.
The GTX 1070 expansion study is in [`../../docs/7-master-gpu.md`](../../docs/7-master-gpu.md).
