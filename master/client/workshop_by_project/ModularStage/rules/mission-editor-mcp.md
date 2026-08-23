# Mission Editor MCP — LLM 작업 가이드

이 문서는 MCP 툴로 AMissionPrefab 에셋을 편집할 때 따라야 할 규칙과 워크플로우를 정의합니다.

---

## 1. 구조 개요

```
AMissionPrefab (Blueprint 에셋)
├── SeptetTiles[0..6]          — 7개 헥스 타일 (0=중심, 1~6=주변)
├── TaskList: FMissionTaskInfo[] — 순차 실행 태스크 목록
└── SCS Components
    ├── UMissionPropsComponent_Spawner  (IMissionPropComponent)
    └── UMissionPropsComponent_Trigger  (IMissionPropComponent)
```

레벨에는 `ABeacon` 이 프리팹 Blueprint 에셋을 참조하여 배치됩니다.

---

## 2. 타일 인덱스 (HexTileIndex)

```
      1
   6     2
      0        ← 0 = 중심 타일
   5     3
      4
```

- 0: 중심
- 1~6: 시계 방향 주변 타일

---

## 3. IMissionPropComponent (스포너 / 트리거)

### 공통 규칙
- 모든 컴포넌트는 `ComponentGuid: FGuid` 로 식별됩니다.
- GUID는 C++ `PostInitProperties`에서 자동 발번됩니다. **Python이 직접 발번하면 안 됩니다.**
- GUID를 읽으려면 `USpawnerEditorLibrary::GetSpawnerComponentGuid(Node)` 를 사용합니다.

### UMissionPropsComponent_Spawner 주요 속성

| 속성 | 타입 | 설명 |
|---|---|---|
| `ComponentGuid` | FGuid | 고유 식별자 (자동 발번) |
| `HexTileIndex` | int32 | 스포너가 위치할 타일 (0~6) |
| `SpawnTileIndices` | TArray<int32> | 몬스터가 소환될 타일 목록 |
| `PatrolTileIndices` | TArray<int32> | 순찰 경로 타일 목록 |
| `ResourcesPath` | FString | 소환할 Blueprint 에셋 경로 |

### MCP 툴

```python
# 스포너 추가
add_prefab_spawner(
    prefab_asset_path="/Game/Blueprints/BP_MyPrefab",
    variable_name="Spawner_Goblin",
    hex_tile_index=4,
    spawn_tile_indices=[4, 5],
    resource_path="/Game/Characters/BP_Goblin"
)

# 스포너 목록 조회 (ComponentGuid 포함)
get_prefab_spawners(prefab_asset_path="/Game/Blueprints/BP_MyPrefab")

# 스포너 삭제
delete_prefab_spawner(
    prefab_asset_path="/Game/Blueprints/BP_MyPrefab",
    variable_name="Spawner_Troll"
)

# 스포너 타일 수정
set_spawner_tiles(
    prefab_asset_path="/Game/Blueprints/BP_MyPrefab",
    variable_name="Spawner_Goblin",
    hex_tile_index=3
)
```

---

## 4. FMissionTaskInfo (태스크)

### 핵심 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `SerializeID` | FGuid | 이 태스크의 고유 식별자. **생성자에서 자동 발번.** |
| `ParentID` | FGuid | 연결된 IMissionPropComponent의 ComponentGuid |
| `Step` | int32 | 실행 순서 (0부터 시작, 오름차순) |
| `Title` | FString | 태스크 이름 |
| `Desc` | FString | 태스크 설명 |
| `Type` | EInGameTaskType | 태스크 종류 (아래 참고) |
| `ObjectiveType` | EMissionObjectiveType | 목표 타입 |
| `TaskDetail` | FInstancedStruct | 타입별 상세 데이터 (에디터 위젯에서 수동 설정) |

### EInGameTaskType

| 값 | 설명 | 연결 컴포넌트 |
|---|---|---|
| `NONE` | 타입 미지정 | — |
| `MISSION` | 목표 달성 태스크 (섬멸, 도착 등) | Trigger 또는 없음 |
| `SPAWN_MONSTER` | 몬스터 소환 | **Spawner** (ParentID 필수) |
| `SPAWN_OBJECT` | 오브젝트 소환 | **Spawner** (ParentID 필수) |
| `PLAY_SEQUENCE` | 시퀀스 재생 | — (확장 예정) |
| `PLAY_DIALOG` | 다이얼로그 재생 | — (확장 예정) |

### EMissionObjectiveType

| 값 | 설명 |
|---|---|
| `None` | 목표 없음 |
| `Destination` | 특정 위치 도달 |
| `Annihilation` | 모든 적 섬멸 |
| `Escort` | 호위 (확장 예정) |
| `Defense` | 방어 (확장 예정) |

---

## 5. 워크플로우 — 몬스터 스폰 설정

> **규칙**: SPAWN_MONSTER 태스크는 반드시 Spawner 컴포넌트의 ComponentGuid를 ParentID로 가져야 합니다.

### Step 1. 스포너 추가

```python
add_prefab_spawner(
    prefab_asset_path="/Game/Blueprints/BP_MyPrefab",
    variable_name="Spawner_Goblin",
    hex_tile_index=4,
    spawn_tile_indices=[4, 5],
    resource_path="/Game/Characters/BP_Goblin"
)
```

### Step 2. 스포너 GUID 읽기

```python
result = get_prefab_spawners("/Game/Blueprints/BP_MyPrefab")
# result["spawners"][n]["component_guid"] 로 GUID 확인
```

> `get_prefab_spawners` 응답에 `component_guid` 필드가 없다면
> UE Python에서 `SpawnerEditorLibrary.get_spawner_component_guid(node)` 로 직접 읽어야 합니다.

### Step 3. 태스크 등록

```python
set_prefab_tasks(
    prefab_asset_path="/Game/Blueprints/BP_MyPrefab",
    tasks=[
        {
            "step": 0,
            "title": "고블린 소환",
            "desc": "4번 타일에 고블린을 소환합니다",
            "type": "SPAWN_MONSTER",
            "objective_type": "NONE",
            "parent_id": "<Spawner_Goblin의 ComponentGuid>"
            # serialize_id 생략 시 C++ 생성자에서 자동 발번
        },
        {
            "step": 1,
            "title": "고블린 섬멸",
            "desc": "모든 고블린을 처치합니다",
            "type": "MISSION",
            "objective_type": "ANNIHILATION",
            "parent_id": "<Spawner_Goblin의 ComponentGuid>"
        }
    ]
)
```

---

## 6. 주의사항

- **GUID 중복 금지**: `SerializeID`는 생성자 자동 발번을 믿으세요. 기존 태스크를 수정할 때는 `get_prefab_tasks`에서 받은 `serialize_id`를 그대로 전달합니다.
- **ParentID 없는 SPAWN_MONSTER**: 런타임에서 어떤 스포너를 쓸지 알 수 없어 소환 실패합니다.
- **TaskDetail**: `FMissionTaskData_Monster`(MonsterID, TileIndex) 등 상세 데이터는 MCP로 설정 불가 — 에디터 위젯(TaskListEditorWidget)에서 수동 입력합니다.
- **에셋 경로 형식**: `/Game/Blueprints/BP_MyPrefab` (`.uasset` 접미사 없이)
- **SCS 없는 Blueprint**: 에디터에서 컴포넌트를 한 번도 추가하지 않은 Blueprint는 SCS가 없어 `add_prefab_spawner`가 실패합니다. 에디터에서 아무 컴포넌트나 추가 후 Compile & Save 하세요.

---

## 7. 프리팹 레지스트리

`PREFAB_REGISTRY.md` (프로젝트 루트) — 스캔 스냅샷 캐시.
에셋 경로, 태그, 설명, 스포너 목록이 담겨 있습니다.
동기화가 깨졌다고 느껴지면 `collect_prefab_registry` 툴로 갱신합니다.
