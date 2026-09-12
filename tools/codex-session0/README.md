# Codex Session 0 runtime

Windows OpenSSH starts in Session 0. Codex versions that use the Windows
sandbox runner can fail there because the runner child does not have access to
the Window Station/Desktop ACLs. The pinned upstream patch in `runtime.toml`
grants the child logon SID only for the lifetime of that child.

This directory is the source of truth for the runtime delivered to workers:

1. `build-windows.ps1` checks out the pinned Codex commit and builds both
   `codex.exe` and `codex-code-mode-host.exe` with the pinned Rust toolchain.
2. The build emits a package directory and `manifest.json` containing source
   commit, toolchain, file sizes, and SHA-256 hashes.
3. The onboarding delivery step installs only a package whose manifest passes
   verification. It never installs Rust or Visual Studio on a worker.
4. `verify-windows.ps1` runs the model-free Session 0 smoke test after install.

The generated package is an artifact, not a Git-tracked binary. CI or the
master artifact store retains it by the manifest's source commit and hashes.
The worker wrapper is deliberately separate from the user's existing `codex`
installation and can be removed without changing that installation.
