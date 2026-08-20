\# UE5 C++ \& Networking Code Style



Claude must strictly follow these Unreal Engine 5 C++ coding standards.



\## 1. Pointers \& Memory Management (UE5 Standard)

\- \*\*TObjectPtr:\*\* Use `TObjectPtr<T>` instead of raw pointers (`T\*`) for all `UPROPERTY` object references in header files. 

&nbsp; - \*Example:\* `UPROPERTY() TObjectPtr<AActor> TargetActor;`

&nbsp; - Raw pointers are still acceptable for local variables inside function bodies.

\- \*\*Validity Checks:\*\* Always check `IsValid(Object)` instead of `Object != nullptr`, especially before broadcasting delegates or calling RPCs.

\- \*\*Garbage Collection:\*\* Any class-level UObject reference must be marked with `UPROPERTY()` to prevent accidental garbage collection.



\## 2. Casting \& Type Checking

\- Use `Cast<T>(Object)` and check the result directly. 

&nbsp; - \*Good:\* `if (UMyComponent\* Comp = Cast<UMyComponent>(Actor)) { ... }`

&nbsp; - \*Bad:\* `if (Actor->IsA(UMyComponent::StaticClass())) { Cast<UMyComponent>(Actor)->... }`



\## 3. Networking \& RPC Standards

\- \*\*Naming Conventions:\*\*

&nbsp; - `Server\_...` for Server RPCs.

&nbsp; - `Client\_...` for Client RPCs.

&nbsp; - `Multicast\_...` for Multicast RPCs.

&nbsp; - `OnRep\_...` for RepNotify functions.

\- \*\*Validation:\*\* Server RPCs must include `WithValidation` in the `UFUNCTION` macro if handling critical game state or client input.

\- \*\*Replication Setup:\*\* - All replicated properties must be registered in `GetLifetimeReplicatedProps`.

&nbsp; - Replicated subobjects (like Components) must call `SetIsReplicatedByDefault(true)` in their constructor.



\## 4. IWYU (Include What You Use)

\- Keep header includes to an absolute minimum to optimize R\&D compile times.

\- Use forward declarations (`class UMyComponent;`) in `.h` files whenever possible.

\- Include the specific headers in `.cpp` files.

