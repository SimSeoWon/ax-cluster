# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`MotionForge` is an Unreal Engine 5.8 **editor plugin** for making animation: text prompts through
NVIDIA Kimodo (`kimodo.cpp`, a C++/GGML port) and, later, video through MetaHuman markerless capture.
It also carries the Kimodo WebUI, so generation works without the editor; results are turned into
`AnimSequence` assets and used in other projects (ModularStage). The UE project around it is a test
host (C++ Third Person template) — the deliverable is `Plugins/MotionForge/`.

## Where you are, and what you can do here

[중요] **This body is machine-neutral on purpose.** What *this* machine can do — the checkout path,
whether UE5 is installed, which backends exist — is in the **AX managed block at the end of this
file**, generated per machine by the master. Read that before assuming you can build.

- [중요] **Source is changed only after stating the plan and getting consent.** Targets:
  `Plugins/MotionForge/**`, `Source/**`, `*.uproject`, `Config/*.ini`, `Content/**`. Reading,
  searching and proposing are free — what is gated is **writing**.
  🔴 [중요] **A dispatched piece (`ax-work`) already has that consent** — registering it was the
  approval, and the instruction names the files. Fill the named files' `[DOC]`/`[PSEUDO]` bodies
  without asking (a non-interactive run has nobody to approve; asking ends in `RESULT: BLOCKED`).
  Files outside that list still need consent.
- `/CLAUDE.md` and `/.claude/` are **gitignored** at the repo root; this file is local to each
  checkout. Push to the source repo is disabled on non-authoring checkouts.
- [중요] **Do not start, stop or kill the WebUI, Unreal or other long-running processes** without
  the user's approval. The WebUI runs in a *visible* console (`Kimodo/run-webui.bat`).

## Layout

| Path | What |
|---|---|
| `Plugins/MotionForge/Source/MotionForgeEditor` | Editor module: panel (Tools > MotionForge), WebUI tab (Tools > MotionForge WebUI), commandlet `-run=MotionForgeGenerate` |
| `Plugins/MotionForge/Kimodo/webui` | Kimodo WebUI server (`server.py`, standard library only) + static front end |
| `Plugins/MotionForge/Kimodo/scripts` | Launchers, `build-kimodo.ps1`, `follow-upstream.ps1`, GLB export |
| `Plugins/MotionForge/Kimodo/vendor/kimodo.cpp` | Submodule — the user's fork, branch `motion/main`. Never commit to its `main` |
| `Content/SOMA` | Reference SOMA30 skeleton imported from a kimodo `animation.glb` |

Not in git (local only): `vendor/kimodo.cpp/models`, `vendor/kimodo.cpp/generated` (text encoder,
~14 GB), `output_motion`, `assets/mixamo_*` (Adobe licence — never commit), `webui/config.local.json`.

## Build · test

- UE plugin: build the `MotionForgeEditor` target (command in the AX block). The editor must be closed.
- kimodo.cpp: `Kimodo\scripts\build-kimodo.ps1` — builds **out of tree** in
  `%LOCALAPPDATA%\MotionForge\kimodo-build` (the in-plugin build dir exceeds MAX_PATH, FTK1011), runs the
  ctest baseline (5 tests) + SOMA smoke, then installs exe/dll into `vendor/kimodo.cpp/build`.
- WebUI: `py -m unittest discover -s webui/tests -p "*_test.py"` from `Plugins/MotionForge/Kimodo`;
  preflight `py webui\server.py --check` (does not start the server).
- Plugin conversion check: `UnrealEditor-Cmd <uproject> -run=MotionForgeGenerate -Skeleton=<SOMA>
  -FromDir=<generation> -CompareTo=<imported glb anim>` must report rot/pos error ≈ 0.

## Code conventions

- **UE C++ (plugin)**: Epic coding standard — tabs, `A/U/F/E/I` prefixes, `TObjectPtr` in `UPROPERTY`,
  IWYU (forward-declare in `.h`). **Comments in English.** Log through `LogMotionForge`; every
  external process, wait and import step logs what it did (start, heartbeat every 15s, exit code).
- Verify UE 5.8 APIs against the installed engine source before using them — two identifiers
  remembered from older engines were wrong here (`IWebBrowserModule.h` is `WebBrowserModule.h`).
- Kimodo → Unreal: glTF Y-up metres → UE Z-up cm with the importer's mapping
  (`ConvertVec3` `(x,z,y)`, `ConvertQuat` `(-x,-z,-y,w)`), scale fixed at **100**. Never derive the
  scale from skeleton bone lengths — exporters differ (WebUI's GLB uses Mixamo offsets).
- **Python (WebUI)**: match nearby code; comments and user-facing strings in Korean as already used;
  `server.py` stays standard-library only. Tests are `webui/tests/*_test.py`.
- **kimodo.cpp**: four-space indent, C++23, `snake_case`, warnings clean under `/W4 /permissive-`;
  public API in namespace `kimodo`. Follow upstream by **merge**, never rebase (old pins must stay
  reachable). Keep root and submodule commits separate.
- PowerShell: parameters `PascalCase`, locals `camelCase`. Native commands under
  `$ErrorActionPreference = "Stop"` must be wrapped (stderr progress lines otherwise abort the script).
- Paths: keep checkouts short (`C:\trunk`, `E:\trunk`) — MAX_PATH bites the in-plugin submodule.

## Commit conventions

Short imperative subjects (Korean or English). Machine-generated work uses the AX prefixes
(`[skeleton]`, `[verify-merge]`, `[review fix]`, `Merge work <id>`).
