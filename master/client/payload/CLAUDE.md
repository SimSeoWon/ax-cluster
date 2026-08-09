# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`ModularStage` is an Unreal Engine 5.8 **listen-server** game project. Its reason for existing is the
**mission system**: a stage is assembled from hexagonal prefab modules, each carrying a list of
mission tasks that a runtime executor drives. Almost everything else (UI layers, event bus, editor
widgets, Python/MCP bridge) exists to author or observe that system.

## Where you are, and what you can do here

🔴 **This body is machine-neutral on purpose.** What *this* machine can do — the checkout path,
whether UE5 is installed, which backends exist — is in the **AX managed block at the end of this
file**, generated per machine by the master. Read that before assuming you can build.

- `/CLAUDE.md` and `/.claude/` are **gitignored**, so this file is local to each checkout and never
  gets committed. Don't "fix" that by un-ignoring it.
- Push to the source repo is disabled on non-authoring checkouts. Work on
  `attempt/<task_id>/<workshop>/<ts>` branches; never push `main`.

Build command (only where UE5 is installed — check the AX block):

```bat
"<UE5>\Engine\Build\BatchFiles\Build.bat" ^
  ModularStageEditor Win64 Development "<checkout>\ModularStage.uproject" -WaitMutex -FromMsBuild
```

`gemini_build.bat` at the repo root is the same command but **stale** — it still points at `UE_5.4`
and a hardcoded `C:\Users\USER\Documents\ModularStage` path. Fix the version/path before reusing it.

There is no lint, no unit-test suite, and no CI. Verification is: it compiles, and the editor opens.
Do not invent tooling commands.

## Targets and modules

| Target | Modules | Notes |
|---|---|---|
| `ModularStageEditor` (Editor) | `ModularStage` + `ModularStageEditor` | **This is the one you build.** |
| `ModularStage` (Game) | `ModularStage` | `ModularStage.Build.cs` lists `UnrealEd` in `PublicDependencyModuleNames` *outside* the `bBuildEditor` guard, so a clean Game/packaged build is not currently viable. |
| `Project_Alpha` / `Project_AlphaEditor` | — | **Legacy reference only.** Not listed in `ModularStage.uproject`, still on `BuildSettingsVersion.V5` / `EngineIncludeOrderVersion.Unreal5_4`, ~1,400 files. Code is *ported out* of it (see the `[DOC]` blocks in `Manager_UI.h`, `EventBusSubsystem.h` that say what the Alpha version did and why it changed). Don't build it, don't refactor it. |

Both `Build.cs` files call a local `AddIncludePathRecursive` that registers **every subdirectory**
under `Source/ModularStage` (and `Source/ModularStageEditor`) as a private include path. Consequences:

- Adding a new folder needs **no** `Build.cs` edit.
- Includes appear in two styles and both compile: module-qualified
  (`#include "ModularStage/Table/TableEnum.h"`) and bare (`#include "Table/MissionTaskTable.h"`).
  Match the file you're editing.
- `ModularStageEditor` shares the runtime PCH: `PrivatePCHHeaderFile = "../ModularStage/ModularStagePCH.h"`.
- The editor module sets `ShadowVariableWarningLevel = WarningLevel.Error` and
  `OptimizeCode = CodeOptimization.Never` — a shadowed variable is a hard build failure there.

UE 5.8 API notes already applied on `main` (commit `9efbfc1`): `InstancedStruct` is included as
`"StructUtils/InstancedStruct.h"`, `BuildSettingsVersion.V7`, `EngineIncludeOrderVersion.Unreal5_8`.
`origin/upgrade/ue5.8` is identical to `main`.

## Mission system — the core data flow

```
AMissionPrefab (actor, 7 hex tiles + TArray<FMissionTaskInfo> TaskList)
  └─ UActorComponent_MissionTaskExecutor
       └─ UMissionTaskExecutor (UObject + FTickableGameObject)
            ├─ SequentialTaskList : TArray<UMissionTaskBase>
            └─ registers itself with UManager_Mission
```

`FMissionTaskInfo` (`Table/MissionTaskTable.h`) is the authored unit. It carries `Step`, `Type`
(`EInGameTaskType`), `ObjectiveType` (`EMissionObjectiveType`), and a polymorphic
`FInstancedStruct TaskDetail` constrained by
`meta=(BaseStruct="/Script/ModularStage.MissionTaskData_Base")` — the concrete payload structs live
in `Table/MissionTaskData.h`.

**Two-level dispatch** — this trips people up:

1. `UMissionTaskExecutor::CreateTask` switches on **`EInGameTaskType`**
   (`SPAWN_OBJECT` / `SPAWN_MONSTER` / `MISSION`).
2. `MISSION` produces a `UMissionMultiTaskBase`, whose `CreateMainTask` switches again on
   **`EMissionObjectiveType`** (`Annihilation` / `BossRaid` / `Destination` / `Wait`).

A `UMissionMultiTaskBase` runs its `SubTaskList` sequentially (spawns, camera moves — the setup),
then runs one `MainTask` (a `UMissionTask_Stateful`) that decides success/failure. The whole
multi-task only reports `Complete` when the main task does.

`UMissionTask_Stateful` is the base you almost always want for a new objective. It owns the
`Idle → Working → Success/Failure` machine; subclasses override only `OnEnter` / `OnUpdate` /
`OnSuccess` / `OnRollBack` and call `MarkSuccess()` / `MarkFailure()`. `DoAction()` itself is already
implemented — don't override it.

### Adding a new objective type (the common task)

`MissionTask_BossRaid` is the worked example; grep it to see all touch points at once.

1. `Table/TableEnum.h` — add the `EMissionObjectiveType` entry.
2. `Table/MissionTaskData.h` — add `FMissionTaskData_<Name> : public FMissionTaskData_Base`.
3. `Mission/TaskSystem/MissionTask_<Name>.{h,cpp}` — derive from `UMissionTask_Stateful`.
4. `MissionMultiTaskBase.h/.cpp` — add `OnCreateMainTask_<Name>` and its `switch` case.
5. `ModularStageEditor/.../Widget/EditorView_MissionTask_<Name>_Renewal.{h,cpp}` — derive from
   `UEditorView_MissionTaskDetailBase` and override **`ApplyData()` only**; the base handles caching
   and validating `EntryData`. A matching `EditorUtilityWidget` Blueprint must exist and be returned
   by the class's static `GetWidgetBlueprintPath()`.

Reading `TaskDetail`: `GetPtr<T>()` returns a **const** pointer — declare the local as
`const FMissionTaskData_X*` (this was a real review fix, commit `080693c`).

## Subsystem conventions

No custom singletons. Managers are `UGameInstanceSubsystem`s under `UManagerBase`:

- Access is always the zero-arg static: `if (UManager_UI* UI = UManager_UI::Get()) { ... }`.
  Internally `UManagerBase::GetManager<T>()` → `UGameInstance_ModularStage::Get()`. It can return
  `nullptr` before the GameInstance exists — **always null-check**.
- `ShouldCreateSubsystem` is overridden to instantiate **only the most-derived class**, so a
  Blueprint/C++ subclass of `UManager_UI` replaces the base rather than doubling it.
- 🔴 **Subsystems never replicate** — no `UPROPERTY(Replicated)`, no RPCs. Authority gating belongs at
  the call sites (`HasAuthority()`), UI gating at `IsLocalController()`.

`UManager_Mission` owns `MainMissionExecutors` (sequential) and `SubMissionExecutors` (parallel),
and holds `ReplicatedExecutorIndex` (client-only, `FGuid` → executor). `UManager_PreLoad`,
`UManager_TableData`, `UManager_UI` follow the same shape.

## Global event system — two parallel paths

`FGlobalEventSystem` (`GlobalEventSystem/`) is a static facade; its handler is allocated and torn
down by `UEventBusSubsystem` (a GameInstance subsystem) so listener maps die with the game instance
instead of surviving PIE / seamless travel.

| Path | Key | API |
|---|---|---|
| Type-keyed (original) | `UINTERFACE` deriving `UGlobalEventListener` | `AddEventListener<I>()` / `ExecuteEvent<I>(lambda)` |
| Tag-keyed (widget events, newer) | `FGameplayTag` + `FInstancedStruct` payload | `AddWidgetEventListener()` / `BroadcastWidgetEvent(Tag, Payload)` |

Tags and payload structs live in `WidgetEventTags.h` / `WidgetEventPayloads.h`. Events are
**local-scope only** — never replicated.

## UI — CommonUI layer stack

`AMSHUD` → `UMSPrimaryGameLayout` → four `UCommonActivatableWidgetContainerBase` layers bound by
`UPROPERTY(meta=(BindWidget))`: `GameLayer`, `GameMenuLayer`, `MenuLayer`, `ModalLayer`. **The
Blueprint subclass must name its widgets exactly that** or the BP fails to compile. Layers are
registered against `TAG_UI_Layer_*` (`UI/Layout/UILayerTags.h`) in `NativeOnInitialized`.

`UManager_UI` is the only thing gameplay code should talk to:

- `Show<T>()` routes by base class — `UMSPageWidget` → Menu, `UMSPopupWidget` → Modal,
  `UMSHUDWidget` → Game. A non-matching `T` is a `static_assert`.
- `Hide<T>()` closes the top of that type's layer (fine for pages, which are one-at-a-time);
  `Hide(UMSViewBase*)` closes a **specific instance** (required for popups, where the same class is
  shown multiple times with different content).
- The manager is intentionally **stateless** — it tracks no active widgets. Don't add tracking
  containers to it; resolve through `ResolveHUD()` → `GetPrimaryGameLayout()`.

## Networking (listen server)

The host is server and client at once. Mission replication path:

`AMissionPrefab::MissionId` (`ReplicatedUsing=OnRep_MissionId`, server-assigned `FGuid`) is the
shared identity — `UMissionTaskExecutor::GetMissionId()` returns the owning prefab's value, so both
sides can resolve the same executor from a replicated payload. State changes go
`UManager_Mission::NotifyMissionStateChanged` → `MissionReplicationComponent` on `AMSGameState` →
`FReplicatedMissionState` → `UManager_Mission::ApplyReplicatedState` (the single broadcast entry
point, used by both the client OnRep and the host's direct upsert).

Match start is gated: clients call `AModularStagePlayerController::Server_ReportReady` after local
preloading, `AModularStageGameMode::NotifyPlayerReady` counts them, `OnAllPlayersReady` fires once.

RPC prefixes: `Server_` (client→server, add `WithValidation` for anything authoritative), `Client_`,
`Multicast_`, `OnRep_`.

## Editor module

`FModularStageEditor` (`IModuleInterface`) registers menus via `FEditorMenuHelper` and a workflow tab
via `WorkflowTabFactory_Mission`. Most tools are **`UEditorUtilityWidget`s**, not Slate: derive from
`UEditorWidgetBase`, provide the statics `GetMenuName` / `GetMenuDisplayName` / `GetMenuTooltip` /
`GetWidgetBlueprintPath`, and open with the template
`UEditorWidgetBase::ShowEditorUtilityWidget<TWidget>()`. `UEditorWidgetBase` also hooks editor-exit
cleanup (`OnEditorExit_Implement`).

`EditorCommands_Refactoring_Guide.txt` at the repo root is a **proposal**, not the current state —
`FModularStageEditorCommands` / `TCommands<>` does not exist yet. Treat it as the intended direction
if asked to add shortcuts or conditional menu enabling.

## Python / MCP bridge

Three layers under `Content/Python/` (design doc: `MCP_Implementation_Report.md`):

- `layer1_unreal_api/editor_api.py` — transactions, actor lookup, dirty/save.
- `layer2_mission_service/*.py` — prefab tiles, beacons, tasks, spawners, registry.
- `layer3_entry_points/mcp_bridge.py` — TCP server on `127.0.0.1:12345`, started automatically by
  `Content/Python/init_unreal.py` when the editor launches.

Protocol is 4-byte big-endian length prefix + JSON. 🔴 **Socket threads must never call `unreal.*`.**
`_handle_client` pushes the request onto `_command_queue`; `_game_thread_tick` (registered via
`register_slate_pre_tick_callback`) drains it and is the only place `_process_command` runs. Client
waits 10 s then returns a timeout error, because the tick stalls while the editor is busy. Any new
command goes in the `_process_command` if/elif chain and must respect that rule.

The external MCP server half lives in `Source/MissionTools/`, which is **gitignored** — it is
maintained in the separate `MissionEditorMCP` repository.

## Code conventions

- **Comments are written in Korean.** Newer ported classes use `// [DOC]` blocks that record *why*
  the design changed from `Project_Alpha` — keep that habit when porting more.
- `TObjectPtr<T>` for every `UPROPERTY` object reference in a header; raw pointers only as locals.
- `IsValid(X)` over `X != nullptr`. `Cast<T>` result-checked directly — never `IsA()` then `Cast`.
- IWYU: forward-declare in `.h`, include in `.cpp`. `GlobalEventSystem.h` forward-declares
  `FInstancedStruct` on purpose; `Manager_UI` hides `UILayerTags.h` behind static accessors in the
  `.cpp`. Don't undo those.
- `FTimerHandle` is always a member, never a local. Replicated components are created in the
  constructor with `CreateDefaultSubobject`, never `NewObject` in `BeginPlay`.
- Static data goes in `UDataTable` / `UPrimaryDataAsset`; no magic numbers in C++ — expose via
  `UPROPERTY(EditDefaultsOnly)`.
- Prefixes: `A` actor, `U` UObject/component/subsystem, `F` struct, `E` enum, `I` interface.
- Some older `Build.cs` / source comments are mojibake (cp949 read as UTF-8). Leave them; don't
  "fix" the encoding as a drive-by, it produces noisy diffs.

## Commit conventions

This repo is also written to by the AX cluster's distributed pipeline, so history mixes human and
machine commits. Machine-generated subjects use these prefixes — match them if you are producing
work in that flow, and otherwise write a plain Korean subject like the human commits:

- `[skeleton] <feature>: N files for distributed implementation`
- `[verify-merge] <hash> <path> by <workshop-host>`
- `[review fix] <what> (work=<work-id>)`
- `Merge work <work-id>: <Title>` with `Reviewed-by:` and `Refs-work:` trailers.

Work branches are named `work/<YYYYMMDD_HHMM>_<slug>`.
