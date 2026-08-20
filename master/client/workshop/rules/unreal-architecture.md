\# Unreal Engine 5 Architecture \& Lifecycle Rules



This document maps general software architecture concepts to Unreal Engine native systems. Claude must use these UE-specific classes for modularity and logic separation.



\## 1. The "Service Layer" / Global Managers -> `USubsystem`

Do not create custom Singleton classes. All global or scoped manager logic must be implemented using Unreal's Subsystem framework.



\- \*\*`UGameInstanceSubsystem`\*\*: For data/services that persist across the entire application lifecycle (e.g., UserProfileService, GlobalConfigService).

\- \*\*`UWorldSubsystem`\*\*: For data/services tied to a specific level or map (e.g., MatchmakingService, EnvironmentManager).

\- \*\*`ULocalPlayerSubsystem`\*\*: For local player-specific data (e.g., LocalInputSettings, UIState).

\- \*Rule:\* Subsystems cannot replicate. Do not add RPCs or `Replicated` properties here.



\## 2. Reusable Business Logic -> `UActorComponent`

Instead of deep Actor inheritance, encapsulate features into components.

\- Examples: `UHealthComponent`, `UInventoryComponent`, `UCombatStatComponent`.

\- \*Rule:\* If the logic requires network replication, it MUST be a `UActorComponent` attached to an Actor.



\## 3. Data Storage \& Repositories -> `UDataAsset` / `UDataTable`

\- Static game data (item stats, default configs) should be stored in `UDataTable` or custom `UPrimaryDataAsset`.

\- Do not hardcode magic numbers or strings in C++. Expose them via `UPROPERTY(EditDefaultsOnly)` and configure them in DataAssets.



\## 4. Interaction \& Decoupling -> Interfaces \& Delegates

\- Use `UINTERFACE` for cross-class communication where tight coupling is not desired.

\- Use `DECLARE\_DYNAMIC\_MULTICAST\_DELEGATE` for events that Blueprint UI might need to listen to (e.g., OnHealthChanged).

