

\# UE5 Listen Server Session Management Rules



This document defines how Claude should implement session lifecycle and network connection logic for this Listen Server project. The architecture assumes a private gathering platform where clients are trusted.



\## 1. Session Manager (`UGameInstanceSubsystem`)

All session-related logic MUST be encapsulated in a dedicated `UGameInstanceSubsystem` (e.g., `USessionManagerSubsystem`).

\- Do \*\*not\*\* handle `IOnlineSessionPtr` or `CreateSession`/`JoinSession` logic inside `AGameModeBase`, `APlayerController`, or UI Widgets.

\- UI Widgets must only bind to delegates provided by the Session Subsystem to update the display.



\## 2. Host Lifecycle (Server-Side)

\- \*\*Creation:\*\* The host creates a session using `CreateSession`. Upon success, the host must load the target map using `GetWorld()->ServerTravel("/Game/Maps/YourMapName?listen")`.

\- \*\*Destruction:\*\* When the host decides to leave or close the game, they must explicitly call `DestroySession()`.



\## 3. Disconnect \& Host Migration Policy

Since this is a small-scale gathering platform, \*\*Host Migration is NOT supported\*\*. 

\- When the host leaves or the session is destroyed, all connected clients must be cleanly kicked out.

\- \*\*Implementation:\*\* Bind to the `OnSessionUserInviteAccepted` or engine network failure delegates (e.g., `GEngine->OnNetworkFailure`) in the `UGameInstance` or Subsystem.

\- \*\*Client Behavior:\*\* When a client loses connection to the host, they must automatically be routed back to the Main Menu (Title Screen) map via local travel (`GetWorld()->ServerTravel` is for servers; clients use `ClientTravel` or just `UGameplayStatics::OpenLevel` to a local map), and present a UI message like "Host has disconnected."



\## 4. Trusted Client Connection

\- Clients are trusted in this environment. Do not implement complex token validation or anti-cheat handshakes during the `PreLogin` or `Login` phases in `AGameModeBase` unless explicitly requested.

\- Focus on fast, seamless joining. Use `FindSessions` and `JoinSession`, and immediately travel the client to the resulting connect string.



\## 5. Map Travel \& Seamless Travel

\- To move the entire group of players from a lobby map to a gathering map, the Host must use `GetWorld()->ServerTravel()`.

\- Ensure `bUseSeamlessTravel = true` is set in the `AGameModeBase` if transitioning between heavy maps to prevent clients from disconnecting during load times.

\- State that needs to persist across travels must be stored in `UGameInstanceSubsystem`, not in `AGameState` or `APlayerState`, as those are destroyed during standard travel.

