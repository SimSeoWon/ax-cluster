\# UE5 Asset Loading \& Memory Management



Claude must strictly follow asynchronous loading patterns to prevent frame hitches and memory leaks during gameplay. Hard references should be avoided for heavy assets.



\## 1. Soft References

\- Use `TSoftObjectPtr<T>` for specific asset instances (e.g., textures, static meshes, sound cues).

\- Use `TSoftClassPtr<T>` for Blueprint classes (e.g., character BPs, widget BPs) to be spawned.

\- \*Rule:\* Never use hard pointers (`T\*` or `TObjectPtr<T>`) for heavy assets in `UPROPERTY` unless they are strictly required to be loaded with the object.



\## 2. Asynchronous Loading (FStreamableManager)

\- Never use `LoadObject<T>()` or `LoadClass<T>()` during gameplay.

\- Do not use `ConstructorHelpers::FObjectFinder` outside of a class constructor.

\- Always use `UAssetManager::GetStreamableManager().RequestAsyncLoad()` to load soft references.

\- \*Callback Safety:\* Ensure the callback function checks the validity of the loading object (using `TWeakObjectPtr` or `IsValid()`) before using the loaded asset, as the requesting object might have been destroyed during the load.



\## 3. Spawning and Instantiation

\- Only call `GetWorld()->SpawnActor<T>()` or `NewObject<T>()` AFTER the async load callback confirms the asset is fully loaded.

\- Ensure all actor spawning happens explicitly on the GameThread.



\## 4. Asset Caching

\- If an asset is loaded asynchronously and needs to be reused frequently (e.g., UI widgets, common VFX), cache the loaded hard reference in a `UGameInstanceSubsystem` or a dedicated `UWorldSubsystem` to keep it in memory.

